"""
Numba kernels for the fast engine.

This file re-implements, as tight loops, exactly what one iteration of the live loop
(``app.py: MT5TradingBot.process_symbol``) computes and decides:

* ``indicator_arrays`` / ``pivot_arrays`` -- the closed-bar RSI / MACD values and the
  pivot bookkeeping of ``indicator.py`` (``calculate_rsi``, ``calculate_macd``,
  ``latest_pivot_slope``), pre-computed once per timeframe.
* ``run_kernel`` -- the poll loop: at every poll it takes the latest tick, updates the
  *forming* bar of every timeframe with that price (the live bot reads its indicators on
  the still-forming bar), derives the slope signs and section scores, applies the rules
  of ``strategy.py`` and simulates the MT5 account.

Nothing here looks ahead: a poll at time T only reads rows with ``t_ms <= T`` and bars
that closed before the bar holding that row. ``tests/test_engine_parity.py`` checks the
whole thing, decision by decision, against the real live code.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

# ── integer config slots ──
CI_START_MS = 0
CI_END_MS = 1
CI_POLL_MS = 2
CI_LATENCY_MS = 3
CI_OPEN_DELAY_MS = 4
CI_ADD_DELAY_MS = 5
CI_COOLDOWN_MS = 6
CI_LIVENESS_MS = 7
CI_UNIT_MAX = 8
CI_FIXED_UNITS = 9
CI_LOOKBACK = 10
CI_WIDTH = 11
CI_WINDOW_ENABLED = 12
CI_WIN_START = 13
CI_WIN_END = 14
CI_BRAKE = 15
CI_BOOK_ENABLED = 16
CI_GREY_OPEN = 17
CI_GREY_BOOK = 18
CI_GREY_FC = 19
CI_SLOPE_CLOSED = 20
CI_LADDER_CLOSED = 21
CI_ALLOW_LONG = 22
CI_ALLOW_SHORT = 23
CI_MIN_HOLD_MS = 24
CI_FC_CONFIRM_MS = 25
CI_ENTRY_CONFIRM_MS = 26
CI_N_TIERS = 27
CI_REC_MS = 28
CI_FC_ENABLED = 29
CI_TARGET_ON = 30
CI_SL_ON = 31
CI_HOURS_ON = 32
CI_LADDER_INTERVAL_MS = 33
CI_MAX_HOLD_MS = 34
CI_TARGET_PER_LOT = 35
CI_REOPEN_DAILY_MS = 36
CI_REOPEN_WEEKLY_MS = 37
CI_RSI_LEN = 38
CI_MACD_FAST = 39
CI_MACD_SLOW = 40
CI_MACD_SIGNAL = 41
CI_HOLE_MS = 42            # a silence this long is a hole in the tick history (0 = off)
CI_HOLE_QUARANTINE_MS = 43
CI_HOLE_UNTIL0 = 44        # entries blocked until this time because a hole ended shortly before the start
CI_JITTER_MS = 45          # each loop pass takes up to this much longer, drawn at random (0 = fixed period)
CI_JITTER_SEED = 46
CI_REOPEN_UNTIL0 = 47      # the broker is still in close-only mode until this time when the run starts
CI_N = 48

# ── float config slots ──
CF_BALANCE = 0
CF_LEVERAGE = 1
CF_CONTRACT = 2
CF_MTQTY = 3
CF_STEP_UP = 4
CF_ENTRY_S = 5
CF_ENTRY_AGREE_S = 6
CF_LADDER_S = 7
CF_FORCE_CLOSE_S = 8
CF_BOOK_S = 9
CF_TARGET = 10
CF_PROTECT = 11
CF_RSI_OS = 12
CF_RSI_OB = 13
CF_SPREAD_MULT = 14
CF_EXTRA_SPREAD = 15
CF_SLIPPAGE = 16
CF_COMMISSION = 17
CF_STOP_OUT = 18
CF_SL = 19
CF_LADDER_GAP = 20
CF_RSI_ALPHA = 21
CF_MACD_AF = 22
CF_MACD_AS = 23
CF_MACD_ASG = 24
CF_N = 25

# ── fill log columns ──
F_T = 0            # decision time (poll), ms
F_FILL_T = 1       # time of the quote the fill used, ms
F_ACTION = 2       # 1 open, 2 ladder add, 3 close
F_SIDE = 3         # +1 long, -1 short
F_LOTS = 4
F_PRICE = 5
F_PROFIT = 6       # realised P/L of this position (closes only)
F_BALANCE = 7      # balance after the fill
F_BASKET = 8
F_REASON = 9
F_UNITS = 10
F_OPEN_SCORE = 11
F_FC_SCORE = 12
F_BOOK_SCORE = 13
F_NPOS = 14        # open positions after the fill
F_BID = 15         # quote at the decision
F_ASK = 16
F_TIER = 17        # ladder timeframe index for adds, else -1
F_BASKET_PROFIT = 18   # floating basket P/L seen at the decision
F_POS_OPEN_T = 19  # closes: when that position was opened
F_POS_OPEN_PRICE = 20
F_N = 21

ACT_OPEN, ACT_ADD, ACT_CLOSE = 1, 2, 3
R_NONE, R_TARGET, R_BOOK, R_FORCE, R_STOPOUT, R_STOPLOSS, R_END, R_TIME = 0, 1, 2, 3, 4, 5, 6, 7
R_HOLE = 8     # closed at the last quote before a hole in the tick history (data hygiene, not a bot decision)

# ── basket log columns ──
B_ID = 0
B_SIDE = 1
B_OPEN_T = 2
B_CLOSE_T = 3
B_NPOS = 4
B_LOTS = 5
B_PNL = 6
B_REASON = 7
B_UNITS = 8
B_MAE = 9          # worst floating P/L seen while open (USD)
B_MFE = 10         # best floating P/L seen while open (USD)
B_FIRST_PRICE = 11
B_AVG_PRICE = 12
B_CLOSE_PRICE = 13
B_OPEN_SCORE = 14
B_FC_SCORE = 15
B_COMMISSION = 16
B_BALANCE = 17
B_PROFIT_SEEN = 18  # floating P/L at the decision that closed it (before latency / slippage)
B_N = 19

# ── equity sample columns ──
E_T = 0
E_BALANCE = 1
E_EQUITY = 2
E_LOTS = 3         # signed open lots
E_NPOS = 4
E_OPEN_SCORE = 5
E_FC_SCORE = 6
E_BOOK_SCORE = 7
E_UNITS = 8
E_BID = 9
E_ASK = 10
E_N = 11

# ── counters ──
K_POLLS = 0
K_LIVE = 1
K_FLAT_LIVE = 2
K_ENTRIES = 3
K_ADDS = 4
K_CLOSE_TARGET = 5
K_CLOSE_BOOK = 6
K_CLOSE_FORCE = 7
K_CLOSE_STOPOUT = 8
K_CLOSE_SL = 9
K_BLOCK_COOLDOWN = 10    # flat polls where an entry was wanted but the re-entry cooldown blocked it
K_BLOCK_BRAKE = 11       # ... but the trading window / brake blocked it
K_BLOCK_CHOP = 12        # open score wanted in, force-close score vetoed (entry_chop_block)
K_LADDER_GATED = 13      # ladder tier RSI hit but the open-score gate blocked the add
K_MARGIN_REJECT = 14
K_FILL_OVERFLOW = 15
K_BASKET_OVERFLOW = 16
K_LADDER_EXHAUSTED = 17  # polls spent holding a full ladder
K_DEAD_SKIPS = 18        # jumps over periods with no ticks (market closed)
K_TRACE_OVERFLOW = 19
K_BLOCK_CONFIRM = 20
K_BLOCK_HOURS = 21
K_CLOSE_TIME = 22
K_LADDER_SPACED = 23   # ladder tier hit but held back by the experimental spacing levers
K_BLOCK_REOPEN = 24     # an open / add was wanted while the broker was in close-only mode after a break
K_CLOSE_HOLE = 25       # baskets closed at the last quote before a hole in the tick history
K_BLOCK_HOLE = 26       # polls on which an entry was wanted during the quarantine after such a hole
K_BLOCK_CLOSED = 27     # orders (open, add or close) sent after the session's last quote: the server refuses them
K_N = 28

# A session ends with its last quote. For three more minutes the bot still counts the market as
# live (its liveness rule) and may send orders; the server answers "market closed". An order is
# taken to have reached the server in time only within this long after that last quote.
SESSION_CLOSE_GRACE_MS = 1000
SESSION_BREAK_MS = 1_800_000     # a silence this long is a session break (daily break, weekend, holiday, maintenance)

# ── scalar outputs ──
S_FINAL_BALANCE = 0
S_FINAL_EQUITY = 1
S_MAX_EQUITY = 2
S_MIN_EQUITY = 3
S_MAX_DD_ABS = 4         # largest peak-to-trough equity drop, USD
S_MAX_DD_PCT = 5         # same, as % of the running peak
S_MAX_LOTS = 6
S_MAX_NPOS = 7
S_MIN_MARGIN_LEVEL = 8   # %, lowest equity/margin seen (inf if never in the market)
S_OPEN_PROFIT_END = 9
S_MAX_MARGIN = 10
S_BLOWN = 11             # 1 when the account was stopped out
S_LAST_T = 12
S_N_FILLS = 13
S_N_BASKETS = 14
S_N_EQ = 15
S_N_TRACE = 16
S_MAX_FLOAT_LOSS = 17    # most negative floating P/L seen
S_OPEN_NPOS_END = 18
S_OPEN_LOTS_END = 19     # signed
S_N = 20

# ── trace columns (parity testing) ──
T_T = 0
T_SIGNAL = 1       # Signal enum value: 0 none 1 BUY 2 SELL 3 CLOSE_BUY 4 CLOSE_SELL 5 BUY_MORE 6 SELL_MORE
T_OPEN_SCORE = 2
T_FC_SCORE = 3
T_BOOK_SCORE = 4
T_BID = 5
T_ASK = 6
T_NPOS = 7
T_PROFIT = 8
T_UNITS = 9
T_ENTRY_ALLOWED = 10
T_BRAKE = 11
T_RSI0 = 12        # ladder-timeframe RSI values follow (up to 6)
T_N = 18


@njit(cache=True)
def _round2(x):
    """Round to cents, half away from zero (how MT5 reports position profit)."""
    if x >= 0.0:
        return math.floor(x * 100.0 + 0.5) / 100.0
    return -math.floor(-x * 100.0 + 0.5) / 100.0


@njit(cache=True)
def indicator_arrays(C, rsi_len, mf, ms, msig):
    """
    Closed-bar indicator values and recursion states for one timeframe.

    Mirrors ``Indicator.calculate_rsi`` (Wilder RMA, SMA-seeded) and
    ``Indicator.calculate_macd`` (SMA-seeded EMAs). Returns, per bar k (state *after*
    bar k closed): AG, AL (RSI average gain / loss), RSI, EF, ES (fast / slow EMA),
    SG (signal line), HIST (macd - signal).
    """
    n = C.shape[0]
    AG = np.full(n, np.nan)
    AL = np.full(n, np.nan)
    RSI = np.full(n, 100.0)   # live: rsi.fillna(100.0) over the warm-up bars
    EF = np.full(n, np.nan)
    ES = np.full(n, np.nan)
    SG = np.full(n, np.nan)
    HIST = np.full(n, np.nan)

    # RSI
    a = 1.0 / rsi_len
    if n > rsi_len:
        sg = 0.0
        sl = 0.0
        for k in range(1, rsi_len + 1):
            d = C[k] - C[k - 1]
            if d > 0.0:
                sg += d
            elif d < 0.0:
                sl -= d
        AG[rsi_len] = sg / rsi_len
        AL[rsi_len] = sl / rsi_len
        for k in range(rsi_len + 1, n):
            d = C[k] - C[k - 1]
            g = d if d > 0.0 else 0.0
            l = -d if d < 0.0 else 0.0
            AG[k] = a * g + (1.0 - a) * AG[k - 1]
            AL[k] = a * l + (1.0 - a) * AL[k - 1]
        for k in range(rsi_len, n):
            if AL[k] == 0.0:
                RSI[k] = 100.0
            else:
                RSI[k] = 100.0 - (100.0 / (1.0 + AG[k] / AL[k]))

    # MACD
    af = 2.0 / (mf + 1.0)
    as_ = 2.0 / (ms + 1.0)
    asg = 2.0 / (msig + 1.0)
    if n >= mf:
        s = 0.0
        for k in range(mf):
            s += C[k]
        EF[mf - 1] = s / mf
        for k in range(mf, n):
            EF[k] = af * C[k] + (1.0 - af) * EF[k - 1]
    if n >= ms:
        s = 0.0
        for k in range(ms):
            s += C[k]
        ES[ms - 1] = s / ms
        for k in range(ms, n):
            ES[k] = as_ * C[k] + (1.0 - as_) * ES[k - 1]
    first = max(mf, ms) - 1          # first bar with a defined macd line
    seed = first + msig - 1          # signal line is SMA-seeded over msig macd values
    if n > seed:
        s = 0.0
        for k in range(first, seed + 1):
            s += EF[k] - ES[k]
        SG[seed] = s / msig
        for k in range(seed + 1, n):
            SG[k] = asg * (EF[k] - ES[k]) + (1.0 - asg) * SG[k - 1]
        for k in range(seed, n):
            HIST[k] = (EF[k] - ES[k]) - SG[k]
    return AG, AL, RSI, EF, ES, SG, HIST


@njit(cache=True)
def pivot_arrays(v, width, use_band, ob, os_):
    """
    Pivot bookkeeping for ``latest_pivot_slope`` on one closed-bar series ``v``.

    ph_last[j] / pl_last[j]  index of the latest pivot HIGH / LOW at or before bar j whose
                             ``width`` neighbours on both sides are all closed bars (-1 = none).
                             Read as ph_last[K - width - 1] when the forming bar is K, so every
                             neighbour it used had closed by then.
    ch_ok[K] / cl_ok[K]      the newest candidate (bar K - width) is a HIGH / LOW against its
                             closed neighbours; whether it is a pivot *now* still depends on the
                             forming bar's value and is decided at poll time.
    With ``use_band`` a HIGH only counts at v >= ob and a LOW at v <= os_ (RSI OB/OS bands).
    """
    n = v.shape[0]
    ph_last = np.full(n, -1, np.int64)
    pl_last = np.full(n, -1, np.int64)
    ch_ok = np.zeros(n, np.uint8)
    cl_ok = np.zeros(n, np.uint8)
    last_h = -1
    last_l = -1
    for i in range(n):
        if i >= width and i + width < n:
            c = v[i]
            hi = True
            lo = True
            for d in range(1, width + 1):
                x = v[i - d]
                y = v[i + d]
                if not (c > x and c > y):
                    hi = False
                if not (c < x and c < y):
                    lo = False
            if hi and use_band and c < ob:
                hi = False
            if lo and use_band and c > os_:
                lo = False
            if hi:
                last_h = i
            if lo:
                last_l = i
        ph_last[i] = last_h
        pl_last[i] = last_l
    for K in range(n):
        i0 = K - width
        if i0 - width >= 0:
            c = v[i0]
            hi = True
            lo = True
            for d in range(1, width + 1):
                x = v[i0 - d]
                if not (c > x):
                    hi = False
                if not (c < x):
                    lo = False
            for i in range(i0 + 1, K):
                y = v[i]
                if not (c > y):
                    hi = False
                if not (c < y):
                    lo = False
            if hi and use_band and c < ob:
                hi = False
            if lo and use_band and c > os_:
                lo = False
            ch_ok[K] = 1 if hi else 0
            cl_ok[K] = 1 if lo else 0
    return ph_last, pl_last, ch_ok, cl_ok


@njit(cache=True)
def slope_sign(v, ph_last, pl_last, ch_ok, cl_ok, base, K, x, width, lookback, allow_high, allow_low):
    """
    ``latest_pivot_slope(...)['sign']`` for the series (closed bars v[base : base+K], current x).

    Scans from the newest confirmable bar (K - width, whose last right-hand neighbour is
    the current value x) back to K - (lookback - 1) and takes the FIRST pivot found; the
    sign is that of (x - pivot value). 0 when there is no pivot in the window.
    """
    if x != x:
        return 0
    if lookback <= width:
        return 0        # live: latest_i = n-1-width < earliest_i = n-lookback -> nothing is scanned
    i0 = K - width
    if i0 - width >= 0:
        c = v[base + i0]
        if allow_high and ch_ok[base + K] == 1 and c > x:
            return -1
        if allow_low and cl_ok[base + K] == 1 and c < x:
            return 1
    j = K - width - 1
    if j < 0:
        return 0
    lo_idx = K - (lookback - 1)
    if lo_idx < width:
        lo_idx = width
    ih = -1
    il = -1
    if allow_high:
        ih = ph_last[base + j]
        if ih < lo_idx:
            ih = -1
    if allow_low:
        il = pl_last[base + j]
        if il < lo_idx:
            il = -1
    i = ih if ih > il else il
    if i < 0:
        return 0
    d = x - v[base + i]
    if d > 0.0:
        return 1
    if d < 0.0:
        return -1
    return 0


@njit(cache=True)
def forming_rsi(C, AG, AL, o, k, price, rsi_len, alpha):
    """
    ``calculate_rsi(closed bars + [price]).iloc[-1]`` for the forming bar k of one timeframe.

    The live series has k deltas at this point. With fewer than ``rsi_len`` of them the
    Wilder average does not exist yet (live: NaN -> fillna(100)); with exactly ``rsi_len``
    it is the SMA seed, forming delta included; after that it is the usual recursion.
    """
    if k < rsi_len:
        return 100.0
    if k == rsi_len:
        sg = 0.0
        sl = 0.0
        for j in range(1, k):
            d = C[o + j] - C[o + j - 1]
            if d > 0.0:
                sg += d
            elif d < 0.0:
                sl -= d
        d = price - C[o + k - 1]
        if d > 0.0:
            sg += d
        elif d < 0.0:
            sl -= d
        ag = sg / rsi_len
        al = sl / rsi_len
    else:
        d = price - C[o + k - 1]
        g = d if d > 0.0 else 0.0
        l = -d if d < 0.0 else 0.0
        ag = alpha * g + (1.0 - alpha) * AG[o + k - 1]
        al = alpha * l + (1.0 - alpha) * AL[o + k - 1]
    if al == 0.0 or ag != ag or al != al:
        return 100.0
    return 100.0 - (100.0 / (1.0 + ag / al))


@njit(cache=True)
def forming_macd(C, EF, ES, SG, o, k, price, mf, ms, msig, af, as_, asg):
    """
    (histogram, signal line) of ``calculate_macd(closed bars + [price])`` on the forming bar k.
    NaN wherever the live SMA-seeded EMAs have no value yet; exact on the seed bars too.
    """
    if k < mf - 1:
        ef = np.nan
    elif k == mf - 1:
        t = price
        for j in range(k):
            t += C[o + j]
        ef = t / mf
    else:
        ef = af * price + (1.0 - af) * EF[o + k - 1]
    if k < ms - 1:
        es = np.nan
    elif k == ms - 1:
        t = price
        for j in range(k):
            t += C[o + j]
        es = t / ms
    else:
        es = as_ * price + (1.0 - as_) * ES[o + k - 1]
    macd = ef - es
    first = (mf if mf > ms else ms) - 1
    seed = first + msig - 1
    if k < seed:
        sg = np.nan
    elif k == seed:
        t = macd
        for j in range(first, k):
            t += EF[o + j] - ES[o + j]
        sg = t / msig
    else:
        sg = asg * macd + (1.0 - asg) * SG[o + k - 1]
    return macd - sg, sg


@njit(cache=True)
def run_kernel(t_ms, bid, ask,
               off, nb, nwarm, START_ROW,
               C, AG, AL, RSIc, EF, ES, SG, HISTc,
               R_PH, R_PL, R_CH, R_CL, M_PH, M_PL, M_CH, M_CL,
               need_rsi, need_slope,
               w_or, w_om, w_fr, w_fm, w_br, w_bm,
               ladder_tf, ladder_mult, hour_ok,
               ci, cf,
               fills, baskets, eq, trace, counters, scal):
    n = t_ms.shape[0]
    n_tf = off.shape[0]

    start_ms = ci[CI_START_MS]
    end_ms = ci[CI_END_MS]
    poll = ci[CI_POLL_MS]
    latency = ci[CI_LATENCY_MS]
    open_delay = ci[CI_OPEN_DELAY_MS]
    add_delay = ci[CI_ADD_DELAY_MS]
    cooldown = ci[CI_COOLDOWN_MS]
    liveness = ci[CI_LIVENESS_MS]
    unit_max = ci[CI_UNIT_MAX]
    fixed_units = ci[CI_FIXED_UNITS]
    lookback = ci[CI_LOOKBACK]
    width = ci[CI_WIDTH]
    window_enabled = ci[CI_WINDOW_ENABLED] != 0
    win_start = ci[CI_WIN_START]
    win_end = ci[CI_WIN_END]
    brake_manual = ci[CI_BRAKE] != 0
    book_enabled = ci[CI_BOOK_ENABLED] != 0
    grey_open = ci[CI_GREY_OPEN] != 0
    grey_book = ci[CI_GREY_BOOK] != 0
    grey_fc = ci[CI_GREY_FC] != 0
    slope_closed = ci[CI_SLOPE_CLOSED] != 0
    ladder_closed = ci[CI_LADDER_CLOSED] != 0
    allow_long = ci[CI_ALLOW_LONG] != 0
    allow_short = ci[CI_ALLOW_SHORT] != 0
    min_hold = ci[CI_MIN_HOLD_MS]
    fc_confirm = ci[CI_FC_CONFIRM_MS]
    entry_confirm = ci[CI_ENTRY_CONFIRM_MS]
    n_tiers = ci[CI_N_TIERS]
    rec_ms = ci[CI_REC_MS]
    fc_enabled = ci[CI_FC_ENABLED] != 0
    target_on = ci[CI_TARGET_ON] != 0
    sl_on = ci[CI_SL_ON] != 0
    hours_on = ci[CI_HOURS_ON] != 0
    ladder_interval = ci[CI_LADDER_INTERVAL_MS]
    max_hold = ci[CI_MAX_HOLD_MS]
    target_per_lot = ci[CI_TARGET_PER_LOT] != 0
    reopen_daily = ci[CI_REOPEN_DAILY_MS]
    reopen_weekly = ci[CI_REOPEN_WEEKLY_MS]
    hole_ms = ci[CI_HOLE_MS]
    hole_quarantine = ci[CI_HOLE_QUARANTINE_MS]
    jitter_ms = ci[CI_JITTER_MS]
    # a small linear congruential generator: reproducible, and all arithmetic stays inside int64
    rng = (ci[CI_JITTER_SEED] * 2654435761 + 12345) % 2147483648
    rsi_len = ci[CI_RSI_LEN]
    mf = ci[CI_MACD_FAST]
    ms = ci[CI_MACD_SLOW]
    msig = ci[CI_MACD_SIGNAL]

    balance = cf[CF_BALANCE]
    leverage = cf[CF_LEVERAGE]
    contract = cf[CF_CONTRACT]
    mtqty = cf[CF_MTQTY]
    step_up = cf[CF_STEP_UP]
    entry_s = cf[CF_ENTRY_S]
    entry_agree_s = cf[CF_ENTRY_AGREE_S]
    ladder_s = cf[CF_LADDER_S]
    force_close_s = cf[CF_FORCE_CLOSE_S]
    book_s = cf[CF_BOOK_S]
    target = cf[CF_TARGET]
    protect = cf[CF_PROTECT]
    rsi_os = cf[CF_RSI_OS]
    rsi_ob = cf[CF_RSI_OB]
    spread_mult = cf[CF_SPREAD_MULT]
    extra_spread = cf[CF_EXTRA_SPREAD]
    slippage = cf[CF_SLIPPAGE]
    commission = cf[CF_COMMISSION]
    stop_out = cf[CF_STOP_OUT]
    sl_usd = cf[CF_SL]
    ladder_gap = cf[CF_LADDER_GAP]
    a_rsi = cf[CF_RSI_ALPHA]
    a_f = cf[CF_MACD_AF]
    a_s = cf[CF_MACD_AS]
    a_sg = cf[CF_MACD_ASG]

    max_fills = fills.shape[0]
    max_baskets = baskets.shape[0]
    max_eq = eq.shape[0]
    max_trace = trace.shape[0]
    n_fills = 0
    n_baskets = 0
    n_eq = 0
    n_trace = 0

    MAXPOS = 64
    pos_lots = np.zeros(MAXPOS)
    pos_price = np.zeros(MAXPOS)
    pos_t = np.zeros(MAXPOS, np.int64)
    n_pos = 0
    side = 0
    units = 1
    basket_units = 1
    last_close = -(1 << 60)
    basket_open_t = 0
    basket_mae = 0.0
    basket_mfe = 0.0
    basket_open_score = 0.0
    basket_fc_score = 0.0
    basket_comm = 0.0
    basket_first_price = 0.0
    last_fill_price = 0.0
    last_fill_t = 0
    basket_lot_units = 0.0

    K = np.empty(n_tf, np.int64)
    for f in range(n_tf):
        K[f] = nwarm[f]
    rsi_now = np.full(n_tf, 50.0)
    sgn_r = np.zeros(n_tf, np.int64)
    sgn_m = np.zeros(n_tf, np.int64)

    max_equity = balance
    min_equity = balance
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    max_lots = 0.0
    max_npos = 0
    min_margin_level = np.inf
    max_margin = 0.0
    max_float_loss = 0.0
    blown = 0

    open_score = 0.0
    fc_score = 0.0
    book_score = 0.0
    prev_dir = 0
    dir_since = 0
    fc_since = -1
    reopen_until = ci[CI_REOPEN_UNTIL0]
    hole_until = ci[CI_HOLE_UNTIL0] if hole_ms > 0 else -(1 << 60)
    hole_close = 0
    next_rec = start_ms
    ptr = -1
    fptr = -1
    T = start_ms
    profit = 0.0
    equity = balance

    while T < end_ms:
        counters[K_POLLS] += 1
        while ptr + 1 < n and t_ms[ptr + 1] <= T:
            ptr += 1
        if ptr < 0:
            gap = t_ms[0] - T
            steps = gap // poll
            if gap % poll != 0:
                steps += 1
            if steps < 1:
                steps = 1
            T += steps * poll
            counters[K_DEAD_SKIPS] += 1
            continue
        tick_t = t_ms[ptr]
        # market_status: live only when the latest tick (whole seconds, as MT5 reports
        # tick.time) is no older than MARKET_LOOKBACK_MINUTES.
        if T - (tick_t // 1000) * 1000 > liveness:
            if ptr + 1 >= n:
                break
            # After a session break the broker accepts closes but no new orders for a short
            # while ("close-only" mode): ~90 s after gold's daily break, ~3.5 min after the
            # weekly open. Sessions are read off the tick gaps themselves.
            brk = t_ms[ptr + 1] - tick_t
            if brk >= 86_400_000:
                reopen_until = t_ms[ptr + 1] + reopen_weekly
            elif brk >= 1_800_000:
                reopen_until = t_ms[ptr + 1] + reopen_daily
            # A hole in the history of a market that never closes: the basket is closed on this poll
            # at the last quote before the hole, and entries stay out for a while after it.
            if hole_ms > 0 and brk >= hole_ms:
                hole_until = t_ms[ptr + 1] + hole_quarantine
                if n_pos > 0:
                    hole_close = 1
            if hole_close == 0:
                gap = t_ms[ptr + 1] - T
                steps = gap // poll
                if gap % poll != 0:
                    steps += 1
                if steps < 1:
                    steps = 1
                T += steps * poll
                prev_dir = 0
                fc_since = -1
                counters[K_DEAD_SKIPS] += 1
                continue
        counters[K_LIVE] += 1

        # the quote in hand is the last one before a session break and is no longer fresh: the server is shut
        mkt_closed = (ptr + 1 < n) and (t_ms[ptr + 1] - tick_t >= SESSION_BREAK_MS) and (T - tick_t > SESSION_CLOSE_GRACE_MS)

        b = bid[ptr]
        a = b + (ask[ptr] - b) * spread_mult + extra_spread

        # forming-bar index of every timeframe in use
        for f in range(n_tf):
            if need_rsi[f] == 1 or need_slope[f] == 1:
                o = off[f]
                while K[f] + 1 < nb[f] and START_ROW[o + K[f] + 1] <= ptr:
                    K[f] += 1

        # floating P/L exactly as positions_get() would report it
        profit = 0.0
        if n_pos > 0:
            for i in range(n_pos):
                if side > 0:
                    profit += _round2((b - pos_price[i]) * pos_lots[i] * contract)
                else:
                    profit += _round2((pos_price[i] - a) * pos_lots[i] * contract)
            profit = _round2(profit)
            if profit < basket_mae:
                basket_mae = profit
            if profit > basket_mfe:
                basket_mfe = profit
            if profit < max_float_loss:
                max_float_loss = profit
        equity = balance + profit
        if equity > max_equity:
            max_equity = equity
        if equity < min_equity:
            min_equity = equity
        dd = max_equity - equity
        if dd > max_dd_abs:
            max_dd_abs = dd
        if max_equity > 0.0:
            ddp = dd / max_equity * 100.0
            if ddp > max_dd_pct:
                max_dd_pct = ddp

        used_margin = 0.0
        if n_pos > 0:
            for i in range(n_pos):
                used_margin += pos_lots[i] * contract * pos_price[i] / leverage
            if used_margin > max_margin:
                max_margin = used_margin
            ml = equity / used_margin * 100.0 if used_margin > 0.0 else np.inf
            if ml < min_margin_level:
                min_margin_level = ml

        # unit auto-step: re-derived from the balance only while flat
        if n_pos == 0:
            if fixed_units > 0:
                units = fixed_units
            elif step_up > 0.0:
                units = int(math.floor(balance / step_up)) + 1
            else:
                units = 1
            if units > unit_max:
                units = unit_max
            if units < 1:
                units = 1

        # trading window is judged on server time = the latest tick's time
        tsec = tick_t // 1000
        in_window = True
        if window_enabled:
            wd = (tsec // 86400 + 3) % 7
            mow = wd * 1440 + (tsec % 86400) // 60
            if win_start == win_end:
                in_window = True
            elif win_start < win_end:
                in_window = (mow >= win_start) and (mow < win_end)
            else:
                in_window = (mow >= win_start) or (mow < win_end)
        brake = brake_manual or (not in_window)

        # ── indicators on the forming bar ──
        for f in range(n_tf):
            o = off[f]
            k = K[f]
            if need_rsi[f] == 1 or need_slope[f] == 1:
                if k < 1:
                    rsi_now[f] = 100.0
                elif ladder_closed and need_slope[f] == 0:
                    rsi_now[f] = RSIc[o + k - 1]
                else:
                    rsi_now[f] = forming_rsi(C, AG, AL, o, k, b, rsi_len, a_rsi)
            if need_slope[f] == 1:
                if k < 1:
                    sgn_r[f] = 0
                    sgn_m[f] = 0
                elif slope_closed:
                    # closed-bar variant: the last CLOSED bar is "current"
                    kk = k - 1
                    sgn_r[f] = slope_sign(RSIc, R_PH, R_PL, R_CH, R_CL, o, kk, RSIc[o + kk],
                                          width, lookback, True, True)
                    sg0 = SG[o + kk]
                    sgn_m[f] = slope_sign(HISTc, M_PH, M_PL, M_CH, M_CL, o, kk, HISTc[o + kk],
                                          width, lookback, not (sg0 < 0.0), not (sg0 > 0.0))
                else:
                    sgn_r[f] = slope_sign(RSIc, R_PH, R_PL, R_CH, R_CL, o, k, rsi_now[f],
                                          width, lookback, True, True)
                    hist, sg1 = forming_macd(C, EF, ES, SG, o, k, b, mf, ms, msig, a_f, a_s, a_sg)
                    # the signal line's sign picks the pivot side: >0 highs only, <0 lows only
                    sgn_m[f] = slope_sign(HISTc, M_PH, M_PL, M_CH, M_CL, o, k, hist,
                                          width, lookback, not (sg1 < 0.0), not (sg1 > 0.0))
                if ladder_closed and need_rsi[f] == 1:
                    rsi_now[f] = RSIc[o + k - 1] if k >= 1 else 100.0

        # ── section scores (Strategy._weighted_score) ──
        open_score = 0.0
        fc_score = 0.0
        book_score = 0.0
        for f in range(n_tf):
            if need_slope[f] == 0:
                continue
            r = sgn_r[f]
            m = sgn_m[f]
            wr = w_or[f]
            wm = w_om[f]
            if wr != 0.0 or wm != 0.0:
                rr = r
                mm = m
                if grey_open and wr != 0.0 and wm != 0.0:
                    if rr == 0 and mm != 0:
                        rr = mm
                    elif mm == 0 and rr != 0:
                        mm = rr
                open_score += wr * rr + wm * mm
            wr = w_fr[f]
            wm = w_fm[f]
            if wr != 0.0 or wm != 0.0:
                rr = r
                mm = m
                if grey_fc and wr != 0.0 and wm != 0.0:
                    if rr == 0 and mm != 0:
                        rr = mm
                    elif mm == 0 and rr != 0:
                        mm = rr
                fc_score += wr * rr + wm * mm
            wr = w_br[f]
            wm = w_bm[f]
            if wr != 0.0 or wm != 0.0:
                rr = r
                mm = m
                if grey_book and wr != 0.0 and wm != 0.0:
                    if rr == 0 and mm != 0:
                        rr = mm
                    elif mm == 0 and rr != 0:
                        mm = rr
                book_score += wr * rr + wm * mm

        # ── Strategy.calculate_signal ──
        entry_dir = 0
        if open_score >= entry_s and fc_score >= entry_agree_s:
            entry_dir = 1
        elif open_score <= -entry_s and fc_score <= -entry_agree_s:
            entry_dir = -1
        open_wants = 0
        if open_score >= entry_s:
            open_wants = 1
        elif open_score <= -entry_s:
            open_wants = -1
        entry_allowed = (T - last_close) >= cooldown

        signal = 0
        reason = R_NONE
        tier = -1
        if n_pos == 0:
            counters[K_FLAT_LIVE] += 1
            if open_wants != 0 and entry_dir == 0:
                counters[K_BLOCK_CHOP] += 1
            if entry_dir != prev_dir:
                prev_dir = entry_dir
                dir_since = T
            if entry_dir != 0:
                if not entry_allowed:
                    counters[K_BLOCK_COOLDOWN] += 1
                elif entry_dir > 0:
                    signal = 1
                else:
                    signal = 2
        else:
            prev_dir = 0
            held = (T - basket_open_t) >= min_hold
            if side > 0:
                fc_hit = fc_enabled and (fc_score <= -force_close_s)
                bk_hit = book_enabled and (profit > protect * basket_units) and (book_score <= -book_s)
                add_ok = open_score > -ladder_s
            else:
                fc_hit = fc_enabled and (fc_score >= force_close_s)
                bk_hit = book_enabled and (profit > protect * basket_units) and (book_score >= book_s)
                add_ok = open_score < ladder_s
            if fc_hit:
                if fc_since < 0:
                    fc_since = T
            else:
                fc_since = -1
            fc_fire = fc_hit and held and ((T - fc_since) >= fc_confirm)
            bk_fire = bk_hit and held
            # live: the target is $target x unit for the whole basket, however many lots it holds
            tgt = target * (basket_lot_units if target_per_lot else basket_units)
            if sl_on and profit <= -sl_usd * basket_units:
                signal = 3 if side > 0 else 4
                reason = R_STOPLOSS
            elif target_on and profit > tgt:
                signal = 3 if side > 0 else 4
                reason = R_TARGET
            elif bk_fire:
                signal = 3 if side > 0 else 4
                reason = R_BOOK
            elif fc_fire:
                signal = 3 if side > 0 else 4
                reason = R_FORCE
            elif max_hold > 0 and (T - basket_open_t) >= max_hold:
                signal = 3 if side > 0 else 4
                reason = R_TIME
            else:
                cnt = n_pos
                if cnt <= n_tiers:
                    tf_i = ladder_tf[cnt - 1]
                    if side > 0:
                        hit = rsi_now[tf_i] <= rsi_os
                    else:
                        hit = rsi_now[tf_i] >= rsi_ob
                    if hit:
                        if not add_ok:
                            counters[K_LADDER_GATED] += 1
                        else:
                            gap_ok = True
                            if ladder_gap > 0.0:
                                if side > 0:
                                    gap_ok = (last_fill_price - a) >= ladder_gap
                                else:
                                    gap_ok = (b - last_fill_price) >= ladder_gap
                            if ladder_interval > 0 and (T - last_fill_t) < ladder_interval:
                                gap_ok = False
                            if gap_ok:
                                signal = 5 if side > 0 else 6
                                tier = tf_i
                            else:
                                counters[K_LADDER_SPACED] += 1
                else:
                    counters[K_LADDER_EXHAUSTED] += 1

        if hole_close == 1:
            # not a decision of the bot: the history stops here, so the basket is taken off at this quote
            hole_close = 0
            signal = 3 if side > 0 else 4
            reason = R_HOLE
            tier = -1

        if n_trace < max_trace:
            trace[n_trace, T_T] = T
            trace[n_trace, T_SIGNAL] = signal
            trace[n_trace, T_OPEN_SCORE] = open_score
            trace[n_trace, T_FC_SCORE] = fc_score
            trace[n_trace, T_BOOK_SCORE] = book_score
            trace[n_trace, T_BID] = b
            trace[n_trace, T_ASK] = a
            trace[n_trace, T_NPOS] = n_pos * side
            trace[n_trace, T_PROFIT] = profit
            trace[n_trace, T_UNITS] = units
            trace[n_trace, T_ENTRY_ALLOWED] = 1.0 if entry_allowed else 0.0
            trace[n_trace, T_BRAKE] = 1.0 if brake else 0.0
            for q in range(n_tiers):
                if q < T_N - T_RSI0:
                    trace[n_trace, T_RSI0 + q] = rsi_now[ladder_tf[q]]
            n_trace += 1
        elif max_trace > 0:
            counters[K_TRACE_OVERFLOW] += 1

        # ── execution ──
        extra_wait = 0
        do_close = False

        # broker-side stop-out comes first: it does not wait for the bot
        if n_pos > 0 and used_margin > 0.0 and (equity / used_margin * 100.0) <= stop_out:
            do_close = True
            reason = R_STOPOUT
            signal = 3 if side > 0 else 4
            blown = 1

        if signal != 0:
            fptr = ptr
            if latency > 0:
                while fptr + 1 < n and t_ms[fptr + 1] <= T + latency:
                    fptr += 1
            fb = bid[fptr]
            fa = fb + (ask[fptr] - fb) * spread_mult + extra_spread

            if signal == 1 or signal == 2:
                want_side = 1 if signal == 1 else -1
                ok = True
                # 1. reasons for which no order is sent at all
                if brake:
                    counters[K_BLOCK_BRAKE] += 1
                    ok = False
                elif T < hole_until:
                    counters[K_BLOCK_HOLE] += 1       # quarantine after a hole in the tick history
                    ok = False
                elif (want_side > 0 and not allow_long) or (want_side < 0 and not allow_short):
                    ok = False
                elif hours_on and hour_ok[(tsec % 86400) // 3600] == 0:
                    counters[K_BLOCK_HOURS] += 1
                    ok = False
                elif entry_confirm > 0 and (T - dir_since) < entry_confirm:
                    counters[K_BLOCK_CONFIRM] += 1
                    ok = False
                # 2. the order is sent. The live helper sleeps after order_send whatever the broker answers,
                #    so a refused order costs the loop the same time as a filled one.
                elif mkt_closed:
                    counters[K_BLOCK_CLOSED] += 1     # refused: the session has ended
                    ok = False
                    extra_wait = open_delay
                elif T < reopen_until:
                    counters[K_BLOCK_REOPEN] += 1     # refused: the broker is in close-only mode after a break
                    ok = False
                    extra_wait = open_delay
                if ok:
                    lots = _round2(units * mtqty)
                    price = fa + slippage if want_side > 0 else fb - slippage
                    need = lots * contract * price / leverage
                    if need > equity:
                        counters[K_MARGIN_REJECT] += 1
                        extra_wait = open_delay         # refused for margin: same sleep
                    else:
                        side = want_side
                        pos_lots[0] = lots
                        pos_price[0] = price
                        pos_t[0] = T
                        n_pos = 1
                        basket_units = units
                        basket_open_t = T
                        basket_mae = 0.0
                        basket_mfe = 0.0
                        basket_open_score = open_score
                        basket_fc_score = fc_score
                        basket_comm = lots * commission
                        basket_first_price = price
                        last_fill_price = price
                        last_fill_t = T
                        basket_lot_units = lots / mtqty
                        fc_since = -1
                        counters[K_ENTRIES] += 1
                        extra_wait = open_delay
                        if n_fills < max_fills:
                            fills[n_fills, F_T] = T
                            fills[n_fills, F_FILL_T] = t_ms[fptr]
                            fills[n_fills, F_ACTION] = ACT_OPEN
                            fills[n_fills, F_SIDE] = side
                            fills[n_fills, F_LOTS] = lots
                            fills[n_fills, F_PRICE] = price
                            fills[n_fills, F_PROFIT] = 0.0
                            fills[n_fills, F_BALANCE] = balance
                            fills[n_fills, F_BASKET] = n_baskets
                            fills[n_fills, F_REASON] = 0
                            fills[n_fills, F_UNITS] = units
                            fills[n_fills, F_OPEN_SCORE] = open_score
                            fills[n_fills, F_FC_SCORE] = fc_score
                            fills[n_fills, F_BOOK_SCORE] = book_score
                            fills[n_fills, F_NPOS] = 1
                            fills[n_fills, F_BID] = b
                            fills[n_fills, F_ASK] = a
                            fills[n_fills, F_TIER] = -1
                            fills[n_fills, F_BASKET_PROFIT] = 0.0
                            fills[n_fills, F_POS_OPEN_T] = T
                            fills[n_fills, F_POS_OPEN_PRICE] = price
                            n_fills += 1
                        else:
                            counters[K_FILL_OVERFLOW] += 1

            elif signal == 5 or signal == 6:
                lots = _round2(ladder_mult[n_pos] * basket_units * mtqty)
                price = fa + slippage if side > 0 else fb - slippage
                need = lots * contract * price / leverage
                # live sleeps 0.1 s in the helper and ORDER_COOLDOWN_SECONDS after every add it sends, filled or refused
                if mkt_closed:
                    counters[K_BLOCK_CLOSED] += 1
                    extra_wait = open_delay + add_delay
                elif T < reopen_until:
                    counters[K_BLOCK_REOPEN] += 1
                    extra_wait = open_delay + add_delay
                elif need > equity - used_margin or n_pos >= MAXPOS:
                    counters[K_MARGIN_REJECT] += 1
                    extra_wait = open_delay + add_delay
                else:
                    pos_lots[n_pos] = lots
                    pos_price[n_pos] = price
                    pos_t[n_pos] = T
                    n_pos += 1
                    basket_comm += lots * commission
                    last_fill_price = price
                    last_fill_t = T
                    basket_lot_units += lots / mtqty
                    counters[K_ADDS] += 1
                    extra_wait = open_delay + add_delay
                    if n_fills < max_fills:
                        fills[n_fills, F_T] = T
                        fills[n_fills, F_FILL_T] = t_ms[fptr]
                        fills[n_fills, F_ACTION] = ACT_ADD
                        fills[n_fills, F_SIDE] = side
                        fills[n_fills, F_LOTS] = lots
                        fills[n_fills, F_PRICE] = price
                        fills[n_fills, F_PROFIT] = 0.0
                        fills[n_fills, F_BALANCE] = balance
                        fills[n_fills, F_BASKET] = n_baskets
                        fills[n_fills, F_REASON] = 0
                        fills[n_fills, F_UNITS] = basket_units
                        fills[n_fills, F_OPEN_SCORE] = open_score
                        fills[n_fills, F_FC_SCORE] = fc_score
                        fills[n_fills, F_BOOK_SCORE] = book_score
                        fills[n_fills, F_NPOS] = n_pos
                        fills[n_fills, F_BID] = b
                        fills[n_fills, F_ASK] = a
                        fills[n_fills, F_TIER] = tier
                        fills[n_fills, F_BASKET_PROFIT] = profit
                        fills[n_fills, F_POS_OPEN_T] = T
                        fills[n_fills, F_POS_OPEN_PRICE] = price
                        n_fills += 1
                    else:
                        counters[K_FILL_OVERFLOW] += 1

            elif signal == 3 or signal == 4:
                # a close the bot sends after the session's last quote is refused like any other order; the
                # positions stay and the bot tries again on the next pass. (Closing at the last quote before a
                # hole in the history is not an order at all, and a stop-out is the broker's own doing.)
                if mkt_closed and reason != R_HOLE and reason != R_STOPOUT:
                    counters[K_BLOCK_CLOSED] += 1
                else:
                    do_close = True

            if do_close and n_pos > 0:
                cprice = fb - slippage if side > 0 else fa + slippage
                realised = 0.0
                tot_lots = 0.0
                wsum = 0.0
                for i in range(n_pos):
                    if side > 0:
                        p = _round2((cprice - pos_price[i]) * pos_lots[i] * contract)
                    else:
                        p = _round2((pos_price[i] - cprice) * pos_lots[i] * contract)
                    realised += p
                    tot_lots += pos_lots[i]
                    wsum += pos_lots[i] * pos_price[i]
                    balance += p
                    if n_fills < max_fills:
                        fills[n_fills, F_T] = T
                        fills[n_fills, F_FILL_T] = t_ms[fptr]
                        fills[n_fills, F_ACTION] = ACT_CLOSE
                        fills[n_fills, F_SIDE] = side
                        fills[n_fills, F_LOTS] = pos_lots[i]
                        fills[n_fills, F_PRICE] = cprice
                        fills[n_fills, F_PROFIT] = p
                        fills[n_fills, F_BALANCE] = balance
                        fills[n_fills, F_BASKET] = n_baskets
                        fills[n_fills, F_REASON] = reason
                        fills[n_fills, F_UNITS] = basket_units
                        fills[n_fills, F_OPEN_SCORE] = open_score
                        fills[n_fills, F_FC_SCORE] = fc_score
                        fills[n_fills, F_BOOK_SCORE] = book_score
                        fills[n_fills, F_NPOS] = n_pos - i - 1
                        fills[n_fills, F_BID] = b
                        fills[n_fills, F_ASK] = a
                        fills[n_fills, F_TIER] = -1
                        fills[n_fills, F_BASKET_PROFIT] = profit
                        fills[n_fills, F_POS_OPEN_T] = pos_t[i]
                        fills[n_fills, F_POS_OPEN_PRICE] = pos_price[i]
                        n_fills += 1
                    else:
                        counters[K_FILL_OVERFLOW] += 1
                basket_comm += tot_lots * commission
                balance -= basket_comm
                if balance < 0.0 and reason == R_STOPOUT:
                    balance = 0.0   # negative-balance protection
                if reason == R_TARGET:
                    counters[K_CLOSE_TARGET] += 1
                elif reason == R_BOOK:
                    counters[K_CLOSE_BOOK] += 1
                elif reason == R_FORCE:
                    counters[K_CLOSE_FORCE] += 1
                elif reason == R_STOPOUT:
                    counters[K_CLOSE_STOPOUT] += 1
                elif reason == R_STOPLOSS:
                    counters[K_CLOSE_SL] += 1
                elif reason == R_TIME:
                    counters[K_CLOSE_TIME] += 1
                elif reason == R_HOLE:
                    counters[K_CLOSE_HOLE] += 1
                if n_baskets < max_baskets:
                    baskets[n_baskets, B_ID] = n_baskets
                    baskets[n_baskets, B_SIDE] = side
                    baskets[n_baskets, B_OPEN_T] = basket_open_t
                    baskets[n_baskets, B_CLOSE_T] = T
                    baskets[n_baskets, B_NPOS] = n_pos
                    baskets[n_baskets, B_LOTS] = tot_lots
                    baskets[n_baskets, B_PNL] = realised - basket_comm
                    baskets[n_baskets, B_REASON] = reason
                    baskets[n_baskets, B_UNITS] = basket_units
                    baskets[n_baskets, B_MAE] = basket_mae
                    baskets[n_baskets, B_MFE] = basket_mfe
                    baskets[n_baskets, B_FIRST_PRICE] = basket_first_price
                    baskets[n_baskets, B_AVG_PRICE] = wsum / tot_lots if tot_lots > 0.0 else 0.0
                    baskets[n_baskets, B_CLOSE_PRICE] = cprice
                    baskets[n_baskets, B_OPEN_SCORE] = basket_open_score
                    baskets[n_baskets, B_FC_SCORE] = basket_fc_score
                    baskets[n_baskets, B_COMMISSION] = basket_comm
                    baskets[n_baskets, B_BALANCE] = balance
                    baskets[n_baskets, B_PROFIT_SEEN] = profit
                    n_baskets += 1
                else:
                    counters[K_BASKET_OVERFLOW] += 1
                n_pos = 0
                side = 0
                last_close = T
                fc_since = -1
                profit = 0.0
                equity = balance
                if blown == 1:
                    # stopped out: the run ends here (nothing left to trade responsibly)
                    T += poll
                    break

        # exposure extremes
        if n_pos > 0:
            tl = 0.0
            for i in range(n_pos):
                tl += pos_lots[i]
            if tl > max_lots:
                max_lots = tl
            if n_pos > max_npos:
                max_npos = n_pos

        # equity / score sample for the charts
        if rec_ms > 0 and T >= next_rec and n_eq < max_eq:
            tl = 0.0
            for i in range(n_pos):
                tl += pos_lots[i]
            eq[n_eq, E_T] = T
            eq[n_eq, E_BALANCE] = balance
            eq[n_eq, E_EQUITY] = equity
            eq[n_eq, E_LOTS] = tl * side
            eq[n_eq, E_NPOS] = n_pos
            eq[n_eq, E_OPEN_SCORE] = open_score
            eq[n_eq, E_FC_SCORE] = fc_score
            eq[n_eq, E_BOOK_SCORE] = book_score
            eq[n_eq, E_UNITS] = units
            eq[n_eq, E_BID] = b
            eq[n_eq, E_ASK] = a
            n_eq += 1
            next_rec = T - (T - start_ms) % rec_ms + rec_ms

        T += poll + extra_wait
        if jitter_ms > 0:
            # the live loop sleeps for the period and then spends a varying time talking to the terminal
            rng = (rng * 1103515245 + 12345) % 2147483648
            T += (rng >> 8) % (jitter_ms + 1)

    # mark any basket still open at the end to market (it is NOT closed)
    open_profit = 0.0
    tl = 0.0
    if n_pos > 0 and ptr >= 0:
        b = bid[ptr]
        a = b + (ask[ptr] - b) * spread_mult + extra_spread
        for i in range(n_pos):
            tl += pos_lots[i]
            if side > 0:
                open_profit += _round2((b - pos_price[i]) * pos_lots[i] * contract)
            else:
                open_profit += _round2((pos_price[i] - a) * pos_lots[i] * contract)
    scal[S_FINAL_BALANCE] = balance
    scal[S_FINAL_EQUITY] = balance + open_profit
    scal[S_MAX_EQUITY] = max_equity
    scal[S_MIN_EQUITY] = min_equity
    scal[S_MAX_DD_ABS] = max_dd_abs
    scal[S_MAX_DD_PCT] = max_dd_pct
    scal[S_MAX_LOTS] = max_lots
    scal[S_MAX_NPOS] = max_npos
    scal[S_MIN_MARGIN_LEVEL] = min_margin_level
    scal[S_OPEN_PROFIT_END] = open_profit
    scal[S_MAX_MARGIN] = max_margin
    scal[S_BLOWN] = blown
    scal[S_LAST_T] = T
    scal[S_N_FILLS] = n_fills
    scal[S_N_BASKETS] = n_baskets
    scal[S_N_EQ] = n_eq
    scal[S_N_TRACE] = n_trace
    scal[S_MAX_FLOAT_LOSS] = max_float_loss
    scal[S_OPEN_NPOS_END] = n_pos
    scal[S_OPEN_LOTS_END] = tl * side
