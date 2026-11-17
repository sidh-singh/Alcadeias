"""
Silver (XAGUSDm, Exness) study: the 40 candidates / 144 variants of ``backtest_results/silver/PREREG_SILVER.md``.

Library only: loading with the split cut (§1), the cost models (§2), the per-unit stream and its metrics (§3), the
candidate builders (§4), the tick-engine basket designs, the selection statistics (DSR, SPA) and the sizing accounts (§6).
The driver of the develop step is ``silver_develop.py``. Existing modules are imported and called, never edited.

One unit = 0.01 lot = 50 oz: a 1.00 move is $50 (K). Prices are bids; buys pay the ask (bid + spread).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..config import REPO_ROOT
from ..data import store
from . import multisymbol as MS          # noqa: F401  (registers XAGUSDm in the engine's symbol table)
from . import external as X
from . import balke as B
from . import final10 as F

SYM, GOLD = "XAGUSDm", "XAUUSDm"
CONTRACT, DIGITS = 5000.0, 3
K = 50.0                       # USD per 1.00 of price per unit (0.01 lot)
TICK = 0.001
WARM = "2017-11-01"
DEV = ("2018-11-01", "2023-01-01")
VAL = ("2023-01-01", "2024-07-01")
HOLDOUT = ("2024-07-01", "2026-11-13")
DEVVAL = (DEV[0], VAL[1])
HALVES = (("2018-11-01", "2021-01-01"), ("2021-01-01", "2023-01-01"))
COVID = ("2020-03-01", "2020-05-01")
N_TRIALS = 144
OUT = REPO_ROOT / "backtest_results" / "silver"
NY, LDN = "America/New_York", "Europe/London"
DAY = 86400
LIVE_S = 180.0
BREAK_S = 1800                 # a silence this long is a break (daily or weekend)
ZONE_S = 300                   # §4.1: 5 minutes after a reopen / before a break
COSTS = ("x1", "x15", "pct", "gross")
PCT_SPREAD = 0.0021


def s_of(x) -> int:
    return int(store.to_ms(x) // 1000)


# ───────────────────────────── §1 loading with the cut ─────────────────────────────

class CutError(AssertionError):
    pass


def guard(t: np.ndarray, cut: str, what: str = "") -> None:
    """§1.2: no timestamp at or after the step's allowed end may be present."""
    c = s_of(cut)
    if len(t) and int(np.max(t)) >= c:
        raise CutError(f"{what}: data at or after the cut {cut} ({pd.Timestamp(int(np.max(t)), unit='s')})")


def hold_out_allowed() -> bool:
    """The hold-out may be read only once FINALISTS.md is frozen (its sha256 matches) and names at least one finalist."""
    import hashlib
    import re
    f, h = OUT / "FINALISTS.md", OUT / "FINALISTS.md.sha256"
    if not (f.exists() and h.exists()):
        return False
    if hashlib.sha256(f.read_bytes()).hexdigest() != h.read_text().split()[0]:
        return False
    m = re.search(r"Finalists: (\d+)", f.read_text())
    return bool(m and int(m.group(1)) > 0)


def check_cut(cut: str) -> None:
    if s_of(cut) > s_of(VAL[1]) and not hold_out_allowed():
        raise CutError(f"cut {cut} reaches the hold-out before FINALISTS.md.sha256 exists")


def load_market(sym: str, cut: str) -> X.Market:
    check_cut(cut)
    m1 = store.load_m1(sym, WARM, cut)
    guard(m1["t"], cut, f"{sym} M1")
    if sym == GOLD:
        return X.Market(sym, m1)
    return B.SpecMarket(sym, m1, CONTRACT, DIGITS)


def month_floor(t: np.ndarray, sp: np.ndarray) -> np.ndarray:
    """0.5 x the calendar month's median spread, per element (§2.1)."""
    mon = pd.to_datetime(t, unit="s").to_period("M").asi8 if len(t) else np.zeros(0, np.int64)
    s = pd.Series(sp)
    med = s.groupby(mon).transform("median").to_numpy()
    return 0.5 * med


def with_spread(m: X.Market, sp: np.ndarray) -> X.Market:
    """The same market (shared bars and clocks) with another spread series."""
    mm = object.__new__(type(m))
    mm.__dict__.update(m.__dict__)
    mm.sp = np.ascontiguousarray(sp, np.float64)
    return mm


def cost_markets(m: X.Market) -> Dict[str, X.Market]:
    """§2: x1 (floored spread), x15 (x 1.5), pct (0.21 % of price), gross (no spread)."""
    spf = np.maximum(m.sp, month_floor(m.t, m.sp))
    return {"x1": with_spread(m, spf), "x15": with_spread(m, 1.5 * spf),
            "pct": with_spread(m, PCT_SPREAD * m.c), "gross": with_spread(m, np.zeros(len(m)))}


# ───────────────────────────── sessions: reopens and breaks ─────────────────────────────

@dataclass
class Zones:
    reopen5: np.ndarray        # bar opens within 5 min of a reopen (first bar after a >= 30 min silence)
    blocked: np.ndarray        # reopen5 | within 5 min before a break | (a decision landing here is inside a break)
    reopen_t: np.ndarray       # times of the reopen bars


def zones(m: X.Market) -> Zones:
    t = m.t
    gap = np.diff(t) >= BREAK_S
    start = np.concatenate([[0], np.flatnonzero(gap) + 1])        # session first bars
    end = np.append(start[1:] - 1, len(t) - 1)                  # session last bars
    sid = np.repeat(np.arange(len(start)), np.diff(np.append(start, len(t))))
    since = t - t[start][sid]
    until = (t[end][sid] + 60) - t
    re5 = since < ZONE_S
    blk = re5 | (until <= ZONE_S)
    return Zones(re5, blk, t[start])


def block_entries(m: X.Market, plan: X.PathPlan, z: Zones) -> X.PathPlan:
    """§4.1 for sub-daily rules: entries (and order placements) executed in a blocked bar are dropped; stop orders cannot
    fill in a blocked bar. Exits are kept. A decision inside a break executes at the reopen bar, which is blocked."""
    dx = np.minimum(plan.dx, len(m) - 1)
    bad = z.blocked[dx]
    want = np.where(bad, 0, plan.want)
    f = dict(plan.f)
    if plan.orders:
        f["bstop"] = np.where(bad, np.nan, f["bstop"])
        f["sstop"] = np.where(bad, np.nan, f["sstop"])
        ml = ~z.blocked if plan.m_l is None else plan.m_l & ~z.blocked
        ms = ~z.blocked if plan.m_s is None else plan.m_s & ~z.blocked
        return plan.copy(want=want, f=f, m_l=np.ascontiguousarray(ml), m_s=np.ascontiguousarray(ms))
    return plan.copy(want=want, f=f)


# ───────────────────────────── §2.2 the costed path ─────────────────────────────

@njit(cache=True)
def _costed(sp, reopen5, d, eix, xix, why, leg0, nleg, leix, lepx, xpx, stop_entry, charge):
    """Adverse shift of each fill by one extra spread where §2.2 charges it. Returns new leg prices, exit prices and the
    number of charged fills (entries, exits)."""
    le = lepx.copy()
    xe = xpx.copy()
    n_in = 0
    n_out = 0
    if not charge:
        return le, xe, n_in, n_out
    for i in range(d.shape[0]):
        dd = d[i]
        for q in range(leg0[i], leg0[i] + nleg[i]):
            e = leix[q]
            if stop_entry or q > leg0[i] or reopen5[e]:
                le[q] = le[q] + dd * sp[e]
                n_in += 1
        x = xix[i]
        if why[i] != 4 and (why[i] == 2 or why[i] == 5 or reopen5[x]):
            xe[i] = xe[i] - dd * sp[x] * 1.0
            n_out += nleg[i]
    return le, xe, n_in, n_out


def costed(m: X.Market, p: X.Path_, z: Zones, stop_entry: bool, charge: bool):
    le, xe, n_in, n_out = _costed(m.sp, z.reopen5, p.dir, p.eix, p.xix, p.why, p.leg0, p.nleg, p.leix, p.lepx, p.xpx,
                                  bool(stop_entry), bool(charge))
    return replace(p, lepx=le, xpx=xe), int(n_in), int(n_out)


def merge_paths(parts: Sequence[X.Path_]) -> X.Path_:
    """Several independent lanes (C09's two unit lanes, C19's every-signal lanes) as one path."""
    parts = [p for p in parts if len(p)]
    if not parts:
        z = np.zeros(0, np.int64)
        zf = np.zeros(0)
        return X.Path_(z, z, zf, z, zf, z, zf, zf, z, z, z, zf)
    cat = {f: [] for f in X.Path_.__dataclass_fields__}
    off = 0
    for p in parts:
        for f in cat:
            v = getattr(p, f)
            cat[f].append(v + off if f == "leg0" else v)
        off += len(p.leix)
    cat = {f: np.concatenate(v) for f, v in cat.items()}
    o = np.argsort(cat["eix"], kind="stable")
    legs = np.concatenate([np.arange(cat["leg0"][i], cat["leg0"][i] + cat["nleg"][i]) for i in o]) if len(o) else np.zeros(0, np.int64)
    out = {f: cat[f][o] for f in cat if f not in ("leix", "lepx")}
    out["leix"], out["lepx"] = cat["leix"][legs], cat["lepx"][legs]
    out["leg0"] = np.concatenate([[0], np.cumsum(out["nleg"])[:-1]]).astype(np.int64) if len(o) else np.zeros(0, np.int64)
    return X.Path_(**{f: out[f] for f in X.Path_.__dataclass_fields__})


# ───────────────────────────── §3 the per-unit stream ─────────────────────────────

@njit(cache=True)
def _stream(c, h, l, sp, k, d, eix, xix, xpx, why, leg0, nleg, leix, lepx):
    """Per M1 bar: realised cash, floating at the close mark, floating at the worst mark, signed units held."""
    n = c.shape[0]
    rel = np.zeros(n)
    fc = np.zeros(n)
    fw = np.zeros(n)
    pos = np.zeros(n)
    for i in range(d.shape[0]):
        dd = d[i]
        x = xix[i]
        if x >= n:
            x = n - 1
        for q in range(leg0[i], leg0[i] + nleg[i]):
            e = leix[q]
            ep = lepx[q]
            for j in range(e, x):
                if dd == 1:
                    cm = c[j]
                    wm = l[j]
                else:
                    cm = c[j] + sp[j]
                    wm = h[j] + sp[j]
                fc[j] += dd * (cm - ep) * k
                fw[j] += dd * (wm - ep) * k
                pos[j] += dd
            rel[x] += dd * (xpx[i] - ep) * k
            if why[i] == 3 or why[i] == 4:
                wm = l[x] if dd == 1 else h[x] + sp[x]
                v = dd * (wm - xpx[i]) * k
                if v < 0:
                    fw[x] += v
    return rel, fc, fw, pos


@dataclass
class Stream:
    """A per-unit stream on the market's M1 grid (USD, cumulative from the run start)."""
    t: np.ndarray
    ec: np.ndarray             # equity at each bar's close mark
    ew: np.ndarray             # worst equity inside each bar
    pos: np.ndarray            # signed units held during the bar
    tr: pd.DataFrame           # trades: e_t, x_t, dir, legs, pnl, why, closed
    n_extra: int = 0


def stream_of(m: X.Market, p: X.Path_) -> Stream:
    rel, fc, fw, pos = _stream(m.c, m.h, m.l, m.sp, m.k, p.dir, p.eix, p.xix, p.xpx, p.why, p.leg0, p.nleg, p.leix, p.lepx)
    cum = np.cumsum(rel)
    n = len(p)
    pnl = np.zeros(n)
    e0 = np.zeros(n, np.int64)
    for i in range(n):
        q = slice(p.leg0[i], p.leg0[i] + p.nleg[i])
        pnl[i] = float(np.sum(p.dir[i] * (p.xpx[i] - p.lepx[q]) * m.k))
        e0[i] = p.leix[q].min() if p.nleg[i] else p.eix[i]
    xi = np.minimum(p.xix, len(m) - 1)
    tr = pd.DataFrame({"e_t": m.t[e0], "x_t": m.t[xi], "dir": p.dir, "legs": p.nleg, "pnl": pnl, "why": p.why,
                       "closed": p.why != 4, "e_ix": e0, "x_ix": xi, "entry": p.epx, "exit": p.xpx})
    return Stream(m.t, cum + fc, cum + fw, pos, tr)


def _weeks_edges(a_s: int, z_s: int) -> np.ndarray:
    first = pd.Timestamp(a_s, unit="s").normalize()
    first += pd.Timedelta(days=(5 - first.dayofweek) % 7)
    t = np.arange(first.value // 10**9, z_s, 7 * DAY, dtype=np.int64)
    t = t[(t > a_s) & (t < z_s)]
    return np.concatenate([[a_s], t, [z_s]])


def _q_edges(a: str, z: str) -> np.ndarray:
    a_t, z_t = pd.Timestamp(a), pd.Timestamp(z)
    q = pd.date_range(a_t, z_t, freq="QS")
    e = sorted({a_t, *[x for x in q if a_t < x < z_t], z_t})
    return np.asarray([x.value // 10**9 for x in e], np.int64)


def eq_at(s: Stream, T: np.ndarray, base: float) -> np.ndarray:
    """Close-marked equity at times T (s): the last bar opening before T; ``base`` before the first."""
    i = np.searchsorted(s.t, np.asarray(T, np.int64), side="left") - 1
    return np.where(i >= 0, s.ec[np.maximum(i, 0)], base)


def split_metrics(s: Stream, a: str, z: str, spread: Optional[np.ndarray] = None) -> Dict[str, float]:
    a_s, z_s = s_of(a), s_of(z)
    ia, iz = int(np.searchsorted(s.t, a_s, "left")), int(np.searchsorted(s.t, z_s, "left"))
    e0 = float(s.ec[ia - 1]) if ia > 0 else 0.0
    out: Dict[str, float] = {}
    if iz <= ia:
        return dict(profit=np.nan)
    ec, ew = s.ec[ia:iz], s.ew[ia:iz]
    profit = float(ec[-1] - e0)
    peak = np.maximum.accumulate(np.concatenate([[e0], ec]))[1:]       # external's convention: the bar's close first
    dd = float(max(0.0, np.max(peak - ew)))
    years = (z_s - a_s) / (365.25 * DAY)
    days = (z_s - a_s) / DAY
    we = _weeks_edges(a_s, z_s)
    weq = eq_at(s, we, 0.0)
    weq[0] = e0
    wk = np.diff(weq)
    sd = float(np.std(wk, ddof=1)) if len(wk) > 2 else 0.0
    sr_w = float(np.mean(wk) / sd) if sd > 0 else 0.0
    qe = _q_edges(a, z)
    qeq = eq_at(s, qe, 0.0)
    qeq[0] = e0
    qp = np.diff(qeq)
    qix = np.searchsorted(s.t, qe, "left")
    expo_q = np.array([bool(np.any(s.pos[qix[i]:qix[i + 1]] != 0)) for i in range(len(qe) - 1)])
    de = np.unique(np.concatenate([np.arange((a_s // DAY + 1) * DAY, z_s, DAY), [z_s]]))
    deq = eq_at(s, de, 0.0)
    dpl = np.diff(np.concatenate([[e0], deq]))
    d5 = pd.Series(dpl).rolling(5).sum().min() if len(dpl) >= 5 else np.nan
    tr = s.tr[(s.tr.x_t >= a_s) & (s.tr.x_t < z_s) & s.tr.closed]
    hold_h = ((tr.x_t - tr.e_t) / 3600.0).to_numpy()
    pos = s.pos[ia:iz]
    cv = (eq_at(s, np.array([s_of(COVID[1])]), 0.0)[0] - eq_at(s, np.array([s_of(COVID[0])]), 0.0)[0]
          if a_s <= s_of(COVID[0]) and z_s >= s_of(COVID[1]) else 0.0)
    wkv = pd.Series(wk)
    out.update(
        profit=round(profit, 2), profit_per_week=round(profit / (days / 7.0), 4), max_dd=round(dd, 2),
        profit_dd=round(profit / dd, 4) if dd > 0 else np.nan,
        ann_profit_dd=round(profit / years / dd, 4) if dd > 0 else np.nan,
        sharpe_w=round(sr_w * math.sqrt(52), 4), sr_w_raw=sr_w, weeks=int(len(wk)),
        skew_w=float(wkv.skew()) if len(wk) > 3 else 0.0, kurt_w=float(wkv.kurt() + 3.0) if len(wk) > 3 else 3.0,
        pos_q_share=round(float((qp[expo_q] > 0).mean()), 4) if expo_q.any() else np.nan,
        n_q_exposed=int(expo_q.sum()), n_q=int(len(qp)),
        trades=int(len(tr)), avg_hold_h=round(float(hold_h.mean()), 2) if len(tr) else np.nan,
        time_in_mkt=round(float((pos != 0).mean()), 4), mean_pos=round(float(pos.mean()), 4),
        long_pnl=round(float(tr.pnl[tr.dir > 0].sum()), 2), short_pnl=round(float(tr.pnl[tr.dir < 0].sum()), 2),
        win_rate=round(float((tr.pnl > 0).mean()), 4) if len(tr) else np.nan,
        worst_day=round(float(dpl.min()), 2) if len(dpl) else np.nan,
        worst_5d=round(float(d5), 2) if d5 == d5 else np.nan,
        worst_week=round(float(wk.min()), 2) if len(wk) else np.nan,
        profit_ex_best=round(profit - float(tr.pnl.max()), 2) if len(tr) else round(profit, 2),
        profit_ex_covid=round(profit - cv, 2),
        median_spread=round(float(np.median(spread[ia:iz])), 4) if spread is not None else np.nan,
    )
    return out


def weekly_pnl(s: Stream, a: str, z: str) -> np.ndarray:
    a_s, z_s = s_of(a), s_of(z)
    ia = int(np.searchsorted(s.t, a_s, "left"))
    e0 = float(s.ec[ia - 1]) if ia > 0 else 0.0
    we = _weeks_edges(a_s, z_s)
    weq = eq_at(s, we, 0.0)
    weq[0] = e0
    return np.diff(weq)


def daily_eq(s: Stream, a: str, z: str) -> Tuple[np.ndarray, np.ndarray]:
    a_s, z_s = s_of(a), s_of(z)
    de = np.unique(np.concatenate([np.arange((a_s // DAY + 1) * DAY, z_s, DAY), [z_s]]))
    ia = int(np.searchsorted(s.t, a_s, "left"))
    e0 = float(s.ec[ia - 1]) if ia > 0 else 0.0
    return de, eq_at(s, de, 0.0) - e0


# ───────────────────────────── context for the builders ─────────────────────────────

@dataclass
class Ctx:
    m: X.Market                # the cost market (spread as the cost case)
    base: X.Market             # the floored x1 market (signals that read the spread use the cost market)
    sig: X.BotSignals
    z: Zones
    gold: X.Market
    rho: Dict[str, float]
    cache: dict = field(default_factory=dict)


def _ny(m: X.Market):
    loc = m.local(NY)
    return loc // DAY, (loc % DAY) // 60


def utc_ny(day: np.ndarray, hh: int, mm: int) -> np.ndarray:
    return X.utc_of_local(np.asarray(day, np.int64) * DAY + hh * 3600 + mm * 60, NY)


def weekdays(day: np.ndarray) -> np.ndarray:
    return (np.asarray(day) + 3) % 7 <= 4


def window_hl(m: X.Market, day: np.ndarray, minute: np.ndarray, a_min: int, z_min: int, need: float):
    """Per day (of the given clock): high, low, last close, last spread, first open, bar count of the bars opening in
    [a_min, z_min). Returns (days, H, L, C, SP, O, ok)."""
    idx = np.flatnonzero((minute >= a_min) & (minute < z_min) & weekdays(day))
    if not len(idx):
        e = np.zeros(0)
        return np.zeros(0, np.int64), e, e, e, e, e, np.zeros(0, bool)
    g = day[idx]
    first = np.flatnonzero(np.diff(g, prepend=g[0] - 1) != 0)
    H = np.maximum.reduceat(m.h[idx], first)
    L = np.minimum.reduceat(m.l[idx], first)
    cnt = np.diff(np.append(first, len(idx)))
    last = idx[np.append(first[1:] - 1, len(idx) - 1)]
    return g[first], H, L, m.c[last], m.sp[last], m.o[idx[first]], cnt >= need * (z_min - a_min)


def d1(m: X.Market) -> X.Bars:
    return m.bars("D1")


def monthly(m: X.Market):
    """(decision times M = 00:00 UTC of each month start, monthly closes = last D1 close before M, with the first M1
    open standing for the close before the data start, DEVIATIONS 9)."""
    b = d1(m)
    M = X.month_starts(m)
    i = np.searchsorted(b.tc, M, side="right") - 1
    good = i >= 0
    M, i = M[good], i[good]
    Cm = b.c[i]
    M0 = np.concatenate([[int(m.t[0])], M])
    C0 = np.concatenate([[m.o[0]], Cm])
    return M0, C0


def state_plan(m: X.Market, dt: np.ndarray, state: np.ndarray, long_only: bool = False, **kw) -> X.PathPlan:
    st = np.where(np.asarray(state) > 0, 1, np.where((np.asarray(state) < 0) & (not long_only), -1, 0)).astype(np.int64)
    return X.make_plan(m, dt, want=st, xl=st != 1, xs=st != -1, **kw)


def ema(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def sign_at(tc: np.ndarray, v: np.ndarray):
    return lambda T: X.value_at(tc, v, T, 0)


# ───────────────────────────── §4 the candidates ─────────────────────────────
# Each builder returns a Spec: the plans (lanes), whether it is sub-daily (entry zones apply), whether its entries are
# stop orders, and whether every signal is its own position.

@dataclass
class Spec:
    plans: List[X.PathPlan]
    intra: bool = False
    stop_entry: bool = False
    every: bool = False
    pmax: int = 1
    d_stop: bool = False       # the plan's T_risk is a stop distance (sizing iv)


# TREND ---------------------------------------------------------------------------------------------------------

def c01(c: Ctx, L: int, lo: bool) -> Spec:
    M, C = monthly(c.m)
    s = np.zeros(len(C))
    s[L:] = np.sign(C[L:] / C[:-L] - 1.0)
    return Spec([state_plan(c.m, M[L:], s[L:], lo)])


def _tsmom_S(m: X.Market) -> Tuple[np.ndarray, np.ndarray]:
    b = d1(m)
    C = b.c
    S = np.zeros(len(C))
    for k in (21, 63, 252):
        s = np.zeros(len(C))
        if len(C) > k:
            s[k:] = np.sign(C[k:] / C[:-k] - 1.0)
        S += s
    M = X.month_starts(m)
    i = np.searchsorted(b.tc, M, side="right") - 1
    good = i >= 0
    return M[good], S[i[good]]


def c02(c: Ctx, how: str, lo: bool) -> Spec:
    M, S = _tsmom_S(c.m)
    st = np.sign(S) if how == "majority" else np.where(np.abs(S) == 3, np.sign(S), 0)
    return Spec([state_plan(c.m, M, st, lo)])


def _turtle(c: Ctx, system: int, P: int, kN: float, votes: bool) -> Spec:
    key = ("turtle", system)
    if key not in c.cache:
        c.cache[key] = X.turtle(c.m, system).plan
    plan = c.cache[key]
    f = dict(plan.f)
    N = f["pstep"] * 2.0
    f["sl"] = kN * N
    f["rk"] = np.full(len(plan), np.nan)
    plan = plan.copy(f=f, pmax=np.full(len(plan), P, np.int64))
    if votes:
        plan = X.filtered(plan, c.m, c.sig.votes_at)
    return Spec([plan], stop_entry=True, pmax=P, d_stop=True)


def c03(c: Ctx, P: int, kN: float, votes: bool) -> Spec:
    return _turtle(c, 1, P, kN, votes)


def c04(c: Ctx, P: int, kN: float, votes: bool) -> Spec:
    return _turtle(c, 2, P, kN, votes)


@njit(cache=True)
def _clenow(C, up, B, atr, mult):
    n = C.shape[0]
    st = np.zeros(n, np.int64)
    p = 0
    best = 0.0
    for b in range(n):
        if p == 1:
            if C[b] > best:
                best = C[b]
            if C[b] <= best - mult * atr[b]:
                p = 0
        elif p == -1:
            if C[b] < best:
                best = C[b]
            if C[b] >= best + mult * atr[b]:
                p = 0
        elif b >= B - 1 and atr[b] == atr[b]:
            hi = C[b]
            lo = C[b]
            for q in range(b - B + 1, b + 1):
                if C[q] > hi:
                    hi = C[q]
                if C[q] < lo:
                    lo = C[q]
            if up[b] == 1 and C[b] >= hi:
                p = 1
                best = C[b]
            elif up[b] == -1 and C[b] <= lo:
                p = -1
                best = C[b]
        st[b] = p
    return st


def c05(c: Ctx, Bn: int, mult: float) -> Spec:
    b = d1(c.m)
    up = np.sign(ema(b.c, 50) - ema(b.c, 100)).astype(np.int64)
    atr = X.wilder_atr(b.h, b.l, b.c, 100)
    st = _clenow(b.c, up, Bn, atr, mult)
    return Spec([state_plan(c.m, b.tc, st)])


def c06(c: Ctx, s: int, l: int, lo: bool) -> Spec:
    M, C = monthly(c.m)
    fs, fl = X.sma(C, s), X.sma(C, l)
    st = np.where(np.isfinite(fs) & np.isfinite(fl), np.sign(fs - fl), 0)
    return Spec([state_plan(c.m, M, st, lo)])


def c07(c: Ctx, L: int) -> Spec:
    M, C = monthly(c.m)
    hi = pd.Series(C).shift(1).rolling(L, min_periods=L).max().to_numpy()
    lo = pd.Series(C).shift(1).rolling(L, min_periods=L).min().to_numpy()
    st = np.zeros(len(C))
    p = 0
    for i in range(len(C)):
        if np.isfinite(hi[i]):
            if C[i] > hi[i]:
                p = 1
            elif C[i] < lo[i]:
                p = -1
        st[i] = p
    return Spec([state_plan(c.m, M, st)])


def c08(c: Ctx, n: int) -> Spec:
    M, C = monthly(c.m)
    s = X.sma(C, n)
    st = np.where(np.isfinite(s) & (C > s), 1, 0)
    return Spec([state_plan(c.m, M, st, True)])


def _ewmac_f(b: X.Bars, fast: int, slow: int, a0: int, a1: int) -> np.ndarray:
    C = b.c
    dP = np.abs(np.diff(C, prepend=np.nan))
    sig = pd.Series(dP).ewm(span=25, adjust=False, ignore_na=True).mean().to_numpy()
    raw = (ema(C, fast) - ema(C, slow)) / np.where(sig > 0, sig, np.nan)
    warm = (b.tc > a0) & (b.tc <= a1) & np.isfinite(raw)
    scale = 10.0 / np.mean(np.abs(raw[warm]))
    return np.clip(raw * scale, -20.0, 20.0)


def c09(c: Ctx, speed: str) -> Spec:
    b = d1(c.m)
    a0, a1 = s_of(WARM), s_of(DEV[0])
    pairs = {"16/64": [(16, 64)], "32/128": [(32, 128)], "64/256": [(64, 256)],
             "blend": [(16, 64), (32, 128), (64, 256)]}[speed]
    f = np.mean([_ewmac_f(b, p, q, a0, a1) for p, q in pairs], axis=0)
    u = np.clip(np.round(np.nan_to_num(f) / 10.0), -2, 2)
    lane1 = np.where(np.abs(u) >= 1, np.sign(u), 0)
    lane2 = np.where(np.abs(u) >= 2, np.sign(u), 0)
    return Spec([state_plan(c.m, b.tc, lane1), state_plan(c.m, b.tc, lane2)])


def c10(c: Ctx, ls: bool) -> Spec:
    return Spec([X.donchian_ensemble(c.m, long_short=ls).plan])


def c11(c: Ctx, n: int) -> Spec:
    b = d1(c.m)
    s = X.sma(b.c, n)
    st = np.where(np.isfinite(s), np.sign(b.c - s), 0)
    return Spec([state_plan(c.m, b.tc, st)])


def c12(c: Ctx, period: int, mult: float) -> Spec:
    return Spec([X.supertrend(c.m, long_only=False, tf="H4", period=period, mult=mult).plan], intra=True)


def c13(c: Ctx, N: int, H: int) -> Spec:
    b = d1(c.m)
    hi = pd.Series(b.h).shift(1).rolling(N, min_periods=N).max().to_numpy()
    lo = pd.Series(b.l).shift(1).rolling(N, min_periods=N).min().to_numpy()
    sig = np.where(np.isfinite(hi) & (b.c > hi), 1, np.where(np.isfinite(lo) & (b.c < lo), -1, 0))
    dts, wants, xts = [], [], []
    nxt = 0
    for i in np.flatnonzero(sig != 0):
        if i < nxt or i + H >= len(b):
            continue
        dts.append(b.tc[i])
        wants.append(sig[i])
        xts.append(b.tc[i + H])
        nxt = i + H + 1
    plan = X.merge_plans(c.m, [dict(dt=np.asarray(dts, np.int64), want=np.asarray(wants)),
                               dict(dt=np.asarray(xts, np.int64), xl=True, xs=True)])
    return Spec([plan])


# INTRADAY ------------------------------------------------------------------------------------------------------

def _oco_rows(c: Ctx, days, H, L, C, SP, ok, t_ord, lvl_b, lvl_s, **stops):
    buy_ok = ok & (C + SP < lvl_b)
    sell_ok = ok & (C > lvl_s)
    good = ok & (t_ord > 0)
    part = dict(dt=t_ord[good], bstop=np.where(buy_ok, lvl_b, np.nan)[good],
                sstop=np.where(sell_ok, lvl_s, np.nan)[good])
    for k_, v in stops.items():
        part[k_] = np.asarray(v)[good] if np.ndim(v) else v
    return part, good


def c14(c: Ctx, R: int, Xt: str) -> Spec:
    day, minute = _ny(c.m)
    a = 8 * 60 + 25
    days, H, L, C, SP, O, ok = window_hl(c.m, day, minute, a, a + R, 0.5)
    t_ord = utc_ny(days, 8, 25 + R)
    part, good = _oco_rows(c, days, H, L, C, SP, ok, t_ord, H + TICK, L - TICK, bsl=L, ssl=H)
    hh, mm = (13, 25) if Xt == "13:25" else (16, 45)
    cancel = utc_ny(days[good], 12, 0)
    exit_t = utc_ny(days[good], hh, mm)
    plan = X.merge_plans(c.m, [part, dict(dt=cancel[cancel > 0]), dict(dt=exit_t[exit_t > 0], xl=True, xs=True)],
                         orders=True)
    return Spec([plan], intra=True, stop_entry=True, d_stop=True)


def c15(c: Ctx, Xt: str) -> Spec:
    day, minute = _ny(c.m)
    days, H, L, C, SP, O, ok = window_hl(c.m, day, minute, 8 * 60 + 25, 8 * 60 + 30, 0.6)
    up = ok & (C - O >= TICK)
    dn = ok & (O - C >= TICK)
    want = np.where(up, 1, np.where(dn, -1, 0))
    T = utc_ny(days, 8, 30)
    hh, mm = (13, 25) if Xt == "13:25" else (16, 45)
    xt = utc_ny(days, hh, mm)
    g = (T > 0) & (want != 0)
    plan = X.merge_plans(c.m, [dict(dt=T[g], want=want[g], trl=L[g], trs=H[g], tpr=10.0),
                               dict(dt=xt[xt > 0], xl=True, xs=True)], live_s=LIVE_S)
    return Spec([plan], intra=True, d_stop=True)


def _server_days(m: X.Market):
    loc = B.server_clock(m)
    sday = loc // DAY
    first = np.flatnonzero(np.diff(sday, prepend=sday[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(sday) - 1)
    H = np.maximum.reduceat(m.h, first)
    L = np.minimum.reduceat(m.l, first)
    return sday[first], first, last, H, L


def c16(c: Ctx, kk: float) -> Spec:
    m = c.m
    sd, first, last, H, L = _server_days(m)
    wk = weekdays(sd)
    R = np.concatenate([[np.nan], (H - L)[:-1]])
    O = m.o[first]
    T = m.t[first] + ZONE_S
    j = np.searchsorted(m.t, T, "left") - 1          # the last bar before the orders go in
    j = np.clip(j, 0, len(m) - 1)
    ok = wk & np.isfinite(R) & (R > 0)
    lb, ls = O + kk * R, O - kk * R
    buy_ok = ok & (m.c[j] + m.sp[j] < lb)
    sell_ok = ok & (m.c[j] > ls)
    xt = utc_ny(sd, 16, 45)                          # server day D = NY day D up to 17:00
    g = ok & (xt > T)
    plan = X.merge_plans(m, [dict(dt=T[g], bstop=np.where(buy_ok, lb, np.nan)[g], sstop=np.where(sell_ok, ls, np.nan)[g],
                                  sl=(0.5 * kk * R)[g]),
                             dict(dt=xt[g], xl=True, xs=True)], orders=True)
    return Spec([plan], intra=True, stop_entry=True, d_stop=True)


def london_range_pct(m: X.Market, clock: str, a: str, z: str) -> float:
    loc = (m.local(NY) + 7 * 3600) if clock == "server" else m.t
    day, minute = loc // DAY, (loc % DAY) // 60
    sel = (m.t >= s_of(a)) & (m.t < s_of(z))
    days, H, L, C, SP, O, ok = window_hl(m, np.where(sel, day, -10**6), minute, 180, 480, 0.2)
    keep = ok & (days > 0)
    return float(np.median((H - L)[keep] / C[keep]))


def c17(c: Ctx, clock: str, T: float) -> Spec:
    m = c.m
    rho = c.rho[clock]
    loc = (m.local(NY) + 7 * 3600) if clock == "server" else m.t
    day, minute = loc // DAY, (loc % DAY) // 60
    idx = np.flatnonzero((minute >= 180) & (minute < 480) & ((day + 3) % 7 <= 4))
    g = day[idx]
    first = np.flatnonzero(np.diff(g, prepend=g[0] - 1) != 0)
    H = np.maximum.reduceat(m.h[idx], first)
    L = np.minimum.reduceat(m.l[idx], first)
    cnt = np.diff(np.append(first, len(idx)))
    last = idx[np.append(first[1:] - 1, len(idx) - 1)]
    spr = np.add.reduceat(m.sp[idx], first) / cnt
    D = g[first]
    px = m.c[last]
    rng = H - L
    ok = (cnt >= 60) & (rng >= 0.003 * rho * px) & (rng <= 0.016 * rho * px)
    buf = np.maximum(2.0 * spr, 0.05 * rng)
    start = D * DAY + 8 * 3600
    stop_t = D * DAY + 21 * 3600
    if clock == "server":
        start, stop_t = X.utc_of_local(start - 7 * 3600, NY), X.utc_of_local(stop_t - 7 * 3600, NY)
        ny_day = D
    else:
        ny_day = X.local_seconds(start, NY) // DAY
    stop_t = np.where(stop_t > 0, np.minimum(stop_t, utc_ny(ny_day, 16, 45)), stop_t)
    good = (start > 0) & (stop_t > start)
    plan = X.merge_plans(m, [dict(dt=start[good], bstop=np.where(ok, H + buf, np.nan)[good],
                                  sstop=np.where(ok, L - buf, np.nan)[good], bsl=np.where(ok, L, np.nan)[good],
                                  ssl=np.where(ok, H, np.nan)[good], slcap=0.006 * rho, tpr=T, ber=1.5),
                             dict(dt=stop_t[good], xl=True, xs=True)], orders=True)
    return Spec([plan], intra=True, stop_entry=True, d_stop=True)


def c18(c: Ctx, W: str, s_pct: float) -> Spec:
    m = c.m
    if W == "london":
        loc = m.local(LDN)
        day, minute = loc // DAY, (loc % DAY) // 60
        days, H, L, C, SP, O, ok = window_hl(m, day, minute, 7 * 60, 9 * 60, 0.5)
        t_ord = X.utc_of_local(days * DAY + 9 * 3600, LDN)
        ny_day = X.local_seconds(np.maximum(t_ord, 0), NY) // DAY
    else:
        day, minute = _ny(m)
        days, H, L, C, SP, O, ok = window_hl(m, day, minute, 8 * 60 + 25, 9 * 60 + 30, 0.5)
        t_ord = utc_ny(days, 9, 30)
        ny_day = days
    part, good = _oco_rows(c, days, H, L, C, SP, ok & (H > L), t_ord, H, L, slf=s_pct / 100.0)
    cancel = utc_ny(ny_day[good], 12, 0)
    xt = utc_ny(ny_day[good], 16, 45)
    plan = X.merge_plans(m, [part, dict(dt=cancel[cancel > part["dt"]]), dict(dt=xt[xt > 0], xl=True, xs=True)],
                         orders=True)
    return Spec([plan], intra=True, stop_entry=True, d_stop=True)


def c19(c: Ctx, a: float, tp: float, sl: float) -> Spec:
    b = B.atr_breakout(c.m, period=200, mult=a, proximity=0.25, tp_pct=tp, sl_pct=sl)
    return Spec([b.plan], intra=True, every=True, d_stop=True)


def c20(c: Ctx, ref: str, hv: bool) -> Spec:
    m = c.m
    day, minute = _ny(m)
    days = np.unique(day[weekdays(day)])
    T_sig = utc_ny(days, 12, 55)
    T_x = utc_ny(days, 13, 25)
    p_sig, _ = X.price_before(m, T_sig, T_sig - 15 * 60)
    if ref == "close17":
        T17 = utc_ny(days, 17, 0)
        c17, _ = X.price_before(m, T17, T17 - 15 * 60)
        r0 = pd.Series(c17).ffill().shift(1).to_numpy()
    else:
        T0 = utc_ny(days, 8, 25)
        j = np.searchsorted(m.t, T0, "left")
        jj = np.minimum(j, len(m) - 1)
        r0 = np.where((j < len(m)) & (m.t[jj] - T0 < LIVE_S), m.o[jj], np.nan)
    r = p_sig / r0 - 1.0
    want = np.where(np.isfinite(r), np.sign(r), 0).astype(np.int64)
    if hv:
        dd, H, L, C, SP, O, ok = window_hl(m, day, minute, 8 * 60 + 25, 9 * 60 + 25, 0.5)
        rng = pd.Series(np.where(ok, H - L, np.nan), index=dd).reindex(days)
        med = rng.dropna().rolling(20, min_periods=20).median().reindex(rng.index).ffill().shift(1)
        want = np.where((rng.to_numpy() > med.to_numpy()), want, 0)
    g = (T_sig > 0) & (T_x > 0)
    plan = X.merge_plans(m, [dict(dt=T_sig[g], want=want[g]), dict(dt=T_x[g], xl=True, xs=True)], live_s=LIVE_S)
    return Spec([plan], intra=True)


def _noise(c: Ctx, b: float, trail: str) -> X.PathPlan:
    m = c.m
    day, minute = _ny(m)
    ldays = np.unique(day)
    ldays = ldays[weekdays(ldays)]
    a, z = 8 * 3600 + 25 * 60, 13 * 3600 + 25 * 60
    offs = np.arange((a // 1800 + 1) * 1800, z, 1800)
    start = utc_ny(ldays, 8, 25)
    end = utc_ny(ldays, 13, 25)
    checks = X.utc_of_local((ldays[:, None] * DAY + offs[None, :]).ravel(), NY).reshape(len(ldays), len(offs))
    good_s = (start > 0) & (end > 0)
    start, end, checks = start[good_s], end[good_s], checks[good_s]
    nS, nC = checks.shape
    j0 = np.searchsorted(m.t, start, side="left")
    has = (j0 < len(m)) & (m.t[np.minimum(j0, len(m) - 1)] < end)
    op = np.where(has, m.o[np.minimum(j0, len(m) - 1)], np.nan)
    cl, _ = X.price_before(m, end, start)
    P, jP = X.price_before(m, checks.ravel(), np.repeat(start, nC))
    P = P.reshape(nS, nC)
    jP = jP.reshape(nS, nC)
    move = np.abs(P / op[:, None] - 1.0)
    sig = X.mean_of_last_valid(move, 14)
    prev_cl = pd.Series(cl).ffill().shift(1).to_numpy()
    ub = np.maximum(op, prev_cl)[:, None] * (1.0 + b * sig)
    lb = np.minimum(op, prev_cl)[:, None] * (1.0 - b * sig)
    typ = (m.h + m.l + m.c) / 3.0
    cpv = np.concatenate([[0.0], np.cumsum(typ * m.n)])
    cv = np.concatenate([[0.0], np.cumsum(m.n)])
    jj = np.maximum(jP, 0)
    base = np.repeat(j0, nC).reshape(nS, nC)
    vol = cv[jj + 1] - cv[np.minimum(base, len(cv) - 1)]
    vwap = np.where((jP >= 0) & (vol > 0), (cpv[jj + 1] - cpv[np.minimum(base, len(cpv) - 1)]) / np.where(vol > 0, vol, 1.0), np.nan)
    good = np.isfinite(P) & np.isfinite(ub) & np.isfinite(lb) & np.isfinite(vwap) & (checks > 0)
    want = np.where(good & (P > ub), 1, np.where(good & (P < lb), -1, 0))
    if trail == "vwap":
        xl = good & (P < np.maximum(ub, vwap))
        xs = good & (P > np.minimum(lb, vwap))
    else:
        xl = good & (P < ub)
        xs = good & (P > lb)
    dt = checks.ravel()
    sel = dt > 0
    return X.merge_plans(m, [dict(dt=dt[sel], want=want.ravel()[sel], xl=xl.ravel()[sel], xs=xs.ravel()[sel]),
                             dict(dt=end, xl=True, xs=True)], live_s=LIVE_S)


def c21(c: Ctx, b: float, trail: str) -> Spec:
    return Spec([_noise(c, b, trail)], intra=True)


# MEAN REVERSION ------------------------------------------------------------------------------------------------

def c22(c: Ctx, lo: float, hi: float, ls: bool) -> Spec:
    p = X.connors_rsi2(c.m, lo, hi).plan
    if not ls:
        p = p.copy(want=np.where(p.want == 1, 1, 0))
    return Spec([p])


@njit(cache=True)
def _boll(C, m20, s20, s200, z, filt):
    n = C.shape[0]
    st = np.zeros(n, np.int64)
    p = 0
    for b in range(n):
        if p == 1 and C[b] >= m20[b]:
            p = 0
        elif p == -1 and C[b] <= m20[b]:
            p = 0
        if p == 0 and s20[b] == s20[b]:
            okl = (not filt) or (s200[b] == s200[b] and C[b] > s200[b])
            oks = (not filt) or (s200[b] == s200[b] and C[b] < s200[b])
            if C[b] < m20[b] - z * s20[b] and okl:
                p = 1
            elif C[b] > m20[b] + z * s20[b] and oks:
                p = -1
        st[b] = p
    return st


def c23(c: Ctx, z: float, filt: bool) -> Spec:
    b = d1(c.m)
    m20 = X.sma(b.c, 20)
    s20 = pd.Series(b.c).rolling(20, min_periods=20).std(ddof=0).to_numpy()
    st = _boll(b.c, m20, s20, X.sma(b.c, 200), z, filt)
    return Spec([state_plan(c.m, b.tc, st)])


def c24(c: Ctx, n: int) -> Spec:
    return Spec([X.max_min(c.m, n).plan])


def c25(c: Ctx, D: int) -> Spec:
    m = c.m
    loc = m.local(LDN)
    days = np.unique(loc // DAY)
    days = days[weekdays(days)]
    T = X.utc_of_local(days * DAY + 12 * 3600, LDN)
    T = T[T > 0]
    plan = X.merge_plans(m, [dict(dt=T, want=-1), dict(dt=T + D * 60, xl=True, xs=True)], live_s=LIVE_S)
    return Spec([plan], intra=True)


def c26(c: Ctx) -> Spec:
    m = c.m
    b = m.bars("M15")
    hi = pd.Series(b.h).shift(1).rolling(20, min_periods=20).max().to_numpy()
    lo = pd.Series(b.l).shift(1).rolling(20, min_periods=20).min().to_numpy()
    sig = np.where(b.c > hi, -1, np.where(b.c < lo, 1, 0))
    loc = X.local_seconds(b.tc, NY)
    mn = (loc % DAY) // 60
    inwin = (mn >= 7 * 60) & (mn < 16 * 60 + 45) & weekdays(loc // DAY)
    lim = X.utc_of_local((loc // DAY) * DAY + 16 * 3600 + 45 * 60, NY)
    dts, ws, xts = [], [], []
    nxt = -1
    for i in np.flatnonzero((sig != 0) & inwin):
        if b.tc[i] < nxt or lim[i] <= 0:
            continue
        xt = min(int(b.tc[i]) + 5 * 900, int(lim[i]))
        dts.append(b.tc[i]); ws.append(sig[i]); xts.append(xt)
        nxt = xt
    plan = X.merge_plans(m, [dict(dt=np.asarray(dts, np.int64), want=np.asarray(ws)),
                             dict(dt=np.asarray(xts, np.int64), xl=True, xs=True)], live_s=LIVE_S)
    return Spec([plan], intra=True)


# GOLD-LED ------------------------------------------------------------------------------------------------------

def gold_on(c: Ctx, tc: np.ndarray, which: str = "c") -> np.ndarray:
    """Gold's last M1 close at or before each time (bar close time ``tc``): aligned by timestamp."""
    g = c.gold
    j = np.searchsorted(g.t, np.asarray(tc, np.int64) - 60, side="right") - 1
    ok = (j >= 0) & (g.t[np.maximum(j, 0)] >= np.asarray(tc) - 900)
    return np.where(ok, g.c[np.maximum(j, 0)], np.nan)


@njit(cache=True)
def _ec_sched(z, gmove, gatr, okent, c_, Hb, stop_add):
    n = z.shape[0]
    ent = np.zeros(n, np.int64)
    ext = np.zeros(n, np.bool_)
    p = 0
    held = 0
    for i in range(n):
        if p != 0:
            held += 1
            zz = z[i]
            if zz != zz or (p == 1 and zz >= 0) or (p == -1 and zz <= 0) or held >= Hb or abs(zz) >= c_ + stop_add:
                ext[i] = True
                p = 0
            continue
        if not okent[i] or z[i] != z[i] or gatr[i] != gatr[i] or gmove[i] != gmove[i]:
            continue
        if z[i] < -c_ and gmove[i] > gatr[i]:
            p = 1
        elif z[i] > c_ and gmove[i] < -gatr[i]:
            p = -1
        if p != 0:
            ent[i] = p
            held = 0
    return ent, ext


def c27(c: Ctx, cz: float, Hb: int) -> Spec:
    m = c.m
    key = "c27_base"
    if key not in c.cache:
        b = m.bars("M15")
        gs = gold_on(c, b.tc)
        lx, lg = np.log(b.c), np.log(gs)
        rx, rg = np.diff(lx, prepend=np.nan), np.diff(lg, prepend=np.nan)
        cnt = np.bincount(b.t // DAY - (b.t // DAY).min())
        per_s = int(np.median(cnt[cnt > 0]))
        W = 20 * per_s
        sx, sg = pd.Series(rx), pd.Series(rg)
        beta = (sx.rolling(W, min_periods=W // 2).cov(sg) / sg.rolling(W, min_periods=W // 2).var()).to_numpy()
        s = lx - beta * lg
        ss = pd.Series(s)
        e = s - ss.rolling(W, min_periods=W // 2).mean().to_numpy()
        z = e / pd.Series(e).rolling(W, min_periods=W // 2).std().to_numpy()
        gh = c.gold.bars("H1")
        gatr_h = X.wilder_atr(gh.h, gh.l, gh.c, 14)
        gmv_h = np.diff(gh.c, prepend=np.nan)
        gatr = X.value_at(gh.tc, gatr_h, b.tc, np.nan)
        gmv = X.value_at(gh.tc, gmv_h, b.tc, np.nan)
        loc = X.local_seconds(b.tc, NY)
        mn = (loc % DAY) // 60
        late = mn >= 16 * 60 + 45                    # 16:45 NY until the break (the reopen zone is dropped later)
        c.cache[key] = (b, z, gmv, gatr, ~late, W)
    b, z, gmv, gatr, okent, W = c.cache[key]
    ent, ext = _ec_sched(np.ascontiguousarray(z), gmv, gatr, okent, cz, Hb, 2.0)
    e_i, x_i = np.flatnonzero(ent != 0), np.flatnonzero(ext)
    plan = X.merge_plans(m, [dict(dt=b.tc[e_i], want=ent[e_i]), dict(dt=b.tc[x_i], xl=True, xs=True)], live_s=LIVE_S)
    return Spec([plan], intra=True)


def c28(c: Ctx, N: int, E: int) -> Spec:
    m = c.m
    b = m.bars("H1")
    gs = gold_on(c, b.tc)
    ghi = pd.Series(gs).shift(1).rolling(N, min_periods=N).max().to_numpy()
    glo = pd.Series(gs).shift(1).rolling(N, min_periods=N).min().to_numpy()
    shi = pd.Series(b.c).shift(1).rolling(N, min_periods=N).max().to_numpy()
    slo = pd.Series(b.c).shift(1).rolling(N, min_periods=N).min().to_numpy()
    sig = np.where((gs > ghi) & ~(b.c > shi), 1, np.where((gs < glo) & ~(b.c < slo), -1, 0))
    atr = X.wilder_atr(b.h, b.l, b.c, 14)
    dts, ws, sls, xts = [], [], [], []
    nxt = -1
    for i in np.flatnonzero((sig != 0) & np.isfinite(atr)):
        if b.tc[i] < nxt or i + E >= len(b):
            continue
        dts.append(b.tc[i]); ws.append(sig[i]); sls.append(2.0 * atr[i]); xts.append(b.tc[i + E])
        nxt = b.tc[i + E]
    plan = X.merge_plans(m, [dict(dt=np.asarray(dts, np.int64), want=np.asarray(ws), sl=np.asarray(sls)),
                             dict(dt=np.asarray(xts, np.int64), xl=True, xs=True)], live_s=LIVE_S)
    return Spec([plan], intra=True, d_stop=True)


def _ema_dir(mk: X.Market):
    b = d1(mk)
    return b.tc, np.sign(ema(b.c, 50) - ema(b.c, 100)).astype(np.int64)


def c29(c: Ctx, base: str, filt: str) -> Spec:
    sp = {"C03": lambda: c03(c, 1, 2.0, False), "C05": lambda: c05(c, 50, 3.0), "C14": lambda: c14(c, 30, "13:25")}[base]()
    tc, v = _ema_dir(c.gold if filt == "gold" else c.m)
    sp.plans = [X.filtered(p, c.m, sign_at(tc, v)) for p in sp.plans]
    return sp


def _gsr(c: Ctx):
    """Gold / silver on D1 closes: gold's last D1 close at or before each silver D1 close."""
    b = d1(c.m)
    gd = d1(c.gold)
    g = X.value_at(gd.tc, gd.c, b.tc, np.nan)
    return b, g / b.c


def c30(c: Ctx, trend: bool) -> Spec:
    b, gsr = _gsr(c)
    med = pd.Series(gsr).rolling(250, min_periods=250).median().to_numpy()
    st = np.where(np.isfinite(med) & (gsr > med), 1, 0)
    if trend:
        s200 = X.sma(b.c, 200)
        st = np.where(np.isfinite(s200) & (b.c > s200), st, 0)
    return Spec([state_plan(c.m, b.tc, st, True)])


def c31(c: Ctx, n: int) -> Spec:
    b, gsr = _gsr(c)
    lg = pd.Series(np.log(gsr))
    z = ((lg - lg.rolling(n, min_periods=n).mean()) / lg.rolling(n, min_periods=n).std()).to_numpy()
    st = np.zeros(len(z))
    p, held = 0, 0
    for i in range(len(z)):
        if p != 0:
            held += 1
            if not np.isfinite(z[i]) or abs(z[i]) < 0.5 or held >= 2 * n:
                p = 0
        if p == 0 and np.isfinite(z[i]):
            if z[i] > 2:
                p, held = 1, 0
            elif z[i] < -2:
                p, held = -1, 0
        st[i] = p
    return Spec([state_plan(c.m, b.tc, st)])


# SEASON --------------------------------------------------------------------------------------------------------

def c32(c: Ctx, which: str) -> Spec:
    m = c.m
    if which in ("sepnov", "dec"):
        M = X.month_starts(m)
        mon = pd.to_datetime(M, unit="s").month.to_numpy()
        months = (9, 11) if which == "sepnov" else (12,)
        st = np.isin(mon, months).astype(np.int64)
        return Spec([state_plan(m, M, st, True)])
    day, minute = _ny(m)
    days = np.unique(day)
    dow = (days + 3) % 7
    if which == "weekend":
        fr = days[dow == 4]
        T = utc_ny(fr, 16, 45)
        Xt = utc_ny(fr + 3, 16, 45)
        g = (T > 0) & (Xt > 0)
        plan = X.merge_plans(m, [dict(dt=T[g], want=-1), dict(dt=Xt[g], xl=True, xs=True)], live_s=LIVE_S)
        return Spec([plan], intra=True)
    # Wednesday session: Tuesday's reopen + 5 min -> 16:45 NY Wednesday
    we = days[dow == 2]
    z = c.z
    T17 = utc_ny(we - 1, 17, 0)
    k = np.searchsorted(z.reopen_t, T17, "left")
    ok = k < len(z.reopen_t)
    T = np.where(ok, z.reopen_t[np.minimum(k, len(z.reopen_t) - 1)] + ZONE_S, -1)
    Xt = utc_ny(we, 16, 45)
    g = (T > 0) & (Xt > T) & (T - T17 < 4 * 3600)
    plan = X.merge_plans(m, [dict(dt=T[g], want=1), dict(dt=Xt[g], xl=True, xs=True)], live_s=LIVE_S)
    return Spec([plan], intra=True)


def c33(c: Ctx, which: str) -> Spec:
    m = c.m
    z = c.z
    if which == "night":
        rt = z.reopen_t
        ny = X.local_seconds(rt, NY)
        dow = ((ny // DAY) + 3) % 7
        hr = (ny % DAY) / 3600.0
        daily = (dow <= 3) & (hr >= 17) & (hr < 19)          # reopens after the Mon-Thu daily breaks
        T = rt[daily] + ZONE_S
        ld = X.local_seconds(T, LDN) // DAY + 1               # the next London morning
        Xt = X.utc_of_local(ld * DAY + 7 * 3600, LDN)
        g = (Xt > T)
        plan = X.merge_plans(m, [dict(dt=T[g], want=1), dict(dt=Xt[g], xl=True, xs=True)], live_s=LIVE_S)
        return Spec([plan], intra=True)
    days = np.unique(m.t // DAY)
    days = days[(days + 3) % 7 <= 3]
    T = days * DAY + 23 * 3600
    j = np.searchsorted(m.t, T, "left")
    open_then = (j < len(m)) & (m.t[np.minimum(j, len(m) - 1)] == T)
    T = T[open_then]
    plan = X.merge_plans(m, [dict(dt=T, want=1), dict(dt=T + 59 * 60, xl=True, xs=True)], live_s=60.0)
    return Spec([plan], intra=True)


def nfp_block(m: X.Market, plan: X.PathPlan) -> X.PathPlan:
    loc = X.local_seconds(plan.dt, NY)
    day = loc // DAY
    dom = pd.to_datetime(day * DAY, unit="s").day.to_numpy()
    fri = (day + 3) % 7 == 4
    mn = (loc % DAY) // 60
    bad = fri & (dom <= 7) & (mn >= 8 * 60 + 25) & (mn < 8 * 60 + 45)
    f = dict(plan.f)
    if plan.orders:
        f["bstop"] = np.where(bad, np.nan, f["bstop"])
        f["sstop"] = np.where(bad, np.nan, f["sstop"])
    return plan.copy(want=np.where(bad, 0, plan.want), f=f)


def c34(c: Ctx, base: str) -> Spec:
    sp = {"C14": lambda: c14(c, 30, "13:25"), "C20": lambda: c20(c, "close17", False),
          "C21": lambda: c21(c, 1.0, "vwap")}[base]()
    sp.plans = [nfp_block(c.m, p) for p in sp.plans]
    return sp


# ───────────────────────────── the registry (§4.2) ─────────────────────────────

@dataclass
class Variant:
    vid: str
    cid: str
    family: str
    params: Dict[str, object]
    build: Optional[Callable[[Ctx], Spec]]
    engine: str = "bars"          # "bars" or "ticks"
    flags: str = ""


def _v(cid, fam, params, fn, flags=""):
    lab = ",".join(f"{k}={v}" for k, v in params.items())
    return Variant(f"{cid}[{lab}]", cid, fam, dict(params), (lambda c, p=dict(params): fn(c, **p)), flags=flags)


def registry() -> List[Variant]:
    V: List[Variant] = []
    T, I, MR, G, S, BOT = "TREND", "INTRADAY", "MR", "GOLD", "SEASON", "BOT"
    V += [_v("C01", T, dict(L=L, lo=lo), c01) for lo in (False, True) for L in (6, 9, 12)]
    V += [_v("C02", T, dict(how=h, lo=lo), c02) for h in ("majority", "unanimous") for lo in (False, True)]
    tv = [dict(P=1, kN=2.0, votes=False), dict(P=4, kN=2.0, votes=False), dict(P=1, kN=1.0, votes=False),
          dict(P=1, kN=2.0, votes=True), dict(P=4, kN=2.0, votes=True)]
    V += [_v("C03", T, p, c03, "S" if p["votes"] else "") for p in tv]
    V += [_v("C04", T, p, c04, "S" if p["votes"] else "") for p in tv]
    V += [_v("C05", T, dict(Bn=b, mult=mm), c05) for b in (50, 100) for mm in (3.0, 5.0)]
    V += [_v("C06", T, dict(s=s, l=l, lo=lo), c06) for lo in (False, True) for s, l in ((1, 10), (1, 12), (3, 12))]
    V += [_v("C07", T, dict(L=L), c07) for L in (6, 9, 12)]
    V += [_v("C08", T, dict(n=n), c08) for n in (8, 10, 12)]
    V += [_v("C09", T, dict(speed=s), c09) for s in ("16/64", "32/128", "64/256", "blend")]
    V += [_v("C10", T, dict(ls=ls), c10) for ls in (False, True)]
    V += [_v("C11", T, dict(n=n), c11) for n in (50, 100, 200)]
    V += [_v("C12", T, dict(period=p, mult=mm), c12) for p in (10, 20) for mm in (3.0, 4.0)]
    V += [_v("C13", T, dict(N=N, H=H), c13, "M") for N in (20, 55) for H in (1, 5, 20)]
    V += [_v("C14", I, dict(R=R, Xt=x), c14, "M") for R in (15, 30) for x in ("13:25", "16:45")]
    V += [_v("C15", I, dict(Xt=x), c15) for x in ("13:25", "16:45")]
    V += [_v("C16", I, dict(kk=k), c16) for k in (0.5, 0.75, 1.0)]
    V += [_v("C17", I, dict(clock=cl, T=t), c17) for cl in ("server", "utc") for t in (1.5, 2.5)]
    V += [_v("C18", I, dict(W=w, s_pct=s), c18) for w in ("london", "ny") for s in (1.0, 2.0)]
    V += [_v("C19", I, dict(a=a, tp=tp, sl=sl), c19) for tp, sl in ((2.0, 0.5), (4.0, 1.0)) for a in (2.0, 2.5, 3.0)]
    V += [_v("C20", I, dict(ref=r, hv=h), c20, "M") for r in ("close17", "open0825") for h in (False, True)]
    V += [_v("C21", I, dict(b=b, trail=t), c21, "M") for b in (1.0, 1.5) for t in ("vwap", "bound")]
    V += [_v("C22", MR, dict(lo=lo, hi=hi, ls=ls), c22, "C") for ls in (False, True) for lo, hi in ((5.0, 95.0), (10.0, 90.0))]
    V += [_v("C23", MR, dict(z=z, filt=f), c23, "C") for f in (False, True) for z in (2.0, 2.5)]
    V += [_v("C24", MR, dict(n=n), c24, "C") for n in (10, 20)]
    V += [_v("C25", MR, dict(D=d), c25, "C") for d in (15, 30)]
    V += [_v("C26", MR, dict(), c26, "C,M")]
    V += [_v("C27", G, dict(cz=cz, Hb=h), c27) for cz in (1.5, 2.0) for h in (4, 16)]
    V += [_v("C28", G, dict(N=N, E=E), c28) for N in (20, 50) for E in (8, 24)]
    V += [_v("C29", G, dict(base=b, filt=f), c29) for b in ("C03", "C05", "C14") for f in ("gold", "silver")]
    V += [_v("C30", G, dict(trend=t), c30) for t in (False, True)]
    V += [_v("C31", G, dict(n=n), c31) for n in (20, 60)]
    V += [_v("C32", S, dict(which=w), c32, "C,M" if w in ("dec", "wed") else "C") for w in ("sepnov", "weekend", "wed", "dec")]
    V += [_v("C33", S, dict(which=w), c33, "C,M" if w == "h23" else "C") for w in ("night", "h23")]
    V += [_v("C34", I, dict(base=b), c34) for b in ("C14", "C20", "C21")]
    for cid, key, grid, flags in TICK_GRID:
        for p in grid:
            lab = ",".join(f"{k}={v}" for k, v in p.items())
            V.append(Variant(f"{cid}[{lab}]", cid, BOT, dict(p, key=key), None, engine="ticks", flags=flags))
    return V


# the tick-engine designs (C35-C40): (candidate, multisymbol key or 'live'/'slot5', grid, flags)
TICK_GRID = [
    ("C35", "live", [dict(target=5.0), dict(target=10.0), dict(target=20.0)], "S,Bot"),
    ("C36", "slot5", [dict(target=5.0), dict(target=10.0), dict(target=20.0)], "Bot"),
    ("C37", "v3lite", [dict(tv=6.0, sv=6.0), dict(tv=8.0, sv=8.0), dict(tv=10.0, sv=10.0)], "S,Bot"),
    ("C38", "gtop2", [dict(tv=8.0, sv=4.0, cap=14.72), dict(tv=8.0, sv=4.0, cap=30.0), dict(tv=10.0, sv=5.0, cap=14.72)], "S,Bot"),
    ("C39", "gtop1add", [dict(tv=8.0, sv=8.0), dict(tv=10.0, sv=8.0), dict(tv=12.0, sv=10.0)], "S,Bot"),
    ("C40", "btop2", [dict(tv=10.0, sv=8.0, cap=30.98), dict(tv=8.0, sv=8.0, cap=30.98), dict(tv=10.0, sv=8.0, cap=0.0)], "S,Bot"),
]

# §4.2 neighbours: numeric axes per candidate (each a list of values in grid order); irregular ones by hand (index lists)
AXES = {"C01": {"L": [6, 9, 12]}, "C05": {"Bn": [50, 100], "mult": [3.0, 5.0]},
        "C06": {("s", "l"): [(1, 10), (1, 12), (3, 12)]}, "C07": {"L": [6, 9, 12]}, "C08": {"n": [8, 10, 12]},
        "C09": {"speed": ["16/64", "32/128", "64/256"]}, "C11": {"n": [50, 100, 200]},
        "C12": {"period": [10, 20], "mult": [3.0, 4.0]}, "C13": {"N": [20, 55], "H": [1, 5, 20]},
        "C14": {"R": [15, 30], "Xt": ["13:25", "16:45"]}, "C15": {"Xt": ["13:25", "16:45"]}, "C16": {"kk": [0.5, 0.75, 1.0]},
        "C17": {"T": [1.5, 2.5]}, "C18": {"s_pct": [1.0, 2.0]}, "C19": {"a": [2.0, 2.5, 3.0]},
        "C21": {"b": [1.0, 1.5]}, "C22": {("lo", "hi"): [(5.0, 95.0), (10.0, 90.0)]}, "C23": {"z": [2.0, 2.5]},
        "C24": {"n": [10, 20]}, "C25": {"D": [15, 30]}, "C27": {"cz": [1.5, 2.0], "Hb": [4, 16]},
        "C28": {"N": [20, 50], "E": [8, 24]}, "C31": {"n": [20, 60]},
        "C35": {"target": [5.0, 10.0, 20.0]}, "C36": {"target": [5.0, 10.0, 20.0]},
        "C37": {("tv", "sv"): [(6.0, 6.0), (8.0, 8.0), (10.0, 10.0)]},
        "C39": {("tv", "sv"): [(8.0, 8.0), (10.0, 8.0), (12.0, 10.0)]}}
# by hand: variant index within the candidate -> neighbour indices
HAND = {"C03": {0: [1, 2], 1: [0], 2: [0], 3: [4], 4: [3]}, "C04": {0: [1, 2], 1: [0], 2: [0], 3: [4], 4: [3]},
        "C38": {0: [1, 2], 1: [0], 2: [0]}, "C40": {0: [1, 2], 1: [0], 2: [0]}}


def neighbours(V: List[Variant]) -> Dict[str, List[str]]:
    by_c: Dict[str, List[Variant]] = {}
    for v in V:
        by_c.setdefault(v.cid, []).append(v)
    out: Dict[str, List[str]] = {}
    for cid, vs in by_c.items():
        if cid in HAND:
            for i, v in enumerate(vs):
                out[v.vid] = [vs[j].vid for j in HAND[cid].get(i, [])]
            continue
        axes = AXES.get(cid)
        for v in vs:
            if not axes:
                out[v.vid] = []
                continue
            nb = []
            for ax, vals in axes.items():
                keys = ax if isinstance(ax, tuple) else (ax,)
                cur = tuple(v.params.get(k) for k in keys)
                if len(keys) == 1:
                    cur = cur[0]
                if cur not in vals:
                    continue                     # e.g. the C09 blend
                i = vals.index(cur)
                for j in (i - 1, i + 1):
                    if 0 <= j < len(vals):
                        want = dict(v.params)
                        new = vals[j] if isinstance(ax, tuple) else (vals[j],)
                        for k, x in zip(keys, new if isinstance(ax, tuple) else new):
                            want[k] = x
                        for w in vs:
                            if w.params == want:
                                nb.append(w.vid)
            out[v.vid] = nb
    return out


# ───────────────────────────── running a bar variant ─────────────────────────────

def paths_of(c: Ctx, spec: Spec, a_ix: int, z_ix: int) -> X.Path_:
    parts = []
    for plan in spec.plans:
        if spec.intra:
            plan = block_entries(c.m, plan, c.z)
        if spec.every:
            parts.append(B.every_signal(c.m, plan, a_ix, z_ix))
        else:
            parts.append(X.run_path(c.m, plan, a_ix, z_ix))
    return parts[0] if len(parts) == 1 else merge_paths(parts)


def run_bar_variant(v: Variant, ctxs: Dict[str, Ctx], a: str, costs: Sequence[str] = COSTS):
    """The per-unit stream of one bar variant for each cost case, continuous from ``a`` to the data end."""
    out = {}
    for cost in costs:
        c = ctxs[cost]
        spec = v.build(c)
        a_ix = c.m.ix(a)
        p = paths_of(c, spec, a_ix, len(c.m))
        pc, n_in, n_out = costed(c.m, p, c.z, spec.stop_entry, cost != "gross")
        s = stream_of(c.m, pc)
        s.n_extra = n_in + n_out
        out[cost] = (s, spec, p, pc)
    return out


# ───────────────────────────── selection statistics (§3) ─────────────────────────────

def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phinv(p):
    from statistics import NormalDist
    return NormalDist().inv_cdf(p)


EULER = 0.5772156649015329


def expected_max_sr(var_sr: float, N: int) -> float:
    """Bailey & Lopez de Prado: E[max] of N trial Sharpe ratios with variance var_sr and true mean 0."""
    return math.sqrt(var_sr) * ((1 - EULER) * _phinv(1 - 1.0 / N) + EULER * _phinv(1 - 1.0 / (N * math.e)))


def dsr(sr: float, T: int, skew: float, kurt: float, sr0: float) -> float:
    den = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if T < 3 or den <= 0:
        return np.nan
    return _phi((sr - sr0) * math.sqrt(T - 1) / math.sqrt(den))


def spa_test(D: np.ndarray, B_: int = 5000, block: float = 8.0, seed: int = 20261117) -> Tuple[float, int]:
    """Hansen (2005) SPA, studentised, stationary bootstrap, benchmark = flat (0). D: weeks x variants of weekly P/L.
    Returns the p-value and the index of the best variant."""
    T, M = D.shape
    keep = np.flatnonzero(D.std(axis=0) > 0)
    D = D[:, keep]
    dbar = D.mean(axis=0)
    rng = np.random.default_rng(seed)
    p_new = 1.0 / block
    stats = np.zeros((B_, D.shape[1]))
    for b in range(B_):
        idx = np.empty(T, np.int64)
        idx[0] = rng.integers(T)
        u = rng.random(T)
        r = rng.integers(T, size=T)
        for t in range(1, T):
            idx[t] = r[t] if u[t] < p_new else (idx[t - 1] + 1) % T
        stats[b] = D[idx].mean(axis=0)
    omega = np.sqrt(T) * stats.std(axis=0)
    omega = np.where(omega > 0, omega, np.inf)
    tstat = np.sqrt(T) * dbar / omega
    t_spa = max(float(tstat.max()), 0.0)
    thr = -math.sqrt(2.0 * math.log(math.log(T)))
    mu_c = np.where(tstat >= thr, dbar, 0.0)
    tb = (np.sqrt(T) * (stats - mu_c[None, :]) / omega).max(axis=1)
    tb = np.maximum(tb, 0.0)
    return float((tb >= t_spa).mean()), int(keep[int(np.argmax(tstat))])


# ───────────────────────────── the tick engine (C35-C40) ─────────────────────────────

STOP_REASONS = ("stop_loss", "stop_out", "trailing")


def tick_cfg(key: str, p: dict, a: str, z: str):
    from .. import experiments as E
    from ..config import SYMBOLS
    if key in ("live", "slot5"):
        cfg = E.live_config(SYM, start=a, end=z).replace(**MS.GOLD_WINDOW)
        cfg = cfg.replace(target_usd_per_unit=float(p["target"]), fixed_units=1, mtqty=0.01, initial_balance=MS.BIG)
        if key == "slot5":
            cfg = cfg.replace(ladder_multipliers=[1.0] * len(cfg.ladder_multipliers), fc_weights={"H4": 1})
        return cfg
    caps = MS.load_specs(SYM)["caps"]
    cfg = MS.basket_cfg(SYM, key, a, z, per_unit=True, cap_price=caps.get(key))
    cfg = cfg.replace(target_vol=float(p["tv"]), stop_vol=float(p["sv"]))
    if "cap" in p:
        cap = float(p["cap"])
        if abs(cap - 14.72) < 1e-9:
            cap = caps["gtop2"] * CONTRACT * 0.01          # the translation itself ($14.715)
        elif abs(cap - 30.98) < 1e-9:
            cap = caps["btop2"] * CONTRACT * 0.01
        cfg = cfg.replace(vol_cap_usd_per_unit=cap)
    assert SYMBOLS[SYM].contract_size == CONTRACT
    return cfg


def tick_prepare(a: str, z: str):
    from ..engine import fast
    check_cut(z)
    prep = fast.prepare(SYM, a, z, MS.TFS, mode="sec")
    guard(prep.t_ms // 1000, z, "sec rows")
    spr = prep.ask - prep.bid
    prep._silver_floor = month_floor(prep.t_ms // 1000, spr)
    return prep


def tick_cost(prep, cost: str):
    bid = prep.bid
    spr = np.maximum(prep.ask - bid, prep._silver_floor)
    ask = {"x1": bid + spr, "x15": bid + 1.5 * spr, "pct": bid * (1.0 + PCT_SPREAD), "gross": bid.copy()}[cost]
    return replace(prep, ask=np.ascontiguousarray(ask))


def tick_reopens(prep) -> np.ndarray:
    t = prep.t_ms // 1000
    return t[np.concatenate([[0], np.flatnonzero(np.diff(t) >= BREAK_S) + 1])]


def tick_stream(res, prep, cost: str) -> Stream:
    """The engine's per-unit result as a Stream on its per-minute equity grid, with the §2.2 extra spread."""
    b, f, eq = res.baskets, res.fills, res.equity
    bal0 = float(res.cfg.initial_balance)
    re_t = tick_reopens(prep)
    ft = f["fill_time"].astype("int64").to_numpy() // 10**9 if len(f) else np.zeros(0, np.int64)
    k_ = np.searchsorted(re_t, ft, "right") - 1
    near = (k_ >= 0) & (ft - re_t[np.maximum(k_, 0)] < ZONE_S)
    bk_reason = dict(zip(b["basket"], b["reason"])) if len(b) else {}
    is_stop = np.array([(a_ == "close") and (bk_reason.get(bb, "") in STOP_REASONS)
                        for a_, bb in zip(f["action"], f["basket"])], bool) if len(f) else np.zeros(0, bool)
    charge = (is_stop | near) & (cost != "gross")
    extra = np.where(charge, (f["ask"] - f["bid"]).to_numpy() * f["lots"].to_numpy() * CONTRACT, 0.0) if len(f) else np.zeros(0)
    ex_b = pd.Series(extra).groupby(f["basket"].to_numpy()).sum() if len(f) else pd.Series(dtype=float)
    bx = b["basket"].map(ex_b).fillna(0.0).to_numpy() if len(b) else np.zeros(0)
    ot = b["open_time"].astype("int64").to_numpy() // 10**9 if len(b) else np.zeros(0, np.int64)
    ct = b["close_time"].astype("int64").to_numpy() // 10**9 if len(b) else np.zeros(0, np.int64)
    side = np.where(b["side"] == "BUY", 1, -1) if len(b) else np.zeros(0, np.int64)
    et = eq["time"].astype("int64").to_numpy() // 10**9
    ev = eq["equity"].to_numpy() - bal0
    cum_x = np.concatenate([[0.0], np.cumsum(bx)])
    order = np.argsort(ct)
    ctc = ct[order]
    cxs = np.concatenate([[0.0], np.cumsum(bx[order])])
    ec = ev - cxs[np.searchsorted(ctc, et, "right")]
    ew = ec.copy()
    if len(b):
        bal_b = b["balance"].to_numpy() - b["pnl"].to_numpy() - bal0          # balance before the basket
        mae = b["mae"].to_numpy()
        worst = bal_b - cxs[np.searchsorted(ctc, ot, "right")] + np.minimum(mae, 0.0)      # mae <= 0 (engine)
        kk = np.clip(np.searchsorted(et, ot, "left"), 0, len(et) - 1)
        np.minimum.at(ew, kk, worst)
    j = np.searchsorted(ot, et, "right") - 1
    active = (j >= 0) & (et < ct[np.maximum(j, 0)]) if len(b) else np.zeros(len(et), bool)
    pos = np.where(active, side[np.maximum(j, 0)] if len(b) else 0, 0) * eq["lots"].to_numpy() / 0.01
    tr = pd.DataFrame({"e_t": ot, "x_t": ct, "dir": side, "legs": b["n_pos"].to_numpy() if len(b) else [],
                       "pnl": (b["pnl"].to_numpy() - bx) if len(b) else [], "why": b["reason"].to_numpy() if len(b) else [],
                       "closed": (b["reason"] != "end").to_numpy() if len(b) else [], "extra": bx,
                       "mae": b["mae"].to_numpy() if len(b) else [], "lots": b["lots"].to_numpy() if len(b) else []})
    s = Stream(et, ec, ew, pos, tr)
    s.n_extra = int(charge.sum())
    return s


# ───────────────────────────── §6 sizing accounts ─────────────────────────────

@njit(cache=True)
def _size_kernel(t, c, h, l, sp, k, d, e0, xix, xpx, why, leg0, nleg, leix, lepx, D, pmx,
                 mode, step, r, W, a_ix, z_ix, bal0, unit_max):
    """One account over [a_ix, z_ix) for trades (sorted by first entry e0). mode 0: one unit; 1: the unit rule with
    ``step``; 2: r of the Turtle-cut equity over D, capped by the worst-5-session rule (W). Returns per-bar close and
    worst equity, per-trade units (0 = skipped), and the account figures."""
    nt = d.shape[0]
    nb = z_ix - a_ix
    E_c = np.zeros(nb)
    E_w = np.zeros(nb)
    U = np.zeros(nb)
    units = np.zeros(nt)
    taken = np.zeros(nt, np.bool_)
    op = np.zeros(nt, np.int64)
    n_op = 0
    bal = bal0
    peak = bal0
    maxdd = 0.0
    maxddu = 0.0
    wiped = False
    wipe_j = -1
    held = 0.0
    last_ec = bal0
    stress = 0.0
    stress_j = -1
    ti = 0
    while ti < nt and e0[ti] < a_ix:
        ti += 1
    for j in range(a_ix, z_ix):
        while ti < nt and e0[ti] == j:
            s = 0.0
            if mode == 0:
                s = 1.0
            elif mode == 1:
                s = math.floor(bal / step) + 1.0
                if s > unit_max:
                    s = unit_max
            else:
                E = last_ec
                ddp = (peak - E) / peak if peak > 0 else 0.0
                Es = E * 0.8 ** math.floor(ddp * 10.0 + 1e-12)
                if D[ti] > 0:
                    s = math.floor(r * Es / (D[ti] * k) + 1e-9)
                P = c[j]
                capu = math.floor(0.25 * E / (W * P * k) + 1e-9) - held
                lim = math.floor(capu / pmx[ti] + 1e-9) if capu > 0 else 0.0
                if s > lim:
                    s = lim
                if s < 0:
                    s = 0.0
            units[ti] = s
            if s > 0:
                taken[ti] = True
                op[n_op] = ti
                n_op += 1
            ti += 1
        fc = 0.0
        fw = 0.0
        rl = 0.0
        held = 0.0
        q_keep = 0
        for qi in range(n_op):
            i = op[qi]
            s = units[i]
            dd = d[i]
            x = xix[i]
            done = False
            for q in range(leg0[i], leg0[i] + nleg[i]):
                if leix[q] > j:
                    continue
                ep = lepx[q]
                if j >= x or j == z_ix - 1 and x >= z_ix:
                    if j >= x:
                        v = s * k * dd * (xpx[i] - ep)
                        rl += v
                        if why[i] == 3 or why[i] == 4:
                            wm = l[j] if dd == 1 else h[j] + sp[j]
                            fw += min(0.0, s * k * dd * (wm - xpx[i]))
                        done = True
                        continue
                cm = c[j] if dd == 1 else c[j] + sp[j]
                wm = l[j] if dd == 1 else h[j] + sp[j]
                fc += s * k * dd * (cm - ep)
                fw += s * k * dd * (wm - ep)
                held += s
            if not done:
                op[q_keep] = i
                q_keep += 1
        n_op = q_keep
        bal_before = bal
        bal += rl
        ec = bal + fc
        ew = bal_before + rl + fw
        if ew <= 0.0:
            wiped = True
            wipe_j = j
            E_c[j - a_ix:] = 0.0
            E_w[j - a_ix:] = 0.0
            maxdd = 1.0
            if peak > maxddu:
                maxddu = peak
            bal = 0.0
            last_ec = 0.0
            break
        if ec > peak:
            peak = ec
        dd_ = (peak - ew) / peak
        if dd_ > maxdd:
            maxdd = dd_
        if peak - ew > maxddu:
            maxddu = peak - ew
        E_c[j - a_ix] = ec
        E_w[j - a_ix] = ew
        U[j - a_ix] = held
        st = held * k * c[j] * W / ec if ec > 0 else 0.0
        if st > stress:
            stress = st
            stress_j = j
        last_ec = ec
    return E_c, E_w, U, units, taken, last_ec, maxdd, maxddu, wiped, wipe_j, stress, stress_j


def worst_5session(m: X.Market, a: str, z: str) -> float:
    b = d1(m)
    sel = (b.tc > s_of(a)) & (b.tc <= s_of(z))
    C = b.c[sel]
    r = np.abs(C[5:] / C[:-5] - 1.0)
    return float(r.max())
