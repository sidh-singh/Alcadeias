"""The 'portfolio' step of the multi-symbol study: PREREG.md §§8 - 9 applied to the finished runs.

Reads only the run step's outputs (``backtest_results/multisymbol/runs/``) and writes
``selection.csv``, ``portfolio_curve.csv``, ``portfolio_members.csv``, ``correlation.csv``, ``swap.csv`` and
``usdjpy_badtick.csv`` next to them. No engine run, except the USDJPYm bad-quote sensitivity (M1 Turtle, in memory).

    python -m backtesting.research.multiportfolio all
"""
from __future__ import annotations

import argparse
import math
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import multisymbol as MS

OUT = MS.OUT
RUNS = MS.RUNS
ACC0 = MS.ACCOUNT
SCOPE_SYMBOLS = tuple(s for s in MS.UNIVERSE if s in MS.SCOPE)          # §1 order, budget scope (DEVIATIONS C)
EVIDENCE = {k: ("sel" if k in MS.BASKETS else "tsel") for k in MS.DESIGN_ORDER}
WEEKS = {p: (MS.to_ms(MS.PERIODS[p][1]) - MS.to_ms(MS.PERIODS[p][0])) / MS.WEEK_MS for p in ("sel", "conf")}
BASE_PAIRS = [("XAUUSDm", k) for k in MS.BASE["XAUUSDm"]] + [("BTCUSDm", k) for k in MS.BASE["BTCUSDm"]]


def summary() -> pd.DataFrame:
    d = pd.read_csv(RUNS / "summary.csv")
    d["csv_row"] = d.index + 2          # the line number in runs/summary.csv (header = line 1)
    return d


def row(s: pd.DataFrame, sym: str, design: str, period: str, account: str) -> pd.Series:
    r = s[(s.symbol == sym) & (s.design == design) & (s.period == period) & (s.account == account)]
    if len(r) != 1:
        raise KeyError((sym, design, period, account, len(r)))
    return r.iloc[0]


# ───────────────────────────── §8.1 - 8.4: selection ─────────────────────────────

def selection(s: pd.DataFrame) -> pd.DataFrame:
    present = set(s[s.role == "new"].symbol)
    rows = []
    for sym in SCOPE_SYMBOLS:
        if sym not in present:
            continue
        for k in MS.DESIGN_ORDER:
            ev = EVIDENCE[k]
            st, b = row(s, sym, k, ev, "stream"), row(s, sym, k, ev, "b")
            basket = k in MS.BASKETS
            q1 = st.profit > 0
            q2 = st.profit_per_dd >= 1.0
            q3 = (st.pos_quarters >= 6) if basket else (st.pos_halfyears >= 6)
            q4 = st.trades >= (60 if basket else 25)
            q5 = (not bool(b.wiped)) and b.max_dd_pct <= 50.0
            rows.append(dict(symbol=sym, design=k, design_name=MS.DESIGN_NAME[k], evidence=ev,
                             profit=st.profit, max_dd_usd=st.max_dd_usd, profit_per_dd=st.profit_per_dd,
                             blocks_pos=int(st.pos_quarters if basket else st.pos_halfyears),
                             blocks_n=int(st.n_quarters if basket else st.n_halfyears), trades=int(st.trades),
                             b_wiped=bool(b.wiped), b_max_dd_pct=b.max_dd_pct, sharpe_weekly=st.sharpe_weekly,
                             Q1=q1, Q2=q2, Q3=q3, Q4=q4, Q5=q5, qualified=bool(q1 and q2 and q3 and q4 and q5),
                             summary_row_stream=int(st.csv_row), summary_row_b=int(b.csv_row),
                             _si=MS.UNIVERSE.index(sym), _di=MS.DESIGN_ORDER.index(k)))
    t = pd.DataFrame(rows)
    t["_sh"] = t.sharpe_weekly.fillna(-np.inf)
    t = t.sort_values(["qualified", "_sh", "profit_per_dd", "_si", "_di"],
                      ascending=[False, False, False, True, True]).reset_index(drop=True)
    t.insert(0, "rank", np.arange(1, len(t) + 1))
    return t.drop(columns=["_si", "_di", "_sh"])


# ───────────────────────────── daily equity ─────────────────────────────

_DAILY: Dict[str, pd.DataFrame] = {}


def daily(sym: str, design: str, period: str, account: str) -> pd.Series:
    if sym not in _DAILY:
        _DAILY[sym] = pd.read_csv(RUNS / sym / "daily.csv.gz")
    d = _DAILY[sym]
    d = d[(d.design == design) & (d.period == period)]
    a, z = MS.PERIODS[period]
    idx = pd.date_range(a, pd.Timestamp(z) - pd.Timedelta(days=1), freq="D")
    v = pd.Series(d[f"eq_{account}"].to_numpy(float), index=pd.to_datetime(d.date.to_numpy())).reindex(idx)
    if v.isna().any():
        v = v.ffill().fillna(ACC0)
    return v


def acc_for(sym: str, new_acc: str) -> str:
    """The base keeps its demo 0.01 lot: its (a) account (the engine's direct run for the basket designs)."""
    return "a" if sym in MS.BASE_SYMBOLS else new_acc


def _period_for(design: str, period: str) -> str:
    return period          # 'sel' and 'conf' exist for every design (the Turtles were also run on the basket 'sel')


def block_bounds(period: str) -> List[pd.Timestamp]:
    a, z = MS.PERIODS[period]
    out, k = [], 0
    while True:
        t = pd.Timestamp(a) + pd.DateOffset(months=k)
        if t >= pd.Timestamp(z):
            break
        out.append(t)
        k += 1
    return out + [pd.Timestamp(z)]


def port_metrics(members: Sequence[Tuple[str, str]], period: str, new_acc: str,
                 base_eq: Optional[pd.Series] = None) -> dict:
    if not members:
        return dict(n=0)
    eqs = [daily(sy, k, period, acc_for(sy, new_acc)) for sy, k in members]
    E = pd.concat(eqs, axis=1)
    tot = E.sum(axis=1)
    n = len(members)
    start = ACC0 * n
    profit = float(tot.iloc[-1] - start)
    path = np.r_[start, tot.to_numpy()]
    peak = np.maximum.accumulate(path)
    ddu = float((peak - path).max())
    ddp = float(((peak - path) / peak).max() * 100.0)
    # worst month: 13th-to-13th blocks (§7's monthly blocks), equity at a block edge = the last daily mark before it
    bb = block_bounds(period)
    ser = pd.Series(path, index=[tot.index[0] - pd.Timedelta(days=1)] + list(tot.index))
    at = [start] + [float(ser[ser.index <= t - pd.Timedelta(days=1)].iloc[-1]) for t in bb[1:]]
    mo = np.diff(at)
    wi = int(np.argmin(mo))
    rets = E.diff().iloc[1:]
    first = E.iloc[0] - ACC0
    rets = pd.concat([first.to_frame().T, rets])
    if n > 1:
        c = rets.corr().to_numpy()
        avg_pair = float(np.nanmean(c[np.triu_indices(n, 1)]))
    else:
        avg_pair = np.nan
    out = dict(n=n, symbols=len({sy for sy, _ in members}), profit=round(profit, 2),
               profit_per_week=round(profit / WEEKS[period], 2), profit_per_week_per_bot=round(profit / WEEKS[period] / n, 2),
               max_dd_usd=round(ddu, 2), max_dd_pct=round(ddp, 2), score=round(profit / max(ddu, 1.0), 4),
               worst_month_usd=round(float(mo[wi]), 2), worst_month_start=str(bb[wi].date()),
               avg_pair_corr=round(avg_pair, 4) if n > 1 else np.nan)
    if base_eq is not None:
        pr = tot.diff().fillna(tot.iloc[0] - start)
        br = base_eq.diff().fillna(base_eq.iloc[0] - ACC0 * len(BASE_PAIRS))
        out["corr_with_base6"] = round(float(pr.corr(br)), 4)
    return out


def base_equity(period: str) -> pd.Series:
    return pd.concat([daily(sy, k, period, "a") for sy, k in BASE_PAIRS], axis=1).sum(axis=1)


def label(members) -> str:
    return " + ".join(f"{s}:{k}" for s, k in members)


def portfolios(sel: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    pairs = list(zip(sel.symbol, sel.design))
    Q = int(sel.qualified.sum())
    nmax = len(pairs)
    beq = {p: base_equity(p) for p in ("sel", "conf")}
    rows = []

    def add(view, N, members, period, acc, **kw):
        m = port_metrics(members, period, acc, beq[period])
        rows.append(dict(view=view, N=N, period=period, account=acc, qualified_part=N <= Q, **m,
                         members=label(members), **kw))

    for N in range(1, nmax + 1):
        mem = pairs[:N]
        add("P_N", N, mem, "conf", "b")
        add("P_N", N, mem, "conf", "a")
        add("P_N", N, mem, "sel", "b")
    # §8.7.1: one bot per symbol, by the rank of each symbol's best pair
    best = sel.drop_duplicates("symbol", keep="first")
    sym_pairs = list(zip(best.symbol, best.design))
    sym_q = list(best.qualified)
    for K in range(1, len(sym_pairs) + 1):
        for per, acc in (("conf", "b"), ("conf", "a"), ("sel", "b")):
            m = port_metrics(sym_pairs[:K], per, acc, beq[per])
            rows.append(dict(view="K_symbols", N=K, period=per, account=acc, qualified_part=all(sym_q[:K]), **m,
                             members=label(sym_pairs[:K])))
    # §8.7.2: silver + the first F forex symbols, V3-lite, no selection. Only F = 6 exists in this step.
    present = [x for x in SCOPE_SYMBOLS if x in set(sel.symbol)]
    named = [(x, "v3lite") for x in present]
    for per, acc in (("conf", "b"), ("conf", "a")):
        m = port_metrics(named, per, acc, beq[per])
        rows.append(dict(view="named_v3lite_F6", N=len(named), period=per, account=acc, qualified_part=False, **m,
                         members=label(named)))
    # §8.7.3: the base, and the base + P_N (new pairs under (b), and under (a) for information)
    for per in ("conf", "sel"):
        m = port_metrics(BASE_PAIRS, per, "a", beq[per])
        rows.append(dict(view="base", N=0, period=per, account="a", qualified_part=True, **m, members=label(BASE_PAIRS)))
    for N in range(1, nmax + 1):
        for acc in ("b", "a"):
            mem = BASE_PAIRS + pairs[:N]
            m = port_metrics(mem, "conf", acc, beq["conf"])
            rows.append(dict(view="base_plus_P_N", N=N, period="conf", account=acc, qualified_part=N <= Q, **m,
                             members=label(mem)))
    cur = pd.DataFrame(rows)

    # §8.6
    def pick(view, per, acc):
        c = cur[(cur.view == view) & (cur.period == per) & (cur.account == acc)].set_index("N")
        return c

    res = dict(Q=Q, n_candidates=nmax)
    for acc in ("b", "a"):
        cf = pick("P_N", "conf", acc)
        sl = pick("P_N", "sel", "b")
        if Q == 0:
            res[acc] = dict(success=False, N_star=0)
            continue
        pq = cf.loc[Q]
        ok = bool(pq.profit > 0 and pq.score >= 1.0)
        qual = cf.loc[1:Q]
        n_star = int(qual.score.idxmax())
        best_score = float(qual.score.max())
        near = [int(n) for n, v in qual.score.items() if v >= best_score * 0.9]
        n_sel = int(sl.loc[1:Q].score.idxmax())
        res[acc] = dict(success=ok, P_Q_profit=float(pq.profit), P_Q_score=float(pq.score),
                        N_star=n_star if ok else 0, N_best_in_1_Q=n_star, best_score=best_score, within_10pct=near,
                        N_sel=n_sel, N_sel_conf_score=float(cf.loc[n_sel].score))
    return cur, res


# ───────────────────────────── correlations ─────────────────────────────

def correlations(sel: pd.DataFrame, top: int) -> pd.DataFrame:
    """Daily P/L correlation, confirmation half: each of the top pairs and the six base bots, pairwise."""
    pairs = list(zip(sel.symbol, sel.design))[:top] + BASE_PAIRS
    cols = {}
    for sy, k in pairs:
        e = daily(sy, k, "conf", acc_for(sy, "b"))
        cols[f"{sy}:{k}"] = e.diff().fillna(e.iloc[0] - ACC0)
    return pd.DataFrame(cols).corr().round(4)


# ───────────────────────────── §9: swap ─────────────────────────────

def swap_table(sel: pd.DataFrame, s: pd.DataFrame, res: dict) -> pd.DataFrame:
    """Lot-nights (weighted 3 on the triple night) and the break-even swap: the cost in points per lot per night,
    charged on both sides, that cuts the profit to zero. Confirmation half, accounts (a) and (b)."""
    rows = []
    cache = {}

    def tr(sym):
        if sym not in cache:
            cache[sym] = pd.read_csv(RUNS / sym / "trades.csv.gz")
        return cache[sym]

    def one(sym, k, acc):
        t = tr(sym)
        t = t[(t.design == k) & (t.period == "conf")]
        spec = MS.SYMBOLS[sym]
        pt = 10.0 ** (-spec.digits)
        if acc == "a" or sym in MS.BASE_SYMBOLS:
            lots_nights = t.lot_nights_w_1u * t.units_a.fillna(0)
        else:
            lots_nights = t.lot_nights_w_1u * t.units_b.fillna(0) * t.lot_per_unit_b / 0.01
        usd_per_point = float((lots_nights * spec.contract_size * pt * t.fx_close).sum())   # $ per 1 point/lot/night
        long_ln = float(lots_nights[t.side > 0].sum())
        short_ln = float(lots_nights[t.side < 0].sum())
        return usd_per_point, long_ln, short_ln, pt

    for sy, k in list(zip(sel.symbol, sel.design)) + BASE_PAIRS:
        for acc in ("a", "b"):
            if sy in MS.BASE_SYMBOLS and acc == "b":
                continue
            u, ll, sl, pt = one(sy, k, acc)
            r = row(s, sy, k, "conf", acc_for(sy, acc))
            be = r.profit / u if (r.profit > 0 and u > 0) else np.nan
            rows.append(dict(symbol=sy, design=k, account=acc_for(sy, acc), role="base" if sy in MS.BASE_SYMBOLS else "new",
                             profit_conf=r.profit, long_lot_nights=round(ll, 3), short_lot_nights=round(sl, 3),
                             usd_per_point_per_lot_night=round(u, 4), point=pt,
                             breakeven_points_per_lot_night=round(be, 3) if be == be else np.nan,
                             summary_row=int(r.csv_row)))
    return pd.DataFrame(rows)


# ───────────────────────────── the USDJPYm bad quote (sensitivity, not a registered result) ─────────────────────────────

def usdjpy_badtick() -> pd.DataFrame:
    """One M1 bar, 2019-04-15 06:28 UTC, has bid open / low 55.920 between closes of 111.938 and 111.940 (half the
    price). The run step's Turtles stopped out on it. Re-run the USDJPYm Turtles in memory with that bar's open and
    low set to the neighbouring closes, and report the selection measures (§8.3) beside the registered ones."""
    sym = "USDJPYm"
    m1 = MS.store.load_m1(sym, MS.TURTLE_HISTORY, MS.DATA_END)
    m1 = {k: np.array(v) for k, v in m1.items()}
    i = int(np.searchsorted(m1["t"], 1555309680))
    assert m1["t"][i] == 1555309680 and m1["l"][i] < 60
    pc = m1["c"][i - 1]
    m1["o"][i] = pc
    m1["l"][i] = min(pc, m1["c"][i])
    spec = MS.SYMBOLS[sym]
    m = MS.B.SpecMarket(sym, m1, spec.contract_size, spec.digits)
    sig = MS.X.bot_signals(m)
    fxm = MS.FX(sym).at_s(m.t)
    L = float(MS.load_specs(sym)["L"])
    rows = []
    for key in ("ts2", "ts1"):
        plan = MS.X.filtered(MS.X.turtle(m, MS.TURTLES[key][1]).plan, m, sig.votes_at)
        for period in ("tsel", "conf"):
            a, z = MS.PERIODS[period]
            a_ms, z_ms = MS.to_ms(a), MS.to_ms(z)
            a_ix, z_ix = int(np.searchsorted(m.t, a_ms // 1000)), int(np.searchsorted(m.t, z_ms // 1000))
            p = MS.X.run_path(m, plan, a_ix, z_ix)
            bnd = MS.F._day_bounds(m, a_ix, z_ix)
            closed = p.why != 4
            for name, rule, lf in MS.ACCOUNTS:
                lotf = MS.lot_factor(lf, L)
                r = MS.turtle_account(m, p, bnd, spec.contract_size * 0.01 * lotf, fxm, rule == 0, z_ms)
                lots = np.nan_to_num(r["units"]) * p.nleg * 0.01 * lotf
                met = MS.measures(r, a, z, np.nan_to_num(r["pnl"]), closed, lots.astype(float), p.dir)
                rows.append(dict(design=key, period=period, account=name, **{k: met[k] for k in (
                    "profit", "max_dd_usd", "max_dd_pct", "profit_per_dd", "trades", "pos_halfyears", "n_halfyears",
                    "sharpe_weekly", "wiped")}))
    return pd.DataFrame(rows)


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.multiportfolio")
    ap.add_argument("cmd", choices=["all", "badtick"])
    a = ap.parse_args(argv)
    if a.cmd == "badtick":
        usdjpy_badtick().to_csv(OUT / "usdjpy_badtick.csv", index=False)
        return
    s = summary()
    sel = selection(s)
    sel.to_csv(OUT / "selection.csv", index=False)
    cur, res = portfolios(sel)
    cur.to_csv(OUT / "portfolio_curve.csv", index=False)
    correlations(sel, top=max(int(sel.qualified.sum()), 1) + 4).to_csv(OUT / "correlation.csv")
    swap_table(sel, s, res).to_csv(OUT / "swap.csv", index=False)
    import json
    (OUT / "portfolio_result.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    print(sel[["rank", "symbol", "design", "sharpe_weekly", "profit", "profit_per_dd", "blocks_pos", "trades",
               "b_max_dd_pct", "Q1", "Q2", "Q3", "Q4", "Q5", "qualified"]].head(12).to_string())


if __name__ == "__main__":
    main()
