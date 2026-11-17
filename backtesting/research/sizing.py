"""
How low can the step-up balance go?  The six demo designs under more aggressive sizing (study of 2026-11-17).

The bot sizes every basket (every Turtle trade) by the unit rule

    units = floor(balance / STEP) + 1, capped at 10 units, 0.01 lot per unit,

re-derived only while flat, from a virtual balance of $2,000 plus the bot's own closed P/L. Today STEP = $2,500.
This module runs the six designs of the demo branches with STEP in ``STEPS``, with the cap of 10 units and without a
cap, on the four windows of the final-ten study (``final10.WINDOWS``) and on rolling starts (a fresh $2,000 account on
the 1st of every month, run for 12 months).

How each design is measured:

* The four designs of the tick engine (gold V3-lite, Top 2, Top 1; BTC Top 2) are re-run by the engine itself
  (``engine.fast``) at every STEP: per second for 8 years, 5 years, Nov 2018 - Dec 2020 and every rolling start, on
  every tick under the eight loop timings of the final-ten study for the last year. A per-unit replay of these designs
  is not exact: the engine (like MT5) rounds every position's floating profit to the cent before it compares the basket
  profit with "units x target" or "units x stop", so the poll at which a target or a stop fires can move by a second
  or two when the unit changes (``check`` measures it). Re-running costs more CPU but leaves nothing to approximate.
* The two Turtle designs run on the research M1-bar simulator (``external.py``), whose trade path does not depend on
  the account at all: the path is computed once per window (or start) and the account kernel sizes it. ``_bar_replay``
  mirrors ``external._account_kernel`` operation for operation and adds the extra figures (lowest equity, margin,
  lots); it is checked against the kernel itself at every STEP.

"Breaking" is judged on equity with floating P/L at each engine's own resolution: a wipe (equity <= 0, the engine's
stop-out), the margin level (equity / margin, margin at the positions' fill prices as the tick engine computes it,
gold 100 oz and BTC 1 BTC per lot) at 1:100 and 1:200, and a drawdown of 50 % or more.

Usage (one at a time on the 16 GB machine; outputs in ``backtest_results/sizing``, run records in --work)::

    python -m backtesting.research.sizing constants
    python -m backtesting.research.sizing bars
    python -m backtesting.research.sizing sec --symbol XAUUSDm --workers 6
    python -m backtesting.research.sizing ticks1y --symbol XAUUSDm --workers 6
    python -m backtesting.research.sizing check --symbol XAUUSDm
    python -m backtesting.research.sizing report
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from numba import njit

from . import final10 as F
from ..config import REPO_ROOT

OUT = F.RESULTS / "sizing"
STEPS = (2500, 2000, 1750, 1500, 1250, 1000, 750, 500)
CAP = 10
NO_CAP = 1_000_000                      # "no cap": the rule without its 10-unit limit
CAPS = (("10", CAP), ("none", NO_CAP))
ACCOUNT = 2000.0
WINDOWS = F.WINDOWS                     # 8y, 5y, new (Nov 2018 - Dec 2020), 1y
WINDOW_NAMES = F.WINDOW_NAMES
SEC_WINDOWS = ("8y", "5y", "new")
ROLL_FIRST, ROLL_LAST = "2018-12-01", "2025-11-01"   # every 1st of a month whose 12 months lie inside the 8 years
RECENT_FIRST = "2023-12-01"                          # the last 24 start months
TFS = ["M1", "M5", "M15", "H1", "H4"]                # the timeframes final10 prepared for its tick runs
SEEDS = tuple(range(1, 9))                           # final10's eight loop timings for the last year
LEVERAGES = (100, 200)
DAY_S = 86400

DESIGNS: Dict[str, dict] = {
    "xau_v3lite": dict(branch="demo_hedging_xauusd6", symbol="XAUUSDm", name="Gold V3-lite", engine="ticks",
                       own="V3-lite", label="V3-lite"),
    "xau_top2": dict(branch="demo_hedging_xauusd7", symbol="XAUUSDm", name="Gold Top 2", engine="ticks",
                     own="Top 2", label="Top 2"),
    "xau_top1": dict(branch="demo_hedging_xauusd8", symbol="XAUUSDm", name="Gold Top 1", engine="ticks",
                     own="Top 1", label="Top 1"),
    "btc_turtle_s2": dict(branch="demo_hedging_btcusd6", symbol="BTCUSDm", name="BTC Turtle System 2 + bot votes",
                          engine="bars", label="Turtle [alt] + bot votes", family="turtle", params="alt",
                          variant="+ bot votes", sizing="bot unit rule"),
    "btc_turtle_s1": dict(branch="demo_hedging_btcusd7", symbol="BTCUSDm", name="BTC Turtle System 1 + bot votes",
                          engine="bars", label="Turtle + bot votes", family="turtle", params="default",
                          variant="+ bot votes", sizing="bot unit rule"),
    "btc_top2": dict(branch="demo_hedging_btcusd8", symbol="BTCUSDm", name="BTC Top 2", engine="ticks",
                     own="Top 2", label="Top 2"),
}
ORDER = list(DESIGNS)


def roll_starts() -> List[str]:
    return [str(d.date()) for d in pd.date_range(ROLL_FIRST, ROLL_LAST, freq="MS")]


def roll_end(start: str) -> str:
    return str((pd.Timestamp(start) + pd.DateOffset(months=12)).date())


def _s(when: str) -> int:
    from ..data import store
    return store.to_ms(when) // 1000


def _weeks(a: str, z: str) -> float:
    return (_s(z) - _s(a)) / DAY_S / 7.0


# ───────────────────────────── the sizing constants ─────────────────────────────

def demo_constants() -> List[dict]:
    """The sizing constants of each demo branch (symbols.json, constants.py) next to the backtester's."""
    from . import external as X
    from ..config import BacktestConfig
    out = []
    for key, d in DESIGNS.items():
        ref = f"origin/{d['branch']}"
        sj = json.loads(subprocess.run(["git", "show", f"{ref}:symbols.json"], cwd=REPO_ROOT, capture_output=True,
                                       text=True, check=True).stdout)
        entry = next(e for e in sj["symbols"] if e.get("symbol") == d["symbol"])
        cpy = subprocess.run(["git", "show", f"{ref}:constants.py"], cwd=REPO_ROOT, capture_output=True, text=True,
                             check=True).stdout
        ns: dict = {}
        exec(compile(cpy, f"{ref}:constants.py", "exec"), ns)       # constants.py holds plain assignments only
        bt = BacktestConfig.live(d["symbol"])
        out.append(dict(design=key, branch=d["branch"], step_up_balance=float(entry["step_up_balance"]),
                        unit_max_limit=int(entry["unit_max_limit"]), mtqty=float(sj.get("mtqty", 0.01)),
                        virtual_start_balance=float(ns.get("VIRTUAL_START_BALANCE")),
                        virtual_start_date=ns.get("VIRTUAL_START_DATE"), design_name=ns.get("DESIGN_NAME"),
                        strategy=ns.get("STRATEGY"), turtle_system=ns.get("TURTLE_SYSTEM"),
                        bt_step_up=bt.step_up_balance, bt_unit_max=bt.unit_max_limit, bt_mtqty=bt.mtqty,
                        bt_initial_balance=bt.initial_balance, bars_step_up=X.STEP_UP, bars_unit_max=X.UNIT_MAX,
                        bars_account=X.ACCOUNT))
    return out


# ───────────────────────────── the tick engine ─────────────────────────────

_G: dict = {}            # what forked workers inherit: the prepared data and the base configurations


def _base_cfg(key: str):
    if key not in _G.setdefault("cfg", {}):
        from .. import experiments as E
        d = DESIGNS[key]
        _G["cfg"][key] = E.live_config(d["symbol"]).replace(**F.own_designs(d["symbol"])[d["own"]])
    return _G["cfg"][key]


def tick_cfg(key: str, a: str, z: str, step: float, cap: int, seed: Optional[int] = None, record_s: int = 3600):
    from ..analysis.robustness import live_timing
    kw = dict(start=a, end=z, step_up_balance=float(step), unit_max_limit=int(cap), record_interval_s=int(record_s))
    if seed is not None:
        kw.update(live_timing(int(seed)))
    return _base_cfg(key).replace(**kw)


def _tick_daily(res) -> pd.Series:
    e = res.equity.set_index("time")["equity"]
    d = e.groupby(e.index.floor("D")).first()
    if len(d):
        d.iloc[0] = ACCOUNT
    return d


def tick_metrics(res, cfg, a: str, z: str, daily: bool) -> dict:
    """The figures of one tick-engine account."""
    sc, b = res.scalars, res.baskets
    pnl = b["pnl"].to_numpy(np.float64) if len(b) else np.zeros(0)
    units = b["units"].to_numpy(np.int64) if len(b) else np.zeros(0, np.int64)
    max_units = int(max(units.max() if len(units) else 0, sc.get("open_units_at_end", 0.0)))
    lev = float(cfg.effective_leverage)
    ml = float(sc["min_margin_level_pct"])
    wiped = bool(sc["stopped_out"])
    out = dict(final_equity=float(sc["final_equity"]), max_dd_pct=float(sc["max_drawdown_pct"]),
               max_dd_usd=float(sc["max_drawdown_usd"]), min_equity=float(sc["min_equity"]),
               max_equity=float(sc["max_equity"]), worst_basket=float(pnl.min()) if len(pnl) else np.nan,
               worst_float=float(sc["max_floating_loss"]), max_lots=float(sc["max_lots"]), max_units=max_units,
               trades=int(len(pnl)), wiped=wiped,
               wiped_at=str(pd.Timestamp(int(sc["last_poll_ms"]), unit="ms").date()) if wiped else "",
               engine_leverage=lev, min_ml_engine=ml, margin_rejects=int(res.counters.get("margin_rejects", 0)),
               max_margin_engine=float(sc["max_margin_used"]), open_profit_end=float(sc["open_profit_at_end"]))
    for L in LEVERAGES:
        out[f"ml_{L}"] = ml * L / lev                         # margin level scales with the leverage
        out[f"margin_{L}"] = float(sc["max_margin_used"]) * lev / L
    if daily:
        dser = _tick_daily(res)
        met = F.account_metrics(dser, out["final_equity"], out["max_dd_pct"], _s(a), _s(z), pnl, wiped,
                                pd.Timestamp(out["wiped_at"]) if wiped else None)
        out["longest_underwater_days"] = float(met["longest_underwater_days"])
        out["losing_months"] = int(met["losing_months"])
        out["months"] = int(met["months"])
    return out


def _tick_sizings(key: str, a: str, z: str, prep, light: bool, seed: Optional[int] = None,
                  steps: Sequence[int] = STEPS) -> List[dict]:
    """Every STEP with the cap, and without it where the capped account ever reached the cap (otherwise the two
    accounts are the same account: every unit the capped rule chose was below the cap)."""
    from ..engine import fast
    rows = []
    for step in steps:
        for cap_name, cap in CAPS:
            if cap_name == "none" and rows[-1]["max_units"] < CAP:
                rows.append(dict(rows[-1], cap="none", same_as_capped=True))
                continue
            t0 = time.time()
            cfg = tick_cfg(key, a, z, step, cap, seed)
            res = fast.run(cfg, prep, light=light)
            row = dict(design=key, step=int(step), cap=cap_name, start=a, end=z, seed=seed,
                       same_as_capped=False, **tick_metrics(res, cfg, a, z, daily=not light))
            row["run_s"] = round(time.time() - t0, 1)
            rows.append(row)
    return rows


def _tick_task(task: tuple) -> List[dict]:
    kind, key, what = task
    prep = _G["prep"]
    if kind == "win":
        a, z = WINDOWS[what]
        rows = _tick_sizings(key, a, z, prep, light=False)
        for r in rows:
            r.update(window=what)
    elif kind == "roll":
        rows = _tick_sizings(key, what, roll_end(what), prep, light=True)
        for r in rows:
            r.update(window="roll")
    elif kind == "t1y":
        a, z = WINDOWS["1y"]
        rows = _tick_sizings(key, a, z, prep, light=False, seed=int(what))
        for r in rows:
            r.update(window="1y")
    else:
        raise ValueError(kind)
    for r in rows:
        r["task"] = f"{kind}|{key}|{what}"
    return rows


def _done(sink: Path) -> set:
    if not sink.exists():
        return set()
    return {json.loads(line)["task"] for line in sink.read_text().splitlines() if line.strip()}


def _pool(tasks: List[tuple], sink: Path, workers: int, log=print) -> None:
    done = _done(sink)
    todo = [t for t in tasks if f"{t[0]}|{t[1]}|{t[2]}" not in done]
    log(f"{len(todo)} of {len(tasks)} tasks to run, {workers} workers -> {sink}")
    sink.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    ctx = mp.get_context("fork")        # the workers share the prepared rows (copy-on-write)
    with ctx.Pool(workers) as pool, open(sink, "a") as fh:
        for i, rows in enumerate(pool.imap_unordered(_tick_task, todo, chunksize=1)):
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            r0 = rows[0]
            log(f"  [{i + 1}/{len(todo)} {time.time() - t0:6.0f}s] {r0['task']}: STEP 2500 final "
                f"{r0['final_equity']:.2f} DD {r0['max_dd_pct']:.2f}%")


def _warm(prep, keys: Sequence[str]) -> None:
    """Indicator arrays and the compiled kernel, made in the parent so that every worker inherits them."""
    from ..engine import fast
    for key in keys:
        cfg = tick_cfg(key, WINDOWS["8y"][0], WINDOWS["8y"][1], 2500, CAP)
        prep.flat(cfg)
    a = pd.Timestamp(prep.start_ms, unit="ms")
    fast.run(tick_cfg(keys[0], str(a.date()), str((a + pd.Timedelta(days=2)).date()), 2500, CAP), prep, light=True)


def run_sec(symbol: str, work: Path, workers: int = 6, roll: bool = True, log=print) -> None:
    """Per-second runs: the 8-year, 5-year and Nov 2018 - Dec 2020 windows and every rolling start, all cut out of one
    8-year preparation (the windows are checked against the published accounts in ``report``)."""
    from ..engine import fast
    keys = [k for k, d in DESIGNS.items() if d["symbol"] == symbol and d["engine"] == "ticks"]
    t0 = time.time()
    a, z = WINDOWS["8y"]
    _G["prep"] = fast.prepare(symbol, a, z, TFS, mode="sec")
    _warm(_G["prep"], keys)
    log(f"{symbol}: {_G['prep'].n_rows:,} per-second rows ready ({time.time() - t0:.0f}s)")
    tasks = [("win", k, w) for w in SEC_WINDOWS for k in keys]
    if roll:
        tasks += [("roll", k, s) for s in roll_starts() for k in keys]
    _pool(tasks, work / f"sec_{symbol}.jsonl", workers, log)


def run_ticks1y(symbol: str, work: Path, workers: int = 6, log=print) -> None:
    """The last year on every tick under the eight loop timings of the final-ten study."""
    from ..engine import fast
    keys = [k for k, d in DESIGNS.items() if d["symbol"] == symbol and d["engine"] == "ticks"]
    t0 = time.time()
    a, z = WINDOWS["1y"]
    _G["prep"] = fast.prepare(symbol, a, z, TFS, mode="ticks")
    for key in keys:
        _G["prep"].flat(tick_cfg(key, a, z, 2500, CAP))
    fast.run(tick_cfg(keys[0], a, str((pd.Timestamp(a) + pd.Timedelta(days=2)).date()), 2500, CAP, seed=1),
             _G["prep"], light=True)
    log(f"{symbol}: {_G['prep'].n_rows:,} ticks ready ({time.time() - t0:.0f}s)")
    tasks = [("t1y", k, sd) for k in keys for sd in SEEDS]
    _pool(tasks, work / f"ticks1y_{symbol}.jsonl", workers, log)


# ───────────────────────────── the M1-bar simulator (Turtles) ─────────────────────────────

@njit(cache=True)
def _bar_replay(t, h, l, c, sp, k, T_dir, T_eix, T_epx, T_xix, T_xpx, T_why, T_leg0, T_nleg, L_eix, L_epx,
                bnd, bal0, step_up, unit_max):
    """
    ``external._account_kernel`` in the bot's unit mode (no leverage cap), operation for operation, plus: the lowest
    equity (worst price of every M1 bar), the lowest equity / notional at the legs' fill prices (margin level at
    leverage L = that x L x 100), the largest position in lots, the worst floating trade P/L and the largest notional.
    """
    nt = T_dir.shape[0]
    nb = bnd.shape[0]
    steps = np.zeros(nt)
    pnl = np.zeros(nt)
    eqb = np.full(nb, np.nan)
    bal = bal0
    peak = bal0
    maxdd = 0.0
    wiped = False
    wipe_ix = -1
    n_done = 0
    bi = 0
    min_eq = bal0
    min_ml1 = np.inf
    max_lots = 0.0
    worst_float = 0.0
    max_notional = 0.0
    for i in range(nt):
        n_done = i + 1
        e = T_eix[i]
        x = T_xix[i]
        d = T_dir[i]
        while bi < nb and bnd[bi] <= e:
            eqb[bi] = bal
            bi += 1
        s = math.floor(bal / step_up) + 1.0
        if s > unit_max:
            s = unit_max
        if s < 0:
            s = 0.0
        steps[i] = s
        if s == 0:
            continue
        for j in range(e, x + 1):
            uc = 0.0
            uw = 0.0
            notional = 0.0
            nl = 0
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
                notional += s * k * ep
                nl += 1
            if j < x and bal + uc > peak:
                peak = bal + uc
            ew = bal + uw
            if ew < min_eq:
                min_eq = ew
            if uw < worst_float:
                worst_float = uw
            if nl > 0:
                lots = s * nl * 0.01
                if lots > max_lots:
                    max_lots = lots
                if notional > max_notional:
                    max_notional = notional
                r = ew / notional
                if r < min_ml1:
                    min_ml1 = r
            if ew <= 0.0:
                wiped = True
                wipe_ix = j
                pnl[i] = -bal
                bal = 0.0
                maxdd = 1.0
                break
            dd = (peak - ew) / peak
            if dd > maxdd:
                maxdd = dd
            if j < x:
                while bi < nb and bnd[bi] == j + 1:
                    eqb[bi] = bal + uc
                    bi += 1
        if wiped:
            break
        pl = 0.0
        for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
            pl += s * k * d * (T_xpx[i] - L_epx[q])
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
    return steps, pnl, bal, maxdd, wiped, wipe_ix, n_done, eqb, min_eq, min_ml1, max_lots, worst_float, max_notional


@njit(cache=True)
def _bar_curve(c, sp, k, a_ix, z_ix, T_dir, T_eix, T_xix, T_xpx, T_leg0, T_nleg, L_eix, L_epx, steps, pnl, bal0):
    """Equity at the close of every M1 bar of [a_ix, z_ix) (closed balance + the open trade at the bar's close)."""
    out = np.empty(z_ix - a_ix)
    bal = bal0
    i = 0
    nt = T_dir.shape[0]
    for j in range(a_ix, z_ix):
        while i < nt and (steps[i] == 0 or T_xix[i] < j):
            if steps[i] != 0:
                bal += pnl[i]
            i += 1
        uc = 0.0
        if i < nt and T_eix[i] <= j <= T_xix[i]:
            s = steps[i]
            d = T_dir[i]
            for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
                if L_eix[q] > j:
                    continue
                mc = T_xpx[i] if j == T_xix[i] else (c[j] if d == 1 else c[j] + sp[j])
                uc += s * k * d * (mc - L_epx[q])
        out[j - a_ix] = bal + uc
    return out


class BarDesigns:
    """BTC market, the bot's votes and the two Turtle plans (built once)."""

    def __init__(self, cache_dir: Optional[Path] = None, log=print):
        from . import external as X
        self.X = X
        t0 = time.time()
        self.m = X.load_market("BTCUSDm", earliest=F.HISTORY_FROM["BTCUSDm"], end=F.DATA_END)
        self.sig = X.bot_signals(self.m, cache_dir)
        built: dict = {}
        self.plans = {}
        for key, d in DESIGNS.items():
            if d["engine"] == "bars":
                plan, sizing = F._bar_plan(X, self.m, self.sig, None, built, d)
                assert sizing.mode == "bot" and sizing.cap_lev == 0.0
                self.plans[key] = plan
        log(f"BTCUSDm: {len(self.m):,} M1 bars, votes and Turtle plans ready ({time.time() - t0:.0f}s)")

    def path(self, key: str, a: str, z: str):
        m = self.m
        a_ix, z_ix = int(np.searchsorted(m.t, _s(a), "left")), int(np.searchsorted(m.t, _s(z), "left"))
        return self.X.run_path(m, self.plans[key], a_ix, z_ix), a_ix, z_ix

    def kernel(self, p, a_ix: int, z_ix: int, step: float, cap: float):
        """The simulator's own account kernel, as ``final10._bar_account`` calls it."""
        X, m = self.X, self.m
        bnd = F._day_bounds(m, a_ix, z_ix)
        return X._account_kernel(m.t, m.o, m.h, m.l, m.c, m.sp, m.k, p.dir, p.eix, p.epx, p.xix, p.xpx, p.why,
                                 p.risk, p.expo, p.leg0, p.nleg, p.leix, p.lepx, 0, 0.0, 0.0, False,
                                 np.asarray(bnd[1:-1], np.int64), X._YEARS, X.ACCOUNT, float(step), float(cap))

    def replay(self, p, a_ix: int, z_ix: int, step: float, cap: float):
        m = self.m
        bnd = F._day_bounds(m, a_ix, z_ix)
        out = _bar_replay(m.t, m.h, m.l, m.c, m.sp, m.k, p.dir, p.eix, p.epx, p.xix, p.xpx, p.why, p.leg0, p.nleg,
                          p.leix, p.lepx, np.asarray(bnd[1:-1], np.int64), ACCOUNT, float(step), float(cap))
        return out, bnd

    def metrics(self, key: str, a: str, z: str, p, a_ix: int, z_ix: int, step: float, cap: float,
                check: bool = True, daily: bool = True) -> dict:
        m = self.m
        (steps, pnl, bal, dd, wiped, wix, n_done, eqb, min_eq, min_ml1, max_lots, worst_float, max_not), bnd = \
            self.replay(p, a_ix, z_ix, step, cap)
        out = dict(final_equity=float(bal), max_dd_pct=float(dd) * 100.0, min_equity=float(min_eq),
                   max_lots=round(float(max_lots), 6), worst_float=float(worst_float), wiped=bool(wiped),
                   wiped_at=str(pd.Timestamp(int(m.t[wix]), unit="s").date()) if wiped else "",
                   engine_leverage=np.nan, min_ml_engine=np.nan, margin_rejects=0)
        done = np.arange(len(steps)) < n_done
        sel = np.flatnonzero(done & (steps > 0))
        tp = pnl[sel]
        out.update(trades=int(len(sel)), worst_basket=float(tp.min()) if len(tp) else np.nan,
                   max_units=int(steps[sel].max()) if len(sel) else 0)
        for L in LEVERAGES:
            out[f"ml_{L}"] = float(min_ml1) * L * 100.0
            out[f"margin_{L}"] = float(max_not) / L
        if check:
            ks, kp, kb, kdd, kw, kwix, kn, keqb = self.kernel(p, a_ix, z_ix, step, cap)
            same = (kb == bal and kdd == dd and bool(kw) == bool(wiped) and kn == n_done
                    and np.array_equal(ks, steps) and np.array_equal(kp, pnl)
                    and np.array_equal(np.nan_to_num(keqb, nan=-1.0), np.nan_to_num(eqb, nan=-1.0)))
            if not same:
                raise RuntimeError(f"{key} {a}..{z} STEP {step} cap {cap}: the replay differs from the kernel "
                                   f"({bal} vs {kb}, DD {dd} vs {kdd})")
            out["kernel_match"] = True
        if daily:
            blocks = np.concatenate([[ACCOUNT], eqb, [bal]])
            ser = pd.Series(blocks[:-1], index=[F._ts(m.t[i]) if i < len(m) else F._ts(m.t[-1]) for i in bnd[:-1]])
            ser.iloc[0] = ACCOUNT
            met = F.account_metrics(ser, float(bal), float(dd) * 100.0, _s(a), _s(z), tp, bool(wiped),
                                    pd.Timestamp(out["wiped_at"]) if wiped else None)
            out["longest_underwater_days"] = float(met["longest_underwater_days"])
            out["losing_months"] = int(met["losing_months"])
            out["months"] = int(met["months"])
        return out


def run_bars(work: Path, cache_dir: Optional[Path] = None, log=print) -> None:
    sink = work / "bars_BTCUSDm.jsonl"
    B = BarDesigns(cache_dir, log)
    rows = []
    jobs = [(w,) + tuple(WINDOWS[w]) for w in WINDOWS] + [("roll", s, roll_end(s)) for s in roll_starts()]
    t0 = time.time()
    for key in (k for k, d in DESIGNS.items() if d["engine"] == "bars"):
        for w, a, z in jobs:
            p, a_ix, z_ix = B.path(key, a, z)
            for step in STEPS:
                for cap_name, cap in CAPS:
                    met = B.metrics(key, a, z, p, a_ix, z_ix, step, cap, check=True, daily=(w != "roll"))
                    rows.append(dict(design=key, step=int(step), cap=cap_name, start=a, end=z, seed=None,
                                     window=w, same_as_capped=False, task=f"bars|{key}|{w}|{a}", **met))
        log(f"  {key}: {len(jobs)} windows and starts x {len(STEPS) * 2} sizings, every one equal to the kernel "
            f"({time.time() - t0:.0f}s)")
    sink.parent.mkdir(parents=True, exist_ok=True)
    with open(sink, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    log(f"{len(rows)} accounts -> {sink}")


# ───────────────────────────── the check: a per-unit replay of the tick engine ─────────────────────────────

def _r2(x: float) -> float:
    """kernels._round2: to cents, half away from zero."""
    if x >= 0.0:
        return math.floor(x * 100.0 + 0.5) / 100.0
    return -math.floor(-x * 100.0 + 0.5) / 100.0


def per_unit_replay(fills: pd.DataFrame, contract: float, step: float, cap: int, last_bid: float, last_ask: float,
                    mtqty: float = 0.01) -> dict:
    """
    Replays the baskets of one engine run with another sizing: the same positions at the same prices, the unit from
    the replayed closed balance (only while flat), each position's lots = round2(multiplier x unit x mtqty) and its
    P/L rounded to the cent exactly as the engine books it. Only the decisions are taken from the run.
    """
    bal = ACCOUNT
    per = []
    open_profit = 0.0
    for bid, g in fills.groupby("basket", sort=True):
        ent = g[g["action"].isin(["open", "add"])]
        cls = g[g["action"] == "close"]
        u_ref = int(ent["units"].iloc[0])
        u = int(math.floor(bal / step)) + 1
        u = max(1, min(u, cap))
        side = 1 if ent["side"].iloc[0] == "BUY" else -1
        pl = 0.0
        for _, e in ent.iterrows():
            mult = round(float(e["lots"]) / (u_ref * mtqty), 6)
            lots = _r2(mult * u * mtqty)
            if len(cls):
                cp = float(cls["price"].iloc[0])
                pl += _r2((cp - e["price"]) * lots * contract) if side > 0 else _r2((e["price"] - cp) * lots * contract)
            else:      # open at the end: marked to market at the last quote (not closed)
                a = last_bid + (last_ask - last_bid) * 1.0 + 0.0
                open_profit += _r2((last_bid - e["price"]) * lots * contract) if side > 0 else \
                    _r2((e["price"] - a) * lots * contract)
        if len(cls):
            bal += pl
            per.append(dict(basket=int(bid), units=u, pnl=round(pl, 2), open_time=g["time"].iloc[0],
                            close_time=cls["time"].iloc[0]))
    return dict(final=bal + open_profit, baskets=pd.DataFrame(per))


def run_check(symbol: str, work: Path, keys: Sequence[str] = ("xau_v3lite",), steps: Sequence[int] = (1000, 500),
              windows: Sequence[str] = ("8y", "1y"), log=print) -> None:
    """The engine re-run at other STEPs against the per-unit replay of its STEP-2500 run (the proof the task asks for,
    and where it fails)."""
    from ..engine import fast
    out = []
    for w in windows:
        a, z = WINDOWS[w]
        mode = "ticks" if w == "1y" else "sec"
        prep = fast.prepare(symbol, a, z, TFS, mode=mode)
        last = int(np.searchsorted(prep.t_ms, prep.end_ms, "left")) - 1
        for key in keys:
            seeds = (5,) if w == "1y" else (None,)
            for sd in seeds:
                cfg0 = tick_cfg(key, a, z, 2500, CAP, sd)
                ref = fast.run(cfg0, prep, light=True)
                contract = cfg0.spec.contract_size
                for step in steps:
                    for cap_name, cap in CAPS:
                        cfg = tick_cfg(key, a, z, step, cap, sd)
                        res = fast.run(cfg, prep, light=True)
                        rp = per_unit_replay(ref.fills, contract, step, cap, float(prep.bid[last]),
                                             float(prep.ask[last]))
                        eb = res.baskets
                        rb = rp["baskets"]
                        n = min(len(eb), len(rb))
                        same_t = (eb["open_time"].iloc[:n].to_numpy() == rb["open_time"].iloc[:n].to_numpy()) & \
                                 (eb["close_time"].iloc[:n].to_numpy() == rb["close_time"].iloc[:n].to_numpy())
                        first = int(np.flatnonzero(~same_t)[0]) if (~same_t).any() else (n if len(eb) != len(rb) else -1)
                        same_pnl = np.abs(eb["pnl"].iloc[:n].to_numpy() - rb["pnl"].iloc[:n].to_numpy()) < 0.005
                        pre = first if first >= 0 else n
                        row = dict(design=key, window=w, seed=sd, step=step, cap=cap_name,
                                   engine_final=round(float(res.scalars["final_equity"]), 2),
                                   replay_final=round(float(rp["final"]), 2),
                                   diff=round(float(rp["final"]) - float(res.scalars["final_equity"]), 2),
                                   engine_baskets=int(len(eb)), replay_baskets=int(len(rb)),
                                   baskets_same_times=int(same_t.sum()),
                                   first_different_basket=first,
                                   pnl_equal_before_it=bool(same_pnl[:pre].all()))
                        if 0 <= first < n:
                            row.update(engine_basket=f"{eb['open_time'].iloc[first]} -> {eb['close_time'].iloc[first]} "
                                                     f"{eb['reason'].iloc[first]} {eb['pnl'].iloc[first]:.2f}",
                                       replay_basket=f"{rb['open_time'].iloc[first]} -> {rb['close_time'].iloc[first]} "
                                                     f"{rb['pnl'].iloc[first]:.2f}")
                        out.append(row)
                        log(f"  {key} {w} STEP {step} cap {cap_name}: engine {row['engine_final']:.2f} replay "
                            f"{row['replay_final']:.2f} (first different basket {first})")
        del prep
    p = work / f"check_{symbol}.json"
    p.write_text(json.dumps(out, indent=1, default=str))
    log(f"-> {p}")


# ───────────────────────────── the report ─────────────────────────────

def load_rows(work: Path) -> pd.DataFrame:
    rows = []
    for p in sorted(work.glob("*.jsonl")):
        rows += [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    d = pd.DataFrame(rows)
    d["symbol"] = d["design"].map(lambda k: DESIGNS[k]["symbol"])
    return d


def window_table(d: pd.DataFrame) -> pd.DataFrame:
    """One row per design x STEP x cap x window. The last year of the tick designs: median final equity and median
    drawdown of the eight loop timings (as published), the worst timing for the risk figures."""
    out = []
    w = d[d["window"] != "roll"]
    for (key, step, cap, win), g in w.groupby(["design", "step", "cap", "window"], sort=False):
        a, z = WINDOWS[win]
        if len(g) > 1:                                        # eight loop timings
            g = g.sort_values("seed")
            order = sorted(zip(g["final_equity"], g["seed"]), key=lambda x: x[0])
            rep = g[g["seed"] == order[len(order) // 2][1]].iloc[0]
            final, dd = float(np.median(g["final_equity"])), float(np.median(g["max_dd_pct"]))
            r = rep.to_dict()
            r.update(final_equity=final, max_dd_pct=dd, dd_worst_pct=float(g["max_dd_pct"].max()),
                     final_min=float(g["final_equity"].min()), final_max=float(g["final_equity"].max()),
                     min_equity=float(g["min_equity"].min()), worst_basket=float(g["worst_basket"].min()),
                     worst_float=float(g["worst_float"].min()), max_lots=float(g["max_lots"].max()),
                     ml_100=float(g["ml_100"].min()), ml_200=float(g["ml_200"].min()),
                     wiped=bool(g["wiped"].any()), wiped_runs=int(g["wiped"].sum()), runs=int(len(g)),
                     mode="every tick, median of 8 loop timings")
        else:
            r = g.iloc[0].to_dict()
            r.update(dd_worst_pct=r["max_dd_pct"], final_min=r["final_equity"], final_max=r["final_equity"],
                     wiped_runs=int(bool(r["wiped"])), runs=1,
                     mode="M1 bars" if DESIGNS[key]["engine"] == "bars" else "per second")
        weeks = _weeks(a, z)
        net = r["final_equity"] - ACCOUNT
        yrs = (_s(z) - _s(a)) / F.YEAR_S
        r.update(window=win, start=a, end=z, name=DESIGNS[key]["name"], net=net, profit_per_week=net / weeks,
                 profit_per_day=net / (weeks * 7.0), return_pct=net / ACCOUNT * 100.0,
                 cagr_pct=((r["final_equity"] / ACCOUNT) ** (1.0 / yrs) - 1.0) * 100.0 if r["final_equity"] > 0 else -100.0,
                 min_equity_pct=r["min_equity"] / ACCOUNT * 100.0)
        out.append(r)
    return pd.DataFrame(out)


def rolling_table(d: pd.DataFrame) -> pd.DataFrame:
    r = d[d["window"] == "roll"].copy()
    r["profit"] = r["final_equity"] - ACCOUNT
    r["profit_per_week"] = r["profit"] / [_weeks(a, z) for a, z in zip(r["start"], r["end"])]
    r["min_equity_pct"] = r["min_equity"] / ACCOUNT * 100.0
    r["recent"] = r["start"] >= RECENT_FIRST
    r["name"] = r["design"].map(lambda k: DESIGNS[k]["name"])
    return r


def rolling_summary(r: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (key, step, cap), g in r.groupby(["design", "step", "cap"], sort=False):
        for which, h in (("all", g), ("last24", g[g["recent"]])):
            i = int(h["max_dd_pct"].to_numpy().argmax())
            out.append(dict(design=key, name=DESIGNS[key]["name"], step=step, cap=cap, starts=which, n=int(len(h)),
                            median_profit=float(h["profit"].median()),
                            p10_profit=float(np.percentile(h["profit"], 10)),
                            median_profit_per_week=float(h["profit_per_week"].median()),
                            share_dd30=float((h["max_dd_pct"] >= 30.0).mean()),
                            share_dd50=float((h["max_dd_pct"] >= 50.0).mean()),
                            share_wiped=float(h["wiped"].astype(bool).mean()),
                            worst_dd=float(h["max_dd_pct"].max()), worst_dd_start=str(h["start"].iloc[i]),
                            lowest_equity_pct=float(h["min_equity_pct"].min()),
                            ml_100=float(h["ml_100"].min()), ml_200=float(h["ml_200"].min()),
                            max_lots=float(h["max_lots"].max())))
    return pd.DataFrame(out)


def criteria(wt: pd.DataFrame, rr: pd.DataFrame) -> pd.DataFrame:
    """Per design x cap x STEP: the worst of every window (the last year's worst loop timing) and every rolling start."""
    out = []
    for (key, cap, step), g in wt.groupby(["design", "cap", "step"], sort=False):
        h = rr[(rr["design"] == key) & (rr["cap"] == cap) & (rr["step"] == step)]
        rec = h[h["recent"]]
        win = {w: g[g["window"] == w].iloc[0] for w in WINDOWS}
        dd_all = max(float(g["dd_worst_pct"].max()), float(h["max_dd_pct"].max()))
        wiped = int(g["wiped_runs"].sum()) + int(h["wiped"].astype(bool).sum())
        ml200 = min(float(g["ml_200"].min()), float(h["ml_200"].min()))
        ml100 = min(float(g["ml_100"].min()), float(h["ml_100"].min()))
        out.append(dict(design=key, name=DESIGNS[key]["name"], cap=cap, step=int(step),
                        ppw_1y=float(win["1y"]["profit_per_week"]), ppw_8y=float(win["8y"]["profit_per_week"]),
                        ppw_5y=float(win["5y"]["profit_per_week"]),
                        ppw_roll24_median=float(rec["profit_per_week"].median()),
                        final_8y=float(win["8y"]["final_equity"]), final_1y=float(win["1y"]["final_equity"]),
                        dd_1y=float(win["1y"]["max_dd_pct"]), dd_1y_worst=float(win["1y"]["dd_worst_pct"]),
                        dd_8y=float(win["8y"]["max_dd_pct"]), dd_5y=float(win["5y"]["max_dd_pct"]),
                        dd_new=float(win["new"]["max_dd_pct"]),
                        dd_roll24_worst=float(rec["max_dd_pct"].max()), dd_roll_worst=float(h["max_dd_pct"].max()),
                        dd_roll24_median=float(rec["max_dd_pct"].median()),
                        share_roll24_dd30=float((rec["max_dd_pct"] >= 30).mean()),
                        share_roll24_dd50=float((rec["max_dd_pct"] >= 50).mean()),
                        dd_worst_anywhere=dd_all,
                        lowest_equity_pct=min(float(g["min_equity_pct"].min()), float(h["min_equity_pct"].min())),
                        ml_100_min=ml100, ml_200_min=ml200, wiped_accounts=wiped,
                        max_lots=max(float(g["max_lots"].max()), float(h["max_lots"].max())),
                        pass_a=bool(wiped == 0 and ml200 >= 100.0), pass_b=bool(dd_all <= 50.0),
                        pass_c=bool(dd_all <= 35.0)))
    return pd.DataFrame(out)


def recommend(cr: pd.DataFrame) -> pd.DataFrame:
    """The lowest STEP that passes, every higher STEP passing too (scanned from $2,500 down)."""
    out = []
    for (key, cap), g in cr.groupby(["design", "cap"], sort=False):
        g = g.sort_values("step", ascending=False)
        row = dict(design=key, name=DESIGNS[key]["name"], cap=cap)
        for c in "abc":
            ok = None
            for _, r in g.iterrows():
                if not r[f"pass_{c}"]:
                    break
                ok = r
            row[f"step_{c}"] = int(ok["step"]) if ok is not None else None
            for f in ("ppw_1y", "ppw_8y", "ppw_roll24_median", "dd_worst_anywhere"):
                row[f"{c}_{f}"] = float(ok[f]) if ok is not None else np.nan
            lower = g[(g["step"] < (ok["step"] if ok is not None else 10 ** 9)) & g[f"pass_{c}"]]
            row[f"{c}_lower_isolated"] = ",".join(str(int(s)) for s in lower["step"])
        out.append(row)
    return pd.DataFrame(out)


def run_combined(work: Path, levels: Optional[Dict[str, tuple]] = None, log=print) -> None:
    """The six accounts summed on a one-minute grid at each set of levels (STEP, cap) per design."""
    from ..engine import fast
    d = load_rows(work)
    wt = window_table(d)
    rr = rolling_table(d)
    rec = recommend(criteria(wt, rr))
    sets = {"today: STEP $2,500, cap 10": {k: (2500, "10") for k in ORDER}}
    for c in "cb":
        for cap in ("10", "none"):
            r = rec[rec["cap"] == cap].set_index("design")
            lv = {k: (int(r.at[k, f"step_{c}"]) if pd.notna(r.at[k, f"step_{c}"]) else 2500,
                      cap if pd.notna(r.at[k, f"step_{c}"]) else "10") for k in ORDER}
            if lv not in sets.values():
                sets[f"({c}) levels, cap {cap} ($2,500 where no lower STEP passes)"] = lv
    if levels:
        sets.update(levels)
    capv = dict(CAPS)
    out = []
    B = BarDesigns(work.parent / "cache", log)
    for w in WINDOWS:
        a, z = WINDOWS[w]
        a_s, z_s = _s(a), _s(z)
        n = (z_s - a_s) // 60
        runs: Dict[tuple, tuple] = {}            # (design, step, cap) -> (minute index, equity, final)
        for sym in ("XAUUSDm", "BTCUSDm"):
            keys = [k for k in ORDER if DESIGNS[k]["symbol"] == sym and DESIGNS[k]["engine"] == "ticks"]
            need = sorted({(k,) + lv[k] for lv in sets.values() for k in keys})
            if not need:
                continue
            prep = fast.prepare(sym, a, z, TFS, mode="ticks" if w == "1y" else "sec")
            for key, step, cap in need:
                seed = None
                if w == "1y":            # the representative loop timing of that sizing (upper median, as published)
                    seed = int(wt[(wt["design"] == key) & (wt["step"] == step) & (wt["cap"] == cap)
                                  & (wt["window"] == "1y")].iloc[0]["seed"])
                res = fast.run(tick_cfg(key, a, z, step, capv[cap], seed, record_s=60), prep)
                e = res.equity
                ix = ((e["time"].astype("int64").to_numpy() // 10 ** 9) - a_s) // 60
                runs[(key, step, cap)] = (ix, e["equity"].to_numpy(np.float64), float(res.scalars["final_equity"]))
                del res, e
            del prep
        for key in (k for k in ORDER if DESIGNS[k]["engine"] == "bars"):
            p, a_ix, z_ix = B.path(key, a, z)
            for step, cap in sorted({lv[key] for lv in sets.values()}):
                (steps, pnl, bal, *_), _b = B.replay(p, a_ix, z_ix, step, capv[cap])
                m = B.m
                eq = _bar_curve(m.c, m.sp, m.k, a_ix, z_ix, p.dir, p.eix, p.xix, p.xpx, p.leg0, p.nleg, p.leix,
                                p.lepx, steps, pnl, ACCOUNT)
                runs[(key, step, cap)] = ((m.t[a_ix:z_ix] - a_s) // 60, eq, float(bal))
        for name, lv in sets.items():
            tot = np.zeros(n)
            for key in ORDER:
                ix, v, _f = runs[(key,) + lv[key]]
                g = np.full(n, np.nan)
                ok = (ix >= 0) & (ix < n)
                g[ix[ok]] = v[ok]
                if np.isnan(g[0]):
                    g[0] = ACCOUNT
                tot += pd.Series(g).ffill().to_numpy()
            peak = np.maximum.accumulate(tot)
            dd = float(((peak - tot) / peak).max() * 100.0)
            final = sum(runs[(k,) + lv[k]][2] for k in ORDER)
            out.append(dict(levels=name, window=w, start=a, end=z, accounts=6, start_equity=6 * ACCOUNT,
                            final_equity=final, net=final - 6 * ACCOUNT,
                            profit_per_week=(final - 6 * ACCOUNT) / _weeks(a, z), max_dd_pct_minute=dd,
                            accounts_detail={k: [lv[k][0], lv[k][1], round(runs[(k,) + lv[k]][2], 2)] for k in ORDER}))
            log(f"  {w} {name}: final {final:,.2f}  combined DD {dd:.1f}%")
    p = work / "combined.json"
    p.write_text(json.dumps(out, indent=1))
    log(f"-> {p}")


def published_check(wt: pd.DataFrame) -> pd.DataFrame:
    """STEP 2,500 with the cap of 10 against the final-ten study's published accounts."""
    pub = pd.read_csv(F.OUT / "results.csv")
    rows = []
    for key, dsg in DESIGNS.items():
        eng = "bars" if dsg["engine"] == "bars" else "ticks"
        for w in WINDOWS:
            p = pub[(pub["symbol"] == dsg["symbol"]) & (pub["label"] == dsg["label"]) & (pub["engine"] == eng)
                    & (pub["window"] == w)].iloc[0]
            r = wt[(wt["design"] == key) & (wt["step"] == 2500) & (wt["cap"] == "10") & (wt["window"] == w)].iloc[0]
            rows.append(dict(design=key, window=w, published_final=float(p["final_equity"]),
                             final=round(float(r["final_equity"]), 2), published_dd=float(p["max_dd_pct"]),
                             dd=round(float(r["max_dd_pct"]), 4), published_trades=int(p["trades"]),
                             trades=int(r["trades"]),
                             final_match=bool(abs(round(float(r["final_equity"]), 2) - float(p["final_equity"])) < 0.005),
                             dd_match=bool(abs(float(r["max_dd_pct"]) - float(p["max_dd_pct"])) < 0.05),
                             trades_match=bool(int(r["trades"]) == int(p["trades"]))))
    return pd.DataFrame(rows)


def _usd(x, d: int = 0) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "-"
    return f"-${abs(x):,.{d}f}" if x < 0 else f"${x:,.{d}f}"


def _pct(x, d: int = 1) -> str:
    if x is None or not np.isfinite(x):
        return "-"
    return f"{x:.{d}f}%"


def _ml(x) -> str:
    if not np.isfinite(x):
        return "-"
    return f"{x:,.0f}%"


def _md(head: List[str], body: List[List[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
                     + ["| " + " | ".join(r) + " |" for r in body])


def write_report(work: Path, out: Path = OUT, log=print) -> None:
    out.mkdir(parents=True, exist_ok=True)
    d = load_rows(work)
    wt = window_table(d)
    rr = rolling_table(d)
    rs = rolling_summary(rr)
    cr = criteria(wt, rr)
    rc = recommend(cr)
    pc = published_check(wt)
    cols = ["design", "name", "symbol", "step", "cap", "window", "start", "end", "mode", "runs", "final_equity", "net",
            "profit_per_week", "profit_per_day", "return_pct", "cagr_pct", "max_dd_pct", "dd_worst_pct", "max_dd_usd",
            "min_equity", "min_equity_pct", "worst_basket", "worst_float", "max_lots", "max_units",
            "longest_underwater_days", "ml_100", "ml_200", "margin_100", "margin_200", "wiped", "wiped_runs",
            "wiped_at", "trades", "final_min", "final_max", "seed", "same_as_capped", "margin_rejects"]
    wt["_o"] = wt["design"].map(ORDER.index)
    wt["_w"] = wt["window"].map(list(WINDOWS).index)
    wt = wt.sort_values(["_o", "cap", "step", "_w"], ascending=[True, True, False, True])
    wt[[c for c in cols if c in wt]].to_csv(out / "results.csv", index=False, float_format="%.4f")
    rcols = ["design", "name", "step", "cap", "start", "end", "recent", "final_equity", "profit", "profit_per_week",
             "max_dd_pct", "min_equity", "min_equity_pct", "worst_basket", "worst_float", "max_lots", "max_units",
             "ml_100", "ml_200", "wiped", "wiped_at", "trades", "same_as_capped", "margin_rejects"]
    rr["_o"] = rr["design"].map(ORDER.index)
    rr = rr.sort_values(["_o", "cap", "step", "start"], ascending=[True, True, False, True])
    rr[[c for c in rcols if c in rr]].to_csv(out / "rolling.csv", index=False, float_format="%.4f")
    rs.to_csv(out / "rolling_summary.csv", index=False, float_format="%.4f")
    cr.to_csv(out / "criteria.csv", index=False, float_format="%.4f")
    rc.to_csv(out / "recommendation.csv", index=False, float_format="%.4f")
    pc.to_csv(out / "published_check.csv", index=False)
    log(f"published figures reproduced: final {pc['final_match'].sum()}/{len(pc)}, DD {pc['dd_match'].sum()}/{len(pc)}, "
        f"trades {pc['trades_match'].sum()}/{len(pc)}")
    checks = []
    for p in sorted(work.glob("check_*.json")):
        checks += json.loads(p.read_text())
    comb = json.loads((work / "combined.json").read_text()) if (work / "combined.json").exists() else []
    const = pd.read_csv(work / "constants.csv") if (work / "constants.csv").exists() else None
    (out / "SIZING.md").write_text(render_md(wt, rr, rs, cr, rc, pc, checks, comb, const), encoding="utf-8")
    log(f"-> {out}")


def _verdict(r) -> str:
    if r["wiped_accounts"] > 0 or r["ml_200_min"] < 100.0:
        return "breaks"
    if r["dd_worst_anywhere"] > 50.0:
        return "too deep"
    if r["dd_worst_anywhere"] > 35.0:
        return "holds, thin margin"
    return "holds"


def design_tables(cr: pd.DataFrame, key: str) -> str:
    g = cr[cr["design"] == key].set_index(["cap", "step"])
    head = ["STEP", "Profit/week last year", "Profit/week 8-yr avg", "Profit/week, median 12 months (last 24 starts)",
            "DD last year (worst timing)", "DD 8 yr", "Worst DD, 12-month starts in the last 24 months",
            "Worst DD anywhere", "Lowest equity", "Margin level min 1:200 / 1:100", "Wiped accounts", "Verdict"]
    parts = []
    for cap, title in (("10", "With the cap of 10 units (0.10 lot), as the bot runs"), ("none", "Without the cap")):
        body = []
        for step in STEPS:
            r = g.loc[(cap, step)]
            last = f"{r['dd_1y']:.1f}%" + (f" ({r['dd_1y_worst']:.1f}%)" if abs(r["dd_1y_worst"] - r["dd_1y"]) >= 0.05 else "")
            body.append([f"${step:,}", _usd(r["ppw_1y"]), _usd(r["ppw_8y"]), _usd(r["ppw_roll24_median"]), last,
                         _pct(r["dd_8y"]), _pct(r["dd_roll24_worst"]), f"**{r['dd_worst_anywhere']:.1f}%**",
                         f"{r['lowest_equity_pct']:.0f}% of $2,000", f"{_ml(r['ml_200_min'])} / {_ml(r['ml_100_min'])}",
                         str(int(r["wiped_accounts"])), _verdict(r)])
        parts.append(f"*{title}:*\n\n" + _md(head, body))
    return "\n\n".join(parts)


def rolling_md(rs: pd.DataFrame, key: str, cap: str = "10") -> str:
    g = rs[(rs["design"] == key) & (rs["cap"] == cap)].set_index(["step", "starts"])
    head = ["STEP"] + [f"{w}: {c}" for w in ("All starts", "Last 24 starts")
                       for c in ("median 12-mo profit", "10th pct", "DD >= 30%", "DD >= 50%", "wiped", "worst DD")]
    body = []
    for step in STEPS:
        row = [f"${step:,}"]
        for which in ("all", "last24"):
            r = g.loc[(step, which)]
            row += [_usd(r["median_profit"]), _usd(r["p10_profit"]), f"{r['share_dd30'] * 100:.0f}%",
                    f"{r['share_dd50'] * 100:.0f}%", f"{r['share_wiped'] * 100:.0f}%", _pct(r["worst_dd"])]
        body.append(row)
    return _md(head, body)


def step_answer(cr: pd.DataFrame, key: str, step: int, cap: str = "10") -> str:
    r = cr[(cr["design"] == key) & (cr["step"] == step) & (cr["cap"] == cap)].iloc[0]
    return (f"${step:,}: **{_verdict(r)}**. Worst DD {r['dd_worst_anywhere']:.1f}% (last year {r['dd_1y']:.1f}%, "
            f"8 years {r['dd_8y']:.1f}%, worst 12-month start of the last 24 {r['dd_roll24_worst']:.1f}%; "
            f"{r['share_roll24_dd50'] * 100:.0f}% of those starts fell 50% or more), lowest equity "
            f"{r['lowest_equity_pct']:.0f}% of the $2,000 start, {int(r['wiped_accounts'])} wiped account(s), margin "
            f"level at least {_ml(r['ml_200_min'])} at 1:200; profit {_usd(r['ppw_1y'])} a week last year, "
            f"{_usd(r['ppw_8y'])} a week on the 8-year average")


def render_md(wt, rr, rs, cr, rc, pc, checks, comb, const) -> str:
    n_roll = len(roll_starts())
    L = []
    L.append("# How low can the step-up balance go? The six demo designs under more aggressive sizing\n")
    L.append("*Study of 2026-11-17, not committed. Code: `backtesting/research/sizing.py`. Data in this folder: "
             "`results.csv` (design x STEP x cap x window), `rolling.csv` (every 12-month start), `rolling_summary.csv`, "
             "`criteria.csv`, `recommendation.csv`, `published_check.csv`.*\n")
    # ── short answer
    L.append("## The answer in short\n")
    rec10 = rc[rc["cap"] == "10"].set_index("design")
    recn = rc[rc["cap"] == "none"].set_index("design")
    c10 = cr[cr["cap"] == "10"].set_index(["design", "step"])
    head = ["Design", "Today, $2,500: profit/week last year / 8-yr avg, worst DD",
            "(a) lowest STEP never wiped, margin >= 100% at 1:200", "(b) lowest STEP with worst DD <= 50%",
            "(c) lowest STEP with worst DD <= 35%", "$750", "$500"]
    body = []
    for key in ORDER:
        r0 = c10.loc[(key, 2500)]
        cells = [DESIGNS[key]["name"], f"{_usd(r0['ppw_1y'])} / {_usd(r0['ppw_8y'])}, {r0['dd_worst_anywhere']:.1f}%"]
        for c in "abc":
            s = rec10.at[key, f"step_{c}"]
            if s is None or (isinstance(s, float) and np.isnan(s)):
                cells.append("none in the grid")
            else:
                cells.append(f"${int(s):,}: {_usd(rec10.at[key, f'{c}_ppw_1y'])} / {_usd(rec10.at[key, f'{c}_ppw_8y'])} a week")
        for st in (750, 500):
            r = c10.loc[(key, st)]
            cells.append(f"{_verdict(r)}: worst DD {r['dd_worst_anywhere']:.0f}%, {int(r['wiped_accounts'])} wiped")
        body.append(cells)
    L.append(_md(head, body) + "\n")
    L.append("Profit a week = net profit of a fresh $2,000 account divided by the weeks of the window (last year: "
             "2025-11-13 to 2026-11-13; 8-yr avg: 2018-11-13 to 2026-11-13). \"Worst DD\" is the deepest fall of equity "
             "(floating losses included) from its running high, in any of the four windows, under any of the eight loop "
             f"timings of the last year, or in any of the {n_roll} rolling 12-month accounts. Cap of 10 units as the bot "
             "runs; without the cap see the design sections.\n")
    # ── the rule
    L.append("## The sizing rule, as found\n")
    if const is not None:
        same = const[["step_up_balance", "unit_max_limit", "mtqty", "virtual_start_balance"]].drop_duplicates()
        L.append(f"- All six demo branches (`symbols.json`, `constants.py`): step_up_balance "
                 f"{', '.join(f'${x:,.0f}' for x in same['step_up_balance'])}, unit_max_limit "
                 f"{', '.join(str(int(x)) for x in same['unit_max_limit'])}, mtqty "
                 f"{', '.join(str(x) for x in same['mtqty'])} lot per unit, VIRTUAL_START_BALANCE "
                 f"{', '.join(f'${x:,.0f}' for x in same['virtual_start_balance'])} plus the bot's own closed P/L "
                 f"(from {const['virtual_start_date'].iloc[0]}).")
    L.append("- `app.py` (baskets): `units = int(balance // step_up_balance) + 1`, then `max(1, min(units, unit_max_limit))`, "
             "re-derived only while the symbol is flat; an open basket keeps its unit, the ladder add of Top 1 is "
             "`multiplier x unit`. `turtle.py` `unit_rule` is the same rule, taken at each Turtle entry; the Turtle's adds "
             "use the trade's unit.")
    L.append("- Backtester: `BacktestConfig` step_up_balance 2500, unit_max_limit 10, mtqty 0.01, initial_balance 2000 "
             "(the tick engine re-derives the unit only while flat); `external.py` STEP_UP 2500, UNIT_MAX 10, ACCOUNT 2000 "
             "(`_account_kernel(..., step_up, unit_max)` sizes each trade and all its legs with one unit).")
    L.append("- The cap binds from a balance of STEP x 9 (STEP $500: $4,500). \"No cap\" below means the same rule with "
             "the limit at 1,000,000 units.\n")
    # ── method and proof
    L.append("## How it was measured, and the checks\n")
    ok_f, ok_d, ok_t = int(pc["final_match"].sum()), int(pc["dd_match"].sum()), int(pc["trades_match"].sum())
    L.append(f"1. **Published figures reproduced.** At STEP $2,500 with the cap of 10, all {len(pc)} published accounts "
             f"(six designs x four windows): final equity to the cent {ok_f}/{len(pc)}, maximum drawdown to 0.1 point "
             f"{ok_d}/{len(pc)}, trade counts {ok_t}/{len(pc)} (`published_check.csv`).")
    L.append("2. **Turtles (M1-bar simulator): the per-unit replay is exact.** The Turtle trade path does not depend on "
             "the account at all; the account kernel only sizes it. `_bar_replay` mirrors the kernel operation for "
             "operation and adds lowest equity, margin and lots. It equals the kernel itself bit for bit (every trade's "
             "P/L, final balance, drawdown, daily marks) at every STEP and cap, in all four windows and all "
             f"{n_roll} rolling starts ({2 * (len(WINDOWS) + n_roll) * len(STEPS) * 2:,} accounts), including STEP "
             "$1,000 and $500 for System 2 over 8 years and the last year.")
    if checks:
        ch = pd.DataFrame(checks)
        L.append("3. **The tick-engine designs: the per-unit premise fails, so the engine itself was re-run at every "
                 "STEP.** The engine, like MT5, rounds each position's floating profit to the cent and compares the "
                 "basket's profit with `unit x target` and `-unit x stop`. Rounding does not scale with the unit, so "
                 "the first poll that crosses a target or a stop can move by a second or more when the unit changes, "
                 "and the exit price and every later trade with it. A per-unit replay of the STEP-$2,500 run (same "
                 "trades, exact cent rounding, only the unit changed) against the engine re-run at the new STEP:")
        body = []
        for _, r in ch.iterrows():
            body.append([DESIGNS[r["design"]]["name"], WINDOW_NAMES[r["window"]].split(",")[0]
                         + (f", timing {int(r['seed'])}" if r["seed"] == r["seed"] and r["seed"] is not None else ""),
                         f"${int(r['step']):,}", r["cap"], _usd(r["engine_final"], 2), _usd(r["replay_final"], 2),
                         _usd(r["diff"], 2), f"{int(r['first_different_basket']) + 1 if r['first_different_basket'] >= 0 else '-'}"
                         f" of {int(r['engine_baskets'])}",
                         "yes" if r["pnl_equal_before_it"] else "no"])
        L.append(_md(["Design", "Window", "STEP", "Cap", "Engine re-run", "Per-unit replay", "Replay - engine",
                      "First basket that differs", "Every basket before it equal to the cent"], body))
        ex = ch[ch["first_different_basket"] >= 0]
        if len(ex) and "engine_basket" in ex:
            e = ex.iloc[0]
            L.append(f"\n   Example ({DESIGNS[e['design']]['name']}, {e['window']}, STEP ${int(e['step']):,}): engine "
                     f"`{e['engine_basket']}`, replay `{e['replay_basket']}`. Every figure of the four tick-engine designs "
                     "in this study is therefore the engine's own run at that STEP (per second for 8 years, 5 years, "
                     "Nov 2018 - Dec 2020 and every rolling start; every tick under the eight loop timings for the last "
                     "year), not a replay.")
    L.append(f"4. **Rolling starts.** A fresh $2,000 account on the 1st of every month from {ROLL_FIRST[:7]} to "
             f"{ROLL_LAST[:7]} ({n_roll} starts), each run for 12 months; \"last 24 months\" = the 24 starts from "
             f"{RECENT_FIRST[:7]}, whose years end between Dec 2024 and Nov 2026. The tick designs run per second, cut out "
             "of one 8-year preparation (checked: the 5-year and Nov 2018 - Dec 2020 windows cut the same way give the "
             "published accounts to the cent, and a rolling start cut out equals the same start prepared on its own).")
    L.append("5. **Breaking** is judged on equity with floating P/L at the engine's own resolution (every poll of the "
             "tick engine; the worst price of every M1 bar for the Turtles): wiped = equity reached 0 (the engine's "
             "stop-out), margin level = equity / margin with margin = lots x contract (gold 100 oz, BTC 1 BTC) x fill "
             "price / leverage, at 1:100 and 1:200, and drawdown >= 50%. The uncapped account is run only where the "
             "capped one reached 10 units; otherwise the two are the same account.\n")
    # ── per design
    L.append("## Design by design\n")
    for key in ORDER:
        dsg = DESIGNS[key]
        L.append(f"### {dsg['name']} (`{dsg['branch']}`)\n")
        L.append(design_tables(cr, key) + "\n")
        r10, rn = rec10.loc[key], recn.loc[key]
        def lv(r, c):
            s = r[f"step_{c}"]
            return "none in the grid" if s is None or (isinstance(s, float) and np.isnan(s)) else f"${int(s):,}"
        L.append(f"Lowest safe STEP, cap 10: (a) {lv(r10, 'a')}, (b) {lv(r10, 'b')}, (c) {lv(r10, 'c')}. "
                 f"Without the cap: (a) {lv(rn, 'a')}, (b) {lv(rn, 'b')}, (c) {lv(rn, 'c')}.\n")
    # ── combined
    if comb:
        L.append("## The six together\n")
        cb = pd.DataFrame(comb)
        body = []
        for _, r in cb.iterrows():
            body.append([r["levels"], WINDOW_NAMES[r["window"]].split(",")[0], _usd(r["start_equity"]),
                         _usd(r["final_equity"]), _usd(r["profit_per_week"]), _pct(r["max_dd_pct_minute"])])
        L.append("Six $2,000 accounts summed minute by minute (one account per bot, as on the demo):\n")
        L.append(_md(["Levels", "Window", "Start", "Final", "Profit/week", "Combined max DD"], body) + "\n")
    return "\n".join(L) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["constants", "bars", "sec", "ticks1y", "check", "combined", "report"])
    ap.add_argument("--symbol", default="XAUUSDm")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--work", type=Path, required=True, help="folder for the run records (JSON lines)")
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--no-roll", action="store_true")
    a = ap.parse_args(argv)
    a.work.mkdir(parents=True, exist_ok=True)
    log = lambda s: print(time.strftime("%H:%M:%S"), s, flush=True)
    if a.cmd == "constants":
        c = pd.DataFrame(demo_constants())
        c.to_csv(a.work / "constants.csv", index=False)
        print(c.to_string())
    elif a.cmd == "bars":
        run_bars(a.work, a.cache, log)
    elif a.cmd == "sec":
        run_sec(a.symbol, a.work, a.workers, roll=not a.no_roll, log=log)
    elif a.cmd == "ticks1y":
        run_ticks1y(a.symbol, a.work, a.workers, log)
    elif a.cmd == "check":
        run_check(a.symbol, a.work, log=log)
    elif a.cmd == "combined":
        run_combined(a.work, log=log)
    elif a.cmd == "report":
        write_report(a.work, OUT, log)


if __name__ == "__main__":
    main()
