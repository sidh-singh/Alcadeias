"""
Silver study, step 'develop' (PREREG_SILVER.md §9.1-3): gates, every variant on DEV, the shortlist, VAL, the finalists.

    python3 -m backtesting.research.silver_develop gates | dev-bars | dev-ticks I N | shortlist | val | finalists

Never reads the hold-out: every load goes through ``silver.load_market`` / ``silver.tick_prepare`` with the step's cut.
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import silver as S
from . import external as X
from . import final10 as F
from . import multisymbol as MS

OUT = S.OUT
DEVD = OUT / "dev"
VALD = OUT / "val"
LOGS = OUT / "logs"
SCR = Path(__import__("os").environ.get("TMPDIR", "/tmp"))


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_hashed(p: Path, text: str) -> str:
    p.write_text(text)
    h = sha(p)
    (p.parent / (p.name + ".sha256")).write_text(f"{h}  {p.name}\n")
    return h


def contexts(cut: str):
    m0 = S.load_market(S.SYM, cut)
    gold = S.load_market(S.GOLD, cut)
    cm = S.cost_markets(m0)
    sig = X.bot_signals(cm["x1"], cache_dir=SCR / "botsig")
    z = S.zones(m0)
    rho = {}
    for clock in ("server", "utc"):
        rho[clock] = S.london_range_pct(cm["x1"], clock, *S.DEV) / S.london_range_pct(gold, clock, *S.DEV)
    ctxs = {k: S.Ctx(m=v, base=cm["x1"], sig=sig, z=z, gold=gold, rho=rho) for k, v in cm.items()}
    return m0, cm, ctxs, rho


# ───────────────────────────── gates (§9.1) and plumbing proofs ─────────────────────────────

def gates() -> None:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        log(f"[{'PASS' if cond else 'FAIL'}] {name}{(': ' + info) if info else ''}")

    # G4: the loader's cut assertion fires on a bar dated 2023-01-01
    try:
        S.guard(np.array([S.s_of("2022-12-30"), S.s_of("2023-01-01")]), S.DEV[1], "G4 test")
        check("G4 the cut assertion fires on a bar dated 2023-01-01", False)
    except S.CutError as e:
        check("G4 the cut assertion fires on a bar dated 2023-01-01", True, str(e)[:80])
    try:
        S.check_cut("2024-07-02")
        check("G4b a load reaching the hold-out is refused before FINALISTS.md.sha256", False)
    except S.CutError:
        check("G4b a load reaching the hold-out is refused before FINALISTS.md.sha256", True)
    m_dev = S.load_market(S.SYM, S.DEV[1])
    check("G4c the DEV market ends before 2023-01-01", int(m_dev.t[-1]) < S.s_of(S.DEV[1]),
          str(pd.Timestamp(int(m_dev.t[-1]), unit="s")))

    # G2: the already-seen silver Turtle + votes streams, 2021-11-13 -> 2024-05-13 (inside DEV+VAL), with the study's
    # own stream code on the multisymbol market (raw spread, no extra slippage)
    m = S.load_market(S.SYM, S.VAL[1])
    sig = X.bot_signals(m, cache_dir=SCR / "botsig")
    a, z = "2021-11-13", "2024-05-13"
    a_ix, z_ix = m.ix(a), m.ix(z)
    want = {1: (-419.40, 1394.55, 23), 2: (-1335.00, 1381.08, 17)}
    for system in (1, 2):
        plan = X.filtered(X.turtle(m, system).plan, m, sig.votes_at)
        p = X.run_path(m, plan, a_ix, z_ix)
        st = S.stream_of(m, p)
        met = S.split_metrics(st, a, z)
        w = want[system]
        n_tr = len(p)
        check(f"G2 silver Turtle S{system} + votes stream {a}..{z}",
              abs(met["profit"] - w[0]) < 0.005 and abs(met["max_dd"] - w[1]) < 0.005 and n_tr == w[2],
              f"profit {met['profit']:.2f} (want {w[0]:.2f}), max DD {met['max_dd']:.2f} (want {w[1]:.2f}), "
              f"trades {n_tr} (want {w[2]})")
        # the same path on the unit-rule account through the study's sizing kernel vs external.account
        bnd = F._day_bounds(m, a_ix, z_ix)
        ref = X.account(m, p, X.BOT, bnd)
        res = size_run(m, p, a_ix, z_ix, mode=1, step=2500.0)
        check(f"G2b S{system}: study sizing kernel (unit rule) = external.account", abs(res["final"] - ref.final) < 0.005,
              f"{res['final']:.2f} vs {ref.final:.2f}; DD {res['ddp']:.4f}% vs {ref.max_dd * 100:.4f}%")
    del m, sig

    # published gold / BTC results (FINAL10.md / results.csv, window 'new' 2018-11-13 -> 2021-01-01), same code paths
    pub = pd.read_csv(S.REPO_ROOT / "backtest_results" / "final10" / "results.csv")
    for sym, label, build in (("XAUUSDm", "London breakout (risk-sized)", "london"),
                              ("BTCUSDm", "Turtle + bot votes", "turtle")):
        r = pub[(pub.symbol == sym) & (pub.label == label) & (pub.window == "new") & (pub.engine == "bars")].iloc[0]
        mk = X.load_market(sym, earliest=F.HISTORY_FROM[sym], end=F.DATA_END)
        a_ix, z_ix = mk.ix("2018-11-13"), mk.ix("2021-01-01")
        if build == "london":
            b = X.london_breakout(mk, "server")
            plan, mode, rf = b.risk, 3, 0.01
        else:
            sg = X.bot_signals(mk, cache_dir=SCR / "botsig")
            plan, mode, rf = X.filtered(X.turtle(mk, 1).plan, mk, sg.votes_at), 1, 0.0
        p = X.run_path(mk, plan, a_ix, z_ix)
        if mode == 1:
            res = size_run(mk, p, a_ix, z_ix, mode=1, step=2500.0)
            fin, n, ddp = res["final"], res["n_taken"], res["ddp"]
        else:
            bnd = F._day_bounds(mk, a_ix, z_ix)
            rr = X.account(mk, p, X.Sizing("risk", rf=rf), bnd)
            fin, n, ddp = rr.final, len(rr.trades_pnl), rr.max_dd * 100
        check(f"published {sym} {label} (new window) reproduced", abs(fin - r.final_equity) < 0.005 and n == r.trades,
              f"final {fin:.2f} (published {r.final_equity:.2f}), trades {n} ({int(r.trades)}), DD {ddp:.4f}% "
              f"({r.max_dd_pct:.4f}%)")
        del mk

    # G3, bar engine: one DEV month (March 2021): P/L = move x lots x 5,000 after removing the slippage, and the
    # slippage = count x spread x k
    m0, cm, ctxs, rho = contexts(S.DEV[1])
    log(f"rho (silver/gold London-window range in % of price, DEV): {rho}")
    c = ctxs["x1"]
    for vid, fn in (("C14[R=30,Xt=13:25]", lambda: S.c14(c, 30, "13:25")),
                    ("C03[P=4,kN=2.0,votes=False]", lambda: S.c03(c, 4, 2.0, False))):
        spec = fn()
        a_ix, z_ix = c.m.ix("2021-03-01"), c.m.ix("2021-04-01")
        p = S.paths_of(c, spec, a_ix, z_ix)
        pc, n_in, n_out = S.costed(c.m, p, c.z, spec.stop_entry, True)
        gross_legs = 0.0
        slip = 0.0
        moves = 0.0
        for i in range(len(p)):
            for q in range(p.leg0[i], p.leg0[i] + p.nleg[i]):
                moves += p.dir[i] * (p.xpx[i] - p.lepx[q]) * 0.01 * S.CONTRACT
                gross_legs += p.dir[i] * (pc.xpx[i] - pc.lepx[q]) * 0.01 * S.CONTRACT
        # recount the slippage independently
        for i in range(len(p)):
            for q in range(p.leg0[i], p.leg0[i] + p.nleg[i]):
                e = p.leix[q]
                if spec.stop_entry or q > p.leg0[i] or c.z.reopen5[e]:
                    slip += c.m.sp[e] * S.K
            x = min(p.xix[i], len(c.m) - 1)
            if p.why[i] != 4 and (p.why[i] in (2, 5) or c.z.reopen5[x]):
                slip += c.m.sp[x] * S.K * p.nleg[i]
        st = S.stream_of(c.m, pc)
        check(f"G3 bars {vid} March 2021: net P/L + slippage = price move x lots x 5,000",
              abs(gross_legs + slip - moves) < 0.005 and abs(st.tr.pnl.sum() - gross_legs) < 0.005,
              f"{len(p)} trades, {n_in + n_out} charged fills, move ${moves:.2f}, net ${gross_legs:.2f}, slippage ${slip:.2f}")
    # hand check: C14 R=30, 13:25 on three DEV days, printed with its range, levels and fills
    hand_check(c)

    # G3, tick engine: V3-lite on March 2021
    prep = S.tick_prepare("2021-03-01", "2021-04-01")
    from ..engine import fast
    for key, p_ in (("v3lite", dict(tv=8.0, sv=8.0)), ("gtop2", dict(tv=8.0, sv=4.0, cap=14.72))):
        cfg = S.tick_cfg(key, p_, "2021-03-01", "2021-04-01")
        pr = S.tick_cost(prep, "x1")
        res = fast.run(cfg, pr)
        st = S.tick_stream(res, pr, "x1")
        f = res.fills
        cl = f[f.action == "close"]
        move = float((np.where(cl.side == "BUY", 1, -1) * (cl.price - cl.pos_open_price) * cl.lots * S.CONTRACT).sum())
        # a close fill's side is the position's side
        bp = float(res.baskets.pnl.sum())
        ext = float(st.tr.extra.sum())
        check(f"G3 ticks {key} March 2021: basket P/L = move x lots x 5,000; slippage = count x spread x k",
              abs(move - bp) < 0.02 and abs(st.tr.pnl.sum() + ext - bp) < 0.005,
              f"{len(res.baskets)} baskets, move ${move:.2f}, engine ${bp:.2f}, extra ${ext:.2f} on {st.n_extra} fills; "
              f"mae sign: min {res.baskets.mae.min():.2f} max {res.baskets.mae.max():.2f}")
    log("GATES: ALL PASS" if ok_all else "GATES: SOME FAILED")


def hand_check(c) -> None:
    """One candidate's trades by hand: C14 (R = 30, exit 13:25 NY) on 4, 5 and 8 March 2021 (2 and 3 March have no
    quotes in the store between 08:25 and 13:25 NY)."""
    m = c.m
    spec = S.c14(c, 30, "13:25")
    a_ix, z_ix = m.ix("2021-03-04"), m.ix("2021-03-09")
    p = S.paths_of(c, spec, a_ix, z_ix)
    pc, _, _ = S.costed(m, p, c.z, True, True)
    day, minute = S._ny(m)
    lines = ["C14 R=30, exit 13:25 NY, 2021-03-04..08 (NY times; bid prices; buys fill at the ask):"]
    for d in np.unique(day[a_ix:z_ix]):
        sel = np.flatnonzero((day == d) & (minute >= 505) & (minute < 535))
        if not len(sel):
            continue
        H, L = m.h[sel].max(), m.l[sel].min()
        lines.append(f"  {pd.Timestamp(int(d) * 86400, unit='s').date()}: range 08:25-08:55 high {H:.3f} low {L:.3f}; "
                     f"buy stop {H + S.TICK:.3f}, sell stop {L - S.TICK:.3f}, stop at the other side")
    for i in range(len(p)):
        e, x = p.eix[i], min(p.xix[i], len(m) - 1)
        side = "BUY" if p.dir[i] > 0 else "SELL"
        sp_e, sp_x = m.sp[e], m.sp[x]
        by_hand = p.dir[i] * (pc.xpx[i] - pc.lepx[p.leg0[i]]) * S.K
        lines.append(f"  trade {i + 1}: {side} at {pd.Timestamp(int(m.t[e]), unit='s', tz='UTC').tz_convert(S.NY):%Y-%m-%d %H:%M} "
                     f"fill {p.epx[i]:.3f} (+ {sp_e:.3f} stop-entry slippage -> {pc.lepx[p.leg0[i]]:.3f}); "
                     f"exit {X.WHY_NAMES[int(p.why[i])]} at {pd.Timestamp(int(m.t[x]), unit='s', tz='UTC').tz_convert(S.NY):%H:%M} "
                     f"price {p.xpx[i]:.3f}{f' (+ stop slippage {sp_x:.3f} -> {pc.xpx[i]:.3f})' if p.why[i] in (2, 5) else ''}; "
                     f"P/L by hand ({pc.xpx[i]:.3f} - {pc.lepx[p.leg0[i]]:.3f}) x {int(p.dir[i]):+d} x $50 = ${by_hand:.2f}")
    st = S.stream_of(m, pc)
    lines.append(f"  stream trades' P/L: {', '.join(f'${x:.2f}' for x in st.tr.pnl)}")
    (LOGS / "hand_check_C14.txt").write_text("\n".join(lines) + "\n")
    for ln in lines:
        log(ln)


def size_run(m, p, a_ix, z_ix, mode, step=2500.0, r=0.01, W=1.0, D=None, pmx=None, bal0=2000.0):
    e0 = np.array([p.leix[p.leg0[i]:p.leg0[i] + p.nleg[i]].min() if p.nleg[i] else p.eix[i] for i in range(len(p))],
                  np.int64)
    o = np.argsort(e0, kind="stable")
    legs = [np.arange(p.leg0[i], p.leg0[i] + p.nleg[i]) for i in o]
    li = np.concatenate(legs) if legs else np.zeros(0, np.int64)
    nleg = p.nleg[o]
    leg0 = np.concatenate([[0], np.cumsum(nleg)[:-1]]).astype(np.int64) if len(o) else np.zeros(0, np.int64)
    Dv = np.ones(len(p)) if D is None else np.asarray(D, float)[o]
    pm = np.ones(len(p)) if pmx is None else np.asarray(pmx, float)[o]
    out = S._size_kernel(m.t, m.c, m.h, m.l, m.sp, m.k, p.dir[o], e0[o], np.minimum(p.xix[o], len(m) - 1), p.xpx[o],
                         p.why[o], leg0, nleg, p.leix[li], p.lepx[li], Dv, pm, int(mode), float(step), float(r), float(W),
                         int(a_ix), int(z_ix), float(bal0), 10.0)
    E_c, E_w, U, units, taken, fin, dd, ddu, wiped, wj, stress, sj = out
    return dict(E_c=E_c, E_w=E_w, U=U, units=units, taken=taken, final=float(fin), ddp=float(dd) * 100.0,
                ddu=float(ddu), wiped=bool(wiped), wipe_t=int(m.t[wj]) if wiped else None, n_taken=int(taken.sum()),
                n_trades=len(p), stress=float(stress), stress_t=int(m.t[sj]) if sj >= 0 else None, order=o)


# ───────────────────────────── running variants on a split ─────────────────────────────

SPLITS = {"DEV": S.DEV, "H1": S.HALVES[0], "H2": S.HALVES[1], "VAL": S.VAL}


def _rows(v, cost, st, splits, spread, extra=None):
    rows = []
    for name in splits:
        a, z = SPLITS[name]
        met = S.split_metrics(st, a, z, spread)
        rows.append(dict(vid=v.vid, cid=v.cid, family=v.family, flags=v.flags, engine=v.engine,
                         params=json.dumps({k: v.params[k] for k in v.params if k != "key"}), cost=cost, split=name,
                         n_extra=st.n_extra, **met, **(extra or {})))
    return rows


def run_bars(period: str, vids=None) -> None:
    """Every bar variant (or ``vids``) on DEV (``period`` 'dev', data cut 2023-01-01) or VAL ('val', cut 2024-07-01),
    continuous from 2018-11-01."""
    cut = S.DEV[1] if period == "dev" else S.VAL[1]
    splits = ("DEV", "H1", "H2") if period == "dev" else ("VAL", "DEV")
    d_out = (DEVD if period == "dev" else VALD)
    (d_out / "streams").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    m0, cm, ctxs, rho = contexts(cut)
    log(f"{period}: market to {pd.Timestamp(int(m0.t[-1]), unit='s')} ({len(m0):,} bars), votes ready, rho {rho} "
        f"({time.time() - t0:.0f}s)")
    spread = cm["x1"].sp
    V = [v for v in S.registry() if v.engine == "bars" and (vids is None or v.vid in vids)]
    rows, weekly = [], {}
    for v in V:
        t1 = time.time()
        try:
            out = S.run_bar_variant(v, ctxs, S.DEV[0])
        except Exception as e:                         # §4.4: recorded as not run, still counted in N
            log(f"  {v.vid}: NOT RUN ({type(e).__name__}: {e})")
            rows.append(dict(vid=v.vid, cid=v.cid, family=v.family, flags=v.flags, engine="bars", cost="x1",
                             split=splits[0], not_run=f"{type(e).__name__}: {e}"))
            continue
        for cost, (st, spec, p, pc) in out.items():
            rows += _rows(v, cost, st, splits, spread)
        st = out["x1"][0]
        weekly[v.vid] = S.weekly_pnl(st, *SPLITS[splits[0]])
        de, deq = S.daily_eq(st, S.DEV[0], cut)
        with open(d_out / "streams" / f"{_fn(v.vid)}.pkl", "wb") as fh:
            pickle.dump(dict(day=de, eq=deq, tr=st.tr), fh)
        r = rows[-len(splits) * 4]
        log(f"  {v.vid:42s} {time.time() - t1:5.1f}s trades {r.get('trades')}")
    pd.DataFrame(rows).to_csv(d_out / "bars_runs.csv", index=False)
    np.savez(d_out / "weekly_bars_x1.npz", **{_fn(k): w for k, w in weekly.items()})
    log(f"{period} bars: {len(V)} variants in {time.time() - t0:.0f}s")


def _fn(vid: str) -> str:
    return vid.replace("[", "__").replace("]", "").replace("=", "-").replace(",", "_").replace("/", "-").replace(":", "")


def run_ticks(period: str, part: int, nparts: int, vids=None) -> None:
    from ..engine import fast
    a, z = (S.DEV if period == "dev" else S.VAL)
    d_out = (DEVD if period == "dev" else VALD) / "ticks"
    d_out.mkdir(parents=True, exist_ok=True)
    V = [v for v in S.registry() if v.engine == "ticks" and (vids is None or v.vid in vids)]
    costs = ("x1", "x15", "pct", "gross")
    jobs = [(v, c) for v in V for c in costs][part::nparts]
    if not jobs:
        return
    t0 = time.time()
    prep = S.tick_prepare(a, z)
    log(f"ticks {period} part {part}/{nparts}: {prep.n_rows:,} rows ({time.time() - t0:.0f}s), {len(jobs)} runs")
    m1 = S.load_market(S.SYM, z)
    spread = S.cost_markets(m1)["x1"].sp
    for v, cost in jobs:
        f = d_out / f"{_fn(v.vid)}__{cost}.pkl"
        if f.exists():
            continue
        t1 = time.time()
        cfg = S.tick_cfg(v.params["key"], v.params, a, z)
        pr = S.tick_cost(prep, cost)
        res = fast.run(cfg, pr, light=False)
        st = S.tick_stream(res, pr, cost)
        st_split = ("DEV",) if period == "dev" else ("VAL",)
        rows = []
        for name in st_split:
            met = S.split_metrics(st, a, z, None)
            ia, iz = m1.ix(a), m1.ix(z)
            met["median_spread"] = round(float(np.median(spread[ia:iz])), 4)
            rows.append(dict(vid=v.vid, cid=v.cid, family=v.family, flags=v.flags, engine="ticks",
                             params=json.dumps({k: v.params[k] for k in v.params if k != "key"}), cost=cost, split=name,
                             n_extra=st.n_extra, **met))
        if period == "dev":
            for hn in ("H1", "H2"):
                met = S.split_metrics(st, *SPLITS[hn])
                rows.append(dict(vid=v.vid, cid=v.cid, family=v.family, flags=v.flags, engine="ticks",
                                 params=json.dumps({k: v.params[k] for k in v.params if k != "key"}), cost=cost,
                                 split=hn, n_extra=st.n_extra, **met))
        with open(f, "wb") as fh:
            day, eq = S.daily_eq(st, a, z)
            pickle.dump(dict(rows=rows, tr=st.tr, day=day, eq=eq, weekly=S.weekly_pnl(st, a, z)), fh)
        log(f"  {v.vid:36s} {cost:5s} {time.time() - t1:5.1f}s baskets {len(st.tr)}")
        del res, pr
    log(f"ticks part {part} done in {time.time() - t0:.0f}s")


# ───────────────────────────── the shortlist (§5.1) ─────────────────────────────

def _hold_need(h: float) -> int:
    if not np.isfinite(h):
        return 10**9
    return 12 if h > 120 else (40 if h >= 24 else 150)


def collect(period: str) -> pd.DataFrame:
    d_out = DEVD if period == "dev" else VALD
    rows = [pd.read_csv(d_out / "bars_runs.csv")] if (d_out / "bars_runs.csv").exists() else []
    tk = []
    for f in sorted((d_out / "ticks").glob("*.pkl")):
        with open(f, "rb") as fh:
            tk += pickle.load(fh)["rows"]
    if tk:
        rows.append(pd.DataFrame(tk))
    return pd.concat(rows, ignore_index=True)


def weekly_matrix(period: str, vids, split: str = "DEV") -> np.ndarray:
    d_out = DEVD if period == "dev" else VALD
    wb = np.load(d_out / "weekly_bars_x1.npz") if (d_out / "weekly_bars_x1.npz").exists() else {}
    cols = []
    for vid in vids:
        k = _fn(vid)
        if k in wb:
            cols.append(wb[k])
            continue
        f = d_out / "ticks" / f"{k}__x1.pkl"
        if f.exists():
            with open(f, "rb") as fh:
                cols.append(pickle.load(fh)["weekly"])
        else:
            cols.append(None)
    n = max(len(c) for c in cols if c is not None)
    return np.column_stack([c if c is not None and len(c) == n else np.zeros(n) for c in cols])


def haircut(D: pd.DataFrame, W: np.ndarray, N: int) -> pd.DataFrame:
    """DSR per variant (N trials, cross-variant variance of the weekly SR), E[max SR], the SPA p-value of the set."""
    sr = D["sr_w_raw"].to_numpy(float)
    T = int(W.shape[0])
    var = float(np.nanvar(sr, ddof=1))
    sr0 = S.expected_max_sr(var, N)
    sr0_null = S.expected_max_sr(1.0 / (T - 1), N)
    D = D.copy()
    D["dsr"] = [S.dsr(a, T, b, c, sr0) for a, b, c in zip(sr, D["skew_w"], D["kurt_w"])]
    D["dsr_null"] = [S.dsr(a, T, b, c, sr0_null) for a, b, c in zip(sr, D["skew_w"], D["kurt_w"])]
    D["e_max_sr_ann"] = round(sr0 * math.sqrt(52), 4)
    D["e_max_sr_null_ann"] = round(sr0_null * math.sqrt(52), 4)
    p, best = S.spa_test(W)
    D["spa_p_set"] = round(p, 4)
    D["spa_best"] = D["vid"].iloc[best]
    D["n_trials"] = N
    return D


def shortlist() -> None:
    R = collect("dev")
    R.to_csv(OUT / "dev_results.csv", index=False)
    V = S.registry()
    nb = S.neighbours(V)
    get = lambda cost, split: R[(R.cost == cost) & (R.split == split)].set_index("vid")
    d1x, d15, h1, h2 = get("x1", "DEV"), get("x15", "DEV"), get("x1", "H1"), get("x1", "H2")
    rows = []
    for v in V:
        r = d1x.loc[v.vid] if v.vid in d1x.index else None
        if r is None or ("not_run" in r and isinstance(r.get("not_run"), str)):
            rows.append(dict(vid=v.vid, cid=v.cid, family=v.family, flags=v.flags, not_run=True))
            continue
        need = _hold_need(r.avg_hold_h)
        nbs = nb[v.vid]
        if nbs:
            d5 = all(d1x.loc[n].profit > 0 for n in nbs)
            d5_how = "neighbours " + " ".join(f"{d1x.loc[n].profit:+.0f}" for n in nbs)
        else:
            d5 = h1.loc[v.vid].profit > 0 and h2.loc[v.vid].profit > 0
            d5_how = f"halves {h1.loc[v.vid].profit:+.0f} / {h2.loc[v.vid].profit:+.0f}"
        g = dict(D1=r.trades >= need, D2=(r.profit > 0) and (d15.loc[v.vid].profit > 0),
                 D3=(r.pos_q_share >= 0.5) if np.isfinite(r.pos_q_share) else False,
                 D4=(r.profit_dd >= 1.0) if np.isfinite(r.profit_dd) else False, D5=bool(d5), D6=r.max_dd < 2000.0)
        if v.cid == "C29" and v.params["filt"] == "gold":
            twin = [w for w in V if w.cid == "C29" and w.params["base"] == v.params["base"] and w.params["filt"] == "silver"][0]
            g["D7"] = bool(np.nan_to_num(r.profit_dd, nan=-9) > np.nan_to_num(d1x.loc[twin.vid].profit_dd, nan=-9))
        rows.append(dict(vid=v.vid, cid=v.cid, family=v.family, flags=v.flags, not_run=False,
                         profit=r.profit, profit_x15=d15.loc[v.vid].profit, max_dd=r.max_dd, profit_dd=r.profit_dd,
                         ann_profit_dd=r.ann_profit_dd, pos_q_share=r.pos_q_share, trades=r.trades, need=need,
                         avg_hold_h=r.avg_hold_h, sharpe_w=r.sharpe_w, sr_w_raw=r.sr_w_raw, skew_w=r.skew_w,
                         kurt_w=r.kurt_w, d5_how=d5_how, **g, passed=all(g.values())))
    D = pd.DataFrame(rows)
    ok = D[~D.not_run]
    W = weekly_matrix("dev", ok.vid.tolist())
    ok = haircut(ok, W, S.N_TRIALS)
    D = D.merge(ok[["vid", "dsr", "dsr_null", "e_max_sr_ann", "e_max_sr_null_ann", "spa_p_set", "spa_best", "n_trials"]],
                on="vid", how="left")
    D.to_csv(DEVD / "shortlist_table.csv", index=False)
    sl = D[D.passed == True]                                        # noqa: E712
    gates_ = ["D1", "D2", "D3", "D4", "D5", "D6"]
    fail_counts = {g: int((~D[g].fillna(False).astype(bool) & ~D.not_run).sum()) for g in gates_}
    lines = ["# Silver study: the DEV shortlist (PREREG_SILVER.md §5.1)", "",
             f"- Written {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}, before any VAL run.",
             f"- Variants: {len(D)} (N = {S.N_TRIALS}); not run: {int(D.not_run.sum())}.",
             f"- DEV 2018-11-01 → 2023-01-01, per-unit streams (0.01 lot), costs × 1.0 and × 1.5 (§2).",
             f"- Multiple testing over the {len(ok)} run variants: E[max weekly Sharpe] of {S.N_TRIALS} trials, annualised: "
             f"{ok.e_max_sr_ann.iloc[0]:.2f} with the cross-variant variance, {ok.e_max_sr_null_ann.iloc[0]:.2f} under a "
             f"pure-noise null of {W.shape[0]} weeks. Hansen SPA (best variant {ok.spa_best.iloc[0]}): "
             f"p = {ok.spa_p_set.iloc[0]:.3f}.",
             f"- Variants failing each rule: " + ", ".join(f"{g} {n}" for g, n in fail_counts.items()) + ".", ""]
    if len(sl):
        lines += [f"**Shortlisted: {len(sl)}.**", "",
                  "| Variant | Family | Flags | DEV profit ×1.0 | ×1.5 | Max DD | Profit/DD | Pos. quarters | Trades (need) | Mean hold h | Sharpe (wk, ann.) | DSR | D5 |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in sl.sort_values("ann_profit_dd", ascending=False).iterrows():
            lines.append(f"| {r.vid} | {r.family} | {r['flags']} | {r.profit:+,.0f} | {r.profit_x15:+,.0f} | {r.max_dd:,.0f} | "
                         f"{r.profit_dd:.2f} | {r.pos_q_share:.0%} | {int(r.trades)} ({int(r.need)}) | {r.avg_hold_h:.0f} | "
                         f"{r.sharpe_w:.2f} | {r.dsr:.2f} | {r.d5_how} |")
    else:
        lines += ["**The shortlist is empty.** By §5.2 there are no finalists and the hold-out is not run.", ""]
    near = D[~D.not_run & (D.passed != True)].sort_values("ann_profit_dd", ascending=False).head(6)   # noqa: E712
    lines += ["", "**The six closest variants that did not pass** (by DEV annualised profit/DD, for information; "
              "rules D1 trades, D2 profit at ×1.0 and ×1.5, D3 positive quarters ≥ 50%, D4 profit/DD ≥ 1.0, "
              "D5 neighbours or halves positive, D6 max DD < $2,000, D7 gold filter beats silver's):", "",
              "| Variant | Flags | DEV profit ×1.0 | ×1.5 | Max DD | Profit/DD | Pos. quarters | Trades (need) | Failed | D5 detail | DSR (prereg) | DSR vs noise null |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in near.iterrows():
        failed = [g for g in gates_ + ["D7"] if g in r and r[g] is not None and r[g] == r[g] and not bool(r[g])]
        lines.append(f"| {r.vid} | {r['flags'] if isinstance(r['flags'], str) else ''} | {r.profit:+,.0f} | {r.profit_x15:+,.0f} | "
                     f"{r.max_dd:,.0f} | {r.profit_dd:.2f} | {r.pos_q_share:.0%} | {int(r.trades)} ({int(r.need)}) | "
                     f"{' '.join(failed)} | {r.d5_how} | {r.dsr:.2f} | {r.dsr_null:.2f} |")
    lines += ["", "The full table (every variant, every rule) is `dev/shortlist_table.csv`; the per-split metrics are "
              "`dev_results.csv`."]
    h = write_hashed(OUT / "SHORTLIST.md", "\n".join(lines) + "\n")
    log(f"SHORTLIST.md written ({len(sl)} variants), sha256 {h}")


# ───────────────────────────── VAL and the finalists (§5.2) ─────────────────────────────

def _shortlisted():
    f = OUT / "SHORTLIST.md"
    h = (OUT / "SHORTLIST.md.sha256").read_text().split()[0]
    if sha(f) != h:
        raise RuntimeError("SHORTLIST.md does not match its sha256")
    D = pd.read_csv(DEVD / "shortlist_table.csv")
    return D[D.passed == True]                                    # noqa: E712


def val_runs(part: int = -1, nparts: int = 1) -> None:
    sl = _shortlisted()
    V = {v.vid: v for v in S.registry()}
    bars = [x for x in sl.vid if V[x].engine == "bars"]
    ticks = [x for x in sl.vid if V[x].engine == "ticks"]
    if part < 0:
        if bars:
            run_bars("val", set(bars))
    elif ticks:
        run_ticks("val", part, nparts, set(ticks))


def val_select() -> None:
    sl = _shortlisted()
    V = {v.vid: v for v in S.registry()}
    R = collect("val")
    R = R[R.split == "VAL"]
    R.to_csv(OUT / "val_results.csv", index=False)
    dev = pd.read_csv(OUT / "dev_results.csv")
    dx = dev[(dev.cost == "x1") & (dev.split == "DEV")].set_index("vid")
    vx, v15 = R[R.cost == "x1"].set_index("vid"), R[R.cost == "x15"].set_index("vid")
    rows = []
    for vid in sl.vid:
        r, r15, d = vx.loc[vid], v15.loc[vid], dx.loc[vid]
        need = {12: 3, 40: 10, 150: 40}[_hold_need(r.avg_hold_h)] if np.isfinite(r.avg_hold_h) else 10**9
        e = dict(E_profit=(r.profit > 0) and (r15.profit > 0), E_trades=r.trades >= need,
                 E_dd=r.max_dd <= 1.5 * d.max_dd)
        rows.append(dict(vid=vid, cid=V[vid].cid, family=V[vid].family, flags=V[vid].flags,
                         dev_profit=d.profit, dev_max_dd=d.max_dd, dev_ann_pdd=d.ann_profit_dd,
                         val_profit=r.profit, val_profit_x15=r15.profit, val_profit_pct=R[(R.cost == "pct")].set_index("vid").profit.get(vid, np.nan),
                         val_profit_gross=R[(R.cost == "gross")].set_index("vid").profit.get(vid, np.nan),
                         val_max_dd=r.max_dd, val_ann_pdd=r.ann_profit_dd, val_trades=r.trades, val_need=need,
                         val_hold_h=r.avg_hold_h, val_sharpe=r.sharpe_w, sr_w_raw=r.sr_w_raw, skew_w=r.skew_w,
                         kurt_w=r.kurt_w, val_median_spread=r.median_spread, **e, eligible=all(e.values()),
                         score=min(d.ann_profit_dd, r.ann_profit_dd)))
    T = pd.DataFrame(rows)
    if len(T):
        Wv = weekly_matrix("val", T.vid.tolist())
        Wd = weekly_matrix("dev", T.vid.tolist())
        T["devval_sharpe"] = [float(np.mean(np.r_[Wd[:, i], Wv[:, i]]) / np.std(np.r_[Wd[:, i], Wv[:, i]], ddof=1) * math.sqrt(52))
                              for i in range(len(T))]
        T = haircut(T.rename(columns={}), Wv, max(len(T), 2)) if len(T) >= 2 else T
    T.to_csv(VALD / "val_table.csv", index=False)
    log(f"VAL: {len(T)} shortlisted, {int(T.eligible.sum()) if len(T) else 0} eligible")


if __name__ == "__main__":
    cmd = sys.argv[1]
    LOGS.mkdir(parents=True, exist_ok=True)
    if cmd == "gates":
        gates()
    elif cmd == "dev-bars":
        run_bars("dev")
    elif cmd == "dev-ticks":
        run_ticks("dev", int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "shortlist":
        shortlist()
    elif cmd == "val-bars":
        val_runs()
    elif cmd == "val-ticks":
        val_runs(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "val-select":
        val_select()
