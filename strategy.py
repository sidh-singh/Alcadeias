from enum import Enum
from constants import (
    STRATEGY_HEDGE,
    FIBO_SEQUENCE_LENGTH,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
    PROFIT_PROTECT_USD_PER_UNIT,
    ENTRY_S, ENTRY_AGREE_S, LADDER_S, FORCE_CLOSE_S, BOOK_S,
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
    """RSI+MACD slope strategy - slope entry, RSI Fibo DCA ladder, slope exits."""

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

    @staticmethod
    def _entry_direction(score, exit_score):
        """Fresh-entry direction. Opens only when the SLOW trend score is clearly directional AND the
        FAST exit_score is NOT opposing it (agreement gate added 2026-10-29):
          score >= ENTRY_S  and exit_score >= ENTRY_AGREE_S   -> BUY
          score <= -ENTRY_S and exit_score <= -ENTRY_AGREE_S  -> SELL
          else                                                -> WAIT
        Why the gate: since v3.6.0 entry runs on the slow score but the force-close runs on the fast
        exit_score, so in chop (slow bullish / fast bearish) the bot would open on the slow score and
        force-close ~1-2s later on the fast score -- an open-and-instantly-close "vibration". Requiring
        the fast score to agree means that during slow/fast disagreement the bot simply WAITS until the
        chop settles (both scores point the same way), instead of churning out false trades. The
        level-based regime was fully removed 2026-10-27; this is a score-only gate. ENTRY_AGREE_S is
        tunable (0 = fast score must merely not oppose). Returns 'BUY' / 'SELL' / None."""
        if score >= ENTRY_S and exit_score >= ENTRY_AGREE_S:
            return 'BUY'
        if score <= -ENTRY_S and exit_score <= -ENTRY_AGREE_S:
            return 'SELL'
        return None

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
        RSI+MACD slope strategy (slope-exit variant). TWO weighted scores -- "enter slow, exit fast"
        (asymmetric weighting added 2026-10-28, variant-A `_h` only):
          - slope_score (SLOW, trend): 4*D1 + 3*H4 + 2*H1 + 1*M15  -> entry + ladder.
          - exit_score  (FAST, react): 4*M15 + 3*H1 + 2*H4 + 1*D1  -> profit-book + force-close.
        Both range -20..+20; same thresholds -- the exit's extra sensitivity is from the weighting.

          Flat: open when the SLOW slope_score is directional AND the FAST exit_score agrees
                (agreement gate, 2026-10-29) - BUY: slope_score >= ENTRY_S and exit_score >=
                ENTRY_AGREE_S; SELL mirror; else WAIT. When the two scores disagree (chop) the bot
                WAITS rather than open-and-instantly-force-close. Single position, cooldown-gated.
                (slope_direction is the dashboard's structural read only.)
          Open:
            Exits (checked first; both on the FAST exit_score):
              - profit-book (variant A): once profit > times * PROFIT_PROTECT_USD_PER_UNIT, book when
                exit_score reverses - BUY exit_score <= -BOOK_S, SELL >= +BOOK_S (reason 'book').
                Checked before the force-close.
              - force-close: close when exit_score is far enough against the basket - BUY exit_score
                <= -FORCE_CLOSE_S, SELL >= +FORCE_CLOSE_S (reason 'force_close').
            RSI DCA ladder (if no exit; gated on the SLOW slope_score): BUY_MORE/SELL_MORE at RSI
            35/65, one tier per open count - count 1->M1, 2->M5, 3->M15, 4->H1, 5->H4 (max 6
            positions); an add fires only when slope_score is not strongly against it. Fibo. Else HOLD.

        Args:
            source_df: Raw OHLC DataFrame (capitalized: Open, High, Low, Close)
            buy_positions / sell_positions: dicts from get_*_positions() or None
            times: effective unit; scales the Fibo lot ladder.
            close_threshold: legacy param, unused in this variant.
            rsi_value: current RSI (dashboard/logs).
            rsi_mtf: {timeframe_name: rsi_value} - drives the DCA ladder tiers.
            slopes: {tf: {'rsi': <pivot-slope>, 'macd': <pivot-slope>}} for 15M/H1/H4 + D1 - all four
                    TFs feed both the slow slope_score (entry/ladder) and the fast exit_score (exits).
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

        # Per-timeframe RSI for the DCA ladder tiers (count 1->M1 ... 5->H4)
        rsi_1m = rsi_mtf.get('TIMEFRAME_M1', 50.0) if rsi_mtf else 50.0
        rsi_5m = rsi_mtf.get('TIMEFRAME_M5', 50.0) if rsi_mtf else 50.0
        rsi_15m = rsi_mtf.get('TIMEFRAME_M15', 50.0) if rsi_mtf else 50.0
        rsi_1h = rsi_mtf.get('TIMEFRAME_H1', 50.0) if rsi_mtf else 50.0
        rsi_4h = rsi_mtf.get('TIMEFRAME_H4', 50.0) if rsi_mtf else 50.0

        # Slope signs for all four TFs (D1/H4/H1/15M -> the weighted score) + fresh-entry direction
        h4r = self._slope_sign(slopes, 'H4', 'rsi')
        h4m = self._slope_sign(slopes, 'H4', 'macd')
        h1r = self._slope_sign(slopes, 'H1', 'rsi')
        h1m = self._slope_sign(slopes, 'H1', 'macd')
        m15r = self._slope_sign(slopes, 'M15', 'rsi')
        m15m = self._slope_sign(slopes, 'M15', 'macd')
        d1r = self._slope_sign(slopes, 'D1', 'rsi')
        d1m = self._slope_sign(slopes, 'D1', 'macd')
        slope_direction = self._slope_direction(slopes)   # structural 4H/1H/15M read (dashboard/compare only; entry uses the score)

        # ENTRY/LADDER score (the SLOW, trend-weighted read). S = 4*D1 + 3*H4 + 2*H1 + 1*M15, each
        # TF = its RSI + MACD slope signs; range -20..+20 (negative = bearish). Higher (slower) TF
        # dominates so fresh entries + DCA adds follow the trend, not 15-min noise. Drives entry and
        # the ladder gate ONLY (exits use the fast exit_score below). No regime (removed 2026-10-27).
        slope_score = (4 * (d1r + d1m) + 3 * (h4r + h4m)
                       + 2 * (h1r + h1m) + 1 * (m15r + m15m))

        # EXIT score (the FAST, reaction-weighted read) -- the SAME four TFs with the weights REVERSED:
        # S_exit = 4*M15 + 3*H1 + 2*H4 + 1*D1; range -20..+20. Here the fastest TF dominates, so a
        # short-term reversal moves S_exit ~4x more than it moves slope_score (M15 now +/-8 vs +/-2).
        # Added 2026-10-28 (variant-A `_h` only): booking/force-close on slope_score lagged -- the
        # slow weights couldn't cross BOOK_S/FORCE_CLOSE_S until H1/H4 confirmed, giving back profit.
        # Drives the profit-book + force-close ONLY; entry/ladder keep the slow slope_score ("enter
        # slow, exit fast"). Same thresholds, same -20..+20 scale -- the sensitivity comes from the
        # weighting, not the thresholds.
        exit_score = (4 * (m15r + m15m) + 3 * (h1r + h1m)
                      + 2 * (h4r + h4m) + 1 * (d1r + d1m))

        # Fresh-entry direction: the SLOW slope_score must be directional AND the FAST exit_score must
        # not oppose it (agreement gate, 2026-10-29). Opens BUY on slope_score >= +ENTRY_S & exit_score
        # >= +ENTRY_AGREE_S; SELL mirror. Stops the open-then-instant-force-close "vibration": when the
        # two scores disagree (chop) the bot WAITS instead of opening a false position. (slope_direction
        # stays above only as the dashboard's structural read.)
        entry_direction = self._entry_direction(slope_score, exit_score)
        # Telemetry: the slow score alone WANTED in but the fast score vetoed it (chop) -> we're waiting.
        slow_wants = 'BUY' if slope_score >= ENTRY_S else ('SELL' if slope_score <= -ENTRY_S else None)
        entry_chop_block = bool(slow_wants and entry_direction is None)

        # DCA ladder gate (score-only). Average into a position only while the weighted score is not
        # strongly adverse: a BUY may add unless score <= -LADDER_S; a SELL unless score >= +LADDER_S.
        # Blocks the "average down into a trend" half of the 2026-10 loss (that case scored -14, well
        # past -LADDER_S).
        buy_add_ok = slope_score > -LADDER_S
        sell_add_ok = slope_score < LADDER_S

        # Force-close (EXIT): close a basket when the FAST exit_score has moved far enough AGAINST it
        # -- a BUY at exit_score <= -FORCE_CLOSE_S, a SELL at exit_score >= +FORCE_CLOSE_S. Uses the
        # fast (M15-dominant) score so a loss is cut on the short-term reversal instead of waiting for
        # the slow TFs to confirm. Single threshold, no regime. Tunable in constants.py.
        buy_fc = exit_score <= -FORCE_CLOSE_S
        buy_fc_reason = 'force_close'
        sell_fc = exit_score >= FORCE_CLOSE_S
        sell_fc_reason = 'force_close'

        # Profit-book (variant A's ONLY profit exit; no +$unit target). Once the basket is in profit
        # by at least times * PROFIT_PROTECT_USD_PER_UNIT (buffer scales with the unit / entry lot),
        # book when the FAST exit_score has reversed far enough against it -- a BUY at exit_score <=
        # -BOOK_S, a SELL at exit_score >= +BOOK_S. Uses the fast (M15-dominant) score so profit is
        # taken on the short-term turn instead of bleeding back while the slow TFs catch up. Checked
        # BEFORE the force-close (in profit a book beats a capitulation). Single threshold. Tunable.
        profit_protect_min = times * PROFIT_PROTECT_USD_PER_UNIT
        buy_pp = (buy_profit > profit_protect_min) and (exit_score <= -BOOK_S)
        buy_pp_reason = 'book'
        sell_pp = (sell_profit > profit_protect_min) and (exit_score >= BOOK_S)
        sell_pp_reason = 'book'

        if buy_count == 0 and sell_count == 0:
            # Fresh entry (single position; opens on the weighted score), cooldown-gated.
            if entry_allowed and entry_direction == 'BUY':
                buy_status = Signal.BUY
            elif entry_allowed and entry_direction == 'SELL':
                sell_status = Signal.SELL

        elif buy_count > 0 and sell_count == 0:
            # Open BUY: slope exits FIRST, then the RSI DCA ladder (threat = DOWN move).
            if buy_pp:
                buy_status = Signal.CLOSE_BUY
                exit_reason = buy_pp_reason
            elif buy_fc:
                buy_status = Signal.CLOSE_BUY
                exit_reason = buy_fc_reason
            elif buy_add_ok:
                # DCA add - gated: averages into the long only when the score is not against it.
                if rsi_1m <= RSI_OVERSOLD and buy_count == 1:
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
            # Open SELL (mirror): slope exits FIRST, then the RSI DCA ladder.
            if sell_pp:
                sell_status = Signal.CLOSE_SELL
                exit_reason = sell_pp_reason
            elif sell_fc:
                sell_status = Signal.CLOSE_SELL
                exit_reason = sell_fc_reason
            elif sell_add_ok:
                # DCA add - gated: averages into the short only when the score is not against it.
                if rsi_1m >= RSI_OVERBOUGHT and sell_count == 1:
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
            'entry_direction': entry_direction or 'WAIT',
            'score': slope_score,
            'exit_score': exit_score,
            'buy_add_ok': bool(buy_add_ok),
            'sell_add_ok': bool(sell_add_ok),
            'entry_allowed': bool(entry_allowed),
            'entry_chop_block': bool(entry_chop_block),
            'exit_reason': exit_reason,
        }

        return buy_status, sell_status, analysis_data
