"""
Port A of Swing Profile (``backtesting/research/tradeiq2_ind_swing.py``).

1. One hand-computed test per trap of the map's porting risks (``orb_session_swing_ha.md`` 3.6, "Risks": nine
   items), named after it. Each also runs the wrong reading on the same bars (``PineScript``, a plain-Python
   bar-by-bar transcription of the script's computing lines, l.66-154 and the forming copy l.214-258, with one switch
   per misreading) and checks that it answers differently.
2. The rest of the map's test list (3.6, "Tests"): the top and bottom edges, the doji, the skips (a swing missing, the
   ATR na, ``binCount == 0``, empty bins), the forming leg against the finished leg; plus the dir-versus-geometry case,
   the outside bar confirmed on both sides, the warm-up and the contract's keys and dtypes.
3. The port against the transcription on random bars, bit for bit (defaults and short lengths, tick-like and
   Binance-like volumes, coarse price grids that make ties).
4. Truncation invariance: the outputs up to bar T do not change when the bars after T are removed.
5. Real bars (skipped when the tick store is absent): both symbols, 1H and 4H (PREREG 6.4), from the data start to
   2024-06-30 with the hold-out guard closed; gold with its tick volume, BTC with Binance's volume (PREREG 2): no NaN
   where the contract says values exist, the legs' geometry, the transcription bit for bit (every finished leg and a
   sample of forming bars), and truncation.

Every test runs with the guard pointed at an empty folder (FINALISTS.md absent: nothing at or after 2024-07-01).
Line numbers l. are those of the owner's plain-text copy of the script (l.1-424).
"""

from __future__ import annotations

import gc
import math

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_ind_swing as SP
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

NAN = math.nan
SYMS = ("XAUUSDm", "BTCUSDm")
ARRAY_KEYS = SP.KEYS[:-1]
FLOAT_KEYS = ("hs_price", "ls_price", "f_lo", "f_hi", "f_poc", "f_delta_pct", "f_total")
LEG_FLOATS = ("lo", "hi", "poc", "delta_pct", "total", "fifty", "atr_at_flip")
LEG_INTS = ("flip_bar", "dir", "start_bar", "end_bar")


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """The study folder seen by the hold-out guard: an empty tmp folder (the hold-out is closed)."""
    d = tmp_path / "study"
    d.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d


def same(a, b) -> bool:
    """Equal values (bit for bit up to the sign of zero), NaN where the other is NaN, same shape."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def legs_equal(x: pd.DataFrame, y: pd.DataFrame) -> bool:
    if list(x.columns) != list(SP.LEG_COLUMNS) or list(y.columns) != list(SP.LEG_COLUMNS) or len(x) != len(y):
        return False
    for k in LEG_INTS:
        if not np.array_equal(x[k].to_numpy(np.int64), y[k].to_numpy(np.int64)):
            return False
    for k in LEG_FLOATS:
        if not same(x[k].to_numpy(np.float64), y[k].to_numpy(np.float64)):
            return False
    return [tuple(p) for p in x["poc_all"]] == [tuple(p) for p in y["poc_all"]]


def outputs_equal(x, y, upto=None, forming=None) -> bool:
    """Every key equal (floats bit for bit, NaN to NaN; bool / int exactly) on bars [0, upto); the forming-leg keys
    only on the bars of the mask ``forming`` when given; legs with ``flip_bar < upto``."""
    for k in ARRAY_KEYS:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if upto is not None:
            a, b = a[:upto], b[:upto]
        if forming is not None and k.startswith("f_"):
            m = np.asarray(forming)[:len(a)]
            a, b = a[m], b[m]
        if k in FLOAT_KEYS:
            if not same(a, b):
                return False
        elif not np.array_equal(a.astype(np.int64), b.astype(np.int64)):
            return False
    lx, ly = x["legs"], y["legs"]
    if upto is not None:
        lx = lx[lx["flip_bar"] < upto].reset_index(drop=True)
        ly = ly[ly["flip_bar"] < upto].reset_index(drop=True)
    return legs_equal(lx, ly)


# ───────────────────────────── the transcription (the script, bar by bar) ─────────────────────────────

def _fsum(xs):
    """``array.sum()`` read as a left-to-right sum (Python 3.12's ``sum`` of floats is compensated; not used)."""
    s = 0.0
    for x in xs:
        s = s + x
    return s


class PineScript:
    """
    The script's computing lines transcribed bar by bar in plain Python floats from the source: l.66-82 (windows,
    direction, swing points), l.85 (bin size; study 1's ``tradeiq_ind.atr``, which is not under test here), the flip
    block l.90-154 and l.181-187 for the finished legs, and the forming block l.214-258 / 288-291 at the bars asked
    for. Every bin is tested for every bar (the loops of l.125-131), the POC is ``volumeBins.get(k) /
    volumeBins.max() == 1`` computed literally, and the arrays and ``legs`` frame of the contract are returned.
    Switches (default = the script as written, the contract's readings):

    * ``source``: "high_low", or "close" (``ta.highest`` / ``ta.lowest`` read the close; l.69-82 still compare
      ``high`` / ``low``);
    * ``confirm``: "strict", or "loose" (``<=`` / ``>=`` in l.75 / 80);
    * ``both``: "low_wins" (l.69 before l.71), or "high_wins";
    * ``span``: "swings" (bars prev .. last, l.113-125), or "to_bar" (prev .. the bar that computes the profile);
    * ``bins``: "pine" (``|mid - close| < step``), "le" (``<=``), or "single" (only the bin holding the close);
    * ``bin_count``: "int" (truncation, l.110), or "round";
    * ``ties``: "nearest" (PREREG 6.4), "first" (the lowest tied bin), or "last";
    * ``atr_at``: "flip" (l.85 on the flip bar), or "newer_swing" (the ATR of the leg's newer swing bar; finished legs);
    * ``dir_naming``: "script" (a flip to true finishes the down leg: dir -1), or "swapped";
    * ``doji``: "sell" (l.138 ``close > open``), or "buy" (``>=``);
    * ``level``: "avg" (``math.avg(binLow, binHigh)``, l.154), or "mid" (``binMidPrice``, l.132).
    """

    OPTS = dict(source="high_low", confirm="strict", both="low_wins", span="swings", bins="pine", bin_count="int",
                ties="nearest", atr_at="flip", dir_naming="script", doji="sell", level="avg")

    def __init__(self, swing_len=50, atr_len=200, bin_mult=0.5, **kw):
        self.swing_len, self.atr_len, self.bin_mult = int(swing_len), int(atr_len), float(bin_mult)
        self.o = dict(self.OPTS)
        for k, val in kw.items():
            if k not in self.o:
                raise TypeError(k)
            self.o[k] = val

    def profile(self, o, c, v, atr, t, hs, ls, finished):
        """l.106-154 at bar t for the stored pair ``hs`` / ``ls`` = (index or None, price)."""
        S = self.o
        res = dict(lo=NAN, hi=NAN, poc=NAN, ties=0, poc_all=(), delta=NAN, total=NAN, n_bins=0)
        if hs[0] is None or ls[0] is None:
            return res
        swing_bottom = min(hs[1], ls[1])                                         # l.106
        swing_top = max(hs[1], ls[1])                                            # l.107
        res.update(lo=swing_bottom, hi=swing_top)
        last_swing = max(hs[0], ls[0])                                           # l.113
        prev_swing = min(hs[0], ls[0])                                           # l.114
        a = atr[last_swing] if (finished and S["atr_at"] == "newer_swing") else atr[t]
        if a != a:
            return res
        price_bin_size = a * self.bin_mult                                       # l.85
        if not price_bin_size > 0:                                               # an ATR of 0: no bin size
            return res
        q = abs(hs[1] - ls[1]) / price_bin_size
        if not q < SP.PINE_ARRAY_MAX + 1:                                        # l.117 beyond Pine's array limit
            return res
        bin_count = int(q) if S["bin_count"] == "int" else int(round(q))         # l.110
        if bin_count == 0:
            return res
        bin_step = abs(hs[1] - ls[1]) / bin_count                                # l.111
        res["n_bins"] = bin_count
        volume_bins = [0.0] * bin_count
        buy_bins = [0.0] * bin_count
        sell_bins = [0.0] * bin_count
        newest = t if S["span"] == "to_bar" else last_swing
        bar_offset = t - newest                                                  # l.122
        for i in range(bar_offset, (newest - prev_swing) + bar_offset + 1):      # l.125, both ends included
            candle_close, candle_open, candle_vol = c[t - i], o[t - i], v[t - i]  # close[i], open[i], volume[i]
            for k in range(bin_count):                                           # l.131
                bin_mid = swing_bottom + (k * bin_step) + (bin_step / 2)         # l.132
                if S["bins"] == "pine":
                    hit = abs(bin_mid - candle_close) < bin_step                 # l.134
                elif S["bins"] == "le":
                    hit = abs(bin_mid - candle_close) <= bin_step
                else:
                    lo_k = swing_bottom + k * bin_step
                    hit = lo_k <= candle_close < lo_k + bin_step or (k == bin_count - 1 and
                                                                     candle_close == lo_k + bin_step)
                if hit:
                    volume_bins[k] = volume_bins[k] + candle_vol                 # l.136
                    buy = candle_close > candle_open if S["doji"] == "sell" else candle_close >= candle_open
                    if buy:                                                      # l.138
                        buy_bins[k] = buy_bins[k] + candle_vol
                    else:
                        sell_bins[k] = sell_bins[k] + candle_vol
        mx = max(volume_bins)
        levels = []
        for k in range(bin_count):                                               # l.144-154
            bin_low = swing_bottom + (k * bin_step)
            bin_high = bin_low + bin_step
            ratio = volume_bins[k] / mx if mx != 0 else NAN                      # l.149 (0 / 0 is na)
            if ratio == 1:                                                       # l.153
                if S["level"] == "avg":
                    levels.append((bin_low + bin_high) / 2)                      # l.154 math.avg(binLow, binHigh)
                else:
                    levels.append(swing_bottom + (k * bin_step) + (bin_step / 2))
        total = _fsum(volume_bins)                                               # l.184-187
        res["total"] = total
        res["delta"] = (_fsum(buy_bins) - _fsum(sell_bins)) / total if total != 0 else NAN
        if levels:
            if S["ties"] == "nearest":
                best = levels[0]
                for lev in levels[1:]:
                    if abs(lev - c[t]) < abs(best - c[t]):
                        best = lev
            elif S["ties"] == "first":
                best = levels[0]
            else:
                best = levels[-1]
            res.update(poc=best, ties=len(levels), poc_all=tuple(levels))
        return res

    def run(self, o, h, l, c, v, forming_at=None):
        S = self.o
        o, h, l, c, v = ([float(x) for x in np.asarray(a, np.float64)] for a in (o, h, l, c, v))
        N, L = len(c), self.swing_len
        atr = I.atr(h, l, c, self.atr_len).tolist()
        src_hi = h if S["source"] == "high_low" else c
        src_lo = l if S["source"] == "high_low" else c
        want = None if forming_at is None else set(int(t) for t in forming_at)
        HH, LL = [NAN] * N, [NAN] * N
        out = {"is_down_move": np.zeros(N, bool), "hs_bar": np.full(N, -1, np.int64), "hs_price": np.full(N, NAN),
               "ls_bar": np.full(N, -1, np.int64), "ls_price": np.full(N, NAN), "flip": np.zeros(N, bool),
               "f_dir": np.zeros(N, np.int8), "f_lo": np.full(N, NAN), "f_hi": np.full(N, NAN),
               "f_poc": np.full(N, NAN), "f_poc_ties": np.zeros(N, np.int64), "f_delta_pct": np.full(N, NAN),
               "f_total": np.full(N, NAN)}
        rows = []
        is_down = False                                                          # l.61 var isDownMove = false
        hs, ls = (None, NAN), (None, NAN)                                        # l.57-58 SwingData.new(na, na)
        for t in range(N):
            if t >= L - 1:                                                       # l.66-67
                HH[t] = max(src_hi[t - L + 1:t + 1])
                LL[t] = min(src_lo[t - L + 1:t + 1])
            was_down = is_down                                                   # isDownMove[1]
            if S["both"] == "low_wins":                                          # l.69-72
                if h[t] == HH[t]:
                    is_down = True
                if l[t] == LL[t]:
                    is_down = False
            else:
                if l[t] == LL[t]:
                    is_down = False
                if h[t] == HH[t]:
                    is_down = True
            if t >= 1:                                                           # l.75-82
                below = h[t] < HH[t] if S["confirm"] == "strict" else h[t] <= HH[t]
                if h[t - 1] == HH[t - 1] and below:
                    hs = (t - 1, h[t - 1])
                above = l[t] > LL[t] if S["confirm"] == "strict" else l[t] >= LL[t]
                if l[t - 1] == LL[t - 1] and above:
                    ls = (t - 1, l[t - 1])
            out["is_down_move"][t] = is_down
            if hs[0] is not None:
                out["hs_bar"][t], out["hs_price"][t] = hs
            if ls[0] is not None:
                out["ls_bar"][t], out["ls_price"][t] = ls
            if is_down != was_down:                                              # l.90
                out["flip"][t] = True
                p = self.profile(o, c, v, atr, t, hs, ls, finished=True)
                up_leg = not is_down if S["dir_naming"] == "script" else is_down
                have = hs[0] is not None and ls[0] is not None
                rows.append({"flip_bar": t, "dir": 1 if up_leg else -1,
                             "start_bar": min(hs[0], ls[0]) if have else -1,
                             "end_bar": max(hs[0], ls[0]) if have else -1,
                             "lo": p["lo"], "hi": p["hi"], "poc": p["poc"], "poc_all": p["poc_all"],
                             "delta_pct": p["delta"], "total": p["total"], "fifty": (p["lo"] + p["hi"]) / 2,
                             "atr_at_flip": atr[t]})
            if hs[0] is not None and ls[0] is not None:
                out["f_dir"][t] = 1 if hs[0] > ls[0] else (-1 if hs[0] < ls[0] else 0)
            if want is None or t in want:                                        # the forming leg (l.214-258)
                p = self.profile(o, c, v, atr, t, hs, ls, finished=False)
                out["f_lo"][t], out["f_hi"][t], out["f_poc"][t] = p["lo"], p["hi"], p["poc"]
                out["f_poc_ties"][t], out["f_delta_pct"][t], out["f_total"][t] = p["ties"], p["delta"], p["total"]
        legs = pd.DataFrame(rows, columns=list(SP.LEG_COLUMNS))
        legs = legs.astype({"flip_bar": np.int64, "dir": np.int8, "start_bar": np.int64, "end_bar": np.int64,
                            "lo": np.float64, "hi": np.float64, "poc": np.float64, "delta_pct": np.float64,
                            "total": np.float64, "fifty": np.float64, "atr_at_flip": np.float64})
        out["legs"] = legs
        return out


def arr(rows):
    """(o, h, l, c, v) arrays from rows of (o, h, l, c, v)."""
    a = np.array(rows, dtype=np.float64)
    return a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy(), a[:, 3].copy(), a[:, 4].copy()


def hl_bars(highs, lows):
    """Bars with the given highs and lows, open = close = the bar's middle, volume 1 (swing-logic tests)."""
    h, l = np.array(highs, float), np.array(lows, float)
    m = (h + l) / 2
    return m.copy(), h, l, m.copy(), np.ones(len(h))


def leg_row(out, flip_bar):
    lg = out["legs"]
    r = lg[lg["flip_bar"] == flip_bar]
    assert len(r) == 1, flip_bar
    return r.iloc[0]


# ───────────────────────────── the hand-made legs (used by several traps) ─────────────────────────────
#
# swing_len 3, atr_len 1 (the ATR is the bar's true range), bins of 0.5 ATR. Prices are multiples of 1/8, so every
# number below is exact in binary. Hand trace (H3 / L3 = the 3-bar highest high / lowest low, this bar included):
#   bar 2: H3 = 10 = high -> new high: isDownMove true, a flip (no swing stored yet)
#   bar 3: high 9.875 < H3 10 and bar 2 was the 3-bar high -> swing high (2, 10.0)
#   bar 4: low 8.5 = L3 -> new low: isDownMove false, a flip (no swing low stored yet)
#   bars 5, 6, 7: new 3-bar lows 8.0, 7.75, 7.0, none confirmed (each next bar is lower)
#   bar 8: low 7.125 > L3 7.0 and bar 7 was the 3-bar low -> swing low (7, 7.0)
#   bar 9: high 8.25 = H3 -> new high: FLIP to true, the DOWN leg from the high (2, 10.0) to the low (7, 7.0)
#   bars 10, 11: new highs 8.75, 9.5; bar 12: high 9.375 < 9.5 -> swing high (11, 9.5)
#   bar 13: low 8.0 = L3 -> new low: FLIP to false, the UP leg from the low (7, 7.0) to the high (11, 9.5)
# True ranges (= ATR): 1, 1, 1.375, 0.875, 1.125, 0.875, 0.5, 1.125, 1, 1, 1.375, 1.25, 0.625, 1.125.

LEGS = [
    #  open     high    low     close   volume
    (8.00,   8.50,   7.50,   8.25,   1),     # 0
    (8.25,   9.00,   8.00,   8.75,   1),     # 1
    (8.75,  10.00,   8.625,  9.875,  1),     # 2  swing high 10.0; close in the top bin's upper half
    (9.875,  9.875,  9.00,   9.50,   2),     # 3  close on a bin boundary (bins of 0.5 from 7.0)
    (9.50,   9.625,  8.50,   8.875,  3),     # 4  close inside a bin
    (8.875,  8.875,  8.00,   8.25,   4),     # 5  close on a bin midpoint
    (7.875,  8.25,   7.75,   7.875,  5),     # 6  doji
    (7.875,  8.125,  7.00,   7.125,  6),     # 7  swing low 7.0; close in the bottom bin's lower half
    (7.125,  8.125,  7.125,  7.375,  1),     # 8  after the newer swing: not in the down leg
    (7.375,  8.25,   7.25,   7.50, 100),     # 9  flip bar of the down leg: not in it
    (7.50,   8.75,   7.375,  8.50,   1),     # 10
    (8.50,   9.50,   8.25,   9.25,   1),     # 11 swing high 9.5
    (9.25,   9.375,  8.75,   9.00,   1),     # 12
    (9.00,   9.125,  8.00,   8.25,   1),     # 13 flip bar of the up leg
]
HAND = dict(swing_len=3, atr_len=1, bin_mult=0.5)


def legs_bars(**change):
    """LEGS with some cells changed: ``change`` maps "v7" / "h9" / ... to a new value."""
    rows = [list(r) for r in LEGS]
    col = {"o": 0, "h": 1, "l": 2, "c": 3, "v": 4}
    for key, val in change.items():
        rows[int(key[1:])][col[key[0]]] = val
    return arr(rows)


def run_both(bars, **kw):
    """The port and the transcription (the script's readings) on the same bars; they must agree bit for bit."""
    params = {k: kw.pop(k) for k in ("swing_len", "atr_len", "bin_mult") if k in kw}
    port = SP.swing_profile(*bars, **params)
    ref = PineScript(**params).run(*bars)
    assert outputs_equal(port, ref)
    return port, PineScript(**params, **kw).run(*bars) if kw else ref


def test_hand_legs_trace():
    """The trace above, per bar, before any trap: direction, flips, stored points, forming-leg geometry."""
    out, _ = run_both(arr(LEGS), **HAND)
    F, T = False, True
    assert out["is_down_move"].tolist() == [F, F, T, T, F, F, F, F, F, T, T, T, T, F]
    assert out["flip"].tolist() == [F, F, T, F, T, F, F, F, F, T, F, F, F, T]
    assert out["hs_bar"].tolist() == [-1, -1, -1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 11, 11]
    assert same(out["hs_price"], [NAN] * 3 + [10.0] * 9 + [9.5] * 2)
    assert out["ls_bar"].tolist() == [-1] * 8 + [7] * 6
    assert same(out["ls_price"], [NAN] * 8 + [7.0] * 6)
    assert out["f_dir"].tolist() == [0] * 8 + [-1, -1, -1, -1, 1, 1]
    assert same(out["f_lo"], [NAN] * 8 + [7.0] * 6) and same(out["f_hi"], [NAN] * 8 + [10.0] * 4 + [9.5] * 2)
    lg = out["legs"]
    assert lg["flip_bar"].tolist() == [2, 4, 9, 13] and lg["dir"].tolist() == [-1, 1, -1, 1]
    assert same(lg["atr_at_flip"], [1.375, 1.125, 1.0, 1.125])


# ───────────────────────────── 1. the nine traps of the map (3.6 "Risks") ─────────────────────────────

def test_risk1_ta_highest_reads_high():
    """``ta.highest(swingLen)`` / ``ta.lowest(swingLen)`` (l.66-67) read high / low, not the close. Bar 3 closes at
    its high 11.5, the highest CLOSE of bars 1-3, but bar 1's high 12 is the highest HIGH: no new high, no flip.
    Read from the close, bar 3 is a new high (11.5 == max(10, 8.5, 11.5)) and the direction flips to true."""
    bars = arr([(10.0, 11.0, 9.0, 10.25, 1), (10.25, 12.0, 9.5, 10.0, 1), (10.0, 10.5, 8.0, 8.5, 1),
                (8.5, 11.5, 8.4, 11.5, 1)])
    out, wrong = run_both(bars, swing_len=3, atr_len=1, source="close")
    assert out["is_down_move"].tolist() == [False] * 4 and not out["flip"].any()
    sw = SP.swings(bars[1], bars[2], 3)
    assert same(sw["highest"], [NAN, NAN, 12.0, 12.0]) and same(sw["lowest"], [NAN, NAN, 8.0, 8.0])
    assert sw["new_low"].tolist() == [False, False, True, False] and not sw["new_high"].any()
    assert out["ls_bar"].tolist() == [-1, -1, -1, 2] and out["ls_price"][3] == 8.0   # bar 2's low, confirmed at 3
    assert wrong["is_down_move"].tolist() == [False, False, False, True] and wrong["flip"].tolist()[3]


def test_risk2_strict_confirmation_one_bar_late_and_not_when_the_next_high_equals_it():
    """l.75 / l.80: ``high[1] == highestSwingHigh[1] and high < highestSwingHigh`` (strict). Highs 10, 11, 12, 12,
    11.5, 13, 12.5: bar 2's 12 is NOT stored (bar 3's equal 12 is itself the 3-bar high); bar 3's 12 is stored at bar
    4, one bar late, with index 3; bar 5's 13 is stored at bar 6. With ``<=`` bar 2 would be stored at bar 3.
    The low side mirrors it with ``>``: lows 10, 9.5, 9, 9, 9.5 store (3, 9) at bar 4."""
    bars = hl_bars([10, 11, 12, 12, 11.5, 13, 12.5], [8, 8.5, 9, 10, 10.5, 11, 11.5])
    out, wrong = run_both(bars, swing_len=3, atr_len=1, confirm="loose")
    assert out["hs_bar"].tolist() == [-1, -1, -1, -1, 3, 3, 5]
    assert same(out["hs_price"], [NAN] * 4 + [12.0, 12.0, 13.0])
    assert wrong["hs_bar"].tolist() == [-1, -1, -1, 2, 3, 3, 5]
    lows = hl_bars([12, 11.5, 11, 10.5, 10.75], [10, 9.5, 9, 9, 9.5])
    out, wrong = run_both(lows, swing_len=3, atr_len=1, confirm="loose")
    assert out["ls_bar"].tolist() == [-1, -1, -1, -1, 3] and out["ls_price"][4] == 9.0
    assert wrong["ls_bar"].tolist() == [-1, -1, -1, 2, 3]


def test_risk3_low_wins_on_a_bar_that_is_both_extremes():
    """l.69-72: ``isDownMove := true`` on a new high, THEN ``:= false`` on a new low. Bar 3 (high 12, low 8) is the
    3-bar high and the 3-bar low: false, a flip to false (dir +1). Bar 4 is neither, so it confirms bar 3 on both
    sides: both stored swings are bar 3 and the forming leg's direction is 0. High-first would keep true."""
    bars = hl_bars([10.0, 10.5, 11.0, 12.0, 11.5], [9.0, 9.5, 10.0, 8.0, 8.5])
    out, wrong = run_both(bars, swing_len=3, atr_len=1, both="high_wins")
    assert out["is_down_move"].tolist() == [False, False, True, False, False]
    assert out["flip"].tolist() == [False, False, True, True, False]
    assert out["legs"]["dir"].tolist() == [-1, 1]
    assert out["hs_bar"][4] == 3 and out["ls_bar"][4] == 3 and out["f_dir"][4] == 0
    assert out["f_lo"][4] == 8.0 and out["f_hi"][4] == 12.0
    assert wrong["is_down_move"].tolist() == [False, False, True, True, True]
    assert wrong["flip"].tolist() == [False, False, True, False, False]


def test_risk4_bar_span_is_prev_to_last_swing_both_included():
    """l.113-125: the loop reads ``close[i]`` for i = bar_index - lastSwingIndex .. bar_index - prevSwingIndex, i.e.
    the bars from the older swing (2) to the newer swing (7), both included. The bars after the newer swing, 8 and the
    flip bar 9 (volume 100 at 7.5), are not read. Down leg at bar 9: bins of 0.5 from 7.0 (6 bins):
    bar 7 -> bin 0 (+6), 6 -> 1, 2 (+5), 5 -> 2 (+4), 4 -> 3, 4 (+3), 3 -> 4, 5 (+2), 2 -> 5 (+1): [6, 5, 9, 3, 5, 3],
    POC bin 2 = 8.25. Read up to the flip bar, bars 8 and 9 add 101 to bins 0 and 1: POC 7.25."""
    out, wrong = run_both(arr(LEGS), **HAND, span="to_bar")
    r = leg_row(out, 9)
    assert (r["start_bar"], r["end_bar"]) == (2, 7)
    assert r["poc"] == 8.25 and r["poc_all"] == (8.25,) and r["total"] == 31.0
    p = SP.leg_profile(*(arr(LEGS)[i] for i in (0, 3, 4)), 2, 10.0, 7, 7.0, 0.5, 7.5)
    assert p["vol"].tolist() == [6, 5, 9, 3, 5, 3] and p["n_bins"] == 6 and p["step"] == 0.5
    w = leg_row(wrong, 9)
    assert w["poc"] == 7.25 and w["total"] == 31.0 + 2 * 101


def test_risk5_double_counting_into_two_bins():
    """l.131-136: every bin whose midpoint is LESS than one step from the close gets the bar's volume. In the down leg
    (bins of 0.5 from 7.0, midpoints 7.25 .. 9.75): bar 6's close 7.875 (inside bin 1) counts in bins 1 and 2, bar 4's
    8.875 in bins 3 and 4, bar 3's 9.5 (a boundary) in bins 4 and 5; bar 5's 8.25 (a midpoint: its neighbours are
    exactly one step away) only in bin 2; bar 2's 9.875 and bar 7's 7.125 (outer halves of the edge bins) only in their
    bin. Total 31 = 6 + 2*5 + 4 + 2*3 + 2*2 + 1. One bin per bar (the bin holding the close) gives [6, 5, 4, 3, 0, 3]
    (total 21, POC 7.25); ``<=`` gives bar 5 three bins ([6, 9, 9, 7, 5, 3]: total 39, a tie)."""
    out, single = run_both(arr(LEGS), **HAND, bins="single")
    r = leg_row(out, 9)
    assert r["total"] == 31.0 and r["poc"] == 8.25
    w = leg_row(single, 9)
    assert w["total"] == 21.0 and w["poc"] == 7.25
    le = leg_row(PineScript(**HAND, bins="le").run(*arr(LEGS)), 9)
    assert le["total"] == 39.0 and le["poc_all"] == (7.75, 8.25) and le["poc"] == 7.75
    # each close on its own (volume 1 at bar 0, the leg is bar 0 alone): bins of 0.5 from 7.0
    for close, bins in ((8.25, [2]), (8.5, [2, 3]), (8.375, [2, 3]), (8.125, [1, 2]), (7.125, [0]), (9.875, [5])):
        p = SP.leg_profile([0.0], [close], [1.0], 0, 10.0, 0, 7.0, 0.5, close)
        assert np.flatnonzero(p["vol"]).tolist() == bins, close


def test_risk6_int_truncation_of_the_bin_count():
    """l.110: ``binCount = int(|H - L| / priceBinSize)`` truncates. Forming leg at bar 11 (the pair 10.0 / 7.0, ATR
    1.25): 3.0 / 0.625 = 4.8 -> 4 bins of 0.75 (midpoints 7.375, 8.125, 8.875, 9.625): bar 7 -> bin 0 (+6), 6 -> 0, 1
    (+5), 5 -> 1, 2 (+4), 4 -> 2 (+3, a midpoint), 3 -> 2, 3 (+2), 2 -> 3 (+1) = [11, 9, 9, 3], POC 7.375. Rounded to 5
    bins of 0.6 the POC is 7.3. Same at bar 10 (ATR 1.375: 4.36 -> 4)."""
    out, wrong = run_both(arr(LEGS), **HAND, bin_count="round")
    assert out["f_poc"][11] == 7.375 and out["f_poc"][10] == 7.375
    assert out["f_total"][11] == 32.0 and out["f_delta_pct"][11] == (1.0 - 31.0) / 32.0
    p = SP.leg_profile(*(arr(LEGS)[i] for i in (0, 3, 4)), 2, 10.0, 7, 7.0, 0.625, 9.25)
    assert p["n_bins"] == 4 and p["step"] == 0.75 and p["vol"].tolist() == [11, 9, 9, 3]
    assert wrong["f_poc"][11] == (7.0 + (7.0 + 0.6)) / 2 and wrong["f_poc"][11] != 7.375


def test_risk7_ties_go_to_the_tied_bin_nearest_the_close():
    """l.149-154 draws a POC line for every bin equal to the maximum; the plan takes the tied bin nearest the close of
    the bar that uses it. With bar 7's volume 1 instead of 6, the up leg at the flip bar 13 (bins of 0.625 from 7.0,
    ATR 1.125) has bins [102, 102, 1, 1]: bars 9 (+100), 8 (+1), 7 (+1) in bin 0, bars 10 (+1), 9 (+100), 8 (+1) in
    bin 1. Levels 7.3125 and 7.9375; the flip bar's close 8.25 is nearer 7.9375. The lowest tied bin would be 7.3125."""
    bars = legs_bars(v7=1)
    out, wrong = run_both(bars, **HAND, ties="first")
    r = leg_row(out, 13)
    assert r["poc_all"] == (7.3125, 7.9375) and r["poc"] == 7.9375
    assert r["total"] == 206.0 and r["delta_pct"] == (205.0 - 1.0) / 206.0
    assert out["f_poc"][13] == 7.9375 and out["f_poc_ties"][13] == 2
    assert leg_row(wrong, 13)["poc"] == 7.3125
    # an exactly equal distance goes to the lower bin: the close 7.625 is 0.3125 from both levels
    p = SP.leg_profile(*(bars[i] for i in (0, 3, 4)), 11, 9.5, 7, 7.0, 0.5625, 7.625)
    assert p["poc_all"] == (7.3125, 7.9375) and p["poc"] == 7.3125 and p["poc_ties"] == 2


def test_risk8_atr200_taken_at_the_flip_bar():
    """l.85 runs on every bar; the flip block (l.90) uses the flip bar's value. The down leg at bar 9 takes ATR 1.0
    (bins of 0.5: 6 bins, POC 8.25). The ATR of its newer swing bar 7 is 1.125 (5 bins of 0.6, POC 7.3). The forming
    leg uses the current bar's ATR: the same pair 10.0 / 7.0 has POC 8.25 at bar 8 (ATR 1.0, 6 bins) and 7.375 at bar
    10 (ATR 1.375, 4 bins)."""
    out, wrong = run_both(arr(LEGS), **HAND, atr_at="newer_swing")
    r = leg_row(out, 9)
    assert r["atr_at_flip"] == 1.0 and r["poc"] == 8.25
    w = leg_row(wrong, 9)
    assert w["poc"] == (7.0 + (7.0 + 0.6)) / 2 and w["total"] == 35.0      # [11, 9, 7, 5, 3]
    assert out["hs_bar"][8] == out["hs_bar"][10] == 2 and out["ls_bar"][8] == out["ls_bar"][10] == 7
    assert out["f_poc"][8] == 8.25 and out["f_poc"][10] == 7.375


def test_risk9_naming_isdownmove_true_finishes_a_down_leg():
    """l.60 "true = down move", l.99 / 181: the flip to TRUE (a new high, bar 9) finishes the DOWN leg (orange, "v"),
    from the older swing high (2, 10.0) to the newer swing low (7, 7.0): dir -1. The flip to FALSE (a new low, bar 13)
    finishes the UP leg (lime, "^") from the low (7, 7.0) to the high (11, 9.5): dir +1. Up leg at ATR 1.125: 2.5 /
    0.5625 = 4.44 -> 4 bins of 0.625 from 7.0: bars 11 -> 3, 10 -> 1, 2, 9 -> 0, 1 (+100), 8 -> 0, 1, 7 -> 0 (+6):
    [107, 102, 1, 1], POC 7.3125, buy 205 (bars 8-11 close above their open), sell 6."""
    out, wrong = run_both(arr(LEGS), **HAND, dir_naming="swapped")
    d, u = leg_row(out, 9), leg_row(out, 13)
    assert d["dir"] == -1 and (d["start_bar"], d["end_bar"], d["lo"], d["hi"]) == (2, 7, 7.0, 10.0)
    assert out["hs_bar"][9] < out["ls_bar"][9]                      # the high is the older end of the down leg
    assert u["dir"] == 1 and (u["start_bar"], u["end_bar"], u["lo"], u["hi"]) == (7, 11, 7.0, 9.5)
    assert u["poc"] == 7.3125 and u["total"] == 211.0 and u["delta_pct"] == (205.0 - 6.0) / 211.0
    assert u["fifty"] == 8.25 and d["fifty"] == 8.5
    assert leg_row(wrong, 9)["dir"] == 1 and leg_row(wrong, 13)["dir"] == -1


# ───────────────────────────── 2. the rest of the map's test list ─────────────────────────────

def test_down_leg_by_hand_delta_and_total():
    """The down leg at bar 9 in full: buy [0, 0, 0, 0, 0, 1] (only bar 2 closes above its open), sell [6, 5, 9, 3, 5,
    2]; total 31; delta (1 - 30) / 31; fifty 8.5; ATR 1.0. The forming leg at bar 9 is the same leg."""
    out, _ = run_both(arr(LEGS), **HAND)
    r = leg_row(out, 9)
    assert r["delta_pct"] == (1.0 - 30.0) / 31.0 and r["total"] == 31.0 and r["fifty"] == 8.5
    p = SP.leg_profile(*(arr(LEGS)[i] for i in (0, 3, 4)), 2, 10.0, 7, 7.0, 0.5, 7.5)
    assert p["buy"].tolist() == [0, 0, 0, 0, 0, 1] and p["sell"].tolist() == [6, 5, 9, 3, 5, 2]
    assert out["f_poc"][9] == 8.25 and out["f_total"][9] == 31.0 and out["f_delta_pct"][9] == r["delta_pct"]
    # the forming up leg at bar 12 (ATR 0.625: 8 bins of 0.3125): [7, 101, 100, 0, 1, 1, 1, 1], POC 7.46875
    assert out["f_poc"][12] == 7.46875 and out["f_total"][12] == 212.0
    assert out["f_delta_pct"][12] == (206.0 - 6.0) / 212.0 and out["f_poc_ties"][12] == 1


def test_top_and_bottom_edges():
    """A close in the outer half of the bottom or top bin counts once; a close below the bottom (above the top) counts
    in the edge bin while it is less than half a step outside, and nowhere from half a step on. Leg 10.0 - 12.0, bins
    of 0.5 (midpoints 10.25 .. 11.75); volumes 1, 2, 4, 8, 16, 32, 64 at closes 9.875, 9.75, 12.125, 12.25, 11.875,
    10.0, 12.0."""
    closes = [9.875, 9.75, 12.125, 12.25, 11.875, 10.0, 12.0]
    vols = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
    p = SP.leg_profile(closes, closes, vols, 6, 12.0, 0, 10.0, 0.5, 11.0)
    assert p["n_bins"] == 4 and p["vol"].tolist() == [1 + 32, 0, 0, 4 + 16 + 64]
    assert p["total"] == 117.0 and p["poc"] == 11.75 and p["sell"].sum() == 117.0      # open == close: all sell


def test_doji_counts_as_sell():
    """l.138: ``if candleClose > candleOpen`` buy, else sell: bar 6 (open = close = 7.875) is sell volume. As buy,
    the down leg's delta would be (11 - 20) / 31 instead of (1 - 30) / 31."""
    out, wrong = run_both(arr(LEGS), **HAND, doji="buy")
    assert leg_row(out, 9)["delta_pct"] == (1.0 - 30.0) / 31.0
    assert leg_row(wrong, 9)["delta_pct"] == (11.0 - 20.0) / 31.0


def test_skips_a_swing_missing_the_atr_na_bincount_zero_and_empty_bins():
    """(a) Flips 2 and 4 come before a swing pair exists: rows with start / end -1 and NaN values, the ATR kept.
    (b) atr_len 20 on 14 bars: the ATR is na everywhere; the legs keep their geometry, the profile values are NaN.
    (c) Bar 9's high 15.0 makes its ATR 7.75: bins of 3.875 for a 3.0 leg, ``binCount == 0``.
    (d) Zero volume everywhere: bins exist but are empty: total 0, no POC, delta NaN (0 / 0, l.149 / 187)."""
    out, _ = run_both(arr(LEGS), **HAND)
    for f, atr in ((2, 1.375), (4, 1.125)):
        r = leg_row(out, f)
        assert (r["start_bar"], r["end_bar"], r["poc_all"]) == (-1, -1, ())
        assert all(math.isnan(r[k]) for k in ("lo", "hi", "poc", "delta_pct", "total", "fifty"))
        assert r["atr_at_flip"] == atr
    assert np.isnan(out["f_poc"][:8]).all() and (out["f_poc_ties"][:8] == 0).all()
    assert np.isnan(out["f_total"][:8]).all() and np.isnan(out["f_delta_pct"][:8]).all()

    na, _ = run_both(arr(LEGS), swing_len=3, atr_len=20, bin_mult=0.5)
    assert np.isnan(na["f_poc"]).all() and (na["f_poc_ties"] == 0).all() and np.isnan(na["f_total"]).all()
    assert same(na["f_lo"], out["f_lo"]) and same(na["f_hi"], out["f_hi"])
    r = leg_row(na, 9)
    assert (r["start_bar"], r["end_bar"], r["lo"], r["hi"], r["fifty"]) == (2, 7, 7.0, 10.0, 8.5)
    assert math.isnan(r["poc"]) and math.isnan(r["total"]) and math.isnan(r["atr_at_flip"]) and r["poc_all"] == ()

    zero, _ = run_both(legs_bars(h9=15.0), **HAND)
    r = leg_row(zero, 9)
    assert r["atr_at_flip"] == 7.75 and (r["lo"], r["hi"]) == (7.0, 10.0)
    assert math.isnan(r["poc"]) and math.isnan(r["total"]) and math.isnan(r["delta_pct"]) and r["poc_all"] == ()
    assert math.isnan(zero["f_poc"][9]) and zero["f_poc_ties"][9] == 0 and zero["f_lo"][9] == 7.0

    o, h, l, c, _ = arr(LEGS)
    empty, _ = run_both((o, h, l, c, np.zeros(len(c))), **HAND)
    r = leg_row(empty, 9)
    assert r["total"] == 0.0 and math.isnan(r["poc"]) and math.isnan(r["delta_pct"]) and r["poc_all"] == ()
    assert empty["f_total"][9] == 0.0 and empty["f_poc_ties"][9] == 0


def test_bin_count_above_pines_array_limit_is_not_computable():
    """Reading 5: ``array.new<float>(binCount, 0.)`` (l.117) beyond Pine's limit of 100,000 elements is a runtime
    error, so such a leg is not computable (NaN), like ``binCount == 0``. A leg 0 .. 100,000 with bins of 1.0 has
    exactly 100,000 bins and is computed: closes 50,000.25 (bins 49,999 and 50,000) and 99,999.75 (the top bin's
    outer half: bin 99,999 only, volume 2), POC (99,999 + 100,000) / 2, total 4, all doji (sell). 0 .. 100,001 has
    100,001 bins: not computable; so is a quotient that overflows to infinity (the smallest double as the bin size).
    Through the indicator: bar 8 of the hand legs (it confirms the swing low (7, 7.0)) with a true range of 2^-17
    (ATR 1) gives the forming leg 10.0 / 7.0 bins of 2^-18, i.e. 786,432 bins: NaN (this port computed it before the
    reconciliation; it raised above 1,000,000 bins). Bar 9 still flips, with the ATR 1.125: 5 bins, computed."""
    closes, vols = [50_000.25, 99_999.75], [1.0, 2.0]
    p = SP.leg_profile(closes, closes, vols, 1, 100_000.0, 0, 0.0, 1.0, 99_999.75)
    assert p["n_bins"] == 100_000 and p["step"] == 1.0 and p["poc"] == 99_999.5 and p["poc_ties"] == 1
    assert p["total"] == 4.0 and p["delta_pct"] == -1.0
    assert np.flatnonzero(p["vol"]).tolist() == [49_999, 50_000, 99_999]
    for hi, size in ((100_001.0, 1.0), (100_000.0, 5e-324)):
        q = SP.leg_profile(closes, closes, vols, 1, hi, 0, 0.0, size, 99_999.75)
        assert q["n_bins"] == 0 and math.isnan(q["poc"]) and math.isnan(q["total"]) and q["poc_all"] == ()
    bars = legs_bars(o8=7.125, h8=7.125 + 2.0 ** -17, l8=7.125, c8=7.125)
    out, _ = run_both(bars, **HAND)
    assert I.atr(bars[1], bars[2], bars[3], 1)[8] == 2.0 ** -17
    assert (out["hs_bar"][8], out["ls_bar"][8], out["f_lo"][8], out["f_hi"][8]) == (2, 7, 7.0, 10.0)
    assert math.isnan(out["f_poc"][8]) and math.isnan(out["f_total"][8]) and out["f_poc_ties"][8] == 0
    r = leg_row(out, 9)
    assert r["atr_at_flip"] == 1.125 and r["poc"] == (7.0 + (7.0 + 0.6)) / 2 and r["poc_all"] == (r["poc"],)


def test_forming_leg_equals_the_finished_leg_at_the_next_flip():
    """The forming leg at bar t is the leg the next flip finishes when no swing point changes in between and the
    bin count is the same (the ATR moves the bins only through ``binCount``): bar 8 (ATR 1.0, the pair confirmed at
    bar 8) equals the down leg finished at bar 9 (ATR 1.0). On random bars: every bar between a flip's last swing
    change and the flip, with the flip's bin count, has the flip leg's total, delta and tied levels."""
    out, _ = run_both(arr(LEGS), **HAND)
    r = leg_row(out, 9)
    assert (out["f_poc"][8], out["f_total"][8], out["f_delta_pct"][8]) == (r["poc"], r["total"], r["delta_pct"])
    for seed in range(4):
        o, h, l, c, v = random_bars(seed, 2500, grid=0.25 if seed % 2 else 0.0)
        out = SP.swing_profile(o, h, l, c, v, swing_len=12, atr_len=30)
        atr = I.atr(h, l, c, 30)
        hsb, lsb = out["hs_bar"], out["ls_bar"]
        checked = 0
        for _, row in out["legs"].iterrows():
            f = int(row["flip_bar"])
            if math.isnan(row["poc"]):
                continue
            s = f
            while s > 0 and hsb[s - 1] == hsb[f] and lsb[s - 1] == lsb[f]:
                s -= 1
            nb_f = SP.leg_profile(o, c, v, hsb[f], h[hsb[f]], lsb[f], l[lsb[f]], atr[f] * 0.5, c[f])["n_bins"]
            for t in range(s, f + 1):
                p = SP.leg_profile(o, c, v, hsb[t], h[hsb[t]], lsb[t], l[lsb[t]], atr[t] * 0.5, c[t])
                if p["n_bins"] != nb_f:
                    continue
                assert out["f_total"][t] == row["total"] and same(out["f_delta_pct"][t], row["delta_pct"])
                assert p["poc_all"] == row["poc_all"] and out["f_poc"][t] in row["poc_all"]
                checked += 1
        assert checked > 50, seed


def test_dir_is_the_flips_side_not_the_geometry():
    """Bar 9 (high 9.75, low 6.0) is both a 3-bar high and a 3-bar low after an up move whose last high (bar 8) is
    still unconfirmed (bar 9's high is not below the window's high): the flip to false finishes "the up leg" (dir +1,
    l.99), but the stored pair is still the previous down leg, high (3, 9.5) older than low (5, 6.5). The row keeps
    the flip's side; ``f_dir`` shows the geometry (-1)."""
    bars = hl_bars([10.0, 9.5, 9.0, 9.5, 9.25, 9.0, 8.0, 8.5, 9.25, 9.75],
                   [9.0, 8.0, 7.0, 7.5, 8.5, 6.5, 6.75, 7.0, 7.5, 6.0])
    out, _ = run_both(bars, swing_len=3, atr_len=1)
    assert out["legs"]["flip_bar"].tolist() == [3, 5, 8, 9] and out["legs"]["dir"].tolist() == [-1, 1, -1, 1]
    r = leg_row(out, 9)
    assert (r["start_bar"], r["end_bar"], r["lo"], r["hi"]) == (3, 5, 6.5, 9.5)
    assert out["hs_bar"][9] == 3 and out["ls_bar"][9] == 5 and out["f_dir"][9] == -1
    assert (leg_row(out, 5)["start_bar"], leg_row(out, 5)["end_bar"]) == (2, 3)     # the normal up leg


def test_warm_up_nothing_before_the_window_is_full():
    """``ta.highest(50)`` / ``ta.lowest(50)`` are na on bars 0-48: no event, no flip, no swing before bar 49; the
    first confirmation can come at bar 50 (of bar 49). Bar 0 is never a flip (v6: ``isDownMove[1]`` is false)."""
    o, h, l, c, v = random_bars(3, 400)
    out = SP.swing_profile(o, h, l, c, v)
    sw = SP.swings(h, l, 50)
    assert np.isnan(sw["highest"][:49]).all() and np.isfinite(sw["highest"][49:]).all()
    assert not out["flip"][:49].any() and not out["is_down_move"][:49].any()
    assert (out["hs_bar"][:50] == -1).all() and (out["ls_bar"][:50] == -1).all()
    assert np.isnan(out["f_poc"][:199]).all()                                    # the ATR(200) is na until bar 199
    rising = np.arange(60.0)
    up = SP.swing_profile(rising, rising + 1, rising - 1, rising + 0.5, np.ones(60), swing_len=50, atr_len=5)
    assert up["flip"].tolist().index(True) == 49 and up["is_down_move"][49:].all()


def test_output_keys_dtypes_and_inputs():
    o, h, l, c, v = random_bars(5, 700)
    out = SP.swing_profile(o, h, l, c, v, swing_len=20, atr_len=50)
    assert tuple(out) == SP.KEYS and tuple(out["legs"].columns) == SP.LEG_COLUMNS
    dt = {"is_down_move": np.bool_, "flip": np.bool_, "hs_bar": np.int64, "ls_bar": np.int64, "f_dir": np.int8,
          "f_poc_ties": np.int64}
    for k in ARRAY_KEYS:
        assert out[k].shape == (700,), k
        assert out[k].dtype == dt.get(k, np.float64), k
    lg = out["legs"]
    assert lg["flip_bar"].dtype == np.int64 and lg["dir"].dtype == np.int8 and lg["poc_all"].dtype == object
    assert lg["flip_bar"].tolist() == np.flatnonzero(out["flip"]).tolist()
    assert np.all(lg["dir"].to_numpy()[1:] == -lg["dir"].to_numpy()[:-1])         # flips alternate
    for x in (o, h, l, c, v):
        before = x.copy()
        SP.swing_profile(o, h, l, c, v, swing_len=20, atr_len=50)
        assert np.array_equal(x, before)                                         # inputs untouched
    empty = SP.swing_profile([], [], [], [], [])
    assert all(len(empty[k]) == 0 for k in ARRAY_KEYS) and len(empty["legs"]) == 0
    assert tuple(empty["legs"].columns) == SP.LEG_COLUMNS
    with pytest.raises(ValueError):
        SP.swing_profile(o, h, l, c, v[:-1])
    with pytest.raises(ValueError):
        SP.swing_profile(o, h, l, np.r_[c[:-1], np.nan], v)
    with pytest.raises(ValueError):
        SP.swing_profile(o, h, l, c, -v)
    for bad in (dict(swing_len=0), dict(atr_len=2.5), dict(bin_mult=0.0), dict(swing_len=True)):
        with pytest.raises(ValueError):
            SP.swing_profile(o, h, l, c, v, **bad)


# ───────────────────────────── 3. random bars: the port against the transcription ─────────────────────────────

def random_bars(seed, n, grid=0.0, volume="ticks"):
    """A random walk with wicks; ``grid`` > 0 rounds every price to multiples of it (equal highs, closes on bin
    edges, ties); ``volume`` "ticks" (integers) or "float" (Binance-like, 8 decimals)."""
    r = np.random.default_rng(seed)
    c = 1000.0 + np.cumsum(r.standard_t(4, n) * 2.0)
    o = np.r_[c[0], c[:-1]] + r.normal(0, 0.5, n)
    h = np.maximum(o, c) + r.exponential(1.0, n)
    l = np.minimum(o, c) - r.exponential(1.0, n)
    if grid:
        o, h, l, c = (np.round(x / grid) * grid for x in (o, h, l, c))
        h, l = np.maximum(h, np.maximum(o, c)), np.minimum(l, np.minimum(o, c))
    if volume == "ticks":
        v = r.integers(1, 40, n).astype(np.float64)
    else:
        v = np.round(r.lognormal(3.0, 1.0, n), 8)
        v[r.random(n) < 0.01] = 0.0                                              # an hour without a kline
    return o, h, l, c, v


@pytest.mark.parametrize("seed,grid,volume,kw", [
    (0, 0.0, "ticks", dict(swing_len=10, atr_len=14)),
    (1, 0.25, "ticks", dict(swing_len=10, atr_len=14)),
    (2, 1.0, "ticks", dict(swing_len=8, atr_len=20, bin_mult=1.0)),
    (3, 0.0, "float", dict(swing_len=12, atr_len=30)),
    (4, 0.5, "float", dict(swing_len=15, atr_len=40, bin_mult=0.25)),
    (5, 0.0, "ticks", dict(swing_len=3, atr_len=1)),
])
def test_port_equals_the_transcription_bit_for_bit_on_random_bars(seed, grid, volume, kw):
    bars = random_bars(seed, 900, grid, volume)
    port = SP.swing_profile(*bars, **kw)
    ref = PineScript(**kw).run(*bars)
    assert outputs_equal(port, ref)
    assert len(port["legs"]) > 20
    if grid:
        assert (port["f_poc_ties"] > 1).any()                                    # the coarse grids do make ties


def test_port_equals_the_transcription_with_the_defaults():
    bars = random_bars(11, 1400, 0.0, "float")
    port = SP.swing_profile(*bars)
    ref = PineScript().run(*bars, forming_at=range(0, 1400, 2))
    m = np.zeros(1400, bool)
    m[::2] = True
    assert outputs_equal(port, ref, forming=m)
    lg = port["legs"]
    assert np.isfinite(port["f_poc"][250:]).all() and lg.loc[lg["flip_bar"] >= 250, "poc"].notna().all()


def test_the_volume_ratio_test_equals_the_maximum_test():
    """Reading 7: ``volumeBins.get(k) / volumeBins.max() == 1`` (the transcription) and ``volumeBins[k] == max``
    (the port) pick the same bins, also with Binance-like float volumes summed in the script's order."""
    for seed in range(6, 10):
        bars = random_bars(seed, 800, 0.5 if seed % 2 else 0.0, "float")
        port = SP.swing_profile(*bars, swing_len=10, atr_len=14)
        ref = PineScript(swing_len=10, atr_len=14).run(*bars)
        assert np.array_equal(port["f_poc_ties"], ref["f_poc_ties"]) and same(port["f_poc"], ref["f_poc"])


# ───────────────────────────── 4. truncation invariance ─────────────────────────────

@pytest.mark.parametrize("seed", [0, 1])
def test_outputs_to_t_do_not_change_when_the_bars_after_t_are_removed(seed):
    bars = random_bars(seed, 1500, 0.25 * seed)
    full = SP.swing_profile(*bars, swing_len=20, atr_len=60)
    for T in (0, 1, 19, 59, 60, 333, 777, 1001, 1498):
        part = SP.swing_profile(*[x[:T + 1] for x in bars], swing_len=20, atr_len=60)
        assert outputs_equal(part, full, T + 1), T
    # and changing the bars after t changes nothing up to t
    t = 900
    other = [x.copy() for x in bars]
    for x in other:
        x[t + 1:] = x[t + 1:][::-1].copy()
    alt = SP.swing_profile(*other, swing_len=20, atr_len=60)
    assert outputs_equal(alt, full, t + 1)


# ───────────────────────────── 5. real bars (to 2024-06-30, the guard closed) ─────────────────────────────

TFS = ("1H", "4H")                    # PREREG 6.4
A19, A23 = TM.s_of("2019-01-01"), TM.s_of("2023-01-01")


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H bars of a symbol from its data start to 2024-06-30 (``load(symbol, end="2024-07-01")`` with
    the guard pointed at an empty folder) and the volume the plan gives it: gold's tick volume, BTC's Binance
    BTCUSDT volume. One symbol in memory at a time; the market is dropped once the bars are taken."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            cache.clear()
            gc.collect()
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end="2024-07-01")
                out = {}
                for tf in TFS:
                    b = mk.tbars(tf)
                    d = {"t": b.t.copy(), "tc": b.tc.copy(), "o": b.o.copy(), "h": b.h.copy(), "l": b.l.copy(),
                         "c": b.c.copy()}
                    if symbol.startswith("BTC"):
                        if not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.CUT_S):
                            pytest.skip("the Binance klines are not on this machine")
                        d["v"] = np.asarray(TM.binance_volume(mk, tf)[0], np.float64)
                    else:
                        d["v"] = b.vol.astype(np.float64)
                    out[tf] = d
            del mk
            gc.collect()
            cache[symbol] = out
        return cache[symbol]
    return get


def _bars_of(d, upto=None):
    return tuple(d[k][:upto] for k in ("o", "h", "l", "c", "v"))


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_smoke(symbol, real):
    for tf in TFS:
        d = real(symbol)[tf]
        n = len(d["c"])
        assert n > 10000 and int(d["tc"][-1]) <= TM.CUT_S, tf                     # nothing from the hold-out
        assert np.isfinite(d["v"]).all() and (d["v"] >= 0).all()
        out = SP.swing_profile(*_bars_of(d))
        assert tuple(out) == SP.KEYS
        for k in ARRAY_KEYS:
            assert out[k].shape == (n,), (tf, k)
        hsb, lsb = out["hs_bar"], out["ls_bar"]
        # NaN exactly where the contract says no value exists
        assert same(np.isnan(out["hs_price"]), hsb < 0) and same(np.isnan(out["ls_price"]), lsb < 0)
        both = (hsb >= 0) & (lsb >= 0)
        for k in ("f_lo", "f_hi"):
            assert np.isfinite(out[k][both]).all() and np.isnan(out[k][~both]).all(), (tf, k)
        atr = I.atr(d["h"], d["l"], d["c"], 200)
        with np.errstate(invalid="ignore"):
            nb = np.where(both & np.isfinite(atr), np.abs(out["hs_price"] - out["ls_price"]) / (atr * 0.5), 0.0)
        computable = both & np.isfinite(atr) & (nb >= 1.0)
        assert np.isfinite(out["f_poc"][computable]).all() and np.isnan(out["f_poc"][~computable]).all(), tf
        assert np.isfinite(out["f_total"][computable]).all() and (out["f_total"][computable] > 0).all(), tf
        assert np.isnan(out["f_total"][~computable]).all(), tf
        dl = out["f_delta_pct"][computable]
        assert np.isfinite(dl).all() and (np.abs(dl) <= 1.0).all(), tf
        assert (out["f_poc_ties"][computable] >= 1).all() and (out["f_poc_ties"][~computable] == 0).all(), tf
        on = computable & (out["f_poc"] >= out["f_lo"]) & (out["f_poc"] <= out["f_hi"])
        assert np.array_equal(on, computable), tf                               # the POC is inside the leg
        # from 2019 on every bar has a forming leg, and every finished leg a profile
        s19 = int(np.searchsorted(d["tc"], A19, side="right"))
        assert computable[s19:].all(), tf
        # f_dir is the geometry; 0 only where both stored swings are the same (outside) bar, which 1H bars do have
        assert np.array_equal(out["f_dir"][both], np.sign(hsb - lsb)[both]) and (out["f_dir"][~both] == 0).all()
        lg = out["legs"]
        assert lg["flip_bar"].tolist() == np.flatnonzero(out["flip"]).tolist()
        late = lg[lg["flip_bar"] >= s19]
        assert late[list(LEG_FLOATS)].notna().all().all(), tf
        assert ((late["start_bar"] <= late["end_bar"]) & (late["end_bar"] < late["flip_bar"])).all(), tf
        assert ((late["lo"] < late["hi"]) & (late["poc"] >= late["lo"]) & (late["poc"] <= late["hi"])).all(), tf
        assert all(p in a for p, a in zip(late["poc"], late["poc_all"])), tf
        assert same(late["fifty"], (late["lo"] + late["hi"]) / 2) and (late["atr_at_flip"] > 0).all(), tf
        assert same(late["poc"], out["f_poc"][late["flip_bar"].to_numpy()]), tf
        assert (late["flip_bar"] - late["start_bar"]).max() < 5000, tf             # max_bars_back (l.6) is never hit
        # legs per year closing 2019-2022 near the map's probe (gold 77 / 21, BTC 117 / 27 per year)
        dev = lg[(d["tc"][lg["flip_bar"]] > A19) & (d["tc"][lg["flip_bar"]] <= A23)]
        per_year = len(dev) / 4.0
        lo_hi = {("XAUUSDm", "1H"): (60, 95), ("XAUUSDm", "4H"): (15, 28), ("BTCUSDm", "1H"): (95, 140),
                 ("BTCUSDm", "4H"): (20, 34)}[(symbol, tf)]
        assert lo_hi[0] <= per_year <= lo_hi[1], (tf, per_year)


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_equal_the_transcription_bit_for_bit(symbol, real):
    """Every finished leg from the data start, and the forming leg on 300 random bars and every flip bar's
    neighbours, against the all-bins transcription."""
    r = np.random.default_rng(7)
    for tf in TFS:
        d = real(symbol)[tf]
        n = len(d["c"])
        port = SP.swing_profile(*_bars_of(d))
        fb = np.flatnonzero(port["flip"])
        sample = np.unique(np.r_[r.choice(np.arange(200, n), 300, replace=False), fb[-40:] - 1, fb[-40:]])
        ref = PineScript().run(*_bars_of(d), forming_at=sample)
        m = np.zeros(n, bool)
        m[sample] = True
        assert outputs_equal(port, ref, forming=m), tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_truncation_invariance(symbol, real):
    for tf in TFS:
        d = real(symbol)[tf]
        full = SP.swing_profile(*_bars_of(d))
        for when in ("2020-03-16 12:00", "2022-11-09 00:00"):
            j = int(np.searchsorted(d["tc"], TM.s_of(when), side="right")) - 1
            part = SP.swing_profile(*_bars_of(d, j + 1))
            assert outputs_equal(part, full, j + 1), (tf, when)
