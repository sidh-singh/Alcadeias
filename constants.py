"""
Alcadeias Trading Bot — Central Configuration
==============================================
All tuneable parameters in one place.
Edit this file to adjust strategy, indicator, dashboard, or system behaviour.
"""

# ─── SHA Signal Indicator ───
SHA_LENGTH = 20                      # Smoothing length for signal SHA (pre & post)
SHA_MA_TYPE = 'RMA'                 # MA type for signal SHA (SMA, EMA, RMA, WMA, HMA …)

# ─── SHA Trend Indicator ───
SHA_TREND_LENGTH = 50               # Smoothing length for trend SHA (pre & post)
SHA_TREND_MA_TYPE = 'RMA'           # MA type for trend SHA

# ─── SHA Gap ───
DEFAULT_GAP_RANGE = [0.001, 0.003]   # Default gap range [min, max] as raw ratio (not ×100)

# ─── SHA Convergence ───
SHA_CONVERGENCE_LOOKBACK = 5         # Bars to measure gap direction
SHA_CLOSE_THRESHOLD = 0.0003        # Gap below this = CLOSE (raw ratio, 0.03%)
SHA_CONVERGENCE_THRESHOLD = 0.0001  # Dead zone for PARALLEL (raw ratio, 0.01%)

# ─── Data Fetching ───
CANDLE_TIMEFRAME = 'TIMEFRAME_M1'   # Timeframe for price data (resolved via mt5 at runtime)
CANDLE_COUNT = 1000                  # Must be large for RMA convergence (~140 warmup + ~640 convergence for RMA(70))
ALLOW_SYNTHETIC_TICK_BAR = True     # Append provisional bar from tick when MT5 bar feed lags

# ─── Market Status ───
MARKET_STATUS_TIMEFRAME = 'TIMEFRAME_M1'   # Timeframe used to check market open/closed
MARKET_LOOKBACK_MINUTES = 3                # Max minutes since last candle → still "open"

# ─── Strategy Parameters ───
STRATEGY_HEDGE = 1                  # Hedge / profit target multiplier
STRATEGY_LOOKBACK = 7               # Number of candles to analyse for signal
STRATEGY_SHA_THRESHOLD = 0          # Min SHA ratio to classify candle as bullish
FIBO_SEQUENCE_LENGTH = 25           # Fibonacci sequence length (first 2 dropped)
FIBO_POWER_DEFAULT = 3              # Default exponent for fibo-based DCA threshold

# ─── RSI Indicator ───
RSI_LENGTH = 14                     # RSI period
RSI_MA_TYPE = 'RMA'                 # MA type for RSI smoothing (RMA = Wilder's, matches TradingView default)
RSI_OVERSOLD = 30                   # Oversold threshold (BUY_MORE when RSI <= this)
RSI_OVERBOUGHT = 70                 # Overbought threshold (SELL_MORE when RSI >= this)
RSI_DCA_MAX_POSITIONS = 1           # Max additional DCA positions allowed via RSI signal

# ─── RSI Multi-Timeframe Entry Filter ───
RSI_MTF_TIMEFRAMES = ['TIMEFRAME_M1', 'TIMEFRAME_M5', 'TIMEFRAME_M15']
RSI_MTF_OVERSOLD = 30               # Block BUY entry when ANY MTF RSI <= this
RSI_MTF_OVERBOUGHT = 70             # Block SELL entry when ANY MTF RSI >= this

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
