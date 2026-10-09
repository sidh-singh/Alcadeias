from enum import Enum
from constants import (
    STRATEGY_HEDGE,
    PROFIT_PROTECT_MIN_USD,
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
    """RSI+MACD slope strategy - single-position entry/exit on H1/H4 pivot slopes."""

    def __init__(self):
        self.hedge = STRATEGY_HEDGE

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

        if h4r > 0 and h4m > 0:                 # H4 aligned up
            return 'BUY' if (h1r > 0 or h1m > 0) else None
        if h4r < 0 and h4m < 0:                 # H4 aligned down
            return 'SELL' if (h1r < 0 or h1m < 0) else None
        if (h4r > 0 and h4m < 0) or (h4r < 0 and h4m > 0):   # H4 split -> defer to H1
            if h1r > 0 and h1m > 0:
                return 'BUY'
            if h1r < 0 and h1m < 0:
                return 'SELL'
            return None
        return None                             # a zero/undefined H4 slope -> WAIT

    def calculate_signal(self, source_df,
                         buy_positions, sell_positions, times,
                         close_threshold=2,
                         rsi_value=None, rsi_mtf=None, slopes=None,
                         entry_allowed=True):
        """
        RSI+MACD slope strategy - fresh-entry direction and open-basket exit from the
        four H1/H4 pivot slopes. Single position (no martingale).

          Flat (Step 6): H4-primary / H1-confirm -> BUY / SELL / WAIT.
          Open (Step 7, option C), checked in order:
            1. profit-protect - basket profit > cost buffer (PROFIT_PROTECT_MIN_USD)
               AND BOTH H1 slopes have flipped against the position -> CLOSE.
            2. hard stop      - H4 both slopes flipped against AND (either H1 against)
               -> CLOSE (accept the loss).
            3. else HOLD.

        Args:
            source_df: Raw OHLC DataFrame (capitalized columns: Open, High, Low, Close)
            buy_positions: Dict from get_buy_positions() or None
            sell_positions: Dict from get_sell_positions() or None
            times: Effective unit (min(times, max_limit) from symbols config).
            close_threshold: Legacy param, unused (the fixed +$unit target was removed).
            rsi_value: Current RSI value (float 0-100); retained for dashboard/logs.
            rsi_mtf: Dict of {timeframe_name: rsi_value}; retained for the dashboard.
            slopes: Dict {tf: {'rsi': <pivot-slope dict>, 'macd': <pivot-slope dict>}}
                   for H1/H4, from indicator.latest_pivot_slope. Drives entry and exit.
            entry_allowed: False while the post-close re-entry cooldown is active
                   (app-side); suppresses a fresh entry even if the slopes agree.

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

        # ─── Slope signs (H1/H4 RSI & MACD) + fresh-entry direction ───
        h4r = self._slope_sign(slopes, 'H4', 'rsi')
        h4m = self._slope_sign(slopes, 'H4', 'macd')
        h1r = self._slope_sign(slopes, 'H1', 'rsi')
        h1m = self._slope_sign(slopes, 'H1', 'macd')
        slope_direction = self._slope_direction(slopes)

        if buy_count == 0 and sell_count == 0:
            # Fresh entry (single position; H4-primary / H1-confirm), gated by cooldown.
            if entry_allowed and slope_direction == 'BUY':
                buy_status = Signal.BUY
            elif entry_allowed and slope_direction == 'SELL':
                sell_status = Signal.SELL

        elif buy_count > 0 and sell_count == 0:
            # Open BUY exit (Step 7 C) - the threat to a long is a DOWN move.
            if buy_profit > PROFIT_PROTECT_MIN_USD and h1r < 0 and h1m < 0:
                buy_status = Signal.CLOSE_BUY          # profit-protect (both H1 flipped down)
                exit_reason = 'profit_protect'
            elif h4r < 0 and h4m < 0 and (h1r < 0 or h1m < 0):
                buy_status = Signal.CLOSE_BUY          # hard stop (H4 flipped down + H1 confirm)
                exit_reason = 'force_close'

        elif buy_count == 0 and sell_count > 0:
            # Open SELL exit (mirror) - the threat to a short is an UP move.
            if sell_profit > PROFIT_PROTECT_MIN_USD and h1r > 0 and h1m > 0:
                sell_status = Signal.CLOSE_SELL        # profit-protect (both H1 flipped up)
                exit_reason = 'profit_protect'
            elif h4r > 0 and h4m > 0 and (h1r > 0 or h1m > 0):
                sell_status = Signal.CLOSE_SELL        # hard stop (H4 flipped up + H1 confirm)
                exit_reason = 'force_close'

        analysis_data = {
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'slopes': slopes or {},
            'slope_direction': slope_direction or 'WAIT',
            'entry_allowed': bool(entry_allowed),
            'exit_reason': exit_reason,
        }

        return buy_status, sell_status, analysis_data
