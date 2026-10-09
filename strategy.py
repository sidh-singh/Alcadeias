from enum import Enum
from constants import (
    STRATEGY_HEDGE,
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
        Calculate entry/exit signals.

        RSI+MACD REBUILD. The old SHA / ADX-regime / RSI-MTF-filter / DCA-martingale /
        H6 logic was removed (Steps 2-4, 7). The flat-entry branch now runs the new
        RSI+MACD slope entry (Step 6, below). Still to be added: the open-basket slope
        exit (H1-flip profit-protect + H4 force-close, Phase 4) - the open branches are
        no-op placeholders until then.

        Args:
            source_df: Raw OHLC DataFrame (capitalized columns: Open, High, Low, Close)
            buy_positions: Dict from get_buy_positions() or None
            sell_positions: Dict from get_sell_positions() or None
            times: Effective unit (min(times, max_limit) from symbols config).
            close_threshold: USD basket profit target (used by the exit, Phase 4).
            rsi_value: Current RSI value (float 0-100); retained for dashboard/logs.
            rsi_mtf: Dict of {timeframe_name: rsi_value}; retained for the dashboard.
            slopes: Dict {tf: {'rsi': <pivot-slope dict>, 'macd': <pivot-slope dict>}}
                   for H1/H4, from indicator.latest_pivot_slope. Drives the entry
                   direction (and, later, the exit).
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

        # ─── Entry/Exit Logic ───
        # Fresh-entry direction from the 4 H1/H4 slopes (Step 6). Computed always so
        # the dashboard can show it even when flat-entry is gated by the cooldown.
        slope_direction = self._slope_direction(slopes)

        if buy_count == 0 and sell_count == 0:
            # Fresh entry (single position; H4-primary / H1-confirm). Suppressed while
            # the post-close re-entry cooldown is active (entry_allowed=False).
            if entry_allowed and slope_direction == 'BUY':
                buy_status = Signal.BUY
            elif entry_allowed and slope_direction == 'SELL':
                sell_status = Signal.SELL
        elif buy_count > 0 and sell_count == 0:
            # Open BUY: slope profit-protect + force-close added in a later step (Phase 4).
            pass
        elif buy_count == 0 and sell_count > 0:
            # Open SELL: slope profit-protect + force-close added in a later step (Phase 4).
            pass

        analysis_data = {
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'slopes': slopes or {},
            'slope_direction': slope_direction or 'WAIT',
            'entry_allowed': bool(entry_allowed),
        }

        return buy_status, sell_status, analysis_data
