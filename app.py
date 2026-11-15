import MetaTrader5 as mt5
import json
import os
import sys
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from mt5_helper import MT5PositionHelper, TerminalReadError
from indicator import Indicator
from strategy import Strategy, Signal
from datetime import timezone
from constants import (
    RSI_LENGTH, RSI_MA_TYPE, RSI_CANDLE_COUNT, RSI_MTF_TIMEFRAMES,
    RSI_DCA_LADDER_TIMEFRAMES, RSI_FINAL_CLOSE_TIMEFRAME,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    SLOPE_TIMEFRAMES, PEAK_LOOKBACK, PIVOT_WIDTH, RSI_PEAK_OB, RSI_PEAK_OS,
    RSI_GRAPH_BARS,
    REENTRY_COOLDOWN_SECONDS,
    CANDLE_TIMEFRAME, CANDLE_COUNT,
    MARKET_STATUS_TIMEFRAME, MARKET_LOOKBACK_MINUTES,
    OUTPUT_DIR, DAILY_TRADE_SUBDIR,
    HISTORICAL_SUMMARY_DAYS, HISTORICAL_SUMMARY_FILENAME,
    STRATEGY_LOG_FILENAME, STRATEGY_LOG_MAX_ENTRIES,
    ORDER_COOLDOWN_SECONDS,
    ACTIVE_CONFIG_FILENAME,
    STRATEGY_HEDGE,
    # design levers (constants.py; the defaults are the live bot). Read at call time, like the names above.
    DESIGN_NAME, STRATEGY,
    TREND_TF, VOL_TF, VOL_LEN,
    TARGET_USD_PER_UNIT, STOP_LOSS_USD_PER_UNIT,
    TARGET_VOL, STOP_VOL, VOL_CAP_USD_PER_UNIT, LADDER_GAP_VOL,
    LOSS_COOLDOWN_S,
    CONTRACT_SIZE_FALLBACK, STATE_SUBDIR,
    # demo isolation
    MAGIC, DEMO_BRANCH, VIRTUAL_START_BALANCE, VIRTUAL_START_DATE,
)

_TF_PREFIX = 'TIMEFRAME_'
_STATE_VERSION = 1
_RESOLVE_ATTEMPTS = 30           # polls spent looking for a closed basket's deals before its P/L at the close decision stands


def _tf_key(tf):
    """'TIMEFRAME_H1' or 'H1' -> 'H1' (None stays None)."""
    if tf is None:
        return None
    s = str(tf).strip().upper()
    return s[len(_TF_PREFIX):] if s.startswith(_TF_PREFIX) else s


def _tf_name(tf):
    """'H1' or 'TIMEFRAME_H1' -> 'TIMEFRAME_H1' (None stays None)."""
    k = _tf_key(tf)
    return None if k is None else _TF_PREFIX + k


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float('inf')


def _utc(ts):
    """Epoch seconds -> aware UTC datetime (what the terminal's time arguments expect)."""
    from datetime import datetime
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def _virtual_start_ts():
    """VIRTUAL_START_DATE ('YYYY-MM-DD' or an ISO time, UTC) as epoch seconds; None when it is None."""
    if VIRTUAL_START_DATE is None:
        return None
    from datetime import datetime
    dt = datetime.fromisoformat(str(VIRTUAL_START_DATE).strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _pos_time(pos):
    """Open time of a position in seconds (time_msc when the terminal has it)."""
    msc = getattr(pos, 'time_msc', None)
    return msc / 1000.0 if msc else float(pos.time)


def _pos_id(pos):
    """The identifier the deal history knows a position by (position_id of its deals)."""
    ident = getattr(pos, 'identifier', None)
    return int(ident) if ident else int(pos.ticket)


def _sorted_positions(positions):
    """Positions oldest first (open time, then ticket)."""
    return sorted(positions or [], key=lambda p: (_pos_time(p), int(p.ticket)))


def _deal_time(deal):
    msc = getattr(deal, 'time_msc', None)
    return msc / 1000.0 if msc else float(deal.time)


def _deal_net(deal):
    """Realised money of a deal: profit + swap + commission + fee."""
    return (float(getattr(deal, 'profit', 0.0) or 0.0) + float(getattr(deal, 'swap', 0.0) or 0.0)
            + float(getattr(deal, 'commission', 0.0) or 0.0) + float(getattr(deal, 'fee', 0.0) or 0.0))


def _is_out_deal(deal):
    """A deal that closes (part of) a position: DEAL_ENTRY_OUT (1) or DEAL_ENTRY_OUT_BY (3)."""
    e = getattr(deal, 'entry', None)
    return e in (1, 3) or e == 'out'


def virtual_balance_enabled():
    """Units come from the virtual balance (VIRTUAL_START_BALANCE + this bot's own closed P/L) when a start
    date is set and the bot has a MAGIC to find its deals by; otherwise from the account balance (live)."""
    return VIRTUAL_START_DATE is not None and MAGIC is not None


def usd_target_per_unit():
    """The configured $ target per unit: STRATEGY_HEDGE for 'live', the number, or None (no $ target)."""
    if TARGET_USD_PER_UNIT is None:
        return None
    if isinstance(TARGET_USD_PER_UNIT, str) and TARGET_USD_PER_UNIT == 'live':
        return STRATEGY_HEDGE
    return TARGET_USD_PER_UNIT


def basket_levels(vol_unit, usd_per_price):
    """
    A basket's distances, fixed when it opens (the backtester's kernels.py L1266-1289):
      target_usd_per_unit  USD per unit (None = no target): the $ target, or TARGET_VOL x unit x usd_per_price
      stop_usd_per_unit    USD per unit (None = no stop):   the $ stop,   or STOP_VOL x unit x usd_per_price
      gap_px               price units an add needs against the last fill: LADDER_GAP_VOL x unit (0 = none)
    with unit = `vol_unit` (price units, the last closed VOL_TF bar), first capped at
    VOL_CAP_USD_PER_UNIT / usd_per_price, and usd_per_price = contract_size x mtqty (gold 1.0, BTC 0.01).
    The volatility multiples apply only with VOL_TF set and a known unit (> 0); the basket's USD levels
    are these per-unit values times the basket's unit count.
    """
    tgt = usd_target_per_unit()
    sl = STOP_LOSS_USD_PER_UNIT
    gap = 0.0
    v = None
    if VOL_TF is not None and vol_unit is not None and vol_unit > 0:
        # (an unknown usd_per_price cannot reach here with a USD distance configured: entry_block_reason
        # refuses the entry, and a rebuilt basket waits for it, see levels_complete)
        v = vol_unit
        if VOL_CAP_USD_PER_UNIT > 0.0 and usd_per_price and v * usd_per_price > VOL_CAP_USD_PER_UNIT:
            v = VOL_CAP_USD_PER_UNIT / usd_per_price
        if TARGET_VOL > 0.0 and usd_per_price:
            tgt = TARGET_VOL * v * usd_per_price
        if STOP_VOL > 0.0 and usd_per_price:
            sl = STOP_VOL * v * usd_per_price
        if LADDER_GAP_VOL > 0.0:
            gap = LADDER_GAP_VOL * v
    return {
        'target_usd_per_unit': tgt,
        'stop_usd_per_unit': sl,
        'gap_px': gap,
        'vol_unit_raw': vol_unit if VOL_TF is not None else None,
        'vol_unit': v,
    }


def levels_complete(vol_unit, usd_per_price):
    """True when basket_levels() can give the design's distances (always without VOL_TF)."""
    if VOL_TF is None:
        return True
    if not (vol_unit is not None and vol_unit > 0):
        return False
    return bool(usd_per_price) or not (TARGET_VOL > 0 or STOP_VOL > 0 or VOL_CAP_USD_PER_UNIT > 0)


def entry_block_reason(want_side, trend_now, vol_now, usd_per_price):
    """
    Why a fresh entry the strategy wants is not sent, after the brake (None = send it). The backtester's
    execution-time order (kernels.py L1206-1225): trend, then the volatility unit not known.
      trend: TREND_TF set and want_side * trend <= 0 (a trend of 0 blocks both sides)
      volatility unknown: VOL_TF set and the unit of the last closed bar is not > 0
      contract size unknown: a volatility distance is configured and the USD value of a price move is not known
    """
    if TREND_TF is not None and want_side * trend_now <= 0:
        return 'trend'
    if VOL_TF is not None and not (vol_now is not None and vol_now > 0):
        return 'volatility unknown'
    if VOL_TF is not None and not usd_per_price and (TARGET_VOL > 0 or STOP_VOL > 0 or VOL_CAP_USD_PER_UNIT > 0):
        return 'contract size unknown'
    return None


def design_problems():
    """Why the design in constants.py cannot run (empty = fine). The backtester's BacktestConfig checks."""
    p = list(Strategy.design_problems())
    if STRATEGY not in ('basket', 'turtle'):
        p.append(f"STRATEGY {STRATEGY!r} is not 'basket' or 'turtle'")
    elif STRATEGY == 'turtle':
        p.append("STRATEGY 'turtle': the Turtle module is not part of this code; this bot runs only 'basket'")
    for name, tf in (('TREND_TF', TREND_TF), ('VOL_TF', VOL_TF)):
        if tf is not None and not hasattr(mt5, _tf_name(tf)):
            p.append(f'{name} {tf!r} is not an MT5 timeframe')
    for tf in Strategy.ladder_tiers():
        if not hasattr(mt5, _TF_PREFIX + tf):
            p.append(f'LADDER_TFS entry {tf!r} is not an MT5 timeframe')
    if not isinstance(VOL_LEN, int) or isinstance(VOL_LEN, bool) or VOL_LEN < 2:
        p.append(f'VOL_LEN must be a whole number >= 2, not {VOL_LEN!r}')
    vols = {'TARGET_VOL': TARGET_VOL, 'STOP_VOL': STOP_VOL, 'LADDER_GAP_VOL': LADDER_GAP_VOL,
            'VOL_CAP_USD_PER_UNIT': VOL_CAP_USD_PER_UNIT}
    for name, x in vols.items():
        if not _is_number(x) or x < 0:
            p.append(f'{name} must be a number >= 0, not {x!r}')
        elif x > 0 and VOL_TF is None:
            p.append(f'{name} > 0 needs VOL_TF, the timeframe whose volatility is the unit')
    t = TARGET_USD_PER_UNIT
    if not (t is None or (isinstance(t, str) and t == 'live') or (_is_number(t) and t >= 0)):
        p.append(f"TARGET_USD_PER_UNIT must be 'live', None or a number >= 0, not {t!r}")
    if not (STOP_LOSS_USD_PER_UNIT is None or (_is_number(STOP_LOSS_USD_PER_UNIT) and STOP_LOSS_USD_PER_UNIT >= 0)):
        p.append(f'STOP_LOSS_USD_PER_UNIT must be None or a number >= 0, not {STOP_LOSS_USD_PER_UNIT!r}')
    if not _is_number(LOSS_COOLDOWN_S) or LOSS_COOLDOWN_S < 0:
        p.append(f'LOSS_COOLDOWN_S must be a number of seconds >= 0, not {LOSS_COOLDOWN_S!r}')
    if MAGIC is not None and (not isinstance(MAGIC, int) or isinstance(MAGIC, bool) or MAGIC < 0):
        p.append(f'MAGIC must be None or a whole number >= 0, not {MAGIC!r}')
    if VIRTUAL_START_DATE is not None:
        try:
            _virtual_start_ts()
        except (TypeError, ValueError):
            p.append(f"VIRTUAL_START_DATE must be None or a date 'YYYY-MM-DD', not {VIRTUAL_START_DATE!r}")
        if not _is_number(VIRTUAL_START_BALANCE) or VIRTUAL_START_BALANCE <= 0:
            p.append(f'VIRTUAL_START_BALANCE must be a number > 0, not {VIRTUAL_START_BALANCE!r}')
    return p


def design_summary():
    """One line describing the design in effect (startup print)."""
    from strategy import (FORCE_CLOSE_ENABLED as _fc, MAX_ADDS as _ma, LADDER_TRIGGER as _lt,
                          LADDER_MULTIPLIERS as _lm)
    bits = [f'design {DESIGN_NAME!r}', f'force-close {"on" if _fc else "off"}',
            f'trend {TREND_TF or "off"}', f'vol {VOL_TF + "/" + str(VOL_LEN) if VOL_TF else "off"}']
    if VOL_TF:
        bits.append(f'target {TARGET_VOL:g}u stop {STOP_VOL:g}u cap ${VOL_CAP_USD_PER_UNIT:g}')
    else:
        bits.append(f'target ${usd_target_per_unit()}/unit stop {STOP_LOSS_USD_PER_UNIT}')
    bits.append(f'loss pause {LOSS_COOLDOWN_S:g}s' if LOSS_COOLDOWN_S else 'loss pause off')
    tiers = Strategy.ladder_tiers()
    bits.append(f'ladder {len(tiers)} x {_lt} {tiers} {"fibo" if _lm is None else list(_lm)}' if tiers else 'no ladder')
    bits.append(f'magic {MAGIC}')
    bits.append(f'virtual ${VIRTUAL_START_BALANCE:g} from {VIRTUAL_START_DATE}' if virtual_balance_enabled()
                else 'units from the account balance')
    return ' | '.join(bits)


# ─── the terminal (demo review) ───
_RECONNECT_AFTER = 5                         # polls in a row without the terminal (terminal_info() None) before the
                                             # bot connects again: mt5.shutdown(), then initialize_mt5()
_RECONNECT_BACKOFF_S = (5.0, 10.0, 30.0, 60.0)   # waits after a reconnect that failed (the last one repeats)


class MT5TradingBot:
    """Main Trading Bot Class with Clean Architecture"""
    
    def __init__(self, mode='demo', target_symbol=None):
        """
        Initialize the trading bot
        
        Args:
            mode (str): Either 'demo' or 'live'
            target_symbol (str): If set, only process this single symbol.
                                 Recommended to avoid MT5 threading issues.
        """
        self.mode = mode.lower()
        self.target_symbol = target_symbol.strip().upper() if target_symbol else None
        self.credentials = None
        self.symbols_config = None
        self.symbols = []
        self.symbol_configs = {}      # Per-symbol config lookup
        self.mt5_initialized = False
        self.thread_lock = threading.Lock()       # For file I/O
        self.mt5_lock = threading.Lock()           # For MT5 API calls (not thread-safe)
        self.position_helper = None
        self.symbol_map = {}
        self.indicator = Indicator()
        self.strategy = Strategy()
        self._stop_event = threading.Event()     # Signal workers to stop
        # Per-basket state (fixed distances, ladder arming) and the loss pause live in
        # <state_dir>/<symbol>_state.json; None = OUTPUT_DIR/STATE_SUBDIR. A replay may point it elsewhere
        # or replace _load_state / _save_state.
        self.state_dir = None
        self._usd_per_price = {}                 # trade symbol -> contract_size x mtqty (USD per unit per 1.0 of price)
        self._virtual_balance_last = None        # last virtual balance read from the deal history
        # The account this bot trades on: the demo login initialize_mt5 found (None before it ran; a replay that
        # does not call it takes the first account it sees) and why the account seen last was refused (None = ok).
        self._account_login = None
        self._account_bad = None
        # Polls in a row that could not read the terminal (they decide nothing), and why the last one could not;
        # those of them without the terminal at all (terminal_info() None), the reconnects that failed since, the
        # time of the next attempt, and why initialize_mt5 failed last.
        self._failed_polls = 0
        self._read_bad = None
        self._ipc_failed = 0
        self._reconnects_failed = 0
        self._reconnect_at = None
        self._init_problem = None

    # ── Day-of-week mapping for trading_window config ──
    _DAY_NAME_TO_NUM = {
        'monday': 0, 'mon': 0,
        'tuesday': 1, 'tue': 1, 'tues': 1,
        'wednesday': 2, 'wed': 2,
        'thursday': 3, 'thu': 3, 'thurs': 3,
        'friday': 4, 'fri': 4,
        'saturday': 5, 'sat': 5,
        'sunday': 6, 'sun': 6,
    }

    @classmethod
    def _day_time_to_week_minutes(cls, day, time_str):
        """Convert (day_name, 'HH:MM') to minutes since Monday 00:00."""
        d = cls._DAY_NAME_TO_NUM.get(str(day).strip().lower(), 0)
        try:
            hh, mm = str(time_str).strip().split(':')
            return d * 1440 + int(hh) * 60 + int(mm)
        except (ValueError, AttributeError):
            return d * 1440

    def _is_in_trading_window(self, now_dt, window_cfg):
        """Return True if `now_dt` falls inside the configured trading window.

        Window may wrap past Sunday (e.g. Friday 22:00 → Monday 06:00).
        If config is missing or `enabled` is false, always returns True.
        """
        if not window_cfg or not window_cfg.get('enabled', False):
            return True
        start = self._day_time_to_week_minutes(
            window_cfg.get('start_day', 'Monday'),
            window_cfg.get('start_time', '00:00'),
        )
        end = self._day_time_to_week_minutes(
            window_cfg.get('end_day', 'Saturday'),
            window_cfg.get('end_time', '00:00'),
        )
        now_min = now_dt.weekday() * 1440 + now_dt.hour * 60 + now_dt.minute
        if start == end:
            return True   # 24/7 window
        if start < end:
            return start <= now_min < end
        # Wrap-around window (e.g. Fri 22:00 → Mon 06:00)
        return now_min >= start or now_min < end

    def _resolve_symbol_alias(self, symbol):
        """Resolve configured symbol to the best matching broker symbol name."""
        info = mt5.symbol_info(symbol)
        if info is not None:
            return symbol

        base = symbol.rstrip('mM')
        patterns = [f"{symbol}*", f"{base}*", f"*{base}*"]
        candidates = []
        seen = set()
        for pattern in patterns:
            for cand in (mt5.symbols_get(pattern) or []):
                if cand.name in seen:
                    continue
                seen.add(cand.name)
                candidates.append(cand)

        if not candidates:
            return symbol

        disabled_mode = getattr(mt5, 'SYMBOL_TRADE_MODE_DISABLED', None)

        def _score(cand):
            name = cand.name
            score = 0
            if name == symbol:
                score += 200
            if name.startswith(symbol):
                score += 120
            if name.startswith(base):
                score += 90
            if base and base in name:
                score += 50
            if getattr(cand, 'visible', False):
                score += 15
            if getattr(cand, 'select', False):
                score += 10
            if disabled_mode is not None and getattr(cand, 'trade_mode', None) != disabled_mode:
                score += 8
            return (score, -len(name))

        best = max(candidates, key=_score)
        return best.name

    def _build_symbol_map(self):
        """Build configured→resolved MT5 symbol map for this session."""
        self.symbol_map = {}
        for symbol in self.symbols:
            resolved = self._resolve_symbol_alias(symbol)
            self.symbol_map[symbol] = resolved
            if resolved == symbol:
                print(f"✓ Symbol mapped: {symbol}")
            else:
                print(f"✓ Symbol mapped: {symbol} -> {resolved}")
        
    def load_credentials(self):
        """Step 1: Load MT5 credentials from JSON file"""
        if DEMO_BRANCH and self.mode != 'demo':
            print(f"✗ This is the demo branch {DEMO_BRANCH}: mode '{self.mode}' is refused, it trades on demo only")
            return False
        try:
            json_path = Path(__file__).parent / 'mt5_credentials.json'
            with open(json_path, 'r') as f:
                credentials = json.load(f)
            
            if self.mode not in credentials:
                raise ValueError(f"Invalid mode '{self.mode}'. Must be 'demo' or 'live'")
            
            self.credentials = credentials[self.mode]
            print(f"✓ Credentials loaded for {self.mode.upper()} account")
            return True
        except FileNotFoundError:
            print(f"✗ Error: mt5_credentials.json not found")
            return False
        except json.JSONDecodeError:
            print("✗ Error: Invalid JSON format in mt5_credentials.json")
            return False
    
    def load_symbols(self):
        """Step 2: Load symbols configuration from JSON file"""
        try:
            json_path = Path(__file__).parent / 'symbols.json'
            with open(json_path, 'r') as f:
                self.symbols_config = json.load(f)
            
            sym_list = self.symbols_config.get('symbols', [])
            if not sym_list:
                print("✗ Warning: No symbols found in symbols.json")
                return False

            # Build per-symbol config lookup from the array (only active symbols)
            self.symbols = []
            self.symbol_configs = {}
            skipped = []
            for entry in sym_list:
                name = entry.get('symbol', '')
                if not name:
                    continue
                if not entry.get('is_active', True):
                    skipped.append(name)
                    continue
                self.symbols.append(name)
                self.symbol_configs[name] = entry

            if skipped:
                print(f"⊘ Skipped inactive symbols: {', '.join(skipped)}")

            # ── Single-symbol mode: filter to target_symbol only ──
            if self.target_symbol:
                # Match case-insensitively against configured symbol names
                matched = [s for s in self.symbols if s.upper() == self.target_symbol]
                if not matched:
                    print(f"✗ Error: Symbol '{self.target_symbol}' not found in symbols.json")
                    print(f"  Available: {', '.join(self.symbols)}")
                    return False
                self.symbols = matched
                self.symbol_configs = {s: self.symbol_configs[s] for s in matched}
                print(f"⚡ Single-symbol mode: {matched[0]}")

            if not self.symbols:
                print("✗ Warning: No valid symbols in symbols.json")
                return False

            print(f"✓ Loaded {len(self.symbols)} symbols: {', '.join(self.symbols)}")
            return True
        except FileNotFoundError:
            print(f"✗ Error: symbols.json not found")
            return False
        except json.JSONDecodeError:
            print("✗ Error: Invalid JSON format in symbols.json")
            return False
    
    def initialize_mt5(self):
        """Step 3: Initialize and login to MT5"""
        print(f"\n{'='*60}")
        print(f"  Initializing MT5 - {self.mode.upper()} Account")
        print(f"{'='*60}\n")
        
        # Initialize MT5
        if not mt5.initialize(path=self.credentials['terminal_path']):
            self._init_problem = f'initialize failed: {mt5.last_error()}'
            print(f"✗ MT5 initialization failed: {mt5.last_error()}")
            return False

        print(f"✓ MT5 initialized successfully")
        print(f"✓ MT5 version: {mt5.version()}")

        # Login to MT5 account
        authorized = mt5.login(
            login=self.credentials['login_id'],
            password=self.credentials['login_pass'],
            server=self.credentials['server']
        )

        if not authorized:
            error = mt5.last_error()
            self._init_problem = f'login failed: {error}'
            print(f"✗ Login failed: {error}")
            mt5.shutdown()
            return False

        # Get account info
        account_info = mt5.account_info()
        if account_info is None:
            self._init_problem = 'no account info'
            print("✗ Failed to get account info")
            mt5.shutdown()
            return False

        # Only ever this branch's demo account: a demo, hedging account with the login of the credentials
        problem = self._login_problem(account_info)
        if problem:
            self._init_problem = problem
            print(f"✗ Refused: {problem}")
            mt5.shutdown()
            return False
        self._account_login = account_info.login
        self._init_problem = None

        print(f"\n{'='*60}")
        print(f"  Login Successful - {self.mode.upper()} Account")
        print(f"{'='*60}")
        print(f"Login ID: {account_info.login}")
        print(f"Server: {account_info.server}")
        print(f"Balance: ${account_info.balance:.2f}")
        print(f"Equity: ${account_info.equity:.2f}")
        print(f"Leverage: 1:{account_info.leverage}")
        print(f"{'='*60}\n")
        
        self.mt5_initialized = True
        
        # Initialize position helper with mt5 instance
        self.position_helper = MT5PositionHelper(mt5)
        self._install_order_guard()

        # Resolve configured symbols to broker symbol names (suffix/alias safe)
        self._build_symbol_map()
        heartbeat_symbol = self._resolve_symbol_alias('EURUSD')

        # Subscribe all traded symbols + EURUSD (used for server-time)
        # symbol_select adds a symbol to Market Watch so live data flows
        subscribe_symbols = list(set(self.symbol_map.values())) + [heartbeat_symbol]
        for sym in subscribe_symbols:
            selected = mt5.symbol_select(sym, True)
            if selected:
                print(f"✓ Subscribed to {sym}")
            else:
                prefix = sym[:6] if len(sym) >= 6 else sym
                matches = mt5.symbols_get(f"{prefix}*") or []
                candidates = ', '.join(s.name for s in matches[:8]) if matches else 'none'
                print(f"✗ Failed to subscribe {sym}: {mt5.last_error()} | candidates: {candidates}")
        
        return True
    
    def _save_symbol_data(self, symbol, data):
        """Save symbol data to JSON file on C: drive (thread-safe)"""
        import os
        output_dir = OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, f'{symbol}.json')
        with self.thread_lock:
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
    
    def _save_account_data(self, account_info):
        """Save account data to dedicated account.json (thread-safe)"""
        import os
        from datetime import datetime
        output_dir = OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, 'account.json')
        account_info['last_updated'] = datetime.now(tz=timezone.utc).isoformat()
        with self.thread_lock:
            with open(json_path, 'w') as f:
                json.dump(account_info, f, indent=2, default=str)
    
    def _save_daily_trades(self, symbol, mt5_symbol=None):
        """Fetch today's closed deals for a symbol and save to per-symbol daily_trade folder (thread-safe)"""
        import os
        from datetime import datetime
        
        # Per-symbol folder: C:\Alcadeias\daily_trade\{symbol}\
        output_dir = os.path.join(OUTPUT_DIR, DAILY_TRADE_SUBDIR, symbol)
        os.makedirs(output_dir, exist_ok=True)
        
        # Use server time for the filename so it matches broker's trading day
        with self.mt5_lock:
            server_now = self.position_helper._get_server_time()
        filename = server_now.strftime('%d_%b_%Y').lower() + '.json'
        json_path = os.path.join(output_dir, filename)
        
        # Fetch today's closed deals for this symbol (server-time aware)
        deal_symbol = mt5_symbol or symbol
        with self.mt5_lock:
            today_deals = self.position_helper.get_today_deals(deal_symbol)
        
        # Calculate summary using net_profit (includes commission+swap+fee)
        total_net = sum(d.get('net_profit', d['profit']) for d in today_deals)
        total_volume = sum(d['volume'] for d in today_deals)
        avg_net = round(total_net / len(today_deals), 2) if today_deals else 0
        
        data = {
            'symbol': symbol,
            'date': server_now.strftime('%d %b %Y'),
            'server_date': server_now.strftime('%Y-%m-%d'),
            'server_time': server_now.isoformat(),
            'last_updated': datetime.now(tz=timezone.utc).isoformat(),
            'deal_count': len(today_deals),
            'total_profit': round(total_net, 2),
            'total_volume': round(total_volume, 4),
            'avg_profit': avg_net,
            'deals': today_deals,
        }
        
        with self.thread_lock:
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
    
    def _save_historical_summary(self, symbol, mt5_symbol=None):
        """Fetch last 10 years of deal history for a specific symbol and save to its folder (thread-safe)"""
        import os
        from datetime import datetime
        
        # Per-symbol folder: <OUTPUT_DIR>/daily_trade/{symbol}/
        output_dir = os.path.join(OUTPUT_DIR, DAILY_TRADE_SUBDIR, symbol)
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, HISTORICAL_SUMMARY_FILENAME)
        
        # Fetch only this symbol's deals for the configured history period
        deal_symbol = mt5_symbol or symbol
        with self.mt5_lock:
            all_deals = self.position_helper.get_deals_since(days=HISTORICAL_SUMMARY_DAYS, symbol=deal_symbol)
        
        total_net = sum(d.get('net_profit', d['profit']) for d in all_deals)
        total_volume = sum(d['volume'] for d in all_deals)
        avg_net = round(total_net / len(all_deals), 2) if all_deals else 0
        
        summary = {
            'symbol': symbol,
            'last_updated': datetime.now(tz=timezone.utc).isoformat(),
            'period': 'Last 10 years',
            'total_deals': len(all_deals),
            'total_profit': round(total_net, 2),
            'total_volume': round(total_volume, 4),
            'avg_profit': avg_net,
        }
        
        with self.thread_lock:
            with open(json_path, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
    
    def _log_event(self, symbol, event, tag, details=None, server_time=None):
        """Append a strategy event to the per-symbol log file (thread-safe).
        
        Args:
            symbol: Trading symbol
            event: Short event name (e.g. 'BUY_EXECUTED', 'CLOSE_SELL', 'SIGNAL_BUY')
            tag: Category tag (e.g. 'ENTRY', 'EXIT', 'SIGNAL', 'ERROR')
            details: Optional dict with extra info (volume, profit, response, etc.)
            server_time: Optional pre-fetched server time (avoids extra MT5 lock)
        """
        import os
        from datetime import datetime

        if server_time is None:
            server_time = datetime.now(tz=timezone.utc)

        entry = {
            'time': server_time.isoformat(),
            'utc_time': datetime.now(tz=timezone.utc).isoformat(),
            'symbol': symbol,
            'event': event,
            'tag': tag,
            'details': details or {},
        }

        log_dir = os.path.join(OUTPUT_DIR, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f'{symbol}_{STRATEGY_LOG_FILENAME}')

        with self.thread_lock:
            # Load existing log
            try:
                with open(log_path, 'r') as f:
                    log_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                log_data = []

            # Prepend (newest first) and cap
            log_data.insert(0, entry)
            log_data = log_data[:STRATEGY_LOG_MAX_ENTRIES]

            with open(log_path, 'w') as f:
                json.dump(log_data, f, indent=2, default=str)
    
    # ───────────────────── per-basket state, loss pause, virtual balance ─────────────────────
    def _state_path(self, symbol):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, f'{symbol}_state.json')

    def _load_state(self, symbol):
        """The persisted state ({'basket': ..., 'last_close': ...}) or None: no file, unreadable, or written
        for another symbol / magic number (then it is rebuilt from the terminal)."""
        path = self._state_path(symbol)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            print(f"[{symbol}] note: state file {path} unreadable ({e}); rebuilding it from the terminal")
            return None
        if not isinstance(data, dict) or data.get('symbol') != symbol or data.get('magic') != MAGIC:
            print(f"[{symbol}] note: state file {path} is not this bot's (symbol/magic); rebuilding it from the terminal")
            return None
        return {'basket': data.get('basket'), 'last_close': data.get('last_close')}

    def _save_state(self, symbol, state):
        """Write the state atomically (a crash mid-write leaves the previous file)."""
        path = self._state_path(symbol)
        data = {'version': _STATE_VERSION, 'symbol': symbol, 'magic': MAGIC, 'design': DESIGN_NAME,
                'saved_at': time.time(), 'basket': state.get('basket'), 'last_close': state.get('last_close')}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with self.thread_lock:
                with open(tmp, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp, path)
        except OSError as e:
            print(f"[{symbol}] Error: could not write the state file {path}: {e}")

    def _usd_per_price_of(self, symbol, trade_symbol, mtqty):
        """USD per unit (mtqty lots) for a move of 1.0 in price = contract_size x mtqty (gold 100 x 0.01 = 1.0,
        BTC 1 x 0.01 = 0.01). The contract size is the terminal's symbol_info().trade_contract_size, else
        CONTRACT_SIZE_FALLBACK by symbol prefix. Read once; None when unknown."""
        if trade_symbol in self._usd_per_price:
            return self._usd_per_price[trade_symbol]
        info = mt5.symbol_info(trade_symbol)
        size, source = None, None
        try:
            raw = getattr(info, 'trade_contract_size', None) if info is not None else None
            size = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            size = None
        if size is not None and size > 0:
            source = 'terminal'
        else:
            size = None
            for prefix, value in CONTRACT_SIZE_FALLBACK.items():
                if str(trade_symbol).upper().startswith(str(prefix).upper()):
                    size, source = float(value), 'CONTRACT_SIZE_FALLBACK'
                    break
        if size is None:
            if info is not None:
                self._usd_per_price[trade_symbol] = None
            return None
        usd = size * mtqty
        if info is not None:          # a missing symbol_info may be transient: ask again next time
            self._usd_per_price[trade_symbol] = usd
            print(f"[{symbol}] contract size {size:g} ({source}): {usd:g} USD per unit for a 1.0 price move")
        return usd

    def _virtual_balance(self, now):
        """VIRTUAL_START_BALANCE + profit + swap + commission + fee of this bot's deals since VIRTUAL_START_DATE,
        added up in time order (the backtester's balance of a fresh account). When the terminal gives no
        history, the last value read (or the start balance): the smaller, safe unit."""
        start = _virtual_start_ts()
        deals = self.position_helper.get_bot_deals(_utc(start), _utc(now + 86400))
        if deals is None:
            return self._virtual_balance_last if self._virtual_balance_last is not None else float(VIRTUAL_START_BALANCE)
        bal = float(VIRTUAL_START_BALANCE)
        for d in sorted(deals, key=lambda d: (_deal_time(d), int(getattr(d, 'ticket', 0) or 0))):
            if _deal_time(d) >= start:
                bal += _deal_net(d)
        self._virtual_balance_last = bal
        return bal

    def _basket_pnl(self, ids, since, now):
        """Realised P/L of the positions `ids` (profit + swap + commission + fee of all their deals, rounded to
        cents) once the history holds a closing deal for every one of them, else None. Also returns the time
        of the last closing deal."""
        if not ids:
            return None, None
        frm = (since if since else now) - 2 * 86400
        deals = self.position_helper.get_bot_deals(_utc(frm), _utc(now + 86400))
        if deals is None:
            return None, None
        idset = {int(i) for i in ids}
        mine = [d for d in deals if getattr(d, 'position_id', None) in idset]
        outs = [d for d in mine if _is_out_deal(d)]
        if not idset <= {getattr(d, 'position_id', None) for d in outs}:
            return None, None
        pnl = 0.0
        for d in sorted(mine, key=lambda d: (_deal_time(d), int(getattr(d, 'ticket', 0) or 0))):
            pnl += _deal_net(d)
        return round(pnl, 2), max(_deal_time(d) for d in outs)

    def _resolve_last_close(self, state, now):
        """Replace the provisional result of the last closed basket (its P/L at the close decision) by the
        realised one from the deal history; True when the state changed. Gives up after _RESOLVE_ATTEMPTS
        polls (the decision-time P/L then stands)."""
        lc = state.get('last_close')
        if not lc or lc.get('resolved'):
            return False
        lc['attempts'] = int(lc.get('attempts', 0)) + 1
        pnl, t_out = self._basket_pnl(lc.get('ids') or [], lc.get('open_time'), now)
        if pnl is not None:
            lc.update(pnl=pnl, lost=bool(pnl < 0), resolved=True, source='history')
            if lc.get('time_from_history') and t_out is not None:
                lc['time'] = float(t_out)   # closed outside the bot: the pause runs from its closing deal
            return True
        if lc['attempts'] >= _RESOLVE_ATTEMPTS:
            lc['resolved'] = True
            return True
        return False

    def _last_close_from_history(self, now):
        """The last basket this bot closed, from the deal history (used when there is no state file): the
        time of its last closing deal and its realised P/L. None when there is none in the look-back."""
        look = max(float(LOSS_COOLDOWN_S or 0), float(REENTRY_COOLDOWN_SECONDS)) + 86400.0
        deals = self.position_helper.get_bot_deals(_utc(now - look), _utc(now + 86400))
        if not deals:
            return None
        outs = [d for d in deals if _is_out_deal(d)]
        if not outs:
            return None
        t_last = max(_deal_time(d) for d in outs)
        last = [d for d in outs if t_last - _deal_time(d) <= 60.0]
        ids = {getattr(d, 'position_id', None) for d in last} - {None, 0}
        group = [d for d in deals if getattr(d, 'position_id', None) in ids] if ids else last
        pnl = round(sum(_deal_net(d) for d in sorted(group, key=_deal_time)), 2)
        return {'time': float(t_last), 'pnl': pnl, 'lost': bool(pnl < 0), 'resolved': True,
                'source': 'history_rebuild', 'reason': None, 'side': None, 'ids': sorted(int(i) for i in ids),
                'open_time': None, 'attempts': 0}

    def _vol_unit_at(self, trade_symbol, t_open):
        """The volatility unit a basket opened at `t_open` (seconds) saw: the unit of the last VOL_TF bar
        closed before the bar that was forming at that time."""
        tf = getattr(mt5, _tf_name(VOL_TF), None)
        if tf is None:
            return None
        rates = mt5.copy_rates_from(trade_symbol, tf, _utc(int(t_open)), RSI_CANDLE_COUNT)
        if rates is None or len(rates) < 2:
            return None
        v = Indicator.vol_unit(rates['close'][:-1], VOL_LEN)
        return v if v > 0 else None

    def _new_basket(self, side, units, levels, opened_at, opened_by='bot'):
        return dict(levels, side=side, units=int(units), ids=[], first_time=None, opened_at=float(opened_at),
                    opened_by=opened_by, ladder_armed=False, close_pending=False,
                    levels_pending=False, vol_source='open' if levels.get('vol_unit') is not None else None,
                    last_profit=0.0)

    def _rebuild_basket(self, trade_symbol, side, plist, mtqty, usd_per_price, now):
        """A basket found open without its state (first start, lost file, another basket): the unit from the
        oldest position's volume, the volatility unit from the bars at its open time. The ladder starts
        disarmed (its arming is a path of votes that cannot be read back)."""
        first = plist[0]
        units = max(1, int(round(float(first.volume) / float(mtqty)))) if mtqty else 1
        v_raw = self._vol_unit_at(trade_symbol, _pos_time(first)) if VOL_TF is not None else None
        complete = levels_complete(v_raw, usd_per_price)
        levels = basket_levels(v_raw if complete else None, usd_per_price)
        b = self._new_basket(side, units, levels, now, opened_by='rebuild')
        b.update(ids=[_pos_id(p) for p in plist], first_time=_pos_time(first),
                 levels_pending=not complete, vol_source='bars_at_open' if complete and VOL_TF is not None else None)
        return b

    def _finish_outside_close(self, state, basket, now):
        """A basket whose positions are gone without a close of this bot (closed from the terminal, by the
        broker, or while the bot was down): book it as closed now; the P/L and the time of its closing deals
        replace that when the history has them."""
        profit = basket.get('last_profit') or 0.0
        state['last_close'] = {
            'time': float(now), 'pnl': profit, 'lost': bool(profit < 0), 'resolved': False, 'source': 'last_seen',
            'reason': 'closed_outside', 'side': basket.get('side'), 'ids': list(basket.get('ids') or []),
            'open_time': basket.get('first_time'), 'attempts': 0, 'time_from_history': True}
        state['basket'] = None

    def _sync_basket(self, symbol, trade_symbol, state, buy_positions, sell_positions, mtqty, usd_per_price, now):
        """Match the state's basket with this bot's open positions. True when the state changed."""
        nb = buy_positions['count'] if buy_positions else 0
        ns = sell_positions['count'] if sell_positions else 0
        basket = state.get('basket')
        if nb and ns:
            return False        # both sides open: the strategy holds still; the books stay as they are
        if not nb and not ns:
            if basket is None:
                return False
            if basket.get('ids'):
                self._finish_outside_close(state, basket, now)
                print(f"[{symbol}] note: the {basket.get('side')} basket was closed outside the bot")
            else:
                state['basket'] = None      # an open that never showed up as a position
            return True
        side = 'BUY' if nb else 'SELL'
        plist = _sorted_positions((buy_positions if nb else sell_positions).get('positions'))
        if not plist:
            return False
        ids = [_pos_id(p) for p in plist]
        known = list(basket.get('ids') or []) if basket is not None else []
        if basket is not None and basket.get('side') == side and (not known or set(ids) & set(known)):
            new = [i for i in ids if i not in known]
            if known and not new:
                return False
            if not known:
                basket['first_time'] = _pos_time(plist[0])
            basket['ids'] = known + new
            return True
        if basket is not None and basket.get('ids'):
            self._finish_outside_close(state, basket, now)
        state['basket'] = self._rebuild_basket(trade_symbol, side, plist, mtqty, usd_per_price, now)
        b = state['basket']
        print(f"[{symbol}] note: {side} basket of {len(plist)} position(s) taken over from the terminal: "
              f"unit {b['units']}, volatility unit {b.get('vol_unit')}, target/unit {b.get('target_usd_per_unit')}, "
              f"stop/unit {b.get('stop_usd_per_unit')}, gap {b.get('gap_px')}")
        return True

    def _after_close(self, symbol, state, side, close_response, positions, reason, now):
        """Book this bot's close of the basket: the loss pause starts at this close decision. A close that
        closed nothing changes nothing (it is decided again next poll, as the backtester does); a partial one
        keeps the basket and closes the rest on the next polls. Returns the new last_close or None."""
        closed = int((close_response or {}).get('closed_count', 0) or 0)
        failed = int((close_response or {}).get('failed_count', 0) or 0)
        basket = state.get('basket')
        if closed <= 0:
            return None
        if failed > 0:
            if basket is not None:
                basket['close_pending'] = True
                self._save_state(symbol, state)
            return None
        ids = list(basket.get('ids') or []) if basket is not None else []
        if not ids and positions and positions.get('positions'):
            ids = [_pos_id(p) for p in positions['positions']]
        profit = positions['total_profit'] if positions else 0.0
        lc = {'time': float(now), 'pnl': profit, 'lost': bool(profit < 0), 'resolved': False, 'source': 'decision',
              'reason': reason, 'side': side, 'ids': ids,
              'open_time': basket.get('first_time') if basket is not None else None, 'attempts': 0}
        state['last_close'] = lc
        state['basket'] = None
        with self.mt5_lock:
            self._resolve_last_close(state, now)
        self._save_state(symbol, state)
        return lc

    @staticmethod
    def _order_done(response):
        """True when the terminal reports the market order as filled."""
        if response is None:
            return False
        done = (getattr(mt5, 'TRADE_RETCODE_DONE', 10009), getattr(mt5, 'TRADE_RETCODE_DONE_PARTIAL', 10010))
        return getattr(response, 'retcode', None) in done

    # ───────────────────── the demo account: the only account this bot trades on ─────────────────────
    @staticmethod
    def _last_error():
        try:
            return mt5.last_error()
        except Exception as e:          # a broken terminal connection can raise instead of answering
            return repr(e)

    def _account_problem(self, acct=None, check_login=True):
        """
        Why the account the terminal is logged into is not this bot's right now (None = it is). Read at the start
        of every poll and before every order: with DEMO_BRANCH set it must be a demo account
        (trade_mode ACCOUNT_TRADE_MODE_DEMO) and the login initialize_mt5 remembered. All demo bots attach to one
        terminal, so another process (a live bot) can log it into another account at any time. A bot that was not
        started through initialize_mt5 (a replay) takes the first demo account it sees as its own, so a later
        switch is still caught.
        """
        if acct is None:
            acct = mt5.account_info()
        if acct is None:
            return f'account_info() returned None (last_error {self._last_error()})'
        login = getattr(acct, 'login', None)
        demo = getattr(mt5, 'ACCOUNT_TRADE_MODE_DEMO', 0)
        mode = getattr(acct, 'trade_mode', None)
        if DEMO_BRANCH and mode != demo:
            return f'account {login} is not a demo account (trade_mode {mode}, demo is {demo})'
        if check_login:
            if self._account_login is None:
                self._account_login = login
            elif login != self._account_login:
                return f'the terminal is logged into account {login}, not the demo account {self._account_login}'
        return None

    def _login_problem(self, acct):
        """Why the account initialize_mt5 has just logged into may not be traded (None = it may): a demo account
        (DEMO_BRANCH), a hedging account (the basket holds one position per fill), and the login of the
        credentials (not one another process switched the terminal to in the meantime)."""
        problem = self._account_problem(acct, check_login=False)
        if problem:
            return problem
        hedging = getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING', 2)
        mode = getattr(acct, 'margin_mode', None)
        if mode != hedging:
            return f'account {acct.login} is not a hedging account (margin_mode {mode}, hedging is {hedging})'
        want = (self.credentials or {}).get('login_id')
        if want is not None:
            try:
                same = int(acct.login) == int(want)
            except (TypeError, ValueError):
                same = False
            if not same:
                return f'the terminal is logged into account {acct.login}, not the login of the credentials ({want})'
        return None

    def _account_refused(self, symbol, problem, request=None, server_time=None):
        """The account is not this bot's: a WARNING and an ERROR event when the problem starts or changes."""
        if problem == self._account_bad:
            return
        self._account_bad = problem
        print(f"[{symbol}] WARNING: not trading: {problem}")
        details = {'problem': problem, 'demo_login': self._account_login}
        if request is not None:
            details['request'] = {k: request.get(k) for k in ('action', 'symbol', 'type', 'volume', 'position')
                                  if k in request}
        self._log_event(symbol, 'ACCOUNT_REFUSED', 'ERROR', details, server_time=server_time)

    def _account_ok(self, symbol, server_time=None):
        """At the start of a poll: True when the terminal holds this bot's demo account. Otherwise the poll decides
        nothing -- no sync with the positions of another account (they would book this bot's basket as closed),
        no order -- until the account is right again (then an ACCOUNT_OK event)."""
        problem = self._account_problem()
        if problem is not None:
            self._account_refused(symbol, problem, server_time=server_time)
            return False
        if self._account_bad is not None:
            print(f"[{symbol}] note: the terminal holds the demo account {self._account_login} again: trading")
            self._log_event(symbol, 'ACCOUNT_OK', 'SIGNAL', {'login': self._account_login, 'was': self._account_bad},
                            server_time=server_time)
            self._account_bad = None
        return True

    def _order_guard(self, request):
        """Before every order_send (MT5PositionHelper._send): account_info() is read again and nothing is sent
        unless it is still the demo account; a refused request is an ERROR event, and the polls after it decide
        nothing until the account is right again (_account_ok)."""
        problem = self._account_problem()
        if problem is None:
            return True
        self._account_refused(self._symbol_of(request.get('symbol')), problem, request=request)
        return False

    def _symbol_of(self, trade_symbol):
        """The configured symbol of a terminal symbol name (the log files are named by it)."""
        for sym, resolved in self.symbol_map.items():
            if resolved == trade_symbol:
                return sym
        return trade_symbol or (self.symbols[0] if self.symbols else '?')

    def _install_order_guard(self):
        """_order_guard in front of every order_send of the helper the bot trades through (initialize_mt5 makes a
        new helper; a replay brings its own)."""
        helper = self.position_helper
        if helper is not None and getattr(helper, 'order_guard', None) is None:
            helper.order_guard = self._order_guard

    def _poll_guard(self, symbol):
        """At the start of every poll: True when the poll may read the terminal and decide -- the terminal answers
        and is connected, and it holds this bot's demo account."""
        self._install_order_guard()
        problem, ipc_lost = self._terminal_problem()
        if problem is not None:
            self._poll_failed(symbol, problem, ipc_lost=ipc_lost)
            return False
        return self._account_ok(symbol)

    def _terminal_problem(self):
        """Why the terminal cannot be used this poll: (problem, ipc_lost), (None, False) when it can. ipc_lost:
        terminal_info() answers None (or raises), the connection to the terminal is gone -- the terminal was
        restarted or closed -- and every call will answer None until the bot connects again. Not connected to the
        trade server: the terminal reconnects by itself (a reconnect of the bot would log in again, and may undo
        another process's login on the shared terminal), so the poll only waits."""
        try:
            info = mt5.terminal_info()
        except Exception as e:
            return f'terminal_info() raised {e!r}', True
        if info is None:
            return f'terminal_info() returned None (last_error {self._last_error()})', True
        if getattr(info, 'connected', True) is False:
            return f'the terminal is not connected to the trade server (last_error {self._last_error()})', False
        return None, False

    def _poll_failed(self, symbol, problem, ipc_lost=False):
        """A poll that could not read what it decides on: it syncs, books and decides nothing. A WARNING and an ERROR
        event TERMINAL_ERROR when such a streak starts or its problem changes. After _RECONNECT_AFTER polls in a
        row without the terminal the bot connects again (_try_reconnect), and while that fails again after 5, 10,
        30, then every 60 s."""
        self._failed_polls += 1
        if problem != self._read_bad:
            self._read_bad = problem
            print(f"[{symbol}] WARNING: poll skipped, nothing decided: {problem}")
            self._log_event(symbol, 'TERMINAL_ERROR', 'ERROR', {'problem': problem, 'failed_polls': self._failed_polls})
        if not ipc_lost:
            return
        self._ipc_failed += 1
        if self._ipc_failed >= _RECONNECT_AFTER and (self._reconnect_at is None or time.time() >= self._reconnect_at):
            self._try_reconnect(symbol)

    def _try_reconnect(self, symbol):
        attempt = self._reconnects_failed + 1
        if self._reconnect(symbol):
            print(f"[{symbol}] note: connected to the terminal again (attempt {attempt})")
            self._log_event(symbol, 'TERMINAL_RECONNECTED', 'SIGNAL', {
                'attempt': attempt, 'failed_polls': self._failed_polls, 'login': self._account_login})
            self._ipc_failed = 0
            self._reconnects_failed = 0
            self._reconnect_at = None
            return
        wait = _RECONNECT_BACKOFF_S[min(self._reconnects_failed, len(_RECONNECT_BACKOFF_S) - 1)]
        self._reconnects_failed += 1
        self._reconnect_at = time.time() + wait
        print(f"[{symbol}] WARNING: reconnect attempt {attempt} failed ({self._init_problem}); next one in {wait:g} s")
        self._log_event(symbol, 'RECONNECT_FAILED', 'ERROR', {
            'attempt': attempt, 'why': self._init_problem, 'next_in_s': wait, 'failed_polls': self._failed_polls})

    def _reconnect(self, symbol):
        """mt5.shutdown(), then initialize_mt5() again: the terminal, the login, the demo-account checks, the symbol
        map and a new helper behind the order guard. True when the bot is on its demo account again."""
        print(f"[{symbol}] reconnecting to the MT5 terminal ...")
        with self.mt5_lock:
            try:
                mt5.shutdown()
            except Exception:
                pass
            self.mt5_initialized = False
            try:
                return bool(self.initialize_mt5())
            except Exception as e:          # (no credentials, a terminal that raises ...)
                self._init_problem = f'initialize_mt5 raised {e!r}'
                return False

    def _poll_succeeded(self, symbol):
        """The poll has read the terminal: a streak of failed polls is over (an event TERMINAL_OK)."""
        if self._failed_polls:
            print(f"[{symbol}] note: the terminal answers again after {self._failed_polls} skipped poll(s)")
            self._log_event(symbol, 'TERMINAL_OK', 'SIGNAL', {'failed_polls': self._failed_polls, 'was': self._read_bad})
        self._failed_polls = 0
        self._read_bad = None
        self._ipc_failed = 0
        self._reconnects_failed = 0
        self._reconnect_at = None

    def process_symbol(self, symbol):
        """
        Process a single symbol (will be called in separate threads)
        Lightweight and optimized - runs in infinite loop

        One poll, in the backtester's order (kernels.py run_kernel; map: scratchpad map_levers.md §2):
          market data + this bot's positions (MAGIC) -> the basket's state matched with them ->
          unit (only while flat, from the virtual balance) -> brake -> liveness (a dead poll decides nothing)
          -> forming-bar votes, H1 trend (last closed bar), volatility unit (closed bars) -> pause
          (loss pause) -> strategy (stop, target, force-close, ladder) -> execution (entry gates after the
          brake: trend, volatility known) -> bookkeeping (distances fixed at a fill, arming, pause start).

        Args:
            symbol (str): Symbol to process (e.g., 'BTCUSD', 'XAUUSD')
        """
        from datetime import datetime

        _problems = design_problems()
        if _problems:
            raise ValueError(f"design {DESIGN_NAME!r} refused: " + '; '.join(_problems))

        # Get configuration once before loop (per-symbol config from array)
        sym_cfg = self.symbol_configs.get(symbol, {})
        brake_manual = self.symbols_config.get('brake', 0)
        trading_window_cfg = self.symbols_config.get('trading_window', {})
        # ── Auto unit stepping by account balance ──
        # The running unit is no longer configured directly; it is derived from
        # the live account balance in `step_up_balance`-sized tiers:
        #   balance [0, step)         → unit 1
        #   balance [step, 2·step)    → unit 2
        #   balance [2·step, 3·step)  → unit 3   … and so on
        # i.e. unit = floor(balance / step_up_balance) + 1, then capped by
        # `unit_max_limit`. The effective unit (`units`) drives BOTH lot sizing
        # (entry + Fibo ladder) and the USD profit target, keeping them
        # synchronized (unit N → target $N). It is re-derived below, but ONLY
        # while the symbol is flat — an open Fibo basket keeps the unit it was
        # opened with (rescaling mid-basket would corrupt the ladder maths).
        # Demo: the balance is the virtual one (VIRTUAL_START_BALANCE + this bot's own
        # closed P/L) and an open basket keeps the unit recorded at its open (after a
        # restart: its oldest position's volume / mtqty).
        step_up_balance = sym_cfg.get('step_up_balance', 0)
        max_limit = sym_cfg.get('unit_max_limit', 1)
        units = 1
        mtqty = self.symbols_config.get('mtqty', 0.01)
        trade_symbol = self.symbol_map.get(symbol, symbol)

        # Throttle expensive saves so they don't block other threads
        _last_daily_save = 0.0
        _last_hist_save = 0.0
        _DAILY_SAVE_INTERVAL = 60       # seconds between daily-trade saves
        _HIST_SAVE_INTERVAL = 300       # seconds between historical-summary saves

        # The open basket's fixed distances and ladder arming, and the post-close pause
        # (time, and whether that basket lost), persisted so a restart keeps them.
        state = self._load_state(symbol)
        _rebuild_pause = state is None          # no file: the pause comes back from the deal history
        state = state or {}
        state.setdefault('basket', None)
        state.setdefault('last_close', None)
        _block_logged = None                    # last entry-gate block written to the log (logged on change)
        _virtual_balance = None

        while True:
            try:
                # Start of one full iteration's work (excludes the end-of-cycle sleep)
                _iter_start = time.perf_counter()

                # ── The terminal must hold this bot's demo account, else this poll decides nothing ──
                if not self._poll_guard(symbol):
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue

                # ── Gather MT5 data under lock (split into small windows for fairness) ──
                with self.mt5_lock:
                    # Ensure symbol stays subscribed in Market Watch
                    mt5.symbol_select(trade_symbol, True)
                    source_df = self.position_helper.get_rates(trade_symbol, getattr(mt5, CANDLE_TIMEFRAME), CANDLE_COUNT)
                    market_status = self.position_helper.get_market_status(
                        trade_symbol, getattr(mt5, MARKET_STATUS_TIMEFRAME), lookback_minutes=MARKET_LOOKBACK_MINUTES
                    )
                time.sleep(0)  # yield so other symbol-threads can acquire the lock
                try:
                    with self.mt5_lock:
                        buy_positions = self.position_helper.get_buy_positions(trade_symbol)
                        sell_positions = self.position_helper.get_sell_positions(trade_symbol)
                        account_info = self.position_helper.get_account_info()
                        server_time = self.position_helper._get_server_time(trade_symbol)
                        _tick = mt5.symbol_info_tick(trade_symbol)     # the decision quote (add gap)
                except TerminalReadError as e:
                    # The positions are not known this poll (not "none"): no sync, no bookkeeping, no decision.
                    self._poll_failed(symbol, str(e))
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue
                self._poll_succeeded(symbol)
                _now = time.time()
                _bid = float(_tick.bid) if _tick is not None else None
                _ask = float(_tick.ask) if _tick is not None else None

                _buy_ct = buy_positions['count'] if buy_positions else 0
                _sell_ct = sell_positions['count'] if sell_positions else 0

                # ── This bot's basket: match the persisted state with its open positions ──
                with self.mt5_lock:
                    _usd_per_price = self._usd_per_price_of(symbol, trade_symbol, mtqty)
                    _changed = self._sync_basket(symbol, trade_symbol, state, buy_positions, sell_positions,
                                                 mtqty, _usd_per_price, _now)
                    if _rebuild_pause:
                        _rebuild_pause = False
                        if state.get('last_close') is None:
                            _lc = self._last_close_from_history(_now)
                            if _lc is not None:
                                state['last_close'] = _lc
                                _changed = True
                    if self._resolve_last_close(state, _now):
                        _changed = True
                if _changed:
                    self._save_state(symbol, state)
                basket = state.get('basket')
                _in_basket = basket is not None and (
                    (basket.get('side') == 'BUY' and _buy_ct > 0 and _sell_ct == 0)
                    or (basket.get('side') == 'SELL' and _sell_ct > 0 and _buy_ct == 0))
                if _in_basket:
                    basket['last_profit'] = (buy_positions if _buy_ct else sell_positions)['total_profit']

                # ── Auto-step the running unit from live balance (only when flat) ──
                # Re-derive only while no positions are open so an active basket
                # stays on the unit it was opened with; the new tier applies to
                # the next basket. Balance is unavailable → keep the current unit.
                if _buy_ct == 0 and _sell_ct == 0:
                    balance = None
                    if virtual_balance_enabled():
                        with self.mt5_lock:
                            _virtual_balance = self._virtual_balance(_now)
                        balance = _virtual_balance
                    elif account_info:
                        balance = account_info.get('balance', 0)
                    if balance is not None:
                        if step_up_balance and step_up_balance > 0:
                            units = int(balance // step_up_balance) + 1
                        else:
                            units = 1
                        units = max(1, min(units, max_limit))
                elif _in_basket:
                    units = int(basket['units'])

                # ── Effective brake: manual override OR outside trading window ──
                # brake_manual=1 → always braked; else brake when outside the
                # configured trading_window (server-time based).
                in_window = self._is_in_trading_window(server_time, trading_window_cfg)
                brake = 1 if brake_manual or not in_window else 0

                # Save account data regardless of candle availability
                if account_info:
                    self._save_account_data(account_info)

                # ── Indicators & signals (only when candle data is available) ──
                buy_signal = Signal.DO_NOTHING
                sell_signal = Signal.DO_NOTHING
                analysis_data = {}
                has_candle_data = source_df is not None and len(source_df) > 0
                candle_is_fresh = False
                candle_age_min = None
                trend_now = 0              # sign of the TREND_TF MACD signal line, last closed bar
                trend_signal = None
                vol_now = None             # VOL_TF volatility unit, last closed bar (price units)

                if not has_candle_data:
                    print(f"[{symbol}] WARNING: No candle data returned by MT5")
                elif market_status and not market_status.get('is_open'):
                    print(f"[{symbol}] Market {market_status.get('status')} — {market_status.get('minutes_since_last')}m since last candle")

                if has_candle_data:
                    # Market liveness is judged from the M1 market probe (latest M1
                    # bar + tick), NOT from the SHA source bar. The SHA source is now
                    # M15, whose forming bar is up to 15 minutes "old" by design, so its
                    # age must never gate trading. market_status is tick-aware and
                    # timeframe-agnostic, so it stays correct regardless of the SHA
                    # source timeframe.
                    candle_is_fresh = bool(market_status.get('is_open')) if market_status else False

                    # Age of the latest M15 SHA bar — kept for logging/analysis only.
                    try:
                        last_candle_time = source_df['time'].iloc[-1]
                        if getattr(last_candle_time, 'tzinfo', None) is None:
                            last_candle_time = last_candle_time.replace(tzinfo=timezone.utc)
                        candle_age_min = (server_time - last_candle_time).total_seconds() / 60.0
                    except Exception:
                        candle_age_min = None

                    if not candle_is_fresh:
                        _mins = market_status.get('minutes_since_last') if market_status else None
                        print(f"[{symbol}] Market not live ({_mins}m since last activity) — SHA/trading skipped this cycle")

                if has_candle_data and candle_is_fresh:
                    # Capitalize columns for indicator compatibility
                    source_df.rename(columns={
                        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'
                    }, inplace=True)
                    
                    # Calculate RSI for multiple timeframes (entry filter + DCA ladder + final close).
                    # Fetched INDEPENDENTLY of the SHA source (its own small count via a
                    # lightweight fetch), so the mean-reversion ladder is never impacted
                    # by the SHA timeframe/candle-count. Union of all needed timeframes,
                    # de-duplicated while preserving order.
                    rsi_mtf = {}
                    slopes = {}   # D1/H4/H1/15M latest-pivot slopes (RSI+MACD) -> the weighted score
                    rsi_graphs = {}  # per-TF RSI series + pivot for the dashboard mini-charts
                    macd_graphs = {}  # per-TF MACD-histogram series + pivot for the mini-charts
                    # Votes for SLOPE_TIMEFRAMES plus every timeframe the strategy reads votes from
                    # (the section weights as they finally are, and a 'macd_turn' ladder's tiers).
                    slope_tfs = list(dict.fromkeys(list(SLOPE_TIMEFRAMES) + self.strategy.slope_timeframes()))
                    _trend_name = _tf_name(TREND_TF)
                    _vol_name = _tf_name(VOL_TF)
                    rsi_tf_list = []
                    for tf_name in (list(RSI_MTF_TIMEFRAMES)
                                    + list(RSI_DCA_LADDER_TIMEFRAMES)
                                    + slope_tfs
                                    + [RSI_FINAL_CLOSE_TIMEFRAME]
                                    + self.strategy.rsi_timeframes()
                                    + [n for n in (_trend_name, _vol_name) if n]):
                        if tf_name not in rsi_tf_list:
                            rsi_tf_list.append(tf_name)
                    for tf_name in rsi_tf_list:
                        with self.mt5_lock:
                            tf_df = self.position_helper.get_rates(
                                trade_symbol, getattr(mt5, tf_name), RSI_CANDLE_COUNT, simple=True
                            )
                        if tf_df is not None and len(tf_df) > 0:
                            rsi_s = self.indicator.calculate_rsi(
                                tf_df['close'], length=RSI_LENGTH, ma_type=RSI_MA_TYPE
                            )
                            rsi_mtf[tf_name] = float(rsi_s.iloc[-1]) if len(rsi_s) > 0 else 50.0
                            macd_df = None
                            # RSI + MACD-histogram latest-pivot slopes on the slope timeframes
                            # (D1/H4/H1/15M -> the weighted score). Reuses this TF's RSI fetch -
                            # no extra call beyond the per-TF rates already pulled.
                            if tf_name in slope_tfs:
                                macd_df = self.indicator.calculate_macd(
                                    tf_df['close'], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL
                                )
                                # 15M / 1H / 4H / D1 latest-pivot slopes - identical computation;
                                # all four feed the weighted score (no level-based regime).
                                rsi_slope = self.indicator.latest_pivot_slope(
                                    rsi_s, lookback=PEAK_LOOKBACK, width=PIVOT_WIDTH,
                                    ob_level=RSI_PEAK_OB, os_level=RSI_PEAK_OS
                                )
                                # MACD has no fixed OB/OS; the signal line's sign
                                # selects the pivot side -> high (OB) when signal > 0,
                                # low (OS) when signal < 0.
                                _sig = float(macd_df['signal'].iloc[-1]) if len(macd_df) > 0 else 0.0
                                _macd_side = 'high' if _sig > 0 else ('low' if _sig < 0 else None)
                                macd_slope = self.indicator.latest_pivot_slope(
                                    macd_df['hist'], lookback=PEAK_LOOKBACK, width=PIVOT_WIDTH,
                                    side=_macd_side
                                )
                                _tf_key_ = tf_name.replace('TIMEFRAME_', '')
                                slopes[_tf_key_] = {
                                    'rsi': rsi_slope, 'macd': macd_slope,
                                }
                                # RSI mini-chart: RSI line + latest (OB/OS-band) pivot +
                                # peak->current line coloured by the RSI slope sign.
                                rsi_graphs[_tf_key_] = {
                                    'series': [round(float(v), 2) for v in rsi_s.tail(RSI_GRAPH_BARS).tolist()],
                                    'current': round(float(rsi_s.iloc[-1]), 2),
                                    'pivot_bars_ago': rsi_slope.get('bars_ago'),
                                    'pivot_value': (round(rsi_slope['value'], 2)
                                                    if rsi_slope.get('value') is not None else None),
                                    'sign': rsi_slope.get('sign', 0),
                                    'bands': [RSI_PEAK_OS, RSI_PEAK_OB],
                                    'clamp': [0, 100], 'name': 'RSI',
                                }
                                # MACD-histogram mini-chart: hist line + latest (signal-
                                # side) pivot + peak->current line coloured by its slope.
                                macd_graphs[_tf_key_] = {
                                    'series': [round(float(v), 5) for v in macd_df['hist'].tail(RSI_GRAPH_BARS).tolist()],
                                    'current': round(float(macd_df['hist'].iloc[-1]), 5),
                                    'pivot_bars_ago': macd_slope.get('bars_ago'),
                                    'pivot_value': (round(macd_slope['value'], 5)
                                                    if macd_slope.get('value') is not None else None),
                                    'sign': macd_slope.get('sign', 0),
                                    'bands': [0], 'clamp': None, 'name': 'MACD',
                                }
                            # H1 trend: the MACD SIGNAL line of the last CLOSED bar (row -2; row -1 is
                            # the forming bar, whose signal line only picks the MACD vote's pivot side).
                            # 0 or NaN -> no trend -> no entry on either side.
                            if tf_name == _trend_name:
                                if macd_df is None:
                                    macd_df = self.indicator.calculate_macd(
                                        tf_df['close'], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL
                                    )
                                trend_signal = float(macd_df['signal'].iloc[-2]) if len(macd_df) >= 2 else float('nan')
                                trend_now = 1 if trend_signal > 0 else (-1 if trend_signal < 0 else 0)
                            # Volatility unit on the CLOSED bars (the forming row -1 excluded).
                            if tf_name == _vol_name:
                                vol_now = Indicator.vol_unit(tf_df['close'].to_numpy()[:-1], VOL_LEN)
                        else:
                            rsi_mtf[tf_name] = 50.0
                    current_rsi = rsi_mtf.get('TIMEFRAME_M1', 50.0)

                    # A basket taken over without the bars of its open (levels pending) takes the
                    # volatility unit measured now.
                    if _in_basket and basket.get('levels_pending') and levels_complete(vol_now, _usd_per_price):
                        basket.update(basket_levels(vol_now, _usd_per_price))
                        basket['levels_pending'] = False
                        basket['vol_source'] = 'current'
                        self._save_state(symbol, state)
                    
                    # Calculate signal. `units` (effective, capped by max_limit) drives
                    # the lot size and the USD close target. `entry_allowed` is False
                    # while the post-close re-entry cooldown is still active: after a basket
                    # that lost, LOSS_COOLDOWN_S (if set) instead of REENTRY_COOLDOWN_SECONDS.
                    _lc = state.get('last_close') or {}
                    _last_close_time = float(_lc.get('time') or 0.0)
                    _pause = LOSS_COOLDOWN_S if (_lc.get('lost') and LOSS_COOLDOWN_S > 0) else REENTRY_COOLDOWN_SECONDS
                    entry_allowed = (time.time() - _last_close_time) >= _pause
                    # The basket's distances, fixed at its open; flat: the configured ones (unused).
                    if _in_basket:
                        _tgt_u = basket.get('target_usd_per_unit')
                        _sl_u = basket.get('stop_usd_per_unit')
                        _gap = float(basket.get('gap_px') or 0.0)
                        _armed = bool(basket.get('ladder_armed'))
                        _plist = _sorted_positions((buy_positions if _buy_ct else sell_positions).get('positions'))
                        _last_fill = float(_plist[-1].price_open) if _plist else None
                    else:
                        _flat_levels = basket_levels(None, _usd_per_price)
                        _tgt_u = _flat_levels['target_usd_per_unit']
                        _sl_u = _flat_levels['stop_usd_per_unit']
                        _gap, _armed, _last_fill = 0.0, False, None
                    close_threshold = None if _tgt_u is None else _tgt_u * units
                    stop_threshold = None if _sl_u is None else _sl_u * units
                    buy_signal, sell_signal, analysis_data = self.strategy.calculate_signal(
                        source_df,
                        buy_positions, sell_positions, units,
                        close_threshold=close_threshold,
                        rsi_value=current_rsi,
                        rsi_mtf=rsi_mtf,
                        slopes=slopes,
                        entry_allowed=entry_allowed,
                        stop_threshold=stop_threshold,
                        ladder_armed=_armed,
                        ladder_gap=_gap,
                        last_fill_price=_last_fill,
                        bid=_bid, ask=_ask,
                    )
                    # The macd_turn ladder's arming is a fact of this poll's votes: keep it.
                    if _in_basket and bool(analysis_data.get('ladder_armed')) != _armed:
                        basket['ladder_armed'] = bool(analysis_data.get('ladder_armed'))
                        self._save_state(symbol, state)
                    # A close that left positions behind is finished first.
                    if _in_basket and basket.get('close_pending'):
                        if basket['side'] == 'BUY':
                            buy_signal = Signal.CLOSE_BUY
                        else:
                            sell_signal = Signal.CLOSE_SELL
                        analysis_data['exit_reason'] = 'close_retry'
                    analysis_data['rsi_graphs'] = rsi_graphs
                    analysis_data['macd_graphs'] = macd_graphs
                    analysis_data['candle_fresh'] = True
                    analysis_data['trend'] = trend_now if TREND_TF is not None else None
                    analysis_data['trend_signal'] = trend_signal if trend_signal == trend_signal else None
                    analysis_data['vol_unit_now'] = vol_now
                    analysis_data['loss_pause_s'] = _pause
                    analysis_data['pause_left_s'] = max(0.0, round(_pause - (time.time() - _last_close_time), 1))
                    analysis_data['last_close_lost'] = _lc.get('lost')
                else:
                    analysis_data['candle_fresh'] = False

                # Always populate source metadata (regardless of fresh/stale)
                if has_candle_data:
                    analysis_data['source_candle_count'] = int(len(source_df))
                    analysis_data['rates_source'] = source_df.attrs.get('rates_source', 'unknown')
                    analysis_data['synthetic_bar'] = bool(source_df.attrs.get('synthetic_appended', False))
                    analysis_data['tick_rebuilt'] = bool(source_df.attrs.get('tick_rebuilt', False))
                    try:
                        analysis_data['last_source_candle_time'] = source_df['time'].iloc[-1].isoformat()
                    except Exception:
                        analysis_data['last_source_candle_time'] = None
                else:
                    analysis_data['source_candle_count'] = 0
                    analysis_data['rates_source'] = 'none'
                    analysis_data['synthetic_bar'] = False
                    analysis_data['tick_rebuilt'] = False
                    analysis_data['last_source_candle_time'] = None
                analysis_data['candle_age_min'] = round(float(candle_age_min), 2) if candle_age_min is not None else None

                # Running unit (auto-derived from balance) so the dashboard/logs
                # show the current tier and its inputs.
                analysis_data['unit_times'] = units
                analysis_data['step_up_balance'] = step_up_balance
                analysis_data['unit_max_limit'] = max_limit
                analysis_data['design'] = DESIGN_NAME
                analysis_data['virtual_balance'] = _virtual_balance if virtual_balance_enabled() else None
                analysis_data['basket_levels'] = ({
                    'units': basket.get('units'),
                    'target_usd': (None if basket.get('target_usd_per_unit') is None
                                   else round(basket['target_usd_per_unit'] * basket['units'], 2)),
                    'stop_usd': (None if basket.get('stop_usd_per_unit') is None
                                 else round(basket['stop_usd_per_unit'] * basket['units'], 2)),
                    'gap_px': basket.get('gap_px'),
                    'vol_unit': basket.get('vol_unit'),
                    'ladder_armed': basket.get('ladder_armed'),
                } if _in_basket else None)

                # ── Build JSON data (always saved so dashboard stays current) ──
                symbol_data = {
                    'symbol': symbol,
                    'mt5_symbol': trade_symbol,
                    'last_updated': datetime.now(tz=timezone.utc).isoformat(),
                    'server_time': server_time.isoformat(),
                    'market_status': market_status,
                    'account': account_info if account_info else {},
                    'positions': {
                        'buy': {
                            'count': buy_positions['count'] if buy_positions else 0,
                            'total_profit': buy_positions['total_profit'] if buy_positions else 0,
                            'total_volume': buy_positions['total_volume'] if buy_positions else 0,
                            'first_profit': buy_positions['first_profit'] if buy_positions else 0,
                            'first_volume': buy_positions['first_volume'] if buy_positions else 0,
                            'last_profit': buy_positions['last_profit'] if buy_positions else 0,
                            'last_volume': buy_positions['last_volume'] if buy_positions else 0,
                        },
                        'sell': {
                            'count': sell_positions['count'] if sell_positions else 0,
                            'total_profit': sell_positions['total_profit'] if sell_positions else 0,
                            'total_volume': sell_positions['total_volume'] if sell_positions else 0,
                            'first_profit': sell_positions['first_profit'] if sell_positions else 0,
                            'first_volume': sell_positions['first_volume'] if sell_positions else 0,
                            'last_profit': sell_positions['last_profit'] if sell_positions else 0,
                            'last_volume': sell_positions['last_volume'] if sell_positions else 0,
                        },
                    },
                    'signal': {
                        'buy_status': buy_signal.name,
                        'sell_status': sell_signal.name,
                    },
                    'analysis': analysis_data,
                    'order_response': None,
                    'demo': {
                        'branch': DEMO_BRANCH, 'magic': MAGIC, 'design': DESIGN_NAME,
                        'virtual_balance': analysis_data.get('virtual_balance'),
                        'basket': state.get('basket'), 'last_close': state.get('last_close'),
                    },
                }
                
                # Execute buy signal
                order_response = None
                close_response = None
                if has_candle_data and candle_is_fresh and buy_signal == Signal.BUY:
                    if not brake:
                        _why = entry_block_reason(1, trend_now, vol_now, _usd_per_price)
                        if _why is None:
                            _levels = basket_levels(vol_now, _usd_per_price)   # fixed for this basket's life
                            with self.mt5_lock:
                                order_response = self.position_helper.buy(trade_symbol, units * mtqty)
                            if self._order_done(order_response):
                                state['basket'] = self._new_basket('BUY', units, _levels, time.time())
                                self._save_state(symbol, state)
                            _block_logged = None
                            self._log_event(symbol, 'BUY_EXECUTED', 'ENTRY', {
                                'mt5_symbol': trade_symbol,
                                'qty': units * mtqty,
                                'target_usd': None if _levels['target_usd_per_unit'] is None else round(_levels['target_usd_per_unit'] * units, 2),
                                'stop_usd': None if _levels['stop_usd_per_unit'] is None else round(_levels['stop_usd_per_unit'] * units, 2),
                                'vol_unit': _levels['vol_unit'],
                                'response': str(order_response),
                            }, server_time=server_time)
                        elif _block_logged != ('BUY', _why):
                            _block_logged = ('BUY', _why)
                            self._log_event(symbol, 'BUY_SIGNAL', 'SIGNAL', {
                                'note': f'Entry blocked: {_why} — order skipped',
                                'trend_signal': analysis_data.get('trend_signal'), 'vol_unit': vol_now,
                            }, server_time=server_time)
                    else:
                        self._log_event(symbol, 'BUY_SIGNAL', 'SIGNAL', {
                            'note': 'Brake active — order skipped',
                        }, server_time=server_time)
                elif buy_signal == Signal.BUY_MORE:
                    vol = self.strategy.next_add_volume(buy_positions['total_volume'], buy_positions['count'], units, mtqty)
                    with self.mt5_lock:
                        order_response = self.position_helper.buy(trade_symbol, vol)
                    if _in_basket and self._order_done(order_response):
                        basket['ladder_armed'] = False      # the next add needs a new turn
                        self._save_state(symbol, state)
                    self._log_event(symbol, 'BUY_MORE_EXECUTED', 'ENTRY', {
                        'mt5_symbol': trade_symbol,
                        'qty': vol,
                        'fibo_level': buy_positions['count'] + 1,
                        'total_volume': buy_positions['total_volume'],
                        'total_profit': buy_positions['total_profit'],
                        'first_profit': buy_positions['first_profit'],
                        'response': str(order_response),
                    }, server_time=server_time)
                    time.sleep(ORDER_COOLDOWN_SECONDS)  # Wait for MT5 to register position
                elif buy_signal == Signal.CLOSE_BUY:
                    with self.mt5_lock:
                        close_response = self.position_helper.close_by_type(trade_symbol, 0)
                    # start the re-entry cooldown (only once the basket is really closed)
                    _closed = self._after_close(symbol, state, 'BUY', close_response, buy_positions,
                                                analysis_data.get('exit_reason'), time.time())
                    self._log_event(symbol, 'CLOSE_BUY', 'EXIT', {
                        'mt5_symbol': trade_symbol,
                        'positions_closed': close_response.get('closed_count', 0),
                        'total_profit': buy_positions['total_profit'] if buy_positions else 0,
                        'reason': analysis_data.get('exit_reason'),
                        'realised_pnl': _closed.get('pnl') if _closed else None,
                        'lost': _closed.get('lost') if _closed else None,
                        'response': close_response,
                    }, server_time=server_time)
                
                # Execute sell signal
                if has_candle_data and candle_is_fresh and sell_signal == Signal.SELL:
                    if not brake:
                        _why = entry_block_reason(-1, trend_now, vol_now, _usd_per_price)
                        if _why is None:
                            _levels = basket_levels(vol_now, _usd_per_price)   # fixed for this basket's life
                            with self.mt5_lock:
                                order_response = self.position_helper.sell(trade_symbol, units * mtqty)
                            if self._order_done(order_response):
                                state['basket'] = self._new_basket('SELL', units, _levels, time.time())
                                self._save_state(symbol, state)
                            _block_logged = None
                            self._log_event(symbol, 'SELL_EXECUTED', 'ENTRY', {
                                'mt5_symbol': trade_symbol,
                                'qty': units * mtqty,
                                'target_usd': None if _levels['target_usd_per_unit'] is None else round(_levels['target_usd_per_unit'] * units, 2),
                                'stop_usd': None if _levels['stop_usd_per_unit'] is None else round(_levels['stop_usd_per_unit'] * units, 2),
                                'vol_unit': _levels['vol_unit'],
                                'response': str(order_response),
                            }, server_time=server_time)
                        elif _block_logged != ('SELL', _why):
                            _block_logged = ('SELL', _why)
                            self._log_event(symbol, 'SELL_SIGNAL', 'SIGNAL', {
                                'note': f'Entry blocked: {_why} — order skipped',
                                'trend_signal': analysis_data.get('trend_signal'), 'vol_unit': vol_now,
                            }, server_time=server_time)
                    else:
                        self._log_event(symbol, 'SELL_SIGNAL', 'SIGNAL', {
                            'note': 'Brake active — order skipped',
                        }, server_time=server_time)
                elif sell_signal == Signal.SELL_MORE:
                    vol = self.strategy.next_add_volume(sell_positions['total_volume'], sell_positions['count'], units, mtqty)
                    with self.mt5_lock:
                        order_response = self.position_helper.sell(trade_symbol, vol)
                    if _in_basket and self._order_done(order_response):
                        basket['ladder_armed'] = False      # the next add needs a new turn
                        self._save_state(symbol, state)
                    self._log_event(symbol, 'SELL_MORE_EXECUTED', 'ENTRY', {
                        'mt5_symbol': trade_symbol,
                        'qty': vol,
                        'fibo_level': sell_positions['count'] + 1,
                        'total_volume': sell_positions['total_volume'],
                        'total_profit': sell_positions['total_profit'],
                        'first_profit': sell_positions['first_profit'],
                        'response': str(order_response),
                    }, server_time=server_time)
                    time.sleep(ORDER_COOLDOWN_SECONDS)  # Wait for MT5 to register position
                elif sell_signal == Signal.CLOSE_SELL:
                    with self.mt5_lock:
                        close_response = self.position_helper.close_by_type(trade_symbol, 1)
                    # start the re-entry cooldown (only once the basket is really closed)
                    _closed = self._after_close(symbol, state, 'SELL', close_response, sell_positions,
                                                analysis_data.get('exit_reason'), time.time())
                    self._log_event(symbol, 'CLOSE_SELL', 'EXIT', {
                        'mt5_symbol': trade_symbol,
                        'positions_closed': close_response.get('closed_count', 0),
                        'total_profit': sell_positions['total_profit'] if sell_positions else 0,
                        'reason': analysis_data.get('exit_reason'),
                        'realised_pnl': _closed.get('pnl') if _closed else None,
                        'lost': _closed.get('lost') if _closed else None,
                        'response': close_response,
                    }, server_time=server_time)
                
                # Attach order response if any
                if order_response is not None:
                    symbol_data['order_response'] = str(order_response)
                
                # Attach close response if any
                if close_response is not None:
                    symbol_data['close_response'] = close_response
                
                # ── Full-iteration timing (work only, excludes the trailing sleep) ──
                iteration_ms = round((time.perf_counter() - _iter_start) * 1000, 1)
                symbol_data['iteration_ms'] = iteration_ms
                symbol_data['analysis']['iteration_ms'] = iteration_ms
                print(f"[{symbol}] iteration {iteration_ms} ms")

                # Save to JSON
                self._save_symbol_data(symbol, symbol_data)
                
                # Save daily trade logs (throttled to reduce MT5 lock contention)
                _now_ts = time.time()
                if has_candle_data and candle_is_fresh:
                    try:
                        if _now_ts - _last_daily_save >= _DAILY_SAVE_INTERVAL:
                            self._save_daily_trades(symbol, mt5_symbol=trade_symbol)
                            _last_daily_save = _now_ts
                        if _now_ts - _last_hist_save >= _HIST_SAVE_INTERVAL:
                            self._save_historical_summary(symbol, mt5_symbol=trade_symbol)
                            _last_hist_save = _now_ts
                    except Exception:
                        pass  # Non-critical, don't break the main loop
                
                time.sleep(max(brake, 1))  # At least 1s between cycles
                
                # Check if supervisor requested shutdown (mode change)
                if self._stop_event.is_set():
                    return
                
            except Exception as e:
                print(f"[{symbol}] Error: {e}")
                time.sleep(1)
                if self._stop_event.is_set():
                    return
    
    def run_multithreaded_processing(self):
        """Step 4: Start processing for all symbols.
        
        Single-symbol mode: runs directly on the main thread (no threading overhead).
        Multi-symbol mode: spawns one thread per symbol (legacy, not recommended).
        """
        # Reset stop event for this run
        self._stop_event.clear()

        # ── Single-symbol: run directly on main thread (no threading) ──
        if len(self.symbols) == 1:
            symbol = self.symbols[0]
            print(f"\n{'='*60}")
            print(f"  Running single-symbol process: {symbol}")
            print(f"{'='*60}")
            print(f"Press Ctrl+C to stop\n")
            try:
                self.process_symbol(symbol)
            except KeyboardInterrupt:
                print("\n\n⚠ Stopping...")
                self._stop_event.set()
                raise
            return

        # ── Multi-symbol: threaded (legacy fallback) ──
        print(f"\n{'='*60}")
        print(f"  Starting Continuous Multithreaded Processing")
        print(f"  ⚠ Running {len(self.symbols)} symbols in threads — consider")
        print(f"    running separate processes with --symbol for each instead.")
        print(f"{'='*60}\n")
        
        max_workers = len(self.symbols)
        
        print(f"Launching {max_workers} threads (1 per symbol)...")
        print(f"Press Ctrl+C to stop\n")
        
        # Start threads — they will run until stop_event is set
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='Symbol') as executor:
            # Submit all symbol processing tasks (infinite loops)
            futures = [
                executor.submit(self.process_symbol, symbol) 
                for symbol in self.symbols
            ]
            
            # Keep main thread alive — futures complete when stop_event is set
            try:
                for future in as_completed(futures):
                    future.result()
                    if self._stop_event.is_set():
                        break
            except KeyboardInterrupt:
                print("\n\n⚠ Stopping all threads...")
                self._stop_event.set()
                executor.shutdown(wait=False, cancel_futures=True)
                raise
    
    def cleanup(self):
        """Step 5: Cleanup and shutdown MT5"""
        if self.mt5_initialized:
            mt5.shutdown()
            self.mt5_initialized = False
            print("\n✓ MT5 connection closed")
    
    def _init_cycle(self):
        """
        Single initialisation cycle: write mode to config → load credentials
        → load symbols → initialise MT5.  Returns True on success.
        """
        # ── Write current mode to active_config so dashboard can display it ──
        _acfg_path = os.path.join(OUTPUT_DIR, ACTIVE_CONFIG_FILENAME)
        try:
            with open(_acfg_path, 'r') as _af:
                _acfg = json.load(_af)
        except (FileNotFoundError, json.JSONDecodeError):
            _acfg = {}
        _acfg['mode'] = self.mode
        try:
            os.makedirs(os.path.dirname(_acfg_path) or '.', exist_ok=True)
            with open(_acfg_path, 'w') as _af:
                json.dump(_acfg, _af, indent=2)
        except OSError:
            pass

        print(f"\n{'#'*60}")
        print(f"#  JOB STARTED - {self.mode.upper()} MODE")
        print(f"{'#'*60}\n")
        print(f"✓ {design_summary()}")

        # Step 1: Load Credentials
        if not self.load_credentials():
            print("\n✗ Job Failed: Could not load credentials")
            return False

        # Step 2: Load Symbols
        if not self.load_symbols():
            print("\n✗ Job Failed: Could not load symbols")
            return False

        # Step 3: Initialize MT5
        if not self.initialize_mt5():
            print("\n✗ Job Failed: Could not initialize MT5")
            return False

        return True

    def execute_job(self):
        """
        Main Job Orchestrator.
        Initialises MT5, starts worker threads, and runs until Ctrl+C.
        Mode is fixed from the command line — use start_job.bat to switch.
        """
        try:
            # ── The design in constants.py must be one this bot can run (checked once, before connecting) ──
            _problems = design_problems()
            if _problems:
                for _p in _problems:
                    print(f"✗ Design: {_p}")
                print("\n✗ Job Failed: the design in constants.py is refused (see above)")
                return False

            # ── Initialise (retry up to 3 times) ──
            for _attempt in range(1, 4):
                if self._init_cycle():
                    break
                print(f"\n⚠ Init attempt {_attempt}/3 failed, retrying in 5s...")
                time.sleep(5)
            else:
                print("\n✗ All init attempts failed. Restart start_job.bat to try again.")
                return False

            # ── Run processing (blocks until Ctrl+C) ──
            self.run_multithreaded_processing()

            self.cleanup()
            print(f"\n{'#'*60}")
            print(f"#  JOB COMPLETED SUCCESSFULLY")
            print(f"{'#'*60}\n")
            return True

        except KeyboardInterrupt:
            print("\n\n⚠ Job interrupted by user")
            self._stop_event.set()
            self.cleanup()
            return False
        except Exception as e:
            print(f"\n✗ Job Failed with exception: {e}")
            self._stop_event.set()
            self.cleanup()
            return False


def main():
    """
    Main entry point for the application
    
    Usage:
        app.py [mode]                      # Run all active symbols (legacy)
        app.py [mode] --symbol SYMBOL      # Run a SINGLE symbol only (recommended)
    
    Running one symbol per process avoids MT5 threading issues
    where SHA candle data can overlap between symbols.
    """
    import argparse

    parser = argparse.ArgumentParser(description='Alcadeias Trading Bot')
    parser.add_argument('mode', nargs='?', default='demo', choices=['demo', 'live'],
                        help='Account mode (default: demo)')
    parser.add_argument('--symbol', '-s', type=str, default=None,
                        help='Run only this symbol (e.g. BTCUSDm). '
                             'Recommended: run one process per symbol.')
    args = parser.parse_args()
    if DEMO_BRANCH and args.mode != 'demo':
        parser.error(f"this is the demo branch {DEMO_BRANCH}: mode '{args.mode}' is refused, it trades on demo only")

    # Create bot instance and execute job
    bot = MT5TradingBot(mode=args.mode, target_symbol=args.symbol)
    success = bot.execute_job()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if '__main__' == __name__:
    main()