import MetaTrader5 as mt5
import json
import os
import sys
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from mt5_helper import MT5PositionHelper
from indicator import Indicator
from strategy import Strategy, Signal
from datetime import timezone
from constants import (
    SHA_LENGTH, SHA_MA_TYPE,
    SHA_TREND_LENGTH, SHA_TREND_MA_TYPE,
    DEFAULT_GAP_RANGE,
    CANDLE_TIMEFRAME, CANDLE_COUNT,
    MARKET_STATUS_TIMEFRAME, MARKET_LOOKBACK_MINUTES,
    OUTPUT_DIR, DAILY_TRADE_SUBDIR,
    HISTORICAL_SUMMARY_DAYS, HISTORICAL_SUMMARY_FILENAME,
    STRATEGY_LOG_FILENAME, STRATEGY_LOG_MAX_ENTRIES,
    ORDER_COOLDOWN_SECONDS,
    ACTIVE_CONFIG_FILENAME,
)


class MT5TradingBot:
    """Main Trading Bot Class with Clean Architecture"""
    
    def __init__(self, mode='demo'):
        """
        Initialize the trading bot
        
        Args:
            mode (str): Either 'demo' or 'live'
        """
        self.mode = mode.lower()
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
            print(f"✗ Login failed: {error}")
            mt5.shutdown()
            return False
        
        # Get account info
        account_info = mt5.account_info()
        if account_info is None:
            print("✗ Failed to get account info")
            mt5.shutdown()
            return False
        
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
        output_dir = os.path.join(r'C:\Alcadeias', 'daily_trade', symbol)
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
    
    def process_symbol(self, symbol):
        """
        Process a single symbol (will be called in separate threads)
        Lightweight and optimized - runs in infinite loop
        
        Args:
            symbol (str): Symbol to process (e.g., 'BTCUSD', 'XAUUSD')
        """
        from datetime import datetime
        
        # Get configuration once before loop (per-symbol config from array)
        sym_cfg = self.symbol_configs.get(symbol, {})
        brake = self.symbols_config.get('brake', 0)
        times = sym_cfg.get('times', 1)
        mtqty = self.symbols_config.get('mtqty', 0.01)
        symbol_gap_range = sym_cfg.get('gap_range', DEFAULT_GAP_RANGE)
        symbol_fibo_power = sym_cfg.get('fibo_power', None)
        trade_symbol = self.symbol_map.get(symbol, symbol)

        # Throttle expensive saves so they don't block other threads
        _last_daily_save = 0.0
        _last_hist_save = 0.0
        _DAILY_SAVE_INTERVAL = 60       # seconds between daily-trade saves
        _HIST_SAVE_INTERVAL = 300       # seconds between historical-summary saves
        _last_seen_candle_time = None
        _same_candle_count = 0
        
        while True:
            try:
                # ── Gather MT5 data under lock (split into small windows for fairness) ──
                with self.mt5_lock:
                    # Ensure symbol stays subscribed in Market Watch
                    mt5.symbol_select(trade_symbol, True)
                    source_df = self.position_helper.get_rates(trade_symbol, getattr(mt5, CANDLE_TIMEFRAME), CANDLE_COUNT)
                    market_status = self.position_helper.get_market_status(
                        trade_symbol, getattr(mt5, MARKET_STATUS_TIMEFRAME), lookback_minutes=MARKET_LOOKBACK_MINUTES
                    )
                time.sleep(0)  # yield so other symbol-threads can acquire the lock
                with self.mt5_lock:
                    buy_positions = self.position_helper.get_buy_positions(trade_symbol)
                    sell_positions = self.position_helper.get_sell_positions(trade_symbol)
                    account_info = self.position_helper.get_account_info()
                    server_time = self.position_helper._get_server_time(trade_symbol)

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

                if not has_candle_data:
                    print(f"[{symbol}] WARNING: No candle data returned by MT5")
                elif market_status and not market_status.get('is_open'):
                    print(f"[{symbol}] Market {market_status.get('status')} — {market_status.get('minutes_since_last')}m since last candle")

                if has_candle_data:
                    try:
                        # Always derive freshness from the ACTUAL source_df we will
                        # use (which may contain tick-rebuilt bars), NOT from
                        # market_status that fetches its own (possibly stale) bars.
                        last_candle_time = source_df['time'].iloc[-1]
                        if getattr(last_candle_time, 'tzinfo', None) is None:
                            last_candle_time = last_candle_time.replace(tzinfo=timezone.utc)
                        candle_age_min = (server_time - last_candle_time).total_seconds() / 60.0

                        # When bars were rebuilt from ticks, the rebuild IS our
                        # freshest available data — always treat as fresh so SHA
                        # analysis runs instead of being permanently blocked.
                        if source_df.attrs.get('tick_rebuilt', False):
                            candle_is_fresh = True
                        else:
                            candle_is_fresh = candle_age_min <= max(MARKET_LOOKBACK_MINUTES + 1, 4)
                    except Exception:
                        candle_is_fresh = False

                    try:
                        current_candle_time = source_df['time'].iloc[-1]
                        if _last_seen_candle_time is not None and current_candle_time == _last_seen_candle_time:
                            _same_candle_count += 1
                            if _same_candle_count % 30 == 0:
                                tick_time = None
                                if market_status:
                                    tick_time = market_status.get('last_tick_time')
                                print(
                                    f"[{symbol}] Candle time not advancing: {current_candle_time} "
                                    f"(same for {_same_candle_count} cycles) | age={candle_age_min}m | tick={tick_time}"
                                )
                        else:
                            _last_seen_candle_time = current_candle_time
                            _same_candle_count = 0
                    except Exception:
                        pass

                    if not candle_is_fresh:
                        print(f"[{symbol}] WARNING: Stale candle stream (age={candle_age_min}m) — SHA/trading skipped this cycle")

                if has_candle_data and candle_is_fresh:
                    # Capitalize columns for indicator compatibility
                    source_df.rename(columns={
                        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'
                    }, inplace=True)
                    
                    # Calculate SHA signal indicator
                    sha_df = self.indicator.calculate_sha_v3(
                        source_df, 
                        length=SHA_LENGTH, 
                        ma_type=SHA_MA_TYPE,
                    )
                    
                    # Calculate SHA trend indicator
                    sha_trend_df = self.indicator.calculate_sha_v3(
                        source_df, 
                        length=SHA_TREND_LENGTH, 
                        ma_type=SHA_TREND_MA_TYPE,
                    )
                    
                    # Calculate gap% between signal SHA and trend SHA
                    gap_pct_series = self.indicator.calculate_sha_gap(sha_df, sha_trend_df)
                    
                    # Calculate signal
                    symbol_cfg = self.symbol_configs.get(symbol, {})
                    symbol_close = symbol_cfg.get('close', 2)
                    buy_signal, sell_signal, analysis_data = self.strategy.calculate_signal(
                        source_df, sha_df, sha_trend_df, gap_pct_series,
                        buy_positions, sell_positions, times, gap_range=symbol_gap_range,
                        fibo_power=symbol_fibo_power, close_threshold=symbol_close
                    )
                    analysis_data['candle_fresh'] = True
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
                }
                
                # Execute buy signal
                order_response = None
                close_response = None
                if has_candle_data and candle_is_fresh and buy_signal == Signal.BUY:
                    if not brake:
                        with self.mt5_lock:
                            order_response = self.position_helper.buy(trade_symbol, times * mtqty)
                        self._log_event(symbol, 'BUY_EXECUTED', 'ENTRY', {
                            'mt5_symbol': trade_symbol,
                            'qty': times * mtqty,
                            'response': str(order_response),
                        }, server_time=server_time)
                    else:
                        self._log_event(symbol, 'BUY_SIGNAL', 'SIGNAL', {
                            'note': 'Brake active — order skipped',
                        }, server_time=server_time)
                elif buy_signal == Signal.BUY_MORE:
                    vol = self.strategy._get_next_fibo_volume(buy_positions['count'], times)
                    with self.mt5_lock:
                        order_response = self.position_helper.buy(trade_symbol, vol)
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
                    self._log_event(symbol, 'CLOSE_BUY', 'EXIT', {
                        'mt5_symbol': trade_symbol,
                        'positions_closed': close_response.get('closed_count', 0),
                        'total_profit': buy_positions['total_profit'] if buy_positions else 0,
                        'response': close_response,
                    }, server_time=server_time)
                
                # Execute sell signal
                if has_candle_data and candle_is_fresh and sell_signal == Signal.SELL:
                    if not brake:
                        with self.mt5_lock:
                            order_response = self.position_helper.sell(trade_symbol, times * mtqty)
                        self._log_event(symbol, 'SELL_EXECUTED', 'ENTRY', {
                            'mt5_symbol': trade_symbol,
                            'qty': times * mtqty,
                            'response': str(order_response),
                        }, server_time=server_time)
                    else:
                        self._log_event(symbol, 'SELL_SIGNAL', 'SIGNAL', {
                            'note': 'Brake active — order skipped',
                        }, server_time=server_time)
                elif sell_signal == Signal.SELL_MORE:
                    vol = self.strategy._get_next_fibo_volume(sell_positions['count'], times)
                    with self.mt5_lock:
                        order_response = self.position_helper.sell(trade_symbol, vol)
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
                    self._log_event(symbol, 'CLOSE_SELL', 'EXIT', {
                        'mt5_symbol': trade_symbol,
                        'positions_closed': close_response.get('closed_count', 0),
                        'total_profit': sell_positions['total_profit'] if sell_positions else 0,
                        'response': close_response,
                    }, server_time=server_time)
                
                # Attach order response if any
                if order_response is not None:
                    symbol_data['order_response'] = str(order_response)
                
                # Attach close response if any
                if close_response is not None:
                    symbol_data['close_response'] = close_response
                
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
        """Step 4: Start infinite multithreaded processing for all symbols."""
        print(f"\n{'='*60}")
        print(f"  Starting Continuous Multithreaded Processing")
        print(f"{'='*60}\n")
        
        max_workers = len(self.symbols)
        
        print(f"Launching {max_workers} threads (1 per symbol)...")
        print(f"Press Ctrl+C to stop\n")

        # Reset stop event for this run
        self._stop_event.clear()
        
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
    """
    # Get mode from command line argument (default: demo)
    mode = sys.argv[1] if len(sys.argv) > 1 else 'demo'
    mode = mode.lower()
    
    # Validate mode
    if mode not in ['demo', 'live']:
        print(f"✗ Error: Invalid mode '{mode}'. Must be 'demo' or 'live'")
        sys.exit(1)
    
    # Create bot instance and execute job
    bot = MT5TradingBot(mode=mode)
    success = bot.execute_job()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if '__main__' == __name__:
    main()