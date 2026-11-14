"""
The tick store and the data preparation (``backtesting/data/store.py``, ``fast.prepare``).

Every number a backtest produces starts here: ticks are bucketed into bars, reduced to
one row per second, sliced to the requested window and joined to M1 warm-up history.
A mistake at this level does not crash anything -- it silently shifts a bar boundary,
drops a tick or lets a bar's final close leak into polls that happen before it -- so
each step is checked against a brute-force restatement of what it should do.

MT5 conventions the live bot sees and these tests protect:
  * bars are built from BID prices on plain UTC boundaries (Exness server time = UTC+0);
  * a bar exists only where a tick exists; its close is the last tick's Bid;
  * a window is [start, end): start inclusive, end exclusive.
"""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.config import BacktestConfig, TF_SECONDS
from backtesting.data import store
from backtesting.engine import fast

SYMBOLS = ("XAUUSDm", "BTCUSDm")
BAR_KEYS = ("t", "o", "h", "l", "c", "ask_c", "spread_mean", "spread_max", "n")


# ───────────────────────────── helpers ─────────────────────────────

def random_ticks(seed: int, n: int = 6000, mean_gap_ms: float = 4000.0, start="2026-03-06 21:30"):
    """
    Random but realistic ticks: irregular spacing, bursts with identical millisecond
    stamps, ticks exactly on second / minute / hour boundaries, a multi-hour hole and a
    weekend-sized hole.
    """
    rng = np.random.default_rng(seed)
    gaps = rng.exponential(mean_gap_ms, n).astype(np.int64)
    gaps[rng.random(n) < 0.08] = 0                                  # same-millisecond bursts
    gaps[n // 3] += 5 * 3600 * 1000                                 # a quiet stretch
    gaps[2 * n // 3] += 49 * 3600 * 1000                            # a weekend
    t = store.to_ms(start) + np.cumsum(gaps)
    snap = rng.random(n)
    t = np.where(snap < 0.03, (t // 1000) * 1000, t)                # exactly on a second
    t = np.where((snap >= 0.03) & (snap < 0.045), (t // 60_000) * 60_000, t)     # ... a minute
    t = np.where((snap >= 0.045) & (snap < 0.05), (t // 3_600_000) * 3_600_000, t)  # ... an hour
    t = np.sort(t).astype(np.int64)
    bid = np.round(4000.0 + np.cumsum(rng.normal(0.0, 0.08, n)), 3)
    ask = np.round(bid + rng.choice([0.16, 0.2, 0.24, 0.5, 1.1], n), 3)
    return t, bid, ask


def brute_force_bars(t_ms, bid, ask, tf_s: int) -> dict:
    """OHLC bars the slow, obvious way: one Python list of ticks per bar."""
    groups: dict = {}
    for i in range(len(t_ms)):
        groups.setdefault(int(t_ms[i]) // (tf_s * 1000), []).append(i)
    out = {k: [] for k in BAR_KEYS}
    for bar_id in sorted(groups):
        idx = groups[bar_id]
        b, a = [float(bid[i]) for i in idx], [float(ask[i]) for i in idx]
        spread = [x - y for x, y in zip(a, b)]
        out["t"].append(bar_id * tf_s)
        out["o"].append(b[0])
        out["h"].append(max(b))
        out["l"].append(min(b))
        out["c"].append(b[-1])
        out["ask_c"].append(a[-1])
        out["spread_mean"].append(sum(spread) / len(spread))
        out["spread_max"].append(max(spread))
        out["n"].append(len(idx))
    return {k: np.asarray(v) for k, v in out.items()}


def assert_bars_equal(got: dict, want: dict, what: str) -> None:
    assert set(got) == set(BAR_KEYS), f"{what}: keys {sorted(got)}"
    for k in BAR_KEYS:
        assert len(got[k]) == len(want[k]), f"{what}: {k} has {len(got[k])} bars, expected {len(want[k])}"
        if k in ("spread_mean",):
            np.testing.assert_allclose(got[k], want[k], rtol=0, atol=1e-9, err_msg=f"{what}: {k}")
        else:
            assert np.array_equal(got[k], want[k]), f"{what}: {k} differs"


def week_minute(ts: pd.Timestamp) -> int:
    return ts.weekday() * 1440 + ts.hour * 60 + ts.minute


# ───────────────────────────── build_bars ─────────────────────────────

@pytest.mark.parametrize("tf_s", [60, 300, 900, 3600, 14400])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_build_bars_equals_a_brute_force_loop(seed, tf_s):
    """
    Protects: the bars the indicators are computed on. ``build_bars`` must give, for
    every bar, the first / highest / lowest / last BID, the Ask at the closing tick, the
    spread statistics and the tick count that a plain loop over the ticks gives -- with
    bars only where ticks exist and stamped with the UTC open time of their bucket.
    """
    t, bid, ask = random_ticks(seed, n=4000)
    got = store.build_bars(t, bid, ask, tf_s)
    assert_bars_equal(got, brute_force_bars(t, bid, ask, tf_s), f"seed {seed} tf {tf_s}")
    assert np.all(np.diff(got["t"]) > 0) and np.all(got["t"] % tf_s == 0)
    assert int(got["n"].sum()) == len(t)
    assert np.all(got["l"] <= got["o"]) and np.all(got["o"] <= got["h"])
    assert np.all(got["l"] <= got["c"]) and np.all(got["c"] <= got["h"])


def test_build_bars_boundary_tick_opens_the_new_bar():
    """
    Protects: MT5 bar boundaries. A tick stamped exactly 15:00:00.000 belongs to the bar
    that OPENS at 15:00, one stamped 14:59:59.999 to the bar before it.
    """
    base = store.to_ms("2026-11-11 15:00:00")
    t = np.array([base - 1, base, base + 59_999, base + 60_000], dtype=np.int64)
    bid = np.array([10.0, 11.0, 12.0, 13.0])
    ask = bid + 0.2
    m1 = store.build_bars(t, bid, ask, 60)
    assert m1["t"].tolist() == [base // 1000 - 60, base // 1000, base // 1000 + 60]
    assert m1["c"].tolist() == [10.0, 12.0, 13.0] and m1["o"].tolist() == [10.0, 11.0, 13.0]
    assert m1["n"].tolist() == [1, 2, 1]


def test_build_bars_and_reductions_on_empty_input():
    """Protects: a month with no ticks (the fixture's warm-up-only month) must not crash the store."""
    e_t, e_p = np.zeros(0, np.int64), np.zeros(0)
    bars = store.build_bars(e_t, e_p, e_p, 60)
    assert set(bars) == set(BAR_KEYS) and all(len(v) == 0 for v in bars.values())
    assert store.resample_bars(bars, 300) is bars
    rt, rb, ra = store.reduce_to_seconds(e_t, e_p, e_p)
    assert len(rt) == len(rb) == len(ra) == 0


# ───────────────────────────── resample_bars ─────────────────────────────

@pytest.mark.parametrize("tf", ["M2", "M5", "M15", "M30", "H1", "H4", "D1"])
def test_resampling_m1_bars_equals_building_the_bars_from_ticks(tf):
    """
    Protects: the warm-up history. Higher-timeframe bars before a test window are
    aggregated from stored M1 bars, while bars inside the window come straight from the
    ticks. Both routes must produce the same bar, or the indicators would see a seam at
    the start of every backtest.
    """
    tf_s = TF_SECONDS[tf]
    for seed in (4, 5):
        t, bid, ask = random_ticks(seed, n=9000, mean_gap_ms=25_000.0)       # about four days
        m1 = store.build_bars(t, bid, ask, 60)
        assert_bars_equal(store.resample_bars(m1, tf_s), store.build_bars(t, bid, ask, tf_s), f"{tf} seed {seed}")
    assert store.resample_bars(m1, 60) is m1


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_fixture_archives_are_consistent_with_each_other(fixture_store, windows, symbol):
    """
    Protects: the three archives of one month describe the same ticks -- ``sec`` is the
    last tick of every second of ``ticks`` and ``m1`` is ``build_bars(ticks)`` -- on the
    real fixture data, including resampling its M1 bars to M5 / M15 / H1.
    """
    a, z = windows[symbol]
    tk = store.load_ticks(symbol, a, z, fixture_store)
    sec = store.load_sec(symbol, a, z, fixture_store)
    m1 = store.load_m1(symbol, a, z, fixture_store)
    assert len(tk["t_ms"]) > 5000
    rt, rb, ra = store.reduce_to_seconds(tk["t_ms"], tk["bid"], tk["ask"])
    assert np.array_equal(rt, sec["t_ms"]) and np.array_equal(rb, sec["bid"]) and np.array_equal(ra, sec["ask"])
    assert_bars_equal(m1, store.build_bars(tk["t_ms"], tk["bid"], tk["ask"], 60), f"{symbol} M1")
    for tf in ("M5", "M15", "H1"):
        assert_bars_equal(store.resample_bars(m1, TF_SECONDS[tf]),
                          store.build_bars(tk["t_ms"], tk["bid"], tk["ask"], TF_SECONDS[tf]), f"{symbol} {tf}")
    # real quotes: ordered in time, positive, ask never below bid
    assert np.all(np.diff(tk["t_ms"]) >= 0)
    assert np.all(tk["bid"] > 0) and np.all(tk["ask"] >= tk["bid"])


# ───────────────────────────── reduce_to_seconds ─────────────────────────────

@pytest.mark.parametrize("seed", [6, 7, 8])
def test_reduce_to_seconds_keeps_what_a_whole_second_poll_can_act_on(seed):
    """
    Protects: the per-second series the parameter sweeps run on. It must hold, with their
    true millisecond stamps and their own bid / ask, exactly

    * the LAST tick of every UTC second that has ticks (so every bar close is exact), and
    * the last tick stamped exactly on a whole second (a poll at T sees ticks with
      t <= T, so that tick is what the poll at T reads even when more ticks follow in
      the same second),

    and nothing else.
    """
    t, bid, ask = random_ticks(seed, n=5000, mean_gap_ms=350.0)      # several ticks per second
    # make sure exact-second stamps (incl. duplicates and not-last-of-second ones) are present
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(t), size=300, replace=False)
    t = t.copy()
    t[pick] = (t[pick] // 1000) * 1000
    order = np.argsort(t, kind="stable")
    t, bid, ask = t[order], bid[order], ask[order]

    rt, rb, ra = store.reduce_to_seconds(t, bid, ask)
    keep = set()
    last_of_second, last_of_stamp = {}, {}
    for i in range(len(t)):
        last_of_second[int(t[i]) // 1000] = i                         # later ticks overwrite earlier ones
        last_of_stamp[int(t[i])] = i
    keep.update(last_of_second.values())
    keep.update(i for ts, i in last_of_stamp.items() if ts % 1000 == 0)
    idx = np.array(sorted(keep))
    assert np.array_equal(rt, t[idx]) and np.array_equal(rb, bid[idx]) and np.array_equal(ra, ask[idx])
    assert len(np.unique(t // 1000)) <= len(rt) < len(t)
    assert np.all(np.diff(rt) >= 0)
    # the property that matters: every whole-second poll reads the same quote as on raw ticks
    polls = np.arange((int(t[0]) // 1000 + 1) * 1000, int(t[-1]) + 2000, 1000, dtype=np.int64)
    i_t = np.searchsorted(t, polls, side="right") - 1
    i_s = np.searchsorted(rt, polls, side="right") - 1
    assert np.array_equal(t[i_t], rt[i_s]) and np.array_equal(bid[i_t], rb[i_s]) and np.array_equal(ask[i_t], ra[i_s])
    # reducing twice changes nothing
    again = store.reduce_to_seconds(rt, rb, ra)
    assert np.array_equal(again[0], rt) and np.array_equal(again[1], rb)


def _visible_row(times: np.ndarray, poll_ms: np.ndarray) -> np.ndarray:
    """Index of the latest row with time <= poll time (-1 if none): what a poll sees."""
    return np.searchsorted(times, poll_ms, side="right") - 1


def _hidden_boundary_seconds(t: np.ndarray) -> np.ndarray:
    """Whole seconds (ms) holding a tick stamped exactly on the second that is NOT the last tick of that second."""
    sec = t // 1000
    is_last = np.r_[sec[1:] != sec[:-1], True]
    return np.unique(t[(t % 1000 == 0) & ~is_last])


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_fixture_contains_the_hard_case_for_the_per_second_series(fixture_store, windows, symbol):
    """
    Protects: the test below from passing vacuously. The real fixture ticks must contain
    ticks stamped exactly on a whole second that are NOT the last tick of that second --
    the case a "last tick of each second" reduction gets wrong.
    """
    a, z = windows[symbol]
    tk = store.load_ticks(symbol, a, z, fixture_store)
    assert len(_hidden_boundary_seconds(tk["t_ms"])) >= 3


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_per_second_series_shows_every_whole_second_poll_the_same_quote_as_raw_ticks(fixture_store, windows, symbol):
    """
    Protects: the claim sweeps rest on -- "the per-second series reproduces what a 1 s
    poll sees exactly". Every poll on a whole second must read the same bid / ask from
    the ``sec`` archive as from the raw ticks.
    """
    a, z = windows[symbol]
    tk = store.load_ticks(symbol, a, z, fixture_store)
    sec = store.load_sec(symbol, a, z, fixture_store)
    polls = np.arange(store.to_ms(a) + 1000, store.to_ms(z), 1000, dtype=np.int64)
    i_t, i_s = _visible_row(tk["t_ms"], polls), _visible_row(sec["t_ms"], polls)
    ok = (i_t >= 0) & (i_s >= 0)
    assert np.array_equal(tk["bid"][i_t[ok]], sec["bid"][i_s[ok]])
    assert np.array_equal(tk["ask"][i_t[ok]], sec["ask"][i_s[ok]])


# ───────────────────────────── time helpers ─────────────────────────────

def test_to_ms_accepts_strings_dates_datetimes_and_timestamps_naive_means_utc():
    """
    Protects: window boundaries. Every way a caller can write "2026-11-11 15:00" must
    land on the same UTC millisecond; a value without a timezone is UTC (the Exness
    server clock), never the machine's local time; an explicit offset is honoured.
    """
    want = calendar.timegm((2026, 11, 11, 15, 0, 0)) * 1000
    midnight = calendar.timegm((2026, 11, 11, 0, 0, 0)) * 1000
    ist = timezone(timedelta(hours=5, minutes=30))
    same_instant = [
        "2026-11-11 15:00", "2026-11-11 15:00:00", "2026-11-11T15:00:00", "2026-11-11T15:00:00Z",
        "2026-11-11 15:00:00+00:00", "2026-11-11 20:30:00+05:30",
        datetime(2026, 11, 11, 15, 0), datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 20, 30, tzinfo=ist),
        pd.Timestamp("2026-11-11 15:00"), pd.Timestamp("2026-11-11 15:00", tz="UTC"),
        pd.Timestamp("2026-11-11 20:30", tz="Asia/Kolkata"),
        want, np.int64(want),
    ]
    for x in same_instant:
        assert store.to_ms(x) == want, f"to_ms({x!r}) = {store.to_ms(x)}"
        assert isinstance(store.to_ms(x), int)
    for x in ("2026-11-11", date(2026, 11, 11), datetime(2026, 11, 11), pd.Timestamp("2026-11-11")):
        assert store.to_ms(x) == midnight, f"to_ms({x!r})"
    # millisecond precision survives for every representation
    for ms in (0, 1, 7, 123, 500, 999):
        assert store.to_ms(f"2026-11-11 15:00:00.{ms:03d}") == want + ms
        assert store.to_ms(datetime(2026, 11, 11, 15, 0, 0, ms * 1000)) == want + ms
        assert store.to_ms(pd.Timestamp(2026, 11, 11, 15, 0, 0, ms * 1000)) == want + ms
    with pytest.raises(TypeError):
        store.to_ms(1.5)
    with pytest.raises(TypeError):
        store.to_ms(None)


def test_ms_to_dt_round_trips():
    """Protects: timestamps shown in reports are the instants the engine used."""
    rng = np.random.default_rng(9)
    for ms in rng.integers(1_700_000_000_000, 1_900_000_000_000, 200):
        ts = store.ms_to_dt(int(ms))
        assert str(ts.tz) == "UTC" and store.to_ms(ts) == int(ms)
    assert store.ms_to_dt(calendar.timegm((2026, 11, 9, 6, 0, 0)) * 1000) == pd.Timestamp("2026-11-09 06:00", tz="UTC")


# ───────────────────────────── loaders ─────────────────────────────

@pytest.mark.parametrize("symbol", SYMBOLS)
def test_loaders_return_the_half_open_window_on_the_fixture_store(fixture_store, windows, symbol):
    """
    Protects: [start, end) slicing of ticks, seconds and M1 bars. A tick stamped exactly
    ``start`` is in, one stamped exactly ``end`` is out; nothing inside is dropped and
    nothing is duplicated.
    """
    a, z = windows[symbol]
    a_ms, z_ms = store.to_ms(a), store.to_ms(z)
    full = store.load_ticks(symbol, a_ms, z_ms, fixture_store)
    t = full["t_ms"]
    assert set(full) == {"t_ms", "bid", "ask"}
    assert t[0] >= a_ms and t[-1] < z_ms and np.all(np.diff(t) >= 0)
    # the fixture holds exactly the window: asking for more returns the same ticks
    wide = store.load_ticks(symbol, a_ms - 86_400_000, z_ms + 86_400_000, fixture_store)
    assert np.array_equal(wide["t_ms"], t)

    rng = np.random.default_rng(10)
    for _ in range(40):
        lo, hi = sorted(int(x) for x in rng.integers(a_ms, z_ms, 2))
        if rng.random() < 0.5:                       # cut exactly on existing tick stamps
            lo, hi = sorted((int(t[rng.integers(0, len(t))]), int(t[rng.integers(0, len(t))])))
        for loader, ref in ((store.load_ticks, full), (store.load_sec, store.load_sec(symbol, a_ms, z_ms, fixture_store))):
            got = loader(symbol, lo, hi, fixture_store)
            keep = (ref["t_ms"] >= lo) & (ref["t_ms"] < hi)
            if not keep.any():
                assert got == {}
                continue
            for k in ("t_ms", "bid", "ask"):
                assert np.array_equal(got[k], ref[k][keep]), f"{loader.__name__} {k} [{lo}, {hi})"
    # string / Timestamp arguments mean the same window
    by_str = store.load_ticks(symbol, a, z, fixture_store)
    by_ts = store.load_ticks(symbol, pd.Timestamp(a), pd.Timestamp(z, tz="UTC"), fixture_store)
    assert np.array_equal(by_str["t_ms"], t) and np.array_equal(by_ts["t_ms"], t)
    # outside the data: an empty dict, not an error
    assert store.load_ticks(symbol, "2026-12-24", "2026-12-25", fixture_store) == {}
    assert store.load_ticks(symbol, z_ms, z_ms + 1000, fixture_store) == {}
    assert store.load_ticks("NOSUCHm", a, z, fixture_store) == {}


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_load_m1_selects_bars_by_open_time_across_months(fixture_store, windows, symbol):
    """
    Protects: the warm-up fetch. ``load_m1`` returns the bars whose OPEN time is in
    [start, end), in order, across the month boundary (the fixtures span October and
    November), with no bar repeated.
    """
    span = store.data_span(symbol, fixture_store)
    assert store.available_months(symbol, fixture_store) == [(2026, 10), (2026, 11)]
    everything = store.load_m1(symbol, span[0], span[1] + pd.Timedelta(minutes=1), fixture_store)
    t = everything["t"]
    assert set(everything) == set(BAR_KEYS)
    assert np.all(np.diff(t) >= 60) and np.all(t % 60 == 0)
    assert t[0] * 1000 == store.to_ms(span[0])
    oct_nov = store.to_ms("2026-11-01")
    assert (t * 1000 < oct_nov).any() and (t * 1000 >= oct_nov).any()
    rng = np.random.default_rng(12)
    for _ in range(30):
        i, j = sorted(int(x) for x in rng.integers(0, len(t), 2))
        lo, hi = int(t[i]) * 1000, int(t[j]) * 1000
        if rng.random() < 0.5:
            lo += int(rng.integers(1, 59_999))        # a start inside a minute excludes that bar
            hi += int(rng.integers(1, 59_999))        # an end inside a minute includes the bar that opened before it
        got = store.load_m1(symbol, lo, hi, fixture_store)
        keep = (t * 1000 >= lo) & (t * 1000 < hi)
        if not keep.any():
            assert got == {}
            continue
        for k in BAR_KEYS:
            assert np.array_equal(got[k], everything[k][keep]), k
    a, z = windows[symbol]
    assert store.to_ms(span[1]) < store.to_ms(z) and store.to_ms(span[1]) >= store.to_ms(z) - 5000


def test_loaders_concatenate_months_and_skip_missing_ones(tmp_path):
    """
    Protects: multi-month backtests. A window spanning several monthly archives must come
    back as one ordered series with every tick exactly once, also when the window ends
    exactly on a month boundary or a month in the middle is absent.
    """
    symbol = "XAUUSDm"
    parts = {}
    rng = np.random.default_rng(13)
    for (y, m) in ((2026, 1), (2026, 2), (2026, 4)):                 # March is missing on purpose
        lo = store.to_ms(f"{y}-{m:02d}-01")
        hi = store.to_ms(f"{y}-{m + 1:02d}-01")
        t = np.sort(rng.integers(lo, hi, 3000)).astype(np.int64)
        t[0], t[-1] = lo, hi - 1                                      # ticks on the very edges of the month
        bid = np.round(2000.0 + np.cumsum(rng.normal(0, 0.1, len(t))), 3)
        ask = bid + 0.2
        d = store.month_dir(tmp_path, symbol, y, m)
        d.mkdir(parents=True)
        st, sb, sa = store.reduce_to_seconds(t, bid, ask)
        np.savez(d / "ticks.npz", t_ms=t, bid=bid, ask=ask)
        np.savez(d / "sec.npz", t_ms=st, bid=sb, ask=sa)
        np.savez(d / "m1.npz", **store.build_bars(t, bid, ask, 60))
        (d / "meta.json").write_text(json.dumps({"first": store.ms_to_dt(int(t[0])).isoformat(),
                                                 "last": store.ms_to_dt(int(t[-1])).isoformat()}),
                                     encoding="utf-8")
        parts[(y, m)] = (t, bid, ask)
    all_t = np.concatenate([parts[k][0] for k in sorted(parts)])
    all_b = np.concatenate([parts[k][1] for k in sorted(parts)])

    assert store.available_months(symbol, tmp_path) == [(2026, 1), (2026, 2), (2026, 4)]
    span = store.data_span(symbol, tmp_path)
    assert store.to_ms(span[0]) == all_t[0] and store.to_ms(span[1]) == all_t[-1]

    feb1, mar1 = store.to_ms("2026-02-01"), store.to_ms("2026-03-01")
    cases = [(store.to_ms("2026-01-30 12:00"), store.to_ms("2026-02-02 12:00")),   # across a boundary
             (store.to_ms("2026-01-15"), feb1),                                    # ends exactly on a boundary
             (feb1, feb1 + 1), (feb1 - 1, feb1),                                   # single-millisecond windows
             (store.to_ms("2026-02-20"), store.to_ms("2026-04-10")),               # over the missing month
             (store.to_ms("2025-12-01"), store.to_ms("2026-06-01"))]               # wider than the store
    for lo, hi in cases:
        got = store.load_ticks(symbol, lo, hi, tmp_path)
        keep = (all_t >= lo) & (all_t < hi)
        assert keep.any()
        assert np.array_equal(got["t_ms"], all_t[keep]) and np.array_equal(got["bid"], all_b[keep])
        sec = store.load_sec(symbol, lo, hi, tmp_path)
        assert np.all(np.diff(sec["t_ms"]) > 0) and sec["t_ms"][0] >= lo and sec["t_ms"][-1] < hi
    assert store.load_ticks(symbol, mar1, store.to_ms("2026-03-20"), tmp_path) == {}
    m1 = store.load_m1(symbol, store.to_ms("2026-01-31 23:00"), store.to_ms("2026-02-01 01:00"), tmp_path)
    assert np.all(np.diff(m1["t"]) > 0) and m1["t"][0] * 1000 >= store.to_ms("2026-01-31 23:00")
    assert m1["t"][-1] * 1000 < store.to_ms("2026-02-01 01:00")


# ───────────────────────────── fast.prepare ─────────────────────────────

ALL_TFS = ["M1", "M5", "M15", "H1", "H4"]


def _warm_closes_by_brute_force(m1: dict, tf_s: int, first_window_bar_id: int, warm_bars: int):
    """(bar ids, closes) of the bars made only of M1 bars that closed before the first window bar."""
    last_close = {}
    for t, c in zip(m1["t"], m1["c"]):
        bar_id = int(t) // tf_s
        if bar_id < first_window_bar_id:
            last_close[bar_id] = float(c)              # M1 bars are in time order: the last one wins
    ids = sorted(last_close)[-warm_bars:]
    return np.asarray(ids, dtype=np.int64), np.asarray([last_close[i] for i in ids])


@pytest.mark.parametrize("mode", ["ticks", "sec"])
@pytest.mark.parametrize("symbol", SYMBOLS)
def test_prepare_joins_warmup_history_to_window_bars_without_a_seam(fixture_store, windows, prepared, symbol, mode):
    """
    Protects: what the kernel is handed. For every timeframe
      * warm-up bars come first, strictly older than the first window bar, with no bar
        present twice at the seam and no bar out of order;
      * START_ROW is -1 for warm-up bars and strictly increasing from 0 for window bars,
        and the rows it delimits all belong to that bar's UTC bucket;
      * the close of every window bar is the Bid of the LAST row inside it;
      * the warm-up closes are the closes of the M1 history aggregated to that timeframe.
    """
    a, z = windows[symbol]
    prep = prepared(symbol, mode=mode)
    rows = (store.load_ticks if mode == "ticks" else store.load_sec)(symbol, a, z, fixture_store)
    assert prep.mode == mode and prep.n_rows == len(rows["t_ms"]) > 2000
    assert np.array_equal(prep.t_ms, rows["t_ms"]) and np.array_equal(prep.bid, rows["bid"])
    assert np.array_equal(prep.ask, rows["ask"])
    assert prep.start_ms == store.to_ms(a) and prep.end_ms == store.to_ms(z)
    assert prep.tfs == ALL_TFS
    span = store.data_span(symbol, fixture_store)
    m1 = store.load_m1(symbol, span[0], a, fixture_store)

    for tf in ALL_TFS:
        tf_s = TF_SECONDS[tf]
        closes, bar_t, start_row, nwarm = prep.closes[tf], prep.bar_t[tf], prep.start_row[tf], prep.nwarm[tf]
        assert len(closes) == len(bar_t) == len(start_row)
        assert np.all(np.diff(bar_t) > 0), f"{tf}: bars repeated or out of order"
        assert np.all(bar_t % tf_s == 0)
        assert 0 < nwarm <= fast.DEFAULT_WARM_BARS
        assert np.all(start_row[:nwarm] == -1) and start_row[nwarm] == 0
        assert np.all(np.diff(start_row[nwarm:]) > 0), f"{tf}: START_ROW not increasing"
        # window bars: each owns rows [start_row[j], start_row[j + 1]) of its own bucket
        edges = np.append(start_row[nwarm:], prep.n_rows)
        for j in range(len(edges) - 1):
            lo, hi = int(edges[j]), int(edges[j + 1])
            bucket = prep.t_ms[lo:hi] // (tf_s * 1000)
            assert np.all(bucket == bar_t[nwarm + j] // tf_s), f"{tf}: row outside its bar"
            assert closes[nwarm + j] == prep.bid[hi - 1], f"{tf}: close is not the last Bid of the bar"
        # warm-up bars: the M1 history, aggregated, ending right before the first window bar
        want_ids, want_c = _warm_closes_by_brute_force(m1, tf_s, int(bar_t[nwarm] // tf_s), fast.DEFAULT_WARM_BARS)
        assert np.array_equal(bar_t[:nwarm] // tf_s, want_ids), f"{tf}: warm-up bars"
        assert np.array_equal(closes[:nwarm], want_c), f"{tf}: warm-up closes"
        assert bar_t[nwarm - 1] < bar_t[nwarm]
    # the fixture really exercises a bar that straddles the window start (H4 opens before the window)
    assert prep.bar_t["H4"][prep.nwarm["H4"]] * 1000 < prep.start_ms
    assert prep.nwarm["M1"] == prep.nwarm["M5"] == prep.nwarm["M15"] == fast.DEFAULT_WARM_BARS


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_prepare_from_a_mid_bar_start_uses_no_tick_from_after_the_start_for_warmup(fixture_store, windows, symbol):
    """
    Protects: NO LOOKAHEAD at the start of a run. When a window starts in the middle of a
    bar, the stored M1 bar that straddles the start already contains ticks from AFTER it.
    That bar must be rebuilt from in-window rows only (it is the first window bar), never
    taken from history, on every timeframe.
    """
    a, z = windows[symbol]
    start = pd.Timestamp(a) + pd.Timedelta(minutes=7, seconds=30)
    prep = fast.prepare(symbol, start, z, ALL_TFS, mode="ticks", store_dir=fixture_store)
    start_ms = store.to_ms(start)
    assert prep.t_ms[0] >= start_ms
    span = store.data_span(symbol, fixture_store)
    m1_before = store.load_m1(symbol, span[0], start_ms - 60_000 + 1, fixture_store)   # bars that CLOSED before start
    for tf in ALL_TFS:
        tf_s = TF_SECONDS[tf]
        nwarm = prep.nwarm[tf]
        first_id = int(prep.bar_t[tf][nwarm] // tf_s)
        assert first_id == int(prep.t_ms[0] // (tf_s * 1000))
        assert first_id * tf_s * 1000 < start_ms, f"{tf}: the first window bar should straddle the start"
        # the straddling bar holds in-window rows only: its close is an in-window Bid
        hi = int(prep.start_row[tf][nwarm + 1]) if nwarm + 1 < len(prep.start_row[tf]) else prep.n_rows
        assert prep.closes[tf][nwarm] == prep.bid[hi - 1]
        # every warm-up bar is strictly older and built from M1 bars that closed before the start
        want_ids, want_c = _warm_closes_by_brute_force(m1_before, tf_s, first_id, fast.DEFAULT_WARM_BARS)
        assert np.array_equal(prep.bar_t[tf][:nwarm] // tf_s, want_ids), tf
        assert np.array_equal(prep.closes[tf][:nwarm], want_c), tf


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_prepare_of_a_shorter_window_is_a_prefix_of_the_longer_one(fixture_store, windows, prepared, symbol):
    """
    Protects: NO LOOKAHEAD in the data itself. Preparing [a, b) and [a, c) with c > b must
    agree on every row before b and on every bar that closed before b; only the bar still
    forming at b may differ (its close is "the last Bid so far", which is exactly why the
    kernel never reads the forming bar's close).
    """
    a, z = windows[symbol]
    long = prepared(symbol, mode="ticks")
    for minutes in (7, 16, 29):
        b = pd.Timestamp(a) + pd.Timedelta(minutes=minutes, seconds=13)
        short = fast.prepare(symbol, a, b, ALL_TFS, mode="ticks", store_dir=fixture_store)
        n = short.n_rows
        assert 0 < n < long.n_rows
        assert np.array_equal(short.t_ms, long.t_ms[:n]) and np.array_equal(short.bid, long.bid[:n])
        for tf in ALL_TFS:
            assert short.nwarm[tf] == long.nwarm[tf]
            m = len(short.closes[tf])
            assert np.array_equal(short.bar_t[tf], long.bar_t[tf][:m])
            assert np.array_equal(short.start_row[tf], long.start_row[tf][:m])
            assert np.array_equal(short.closes[tf][:m - 1], long.closes[tf][:m - 1]), f"{tf}: a closed bar changed"
            assert short.closes[tf][m - 1] == short.bid[-1]


def test_prepare_options_and_errors(fixture_store, windows):
    """
    Protects: the knobs around ``prepare``. Timeframes are de-duplicated and sorted fast
    to slow; ``warm_bars`` keeps the LATEST bars; a window without data is an error with a
    hint, not an empty backtest that looks like "the strategy did not trade".
    """
    a, z = windows["XAUUSDm"]
    prep = fast.prepare("XAUUSDm", a, z, ["H1", "M1", "M15", "M1"], mode="sec", warm_bars=50, store_dir=fixture_store)
    assert prep.tfs == ["M1", "M15", "H1"]
    full = fast.prepare("XAUUSDm", a, z, ["M1", "M15", "H1"], mode="sec", store_dir=fixture_store)
    for tf in prep.tfs:
        assert prep.nwarm[tf] == 50
        assert np.array_equal(prep.closes[tf], full.closes[tf][full.nwarm[tf] - 50:])
        assert np.array_equal(prep.bar_t[tf], full.bar_t[tf][full.nwarm[tf] - 50:])
    with pytest.raises(ValueError, match="no sec data"):
        fast.prepare("XAUUSDm", "2026-12-24", "2026-12-25", ["M1"], mode="sec", store_dir=fixture_store)
    with pytest.raises(ValueError, match="no ticks data"):
        fast.prepare("BTCUSDm", a, z, ["M1"], mode="ticks", store_dir=fixture_store)   # BTC has no ticks that day


def test_flattened_arrays_keep_each_timeframe_at_its_offset(prepared):
    """
    Protects: the hand-over to the kernel. ``Prepared.flat`` concatenates the timeframes;
    ``off`` / ``nb`` / ``nwarm`` must describe exactly where each one lives, and the
    arrays must be cached per indicator setting (a sweep re-uses them) without mixing
    settings up.
    """
    prep = prepared("XAUUSDm", mode="sec")
    cfg = BacktestConfig(symbol="XAUUSDm")
    flat = prep.flat(cfg)
    assert prep.flat(cfg) is flat
    pos = 0
    for f, tf in enumerate(prep.tfs):
        n = len(prep.closes[tf])
        assert flat["off"][f] == pos and flat["nb"][f] == n and flat["nwarm"][f] == prep.nwarm[tf]
        assert np.array_equal(flat["C"][pos:pos + n], prep.closes[tf])
        assert np.array_equal(flat["START_ROW"][pos:pos + n], prep.start_row[tf])
        pos += n
    assert all(len(flat[k]) == pos for k in ("C", "RSI", "HIST", "R_PH", "M_CL", "START_ROW"))
    other = prep.flat(cfg.replace(rsi_length=7))
    assert other is not flat and not np.array_equal(other["RSI"], flat["RSI"])
    assert np.array_equal(other["C"], flat["C"]) and prep.flat(cfg.replace(entry_s=4.0)) is flat
