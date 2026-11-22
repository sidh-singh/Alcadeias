"""
The Turtle with the bot's votes (STRATEGY = 'turtle' in constants.py): the backtest rows "Turtle + bot votes"
(System 1) and "Turtle System 2 + bot votes" of the final ten, rule for rule.

The authority is the backtester on backtest_hedging, backtesting/research/external.py: turtle() (the plan),
_turtle_s1_use20() (the System 1 filter), filtered() + bot_signals() (the vote gate) and _path_kernel() (how the
orders, the stop and the adds are executed on M1 bars). This module holds those rules as pure functions -- no
MetaTrader5, no constants: app.py (MT5TradingBot._process_turtle) feeds it closed bars, quotes, the vote and the
fills and executes what it decides; tests_demo/test_turtle_replay.py feeds it the stored M1 bars and finds the
backtest's trades.

Daily levels: UTC D1 bid bars, CLOSED bars only. The last closed bar sets the levels until the next one closes.
  TR     max(H - L, |H - C_prev|, |L - C_prev|)  (the first bar of the series: H - L)
  N      Wilder's RMA(20) of TR, seeded with the simple mean of the first 20 TRs
  hiK    highest high of the last K bars, the bar that just closed included; loK the lowest low
  System 1  buy level hi20 + 0.01, sell level lo20 - 0.01. On days the skip-after-winner filter skips the 20-day
            breakout (use20 False), the 55-day failsafe instead: hi55 + 0.01 / lo55 - 0.01, both sides.
            Exit channel lo10 (a long) / hi10 (a short).
            The filter is a hypothetical System 1 on the daily bars -- one unit, every 20-day breakout while it is
            flat, a 2N stop from its fill, the previous day's 10-day exit, no adds, no votes -- and use20 is True
            only while it is flat and its last trade did not make money (s1_use20, verbatim).
  System 2  buy level hi55 + 0.01, sell level lo55 - 0.01; exit channel lo20 / hi20. No filter.

Trading (every rule is checked on every poll; the backtest checks them on every M1 bar):
  entry  flat; the entry orders of the last closed D1 bar armed -- an entry fill consumes both of them until the
         next D1 bar closes; a buy when the ask is at or above the buy level and the vote is +1, a sell when the
         bid is at or below the sell level and the vote is -1. The vote is the bot's M15 agreement on the last
         CLOSED M15 bar: the RSI and the MACD-histogram pivot-slope votes both up (+1) or both down (-1). A vote
         that turns while the price is beyond the level enters at once (the backtest's vote-delayed fills, at
         the open of the M1 bar after the M15 close). Never in the M1 bar of the last exit.
  units  the bot's unit rule on the (virtual) balance at the first fill, fixed for the trade; every leg is
         units x 0.01 lot
  N      frozen at the entry: the N of the D1 bar whose orders filled
  adds   one more leg each time the price is 0.5 N beyond the previous actual fill (a long: ask >= last fill +
         0.5 N; a short: bid <= last fill - 0.5 N), up to 4 legs; never in the entry's M1 bar; not gated by the
         votes
  stop   one stop for all legs: the tighter of 2N from the newest fill and the exit channel (of the bar whose
         orders filled); raised to the exit channel each time a D1 bar closes and to 2N from every new fill;
         never loosened. Checked on the bid (a long) / the ask (a short). It is the only exit.
"""
import math

import numpy as np
import pandas as pd

DAY_S = 86400
BAR_S = 60                  # the backtest's resolution: no add in the entry's M1 bar, no entry in an exit's M1 bar
SYSTEMS = (1, 2)
NAN = float('nan')

# the backtest's parameters (external.turtle(): turtle_n(..., 20), sl=2.0*N, pstep=0.5*N, pmax=4, m.tick = 0.01)
DEFAULT_PARAMS = dict(system=2, n_len=20, stop_n=2.0, add_n=0.5, max_legs=4, tick=0.01)


def _finite(x):
    return x is not None and not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)


def _num(x):
    """A float for JSON, None for NaN / infinity / missing."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


# ───────────────────────────── daily bars: N, channels, the System 1 filter ─────────────────────────────

def true_range(h, l, c):
    """external.true_range: max(H - L, |H - C_prev|, |L - C_prev|), the first bar H - L."""
    h, l, c = (np.asarray(x, np.float64) for x in (h, l, c))
    prev = np.concatenate([[np.nan], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    if len(tr):
        tr[0] = h[0] - l[0]
    return tr


def wilder(x, n):
    """external.wilder: Wilder's RMA, seeded with the simple mean of the first n values; NaN before."""
    x = np.asarray(x, np.float64)
    out = np.full(len(x), np.nan)
    good = np.flatnonzero(np.isfinite(x))
    if len(good) < n:
        return out
    s = good[0]
    if s + n > len(x):
        return out
    v = float(np.mean(x[s:s + n]))
    out[s + n - 1] = v
    for i in range(s + n, len(x)):
        v = (v * (n - 1) + x[i]) / n
        out[i] = v
    return out


def roll_max(x, n):
    """Highest value of the last n elements, the current one included (NaN for the first n - 1)."""
    return pd.Series(np.asarray(x, np.float64)).rolling(n, min_periods=n).max().to_numpy()


def roll_min(x, n):
    """Lowest value of the last n elements, the current one included (NaN for the first n - 1)."""
    return pd.Series(np.asarray(x, np.float64)).rolling(n, min_periods=n).min().to_numpy()


def s1_use20(O, H, L, N, hi20, lo20, lo10, hi10, tick):
    """
    external._turtle_s1_use20, verbatim. The System 1 filter, decided at each day's close for the next day:
    True = trade the 20-day breakout, False = only the 55-day failsafe. A hypothetical one-unit System 1 (2N
    stop, 10-day exit, no adds) is run on the daily bars; a breakout is skipped when the last hypothetical
    breakout trade made money. The outcome of a trade is known from the close of the day it ended.
    """
    nb = len(O)
    use20 = np.zeros(nb, np.bool_)
    hyp = 0
    entry = 0.0
    stop = 0.0
    last_win = False
    for b in range(nb):
        if b >= 1:
            if hyp == 0 and hi20[b - 1] == hi20[b - 1] and N[b - 1] == N[b - 1]:
                up_l = hi20[b - 1] + tick
                dn_l = lo20[b - 1] - tick
                up = H[b] >= up_l
                dn = L[b] <= dn_l
                if up and dn:
                    if up_l - O[b] <= O[b] - dn_l:
                        dn = False
                    else:
                        up = False
                if up:
                    hyp = 1
                    entry = max(up_l, O[b])
                    stop = entry - 2.0 * N[b - 1]
                    if L[b] <= stop:
                        hyp = 0
                        last_win = False
                elif dn:
                    hyp = -1
                    entry = min(dn_l, O[b])
                    stop = entry + 2.0 * N[b - 1]
                    if H[b] >= stop:
                        hyp = 0
                        last_win = False
            elif hyp == 1:
                ex = stop
                if lo10[b - 1] == lo10[b - 1] and lo10[b - 1] > ex:
                    ex = lo10[b - 1]
                if O[b] <= ex:
                    last_win = O[b] > entry
                    hyp = 0
                elif L[b] <= ex:
                    last_win = ex > entry
                    hyp = 0
            elif hyp == -1:
                ex = stop
                if hi10[b - 1] == hi10[b - 1] and hi10[b - 1] < ex:
                    ex = hi10[b - 1]
                if O[b] >= ex:
                    last_win = O[b] < entry
                    hyp = 0
                elif H[b] >= ex:
                    last_win = ex < entry
                    hyp = 0
        use20[b] = hyp == 0 and not last_win
    return use20


def daily_rows(o, h, l, c, system=2, n_len=20, stop_n=2.0, add_n=0.5, tick=0.01, **_):
    """
    What every closed D1 bar of the series sets for the days after it (arrays, one element per bar), as
    external.turtle() builds the plan: 'buy' / 'sell' the entry levels, 'stop_dist' = 2N and 'add_step' = 0.5N
    (NaN where N or a channel is not known yet: no orders), 'trail_long' / 'trail_short' the exit channel,
    'n', 'use20' (System 1; None for System 2) and the channels for display.
    """
    if system not in SYSTEMS:
        raise ValueError(f'Turtle system {system!r} is not 1 or 2')
    O, H, L, C = (np.asarray(x, np.float64) for x in (o, h, l, c))
    N = wilder(true_range(H, L, C), n_len)
    hi20, lo20 = roll_max(H, 20), roll_min(L, 20)
    hi55, lo55 = roll_max(H, 55), roll_min(L, 55)
    hi10, lo10 = roll_max(H, 10), roll_min(L, 10)
    if system == 1:
        use20 = s1_use20(O, H, L, N, hi20, lo20, lo10, hi10, tick)
        hi_e, lo_e = np.where(use20, hi20, hi55), np.where(use20, lo20, lo55)
        trl, trs = lo10, hi10
    else:
        use20 = None
        hi_e, lo_e = hi55, lo55
        trl, trs = lo20, hi20
    ok = np.isfinite(N) & np.isfinite(hi_e) & np.isfinite(lo_e)
    return {
        'system': int(system),
        'n': N,
        'buy': np.where(ok, hi_e + tick, np.nan),
        'sell': np.where(ok, lo_e - tick, np.nan),
        'stop_dist': np.where(ok, stop_n * N, np.nan),
        'add_step': np.where(ok, add_n * N, np.nan),
        'trail_long': trl,
        'trail_short': trs,
        'use20': use20,
        'ok': ok,
        'hi_entry': hi_e, 'lo_entry': lo_e,
    }


def row_levels(rows, times, b):
    """The levels D1 bar `b` (open time times[b], UTC seconds) sets, as a JSON-ready dict."""
    use20 = rows['use20']
    return {
        'bar_time': int(times[b]),                 # the D1 bar these levels come from
        'from_time': int(times[b]) + DAY_S,        # they apply from its close (00:00 UTC of the next day)
        'system': rows['system'],
        'n': _num(rows['n'][b]),
        'buy': _num(rows['buy'][b]),
        'sell': _num(rows['sell'][b]),
        'stop_dist': _num(rows['stop_dist'][b]),
        'add_step': _num(rows['add_step'][b]),
        'trail_long': _num(rows['trail_long'][b]),
        'trail_short': _num(rows['trail_short'][b]),
        'use20': None if use20 is None else bool(use20[b]),
        'ok': bool(rows['ok'][b]),
    }


def entry_row_index(times, t):
    """Index of the D1 bar whose levels were in force at time `t`: the last bar closed by then
    (open time + 1 day <= t); -1 when there is none."""
    closes = np.asarray(times, np.int64) + DAY_S
    return int(np.searchsorted(closes, float(t), side='right')) - 1


# ───────────────────────────── the M15 vote (closed bars) ─────────────────────────────

def closed_bar_vote(closes, indicator, rsi_length=14, rsi_ma_type='RMA', macd_fast=12, macd_slow=26, macd_signal=9,
                    lookback=20, width=2, rsi_ob=60, rsi_os=40):
    """
    The bot's agreement on the LAST bar of `closes` (closes of CLOSED bars only, oldest first): +1 when the RSI
    pivot-slope vote and the MACD-histogram pivot-slope vote are both +1, -1 when both are -1, else 0. Computed
    as the backtest does (backtesting/analysis/signal.py votes() -> external.bot_signals' m15_agree): the live
    indicator.py functions, the bar itself as the current value, the MACD pivot side from its own signal line,
    the last lookback + 2 x width + 2 values searched. Returns (agree, {'rsi': ..., 'macd': ...}).
    """
    s = pd.Series(np.asarray(closes, np.float64))
    none = {'side': None, 'value': None, 'bars_ago': None, 'slope': 0.0, 'sign': 0}
    if len(s) < 2 * width + 1:
        return 0, {'rsi': dict(none), 'macd': dict(none)}
    rsi = indicator.calculate_rsi(s, length=rsi_length, ma_type=rsi_ma_type)
    macd = indicator.calculate_macd(s, fast=macd_fast, slow=macd_slow, signal=macd_signal)
    sig = float(macd['signal'].iloc[-1])
    side = 'high' if sig > 0 else ('low' if sig < 0 else None)
    look = int(lookback) + 2 * int(width) + 2
    m = indicator.latest_pivot_slope(macd['hist'].iloc[-look:], lookback=lookback, width=width, side=side)
    r = indicator.latest_pivot_slope(rsi.iloc[-look:], lookback=lookback, width=width, ob_level=rsi_ob, os_level=rsi_os)
    agree = 1 if (m['sign'] == 1 and r['sign'] == 1) else (-1 if (m['sign'] == -1 and r['sign'] == -1) else 0)
    return agree, {'rsi': r, 'macd': m}


# ───────────────────────────── sizing ─────────────────────────────

def unit_rule(balance, step_up_balance, max_limit):
    """The bot's unit (app.py): floor(balance / step_up_balance) + 1, between 1 and max_limit."""
    if step_up_balance and step_up_balance > 0:
        units = int(balance // step_up_balance) + 1
    else:
        units = 1
    return max(1, min(units, int(max_limit)))


# ───────────────────────────── the trade state ─────────────────────────────

def bar_of(t):
    """The M1 bar (minute) a time in seconds falls in."""
    return int(math.floor(float(t) / BAR_S))


def new_state():
    """A flat book with no orders armed yet. JSON-ready (app.py persists it in OUTPUT_DIR/state)."""
    return {
        'side': 0,              # +1 long, -1 short, 0 flat
        'units': 0,             # lot units per leg (x 0.01 lot), fixed at the first fill
        'legs': [],             # [{'price', 'time', 'ticket'}], oldest first; live: the terminal's positions
        'n_entry': None,        # N frozen at the entry
        'stop_dist': None,      # 2 N_entry
        'add_step': None,       # 0.5 N_entry
        'trail_best': None,     # the tightest exit channel seen since the entry (the entry bar's and every later bar's)
        'stop_floor': None,     # the stop before a leg was closed outside the bot (it never loosens)
        'stop': None,           # the one stop of all legs (derived: trade_stop)
        'entry_time': None,     # first fill (seconds)
        'entry_row': None,      # bar_time of the D1 bar whose orders filled
        'row': None,            # bar_time of the last D1 bar processed (its levels are in 'levels')
        'levels': None,         # row_levels() of that bar
        'armed': False,         # that bar's entry orders are still there (no entry fill since it closed)
        'last_exit_time': None,
        'closing': False,       # an exit was decided and some legs are still open
    }


def last_fill(st):
    return st['legs'][-1]['price'] if st['legs'] else None


def trade_stop(st):
    """The stop of the open trade: the tighter of 2 N_entry from the newest fill (a long: the highest fill) and the
    tightest exit channel seen since the entry. The same number as the backtest's ratchet (every step a max), so it
    never loosens: fills only ever move it to 2N from a better price, D1 closes only to a tighter channel."""
    side = st['side']
    if side == 0 or not st['legs'] or not _finite(st['stop_dist']):
        return None
    fills = [float(leg['price']) for leg in st['legs']]
    tb, fl = st['trail_best'], st.get('stop_floor')
    if side == 1:
        s = max(fills) - st['stop_dist']
        if _finite(tb) and tb > s:
            s = tb
        if _finite(fl) and fl > s:
            s = fl
    else:
        s = min(fills) + st['stop_dist']
        if _finite(tb) and tb < s:
            s = tb
        if _finite(fl) and fl < s:
            s = fl
    return float(s)


def stop_origin(st):
    """'2N', 'channel' or 'kept' (where it was before a leg was closed outside the bot): what the stop is now."""
    s = trade_stop(st)
    if s is None:
        return None
    tb, fl = st['trail_best'], st.get('stop_floor')
    if _finite(tb) and tb == s:
        return 'channel'
    return 'kept' if (_finite(fl) and fl == s) else '2N'


def _leg(price, time, ticket=None):
    return {'price': float(price), 'time': float(time), 'ticket': None if ticket is None else int(ticket)}


def on_new_row(st, lv):
    """A D1 bar closed: an open trade's stop is raised to that bar's exit channel (never lowered), and the bar's
    entry orders replace the previous ones (external._path_kernel step 2)."""
    if st['side'] != 0:
        tr = lv['trail_long'] if st['side'] == 1 else lv['trail_short']
        if _finite(tr):
            tb = st['trail_best']
            if not _finite(tb) or (st['side'] == 1 and tr > tb) or (st['side'] == -1 and tr < tb):
                st['trail_best'] = float(tr)
        st['stop'] = trade_stop(st)
    st['row'] = lv['bar_time']
    st['levels'] = dict(lv)
    st['armed'] = True


def exit_due(st, bid, ask):
    """The stop is hit: a long on the bid at or below it, a short on the ask at or above it."""
    if st['side'] == 0 or st['stop'] is None:
        return False
    if st['side'] == 1:
        return bid is not None and bid <= st['stop']
    return ask is not None and ask >= st['stop']


def add_level(st):
    """The price of the next add: 0.5 N_entry beyond the last actual fill (None when flat)."""
    lf = last_fill(st)
    if st['side'] == 0 or lf is None or not _finite(st['add_step']):
        return None
    return lf + st['add_step'] if st['side'] == 1 else lf - st['add_step']


def add_due(st, bid, ask, now, max_legs=4):
    """The level of a pyramid add that is due now, else None: fewer than max_legs legs, not in the entry's M1 bar,
    and a long's ask at or above the last fill + 0.5 N_entry (a short's bid at or below the last fill - 0.5 N_entry).
    Not gated by the votes."""
    if st['side'] == 0 or st['closing'] or len(st['legs']) >= int(max_legs):
        return None
    if st['entry_time'] is None or bar_of(now) <= bar_of(st['entry_time']):
        return None
    lvl = add_level(st)
    if lvl is None:
        return None
    if st['side'] == 1:
        return lvl if (ask is not None and ask >= lvl) else None
    return lvl if (bid is not None and bid <= lvl) else None


def entry_due(st, bid, ask, vote, now):
    """
    +1 / -1 when an entry is due now, else 0: flat, the last D1 bar's orders armed, not in the M1 bar of the last
    exit, and a buy level reached by the ask with the vote +1 (a sell level reached by the bid with the vote -1).
    `vote` may be a function: it is called only when a level is reached.
    """
    if st['side'] != 0 or not st['armed'] or not st['levels']:
        return 0
    if st['last_exit_time'] is not None and bar_of(now) <= bar_of(st['last_exit_time']):
        return 0
    lv = st['levels']
    hb = _finite(lv['buy']) and ask is not None and ask >= lv['buy']
    hs = _finite(lv['sell']) and bid is not None and bid <= lv['sell']
    if not (hb or hs):
        return 0
    v = vote() if callable(vote) else vote
    if hb and v == 1:
        return 1
    if hs and v == -1:
        return -1
    return 0


def on_entry(st, side, price, time, units, ticket=None):
    """The entry filled at `price`: N, 2N and 0.5N of the bar whose orders filled are frozen, the stop is the tighter
    of 2N and that bar's exit channel, and both of its orders are gone until the next D1 bar closes."""
    lv = st['levels']
    tr = lv['trail_long'] if side == 1 else lv['trail_short']
    st.update(side=int(side), units=int(units), legs=[_leg(price, time, ticket)], n_entry=lv['n'],
              stop_dist=lv['stop_dist'], add_step=lv['add_step'], trail_best=tr if _finite(tr) else None,
              stop_floor=None, entry_time=float(time), entry_row=lv['bar_time'], armed=False, closing=False)
    st['stop'] = trade_stop(st)


def on_add(st, price, time, ticket=None):
    """An add filled at `price`: one more leg; the stop moves to 2N from it if that is tighter."""
    st['legs'].append(_leg(price, time, ticket))
    st['stop'] = trade_stop(st)


def set_legs(st, legs):
    """The legs as the terminal shows them (oldest first): the actual fills; the stop follows them. A leg gone (closed
    outside the bot) does not loosen the stop: it stays where it was."""
    before = st['stop']
    gone = {leg.get('ticket') for leg in st['legs']} - {leg.get('ticket') for leg in legs} - {None}
    st['legs'] = [dict(leg) for leg in legs]
    st['stop'] = trade_stop(st)
    if gone and _finite(before) and st['stop'] is not None and (
            (st['side'] == 1 and st['stop'] < before) or (st['side'] == -1 and st['stop'] > before)):
        st['stop_floor'] = float(before)
        st['stop'] = trade_stop(st)


def on_exit(st, time):
    """The trade is closed. The armed orders stay as they are: if a D1 bar closed since the entry, its orders are
    still there and a new breakout can fill the same day (from the next M1 bar)."""
    keep = {k: st[k] for k in ('row', 'levels', 'armed')}
    st.clear()
    st.update(new_state())
    st.update(keep)
    st['last_exit_time'] = float(time)


def rebuild(side, legs, units, rows, times, max_legs=4):
    """
    The state of a trade found open without its book (a first start, a lost state file): `legs` the open
    positions [{'price', 'time', 'ticket'}] oldest first, `rows` / `times` the daily rows of the closed D1 bars.
    The entry bar is the last D1 bar closed before the first leg opened; its N, 2N, 0.5N and exit channel are
    taken, the later legs are the adds, and every D1 bar closed since raises the stop: the same numbers the
    trade would have had. None when the D1 history does not reach back to the entry.
    """
    if not legs:
        return None
    b_e = entry_row_index(times, legs[0]['time'])
    if b_e < 0:
        return None
    st = new_state()
    on_new_row(st, row_levels(rows, times, b_e))
    if not st['levels']['ok']:
        return None
    on_entry(st, side, legs[0]['price'], legs[0]['time'], units, legs[0].get('ticket'))
    for leg in legs[1:]:
        on_add(st, leg['price'], leg['time'], leg.get('ticket'))
    for b in range(b_e + 1, len(times)):
        on_new_row(st, row_levels(rows, times, b))
    return st


def describe(system):
    """One line for the startup print and the dashboard."""
    if system == 1:
        return ('Turtle System 1 + bot votes: 20-day breakout (55-day failsafe after a winning breakout), 10-day exit, '
                '2N stop, an add every 0.5N up to 4 legs, entries on the M15 votes of closed bars')
    return ('Turtle System 2 + bot votes: 55-day breakout, 20-day exit, 2N stop, an add every 0.5N up to 4 legs, '
            'entries on the M15 votes of closed bars')
