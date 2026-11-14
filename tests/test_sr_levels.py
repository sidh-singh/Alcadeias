"""
The support / resistance detector (``backtesting/research/sr.py``).

Three things are pinned down here:

* what a level is and how it lives, on hand-made price paths whose swings, touches and breaks can be
  read off the path: a swing high is a level only once the bars that confirm it have closed; a touch
  needs price to have been away first; a close beyond the buffer changes the level's role and a
  second one drops it; levels close together are one zone; previous-day / week levels and round
  numbers stand where the calendar and the price grid put them;
* that nothing looks ahead: the level table and every event computed on a history cut at an
  arbitrary minute are identical to those computed on the full history, on the real bars of the
  fixture store and on a long random history with weekends and daily breaks;
* the bookkeeping of the reaction study: which barrier a trade reaches first in each of the three
  ways of standing in the entry minute, when a level counts as having held, the matched comparison
  with the control, and that the study runs end to end on the fixture store.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import sr

T0 = 1772409600                     # 2026-03-02 00:00 UTC, a Monday
H, D = 60, 1440                     # minutes


def path(knots, t0: int = T0, spread: float = 0.2) -> dict:
    """M1 bid bars along straight lines between (minute, price) knots; a bar runs from one minute's price to the next."""
    mins = np.arange(knots[0][0], knots[-1][0] + 1)
    px = np.interp(mins, [k[0] for k in knots], [k[1] for k in knots])
    o, c = px[:-1], px[1:]
    n = len(o)
    return {"t": (t0 + mins[:-1] * 60).astype(np.int64), "o": o, "h": np.maximum(o, c), "l": np.minimum(o, c), "c": c,
            "ask_c": c + spread, "spread_mean": np.full(n, spread), "spread_max": np.full(n, spread), "n": np.full(n, 10, np.int64)}


def keep(m1: dict, mask: np.ndarray) -> dict:
    return {k: v[mask] for k, v in m1.items()}


def hours(t) -> np.ndarray:
    return (np.asarray(t) - T0) / 3600.0


# One resistance through its whole life. Thirty hours of steady rise (no swing, H1 ATR 2.5), then:
STORY = [(0, 927.0), (30 * H, 1002.0),
         (32 * H + 30, 1017.0),     # 32:30  the swing high
         (37 * H, 1002.0),          #        five ATRs away
         (40 * H, 1017.0),          # ~40:00 back up to it: first touch, from below
         (41 * H, 1015.5),          #        half an ATR away: not far enough to count as away
         (42 * H, 1017.0),          #        at it again: no new touch
         (45 * H, 1008.0),          #        away again
         (48 * H, 1017.0),          # ~48:00 second touch
         (49 * H, 1015.0),          #        not away
         (52 * H, 1024.0),          # ~50:00 closes above it: the break, it is a support now
         (55 * H, 1030.0),
         (58 * H, 1017.2),          # ~58:00 comes back from above: the retest
         (59 * H, 1019.5),          #        not away
         (63 * H, 1008.0),          # ~60:00 closes below it: broken a second time, dropped
         (66 * H, 1000.5)]
PEAK = 1017.0


@pytest.fixture(scope="module")
def story():
    m1 = path(STORY)
    prep = sr.prepare(m1, "XAUUSDm")
    return m1, prep, sr.scan(prep)


# ───────────────────────────── what a level is ─────────────────────────────

def test_a_swing_needs_higher_bars_on_neither_side():
    #                0    1    2    3    4    5    6    7    8    9
    h = np.array([1.0, 2.0, 5.0, 3.0, 5.0, 2.0, 1.0, 4.0, 4.0, 0.5])
    l = h - 1.0
    hi, _ = sr._pivots(h, l, 2)
    # bar 2 is a swing high: the equal high at bar 4 comes later and does not disqualify it. Bar 4 is not:
    # an equal high came before it. Bar 7 is one for the same reason as bar 2; bar 8, its equal, is not.
    assert list(np.flatnonzero(hi)) == [2, 7]
    assert not hi[4] and not hi[8]
    hi1, _ = sr._pivots(h, l, 1)
    assert list(np.flatnonzero(hi1)) == [2, 4, 7]
    # the first and last ``w`` bars can never be swings: their neighbours are not all there
    assert not sr._pivots(np.array([9.0, 1.0, 1.0, 1.0, 9.0]), np.zeros(5), 2)[0].any()
    # lows mirror highs
    assert list(np.flatnonzero(sr._pivots(-l, -h, 2)[1])) == [2, 7]


def test_a_swing_high_is_a_level_only_after_the_bars_that_confirm_it_have_closed(story):
    _, prep, out = story
    lv = prep["levels"]
    i = np.flatnonzero((lv["price"] == PEAK) & (lv["kind"] == sr.K_HIGH))[0]     # the first high at this price (later visits equal it)
    # the high was made in the minute before 32:30, inside the H1 bar 32:00-33:00; with three bars on
    # each side that bar is confirmed when the bar 35:00-36:00 closes
    assert lv["i_start"][i] == 32 * H + 30
    assert lv["t0"][i] == T0 + (32 * H + 29) * 60
    assert lv["kfrom"][i, sr.C_H1] == T0 + 36 * 3600
    assert lv["kto"][i, sr.C_H1] == lv["t0"][i] + 500 * 3600
    # the same high is the H4 swing of the bar 32:00-36:00 (known at 48:00) and, once the day is over, the previous day's high
    assert lv["kfrom"][i, sr.C_H4] == T0 + 48 * 3600
    assert (lv["kfrom"][i, sr.C_PDHL], lv["kto"][i, sr.C_PDHL]) == (T0 + 48 * 3600, T0 + 72 * 3600)

    snap = out["snap"]
    before = snap[(snap["t_close"] >= T0 + 33 * 3600) & (snap["t_close"] < T0 + 36 * 3600)]
    assert len(before) == 12 and not (before["res_price"] == PEAK).any() and not (before["sup_price"] == PEAK).any()
    at = snap[snap["t_close"] == T0 + 36 * 3600].iloc[0]
    assert at["res_price"] == PEAK and at["res_mask"] == 1 << sr.C_H1 and at["res_kind"] == sr.K_HIGH
    assert at["res_age_s"] == 36 * 3600 - (32 * H + 29) * 60 and at["res_touches"] == 0 and at["res_flips"] == 0
    assert at["res_dist"] == pytest.approx((PEAK - at["close"]) / at["atr"]) and at["res_armed"]


def test_touch_needs_distance_first_and_a_break_changes_the_role(story):
    m1, prep, out = story
    zone, buf = sr.SRParams().zone, sr.SRParams().buffer
    tch = out["touch"]
    mine = tch[tch["level"] == PEAK].reset_index(drop=True)
    when = hours(mine["t"])
    # two touches from below and, after the break, one from above; the visits at 42:00 and around 50:00 are not touches
    assert list(mine["side"]) == [-1, -1, 1]
    assert when == pytest.approx([39.9, 47.9, 57.9], abs=0.15)
    first = mine.iloc[0]
    assert first["touches"] == 0 and first["flips"] == 0 and first["own_mask"] == 1 << sr.C_H1 and first["n_zone"] == 1
    # the touch is the first minute whose high comes within the zone; the entry is the edge of the zone
    k = int(first["k"])
    edge = PEAK - zone * prep["atr"][k]
    assert first["atr"] == prep["atr"][k] and first["entry"] == pytest.approx(edge)
    assert m1["h"][k] >= edge > m1["h"][k - 1]
    # the second touch finds the level touched once, and the high of the first visit standing beside it
    assert list(mine["touches"]) == [0, 1, 2] and list(mine["zone_touches"]) == [0, 1, 2] and mine["n_zone"].iloc[1] == 2
    assert list(mine["flips"]) == [0, 0, 1]
    assert mine["entry"].iloc[2] == pytest.approx(PEAK + zone * mine["atr"].iloc[2])
    assert mine["since_flip_s"].iloc[2] == pytest.approx(7.9 * 3600, abs=1800) and np.isnan(mine["since_flip_s"].iloc[0])

    brk = out["brk"]
    mine_b = brk[brk["level"] == PEAK].reset_index(drop=True)
    assert list(mine_b["side"]) == [1, -1] and list(mine_b["flips"]) == [0, 1]
    up = mine_b.iloc[0]
    # the break is the first M15 close a buffer beyond the level; the M15 close before it was not
    k = int(up["k"])
    assert up["t"] == m1["t"][k] + 60 and up["t"] % 900 == 0 and hours(up["t"]) == pytest.approx(50.0, abs=0.3)
    assert up["entry"] == m1["c"][k] >= PEAK + buf * up["atr"]
    assert m1["c"][k - 15] < PEAK + buf * prep["atr"][k - 15]
    assert int(up["zone_mask"]) & (1 << sr.C_H4) and int(up["zone_mask"]) & (1 << sr.C_PDHL)

    snap = out["snap"].set_index("t_close")
    after = snap.loc[T0 + 53 * 3600]
    assert after["sup_price"] == PEAK and after["sup_flips"] == 1 and after["sup_kind"] == sr.K_HIGH
    assert after["sup_mask"] == (1 << sr.C_H1) | (1 << sr.C_H4) | (1 << sr.C_PDHL)
    assert sr.top_class([after["sup_mask"]])[0] == "H4"
    gone = out["snap"][out["snap"]["t_close"] >= mine_b.iloc[1]["t"]]
    assert len(gone) > 10 and not (gone["sup_price"] == PEAK).any() and not (gone["res_price"] == PEAK).any()


def test_levels_close_together_are_one_zone_and_one_approach():
    # two swing highs 0.5 apart (a fifth of an ATR), then one approach that runs through both zones' edges
    knots = [(0, 927.0), (30 * H, 1002.0), (32 * H + 30, 1017.0), (36 * H + 30, 1004.0), (40 * H + 30, 1017.5),
             (45 * H, 1003.0), (49 * H, 1017.3), (53 * H, 1005.0)]
    out = sr.scan(sr.prepare(path(knots), "XAUUSDm"))
    tch = out["touch"]
    late = tch[(tch["t"] >= T0 + 46 * 3600) & (tch["side"] == -1)]
    assert len(late) == 1
    e = late.iloc[0]
    # the lower high is reached first and carries the event; the zone holds both; the higher one shares the touch
    assert e["level"] == 1017.0 and e["side"] == -1 and e["n_zone"] == 2
    assert e["zone_touches"] == 1 and e["touches"] == 1          # the first high was touched when the second was made
    # strength: an H1 swing, plus the higher one that is by now also the previous day's high, plus one earlier touch
    assert e["zone_mask"] == (1 << sr.C_H1) | (1 << sr.C_PDHL) and e["own_mask"] == 1 << sr.C_H1
    assert e["strength"] == sr.CLASS_WEIGHT[sr.C_H1] + sr.CLASS_WEIGHT[sr.C_PDHL] + 1
    row = out["snap"].set_index("t_close").loc[T0 + 49 * 3600 + 1800]
    assert row["res_price"] == 1017.0 and row["res_n_zone"] == 2 and row["res_touches"] == 2 and not row["res_armed"]


def test_previous_day_and_week_levels_follow_the_calendar():
    # twelve days of round-the-clock trading: each day opens at its base, makes its high at 06:00 and its low at 15:00
    knots = []
    for d in range(12):
        base = 60000.0 + 150.0 * d
        knots += [(d * D, base), (d * D + 6 * H, base + 600.0 + 10.0 * d), (d * D + 15 * H, base - 700.0)]
    knots.append((12 * D, 60000.0 + 150.0 * 12))
    m1 = path(knots, spread=10.0)
    lv = sr.build_levels(m1, "BTCUSDm")

    def record(kind, price):
        (i,) = np.flatnonzero((lv["kind"] == kind) & np.isclose(lv["price"], price))
        return i

    day = 86400
    i = record(sr.K_HIGH, 60600.0)                              # Monday's high
    assert (lv["kfrom"][i, sr.C_PDHL], lv["kto"][i, sr.C_PDHL]) == (T0 + day, T0 + 2 * day)
    i = record(sr.K_LOW, 59450.0)                               # Tuesday's low
    assert (lv["kfrom"][i, sr.C_PDHL], lv["kto"][i, sr.C_PDHL]) == (T0 + 2 * day, T0 + 3 * day)
    i = record(sr.K_CLOSE, 60150.0)                             # Monday's close
    assert (lv["kfrom"][i, sr.C_PDC], lv["kto"][i, sr.C_PDC]) == (T0 + day, T0 + 2 * day)
    # the first week runs Monday to Sunday: its high is Sunday's, its low Monday's, its close Sunday's
    i = record(sr.K_HIGH, 60000.0 + 150.0 * 6 + 600.0 + 60.0)
    assert (lv["kfrom"][i, sr.C_PWHL], lv["kto"][i, sr.C_PWHL]) == (T0 + 7 * day, T0 + 14 * day)
    assert lv["kfrom"][i, sr.C_PDHL] == T0 + 7 * day            # ... and it is Monday's previous-day high as well
    i = record(sr.K_LOW, 59300.0)
    assert lv["kfrom"][i, sr.C_PWHL] == T0 + 7 * day
    i = record(sr.K_CLOSE, 60000.0 + 150.0 * 7)
    assert lv["kfrom"][i, sr.C_PWC] == T0 + 7 * day and lv["kfrom"][i, sr.C_PDC] == T0 + 7 * day
    # the second week is not over when the history ends: its levels are never known
    i = record(sr.K_HIGH, 60000.0 + 150.0 * 11 + 600.0 + 110.0)
    assert lv["kfrom"][i, sr.C_PWHL] >= T0 + 14 * day

    # early on Tuesday, on the way up, the table reads Monday's close below and Monday's high above;
    # a day later it reads Tuesday's, and Monday's are gone
    snap = sr.nearest_levels(m1, "BTCUSDm").set_index("t_close")
    row = snap.loc[T0 + day + 3 * 3600]
    assert row["res_price"] == 60600.0 and row["res_mask"] & (1 << sr.C_PDHL) and row["res_kind"] == sr.K_HIGH
    assert row["sup_price"] == 60150.0 and row["sup_mask"] == 1 << sr.C_PDC and row["sup_tf"] == "D"
    row = snap.loc[T0 + 2 * day + 3 * 3600]
    assert row["res_price"] == 60760.0 and row["res_mask"] & (1 << sr.C_PDHL)
    assert row["sup_price"] == 60300.0 and row["sup_mask"] == 1 << sr.C_PDC


def test_gold_counts_the_sunday_session_with_monday():
    # Friday's session, a closed weekend, Sunday 22:00 to Monday night
    fri = T0 + 4 * 86400
    mins = np.arange(0, 4 * D)
    m1 = path([(0, 2000.0), (10 * H, 2012.0), (21 * H, 2003.0), (2 * D + 22 * H, 2003.0), (3 * D + 2 * H, 2008.0),
               (3 * D + 9 * H, 1995.0), (4 * D, 2001.0)], t0=fri)
    m1 = keep(m1, (mins < 21 * H) | (mins >= 2 * D + 22 * H))
    t = m1["t"]
    dk = sr.day_key(t, True)
    assert len(np.unique(dk)) == 2                              # Friday, and Sunday evening + Monday as one day
    assert (dk[t >= fri + 2 * 86400] == (fri + 3 * 86400) // 86400).all()
    assert len(np.unique(sr.week_key(dk))) == 2                 # the Sunday session already belongs to the new week
    assert len(np.unique(sr.day_key(t, False))) == 3            # without the rule Sunday would be a day of its own
    lv = sr.build_levels(m1, "XAUUSDm")
    (i,) = np.flatnonzero((lv["kind"] == sr.K_HIGH) & np.isclose(lv["price"], 2012.0))
    # Friday's high is the previous day's high from Saturday 00:00 until Monday is over, and the previous
    # week's high from the same moment, so Sunday's reopening reads the week that ended on Friday
    assert (lv["kfrom"][i, sr.C_PDHL], lv["kto"][i, sr.C_PDHL]) == (fri + 86400, fri + 4 * 86400)
    assert lv["kfrom"][i, sr.C_PWHL] == fri + 86400


def test_round_numbers_are_levels_from_the_start():
    m1 = path([(0, 1022.0), (20 * H, 1041.0)])                  # inside one day, no swing: only the grid is there
    snap = sr.nearest_levels(m1, "XAUUSDm")
    assert snap["atr"].isna().iloc[0] and snap["sup_kind"].iloc[0] == -1 and np.isnan(snap["sup_price"].iloc[0])
    row = snap.iloc[-1]
    assert row["sup_price"] == 1000.0 and row["sup_tf"] == "round" and row["sup_mask"] == (1 << sr.C_R1) | (1 << sr.C_R2)
    assert row["res_price"] == 1050.0 and row["res_mask"] == 1 << sr.C_R1 and np.isnan(row["res_age_s"])
    assert row["sup_dist"] == pytest.approx((row["close"] - 1000.0) / row["atr"])
    btc = sr.nearest_levels(path([(0, 61200.0), (20 * H, 63800.0)], spread=10.0), "BTCUSDm").iloc[-1]
    assert btc["sup_price"] == 63000.0 and btc["res_price"] == 64000.0


# ───────────────────────────── no look-ahead ─────────────────────────────

def test_a_slower_bar_is_read_only_once_it_has_closed():
    end = np.array([3600, 7200, 10800])
    out = sr.asof(end, np.array([1.0, 2.0, 3.0]), np.array([0, 3599, 3600, 7199, 7200, 99999]))
    assert np.isnan(out[:2]).all() and list(out[2:]) == [1.0, 1.0, 2.0, 3.0]
    # the ATR a minute works with is that of the H1 bars closed before the minute opens: cutting the history
    # at the start of any hour and computing the ATR of what is left gives the same number
    m1 = random_history(11, days=4)
    prep = sr.prepare(m1, "XAUUSDm")
    t = m1["t"]
    assert np.isnan(prep["atr"][t < t[0] + 15 * 3600]).all()             # fourteen true ranges need fifteen closed bars
    for hour in (15, 16, 23, 40, 70):
        k = int(np.searchsorted(t, t[0] + hour * 3600))                  # the first minute of that hour
        past = {key: v[:k] for key, v in m1.items()}
        h1 = sr.bars_of(past, past["t"] // 3600)
        expect = sr.atr_wilder(h1["h"], h1["l"], h1["c"], 14)[-1]
        assert prep["atr"][k] == pytest.approx(expect, rel=1e-12) and prep["atr"][k + 59] == prep["atr"][k]


def _cut(m1: dict, n: int) -> dict:
    return {k: v[:n] for k, v in m1.items()}


def assert_cut_changes_nothing_earlier(m1: dict, symbol: str, cuts, shift: float = 0.0) -> dict:
    """Everything reported up to a cut must be the same whether or not the history goes on after it."""
    full = sr.scan(sr.prepare(m1, symbol), shift)
    for n in cuts:
        part = sr.scan(sr.prepare(_cut(m1, n), symbol), shift)
        now = m1["t"][n - 1] + 60                               # the last minute of the cut history has just closed
        a = full["snap"][full["snap"]["t_close"] <= now].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, part["snap"].reset_index(drop=True), obj=f"level table, cut at bar {n}")
        for name in ("touch", "brk"):
            a = full[name][(full[name]["k"] < n) & (full[name]["t"] <= now)].drop(columns="rec").reset_index(drop=True)
            pd.testing.assert_frame_equal(a, part[name].drop(columns="rec").reset_index(drop=True), obj=f"{name} events, cut at bar {n}")
    return full


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_cutting_the_history_changes_nothing_earlier_on_real_bars(fixture_store, symbol):
    m1 = store.load_m1(symbol, store.to_ms("2026-10-01"), store.to_ms("2026-12-01"), store_dir=fixture_store)
    n = len(m1["t"])
    assert n > 10_000
    rng = np.random.default_rng(20261114)
    # arbitrary minutes, plus the ends of an M15, an H1, an H4 bar and of a day, where levels become known
    special = [int(np.searchsorted(m1["t"], x)) for x in (m1["t"][n // 2] // tf * tf for tf in (900, 3600, 14400, 86400))]
    cuts = sorted(set(rng.integers(n // 4, n, 30).tolist()) | {s for s in special if s > 2000} | {n - 1})
    full = assert_cut_changes_nothing_earlier(m1, symbol, cuts)
    assert len(full["touch"]) > 50 and len(full["brk"]) > 40          # the comparison is not an empty one
    snap = full["snap"]
    assert (snap["sup_kind"] >= 0).mean() > 0.9 and (snap["res_kind"] >= 0).mean() > 0.9
    # the control maps of the study go through the same code and must be as blind to the future
    assert_cut_changes_nothing_earlier(m1, symbol, cuts[::5], shift=sr.SYMBOLS[symbol]["shifts"][-1])


def random_history(seed: int, days: int = 75) -> dict:
    """A random walk on the gold calendar: closed 21:00-22:00 UTC and from Friday 21:00 to Sunday 22:00."""
    rng = np.random.default_rng(seed)
    mins = np.arange(days * D)
    t = T0 + mins * 60
    dow, hod = (mins // D) % 7, (mins % D) // 60                 # T0 is a Monday
    is_open = (hod != 21) & ~((dow == 4) & (hod >= 21)) & (dow != 5) & ~((dow == 6) & (hod < 22))
    t = t[is_open]
    n = len(t)
    c = 3000.0 + np.cumsum(rng.normal(0.0, 0.9, n) * (1.0 + 0.5 * np.sin(np.arange(n) / 4000.0)))
    c[np.diff(t, prepend=t[0]) > 3600] += rng.normal(0.0, 6.0, int((np.diff(t, prepend=t[0]) > 3600).sum()))    # reopening gaps
    o = np.concatenate([[3000.0], c[:-1]])
    wick = np.abs(rng.normal(0.0, 0.4, (2, n)))
    return {"t": t.astype(np.int64), "o": o, "h": np.maximum(o, c) + wick[0], "l": np.minimum(o, c) - wick[1], "c": c,
            "ask_c": c + 0.2, "spread_mean": np.full(n, 0.2), "spread_max": np.full(n, 0.3), "n": np.full(n, 30, np.int64)}


def test_cutting_the_history_changes_nothing_earlier_over_weeks_of_random_bars():
    # long enough for D1 swings and several previous-week levels, which the twelve fixture days cannot show
    m1 = random_history(7)
    n = len(m1["t"])
    lv = sr.build_levels(m1, "XAUUSDm")
    assert (lv["kfrom"][:, sr.C_D1] < sr.FOREVER).sum() >= 6 and (lv["kfrom"][:, sr.C_PWHL] < m1["t"][-1]).sum() >= 16
    rng = np.random.default_rng(3)
    cuts = sorted(set(rng.integers(n // 3, n, 12).tolist()))
    full = assert_cut_changes_nothing_earlier(m1, "XAUUSDm", cuts)
    seen = np.bitwise_or.reduce(full["touch"]["zone_mask"].to_numpy())
    assert all(seen >> c & 1 for c in range(sr.N_CLASS)), "every class of level should have been touched at least once"


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_events_and_the_table_agree_with_the_bars_themselves(fixture_store, symbol):
    p = sr.SRParams()
    m1 = store.load_m1(symbol, store.to_ms("2026-10-01"), store.to_ms("2026-12-01"), store_dir=fixture_store)
    prep = sr.prepare(m1, symbol)
    out = sr.scan(prep)
    t, h, l, c, o = (prep["m1"][k] for k in ("t", "h", "l", "c", "o"))
    atr = prep["atr"]
    for e in out["touch"].itertuples():
        k, s = e.k, e.side
        edge = e.level + s * p.zone * e.atr
        assert e.atr == atr[k] and e.t == t[k]
        assert (l[k] <= edge) if s > 0 else (h[k] >= edge), "the minute of a touch reaches the zone"
        assert e.entry == (min(o[k], edge) if s > 0 else max(o[k], edge))
        # ... from the far side, after a close at least ``away`` from the level
        far = s * (c[:k] - e.level) >= p.away * atr[:k]
        assert far.any(), "price had closed away from the level before"
        assert e.n_zone >= 1 and e.zone_mask & e.own_mask == e.own_mask and e.zone_touches >= e.touches
    for e in out["brk"].itertuples():
        assert e.t % p.base_tf == 0 and e.entry == c[e.k] and e.side * (e.entry - e.level) >= p.buffer * e.atr
    snap = out["snap"].dropna(subset=["atr"])
    # a support is a level price has closed above: at most the buffer below the close, and likewise for a resistance
    assert (snap["sup_dist"].dropna() > -p.buffer).all() and (snap["res_dist"].dropna() > -p.buffer).all()
    ok = snap["sup_kind"] >= 0
    assert np.allclose(snap.loc[ok, "sup_dist"], (snap.loc[ok, "close"] - snap.loc[ok, "sup_price"]) / snap.loc[ok, "atr"])
    # a level that is only an H1 swing cannot be younger than the bars that confirm it
    for side in ("sup", "res"):
        only_h1 = snap[snap[f"{side}_mask"] == 1 << sr.C_H1]
        assert len(only_h1) > 0 and (only_h1[f"{side}_age_s"] > p.pivot_w * 3600).all()


# ───────────────────────────── the reaction study ─────────────────────────────

def _race(o, h, l, c, mode, d, target, stop, k=0, t_end=10**9):
    t = np.arange(len(o), dtype=np.int64) * 60
    a = lambda x: np.asarray(x, dtype=np.float64)
    code, k_out, px = sr._races(t, a(o), a(h), a(l), a(c), np.array([k]), mode, np.array([d]), a([target]), a([stop]), np.array([t_end]))
    return int(code[0]), int(k_out[0]), float(px[0])


def test_a_trade_ends_at_the_first_barrier_and_the_stop_wins_a_shared_minute():
    flat = [100.0] * 4
    # a long entered at the close of bar 0 (mode 0), target 101, stop 99
    assert _race(flat, [100, 100.5, 101.2, 100], [100, 99.5, 100, 100], flat, 0, 1, 101.0, 99.0) == (1, 2, 101.0)
    assert _race(flat, [100, 101.5, 100, 100], [100, 98.5, 100, 100], flat, 0, 1, 101.0, 99.0) == (-1, 1, 99.0)      # both in one minute
    assert _race([100, 98.2, 100, 100], [100, 101.5, 100, 100], [100, 98.0, 100, 100], flat, 0, 1, 101.0, 99.0) == (-1, 1, 98.2)    # opens beyond the stop
    assert _race([100, 101.6, 100, 100], [100, 101.8, 100, 100], flat, flat, 0, 1, 101.0, 99.0) == (1, 1, 101.6)     # opens beyond the target
    assert _race(flat, [101.5, 100, 100, 100], [98.5, 100, 100, 100], flat, 0, 1, 101.0, 99.0)[0] == 0                # bar 0 itself is over
    # a short is the mirror image
    assert _race(flat, [100, 100.5, 100, 100], [100, 99.5, 98.9, 100], flat, 0, -1, 99.0, 101.0) == (1, 2, 99.0)
    assert _race(flat, [100, 101.0, 100, 100], [100, 98.0, 100, 100], flat, 0, -1, 99.0, 101.0) == (-1, 1, 101.0)
    # a bounce trade entered inside bar 0 (mode 1): the bar's own high may have come before the entry and
    # is not a target; its low beyond the stop is certain to have come after
    assert _race(flat, [101.5, 100, 101.1, 100], [100, 100, 100, 100], flat, 1, 1, 101.0, 99.0) == (1, 2, 101.0)
    assert _race(flat, [101.5, 100, 100, 100], [98.5, 100, 100, 100], flat, 1, 1, 101.0, 99.0) == (-1, 0, 99.0)
    assert _race([98.7, 100, 100, 100], [100, 100, 100, 100], [98.5, 100, 100, 100], flat, 1, 1, 101.0, 99.0) == (-1, 0, 98.7)   # entered after a gap, already beyond
    # a through trade entered inside bar 0 (mode 2): the bar's extreme in its favour came after the entry and
    # counts, but an extreme beyond its stop is accepted first
    assert _race(flat, [100, 100, 100, 100], [98.5, 100, 100, 100], flat, 2, -1, 99.0, 101.0) == (1, 0, 99.0)
    assert _race(flat, [101.5, 100, 100, 100], [98.5, 100, 100, 100], flat, 2, -1, 99.0, 101.0) == (-1, 0, 101.0)
    assert _race([101.8, 100, 100, 100], [101.9, 100, 100, 100], [99.5, 100, 98.0, 100], flat, 2, -1, 99.0, 101.0) == (-1, 0, 101.0)
    assert _race(flat, [100.5, 100.5, 100, 100], [99.5, 99.5, 98.0, 100], flat, 2, -1, 99.0, 101.0) == (1, 2, 99.0)
    assert _race([98.6, 100, 100, 100], [98.8, 100, 100, 100], [98.5, 100, 100, 100], flat, 2, -1, 99.0, 101.0) == (1, 0, 98.6)   # entered after a gap, beyond its target
    # nothing reached before the time limit: closed at the last close before it
    assert _race(flat, [100.2] * 4, [99.8] * 4, [100.0, 100.1, 99.9, 100.0], 0, 1, 101.0, 99.0, t_end=170) == (0, 2, 99.9)
    assert _race(flat, [100.2] * 4, [99.8] * 4, [100.0, 100.1, 99.9, 100.05], 0, 1, 101.0, 99.0) == (0, 3, 100.05)


def test_a_rejection_is_the_first_close_back_from_the_level_unless_it_breaks_first():
    # a support at 100 touched in bar 0, ATR 2: a close at 101 or higher is half an ATR back, one at 99.5 or lower breaks it
    def first(closes, every=3, max_bars=16):
        c = np.asarray(closes, dtype=np.float64)
        base_end = np.zeros(len(c), np.int64)
        base_end[every - 1::every] = 1                           # the decision clock closes with every third minute
        j = sr._rejections(c, base_end, np.array([0]), np.array([1]), np.array([100.0]), np.array([2.0]), 0.25, 0.5, max_bars)
        return int(j[0])

    assert first([100.2, 100.4, 100.6, 100.8, 101.5, 101.2, 100.9, 100.9, 100.9]) == 5       # 101.5 came inside a bar; its close 101.2 counts
    assert first([100.2, 100.4, 100.6, 100.8, 101.5, 100.9, 100.9, 100.9, 101.0]) == 8
    assert first([100.2, 100.4, 99.4, 100.8, 101.5, 101.2]) == -1                            # closed beyond the level first
    assert first([100.2, 99.0, 100.2, 100.8, 101.5, 101.2]) == 5                             # a dip inside a bar is not a close
    assert first([100.2, 100.4, 100.6] * 3 + [101.0] * 3, max_bars=3) == -1                  # too late
    # a resistance is the mirror image
    c = np.array([99.8, 99.6, 99.4, 99.2, 98.5, 98.9])
    base_end = np.array([0, 0, 1, 0, 0, 1], np.int64)
    assert int(sr._rejections(c, base_end, np.array([0]), np.array([-1]), np.array([100.0]), np.array([2.0]), 0.25, 0.5, 16)[0]) == 5


def test_matched_comparison_of_a_sample_with_itself_is_zero():
    rng = np.random.default_rng(1)
    n = 600
    df = pd.DataFrame({"half": rng.choice(["2026H1", "2026H2"], n), "side": rng.choice([-1, 1], n), "hour": rng.integers(0, 24, n),
                       "vol": rng.uniform(0.5, 1.6, n), "week": rng.integers(0, 30, n), "atr": 10.0, "usd": 1.0})
    assert len(set(sr._strata(df, ["2026H1", "2026H2"]))) == 2 * 2 * 4 * 3      # half-year x side x session x volatility state
    df["c"] = rng.choice([-1, 0, 1], n, p=[0.55, 0.05, 0.40])
    df["x"] = np.where(df["c"] == 1, 1.0, -0.6) - 0.02
    row = sr.compare(df, df.copy(), "c", "x")
    decided = df[df["c"] != 0]
    assert row["n"] == n and row["rate"] == pytest.approx((decided["c"] == 1).mean())
    assert row["diff"] == pytest.approx(0.0, abs=1e-12) and row["diff_lo"] == pytest.approx(0.0, abs=1e-12)
    assert row["x"] == pytest.approx(df["x"].mean()) and row["x_lo"] < row["x"] < row["x_hi"]
    assert row["usd"] == pytest.approx(df["x"].mean() * 10.0)
    # a control that bounces less often shows up as a positive difference of about the right size
    worse = df.copy()
    worse.loc[worse.index[::4], "c"] = -1
    assert sr.compare(df, worse, "c", "x")["diff"] == pytest.approx((decided["c"] == 1).mean() - (worse.loc[worse["c"] != 0, "c"] == 1).mean(), abs=0.03)


def test_the_study_runs_end_to_end_on_the_fixture_store(fixture_store, monkeypatch):
    monkeypatch.setenv("ALCADEIAS_STORE_DIR", str(fixture_store))
    monkeypatch.setitem(sr.PERIODS, "FIXTURE", ("2026-10-28", "2026-10-31", "2026-11-09"))
    p = sr.SRParams()
    ev = sr.collect("BTCUSDm", "FIXTURE")
    tch = ev["touch"]
    real = tch[tch["shift"] == 0.0]
    assert len(real) > 40 and set(tch["shift"]) == {0.0, *sr.SYMBOLS["BTCUSDm"]["shifts"]}
    assert real["clean"].all() and not tch.loc[tch["shift"] != 0.0, "clean"].all()
    assert tch["t"].min() >= store.to_ms("2026-10-31") // 1000 and tch["t"].max() < store.to_ms("2026-11-08") // 1000
    code, x = tch[f"c{sr.TARGET}_{sr.STOP}"], tch[f"x{sr.TARGET}_{sr.STOP}"]
    cost = tch["spread"] / tch["atr"]
    plain = tch["entry"] == tch["thr"]                           # entered at the edge of the zone, no gap
    assert set(code.unique()) <= {-1, 0, 1} and (code == 1).any() and (code == -1).any()
    assert (x[code == 1] >= sr.TARGET - cost[code == 1] - 1e-9).all()
    assert (x[(code == -1) & plain] <= -(p.zone + sr.STOP) - cost[(code == -1) & plain] + 1e-9).all()
    assert np.allclose(tch["thr"], tch["level"] + tch["side"] * p.zone * tch["atr"])
    assert tch[["rsi_m15", "rsi_h1", "h4", "d1", "hour"]].notna().all().all()
    tabs = sr.tables(ev)
    # the through trade is the same touch taken the other way: where neither trade timed out and no minute
    # held both barriers, one wins exactly when the other loses, and together they pay the spread twice
    ct, xt = tch["ct"], tch["xt"]
    both = (code != 0) & (ct != 0)
    assert ((code[both] == -ct[both]).mean() > 0.97) and (ct == 1).any() and (ct == -1).any()
    same_exit = both & (code == -ct) & plain
    assert np.allclose((x + xt)[same_exit], -2 * cost[same_exit], atol=1e-9)
    # the rejection trade exists only where an M15 bar closed half an ATR back from the level before one closed beyond it
    took = tch["xr"].notna()
    assert 0.2 < took.mean() < 0.95 and (tch.loc[~took, "cr"] == 0).all() and set(tch.loc[took, "cr"].unique()) <= {-1, 0, 1}
    assert tabs["kinds"].iloc[0]["n"] == len(real) and tabs["rejection"].iloc[0]["n"] == int(took[tch["shift"] == 0.0].sum())
    assert {"kinds", "halves", "grid", "factors", "retest", "through_kinds", "through_factors", "rejection", "breakout", "later",
            "controls"} <= set(tabs)
    text = sr.render({"FIXTURE": tabs}, "kinds")
    assert text.count("\n") == len(tabs["kinds"]) + 1 and "all levels" in text
    assert len(tabs["summary"]) == 7 and all(sr.render({"FIXTURE": tabs}, name) for name, _ in sr.TITLES if name in tabs)
    # the count against the candidate rule covers every row with trades; a row cannot meet the rule without its interval above zero
    rows = sr.rule_rows(tabs)
    assert len(rows) == sum(int(tabs[name]["x"].notna().sum()) for name in sr.RULE_TABLES)
    assert not (rows["profit"] & ~rows["above"]).any() and not (rows["above"] & rows["below"]).any()
    count = sr.tally({"FIXTURE": tabs}).split("\n")
    assert len(count) == 3 and count[2].split(" | ")[1] == str(len(rows))
    # the hindsight count: every bar has a high and a low; a turning point is one of them; shares are shares
    turns = ev["turns"]
    assert set(turns["tf"]) == {"H1", "H4"} and set(turns["shift"]) == set(tch["shift"])
    assert (turns["turns_near"] <= turns[["turns", "near"]].min(axis=1)).all() and (turns["near"] <= turns["n"]).all()
    assert turns.groupby("tf")["n"].nunique().eq(1).all() and turns.groupby("tf")["turns"].nunique().eq(1).all()
    h1 = turns[(turns["tf"] == "H1") & (turns["shift"] == 0.0)].iloc[0]
    assert h1["n"] == 2 * 8 * 24 and 20 <= h1["turns"] <= 60 and 0 < h1["near"] < h1["n"]
