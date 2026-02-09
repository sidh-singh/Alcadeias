import MetaTrader5 as mt5
import json
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
    SHA_SMOOTH_LENGTH, SHA_SMOOTH_MA_TYPE,
    SHA_AFTER_SMOOTH_LENGTH, SHA_AFTER_SMOOTH_MA_TYPE,
    CANDLE_TIMEFRAME, CANDLE_COUNT,
    MARKET_STATUS_TIMEFRAME, MARKET_LOOKBACK_MINUTES,
    OUTPUT_DIR, DAILY_TRADE_SUBDIR,
    HISTORICAL_SUMMARY_DAYS, HISTORICAL_SUMMARY_FILENAME,
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
        self.mt5_initialized = False
        self.thread_lock = threading.Lock()
        self.position_helper = None
        self.indicator = Indicator()
        self.strategy = Strategy()
        
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
            
            self.symbols = self.symbols_config.get('symbols', [])
            if not self.symbols:
                print("✗ Warning: No symbols found in symbols.json")
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
    
    def _save_daily_trades(self, symbol):
        """Fetch today's closed deals for a symbol and save to per-symbol daily_trade folder (thread-safe)"""
        import os
        from datetime import datetime
        
        # Per-symbol folder: C:\Alcadeias\daily_trade\{symbol}\
        output_dir = os.path.join(r'C:\Alcadeias', 'daily_trade', symbol)
        os.makedirs(output_dir, exist_ok=True)
        
        # Use server time for the filename so it matches broker's trading day
        server_now = self.position_helper._get_server_time()
        filename = server_now.strftime('%d_%b_%Y').lower() + '.json'
        json_path = os.path.join(output_dir, filename)
        
        # Fetch today's closed deals for this symbol (server-time aware)
        today_deals = self.position_helper.get_today_deals(symbol)
        
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
    
    def _save_historical_summary(self, symbol):
        """Fetch last 10 years of deal history for a specific symbol and save to its folder (thread-safe)"""
        import os
        from datetime import datetime
        
        # Per-symbol folder: <OUTPUT_DIR>/daily_trade/{symbol}/
        output_dir = os.path.join(OUTPUT_DIR, DAILY_TRADE_SUBDIR, symbol)
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, HISTORICAL_SUMMARY_FILENAME)
        
        # Fetch only this symbol's deals for the configured history period
        all_deals = self.position_helper.get_deals_since(days=HISTORICAL_SUMMARY_DAYS, symbol=symbol)
        
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
    
    def process_symbol(self, symbol):
        """
        Process a single symbol (will be called in separate threads)
        Lightweight and optimized - runs in infinite loop
        
        Args:
            symbol (str): Symbol to process (e.g., 'BTCUSD', 'XAUUSD')
        """
        from datetime import datetime
        
        # Get configuration once before loop
        brake = self.symbols_config.get('brake', 0)
        times = self.symbols_config.get('times', 1)
        mtqty = self.symbols_config.get('mtqty', 0.01)
        
        while True:
            try:
                # Fetch candle data using configured timeframe and count
                source_df = self.position_helper.get_rates(symbol, getattr(mt5, CANDLE_TIMEFRAME), CANDLE_COUNT)
                
                if source_df is None or len(source_df) == 0:
                    time.sleep(brake)
                    continue
                
                # Capitalize columns for indicator compatibility
                source_df.rename(columns={
                    'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'
                }, inplace=True)
                
                # Calculate SHA indicator with configured parameters
                sha_df = self.indicator.calculate_sha_v3(
                    source_df, 
                    smooth_length=SHA_SMOOTH_LENGTH, 
                    smooth_ma_type=SHA_SMOOTH_MA_TYPE,
                    after_smooth_length=SHA_AFTER_SMOOTH_LENGTH, 
                    after_smooth_ma_type=SHA_AFTER_SMOOTH_MA_TYPE
                )
                
                # Check market status using configured timeframe & lookback
                market_status = self.position_helper.get_market_status(
                    symbol, getattr(mt5, MARKET_STATUS_TIMEFRAME), lookback_minutes=MARKET_LOOKBACK_MINUTES
                )
                
                # Get buy and sell positions
                buy_positions = self.position_helper.get_buy_positions(symbol)
                sell_positions = self.position_helper.get_sell_positions(symbol)
                
                # Get account info and save to dedicated file
                account_info = self.position_helper.get_account_info()
                if account_info:
                    self._save_account_data(account_info)
                
                # Calculate signal
                buy_signal, sell_signal, analysis_data = self.strategy.calculate_signal(
                    source_df, sha_df, buy_positions, sell_positions, times
                )
                
                # Build JSON data
                # Get server time for consistency with broker
                server_time = self.position_helper._get_server_time()
                symbol_data = {
                    'symbol': symbol,
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
                if buy_signal == Signal.BUY:
                    if not brake:
                        order_response = self.position_helper.buy(symbol, times * mtqty)
                elif buy_signal == Signal.BUY_MORE:
                    vol = self.strategy._get_next_fibo_volume(buy_positions['total_volume'], times)
                    order_response = self.position_helper.buy(symbol, vol)
                elif buy_signal == Signal.CLOSE_BUY:
                    close_response = self.position_helper.close_by_type(symbol, 0)
                
                # Execute sell signal
                if sell_signal == Signal.SELL:
                    if not brake:
                        order_response = self.position_helper.sell(symbol, times * mtqty)
                elif sell_signal == Signal.SELL_MORE:
                    vol = self.strategy._get_next_fibo_volume(sell_positions['total_volume'], times)
                    order_response = self.position_helper.sell(symbol, vol)
                elif sell_signal == Signal.CLOSE_SELL:
                    close_response = self.position_helper.close_by_type(symbol, 1)
                
                # Attach order response if any
                if order_response is not None:
                    symbol_data['order_response'] = str(order_response)
                
                # Attach close response if any
                if close_response is not None:
                    symbol_data['close_response'] = close_response
                
                # Save to JSON
                self._save_symbol_data(symbol, symbol_data)
                
                # Save daily trade logs
                try:
                    self._save_daily_trades(symbol)
                    self._save_historical_summary(symbol)
                except Exception:
                    pass  # Non-critical, don't break the main loop
                
                time.sleep(brake)
                
            except Exception as e:
                time.sleep(1)
    
    def run_multithreaded_processing(self):
        """Step 4: Start infinite multithreaded processing for all symbols"""
        print(f"\n{'='*60}")
        print(f"  Starting Continuous Multithreaded Processing")
        print(f"{'='*60}\n")
        
        max_workers = len(self.symbols)
        
        print(f"Launching {max_workers} threads (1 per symbol)...")
        print(f"Press Ctrl+C to stop\n")
        
        # Start threads - they will run forever until interrupted
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='Symbol') as executor:
            # Submit all symbol processing tasks (infinite loops)
            futures = [
                executor.submit(self.process_symbol, symbol) 
                for symbol in self.symbols
            ]
            
            # Keep main thread alive - threads run forever
            try:
                for future in futures:
                    future.result()  # This will block indefinitely
            except KeyboardInterrupt:
                print("\n\n⚠ Stopping all threads...")
                executor.shutdown(wait=False, cancel_futures=True)
                raise
    
    def cleanup(self):
        """Step 5: Cleanup and shutdown MT5"""
        if self.mt5_initialized:
            mt5.shutdown()
            print("\n✓ MT5 connection closed")
    
    def execute_job(self):
        """
        Main Job Orchestrator - Executes all steps in sequence
        This is the central function that controls the entire workflow
        """
        print(f"\n{'#'*60}")
        print(f"#  JOB STARTED - {self.mode.upper()} MODE")
        print(f"{'#'*60}\n")
        
        try:
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
            
            # Step 4: Run Multithreaded Processing (Infinite Loop)
            self.run_multithreaded_processing()
            
            # Step 5: Cleanup (only reached on interrupt)
            self.cleanup()
            
            print(f"\n{'#'*60}")
            print(f"#  JOB COMPLETED SUCCESSFULLY")
            print(f"{'#'*60}\n")
            
            return True
            
        except KeyboardInterrupt:
            print("\n\n⚠ Job interrupted by user")
            self.cleanup()
            return False
        except Exception as e:
            print(f"\n✗ Job Failed with exception: {e}")
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