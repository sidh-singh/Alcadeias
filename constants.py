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
STRATEGY_HEDGE = 1                  # the live basket target: $ per unit (close when basket profit > STRATEGY_HEDGE x unit;
                                    # used while TARGET_USD_PER_UNIT = 'live', see the design levers below)
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

# ─── Per-section score thresholds (RAW units; NO regime) ───
# Each decision SECTION has its OWN timeframe set (see *_SCORE_WEIGHTS below); its score is the RAW
# weighted sum, range ±(2*Σ|weight|). These thresholds are in those RAW units, so they move WITH the
# section's timeframes -- change a section's TFs and re-check its threshold. (Raw rescale 2026-10-30;
# values below are the raw equivalents of the previous normalised 6/6/12 for the current config, so
# behaviour is unchanged.) All tunable on demo. (The regime/tide was fully REMOVED 2026-10-27. This
# h6/variant-B pair books profit via the +$unit target, so there is no BOOK score / threshold here.)
ENTRY_S = 2                         # |open_score| to OPEN. OPEN range is ±4 (H1+M15, w1+w1); +2 = one
                                    # timeframe fully aligned (or both half). BUY open_score >= +2 / SELL <= -2.
ENTRY_AGREE_S = 2                    # agreement gate (2026-10-29; raised 0->2 2026-11-13 anti-vibration): FORCE-CLOSE must FIRMLY agree
                                    # the open -- BUY also needs fc_score >= +ENTRY_AGREE_S, SELL needs
                                    # fc_score <= -ENTRY_AGREE_S. now 2 = the M15 force-close score must FULLY agree (both slopes on-side) so a fresh entry sits clear of the close trigger; 0 was "merely not
                                    # be against it"; raise to demand stronger agreement. Stops the
                                    # open-then-instant-force-close vibration -- the bot WAITS until the
                                    # OPEN and FORCE-CLOSE scores agree.
LADDER_S = 2                        # DCA ladder add blocked once OPEN score is this far adverse
                                    # (BUY add needs open_score > -2; SELL add needs < +2)
FORCE_CLOSE_S = 1                  # force-close when the FORCE-CLOSE score is this far AGAINST the
                                    # basket. FORCE-CLOSE range is ±2 (M15 only). BUY close fc_score
                                    # <= -1; SELL fc_score >= +1. (Unchanged by the raw rescale.)

# ─── Per-section timeframe weights (config-driven; 2026-10-30) ───
# Each decision SECTION builds its own weighted slope score from its OWN timeframes. TO TUNE:
# add/remove a timeframe by editing its dict below -- 'TF': weight  (TF is the short key
# M5 / M15 / H1 / H4 / D1; weight is any number). The score is the RAW weighted sum of the latest-pivot
# RSI + MACD slope signs (see Strategy._weighted_score), range ±(2*Σ|weight|); the thresholds above are
# in those raw units + the dashboard gauge is scaled to ±(2*Σ|weight|) per section, so both move with
# the timeframes -- change a section's TFs and re-check its threshold.
#   OPEN        -> fresh entry + the DCA ladder-add gate.
#   FORCE_CLOSE -> force-close (kept at the original 4/3/2/1 set, so its score == the old exit_score).
# (This h6/variant-B pair books profit via the +$unit target, so there is NO BOOK section here.)
OPEN_SCORE_WEIGHTS        = {'H1': 1, 'M15': 1}                       # 2026-11-12: H1 + M15 (was H4 + M5)
FORCE_CLOSE_SCORE_WEIGHTS = {'M15': 1}  # 2026-11-12: M15-only reversal (was M15/H1/H4/D1)

# ─── Slope fetch list (auto-derived) ───
# Every timeframe named in ANY section above is fetched for slopes (app.py reads SLOPE_TIMEFRAMES),
# so adding a TF to a section dict is enough -- it is fetched + shown on the dashboard automatically.
# Order-preserving union, mapped short-key -> 'TIMEFRAME_<key>'.
# NOTE: D1 is not fetched elsewhere, so including it costs +1 MT5 rates call per loop; M5/M15/H1/H4
# are already fetched for the RSI ladder, so they are free.
# This list is derived from the live weights above. A design block at the END of this file may change
# the weights afterwards; app.py therefore adds, on every poll, each timeframe the strategy reads votes
# from (Strategy.slope_timeframes(): the section weights as they finally are, plus the tier timeframes of
# a 'macd_turn' ladder), so a stale list here never drops a timeframe.
SLOPE_TIMEFRAMES = ['TIMEFRAME_' + _tf for _tf in dict.fromkeys(
    _k for _d in (OPEN_SCORE_WEIGHTS, FORCE_CLOSE_SCORE_WEIGHTS) for _k in _d
)]
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
# Profit-protect fires only when basket profit exceeds this USD buffer. Set it to
# cover the round-trip spread + commission so a protect-close never locks a net loss.
# 0.0 = protect at any profit > 0 (TUNE from the backtest / your broker costs).
PROFIT_PROTECT_MIN_USD = 0.0


# ─── Risk Management ───
RISK_REWARD_RATIO = [1, 1]          # [risk, reward] multiplier for auto SL/TP calculation

# ─── File System / Output ───
OUTPUT_DIR = r'C:\Alcadeias\demo_hedging_btcusd6'                    # Root directory for JSON data files
DAILY_TRADE_SUBDIR = 'daily_trade'              # Sub-folder for per-symbol daily trade logs
HISTORICAL_SUMMARY_DAYS = 3650                  # Days of deal history (≈ 10 years)
HISTORICAL_SUMMARY_FILENAME = 'historical_summary.json'

# ─── Dashboard ───
DASHBOARD_REFRESH_INTERVAL = 5000   # Auto-refresh interval in milliseconds
DASHBOARD_HOST = '0.0.0.0'
DASHBOARD_PORT = 8071
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

# ─── Design levers (demo branches, 2026-11-15) ───
# Every lever below defaults to the live bot v3.9.2 exactly. A demo branch sets its design in a block at
# the END of this file (one commented example per design there). Their meaning is the backtester's
# (backtesting/engine/kernels.py on backtest_hedging), which the demo forward test is meant to reproduce:
#   * every exit / add is decided on the poll's forming-bar votes, as live;
#   * the trend and the volatility unit are read on the last CLOSED bar of their timeframe;
#   * a basket's target, stop and add gap are fixed when it opens and kept for its life (persisted in
#     OUTPUT_DIR/state, so a restart keeps them);
#   * in a basket the stop is checked first, then the target, then the force-close, then the ladder.
DESIGN_NAME = 'live'                 # a label only (startup print, dashboard JSON, state file)
STRATEGY = 'basket'                  # 'basket' = this bot's logic with the levers below; 'turtle' = the Turtle
                                     # (turtle.py, the TURTLE_* constants below; BTC 6/7), the levers then unused
FORCE_CLOSE_ENABLED = True           # False: the M15 force-close never fires; the M15 votes (FORCE_CLOSE_SCORE_WEIGHTS)
                                     # still feed the ENTRY_AGREE_S agreement gate, so keep that dict as it is
TREND_TF = None                      # 'H1': a fresh entry only if sign(MACD signal line of the last CLOSED H1 bar)
                                     # equals the side; a signal of exactly 0 (or NaN) blocks both sides. None = off
VOL_TF = None                        # 'H1': the volatility unit = EWMA(alpha=1/VOL_LEN, adjust=False) of |delta close|
                                     # of the CLOSED bars (bid closes), read when a basket opens. None = off
VOL_LEN = 24
TARGET_USD_PER_UNIT = 'live'         # 'live' = STRATEGY_HEDGE $ per unit (the live $1 x unit target, strict >);
                                     # a number = that many $ per unit; None = no $ target
STOP_LOSS_USD_PER_UNIT = None        # None = no $ stop; a number = close the basket at profit <= -(that x unit)
TARGET_VOL = 0.0                     # > 0 (needs VOL_TF): target per unit (USD) = TARGET_VOL x unit x contract_size x mtqty,
                                     # fixed at the open; replaces TARGET_USD_PER_UNIT
STOP_VOL = 0.0                       # > 0 (needs VOL_TF): stop per unit, the same way; replaces STOP_LOSS_USD_PER_UNIT
VOL_CAP_USD_PER_UNIT = 0.0           # > 0 (needs VOL_TF): the unit is capped at cap / (contract_size x mtqty) price units
                                     # (USD per 0.01 lot: gold $12 = a $12 move, BTC $12 = a $1,200 move); caps target, stop, gap
LOSS_COOLDOWN_S = 0                  # > 0: after a basket that closed with a net loss (realised P/L from the deal
                                     # history) the next entry waits this long INSTEAD of REENTRY_COOLDOWN_SECONDS,
                                     # counted from the close decision (wall clock, through weekends)
MAX_ADDS = 99                        # ladder adds = min(len(LADDER_TFS), MAX_ADDS); 0 = no ladder
LADDER_TRIGGER = 'rsi_level'         # 'rsi_level' (live): the tier timeframe's forming-bar RSI is at/beyond
                                     #   RSI_OVERSOLD (buy) / RSI_OVERBOUGHT (sell);
                                     # 'macd_turn': the tier timeframe's MACD vote was not with the basket on some
                                     #   poll since the last fill (armed) and now is
LADDER_TFS = ['M1', 'M5', 'M15', 'H1', 'H4']   # tier timeframe of add n = LADDER_TFS[n-1]
LADDER_GAP_VOL = 0.0                 # > 0 (needs VOL_TF): an add also needs the price >= LADDER_GAP_VOL x unit (price
                                     # units, fixed at the open) worse than the last fill (buy: last fill - ask)
LADDER_MULTIPLIERS = None            # None = the live Fibonacci sizes; a list = units per position (index n for add n;
                                     # index 0 is the entry and must be 1; padded with its last value)
# Contract size (units of the asset per 1.00 lot) when the terminal's symbol_info() has none: the volatility
# levers convert price moves to USD with contract_size x mtqty (gold 100 x 0.01 = $1, BTC 1 x 0.01 = $0.01).
CONTRACT_SIZE_FALLBACK = {'XAU': 100.0, 'BTC': 1.0}
STATE_SUBDIR = 'state'               # OUTPUT_DIR/state/<symbol>_state.json: the open basket's fixed distances, its
                                     # ladder arming and the loss pause (a sub-folder: the dashboard lists every
                                     # top-level JSON of OUTPUT_DIR as a symbol)

# ─── The Turtle (STRATEGY = 'turtle'; the rules: turtle.py) ───
# The final ten's BTC Turtles, "Turtle + bot votes" (System 1) and "Turtle System 2 + bot votes", with the
# backtest's parameters (backtesting/research/external.py turtle() on backtest_hedging). Read only with
# STRATEGY = 'turtle'. Levels from UTC D1 bars (Exness MT5 server time is UTC); entries need the bot's M15
# votes on CLOSED bars to agree; one stop for all legs, held by the bot (checked every poll, every leg closed
# at market), no broker SL / TP. As in the backtest: no trading window (symbols.json 'brake' still stops new
# entries), no re-entry cooldown beyond the next M1 bar, no target. The book (N at the entry, unit, stop, the
# armed orders) is kept in OUTPUT_DIR/state/<symbol>_turtle.json and rebuilt from the positions without it.
TURTLE_SYSTEM = 2                    # 1: 20-day breakout, skipped after a winning breakout (then the 55-day
                                     #    failsafe), 10-day exit; 2: 55-day breakout, 20-day exit
TURTLE_N_LEN = 20                    # N = Wilder's RMA of the daily true range over this many days
TURTLE_STOP_N = 2.0                  # the stop: this many N from the newest fill, or the exit channel if tighter
TURTLE_ADD_N = 0.5                   # one more leg each time the price is this many N beyond the previous fill
TURTLE_MAX_LEGS = 4                  # legs per trade, the entry included; each leg = the unit x 0.01 lot
TURTLE_TICK = 0.01                   # entry levels: channel high + this / channel low - this
TURTLE_VOTE_TF = 'M15'               # the bot's votes on the CLOSED bars of this timeframe gate the entries
TURTLE_VOTE_BARS = 1000              # closed bars read for the votes
TURTLE_D1_BARS = 1000                # closed D1 bars read for N, the channels and the System 1 filter (1000: the
                                     # backtest's levels to the cent)
TURTLE_MIN_D1_BARS = 300             # fewer closed D1 bars from the terminal: no trading (N not settled yet)

# ── demo deployment (this branch only) ──
DEMO_BRANCH = 'demo_hedging_btcusd6'                     # demo account only: live mode is refused
MAGIC = 26126                              # this bot's orders and positions carry this magic number
ORDER_COMMENT = None                 # None -> DEMO_BRANCH cut to 31 characters (the MT5 limit)
VIRTUAL_START_BALANCE = 2000.0       # units are sized from this + this bot's own closed P/L (profit + swap +
VIRTUAL_START_DATE = '2026-11-16'    #   commission of the deals with its MAGIC) since this UTC date;
                                     #   None = the account balance (as live)

# ─── Design examples ───
# Copy ONE block below to the very end of this file and remove the leading '# '. Everything not listed
# stays at the live value above. Effective parameters from the backtester's top3_v4 designs; the two
# Turtles are the final ten's rows (the TURTLE_* values above are theirs).
#
# ── XAU V3-lite ──
# DESIGN_NAME = 'xau_v3lite'
# OPEN_SCORE_WEIGHTS = {'H1': 1}
# ENTRY_AGREE_S = 2
# FORCE_CLOSE_ENABLED = False
# TREND_TF = 'H1'
# VOL_TF = 'H1'
# VOL_LEN = 24
# TARGET_USD_PER_UNIT = None
# STOP_LOSS_USD_PER_UNIT = None
# TARGET_VOL = 8.0
# STOP_VOL = 8.0
# VOL_CAP_USD_PER_UNIT = 0.0
# LOSS_COOLDOWN_S = 43200
# MAX_ADDS = 0
#
# ── XAU Top 2 ──
# DESIGN_NAME = 'xau_top2'
# OPEN_SCORE_WEIGHTS = {'H1': 1}
# ENTRY_AGREE_S = 0
# FORCE_CLOSE_ENABLED = False
# TREND_TF = 'H1'
# VOL_TF = 'H1'
# VOL_LEN = 24
# TARGET_USD_PER_UNIT = None
# STOP_LOSS_USD_PER_UNIT = None
# TARGET_VOL = 8.0
# STOP_VOL = 4.0
# VOL_CAP_USD_PER_UNIT = 12.0
# LOSS_COOLDOWN_S = 43200
# MAX_ADDS = 0
#
# ── XAU Top 1 ──
# DESIGN_NAME = 'xau_top1'
# OPEN_SCORE_WEIGHTS = {'H1': 1}
# ENTRY_AGREE_S = 0
# FORCE_CLOSE_ENABLED = False
# TREND_TF = 'H1'
# VOL_TF = 'H1'
# VOL_LEN = 24
# TARGET_USD_PER_UNIT = None
# STOP_LOSS_USD_PER_UNIT = None
# TARGET_VOL = 10.0
# STOP_VOL = 8.0
# VOL_CAP_USD_PER_UNIT = 0.0
# LOSS_COOLDOWN_S = 14400
# MAX_ADDS = 1
# LADDER_TRIGGER = 'macd_turn'
# LADDER_TFS = ['M5', 'M15', 'H1', 'H1', 'H1']
# LADDER_GAP_VOL = 1.0
# LADDER_MULTIPLIERS = [1, 1, 1, 1]
#
# ── BTC Top 2 ──
# DESIGN_NAME = 'btc_top2'
# OPEN_SCORE_WEIGHTS = {'H1': 1}
# ENTRY_AGREE_S = 0
# FORCE_CLOSE_ENABLED = False
# TREND_TF = 'H1'
# VOL_TF = 'H1'
# VOL_LEN = 24
# TARGET_USD_PER_UNIT = None
# STOP_LOSS_USD_PER_UNIT = None
# TARGET_VOL = 10.0
# STOP_VOL = 8.0
# VOL_CAP_USD_PER_UNIT = 12.0
# LOSS_COOLDOWN_S = 14400
# MAX_ADDS = 0
#
# ── BTC Turtle System 2 + bot votes ──
# DESIGN_NAME = 'btc_turtle_s2'
# STRATEGY = 'turtle'
# TURTLE_SYSTEM = 2
#
# ── BTC Turtle System 1 + bot votes ──
# DESIGN_NAME = 'btc_turtle_s1'
# STRATEGY = 'turtle'
# TURTLE_SYSTEM = 1

# ─── Design of this branch (demo_hedging_btcusd6): BTC Turtle System 2 + bot votes ───
# The example block 'BTC Turtle System 2 + bot votes' above, uncommented. Everything not set here stays at the live value.
DESIGN_NAME = 'btc_turtle_s2'
STRATEGY = 'turtle'
TURTLE_SYSTEM = 2
VIRTUAL_START_DATE = '2026-11-15'    # the demo forward test's virtual $2,000 counts this bot's deals from this UTC day
