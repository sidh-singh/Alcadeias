"""
Stub rule modules for ``tests/test_tradeiq2.py``. They are NOT study-2 rules: no indicator of the study is read and
none of the PREREG's rules is coded here. They give the driver (``backtesting/research/tradeiq2.py``) variants and
Execs of every kind the harness runs (STATE with and without a stop, a filter, legs and per-bar exits; EVENTS with
market entries and with stop orders; LANES), from seeded random states and events, on synthetic M1 bars of August to
October 2020 (``market``). Nothing here is computed on a bar that opens before 2019-01-01 (``FROM_S``).

Every stub is causal in the way the driver's look-ahead checks see it: what it gives for a bar depends only on the
bars up to that one (the seeded draws are taken per bar position from a fixed-length stream, and an exit bar that the
served market does not hold becomes "no exit decision"), so a market cut at any instant gives the same results on the
bars it holds. Two rows are not:

* one ORACLE row per symbol reads the next bar's close from the synthetic generator itself (not from the market the
  guard served), so it wins, the synthetic grid has qualifiers, champions and finalists for the driver's selection,
  freeze, exam and account paths, and no check that compares markets cut at different instants can see it;
* the HP-DRAWN row (information only, like PREREG 6.7's) peeks five bars ahead in the served market: the driver must
  leave it out of its look-ahead checks and of the comparison page.

``MODULES`` maps the driver's module keys to these stubs, ``COUNTS`` is their count table (the driver's grid check),
``LOADER(symbol, end)`` gives the synthetic markets cut at ``end`` (``M.load``'s rule: ``end=None`` is the data end
once FINALISTS.md is frozen, else the hold-out start).
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np

from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2 as D

FROM_S = M.s_of("2019-01-01")
DAY = 86400
START = "2020-08-03"                   # a Monday
DAYS = 84
END_S = M.s_of(START) + DAYS * DAY     # the synthetic data end (exclusive): 2020-10-26
N_MAX = 50_000                         # the length of every seeded stream (more than the bars of any timeframe)


# ───────────────────────────── synthetic markets ─────────────────────────────

def m1_bars(symbol: str, start: str = START, days: int = DAYS) -> dict:
    """Seeded M1 bars: BTC around the clock; gold and the Nasdaq with gold's week (Sunday 22:05 UTC to Friday 20:57,
    a daily break 20:57-22:02); a small upward drift."""
    rng = np.random.default_rng(int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16))
    t = M.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    if symbol == "BTCUSDm":
        keep = np.ones(len(t), bool)
        p0, vol, drift, spread = 11000.0, 4.0, 0.02, 12.0
    else:
        minute = (t % DAY) // 60
        weekday = ((t // DAY) + 4) % 7                      # 0 = Sunday
        keep = ~((minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)) & (weekday != 6)
        keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
        p0, vol, drift, spread = ((1950.0, 0.35, 0.002, 0.2) if symbol == "XAUUSDm" else (11000.0, 3.0, 0.02, 1.2))
    t = t[keep]
    n = len(t)
    c = p0 + np.cumsum(rng.normal(drift, vol, n))
    o = np.concatenate(([p0], c[:-1])) + rng.normal(0.0, 0.05 * vol, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.5 * vol, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.5 * vol, n))
    return {"t": t, "o": o, "h": h, "l": lo, "c": c, "spread_mean": spread * (1.0 + 0.3 * rng.random(n)),
            "n": rng.integers(5, 60, n).astype(np.float64)}


_RAW: dict = {}
_MARKETS: dict = {}


def raw(symbol: str) -> dict:
    """The generator's whole series (to the synthetic data end), never served as a market before the freeze."""
    if symbol not in _RAW:
        _RAW[symbol] = m1_bars(symbol)
    return _RAW[symbol]


def end_of(end=None) -> int:
    """``M.load``'s end: an explicit end, else the data end once FINALISTS.md is frozen, else the hold-out start."""
    if end is None:
        return END_S if M.frozen() else min(int(M.CUT_S), END_S)
    return min(int(M.s_of(end)), END_S)


def market(symbol: str, end=None) -> M.TMarket2:
    """The synthetic market of ``symbol`` cut at ``end`` (exclusive; see ``end_of``), built through study 2's guard."""
    end_s = end_of(end)
    key = (symbol, end_s)
    if key not in _MARKETS:
        r = raw(symbol)
        keep = r["t"] + 60 <= end_s
        _MARKETS[key] = M.TMarket2(symbol, {k: v[keep] for k, v in r.items()}, end_s)
    return _MARKETS[key]


def LOADER(symbol: str, end=None) -> M.TMarket2:               # noqa: N802 - the driver's loader(symbol, end)
    return market(symbol, end)


# ───────────────────────────── seeded states and events ─────────────────────────────

def _rng(vid: str) -> np.random.Generator:
    return np.random.default_rng(int(hashlib.sha256(vid.encode()).hexdigest()[:12], 16))


def _stream(vid: str, n: int, kind: str = "u") -> np.ndarray:
    """A seeded draw per bar position, from a stream of fixed length: the first n values are the same for any n
    (so a market cut earlier sees the same draws on the bars it holds)."""
    rng = _rng(vid + "|" + kind)
    if kind == "u":
        x = rng.random(N_MAX)
    elif kind == "side":
        x = rng.choice(np.asarray([-1, 1]), N_MAX)
    else:
        x = rng.choice(np.asarray([-1, 0, 1]), N_MAX)
    if n > N_MAX:
        raise ValueError(f"{n} bars: more than the stub's stream ({N_MAX})")
    return x[:n]


def _live(b) -> np.ndarray:
    return b.t >= FROM_S


def seeded_state(ctx: M.Context, tf: str, vid: str, p: float = 0.06, long_only: bool = False) -> np.ndarray:
    b = ctx.bars(tf)
    n = len(b)
    change = (_stream(vid, n) < p) & _live(b)
    vals = _stream(vid, n, "state")
    if long_only:
        vals = np.abs(vals)
    last = np.maximum.accumulate(np.where(change, np.arange(n), -1))
    st = np.where(last >= 0, vals[np.maximum(last, 0)], 0)
    st[~_live(b)] = 0
    return st.astype(np.int64)


def oracle_state(ctx: M.Context, tf: str) -> np.ndarray:
    """Long while the NEXT bar closes higher, read from the generator (look-ahead on purpose: a stub that must win,
    and one that no truncation of the served market can reveal)."""
    b = ctx.bars(tf)
    r = raw(ctx.symbol)
    j = np.searchsorted(r["t"], b.tc + M.TF_SECONDS[tf], side="left") - 1     # the next bar's last M1 bar
    nxt = r["c"][np.clip(j, 0, len(r["c"]) - 1)]
    up = (nxt > b.c).astype(np.int64)
    up[~_live(b)] = 0
    return up


def peek_state(ctx: M.Context, tf: str, ahead: int = 5) -> np.ndarray:
    """Long while the close ``ahead`` bars later in the SERVED market is higher (look-ahead the checks can see)."""
    b = ctx.bars(tf)
    up = np.zeros(len(b), np.int64)
    if len(b) > ahead:
        up[:-ahead] = (b.c[ahead:] > b.c[:-ahead]).astype(np.int64)
    up[~_live(b)] = 0
    return up


def _stop(ctx: M.Context, tf: str, mult: float = 3.0) -> np.ndarray:
    a = np.asarray(ctx.atr(tf), np.float64)
    return np.where(np.isfinite(a) & (a > 0), mult * a, np.nan)


def seeded_events(ctx: M.Context, tf: str, vid: str, p: float):
    b = ctx.bars(tf)
    atr = np.asarray(ctx.atr(tf), np.float64)
    ok = (_stream(vid + "|events", len(b)) < p) & _live(b) & np.isfinite(atr) & (atr > 0)
    bars = np.flatnonzero(ok)
    return bars, _stream(vid + "|events", len(b), "side")[bars], atr


def exit_after(ctx: M.Context, tf: str, bars: np.ndarray, k: int) -> np.ndarray:
    """The bar k bars after each entry's, or -1 (no exit decision: the window's end closes it) where the served
    market does not hold that bar."""
    x = bars + k
    return np.where(x < len(ctx.bars(tf)), x, -1)


# ───────────────────────────── the stubs, one per module key ─────────────────────────────

def _v(s, tf, script, family, rest, eligible=True, info="", **params):
    return M.Variant(f"{s}|{tf}|{family}|{rest}", s, tf, script, family, eligible, info, params)


def _ribbon_variants(s):
    if s not in M.SYMBOLS:
        return []
    return [_v(s, "1H", "RIB", "RIB", "LS|X0|F0", side="LS", exit="X0", filter="F0"),
            _v(s, "1H", "RIB", "RIB", "LS|X0|F1", side="LS", exit="X0", filter="F1"),
            _v(s, "1H", "RIB", "RIB", "LO|X0|F0", side="LO", exit="X0", filter="F0"),
            _v(s, "1H", "RIB", "RIB", "LS|XP|F0", side="LS", exit="XP", filter="F0"),
            _v(s, "1H", "RIB", "RIB", "LO|ORACLE|F0", side="LO", exit="ORACLE", filter="F0"),
            _v(s, "1H", "RIB", "RIB", "RIB-LIT|LS|X0|F0", False, "sensitivity; not eligible", filter="F0"),
            _v(s, "4H", "RIB", "ALMA-X", "LS|X0", side="LS", exit="X0"),
            _v(s, "1H", "STK", "STK", "STK-RM|LS|S1", side="LS", stop="S1")]


def _ribbon_build(v, ctx):
    tf, t = v.tf, v.id.split("|")
    if "ORACLE" in t:
        return M.state_exec(tf, oracle_state(ctx, tf))
    st = seeded_state(ctx, tf, v.id, p=0.12, long_only="LO" in t)
    if "F1" in t:
        st = F.as_state_filter(st, *ctx.allow(tf, "F1"))
    if "XP" in t:
        return M.state_exec(tf, st, _stop(ctx, tf), legs=(M.Leg(0.5, target_r=2.0), M.Leg(0.5, no_target=True)))
    return M.state_exec(tf, st, _stop(ctx, tf) if v.family in ("RIB", "STK") else None)


def _ribbon_describe(v):
    return f"STUB {v.family} row {v.id.split('|', 2)[2]} (seeded random states; not a rule)"


def _msd_variants(s):
    if s not in M.SYMBOLS:
        return []
    return [_v(s, "4H", "MSD", "MSD-ALONE", "MSD-A1|S0", stop="S0"),
            _v(s, "4H", "MSD", "MSD-FILTER", "MSD-F4|RSI|R1|S0", stop="S0"),
            _v(s, "4H", "MSD", "MSD-FILTER", "MSD-F6|RSI|R1|S0", stop="S0")]


def _msd_build(v, ctx):
    return M.state_exec(v.tf, seeded_state(ctx, v.tf, v.id, p=0.1))


def _msd_study1_ids(v):
    s, tf = v.symbol, v.tf
    return {F_: f"{s}|{tf}|RSI|R1|{F_}|S0" for F_ in ("F0", "F1", "F2-1D")}


def _msd_warm(ctx, variants):
    for v in variants:
        ctx.atr(v.tf)


def _wyckoff_variants(s):
    if s not in M.SYMBOLS:
        return []
    return [_v(s, "1D", "WY", "WY", "WY-STD|X-S|F0", filter="F0")]


def _wyckoff_build(v, ctx):
    bars, side, atr = seeded_events(ctx, v.tf, v.id, p=0.25)
    return M.event_exec(v.tf, M.entries(bars, side, stop_dist=2.0 * atr[bars], target_r=3.0))


def _orb_variants(s):
    if s not in M.SYMBOLS:
        return []
    return [_v(s, "M15", "ORB", "ORB", "O2|F0", filter="F0"),
            _v(s, "M15", "ORB", "ORB", "O5|F0", filter="F0"),
            _v(s, "M15", "ORB", "ORB", "O1|LV", False, "control (claim 7); not eligible", filter="LV")]


def _orb_build(v, ctx):
    t = v.id.split("|")
    bars, side, atr = seeded_events(ctx, v.tf, v.id, p=0.02)
    if "O5" in t:
        b = ctx.bars(v.tf)
        return M.event_exec(v.tf, orders=M.orders(bars, b.tc[bars] + 4 * 3600, buy=b.c[bars] + 0.5 * atr[bars],
                                                  sell=b.c[bars] - 0.5 * atr[bars], stop_dist=atr[bars],
                                                  exit_bar=exit_after(ctx, v.tf, bars, 8)))
    if "O1" in t:
        return M.event_exec(v.tf, M.entries(bars, side, exit_bar=exit_after(ctx, v.tf, bars, 4)))
    return M.event_exec(v.tf, M.entries(bars, side, stop_dist=1.5 * atr[bars], target_r=1.0))


def _session_variants(s):
    if s in M.SYMBOLS:
        return [_v(s, "M5", "SH", "SH", "PRESET-CUSTOM|K2|E1", preset="Custom")]
    if s == "USTECm":
        return [_v(s, "M5", "SH", "SH", "PRESET-NASDAQ|K2|E1", False, "information only (PREREG 8 claim 10)",
                   preset="Nasdaq")]
    return []


def _session_build(v, ctx):
    lanes = []
    for lane in ("A", "B"):
        bars, side, atr = seeded_events(ctx, v.tf, v.id + lane, p=0.004)
        lanes.append(M.event_exec(v.tf, M.entries(bars, side, stop_dist=2.0 * atr[bars],
                                                  exit_bar=exit_after(ctx, v.tf, bars, 12))))
    return M.lanes_exec(lanes)


def _patterns_variants(s):
    if s not in M.SYMBOLS:
        return []
    return [_v(s, "1H", "HP", "HP-HARMONIC", "HP-HC|TP1|F0", filter="F0"),
            _v(s, "1H", "HP", "HP-HARMONIC", "HP-DRAWN|TP1", False, "information only; looks ahead (PREREG 6.7)")]


def _patterns_build(v, ctx):
    if "HP-DRAWN" in v.id.split("|"):
        return M.state_exec(v.tf, peek_state(ctx, v.tf))
    bars, side, atr = seeded_events(ctx, v.tf, v.id, p=0.05)
    return M.event_exec(v.tf, M.entries(bars, side, stop_dist=2.0 * atr[bars], target_r=1.0,
                                        exit_bar=exit_after(ctx, v.tf, bars, 30)))


def _ha_variants(s):
    if s not in M.SYMBOLS:
        return []
    return [_v(s, "1H", "HA", "HA-MANAGED", "M1|RIB-LS-X0-F0", base=f"{s}|1H|RIB|LS|X0|F0", overlay="M1")]


def _ha_build(v, ctx):
    base = v.params["base"]
    st = seeded_state(ctx, v.tf, base, p=0.12)
    n = len(ctx.bars(v.tf))
    return M.state_exec(v.tf, st, _stop(ctx, v.tf), exit_long=_stream(v.id + "|xl", n) < 0.05,
                        exit_short=_stream(v.id + "|xs", n) < 0.05)


MODULES = {
    "ribbon": SimpleNamespace(variants=_ribbon_variants, build=_ribbon_build, describe=_ribbon_describe,
                              __file__=__file__),
    "msd": SimpleNamespace(variants=_msd_variants, build=_msd_build, study1_ids=_msd_study1_ids, warm=_msd_warm,
                           __file__=__file__),
    "wyckoff": SimpleNamespace(variants=_wyckoff_variants, build=_wyckoff_build, __file__=__file__),
    "orb": SimpleNamespace(variants=_orb_variants, build=_orb_build, __file__=__file__),
    "session": SimpleNamespace(variants=_session_variants, build=_session_build, __file__=__file__),
    "patterns": SimpleNamespace(variants=_patterns_variants, build=_patterns_build, __file__=__file__),
    "ha": SimpleNamespace(variants=_ha_variants, build=_ha_build, __file__=__file__),
}

# the stubs' count table, in the driver's format: (module, family, eligible, gold, BTC, where)
TABLE = (("ribbon", "RIB", True, 5, 5, "stub"), ("ribbon", "RIB", False, 1, 1, "stub"),
         ("ribbon", "ALMA-X", True, 1, 1, "stub"), ("ribbon", "STK", True, 1, 1, "stub"),
         ("msd", "MSD-ALONE", True, 1, 1, "stub"), ("msd", "MSD-FILTER", True, 2, 2, "stub"),
         ("wyckoff", "WY", True, 1, 1, "stub"), ("orb", "ORB", True, 2, 2, "stub"),
         ("orb", "ORB", False, 1, 1, "stub"), ("session", "SH", True, 1, 1, "stub"),
         ("patterns", "HP-HARMONIC", True, 1, 1, "stub"), ("patterns", "HP-HARMONIC", False, 1, 1, "stub"),
         ("ha", "HA-MANAGED", True, 1, 1, "stub"))
COUNTS = D.counts_of(TABLE)
N_GOLD = sum(r[3] for r in TABLE)                        # the variants of one symbol (gold and BTC alike)
N_VARIANTS = 2 * N_GOLD + 1                              # gold, BTC and the one USTECm row
