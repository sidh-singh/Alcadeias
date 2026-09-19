from enum import Enum
from constants import (
    STRATEGY_HEDGE, STRATEGY_LOOKBACK, STRATEGY_SHA_THRESHOLD,
    FIBO_SEQUENCE_LENGTH,
    RSI_OVERSOLD, RSI_OVERBOUGHT, RSI_DCA_MAX_POSITIONS,
    RSI_MTF_OVERSOLD, RSI_MTF_OVERBOUGHT,
    RSI_MTF_TIMEFRAMES, RSI_FINAL_CLOSE_TIMEFRAME,
    HTF_PROTECTION_ENABLED, HTF_CATASTROPHE_LOSS_PCT,
    HTF_MEDIUM_LOSS_PCT, HTF_PROTECT_MIN_COUNT,
    HTF_LADDER_CAP_ON_SPIKE, HTF_LADDER_CAP_MAX_COUNT,
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
        Get next fibonacci volume so each placed position is a fib value.

        Positions are opened as the fib sequence itself (0.01, 0.02, 0.03,
        0.05, 0.08, 0.13, ...). total_volume is the SUM of the fib positions
        already open, so we walk the cumulative sum to find how many positions
        are open and return the next fib value to place.

        Eg: fib = [0.01, 0.02, 0.03, 0.05, 0.08, 0.13, ...]
            total_volume 0.01 (1 pos)        → next 0.02
            total_volume 0.03 (0.01+0.02)    → next 0.03
            total_volume 0.06 (+0.03)        → next 0.05
            total_volume 0.11 (+0.05)        → next 0.08

        Args:
            total_volume: Total volume of all open positions for this direction
            times: Multiplier from config

        Returns:
            float: Next fibo volume in lots
        """
        fib = [self._recur_fibo(i) for i in range(FIBO_SEQUENCE_LENGTH)][2:]
        total_units = round(total_volume * 100 / times) if times else 0
        cumulative = 0
        for i, f in enumerate(fib):
            cumulative += f
            if cumulative >= total_units:
                try:
                    return round(fib[i + 1] * times / 100, 2)
                except IndexError:
                    return round(0.01 * times, 2)
        return round(0.01 * times, 2)
    
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
    
    def calculate_signal(self, source_df, sha_df, sha_trend_df,
                         buy_positions, sell_positions, times,
                         close_threshold=2,
                         rsi_value=None, rsi_mtf=None,
                         balance=None, spike=False):
        """
        Calculate entry/exit signals based on SHA power and crossover
        
        Args:
            source_df: Raw OHLC DataFrame (capitalized columns: Open, High, Low, Close)
            sha_df: SHA signal indicator DataFrame (Open, High, Low, Close)
            sha_trend_df: SHA trend indicator DataFrame (Open, High, Low, Close)
            buy_positions: Dict from get_buy_positions() or None
            sell_positions: Dict from get_sell_positions() or None
            times: Effective unit (min(times, max_limit) from symbols config).
                   Scales the Fibo lot ladder.
            close_threshold: USD basket profit target to close all trades. Derived
                   from the effective unit, so it always equals `times` (unit N → $N).
            rsi_value: Current RSI value (float 0-100) for DCA entry decisions
            rsi_mtf: Dict of {timeframe_name: rsi_value} for multi-timeframe entry filter
            balance: Live account balance (float). Used to size the %-of-balance
                   higher-timeframe protection stops. None/0 → those stops are
                   skipped and the strategy behaves exactly as before.
            spike: True when a fast adverse move (spike/slippage) is detected on
                   the protection timeframe for the currently-open basket. Gates
                   the ladder cap and the medium stop (see constants HTF_*).

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
        
        # RSI value
        current_rsi = rsi_value if rsi_value is not None else 50.0

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
                'rsi_value': round(current_rsi, 2),
                'rsi_mtf': rsi_mtf or {},
                'rsi_mtf_blocked': False,
                'lookback_used': min(len(lt_sha_power_list), len(lt_trend_power_list)),
            }
            return buy_status, sell_status, analysis_data
        
        # ─── Entry/Exit Logic ───

        # Multi-timeframe RSI entry filter:
        # Block BUY if ANY timeframe RSI shows oversold (price likely still falling)
        # Block SELL if ANY timeframe RSI shows overbought (price likely still rising)
        rsi_any_oversold = False
        rsi_any_overbought = False
        if rsi_mtf and len(rsi_mtf) > 0:
            # Only the configured entry-filter timeframes (RSI_MTF_TIMEFRAMES:
            # M1/M5/M15/M30) gate entries; the DCA-ladder timeframes (H1/H4) and
            # the final forced-close timeframe (H6) are intentionally excluded here.
            rsi_vals = [rsi_mtf[tf] for tf in RSI_MTF_TIMEFRAMES if tf in rsi_mtf]
            rsi_any_oversold = any(v <= RSI_MTF_OVERSOLD for v in rsi_vals)
            rsi_any_overbought = any(v >= RSI_MTF_OVERBOUGHT for v in rsi_vals)
        rsi_mtf_blocked = rsi_any_oversold or rsi_any_overbought
        
        # Extract individual timeframe RSIs for tiered DCA + final forced close
        rsi_1m = rsi_mtf.get('TIMEFRAME_M1', 50.0) if rsi_mtf else 50.0
        rsi_5m = rsi_mtf.get('TIMEFRAME_M5', 50.0) if rsi_mtf else 50.0
        rsi_15m = rsi_mtf.get('TIMEFRAME_M15', 50.0) if rsi_mtf else 50.0
        rsi_1h = rsi_mtf.get('TIMEFRAME_H1', 50.0) if rsi_mtf else 50.0
        rsi_4h = rsi_mtf.get('TIMEFRAME_H4', 50.0) if rsi_mtf else 50.0
        rsi_6h = rsi_mtf.get(RSI_FINAL_CLOSE_TIMEFRAME, 50.0) if rsi_mtf else 50.0
        
        # No positions open → look for entry (with MTF RSI filter)
        if buy_count == 0 and sell_count == 0:
            if not rsi_mtf_blocked:
                if lt_sha_power_list[0] == 1 and lt_trend_power_list[0] == 1:
                    buy_status = Signal.BUY
                elif lt_sha_power_list[0] == 0 and lt_trend_power_list[0] == 0:
                    sell_status = Signal.SELL
        
        # Only BUY positions open → exit or DCA (max 6 total: 1 entry + 1m + 5m + 15m + 1h + 4h RSI DCA; final forced close via 6h RSI)
        elif buy_count > 0 and sell_count == 0:
            # ── Higher-timeframe spike / drawdown protection ──
            # Strict priority chain (mutually exclusive, so no layer can cancel
            # another): catastrophe stop > profit close > spike medium stop >
            # DCA ladder (H4 add capped during a spike). Low tiers (counts 1-3)
            # are never affected.
            catastrophe_hit = (
                HTF_PROTECTION_ENABLED and HTF_CATASTROPHE_LOSS_PCT > 0
                and balance and balance > 0
                and buy_profit <= -(HTF_CATASTROPHE_LOSS_PCT * balance)
            )
            spike_medium_hit = (
                HTF_PROTECTION_ENABLED and spike
                and buy_count >= HTF_PROTECT_MIN_COUNT
                and balance and balance > 0
                and buy_profit <= -(HTF_MEDIUM_LOSS_PCT * balance)
            )
            ladder_capped = (
                HTF_PROTECTION_ENABLED and HTF_LADDER_CAP_ON_SPIKE and spike
                and buy_count >= HTF_LADDER_CAP_MAX_COUNT
            )

            if catastrophe_hit:
                buy_status = Signal.CLOSE_BUY
            elif buy_profit > close_threshold:
                buy_status = Signal.CLOSE_BUY
            elif spike_medium_hit:
                buy_status = Signal.CLOSE_BUY
            elif rsi_1m <= RSI_OVERSOLD and buy_count == 1:
                buy_status = Signal.BUY_MORE
            elif rsi_5m <= RSI_OVERSOLD and buy_count == 2:
                buy_status = Signal.BUY_MORE
            elif rsi_15m <= RSI_OVERSOLD and buy_count == 3:
                buy_status = Signal.BUY_MORE
            elif rsi_1h <= RSI_OVERSOLD and buy_count == 4:
                buy_status = Signal.BUY_MORE                       # H1 tier add (#5) — always allowed
            elif rsi_4h <= RSI_OVERSOLD and buy_count == 5 and not ladder_capped:
                buy_status = Signal.BUY_MORE                       # H4 tier add (#6) — blocked during spike
            elif rsi_6h <= RSI_OVERSOLD and buy_count == 6:
                buy_status = Signal.CLOSE_BUY

        # Only SELL positions open → exit or DCA (max 6 total: 1 entry + 1m + 5m + 15m + 1h + 4h RSI DCA; final forced close via 6h RSI)
        elif buy_count == 0 and sell_count > 0:
            # ── Higher-timeframe spike / drawdown protection (mirror of BUY) ──
            catastrophe_hit = (
                HTF_PROTECTION_ENABLED and HTF_CATASTROPHE_LOSS_PCT > 0
                and balance and balance > 0
                and sell_profit <= -(HTF_CATASTROPHE_LOSS_PCT * balance)
            )
            spike_medium_hit = (
                HTF_PROTECTION_ENABLED and spike
                and sell_count >= HTF_PROTECT_MIN_COUNT
                and balance and balance > 0
                and sell_profit <= -(HTF_MEDIUM_LOSS_PCT * balance)
            )
            ladder_capped = (
                HTF_PROTECTION_ENABLED and HTF_LADDER_CAP_ON_SPIKE and spike
                and sell_count >= HTF_LADDER_CAP_MAX_COUNT
            )

            if catastrophe_hit:
                sell_status = Signal.CLOSE_SELL
            elif sell_profit > close_threshold:
                sell_status = Signal.CLOSE_SELL
            elif spike_medium_hit:
                sell_status = Signal.CLOSE_SELL
            elif rsi_1m >= RSI_OVERBOUGHT and sell_count == 1:
                sell_status = Signal.SELL_MORE
            elif rsi_5m >= RSI_OVERBOUGHT and sell_count == 2:
                sell_status = Signal.SELL_MORE
            elif rsi_15m >= RSI_OVERBOUGHT and sell_count == 3:
                sell_status = Signal.SELL_MORE
            elif rsi_1h >= RSI_OVERBOUGHT and sell_count == 4:
                sell_status = Signal.SELL_MORE                     # H1 tier add (#5) — always allowed
            elif rsi_4h >= RSI_OVERBOUGHT and sell_count == 5 and not ladder_capped:
                sell_status = Signal.SELL_MORE                     # H4 tier add (#6) — blocked during spike
            elif rsi_6h >= RSI_OVERBOUGHT and sell_count == 6:
                sell_status = Signal.CLOSE_SELL
        
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
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'rsi_mtf_blocked': rsi_mtf_blocked,
            'htf_spike': bool(spike),
            'htf_protection_enabled': bool(HTF_PROTECTION_ENABLED),
            'lookback_used': min(len(lt_sha_power_list), len(lt_trend_power_list)),
        }

        return buy_status, sell_status, analysis_data