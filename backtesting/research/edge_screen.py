"""
Which entry ideas predict direction, net of spread? Closed M15 bars, fifteen months, five quarters.

    python -m backtesting.research.edge_screen XAUUSDm

Every signal is measured on closed bars with no look-ahead (slower timeframes are read from their last CLOSED bar).
"""
import sys, numpy as np, pandas as pd
from ..data import store
from ..analysis.signal import votes
sym = sys.argv[1]
UNIT = 1.0 if sym.startswith("XAU") else 0.01            # USD per 1.0 of price on a 0.01 lot
Q = [("HO1", "2025-08-13", "2025-11-13"), ("HO2", "2025-11-13", "2026-02-13"), ("OOS2", "2026-02-13", "2026-05-13"),
     ("OOS1", "2026-05-13", "2026-08-13"), ("IS", "2026-08-13", "2026-11-13")]
m1 = store.load_m1(sym, store.to_ms("2025-07-01"), store.to_ms("2026-11-13"))
def bars(tf_s):
    b = store.resample_bars(m1, tf_s)
    return pd.DataFrame({k: np.asarray(b[k], float) for k in ("o", "h", "l", "c")}, index=pd.to_datetime(np.asarray(b["t"]) * 1000, unit="ms"))
def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)
def macd_sig(c):
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); return m.ewm(span=9, adjust=False).mean()
b = bars(900); c = b["c"]
def slow(tf_s, f):          # a value of a slower timeframe as known at each M15 close (last CLOSED slow bar only)
    s = f(bars(tf_s)["c"]); s.index = s.index + pd.Timedelta(seconds=tf_s)       # available once that bar has closed
    return s.reindex(c.index + pd.Timedelta(seconds=900), method="ffill").set_axis(c.index)
h4t, h1t, d1t = np.sign(slow(14400, macd_sig)), np.sign(slow(3600, macd_sig)), np.sign(slow(86400, lambda x: x - x.ewm(span=20, adjust=False).mean()))
r15, r1h, r4h = rsi(c), slow(3600, rsi), slow(14400, rsi)
v = votes(c.reset_index(drop=True), first=600).set_axis(c.index[600:]).reindex(c.index)
bu, bd = (v["macd"] == 1) & (v["rsi"] == 1), (v["macd"] == -1) & (v["rsi"] == -1)
hi96, lo96 = b["h"].rolling(96).max().shift(1), b["l"].rolling(96).min().shift(1)
atr = (b["h"] - b["l"]).rolling(96).mean()
lo5, lo_prev = b["l"].rolling(5).min(), b["l"].rolling(25).min().shift(5)
rlo5, rlo_prev = r15.rolling(5).min(), r15.rolling(25).min().shift(5)
hi5, hi_prev = b["h"].rolling(5).max(), b["h"].rolling(25).max().shift(5)
rhi5, rhi_prev = r15.rolling(5).max(), r15.rolling(25).max().shift(5)
S = {  # name -> (+1 long / -1 short series, 0 = no signal)
 "bot votes agree (live M15)": bu.astype(int) - bd.astype(int),
 "bot votes + with H4 trend": (bu & (h4t > 0)).astype(int) - (bd & (h4t < 0)).astype(int),
 "bot votes + against H4 trend": (bu & (h4t < 0)).astype(int) - (bd & (h4t > 0)).astype(int),
 "bot votes + with H1 trend": (bu & (h1t > 0)).astype(int) - (bd & (h1t < 0)).astype(int),
 "bot votes + with D1 trend": (bu & (d1t > 0)).astype(int) - (bd & (d1t < 0)).astype(int),
 "H4 MACD trend, always in": h4t, "H1 MACD trend, always in": h1t, "D1 close vs EMA20, always in": d1t,
 "momentum: past 1 day": np.sign(c - c.shift(96)), "momentum: past 4 h": np.sign(c - c.shift(16)), "momentum: past 5 days": np.sign(c - c.shift(480)),
 "M15 RSI <30 long / >70 short": (r15 < 30).astype(int) - (r15 > 70).astype(int),
 "M15 RSI extreme, with H4 trend": ((r15 < 35) & (h4t > 0)).astype(int) - ((r15 > 65) & (h4t < 0)).astype(int),
 "H1 RSI <30 long / >70 short": (r1h < 30).astype(int) - (r1h > 70).astype(int),
 "H4 RSI <30 long / >70 short": (r4h < 30).astype(int) - (r4h > 70).astype(int),
 "breakout of 1-day high/low": (c > hi96).astype(int) - (c < lo96).astype(int),
 "bounce: within 0.25 ATR of 1-day low/high": ((c - lo96).between(0, 0.25 * atr * 4)).astype(int) - ((hi96 - c).between(0, 0.25 * atr * 4)).astype(int),
 "RSI divergence (M15)": ((lo5 < lo_prev) & (rlo5 > rlo_prev + 3) & (r15 < 45)).astype(int) - ((hi5 > hi_prev) & (rhi5 < rhi_prev - 3) & (r15 > 55)).astype(int),
 "RSI divergence, with H4 trend": ((lo5 < lo_prev) & (rlo5 > rlo_prev + 3) & (r15 < 45) & (h4t > 0)).astype(int) - ((hi5 > hi_prev) & (rhi5 < rhi_prev - 3) & (r15 > 55) & (h4t < 0)).astype(int),
 "RSI divergence at 1-day low/high": ((lo5 < lo_prev) & (rlo5 > rlo_prev + 3) & (lo5 <= lo96 + atr)).astype(int) - ((hi5 > hi_prev) & (rhi5 < rhi_prev - 3) & (hi5 >= hi96 - atr)).astype(int),
}
sec = store.load_sec(sym, store.to_ms("2026-08-13"), store.to_ms("2026-11-13")); cost = float(np.median(sec["ask"] - sec["bid"])) * UNIT
rows = []
for name, s in S.items():
    s = pd.Series(np.asarray(s, float), index=c.index).fillna(0)
    out = {"signal": name}
    for k in (4, 16, 64):
        f = (c.shift(-k) - c) * UNIT * s
        x = f[(s != 0) & (c.index >= "2025-08-13")].dropna()
        out[f"n"] = len(x); out[f"mean{k}"] = x.mean(); out[f"t{k}"] = x.mean() / (x.std() / np.sqrt(max(len(x) / k, 1)))
        if k == 16:
            qs = [f[(s != 0) & (c.index >= a) & (c.index < z)].mean() for _, a, z in Q]
            out["q+"] = sum(q > 0 for q in qs); out["per_quarter_16"] = " ".join(f"{q:+.2f}" for q in qs)
    rows.append(out)
t = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 44)
print(f"{sym}: mean P/L in USD per 0.01 lot after k M15 bars, gross; one round trip costs about {cost:.2f} (median spread, Aug-Nov 2026); t = t-stat with overlap discounted; q+ = quarters (of 5) with a positive mean at 16 bars")
print(t[["signal", "n", "mean4", "t4", "mean16", "t16", "mean64", "t64", "q+", "per_quarter_16"]].round(2).to_string(index=False))
r = (c.shift(-4) - c) * UNIT; hr = r.groupby(c.index.hour).agg(["mean", "std", "count"]); hr["t"] = hr["mean"] / (hr["std"] / np.sqrt(hr["count"] / 4))
qh = pd.concat([r[(c.index >= a) & (c.index < z)].groupby(c.index[(c.index >= a) & (c.index < z)].hour).mean().rename(n) for n, a, z in Q], axis=1)
hr["q+"] = (qh > 0).sum(axis=1)
print("hour of day (UTC): mean P/L of holding long for the next hour:", " ".join(f"{h}:{m:+.2f}(t{tt:+.1f},q{int(q)})" for h, m, tt, q in zip(hr.index, hr["mean"], hr["t"], hr["q+"])))
