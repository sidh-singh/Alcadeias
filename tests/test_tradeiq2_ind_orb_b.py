"""
Tests of PORT B (the oracle) of "Ultimate Opening Range Breakout [LuxAlgo]", ``tests/tradeiq2_oracle_orb.py`` (study
2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.5 and claims 6-9).

1. One hand-computed test per trap of the spec's "Porting effort, risks and tests" section (its "Risks" list, in its
   order: ``test_trapN_*``), then its numbered tests 1-13 (``test_specNN_*``), then the readings R1-R16 of the module
   docstring that can be pinned on synthetic bars (``test_reading_*``), the parameters and the refused inputs.
2. The Pine primitives against study 1's independent oracle (``tests/tradeiq_oracle.py``, read-only) and the clocks
   against hand-written UTC times.
3. Truncation invariance: everything decided before bar T is unchanged when the bars from T on are removed.
4. The real bars of both symbols, M5 and M15 (the timeframes of PREREG 6.5), to 2024-06-30: the oracle runs, and every
   value the contract says exists exists. Only counts and consistency are checked; no profit or loss is computed.

Synthetic bars are placed by New York wall-clock time (``zoneinfo``) or by UTC time; their dates are in 2023. A
"quiet" bar is o = c = 100, h = 100.5, l = 99.5 (a true range of 1, so the ATR(14) stays near 1 and 2 x ATR near 2).
The "standard range" is the 09:30 bar (100, 101, 99.8, 100.2) and the 09:45 bar (100, 100.4, 99, 99.5) among quiet
bars: orHigh 101, orLow 99, width 2, so u1 / u2 / u3 = 103 / 105 / 107 and d1 / d2 / d3 = 97 / 95 / 93. Trails that
depend on the ATR are computed in the tests with study 1's ATR (an independent port) and the script's formula; every
scenario keeps a margin of at least 0.3 between a close and the level it is tested against.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_orb as O  # noqa: E402
import tradeiq_oracle as S1  # noqa: E402   (study 1's independent oracle; read-only)

NYZ = ZoneInfo("America/New_York")
nan = math.nan
CUT = int(datetime(2024, 7, 1, tzinfo=timezone.utc).timestamp())       # the hold-out start: nothing at or after it
TUE, WED, THU = "2023-01-10", "2023-01-11", "2023-01-12"                 # EST (UTC-5): both clocks agree
SUMMER = "2023-07-11"                                                    # a Tuesday in EDT (UTC-4)
ARRAYS = tuple(k for k in O.KEYS if k != "days")


# ───────────────────────────── helpers ─────────────────────────────

def ny(s: str) -> int:
    """UTC epoch seconds of a New York wall-clock time 'YYYY-MM-DD HH:MM'."""
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=NYZ).timestamp())


def utc(s: str) -> int:
    """UTC epoch seconds of a UTC time 'YYYY-MM-DD HH:MM'."""
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())


def at(day: str, hm: str) -> str:
    return f"{day} {hm}"


def eday(day: str) -> int:
    """The epoch day number of 'YYYY-MM-DD' (the ``days`` frame's ``day``)."""
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) // 86400


class Chart:
    """Synthetic chart bars of ``tf`` minutes keyed by their open time; ``symbol`` picks the day boundary ('auto')."""

    def __init__(self, tf: int = 5, symbol: str = "XAUUSDm"):
        self.tf, self.symbol, self.b = tf, symbol, {}

    def _fill(self, ta: int, tz: int, px: float, half: float, v: float) -> "Chart":
        step = 60 * self.tf
        t = -(-ta // step) * step
        while t < tz:
            self.b[t] = [px, px + half, px - half, px, v]
            t += step
        return self

    def quiet(self, a: str, z: str, px: float = 100.0, half: float = 0.5, v: float = 100.0) -> "Chart":
        """Quiet bars from New York time ``a`` to ``z`` (exclusive)."""
        return self._fill(ny(a), ny(z), px, half, v)

    def quiet_utc(self, a: str, z: str, px: float = 100.0, half: float = 0.5, v: float = 100.0) -> "Chart":
        return self._fill(utc(a), utc(z), px, half, v)

    def put(self, when: str, o, h, l, c, v=100.0) -> "Chart":
        assert l <= min(o, c) and h >= max(o, c), when
        self.b[ny(when)] = [float(o), float(h), float(l), float(c), float(v)]
        return self

    def vol(self, when: str, v: float) -> "Chart":
        self.b[ny(when)][4] = float(v)
        return self

    def drop(self, a: str, z: str) -> "Chart":
        ta, tz = ny(a), ny(z)
        for t in [t for t in self.b if ta <= t < tz]:
            del self.b[t]
        return self

    def arrays(self):
        ts = sorted(self.b)
        m = np.array([self.b[t] for t in ts], np.float64).reshape(-1, 5)
        return (np.array(ts, np.int64), m[:, 0].copy(), m[:, 1].copy(), m[:, 2].copy(), m[:, 3].copy(),
                m[:, 4].copy())

    def idx(self, when: str) -> int:
        return sorted(self.b).index(ny(when))

    def idx_utc(self, when: str) -> int:
        return sorted(self.b).index(utc(when))

    def utc_of(self, i: int) -> str:
        return datetime.fromtimestamp(sorted(self.b)[i], timezone.utc).strftime("%Y-%m-%d %H:%M")

    def ny_of(self, i: int) -> str:
        return datetime.fromtimestamp(sorted(self.b)[i], NYZ).strftime("%Y-%m-%d %H:%M")

    def _kw(self, kw):
        if "symbol" not in kw and "day_boundary" not in kw:
            kw["symbol"] = self.symbol
        return kw

    def run(self, **kw):
        t, o, h, l, c, v = self.arrays()
        return O.orb(t, o, h, l, c, v, self.tf, **self._kw(kw))

    def series(self, **kw):
        t, o, h, l, c, v = self.arrays()
        return O.orb_series(t, o, h, l, c, v, self.tf, **self._kw(kw))

    def atr(self) -> np.ndarray:
        """Study 1's ATR(14) of these bars (its independent port)."""
        t, o, h, l, c, v = self.arrays()
        return S1.atr(h, l, c, 14)

    def col(self, name: str) -> np.ndarray:
        t, o, h, l, c, v = self.arrays()
        return {"o": o, "h": h, "l": l, "c": c, "v": v}[name]


def std_range(ch: Chart, day: str) -> Chart:
    ch.put(at(day, "09:30"), 100, 101, 99.8, 100.2)
    ch.put(at(day, "09:45"), 100, 100.4, 99, 99.5)
    return ch


def gold_day(day: str = TUE, tf: int = 5, start: str = "05:00") -> Chart:
    """Quiet gold-like bars of one day, ``start`` to 16:55 New York (the 17:00-18:00 break follows), standard range."""
    return std_range(Chart(tf).quiet(at(day, start), at(day, "17:00")), day)


def bull(ch: Chart, when: str, c: float = 101.5) -> Chart:
    """A breakout bar up from a quiet close of 100: open 100.2, low 100.1, high c + 0.1."""
    return ch.put(when, 100.2, c + 0.1, 100.1, c)


def rows(r) -> pd.DataFrame:
    return r["days"]


def one_row(r):
    df = r["days"]
    assert len(df) == 1, df
    return df.iloc[0]


def on(r, key: str):
    return np.flatnonzero(r[key]).tolist()


# ───────────────────────────── 1. the traps of the spec (section 1.6, "Risks"), one test each ─────────────────────

def test_trap1_session_by_bar_open_time():
    """Risk 1: "the session is defined by bar open times" (R1). A bar is in the session when its OPEN time is in
    [start, end). M15, 09:30-10:00: the 09:30 and 09:45 bars; not the 09:15 bar (it ends at 09:30) nor the 10:00
    bar, whose wicks are therefore not in the range (they are hits of the first bar after the session). M15, the
    COMEX session 08:20-08:50: the 08:30 and 08:45 bars; the 08:15 bar overlaps the session but opens before it, the
    08:45 bar runs to 09:00, past its end; the session ends on the 09:00 bar, and the display window opens with the
    08:30 bar. M5: the 09:25 bar is out, the 09:55 bar in."""
    ch = gold_day(TUE, 15)
    ch.put(at(TUE, "09:15"), 100, 104, 96, 100)
    ch.put(at(TUE, "10:00"), 100, 104, 96, 100)
    r = ch.run()
    assert on(r, "in_session") == [ch.idx(at(TUE, "09:30")), ch.idx(at(TUE, "09:45"))]
    d = one_row(r)
    assert (d.or_high, d.or_low, d.width) == (101.0, 99.0, 2.0)
    assert (d.start_bar, d.end_bar) == (ch.idx(at(TUE, "09:30")), ch.idx(at(TUE, "09:45")))
    k = ch.idx(at(TUE, "10:00"))
    assert on(r, "session_ended")[0] == k and d.end_bar + 1 == k == d.post_bar
    assert d.hit_u1_bar == k and d.hit_d1_bar == k                 # 104 >= u1 = 103, 96 <= d1 = 97
    assert not d.hit_u2 and not d.hit_d2                            # u2 = 105, d2 = 95
    assert not r["breakout_up"].any() and not r["breakout_dn"].any()

    cx = Chart(15).quiet(at(TUE, "05:00"), at(TUE, "17:00"))
    cx.put(at(TUE, "08:15"), 100, 104, 96, 100)
    cx.put(at(TUE, "08:30"), 100, 101, 99.8, 100.2)
    cx.put(at(TUE, "08:45"), 100, 100.4, 99, 99.5)
    r = cx.series(sess=(500, 530))
    assert on(r, "in_session") == [cx.idx(at(TUE, "08:30")), cx.idx(at(TUE, "08:45"))]
    d = one_row(r)
    assert (d.or_high, d.or_low) == (101.0, 99.0) and d.post_bar == cx.idx(at(TUE, "09:00"))
    assert not r["display"][cx.idx(at(TUE, "08:15"))] and r["display"][cx.idx(at(TUE, "08:30"))]
    assert r["display"][cx.idx(at(TUE, "16:45"))]

    m5 = gold_day(TUE, 5)
    m5.put(at(TUE, "09:25"), 100, 104, 96, 100)
    m5.put(at(TUE, "09:55"), 100, 101.3, 98.7, 100)
    r = m5.run()
    assert on(r, "in_session") == list(range(m5.idx(at(TUE, "09:30")), m5.idx(at(TUE, "09:55")) + 1))
    d = one_row(r)
    assert (d.or_high, d.or_low) == (101.3, 98.7)


def test_trap2_day_reset():
    """Risk 2: "the day reset" (l.88, l.147, R3). 'ny17' (gold; 'auto' with XAUUSDm): the exchange day starts at
    17:00 New York, 22:00 UTC in winter and 21:00 UTC in summer, whatever the session clock; 'utc0' (BTC): at 00:00
    UTC. On gold the reset falls on the reopen after the 17:00-18:00 break: it wipes the range and ends the day's hit
    window, so a wick to u1 on the reopen bar is not counted. On BTC the window runs to 00:00 UTC (19:00 New York in
    winter): a wick to u1 at 18:00 New York counts, one at 19:30 does not. The reset also re-arms the hit flags: a
    second day's hit counts again."""
    w = Chart(5, None).quiet_utc("2023-01-10 20:00", "2023-01-11 06:00")
    nd = [w.utc_of(i) for i in on(w.run(day_boundary="ny17"), "new_day")]
    assert nd == ["2023-01-10 22:00"]                                         # 17:00 EST (bar 0: no, R4)
    assert [w.utc_of(i) for i in on(w.run(day_boundary="utc0"), "new_day")] == ["2023-01-11 00:00"]
    np.testing.assert_array_equal(w.run(day_boundary="ny17", clock="utc-5")["new_day"],
                                  w.run(day_boundary="ny17")["new_day"])     # the clock does not move the day
    s = Chart(5, None).quiet_utc("2023-07-11 19:00", "2023-07-12 06:00")
    assert [s.utc_of(i) for i in on(s.run(day_boundary="ny17"), "new_day")] == ["2023-07-11 21:00"]  # 17:00 EDT
    assert O.day_boundary_of("auto", "XAUUSDm") == "ny17" and O.day_boundary_of("auto", "BTCUSDm") == "utc0"
    with pytest.raises(ValueError):
        w.run(day_boundary="auto", symbol=None)

    # gold: the reopen is the reset
    g = gold_day(TUE).quiet(at(TUE, "18:00"), at(WED, "01:00"))
    g.put(at(TUE, "18:00"), 100, 104, 99.9, 100)
    r = g.run()
    k = g.idx(at(TUE, "18:00"))
    assert [g.ny_of(i) for i in on(r, "new_day")] == [at(TUE, "18:00")]
    assert r["session_ended"][k - 1] and not r["session_ended"][k] and math.isnan(r["or_high"][k])
    d = one_row(r)
    assert not d.hit_u1 and d.span_end == k

    # BTC: the hit window runs to 00:00 UTC
    b = std_range(Chart(5, "BTCUSDm").quiet(at(TUE, "05:00"), at(WED, "02:00")), TUE)
    b.put(at(TUE, "18:00"), 100, 103.5, 99.9, 100)
    b.put(at(TUE, "19:30"), 100, 105.5, 99.9, 100)                     # 00:30 UTC: the next day
    r = b.run()
    d = one_row(r)
    assert d.hit_u1_bar == b.idx(at(TUE, "18:00")) and not d.hit_u2
    assert d.span_end == b.idx(at(TUE, "19:00"))                        # 00:00 UTC

    # the flags are per day: two days, two counts
    two = gold_day(TUE).quiet(at(TUE, "18:00"), at(WED, "17:00"))
    std_range(two, WED)
    two.put(at(TUE, "11:00"), 100, 103.2, 99.9, 100).put(at(TUE, "12:00"), 100, 103.4, 99.9, 100)
    two.put(at(WED, "11:00"), 100, 103.2, 99.9, 100)
    s = two.series()
    assert s["count_u1"][-1] == 2 and s["total_sessions"][-1] == 2
    assert rows(s).hit_u1_bar.tolist() == [two.idx(at(TUE, "11:00")), two.idx(at(WED, "11:00"))]


def test_trap3_fixed_utc5_against_new_york():
    """Risk 3: "fixed UTC-5 against New York time" (l.35, 87, 225; R15). In summer (EDT) the New York clock's range is
    09:30-10:00 EDT = 13:30-14:00 UTC and its window ends at 17:00 EDT; the literal clock's range is 14:30-15:00 UTC =
    10:30-11:00 EDT and its window ends at 17:00 UTC-5 = 18:00 EDT. So the two ranges differ and the same breakout's
    trade leaves at 17:00 EDT on one clock and 18:00 EDT on the other (BTC-like bars, no reset at 17:00). In winter
    (EST) the two clocks give identical outputs."""
    def day(d):
        ch = Chart(5, "BTCUSDm").quiet(at(d, "07:00"), at(d, "19:00"))
        std_range(ch, d)
        ch.put(at(d, "10:40"), 100, 102, 98.5, 100)
        bull(ch, at(d, "16:30"), 102.5)
        return ch

    ch = day(SUMMER)
    a, b = ch.run(clock="ny"), ch.run(clock="utc-5")
    assert [ch.utc_of(i)[11:] for i in on(a, "in_session")] == ["13:30", "13:35", "13:40", "13:45", "13:50",
                                                                "13:55"]
    assert [ch.utc_of(i)[11:] for i in on(b, "in_session")] == ["14:30", "14:35", "14:40", "14:45", "14:50",
                                                                "14:55"]
    da, db = one_row(a), one_row(b)
    assert (da.or_high, da.or_low) == (101.0, 99.0) and (db.or_high, db.or_low) == (102.0, 98.5)
    k = ch.idx(at(SUMMER, "16:30"))
    assert da.entry_bar == k and db.entry_bar == k
    assert (da.exit_bar, da.exit_reason) == (ch.idx(at(SUMMER, "17:00")), "window")
    assert (db.exit_bar, db.exit_reason) == (ch.idx(at(SUMMER, "18:00")), "window")
    assert da.exit_price == 100.0 and db.exit_price == 100.0          # the quiet close of the exit bar

    w = day(TUE)
    a, b = w.run(clock="ny"), w.run(clock="utc-5")
    for key in ARRAYS:
        np.testing.assert_array_equal(a[key], b[key], err_msg=key)
    pd.testing.assert_frame_equal(a["days"], b["days"])
    assert [w.utc_of(i)[11:] for i in on(a, "in_session")][0] == "14:30"


def test_trap4_crossover_semantics():
    """Risk 4: "the crossover semantics" (l.243-244, R7). ``ta.crossover(close, orHigh)``: close > orHigh now and
    close[1] <= orHigh[1]. A close equal to orHigh is not a breakout; the next close above it is (equality on the
    previous bar is enough); a second close above is not; a re-cross after a close back inside is a new breakout
    (the alert) but not a new label; a wick above with a close inside is nothing. ``ta.crossunder`` mirrors it at
    orLow. Before the session (orHigh na) a close far above is nothing."""
    up = gold_day(TUE)
    up.put(at(TUE, "08:00"), 100, 200.5, 99.9, 200)                    # orHigh is na: no breakout
    up.put(at(TUE, "10:00"), 100, 101, 99.9, 101.0)                    # == orHigh
    up.put(at(TUE, "10:05"), 101, 101.3, 100.9, 101.2)                 # crossover (prev == orHigh)
    up.put(at(TUE, "10:10"), 101.2, 101.6, 101.1, 101.5)               # still above: none
    up.put(at(TUE, "10:15"), 101.5, 101.5, 100.7, 100.8)               # back inside
    up.put(at(TUE, "10:20"), 100.8, 101.4, 100.8, 101.3)               # re-cross: alert, no label
    up.put(at(TUE, "10:25"), 101.3, 101.8, 100.8, 100.9)               # wick above, close inside
    r = up.run()
    assert on(r, "breakout_up") == [up.idx(at(TUE, "10:05")), up.idx(at(TUE, "10:20"))]
    assert on(r, "label_up") == [up.idx(at(TUE, "10:05"))]
    assert not r["breakout_dn"].any()

    dn = gold_day(TUE)
    dn.put(at(TUE, "10:00"), 100, 100.1, 99.0, 99.0)                   # == orLow
    dn.put(at(TUE, "10:05"), 99.0, 99.1, 98.7, 98.8)                   # crossunder
    dn.put(at(TUE, "10:10"), 98.8, 98.9, 98.4, 98.5)
    dn.put(at(TUE, "10:15"), 98.5, 99.3, 98.5, 99.2)
    dn.put(at(TUE, "10:20"), 99.2, 99.2, 98.6, 98.7)                   # re-cross: alert, no label
    dn.put(at(TUE, "10:25"), 98.7, 99.6, 98.2, 99.5)                   # wick below, close inside
    r = dn.run()
    assert on(r, "breakout_dn") == [dn.idx(at(TUE, "10:05")), dn.idx(at(TUE, "10:20"))]
    assert on(r, "label_dn") == [dn.idx(at(TUE, "10:05"))]
    assert not r["breakout_up"].any()


def _trap5_chart() -> Chart:
    ch = gold_day(TUE).quiet(at(TUE, "18:00"), at(WED, "17:00"))
    std_range(ch, WED)
    bull(ch, at(TUE, "10:30"))                                          # long, trail ~97.97
    ch.put(at(TUE, "11:30"), 99.5, 99.6, 98.4, 98.5)                    # bear label while long: no short
    ch.put(at(TUE, "13:00"), 99.6, 99.7, 98.5, 98.6)                    # bear cross again: no label
    ch.put(at(WED, "10:30"), 99.8, 99.9, 98.4, 98.5)                    # Wednesday: bear label, short, trail ~102
    ch.put(at(WED, "11:30"), 100.5, 101.6, 100.4, 101.5)                # bull label while short: no long
    return ch


def test_trap5_cansignal_per_side_and_activedir_blocks():
    """Risk 5: "canSignal is per side, and activeDir blocks new trades" (l.246-272). Tuesday: a bull label opens a
    long; a bear breakout while the long is open is labelled but opens nothing; a second bear cross is neither
    labelled nor traded (canSignalDn is spent); the long is dropped at the reopen. Wednesday (the gates re-armed by
    the new day): a bear label opens a short; a bull breakout while it is open is labelled, nothing more."""
    ch = _trap5_chart()
    r = ch.run()
    i = ch.idx
    assert on(r, "label_up") == [i(at(TUE, "10:30")), i(at(WED, "11:30"))]
    assert on(r, "label_dn") == [i(at(TUE, "11:30")), i(at(WED, "10:30"))]
    assert on(r, "breakout_dn") == [i(at(TUE, "11:30")), i(at(TUE, "13:00")), i(at(WED, "10:30"))]
    ad = r["active_dir"]
    assert (ad[i(at(TUE, "10:30")):i(at(TUE, "18:00"))] == 1).all() and ad[i(at(TUE, "18:00"))] == 0
    assert (ad[i(at(WED, "10:30")):] == -1).all() and (ad[:i(at(TUE, "10:30"))] == 0).all()
    tue, wed = rows(r).iloc[0], rows(r).iloc[1]
    assert (tue.trade_side, tue.entry_bar, tue.entry_price) == (1, i(at(TUE, "10:30")), 101.0)
    assert (tue.exit_bar, tue.exit_reason) == (i(at(TUE, "18:00")), "reset") and math.isnan(tue.exit_price)
    assert tue.trade2_side == 0 and tue.entry2_bar == -1 and tue.exit2_reason == ""
    assert (wed.trade_side, wed.entry_bar, wed.entry_price) == (-1, i(at(WED, "10:30")), 99.0)
    assert wed.exit_bar == -1 and wed.exit_reason == "open" and wed.trade2_side == 0
    assert (wed.label_up_bar, wed.label_dn_bar) == (i(at(WED, "11:30")), i(at(WED, "10:30")))
    # the margins the scenario relies on (study 1's ATR, the script's formula)
    atr, l, h = ch.atr(), ch.col("l"), ch.col("h")
    long_trail = l[i(at(TUE, "10:30"))] - atr[i(at(TUE, "10:30"))] * 2.0
    short_trail = h[i(at(WED, "10:30"))] + atr[i(at(WED, "10:30"))] * 2.0
    assert 98.5 - long_trail > 0.3 and short_trail - 101.5 > 0.3


def test_trap6_nz_trailstop_on_entry_bar():
    """Risk 6: "nz(trailStop[1]) on the entry bar" (l.258, 275; R10). On the entry bar ``trailStop[1]`` is na, so the
    trail is ``low - atr * 2`` exactly; from the next bar it is ``max(trail[1], low - atr * 2)``: up after a higher
    low, unchanged after a lower one. A short mirrors it with ``high + atr * 2`` and min. The ATR is study 1's, bit
    for bit."""
    ch = gold_day(TUE)
    bull(ch, at(TUE, "10:30"))
    ch.put(at(TUE, "10:35"), 101.5, 102.6, 101.4, 102.5)
    ch.put(at(TUE, "10:40"), 102.5, 102.6, 100.9, 101.0)
    r = ch.run()
    atr, l = ch.atr(), ch.col("l")
    np.testing.assert_array_equal(r["atr"], atr)
    e = ch.idx(at(TUE, "10:30"))
    tr = r["trail"]
    assert math.isnan(tr[e - 1]) and tr[e] == l[e] - (atr[e] * 2.0)
    assert tr[e + 1] == l[e + 1] - (atr[e + 1] * 2.0) and tr[e + 1] > tr[e]
    assert l[e + 2] - (atr[e + 2] * 2.0) < tr[e + 1] and tr[e + 2] == tr[e + 1]
    assert r["active_dir"][e + 2] == 1 and 101.0 - tr[e + 2] > 0.3

    sh = gold_day(TUE)
    sh.put(at(TUE, "10:30"), 99.8, 99.9, 98.4, 98.5)
    sh.put(at(TUE, "10:35"), 98.5, 98.6, 97.5, 97.6)                    # a lower high: the trail comes down
    r = sh.run()
    atr, h = sh.atr(), sh.col("h")
    e = sh.idx(at(TUE, "10:30"))
    assert r["active_dir"][e] == -1 and r["trail"][e] == h[e] + (atr[e] * 2.0)
    assert r["trail"][e + 1] == min(r["trail"][e], h[e + 1] + (atr[e + 1] * 2.0)) < r["trail"][e]


def test_trap7_reset_before_exit_and_bear_before_exit():
    """Risk 7: "the reset runs before the exit, and the bear branch runs before the exit" (l.246 before l.274; l.263
    before l.274). (a) Gold: a long still open at 16:55 meets the reopen at 18:00, a new day: l.246 sets activeDir to
    0 before l.276 can test the gap below the trail, so the trade vanishes unbooked ('reset', NaN), and the reopen's
    wick to d2 is not a hit (the reset ended the window). With a 00:00 UTC day the same bar is no reset: the long
    exits at its close ('trail': both exit conditions hold, R11) and the wicks to d1 and d2 count. (b) A bear
    breakout on the bar on which the long's trail exit happens: the bear label is spent before the exit, so no short
    opens, then or later that day."""
    g = gold_day(TUE).quiet(at(TUE, "18:00"), at(TUE, "19:00"), px=95.0)
    bull(g, at(TUE, "16:30"))
    g.put(at(TUE, "18:00"), 95.0, 95.2, 94.8, 95.0)
    k = g.idx(at(TUE, "18:00"))
    d = one_row(g.run())
    assert (d.trade_side, d.exit_bar, d.exit_reason) == (1, k, "reset") and math.isnan(d.exit_price)
    assert not d.hit_d1 and not d.hit_d2
    d = one_row(g.run(day_boundary="utc0"))
    assert (d.exit_bar, d.exit_reason, d.exit_price) == (k, "trail", 95.0)
    assert d.hit_d1_bar == k and d.hit_d2_bar == k and not d.hit_d3

    b = gold_day(TUE)
    bull(b, at(TUE, "10:30"))
    b.put(at(TUE, "11:30"), 99.0, 99.2, 96.9, 97.0)                     # close below orLow and below the trail
    b.put(at(TUE, "13:00"), 99.6, 99.7, 98.5, 98.6)                     # a later bear cross
    r = b.run()
    k = b.idx(at(TUE, "11:30"))
    assert r["label_dn"][k] and r["active_dir"][k] == 0 and r["active_dir"][k - 1] == 1
    d = one_row(r)
    assert (d.exit_bar, d.exit_reason, d.exit_price) == (k, "trail", 97.0)
    assert d.trade2_side == 0 and (r["active_dir"][k:] == 0).all()
    assert on(r, "breakout_dn") == [k, b.idx(at(TUE, "13:00"))] and on(r, "label_dn") == [k]
    assert 97.0 < r["trail"][k - 1] - 0.3                               # the margin of the trail exit


def test_trap8_entry_booked_at_orhigh():
    """Risk 8: "the script books the entry at orHigh while the real fill differs" (l.257, 268). A bull breakout bar
    closing at 102.5 books its long at orHigh = 101 (``entryPrice``), a bear breakout closing at 97.5 its short at
    orLow = 99: the decision is known at the close, so a real fill is at least the breakout close away."""
    up = gold_day(TUE)
    bull(up, at(TUE, "10:30"), 102.5)
    s = up.series()
    e = up.idx(at(TUE, "10:30"))
    d = one_row(s)
    assert (d.entry_bar, d.entry_price) == (e, 101.0) and up.col("c")[e] == 102.5
    assert s["entry_price"][e] == 101.0 and math.isnan(s["entry_price"][e - 1])

    dn = gold_day(TUE)
    dn.put(at(TUE, "10:30"), 99.8, 99.9, 97.4, 97.5)
    d = one_row(dn.run())
    assert (d.trade_side, d.entry_price) == (-1, 99.0) and dn.col("c")[d.entry_bar] == 97.5


def test_trap9_absolute_levels_and_the_kernel_trap():
    """Risk 9: "the absolute levels and the kernel trap of section 0.4". (a) The levels are absolute prices with the
    script's arithmetic, ``orHigh + orRange * f`` and ``orLow - orRange * f`` (getExt, l.139-142), here on an inexact
    gold-like range and with the Fibonacci factors. (b) A first bar after the session that closes beyond T1: the
    label, the long and the T1 hit are on the same bar, so at the decision the target is already crossed; the oracle
    reports the absolute level, and an O2 entry at the next open must be dropped by the harness (PREREG 4). (c) The
    trail exit is close-based and books the close, never the trail level: a bar that gaps below the trail exits at
    its close; a wick below the trail with a close above does not exit."""
    ch = Chart(5).quiet(at(TUE, "05:00"), at(TUE, "17:00"), px=2032.5)
    ch.put(at(TUE, "09:30"), 2032.5, 2034.37, 2032.4, 2033.0)
    ch.put(at(TUE, "09:45"), 2032.5, 2032.6, 2031.12, 2031.5)
    for mults in ((1.0, 2.0, 3.0), (0.382, 0.618, 1.0)):
        s = ch.series(multiples=mults)
        k = ch.idx(at(TUE, "10:00"))
        hi, lo = 2034.37, 2031.12
        for j, f in enumerate(mults):
            assert s[f"u{j + 1}"][k] == hi + (hi - lo) * f and s[f"d{j + 1}"][k] == lo - (hi - lo) * f
        assert (s["or_high"][k], s["or_low"][k]) == (hi, lo)

    b = gold_day(TUE)
    b.put(at(TUE, "10:00"), 100, 103.6, 99.9, 103.5)
    r = b.run()
    k = b.idx(at(TUE, "10:00"))
    d = one_row(r)
    assert r["label_up"][k] and d.entry_bar == k and d.hit_u1_bar == k
    assert b.col("c")[k] > 101.0 + 2.0 * 1.0                           # the close is beyond u1 = 103

    g = gold_day(TUE)
    bull(g, at(TUE, "10:30"))
    g.put(at(TUE, "10:45"), 100.0, 100.1, 97.8, 99.9)                   # a wick below the trail, close above it
    g.put(at(TUE, "11:00"), 97.0, 97.3, 96.9, 97.2)                     # a gap below the trail
    r = g.run()
    w, x = g.idx(at(TUE, "10:45")), g.idx(at(TUE, "11:00"))
    trail = r["trail"][x - 1]
    assert g.col("l")[w] < r["trail"][w] < g.col("c")[w] and r["active_dir"][w] == 1
    assert g.col("o")[x] < trail - 0.3
    d = one_row(r)
    assert (d.exit_bar, d.exit_reason, d.exit_price) == (x, "trail", 97.2) and d.exit_price != trail


# ───────────────────────────── 1b. the spec's numbered tests (section 1.6, "Tests") ─────────────────────────────

def _two_days_utc(d1: str, d2: str) -> Chart:
    """BTC-like 24-hour bars (M5) over the two UTC days and every day between them."""
    ch = Chart(5, "BTCUSDm").quiet_utc(f"{d1} 00:00", f"{d2} 23:55")
    return ch


def test_spec01_dst_march():
    """Spec test 1: 2023-03-10 (Friday, EST) against 2023-03-13 (Monday, EDT): on the New York clock the range moves
    from 14:30 UTC to 13:30 UTC; on the literal UTC-5 clock it stays at 14:30 UTC. The weekend has no session."""
    ch = _two_days_utc("2023-03-10", "2023-03-13")
    a = [ch.utc_of(i) for i in on(ch.run(), "in_session")]
    fri = [f"2023-03-10 14:{m:02d}" for m in range(30, 60, 5)]
    assert a == fri + [f"2023-03-13 13:{m:02d}" for m in range(30, 60, 5)]
    b = [ch.utc_of(i) for i in on(ch.run(clock="utc-5"), "in_session")]
    assert b == fri + [f"2023-03-13 14:{m:02d}" for m in range(30, 60, 5)]


def test_spec02_dst_november():
    """Spec test 2: 2023-11-03 (Friday, EDT) against 2023-11-06 (Monday, EST): New York clock 13:30 UTC, then 14:30
    UTC; the literal UTC-5 clock 14:30 UTC on both days."""
    ch = _two_days_utc("2023-11-03", "2023-11-06")
    a = [ch.utc_of(i) for i in on(ch.run(), "in_session")]
    assert a == [f"2023-11-03 13:{m:02d}" for m in range(30, 60, 5)] + [f"2023-11-06 14:{m:02d}"
                                                                        for m in range(30, 60, 5)]
    b = [ch.utc_of(i) for i in on(ch.run(clock="utc-5"), "in_session")]
    assert b == [f"2023-11-03 14:{m:02d}" for m in range(30, 60, 5)] + [f"2023-11-06 14:{m:02d}"
                                                                        for m in range(30, 60, 5)]


def test_spec03_the_10_00_bar_closes_beyond_the_range():
    """Spec test 3: the 10:00 bar closes above the range: ``close[1] <= orHigh[1]`` holds by construction (the 09:55
    bar's high is in the range), so it is the breakout, the label and the long, on M5 and on M15."""
    for tf in (5, 15):
        ch = gold_day(TUE, tf)
        ch.put(at(TUE, "10:00"), 100.2, 101.5, 100.1, 101.4)
        r = ch.run()
        k = ch.idx(at(TUE, "10:00"))
        d = one_row(r)
        assert r["breakout_up"][k] and r["label_up"][k] and r["active_dir"][k] == 1
        assert (d.first_breakout_side, d.first_breakout_bar, d.entry_bar) == (1, k, k)


def test_spec04_a_long_open_when_the_bear_breakout_comes():
    """Spec test 4: a long is still open when the bear breakout comes (its close stays above the trail): the
    breakout (the alert) and the label, but no trade."""
    ch = gold_day(TUE)
    bull(ch, at(TUE, "10:30"))
    ch.put(at(TUE, "11:30"), 99.5, 99.6, 98.4, 98.5)
    r = ch.run()
    k = ch.idx(at(TUE, "11:30"))
    assert r["breakout_dn"][k] and r["label_dn"][k] and r["active_dir"][k] == 1
    d = one_row(r)
    assert d.trade_side == 1 and d.trade2_side == 0 and d.label_dn_bar == k
    assert 98.5 - r["trail"][k] > 0.3


def test_spec05_bear_breakout_on_the_bar_of_the_longs_trail_exit():
    """Spec test 5: a bear breakout on the same bar as the long's trail exit: the long closes, no short opens that
    day (see trap 7 (b)); here the day continues with bear closes and no short appears."""
    ch = gold_day(TUE)
    bull(ch, at(TUE, "10:30"))
    ch.put(at(TUE, "11:30"), 99.0, 99.2, 96.9, 97.0)
    ch.put(at(TUE, "12:00"), 99.5, 99.6, 98.0, 98.1)
    ch.put(at(TUE, "12:05"), 98.1, 98.2, 97.6, 97.7)
    r = ch.run()
    d = one_row(r)
    assert d.exit_bar == ch.idx(at(TUE, "11:30")) and d.exit_reason == "trail"
    assert d.trade2_side == 0 and (r["active_dir"][d.exit_bar:] == 0).all()
    assert r["breakout_dn"][ch.idx(at(TUE, "12:00"))] and on(r, "label_dn") == [d.exit_bar]


def test_spec06_long_closed_by_the_trail_then_a_bear_breakout_opens_a_short():
    """Spec test 6: the long is closed by the trail (a close inside the range, under a trail lifted above orLow by a
    rally), then a bear breakout comes: a short opens, the session's second trade (R14), booked at orLow."""
    ch = gold_day(TUE)
    bull(ch, at(TUE, "10:30"))
    ch.put(at(TUE, "10:35"), 101.5, 102.6, 101.4, 102.5)
    ch.put(at(TUE, "10:40"), 102.5, 102.9, 102.4, 102.8)
    ch.put(at(TUE, "10:45"), 102.8, 102.9, 99.5, 99.6)                  # inside the range, under the trail
    ch.put(at(TUE, "11:30"), 99.5, 99.6, 98.4, 98.5)                    # the bear breakout
    r = ch.run()
    x, e2 = ch.idx(at(TUE, "10:45")), ch.idx(at(TUE, "11:30"))
    d = one_row(r)
    assert (d.trade_side, d.exit_bar, d.exit_reason, d.exit_price) == (1, x, "trail", 99.6)
    assert r["trail"][x - 1] - 99.6 > 0.3 and not r["breakout_dn"][x]
    assert (d.trade2_side, d.entry2_bar, d.entry2_price) == (-1, e2, 99.0)
    assert r["label_dn"][e2] and r["active_dir"][e2] == -1


def test_spec07_a_second_cross_up_gives_an_alert_but_no_label():
    """Spec test 7: after the first bull breakout, a close back inside and a second close above: ``breakout_up`` (the
    alert condition) is true again, ``label_up`` is not (see trap 4)."""
    ch = gold_day(TUE)
    bull(ch, at(TUE, "10:30"))
    ch.put(at(TUE, "10:35"), 101.5, 101.5, 100.6, 100.7)
    bull(ch, at(TUE, "10:40"), 101.6)
    r = ch.run()
    assert on(r, "breakout_up") == [ch.idx(at(TUE, "10:30")), ch.idx(at(TUE, "10:40"))]
    assert on(r, "label_up") == [ch.idx(at(TUE, "10:30"))]


def test_spec08_the_trail_never_moves_down_and_a_wick_does_not_exit():
    """Spec test 8: over the whole trade the long's trail is non-decreasing, ``trail = max(trail[1], low - 2 * atr)``
    on every bar after the entry; a bar whose low goes below the trail but closes above it does not exit."""
    ch = gold_day(TUE)
    bull(ch, at(TUE, "10:30"))
    ch.put(at(TUE, "10:35"), 101.5, 102.6, 101.4, 102.5)
    ch.put(at(TUE, "10:40"), 102.5, 102.6, 98.8, 102.0)                 # the wick through the trail
    ch.put(at(TUE, "10:45"), 102.0, 102.1, 101.0, 101.2)
    r = ch.run()
    atr, l = ch.atr(), ch.col("l")
    e, w = ch.idx(at(TUE, "10:30")), ch.idx(at(TUE, "10:40"))
    tr = r["trail"]
    assert l[w] < tr[w - 1] - 0.3 and ch.col("c")[w] > tr[w] + 0.3 and r["active_dir"][w] == 1
    live = np.flatnonzero(r["active_dir"] == 1)
    assert live[0] == e and np.all(np.diff(tr[live]) >= 0)
    for k in live[1:]:
        assert tr[k] == max(tr[k - 1], l[k] - (atr[k] * 2.0))


def test_spec09_hits_t1_up_and_down_and_t2_without_breakout():
    """Spec test 9: a day that reaches T1 up (a wick to 103.2) and T1 down (a wick to 96.8) with every close inside
    the range: both hits count, once each (a second wick to u1 adds nothing), and there is no breakout. The next day
    a wick to 105.1 counts T1 and T2 up with no breakout. ``totalSessions`` = 2."""
    ch = gold_day(TUE).quiet(at(TUE, "18:00"), at(WED, "17:00"))
    std_range(ch, WED)
    ch.put(at(TUE, "11:00"), 100, 103.2, 99.9, 100.0)
    ch.put(at(TUE, "12:00"), 100, 100.1, 96.8, 100.0)
    ch.put(at(TUE, "13:00"), 100, 103.5, 99.9, 100.0)
    ch.put(at(WED, "11:00"), 100, 105.1, 99.9, 100.5)
    s = ch.series()
    assert not s["breakout_up"].any() and not s["breakout_dn"].any()
    tue, wed = rows(s).iloc[0], rows(s).iloc[1]
    assert (tue.hit_u1_bar, tue.hit_d1_bar) == (ch.idx(at(TUE, "11:00")), ch.idx(at(TUE, "12:00")))
    assert not (tue.hit_u2 or tue.hit_d2 or tue.hit_u3 or tue.hit_d3)
    assert wed.hit_u1_bar == wed.hit_u2_bar == ch.idx(at(WED, "11:00")) and not wed.hit_u3 and not wed.hit_d1
    assert tue.first_breakout_side == 0 and tue.first_breakout_bar == -1 and wed.first_breakout_side == 0
    last = len(s["total_sessions"]) - 1
    assert (s["total_sessions"][last], s["count_u1"][last], s["count_u2"][last], s["count_d1"][last]) == (2, 2, 1, 1)


def test_spec10_a_holiday_without_session_bars():
    """Spec test 10: a day with bars but none inside 09:30-10:00: no row, no range, no session end, and
    ``totalSessions`` does not change; a close above the previous day's range that day is no breakout."""
    ch = gold_day(TUE).quiet(at(TUE, "18:00"), at(WED, "17:00")).quiet(at(WED, "18:00"), at(THU, "17:00"))
    std_range(ch, THU)
    ch.drop(at(WED, "09:30"), at(WED, "10:00"))
    ch.put(at(WED, "11:00"), 100, 102.1, 99.9, 102.0)
    s = ch.series()
    assert rows(s).day.tolist() == [eday(TUE), eday(THU)]
    wed = [ch.idx(at(WED, "08:00")), ch.idx(at(WED, "11:00")), ch.idx(at(WED, "16:55"))]
    assert all(s["total_sessions"][k] == 1 and not s["session_ended"][k] and math.isnan(s["or_high"][k])
               for k in wed)
    assert not s["breakout_up"].any() and s["total_sessions"][-1] == 2


def test_spec11_a_gold_trade_open_at_16_59_is_dropped_by_the_reopen_reset():
    """Spec test 11: faithful bookkeeping on gold ('ny17'): a long still open at the session's last bar before the
    17:00 break is dropped by the reopen's reset, in winter and in summer (the boundary follows New York's daylight
    saving). On BTC-like bars ('utc0') the 17:00 New York bar exits it at its close ('window')."""
    for day in (TUE, SUMMER):
        g = gold_day(day).quiet(at(day, "18:00"), at(day, "18:30"))
        bull(g, at(day, "16:30"))
        r = g.run()
        d = one_row(r)
        k = g.idx(at(day, "18:00"))
        assert r["new_day"][k] and (d.exit_bar, d.exit_reason) == (k, "reset") and math.isnan(d.exit_price)
        assert r["active_dir"][k - 1] == 1 and r["active_dir"][k] == 0
        b = Chart(5, "BTCUSDm").quiet(at(day, "05:00"), at(day, "18:30"))
        std_range(b, day)
        bull(b, at(day, "16:30"))
        d = one_row(b.run())
        assert (d.exit_bar, d.exit_reason, d.exit_price) == (b.idx(at(day, "17:00")), "window", 100.0)


def test_spec12_m5_and_m15_give_the_same_range_but_a_different_first_breakout():
    """Spec test 12: M15 bars aggregated from the M5 bars. With the High/Low source the range is the same; the first
    breakout differs: M5 breaks out at 10:05 (its close above 101), but the M15 bar of 10:00-10:15 closes back inside
    (the 10:10 close), so M15's first breakout is the 10:30 bar (closing with the 10:40 M5 bar)."""
    m5 = gold_day(TUE, 5)
    m5.put(at(TUE, "10:05"), 100.2, 101.4, 100.1, 101.3)
    m5.put(at(TUE, "10:10"), 101.3, 101.3, 100.4, 100.5)
    m5.put(at(TUE, "10:30"), 100.5, 100.6, 100.3, 100.4)
    m5.put(at(TUE, "10:35"), 100.4, 100.8, 100.3, 100.7)
    m5.put(at(TUE, "10:40"), 100.7, 101.5, 100.6, 101.4)
    t, o, h, l, c, v = m5.arrays()
    m15 = Chart(15)
    g = t // 900
    for key in np.unique(g):
        j = np.flatnonzero(g == key)
        m15.b[int(key) * 900] = [o[j[0]], h[j].max(), l[j].min(), c[j[-1]], v[j].sum()]
    a, b = m5.run(), m15.run()
    da, db = one_row(a), one_row(b)
    assert (da.or_high, da.or_low) == (db.or_high, db.or_low) == (101.0, 99.0)
    assert m5.ny_of(da.first_breakout_bar) == at(TUE, "10:05") and m15.ny_of(db.first_breakout_bar) == at(TUE,
                                                                                                          "10:30")
    assert da.first_breakout_side == db.first_breakout_side == 1


def test_spec13_hv_against_an_sma20_that_includes_the_bar():
    """Spec test 13: ``isHV = volume > ta.sma(volume, 20)`` with the bar inside its own window (l.238-239). A bar of
    volume 100 after nineteen bars of 100 is LV (100 > 100 is false), although it would be HV against the 20 bars
    BEFORE it when the twentieth of those was 10 (95.5). A bar of 101 after nineteen of 100 is HV (100.05). A
    breakout with volume 150 is HV, one with 100 among bars of 100 is LV. Bars 0-18 are LV (the SMA is na)."""
    ch = gold_day(TUE)
    ch.vol(at(TUE, "07:00"), 10.0)
    k = ch.idx(at(TUE, "07:00")) + 20                                  # 08:40: its window is 07:05-08:40
    j = ch.idx(at(TUE, "09:00"))                                        # its window 07:25-09:00 misses 07:00
    ch.vol(at(TUE, "09:00"), 101.0)
    bull(ch, at(TUE, "10:30"))
    ch.vol(at(TUE, "10:30"), 150.0)
    s = ch.series()
    v = ch.col("v")
    assert s["vol_sma"][k] == 100.0 and not s["hv"][k]
    assert sum(v[k - 20:k]) / 20 == 95.5 and v[k] > 95.5                  # the window without the bar
    assert s["hv"][j] and s["vol_sma"][j] == pytest.approx(100.05, abs=1e-12)
    assert not s["hv"][:19].any() and np.isnan(s["vol_sma"][:19]).all()
    assert s["hv"][ch.idx(at(TUE, "10:30"))] and s["label_up"][ch.idx(at(TUE, "10:30"))]
    lv = gold_day(TUE)
    bull(lv, at(TUE, "10:30"))
    r = lv.run()
    assert r["label_up"][lv.idx(at(TUE, "10:30"))] and not r["hv"][lv.idx(at(TUE, "10:30"))]


# ───────────────────────────── 1c. readings, parameters, refused inputs ─────────────────────────────

def test_reading_r4_r5_bar_zero_and_r6_the_final_range():
    """R4-R5: bar 0 is no new day (a comparison with na is false) and its ``inSession[1]`` is false, so a chart that
    starts inside the session still resets there and forms its range from bar 0. R6: ``or_high`` / ``or_low`` are NaN on the session's own bars while the script's ``orHigh``
    forms (``or_high_live``), and equal to it from the first bar after the session to the next reset."""
    ch = Chart(5).quiet(at(TUE, "09:40"), at(TUE, "12:00"))
    ch.put(at(TUE, "09:45"), 100, 100.4, 99, 99.5)
    s = ch.series()
    assert not s["new_day"].any() and s["in_session"][0]
    d = one_row(s)
    assert (d.start_bar, d.or_high, d.or_low) == (0, 100.5, 99.0)

    g = gold_day(TUE).quiet(at(TUE, "18:00"), at(TUE, "19:00"))
    s = g.series()
    a, z = g.idx(at(TUE, "09:30")), g.idx(at(TUE, "10:00"))
    assert np.isnan(s["or_high"][:z]).all() and np.isnan(s["or_high_live"][:a]).all()
    assert s["or_high_live"][a:z].tolist() == [101.0] * (z - a)
    assert s["or_low_live"][a:z].tolist() == [99.8, 99.5, 99.5, 99.0, 99.0, 99.0]
    k = g.idx(at(TUE, "18:00"))
    np.testing.assert_array_equal(s["or_high"][z:k], s["or_high_live"][z:k])
    assert np.isnan(s["or_high"][k:]).all() and np.isnan(s["or_high_live"][k:]).all()


def test_reading_r11_trail_label_when_both_exit_conditions_hold():
    """R11: on BTC-like bars the first bar outside the window closes below the trail: both operands of l.276 hold; the
    exit is labelled 'trail' (the first operand) and booked at the close."""
    b = Chart(5, "BTCUSDm").quiet(at(TUE, "05:00"), at(TUE, "18:00"))
    std_range(b, TUE)
    bull(b, at(TUE, "16:30"))
    b.put(at(TUE, "17:00"), 99.0, 99.1, 96.0, 96.1)
    d = one_row(b.run())
    assert (d.exit_bar, d.exit_reason, d.exit_price) == (b.idx(at(TUE, "17:00")), "trail", 96.1)


def test_reading_r12_a_wiped_range_and_a_run_across_two_days():
    """R12. (a) The bars jump from 09:50 to the reopen at 18:00, a new day: on that bar l.147 wipes the range and l.181
    still counts the session, so the row has a NaN range (its ``start_bar`` / ``end_bar`` are the session's bars, its
    span runs from the reopen to the next reset, here the data end), and nothing is hit or broken afterwards. (b) Tuesday's session bars are followed directly by Wednesday's: Wednesday's first bar is a new day
    inside the session, so the range restarts there and Tuesday is never counted."""
    g = Chart(5).quiet(at(TUE, "05:00"), at(TUE, "09:55")).quiet(at(TUE, "18:00"), at(WED, "02:00"))
    g.put(at(TUE, "09:30"), 100, 101, 99.8, 100.2)
    g.put(at(TUE, "18:05"), 100, 120, 80, 100)
    s = g.series()
    d = one_row(s)
    k = g.idx(at(TUE, "18:00"))
    assert (d.start_bar, d.end_bar, d.post_bar) == (g.idx(at(TUE, "09:30")), g.idx(at(TUE, "09:50")), k)
    assert d.span_end == len(g.b) and s["session_ended"][k:].all() and np.isnan(s["or_high"][k:]).all()
    assert math.isnan(d.or_high) and math.isnan(d.width) and not d.hit_u1 and not d.hit_d3
    assert s["session_ended"][k] and s["total_sessions"][k] == 1 and math.isnan(s["or_high"][k])

    x = Chart(5).quiet(at(TUE, "07:00"), at(TUE, "10:00")).quiet(at(WED, "09:30"), at(WED, "12:00"))
    x.put(at(TUE, "09:30"), 100, 105, 95, 100)
    x.put(at(WED, "09:45"), 100, 100.4, 99, 99.5)
    s = x.series()
    d = one_row(s)
    assert d.day == eday(WED) and d.start_bar == x.idx(at(WED, "09:30"))
    assert (d.or_high, d.or_low) == (100.5, 99.0) and s["total_sessions"][-1] == 1


def test_reading_r13_first_breakout_after_the_window_and_r2_weekdays():
    """R13: on BTC-like bars with no breakout before 17:00 New York, a close above the range at 18:00 is the first
    breakout (the alert condition) but no label (the window is closed). R2: on a Saturday the 'weekdays' session does
    not exist, 'all' days (the script's default "1234567") forms it."""
    b = Chart(5, "BTCUSDm").quiet(at(TUE, "05:00"), at(TUE, "19:00"))
    std_range(b, TUE)
    bull(b, at(TUE, "18:00"))
    r = b.run()
    d = one_row(r)
    assert (d.first_breakout_side, d.first_breakout_bar) == (1, b.idx(at(TUE, "18:00")))
    assert d.label_up_bar == -1 and not r["label_up"].any() and d.trade_side == 0

    sat = "2023-01-14"
    s = Chart(5, "BTCUSDm").quiet(at(sat, "05:00"), at(sat, "12:00"))
    std_range(s, sat)
    assert not s.run()["in_session"].any() and len(rows(s.run())) == 0
    r = s.run(days="all")
    assert len(on(r, "in_session")) == 6 and one_row(r).day == eday(sat)
    with pytest.raises(ValueError):                                    # 'all' is the script's "1234567"
        s.run(days="1234567")


def test_reading_r3_the_clock0_alternative_and_no_volume():
    """R3's alternative reading, ``day_boundary='clock0'`` (midnight of the session clock), on gold-like bars: the
    18:00 reopen is then no new day, so the range lives on through the evening: the 18:00 close above it is a raw
    breakout (no label: the window ended at 17:00), the 19:00 wick to u1 = 103 counts, the long is booked as a
    'window' exit at the reopen instead of vanishing, and the reset comes at 00:00 New York. ``v=None`` (Pine's na
    volume) makes every bar LV and changes nothing else."""
    g = gold_day(TUE).quiet(at(TUE, "18:00"), at(WED, "01:00"))
    bull(g, at(TUE, "16:30"))
    g.put(at(TUE, "18:00"), 100, 102.6, 99.9, 102.5).put(at(TUE, "19:00"), 102.5, 103.2, 102.4, 102.5)
    g.vol(at(TUE, "16:30"), 150.0)                                     # an HV breakout
    k18, k19, k0 = g.idx(at(TUE, "18:00")), g.idx(at(TUE, "19:00")), g.idx(at(WED, "00:00"))
    lit, alt = g.run(), g.run(day_boundary="clock0")
    assert on(lit, "new_day") == [k18] and on(alt, "new_day") == [k0]
    dl, da = one_row(lit), one_row(alt)
    assert (dl.exit_bar, dl.exit_reason, dl.span_end) == (k18, "reset", k18) and not dl.hit_u1
    assert (da.exit_bar, da.exit_reason, da.exit_price, da.span_end) == (k18, "window", 102.5, k0)
    assert alt["breakout_up"][k18] and not alt["label_up"][k18] and da.hit_u1_bar == k19
    t, o, h, l, c, v = g.arrays()
    nv = O.orb(t, o, h, l, c, None, 5, symbol="XAUUSDm")
    assert not nv["hv"].any() and lit["hv"].any()
    for key in ARRAYS:
        if key != "hv":
            np.testing.assert_array_equal(nv[key], lit[key], err_msg=key)
    pd.testing.assert_frame_equal(nv["days"], lit["days"])


def test_reading_the_in_session_gate_reset_of_l246():
    """l.246 re-arms ``canSignalUp/Dn`` on every in-session bar, not only on a new day. With the study's sessions this
    is redundant (a new day always lies between two sessions), so it is pinned on a configuration where it is not: a
    19:00-19:30 New York session, a 23:00 window end and a 00:00 UTC day on the March 2023 daylight-saving weekend.
    Saturday's session (19:00 EST = 00:00 UTC Sunday) and Sunday's (19:00 EDT = 23:00 UTC Sunday) fall in the same UTC
    day; Saturday's bull label spends ``canSignalUp``, and only Sunday's in-session bars re-arm it for Sunday's
    label."""
    ch = Chart(5, None).quiet_utc("2023-03-12 00:00", "2023-03-12 23:55")        # Sunday UTC only
    sat, sun = "2023-03-11", "2023-03-12"
    for d in (sat, sun):
        ch.put(at(d, "19:05"), 100, 101, 99.8, 100.2)
        ch.put(at(d, "19:15"), 100, 100.4, 99, 99.5)
    bull(ch, at(sat, "20:30"))
    bull(ch, at(sun, "19:40"))
    r = ch.run(sess=(1140, 1170), window_end=1380, days="all", day_boundary="utc0")
    assert on(r, "new_day") == []                                               # one UTC day (bar 0: R4)
    assert [ch.ny_of(i) for i in on(r, "label_up")] == [at(sat, "20:30"), at(sun, "19:40")]
    d = rows(r)
    assert d.trade_side.tolist() == [1, 1] and d.exit_reason.tolist() == ["window", "open"]


def test_parameters_trail_mult_window_end_and_days_frame_contract():
    """``trail_mult`` scales the trail (``low - atr * trailMult``); ``window_end`` moves the window exit; the outputs
    have the contract's keys, lengths and dtypes; an empty input gives empty outputs."""
    ch = gold_day(TUE)
    bull(ch, at(TUE, "10:30"))
    e = ch.idx(at(TUE, "10:30"))
    r = ch.run(trail_mult=3.0)
    assert r["trail"][e] == ch.col("l")[e] - (ch.atr()[e] * 3.0)
    d = one_row(ch.run(window_end=12 * 60))
    assert (d.exit_bar, d.exit_reason) == (ch.idx(at(TUE, "12:00")), "window")
    assert tuple(r) == O.KEYS and tuple(r["days"].columns) == O.DAY_COLUMNS
    n = len(ch.b)
    for k in ARRAYS:
        assert len(r[k]) == n, k
    for k in ("in_session", "new_day", "session_ended", "breakout_up", "breakout_dn", "label_up", "label_dn", "hv"):
        assert r[k].dtype == np.bool_, k
    assert r["active_dir"].dtype == np.int8 and r["atr"].dtype == r["trail"].dtype == r["or_high"].dtype == np.float64
    df = r["days"]
    assert df.day.dtype == np.int64 and df.trade_side.dtype == np.int64 and df.hit_u1.dtype == np.bool_
    assert df.exit_reason.dtype == object and set(df.exit_reason) | set(df.exit2_reason) <= set(O.EXIT_REASONS)
    assert all(df[k].dtype == np.int64 for k in O.DAY_COLUMNS if k.endswith("_bar") or k.endswith("_side")
               or k in ("day", "span_end"))
    e0 = O.orb(np.zeros(0, np.int64), *(np.zeros(0),) * 5, 5, symbol="XAUUSDm")
    assert all(len(e0[k]) == 0 for k in ARRAYS) and tuple(e0["days"].columns) == O.DAY_COLUMNS
    assert e0["days"].dtypes.equals(df.dtypes)


def test_refused_inputs():
    """The oracle refuses what it does not port rather than guess: NaN prices or volumes, unsorted or off-grid open
    times, unequal lengths, a bad session, window, clock, days or day boundary, and 'auto' without a symbol."""
    ch = gold_day(TUE)
    t, o, h, l, c, v = ch.arrays()
    ok = dict(symbol="XAUUSDm")
    bad_c = c.copy()
    bad_c[5] = nan
    cases = [
        lambda: O.orb(t, o, h, l, bad_c, v, 5, **ok),
        lambda: O.orb(t[::-1], o, h, l, c, v, 5, **ok),
        lambda: O.orb(t + 60, o, h, l, c, v, 5, **ok),
        lambda: O.orb(t, o[:-1], h, l, c, v, 5, **ok),
        lambda: O.orb(t, o, h, l, c, v, 7, **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, sess=(600, 570), **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, window_end=500, **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, clock="America/Chicago", **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, clock="utc-13", **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, clock="UTC-5", **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, clock="utc-4", **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, days="weekends", **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, days="23456", **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, day_boundary="london"),
        lambda: O.orb(t, o, h, l, c, v, 5, day_boundary="NY17"),
        lambda: O.orb(t.astype(float), o, h, l, c, v, 5, **ok),
        lambda: O.orb(t, o, h, l, c, v, 5),
        lambda: O.orb(t, o, h, l, c, v, 5, trail_mult=0.0, **ok),
        lambda: O.orb(t, o, h, l, c, v, 5, multiples=(1.0, 2.0), **ok),
    ]
    for f in cases:
        with pytest.raises(ValueError):
            f()


# ───────────────────────────── 2. the primitives and the clocks ─────────────────────────────

def test_primitives_against_study1_oracle():
    """``pine_sma``, ``pine_rma``, ``pine_tr`` and ``pine_atr`` equal study 1's independent port (numba) and its Pine VM
    (plain Python) bit for bit, on random bars with gaps."""
    rng = np.random.default_rng(7)
    n = 600
    c = 100 + np.cumsum(rng.normal(0, 0.4, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.2, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.3, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.3, n))
    v = rng.integers(1, 400, n).astype(float)
    for k in (14, 20, 3, 1):
        np.testing.assert_array_equal(O.pine_sma(v, k), S1.sma(v, k))
        np.testing.assert_array_equal(O.pine_sma(c, k), S1.sma(c, k))
        np.testing.assert_array_equal(O.pine_rma(c, k), S1.rma(c, k))
        vm = S1.Sma(k)
        np.testing.assert_array_equal(O.pine_sma(c, k), np.array([vm(x) for x in c]))
        vr = S1.Rma(k)
        np.testing.assert_array_equal(O.pine_rma(c, k), np.array([vr(x) for x in c]))
    np.testing.assert_array_equal(O.pine_tr(h, l, c), S1.true_range(h, l, c))
    np.testing.assert_array_equal(O.pine_atr(h, l, c, 14), S1.atr(h, l, c, 14))
    assert np.isnan(O.pine_atr(h, l, c, 14)[:13]).all() and np.isfinite(O.pine_atr(h, l, c, 14)[13:]).all()


def test_clocks_against_hand_written_utc_times():
    """The New York clock at the 2023 daylight-saving changes (02:00 local: 07:00 UTC on 12 March, 06:00 UTC on 5
    November), the fixed UTC-5 clock, Pine's ``dayofweek`` (1 = Sunday) and the two exchange days."""
    t = np.array([utc("2023-03-12 06:55"), utc("2023-03-12 07:00"), utc("2023-11-05 05:55"), utc("2023-11-05 06:00"),
                  utc("2023-01-10 14:30"), utc("2023-07-11 13:30")], np.int64)
    minute, day, dow = O.session_clock(t, "ny")
    assert minute.tolist() == [1 * 60 + 55, 3 * 60, 1 * 60 + 55, 1 * 60, 9 * 60 + 30, 9 * 60 + 30]
    assert dow.tolist() == [1, 1, 1, 1, 3, 3]                           # Sundays, then Tuesdays
    minute, day, dow = O.session_clock(t, "utc-5")
    assert minute.tolist() == [1 * 60 + 55, 2 * 60, 0 * 60 + 55, 1 * 60, 9 * 60 + 30, 8 * 60 + 30]
    e = np.array([utc("2023-01-10 21:55"), utc("2023-01-10 22:00"), utc("2023-07-11 20:55"), utc("2023-07-11 21:00"),
                  utc("2023-07-11 23:55"), utc("2023-07-12 00:00")], np.int64)
    d17 = O.exchange_day(e, "ny17") - O.exchange_day(e, "ny17")[0]
    d0 = O.exchange_day(e, "utc0") - O.exchange_day(e, "utc0")[0]
    assert d17.tolist() == [0, 1, 182, 183, 183, 183]
    assert d0.tolist() == [0, 0, 182, 182, 182, 183]


# ───────────────────────────── 3. truncation invariance ─────────────────────────────

def _random_chart(seed: int, tf: int, kind: str) -> Chart:
    """Random-walk bars over two weeks around the March 2023 daylight-saving change: gold-like (Sunday 18:00 to
    Friday 17:00 New York, the 17:00-18:00 break, a gap at each reopen) or BTC-like (24/7)."""
    rng = np.random.default_rng(seed)
    ch = Chart(tf, "XAUUSDm" if kind == "gold" else "BTCUSDm")
    step = 60 * tf
    if kind == "gold":
        spans = []
        for d0 in ("2023-03-05", "2023-03-06", "2023-03-07", "2023-03-08", "2023-03-09",
                   "2023-03-12", "2023-03-13", "2023-03-14", "2023-03-15", "2023-03-16"):
            d1 = datetime.strptime(d0, "%Y-%m-%d").toordinal() + 1
            spans.append((ny(f"{d0} 18:00"), ny(f"{datetime.fromordinal(d1):%Y-%m-%d} 17:00")))
    else:
        spans = [(utc("2023-03-08 00:00"), utc("2023-03-16 00:00"))]
    p = 100.0
    for a, z in spans:
        p += rng.normal(0, 0.4)
        for t in range(a, z, step):
            o = p
            c = o + rng.normal(0, 0.12 * math.sqrt(tf / 5))
            hi = max(o, c) + abs(rng.normal(0, 0.06))
            lo = min(o, c) - abs(rng.normal(0, 0.06))
            o, c = round(o, 2), round(c, 2)
            ch.b[t] = [o, max(round(hi, 2), o, c), min(round(lo, 2), o, c), c, float(rng.integers(20, 200))]
            p = c
    return ch


def censor(df: pd.DataFrame, T: int) -> pd.DataFrame:
    """What a full run's ``days`` says about the bars before T: the sessions that ended before T, with every event
    at or after T removed (an open trade, an unhit level, no breakout yet, no reset yet)."""
    d = df[df.post_bar < T].copy()
    late = d.first_breakout_bar >= T
    d.loc[late, "first_breakout_side"] = 0
    d.loc[late, "first_breakout_bar"] = -1
    for k in O.HIT_NAMES:
        late = d[f"hit_{k}_bar"] >= T
        d.loc[late, f"hit_{k}_bar"] = -1
        d.loc[late, f"hit_{k}"] = False
    for side in ("up", "dn"):
        late = d[f"label_{side}_bar"] >= T
        d.loc[late, f"label_{side}_bar"] = -1
    for side, eb, ep, xb, xp, why in (O.TRADE1_COLUMNS, O.TRADE2_COLUMNS):
        gone = d[eb] >= T
        d.loc[gone, [side, eb, xb]] = [0, -1, -1]
        d.loc[gone, [ep, xp]] = nan
        d.loc[gone, why] = ""
        still = (d[eb] >= 0) & (d[xb] >= T)
        d.loc[still, xb] = -1
        d.loc[still, xp] = nan
        d.loc[still, why] = "open"
    late = d.span_end >= T                              # the next reset is not in the cut bars: the data end
    d.loc[late, "span_end"] = T
    return d.reset_index(drop=True).astype(df.dtypes.to_dict())


def assert_prefix(full, part, T: int) -> None:
    for k in ARRAYS:
        np.testing.assert_array_equal(part[k], full[k][:T], err_msg=k)
    pd.testing.assert_frame_equal(part["days"], censor(full["days"], T))


@pytest.mark.parametrize("kind,tf", [("gold", 5), ("gold", 15), ("btc", 5), ("btc", 15)])
def test_truncation_invariance(kind, tf):
    """Every per-bar value and every ``days`` value decided before bar T is the same when the bars from T on are
    removed, for cuts at random bars and at every kind of event (session ends, breakouts, labels, entries, exits,
    resets, hits), with the default inputs and with the literal UTC-5 clock on all days."""
    ch = _random_chart(11 + tf, tf, kind)
    t, o, h, l, c, v = ch.arrays()
    for kw in (dict(), dict(clock="utc-5", days="all")):
        full = O.orb(t, o, h, l, c, v, tf, symbol=ch.symbol, **kw)
        df = full["days"]
        assert len(df) >= 6 and (df.trade_side != 0).sum() >= 3 and set(df.exit_reason) >= {"trail"}
        marks = set()
        for col in ("end_bar", "first_breakout_bar", "label_up_bar", "label_dn_bar", "entry_bar", "exit_bar",
                    "entry2_bar", "exit2_bar", "span_end", "hit_u1_bar", "hit_d1_bar"):
            for b in df[col]:
                if b >= 0:
                    marks.update((int(b), int(b) + 1))
        rng = np.random.default_rng(tf)
        marks = sorted(T for T in marks if 1 <= T < len(t))
        pick = rng.choice(len(marks), size=min(36, len(marks)), replace=False)
        cuts = sorted({marks[j] for j in pick} | set(rng.integers(1, len(t), 8).tolist()))
        for T in cuts:
            part = O.orb(t[:T], o[:T], h[:T], l[:T], c[:T], v[:T], tf, symbol=ch.symbol, **kw)
            assert_prefix(full, part, T)


# ───────────────────────────── 4. the real bars (to 2024-06-30) ─────────────────────────────

@pytest.fixture(scope="module")
def real():
    """Per symbol (one at a time): the M5 and M15 bars of ``external.load_market(symbol, earliest="2019-01-01",
    end="2024-07-01")`` with their tick volume (the sum of the M1 tick counts n over each bar's [i0, i1])."""
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2019, 1) not in months or (2024, 6) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            cache.clear()
            m = X.load_market(symbol, earliest="2019-01-01", end="2024-07-01")
            assert int(m.t[0]) >= utc("2019-01-01 00:00") and int(m.t[-1]) + 60 <= CUT
            charts = {}
            for tf, key in ((5, "M5"), (15, "M15")):
                b = m.bars(key)
                assert np.all(b.i0[1:] == b.i1[:-1] + 1) and int(b.i1[-1]) == len(m) - 1
                charts[tf] = NS(t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(),
                                c=b.c.copy(), v=np.add.reduceat(m.n, b.i0).astype(np.float64))
            del m
            cache[symbol] = charts
        return cache[symbol]
    return get


def check_real(r, b, symbol: str) -> None:
    """Every value the contract says exists exists, and the outputs agree with each other and with the bars. Nothing
    is aggregated into a result, nothing is shown."""
    n = len(b.t)
    assert tuple(r) == O.KEYS and all(len(r[k]) == n for k in ARRAYS)
    atr = r["atr"]
    assert np.isnan(atr[:13]).all() and np.isfinite(atr[13:]).all() and (atr[13:] >= 0).all()
    se, ins = r["session_ended"], r["in_session"]
    df = r["days"]
    assert tuple(df.columns) == O.DAY_COLUMNS and len(df) > 1000
    end = df.post_bar.to_numpy()
    assert np.array_equal(end, df.end_bar.to_numpy() + 1)
    stop = df.span_end.to_numpy()                          # the next reset after the session's end, or n
    wiped = df.or_high.isna().to_numpy()                   # R12: only when the first bar after the session is a new day
    assert r["new_day"][end[wiped]].all()
    in_wiped = np.zeros(n, bool)
    for a, z in zip(end[wiped], stop[wiped]):
        in_wiped[a:z] = True
    ok = se & ~in_wiped
    assert not (se & ins).any()
    assert np.isfinite(r["or_high"][ok]).all() and np.isfinite(r["or_low"][ok]).all()
    assert np.isnan(r["or_high"][~ok]).all() and np.isnan(r["or_low"][~ok]).all()
    assert (r["or_high"][ok] >= r["or_low"][ok]).all()
    live = r["active_dir"] != 0
    assert set(np.unique(r["active_dir"])) <= {-1, 0, 1}
    assert np.isfinite(r["trail"][live]).all() and np.isnan(r["trail"][~live]).all()
    for side in ("up", "dn"):
        lab, brk = r["label_" + side], r["breakout_" + side]
        assert not (lab & ~brk).any() and not (brk & ~se).any() and not (brk & ins).any()
    assert not (r["breakout_up"] & r["breakout_dn"]).any()
    assert not (ins[1:] & r["new_day"][1:] & ins[:-1]).any()           # no session run across two days (R12)
    for key, lvl, sign in (("breakout_up", "or_high", 1.0), ("breakout_dn", "or_low", -1.0)):
        k = np.flatnonzero(r[key])
        assert (k >= 1).all() and (sign * (b.c[k] - r[lvl][k]) > 0).all()
        kk = k[se[k - 1]]                                                # not the first bar after the session
        assert (sign * (b.c[kk - 1] - r[lvl][kk - 1]) <= 0).all()

    good = df[~wiped]
    assert np.isfinite(good.or_high).all() and (good.width >= 0).all() and (df.start_bar >= 0).all()
    assert (np.diff(df.end_bar) > 0).all() and (df.start_bar <= df.end_bar).all()
    assert se[end].all() and not se[end - 1].any() and ins[df.start_bar].all() and ins[end - 1].all()
    np.testing.assert_array_equal(df.or_high.to_numpy(), r["or_high"][end])
    nxt = df.start_bar.to_numpy()[1:]
    assert (stop > end).all() and (stop[:-1] <= nxt).all()
    hi = df.or_high.to_numpy()
    lo = df.or_low.to_numpy()
    for j in range(len(df)):
        a, z = end[j], stop[j]
        assert se[a:z].all() and (z == n or not se[z])
        brk = np.flatnonzero(r["breakout_up"][a:z] | r["breakout_dn"][a:z])
        fb = df.first_breakout_bar.iat[j]
        assert (fb == -1 and brk.size == 0) or (brk.size > 0 and fb == a + brk[0])
        for name, f in zip(O.HIT_NAMES, (1.0, 2.0, 3.0, 1.0, 2.0, 3.0)):
            if name[0] == "u":
                lvl = hi[j] + (hi[j] - lo[j]) * f
                touch = np.flatnonzero(b.h[a:z] >= lvl)
            else:
                lvl = lo[j] - (hi[j] - lo[j]) * f
                touch = np.flatnonzero(b.l[a:z] <= lvl)
            hb = df[f"hit_{name}_bar"].iat[j]
            assert (hb == -1 and touch.size == 0) or (touch.size > 0 and hb == a + touch[0]), (j, name)
            assert df[f"hit_{name}"].iat[j] == (hb >= 0)
        for side, key in (("up", "label_up_bar"), ("dn", "label_dn_bar")):
            lab = np.flatnonzero(r["label_" + side][a:z])
            assert lab.size <= 1 and df[key].iat[j] == (a + lab[0] if lab.size else -1)
    for cols in (O.TRADE1_COLUMNS, O.TRADE2_COLUMNS):
        side, eb, ep, xb, xp, why = cols
        tr = df[df[side] != 0]
        assert set(tr[side]) <= {-1, 1} and set(tr[why]) <= {"trail", "window", "reset", "open"}
        assert (df[df[side] == 0][why] == "").all()
        assert (tr[ep] == np.where(tr[side] > 0, tr.or_high, tr.or_low)).all()
        lab = np.where(tr[side] > 0, tr.label_up_bar, tr.label_dn_bar)
        assert np.array_equal(tr[eb].to_numpy(), lab)
        done = tr[tr[why].isin(["trail", "window"])]
        assert np.array_equal(done[xp].to_numpy(), b.c[done[xb].to_numpy()])
        gone = tr[tr[why] == "reset"]
        assert gone[xp].isna().all() and r["new_day"][gone[xb].to_numpy()].all()
        assert np.array_equal(gone[xb].to_numpy(), gone.span_end.to_numpy())
        still = tr[tr[why] == "open"]
        assert len(still) <= 1 and (still.index == len(df) - 1).all() and (still[xb] == -1).all()
    none = df[df.trade_side == 0]
    assert (none.trade2_side == 0).all()


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    """The real bars of both symbols, M5 and M15 (PREREG 6.5), 2019-01-01 to 2024-06-30: the defaults (New York clock,
    weekdays, the symbol's exchange day) and the variants of PREREG 6.5 (gold's COMEX range 08:20-08:50 on both
    timeframes; on M15 the literal UTC-5 clock and BTC on all days). The only NaN range is gold's M5 COMEX session of
    2021-03-02, cut by a data hole from 08:25 EST into the next exchange day (R12). Then a cut at 2021-06-15 12:00
    UTC changes nothing before it."""
    charts = real(symbol)
    for tf, b in charts.items():
        assert int(b.tc[-1]) <= CUT and int(b.t[0]) >= utc("2019-01-01 00:00")
        r = O.orb(b.t, b.o, b.h, b.l, b.c, b.v, tf, symbol=symbol)
        check_real(r, b, symbol)
        assert not r["days"].or_high.isna().any()
        if not symbol.startswith("BTC"):
            cx = O.orb(b.t, b.o, b.h, b.l, b.c, b.v, tf, symbol=symbol, sess=(500, 530))
            check_real(cx, b, symbol)
            wiped = cx["days"][cx["days"].or_high.isna()]
            assert wiped.day.tolist() == ([eday("2021-03-02")] if tf == 5 else [])
    b = charts[15]
    variants = [dict(clock="utc-5")] + ([dict(days="all")] if symbol.startswith("BTC") else [])
    for kw in variants:
        check_real(O.orb(b.t, b.o, b.h, b.l, b.c, b.v, 15, symbol=symbol, **kw), b, symbol)
    T = int(np.searchsorted(b.t, utc("2021-06-15 12:00")))
    full = O.orb(b.t, b.o, b.h, b.l, b.c, b.v, 15, symbol=symbol)
    part = O.orb(b.t[:T], b.o[:T], b.h[:T], b.l[:T], b.c[:T], b.v[:T], 15, symbol=symbol)
    assert_prefix(full, part, T)
