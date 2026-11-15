import math
from enum import Enum
from constants import (
    STRATEGY_HEDGE,
    FIBO_SEQUENCE_LENGTH,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
    ENTRY_S, ENTRY_AGREE_S, LADDER_S, FORCE_CLOSE_S,
    OPEN_SCORE_WEIGHTS, FORCE_CLOSE_SCORE_WEIGHTS,
    # design levers (constants.py; the defaults are the live bot). Read at call time, like the names above.
    FORCE_CLOSE_ENABLED, MAX_ADDS, LADDER_TRIGGER, LADDER_TFS, LADDER_MULTIPLIERS,
)

LADDER_TRIGGERS = ('rsi_level', 'macd_turn')


def _tf_key(tf):
    """'TIMEFRAME_H1' or 'H1' -> 'H1'."""
    s = str(tf).strip().upper()
    return s[len('TIMEFRAME_'):] if s.startswith('TIMEFRAME_') else s


def _round2(x):
    """Round to cents, half away from zero (the backtester's _round2, used for its ladder lots)."""
    if x >= 0.0:
        return math.floor(x * 100.0 + 0.5) / 100.0
    return -math.floor(-x * 100.0 + 0.5) / 100.0


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float('inf')


class Signal(Enum):
    DO_NOTHING = 0
    BUY = 1
    SELL = 2
    CLOSE_BUY = 3
    CLOSE_SELL = 4
    BUY_MORE = 5
    SELL_MORE = 6


class Strategy:
    """RSI+MACD slope entry + RSI Fibo DCA ladder; +$unit target or fast-score force-close (variant B)."""

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

    # ── design levers: which timeframes the strategy reads, the ladder's tiers and sizes ──
    @staticmethod
    def ladder_tiers():
        """Tier timeframe (short key) of each ladder add: add n uses ladder_tiers()[n-1].
        min(len(LADDER_TFS), MAX_ADDS) tiers (the backtester's n_ladder_adds); [] = no ladder.
        Live: M1, M5, M15, H1, H4 (5 adds, at most 6 positions)."""
        n = max(0, min(len(LADDER_TFS), int(MAX_ADDS)))
        return [_tf_key(t) for t in list(LADDER_TFS)[:n]]

    @staticmethod
    def slope_timeframes():
        """'TIMEFRAME_<key>' of every timeframe whose RSI + MACD pivot votes this strategy reads: the OPEN and
        FORCE-CLOSE section timeframes (the force-close section is also the entry-agreement section, so it is
        read even with FORCE_CLOSE_ENABLED off) plus, for a 'macd_turn' ladder, the tier timeframes (their
        votes carry no weight in any score). app.py computes votes for these on top of SLOPE_TIMEFRAMES."""
        keys = [_tf_key(k) for k in list(OPEN_SCORE_WEIGHTS) + list(FORCE_CLOSE_SCORE_WEIGHTS)]
        if LADDER_TRIGGER == 'macd_turn':
            keys += Strategy.ladder_tiers()
        return ['TIMEFRAME_' + k for k in dict.fromkeys(keys)]

    @staticmethod
    def rsi_timeframes():
        """'TIMEFRAME_<key>' of the ladder tiers, whose forming-bar RSI the 'rsi_level' ladder reads."""
        return ['TIMEFRAME_' + k for k in dict.fromkeys(Strategy.ladder_tiers())]

    def next_add_volume(self, total_volume, count, times, mtqty=0.01):
        """Lots of the next ladder add, `count` positions being open already.
        LADDER_MULTIPLIERS None: the live Fibonacci size (_get_next_fibo_volume, bit-for-bit).
        A list: LADDER_MULTIPLIERS[count] units (padded with its last element), rounded to cents half away
        from zero as the backtester does (kernels.py: _round2(ladder_mult[n_pos] * basket_units * mtqty))."""
        if LADDER_MULTIPLIERS is None:
            return self._get_next_fibo_volume(total_volume, times)
        mult = list(LADDER_MULTIPLIERS)
        m = mult[count] if count < len(mult) else mult[-1]
        return _round2(float(m) * times * mtqty)

    @staticmethod
    def design_problems():
        """Why the strategy's design levers cannot run (empty list = fine). Mirrors BacktestConfig's checks."""
        problems = []
        if not isinstance(FORCE_CLOSE_ENABLED, bool):
            problems.append(f'FORCE_CLOSE_ENABLED must be True or False, not {FORCE_CLOSE_ENABLED!r}')
        if not isinstance(MAX_ADDS, int) or isinstance(MAX_ADDS, bool) or MAX_ADDS < 0:
            problems.append(f'MAX_ADDS must be a whole number >= 0, not {MAX_ADDS!r}')
        if LADDER_TRIGGER not in LADDER_TRIGGERS:
            problems.append(f'LADDER_TRIGGER {LADDER_TRIGGER!r} is not one of {LADDER_TRIGGERS}')
        if not isinstance(LADDER_TFS, (list, tuple)) or not all(isinstance(t, str) and t for t in LADDER_TFS):
            problems.append(f'LADDER_TFS must be a list of timeframe names, not {LADDER_TFS!r}')
        if LADDER_MULTIPLIERS is not None:
            m = LADDER_MULTIPLIERS
            if (not isinstance(m, (list, tuple)) or not m or not all(_is_number(x) and x > 0 for x in m)):
                problems.append(f'LADDER_MULTIPLIERS must be None or a list of positive numbers, not {m!r}')
            elif float(m[0]) != 1.0:
                problems.append('LADDER_MULTIPLIERS[0] is the entry and must be 1 (the adds are elements 1, 2, ...)')
        for name, w in (('OPEN_SCORE_WEIGHTS', OPEN_SCORE_WEIGHTS), ('FORCE_CLOSE_SCORE_WEIGHTS', FORCE_CLOSE_SCORE_WEIGHTS)):
            if not isinstance(w, dict) or not all(_is_number(v) for v in w.values()):
                problems.append(f'{name} must be a {{timeframe: weight}} dict, not {w!r}')
        return problems

    def _ladder_add(self, side, count, add_ok, rsi_mtf, slopes, armed, gap, last_fill, bid, ask):
        """The ladder branch of an open basket (reached only when no exit fired), as the backtester runs it
        (kernels.py L1093-1147): tier -> trigger (and arming) -> open-score gate -> price gap.
        Returns (add?, armed, tier timeframe or None).
          tier:      positions `count` -> LADDER_TFS[count-1]; no tier left -> no add (and no arming).
          trigger:   'rsi_level' the tier's forming-bar RSI <= RSI_OVERSOLD (buy) / >= RSI_OVERBOUGHT (sell);
                     'macd_turn' the tier's MACD vote not with the basket (<= 0 for a buy) ARMS the ladder,
                     which then stays armed (also through polls the gate or the gap refuse) until an add
                     fills; it fires on a later poll with the vote with the basket.
          gate:      add_ok (OPEN score not fully against the basket).
          gap:       gap > 0: buy needs last fill - ask >= gap, sell needs bid - last fill >= gap."""
        tiers = self.ladder_tiers()
        if count < 1 or count > len(tiers):
            return False, armed, None
        tf = tiers[count - 1]
        if LADDER_TRIGGER == 'macd_turn':
            vote = self._slope_sign(slopes, tf, 'macd')
            if vote * side <= 0:
                armed = True
            hit = armed and vote * side > 0
        else:
            r = rsi_mtf.get('TIMEFRAME_' + tf, 50.0) if rsi_mtf else 50.0
            hit = (r <= RSI_OVERSOLD) if side > 0 else (r >= RSI_OVERBOUGHT)
        if not hit or not add_ok:
            return False, armed, tf
        if gap and gap > 0.0:
            quote = ask if side > 0 else bid
            if last_fill is None or quote is None:
                return False, armed, tf
            gap_ok = (last_fill - ask) >= gap if side > 0 else (bid - last_fill) >= gap
            if not gap_ok:
                return False, armed, tf
        return True, armed, tf

    @staticmethod
    def _slope_sign(slopes, tf, ind):
        """Slope sign (+1/-1/0) for (timeframe, indicator); 0 if missing/undefined."""
        try:
            s = slopes[tf][ind]['sign']
        except (KeyError, TypeError, IndexError):
            return 0
        return s if s in (-1, 0, 1) else 0

    @staticmethod
    def _weighted_score(slopes, weights, grey_fill=False):
        """RAW weighted slope score for one section's {TF: weight} map (config-driven; raw rescale
        2026-10-30). Each section (open / force-close) has its OWN timeframe set + weights in
        constants.py; add/remove a timeframe there.
            score = Σ weight * (rsi_sign + macd_sign)   over the map  (each sign ∈ {-1,0,+1})
        So the section's range is ±(2 * Σ|weight|): e.g. {'H4':1,'M5':1} -> -4..+4 ; the 4/3/2/1
        force-close set -> -20..+20. Thresholds in constants.py are in these RAW units, so change a
        section's timeframes and its range (and its threshold) move together -- the dashboard gauge is
        scaled to ±(2*Σ|w|) per section to match. A missing/zero slope contributes 0; an empty map -> 0.

        grey_fill (OPEN; 2026-10-31): when EXACTLY ONE of a timeframe's two signs is 0 (grey -- its RSI
        or MACD is at a peak/plateau so the pivot slope is undefined), substitute the OTHER sign for the
        grey one, so a timeframe that is clear on one indicator and grey on the other counts as a FULL
        aligned vote (±2·w) instead of half. Both grey -> the timeframe stays 0, so a fully-grey
        timeframe defers to the section's OTHER timeframes via the threshold (open fires only if another
        timeframe is aligned, else WAIT). The FORCE-CLOSE score keeps RAW signs (grey_fill off).
        grey_fill never changes the per-TF max (±2·w), so the section's range is unchanged."""
        total = 0
        for tf, w in weights.items():
            r = Strategy._slope_sign(slopes, tf, 'rsi')
            m = Strategy._slope_sign(slopes, tf, 'macd')
            if grey_fill:
                if r == 0 and m != 0:      # RSI grey -> borrow MACD's direction
                    r = m
                elif m == 0 and r != 0:    # MACD grey -> borrow RSI's direction
                    m = r
            total += w * (r + m)
        return total

    @staticmethod
    def _entry_direction(open_score, fc_score):
        """Fresh-entry direction. Opens only when the OPEN score is clearly directional AND the
        FORCE-CLOSE score is NOT opposing it (agreement gate, 2026-10-29, kept through the per-section
        refactor 2026-10-30):
          open_score >= ENTRY_S  and fc_score >= ENTRY_AGREE_S   -> BUY
          open_score <= -ENTRY_S and fc_score <= -ENTRY_AGREE_S  -> SELL
          else                                                   -> WAIT
        Why the gate: entry runs on the OPEN score but the force-close runs on the FORCE-CLOSE score
        (different timeframe sets), so when they disagree (chop) the bot would open and force-close
        ~1-2s later -- an open-and-instantly-close "vibration". Requiring the force-close score not to
        oppose means that during disagreement the bot simply WAITS. ENTRY_AGREE_S is tunable
        (0 = force-close score must merely not oppose). Returns 'BUY' / 'SELL' / None."""
        if open_score >= ENTRY_S and fc_score >= ENTRY_AGREE_S:
            return 'BUY'
        if open_score <= -ENTRY_S and fc_score <= -ENTRY_AGREE_S:
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
                         entry_allowed=True,
                         stop_threshold=None, ladder_armed=False, ladder_gap=0.0,
                         last_fill_price=None, bid=None, ask=None):
        """
        Design levers (constants.py; their defaults are the live rules, so these arguments at their
        defaults reproduce live v3.9.2 exactly):
          close_threshold  basket target, USD for the whole basket (strict >); None = no target.
          stop_threshold   basket stop, USD for the whole basket: close at profit <= -stop_threshold.
                           Checked BEFORE the target. None = no stop (live).
          FORCE_CLOSE_ENABLED False: the force-close never fires; fc_score still gates the entry.
          ladder           tiers LADDER_TFS[:MAX_ADDS], trigger LADDER_TRIGGER ('macd_turn' reads and
                           updates `ladder_armed`, returned as analysis_data['ladder_armed']), the gap
                           `ladder_gap` (price units) from `last_fill_price` judged on `ask` (buy) / `bid`.

        RSI+MACD slope entry + RSI Fibo ladder; exits are the +$unit target or the force-close
        (variant B). Per-section weighted scores, each from its OWN configurable timeframe set
        (constants.py OPEN/FORCE_CLOSE_SCORE_WEIGHTS; 2026-10-30), each normalised to -20..+20 so its
        threshold survives adding/removing a TF:
          - open_score -> fresh entry + the DCA ladder-add gate   (default TFs: H4, M5)
          - fc_score   -> force-close                             (default TFs: M15,H1,H4,D1 w4/3/2/1)
        (No BOOK score on this pair -- profit books via the +$unit target, a USD level, not a score.)

          Flat: open when the OPEN score is directional AND the FORCE-CLOSE score agrees (agreement
                gate) - BUY: open_score >= ENTRY_S and fc_score >= ENTRY_AGREE_S; SELL mirror; else
                WAIT. When OPEN and FORCE-CLOSE disagree (chop) the bot WAITS rather than
                open-and-instantly-force-close. Single position, cooldown-gated. (slope_direction is
                the dashboard's structural read only.)
          Open (checked in order; closing has priority over adding):
            - +$unit target: basket profit > close_threshold (= unit) -> CLOSE (reason 'target').
            - force-close (on fc_score): close when it is far enough against the basket -
              BUY fc_score <= -FORCE_CLOSE_S, SELL >= +FORCE_CLOSE_S (reason 'force_close').
            - RSI DCA ladder (gated on the OPEN score): BUY_MORE/SELL_MORE at RSI 35/65, one tier per
              count (1->M1, 2->M5, 3->M15, 4->H1, 5->H4), Fibo lot sizing; an add fires only when
              open_score is not strongly against the position.
            - else HOLD.

        Args:
            source_df: Raw OHLC DataFrame (capitalized: Open, High, Low, Close)
            buy_positions / sell_positions: dicts from get_*_positions() or None
            times: effective unit; scales the Fibo lot ladder.
            close_threshold: USD basket profit target (= unit) for the +$unit close.
            rsi_value: current RSI (dashboard/logs).
            rsi_mtf: {timeframe_name: rsi_value} - drives the DCA ladder tiers.
            slopes: {tf: {'rsi': <pivot-slope>, 'macd': <pivot-slope>}} per fetched timeframe (the union
                    of the section TF sets) - fed to _weighted_score for each section.
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

        # The DCA ladder reads its tier timeframes' RSI from rsi_mtf (see _ladder_add; live tiers
        # 1->M1 ... 5->H4 = LADDER_TFS).

        slope_direction = self._slope_direction(slopes)   # structural 4H/1H/15M read (dashboard/compare only; entry uses the score)

        # ── Per-section RAW weighted slope scores (config-driven; 2026-10-30) ──
        # Each decision section computes its OWN raw score, range ±(2*Σ|w|), from its OWN timeframe set
        # (constants.py: OPEN / FORCE_CLOSE _SCORE_WEIGHTS). Add/remove a timeframe there. OPEN uses
        # grey_fill (a timeframe grey on one indicator borrows its other indicator's direction -> full
        # vote); FORCE-CLOSE uses raw signs. See _weighted_score. (This h6/variant-B pair books profit
        # via the +$unit target -- a USD level, not a score -- so there is NO book score here.)
        open_score = self._weighted_score(slopes, OPEN_SCORE_WEIGHTS, grey_fill=True)   # entry + ladder gate
        fc_score = self._weighted_score(slopes, FORCE_CLOSE_SCORE_WEIGHTS)              # force-close (raw signs)

        # Fresh-entry direction: the OPEN score must be directional AND the FORCE-CLOSE score must not
        # oppose it (agreement gate). BUY: open_score >= +ENTRY_S & fc_score >= +ENTRY_AGREE_S; SELL
        # mirror. Stops the open-then-instant-force-close "vibration": when the OPEN and FORCE-CLOSE
        # scores disagree (chop) the bot WAITS. (slope_direction stays as the dashboard structural read.)
        entry_direction = self._entry_direction(open_score, fc_score)
        # Telemetry: the OPEN score alone WANTED in but the force-close score vetoed it (chop) -> waiting.
        open_wants = 'BUY' if open_score >= ENTRY_S else ('SELL' if open_score <= -ENTRY_S else None)
        entry_chop_block = bool(open_wants and entry_direction is None)

        # DCA ladder-add gate: average into a position only while the OPEN score is not strongly adverse
        # -- a BUY may add unless open_score <= -LADDER_S; a SELL unless open_score >= +LADDER_S. An
        # "add" is "opening more", so it follows the OPEN section. Blocks averaging down into a trend.
        buy_add_ok = open_score > -LADDER_S
        sell_add_ok = open_score < LADDER_S

        # Force-close (EXIT): close a basket when the FORCE-CLOSE score has moved far enough AGAINST it
        # -- a BUY at fc_score <= -FORCE_CLOSE_S, a SELL at fc_score >= +FORCE_CLOSE_S. Tunable in
        # constants.py (threshold + the FORCE_CLOSE_SCORE_WEIGHTS timeframe set). Profit books via the
        # +$unit target below -- no score profit-book on this h6/variant-B pair.
        buy_fc = fc_score <= -FORCE_CLOSE_S
        buy_fc_reason = 'force_close'
        sell_fc = fc_score >= FORCE_CLOSE_S
        sell_fc_reason = 'force_close'
        fc_enabled = bool(FORCE_CLOSE_ENABLED)   # off: fc_score still gates the entry (above), it never closes
        ladder_tier = None

        if buy_count == 0 and sell_count == 0:
            # Fresh entry (single position; opens on the weighted score), cooldown-gated.
            if entry_allowed and entry_direction == 'BUY':
                buy_status = Signal.BUY
            elif entry_allowed and entry_direction == 'SELL':
                sell_status = Signal.SELL

        elif buy_count > 0 and sell_count == 0:
            # Open BUY: close first (stop, then target, then slope force-close), then the
            # ladder adds -- closing has priority over taking new positions.
            if stop_threshold is not None and buy_profit <= -stop_threshold:
                buy_status = Signal.CLOSE_BUY
                exit_reason = 'stop_loss'
            elif close_threshold is not None and buy_profit > close_threshold:
                buy_status = Signal.CLOSE_BUY
                exit_reason = 'target'
            elif fc_enabled and buy_fc:
                buy_status = Signal.CLOSE_BUY
                exit_reason = buy_fc_reason
            else:
                # DCA add - gated: averages into the long only when the score is not against it.
                # Live: one RSI tier per count (1->M1 ... 5->H4) at RSI <= RSI_OVERSOLD.
                add, ladder_armed, ladder_tier = self._ladder_add(
                    1, buy_count, buy_add_ok, rsi_mtf, slopes, ladder_armed, ladder_gap,
                    last_fill_price, bid, ask)
                if add:
                    buy_status = Signal.BUY_MORE

        elif buy_count == 0 and sell_count > 0:
            # Open SELL (mirror): close first (stop, then target, then slope force-close),
            # then the ladder adds.
            if stop_threshold is not None and sell_profit <= -stop_threshold:
                sell_status = Signal.CLOSE_SELL
                exit_reason = 'stop_loss'
            elif close_threshold is not None and sell_profit > close_threshold:
                sell_status = Signal.CLOSE_SELL
                exit_reason = 'target'
            elif fc_enabled and sell_fc:
                sell_status = Signal.CLOSE_SELL
                exit_reason = sell_fc_reason
            else:
                # DCA add - gated: averages into the short only when the score is not against it.
                # Live: one RSI tier per count (1->M1 ... 5->H4) at RSI >= RSI_OVERBOUGHT.
                add, ladder_armed, ladder_tier = self._ladder_add(
                    -1, sell_count, sell_add_ok, rsi_mtf, slopes, ladder_armed, ladder_gap,
                    last_fill_price, bid, ask)
                if add:
                    sell_status = Signal.SELL_MORE

        analysis_data = {
            'rsi_value': round(current_rsi, 2),
            'rsi_mtf': rsi_mtf or {},
            'slopes': slopes or {},
            'slope_direction': slope_direction or 'WAIT',
            'entry_direction': entry_direction or 'WAIT',
            'open_score': round(open_score, 1),
            'fc_score': round(fc_score, 1),
            'buy_add_ok': bool(buy_add_ok),
            'sell_add_ok': bool(sell_add_ok),
            'entry_allowed': bool(entry_allowed),
            'entry_chop_block': bool(entry_chop_block),
            'exit_reason': exit_reason,
            'force_close_enabled': fc_enabled,
            'close_threshold': close_threshold,
            'stop_threshold': stop_threshold,
            'ladder_armed': bool(ladder_armed),
            'ladder_tier': ladder_tier,
        }

        return buy_status, sell_status, analysis_data
