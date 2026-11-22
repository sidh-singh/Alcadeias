"""
The Turtle's decisions replayed on the stored BTCUSDm M1 bars against the backtest it ports.

turtle.py's own functions -- the daily levels from the last TURTLE_D1_BARS closed UTC D1 bars, the M15 vote from
the last TURTLE_VOTE_BARS closed M15 bars, and the entry / add / stop rules -- are fed the store's M1 bid bars,
one bar at a time in the backtest's order (backtesting/research/external.py _path_kernel: a gap at the open, the
D1 bar that closed, the stop on the unfavourable extreme, the adds on the favourable one, the stop-entry orders),
with the backtest's fill prices (the level, or the open when the bar opened beyond it). The trades must be the
backtest's -- external.run_path on external.filtered(external.turtle(m, system).plan, m, bot_signals.votes_at),
the final ten's "Turtle + bot votes" (System 1) and "Turtle System 2 + bot votes" -- trade for trade: the same
entry day, side, number of legs and exit day; the M1 bars and prices are compared too, and the account on the
bot's unit rule must end on the same cent.

Needs the backtester and its tick store (the backtest_hedging checkout): ALCADEIAS_BACKTEST_REPO, default
/Users/sidharthsingh/Desktop/Alcadeias/Alcadeias; skipped without it. The window is TURTLE_REPLAY_FROM ..
TURTLE_REPLAY_TO (default 2023-01-01 .. 2026-11-13; 2018-11-13 gives the final ten's eight years). The bot's
votes on all the M15 bars take a few minutes; TURTLE_REPLAY_CACHE names a folder to keep them in. Nothing is
written to the backtester's checkout (numba's cache goes to NUMBA_CACHE_DIR or a temporary folder).
"""
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT

REPO = Path(os.environ.get('ALCADEIAS_BACKTEST_REPO', '/Users/sidharthsingh/Desktop/Alcadeias/Alcadeias'))
FROM = os.environ.get('TURTLE_REPLAY_FROM', '2023-01-01')
TO = os.environ.get('TURTLE_REPLAY_TO', '2026-11-13')
HISTORY_FROM = '2018-01-01'          # the final ten's BTC history (final10.HISTORY_FROM)
DATA_END = '2026-11-13'              # final10.DATA_END

pytestmark = pytest.mark.slow


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _constants():
    return _load('replay_constants', ROOT / 'constants.py')


@pytest.fixture(scope='module')
def bt(tmp_path_factory):
    """The backtester's market, the bot's votes on it, and this branch's turtle.py / indicator.py."""
    if not (REPO / 'backtesting' / 'research' / 'external.py').exists():
        pytest.skip(f'no backtester at {REPO} (set ALCADEIAS_BACKTEST_REPO)')
    os.environ.setdefault('NUMBA_CACHE_DIR', str(tmp_path_factory.mktemp('numba_cache')))
    if 'numba' in sys.modules:
        import numba
        numba.config.CACHE_DIR = os.environ['NUMBA_CACHE_DIR']
    # The checkout goes first on the path only while its package is imported (a pip package is also called
    # 'backtesting'; and the checkout's own app.py / constants.py must not stand in for this branch's later).
    for name in [n for n in sys.modules if n == 'backtesting' or n.startswith('backtesting.')]:
        if not str(getattr(sys.modules[name], '__file__', '') or '').startswith(str(REPO)):
            sys.modules.pop(name)
    sys.path.insert(0, str(REPO))
    try:
        from backtesting.research import external as X
    except ImportError as e:
        pytest.skip(f'the backtester does not import: {e}')
    finally:
        sys.path.remove(str(REPO))
    try:
        m = X.load_market('BTCUSDm', earliest=HISTORY_FROM, end=DATA_END)
    except FileNotFoundError as e:
        pytest.skip(f'no BTCUSDm bars in the store: {e}')
    cache = Path(os.environ.get('TURTLE_REPLAY_CACHE') or tmp_path_factory.mktemp('bot_votes'))
    sig = X.bot_signals(m, cache)
    return {'X': X, 'm': m, 'sig': sig, 'T': _load('replay_turtle', ROOT / 'turtle.py'),
            'ind': _load('replay_indicator', ROOT / 'indicator.py').Indicator(), 'c': _constants()}


class Bars:
    """The store's M1 bars grouped as MT5 groups the bid: UTC days and M15 buckets."""

    def __init__(self, m):
        day = m.t // 86400
        f = np.flatnonzero(np.diff(day, prepend=day[0] - 1) != 0)
        e = np.append(f[1:], len(day))
        self.d_t = (day[f] * 86400).astype(np.int64)
        self.d_o, self.d_c = m.o[f], m.c[e - 1]
        self.d_h, self.d_l = np.maximum.reduceat(m.h, f), np.minimum.reduceat(m.l, f)
        self.d_m1 = e - f
        self.d_dx = np.searchsorted(m.t, self.d_t + 86400, side='left')     # the M1 bar the close is first seen at
        q = m.t // 900
        f15 = np.flatnonzero(np.diff(q, prepend=q[0] - 1) != 0)
        e15 = np.append(f15[1:], len(q))
        self.m15_tc = (q[f15] * 900 + 900).astype(np.int64)
        self.m15_c = m.c[e15 - 1]


@pytest.fixture(scope='module')
def bars(bt):
    return Bars(bt['m'])


def _levels(T, b, bars, system, c):
    """What the bot computes when D1 bar b has closed: the levels from its last TURTLE_D1_BARS closed bars."""
    lo = max(0, b + 1 - c.TURTLE_D1_BARS)
    sl = slice(lo, b + 1)
    rows = T.daily_rows(bars.d_o[sl], bars.d_h[sl], bars.d_l[sl], bars.d_c[sl], system=system, n_len=c.TURTLE_N_LEN,
                        stop_n=c.TURTLE_STOP_N, add_n=c.TURTLE_ADD_N, tick=c.TURTLE_TICK)
    return T.row_levels(rows, bars.d_t[sl], b - lo)


def _vote_fn(bt, bars):
    """The bot's vote at a time: turtle.closed_bar_vote on the last TURTLE_VOTE_BARS closed M15 bars (memoised per
    M15 bar), with a count of the bars where it differs from the backtest's m15_agree."""
    T, ind, c, sig = bt['T'], bt['ind'], bt['c'], bt['sig']
    assert np.array_equal(sig.m15_tc, bars.m15_tc)
    memo, stats = {}, {'n': 0, 'differ': []}
    kw = dict(rsi_length=c.RSI_LENGTH, rsi_ma_type=c.RSI_MA_TYPE, macd_fast=c.MACD_FAST, macd_slow=c.MACD_SLOW,
              macd_signal=c.MACD_SIGNAL, lookback=c.PEAK_LOOKBACK, width=c.PIVOT_WIDTH, rsi_ob=c.RSI_PEAK_OB,
              rsi_os=c.RSI_PEAK_OS)

    def vote_at(t):
        i = int(np.searchsorted(bars.m15_tc, t, side='right')) - 1
        if i < 0:
            return 0
        v = memo.get(i)
        if v is None:
            v, _ = T.closed_bar_vote(bars.m15_c[max(0, i + 1 - c.TURTLE_VOTE_BARS): i + 1], ind, **kw)
            memo[i] = v
            stats['n'] += 1
            if v != int(sig.m15_agree[i]):
                stats['differ'].append(i)
        return v
    return vote_at, stats


def replay(bt, bars, system, a_ix, z_ix, vote_at):
    """turtle.py on M1 bars a_ix .. z_ix - 1 in _path_kernel's order, from a flat $2,000 account."""
    T, m, c = bt['T'], bt['m'], bt['c']
    tl, ol, hl, ll, cl, spl = (x.tolist() for x in (m.t, m.o, m.h, m.l, m.c, m.sp))
    rows_at = {}
    for b in np.flatnonzero((bars.d_dx >= a_ix) & (bars.d_dx < z_ix)):
        rows_at.setdefault(int(bars.d_dx[b]), []).append(_levels(T, int(b), bars, system, c))
    st = T.new_state()
    trades, cur, bal = [], None, 2000.0

    def close(j, px, why):
        nonlocal cur, bal
        pl = sum(cur['units'] * 0.01 * cur['dir'] * (px - lp) for _, lp in cur['legs'])
        bal += pl
        cur.update(xix=j, xpx=px, why=why, pnl=pl)
        trades.append(cur)
        cur = None
        T.on_exit(st, tl[j])

    for j in range(a_ix, z_ix):
        t, o, h, l, cc, sp = tl[j], ol[j], hl[j], ll[j], cl[j], spl[j]
        ask_o = o + sp
        # 1. a gap through the stop at the open
        if st['side'] != 0 and T.exit_due(st, o, ask_o):
            close(j, o if st['side'] == 1 else ask_o, 'gap stop')
        # 2. a D1 bar closed: the levels it sets (and the stop ratchet)
        for lv in rows_at.get(j, ()):
            T.on_new_row(st, lv)
        # 3. in a trade: the stop on the unfavourable extreme, else the adds on the favourable one
        exited = False
        if st['side'] == 1:
            if T.exit_due(st, l, l + sp):
                close(j, st['stop'], 'stop')
                exited = True
            else:
                while (lvl := T.add_due(st, h, h + sp, t, c.TURTLE_MAX_LEGS)) is not None:
                    T.on_add(st, max(lvl, ask_o), t)
                    cur['legs'].append((j, max(lvl, ask_o)))
        elif st['side'] == -1:
            if T.exit_due(st, h, h + sp):
                close(j, st['stop'], 'stop')
                exited = True
            else:
                while (lvl := T.add_due(st, l, l + sp, t, c.TURTLE_MAX_LEGS)) is not None:
                    T.on_add(st, min(lvl, o), t)
                    cur['legs'].append((j, min(lvl, o)))
        # 4. flat: the breakout orders (the bar's ask high for a buy, its bid low for a sell)
        if st['side'] == 0 and not exited:
            d = T.entry_due(st, l, h + sp, lambda: vote_at(t), t)
            if d:
                lv = st['levels']
                px = max(lv['buy'], ask_o) if d == 1 else min(lv['sell'], o)
                units = T.unit_rule(bal, 2500, 10)
                T.on_entry(st, d, px, t, units)
                cur = dict(dir=d, eix=j, epx=px, legs=[(j, px)], units=units)
                # the bar's opposite extreme comes after the fill
                if T.exit_due(st, l, l + sp) if d == 1 else T.exit_due(st, h, h + sp):
                    close(j, st['stop'], 'stop')
        # 5. the end of the window
        if j == z_ix - 1 and st['side'] != 0:
            close(j, cc if st['side'] == 1 else cc + sp, 'end')
    return trades, bal


def backtest(bt, system, a_ix, z_ix):
    X, m, sig = bt['X'], bt['m'], bt['sig']
    plan = X.filtered(X.turtle(m, system).plan, m, sig.votes_at)
    p = X.run_path(m, plan, a_ix, z_ix)
    res = X.account(m, p, X.BOT, np.asarray([a_ix, z_ix], np.int64))
    out = []
    for i in range(len(p)):
        legs = [(int(p.leix[q]), float(p.lepx[q])) for q in range(p.leg0[i], p.leg0[i] + p.nleg[i])]
        out.append(dict(dir=int(p.dir[i]), eix=int(p.eix[i]), epx=float(p.epx[i]), xix=int(p.xix[i]),
                        xpx=float(p.xpx[i]), why=X.WHY_NAMES[int(p.why[i])], legs=legs))
    return out, float(res.final), plan


def _day(m, j):
    return str(pd.Timestamp(int(m.t[j]), unit='s').date())


def _show(m, tr):
    return (f"{'BUY ' if tr['dir'] == 1 else 'SELL'} {_day(m, tr['eix'])} -> {_day(m, tr['xix'])} "
            f"{len(tr['legs'])} legs ({tr['why']})")


@pytest.mark.parametrize('system', [1, 2])
def test_the_replay_takes_the_backtests_trades(bt, bars, system):
    m = bt['m']
    a_ix, z_ix = m.ix(FROM), m.ix(TO)
    # every UTC day of the history used is a whole day for the backtest too (it merges days of < 360 M1 bars)
    lo = int(np.searchsorted(bars.d_t, m.t[a_ix] - bt['c'].TURTLE_D1_BARS * 86400))
    assert bars.d_m1[lo:].min() >= 360
    vote_at, stats = _vote_fn(bt, bars)
    mine, bal = replay(bt, bars, system, a_ix, z_ix, vote_at)
    theirs, final, _ = backtest(bt, system, a_ix, z_ix)

    decision, exact = [], []
    for i in range(max(len(mine), len(theirs))):
        a = mine[i] if i < len(mine) else None
        b = theirs[i] if i < len(theirs) else None
        if a is None or b is None:
            decision.append(f'trade {i}: replay {a and _show(m, a)} | backtest {b and _show(m, b)}')
            continue
        if (_day(m, a['eix']), a['dir'], len(a['legs']), _day(m, a['xix'])) != \
                (_day(m, b['eix']), b['dir'], len(b['legs']), _day(m, b['xix'])):
            decision.append(f'trade {i}: replay {_show(m, a)} | backtest {_show(m, b)}')
        elif (a['eix'], a['xix'], [x for x, _ in a['legs']]) != (b['eix'], b['xix'], [x for x, _ in b['legs']]) or \
                not np.allclose([a['epx'], a['xpx']] + [p for _, p in a['legs']],
                                [b['epx'], b['xpx']] + [p for _, p in b['legs']], rtol=0, atol=1e-6):
            exact.append(f'trade {i}: same days, other M1 bars or prices: replay {a} | backtest {b}')
    report = (f'System {system}, {FROM} .. {TO}: replay {len(mine)} trades, backtest {len(theirs)}; '
              f'account ${bal:,.2f} vs ${final:,.2f}; {stats["n"]} votes computed, '
              f'{len(stats["differ"])} differ from the backtest\'s')
    print(report)
    assert len(theirs) > 20, report
    assert not decision, report + '\n' + '\n'.join(decision)
    assert not exact, report + '\n' + '\n'.join(exact[:10])
    assert not stats['differ'], report
    assert round(bal, 2) == round(final, 2), report


@pytest.mark.parametrize('system', [1, 2])
def test_the_daily_levels_are_the_backtests(bt, bars, system):
    """Every D1 bar of the window: the levels the bot computes from its last TURTLE_D1_BARS closed bars are the
    backtest's plan rows (stop-entry levels, 2N, 0.5N, the exit channels)."""
    X, m, T, c = bt['X'], bt['m'], bt['T'], bt['c']
    plan = X.turtle(m, system).plan
    d1 = m.bars('D1')
    assert np.array_equal(d1.t, bars.d_t)
    first = int(np.searchsorted(bars.d_t, pd.Timestamp(FROM, tz='UTC').timestamp())) - 1
    for b in range(max(first, 0), len(bars.d_t) - 1):
        k = int(np.searchsorted(plan.dt, d1.tc[b]))
        assert plan.dt[k] == d1.tc[b]
        lv = _levels(T, b, bars, system, c)
        for name, col in (('buy', 'bstop'), ('sell', 'sstop'), ('stop_dist', 'sl'), ('add_step', 'pstep'),
                          ('trail_long', 'trl'), ('trail_short', 'trs')):
            want = float(plan.f[col][k])
            got = lv[name]
            assert (got is None and want != want) or got == pytest.approx(want, rel=1e-12, abs=1e-9), (
                f'System {system}, D1 bar {pd.Timestamp(int(bars.d_t[b]), unit="s").date()}: {name} {got} vs {want}')


def test_the_vote_is_the_backtests_on_closed_m15_bars(bt, bars):
    """turtle.closed_bar_vote on the last TURTLE_VOTE_BARS closed M15 bars against the backtest's m15_agree, on
    every 40th M15 bar of the window and on every bar of its first week."""
    m, sig = bt['m'], bt['sig']
    vote_at, stats = _vote_fn(bt, bars)
    a = int(np.searchsorted(bars.m15_tc, m.t[m.ix(FROM)], side='left'))
    z = int(np.searchsorted(bars.m15_tc, m.t[m.ix(TO) - 1], side='right'))
    sample = sorted(set(range(a, z, 40)) | set(range(a, min(z, a + 7 * 96))))
    for i in sample:
        vote_at(int(bars.m15_tc[i]))
    agree = sig.m15_agree[sample]
    assert stats['n'] == len(sample)
    assert (agree == 1).mean() > 0.2 and (agree == -1).mean() > 0.2       # both states are exercised
    assert not stats['differ'], [str(pd.Timestamp(int(bars.m15_tc[i]), unit='s')) for i in stats['differ'][:10]]
