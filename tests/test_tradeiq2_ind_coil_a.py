"""
Port A of the coil breakout (``backtesting/research/tradeiq2_ind_coil.py``; PREREG 6.9 of
``backtest_results/tradeiq_2027/PREREG.md``, which is the whole specification: the script is private and has no source).

1. One hand-computed test per trap, named after it: the contract's edge cases (a run of exactly 5 and of 6; a breakout
   on the 12th and on the 13th armed bar; a newer coil replacing an armed one; a close exactly at the box edge) and the
   other traps of the rule and of the platform's built-ins that the port's docstring lists (the newer run of 5, the box
   over the whole run, the squeeze fire bar, once per coil, the close not the wick, the strict squeeze, the population
   deviation, the Wilder ATR width, the SMA basis, the warm-up, the squeeze as written; ``ta.dmi``'s true range, its
   directional-movement ties, its ``sum == 0`` guard and ``fixnan``, its first value). The expected values are written
   out by hand. Each test also runs the wrong reading on the same bars (``Transcription``, a plain-Python bar-by-bar
   transcription of the rule with one switch per misreading) and checks that it answers differently.
2. The port against the transcription on random bars, bit for bit (also with other inputs), and the ADX against
   ``ladder_ind.adx`` (another study's Wilder ADX, another order of operations).
3. Truncation invariance: the outputs up to bar T do not change when the bars after T are removed.
4. Real bars (skipped when the tick store is absent): both symbols, 1H / 4H / 1D (PREREG 6.9), from the data start to
   2024-06-30 with the hold-out guard closed: the NaN pattern of the contract, ranges and structure, the transcription
   bit for bit, the ADX against ``ladder_ind.adx``, truncation.

Many hand cases use ``bb_len = kc_len = 1``, where the squeeze is exactly "the bar has a true range": the deviation of
one close is 0 and ``ta.atr(1)`` is the true range, so ``squeeze_on = close < close + 1.5 TR and close > close - 1.5
TR``.
A flat bar at the previous close (high = low = close = the previous close) is then the only bar without squeeze, which
lets a test place squeeze bars, runs and arming bars exactly. The default 20 / 2.0 / 20 / 1.5 squeeze has its own hand
cases (traps 07 and 10-14).

Every test runs with the guard pointed at an empty folder (FINALISTS.md absent: nothing at or after 2024-07-01).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import ladder_ind as LI
from backtesting.research import tradeiq2_ind_coil as C
from backtesting.research import tradeiq_market as TM

NAN = math.nan
SYMS = ("XAUUSDm", "BTCUSDm")
FLOAT_KEYS = ("box_hi", "box_lo", "bo_box_hi", "bo_box_lo", "adx")
DTYPES = {"squeeze_on": np.bool_, "run_len": np.int64, "armed": np.bool_, "box_hi": np.float64, "box_lo": np.float64,
          "breakout": np.int8, "bo_box_hi": np.float64, "bo_box_lo": np.float64, "adx": np.float64}
K1 = dict(bb_len=1, kc_len=1)          # the squeeze = "the bar has a true range" (module docstring of this file)


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


def outputs_equal(x, y, upto=None) -> bool:
    """Every key of the contract equal (floats bit for bit, NaN to NaN; bool / int exactly), on bars [0, upto)."""
    for k in C.KEYS:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if upto is not None:
            a, b = a[:upto], b[:upto]
        if k in FLOAT_KEYS:
            if not same(a, b):
                return False
        elif not np.array_equal(a.astype(np.int64), b.astype(np.int64)):
            return False
    return True


# ───────────────────────────── the transcription (the rule, bar by bar) ─────────────────────────────

def _div(a, b):
    """IEEE division as numpy does it (0 / 0 is na; never reached with a != 0 and b == 0 on bars)."""
    if b == 0.0:
        return NAN if (a == 0.0 or a != a) else math.copysign(math.inf, a)
    return a / b


class Transcription:
    """
    PREREG 6.9 and ``ta.dmi`` bar by bar in plain Python floats, written from the plan and TradingView's reference
    (``pine_sma``, ``pine_stdev``, ``pine_rma``, ``pine_ema``, ``ta.tr``, ``fixnan``, the built-in DMI script); the coil
    machine is written as a list of coils (each coil's armed window is cut by its breakout, its 12 bars, or the bar
    where the next coil's run reaches ``min_bars``) rather than the port's bar loop. Switches (default = the contract):

    * ``biased``: True = population deviation (``ta.stdev``'s default); False = the sample one.
    * ``kc_basis``: "sma" (the plan) or "ema" (``ta.kc``'s ``ta.ema(close, 20)``).
    * ``kc_width``: "atr" (``ta.atr(20)``, the plan), "ema_tr" (``ta.kc``'s ``ta.ema(ta.tr, 20)``), "sma_tr"
      (LazyBear's ``sma(tr, 20)``).
    * ``as_written``: True = ``basis + dev < kcb + rng and basis - dev > kcb - rng``; False = ``dev < rng``.
    * ``strict_squeeze``: True = ``<`` / ``>``; False = ``<=`` / ``>=``.
    * ``precedence``: "replace_first" (the old coil is not armed on the bar where a newer run reaches min_bars) or
      "breakout_first" (it is, and breaks out there if its close is beyond its box).
    * ``box``: "all" (the whole run), "last" (its last min_bars bars), "first" (its first min_bars bars), "close"
      (the run's closes).
    * ``arm_offset``: 1 (armed from the first bar after the run) or 2 (from the bar after that).
    * ``strict_breakout``: True = ``close > box_hi`` / ``close < box_lo``; False = ``>=`` / ``<=``.
    * ``dmi_tr_handle_na``: False = ``ta.tr`` (na on bar 0, the documented script); True = ``ta.tr(true)``.
    * ``dm_tie``: "zero" (as documented) or "plus" (``up >= down`` gives +DM).
    * ``sum_guard``: True = ``sum == 0 ? 1 : sum``; False = divide by the sum.
    """

    def __init__(self, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5, min_bars=6, armed_bars=12, di_len=14,
                 adx_len=14, biased=True, kc_basis="sma", kc_width="atr", as_written=True, strict_squeeze=True,
                 precedence="replace_first", box="all", arm_offset=1, strict_breakout=True, dmi_tr_handle_na=False,
                 dm_tie="zero", sum_guard=True):
        self.__dict__.update({k: v for k, v in locals().items() if k != "self"})

    # Pine built-ins on whole series (lists of floats), each value from bars 0..t only
    @staticmethod
    def sma_at(x, t, n):
        """pine_sma at bar t: ``sum := sum + x[i] / length``, i = 0 (this bar) .. length - 1; an na makes it na."""
        if t < n - 1:
            return NAN
        s = 0.0
        for i in range(n):
            s = s + x[t - i] / n
        return s

    def sma(self, x, n):
        return [self.sma_at(x, t, n) for t in range(len(x))]

    def stdev(self, x, n):
        avg = self.sma(x, n)
        out = []
        for t in range(len(x)):
            if avg[t] != avg[t]:
                out.append(NAN)
                continue
            s = 0.0
            for i in range(n):
                d = x[t - i] + (-avg[t])
                if abs(d) <= 1e-10:                  # pine_stdev's isZero
                    d = 0.0
                s = s + d * d
            out.append(math.sqrt(s / (n if self.biased else n - 1)))
        return out

    def rma(self, x, n):
        """pine_rma: ``na(sum[1]) ? ta.sma(src, length) : alpha * src + (1 - alpha) * nz(sum[1])``."""
        alpha = 1.0 / n
        out, prev = [], NAN
        for t in range(len(x)):
            v = self.sma_at(x, t, n) if prev != prev else alpha * x[t] + (1.0 - alpha) * prev
            out.append(v)
            prev = v
        return out

    @staticmethod
    def ema(x, n):
        alpha = 2.0 / (n + 1.0)
        out, prev = [], NAN
        for v in x:                                  # pine_ema: na(sum[1]) ? src : alpha * src + (1 - alpha) * sum[1]
            prev = v if prev != prev else alpha * v + (1.0 - alpha) * prev
            out.append(prev)
        return out

    @staticmethod
    def tr(h, l, c, handle_na):
        out = [(h[0] - l[0]) if handle_na else NAN] if len(h) else []
        for t in range(1, len(h)):
            out.append(max(max(h[t] - l[t], abs(h[t] - c[t - 1])), abs(l[t] - c[t - 1])))
        return out

    @staticmethod
    def fixnan(x):
        out, last = [], NAN
        for v in x:
            if v == v:
                last = v
            out.append(last)
        return out

    def squeeze(self, h, l, c):
        basis = self.sma(c, self.bb_len)
        sd = self.stdev(c, self.bb_len)
        kcb = self.sma(c, self.kc_len) if self.kc_basis == "sma" else self.ema(c, self.kc_len)
        if self.kc_width == "atr":
            width = self.rma(self.tr(h, l, c, True), self.kc_len)
        elif self.kc_width == "ema_tr":
            width = self.ema(self.tr(h, l, c, False), self.kc_len)
        else:
            width = self.sma(self.tr(h, l, c, False), self.kc_len)
        sq = []
        for t in range(len(c)):
            dev = self.bb_mult * sd[t]
            rng = self.kc_mult * width[t]
            if self.as_written:
                up, lo, kup, klo = basis[t] + dev, basis[t] - dev, kcb[t] + rng, kcb[t] - rng
                if self.strict_squeeze:
                    sq.append(up < kup and lo > klo)         # a comparison with na is false
                else:
                    sq.append(up <= kup and lo >= klo)
            else:
                sq.append(dev < rng if self.strict_squeeze else dev <= rng)
        return sq

    def machine(self, sq, h, l, c):
        n, m = len(sq), self.min_bars
        runs, t = [], 0
        while t < n:                                 # the maximal runs of squeeze bars
            if sq[t]:
                s = t
                while t < n and sq[t]:
                    t += 1
                runs.append((s, t - 1))
            else:
                t += 1
        run_len = [0] * n
        for s, e in runs:
            for t in range(s, e + 1):
                run_len[t] = t - s + 1
        coils = [(s, e) for s, e in runs if e - s + 1 >= m]
        armed, bo = [False] * n, [0] * n
        bhi, blo, ohi, olo = [NAN] * n, [NAN] * n, [NAN] * n, [NAN] * n
        for k, (s, e) in enumerate(coils):
            if self.box == "all":
                hi, lo = max(h[s:e + 1]), min(l[s:e + 1])
            elif self.box == "last":
                hi, lo = max(h[e - m + 1:e + 1]), min(l[e - m + 1:e + 1])
            elif self.box == "first":
                hi, lo = max(h[s:s + m]), min(l[s:s + m])
            else:
                hi, lo = max(c[s:e + 1]), min(c[s:e + 1])
            a = e + self.arm_offset                  # the first armed bar
            last = min(a + self.armed_bars - 1, n - 1)
            if k + 1 < len(coils):                   # the bar where the next coil's run reaches min_bars
                r = coils[k + 1][0] + m - 1
                last = min(last, r - 1 if self.precedence == "replace_first" else r)
            for t in range(a, last + 1):
                armed[t], bhi[t], blo[t] = True, hi, lo
                above = c[t] > hi if self.strict_breakout else c[t] >= hi
                below = c[t] < lo if self.strict_breakout else c[t] <= lo
                if above or below:
                    bo[t] = 1 if above else -1
                    ohi[t], olo[t] = hi, lo
                    break
        return run_len, armed, bhi, blo, bo, ohi, olo

    def dmi(self, h, l, c):
        n = len(h)
        up = [NAN] + [h[t] - h[t - 1] for t in range(1, n)]
        down = [NAN] + [-(l[t] - l[t - 1]) for t in range(1, n)]
        pdm, mdm = [], []
        for u, d in zip(up, down):
            if u != u:
                pdm.append(NAN)
                mdm.append(NAN)
                continue
            if self.dm_tie == "zero":
                pdm.append(u if (u > d and u > 0) else 0.0)
            else:
                pdm.append(u if (u >= d and u > 0) else 0.0)
            mdm.append(d if (d > u and d > 0) else 0.0)
        trur = self.rma(self.tr(h, l, c, self.dmi_tr_handle_na), self.di_len)
        rp, rm = self.rma(pdm, self.di_len), self.rma(mdm, self.di_len)
        plus = self.fixnan([_div(100.0 * a, b) for a, b in zip(rp, trur)])
        minus = self.fixnan([_div(100.0 * a, b) for a, b in zip(rm, trur)])
        dx = []
        for p, q in zip(plus, minus):
            s = p + q
            dx.append(_div(abs(p - q), 1.0 if (self.sum_guard and s == 0) else s))
        first = next((t for t, v in enumerate(dx) if v == v), n)
        adx = [NAN] * first + [100.0 * v for v in self.rma(dx[first:], self.adx_len)]
        return plus, minus, adx

    def run(self, o, h, l, c):
        h, l, c = (np.asarray(x, np.float64).tolist() for x in (h, l, c))
        sq = self.squeeze(h, l, c)
        run_len, armed, bhi, blo, bo, ohi, olo = self.machine(sq, h, l, c)
        adx = self.dmi(h, l, c)[2]
        return {"squeeze_on": np.array(sq, bool), "run_len": np.array(run_len, np.int64),
                "armed": np.array(armed, bool), "box_hi": np.array(bhi), "box_lo": np.array(blo),
                "breakout": np.array(bo, np.int8), "bo_box_hi": np.array(ohi), "bo_box_lo": np.array(olo),
                "adx": np.array(adx)}


# ───────────────────────────── hand-case helpers ─────────────────────────────

R = (99.0, 101.0, 100.0)          # a squeeze bar of the first coil: low, high, close
I_ = (99.5, 100.5, 100.0)         # a squeeze bar well inside that box
F = "F"                           # a flat bar at the previous close: no true range, no squeeze (with K1)


def hand_bars(spec, start=100.0):
    """o, h, l, c from a list of bars: "F" = a flat bar at the previous close; (low, high, close) = a bar with that
    low, high and close. The open is the previous close (not read). Bar 0 of every case is "F" at ``start``."""
    o, h, l, c = [], [], [], []
    prev = start
    for item in spec:
        lo, hi, cl = (prev, prev, prev) if item == F else item
        o.append(prev)
        h.append(hi)
        l.append(lo)
        c.append(cl)
        prev = cl
    return tuple(np.array(x, np.float64) for x in (o, h, l, c))


def expect(out, squeeze=None, run_len=None, armed=None, boxes=None, breakouts=None):
    """Compare a coil output with a hand case. ``armed``: the armed bars; ``boxes``: {bar: (box_hi, box_lo)} for
    every armed bar; ``breakouts``: {bar: +1 / -1} (every other bar 0, and ``bo_box_*`` NaN there)."""
    n = len(out["breakout"])
    if squeeze is not None:
        assert out["squeeze_on"].tolist() == [bool(x) for x in squeeze]
    if run_len is not None:
        assert out["run_len"].tolist() == list(run_len)
    if armed is not None:
        want = np.zeros(n, bool)
        want[list(armed)] = True
        assert out["armed"].tolist() == want.tolist()
    if boxes is not None:
        for t in range(n):
            if t in boxes:
                assert (out["box_hi"][t], out["box_lo"][t]) == boxes[t], t
            else:
                assert np.isnan(out["box_hi"][t]) and np.isnan(out["box_lo"][t]), t
    if breakouts is not None:
        want = np.zeros(n, np.int8)
        for t, s in breakouts.items():
            want[t] = s
        assert out["breakout"].tolist() == want.tolist()
        for t in range(n):
            if t in breakouts:
                assert (out["bo_box_hi"][t], out["bo_box_lo"][t]) == (out["box_hi"][t], out["box_lo"][t]), t
            else:
                assert np.isnan(out["bo_box_hi"][t]) and np.isnan(out["bo_box_lo"][t]), t


def box_of(bars, hi, lo):
    return {t: (hi, lo) for t in bars}


def flat_then_jump(jump_close, jump_low, n=60, after=None):
    """Bars 0..30: low 99, high 101, close 100 (true range 2); bar 31: the given close as its high, the given low;
    bars 32..: the close of bar 31 +- 1 (true range 2), or ``after`` = (low, high, close)."""
    lo = [99.0] * 31 + [jump_low]
    hi = [101.0] * 31 + [jump_close]
    cl = [100.0] * 31 + [jump_close]
    a = after or (jump_close - 1.0, jump_close + 1.0, jump_close)
    lo += [a[0]] * (n - 32)
    hi += [a[1]] * (n - 32)
    cl += [a[2]] * (n - 32)
    c = np.array(cl)
    return np.r_[c[0], c[:-1]], np.array(hi), np.array(lo), c


# ───────────────────────────── 1. the traps, by hand ─────────────────────────────

def test_trap01_a_run_of_exactly_5_is_no_coil_a_run_of_6_is():
    """"A coil is at least 6 consecutive squeeze_on bars": 5 squeeze bars arm nothing (a close far above their box
    is no breakout); 6 arm a coil on the next bar, whose box breaks on the bar after."""
    five = hand_bars([F, R, R, R, R, R, F, (100.0, 103.0, 102.5)])
    out = C.coil(*five, **K1)
    expect(out, squeeze=[0, 1, 1, 1, 1, 1, 0, 1], run_len=[0, 1, 2, 3, 4, 5, 0, 1], armed=[], boxes={}, breakouts={})
    six = hand_bars([F, R, R, R, R, R, R, F, (100.0, 103.0, 102.5)])
    out = C.coil(*six, **K1)
    expect(out, squeeze=[0, 1, 1, 1, 1, 1, 1, 0, 1], run_len=[0, 1, 2, 3, 4, 5, 6, 0, 1], armed=[7, 8],
           boxes=box_of([7, 8], 101.0, 99.0), breakouts={8: 1})
    assert (out["bo_box_hi"][8], out["bo_box_lo"][8]) == (101.0, 99.0)
    # the wrong reading (a coil from 5 bars) answers differently on the five-bar case
    wrong = Transcription(min_bars=5, **K1).run(*five)
    assert wrong["breakout"].tolist() == [0, 0, 0, 0, 0, 0, 0, 1]
    assert outputs_equal(Transcription(**K1).run(*six), out)


def test_trap02_a_breakout_on_the_12th_armed_bar_counts_on_the_13th_it_does_not():
    """Armed for 12 bars, the first bar after the run included: bars 7..18 for a run ending at bar 6. Between them
    single squeeze bars (runs of 1) and flat bars, all closing inside the box."""
    gap = [I_, F, I_, F, I_, F, I_, F, I_, F]                          # bars 8..17: armed bars 2..11
    hit = (100.0, 102.0, 101.5)                                        # closes above the box high 101
    on12 = hand_bars([F] + [R] * 6 + [F] + gap + [hit])                # bar 18 = the 12th armed bar
    out = C.coil(*on12, **K1)
    expect(out, armed=range(7, 19), boxes=box_of(range(7, 19), 101.0, 99.0), breakouts={18: 1})
    on13 = hand_bars([F] + [R] * 6 + [F] + gap + [I_, hit])            # bar 19 = the 13th bar
    out = C.coil(*on13, **K1)
    expect(out, armed=range(7, 19), boxes=box_of(range(7, 19), 101.0, 99.0), breakouts={})
    assert not out["armed"][19] and out["squeeze_on"][19]
    # wrong readings: a 13-bar window (or "12 bars after" counted from the bar after the arming bar) fires on bar 19;
    # an 11-bar window misses bar 18
    assert Transcription(armed_bars=13, **K1).run(*on13)["breakout"][19] == 1
    assert Transcription(arm_offset=2, **K1).run(*on13)["breakout"][19] == 1
    assert Transcription(armed_bars=11, **K1).run(*on12)["breakout"][18] == 0


def test_trap03_a_newer_run_reaching_6_replaces_the_armed_coil_from_that_bar():
    """Coil A (bars 1-6, box 99-101) is armed from bar 7. A newer run (bars 8-13) reaches 6 bars at bar 13: from that
    bar on, bar 13 included, A is no longer armed; the newer coil B arms on bar 14 with its own box (100.6, 99.4) and
    breaks out at bar 15, whose close 100.8 is inside A's box. Second case, the precedence: the newer run's 6th bar
    (bar 13) closes at 101.5, above A's box: still no breakout, A is replaced on that bar."""
    N = (99.4, 100.6, 100.0)
    case = hand_bars([F] + [R] * 6 + [F] + [N] * 6 + [F, (100.5, 100.9, 100.8)])
    out = C.coil(*case, **K1)
    expect(out, squeeze=[0] + [1] * 6 + [0] + [1] * 6 + [0, 1],
           run_len=[0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3, 4, 5, 6, 0, 1],
           armed=[7, 8, 9, 10, 11, 12, 14, 15],
           boxes={**box_of(range(7, 13), 101.0, 99.0), **box_of([14, 15], 100.6, 99.4)}, breakouts={15: 1})
    assert (out["bo_box_hi"][15], out["bo_box_lo"][15]) == (100.6, 99.4)
    # the precedence on the replacing bar: its close (101.5) is above A's box, but A is replaced there
    prec = hand_bars([F] + [R] * 6 + [F] + [N] * 5 + [(100.0, 101.6, 101.5), F, (101.5, 101.7, 101.65)])
    out = C.coil(*prec, **K1)
    expect(out, armed=[7, 8, 9, 10, 11, 12, 14, 15],
           boxes={**box_of(range(7, 13), 101.0, 99.0), **box_of([14, 15], 101.6, 99.4)}, breakouts={15: 1})
    # wrong readings: the old coil tested before the replacement breaks out at bar 13; without replacement (only a
    # newer ARMED coil replaces) the old one also breaks out there
    wrong = Transcription(precedence="breakout_first", **K1).run(*prec)
    assert wrong["breakout"][13] == 1 and wrong["armed"][13]
    assert outputs_equal(Transcription(**K1).run(*prec), out)


def test_trap04_a_close_exactly_at_the_box_edge_is_no_breakout():
    """Strict: a close == box_hi (bar 8) or == box_lo (bar 10) is no breakout; just beyond is (bar 12)."""
    up = hand_bars([F] + [R] * 6 + [F, (100.0, 101.5, 101.0), F, (99.0, 101.0, 99.0), F,
                                    (99.0, 101.5, 101.000001)])
    out = C.coil(*up, **K1)
    expect(out, armed=range(7, 13), boxes=box_of(range(7, 13), 101.0, 99.0), breakouts={12: 1})
    dn = hand_bars([F] + [R] * 6 + [F, (100.0, 101.5, 101.0), F, (99.0, 101.0, 99.0), F,
                                    (98.5, 100.0, 98.999999)])
    expect(C.coil(*dn, **K1), armed=range(7, 13), breakouts={12: -1})
    wrong = Transcription(strict_breakout=False, **K1).run(*up)
    assert wrong["breakout"][8] == 1 and wrong["breakout"][12] == 0


def test_trap05_a_newer_run_of_5_replaces_nothing_and_the_count_does_not_pause():
    """A newer run of 5 squeeze bars (bars 8-12) inside the armed window is no coil: the old coil stays armed through
    it, its 12 bars still end at bar 18 (the count does not pause on squeeze bars), and it can break out on a squeeze
    bar of that newer run (bar 10)."""
    five_inside = hand_bars([F] + [R] * 6 + [F] + [I_] * 5 + [F, I_, F, I_, F, (100.0, 102.0, 101.5)])
    out = C.coil(*five_inside, **K1)
    expect(out, squeeze=[0] + [1] * 6 + [0] + [1] * 5 + [0, 1, 0, 1, 0, 1],
           armed=range(7, 19), boxes=box_of(range(7, 19), 101.0, 99.0), breakouts={18: 1})
    on_squeeze = hand_bars([F] + [R] * 6 + [F, I_, I_, (100.0, 102.0, 101.5)])
    out = C.coil(*on_squeeze, **K1)
    expect(out, armed=[7, 8, 9, 10], breakouts={10: 1})
    assert out["squeeze_on"][10] and out["run_len"][10] == 3
    # the wrong reading (a run of 5 is a coil and replaces) disarms the first coil at bar 12; the breakout at bar 18
    # is then the newer coil's, with the newer box
    w = Transcription(min_bars=5, **K1).run(*five_inside)
    assert not w["armed"][12] and (w["bo_box_hi"][18], w["bo_box_lo"][18]) == (100.5, 99.5)


def test_trap06_the_box_is_the_highest_high_and_lowest_low_of_the_whole_run():
    """Run of 9 bars (1-9): its highest high (104) is on its first bar and its lowest low (97.5) on its last; the closes
    stay at 100. Box = (104, 97.5), not the last 6 bars' (101, 97.5), not the first 6 bars' (104, 98), not the closes'.
    Bar 11 closes at 97.8 (below the first-6 low, above the box low), bar 13 at 103 (above the last-6 high, below the
    box high): no breakout; bar 15 closes at 104.2 > 104: the breakout."""
    case = hand_bars([F, (98.0, 104.0, 100.0)] + [R] * 7 + [(97.5, 101.0, 100.0), F, (97.6, 100.0, 97.8), F,
                                                          (100.0, 103.5, 103.0), F, (103.0, 104.5, 104.2)])
    out = C.coil(*case, **K1)
    expect(out, armed=range(10, 16), boxes=box_of(range(10, 16), 104.0, 97.5), breakouts={15: 1})
    assert Transcription(box="last", **K1).run(*case)["breakout"][13] == 1
    assert Transcription(box="first", **K1).run(*case)["breakout"][11] == -1
    assert Transcription(box="close", **K1).run(*case)["breakout"][11] == -1


def test_trap07_armed_from_the_first_bar_after_the_run_which_is_where_the_squeeze_fires():
    """The plan's settings. Bars 0-30 close at 100 with a true range of 2: no deviation, ATR(20) about 2, squeeze from
    bar 19 (the warm-up ends) to bar 30. Bar 31 jumps to 110 (low 108): the deviation of the window becomes
    10 * sqrt(19) / 20 = 2.1794 (2 sd = 4.359) while 1.5 ATR = 1.5 * (0.95 * 2 + 0.05 * 10) = 3.6: the squeeze is off,
    the run of 12 (bars 19-30) is a coil, armed on bar 31 itself, whose close 110 > 101 breaks out. The arming bar's
    own high (110) is not in the box. The squeeze stays off while the jump is in the window (bars 31-49) and returns
    at bar 50."""
    b = flat_then_jump(110.0, 108.0)
    out = C.coil(*b)
    sq = [0] * 19 + [1] * 12 + [0] * 19 + [1] * 10
    expect(out, squeeze=sq, run_len=[0] * 19 + list(range(1, 13)) + [0] * 19 + list(range(1, 11)), armed=[31],
           boxes={31: (101.0, 99.0)}, breakouts={31: 1})
    up, lo, kup, klo = C._bands(b[1], b[2], b[3], 20, 2.0, 20, 1.5)
    assert abs((up[31] - lo[31]) / 2 - 2 * 10 * math.sqrt(19) / 20) < 1e-12
    assert abs((kup[31] - klo[31]) / 2 - 3.6) < 1e-12
    # wrong reading: arming from the bar after the first non-squeeze bar misses the fire bar
    assert Transcription(arm_offset=2).run(*b)["breakout"][31] == 0


def test_trap08_once_per_coil_and_the_breakout_bar_is_its_last_armed_bar():
    """After the +1 at bar 8 the coil is done: a close below its box (bar 10) and above it again (bar 12) inside what
    would have been its 12 bars are nothing; ``armed`` and the box stop after the breakout bar."""
    case = hand_bars([F] + [R] * 6 + [F, (100.0, 102.0, 101.5), F, (98.0, 101.5, 98.5), F, (98.5, 102.0, 101.8)])
    out = C.coil(*case, **K1)
    expect(out, armed=[7, 8], boxes=box_of([7, 8], 101.0, 99.0), breakouts={8: 1})


def test_trap09_the_close_decides_not_the_wick():
    """A high far above the box (bar 8) or a low far below it (bar 10) with the close inside is no breakout."""
    case = hand_bars([F] + [R] * 6 + [F, (99.5, 105.0, 100.5), F, (95.0, 100.5, 99.5), F, (100.0, 101.4, 101.2)])
    expect(C.coil(*case, **K1), armed=range(7, 13), breakouts={12: 1})


def test_trap10_the_squeeze_is_strict_a_dead_market_is_no_squeeze():
    """Constant bars (no range, one close): both widths are 0, the bands coincide, and ``bbUpper < kcUpper`` is
    false: no squeeze, no coil. The same closes with a range of 2 are a squeeze from bar 19."""
    c = np.full(40, 100.0)
    dead = C.coil(c, c, c, c)
    assert not dead["squeeze_on"].any() and not dead["run_len"].any() and not dead["armed"].any()
    assert Transcription(strict_squeeze=False).run(c, c, c, c)["squeeze_on"][19:].all()
    live = C.coil(c, c + 1.0, c - 1.0, c)
    assert live["squeeze_on"].tolist() == [False] * 19 + [True] * 21


def test_trap11_the_deviation_is_the_population_one():
    """Closes 100, 101, 102, ... with a range of 7.8 around each (true range 7.8, ATR(20) = 7.8). Population
    deviation of 20 consecutive integers: sqrt(399 / 12) = 5.76628, 2 sd = 11.5326 < 1.5 ATR = 11.7: a squeeze from
    bar 19 on. The sample deviation, sqrt(35) = 5.91608, 2 sd = 11.8322 > 11.7, would give none."""
    c = 100.0 + np.arange(60.0)
    b = (c - 1.0, c + 3.9, c - 3.9, c)
    out = C.coil(*b)
    assert out["squeeze_on"].tolist() == [False] * 19 + [True] * 41
    up, lo, kup, klo = C._bands(b[1], b[2], b[3], 20, 2.0, 20, 1.5)
    assert np.allclose((up[19:] - lo[19:]) / 2, 2 * math.sqrt(399 / 12), rtol=0, atol=1e-10)
    assert np.allclose((kup[19:] - klo[19:]) / 2, 11.7, rtol=0, atol=1e-10)
    assert not Transcription(biased=False).run(*b)["squeeze_on"].any()


def test_trap12_the_keltner_width_is_wilder_atr20_not_an_ema_or_sma_of_the_true_range():
    """Bars 0-30: close 100, range 2. Bar 31: a range spike (low 90, high 110, close 100). Bars 32-40 as 0-30. Bar 41:
    close 111 (low 109). At bar 41, 2 sd = 2 * 11 * sqrt(19) / 20 = 4.79478 and
    * Wilder ATR(20) = 0.95 * (2 + 0.9 * 0.95**9) + 0.05 * 11 = 2.98886, 1.5 ATR = 4.48329: the squeeze is OFF; the run
      19-40 (with the spike: box 90-110) is a coil armed on bar 41, whose close 111 breaks out;
    * ta.kc's EMA(20) of the true range = 3.48729 (1.5 x = 5.23093) and an SMA(20) of it = 3.35 (5.025) keep the
      squeeze ON: the run goes on, nothing is armed and bar 41 is no breakout."""
    b = flat_then_jump(100.0, 90.0, n=42, after=(99.0, 101.0, 100.0))
    h, l, c = b[1].copy(), b[2].copy(), b[3].copy()
    h[31], l[31], c[31] = 110.0, 90.0, 100.0
    h[41], l[41], c[41] = 111.0, 109.0, 111.0
    o = np.r_[c[0], c[:-1]]
    out = C.coil(o, h, l, c)
    assert out["squeeze_on"][19:41].all() and not out["squeeze_on"][41]
    expect(out, armed=[41], boxes={41: (110.0, 90.0)}, breakouts={41: 1})
    _, _, kup, klo = C._bands(h, l, c, 20, 2.0, 20, 1.5)
    assert abs((kup[41] - klo[41]) / 2 - 1.5 * (0.95 * (2 + 0.9 * 0.95 ** 9) + 0.05 * 11)) < 1e-12
    for width in ("ema_tr", "sma_tr"):
        w = Transcription(kc_width=width).run(o, h, l, c)
        assert w["squeeze_on"][41] and w["breakout"][41] == 0, width


def test_trap13_the_keltner_basis_is_the_sma_not_an_ema():
    """Bars 0-30 close at 100 (range 2); bar 31 closes at 107.5 (low 105.5). At bar 31: SMA(20) = 100.375,
    2 sd = 2 * 7.5 * sqrt(19) / 20 = 3.26918, 1.5 ATR = 1.5 * (1.9 + 0.375) = 3.4125: the squeeze holds (margin
    0.143). Around ta.kc's EMA(20) = 100 + 7.5 * 2 / 21 = 100.71429 the lower band 97.30179 is above the Bollinger
    lower band 97.10582: no squeeze. With the plan's SMA the run goes on to bar 31 (its high 107.5 enters the box);
    bar 32 ends it, the coil is armed on bars 32-43 with box (107.5, 99), and its closes at exactly 107.5 never break
    out (strict)."""
    b = flat_then_jump(107.5, 105.5, n=46)
    out = C.coil(*b)
    assert out["squeeze_on"][19:32].all() and not out["squeeze_on"][32:46].any()
    expect(out, armed=range(32, 44), boxes=box_of(range(32, 44), 107.5, 99.0), breakouts={})
    w = Transcription(kc_basis="ema").run(*b)
    assert not w["squeeze_on"][31] and w["breakout"][31] == 1


def test_trap14_no_squeeze_during_the_warm_up():
    """The SMA, the deviation and the ATR exist from bar ``length - 1``: a quiet market has its first squeeze bar at
    19 with the plan's 20 / 20, at 24 with a Keltner length of 25; the ADX exists from bar 27."""
    c = np.full(40, 100.0)
    out = C.coil(c, c + 1.0, c - 1.0, c)
    assert np.flatnonzero(out["squeeze_on"])[0] == 19
    assert np.flatnonzero(C.coil(c, c + 1.0, c - 1.0, c, kc_len=25)["squeeze_on"])[0] == 24
    assert np.isnan(out["adx"][:27]).all()


def test_trap15_the_squeeze_is_evaluated_as_written_not_simplified():
    """``basis + dev < basis + rng``, not ``dev < rng``: at a price of 1e16 (spacing 2) with ``bb_len = kc_len = 1``
    (dev = 0) and ``kc_mult = 0.25`` the Keltner half-width is 0.25 * 2 = 0.5, which the sum rounds away: the bands
    coincide and there is no squeeze, although 0 < 0.5. With ``kc_mult = 1`` (half-width 2) the squeeze is on."""
    c = np.full(10, 1e16)
    b = (c, c + 2.0, c, c)
    assert not C.coil(*b, kc_mult=0.25, **K1)["squeeze_on"].any()
    assert C.coil(*b, kc_mult=1.0, **K1)["squeeze_on"].all()
    assert Transcription(kc_mult=0.25, as_written=False, **K1).run(*b)["squeeze_on"].all()


def test_trap16_dmi_true_range_without_handle_na_and_the_adx_by_hand():
    """``ta.dmi(2, 2)`` by hand on six bars. ``ta.tr`` is na on bar 0, so trur starts at bar 2 with (2.5 + 2) / 2:
    trur = [., ., 2.25, 2.375, 2.6875, 2.59375]; RMA(+DM) = [., ., 0.5, 0.5, 0.25, 0.125]; RMA(-DM) = [., ., 0, 0, 1,
    0.75]; +DI = 100 RMA / trur; DX = |+DI - -DI| / (+DI + -DI) = [., ., 1, 1, 0.6, 0.714286]; ADX = 100 RMA(DX, 2) =
    [., ., ., 100, 80, 75.714286]. With ``ta.tr(true)`` (bar 0's range 10 in the seed) +DI and -DI change, but the ADX
    does not: both DIs divide by the same trur, which cancels in DX."""
    h = np.array([10.0, 6.0, 7.0, 7.5, 6.0, 5.0])
    l = np.array([0.0, 4.0, 4.5, 5.0, 3.0, 2.5])
    c = np.array([5.0, 5.0, 6.5, 5.5, 3.5, 4.0])
    plus, minus, adx = C._dmi(h, l, c, 2, 2)
    assert np.isnan(plus[:2]).all() and np.allclose(plus[2:], [50 / 2.25, 50 / 2.375, 25 / 2.6875, 12.5 / 2.59375],
                                                    rtol=1e-14, atol=0)
    assert np.isnan(minus[:2]).all() and np.allclose(minus[2:], [0, 0, 100 / 2.6875, 75 / 2.59375], rtol=1e-14, atol=0)
    assert np.isnan(adx[:3]).all()
    assert np.allclose(adx[3:], [100.0, 80.0, 100 * (0.5 * 5 / 7 + 0.4)], rtol=1e-13, atol=0)
    assert same(C.adx(h, l, c, 2, 2), adx)
    wrong = Transcription(di_len=2, adx_len=2, dmi_tr_handle_na=True)
    wp, _, wa = wrong.dmi(h.tolist(), l.tolist(), c.tolist())
    assert abs(wp[2] - 50 / 4.25) < 1e-12 and abs(wp[2] - plus[2]) > 1.0
    assert np.allclose(wa[3:], adx[3:], rtol=1e-12, atol=0)


def test_trap17_dmi_a_tie_and_an_inside_bar_give_no_directional_movement_and_sum_zero_divides_by_1():
    """Bar 1 is a symmetric outside bar (up = down = 1: a tie, both DMs 0), bar 2 an inside bar (both 0); bar 3 +DM
    1.5, bar 4 -DM 1, bar 5 -DM 0.5. ``ta.dmi(2, 2)``: at bar 2 +DI = -DI = 0, so ``sum == 0`` divides by 1 and DX = 0
    (not na); DX = [., ., 0, 1, 1/7, 5/11]; ADX = [., ., ., 50, 32.142857, 38.798701]. Giving the tie to +DM, or
    dividing 0 by 0, answers differently."""
    h = np.array([10.0, 11.0, 10.5, 12.0, 11.5, 10.0])
    l = np.array([8.0, 7.0, 7.5, 9.5, 8.5, 8.0])
    c = np.array([9.0, 9.0, 10.0, 11.5, 9.0, 9.5])
    plus, minus, adx = C._dmi(h, l, c, 2, 2)
    assert np.allclose(plus[2:], [0.0, 25.0, 12.5, 7.5], rtol=1e-14, atol=0)
    assert np.allclose(minus[2:], [0.0, 0.0, 50 / 3, 20.0], rtol=1e-14, atol=0)
    want = [50.0, 100 * (0.5 / 7 + 0.25), 100 * (0.5 * 5 / 11 + 0.5 * (0.5 / 7 + 0.25))]
    assert np.isnan(adx[:3]).all() and np.allclose(adx[3:], want, rtol=1e-13, atol=0)
    tie = Transcription(di_len=2, adx_len=2, dm_tie="plus").dmi(h.tolist(), l.tolist(), c.tolist())[2]
    assert abs(tie[3] - adx[3]) > 1.0
    noguard = Transcription(di_len=2, adx_len=2, sum_guard=False).dmi(h.tolist(), l.tolist(), c.tolist())[2]
    assert np.isnan(noguard[3]) and not np.isnan(adx[3])


def test_trap18_dmi_fixnan_on_a_flat_start():
    """Bars 0-14 flat (no true range): at bar 14 (the first trur) both RMAs are 0 and +DI = 0 / 0 is na, which fixnan
    cannot fill (no earlier value). Bar 15 (a symmetric outside bar: a tie) gives trur > 0 and +DI = -DI = 0, DX = 0
    through the ``sum == 0`` guard; DX exists from bar 15 and the ADX(14) from bar 15 + 13 = 28, a bar later than
    usual."""
    n = 60
    c = np.r_[np.full(16, 100.0), 100.0 + 2.0 * np.sin(np.arange(n - 16) / 3.0)]
    h, l = c.copy(), c.copy()
    h[15], l[15] = 102.0, 98.0
    h[16:], l[16:] = c[16:] + 1.0, c[16:] - 1.0
    plus, minus, adx = C._dmi(h, l, c, 14, 14)
    assert np.isnan(plus[:15]).all() and plus[15] == 0.0 and minus[15] == 0.0
    assert np.isnan(adx[:28]).all() and np.isfinite(adx[28:]).all()
    assert same(C.coil(c, h, l, c)["adx"], adx)


def test_trap19_dmi_first_value_at_bar_27_and_the_independent_wilder_adx():
    """On ordinary bars +DI / -DI exist from bar 14 and the ADX from bar 14 + 14 - 1 = 27; the ADX equals
    ``ladder_ind.adx`` (another study's Wilder ADX: RMA as (prev * 13 + x) / 14, DX scaled before its RMA) to 1e-12."""
    o, h, l, c = random_bars(800, 11)
    plus, _, adx = C._dmi(h, l, c, 14, 14)
    assert np.isnan(plus[:14]).all() and np.isfinite(plus[14:]).all()
    assert np.isnan(adx[:27]).all() and np.isfinite(adx[27:]).all()
    other = LI.adx(h, l, c, 14)[0]
    assert np.array_equal(np.isnan(other), np.isnan(adx)) and np.nanmax(np.abs(other - adx)) < 1e-12


def test_reading_the_keltner_basis_uses_kc_len():
    """Off the plan's settings only: the Keltner basis is ``ta.sma(close, kc_len)``. bb_len 1, kc_len 2, kc_mult 0.5
    on two flat bars at 100 and 104: kc basis 102, ATR(2) = (0 + 4) / 2 = 2, Keltner 101-103, the band (104, 104) is
    outside: no squeeze. A basis of SMA(bb_len) = 104 would give 103-105, a squeeze."""
    c = np.array([100.0, 104.0])
    assert C.coil(c, c, c, c, bb_len=1, kc_len=2, kc_mult=0.5)["squeeze_on"].tolist() == [False, False]
    _, _, kup, klo = C._bands(c, c, c, 1, 2.0, 2, 0.5)
    assert (kup[1], klo[1]) == (103.0, 101.0)


def test_output_keys_dtypes_and_inputs():
    o, h, l, c = random_bars(300, 3)
    keep = [x.copy() for x in (o, h, l, c)]
    out = C.coil(o, h, l, c)
    assert tuple(out) == C.KEYS
    for k, v in out.items():
        assert v.shape == (300,) and v.dtype == DTYPES[k], k
    for x, y in zip((o, h, l, c), keep):
        assert np.array_equal(x, y)                                       # inputs untouched
    assert outputs_equal(C.coil(o * 0.0 + 7.0, h, l, c), out)             # the open is not read
    assert same(C.adx(h, l, c), out["adx"])
    assert set(np.unique(out["breakout"])) <= {-1, 0, 1}
    empty = C.coil([], [], [], [])
    assert all(len(v) == 0 for v in empty.values())
    with pytest.raises(ValueError):
        C.coil(o, h, l, c[:-1])
    bad = c.copy()
    bad[50] = np.nan
    with pytest.raises(ValueError):
        C.coil(o, h, l, bad)
    for kw in (dict(bb_len=0), dict(kc_len=2.5), dict(min_bars=0), dict(armed_bars=True), dict(bb_mult=-1.0),
               dict(kc_mult=math.inf)):
        with pytest.raises(ValueError):
            C.coil(o, h, l, c, **kw)
    with pytest.raises(ValueError):
        C.adx(h, l, c, di_len=0)


# ───────────────────────────── 2. the port against the transcription ─────────────────────────────

def random_bars(n, seed, decimals=None):
    """Quiet and active regimes of random lengths (the closes barely move in a quiet one, with a slow drift, while
    the bars keep their ranges, which makes squeezes), random ranges; ``decimals`` rounds the prices (ties: closes at
    a box edge, equal highs, directional-movement ties)."""
    rng = np.random.default_rng(seed)
    vol, drift = np.empty(n), np.empty(n)
    i, quiet = 0, True
    while i < n:
        k = int(rng.integers(8, 60))
        vol[i:i + k] = 0.12 if quiet else 1.0
        drift[i:i + k] = rng.choice((-1.0, 1.0)) * rng.uniform(0.0, 0.06) if quiet else 0.0
        i, quiet = i + k, not quiet
    c = 1000.0 + np.cumsum(rng.normal(0.0, 1.0, n) * vol * rng.uniform(0.5, 1.5, n) + drift)
    o = np.r_[c[0], c[:-1]] + rng.normal(0.0, 0.05, n)
    span = rng.exponential(0.5, n) + 0.05
    h = np.maximum(o, c) + span * rng.uniform(0.0, 1.0, n)
    l = np.minimum(o, c) - span * rng.uniform(0.0, 1.0, n)
    if decimals is not None:
        o, h, l, c = (np.round(x, decimals) for x in (o, h, l, c))
        h, l = np.maximum(h, np.maximum(o, c)), np.minimum(l, np.minimum(o, c))
    return o, h, l, c


def random_k1_bars(n, seed):
    """A random hand case for ``bb_len = kc_len = 1``: runs of 1-12 squeeze bars (random lows, highs and closes to
    0.1 around a wandering level) separated by 1-2 flat bars. Every event of the coil machine is frequent here:
    coils of every length, replacements, breakouts on any armed bar (the 12th included) and on squeeze bars, and
    closes exactly at a box edge."""
    rng = np.random.default_rng(seed)
    spec, level = [F], 100.0
    while len(spec) < n:
        for _ in range(int(rng.choice([1, 2, 3, 4, 5, 6, 7, 9, 12], p=[.2, .12, .1, .08, .1, .14, .12, .08, .06]))):
            mid = level + rng.normal(0.0, 0.25)
            lo = round(mid - rng.uniform(0.1, 1.0), 1)
            hi = round(mid + rng.uniform(0.1, 1.0), 1)
            spec.append((lo, hi, round(rng.uniform(lo, hi), 1)))
        spec.extend([F] * int(rng.integers(1, 3)))
        level += rng.normal(0.0, 0.35)
    return hand_bars(spec[:n])


def coil_events(out):
    """(arming bars, breakouts at the 12th armed bar, replaced coils) of a coil output."""
    a, bo = out["armed"], out["breakout"]
    starts = np.flatnonzero(a & ~np.r_[False, a[:-1]])
    ends = np.flatnonzero(a & ~np.r_[a[1:], False])
    length = ends - starts + 1
    return starts, int(((bo[ends] != 0) & (length == 12)).sum()), int(((bo[ends] == 0) & (length < 12)).sum())


@pytest.mark.parametrize("seed,decimals", [(1, None), (2, None), (3, 1), (4, 0), (5, 2), (6, None)])
def test_port_equals_the_transcription_bit_for_bit_on_random_bars(seed, decimals):
    """Every output, bit for bit, on random bars (rounded prices give equal closes and closes at the box edges)."""
    bars = random_bars(4000, seed, decimals=decimals)
    port, ref = C.coil(*bars), Transcription().run(*bars)
    assert outputs_equal(port, ref)
    starts, _, _ = coil_events(port)
    assert len(starts) > 30 and (port["breakout"] != 0).sum() > 30


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_port_equals_the_transcription_on_random_coil_sequences(seed):
    """The coil machine, bit for bit, on random hand-like sequences (``random_k1_bars``)."""
    bars = random_k1_bars(3000, seed)
    port = C.coil(*bars, **K1)
    assert outputs_equal(port, Transcription(**K1).run(*bars))
    assert len(coil_events(port)[0]) > 100


def tally(out, c):
    """(coils, breakouts at the 12th armed bar, replaced coils, breakouts on squeeze bars, closes at a box edge)."""
    starts, k12, rep = coil_events(out)
    return np.array([len(starts), k12, rep, int(((out["breakout"] != 0) & out["squeeze_on"]).sum()),
                     int((out["armed"] & ((c == out["box_hi"]) | (c == out["box_lo"]))).sum())])


def test_the_random_bars_reach_every_event():
    """The random bars of the comparisons above contain every event of the machine, so the comparisons cover them:
    breakouts at the 12th armed bar, replaced coils, breakouts on squeeze bars of a newer run, closes exactly at a box
    edge (strictness)."""
    plain = sum(tally(C.coil(*b), b[3]) for b in (random_bars(4000, s, decimals=d) for s, d in
                                                  ((1, None), (2, None), (3, 1), (4, 0), (5, 2), (6, None))))
    k1 = sum(tally(C.coil(*b, **K1), b[3]) for b in (random_k1_bars(3000, s) for s in range(1, 7)))
    assert plain[0] >= 300 and plain[1] >= 1 and plain[2] >= 10 and plain[3] >= 5 and plain[4] >= 100, plain
    assert k1[0] >= 1000 and k1[1] >= 15 and k1[2] >= 300 and k1[3] >= 300 and k1[4] >= 150, k1


@pytest.mark.parametrize("kw", [dict(bb_len=10, bb_mult=1.5, kc_len=14, kc_mult=2.0, min_bars=3, armed_bars=5),
                                dict(bb_len=30, kc_len=10, min_bars=10, armed_bars=20), K1])
def test_port_equals_the_transcription_with_other_inputs(kw):
    bars = random_bars(3000, 8)
    port = C.coil(*bars, **kw)
    assert outputs_equal(port, Transcription(**kw).run(*bars))


def test_port_equals_the_transcription_on_the_hand_cases():
    N = (99.4, 100.6, 100.0)
    for spec in ([F] + [R] * 6 + [F] + [I_, F] * 5 + [(100.0, 102.0, 101.5)],
                 [F] + [R] * 6 + [F] + [N] * 5 + [(100.0, 101.6, 101.5), F, (101.5, 101.7, 101.65)]):
        bars = hand_bars(spec)
        assert outputs_equal(C.coil(*bars, **K1), Transcription(**K1).run(*bars))
    for b in (flat_then_jump(110.0, 108.0), flat_then_jump(107.5, 105.5, n=46)):
        assert outputs_equal(C.coil(*b), Transcription().run(*b))


def test_adx_with_other_lengths_equals_the_transcription_and_ladder_ind():
    o, h, l, c = random_bars(1500, 9, decimals=1)
    for di, ax in ((14, 14), (7, 20), (20, 5), (1, 1)):
        a = C.adx(h, l, c, di, ax)
        ref = Transcription(di_len=di, adx_len=ax).dmi(h.tolist(), l.tolist(), c.tolist())[2]
        assert same(a, ref), (di, ax)
        assert np.isnan(a[:di + ax - 1]).all() and np.isfinite(a[di + ax - 1:]).all()
        assert np.all((a[di + ax - 1:] >= 0) & (a[di + ax - 1:] <= 100))
    other = LI.adx(h, l, c, 14)[0]
    assert np.nanmax(np.abs(other - C.adx(h, l, c))) < 1e-12


# ───────────────────────────── 3. truncation invariance ─────────────────────────────

@pytest.mark.parametrize("seed", [1, 3, 4])
def test_outputs_to_t_do_not_change_when_the_bars_after_t_are_removed(seed):
    bars = random_bars(3000, seed, decimals=1 if seed == 3 else (0 if seed == 4 else None))
    full = C.coil(*bars)
    starts, _, _ = coil_events(full)
    bo = np.flatnonzero(full["breakout"])
    cuts = {0, 1, 18, 19, 26, 27, 500, 2999, int(starts[3]), int(starts[3]) - 1, int(bo[4]), int(bo[4]) + 1,
            int(starts[-1])}
    for T in sorted(cuts):
        part = C.coil(*[x[:T + 1] for x in bars])
        assert outputs_equal(part, full, T + 1), T


def test_truncation_invariance_on_a_coil_sequence_at_every_bar():
    """Cut after every bar of a random coil sequence (arming bars, breakout bars, replacements, expiries)."""
    bars = random_k1_bars(400, 7)
    full = C.coil(*bars, **K1)
    for T in range(len(bars[0])):
        assert outputs_equal(C.coil(*[x[:T + 1] for x in bars], **K1), full, T + 1), T


# ───────────────────────────── 4. real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H / 1D bars of a symbol from its data start to 2024-06-30 (``load(symbol, end="2024-07-01")``
    with the guard pointed at an empty folder), one symbol in memory at a time."""
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
                mk = TM.load(symbol, end="2024-07-01")
                tb = {tf: mk.tbars(tf) for tf in TM.TFS}
            del mk
            cache[symbol] = tb
        return cache[symbol]
    return get


def check_structure(out, h, l, c, min_bars=6, armed_bars=12):
    """The contract's structure on any bars: the run counter, the armed windows, the boxes, the breakouts."""
    n = len(c)
    sq, rl, a, bo = out["squeeze_on"], out["run_len"], out["armed"], out["breakout"]
    prev = np.r_[0, rl[:-1]]
    assert np.array_equal(rl, np.where(sq, prev + 1, 0))
    # box finite exactly where armed, the broken box exactly where a breakout is, equal to the box there
    assert np.isfinite(out["box_hi"][a]).all() and np.isnan(out["box_hi"][~a]).all()
    assert np.isfinite(out["box_lo"][a]).all() and np.isnan(out["box_lo"][~a]).all()
    hit = bo != 0
    assert np.all(a[hit]) and set(np.unique(bo)) <= {-1, 0, 1}
    assert np.isfinite(out["bo_box_hi"][hit]).all() and np.isnan(out["bo_box_hi"][~hit]).all()
    assert np.isfinite(out["bo_box_lo"][hit]).all() and np.isnan(out["bo_box_lo"][~hit]).all()
    assert np.array_equal(out["bo_box_hi"][hit], out["box_hi"][hit])
    assert np.array_equal(out["bo_box_lo"][hit], out["box_lo"][hit])
    assert np.all(c[bo == 1] > out["box_hi"][bo == 1]) and np.all(c[bo == -1] < out["box_lo"][bo == -1])
    inside = a & ~hit
    assert np.all((c[inside] <= out["box_hi"][inside]) & (c[inside] >= out["box_lo"][inside]))
    starts = np.flatnonzero(a & ~np.r_[False, a[:-1]])
    ends = np.flatnonzero(a & ~np.r_[a[1:], False])
    assert len(starts) == len(ends)
    for s, e in zip(starts, ends):
        L = rl[s - 1]
        assert L >= min_bars and not sq[s]                                  # armed right after a coil's run
        assert out["box_hi"][s] == h[s - L:s].max() and out["box_lo"][s] == l[s - L:s].min()
        assert np.all(out["box_hi"][s:e + 1] == out["box_hi"][s])
        assert e - s + 1 <= armed_bars and np.count_nonzero(bo[s:e + 1]) <= 1 and (bo[s:e] == 0).all()
        if bo[e] == 0 and e - s + 1 < armed_bars and e + 1 < n:              # replaced: a newer run reaches 6
            assert rl[e + 1] == min_bars
    # every run of at least min_bars that ends before the last bar arms a coil on the next bar
    ended = np.flatnonzero((rl[:-1] >= min_bars) & ~sq[1:]) + 1
    assert np.array_equal(ended, starts)


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_smoke(symbol, real):
    tbars = real(symbol)
    a19, a23 = TM.s_of("2019-01-01"), TM.s_of("2023-01-01")
    for tf, least in (("1H", 200), ("4H", 50), ("1D", 10)):
        b = tbars[tf]
        n = len(b)
        assert n > 1500 and int(b.tc[-1]) <= TM.CUT_S, tf                     # nothing from the hold-out
        out = C.coil(b.o, b.h, b.l, b.c)
        assert tuple(out) == C.KEYS
        for k, v in out.items():
            assert v.shape == (n,) and v.dtype == DTYPES[k], (tf, k)
        # no NaN where the contract says values exist, NaN where it says none
        assert not out["squeeze_on"][:19].any() and out["squeeze_on"][19:].any()
        assert np.isnan(out["adx"][:27]).all() and np.isfinite(out["adx"][27:]).all(), tf
        assert np.all((out["adx"][27:] >= 0) & (out["adx"][27:] <= 100))
        check_structure(out, b.h, b.l, b.c)
        w = (b.tc >= a19) & (b.tc < a23)
        bo = out["breakout"]
        assert ((bo == 1) & w).sum() >= least // 2 and ((bo == -1) & w).sum() >= least // 3, tf
        assert ((bo != 0) & w).sum() >= least, tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_equal_the_transcription_bit_for_bit(symbol, real):
    tbars = real(symbol)
    for tf in ("1H", "4H", "1D"):
        b = tbars[tf]
        port = C.coil(b.o, b.h, b.l, b.c)
        assert outputs_equal(port, Transcription().run(b.o, b.h, b.l, b.c)), tf
        other = LI.adx(b.h, b.l, b.c, 14)[0]                                    # another study's Wilder ADX
        assert np.array_equal(np.isnan(other), np.isnan(port["adx"])) and np.nanmax(np.abs(other - port["adx"])) < 1e-12


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_truncation_invariance(symbol, real):
    tbars = real(symbol)
    for tf in ("1H", "4H", "1D"):
        b = tbars[tf]
        full = C.coil(b.o, b.h, b.l, b.c)
        for when in ("2020-03-16 12:00", "2022-11-09 00:00"):
            j = int(np.searchsorted(b.tc, TM.s_of(when), side="right")) - 1
            part = C.coil(b.o[:j + 1], b.h[:j + 1], b.l[:j + 1], b.c[:j + 1])
            assert outputs_equal(part, full, j + 1), (tf, when)
