"""
"Harmonic & Chart Patterns [AI-AlgoCode]" (study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.7): the
reconciliation of its two independent ports. The notes for readers are
``backtest_results/tradeiq_2027/porting/patterns.md``.

* Port A, ``backtesting/research/tradeiq2_ind_patterns.py``: the production port (numpy, one compiled zigzag loop);
  its own tests are ``test_tradeiq2_ind_patterns_a.py``.
* Port B, ``tests/tradeiq2_oracle_patterns.py``: the oracle, the script's statements bar by bar in plain Python, with
  its three ``var`` arrays kept as Pine keeps them (unshift / set / pop at 60); its own tests are
  ``test_tradeiq2_ind_patterns_b.py``.

The reconciliation found no mismatch: the two ports were equal on every series from the first run, so neither was
changed in behaviour. What is asserted here:

1. Real bars (skipped when the tick store is absent). XAUUSDm and BTCUSDm, 1H / 4H / 1D: the timeframes of PREREG
   6.7 (HP-HF and HP-HC on all three, HP-CF / HP-CS / HP-CC on 1H and 4H). From the study's data start
   (``tradeiq2_market.data_start``: gold 2016-01-01 when all twelve 2016 months are in the store, BTC 2018-01-01) to
   2024-06-30: the M1 bars come from ``external.load_market(symbol, earliest=..., end="2024-07-01")``, so nothing at
   or after the hold-out start is read, and study 1's ``TMarket.tbars`` builds the bars (what ``tradeiq2_market.load``
   serves on 1H / 4H / 1D), with study 1's and study 2's guards pointed at an empty folder. Gold is also run from
   2017-01-03 (study 1's start; those bars are a suffix of the same bars), because the zigzag depends on where the
   bars start. Asserted:
   - the swings (bar, price, pivC, high or low), and per bar ``n_swings``, ``added`` and the zigzag state port A
     returns (``isHi``, ``isLo``, ``pivP.size()``, the live swing, ``makeQ(0)`` and its bars), read from port B's
     ``Script`` after each bar;
   - the confirmed and the forming tables, row for row and column for column, through one adapter (port B's ``xs`` /
     ``ys`` tuples, oldest first, are port A's ``b0..b8`` / ``p0..p8``, newest first): integers and booleans exactly,
     floats bit for bit (``numpy.array_equal`` with NaN in the same places, and the same sign bit), the object
     columns (``name``, ``kind``, ``instance_key``) equal. No tolerance anywhere: both ports evaluate the script's
     expressions in Pine's order (``inR``'s bounds as ``(A - B) * mx + B`` and ``B - (B - A) * mn``, the plan as
     ``Q0 - dir * slK * ad`` from the left, the chart ratios as written);
   - port A's extra columns from port B's values: ``close`` is the bar's close, ``unit`` is |Q3 - Q0| (harmonic) or
     |Q1 - Q2| (chart), ``drawn`` is ``B.drawn_mask`` and is set on first hits only;
   - HP-CS's series: ``A.armed(pid, forming_q)`` equals port B's predicate with its breakout conjunct satisfied, for
     the 16 chart ids at every bar;
   - the Development counts (the harness's decision bars: closing after 2019-01-01 00:00, filled before
     2023-01-01 00:00) recorded at the reconciliation, from each port's own output. Counts only: no rule is run and
     no profit or loss is computed;
   - gold from 2016 or from 2017 gives the same Development events;
   - the alternative tie reading of ``ta.highestbars`` / ``ta.lowestbars`` (the oldest bar wins): both ports'
     zigzags agree under it too, and its effect on Development is recorded.
2. Synthetic bars: random walks with and without ties (prices rounded to 1 or 0 decimals), outside bars, repeated
   highs and lows, random depths 2-50, and short or degenerate series (0-100 bars): both ports equal.
3. The tables: port A's and port B's names, 144 constants, dispatch, directions, point counts and plan inputs are
   equal; when the Pine source is on this machine, ``c0`` appears in each chart predicate exactly once, as its last
   conjunct ``c0 < p2`` (bearish id) or ``c0 > p2`` (bullish id), which is what makes ``armed`` (HP-CS) a predicate
   of the fixed swings only.

Line numbers L... are those of the owner's copy of the script (third-party code, cited, never copied).
"""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_patterns as A
from backtesting.research import tradeiq2_market as TM2
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_patterns as B  # noqa: E402

SYMS = ("XAUUSDm", "BTCUSDm")
TFS = ("1H", "4H", "1D")                                     # PREREG 6.7
DEV = ("2019-01-01", "2023-01-01")                           # PREREG 3: Development
STUDY1_GOLD_START = "2017-01-01"                             # study 1's gold bars begin on 2017-01-03
NP = A.N_PTS_MAX                                             # 9: the most points a pattern uses
CHART_IDS = tuple(range(22, 38))
SOURCE_CANDIDATES = (
    os.environ.get("TRADEIQ2_PATTERNS_SOURCE", ""),
    "/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/"
    "scratchpad/study2/src/Harmonic and Chart Patterns Script.txt",
    "/Users/sidharthsingh/Desktop/study/indicator/Harmonic and Chart Patterns Script.txt",
    "/Users/sidharthsingh/Desktop/study/indicator/Harmonic and Chart Patterns Script.rtf",
)

# The columns both ports return (port B's xs / ys / d_bar / d_price mapped by b_rows_as_a), in port A's order.
POINTS = tuple(f"p{k}" for k in range(NP)) + tuple(f"b{k}" for k in range(NP))
CONF_COMMON = ("t_bar", "id", "name", "kind", "dir", "first_hit", "n_hits", "n_pts", "c0") + POINTS + \
    ("entry", "sl", "tp1", "tp2")
FORM_COMMON = CONF_COMMON + ("instance_key", "first_bar_of_instance")
STATE_KEYS = ("is_hi", "is_lo", "n_piv", "live_bar", "live_price", "forming_q", "forming_qbar")

# Recorded at the reconciliation (28 Nov 2026) on the study's bars, both ports equal. Per symbol and timeframe, over
# the Development decision bars: bars; swings added; confirmed detections (first hits) and hit rows; first hits that
# are chart patterns, that are bullish, that are drawn (the overlap gate); forming hit rows and bars with a forming
# hit; forming instances by their first bar over any hit, of which harmonic; instances by their first bar as the first
# hit; chart instances "armed" (every condition but the breakout close, HP-CS) by their first armed bar; then over the
# whole series to 2024-06-30: confirmed detections and the bar index of the first one.
_RECORDED = {
    ("XAUUSDm", "1H"): (23590, 3404, 950, 1465, 110, 437, 641, 10735, 7025, 2025, 1865, 1283, 312, 2026, 149),
    ("XAUUSDm", "4H"): (6385, 912, 260, 417, 30, 109, 173, 3194, 2036, 578, 531, 349, 80, 577, 83),
    ("XAUUSDm", "1D"): (1031, 140, 41, 61, 6, 18, 30, 541, 349, 87, 80, 55, 11, 76, 83),
    ("BTCUSDm", "1H"): (35016, 5030, 1342, 2152, 160, 597, 938, 15195, 9927, 2799, 2564, 1751, 421, 2187, 86),
    ("BTCUSDm", "4H"): (8756, 1247, 337, 517, 35, 139, 244, 3843, 2560, 683, 624, 450, 113, 552, 121),
    ("BTCUSDm", "1D"): (1459, 210, 48, 78, 6, 22, 39, 676, 397, 121, 112, 77, 25, 80, 115),
}

# The 'oldest' tie reading against the 'newest' one (the ports' reading), over the Development decision bars: bars
# where isHi or isLo differ; swings added on different bars (symmetric difference); confirmed first hits (t_bar, id)
# in one reading only; forming instances (key at its first bar, any hit) in one reading only. Recorded at the
# reconciliation; counts only. Gold 1H: the one extra confirmed first hit is a Bear Three Drives (id 10) that only
# the 'oldest' reading sees; 2 forming instances exist only under 'newest' and 3 only under 'oldest'.
_TIES_RECORDED = {
    ("XAUUSDm", "1H"): (7, 2, 1, 5), ("XAUUSDm", "4H"): (2, 0, 0, 0), ("XAUUSDm", "1D"): (0, 0, 0, 0),
    ("BTCUSDm", "1H"): (6, 4, 0, 0), ("BTCUSDm", "4H"): (0, 0, 0, 0), ("BTCUSDm", "1D"): (0, 0, 0, 0),
}


# ───────────────────────────── the comparison ─────────────────────────────

def same(a, b) -> bool:
    """Exact equality of two columns: the same shape and dtype; floats bit for bit (``array_equal`` with NaN in the
    same places, and the same sign bit, so 0.0 and -0.0 differ); object columns element by element."""
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    if a.dtype.kind == "f":
        return bool(np.array_equal(a, b, equal_nan=True) and np.array_equal(np.isnan(a), np.isnan(b))
                    and np.array_equal(np.signbit(a), np.signbit(b)))
    if a.dtype == object:
        return a.tolist() == b.tolist()
    return bool(np.array_equal(a, b))


def first_differences(a, b, n=3):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return [("shape", a.shape, b.shape)]
    if a.dtype != b.dtype:
        return [("dtype", str(a.dtype), str(b.dtype))]
    if a.dtype == object:
        i = [j for j, (x, y) in enumerate(zip(a.tolist(), b.tolist())) if x != y]
    elif a.dtype.kind == "f":
        i = np.flatnonzero(~((a == b) & (np.signbit(a) == np.signbit(b)) | (np.isnan(a) & np.isnan(b))))
    else:
        i = np.flatnonzero(a != b)
    return [(int(j), a[j], b[j]) for j in list(i)[:n]]


def b_rows_as_a(df: pd.DataFrame) -> pd.DataFrame:
    """Port B's confirmed / forming rows in port A's layout. ``xs`` / ``ys`` (the pattern's swing bars and prices,
    oldest first, the last = D, as ``newPat`` fills them, L606-613) become ``b0..b8`` / ``p0..p8`` (newest first,
    Q0 = D; -1 / NaN beyond ``n_pts``); ``d_bar`` / ``d_price`` are kept to be checked against ``b0`` / ``p0``."""
    m = len(df)
    P = np.full((m, NP), np.nan)
    Bb = np.full((m, NP), -1, np.int64)
    for i, (xs, ys) in enumerate(zip(df["xs"], df["ys"])):
        n = len(xs)
        P[i, :n] = np.array(ys[::-1], np.float64)
        Bb[i, :n] = np.array(xs[::-1], np.int64)
    out = df.drop(columns=["xs", "ys"]).reset_index(drop=True)
    for k in range(NP):
        out[f"p{k}"] = P[:, k]
    for k in range(NP):
        out[f"b{k}"] = Bb[:, k]
    return out


def rows_differ(a: pd.DataFrame, b: pd.DataFrame, cols, c) -> dict:
    """The columns on which port A's rows ``a`` and port B's rows ``b`` (in A's layout) differ, with the first
    differences; also port A's derived columns against port B's values."""
    if len(a) != len(b):
        return {"rows": (len(a), len(b))}
    bad = {}
    for col in cols:
        if not same(a[col].to_numpy(), b[col].to_numpy()):
            bad[col] = first_differences(a[col].to_numpy(), b[col].to_numpy())
    for mine, theirs in (("b0", "d_bar"), ("p0", "d_price")):
        if not same(a[mine].to_numpy(), b[theirs].to_numpy()):
            bad[theirs] = first_differences(a[mine].to_numpy(), b[theirs].to_numpy())
    if not same(a["close"].to_numpy(), c[b["t_bar"].to_numpy()]):
        bad["close"] = first_differences(a["close"].to_numpy(), c[b["t_bar"].to_numpy()])
    P = b[[f"p{k}" for k in range(4)]].to_numpy()
    unit = np.where(b["id"].to_numpy() <= 21, np.abs(P[:, 3] - P[:, 0]), np.abs(P[:, 1] - P[:, 2]))
    if not same(a["unit"].to_numpy(), unit):
        bad["unit"] = first_differences(a["unit"].to_numpy(), unit)
    return bad


def b_state(h, l, c, ties="newest", depth=A.DEPTH):
    """Port B's zigzag state after each bar, read from its ``Script``: ``isHi`` / ``isLo`` (its ``ta_highestbars`` /
    ``ta_lowestbars`` on the last ``depth`` values, which is all they read), ``pivP.size()``, the live swing
    (``pivB[0]``, ``pivP[0]``), ``makeQ(0)`` and the bars of those swings while ``pivP.size() >= 11``."""
    sc = B.Script(depth, ties)
    n = len(h)
    st = {"is_hi": np.zeros(n, np.bool_), "is_lo": np.zeros(n, np.bool_), "n_piv": np.zeros(n, np.int64),
          "live_bar": np.full(n, -1, np.int64), "live_price": np.full(n, np.nan),
          "forming_q": np.full((n, A.N_Q), np.nan), "forming_qbar": np.full((n, A.N_Q), -1, np.int64)}
    hh, ll, cc = h.tolist(), l.tolist(), c.tolist()
    d = sc.depth
    for i in range(n):
        w = max(0, i - d + 1)
        st["is_hi"][i] = B.ta_highestbars(hh[w:i + 1], d, ties) == 0
        st["is_lo"][i] = B.ta_lowestbars(ll[w:i + 1], d, ties) == 0
        sc.step(hh[i], ll[i], cc[i])
        k = len(sc.pivP)
        st["n_piv"][i] = k
        if k:
            st["live_bar"][i], st["live_price"][i] = sc.pivB[0], sc.pivP[0]
        if k >= 11:
            st["forming_q"][i] = sc.makeQ(0)
            st["forming_qbar"][i] = [sc.pivB[min(j, k - 1)] for j in range(A.N_Q)]
    return st


def armed_a(r) -> np.ndarray:
    """Port A's HP-CS series: ``armed`` of each chart id on ``forming_q`` (bars x 16)."""
    out = np.zeros((len(r["n_swings"]), len(CHART_IDS)), np.bool_)
    rows = np.flatnonzero(r["n_piv"] >= 11)
    for j, pid in enumerate(CHART_IDS):
        out[rows, j] = np.asarray(A.armed(pid, r["forming_q"][rows]), np.bool_)
    return out


def armed_b(st) -> np.ndarray:
    """The same from port B: its ``check`` on its own ``makeQ(0)`` with a close beyond p2 on the pattern's side (+inf
    for a bullish id, -inf for a bearish one), so that only the breakout conjunct is satisfied by construction."""
    out = np.zeros((len(st["n_piv"]), len(CHART_IDS)), np.bool_)
    for i in np.flatnonzero(st["n_piv"] >= 11):
        q = st["forming_q"][i].tolist()
        for j, pid in enumerate(CHART_IDS):
            out[i, j] = B.check(pid, q, math.inf if B.dirOf(pid) > 0 else -math.inf)
    return out


def armed_keys(armed, qbar) -> dict:
    """Armed chart instances: (id, bars of Q1 .. Q(n-1)) -> the first bar on which the key is armed."""
    seen = {}
    for j, pid in enumerate(CHART_IDS):
        m = int(A.PTS[pid])
        for t in np.flatnonzero(armed[:, j]):
            key = (pid,) + tuple(int(x) for x in qbar[t, 1:m])
            seen.setdefault(key, int(t))
    return seen


def dev_counts(v, dev) -> tuple:
    """The recorded tuple of one port (see ``_RECORDED``) from its own output ``v`` (added, conf, form, drawn of the
    first hits, armed keys)."""
    cf, fm = v.conf, v.form
    cd = dev[cf["t_bar"].to_numpy()]
    fd = dev[fm["t_bar"].to_numpy()]
    first = cf[cf["first_hit"].to_numpy() & cd]
    drawn = v.drawn[cd[cf["first_hit"].to_numpy()]]
    inst = fm[fm["first_bar_of_instance"].to_numpy() & fd]
    ff = fm[fm["first_hit"].to_numpy()]
    fi = (~ff["instance_key"].duplicated(keep="first")).to_numpy() & dev[ff["t_bar"].to_numpy()]
    armed_first = np.array(sorted(v.armed.values()), np.int64)
    return (int(dev.sum()), int((v.added & dev).sum()), int(len(first)), int(cd.sum()),
            int((first["id"] >= 22).sum()), int((first["dir"] == 1).sum()), int(drawn.sum()),
            int(fd.sum()), int(fm.loc[fd, "t_bar"].nunique()), int(len(inst)), int((inst["id"] <= 21).sum()),
            int(fi.sum()), int(dev[armed_first].sum()) if len(armed_first) else 0,
            int(cf["first_hit"].sum()), int(cf["t_bar"].iloc[0]))


def run_both(h, l, c, depth=5, state=True):
    """Both ports on the same bars: port A's dict, port B's dict, port B's rows in A's layout and its drawn mask,
    and (``state``) port B's per-bar zigzag state."""
    ra = A.patterns(h, l, c, depth)
    rb = B.patterns(h, l, c, depth)
    out = NS(a=ra, b=rb, bconf=b_rows_as_a(rb["confirmed"]), bform=b_rows_as_a(rb["forming"]),
             bdrawn=B.drawn_mask(rb["confirmed"]))
    if state:
        out.bst = b_state(h, l, c, depth=depth)
    return out


def differences(x: NS, c) -> dict:
    """Every key on which the two ports differ (empty: identical)."""
    ra, rb = x.a, x.b
    bad = {}
    for col in B.SWING_COLUMNS:
        if not same(ra["swings"][col].to_numpy(), rb["swings"][col].to_numpy()):
            bad[f"swings.{col}"] = first_differences(ra["swings"][col].to_numpy(), rb["swings"][col].to_numpy())
    for k in ("n_swings", "added"):
        if not same(ra[k], rb[k]):
            bad[k] = first_differences(ra[k], rb[k])
    if hasattr(x, "bst"):
        for k in STATE_KEYS:
            if not same(ra[k], x.bst[k]):
                bad[k] = first_differences(np.ravel(ra[k]), np.ravel(x.bst[k]))
    for key, cols, theirs in (("confirmed", CONF_COMMON, x.bconf), ("forming", FORM_COMMON, x.bform)):
        d = rows_differ(ra[key], theirs, cols, c)
        if d:
            bad[key] = d
    fh = ra["confirmed"]["first_hit"].to_numpy()
    if not same(ra["confirmed"]["drawn"].to_numpy()[fh], x.bdrawn) or ra["confirmed"]["drawn"].to_numpy()[~fh].any():
        bad["drawn"] = first_differences(ra["confirmed"]["drawn"].to_numpy()[fh], x.bdrawn)
    return bad


# ───────────────────────────── 1. the real bars (to 2024-06-30, the guards closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Per symbol and timeframe: the bars (open and close times, high, low, close, the Development decision mask),
    both ports' outputs and port B's zigzag state from the study's data start, HP-CS's series of both ports, and for
    gold both ports again from study 1's start. The M1 bars are released as soon as the bars are built (one symbol's
    M1 bars in memory at a time); both symbols' results stay cached, and the whole file peaks at about 1.5 GB."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol in cache:
            return cache[symbol]
        start = TM2.data_start(symbol)
        months = store.available_months(symbol)
        if (2024, 6) not in months or (int(start[:4]), int(start[5:7])) not in months:
            pytest.skip(f"the tick store of {symbol} is not on this machine")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(TM, "STUDY_DIR", closed)
            mp.setattr(TM2, "STUDY_DIR", closed)
            mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
            m = X.load_market(symbol, earliest=start, end="2024-07-01")
            mk = TM.TMarket(symbol, {"t": m.t, "o": m.o, "h": m.h, "l": m.l, "c": m.c, "spread_mean": m.sp,
                                     "n": m.n}, TM.CUT_S)
            del m
            assert int(mk.t[-1]) + 60 <= TM.CUT_S                      # nothing from the hold-out is in memory
            m1_first = int(mk.t[0])
            iz = int(np.searchsorted(mk.t, TM.s_of(DEV[1]), side="left"))   # the harness's window end (_window_ix)
            out = {}
            for tf in TFS:
                b = mk.tbars(tf)
                dev = (b.tc > TM.s_of(DEV[0])) & (b.ex < iz)            # tradeiq_market.run's decision bars
                out[tf] = NS(t=b.t.copy(), tc=b.tc.copy(), h=b.h.copy(), l=b.l.copy(), c=b.c.copy(),
                             complete=b.complete.copy(), dev=dev)
            del mk
        for tf, b in out.items():
            b.x = run_both(b.h, b.l, b.c)
            b.armed_a, b.armed_b = armed_a(b.x.a), armed_b(b.x.bst)
            if symbol == "XAUUSDm":                                      # study 1's start: a suffix of the bars
                k = int(np.searchsorted(b.t, TM.s_of(STUDY1_GOLD_START)))
                b.k1 = k
                b.x1 = run_both(b.h[k:], b.l[k:], b.c[k:], state=False)
        cache[symbol] = NS(start=start, m1_first=m1_first, bars=out)
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_the_hold_out_is_never_read(symbol, real):
    data = real(symbol)
    assert data.start == ("2016-01-01" if symbol == "XAUUSDm" else "2018-01-01")
    for tf, b in data.bars.items():
        assert int(b.tc[-1]) <= TM.CUT_S and int(b.t[0]) >= data.m1_first - 86400, tf
        assert b.complete.all() and len(b.c) > 2000, tf
        assert np.isfinite(b.h).all() and np.isfinite(b.l).all() and np.isfinite(b.c).all(), tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_swings_and_zigzag_state_bit_for_bit(symbol, real):
    for tf, b in real(symbol).bars.items():
        ra, rb, st = b.x.a, b.x.b, b.x.bst
        for col in B.SWING_COLUMNS:
            assert same(ra["swings"][col].to_numpy(), rb["swings"][col].to_numpy()), (symbol, tf, col)
        for k in ("n_swings", "added"):
            assert same(ra[k], rb[k]), (symbol, tf, k, first_differences(ra[k], rb[k]))
        for k in STATE_KEYS:
            assert same(ra[k], st[k]), (symbol, tf, k, first_differences(np.ravel(ra[k]), np.ravel(st[k])))
        # the contract's own consistency: n_swings counts the swings, the live swing is the last one
        assert ra["n_swings"][-1] == len(ra["swings"]) and ra["live_bar"][-1] == ra["swings"]["bar"].iloc[-1]
        assert np.array_equal(ra["n_piv"], np.minimum(ra["n_swings"], A.MAX_SWINGS))
        assert len(ra["swings"]) > 250, (symbol, tf)


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_confirmed_tables_identical(symbol, real):
    for tf, b in real(symbol).bars.items():
        a, theirs = b.x.a["confirmed"], b.x.bconf
        assert not rows_differ(a, theirs, CONF_COMMON, b.c), (symbol, tf, rows_differ(a, theirs, CONF_COMMON, b.c))
        fh = a["first_hit"].to_numpy()
        assert same(a["drawn"].to_numpy()[fh], b.x.bdrawn) and not a["drawn"].to_numpy()[~fh].any(), (symbol, tf)
        # the detection bar is the bar where the next swing is added, with at least 12 swings (L780)
        assert b.x.a["added"][a["t_bar"].to_numpy()].all() and (b.x.a["n_swings"][a["t_bar"].to_numpy()] >= 12).all()
        assert (a["b0"] < a["t_bar"]).all() and len(a) > 50, (symbol, tf)


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_forming_tables_identical(symbol, real):
    for tf, b in real(symbol).bars.items():
        a, theirs = b.x.a["forming"], b.x.bform
        assert not rows_differ(a, theirs, FORM_COMMON, b.c), (symbol, tf, rows_differ(a, theirs, FORM_COMMON, b.c))
        # forming rows read the close of their own bar and the live swing (L807-808)
        assert same(a["c0"].to_numpy(), b.c[a["t_bar"].to_numpy()])
        assert same(a["b0"].to_numpy(), b.x.a["live_bar"][a["t_bar"].to_numpy()])
        assert (b.x.a["n_swings"][a["t_bar"].to_numpy()] >= 11).all() and len(a) > 500, (symbol, tf)


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_hp_cs_armed_series_identical(symbol, real):
    """HP-CS reads "every condition except the breakout close" of each chart id on the forming state."""
    for tf, b in real(symbol).bars.items():
        assert np.array_equal(b.armed_a, b.armed_b), (symbol, tf, int((b.armed_a != b.armed_b).sum()))
        assert b.armed_a.any(axis=0).sum() >= 8, (symbol, tf)               # most chart ids are armed some time
        # a forming chart hit is armed on the same bar (the breakout close is the only conjunct left out)
        fm = b.x.a["forming"]
        ch = fm[fm["id"] >= 22]
        assert b.armed_a[ch["t_bar"].to_numpy(), ch["id"].to_numpy() - 22].all(), (symbol, tf)
        # it reads only the fixed swings Q1..Q8, so it can change only on a bar where a swing is added
        moved = np.flatnonzero((b.armed_a[1:] != b.armed_a[:-1]).any(axis=1)) + 1
        assert len(moved) >= 30 and b.x.a["added"][moved].all(), (symbol, tf)      # gold 1D: 40 changes


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_recorded_development_counts(symbol, real):
    """2019-2022 counts recorded at the reconciliation: a guard against either port changing (counts, no P/L)."""
    for tf, b in real(symbol).bars.items():
        va = NS(added=b.x.a["added"], conf=b.x.a["confirmed"], form=b.x.a["forming"],
                drawn=b.x.a["confirmed"]["drawn"].to_numpy()[b.x.a["confirmed"]["first_hit"].to_numpy()],
                armed=armed_keys(b.armed_a, b.x.a["forming_qbar"]))
        vb = NS(added=b.x.b["added"], conf=b.x.bconf, form=b.x.bform, drawn=b.x.bdrawn,
                armed=armed_keys(b.armed_b, b.x.bst["forming_qbar"]))
        want = _RECORDED[(symbol, tf)]
        assert dev_counts(va, b.dev) == want, (symbol, tf, dev_counts(va, b.dev))
        assert dev_counts(vb, b.dev) == want, (symbol, tf, dev_counts(vb, b.dev))


def test_real_bars_gold_from_2016_or_2017_gives_the_same_development_events(real):
    """The zigzag depends on where the bars start. On gold, the study's bars (from 2016-01-03) and study 1's (from
    2017-01-03, a suffix) give the same swings, confirmed and forming rows (every column, the instance keys and the
    drawn flags included) on every Development bar, in both ports."""
    for tf, b in real("XAUUSDm").bars.items():
        k = b.k1
        assert int(b.t[k]) >= TM.s_of(STUDY1_GOLD_START) and int(b.t[k - 1]) < TM.s_of(STUDY1_GOLD_START)
        assert not b.dev[:k].any()
        x, y = b.x, b.x1
        assert not differences(y, b.c[k:]), (tf, differences(y, b.c[k:]))     # the two ports agree on the suffix
        for key in ("confirmed", "forming"):
            full = x.a[key][b.dev[x.a[key]["t_bar"].to_numpy()]].reset_index(drop=True)
            late = y.a[key][b.dev[k:][y.a[key]["t_bar"].to_numpy()]].reset_index(drop=True)
            late["t_bar"] += k
            for col in POINTS[NP:]:
                late[col] = np.where(late[col] >= 0, late[col] + k, -1)
            if key == "forming":
                late["instance_key"] = [(kk[0],) + tuple(v + k for v in kk[1:]) for kk in late["instance_key"]]
            assert len(full) == len(late) > 0, (tf, key)
            for col in full.columns:
                assert same(full[col].to_numpy(), late[col].to_numpy()), (tf, key, col)
        a = x.a["added"][k:][b.dev[k:]]
        assert np.array_equal(a, y.a["added"][b.dev[k:]]), tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_the_oldest_tie_reading_agrees_and_its_effect_is_recorded(symbol, real):
    """``ta.highestbars`` / ``ta.lowestbars`` ties (L541-542) are not documented. Both ports implement the alternative
    (an equal earlier value wins, so the current bar is not the extreme) for measurement only: port A in ``zigzag``,
    port B in ``Script`` / ``patterns(_ties=...)``. Under it the two zigzags agree too; its effect on Development is
    recorded in ``_TIES_RECORDED``."""
    for tf, b in real(symbol).bars.items():
        za = A.zigzag(b.h, b.l, b.c, tie="oldest")
        rbo = B.patterns(b.h, b.l, b.c, _ties="oldest")
        sto = b_state(b.h, b.l, b.c, ties="oldest")
        for mine, theirs in (("sw_bar", "bar"), ("sw_price", "price"), ("sw_close", "close_at_set"),
                             ("sw_is_high", "is_high")):
            assert same(za[mine], rbo["swings"][theirs].to_numpy()), (symbol, tf, mine)
        for k in ("is_hi", "is_lo", "n_piv", "live_bar", "live_price"):
            assert same(za[k], sto[k]), (symbol, tf, k)
        assert same(za["added"], rbo["added"]) and same(za["n_swings"], rbo["n_swings"]), (symbol, tf)
        # the effect, over the Development decision bars
        dev, ra = b.dev, b.x.a
        bits = int((((ra["is_hi"] != za["is_hi"]) | (ra["is_lo"] != za["is_lo"])) & dev).sum())
        sw = len(set(np.flatnonzero(ra["added"] & dev)) ^ set(np.flatnonzero(za["added"] & dev)))
        cn, co = ra["confirmed"], rbo["confirmed"]
        kn = set(map(tuple, cn.loc[cn["first_hit"].to_numpy() & dev[cn["t_bar"].to_numpy()], ["t_bar", "id"]]
                     .to_numpy().tolist()))
        ko = set(map(tuple, co.loc[co["first_hit"].to_numpy() & dev[co["t_bar"].to_numpy()], ["t_bar", "id"]]
                     .to_numpy().tolist()))
        fn, fo = ra["forming"], rbo["forming"]
        jn = set(fn.loc[fn["first_bar_of_instance"].to_numpy() & dev[fn["t_bar"].to_numpy()], "instance_key"])
        jo = set(fo.loc[fo["first_bar_of_instance"].to_numpy() & dev[fo["t_bar"].to_numpy()], "instance_key"])
        got = (bits, sw, len(kn ^ ko), len(jn ^ jo))
        assert got == _TIES_RECORDED[(symbol, tf)], (symbol, tf, got)


# ───────────────────────────── 2. synthetic bars ─────────────────────────────

def walk(n, seed, decimals=None, outside=0.0, flat=0.0):
    """A random walk of closes with wicks; ``decimals`` rounds the prices (ties between highs and lows),
    ``outside`` widens a share of the bars on both sides (outside bars), ``flat`` repeats the previous bar's high
    and low on a share of the bars (exact ties inside the 5-bar window)."""
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = np.r_[c[:1], c[:-1]]
    w = np.abs(rng.normal(0, 0.6, n))
    h = np.maximum(o, c) + w * rng.random(n)
    l = np.minimum(o, c) - w * rng.random(n)
    if outside:
        k = rng.random(n) < outside
        h[k] += 3 * rng.random(int(k.sum()))
        l[k] -= 3 * rng.random(int(k.sum()))
    if flat:
        k = rng.random(n) < flat
        h[k] = np.r_[h[:1], h[:-1]][k]
        l[k] = np.r_[l[:1], l[:-1]][k]
    if decimals is not None:
        h, l, c = np.round(h, decimals), np.round(l, decimals), np.round(c, decimals)
        h = np.maximum(h, np.maximum(l, c))
        l = np.minimum(l, np.minimum(h, c))
    return h, l, c


SYNTH = [  # (seed, n, depth, decimals, outside share, flat share)
    (1, 1500, 5, None, 0.0, 0.0), (2, 1500, 5, 1, 0.0, 0.0), (3, 1500, 5, 0, 0.0, 0.0),
    (4, 1500, 5, None, 0.2, 0.0), (5, 1500, 5, 1, 0.0, 0.3), (6, 1200, 2, 1, 0.1, 0.1),
    (7, 1200, 3, None, 0.0, 0.0), (8, 1500, 9, 0, 0.1, 0.2), (9, 2500, 21, 1, 0.0, 0.0),
    (10, 2500, 50, None, 0.2, 0.0),
]


@pytest.mark.parametrize("seed,n,depth,decimals,outside,flat", SYNTH)
def test_synthetic_bars_bit_for_bit(seed, n, depth, decimals, outside, flat):
    h, l, c = walk(n, seed, decimals, outside, flat)
    x = run_both(h, l, c, depth)
    assert not differences(x, c), differences(x, c)
    assert np.array_equal(armed_a(x.a), armed_b(x.bst))
    if depth <= 9:                             # the case is not empty
        assert len(x.a["confirmed"]) > 0 and len(x.a["forming"]) > 0


@pytest.mark.parametrize("n", [0, 1, 4, 5, 6, 11, 12, 13, 30, 100])
@pytest.mark.parametrize("shape", ["flat", "rise", "drift_down", "saw"])
def test_short_and_degenerate_series(n, shape):
    """Fewer bars than the window or the gates, constant prices (every bar ties, so a swing on every bar), a straight
    rise (one swing high that keeps moving), a slow fall and a regular saw (zigzag legs of 7 bars)."""
    x = np.arange(n, dtype=np.float64)
    if shape == "flat":
        h, l, c = np.full(n, 10.0), np.full(n, 9.0), np.full(n, 9.5)
    elif shape == "rise":
        h, l, c = 10 + x, 9 + x, 9.5 + x
    elif shape == "drift_down":
        h, l, c = 10 - 0.01 * x, 9 - 0.01 * x, 9.5 - 0.01 * x
    else:
        s = np.where(x % 14 < 7, x % 7, 7 - x % 7)
        h, l, c = 10 + s, 9 + s, 9.5 + s
    xs = run_both(h, l, c)
    assert not differences(xs, c), differences(xs, c)


# ───────────────────────────── 3. the tables ─────────────────────────────

def test_the_tables_of_both_ports_are_equal():
    """The names (L96-103), the 144 constants in the source's order (L146-289), the harmonic dispatch of ``check``
    (L484-505), the chart dispatch (L506-521), dirOf / ptsOf (L117-142) and the inputs (L19-41) are the same in both
    ports (each generates its tables from the source text and checks them there)."""
    assert A.NAMES == B.NAMES
    assert list(A.RATIOS.items()) == list(B.RATIOS.items())
    assert {i: A.CALLS[i] for i in range(22)} == B.HARMONIC_CALLS
    assert [A.CALLS[i][0] for i in CHART_IDS] == [B._CHART_FUNCS[i].__name__ for i in CHART_IDS]
    assert [int(A.DIR[i]) for i in range(38)] == [B.dirOf(i) for i in range(38)]
    assert [int(A.PTS[i]) for i in range(38)] == [B.ptsOf(i) for i in range(38)]
    assert list(A.KIND) == [B.kindOf(i) for i in range(38)]
    for k in ("DEPTH", "DEV_PCT", "HIST_MAX", "SL_K", "TP1_K", "TP2_K", "CSL_K", "CTP1_K", "CTP2_K", "PLAN_BARS",
              "MAX_SWINGS", "N_IDS"):
        assert getattr(A, k) == getattr(B, k), k


def _source_lines():
    for p in SOURCE_CANDIDATES:
        if p and Path(p).is_file():
            return B.source_lines(B.read_source(p))
    pytest.skip("the Pine source of the script is not on this machine (set TRADEIQ2_PATTERNS_SOURCE)")


def test_c0_is_read_only_in_the_breakout_conjunct_of_each_chart_predicate():
    """HP-CS needs "every condition except the breakout close" (PREREG 6.7). Both ports get it by satisfying the
    breakout conjunct with a close beyond p2 (``A.armed``: +-inf). That is exact only if ``c0`` appears in each chart
    predicate (L322-480) once, as the last ``and`` conjunct ``c0 < p2`` for a bearish id and ``c0 > p2`` for a
    bullish one; checked here on the source text."""
    lines = _source_lines()
    by_name = {}
    for i, s in enumerate(lines):
        m = re.match(r"^(pc\w+)\(array<float> P, float c0\) =>$", s)
        if m:
            body = []
            j = i + 1
            while j < len(lines) and lines[j].startswith("    "):
                body.append(lines[j].strip())
                j += 1
            by_name[m.group(1)] = body
    cases = {}
    for s in lines:
        m = re.match(r"^\s+(\d+) => (pc\w+)\(P, c0\)$", s)
        if m:
            cases[int(m.group(1))] = m.group(2)
    assert sorted(cases) == list(CHART_IDS) and [cases[i] for i in CHART_IDS] == [A.CALLS[i][0] for i in CHART_IDS]
    for pid in CHART_IDS:
        body = by_name[cases[pid]]
        assert all("c0" not in s for s in body[:-1]), pid
        conj = body[-1].split(" and ")
        assert all(not re.search(r"\bc0\b", s) for s in conj[:-1]), pid
        assert conj[-1] == ("c0 > p2" if A.DIR[pid] > 0 else "c0 < p2"), (pid, conj[-1])
