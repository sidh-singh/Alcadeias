"""
Study 3, entry filters on the bots' designs (``backtesting/research/bot_filters.py``; plan
``backtest_results/bot_filters/PREREG.md``).

* The windows: the 23 Development quarters are round 4's segments, the 5-year window FINAL10's; T1, T2 and the forward
  window as PREREG 4 lists them.
* The guard: every scored window outside Development (T1, T2, forward, the comparison accounts) is refused, base
  designs included, until FINALISTS.md and a matching sha256 exist; ``freeze`` opens it, a wrong hash keeps it shut.
* The 59 filters of PREREG 3 by name, and their definitions on hand-made bars.
* Causality: a filter value never takes effect before its bar's close (it starts at the first row at or after the
  close, the kernel's own switching instant), the session filters switch on the New York clock (DST included), and
  on real bars the allow series up to a time T do not change when the data after T is removed.
* The regime composition: regime = trend where the filter allows that side, 0 elsewhere and before the first stamp;
  on the engine (fixture store, synthetic allow-steps only, so no filter variant is ever scored) the always-allow
  filter is the design fill for fill, one-sided steps are the engine's own allow_long / allow_short switches, and
  every basket opens in a direction both the trend and the steps allowed.
* The Turtle: the gates block first fills only; the exit overlay without flags or with flags it never meets is the
  base trade for trade; an H4 flip closes a long at the next M1 open and the Turtle stays out until its next decision.
* The yardstick, "better", candidates, pairs, finalists, the exam rule, the freeze and the multiple-testing wrapper on
  hand-made tables.
* Slow (``-m slow``; real store, about 5 GB for gold): the published 5-year accounts reproduced by the identity
  filter, and the Turtle's.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.engine import fast
from backtesting.research import bot_filters as B
from backtesting.research import external as X
from backtesting.research import final10 as F
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

ALL_TFS = ("M1", "M5", "M15", "H1", "H4")


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """The guard reads an empty study folder: no FINALISTS.md, the sealed windows are shut."""
    d = tmp_path / "study"
    d.mkdir()
    monkeypatch.setattr(B, "STUDY_DIR", d)
    return d


def has_store(symbol: str) -> bool:
    try:
        return store.data_span(symbol) is not None
    except Exception:
        return False


# ───────────────────────────── the windows ─────────────────────────────

def test_the_23_quarters_are_round_4s_segments_and_the_5y_window_final10s():
    period_of = {"FINAL": "2023", "CONFIRM": "2024-25", "DEV": "2025-26"}
    for sym in ("XAUUSDm", "BTCUSDm"):
        seg = set()
        for f in ("dev", "holdout"):
            d = pd.read_csv(F.IMPROVE / "round4" / f"top3_v4_{f}_{sym}.csv")
            for (per, win, s), _ in d.groupby(["period", "window", "segment"]):
                a, z = [x.strip() for x in s.split("→")]
                p = period_of.get(per) or ("2021" if a.startswith("2021") else "2022")
                seg.add((p, win, a, z))
        assert seg == {(w.period, w.name, w.start, w.end) for w in B.DEV_QUARTERS}
    assert len(B.DEV_QUARTERS) == 23
    assert [sum(w.period == p for w in B.DEV_QUARTERS) for p in B.P5] == [4, 4, 4, 6, 5]
    assert (B.FIVE_Y.start, B.FIVE_Y.end) == F.WINDOWS["5y"] and B.FIVE_Y.continuous
    assert B.DEV_WINDOWS == B.DEV_QUARTERS + (B.FIVE_Y,)
    assert all(B.DEV_START <= w.start and w.end <= B.DEV_END for w in B.DEV_WINDOWS)


def test_the_sealed_windows_are_prereg_4s():
    t1 = [(w.start, w.end) for w in B.T1_QUARTERS]
    assert t1[0] == ("2018-11-13", "2019-01-01") and len(t1) == 9
    assert t1[1:] == [(f"{y}-{m:02d}-01", f"{y + (m == 10)}-{1 if m == 10 else m + 3:02d}-01")
                      for y in (2019, 2020) for m in (1, 4, 7, 10)]
    assert (B.T1_CONT.start, B.T1_CONT.end) == ("2018-11-13", "2021-01-01") == F.WINDOWS["new"]
    t2 = [(w.start, w.end) for w in B.T2_QUARTERS]
    assert t2 == [("2017-01-03", "2017-04-01"), ("2017-04-01", "2017-07-01"), ("2017-07-01", "2017-10-01"),
                  ("2017-10-01", "2018-01-01"), ("2018-01-01", "2018-04-01"), ("2018-04-01", "2018-07-01"),
                  ("2018-07-01", "2018-10-01"), ("2018-10-01", "2018-11-13")]
    assert (B.T2_CONT.start, B.T2_CONT.end) == ("2017-01-03", "2018-11-13")
    assert set(B.exam_windows("XAUUSDm")) == {"t1", "t2"} and set(B.exam_windows("BTCUSDm")) == {"t1"}
    for qs in (B.T1_QUARTERS, B.T2_QUARTERS):
        assert all(a.end == b.start for a, b in zip(qs[:-1], qs[1:]))
    assert B.FORWARD_START == B.DEV_END


# ───────────────────────────── the guard ─────────────────────────────

SEALED = [("2018-11-13", "2019-01-01"), ("2019-01-01", "2019-04-01"), ("2017-01-03", "2017-04-01"),
          ("2018-11-13", "2021-01-01"), ("2018-11-13", "2026-11-13"), ("2026-11-13", "2026-11-26"),
          ("2020-12-31", "2021-04-01"), ("2026-08-13", "2026-11-14")]


@pytest.mark.parametrize("a,z", SEALED)
def test_the_guard_refuses_every_sealed_window_before_the_freeze(a, z):
    with pytest.raises(B.SealedWindowError):
        B.guard(a, z, "test")


def test_the_guard_lets_development_through_and_refuses_data_past_its_end():
    for w in B.DEV_WINDOWS:
        B.guard(w.start, w.end, w.name)
    B.guard_data_end(B.DEV_END, "dev")
    with pytest.raises(B.SealedWindowError):
        B.guard_data_end("2026-11-20", "forward")
    with pytest.raises(B.SealedWindowError):
        B.FilterBook("XAUUSDm", "2026-11-20")


@pytest.mark.parametrize("stage", ["sec", "ticks", "bars"])
def test_the_runners_refuse_t1_and_t2_before_loading_anything_base_included(tmp_path, stage):
    """The base design is not exempt: its exam comparison runs only after the freeze (PREREG 6). The guard fires
    before any data is touched (a missing store would raise something else)."""
    for qs in (B.T1_QUARTERS, B.T2_QUARTERS, (B.T1_CONT,)):
        with pytest.raises(B.SealedWindowError):
            if stage == "sec":
                B.run_sec_stage("xau_v3lite", [B.BASE], qs, tmp_path / "a.csv", tmp_path / "d.csv", workers=1,
                                store_dir=tmp_path / "no_store")
            elif stage == "ticks":
                B.run_tick_stage("xau_v3lite", [B.BASE], qs, tmp_path / "a.csv", workers=1,
                                 store_dir=tmp_path / "no_store")
            else:
                B.run_bar_stage("btc_turtle", [B.BASE], qs, tmp_path / "a.csv", tmp_path / "d.csv",
                                store_dir=tmp_path / "no_store")
    with pytest.raises(B.SealedWindowError):
        B.run_exam("xau_v3lite", [B.BASE], tmp_path, workers=1, store_dir=tmp_path / "no_store")
    with pytest.raises(B.SealedWindowError):
        B.run_compare("btc_turtle", [B.BASE], tmp_path, store_dir=tmp_path / "no_store")


def test_freeze_writes_the_finalists_and_their_hash_and_opens_the_guard(closed_guard):
    assert not B.finalists_frozen()
    f = B.freeze({"xau_v3lite": ["SIDE200-D1"], "btc_turtle": []},
                 {"xau_v3lite": pd.DataFrame({"vid": ["SIDE200-D1"], "score": [3.5], "confirmed_score": [3.2]})})
    body = f.read_bytes()
    assert (closed_guard / "FINALISTS.md.sha256").read_text().split()[0] == hashlib.sha256(body).hexdigest()
    text = body.decode()
    assert "`SIDE200-D1`" in text and "no filter improved it" in text and "3.500" in text and "3.200" in text
    assert "backtesting/research/bot_filters.py" in text and B.blob_id(B.REPO_ROOT / B.CODE_FILES[0]) in text
    assert B.finalists_frozen()
    for a, z in SEALED[:-2]:
        B.guard(a, z, "after the freeze")
    with pytest.raises(FileExistsError):
        B.freeze({"xau_v3lite": []})
    (closed_guard / "FINALISTS.md").write_text(text + "edited\n")
    assert not B.finalists_frozen()
    with pytest.raises(B.SealedWindowError):
        B.guard(*SEALED[0], "after an edit")


def test_blob_id_is_gits():
    import subprocess
    p = B.REPO_ROOT / "backtesting" / "research" / "final10.py"
    got = subprocess.run(["git", "hash-object", "--", str(p)], capture_output=True, text=True, check=True).stdout.strip()
    assert B.blob_id(p) == got


# ───────────────────────────── the filters ─────────────────────────────

def test_the_59_filters_of_prereg_3():
    ids = [f.fid for f in B.single_filters()]
    assert len(ids) == len(set(ids)) == 59
    want = [f"{fam}{n}-{tf}" for fam in ("SIDE", "SLOPE", "TREND") for n in (50, 100, 200) for tf in ("H1", "H4", "D1")]
    want += [f"{fam}-{tf}" for fam in ("CROSS", "LGATE200", "SGATE200", "TSI", "LARSI", "QQE", "VWRSI", "RIB", "MSD",
                                       "HA") for tf in ("H1", "H4", "D1")]
    want += ["SESS-KZ", "SESS-LN"]
    assert ids == want
    assert B.stage1_vids("xau_v3lite") == [B.BASE, B.IDENTITY] + want
    assert B.stage1_vids("btc_turtle")[-4:] == ["EXIT:HA-M1-H4", "EXIT:HA-M1-D1", "EXIT:HA-M4-H4", "EXIT:HA-M4-D1"]
    assert sum(len(B.stage1_vids(k)) - 2 for k in B.DESIGNS) == 59 * 5 + 4      # PREREG 3's 295 singles + 4 exits
    # without study 2's ports (until they are reconciled): 50 singles per design, no exit
    assert B.stage1_vids("xau_v3lite", ports=False) == [B.BASE, B.IDENTITY] + [f for f in want if
                                                                              f.split("-")[0] not in B.PORTS]
    assert len(B.stage1_vids("btc_turtle", ports=False)) == 2 + 50 and B.uses_port("EXIT:HA-M1-D1")
    assert B.uses_port("SIDE50-H1&HA-D1") and not B.uses_port("SIDE50-H1&TSI-D1") and not B.uses_port("BASE")
    assert B.SESSIONS["SESS-KZ"] == (2, 3, 4, 7, 8, 9, 10) and B.SESSIONS["SESS-LN"] == tuple(range(2, 11))
    with pytest.raises(ValueError):
        B.filter_of("SIDE20-H1")


def test_variant_names_kinds_and_pairs():
    assert B.Variant("BASE").kind == "base" and B.Variant("ALLOW").kind == "identity"
    assert B.Variant("TSI-H4").fids == ("TSI-H4",) and B.Variant("TSI-H4").kind == "single"
    assert B.pair_vid("TSI-H4", "SIDE200-D1") == "SIDE200-D1&TSI-H4" == B.pair_vid("SIDE200-D1", "TSI-H4")
    assert B.Variant("SIDE200-D1&TSI-H4").kind == "pair" and B.Variant("SIDE200-D1&TSI-H4").fids == ("SIDE200-D1", "TSI-H4")
    assert B.Variant("EXIT:HA-M4-D1").exit == "HA-M4-D1"
    B.check_vids(B.stage1_vids("btc_turtle"))
    with pytest.raises(ValueError):
        B.check_vids(["EXIT:HA-M9-D1"])


def _synthetic_book(seed: int = 7, days: int = 40, symbol: str = "XAUUSDm") -> B.FilterBook:
    """A FilterBook over hand-made M1 bars (no store): a random walk from 2019-03-04, every minute of every day."""
    rng = np.random.default_rng(seed)
    t0 = TM.s_of("2019-03-04")
    n = days * 1440
    t = t0 + 60 * np.arange(n, dtype=np.int64)
    c = 1300.0 + np.cumsum(rng.normal(0, 0.4, n))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0, 0.3, n)
    lo = np.minimum(o, c) - rng.uniform(0, 0.3, n)
    m1 = {"t": t, "o": o, "h": h, "l": lo, "c": c, "spread_mean": np.full(n, 0.2), "n": rng.integers(1, 50, n).astype(float)}
    bk = object.__new__(B.FilterBook)
    bk.symbol, bk.end = symbol, str(TM.utc(t[-1] + 60).tz_localize(None))
    bk.mk = TM.TMarket(symbol, m1, int(t[-1]) + 60)
    bk.history_from = str(TM.utc(t[0]))
    bk._lines, bk._sides = {}, {}
    return bk


def test_the_filter_definitions_on_hand_made_bars():
    bk = _synthetic_book()
    for tf in B.FILTER_TFS:
        b = bk.bars(tf)
        c = b.c
        sma = {n: I.sma(c, n) for n in (50, 100, 200)}
        with np.errstate(invalid="ignore"):
            for n in (50, 100, 200):
                past = np.concatenate([np.full(5, np.nan), sma[n][:-5]])
                side = (c > sma[n], c < sma[n])
                slope = (sma[n] > past, sma[n] < past)
                for fam, (wl, ws) in (("SIDE", side), ("SLOPE", slope),
                                      ("TREND", (side[0] & slope[0], side[1] & slope[1]))):
                    s = bk.sides(f"{fam}{n}-{tf}")
                    assert np.array_equal(s.al, wl) and np.array_equal(s.as_, ws), (fam, n, tf)
            s = bk.sides(f"CROSS-{tf}")
            assert np.array_equal(s.al, sma[50] > sma[200]) and np.array_equal(s.as_, sma[50] < sma[200])
            s = bk.sides(f"LGATE200-{tf}")
            assert np.array_equal(s.al, c > sma[200]) and s.as_.all()
            s = bk.sides(f"SGATE200-{tf}")
            assert s.al.all() and np.array_equal(s.as_, c < sma[200])
            tsi = I.bjorgum_tsi(c).tsi
            s = bk.sides(f"TSI-{tf}")
            assert np.array_equal(s.al, tsi > 0) and np.array_equal(s.as_, tsi < 0)
            la = I.laguerre_rsi(c, 0.2)
            s = bk.sides(f"LARSI-{tf}")
            assert np.array_equal(s.al, la > 50) and np.array_equal(s.as_, la < 50)
            col = I.qqe_mod(c).color
            s = bk.sides(f"QQE-{tf}")
            assert np.array_equal(s.al, col != I.RED) and np.array_equal(s.as_, col != I.BLUE)
            assert (s.al & s.as_)[:56].all()                    # GRAY before the Bollinger band: both allowed
            vw = I.vwrsi(c, b.vol).rsi
            s = bk.sides(f"VWRSI-{tf}")
            assert np.array_equal(s.al, vw > 50) and np.array_equal(s.as_, vw < 50)
        assert np.array_equal(bk.sides(f"SIDE50-{tf}").tc, b.tc)
    # warm-up: SIDE allows neither side before its SMA exists, LGATE keeps its "always" side
    s = bk.sides("SIDE200-H1")
    assert not s.al[:199].any() and not s.as_[:199].any()
    assert bk.sides("LGATE200-H1").as_[:199].all() and not bk.sides("LGATE200-H1").al[:199].any()


def test_the_dashboard_labels_map_to_sides():
    al, ash = B._msd_sides(np.array(["BULLISH", "LEAN BULL", "NEUTRAL", "LEAN BEAR", "BEARISH", "lean bull "]))
    assert al.tolist() == [True, True, False, False, False, True]
    assert ash.tolist() == [False, False, False, True, True, False]
    al, ash = B._msd_sides(np.array([2, 1, 0, -1, -2, np.nan]))
    assert al.tolist() == [True, True, False, False, False, False] and ash.tolist() == [False] * 3 + [True, True, False]


def test_week_bars_are_monday_weeks_of_the_merged_days():
    bk = _synthetic_book(days=30)
    d1 = bk.bars("D1")
    w = B.week_bars(d1)
    assert pd.Timestamp(int(w.t[0]), unit="s").dayofweek == 0                 # the data starts on a Monday
    assert all(pd.Timestamp(int(x), unit="s").dayofweek == 0 for x in w.tc[:-1])   # a week closes Monday 00:00
    assert w.h.max() == d1.h.max() and w.c[-1] == d1.c[-1] and len(w) == 5
    # 30 days from a Monday end on a Wednesday: that week could still grow, it closes at its ISO end
    assert w.tc[-1] == d1.tc[-1]
    w2 = B.week_bars(d1, end_s=int(d1.tc[-1]))
    assert w2.tc[-1] == TM.s_of("2019-04-08") and np.array_equal(w2.tc[:-1], w.tc[:-1])
    try:
        M = B._port("MSD")
    except B.PortMissing:
        return
    ref = M.weekly_bars(d1, end_s=int(d1.tc[-1]))
    assert np.array_equal(ref.tc, w2.tc) and np.array_equal(ref.t, w2.t) and np.array_equal(ref.h, w2.h)


@pytest.mark.parametrize("family", ["RIB", "MSD", "HA"])
def test_the_ports_of_study_2_feed_their_filters(family):
    try:
        B._port(family)
    except B.PortMissing:
        pytest.skip(f"{B.PORTS[family]} is not in the repository yet")
    bk = _synthetic_book(days=120)
    for tf in B.FILTER_TFS:
        s = bk.sides(f"{family}-{tf}")
        assert len(s.tc) == len(bk.bars(tf)) and not (s.al & s.as_).any()


# ───────────────────────────── causality: stamps, sessions, no look-ahead ─────────────────────────────

def test_a_bar_value_takes_effect_at_the_first_row_at_or_after_its_close():
    rng = np.random.default_rng(3)
    rows = np.sort(rng.integers(0, 10_000_000, 4000)).astype(np.int64) + 1_600_000_000_000
    rows = np.unique(rows)
    tc = np.arange(1_599_999_000, 1_600_011_000, 7, dtype=np.int64)          # closes every 7 s, before and after
    al, ash = rng.random(len(tc)) < 0.5, rng.random(len(tc)) < 0.5
    st = B.bar_steps(rows, B.BarSides(tc, al, ash))
    assert np.all(np.isin(st.t, rows))
    # every stamp is at or after the close of the bar whose value it carries, and no row lies in between
    T = np.concatenate([rows, rows - 1, rows + 1])
    l1, s1 = st.at(T)
    for k, Tm in enumerate(T[:3000]):
        r = rows[rows <= Tm]
        if not len(r):
            assert not l1[k] and not s1[k]
            continue
        seen = r[-1]                                    # the last row a poll at Tm has seen
        i = np.searchsorted(tc * 1000, seen, side="right") - 1
        want = (al[i], ash[i]) if i >= 0 else (False, False)
        assert (l1[k], s1[k]) == want
    # bars that close after the last row never take effect; before the first row the last of them holds
    last = int(rows[-1])
    assert st.t[-1] <= last
    i0 = np.searchsorted(tc * 1000, rows[0], side="right") - 1
    assert st.at([rows[0]])[0][0] == al[i0] and st.at([rows[0] - 1])[0][0] == False   # noqa: E712


def test_a_value_never_precedes_its_close_even_when_a_close_falls_on_a_row():
    rows = np.asarray([1000, 2000, 3000, 3000, 3001, 9000], np.int64) + 1_600_000_000_000
    tc = np.asarray([1_600_000_002, 1_600_000_003, 1_600_000_004], np.int64)    # 2000 and 3000 ms are rows
    st = B.bar_steps(rows, B.BarSides(tc, np.array([True, False, True]), np.array([False, True, False])))
    assert st.t.tolist() == [1_600_000_002_000, 1_600_000_003_000, 1_600_000_009_000]
    assert st.at([1_600_000_001_999])[0].tolist() == [False]
    assert st.at([1_600_000_002_000])[0].tolist() == [True]


def test_the_sessions_follow_the_new_york_clock_through_dst():
    a, z = TM.s_of("2022-03-10") * 1000, TM.s_of("2022-11-10") * 1000
    kz, ln = B.clock_steps("SESS-KZ", a, z), B.clock_steps("SESS-LN", a, z)

    def on(st, when):
        return bool(st.at([pd.Timestamp(when, tz="UTC").value // 1_000_000])[0][0])
    # winter (EST, UTC-5): 02:00-05:00 NY = 07:00-10:00 UTC, 07:00-11:00 NY = 12:00-16:00 UTC
    assert [on(kz, f"2022-03-11 {h:02d}:00") for h in range(5, 18)] == \
        [False, False, True, True, True, False, False, True, True, True, True, False, False]
    assert on(kz, "2022-03-11 06:59:59.999") is False and on(kz, "2022-03-11 07:00:00") is True
    assert on(kz, "2022-03-11 09:59:59.999") is True and on(kz, "2022-03-11 10:00:00") is False
    # summer (EDT, UTC-4) from Sunday 13 March 2022: an hour earlier in UTC
    assert [on(kz, f"2022-03-14 {h:02d}:00") for h in range(5, 17)] == \
        [False, True, True, True, False, False, True, True, True, True, False, False]
    # the spring-forward Sunday: 02:00 NY does not exist, the session opens at 03:00 EDT = 07:00 UTC
    assert on(kz, "2022-03-13 06:30") is False and on(kz, "2022-03-13 07:00") is True
    # fall back on 6 November 2022: 01:00-02:00 EDT then 01:00 EST; 02:00 EST = 07:00 UTC
    assert on(ln, "2022-11-06 06:30") is False and on(ln, "2022-11-06 07:00") is True
    assert on(ln, "2022-11-07 15:59") is True and on(ln, "2022-11-07 16:00") is False
    assert on(ln, "2022-11-04 14:59") is True and on(ln, "2022-11-04 15:00") is False
    assert (kz.al == kz.as_).all() and (ln.al == ln.as_).all()


def test_the_bar_model_masks_read_the_last_closed_bar():
    bk = _synthetic_book()
    s = bk.sides("SIDE50-H4")
    T = np.concatenate([s.tc - 1, s.tc, s.tc + 60])
    al, ash = bk.masks("SIDE50-H4", T)
    n = len(s.tc)
    assert np.array_equal(al[n:2 * n], s.al) and np.array_equal(al[2 * n:], s.al)
    assert np.array_equal(al[1:n], s.al[:-1]) and not al[0]
    al2, _ = bk.masks("SIDE50-H4&TSI-H1", T)
    assert np.array_equal(al2, al & bk.masks("TSI-H1", T)[0])
    l3, s3 = bk.masks("SESS-KZ", np.asarray([TM.s_of("2019-03-05 12:30"), TM.s_of("2019-03-05 16:30")]))
    assert l3.tolist() == [True, False] and s3.tolist() == [True, False]


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_no_look_ahead_on_real_bars(symbol):
    """Every bar filter's allow series up to T is the same when the M1 bars after T are not loaded (indicator values
    only; nothing after 2024-06-30 is read)."""
    if not has_store(symbol):
        pytest.skip("no tick store")
    full = B.FilterBook(symbol, "2022-07-01")
    for T in ("2021-03-17 13:00", "2022-02-08"):
        cut = B.FilterBook(symbol, T)
        for f in B.single_filters():
            if f.clock or f.family in B.PORTS:
                continue
            a, b = full.sides(f.fid), cut.sides(f.fid)
            k = len(b.tc)
            assert k > 100 and np.array_equal(a.tc[:k], b.tc) and b.tc[-1] <= TM.s_of(T)
            assert np.array_equal(a.al[:k], b.al) and np.array_equal(a.as_[:k], b.as_), (f.fid, T)


def test_stamps_on_a_real_prepare_are_the_kernels_switching_instants():
    """On a per-second prepare of a Development week: an H1 filter switches exactly where the kernel moves its H1
    forming-bar index on (the first row of the next bar), and a D1 filter at the first row of the next merged day."""
    if not has_store("XAUUSDm"):
        pytest.skip("no tick store")
    p = fast.prepare("XAUUSDm", "2022-03-01", "2022-03-08", list(B.TFS_PREP), mode="sec")
    bk = B.FilterBook("XAUUSDm", "2022-03-08")
    s = bk.sides("SIDE50-H1")
    st = bk.steps("SIDE50-H1", p.t_ms)
    rows = p.start_row["H1"]
    first_rows = p.t_ms[rows[rows >= 0]]
    assert set(st.t[1:]).issubset(set(first_rows.tolist()))
    for t_ in st.t[1:]:
        i = np.searchsorted(s.tc * 1000, t_, side="right") - 1         # the bar whose value starts here
        assert s.tc[i] * 1000 <= t_ and not np.any((p.t_ms >= s.tc[i] * 1000) & (p.t_ms < t_))
    d = bk.steps("SIDE50-D1", p.t_ms)
    assert all(pd.Timestamp(int(t_), unit="ms").hour in (0, 23) for t_ in d.t[1:])


# ───────────────────────────── the regime composition ─────────────────────────────

def test_compose_is_the_trend_where_the_filter_allows_that_side():
    tt = np.asarray([100, 200, 300, 400, 500], np.int64)
    tv = np.asarray([1, -1, 1, 0, -1], np.int64)
    st = B.Steps(np.asarray([150, 250, 350, 450], np.int64), np.asarray([True, True, False, True]),
                 np.asarray([True, False, True, True]))
    reg = B.compose((tt, tv), st)
    T = np.arange(50, 700, 5)
    got = B.regime_at(reg, T)
    trend = np.where(np.searchsorted(tt, T, "right") > 0, tv[np.maximum(np.searchsorted(tt, T, "right") - 1, 0)], 0)
    al, ash = st.at(T)
    want = np.where((trend == 1) & al, 1, np.where((trend == -1) & ash, -1, 0))
    assert np.array_equal(got, want)
    assert (got[T < 150] == 0).all()                    # before the filter's first stamp: 0
    assert np.all(np.diff(reg[1]) != 0)                 # only changes are kept
    ident = B.compose((tt, tv), B.ALLOW)
    assert np.array_equal(B.regime_at(ident, T), trend)
    nothing = B.bar_steps(np.asarray([1, 2], np.int64), B.BarSides(np.asarray([10], np.int64), np.array([True]),
                                                                  np.array([True])))
    assert (B.regime_at(B.compose((tt, tv), nothing), T) == 0).all()


def test_and_steps_is_both_filters():
    a = B.Steps(np.asarray([0, 10, 20], np.int64), np.array([True, False, True]), np.array([False, True, True]))
    b = B.Steps(np.asarray([5, 15], np.int64), np.array([True, True]), np.array([True, False]))
    c = B.and_steps(a, b)
    T = np.arange(-5, 30)
    la, sa = a.at(T)
    lb, sb = b.at(T)
    lc, sc = c.at(T)
    assert np.array_equal(lc, la & lb) and np.array_equal(sc, sa & sb)


QUICK = dict(open_weights={"M1": 1}, fc_weights={"M1": 1}, reentry_cooldown_s=5.0, fixed_units=2, initial_balance=1e6,
             rsi_oversold=45.0, rsi_overbought=55.0)


def _run(prepared, cfg, regime=None):
    prep = prepared(cfg.symbol, mode="ticks", tfs=ALL_TFS)
    return fast.run(cfg, prep, regime=regime), prep


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
@pytest.mark.parametrize("trend_tf,mode", [("M1", 1), ("M5", 1), ("H1", 1), ("M1", -1)])
def test_the_always_allow_filter_is_the_design_fill_for_fill(live_cfg, prepared, symbol, trend_tf, mode):
    cfg = live_cfg(symbol, **QUICK, trend_tf=trend_tf, trend_mode=mode)
    base, prep = _run(prepared, cfg)
    trend = B.trend_series(prep, cfg)
    ident, _ = _run(prepared, cfg, B.compose(trend, B.ALLOW))
    assert len(base.fills) > 5
    pd.testing.assert_frame_equal(base.fills.reset_index(drop=True), ident.fills.reset_index(drop=True))
    assert base.counters["polls_entry_blocked_trend"] > 0
    assert ident.counters["polls_entry_blocked_regime"] == base.counters["polls_entry_blocked_trend"]
    assert ident.counters["polls_entry_blocked_trend"] == 0


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
@pytest.mark.parametrize("side", ["long", "short"])
def test_one_sided_steps_are_the_engines_own_side_switches(live_cfg, prepared, symbol, side):
    """The fixture windows trend down: longs are tested with the contrarian trend mode, so that both sides trade."""
    cfg = live_cfg(symbol, **QUICK, trend_tf="M1", trend_mode=-1 if side == "long" else 1)
    base, prep = _run(prepared, cfg)
    st = B.Steps(np.asarray([B.ALWAYS_MS], np.int64), np.array([side == "long"]), np.array([side == "short"]))
    got, _ = _run(prepared, cfg, B.compose(B.trend_series(prep, cfg), st))
    one, _ = _run(prepared, cfg.replace(**{"allow_short" if side == "long" else "allow_long": False}))
    pd.testing.assert_frame_equal(got.fills.reset_index(drop=True), one.fills.reset_index(drop=True))
    assert set(got.baskets["side"]) == {"BUY" if side == "long" else "SELL"}
    # and the opposite side alone is the opposite switch
    other = B.Steps(np.asarray([B.ALWAYS_MS], np.int64), np.array([side != "long"]), np.array([side != "short"]))
    got2, _ = _run(prepared, cfg, B.compose(B.trend_series(prep, cfg), other))
    one2, _ = _run(prepared, cfg.replace(**{"allow_long" if side == "long" else "allow_short": False}))
    pd.testing.assert_frame_equal(got2.fills.reset_index(drop=True), one2.fills.reset_index(drop=True))


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
@pytest.mark.parametrize("mode", [1, -1])
def test_every_basket_opens_where_the_trend_and_the_filter_both_allowed(live_cfg, prepared, symbol, mode):
    cfg = live_cfg(symbol, **QUICK, trend_tf="M1", trend_mode=mode)
    base, prep = _run(prepared, cfg)
    rng = np.random.default_rng(11)
    t0, t1 = int(prep.t_ms[0]), int(prep.t_ms[-1])
    times = np.arange(t0 - 60_000, t1, 150_000, dtype=np.int64)          # switches every 2.5 minutes
    st = B.Steps(times, rng.random(len(times)) < 0.7, rng.random(len(times)) < 0.7)
    trend = B.trend_series(prep, cfg)
    reg = B.compose(trend, st)
    res, _ = _run(prepared, cfg, reg)
    b = res.baskets
    assert len(b) >= 2
    t_open = (b["open_time"].astype("int64") // 1_000_000).to_numpy()
    sides = np.where(b["side"].to_numpy() == "BUY", 1, -1)
    # the order is decided on a poll and filled a moment later: read the regime just before the fill
    in_force = B.regime_at(reg, t_open - 1)
    near = np.abs(t_open[:, None] - np.union1d(reg[0], trend[0])[None, :]).min(axis=1) < 2000
    assert (in_force[~near] == sides[~near]).all()
    al, ash = st.at(t_open - 1)
    ok = np.where(sides > 0, al, ash)
    assert ok[~near].all()
    # the regime is the trend or 0, and it is checked first: the trend gate itself never fires any more
    assert res.counters["polls_entry_blocked_regime"] > 0 and res.counters["polls_entry_blocked_trend"] == 0


@pytest.mark.parametrize("workers", [1, 2])
def test_the_runner_wiring_on_the_fixture_store(tmp_path, monkeypatch, fixture_store, workers):
    """``run_sec_stage`` end to end on the fixture store (BTC Top 2's configuration, the one-hour BTC window, where
    it keeps wanting to enter against the trend): the filter's steps come from a stand-in FilterBook (synthetic steps,
    not a study-3 filter), and the variant's account must be the engine's own run with ``compose(trend, steps)``; the
    base is the plain run; resume skips what is there."""
    a, z = "2026-11-09 06:00", "2026-11-09 07:00"
    w = B.Window("dev", "fixture", "fix", a, z, True)
    t0 = TM.s_of(a) * 1000
    steps = B.Steps(np.arange(t0 - 60_000, t0 + 3_600_000, 240_000, dtype=np.int64),
                    np.resize(np.array([True, False, True]), 16), np.resize(np.array([True, True, False]), 16))

    class FakeBook:
        history_from = "synthetic"

        def __init__(self, *a, **k):
            pass

        def steps(self, fid, t_ms):
            return steps

    monkeypatch.setattr(B, "FilterBook", FakeBook)
    sink, daily = tmp_path / "dev.csv", tmp_path / "daily.csv"
    rows = B.run_sec_stage("btc_top2", [B.BASE, "TSI-H1"], [w], sink, daily, workers=workers,
                           store_dir=fixture_store, log=lambda *x: None)
    prep = fast.prepare("BTCUSDm", a, z, list(B.TFS_PREP), mode="sec", store_dir=fixture_store)
    cfg = B.design_cfg("btc_top2", a, z)
    want = fast.run(cfg, prep, regime=B.compose(B.trend_series(prep, cfg), steps))
    plain = fast.run(cfg, prep)
    r = rows.set_index("vid")
    assert r.loc["TSI-H1", "final_equity"] == round(float(want.scalars["final_equity"]), 6)
    assert r.loc["TSI-H1", "blocked_regime"] == want.counters["polls_entry_blocked_regime"] > 0
    assert r.loc["TSI-H1", "history_from"] == "synthetic" and r.loc["TSI-H1", "kind"] == "single"
    assert r.loc[B.BASE, "final_equity"] == round(float(plain.scalars["final_equity"]), 6)
    assert r.loc[B.BASE, "blocked_regime"] == 0 and r.loc[B.BASE, "blocked_trend"] == plain.counters[
        "polls_entry_blocked_trend"] > 0
    # the regime is the trend or 0: it blocks at least every poll the trend gate blocked
    assert r.loc["TSI-H1", "blocked_regime"] >= r.loc[B.BASE, "blocked_trend"]
    assert set(B.read_daily(daily)["vid"]) == {B.BASE, "TSI-H1"}
    n = len(pd.read_csv(sink))
    B.run_sec_stage("btc_top2", [B.BASE, "TSI-H1"], [w], sink, daily, workers=workers, store_dir=fixture_store,
                    log=lambda *x: None)
    assert len(pd.read_csv(sink)) == n                                # resumed: nothing ran again


def test_the_raw_tick_runner_on_the_fixture_store(tmp_path, monkeypatch, fixture_store):
    """``run_tick_stage`` (the confirmation's format) on the fixture store: one raw-tick prepare for the window, the
    regime composed on that prepare's own rows and trend, every (variant, timing) once, the timing's own jitter; the
    median per quarter comes from these rows. Synthetic steps again, not a study-3 filter."""
    from backtesting.analysis.robustness import live_timing
    a, z = "2026-11-09 06:00", "2026-11-09 07:00"
    w = B.Window("dev", "fixture", "fix", a, z)
    t0 = TM.s_of(a) * 1000
    steps = B.Steps(np.arange(t0 - 60_000, t0 + 3_600_000, 300_000, dtype=np.int64),
                    np.resize(np.array([True, False]), 13), np.resize(np.array([True, True, False]), 13))

    class FakeBook:
        history_from = "synthetic"

        def __init__(self, *a, **k):
            pass

        def steps(self, fid, t_ms):
            return steps

    monkeypatch.setattr(B, "FilterBook", FakeBook)
    sink = tmp_path / "confirm.csv"
    rows = B.run_tick_stage("btc_top2", [B.BASE, "TSI-H1"], [w], sink, workers=2, seeds=(1, 2), store_dir=fixture_store,
                            log=lambda *x: None)
    assert len(rows) == 4 and set(rows["mode"]) == {"ticks"} and sorted(set(rows["seed"])) == [1, 2]
    prep = fast.prepare("BTCUSDm", a, z, list(B.TFS_PREP), mode="ticks", store_dir=fixture_store)
    for sd in (1, 2):
        cfg = B.design_cfg("btc_top2", a, z, extra=live_timing(sd))
        reg = B.compose(B.trend_series(prep, cfg), steps)
        r = rows[(rows.vid == "TSI-H1") & (rows.seed == sd)].iloc[0]
        want = fast.run(cfg, prep, light=True, regime=reg)
        assert r["final_equity"] == round(float(want.scalars["final_equity"]), 6)
        assert r["blocked_regime"] == want.counters["polls_entry_blocked_regime"]
        b = rows[(rows.vid == B.BASE) & (rows.seed == sd)].iloc[0]
        assert b["blocked_trend"] == fast.run(cfg, prep, light=True).counters["polls_entry_blocked_trend"]
    q = B.quarter_table(rows, [w])
    assert (q["runs"] == 2).all() and len(q) == 2
    B.run_tick_stage("btc_top2", [B.BASE, "TSI-H1"], [w], sink, workers=2, seeds=(1, 2), store_dir=fixture_store,
                     log=lambda *x: None)
    assert len(pd.read_csv(sink)) == 4                                # resumed


def test_the_trend_series_needs_a_trend_timeframe(live_cfg, prepared):
    cfg = live_cfg("XAUUSDm", **QUICK)
    prep = prepared("XAUUSDm", mode="ticks", tfs=ALL_TFS)
    with pytest.raises(ValueError):
        B.trend_series(prep, cfg.replace(trend_tf=None))


def test_the_designs_all_gate_on_the_h1_trend():
    for key, d in B.DESIGNS.items():
        if d.engine == "ticks":
            cfg = B.design_cfg(key, "2021-01-01", "2021-02-01")
            assert cfg.trend_tf == "H1" and cfg.trend_mode == 1 and cfg.record_interval_s == 3600
            assert set(cfg.timeframes()) <= set(B.TFS_PREP)


# ───────────────────────────── the Turtle ─────────────────────────────

def _turtle_market(seed: int = 5, days: int = 260):
    """Hand-made BTC M1 bars: trending legs (breakouts of the 55-day channel both ways) with noise."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    t = TM.s_of("2019-01-07") + 60 * np.arange(n, dtype=np.int64)
    drift = np.repeat(rng.choice([-1.0, 1.0], days // 30 + 1), 30 * 1440)[:n] * 0.1
    c = 10000.0 + np.cumsum(drift + rng.normal(0, 3.0, n))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0, 3, n)
    lo = np.minimum(o, c) - rng.uniform(0, 3, n)
    m = X.Market("BTCUSDm", {"t": t, "o": o, "h": h, "l": lo, "c": c, "spread_mean": np.full(n, 5.0),
                             "n": np.full(n, 10.0)})
    plan = X.turtle(m, 2).plan
    plan = plan.copy(m_l=np.ones(len(m), bool), m_s=np.ones(len(m), bool))
    return m, plan


def test_the_turtle_gates_block_first_fills_only():
    m, plan = _turtle_market()
    p0 = X.run_path(m, plan, 0, len(m))
    assert len(p0) >= 4 and (p0.nleg > 1).any() and set(p0.dir) == {1, -1}
    ones_dt, ones_m = np.ones(len(plan), bool), np.ones(len(m), bool)
    same = B.turtle_gate(plan, m, ones_dt, ones_dt, ones_m, ones_m)
    assert B.same_path(p0, X.run_path(m, same, 0, len(m)))
    no_long = B.turtle_gate(plan, m, ones_dt, ones_dt, np.zeros(len(m), bool), ones_m)
    p1 = X.run_path(m, no_long, 0, len(m))
    assert set(p1.dir) == {-1} and (p1.nleg > 1).any()              # shorts keep their pyramid adds
    # a gate closed only on bars where a long's add happens leaves that long and its adds alone
    j = int(np.flatnonzero((p0.dir == 1) & (p0.nleg > 1))[0])
    legs = p0.leix[p0.leg0[j] + 1:p0.leg0[j] + p0.nleg[j]]
    m_l = ones_m.copy()
    m_l[legs] = False
    p2 = X.run_path(m, B.turtle_gate(plan, m, ones_dt, ones_dt, m_l, ones_m), 0, len(m))
    assert p2.eix[j] == p0.eix[j] and p2.nleg[j] == p0.nleg[j]


def test_the_exit_overlay_without_flags_or_with_inert_flags_is_the_turtle():
    m, plan = _turtle_market()
    h4 = X.tf_bars(m, 14400)
    for a_ix, z_ix in ((0, len(m)), (60 * 1440 + 77, 200 * 1440)):
        p0 = X.run_path(m, plan, a_ix, z_ix)
        empty = B.turtle_exit_plan(plan, m, np.zeros(0, np.int64), np.zeros(0, bool), np.zeros(0, bool), a_ix, z_ix)
        assert B.same_path(p0, X.run_path(m, empty, a_ix, z_ix))
        xl, xs = B.inert_flags(m, p0, h4.tc)
        full = B.turtle_exit_plan(plan, m, h4.tc, xl, xs, a_ix, z_ix)
        assert len(full) - len(plan) > 1000                          # a new row at nearly every H4 close
        assert B.same_path(p0, X.run_path(m, full, a_ix, z_ix))


def _crafted(moves, days=2):
    """M1 bars of a 24/7 market flat at 100 (bid; spread 0.1), with ``moves`` = {bar: (open, high, low, close)} and
    the level after each move held until the next one."""
    n = days * 1440
    t = TM.s_of("2019-02-04") + 60 * np.arange(n, dtype=np.int64)
    lvl = np.full(n, 100.0)
    o, h, lo, c = lvl.copy(), lvl + 0.05, lvl - 0.05, lvl.copy()
    for i in sorted(moves):
        mo, mh, ml, mc = moves[i]
        o[i], h[i], lo[i], c[i] = mo, mh, ml, mc
        o[i + 1:], c[i + 1:], h[i + 1:], lo[i + 1:] = mc, mc, mc + 0.05, mc - 0.05
    return X.Market("BTCUSDm", {"t": t, "o": o, "h": h, "l": lo, "c": c, "spread_mean": np.full(n, 0.1),
                                "n": np.full(n, 10.0)})


def test_a_fill_cancels_the_days_orders_and_an_h4_exit_keeps_the_turtle_out_until_its_next_decision():
    # 1. a buy stop fills at 100.5, the 1.0 stop is hit, the price comes back through 100.5 the same day: the base
    #    does not re-enter (one fill cancels both orders until the next decision); a new row at 04:00 must not re-arm
    m = _crafted({60: (100.0, 100.8, 99.95, 100.7), 120: (100.7, 100.75, 99.3, 99.4), 300: (99.4, 100.9, 99.35, 100.8)})
    plan = X.make_plan(m, m.t[:1], bstop=np.array([100.5]), sl=np.array([1.0]), orders=True)
    p0 = X.run_path(m, plan, 0, len(m))
    assert len(p0) == 1 and p0.eix[0] == 60 and p0.xix[0] == 120 and p0.why[0] == X.WHY_STOP
    tc, xl, xs = m.t[240:241], np.array([True]), np.array([True])        # flat at 04:00: an inert flag
    with pytest.raises(RuntimeError):
        B.turtle_exit_plan(plan, m, tc, xl, xs, 0, len(m), max_iter=1)  # the first pass re-arms and refills at 300
    assert B.same_path(p0, X.run_path(m, B.turtle_exit_plan(plan, m, tc, xl, xs, 0, len(m)), 0, len(m)))
    # 2. a long from day 0 is still open when day 1's decision arms a buy stop at 101.5; an H4 flag at 02:00 closes it
    #    at the next open; the price then crosses 101.5: the Turtle stays out until its next decision
    m = _crafted({60: (100.0, 100.8, 99.95, 100.7), 1600: (100.7, 101.8, 100.65, 101.7)})
    plan = X.make_plan(m, m.t[[0, 1440]], bstop=np.array([100.5, 101.5]), sl=np.array([5.0, 5.0]), orders=True)
    p0 = X.run_path(m, plan, 0, len(m))
    assert len(p0) == 1 and p0.eix[0] == 60 and p0.why[0] == X.WHY_END
    tc, xl, xs = m.t[1560:1561], np.array([True]), np.array([False])
    with pytest.raises(RuntimeError):
        B.turtle_exit_plan(plan, m, tc, xl, xs, 0, len(m), max_iter=1)
    p = X.run_path(m, B.turtle_exit_plan(plan, m, tc, xl, xs, 0, len(m)), 0, len(m))
    assert len(p) == 1 and p.eix[0] == 60 and p.xix[0] == 1560 and p.why[0] == X.WHY_SIGNAL and p.xpx[0] == 100.7
    # the same flag on day 1's own decision row (a D1 flag): the exit is at that row, and its orders stay armed
    p = X.run_path(m, B.turtle_exit_plan(plan, m, m.t[1440:1441], xl, xs, 0, len(m)), 0, len(m))
    assert p.xix[0] == 1440 and p.why[0] == X.WHY_SIGNAL and len(p) == 2 and p.eix[1] == 1600


def test_an_h4_flip_closes_the_position_at_the_next_open_and_the_turtle_waits_for_its_next_decision():
    m, plan = _turtle_market()
    p0 = X.run_path(m, plan, 0, len(m))
    h4 = X.tf_bars(m, 14400)
    j = int(np.flatnonzero(p0.dir == 1)[0])
    e, x = int(p0.eix[j]), int(p0.xix[j])
    k = int(np.flatnonzero((h4.ex > e + 300) & (h4.ex < x) & (h4.tc % 86400 != 0))[0])   # an H4 close inside it
    xl = np.zeros(len(h4), bool)
    xl[k] = True
    p = X.run_path(m, B.turtle_exit_plan(plan, m, h4.tc, xl, np.zeros(len(h4), bool), 0, len(m)), 0, len(m))
    i = int(np.flatnonzero(p.eix == e)[0])
    assert p.xix[i] == h4.ex[k] and p.why[i] == X.WHY_SIGNAL and p.xpx[i] == m.o[h4.ex[k]]
    nxt = plan.dx[plan.dx > h4.ex[k]][0]                                # the next D1 decision's execution bar
    assert not np.any((p.eix > h4.ex[k]) & (p.eix < nxt))               # flat until then
    assert np.array_equal(p.eix[:i + 1], p0.eix[:i + 1])                # nothing before the flip changed
    # the same flag as a D1 flag on the day's own decision row exits there
    d = int(np.flatnonzero((plan.dx > e + 1440) & (plan.dx < x))[0])
    q = X.run_path(m, B.turtle_exit_plan(plan, m, plan.dt[d:d + 1], np.array([True]), np.array([False]), 0, len(m)),
                   0, len(m))
    i = int(np.flatnonzero(q.eix == e)[0])
    assert q.xix[i] == plan.dx[d] and q.why[i] == X.WHY_SIGNAL


def test_the_exit_flags_on_closed_bars_through_the_ha_port(monkeypatch):
    """HA-M1 / HA-M4 flags from the port's colour (a stand-in port here: the textbook candles), on complete bars;
    M4 takes the port's own rare-age series when it has one."""
    import types

    def heikin_ashi(o, h, l, c):
        hc = (np.asarray(o) + h + l + c) / 4.0
        ho = np.empty(len(hc))
        ho[0] = (o[0] + c[0]) / 2.0
        for i in range(1, len(hc)):
            ho[i] = (ho[i - 1] + hc[i - 1]) / 2.0
        return {"dir": np.where(hc >= ho, 1, -1)}
    fake = types.SimpleNamespace(heikin_ashi=heikin_ashi)
    real = B._port
    monkeypatch.setattr(B, "_port", lambda fam: fake if fam == "HA" else real(fam))
    bk = _synthetic_book(days=200)
    for tf in ("H4", "D1"):
        b = bk.bars(tf)
        d = heikin_ashi(b.o, b.h, b.l, b.c)["dir"].astype(float)
        tc, xl, xs = B.exit_flags(bk, f"HA-M1-{tf}")
        fl, fs = B.ha_flips(d)
        assert np.array_equal(tc, b.tc[b.complete]) and np.array_equal(xl, fl) and np.array_equal(xs, fs)
        assert xl.sum() > 10 and not (xl & xs).any()
        tc, xl, xs = B.exit_flags(bk, f"HA-M4-{tf}")
        r = B.rare_age(d)
        assert np.array_equal(xl, r & (d > 0)) and np.array_equal(xs, r & (d < 0))
    assert B.exit_flags(bk, "HA-M4-H4")[1].sum() > 0
    marks = np.zeros(len(bk.bars("D1")), bool)
    marks[[3, 7]] = True
    fake.heikin_ashi = lambda o, h, l, c: {**heikin_ashi(o, h, l, c), "rare_now": marks if len(o) == len(marks)
                                           else np.zeros(len(o), bool)}
    bk2 = _synthetic_book(days=200)
    _, xl, xs = B.exit_flags(bk2, "HA-M4-D1")
    assert np.flatnonzero(xl | xs).tolist() == [3, 7]


def test_heikin_ashi_flips_and_the_rare_age():
    d = np.array([1, 1, -1, -1, 1, -1, 1, 1, 1], float)
    xl, xs = B.ha_flips(d)
    assert xl.tolist() == [False, False, True, False, False, True, False, False, False]
    assert xs.tolist() == [False, False, False, False, True, False, True, False, False]
    # ten bullish streaks of lengths 1..10 (bearish streaks of 1 in between), then a long bullish streak
    seq = []
    for L in range(1, 11):
        seq += [1] * L + [-1]
    seq += [1] * 12
    r = B.rare_age(np.array(seq, float), pct=90.0, min_n=10)
    tail = r[-12:]
    # finished bullish lengths 1..10: pctBelow(a) = 10 * (a - 1); it first reaches 90 at age 10
    assert tail.tolist() == [False] * 9 + [True] + [False] * 2
    assert not r[:-12].any()
    assert not B.rare_age(np.array(seq, float), pct=90.0, min_n=11).any()      # too few finished streaks
    # the bearish list holds ten streaks of 1: pctBelow(1) = 0 and pctBelow(2) = 100, so age 2 is rare at once
    assert B.rare_age(np.array(seq + [-1, -1, -1], float), pct=90.0, min_n=10)[-3:].tolist() == [False, True, False]


# ───────────────────────────── the score ─────────────────────────────

def _q(vid, nets, dds, wiped=()):
    return pd.DataFrame({"vid": vid, "window": [w.name for w in B.DEV_QUARTERS], "net": nets, "max_dd_pct": dds,
                         "trades": 10, "wiped": [w.name in wiped for w in B.DEV_QUARTERS]})


def test_the_yardstick_is_final10s():
    rng = np.random.default_rng(1)
    nets, dds = rng.normal(50, 100, 23), rng.uniform(2, 30, 23)
    q = B.quarter_table(_q("BASE", nets, dds))
    Y = B.yardstick(q, n_quarters=23).iloc[0]
    per = {p: np.mean([n for n, w in zip(nets, B.DEV_QUARTERS) if w.period == p]) for p in B.P5}
    assert all(math.isclose(Y[p], per[p]) for p in B.P5)
    assert math.isclose(Y["mean_q"], np.mean(list(per.values())))
    assert math.isclose(Y["dd_fresh"], dds.max()) and math.isclose(Y["score"], Y["mean_q"] / dds.max())
    assert Y["periods_up"] == sum(v > 0 for v in per.values())
    assert bool(Y["eligible"]) == (Y["periods_up"] >= 4 and Y["mean_q"] > 0 and dds.max() <= 50)
    small = B.yardstick(B.quarter_table(_q("X", np.full(23, 1.0), np.full(23, 0.4))), n_quarters=23).iloc[0]
    assert math.isclose(small["score"], 1.0)                       # the drawdown is floored at 1%
    with pytest.raises(ValueError):
        B.yardstick(B.quarter_table(_q("X", nets, dds).iloc[:-1]), n_quarters=23)


def test_the_median_of_eight_timings_per_quarter():
    rows = []
    for sd in range(1, 9):
        rows.append(_q("V", np.arange(23) + sd, np.full(23, 10.0 + sd), wiped=("H3",) if sd == 8 else ()).assign(seed=sd))
    q = B.quarter_table(pd.concat(rows))
    assert (q["runs"] == 8).all()
    assert np.allclose(q["net"], np.arange(23) + 4.5) and np.allclose(q["dd"], 14.5)
    assert q.set_index("window").loc["H3", "wiped"] and q["wiped"].sum() == 1


def _table(spec):
    """vid -> (period values, dd, wiped): a yardstick-like table."""
    rows = []
    for vid, (vals, dd, wiped) in spec.items():
        r = dict(vid=vid, **dict(zip(B.P5, vals)), dd_fresh=dd, wiped=wiped)
        r["periods_up"] = sum(v > 0 for v in vals)
        r["mean_q"] = float(np.mean(vals))
        r["score"] = r["mean_q"] / max(dd, 1.0)
        r["kind"] = B.Variant(vid).kind
        rows.append(r)
    return pd.DataFrame(rows)


def test_better_needs_score_periods_the_profit_floor_and_no_wipe():
    Y = _table({"BASE": ([100, 100, 100, 100, 100], 20.0, False),
                "SIDE50-H1": ([95, 95, 95, 95, 95], 10.0, False),       # better
                "SIDE100-H1": ([80, 80, 80, 80, 80], 5.0, False),       # higher score, but below the 90% floor
                "SIDE200-H1": ([200, 200, 200, 200, -1], 18.0, False),  # one period fewer up
                "TSI-H1": ([95, 95, 95, 95, 95], 10.0, True),           # wiped
                "TSI-H4": ([400, 400, 400, 400, 400], 60.0, False),     # a higher score, but DD above 50%
                "TSI-D1": ([90, 90, 90, 90, 90], 9.0, False),           # exactly 90%: allowed
                "LARSI-H1": ([110, 110, 110, 110, 110], 22.0, False)})  # same score: not higher
    Y = B.mark_better(Y)
    got = dict(zip(Y["vid"], Y["better"]))
    assert got == {"BASE": False, "SIDE50-H1": True, "SIDE100-H1": False, "SIDE200-H1": False, "TSI-H1": False,
                   "TSI-H4": False, "TSI-D1": True, "LARSI-H1": False}
    assert math.isclose(B.profit_floor(100.0), 90.0) and B.profit_floor(-50.0) == -50.0 and B.profit_floor(0.0) == 0.0
    assert B.meets_floor(90.0, 100.0) and not B.meets_floor(89.999, 100.0) and B.meets_floor(-50.0, -50.0)
    assert B.candidates(Y) == ["TSI-D1", "SIDE50-H1"]


def test_candidates_pairs_and_finalists():
    spec = {"BASE": ([10] * 5, 10.0, False)}
    for i, fid in enumerate(["SIDE50-H1", "SLOPE50-H1", "TSI-D1", "QQE-H4", "HA-D1"]):
        spec[fid] = ([10 + i] * 5, 10.0 - i, False)                 # rising scores
    spec["SIDE50-H1&TSI-D1"] = ([30] * 5, 3.0, False)
    Y = _table(spec)
    assert B.candidates(Y) == ["SIDE50-H1&TSI-D1", "HA-D1", "QQE-H4"]
    assert B.stage2_pairs(Y) == [B.pair_vid("HA-D1", "QQE-H4"), B.pair_vid("HA-D1", "TSI-D1"),
                                 B.pair_vid("QQE-H4", "TSI-D1")]
    few = _table({"BASE": ([10] * 5, 1.0, False), "SIDE50-H1": ([20] * 5, 1.0, False),
                  "SIDE50-H4": ([5] * 5, 1.0, False)})
    assert B.stage2_pairs(few) == []                                 # only one filter beats the base
    # finalists: confirmed candidates (still better in the confirmation format), the two best
    Yc = _table({"BASE": ([10] * 5, 10.0, False), "SIDE50-H1&TSI-D1": ([12] * 5, 9.0, False),
                 "HA-D1": ([5] * 5, 4.0, False), "QQE-H4": ([11] * 5, 6.0, False)})
    assert B.finalists(["SIDE50-H1&TSI-D1", "HA-D1", "QQE-H4"], Yc) == ["QQE-H4", "SIDE50-H1&TSI-D1"]
    assert B.finalists(["EXIT:HA-M1-D1", "HA-D1", "QQE-H4"], None) == ["EXIT:HA-M1-D1", "HA-D1"]


def test_the_exam_rule_and_verdict():
    base = {"score": 2.0, "mean_q": 100.0}
    assert B.exam_pass({"score": 2.0, "mean_q": 90.0}, base)
    assert not B.exam_pass({"score": 1.99, "mean_q": 200.0}, base)
    assert not B.exam_pass({"score": 3.0, "mean_q": 89.0}, base)
    neg = {"score": -1.0, "mean_q": -20.0}
    assert B.exam_pass({"score": -0.5, "mean_q": -20.0}, neg) and not B.exam_pass({"score": -0.5, "mean_q": -21.0}, neg)
    rows = []
    for name, (qs, _) in B.exam_windows("XAUUSDm").items():
        for vid, net, dd in (("BASE", 50.0, 10.0), ("TSI-H4", 60.0, 8.0), ("QQE-D1", 40.0, 10.0)):
            for sd in range(1, 9):
                rows += [dict(vid=vid, window=w.name, net=net + sd, max_dd_pct=dd, trades=5, wiped=False, seed=sd,
                              mode="ticks") for w in qs]
    v = B.exam_verdict("xau_v3lite", pd.DataFrame(rows), ["TSI-H4", "QQE-D1"]).set_index("vid")
    assert v.loc["TSI-H4", "passes"] and v.loc["TSI-H4", "t1_pass"] and v.loc["TSI-H4", "t2_pass"]
    assert not v.loc["QQE-D1", "passes"]
    assert math.isclose(v.loc["TSI-H4", "t1_score"], (60 + 4.5) / 8.0)


# ───────────────────────────── results files and multiple testing ─────────────────────────────

def test_results_files_resume_and_keep_the_last_row(tmp_path):
    sink = tmp_path / "dev.csv"
    w = B.DEV_WINDOWS
    rows = [dict(design="xau_v3lite", vid="BASE", stage="dev", window=x.name, period=x.period, mode="sec", seed=0,
                 net=1.0) for x in w]
    B._append(sink, rows[:10])
    assert B._done(B.read_rows(sink), w, "sec") == set()
    B._append(sink, rows)
    B._append(sink, [dict(rows[0], net=5.0)])
    r = B.read_rows(sink)
    assert B._done(r, w, "sec") == {"BASE"} and len(r) == 24 and r.loc[r.window == "H1", "net"].item() == 5.0
    assert list(pd.read_csv(sink).columns) == B.COLUMNS


def test_the_selection_pipeline_from_the_results_files_to_the_freeze(tmp_path, closed_guard):
    """Hand-made results files for one tick design: Development (per second), the confirmation (8 timings), the 5-year
    daily equity; ``choose`` picks the candidates and the confirmed finalists, ``freeze_choice`` writes them, and
    ``run_multiple_testing`` reads the same files."""
    rng = np.random.default_rng(9)
    key = "xau_v3lite"
    spec = {"BASE": (40.0, 10.0), "ALLOW": (40.0, 10.0), "SIDE200-D1": (45.0, 8.0), "TSI-H4": (38.0, 6.0),
            "QQE-D1": (20.0, 2.0), "HA-H1": (60.0, 40.0)}
    dev, conf, daily = [], [], []
    for vid, (net, dd) in spec.items():
        for w in B.DEV_QUARTERS:
            dev.append(dict(design=key, vid=vid, stage="dev", window=w.name, period=w.period, mode="sec", seed=0,
                            net=net, final_equity=2000 + net, max_dd_pct=dd, trades=9, wiped=False))
            for sd in B.SEEDS:
                conf.append(dict(design=key, vid=vid, stage="dev", window=w.name, period=w.period, mode="ticks",
                                 seed=sd, net=net * (0.9 if vid == "TSI-H4" else 1.0), final_equity=2000 + net,
                                 max_dd_pct=dd, trades=9, wiped=False))
        dev.append(dict(design=key, vid=vid, stage="dev", window="5y", period="5y", mode="sec", seed=0, net=900.0,
                        final_equity=2900.0, max_dd_pct=dd, trades=100, wiped=False))
        eq = 2000 + np.cumsum(rng.normal(0.5, 5, 300))
        daily += [dict(design=key, vid=vid, window="5y", date=str(d.date()), equity=e)
                  for d, e in zip(pd.date_range("2021-11-13", periods=300), eq)]
    sink, dsink = B.dev_paths(key, tmp_path)
    B._append(sink, [r for r in dev if r["vid"] != "QQE-D1"])
    B._append(sink, [r for r in dev if r["vid"] == "QQE-D1"][:5])          # an unfinished variant is not scored
    B._append(tmp_path / f"confirm_{key}.csv", [r for r in conf if r["vid"] in ("BASE", "SIDE200-D1", "TSI-H4")])
    B._append(dsink, daily, ["design", "vid", "window", "date", "equity"])
    Y = B.score_dev(key, tmp_path)
    assert set(Y["vid"]) == {"BASE", "ALLOW", "SIDE200-D1", "TSI-H4", "HA-H1"}
    ch = B.choose(tmp_path, [key])[key]
    assert ch["candidates"] == ["TSI-H4", "SIDE200-D1"]                    # HA-H1: DD 40 gives a lower score
    assert ch["finalists"] == ["SIDE200-D1"]                               # TSI-H4 falls below the floor confirmed
    f = B.freeze_choice({key: ch}, closed_guard)
    assert "`SIDE200-D1`" in f.read_text() and B.finalists_frozen()
    mt = B.run_multiple_testing(tmp_path, [key], B_=200)
    assert set(mt["role"]) == {"best 5y daily Sharpe", "best Development score"} and (mt["N"] == 3).all()
    # a confirmation that misses a timing is refused
    B._append(tmp_path / f"confirm_{key}.csv", [dict(r, seed=9) for r in conf if r["vid"] == "BASE"][:1])
    with pytest.raises(ValueError):
        B.score_confirm(key, tmp_path)


def test_no_variant_runs_unless_the_identity_filter_equals_the_base():
    w = B.DEV_WINDOWS
    rows = [dict(vid=v, window=x.name, final_equity=2000.0 + i, max_dd_pct=1.5, trades=3, wiped=False)
            for v in (B.BASE, B.IDENTITY) for i, x in enumerate(w)]
    assert B.check_identity(pd.DataFrame(rows)) == 24
    bad = pd.DataFrame(rows)
    bad.loc[(bad.vid == B.IDENTITY) & (bad.window == "C3"), "trades"] = 4
    with pytest.raises(B.IdentityError, match="C3"):
        B.check_identity(bad)
    with pytest.raises(B.IdentityError):
        B.check_identity(pd.DataFrame(rows[:-1]))


def test_multiple_testing_uses_the_tradeiq_bootstrap_on_differences_against_the_base():
    from backtesting.research.tradeiq import bootstrap_pvalues
    rng = np.random.default_rng(4)
    days = pd.date_range("2021-11-13", periods=400, freq="D")
    base = 2000 + np.cumsum(rng.normal(1, 10, 400))
    rows = [dict(design="x", vid="BASE", window="5y", date=d, equity=e) for d, e in zip(days, base)]
    eq = {}
    for i, vid in enumerate(["SIDE50-H1", "TSI-D1", "QQE-H4"]):
        eq[vid] = 2000 + np.cumsum(rng.normal(1 + 0.3 * i, 9, 400))
        rows += [dict(design="x", vid=vid, window="5y", date=d, equity=e) for d, e in zip(days, eq[vid])]
    rows += [dict(design="x", vid="ALLOW", window="5y", date=d, equity=e) for d, e in zip(days, base)]
    daily = pd.DataFrame(rows)
    mt = B.multiple_testing("x", daily, B_=300)
    vids = ["SIDE50-H1", "TSI-D1", "QQE-H4"]
    E = np.column_stack([base] + [eq[v] for v in vids])
    D = np.diff(E, axis=0)[:, 1:] - np.diff(E, axis=0)[:, :1]
    bp = bootstrap_pvalues(D, B_=300, block=8.0 * 399 / ((days[-1] - days[0]).days / 7.0), seed=20261128)
    r = mt.iloc[0]
    assert r["N"] == 3 and r["T_days"] == 399 and math.isclose(r["spa_p"], bp["spa_p"])
    assert r["spa_best_vid"] == vids[bp["spa_best"]]
    R = np.diff(E, axis=0)[:, 1:] / E[:-1, 1:]
    sr = R.mean(axis=0) / R.std(axis=0, ddof=1)
    assert r["vid"] == vids[int(np.argmax(sr))] and math.isclose(r["sr_daily"], sr.max())
    assert 0.0 <= r["dsr"] <= 1.0


# ───────────────────────────── the published numbers ─────────────────────────────

def test_the_published_five_year_accounts():
    want = {"xau_v3lite": 10747.58, "xau_top1": 12433.38, "xau_top2": 8879.85, "btc_top2": 3918.63, "btc_turtle": 3546.56}
    for k, v in want.items():
        assert B.published_5y(k)["final_equity"] == v
    t = B.published_5y("btc_turtle")
    assert round(t["max_dd_pct"], 2) == 38.40 and t["trades"] == 41


@pytest.mark.slow
@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_the_identity_filter_reproduces_the_published_five_year_accounts(tmp_path, symbol):
    """(about 5 GB for gold, 8 GB for BTC: run alone) PREREG 2's identity check on the real store."""
    if not has_store(symbol):
        pytest.skip("no tick store")
    d = B.identity_ticks(symbol, tmp_path, full=False)
    assert d["equals_published"].all() and d["fills_identical"].all()
    assert (d["allow_final"] == d["base_final"]).all() and (d["allow_trades"] == d["published_trades"]).all()


@pytest.mark.slow
def test_the_turtle_identity_on_the_bar_model(tmp_path):
    if not has_store("BTCUSDm"):
        pytest.skip("no tick store")
    d = B.identity_turtle(tmp_path)
    for _, r in d.iterrows():
        assert r["final"] == r["published_final"] and r["trades"] == r["published_trades"]
        assert round(r["dd"], 2) == round(r["published_dd"], 2)
    assert (d["gate_identical_windows"] == 24).all() and (d["empty_overlay_identical_windows"] == 24).all()
    assert (d["inert_h4_overlay_identical_windows"] == 24).all()
