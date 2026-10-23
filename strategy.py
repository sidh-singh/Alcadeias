from enum import Enum
from constants import (
    STRATEGY_HEDGE,
    FIBO_SEQUENCE_LENGTH,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
    PROFIT_PROTECT_USD_PER_UNIT,
    REGIME_RSI_BULL, REGIME_RSI_BEAR, REGIME_LADDER_S,
    FORCE_CLOSE_S_WITH, FORCE_CLOSE_S_NEUTRAL, FORCE_CLOSE_S_AGAINST,
    ENTRY_S_WITH, ENTRY_S_NEUTRAL,
    BOOK_S_WITH, BOOK_S_NEUTRAL, BOOK_S_AGAINST,
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
    def _macd_line(slopes, tf):
        """Latest MACD-line value for a timeframe (0.0 if missing). Distinct from the
        histogram pivot slope - this is the raw MACD line, the regime's level input."""
        try:
            v = slopes[tf]['macd_line']
        except (KeyError, TypeError, IndexError):
            return 0.0
        return v if isinstance(v, (int, float)) else 0.0

    @staticmethod
    def _regime_tf(rsi_level, macd_line):
        """Per-TF regime verdict from LEVEL (not slope): 'BULL' / 'BEAR' / 'NEUTRAL'.
        BULL = RSI > REGIME_RSI_BULL AND MACD line > 0; BEAR = RSI < REGIME_RSI_BEAR AND
        MACD line < 0; else NEUTRAL. The 'tide' direction for one big TF (D1 or H4);
        see docs/weighted-regime-redesign.md §4."""
        if rsi_level > REGIME_RSI_BULL and macd_line > 0:
            return 'BULL'
        if rsi_level < REGIME_RSI_BEAR and macd_line < 0:
            return 'BEAR'
        return 'NEUTRAL'

    @staticmethod
    def _regime_combine(d1_regime, h4_regime):
        """Combine the big-TF verdicts into one tide - D1 leads, H4 confirms. D1 sets the
        bias; H4 can only downgrade a biased D1 to NEUTRAL when it directly opposes, and
        cannot create a bias when D1 is NEUTRAL (table in the design doc §4)."""
        if d1_regime == 'BULL':
            return 'NEUTRAL' if h4_regime == 'BEAR' else 'BULL'
        if d1_regime == 'BEAR':
            return 'NEUTRAL' if h4_regime == 'BULL' else 'BEAR'
        return 'NEUTRAL'

    @staticmethod
    def _entry_direction(regime, score):
        """Fresh-entry direction from the score + regime (the 'tide + waves' open rule): open
        WITH the tide once the score confirms, demand a bigger score with no tide, and never
        open against the tide. BUY: BULL & score>=ENTRY_S_WITH, or NEUTRAL & score>=ENTRY_S_NEUTRAL.
        SELL mirrors (score<=-X; swap BULL<->BEAR). Returns 'BUY' / 'SELL' / None (WAIT). A BEAR
        tide blocks new longs and a BULL tide blocks new shorts. See doc §6."""
        if regime == 'BULL' and score >= ENTRY_S_WITH:
            return 'BUY'
        if regime == 'NEUTRAL' and score >= ENTRY_S_NEUTRAL:
            return 'BUY'
        if regime == 'BEAR' and score <= -ENTRY_S_WITH:
            return 'SELL'
        if regime == 'NEUTRAL' and score <= -ENTRY_S_NEUTRAL:
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
        RSI+MACD slope strategy (slope-exit variant).

          Flat: open from the score + regime (Step 5) - BUY when regime BULL & S>=8 or
                NEUTRAL & S>=12; SELL mirrors (S<=-8 / -12); BEAR blocks new longs, BULL blocks
                new shorts. Single position, cooldown-gated. See docs/weighted-regime-redesign.md §6.
          Open:
            Exits (checked first):
              - profit-book (score + regime, Step 6): once profit > times *
                PROFIT_PROTECT_USD_PER_UNIT, book when the score reverses enough - BUY: BULL
                S<=-6 / NEUTRAL S<=-4 / BEAR S<=-2 ('book_bull'/'book_neutral'/'book_bear'); SELL
                mirrors. Let a with-trend winner run, grab a counter-trend one fast. Checked first.
              - force-close (score + regime, Step 4): close when the weighted score S is far
                enough AGAINST the basket, scaled by the tide - BUY: BULL S<=-12 / NEUTRAL
                S<=-8 / BEAR S<=-4 ('fc_bull'/'fc_neutral'/'fc_bear'); SELL mirrors. See
                docs/weighted-regime-redesign.md §6.
            RSI DCA ladder (if no exit; score+regime gated, Step 3): BUY_MORE/SELL_MORE at
            RSI 35/65, one tier per open count - count 1->M1, 2->M5, 3->M15, 4->H1, 5->H4
            (max 6 positions); an add fires only when the tide/score is not against the
            position. Fibo lot sizing. Else HOLD.

        Args:
            source_df: Raw OHLC DataFrame (capitalized: Open, High, Low, Close)
            buy_positions / sell_positions: dicts from get_*_positions() or None
            times: effective unit; scales the Fibo lot ladder.
            close_threshold: legacy param, unused in this variant.
            rsi_value: current RSI (dashboard/logs).
            rsi_mtf: {timeframe_name: rsi_value} - drives the DCA ladder tiers.
            slopes: {tf: {'rsi': <pivot-slope>, 'macd': <pivot-slope>}} for 15M/H1/H4 (entry +
                    exits) + D1 (exit-regime only) - drives entry direction and the slope exits.
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

        # Slope signs (15M/H1/H4 entry+exit; D1 exit-regime) + fresh-entry direction
        h4r = self._slope_sign(slopes, 'H4', 'rsi')
        h4m = self._slope_sign(slopes, 'H4', 'macd')
        h1r = self._slope_sign(slopes, 'H1', 'rsi')
        h1m = self._slope_sign(slopes, 'H1', 'macd')
        m15r = self._slope_sign(slopes, 'M15', 'rsi')
        m15m = self._slope_sign(slopes, 'M15', 'macd')
        d1r = self._slope_sign(slopes, 'D1', 'rsi')
        d1m = self._slope_sign(slopes, 'D1', 'macd')
        slope_direction = self._slope_direction(slopes)   # structural 4H/1H/15M read (dashboard/compare only; entry uses score+regime)

        # Weighted MTF slope score. S = 4*D1 + 3*H4 + 2*H1 + 1*M15, each TF = its RSI + MACD
        # slope signs; range -20..+20 (negative = bearish). Weighted-score + regime redesign;
        # read LIVE by the ladder gate (Step 3), force-close (Step 4) and entry (Step 5). Higher
        # TF dominates; one noisy sign moves S by <=1. See docs/weighted-regime-redesign.md.
        slope_score = (4 * (d1r + d1m) + 3 * (h4r + h4m)
                       + 2 * (h1r + h1m) + 1 * (m15r + m15m))

        # Regime "tide". From the big-TF LEVEL (not the pivot slope): per-TF BULL/BEAR/NEUTRAL
        # (RSI vs REGIME_RSI_BULL/BEAR + MACD line vs 0), combined D1-leads-H4. Weighted-score +
        # regime redesign (doc §4). Pairs with slope_score: the tide = slow bias/direction, the
        # score ("waves") = fast timing. Read LIVE by the ladder gate (3), force-close (4), entry (5).
        rsi_d1 = rsi_mtf.get('TIMEFRAME_D1', 50.0) if rsi_mtf else 50.0
        d1_regime = self._regime_tf(rsi_d1, self._macd_line(slopes, 'D1'))
        h4_regime = self._regime_tf(rsi_4h, self._macd_line(slopes, 'H4'))
        regime = self._regime_combine(d1_regime, h4_regime)

        # Fresh-entry direction (Step 5, LIVE) from the score + regime -- replaces the structural
        # _slope_direction for OPENING: open with the tide once the score confirms, never against
        # it (slope_direction is kept above only as the dashboard's structural read). See doc §6.
        entry_direction = self._entry_direction(regime, slope_score)

        # DCA ladder gate (Step 3, LIVE — the first decision wired to the score + regime).
        # Average into a position ONLY when the tide is not against it AND the score is not
        # strongly adverse: a BUY may add unless regime BEAR or S <= -REGIME_LADDER_S; a SELL
        # may add unless regime BULL or S >= +REGIME_LADDER_S. Blocks the "average down into a
        # trend" half of the 2026-10 loss (doc §6). Exits / entry are unchanged (Steps 4-6).
        buy_add_ok = (regime != 'BEAR') and (slope_score > -REGIME_LADDER_S)
        sell_add_ok = (regime != 'BULL') and (slope_score < REGIME_LADDER_S)

        # Force-close (EXIT) via the weighted score + regime (Step 4, LIVE). Replaces the v2.x
        # D1 cascade (sensitive / normal / split paths). Close a basket when the score has moved
        # far enough AGAINST it; the distance scales with the tide -- WITH the tide give a winner
        # room (deep reversal needed), AGAINST the tide cut fast. BUY shown; SELL mirrors (flip
        # the score, swap BULL<->BEAR). Thresholds tunable in constants.py; see doc §6.
        #   BUY : BULL -> S <= -WITH ; NEUTRAL -> S <= -NEUTRAL ; BEAR -> S <= -AGAINST
        if regime == 'BULL':                                   # tide with the long -> give it room
            buy_close_at = -FORCE_CLOSE_S_WITH
        elif regime == 'BEAR':                                 # tide against the long -> cut fast
            buy_close_at = -FORCE_CLOSE_S_AGAINST
        else:                                                  # NEUTRAL
            buy_close_at = -FORCE_CLOSE_S_NEUTRAL
        buy_fc = slope_score <= buy_close_at
        buy_fc_reason = 'fc_' + regime.lower()                 # fc_bull / fc_neutral / fc_bear

        if regime == 'BEAR':                                   # tide with the short -> give it room
            sell_close_at = FORCE_CLOSE_S_WITH
        elif regime == 'BULL':                                 # tide against the short -> cut fast
            sell_close_at = FORCE_CLOSE_S_AGAINST
        else:                                                  # NEUTRAL
            sell_close_at = FORCE_CLOSE_S_NEUTRAL
        sell_fc = slope_score >= sell_close_at
        sell_fc_reason = 'fc_' + regime.lower()

        # Profit-book (score + regime, Step 6 - variant A's ONLY profit exit; no +$unit target).
        # Once the basket is in profit by at least times * PROFIT_PROTECT_USD_PER_UNIT (buffer
        # scales with the unit / entry lot), book when the score has reversed enough against it;
        # how far scales with the tide -- let a with-trend winner run (deeper reversal needed),
        # grab a counter-trend winner fast. BUY shown; SELL mirrors. Checked BEFORE the force-close
        # (in profit a book beats a capitulation). Thresholds tunable; see doc §6.
        #   BUY : BULL -> S <= -BOOK_S_WITH ; NEUTRAL -> -BOOK_S_NEUTRAL ; BEAR -> -BOOK_S_AGAINST
        profit_protect_min = times * PROFIT_PROTECT_USD_PER_UNIT
        if regime == 'BULL':                                   # tide with the long -> let it run
            buy_book_at = -BOOK_S_WITH
        elif regime == 'BEAR':                                 # tide against the long -> grab it
            buy_book_at = -BOOK_S_AGAINST
        else:                                                  # NEUTRAL
            buy_book_at = -BOOK_S_NEUTRAL
        buy_pp = (buy_profit > profit_protect_min) and (slope_score <= buy_book_at)
        buy_pp_reason = 'book_' + regime.lower()               # book_bull / book_neutral / book_bear

        if regime == 'BEAR':                                   # tide with the short -> let it run
            sell_book_at = BOOK_S_WITH
        elif regime == 'BULL':                                 # tide against the short -> grab it
            sell_book_at = BOOK_S_AGAINST
        else:                                                  # NEUTRAL
            sell_book_at = BOOK_S_NEUTRAL
        sell_pp = (sell_profit > profit_protect_min) and (slope_score >= sell_book_at)
        sell_pp_reason = 'book_' + regime.lower()

        if buy_count == 0 and sell_count == 0:
            # Fresh entry (single position; score + regime, Step 5), cooldown-gated.
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
                # DCA add - gated: averages into the long only when the tide/score is not against it.
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
                # DCA add - gated: averages into the short only when the tide/score is not against it.
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
            'regime': regime,
            'regime_d1': d1_regime,
            'regime_h4': h4_regime,
            'buy_add_ok': bool(buy_add_ok),
            'sell_add_ok': bool(sell_add_ok),
            'entry_allowed': bool(entry_allowed),
            'exit_reason': exit_reason,
        }

        return buy_status, sell_status, analysis_data
