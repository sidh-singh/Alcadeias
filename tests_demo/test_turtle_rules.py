"""
turtle.py's rules on hand-made bars and quotes: the daily levels (channels that include the bar just closed, a tick
beyond), N, the System 1 skip-after-winner filter, the one shared stop (2N or the exit channel, ratcheting, never
loosened), the adds (every 0.5N from the actual fill, not in the entry's M1 bar, at most 4 legs), the entries
(armed per D1 bar, consumed by a fill, gated by the vote, never in an exit's M1 bar) and the rebuild of a trade from
its legs. The replay on the stored bars (test_turtle_replay.py) checks the same functions against the backtest.
"""
import importlib.util

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT

_spec = importlib.util.spec_from_file_location('rules_turtle', ROOT / 'turtle.py')
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
_spec = importlib.util.spec_from_file_location('rules_indicator', ROOT / 'indicator.py')
_ind = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ind)

DAY = 86400
T0 = 1_790_000_000 // DAY * DAY            # a UTC midnight


def _days(n):
    return T0 + DAY * np.arange(n)


def _rising(n=60):
    H = 100.0 + np.arange(n)
    return H - 1.5, H, H - 2.0, H - 1.0          # o, h, l, c


def test_levels_use_the_bar_that_just_closed_and_sit_one_tick_beyond():
    o, h, l, c = _rising(60)
    rows = T.daily_rows(o, h, l, c, system=2)
    lv = T.row_levels(rows, _days(60), 59)
    assert lv['buy'] == pytest.approx(159.01) and lv['sell'] == pytest.approx(102.99)    # hi55 = H[59], lo55 = L[5]
    assert lv['trail_long'] == 138.0 and lv['trail_short'] == 159.0                    # lo20 = L[40], hi20 = H[59]
    assert lv['n'] == 2.0 and lv['stop_dist'] == 4.0 and lv['add_step'] == 1.0
    assert lv['bar_time'] == _days(60)[59] and lv['from_time'] == lv['bar_time'] + DAY
    s1 = T.row_levels(T.daily_rows(o, h, l, c, system=1), _days(60), 59)
    # System 1's hypothetical trade is still riding the rise: only the 55-day failsafe, both sides
    assert s1['use20'] is False and s1['buy'] == pytest.approx(159.01) and s1['sell'] == pytest.approx(102.99)
    assert s1['trail_long'] == 148.0 and s1['trail_short'] == 159.0                    # the 10-day channels
    early = T.row_levels(rows, _days(60), 53)                                          # 54 bars: no 55-day channel
    assert early['ok'] is False and early['buy'] is None and early['sell'] is None


def test_n_is_wilders_average_of_the_true_range_seeded_with_its_simple_mean():
    rng = np.random.default_rng(5)
    c = 100 + np.cumsum(rng.normal(0, 1, 80))
    h, l = c + rng.uniform(0.2, 2, 80), c - rng.uniform(0.2, 2, 80)
    o = np.r_[c[0], c[:-1]]
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, 80)]
    want = [np.nan] * 19 + [float(np.mean(tr[:20]))]
    for x in tr[20:]:
        want.append((want[-1] * 19 + x) / 20)
    got = T.daily_rows(o, h, l, c, system=2)['n']
    assert np.isnan(got[:19]).all()
    assert np.allclose(got[19:], want[19:], rtol=1e-12)


def _flat(n=100):
    """A 2-point daily range around 100, and one spike on day 20: a high inside the 55-day window of days 60-74
    but not inside their 20-day one. The spike is itself a hypothetical breakout that loses (out the next day at
    the 10-day low, 99 < 101.01)."""
    o, h, l, c = np.full(n, 100.0), np.full(n, 101.0), np.full(n, 99.0), np.full(n, 100.0)
    h[20] = 120.0
    return o, h, l, c


def test_system1_skips_the_20_day_breakout_after_a_winning_one():
    """A hypothetical 20-day breakout that won makes the next levels the 55-day failsafe, both sides."""
    o, h, l, c = _flat()
    h[60] = 103.0                                  # day 60 breaks the 20-day high (101.01): a hypothetical long
    run = np.arange(61, 72)
    o[run], h[run], c[run] = 104.0, 105.0, 104.0
    l[run] = 103.0 + 0.1 * (run - 61)              # ... rides higher lows ...
    o[72], h[72], l[72], c[72] = 104.0, 104.5, 95.0, 96.0   # ... and is out on day 72 at its 10-day low 103.1 > 101.01
    rows = T.daily_rows(o, h, l, c, system=1)
    assert rows['use20'][59]                        # flat, its last trade (the spike) lost: the 20-day breakout
    assert not rows['use20'][60:72].any()           # in the hypothetical trade: only the failsafe
    lv = T.row_levels(rows, _days(100), 72)
    assert lv['use20'] is False                     # flat again, but the last trade won
    assert lv['buy'] == pytest.approx(120.01) and lv['sell'] == pytest.approx(94.99)   # 55-day, not 105.01
    assert T.row_levels(rows, _days(100), 59)['buy'] == pytest.approx(101.01)
    s2 = T.row_levels(T.daily_rows(o, h, l, c, system=2), _days(100), 72)
    assert s2['use20'] is None and s2['buy'] == pytest.approx(120.01)


def test_system1_takes_the_20_day_breakout_again_after_a_loser():
    o, h, l, c = _flat()
    h[60], l[60] = 103.0, 90.0                     # breaks out and falls through its 2N stop the same day: lost
    rows = T.daily_rows(o, h, l, c, system=1)
    assert rows['use20'][60]
    lv = T.row_levels(rows, _days(100), 60)
    assert lv['buy'] == pytest.approx(103.01)       # the 20-day high again (the 55-day one is 120)


def _book(side=1, n=2.0, trail=97.0, buy=100.0, sell=90.0, bar_time=T0):
    st = T.new_state()
    T.on_new_row(st, dict(bar_time=bar_time, from_time=bar_time + DAY, system=2, n=n, buy=buy, sell=sell,
                          stop_dist=2 * n, add_step=0.5 * n, trail_long=trail if side == 1 else 80.0,
                          trail_short=trail if side == -1 else 120.0, use20=None, ok=True))
    return st


def _row(bar_time, trail_long=80.0, trail_short=120.0, buy=100.0, sell=90.0):
    return dict(bar_time=bar_time, from_time=bar_time + DAY, system=2, n=2.0, buy=buy, sell=sell, stop_dist=4.0,
                add_step=1.0, trail_long=trail_long, trail_short=trail_short, use20=None, ok=True)


def test_the_stop_is_the_tighter_of_2n_and_the_channel_and_never_loosens():
    st = _book(trail=97.0)
    t = T0 + DAY + 3600
    T.on_entry(st, 1, 100.0, t, units=1)
    assert st['stop'] == 97.0 and T.stop_origin(st) == 'channel'      # 2N = 96 is looser than the channel
    T.on_add(st, 101.2, t + 120)
    assert st['stop'] == pytest.approx(97.2) and T.stop_origin(st) == '2N'
    T.on_new_row(st, _row(T0 + DAY, trail_long=98.0))
    assert st['stop'] == 98.0                                          # a D1 close raises it to the channel
    T.on_new_row(st, _row(T0 + 2 * DAY, trail_long=95.0))
    assert st['stop'] == 98.0                                          # a lower channel does not lower it
    T.on_add(st, 102.5, t + DAY)
    assert st['stop'] == pytest.approx(98.5)
    assert T.exit_due(st, 98.51, 98.6) is False and T.exit_due(st, 98.5, 98.6) is True      # a long: on the bid


def test_a_short_mirrors_it_on_the_ask():
    st = _book(side=-1, trail=103.0)
    t = T0 + DAY + 3600
    T.on_entry(st, -1, 100.0, t, units=1)
    assert st['stop'] == 103.0                                         # 2N = 104 is looser
    T.on_add(st, 98.8, t + 120)
    assert st['stop'] == pytest.approx(102.8)
    T.on_new_row(st, _row(T0 + DAY, trail_short=104.0))
    assert st['stop'] == pytest.approx(102.8)                          # never loosened
    assert T.exit_due(st, 102.0, 102.79) is False and T.exit_due(st, 102.0, 102.8) is True


def test_a_leg_closed_outside_the_bot_does_not_loosen_the_stop():
    st = _book(trail=90.0)
    t = T0 + DAY + 3600
    T.on_entry(st, 1, 100.0, t, units=1, ticket=1)
    T.on_add(st, 101.0, t + 60, ticket=2)
    T.on_add(st, 102.0, t + 120, ticket=3)
    assert st['stop'] == 98.0
    T.set_legs(st, [dict(st['legs'][0]), dict(st['legs'][1])])          # the newest leg closed by hand
    assert st['stop'] == 98.0 and T.stop_origin(st) == 'kept'
    assert T.add_level(st) == 102.0                                      # the adds go on from the last open fill
    T.on_add(st, 103.0, t + 180, ticket=4)
    assert st['stop'] == 99.0 and T.stop_origin(st) == '2N'
    fixed = [dict(leg, price=leg['price'] - 0.5) for leg in st['legs']]  # the terminal's actual fills: followed
    T.set_legs(st, fixed)
    assert st['stop'] == 98.5


def test_adds_every_half_n_from_the_actual_fill_not_in_the_entry_bar_at_most_four_legs():
    st = _book()
    t = T0 + DAY + 3600                                                # a minute boundary
    T.on_entry(st, 1, 100.0, t + 10, units=3)
    assert T.add_due(st, 105.0, 105.1, t + 59) is None                 # the entry's M1 bar
    assert T.add_due(st, 100.8, 100.99, t + 60) is None                # below 100 + 0.5N = 101
    assert T.add_due(st, 100.9, 101.0, t + 60) == 101.0
    T.on_add(st, 101.7, t + 60)                                        # filled beyond the level (a gap)
    assert T.add_level(st) == pytest.approx(102.7)                     # the next one from the actual fill
    assert T.add_due(st, 102.5, 102.6, t + 61) is None
    T.on_add(st, 102.7, t + 70)
    T.on_add(st, 103.7, t + 80)
    assert len(st['legs']) == 4 and T.add_due(st, 110.0, 110.1, t + 200) is None
    assert st['units'] == 3 and all(leg['price'] for leg in st['legs'])
    st2 = _book(side=-1, trail=103.0)
    T.on_entry(st2, -1, 100.0, t, units=1)
    assert T.add_due(st2, 99.0, 99.1, t + 60) == 99.0 and T.add_due(st2, 99.01, 99.1, t + 60) is None


def test_entries_need_the_vote_and_one_fill_uses_the_d1_bars_orders():
    st = _book(buy=100.0, sell=90.0)
    t = T0 + DAY + 3600
    called = []
    vote = lambda: called.append(1) or 1
    assert T.entry_due(st, 95.0, 95.1, vote, t) == 0 and not called     # no level reached: the vote is not read
    assert T.entry_due(st, 99.9, 100.0, 0, t) == 0                      # the level, but no agreement
    assert T.entry_due(st, 99.9, 100.0, -1, t) == 0
    assert T.entry_due(st, 99.9, 100.0, 1, t) == 1
    assert T.entry_due(st, 90.0, 90.1, -1, t) == -1 and T.entry_due(st, 90.0, 90.1, 1, t) == 0
    T.on_entry(st, 1, 100.0, t, units=1)
    assert st['armed'] is False and T.entry_due(st, 99.9, 100.0, 1, t + 600) == 0     # in a trade
    T.on_exit(st, t + 3000)
    assert T.entry_due(st, 99.9, 100.5, 1, t + 4000) == 0               # the bar's orders were used: none until
    T.on_new_row(st, _row(T0 + 2 * DAY))                                 # the next D1 bar closes
    exit_t = T0 + 3 * DAY + 600 + 30
    T.on_entry(st, 1, 100.0, T0 + 3 * DAY + 100, units=1)
    T.on_new_row(st, _row(T0 + 3 * DAY))                                 # a bar closed while in the trade
    T.on_exit(st, exit_t)
    assert st['armed'] is True                                           # its orders are still there ...
    assert T.entry_due(st, 89.0, 89.1, -1, exit_t + 29) == 0             # ... but not in the exit's M1 bar
    assert T.entry_due(st, 89.0, 89.1, -1, exit_t + 30) == -1


def test_a_trade_is_rebuilt_from_its_legs_and_the_d1_bars():
    o, h, l, c = _rising(80)
    times = _days(80)
    rows = T.daily_rows(o, h, l, c, system=2)
    # live: the levels of bar 59, a long at 160.5 on day 60, adds, D1 closes on days 61 .. 79
    st = T.new_state()
    T.on_new_row(st, T.row_levels(rows, times, 59))
    t_e = times[60] + 3600
    T.on_entry(st, 1, 160.5, t_e, units=2)
    legs = [(t_e, 160.5)]
    for b in range(60, 80):
        T.on_new_row(st, T.row_levels(rows, times, b))
        if b in (63, 66):
            T.on_add(st, st['legs'][-1]['price'] + 1.3, times[b] + DAY + 600)
            legs.append((times[b] + DAY + 600, st['legs'][-1]['price']))
    rebuilt = T.rebuild(1, [{'price': p, 'time': t, 'ticket': i} for i, (t, p) in enumerate(legs)], 2, rows, times)
    for k in ('side', 'units', 'n_entry', 'stop_dist', 'add_step', 'trail_best', 'stop', 'entry_row', 'row', 'armed'):
        assert rebuilt[k] == st[k], k
    assert [leg['price'] for leg in rebuilt['legs']] == [leg['price'] for leg in st['legs']]
    assert T.rebuild(1, [{'price': 1.0, 'time': times[0], 'ticket': 1}], 1, rows, times) is None   # before the history


def test_the_bot_unit_rule():
    assert [T.unit_rule(b, 2500, 10) for b in (0, 2000, 2499.99, 2500, 7600, 99999)] == [1, 1, 1, 2, 4, 10]


def test_the_vote_searches_the_same_pivots_as_on_the_whole_series():
    """closed_bar_vote reads the last lookback + 2 x width + 2 values, as the backtest; the live 500-bar call on the
    whole series finds the same pivots (map_turtle §7)."""
    ind = _ind.Indicator()
    rng = np.random.default_rng(9)
    closes = 60000 + np.cumsum(rng.normal(0, 40, 1200))
    seen = set()
    for end in range(600, 1200, 7):
        s = pd.Series(closes[:end])
        agree, d = T.closed_bar_vote(s.to_numpy(), ind)
        rsi = ind.calculate_rsi(s, 14, 'RMA')
        macd = ind.calculate_macd(s, 12, 26, 9)
        sig = float(macd['signal'].iloc[-1])
        m = ind.latest_pivot_slope(macd['hist'], 20, 2, side='high' if sig > 0 else ('low' if sig < 0 else None))
        r = ind.latest_pivot_slope(rsi, 20, 2, ob_level=60, os_level=40)
        assert (d['rsi']['sign'], d['macd']['sign']) == (r['sign'], m['sign'])
        assert agree == (r['sign'] if r['sign'] == m['sign'] else 0)
        seen.add(agree)
    assert seen == {-1, 0, 1}
