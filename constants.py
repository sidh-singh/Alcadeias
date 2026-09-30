"""
Alcadeias Trading Bot — Central Configuration
==============================================
All tuneable parameters in one place.
Edit this file to adjust strategy, indicator, dashboard, or system behaviour.
"""

# ─── SHA Signal Indicator ───
# Computed directly on 15-minute candles (see CANDLE_TIMEFRAME). Length 10 TEMA on
# M15 is the target signal; previously this was emulated on M1 with length 600
# (10×60) for H1; switching to M15 reduces historical download size while keeping
# smoothing lengths unchanged.
SHA_LENGTH = 10                     # Smoothing length for signal SHA (pre & post)
SHA_MA_TYPE = 'TEMA'                # MA type for signal SHA (SMA, EMA, RMA, WMA, HMA …)

# ─── SHA Trend Indicator ───
# Length 20 DEMA on M15 (previously emulated on M1 as length 1200 = 20×60 for H1).
SHA_TREND_LENGTH = 20               # Smoothing length for trend SHA (pre & post)
SHA_TREND_MA_TYPE = 'DEMA'          # MA type for trend SHA

# ─── Data Fetching ───
# SHA is now computed on H1 candles directly, so only a few hundred bars are
# needed (vs thousands of M1 bars before). The SHA smooths OHLC twice and
# TEMA/DEMA chain 2-3 passes, so with length 10/20 the NaN warmup is:
#   signal SHA TEMA(10): first valid ≈ bar 54
#   trend  SHA DEMA(20): first valid ≈ bar 76
# Both converge to <0.001% error by ~150 bars. 300 gives a wide safety margin
# (~12 days of H1) while keeping each iteration light.
CANDLE_TIMEFRAME = 'TIMEFRAME_M15'   # Timeframe for SHA price data (resolved via mt5 at runtime)
CANDLE_COUNT = 300
ALLOW_SYNTHETIC_TICK_BAR = True     # Append provisional bar from tick when MT5 bar feed lags (M1 only)

# ─── Market Status ───
MARKET_STATUS_TIMEFRAME = 'TIMEFRAME_M1'   # Timeframe used to check market open/closed
MARKET_LOOKBACK_MINUTES = 3                # Max minutes since last candle → still "open"

# ─── Strategy Parameters ───
STRATEGY_HEDGE = 1                  # Hedge / profit target multiplier
STRATEGY_LOOKBACK = 7               # Number of candles to analyse for signal
STRATEGY_SHA_THRESHOLD = 0          # Min SHA ratio to classify candle as bullish
FIBO_SEQUENCE_LENGTH = 25           # Fibonacci sequence length (first 2 dropped)

# ─── RSI Indicator ───
RSI_LENGTH = 14                     # RSI period
RSI_MA_TYPE = 'RMA'                 # MA type for RSI smoothing (RMA = Wilder's, matches TradingView default)
# RSI(14) converges within a few hundred bars, so multi-timeframe RSI fetches use
# this smaller count instead of the large SHA CANDLE_COUNT. This avoids pulling
# years of history on high timeframes (e.g. 8000 H6 bars ≈ 5.5 years) every loop.
RSI_CANDLE_COUNT = 500
RSI_OVERSOLD = 35                   # Oversold threshold (BUY_MORE when RSI <= this)
RSI_OVERBOUGHT = 65                 # Overbought threshold (SELL_MORE when RSI >= this)
RSI_DCA_MAX_POSITIONS = 1           # Max additional DCA positions allowed via RSI signal

# ─── RSI Multi-Timeframe Entry Filter ───
RSI_MTF_TIMEFRAMES = ['TIMEFRAME_M1', 'TIMEFRAME_M5', 'TIMEFRAME_M15', 'TIMEFRAME_M30']
RSI_MTF_OVERSOLD = 35               # Block BUY entry when ANY MTF RSI <= this
RSI_MTF_OVERBOUGHT = 65             # Block SELL entry when ANY MTF RSI >= this

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

# ─── Regime Entry Filter (FRESH-ENTRY gate ONLY) ───
# Studies the current price *regime* to decide whether a FRESH basket may open.
# It can ONLY turn a fresh BUY/SELL into DO_NOTHING — it NEVER touches an open
# basket: the DCA ladder, RSI adds, +$ profit close and H6 forced close all
# behave exactly as before. Computed on the M15 `source_df` already fetched for
# SHA (ATR is an intermediate value of ADX), so it adds NO new MT5 fetches, and
# it is fully STATELESS (recomputed each loop — no latch to reset, unlike the
# rolled-back v1.1.0 HTF protection).
#
# Behaviour matrix:
#   REGIME_FILTER_ENABLED = False                         → byte-identical to before.
#   REGIME_FILTER_ENABLED = True,  REGIME_FILTER_SHADOW = True  → trades identically
#       to now, but LOGS every fresh entry it *would* have blocked (measurement).
#   REGIME_FILTER_ENABLED = True,  REGIME_FILTER_SHADOW = False → actually blocks.
REGIME_FILTER_ENABLED = False       # Master switch. False = pre-filter behaviour.
REGIME_FILTER_SHADOW = True         # True = compute + log only, do NOT block trades.

# ADX trend-strength gate — mean-reversion works in ranges and dies in trends, so
# block FRESH entries when ADX says a strong trend is running (inverted ADX use).
REGIME_ADX_ENABLED = True
REGIME_ADX_PERIOD = 14              # ADX/ATR period on M15 (Wilder / TradingView ta.adx)
REGIME_ADX_MAX = 25.0              # Block fresh entry when ADX >= this
REGIME_ADX_USE_DI = False          # True = block only the counter-trend side via +DI/-DI

# ATR spike guard — catches the fast 1-2 candle move ADX is too slow to see. A
# spike anywhere in the last REGIME_SPIKE_WINDOW M15 bars blocks fresh entries
# (self-clearing: recomputed from data each loop, so no cooldown state is stored).
REGIME_ATR_ENABLED = True
REGIME_SPIKE_K1 = 2.2             # 1-bar true range     >= K1 * prior ATR → spike
REGIME_SPIKE_K2 = 3.2             # 2-bar true range sum >= K2 * prior ATR → spike
REGIME_SPIKE_WINDOW = 2           # Block if a spike occurred in the last N M15 bars
REGIME_SPIKE_USE_DIR = False       # True = block only the wrong (against-spike) side

# RSI-slope confirm (PHASE 2 — off by default). Block a fresh entry taken against
# a fast-moving RSI even before it reaches the static 35/65 band.
REGIME_RSI_SLOPE_ENABLED = False
REGIME_RSI_SLOPE_TIMEFRAMES = ['TIMEFRAME_M1', 'TIMEFRAME_M5']
REGIME_RSI_SLOPE_BARS = 3          # Lookback bars for the RSI slope
REGIME_RSI_SLOPE_MIN = 8.0        # Block entry against an RSI move >= this over BARS

# Optional per-symbol overrides may be placed in symbols.json under a "regime"
# key on the symbol entry, e.g.:  "regime": {"adx_max": 28, "spike_k1": 2.2,
# "spike_k2": 3.2, "spike_window": 2}. Missing keys fall back to the values above.

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