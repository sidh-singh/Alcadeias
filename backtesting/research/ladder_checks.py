"""
Ladder study, build step: the checks of PREREG_LADDER.md section 6, run before any variant.

  identity   the new engine with every new field at its default equals the existing engine (np.array_equal)
  tfs        bars of M4, M6, M12, M20, H3 and W1 against bars built independently from the ticks and the M1 store
  ind        every closed-bar indicator against a plain-loop reference
  features   each new path switched on, rule-checked fill by fill on one quarter; traces of 3 baskets
  anchors    A1 / A2: Live on the 184-run anchor, row by row
  long       A3 / A4 / A5: the 8-year accounts
  fold       the fold-prepare check of section 3.2 (memory, shared against own prepare)
  speed      a small speed table

usage: python -m backtesting.research.ladder_checks WHAT [jobs]      (results: backtest_results/ladder/identity/)
"""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from . import ladder_tfs as LT
from . import ladder_ind as LI
from . import ladder_kernels as LK
from . import ladder_engine as LE
from ..config import BacktestConfig, REPO_ROOT, TF_SECONDS
from ..data import store
from ..engine import fast
from ..engine import kernels as K
from ..analysis.robustness import live_timing

OUT = REPO_ROOT / "backtest_results" / "ladder" / "identity"
ROUND4 = REPO_ROOT / "backtest_results" / "improve" / "round4"
SYMBOLS = ("XAUUSDm", "BTCUSDm")
FEATURE_Q = ("2023-02-13", "2023-05-13")       # an F3 quarter: no variant reads F4 before the walk-forward test
V = dict(vol_tf="H1", vol_len=24)


def _log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def _designs(symbol: str) -> Dict[str, dict]:
    """The five identity designs (PREREG section 6, check 1)."""
    r4 = json.loads((ROUND4 / "top3_v4_XAUUSDm_designs.json").read_text())
    top1 = next(v for k, v in r4.items() if k.startswith("Top 1"))
    return {"Live": {}, "V3-lite": r4["V3-lite"], "gold Top 1": top1,
            "price_step flat": dict(ladder_trigger="price_step", ladder_multipliers=[1.0] * 6, ladder_gap_vol=1.0, **V),
            "rsi_cross": dict(ladder_trigger="rsi_cross", ladder_rsi_exit=2.0)}


# ───────────────────────────── 1. bit-identity ─────────────────────────────

def old_raw(cfg: BacktestConfig, prep: fast.Prepared) -> dict:
    """The existing engine's raw outputs: exactly the kernel call of ``fast.run(..., light=True)``."""
    flat = prep.flat(cfg)
    w, need_rsi, need_slope, ladder_tf, mult, hour_ok, ci, cf = fast._kernel_inputs(cfg, prep)
    ci[K.CI_REC_MS] = 0
    reg_t, reg_v = np.zeros(0, np.int64), np.zeros(0, np.int64)
    max_fills = 200_000
    while True:
        fills = np.zeros((max_fills, K.F_N))
        baskets = np.zeros((max(max_fills // 2, 16), K.B_N))
        eq = np.zeros((2, K.E_N))
        tr = np.zeros((0, K.T_N))
        counters = np.zeros(K.K_N, np.int64)
        scal = np.zeros(K.S_N)
        K.run_kernel(prep.t_ms, prep.bid, prep.ask, flat["off"], flat["nb"], flat["nwarm"], flat["START_ROW"],
                     flat["C"], flat["AG"], flat["AL"], flat["RSI"], flat["EF"], flat["ES"], flat["SG"], flat["HIST"],
                     flat["VOL"], flat["R_PH"], flat["R_PL"], flat["R_CH"], flat["R_CL"], flat["M_PH"], flat["M_PL"],
                     flat["M_CH"], flat["M_CL"], need_rsi, need_slope, w["or"], w["om"], w["fr"], w["fm"], w["br"],
                     w["bm"], w["ar"], w["am"], ladder_tf, mult, hour_ok, reg_t, reg_v, ci, cf,
                     fills, baskets, eq, tr, counters, scal)
        if counters[K.K_FILL_OVERFLOW] == 0 and counters[K.K_BASKET_OVERFLOW] == 0:
            break
        max_fills *= 4
    return {"fills": fills[:int(scal[K.S_N_FILLS])], "baskets": baskets[:int(scal[K.S_N_BASKETS])],
            "counters": counters, "scalars": scal}


def _identity_one(task):
    sym, (a, z) = task
    prep = LE.prepare(sym, a, z, sorted({tf for d in _designs(sym).values()
                                         for tf in BacktestConfig.live(sym).replace(**d).timeframes()}, key=TF_SECONDS.get),
                      mode="ticks")
    rows = []
    for name, d in _designs(sym).items():
        for seed in (1, 2):
            ov = {**d, **live_timing(seed)}
            c_old = BacktestConfig.live(sym, start=a, end=z).replace(**ov)
            c_new = LE.live_config(sym, start=a, end=z).replace(**ov)
            o = old_raw(c_old, prep)
            res, n = LE.run(c_new, prep, light=True, raw=True)
            ref = fast.run(c_old, prep, light=True)          # the public entry point gives the same as old_raw
            nb = n["baskets"]
            ok = {
                "eq_fills": np.array_equal(o["fills"], n["fills"]),
                "eq_baskets": np.array_equal(o["baskets"], nb[:, :K.B_N]),
                "eq_counters": np.array_equal(o["counters"], n["counters"][:K.K_N]),
                "eq_scalars": np.array_equal(o["scalars"], n["scalars"]),
                "new_fields_default": bool(np.all(n["counters"][K.K_N:] == 0) and np.all(nb[:, LK.B2_PART_PNL] == 0)
                                           and np.all(nb[:, LK.B2_N_HEDGE] == 0) and np.all(nb[:, LK.B2_IS_REV] == 0)
                                           and np.array_equal(nb[:, LK.B2_N_OPENED], nb[:, K.B_NPOS])
                                           and np.array_equal(nb[:, LK.B2_MAX_LAD], nb[:, K.B_NPOS])),
                "fast_run_same": bool(ref.scalars["final_equity"] == res.scalars["final_equity"]
                                      and len(ref.baskets) == len(res.baskets) and ref.fills.equals(res.fills)),
            }
            rows.append({"symbol": sym, "window": f"{a} → {z}", "design": name, "seed": seed,
                         "net": round(res.scalars["final_equity"] - 2000.0, 2), "baskets": len(res.baskets),
                         "fills": len(n["fills"]), **ok, "all": all(ok.values())})
            _log(sym, a, name, seed, rows[-1]["net"], rows[-1]["baskets"], "OK" if rows[-1]["all"] else f"FAIL {ok}")
    return rows


def identity(jobs: int = 4) -> pd.DataFrame:
    tasks = [(s, w) for s in SYMBOLS for w in (("2026-08-13", "2026-11-13"), ("2021-02-13", "2021-05-13"))]
    with mp.get_context("fork").Pool(min(jobs, len(tasks))) as pool:
        rows = [r for part in pool.map(_identity_one, tasks) for r in part]
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "identity.csv", index=False)
    _log("identity:", int(d["all"].sum()), "of", len(d), "runs bit-identical")
    return d


# ───────────────────────────── 2. timeframes ─────────────────────────────

def _ref_bars_ticks(t_ms, bid, tf):
    """Bars built directly from rows with pandas (bar open on the MT5 grid, last bid)."""
    off, n = LT.tf_offset(tf), TF_SECONDS[tf]
    s = pd.Series(bid, index=(t_ms // 1000 - off) // n)
    g = s.groupby(level=0).last()
    return g.index.to_numpy() * n + off, g.to_numpy()


def _ref_bars_m1(m1, tf):
    off, n = LT.tf_offset(tf), TF_SECONDS[tf]
    df = pd.DataFrame({"o": m1["o"], "h": m1["h"], "l": m1["l"], "c": m1["c"]}, index=(m1["t"] - off) // n)
    g = df.groupby(level=0).agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    return g.index.to_numpy() * n + off, g


def timeframes() -> pd.DataFrame:
    rows = []
    a, z = "2023-02-13", "2023-03-13"
    for sym in SYMBOLS:
        m1 = LI.m1_history(sym)
        for mode in ("ticks", "sec"):
            prep = LE.prepare(sym, a, z, list(LT.NEW_TFS), mode=mode)
            for tf in LT.NEW_TFS:
                nw = prep.nwarm[tf]
                bt, c = prep.bar_t[tf], prep.closes[tf]
                rt, rc = _ref_bars_ticks(prep.t_ms, prep.bid, tf)
                in_ok = np.array_equal(bt[nw:], rt) and np.array_equal(c[nw:], rc)
                before = m1["t"] * 1000 < prep.start_ms
                mt, mg = _ref_bars_m1({k: v[before] for k, v in m1.items()}, tf)
                keep = mt < bt[nw]
                warm_ok = np.array_equal(bt[:nw], mt[keep][-nw:]) and np.array_equal(c[:nw], mg["c"].to_numpy()[keep][-nw:])
                # the window's closes also equal the M1 store's (the series of ladder_ind are built from it)
                full_t, full_g = _ref_bars_m1(m1, tf)
                pos = np.searchsorted(full_t, bt[nw:])
                store_ok = bool(np.all(full_t[pos] == bt[nw:]) and np.array_equal(full_g["c"].to_numpy()[pos][:-1], c[nw:][:-1]))
                if tf == "W1":
                    d = pd.to_datetime(bt, unit="s")
                    grid_ok = bool(np.all(d.dayofweek == 6) and np.all((bt % 86400) == 0))
                else:
                    grid_ok = bool(np.all((bt % 86400) % TF_SECONDS[tf] == 0))
                rows.append({"symbol": sym, "mode": mode, "tf": tf, "warm_bars": nw, "window_bars": len(bt) - nw,
                             "window_vs_rows": in_ok, "warmup_vs_m1": warm_ok, "window_vs_m1_store": store_ok,
                             "mt5_grid": grid_ok})
        # W1 spot check: 3 weeks, OHLC from ladder_ind against a direct M1 cut
        b = LI.bars(sym, "W1")
        for wk in ("2019-03-10", "2021-05-16", "2024-08-04"):
            t0 = int(pd.Timestamp(wk).timestamp())
            i = int(np.flatnonzero(b["t"] == t0)[0])
            sel = (m1["t"] >= t0) & (m1["t"] < t0 + 7 * 86400)
            ok = (pd.Timestamp(wk).dayofweek == 6 and b["o"][i] == m1["o"][sel][0] and b["h"][i] == m1["h"][sel].max()
                  and b["l"][i] == m1["l"][sel].min() and b["c"][i] == m1["c"][sel][-1])
            rows.append({"symbol": sym, "mode": "m1", "tf": f"W1 week of {wk}", "warm_bars": 0, "window_bars": 1,
                         "window_vs_rows": ok, "warmup_vs_m1": ok, "window_vs_m1_store": ok, "mt5_grid": ok})
    d = pd.DataFrame(rows)
    d["all"] = d[["window_vs_rows", "warmup_vs_m1", "window_vs_m1_store", "mt5_grid"]].all(axis=1)
    d.to_csv(OUT / "timeframes.csv", index=False)
    _log("timeframes:", int(d["all"].sum()), "of", len(d), "checks pass")
    return d


# ───────────────────────────── 3. indicators: plain-loop references ─────────────────────────────

def r_sma(x, n):
    out = [math.nan] * len(x)
    for i in range(n - 1, len(x)):
        out[i] = sum(x[i - n + 1:i + 1]) / n
    return np.array(out)


def r_ema(x, n):
    out = [math.nan] * len(x)
    if len(x) >= n:
        v = sum(x[:n]) / n
        out[n - 1] = v
        a = 2.0 / (n + 1)
        for i in range(n, len(x)):
            v = a * x[i] + (1 - a) * v
            out[i] = v
    return np.array(out)


def r_wilder(x, n):
    out = [math.nan] * len(x)
    s = next((i for i, v in enumerate(x) if v == v), None)
    if s is None or s + n > len(x):
        return np.array(out)
    v = sum(x[s:s + n]) / n
    out[s + n - 1] = v
    for i in range(s + n, len(x)):
        v = (v * (n - 1) + x[i]) / n
        out[i] = v
    return np.array(out)


def r_tr(h, l, c):
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]


def r_rsi(c, n):
    g = [math.nan] + [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
    lo = [math.nan] + [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
    ag, al = r_wilder(g, n), r_wilder(lo, n)
    out = []
    for a_, b_ in zip(ag, al):
        if a_ != a_ or b_ != b_:
            out.append(math.nan)
        elif b_ > 0:
            out.append(100 - 100 / (1 + a_ / b_))
        else:
            out.append(100.0 if a_ > 0 else 50.0)
    return np.array(out)


def r_stoch(h, l, c, n, s):
    raw = [math.nan] * len(c)
    for i in range(n - 1, len(c)):
        hh, ll = max(h[i - n + 1:i + 1]), min(l[i - n + 1:i + 1])
        raw[i] = 100 * (c[i] - ll) / (hh - ll) if hh > ll else 50.0
    return r_sma(raw, s)


def r_willr(h, l, c, n):
    out = [math.nan] * len(c)
    for i in range(n - 1, len(c)):
        hh, ll = max(h[i - n + 1:i + 1]), min(l[i - n + 1:i + 1])
        out[i] = -100 * (hh - c[i]) / (hh - ll) if hh > ll else -50.0
    return np.array(out)


def r_cci(h, l, c, n):
    tp = [(h[i] + l[i] + c[i]) / 3 for i in range(len(c))]
    out = [math.nan] * len(c)
    for i in range(n - 1, len(c)):
        w = tp[i - n + 1:i + 1]
        m = sum(w) / n
        md = sum(abs(v - m) for v in w) / n
        out[i] = (tp[i] - m) / (0.015 * md) if md > 0 else 0.0
    return np.array(out)


def r_bb(c, n, k):
    out = [math.nan] * len(c)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1:i + 1]
        m = sum(w) / n
        sd = math.sqrt(sum((v - m) ** 2 for v in w) / n)
        out[i] = (c[i] - (m - k * sd)) / (2 * k * sd) if sd > 0 else 0.5
    return np.array(out)


def r_adx(h, l, c, n):
    pdm, mdm, tr = [math.nan], [math.nan], [math.nan]
    for i in range(1, len(c)):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    at, sp, sm = r_wilder(tr, n), r_wilder(pdm, n), r_wilder(mdm, n)
    pdi = [100 * p / t if t > 0 else (0.0 if t == t else math.nan) for p, t in zip(sp, at)]
    mdi = [100 * m / t if t > 0 else (0.0 if t == t else math.nan) for m, t in zip(sm, at)]
    dx = [(100 * abs(p - m) / (p + m) if (p + m) > 0 else 0.0) if (p == p and m == m) else math.nan for p, m in zip(pdi, mdi)]
    return r_wilder(dx, n), np.array(pdi), np.array(mdi)


def r_supertrend(h, l, c, n, mult):
    """Pine (KivancOzbilgic) Supertrend, written out again from its definition."""
    at = r_wilder(r_tr(h, l, c), n)
    out, up1, dn1, trend, started = [0] * len(c), None, None, 1, False
    for i in range(len(c)):
        if at[i] != at[i]:
            continue
        src = (h[i] + l[i]) / 2
        up, dn = src - mult * at[i], src + mult * at[i]
        if started:
            if c[i - 1] > up1:
                up = max(up, up1)
            if c[i - 1] < dn1:
                dn = min(dn, dn1)
            if trend == -1 and c[i] > dn1:
                trend = 1
            elif trend == 1 and c[i] < up1:
                trend = -1
        started = True
        up1, dn1 = up, dn
        out[i] = trend
    return np.array(out)


def r_donchian(h, l, c, n):
    out, st = [], 0
    for i in range(len(c)):
        if i >= n:
            if c[i] > max(h[i - n:i]):
                st = 1
            elif c[i] < min(l[i - n:i]):
                st = -1
        out.append(st)
    return np.array(out)


def r_vr(c, q, n):
    r = [math.nan] + [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    out = [math.nan] * len(c)
    for i in range(n, len(c)):
        w1 = r[i - n + 1:i + 1]
        m1 = sum(w1) / n
        v1 = sum((x - m1) ** 2 for x in w1) / (n - 1)
        rq = [sum(r[j - q + 1:j + 1]) for j in range(i - n + q, i + 1)]
        mq = sum(rq) / len(rq)
        vq = sum((x - mq) ** 2 for x in rq) / (len(rq) - 1)
        out[i] = vq / (q * v1) if v1 > 0 else math.nan
    return np.array(out)


def r_macd_signal(c):
    ef, es = r_ema(c, 12), r_ema(c, 26)
    m = [a - b for a, b in zip(ef, es)]
    first = 25
    sg = [math.nan] * len(c)
    if len(c) > first + 8:
        v = sum(m[first:first + 9]) / 9
        sg[first + 8] = v
        for i in range(first + 9, len(c)):
            v = 0.2 * m[i] + 0.8 * v
            sg[i] = v
    return np.array(sg)


def _close(a, b, tol=1e-8):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return bool(a.shape == b.shape and np.allclose(a, b, rtol=tol, atol=tol, equal_nan=True))


def indicators() -> pd.DataFrame:
    rows = []
    for sym in SYMBOLS:
        for tf, nbar in (("H1", 2500), ("H4", 1500), ("D1", 900), ("M20", 2500)):
            b = LI.bars(sym, tf)
            sl = slice(len(b["c"]) - nbar, None)
            h, l, c = b["h"][sl], b["l"][sl], b["c"][sl]
            hL, lL, cL = list(h), list(l), list(c)
            ax, pdi, mdi = LI.adx(h, l, c, 14)
            rx, rp, rm = r_adx(hL, lL, cL, 14)
            at = LI.X.wilder_atr(h, l, c, 14)
            checks = {
                "sma20": _close(LI.sma(c, 20), r_sma(cL, 20)),
                "ema200": _close(LI.ema(c, 200), r_ema(cL, 200)),
                "stoch_14_3": _close(LI.stoch_k(h, l, c, 14, 3), r_stoch(hL, lL, cL, 14, 3)),
                "williams_r14": _close(LI.williams_r(h, l, c, 14), r_willr(hL, lL, cL, 14)),
                "cci20": _close(LI.cci(h, l, c, 20), r_cci(hL, lL, cL, 20), 1e-6),
                "bb_pctb_20_2": _close(LI.bb_pctb(c, 20, 2.0), r_bb(cL, 20, 2.0), 1e-6),
                "atr14": _close(at, r_wilder(r_tr(hL, lL, cL), 14)),
                "emadist_20_14": _close(LI.ema_dist_atr(h, l, c, 20, 14),
                                        (c - r_ema(cL, 20)) / r_wilder(r_tr(hL, lL, cL), 14)),
                "rsi2": _close(LI.rsi(c, 2), r_rsi(cL, 2)),
                "rsi14": _close(LI.rsi(c, 14), r_rsi(cL, 14)),
                "adx14": _close(ax, rx) and _close(pdi, rp) and _close(mdi, rm),
                "supertrend_10_3": bool(np.array_equal(LI.supertrend(h, l, c, 10, 3.0), r_supertrend(hL, lL, cL, 10, 3.0))),
                "donchian20": bool(np.array_equal(LI.donchian_side(h, l, c, 20), r_donchian(hL, lL, cL, 20))),
                "vr_4_100": _close(LI.variance_ratio(c, 4, 100), r_vr(cL, 4, 100), 1e-6),
                "macd_signal": _close(LI.macd_signal(c), r_macd_signal(cL)),
            }
            # ATR percentile over 100 calendar days (quantile with linear interpolation, the current bar included)
            tc = b["tc_ms"][sl]
            q = [np.quantile([x for x, t in zip(at, tc) if t > tc[i] - 100 * 86400000 and t <= tc[i] and x == x], 0.9)
                 if at[i] == at[i] else math.nan for i in range(len(at))]
            full = LI.gate_values(sym, {"kind": "atr_pct_block", "tf": tf, "n": 14, "days": 100, "q": 0.9})[sl]
            ref_m = np.where(np.isfinite(at) & ~(at > np.array(q)), 3, 0)
            # the full-history series sees older bars in its window; compare where 100 days of this slice exist
            ok_i = tc >= tc[0] + 100 * 86400000
            checks["atr_pct_block"] = bool(np.array_equal(full[ok_i], ref_m[ok_i]))
            for name, ok in checks.items():
                rows.append({"symbol": sym, "tf": tf, "bars": nbar, "indicator": name, "match": ok})
        # series timing: the value in force at T is the last bar that CLOSED by T
        t, v = LI.gate_series(sym, {"kind": "supertrend", "tf": "H4", "n": 10, "mult": 3})
        b = LI.bars(sym, "H4")
        vals = LI.gate_values(sym, {"kind": "supertrend", "tf": "H4", "n": 10, "mult": 3})
        rng = np.random.default_rng(1)
        T = rng.integers(int(b["tc_ms"][300]), int(b["tc_ms"][-1]), 2000)
        i_ser = np.searchsorted(t, T, side="right") - 1
        i_bar = np.searchsorted(b["tc_ms"], T, side="right") - 1
        ok = bool(np.array_equal(v[i_ser], vals[i_bar]) and np.all(b["tc_ms"][i_bar] <= T)
                  and np.all(b["t"][i_bar] * 1000 + TF_SECONDS["H4"] * 1000 <= T))
        rows.append({"symbol": sym, "tf": "H4", "bars": 2000, "indicator": "series in force = last closed bar", "match": ok})
        ref, thr = LI.abnormal_series(sym, 2.0, 20)
        d1 = LI.bars(sym, "D1")
        rr = [abs(d1["c"][i] / d1["c"][i - 1] - 1) for i in range(1, len(d1["c"]))]
        thr_ref = np.array([2 * sum(rr[i - 20:i]) / 20 for i in range(20, len(rr) + 1)])
        rows.append({"symbol": sym, "tf": "D1", "bars": len(thr_ref), "indicator": "abnormal-day threshold",
                     "match": _close(thr[1], thr_ref) and np.array_equal(ref[1], d1["c"])})
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "indicators.csv", index=False)
    _log("indicators:", int(d["match"].sum()), "of", len(d), "match")
    return d


# ───────────────────────────── 4. each new path, switched on ─────────────────────────────

class Ref:
    """Independent state of one timeframe: bars by pandas from the M1 store, RSI / MACD / volatility by plain loops."""

    def __init__(self, sym: str, tf: str, start_ms: int, end_ms: int, back: int = 3000, vol_n: int = 24):
        t, g = _ref_bars_m1(LI.m1_history(sym), tf)
        i0 = max(int(np.searchsorted(t, start_ms // 1000)) - back, 0)
        i1 = int(np.searchsorted(t, end_ms // 1000 + TF_SECONDS[tf])) + 1
        self.tf, self.n = tf, TF_SECONDS[tf]
        self.t = t[i0:i1]
        self.c = g["c"].to_numpy()[i0:i1]
        self.h = g["h"].to_numpy()[i0:i1]
        self.l = g["l"].to_numpy()[i0:i1]
        c = list(self.c)
        gain = [math.nan] + [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
        loss = [math.nan] + [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
        self.ag, self.al = r_wilder(gain, 14), r_wilder(loss, 14)
        self.ef, self.es = r_ema(c, 12), r_ema(c, 26)
        m = list(self.ef - self.es)
        sg = [math.nan] * len(c)
        v = sum(m[25:34]) / 9
        sg[33] = v
        for i in range(34, len(c)):
            v = 0.2 * m[i] + 0.8 * v
            sg[i] = v
        self.sg = np.array(sg)
        vol = [0.0] * len(c)
        v = abs(c[1] - c[0])
        for i in range(2, len(c)):
            v += (abs(c[i] - c[i - 1]) - v) / vol_n
            vol[i] = v
        self.vol = np.array(vol)

    def k(self, tick_ms):
        """Index of the forming bar: the bar holding the latest tick (the engine's K)."""
        return np.searchsorted(self.t, (np.asarray(tick_ms, np.int64) // 1000 - LT.tf_offset(self.tf)) // self.n * self.n
                               + LT.tf_offset(self.tf), side="right") - 1

    def rsi(self, tick_ms, b):
        k = self.k(tick_ms) - 1
        d = np.asarray(b, float) - self.c[k]
        ag = (self.ag[k] * 13 + np.maximum(d, 0)) / 14
        al = (self.al[k] * 13 + np.maximum(-d, 0)) / 14
        return np.where(al > 0, 100 - 100 / (1 + ag / np.where(al > 0, al, 1)), 100.0)

    def hist(self, tick_ms, b):
        k = self.k(tick_ms) - 1
        b = np.asarray(b, float)
        ef = 2 / 13 * b + 11 / 13 * self.ef[k]
        es = 2 / 27 * b + 25 / 27 * self.es[k]
        sg = 0.2 * (ef - es) + 0.8 * self.sg[k]
        return (ef - es) - sg

    def trend(self, tick_ms):
        return np.sign(self.sg[self.k(tick_ms) - 1])

    def vol_closed(self, tick_ms):
        return self.vol[self.k(tick_ms) - 1]


def _closed_by(tc_ms, T):
    """Index of the last bar whose close time is at or before T (the series' reading)."""
    return np.searchsorted(tc_ms, np.asarray(T, np.int64), side="right") - 1


FEATURES: Dict[str, dict] = {
    "size flat": dict(ladder_multipliers=[1.0] * 64),
    "size +1": dict(ladder_multipliers=[float(i) for i in range(1, 65)]),
    "size doubling": dict(ladder_multipliers=[2.0 ** min(i, 20) for i in range(64)]),
    "tiers T12 M2-M20": dict(ladder_tfs=["M2", "M4", "M6", "M10", "M20"]),
    "tiers T13 M10-H6": dict(ladder_tfs=["M10", "M20", "H2", "H3", "H6"]),
    "tiers T6 +D1+W1": dict(ladder_tfs=["M1", "M5", "M15", "H1", "H4", "D1", "W1"]),
    "per-tier stricter": dict(tier_os=[35, 32, 29, 26, 23], tier_ob=[65, 68, 71, 74, 77]),
    "trigger macd_hist": dict(ladder_trigger_x="macd_hist"),
    "trigger macd_cross": dict(ladder_trigger_x="macd_cross"),
    "trigger rsi_macd": dict(ladder_trigger_x="rsi_macd"),
    "trigger stoch": dict(ladder_trigger_x="series", trigger_spec={"ind": "stoch", "n": 14, "smooth": 3, "lo": 20, "hi": 80}),
    "trigger emadist": dict(ladder_trigger_x="series", trigger_spec={"ind": "emadist", "n": 20, "atr": 14, "lo": -2, "hi": 2}),
    "gap geometric 1.5": dict(ladder_gap_vol=1.0, gap_growth=1.5, **V),
    "gap D1 0.15": dict(gap_vol_tf="D1", gap_vol_len=14, gap_vol_mult=0.15),
    "stop 20% balance": dict(stop_pct_balance=20.0),
    "time 24h deep": dict(max_hold_s=86400.0, max_hold_min_adds=3),
    "target b/e after 3": dict(be_after_adds=3),
    "target shrink": dict(target_shrink=True),
    "final close H6 full": dict(final_close_tf="H6"),
    "add gate H1 trend": dict(add_trend_tf="H1"),
    "add gate EMA200 D1": dict(add_gate=[{"kind": "ema_side", "tf": "D1", "n": 200}]),
    "add gate ADX H1>30": dict(add_gate=[{"kind": "adx_above_block", "tf": "H1", "n": 14, "thr": 30}]),
    "add gate abnormal day": dict(abnormal_day={"mult": 2.0, "days": 20}),
    "add gate 20:30-22:30": dict(add_block_utc=[1230, 1350]),
    "Friday flat": dict(flat_week=[4 * 1440 + 20 * 60, 60]),
    "entry gate ATR pct": dict(entry_gate=[{"kind": "atr_pct_block", "tf": "H4", "n": 14, "days": 100, "q": 0.9}]),
    "confirm Supertrend H4": dict(entry_gate=[{"kind": "supertrend", "tf": "H4", "n": 10, "mult": 3}]),
    "side D1 RSI": dict(side_rsi_tf="D1"),
    "stop-and-reverse x1": dict(reverse=True),
    "stop-and-reverse x2": dict(reverse=True, reverse_mult=2.0),
    "hedge-on-depth": dict(hedge_mode="depth"),
    "counter-ladder": dict(hedge_mode="counter", ladder_gap_vol=1.0, **V),
    "partial LIFO": dict(partial="lifo"),
    "partial overlap": dict(partial="overlap"),
    "sizing pre-funded": dict(sizing="prefund"),
    "sizing vol-target": dict(sizing="voltarget", vt_k=1.0),          # placeholder: k is set per symbol below
    # the two rules give unit 1 at $2,000; these two runs exercise the formula over the whole unit range
    "sizing vol-target k x3": dict(sizing="voltarget", vt_k=1.0),
    "sizing pre-funded $20,000": dict(sizing="prefund", initial_balance=20000.0),
}


def _fill_view(raw: dict, prep) -> pd.DataFrame:
    F = raw["fills"]
    d = pd.DataFrame({"i": np.arange(len(F)), "T": F[:, K.F_T].astype(np.int64), "tick": F[:, K.F_FILL_T].astype(np.int64),
                      "act": F[:, K.F_ACTION].astype(int), "side": F[:, K.F_SIDE].astype(int), "lots": F[:, K.F_LOTS],
                      "price": F[:, K.F_PRICE], "profit": F[:, K.F_PROFIT], "bal": F[:, K.F_BALANCE],
                      "basket": F[:, K.F_BASKET].astype(int), "reason": F[:, K.F_REASON].astype(int),
                      "units": F[:, K.F_UNITS].astype(int), "npos": F[:, K.F_NPOS].astype(int), "bid": F[:, K.F_BID],
                      "ask": F[:, K.F_ASK], "tier": [prep.tfs[int(x)] if x >= 0 else "" for x in F[:, K.F_TIER]],
                      "bprofit": F[:, K.F_BASKET_PROFIT], "pos_t": F[:, K.F_POS_OPEN_T].astype(np.int64)})
    return d


def _basket_view(raw: dict) -> pd.DataFrame:
    B = raw["baskets"]
    return pd.DataFrame({"id": B[:, K.B_ID].astype(int), "side": B[:, K.B_SIDE].astype(int), "open": B[:, K.B_OPEN_T].astype(np.int64),
                         "close": B[:, K.B_CLOSE_T].astype(np.int64), "npos": B[:, K.B_NPOS].astype(int),
                         "lots": B[:, K.B_LOTS], "pnl": B[:, K.B_PNL], "reason": B[:, K.B_REASON].astype(int),
                         "units": B[:, K.B_UNITS].astype(int), "mae": B[:, K.B_MAE], "seen": B[:, K.B_PROFIT_SEEN],
                         "opened": B[:, LK.B2_N_OPENED].astype(int), "maxlad": B[:, LK.B2_MAX_LAD].astype(int),
                         "part": B[:, LK.B2_PART_PNL], "nhedge": B[:, LK.B2_N_HEDGE].astype(int), "rev": B[:, LK.B2_IS_REV] > 0})


def _mow(tick_ms):
    s = np.asarray(tick_ms, np.int64) // 1000
    return ((s // 86400 + 3) % 7) * 1440 + (s % 86400) // 60


class Checker:
    def __init__(self, name):
        self.name, self.n, self.bad, self.notes, self.ann = name, 0, 0, [], {}
        self.acct_n, self.acct_bad = 0, 0

    def check_acct(self, ok, note=""):
        self.acct_n += 1
        if not ok:
            self.acct_bad += 1
            if len(self.notes) < 5:
                self.notes.append("accounting: " + note)

    def check(self, ok, i=None, note=""):
        self.n += 1
        if not ok:
            self.bad += 1
            if len(self.notes) < 5:
                self.notes.append(f"fill {i}: {note}")
        if i is not None and note:
            self.ann[int(i)] = note + ("" if ok else "  <-- FAIL")


def _accounting(ck: Checker, f: pd.DataFrame, bk: pd.DataFrame, raw: dict, init: float):
    """Every basket's P/L is the sum of its fills' P/L; the balance is the start plus every closed basket's P/L."""
    closes = f[f["act"] == K.ACT_CLOSE].groupby("basket")["profit"].sum()
    for _, r in bk.iterrows():
        ck.check_acct(abs(closes.get(r["id"], 0.0) - r["pnl"]) < 1e-6, f"basket {r['id']} pnl")
    ck.check_acct(abs(raw["scalars"][K.S_FINAL_BALANCE] - (init + bk["pnl"].sum())) < 1e-6 or raw["scalars"][K.S_BLOWN] > 0,
             "final balance")


def _verify(name: str, cfg, prep, raw: dict, refs) -> Checker:
    ck = Checker(name)
    f, bk = _fill_view(raw, prep), _basket_view(raw)
    sym, contract = cfg.symbol, cfg.spec.contract_size
    upp = contract * cfg.mtqty
    opens = f[f["act"] == K.ACT_OPEN]
    adds = f[f["act"] == K.ACT_ADD]
    side_of = dict(zip(bk["id"], bk["side"]))
    prev = {}                                    # the previous fill (open / add) of each add's basket
    last = {}
    for r in f[f["act"].isin([K.ACT_OPEN, K.ACT_ADD, LK.ACT_HEDGE])].itertuples():
        prev[r.i] = last.get(r.basket)
        last[r.basket] = r
    open_of = {r.basket: r for r in opens.itertuples()}
    first_close = f[f["act"] == K.ACT_CLOSE].groupby("basket")["i"].min()
    last_close = f[f["act"] == K.ACT_CLOSE].groupby("basket")["i"].max()
    mult = list(cfg.ladder_multipliers) + [cfg.ladder_multipliers[-1]] * 64

    def lvl(cnt, side):
        if cfg.tier_os is not None:
            return (cfg.tier_os + [cfg.tier_os[-1]] * 64)[cnt - 1] if side > 0 else (cfg.tier_ob + [cfg.tier_ob[-1]] * 64)[cnt - 1]
        return cfg.rsi_oversold if side > 0 else cfg.rsi_overbought

    def ref(tf, vol_n=24):
        key = (tf, vol_n)
        if key not in refs:
            refs[key] = Ref(sym, tf, prep.start_ms, prep.end_ms, vol_n=vol_n)
        return refs[key]

    n_t = cfg.n_ladder_adds
    if name.startswith("size"):
        for r in adds.itertuples():
            cnt = r.npos - 1
            exp = round(mult[cnt] * r.units * cfg.mtqty + 1e-12, 2)
            ck.check(abs(r.lots - exp) < 1e-9, r.i, f"add {cnt}: lots {r.lots:.2f} = round2({mult[cnt]:g} x {r.units} x 0.01)")
    if name.startswith("tiers") or name == "per-tier stricter":
        for r in adds.itertuples():
            cnt = r.npos - 1
            tf = cfg.ladder_tfs[cnt - 1]
            v = float(ref(tf).rsi(r.tick, r.bid))
            lv = lvl(cnt, r.side)
            ok = (v <= lv + 1e-6) if r.side > 0 else (v >= lv - 1e-6)
            ck.check(r.tier == tf and ok, r.i, f"add {cnt} on {tf}: forming RSI {v:.3f} {'<=' if r.side > 0 else '>='} {lv:g}")
    if name == "trigger macd_hist":
        for r in adds.itertuples():
            tf = cfg.ladder_tfs[r.npos - 2]
            h = float(ref(tf).hist(r.tick, r.bid))
            ck.check(h <= 1e-9 if r.side > 0 else h >= -1e-9, r.i, f"{tf} forming hist {h:+.4f} on the wrong side")
    if name in ("trigger macd_cross", "trigger rsi_macd"):
        for r in adds.itertuples():
            tf = cfg.ladder_tfs[r.npos - 2]
            p = prev[r.i]
            sel = slice(int(np.searchsorted(prep.t_ms, p.tick, side="right")), int(np.searchsorted(prep.t_ms, r.tick, side="right")))
            R = ref(tf)
            if name == "trigger macd_cross":
                hs = R.hist(prep.t_ms[sel], prep.bid[sel])
                h = float(R.hist(r.tick, r.bid))
                armed = (hs.min() <= 1e-9) if r.side > 0 else (hs.max() >= -1e-9)
                ok = armed and ((h > -1e-9) if r.side > 0 else (h < 1e-9))
                ck.check(ok, r.i, f"{tf} hist now {h:+.4f}, {'min' if r.side > 0 else 'max'} since last fill "
                                  f"{(hs.min() if r.side > 0 else hs.max()):+.4f}")
            else:
                rs = R.rsi(prep.t_ms[sel], prep.bid[sel])
                lv = lvl(r.npos - 1, r.side)
                ext = rs.min() if r.side > 0 else rs.max()
                ck.check((ext <= lv + 1e-6) if r.side > 0 else (ext >= lv - 1e-6), r.i,
                         f"{tf} RSI reached {ext:.2f} since the last fill (level {lv:g}); MACD vote: existing slope_sign")
    if name.startswith("trigger stoch") or name.startswith("trigger emadist"):
        spec = cfg.trigger_spec
        for r in adds.itertuples():
            tf = cfg.ladder_tfs[r.npos - 2]
            R = ref(tf)
            hL, lL, cL = list(R.h), list(R.l), list(R.c)
            key = ("ind", tf, spec["ind"])
            if key not in refs:
                refs[key] = (r_stoch(hL, lL, cL, 14, 3) if spec["ind"] == "stoch"
                             else (R.c - r_ema(cL, 20)) / r_wilder(r_tr(hL, lL, cL), 14))
            vals = refs[key]
            j = _closed_by((R.t + R.n) * 1000, r.T)
            v = float(vals[j])
            ok = (v <= spec["lo"] + 1e-9) if r.side > 0 else (v >= spec["hi"] - 1e-9)
            ck.check(ok, r.i, f"{tf} closed-bar {spec['ind']} {v:.3f} {'<=' if r.side > 0 else '>='} "
                              f"{spec['lo'] if r.side > 0 else spec['hi']}")
    if name.startswith("gap"):
        for r in adds.itertuples():
            o, p = open_of[r.basket], prev[r.i]
            cnt = r.npos - 1
            if name == "gap D1 0.15":
                g = 0.15 * float(ref("D1", 14).vol_closed(o.tick))
            else:
                g = 1.0 * float(ref("H1", 24).vol_closed(o.tick)) * cfg.gap_growth ** (cnt - 1)
            dist = (p.price - r.ask) if r.side > 0 else (r.bid - p.price)
            ck.check(dist >= g * (1 - 1e-6) - 1e-9, r.i, f"add {cnt}: {dist:.3f} from the last fill >= gap {g:.3f}")
    if name == "stop 20% balance":
        for b in bk.itertuples():
            thr = 0.2 * open_of[b.id].bal
            if b.reason == K.R_STOPLOSS:
                ck.check(b.seen <= -thr + 1e-9, first_close[b.id], f"basket {b.id} stopped at {b.seen:.2f} <= -{thr:.2f} (20% of {open_of[b.id].bal:.2f})")
            else:
                ck.check(b.mae > -thr, None, f"basket {b.id} MAE {b.mae:.2f} > -{thr:.2f}")
    if name == "time 24h deep":
        for b in bk.itertuples():
            nadd = b.maxlad - 1
            if b.reason == K.R_TIME:
                ck.check(nadd >= 3 and b.close - b.open >= 86400000, first_close[b.id],
                         f"basket {b.id} time stop after {nadd} adds, {(b.close - b.open) / 3.6e6:.1f} h")
            elif nadd < 3:
                ck.check(True)
        long_deep = bk[(bk["maxlad"] >= 4) & (bk["close"] - bk["open"] > 86400000 + 60000) & (bk["reason"] != K.R_TIME)]
        ck.notes.append(f"deep baskets older than 24 h not closed by the time stop: {len(long_deep)}")
    if name in ("target b/e after 3", "target shrink"):
        cl = f[(f["act"] == K.ACT_CLOSE) & (f["reason"] == K.R_TARGET)].groupby("basket").first()
        for b in bk[bk["reason"] == K.R_TARGET].itertuples():
            c = cl.loc[b.id]
            floor = (c["ask"] - c["bid"]) * b.lots * contract
            if name == "target b/e after 3":
                tgt = floor if b.npos - 1 >= 3 else 1.0 * b.units
            else:
                tgt = max(floor, 1.0 * b.units / b.npos)
            ck.check(b.seen > tgt - 1e-9, int(c["i"]), f"basket {b.id} ({b.npos} pos) closed at {b.seen:.2f} > target {tgt:.2f}")
    if name == "final close H6 full":
        for b in bk[bk["reason"] == LK.R_FINAL].itertuples():
            c = f[(f["basket"] == b.id) & (f["act"] == K.ACT_CLOSE)].iloc[0]
            v = float(ref("H6").rsi(c["tick"], c["bid"]))
            ok = b.npos == n_t + 1 and ((v <= 35 + 1e-6) if b.side > 0 else (v >= 65 - 1e-6))
            ck.check(ok, int(c["i"]), f"basket {b.id}: ladder full ({b.npos} pos), H6 RSI {v:.2f}")
    if name == "add gate H1 trend":
        for r in adds.itertuples():
            tr = float(ref("H1").trend(r.tick))
            ck.check(r.side * tr > 0, r.i, f"add side {r.side:+d}, H1 MACD signal sign {tr:+.0f}")
    if name in ("add gate EMA200 D1", "add gate ADX H1>30"):
        tf = "D1" if "EMA" in name else "H1"
        R = ref(tf)
        if name not in refs:
            if tf == "D1":
                b1 = LI.bars(sym, "D1")
                refs[name] = (b1["tc_ms"], b1["c"], r_ema(list(b1["c"]), 200))
            else:
                refs[name] = ((R.t + R.n) * 1000, None, r_adx(list(R.h), list(R.l), list(R.c), 14)[0])
        tc, cc, vv = refs[name]
        for r in adds.itertuples():
            j = _closed_by(tc, r.T)
            if tf == "D1":
                ok = (r.side > 0) == (cc[j] >= vv[j])
                ck.check(ok, r.i, f"D1 close {cc[j]:.2f} vs EMA200 {vv[j]:.2f}, add side {r.side:+d}")
            else:
                ck.check(vv[j] <= 30 + 1e-9, r.i, f"ADX(14, H1) {vv[j]:.2f} <= 30")
    if name == "add gate abnormal day":
        b1 = LI.bars(sym, "D1")
        rr = np.abs(b1["c"][1:] / b1["c"][:-1] - 1)
        for r in adds.itertuples():
            j = _closed_by(b1["tc_ms"], r.T)
            thr = 2 * rr[j - 20:j].mean()
            ret = r.bid / b1["c"][j] - 1
            ck.check(not (abs(ret) > thr and r.side * ret < 0), r.i, f"today {ret:+.4%}, threshold {thr:.4%}, side {r.side:+d}")
    if name == "add gate 20:30-22:30":
        mod = (adds["tick"].to_numpy() // 1000 % 86400) // 60
        for i, m in zip(adds["i"], mod):
            ck.check(not (1230 <= m < 1350), i, f"add at {m // 60:02d}:{m % 60:02d} UTC")
    if name == "Friday flat":
        fm = _mow(opens["tick"].to_numpy())
        for i, m in zip(opens["i"], fm):
            ck.check(not (m >= 6960 or m < 60), i, f"open at minute-of-week {m}")
        for b in bk.itertuples():
            o, c = b.open, b.close
            # a basket open across Friday 20:00 must have been closed by the weekly flat
            wk = (o // 1000 // 86400 + 3) // 7
            fri = ((wk * 7 + 4 - 3) * 86400 + 20 * 3600) * 1000
            if o < fri <= c:
                ck.check(b.reason == LK.R_WEEKEND, first_close[b.id],
                         f"basket {b.id} open across Friday 20:00, closed at minute-of-week {int(_mow(b.close))} ({LE.REASON_NAMES[b.reason]})")
    if name in ("entry gate ATR pct", "confirm Supertrend H4"):
        R = ref("H4")
        if name not in refs:
            hL, lL, cL = list(R.h), list(R.l), list(R.c)
            if "ATR" in name:
                at = r_wilder(r_tr(hL, lL, cL), 14)
                b4 = LI.bars(sym, "H4")
                atf = LI.X.wilder_atr(b4["h"], b4["l"], b4["c"], 14)
                tcf = b4["tc_ms"]
                q = []
                for i, tci in enumerate((R.t + R.n) * 1000):
                    w = (tcf > tci - 100 * 86400000) & (tcf <= tci) & np.isfinite(atf)
                    q.append(np.quantile(atf[w], 0.9) if w.any() else math.nan)
                refs[name] = ("atr", np.asarray(at), np.asarray(q))
            else:
                refs[name] = ("st", r_supertrend(hL, lL, cL, 10, 3.0), None)
        kind, a1, a2 = refs[name]
        tc = (R.t + R.n) * 1000
        for r in opens.itertuples():
            j = _closed_by(tc, r.T)
            if kind == "atr":
                ck.check(a1[j] <= a2[j] * (1 + 1e-9), r.i, f"ATR(H4) {a1[j]:.3f} <= q90 {a2[j]:.3f}")
            else:
                ck.check(a1[j] == r.side, r.i, f"Supertrend(H4) {a1[j]:+d}, basket side {r.side:+d}")
    if name == "side D1 RSI":
        for r in opens.itertuples():
            v = float(ref("D1", 14).rsi(r.tick, r.bid))
            ck.check(v < 70 if r.side > 0 else v > 30, r.i, f"D1 forming RSI {v:.2f}, side {r.side:+d}")
    if name.startswith("stop-and-reverse"):
        m = cfg.reverse_mult
        bl = bk.reset_index(drop=True)
        for k in range(len(bl) - 1):
            b, nx = bl.iloc[k], bl.iloc[k + 1]
            if b["reason"] in (K.R_STOPLOSS, K.R_FORCE, K.R_RSI_FC) and not b["rev"]:
                ok = (nx["rev"] and nx["side"] == -b["side"] and nx["open"] - b["close"] <= 60000
                      and nx["units"] == max(1, int(math.floor(b["units"] * m + 0.5))))
                ck.check(ok or not nx["rev"], int(open_of[nx["id"]].i) if nx["rev"] else None,
                         f"basket {b['id']} {fast.REASON_NAMES[int(b['reason'])]} -> reverse {nx['side']:+d} x{nx['units']} "
                         f"after {(nx['open'] - b['close']) / 1000:.1f}s")
                if nx["rev"]:
                    ck.ann[int(first_close[b["id"]])] = f"{fast.REASON_NAMES[int(b['reason'])]}: a reversal follows"
            if b["rev"]:
                ck.check(not nx["rev"], None, f"a reversal basket {b['id']} did not reverse again")
    if name == "hedge-on-depth":
        R1 = ref(cfg.ladder_tfs[0])
        frozen = {}
        for r in f[f["act"] == LK.ACT_HEDGE].itertuples():
            lad = f[(f["basket"] == r.basket) & f["act"].isin([K.ACT_OPEN, K.ACT_ADD]) & (f["i"] < r.i)]
            first = r.basket not in frozen
            v1 = float(R1.rsi(r.tick, r.bid))
            zone_ok = v1 < 65 + 1e-6 if side_of[r.basket] > 0 else v1 > 35 - 1e-6
            ok = (first and r.npos == n_t + 2 and abs(r.lots - round(lad["lots"].sum(), 2)) < 1e-9
                  and r.side == -side_of[r.basket] and zone_ok and r.bprofit < 0)          # one hedge per basket
            frozen.setdefault(r.basket, r.bprofit)
            ck.check(ok, r.i, f"hedge {r.lots:.2f} lots vs ladder {lad['lots'].sum():.2f}, floating {r.bprofit:.2f} "
                              f"({'first' if first else 'frozen ' + format(frozen[r.basket], '.2f')}), tier-1 RSI {v1:.2f}")
        for r in f[(f["act"] == K.ACT_CLOSE) & (f["reason"] == LK.R_UNWIND)].itertuples():
            v = float(R1.rsi(r.tick, r.bid))
            s = side_of[r.basket]
            ck.check(v >= 65 - 1e-6 if s > 0 else v <= 35 + 1e-6, r.i, f"unwind: tier-1 RSI {v:.2f}")
        for b in bk[bk["reason"] == LK.R_HEDGE_STOP].itertuples():
            net = b.seen + b.part                    # the basket's whole P/L: floating + realised hedge legs
            ck.check(net <= 2 * frozen[b.id] + 1e-9, last_close[b.id],
                     f"net stop: floating {b.seen:.2f} + realised {b.part:.2f} = {net:.2f} <= 2 x {frozen[b.id]:.2f}")
        for b in bk[(bk["reason"] == K.R_TARGET) & (bk["nhedge"] > 0)].itertuples():
            net = b.seen + b.part
            ck.check(net > 1.0 * b.units - 1e-9, last_close[b.id],
                     f"net target: floating {b.seen:.2f} + realised {b.part:.2f} = {net:.2f} > {1.0 * b.units:.2f}")
    if name == "counter-ladder":
        for r in adds.itertuples():
            o, p = open_of[r.basket], prev[r.i]
            s = side_of[r.basket]
            g = float(ref("H1").vol_closed(o.tick))
            dist = (p.bid - r.bid) if s > 0 else (r.ask - p.ask)
            cnt = r.npos - 1
            exp = round(mult[cnt] * r.units * cfg.mtqty + 1e-12, 2)
            ck.check(r.side == -s and dist >= g * (1 - 1e-6) - 1e-9 and abs(r.lots - exp) < 1e-9, r.i,
                     f"add {cnt} on side {r.side:+d} (basket {s:+d}), moved {dist:.3f} >= {g:.3f}, lots {r.lots:.2f}")
    if name in ("partial LIFO", "partial overlap"):
        pc = f[(f["act"] == K.ACT_CLOSE) & (f["reason"].isin([LK.R_PARTIAL, LK.R_OVERLAP]))]
        for (bid_, T), g in pc.groupby(["basket", "T"]):
            if name == "partial LIFO":
                r = g.iloc[0]
                still = f[(f["basket"] == bid_) & f["act"].isin([K.ACT_OPEN, K.ACT_ADD]) & (f["T"] <= T)]
                closed = f[(f["basket"] == bid_) & (f["act"] == K.ACT_CLOSE) & (f["i"] < r["i"])]
                open_ts = sorted(set(still["T"]) - set(closed["pos_t"]))
                ck.check(len(g) == 1 and r["pos_t"] == max(open_ts) and r["profit"] > 1.0 * r["units"] - 1e-9, int(r["i"]),
                         f"closed the newest leg (opened {pd.Timestamp(r['pos_t'], unit='ms'):%H:%M:%S}) at +{r['profit']:.2f} > {r['units']}")
            else:
                cost = (g["ask"].iloc[0] - g["bid"].iloc[0]) * g["lots"].sum() * contract
                gs = g.sort_values("pos_t")
                p_old, p_new = float(gs["profit"].iloc[0]), float(gs["profit"].iloc[-1])
                ok = len(g) == 2 and p_old < 0 and p_new + p_old >= cost - 1e-9
                ck.check(ok, int(g["i"].iloc[0]), f"newest {p_new:+.2f} + oldest {p_old:+.2f} >= spread cost {cost:.2f}")
    if name.startswith("sizing"):
        b1 = LI.bars(sym, "D1")
        at = r_wilder(r_tr(list(b1["h"]), list(b1["l"]), list(b1["c"])), 14)
        for r in opens.itertuples():
            j = _closed_by(b1["tc_ms"], r.T)
            if name.startswith("sizing pre-funded"):
                loss = sum(mult[q] for q in range(n_t + 1)) * (1.5 * at[j] + (r.ask - r.bid)) * upp
                u = min(max(int(math.floor(0.3 * r.bal / loss)), 1), cfg.unit_max_limit)
            else:
                u = min(max(int(math.floor(cfg.vt_k * r.bal / (at[j] * contract) + 0.5)), 1), cfg.unit_max_limit)
            ck.check(r.units == u, r.i, f"unit {r.units} = formula {u} (balance {r.bal:.2f}, ATR(D1) {at[j]:.3f})")
    _accounting(ck, f, bk, raw, float(cfg.initial_balance))
    return ck


def _trace_md(name: str, ck: Checker, raw: dict, prep, n: int = 3) -> str:
    f, bk = _fill_view(raw, prep), _basket_view(raw)
    # baskets the check annotated, the first three
    ids = []
    for i in sorted(ck.ann):
        b = int(f.loc[i, "basket"])
        if b not in ids:
            ids.append(b)
        if len(ids) == n:
            break
    if not ids:
        ids = list(bk["id"][:n])
    out = [f"### {name}", "", f"{ck.n} rule checks, {ck.bad} failed; {ck.acct_n} accounting checks, {ck.acct_bad} failed. "
           + "; ".join(ck.notes[:3]), "",
           "| fill | time (UTC) | action | side | lots | price | P/L | reason | check |", "|---|---|---|---|---|---|---|---|---|"]
    for b in ids:
        for r in f[f["basket"] == b].itertuples():
            out.append(f"| {r.i} | {pd.Timestamp(r.T, unit='ms'):%Y-%m-%d %H:%M:%S} | {LE.ACTION_NAMES[r.act]} | "
                       f"{'BUY' if r.side > 0 else 'SELL'} | {r.lots:.2f} | {r.price:.3f} | {r.profit:+.2f} | "
                       f"{LE.REASON_NAMES[r.reason]} | {ck.ann.get(r.i, '')} |")
        bb = bk[bk["id"] == b].iloc[0]
        out.append(f"| | basket {b} | **{LE.REASON_NAMES[int(bb['reason'])]}** | | | | **{bb['pnl']:+.2f}** | | "
                   f"{bb['opened']} positions opened |")
    return "\n".join(out) + "\n"


def _features_one(sym: str):
    a, z = FEATURE_Q
    base = LE.live_config(sym, start=a, end=z).replace(**live_timing(1))
    tfs = set(base.timeframes())
    for ov in FEATURES.values():
        tfs |= set(base.replace(**ov).timeframes())
    prep = LE.prepare(sym, a, z, sorted(tfs, key=TF_SECONDS.get), mode="ticks")
    # vol-target k: the median unit equals the live rule's at $2,000 (1), from the F1-F3 median ATR(D1)
    b1 = LI.bars(sym, "D1")
    at = LI.X.wilder_atr(b1["h"], b1["l"], b1["c"], 14)
    sel = (b1["t"] >= pd.Timestamp("2018-11-13").timestamp()) & (b1["t"] < pd.Timestamp("2024-11-13").timestamp())
    k_vt = float(np.nanmedian(at[sel]) * base.spec.contract_size / 2000.0)
    refs, rows, md = {}, [], []
    for name, ov in FEATURES.items():
        if name.startswith("sizing vol-target"):
            ov = {**ov, "vt_k": k_vt * (3.0 if "x3" in name else 1.0)}
        cfg = base.replace(**ov)
        t0 = time.time()
        res, raw = LE.run(cfg, prep, light=True, raw=True)
        ck = _verify(name, cfg, prep, raw, refs)
        live_like = res.counters
        rows.append({"symbol": sym, "feature": name, "baskets": len(res.baskets), "adds": res.counters["ladder_adds"],
                     "net": round(res.scalars["final_equity"] - cfg.initial_balance, 2), "checks": ck.n, "failed": ck.bad,
                     "acct_checks": ck.acct_n, "acct_failed": ck.acct_bad,
                     "notes": " | ".join(ck.notes[:3]), "events": {k: v for k, v in live_like.items()
                                                                  if v and k in LE.COUNTER_NAMES.values()
                                                                  and k not in fast._COUNTER_NAMES.values()},
                     "run_s": round(time.time() - t0, 1)})
        if sym == "XAUUSDm":
            md.append(_trace_md(name, ck, raw, prep))
        _log(sym, f"{name:24s}", "rule checks", ck.n, "failed", ck.bad, "| accounting", ck.acct_n, "failed", ck.acct_bad, ck.notes[:2])
    return rows, md


def features() -> pd.DataFrame:
    rows, md = [], []
    for sym in SYMBOLS:
        r, m = _features_one(sym)
        rows += r
        md += m
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "features.csv", index=False)
    head = [f"# Hand traces: each new path switched on (gold, {FEATURE_Q[0]} to {FEATURE_Q[1]}, raw ticks, loop timing seed 1)", "",
            "Every fill of the quarter is checked against the path's rule with values recomputed independently "
            "(bars by pandas from the M1 store; RSI, MACD, volatility and the indicators by plain loops). "
            "Below, three baskets per path, fill by fill, with the checked quantity.", ""]
    (OUT / "TRACES.md").write_text("\n".join(head) + "\n".join(md))
    _log("features:", int(((d["failed"] == 0) & (d["acct_failed"] == 0)).sum()), "of", len(d), "paths without a failed check")
    return d


# ───────────────────────────── 5. anchors ─────────────────────────────

LONG_ANCHORS = {   # A3 (live, wiped), A4 (live per unit), A5 (V3-lite): final10 / MAP section 4, to the cent
    "XAUUSDm": {"A3_wiped_at": "2019-05-21 13:35", "A3_baskets": 1938, "A4_net": -39689.81, "A4_baskets": 62937,
                "A5_final": 11957.34, "A5_dd": 33.0, "A5_trades": 809},
    "BTCUSDm": {"A3_wiped_at": "2019-06-26 03:57", "A3_baskets": 1997, "A4_net": -62820.81, "A4_baskets": 56842,
                "A5_final": 2914.34, "A5_dd": 18.33, "A5_trades": 1154},
}


def anchor_table(sym: str) -> pd.DataFrame:
    parts = []
    for f in ("holdout", "dev"):
        d = pd.read_csv(ROUND4 / f"top3_v4_{f}_{sym}.csv")
        parts.append(d[d["design"] == "Live"][["period", "window", "segment", "seed", "acct_net", "acct_wiped", "baskets"]])
    return pd.concat(parts, ignore_index=True)


def _anchor_one(task):
    sym, seg = task
    a, z = [s.strip() for s in seg.split("→")]
    cfg = LE.live_config(sym, start=a, end=z)
    prep = LE.prepare(sym, a, z, cfg.timeframes(), mode="ticks")
    out = []
    for seed in range(1, 9):
        r = LE.run(cfg.replace(**live_timing(seed)), prep, light=True)
        out.append({"symbol": sym, "segment": seg, "seed": seed, "new_net": round(r.scalars["final_equity"] - 2000.0, 2),
                    "new_baskets": len(r.baskets), "new_wiped": bool(r.scalars["stopped_out"])})
    return out


def anchors(jobs: int = 5) -> pd.DataFrame:
    tabs = {s: anchor_table(s) for s in SYMBOLS}
    tasks = [(s, seg) for s in SYMBOLS for seg in tabs[s]["segment"].unique()]
    with mp.get_context("fork").Pool(jobs) as pool:
        got = pd.DataFrame([r for part in pool.imap_unordered(_anchor_one, tasks) for r in part])
    rows = []
    for s in SYMBOLS:
        m = tabs[s].merge(got[got["symbol"] == s], on=["segment", "seed"])
        m["symbol"] = s
        m["match"] = (m["acct_net"].round(2) == m["new_net"]) & (m["baskets"] == m["new_baskets"]) & (m["acct_wiped"] == m["new_wiped"])
        rows.append(m)
    d = pd.concat(rows, ignore_index=True)
    d.to_csv(OUT / "anchor_184.csv", index=False)
    for s in SYMBOLS:
        x = d[d["symbol"] == s]
        _log(s, f"A2: {int(x['match'].sum())}/{len(x)} rows equal; mean {x['new_net'].mean():.2f}, lost {(x['new_net'] < 0).sum()}, "
                f"wiped {x['new_wiped'].sum()}")
        a1 = x[(x["segment"].str.startswith("2026-08-13")) & (x["seed"] == 2)]
        _log(s, "A1 (2026-08-13, seed 2):", a1[["new_net", "new_baskets"]].to_dict("records"))
    return d


def _long_one(sym: str) -> dict:
    import gc
    a, z = "2018-11-13", "2026-11-13"
    r4 = json.loads((ROUND4 / "top3_v4_XAUUSDm_designs.json").read_text())
    live = LE.live_config(sym, start=a, end=z)
    v3 = live.replace(**r4["V3-lite"])
    tfs = sorted(set(live.timeframes()) | set(v3.timeframes()), key=TF_SECONDS.get)
    t0 = time.time()
    prep = LE.prepare(sym, a, z, tfs, mode="sec")
    out = {"symbol": sym, "rows": prep.n_rows, "prepare_s": round(time.time() - t0, 1)}
    t0 = time.time()
    r = LE.run(live, prep, light=True)
    s = r.summary()
    out.update(A3_wiped_at=s.get("stopped_out_at"), A3_baskets=len(r.baskets), A3_s=round(time.time() - t0, 1))
    t0 = time.time()
    r = LE.run(live.replace(initial_balance=1e9, fixed_units=1), prep, light=True)
    out.update(A4_net=round(r.scalars["final_equity"] - 1e9, 2), A4_baskets=len(r.baskets), A4_s=round(time.time() - t0, 1))
    t0 = time.time()
    r = LE.run(v3, prep)
    s = r.summary()
    out.update(A5_final=round(float(s["final_equity"]), 2), A5_dd=round(float(s["max_drawdown_pct"]), 2), A5_trades=len(r.baskets),
               A5_s=round(time.time() - t0, 1))
    exp = LONG_ANCHORS[sym]
    out["match"] = {k: (out[k] == v) for k, v in exp.items()}
    out["all"] = all(out["match"].values())
    del prep, r
    gc.collect()
    return out


def long_anchors() -> pd.DataFrame:
    rows = []
    for sym in SYMBOLS:
        rows.append(_long_one(sym))
        _log(rows[-1])
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "anchor_long.csv", index=False)
    return d


# ───────────────────────────── 6. fold prepare ─────────────────────────────

FOLD_ACCOUNTS = (("2018-12-13", "2019-12-13"), ("2019-05-13", "2020-05-13"), ("2019-11-13", "2020-11-13"))
_FOLD: dict = {}


def _fold_run(task):
    name, ov, (a, z), seed = task
    sym, prep = _FOLD["sym"], _FOLD["prep"]
    r = LE.run(LE.live_config(sym, start=a, end=z).replace(**ov, **live_timing(seed)), prep, light=True)
    return {"design": name, "start": a, "seed": seed, "final": round(r.scalars["final_equity"], 2), "baskets": len(r.baskets)}


def _fold_designs():
    r4 = json.loads((ROUND4 / "top3_v4_XAUUSDm_designs.json").read_text())
    return {"L0": {}, "V3L": next(v for k, v in r4.items() if k.startswith("Top 1"))}


def fold(jobs: int = 3) -> pd.DataFrame:
    import gc
    import threading
    import psutil
    rows = []
    for sym in SYMBOLS:
        des = _fold_designs()
        tfs = sorted({tf for ov in des.values() for tf in LE.live_config(sym).replace(**ov).timeframes()}, key=TF_SECONDS.get)
        tasks = [(n, ov, w, sd) for n, ov in des.items() for w in FOLD_ACCOUNTS for sd in (1, 2)]
        t0 = time.time()
        _FOLD.update(sym=sym, prep=LE.prepare(sym, "2018-11-13", "2020-11-13", tfs, mode="ticks"))
        prep_s = time.time() - t0
        me = psutil.Process()
        rss_after_prepare = me.memory_info().rss
        peak = {"v": 0.0, "stop": False}

        def sample():
            while not peak["stop"]:
                try:
                    kids = me.children()
                    tot = me.memory_info().rss + sum(k.memory_full_info().uss for k in kids)
                    peak["v"] = max(peak["v"], tot)
                except Exception:
                    pass
                time.sleep(0.5)
        th = threading.Thread(target=sample, daemon=True)
        th.start()
        t0 = time.time()
        with mp.get_context("fork").Pool(jobs) as pool:
            shared = pool.map(_fold_run, tasks)
        shared_s = time.time() - t0
        peak["stop"] = True
        th.join()
        rows_n = _FOLD["prep"].n_rows
        _FOLD.clear()
        gc.collect()
        own = []
        for n, ov, (a, z), sd in tasks:
            p = LE.prepare(sym, a, z, tfs, mode="ticks")
            r = LE.run(LE.live_config(sym, start=a, end=z).replace(**ov, **live_timing(sd)), p, light=True)
            own.append({"final": round(r.scalars["final_equity"], 2), "baskets": len(r.baskets)})
            del p
        for s_, o in zip(shared, own):
            rows.append({"symbol": sym, **s_, "own_final": o["final"], "own_baskets": o["baskets"],
                         "within_1pct": abs(s_["final"] - o["final"]) <= 0.01 * max(abs(o["final"]), 1e-9),
                         "same_baskets": s_["baskets"] == o["baskets"], "fold_rows": rows_n,
                         "prepare_s": round(prep_s, 1), "shared_runs_s": round(shared_s, 1),
                         "rss_after_prepare_gb": round(rss_after_prepare / 1e9, 2), "peak_gb_parent_rss_plus_child_uss": round(peak["v"] / 1e9, 2),
                         "workers": jobs})
        _log(sym, "fold check done", rows[-1])
    d = pd.DataFrame(rows)
    d["pass"] = d["within_1pct"] & d["same_baskets"]
    d.to_csv(OUT / "fold_prepare.csv", index=False)
    _log("fold:", int(d["pass"].sum()), "of", len(d), "accounts equal")
    return d


# ───────────────────────────── 7. speed ─────────────────────────────

def speed() -> pd.DataFrame:
    a, z = FEATURE_Q
    rows = []
    pick = ("trigger stoch", "trigger macd_cross", "gap D1 0.15", "hedge-on-depth", "counter-ladder", "partial LIFO",
            "sizing pre-funded", "Friday flat", "add gate EMA200 D1", "confirm Supertrend H4")
    for sym in SYMBOLS:
        base = LE.live_config(sym, start=a, end=z).replace(**live_timing(1))
        tfs = set(base.timeframes())
        for k in pick:
            tfs |= set(base.replace(**FEATURES[k]).timeframes())
        t0 = time.time()
        prep = LE.prepare(sym, a, z, sorted(tfs, key=TF_SECONDS.get), mode="ticks")
        prep_s = time.time() - t0
        old = BacktestConfig.live(sym, start=a, end=z).replace(**live_timing(1))
        cases = [("existing engine, live", lambda: fast.run(old, prep, light=True)),
                 ("new engine, live", lambda: LE.run(base, prep, light=True))]
        for k in pick:
            cfg = base.replace(**FEATURES[k])
            cases.append((f"new engine, {k}", lambda cfg=cfg: LE.run(cfg, prep, light=True)))
        for label, fn in cases:
            fn()                                          # warm (series caches, compile)
            ts = []
            for _ in range(3):
                t0 = time.time()
                fn()
                ts.append(time.time() - t0)
            rows.append({"symbol": sym, "case": label, "rows": prep.n_rows, "prepare_s": round(prep_s, 1),
                         "run_s_median": round(float(np.median(ts)), 2)})
            _log(rows[-1])
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "speed.csv", index=False)
    return d


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    OUT.mkdir(parents=True, exist_ok=True)
    what = argv[0]
    jobs = int(argv[1]) if len(argv) > 1 else 4
    fn = {"identity": lambda: identity(jobs), "tfs": timeframes, "ind": indicators, "features": features,
          "anchors": lambda: anchors(jobs), "long": long_anchors, "fold": lambda: fold(jobs), "speed": speed}[what]
    t0 = time.time()
    fn()
    _log(f"{what} done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
