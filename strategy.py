from enum import Enum
from constants import (
    STRATEGY_HEDGE,
    FIBO_SEQUENCE_LENGTH,
    RSI_OVERSOLD, RSI_OVERBOUGHT, RSI_DCA_MAX_POSITIONS,
    RSI_MTF_OVERSOLD, RSI_MTF_OVERBOUGHT,
    RSI_MTF_TIMEFRAMES, RSI_FINAL_CLOSE_TIMEFRAME,
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
            total_volume 0.01 (1 pos)        -> next 0.02
            total_volume 0.03 (0.01+0.02)    -> next 0.03
            total_volume 0.06 (+0.03)        -> next 0.05
            total_volume 0.11 (+0.05)        -> next 0.08

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

    def calculate_signal(self, source_df,
                         buy_positions, sell_positions, times,
                         close_threshold=2,
                         rsi_value=None, rsi_mtf=None, regime=None):
        """
        Calculate entry/exit signals.

        NOTE: SHA direction logic has been REMOVED (Step 2 of the RSI+MACD
        rebuild). The fresh-entry branch is currently a no-op placeholder; the
        RSI+MACD slope entry engine is added in a later step. Open-basket
        management (DCA ladder, profit close, H6 forced close) is unchanged here
        and is revised in a later step.

        Args:
            source_df: Raw OHLC DataFrame (capitalized columns: Open, High, Low, Close)
            buy_positions: Dict from get_buy_positions() or None
            sell_positions: Dict from get_sell_positions() or None
            times: Effective unit (min(times, max_limit) from symbols config).
                   Scales the Fibo lot ladder.
            close_threshold: USD basket profit target to close all trades. Derived
                   from the effective unit, so it always equals `times` (unit N -> $N).
            rsi_value: Current RSI value (float 0-100) for DCA entry decisions
            rsi_mtf: Dict of {timeframe_name: rsi_value} for the MTF filter / DCA ladder
            regime: Optional dict from app._compute_regime() (kept inert here; removed
                   in a later step).

        Returns:
            tuple: (buy_signal, sell_signal, analysis_data)
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

        # RSI value
        current_rsi = rsi_value if rsi_value is not None else 50.0

        buy_status = Signal.DO_NOTHING
        sell_status = Signal.DO_NOTHING

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

        # Regime entry-filter bookkeeping (kept inert here; removed in a later step).
        _regime = regime or {}
        _block_buy = bool(_regime.get('block_buy', False))
        _block_sell = bool(_regime.get('block_sell', False))

        # No positions open -> look for entry.
        # SHA direction logic REMOVED (Step 2). The RSI+MACD slope entry engine is
        # added in a later step; until then no fresh entry is taken.
        if buy_count == 0 and sell_count == 0:
            pass

        # Only BUY positions open → exit or DCA (max 6 total: 1 entry + 1m + 5m + 15m + 1h + 4h RSI DCA; final forced close via 6h RSI)
        elif buy_count > 0 and sell_count == 0:
            if buy_profit > close_threshold:
                buy_status = Signal.CLOSE_BUY
            elif rsi_1m <= RSI_OVERSOLD and buy_count == 1:
                buy_status = Signal.BUY_MORE
            elif rsi_5m <= RSI_OVERSOLD and buy_count == 2:
                buy_status = Signal.BUY_MORE
            elif rsi_15m <= RSI_OVERSOLD and buy_count == 3:
                buy_status = Signal.BUY_MORE
            elif rsi_1h <= RSI_OVERSOLD and buy_count == 4:
                buy_status = Signal.BUY_MORE
            elif rsi_4h <= RSI_OVERSOLD and buy_count == 5:
                buy_status = Signal.BUY_MORE
            elif rsi_6h <= RSI_OVERSOLD and buy_count == 6:
                buy_status = Signal.CLOSE_BUY

        # Only SELL positions open → exit or DCA (max 6 total: 1 entry + 1m + 5m + 15m + 1h + 4h RSI DCA; final forced close via 6h RSI)
        elif buy_count == 0 and sell_count > 0:
            if sell_profit > close_threshold:
                sell_status = Signal.CLOSE_SELL
            elif rsi_1m >= RSI_OVERBOUGHT and sell_count == 1:
                sell_status = Signal.SELL_MORE
            elif rsi_5m >= RSI_OVERBOUGHT and sell_count == 2:
                sell_status = Signal.SELL_MORE
            elif rsi_15m >= RSI_OVERBOUGHT and sell_count == 3:
                sell_status = Signal.SELL_MORE
            elif rsi_1h >= RSI_OVERBOUGHT and sell_count == 4:
                sell_status = Signal.SELL_MORE
            elif rsi_4h >= RSI_OVERBOUGHT and sell_count == 5:
                sell_status = Signal.SELL_MORE
            elif rsi_6h >= RSI_OVERBOUGHT and sell_count == 6:
                sell_status = Signal.CLOSE_SELL

        # ── Regime filter annotation (kept inert here; removed in a later step) ──
        _flat = (buy_count == 0 and sell_count == 0)
        _would_fire_buy = False   # entry logic removed with SHA (Step 2)
        _would_fire_sell = False
        regime_out = dict(_regime)
        regime_out['would_fire_buy'] = bool(_would_fire_buy)
        regime_out['would_fire_sell'] = bool(_would_fire_sell)
        regime_out['blocked_buy'] = bool(_would_fire_buy and _block_buy)
        regime_out['blocked_sell'] = bool(_would_fire_sell and _block_sell)
        regime_out['shadow_would_block_buy'] = bool(_would_fire_buy and _regime.get('would_block_buy', False))
        regime_out['shadow_would_block_sell'] = bool(_would_fire_sell and _regime.get('would_block_sell', False))

        analysis_data = {
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'rsi_mtf_blocked': rsi_mtf_blocked,
            'regime': regime_out,
        }

        return buy_status, sell_status, analysis_data
