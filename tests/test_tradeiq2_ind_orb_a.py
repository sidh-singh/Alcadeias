"""
Port A of LuxAlgo's Ultimate Opening Range Breakout (``backtesting/research/tradeiq2_ind_orb.py``).

1. One hand-computed test per trap of the map's porting risks (``orb_session_swing_ha.md`` 1.6, "Risks": nine lines),
   named after it (``test_trap1`` .. ``test_trap9``). Each also runs the wrong reading on the same bars
   (``PineScript``, a plain-Python bar-by-bar transcription of the script's computing lines with one switch per
   misreading) and checks that it answers differently, while the port equals the transcription's script reading.
2. The map's thirteen test cases (1.6, "Tests"), one test each (``test_case01`` .. ``test_case13``).
3. The contract: the keys, the dtypes, the days frame's columns, the refused inputs.
4. The port against the transcription on random bars, bit for bit: gold-like and BTC-like sessions, both daylight-
   saving changes of 2023, data holes, prices on a coarse grid (exact ties), every input of the contract.
5. Truncation invariance: the outputs up to bar T do not change when the bars after T are removed.
6. Real bars (skipped when the tick store is absent): both symbols, M5 and M15 (PREREG 6.5), 2019-01-01 to
   2024-06-30 (the hold-out guard closed): the contract's NaN pattern and structure, the controls of PREREG 6.5, the
   transcription bit for bit, truncation; BTC also with Binance volume (PREREG 2).

No test computes a profit on real bars; the hand-made and random bars are synthetic. Line numbers l.... are those of
the owner's copy of the script.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_orb as ORB
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

NAN = math.nan
DAY = 86400
NYZ = ZoneInfo("America/New_York")
FIXED_UTC5 = timezone(timedelta(hours=-5))
EPOCH = date(1970, 1, 1)
GOLD, BTC = "XAUUSDm", "BTCUSDm"
SYMS = (GOLD, BTC)
TF_MIN = {"M5": 5, "M15": 15}
CUT = TM.s_of("2024-07-01")
BOOL_KEYS = ("in_session", "new_day", "session_ended", "breakout_up", "breakout_dn", "label_up", "label_dn", "hv")
FLOAT_KEYS = ("or_high", "or_low", "atr", "trail")


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' folders as the guards see them: empty tmp folders (no FINALISTS.md: the hold-out is closed)."""
    d1, d2 = tmp_path / "study1", tmp_path / "study2"
    d1.mkdir()
    d2.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d2


# ───────────────────────────── comparisons ─────────────────────────────

def same(a, b) -> bool:
    """Equal floats bit for bit (up to the sign of zero), NaN where the other is NaN, same shape."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def frames_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return False
    for k in a.columns:
        x, y = a[k].to_numpy(), b[k].to_numpy()
        if x.dtype.kind == "f" or y.dtype.kind == "f":
            if not same(x, y):
                return False
        elif not (x.dtype == y.dtype and np.array_equal(x, y)):
            return False
    return True


def outputs_equal(x, y, upto=None) -> bool:
    """Every per-bar key of the contract equal (floats bit for bit, NaN to NaN; bool / int8 exactly), on [0, upto)."""
    for k in ORB.BAR_KEYS:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if upto is not None:
            a, b = a[:upto], b[:upto]
        if k in FLOAT_KEYS:
            if not same(a, b):
                return False
        elif not (a.dtype == b.dtype and np.array_equal(a, b)):
            return False
    return True


def assert_same(port, ref):
    """The port and the transcription agree on every per-bar series and on the days frame."""
    assert outputs_equal(port, ref), first_diff(port, ref)
    assert frames_equal(port["days"], ref["days"]), "days frames differ"


def first_diff(port, ref):
    """For failure messages: the first per-bar key and bar where two outputs differ."""
    for k in ORB.BAR_KEYS:
        a, b = np.asarray(port[k]), np.asarray(ref[k])
        bad = ~((a == b) | (np.isnan(a) & np.isnan(b))) if k in FLOAT_KEYS else (a != b)
        if bad.any():
            return k, int(np.argmax(bad))
    return None


# ───────────────────────────── the transcription (the script, bar by bar) ─────────────────────────────

def _na(x) -> bool:
    return x != x


def _nz(x, y):
    return y if x != x else x


def _pmax(a, b):
    """``math.max``: na if either is na."""
    return NAN if (a != a or b != b) else (a if a > b else b)


def _pmin(a, b):
    return NAN if (a != a or b != b) else (a if a < b else b)


def atr_ref(h, l, c, n=14):
    """``ta.atr(n)`` written out: ``pine_atr``'s true range (high - low on the first bar), the reference ``pine_sma``
    of the first n (added from the newest back), then ``alpha * tr + (1 - alpha) * prev`` with alpha = 1 / n."""
    N = len(h)
    out = [NAN] * N
    tr = []
    for i in range(N):
        if i == 0:
            tr.append(h[0] - l[0])
        else:
            tr.append(max(max(h[i] - l[i], abs(h[i] - c[i - 1])), abs(l[i] - c[i - 1])))
    if N >= n:
        s = 0.0
        for j in range(n):
            s = s + tr[n - 1 - j] / n
        out[n - 1] = s
        alpha, prev = 1.0 / n, s
        for i in range(n, N):
            prev = alpha * tr[i] + (1.0 - alpha) * prev
            out[i] = prev
    return out


def sma_ref(v, n=20, incl=True):
    """``ta.sma(v, n)`` written out (``pine_sma``: ``sum + v[i] / n`` from this bar back); ``incl=False`` is the
    misreading that averages the n bars BEFORE this one."""
    N = len(v)
    out = [NAN] * N
    for i in range(N):
        top = i if incl else i - 1
        if top - n + 1 < 0:
            continue
        s = 0.0
        for j in range(n):
            s = s + v[top - j] / n
        out[i] = s
    return out


class PineScript:
    """
    A plain-Python transcription of the script's computing lines (l.84-88, 147-286), one bar at a time, written for
    these tests independently of the port's kernel: the clocks with Python's zoneinfo, ``ta.atr`` and ``ta.sma``
    written out, the sessions and the trades kept as dicts. The defaults are the script; each switch is one
    misreading of a trap:

    session_by   'open' (the bar's open lies in the session, l.87) | 'overlap' (the bar overlaps it) | 'inside' (the
                 whole bar lies in it)
    cross        'pine' (close > orHigh and close[1] <= orHigh[1], l.243) | 'level' (close > orHigh alone) |
                 'runtime' (TradingView's recorded runtime: the previous pair is that of the last bar where both
                 values were non-na; an alternative reading, not a misreading)
    per_side     True (canSignalUp / canSignalDn, l.125-126) | False (one label per day for both sides)
    block        True (no entry while a trade is open, l.255 / 266) | False (an opposite label reverses the trade)
    trail_seed   'nz' (math.max(nz(trailStop[1], x), x), l.275) | 'none' (without nz) | 'stale' (trailStop never set
                 back to na, l.250 / 279 / 286 skipped) | 'current' (the variable's current value instead of
                 trailStop[1], i.e. the just-assigned entry level on an entry bar: an alternative reading)
    reset_first  True (the daily gates l.246 before the exits l.274) | False (the exits first)
    bear_first   True (the label branches l.252-272 before the exits) | False (the exits first)
    entry_at     'range' (entryPrice := orHigh / orLow, l.257 / 268) | 'close' (the label bar's close)
    hv_incl      True (ta.sma(volume, 20) with the current bar) | False (the 20 bars before it)

    ``day_boundary`` of ``run``: 'ny17', 'utc0', 'clock0' as in the port, or 'none' (no isNewDay at all).
    """

    def __init__(self, session_by="open", cross="pine", per_side=True, block=True, trail_seed="nz",
                 reset_first=True, bear_first=True, entry_at="range", hv_incl=True):
        self.session_by, self.cross, self.per_side, self.block = session_by, cross, per_side, block
        self.trail_seed, self.reset_first, self.bear_first = trail_seed, reset_first, bear_first
        self.entry_at, self.hv_incl = entry_at, hv_incl

    def clocks(self, t, tf_min, sess, window_end, clock, days, day_boundary):
        s0, s1 = sess
        zone = NYZ if clock == "ny" else FIXED_UTC5
        ins, disp, key, wday = [], [], [], []
        for ts in t:
            w = datetime.fromtimestamp(ts, zone)
            m = w.hour * 60 + w.minute
            ok = days == "all" or w.weekday() < 5
            if self.session_by == "open":
                s_in = s0 <= m < s1
            elif self.session_by == "overlap":
                s_in = m < s1 and m + tf_min > s0
            else:
                s_in = m >= s0 and m + tf_min <= s1
            ins.append(ok and s_in)
            disp.append(ok and s0 <= m < window_end)
            wday.append((w.date() - EPOCH).days)
            if day_boundary == "ny17":
                key.append((datetime.fromtimestamp(ts, NYZ) + timedelta(hours=7)).date())
            elif day_boundary == "utc0":
                key.append(datetime.fromtimestamp(ts, timezone.utc).date())
            elif day_boundary == "clock0":
                key.append(w.date())
            elif day_boundary == "none":
                key.append(0)
            else:
                raise ValueError(day_boundary)
        nd = [False] + [key[i] != key[i - 1] for i in range(1, len(key))]
        return ins, disp, nd, wday

    def run(self, t, o, h, l, c, v, tf_min, sess=(570, 600), window_end=1020, clock="ny", days="weekdays",
            trail_mult=2.0, multiples=(1.0, 2.0, 3.0), day_boundary="ny17"):
        t = [int(x) for x in t]
        h, l, c = [float(x) for x in h], [float(x) for x in l], [float(x) for x in c]
        n = len(t)
        ins, disp, nd, wday = self.clocks(t, tf_min, sess, window_end, clock, days, day_boundary)
        atr = atr_ref(h, l, c, 14)
        if v is None:
            hv = [False] * n
        else:
            v = [float(x) for x in v]
            vs = sma_ref(v, 20, self.hv_incl)
            hv = [v[i] > vs[i] for i in range(n)]
        mults = [float(m) for m in multiples]
        tm = float(trail_mult)

        S = SimpleNamespace(orH=NAN, orL=NAN, ended=False, reached=[False] * 6, canU=True, canD=True, canA=True,
                            aDir=0, trail=NAN, trail1=NAN, entry=NAN, open=None, cur=None)
        sessions, trades = [], []
        res = {k: [] for k in ("or_high", "or_low", "session_ended", "breakout_up", "breakout_dn", "label_up",
                               "label_dn", "active_dir", "trail")}
        orH1 = orL1 = NAN
        inS1 = False
        last_up = last_dn = None              # 'runtime': (close, level) of the last bar where both were non-na

        for i in range(n):
            inS, newD = ins[i], nd[i]
            # l.147-164 (a reset ends the span of a session that ended on an earlier bar)
            if newD or (inS and not inS1):
                if S.cur is not None and S.cur["post"] >= 0 and S.cur["span_end"] is None:
                    S.cur["span_end"] = i
                S.orH = S.orL = NAN
                S.ended = False
                S.reached = [False] * 6
                S.entry = NAN
                if inS:
                    S.cur = {"start": i, "end": -1, "post": -1, "span_end": None, "orh": NAN, "orl": NAN,
                             "hits": [-1] * 6, "fb": -1, "fbs": 0, "lu": -1, "ld": -1, "day": wday[i]}
                    sessions.append(S.cur)
            # l.166-171
            if inS:
                S.orH = h[i] if _na(S.orH) else _pmax(S.orH, h[i])
                S.orL = l[i] if _na(S.orL) else _pmin(S.orL, l[i])
                S.cur["end"], S.cur["orh"], S.cur["orl"] = i, S.orH, S.orL
            # l.181-183: the session counts with the range the script holds now (na if this bar's reset wiped it)
            if not inS and inS1:
                S.ended = True
                S.cur["post"] = i
                S.cur["orh"], S.cur["orl"] = S.orH, S.orL
            # l.185-214
            rng = S.orH - S.orL
            U = [S.orH + rng * f for f in mults]
            D = [S.orL - rng * f for f in mults]
            if S.ended:
                for k in range(3):
                    if not _na(U[k]) and h[i] >= U[k] and not S.reached[k]:
                        S.reached[k] = True
                        S.cur["hits"][k] = i
                for k in range(3):
                    if not _na(D[k]) and l[i] <= D[k] and not S.reached[3 + k]:
                        S.reached[3 + k] = True
                        S.cur["hits"][3 + k] = i
            # l.243-244
            if self.cross == "pine":
                xu = i > 0 and c[i] > S.orH and c[i - 1] <= orH1
                xd = i > 0 and c[i] < S.orL and c[i - 1] >= orL1
            elif self.cross == "runtime":
                xu = last_up is not None and c[i] > S.orH and last_up[0] <= last_up[1]
                xd = last_dn is not None and c[i] < S.orL and last_dn[0] >= last_dn[1]
                if not _na(S.orH):
                    last_up = (c[i], S.orH)
                if not _na(S.orL):
                    last_dn = (c[i], S.orL)
            else:
                xu, xd = c[i] > S.orH, c[i] < S.orL
            bu = xu and not inS and S.ended
            bd = xd and not inS and S.ended
            if (bu or bd) and S.cur["fb"] < 0:
                S.cur["fb"], S.cur["fbs"] = i, (1 if bu else -1)
            lu = ld = False

            def gates():
                if newD or inS:
                    S.canU = S.canD = S.canA = True
                    if S.aDir != 0:
                        S.open.update(exit_bar=i, reason="reset")
                        S.open = None
                    S.aDir = 0
                    if self.trail_seed != "stale":
                        S.trail = NAN

            def can(side):
                return (S.canU if side == 1 else S.canD) if self.per_side else S.canA

            def use(side):
                if not self.per_side:
                    S.canA = False
                elif side == 1:
                    S.canU = False
                else:
                    S.canD = False

            def close(price, why):
                S.open.update(exit_bar=i, exit_price=price, reason=why)
                S.open = None
                S.aDir = 0

            def open_(side):
                S.aDir = side
                S.entry = (S.orH if side == 1 else S.orL) if self.entry_at == "range" else c[i]
                S.trail = l[i] - (atr[i] * tm) if side == 1 else h[i] + (atr[i] * tm)
                S.open = {"sess": S.cur, "side": side, "entry_bar": i, "entry_price": S.entry, "exit_bar": -1,
                          "exit_price": NAN, "reason": "open"}
                trades.append(S.open)

            def label(side):
                nonlocal lu, ld
                fired = bu if side == 1 else bd
                if fired and can(side) and disp[i]:
                    if side == 1:
                        lu = True
                        S.cur["lu"] = i
                    else:
                        ld = True
                        S.cur["ld"] = i
                    use(side)
                    if S.aDir == 0:
                        open_(side)
                    elif not self.block and S.aDir == -side:
                        close(c[i], "reverse")
                        open_(side)

            def trail_exit(side):
                if S.aDir != side:
                    return
                x = l[i] - (atr[i] * tm) if side == 1 else h[i] + (atr[i] * tm)
                prev = {"none": S.trail1, "current": _nz(S.trail, x)}.get(self.trail_seed, _nz(S.trail1, x))
                S.trail = _pmax(prev, x) if side == 1 else _pmin(prev, x)
                hit = (c[i] < S.trail) if side == 1 else (c[i] > S.trail)
                if hit or not disp[i]:
                    close(c[i], "trail" if hit else "window")
                    if self.trail_seed != "stale":
                        S.trail = NAN

            steps = [gates, lambda: label(1), lambda: label(-1), lambda: trail_exit(1), lambda: trail_exit(-1)]
            if not self.bear_first:
                steps = [gates, lambda: trail_exit(1), lambda: trail_exit(-1), lambda: label(1), lambda: label(-1)]
            if not self.reset_first:
                steps = steps[1:] + [gates]
            for step in steps:
                step()

            res["or_high"].append(S.orH if S.ended else NAN)
            res["or_low"].append(S.orL if S.ended else NAN)
            res["session_ended"].append(S.ended)
            res["breakout_up"].append(bu)
            res["breakout_dn"].append(bd)
            res["label_up"].append(lu)
            res["label_dn"].append(ld)
            res["active_dir"].append(S.aDir)
            res["trail"].append(S.trail)
            orH1, orL1, S.trail1, inS1 = S.orH, S.orL, S.trail, inS

        out = {"in_session": np.asarray(ins, np.bool_), "new_day": np.asarray(nd, np.bool_),
               "or_high": np.asarray(res["or_high"], np.float64), "or_low": np.asarray(res["or_low"], np.float64),
               "session_ended": np.asarray(res["session_ended"], np.bool_),
               "breakout_up": np.asarray(res["breakout_up"], np.bool_),
               "breakout_dn": np.asarray(res["breakout_dn"], np.bool_),
               "label_up": np.asarray(res["label_up"], np.bool_), "label_dn": np.asarray(res["label_dn"], np.bool_),
               "hv": np.asarray(hv, np.bool_), "atr": np.asarray(atr, np.float64),
               "active_dir": np.asarray(res["active_dir"], np.int8), "trail": np.asarray(res["trail"], np.float64)}
        out["days"] = self.frame(sessions, trades, mults, n)
        out["trades"] = trades
        return out

    @staticmethod
    def frame(sessions, trades, mults, n) -> pd.DataFrame:
        rows = []
        for s in sessions:
            if s["post"] < 0:                     # never counted by the script (l.181): not a row
                continue
            orh, orl = s["orh"], s["orl"]
            w = orh - orl
            r = {"day": s["day"], "start_bar": s["start"], "end_bar": s["end"], "post_bar": s["post"],
                 "span_end": n if s["span_end"] is None else s["span_end"],
                 "or_high": orh, "or_low": orl, "width": w}
            for k in range(3):
                r[f"u{k + 1}"] = orh + w * mults[k]
            for k in range(3):
                r[f"d{k + 1}"] = orl - w * mults[k]
            r.update(first_breakout_side=s["fbs"], first_breakout_bar=s["fb"], label_up_bar=s["lu"],
                     label_dn_bar=s["ld"])
            names = ("u1", "u2", "u3", "d1", "d2", "d3")
            for k, nm in enumerate(names):
                r[f"hit_{nm}"] = s["hits"][k] >= 0
            for k, nm in enumerate(names):
                r[f"hit_{nm}_bar"] = s["hits"][k]
            mine = [tr for tr in trades if tr["sess"] is s]
            assert len(mine) <= 2
            for pre in (("trade_side", "entry_bar", "entry_price", "exit_bar", "exit_price", "exit_reason"),
                        ("trade2_side", "entry2_bar", "entry2_price", "exit2_bar", "exit2_price", "exit2_reason")):
                tr = mine.pop(0) if mine else None
                if tr is None:
                    r.update({pre[0]: 0, pre[1]: -1, pre[2]: NAN, pre[3]: -1, pre[4]: NAN, pre[5]: ""})
                else:
                    r.update({pre[0]: tr["side"], pre[1]: tr["entry_bar"], pre[2]: tr["entry_price"],
                              pre[3]: tr["exit_bar"], pre[4]: tr["exit_price"], pre[5]: tr["reason"]})
            rows.append(r)
        df = pd.DataFrame(rows, columns=list(ORB.DAY_COLUMNS))
        ints = [k for k in ORB.DAY_COLUMNS if k in ("day", "start_bar", "end_bar", "post_bar", "span_end",
                                                    "first_breakout_side", "first_breakout_bar", "label_up_bar",
                                                    "label_dn_bar", "trade_side", "entry_bar", "exit_bar",
                                                    "trade2_side", "entry2_bar", "exit2_bar") or k.endswith("_bar")]
        for k in ints:
            df[k] = df[k].astype(np.int64)
        for k in [f"hit_{nm}" for nm in ("u1", "u2", "u3", "d1", "d2", "d3")]:
            df[k] = df[k].astype(np.bool_)
        for k in ("or_high", "or_low", "width", "u1", "u2", "u3", "d1", "d2", "d3", "entry_price", "exit_price",
                  "entry2_price", "exit2_price"):
            df[k] = df[k].astype(np.float64)
        for k in ("exit_reason", "exit2_reason"):
            df[k] = df[k].astype(object)
        return df


# ───────────────────────────── hand-made bars (New York wall clock) ─────────────────────────────

def ny_ts(day: str, hhmm: str) -> int:
    """UTC epoch seconds of New York wall-clock ``hhmm`` on ``day`` (daylight saving included; "24:00" = the next
    day's 00:00)."""
    d = date.fromisoformat(day)
    hh, mm = (int(x) for x in hhmm.split(":"))
    if hh == 24:
        d, hh = d + timedelta(days=1), 0
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NYZ).timestamp())


class Chart:
    """Chart bars of ``tf`` minutes on New York wall-clock times: flat stretches (o = c = p, h = p + 0.5,
    l = p - 0.5, so every true range is 1.0 and the ATR settles at 1), single bars set by hand, and walks."""

    def __init__(self, tf=5):
        self.tf = tf
        self.rows = {}

    def flat(self, day, start, end, p=100.0, half=0.5, v=100.0):
        for ts in range(ny_ts(day, start), ny_ts(day, end), 60 * self.tf):
            self.rows[ts] = [p, p + half, p - half, p, v]
        return self

    def bar(self, day, hhmm, o, h, l, c, v=None):
        ts = ny_ts(day, hhmm)
        assert ts in self.rows, (day, hhmm)
        self.rows[ts][:4] = [float(o), float(h), float(l), float(c)]
        if v is not None:
            self.rows[ts][4] = float(v)
        return self

    def hold(self, day, start, end, p, half=0.5):
        """Bars at the flat level p from ``start`` to ``end`` (exclusive): o = c = p."""
        for ts in range(ny_ts(day, start), ny_ts(day, end), 60 * self.tf):
            assert ts in self.rows
            self.rows[ts][:4] = [p, p + half, p - half, p]
        return self

    def walk(self, day, start, closes, wick=0.25):
        """Consecutive bars from ``start``: o = the previous bar's close, c as given, h / l = max / min(o, c) +- wick."""
        keys = sorted(self.rows)
        j = keys.index(ny_ts(day, start))
        for k, cl in enumerate(closes):
            o = self.rows[keys[j + k - 1]][3]
            self.rows[keys[j + k]][:4] = [o, max(o, cl) + wick, min(o, cl) - wick, float(cl)]
        return self

    def ix(self, day, hhmm) -> int:
        return sorted(self.rows).index(ny_ts(day, hhmm))

    def arrays(self):
        keys = sorted(self.rows)
        a = np.asarray([self.rows[k] for k in keys], np.float64)
        return np.asarray(keys, np.int64), a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]


def run(ch, **kw):
    kw = {"symbol": GOLD, **kw}
    return ORB.orb(*ch.arrays(), ch.tf, **kw)


def pine(ch, day_boundary="ny17", **switches):
    def go(**kw):
        return PineScript(**switches).run(*ch.arrays(), ch.tf, day_boundary=day_boundary, **kw)
    return go


D0 = "2023-03-15"        # a Wednesday, New York on daylight saving (09:30 = 13:30 UTC)
D1 = "2023-03-16"


def base_day(day=D0, ch=None, end="17:00"):
    """M5 bars 08:00-16:55 New York, flat at 100; the session's range is [99, 101] (09:40 high 101, 09:50 low 99):
    width 2, u1..u3 = 103, 105, 107, d1..d3 = 97, 95, 93."""
    ch = ch or Chart(5)
    ch.flat(day, "08:00", end)
    ch.bar(day, "09:40", 100, 101.0, 99.5, 100)
    ch.bar(day, "09:50", 100, 100.5, 99.0, 100)
    return ch


def bull_at_10(ch, day=D0):
    """The 10:00 bar closes above the range: o 100, h 101.6, l 99.9, c 101.5 (the long's entry bar)."""
    return ch.bar(day, "10:00", 100, 101.6, 99.9, 101.5)


def row(out, k=0):
    return out["days"].iloc[k]


# ───────────────────────────── 1. the traps of the map's 1.6, one test each ─────────────────────────────

def test_trap1_the_session_is_defined_by_bar_open_times():
    """l.87: ``time(timeframe.period, session)`` is na unless the bar OPENS inside the session. M15: the 09:15 bar
    (high 105, it closes at 09:30) and the 10:00 bar (high 106) are outside; the range is 09:30 + 09:45 = [99, 101].
    1H: no bar opens in 09:30-10:00, so no range ever forms (the 'overlap' reading would take the 09:00 bar). COMEX
    08:20-08:50 on M15: the 08:30 and 08:45 bars (08:30-09:00), not 08:15 ('overlap': 08:15-09:00; 'inside': 08:30
    only); on M5 08:20 .. 08:45."""
    ch = Chart(15).flat(D0, "08:00", "17:00")
    ch.bar(D0, "09:15", 100, 105.0, 99.5, 100).bar(D0, "09:30", 100, 101.0, 99.5, 100)
    ch.bar(D0, "09:45", 100, 100.5, 99.0, 100).bar(D0, "10:00", 100, 106.0, 99.5, 100.2)
    out = run(ch)
    assert np.flatnonzero(out["in_session"]).tolist() == [ch.ix(D0, "09:30"), ch.ix(D0, "09:45")]
    r = row(out)
    assert (r.start_bar, r.end_bar, r.post_bar) == (ch.ix(D0, "09:30"), ch.ix(D0, "09:45"), ch.ix(D0, "10:00"))
    assert (r.or_high, r.or_low) == (101.0, 99.0) and out["or_high"][ch.ix(D0, "10:00")] == 101.0
    assert_same(out, pine(ch)())
    # 1H: no session at all; the overlap reading would build a range from the 09:00 bar
    h1 = Chart(60).flat(D0, "08:00", "17:00").bar(D0, "09:00", 100, 102.0, 99.0, 100)
    o1 = run(h1)
    assert not o1["in_session"].any() and len(o1["days"]) == 0 and not o1["session_ended"].any()
    assert_same(o1, pine(h1)())
    ov = pine(h1, session_by="overlap")()
    assert np.flatnonzero(ov["in_session"]).tolist() == [h1.ix(D0, "09:00")] and ov["days"].or_high[0] == 102.0
    # COMEX on M15 and M5
    cx = run(ch, sess=ORB.COMEX_SESSION)
    assert np.flatnonzero(cx["in_session"]).tolist() == [ch.ix(D0, "08:30"), ch.ix(D0, "08:45")]
    assert np.flatnonzero(pine(ch, session_by="overlap")(sess=(500, 530))["in_session"]).tolist() == [
        ch.ix(D0, "08:15"), ch.ix(D0, "08:30"), ch.ix(D0, "08:45")]
    assert np.flatnonzero(pine(ch, session_by="inside")(sess=(500, 530))["in_session"]).tolist() == [ch.ix(D0, "08:30")]
    m5 = Chart(5).flat(D0, "08:00", "17:00")
    assert np.flatnonzero(run(m5, sess=(500, 530))["in_session"]).tolist() == list(
        range(m5.ix(D0, "08:20"), m5.ix(D0, "08:45") + 1))


def _evening(ch, day):
    """The same New York evening path on any chart: a cross above the range at 18:00 (c 102), a high of 103.5 at
    19:00 (above u1 = 103), a dip at 21:00 and a cross back above at 21:05."""
    ch.bar(day, "18:00", 100, 102.5, 99.9, 102.0).hold(day, "18:05", "24:00", 102.0)
    ch.bar(day, "19:00", 102, 103.5, 101.5, 102.0)
    ch.bar(day, "21:00", 102, 102.2, 99.8, 100.0).bar(day, "21:05", 100, 102.2, 99.9, 102.0)
    return ch


def test_trap2_the_day_reset_follows_the_exchange_day():
    """l.88 ``isNewDay`` = the daily bar changed: gold's day starts at 17:00 New York (the 18:00 reopen after the
    break is the new day, not midnight), BTC's at 00:00 UTC (20:00 New York in summer). After the reset the range is
    na: on gold the 18:00 cross, the 19:00 high above u1 and the 21:05 cross count for nothing; on BTC, whose range
    lives until 20:00 New York, the 18:00 cross is a breakout (unlabelled: the display window ended at 17:00) and the
    19:00 high counts as T1 up, while the 21:05 cross after the reset is nothing. The 'clock0' reading (midnight New
    York) would keep gold's range through the evening too."""
    g = base_day(D0)
    g.flat(D0, "18:00", "24:00").flat(D1, "00:00", "02:00")
    _evening(g, D0)
    og = run(g, symbol=GOLD)
    assert np.flatnonzero(og["new_day"]).tolist() == [g.ix(D0, "18:00")]
    k18 = g.ix(D0, "18:00")
    assert og["session_ended"][k18 - 1] and not og["session_ended"][k18:].any() and np.isnan(og["or_high"][k18:]).all()
    assert not og["breakout_up"].any() and not row(og).hit_u1 and row(og).span_end == k18
    assert_same(og, pine(g, "ny17")())
    # BTC: bars around the clock, the same path; the day ends at 00:00 UTC = 20:00 New York (EDT)
    b = base_day(D0, end="24:00").flat(D1, "00:00", "02:00")
    _evening(b, D0)
    ob = run(b, symbol=BTC)
    assert np.flatnonzero(ob["new_day"]).tolist() == [b.ix(D0, "20:00")] and ny_ts(D0, "20:00") % DAY == 0
    assert ob["breakout_up"][b.ix(D0, "18:00")] and not ob["label_up"].any()
    assert row(ob).hit_u1 and row(ob).hit_u1_bar == b.ix(D0, "19:00") and row(ob).span_end == b.ix(D0, "20:00")
    assert not ob["breakout_up"][b.ix(D0, "21:05")] and row(ob).first_breakout_bar == b.ix(D0, "18:00")
    assert_same(ob, pine(b, "utc0")())
    # 'auto' is the symbol's exchange day; the alternative reading moves gold's reset to midnight
    assert ORB.day_boundary_of(GOLD) == "ny17" and ORB.day_boundary_of(BTC) == "utc0"
    with pytest.raises(ValueError):
        run(g, symbol=None)
    oc = run(g, day_boundary="clock0")
    assert oc["breakout_up"][k18] and row(oc).hit_u1_bar == g.ix(D0, "19:00")
    assert_same(oc, pine(g, "clock0")())


def test_trap3_fixed_utc_minus_5_against_new_york_time():
    """l.35: "UTC-5" is a fixed offset. On 2023-07-12 (EDT) the New York range is 09:30-10:00 EDT = 13:30 UTC and the
    literal one 10:30-11:00 EDT = 14:30 UTC; the display windows end at 17:00 EDT and 18:00 EDT. Path (BTC-like, all
    hours): the New York range [99, 101], the literal one [99.2, 100.8]; 10:05 closes at 101.5 (the New York long;
    for the literal clock it is before its session), 11:05 at 101.0 (the literal long; for New York it equals orHigh:
    no breakout). Each long exits by the window rule at its clock's 17:00. In winter (2023-01-11, EST) the two clocks
    give the same everything."""
    S = "2023-07-12"
    ch = Chart(5).flat(S, "08:00", "19:00")
    ch.bar(S, "09:40", 100, 101.0, 99.5, 100).bar(S, "09:50", 100, 100.5, 99.0, 100)
    ch.bar(S, "10:40", 100, 100.8, 99.5, 100).bar(S, "10:50", 100, 100.5, 99.2, 100)
    ch.bar(S, "10:05", 100, 101.6, 99.9, 101.5)
    ch.bar(S, "11:05", 100, 101.1, 99.9, 101.0)
    ny, lit = run(ch, symbol=BTC), run(ch, symbol=BTC, clock="utc-5")
    t = ch.arrays()[0]
    assert [int(x % DAY) // 60 for x in t[ny["in_session"]]] == list(range(13 * 60 + 30, 14 * 60, 5))
    assert [int(x % DAY) // 60 for x in t[lit["in_session"]]] == list(range(14 * 60 + 30, 15 * 60, 5))
    assert (row(ny).or_high, row(ny).or_low, row(lit).or_high, row(lit).or_low) == (101.0, 99.0, 100.8, 99.2)
    assert np.flatnonzero(ny["label_up"]).tolist() == [ch.ix(S, "10:05")]
    assert np.flatnonzero(lit["label_up"]).tolist() == [ch.ix(S, "11:05")]
    assert (row(ny).exit_bar, row(ny).exit_reason) == (ch.ix(S, "17:00"), "window")
    assert (row(lit).exit_bar, row(lit).exit_reason) == (ch.ix(S, "18:00"), "window")
    assert_same(ny, pine(ch, "utc0")())
    assert_same(lit, pine(ch, "utc0")(clock="utc-5"))
    W = "2023-01-11"
    wch = Chart(5).flat(W, "08:00", "19:00")
    wch.bar(W, "09:40", 100, 101.0, 99.5, 100).bar(W, "09:50", 100, 100.5, 99.0, 100)
    wch.bar(W, "10:05", 100, 101.6, 99.9, 101.5)
    a, b = run(wch, symbol=BTC), run(wch, symbol=BTC, clock="utc-5")
    assert outputs_equal(a, b) and frames_equal(a["days"], b["days"]) and a["label_up"].sum() == 1


def test_trap4_the_crossover_semantics():
    """l.243 ``ta.crossover(close, orHigh)`` = ``close > orHigh and close[1] <= orHigh[1]`` on closes. 10:00: a wick
    to 101.5 that closes inside (100.5): nothing; 10:05 closes AT orHigh (101.0): not a breakout; 10:10 closes 101.2:
    a breakout (close[1] = orHigh[1] counts as <=), labelled; 10:15 stays above: no new cross; 10:20 falls back to
    100.9; 10:25 crosses again (101.3): a breakout, the alert's condition, but no second label. The misreading 'level'
    (close above the range) fires on every bar above it."""
    ch = base_day()
    ch.bar(D0, "10:00", 100, 101.5, 99.8, 100.5).bar(D0, "10:05", 100.5, 101.2, 100.4, 101.0)
    ch.bar(D0, "10:10", 101.0, 101.3, 100.9, 101.2).bar(D0, "10:15", 101.2, 101.5, 101.1, 101.4)
    ch.bar(D0, "10:20", 101.4, 101.5, 100.8, 100.9).bar(D0, "10:25", 100.9, 101.4, 100.8, 101.3)
    ch.hold(D0, "10:30", "17:00", 101.3)
    out = run(ch)
    up = np.flatnonzero(out["breakout_up"]).tolist()
    assert up == [ch.ix(D0, "10:10"), ch.ix(D0, "10:25")] and not out["breakout_dn"].any()
    assert np.flatnonzero(out["label_up"]).tolist() == [ch.ix(D0, "10:10")]
    assert row(out).first_breakout_bar == ch.ix(D0, "10:10") and row(out).entry_bar == ch.ix(D0, "10:10")
    assert_same(out, pine(ch)())
    lv = pine(ch, cross="level")()
    assert np.flatnonzero(lv["breakout_up"]).tolist()[:3] == [ch.ix(D0, "10:10"), ch.ix(D0, "10:15"),
                                                             ch.ix(D0, "10:25")]
    assert lv["breakout_up"].sum() == 1 + 1 + (ch.ix(D0, "16:55") - ch.ix(D0, "10:25") + 1)


def _long_then_bear(ch):
    """Long at 10:00 (trail 99.9 - 2 ATR = 97.69); 10:05 closes at 98.8 (low 98.7): below orLow 99, above the
    trail."""
    bull_at_10(ch)
    ch.bar(D0, "10:05", 101.5, 101.6, 98.7, 98.8)
    ch.hold(D0, "10:10", "17:00", 98.8)
    return ch


def test_trap5_can_signal_is_per_side_and_active_dir_blocks_new_trades():
    """l.125-126, 252-272: one label per SIDE per day, and ``activeDir`` blocks a new trade. The long of 10:00 is
    still open when 10:05 breaks down (close 98.8 > trail 97.69): the bear label is drawn, no short opens, the long
    stays. Misreadings: one label per day for both sides (no bear label); an opposite label reversing the trade (a
    short at 10:05)."""
    ch = _long_then_bear(base_day())
    out = run(ch)
    k0, k1 = ch.ix(D0, "10:00"), ch.ix(D0, "10:05")
    assert np.flatnonzero(out["label_up"]).tolist() == [k0] and np.flatnonzero(out["label_dn"]).tolist() == [k1]
    assert out["trail"][k1] == out["trail"][k0] and abs(out["trail"][k0] - 97.6853) < 1e-4 and 98.8 > out["trail"][k1]
    r = row(out)
    assert (r.trade_side, r.entry_bar, r.exit_reason, r.trade2_side) == (1, k0, "open", 0)
    assert np.all(out["active_dir"][k0:] == 1)
    assert_same(out, pine(ch)())
    one = pine(ch, per_side=False)()
    assert not one["label_dn"].any()
    rev = pine(ch, block=False)()
    assert [(x["side"], x["entry_bar"]) for x in rev["trades"]][:2] == [(1, k0), (-1, k1)]
    assert rev["trades"][0]["reason"] == "reverse"


def _long_trail_then_short(ch):
    """Long at 10:00; a ramp to 104.5 by 10:30 lifts the trail to 101.61; 10:35 closes at 101.2: the trail exit
    (above orLow: no bear breakout); 10:40 closes at 100.4; 10:45 closes at 98.5 (high 100.5): a bear breakout, so
    a short opens at orLow 99 with its trail at 100.5 + 2 ATR."""
    bull_at_10(ch)
    ch.walk(D0, "10:05", [102.0, 102.5, 103.0, 103.5, 104.0, 104.5])
    ch.bar(D0, "10:35", 104.5, 104.6, 101.0, 101.2).bar(D0, "10:40", 101.2, 101.3, 100.3, 100.4)
    ch.bar(D0, "10:45", 100.4, 100.5, 98.4, 98.5)
    ch.hold(D0, "10:50", "17:00", 98.5)
    return ch


def test_trap6_nz_trail_stop_1_on_the_entry_bar():
    """l.258 / 275: on the entry bar ``trailStop[1]`` is na (no trade at the previous bar's end), so the trail is the
    entry bar's own ``low - 2 ATR`` (99.9 - 2 * 1.10735 = 97.6853), and on the next bar ``max(that, low - 2 ATR)``.
    The day's second trade (the short of 10:45, after the long's trail exit at 10:35) starts at ``high + 2 ATR`` of
    its own entry bar: trailStop was set back to na at the exit (l.279). Misreadings: no nz (the trail stays na: the
    long never exits by its trail and the short never opens); a stale trail (never set back to na: the short's
    trail starts at the long's 101.61)."""
    ch = _long_trail_then_short(base_day())
    out = run(ch)
    atr, tr = out["atr"], out["trail"]
    _, o, h, l, c, v = ch.arrays()
    k0, k1, kx, ks = ch.ix(D0, "10:00"), ch.ix(D0, "10:05"), ch.ix(D0, "10:35"), ch.ix(D0, "10:45")
    assert same(atr, I.atr(h, l, c, 14))
    assert tr[k0] == l[k0] - atr[k0] * 2.0 and abs(tr[k0] - 97.6853) < 1e-4
    assert tr[k1] == max(tr[k0], l[k1] - atr[k1] * 2.0) and tr[k1] > tr[k0]
    assert abs(tr[kx - 1] - 101.612) < 1e-3 and c[kx] < tr[kx - 1] and np.isnan(tr[kx]) and out["active_dir"][kx] == 0
    assert tr[ks] == h[ks] + atr[ks] * 2.0 and out["active_dir"][ks] == -1
    r = row(out)
    assert (r.trade_side, r.exit_bar, r.exit_reason, r.trade2_side, r.entry2_bar, r.entry2_price) == (
        1, kx, "trail", -1, ks, 99.0)
    assert_same(out, pine(ch)())
    no_nz = pine(ch, trail_seed="none")()
    assert np.isnan(no_nz["trail"][k0:]).all() and [x["side"] for x in no_nz["trades"]] == [1]
    stale = pine(ch, trail_seed="stale")()
    assert stale["trail"][ks] == tr[kx - 1] != tr[ks]


def test_trap7_the_reset_runs_before_the_exit_and_the_bear_branch_before_the_exit():
    """(a) l.246-250 before l.274-286: gold's long, still open at 16:55, vanishes at the 18:00 reopen (a new day
    outside the window): nothing is booked; with the exits first it would be booked at the 18:00 close. On BTC
    (00:00 UTC day) the 17:00 bar exits by the window rule at its close. (b) l.263 before l.274: 10:05 closes at 97.0,
    below orLow 99 and below the long's trail 97.69: the bear label is drawn first (canSignalDn := false; no entry,
    the long is open), then the long exits by its trail; no short that day, not even at the second cross under
    (10:15). With the exits first, a short would open at 10:05."""
    g = bull_at_10(base_day())
    g.hold(D0, "10:05", "17:00", 101.5)
    g.flat(D0, "18:00", "19:00", p=101.5)
    og = run(g)
    k18 = g.ix(D0, "18:00")
    assert og["active_dir"][k18 - 1] == 1 and og["active_dir"][k18] == 0 and og["new_day"][k18]
    assert (row(og).exit_bar, row(og).exit_reason) == (k18, "reset") and np.isnan(row(og).exit_price)
    assert_same(og, pine(g)())
    late = pine(g, reset_first=False)()["trades"][0]
    assert (late["exit_bar"], late["reason"], late["exit_price"]) == (k18, "window", 101.5)
    b = bull_at_10(base_day(end="19:00"))
    b.hold(D0, "10:05", "19:00", 101.5)
    ob = run(b, symbol=BTC)
    assert (row(ob).exit_bar, row(ob).exit_reason, row(ob).exit_price) == (b.ix(D0, "17:00"), "window", 101.5)
    assert_same(ob, pine(b, "utc0")())
    # (b) the bear branch before the long's exit
    ch = bull_at_10(base_day())
    ch.bar(D0, "10:05", 101.5, 101.6, 96.9, 97.0).bar(D0, "10:10", 97.0, 100.5, 96.9, 100.0)
    ch.bar(D0, "10:15", 100.0, 100.1, 97.9, 98.0).hold(D0, "10:20", "17:00", 98.0)
    out = run(ch)
    k1 = ch.ix(D0, "10:05")
    assert out["label_dn"][k1] and out["breakout_dn"][ch.ix(D0, "10:15")] and out["label_dn"].sum() == 1
    assert (row(out).exit_bar, row(out).exit_reason, row(out).trade2_side) == (k1, "trail", 0)
    assert not (out["active_dir"] == -1).any()
    assert_same(out, pine(ch)())
    first = pine(ch, bear_first=False)()
    assert first["active_dir"][k1] == -1 and [x["side"] for x in first["trades"]] == [1, -1]


def test_trap8_the_entry_is_booked_at_or_high_while_the_real_fill_differs():
    """l.257 / 268: the script books its long at orHigh (101.0), not at the breakout close (101.5), and a short at
    orLow (99.0), not at its close (98.5). The decision is known at the label bar's close; a real order fills at the
    next M1 open (PREREG 4), which neither number is. The misreading 'close' books the label bar's close."""
    ch = _long_trail_then_short(base_day())
    out = run(ch)
    r = row(out)
    _, o, h, l, c, v = ch.arrays()
    assert (r.entry_price, c[r.entry_bar], r.entry2_price, c[r.entry2_bar]) == (101.0, 101.5, 99.0, 98.5)
    assert r.entry_price == r.or_high and r.entry2_price == r.or_low and r.exit_price == c[r.exit_bar] == 101.2
    by_close = pine(ch, entry_at="close")()["trades"]
    assert [x["entry_price"] for x in by_close] == [101.5, 98.5]


def _m1_day(day, lo, hi, c10, after, spike=None):
    """M1 bid bars 08:00-11:59 New York at 100 +- 0.02, the session's extremes lo / hi (09:40 / 09:50), the 10:00-10:04
    minutes rising to ``c10`` (the M5 bar's close), then flat at ``after``; ``spike``: (hh:mm, high) of one minute.
    Spread 0.2, one tick a minute."""
    t = np.arange(ny_ts(day, "08:00"), ny_ts(day, "12:00"), 60, dtype=np.int64)
    p = np.full(len(t), 100.0)
    i10 = int(np.searchsorted(t, ny_ts(day, "10:00")))
    p[i10:i10 + 5] = np.linspace(100.0, c10, 6)[1:]
    p[i10 + 5:] = after
    o = np.concatenate(([100.0], p[:-1]))
    h, l = np.maximum(o, p) + 0.02, np.minimum(o, p) - 0.02
    h[int(np.searchsorted(t, ny_ts(day, "09:40")))] = hi
    l[int(np.searchsorted(t, ny_ts(day, "09:50")))] = lo
    if spike:
        h[int(np.searchsorted(t, ny_ts(day, spike[0])))] = spike[1]
    return t, o, h, l, p


def test_trap9_absolute_levels_and_the_kernel_trap():
    """l.139-142, 191-193: the levels are absolute prices of the range (u_k = orHigh + width * k, d_k = orLow -
    width * k), whatever the entry. The map's kernel trap (0.4): fed to the execution as levels, they must be turned
    into distances from the ACTUAL fill, and an entry whose fill is already at or beyond its target or stop must be
    dropped (PREREG 4). Day 1 (2019-03-13): a narrow range [99.95, 100.05] (u1 = 100.15) and a 10:00 bar closing at
    100.4: the label's fill (the next M1 open 100.4 + spread 0.2) is above u1, so the harness drops it. Day 2: the
    range [99.5, 100.5] (u1 = 101.5) and a close at 100.8: filled at 101.0 with the stop at orLow 99.5, risk 1.5 =
    fill - level (not orHigh - orLow = 1.0); a minute at 10:30 reaching 101.6 exits at the level 101.5 itself."""
    parts = [_m1_day("2019-03-13", 99.95, 100.05, 100.4, 100.4),
             _m1_day("2019-03-14", 99.5, 100.5, 100.8, 101.0, spike=("10:30", 101.6))]
    t, o, h, l, c = (np.concatenate(z) for z in zip(*parts))
    m1 = {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(len(t), 0.2), "n": np.ones(len(t))}
    mk = M.TMarket2(GOLD, m1)
    b = mk.tbars("M5")
    out = ORB.orb(b.t, b.o, b.h, b.l, b.c, b.vol, 5, symbol=GOLD)
    d = out["days"]
    assert len(d) == 2 and d.label_up_bar.tolist() == d.post_bar.tolist()
    w0 = 100.05 - 99.95
    assert d.u1.tolist() == [100.05 + w0 * 1.0, 101.5] and d.d2.tolist() == [99.95 - w0 * 2.0, 97.5]
    assert np.all(d.u3 == d.or_high + d.width * 3.0) and np.all(d.d1 == d.or_low - d.width * 1.0)
    # the levels are constant over each post-session span, independent of the entry
    for _, r in d.iterrows():
        span = slice(r.post_bar, r.span_end)
        assert np.all(out["or_high"][span] == r.or_high) and np.all(out["or_low"][span] == r.or_low)
    fills = [mk.o[b.ex[k]] + mk.sp[b.ex[k]] for k in d.label_up_bar]
    assert abs(fills[0] - 100.6) < 1e-9 and fills[0] > d.u1[0] and abs(fills[1] - 101.0) < 1e-9 < d.u1[1] - fills[1]
    ex = M.event_exec("M5", entries=M.entries(d.label_up_bar.to_numpy(), 1, stop_level=d.or_low.to_numpy(),
                                              target_level=d.u1.to_numpy()))
    r = M.run_exec(mk, ex, "2019-03-13 12:00", int(mk.t[-1]) + 60)
    assert r.counts["dropped_target"] == 1 and r.counts["taken"] == 1 and len(r.trades) == 1
    tr = r.trades.iloc[0]
    assert abs(tr.entry - 101.0) < 1e-9 and abs(tr.risk - 1.5) < 1e-9 and tr.reason == "target"
    assert abs(tr.exit - 101.5) < 1e-9


# ───────────────────────────── 2. the map's thirteen test cases ─────────────────────────────

def _two_days(d_a, d_b, tf=5):
    ch = Chart(tf)
    for d in (d_a, d_b):
        ch.flat(d, "08:00", "17:00")
    return ch


def test_case01_dst_march_2023_the_range_moves_from_1430_to_1330_utc():
    """Friday 2023-03-10 (EST) against Monday 2023-03-13 (EDT): the New York range starts at 14:30 UTC, then at
    13:30 UTC; the literal UTC-5 clock stays at 14:30 UTC (= 10:30 EDT on the Monday)."""
    ch = _two_days("2023-03-10", "2023-03-13")
    t = ch.arrays()[0]
    for clock, want in (("ny", [14 * 60 + 30, 13 * 60 + 30]), ("utc-5", [14 * 60 + 30, 14 * 60 + 30])):
        out = run(ch, clock=clock)
        d = out["days"]
        assert [int(t[k] % DAY) // 60 for k in d.start_bar] == want and d.end_bar.tolist() == (d.start_bar + 5).tolist()
        assert out["in_session"].sum() == 12
        assert_same(out, pine(ch)(clock=clock))


def test_case02_dst_november_2023_the_range_moves_back_and_the_literal_clock_stays_at_1430_utc():
    """Friday 2023-11-03 (EDT) against Monday 2023-11-06 (EST): 13:30 UTC, then 14:30 UTC on the New York clock;
    14:30 UTC throughout on the literal one."""
    ch = _two_days("2023-11-03", "2023-11-06")
    t = ch.arrays()[0]
    for clock, want in (("ny", [13 * 60 + 30, 14 * 60 + 30]), ("utc-5", [14 * 60 + 30, 14 * 60 + 30])):
        out = run(ch, clock=clock)
        assert [int(t[k] % DAY) // 60 for k in out["days"].start_bar] == want
        assert_same(out, pine(ch)(clock=clock))


def test_case03_the_1000_bar_closes_beyond_the_range():
    """On the first post-session bar ``close[1] <= orHigh[1]`` always holds (09:55 closed inside its range), so the
    10:00 bar closing at 101.5 is a breakout and a label at once: the first breakout bar is the post-session bar.
    The mirror the next day: 10:00 closes at 98.5."""
    ch = _two_days(D0, D1)
    for d in (D0, D1):
        ch.bar(d, "09:40", 100, 101.0, 99.5, 100).bar(d, "09:50", 100, 100.5, 99.0, 100)
    bull_at_10(ch, D0)
    ch.bar(D1, "10:00", 100, 100.1, 98.4, 98.5).hold(D1, "10:05", "17:00", 98.5)
    out = run(ch)
    d = out["days"]
    assert d.first_breakout_bar.tolist() == d.post_bar.tolist() == [ch.ix(D0, "10:00"), ch.ix(D1, "10:00")]
    assert d.first_breakout_side.tolist() == [1, -1] and d.label_up_bar[0] == d.post_bar[0]
    assert d.label_dn_bar[1] == d.post_bar[1] and d.trade_side.tolist() == [1, -1]
    assert_same(out, pine(ch)())


def test_case04_a_long_open_when_the_bear_breakout_comes_label_and_alert_but_no_trade():
    ch = _long_then_bear(base_day())
    out = run(ch)
    k1 = ch.ix(D0, "10:05")
    assert out["breakout_dn"][k1] and out["label_dn"][k1] and out["active_dir"][k1] == 1
    assert row(out).trade2_side == 0 and row(out).label_dn_bar == k1
    assert_same(out, pine(ch)())


def test_case05_a_bear_breakout_on_the_long_trail_exit_bar_no_short_that_day():
    """10:05 closes at 97.0, below orLow and below the long's trail (97.69): the bear label is used up before the
    long's exit; the second cross under at 10:15 is an alert only."""
    ch = bull_at_10(base_day())
    ch.bar(D0, "10:05", 101.5, 101.6, 96.9, 97.0).bar(D0, "10:10", 97.0, 100.5, 96.9, 100.0)
    ch.bar(D0, "10:15", 100.0, 100.1, 97.9, 98.0).hold(D0, "10:20", "17:00", 98.0)
    out = run(ch)
    k1 = ch.ix(D0, "10:05")
    assert out["trail"][k1 - 1] > 97.0 and out["label_dn"][k1] and out["active_dir"][k1] == 0
    assert np.flatnonzero(out["breakout_dn"]).tolist() == [k1, ch.ix(D0, "10:15")]
    assert not (out["active_dir"] == -1).any() and row(out).trade2_side == 0
    assert_same(out, pine(ch)())


def test_case06_the_long_is_closed_by_the_trail_then_a_bear_breakout_opens_a_short():
    ch = _long_trail_then_short(base_day())
    out = run(ch)
    r = row(out)
    kx, ks = ch.ix(D0, "10:35"), ch.ix(D0, "10:45")
    assert (r.exit_bar, r.exit_reason, r.trade2_side, r.entry2_bar, r.exit2_reason) == (kx, "trail", -1, ks, "open")
    assert not out["breakout_dn"][kx] and out["label_dn"][ks] and np.all(out["active_dir"][ks:] == -1)
    assert_same(out, pine(ch)())


def test_case07_a_second_cross_up_gives_an_alert_but_no_label():
    ch = bull_at_10(base_day())
    ch.bar(D0, "10:05", 101.5, 101.6, 100.5, 100.8).bar(D0, "10:10", 100.8, 101.5, 100.7, 101.4)
    ch.hold(D0, "10:15", "17:00", 101.4)
    out = run(ch)
    assert np.flatnonzero(out["breakout_up"]).tolist() == [ch.ix(D0, "10:00"), ch.ix(D0, "10:10")]
    assert np.flatnonzero(out["label_up"]).tolist() == [ch.ix(D0, "10:00")]
    assert row(out).trade2_side == 0 and np.all(out["active_dir"][ch.ix(D0, "10:00"):] == 1)
    assert_same(out, pine(ch)())


def test_case08_the_trail_never_moves_down_and_a_wick_through_it_does_not_exit():
    """10:05 wicks to 96.0, far below the trail (97.69), and closes at 101.8: no exit (the test is on the close), and
    the trail stays at 97.69 although low - 2 ATR is now 93.1; afterwards it only rises."""
    ch = bull_at_10(base_day())
    ch.bar(D0, "10:05", 101.5, 101.9, 96.0, 101.8).hold(D0, "10:10", "17:00", 101.8)
    out = run(ch)
    k0, k1 = ch.ix(D0, "10:00"), ch.ix(D0, "10:05")
    tr = out["trail"][k0:]
    assert out["trail"][k1] == out["trail"][k0] and 96.0 < out["trail"][k1] < 101.8
    assert np.all(np.diff(tr) >= 0) and tr[-1] > tr[0] and np.all(out["active_dir"][k0:] == 1)
    _, o, h, l, c, v = ch.arrays()
    assert l[k1] - 2 * out["atr"][k1] < out["trail"][k1]
    assert_same(out, pine(ch)())


def test_case09_t1_up_and_t1_down_on_one_day_and_t2_on_a_day_without_a_breakout():
    """Day 1: the 10:00 bar's high reaches u1 = 103 while it closes inside (counted on the post-session bar itself),
    and 11:00's low reaches d1 = 97: both counted. Day 2: no close leaves the range, but a wick to 105.1 counts T1
    and T2 up on the same bar."""
    ch = _two_days(D0, D1)
    for d in (D0, D1):
        ch.bar(d, "09:40", 100, 101.0, 99.5, 100).bar(d, "09:50", 100, 100.5, 99.0, 100)
    ch.bar(D0, "10:00", 100, 103.2, 99.9, 100.5).bar(D0, "11:00", 100, 100.4, 96.8, 99.5)
    ch.bar(D1, "12:00", 100, 105.1, 99.8, 100.2)
    out = run(ch)
    d = out["days"]
    assert d[["hit_u1", "hit_u2", "hit_d1", "hit_d2"]].values.tolist() == [[True, False, True, False],
                                                                           [True, True, False, False]]
    assert (d.hit_u1_bar[0], d.hit_d1_bar[0]) == (ch.ix(D0, "10:00"), ch.ix(D0, "11:00"))
    assert d.hit_u1_bar[1] == d.hit_u2_bar[1] == ch.ix(D1, "12:00") and not d.hit_u3.any()
    assert d.first_breakout_side.tolist() == [0, 0] and not out["breakout_up"].any() and not out["breakout_dn"].any()
    assert_same(out, pine(ch)())


def test_case10_a_holiday_without_session_bars_has_no_range_and_no_session_count():
    """Day 2 has bars, but none opening in 09:30-10:00: no range, no row, the session count stays 1, and its
    10:30 close above day 1's range is no breakout (that range ended at the day reset). Without the day reset
    ('none'), day 1's range would live on and give day 2 a label and a trade."""
    ch = Chart(5)
    base_day(D0, ch)
    ch.flat(D1, "08:00", "09:30").flat(D1, "10:00", "17:00")
    ch.bar(D1, "10:30", 100, 102.2, 99.9, 102.0).hold(D1, "10:35", "17:00", 102.0)
    out = run(ch)
    assert len(out["days"]) == 1                                # one row per session the script counts
    assert not out["breakout_up"].any() and not out["in_session"][ch.ix(D1, "08:00"):].any()
    assert np.isnan(out["or_high"][ch.ix(D1, "08:00"):]).all()
    assert_same(out, pine(ch)())
    stay = pine(ch, "none")()
    assert stay["label_up"][ch.ix(D1, "10:30")] and stay["trades"][0]["entry_bar"] == ch.ix(D1, "10:30")


def test_case11_a_gold_trade_open_at_1659_is_dropped_by_the_reopen_reset():
    """The long of 10:00 rides to the 16:55 bar; the next bar is the 18:00 reopen, the new day: the daily gates
    (l.246-250) set activeDir to 0 before the exit test, so the trade vanishes unbooked (faithful bookkeeping)."""
    ch = bull_at_10(base_day())
    ch.walk(D0, "10:05", [101.5 + 0.01 * k for k in range(1, 84)], wick=0.2)
    ch.flat(D0, "18:00", "18:30", p=102.4)
    out = run(ch)
    k55, k18 = ch.ix(D0, "16:55"), ch.ix(D0, "18:00")
    assert out["active_dir"][k55] == 1 and np.isfinite(out["trail"][k55]) and out["active_dir"][k18] == 0
    r = row(out)
    assert (r.exit_bar, r.exit_reason) == (k18, "reset") and np.isnan(r.exit_price) and r.span_end == k18
    assert_same(out, pine(ch)())


def test_case12_m5_and_m15_give_the_same_range_but_a_different_first_breakout():
    """The M15 bars are the M5 bars three by three. Range [99, 101] on both. M5: 10:00 closes at 101.5 (up), 10:05
    at 100, 10:10 at 98.5 (down: a second breakout). M15: the 10:00 bar closes at 98.5, so its first breakout is
    down."""
    m5 = base_day()
    m5.bar(D0, "10:00", 100, 101.6, 99.9, 101.5).bar(D0, "10:05", 101.5, 101.6, 99.9, 100.0)
    m5.bar(D0, "10:10", 100.0, 100.1, 98.4, 98.5).hold(D0, "10:15", "17:00", 98.5)
    t, o, h, l, c, v = m5.arrays()
    g = np.arange(len(t)) // 3
    first = np.flatnonzero(np.diff(g, prepend=-1) != 0)
    t15, o15, c15 = t[first], o[first], c[np.append(first[1:] - 1, len(t) - 1)]
    h15, l15 = np.maximum.reduceat(h, first), np.minimum.reduceat(l, first)
    v15 = np.add.reduceat(v, first)
    assert np.all(t15 % 900 == 0)
    a = run(m5)
    b = ORB.orb(t15, o15, h15, l15, c15, v15, 15, symbol=GOLD)
    ra, rb = row(a), row(b)
    assert (ra.or_high, ra.or_low) == (rb.or_high, rb.or_low) == (101.0, 99.0)
    assert (ra.first_breakout_side, rb.first_breakout_side) == (1, -1)
    assert t[ra.first_breakout_bar] == t15[rb.first_breakout_bar] == ny_ts(D0, "10:00")
    assert a["breakout_dn"][m5.ix(D0, "10:10")] and (ra.trade_side, rb.trade_side) == (1, -1)
    assert_same(b, PineScript().run(t15, o15, h15, l15, c15, v15, 15))


def test_case13_hv_is_tested_against_an_sma20_that_includes_the_current_bar():
    """Volume 100 everywhere but 300 twenty bars before the 10:00 breakout and 105 on it: the SMA20 with the current
    bar is (19 * 100 + 105) / 20 = 100.25, so the label is HV; the 20 bars before it average 110 (LV). A bar equal to
    its SMA is LV (strict >); the first 19 bars have no SMA (LV)."""
    ch = bull_at_10(base_day())
    k = ch.ix(D0, "10:00")
    keys = sorted(ch.rows)
    ch.rows[keys[k]][4] = 105.0
    ch.rows[keys[k - 20]][4] = 300.0
    out = run(ch)
    _, o, h, l, c, v = ch.arrays()
    assert I.sma(v, 20)[k] == 100.25 and out["hv"][k] and out["label_up"][k]
    assert not out["hv"][:19].any() and not out["hv"][k + 1] and k - 20 < 19            # bar k-20: no SMA yet
    assert_same(out, pine(ch)())
    assert not pine(ch, hv_incl=False)()["hv"][k]


def test_rows_are_the_sessions_the_script_counts_and_a_wiped_range_is_nan():
    """l.181-183: ``days`` has one row per session the script counts (``totalSessions``), with the range the script
    holds after the session (the reconciliation's reading, port B's). (1) A data hole from 09:45 into the next
    exchange day (the next bar is 19:00, after gold's 17:00 roll): l.147's reset on that bar wipes the range before
    l.181 counts the session, so the row has NaN levels, its bars 09:30-09:40 and a span from 19:00 to the next reset
    (the next day's 09:30); the 20:00 bar above where u1 would be is no hit and no breakout. (2) Bars cut at 09:45 of
    the next day, inside its session: that session is not a row, the script has not counted it. (3) A hole from
    09:45 into the next day's 09:45 (a new exchange day inside the session): the range restarts at 09:45 and the one
    row is the next day's, from 09:45."""
    ch = Chart(5).flat(D0, "08:00", "09:45").flat(D0, "19:00", "24:00").flat(D1, "00:00", "17:00")
    ch.bar(D0, "09:35", 100, 101.0, 99.5, 100).bar(D0, "20:00", 100, 104.0, 99.9, 103.5)
    out = run(ch)
    d = out["days"]
    a, z = ch.ix(D0, "19:00"), ch.ix(D1, "09:30")
    assert len(d) == 2 and out["new_day"][a]
    r = row(out)
    assert (r.start_bar, r.end_bar, r.post_bar, r.span_end) == (ch.ix(D0, "09:30"), ch.ix(D0, "09:40"), a, z)
    assert all(np.isnan(r[k]) for k in ("or_high", "or_low", "width", "u1", "u2", "u3", "d1", "d2", "d3"))
    assert not any(r[f"hit_{k}"] for k in ("u1", "u2", "u3", "d1", "d2", "d3")) and r.first_breakout_side == 0
    assert out["session_ended"][a:z].all() and not out["session_ended"][z] and np.isnan(out["or_high"][a:z]).all()
    assert not out["breakout_up"].any() and (row(out, 1).start_bar, row(out, 1).or_high) == (z, 100.5)
    assert_same(out, pine(ch)())
    # (2) the bars end inside the next day's session
    k = ch.ix(D1, "09:45")
    part = ORB.orb(*(x[:k] for x in ch.arrays()), 5, symbol=GOLD)
    assert len(part["days"]) == 1 and row(part).span_end == z and part["in_session"][-3:].all()
    assert_same(part, PineScript().run(*(x[:k] for x in ch.arrays()), 5))
    # (3) a session run that the next exchange day restarts
    h3 = Chart(5).flat(D0, "08:00", "09:45").flat(D1, "09:45", "17:00")
    h3.bar(D0, "09:35", 100, 101.0, 99.5, 100)
    o3 = run(h3)
    k = h3.ix(D1, "09:45")
    assert o3["in_session"][k - 1] and o3["in_session"][k] and o3["new_day"][k]
    assert len(o3["days"]) == 1 and (row(o3).start_bar, row(o3).end_bar) == (k, h3.ix(D1, "09:55"))
    assert row(o3).or_high == 100.5 and row(o3).day == (date.fromisoformat(D1) - EPOCH).days
    assert_same(o3, pine(h3)())


# ───────────────────────────── 3. the contract ─────────────────────────────

def test_output_keys_dtypes_and_the_days_frame():
    ch = _long_trail_then_short(base_day())
    out = run(ch)
    n = len(ch.rows)
    assert tuple(out) == ORB.KEYS
    for k in ORB.BAR_KEYS:
        assert out[k].shape == (n,), k
    for k in BOOL_KEYS:
        assert out[k].dtype == np.bool_, k
    for k in FLOAT_KEYS:
        assert out[k].dtype == np.float64, k
    assert out["active_dir"].dtype == np.int8
    d = out["days"]
    assert tuple(d.columns) == ORB.DAY_COLUMNS and len(d) == 1
    for k in d.columns:
        kind = d[k].dtype.kind
        if k in ("exit_reason", "exit2_reason"):
            assert kind == "O"
        elif k.startswith("hit_") and not k.endswith("_bar"):
            assert kind == "b", k
        elif k in ("or_high", "or_low", "width", "u1", "u2", "u3", "d1", "d2", "d3") or k.endswith("_price"):
            assert kind == "f", k
        else:
            assert d[k].dtype == np.int64, k
    assert set(d.exit_reason) | set(d.exit2_reason) <= set(ORB.EXIT_REASONS)
    assert (d.day[0] + 3) % 7 == 2                              # a Wednesday
    # empty inputs and no volume
    e = ORB.orb(np.zeros(0, np.int64), [], [], [], [], [], 5, symbol=GOLD)
    assert all(e[k].shape == (0,) for k in ORB.BAR_KEYS) and len(e["days"]) == 0
    assert tuple(e["days"].columns) == ORB.DAY_COLUMNS
    nv = ORB.orb(*ch.arrays()[:5], None, 5, symbol=GOLD)
    assert not nv["hv"].any() and outputs_equal({**nv, "hv": out["hv"]}, out)


def test_bad_inputs_are_refused():
    t, o, h, l, c, v = base_day().arrays()
    ok = dict(symbol=GOLD)
    ORB.orb(t, o, h, l, c, v, 5, **ok)
    bad = [
        ((t.astype(float), o, h, l, c, v, 5), ok),                    # float times
        ((t[::-1], o, h, l, c, v, 5), ok),                            # not increasing
        ((t + 60, o, h, l, c, v, 5), ok),                             # off the 5-minute grid
        ((t, o, h, l, c, v, 15), ok),                                 # M5 bars called M15
        ((t, o, np.where(np.arange(len(h)) == 3, np.nan, h), l, c, v, 5), ok),
        ((t, o[:-1], h, l, c, v, 5), ok),
        ((t, o, h, l, c, v[:-1], 5), ok),
        ((t, o, h, l, c, v, 0), ok),
        ((np.arange(len(t), dtype=np.int64) * 420 + 420 * 4_000_000, o, h, l, c, v, 7), ok),   # 7 does not divide 1440
        ((t, o, h, l, c, v, 5), dict(symbol=None)),                   # 'auto' needs the symbol
        ((t, o, h, l, c, v, 5), dict(ok, clock="UTC-5")),
        ((t, o, h, l, c, v, 5), dict(ok, days="1234567")),
        ((t, o, h, l, c, v, 5), dict(ok, day_boundary="exchange")),
        ((t, o, h, l, c, v, 5), dict(ok, sess=(600, 570))),
        ((t, o, h, l, c, v, 5), dict(ok, sess=(570, 1500))),
        ((t, o, h, l, c, v, 5), dict(ok, window_end=570)),
        ((t, o, h, l, c, v, 5), dict(ok, multiples=(1.0, 2.0))),
        ((t, o, h, l, c, v, 5), dict(ok, multiples=(1.0, -2.0, 3.0))),
        ((t, o, h, l, c, v, 5), dict(ok, trail_mult=0.0)),
    ]
    for args, kw in bad:
        with pytest.raises(ValueError):
            ORB.orb(*args, **kw)


def test_the_inputs_are_not_modified():
    t, o, h, l, c, v = base_day().arrays()
    keep = [x.copy() for x in (t, o, h, l, c, v)]
    ORB.orb(t, o, h, l, c, v, 5, symbol=GOLD)
    assert all(np.array_equal(a, b) for a, b in zip((t, o, h, l, c, v), keep))


# ───────────────────────────── 4. random bars: the port against the transcription ─────────────────────────────

def random_chart(kind, tf, start, days, seed, grid=None, holes=True, sigma=0.3):
    """Random chart bars on the tf grid: 'gold' (Sunday from 18:00 New York to Friday 17:00, a break 17:00-18:00
    every day, nothing on Saturday) or 'btc' (every bar); optional holes (1% of the bars and two gaps of a few
    hours) and prices on a coarse grid (exact ties of closes, levels, trails and volumes)."""
    rng = np.random.default_rng(seed)
    step = 60 * tf
    t0 = TM.s_of(start) // step * step
    t = t0 + step * np.arange(days * 1440 // tf, dtype=np.int64)
    loc = X.local_seconds(t, X.NY)
    minute, wd = (loc // 60) % 1440, (loc // DAY + 3) % 7
    keep = np.ones(len(t), np.bool_)
    if kind == "gold":
        keep = ((wd != 5) & ~((wd == 6) & (minute < 18 * 60)) & ~((wd == 4) & (minute >= 17 * 60))
                & ~((minute >= 17 * 60) & (minute < 18 * 60)))
    if holes:
        keep &= rng.random(len(t)) > 0.01
        for _ in range(2):
            a = int(rng.integers(0, len(t) - 100))
            keep[a:a + int(rng.integers(5, 60)) * 5 // tf] = False
    t = t[keep]
    n = len(t)
    s = sigma * math.sqrt(tf / 5)
    c = 100.0 + np.cumsum(rng.normal(0.0, s, n))
    o = np.concatenate(([100.0], c[:-1])) + rng.normal(0.0, 0.03, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.5 * s, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.5 * s, n))
    if grid:
        o, h, l, c = (np.round(x / grid) * grid for x in (o, h, l, c))
        h, l = np.maximum.reduce([h, o, c]), np.minimum.reduce([l, o, c])
    v = rng.integers(1, 8 if grid else 400, n).astype(np.float64)
    return t, o, h, l, c, v


RANDOM_CASES = [
    dict(kind="gold", tf=5, start="2023-03-01", days=30, seed=1, kw={}),
    dict(kind="gold", tf=15, start="2023-10-20", days=30, seed=2, kw={}),
    dict(kind="btc", tf=5, start="2023-03-01", days=30, seed=3, kw={}),
    dict(kind="btc", tf=15, start="2023-10-20", days=30, seed=4, kw=dict(days="all")),
    dict(kind="gold", tf=5, start="2023-10-20", days=30, seed=5, grid=0.25, kw=dict(clock="utc-5")),
    dict(kind="btc", tf=5, start="2023-03-01", days=30, seed=6, grid=0.25, kw=dict(clock="utc-5", days="all")),
    dict(kind="gold", tf=5, start="2023-03-01", days=30, seed=7, kw=dict(sess=(500, 530), trail_mult=1.0)),
    dict(kind="gold", tf=15, start="2023-03-01", days=30, seed=8, grid=0.5,
         kw=dict(sess=(500, 530), multiples=(0.382, 0.618, 1.0), window_end=690)),
    dict(kind="btc", tf=5, start="2023-10-20", days=30, seed=9, kw=dict(day_boundary="clock0", trail_mult=3.0)),
    dict(kind="gold", tf=5, start="2023-03-01", days=30, seed=10, kw=dict(day_boundary="clock0", days="all")),
    dict(kind="btc", tf=15, start="2023-03-01", days=30, seed=11, grid=0.5, kw=dict(day_boundary="ny17")),
    dict(kind="gold", tf=5, start="2023-10-20", days=30, seed=12, grid=0.1, sigma=0.15, kw=dict(trail_mult=0.5)),
]


def _ref_boundary(kind, kw):
    b = kw.get("day_boundary", "auto")
    return ("utc0" if kind == "btc" else "ny17") if b == "auto" else b


@pytest.mark.parametrize("case", RANDOM_CASES, ids=[f"{c['kind']}-{c['tf']}-{c['seed']}" for c in RANDOM_CASES])
def test_port_equals_the_transcription_bit_for_bit_on_random_bars(case):
    bars = random_chart(case["kind"], case["tf"], case["start"], case["days"], case["seed"], case.get("grid"),
                        sigma=case.get("sigma", 0.3))
    sym = BTC if case["kind"] == "btc" else GOLD
    kw = case["kw"]
    port = ORB.orb(*bars, case["tf"], symbol=sym, **kw)
    ref_kw = {k: v for k, v in kw.items() if k != "day_boundary"}
    ref = PineScript().run(*bars, case["tf"], day_boundary=_ref_boundary(case["kind"], kw), **ref_kw)
    assert outputs_equal(port, ref), first_diff(port, ref)
    assert frames_equal(port["days"], ref["days"])
    d = port["days"]
    assert len(d) >= 15 and port["label_up"].any() and port["label_dn"].any() and (d.trade_side != 0).sum() >= 5


def test_the_random_cases_reach_every_branch():
    """Across the random cases: labels without a trade, second trades, every exit reason, hits on every level, ties
    of the close with orHigh / orLow, of the high with a level and of the volume with its SMA."""
    seen = {"label_no_trade": 0, "trade2": 0, "trail": 0, "window": 0, "reset": 0, "tie_close": 0, "tie_level": 0,
            "tie_vol": 0, "hits": np.zeros(6)}
    for case in RANDOM_CASES:
        bars = random_chart(case["kind"], case["tf"], case["start"], case["days"], case["seed"], case.get("grid"),
                            sigma=case.get("sigma", 0.3))
        t, o, h, l, c, v = bars
        out = ORB.orb(*bars, case["tf"], symbol=BTC if case["kind"] == "btc" else GOLD, **case["kw"])
        d = out["days"]
        lab = int(out["label_up"].sum() + out["label_dn"].sum())
        seen["label_no_trade"] += lab - int((d.trade_side != 0).sum() + (d.trade2_side != 0).sum())
        seen["trade2"] += int((d.trade2_side != 0).sum())
        for why in ("trail", "window", "reset"):
            seen[why] += int((d.exit_reason == why).sum() + (d.exit2_reason == why).sum())
        ok = out["session_ended"] & ~out["in_session"]
        seen["tie_close"] += int(np.sum(ok & ((c == out["or_high"]) | (c == out["or_low"]))))
        for _, r in d.iterrows():
            span = slice(int(r.post_bar), int(r.span_end))
            seen["tie_level"] += int(np.sum(h[span] == r.u1) + np.sum(l[span] == r.d1))
        seen["tie_vol"] += int(np.sum(v[19:] == I.sma(v, 20)[19:]))
        seen["hits"] += d[[f"hit_{k}" for k in ("u1", "u2", "u3", "d1", "d2", "d3")]].sum().to_numpy()
    assert all(seen[k] > 0 for k in ("label_no_trade", "trade2", "trail", "window", "reset", "tie_close",
                                     "tie_level", "tie_vol")), seen
    assert np.all(seen["hits"] > 0), seen


@pytest.mark.parametrize("case", RANDOM_CASES, ids=[f"{c['kind']}-{c['tf']}-{c['seed']}" for c in RANDOM_CASES])
def test_the_readings_that_cannot_change_a_signal_change_none_here(case):
    """Three alternative readings of the module docstring answer exactly as the port on every random case: the
    runtime's na handling in ``ta.crossover`` (a breakout needs sessionEnded, and then the previous bar's level
    exists), the just-assigned trail instead of ``trailStop[1]`` (that is na on every entry bar), and, for sessions
    aligned with the bars, membership by overlap or by the whole bar instead of the open. The one exception is the
    COMEX session on M15 (08:20 is not on the 15-minute grid), where the session readings differ (trap 1)."""
    bars = random_chart(case["kind"], case["tf"], case["start"], case["days"], case["seed"], case.get("grid"),
                        sigma=case.get("sigma", 0.3))
    kw = case["kw"]
    port = ORB.orb(*bars, case["tf"], symbol=BTC if case["kind"] == "btc" else GOLD, **kw)
    ref_kw = {k: v for k, v in kw.items() if k != "day_boundary"}
    boundary = _ref_boundary(case["kind"], kw)
    for sw in (dict(cross="runtime"), dict(trail_seed="current"), dict(session_by="overlap"),
               dict(session_by="inside")):
        ref = PineScript(**sw).run(*bars, case["tf"], day_boundary=boundary, **ref_kw)
        aligned = kw.get("sess", (570, 600))[0] % case["tf"] == 0
        if "session_by" in sw and not aligned:
            assert not np.array_equal(ref["in_session"], port["in_session"]), sw
            continue
        assert outputs_equal(port, ref), (sw, first_diff(port, ref))
        assert frames_equal(port["days"], ref["days"]), sw


# ───────────────────────────── 5. truncation invariance ─────────────────────────────

def complete_rows_equal(part, full, upto) -> bool:
    """The rows whose span ended by bar ``upto - 1`` (their next reset is inside the cut bars) are identical."""
    a = part["days"]
    a = a[a.span_end < upto].reset_index(drop=True)
    b = full["days"]
    b = b[b.span_end < upto].reset_index(drop=True)
    return frames_equal(a, b)


@pytest.mark.parametrize("case", RANDOM_CASES[:6], ids=[f"{c['kind']}-{c['tf']}-{c['seed']}" for c in RANDOM_CASES[:6]])
def test_outputs_to_t_do_not_change_when_the_bars_after_t_are_removed(case):
    bars = random_chart(case["kind"], case["tf"], case["start"], case["days"], case["seed"], case.get("grid"))
    sym = BTC if case["kind"] == "btc" else GOLD
    full = ORB.orb(*bars, case["tf"], symbol=sym, **case["kw"])
    rng = np.random.default_rng(case["seed"])
    n = len(bars[0])
    for T in sorted(rng.integers(20, n - 1, 12)) + [n - 1]:
        part = ORB.orb(*[x[:T + 1] for x in bars], case["tf"], symbol=sym, **case["kw"])
        assert outputs_equal(part, full, T + 1), (T, first_diff({k: part[k] for k in ORB.BAR_KEYS},
                                                                {k: full[k][:T + 1] for k in ORB.BAR_KEYS}))
        assert complete_rows_equal(part, full, T + 1), T
        # the last row of the cut bars holds what was known at T: nothing after T
        if len(part["days"]):
            r = part["days"].iloc[-1]
            for k in ORB.DAY_COLUMNS:
                if k.endswith("_bar") and k != "end_bar":
                    assert r[k] <= T, (T, k)


# ───────────────────────────── 6. real bars (to 2024-06-30, the guard closed) ─────────────────────────────

def _binance_ok() -> bool:
    try:
        files = M._binance_files_5m()
    except Exception:                                            # noqa: BLE001 - absent or unreadable inventory
        return False
    need = [path for label, a, z, url, path in files if z > TM.s_of("2019-01-01") and a < CUT]
    return bool(need) and all(p.exists() for p in need)


@pytest.fixture(scope="module", params=SYMS)
def real(request, tmp_path_factory):
    """One symbol's M5 and M15 bars from 2019-01-01 to 2024-06-30 (``external.load_market(symbol,
    earliest="2019-01-01", end="2024-07-01").bars``), their tick volume (the sum of the M1 tick counts), and for BTC
    the Binance 5m volume on the same bars (``tradeiq2_market.binance_volume``, PREREG 2). One symbol in memory at a
    time."""
    symbol = request.param
    months = store.available_months(symbol)
    if (2019, 1) not in months or (2024, 6) not in months:
        pytest.skip(f"the tick store of {symbol} is not on this machine")
    d1, d2 = tmp_path_factory.mktemp("closed1"), tmp_path_factory.mktemp("closed2")
    data = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(TM, "STUDY_DIR", d1)
        mp.setattr(M, "STUDY_DIR", d2)
        mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
        m = X.load_market(symbol, earliest="2019-01-01", end="2024-07-01")
        assert int(m.t[-1]) < CUT and int(m.t[0]) >= TM.s_of("2019-01-01")
        for tf in TF_MIN:
            b = m.bars(tf)
            top = int(b.i1[-1]) + 1
            data[tf] = {"t": b.t, "tc": b.tc, "o": b.o, "h": b.h, "l": b.l, "c": b.c,
                        "vol": np.add.reduceat(m.n[:top], b.i0)}
        if symbol == BTC and _binance_ok():
            mk2 = M.TMarket2(symbol, {"t": m.t, "o": m.o, "h": m.h, "l": m.l, "c": m.c, "spread_mean": m.sp,
                                      "n": m.n}, CUT)
            for tf in TF_MIN:
                assert np.array_equal(mk2.tbars(tf).t, data[tf]["t"])
                data[tf]["bvol"] = M.binance_volume(mk2, tf)[0]
            del mk2
        del m
    yield symbol, data
    data.clear()


def check_structure(out, d, tf_min, sess=(570, 600), days="weekdays", clock="ny"):
    """The contract's NaN pattern and the script's structure on one run (no profit anywhere)."""
    n = len(d["t"])
    assert tuple(out) == ORB.KEYS and all(out[k].shape == (n,) for k in ORB.BAR_KEYS)
    assert np.isnan(out["atr"][:13]).all() and np.isfinite(out["atr"][13:]).all() and np.all(out["atr"][13:] >= 0)
    ins, ended = out["in_session"], out["session_ended"]
    rows = out["days"]
    # every row's span [post_bar, span_end) is exactly where sessionEnded holds, up to the next reset (l.147); a
    # wiped row (a reset on the session-end bar, possible only across a data hole) has na levels there
    prev = np.concatenate(([False], ins[:-1]))
    resets = np.flatnonzero(out["new_day"] | (ins & ~prev))
    spans = np.zeros(n, np.bool_)
    wiped = np.zeros(n, np.bool_)
    for _, r in rows.iterrows():
        a, z = int(r.post_bar), int(r.span_end)
        nxt = resets[resets > a]
        assert z == (int(nxt[0]) if len(nxt) else n)
        spans[a:z] = True
        if np.isnan(r.or_high):
            wiped[a:z] = True
            assert out["new_day"][a] and np.isnan(r.or_low)
        else:
            assert np.all(out["or_high"][a:z] == r.or_high) and np.all(out["or_low"][a:z] == r.or_low)
    assert np.array_equal(spans, ended)
    assert not (ins & ended).any()
    fin = np.isfinite(out["or_high"])
    assert np.array_equal(fin, ended & ~wiped) and np.array_equal(fin, np.isfinite(out["or_low"]))
    assert np.all(out["or_high"][fin] >= out["or_low"][fin])
    for side, lv in (("up", "or_high"), ("dn", "or_low")):
        bo, lab = out[f"breakout_{side}"], out[f"label_{side}"]
        assert not (bo & ~fin).any() and not (bo & ins).any() and not (lab & ~bo).any()
        sign = 1 if side == "up" else -1
        assert np.all(sign * (d["c"][bo] - out[lv][bo]) > 0)
    ad = out["active_dir"]
    assert set(np.unique(ad)) <= {-1, 0, 1}
    live = (ad != 0) & np.isfinite(out["atr"])
    assert np.array_equal(np.isfinite(out["trail"]), live)
    # in-session bars: open inside the session on a weekday of the session clock
    loc = X.local_seconds(d["t"][ins], X.NY) if clock == "ny" else d["t"][ins] - 5 * 3600
    mi = (loc // 60) % 1440
    assert np.all((mi >= sess[0]) & (mi < sess[1]))
    if days == "weekdays":
        assert np.all((loc // DAY + 3) % 7 < 5)
    # the rows
    assert np.all(rows.start_bar <= rows.end_bar) and np.all(np.diff(rows.start_bar) > 0)
    assert np.all(rows.post_bar == rows.end_bar + 1) and np.all(rows.post_bar < rows.span_end)
    ok = rows[rows.or_high.notna()]
    lv = ["or_high", "or_low", "width", "u1", "u2", "u3", "d1", "d2", "d3"]
    assert np.all(np.isfinite(ok[lv].to_numpy())) and np.isnan(rows[rows.or_high.isna()][lv].to_numpy()).all()
    assert np.all(ok.width >= 0) and np.all(ok.u1 >= ok.or_high) and np.all(ok.d1 <= ok.or_low)
    for k in ("first_breakout_bar", "label_up_bar", "label_dn_bar") + tuple(
            f"hit_{x}_bar" for x in ("u1", "u2", "u3", "d1", "d2", "d3")):
        has = rows[k] >= 0
        assert np.all((rows[k][has] >= rows.post_bar[has]) & (rows[k][has] < rows.span_end[has])), k
    assert np.array_equal(np.sort(np.flatnonzero(out["label_up"])), np.sort(rows.label_up_bar[rows.label_up_bar >= 0]))
    for pre in (("trade_side", "entry_bar", "entry_price", "exit_bar", "exit_price", "exit_reason"),
                ("trade2_side", "entry2_bar", "entry2_price", "exit2_bar", "exit2_price", "exit2_reason")):
        side, eb, ep, xb, xp, why = (rows[k] for k in pre)
        on = side != 0
        assert set(why[~on]) <= {""} and set(why[on]) <= {"trail", "window", "reset", "open"}
        assert np.all(np.where(side[on] == 1, rows.label_up_bar[on], rows.label_dn_bar[on]) == eb[on])
        assert np.all(np.where(side[on] == 1, rows.or_high[on], rows.or_low[on]) == ep[on])
        booked = why.isin(["trail", "window"])
        assert np.all(np.isfinite(xp[booked])) and np.isnan(xp[~booked]).all() and np.all(xb[booked] > eb[booked])
        assert np.all(xb[why == "reset"] == rows.span_end[why == "reset"])
    assert np.all((rows.trade2_side == 0) | (rows.trade2_side == -rows.trade_side))
    return rows


@pytest.mark.parametrize("tf", list(TF_MIN))
def test_real_bars_smoke(real, tf):
    symbol, data = real
    d = data[tf]
    n = len(d["t"])
    assert n > (300_000 if tf == "M5" else 100_000) and int(d["tc"][-1]) <= CUT       # nothing from the hold-out
    out = ORB.orb(d["t"], d["o"], d["h"], d["l"], d["c"], d["vol"], TF_MIN[tf], symbol=symbol)
    rows = check_structure(out, d, TF_MIN[tf])
    per_session = 30 // TF_MIN[tf]
    assert len(rows) > 1200 and np.mean(rows.end_bar - rows.start_bar + 1 == per_session) > 0.97
    assert out["hv"].any() and not out["hv"].all() and out["label_up"].sum() > 500 and out["label_dn"].sum() > 500
    if symbol == GOLD:                                   # the reopen after the 17:00 break is a new day (l.246)
        assert not ((rows.exit_reason == "window") | (rows.exit2_reason == "window")).any()
    # BTC: the Binance volume changes the HV tag only
    if "bvol" in d:
        ob = ORB.orb(d["t"], d["o"], d["h"], d["l"], d["c"], d["bvol"], TF_MIN[tf], symbol=symbol)
        assert outputs_equal({**ob, "hv": out["hv"]}, out) and frames_equal(ob["days"], out["days"])
        assert not np.array_equal(ob["hv"], out["hv"]) and ob["hv"].any()
    # the controls and variants of PREREG 6.5 run and keep the structure
    variants = [dict(clock="utc-5"), dict(day_boundary="clock0")]
    variants += [dict(days="all")] if symbol == BTC else [dict(sess=ORB.COMEX_SESSION)]
    for kw in variants:
        ov = ORB.orb(d["t"], d["o"], d["h"], d["l"], d["c"], d["vol"], TF_MIN[tf], symbol=symbol, **kw)
        check_structure(ov, d, TF_MIN[tf], sess=kw.get("sess", (570, 600)), days=kw.get("days", "weekdays"),
                        clock=kw.get("clock", "ny"))


@pytest.mark.parametrize("tf", list(TF_MIN))
def test_real_bars_equal_the_transcription_bit_for_bit(real, tf):
    symbol, data = real
    d = data[tf]
    args = (d["t"], d["o"], d["h"], d["l"], d["c"], d["vol"], TF_MIN[tf])
    port = ORB.orb(*args, symbol=symbol)
    ref = PineScript().run(*args, day_boundary="utc0" if symbol == BTC else "ny17")
    assert outputs_equal(port, ref), first_diff(port, ref)
    assert frames_equal(port["days"], ref["days"])


@pytest.mark.parametrize("tf", list(TF_MIN))
def test_real_bars_truncation_invariance(real, tf):
    symbol, data = real
    d = data[tf]
    keys = ("t", "o", "h", "l", "c", "vol")
    full = ORB.orb(*(d[k] for k in keys), TF_MIN[tf], symbol=symbol)
    for when in ("2020-03-16 14:40", "2021-05-19 15:10", "2022-11-09 20:30"):
        j = int(np.searchsorted(d["tc"], TM.s_of(when), side="right")) - 1
        part = ORB.orb(*(d[k][:j + 1] for k in keys), TF_MIN[tf], symbol=symbol)
        assert outputs_equal(part, full, j + 1), (when, first_diff({k: part[k] for k in ORB.BAR_KEYS},
                                                                   {k: full[k][:j + 1] for k in ORB.BAR_KEYS}))
        assert complete_rows_equal(part, full, j + 1), when
