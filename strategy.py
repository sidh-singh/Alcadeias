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

    def calculate_signal(self, source_df,
                         buy_positions, sell_positions, times,
                         close_threshold=2,
                         rsi_value=None, rsi_mtf=None):
        """
        Calculate entry/exit signals.

        TEARDOWN STATE (RSI+MACD rebuild). The old direction + management logic has
        been removed in stages: SHA entry (Step 2), ADX regime (Step 3), and now the
        RSI MTF entry filter, the DCA martingale ladder, the H6 forced close and the
        fixed +$unit profit target (Steps 4 + 7). Both the flat-entry branch and the
        open-basket branches are no-op placeholders.

        Still to be added (later steps):
          - flat  → RSI+MACD slope entry engine (H4-primary / H1-confirm).
          - open  → slope-based exit (H1-flip profit-protect + H4 force-close).

        Args:
            source_df: Raw OHLC DataFrame (capitalized columns: Open, High, Low, Close)
            buy_positions: Dict from get_buy_positions() or None
            sell_positions: Dict from get_sell_positions() or None
            times: Effective unit (min(times, max_limit) from symbols config).
            close_threshold: USD basket profit target (unused in this teardown state).
            rsi_value: Current RSI value (float 0-100); retained for dashboard/logs.
            rsi_mtf: Dict of {timeframe_name: rsi_value}; retained for the dashboard.

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

        # ─── Entry/Exit Logic (REBUILD IN PROGRESS — placeholders) ───
        if buy_count == 0 and sell_count == 0:
            # Fresh entry: RSI+MACD slope engine is added in a later step (Phase 3).
            pass
        elif buy_count > 0 and sell_count == 0:
            # Open BUY: slope profit-protect + force-close added in a later step (Phase 4).
            pass
        elif buy_count == 0 and sell_count > 0:
            # Open SELL: slope profit-protect + force-close added in a later step (Phase 4).
            pass

        analysis_data = {
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
        }

        return buy_status, sell_status, analysis_data
