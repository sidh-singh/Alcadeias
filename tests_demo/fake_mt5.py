"""
A fake MetaTrader5 terminal for the demo-branch tests, and a loader that runs the bot's own
``process_symbol`` against it with a simulated clock.

The terminal is a hedging account on one symbol:
  * quotes come from a tick array (t_ms, bid, ask); the clock decides which ticks have arrived;
  * bars of every timeframe are grown from the bid, forming bar included (as copy_rates_from_pos(...,0,n)
    returns it), seeded with history bars resampled from M1 bars;
  * positions carry ticket / identifier / magic / comment / time / time_msc; profit is rounded to cents
    half away from zero per position (as MT5 reports it);
  * order_send fills market orders at the ask (buy) / bid (sell) and closes at the bid / ask, writing
    DEAL_ENTRY_IN / DEAL_ENTRY_OUT deals with the request's magic and comment;
  * history_deals_get(date_from, date_to) returns the deals in that time range;
  * account_info() reports a demo, hedging account (login / trade_mode / margin_mode can be changed).
Failures can be injected (refused orders, failed closes, no history), and anything can be scheduled at a
terminal time with at(t_s, fn) (an account switch ...).
"""
import math
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TF_SECONDS = {'M1': 60, 'M2': 120, 'M3': 180, 'M4': 240, 'M5': 300, 'M6': 360, 'M10': 600, 'M12': 720,
              'M15': 900, 'M20': 1200, 'M30': 1800, 'H1': 3600, 'H2': 7200, 'H3': 10800, 'H4': 14400,
              'H6': 21600, 'H8': 28800, 'H12': 43200, 'D1': 86400}
TF_CODES = {'M1': 1, 'M2': 2, 'M3': 3, 'M4': 4, 'M5': 5, 'M6': 6, 'M10': 10, 'M12': 12, 'M15': 15,
            'M20': 20, 'M30': 30, 'H1': 16385, 'H2': 16386, 'H3': 16387, 'H4': 16388, 'H6': 16390,
            'H8': 16392, 'H12': 16396, 'D1': 16408}
TF_BY_CODE = {v: k for k, v in TF_CODES.items()}
RATES_DTYPE = np.dtype([('time', '<i8'), ('open', '<f8'), ('high', '<f8'), ('low', '<f8'), ('close', '<f8'),
                        ('tick_volume', '<u8'), ('spread', '<i4'), ('real_volume', '<u8')])


class StopRun(BaseException):
    """The simulated clock reached the end of the run."""


class Restart(BaseException):
    """The simulated clock reached a scheduled restart: the bot process 'dies'."""


def round2(x):
    if x >= 0.0:
        return math.floor(x * 100.0 + 0.5) / 100.0
    return -math.floor(-x * 100.0 + 0.5) / 100.0


class FakeClock:
    """Stands in for the `time` module of app.py / mt5_helper.py. Time moves only through sleep()."""

    def __init__(self, start_s, end_s, restarts_s=()):
        self.now_ms = int(round(start_s * 1000))
        self.end_ms = int(round(end_s * 1000))
        self.restarts_ms = sorted(int(round(r * 1000)) for r in restarts_s)

    def time(self):
        return self.now_ms / 1000.0

    def perf_counter(self):
        return self.now_ms / 1000.0

    def sleep(self, seconds):
        self.now_ms += int(round(float(seconds) * 1000.0))
        if self.now_ms >= self.end_ms:
            raise StopRun()
        if self.restarts_ms and self.now_ms >= self.restarts_ms[0]:
            self.restarts_ms.pop(0)
            raise Restart()


def resample(m1, tf_s):
    """OHLC bars of `tf_s` seconds from M1 bars (dict of arrays t/o/h/l/c/n)."""
    b = m1['t'] // tf_s
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    ends = np.r_[starts[1:], len(b)]
    return {
        't': b[starts] * tf_s,
        'o': m1['o'][starts],
        'h': np.maximum.reduceat(m1['h'], starts),
        'l': np.minimum.reduceat(m1['l'], starts),
        'c': m1['c'][ends - 1],
        'n': np.add.reduceat(m1['n'], starts),
    }


class Bars:
    """Growing OHLC bars of one timeframe, built tick by tick from the bid."""

    def __init__(self, tf_s, seed=None, cap=None):
        self.tf_s = tf_s
        k = len(seed['t']) if seed else 0
        cap = (cap or 0) + k + 16
        self.t = np.zeros(cap, np.int64)
        self.o = np.zeros(cap)
        self.h = np.zeros(cap)
        self.l = np.zeros(cap)
        self.c = np.zeros(cap)
        self.v = np.zeros(cap, np.uint64)
        self.n = 0
        self.cur = -1
        if k:
            self.t[:k], self.o[:k], self.h[:k], self.l[:k], self.c[:k] = seed['t'], seed['o'], seed['h'], seed['l'], seed['c']
            self.v[:k] = seed['n']
            self.n = k
            self.cur = int(seed['t'][-1] // tf_s)

    def on_tick(self, t_s, price):
        b = t_s // self.tf_s
        if b != self.cur:
            if self.n >= len(self.t):
                for name in ('t', 'o', 'h', 'l', 'c', 'v'):
                    arr = getattr(self, name)
                    setattr(self, name, np.concatenate([arr, np.zeros_like(arr)]))
            i = self.n
            self.t[i] = b * self.tf_s
            self.o[i] = self.h[i] = self.l[i] = self.c[i] = price
            self.v[i] = 1
            self.n += 1
            self.cur = b
        else:
            i = self.n - 1
            self.h[i] = max(self.h[i], price)
            self.l[i] = min(self.l[i], price)
            self.c[i] = price
            self.v[i] += 1

    def last(self, count, upto_t=None):
        n = self.n
        if upto_t is not None:
            n = int(np.searchsorted(self.t[:self.n], upto_t, side='right'))
        lo = max(0, n - int(count))
        out = np.zeros(n - lo, RATES_DTYPE)
        out['time'], out['open'], out['high'] = self.t[lo:n], self.o[lo:n], self.h[lo:n]
        out['low'], out['close'], out['tick_volume'] = self.l[lo:n], self.c[lo:n], self.v[lo:n]
        return out


class FakeMT5:
    """The slice of the MetaTrader5 module the bot uses, as a hedging account on one symbol."""

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_REJECT = 10006
    TRADE_RETCODE_MARKET_CLOSED = 10018
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1
    DEAL_TYPE_BALANCE = 2
    COPY_TICKS_ALL = -1
    SYMBOL_TRADE_MODE_DISABLED = 0
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
    ACCOUNT_MARGIN_MODE_EXCHANGE = 1
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

    def __init__(self, symbol, t_ms, bid, ask, clock, warm_m1=None, contract_size=100.0, balance=2000.0,
                 leverage=2000, warm_bars=600, report_contract_size=True):
        self.symbol = symbol
        self.t_ms = np.asarray(t_ms, np.int64)
        self.bid = np.asarray(bid, float)
        self.ask = np.asarray(ask, float)
        self.clock = clock
        self.contract = float(contract_size)
        self.balance = float(balance)
        self.leverage = leverage
        self.report_contract_size = report_contract_size
        self.ptr = -1
        self.positions = []
        self.deals = []
        self.orders = []            # every request sent, as sent
        self.iter_t = clock.now_ms  # start of the bot's current loop pass
        self._ticket = 100000
        self._deal_ticket = 500000
        # the account the terminal is logged into (change them to switch it)
        self.account_login = 1
        self.trade_mode = self.ACCOUNT_TRADE_MODE_DEMO
        self.margin_mode = self.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
        self.calls = []             # (name, terminal ms) of initialize / login / shutdown
        self._hooks = []            # [(t_ms, fn)]: fn(self) runs once the clock reaches t_ms (see at())
        # failure injection
        self.refuse_orders = 0      # refuse the next N new orders (not closes)
        self.fail_close_tickets = set()
        self.history_none = False   # history_deals_get returns None (terminal error)
        self.positions_none = []    # [(from_ms, to_ms)]: positions_get answers None (an error) in these windows
        self._error = (1, 'Success')
        for name, code in TF_CODES.items():
            setattr(self, 'TIMEFRAME_' + name, code)
        span = int((self.t_ms[-1] - self.t_ms[0]) // 1000) + 1 if len(self.t_ms) else 0
        self.bars = {}
        for name, tf_s in TF_SECONDS.items():
            seed = None
            if warm_m1 is not None and len(warm_m1['t']):
                rs = resample(warm_m1, tf_s)
                seed = {k: v[-warm_bars:] for k, v in rs.items()}
            self.bars[name] = Bars(tf_s, seed, span // tf_s + 2)

    # ── time: the terminal knows every tick up to "now" ──
    def at(self, t_s, fn):
        """Run fn(self) once, at the first terminal call at or after terminal time t_s (seconds)."""
        self._hooks.append((int(round(t_s * 1000)), fn))
        self._hooks.sort(key=lambda h: h[0])

    def fail_positions(self, from_s, to_s):
        """positions_get answers None (a terminal error) from terminal time from_s to to_s (seconds)."""
        self.positions_none.append((int(round(from_s * 1000)), int(round(to_s * 1000))))

    @staticmethod
    def _within(windows, now_ms):
        return any(a <= now_ms < b for a, b in windows)

    def _run_hooks(self):
        now = self.clock.now_ms
        while self._hooks and self._hooks[0][0] <= now:
            self._hooks.pop(0)[1](self)

    def _sync(self):
        self._run_hooks()
        now = self.clock.now_ms
        while self.ptr + 1 < len(self.t_ms) and self.t_ms[self.ptr + 1] <= now:
            self.ptr += 1
            ts = int(self.t_ms[self.ptr] // 1000)
            px = float(self.bid[self.ptr])
            for b in self.bars.values():
                b.on_tick(ts, px)

    def quote(self):
        self._sync()
        if self.ptr < 0:
            return None, None
        return float(self.bid[self.ptr]), float(self.ask[self.ptr])

    # ── session ──
    def initialize(self, *a, **k):
        self.calls.append(('initialize', self.clock.now_ms))
        return True

    def login(self, *a, **k):
        self.calls.append(('login', self.clock.now_ms))
        return True

    def shutdown(self):
        self.calls.append(('shutdown', self.clock.now_ms))
        return True

    def version(self):
        return (5, 0, 4738)

    def last_error(self):
        return self._error

    # ── account ──
    def _pos_profit(self, p, b, a):
        if p['type'] == 0:
            return round2((b - p['price_open']) * p['volume'] * self.contract)
        return round2((p['price_open'] - a) * p['volume'] * self.contract)

    def account_info(self):
        b, a = self.quote()
        profit = sum(self._pos_profit(p, b, a) for p in self.positions) if b is not None else 0.0
        margin = sum(p['volume'] * self.contract * p['price_open'] / self.leverage for p in self.positions)
        equity = self.balance + profit
        return types.SimpleNamespace(login=self.account_login, trade_mode=self.trade_mode,
                                     margin_mode=self.margin_mode, server='Fake-Demo', leverage=self.leverage,
                                     balance=self.balance, equity=equity, margin=margin, margin_free=equity - margin,
                                     margin_level=(equity / margin * 100.0) if margin else 0.0, profit=profit)

    # ── symbols / quotes / bars ──
    def symbol_info(self, symbol):
        if symbol != self.symbol:
            return None
        info = dict(name=symbol, visible=True, select=True, trade_mode=4, digits=3, point=0.001,
                    volume_min=0.01, volume_step=0.01)
        if self.report_contract_size:
            info['trade_contract_size'] = self.contract
        return types.SimpleNamespace(**info)

    def symbol_select(self, symbol, enable=True):
        # the bot's first call of every loop pass: it stamps the pass (as the backtester's reference replay does)
        self.iter_t = self.clock.now_ms
        return symbol == self.symbol

    def symbols_get(self, pattern=None):
        return ()

    def symbol_info_tick(self, symbol):
        if symbol != self.symbol:
            return None
        self._sync()
        if self.ptr < 0:
            return None
        i = self.ptr
        return types.SimpleNamespace(time=int(self.t_ms[i] // 1000), time_msc=int(self.t_ms[i]),
                                     bid=float(self.bid[i]), ask=float(self.ask[i]), last=0.0, volume=0)

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        if symbol != self.symbol:
            return None
        self._sync()
        assert start_pos == 0
        return self.bars[TF_BY_CODE[int(timeframe)]].last(int(count))

    def copy_rates_from(self, symbol, timeframe, date_from, count):
        if symbol != self.symbol:
            return None
        self._sync()
        ts = int(date_from.timestamp()) if hasattr(date_from, 'timestamp') else int(date_from)
        return self.bars[TF_BY_CODE[int(timeframe)]].last(int(count), upto_t=ts)

    def copy_ticks_from(self, *a, **k):
        return None

    # ── positions / orders / deals ──
    def positions_get(self, symbol=None, **k):
        b, a = self.quote()
        if self._within(self.positions_none, self.clock.now_ms):
            self._error = (-1, 'Terminal: Call failed')
            return None
        self._error = (1, 'Success')
        if b is None or (symbol is not None and symbol != self.symbol):
            return ()
        return tuple(types.SimpleNamespace(
            ticket=p['ticket'], identifier=p['ticket'], type=p['type'], volume=p['volume'],
            price_open=p['price_open'], symbol=self.symbol, profit=self._pos_profit(p, b, a),
            time=p['time_msc'] // 1000, time_msc=p['time_msc'], swap=0.0, magic=p['magic'],
            comment=p['comment']) for p in self.positions)

    def add_position(self, type_, volume, price_open, time_s, magic=0, comment=''):
        """Put a position on the account directly (a foreign trade, or one opened before a restart)."""
        self._ticket += 1
        p = dict(ticket=self._ticket, type=type_, volume=volume, price_open=price_open,
                 time_msc=int(round(time_s * 1000)), magic=magic, comment=comment)
        self.positions.append(p)
        self._deal(p, 0, volume, price_open, 0.0, magic, comment, p['time_msc'])
        return p['ticket']

    def add_deal(self, position_id, type_, entry, volume, price, profit, time_s, magic, commission=0.0, swap=0.0):
        """Write a deal into the history directly."""
        self._deal_ticket += 1
        self.deals.append(types.SimpleNamespace(
            ticket=self._deal_ticket, order=self._deal_ticket, time=int(time_s), time_msc=int(round(time_s * 1000)),
            type=type_, entry=entry, magic=magic, position_id=position_id, reason=0, volume=volume, price=price,
            commission=commission, swap=swap, profit=profit, fee=0.0, symbol=self.symbol, comment='',
            external_id=''))
        self.balance += profit + commission + swap

    def _deal(self, p, entry, volume, price, profit, magic, comment, t_msc):
        self._deal_ticket += 1
        deal_type = p['type'] if entry == 0 else 1 - p['type']
        self.deals.append(types.SimpleNamespace(
            ticket=self._deal_ticket, order=self._deal_ticket, time=t_msc // 1000, time_msc=t_msc,
            type=deal_type, entry=entry, magic=magic, position_id=p['ticket'], reason=3, volume=volume,
            price=price, commission=0.0, swap=0.0, profit=profit, fee=0.0, symbol=self.symbol,
            comment=comment, external_id=''))

    def order_send(self, request):
        self.orders.append(dict(request, _t_ms=self.clock.now_ms))
        b, a = self.quote()
        now = self.clock.now_ms
        if 'position' in request:
            for k, p in enumerate(self.positions):
                if p['ticket'] == request['position']:
                    if p['ticket'] in self.fail_close_tickets:
                        return types.SimpleNamespace(retcode=self.TRADE_RETCODE_REJECT, price=0.0, volume=0.0,
                                                     order=0, deal=0, comment='rejected')
                    price = b if p['type'] == 0 else a
                    profit = self._pos_profit(p, price, price)
                    self.balance += profit
                    self._deal(p, 1, p['volume'], price, profit, request.get('magic', 0),
                               request.get('comment', ''), now)
                    del self.positions[k]
                    return types.SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, price=price, volume=p['volume'],
                                                 order=p['ticket'], deal=self._deal_ticket, comment='done')
            return types.SimpleNamespace(retcode=10013, price=0.0, volume=0.0, order=0, deal=0, comment='invalid')
        if self.refuse_orders > 0:
            self.refuse_orders -= 1
            return types.SimpleNamespace(retcode=self.TRADE_RETCODE_MARKET_CLOSED, price=0.0, volume=0.0,
                                         order=0, deal=0, comment='market closed')
        typ = int(request['type'])
        vol = round2(float(request['volume']))
        price = a if typ == self.ORDER_TYPE_BUY else b
        self._ticket += 1
        p = dict(ticket=self._ticket, type=typ, volume=vol, price_open=price, time_msc=now,
                 magic=request.get('magic', 0), comment=request.get('comment', ''))
        self.positions.append(p)
        self._deal(p, 0, vol, price, 0.0, p['magic'], p['comment'], now)
        return types.SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, price=price, volume=vol,
                                     order=self._ticket, deal=self._deal_ticket, comment='done')

    def history_deals_get(self, date_from=None, date_to=None, **k):
        if self.history_none:
            return None
        lo = date_from.timestamp() if hasattr(date_from, 'timestamp') else float(date_from)
        hi = date_to.timestamp() if hasattr(date_to, 'timestamp') else float(date_to)
        return tuple(d for d in self.deals if lo <= d.time <= hi)


# ───────────────────────────── synthetic markets ─────────────────────────────

def random_walk_market(start_s, run_s, seed=1, price0=2000.0, sigma_per_s=0.08, spread=0.12,
                       tick_every_s=1, warm_days=140):
    """M1 history bars before `start_s` and one tick every `tick_every_s` seconds for `run_s` seconds."""
    rng = np.random.default_rng(seed)
    n_m1 = int(warm_days * 1440)
    t_m1 = (int(start_s) // 60) * 60 - 60 * np.arange(n_m1, 0, -1)
    steps = rng.normal(0.0, sigma_per_s * math.sqrt(15.0), (n_m1, 4))
    path = price0 + np.cumsum(steps.ravel())
    path = path.reshape(n_m1, 4)
    o, c = path[:, 0], path[:, 3]
    h, l = path.max(axis=1), path.min(axis=1)
    m1 = {'t': t_m1.astype(np.int64), 'o': o, 'h': h, 'l': l, 'c': c, 'n': np.full(n_m1, 60, np.int64)}
    n_t = int(run_s // tick_every_s)
    t_ms = (int(start_s) * 1000 + 1000 * tick_every_s * np.arange(n_t) + 137).astype(np.int64)
    bid = c[-1] + np.cumsum(rng.normal(0.0, sigma_per_s * math.sqrt(tick_every_s), n_t))
    ask = bid + spread
    return m1, t_ms, bid, ask


# ───────────────────────────── loading and running the bot ─────────────────────────────

_MODULES = ('MetaTrader5', 'constants', 'strategy', 'indicator', 'mt5_helper', 'app')


@contextmanager
def bot_modules(root, fake, clock, overrides=None):
    """Import the bot's modules from `root` with MetaTrader5 = `fake` and the simulated clock patched in.
    `overrides` = {CONSTANT: value}, set on every bot module that has the name (they read it at call time)."""
    root = str(Path(root).resolve())
    saved = {n: sys.modules.get(n) for n in _MODULES}
    for n in _MODULES:
        sys.modules.pop(n, None)
    sys.modules['MetaTrader5'] = fake
    sys.path.insert(0, root)
    try:
        import app  # noqa: F401
        mods = types.SimpleNamespace(**{n: sys.modules[n] for n in _MODULES})

        class _SimDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromtimestamp(clock.time(), tz=tz or timezone.utc)

        mods.app.time = clock
        mods.mt5_helper.time = clock
        mods.mt5_helper.datetime = _SimDatetime
        for name, value in (overrides or {}).items():
            hit = False
            for m in (mods.constants, mods.strategy, mods.app, mods.mt5_helper):
                if hasattr(m, name):
                    setattr(m, name, value)
                    hit = True
            assert hit, f'no bot module has {name}'
        yield mods
    finally:
        try:
            sys.path.remove(root)
        except ValueError:
            pass
        for n in _MODULES:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


class Run:
    """What one replay of the bot produced."""

    def __init__(self):
        self.polls = []       # one compact row per loop pass
        self.events = []
        self.errors = []
        self.restarts = 0


def make_bot(mods, fake, symbol, run, state_dir=None, step_up=2500, max_limit=10, window=None, mtqty=0.01):
    bot = mods.app.MT5TradingBot(mode='demo', target_symbol=symbol)
    bot.symbols_config = {'brake': 0, 'mtqty': mtqty,
                          'trading_window': window or {'enabled': False},
                          'symbols': [{'symbol': symbol, 'is_active': True, 'step_up_balance': step_up,
                                       'unit_max_limit': max_limit}]}
    bot.symbols = [symbol]
    bot.symbol_configs = {symbol: bot.symbols_config['symbols'][0]}
    bot.symbol_map = {symbol: symbol}
    bot.position_helper = mods.mt5_helper.MT5PositionHelper(fake)
    bot.mt5_initialized = True
    if state_dir is not None:
        bot.state_dir = str(state_dir)

    def _save_symbol_data(sym, data):
        an = data.get('analysis', {})
        pos = data.get('positions', {})
        run.polls.append({
            't': fake.iter_t, 'buy': data['signal']['buy_status'], 'sell': data['signal']['sell_status'],
            'fresh': an.get('candle_fresh'), 'open_score': an.get('open_score'), 'fc_score': an.get('fc_score'),
            'nb': pos['buy']['count'], 'ns': pos['sell']['count'],
            'profit': pos['buy']['total_profit'] if pos['buy']['count'] else pos['sell']['total_profit'],
            'units': an.get('unit_times'), 'entry_allowed': an.get('entry_allowed'),
            'exit_reason': an.get('exit_reason'), 'rsi': dict(an.get('rsi_mtf') or {}),
            'ladder_armed': an.get('ladder_armed'), 'trend': an.get('trend'), 'vol': an.get('vol_unit_now'),
            'levels': an.get('basket_levels'), 'pause_left': an.get('pause_left_s'),
            'virtual_balance': an.get('virtual_balance'),
            'votes': {tf: ((v or {}).get('rsi', {}).get('sign'), (v or {}).get('macd', {}).get('sign'))
                      for tf, v in (an.get('slopes') or {}).items()},
        })

    def _log_event(sym, event, tag, details=None, server_time=None):
        run.events.append({'t': fake.clock.now_ms, 'event': event, 'tag': tag,
                           'details': {k: v for k, v in (details or {}).items() if k != 'response'}})

    bot._save_symbol_data = _save_symbol_data
    bot._save_account_data = lambda *a, **k: None
    bot._save_daily_trades = lambda *a, **k: None
    bot._save_historical_summary = lambda *a, **k: None
    bot._log_event = _log_event
    return bot


def run_bot(root, fake, clock, symbol, overrides=None, state_dir=None, on_new_bot=None, **bot_kw):
    """Replay the bot from `root` until the clock ends; restarts (clock.restarts) start a fresh bot.
    on_new_bot(bot, n) is called with every bot before it runs (n = 0 first, 1 after the first restart ...)."""
    run = Run()
    with bot_modules(root, fake, clock, overrides) as mods:
        def _print(*args, **kwargs):
            msg = ' '.join(str(x) for x in args)
            if 'Error:' in msg or 'WARNING' in msg:
                run.errors.append(f'{clock.now_ms}: {msg}')
        mods.app.print = _print
        while True:
            try:
                bot = make_bot(mods, fake, symbol, run, state_dir=state_dir, **bot_kw)
                if on_new_bot is not None:
                    on_new_bot(bot, run.restarts)
                bot.process_symbol(symbol)
                break
            except Restart:
                run.restarts += 1
            except StopRun:
                break
        run.mods = mods
    return run
