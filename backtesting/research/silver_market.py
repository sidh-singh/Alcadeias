"""
Silver (XAGUSDm) as a market: the measurements behind backtest_results/silver/MARKET.md.

    python -m backtesting.research.silver_market sec    spreads by hour + data quality from sec.npz, every month
    python -m backtesting.research.silver_market m1     the market profile from M1 bars, data to 2024-06-30 ONLY

The rule (silver study, step 'market'): anything that could steer the choice of strategies (returns, trends,
volatility, patterns, the relation to gold) uses data up to 2024-06-30 only. For 2024-07 .. 2026-11 the 'sec' pass
reports data quality (holes, bad ticks, silences) and spread levels in dollars, nothing else.

Conventions:
- Session day = the New York day shifted by 7 hours (the Exness daily break sits at 17:00 New York, 20:58-22:01 UTC
  in US summer, 21:58-23:01 in winter), so Sunday's open belongs to Monday and Friday's close to Friday.
- Prices are the M1 bid closes; M1 returns are kept only inside one session day and when the bars are <= 5 min apart.
- Splits: warm-up 2017-11..2018-10, DEV 2018-11-01..2022-12-31, VAL 2023-01-01..2024-06-30.
- t-statistics are heteroskedasticity-robust (White); events that overlap in time make them optimistic.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "data" / "store"
OUT = ROOT / "backtest_results" / "silver" / "market"
SYM, GOLD = "XAGUSDm", "XAUUSDm"
CUT_S = int(pd.Timestamp("2024-07-01", tz="UTC").timestamp())
START = (2017, 11)
DEV_A, VAL_A, CUT_D = pd.Timestamp("2018-11-01"), pd.Timestamp("2023-01-01"), pd.Timestamp("2024-07-01")
OZ = {SYM: 50.0, GOLD: 1.0}  # ounces in 0.01 lot (5,000 oz and 100 oz contracts)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def months(sym, a=START, z=(2026, 11)):
    y, m = a
    while (y, m) <= z:
        p = STORE / sym / f"{y}_{m:02d}"
        if p.exists():
            yield y, m, p
        m += 1
        if m == 13:
            y, m = y + 1, 1


def bucket(y, mo):
    if y == 2024:
        return "2024H1" if mo <= 6 else "2024H2"
    return str(y)


def save(df, name, index=False):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"{name}.csv", index=index, float_format="%.6g")


def show(df, title):
    print(f"\n## {title}")
    with pd.option_context("display.width", 250, "display.max_columns", 40, "display.max_rows", 200):
        print(df.to_string(float_format=lambda v: f"{v:.4g}"))


def rt(x):
    """mean, White t of the mean (= mean/sd*sqrt(n))."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan, np.nan, len(x)
    s = x.std(ddof=1)
    return x.mean(), (x.mean() / s * math.sqrt(len(x))) if s > 0 else np.nan, len(x)


def rcorr(x, y):
    """correlation and its heteroskedasticity-robust t (sum xy / sqrt(sum x^2 y^2), demeaned)."""
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 10:
        return np.nan, np.nan, len(x)
    x = x - x.mean()
    y = y - y.mean()
    c = (x * y).sum() / math.sqrt((x * x).sum() * (y * y).sum())
    t = (x * y).sum() / math.sqrt((x * x * y * y).sum())
    return c, t, len(x)


# ----------------------------------------------------------------------------------------------- sec pass

def gap_kind(s_ms, e_ms):
    S = pd.Timestamp(int(s_ms), unit="ms", tz="UTC")
    L = (e_ms - s_ms) / 3.6e6
    wd, hr = S.weekday(), S.hour + S.minute / 60
    if L >= 30 and (wd == 4 and hr >= 19 or wd == 5):
        return "weekend"
    if wd <= 3 and 20.5 <= hr < 22.5 and 0.75 <= L <= 1.6:
        return "break"
    if L >= 2:
        return "closure"
    return "silence"


def sec_pass():
    H, Q, ev = {}, {}, []
    prev = None  # (t_ms, bid) of the previous month's last quote
    for y, mo, p in months(SYM):
        d = np.load(p / "sec.npz")
        t, b, a = d["t_ms"], d["bid"], d["ask"]
        k = bucket(y, mo)
        if k not in H:
            H[k] = np.zeros((24, 1001), np.int64)
            Q[k] = dict(bucket=k, months=0, seconds=0, active_days=0, inverted=0, wide10x=0, jumps_05pct=0,
                        bad_ticks=0, silence_5_30m=0, silence_30m_2h=0, closures=0, closure_h=0.0, weekends=0,
                        breaks=0, break_min_med=[], break_min_max=0.0)
        q = Q[k]
        q["months"] += 1
        q["seconds"] += len(t)
        q["active_days"] += len(np.unique(t // 86_400_000))
        sp = np.rint((a - b) * 1000).astype(np.int64)
        hr = (t // 3_600_000) % 24
        H[k] += np.bincount(hr * 1001 + np.clip(sp, 0, 1000), minlength=24 * 1001).reshape(24, 1001)
        q["inverted"] += int((sp <= 0).sum())
        med = np.median(sp)
        q["wide10x"] += int((sp > 10 * max(med, 1)).sum())
        # silences between consecutive quoted seconds (carried across the month boundary)
        tt = t if prev is None else np.r_[prev[0], t]
        dt = np.diff(tt)
        for i in np.nonzero(dt >= 300_000)[0]:
            kind = gap_kind(tt[i], tt[i + 1])
            L = dt[i] / 60_000
            if kind == "weekend":
                q["weekends"] += 1
            elif kind == "break":
                q["breaks"] += 1
                q["break_min_med"].append(L)
                q["break_min_max"] = max(q["break_min_max"], L)
            elif kind == "closure":
                q["closures"] += 1
                q["closure_h"] += L / 60
                ev.append(dict(bucket=k, kind="closure", start=pd.Timestamp(int(tt[i]), unit="ms", tz="UTC"), minutes=L))
            else:
                if L < 30:
                    q["silence_5_30m"] += 1
                else:
                    q["silence_30m_2h"] += 1
                    ev.append(dict(bucket=k, kind="silence>=30m", start=pd.Timestamp(int(tt[i]), unit="ms", tz="UTC"), minutes=L))
        # bad ticks: a one-quote bid jump of more than 0.5% that is undone (within 0.15%) by the next quote
        bb = b if prev is None else np.r_[prev[1], b]
        r = np.diff(bb) / bb[:-1]
        big = np.nonzero(np.abs(r) > 0.005)[0]
        q["jumps_05pct"] += len(big)
        for i in big:
            if i + 2 < len(bb) and abs(bb[i + 2] - bb[i]) / bb[i] < 0.0015:
                q["bad_ticks"] += 1
                ev.append(dict(bucket=k, kind="bad_tick", start=pd.Timestamp(int(tt[i + 1]), unit="ms", tz="UTC"),
                               minutes=0.0, jump_pct=100 * r[i]))
        prev = (t[-1], b[-1])
        log(k, y, mo, len(t))
    pts = np.arange(1001) / 1000.0

    def stats(h):
        n = h.sum()
        if n == 0:
            return dict(n=0, median=np.nan, mean=np.nan, p90=np.nan, p99=np.nan)
        c = np.cumsum(h)
        qv = lambda f: pts[np.searchsorted(c, f * n)]
        return dict(n=int(n), median=qv(0.5), mean=float((h * pts).sum() / n), p90=qv(0.9), p99=qv(0.99))

    rows_h, rows_b = [], []
    for k, h in H.items():
        for hr in range(24):
            rows_h.append(dict(bucket=k, hour_utc=hr, **stats(h[hr])))
        rows_b.append(dict(bucket=k, **stats(h.sum(0))))
    pre = sum(h for k, h in H.items() if k < "2024H2")
    hold = sum(h for k, h in H.items() if k >= "2024H2")
    for lab, h in (("PRE_2017-11_2024-06", pre), ("HOLD_2024-07_2026-11", hold)):
        for hr in range(24):
            rows_h.append(dict(bucket=lab, hour_utc=hr, **stats(h[hr])))
        rows_b.append(dict(bucket=lab, **stats(h.sum(0))))
    sh, sb = pd.DataFrame(rows_h), pd.DataFrame(rows_b)
    for q in Q.values():
        bm = q.pop("break_min_med")
        q["break_min_med"] = float(np.median(bm)) if bm else np.nan
        q["seconds_per_day"] = q["seconds"] / max(q["active_days"], 1)
    qd = pd.DataFrame(Q.values())
    evd = pd.DataFrame(ev)
    save(sh, "spread_by_hour")
    save(sb, "spread_by_bucket")
    save(qd, "quality_by_bucket")
    save(evd, "quality_events")
    show(sb, "spread by bucket ($)")
    show(qd, "quality by bucket")
    piv = sh[sh.bucket.str.startswith(("PRE", "HOLD"))].pivot(index="hour_utc", columns="bucket", values=["median", "mean", "p90"])
    show(piv, "spread by UTC hour ($): pre-cut vs hold-out")
    if len(evd):
        show(evd.groupby(["bucket", "kind"]).size().unstack(fill_value=0), "quality events")
        show(evd[evd.kind != "closure"].head(40), "first non-closure events")


# ----------------------------------------------------------------------------------------------- M1 pass

def load_m1(sym, cut=CUT_S):
    fr = []
    for y, mo, p in months(sym):
        d = np.load(p / "m1.npz")
        t = d["t"]
        k = t < cut
        if not k.any():
            break
        fr.append(pd.DataFrame(dict(t=t[k], o=d["o"][k], h=d["h"][k], l=d["l"][k], c=d["c"][k], sp=d["spread_mean"][k])))
    m = pd.concat(fr, ignore_index=True).sort_values("t", kind="stable").drop_duplicates("t").reset_index(drop=True)
    m["day"] = sess_day(m.t.values)
    lc = np.log(m.c.values)
    ok = np.r_[False, (np.diff(m.t.values) <= 300) & (m.day.values[1:] == m.day.values[:-1])]
    m["r1"] = np.where(ok, np.r_[np.nan, np.diff(lc)], np.nan)
    return m


def sess_day(t_s):
    ny = pd.to_datetime(t_s, unit="s", utc=True).tz_convert("America/New_York").tz_localize(None)
    return (ny + pd.Timedelta(hours=7)).floor("D").values


def split_of(day):
    day = pd.DatetimeIndex(day)
    return np.where(day < DEV_A, "warm", np.where(day < VAL_A, "DEV", np.where(day < CUT_D, "VAL", "HOLD")))


def daily(m):
    g = m.groupby("day")
    d = pd.DataFrame(dict(o=g.o.first(), h=g.h.max(), l=g.l.min(), c=g.c.last(), n=g.size(), sp=g.sp.median()))
    d = d[d.n >= 300].copy()
    pc = d.c.shift(1)
    d["tr"] = (np.maximum(d.h, pc) - np.minimum(d.l, pc)).fillna(d.h - d.l)
    d["atr"] = d.tr.rolling(14).mean()
    d["atr_p"] = d.atr.shift(1)
    d["r"] = np.log(d.c / pc)
    d["split"] = split_of(d.index)
    d["year"] = d.index.year
    d["wd"] = d.index.weekday
    return d


def tf_bars(m, minutes):
    k = m.t.values // (minutes * 60)
    g = m.groupby(k)
    b = pd.DataFrame(dict(t=g.t.first(), o=g.o.first(), h=g.h.max(), l=g.l.min(), c=g.c.last(), sp=g.sp.mean(),
                          day=g.day.last())).reset_index(drop=True)
    pc = b.c.shift(1)
    b["tr"] = (np.maximum(b.h, pc) - np.minimum(b.l, pc)).fillna(b.h - b.l)
    b["atr_p"] = b.tr.rolling(14).mean().shift(1)
    return b


def grid(t, c, m0, N):
    """log price on the minute grid, forward-filled, and the age (minutes) of the last real bar."""
    p = np.full(N, np.nan)
    ix = t // 60 - m0
    p[ix] = np.log(c)
    has = np.zeros(N, bool)
    has[ix] = True
    last = np.maximum.accumulate(np.where(has, np.arange(N), -1))
    pf = np.where(last >= 0, p[np.maximum(last, 0)], np.nan)
    age = np.arange(N) - last
    return pf, age


def hret(pf, age, sess, h, m0):
    """non-overlapping h-minute returns on UTC-aligned marks; nan when the two marks are in different session
    days or a mark has no bar in the last 5 minutes."""
    first = (-m0) % h
    k = np.arange(first + h, len(pf), h)
    r = pf[k] - pf[k - h]
    ok = (sess[k] == sess[k - h]) & (age[k] <= 5) & (age[k - h] <= 5)
    return np.where(ok, r, np.nan), k


def ac1(r):
    return rcorr(r[1:], r[:-1])


def vr(r, q):
    """Lo-MacKinlay variance ratio with overlapping q-sums inside valid stretches, heteroskedasticity-robust z."""
    ok = np.isfinite(r)
    n = int(ok.sum())
    e = np.where(ok, r - np.nanmean(r), 0.0)
    s2 = (e * e).sum() / n
    cs = np.r_[0.0, np.cumsum(e)]
    cb = np.r_[0, np.cumsum(~ok)]
    S = cs[q:] - cs[:-q]
    S = S[(cb[q:] - cb[:-q]) == 0]
    V = (S * S).mean() / q / s2
    e2 = e * e
    den = e2.sum() ** 2
    th = 0.0
    for j in range(1, q):
        th += (2.0 * (q - j) / q) ** 2 * (n * (e2[j:] * e2[:-j]).sum() / den)
    return V, (V - 1) * math.sqrt(n) / math.sqrt(th), n


def events_table(b, tf, Ns=(20,), Ks=(1, 5, 20)):
    o, h, l, c = (b[x].values for x in "ohlc")
    atr = b.atr_p.values
    sp = b.sp.values
    spl = split_of(b.day.values)
    rows = []
    fam = {}
    for N in Ns:
        hh = b.h.rolling(N).max().shift(1).values
        ll = b.l.rolling(N).min().shift(1).values
        up = c > hh
        dn = c < ll
        upf = up & ~np.r_[False, up[:-1]]
        dnf = dn & ~np.r_[False, dn[:-1]]
        fam[f"donchian{N}"] = np.where(upf, 1, np.where(dnf, -1, 0))
    ma = b.c.rolling(20).mean().values
    sd = b.c.rolling(20).std().values
    z = (c - ma) / sd
    zp = np.r_[np.nan, z[:-1]]
    fam["band2sd"] = np.where((z > 2) & (zp <= 2), 1, np.where((z < -2) & (zp >= -2), -1, 0))
    fam["shock2atr"] = np.where(c - o > 2 * atr, 1, np.where(o - c > 2 * atr, -1, 0))
    for f, s in fam.items():
        idx = np.nonzero((s != 0) & np.isfinite(atr) & (atr > 0))[0]
        for K in Ks:
            j = idx[idx + K < len(c)]
            fw = s[j] * (c[j + K] - c[j]) / atr[j]
            spa = sp[j] / atr[j]
            row = dict(tf=tf, family=f, K=K, n=len(j))
            nz = fw[fw != 0]
            row["hit_cont"] = (nz > 0).mean() if len(nz) else np.nan
            mu, t, _ = rt(fw)
            row["fwd_atr"], row["t"] = mu, t
            for S in ("DEV", "VAL"):
                mu_s, t_s, n_s = rt(fw[spl[j] == S])
                row[f"fwd_{S}"], row[f"t_{S}"], row[f"n_{S}"] = mu_s, t_s, n_s
            row["spread_atr"] = np.nanmean(spa)
            row["net_cont"] = mu - row["spread_atr"]
            row["net_fade"] = -mu - row["spread_atr"]
            rows.append(row)
    return rows


def m1_pass():
    log("loading silver + gold M1 to 2024-06-30")
    s = load_m1(SYM)
    g = load_m1(GOLD)
    assert s.t.max() < CUT_S and g.t.max() < CUT_S
    s = s[s.t >= int(pd.Timestamp("2017-11-01", tz="UTC").timestamp())].reset_index(drop=True)
    g = g[g.t >= s.t.min()].reset_index(drop=True)
    log("bars", len(s), len(g), pd.Timestamp(int(s.t.max()), unit="s"))
    ds, dg = daily(s), daily(g)
    res = {}

    # ---- volatility by year / split
    rows = []
    for key, grp in list(ds.groupby("year")) + list(ds.groupby("split")):
        r = grp.r.dropna()
        rows.append(dict(period=key, days=len(grp), mean_close=grp.c.mean(), sd_daily_pct=100 * r.std(),
                         ann_vol_pct=100 * r.std() * math.sqrt(252), range_pct_med=100 * ((grp.h - grp.l) / grp.c).median(),
                         atr14_usd=grp.atr.mean(), atr14_pct=100 * (grp.atr / grp.c).mean(),
                         p99_absret_pct=100 * r.abs().quantile(0.99), max_absret_pct=100 * r.abs().max(),
                         kurtosis=r.kurt()))
    vy = pd.DataFrame(rows)
    save(vy, "vol_by_year")
    show(vy, "silver daily volatility by year / split (to 2024-06)")

    # ---- volatility by UTC hour (H1 bars) and weekday
    s["hk"] = s.t // 3600
    s["r2"] = s.r1 * s.r1
    gh = s.groupby("hk")
    hb = pd.DataFrame(dict(o=gh.o.first(), h=gh.h.max(), l=gh.l.min(), c=gh.c.last(), sp=gh.sp.mean(),
                           rv=gh.r2.sum(), n=gh.size(), mr=gh.r1.sum(), day=gh.day.last()))
    hb["hour"] = hb.index % 24
    hb["rng"] = 100 * (hb.h - hb.l) / hb.c
    hb["split"] = split_of(hb.day.values)
    hb = hb[hb.n >= 10]
    tot = hb.rv.sum()
    vh = hb.groupby("hour").agg(hours=("n", "size"), range_pct_mean=("rng", "mean"), range_pct_med=("rng", "median"),
                                rv_share_pct=("rv", lambda x: 100 * x.sum() / tot), spread_usd=("sp", "mean"))
    vh["range_pct_DEV"] = hb[hb.split == "DEV"].groupby("hour").rng.mean()
    vh["range_pct_VAL"] = hb[hb.split == "VAL"].groupby("hour").rng.mean()
    hb["sp_over_rng"] = hb.sp / (hb.h - hb.l).replace(0, np.nan)
    vh["spread_over_h1range_med"] = hb.groupby("hour").sp_over_rng.median()
    # drift by hour: mean of the within-hour sum of M1 returns (bps) and its t
    for hr in range(24):
        mu, t, n = rt(hb.mr[hb.hour == hr].values * 1e4)
        vh.loc[hr, "drift_bps"] = mu
        vh.loc[hr, "drift_t"] = t
    save(vh, "vol_by_hour", index=True)
    show(vh, "silver by UTC hour (H1 bars, to 2024-06)")
    rows = []
    for wd, grp in ds.groupby("wd"):
        r = grp.r.dropna()
        mu, t, n = rt(r.values * 1e4)
        rows.append(dict(weekday="Mon Tue Wed Thu Fri Sat Sun".split()[wd], days=len(grp),
                         range_pct_mean=100 * ((grp.h - grp.l) / grp.c).mean(), sd_pct=100 * r.std(),
                         mean_ret_bps=mu, t=t, pct_up=100 * (r > 0).mean(),
                         mean_ret_bps_DEV=1e4 * grp.r[grp.split == "DEV"].mean(),
                         mean_ret_bps_VAL=1e4 * grp.r[grp.split == "VAL"].mean()))
    vw = pd.DataFrame(rows)
    save(vw, "by_weekday")
    show(vw, "silver by session weekday (to 2024-06)")

    # ---- persistence: AC1, variance ratios, Hurst-style scaling
    m0 = int(min(s.t.min(), g.t.min()) // 60)
    N = int(max(s.t.max(), g.t.max()) // 60) - m0 + 1
    sess = sess_day((np.arange(N, dtype=np.int64) + m0) * 60).astype("datetime64[D]").astype(np.int64)
    gsplit = split_of(((np.arange(N, dtype=np.int64) + m0) * 60).astype("datetime64[s]"))
    pfs, ages = grid(s.t.values, s.c.values, m0, N)
    pfg, ageg = grid(g.t.values, g.c.values, m0, N)
    rows = []
    var = {}
    for h in (1, 5, 15, 60, 240):
        r, k = hret(pfs, ages, sess, h, m0)
        for S in ("ALL", "DEV", "VAL"):
            rr = r if S == "ALL" else np.where(gsplit[k] == S, r, np.nan)
            c, t, n = ac1(rr)
            var[(S, h)] = np.nanvar(rr)
            rows.append(dict(horizon=f"{h}m", h_min=h, split=S, ac1=c, t=t, n=n))
    dr = ds.r.values
    for hd, lab in ((1, "1d"), (5, "1w"), (21, "1M")):
        for S in ("ALL", "DEV", "VAL"):
            rr = dr if S == "ALL" else np.where(ds.split.values == S, dr, np.nan)
            nb = len(rr) // hd
            blk = rr[: nb * hd].reshape(nb, hd)
            br = np.where(np.isfinite(blk).all(1), blk.sum(1), np.nan)
            c, t, n = ac1(br)
            var[(S, lab)] = np.nanvar(br)
            rows.append(dict(horizon=lab, h_min=hd * 1380, split=S, ac1=c, t=t, n=n))
    pa = pd.DataFrame(rows)
    hl = []
    for S in ("ALL", "DEV", "VAL"):
        seq = [(1, 1), (5, 5), (15, 15), (60, 60), (240, 240)]
        for (a, _), (b_, _) in zip(seq[:-1], seq[1:]):
            hl.append(dict(split=S, from_to=f"{a}m-{b_}m", H=0.5 * math.log(var[(S, b_)] / var[(S, a)]) / math.log(b_ / a)))
        for a, b_, fa, fb in (("1d", "1w", 1, 5), ("1w", "1M", 5, 21)):
            hl.append(dict(split=S, from_to=f"{a}-{b_}", H=0.5 * math.log(var[(S, b_)] / var[(S, a)]) / math.log(fb / fa)))
    hu = pd.DataFrame(hl)
    r1m, _ = hret(pfs, ages, sess, 1, m0)
    vrs = []
    for S in ("ALL", "DEV", "VAL"):
        rr = r1m if S == "ALL" else np.where(gsplit[np.arange(1, N)] == S, r1m, np.nan) if len(r1m) == N - 1 else r1m
        for q in (5, 15, 60, 240):
            V, z, n = vr(rr, q)
            vrs.append(dict(base="1m", q=q, horizon=f"{q}m", split=S, VR=V, z=z, n=n))
        rd = dr if S == "ALL" else np.where(ds.split.values == S, dr, np.nan)
        for q in (2, 5, 10, 21):
            V, z, n = vr(rd, q)
            vrs.append(dict(base="1d", q=q, horizon=f"{q}d", split=S, VR=V, z=z, n=n))
    vrd = pd.DataFrame(vrs)
    save(pa, "persistence_ac1")
    save(hu, "persistence_hurst")
    save(vrd, "persistence_vr")
    show(pa.pivot(index="horizon", columns="split", values=["ac1", "t"]).reindex(
        ["1m", "5m", "15m", "60m", "240m", "1d", "1w", "1M"]), "AC1 of non-overlapping returns")
    show(vrd.pivot(index="horizon", columns="split", values=["VR", "z"]), "variance ratios")
    show(hu.pivot(index="from_to", columns="split", values="H"), "local Hurst (variance scaling)")

    # ---- gold, same persistence numbers for comparison (ALL only)
    rows = []
    for h in (1, 5, 15, 60, 240):
        r, k = hret(pfg, ageg, sess, h, m0)
        c, t, n = ac1(r)
        rows.append(dict(sym="gold", horizon=f"{h}m", ac1=c, t=t))
    for hd, lab in ((1, "1d"), (5, "1w"), (21, "1M")):
        rr = dg.r.values
        nb = len(rr) // hd
        blk = rr[: nb * hd].reshape(nb, hd)
        c, t, n = ac1(np.where(np.isfinite(blk).all(1), blk.sum(1), np.nan))
        rows.append(dict(sym="gold", horizon=lab, ac1=c, t=t))
    gpa = pd.DataFrame(rows)
    save(gpa, "gold_persistence_ac1")
    show(gpa, "gold AC1 (same method, to 2024-06)")

    # ---- breakout / fade events by timeframe
    log("events")
    rows = []
    bars = {"M5": tf_bars(s, 5), "M15": tf_bars(s, 15), "H1": tf_bars(s, 60), "H4": tf_bars(s, 240)}
    for tf, b in bars.items():
        rows += events_table(b, tf)
    dd = ds.reset_index().rename(columns={"index": "day"})
    dd["day"] = ds.index.values
    dd["t"] = 0
    rows += events_table(dd, "D1", Ns=(20, 55), Ks=(1, 5, 20))
    evt = pd.DataFrame(rows)
    save(evt, "events_breakout_fade")
    show(evt[["tf", "family", "K", "n", "hit_cont", "fwd_atr", "t", "fwd_DEV", "fwd_VAL", "spread_atr", "net_cont",
              "net_fade"]], "breakout / band / shock events: forward move in the signal direction, in ATR(14) units")

    # ---- gaps (Sunday open, daily break, closures)
    log("gaps")
    t, o, c, hi, lo = s.t.values, s.o.values, s.c.values, s.h.values, s.l.values
    atr_of = ds.atr.to_dict()
    dayv = s.day.values
    rows = []
    for i in np.nonzero(np.diff(t) >= 1800)[0] + 1:
        kind = gap_kind((t[i - 1] + 60) * 1000, t[i] * 1000)
        a = atr_of.get(pd.Timestamp(dayv[i - 1]), np.nan)
        gp = o[i] - c[i - 1]
        j = slice(i, min(i + 240, len(t)))
        filled = (lo[j].min() <= c[i - 1]) if gp > 0 else (hi[j].max() >= c[i - 1]) if gp < 0 else True
        rows.append(dict(start=pd.Timestamp(int(t[i - 1]), unit="s"), kind=kind, minutes=(t[i] - t[i - 1]) / 60,
                         gap_usd=gp, gap_pct=100 * gp / c[i - 1], gap_atr=gp / a if a else np.nan, filled_4h=filled))
    gp = pd.DataFrame(rows)
    gp["split"] = split_of(gp.start.values)
    save(gp, "gaps_events")
    rows = []
    for kind, grp in gp.groupby("kind"):
        x = grp.gap_atr.abs()
        rows.append(dict(kind=kind, n=len(grp), med_abs_usd=grp.gap_usd.abs().median(), med_abs_atr=x.median(),
                         p90_abs_atr=x.quantile(0.9), p99_abs_atr=x.quantile(0.99), max_abs_atr=x.max(),
                         max_abs_usd=grp.gap_usd.abs().max(), share_gt_0p25atr=100 * (x > 0.25).mean(),
                         share_gt_1atr=100 * (x > 1).mean(), mean_signed_atr=grp.gap_atr.mean(),
                         filled_4h_pct=100 * grp.filled_4h.mean(),
                         med_abs_usd_per_001lot=50 * grp.gap_usd.abs().median(),
                         max_usd_per_001lot=50 * grp.gap_usd.abs().max()))
    gs = pd.DataFrame(rows)
    save(gs, "gaps_summary")
    show(gs, "gaps (to 2024-06); ATR = daily ATR(14) of the day before the gap")
    show(gp.reindex(gp.gap_atr.abs().sort_values(ascending=False).index).head(10), "largest gaps")

    # ---- spikes: moves of 3+ ATR within minutes
    log("spikes")
    m1b = s[["t", "o", "h", "l", "c", "sp", "day"]].copy()
    pc = m1b.c.shift(1)
    m1b["tr"] = (np.maximum(m1b.h, pc) - np.minimum(m1b.l, pc)).fillna(m1b.h - m1b.l)
    m1b["atr_p"] = m1b.tr.rolling(14).mean().shift(1)
    rows = []
    datr = ds.atr_p.reindex(pd.DatetimeIndex(np.unique(s.day.values))).to_dict()
    tops = []
    for tf, b in (("M1", m1b), ("M5", bars["M5"]), ("M15", bars["M15"])):
        b = b.copy()
        b["year"] = pd.DatetimeIndex(b.day.values).year
        b["x"] = (b.h - b.l) / b.atr_p
        b["xd"] = (b.h - b.l) / pd.Series(pd.DatetimeIndex(b.day.values)).map(datr).values
        for y, grp in b.groupby("year"):
            rows.append(dict(tf=tf, year=y, bars=len(grp), ge3atr=int((grp.x >= 3).sum()),
                             per_1000=1000 * (grp.x >= 3).mean(), ge5atr=int((grp.x >= 5).sum()),
                             ge_half_daily_atr=int((grp.xd >= 0.5).sum()), ge_1_daily_atr=int((grp.xd >= 1).sum())))
        if tf == "M5":
            tb = b.reindex(b.xd.sort_values(ascending=False).index).head(15)
            tops = pd.DataFrame(dict(start=pd.to_datetime(tb.t, unit="s"), range_usd=tb.h - tb.l, x_daily_atr=tb.xd,
                                     x_m5_atr=tb.x, usd_per_001lot=50 * (tb.h - tb.l)))
    sk = pd.DataFrame(rows)
    save(sk, "spikes_by_year")
    save(tops, "spikes_top_m5")
    show(sk.pivot(index="year", columns="tf", values=["per_1000", "ge5atr", "ge_half_daily_atr", "ge_1_daily_atr"]),
         "spikes: bar range >= 3x its own ATR(14) per 1000 bars; >=5x count; >= 0.5 / 1 daily ATR count")
    show(tops, "15 largest M5 ranges in daily-ATR units")

    # ---- relation to gold
    log("gold")
    rows = []
    yr = pd.DatetimeIndex(((np.arange(N, dtype=np.int64) + m0) * 60).astype("datetime64[s]")).year.values
    for h in (1, 5, 15, 60, 240):
        rs_, k = hret(pfs, ages, sess, h, m0)
        rg_, _ = hret(pfg, ageg, sess, h, m0)
        row = dict(horizon=f"{h}m")
        for S in ("ALL", "DEV", "VAL"):
            mk = np.ones(len(k), bool) if S == "ALL" else gsplit[k] == S
            row[S] = rcorr(rs_[mk], rg_[mk])[0]
        for y in range(2018, 2025):
            row[str(y)] = rcorr(rs_[yr[k] == y], rg_[yr[k] == y])[0]
        sdr = np.nanstd(rs_) / np.nanstd(rg_)
        row["beta"] = row["ALL"] * sdr
        row["sd_ratio"] = sdr
        rows.append(row)
    dj = ds[["c", "r", "split", "year"]].join(dg[["c", "r"]], rsuffix="_g", how="inner")
    for hd, lab in ((1, "1d"), (5, "1w"), (21, "1M")):
        nb = len(dj) // hd
        a_ = dj.r.values[: nb * hd].reshape(nb, hd).sum(1)
        b_ = dj.r_g.values[: nb * hd].reshape(nb, hd).sum(1)
        sp_ = dj.split.values[: nb * hd: hd]
        yy = dj.year.values[: nb * hd: hd]
        row = dict(horizon=lab, ALL=rcorr(a_, b_)[0], DEV=rcorr(a_[sp_ == "DEV"], b_[sp_ == "DEV"])[0],
                   VAL=rcorr(a_[sp_ == "VAL"], b_[sp_ == "VAL"])[0])
        for y in range(2018, 2025):
            row[str(y)] = rcorr(a_[yy == y], b_[yy == y])[0]
        sdr = np.nanstd(a_) / np.nanstd(b_)
        row["beta"], row["sd_ratio"] = row["ALL"] * sdr, sdr
        rows.append(row)
    gc_ = pd.DataFrame(rows)
    save(gc_, "gold_corr")
    show(gc_, "return correlation with gold by horizon (to 2024-06); beta = silver % per gold %")
    rs1, _ = hret(pfs, ages, sess, 1, m0)
    rg1, _ = hret(pfg, ageg, sess, 1, m0)
    rows = []
    for kk in range(-60, 61):
        if kk > 0:
            c, t_, n = rcorr(rs1[kk:], rg1[:-kk])
        elif kk < 0:
            c, t_, n = rcorr(rs1[:kk], rg1[-kk:])
        else:
            c, t_, n = rcorr(rs1, rg1)
        rows.append(dict(lag_min=kk, corr=c, t=t_, n=n))
    ll = pd.DataFrame(rows)
    save(ll, "gold_leadlag_1m")
    show(ll[ll.lag_min.isin([-60, -30, -15, -10, -5, -3, -2, -1, 0, 1, 2, 3, 5, 10, 15, 30, 60])],
         "lead-lag of 1m returns: corr(silver_t, gold_t-lag); lag>0 = gold leads")
    rows = []
    for h in (1, 5, 15, 30, 60):
        rs_, k = hret(pfs, ages, sess, h, m0)
        rg_, _ = hret(pfg, ageg, sess, h, m0)
        for S in ("ALL", "DEV", "VAL"):
            mk = np.ones(len(k), bool) if S == "ALL" else gsplit[k] == S
            a_, b_ = np.where(mk, rs_, np.nan), np.where(mk, rg_, np.nan)
            g2s = rcorr(a_[1:], b_[:-1])
            s2g = rcorr(b_[1:], a_[:-1])
            own = rcorr(a_[1:], a_[:-1])
            rows.append(dict(horizon=f"{h}m", split=S, gold_past_to_silver_next=g2s[0], t_g2s=g2s[1],
                             silver_past_to_gold_next=s2g[0], t_s2g=s2g[1], silver_own_ac1=own[0], n=g2s[2]))
    pr = pd.DataFrame(rows)
    save(pr, "gold_predictive")
    show(pr, "does the last h-minute gold return predict silver's next h minutes? (non-overlapping marks)")

    # ---- gold/silver ratio
    x = np.log(dj.c_g / dj.c)
    ratio = dj.c_g / dj.c
    rows = []
    for key, grp in list(ratio.groupby(dj.year)) + list(ratio.groupby(dj.split)):
        rows.append(dict(period=key, mean=grp.mean(), min=grp.min(), max=grp.max(), first=grp.iloc[0], last=grp.iloc[-1]))
    rr_ = pd.DataFrame(rows)

    def ar1(xs):
        xs = np.asarray(xs)
        dx = np.diff(xs)
        x0 = xs[:-1] - xs[:-1].mean()
        bta = (x0 * (dx - dx.mean())).sum() / (x0 * x0).sum()
        res_ = dx - dx.mean() - bta * x0
        se = math.sqrt((res_ * res_).sum() / (len(dx) - 2) / (x0 * x0).sum())
        hlf = math.log(2) / -math.log(1 + bta) if bta < 0 else np.inf
        return bta, bta / se, hlf

    ar = []
    for S, mk in (("ALL", np.ones(len(x), bool)), ("DEV", dj.split.values == "DEV"), ("VAL", dj.split.values == "VAL")):
        b1, t1, h1 = ar1(x.values[mk])
        ar.append(dict(split=S, days=int(mk.sum()), ar_beta=b1, df_t=t1, half_life_days=h1))
    ard = pd.DataFrame(ar)
    z = (x - x.rolling(60).mean()) / x.rolling(60).std()
    zp = z.shift(1)
    ev_ = []
    for i in np.nonzero(((z > 2) & (zp <= 2)) | ((z < -2) & (zp >= -2)))[0]:
        for K in (5, 20):
            if i + K < len(x):
                ev_.append(dict(K=K, split=dj.split.values[i], dir=-np.sign(z.iloc[i]),
                                rev=-np.sign(z.iloc[i]) * (x.iloc[i + K] - x.iloc[i]) * 100))
    zev = pd.DataFrame(ev_)
    zs = zev.groupby(["K"]).rev.agg(n="size", mean_rev_pct="mean", hit=lambda v: 100 * (v > 0).mean())
    save(rr_, "ratio_by_year")
    save(ard, "ratio_ar1")
    save(zev, "ratio_z_events")
    show(rr_, "gold/silver ratio (daily closes, to 2024-06)")
    show(ard, "log ratio AR(1): DF t (5% critical about -2.86), half-life")
    show(zs, "ratio 60-day z beyond 2: reversion of the log ratio over K days, % (positive = reverted)")

    # ---- seasonality: calendar month, weekday done above
    mc = ds.c.groupby([ds.index.year, ds.index.month]).last()
    mr = np.log(mc / mc.shift(1)).dropna()
    rows = []
    for mo in range(1, 13):
        v = mr[mr.index.get_level_values(1) == mo].values * 100
        mu, t, n = rt(v)
        rows.append(dict(month=mo, n=n, mean_pct=mu, median_pct=np.median(v) if n else np.nan, pct_up=100 * (v > 0).mean() if n else np.nan, t=t))
    sm = pd.DataFrame(rows)
    save(sm, "season_month")
    show(sm, "calendar-month returns (2017-12..2024-06)")
    mvol = ds.groupby(ds.index.month).apply(lambda grp: 100 * grp.r.std())
    save(mvol.rename("sd_daily_pct").to_frame(), "season_month_vol", index=True)

    # ---- the size of one 0.01-lot unit
    rows = []
    for key in sorted(set(ds.year)) + ["DEV", "VAL"]:
        a_ = ds[ds.year == key] if isinstance(key, (int, np.integer)) else ds[ds.split == key]
        b_ = dg[dg.year == key] if isinstance(key, (int, np.integer)) else dg[dg.split == key]
        dsu = a_.c.diff().abs()
        w5 = (a_.c - a_.c.shift(5)).abs()
        rows.append(dict(period=key, silver_atr_usd_per_001=50 * a_.atr.mean(), gold_atr_usd_per_001=b_.atr.mean(),
                         ratio=50 * a_.atr.mean() / b_.atr.mean(),
                         silver_p99_day_usd=50 * dsu.quantile(0.99), gold_p99_day_usd=b_.c.diff().abs().quantile(0.99),
                         silver_worst_day_usd=50 * dsu.max(), gold_worst_day_usd=b_.c.diff().abs().max(),
                         silver_worst_5d_usd=50 * w5.max(), gold_worst_5d_usd=(b_.c - b_.c.shift(5)).abs().max(),
                         silver_atr_pct=100 * (a_.atr / a_.c).mean(), gold_atr_pct=100 * (b_.atr / b_.c).mean()))
    us = pd.DataFrame(rows)
    save(us, "unit_size")
    show(us, "one 0.01-lot unit: daily ATR(14) in $ (silver 50 oz, gold 1 oz), tails")
    log("done")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sec":
        sec_pass()
    elif cmd == "m1":
        m1_pass()
    else:
        print(__doc__)
