"""
Higher-timeframe support and resistance: a causal level detector, and the study of how price
reacts at the levels it finds (``backtest_results/improve/sr_study.md``).

    python -m backtesting.research.sr levels XAUUSDm 2026-10-01 2026-11-13    # the level table, last rows
    python -m backtesting.research.sr study    DEV     [out_dir]              # events, outcomes and every table of a period
    python -m backtesting.research.sr variants DEV     [out_dir]              # the main table under other definitions
    python -m backtesting.research.sr study    CONFIRM [out_dir]
    python -m backtesting.research.sr report   [out_dir]                      # all tables, the periods side by side

``out_dir`` (default ``sr_study_out``, or the environment variable ALCADEIAS_SR_OUT) receives the events
and tables of each period; the tick store is read from ``data/store`` or ALCADEIAS_STORE_DIR.

The detector
------------
A level is a price with the time from which it is known:

* swing highs and lows of H1, H4 and D1 bars (fractal pivots, ``pivot_w`` bars on each side; known
  when the last of those bars has closed);
* the high, low and close of the previous day and of the previous week (known when that day or week
  is over, kept while it is the previous one);
* round numbers (gold: multiples of 50 and 100; BTC: of 1,000 and 5,000).

The same price extreme is one level however many of these it is: a D1 swing high is also an H4 and an
H1 swing high and often the previous day's high. It is stored once and carries each class from the
moment that class is known.

Every level is followed minute by minute through one small state machine. Distances are in units of
the ATR(14) of H1 bars as it stood at the last closed H1 bar:

* *side*: +1 once a bar of the decision clock (M15) has closed ``buffer`` above the level (it is a
  support), -1 once one has closed that far below (a resistance). A close ``buffer`` beyond the level
  on the other side is a *break*: the level changes role, and a swing or previous-day / week level
  broken a second time is dropped.
* *armed*: price has closed at least ``away`` from the level on its side since the last touch.
* *touch*: the first minute in which the price of an armed level comes within ``zone`` of it. Levels
  of the same side within ``tol`` of the touched one form its zone; they share the touch, so a zone is
  one approach however many levels it holds.

``nearest_levels`` returns, for every M15 close, the nearest support and resistance with their class,
age, touches, breaks and zone strength. ``scan`` also returns the touch and break events themselves.
Nothing is read from a bar that had not closed at the time: tests/test_sr_levels.py cuts the history at
arbitrary bars and requires every earlier row and event to be unchanged.

Conventions: bars are bid bars on UTC boundaries, as the MT5 terminal builds them. Gold's short Sunday
session (22:00 or 23:00 to 24:00 UTC) is counted with Monday, so a week has five daily bars; weeks run
Monday to Sunday.

The reaction study
------------------
``collect`` lists every touch and break of a period, on the real level map and on control maps (the
same levels moved by a fixed fraction of price), with the state of the market at the event and the
outcome of five simple trades; ``tables`` compares levels with control and gives the profit per trade
after the spread. The rules of the trades and of the comparison are in the comment above ``PERIODS``.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from numba import njit

from ..data import store

# ───────────────────────────── definitions ─────────────────────────────

# classes of a level, in the order of their bit in a class mask
C_H1, C_H4, C_D1, C_PDHL, C_PWHL, C_PDC, C_PWC, C_R1, C_R2 = range(9)
CLASS_NAMES = ("H1 swing", "H4 swing", "D1 swing", "previous-day high/low", "previous-week high/low",
               "previous-day close", "previous-week close", "round number (minor)", "round number (major)")
# what a level of each class adds to the strength of its zone (a level counts once, with its largest class)
CLASS_WEIGHT = np.array([1.0, 2.0, 3.0, 2.0, 3.0, 1.0, 2.0, 1.0, 2.0])
N_CLASS = len(CLASS_NAMES)

K_HIGH, K_LOW, K_CLOSE, K_ROUND = range(4)                 # how a level came about
KIND_NAMES = ("high", "low", "close", "round")

FOREVER = np.iinfo(np.int64).max // 4

SYMBOLS = {
    # usd: P/L in USD of a 0.01 lot per 1.00 of price; round: minor and major round-number step;
    # sunday_with_monday: the market is closed at weekends and reopens late on Sunday (UTC);
    # shifts: how far the whole level map is moved to make the control maps of the reaction study
    "XAUUSDm": dict(usd=1.0, round=(50.0, 100.0), sunday_with_monday=True, shifts=(-0.010, -0.006, 0.006, 0.010)),
    "BTCUSDm": dict(usd=0.01, round=(1000.0, 5000.0), sunday_with_monday=False, shifts=(-0.015, -0.009, 0.009, 0.015)),
}


@dataclass(frozen=True)
class SRParams:
    """The definitions of the detector. Distances are multiples of the ATR of H1 bars."""
    pivot_w: int = 3            # bars on each side of a swing high / low, the same on H1, H4 and D1
    atr_len: int = 14           # ATR length (H1 bars, Wilder smoothing)
    zone: float = 0.10          # a touch: price within this of the level
    tol: float = 0.25           # levels of one side this close together are one zone
    buffer: float = 0.25        # a decision-clock close this far beyond a level breaks it
    away: float = 1.0           # price must have closed this far from a level before an approach counts
    max_age_bars: int = 500     # a swing level is kept for this many bars of its own timeframe
    max_flips: int = 1          # role changes a level survives (1: resistance -> support -> dropped)
    base_tf: int = 900          # the decision clock in seconds (M15)


# ───────────────────────────── bars ─────────────────────────────

def _group(key: np.ndarray):
    """First and last index of every run of equal keys (keys are non-decreasing)."""
    first = np.flatnonzero(np.diff(key, prepend=key[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(key) - 1)
    return first, last


def bars_of(m1: Dict[str, np.ndarray], key: np.ndarray) -> Dict[str, np.ndarray]:
    """OHLC bars of the M1 bars grouped by ``key``, with the M1 index range of each bar."""
    first, last = _group(key)
    return {"key": key[first], "first": first, "last": last, "o": m1["o"][first],
            "h": np.maximum.reduceat(m1["h"], first), "l": np.minimum.reduceat(m1["l"], first), "c": m1["c"][last]}


def day_key(t: np.ndarray, sunday_with_monday: bool) -> np.ndarray:
    """UTC day number of each bar; a Sunday session is counted with the Monday that follows it."""
    d = t // 86400
    if sunday_with_monday:
        d = np.where((d + 3) % 7 == 6, d + 1, d)
    return d


def week_key(day: np.ndarray) -> np.ndarray:
    """Week number of a day number; weeks run Monday to Sunday (UTC)."""
    return (day + 3) // 7


def atr_wilder(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    """ATR with Wilder smoothing; NaN until ``n`` true ranges exist."""
    if len(c) < 2:
        return np.full(len(c), np.nan)
    tr = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    a = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    a[: n - 1] = np.nan
    return np.concatenate([[np.nan], a])


def asof(end: np.ndarray, values: np.ndarray, when: np.ndarray) -> np.ndarray:
    """``values`` of the last bar whose close time ``end`` is not after ``when`` (NaN before the first)."""
    i = np.searchsorted(end, when, side="right") - 1
    out = np.asarray(values, dtype=float)[np.clip(i, 0, None)].copy()
    out[i < 0] = np.nan
    return out


@njit(cache=True)
def _pivots(h, l, w):
    """Swing highs / lows: above (below) the ``w`` bars before, not below (above) the ``w`` bars after."""
    n = len(h)
    hi = np.zeros(n, np.bool_)
    lo = np.zeros(n, np.bool_)
    for i in range(w, n - w):
        a = True
        b = True
        for j in range(1, w + 1):
            if not (h[i] > h[i - j] and h[i] >= h[i + j]):
                a = False
            if not (l[i] < l[i - j] and l[i] <= l[i + j]):
                b = False
        hi[i] = a
        lo[i] = b
    return hi, lo


# ───────────────────────────── the level records ─────────────────────────────

def build_levels(m1: Dict[str, np.ndarray], symbol: str, p: SRParams = SRParams()) -> Dict[str, np.ndarray]:
    """
    Every level of the history as one record: price, how it came about, the M1 bar after which it is
    followed, and for each class the time from which it is known and until which it is kept.

    A record whose classes are all known only later than some time T has no effect on anything
    reported up to T (see ``_scan``), which is what makes the detector causal.
    """
    spec = SYMBOLS[symbol]
    t, h, l, c = m1["t"], m1["h"], m1["l"], m1["c"]
    w = p.pivot_w
    rec: Dict[tuple, list] = {}

    def add(kind, idx, price, cls, known_from, known_to):
        r = rec.get((kind, idx))
        if r is None:
            r = rec[(kind, idx)] = [float(price), np.full(N_CLASS, FOREVER, np.int64), np.zeros(N_CLASS, np.int64)]
        r[1][cls], r[2][cls] = known_from, known_to

    def extremes(b, i):
        """M1 index of the first highest high and of the first lowest low inside bar ``i``."""
        a, z = b["first"][i], b["last"][i] + 1
        return a + int(np.argmax(h[a:z])), a + int(np.argmin(l[a:z]))

    # swing highs and lows of H1, H4 and D1 bars
    dk = day_key(t, spec["sunday_with_monday"])
    frames = ((C_H1, 3600, bars_of(m1, t // 3600)), (C_H4, 14400, bars_of(m1, t // 14400)), (C_D1, 86400, bars_of(m1, dk)))
    for cls, tf, b in frames:
        end = (b["key"] + 1) * tf
        hi, lo = _pivots(b["h"], b["l"], w)
        for i in np.flatnonzero(hi | lo):
            ih, il = extremes(b, i)
            if hi[i]:
                add(K_HIGH, ih, h[ih], cls, end[i + w], t[ih] + p.max_age_bars * tf)
            if lo[i]:
                add(K_LOW, il, l[il], cls, end[i + w], t[il] + p.max_age_bars * tf)

    # high, low and close of the previous day and of the previous week. A day is over at the next UTC
    # midnight; a week on Monday 00:00, or on Saturday 00:00 where the market is closed at weekends
    # (so that Sunday's reopening already reads the week that ended on Friday).
    d1 = frames[2][2]
    w1 = bars_of(m1, week_key(dk))
    week_end = (w1["key"] * 7 + (2 if spec["sunday_with_monday"] else 4)) * 86400
    for cls_hl, cls_c, b, end in ((C_PDHL, C_PDC, d1, (d1["key"] + 1) * 86400), (C_PWHL, C_PWC, w1, week_end)):
        for i in range(len(end)):
            until = end[i + 1] if i + 1 < len(end) else FOREVER
            ih, il = extremes(b, i)
            add(K_HIGH, ih, h[ih], cls_hl, end[i], until)
            add(K_LOW, il, l[il], cls_hl, end[i], until)
            add(K_CLOSE, b["last"][i], c[b["last"][i]], cls_c, end[i], until)

    # round numbers: always known, never dropped
    minor, major = spec["round"]
    lo_px, hi_px = float(np.min(l)), float(np.max(h))
    for q in range(int(np.floor(lo_px / minor)) - 3, int(np.ceil(hi_px / minor)) + 4):
        if q > 0:
            add(K_ROUND, -q, q * minor, C_R1, 0, FOREVER)
            if abs(q * minor / major - round(q * minor / major)) < 1e-9:
                add(K_ROUND, -q, q * minor, C_R2, 0, FOREVER)

    # order: by the bar after which a record is followed, then by kind; ties between equal prices are
    # resolved by this order everywhere, so it must not depend on what comes later in the history
    keys = sorted(rec, key=lambda k: (max(k[1] + 1, 0), k[0], k[1]))
    n = len(keys)
    out = {"price": np.array([rec[k][0] for k in keys]), "kind": np.array([k[0] for k in keys], np.int8),
           "i_start": np.array([max(k[1] + 1, 0) for k in keys], np.int64),
           "kfrom": np.array([rec[k][1] for k in keys], np.int64).reshape(n, N_CLASS),
           "kto": np.array([rec[k][2] for k in keys], np.int64).reshape(n, N_CLASS)}
    out["t0"] = np.where(out["kind"] == K_ROUND, 0, t[np.clip(out["i_start"] - 1, 0, None)])     # when the extreme was made
    out["t_dead"] = np.where(out["kind"] == K_ROUND, FOREVER, out["kto"].max(axis=1))
    out["mortal"] = (out["kind"] != K_ROUND).astype(np.uint8)
    return out


# ───────────────────────────── the scan ─────────────────────────────

@njit(cache=True)
def _mask(kfrom, kto, i, when):
    """The classes of record ``i`` that are known at time ``when``, as a bit mask (0: not a level yet)."""
    m = 0
    for q in range(kfrom.shape[1]):
        if kfrom[i, q] <= when and when < kto[i, q]:
            m |= 1 << q
    return m


@njit(cache=True)
def _weight(m, cw):
    w = 0.0
    for q in range(len(cw)):
        if (m >> q) & 1 and cw[q] > w:
            w = cw[q]
    return w


@njit(cache=True)
def _scan(t, o, h, l, c, atr, base_end, price, i_start, kfrom, kto, t_dead, mortal, cw,
          zone, tol, buf, away, max_flips, cap, n_base):
    """
    Follow every record through the M1 bars. Returns the touch events, the break events and the
    nearest support / resistance at every decision-clock close.

    Causality. A record is followed from the bar after its extreme, before it is known to be a level,
    so that its touches and its distance from price are already there when it becomes one. Until then
    it changes nothing but itself: only a known record can trigger an event, disarm the other records
    of its zone, be counted in a zone or appear in a snapshot.
    """
    n = len(t)
    R = len(price)
    side = np.zeros(R, np.int8)
    armed = np.zeros(R, np.uint8)
    k_armed = np.full(R, -1, np.int64)
    touches = np.zeros(R, np.int32)
    flips = np.zeros(R, np.int32)
    k_flip = np.full(R, -1, np.int64)
    k_touch = np.full(R, -1, np.int64)
    fnow = np.zeros(R, np.int8)
    i_death = np.full(R, np.iinfo(np.int64).max, np.int64)      # the bar from which a record is no longer followed
    act = np.empty(R, np.int64)
    cand = np.empty(R, np.int64)
    tei = np.zeros((cap, 11), np.int64)
    tef = np.zeros((cap, 4), np.float64)
    bei = np.zeros((cap, 9), np.int64)
    bef = np.zeros((cap, 3), np.float64)
    sni = np.full((n_base, 13), -1, np.int64)
    snf = np.full((n_base, 6), np.nan)
    nt = 0
    nb = 0
    ib = 0
    na = 0
    p = 0
    for k in range(n):
        while p < R and i_start[p] <= k:
            if t_dead[p] > t[k]:
                act[na] = p
                na += 1
            else:
                i_death[p] = k
            p += 1
        a = atr[k]
        be = base_end[k]
        if a > 0.0:
            za = zone * a
            aw = away * a
            ta = tol * a
            lo = l[k]
            hi = h[k]
            cl = c[k]
            nc = 0
            for ii in range(na):
                i = act[ii]
                s = side[i]
                if s == 0:
                    continue
                if armed[i] == 1:
                    if s > 0:
                        if lo <= price[i] + za:
                            cand[nc] = i
                            nc += 1
                    elif hi >= price[i] - za:
                        cand[nc] = i
                        nc += 1
                elif s * (cl - price[i]) >= aw:
                    armed[i] = 1
                    k_armed[i] = k
            if nc > 0:
                # touches of this minute: supports from the highest down, resistances from the lowest up
                for sgn in (1, -1):
                    while True:
                        best = -1
                        for q in range(nc):
                            i = cand[q]
                            if i < 0 or side[i] != sgn:
                                continue
                            if best < 0:
                                best = q
                            else:
                                b = cand[best]
                                if sgn * (price[i] - price[b]) > 0 or (price[i] == price[b] and i < b):
                                    best = q
                        if best < 0:
                            break
                        i = cand[best]
                        cand[best] = -1
                        if armed[i] == 0:
                            continue                       # already part of a zone touched this minute
                        L = price[i]
                        own = _mask(kfrom, kto, i, t[k])
                        if own != 0:
                            nz = 0
                            zm = 0
                            zt = 0
                            zs = 0.0
                            for jj in range(na):
                                j = act[jj]
                                if side[j] != sgn or abs(price[j] - L) > ta:
                                    continue
                                mj = _mask(kfrom, kto, j, t[k])
                                if mj != 0:
                                    nz += 1
                                    zm |= mj
                                    zs += _weight(mj, cw)
                                    if touches[j] > zt:
                                        zt = touches[j]
                                if j != i and armed[j] == 1 and k_armed[j] < k:
                                    touches[j] += 1
                                    k_touch[j] = k
                                    armed[j] = 0
                                    if sgn * (cl - price[j]) >= aw:
                                        armed[j] = 1
                                        k_armed[j] = k
                            if nt < cap:
                                thr = L + sgn * za
                                tei[nt, 0] = i
                                tei[nt, 1] = k
                                tei[nt, 2] = sgn
                                tei[nt, 3] = touches[i]
                                tei[nt, 4] = zt
                                tei[nt, 5] = flips[i]
                                tei[nt, 6] = nz
                                tei[nt, 7] = zm
                                tei[nt, 8] = own
                                tei[nt, 9] = k_flip[i]
                                tei[nt, 10] = k_touch[i]
                                tef[nt, 0] = L
                                tef[nt, 1] = a
                                tef[nt, 2] = min(o[k], thr) if sgn > 0 else max(o[k], thr)
                                tef[nt, 3] = zs
                            nt += 1
                        touches[i] += 1
                        k_touch[i] = k
                        armed[i] = 0
                        if sgn * (cl - L) >= aw:
                            armed[i] = 1
                            k_armed[i] = k
            if be > 0:
                # the decision clock closes: expiries, sides and breaks
                ba = buf * a
                nf = 0
                ii = 0
                while ii < na:
                    i = act[ii]
                    if t_dead[i] <= be:
                        i_death[i] = k + 1
                        na -= 1
                        act[ii] = act[na]
                        continue
                    d = cl - price[i]
                    s = side[i]
                    if s == 0:
                        if d >= ba:
                            side[i] = 1
                        elif d <= -ba:
                            side[i] = -1
                    elif s * d <= -ba:
                        cand[nf] = i
                        nf += 1
                        fnow[i] = -s
                    ii += 1
                if nf > 0:
                    for q in range(nf):
                        i = cand[q]
                        dirn = fnow[i]
                        L = price[i]
                        own = _mask(kfrom, kto, i, be)
                        if own == 0:
                            continue
                        held = False
                        nz = 0
                        zm = 0
                        for jj in range(na):
                            j = act[jj]
                            dl = dirn * (price[j] - L)
                            if dl > ta or dl < -ta:
                                continue
                            mj = _mask(kfrom, kto, j, be)
                            if mj == 0:
                                continue
                            if j != i and dl >= 0:
                                if fnow[j] == dirn:
                                    if dl > 0 or j > i:
                                        held = True            # the farthest level of the zone carries the break
                                elif fnow[j] == 0 and side[j] == -dirn:
                                    held = True                # an unbroken level just beyond: not through the zone yet
                            if dl <= 0 and (fnow[j] == dirn or (side[j] == dirn and k_flip[j] >= k - 240)):
                                nz += 1
                                zm |= mj
                        if not held:
                            if nb < cap:
                                bei[nb, 0] = i
                                bei[nb, 1] = k
                                bei[nb, 2] = dirn
                                bei[nb, 3] = touches[i]
                                bei[nb, 4] = flips[i]
                                bei[nb, 5] = nz
                                bei[nb, 6] = own
                                bei[nb, 7] = zm
                                bei[nb, 8] = k_flip[i]
                                bef[nb, 0] = L
                                bef[nb, 1] = a
                                bef[nb, 2] = cl
                            nb += 1
                    for q in range(nf):
                        i = cand[q]
                        flips[i] += 1
                        side[i] = fnow[i]
                        fnow[i] = 0
                        armed[i] = 0
                        k_flip[i] = k
                        if mortal[i] == 1 and flips[i] > max_flips:
                            i_death[i] = k + 1
                    ii = 0
                    while ii < na:
                        if i_death[act[ii]] <= k + 1:
                            na -= 1
                            act[ii] = act[na]
                            continue
                        ii += 1
                if n_base > 0:
                    # nearest known support (highest) and resistance (lowest) at this close
                    bs = -1
                    br = -1
                    for jj in range(na):
                        j = act[jj]
                        if side[j] == 0 or _mask(kfrom, kto, j, be) == 0:
                            continue
                        if side[j] > 0:
                            if bs < 0 or price[j] > price[bs] or (price[j] == price[bs] and j < bs):
                                bs = j
                        elif br < 0 or price[j] < price[br] or (price[j] == price[br] and j < br):
                            br = j
                    snf[ib, 4] = a
                    snf[ib, 5] = cl
                    for which in range(2):
                        i = bs if which == 0 else br
                        if i < 0:
                            continue
                        nz = 0
                        zm = 0
                        zs = 0.0
                        for jj in range(na):
                            j = act[jj]
                            if side[j] != side[i] or abs(price[j] - price[i]) > ta:
                                continue
                            mj = _mask(kfrom, kto, j, be)
                            if mj != 0:
                                nz += 1
                                zm |= mj
                                zs += _weight(mj, cw)
                        c0 = 1 + which * 6
                        sni[ib, c0] = i
                        sni[ib, c0 + 1] = _mask(kfrom, kto, i, be)
                        sni[ib, c0 + 2] = zm
                        sni[ib, c0 + 3] = nz
                        sni[ib, c0 + 4] = touches[i]
                        sni[ib, c0 + 5] = flips[i] * 2 + armed[i]
                        snf[ib, which * 2] = price[i]
                        snf[ib, which * 2 + 1] = zs
        if be > 0:
            if n_base > 0:
                sni[ib, 0] = k
            ib += 1
    return tei, tef, nt, bei, bef, nb, sni, snf, i_death


def _base_end(t: np.ndarray, base_tf: int) -> np.ndarray:
    """
    For the last M1 bar of every decision-clock bar: the time that bar closes; 0 elsewhere. The final
    M1 bar of the history closes its decision bar only if it is that bar's last minute, since more
    minutes of it may still come.
    """
    bucket = t // base_tf
    out = np.zeros(len(t), np.int64)
    if len(t) == 0:
        return out
    last = np.flatnonzero(np.diff(bucket) != 0)
    out[last] = (bucket[last] + 1) * base_tf
    if (t[-1] + 60) % base_tf == 0:
        out[-1] = t[-1] + 60
    return out


def prepare(m1: Dict[str, np.ndarray], symbol: str, p: SRParams = SRParams()) -> dict:
    """The inputs of a scan: the M1 bars, the H1 ATR known at each of them, the decision clock, the records."""
    t = np.asarray(m1["t"], np.int64)
    m1 = {k: np.ascontiguousarray(m1[k], dtype=np.float64) for k in ("o", "h", "l", "c", "spread_mean")} | {"t": t}
    h1 = bars_of(m1, t // 3600)
    atr = asof((h1["key"] + 1) * 3600, atr_wilder(h1["h"], h1["l"], h1["c"], p.atr_len), t)
    return {"symbol": symbol, "p": p, "m1": m1, "atr": atr, "base_end": _base_end(t, p.base_tf),
            "levels": build_levels(m1, symbol, p)}


def scan(prep: dict, shift: float = 0.0, snapshots: bool = True) -> dict:
    """
    Run the detector over a prepared history.

    ``shift`` moves every level by that fraction of its price before the scan: the control maps of the
    reaction study, in which the same levels stand where nothing marks them.

    Returns ``touch`` and ``brk`` (one row per event) and, with ``snapshots``, ``snap`` (one row per
    decision-clock close); see ``nearest_levels`` for the columns of the latter.

    ``touch``: ``k`` the M1 bar of the touch and ``t`` its open time; ``side`` +1 a support reached from
    above, -1 a resistance from below; ``level``; ``atr``; ``entry`` the edge of the zone, or the open
    of the minute after a gap beyond it; ``kind`` and ``own_mask`` of the level reached first;
    ``zone_mask``, ``n_zone``, ``strength`` of its zone; ``touches`` / ``zone_touches`` earlier approaches
    of the level / of any level of the zone; ``flips`` times it has been broken; ``age_s``,
    ``since_flip_s``, ``since_touch_s`` in seconds (NaN where there is none).
    ``brk``: ``k`` the last M1 bar of the decision bar that closed beyond the level and ``t`` its close
    time; ``side`` +1 broken upwards; ``entry`` that close; ``flips`` the breaks before this one.
    """
    p, m1, lv = prep["p"], prep["m1"], prep["levels"]
    t = m1["t"]
    price = lv["price"] * (1.0 + shift)
    n_base = int((prep["base_end"] > 0).sum()) if snapshots else 0
    cap = 40 * len(price) + 10_000
    while True:
        tei, tef, nt, bei, bef, nb, sni, snf, i_death = _scan(
            t, m1["o"], m1["h"], m1["l"], m1["c"], prep["atr"], prep["base_end"], price, lv["i_start"], lv["kfrom"], lv["kto"],
            lv["t_dead"], lv["mortal"], CLASS_WEIGHT, p.zone, p.tol, p.buffer, p.away, p.max_flips, cap, n_base)
        if nt <= cap and nb <= cap:
            break
        cap = max(nt, nb) + 1
    tei, tef, bei, bef = tei[:nt], tef[:nt], bei[:nb], bef[:nb]

    def ago(k_then, k_now):          # seconds since an earlier bar; NaN when there was none
        return np.where(k_then >= 0, t[k_now] - t[np.clip(k_then, 0, None)], np.nan).astype(float)

    r = tei[:, 0]
    touch = pd.DataFrame({
        "k": tei[:, 1], "t": t[tei[:, 1]], "side": tei[:, 2].astype(np.int8), "level": tef[:, 0], "atr": tef[:, 1],
        "entry": tef[:, 2], "kind": lv["kind"][r], "own_mask": tei[:, 8], "zone_mask": tei[:, 7], "n_zone": tei[:, 6],
        "strength": tef[:, 3] + np.minimum(tei[:, 4], 3), "touches": tei[:, 3], "zone_touches": tei[:, 4], "flips": tei[:, 5],
        "age_s": np.where(lv["kind"][r] == K_ROUND, np.nan, t[tei[:, 1]] - lv["t0"][r]).astype(float),
        "since_flip_s": ago(tei[:, 9], tei[:, 1]), "since_touch_s": ago(tei[:, 10], tei[:, 1]), "rec": r})
    r = bei[:, 0]
    brk = pd.DataFrame({
        "k": bei[:, 1], "t": prep["base_end"][bei[:, 1]], "side": bei[:, 2].astype(np.int8), "level": bef[:, 0], "atr": bef[:, 1],
        "entry": bef[:, 2], "kind": lv["kind"][r], "own_mask": bei[:, 6], "zone_mask": bei[:, 7], "n_zone": bei[:, 5],
        "touches": bei[:, 3], "flips": bei[:, 4],
        "age_s": np.where(lv["kind"][r] == K_ROUND, np.nan, prep["base_end"][bei[:, 1]] - lv["t0"][r]).astype(float),
        "since_flip_s": ago(bei[:, 8], bei[:, 1]), "rec": r})
    order = np.lexsort((touch["rec"].to_numpy(), touch["k"].to_numpy()))
    out = {"touch": touch.iloc[order].reset_index(drop=True), "brk": brk.sort_values(["k", "rec"]).reset_index(drop=True),
           "i_death": i_death, "price": price}
    if snapshots:
        k = sni[:, 0]
        snap = {"t": (t[k] // p.base_tf) * p.base_tf, "t_close": prep["base_end"][k], "close": m1["c"][k], "atr": snf[:, 4]}
        for which, name in enumerate(("sup", "res")):
            c0 = 1 + which * 6
            i = sni[:, c0]
            ok = i >= 0
            ic = np.clip(i, 0, None)
            px = snf[:, which * 2]
            sign = 1.0 if which == 0 else -1.0
            snap[f"{name}_price"] = px
            snap[f"{name}_dist"] = sign * (snap["close"] - px) / snf[:, 4]
            snap[f"{name}_kind"] = np.where(ok, lv["kind"][ic], -1).astype(np.int8)
            snap[f"{name}_mask"] = np.where(ok, sni[:, c0 + 1], 0)
            snap[f"{name}_zone_mask"] = np.where(ok, sni[:, c0 + 2], 0)
            snap[f"{name}_n_zone"] = np.where(ok, sni[:, c0 + 3], 0)
            snap[f"{name}_touches"] = np.where(ok, sni[:, c0 + 4], 0)
            snap[f"{name}_flips"] = np.where(ok, sni[:, c0 + 5] // 2, 0)
            snap[f"{name}_armed"] = np.where(ok, sni[:, c0 + 5] % 2, 0).astype(bool)
            snap[f"{name}_age_s"] = np.where(ok & (lv["kind"][ic] != K_ROUND), snap["t_close"] - lv["t0"][ic], np.nan).astype(float)
            snap[f"{name}_strength"] = np.where(ok, snf[:, which * 2 + 1] + np.minimum(np.where(ok, sni[:, c0 + 4], 0), 3), np.nan)
        out["snap"] = pd.DataFrame(snap)
    return out


def top_class(mask) -> np.ndarray:
    """The largest timeframe class in a class mask: 'D1' > 'W' (previous week) > 'H4' > 'D' (previous day) > 'H1' > 'round'."""
    m = np.asarray(mask, np.int64)
    out = np.full(m.shape, "none", dtype=object)
    for name, bits in (("round", (C_R1, C_R2)), ("H1", (C_H1,)), ("D", (C_PDHL, C_PDC)), ("H4", (C_H4,)), ("W", (C_PWHL, C_PWC)), ("D1", (C_D1,))):
        hit = np.zeros(m.shape, bool)
        for b in bits:
            hit |= ((m >> b) & 1).astype(bool)
        out[hit] = name
    return out


def nearest_levels(m1: Dict[str, np.ndarray], symbol: str, p: SRParams = SRParams()) -> pd.DataFrame:
    """
    The nearest support and resistance at every close of the decision clock (M15 by default), from
    M1 bid bars as ``backtesting.data.store.load_m1`` returns them.

    One row per decision bar, read at ``t_close``; nothing in a row uses a bar that closes later.
    For ``sup`` (the highest level price has closed above) and ``res`` (the lowest it has closed below):

    ``*_price``      the level                      ``*_dist``      close to level, in H1 ATRs (can be slightly
                                                                    negative while the level is being tested)
    ``*_kind``       0 high, 1 low, 2 close, 3 round ``*_mask``     its classes, one bit each in CLASS_NAMES order
    ``*_tf``         its largest class (top_class)   ``*_age_s``    seconds since the extreme was made
    ``*_touches``    approaches it has had so far    ``*_flips``    times it has been broken
    ``*_armed``      price has been ``away`` since   ``*_n_zone``   known levels of the same side within ``tol``
    ``*_zone_mask``  classes present in the zone     ``*_strength`` zone weight by class + touches (at most 3)

    ``atr`` is the H1 ATR the detector worked with in the bar's last minute (that of the last H1 bar
    closed before it). Rows before the ATR exists hold NaN and no level.
    """
    snap = scan(prepare(m1, symbol, p))["snap"]
    for name in ("sup", "res"):
        snap[f"{name}_tf"] = top_class(snap[f"{name}_mask"])
    return snap


# ───────────────────────────── the reaction study ─────────────────────────────
#
# What is measured, and against what.
#
#   Bounce trade.  At a touch, a position is opened away from the level (long at a support, short at
#   a resistance) at the touch price plus the spread of that minute. It ends at the first of: TARGET
#   ATRs of profit measured from the touch price (a bounce), STOP ATRs beyond the level (a break), or
#   24 hours (closed at the market). The path is followed on M1 bid bars; in a minute that holds
#   both, the break counts, and in the minute of the touch itself only a break is accepted.
#
#   Through trade. The mirror image, opened at the same touch: short at a support, long at a
#   resistance, target STOP ATRs beyond the level, stop TARGET ATRs back from the touch price. In the
#   minute of the touch its stop is accepted before its target.
#
#   Breakout trade.  At the M15 close that breaks a level (``buffer`` beyond it), a position is opened
#   in the direction of the break and ends at +1 or -1 ATR from that close, or after 24 hours.
#
#   Rejection trade. The bounce trade of a trader who waits to see the level hold: after a touch, the
#   first M15 close at least REJECT ATRs back from the level, if it comes within REJECT_BARS closes and
#   before a close ``buffer`` beyond the level. Opened at that close away from the level, +1 / -1 ATR.
#
#   Random walk.   Without drift, the nearer barrier is reached first in proportion to the distances:
#   a bounce has probability (zone + STOP) / (TARGET + zone + STOP).
#
#   Control.       The whole level map is moved by a fixed fraction of price (SYMBOLS[...]['shifts'])
#   and scanned again: the same levels, with the same lifetimes and classes, approached by the same
#   market, but standing where nothing marks them. Control events closer than EXCL ATRs to a real
#   level are left out. Rates are compared after matching the control to the real events by
#   half-year, side, session and volatility state.

PERIODS = {   # name: (history read from, events counted from, events counted until)
    "DEV": ("2025-07-01", "2025-08-01", "2026-11-13"),
    "CONFIRM": ("2024-01-01", "2024-02-01", "2025-07-01"),
}
HORIZON_S = 86400
TARGET, STOP = 1.0, 0.5                                   # the bounce trade every table uses
GRID = tuple((r, s) for r in (0.5, 1.0, 2.0) for s in (0.25, 0.5, 1.0))     # other shapes, shown once for sensitivity
BREAKOUT_TARGET = BREAKOUT_STOP = 1.0
REJECT, REJECT_BARS = 0.5, 16
RANGING, TRENDING = 0.06, 0.125                           # efficiency ratio of 120 H1 closes: about its lower and upper third
EXCL = 0.5
BOOT = 1000


@njit(cache=True)
def _races(t, o, h, l, c, k_in, mode, d, target, stop, t_end):
    """
    For each trade: which of ``target`` and ``stop`` the bid reaches first.

    ``mode`` says how the trade stands in bar ``k_in``:
      0  opened at the close of that bar: the race starts with the next bar;
      1  opened inside it, against the move that brought price there (a bounce trade at a touch): the
         bar's extreme beyond the stop is certain to have come after the entry, its other extreme may
         have come before, so only the stop is accepted in that bar;
      2  opened inside it, with the move (a through trade at a touch): both are accepted, the stop first.
    From the next bar on, a bar that opens beyond a barrier exits at its open and a bar that holds both
    barriers exits at the stop. Returns the outcome (+1 target, -1 stop, 0 still open at ``t_end``),
    the exit bar and the exit bid.
    """
    n = len(t)
    m = len(k_in)
    code = np.zeros(m, np.int8)
    k_out = np.zeros(m, np.int64)
    px = np.zeros(m, np.float64)
    for e in range(m):
        k = k_in[e]
        up = d[e] > 0
        tg = target[e]
        st = stop[e]
        if mode > 0:
            if (up and l[k] <= st) or ((not up) and h[k] >= st):
                code[e] = -1
                k_out[e] = k
                px[e] = (min(st, o[k]) if up else max(st, o[k])) if mode == 1 else st
                continue
            if mode == 2 and ((up and h[k] >= tg) or ((not up) and l[k] <= tg)):
                code[e] = 1
                k_out[e] = k
                px[e] = max(tg, o[k]) if up else min(tg, o[k])      # opened beyond the target: out where it came in
                continue
        kk = k + 1
        while True:
            if kk >= n or t[kk] >= t_end[e]:
                k_out[e] = kk - 1
                px[e] = c[kk - 1]
                break
            if up:
                if o[kk] <= st or l[kk] <= st:
                    code[e] = -1
                    px[e] = min(st, o[kk])
                elif h[kk] >= tg:
                    code[e] = 1
                    px[e] = max(tg, o[kk])
            else:
                if o[kk] >= st or h[kk] >= st:
                    code[e] = -1
                    px[e] = max(st, o[kk])
                elif l[kk] <= tg:
                    code[e] = 1
                    px[e] = min(tg, o[kk])
            if code[e] != 0:
                k_out[e] = kk
                break
            kk += 1
    return code, k_out, px


@njit(cache=True)
def _rejections(c, base_end, k, side, level, atr, buf, back, max_bars):
    """
    For each touch: the bar of the first decision-clock close at least ``back`` ATRs from the level on
    the side price came from, provided no close ``buf`` beyond the level comes first; -1 if neither
    happens within ``max_bars`` closes.
    """
    out = np.full(len(k), -1, np.int64)
    n = len(c)
    for e in range(len(k)):
        j = k[e]
        seen = 0
        while j < n and seen < max_bars:
            if base_end[j] > 0:
                seen += 1
                d = side[e] * (c[j] - level[e])
                if d <= -buf * atr[e]:
                    break
                if d >= back * atr[e]:
                    out[e] = j
                    break
            j += 1
    return out


@njit(cache=True)
def _near_level(k, level, atr, t, price, i_start, i_death, kfrom, kto, excl):
    """For each event: is a known level of the real map within ``excl`` ATRs of its price?"""
    out = np.zeros(len(k), np.bool_)
    for e in range(len(k)):
        kk = k[e]
        lim = excl * atr[e]
        for i in range(len(price)):
            if i_start[i] <= kk and kk < i_death[i] and abs(price[i] - level[e]) <= lim and _mask(kfrom, kto, i, t[kk]) != 0:
                out[e] = True
                break
    return out


def _rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    d = pd.Series(c).diff()
    up = d.clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1.0 / n, adjust=False).mean()
    return (100.0 - 100.0 / (1.0 + up / dn)).to_numpy()


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(x).ewm(span=span, adjust=False).mean().to_numpy()


def add_features(ev: pd.DataFrame, prep: dict, when: np.ndarray) -> pd.DataFrame:
    """
    The state of the market at each event, from bars closed by ``when`` (the open of the minute of a
    touch; the M15 close of a break): trend, RSI, divergence, speed of the approach, session, volatility.
    """
    m1, lv, sym = prep["m1"], prep["levels"], prep["symbol"]
    t, c = m1["t"], m1["c"]
    side = ev["side"].to_numpy()
    b15, h1, h4 = bars_of(m1, t // 900), bars_of(m1, t // 3600), bars_of(m1, t // 14400)
    d1 = bars_of(m1, day_key(t, SYMBOLS[sym]["sunday_with_monday"]))
    e15, e1, e4, ed = (b15["key"] + 1) * 900, (h1["key"] + 1) * 3600, (h4["key"] + 1) * 14400, (d1["key"] + 1) * 86400
    r15 = _rsi(b15["c"])
    ev["rsi_m15"] = asof(e15, r15, when)
    ev["rsi_h1"] = asof(e1, _rsi(h1["c"]), when)
    # the trend of the larger timeframes: sign of the H4 MACD(12,26,9) signal line; D1 close against its 20-bar EMA
    ev["h4"] = asof(e4, np.sign(_ema(_ema(h4["c"], 12) - _ema(h4["c"], 26), 9)), when)
    ev["d1"] = asof(ed, np.sign(d1["c"] - _ema(d1["c"], 20)), when)
    a1 = pd.Series(atr_wilder(h1["h"], h1["l"], h1["c"], prep["p"].atr_len))
    ev["vol"] = asof(e1, (a1 / a1.rolling(480, min_periods=120).median()).to_numpy(), when)
    # how straight the last 120 H1 closes (five days) ran: net move over distance travelled
    c1 = pd.Series(h1["c"])
    ev["er"] = asof(e1, ((c1 - c1.shift(120)).abs() / c1.diff().abs().rolling(120).sum()).to_numpy(), when)
    ev["hour"] = (when // 3600) % 24
    # distance covered towards the level during the last hour, in ATRs
    j = np.searchsorted(t, when - 3600, side="right") - 1
    ref = ev["thr"].to_numpy() if "thr" in ev else ev["entry"].to_numpy()
    sp = np.where(side > 0, c[np.clip(j, 0, None)] - ref, ref - c[np.clip(j, 0, None)]) / ev["atr"].to_numpy()
    if "thr" not in ev:
        sp = -sp                                             # a break: distance covered through the level
    ev["speed"] = np.where((j >= 0) & (when - t[np.clip(j, 0, None)] <= 7260), sp, np.nan)
    # RSI divergence: price is back at an old low (high) while the M15 RSI stands at least 3 points
    # higher (lower) than in the bar that made it. Defined for unbroken swing and day / week extremes.
    rec = ev["rec"].to_numpy()
    then = r15[np.clip(np.searchsorted(e15, lv["t0"][rec], side="right"), 0, len(r15) - 1)]
    natural = ((ev["kind"].to_numpy() == K_LOW) & (side > 0)) | ((ev["kind"].to_numpy() == K_HIGH) & (side < 0))
    ev["div"] = np.where(natural & (ev["flips"].to_numpy() == 0), (side * (ev["rsi_m15"].to_numpy() - then) >= 3.0).astype(float), np.nan)
    return ev


def turning_points(prep: dict, maps: Dict[float, dict], count_from: int, until: int) -> pd.DataFrame:
    """
    What a chart shows in hindsight: of the highs and lows of the H1 and H4 bars, how many lie within
    ``tol`` of a level that was known at that minute, and how many of those became swing highs / lows,
    on the real map (shift 0) and on each control map. ``maps``: shift -> the result of ``scan``.
    """
    m, lv, p = prep["m1"], prep["levels"], prep["p"]
    t = m["t"]
    rows = []
    for name, tf in (("H1", 3600), ("H4", 14400)):
        b = bars_of(m, t // tf)
        hi, lo = _pivots(b["h"], b["l"], p.pivot_w)
        k = np.concatenate([[a + int(np.argmax(m["h"][a:z + 1])) for a, z in zip(b["first"], b["last"])],
                            [a + int(np.argmin(m["l"][a:z + 1])) for a, z in zip(b["first"], b["last"])]]).astype(np.int64)
        px, turn = np.concatenate([b["h"], b["l"]]), np.concatenate([hi, lo])
        ok = (t[k] >= count_from) & (t[k] < until) & (prep["atr"][k] > 0)
        k, px, turn = k[ok], px[ok], turn[ok]
        for shift, res in maps.items():
            near = _near_level(k, px, prep["atr"][k], t, res["price"], lv["i_start"], res["i_death"], lv["kfrom"], lv["kto"], p.tol)
            rows.append({"tf": name, "shift": shift, "n": len(k), "near": int(near.sum()), "turns": int(turn.sum()),
                         "turns_near": int((turn & near).sum())})
    return pd.DataFrame(rows)


def collect(symbol: str, period: str, p: SRParams = SRParams()) -> Dict[str, pd.DataFrame]:
    """
    Every touch and break of ``period`` on the real level map (``shift`` 0) and on the control maps,
    with the state of the market at the event and the outcome of the trades described above.
    Profit columns (``x...``) are in ATRs after the spread; ``usd`` converts to a 0.01 lot.
    """
    read_from, count_from, until = (store.to_ms(x) // 1000 for x in PERIODS[period])
    m1 = store.load_m1(symbol, read_from * 1000, until * 1000)
    prep = prepare(m1, symbol, p)
    m, lv, t = prep["m1"], prep["levels"], prep["m1"]["t"]
    real = scan(prep, snapshots=False)
    parts = {"touch": [], "brk": []}
    maps = {}
    for shift in (0.0,) + SYMBOLS[symbol]["shifts"]:
        res = maps[shift] = real if shift == 0.0 else scan(prep, shift, snapshots=False)
        for name in parts:
            df = res[name].copy()
            df["shift"] = shift
            df["clean"] = True if shift == 0.0 else ~_near_level(
                df["k"].to_numpy(), df["level"].to_numpy(), df["atr"].to_numpy(), t, lv["price"], lv["i_start"],
                real["i_death"], lv["kfrom"], lv["kto"], EXCL)
            parts[name].append(df)
    out = {}
    for name, frames in parts.items():
        ev = pd.concat(frames, ignore_index=True)
        ev = ev[(ev["t"] >= count_from) & (ev["t"] < until - HORIZON_S)].reset_index(drop=True)
        k, a, d = ev["k"].to_numpy(), ev["atr"].to_numpy(), ev["side"].to_numpy().astype(np.int64)
        ev["spread"] = m["spread_mean"][k]
        ev["usd"] = SYMBOLS[symbol]["usd"]
        t_end = t[k] + HORIZON_S
        entry = ev["entry"].to_numpy()
        if name == "touch":
            ev["thr"] = ev["level"] + d * p.zone * a          # the touch price; the entry differs only after a gap
            ev["minute"] = (m["h"][k] - m["l"][k]) / a         # range of the minute of the touch (known only afterwards)
            thr = ev["thr"].to_numpy()
            beyond = ev["level"].to_numpy() - d * STOP * a
            for r, s in GRID:
                code, _, px = _races(t, m["o"], m["h"], m["l"], m["c"], k, 1, d, thr + d * r * a, ev["level"].to_numpy() - d * s * a, t_end)
                ev[f"c{r}_{s}"] = code
                ev[f"x{r}_{s}"] = (d * (px - entry) - ev["spread"].to_numpy()) / a
            code, _, px = _races(t, m["o"], m["h"], m["l"], m["c"], k, 2, -d, beyond, thr + d * TARGET * a, t_end)
            ev["ct"] = code
            ev["xt"] = (-d * (px - entry) - ev["spread"].to_numpy()) / a
            j = _rejections(m["c"], prep["base_end"], k, d, ev["level"].to_numpy(), a, p.buffer, REJECT, REJECT_BARS)
            jj = np.clip(j, 0, None)
            code, _, px = _races(t, m["o"], m["h"], m["l"], m["c"], jj, 0, d, m["c"][jj] + d * BREAKOUT_TARGET * a,
                                 m["c"][jj] - d * BREAKOUT_STOP * a, t[jj] + HORIZON_S)
            ev["cr"] = np.where(j >= 0, code, 0).astype(np.int8)
            ev["xr"] = np.where(j >= 0, (d * (px - m["c"][jj]) - m["spread_mean"][jj]) / a, np.nan)
            for mins in (60, 240):                             # where price stood later, measured from the touch price
                j = np.searchsorted(t, t[k] + mins * 60, side="right") - 1
                ev[f"ret{mins}"] = d * (m["c"][j] - thr) / a
            ev = add_features(ev, prep, t[k])
        else:
            code, _, px = _races(t, m["o"], m["h"], m["l"], m["c"], k, 0, d, entry + d * BREAKOUT_TARGET * a, entry - d * BREAKOUT_STOP * a, t_end)
            ev["c"] = code
            ev["x"] = (d * (px - entry) - ev["spread"].to_numpy()) / a
            ev = add_features(ev, prep, ev["t"].to_numpy())
        when = pd.to_datetime(ev["t"], unit="s")
        ev["half"] = when.dt.year.astype(str) + "H" + ((when.dt.month > 6) + 1).astype(str)
        ev["week"] = (ev["t"] // 86400 + 3) // 7
        ev["tf"] = top_class(ev["own_mask"])
        ev["symbol"], ev["period"] = symbol, period
        out[name] = ev
    out["turns"] = turning_points(prep, maps, count_from, until - HORIZON_S)
    return out


# ───────────────────────────── statistics ─────────────────────────────

SESSIONS = ("Asia 22-07", "London 07-12", "London + New York 12-16", "New York 16-22")


def _session(hour: np.ndarray) -> np.ndarray:
    return np.select([(hour >= 22) | (hour < 7), hour < 12, hour < 16], [0, 1, 2], 3)


def _vol_state(vol: np.ndarray) -> np.ndarray:
    return np.select([vol < 0.8, vol < 1.25], [0, 1], 2)        # H1 ATR against its 20-day median: low, normal, high


def _strata(df: pd.DataFrame, halves: list) -> np.ndarray:
    half = df["half"].map({h: i for i, h in enumerate(halves)}).to_numpy()
    return ((half * 2 + (df["side"].to_numpy() > 0)) * 4 + _session(df["hour"].to_numpy())) * 3 + _vol_state(df["vol"].to_numpy())


def _by_week(week, weeks, strata, n_strata, y):
    """Sums of ``y`` and counts per (week, stratum)."""
    wi = np.searchsorted(weeks, week)
    s = np.zeros((len(weeks), n_strata))
    n = np.zeros((len(weeks), n_strata))
    np.add.at(s, (wi, strata), y)
    np.add.at(n, (wi, strata), 1.0)
    return s, n


def _resample(n_weeks: int, seed: int = 11) -> np.ndarray:
    """Weights of BOOT week-block bootstrap samples (how often each week is drawn); row 0 is the sample itself."""
    rng = np.random.default_rng(seed)
    w = rng.multinomial(n_weeks, np.full(n_weeks, 1.0 / n_weeks), size=BOOT).astype(float)
    return np.vstack([np.ones(n_weeks), w])


def _matched(real: pd.DataFrame, ctrl: pd.DataFrame, yr: np.ndarray, yc: np.ndarray) -> dict:
    """
    Mean of ``yr`` over the real events, mean of ``yc`` over the control events re-weighted to the
    real events' mix of half-year, side, session and volatility state, and their difference.

    The 95 % intervals come from a bootstrap that resamples whole calendar weeks (the real and the
    control events of a week together), so touches of the same swing are not counted as independent.
    """
    halves = sorted(set(real["half"]) | set(ctrl["half"]))
    weeks = np.unique(np.concatenate([real["week"].to_numpy(), ctrl["week"].to_numpy()]))
    W = _resample(len(weeks))
    ns = len(halves) * 24
    sr_, nr = _by_week(real["week"].to_numpy(), weeks, _strata(real, halves), ns, yr)
    sc, nc = _by_week(ctrl["week"].to_numpy(), weeks, _strata(ctrl, halves), ns, yc)
    Sr, Nr, Sc, Nc = W @ sr_, W @ nr, W @ sc, W @ nc                    # [sample, stratum]; row 0 is the data itself
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = Sr.sum(1) / Nr.sum(1)
        pooled = Sc.sum(1) / Nc.sum(1)
        mc = np.where(Nc > 0, Sc / Nc, pooled[:, None])                  # a stratum without control events takes the pooled mean
        matched = (Nr * mc).sum(1) / Nr.sum(1)
    diff = mean - matched
    out = {"mean": mean[0], "ctrl": matched[0], "diff": diff[0]}
    out["lo"], out["hi"] = np.nanpercentile(mean[1:], [2.5, 97.5])
    if len(ctrl):
        out["diff_lo"], out["diff_hi"] = np.nanpercentile(diff[1:], [2.5, 97.5])
    return out


def compare(real: pd.DataFrame, ctrl: pd.DataFrame, code: str, x: str) -> dict:
    """
    One row of a table: how often the trade reached its target on the real levels and on the matched
    control (trades still open after 24 h left out), and the profit per trade after the spread in
    ATRs and in USD per 0.01 lot (every trade counted), each with its 95 % interval.
    """
    out = {"n": len(real), "n_ctrl": len(ctrl)}
    if len(real) == 0:
        return out
    dr, dc = real[real[code] != 0], ctrl[ctrl[code] != 0]
    if len(dr):
        m = _matched(dr, dc, (dr[code] == 1).to_numpy(float), (dc[code] == 1).to_numpy(float))
        out.update(rate=m["mean"], ctrl=m["ctrl"], diff=m["diff"], diff_lo=m.get("diff_lo", np.nan), diff_hi=m.get("diff_hi", np.nan))
    m = _matched(real, ctrl, real[x].to_numpy(), ctrl[x].to_numpy())
    out.update(x=m["mean"], x_lo=m["lo"], x_hi=m["hi"], x_ctrl=m["ctrl"], x_diff=m["diff"],
               x_diff_lo=m.get("diff_lo", np.nan), x_diff_hi=m.get("diff_hi", np.nan))
    m = _matched(real, ctrl, (real[x] * real["atr"] * real["usd"]).to_numpy(), (ctrl[x] * ctrl["atr"] * ctrl["usd"]).to_numpy())
    out.update(usd=m["mean"], usd_lo=m["lo"], usd_hi=m["hi"])
    out["by_half"] = " / ".join(f"{real.loc[real['half'] == hf, x].mean():+.3f}" for hf in sorted(set(real["half"])))
    out["half_n"] = " / ".join(str(int((real["half"] == hf).sum())) for hf in sorted(set(real["half"])))
    return out


def _bit(df, *bits):
    """Events whose zone holds a level of one of these classes (the level touched first need not be the one)."""
    m = df["zone_mask"].to_numpy()
    hit = np.zeros(len(df), bool)
    for b in bits:
        hit |= ((m >> b) & 1).astype(bool)
    return hit


def _fav_rsi(df, col):
    """RSI seen from the trade: low = the approach has stretched it against the level (oversold at a support)."""
    r = df[col].to_numpy()
    return np.where(df["side"].to_numpy() > 0, r, 100.0 - r)


def kind_rows(df):
    """(label, selector) for each kind of level in the zone; rows overlap where a zone holds several kinds."""
    return [
        ("all levels", np.ones(len(df), bool)),
        ("H1 swing (not H4)", _bit(df, C_H1) & ~_bit(df, C_H4)),
        ("H4 swing (not D1)", _bit(df, C_H4) & ~_bit(df, C_D1)),
        ("D1 swing", _bit(df, C_D1)),
        ("previous-day high / low", _bit(df, C_PDHL)),
        ("previous-day close", _bit(df, C_PDC)),
        ("previous-week high / low", _bit(df, C_PWHL)),
        ("previous-week close", _bit(df, C_PWC)),
        ("round number, minor", _bit(df, C_R1) & ~_bit(df, C_R2)),
        ("round number, major", _bit(df, C_R2)),
        ("any H4 / D1 swing or day / week high / low", _bit(df, C_H4, C_D1, C_PDHL, C_PWHL)),
    ]


def factor_rows(df):
    """(group, label, selector): what might make a level work."""
    side, age = df["side"].to_numpy(), df["age_s"].to_numpy() / 86400.0
    h4, d1 = side * df["h4"].to_numpy(), side * df["d1"].to_numpy()
    swing = df["kind"].to_numpy() != K_ROUND
    zt, nz, st = df["zone_touches"].to_numpy(), df["n_zone"].to_numpy(), df["strength"].to_numpy()
    r15, r1h, sp = _fav_rsi(df, "rsi_m15"), _fav_rsi(df, "rsi_h1"), df["speed"].to_numpy()
    ses, vol, div, fl = _session(df["hour"].to_numpy()), _vol_state(df["vol"].to_numpy()), df["div"].to_numpy(), df["flips"].to_numpy()
    rows = [("side", "support (buy)", side > 0), ("side", "resistance (sell)", side < 0),
            ("levels in the zone", "1", nz == 1), ("levels in the zone", "2", nz == 2), ("levels in the zone", "3 or more", nz >= 3),
            ("zone strength", "1-2", st <= 2), ("zone strength", "3-4", (st > 2) & (st <= 4)), ("zone strength", "5-6", (st > 4) & (st <= 6)),
            ("zone strength", "7 or more", st > 6),
            ("earlier touches", "none (first touch)", zt == 0), ("earlier touches", "1", zt == 1), ("earlier touches", "2", zt == 2),
            ("earlier touches", "3 or more", zt >= 3),
            ("role (not round numbers)", "never broken", swing & (fl == 0)), ("role (not round numbers)", "broken once, retested from the other side", swing & (fl == 1)),
            ("age (not round numbers)", "under 1 day", swing & (age < 1)), ("age (not round numbers)", "1-5 days", swing & (age >= 1) & (age < 5)),
            ("age (not round numbers)", "5-20 days", swing & (age >= 5) & (age < 20)), ("age (not round numbers)", "over 20 days", swing & (age >= 20)),
            ("H4 trend (MACD signal line)", "trade with it", h4 > 0), ("H4 trend (MACD signal line)", "trade against it", h4 < 0),
            ("D1 trend (close vs EMA20)", "trade with it", d1 > 0), ("D1 trend (close vs EMA20)", "trade against it", d1 < 0),
            ("H4 and D1 trend", "with both", (h4 > 0) & (d1 > 0)), ("H4 and D1 trend", "against both", (h4 < 0) & (d1 < 0)),
            ("M15 RSI at the touch", "stretched (under 30 at support, over 70 at resistance)", r15 < 30),
            ("M15 RSI at the touch", "30-50 (50-70)", (r15 >= 30) & (r15 < 50)), ("M15 RSI at the touch", "not stretched", r15 >= 50),
            ("H1 RSI at the touch", "stretched (under 30 at support, over 70 at resistance)", r1h < 30),
            ("H1 RSI at the touch", "30-50 (50-70)", (r1h >= 30) & (r1h < 50)), ("H1 RSI at the touch", "not stretched", r1h >= 50),
            ("RSI divergence (unbroken extremes)", "yes", div == 1), ("RSI divergence (unbroken extremes)", "no", div == 0),
            ("approach in the last hour", "under 0.5 ATR", sp < 0.5), ("approach in the last hour", "0.5-1.5 ATR", (sp >= 0.5) & (sp < 1.5)),
            ("approach in the last hour", "over 1.5 ATR", sp >= 1.5)]
    er = df["er"].to_numpy()
    rows += [("last five days (efficiency ratio of H1 closes)", "ranging (under 0.06)", er < RANGING),
             ("last five days (efficiency ratio of H1 closes)", "in between", (er >= RANGING) & (er < TRENDING)),
             ("last five days (efficiency ratio of H1 closes)", "trending (over 0.125)", er >= TRENDING)]
    rows += [("session (UTC)", SESSIONS[i], ses == i) for i in range(4)]
    rows += [("volatility (H1 ATR vs its 20-day median)", lab, vol == i) for i, lab in enumerate(("low", "normal", "high"))]
    return rows


def tables(ev: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Every table of the study for one symbol and period, as numbers (``render`` formats them)."""
    code, x = f"c{TARGET}_{STOP}", f"x{TARGET}_{STOP}"
    t = ev["touch"]
    real, ctrl = t[t["shift"] == 0.0].reset_index(drop=True), t[(t["shift"] != 0.0) & t["clean"]].reset_index(drop=True)
    b = ev["brk"]
    breal, bctrl = b[b["shift"] == 0.0].reset_index(drop=True), b[(b["shift"] != 0.0) & b["clean"]].reset_index(drop=True)
    out = {}
    out["kinds"] = pd.DataFrame([{"row": lab, **compare(real[m], ctrl[mc], code, x)}
                                 for (lab, m), (_, mc) in zip(kind_rows(real), kind_rows(ctrl))])
    out["halves"] = pd.DataFrame([{"row": hf, **compare(real[real["half"] == hf], ctrl[ctrl["half"] == hf], code, x)}
                                  for hf in sorted(set(real["half"]))])
    out["grid"] = pd.DataFrame([{"row": f"target {r} / stop {s}", "walk": (SRParams().zone + s) / (r + SRParams().zone + s),
                                 **compare(real, ctrl, f"c{r}_{s}", f"x{r}_{s}")} for r, s in GRID])
    out["factors"] = pd.DataFrame([{"group": g, "row": lab, **compare(real[m], ctrl[mc], code, x)}
                                   for (g, lab, m), (_, _, mc) in zip(factor_rows(real), factor_rows(ctrl))])
    # how much the answer depends on the control: each control map alone, and without the 0.5-ATR exclusion
    every = t[t["shift"] != 0.0].reset_index(drop=True)
    rows = [("control as used: four maps, events near a real level left out", ctrl)]
    rows += [(f"only the map moved by {sh * 100:+.1f} %", ctrl[ctrl["shift"] == sh]) for sh in sorted(set(ctrl["shift"]))]
    rows.append(("every control event, also those near a real level", every))
    out["controls"] = pd.DataFrame([{"row": lab, **compare(real, c, code, x)} for lab, c in rows])
    # ... and on news minutes: touches made in a quiet minute only, levels and control alike. A check, not a
    # rule: the range of the minute is known only when it is over.
    quiet = lambda d: d[d["minute"] <= 0.5]
    out["controls"] = pd.concat([out["controls"], pd.DataFrame([
        {"row": "touches in a quiet minute only (range up to 0.5 ATR), control as used", **compare(quiet(real), quiet(ctrl), code, x)},
        {"row": "touches in a quiet minute only, every control event", **compare(quiet(real), quiet(every), code, x)}])], ignore_index=True)
    out["controls"].attrs["wide"] = ((real["minute"] > 0.5).mean(), (ctrl["minute"] > 0.5).mean(), (every["minute"] > 0.5).mean())
    # the mirror image at the same touches: with the approach, through the level
    out["through_kinds"] = pd.DataFrame([{"row": lab, **compare(real[m], ctrl[mc], "ct", "xt")}
                                         for (lab, m), (_, mc) in zip(kind_rows(real), kind_rows(ctrl))])
    out["through_halves"] = pd.DataFrame([{"row": hf, **compare(real[real["half"] == hf], ctrl[ctrl["half"] == hf], "ct", "xt")}
                                          for hf in sorted(set(real["half"]))])
    out["through_factors"] = pd.DataFrame([{"group": g, "row": lab, **compare(real[m], ctrl[mc], "ct", "xt")}
                                           for (g, lab, m), (_, _, mc) in zip(factor_rows(real), factor_rows(ctrl))])
    # the bounce trade of someone who waits for the level to hold first
    jr, jc = real[real["xr"].notna()], ctrl[ctrl["xr"].notna()]
    rows = [("all rejections", np.ones(len(jr), bool), np.ones(len(jc), bool))]
    rows += [(lab, m, mc) for (lab, m), (_, mc) in zip(kind_rows(jr)[1:], kind_rows(jc)[1:])]
    for lab, f in (("first touch of the zone", lambda d: d["zone_touches"] == 0), ("zone touched before", lambda d: d["zone_touches"] > 0),
                   ("with the H4 trend", lambda d: d["side"] * d["h4"] > 0), ("against the H4 trend", lambda d: d["side"] * d["h4"] < 0),
                   ("with the D1 trend", lambda d: d["side"] * d["d1"] > 0), ("against the D1 trend", lambda d: d["side"] * d["d1"] < 0),
                   ("last five days ranging", lambda d: d["er"] < RANGING), ("last five days trending", lambda d: d["er"] >= TRENDING)):
        rows.append((lab, f(jr).to_numpy(), f(jc).to_numpy()))
    out["rejection"] = pd.DataFrame([{"row": lab, **compare(jr[m], jc[mc], "cr", "xr")} for lab, m, mc in rows])
    out["rejection"].attrs["share"] = (len(jr) / max(len(real), 1), len(jc) / max(len(ctrl), 1))
    # the breakout trade: with the break, after the close that made it
    rows = [("all breaks", np.ones(len(breal), bool), np.ones(len(bctrl), bool))]
    rows += [(lab, m, mc) for (lab, m), (_, mc) in zip(kind_rows(breal)[1:], kind_rows(bctrl)[1:])]
    for lab, f in (("first break of the level", lambda d: (d["flips"] == 0) & (d["kind"] != K_ROUND)),
                   ("second break (it had changed role)", lambda d: (d["flips"] == 1) & (d["kind"] != K_ROUND)),
                   ("break with the H4 trend", lambda d: d["side"] * d["h4"] > 0), ("break against the H4 trend", lambda d: d["side"] * d["h4"] < 0),
                   ("break with the D1 trend", lambda d: d["side"] * d["d1"] > 0), ("break against the D1 trend", lambda d: d["side"] * d["d1"] < 0),
                   ("level had been touched before", lambda d: d["touches"] > 0), ("level never touched", lambda d: d["touches"] == 0)):
        rows.append((lab, f(breal).to_numpy(), f(bctrl).to_numpy()))
    out["breakout"] = pd.DataFrame([{"row": lab, **compare(breal[m], bctrl[mc], "c", "x")} for lab, m, mc in rows])
    # the retest: a touch of a level that has been broken once, from its new side
    sel = lambda d: (d["flips"] == 1) & (d["kind"] != K_ROUND)
    rr, rc = real[sel(real)], ctrl[sel(ctrl)]
    rows = [("all retests", np.ones(len(rr), bool), np.ones(len(rc), bool))]
    rows += [(lab, m, mc) for (lab, m), (_, mc) in zip(kind_rows(rr)[1:8], kind_rows(rc)[1:8])]
    hrs = lambda d: d["since_flip_s"] / 3600.0
    for lab, f in (("within 4 h of the break", lambda d: hrs(d) < 4), ("4-24 h after the break", lambda d: (hrs(d) >= 4) & (hrs(d) < 24)),
                   ("more than a day after the break", lambda d: hrs(d) >= 24),
                   ("first touch since the break", lambda d: d["since_touch_s"].isna() | (d["since_touch_s"] > d["since_flip_s"])),
                   ("later touch since the break", lambda d: d["since_touch_s"] <= d["since_flip_s"]),
                   ("with the H4 trend", lambda d: d["side"] * d["h4"] > 0), ("against the H4 trend", lambda d: d["side"] * d["h4"] < 0)):
        rows.append((lab, f(rr).to_numpy(), f(rc).to_numpy()))
    out["retest"] = pd.DataFrame([{"row": lab, **compare(rr[m], rc[mc], code, x)} for lab, m, mc in rows])
    # where price stood one and four hours after the touch: ATRs from the touch price, towards the bounce
    out["later"] = pd.DataFrame([{"row": f"{mins // 60} h after the touch", "n": len(real), "n_ctrl": len(ctrl),
                                  **_matched(real, ctrl, real[f"ret{mins}"].to_numpy(), ctrl[f"ret{mins}"].to_numpy())} for mins in (60, 240)])
    # what the chart shows in hindsight: bar extremes at a level, and how many of them became turning points
    rows = []
    for tf, g in ev["turns"].groupby("tf", sort=False):
        for lab, d in (("real levels", g[g["shift"] == 0.0]), ("control maps", g[g["shift"] != 0.0])):
            n, near, turns, tn = (float(d[c].sum()) for c in ("n", "near", "turns", "turns_near"))
            each = (d["turns_near"] / d["near"]).to_numpy()
            rows.append({"group": f"{tf} bars", "row": lab, "bars": n / len(d), "share_near": near / n, "turns": turns / len(d),
                         "turns_near": tn / turns, "turn_if_near": tn / near, "turn_if_not": (turns - tn) / (n - near),
                         "lo": each.min(), "hi": each.max()})
    out["turns"] = pd.DataFrame(rows)
    # one line per trade
    pick = lambda name, lab, as_: {**out[name][out[name]["row"] == lab].iloc[0].to_dict(), "row": as_, "group": ""}
    out["summary"] = pd.DataFrame([
        pick("kinds", "all levels", "bounce: buy a support, sell a resistance at the touch"),
        pick("kinds", "any H4 / D1 swing or day / week high / low", "bounce, only H4 / D1 swings and day / week highs and lows"),
        pick("factors", "with both", "bounce, only with the H4 and the D1 trend"),
        pick("rejection", "all rejections", "bounce after the level has held for an M15 close (rejection)"),
        pick("retest", "all retests", "bounce at a broken level retested from its other side"),
        pick("through_kinds", "all levels", "through: with the approach at the touch"),
        pick("breakout", "all breaks", "breakout: with the break after an M15 close beyond"),
    ]).drop(columns="group")
    return out


# ───────────────────────────── output ─────────────────────────────

def _quarters(period: str) -> float:
    _, count_from, until = (store.to_ms(x) // 1000 for x in PERIODS[period])
    return (until - HORIZON_S - count_from) / (365.25 * 86400 / 4)


def _cells(r: pd.Series, period: str) -> list:
    """The cells of one period in a table row; an interval that excludes zero is set in bold."""
    n = int(r.get("n", 0) or 0)
    if n == 0 or pd.isna(r.get("x")):
        return [str(n), "", "", "", "", ""]

    def ci(v, lo, hi, scale, digits):
        if pd.isna(lo):
            return f"{v * scale:+.{digits}f}"
        txt = f"{v * scale:+.{digits}f} [{lo * scale:+.{digits}f}, {hi * scale:+.{digits}f}]"
        return f"**{txt}**" if lo > 0 or hi < 0 else txt

    q = _quarters(period)
    rate = "" if pd.isna(r.get("rate")) else f"{r['rate'] * 100:.1f}% vs {r['ctrl'] * 100:.1f}%"
    diff = "" if pd.isna(r.get("diff")) else ci(r["diff"], r.get("diff_lo"), r.get("diff_hi"), 100, 1)
    return [f"{n} ({n / q:.0f})", rate, diff, ci(r["x"], r["x_lo"], r["x_hi"], 1, 3), f"{r['usd']:+.2f} ({r['usd'] * n / q:+.0f})",
            r.get("by_half", "")]


HEAD = ["trades (per quarter)", "target first: levels vs control", "difference, points (95 %)", "ATR per trade (95 %)",
        "USD per trade (per quarter)", "ATR per trade by half-year"]


def render(tabs: Dict[str, Dict[str, pd.DataFrame]], name: str) -> str:
    """One table as markdown, the periods side by side. ``tabs``: period -> tables()."""
    periods = [p for p in PERIODS if p in tabs]
    base = tabs[periods[0]][name]
    keys = [c for c in ("group", "row", "walk") if c in base.columns]
    names = {"group": "", "row": "", "walk": "random walk"}
    if "mean" in base.columns:          # the table of later prices
        cols = ("events", "real levels, ATR (95 %)", "control", "difference (95 %)")
    elif "share_near" in base.columns:  # the hindsight table
        cols = ("bar highs and lows", "of them at a level", "turning points", "of them at a level",
                "became a turning point: at a level", "elsewhere")
    else:
        cols = HEAD
    head = [names[k] for k in keys] + [f"{p}: {h}" for p in periods for h in cols]
    lines = []
    for i in range(len(base)):
        cells = [f"{base.iloc[i][k] * 100:.1f}%" if k == "walk" else str(base.iloc[i][k]) for k in keys]
        for p in periods:
            t = tabs[p][name]
            if i >= len(t):
                cells += [""] * len(cols)
            elif "share_near" in base.columns:
                r = t.iloc[i]
                spread = "" if r["lo"] == r["hi"] else f" ({r['lo'] * 100:.1f} to {r['hi'] * 100:.1f})"
                cells += [f"{r['bars']:.0f}", f"{r['share_near'] * 100:.1f}%", f"{r['turns']:.0f}", f"{r['turns_near'] * 100:.1f}%",
                          f"{r['turn_if_near'] * 100:.1f}%{spread}", f"{r['turn_if_not'] * 100:.1f}%"]
            elif "mean" in base.columns:
                r = t.iloc[i]
                d = f"{r['diff']:+.3f} [{r['diff_lo']:+.3f}, {r['diff_hi']:+.3f}]"
                cells += [str(int(r["n"])), f"{r['mean']:+.3f} [{r['lo']:+.3f}, {r['hi']:+.3f}]", f"{r['ctrl']:+.3f}",
                          f"**{d}**" if r["diff_lo"] > 0 or r["diff_hi"] < 0 else d]
            else:
                cells += _cells(t.iloc[i], p)
        lines.append(cells)
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(c) + " |" for c in lines])


TITLES = (("turns", "In hindsight: turning points and levels"), ("summary", "Every trade, all levels"),
          ("kinds", "Bounce trade by kind of level"), ("halves", "Bounce trade, all levels, by half-year"),
          ("grid", "Bounce trade, all levels, other targets and stops"), ("factors", "Bounce trade: what might make a level work"),
          ("rejection", "Rejection trade: the bounce after the level has held"),
          ("retest", "Retest: the bounce trade at a level that was broken once"),
          ("through_kinds", "Through trade by kind of level"), ("through_halves", "Through trade, all levels, by half-year"),
          ("through_factors", "Through trade by the state of the level and of the market"),
          ("breakout", "Breakout trade"), ("later", "Where price stood after a touch"),
          ("controls", "Bounce trade, all levels, against other choices of control"),
          ("variants", "Bounce trade under other definitions of a level"))


RULE_TABLES = ("kinds", "factors", "rejection", "retest", "through_kinds", "through_factors", "breakout")


def rule_rows(tabs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Every row of the trade tables of one symbol and period against the rule for a candidate: at least 100
    trades, profit per trade positive in every half-year with its 95 % interval above zero (``profit``),
    and a target-first rate above the control's with that interval above zero (``control``).
    ``above`` / ``below``: the profit interval lies wholly above / below zero.
    """
    rows = []
    for name in RULE_TABLES:
        for r in tabs[name].to_dict("records"):
            if not r["n"] or pd.isna(r.get("x")):
                continue
            halves = [float(v) for v in str(r["by_half"]).split(" / ")]
            rows.append({"table": name, "group": r.get("group", ""), "row": r["row"], "n": r["n"], "x": r["x"],
                         "above": bool(r["x_lo"] > 0), "below": bool(r["x_hi"] < 0),
                         "profit": bool(r["n"] >= 100 and r["x_lo"] > 0 and min(halves) > 0),
                         "control": bool(pd.notna(r.get("diff_lo")) and r["diff_lo"] > 0)})
    return pd.DataFrame(rows)


def tally(tabs: Dict[str, Dict[str, pd.DataFrame]]) -> str:
    """The count of ``rule_rows`` per period, and of the rows whose interval is on one side of zero in every period."""
    per = {p: rule_rows(t).set_index(["table", "group", "row"]) for p, t in tabs.items()}
    head = ["", "rows", "profit interval above zero", "below zero", "profit rule met", "profit and control rule met"]
    lines = [[p, str(len(d)), str(int(d["above"].sum())), str(int(d["below"].sum())), str(int(d["profit"].sum())),
              str(int((d["profit"] & d["control"]).sum()))] for p, d in per.items()]
    if len(per) > 1:
        both = pd.concat(per, axis=1, join="inner")
        every = lambda col: both.xs(col, axis=1, level=1).all(axis=1)
        lines.append(["in every period", str(len(both)), str(int(every("above").sum())), str(int(every("below").sum())),
                      str(int(every("profit").sum())), str(int((every("profit") & every("control")).sum()))])
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(c) + " |" for c in lines])


def load_tables(out_dir: Path, symbol: str) -> Dict[str, Dict[str, pd.DataFrame]]:
    """period -> tables, for the periods whose study has been run into ``out_dir``."""
    tabs = {}
    for p in PERIODS:
        f = out_dir / f"sr_{p}_{symbol}.pkl"
        if f.exists():
            tabs[p] = dict(pd.read_pickle(f)["tables"])
            v = out_dir / f"sr_variants_{p}_{symbol}.pkl"
            if v.exists():
                tabs[p]["variants"] = pd.read_pickle(v)
    return tabs


def report(out_dir: Path, symbols=tuple(SYMBOLS)) -> str:
    """All tables of the stored periods as markdown, DEV and CONFIRM side by side."""
    text = []
    for sym in symbols:
        tabs = load_tables(out_dir, sym)
        for name, title in TITLES:
            have = {p: t for p, t in tabs.items() if name in t}
            if not have:
                continue
            if name.endswith("halves"):       # the half-years differ between the periods: one table each
                for p in have:
                    text.append(f"#### {sym}: {title} ({p})\n\n" + render({p: have[p]}, name))
            else:
                text.append(f"#### {sym}: {title}\n\n" + render(have, name))
        if tabs:
            text.append(f"#### {sym}: Rows of the trade tables against the candidate rule\n\n" + tally(tabs))
    return "\n\n".join(text) + "\n"


def run_study(period: str, out_dir: Path, symbols=tuple(SYMBOLS), p: SRParams = SRParams()) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        t0 = time.time()
        ev = collect(sym, period, p)
        tabs = tables(ev)
        pd.to_pickle({"events": ev, "tables": tabs, "params": asdict(p)}, out_dir / f"sr_{period}_{sym}.pkl")
        real = ev["touch"][ev["touch"]["shift"] == 0.0]
        print(f"{sym} {period}: {len(real)} touches and {int((ev['brk']['shift'] == 0.0).sum())} breaks on the real map, "
              f"{int(((ev['touch']['shift'] != 0.0) & ev['touch']['clean']).sum())} control touches, {time.time() - t0:.0f}s", file=sys.stderr)


def run_variants(period: str, out_dir: Path, symbols=tuple(SYMBOLS)) -> None:
    """The bounce trade under other definitions of a level: how much the answer depends on them."""
    code, x = f"c{TARGET}_{STOP}", f"x{TARGET}_{STOP}"
    variants = [("as defined (swing: 3 bars each side; touch zone 0.10 ATR)", SRParams()), ("swing: 2 bars each side", SRParams(pivot_w=2)),
                ("swing: 5 bars each side", SRParams(pivot_w=5)), ("touch zone 0.05 ATR", SRParams(zone=0.05)), ("touch zone 0.20 ATR", SRParams(zone=0.20))]
    out_dir.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        rows = []
        for lab, p in variants:
            t = collect(sym, period, p)["touch"]
            real, ctrl = t[t["shift"] == 0.0], t[(t["shift"] != 0.0) & t["clean"]]
            htf = lambda d: _bit(d, C_H4, C_D1, C_PDHL, C_PWHL)
            rows.append({"group": lab, "row": "all levels", **compare(real, ctrl, code, x)})
            rows.append({"group": lab, "row": "H4 / D1 swings and day / week highs and lows", **compare(real[htf(real)], ctrl[htf(ctrl)], code, x)})
        pd.to_pickle(pd.DataFrame(rows), out_dir / f"sr_variants_{period}_{sym}.pkl")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    default_out = Path(os.environ.get("ALCADEIAS_SR_OUT", "sr_study_out"))
    if cmd == "levels" and len(args) >= 4:
        m1 = store.load_m1(args[1], store.to_ms(args[2]), store.to_ms(args[3]))
        lv = nearest_levels(m1, args[1])
        lv.insert(0, "time", pd.to_datetime(lv["t_close"], unit="s"))
        cols = ["time", "close", "atr", "sup_price", "sup_dist", "sup_tf", "sup_touches", "sup_n_zone", "sup_strength",
                "res_price", "res_dist", "res_tf", "res_touches", "res_n_zone", "res_strength"]
        pd.set_option("display.width", 250)
        print(lv[cols].tail(int(args[4]) if len(args) > 4 else 24).round(2).to_string(index=False))
    elif cmd == "study" and len(args) >= 2 and args[1] in PERIODS:
        out = Path(args[2]) if len(args) > 2 else default_out
        run_study(args[1], out)
        print(report(out))
    elif cmd == "variants" and len(args) >= 2 and args[1] in PERIODS:
        out = Path(args[2]) if len(args) > 2 else default_out
        run_variants(args[1], out)
        print(report(out))
    elif cmd == "report":
        print(report(Path(args[1]) if len(args) > 1 else default_out))
    else:
        raise SystemExit(__doc__)
