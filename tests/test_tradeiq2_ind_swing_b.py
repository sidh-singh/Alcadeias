"""
Port B (the oracle) of BigBeluga's Swing Profile, ``tests/tradeiq2_oracle_swing.py`` (study 2, PREREG 6.4).

1. One hand-computed test per trap of the spec's porting risks (``maps/orb_session_swing_ha.md`` 3.6 "Risks", nine
   items), named after it: ``ta.highest(len)`` reads ``high``; the strict ``<`` / ``>`` of the confirmation; the low
   winning on a bar that is both extremes; the bar span [prev, last]; the double counting into two bins; the ``int()``
   truncation; the ties; the ATR(200) taken at the flip bar; the naming (``isDownMove`` true finishes a DOWN leg).
   Each builds bars by hand (``swing_len = 3`` and ``atr_len = 1``, so that the ATR is the flip bar's true range and
   every number is exact in binary) and states the expected values with their arithmetic; where a wrong reading is
   easy to write, the test also shows that it gives another value.
2. The spec's other test cases (3.6 "Tests"): the top and bottom edges, a doji counts as sell, the skips (binCount 0,
   na ATR, a missing swing), the forming leg equal to the finished leg; and a test of each reading of the oracle's
   docstring that has a value (R1, R4, R5, R7-R11, R13, R15).
3. An independent vectorised formulation (closed forms for the swing state, study 1's oracle ATR, numpy bins), equal
   bit for bit with integer volumes; truncation invariance; the memo changes nothing.
4. Real bars (skipped when the tick store is absent): both symbols, the 1H / 4H bars PREREG 6.4 uses, from the data
   start to 2024-06-30 (study 1's guard pointed at an empty folder, so the hold-out cannot be served); gold with its
   tick volume, BTC with Binance's BTCUSDT volume (PREREG 2): it runs, every value the contract defines exists from
   2019 on, the invariants hold, the vectorised formulation agrees, and a cut at one T changes nothing before it.

Port A (``backtesting/research/tradeiq2_ind_swing.py``) was not read or imported; the two are compared later.
"""

from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest
from numpy.lib.stride_tricks import sliding_window_view

from backtesting.data import store
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_swing as O  # noqa: E402
import tradeiq_oracle as S1  # noqa: E402  (study 1's independent oracle: its ATR is the reference primitive)

nan = math.nan
SMALL = dict(swing_len=3, atr_len=1, bin_mult=0.5)       # the hand-made cases: binSize = true range of the bar / 2
FLOATS = ("hs_price", "ls_price", "f_lo", "f_hi", "f_poc", "f_delta_pct", "f_total")
INTS = ("hs_bar", "ls_bar", "f_poc_ties")                 # int64; f_dir is int8 (the reconciliation, porting/swing.md)
BOOLS = ("is_down_move", "flip")


# ───────────────────────────── helpers ─────────────────────────────

def bars(rows):
    """(o, h, l, c, v) arrays from rows of (o, h, l, c, v)."""
    a = np.asarray(rows, dtype=np.float64)
    return a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy(), a[:, 3].copy(), a[:, 4].copy()


def run(rows, **kw):
    o, h, l, c, v = bars(rows)
    return O.swing_profile(o, h, l, c, v, **{**SMALL, **kw})


def same(a, b) -> bool:
    """Bit-for-bit equality, NaN equal to NaN; dtypes must match."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    if a.dtype.kind == "f":
        return bool(np.array_equal(a.view(np.int64), b.view(np.int64)) or np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def same_legs(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return False
    for k in a.columns:
        if k == "poc_all":
            if [tuple(x) for x in a[k]] != [tuple(x) for x in b[k]]:
                return False
        elif not same(a[k].to_numpy(), b[k].to_numpy()):
            return False
    return True


def leg(r, flip_bar):
    L = r["legs"]
    row = L[L.flip_bar == flip_bar]
    assert len(row) == 1, (flip_bar, L.flip_bar.tolist())
    return row.iloc[0]


# The base path (swing_len 3, atr_len 1, bin_mult 0.5). Window highs H3 / lows L3 by hand:
#   bar  o      h      l      c       v     H3     L3     events
#   0   104    105    103    104     1000   na     na
#   1   104    104    101    102     1000   na     na
#   2   102    102    100    101       10   105    100    low == L3: isDownMove false (already)
#   3   101    103    101    102.5     20   104    100    low[1] == L3[1] and 101 > 100: swing low (2, 100) stored
#   4   103    105    102    104.5     30   105    100    high == H3: true -> FLIP (down leg; no swing high yet)
#   5   105    107    104    106.75    40   107    101    a new high; 107 < 107 is false: bar 4 not confirmed
#   6   108    109    106    108       50   109    102    a new high; bar 5 not confirmed (doji: c == o)
#   7   108    108    105    106.5   1000   109    104    108 < 109: swing high (6, 109) stored
#   8   106    106.5  104.5  105     1000   109    104.5  low == L3: false -> FLIP: the UP leg 2..6 is finished
#   9   103.5  105.5  103    103.75    60   108    103    a new low; 103 > 103 false: bar 8 not confirmed
#   10  103.5  104    102    102.25    70   106.5  102    a new low; bar 9 not confirmed
#   11  102.5  104.5  102.5  104       80   105.5  102    102.5 > 102: swing low (10, 102) stored
#   12  104    106    104    105.5     90   106    102    high == H3: true -> FLIP: the DOWN leg 6..10 is finished
# True ranges: bar 4: max(3, |105 - 102.5|, |102 - 102.5|) = 3; bar 7: max(3, 0, 3) = 3; bar 8: max(2, 0, 2) = 2;
# bar 10: max(2, 0.25, 1.75) = 2; bar 12: max(2, 2, 0) = 2.
BASE = [(104, 105, 103, 104, 1000), (104, 104, 101, 102, 1000), (102, 102, 100, 101, 10),
        (101, 103, 101, 102.5, 20), (103, 105, 102, 104.5, 30), (105, 107, 104, 106.75, 40),
        (108, 109, 106, 108, 50), (108, 108, 105, 106.5, 1000), (106, 106.5, 104.5, 105, 1000),
        (103.5, 105.5, 103, 103.75, 60), (103.5, 104, 102, 102.25, 70), (102.5, 104.5, 102.5, 104, 80),
        (104, 106, 104, 105.5, 90)]


def variant(rows, **changes):
    """A copy of ``rows`` with bars replaced: ``variant(BASE, b8=(o, h, l, c, v))``."""
    out = [tuple(r) for r in rows]
    for k, x in changes.items():
        out[int(k[1:])] = tuple(x)
    return out


# ───────────────────────────── 0. the contract ─────────────────────────────

def test_contract_keys_dtypes_and_signature():
    sig = inspect.signature(O.swing_profile)
    assert list(sig.parameters) == ["o", "h", "l", "c", "v", "swing_len", "atr_len", "bin_mult"]
    assert (sig.parameters["swing_len"].default, sig.parameters["atr_len"].default,
            sig.parameters["bin_mult"].default) == (50, 200, 0.5)
    r = run(BASE)
    assert set(r) == set(O.KEYS) | {"legs"}
    for k in BOOLS:
        assert r[k].dtype == np.bool_ and r[k].shape == (13,), k
    for k in INTS:
        assert r[k].dtype == np.int64 and r[k].shape == (13,), k
    assert r["f_dir"].dtype == np.int8 and r["f_dir"].shape == (13,)
    for k in FLOATS:
        assert r[k].dtype == np.float64 and r[k].shape == (13,), k
    L = r["legs"]
    assert list(L.columns) == list(O.LEG_COLUMNS)
    assert [str(L[k].dtype) for k in O.LEG_COLUMNS] == \
        ["int64", "int8", "int64", "int64"] + ["float64"] * 3 + ["object"] + ["float64"] * 4
    empty = run(BASE[:2])                                       # no flip at all: an empty frame, same columns
    assert len(empty["legs"]) == 0 and list(empty["legs"].columns) == list(O.LEG_COLUMNS)


def test_inputs_refused():
    o, h, l, c, v = bars(BASE)
    bad_c = c.copy()
    bad_c[3] = nan
    with pytest.raises(ValueError):
        O.swing_profile(o, h, l, bad_c, v)
    with pytest.raises(ValueError):
        O.swing_profile(o, h, l, c, v[:-1])
    with pytest.raises(ValueError):
        O.swing_profile(o, h, l, c, -v)
    for kw in (dict(swing_len=0), dict(atr_len=2.5), dict(bin_mult=0.0), dict(bin_mult=nan)):
        with pytest.raises(ValueError):
            O.swing_profile(o, h, l, c, v, **kw)
    before = [x.copy() for x in (o, h, l, c, v)]
    O.swing_profile(o, h, l, c, v, **SMALL)
    assert all(same(x, y) for x, y in zip(before, (o, h, l, c, v)))       # the inputs are left alone


def test_base_path_by_hand():
    """Every per-bar value of the base path (the table above BASE), and its three legs."""
    r = run(BASE)
    F, T = False, True
    assert r["is_down_move"].tolist() == [F, F, F, F, T, T, T, T, F, F, F, F, T]
    assert np.flatnonzero(r["flip"]).tolist() == [4, 8, 12]
    assert r["hs_bar"].tolist() == [-1] * 7 + [6] * 6
    assert same(r["hs_price"], np.r_[[nan] * 7, [109.0] * 6])
    assert r["ls_bar"].tolist() == [-1] * 3 + [2] * 8 + [10] * 2
    assert same(r["ls_price"], np.r_[[nan] * 3, [100.0] * 8, [102.0] * 2])
    assert r["f_dir"].tolist() == [0] * 7 + [1] * 4 + [-1] * 2
    assert same(r["f_lo"], np.r_[[nan] * 7, [100.0] * 4, [102.0] * 2])
    assert same(r["f_hi"], np.r_[[nan] * 7, [109.0] * 6])
    # bar 7: TR 3 -> binSize 1.5 -> 9 / 1.5 = 6 bins of 1.5, midpoints 100.75 .. 108.25. Closes 101 -> bins 0, 1;
    # 102.5 -> 1, 2; 104.5 -> 2, 3; 106.75 (bin 4's midpoint: 1.5 away from 105.25 and 108.25, not < 1.5) -> 4;
    # 108 -> 4, 5. Bins [10, 30, 50, 30, 90, 50]: POC bin 4 = (106 + 107.5) / 2 = 106.75; total 260; buy (green
    # bars 3, 4, 5) 40 + 60 + 40 = 140, sell 20 + 100 = 120.
    assert (r["f_poc"][7], r["f_poc_ties"][7], r["f_total"][7]) == (106.75, 1, 260.0)
    assert r["f_delta_pct"][7] == (140.0 - 120.0) / 260.0
    # bar 8 (the flip) and bar 10: TR 2 -> 9 bins of 1, the up leg's profile (test_trap_double_counting_into_two_bins)
    for t in (8, 10):
        assert (r["f_poc"][t], r["f_poc_ties"][t], r["f_total"][t], r["f_delta_pct"][t]) == (107.5, 1, 250.0, 0.04)
    assert np.isnan(r["f_poc"][:7]).all() and (r["f_poc_ties"][:7] == 0).all() and np.isnan(r["f_total"][:7]).all()
    L = r["legs"]
    assert L.flip_bar.tolist() == [4, 8, 12] and L.dir.tolist() == [-1, 1, -1]
    assert L.start_bar.tolist() == [-1, 2, 6] and L.end_bar.tolist() == [-1, 6, 10]
    assert same(L.lo.to_numpy(), np.array([nan, 100.0, 102.0])) and same(L.hi.to_numpy(), np.array([nan, 109.0, 109.0]))
    assert same(L.fifty.to_numpy(), np.array([nan, 104.5, 105.5]))
    assert same(L.atr_at_flip.to_numpy(), np.array([3.0, 2.0, 2.0]))
    assert [tuple(x) for x in L.poc_all] == [(), (107.5,), (104.5,)]
    # the down leg 6..10 at bar 12, 7 bins of 1 from 102: closes 108 -> bins 5, 6 (50, doji: sell); 106.5 -> 4 only
    # (1000, sell); 105 -> 2, 3 (1000, sell); 103.75 -> 1, 2 (60, buy); 102.25 -> 0 only (70, sell).
    # Bins [70, 60, 1060, 1000, 1000, 50, 50]: POC bin 2 = 104.5; total 3290; buy 120, sell 3170.
    dn = leg(r, 12)
    assert (dn.poc, dn.total) == (104.5, 3290.0) and dn.delta_pct == (120.0 - 3170.0) / 3290.0
    up = leg(r, 8)
    assert (up.poc, up.total, up.delta_pct) == (107.5, 250.0, 0.04)


# ───────────────────────────── 1. the traps of the spec (3.6 "Risks") ─────────────────────────────

def test_trap_highest_reads_high():
    """``ta.highest(swingLen)`` / ``ta.lowest(swingLen)`` are the one-argument forms: they read high and low.
    Bar 3 is a shooting star (high 104 is the 3-bar high, its close 98 is not the highest close: 98.5 at bar 1); bar
    5 a hammer (low 96 is the 3-bar low, its close 102 is not the lowest close). With the closes read instead, the
    flips would be at bar 4 (close 102.5 = the highest close) and none at bar 5."""
    rows = [(100, 101, 99, 100, 1), (100, 101.5, 98, 98.5, 1), (98.5, 100, 97, 97.5, 1),
            (97.5, 104, 97.5, 98, 1), (99, 103, 99, 102.5, 1), (102.5, 103.5, 96, 102, 1)]
    r = run(rows)
    assert r["is_down_move"].tolist() == [False, False, False, True, True, False]
    assert np.flatnonzero(r["flip"]).tolist() == [3, 5]
    # the stored swing is the high (104), not the close (98): confirmed at bar 4 (103 < 104)
    assert r["hs_bar"].tolist() == [-1, -1, -1, -1, 3, 3] and r["hs_price"][4] == 104.0
    assert r["ls_bar"].tolist() == [-1, -1, -1, 2, 2, 2] and r["ls_price"][3] == 97.0
    # the up leg 2..3 finished at bar 5: TR 7.5 -> binSize 3.75 -> int(7 / 3.75) = 1 bin [97, 104], level 100.5;
    # both closes (97.5 red, 98 green) are within 7 of it: total 2, buy 1, sell 1
    up = leg(r, 5)
    assert (up.dir, up.start_bar, up.end_bar, up.lo, up.hi, up.poc, up.total, up.delta_pct, up.atr_at_flip) == \
        (1, 2, 3, 97.0, 104.0, 100.5, 2.0, 0.0, 7.5)
    c = bars(rows)[3]                                           # the close reading would flip elsewhere
    hc = np.r_[nan, nan, sliding_window_view(c, 3).max(axis=1)]
    assert c[3] != hc[3] and c[4] == hc[4]


def test_trap_strict_confirmation():
    """``high[1] == highestSwingHigh[1] and high < highestSwingHigh`` (l.75) and the mirror ``low > lowestSwingLow``
    (l.80): a swing is stored ONE bar after it prints, and not when the next high equals it. Bars 2 and 3 have the
    same high 102: bar 3 confirms nothing (102 < 102 is false), bar 4 (101.5) stores bar 3, the later of the two.
    Bars 5 and 6 have the same low 99.5: bar 6 stores nothing, bar 7 (low 100) stores bar 6. With <= / >= the
    script would store bar 2 at bar 3 and bar 5 at bar 6."""
    rows = [(99, 100, 98, 99.5, 1), (99.5, 101, 99, 100.5, 1), (100.5, 102, 100, 101.5, 1),
            (101.5, 102, 100.5, 101, 1), (101, 101.5, 100.25, 100.5, 1), (100.5, 101, 99.5, 100, 1),
            (100, 100.5, 99.5, 100, 1), (100, 100.75, 100, 100.5, 1)]
    r = run(rows)
    assert r["hs_bar"].tolist() == [-1, -1, -1, -1, 3, 3, 3, 3]
    assert r["hs_price"][4] == 102.0
    assert r["ls_bar"].tolist() == [-1] * 7 + [6]
    assert r["ls_price"][7] == 99.5
    # the direction: bar 2 and bar 3 are both window highs (true), bar 5 and bar 6 both window lows (false)
    assert r["is_down_move"].tolist() == [False, False, True, True, True, False, False, False]
    assert np.flatnonzero(r["flip"]).tolist() == [2, 5]


def test_trap_low_wins_on_a_bar_that_is_both_extremes():
    """l.69-72: ``if high == H`` sets isDownMove true, then ``if low == L`` sets it false. Bar 3 (high 105 = the
    3-bar high, low 98 = the 3-bar low) leaves it FALSE: a flip from the true of bar 2, finishing an up leg (dir +1).
    With the two tests the other way round it would stay true and there would be no flip on bar 3."""
    rows = [(100, 101, 99, 100.5, 1), (100.5, 102, 100, 101.5, 1), (101.5, 103, 101, 102.5, 1),
            (102.5, 105, 98, 99, 1)]
    r = run(rows)
    assert r["is_down_move"].tolist() == [False, False, True, False]
    assert np.flatnonzero(r["flip"]).tolist() == [2, 3]
    assert r["legs"].dir.tolist() == [-1, 1]


def test_trap_bar_span_prev_to_last():
    """The profile reads the bars from the older swing to the newer swing, both included (l.113-125), and not the
    bars after the newer swing up to the flip bar. In the base path the up leg is bars 2..6 (volumes 10..50); bars
    0-1 (before the older swing) and 7-8 (after the newer swing, the flip bar included) carry 1000 each and must
    not count: total 250. With the span running to the flip bar it would be 250 + 1000 (bar 7: close 106.5 is bin
    6's midpoint, one bin) + 2000 (bar 8: close 105 is a bin boundary, two bins); without the older swing bar, 230."""
    r = run(BASE)
    up = leg(r, 8)
    assert (up.start_bar, up.end_bar, up.total) == (2, 6, 250.0)
    o, h, l, c, v = bars(BASE)
    p = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), 8, 6, 109.0, 2, 100.0, 1.0)
    assert (p.prev_bar, p.last_bar) == (2, 6)
    v2 = v.copy()
    v2[[0, 1, 7, 8]] = 0.0                                      # the bars outside [2, 6] carry nothing
    assert O.leg_profile(o.tolist(), c.tolist(), v2.tolist(), 8, 6, 109.0, 2, 100.0, 1.0) == p
    v3 = v.copy()
    v3[[2, 6]] = 0.0                                            # both endpoints are read
    assert O.leg_profile(o.tolist(), c.tolist(), v3.tolist(), 8, 6, 109.0, 2, 100.0, 1.0).total == 250.0 - 20 - 100


def test_trap_double_counting_into_two_bins():
    """l.131-141: a bar's volume goes to EVERY bin whose midpoint is strictly within one binStep of its close, i.e.
    to two bins (its own and the nearer neighbour), to one when the close sits exactly on a midpoint. The up leg of
    the base path, 9 bins of 1 from 100 (midpoints 100.5 .. 108.5): close 101 (a boundary) -> bins 0 and 1; 102.5
    and 104.5 (midpoints) -> bins 2 and 4 only (their neighbours are exactly 1.0 away, not < 1); 106.75 -> bins 6
    and 7; 108 (a boundary) -> bins 7 and 8. The total counts each two-bin bar twice: 2 * 10 + 20 + 30 + 2 * 40 +
    2 * 50 = 250, not the leg's plain volume 150, and the delta is (130 - 120) / 250 = 0.04, not (90 - 60) / 150."""
    o, h, l, c, v = bars(BASE)
    p = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), 8, 6, 109.0, 2, 100.0, 1.0)
    assert (p.ok, p.bin_count, p.bin_step, p.bottom, p.top) == (True, 9, 1.0, 100.0, 109.0)
    assert p.volume_bins == (10.0, 10.0, 20.0, 0.0, 30.0, 0.0, 40.0, 90.0, 50.0)
    assert p.buy_bins == (0.0, 0.0, 20.0, 0.0, 30.0, 0.0, 40.0, 40.0, 0.0)
    assert p.sell_bins == (10.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 50.0, 50.0)
    assert (p.total, p.buy, p.sell, p.delta, p.tied) == (250.0, 130.0, 120.0, 0.04, (107.5,))
    up = leg(run(BASE), 8)
    assert (up.total, up.delta_pct) == (250.0, 0.04)


def test_trap_int_truncation():
    """l.110: ``binCount = int(|H - L| / binSize)`` truncates. With the flip bar's true range 4 (bar 8: high 106.5,
    low 102.5, previous close 106.5) the bin size is 2 and 9 / 2 = 4.5 -> 4 bins of 2.25 (midpoints 101.125,
    103.375, 105.625, 107.875). Closes 101 -> bin 0 only (2.375 from bin 1's midpoint); 102.5 -> 0, 1; 104.5 -> 1, 2;
    106.75 -> 2, 3; 108 -> bin 3 only. Bins [30, 50, 70, 90]: POC bin 3 = (106.75 + 109) / 2 = 107.875; total 240;
    buy 180, sell 60. Rounded (5 bins of 1.8) no bin would be centred on 107.875."""
    rows = variant(BASE, b8=(106, 106.5, 102.5, 105, 1000))
    up = leg(run(rows), 8)
    assert (up.atr_at_flip, up.poc, up.poc_all, up.total, up.delta_pct) == (4.0, 107.875, (107.875,), 240.0, 0.5)
    o, h, l, c, v = bars(rows)
    p = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), 8, 6, 109.0, 2, 100.0, 2.0)
    assert (p.bin_count, p.bin_step, p.volume_bins) == (4, 2.25, (30.0, 50.0, 70.0, 90.0))
    rounded = 100.0 + np.arange(5) * 1.8 + 0.9
    assert not np.any(np.isclose(rounded, 107.875))


def test_trap_poc_ties():
    """Several bins equal to the maximum (l.149-154 draws a POC line for each): ``poc_all`` holds them all, the POC
    is the tied bin nearest the close of the bar that reads it (PREREG 6.4), an exact distance tie goes to the lower
    bin (R11). Base path with bar 4's volume 90: bins 4 (104.5) and 7 (107.5) both hold 90. Flip close 105 -> 104.5
    (0.5 against 2.5); 106.25 -> 107.5 (1.25 against 1.75); 106 -> both 1.5 away -> the lower, 104.5."""
    for c8, want in ((105.0, 104.5), (106.25, 107.5), (106.0, 104.5)):
        rows = variant(BASE, b4=(103, 105, 102, 104.5, 90), b8=(106, 106.5, 104.5, c8, 1000))
        r = run(rows)
        up = leg(r, 8)
        assert up.poc_all == (104.5, 107.5) and up.poc == want, c8
        assert (r["f_poc"][8], r["f_poc_ties"][8]) == (want, 2)              # the forming leg on the flip bar
        assert (up.total, up.delta_pct) == (310.0, (190.0 - 120.0) / 310.0)


def test_trap_atr_taken_at_the_flip_bar():
    """``priceBinSize = ta.atr(200) * 0.5`` (l.85) is read on the bar where the profile is computed: for a finished
    leg, the FLIP bar. In the base path the up leg's flip bar 8 has ATR 2 (9 bins of 1, POC 107.5); the ATR on the
    newer swing bar 6 (true range max(3, 2.25, 0.75) = 3) and on the bar that confirmed it (7: 3) would give 6 bins
    of 1.5 and the POC 106.75 (what the forming leg shows on bar 7)."""
    r = run(BASE)
    up = leg(r, 8)
    assert (up.atr_at_flip, up.poc) == (2.0, 107.5)
    assert r["f_poc"][7] == 106.75 and r["hs_bar"][7] == 6 and r["ls_bar"][7] == 2        # same pair, ATR 3
    o, h, l, c, v = bars(BASE)
    at_swing = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), 8, 6, 109.0, 2, 100.0, 3.0 * 0.5)
    assert at_swing.bin_count == 6 and at_swing.tied == (106.75,)


def test_trap_naming_is_down_move_true_finishes_the_down_leg():
    """``isDownMove`` is true after a new high: a flip TO TRUE finishes the DOWN leg (older high -> newer low, drawn
    orange with "▼", l.99 / l.181: dir -1) and a flip to false finishes the UP leg (older low -> newer high, lime
    "▲": dir +1). Base path: bar 8 flips to false -> dir +1 from the swing low (bar 2) to the swing high (bar 6);
    bar 12 flips to true -> dir -1 from the swing high (bar 6) to the swing low (bar 10)."""
    r = run(BASE)
    up, dn = leg(r, 8), leg(r, 12)
    assert not r["is_down_move"][8] and (up.dir, up.start_bar, up.end_bar) == (1, 2, 6)
    assert r["ls_bar"][8] == up.start_bar and r["hs_bar"][8] == up.end_bar
    assert r["is_down_move"][12] and (dn.dir, dn.start_bar, dn.end_bar) == (-1, 6, 10)
    assert r["hs_bar"][12] == dn.start_bar and r["ls_bar"][12] == dn.end_bar
    assert r["is_down_move"][4] and leg(r, 4).dir == -1


# ───────────────────────────── 2. the spec's other cases and the readings ─────────────────────────────

def test_spec_top_and_bottom_edges():
    """Edge bins have one neighbour: a close at the very bottom (bar 2 closing at its low 100) lands in bin 0 only
    (bin 1's midpoint is 1.5 away); one at the very top (bar 6 closing at its high 109) in the top bin only. Bins
    [10, 0, 20, 0, 30, 0, 40, 40, 50]: POC = the top bin, (108 + 109) / 2 = 108.5; total 190; bar 6 is now green
    (open 108, close 109): buy 180, sell 10. A close half a step or more outside the range reaches no bin at all (bin
    0's midpoint is half a step inside the bottom); one less than half a step outside still reaches the edge bin."""
    rows = variant(BASE, b2=(102, 102, 100, 100, 10), b6=(108, 109, 106, 109, 50))
    up = leg(run(rows), 8)
    assert (up.poc, up.poc_all, up.total, up.delta_pct) == (108.5, (108.5,), 190.0, (180.0 - 10.0) / 190.0)
    o, c, v = [0.0, 0.0, 0.0], [98.4, 109.4, 104.75], [1.0, 2.0, 4.0]    # bars 0..2; swing low bar 0, high bar 2
    p = O.leg_profile(o, c, v, 3, 2, 109.0, 0, 100.0, 1.0)
    assert p.bin_count == 9
    assert p.volume_bins == (0.0, 0.0, 0.0, 0.0, 4.0, 4.0, 0.0, 0.0, 2.0)  # 98.4: lost; 109.4: bin 8; 104.75: 4, 5


def test_spec_doji_counts_as_sell():
    """l.138-141: ``if candleClose > candleOpen`` buy, else sell: a doji (close == open) is SELL. Bar 6 of the base
    path is a doji (108 / 108): its 50 goes to the sell side twice (bins 7, 8), delta (130 - 120) / 250. Opened at
    107 instead it is green: buy 230, sell 20, delta 210 / 250."""
    assert leg(run(BASE), 8).delta_pct == (130.0 - 120.0) / 250.0
    green = leg(run(variant(BASE, b6=(107, 109, 106, 108, 50))), 8)
    assert (green.total, green.delta_pct) == (250.0, (230.0 - 20.0) / 250.0)


def test_spec_skips_bin_count_zero_na_atr_missing_swing():
    """R8: a leg is not computable when binCount == 0, the ATR is na, or a swing is missing; the row keeps its flip
    bar, dir, swing bars and prices, the profile columns are NaN / (), and the run goes on."""
    # binCount 0: the flip bar's true range 18.5 (low 88) -> bin size 9.25 > |H - L| = 9
    rows = variant(BASE, b8=(106, 106.5, 88, 100, 1000))
    r = run(rows)
    up = leg(r, 8)
    assert (up.dir, up.start_bar, up.end_bar, up.lo, up.hi, up.fifty, up.atr_at_flip) == \
        (1, 2, 6, 100.0, 109.0, 104.5, 18.5)
    assert np.isnan(up.poc) and up.poc_all == () and np.isnan(up.total) and np.isnan(up.delta_pct)
    assert np.isnan(r["f_poc"][8]) and r["f_poc_ties"][8] == 0 and np.isnan(r["f_total"][8])
    assert (r["f_lo"][8], r["f_hi"][8]) == (100.0, 109.0)              # the leg's bounds exist without a profile
    # ... and the run continues: bar 9 stores the swing low (8, 88); the down leg 6..8 at bar 12 has 21 bins of 1:
    # closes 108 -> bins 19, 20 (50); 106.5 -> bin 18 only (1000); 100 -> bins 11, 12 (1000): a three-way tie,
    # levels 99.5, 100.5, 106.5; the nearest to the close 105.5 is 106.5. All red or doji: delta -1.
    dn = leg(r, 12)
    assert (dn.start_bar, dn.end_bar, dn.lo) == (6, 8, 88.0)
    assert (dn.poc_all, dn.poc, dn.total, dn.delta_pct) == ((99.5, 100.5, 106.5), 106.5, 3100.0, -1.0)
    # na ATR: atr_len 20 > 13 bars: every profile is NaN, the swings and flips are those of atr_len 1
    a, b = run(BASE), run(BASE, atr_len=20)
    for k in ("is_down_move", "hs_bar", "hs_price", "ls_bar", "ls_price", "flip", "f_dir", "f_lo", "f_hi"):
        assert same(a[k], b[k]), k
    assert np.isnan(b["f_poc"]).all() and (b["f_poc_ties"] == 0).all() and np.isnan(b["legs"].atr_at_flip).all()
    assert b["legs"].poc.isna().all() and b["legs"].flip_bar.tolist() == [4, 8, 12]
    # a missing swing: the first flip of the base path (bar 4) has no swing high yet
    first = leg(a, 4)
    assert (first.start_bar, first.end_bar) == (-1, -1) and np.isnan(first.lo) and np.isnan(first.poc)


def test_spec_forming_leg_equals_finished_leg_at_next_flip():
    """With no swing stored in between and the same binCount, the forming leg on a bar before the flip equals the
    finished leg at the flip. Base path with bar 7's low 106 (true range 2, the flip bar's too): bar 7 already shows
    the up leg's POC 107.5, total 250, delta 0.04. In the base path itself bar 7 has ATR 3 (6 bins), so its forming
    POC 106.75 differs; and bar 10, after the flip, still shows the finished up leg, because no new swing low has
    been stored yet (the forming leg is always the stored pair)."""
    r = run(variant(BASE, b7=(108, 108, 106, 106.5, 1000)))
    up = leg(r, 8)
    for t in (7, 8):
        assert (r["f_poc"][t], r["f_total"][t], r["f_delta_pct"][t]) == (up.poc, up.total, up.delta_pct), t
    base = run(BASE)
    assert base["f_poc"][7] != leg(base, 8).poc
    assert (base["f_poc"][10], base["f_total"][10], base["f_delta_pct"][10]) == (107.5, 250.0, 0.04)


def test_reading_r1_warmup_na():
    """R1: ``ta.highest(3)`` is na on bars 0-1, so nothing can set isDownMove there, even though bar 1's high (101)
    is the highest so far; bar 2 is the first window high. With the partial-window reading bar 1 would flip."""
    rows = [(99, 100, 98, 99.5, 1), (99.5, 101, 99, 100.5, 1), (100.5, 102, 100, 101.5, 1)]
    r = run(rows)
    assert r["is_down_move"].tolist() == [False, False, True]
    assert np.flatnonzero(r["flip"]).tolist() == [2]


def test_reading_r4_swing_confirmed_on_the_flip_bar_ends_the_leg():
    """R4: l.75-82 run before l.90. Bar 7 is both the bar that confirms the swing high of bar 6 (106 < 109) and a new
    3-bar low (103): the swing is stored first, so the leg finished on bar 7 is 2..6. Its true range max(3, 2, 5) = 5
    -> bin size 2.5 -> int(9 / 2.5) = 3 bins of 3: closes 101 -> bin 0; 102.5 -> 0, 1; 104.5 -> bin 1 only; 106.75
    -> 1, 2; 108 -> bin 2. Bins [30, 90, 90]: tied at 104.5 and 107.5, the close 104 picks 104.5; total 210, buy 150,
    sell 60. Computed before the confirmation, the leg would have no swing high at all."""
    rows = BASE[:7] + [(106, 106, 103, 104, 1000)]
    r = run(rows)
    assert r["flip"][7] and r["hs_bar"][7] == 6
    up = leg(r, 7)
    assert (up.dir, up.start_bar, up.end_bar, up.atr_at_flip) == (1, 2, 6, 5.0)
    assert (up.poc_all, up.poc, up.total, up.delta_pct) == ((104.5, 107.5), 104.5, 210.0, (150.0 - 60.0) / 210.0)


def test_reading_r5_delta_is_a_fraction():
    """R5: the contract's (buy - sell) / total, a fraction in [-1, 1]; the script's tooltip shows it times 100
    ("4.00%" for the base up leg, l.187)."""
    up = leg(run(BASE), 8)
    assert up.delta_pct == 0.04 and -1.0 <= up.delta_pct <= 1.0


def test_reading_r7_newest_bar_first_accumulation():
    """R7: each bin accumulates the bars from the newer swing back to the older one, and the sums add the bins in
    index order. With fractional volumes the bits depend on that order; an explicit transcription of that order in
    this test (separate code) agrees bit for bit, and on these volumes the oldest-first order gives other bits."""
    rng = np.random.default_rng(7)
    n = 40
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = c + rng.normal(0, 0.5, n)
    v = rng.gamma(2.0, 123.456, n)
    lo, hi = float(c.min()) - 0.1, float(c.max()) + 0.1
    p = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), n, n - 1, hi, 0, lo, (hi - lo) / 7.3)
    bc, st = p.bin_count, p.bin_step

    def sums(order):
        vb = [0.0] * bc
        for j in order:
            for k in range(bc):
                if abs(lo + (k * st) + (st / 2) - c[j]) < st:
                    vb[k] = vb[k] + v[j]
        tot = 0.0
        for x in vb:
            tot = tot + x
        return tuple(vb), tot
    newest = sums(range(n - 1, -1, -1))
    assert (p.volume_bins, p.total) == newest
    assert sums(range(n)) != newest


def test_reading_r8_pine_array_limit():
    """R8: more than 100,000 bins is an array-size runtime error on TradingView: not computable (here a bin size of
    1e-6 for a 9-dollar leg would need 9,000,000 bins). A bin size so small that the quotient overflows to infinity
    (5e-324, the smallest double) is not computable either, without an OverflowError."""
    r = run(BASE, bin_mult=0.5e-6)
    assert r["legs"].poc.isna().all() and np.isnan(r["f_poc"]).all()
    o, h, l, c, v = bars(BASE)
    p = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), 8, 6, 109.0, 2, 100.0, 1e-6)
    assert not p.ok and p.bin_count > O.PINE_ARRAY_MAX
    p = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), 8, 6, 109.0, 2, 100.0, 5e-324)
    assert not p.ok and p.bin_count == O.PINE_ARRAY_MAX + 1
    assert np.isnan(run(BASE, bin_mult=5e-324)["f_poc"]).all()


def test_reading_r9_zero_volume_no_poc():
    """R9: no volume in any bin: the ratio 0 / 0 is na, never 1, so no POC line: POC NaN, no ties, total 0.0,
    delta NaN."""
    rows = [(*x[:4], 0.0) if 2 <= i <= 6 else x for i, x in enumerate(BASE)]
    r = run(rows)
    up = leg(r, 8)
    assert np.isnan(up.poc) and up.poc_all == () and up.total == 0.0 and np.isnan(up.delta_pct)
    assert np.isnan(r["f_poc"][8]) and r["f_poc_ties"][8] == 0 and r["f_total"][8] == 0.0


def test_reading_r10_poc_is_the_drawn_level():
    """R10: the POC is the drawn line's level ``math.avg(binLow, binHigh)`` = (binLow + (binLow + binStep)) / 2
    (l.146-154), which can differ in the last bit from l.132's ``binLow + binStep / 2``. On a random walk every POC
    equals the first formula, and some differ from the second (so the reading is observable)."""
    o, h, l, c, v = walk(900, 11)
    r = O.swing_profile(o, h, l, c, v, swing_len=10, atr_len=20)
    differs = 0
    for _, row in r["legs"].iterrows():
        if not np.isfinite(row.poc):
            continue
        p = O.leg_profile(o.tolist(), c.tolist(), v.tolist(), int(row.flip_bar), int(r["hs_bar"][row.flip_bar]),
                          float(r["hs_price"][row.flip_bar]), int(r["ls_bar"][row.flip_bar]),
                          float(r["ls_price"][row.flip_bar]), float(row.atr_at_flip) * 0.5)
        levels = [(p.bottom + k * p.bin_step + (p.bottom + k * p.bin_step + p.bin_step)) / 2 for k in range(p.bin_count)]
        mids = [p.bottom + (k * p.bin_step) + (p.bin_step / 2) for k in range(p.bin_count)]
        k = levels.index(row.poc)
        differs += mids[k] != levels[k]
    assert differs > 0


def test_reading_r13_same_bar_swings():
    """R13: bar 3 is both the 3-bar high (105) and low (98) and bar 4 (an inside bar) confirms it both ways: both
    stored swings sit on bar 3, the forming leg has no direction (f_dir 0) and spans that bar only. The flip of bar
    5 (a new high) finishes that one-bar "leg" with dir -1 (from the flip): 7 bins of 1 (true range 2); bar 3's
    close 99 is a bin boundary, so bins 0 and 1 tie at 98.5 and 99.5, and the close 105 picks 99.5; it is red."""
    rows = [(100, 101, 99, 100.5, 1), (100.5, 102, 100, 101.5, 1), (101.5, 103, 101, 102.5, 1),
            (102.5, 105, 98, 99, 7), (99, 104, 99, 103.5, 1), (103.5, 105.5, 103.5, 105, 1)]
    r = run(rows)
    assert r["hs_bar"].tolist()[4:] == [3, 3] and r["ls_bar"].tolist()[4:] == [3, 3]
    assert r["f_dir"].tolist() == [0] * 6
    assert (r["f_lo"][4], r["f_hi"][4]) == (98.0, 105.0)
    one = leg(r, 5)
    assert (one.dir, one.start_bar, one.end_bar, one.atr_at_flip) == (-1, 3, 3, 2.0)
    assert (one.poc_all, one.poc, one.total, one.delta_pct) == ((98.5, 99.5), 99.5, 14.0, -1.0)


def test_reading_r15_atr_is_pine_rma():
    """R15: the oracle's ``Atr`` equals study 1's oracle ATR (``pine_atr`` / ``pine_rma``) bit for bit."""
    for seed, p0, vol in ((1, 1500.0, 2.0), (2, 30000.0, 100.0)):
        o, h, l, c, v = walk(700, seed, p0, vol)
        for n in (1, 14, 200):
            a = O.Atr(n)
            mine = np.array([a(x, y, z) for x, y, z in zip(h.tolist(), l.tolist(), c.tolist())])
            assert same(mine, S1.atr(h, l, c, n)), (seed, n)


# ───────────────────────────── 3. an independent formulation, truncation, the memo ─────────────────────────────

def walk(n, seed, p0=1500.0, vol=2.0, float_volume=False, spikes=True):
    """A random walk with wicks (gold-like for p0 = 1500, BTC-like for p0 = 30000, vol = 100), integer volumes (or
    gamma-distributed fractional ones), and a few huge outside bars that are both window extremes."""
    rng = np.random.default_rng(seed)
    c = p0 + np.cumsum(rng.normal(0.0, vol, n))
    o = np.r_[p0, c[:-1]] + rng.normal(0.0, vol / 4, n) * (rng.random(n) < 0.05)
    h = np.maximum(o, c) + rng.uniform(0.0, vol, n)
    l = np.minimum(o, c) - rng.uniform(0.0, vol, n)
    if spikes:
        k = rng.random(n) < 0.004
        h[k] += 30 * vol
        l[k] -= 30 * vol
    v = rng.gamma(2.0, 50.0, n) if float_volume else rng.integers(1, 400, n).astype(np.float64)
    dj = rng.random(n) < 0.03                                   # some dojis
    c[dj] = o[dj]
    h = np.maximum(h, np.maximum(o, c))
    l = np.minimum(l, np.minimum(o, c))
    return o, h, l, c, v


def np_swing(o, h, l, c, v, swing_len=50, atr_len=200, bin_mult=0.5):
    """The contract from closed forms and numpy: window extremes from sliding windows; the direction as the last
    event (a low event wins); a swing = the bar before the last confirming bar; ATR = study 1's oracle; each distinct
    (pair, binCount) profile with a vectorised mask; the tie choice by argmin (the first = the lower level)."""
    o, h, l, c, v = (np.asarray(x, np.float64) for x in (o, h, l, c, v))
    n = len(c)
    H, L = np.full(n, nan), np.full(n, nan)
    if n >= swing_len:
        H[swing_len - 1:] = sliding_window_view(h, swing_len).max(axis=1)
        L[swing_len - 1:] = sliding_window_view(l, swing_len).min(axis=1)
    ev = np.where(l == L, 0, np.where(h == H, 1, -1))
    last = np.maximum.accumulate(np.where(ev >= 0, np.arange(n), -1))
    is_down = np.where(last >= 0, ev[np.maximum(last, 0)] == 1, False)
    flip = is_down != np.r_[False, is_down[:-1]]
    ch = np.r_[False, (h[:-1] == H[:-1]) & (h[1:] < H[1:])]
    cl = np.r_[False, (l[:-1] == L[:-1]) & (l[1:] > L[1:])]
    jh = np.maximum.accumulate(np.where(ch, np.arange(n), -1))
    jl = np.maximum.accumulate(np.where(cl, np.arange(n), -1))
    hs = np.where(jh >= 0, jh - 1, -1)
    ls = np.where(jl >= 0, jl - 1, -1)
    hp = np.where(hs >= 0, h[np.maximum(hs, 0)], nan)
    lp = np.where(ls >= 0, l[np.maximum(ls, 0)], nan)
    both = (hs >= 0) & (ls >= 0)
    f_dir = np.where(both, np.sign(hs - ls), 0).astype(np.int8)
    f_lo, f_hi = np.where(both, np.minimum(hp, lp), nan), np.where(both, np.maximum(hp, lp), nan)
    atr = S1.atr(h, l, c, atr_len)
    with np.errstate(invalid="ignore", divide="ignore"):
        bc = np.where(both & (atr * bin_mult > 0), np.floor((f_hi - f_lo) / (atr * bin_mult)), 0)
    profiles = {}
    f_poc, f_ties = np.full(n, nan), np.zeros(n, np.int64)
    f_delta, f_total = np.full(n, nan), np.full(n, nan)
    tied_at = [()] * n
    for t in range(n):
        k = int(bc[t]) if np.isfinite(bc[t]) else 0
        if not both[t] or k < 1 or k > O.PINE_ARRAY_MAX:
            continue
        key = (hs[t], ls[t], k)
        if key not in profiles:
            lo, hi = f_lo[t], f_hi[t]
            step = (hi - lo) / k
            kk = np.arange(k, dtype=np.float64)
            mids = lo + kk * step + step / 2
            j = np.arange(min(hs[t], ls[t]), max(hs[t], ls[t]) + 1)
            m = np.abs(mids[None, :] - c[j][:, None]) < step
            green = c[j] > o[j]
            vb = (m * v[j][:, None]).sum(axis=0)
            bb = (m * np.where(green, v[j], 0.0)[:, None]).sum(axis=0)
            sb = (m * np.where(green, 0.0, v[j])[:, None]).sum(axis=0)
            blo = lo + kk * step
            lev = (blo + (blo + step)) / 2
            tied = lev[vb == vb.max()] if vb.max() > 0 else np.zeros(0)
            tot = vb.sum()
            profiles[key] = (tied, tot, (bb.sum() - sb.sum()) / tot if tot != 0 else nan)
        tied, tot, dl = profiles[key]
        f_total[t], f_delta[t], f_ties[t] = tot, dl, len(tied)
        if len(tied):
            f_poc[t] = tied[int(np.argmin(np.abs(tied - c[t])))]
            tied_at[t] = tuple(float(x) for x in tied)
    fb = np.flatnonzero(flip)
    legs = pd.DataFrame({
        "flip_bar": fb.astype(np.int64), "dir": np.where(is_down[fb], -1, 1).astype(np.int8),
        "start_bar": np.where(both[fb], np.minimum(hs[fb], ls[fb]), -1).astype(np.int64),
        "end_bar": np.where(both[fb], np.maximum(hs[fb], ls[fb]), -1).astype(np.int64),
        "lo": f_lo[fb], "hi": f_hi[fb], "poc": f_poc[fb],
        "poc_all": pd.Series([tied_at[t] for t in fb], dtype=object, index=range(len(fb))),
        "delta_pct": f_delta[fb], "total": f_total[fb], "fifty": (f_lo[fb] + f_hi[fb]) / 2, "atr_at_flip": atr[fb]},
        columns=list(O.LEG_COLUMNS))
    return {"is_down_move": is_down, "hs_bar": hs.astype(np.int64), "hs_price": hp, "ls_bar": ls.astype(np.int64),
            "ls_price": lp, "flip": flip, "f_dir": f_dir, "f_lo": f_lo, "f_hi": f_hi, "f_poc": f_poc,
            "f_poc_ties": f_ties, "f_delta_pct": f_delta, "f_total": f_total, "legs": legs}


def check_cross(r, w, exact_sums=True):
    """The oracle against ``np_swing``: bit for bit; with fractional volumes the sums (total, delta) to 1e-12."""
    for k in O.KEYS:
        if not exact_sums and k in ("f_total", "f_delta_pct"):
            assert np.array_equal(np.isnan(r[k]), np.isnan(w[k])), k
            assert np.allclose(r[k], w[k], rtol=1e-12, atol=1e-12, equal_nan=True), k
        else:
            assert same(r[k], w[k]), k
    a, b = r["legs"], w["legs"]
    if exact_sums:
        assert same_legs(a, b)
    else:
        for k in O.LEG_COLUMNS:
            if k in ("total", "delta_pct"):
                assert np.allclose(a[k], b[k], rtol=1e-12, atol=1e-12, equal_nan=True), k
            elif k == "poc_all":
                assert [tuple(x) for x in a[k]] == [tuple(x) for x in b[k]]
            else:
                assert same(a[k].to_numpy(), b[k].to_numpy()), k


@pytest.mark.parametrize("seed,p0,vol,fv", [(3, 1500.0, 2.0, False), (4, 30000.0, 100.0, False),
                                            (5, 30000.0, 100.0, True)])
def test_numpy_cross_check(seed, p0, vol, fv):
    o, h, l, c, v = walk(2500, seed, p0, vol, float_volume=fv)
    for kw in (dict(), dict(swing_len=10, atr_len=14), dict(swing_len=20, atr_len=50, bin_mult=0.3)):
        r = O.swing_profile(o, h, l, c, v, **kw)
        check_cross(r, np_swing(o, h, l, c, v, **kw), exact_sums=not fv)
        assert len(r["legs"]) >= 10 and np.isfinite(r["legs"].poc).sum() >= 5


def test_hand_paths_cross_check():
    """The vectorised formulation also reproduces every hand-made path above."""
    paths = [BASE, variant(BASE, b8=(106, 106.5, 102.5, 105, 1000)), variant(BASE, b8=(106, 106.5, 88, 100, 1000)),
             variant(BASE, b4=(103, 105, 102, 104.5, 90), b8=(106, 106.5, 104.5, 106.0, 1000)),
             BASE[:7] + [(106, 106, 103, 104, 1000)],
             [(100, 101, 99, 100.5, 1), (100.5, 102, 100, 101.5, 1), (101.5, 103, 101, 102.5, 1),
              (102.5, 105, 98, 99, 7), (99, 104, 99, 103.5, 1), (103.5, 105.5, 103.5, 105, 1)]]
    for rows in paths:
        o, h, l, c, v = bars(rows)
        check_cross(O.swing_profile(o, h, l, c, v, **SMALL), np_swing(o, h, l, c, v, **SMALL))


def test_flip_bar_forming_equals_leg_and_invariants():
    """On every flip bar the forming leg is the finished one (same pair, same ATR, same close); the stored prices
    are the swing bars' high / low; the POC lies in the leg's range."""
    for seed, p0, vol in ((6, 1500.0, 2.0), (7, 30000.0, 100.0)):
        o, h, l, c, v = walk(3000, seed, p0, vol)
        check_invariants(O.swing_profile(o, h, l, c, v), o, h, l, c)


def check_invariants(r, o, h, l, c):
    hs, ls = r["hs_bar"], r["ls_bar"]
    assert np.array_equal(np.isnan(r["hs_price"]), hs < 0) and np.array_equal(np.isnan(r["ls_price"]), ls < 0)
    assert same(r["hs_price"][hs >= 0], h[hs[hs >= 0]]) and same(r["ls_price"][ls >= 0], l[ls[ls >= 0]])
    t = np.arange(len(c))
    assert np.all(hs < t) and np.all(ls < t)                    # a stored swing is always an earlier bar
    assert np.all(np.diff(hs) >= 0) and np.all(np.diff(ls) >= 0)
    both = (hs >= 0) & (ls >= 0)
    assert np.array_equal(np.isfinite(r["f_lo"]), both) and np.array_equal(np.isfinite(r["f_hi"]), both)
    ok = np.isfinite(r["f_poc"])
    assert np.all((r["f_lo"][ok] <= r["f_poc"][ok]) & (r["f_poc"][ok] <= r["f_hi"][ok]))
    assert np.array_equal(r["f_poc_ties"] >= 1, ok)
    assert np.all(np.abs(r["f_delta_pct"][np.isfinite(r["f_delta_pct"])]) <= 1.0)
    L = r["legs"]
    fb = L.flip_bar.to_numpy()
    assert np.array_equal(fb, np.flatnonzero(r["flip"]))
    assert np.array_equal(r["flip"][1:], r["is_down_move"][1:] != r["is_down_move"][:-1]) and not r["flip"][0]
    assert np.array_equal(L.dir.to_numpy(), np.where(r["is_down_move"][fb], -1, 1))
    for col, key in (("lo", "f_lo"), ("hi", "f_hi"), ("poc", "f_poc"), ("delta_pct", "f_delta_pct"),
                     ("total", "f_total")):
        assert same(L[col].to_numpy(), r[key][fb]), col
    assert np.array_equal(L.poc_all.map(len).to_numpy(), r["f_poc_ties"][fb])
    assert all(p in a for p, a in zip(L.poc, L.poc_all) if np.isfinite(p))
    assert same(L.fifty.to_numpy(), (L.lo.to_numpy() + L.hi.to_numpy()) / 2)
    hsf, lsf = hs[fb], ls[fb]
    okb = (hsf >= 0) & (lsf >= 0)
    assert np.array_equal(L.start_bar.to_numpy(), np.where(okb, np.minimum(hsf, lsf), -1))
    assert np.array_equal(L.end_bar.to_numpy(), np.where(okb, np.maximum(hsf, lsf), -1))


@pytest.mark.parametrize("seed,p0,vol,kw", [(8, 1500.0, 2.0, {}), (9, 30000.0, 100.0, {}),
                                            (10, 1500.0, 2.0, dict(swing_len=10, atr_len=14))])
def test_truncation_invariance(seed, p0, vol, kw):
    o, h, l, c, v = walk(1600, seed, p0, vol)
    full = O.swing_profile(o, h, l, c, v, **kw)
    for T in (0, 1, 48, 49, 50, 199, 200, 611, 977, 1333, 1598):
        part = O.swing_profile(o[:T + 1], h[:T + 1], l[:T + 1], c[:T + 1], v[:T + 1], **kw)
        for k in O.KEYS:
            assert same(part[k], full[k][:T + 1]), (T, k)
        early = full["legs"][full["legs"].flip_bar <= T].reset_index(drop=True)
        assert same_legs(part["legs"], early), T


def test_memo_changes_nothing():
    """The forming leg's memo (one profile per swing pair and binCount) is exact: recomputing every bar gives the
    same outputs, bit for bit, with integer and with fractional volumes."""
    for seed, fv in ((12, False), (13, True)):
        o, h, l, c, v = walk(700, seed, float_volume=fv)
        for kw in (dict(), dict(swing_len=10, atr_len=14)):
            a = O.swing_profile(o, h, l, c, v, **kw)
            b = O._run(o, h, l, c, v, memo=False, **{**dict(swing_len=50, atr_len=200, bin_mult=0.5), **kw})
            for k in O.KEYS:
                assert same(a[k], b[k]), k
            assert same_legs(a["legs"], b["legs"])


# ───────────────────────────── 4. the real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H bars of one symbol from its data start to 2024-07-01 00:00 UTC (exclusive), with study 1's
    hold-out guard pointed at an empty folder; gold's volume = its tick volume, BTC's = Binance BTCUSDT spot
    volume (PREREG 2). Only the arrays the profile reads are kept, one symbol in memory at a time."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            cache.clear()
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end=TM.HOLDOUT_START)
                out = {}
                for tf in ("1H", "4H"):
                    b = mk.tbars(tf)
                    if symbol.startswith("BTC"):
                        try:
                            vol, miss = TM.binance_volume(mk, tf)
                        except FileNotFoundError as e:
                            pytest.skip(f"Binance klines not on this machine: {e}")
                    else:
                        vol, miss = b.vol, np.zeros(len(b), np.int64)
                    out[tf] = NS(t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(),
                                 c=b.c.copy(), v=np.asarray(vol, np.float64).copy(), miss=np.asarray(miss).copy(),
                                 complete=b.complete.copy())
            del mk
            cache[symbol] = out
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    rows = real(symbol)
    a19, a23 = TM.s_of("2019-01-01"), TM.s_of("2023-01-01")
    T = TM.s_of("2021-06-15 12:00")
    for tf, b in rows.items():
        assert int(b.tc[-1]) <= TM.CUT_S and bool(b.complete.all()), tf          # nothing from the hold-out
        r = O.swing_profile(b.o, b.h, b.l, b.c, b.v)
        check_invariants(r, b.o, b.h, b.l, b.c)
        scored = b.t >= a19
        # from 2019 on every bar has both swings and the ATR, so every value the contract defines exists
        for k in ("hs_price", "ls_price", "f_lo", "f_hi", "f_poc", "f_total", "f_delta_pct"):
            assert np.isfinite(r[k][scored]).all(), (tf, k)
        assert (r["f_poc_ties"][scored] >= 1).all() and (r["hs_bar"][scored] >= 0).all(), tf
        L = r["legs"]
        Ls = L[scored[L.flip_bar.to_numpy()]]
        for k in ("lo", "hi", "poc", "delta_pct", "total", "fifty", "atr_at_flip"):
            assert np.isfinite(Ls[k]).all(), (tf, k)
        assert (Ls.start_bar >= 0).all() and (Ls.poc_all.map(len) >= 1).all(), tf
        dev = Ls[b.tc[Ls.flip_bar.to_numpy()] <= a23]                             # legs finished in 2019-2022
        assert (dev.dir == 1).sum() >= 30 and (dev.dir == -1).sum() >= 30, tf
        assert same(L.atr_at_flip.to_numpy(), S1.atr(b.h, b.l, b.c, 200)[L.flip_bar.to_numpy()]), tf
        check_cross(r, np_swing(b.o, b.h, b.l, b.c, b.v), exact_sums=not symbol.startswith("BTC"))
        i = int(np.searchsorted(b.tc, T, side="right")) - 1                       # a cut at one T
        part = O.swing_profile(b.o[:i + 1], b.h[:i + 1], b.l[:i + 1], b.c[:i + 1], b.v[:i + 1])
        for k in O.KEYS:
            assert same(part[k], r[k][:i + 1]), (tf, k)
        assert same_legs(part["legs"], L[L.flip_bar <= i].reset_index(drop=True)), tf
