"""
More symbols: silver (XAGUSDm) and the forex pairs, run as the pre-registration says
(backtest_results/multisymbol/PREREG.md, frozen 2026-11-16 21:23 UTC, sha256 f8557434...).

    python -m backtesting.research.multisymbol gates            G1 + G2 on gold and BTC (+ the 8-year reproductions)
    python -m backtesting.research.multisymbol fetch SYM        download (CRC-checked), build without ticks, data gate,
                                                                trim, specs.json
    python -m backtesting.research.multisymbol half SYM sel|conf  the basket designs on one half + the USD replays
    python -m backtesting.research.multisymbol turtles SYM      the two Turtles on their four periods
    python -m backtesting.research.multisymbol finalize SYM     merge, write runs/<SYM>/, free the disk
    python -m backtesting.research.multisymbol g3 SYM sel|conf  G3: direct (a) and (b) runs against the replay
    python -m backtesting.research.multisymbol drive            the scheduler (majors first, G3 before the rest)
    python -m backtesting.research.multisymbol summary          runs/summary.csv, runs/data_quality.csv

Method (PREREG §6): each basket design runs once per period on the tick engine ('sec' mode) at a fixed one unit of
0.01 lot with a $1e9 balance, in the quote currency; a replay converts every basket to USD at its close (minute marks
at their minute) and rebuilds three accounts: the constant one-unit stream, (a) the bot's unit rule at 0.01 lot per
unit and (b) the unit rule at the volatility-matched lot L(S). The Turtles run on the M1 simulator; their account is a
copy of external._account_kernel's bot mode with the currency conversion added.
"""

from __future__ import annotations

import argparse
import fcntl
import gc
import json
import math
import os
import pickle
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from .. import experiments as E
from ..config import REPO_ROOT, SYMBOLS, SymbolSpec
from ..data import exness, quality, store
from ..engine import fast
from ..engine.kernels import vol_array
from . import balke as B
from . import external as X
from . import final10 as F

OUT = REPO_ROOT / "backtest_results" / "multisymbol"
RUNS = OUT / "runs"
CHECKS = OUT / "checks"
LOGS = OUT / "logs"
QUAL = OUT / "quality"
SPECS_JSON = OUT / "specs.json"
HEADS = OUT / "archive_heads.txt"

ACCOUNT = 2000.0
STEP_UP = 2500.0
UNIT_MAX = 10.0
BIG = 1e9                                   # the per-unit runs' balance: margin and stop-out never act
SPLIT = "2024-05-13"
DATA_END = "2026-11-13"
BASKET_HISTORY = "2021-05-01"
TURTLE_HISTORY = "2017-11-01"
PERIODS = {"sel": ("2021-11-13", SPLIT), "conf": (SPLIT, DATA_END), "tsel": ("2018-11-13", SPLIT),
           "8y": ("2018-11-13", DATA_END)}
BASKET_PERIODS = ("sel", "conf")
TURTLE_PERIODS = ("tsel", "conf", "sel", "8y")
TFS = ["M1", "M5", "M15", "H1", "H4"]       # the final ten's prepared set (H4 sets the 177-day warm-up)
GOLD_WINDOW = dict(window_enabled=True, window_start_min=60, window_end_min=4 * 1440 + 22 * 60)
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS

SILVER = "XAGUSDm"
MAJORS = ("EURUSDm", "USDJPYm", "GBPUSDm", "AUDUSDm", "USDCADm", "USDCHFm", "NZDUSDm")
CROSSES = ("EURGBPm", "EURJPYm", "EURCHFm", "AUDJPYm", "GBPJPYm", "EURAUDm", "CHFJPYm", "EURCADm", "GBPAUDm",
           "EURNZDm", "GBPCHFm", "GBPCADm", "CADJPYm")
RESERVES = ("AUDCHFm", "AUDCADm", "NZDJPYm", "CADCHFm", "GBPNZDm", "AUDNZDm", "NZDCHFm", "NZDCADm")
UNIVERSE = (SILVER,) + MAJORS + CROSSES                     # the order of §1 (tie-breaks)
RUN_ORDER = ("EURUSDm", "XAGUSDm", "USDJPYm", "GBPUSDm", "AUDUSDm", "USDCADm", "USDCHFm", "NZDUSDm") + CROSSES
CHECK_SYMBOLS = ("EURUSDm", "XAGUSDm")
NEW_SYMBOLS = UNIVERSE + RESERVES
BASE_SYMBOLS = ("XAUUSDm", "BTCUSDm")
CONVERSION = {"USD": None, "JPY": ("USDJPYm", "div"), "CAD": ("USDCADm", "div"), "CHF": ("USDCHFm", "div"),
              "GBP": ("GBPUSDm", "mul"), "AUD": ("AUDUSDm", "mul"), "NZD": ("NZDUSDm", "mul")}


def quote_of(sym: str) -> str:
    return "USD" if sym in BASE_SYMBOLS else sym[3:6]


def register(sym: str) -> None:
    """The symbol's contract (§3.1), added to the engine's table at runtime."""
    if sym in SYMBOLS:
        return
    if sym == SILVER:
        SYMBOLS[sym] = SymbolSpec(sym, contract_size=5000.0, digits=3, quote="USD", data_hole_s=0.0)
    else:
        q = quote_of(sym)
        SYMBOLS[sym] = SymbolSpec(sym, contract_size=100000.0, digits=3 if q == "JPY" else 5, quote=q, data_hole_s=0.0)


for _s in NEW_SYMBOLS:
    register(_s)

# ───────────────────────────── the designs (§4) ─────────────────────────────

_GOLD = F.own_designs("XAUUSDm")
_BTC = F.own_designs("BTCUSDm")
BASKETS = {
    "v3lite": ("Gold V3-lite", _GOLD["V3-lite"], None),
    "gtop2": ("Gold Top 2", _GOLD["Top 2"], ("XAUUSDm", 12.0)),
    "gtop1add": ("Gold Top 1 + add", _GOLD["Top 1"], None),
    "btop2": ("BTC Top 2", _BTC["Top 2"], ("BTCUSDm", 1200.0)),
}
TURTLES = {"ts2": ("BTC Turtle System 2 + bot votes", 2), "ts1": ("BTC Turtle System 1 + bot votes", 1)}
DESIGN_ORDER = ("v3lite", "gtop2", "gtop1add", "btop2", "ts2", "ts1")
DESIGN_NAME = {k: v[0] for k, v in {**BASKETS, **TURTLES}.items()}
BASE = {"XAUUSDm": ("v3lite", "gtop2", "gtop1add"), "BTCUSDm": ("btop2", "ts2", "ts1")}
FINAL10_LABEL = {"v3lite": "V3-lite", "gtop2": "Top 2", "gtop1add": "Top 1", "btop2": "Top 2",
                 "ts1": "Turtle + bot votes", "ts2": "Turtle [alt] + bot votes"}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def to_ms(x) -> int:
    return int(store.to_ms(x))


def _ms(x) -> np.ndarray:
    return np.asarray(pd.DatetimeIndex(x).asi8 // 1_000_000, np.int64)


def _iso(ms) -> str:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").isoformat()


def _update_json(path: Path, key: str, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        d = json.loads(path.read_text()) if path.exists() else {}
        d[key] = value
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(json.dumps(d, indent=1, default=str))
        os.replace(tmp, path)


def load_specs(sym: str) -> dict:
    if sym in BASE_SYMBOLS:
        return {"L": 0.01, "caps": {"gtop2": 12.0, "btop2": 1200.0}}
    return json.loads(SPECS_JSON.read_text())[sym]


# ───────────────────────────── currency conversion (§3.5) ─────────────────────────────

class FX:
    """USD per unit of the symbol's quote currency: the conversion pair's M1 bid close of the minute that holds the
    time, else of the last bar before it."""

    def __init__(self, sym: str):
        conv = CONVERSION[quote_of(sym)]
        self.pair, self.how = conv if conv else (None, None)
        if self.pair:
            m1 = store.load_m1(self.pair, TURTLE_HISTORY, "2026-12-01")
            if not m1 or len(m1["t"]) == 0:
                raise FileNotFoundError(f"no M1 bars of {self.pair} for converting {sym}")
            self.t = np.asarray(m1["t"], np.int64)
            self.c = np.asarray(m1["c"], np.float64)

    def at_s(self, t_s) -> np.ndarray:
        t = np.asarray(t_s, np.int64)
        if self.pair is None:
            return np.ones(t.shape, np.float64)
        i = np.maximum(np.searchsorted(self.t, (t // 60) * 60, side="right") - 1, 0)
        r = self.c[i]
        return 1.0 / r if self.how == "div" else r.astype(np.float64)


# ───────────────────────────── swap nights (§9) ─────────────────────────────

_SWAP_CACHE: Dict[bool, Tuple[np.ndarray, np.ndarray]] = {}


def swap_times(usdcad: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Swap instants (ms, UTC): 17:00 New York, Monday - Friday; weights 3 on Wednesday (Thursday for USDCAD)."""
    if usdcad not in _SWAP_CACHE:
        days = pd.date_range("2017-10-01", "2027-01-31", freq="D")
        loc = pd.DatetimeIndex([pd.Timestamp(d.year, d.month, d.day, 17) for d in days]).tz_localize("America/New_York")
        wd = loc.dayofweek
        keep = wd < 5
        t = loc[keep].tz_convert("UTC").asi8 // 1_000_000
        w = np.where(wd[keep] == (3 if usdcad else 2), 3.0, 1.0)
        _SWAP_CACHE[usdcad] = (np.asarray(t, np.int64), np.concatenate([[0.0], np.cumsum(w)]))
    return _SWAP_CACHE[usdcad]


def nights(o_ms, c_ms, usdcad: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Swap times t with open < t <= close: (count, weighted count)."""
    t, cw = swap_times(usdcad)
    i0 = np.searchsorted(t, np.asarray(o_ms, np.int64), side="right")
    i1 = np.searchsorted(t, np.asarray(c_ms, np.int64), side="right")
    return (i1 - i0).astype(np.int64), cw[i1] - cw[i0]


# ───────────────────────────── the basket replay (§6.1) ─────────────────────────────

@njit(cache=True)
def _replay_kernel(ev_t, ev_ty, ev_ix, s_f, s_k, b_pnl, b_mae, b_closed, rule, lotf, bal0, step_up, unit_max, end_t):
    """
    Events in time order (at one instant: close 0, open 1, minute sample 2). ``s_f`` the floating P/L of one unit in
    USD at each sample (its basket ``s_k``), ``b_pnl`` / ``b_mae`` a basket's P/L and worst floating P/L at one unit in
    USD (at its close). rule 0: always one unit; 1: min(floor(B / step) + 1, max) from the closed balance at the open.
    """
    n = ev_t.shape[0]
    nb = b_pnl.shape[0]
    units = np.zeros(nb)
    acc = np.full(nb, np.nan)
    done = np.zeros(nb, np.bool_)
    mt = np.empty(n + 2, np.int64)
    me = np.empty(n + 2)
    nm = 0
    bal = bal0
    peak = bal0
    ddu = 0.0
    ddp = 0.0
    wiped = False
    wipe_t = -1
    cur = -1
    mult = 0.0
    bal_open = bal0
    peak_open = bal0
    final = bal0
    open_end = False
    for e in range(n):
        ty = ev_ty[e]
        ix = ev_ix[e]
        T = ev_t[e]
        if ty == 1:
            u = 1.0
            if rule == 1:
                u = math.floor(bal / step_up) + 1.0
                if u > unit_max:
                    u = unit_max
            units[ix] = u
            mult = u * lotf
            cur = ix
            bal_open = bal
            peak_open = peak
            continue
        eq = bal
        if ty == 2:
            k = s_k[ix]
            if k >= 0 and k == cur:
                eq = bal + mult * s_f[ix]
        else:
            if ix != cur:
                continue
            trough = bal_open + mult * b_mae[ix]
            if peak_open - trough > ddu:
                ddu = peak_open - trough
            if (peak_open - trough) / peak_open > ddp:
                ddp = (peak_open - trough) / peak_open
            if trough <= 0.0:
                wiped = True
                wipe_t = T
                acc[ix] = -bal_open
                done[ix] = True
                bal = 0.0
                mt[nm] = T
                me[nm] = 0.0
                nm += 1
                if peak > ddu:
                    ddu = peak
                ddp = 1.0
                break
            if b_closed[ix]:
                p = mult * b_pnl[ix]
                acc[ix] = p
                done[ix] = True
                bal += p
                eq = bal
                cur = -1
            else:
                eq = bal + mult * b_pnl[ix]          # open at the end: valued at the last price
                acc[ix] = mult * b_pnl[ix]
                open_end = True
        if eq <= 0.0:
            wiped = True
            wipe_t = T
            if cur >= 0:
                acc[cur] = -bal_open
                done[cur] = True
            bal = 0.0
            mt[nm] = T
            me[nm] = 0.0
            nm += 1
            if peak > ddu:
                ddu = peak
            ddp = 1.0
            break
        if eq > peak:
            peak = eq
        if peak - eq > ddu:
            ddu = peak - eq
        if (peak - eq) / peak > ddp:
            ddp = (peak - eq) / peak
        mt[nm] = T
        me[nm] = eq
        nm += 1
        if open_end:
            final = eq
    if wiped:
        final = 0.0
    else:
        if not open_end:
            final = bal
        mt[nm] = end_t
        me[nm] = final
        nm += 1
    return final, ddu, ddp, wiped, wipe_t, units, acc, done, mt[:nm], me[:nm]


def unit_data(res, sym: str, a_ms: int, z_ms: int, fx: FX) -> dict:
    """The one-unit run's baskets (an open one at the end last, flagged), its minute samples, all in USD too."""
    b, f, sc = res.baskets, res.fills, res.scalars
    nb = len(b)
    o, c = _ms(b["open_time"]), _ms(b["close_time"])
    side = np.where(b["side"].to_numpy() == "BUY", 1, -1).astype(np.int64)
    npos = b["n_pos"].to_numpy(np.int64)
    lots = b["lots"].to_numpy(np.float64)
    pnl = b["pnl"].to_numpy(np.float64)
    mae = b["mae"].to_numpy(np.float64)
    reason = b["reason"].astype(str).tolist()
    closed = np.ones(nb, np.bool_)
    usdcad = sym == "USDCADm"
    # lot-weighted nights per basket (each position from its own open to the basket's close)
    lotn = np.zeros(nb)
    if nb and len(f):
        fc = f[(f["action"] == "close") & (f["basket"] < nb)]
        if len(fc):
            _, w = nights(_ms(fc["pos_open_time"]), _ms(fc["time"]), usdcad)
            lotn = np.bincount(fc["basket"].to_numpy(np.int64), weights=fc["lots"].to_numpy(np.float64) * w,
                               minlength=nb)[:nb]
    if sc.get("open_positions_at_end", 0) > 0:
        fo = f[(f["basket"] == nb) & f["action"].isin(["open", "add"])]
        o = np.append(o, int(_ms(fo["time"]).min()))
        c = np.append(c, z_ms - 1)
        side = np.append(side, 1 if sc["open_lots_at_end"] > 0 else -1)
        npos = np.append(npos, int(sc["open_positions_at_end"]))
        lots = np.append(lots, abs(sc["open_lots_at_end"]))
        pnl = np.append(pnl, sc["open_profit_at_end"])
        mae = np.append(mae, sc["open_mae_at_end"])
        reason.append("open at end")
        closed = np.append(closed, False)
        _, w = nights(_ms(fo["time"]), np.full(len(fo), z_ms - 1), usdcad)
        lotn = np.append(lotn, float((fo["lots"].to_numpy(np.float64) * w).sum()))
    eq = res.equity
    s_t = _ms(eq["time"])
    s_f = (eq["equity"].to_numpy(np.float64) - eq["balance"].to_numpy(np.float64))
    s_n = eq["n_pos"].to_numpy(np.int64)
    s_k = np.full(len(s_t), -1, np.int64)
    live = s_n > 0
    if live.any():
        k = np.searchsorted(o, s_t[live], side="right") - 1
        ok = (k >= 0) & (s_t[live] >= o[np.maximum(k, 0)]) & (s_t[live] < c[np.maximum(k, 0)])
        if not ok.all():
            raise RuntimeError(f"{(~ok).sum()} minute samples with positions outside every basket")
        s_k[live] = k
    fxc = fx.at_s(c // 1000)
    n_all, w_all = nights(o, c, usdcad)
    d = dict(o=o, c=c, side=side, npos=npos, lots=lots, pnl=pnl, mae=mae, reason=reason, closed=closed,
             fx_close=fxc, pnl_usd=pnl * fxc, mae_usd=mae * fxc, lot_nights=lotn, nights=n_all, nights_w=w_all,
             s_t=s_t, s_fusd=s_f * fx.at_s(s_t // 1000), s_k=s_k, a_ms=a_ms, z_ms=z_ms)
    if len(o) > 1 and bool(np.any(o[1:] < c[:-1])):
        raise RuntimeError("two baskets overlap: the bot holds one basket per symbol")
    ev_t = np.concatenate([c, o, s_t]).astype(np.int64)
    ev_ty = np.concatenate([np.zeros(len(c), np.int64), np.ones(len(o), np.int64), np.full(len(s_t), 2, np.int64)])
    ev_ix = np.concatenate([np.arange(len(c)), np.arange(len(o)), np.arange(len(s_t))]).astype(np.int64)
    order = np.lexsort((ev_ty, ev_t))
    d.update(ev_t=ev_t[order], ev_ty=ev_ty[order], ev_ix=ev_ix[order])
    return d


def replay(d: dict, rule: int, lotf: float) -> dict:
    final, ddu, ddp, wiped, wipe_t, units, acc, done, mt, me = _replay_kernel(
        d["ev_t"], d["ev_ty"], d["ev_ix"], d["s_fusd"], d["s_k"], d["pnl_usd"], d["mae_usd"], d["closed"],
        int(rule), float(lotf), ACCOUNT, STEP_UP, UNIT_MAX, int(d["z_ms"] - 1))
    return dict(final=float(final), ddu=float(ddu), ddp=float(ddp) * 100.0, wiped=bool(wiped),
                wipe_ms=int(wipe_t) if wiped else None, units=units, pnl=acc, done=done, mt=mt, me=me)


ACCOUNTS = (("stream", 0, 1.0), ("a", 1, 1.0), ("b", 1, None))       # (name, rule, lot factor; None = L / 0.01)


def lot_factor(acc_lotf: Optional[float], L: float) -> float:
    return float(acc_lotf) if acc_lotf is not None else round(L / 0.01, 6)


# ───────────────────────────── the Turtle account (§6.2) ─────────────────────────────

@njit(cache=True)
def _turtle_kernel(t, h, l, c, sp, k, fx, T_dir, T_eix, T_epx, T_xix, T_xpx, T_why, T_leg0, T_nleg, L_eix, L_epx,
                   fixed, bnd, bal0, step_up, unit_max):
    """external._account_kernel, mode 0 (the bot's unit rule; ``fixed``: always one unit), with every minute's mark
    and the exit's P/L x ``fx`` of that minute, and the largest fall also in USD."""
    nt = T_dir.shape[0]
    nb = bnd.shape[0]
    steps = np.zeros(nt)
    pnl = np.zeros(nt)
    eqb = np.full(nb, np.nan)
    bal = bal0
    peak = bal0
    maxdd = 0.0
    maxddu = 0.0
    wiped = False
    wipe_ix = -1
    n_done = 0
    bi = 0
    for i in range(nt):
        n_done = i + 1
        e = T_eix[i]
        x = T_xix[i]
        d = T_dir[i]
        while bi < nb and bnd[bi] <= e:
            eqb[bi] = bal
            bi += 1
        if fixed:
            s = 1.0
        else:
            s = math.floor(bal / step_up) + 1.0
            if s > unit_max:
                s = unit_max
        steps[i] = s
        for j in range(e, x + 1):
            uc = 0.0
            uw = 0.0
            for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
                if L_eix[q] > j:
                    continue
                ep = L_epx[q]
                if j == x:
                    mc = T_xpx[i]
                    why = T_why[i]
                    if why == 3 or why == 4:
                        mw = l[j] if d == 1 else h[j] + sp[j]
                    else:
                        mw = T_xpx[i]
                else:
                    mc = c[j] if d == 1 else c[j] + sp[j]
                    mw = l[j] if d == 1 else h[j] + sp[j]
                uc += s * k * d * (mc - ep)
                uw += s * k * d * (mw - ep)
            uc = uc * fx[j]
            uw = uw * fx[j]
            if j < x and bal + uc > peak:
                peak = bal + uc
            ew = bal + uw
            if ew <= 0.0:
                wiped = True
                wipe_ix = j
                pnl[i] = -bal
                bal = 0.0
                maxdd = 1.0
                if peak > maxddu:
                    maxddu = peak
                break
            dd = (peak - ew) / peak
            if dd > maxdd:
                maxdd = dd
            if peak - ew > maxddu:
                maxddu = peak - ew
            if j < x:
                while bi < nb and bnd[bi] == j + 1:
                    eqb[bi] = bal + uc
                    bi += 1
        if wiped:
            break
        pl = 0.0
        for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
            pl += s * k * d * (T_xpx[i] - L_epx[q])
        pl = pl * fx[x]
        pnl[i] = pl
        bal += pl
        if bal > peak:
            peak = bal
        while bi < nb and bnd[bi] <= x + 1:
            eqb[bi] = bal
            bi += 1
    while bi < nb:
        eqb[bi] = bal
        bi += 1
    return steps, pnl, bal, maxdd, maxddu, wiped, wipe_ix, n_done, eqb


def turtle_account(m, p, bnd: np.ndarray, k: float, fxm: np.ndarray, fixed: bool, z_ms: int) -> dict:
    steps, pnl, bal, dd, ddu, wiped, wix, n_done, eqb = _turtle_kernel(
        m.t, m.h, m.l, m.c, m.sp, float(k), fxm, p.dir, p.eix, p.epx, p.xix, p.xpx, p.why, p.leg0, p.nleg, p.leix,
        p.lepx, bool(fixed), np.asarray(bnd[1:-1], np.int64), ACCOUNT, STEP_UP, UNIT_MAX)
    done = np.arange(len(steps)) < n_done
    sel = done & (steps > 0)
    inner = np.asarray(bnd[1:-1], np.int64)
    mt = (m.t[inner - 1] + 59) * 1000 if len(inner) else np.zeros(0, np.int64)
    mt = np.append(np.asarray(mt, np.int64), z_ms - 1)
    me = np.append(np.asarray(eqb, np.float64), float(bal))
    return dict(final=float(bal), ddu=float(ddu), ddp=float(dd) * 100.0, wiped=bool(wiped),
                wipe_ms=int(m.t[wix]) * 1000 if wiped else None, units=np.where(sel, steps, np.nan),
                pnl=np.where(sel, pnl, np.nan), done=sel, mt=mt, me=me)


# ───────────────────────────── the measures (§7) ─────────────────────────────

def eq_at(mt: np.ndarray, me: np.ndarray, T) -> np.ndarray:
    """Equity at each time in ``T`` (ms): the last mark before it; $2,000 before the first mark."""
    i = np.searchsorted(mt, np.asarray(T, np.int64), side="left") - 1
    return np.where(i >= 0, me[np.maximum(i, 0)], ACCOUNT)


def _bounds(a: str, z: str, months: int) -> np.ndarray:
    out, k = [], 0
    while True:
        t = pd.Timestamp(a, tz="UTC") + pd.DateOffset(months=months * k)
        if t >= pd.Timestamp(z, tz="UTC"):
            break
        out.append(t.value // 1_000_000)
        k += 1
    out.append(to_ms(z))
    return np.asarray(out, np.int64)


def _saturdays(a_ms: int, z_ms: int) -> np.ndarray:
    first = pd.Timestamp(a_ms, unit="ms", tz="UTC").normalize()
    first += pd.Timedelta(days=(5 - first.dayofweek) % 7)
    t = np.arange(first.value // 1_000_000, z_ms, WEEK_MS, dtype=np.int64)
    t = t[(t > a_ms) & (t < z_ms)]
    return np.concatenate([[a_ms], t, [z_ms]]).astype(np.int64)


def daily_series(mt, me, a_ms: int, z_ms: int) -> Tuple[np.ndarray, np.ndarray]:
    d0, d1 = a_ms // DAY_MS, (z_ms - 1) // DAY_MS
    days = np.arange(d0, d1 + 1, dtype=np.int64)
    return days, eq_at(mt, me, np.minimum((days + 1) * DAY_MS, z_ms))


def measures(r: dict, a: str, z: str, tr_pnl: np.ndarray, tr_closed: np.ndarray, tr_lots: np.ndarray,
             tr_side: np.ndarray) -> dict:
    a_ms, z_ms = to_ms(a), to_ms(z)
    weeks = (z_ms - a_ms) / WEEK_MS
    profit = r["final"] - ACCOUNT
    done = r["done"]
    cl = done & tr_closed
    pc = tr_pnl[cl]
    out = dict(final_equity=round(r["final"], 2), profit=round(profit, 2), profit_per_week=round(profit / weeks, 4),
               max_dd_usd=round(r["ddu"], 2), max_dd_pct=round(r["ddp"], 4),
               profit_per_dd=round(profit / max(r["ddu"], 1.0), 4), trades=int(cl.sum()),
               win_rate=round(float((pc > 0).mean()), 4) if len(pc) else np.nan,
               long_trades=int((cl & (tr_side > 0)).sum()), short_trades=int((cl & (tr_side < 0)).sum()),
               long_pnl=round(float(tr_pnl[cl & (tr_side > 0)].sum()), 2),
               short_pnl=round(float(tr_pnl[cl & (tr_side < 0)].sum()), 2),
               wiped=r["wiped"], wiped_at=_iso(r["wipe_ms"])[:10] if r["wiped"] else "",
               largest_lot=round(float(np.nanmax(tr_lots[done])), 2) if done.any() else 0.0, weeks=round(weeks, 2))
    for name, mo in (("months", 1), ("quarters", 3), ("halfyears", 6)):
        bnd = _bounds(a, z, mo)
        e = eq_at(r["mt"], r["me"], bnd)
        e[0] = ACCOUNT
        dif = np.diff(e)
        out[f"pos_{name}"] = int((dif > 0).sum())
        out[f"n_{name}"] = int(len(dif))
    wk = np.diff(eq_at(r["mt"], r["me"], _saturdays(a_ms, z_ms)))
    sd = float(np.std(wk, ddof=1)) if len(wk) > 1 else 0.0
    out["sharpe_weekly"] = round(float(np.mean(wk)) / sd * math.sqrt(52.18), 4) if sd > 0 else np.nan
    out["weeks_n"] = int(len(wk))
    return out


def trade_stats(t: pd.DataFrame) -> dict:
    """Holding time and nights over a set of one-unit trades (§7)."""
    if not len(t):
        return dict(n_trades=0)
    h = t["hold_h"].to_numpy(float)
    out = dict(n_trades=int(len(t)), avg_hold_h=round(float(h.mean()), 3), median_hold_h=round(float(np.median(h)), 3),
               nights_total=int(t["nights"].sum()), nights_per_trade=round(float(t["nights"].mean()), 4),
               share_overnight=round(float((t["nights"] >= 1).mean()), 4))
    for s, nm in ((1, "long"), (-1, "short")):
        g = t[t["side"] == s]
        out[f"{nm}_n"] = int(len(g))
        out[f"{nm}_avg_hold_h"] = round(float(g["hold_h"].mean()), 3) if len(g) else np.nan
        out[f"{nm}_share_overnight"] = round(float((g["nights"] >= 1).mean()), 4) if len(g) else np.nan
        out[f"{nm}_nights_total"] = int(g["nights"].sum()) if len(g) else 0
    return out


# ───────────────────────────── the engine runs (§6.1) ─────────────────────────────

def basket_cfg(sym: str, key: str, a: str, z: str, per_unit: bool = True, lot: float = 0.01,
               cap_price: Optional[float] = None):
    _, ov, capref = BASKETS[key]
    cfg = E.live_config(sym, start=a, end=z).replace(**ov)
    if sym not in BASE_SYMBOLS:
        cfg = cfg.replace(**GOLD_WINDOW)
    if capref is not None:
        if sym == capref[0]:
            cap = float(ov["vol_cap_usd_per_unit"]) * lot / 0.01          # the design's own $12 per 0.01 lot
        else:
            cap = float(cap_price) * SYMBOLS[sym].contract_size * lot
        cfg = cfg.replace(vol_cap_usd_per_unit=cap)
    if per_unit:
        cfg = cfg.replace(fixed_units=1, mtqty=0.01, initial_balance=BIG)
    else:
        cfg = cfg.replace(mtqty=lot)
    return cfg


def _basket_trades(sym: str, key: str, period: str, d: dict, accs: Dict[str, dict], L: float) -> pd.DataFrame:
    n = len(d["o"])
    t = pd.DataFrame({"symbol": sym, "design": key, "period": period, "n": np.arange(n),
                      "open_time": [_iso(x) for x in d["o"]], "close_time": [_iso(x) for x in d["c"]],
                      "side": d["side"], "legs": d["npos"], "reason": d["reason"], "closed": d["closed"],
                      "lots_1u": d["lots"], "pnl_1u_quote": d["pnl"], "fx_close": d["fx_close"],
                      "pnl_1u_usd": d["pnl_usd"], "mae_1u_usd": d["mae_usd"],
                      "hold_h": (d["c"] - d["o"]) / 3.6e6, "nights": d["nights"], "nights_w": d["nights_w"],
                      "lot_nights_w_1u": d["lot_nights"]})
    for name, r in accs.items():
        t[f"units_{name}"] = np.where(r["done"] | (~d["closed"] & (r["units"] > 0)), r["units"], np.nan)
        t[f"pnl_{name}"] = r["pnl"]
    t["lot_per_unit_b"] = L
    return t


def run_half(sym: str, period: str, keys: Optional[Sequence[str]] = None) -> None:
    """The basket designs on one half: one-unit runs and the three USD replays (§6.1). Saves runs/<SYM>/parts/."""
    a, z = PERIODS[period]
    a_ms, z_ms = to_ms(a), to_ms(z)
    sp = load_specs(sym)
    L = float(sp["L"])
    keys = list(keys or ([k for k in BASE[sym] if k in BASKETS] if sym in BASE_SYMBOLS else BASKETS))
    t0 = time.time()
    prep = fast.prepare(sym, a, z, TFS, mode="sec")
    fx = FX(sym)
    log(f"{sym} {period}: {prep.n_rows:,} per-second rows ready ({time.time() - t0:.0f}s)")
    rows, trades, daily, units = [], [], [], {}
    for key in keys:
        cfg = basket_cfg(sym, key, a, z, per_unit=True, cap_price=sp["caps"].get(key))
        t1 = time.time()
        res = fast.run(cfg, prep)
        rt = time.time() - t1
        d = unit_data(res, sym, a_ms, z_ms, fx)
        accs = {}
        for name, rule, lf in ACCOUNTS:
            lotf = lot_factor(lf, L)
            r = replay(d, rule, lotf)
            accs[name] = r
            lots = r["units"] * d["lots"] * lotf if rule else d["lots"] * lotf
            met = measures(r, a, z, r["pnl"], d["closed"], np.asarray(lots, float), d["side"])
            rows.append(dict(symbol=sym, role="base" if sym in BASE_SYMBOLS else "new", design=key,
                             design_name=DESIGN_NAME[key], period=period, account=name, start=a, end=z,
                             lot_per_unit=round(0.01 * lotf, 4), engine="ticks (sec)", **met,
                             cap_price=float(cfg.vol_cap_usd_per_unit / (SYMBOLS[sym].contract_size * 0.01))
                             if cfg.vol_cap_usd_per_unit else 0.0, runtime_s=round(rt, 1)))
            days, ev = daily_series(r["mt"], r["me"], a_ms, z_ms)
            if name == "stream":
                dd = pd.DataFrame({"symbol": sym, "design": key, "period": period, "day": days})
            dd[f"eq_{name}"] = ev
        daily.append(dd)
        t = _basket_trades(sym, key, period, d, accs, L)
        trades.append(t)
        units[key] = dict(o=d["o"], c=d["c"], side=d["side"], closed=d["closed"], lots=d["lots"],
                          **{f"final_{n}": accs[n]["final"] for n in accs}, **{f"ddp_{n}": accs[n]["ddp"] for n in accs},
                          **{f"wiped_{n}": accs[n]["wiped"] for n in accs})
        ra = accs["a"]
        log(f"  {sym} {period} {key:9s} {rt:6.0f}s  baskets {len(d['o']):4d}  stream {accs['stream']['final']:9.2f}  "
            f"(a) {ra['final']:9.2f} DD {ra['ddp']:5.1f}%  (b, L={L:.2f}) {accs['b']['final']:10.2f} "
            f"DD {accs['b']['ddp']:5.1f}%{'  WIPED' if accs['b']['wiped'] else ''}")
        del res
        gc.collect()
    d_out = RUNS / sym / "parts"
    d_out.mkdir(parents=True, exist_ok=True)
    with open(d_out / f"half_{period}.pkl", "wb") as fh:
        pickle.dump(dict(rows=rows, trades=pd.concat(trades, ignore_index=True), daily=pd.concat(daily, ignore_index=True),
                         units=units), fh)
    (RUNS / sym / f".half_{period}.done").write_text(datetime.now(timezone.utc).isoformat())
    log(f"{sym} {period}: done in {time.time() - t0:.0f}s")


# ───────────────────────────── the Turtles (§4, §6.2) ─────────────────────────────

def turtle_market(sym: str):
    if sym == "BTCUSDm":
        return X.load_market(sym, earliest=F.HISTORY_FROM[sym], end=DATA_END)
    m1 = store.load_m1(sym, TURTLE_HISTORY, DATA_END)
    spec = SYMBOLS[sym]
    return B.SpecMarket(sym, m1, spec.contract_size, spec.digits)


def run_turtles(sym: str, keys: Sequence[str] = ("ts2", "ts1")) -> None:
    t0 = time.time()
    sp = load_specs(sym)
    L = float(sp["L"])
    m = turtle_market(sym)
    sig = X.bot_signals(m)
    fx = FX(sym)
    fxm = fx.at_s(m.t)
    ones = np.ones(len(m.t))
    contract = SYMBOLS[sym].contract_size
    log(f"{sym}: {len(m):,} M1 bars {_iso(m.t[0] * 1000)[:10]} .. {_iso(m.t[-1] * 1000)[:10]}, votes ready "
        f"({time.time() - t0:.0f}s)")
    rows, trades, daily, checks = [], [], [], []
    usdcad = sym == "USDCADm"
    for key in keys:
        plan = X.filtered(X.turtle(m, TURTLES[key][1]).plan, m, sig.votes_at)
        for period in TURTLE_PERIODS:
            a, z = PERIODS[period]
            a_ms, z_ms = to_ms(a), to_ms(z)
            a_ix, z_ix = int(np.searchsorted(m.t, a_ms // 1000, "left")), int(np.searchsorted(m.t, z_ms // 1000, "left"))
            p = X.run_path(m, plan, a_ix, z_ix)
            bnd = F._day_bounds(m, a_ix, z_ix)
            nt = len(p.dir)
            xi = np.minimum(p.xix, len(m) - 1)
            o_ms, c_ms = m.t[p.eix] * 1000, m.t[xi] * 1000
            closed = p.why != 4
            nn, nw = nights(o_ms, c_ms, usdcad)
            legn = np.zeros(nt)
            for i in range(nt):
                q = np.arange(p.leg0[i], p.leg0[i] + p.nleg[i])
                legn[i] = nights(m.t[p.leix[q]] * 1000, np.full(len(q), c_ms[i]), usdcad)[1].sum()
            accs = {}
            for name, rule, lf in ACCOUNTS:
                lotf = lot_factor(lf, L)
                r = turtle_account(m, p, bnd, contract * 0.01 * lotf, fxm, rule == 0, z_ms)
                accs[name] = r
                lots = np.nan_to_num(r["units"]) * p.nleg * 0.01 * lotf
                met = measures(r, a, z, np.nan_to_num(r["pnl"]), closed, lots.astype(float), p.dir)
                rows.append(dict(symbol=sym, role="base" if sym in BASE_SYMBOLS else "new", design=key,
                                 design_name=DESIGN_NAME[key], period=period, account=name, start=a, end=z,
                                 lot_per_unit=round(0.01 * lotf, 4), engine="M1 bars", **met, cap_price=0.0,
                                 runtime_s=np.nan))
                days, ev = daily_series(r["mt"], r["me"], a_ms, z_ms)
                if name == "stream":
                    dd = pd.DataFrame({"symbol": sym, "design": key, "period": period, "day": days})
                dd[f"eq_{name}"] = ev
            daily.append(dd)
            fxx = fxm[xi]
            t = pd.DataFrame({"symbol": sym, "design": key, "period": period, "n": np.arange(nt),
                              "open_time": [_iso(x) for x in o_ms], "close_time": [_iso(x) for x in c_ms],
                              "side": p.dir, "legs": p.nleg, "reason": [X.WHY_NAMES.get(int(w), str(w)) for w in p.why],
                              "closed": closed, "lots_1u": p.nleg * 0.01, "entry": p.epx, "exit": p.xpx,
                              "fx_close": fxx, "hold_h": (c_ms - o_ms) / 3.6e6, "nights": nn, "nights_w": nw,
                              "lot_nights_w_1u": legn * 0.01})
            for name, r in accs.items():
                t[f"units_{name}"] = r["units"]
                t[f"pnl_{name}"] = r["pnl"]
            t["pnl_1u_usd"] = accs["stream"]["pnl"]
            t["lot_per_unit_b"] = L
            trades.append(t)
            if sym in CHECK_SYMBOLS + ("BTCUSDm",):
                ref = X.account(m, p, X.BOT, bnd)
                mine = turtle_account(m, p, bnd, m.k, ones, False, z_ms)
                rp = ref.trades_pnl
                mp = mine["pnl"][mine["done"]]
                same_tr = len(rp) == len(mp) and bool(np.all(np.round(rp, 2) == np.round(mp, 2)))
                ok = (round(ref.final, 2) == round(mine["final"], 2) and same_tr
                      and abs(ref.max_dd * 100.0 - mine["ddp"]) < 1e-9 and ref.wiped == mine["wiped"])
                checks.append(dict(symbol=sym, design=key, period=period, external_final=round(ref.final, 2),
                                   new_final=round(mine["final"], 2), external_dd_pct=round(ref.max_dd * 100, 6),
                                   new_dd_pct=round(mine["ddp"], 6), trades=len(rp), same_trades=same_tr, ok=bool(ok)))
            log(f"  {sym} {key} {period:4s} trades {int(closed.sum()):3d}  stream {accs['stream']['final']:9.2f}  "
                f"(a) {accs['a']['final']:9.2f} DD {accs['a']['ddp']:5.1f}%  (b) {accs['b']['final']:10.2f} "
                f"DD {accs['b']['ddp']:5.1f}%{'  WIPED' if accs['b']['wiped'] else ''}")
    d_out = RUNS / sym / "parts"
    d_out.mkdir(parents=True, exist_ok=True)
    with open(d_out / "turtles.pkl", "wb") as fh:
        pickle.dump(dict(rows=rows, trades=pd.concat(trades, ignore_index=True),
                         daily=pd.concat(daily, ignore_index=True)), fh)
    if checks:
        CHECKS.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(checks).to_csv(CHECKS / f"turtle_fx1_{sym}.csv", index=False)
        log(f"{sym}: Turtle account with FX = 1 vs external.account: "
            f"{'all equal' if all(c['ok'] for c in checks) else 'MISMATCH'}")
    (RUNS / sym / ".turtles.done").write_text(datetime.now(timezone.utc).isoformat())
    log(f"{sym}: Turtles done in {time.time() - t0:.0f}s")


# ───────────────────────────── finalize ─────────────────────────────

def finalize(sym: str) -> None:
    parts = RUNS / sym / "parts"
    rows, trades, daily = [], [], []
    for p in sorted(parts.glob("*.pkl")):
        if p.name.startswith("direct_"):
            continue
        with open(p, "rb") as fh:
            d = pickle.load(fh)
        rows += d["rows"]
        trades.append(d["trades"])
        daily.append(d["daily"])
    if not rows:
        raise RuntimeError(f"{sym}: nothing to finalize")
    # DEVIATIONS D.4: if the replay error is material, the direct runs are the (a) and (b) of a USD-quoted symbol
    mf = CHECKS / "material.json"
    material = bool(json.loads(mf.read_text())["material"]) if mf.exists() else False
    direct = sorted(parts.glob("direct_*.pkl"))
    drows, dtrades, ddaily = [], [], []
    for p in direct:
        with open(p, "rb") as fh:
            d = pickle.load(fh)
        drows += d["rows"]
        dtrades.append(d["trades"])
        ddaily.append(d["daily"])
    use_direct = material and bool(direct)
    for r in rows:
        if r["account"] in ("a", "b") and r["engine"].startswith("ticks"):
            if use_direct:
                r["account"] = r["account"] + "_replay"
            elif material:
                r["engine"] = "ticks (sec), replay (flagged: DEVIATIONS D.4)"
    for r in drows:
        if not use_direct:
            r["account"] = r["account"] + "_direct"
    rows += drows
    if ddaily:
        ren = (lambda c: c + "_replay") if use_direct else (lambda c: c)
        dsuf = (lambda c: c) if use_direct else (lambda c: c + "_direct")
        dd = pd.concat(ddaily, ignore_index=True).rename(columns={"eq_a": dsuf("eq_a"), "eq_b": dsuf("eq_b")})
        merged = []
        for frame in daily:
            fr = frame.copy()
            if "eq_a" in fr.columns and fr["design"].iloc[0] in BASKETS:
                fr = fr.rename(columns={"eq_a": ren("eq_a"), "eq_b": ren("eq_b")})
                fr = fr.merge(dd, on=["symbol", "design", "period", "day"], how="left")
            merged.append(fr)
        daily = merged
        pd.concat(dtrades, ignore_index=True).to_csv(RUNS / sym / "trades_direct.csv.gz", index=False)
    met = pd.DataFrame(rows)
    met["design_order"] = met["design"].map({k: i for i, k in enumerate(DESIGN_ORDER)})
    met = met.sort_values(["design_order", "period", "account"]).drop(columns="design_order")
    met.to_csv(RUNS / sym / "metrics.csv", index=False)
    tr = pd.concat(trades, ignore_index=True)
    tr.to_csv(RUNS / sym / "trades.csv.gz", index=False)
    dl = pd.concat(daily, ignore_index=True)
    dl.insert(4, "date", pd.to_datetime(dl["day"] * DAY_MS, unit="ms").dt.strftime("%Y-%m-%d"))
    dl.drop(columns="day").to_csv(RUNS / sym / "daily.csv.gz", index=False)
    stats = []
    for key, g in tr.groupby("design", sort=False):
        own = ("sel", "conf") if key in BASKETS else ("tsel", "conf")
        for scope, sel in (("selection + confirmation", g["period"].isin(own)),) + tuple(
                (pp, g["period"] == pp) for pp in sorted(g["period"].unique())):
            stats.append(dict(symbol=sym, design=key, scope=scope, **trade_stats(g[sel])))
    pd.DataFrame(stats).to_csv(RUNS / sym / "trade_stats.csv", index=False)
    if sym in NEW_SYMBOLS and sym not in CHECK_SYMBOLS:
        freed = trim_sec(sym, "2021-11-01", "2026-12-01")
        log(f"{sym}: freed {freed / 1e9:.2f} GB of per-second data (2021-11 .. 2026-11)")
    (RUNS / sym / ".finalize.done").write_text(datetime.now(timezone.utc).isoformat())
    log(f"{sym}: finalized ({len(met)} account rows, {len(tr)} trades)")


# ───────────────────────────── data: download, build, gate, specs (§3, §10.3) ─────────────────────────────

MONTHS = exness.month_range(date(2017, 11, 1), date(2026, 11, 1))           # 109


def head_sizes(sym: str) -> Dict[Tuple[int, int], int]:
    out = {}
    for line in HEADS.read_text().splitlines():
        p = line.split()
        if len(p) == 4 and p[0] == sym and p[2] == "200":
            y, m = p[1].split("_")
            out[(int(y), int(m))] = int(p[3])
    return out


def new_data_bytes() -> int:
    tot = 0
    for s in NEW_SYMBOLS:
        for d in (store.DEFAULT_STORE_DIR / s, store.DEFAULT_RAW_DIR / s):
            if d.exists():
                tot += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
    return tot


def disk_free() -> int:
    return shutil.disk_usage(store.DEFAULT_STORE_DIR).free


def trim_sec(sym: str, a: str, z: str) -> int:
    """Delete the per-second files of the months in [a, z) (M1 bars and meta stay)."""
    freed = 0
    ya, yz = pd.Timestamp(a), pd.Timestamp(z)
    for (y, m) in MONTHS:
        if not (ya <= pd.Timestamp(y, m, 1) < yz):
            continue
        p = store.month_dir(store.DEFAULT_STORE_DIR, sym, y, m) / "sec.npz"
        if p.exists():
            freed += p.stat().st_size
            p.unlink()
    return freed


def decimals_check(t: np.ndarray, bid: np.ndarray, ask: np.ndarray, digits: int) -> Tuple[bool, bool]:
    """(no price has more than ``digits`` decimals, some price uses the last one)."""
    sc = 10.0 ** digits
    ok, uses = True, False
    for x in (bid, ask):
        v = x * sc
        r = np.rint(v)
        ok &= bool(np.all(np.abs(v - r) <= 1e-6 * np.maximum(1.0, np.abs(v) * 1e-9)))
        uses |= bool(np.any(np.mod(r, 10) != 0))
    return ok, uses


def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo = (h + l - 7 * m + 114) // 31
    return date(y, mo, ((h + l - 7 * m + 114) % 31) + 1)


def _epoch_day(d: date) -> int:
    return (d - date(1970, 1, 1)).days


HOLIDAYS = sorted({_epoch_day(date(y, 12, 25)) for y in range(2016, 2028)} | {_epoch_day(date(y, 1, 1)) for y in range(2016, 2028)}
                  | {_epoch_day(_easter(y)) - 2 for y in range(2016, 2028)})
XMAS_NY = sorted({_epoch_day(date(y, 12, 25)) for y in range(2016, 2028)} | {_epoch_day(date(y, 1, 1)) for y in range(2016, 2028)})
MONDAY0_S = 4 * 86400                 # 1970-01-05 was a Monday


def gate_span(sym: str, a: str, z: str) -> dict:
    """§3.4 on one span, month by month from the per-second files (reads only the data)."""
    a_s, z_s = to_ms(a) // 1000, to_ms(z) // 1000
    digits = SYMBOLS[sym].digits
    months = exness.month_range(pd.Timestamp(a).date(), (pd.Timestamp(z) - pd.Timedelta(seconds=1)).date())
    missing, dec_bad, uses_all = [], [], False
    sil, prev = [], a_s
    wk_counts: Dict[int, int] = {}
    for (y, mo) in months:
        md = store.month_dir(store.DEFAULT_STORE_DIR, sym, y, mo)
        if not (md / "meta.json").exists() or not (md / "sec.npz").exists():
            missing.append(f"{y}-{mo:02d}")
            continue
        with np.load(md / "sec.npz") as zf:
            t, bid, ask = zf["t_ms"], zf["bid"], zf["ask"]
        keep = (t >= a_s * 1000) & (t < z_s * 1000)
        t, bid, ask = t[keep], bid[keep], ask[keep]
        if len(t) == 0:
            missing.append(f"{y}-{mo:02d}")
            continue
        ts = t // 1000
        allt = np.concatenate([[prev], ts])
        for i in np.flatnonzero(np.diff(allt) >= 8 * 3600):
            sil.append((int(allt[i]), int(allt[i + 1])))
        prev = int(ts[-1])
        us = np.unique(ts)
        rel = us - MONDAY0_S
        wk, inw = rel // (7 * 86400), rel % (7 * 86400)
        wk = wk[inw < 5 * 86400]
        if len(wk):
            ids, cnt = np.unique(wk, return_counts=True)
            for i, c in zip(ids.tolist(), cnt.tolist()):
                wk_counts[i] = wk_counts.get(i, 0) + c
        ok, uses = decimals_check(t, bid, ask, digits)
        if not ok:
            dec_bad.append(f"{y}-{mo:02d}")
        uses_all |= uses
    if z_s - prev >= 8 * 3600:
        sil.append((prev, z_s))
    bad_sil = []
    for s, e in sil:
        wd = ((s // 86400) + 3) % 7
        in_win = wd <= 3 or (wd == 4 and s % 86400 < 18 * 3600)
        d0, d1 = s // 86400, (e - 1) // 86400
        covers = any(d0 <= hd <= d1 for hd in HOLIDAYS)
        if in_win and not covers:
            bad_sil.append(dict(start=_iso(s * 1000), end=_iso(e * 1000), hours=round((e - s) / 3600, 2)))
    w_first = -(-(a_s - MONDAY0_S) // (7 * 86400))
    w_last = (z_s - MONDAY0_S - 5 * 86400) // (7 * 86400)
    full = list(range(int(w_first), int(w_last) + 1))
    counts = np.array([wk_counts.get(w, 0) for w in full], np.int64)
    med = float(np.median(counts)) if len(counts) else 0.0
    exempt = {(hd * 86400 - MONDAY0_S) // (7 * 86400) for hd in XMAS_NY}
    thin = [dict(week_of=_iso((MONDAY0_S + w * 7 * 86400) * 1000)[:10], seconds=int(c))
            for w, c in zip(full, counts) if c < 0.25 * med and w not in exempt]
    passed = not missing and not bad_sil and not thin and not dec_bad and uses_all
    return dict(span=[a, z], passed=bool(passed), months_expected=len(months), missing_months=missing,
                silences_8h=len(sil), bad_silences=bad_sil, full_weeks=len(full), median_week_seconds=med,
                thin_weeks=thin, decimals_bad_months=dec_bad, decimals_use_all=bool(uses_all),
                all_silences_8h=[dict(start=_iso(s * 1000), hours=round((e - s) / 3600, 2)) for s, e in sil])


def regate(sym: str) -> None:
    """DEVIATIONS E: a flagged silence counts only by its minutes in which gold (XAUUSDm) has an M1 bar."""
    qf = QUAL / f"{sym}.json"
    q = json.loads(qf.read_text())
    for span, g in q["gate"].items():
        lit = g.get("bad_silences_literal", g["bad_silences"])
        g["bad_silences_literal"] = lit
        applied = []
        for b in lit:
            a_ms, z_ms = to_ms(b["start"]), to_ms(b["end"])
            gm = store.load_m1("XAUUSDm", a_ms, z_ms)
            gt = np.asarray(gm["t"], np.int64) if gm else np.zeros(0, np.int64)
            own_h = int(((gt * 1000 >= a_ms) & (gt * 1000 < z_ms)).sum()) / 60.0
            b = dict(b, own_hours=round(own_h, 2))
            if own_h >= 8.0:
                applied.append(b)
            else:
                b["exempt"] = "shared with gold's feed (DEVIATIONS E)"
            lit[lit.index(next(x for x in lit if x["start"] == b["start"]))] = b
        g["bad_silences"] = applied
        g["passed"] = bool(not g["missing_months"] and not applied and not g["thin_weeks"]
                           and not g["decimals_bad_months"] and g["decimals_use_all"] and not g.get("missing_heads"))
        g["rule"] = "DEVIATIONS E"
    qf.write_text(json.dumps(q, indent=1, default=str))
    sp = json.loads(SPECS_JSON.read_text())
    if sym in sp:
        e = sp[sym]["gate"]
        for span, g in q["gate"].items():
            e[span].update(passed=g["passed"], bad_silences=len(g["bad_silences"]),
                           bad_silences_literal=len(g["bad_silences_literal"]), rule="DEVIATIONS E")
        _update_json(SPECS_JSON, sym, sp[sym])
    log(f"{sym}: gate (DEVIATIONS E) turtle span {'PASS' if q['gate']['turtle']['passed'] else 'FAIL'}, basket span "
        f"{'PASS' if q['gate']['basket']['passed'] else 'FAIL'}; flagged silences "
        + ", ".join(f"{x['start'][:16]} {x['hours']}h own {x['own_hours']}h" for g in q["gate"].values()
                    for x in g["bad_silences_literal"]))


QCHUNKS = (("2017-11-01", "2018-01-01"), ("2018-01-01", "2019-01-01"), ("2019-01-01", "2020-01-01"),
           ("2020-01-01", "2021-01-01"), ("2021-01-01", "2021-05-01"), ("2021-05-01", "2022-01-01"),
           ("2022-01-01", "2023-01-01"), ("2023-01-01", "2024-01-01"), ("2024-01-01", "2024-05-13"),
           ("2024-05-13", "2025-01-01"), ("2025-01-01", "2026-01-01"), ("2026-01-01", "2026-11-13"))


def h1_vol_median(sym: str) -> float:
    """med(S) of §4: the engine's H1 volatility unit, from 2021-05-01, over the H1 bars closing in the selection half."""
    m1 = store.load_m1(sym, BASKET_HISTORY, SPLIT)
    h1 = store.resample_bars(m1, 3600)
    u = vol_array(np.ascontiguousarray(h1["c"], np.float64), 24)
    tc = h1["t"] + 3600
    sel = (tc >= to_ms(PERIODS["sel"][0]) // 1000) & (tc < to_ms(SPLIT) // 1000)
    return float(np.median(u[sel]))


def daily_move_median(sym: str) -> float:
    """G / M(S) of §5: median |D1 close change| x contract x 0.01 in USD over the D1 bars closing in the selection half."""
    m1 = store.load_m1(sym, BASKET_HISTORY, SPLIT)
    spec = SYMBOLS[sym]
    m = B.SpecMarket(sym, m1, spec.contract_size, spec.digits)
    d1 = X.day_bars(m)
    mv = np.abs(np.diff(d1.c)) * spec.contract_size * 0.01
    usd = mv * FX(sym).at_s(m.t[d1.i1[1:]])
    tc = d1.tc[1:]
    sel = (tc >= to_ms(PERIODS["sel"][0]) // 1000) & (tc < to_ms(SPLIT) // 1000)
    return float(np.median(usd[sel]))


def lot_rule(G: float, M: float) -> float:
    n = math.floor(G / M + 0.5 + 1e-12)
    return round(max(1, n) * 0.01, 2)


def fetch(sym: str) -> None:
    """§10.3 steps 1 - 6 for one symbol."""
    t0 = time.time()
    raw = store.DEFAULT_RAW_DIR
    sizes = head_sizes(sym)
    missing_heads = [f"{y}-{m:02d}" for (y, m) in MONTHS if (y, m) not in sizes]
    batch = sum(sizes.values())
    free = disk_free()
    log(f"{sym}: df free {free / 1e9:.1f} GB, batch {batch / 1e9:.2f} GB, new market data held {new_data_bytes() / 1e9:.2f} GB")
    if free - batch < 15e9:
        raise RuntimeError(f"disk: {free / 1e9:.1f} GB free - {batch / 1e9:.2f} GB would fall below 15 GB")
    todo = [(y, m) for (y, m) in MONTHS
            if not (store.month_dir(store.DEFAULT_STORE_DIR, sym, y, m) / "meta.json").exists()]
    built = 0

    def dl(ym):
        y, m = ym
        mf = exness.MonthFile(sym, y, m)
        return ym, exness.download_month(mf, raw, retries=6, log=lambda s: None)

    first_checked = (store.month_dir(store.DEFAULT_STORE_DIR, sym, 2017, 11) / "meta.json").exists()
    with ThreadPoolExecutor(4) as ex:
        futs = [ex.submit(dl, ym) for ym in todo]
        for fu in as_completed(futs):
            (y, m), path = fu.result()
            if path is None:
                raise RuntimeError(f"{sym} {y}-{m:02d}: not published")
            meta = store.build_month(sym, y, m, raw, store.DEFAULT_STORE_DIR, keep_ticks=False, log=lambda s: None)
            if meta is None:
                raise RuntimeError(f"{sym} {y}-{m:02d}: build failed")
            path.unlink()
            mp = exness.MonthFile(sym, y, m).meta_path(raw)
            if mp.exists():
                mp.unlink()
            built += 1
            if built % 20 == 0:
                log(f"  {sym}: {built}/{len(todo)} months downloaded (CRC checked), built, zips deleted "
                    f"({time.time() - t0:.0f}s)")
    if not first_checked:
        md = store.month_dir(store.DEFAULT_STORE_DIR, sym, 2017, 11)
        with np.load(md / "sec.npz") as zf:
            ok, uses = decimals_check(zf["t_ms"], zf["bid"], zf["ask"], SYMBOLS[sym].digits)
        if not (ok and uses):
            raise RuntimeError(f"{sym}: the first month's prices contradict {SYMBOLS[sym].digits} decimals "
                               f"(at most: {ok}, all used: {uses})")
    rd = raw / sym
    if rd.exists() and not any(rd.iterdir()):
        rd.rmdir()
    log(f"{sym}: {len(todo)} months built in {time.time() - t0:.0f}s; data gate")
    t1 = time.time()
    gates = {"turtle": gate_span(sym, TURTLE_HISTORY, SPLIT), "basket": gate_span(sym, BASKET_HISTORY, DATA_END)}
    if missing_heads:
        for g in gates.values():
            g["passed"] = False
            g["missing_heads"] = missing_heads
    reports = []
    for a, z in QCHUNKS:
        try:
            q = quality.quality_report(sym, a, z)
            q.pop("spread_by_hour_utc", None)
            reports.append(q)
        except Exception as e:                       # noqa: BLE001 - recorded, the gate decides
            reports.append({"window": [a, z], "error": str(e)})
    QUAL.mkdir(parents=True, exist_ok=True)
    (QUAL / f"{sym}.json").write_text(json.dumps(dict(symbol=sym, gate=gates, quality_report_chunks=reports,
                                                      written=datetime.now(timezone.utc).isoformat()),
                                                 indent=1, default=str))
    log(f"{sym}: gate turtle span {'PASS' if gates['turtle']['passed'] else 'FAIL'}, basket span "
        f"{'PASS' if gates['basket']['passed'] else 'FAIL'} ({time.time() - t1:.0f}s)")
    if sym in CHECK_SYMBOLS:                     # the check symbols keep their full store until the check step
        log(f"{sym}: full per-second store kept (check symbol)")
    else:
        freed = trim_sec(sym, "2017-11-01", "2021-11-01")
        log(f"{sym}: freed {freed / 1e9:.2f} GB (per-second files before 2021-11)")
    spec = SYMBOLS[sym]
    medS, medX, medB = h1_vol_median(sym), h1_vol_median("XAUUSDm"), h1_vol_median("BTCUSDm")
    G, M = daily_move_median("XAUUSDm"), daily_move_median(sym)
    entry = dict(symbol=sym, written=datetime.now(timezone.utc).isoformat(),
                 spec=dict(contract_size=spec.contract_size, digits=spec.digits, point=10.0 ** -spec.digits,
                           quote=spec.quote, min_lot=spec.min_lot, lot_step=spec.lot_step, leverage=2000.0,
                           data_hole_s=spec.data_hole_s),
                 conversion=dict(zip(("pair", "how"), CONVERSION[spec.quote])) if CONVERSION[spec.quote] else "x 1",
                 med_h1_vol=medS, med_h1_vol_XAUUSDm=medX, med_h1_vol_BTCUSDm=medB,
                 caps={"gtop2": 12.0 * medS / medX, "btop2": 1200.0 * medS / medB},
                 G_usd=G, M_usd=M, L_raw=0.01 * G / M, L=lot_rule(G, M),
                 gate={k: dict(passed=v["passed"], missing_months=v["missing_months"], bad_silences=len(v["bad_silences"]),
                               thin_weeks=len(v["thin_weeks"]), decimals_bad_months=v["decimals_bad_months"],
                               decimals_use_all=v["decimals_use_all"]) for k, v in gates.items()})
    _update_json(SPECS_JSON, sym, entry)
    regate(sym)
    (RUNS / sym).mkdir(parents=True, exist_ok=True)
    (RUNS / sym / ".fetch.done").write_text(datetime.now(timezone.utc).isoformat())
    log(f"{sym}: specs written: med {medS:.6g}, caps gold {entry['caps']['gtop2']:.6g} / BTC {entry['caps']['btop2']:.6g}, "
        f"G {G:.4f}, M {M:.4f}, L {entry['L']:.2f}; fetch done in {time.time() - t0:.0f}s")


# ───────────────────────────── G3 (§10.3) ─────────────────────────────

USD_QUOTED = ("XAGUSDm", "EURUSDm", "GBPUSDm", "AUDUSDm", "NZDUSDm") + BASE_SYMBOLS
SCOPE = RUN_ORDER[:8]                       # DEVIATIONS C: silver and the 7 majors in this step


def run_g3(sym: str, period: str) -> None:
    """G3 on a check symbol; on any other USD-quoted symbol the same direct runs (DEVIATIONS D.4). The direct (a) and
    (b) accounts are saved as parts/direct_<period>.pkl either way."""
    a, z = PERIODS[period]
    a_ms, z_ms = to_ms(a), to_ms(z)
    sp = load_specs(sym)
    L = float(sp["L"])
    with open(RUNS / sym / "parts" / f"half_{period}.pkl", "rb") as fh:
        part = pickle.load(fh)
    keys = [k for k in BASE[sym] if k in BASKETS] if sym in BASE_SYMBOLS else list(BASKETS)
    prep = fast.prepare(sym, a, z, TFS, mode="sec")
    fx = FX(sym)
    out, rows, trades, daily = [], [], [], []
    for key in keys:
        u = part["units"][key]
        cl = u["closed"]
        dd = None
        for acc, lot in (("a", 0.01), ("b", L)):
            cfg = basket_cfg(sym, key, a, z, per_unit=False, lot=lot, cap_price=sp["caps"].get(key))
            t1 = time.time()
            res = fast.run(cfg, prep)
            rt = time.time() - t1
            b = res.baskets
            o, c = _ms(b["open_time"]), _ms(b["close_time"])
            side = np.where(b["side"].to_numpy() == "BUY", 1, -1)
            uo, uc, us = u["o"][cl], u["c"][cl], u["side"][cl]
            n = min(len(o), len(uo))
            neq = np.flatnonzero((o[:n] != uo[:n]) | (c[:n] != uc[:n]) | (side[:n] != us[:n]))
            first = int(neq[0]) if len(neq) else (n if len(o) != len(uo) else -1)
            same = first < 0
            open_end = int(res.scalars["open_positions_at_end"] > 0)
            same &= open_end == int((~cl).sum())
            f = res.fills
            bound = 0.01 * float(f.loc[f["action"].isin(["open", "add"]), "lots"].sum() / 0.01)
            fe = float(res.scalars["final_equity"])
            rf = u[f"final_{acc}"]
            ddd = float(res.scalars["max_drawdown_pct"])
            rdd = u[f"ddp_{acc}"]
            wiped_d = bool(res.scalars["stopped_out"])
            ok = abs(fe - rf) <= bound + 1e-6 and abs(ddd - rdd) <= 1.0 and wiped_d == bool(u[f"wiped_{acc}"])
            # the direct account, measured as §6.1 on its own marks (FX = 1 for a USD-quoted symbol)
            d = unit_data(res, sym, a_ms, z_ms, fx)
            r = replay(d, 0, 1.0)
            met = measures(r, a, z, r["pnl"], d["closed"], d["lots"], d["side"])
            rows.append(dict(symbol=sym, role="base" if sym in BASE_SYMBOLS else "new", design=key,
                             design_name=DESIGN_NAME[key], period=period, account=acc, start=a, end=z,
                             lot_per_unit=round(lot, 4), engine="ticks (sec), direct", **met,
                             cap_price=float(cfg.vol_cap_usd_per_unit / (SYMBOLS[sym].contract_size * lot))
                             if cfg.vol_cap_usd_per_unit else 0.0, runtime_s=round(rt, 1)))
            days, ev = daily_series(r["mt"], r["me"], a_ms, z_ms)
            if dd is None:
                dd = pd.DataFrame({"symbol": sym, "design": key, "period": period, "day": days})
            dd[f"eq_{acc}"] = ev
            trades.append(pd.DataFrame({"symbol": sym, "design": key, "period": period, "account": acc,
                                        "n": np.arange(len(d["o"])), "open_time": [_iso(x) for x in d["o"]],
                                        "close_time": [_iso(x) for x in d["c"]], "side": d["side"], "legs": d["npos"],
                                        "reason": d["reason"], "closed": d["closed"], "lots": d["lots"],
                                        "pnl_usd": d["pnl_usd"], "mae_usd": d["mae_usd"]}))
            out.append(dict(symbol=sym, period=period, design=key, account=acc, lot=lot, direct_final=round(fe, 2),
                            replay_final=round(rf, 2), diff=round(fe - rf, 4), bound=round(bound, 2),
                            diff_pct_of_profit=round(100 * (fe - rf) / (rf - ACCOUNT), 4) if rf != ACCOUNT else np.nan,
                            direct_dd_pct=round(ddd, 3), replay_dd_pct=round(rdd, 3),
                            measured_dd_pct=round(r["ddp"], 3), direct_wiped=wiped_d, replay_wiped=bool(u[f"wiped_{acc}"]),
                            same_baskets=bool(same), first_diff_basket=first, baskets_direct=int(len(o)),
                            baskets_replay=int(cl.sum()), ok=bool(ok), runtime_s=round(rt, 1)))
            log(f"  direct {sym} {period} {key:9s} ({acc}) {fe:10.2f} replay {rf:10.2f} diff {fe - rf:+.4f} "
                f"(bound {bound:.2f})  DD {ddd:.2f} vs {rdd:.2f}  same baskets {same} (first diff {first})  "
                f"{'ok' if ok else 'OVER'}  {rt:.0f}s")
            del res
            gc.collect()
        daily.append(dd)
    d_out = RUNS / sym / "parts"
    with open(d_out / f"direct_{period}.pkl", "wb") as fh:
        pickle.dump(dict(rows=rows, trades=pd.concat(trades, ignore_index=True),
                         daily=pd.concat(daily, ignore_index=True)), fh)
    CHECKS.mkdir(parents=True, exist_ok=True)
    tag = "G3" if sym in CHECK_SYMBOLS else "direct_vs_replay"
    pd.DataFrame(out).to_csv(CHECKS / f"{tag}_{sym}_{period}.csv", index=False)
    passed = all(r["ok"] for r in out)
    (CHECKS / f"{tag}_{sym}_{period}.json").write_text(json.dumps(dict(passed=passed, rows=len(out)), indent=1))
    (RUNS / sym / f".direct_{period}.done").write_text(datetime.now(timezone.utc).isoformat())
    log(f"{tag} {sym} {period}: {'within the bound' if passed else 'OVER the bound (material, DEVIATIONS D.3)'}")


# ───────────────────────────── G1 + G2 (§10.1) ─────────────────────────────

def run_gates() -> None:
    t0 = time.time()
    rc = pd.read_csv(F.OUT / "results.csv")

    def target(sym, label, w):
        r = rc[(rc["symbol"] == sym) & (rc["label"] == label) & (rc["window"] == w)]
        return float(r["final_equity"].iloc[0])

    g1, g2 = [], []
    for sym, keys, windows in (("XAUUSDm", ("v3lite", "gtop2", "gtop1add"), ("5y", "8y")), ("BTCUSDm", ("btop2",), ("5y",))):
        for w in windows:
            a, z = F.WINDOWS[w]
            a_ms, z_ms = to_ms(a), to_ms(z)
            prep = fast.prepare(sym, a, z, TFS, mode="sec")
            fx = FX(sym)
            for key in (keys if w == "5y" else ("v3lite",)):
                ov = BASKETS[key][1]
                cfg_f10 = E.live_config(sym, start=a, end=z).replace(**ov)             # exactly final10._tick_one
                cfg_pipe = basket_cfg(sym, key, a, z, per_unit=False, lot=0.01, cap_price=load_specs(sym)["caps"].get(key))
                same_cfg = cfg_f10.to_dict() == cfg_pipe.to_dict()
                t1 = time.time()
                res = fast.run(cfg_pipe, prep)
                rt = time.time() - t1
                fe = round(float(res.summary()["final_equity"]), 2)
                tg = target(sym, FINAL10_LABEL[key], w)
                g1.append(dict(gate="G1", symbol=sym, design=key, window=w, published=tg, reproduced=fe,
                               ok=bool(abs(fe - tg) < 0.005), pipeline_config_identical=same_cfg, runtime_s=round(rt, 1)))
                log(f"G1 {sym} {key} {w}: published {tg:.2f}, reproduced {fe:.2f} ({rt:.0f}s) config identical {same_cfg}")
                cfg_u = basket_cfg(sym, key, a, z, per_unit=True, cap_price=load_specs(sym)["caps"].get(key))
                t1 = time.time()
                ru = fast.run(cfg_u, prep)
                d = unit_data(ru, sym, a_ms, z_ms, fx)
                r = replay(d, 1, 1.0)
                b = res.baskets
                o, c = _ms(b["open_time"]), _ms(b["close_time"])
                cl = d["closed"]
                same = (len(o) == int(cl.sum()) and bool(np.all(o == d["o"][cl])) and bool(np.all(c == d["c"][cl])))
                f = res.fills
                bound = 0.01 * float(f.loc[f["action"].isin(["open", "add"]), "lots"].sum() / 0.01)
                ddd = float(res.scalars["max_drawdown_pct"])
                fe_raw = float(res.scalars["final_equity"])
                ok = same and abs(fe_raw - r["final"]) <= bound + 1e-6 and abs(ddd - r["ddp"]) <= 1.0
                g2.append(dict(gate="G2", symbol=sym, design=key, window=w, direct_final=round(fe_raw, 2),
                               replay_final=round(r["final"], 2), diff=round(fe_raw - r["final"], 4), bound=round(bound, 2),
                               direct_dd_pct=round(ddd, 3), replay_dd_pct=round(r["ddp"], 3), same_baskets=same,
                               baskets=len(o), ok=bool(ok), runtime_s=round(time.time() - t1, 1)))
                log(f"G2 {sym} {key} {w}: replay (a) {r['final']:.2f} vs direct {fe_raw:.2f} (bound {bound:.2f}), "
                    f"DD {r['ddp']:.2f}% vs {ddd:.2f}%, same baskets {same}: {'ok' if ok else 'FAIL'}")
                del res, ru
                gc.collect()
            del prep
            gc.collect()
    m = X.load_market("BTCUSDm", earliest=F.HISTORY_FROM["BTCUSDm"], end=DATA_END)
    sig = X.bot_signals(m)
    ones = np.ones(len(m.t))
    for key in ("ts1", "ts2"):
        plan = X.filtered(X.turtle(m, TURTLES[key][1]).plan, m, sig.votes_at)
        for w in ("5y", "8y"):
            a, z = F.WINDOWS[w]
            a_ix, z_ix = m.ix(a), m.ix(z)
            res, daily, trades = F._bar_account(X, m, plan, X.BOT, a_ix, z_ix)
            tg = target("BTCUSDm", FINAL10_LABEL[key], w)
            p = X.run_path(m, plan, a_ix, z_ix)
            bnd = F._day_bounds(m, a_ix, z_ix)
            mine = turtle_account(m, p, bnd, m.k, ones, False, to_ms(z))
            mp = mine["pnl"][mine["done"]]
            same_tr = len(mp) == len(res.trades_pnl) and bool(np.all(np.round(mp, 2) == np.round(res.trades_pnl, 2)))
            fe = round(mine["final"], 2)
            g1.append(dict(gate="G1", symbol="BTCUSDm", design=key, window=w, published=tg, reproduced=fe,
                           ok=bool(abs(fe - tg) < 0.005), pipeline_config_identical=True, runtime_s=np.nan))
            ok2 = same_tr and round(res.final, 2) == fe and abs(res.max_dd * 100 - mine["ddp"]) < 1e-9
            g2.append(dict(gate="G2", symbol="BTCUSDm", design=key, window=w, direct_final=round(res.final, 2),
                           replay_final=fe, diff=round(res.final - mine["final"], 6), bound=0.0,
                           direct_dd_pct=round(res.max_dd * 100, 4), replay_dd_pct=round(mine["ddp"], 4),
                           same_baskets=same_tr, baskets=len(mp), ok=bool(ok2), runtime_s=np.nan))
            log(f"G1 BTCUSDm {key} {w}: published {tg:.2f}, new account function {fe:.2f}; G2 vs external.account "
                f"{res.final:.2f}, DD {mine['ddp']:.4f}% vs {res.max_dd * 100:.4f}%: {'ok' if ok2 else 'FAIL'}")
    CHECKS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(g1).to_csv(CHECKS / "G1.csv", index=False)
    pd.DataFrame(g2).to_csv(CHECKS / "G2.csv", index=False)
    passed = all(r["ok"] for r in g1) and all(r["ok"] for r in g2)
    (CHECKS / "G1_G2.json").write_text(json.dumps(dict(passed=passed, g1=len(g1), g2=len(g2),
                                                       seconds=round(time.time() - t0)), indent=1))
    log(f"G1 + G2: {'PASS' if passed else 'FAIL'} ({time.time() - t0:.0f}s)")


# ───────────────────────────── the scheduler ─────────────────────────────

def other_job_running() -> bool:
    r = subprocess.run(["pgrep", "-f", "backtesting.research.sizing"], capture_output=True, text=True)
    return bool(r.stdout.strip())


class Task:
    def __init__(self, name: str, args: List[str], kind: str, sym: str):
        self.name, self.args, self.kind, self.sym = name, args, kind, sym
        self.proc: Optional[subprocess.Popen] = None
        self.t0 = 0.0
        self.status = "pending"


def drive(max_inflight: int = 3, fetch_slots: int = 2, engine_busy: int = 2, engine_free: int = 4,
          limit_s: float = 90 * 60) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    queue = list(SCOPE)
    reserves: List[str] = []                    # DEVIATIONS C: no crosses in this step, so no reserve
    sym_t0: Dict[str, float] = {}
    sym_active: Dict[str, float] = {}
    status: Dict[str, str] = {}                 # queued / fetching / fetched / done / failed / out
    gate: Dict[str, dict] = {}
    tasks: Dict[str, Task] = {}
    halted = False

    def mk(name, args, kind, sym):
        if name not in tasks:
            tasks[name] = Task(name, args, kind, sym)
        return tasks[name]

    def marker(sym, what):
        return (RUNS / sym / f".{what}.done").exists()

    for s in queue:
        status[s] = "done" if marker(s, "finalize") else ("fetched" if marker(s, "fetch") else "queued")
    base_tasks = [("base_half_XAUUSDm_sel", ["half", "XAUUSDm", "sel"]), ("base_half_XAUUSDm_conf", ["half", "XAUUSDm", "conf"]),
                  ("base_half_BTCUSDm_sel", ["half", "BTCUSDm", "sel"]), ("base_half_BTCUSDm_conf", ["half", "BTCUSDm", "conf"]),
                  ("base_turtles_BTCUSDm", ["turtles", "BTCUSDm"])]
    for name, args in base_tasks:
        t = mk(name, args, "engine", args[1])
        what = f"half_{args[2]}" if args[0] == "half" else "turtles"
        if marker(args[1], what):
            t.status = "done"

    mfile = CHECKS / "material.json"
    material_state: Dict[str, Optional[bool]] = {"m": json.loads(mfile.read_text())["material"] if mfile.exists() else None}

    def g3_state() -> str:
        """DEVIATIONS D: the Turtle checks must be exact (else stop); the basket rows decide 'material'."""
        tst, bst = [], []
        for s in CHECK_SYMBOLS:
            for p in BASKET_PERIODS:
                j = CHECKS / f"G3_{s}_{p}.json"
                bst.append(json.loads(j.read_text())["passed"] if j.exists() else None)
            c = CHECKS / f"turtle_fx1_{s}.csv"
            tst.append(bool(pd.read_csv(c)["ok"].all()) if c.exists() else None)
        if any(x is False for x in tst):
            return "fail"
        if any(x is None for x in tst + bst):
            return "pending"          # §10.3: no design runs on another symbol before G3 is complete
        if material_state["m"] is None:
            material_state["m"] = not all(bst)
            (CHECKS / "material.json").write_text(json.dumps(dict(
                material=material_state["m"], decided=datetime.now(timezone.utc).isoformat(),
                rule="DEVIATIONS D.3"), indent=1))
            log(f"G3 done: the replay error is {'MATERIAL: direct (a)/(b) runs for the USD-quoted symbols' if material_state['m'] else 'within the bound: replay everywhere'}")
        return "pass"

    def read_gate(s):
        try:
            e = json.loads(SPECS_JSON.read_text())[s]["gate"]
            return {"turtle": e["turtle"]["passed"], "basket": e["basket"]["passed"]}
        except Exception:                        # noqa: BLE001
            return None

    def launch(t: Task):
        lf = open(LOGS / f"{t.name}.log", "a")
        t.proc = subprocess.Popen([sys.executable, "-m", "backtesting.research.multisymbol"] + t.args, cwd=str(REPO_ROOT),
                                  stdout=lf, stderr=subprocess.STDOUT)
        t.t0 = time.time()
        t.status = "running"
        sym_t0.setdefault(t.sym, t.t0)
        log(f"start {t.name}")

    last_beat = 0.0
    while True:
        # reap
        for t in tasks.values():
            if t.status == "running" and t.proc is not None:
                rc = t.proc.poll()
                dt = time.time() - t.t0
                if rc is None and dt > limit_s:
                    t.proc.send_signal(signal.SIGTERM)
                    t.status = "failed"
                    log(f"KILLED {t.name}: over the {limit_s / 60:.0f}-minute limit")
                    continue
                if rc is None:
                    continue
                sym_active[t.sym] = sym_active.get(t.sym, 0.0) + dt
                t.status = "done" if rc == 0 else "failed"
                log(f"{'done' if rc == 0 else 'FAILED (rc %d)' % rc} {t.name} ({dt / 60:.1f} min)")
                if t.kind == "fetch":
                    if rc == 0:
                        status[t.sym] = "fetched"
                    else:
                        status[t.sym] = "failed"
        for s in queue:
            if status[s] == "fetched" and s not in gate:
                g = read_gate(s)
                if g is not None:
                    gate[s] = g
                    if not g["basket"]:
                        if s in CROSSES or s in RESERVES:
                            status[s] = "out"
                            if reserves:
                                r = reserves.pop(0)
                                queue.append(r)
                                status[r] = "queued"
                                log(f"{s} fails the basket-span gate: reserve {r} comes in")
                        else:
                            status[s] = "out"
                            log(f"{s} fails the basket-span gate: reported, leaves the candidate pool (M1 kept)")
        g3 = g3_state()
        if g3 == "fail" and not halted:
            halted = True
            log("G3 FAILED: stopping (no further design runs)")
        # create run tasks for fetched symbols
        for s in queue:
            if status[s] != "fetched" or s not in gate:
                continue
            for p in BASKET_PERIODS:
                t = mk(f"half_{s}_{p}", ["half", s, p], "engine", s)
                if marker(s, f"half_{p}") and t.status == "pending":
                    t.status = "done"
            t = mk(f"turtles_{s}", ["turtles", s], "engine", s)
            if not gate[s]["turtle"] and t.status == "pending":
                t.status = "skipped"
            elif marker(s, "turtles") and t.status == "pending":
                t.status = "done"
            if s in CHECK_SYMBOLS:
                for p in BASKET_PERIODS:
                    t = mk(f"g3_{s}_{p}", ["g3", s, p], "engine", s)
                    if (CHECKS / f"G3_{s}_{p}.json").exists() and t.status == "pending":
                        t.status = "done"
            elif s in USD_QUOTED and gate[s]["basket"]:
                if material_state["m"] is None:
                    continue                    # wait for G3 before deciding whether direct runs are needed
                if material_state["m"]:
                    for p in BASKET_PERIODS:
                        t = mk(f"direct_{s}_{p}", ["g3", s, p], "engine", s)
                        if marker(s, f"direct_{p}") and t.status == "pending":
                            t.status = "done"
            mine = [x for x in tasks.values() if x.sym == s and x.kind == "engine"]
            if all(x.status in ("done", "skipped") for x in mine if not x.name.startswith("g3_")) and \
                    all(x.status in ("done", "skipped") for x in mine if x.name.startswith("g3_")) | (s not in CHECK_SYMBOLS):
                f = mk(f"finalize_{s}", ["finalize", s], "final", s)
                if f.status == "pending" and not marker(s, "finalize"):
                    launch(f)
                elif marker(s, "finalize"):
                    f.status = "done"
                    status[s] = "done"
                    sym_active.setdefault(s, 0.0)
                    log(f"{s}: DONE (wall {(time.time() - sym_t0.get(s, time.time())) / 60:.0f} min, "
                        f"active {sym_active.get(s, 0) / 60:.0f} min)")
            if any(x.status == "failed" for x in mine):
                status[s] = "failed"
        if halted:
            if not any(t.status == "running" for t in tasks.values()):
                break
            time.sleep(15)
            continue
        # launch fetches
        inflight = [s for s in queue if status[s] in ("fetching", "fetched")]
        fetching = [s for s in queue if status[s] == "fetching"]
        for s in queue:
            if status[s] != "queued" or len(inflight) >= max_inflight or len(fetching) >= fetch_slots:
                continue
            conv = CONVERSION[quote_of(s)]
            if conv and conv[0] != s and status.get(conv[0]) not in ("fetched", "done", "out"):
                continue
            sizes = head_sizes(s)
            batch = sum(sizes.values())
            if disk_free() - batch < 15e9 or new_data_bytes() + 3.2 * batch > 15e9:
                if time.time() - last_beat > 600:
                    log(f"waiting for disk before fetching {s}")
                continue
            launch(mk(f"fetch_{s}", ["fetch", s], "fetch", s))
            status[s] = "fetching"
            inflight.append(s)
            fetching.append(s)
            break
        # launch engine tasks
        slots = engine_busy if other_job_running() else engine_free
        running = sum(1 for t in tasks.values() if t.status == "running" and t.kind == "engine")
        cands = [t for t in tasks.values() if t.status == "pending" and t.kind == "engine"]

        def prio(t):
            if t.name.startswith("g3_"):
                return (0, 0)
            if t.name.startswith("base_"):
                return (2, 0)
            return (1, queue.index(t.sym) if t.sym in queue else 99)

        for t in sorted(cands, key=prio):
            if running >= slots:
                break
            if t.name.startswith("g3_") or t.name.startswith("direct_") or t.name.startswith("base_direct_"):
                s = t.sym
                pp = t.args[2]
                if not marker(s, f"half_{pp}"):
                    continue
            elif not t.name.startswith("base_") and t.sym not in CHECK_SYMBOLS and g3 != "pass":
                continue
            launch(t)
            running += 1
        # the base: direct runs if material, then finalize (DEVIATIONS D.4)
        if material_state["m"] is not None:
            for bs in BASE_SYMBOLS:
                if material_state["m"]:
                    for p in BASKET_PERIODS:
                        t = mk(f"base_direct_{bs}_{p}", ["g3", bs, p], "engine", bs)
                        if marker(bs, f"direct_{p}") and t.status == "pending":
                            t.status = "done"
                mine = [x for x in tasks.values() if x.sym == bs and x.kind == "engine"]
                if all(x.status == "done" for x in mine):
                    f = mk(f"finalize_{bs}", ["finalize", bs], "final", bs)
                    if f.status == "pending" and not marker(bs, "finalize"):
                        launch(f)
                    elif marker(bs, "finalize"):
                        f.status = "done"
        # finished?
        if all(status[s] in ("done", "failed", "out") for s in queue) and \
                all(t.status in ("done", "failed", "skipped") for t in tasks.values()):
            break
        if time.time() - last_beat > 600:
            last_beat = time.time()
            log("status: " + ", ".join(f"{s}={status[s]}" for s in queue) + f" | G3 {g3} | engine slots {slots} | "
                f"free {disk_free() / 1e9:.0f} GB, new data {new_data_bytes() / 1e9:.1f} GB")
        time.sleep(15)
    log("driver finished: " + ", ".join(f"{s}={status[s]}" for s in queue))
    if not halted:
        summary()


# ───────────────────────────── summary ─────────────────────────────

def summary() -> None:
    mets, stats = [], []
    for d in sorted(RUNS.iterdir()) if RUNS.exists() else []:
        if (d / "metrics.csv").exists():
            mets.append(pd.read_csv(d / "metrics.csv"))
        if (d / "trade_stats.csv").exists():
            stats.append(pd.read_csv(d / "trade_stats.csv"))
    if mets:
        s = pd.concat(mets, ignore_index=True)
        s.to_csv(RUNS / "summary.csv", index=False)
        s.to_csv(OUT / "runs.csv", index=False)
        log(f"runs/summary.csv: {len(s)} rows, {s['symbol'].nunique()} symbols")
    if stats:
        pd.concat(stats, ignore_index=True).to_csv(RUNS / "trade_stats.csv", index=False)
    rows = []
    specs = json.loads(SPECS_JSON.read_text()) if SPECS_JSON.exists() else {}
    for qf in sorted(QUAL.glob("*.json")) if QUAL.exists() else []:
        q = json.loads(qf.read_text())
        sym = q["symbol"]
        point = 10.0 ** -SYMBOLS[sym].digits
        months = {}
        ticks = days = 0
        sec_day = []
        for ch in q["quality_report_chunks"]:
            if "error" in ch:
                continue
            for mo in ch.get("months", []):
                months[(mo["year"], mo["month"])] = mo
            ticks += ch.get("ticks_total") or 0
            days += ch["days"]["with_ticks"]
            sec_day.append(ch["days"]["seconds_per_day_median"])
        sp = [mo["spread_median"] for mo in months.values() if mo.get("spread_median") is not None]
        gt, gb = q["gate"]["turtle"], q["gate"]["basket"]
        rows.append(dict(symbol=sym, months_present=len(months), months_expected=len(MONTHS),
                         gate_turtle_span="pass" if gt["passed"] else "FAIL", gate_basket_span="pass" if gb["passed"] else "FAIL",
                         missing_months=len(set(gt["missing_months"]) | set(gb["missing_months"])),
                         holes_weekday_silences_8h=len(gt["bad_silences"]) + len(gb["bad_silences"]),
                         thin_weeks=len(gt["thin_weeks"]) + len(gb["thin_weeks"]),
                         silences_8h_any=max(gt["silences_8h"], 0) + max(gb["silences_8h"], 0),
                         median_spread_price=float(np.median(sp)) if sp else np.nan,
                         median_spread_points=round(float(np.median(sp)) / point, 2) if sp else np.nan,
                         ticks_per_day=round(ticks / days) if days else np.nan,
                         quote_seconds_per_day_median=int(np.median(sec_day)) if sec_day else np.nan,
                         median_week_seconds_basket_span=gb["median_week_seconds"],
                         L=specs.get(sym, {}).get("L"), med_h1_vol=specs.get(sym, {}).get("med_h1_vol")))
    if rows:
        pd.DataFrame(rows).to_csv(RUNS / "data_quality.csv", index=False)
        log(f"runs/data_quality.csv: {len(rows)} symbols")


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.multisymbol")
    ap.add_argument("cmd", choices=["gates", "fetch", "half", "turtles", "finalize", "g3", "drive", "summary", "regate"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    if a.cmd == "gates":
        run_gates()
    elif a.cmd == "fetch":
        fetch(a.args[0])
    elif a.cmd == "half":
        run_half(a.args[0], a.args[1])
    elif a.cmd == "turtles":
        run_turtles(a.args[0])
    elif a.cmd == "finalize":
        finalize(a.args[0])
    elif a.cmd == "g3":
        run_g3(a.args[0], a.args[1])
    elif a.cmd == "drive":
        drive(engine_free=3)
    elif a.cmd == "summary":
        summary()
    elif a.cmd == "regate":
        for x in a.args:
            regate(x)


if __name__ == "__main__":
    main()
