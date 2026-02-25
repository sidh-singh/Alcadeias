from enum import Enum
from constants import (
    STRATEGY_HEDGE, STRATEGY_LOOKBACK, STRATEGY_SHA_THRESHOLD,
    FIBO_SEQUENCE_LENGTH, DEFAULT_GAP_RANGE, FIBO_POWER_DEFAULT,
    SHA_CONVERGENCE_LOOKBACK, SHA_CLOSE_THRESHOLD, SHA_CONVERGENCE_THRESHOLD,
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
    
    def _get_next_fibo_volume(self, position_count, times):
        """
        Get next fibonacci volume based on current position count.
        Uses count as index into fib sequence.
        
        Args:
            position_count: Current number of open positions (e.g., 1, 2, 3...)
            times: Multiplier from config
        
        Returns:
            float: Next fibo volume in lots
        """
        fib = [self._recur_fibo(i) for i in range(FIBO_SEQUENCE_LENGTH)][2:]
        try:
            return round(fib[position_count] * times / 100, 2)
        except IndexError:
            return 0.01 * times
    
    def _analyze(self, source_df, sha_df):
        """
        Analyze last N candles for SHA power and crossover
        
        Returns:
            tuple: (lt_sha_power_list, ct_power_list, crossover)
        """
        lt_sha_power_list = []
        ct_power_list = []
        crossover = []

        max_lookback = min(self.lookback, len(source_df), len(sha_df))
        if max_lookback <= 0:
            return lt_sha_power_list, ct_power_list, crossover
        
        for i in range(max_lookback):
            idx = -(i + 1)
            
            # SHA candle
            sha_diff = sha_df['Close'].iloc[idx] - sha_df['Open'].iloc[idx]
            sha_range = sha_df['High'].iloc[idx] - sha_df['Low'].iloc[idx]
            
            # Price candle
            price_diff = source_df['Close'].iloc[idx] - source_df['Open'].iloc[idx]
            price_range = source_df['High'].iloc[idx] - source_df['Low'].iloc[idx]
            
            # SHA power (bullish or bearish)
            sha_bullish = False
            if sha_range != 0 and (sha_diff / sha_range) >= self.sha_threshold:
                lt_sha_power_list.append(1)
                sha_bullish = True
            else:
                lt_sha_power_list.append(0)
            
            # Price power
            if price_range != 0 and (price_diff / price_range) >= self.sha_threshold:
                ct_power_list.append(1)
            else:
                ct_power_list.append(0)
            
            # Crossover: price candle position relative to SHA candle
            p_low = source_df['Low'].iloc[idx]
            p_high = source_df['High'].iloc[idx]
            s_low = sha_df['Low'].iloc[idx]
            s_high = sha_df['High'].iloc[idx]

            values = [sha_diff, sha_range, price_diff, price_range, p_low, p_high, s_low, s_high]
            if any(v != v for v in values):
                lt_sha_power_list.append(0)
                ct_power_list.append(0)
                crossover.append(0)
                continue
            
            if sha_bullish:
                if p_low >= s_high:
                    crossover.append(3)    # Price fully above SHA → strong bull
                elif p_high <= s_low:
                    crossover.append(1)    # Price fully below SHA → weak
                else:
                    crossover.append(2)    # Overlapping
            else:
                if p_high <= s_low:
                    crossover.append(-3)   # Price fully below SHA → strong bear
                elif p_low >= s_high:
                    crossover.append(-1)   # Price fully above SHA → weak
                else:
                    crossover.append(-2)   # Overlapping
        
        return lt_sha_power_list, ct_power_list, crossover
    
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
                         fibo_power=None, close_threshold=2, convergence=None):
        """
        Calculate entry/exit signals based on SHA power and crossover
        
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
        
        Returns:
            tuple: (buy_signal, sell_signal, analysis_data)
                - buy_signal: Signal enum
                - sell_signal: Signal enum
                - analysis_data: dict with sha/trend power, crossover, gap% data
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
        lt_sha_power_list, ct_power_list, crossover = self._analyze(source_df, sha_df)
        
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
                'crossover': crossover,
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
                'lookback_used': min(len(lt_sha_power_list), len(lt_trend_power_list)),
            }
            return buy_status, sell_status, analysis_data
        
        # ─── Entry/Exit Logic ───
        
        gap_in_range = gap_range[0] <= current_gap_pct <= gap_range[1]
        below_gap = current_gap_pct < gap_range[0]
        entry_conv_ok = conv_state in ('DIVERGING', 'PARALLEL')
        exit_conv_ok = conv_state == 'CONVERGING'
        
        # No positions open → look for entry
        # Requires: signal+trend agree, gap in range, and convergence is DIVERGING or PARALLEL
        if buy_count == 0 and sell_count == 0:
            if lt_sha_power_list[0] == 1 and lt_trend_power_list[0] == 1 and gap_in_range and entry_conv_ok:
                buy_status = Signal.BUY
            elif lt_sha_power_list[0] == 0 and lt_trend_power_list[0] == 0 and gap_in_range and entry_conv_ok:
                sell_status = Signal.SELL
        
        # Only BUY positions open → exit when trend SHA flips bearish
        elif buy_count > 0 and sell_count == 0:
            if buy_profit > close_threshold:
                buy_status = Signal.CLOSE_BUY
            elif (buy_first_profit < -50) or exit_conv_ok:
                buy_status = Signal.CLOSE_BUY
            elif buy_first_profit < -(self._get_fibo_qty(buy_count, 1) ** fibo_power):
                buy_status = Signal.BUY_MORE
        
        # Only SELL positions open → exit when trend SHA flips bullish
        elif buy_count == 0 and sell_count > 0:
            if sell_profit > close_threshold:
                sell_status = Signal.CLOSE_SELL
            elif (sell_first_profit < -50) or exit_conv_ok:
                sell_status = Signal.CLOSE_SELL
            elif sell_first_profit < -(self._get_fibo_qty(sell_count, 1) ** fibo_power):
                sell_status = Signal.SELL_MORE
        
        analysis_data = {
            'sha_power_list': lt_sha_power_list,
            'price_power_list': ct_power_list,
            'crossover': crossover,
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
            'lookback_used': min(len(lt_sha_power_list), len(lt_trend_power_list)),
        }
        
        return buy_status, sell_status, analysis_data