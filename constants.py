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

# ─── Regime ("tide") + score gates — weighted-score + regime redesign ───
# Per big-TF (D1 / H4) bias from LEVEL (not the pivot slope): BULL when RSI is above
# REGIME_RSI_BULL AND the MACD line > 0; BEAR when RSI is below REGIME_RSI_BEAR AND the
# MACD line < 0; else NEUTRAL. D1 leads / H4 confirms (see Strategy._regime_combine and
# docs/weighted-regime-redesign.md §4). The regime now governs ONLY the EXITS -- the force-close
# (Step 4) and the variant-A profit-book (Step 6). OPENING -- both fresh entry AND the DCA ladder
# adds -- uses the weighted slope score ALONE (regime removed from both 2026-10-27, as the lagging
# level-regime vetoed valid slope-based opens). Tunable on demo.
REGIME_RSI_BULL = 55                # RSI strictly above this (and MACD line > 0) -> BULL
REGIME_RSI_BEAR = 45                # RSI strictly below this (and MACD line < 0) -> BEAR
# DCA ladder gate (score-only; regime removed from ladder adds 2026-10-27, like entry): an RSI-
# ladder add fires only while the weighted slope score is not this far adverse -- a BUY add is
# blocked when score <= -LADDER_S, a SELL add when score >= +LADDER_S. (Still catches the
# "average down into a trend" case; the regime-aware force-close keeps that protection.)
LADDER_S = 6                        # adverse slope-score magnitude that blocks a ladder add
# Force-close (Step 4): a basket force-closes when the weighted slope score has moved this far
# AGAINST it, scaled by the tide -- with the tide give a winner room (deep reversal needed);
# against the tide cut fast. A BUY closes at score <= -X; a SELL at score >= +X, where X is:
FORCE_CLOSE_S_WITH = 12             # tide WITH the position (BULL for a long / BEAR for a short)
FORCE_CLOSE_S_NEUTRAL = 8           # no clear tide
FORCE_CLOSE_S_AGAINST = 4           # tide AGAINST the position (cut fast)
# Fresh entry: OPEN from the weighted slope score ALONE (regime removed from entry 2026-10-27 -
# the lagging level-regime vetoed valid slope entries, e.g. score +12 with D1/H4/H1 rising but a
# BEAR tide). A BUY opens when score >= ENTRY_S, a SELL when score <= -ENTRY_S. (Previously two
# regime-gated thresholds ENTRY_S_WITH/ENTRY_S_NEUTRAL = 4/6; collapsed to one - no entry tide now.)
ENTRY_S = 6                         # |weighted slope score| needed to open a position (lower = more eager)
# Profit-book (Step 6, variant A only): once a basket is in profit by at least the buffer, book
# when the score has reversed this far against it, scaled by the tide -- let a with-trend winner
# run (a bigger reversal is needed to book), grab a counter-trend winner fast. A BUY books at
# score <= -X; a SELL at score >= +X, where X is:
BOOK_S_WITH = 6                    # tide WITH the position (let the winner run)
BOOK_S_NEUTRAL = 4                 # no clear tide
BOOK_S_AGAINST = 2                 # tide AGAINST the position (grab it fast)

# ─── Slope Engine (4H + 1H + 15M entry; D1 regime for the force-close EXIT) ───
# ENTRY (4H primary / 1H confirm / 15M trigger) uses ONLY 4H/1H/15M latest-pivot slopes -
# D1 does NOT enter the entry decision. D1 (_exp) is computed only to modulate the
# force-close EXIT: when the Daily slope is actively AGAINST an open basket (both D1 signs
# oppose it) the force-close turns SENSITIVE (M15-both reversal alone); otherwise it keeps
# the normal 4H>=1 / 1H-both / 15M-both close. See docs/h4h1m15-decision-table.md.
# NOTE: unlike 15M, D1 is not fetched elsewhere, so adding it = +1 MT5 rates call per loop.
SLOPE_TIMEFRAMES = ['TIMEFRAME_M15', 'TIMEFRAME_H1', 'TIMEFRAME_H4', 'TIMEFRAME_D1']  # 15M/1H/4H entry + D1 exit-regime
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
