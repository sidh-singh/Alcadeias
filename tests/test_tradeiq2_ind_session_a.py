"""
Port A of Session Hunter [TradeIQ] (``backtesting/research/tradeiq2_ind_session.py``).

1. One hand-computed test per trap of the map's porting risks (``orb_session_swing_ha.md`` section 2.6, risks 1-13),
   named after it (``test_trapNN_...``). The map's numbered tests (2.6, tests 1-14) are inside them or next to them
   (``test_spec09/10/13_...``); each says what the wrong reading would give on the same bars.
2. The confirmations not covered by a trap (premium / discount, relative volume, tight range, yesterday's candle).
3. The numba kernel against ``pine_ref``, a statement-by-statement plain-Python transcription of the script's l.127-492
   (its own per-bar trade loop over ``open_``, iterated backwards with ``remove``), on random bars with gold's and BTC's
   schedules, data holes, gaps, ties and a daylight-saving change.
4. Truncation invariance: everything up to bar T is unchanged when the bars after T are removed (but the decisions not
   yet taken: 'pending', 'open').
5. Real bars (skipped when the tick store is absent): both symbols, M5 and M15 (PREREG 6.6), 2019-01-01 to 2024-06-30
   with the hold-out guard closed. Structure, timing and geometry only: no profit or loss is computed or looked at.

Prices of the hand cases are multiples of 1/8 or are compared with the formula itself, so every float is exact.
Times are New York wall-clock times of the bars' OPENS (``ny``); 2019-01-07 is a Monday (EST, UTC-5), 2019-07-08 a
Monday (EDT, UTC-4).
"""

from __future__ import annotations

import gc
import math
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_session as SH
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

nan = math.nan
NYZ = ZoneInfo("America/New_York")
SYMS = ("XAUUSDm", "BTCUSDm")
SIGNAL_COLS = ["setup", "bar", "t_signal", "dir", "stop", "tgt_ref", "r_hi", "r_lo", "entry_bar"]


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """The study folder seen by study 1's hold-out guard: an empty tmp folder (the hold-out is closed)."""
    d = tmp_path / "study"
    d.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d


# ───────────────────────────── hand-made charts ─────────────────────────────

def ny(s: str) -> int:
    """UTC epoch seconds of the New York wall-clock time ``s`` ('YYYY-mm-dd HH:MM')."""
    return int(pd.Timestamp(s, tz=NYZ).timestamp())


class Chart:
    """Bars of ``tf`` minutes keyed by their New York open time. ``flat`` fills [a, z) with o = c = px, high px + half,
    low px - half (true range 1.0 by default, so ATR(14) is about 1); ``put`` sets one bar; ``drop`` removes [a, z)."""

    def __init__(self, tf: int = 15):
        self.tf = tf
        self.rows = {}

    def flat(self, a, z, px=100.0, half=0.5, v=100.0):
        for ts in range(ny(a), ny(z), 60 * self.tf):
            self.rows[ts] = (px, px + half, px - half, px, v)
        return self

    def put(self, when, o, h, l, c, v=100.0):
        assert l <= min(o, c) and h >= max(o, c), (when, o, h, l, c)
        self.rows[ny(when)] = (o, h, l, c, v)
        return self

    def drop(self, a, z):
        for ts in [k for k in self.rows if ny(a) <= k < ny(z)]:
            del self.rows[ts]
        return self

    def arrays(self):
        ts = sorted(self.rows)
        a = np.array([self.rows[k] for k in ts], np.float64)
        return np.array(ts, np.int64), a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]

    def ix(self, when) -> int:
        return sorted(self.rows).index(ny(when))

    def atr(self) -> np.ndarray:
        _, _, h, l, c, _ = self.arrays()
        return I.atr(h, l, c, 14)

    def close(self, when) -> float:
        return self.rows[ny(when)][3]

    def run(self, setups=SH.SETUPS, conf=(), htf=None, **kw) -> pd.DataFrame:
        t, o, h, l, c, v = self.arrays()
        hd = np.zeros(len(t)) if htf is None else htf
        return SH.session_hunter(t, o, h, l, c, v, self.tf, hd, setups=setups, conf=conf, **kw)

    def state(self, **kw) -> pd.DataFrame:
        t, o, h, l, c, _ = self.arrays()
        return SH.day_state(t, o, h, l, c, self.tf, **kw)


def tuesday(tf=15, start="2019-01-07 12:00", end="2019-01-08 20:00"):
    """Flat bars from Monday 12:00 to Tuesday 20:00 (EST); Tuesday's Asia session (Monday 20:00-24:00) spans 99..101:
    the 21:00 bar's high and the 22:00 bar's low."""
    ch = Chart(tf).flat(start, end)
    ch.put("2019-01-07 21:00", 100.0, 101.0, 99.5, 100.0)
    ch.put("2019-01-07 22:00", 100.0, 100.5, 99.0, 100.0)
    return ch


def asia_short(ch, day="2019-01-08"):
    """The map's tests 3-4 on ``day``: a wick above the Asia high at 02:15 closing inside with no FVG; 02:30 inside, no
    FVG; at 02:45 a bearish FVG (its high 100.5625 < the 02:15 low 100.625) with a close inside: the short. The 03:00
    bar opens at 100.25."""
    ch.put(f"{day} 02:15", 100.625, 101.75, 100.625, 100.75)
    ch.put(f"{day} 02:30", 100.75, 100.875, 100.375, 100.5)
    ch.put(f"{day} 02:45", 100.5, 100.5625, 100.0, 100.125)
    ch.put(f"{day} 03:00", 100.25, 100.5, 99.75, 100.0)
    return ch


def london_long(ch, day="2019-01-08"):
    """The London range is the flat 99.5..100.5 (02:00-05:00). At 10:30 a sweep of the London low to 98.75 closing
    below it, at 10:45 a close back inside (99.75): the LS long (stop 98.75, 1.0 below the close)."""
    ch.put(f"{day} 10:30", 100.0, 100.25, 98.75, 99.25)
    ch.put(f"{day} 10:45", 99.25, 99.875, 99.0, 99.75)
    return ch


def rows(df, setup=None):
    return df if setup is None else df[df.setup == setup]


def one(df, setup=None):
    r = rows(df, setup)
    assert len(r) == 1, r.to_string()
    return r.iloc[0]


# ───────────────────────────── 1. the traps of the map's 2.6 ─────────────────────────────

def test_trap01_day_key_is_the_new_york_date_of_time_plus_4h_and_the_weekday_comes_from_it():
    # the map's test 1: 19:59 / 20:00 New York = 00:59 / 01:00 UTC in winter, 23:59 / 00:00 UTC in summer
    def utc(s):
        return int(pd.Timestamp(s, tz="UTC").timestamp())

    def date_of(day_key):
        return [str(pd.Timestamp(int(d) * 86400, unit="s").date()) for d in day_key]

    win = SH.clock(np.array([utc("2019-01-08 00:59"), utc("2019-01-08 01:00")]), 1)
    assert date_of(win["day_key"]) == ["2019-01-07", "2019-01-08"]
    assert win["ny_min"].tolist() == [19 * 60 + 59, 1200] and win["new_day"].tolist() == [False, True]
    summer = SH.clock(np.array([utc("2019-07-08 23:59"), utc("2019-07-09 00:00")]), 1)
    assert date_of(summer["day_key"]) == ["2019-07-08", "2019-07-09"]
    assert summer["ny_min"].tolist() == [19 * 60 + 59, 1200] and summer["new_day"].tolist() == [False, True]
    # the weekday is the day key's: Friday 20:00 opens Saturday's day, Sunday 20:00 Monday's
    wk = SH.clock(np.array([ny("2019-01-11 19:59"), ny("2019-01-11 20:00"), ny("2019-01-13 19:59"),
                            ny("2019-01-13 20:00")]), 1)
    assert date_of(wk["day_key"]) == ["2019-01-11", "2019-01-12", "2019-01-13", "2019-01-14"]
    assert wk["weekday"].tolist() == [True, False, False, True]

    # the Asia session (20:00-24:00) belongs to the next day: Tuesday's AS reads Monday evening's 101, not the
    # 19:45 bar's 102 (Monday's day)
    ch = asia_short(tuesday()).put("2019-01-07 19:45", 100.0, 102.0, 99.5, 100.0)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert (r.r_hi, r.r_lo, r.bar) == (101.0, 99.0, ch.ix("2019-01-08 02:45"))
    # a day's high runs 20:00 to 20:00: Wednesday's pdh holds Tuesday 19:45's 102.5 and not Tuesday 20:15's 103,
    # which is Wednesday's (a midnight day would give 103 from 00:00)
    ch = tuesday(end="2019-01-09 03:00").put("2019-01-08 19:45", 100.0, 102.5, 99.5, 100.0)
    ch.put("2019-01-08 20:15", 100.0, 103.0, 99.5, 100.0)
    st = ch.state()
    assert st.pdh[ch.ix("2019-01-08 20:00")] == 102.5 and st.pdh[ch.ix("2019-01-09 00:30")] == 102.5
    assert st.new_day[ch.ix("2019-01-08 20:00")] and not st.new_day[ch.ix("2019-01-09 00:00")]

    # Saturday's day (BTC: Friday 20:00 to Saturday 20:00) is not a weekday: the same clean sweep gives nothing
    sat = Chart(15).flat("2019-01-11 12:00", "2019-01-12 12:00")
    sat.put("2019-01-11 21:00", 100.0, 101.0, 99.5, 100.0).put("2019-01-11 22:00", 100.0, 100.5, 99.0, 100.0)
    asia_short(sat, "2019-01-12")
    assert sat.run(setups=("AS",), conf=("FVG",)).empty
    fri = Chart(15).flat("2019-01-10 12:00", "2019-01-11 12:00")
    fri.put("2019-01-10 21:00", 100.0, 101.0, 99.5, 100.0).put("2019-01-10 22:00", 100.0, 100.5, 99.0, 100.0)
    asia_short(fri, "2019-01-11")
    assert one(fri.run(setups=("AS",), conf=("FVG",))).bar == fri.ix("2019-01-11 02:45")

    # summer (EDT): the same Tuesday on the New York clock, 4 hours after UTC
    jul = Chart(15).flat("2019-07-08 12:00", "2019-07-09 20:00")
    jul.put("2019-07-08 21:00", 100.0, 101.0, 99.5, 100.0).put("2019-07-08 22:00", 100.0, 100.5, 99.0, 100.0)
    asia_short(jul, "2019-07-09")
    r = one(jul.run(setups=("AS",), conf=("FVG",)))
    assert r.t_signal == int(pd.Timestamp("2019-07-09 07:00", tz="UTC").timestamp())   # 02:45 EDT + 15 min


def gold_weekend(sunday_open="2019-01-13 18:00"):
    """Gold's week end: Thursday 18:00 to Friday 17:00, then Sunday from ``sunday_open`` to Tuesday 20:00 (Monday's
    17:00-18:00 break left out). Friday's day spans 95..105 (the 08:00 high, the 09:00 low); its first bar (Thursday
    20:00) opens at 100 and its last (16:45) closes at 99. Monday 02:00 sweeps Friday's high (105.5) and closes back
    inside (104.5); Tuesday 03:00 sweeps Monday's high (106.25 > 105.5) and closes inside (105.25)."""
    ch = Chart(15).flat("2019-01-10 18:00", "2019-01-11 17:00").flat(sunday_open, "2019-01-15 20:00")
    ch.drop("2019-01-14 17:00", "2019-01-14 18:00")
    ch.put("2019-01-11 08:00", 100.0, 105.0, 99.5, 100.0).put("2019-01-11 09:00", 100.0, 100.5, 95.0, 100.0)
    ch.put("2019-01-11 16:45", 100.0, 100.5, 98.75, 99.0)
    ch.put("2019-01-14 02:00", 104.75, 105.5, 104.375, 104.5)
    ch.put("2019-01-15 03:00", 105.0, 106.25, 104.875, 105.25)
    return ch


def test_trap02_monday_pwk_quirk_and_gold_sunday_pseudo_day():
    ch = gold_weekend()
    # the map's test 14: Sunday 18:00-19:45 is a day of its own ("Sunday", not a weekday); it takes Friday's levels
    # (pWk true there), then Sunday 20:00 opens Monday's day with pWk := false (the pseudo-day was not a weekday)
    st = ch.state()
    sun, sun20, mon2, tue3 = (ch.ix(s) for s in ("2019-01-13 18:00", "2019-01-13 20:00", "2019-01-14 02:00",
                                                  "2019-01-15 03:00"))
    assert st.new_day[sun] and st.new_day[sun20] and not st.weekday[sun] and st.weekday[sun20]
    assert (st.pdh[sun], st.pdl[sun], st.p_open[sun], st.p_close[sun], bool(st.p_wk[sun])) == (105.0, 95.0, 100.0,
                                                                                                 99.0, True)
    assert st.mo[sun] == 100.0                               # the pseudo-day's "midnight open" is its 18:00 open
    assert (st.pdh[mon2], st.pdl[mon2], bool(st.p_wk[mon2])) == (105.0, 95.0, False)      # Friday's, but pWk false
    assert (st.pdh[tue3], st.pdl[tue3], bool(st.p_wk[tue3])) == (105.5, 99.5, True)       # Monday's
    assert not st.p_wk[sun20:ch.ix("2019-01-14 19:45") + 1].any()
    # the map's test 2: the clean sweep of Friday's high on Monday gives nothing; Tuesday trades Monday's levels
    r = one(ch.run(setups=("PD",)))
    assert (r.bar, r.dir, r.r_hi, r.r_lo, r.stop, r.tgt_ref) == (tue3, -1, 105.5, 99.5, 106.25, 99.5)
    # the logged variant gives Monday Friday's levels (and leaves Tuesday as it was)
    v = ch.run(setups=("PD",), monday_friday_levels=True)
    assert v.bar.tolist() == [mon2, tue3]
    m = v.iloc[0]
    assert (m.dir, m.r_hi, m.r_lo, m.stop, m.tgt_ref) == (-1, 105.0, 95.0, 105.5, 95.0)
    assert ch.state(monday_friday_levels=True).p_wk[sun20:].all()
    # yesterday's candle: the quirk never runs PD on Monday; the variant reads Friday's candle (open 100 > close 99:
    # shorts pass). Monday's own candle (open 100 = close 100) passes nothing on Tuesday.
    assert ch.run(setups=("PD",), conf=("YC",)).empty
    assert ch.run(setups=("PD",), conf=("YC",), monday_friday_levels=True).bar.tolist() == [mon2]
    # no pseudo-day (gold reopening at 20:00): Sunday 20:00 follows Friday directly, pWk is true on Monday
    ch2 = gold_weekend(sunday_open="2019-01-13 20:00")
    assert ch2.run(setups=("PD",)).bar.tolist() == [ch2.ix("2019-01-14 02:00"), ch2.ix("2019-01-15 03:00")]
    # BTC: Saturday and Sunday are days of their own; Monday's pWk is false and its pdh is Friday's (not Saturday's
    # 110)
    btc = Chart(15).flat("2019-01-10 18:00", "2019-01-15 20:00")
    btc.put("2019-01-11 08:00", 100.0, 105.0, 99.5, 100.0).put("2019-01-11 09:00", 100.0, 100.5, 95.0, 100.0)
    btc.put("2019-01-12 08:00", 100.0, 110.0, 99.5, 100.0)
    btc.put("2019-01-14 02:00", 104.75, 105.5, 104.375, 104.5)
    assert btc.run(setups=("PD",)).empty
    m = one(btc.run(setups=("PD",), monday_friday_levels=True))
    assert (m.bar, m.r_hi, m.r_lo) == (btc.ix("2019-01-14 02:00"), 105.0, 95.0)


def test_trap03_the_whole_bar_inside_the_window_rule():
    # M15: the 04:45 bar ends at 05:00 and is inside London (285 + 15 <= 300); the 05:00 bar is not
    ch = tuesday().put("2019-01-08 04:30", 100.5, 101.5, 100.5, 101.25).put("2019-01-08 04:45", 101.25, 101.375,
                                                                             100.625, 100.75)
    assert one(ch.run(setups=("AS",))).bar == ch.ix("2019-01-08 04:45")
    ch = tuesday().put("2019-01-08 04:30", 100.5, 101.5, 100.5, 101.25).put("2019-01-08 04:45", 101.25, 101.375,
                                                                             101.125, 101.25)
    ch.put("2019-01-08 05:00", 101.25, 101.375, 100.625, 100.75)
    assert ch.run(setups=("AS",)).empty                  # a strict "< 300" would also drop 04:45; open-time keeps it
    # the same for LS at 10:45 / 11:00
    ch = london_long(tuesday())
    assert one(ch.run(setups=("LS",))).bar == ch.ix("2019-01-08 10:45")
    ch = tuesday().put("2019-01-08 10:30", 100.0, 100.25, 98.75, 99.25).put("2019-01-08 10:45", 99.25, 99.375, 99.0,
                                                                             99.25)
    ch.put("2019-01-08 11:00", 99.25, 99.875, 99.0, 99.75)
    assert ch.run(setups=("LS",)).empty
    # 1H: Asia is the 20:00-23:00 bars, London the 02:00, 03:00 and 04:00 bars (04:00 + 60 <= 300)
    h1 = Chart(60).flat("2019-01-07 00:00", "2019-01-08 20:00")
    h1.put("2019-01-07 21:00", 100.0, 101.0, 99.5, 100.0).put("2019-01-07 22:00", 100.0, 100.5, 99.0, 100.0)
    h1.put("2019-01-08 04:00", 100.0, 101.5, 100.0, 100.75)
    ck = SH.clock(h1.arrays()[0], 60)
    lon = [str(pd.Timestamp(int(x), unit="s", tz="UTC").tz_convert(NYZ).time())[:5]
           for x in h1.arrays()[0][ck["in_lon"]]]
    assert lon == ["02:00", "03:00", "04:00"] * 2
    assert one(h1.run(setups=("AS",))).bar == h1.ix("2019-01-08 04:00")
    # 4H (EDT: bars open 20:00, 00:00, 04:00, ... New York): the 20:00 bar is Asia (1200 + 240 <= 1440), but the 04:00
    # bar ends at 08:00 and is not in London: no AS. An open-time reading would take the 04:00 bar.
    h4 = Chart(240).flat("2019-07-08 00:00", "2019-07-10 00:00")
    h4.put("2019-07-08 20:00", 100.0, 101.0, 99.0, 100.0).put("2019-07-09 04:00", 100.0, 101.5, 100.0, 100.75)
    ck = SH.clock(h4.arrays()[0], 240)
    assert ck["in_asia"][h4.ix("2019-07-08 20:00")] and not ck["in_lon"].any() and not ck["win_AS"].any()
    assert h4.state().asia_done[h4.ix("2019-07-09 04:00")] and h4.state().lon_hi.isna().all()
    assert h4.run(setups=("AS",)).empty
    # the sessions use the same rule: on a 4H chart in EST (bars open 03:00, 07:00, ...) the 03:00 bar opens inside
    # London but ends at 07:00, so there is no London range and no LS, though the 07:00 bar (07:00-11:00) is inside the
    # LS window and sweeps the 03:00 bar's high, closing back inside its range
    h4 = Chart(240).flat("2019-01-07 03:00", "2019-01-09 03:00")
    h4.put("2019-01-08 07:00", 100.0, 101.0, 99.75, 100.25)
    ck = SH.clock(h4.arrays()[0], 240)
    assert ck["win_LS"][h4.ix("2019-01-08 07:00")] and not ck["in_lon"].any()
    assert h4.state().lon_hi.isna().all() and h4.run(setups=("LS",)).empty
    # M5: the opening range is the 09:30-09:55 bars; the 10:00 bar is outside it
    m5 = tuesday(tf=5).put("2019-01-08 09:55", 100.0, 100.875, 99.5, 100.0).put("2019-01-08 10:00", 100.0, 101.5,
                                                                                99.5, 100.0)
    st = m5.state()
    j = m5.ix("2019-01-08 10:00")
    assert (st.or_hi[j], st.or_lo[j], bool(st.or_done[j]), bool(st.or_done[j - 1])) == (100.875, 99.5, True, False)


def test_trap04_sweep_state_machine_later_bar_failed_confirmation_does_not_end_it_and_dead():
    # the map's tests 3 and 4: the 02:15 wick fails the FVG, the setup lives on, the 02:45 FVG close inside shorts
    ch = asia_short(tuesday())
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert (r.bar, r.dir, r.stop, r.tgt_ref, r.r_hi, r.r_lo) == (ch.ix("2019-01-08 02:45"), -1, 101.75, 99.0, 101.0,
                                                                 99.0)
    assert r.t_signal == ny("2019-01-08 03:00") and r.entry_bar == ch.ix("2019-01-08 03:00") and r.cancelled is None
    # without the confirmation the 02:15 bar itself signals (the sweep and the close inside on one bar)
    assert one(ch.run(setups=("AS",))).bar == ch.ix("2019-01-08 02:15")
    # the map's test 5: the low swept at 02:30 after the high at 02:15 makes the setup dead: no short at 02:45
    ch = asia_short(tuesday()).put("2019-01-08 02:30", 100.75, 100.875, 98.875, 100.5)
    assert ch.run(setups=("AS",), conf=("FVG",)).empty
    # both sides on one bar: dead at once, even with no confirmation needed
    ch = tuesday().put("2019-01-08 02:15", 100.625, 101.75, 98.875, 100.75)
    assert ch.run(setups=("AS",)).empty
    # a price already beyond the level when the window opens counts as a sweep from the first window bar; a sweep
    # before the window does not (the 01:30 high alone gives no setup)
    ch = tuesday().put("2019-01-08 01:30", 100.0, 103.0, 99.5, 100.0)
    assert ch.run(setups=("AS",)).empty
    ch = tuesday().put("2019-01-08 01:45", 100.0, 101.5, 100.0, 101.25).put("2019-01-08 02:00", 101.25, 101.375,
                                                                             100.75, 100.875)
    assert one(ch.run(setups=("AS",))).bar == ch.ix("2019-01-08 02:00")


def test_trap05_the_stop_extreme_accumulates_over_window_bars_only():
    # 01:30 prints 103 above the Asia high before the window; 02:00 sweeps to 101.75 (closing above), 02:15 to 101.5
    # and closes inside: the stop is 101.75 (the window's extreme), not 103 (since the range was final) nor 101.5
    # (the signal bar's high); a later 102.5 does not move it
    ch = tuesday().put("2019-01-08 01:30", 100.0, 103.0, 99.5, 100.0)
    ch.put("2019-01-08 01:45", 100.0, 101.5, 100.0, 101.25).put("2019-01-08 02:00", 101.25, 101.75, 101.125, 101.25)
    ch.put("2019-01-08 02:15", 101.25, 101.5, 100.5, 100.625).put("2019-01-08 02:30", 100.625, 102.5, 100.5, 100.75)
    r = one(ch.run(setups=("AS",)))
    i = ch.ix("2019-01-08 02:15")
    assert abs(100.625 - 101.75) >= 0.5 * ch.atr()[i]           # the minimum-stop rule does not apply here
    assert (r.bar, r.dir, r.stop) == (i, -1, 101.75)
    # the long mirror: the lowest low below the Asia low over the window bars
    ch = tuesday().put("2019-01-08 01:30", 100.0, 100.5, 97.0, 100.0)
    ch.put("2019-01-08 02:00", 99.0, 99.125, 98.25, 98.75).put("2019-01-08 02:15", 98.75, 99.5, 98.5, 99.375)
    r = one(ch.run(setups=("AS",)))
    assert (r.bar, r.dir, r.stop, r.tgt_ref) == (ch.ix("2019-01-08 02:15"), 1, 98.25, 101.0)


def test_trap06_the_minimum_stop_is_measured_from_the_signal_close():
    # the map's test 6: the sweep extreme 101.25 is 0.30 (about 0.3 ATR) above the 02:00 close 100.95: the stop moves
    # to close + 0.5 ATR of the signal bar, not to the 02:15 entry open + 0.5 ATR, not left at 101.25
    ch = tuesday().put("2019-01-08 02:00", 100.875, 101.25, 100.875, 100.9375)
    ch.put("2019-01-08 02:15", 100.75, 101.0, 100.5, 100.75)
    i = ch.ix("2019-01-08 02:00")
    a = ch.atr()[i]
    assert 0.25 < 0.3125 / a < 0.35                              # 0.3 ATR
    r = one(ch.run(setups=("AS",)))
    assert r.bar == i and r.stop == 100.9375 - (-1 * 0.5) * a and r.stop != 100.75 + 0.5 * a
    # an extreme 0.6 ATR away stays
    ch = tuesday().put("2019-01-08 02:00", 100.875, 101.5625, 100.875, 100.9375)
    assert one(ch.run(setups=("AS",))).stop == 101.5625
    # a breakout's midpoint stop: a narrow Asia range 99.875..100.125, a close at 100.25 is 0.25 from the midpoint 100
    ch = Chart(15).flat("2019-01-07 12:00", "2019-01-07 20:00").flat("2019-01-07 20:00", "2019-01-08 00:00",
                                                                      half=0.125)
    ch.flat("2019-01-08 00:00", "2019-01-08 20:00").put("2019-01-08 02:00", 100.0, 100.375, 100.0, 100.25)
    i = ch.ix("2019-01-08 02:00")
    r = one(ch.run(setups=("AB",)))
    assert (r.bar, r.dir, r.r_hi, r.r_lo) == (i, 1, 100.125, 99.875)
    assert r.stop == 100.25 - (1 * 0.5) * ch.atr()[i] and r.tgt_ref == 100.125 + 1 * 0.25
    # min_stop_atr = 0.1 (the input's minval, l.81; 0 is refused) keeps the midpoint, 0.25 > 0.1 ATR away
    assert 0.1 * ch.atr()[i] < 0.25 and one(ch.run(setups=("AB",), min_stop_atr=0.1)).stop == 100.0


def test_trap07_the_cancels_at_entry():
    # the map's test 7. The short of test 4 (stop 101.75): the 03:00 bar opening beyond the stop / at it
    ch = asia_short(tuesday()).put("2019-01-08 03:00", 102.0, 102.25, 101.5, 102.0)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert r.cancelled == "open_beyond_stop"
    for m in SH.MODES:
        assert r[f"exit_reason_{m}"] is None and r[f"exit_bar_{m}"] == -1
        assert np.isnan(r[f"exit_price_{m}"]) and np.isnan(r[f"R_{m}"])
    ch = asia_short(tuesday()).put("2019-01-08 03:00", 101.75, 102.0, 101.5, 101.75)
    assert one(ch.run(setups=("AS",), conf=("FVG",))).cancelled == "risk<=0"
    # the LS long at 10:45 whose next bar is the 16:00 bar (a hole from 11:00), the 20:00 bar (a new day), or gold's
    # Sunday 18:00 reopen after a Friday signal (closeT and a new day: closeT is named first, l.428)
    ch = london_long(tuesday()).drop("2019-01-08 11:00", "2019-01-08 16:00")
    r = one(ch.run(setups=("LS",)))
    assert r.entry_bar == ch.ix("2019-01-08 16:00") and r.cancelled == "closeT"
    ch = london_long(tuesday(end="2019-01-08 23:00")).drop("2019-01-08 11:00", "2019-01-08 20:00")
    assert one(ch.run(setups=("LS",))).cancelled == "new_day"
    fri = Chart(15).flat("2019-01-10 12:00", "2019-01-11 11:00").flat("2019-01-13 18:00", "2019-01-13 20:00")
    london_long(fri, "2019-01-11")
    r = one(fri.run(setups=("LS",)))
    assert r.entry_bar == fri.ix("2019-01-13 18:00") and r.cancelled == "closeT"
    # a normal entry is not cancelled, and nothing is decided before the entry bar exists
    assert one(london_long(tuesday()).run(setups=("LS",))).cancelled is None
    ch = london_long(Chart(15).flat("2019-01-07 12:00", "2019-01-08 10:30"))
    r = one(ch.run(setups=("LS",)))
    assert r.entry_bar == len(ch.rows) and r.cancelled is None
    assert all(r[f"exit_reason_{m}"] == "pending" for m in SH.MODES)


def test_trap08_r_is_measured_from_the_bid_open_of_the_entry_bar():
    # the short of test 4: signal close 100.125, entry open 100.25 (bar 03:00), stop 101.75: risk 1.5. Held to the
    # 16:00 open 99.5: R = (100.25 - 99.5) / 1.5 = 0.5 exactly (from the signal close it would be 0.625 / 1.625)
    ch = asia_short(tuesday()).put("2019-01-08 16:00", 99.5, 100.0, 99.25, 99.75)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    j = ch.ix("2019-01-08 16:00")
    assert (r.exit_bar_hold, r.exit_price_hold, r.exit_reason_hold, r.R_hold) == (j, 99.5, "closeT", 0.5)
    # TP2 = 100.25 - 2 * 1.5 = 97.25 is not reached: the same exit
    assert (r.exit_bar_tp2, r.exit_reason_tp2, r.R_tp2) == (j, "closeT", 0.5)
    # the map's test 9: the opposite liquidity (the Asia low 99) is 1.25 < 1R from the open: E3 only is cancelled
    assert (r.exit_reason_liq, r.exit_bar_liq) == ("cancel_lt_1R", -1) and np.isnan(r.R_liq)
    # TP2 reached at 10:00: exactly +2R at 97.25
    ch.put("2019-01-08 10:00", 100.0, 100.5, 97.0, 97.5)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert (r.exit_bar_tp2, r.exit_price_tp2, r.exit_reason_tp2, r.R_tp2) == (ch.ix("2019-01-08 10:00"), 97.25,
                                                                              "target", 2.0)
    assert (r.exit_reason_hold, r.R_hold) == ("closeT", 0.5)


def test_trap09_the_order_of_the_exit_checks():
    # the map's test 8: the 16:00 bar exits at its open (99.5, +0.5R) though it later touches the stop 101.75
    ch = asia_short(tuesday()).put("2019-01-08 16:00", 99.5, 102.0, 99.25, 100.0)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert (r.exit_reason_hold, r.exit_price_hold, r.R_hold) == ("closeT", 99.5, 0.5)
    # one bar touching the stop and TP2 (97.25): the stop
    ch = asia_short(tuesday()).put("2019-01-08 10:00", 100.0, 101.875, 97.0, 100.0)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    j = ch.ix("2019-01-08 10:00")
    assert (r.exit_bar_tp2, r.exit_price_tp2, r.exit_reason_tp2, r.R_tp2) == (j, 101.75, "stop", -1.0)
    assert (r.exit_bar_hold, r.exit_reason_hold, r.R_hold) == (j, "stop", -1.0)
    # the entry bar is checked for the stop and the target (not for the time exits)
    ch = asia_short(tuesday()).put("2019-01-08 03:00", 100.25, 101.875, 99.75, 100.0)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert (r.exit_bar_hold, r.exit_reason_hold, r.R_hold) == (r.entry_bar, "stop", -1.0)
    ch = asia_short(tuesday()).put("2019-01-08 03:00", 100.25, 100.5, 97.0, 98.0)
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert (r.exit_bar_tp2, r.exit_reason_tp2, r.R_tp2) == (r.entry_bar, "target", 2.0)
    # a new day is checked before closeT: a Friday short still open when gold reopens on Sunday 18:00 (both a new day
    # and closeT) exits at Friday 15:45's close (99.75), booked on the Sunday bar, not at the Sunday open (99)
    fri = Chart(15).flat("2019-01-10 12:00", "2019-01-11 16:00").flat("2019-01-13 18:00", "2019-01-13 19:00")
    fri.put("2019-01-10 21:00", 100.0, 101.0, 99.5, 100.0).put("2019-01-10 22:00", 100.0, 100.5, 99.0, 100.0)
    asia_short(fri, "2019-01-11").put("2019-01-11 15:45", 100.0, 100.5, 99.5, 99.75)
    fri.put("2019-01-13 18:00", 99.0, 99.5, 98.5, 99.25)
    r = one(fri.run(setups=("AS",), conf=("FVG",)))
    assert (r.exit_bar_hold, r.exit_price_hold, r.exit_reason_hold) == (fri.ix("2019-01-13 18:00"), 99.75, "new_day")
    assert r.R_hold == (-1 * (99.75 - 100.25) - 2 * 0.0) / 1.5


def test_trap10_the_htf_value_is_taken_at_the_chart_bars_open():
    # 1H closes 99, 99.5, 99.75, 100.25 (bars opening 07:00-10:00) with a 3-bar EMA (alpha 1/2): 99, 99.25, 99.5,
    # 99.875. The map's test 11: the M15 bar opening 10:45 reads the EMA as of 10:00 (the 09:00 bar's 99.5), the 11:00
    # bar the EMA as of 11:00 (99.875). The close reading would give 99.875 at 10:45.
    h1 = SimpleNamespace(tc=np.array([ny(f"2019-01-08 {x}:00") for x in ("08", "09", "10", "11")]),
                         c=np.array([99.0, 99.5, 99.75, 100.25]))
    t = np.array([ny(f"2019-01-08 {x}") for x in ("07:45", "08:00", "09:45", "10:00", "10:45", "11:00")])
    c = np.array([99.125, 99.125, 99.375, 99.625, 99.75, 99.75])
    d = SH.htf_ema_dir(t, c, h1, length=3)
    assert d.tolist() == [0, 1, 1, 1, 1, -1]        # na before 08:00; vs 99, 99.25, 99.5, 99.5, 99.875
    assert SH.htf_ema_dir(t, np.array([99.0, 99.0, 99.25, 99.5, 99.5, 99.875]), h1, length=3).tolist() == [0] * 6
    # on a 1H chart the bar opening 10:00 reads the previous 1H bar's EMA (99.5)
    assert SH.htf_ema_dir(np.array([ny("2019-01-08 10:00")]), np.array([99.625]), h1, length=3).tolist() == [1]
    # the default length 200 is ta.ema(close, 200) of study 1 (seeded with the first close)
    e = I.ema(h1.c, 200)
    assert SH.htf_ema_dir(t, c, h1).tolist() == [0] + [int(np.sign(c[k] - e[j])) for k, j in
                                                        ((1, 0), (2, 1), (3, 2), (4, 2), (5, 3))]
    # in the setup: the LS long at 10:45 (close 99.75) passes the HTF test with the open reading
    ch = london_long(tuesday())
    tt = ch.arrays()[0]
    hd = SH.htf_ema_dir(tt, ch.arrays()[4], h1, length=3)
    assert hd[ch.ix("2019-01-08 10:45")] == 1
    assert one(ch.run(setups=("LS",), conf=("HTF",), htf=hd)).bar == ch.ix("2019-01-08 10:45")
    wrong = X.value_at(h1.tc, I.ema(h1.c, 3), tt + 900, np.nan)        # the htf_at (close) reading
    assert np.sign(99.75 - wrong[ch.ix("2019-01-08 10:45")]) == -1
    assert ch.run(setups=("LS",), conf=("HTF",), htf=np.sign(ch.arrays()[4] - wrong)).empty


def test_trap11_fvg_offsets_and_the_one_bar_shift_of_hi5_lo5():
    # the map's test 12: bar 5 has a gap only through low[3] > high[5] (offset 3); bar 6's would be offset 4: none
    h = np.array([10.0, 13, 13, 13, 13, 13, 13])
    lo = np.array([9.0, 9, 11, 9, 9, 9, 9])
    up, dn = SH.fvg(h, lo)
    assert up.tolist() == [False, False, True, True, True, True, False] and not dn.any()
    up, dn = SH.fvg(-lo, -h)                                  # the mirror: high[3] < low[5]
    assert dn.tolist() == [False, False, True, True, True, True, False] and not up.any()
    # hi5 = max(high[1..5]): na on bars 0-4, the current bar excluded, the 6th bar back excluded
    hh = np.array([1.0, 2, 3, 4, 5, 6, 0.5, 0.5])
    hi, lo5 = SH.hi5_lo5(hh, -hh)
    assert np.isnan(hi[:5]).all() and hi[5:].tolist() == [5.0, 6.0, 6.0] and (lo5[5:] == -hi[5:]).all()
    # MSS in a fade: after the 02:00 low sweep, the 02:15 close 100.625 is above the 5 highs before it (100.5) though
    # below its own high (100.75): a long. A 100.75 high six bars back (00:45) is outside the window; five back
    # (01:00) it blocks the long, and no later bar qualifies.
    base = tuesday().put("2019-01-08 02:00", 100.0, 100.25, 98.5, 98.75)
    base.put("2019-01-08 02:15", 98.75, 100.75, 98.75, 100.625)
    ch = Chart(15)
    ch.rows = dict(base.rows)
    ch.put("2019-01-08 00:45", 100.0, 100.75, 99.5, 100.0)
    r = one(ch.run(setups=("AS",), conf=("MSS",)))
    assert (r.bar, r.dir) == (ch.ix("2019-01-08 02:15"), 1)
    ch.put("2019-01-08 01:00", 100.0, 100.75, 99.5, 100.0)
    assert ch.run(setups=("AS",), conf=("MSS",)).empty
    # FVG in a fade: the long needs fvgUp; the same bars without the gap give nothing with ('FVG',)
    assert base.run(setups=("AS",), conf=("FVG",)).empty
    base.put("2019-01-08 02:30", 100.875, 101.0, 100.875, 100.875)     # low 100.875 > high[2] 100.25 (02:00): a gap
    r = one(base.run(setups=("AS",), conf=("FVG",)))
    assert (r.bar, r.dir) == (base.ix("2019-01-08 02:30"), 1)


def test_trap12_the_fill_beyond_stop_trap():
    # PREREG 4 / the map's 0.4: an entry whose open is at or beyond its absolute stop is dropped, so no row ever books
    # the fake profit of a stop already crossed. The LS long (stop 98.75) whose next open gaps to 98.5:
    ch = london_long(tuesday()).put("2019-01-08 11:00", 98.5, 99.0, 98.25, 98.75)
    r = one(ch.run(setups=("LS",)))
    assert r.cancelled == "open_beyond_stop" and r.stop == 98.75 and all(np.isnan(r[f"R_{m}"]) for m in SH.MODES)
    # a later gap through the stop fills at the stop in the script's own exits (its optimism): exactly -1R; the
    # study's execution re-measures the level from its fill and charges the gap (PREREG 4)
    ch = london_long(tuesday()).put("2019-01-08 11:00", 99.75, 100.0, 99.5, 99.75)
    ch.put("2019-01-08 12:00", 98.0, 98.5, 97.75, 98.25)
    r = one(ch.run(setups=("LS",)))
    assert (r.cancelled, r.exit_bar_hold, r.exit_price_hold, r.R_hold) == (None, ch.ix("2019-01-08 12:00"), 98.75, -1.0)
    # on random bars: every entered trade opened on the right side of its stop, every stop exit is exactly -1R
    for seed in (5, 6):
        t, o, h, lo, c, v, hd = random_bars(seed, tf=15, gold=True)
        df = SH.session_hunter(t, o, h, lo, c, v, 15, hd, conf=())
        ent = df[df.cancelled.isna() & (df.entry_bar < len(t))]
        assert len(ent) > 50
        assert (ent.dir * (o[ent.entry_bar.to_numpy()] - ent.stop) > 0).all()
        for m in SH.MODES:
            s = df[df[f"exit_reason_{m}"] == "stop"]
            assert len(s) > 10 and (s[f"R_{m}"] == -1.0).all() and (s[f"exit_price_{m}"] == s.stop).all()


def five_lanes():
    """Sunday 18:00 to Tuesday 20:00; Monday's day spans 98.75..101.25 (pdh / pdl for Tuesday), Tuesday's Asia 99..101.
    Tuesday: 02:00 closes above the Asia high (AB long) after sweeping pdh; 02:15 closes back inside both ranges (AS
    and PD shorts); London is then 99.5..101.5; 08:00 sweeps its low to 99, 08:15 closes inside (LS long); the opening
    range is 99.5..100.5 and 10:00 closes above it (OR long; the 10:15 entry opens at 100.625, above its midpoint
    stop 100: a flat bar opening at 100 would drop it as 'risk<=0')."""
    ch = Chart(15).flat("2019-01-06 18:00", "2019-01-08 20:00")
    ch.put("2019-01-07 12:00", 100.0, 101.25, 99.5, 100.0).put("2019-01-07 13:00", 100.0, 100.5, 98.75, 100.0)
    ch.put("2019-01-07 21:00", 100.0, 101.0, 99.5, 100.0).put("2019-01-07 22:00", 100.0, 100.5, 99.0, 100.0)
    ch.put("2019-01-08 02:00", 100.0, 101.5, 100.0, 101.375).put("2019-01-08 02:15", 101.375, 101.375, 100.625,
                                                                  100.75)
    ch.put("2019-01-08 08:00", 100.0, 100.5, 99.0, 99.375).put("2019-01-08 08:15", 99.375, 99.875, 99.25, 99.75)
    ch.put("2019-01-08 10:00", 100.0, 100.75, 99.875, 100.625).put("2019-01-08 10:15", 100.625, 100.75, 100.5,
                                                                      100.625)
    return ch


def test_trap13_five_lanes():
    ch = five_lanes()
    df = ch.run()
    want = [("AB", "02:00", 1, 100.0, 101.0, 99.0, 103.0), ("AS", "02:15", -1, 101.5, 101.0, 99.0, 99.0),
            ("PD", "02:15", -1, 101.5, 101.25, 98.75, 98.75), ("LS", "08:15", 1, 99.0, 101.5, 99.5, 101.5),
            ("OR", "10:00", 1, 100.0, 100.5, 99.5, 101.5)]
    got = [(r.setup, r.bar, r.dir, r.stop, r.r_hi, r.r_lo, r.tgt_ref) for r in df.itertuples()]
    assert got == [(s, ch.ix(f"2019-01-08 {w}"), d, st, hi, lo, ref) for s, w, d, st, hi, lo, ref in want]
    # the lanes are independent: each setup alone gives its own row unchanged
    for s in SH.SETUPS:
        alone = ch.run(setups=(s,))
        assert alone.equals(df[df.setup == s].reset_index(drop=True)), s
    assert ch.run(setups=("PD", "OR")).equals(df[df.setup.isin(["PD", "OR"])].reset_index(drop=True))
    # all five are entered; overlapping trades: AS, PD and LS are all held from 08:30 to the 16:00 open
    assert df.cancelled.isna().all()
    live = df[df.setup.isin(["AS", "PD", "LS"])]
    assert (live.exit_reason_hold == "closeT").all() and (live.exit_bar_hold == ch.ix("2019-01-08 16:00")).all()
    # one trade per setup and day: a second clean sweep of the Asia high at 03:00 adds nothing
    ch.put("2019-01-08 03:00", 100.0, 101.5, 100.0, 100.5)
    assert ch.run().setup.tolist() == df.setup.tolist()


# ───────────────────────────── the map's other numbered tests ─────────────────────────────

def test_spec09_an_opposite_liquidity_target_at_least_1r_away_is_traded():
    ch = tuesday().put("2019-01-08 02:15", 100.625, 101.5, 100.5, 100.5).put("2019-01-08 02:30", 100.5, 100.75,
                                                                            100.25, 100.5)
    ch.put("2019-01-08 04:00", 100.0, 100.5, 98.75, 99.25)
    r = one(ch.run(setups=("AS",)))
    assert (r.stop, r.tgt_ref, r.entry_bar) == (101.5, 99.0, ch.ix("2019-01-08 02:30"))         # risk 1.0, 1.5R away
    assert (r.exit_bar_liq, r.exit_price_liq, r.exit_reason_liq, r.R_liq) == (ch.ix("2019-01-08 04:00"), 99.0,
                                                                              "target", 1.5)
    assert (r.exit_reason_hold, r.exit_reason_tp2) == ("closeT", "closeT")      # TP2 = 98.5 is not reached


def test_spec10_an_asia_breakout_beyond_4_atr_ends_the_setup_without_a_trade():
    ch = tuesday().put("2019-01-08 02:00", 100.0, 106.25, 100.0, 106.0).put("2019-01-08 02:15", 106.0, 106.0, 100.75,
                                                                             101.5)
    i = ch.ix("2019-01-08 02:00")
    assert abs(106.0 - 100.0) > 4 * ch.atr()[i]
    assert ch.run(setups=("AB",)).empty                    # done at 02:00: the 02:15 close at 101.5 is not taken
    ch = tuesday().put("2019-01-08 02:15", 100.0, 101.75, 100.0, 101.5)
    assert one(ch.run(setups=("AB",))).bar == ch.ix("2019-01-08 02:15")
    # a close outside that fails the confirmations does not end the day
    ch = tuesday().put("2019-01-08 02:00", 100.0, 101.75, 100.0, 101.5).put("2019-01-08 02:15", 101.5, 102.0, 101.5,
                                                                             101.875)
    r = one(ch.run(setups=("AB",), conf=("FVG",)))          # 02:15: low 101.5 > high[2] 100.5 (01:45): a gap
    assert (r.bar, r.dir, r.stop) == (ch.ix("2019-01-08 02:15"), 1, 100.0)


def test_spec13_the_opening_range_setup_is_off_on_1h():
    m15 = tuesday().put("2019-01-08 10:00", 100.0, 101.0, 99.875, 100.875)
    assert one(m15.run(setups=("OR",))).bar == m15.ix("2019-01-08 10:00")
    t, o, h, lo, c, v = m15.arrays()
    hour = t // 3600
    first = np.flatnonzero(np.diff(hour, prepend=hour[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(t) - 1)
    h1 = (t[first], o[first], np.maximum.reduceat(h, first), np.minimum.reduceat(lo, first), c[last],
          np.add.reduceat(v, first))
    ck = SH.clock(h1[0], 60)
    assert not ck["in_or"].any() and not ck["win_OR"].any()
    assert SH.session_hunter(*h1, 60, np.zeros(len(first)), setups=("OR",), conf=()).empty


def test_the_other_confirmations_pd_rv_tight_yc():
    # premium / discount: the 02:45 short of test 4 closes at 100.125, above the midnight open 100 (sell above): passes;
    # with a 00:00 open of 100.25 it does not
    ch = asia_short(tuesday())
    assert one(ch.run(setups=("AS",), conf=("FVG", "PD"))).bar == ch.ix("2019-01-08 02:45")
    assert ch.state().mo[ch.ix("2019-01-08 02:45")] == 100.0
    ch.put("2019-01-08 00:00", 100.25, 100.5, 99.5, 100.0)
    assert ch.run(setups=("AS",), conf=("FVG", "PD")).empty
    # relative volume: volume >= 1.5 x SMA(20) of the volume, the signal bar included (19 x 100 and 160: 154.5)
    ch = asia_short(tuesday())
    ch.rows[ny("2019-01-08 02:45")] = ch.rows[ny("2019-01-08 02:45")][:4] + (160.0,)
    assert one(ch.run(setups=("AS",), conf=("FVG", "RV"))).bar == ch.ix("2019-01-08 02:45")
    ch.rows[ny("2019-01-08 02:45")] = ch.rows[ny("2019-01-08 02:45")][:4] + (150.0,)     # 150 < 153.75
    assert ch.run(setups=("AS",), conf=("FVG", "RV")).empty
    with pytest.raises(ValueError, match="volume"):
        t, o, h, lo, c, _ = ch.arrays()
        SH.session_hunter(t, o, h, lo, c, None, 15, None, conf=("RV",))
    # tight range: five weekdays (Monday 7 to Friday 11 January) of range 4.0 each give adr = 4.0 on Monday 14; an
    # Asia range of 2.0 is not < 0.5 x 4.0 (strict), one of 1.875 is
    tight = Chart(15).flat("2019-01-06 18:00", "2019-01-14 12:00")
    for day in ("07", "08", "09", "10", "11"):
        tight.put(f"2019-01-{day} 12:00", 100.0, 102.0, 99.5, 100.0).put(f"2019-01-{day} 13:00", 100.0, 100.5,
                                                                          98.0, 100.0)
    tight.put("2019-01-13 21:00", 100.0, 101.0, 99.5, 100.0).put("2019-01-13 22:00", 100.0, 100.5, 99.0, 100.0)
    asia_short(tight, "2019-01-14")
    st = tight.state()
    assert st.adr[tight.ix("2019-01-14 02:45")] == 4.0 and np.isnan(st.adr[tight.ix("2019-01-10 12:00")])
    assert tight.run(setups=("AS",), conf=("FVG", "TIGHT")).empty
    tight.put("2019-01-13 22:00", 100.0, 100.5, 99.125, 100.0)
    assert one(tight.run(setups=("AS",), conf=("FVG", "TIGHT"))).r_lo == 99.125
    # yesterday's candle: Monday's day opens at 100 (Sunday 20:00) and closes at 99.75 (19:45): shorts pass, longs not
    ch = asia_short(tuesday(start="2019-01-06 18:00")).put("2019-01-07 19:45", 100.0, 100.5, 99.5, 99.75)
    assert one(ch.run(setups=("AS",), conf=("FVG", "YC"))).dir == -1
    ch.put("2019-01-07 19:45", 100.0, 100.5, 99.5, 100.25)
    assert ch.run(setups=("AS",), conf=("FVG", "YC")).empty
    # the first, partial day of the data has no levels (reading 1: newDay is false on bar 0): no YC on Tuesday when
    # the data start on Monday 12:00
    ch = asia_short(tuesday()).put("2019-01-07 19:45", 100.0, 100.5, 99.5, 99.75)
    assert np.isnan(ch.state().pdh[ch.ix("2019-01-08 02:45")]) and ch.run(setups=("AS",), conf=("YC",)).empty


def test_inputs_are_checked():
    ch = asia_short(tuesday())
    t, o, h, lo, c, v = ch.arrays()
    z = np.zeros(len(t))
    with pytest.raises(ValueError):
        SH.session_hunter(t[::-1], o, h, lo, c, v, 15, z)
    with pytest.raises(ValueError):
        SH.session_hunter(t, o[:-1], h, lo, c, v, 15, z)
    with pytest.raises(ValueError):
        SH.session_hunter(t, o, h, lo, c, v, 15, z, setups=("XX",))
    with pytest.raises(ValueError):
        SH.session_hunter(t, o, h, lo, c, v, 15, z, conf="FVG")
    with pytest.raises(ValueError):
        SH.session_hunter(t, o, h, lo, c, v, 15, None, conf=("HTF",))
    with pytest.raises(ValueError):
        SH.session_hunter(t, o, h, lo, c, v, 0, z)
    for bad in (-1, 0.0, math.inf, math.nan):                   # the reconciled contract: a finite number > 0
        with pytest.raises(ValueError):
            SH.session_hunter(t, o, h, lo, c, v, 15, z, min_stop_atr=bad)
    with pytest.raises(ValueError):
        SH.session_hunter(t, o, h, lo, c, v, 15, z, setups="AS")
    with pytest.raises(ValueError):
        SH.session_hunter(t, np.where(np.arange(len(o)) == 3, np.nan, o), h, lo, c, v, 15, z)
    keep = [x.copy() for x in (o, h, lo, c, v)]
    SH.session_hunter(t, o, h, lo, c, v, 15, z)
    assert all(np.array_equal(a, b) for a, b in zip(keep, (o, h, lo, c, v)))
    e = SH.session_hunter(t[:3], o[:3], h[:3], lo[:3], c[:3], v[:3], 15, z[:3])
    assert e.empty and list(e.columns) == SH.COLUMNS and e.bar.dtype == np.int64
    df = SH.session_hunter(t, o, h, lo, c, v, 15, z, conf=())
    assert list(df.columns) == SH.COLUMNS
    assert {k: str(df[k].dtype) for k in ("bar", "t_signal", "dir", "entry_bar", "stop", "exit_bar_hold", "R_tp2")} \
        == {"bar": "int64", "t_signal": "int64", "dir": "int64", "entry_bar": "int64", "stop": "float64",
            "exit_bar_hold": "int64", "R_tp2": "float64"}


# ───────────────────────────── 3. the kernel against a plain-Python transcription ─────────────────────────────

class _St:
    """``type St`` (l.176-182)."""

    def __init__(self):
        self.sH = False
        self.sL = False
        self.upEx = nan
        self.dnEx = nan
        self.done = False
        self.dead = False


class _Trade:
    """``type Trade`` (l.367-388), the fields the manager reads."""

    def __init__(self, d, nm, stop, tgtRef, sb, key):
        self.d, self.nm, self.stop, self.tgtRef, self.sb, self.key = d, nm, stop, tgtRef, sb, key
        self.e = nan
        self.tgt = nan
        self.risk = nan
        self.live = False
        self.x0 = -1


def pine_ref(t, o, h, l, c, v, tf, hdir, setups=SH.SETUPS, conf=("FVG", "HTF"), mfl=False, min_stop=0.5):
    """
    The script's l.127-492 bar by bar, statement by statement, in plain Python: Pine's ``var`` state as locals that
    survive the bar loop, ``St`` and ``Trade`` as objects, ``open_`` as a list iterated backwards with ``del`` (one
    list per exit mode, which the script would hold in three runs). The clock comes from ``zoneinfo``, the day key as
    l.130 writes it (year * 10000 + month * 100 + day). ``hdir`` stands for htfE through ``sign(close - htfE)``.
    Returns (signals, results): signals = [(setup, bar, dir, stop, tgtRef, rH, rL)] in the order f_new is called;
    results[mode][k] = (cancelled, exit_bar, exit_price, exit_reason, R) of signal k.
    """
    n = len(t)
    t = [int(x) for x in t]
    o, h, l, c, v = (np.asarray(x, np.float64).tolist() for x in (o, h, l, c, v))
    hd = [0 if x != x else (1 if x > 0 else (-1 if x < 0 else 0)) for x in np.asarray(hdir, np.float64)]
    loc = [datetime.fromtimestamp(x, NYZ) for x in t]
    loc4 = [datetime.fromtimestamp(x + 4 * 3600, NYZ) for x in t]
    nyMin = [d.hour * 60 + d.minute for d in loc]                                  # l.128
    dk = [d.year * 10000 + d.month * 100 + d.day for d in loc4]                    # l.129-130
    weekday = [d.isoweekday() <= 5 for d in loc4]                                  # l.131-132
    atr = I.atr(h, l, c, 14).tolist()                                              # l.143
    vAvg = I.sma(v, 20).tolist()                                                   # l.144
    tfMin = tf
    na = math.isnan

    def pmax(a, b):
        return nan if (na(a) or na(b)) else max(a, b)

    def pmin(a, b):
        return nan if (na(a) or na(b)) else min(a, b)

    dH = dL = dO = pdh = pdl = pO = pC = mo = nan
    pWk = False
    asH = asL = loH = loL = oH = oL = nan
    asDone = loDone = oDone = False
    ranges = []
    dWk = False
    st = {s: _St() for s in SH.SETUPS}
    open_ = {m: [] for m in SH.MODES}
    signals = []
    results = {m: {} for m in SH.MODES}
    inAsia1 = inLon1 = inOR1 = False
    for i in range(n):
        def f_in(s0, s1):                                                          # l.134
            return nyMin[i] >= s0 and nyMin[i] + tfMin <= s1 and nyMin[i] < 1440
        inAsia = nyMin[i] >= 1200 and nyMin[i] + tfMin <= 1440                     # l.135
        inLon = f_in(120, 300)
        inOR = f_in(570, 600) and tfMin < 60
        closeT = nyMin[i] >= 960 and nyMin[i] < 1200
        newDay = i > 0 and dk[i] != dk[i - 1]                                      # l.133, false on bar 0

        def g(x, k):
            return x[i - k] if i - k >= 0 else nan
        fvgUp = g(l, 0) > g(h, 2) or g(l, 1) > g(h, 3) or g(l, 2) > g(h, 4) or g(l, 3) > g(h, 5)
        fvgDn = g(h, 0) < g(l, 2) or g(h, 1) < g(l, 3) or g(h, 2) < g(l, 4) or g(h, 3) < g(l, 5)
        hi5 = max(h[i - 5:i]) if i >= 5 else nan
        lo5 = min(l[i - 5:i]) if i >= 5 else nan
        if newDay:                                                                 # l.190-207
            if not na(dH) and dWk:
                ranges.append(dH - dL)
                if len(ranges) > 10:
                    ranges.pop(0)
            pdh = dH if dWk else pdh
            pdl = dL if dWk else pdl
            pO = dO if dWk else pO
            pC = c[i - 1] if dWk else pC
            pWk = dWk
            dH, dL, dO = h[i], l[i], o[i]
            dWk = weekday[i]
            mo = nan
            asH = asL = loH = loL = oH = oL = nan
            asDone = loDone = oDone = False
            st = {s: _St() for s in SH.SETUPS}
        else:
            dH = pmax(dH, h[i])
            dL = pmin(dL, l[i])
        adr = sum(ranges) / len(ranges) if len(ranges) >= 5 else nan               # l.211
        if na(mo) and nyMin[i] < 1200:
            mo = o[i]
        if inAsia:
            asH = h[i] if na(asH) else max(asH, h[i])
            asL = l[i] if na(asL) else min(asL, l[i])
        if inLon:
            loH = h[i] if na(loH) else max(loH, h[i])
            loL = l[i] if na(loL) else min(loL, l[i])
        if inOR:
            oH = h[i] if na(oH) else max(oH, h[i])
            oL = l[i] if na(oL) else min(oL, l[i])
        if inAsia1 and not inAsia:
            asDone = True
        if inLon1 and not inLon:
            loDone = True
        if inOR1 and not inOR:
            oDone = True
        inAsia1, inLon1, inOR1 = inAsia, inLon, inOR
        pwk = pWk or (mfl and not na(pdh))

        def f_conf(dd, rH, rL):                                                    # l.312-328
            ok = True
            if "FVG" in conf:
                ok = ok and (fvgUp if dd > 0 else fvgDn)
            if "MSS" in conf:
                ok = ok and (c[i] > hi5 if dd > 0 else c[i] < lo5)
            if "HTF" in conf:
                ok = ok and hd[i] != 0 and dd * hd[i] > 0
            if "PD" in conf:
                ok = ok and not na(mo) and dd * (mo - c[i]) > 0
            if "RV" in conf:
                ok = ok and v[i] >= 1.5 * vAvg[i]
            if "TIGHT" in conf:
                ok = ok and not na(adr) and rH - rL < 50 / 100.0 * adr
            if "YC" in conf:
                ok = ok and pwk and dd * (pC - pO) > 0
            return ok

        def f_rev(s, rH, rL, win):                                                 # l.331-347
            sig = 0
            if win and weekday[i] and not s.done and not s.dead and not na(rH) and not na(rL) and rH > rL:
                if h[i] > rH:
                    s.sH = True
                    s.upEx = h[i] if na(s.upEx) else max(s.upEx, h[i])
                if l[i] < rL:
                    s.sL = True
                    s.dnEx = l[i] if na(s.dnEx) else min(s.dnEx, l[i])
                if s.sH and s.sL:
                    s.dead = True
                elif c[i] < rH and c[i] > rL:
                    dd = -1 if s.sH else (1 if s.sL else 0)
                    if dd != 0 and f_conf(dd, rH, rL):
                        sig = dd
                        s.done = True
            return sig

        def f_brk(s, rH, rL, win):                                                 # l.350-358
            sig = 0
            if win and weekday[i] and not s.done and not na(rH) and not na(rL) and rH > rL:
                dd = 1 if c[i] > rH else (-1 if c[i] < rL else 0)
                if dd != 0 and f_conf(dd, rH, rL):
                    s.done = True
                    if abs(c[i] - (rH + rL) / 2) <= 4 * atr[i]:
                        sig = dd
            return sig

        sAS = f_rev(st["AS"], asH if asDone else nan, asL, f_in(120, 300)) if "AS" in setups else 0
        sLS = f_rev(st["LS"], loH if loDone else nan, loL, f_in(420, 660)) if "LS" in setups else 0
        sPD = f_rev(st["PD"], pdh, pdl, f_in(120, 660)) if ("PD" in setups and pwk) else 0
        sAB = f_brk(st["AB"], asH if asDone else nan, asL, f_in(120, 300)) if "AB" in setups else 0
        sOR = f_brk(st["OR"], oH if oDone else nan, oL, f_in(600, 720)) if ("OR" in setups and tfMin < 60) else 0

        def f_new(dd, nm, s, rH, rL, rev):                                         # l.399-404
            stop = (s.upEx if dd < 0 else s.dnEx) if rev else (rH + rL) / 2
            if abs(c[i] - stop) < min_stop * atr[i]:
                stop = c[i] - dd * min_stop * atr[i]
            ref = (rL if dd < 0 else rH) if rev else (rH if dd > 0 else rL) + dd * (rH - rL)
            k = len(signals)
            signals.append((nm, i, dd, stop, ref, rH, rL))
            for m in SH.MODES:
                open_[m].append(_Trade(dd, nm, stop, ref, i, k))

        if sAS != 0:
            f_new(sAS, "AS", st["AS"], asH, asL, True)
        if sLS != 0:
            f_new(sLS, "LS", st["LS"], loH, loL, True)
        if sPD != 0:
            f_new(sPD, "PD", st["PD"], pdh, pdl, True)
        if sAB != 0:
            f_new(sAB, "AB", st["AB"], asH, asL, False)
        if sOR != 0:
            f_new(sOR, "OR", st["OR"], oH, oL, False)
        for m in SH.MODES:                                                         # l.424-492
            lst = open_[m]
            for idx in range(len(lst) - 1, -1, -1):
                T = lst[idx]
                if na(T.e) and i > T.sb:
                    if closeT or newDay:
                        results[m][T.key] = ("closeT" if closeT else "new_day", -1, nan, None, nan)
                        del lst[idx]
                        continue
                    T.e = o[i]
                    T.risk = abs(o[i] - T.stop)
                    if T.risk <= 0 or T.d * (o[i] - T.stop) <= 0:
                        results[m][T.key] = ("risk<=0" if T.risk <= 0 else "open_beyond_stop", -1, nan, None, nan)
                        del lst[idx]
                        continue
                    T.tgt = o[i] + T.d * 2.0 * T.risk if m == "tp2" else (T.tgtRef if m == "liq" else nan)
                    if m == "liq" and T.d * (T.tgt - o[i]) < T.risk:
                        results[m][T.key] = (None, -1, nan, "cancel_lt_1R", nan)
                        del lst[idx]
                        continue
                    T.live = True
                    T.x0 = i
                if T.live:
                    x, why = nan, None
                    if newDay and i > T.x0:
                        x, why = c[i - 1], "new_day"
                    elif closeT and i > T.x0:
                        x, why = o[i], "closeT"
                    elif (l[i] <= T.stop) if T.d > 0 else (h[i] >= T.stop):
                        x, why = T.stop, "stop"
                    elif not na(T.tgt) and ((h[i] >= T.tgt) if T.d > 0 else (l[i] <= T.tgt)):
                        x, why = T.tgt, "target"
                    if not na(x):
                        results[m][T.key] = (None, i, x, why, (T.d * (x - T.e) - 2 * 0.0) / T.risk)
                        del lst[idx]
    for m in SH.MODES:
        for T in open_[m]:
            results[m][T.key] = (None, -1, nan, "open" if T.live else "pending", nan)
    return signals, results


def random_bars(seed, tf=15, gold=True, start="2019-02-24 17:00", days=49, holes=0.01):
    """Random-walk bars on gold's schedule (Sunday 18:00 to Friday 17:00 New York with the 17:00-18:00 break) or BTC's
    (around the clock), with single missing bars, a few longer holes, opening gaps, a few jumps, and prices rounded to
    0.05 (ties). ``start`` 2019-02-24 spans the 10 March daylight-saving change; 2019-10-27 the 3 November one."""
    rng = np.random.default_rng(seed)
    t = ny(start) + 60 * tf * np.arange(days * 1440 // tf, dtype=np.int64)
    loc = pd.to_datetime(t, unit="s", utc=True).tz_convert(NYZ)
    mins = np.asarray(loc.hour * 60 + loc.minute)
    dow = np.asarray(loc.dayofweek)
    keep = rng.random(len(t)) > holes
    if gold:
        keep &= ~((mins >= 17 * 60) & (mins < 18 * 60)) & (dow != 5)
        keep &= ~((dow == 4) & (mins >= 17 * 60)) & ~((dow == 6) & (mins < 18 * 60))
    for _ in range(max(1, days // 6)):
        j = int(rng.integers(0, len(t)))
        keep[j:j + int(rng.integers(2, 9)) * 60 // tf] = False
    t = t[keep]
    n = len(t)
    step = rng.normal(0.0, 0.35 * math.sqrt(tf / 15), n)
    jump = rng.random(n) < 0.02
    step[jump] += rng.normal(0.0, 2.0, int(jump.sum()))
    c = np.round(100.0 + np.cumsum(step), 2)
    gap = np.where(rng.random(n) < 0.06, rng.normal(0.0, 0.6, n), 0.0)
    o = np.round(np.r_[100.0, c[:-1]] + gap, 2)
    h = np.round(np.maximum(o, c) + np.abs(rng.normal(0.0, 0.25, n)), 2)
    lo = np.round(np.minimum(o, c) - np.abs(rng.normal(0.0, 0.25, n)), 2)
    c = np.round(c / 0.05) * 0.05
    o = np.round(o / 0.05) * 0.05
    h = np.maximum(np.round(h / 0.05) * 0.05, np.maximum(o, c))
    lo = np.minimum(np.round(lo / 0.05) * 0.05, np.minimum(o, c))
    v = rng.integers(10, 300, n).astype(np.float64)
    hd = rng.choice([-1, 0, 1], n, p=[0.45, 0.1, 0.45]).astype(np.float64)
    return t, o, h, lo, c, v, hd


def with_branches(bars, tf):
    """Edits that make the rare branches certain, each after a signal found (with K0) on the bars edited so far and a
    day after the previous edit: the entry bar's open at the stop ('risk<=0') or beyond it ('open_beyond_stop'), a
    hole from the entry bar to 16:00 ('closeT') or to 20:00 ('new_day'), and a hole from 15:00 to 20:15 while the
    trade may still be open (the new-day exit at the previous close). A signal depends on the bars up to it only, so
    each edit keeps its signal; what comes after it changes, which does not matter here."""
    t, o, h, lo, c, v, hd = (np.array(x) for x in bars)
    after = int(t[0]) + 3 * 86400
    for kind in ("risk0", "beyond", "closeT", "new_day", "nd_exit", "beyond", "closeT", "new_day", "nd_exit",
                 "nd_exit"):
        df = SH.session_hunter(t, o, h, lo, c, v, tf, hd, conf=())
        cand = df[(df.t_signal > after) & (df.entry_bar < len(t) - 300) & df.cancelled.isna()]
        if kind in ("closeT", "new_day"):
            cand = cand[cand.setup.isin(["LS", "PD", "OR"])]
        if cand.empty:
            break
        r = cand.iloc[0]
        s, e = int(r.bar), int(r.bar) + 1
        day = pd.Timestamp(int(t[s]), unit="s", tz="UTC").tz_convert(NYZ).strftime("%Y-%m-%d")
        if kind in ("risk0", "beyond"):
            o[e] = r.stop if kind == "risk0" else r.stop - r.dir * 0.1
            h[e] = max(h[e], o[e])
            lo[e] = min(lo[e], o[e])
        else:
            a = e if kind != "nd_exit" else int(np.searchsorted(t, ny(f"{day} 15:00")))
            until = {"closeT": "16:00", "new_day": "20:00", "nd_exit": "20:15"}[kind]
            z = int(np.searchsorted(t, ny(f"{day} {until}")))
            keep = np.ones(len(t), np.bool_)
            keep[max(a, e):z] = False
            t, o, h, lo, c, v, hd = (x[keep] for x in (t, o, h, lo, c, v, hd))
        after = int(t[s]) + 86400
    return t, o, h, lo, c, v, hd


def same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return (a == b) or (a != a and b != b)
    return a == b


def assert_matches_reference(df, ref):
    signals, results = ref
    assert len(df) == len(signals), (len(df), len(signals))
    for k, (row, s) in enumerate(zip(df.itertuples(index=False), signals)):
        got = (row.setup, row.bar, row.dir, row.stop, row.tgt_ref, row.r_hi, row.r_lo)
        assert all(same(float(a) if isinstance(a, (np.floating, float)) else a, b) for a, b in zip(got, s)), (k, got, s)
        canc = {results[m][k][0] for m in SH.MODES} - {None}
        assert len(canc) <= 1 and (row.cancelled == (canc.pop() if canc else None)), (k, row.cancelled, canc)
        for m in SH.MODES:
            _, xb, xp, why, r = results[m][k]
            mine = (getattr(row, f"exit_bar_{m}"), getattr(row, f"exit_price_{m}"), getattr(row, f"exit_reason_{m}"),
                    getattr(row, f"R_{m}"))
            if row.cancelled is not None:
                why = None
            assert mine[0] == xb and same(float(mine[1]), xp) and mine[2] == why and same(float(mine[3]), r), \
                (k, m, mine, (xb, xp, why, r))


CHARTS = [(1, 15, True, "2019-02-24 17:00"), (2, 15, False, "2019-10-20 12:00"), (3, 5, True, "2019-10-27 17:00"),
          (4, 60, False, "2019-02-24 12:00")]
CONF_SETS = [(), ("FVG",), ("FVG", "HTF"), ("FVG", "MSS"), SH.CONFS, ("PD", "RV", "TIGHT", "YC"), ("TIGHT",),
             ("YC", "RV"), ("MSS", "PD", "HTF")]


@pytest.fixture(scope="module")
def random_charts():
    return {key: with_branches(random_bars(key[0], tf=key[1], gold=key[2], start=key[3],
                                           days=35 if key[1] == 5 else 49), key[1])
            for key in CHARTS}


@pytest.mark.parametrize("key", CHARTS, ids=[f"seed{k[0]}_{k[1]}m_{'gold' if k[2] else 'btc'}" for k in CHARTS])
def test_kernel_equals_the_transcription_on_random_bars(random_charts, key):
    t, o, h, lo, c, v, hd = random_charts[key]
    tf = key[1]
    total = 0
    for conf in CONF_SETS:
        df = SH.session_hunter(t, o, h, lo, c, v, tf, hd, conf=conf)
        assert_matches_reference(df, pine_ref(t, o, h, lo, c, v, tf, hd, conf=conf))
        total += len(df)
    assert total > 100
    # the variant, another minimum stop, a subset of setups
    for kw in ({"mfl": True}, {"min_stop": 1.25}):
        mine = {"monday_friday_levels": kw.get("mfl", False), "min_stop_atr": kw.get("min_stop", 0.5)}
        df = SH.session_hunter(t, o, h, lo, c, v, tf, hd, conf=("FVG",), **mine)
        assert_matches_reference(df, pine_ref(t, o, h, lo, c, v, tf, hd, conf=("FVG",), **kw))
    df = SH.session_hunter(t, o, h, lo, c, v, tf, hd, setups=("LS", "OR"), conf=())
    assert_matches_reference(df, pine_ref(t, o, h, lo, c, v, tf, hd, setups=("LS", "OR"), conf=()))


def test_the_random_charts_reach_every_branch(random_charts):
    seen = {"setup": set(), "cancelled": set(), "why": set()}
    for key in CHARTS:
        t, o, h, lo, c, v, hd = random_charts[key]
        df = SH.session_hunter(t, o, h, lo, c, v, key[1], hd, conf=())
        seen["setup"] |= set(df.setup)
        seen["cancelled"] |= set(df.cancelled.dropna())
        for m in SH.MODES:
            seen["why"] |= set(df[f"exit_reason_{m}"].dropna())
    assert seen["setup"] == set(SH.SETUPS)
    assert seen["cancelled"] == set(SH.CANCELS)
    assert seen["why"] >= {"stop", "target", "closeT", "new_day", "cancel_lt_1R"}


# ───────────────────────────── 4. truncation invariance ─────────────────────────────

def assert_prefix(full, part, T):
    """``part`` (the bars 0..T) against ``full``: the same signals up to T, the same decisions where they are known by
    T, 'pending' / 'open' where they are not."""
    f = full[full.bar <= T].reset_index(drop=True)
    assert len(part) == len(f) and part[SIGNAL_COLS].equals(f[SIGNAL_COLS])
    for k in range(len(f)):
        a, b = f.iloc[k], part.iloc[k]
        if a.entry_bar > T:
            assert b.cancelled is None and all(b[f"exit_reason_{m}"] == "pending" for m in SH.MODES)
            continue
        assert a.cancelled == b.cancelled
        for m in SH.MODES:
            xa = a[f"exit_bar_{m}"]
            if a[f"exit_reason_{m}"] in (None, "cancel_lt_1R") or (xa != -1 and xa <= T):
                assert b[f"exit_reason_{m}"] == a[f"exit_reason_{m}"] and b[f"exit_bar_{m}"] == xa
                assert same(float(b[f"exit_price_{m}"]), float(a[f"exit_price_{m}"]))
                assert same(float(b[f"R_{m}"]), float(a[f"R_{m}"]))
            else:
                assert b[f"exit_reason_{m}"] == "open" and b[f"exit_bar_{m}"] == -1


@pytest.mark.parametrize("key", CHARTS[:3], ids=["gold_15m", "btc_15m", "gold_5m"])
def test_outputs_to_t_do_not_change_when_the_bars_after_t_are_removed(random_charts, key):
    t, o, h, lo, c, v, hd = random_charts[key]
    tf = key[1]
    rng = np.random.default_rng(7)
    for conf in ((), ("FVG", "HTF"), ("FVG", "MSS", "PD", "RV")):
        full = SH.session_hunter(t, o, h, lo, c, v, tf, hd, conf=conf)
        assert len(full) >= 3, conf
        # random cuts, a cut on a signal bar (its entry still pending) and one on an entry bar (its exits still open)
        cuts = [int(x) for x in rng.integers(200, len(t) - 1, 6)]
        cuts += [int(full.bar.iloc[len(full) // 2]), int(full.entry_bar.iloc[len(full) // 3])]
        for T in cuts:
            T = int(T)
            part = SH.session_hunter(t[:T + 1], o[:T + 1], h[:T + 1], lo[:T + 1], c[:T + 1], v[:T + 1], tf,
                                     hd[:T + 1], conf=conf)
            assert_prefix(full, part, T)
        st, sp = SH.day_state(t, o, h, lo, c, tf), SH.day_state(t[:cuts[0] + 1], o[:cuts[0] + 1], h[:cuts[0] + 1],
                                                                lo[:cuts[0] + 1], c[:cuts[0] + 1], tf)
        assert sp.equals(st.iloc[:cuts[0] + 1])
    # the 1H trend: from the 1H bars closed by T only
    hour = t // 3600
    first = np.flatnonzero(np.diff(hour, prepend=hour[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(t) - 1)
    h1 = SimpleNamespace(tc=(hour[first] + 1) * 3600, c=c[last])
    d = SH.htf_ema_dir(t, c, h1, length=20)
    T = int(cuts[0])
    k = int(np.searchsorted(h1.tc, t[T], side="right"))
    assert np.array_equal(SH.htf_ema_dir(t[:T + 1], c[:T + 1], SimpleNamespace(tc=h1.tc[:k], c=h1.c[:k]), 20),
                          d[:T + 1])


# ───────────────────────────── 5. real bars (to 2024-06-30, the guard closed) ─────────────────────────────

TFS = (("M5", 5), ("M15", 15))


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        """The M5 / M15 bars (and the 1H closes for the EMA) of ``symbol``. Only bars are kept (about 45 MB a symbol);
        the M1 market of one symbol at a time is in memory while they are built."""
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end="2024-07-01")
                h1b = mk.tbars("1H")
                h1 = SimpleNamespace(tc=h1b.tc.copy(), c=h1b.c.copy())
                del mk, h1b
            m = X.load_market(symbol, earliest="2019-01-01", end="2024-07-01")
            bars = {}
            for tf, _ in TFS:
                b = m.bars(tf)
                top = int(b.i1[-1]) + 1
                bars[tf] = SimpleNamespace(t=b.t, tc=b.tc, o=b.o, h=b.h, l=b.l, c=b.c,
                                           vol=np.add.reduceat(m.n[:top], b.i0))
            del m, b
            gc.collect()
            cache[symbol] = (bars, h1)
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_smoke(symbol, real):
    bars, h1 = real(symbol)
    assert int(h1.tc[-1]) <= TM.CUT_S
    for tf, tfm in TFS:
        b = bars[tf]
        assert int(b.tc[-1]) <= TM.CUT_S and len(b.t) > 100_000                    # nothing from the hold-out
        hd = SH.htf_ema_dir(b.t, b.c, h1)
        assert set(np.unique(hd)) <= {-1, 0, 1} and (hd[b.t >= TM.s_of("2019-01-02")] != 0).mean() > 0.999
        ck = SH.clock(b.t, tfm)
        atr = I.atr(b.h, b.l, b.c, 14)
        for conf in ((), ("FVG",), ("FVG", "HTF"), ("FVG", "MSS")):
            df = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, b.vol, tfm, hd, conf=conf)
            assert list(df.columns) == SH.COLUMNS and len(df) > 300, (tf, conf)
            assert set(df.setup) == set(SH.SETUPS), (tf, conf)
            bar = df.bar.to_numpy()
            for k in ("stop", "tgt_ref", "r_hi", "r_lo"):
                assert np.isfinite(df[k]).all(), (tf, conf, k)
            assert (df.t_signal == b.t[bar] + 60 * tfm).all() and (df.entry_bar == bar + 1).all()
            assert set(df.dir) <= {-1, 1} and (df.r_hi > df.r_lo).all()
            # every signal on a weekday trading day, inside its window, once per setup and day
            assert ck["weekday"][bar].all()
            for s in SH.SETUPS:
                sel = (df.setup == s).to_numpy()
                assert ck[f"win_{s}"][bar[sel]].all(), (tf, conf, s)
                assert len(np.unique(ck["day_key"][bar[sel]])) == sel.sum(), (tf, conf, s)
            # event geometry: the stop on the far side of the signal close, at least 0.5 ATR away; fades close inside
            # the range, breakouts beyond it
            cl = b.c[bar]
            assert (df.dir * (cl - df.stop) > 0).all()
            assert (np.abs(cl - df.stop) >= 0.5 * atr[bar] * (1 - 1e-12)).all()
            fade = df.setup.isin(["AS", "LS", "PD"]).to_numpy()
            assert ((cl > df.r_lo) & (cl < df.r_hi))[fade].all()
            brk = ~fade
            assert (np.where(df.dir > 0, cl > df.r_hi, cl < df.r_lo))[brk].all()
            # the trade manager's decisions are well formed (values are not looked at: no profit or loss here)
            assert set(df.cancelled.dropna()) <= set(SH.CANCELS)
            canc = df.cancelled.notna().to_numpy()
            for m in SH.MODES:
                why = df[f"exit_reason_{m}"]
                xb = df[f"exit_bar_{m}"].to_numpy()
                px = df[f"exit_price_{m}"].to_numpy()
                r = df[f"R_{m}"].to_numpy()
                assert why[canc].isna().all() and (xb[canc] == -1).all()
                out = why.isin(["stop", "target", "closeT", "new_day"]).to_numpy()
                assert set(why[~canc]) <= set(SH.EXIT_REASONS)
                assert (xb[out] >= df.entry_bar.to_numpy()[out]).all()
                assert np.isfinite(px[out]).all() and np.isfinite(r[out]).all()
                assert (xb[~out] == -1).all() and np.isnan(px[~out]).all() and np.isnan(r[~out]).all()
                tx = why.to_numpy() == "closeT"
                assert ck["close_t"][xb[tx]].all()
                assert ck["new_day"][xb[why.to_numpy() == "new_day"]].all()
            assert not df["exit_reason_hold"].isin(["target"]).any()             # E1 has no target
        # the variant gives Monday Friday's levels: more PD rows, all others unchanged
        a = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, b.vol, tfm, hd)
        z = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, b.vol, tfm, hd, monday_friday_levels=True)
        assert a[a.setup != "PD"].reset_index(drop=True)[SIGNAL_COLS].equals(
            z[z.setup != "PD"].reset_index(drop=True)[SIGNAL_COLS])
        assert (z.setup == "PD").sum() > (a.setup == "PD").sum()
        # the other confirmations run on real bars too
        e = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, b.vol, tfm, hd, conf=SH.CONFS)
        assert list(e.columns) == SH.COLUMNS


def _rv_holds(b, vol, tfm, hd):
    """The 'RV' rows on real bars: every signal bar has volume >= 1.5 x SMA(20) of the volume given."""
    df = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, vol, tfm, hd, conf=("FVG", "RV"))
    bar = df.bar.to_numpy()
    assert len(df) > 30 and np.isfinite(df[["stop", "tgt_ref", "r_hi", "r_lo"]].to_numpy()).all()
    assert (vol[bar] >= 1.5 * I.sma(vol, 20)[bar]).all()


@pytest.mark.parametrize("tf,tfm", TFS)
def test_real_bars_relative_volume_gold_ticks_btc_binance(real, tf, tfm):
    """PREREG 2: gold's 'RV' reads tick volume; BTC's reads Binance BTCUSDT spot volume (the 5m klines on M5, the sum
    of its M5 bars on M15). Skipped when the 5m klines (tradeiq2_market) are not available."""
    bars, h1 = real("XAUUSDm")
    b = bars[tf]
    _rv_holds(b, b.vol, tfm, SH.htf_ema_dir(b.t, b.c, h1))
    try:
        from backtesting.research import tradeiq2_market as TM2
        k = TM2.load_binance_5m(end="2024-07-01", start="2019-01-01")
    except (ImportError, AttributeError, FileNotFoundError, OSError) as exc:
        pytest.skip(f"Binance 5m klines are not available: {exc}")
    assert int(k["t"][-1]) + 300 <= TM.CUT_S
    bars, h1 = real("BTCUSDm")
    b5 = bars["M5"]
    j = np.searchsorted(k["t"], b5.t)
    jj = np.minimum(j, len(k["t"]) - 1)
    hit = (j < len(k["t"])) & (k["t"][jj] == b5.t)
    assert hit.mean() > 0.99
    v5 = np.where(hit, k["volume"][jj], 0.0)
    b = bars[tf]
    vol = v5 if tf == "M5" else np.bincount(np.searchsorted(b.t, b5.t, side="right") - 1, weights=v5,
                                            minlength=len(b.t))
    _rv_holds(b, vol, tfm, SH.htf_ema_dir(b.t, b.c, h1))


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_truncation_invariance(symbol, real):
    bars, h1 = real(symbol)
    b = bars["M15"]
    hd = SH.htf_ema_dir(b.t, b.c, h1)
    full = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, b.vol, 15, hd)
    for when in ("2020-11-17 13:00", "2022-06-01 09:00", "2023-03-13 03:00"):
        T = int(np.searchsorted(b.t, TM.s_of(when), side="right") - 1)
        part = SH.session_hunter(b.t[:T + 1], b.o[:T + 1], b.h[:T + 1], b.l[:T + 1], b.c[:T + 1], b.vol[:T + 1], 15,
                                 hd[:T + 1])
        assert_prefix(full, part, T)
