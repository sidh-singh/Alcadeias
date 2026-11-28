"""
Port B (the oracle) of the Market Structure Dashboard, ``tests/tradeiq2_oracle_msd.py`` (study 2, PREREG 6.2).

1. One hand-computed test per trap of the spec's porting risks (``maps/structure.md`` section 6, risks 1-11), named
   after it (``test_trap01_..`` .. ``test_trap11_..``). Each builds bars (or zones) by hand and states the expected
   values with the arithmetic in the comments; where a wrong reading is easy to write, the test also shows that it
   would give another value.
2. The spec's other test cases: the contract (keys, dtypes), the swing factor's exact points, the maximum score,
   the merge against ``tradeiq_market.htf_at``, weekly bars built from ``external.day_bars``, independent second
   formulations of the pivots, the FVG patterns and the weekly bars.
3. Truncation invariance: the outputs up to bar T are unchanged when the bars after T are removed, on synthetic
   gold-like and BTC-like calendars, on every chart, also with each row's forming (partial) bar left in.
4. Real bars (skipped when the tick store is absent): both symbols, the 1H / 4H / 1D charts, bars to 2024-06-30
   only (study 1's guard pointed at an empty folder): it runs, every value exists and is in range, the score and the
   label follow from the factors, the merge equals ``htf_at``, and a cut at one T changes nothing before it.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from backtesting import config as C
from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_msd as O  # noqa: E402

nan = math.nan
H = 3600
H4 = 4 * H
DAY = 86400
WEEK = 7 * DAY
T0 = 1546300800            # 2019-01-01 00:00 UTC, a Tuesday
SUN0 = 1546732800          # 2019-01-06 00:00 UTC, a Sunday
MON0 = 1546819200          # 2019-01-07 00:00 UTC, a Monday


# ───────────────────────────── helpers ─────────────────────────────

def bars_of(ohlc, step=H, t0=T0, symbol="XAUUSDm"):
    """Bars from rows (o, h, l, c), one every ``step`` seconds from ``t0``; tc = t + step."""
    a = np.asarray(ohlc, np.float64).reshape(-1, 4)
    t = t0 + step * np.arange(len(a), dtype=np.int64)
    return NS(t=t, tc=t + step, o=a[:, 0].copy(), h=a[:, 1].copy(), l=a[:, 2].copy(), c=a[:, 3].copy(), symbol=symbol)


def run_row(ohlc):
    """A Row driven bar by bar; returns the row (its state can be inspected) and every bar's outputs."""
    row = O.Row()
    outs = [row.step(*(float(v) for v in r)) for r in ohlc]
    return row, outs


def pivots(values, kind, ties="strict"):
    s = O.Series()
    out = []
    for k, v in enumerate(values):
        s.push(float(v))
        out.append(O.pivot(s, k, 5, 5, kind, ties))
    return out


def is_nan(x):
    return x != x


def zones(arr):
    return [(z.dir, z.top, z.bottom, z.barIdx) for z in arr]


def far_row(t_after, symbol="XAUUSDm"):
    """One bar closing after every chart bar of a test: the row never merges, so it scores 0."""
    return NS(t=np.asarray([t_after], np.int64), tc=np.asarray([t_after + WEEK], np.int64), o=np.asarray([1.0]),
              h=np.asarray([1.0]), l=np.asarray([1.0]), c=np.asarray([1.0]), symbol=symbol)


def contract_keys(chart_tf):
    keys = {"label", "score", "max_score", "bos", "bos_trend"}
    for r in O.active_rows(chart_tf):
        keys |= {f"s_{r}", f"struct_{r}", f"ob_{r}", f"fvg_{r}", f"swing_{r}"}
    return keys


# synthetic calendars: hourly bars, aggregated as the harness aggregates (UTC buckets, tc = the bucket's end)

def hours(kind, weeks, t0=SUN0):
    """1H open times. 'gold': Sunday 22:00-24:00, Monday-Thursday every hour but 21:00 (the daily break),
    Friday 00:00-21:00, nothing on Saturday. 'btc': every hour."""
    out = []
    for k in range(weeks * 7 * 24):
        t = t0 + k * H
        dow = (t // DAY + 3) % 7                    # 0 Monday .. 6 Sunday
        hr = (t % DAY) // H
        if kind == "btc":
            out.append(t)
        elif dow == 6 and hr >= 22:
            out.append(t)
        elif dow in (0, 1, 2, 3) and hr != 21:
            out.append(t)
        elif dow == 4 and hr < 21:
            out.append(t)
    return np.asarray(out, np.int64)


def walk_bars(t, seed, decimals=None, step=H, symbol="XAUUSDm"):
    rng = np.random.default_rng(seed)
    n = len(t)
    c = 2000.0 + np.cumsum(rng.standard_normal(n) * 2.0)
    o = np.r_[c[0], c[:-1]] + rng.standard_normal(n) * 0.3
    h = np.maximum(o, c) + np.abs(rng.standard_normal(n))
    lo = np.minimum(o, c) - np.abs(rng.standard_normal(n))
    if decimals is not None:
        o, h, lo, c = (np.round(x, decimals) for x in (o, h, lo, c))
        h = np.maximum(h, np.maximum(o, c))
        lo = np.minimum(lo, np.minimum(o, c))
    return NS(t=np.asarray(t, np.int64), tc=np.asarray(t, np.int64) + step, o=o, h=h, l=lo, c=c, symbol=symbol)


def _agg(b, groups, t_open, t_close, symbol):
    o = np.asarray([b.o[g[0]] for g in groups])
    h = np.asarray([b.h[g].max() for g in groups])
    lo = np.asarray([b.l[g].min() for g in groups])
    c = np.asarray([b.c[g[-1]] for g in groups])
    return NS(t=np.asarray(t_open, np.int64), tc=np.asarray(t_close, np.int64), o=o, h=h, l=lo, c=c, symbol=symbol)


def h4_of(b1):
    key = b1.t // H4
    groups = [np.flatnonzero(key == k) for k in np.unique(key)]
    return _agg(b1, groups, [key[g[0]] * H4 for g in groups], [key[g[0]] * H4 + H4 for g in groups], b1.symbol)


def d1_of(b1, min_hours=6):
    """UTC days; a day with fewer than ``min_hours`` 1H bars is merged into the next day (external.day_bars' rule
    with 360 M1 bars = 6 hours): it opens at its own midnight and closes when that next day ends."""
    day = b1.t // DAY
    groups, opens, closes = [], [], []
    cur, start = [], None
    for d in np.unique(day):
        idx = np.flatnonzero(day == d)
        if start is None:
            start = int(d)
        cur.extend(idx.tolist())
        if len(idx) >= min_hours:
            groups.append(np.asarray(cur))
            opens.append(start * DAY)
            closes.append((int(d) + 1) * DAY)
            cur, start = [], None
    return _agg(b1, groups, opens, closes, b1.symbol)


def rows_of(b1):
    d1 = d1_of(b1)
    return {"1H": b1, "4H": h4_of(b1), "1D": d1, "1W": O.weekly_bars(d1)}


# ───────────────────────────── 1. the spec's traps (risks 1-11), by hand ─────────────────────────────

def test_trap01_pivot_ties_strict_on_both_sides():
    # ta.pivothigh(high, 5, 5): bar 5 (10) is above the 5 bars before it (1..5) and the 5 after it (5..1): it is
    # reported on bar 10 = 5 + 5, with its own value; na everywhere else (bars 0-9 cannot hold a full window)
    hi = [1, 2, 3, 4, 5, 10, 5, 4, 3, 2, 1, 0]
    got = pivots(hi, "high")
    assert all(is_nan(x) for x in got[:10]) and got[10] == 10.0 and is_nan(got[11])
    # an equal value 5 bars BEFORE the candidate (bar 0 = 10): no pivot under the study's strict reading; a pivot
    # under the readings that allow ties on the older side
    hi_old = [10, 2, 3, 4, 5, 10, 5, 4, 3, 2, 1]
    assert is_nan(pivots(hi_old, "high")[10])
    assert pivots(hi_old, "high", "ties_left")[10] == 10.0 and pivots(hi_old, "high", "ties_both")[10] == 10.0
    assert is_nan(pivots(hi_old, "high", "ties_right")[10])
    # an equal value 5 bars AFTER it (bar 10 = 10): the mirror
    hi_new = [1, 2, 3, 4, 5, 10, 5, 4, 3, 2, 10]
    assert is_nan(pivots(hi_new, "high")[10]) and is_nan(pivots(hi_new, "high", "ties_left")[10])
    assert pivots(hi_new, "high", "ties_right")[10] == 10.0 and pivots(hi_new, "high", "ties_both")[10] == 10.0
    # a tie 6 bars away is outside the window: still a pivot
    assert pivots([10, 1, 2, 3, 4, 5, 10, 5, 4, 3, 2, 1], "high")[11] == 10.0
    # pivot lows mirror it: bar 5 (1) below 2..6 on both sides, reported on bar 10; a tie on either side kills it
    lo = [6, 5, 4, 3, 2, 1, 2, 3, 4, 5, 6]
    assert pivots(lo, "low")[10] == 1.0 and all(is_nan(x) for x in pivots(lo, "low")[:10])
    lo_tie = [6, 5, 4, 3, 2, 1, 2, 3, 4, 5, 1]
    assert is_nan(pivots(lo_tie, "low")[10]) and pivots(lo_tie, "low", "ties_right")[10] == 1.0
    # a bar with only 4 bars before it is never a pivot (the first full window ends on bar 10)
    assert all(is_nan(x) for x in pivots([1, 2, 3, 4, 10, 5, 4, 3, 2, 1], "high"))
    # end to end: two equal tops 3 bars apart give no swing high under the strict reading
    flat = [(100, 101, 99, 100)] * 5 + [(100, 110, 99, 100), (100, 105, 99, 100), (100, 105, 99, 100),
                                         (100, 110, 99, 100)] + [(100, 101, 99, 100)] * 8
    _, outs = run_row(flat)
    assert all(is_nan(o["swing_h"]) for o in outs) and all(is_nan(o["pivot_high"]) for o in outs)
    with pytest.raises(ValueError):
        pivots(hi, "high", "loose")


def test_trap02_structure_override_uses_prev_not_curr_and_a_tie_is_lh():
    # calcStructure fed by hand: (pivotHigh, pivotLow, close) -> (rtHighType, rtLowType, structureBias)
    s = O.CalcStructure()
    seq = [
        ((nan, 90.0, 100.0), (0, 0, 0)),     # the first pivot low: no previous one, lowType stays 0
        ((110.0, nan, 100.0), (0, 0, 0)),    # the first pivot high
        ((nan, 95.0, 100.0), (0, 1, 0)),     # 95 > 90: HL, lowType +1 (prevL = 90)
        ((105.0, nan, 100.0), (-1, 1, 0)),   # 105 < 110: LH, highType -1 (prevH = 110): mixed, 0
        ((nan, nan, 107.0), (-1, 1, 0)),     # 107 > currH 105 but not > prevH 110: no override (a currH port: +1)
        ((nan, nan, 110.0), (-1, 1, 0)),     # 110 > 110 is false
        ((nan, nan, 112.0), (1, 1, 1)),      # 112 > prevH 110: the "real-time HH", +1 with the HL: BULLISH structure
        ((nan, nan, 100.0), (-1, 1, 0)),     # it does not persist
        ((nan, nan, 92.0), (-1, 1, 0)),      # 92 < currL 95 but not < prevL 90: no override (a currL port: -1, -1)
        ((nan, nan, 89.0), (-1, -1, -1)),    # 89 < prevL 90: the "real-time LL": LH + LL, -1
        ((105.0, nan, 100.0), (-1, 1, 0)),   # a pivot high EQUAL to the previous one (105 == 105) counts LH (L384)
        ((nan, nan, 106.0), (1, 1, 1)),      # prevH is now 105: 106 > 105 overrides to +1
        ((nan, 95.0, 100.0), (-1, -1, -1)),  # a pivot low EQUAL to the previous one (95 == 95) is LL (L393): HL -> LL
        ((nan, 85.0, 100.0), (-1, -1, -1)),  # 85 < 95: LL; prevL = 95 and 100 is not below it: LH + LL, -1
        ((nan, nan, 106.0), (1, -1, 0)),     # 106 > prevH 105: the high side turns +1, the low side stays LL: 0
    ]
    for k, (inp, want) in enumerate(seq):
        assert s.step(*inp) == want, (k, inp)
    # a plain HH + HL is +1 with no override (100 is neither above prevH 110 nor below prevL 90)
    s2 = O.CalcStructure()
    for inp in ((nan, 90.0, 100.0), (110.0, nan, 100.0), (nan, 95.0, 100.0)):
        s2.step(*inp)
    assert s2.step(115.0, nan, 100.0) == (1, 1, 1)
    # end to end through Row: pivot highs 110 (bar 5) then 105 (bar 16, LH), pivot lows 90 (bar 11) then 95 (bar 21,
    # HL), then closes of 107 (above currH 105, below prevH 110), 112 (above prevH) and 100
    ohlc = ([(100, 101, 97, 100), (100, 102, 97.5, 101), (101, 103, 98, 102), (102, 104, 98.5, 103),
             (103, 105, 99, 104),
             (104, 110, 99.5, 105),                                       # bar 5: pivot high 110
             (105, 106, 95, 96), (96, 103, 94, 95), (95, 102, 93, 94), (94, 101, 92, 93), (93, 100, 91, 92),
             (92, 99, 90, 93),                                            # bar 11: pivot low 90
             (93, 100, 91, 99), (99, 101, 92, 100), (100, 102, 93, 101), (101, 103, 94, 102),
             (102, 105, 96, 104),                                         # bar 16: pivot high 105 (LH), < 110
             (104, 104.5, 97, 98), (98, 104, 96.5, 97), (97, 103, 96, 96.5), (96.5, 102, 95.5, 96),
             (96, 101, 95, 96),                                           # bar 21: pivot low 95 (HL)
             (96, 101.5, 96, 101), (101, 102, 97, 101.5), (101.5, 102.5, 98, 102), (102, 103, 99, 102.5),
             (102.5, 104, 100, 103.5),                                    # bar 26: confirms the pivot low 95
             (103.5, 107.5, 103, 107),                                    # bar 27: close 107: > 105, < 110
             (107, 113, 106, 112),                                        # bar 28: close 112 > 110
             (112, 112.5, 99, 100)])                                      # bar 29: back to 100
    _, outs = run_row(ohlc)
    assert outs[10]["pivot_high"] == 110.0 and outs[16]["pivot_low"] == 90.0
    assert outs[21]["pivot_high"] == 105.0 and outs[26]["pivot_low"] == 95.0
    assert [outs[k]["high_type"] for k in (21, 26, 27, 28, 29)] == [-1, -1, -1, 1, -1]
    assert [outs[k]["low_type"] for k in (21, 26, 27, 28, 29)] == [0, 1, 1, 1, 1]
    assert [outs[k]["struct"] for k in (26, 27, 28, 29)] == [0, 0, 1, 0]


def test_trap03_swing_factor_uses_the_chart_close():
    # a 4H row with a pivot high 110 on bar 5 (confirmed on bar 10) and a pivot low 90 on bar 10 (confirmed on bar
    # 15); no break, no FVG, one pivot per side: struct 0, ob 0, fvg 0, so its score is its swing factor
    hl = [(101, 95), (102, 96), (103, 97), (104, 98), (105, 99), (110, 100), (105, 99), (104, 98), (103, 97),
          (102, 96), (101, 90), (102, 96), (103, 97), (104, 98), (105, 99), (106, 98.5)]
    ohlc4 = [((h + lo) / 2, h, lo, (h + lo) / 2) for h, lo in hl]
    ohlc4[-1] = (102.0, 106.0, 98.5, 99.0)                     # the row's last close: 99 = 45% of 90..110
    r4 = bars_of(ohlc4, step=H4)
    st = O.calc_all(r4)
    assert st["swing_h"][15] == 110.0 and st["swing_l"][15] == 90.0
    assert st["struct"][15] == 0 and st["ob_dir"][15] == 0 and st["fvg_dir"][15] == 0
    # four 1H chart bars inside the next 4H bar (the 4H row shows its bar 15 all along): closes 91, 100, 108, 111
    closes = [91.0, 100.0, 108.0, 111.0]
    r1 = bars_of([(c, c, c, c) for c in closes], step=H, t0=int(r4.tc[-1]))
    rows = {"1H": r1, "4H": r4, "1D": far_row(int(r1.tc[-1])), "1W": far_row(int(r1.tc[-1]))}
    out = O.structure_dashboard(rows, "1H")
    # (91 - 90) / 20 * 100 = 5 -> +1; 50 -> 0; 90 -> -1; 105 (> 100) -> +1
    assert out["swing_4H"].tolist() == [1, 0, -1, 1]
    assert out["s_4H"].tolist() == [1, 0, -1, 1]
    assert out["score"].tolist() == [2, 0, -2, 2]               # weight 2; the 1H, D and W rows score 0 here
    # with the row's own close (99, 45%) it would be 0 on all four bars
    assert O.swing_bias_dir(110.0, 90.0, 99.0, 0.001) == 0


def test_trap04_six_slot_caps_pop_before_mitigation_obs_by_close_fvgs_by_wick():
    # (a) the FVG cap feeds the bias: a bullish gap just below the close is the nearest zone (+1) until the 7th
    # zone arrives and limitArraySize pops it (the oldest); then the nearest is a far bearish gap (-1)
    f = O.CalcFVG(6)
    assert f.step((1, 99.0, 98.0, 0), 99.5, 100.5, 100.0) == (1, -1.0)       # |99 - 100| = 1
    for k in range(5):                                                         # bearish gaps, bottoms 150..154
        assert f.step((-1, 160.0 + k, 150.0 + k, k + 1), 99.5, 100.5, 100.0) == (1, -1.0)
    assert len(f.fvgs) == 6
    assert f.step((-1, 165.0, 155.0, 6), 99.5, 100.5, 100.0) == (-1, 50.0)   # 7 zones -> pop the bullish one
    assert len(f.fvgs) == 6 and all(z.dir == -1 for z in f.fvgs)
    # (b) the cap pops BEFORE the mitigation: six live gaps (bottoms 90..95), a 7th (bottom 99.5) on a bar with a low
    # of 99: unshift (7), pop the oldest (bottom 90), then the wick removes the new one: 5 zones, the oldest gone
    # (mitigating first would leave 6 with the oldest kept)
    g = O.CalcFVG(6)
    for k in range(6):
        g.step((1, 91.0 + k, 90.0 + k, k), 99.5, 101.0, 100.0)
    assert [z.bottom for z in g.fvgs] == [95.0, 94.0, 93.0, 92.0, 91.0, 90.0]
    assert g.step((1, 100.0, 99.5, 6), 99.0, 101.0, 100.0) == (1, -4.0)       # nearest top 96: 96 - 100
    assert [z.bottom for z in g.fvgs] == [95.0, 94.0, 93.0, 92.0, 91.0]
    # (c) order blocks are mitigated by the CLOSE, FVGs by the WICK
    obs = [O.ZoneBlock(1, 101.0, 100.0, 0), O.ZoneBlock(-1, 110.0, 109.0, 0)]
    O.mitigate_obs(obs, 100.0)                                                 # 100 < 100 false; 100 > 110 false
    assert len(obs) == 2
    O.mitigate_obs(obs, 110.0)                                                 # 110 > 110 false
    assert len(obs) == 2
    O.mitigate_obs(obs, 99.99)                                                 # the bullish one goes
    assert zones(obs) == [(-1, 110.0, 109.0, 0)]
    O.mitigate_obs(obs, 110.01)
    assert obs == []
    fv = [O.ZoneBlock(1, 101.0, 100.0, 0), O.ZoneBlock(-1, 110.0, 109.0, 0)]
    O.mitigate_fvgs(fv, 100.0, 110.0)                                          # low 100 / high 110: both stay
    assert len(fv) == 2
    O.mitigate_fvgs(fv, 99.99, 105.0)                                          # a wick under the bottom
    assert zones(fv) == [(-1, 110.0, 109.0, 0)]
    O.mitigate_fvgs(fv, 105.0, 110.01)
    assert fv == []
    # (d) end to end: a bullish gap (bottom 101 = high of bar 0, top 102 = low of bar 2) seen on bar 3, whose own
    # low (100.9) is below the bottom: detected and removed on the same bar
    ohlc = [(100, 101, 99, 100.5), (100.5, 104, 100, 103.5), (103.5, 105, 102, 104.5), (104.5, 106, 100.9, 105.5)]
    _, outs = run_row(ohlc)
    assert outs[3]["new_fvg"] == 1 and outs[3]["n_fvg"] == 0 and outs[3]["fvg_dir"] == 0
    # (e) the order-block cap: a zigzag of rising cycles (troughs 100 + 10 j at bar 12 j, peaks 115 + 10 j at bar
    # 12 j + 6) breaks each peak in the next leg up and leaves one bullish block per cycle at the trough; the 7th
    # block pops the oldest
    pts = [(12 * j, 100.0 + 10 * j) for j in range(10)] + [(12 * j + 6, 115.0 + 10 * j) for j in range(9)]
    pts.sort()
    xs = np.arange(pts[-1][0] + 1)
    c = np.interp(xs, [p[0] for p in pts], [p[1] for p in pts])
    zig = [(min(max(c[k - 1] if k else c[0], c[k] - 0.5), c[k] + 0.5), c[k] + 0.5, c[k] - 0.5, c[k])
           for k in range(len(c))]                                             # open: the last close, inside the bar
    row, outs = run_row(zig)
    made = [k for k, o in enumerate(outs) if o["new_ob"] == 1]
    assert made == [12 * j + 15 for j in range(8)]                             # close 117.5 + 10 j > 115.5 + 10 j
    assert [outs[k]["n_ob"] for k in made] == [1, 2, 3, 4, 5, 6, 6, 6]        # the 7th and 8th pop the oldest
    assert max(o["n_ob"] for o in outs) == 6
    assert sorted(z.bottom for z in row.calcOrderBlock.obs) == [109.5 + 10 * j for j in range(2, 8)]


def test_trap05_order_block_search_window_ties_overlap_and_pivot_first():
    # (a) the window (pivot, break], the lowest low, a tie to the most recent bar
    a = [(100, 101, 99, 100), (100, 102, 99, 101), (101, 103, 100, 102), (102, 104, 101, 103), (103, 105, 102, 104),
         (104, 110, 90, 105),      # 5: pivot high 110; its low 90 is the lowest of all, but the pivot bar is outside
         (105, 108, 100, 101), (101, 107, 96, 97), (97, 106, 94, 95),
         (95, 104, 93, 99),        # 9: low 93
         (99, 103, 95, 100),       # 10: the pivot high is confirmed: lastPH 110, lastPHBar 5
         (100, 108, 93, 107),      # 11: low 93 again: the tie goes to this, the more recent bar
         (107, 112, 106, 111)]     # 12: close 111 > 110 and close[1] 107 <= 110: the bullish break
    row, outs = run_row(a)
    assert outs[10]["pivot_high"] == 110.0
    assert [o["bull_break"] for o in outs] == [False] * 12 + [True]
    # barsBack = 12 - 5 - 1 = 6: bars 12..6, lows 106 93 95 93 94 96 100 -> bar 11 (strict <, scanning back)
    assert zones(row.calcOrderBlock.obs) == [(1, 108.0, 93.0, 11)]
    assert outs[12]["new_ob"] == 1 and outs[12]["ob_dir"] == 1 and outs[12]["ob_dist"] == 108.0 - 111.0
    # (b) a second break whose lowest candle touches the first block (its high 93 = the block's bottom 93): the
    # overlap test (>=, <=) rejects it; bar 21's wick to 91 does not mitigate the block (its close is 93)
    b = [(111, 113, 110, 112), (112, 114, 111, 113), (113, 115, 112, 114), (114, 116, 113, 115), (115, 117, 114, 116),
         (116, 120, 115, 117),     # 18: pivot high 120
         (117, 118, 100, 101), (101, 102, 95, 96),
         (93, 93, 91, 93),         # 21: the lowest low 91; high exactly 93
         (93, 100, 93, 99),
         (99, 110, 98, 109),       # 23: the pivot high 120 is confirmed
         (109, 119, 108, 118),
         (118, 122, 117, 121)]     # 25: close 121 > 120, close[1] 118 <= 120: a break, pivot bar 18
    row, outs = run_row(a + b)
    assert outs[25]["bull_break"] and outs[25]["new_ob"] == 0 and outs[25]["ob_rejected"] == 1
    assert zones(row.calcOrderBlock.obs) == [(1, 108.0, 93.0, 11)]
    assert all(outs[k]["n_ob"] == 1 for k in range(12, 26))
    assert O.has_overlapping_ob(1, 93.0, 91.0, row.calcOrderBlock.obs)          # touching
    assert not O.has_overlapping_ob(1, 92.999, 91.0, row.calcOrderBlock.obs)
    assert not O.has_overlapping_ob(-1, 100.0, 95.0, row.calcOrderBlock.obs)    # other direction: never
    # (c) the cap of the search: a break 61 bars after the pivot searches bars b-50..b only (51 bars)
    c = [(100, 101, 99, 100), (100, 102, 99, 101), (101, 103, 100, 102), (102, 104, 101, 103), (103, 105, 102, 104),
         (104, 110, 99, 105)]                                                  # 5: pivot high 110
    c += [(100, 101, 99, 100)] * 60                                           # bars 6..65
    c[15] = (100, 101, 80, 100)                                                # bar 15: low 80, = b - 51: outside
    c[16] = (100, 101, 85, 100)                                                # bar 16: low 85, = b - 50: inside
    c += [(100, 112, 99.5, 111)]                                               # bar 66: the break
    row, outs = run_row(c)
    assert outs[66]["bull_break"] and outs[66]["new_ob"] == 1
    assert zones(row.calcOrderBlock.obs) == [(1, 101.0, 85.0, 16)]             # an uncapped window: bar 15, 80
    # (d) the new pivot is stored BEFORE the break test: an unbroken pivot high 100 (bar 5) is replaced by 120
    # (bar 15, a shooting star) on bar 20, the very bar whose close (105) first crosses 100: no break at all
    d = [(90, 91, 89, 90), (90, 92, 89, 91), (91, 93, 90, 92), (92, 94, 91, 93), (93, 95, 92, 94),
         (94, 100, 93, 95),                                                    # 5: pivot high 100
         (95, 99, 94, 96), (96, 98, 95, 97), (97, 97.5, 94, 95), (95, 96, 93, 94), (94, 95, 92, 93),
         (93, 94, 91, 92), (92, 95, 91, 94), (94, 97, 93, 96), (96, 98, 95, 97),
         (97, 120, 96, 98),                                                    # 15: pivot high 120, close 98
         (98, 99, 96, 97), (97, 99, 95, 96), (96, 99.5, 95, 98), (98, 99.8, 97, 99),
         (99, 106, 98, 105)]                                                   # 20: close 105 > 100, close[1] 99
    _, outs = run_row(d)
    assert outs[10]["pivot_high"] == 100.0 and outs[20]["pivot_high"] == 120.0
    assert not any(o["bull_break"] for o in outs)                              # testing first would break 100 here
    # (e) the earliest break is 6 bars after the pivot bar: the same first 11 bars, then a close of 101 on bar 11;
    # barsBack = 11 - 5 - 1 = 5: bars 11..6, lows 92.5 92 93 94 95 94 -> bar 10 (high 95)
    row, outs = run_row(d[:11] + [(93, 102, 92.5, 101)])
    assert [k for k, o in enumerate(outs) if o["bull_break"]] == [11]
    assert zones(row.calcOrderBlock.obs) == [(1, 95.0, 92.0, 10)]
    # (f) each pivot is used once: after the break, closes above 110 again break nothing until a new pivot high
    row, outs = run_row(a + [(111, 113, 110, 112), (112, 112.5, 108, 108.5), (108.5, 113, 108, 112)])
    assert [k for k, o in enumerate(outs) if o["bull_break"]] == [12]


def test_trap06_fvg_pattern_on_bars_1_to_3_and_green_includes_close_above_prev_close():
    # candles 0, 1, 2 make the gap (low of 2 = 102 > high of 0 = 101); it is SEEN on bar 3 ([1]..[3]), not on bar 2
    ohlc = [(100, 101, 99, 100.5), (100.5, 104, 100, 103.5), (103.5, 105, 102, 104.5), (104.5, 106, 103, 105.5)]
    row, outs = run_row(ohlc)
    assert [o["new_fvg"] for o in outs] == [0, 0, 0, 1]
    assert zones(row.calcFVG.fvgs) == [(1, 102.0, 101.0, 0)]                   # top low[1], bottom high[3], bar - 3
    assert outs[3]["fvg_dir"] == 1 and outs[3]["fvg_dist"] == 102.0 - 105.5
    # the middle candle may have a RED body: _green is close > open OR close > close[1] (103 > 100)
    red_body = [(100, 101, 99, 100), (104, 104.5, 100.5, 103), (103, 105, 102, 104.5), (104.5, 106, 103, 105)]
    _, outs = run_row(red_body)
    assert outs[3]["new_fvg"] == 1                                             # "close > open" alone: no gap
    # the middle candle must make the gap alone: low[1] < high[2] and low[2] < high[3]
    double_gap = [(100, 101, 99, 100.5), (100.5, 104, 100, 103.5), (104.5, 106, 104.5, 105.5), (105.5, 107, 105, 106)]
    assert run_row(double_gap)[1][3]["new_fvg"] == 0                           # low of 2 (104.5) >= high of 1 (104)
    early_gap = [(100, 101, 99, 100.5), (101.5, 104, 101.5, 103.5), (103.5, 105, 102, 104.5), (104.5, 106, 103, 105.5)]
    assert run_row(early_gap)[1][3]["new_fvg"] == 0                            # low of 1 (101.5) >= high of 0 (101)
    # a not-green middle candle (red body, close below the previous close): no gap
    red_mid = [(100, 101, 99, 100.5), (103.5, 104, 100, 100.4), (103.5, 105, 102, 104.5), (104.5, 106, 103, 105.5)]
    assert run_row(red_mid)[1][3]["new_fvg"] == 0
    # the bearish mirror: high of 2 (98) < low of 0 (99), the middle candle red by its close (96.5 < 99.5) with a
    # GREEN body (96 -> 96.5): seen on bar 3, top = low[3] = 99, bottom = high[1] = 98
    bear = [(100, 101, 99, 99.5), (96, 99.5, 95, 96.5), (96.5, 98, 94, 95), (95, 97, 93, 94)]
    row, outs = run_row(bear)
    assert [o["new_fvg"] for o in outs] == [0, 0, 0, -1]
    assert zones(row.calcFVG.fvgs) == [(-1, 99.0, 98.0, 0)] and outs[3]["fvg_dir"] == -1
    assert outs[3]["fvg_dist"] == 98.0 - 94.0                                  # bottom - close


def test_trap07_nearest_zone_sentinel_and_ties_go_bearish():
    Z = O.ZoneBlock
    assert O.find_nearest_zone([], 100.0) == (0, 0.0)
    assert O.find_nearest_zone([Z(1, 99.0, 98.0, 0)], 100.0) == (1, -1.0)
    # a bull / bear tie (|95 - 100| == |105 - 100|) is bearish (the first test is strict)
    assert O.find_nearest_zone([Z(1, 95.0, 94.0, 0), Z(-1, 106.0, 105.0, 0)], 100.0) == (-1, 5.0)
    assert O.find_nearest_zone([Z(1, 95.01, 94.0, 0), Z(-1, 106.0, 105.0, 0)], 100.0)[0] == 1
    # within a side the newest zone (index 0) wins a tie: tops 99 (newest) and 101 are both 1 away
    assert O.find_nearest_zone([Z(1, 99.0, 98.0, 1), Z(1, 101.0, 100.5, 0)], 100.0) == (1, -1.0)
    assert O.find_nearest_zone([Z(1, 101.0, 100.5, 1), Z(1, 99.0, 98.0, 0)], 100.0) == (1, 1.0)
    # the 100000.0 sentinel: a bullish top 100000.01 below a $150,000 close is invisible; so is one exactly 100000
    # below (strict <); a bearish zone then decides
    assert O.find_nearest_zone([Z(1, 49999.99, 49000.0, 0)], 150000.0) == (0, 0.0)
    assert O.find_nearest_zone([Z(1, 50000.0, 49000.0, 0)], 150000.0) == (0, 0.0)
    assert O.find_nearest_zone([Z(1, 50000.01, 49000.0, 0)], 150000.0)[0] == 1
    assert O.find_nearest_zone([Z(1, 49999.99, 49000.0, 0), Z(-1, 170000.0, 160000.0, 0)], 150000.0) == (-1, 10000.0)
    # inside a zone or far from it, only the direction counts
    assert O.find_nearest_zone([Z(1, 120.0, 80.0, 0)], 100.0) == (1, 20.0)


def test_trap08_strict_thresholds_and_inactive_rows_out_of_max_score():
    assert (O.max_score_of("1H"), O.max_score_of("4H"), O.max_score_of("1D")) == (44, 36, 28)
    # exactly 50% is LEAN, not BULLISH; the first LEAN point is p > m / 5
    assert [O.label_of(p, 44) for p in (23, 22, 9, 8, 0, -8, -9, -22, -23)] == [2, 1, 1, 0, 0, 0, -1, -1, -2]
    assert [O.label_of(p, 36) for p in (19, 18, 8, 7, -7, -8, -18, -19)] == [2, 1, 1, 0, 0, -1, -1, -2]
    assert [O.label_of(p, 28) for p in (15, 14, 6, 5, -5, -6, -14, -15)] == [2, 1, 1, 0, 0, -1, -1, -2]
    for m in (44, 36, 28):                       # every reachable score: the integer rule is the float rule
        for p in range(-m, m + 1):
            pct = p / m * 100
            want = 2 if pct > 50 else 1 if pct > 20 else -2 if pct < -50 else -1 if pct < -20 else 0
            assert O.label_of(p, m) == want
    with pytest.raises(ValueError):
        O.label_of(0, 0)
    # inactive rows: a 4H chart has no 1H row, needs none, and its maximum is 36 (4H, D, W); a 1D chart: 28
    b1 = walk_bars(hours("btc", 3, t0=MON0), 1, symbol="BTCUSDm")
    rows = rows_of(b1)
    out4 = O.structure_dashboard({k: v for k, v in rows.items() if k != "1H"}, "4H")
    assert set(out4) == contract_keys("4H") and "s_1H" not in out4
    assert np.all(out4["max_score"] == 36)
    out1 = O.structure_dashboard({"1D": rows["1D"], "1W": rows["1W"]}, "1D")
    assert set(out1) == contract_keys("1D") and np.all(out1["max_score"] == 28)
    # a row before its first closed bar scores 0 and still counts: the first weekly bar closes with day 7 of the data
    first_w = int(rows["1W"].tc[0])
    early = rows["1D"].tc < first_w
    assert first_w == MON0 + WEEK and early.sum() == 6
    assert np.all(out1["s_1W"][early] == 0) and np.all(out1["max_score"][early] == 28)
    assert np.all(out1["swing_1W"][early] == 0) and np.all(out1["struct_1W"][early] == 0)


def test_trap09_merge_at_tc_le_T_and_the_weekly_bar_definition():
    # the merge: the 4H row's values appear on the 1H bar that closes WITH the 4H bar (tc_4H <= tc_1H), not an hour
    # earlier, and equal tradeiq_market.htf_at
    b1 = walk_bars(hours("gold", 8), 2, decimals=1)
    rows = rows_of(b1)
    out = O.structure_dashboard(rows, "1H")
    for r in ("4H", "1D", "1W"):
        st = O.calc_all(rows[r])
        for f, key in (("struct", "struct"), ("ob", "ob_dir"), ("fvg", "fvg_dir")):
            want = TM.htf_at(rows[r], st[key].astype(float), rows["1H"], default=0.0)
            assert np.array_equal(out[f"{f}_{r}"], want.astype(np.int8)), (r, f)
        sh = TM.htf_at(rows[r], st["swing_h"], rows["1H"])
        sl = TM.htf_at(rows[r], st["swing_l"], rows["1H"])
        tick = O.MINTICK["XAUUSDm"]
        sw = [O.swing_bias_dir(a, b, c, tick) for a, b, c in zip(sh, sl, rows["1H"].c)]
        assert out[f"swing_{r}"].tolist() == sw, r
    st4 = O.calc_all(rows["4H"])
    r1, r4 = rows["1H"], rows["4H"]
    seen = 0
    for k in np.flatnonzero(np.diff(st4["struct"]) != 0) + 1:                 # 4H bars where the structure changes
        idx = np.flatnonzero(r1.tc == r4.tc[k])                                # the 1H bar closing with it
        if len(idx) == 0 or r1.t[idx[0] - 1] < r4.t[k]:
            continue                                                           # (a Friday 20:00 4H bar has none)
        i = int(idx[0])
        assert out["struct_4H"][i] == st4["struct"][k]                         # visible at T == tc_4H ...
        assert out["struct_4H"][i - 1] == st4["struct"][k - 1]                 # ... not one hour earlier
        seen += 1
    assert seen >= 3
    # weekly bars from external.day_bars on M1 minutes (gold): Sunday stubs (120 M1 bars) merge into Monday and
    # start the new week; the week of 14 Jan has a short Friday (300 M1 bars) that merges, with the next Sunday
    # stub, into Monday 21 Jan, and so belongs to the following week
    mins = []
    for w in range(3):
        sun = SUN0 + w * WEEK
        mins += [sun + 22 * H + 60 * m for m in range(120)]                                  # Sunday 22:00-24:00
        for d in range(1, 5):
            mins += [sun + d * DAY + 60 * m for m in range(1440) if not (21 * 60 <= m < 22 * 60)]
        fri = sun + 5 * DAY
        mins += [fri + 60 * m for m in range(300 if w == 1 else 1260)]
    mins += [SUN0 + 3 * WEEK + 22 * H + 60 * m for m in range(120)]                           # a 4th Sunday stub
    mins += [SUN0 + 3 * WEEK + DAY + 60 * m for m in range(1440)]                             # and its Monday
    t = np.asarray(sorted(mins), np.int64)
    px = 1000.0 + 0.001 * np.arange(len(t))
    mk = X.Market("XAUUSDm", {"t": t, "o": px, "h": px + 0.0005, "l": px - 0.0005, "c": px,
                              "spread_mean": np.full(len(t), 0.1), "n": np.ones(len(t))})
    d = X.day_bars(mk)
    w = O.weekly_bars(d)
    jan = lambda day: TM.s_of(f"2019-01-{day:02d}")                                           # noqa: E731
    assert w.tc.tolist() == [jan(12), jan(18), jan(26), jan(29)]
    assert w.t.tolist() == [jan(6), jan(13), jan(18), jan(27)]
    assert len(d) == 15 and w.d0.tolist() == [0, 5, 9, 14] and w.d1.tolist() == [4, 8, 13, 14]
    assert w.o[0] == px[0] and w.c[1] == d.c[8] and w.h[2] == max(d.h[9:14]) and w.l[2] == min(d.l[9:14])
    # the alternative reading, the week of the day bar's OPEN time, would put the Sunday-opened Monday bars into the
    # previous week; ours puts them in the week they close in
    assert O.iso_week_of(int(d.t[5])) == (2019, 2) and O.iso_week_of(int(d.tc[5]) - 1) == (2019, 3)
    # BTC: every day full, weeks from Monday 00:00 to Monday 00:00 UTC
    tb = np.arange(MON0, MON0 + 2 * WEEK, 60, dtype=np.int64)
    pb = 4000.0 + 0.01 * np.arange(len(tb))
    mb = X.Market("BTCUSDm", {"t": tb, "o": pb, "h": pb, "l": pb, "c": pb, "spread_mean": np.full(len(tb), 1.0),
                              "n": np.ones(len(tb))})
    wb = O.weekly_bars(X.day_bars(mb))
    assert wb.t.tolist() == [MON0, MON0 + WEEK] and wb.tc.tolist() == [MON0 + WEEK, MON0 + 2 * WEEK]


def test_trap10_inverted_ranges_collapse_to_one_tick():
    # a pivot low 100 (bar 5), a crash to a floor of equal lows (90: ties, so no new pivot low), and a pivot high 95
    # on bar 18, confirmed on bar 23: swingH 95 < swingL 100
    ohlc = [(106, 107, 105, 106), (105, 106, 104, 105), (104, 105, 103, 104), (103, 104, 102, 103),
            (102, 103, 101, 102), (101, 102, 100, 101),                                   # 5: pivot low 100
            (101, 103, 101.5, 102), (102, 104, 102, 103), (103, 105, 102.5, 104), (104, 106, 103, 105),
            (105, 107, 104, 106),                                                         # 10: pivot high 107
            (106, 106, 91, 92), (92, 93, 90, 91), (91, 92, 90, 91), (91, 93, 90, 92), (92, 93.5, 90, 93),
            (93, 94, 90, 93), (93, 94.5, 90, 94),
            (94, 95, 90, 94.5),                                                           # 18: high 95
            (94.5, 94.5, 90, 94), (94, 94, 90, 93), (93, 93.5, 90, 92), (92, 93, 90, 91), (91, 92, 90, 91.5)]
    _, outs = run_row(ohlc)
    assert outs[10]["pivot_low"] == 100.0 and outs[15]["pivot_high"] == 107.0 and outs[23]["pivot_high"] == 95.0
    assert outs[23]["swing_h"] == 95.0 and outs[23]["swing_l"] == 100.0
    # swingRange = max(95 - 100, 0.001) = 0.001: the factor is the side of swingL (100) the close is on
    tick = 0.001
    assert O.swing_bias_dir(95.0, 100.0, 91.5, tick) == -1                     # below swingL
    assert O.swing_bias_dir(95.0, 100.0, 100.0, tick) == 1                     # 0%: the "discount" end
    assert O.swing_bias_dir(95.0, 100.0, 100.0005, tick) == 0                  # ~50% of one tick
    assert O.swing_bias_dir(95.0, 100.0, 100.0008, tick) == -1                 # ~80%
    assert O.swing_bias_dir(95.0, 100.0, 100.002, tick) == 1                   # above swingL + 1 tick
    assert O.swing_bias_dir(95.0, 100.0, 100.005, 0.01) == 0                   # BTC's tick: 50%
    assert O.swing_bias_dir(100.0, 100.0, 100.0, tick) == 1                    # a flat range is one tick too


def test_trap11_outside_bar_is_both_pivot_high_and_pivot_low():
    # pivots H1 105 (bar 5) and L1 95 (bar 11), then bar 22 with the highest high (110) AND the lowest low (90) of
    # bars 17..27: on bar 27 both pivots arrive, and both sides of every tracker update on that one bar
    hl = [(101, 99), (102, 99.5), (103, 100), (103.5, 100.5), (104, 101), (105, 101.5),        # 5: H1 105
          (104, 100), (103, 99), (102, 98), (101, 97), (100.5, 96.5), (100, 95),              # 11: L1 95
          (101, 96), (102, 97), (102.5, 97.5), (103, 98), (103.5, 98.5), (103.5, 98),         # 16-17: equal highs
          (102.5, 97.5), (102, 97), (101.5, 96.6), (101, 96.2),
          (110, 90),                                                                          # 22: the outside bar
          (104, 96), (103, 96.5), (102, 97), (101.5, 97.5), (101, 98)]
    ohlc = [((h + lo) / 2, h, lo, (h + lo) / 2) for h, lo in hl]
    row, outs = run_row(ohlc)
    ph = [k for k, o in enumerate(outs) if not is_nan(o["pivot_high"])]
    pl = [k for k, o in enumerate(outs) if not is_nan(o["pivot_low"])]
    assert ph == [10, 27] and pl == [16, 27]
    assert outs[27]["pivot_high"] == 110.0 and outs[27]["pivot_low"] == 90.0
    assert outs[27]["swing_h"] == 110.0 and outs[27]["swing_l"] == 90.0
    # calcStructure: 110 > 105 is HH (+1) and 90 < 95 is LL (-1) on the same bar: mixed structure 0
    assert outs[26]["high_type"] == 0 and outs[26]["low_type"] == 0
    assert outs[27]["high_type"] == 1 and outs[27]["low_type"] == -1 and outs[27]["struct"] == 0
    # trackPivotBreaks keeps both levels of the same bar (an if/elif port would lose one)
    p = row.calcOrderBlock.pivot
    assert (p.lastPH, p.lastPHBar, p.lastPL, p.lastPLBar) == (110.0, 22, 90.0, 22)
    assert row.calcSwingHL.swing.prevH == 105.0 and row.calcSwingHL.swing.prevL == 95.0


# ───────────────────────────── 2. the spec's other cases and second formulations ─────────────────────────────

def test_swing_factor_points():
    tick = 0.001
    sw = lambda c: O.swing_bias_dir(110.0, 100.0, c, tick)                    # noqa: E731
    assert [sw(c) for c in (100.0, 102.9, 103.0, 105.0, 107.0, 107.1, 110.0, 110.001, 99.999)] == \
        [1, 1, 0, 0, 0, -1, -1, 1, -1]                                         # 0%, <30, 30, 50, 70, >70, 100, >100, <0
    assert O.swing_bias_dir(nan, 100.0, 105.0, tick) == 0 and O.swing_bias_dir(110.0, nan, 105.0, tick) == 0
    assert O.swing_bias_dir(nan, nan, 105.0, tick) == 0
    assert O.dir_score(nan) == 0 and O.dir_score(3) == 1 and O.dir_score(-2) == -1 and O.dir_score(0) == 0


def test_contract_keys_dtypes_and_model_b_refused():
    b1 = walk_bars(hours("gold", 4), 3, decimals=2)
    rows = rows_of(b1)
    for chart in O.CHARTS:
        out = O.structure_dashboard(rows, chart, model="A")
        n = len(rows[chart].tc)
        assert set(out) == contract_keys(chart)
        assert all(len(v) == n for v in out.values())
        for k in ("label", "bos", "bos_trend") + tuple(f"{f}_{r}" for r in O.active_rows(chart)
                                                       for f in ("struct", "ob", "fvg", "swing")):
            assert out[k].dtype == np.int8, k
        for k in ("score", "max_score") + tuple(f"s_{r}" for r in O.active_rows(chart)):
            assert out[k].dtype == np.int64, k
    with pytest.raises(ValueError):
        O.structure_dashboard(rows, "1H", model="B")
    with pytest.raises(ValueError):
        O.structure_dashboard(rows, "1W")
    with pytest.raises(ValueError):
        O.structure_dashboard({"1D": rows["1D"]}, "1D")                        # the W row is missing
    nosym = {k: NS(t=v.t, tc=v.tc, o=v.o, h=v.h, l=v.l, c=v.c) for k, v in rows.items()}
    with pytest.raises(ValueError):
        O.structure_dashboard(nosym, "1D")                                     # no mintick known
    a = O.structure_dashboard(nosym, "1D", mintick=0.001)
    b = O.structure_dashboard(rows, "1D")
    assert all(np.array_equal(a[k], b[k]) for k in a)
    assert all(O.MINTICK[s] == 10.0 ** -C.SYMBOLS[s].digits for s in ("XAUUSDm", "BTCUSDm"))


def test_bos_and_bos_trend_follow_the_chart_rows_breaks():
    b1 = walk_bars(hours("btc", 6), 4, symbol="BTCUSDm")
    rows = rows_of(b1)
    out = O.structure_dashboard(rows, "1H")
    st = O.calc_all(rows["1H"])
    assert np.array_equal(out["bos"], st["bull_break"].astype(np.int8) - st["bear_break"].astype(np.int8))
    assert (out["bos"] != 0).sum() > 10
    side, want = 0, []
    for v in out["bos"]:
        side = v if v != 0 else side
        want.append(side)
    first = int(np.flatnonzero(out["bos"])[0])
    assert out["bos_trend"].tolist() == want and first > 10 and np.all(out["bos_trend"][:first] == 0)


def test_second_formulations_pivots_and_fvg_patterns():
    """numpy formulations, written separately, of the pivots (strict and the tie readings) and the FVG patterns."""
    for seed, dec in ((5, 1), (6, None)):
        b = walk_bars(np.arange(3000, dtype=np.int64) * H + T0, seed, decimals=dec)
        st = O.calc_all(b)
        n = len(b.c)
        w = np.lib.stride_tricks.sliding_window_view
        for kind, src in (("high", b.h), ("low", b.l)):
            win = w(src, 11)                                                   # bars k-10 .. k, k = 10 .. n-1
            cen = win[:, 5]
            older, newer = win[:, :5], win[:, 6:]
            for ties in O.TIES:
                eq_o = ties in ("ties_left", "ties_both")
                eq_n = ties in ("ties_right", "ties_both")
                if kind == "high":
                    ok = (np.all(cen[:, None] >= older, 1) if eq_o else np.all(cen[:, None] > older, 1)) & \
                         (np.all(cen[:, None] >= newer, 1) if eq_n else np.all(cen[:, None] > newer, 1))
                else:
                    ok = (np.all(cen[:, None] <= older, 1) if eq_o else np.all(cen[:, None] < older, 1)) & \
                         (np.all(cen[:, None] <= newer, 1) if eq_n else np.all(cen[:, None] < newer, 1))
                want = np.full(n, nan)
                want[10:] = np.where(ok, cen, nan)
                got = O.calc_all(b, ties=ties)[f"pivot_{kind}"] if ties != "strict" else st[f"pivot_{kind}"]
                assert np.array_equal(np.isnan(got), np.isnan(want)) and np.array_equal(got[~np.isnan(got)],
                                                                                      want[~np.isnan(want)])
        o, h, lo, c = b.o, b.h, b.l, b.c
        green = (c > o) | (c > np.r_[nan, c[:-1]])
        red = (c < o) | (c < np.r_[nan, c[:-1]])
        k = np.arange(3, n)
        bull = (lo[k - 1] > h[k - 3]) & green[k - 2] & (lo[k - 1] < h[k - 2]) & (lo[k - 2] < h[k - 3])
        bear = (h[k - 1] < lo[k - 3]) & red[k - 2] & (h[k - 1] > lo[k - 2]) & (h[k - 2] > lo[k - 3])
        want = np.zeros(n, np.int8)
        want[3:] = np.where(bull, 1, np.where(bear, -1, 0))
        assert np.array_equal(st["new_fvg"], want) and (want != 0).sum() > 50
        if dec is not None:
            assert (O.calc_all(b, ties="ties_both")["pivot_high"] >= 0).sum() > (st["pivot_high"] >= 0).sum()


def test_weekly_bars_equal_a_pandas_groupby():
    b1 = walk_bars(hours("gold", 12), 7)
    d1 = d1_of(b1)
    w = O.weekly_bars(d1)
    f = pd.DataFrame({"t": d1.t, "tc": d1.tc, "o": d1.o, "h": d1.h, "l": d1.l, "c": d1.c})
    iso = pd.to_datetime(f.tc - 1, unit="s", utc=True).dt.isocalendar()
    f["wk"] = iso.year * 100 + iso.week
    g = f.groupby("wk", sort=True).agg(t=("t", "first"), tc=("tc", "last"), o=("o", "first"), h=("h", "max"),
                                       l=("l", "min"), c=("c", "last"))
    for k in ("t", "tc", "o", "h", "l", "c"):
        assert np.array_equal(getattr(w, k), g[k].to_numpy()), k
    assert len(w) == 12


def test_weekly_bars_a_forming_last_week_closes_at_its_iso_end():
    # Added at the reconciliation with port A (tests/test_tradeiq2_ind_msd.py). 24/7 day bars Monday 7 .. Wednesday 23
    # January 2019: two full ISO weeks (7-13 and 14-20 Jan) and a forming one (Mon 21 - Wed 23). With the data end
    # Thursday 24 Jan 00:00 that week can still receive Thursday .. Sunday, so it closes at its ISO end (Monday 28 Jan
    # 00:00) and is not complete; its open, high, low and close so far are kept, and the full weeks do not change.
    jan = lambda day: TM.s_of(f"2019-01-{day:02d}")                                           # noqa: E731
    t = MON0 + DAY * np.arange(17, dtype=np.int64)
    px = 100.0 + np.arange(17, dtype=np.float64)
    d1 = NS(t=t, tc=t + DAY, o=px, h=px + 1.0, l=px - 1.0, c=px + 0.5, symbol="BTCUSDm")
    w = O.weekly_bars(d1, end_s=jan(24))
    assert w.t.tolist() == [jan(7), jan(14), jan(21)] and w.tc.tolist() == [jan(14), jan(21), jan(28)]
    assert w.complete.tolist() == [True, True, False]
    assert (w.o[-1], w.h[-1], w.l[-1], w.c[-1]) == (114.0, 117.0, 113.0, 116.5)    # days 21-23: px 114, 115, 116
    # data that end at (or after) the week's end, or no end given: every week complete, the last one closing with its
    # last day bar (Thursday 00:00)
    for end in (None, jan(28), jan(29)):
        w2 = O.weekly_bars(d1, end_s=end)
        assert w2.tc.tolist() == [jan(14), jan(21), jan(24)] and w2.complete.all(), end
    # model A (tc_row <= tc_chart): on the last day bar (closing Thursday 00:00) the W row shows the week of 14 Jan
    # with the data end given, and would show the forming week without it
    assert TM.htf_at(w, np.arange(3.0), d1)[-1] == 1.0
    assert TM.htf_at(O.weekly_bars(d1), np.arange(3.0), d1)[-1] == 2.0


def test_inputs_left_alone():
    b1 = walk_bars(hours("gold", 3), 8)
    rows = rows_of(b1)
    keep = {r: [getattr(b, k).copy() for k in ("t", "tc", "o", "h", "l", "c")] for r, b in rows.items()}
    O.structure_dashboard(rows, "1H")
    for r, b in rows.items():
        assert all(np.array_equal(a, getattr(b, k)) for a, k in zip(keep[r], ("t", "tc", "o", "h", "l", "c")))


# ───────────────────────────── 3. truncation invariance ─────────────────────────────

def _closed_at(rows, T):
    """Every row cut to its bars closed at or before T (what model A may know at T)."""
    return {r: NS(t=b.t[b.tc <= T], tc=b.tc[b.tc <= T], o=b.o[b.tc <= T], h=b.h[b.tc <= T], l=b.l[b.tc <= T],
                  c=b.c[b.tc <= T], symbol=b.symbol) for r, b in rows.items()}


def _with_forming(rows, b1, T):
    """As ``_closed_at``, plus each higher-timeframe row's forming bar built from the 1H bars that closed by T
    (its scheduled close is after T: model A must not use it)."""
    out = _closed_at(rows, T)
    for r in ("4H", "1D", "1W"):
        b = rows[r]
        k = int(np.searchsorted(b.tc, T, side="right"))                        # the first bar not closed at T
        if k >= len(b.tc):
            continue
        inside = (b1.t >= b.t[k]) & (b1.tc <= T)
        if not inside.any():
            continue
        x = out[r]
        out[r] = NS(t=np.r_[x.t, b.t[k]], tc=np.r_[x.tc, b.tc[k]], o=np.r_[x.o, b1.o[inside][0]],
                    h=np.r_[x.h, b1.h[inside].max()], l=np.r_[x.l, b1.l[inside].min()], c=np.r_[x.c, b1.c[inside][-1]],
                    symbol=b.symbol)
    return out


@pytest.mark.parametrize("kind,seed", [("gold", 11), ("btc", 12)])
def test_truncation_invariance(kind, seed):
    b1 = walk_bars(hours(kind, 30), seed, decimals=1, symbol="XAUUSDm" if kind == "gold" else "BTCUSDm")
    rows = rows_of(b1)
    rng = np.random.default_rng(seed)
    for chart in O.CHARTS:
        full = O.structure_dashboard(rows, chart)
        assert (full["bos"] != 0).sum() > 0 and len(np.unique(full["label"])) >= 3
        tc = rows[chart].tc
        picks = set(rng.integers(30, len(tc) - 1, 4).tolist()) | {len(tc) // 2}
        if chart == "1H":                                                      # a Friday's last bar, a Sunday bar
            dow = (rows["1H"].t // DAY + 3) % 7
            picks |= {int(np.flatnonzero(dow == 4)[-1]), int(np.flatnonzero(dow == 6)[-1])}
        for i in sorted(picks):
            T = int(tc[i])
            for part in (_closed_at(rows, T), _with_forming(rows, b1, T)):
                got = O.structure_dashboard(part, chart)
                for k, v in full.items():
                    assert len(got[k]) == i + 1 and np.array_equal(got[k], v[:i + 1]), (kind, chart, i, k)


# ───────────────────────────── 4. the real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H / 1D bars of a symbol from its data start to 2024-07-01 00:00 UTC (exclusive) with study 1's
    hold-out guard pointed at an empty folder, plus the weekly bars."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end=TM.HOLDOUT_START)
                bars = {tf: mk.tbars(tf) for tf in ("1H", "4H", "1D")}
            del mk
            bars["1W"] = O.weekly_bars(bars["1D"])
            cache[symbol] = bars
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    rows = real(symbol)
    for b in rows.values():
        assert int(b.tc[-1]) <= TM.CUT_S                                       # nothing from the hold-out
    assert rows["1W"].symbol == symbol and int(rows["1W"].tc[-1]) == int(rows["1D"].tc[-1])
    assert np.all(rows["1W"].d0[1:] == rows["1W"].d1[:-1] + 1) and int(rows["1W"].d1[-1]) == len(rows["1D"].tc) - 1
    states = {r: O.calc_all(rows[r]) for r in O.ROWS}
    for chart in O.CHARTS:
        out = O.structure_dashboard(rows, chart)
        n = len(rows[chart].tc)
        m = O.max_score_of(chart)
        assert set(out) == contract_keys(chart) and all(len(v) == n for v in out.values())
        for k, v in out.items():
            assert np.all(np.isfinite(v.astype(np.float64))), (chart, k)       # every value exists
        assert np.all(out["max_score"] == m)
        assert np.all(np.abs(out["score"]) <= m) and set(np.unique(out["label"])) <= {-2, -1, 0, 1, 2}
        pts = np.zeros(n, np.int64)
        for r in O.active_rows(chart):
            fac = [out[f"{f}_{r}"].astype(np.int64) for f in ("struct", "ob", "fvg", "swing")]
            assert all(set(np.unique(x)) <= {-1, 0, 1} for x in fac)
            assert np.array_equal(out[f"s_{r}"], sum(fac))
            pts += O.WEIGHT[r] * out[f"s_{r}"]
            if r != chart:                                                     # model A = htf_at
                for f, key in (("struct", "struct"), ("ob", "ob_dir"), ("fvg", "fvg_dir")):
                    want = TM.htf_at(rows[r], states[r][key].astype(float), rows[chart], default=0.0)
                    assert np.array_equal(out[f"{f}_{r}"], want.astype(np.int8)), (chart, r, f)
            else:
                assert np.array_equal(out[f"struct_{r}"], states[r]["struct"])
        assert np.array_equal(out["score"], pts)
        assert np.array_equal(out["label"], [O.label_of(p, m) for p in out["score"]])
        assert set(np.unique(out["bos"])) <= {-1, 0, 1} and (out["bos"] != 0).sum() > 0
        assert len(np.unique(out["label"])) == 5                               # every label occurs
    # every row is warmed up before the scored windows: from 2019 on both swings exist and both sides of the
    # structure have two pivots (highType and lowType are +-1, never their starting 0)
    for r in O.ROWS:
        late = rows[r].tc >= TM.s_of("2019-01-01")
        st = states[r]
        assert late.sum() > 0 and np.all(np.isfinite(st["swing_h"][late])) and np.all(np.isfinite(st["swing_l"][late]))
        assert np.all(st["high_type"][late] != 0) and np.all(st["low_type"][late] != 0), r
    # a cut at one T (2021-06-15 12:00 UTC) changes nothing at or before it, on the 4H and 1D charts
    T = TM.s_of("2021-06-15 12:00")
    for chart in ("4H", "1D"):
        full = O.structure_dashboard(rows, chart)
        i = int(np.searchsorted(rows[chart].tc, T, side="right")) - 1
        part = O.structure_dashboard(_closed_at(rows, int(rows[chart].tc[i])), chart)
        for k, v in full.items():
            assert np.array_equal(part[k], v[:i + 1]), (symbol, chart, k)
