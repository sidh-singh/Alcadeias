"""
Alcadeias Trading Bot — Central Configuration
==============================================
All tuneable parameters in one place.
Edit this file to adjust strategy, indicator, dashboard, or system behaviour.
"""

# ─── SHA Indicator Parameters ───
SHA_SMOOTH_LENGTH = 2               # Pre-smooth length for SHA v3
SHA_SMOOTH_MA_TYPE = 'RMA'          # MA type for pre-smoothing  (SMA, EMA, RMA, WMA, HMA …)
SHA_AFTER_SMOOTH_LENGTH = 2         # Post-HA smooth length
SHA_AFTER_SMOOTH_MA_TYPE = 'RMA'    # MA type for post-HA smoothing

# ─── Data Fetching ───
CANDLE_TIMEFRAME = 'TIMEFRAME_M1'   # Timeframe for price data (resolved via mt5 at runtime)
CANDLE_COUNT = 50                   # Number of candles to fetch per cycle

# ─── Market Status ───
MARKET_STATUS_TIMEFRAME = 'TIMEFRAME_M5'   # Timeframe used to check market open/closed
MARKET_LOOKBACK_MINUTES = 15               # Max minutes since last candle → still "open"

# ─── Strategy Parameters ───
STRATEGY_HEDGE = 1                  # Hedge / profit target multiplier
STRATEGY_LOOKBACK = 7               # Number of candles to analyse for signal
STRATEGY_SHA_THRESHOLD = 0          # Min SHA ratio to classify candle as bullish
FIBO_SEQUENCE_LENGTH = 25           # Fibonacci sequence length (first 2 dropped)

# ─── Risk Management ───
# Strategy manages exits — SL/TP are set far away so the broker accepts the order
# but they never realistically trigger.  0.95 = 95% of price distance.
SL_TP_DISTANCE_PCT = 0.95           # Fraction of price used for dummy SL/TP

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
