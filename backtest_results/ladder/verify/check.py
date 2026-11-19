"""Own small implementations of the new features that decide G1 / G5 / B1, checked against the engine on a few weeks."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/port_tmp/ladder_verify")
import verify as V
from backtesting.data import store
from backtesting.research import ladder_engine as LE

def own_bars(sym, rule):
    m = store.load_m1(sym, "2016-01-01", "2026-11-20")
    df = pd.DataFrame({k: m[k] for k in "ohlc"}, index=pd.to_datetime(np.asarray(m["t"], np.int64), unit="s"))
    r = df.resample(rule, origin="epoch", label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    r["close_s"] = r.index.astype("int64") // 10**9 + pd.Timedelta(rule).total_seconds()
    return r

def rma(x, n):                       # Wilder smoothing, seeded by the first value (converges over years of history)
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()

def own_adx(b, n=14):
    h, l, c = b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy()
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    up, dn = np.r_[0, np.diff(h)], np.r_[0, -np.diff(l)]
    pdm, mdm = np.where((up > dn) & (up > 0), up, 0), np.where((dn > up) & (dn > 0), dn, 0)
    at = rma(tr, n)
    pdi, mdi = 100 * rma(pdm, n) / at, 100 * rma(mdm, n) / at
    return rma(100 * np.abs(pdi - mdi) / (pdi + mdi), n)

def own_atr(b, n=14):
    h, l, c = b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy()
    pc = np.r_[np.nan, c[:-1]]
    return rma(np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1), n)

def own_donchian(b, n=20):
    hh = b.h.shift(1).rolling(n).max().to_numpy(); ll = b.l.shift(1).rolling(n).min().to_numpy(); c = b.c.to_numpy()
    st, out = 0, np.zeros(len(c), int)
    for i in range(len(c)):
        if c[i] > hh[i]: st = 1
        elif c[i] < ll[i]: st = -1
        out[i] = st
    return out

def own_pctb(b, n=20, k=2.0):
    ma = b.c.rolling(n).mean(); sd = b.c.rolling(n).std(ddof=0)
    return ((b.c - (ma - k * sd)) / (2 * k * sd)).to_numpy()

def own_vol(b, n=24):                # EWMA (1/n) of |close change|
    return pd.Series(np.abs(np.diff(b.c.to_numpy(), prepend=np.nan))).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()

def at_decision(b, vals, t):         # value of the last bar CLOSED at or before decision time t (s)
    i = np.searchsorted(b.close_s.to_numpy(), t, side="right") - 1
    return vals[i]

def run(design, sym, start, end, **kw):
    cfg = V.make_cfg(design, sym, start, end, 1).replace(**kw) if kw else V.make_cfg(design, sym, start, end, 1)
    return LE.run(cfg, mode="ticks")

def prefund_units(f, vol, atr, contract, n_tiers, risk=0.30, atr_mult=1.5):
    g0 = vol; d_end = n_tiers * g0 + atr_mult * atr; spread = f.ask - f.bid
    loss = sum(d_end - q * g0 + spread for q in range(n_tiers + 1)) * contract * 0.01
    return int(min(max(np.floor(risk * f.balance / loss), 1), 10))

out = {}
# ── gold window: 5 Jan - 23 Feb 2026 (includes the Jan-Feb crash) ──
GS, GE = "2026-01-05", "2026-02-23"
h1, d1 = own_bars("XAUUSDm", "1h"), own_bars("XAUUSDm", "1D")
adx_h1, vol_h1, atr_d1 = own_adx(h1), own_vol(h1), own_atr(d1)
r5 = run("G5", "XAUUSDm", GS, GE); r5n = run("G5", "XAUUSDm", GS, GE, add_gate=None)
def adds_adx(r):
    a = r.fills[r.fills.action == "add"]
    return np.array([at_decision(h1, adx_h1, t.value // 10**9) for t in a.time])
x5, x5n = adds_adx(r5), adds_adx(r5n)
out["G5_gate"] = dict(adds_gated=len(x5), adds_gated_with_own_adx_gt30=int((x5 > 30).sum()), max_own_adx_gated=float(np.max(x5)) if len(x5) else None,
                      adds_ungated=len(x5n), adds_ungated_with_own_adx_gt30=int((x5n > 30).sum()),
                      net_gated=round(r5.scalars["final_equity"] - 2000, 2), net_ungated=round(r5n.scalars["final_equity"] - 2000, 2),
                      units_seen=sorted(set(r5.baskets.units.tolist())))
r1 = run("G1", "XAUUSDm", GS, GE)
op = r1.fills[r1.fills.action == "open"]
mine = [prefund_units(f, at_decision(h1, vol_h1, f.time.value // 10**9), at_decision(d1, atr_d1, f.time.value // 10**9), 100.0, 1) for f in op.itertuples()]
eng = op.units.to_numpy()
out["G1_prefund"] = dict(baskets=len(op), units_equal=int((np.array(mine) == eng).sum()), units_off_by_1=int((np.abs(np.array(mine) - eng) == 1).sum()),
                         engine_units=np.bincount(eng).tolist(), own_units=np.bincount(mine).tolist(),
                         adds=int((r1.fills.action == "add").sum()), add_tiers=sorted(set(r1.fills[r1.fills.action == "add"].tier)))
# M2 bars from the window's ticks vs the engine's prepared M2 closes
prep = LE.prepare("XAUUSDm", GS, GE, ["M2"], mode="ticks")
nw = prep.nwarm["M2"]; et, ec = prep.bar_t["M2"][nw:], prep.closes["M2"][nw:]
tk = store.load_ticks("XAUUSDm", GS, GE)
s = pd.Series(tk["bid"], index=pd.to_datetime(tk["t_ms"], unit="ms")).resample("2min", origin="epoch").last().dropna()
own = pd.Series(s.values, index=s.index.astype("int64") // 10**9)
common = np.intersect1d(et, own.index.to_numpy())
diff = np.abs(pd.Series(ec, index=et).loc[common].to_numpy() - own.loc[common].to_numpy())
out["M2_bars"] = dict(engine_bars=len(et), own_bars=len(own), common=len(common), max_abs_close_diff=float(diff.max()), n_diff=int((diff > 1e-9).sum()))

# ── BTC window: 13 Jan - 13 Jul 2021 (includes the May 2021 fall) ──
BS, BE = "2021-01-13", "2021-07-13"
h1b, h4b, d1b = own_bars("BTCUSDm", "1h"), own_bars("BTCUSDm", "4h"), own_bars("BTCUSDm", "1D")
don, pb, volb, atrb = own_donchian(h4b), own_pctb(h4b), own_vol(h1b), own_atr(d1b)
rb = run("B1", "BTCUSDm", BS, BE)
fb = rb.fills
opb, adb = fb[fb.action == "open"], fb[fb.action == "add"]
side = lambda s: 1 if s == "BUY" else -1
don_ok = [at_decision(h4b, don, f.time.value // 10**9) == side(f.side) for f in opb.itertuples()]
pb_v = [at_decision(h4b, pb, f.time.value // 10**9) for f in adb.itertuples()]
pb_ok = [(v <= 0) if side(f.side) > 0 else (v >= 1) for v, f in zip(pb_v, adb.itertuples())]
mineb = [prefund_units(f, at_decision(h1b, volb, f.time.value // 10**9), at_decision(d1b, atrb, f.time.value // 10**9), 1.0, 3) for f in opb.itertuples()]
rbn = run("B1", "BTCUSDm", BS, BE, entry_gate=None)
opn = rbn.fills[rbn.fills.action == "open"]
don_n = [at_decision(h4b, don, f.time.value // 10**9) == side(f.side) for f in opn.itertuples()]
out["B1"] = dict(baskets=len(opb), opens_on_own_donchian_side=int(sum(don_ok)),
                 ungated_baskets=len(opn), ungated_opens_against_own_donchian=int(len(don_n) - sum(don_n)),
                 adds=len(adb), adds_with_own_pctb_extreme=int(sum(pb_ok)), own_pctb_at_adds=[round(float(v), 3) for v in pb_v],
                 units_equal=int((np.array(mineb) == opb.units.to_numpy()).sum()), units_off_by_1=int((np.abs(np.array(mineb) - opb.units.to_numpy()) == 1).sum()),
                 engine_units=np.bincount(opb.units.to_numpy()).tolist(), own_units=np.bincount(mineb).tolist(),
                 net=round(rb.scalars["final_equity"] - 2000, 2), net_ungated=round(rbn.scalars["final_equity"] - 2000, 2))
print(json.dumps(out, indent=1))
json.dump(out, open("/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/port_tmp/ladder_verify/check.json", "w"), indent=1)
