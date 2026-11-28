"""
TradeIQ study 2: the filters of PREREG section 5, as allow-masks per signal bar, and the two ways to apply them.

Every filter of one symbol and signal timeframe is a pair (allow_long, allow_short) of boolean arrays, one value per
bar of ``ctx.bars(tf)``, known at that bar's close (``allow(ctx, tf, name)``, cached in the ``Context``):

| Filter | allow_long / allow_short at the close of bar i |
|---|---|
| F0 | always / always |
| F1 | close[i] > MA200[i] / close[i] < MA200[i], MA200 = SMA(close, 200) of the same timeframe (``tradeiq_ind.ma200``) |
| F2-4H, F2-1D | the same on the last CLOSED 4H / 1D bar (close time at or before bar i's close; ``tradeiq_market.htf_at``), for every signal timeframe below it (M5, M15, 1H; F2-1D also 4H) |
| F3 | TSI > 0 / TSI < 0: study 1's ``bjorgum_tsi`` (short 5, long 25) of the signal timeframe; on M5 and M15 the TSI of the last closed 1H bar |
| LO | always / never (long only) |
| FR | the Trend Target Ribbon's trend is +1 / -1: of the last closed 4H bar for 1H, of the last closed 1D bar for 4H, of the 1D bar itself for 1D (``tradeiq2_ind_ribbon.ribbon(o, h, l, c)['trend']``) |
| FS | the Market Structure Dashboard's label is >= +1 (LEAN BULL, BULLISH) / <= -1 (LEAN BEAR, BEARISH), on the signal chart (``tradeiq2_ind_msd.structure_dashboard(rows, chart_tf)['label']``) |

Where a value does not exist yet (the MA200's or the TSI's warm-up, no higher bar closed yet, a ribbon before its
first setup) neither side is allowed, as in study 1 (``tradeiq.htf_sides``: a NaN comparison is False). A strict
inequality: a close exactly on its MA200 allows neither side.

How a filter applies (PREREG 5):
* ``as_state_filter(state, al, ash)``: on a state rule a state the filter does not allow becomes flat (study 1's
  ``apply_filter``), so the position closes when the filter turns against it and opens where it turns in favour.
* ``gate_entries(E, al, ash)`` / ``gate_orders(O, al, ash)``: on an event rule the filter must agree at the decision
  close of the entry (an order: at its placement close); it does not close an open trade.
* ``fill_masks(ctx, tf, al, ash)``: per M1 bar, the allow value of the last signal bar closed at that M1 bar's open,
  for a gate checked when a stop order fills (``Exec.fill_long`` / ``fill_short``), if a rule wants that reading.

FR and FS import ``tradeiq2_ind_ribbon`` and ``tradeiq2_ind_msd`` only when asked for (they are written in parallel).
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

from . import tradeiq_ind as I
from . import tradeiq_market as TM
from . import tradeiq2_market as M2

FILTERS = ("F0", "F1", "F2-4H", "F2-1D", "F3", "LO", "FR", "FS")
INTRADAY = ("M5", "M15")
F2_OF = {"F2-4H": "4H", "F2-1D": "1D"}
# which F2 a timeframe may use: only higher bars (PREREG 5's table; F2-4H on M5 / M15 / 1H, F2-1D on M5 .. 4H)
F2_ALLOWED = {"M5": ("F2-4H", "F2-1D"), "M15": ("F2-4H", "F2-1D"), "1H": ("F2-4H", "F2-1D"), "4H": ("F2-1D",),
              "1D": ()}
RIBBON_TF = {"1H": "4H", "4H": "1D", "1D": "1D"}         # FR: the ribbon of the higher timeframe (1D: itself)
MSD_ROWS = {"1H": ("1H", "4H", "1D", "1W"), "4H": ("4H", "1D", "1W"), "1D": ("1D", "1W")}   # PREREG 6.2


def _pair(al, ash) -> Tuple[np.ndarray, np.ndarray]:
    al, ash = np.asarray(al, bool), np.asarray(ash, bool)
    al.setflags(write=False)
    ash.setflags(write=False)
    return al, ash


def ma_sides(close) -> Tuple[np.ndarray, np.ndarray]:
    """(close > MA200, close < MA200) of one series, MA200 = ``tradeiq_ind.ma200`` (NaN warm-up: neither)."""
    c = np.asarray(close, np.float64)
    m = I.ma200(c)
    with np.errstate(invalid="ignore"):
        return c > m, c < m


def htf_sides(htf: TM.TBars, ltf: TM.TBars, up, dn) -> Tuple[np.ndarray, np.ndarray]:
    """Per bar of ``ltf``, ``up`` / ``dn`` (booleans per ``htf`` bar) of the last ``htf`` bar CLOSED at its close
    (``tradeiq_market.htf_at``); before the first closed higher bar neither side. Study 1's ``tradeiq.htf_sides``
    when up / dn are the MA200 sides."""
    u = TM.htf_at(htf, np.asarray(up, np.float64), ltf, 0.0) == 1.0
    d = TM.htf_at(htf, np.asarray(dn, np.float64), ltf, 0.0) == 1.0
    return u, d


def f1(ctx: M2.Context, tf: str) -> Tuple[np.ndarray, np.ndarray]:
    return ma_sides(ctx.bars(tf).c)


def f2(ctx: M2.Context, tf: str, name: str) -> Tuple[np.ndarray, np.ndarray]:
    if name not in F2_ALLOWED.get(tf, ()):
        raise ValueError(f"{name} is not a filter of {tf} rules (PREREG 5: {', '.join(F2_ALLOWED.get(tf, ())) or 'none'})")
    hb = ctx.bars(F2_OF[name])
    up, dn = ma_sides(hb.c)
    return htf_sides(hb, ctx.bars(tf), up, dn)


def tsi(ctx: M2.Context, tf: str) -> np.ndarray:
    """Study 1's Bjorgum TSI "Fast" (5, 25) of the close of ``tf`` (cached)."""
    def make():
        a = I.bjorgum_tsi(ctx.bars(tf).c, short=5, long=25).tsi
        a.setflags(write=False)
        return a
    return ctx.get("tsi", tf, {"short": 5, "long": 25}, make)


def f3(ctx: M2.Context, tf: str) -> Tuple[np.ndarray, np.ndarray]:
    if tf in INTRADAY:
        x = tsi(ctx, "1H")
        with np.errstate(invalid="ignore"):
            return htf_sides(ctx.bars("1H"), ctx.bars(tf), x > 0.0, x < 0.0)
    x = tsi(ctx, tf)
    with np.errstate(invalid="ignore"):
        return x > 0.0, x < 0.0


def ribbon_trend(ctx: M2.Context, tf: str) -> np.ndarray:
    """The Trend Target Ribbon's trend per bar of ``tf`` (+1, -1, 0 or NaN before the first setup), from
    ``tradeiq2_ind_ribbon.ribbon(o, h, l, c)['trend']`` (cached)."""
    def make():
        from . import tradeiq2_ind_ribbon as RB
        b = ctx.bars(tf)
        a = np.asarray(RB.ribbon(b.o, b.h, b.l, b.c)["trend"], np.float64)
        if a.shape != (len(b),):
            raise AssertionError(f"ribbon trend has shape {a.shape}, the bars {len(b)}")
        a.setflags(write=False)
        return a
    return ctx.get("ribbon_trend", tf, {}, make)


def fr(ctx: M2.Context, tf: str) -> Tuple[np.ndarray, np.ndarray]:
    if tf not in RIBBON_TF:
        raise ValueError(f"FR is defined for 1H, 4H and 1D rules (PREREG 5), not {tf}")
    htf = RIBBON_TF[tf]
    tr = ribbon_trend(ctx, htf)
    if htf == tf:
        return tr == 1.0, tr == -1.0
    return htf_sides(ctx.bars(htf), ctx.bars(tf), tr == 1.0, tr == -1.0)


def msd_label(ctx: M2.Context, tf: str) -> np.ndarray:
    """The Market Structure Dashboard's bias label per bar of chart ``tf`` (-2 BEARISH .. +2 BULLISH), from
    ``tradeiq2_ind_msd.structure_dashboard(rows, tf)['label']`` with ``rows`` = {row timeframe: ``ctx.bars(row)``} for
    the chart's rows (1H: 1H, 4H, 1D, 1W; 4H: 4H, 1D, 1W; 1D: 1D, 1W; PREREG 6.2) (cached)."""
    if tf not in MSD_ROWS:
        raise ValueError(f"FS is defined on 1H, 4H and 1D charts (PREREG 6.2), not {tf}")

    def make():
        from . import tradeiq2_ind_msd as MS
        rows = {r: ctx.bars(r) for r in MSD_ROWS[tf]}
        a = np.asarray(MS.structure_dashboard(rows, tf)["label"], np.float64)
        if a.shape != (len(ctx.bars(tf)),):
            raise AssertionError(f"dashboard label has shape {a.shape}, the bars {len(ctx.bars(tf))}")
        a.setflags(write=False)
        return a
    return ctx.get("msd_label", tf, {}, make)


def fs(ctx: M2.Context, tf: str) -> Tuple[np.ndarray, np.ndarray]:
    lab = msd_label(ctx, tf)
    with np.errstate(invalid="ignore"):
        return lab >= 1.0, lab <= -1.0


def allow(ctx: M2.Context, tf: str, name: str) -> Tuple[np.ndarray, np.ndarray]:
    """(allow_long, allow_short) per bar of ``ctx.bars(tf)`` for filter ``name`` (FILTERS; see the module docstring),
    read-only, cached in the context."""
    if name not in FILTERS:
        raise ValueError(f"{name}: not a filter of PREREG 5 ({', '.join(FILTERS)})")

    def make():
        n = len(ctx.bars(tf))
        if name == "F0":
            return _pair(np.ones(n, bool), np.ones(n, bool))
        if name == "LO":
            return _pair(np.ones(n, bool), np.zeros(n, bool))
        if name == "F1":
            return _pair(*f1(ctx, tf))
        if name in F2_OF:
            return _pair(*f2(ctx, tf, name))
        if name == "F3":
            return _pair(*f3(ctx, tf))
        if name == "FR":
            return _pair(*fr(ctx, tf))
        return _pair(*fs(ctx, tf))
    return ctx.get("filter", tf, {"name": name}, make)


def combine(*pairs: Tuple[np.ndarray, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    """The AND of several (allow_long, allow_short) pairs (e.g. HV + F2-4H)."""
    if not pairs:
        raise ValueError("nothing to combine")
    al = np.logical_and.reduce([np.asarray(p[0], bool) for p in pairs])
    ash = np.logical_and.reduce([np.asarray(p[1], bool) for p in pairs])
    return _pair(al, ash)


def as_state_filter(state, al, ash) -> np.ndarray:
    """A state rule under a filter: a state the filter does not allow becomes flat (study 1's ``apply_filter``)."""
    st = np.asarray(state)
    al, ash = np.asarray(al, bool), np.asarray(ash, bool)
    if not (st.shape == al.shape == ash.shape):
        raise ValueError("the state and the masks must have one shape")
    return np.where((st == 1) & al, 1, np.where((st == -1) & ash, -1, 0)).astype(np.int8)


def gate_entries(E: M2.Entries, al, ash) -> M2.Entries:
    """An event rule under a filter: the entries whose side the filter allows at their decision bar's close."""
    al, ash = np.asarray(al, bool), np.asarray(ash, bool)
    if len(E) and (E.bar.max() >= len(al) or E.bar.min() < 0):
        raise ValueError("an entry's bar is outside the masks")
    ok = np.where(E.side == 1, al[E.bar], ash[E.bar]) if len(E) else np.zeros(0, bool)
    return E.take(ok)


def gate_orders(O: M2.Orders, al, ash) -> M2.Orders:
    """Stop orders under a filter checked at the placement close: a side the filter does not allow there is removed
    (its level, stop and target become NaN); an order left with no side is dropped."""
    al, ash = np.asarray(al, bool), np.asarray(ash, bool)
    if len(O) and (O.bar.max() >= len(al) or O.bar.min() < 0):
        raise ValueError("an order's bar is outside the masks")
    kb, ks = al[O.bar], ash[O.bar]
    cols = {k: getattr(O, k).copy() for k in O.__dataclass_fields__}
    for k in ("buy", "buy_stop", "buy_target"):
        cols[k][~kb] = np.nan
    for k in ("sell", "sell_stop", "sell_target"):
        cols[k][~ks] = np.nan
    out = M2.Orders(**cols)
    return out.take(np.isfinite(out.buy) | np.isfinite(out.sell))


def fill_masks(ctx: M2.Context, tf: str, al, ash) -> Tuple[np.ndarray, np.ndarray]:
    """Per M1 bar of the market: the allow value of the last ``tf`` bar CLOSED at the M1 bar's open (False before
    the first), for ``Exec.fill_long`` / ``fill_short``."""
    b = ctx.bars(tf)
    t = ctx.mk.t
    i = np.searchsorted(b.tc, t, side="right") - 1
    ok = i >= 0
    ii = np.maximum(i, 0)
    ml = np.ascontiguousarray(np.where(ok, np.asarray(al, bool)[ii], False))
    ms = np.ascontiguousarray(np.where(ok, np.asarray(ash, bool)[ii], False))
    return ml, ms


def available(tf: str) -> Sequence[str]:
    """The filters PREREG 5 defines for rules of timeframe ``tf`` (whether a rule uses each is its own section's
    business)."""
    out = ["F0", "F1"] + list(F2_ALLOWED.get(tf, ())) + ["F3", "LO"]
    if tf in RIBBON_TF:
        out.append("FR")
    if tf in MSD_ROWS:
        out.append("FS")
    return out
