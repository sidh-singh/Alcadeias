"""
Alcadeias Trading Bot — Central Configuration
==============================================
All tuneable parameters in one place.
Edit this file to adjust strategy, indicator, dashboard, or system behaviour.
"""

# ─── Price Data Feed ───
# Main OHLC candle feed pulled each loop. This previously fed the SHA entry
# indicator (removed in the RSI+MACD rebuild); it is retained for market-liveness
# / metadata and as a price source. The RSI+MACD slope entry runs on its own
# 15M/H1/H4 fetches, independent of this feed.
CANDLE_TIMEFRAME = 'TIMEFRAME_M15'   # Timeframe for the main price feed (resolved via mt5 at runtime)
CANDLE_COUNT = 300
ALLOW_SYNTHETIC_TICK_BAR = True     # Append provisional bar from tick when MT5 bar feed lags (M1 only)

# ─── Market Status ───
MARKET_STATUS_TIMEFRAME = 'TIMEFRAME_M1'   # Timeframe used to check market open/closed
MARKET_LOOKBACK_MINUTES = 3                # Max minutes since last candle → still "open"

# ─── Strategy Parameters ───
STRATEGY_HEDGE = 1                  # Hedge / profit target multiplier
FIBO_SEQUENCE_LENGTH = 25           # Fibonacci sequence length (first 2 dropped)

# ─── RSI Indicator ───
RSI_LENGTH = 14                     # RSI period
RSI_MA_TYPE = 'RMA'                 # MA type for RSI smoothing (RMA = Wilder's, matches TradingView default)
# RSI(14) converges within a few hundred bars, so multi-timeframe RSI fetches use
# this smaller count instead of the large SHA CANDLE_COUNT. This avoids pulling
# years of history on high timeframes (e.g. 8000 H6 bars ≈ 5.5 years) every loop.
RSI_CANDLE_COUNT = 500
RSI_OVERSOLD = 35                   # DCA ladder: BUY_MORE when the tier timeframe RSI <= this
RSI_OVERBOUGHT = 65                 # DCA ladder: SELL_MORE when the tier timeframe RSI >= this

# ─── RSI fetch timeframes (for the dashboard RSI display; entry filter removed) ───
RSI_MTF_TIMEFRAMES = ['TIMEFRAME_M1', 'TIMEFRAME_M5', 'TIMEFRAME_M15', 'TIMEFRAME_M30']

# ─── RSI DCA Ladder Timeframes ───
# Tiered DCA (BUY_MORE / SELL_MORE) is gated by these timeframes' RSI — one
# timeframe per open-position count. Position 1 is the initial entry; each
# further position is added when the matching timeframe RSI hits its extreme:
#   count 1 → M1, count 2 → M5, count 3 → M15, count 4 → H1, count 5 → H4.
# After the last ladder position the basket is force-closed on the final-close
# timeframe RSI (see below).
RSI_DCA_LADDER_TIMEFRAMES = [
    'TIMEFRAME_M1', 'TIMEFRAME_M5', 'TIMEFRAME_M15', 'TIMEFRAME_H1', 'TIMEFRAME_H4',
]

# ─── RSI Final Forced-Close Timeframe ───
# When a basket has maxed out its DCA ladder, the final forced close is
# triggered by this timeframe's RSI hitting the oversold/overbought threshold.
# Previously the 1-hour (H1) RSI was used; now the 6-hour (H6) RSI.
RSI_FINAL_CLOSE_TIMEFRAME = 'TIMEFRAME_H6'

# ─── MACD Indicator (RSI+MACD slope entry engine) ───
MACD_FAST = 12                      # fast EMA length (TradingView ta.macd default)
MACD_SLOW = 26                      # slow EMA length
MACD_SIGNAL = 9                     # signal EMA length

# ─── Weighted-score gates (TWO asymmetric scores; NO regime) ───
# "Enter slow, exit fast" (2026-10-28, variant-A `_h` only). Two weighted MTF slope scores, each
# the same four TFs (RSI + MACD slope signs) but weighted opposite ways; both range -20..+20:
#   slope_score (SLOW/trend) = 4*D1 + 3*H4 + 2*H1 + 1*M15   -> entry + DCA ladder gate
#   exit_score  (FAST/react) = 4*M15 + 3*H1 + 2*H4 + 1*D1   -> profit-book + force-close
# Entry/adds follow the slow trend (higher TF dominant); exits react on the fast score (M15 now
# +/-8 vs +/-2) so profit is booked / a loss is cut on the short-term turn instead of lagging until
# H1/H4 confirm. The level-based regime ("tide") was fully REMOVED 2026-10-27. Each gate is a single
# score magnitude on the -20..+20 scale (all tunable on demo); the weights supply the sensitivity.
ENTRY_S = 6                         # |slope_score| to OPEN (BUY >= +6 / SELL <= -6)
LADDER_S = 6                        # DCA ladder add blocked once slope_score is this far adverse
                                    # (BUY add needs slope_score > -6; SELL add needs < +6)
FORCE_CLOSE_S = 8                   # force-close when EXIT_SCORE is this far AGAINST the basket
                                    # (BUY close exit_score <= -8; SELL close exit_score >= +8)
BOOK_S = 4                          # profit-book (variant A): in profit, book when EXIT_SCORE
                                    # reverses this far against (BUY <= -4; SELL >= +4)

# ─── Slope Engine (D1 + 4H + 1H + 15M pivot slopes -> both weighted scores) ───
# The latest-pivot slope SIGN on each of these timeframes (RSI + MACD) feeds BOTH the slow
# slope_score (4*D1 + 3*H4 + 2*H1 + 1*M15 -> entry/ladder) and the fast exit_score (4*M15 + 3*H1 +
# 2*H4 + 1*D1 -> book/force-close). Same signs, opposite weights. No regime (removed 2026-10-27).
# NOTE: unlike 15M, D1 is not fetched elsewhere, so including it = +1 MT5 rates call per loop.
SLOPE_TIMEFRAMES = ['TIMEFRAME_M15', 'TIMEFRAME_H1', 'TIMEFRAME_H4', 'TIMEFRAME_D1']  # all four feed the score
PEAK_LOOKBACK = 20                  # candles scanned for the latest pivot (configurable)
PIVOT_WIDTH = 2                     # bars required on each side to confirm a pivot (k)
# RSI pivots only count as real OB/OS turns inside these bands (MACD stays unbounded):
#   OB high valid when RSI >= RSI_PEAK_OB (65-5 -> [60,100]); OS low valid when
#   RSI <= RSI_PEAK_OS (35+5 -> [0,40]). Neutral-zone RSI wiggles (41-59) are ignored.
RSI_PEAK_OB = 60                    # a HIGH pivot on RSI counts only if value >= this
RSI_PEAK_OS = 40                    # a LOW  pivot on RSI counts only if value <= this
# Dashboard RSI pivot graphs (15M/H1/H4): recent RSI bars each mini-chart plots.
# Must exceed PEAK_LOOKBACK so the latest pivot is always within the drawn window.
RSI_GRAPH_BARS = 40
REENTRY_COOLDOWN_SECONDS = 300      # block a fresh entry for this long after any close
# Profit-protect threshold scales with the unit (= the entry lot): the basket must be in
# profit by at least PROFIT_PROTECT_USD_PER_UNIT * unit before a protect-close can fire, so the
# buffer tracks position size (unit 1 / lot 0.01 -> $1; unit 5 / lot 0.05 -> $5). Tune to cover
# round-trip costs per unit. (Variant A `_h` only; replaces the old flat PROFIT_PROTECT_MIN_USD.)
PROFIT_PROTECT_USD_PER_UNIT = 1.0


# ─── Risk Management ───
RISK_REWARD_RATIO = [1, 1]          # [risk, reward] multiplier for auto SL/TP calculation

# ─── File System / Output ───
OUTPUT_DIR = r'C:\Alcadeias'                    # Root directory for JSON data files
DAILY_TRADE_SUBDIR = 'daily_trade'              # Sub-folder for per-symbol daily trade logs
HISTORICAL_SUMMARY_DAYS = 3650                  # Days of deal history (≈ 10 years)
HISTORICAL_SUMMARY_FILENAME = 'historical_summary.json'

# ─── Dashboard ───
DASHBOARD_REFRESH_INTERVAL = 5000   # Auto-refresh interval in milliseconds
DASHBOARD_HOST = '0.0.0.0'
DASHBOARD_PORT = 8050
DASHBOARD_MAX_HEIGHT_JSON = 300     # Max-height (px) for raw JSON viewer

# ─── Daily Trade Graph ───
GRAPH_TEXT_LABEL_THRESHOLD = 60     # Hide per-bar text labels when deal count exceeds this
GRAPH_CUM_LABEL_THRESHOLD = 60     # Hide cumulative line labels when deal count exceeds this

# ─── Order Execution ───
ORDER_COOLDOWN_SECONDS = 1                       # Mandatory sleep after placing an order (lets MT5 update positions)

# ─── Strategy Log ───
STRATEGY_LOG_FILENAME = 'strategy_log.json'     # Log file name inside OUTPUT_DIR
STRATEGY_LOG_MAX_ENTRIES = 200                   # Max log entries kept per symbol

# ─── Active Config (Dashboard ↔ Bot) ───
ACTIVE_CONFIG_FILENAME = 'active_config.json'   # Dashboard writes, bot reads on startup
