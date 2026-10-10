from enum import Enum
from constants import (
    STRATEGY_HEDGE,
    FIBO_SEQUENCE_LENGTH,
    RSI_OVERSOLD, RSI_OVERBOUGHT, RSI_FINAL_CLOSE_TIMEFRAME,
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
    """RSI+MACD slope entry + RSI Fibo DCA ladder with +$unit / H6 exits (variant B)."""

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
        Next fibonacci volume so each placed position is a fib value.

        Positions are opened as the fib sequence itself (0.01, 0.02, 0.03,
        0.05, 0.08, 0.13, ...). total_volume is the SUM of the fib positions
        already open, so we walk the cumulative sum to find how many positions
        are open and return the next fib value to place.

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

    @staticmethod
    def _slope_sign(slopes, tf, ind):
        """Slope sign (+1/-1/0) for (timeframe, indicator); 0 if missing/undefined."""
        try:
            s = slopes[tf][ind]['sign']
        except (KeyError, TypeError, IndexError):
            return 0
        return s if s in (-1, 0, 1) else 0

    def _slope_direction(self, slopes):
        """
        Fresh-entry direction from the four H1/H4 slope signs (Step 6, locked).

        H4 is primary, H1 confirms. Returns 'BUY', 'SELL', or None (WAIT). Any
        missing / zero / undefined slope counts as "no direction".

          - H4 both +ve & (>=1 H1 +ve)  -> BUY   ; both H1 -ve/0 -> WAIT
          - H4 both -ve & (>=1 H1 -ve)  -> SELL  ; both H1 +ve/0 -> WAIT
          - H4 split    & H1 both +ve   -> BUY
          - H4 split    & H1 both -ve   -> SELL  ; H1 mixed/zero -> WAIT
          - H4 has a zero slope         -> WAIT
        """
        slopes = slopes or {}
        h4r = self._slope_sign(slopes, 'H4', 'rsi')
        h4m = self._slope_sign(slopes, 'H4', 'macd')
        h1r = self._slope_sign(slopes, 'H1', 'rsi')
        h1m = self._slope_sign(slopes, 'H1', 'macd')

        if h4r > 0 and h4m > 0:
            return 'BUY' if (h1r > 0 or h1m > 0) else None
        if h4r < 0 and h4m < 0:
            return 'SELL' if (h1r < 0 or h1m < 0) else None
        if (h4r > 0 and h4m < 0) or (h4r < 0 and h4m > 0):
            if h1r > 0 and h1m > 0:
                return 'BUY'
            if h1r < 0 and h1m < 0:
                return 'SELL'
            return None
        return None

    def calculate_signal(self, source_df,
                         buy_positions, sell_positions, times,
                         close_threshold=2,
                         rsi_value=None, rsi_mtf=None, slopes=None,
                         entry_allowed=True):
        """
        RSI+MACD slope entry + RSI Fibo ladder, with the classic +$unit / H6 exits
        (variant B). No slope-based exits.

          Flat  (Step 6): H4-primary / H1-confirm slope direction -> BUY / SELL / WAIT.
                          Opens a single position; gated by the re-entry cooldown.
          Open  (checked in order):
            - +$unit target: basket profit > close_threshold (= unit) -> CLOSE.
            - RSI DCA ladder: BUY_MORE/SELL_MORE at RSI 35/65, one tier per count
              (1->M1, 2->M5, 3->M15, 4->H1, 5->H4), Fibo lot sizing.
            - H6 forced close: at count 6, RSI_FINAL_CLOSE_TIMEFRAME (H6) RSI extreme
              -> CLOSE.
            - else HOLD.

        Args:
            source_df: Raw OHLC DataFrame (capitalized: Open, High, Low, Close)
            buy_positions / sell_positions: dicts from get_*_positions() or None
            times: effective unit; scales the Fibo lot ladder.
            close_threshold: USD basket profit target (= unit) for the +$unit close.
            rsi_value: current RSI (dashboard/logs).
            rsi_mtf: {timeframe_name: rsi_value} - drives the DCA ladder + H6 close.
            slopes: {tf: {'rsi': ..., 'macd': ...}} for H1/H4 - drives entry direction.
            entry_allowed: False during the post-close re-entry cooldown.

        Returns:
            tuple: (buy_signal, sell_signal, analysis_data)
        """
        # Extract position data
        buy_count = buy_positions['count'] if buy_positions else 0
        buy_profit = buy_positions['total_profit'] if buy_positions else 0
        buy_first_profit = buy_positions['first_profit'] if buy_positions else 0
        sell_count = sell_positions['count'] if sell_positions else 0
        sell_profit = sell_positions['total_profit'] if sell_positions else 0
        sell_first_profit = sell_positions['first_profit'] if sell_positions else 0

        current_rsi = rsi_value if rsi_value is not None else 50.0

        buy_status = Signal.DO_NOTHING
        sell_status = Signal.DO_NOTHING
        exit_reason = None

        # Per-timeframe RSI for the DCA ladder tiers (1->M1 ... 5->H4) + H6 final close
        rsi_1m = rsi_mtf.get('TIMEFRAME_M1', 50.0) if rsi_mtf else 50.0
        rsi_5m = rsi_mtf.get('TIMEFRAME_M5', 50.0) if rsi_mtf else 50.0
        rsi_15m = rsi_mtf.get('TIMEFRAME_M15', 50.0) if rsi_mtf else 50.0
        rsi_1h = rsi_mtf.get('TIMEFRAME_H1', 50.0) if rsi_mtf else 50.0
        rsi_4h = rsi_mtf.get('TIMEFRAME_H4', 50.0) if rsi_mtf else 50.0
        rsi_6h = rsi_mtf.get(RSI_FINAL_CLOSE_TIMEFRAME, 50.0) if rsi_mtf else 50.0

        # Fresh-entry direction from the H1/H4 slopes (entry only)
        slope_direction = self._slope_direction(slopes)

        if buy_count == 0 and sell_count == 0:
            # Fresh entry (single position; H4-primary / H1-confirm), cooldown-gated.
            if entry_allowed and slope_direction == 'BUY':
                buy_status = Signal.BUY
            elif entry_allowed and slope_direction == 'SELL':
                sell_status = Signal.SELL

        elif buy_count > 0 and sell_count == 0:
            # Open BUY: +$unit target, RSI DCA ladder, then H6 forced close (max 6).
            if buy_profit > close_threshold:
                buy_status = Signal.CLOSE_BUY
                exit_reason = 'target'
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
                exit_reason = 'h6_forced'

        elif buy_count == 0 and sell_count > 0:
            # Open SELL (mirror): +$unit target, RSI DCA ladder, then H6 forced close.
            if sell_profit > close_threshold:
                sell_status = Signal.CLOSE_SELL
                exit_reason = 'target'
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
                exit_reason = 'h6_forced'

        analysis_data = {
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'slopes': slopes or {},
            'slope_direction': slope_direction or 'WAIT',
            'entry_allowed': bool(entry_allowed),
            'exit_reason': exit_reason,
        }

        return buy_status, sell_status, analysis_data
