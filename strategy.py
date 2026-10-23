from enum import Enum
from constants import (
    STRATEGY_HEDGE,
    FIBO_SEQUENCE_LENGTH,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
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
    """RSI+MACD slope entry + RSI Fibo DCA ladder; +$unit target or slope force-close (variant B)."""

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
        Fresh-entry direction from the 4H / 1H / 15M latest-pivot slope signs.

        4H primary, 1H confirm, 15M trigger (D1 removed on this "_wd" / without-daily
        branch - no daily side-gate). 15M is the finest tier: an entry fires only when
        >=1 of its two signs also agrees with the trade direction.
          H4 both +ve & (>=1 H1 +ve) & (>=1 M15 +ve)  -> BUY
          H4 both -ve & (>=1 H1 -ve) & (>=1 M15 -ve)  -> SELL
          H4 split    & H1 both +ve  & (>=1 M15 +ve)  -> BUY
          H4 split    & H1 both -ve  & (>=1 M15 -ve)  -> SELL
          else                                        -> WAIT

        Returns 'BUY', 'SELL', or None (WAIT). Missing / zero slope = "no direction".
        """
        slopes = slopes or {}
        h4r = self._slope_sign(slopes, 'H4', 'rsi')
        h4m = self._slope_sign(slopes, 'H4', 'macd')
        h1r = self._slope_sign(slopes, 'H1', 'rsi')
        h1m = self._slope_sign(slopes, 'H1', 'macd')
        m15r = self._slope_sign(slopes, 'M15', 'rsi')
        m15m = self._slope_sign(slopes, 'M15', 'macd')

        m15_up = (m15r > 0 or m15m > 0)   # >=1 M15 sign up (the entry trigger)
        m15_dn = (m15r < 0 or m15m < 0)   # >=1 M15 sign down

        if h4r > 0 and h4m > 0:
            return 'BUY' if ((h1r > 0 or h1m > 0) and m15_up) else None
        if h4r < 0 and h4m < 0:
            return 'SELL' if ((h1r < 0 or h1m < 0) and m15_dn) else None
        if (h4r > 0 and h4m < 0) or (h4r < 0 and h4m > 0):
            if h1r > 0 and h1m > 0 and m15_up:
                return 'BUY'
            if h1r < 0 and h1m < 0 and m15_dn:
                return 'SELL'
            return None
        return None

    def calculate_signal(self, source_df,
                         buy_positions, sell_positions, times,
                         close_threshold=2,
                         rsi_value=None, rsi_mtf=None, slopes=None,
                         entry_allowed=True):
        """
        RSI+MACD slope entry + RSI Fibo ladder; exits are the +$unit target or the
        slope force-close (variant B; the old H6 forced close was replaced).

          Flat  (Step 6): 4H-primary / 1H-confirm / 15M-trigger slope direction ->
                          BUY / SELL / WAIT. Opens a single position; cooldown-gated.
          Open  (checked in order; closing has priority over adding):
            - +$unit target: basket profit > close_threshold (= unit) -> CLOSE.
            - slope force-close (D1-regime): D1 AGAINST -> SENSITIVE (M15 both AND >=1 H1,
              'force_close_fast'); D1 with/flat -> NORMAL (>=1 H4 AND H1 both AND M15 both,
              'force_close'); D1 SPLIT -> cascade 4H->H1->floor ('fc_split_*'). See
              docs/h4h1m15-decision-table.md.
            - RSI DCA ladder: BUY_MORE/SELL_MORE at RSI 35/65, one tier per count
              (1->M1, 2->M5, 3->M15, 4->H1, 5->H4), Fibo lot sizing.
            - else HOLD.

        Args:
            source_df: Raw OHLC DataFrame (capitalized: Open, High, Low, Close)
            buy_positions / sell_positions: dicts from get_*_positions() or None
            times: effective unit; scales the Fibo lot ladder.
            close_threshold: USD basket profit target (= unit) for the +$unit close.
            rsi_value: current RSI (dashboard/logs).
            rsi_mtf: {timeframe_name: rsi_value} - drives the DCA ladder tiers.
            slopes: {tf: {'rsi': ..., 'macd': ...}} for 15M/H1/H4 (entry+exit) + D1 (exit-regime only).
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

        # Per-timeframe RSI for the DCA ladder tiers (1->M1 ... 5->H4)
        rsi_1m = rsi_mtf.get('TIMEFRAME_M1', 50.0) if rsi_mtf else 50.0
        rsi_5m = rsi_mtf.get('TIMEFRAME_M5', 50.0) if rsi_mtf else 50.0
        rsi_15m = rsi_mtf.get('TIMEFRAME_M15', 50.0) if rsi_mtf else 50.0
        rsi_1h = rsi_mtf.get('TIMEFRAME_H1', 50.0) if rsi_mtf else 50.0
        rsi_4h = rsi_mtf.get('TIMEFRAME_H4', 50.0) if rsi_mtf else 50.0

        # Slope signs (15M/H1/H4 for entry + force-close; D1 is EXIT-only regime)
        h4r = self._slope_sign(slopes, 'H4', 'rsi')
        h4m = self._slope_sign(slopes, 'H4', 'macd')
        h1r = self._slope_sign(slopes, 'H1', 'rsi')
        h1m = self._slope_sign(slopes, 'H1', 'macd')
        m15r = self._slope_sign(slopes, 'M15', 'rsi')
        m15m = self._slope_sign(slopes, 'M15', 'macd')
        d1r = self._slope_sign(slopes, 'D1', 'rsi')
        d1m = self._slope_sign(slopes, 'D1', 'macd')
        slope_direction = self._slope_direction(slopes)   # entry: 4H/1H/15M only (D1 excluded)

        # Weighted MTF slope score (SHADOW — telemetry/dashboard only; NO decision reads it yet).
        # S = 4*D1 + 3*H4 + 2*H1 + 1*M15, each TF = its RSI + MACD slope signs; range -20..+20
        # (negative = bearish). Step 1 of the weighted-score + regime redesign; see
        # docs/weighted-regime-redesign.md. Higher TF dominates; one noisy sign moves S by <=1.
        slope_score = (4 * (d1r + d1m) + 3 * (h4r + h4m)
                       + 2 * (h1r + h1m) + 1 * (m15r + m15m))

        # D1-regime-aware force-close (EXIT only). Three D1 regimes vs the open basket (for a
        # long: up=supportive, down=against, split=RSI/MACD disagree, flat=a 0):
        #   * D1 AGAINST (both oppose)   -> SENSITIVE: 15M both + >=1 H1 against ('force_close_fast').
        #   * D1 WITH (both support)/FLAT -> NORMAL:   >=1 4H + 1H both + 15M both ('force_close').
        #   * D1 SPLIT -> cascade 4H -> H1 -> floor. First decisive TF sets the band; a supportive
        #     verdict is +1 stricter (wait), descending deeper = more sensitive (less higher-TF
        #     backing). Ladder: C3 = H1 RSI + 15M both; C2 = 15M both; C1 = 15M RSI (floor).
        # Precomputed so the target / profit-protect / DCA ladder chain stays unchanged.
        m15_both_dn = (m15r < 0 and m15m < 0)
        if d1r < 0 and d1m < 0:                                 # D1 against the long -> sensitive
            buy_fc, buy_fc_reason = (m15_both_dn and (h1r < 0 or h1m < 0)), 'force_close_fast'
        elif (d1r < 0 and d1m > 0) or (d1r > 0 and d1m < 0):    # D1 SPLIT -> cascade 4H->H1->floor
            if h4r > 0 and h4m > 0:                             # 4H supportive -> wait (C3)
                buy_fc, buy_fc_reason = ((h1r < 0) and m15_both_dn), 'fc_split_4h_sup'
            elif h4r < 0 and h4m < 0:                           # 4H against (C2)
                buy_fc, buy_fc_reason = m15_both_dn, 'fc_split_4h_opp'
            elif h1r > 0 and h1m > 0:                           # 4H indecisive, H1 supportive (C2)
                buy_fc, buy_fc_reason = m15_both_dn, 'fc_split_h1_sup'
            elif h1r < 0 and h1m < 0:                           # 4H indecisive, H1 against (C1)
                buy_fc, buy_fc_reason = (m15r < 0), 'fc_split_h1_opp'
            else:                                               # 4H & H1 indecisive -> floor (C1)
                buy_fc, buy_fc_reason = (m15r < 0), 'fc_split_floor'
        else:                                                   # D1 with-trend or flat -> normal
            buy_fc = (h4r < 0 or h4m < 0) and h1r < 0 and h1m < 0 and m15_both_dn
            buy_fc_reason = 'force_close'

        m15_both_up = (m15r > 0 and m15m > 0)
        if d1r > 0 and d1m > 0:                                 # D1 against the short -> sensitive
            sell_fc, sell_fc_reason = (m15_both_up and (h1r > 0 or h1m > 0)), 'force_close_fast'
        elif (d1r < 0 and d1m > 0) or (d1r > 0 and d1m < 0):    # D1 SPLIT -> cascade (mirror)
            if h4r < 0 and h4m < 0:                             # 4H supportive -> wait (C3)
                sell_fc, sell_fc_reason = ((h1r > 0) and m15_both_up), 'fc_split_4h_sup'
            elif h4r > 0 and h4m > 0:                           # 4H against (C2)
                sell_fc, sell_fc_reason = m15_both_up, 'fc_split_4h_opp'
            elif h1r < 0 and h1m < 0:                           # 4H indecisive, H1 supportive (C2)
                sell_fc, sell_fc_reason = m15_both_up, 'fc_split_h1_sup'
            elif h1r > 0 and h1m > 0:                           # 4H indecisive, H1 against (C1)
                sell_fc, sell_fc_reason = (m15r > 0), 'fc_split_h1_opp'
            else:                                               # 4H & H1 indecisive -> floor (C1)
                sell_fc, sell_fc_reason = (m15r > 0), 'fc_split_floor'
        else:                                                   # D1 with-trend or flat -> normal
            sell_fc = (h4r > 0 or h4m > 0) and h1r > 0 and h1m > 0 and m15_both_up
            sell_fc_reason = 'force_close'

        if buy_count == 0 and sell_count == 0:
            # Fresh entry (single position; 4H-primary / 1H-confirm / 15M-trigger), cooldown-gated.
            if entry_allowed and slope_direction == 'BUY':
                buy_status = Signal.BUY
            elif entry_allowed and slope_direction == 'SELL':
                sell_status = Signal.SELL

        elif buy_count > 0 and sell_count == 0:
            # Open BUY: close first (+$unit target, then slope force-close), then the
            # RSI DCA ladder adds -- closing has priority over taking new positions.
            if buy_profit > close_threshold:
                buy_status = Signal.CLOSE_BUY
                exit_reason = 'target'
            elif buy_fc:
                buy_status = Signal.CLOSE_BUY
                exit_reason = buy_fc_reason
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

        elif buy_count == 0 and sell_count > 0:
            # Open SELL (mirror): close first (+$unit target, then slope force-close),
            # then the RSI DCA ladder adds.
            if sell_profit > close_threshold:
                sell_status = Signal.CLOSE_SELL
                exit_reason = 'target'
            elif sell_fc:
                sell_status = Signal.CLOSE_SELL
                exit_reason = sell_fc_reason
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

        analysis_data = {
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'slopes': slopes or {},
            'slope_direction': slope_direction or 'WAIT',
            'score': slope_score,
            'entry_allowed': bool(entry_allowed),
            'exit_reason': exit_reason,
        }

        return buy_status, sell_status, analysis_data
