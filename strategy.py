from enum import Enum
from constants import (
    STRATEGY_HEDGE, STRATEGY_LOOKBACK, STRATEGY_SHA_THRESHOLD,
    FIBO_SEQUENCE_LENGTH, DEFAULT_GAP_RANGE, FIBO_POWER_DEFAULT,
    SHA_CONVERGENCE_LOOKBACK, SHA_CLOSE_THRESHOLD, SHA_CONVERGENCE_THRESHOLD,
    RSI_OVERSOLD, RSI_OVERBOUGHT, RSI_DCA_MAX_POSITIONS,
    RSI_MTF_OVERSOLD, RSI_MTF_OVERBOUGHT,
)


class Signal(Enum):
    DO_NOTHING = 0
    BUY = 1
    SELL = 2
    CLOSE_BUY = 3
    CLOSE_SELL = 4
    BUY_MORE = 5
    SELL_MORE = 6


class Strategy:
    """HAM Strategy - Heiken Ashi Martingale Signal Calculator"""
    
    def __init__(self):
        self.hedge = STRATEGY_HEDGE
        self.lookback = STRATEGY_LOOKBACK
        self.sha_threshold = STRATEGY_SHA_THRESHOLD
    
    def _recur_fibo(self, n):
        if n <= 1:
            return n
        return self._recur_fibo(n - 1) + self._recur_fibo(n - 2)
    
    def _get_fibo_qty(self, qty_count, times):
        fib = [self._recur_fibo(i) for i in range(FIBO_SEQUENCE_LENGTH)][2:]
        try:
            return fib[qty_count] * times
        except (IndexError, ValueError):
            return times
    
    def _get_next_fibo_volume(self, total_volume, times):
        """
        Get next fibonacci volume based on total open volume.
        Finds total_volume in fib sequence and returns the next fib value.
        
        Eg: fib = [0.01, 0.02, 0.03, 0.05, 0.08, 0.13, ...]
            total_volume 0.01 → next 0.02
            total_volume 0.03 → next 0.05
            total_volume 0.08 → next 0.13
        
        Args:
            total_volume: Total volume of all open positions for this direction
            times: Multiplier from config
        
        Returns:
            float: Next fibo volume in lots
        """
        fib = [self._recur_fibo(i) for i in range(FIBO_SEQUENCE_LENGTH)][2:]
        total_units = round(total_volume * 100 / times) if times else 0
        for i, f in enumerate(fib):
            if f >= total_units:
                try:
                    return round(fib[i + 1] * times / 100, 2)
                except IndexError:
                    return round(0.01 * times, 2)
        return round(0.01 * times, 2)
    
    def _analyze(self, source_df, sha_df):
        """
        Analyze last N candles for SHA power
        
        Returns:
            tuple: (lt_sha_power_list, ct_power_list)
        """
        lt_sha_power_list = []
        ct_power_list = []

        max_lookback = min(self.lookback, len(source_df), len(sha_df))
        if max_lookback <= 0:
            return lt_sha_power_list, ct_power_list
        
        for i in range(max_lookback):
            idx = -(i + 1)
            
            # SHA candle
            sha_diff = sha_df['Close'].iloc[idx] - sha_df['Open'].iloc[idx]
            sha_range = sha_df['High'].iloc[idx] - sha_df['Low'].iloc[idx]
            
            # Price candle
            price_diff = source_df['Close'].iloc[idx] - source_df['Open'].iloc[idx]
            price_range = source_df['High'].iloc[idx] - source_df['Low'].iloc[idx]
            
            # SHA power (bullish or bearish)
            if sha_range != 0 and (sha_diff / sha_range) >= self.sha_threshold:
                lt_sha_power_list.append(1)
            else:
                lt_sha_power_list.append(0)
            
            # Price power
            if price_range != 0 and (price_diff / price_range) >= self.sha_threshold:
                ct_power_list.append(1)
            else:
                ct_power_list.append(0)
            
            values = [sha_diff, sha_range, price_diff, price_range]
            if any(v != v for v in values):
                lt_sha_power_list.append(0)
                ct_power_list.append(0)
                continue
        
        return lt_sha_power_list, ct_power_list
    
    def _analyze_trend(self, sha_trend_df):
        """Analyze last N candles of trend SHA for power (bullish/bearish)."""
        trend_power_list = []
        max_lookback = min(self.lookback, len(sha_trend_df))
        if max_lookback <= 0:
            return trend_power_list

        for i in range(max_lookback):
            idx = -(i + 1)
            sha_diff = sha_trend_df['Close'].iloc[idx] - sha_trend_df['Open'].iloc[idx]
            sha_range = sha_trend_df['High'].iloc[idx] - sha_trend_df['Low'].iloc[idx]
            if sha_diff != sha_diff or sha_range != sha_range:
                trend_power_list.append(0)
                continue
            if sha_range != 0 and (sha_diff / sha_range) >= self.sha_threshold:
                trend_power_list.append(1)
            else:
                trend_power_list.append(0)
        return trend_power_list
    
    def calculate_signal(self, source_df, sha_df, sha_trend_df, gap_pct_series,
                         buy_positions, sell_positions, times, gap_range=None,
                         fibo_power=None, close_threshold=2, convergence=None,
                         rsi_value=None, rsi_mtf=None):
        """
        Calculate entry/exit signals based on SHA power
        
        Args:
            source_df: Raw OHLC DataFrame (capitalized columns: Open, High, Low, Close)
            sha_df: SHA signal indicator DataFrame (Open, High, Low, Close)
            sha_trend_df: SHA trend indicator DataFrame (Open, High, Low, Close)
            gap_pct_series: pd.Series of gap% between signal and trend SHA
            buy_positions: Dict from get_buy_positions() or None
            sell_positions: Dict from get_sell_positions() or None
            times: Hedge/multiplier from symbols config
            gap_range: [min, max] gap% range for this symbol (default from constants)
            fibo_power: Exponent for fibo DCA threshold (default from constants, per-symbol override)
            rsi_value: Current RSI value (float 0-100) for DCA entry decisions
            rsi_mtf: Dict of {timeframe_name: rsi_value} for multi-timeframe entry filter
        
        Returns:
            tuple: (buy_signal, sell_signal, analysis_data)
                - buy_signal: Signal enum
                - sell_signal: Signal enum
                - analysis_data: dict with sha/trend power, gap% data
        """
        # Use local variable instead of self.hedge for thread-safety
        hedge = times
        
        # Extract position data
        buy_count = buy_positions['count'] if buy_positions else 0
        buy_profit = buy_positions['total_profit'] if buy_positions else 0
        buy_first_profit = buy_positions['first_profit'] if buy_positions else 0
        sell_count = sell_positions['count'] if sell_positions else 0
        sell_profit = sell_positions['total_profit'] if sell_positions else 0
        sell_first_profit = sell_positions['first_profit'] if sell_positions else 0
        
        # Analyze candles
        lt_sha_power_list, ct_power_list = self._analyze(source_df, sha_df)
        
        # Calculate strengths
        lt_buy_power = sum(1 for x in lt_sha_power_list if x == 1)
        lt_sell_power = sum(1 for x in lt_sha_power_list if x == 0)
        ct_buy_power = sum(1 for x in ct_power_list if x == 1)
        ct_sell_power = sum(1 for x in ct_power_list if x == 0)
        
        # Analyze trend SHA
        lt_trend_power_list = self._analyze_trend(sha_trend_df)
        lt_trend_buy_power = sum(1 for x in lt_trend_power_list if x == 1)
        lt_trend_sell_power = sum(1 for x in lt_trend_power_list if x == 0)
        
        # Current candle gap%
        current_gap_pct = 0.0
        if len(gap_pct_series) > 0:
            try:
                gap_value = float(gap_pct_series.iloc[-1])
                if gap_value == gap_value:  # not NaN
                    current_gap_pct = round(gap_value, 4)
            except (TypeError, ValueError):
                current_gap_pct = 0.0
        
        # Gap range
        if gap_range is None:
            gap_range = DEFAULT_GAP_RANGE
        
        # Fibo power
        if fibo_power is None:
            fibo_power = FIBO_POWER_DEFAULT
        
        # RSI value
        current_rsi = rsi_value if rsi_value is not None else 50.0

        # Convergence state
        if convergence is None:
            convergence = {'state': 'UNKNOWN', 'gap_now': 0.0, 'gap_prev': 0.0, 'gap_delta': 0.0}
        conv_state = convergence.get('state', 'UNKNOWN')

        buy_status = Signal.DO_NOTHING
        sell_status = Signal.DO_NOTHING

        if not lt_sha_power_list or not lt_trend_power_list:
            analysis_data = {
                'sha_power_list': lt_sha_power_list,
                'price_power_list': ct_power_list,
                'sha_buy_strength': lt_buy_power,
                'sha_sell_strength': lt_sell_power,
                'price_buy_strength': ct_buy_power,
                'price_sell_strength': ct_sell_power,
                'sha_trend_power_list': lt_trend_power_list,
                'sha_trend_buy_strength': lt_trend_buy_power,
                'sha_trend_sell_strength': lt_trend_sell_power,
                'current_gap_pct': current_gap_pct,
                'gap_range': gap_range,
                'convergence': convergence,
                'rsi_value': round(current_rsi, 2),
                'rsi_mtf': rsi_mtf or {},
                'rsi_mtf_blocked': False,
                'lookback_used': min(len(lt_sha_power_list), len(lt_trend_power_list)),
            }
            return buy_status, sell_status, analysis_data
        
        # ─── Entry/Exit Logic ───
        
        gap_in_range = gap_range[0] <= current_gap_pct <= gap_range[1]
        below_gap = current_gap_pct < gap_range[0]
        entry_conv_ok = conv_state in ('DIVERGING', 'PARALLEL')
        exit_conv_ok = conv_state == 'CONVERGING'
        
        # Multi-timeframe RSI entry filter:
        # Block BUY if ANY timeframe RSI shows oversold (price likely still falling)
        # Block SELL if ANY timeframe RSI shows overbought (price likely still rising)
        rsi_any_oversold = False
        rsi_any_overbought = False
        if rsi_mtf and len(rsi_mtf) > 0:
            rsi_vals = list(rsi_mtf.values())
            rsi_any_oversold = any(v <= RSI_MTF_OVERSOLD for v in rsi_vals)
            rsi_any_overbought = any(v >= RSI_MTF_OVERBOUGHT for v in rsi_vals)
        rsi_mtf_blocked = rsi_any_oversold or rsi_any_overbought

        def _get_mtf_rsi(*timeframes, default=50.0):
            if not rsi_mtf:
                return default
            for timeframe in timeframes:
                if timeframe in rsi_mtf:
                    return rsi_mtf[timeframe]
            return default
        
        # Extract individual timeframe RSIs for tiered DCA
        rsi_1m = _get_mtf_rsi('TIMEFRAME_M1')
        rsi_5m = _get_mtf_rsi('TIMEFRAME_M5')
        rsi_15m = _get_mtf_rsi('TIMEFRAME_M15')
        
        # No positions open → look for entry (with MTF RSI filter)
        if buy_count == 0 and sell_count == 0:
            if not rsi_mtf_blocked:
                if lt_sha_power_list[0] == 1 and lt_trend_power_list[0] == 1 and gap_in_range and entry_conv_ok:
                    buy_status = Signal.BUY
                elif lt_sha_power_list[0] == 0 and lt_trend_power_list[0] == 0 and gap_in_range and entry_conv_ok:
                    sell_status = Signal.SELL
        
        # Only BUY positions open → exit or DCA (max 3 total: 1 entry + 1 via 1m RSI + 1 via 5m RSI, close via 15m RSI)
        elif buy_count > 0 and sell_count == 0:
            if buy_profit > close_threshold:
                buy_status = Signal.CLOSE_BUY
            elif rsi_1m <= RSI_OVERSOLD and buy_count == 1:
                buy_status = Signal.BUY_MORE
            elif rsi_5m <= RSI_OVERSOLD and buy_count == 2:
                buy_status = Signal.BUY_MORE
            elif rsi_15m <= RSI_OVERSOLD and buy_count == 3:
                buy_status = Signal.CLOSE_BUY

        # Only SELL positions open → exit or DCA (max 3 total: 1 entry + 1 via 1m RSI + 1 via 5m RSI, close via 15m RSI)
        elif buy_count == 0 and sell_count > 0:
            if sell_profit > close_threshold:
                sell_status = Signal.CLOSE_SELL
            elif rsi_1m >= RSI_OVERBOUGHT and sell_count == 1:
                sell_status = Signal.SELL_MORE
            elif rsi_5m >= RSI_OVERBOUGHT and sell_count == 2:
                sell_status = Signal.SELL_MORE
            elif rsi_15m >= RSI_OVERBOUGHT and sell_count == 3:
                sell_status = Signal.CLOSE_SELL
        
        analysis_data = {
            'sha_power_list': lt_sha_power_list,
            'price_power_list': ct_power_list,
            'sha_buy_strength': lt_buy_power,
            'sha_sell_strength': lt_sell_power,
            'price_buy_strength': ct_buy_power,
            'price_sell_strength': ct_sell_power,
            'sha_trend_power_list': lt_trend_power_list,
            'sha_trend_buy_strength': lt_trend_buy_power,
            'sha_trend_sell_strength': lt_trend_sell_power,
            'current_gap_pct': current_gap_pct,
            'gap_range': gap_range,
            'convergence': convergence,
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'rsi_mtf_blocked': rsi_mtf_blocked,
            'lookback_used': min(len(lt_sha_power_list), len(lt_trend_power_list)),
        }
        
        return buy_status, sell_status, analysis_data