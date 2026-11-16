import MetaTrader5 as mt5
import copy
import json
import ntpath
import os
import re
import sys
import threading
import time
from pathlib import Path
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from mt5_helper import MT5PositionHelper, TerminalReadError
from indicator import Indicator
from strategy import Strategy, Signal
from datetime import timezone
from constants import (
    RSI_LENGTH, RSI_MA_TYPE, RSI_CANDLE_COUNT, RSI_MTF_TIMEFRAMES,
    RSI_DCA_LADDER_TIMEFRAMES, RSI_FINAL_CLOSE_TIMEFRAME,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    SLOPE_TIMEFRAMES, PEAK_LOOKBACK, PIVOT_WIDTH, RSI_PEAK_OB, RSI_PEAK_OS,
    RSI_GRAPH_BARS,
    REENTRY_COOLDOWN_SECONDS,
    CANDLE_TIMEFRAME, CANDLE_COUNT,
    MARKET_STATUS_TIMEFRAME, MARKET_LOOKBACK_MINUTES,
    OUTPUT_DIR, DAILY_TRADE_SUBDIR,
    HISTORICAL_SUMMARY_DAYS, HISTORICAL_SUMMARY_FILENAME,
    STRATEGY_LOG_FILENAME, STRATEGY_LOG_MAX_ENTRIES,
    ORDER_COOLDOWN_SECONDS,
    ACTIVE_CONFIG_FILENAME,
    STRATEGY_HEDGE,
    # design levers (constants.py; the defaults are the live bot). Read at call time, like the names above.
    DESIGN_NAME, STRATEGY,
    TREND_TF, VOL_TF, VOL_LEN,
    TARGET_USD_PER_UNIT, STOP_LOSS_USD_PER_UNIT,
    TARGET_VOL, STOP_VOL, VOL_CAP_USD_PER_UNIT, LADDER_GAP_VOL,
    LOSS_COOLDOWN_S, BACKSTOP_FACTOR,
    CONTRACT_SIZE_FALLBACK, STATE_SUBDIR,
    # demo isolation
    MAGIC, DEMO_BRANCH, VIRTUAL_START_BALANCE, VIRTUAL_START_DATE,
    # the Turtle (STRATEGY = 'turtle')
    TURTLE_SYSTEM, TURTLE_N_LEN, TURTLE_STOP_N, TURTLE_ADD_N, TURTLE_MAX_LEGS, TURTLE_TICK, TURTLE_BACKSTOP_N,
    TURTLE_VOTE_TF, TURTLE_VOTE_BARS, TURTLE_D1_BARS, TURTLE_MIN_D1_BARS,
)
try:
    import tracelog as _tracelog     # the dashboard's trace files and the text log; trading never needs them
except Exception as _e:              # a broken tracelog.py must not stop the bot: it trades without them
    print(f"note: tracelog.py did not load ({_e!r}): no trace files, no text log")
    _tracelog = None


def _turtle_rules():
    """This folder's turtle.py (the Turtle's rules), loaded from its path: the bare name 'turtle' can resolve to
    Python's own turtle-graphics module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('alcadeias_turtle', Path(__file__).resolve().parent / 'turtle.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T = _turtle_rules()

_TF_PREFIX = 'TIMEFRAME_'
_STATE_VERSION = 1
_RESOLVE_ATTEMPTS = 30           # polls spent looking for a closed basket's deals before its P/L at the close decision stands
_TF_SECONDS = {'M1': 60, 'M2': 120, 'M3': 180, 'M4': 240, 'M5': 300, 'M6': 360, 'M10': 600, 'M12': 720, 'M15': 900,
               'M20': 1200, 'M30': 1800, 'H1': 3600, 'H2': 7200, 'H3': 10800, 'H4': 14400, 'H6': 21600,
               'H8': 28800, 'H12': 43200, 'D1': 86400}
_TURTLE_PENDING_S = 10.0         # a leg the bot just filled waits this long for the terminal to list it
_TURTLE_SETTLE_S = 2.0           # a D1 / M15 bar is read this long after its end (its last ticks are in by then)
_TURTLE_MIN_VOTE_BARS = 100      # fewer closed M15 bars from the terminal: no vote (no entry)
_TURTLE_HISTORY_S = 400 * 86400  # deal history read at a start without the Turtle's state file
_TURTLE_NOTE_S = 300.0           # a repeated Turtle note (no bars, refused order, brake) is printed / logged this often


def _tf_key(tf):
    """'TIMEFRAME_H1' or 'H1' -> 'H1' (None stays None)."""
    if tf is None:
        return None
    s = str(tf).strip().upper()
    return s[len(_TF_PREFIX):] if s.startswith(_TF_PREFIX) else s


def _tf_name(tf):
    """'H1' or 'TIMEFRAME_H1' -> 'TIMEFRAME_H1' (None stays None)."""
    k = _tf_key(tf)
    return None if k is None else _TF_PREFIX + k


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float('inf')


def _utc(ts):
    """Epoch seconds -> aware UTC datetime (what the terminal's time arguments expect)."""
    from datetime import datetime
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def _virtual_start_ts():
    """VIRTUAL_START_DATE ('YYYY-MM-DD' or an ISO time, UTC) as epoch seconds; None when it is None."""
    if VIRTUAL_START_DATE is None:
        return None
    from datetime import datetime
    dt = datetime.fromisoformat(str(VIRTUAL_START_DATE).strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _pos_time(pos):
    """Open time of a position in seconds (time_msc when the terminal has it)."""
    msc = getattr(pos, 'time_msc', None)
    return msc / 1000.0 if msc else float(pos.time)


def _tick_time(tick):
    """The terminal's clock: the time of the symbol's last tick in seconds (time_msc when there), None without one.
    The Turtle reads its bars against it, so a bar counts as closed once a tick after its end has arrived."""
    if tick is None:
        return None
    msc = getattr(tick, 'time_msc', 0) or 0
    if msc:
        return msc / 1000.0
    t = getattr(tick, 'time', 0) or 0
    return float(t) if t else None


def _iso(ts):
    return None if ts is None else _utc(ts).isoformat()


def _pos_id(pos):
    """The identifier the deal history knows a position by (position_id of its deals)."""
    ident = getattr(pos, 'identifier', None)
    return int(ident) if ident else int(pos.ticket)


def _sorted_positions(positions):
    """Positions oldest first (open time, then ticket)."""
    return sorted(positions or [], key=lambda p: (_pos_time(p), int(p.ticket)))


def _deal_time(deal):
    msc = getattr(deal, 'time_msc', None)
    return msc / 1000.0 if msc else float(deal.time)


def _deal_net(deal):
    """Realised money of a deal: profit + swap + commission + fee."""
    return (float(getattr(deal, 'profit', 0.0) or 0.0) + float(getattr(deal, 'swap', 0.0) or 0.0)
            + float(getattr(deal, 'commission', 0.0) or 0.0) + float(getattr(deal, 'fee', 0.0) or 0.0))


def _is_out_deal(deal):
    """A deal that closes (part of) a position: DEAL_ENTRY_OUT (1) or DEAL_ENTRY_OUT_BY (3)."""
    e = getattr(deal, 'entry', None)
    return e in (1, 3) or e == 'out'


def virtual_balance_enabled():
    """Units come from the virtual balance (VIRTUAL_START_BALANCE + this bot's own closed P/L) when a start
    date is set and the bot has a MAGIC to find its deals by; otherwise from the account balance (live)."""
    return VIRTUAL_START_DATE is not None and MAGIC is not None


def usd_target_per_unit():
    """The configured $ target per unit: STRATEGY_HEDGE for 'live', the number, or None (no $ target)."""
    if TARGET_USD_PER_UNIT is None:
        return None
    if isinstance(TARGET_USD_PER_UNIT, str) and TARGET_USD_PER_UNIT == 'live':
        return STRATEGY_HEDGE
    return TARGET_USD_PER_UNIT


def basket_levels(vol_unit, usd_per_price):
    """
    A basket's distances, fixed when it opens (the backtester's kernels.py L1266-1289):
      target_usd_per_unit  USD per unit (None = no target): the $ target, or TARGET_VOL x unit x usd_per_price
      stop_usd_per_unit    USD per unit (None = no stop):   the $ stop,   or STOP_VOL x unit x usd_per_price
      gap_px               price units an add needs against the last fill: LADDER_GAP_VOL x unit (0 = none)
    with unit = `vol_unit` (price units, the last closed VOL_TF bar), first capped at
    VOL_CAP_USD_PER_UNIT / usd_per_price, and usd_per_price = contract_size x mtqty (gold 1.0, BTC 0.01).
    The volatility multiples apply only with VOL_TF set and a known unit (> 0); the basket's USD levels
    are these per-unit values times the basket's unit count.
    """
    tgt = usd_target_per_unit()
    sl = STOP_LOSS_USD_PER_UNIT
    gap = 0.0
    v = None
    if VOL_TF is not None and vol_unit is not None and vol_unit > 0:
        # (an unknown usd_per_price cannot reach here with a USD distance configured: entry_block_reason
        # refuses the entry, and a rebuilt basket waits for it, see levels_complete)
        v = vol_unit
        if VOL_CAP_USD_PER_UNIT > 0.0 and usd_per_price and v * usd_per_price > VOL_CAP_USD_PER_UNIT:
            v = VOL_CAP_USD_PER_UNIT / usd_per_price
        if TARGET_VOL > 0.0 and usd_per_price:
            tgt = TARGET_VOL * v * usd_per_price
        if STOP_VOL > 0.0 and usd_per_price:
            sl = STOP_VOL * v * usd_per_price
        if LADDER_GAP_VOL > 0.0:
            gap = LADDER_GAP_VOL * v
    return {
        'target_usd_per_unit': tgt,
        'stop_usd_per_unit': sl,
        'gap_px': gap,
        'vol_unit_raw': vol_unit if VOL_TF is not None else None,
        'vol_unit': v,
    }


def levels_complete(vol_unit, usd_per_price):
    """True when basket_levels() can give the design's distances (always without VOL_TF)."""
    if VOL_TF is None:
        return True
    if not (vol_unit is not None and vol_unit > 0):
        return False
    return bool(usd_per_price) or not (TARGET_VOL > 0 or STOP_VOL > 0 or VOL_CAP_USD_PER_UNIT > 0)


def entry_timeframes():
    """Short keys of every timeframe a fresh entry reads: the OPEN and FORCE-CLOSE (agreement) sections, TREND_TF
    and VOL_TF."""
    keys = Strategy.section_timeframes() + [_tf_key(t) for t in (TREND_TF, VOL_TF) if t is not None]
    return list(dict.fromkeys(keys))


def entry_block_reason(want_side, trend_now, vol_now, usd_per_price, no_data=(), short_history=()):
    """
    Why a fresh entry the strategy wants is not sent, after the brake (None = send it). The backtester's
    execution-time order (kernels.py L1206-1225): trend, then the volatility unit not known; before them
    the data the live terminal may not have given this poll.
      votes unknown: a timeframe of entry_timeframes() returned no bars this poll (`no_data`): its votes are
                     missing, which the scores would read as 0 -- with ENTRY_AGREE_S = 0 a missing M15 would
                     pass the agreement gate. Exits and stops do not depend on it.
      trend: TREND_TF set and want_side * trend <= 0 (a trend of 0 blocks both sides)
      volatility unknown: VOL_TF set and the unit of the last closed bar is not > 0, or the terminal gave fewer
                     than _MIN_CLOSED_BARS closed bars of VOL_TF / TREND_TF this poll (`short_history`: the unit
                     and the MACD signal line are not settled on a short history)
      contract size unknown: a volatility distance is configured and the USD value of a price move is not known
    """
    if no_data and {_tf_key(t) for t in no_data} & set(entry_timeframes()):
        return 'votes unknown'
    if TREND_TF is not None and want_side * trend_now <= 0:
        return 'trend'
    if VOL_TF is not None and not (vol_now is not None and vol_now > 0):
        return 'volatility unknown'
    if short_history:
        return 'volatility unknown'
    if VOL_TF is not None and not usd_per_price and (TARGET_VOL > 0 or STOP_VOL > 0 or VOL_CAP_USD_PER_UNIT > 0):
        return 'contract size unknown'
    return None


def design_has_stop():
    """A design whose baskets have a stop (STOP_VOL > 0, or a $ stop): its fills carry a broker-side backstop."""
    return STOP_VOL > 0 or STOP_LOSS_USD_PER_UNIT is not None


def backstop_distance(stop_usd_per_unit, usd_per_price):
    """
    How far beyond its fill a basket leg's broker-side backstop (request sl) sits, in price units:
    BACKSTOP_FACTOR x the basket's stop distance = its stop per unit / the USD value of a 1.0 move per unit
    (STOP_VOL x unit, capped, for a volatility stop). The bot's own stop closes the basket before the price is one
    stop distance beyond the fill of any of its legs (the entry's stop sits there; an add, made before the stop,
    only moves it nearer), so in normal operation it always closes first and the backtested behaviour is
    unchanged; the backstop acts only while the bot or the terminal is down. None when there is no stop or its
    distance is not known (no backstop).
    """
    if stop_usd_per_unit is None or not usd_per_price or not stop_usd_per_unit > 0:
        return None
    return float(BACKSTOP_FACTOR) * float(stop_usd_per_unit) / float(usd_per_price)


def design_problems():
    """Why the design in constants.py cannot run (empty = fine). The backtester's BacktestConfig checks."""
    p = list(Strategy.design_problems())
    if STRATEGY not in ('basket', 'turtle'):
        p.append(f"STRATEGY {STRATEGY!r} is not 'basket' or 'turtle'")
    elif STRATEGY == 'turtle':
        p.extend(turtle_design_problems())
    for name, tf in (('TREND_TF', TREND_TF), ('VOL_TF', VOL_TF)):
        if tf is not None and not hasattr(mt5, _tf_name(tf)):
            p.append(f'{name} {tf!r} is not an MT5 timeframe')
    for tf in Strategy.ladder_tiers():
        if not hasattr(mt5, _TF_PREFIX + tf):
            p.append(f'LADDER_TFS entry {tf!r} is not an MT5 timeframe')
    if not isinstance(VOL_LEN, int) or isinstance(VOL_LEN, bool) or VOL_LEN < 2:
        p.append(f'VOL_LEN must be a whole number >= 2, not {VOL_LEN!r}')
    if not _is_number(BACKSTOP_FACTOR) or BACKSTOP_FACTOR <= 1.0:
        p.append(f"BACKSTOP_FACTOR must be a number > 1 (the backstop beyond the bot's own stop), not {BACKSTOP_FACTOR!r}")
    if design_has_stop() and Strategy.ladder_tiers() and not (_is_number(LADDER_GAP_VOL) and LADDER_GAP_VOL > 0):
        p.append("a design with a stop and a ladder needs LADDER_GAP_VOL > 0 (and VOL_TF), or MAX_ADDS = 0: without a "
                 "gap an add can fill in favour of the basket, and its broker-side backstop could then lie inside the "
                 "basket's stop (the broker would close it before the bot's own stop)")
    if (TREND_TF is not None or VOL_TF is not None) and RSI_CANDLE_COUNT - 1 < _MIN_CLOSED_BARS:
        p.append(f'RSI_CANDLE_COUNT {RSI_CANDLE_COUNT} leaves fewer than {_MIN_CLOSED_BARS} closed bars for TREND_TF / '
                 f'VOL_TF: no entry could ever be sent')
    vols = {'TARGET_VOL': TARGET_VOL, 'STOP_VOL': STOP_VOL, 'LADDER_GAP_VOL': LADDER_GAP_VOL,
            'VOL_CAP_USD_PER_UNIT': VOL_CAP_USD_PER_UNIT}
    for name, x in vols.items():
        if not _is_number(x) or x < 0:
            p.append(f'{name} must be a number >= 0, not {x!r}')
        elif x > 0 and VOL_TF is None:
            p.append(f'{name} > 0 needs VOL_TF, the timeframe whose volatility is the unit')
    t = TARGET_USD_PER_UNIT
    if not (t is None or (isinstance(t, str) and t == 'live') or (_is_number(t) and t >= 0)):
        p.append(f"TARGET_USD_PER_UNIT must be 'live', None or a number >= 0, not {t!r}")
    if not (STOP_LOSS_USD_PER_UNIT is None or (_is_number(STOP_LOSS_USD_PER_UNIT) and STOP_LOSS_USD_PER_UNIT >= 0)):
        p.append(f'STOP_LOSS_USD_PER_UNIT must be None or a number >= 0, not {STOP_LOSS_USD_PER_UNIT!r}')
    if not _is_number(LOSS_COOLDOWN_S) or LOSS_COOLDOWN_S < 0:
        p.append(f'LOSS_COOLDOWN_S must be a number of seconds >= 0, not {LOSS_COOLDOWN_S!r}')
    if MAGIC is not None and (not isinstance(MAGIC, int) or isinstance(MAGIC, bool) or MAGIC < 0):
        p.append(f'MAGIC must be None or a whole number >= 0, not {MAGIC!r}')
    if VIRTUAL_START_DATE is not None:
        try:
            _virtual_start_ts()
        except (TypeError, ValueError):
            p.append(f"VIRTUAL_START_DATE must be None or a date 'YYYY-MM-DD', not {VIRTUAL_START_DATE!r}")
        if not _is_number(VIRTUAL_START_BALANCE) or VIRTUAL_START_BALANCE <= 0:
            p.append(f'VIRTUAL_START_BALANCE must be a number > 0, not {VIRTUAL_START_BALANCE!r}')
    return p


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def turtle_params():
    """The TURTLE_* constants as turtle.py's keyword arguments."""
    return dict(system=TURTLE_SYSTEM, n_len=TURTLE_N_LEN, stop_n=float(TURTLE_STOP_N), add_n=float(TURTLE_ADD_N),
                tick=float(TURTLE_TICK))


def turtle_design_problems():
    """Why the TURTLE_* constants cannot run (empty = fine)."""
    p = []
    if not _is_int(TURTLE_SYSTEM) or TURTLE_SYSTEM not in T.SYSTEMS:
        p.append(f'TURTLE_SYSTEM must be 1 or 2, not {TURTLE_SYSTEM!r}')
    for name, x in (('TURTLE_STOP_N', TURTLE_STOP_N), ('TURTLE_ADD_N', TURTLE_ADD_N),
                    ('TURTLE_BACKSTOP_N', TURTLE_BACKSTOP_N)):
        if not _is_number(x) or x <= 0:
            p.append(f'{name} must be a number > 0, not {x!r}')
    if not _is_number(TURTLE_TICK) or TURTLE_TICK < 0:
        p.append(f'TURTLE_TICK must be a number >= 0, not {TURTLE_TICK!r}')
    if not _is_int(TURTLE_N_LEN) or TURTLE_N_LEN < 2:
        p.append(f'TURTLE_N_LEN must be a whole number >= 2, not {TURTLE_N_LEN!r}')
    if not _is_int(TURTLE_MAX_LEGS) or TURTLE_MAX_LEGS < 1:
        p.append(f'TURTLE_MAX_LEGS must be a whole number >= 1, not {TURTLE_MAX_LEGS!r}')
    key = _tf_key(TURTLE_VOTE_TF) if isinstance(TURTLE_VOTE_TF, str) else None
    if key is None or key not in _TF_SECONDS or not hasattr(mt5, _TF_PREFIX + key):
        p.append(f'TURTLE_VOTE_TF {TURTLE_VOTE_TF!r} is not an MT5 timeframe')
    if not _is_int(TURTLE_VOTE_BARS) or TURTLE_VOTE_BARS < 100:
        p.append(f'TURTLE_VOTE_BARS must be a whole number >= 100, not {TURTLE_VOTE_BARS!r}')
    if not _is_int(TURTLE_MIN_D1_BARS) or TURTLE_MIN_D1_BARS < 60:
        p.append(f'TURTLE_MIN_D1_BARS must be a whole number >= 60 (the 55-day channel and N), not {TURTLE_MIN_D1_BARS!r}')
    elif not _is_int(TURTLE_D1_BARS) or TURTLE_D1_BARS < TURTLE_MIN_D1_BARS:
        p.append(f'TURTLE_D1_BARS must be a whole number >= TURTLE_MIN_D1_BARS, not {TURTLE_D1_BARS!r}')
    if not hasattr(mt5, 'TIMEFRAME_D1'):
        p.append('the terminal module has no TIMEFRAME_D1')
    return p


def design_summary():
    """One line describing the design in effect (startup print)."""
    if STRATEGY == 'turtle':
        bits = [f'design {DESIGN_NAME!r}', T.describe(TURTLE_SYSTEM),
                f'N {TURTLE_N_LEN}d, stop {TURTLE_STOP_N:g}N, add every {TURTLE_ADD_N:g}N, {TURTLE_MAX_LEGS} legs max',
                f'votes {TURTLE_VOTE_TF} closed bars', f'magic {MAGIC}',
                f'virtual ${VIRTUAL_START_BALANCE:g} from {VIRTUAL_START_DATE}' if virtual_balance_enabled()
                else 'units from the account balance']
        return ' | '.join(bits)
    from strategy import (FORCE_CLOSE_ENABLED as _fc, MAX_ADDS as _ma, LADDER_TRIGGER as _lt,
                          LADDER_MULTIPLIERS as _lm)
    bits = [f'design {DESIGN_NAME!r}', f'force-close {"on" if _fc else "off"}',
            f'trend {TREND_TF or "off"}', f'vol {VOL_TF + "/" + str(VOL_LEN) if VOL_TF else "off"}']
    if VOL_TF:
        bits.append(f'target {TARGET_VOL:g}u stop {STOP_VOL:g}u cap ${VOL_CAP_USD_PER_UNIT:g}')
    else:
        bits.append(f'target ${usd_target_per_unit()}/unit stop {STOP_LOSS_USD_PER_UNIT}')
    bits.append(f'loss pause {LOSS_COOLDOWN_S:g}s' if LOSS_COOLDOWN_S else 'loss pause off')
    tiers = Strategy.ladder_tiers()
    bits.append(f'ladder {len(tiers)} x {_lt} {tiers} {"fibo" if _lm is None else list(_lm)}' if tiers else 'no ladder')
    bits.append(f'magic {MAGIC}')
    bits.append(f'virtual ${VIRTUAL_START_BALANCE:g} from {VIRTUAL_START_DATE}' if virtual_balance_enabled()
                else 'units from the account balance')
    return ' | '.join(bits)


# ─── the terminal (demo review) ───
_RECONNECT_AFTER = 5                         # polls in a row without the terminal (terminal_info() None) before the
                                             # bot connects again: mt5.shutdown(), then initialize_mt5()
_RECONNECT_BACKOFF_S = (5.0, 10.0, 30.0, 60.0)   # waits after a reconnect that failed (the last one repeats)
_LOG_REPEAT_S = 900.0                        # a problem that lasts (reconnects that fail, the terminal held by another
                                             # account) is logged again at most this often
_PENDING_FILL_S = 10.0                       # a basket the bot just opened waits this long for the terminal to list
                                             # its position (as the Turtle's legs do)
_MIN_CLOSED_BARS = 300                       # closed VOL_TF / TREND_TF bars an entry (and a rebuilt basket's unit)
                                             # needs: with fewer the EWMA unit is off by up to 12% (BTC H1, 100 bars)
_ACCOUNT_GRACE_S = 15.0                      # right after mt5.initialize(), a terminal that shows no account is read
                                             # again about once a second for this long before the bot logs in: a
                                             # terminal just started or restarted logs into its saved account by itself
_IPC_ERRORS = (-10005, -10000)               # last_error() codes of a broken connection to the terminal (IPC)


def _ipc_error(err):
    """True when last_error() reports a broken connection to the terminal (an IPC error, -10000 to -10005) or gives no
    code at all: an answer the terminal gave then says nothing about its account."""
    code = err[0] if isinstance(err, (tuple, list)) and err else None
    if isinstance(code, bool) or not isinstance(code, int):
        return True
    return _IPC_ERRORS[0] <= code <= _IPC_ERRORS[1]


# The MetaTrader 5 of the live bots on the server: every live branch's mt5_credentials.json names it as terminal_path.
# A demo bot never attaches to it (LIVE_TERMINAL_PATH): any login on it, the bot's or another program's, would switch
# the live account of every live bot attached to it.
_LIVE_TERMINAL_PATHS = (r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe',)


def _norm_path(path):
    """A Windows path as the terminal reads it: '/' and '\\' alike, no doubled separators or '.', any case."""
    return ntpath.normpath(str(path).strip().strip('"').strip()).casefold()


def _same_file(a, b):
    try:
        return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)
    except (OSError, ValueError):
        return False


def _live_terminal(path):
    """True when `path` is the live bots' MetaTrader 5: its terminal64.exe, its folder or a file in it -- however it is
    spelt (on the server also another spelling of the same file, such as a short 8.3 name)."""
    p = _norm_path(path)
    raw = str(path).strip().strip('"').strip()
    for live in _LIVE_TERMINAL_PATHS:
        exe = _norm_path(live)
        folder = ntpath.dirname(exe)
        if p in (exe, folder) or p.startswith(folder + '\\'):
            return True
        live_folder = ntpath.dirname(live)
        if _same_file(raw, live) or _same_file(raw, live_folder) or _same_file(ntpath.dirname(raw), live_folder):
            return True
    return False


def _slot_name():
    """'slot 6' for demo_hedging_xauusd6 (the number at the end of DEMO_BRANCH); 'this slot' without one."""
    m = re.search(r'(\d+)$', str(DEMO_BRANCH or ''))
    return f'slot {m.group(1)}' if m else 'this slot'


def _why_key(why):
    """A problem without the terminal's last_error, which can differ from one attempt to the next ('initialize
    failed: (-10003, ...)' -> 'initialize failed'): whether a repeated problem is a new one to log."""
    if not why:
        return why
    s = str(why)
    for sep in (' (last_error ', ': ('):
        i = s.find(sep)
        if i >= 0:
            s = s[:i]
    return s


def _unlisted_fills(basket):
    """{position id: fill time} of a basket's legs (its entry, its adds) the terminal has not listed yet
    (MT5TradingBot._record_fill)."""
    out = {}
    for u in (basket or {}).get('unlisted') or []:
        try:
            out[int(u['id'])] = float(u['time'])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fill_pending(basket, now):
    """True while a fill of the bot is not listed yet and was made under _PENDING_FILL_S ago: the entry of a basket it
    opened, or an add it made (_record_fill; a basket opened without an order ticket: under _PENDING_FILL_S since it
    opened). With no position listed, its side then counts as in that basket (no second entry, the basket's unit), and
    the basket is not booked as closed."""
    if basket is None:
        return False
    if not basket.get('ids'):
        return now - float(basket.get('opened_at') or 0.0) < _PENDING_FILL_S
    return any(now - t < _PENDING_FILL_S for t in _unlisted_fills(basket).values())


class MT5TradingBot:
    """Main Trading Bot Class with Clean Architecture"""
    
    def __init__(self, mode='demo', target_symbol=None):
        """
        Initialize the trading bot
        
        Args:
            mode (str): Either 'demo' or 'live'
            target_symbol (str): If set, only process this single symbol.
                                 Recommended to avoid MT5 threading issues.
        """
        self.mode = mode.lower()
        self.target_symbol = target_symbol.strip().upper() if target_symbol else None
        self.credentials = None
        self.symbols_config = None
        self.symbols = []
        self.symbol_configs = {}      # Per-symbol config lookup
        self.mt5_initialized = False
        self.thread_lock = threading.Lock()       # For file I/O
        self.mt5_lock = threading.Lock()           # For MT5 API calls (not thread-safe)
        self.position_helper = None
        self.symbol_map = {}
        self.indicator = Indicator()
        self.strategy = Strategy()
        self._stop_event = threading.Event()     # Signal workers to stop
        # Per-basket state (fixed distances, ladder arming) and the loss pause live in
        # <state_dir>/<symbol>_state.json; None = OUTPUT_DIR/STATE_SUBDIR. A replay may point it elsewhere
        # or replace _load_state / _save_state.
        self.state_dir = None
        self._usd_per_price = {}                 # trade symbol -> contract_size x mtqty (USD per unit per 1.0 of price)
        self._virtual_balance_last = None        # last virtual balance read from the deal history
        self._digits = {}                        # trade symbol -> price digits (the backstop is rounded to them)
        # The account this bot trades on: the demo login initialize_mt5 found (None before it ran; a replay that
        # does not call it takes the first account it sees) and why the account seen last was refused (None = ok).
        self._account_login = None
        self._account_bad = None
        # Polls in a row that could not read the terminal (they decide nothing), and why the last one could not;
        # those of them without the terminal at all (terminal_info() None) and since when, the reconnects that
        # failed since, the time of the next attempt, why initialize_mt5 failed last, and for each reason a reconnect
        # failed with (_why_key) the time of its last RECONNECT_FAILED event and the failures not logged since.
        self._failed_polls = 0
        self._read_bad = None
        self._ipc_failed = 0
        self._ipc_lost_at = None
        self._reconnects_failed = 0
        self._reconnect_at = None
        self._init_problem = None
        self._reconnect_logged = {}
        # Problems initialize_mt5 refuses to start on and that can last -- the terminal logged into another account
        # (TERMINAL_IN_USE), terminal_path naming the live bots' MetaTrader 5 (LIVE_TERMINAL_PATH): for each event, each
        # problem logged and when (_log_limited).
        self._limited_logged = {}
        # The dashboard's trace and the text log (tracelog.py), one per symbol, in trace_dir (None = OUTPUT_DIR).
        # Nothing the bot decides reads them; every call into them is wrapped (_trace), trace_enabled False = none.
        self.trace_dir = None
        self.trace_enabled = True
        self._tracers = {}
        self._boot_lines = []                    # lines logged before a symbol's trace exists (job start, login)
        self._last_account = None                # (login, trade_mode, margin_mode) of the account read last
        self._guard_why = None                   # why the last poll guard refused: ('terminal' | 'account', problem)
        self._reconnects_done = 0

    # ───────────────────── the trace (tracelog.py): read-only, never raises into the loop ─────────────────────
    def _tracer(self, symbol):
        """The symbol's TraceLog (made on first use, the lines logged before it written first); None without one."""
        tr = self._tracers.get(symbol)
        if tr is None and self.trace_enabled and _tracelog is not None:
            try:
                tr = _tracelog.TraceLog(self, symbol, self.trace_dir or OUTPUT_DIR, sys.modules[__name__])
            except Exception as e:
                print(f"[{symbol}] note: no trace / text log ({e!r}); trading goes on without them")
                self.trace_enabled = False
                return None
            self._tracers[symbol] = tr
            tr.boot(list(self._boot_lines))
        return tr

    def _trace(self, symbol, method, *args, **kwargs):
        """Hand something to the symbol's trace. Never raises (the trace logs and swallows its own errors; this is a
        second net): the trading loop must not notice it."""
        try:
            tr = self._tracer(symbol)
            if tr is not None:
                getattr(tr, method)(*args, **kwargs)
        except Exception:
            pass

    def _boot(self, level, cat, msg, kv=None, exc=False):
        """A line of the job's start (or of a reconnect): to every symbol's trace, or kept until the first one exists."""
        try:
            import traceback
            rec = (time.time(), level, cat, msg, kv, traceback.format_exc() if exc else None)
            if self._tracers:
                for tr in list(self._tracers.values()):
                    tr.boot([rec])
            else:
                self._boot_lines.append(rec)
                del self._boot_lines[:-500]
        except Exception:
            pass

    def _boot_flush(self):
        """The job ends before any symbol's loop started: its lines go to the log of the symbol it was started for."""
        if self._boot_lines and not self._tracers:
            self._tracer(self.symbols[0] if self.symbols else (self.target_symbol or 'bot'))

    def _order_observed(self, request, result, refused=False, ms=None):
        """MT5PositionHelper._send: every order request and its result, to the trace of its symbol (inside mt5_lock)."""
        self._trace(self._symbol_of((request or {}).get('symbol')), 'order', request, result, refused, ms)

    def _write_failed(self, symbol, what, path, err):
        """A file of the old dashboard could not be written (a full or missing disk): a WARN in the log, a console
        line at most once a minute per file, and trading goes on -- a write error never reaches the decisions."""
        try:
            last = getattr(self, '_write_failed_t', {})
            self._write_failed_t = last
            now = time.time()
            if now - last.get(path, -1e18) >= 60.0:
                last[path] = now
                print(f"[{symbol}] Error: could not write {path}: {err}")
        except Exception:
            pass
        self._trace(symbol, 'write_failed', what, path, err)

    # ── Day-of-week mapping for trading_window config ──
    _DAY_NAME_TO_NUM = {
        'monday': 0, 'mon': 0,
        'tuesday': 1, 'tue': 1, 'tues': 1,
        'wednesday': 2, 'wed': 2,
        'thursday': 3, 'thu': 3, 'thurs': 3,
        'friday': 4, 'fri': 4,
        'saturday': 5, 'sat': 5,
        'sunday': 6, 'sun': 6,
    }

    @classmethod
    def _day_time_to_week_minutes(cls, day, time_str):
        """Convert (day_name, 'HH:MM') to minutes since Monday 00:00."""
        d = cls._DAY_NAME_TO_NUM.get(str(day).strip().lower(), 0)
        try:
            hh, mm = str(time_str).strip().split(':')
            return d * 1440 + int(hh) * 60 + int(mm)
        except (ValueError, AttributeError):
            return d * 1440

    def _is_in_trading_window(self, now_dt, window_cfg):
        """Return True if `now_dt` falls inside the configured trading window.

        Window may wrap past Sunday (e.g. Friday 22:00 → Monday 06:00).
        If config is missing or `enabled` is false, always returns True.
        """
        if not window_cfg or not window_cfg.get('enabled', False):
            return True
        start = self._day_time_to_week_minutes(
            window_cfg.get('start_day', 'Monday'),
            window_cfg.get('start_time', '00:00'),
        )
        end = self._day_time_to_week_minutes(
            window_cfg.get('end_day', 'Saturday'),
            window_cfg.get('end_time', '00:00'),
        )
        now_min = now_dt.weekday() * 1440 + now_dt.hour * 60 + now_dt.minute
        if start == end:
            return True   # 24/7 window
        if start < end:
            return start <= now_min < end
        # Wrap-around window (e.g. Fri 22:00 → Mon 06:00)
        return now_min >= start or now_min < end

    def _resolve_symbol_alias(self, symbol):
        """Resolve configured symbol to the best matching broker symbol name."""
        info = mt5.symbol_info(symbol)
        if info is not None:
            return symbol

        base = symbol.rstrip('mM')
        patterns = [f"{symbol}*", f"{base}*", f"*{base}*"]
        candidates = []
        seen = set()
        for pattern in patterns:
            for cand in (mt5.symbols_get(pattern) or []):
                if cand.name in seen:
                    continue
                seen.add(cand.name)
                candidates.append(cand)

        if not candidates:
            return symbol

        disabled_mode = getattr(mt5, 'SYMBOL_TRADE_MODE_DISABLED', None)

        def _score(cand):
            name = cand.name
            score = 0
            if name == symbol:
                score += 200
            if name.startswith(symbol):
                score += 120
            if name.startswith(base):
                score += 90
            if base and base in name:
                score += 50
            if getattr(cand, 'visible', False):
                score += 15
            if getattr(cand, 'select', False):
                score += 10
            if disabled_mode is not None and getattr(cand, 'trade_mode', None) != disabled_mode:
                score += 8
            return (score, -len(name))

        best = max(candidates, key=_score)
        return best.name

    def _build_symbol_map(self):
        """Build configured→resolved MT5 symbol map for this session."""
        self.symbol_map = {}
        for symbol in self.symbols:
            resolved = self._resolve_symbol_alias(symbol)
            self.symbol_map[symbol] = resolved
            if resolved == symbol:
                print(f"✓ Symbol mapped: {symbol}")
            else:
                print(f"✓ Symbol mapped: {symbol} -> {resolved}")
        
    def load_credentials(self):
        """Step 1: Load MT5 credentials from JSON file"""
        if DEMO_BRANCH and self.mode != 'demo':
            print(f"✗ This is the demo branch {DEMO_BRANCH}: mode '{self.mode}' is refused, it trades on demo only")
            self._boot('ERROR', 'START', f"mode '{self.mode}' refused: the demo branch {DEMO_BRANCH} trades on demo only")
            return False
        try:
            json_path = Path(__file__).parent / 'mt5_credentials.json'
            with open(json_path, 'r') as f:
                credentials = json.load(f)

            if self.mode not in credentials:
                raise ValueError(f"Invalid mode '{self.mode}'. Must be 'demo' or 'live'")

            self.credentials = credentials[self.mode]
            print(f"✓ Credentials loaded for {self.mode.upper()} account")
            self._boot('INFO', 'START', f'credentials loaded for the {self.mode} account')
            return True
        except FileNotFoundError:
            print(f"✗ Error: mt5_credentials.json not found")
            self._boot('ERROR', 'START', 'mt5_credentials.json not found')
            return False
        except json.JSONDecodeError:
            print("✗ Error: Invalid JSON format in mt5_credentials.json")
            self._boot('ERROR', 'START', 'mt5_credentials.json is not valid JSON')
            return False
    
    def load_symbols(self):
        """Step 2: Load symbols configuration from JSON file"""
        try:
            json_path = Path(__file__).parent / 'symbols.json'
            with open(json_path, 'r') as f:
                self.symbols_config = json.load(f)
            
            sym_list = self.symbols_config.get('symbols', [])
            if not sym_list:
                print("✗ Warning: No symbols found in symbols.json")
                return False

            # Build per-symbol config lookup from the array (only active symbols)
            self.symbols = []
            self.symbol_configs = {}
            skipped = []
            for entry in sym_list:
                name = entry.get('symbol', '')
                if not name:
                    continue
                if not entry.get('is_active', True):
                    skipped.append(name)
                    continue
                self.symbols.append(name)
                self.symbol_configs[name] = entry

            if skipped:
                print(f"⊘ Skipped inactive symbols: {', '.join(skipped)}")

            # ── Single-symbol mode: filter to target_symbol only ──
            if self.target_symbol:
                # Match case-insensitively against configured symbol names
                matched = [s for s in self.symbols if s.upper() == self.target_symbol]
                if not matched:
                    print(f"✗ Error: Symbol '{self.target_symbol}' not found in symbols.json")
                    print(f"  Available: {', '.join(self.symbols)}")
                    self._boot('ERROR', 'START', f"symbol {self.target_symbol!r} not in symbols.json "
                               f"(active: {', '.join(self.symbols) or 'none'})")
                    return False
                self.symbols = matched
                self.symbol_configs = {s: self.symbol_configs[s] for s in matched}
                print(f"⚡ Single-symbol mode: {matched[0]}")

            if not self.symbols:
                print("✗ Warning: No valid symbols in symbols.json")
                self._boot('ERROR', 'START', 'no valid symbol in symbols.json')
                return False

            print(f"✓ Loaded {len(self.symbols)} symbols: {', '.join(self.symbols)}")
            return True
        except FileNotFoundError:
            print(f"✗ Error: symbols.json not found")
            self._boot('ERROR', 'START', 'symbols.json not found')
            return False
        except json.JSONDecodeError:
            print("✗ Error: Invalid JSON format in symbols.json")
            self._boot('ERROR', 'START', 'symbols.json is not valid JSON')
            return False
    
    def initialize_mt5(self):
        """Step 3: Initialize and login to MT5. The login only on a terminal that shows no account for
        _ACCOUNT_GRACE_S (a first None or login-0 answer can be momentary, and an IPC error means the account is not
        known: no login, retried later); a terminal that holds this bot's account (login and server of the
        credentials) is used as it is, and one that holds any other account is refused (TERMINAL_IN_USE) and left
        alone. Then the demo-account checks. Before all that, a demo bot whose terminal_path names the live bots'
        MetaTrader 5 (or is empty) is refused before any terminal call (LIVE_TERMINAL_PATH): it never attaches."""
        print(f"\n{'='*60}")
        print(f"  Initializing MT5 - {self.mode.upper()} Account")
        print(f"{'='*60}\n")
        
        # Never the live bots' MetaTrader 5: refused before mt5.initialize() could attach to it
        problem = self._terminal_path_problem()
        if problem:
            self._init_problem = problem
            print(f"✗ Refused before attaching to any terminal: {problem}")
            self._log_limited('LIVE_TERMINAL_PATH', problem, {
                'terminal_path': (self.credentials or {}).get('terminal_path'), 'live_terminal': _LIVE_TERMINAL_PATHS[0]})
            return False

        # Initialize MT5
        if not mt5.initialize(path=self.credentials['terminal_path']):
            self._init_problem = f'initialize failed: {mt5.last_error()}'
            print(f"✗ MT5 initialization failed: {mt5.last_error()}")
            self._boot('ERROR', 'TERMINAL', f'MT5 initialize failed: {self._init_problem}')
            return False

        print(f"✓ MT5 initialized successfully")
        print(f"✓ MT5 version: {mt5.version()}")
        self._boot('INFO', 'TERMINAL', 'MT5 initialized', {'version': mt5.version()})

        # The account the terminal holds before any login: a login switches the account of EVERY process attached
        # to the terminal (the bots of another slot, a live bot), so this bot logs in only on a terminal that shows
        # no account for the whole grace period, and never on one that holds another account (_account_held).
        held, unknown = self._account_held()
        if unknown is not None:
            self._init_problem = unknown
            print(f"✗ Not logging in: {unknown}; detached, trying again later")
            mt5.shutdown()                  # detach; the terminal and its account are left as they are
            return False
        if held is not None and not self._is_own_account(held):
            problem = self._terminal_in_use_problem(held)
            self._init_problem = problem
            print(f"✗ Refused: {problem}")
            self._terminal_in_use(problem, held)
            mt5.shutdown()                  # detach; the terminal and its account are left as they are
            return False
        if held is None:
            # Login to MT5 account (the terminal showed no account for _ACCOUNT_GRACE_S)
            print(f"… the terminal showed no account for {_ACCOUNT_GRACE_S:g} s: logging in")
            authorized = mt5.login(
                login=self.credentials['login_id'],
                password=self.credentials['login_pass'],
                server=self.credentials['server']
            )

            if not authorized:
                error = mt5.last_error()
                self._init_problem = f'login failed: {error}'
                print(f"✗ Login failed: {error}")
                self._boot('ERROR', 'ACCOUNT', f'login failed: {error}', {'server': self.credentials.get('server')})
                mt5.shutdown()
                return False
        else:
            print(f"✓ The terminal already holds this bot's account {held.login} ({held.server}): no login")
            self._boot('INFO', 'ACCOUNT', f"no login: the terminal already holds this bot's account {held.login} "
                       f"({held.server})", {'login': held.login, 'server': held.server})

        # Get account info
        account_info = mt5.account_info()
        if account_info is None:
            self._init_problem = 'no account info'
            print("✗ Failed to get account info")
            self._boot('ERROR', 'ACCOUNT', 'logged in, but account_info() returned None')
            mt5.shutdown()
            return False

        # Only ever this branch's demo account: a demo, hedging account with the login of the credentials
        problem = self._login_problem(account_info)
        if problem:
            self._init_problem = problem
            print(f"✗ Refused: {problem}")
            self._boot('ERROR', 'ACCOUNT', f'refused, not trading: {problem}', {
                'login': getattr(account_info, 'login', None), 'trade_mode': getattr(account_info, 'trade_mode', None),
                'margin_mode': getattr(account_info, 'margin_mode', None)})
            mt5.shutdown()
            return False
        self._account_login = account_info.login
        self._init_problem = None
        self._limited_logged = {}
        self._boot('INFO', 'ACCOUNT', f"{'logged in: ' if held is None else ''}account {account_info.login} on "
                   f'{account_info.server}; checks passed (a demo account, a hedging account, the login of the '
                   'credentials)', {
                       'login': account_info.login, 'server': account_info.server,
                       'trade_mode': getattr(account_info, 'trade_mode', None),
                       'margin_mode': getattr(account_info, 'margin_mode', None),
                       'balance': account_info.balance, 'equity': account_info.equity,
                       'leverage': account_info.leverage, 'currency': getattr(account_info, 'currency', None)})

        print(f"\n{'='*60}")
        print(f"  Login Successful - {self.mode.upper()} Account")
        print(f"{'='*60}")
        print(f"Login ID: {account_info.login}")
        print(f"Server: {account_info.server}")
        print(f"Balance: ${account_info.balance:.2f}")
        print(f"Equity: ${account_info.equity:.2f}")
        print(f"Leverage: 1:{account_info.leverage}")
        print(f"{'='*60}\n")
        
        self.mt5_initialized = True
        
        # Initialize position helper with mt5 instance
        self.position_helper = MT5PositionHelper(mt5)
        self._install_order_guard()

        # Resolve configured symbols to broker symbol names (suffix/alias safe)
        self._build_symbol_map()
        heartbeat_symbol = self._resolve_symbol_alias('EURUSD')

        # Subscribe all traded symbols + EURUSD (used for server-time)
        # symbol_select adds a symbol to Market Watch so live data flows
        subscribe_symbols = list(set(self.symbol_map.values())) + [heartbeat_symbol]
        for sym in subscribe_symbols:
            selected = mt5.symbol_select(sym, True)
            if selected:
                print(f"✓ Subscribed to {sym}")
            else:
                prefix = sym[:6] if len(sym) >= 6 else sym
                matches = mt5.symbols_get(f"{prefix}*") or []
                candidates = ', '.join(s.name for s in matches[:8]) if matches else 'none'
                print(f"✗ Failed to subscribe {sym}: {mt5.last_error()} | candidates: {candidates}")
                self._boot('WARN', 'TERMINAL', f'could not subscribe {sym}: {mt5.last_error()}', {'candidates': candidates})
        self._boot('INFO', 'TERMINAL', 'symbols: ' + ', '.join(f'{k} -> {v}' for k, v in self.symbol_map.items()),
                   {'subscribed': subscribe_symbols})

        return True
    
    def _save_symbol_data(self, symbol, data):
        """Save symbol data to JSON file on C: drive (thread-safe). A write that fails is logged, not raised."""
        import os
        output_dir = OUTPUT_DIR
        json_path = os.path.join(output_dir, f'{symbol}.json')
        try:
            os.makedirs(output_dir, exist_ok=True)
            with self.thread_lock:
                with open(json_path, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
        except Exception as e:
            self._write_failed(symbol, f'{symbol}.json', json_path, e)

    def _save_account_data(self, account_info, symbol=None):
        """Save account data to dedicated account.json (thread-safe). A write that fails is logged, not raised: it is
        made before the poll decides, so a full disk would otherwise stop the trading."""
        import os
        from datetime import datetime
        output_dir = OUTPUT_DIR
        json_path = os.path.join(output_dir, 'account.json')
        account_info['last_updated'] = datetime.now(tz=timezone.utc).isoformat()
        try:
            os.makedirs(output_dir, exist_ok=True)
            with self.thread_lock:
                with open(json_path, 'w') as f:
                    json.dump(account_info, f, indent=2, default=str)
        except Exception as e:
            self._write_failed(symbol or self._symbol_of(None), 'account.json', json_path, e)
    
    def _save_daily_trades(self, symbol, mt5_symbol=None):
        """Fetch today's closed deals for a symbol and save to per-symbol daily_trade folder (thread-safe)"""
        import os
        from datetime import datetime
        
        # Per-symbol folder: C:\Alcadeias\daily_trade\{symbol}\
        output_dir = os.path.join(OUTPUT_DIR, DAILY_TRADE_SUBDIR, symbol)
        os.makedirs(output_dir, exist_ok=True)
        
        # Use server time for the filename so it matches broker's trading day
        with self.mt5_lock:
            server_now = self.position_helper._get_server_time()
        filename = server_now.strftime('%d_%b_%Y').lower() + '.json'
        json_path = os.path.join(output_dir, filename)
        
        # Fetch today's closed deals for this symbol (server-time aware)
        deal_symbol = mt5_symbol or symbol
        with self.mt5_lock:
            today_deals = self.position_helper.get_today_deals(deal_symbol)
        
        # Calculate summary using net_profit (includes commission+swap+fee)
        total_net = sum(d.get('net_profit', d['profit']) for d in today_deals)
        total_volume = sum(d['volume'] for d in today_deals)
        avg_net = round(total_net / len(today_deals), 2) if today_deals else 0
        
        data = {
            'symbol': symbol,
            'date': server_now.strftime('%d %b %Y'),
            'server_date': server_now.strftime('%Y-%m-%d'),
            'server_time': server_now.isoformat(),
            'last_updated': datetime.now(tz=timezone.utc).isoformat(),
            'deal_count': len(today_deals),
            'total_profit': round(total_net, 2),
            'total_volume': round(total_volume, 4),
            'avg_profit': avg_net,
            'deals': today_deals,
        }
        
        with self.thread_lock:
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
    
    def _save_historical_summary(self, symbol, mt5_symbol=None):
        """Fetch last 10 years of deal history for a specific symbol and save to its folder (thread-safe)"""
        import os
        from datetime import datetime
        
        # Per-symbol folder: <OUTPUT_DIR>/daily_trade/{symbol}/
        output_dir = os.path.join(OUTPUT_DIR, DAILY_TRADE_SUBDIR, symbol)
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, HISTORICAL_SUMMARY_FILENAME)
        
        # Fetch only this symbol's deals for the configured history period
        deal_symbol = mt5_symbol or symbol
        with self.mt5_lock:
            all_deals = self.position_helper.get_deals_since(days=HISTORICAL_SUMMARY_DAYS, symbol=deal_symbol)
        
        total_net = sum(d.get('net_profit', d['profit']) for d in all_deals)
        total_volume = sum(d['volume'] for d in all_deals)
        avg_net = round(total_net / len(all_deals), 2) if all_deals else 0
        
        summary = {
            'symbol': symbol,
            'last_updated': datetime.now(tz=timezone.utc).isoformat(),
            'period': 'Last 10 years',
            'total_deals': len(all_deals),
            'total_profit': round(total_net, 2),
            'total_volume': round(total_volume, 4),
            'avg_profit': avg_net,
        }
        
        with self.thread_lock:
            with open(json_path, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
    
    def _log_event(self, symbol, event, tag, details=None, server_time=None):
        """Append a strategy event to the per-symbol log file (thread-safe).
        
        Args:
            symbol: Trading symbol
            event: Short event name (e.g. 'BUY_EXECUTED', 'CLOSE_SELL', 'SIGNAL_BUY')
            tag: Category tag (e.g. 'ENTRY', 'EXIT', 'SIGNAL', 'ERROR')
            details: Optional dict with extra info (volume, profit, response, etc.)
            server_time: Optional pre-fetched server time (avoids extra MT5 lock)
        """
        import os
        from datetime import datetime

        if server_time is None:
            server_time = datetime.now(tz=timezone.utc)

        entry = {
            'time': server_time.isoformat(),
            'utc_time': datetime.now(tz=timezone.utc).isoformat(),
            'symbol': symbol,
            'event': event,
            'tag': tag,
            'details': details or {},
        }

        log_path = self._log_path(symbol)

        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with self.thread_lock:
                # Load existing log
                try:
                    with open(log_path, 'r') as f:
                        log_data = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    log_data = []

                # Prepend (newest first) and cap
                log_data.insert(0, entry)
                log_data = log_data[:STRATEGY_LOG_MAX_ENTRIES]

                with open(log_path, 'w') as f:
                    json.dump(log_data, f, indent=2, default=str)
        except Exception as e:
            self._write_failed(symbol, 'the strategy log', log_path, e)
        # the same event in the text log
        self._trace(symbol, 'event', event, tag, details, server_time)

    @staticmethod
    def _log_path(symbol):
        """The symbol's strategy log: OUTPUT_DIR/logs/<symbol>_<STRATEGY_LOG_FILENAME> (newest entry first)."""
        return os.path.join(OUTPUT_DIR, 'logs', f'{symbol}_{STRATEGY_LOG_FILENAME}')

    def _log_entries(self, symbol):
        """The entries of the symbol's strategy log, newest first; [] without a (readable) log."""
        try:
            with self.thread_lock:
                with open(self._log_path(symbol), 'r') as f:
                    data = json.load(f)
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    # ───────────────────── per-basket state, loss pause, virtual balance ─────────────────────
    def _state_path(self, symbol):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, f'{symbol}_state.json')

    def _load_state(self, symbol):
        """The persisted state ({'basket': ..., 'last_close': ...}) or None: no file, unreadable, or written
        for another symbol / magic number (then it is rebuilt from the terminal)."""
        path = self._state_path(symbol)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            print(f"[{symbol}] note: state file {path} unreadable ({e}); rebuilding it from the terminal")
            self._trace(symbol, 'state_note', 'WARN', f'the state file {path} is unreadable ({e!r}): it is rebuilt from '
                        'the terminal')
            return None
        if not isinstance(data, dict) or data.get('symbol') != symbol or data.get('magic') != MAGIC:
            print(f"[{symbol}] note: state file {path} is not this bot's (symbol/magic); rebuilding it from the terminal")
            self._trace(symbol, 'state_note', 'WARN', f"the state file {path} is not this bot's (symbol / magic): it is "
                        'rebuilt from the terminal')
            return None
        return {'basket': data.get('basket'), 'last_close': data.get('last_close')}

    def _save_state(self, symbol, state):
        """Write the state atomically (a crash mid-write leaves the previous file)."""
        path = self._state_path(symbol)
        data = {'version': _STATE_VERSION, 'symbol': symbol, 'magic': MAGIC, 'design': DESIGN_NAME,
                'saved_at': time.time(), 'basket': state.get('basket'), 'last_close': state.get('last_close')}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with self.thread_lock:
                with open(tmp, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp, path)
        except OSError as e:
            print(f"[{symbol}] Error: could not write the state file {path}: {e}")
            self._trace(symbol, 'state_note', 'ERROR', f'could not write the state file {path}: {e!r} (a restart now '
                        'would rebuild the basket from the terminal)')
            return
        self._trace(symbol, 'state_saved', state)

    def _usd_per_price_of(self, symbol, trade_symbol, mtqty):
        """USD per unit (mtqty lots) for a move of 1.0 in price = contract_size x mtqty (gold 100 x 0.01 = 1.0,
        BTC 1 x 0.01 = 0.01). The contract size is the terminal's symbol_info().trade_contract_size, else
        CONTRACT_SIZE_FALLBACK by symbol prefix. Read once; None when unknown."""
        if trade_symbol in self._usd_per_price:
            return self._usd_per_price[trade_symbol]
        info = mt5.symbol_info(trade_symbol)
        size, source = None, None
        try:
            raw = getattr(info, 'trade_contract_size', None) if info is not None else None
            size = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            size = None
        if size is not None and size > 0:
            source = 'terminal'
        else:
            size = None
            for prefix, value in CONTRACT_SIZE_FALLBACK.items():
                if str(trade_symbol).upper().startswith(str(prefix).upper()):
                    size, source = float(value), 'CONTRACT_SIZE_FALLBACK'
                    break
        if size is None:
            if info is not None:
                self._usd_per_price[trade_symbol] = None
            return None
        usd = size * mtqty
        if info is not None:          # a missing symbol_info may be transient: ask again next time
            self._usd_per_price[trade_symbol] = usd
            print(f"[{symbol}] contract size {size:g} ({source}): {usd:g} USD per unit for a 1.0 price move")
        return usd

    def _virtual_balance(self, now):
        """VIRTUAL_START_BALANCE + profit + swap + commission + fee of this bot's deals since VIRTUAL_START_DATE,
        added up in time order (the backtester's balance of a fresh account). When the terminal gives no
        history, the last value read (or the start balance): the smaller, safe unit."""
        start = _virtual_start_ts()
        deals = self.position_helper.get_bot_deals(_utc(start), _utc(now + 86400))
        if deals is None:
            return self._virtual_balance_last if self._virtual_balance_last is not None else float(VIRTUAL_START_BALANCE)
        bal = float(VIRTUAL_START_BALANCE)
        for d in sorted(deals, key=lambda d: (_deal_time(d), int(getattr(d, 'ticket', 0) or 0))):
            if _deal_time(d) >= start:
                bal += _deal_net(d)
        self._virtual_balance_last = bal
        return bal

    def _basket_pnl(self, ids, since, now):
        """Realised P/L of the positions `ids` (profit + swap + commission + fee of all their deals, rounded to
        cents) once the history holds a closing deal for every one of them, else None. Also returns the time
        of the last closing deal."""
        if not ids:
            return None, None
        frm = (since if since else now) - 2 * 86400
        deals = self.position_helper.get_bot_deals(_utc(frm), _utc(now + 86400))
        if deals is None:
            return None, None
        idset = {int(i) for i in ids}
        mine = [d for d in deals if getattr(d, 'position_id', None) in idset]
        outs = [d for d in mine if _is_out_deal(d)]
        if not idset <= {getattr(d, 'position_id', None) for d in outs}:
            return None, None
        pnl = 0.0
        for d in sorted(mine, key=lambda d: (_deal_time(d), int(getattr(d, 'ticket', 0) or 0))):
            pnl += _deal_net(d)
        return round(pnl, 2), max(_deal_time(d) for d in outs)

    def _resolve_last_close(self, state, now):
        """Replace the provisional result of the last closed basket (its P/L at the close decision) by the
        realised one from the deal history; True when the state changed. Gives up after _RESOLVE_ATTEMPTS
        polls (the decision-time P/L then stands)."""
        lc = state.get('last_close')
        if not lc or lc.get('resolved'):
            return False
        lc['attempts'] = int(lc.get('attempts', 0)) + 1
        pnl, t_out = self._basket_pnl(lc.get('ids') or [], lc.get('open_time'), now)
        if pnl is not None:
            lc.update(pnl=pnl, lost=bool(pnl < 0), resolved=True, source='history')
            if lc.get('time_from_history') and t_out is not None:
                lc['time'] = float(t_out)   # closed outside the bot: the pause runs from its closing deal
            return True
        if lc['attempts'] >= _RESOLVE_ATTEMPTS:
            lc['resolved'] = True
            return True
        return False

    def _last_close_from_history(self, now):
        """The last basket this bot closed, from the deal history (used when there is no state file): the
        time of its last closing deal and its realised P/L. None when there is none in the look-back."""
        look = max(float(LOSS_COOLDOWN_S or 0), float(REENTRY_COOLDOWN_SECONDS)) + 86400.0
        deals = self.position_helper.get_bot_deals(_utc(now - look), _utc(now + 86400))
        if not deals:
            return None
        outs = [d for d in deals if _is_out_deal(d)]
        if not outs:
            return None
        t_last = max(_deal_time(d) for d in outs)
        last = [d for d in outs if t_last - _deal_time(d) <= 60.0]
        ids = {getattr(d, 'position_id', None) for d in last} - {None, 0}
        group = [d for d in deals if getattr(d, 'position_id', None) in ids] if ids else last
        pnl = round(sum(_deal_net(d) for d in sorted(group, key=_deal_time)), 2)
        return {'time': float(t_last), 'pnl': pnl, 'lost': bool(pnl < 0), 'resolved': True,
                'source': 'history_rebuild', 'reason': None, 'side': None, 'ids': sorted(int(i) for i in ids),
                'open_time': None, 'attempts': 0}

    def _vol_unit_at(self, trade_symbol, t_open):
        """The volatility unit a basket opened at `t_open` (seconds) saw: the unit of the last VOL_TF bar
        closed before the bar that was forming at that time."""
        tf = getattr(mt5, _tf_name(VOL_TF), None)
        if tf is None:
            return None
        rates = mt5.copy_rates_from(trade_symbol, tf, _utc(int(t_open)), RSI_CANDLE_COUNT)
        if rates is None or len(rates) - 1 < _MIN_CLOSED_BARS:
            return None                 # too short a history: the basket waits for the unit of a full one
        v = Indicator.vol_unit(rates['close'][:-1], VOL_LEN)
        return v if v > 0 else None

    def _new_basket(self, side, units, levels, opened_at, opened_by='bot'):
        return dict(levels, side=side, units=int(units), ids=[], first_time=None, opened_at=float(opened_at),
                    opened_by=opened_by, ladder_armed=False, close_pending=False,
                    levels_pending=False, vol_source='open' if levels.get('vol_unit') is not None else None,
                    last_profit=0.0)

    def _rebuild_basket(self, trade_symbol, side, plist, mtqty, usd_per_price, now):
        """A basket found open without its state (first start, lost file, another basket): the unit from the
        oldest position's volume, the volatility unit from the bars at its open time. The ladder starts
        disarmed (its arming is a path of votes that cannot be read back)."""
        first = plist[0]
        units = max(1, int(round(float(first.volume) / float(mtqty)))) if mtqty else 1
        v_raw = self._vol_unit_at(trade_symbol, _pos_time(first)) if VOL_TF is not None else None
        complete = levels_complete(v_raw, usd_per_price)
        levels = basket_levels(v_raw if complete else None, usd_per_price)
        b = self._new_basket(side, units, levels, now, opened_by='rebuild')
        b.update(ids=[_pos_id(p) for p in plist], first_time=_pos_time(first),
                 levels_pending=not complete, vol_source='bars_at_open' if complete and VOL_TF is not None else None)
        return b

    def _finish_outside_close(self, state, basket, now):
        """A basket whose positions are gone without a close of this bot (closed from the terminal, by the
        broker, or while the bot was down): book it as closed now; the P/L and the time of its closing deals
        replace that when the history has them."""
        profit = basket.get('last_profit') or 0.0
        state['last_close'] = {
            'time': float(now), 'pnl': profit, 'lost': bool(profit < 0), 'resolved': False, 'source': 'last_seen',
            'reason': 'closed_outside', 'side': basket.get('side'), 'ids': list(basket.get('ids') or []),
            'open_time': basket.get('first_time') or basket.get('opened_at'),     # (an entry never listed: its fill)
            'attempts': 0, 'time_from_history': True}
        state['basket'] = None

    @staticmethod
    def _unlisted(basket):
        """{position id: fill time} of the basket's legs the terminal has not listed yet (_record_fill)."""
        return _unlisted_fills(basket)

    @staticmethod
    def _set_unlisted(basket, unlisted):
        if unlisted:
            basket['unlisted'] = [{'id': int(i), 'time': float(t)} for i, t in unlisted.items()]
        else:
            basket.pop('unlisted', None)

    def _record_fill(self, basket, response, now):
        """
        A leg the terminal reports filled -- the entry of a basket, or an add -- is a leg of the basket from then on,
        listed or not. Its position id -- on a hedging account the position a market order opens has the order's
        ticket as its identifier (fake_mt5 and the backtester's SimMT5 answer so) -- joins the basket's ids at once, and
        `unlisted` with its fill time until a positions read lists it (kept _PENDING_FILL_S). It is saved with the
        state, so a terminal outage or a restart in the ~1-2 s before the next positions read still counts the leg: an
        entry gone then (its backstop) is a basket closed outside the bot (booked with its realised P/L, then the pause
        after a loss), not a fill that "never showed up"; a leg gone with another still there is a leg closed outside
        the bot (LEG_CLOSED_OUTSIDE: the rest is closed, the whole basket booked), not a new basket to take over. False
        without a ticket (then the next positions read adds it).
        """
        try:
            pid = int(getattr(response, 'order', 0) or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid <= 0:
            return False
        ids = list(basket.get('ids') or [])
        if pid not in ids:
            ids.append(pid)
        basket['ids'] = ids
        unlisted = self._unlisted(basket)
        unlisted[pid] = float(now)
        self._set_unlisted(basket, unlisted)
        return True

    def _sync_basket(self, symbol, trade_symbol, state, buy_positions, sell_positions, mtqty, usd_per_price, now):
        """Match the state's basket with this bot's open positions. True when the state changed. A basket the bot
        has just opened is kept _PENDING_FILL_S seconds while the terminal does not list its position yet (the
        terminal answers asynchronously; dropped at once, the next poll saw "flat" and opened a second basket), and so
        is an add -- both by the position id recorded from the order (_record_fill; a position listed under another id
        while such a leg is not listed is that leg). An entry gone after that without ever being listed is a basket
        closed outside the bot, booked as such. A basket some of whose legs are gone without a close of this bot -- an
        add too, listed yet or not -- is marked to close the rest at once (close_pending, outside_ids); _after_close
        then books the whole basket as closed outside the bot."""
        nb = buy_positions['count'] if buy_positions else 0
        ns = sell_positions['count'] if sell_positions else 0
        basket = state.get('basket')
        if nb and ns:
            return False        # both sides open: the strategy holds still; the books stay as they are
        if not nb and not ns:
            if basket is None:
                return False
            if fill_pending(basket, now):
                return False                # filled, not listed yet (the entry, or an add): still this bot's basket
            if basket.get('ids'):
                never_listed = basket.get('first_time') is None
                self._finish_outside_close(state, basket, now)
                if never_listed:
                    print(f"[{symbol}] note: the {basket.get('side')} entry {basket.get('ids')} is gone before the "
                          f"terminal listed it (its backstop while the bot or the terminal was down?): booked as "
                          f"closed outside the bot, its result from the deal history")
                else:
                    print(f"[{symbol}] note: the {basket.get('side')} basket was closed outside the bot")
            else:
                print(f"[{symbol}] note: the {basket.get('side')} fill of {basket.get('opened_at')} never showed up "
                      f"as a position in {_PENDING_FILL_S:g} s; the basket is dropped")
                state['basket'] = None      # an open that never showed up as a position
            return True
        side = 'BUY' if nb else 'SELL'
        plist = _sorted_positions((buy_positions if nb else sell_positions).get('positions'))
        if not plist:
            return False
        ids = [_pos_id(p) for p in plist]
        known = list(basket.get('ids') or []) if basket is not None else []
        unlisted = self._unlisted(basket)               # legs recorded from their order, not listed yet
        if basket is not None and basket.get('side') == side and (not known or set(ids) & set(known) or unlisted):
            new = [i for i in ids if i not in known]
            waiting = [i for i in known if i in unlisted and i not in ids]
            while new and waiting:                      # a leg listed under another id than its order's ticket
                old, pid = waiting.pop(0), new.pop(0)
                known = [pid if k == old else k for k in known]
                unlisted.pop(old)
            for i in ids:
                unlisted.pop(i, None)                   # listed now
            young = {i for i, t in unlisted.items() if now - t < _PENDING_FILL_S}
            gone = [i for i in known if i not in ids and i not in young]
            changed = known != list(basket.get('ids') or []) or unlisted != self._unlisted(basket)
            if gone and not basket.get('close_pending'):
                # A leg closed outside the bot (its broker-side backstop while the bot or the terminal was down, a
                # stop-out, by hand): what is left is not the basket the design holds -- its stop would judge the
                # listed legs only and the ladder could add again. The other legs are closed at once (this poll's
                # decision, as a close to finish) and the whole basket is booked as closed outside the bot.
                basket['ids'] = known + new
                self._set_unlisted(basket, unlisted)
                basket['close_pending'] = True
                basket['outside_ids'] = sorted(set(gone) | set(basket.get('outside_ids') or []))
                print(f"[{symbol}] note: leg(s) {gone} of the {side} basket closed outside the bot: closing the "
                      f"other {len(ids)} and booking the basket as closed outside the bot")
                self._log_event(symbol, 'LEG_CLOSED_OUTSIDE', 'EXIT', {'side': side, 'legs_gone': gone,
                                                                       'legs_left': ids})
                return True
            if known and not new and not changed:
                return False
            if basket.get('first_time') is None:        # its first listing (the entry recorded from its order, or not)
                basket['first_time'] = _pos_time(plist[0])
            basket['ids'] = known + new
            self._set_unlisted(basket, unlisted)
            return True
        if basket is not None and basket.get('ids'):
            self._finish_outside_close(state, basket, now)
        state['basket'] = self._rebuild_basket(trade_symbol, side, plist, mtqty, usd_per_price, now)
        b = state['basket']
        print(f"[{symbol}] note: {side} basket of {len(plist)} position(s) taken over from the terminal: "
              f"unit {b['units']}, volatility unit {b.get('vol_unit')}, target/unit {b.get('target_usd_per_unit')}, "
              f"stop/unit {b.get('stop_usd_per_unit')}, gap {b.get('gap_px')}")
        return True

    def _after_close(self, symbol, state, side, close_response, positions, reason, now):
        """Book this bot's close of the basket: the loss pause starts at this close decision. A close that
        closed nothing changes nothing (it is decided again next poll, as the backtester does); a partial one -- a
        leg the terminal refused to close, or an add the terminal has not listed yet (_record_fill) and the close did
        not close either -- keeps the basket and closes the rest on the next polls. Returns the new last_close or
        None."""
        closed = int((close_response or {}).get('closed_count', 0) or 0)
        failed = int((close_response or {}).get('failed_count', 0) or 0)
        basket = state.get('basket')
        if closed <= 0:
            return None
        # (an add the poll's positions read did not list yet, but the close's own read did, was closed now with the rest)
        done = set()
        for t in (close_response or {}).get('closed_tickets') or []:
            try:
                done.add(int(t))
            except (TypeError, ValueError):
                continue
        young = [i for i, t in self._unlisted(basket).items() if now - t < _PENDING_FILL_S and i not in done]
        if failed > 0 or young:
            if basket is not None:
                basket['close_pending'] = True
                self._save_state(symbol, state)
            return None
        ids = list(basket.get('ids') or []) if basket is not None else []
        if not ids and positions and positions.get('positions'):
            ids = [_pos_id(p) for p in positions['positions']]
        profit = positions['total_profit'] if positions else 0.0
        outside = list(basket.get('outside_ids') or []) if basket is not None else []
        lc = {'time': float(now), 'pnl': profit, 'lost': bool(profit < 0), 'resolved': False, 'source': 'decision',
              'reason': 'closed_outside' if outside else reason, 'side': side, 'ids': ids,
              'open_time': basket.get('first_time') if basket is not None else None, 'attempts': 0}
        if outside:
            lc['outside_ids'] = outside
        state['last_close'] = lc
        state['basket'] = None
        with self.mt5_lock:
            if outside:
                # Legs closed outside the bot (_sync_basket): until the history has every leg, the result is what
                # the bot closed now plus what those legs realised -- or, not in the history yet, a loss.
                o_pnl, _ = self._basket_pnl(outside, lc['open_time'], now)
                lc['pnl'] = profit if o_pnl is None else round(profit + o_pnl, 2)
                lc['lost'] = True if o_pnl is None else bool(lc['pnl'] < 0)
            self._resolve_last_close(state, now)
        self._save_state(symbol, state)
        return lc

    @staticmethod
    def _order_done(response):
        """True when the terminal reports the market order as filled."""
        if response is None:
            return False
        done = (getattr(mt5, 'TRADE_RETCODE_DONE', 10009), getattr(mt5, 'TRADE_RETCODE_DONE_PARTIAL', 10010))
        return getattr(response, 'retcode', None) in done

    def _price_digits(self, trade_symbol):
        """The symbol's price digits (symbol_info().digits), read once; None when unknown."""
        if trade_symbol not in self._digits:
            info = mt5.symbol_info(trade_symbol)
            digits = getattr(info, 'digits', None) if info is not None else None
            if digits is None:
                return None
            self._digits[trade_symbol] = int(digits)
        return self._digits[trade_symbol]

    def _open_leg(self, side, trade_symbol, qty, stop_usd_per_unit, usd_per_price, quote):
        """
        The market order of a basket leg (the entry or an add). A design with a stop: with a broker-side backstop,
        sl = the fill (the decision quote: the ask of a buy, the bid of a sell) -/+ backstop_distance(), and no tp;
        it is never moved. A design without a stop (the live levers): the live request, its auto sl / tp.
        Returns (the order response, the backstop sent or None).
        """
        send = self.position_helper.buy if side > 0 else self.position_helper.sell
        if not design_has_stop():
            with self.mt5_lock:
                return send(trade_symbol, qty), None
        dist = backstop_distance(stop_usd_per_unit, usd_per_price)
        with self.mt5_lock:
            sl = 0.0
            if dist is not None and quote is not None:
                sl = quote - dist if side > 0 else quote + dist
                digits = self._price_digits(trade_symbol)
                sl = round(sl, digits) if digits is not None else sl
                sl = sl if sl > 0 else 0.0
            return send(trade_symbol, qty, sl=sl, tp=0.0, auto_sltp=False), sl

    # ───────────────────── the demo account: the only account this bot trades on ─────────────────────
    @staticmethod
    def _last_error():
        try:
            return mt5.last_error()
        except Exception as e:          # a broken terminal connection can raise instead of answering
            return repr(e)

    def _account_problem(self, acct=None, check_login=True):
        """
        Why the account the terminal is logged into is not this bot's right now (None = it is). Read at the start
        of every poll and before every order: with DEMO_BRANCH set it must be a demo account
        (trade_mode ACCOUNT_TRADE_MODE_DEMO) and the login initialize_mt5 remembered. Each slot should have its own
        MT5 installation, but any other process attached to the terminal (a live bot, the bot of another slot) can
        log it into another account at any time; this bot then waits and never logs in again over it. A bot that
        was not started through initialize_mt5 (a replay) takes the first demo account it sees as its own, so a
        later switch is still caught.
        """
        if acct is None:
            acct = mt5.account_info()
        if acct is None:
            return f'account_info() returned None (last_error {self._last_error()})'
        login = getattr(acct, 'login', None)
        demo = getattr(mt5, 'ACCOUNT_TRADE_MODE_DEMO', 0)
        mode = getattr(acct, 'trade_mode', None)
        self._last_account = (login, mode, getattr(acct, 'margin_mode', None))     # the trace's health line
        if DEMO_BRANCH and mode != demo:
            return f'account {login} is not a demo account (trade_mode {mode}, demo is {demo})'
        if check_login:
            if self._account_login is None:
                self._account_login = login
            elif login != self._account_login:
                return f'the terminal is logged into account {login}, not the demo account {self._account_login}'
        return None

    def _login_problem(self, acct):
        """Why the account initialize_mt5 has just logged into may not be traded (None = it may): a demo account
        (DEMO_BRANCH), a hedging account (the basket holds one position per fill), and the login of the
        credentials (not one another process switched the terminal to in the meantime)."""
        problem = self._account_problem(acct, check_login=False)
        if problem:
            return problem
        hedging = getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING', 2)
        mode = getattr(acct, 'margin_mode', None)
        if mode != hedging:
            return f'account {acct.login} is not a hedging account (margin_mode {mode}, hedging is {hedging})'
        want = (self.credentials or {}).get('login_id')
        if want is not None:
            try:
                same = int(acct.login) == int(want)
            except (TypeError, ValueError):
                same = False
            if not same:
                return f'the terminal is logged into account {acct.login}, not the login of the credentials ({want})'
        return None

    def _account_held(self):
        """
        The account the terminal holds right after mt5.initialize(), before any login: (account, None); (None, None)
        when it shows none for _ACCOUNT_GRACE_S; (None, why) when that cannot be known. An answer None or login 0 can
        be momentary -- an IPC timeout on a busy terminal, or a terminal that initialize() has just started, or that
        restarted (an update, a crash, a reboot), still logging into its saved account -- so it is read again about
        once a second for the grace period; an account that appears is this bot's (used) or another (TERMINAL_IN_USE).
        Not known (no login: the attempt fails and is retried with the back-off): an IPC error (-10000 to -10005), no
        terminal_info(), or a terminal connected to a trade server -- so logged into some account -- that shows none.
        """
        t_end = time.time() + _ACCOUNT_GRACE_S
        noted = False
        while True:
            try:
                acct = mt5.account_info()
            except Exception as e:              # (a broken connection can raise instead of answering)
                return None, f'account not known: account_info() raised {e!r}'
            if acct is not None and getattr(acct, 'login', None):
                return acct, None
            what = 'None' if acct is None else 'login 0'
            err = self._last_error()
            if _ipc_error(err):
                return None, f'account not known: account_info() answered {what} (last_error {err})'
            try:
                info = mt5.terminal_info()
            except Exception as e:
                return None, f'account not known: terminal_info() raised {e!r}'
            if info is None:
                return None, f'account not known: terminal_info() answered None (last_error {self._last_error()})'
            if time.time() >= t_end:
                if bool(getattr(info, 'connected', False)):
                    return None, (f'account not known: the terminal is connected to a trade server but shows no '
                                  f'account (account_info() answered {what} for {_ACCOUNT_GRACE_S:g} s)')
                return None, None
            if not noted:
                noted = True
                print(f"… the terminal shows no account yet (account_info() answered {what}, last_error {err}): "
                      f"reading it again for up to {_ACCOUNT_GRACE_S:g} s before any login")
            time.sleep(1.0)

    def _is_own_account(self, acct):
        """True when the account a terminal holds is this bot's: the login and the server of the credentials."""
        creds = self.credentials or {}
        try:
            same_login = int(acct.login) == int(creds.get('login_id'))
        except (TypeError, ValueError):
            return False
        want = str(creds.get('server') or '').strip().casefold()
        have = str(getattr(acct, 'server', '') or '').strip().casefold()
        return same_login and (not want or have == want)

    @staticmethod
    def _trade_mode_name(mode):
        names = {getattr(mt5, 'ACCOUNT_TRADE_MODE_DEMO', 0): 'demo', getattr(mt5, 'ACCOUNT_TRADE_MODE_CONTEST', 1): 'contest',
                 getattr(mt5, 'ACCOUNT_TRADE_MODE_REAL', 2): 'real'}
        return names.get(mode, f'trade_mode {mode}')

    def _terminal_in_use_problem(self, acct):
        creds = self.credentials or {}
        return (f"TERMINAL_IN_USE: the terminal at {creds.get('terminal_path')} is logged into another account "
                f"{acct.login} ({self._trade_mode_name(getattr(acct, 'trade_mode', None))}, "
                f"{getattr(acct, 'server', '?')}), not this bot's {creds.get('login_id')} ({creds.get('server')}); "
                f"give this slot its own MT5 installation")

    def _terminal_in_use(self, problem, acct):
        """initialize_mt5 found the terminal logged into another account and left it alone: an ERROR event
        TERMINAL_IN_USE, limited by _log_limited."""
        creds = self.credentials or {}
        self._log_limited('TERMINAL_IN_USE', problem, {
            'terminal_path': creds.get('terminal_path'), 'login': getattr(acct, 'login', None),
            'server': getattr(acct, 'server', None), 'trade_mode': self._trade_mode_name(getattr(acct, 'trade_mode', None)),
            'own_login': creds.get('login_id')})

    def _terminal_path_problem(self):
        """Why this demo bot may not attach to the terminal of its credentials (None = it may): terminal_path names the
        live bots' MetaTrader 5 (_LIVE_TERMINAL_PATHS), or is empty -- then initialize() attaches to a terminal it finds
        itself, on the server the live bots'."""
        if not DEMO_BRANCH:
            return None
        path = (self.credentials or {}).get('terminal_path')
        todo = (f'install a separate MetaTrader 5 for {_slot_name()} and set terminal_path in mt5_credentials.json to '
                f'its terminal64.exe')
        if not str(path or '').strip():
            return (f"LIVE_TERMINAL_PATH: terminal_path in mt5_credentials.json is empty, so initialize() would attach "
                    f"to a MetaTrader 5 it finds itself (on the server, the live bots'): {todo}")
        if _live_terminal(path):
            return (f"LIVE_TERMINAL_PATH: terminal_path {str(path).strip()} is the MetaTrader 5 of the live bots "
                    f"({_LIVE_TERMINAL_PATHS[0]}): {todo}")
        return None

    _LIMITED_EVENTS = ('TERMINAL_IN_USE', 'LIVE_TERMINAL_PATH')       # the events _log_limited writes

    def _log_limited(self, event, problem, details):
        """An ERROR event `event` (details + problem) for a problem initialize_mt5 refuses to start on: the first time
        the problem is seen, then at most every _LOG_REPEAT_S while it lasts, for each problem on its own (a terminal
        held in turn by two other accounts: each is logged, not every attempt) -- also across the launcher's restarts
        of app.py (a start reads the entries refused starts left at the head of the strategy log), so a problem that
        lasts does not fill the 200-entry log. True when it was logged."""
        symbol = self._symbol_of(None)
        now = time.time()
        seen = self._limited_logged.setdefault(event, {})        # problem -> when it was last logged
        if problem not in seen:
            at = self._logged_at(symbol, event, problem)
            if at is not None:
                seen[problem] = at
        if problem in seen and now - float(seen[problem]) < _LOG_REPEAT_S:
            return False
        if len(seen) >= 32:                    # (keep it small: a problem logged long ago is logged again anyway)
            for k in [k for k, t in seen.items() if now - float(t) >= _LOG_REPEAT_S]:
                del seen[k]
        seen[problem] = now
        self._log_event(symbol, event, 'ERROR', dict(details, problem=problem))
        return True

    def _logged_at(self, symbol, event, problem):
        """When the strategy log last got `event` for `problem` (epoch seconds), among the entries refused starts leave
        at its head (TERMINAL_IN_USE, LIVE_TERMINAL_PATH); None when it is not there: no log, or another entry comes
        first (the bot ran in between, so this is a new occurrence)."""
        from datetime import datetime
        for e in self._log_entries(symbol):
            if not isinstance(e, dict) or e.get('event') not in self._LIMITED_EVENTS:
                return None
            if e.get('event') == event and (e.get('details') or {}).get('problem') == problem:
                try:
                    return datetime.fromisoformat(str(e.get('utc_time'))).timestamp()
                except (TypeError, ValueError):
                    return None
        return None

    def _account_refused(self, symbol, problem, request=None, server_time=None):
        """The account is not this bot's: a WARNING and an ERROR event when the problem starts or changes."""
        if problem == self._account_bad:
            return
        self._account_bad = problem
        print(f"[{symbol}] WARNING: not trading: {problem}")
        details = {'problem': problem, 'demo_login': self._account_login}
        if request is not None:
            details['request'] = {k: request.get(k) for k in ('action', 'symbol', 'type', 'volume', 'position')
                                  if k in request}
        self._log_event(symbol, 'ACCOUNT_REFUSED', 'ERROR', details, server_time=server_time)

    def _account_ok(self, symbol, server_time=None):
        """At the start of a poll: True when the terminal holds this bot's demo account. Otherwise the poll decides
        nothing -- no sync with the positions of another account (they would book this bot's basket as closed),
        no order -- until the account is right again (then an ACCOUNT_OK event)."""
        with self.mt5_lock:
            problem = self._account_problem()
        if problem is not None:
            self._account_refused(symbol, problem, server_time=server_time)
            return False
        if self._account_bad is not None:
            print(f"[{symbol}] note: the terminal holds the demo account {self._account_login} again: trading")
            self._log_event(symbol, 'ACCOUNT_OK', 'SIGNAL', {'login': self._account_login, 'was': self._account_bad},
                            server_time=server_time)
            self._account_bad = None
        return True

    def _order_guard(self, request):
        """Before every order_send (MT5PositionHelper._send): account_info() is read again and nothing is sent
        unless it is still the demo account; a refused request is an ERROR event, and the polls after it decide
        nothing until the account is right again (_account_ok). (Called inside the caller's mt5_lock.)"""
        problem = self._account_problem()
        if problem is None:
            return True
        self._account_refused(self._symbol_of(request.get('symbol')), problem, request=request)
        return False

    def _symbol_of(self, trade_symbol):
        """The configured symbol of a terminal symbol name (the log files are named by it)."""
        for sym, resolved in self.symbol_map.items():
            if resolved == trade_symbol:
                return sym
        return trade_symbol or (self.symbols[0] if self.symbols else '?')

    def _install_order_guard(self):
        """_order_guard in front of every order_send of the helper the bot trades through (initialize_mt5 makes a
        new helper; a replay brings its own), and the trace's observer of every request and result behind it."""
        helper = self.position_helper
        if helper is not None and getattr(helper, 'order_guard', None) is None:
            helper.order_guard = self._order_guard
        if helper is not None and getattr(helper, 'order_observer', False) is None:
            helper.order_observer = self._order_observed

    def _poll_guard(self, symbol):
        """At the start of every poll: True when the poll may read the terminal and decide -- the terminal answers
        and is connected, and it holds this bot's demo account."""
        self._install_order_guard()
        with self.mt5_lock:
            problem, ipc_lost = self._terminal_problem()
        if problem is not None:
            self._poll_failed(symbol, problem, ipc_lost=ipc_lost)
            self._guard_why = ('terminal', problem)
            return False
        if not self._account_ok(symbol):
            self._guard_why = ('account', self._account_bad)
            return False
        return True

    def _terminal_problem(self):
        """Why the terminal cannot be used this poll: (problem, ipc_lost), (None, False) when it can. ipc_lost:
        terminal_info() answers None (or raises), the connection to the terminal is gone -- the terminal was
        restarted or closed -- and every call will answer None until the bot connects again. Not connected to the
        trade server: the terminal reconnects to it by itself, so the poll only waits (the bot's own reconnect is for
        a lost connection to the terminal, and it never logs in over another account, see initialize_mt5)."""
        try:
            info = mt5.terminal_info()
        except Exception as e:
            return f'terminal_info() raised {e!r}', True
        if info is None:
            return f'terminal_info() returned None (last_error {self._last_error()})', True
        if getattr(info, 'connected', True) is False:
            return f'the terminal is not connected to the trade server (last_error {self._last_error()})', False
        return None, False

    def _poll_failed(self, symbol, problem, ipc_lost=False):
        """A poll that could not read what it decides on: it syncs, books and decides nothing. A WARNING and an ERROR
        event TERMINAL_ERROR when such a streak starts or its problem changes (the terminal's last_error aside).
        After _RECONNECT_AFTER polls in a row without the terminal the bot connects again (_try_reconnect), and while
        that fails again after 5, 10, 30, then every 60 s."""
        self._failed_polls += 1
        if _why_key(problem) != _why_key(self._read_bad):
            print(f"[{symbol}] WARNING: poll skipped, nothing decided: {problem}")
            self._log_event(symbol, 'TERMINAL_ERROR', 'ERROR', {'problem': problem, 'failed_polls': self._failed_polls})
        self._read_bad = problem
        if not ipc_lost:
            return
        if self._ipc_failed == 0:
            self._ipc_lost_at = time.time()          # the outage starts (TERMINAL_RECONNECTED reports its length)
        self._ipc_failed += 1
        if self._ipc_failed >= _RECONNECT_AFTER and (self._reconnect_at is None or time.time() >= self._reconnect_at):
            self._try_reconnect(symbol)

    def _outage_s(self):
        return None if self._ipc_lost_at is None else round(time.time() - self._ipc_lost_at, 1)

    def _try_reconnect(self, symbol):
        """One reconnect attempt. Every failed one is printed; the ERROR event RECONNECT_FAILED for each reason (the
        terminal's last_error aside) the first time it is seen, then at most every _LOG_REPEAT_S for that reason
        (with the failures not logged since), so an outage of hours -- also one whose reasons alternate, a terminal
        that keeps restarting -- does not fill the 200-entry strategy log; TERMINAL_RECONNECTED reports the attempts
        and the outage's length."""
        attempt = self._reconnects_failed + 1
        if self._reconnect(symbol):
            print(f"[{symbol}] note: connected to the terminal again (attempt {attempt}, after {self._outage_s()} s)")
            self._reconnects_done += 1
            self._log_event(symbol, 'TERMINAL_RECONNECTED', 'SIGNAL', {
                'attempt': attempt, 'failed_attempts': attempt - 1, 'outage_s': self._outage_s(),
                'failed_polls': self._failed_polls, 'login': self._account_login})
            self._ipc_failed = 0
            self._reconnects_failed = 0
            self._reconnect_at = None
            self._ipc_lost_at = None
            self._reconnect_logged = {}
            return
        wait = _RECONNECT_BACKOFF_S[min(self._reconnects_failed, len(_RECONNECT_BACKOFF_S) - 1)]
        self._reconnects_failed += 1
        now = time.time()
        self._reconnect_at = now + wait
        print(f"[{symbol}] WARNING: reconnect attempt {attempt} failed ({self._init_problem}); next one in {wait:g} s")
        why = _why_key(self._init_problem)
        logged_at, unlogged = self._reconnect_logged.get(why, (None, 0))
        if logged_at is None or now - logged_at >= _LOG_REPEAT_S:
            if len(self._reconnect_logged) >= 32:      # (keep it small: a reason logged long ago is logged again anyway)
                self._reconnect_logged = {k: v for k, v in self._reconnect_logged.items()
                                          if now - v[0] < _LOG_REPEAT_S}
            self._reconnect_logged[why] = (now, 0)
            self._log_event(symbol, 'RECONNECT_FAILED', 'ERROR', {
                'attempt': attempt, 'why': self._init_problem, 'next_in_s': wait, 'failed_polls': self._failed_polls,
                'outage_s': self._outage_s(), 'not_logged_since': unlogged})
        else:
            self._reconnect_logged[why] = (logged_at, unlogged + 1)
        # the trace: every failed attempt (a WARN line for those the throttle above leaves out of the strategy log;
        # logged = this attempt's RECONNECT_FAILED was written: its reason's entry was set to (now, 0) just above)
        self._trace(symbol, 'reconnect_failed', attempt, self._init_problem, wait, self._outage_s(),
                    self._reconnect_logged.get(why) == (now, 0))

    def _reconnect(self, symbol):
        """mt5.shutdown(), then initialize_mt5() again: the terminal, the login (only on a terminal that shows no
        account for _ACCOUNT_GRACE_S), the demo-account checks, the symbol map and a new helper behind the order guard.
        True when the bot is on its demo account again."""
        print(f"[{symbol}] reconnecting to the MT5 terminal ...")
        with self.mt5_lock:
            try:
                mt5.shutdown()
            except Exception:
                pass
            self.mt5_initialized = False
            try:
                return bool(self.initialize_mt5())
            except Exception as e:          # (no credentials, a terminal that raises ...)
                self._init_problem = f'initialize_mt5 raised {e!r}'
                return False

    def _poll_succeeded(self, symbol):
        """The poll has read the terminal: a streak of failed polls is over (an event TERMINAL_OK)."""
        if self._failed_polls:
            print(f"[{symbol}] note: the terminal answers again after {self._failed_polls} skipped poll(s)")
            self._log_event(symbol, 'TERMINAL_OK', 'SIGNAL', {'failed_polls': self._failed_polls, 'was': self._read_bad})
        self._failed_polls = 0
        self._read_bad = None
        self._ipc_failed = 0
        self._reconnects_failed = 0
        self._reconnect_at = None
        self._ipc_lost_at = None
        self._reconnect_logged = {}

    def process_symbol(self, symbol):
        """
        Process a single symbol (will be called in separate threads)
        Lightweight and optimized - runs in infinite loop

        One poll, in the backtester's order (kernels.py run_kernel; map: scratchpad map_levers.md §2):
          market data + this bot's positions (MAGIC) -> the basket's state matched with them ->
          unit (only while flat, from the virtual balance) -> brake -> liveness (a dead poll decides nothing)
          -> forming-bar votes, H1 trend (last closed bar), volatility unit (closed bars) -> pause
          (loss pause) -> strategy (stop, target, force-close, ladder) -> execution (entry gates after the
          brake: trend, volatility known) -> bookkeeping (distances fixed at a fill, arming, pause start).

        Args:
            symbol (str): Symbol to process (e.g., 'BTCUSD', 'XAUUSD')
        """
        from datetime import datetime

        _problems = design_problems()
        if _problems:
            raise ValueError(f"design {DESIGN_NAME!r} refused: " + '; '.join(_problems))
        if STRATEGY == 'turtle':
            return self._process_turtle(symbol)        # its own loop; everything below is the basket

        # Get configuration once before loop (per-symbol config from array)
        sym_cfg = self.symbol_configs.get(symbol, {})
        brake_manual = self.symbols_config.get('brake', 0)
        trading_window_cfg = self.symbols_config.get('trading_window', {})
        # ── Auto unit stepping by account balance ──
        # The running unit is no longer configured directly; it is derived from
        # the live account balance in `step_up_balance`-sized tiers:
        #   balance [0, step)         → unit 1
        #   balance [step, 2·step)    → unit 2
        #   balance [2·step, 3·step)  → unit 3   … and so on
        # i.e. unit = floor(balance / step_up_balance) + 1, then capped by
        # `unit_max_limit`. The effective unit (`units`) drives BOTH lot sizing
        # (entry + Fibo ladder) and the USD profit target, keeping them
        # synchronized (unit N → target $N). It is re-derived below, but ONLY
        # while the symbol is flat — an open Fibo basket keeps the unit it was
        # opened with (rescaling mid-basket would corrupt the ladder maths).
        # Demo: the balance is the virtual one (VIRTUAL_START_BALANCE + this bot's own
        # closed P/L) and an open basket keeps the unit recorded at its open (after a
        # restart: its oldest position's volume / mtqty).
        step_up_balance = sym_cfg.get('step_up_balance', 0)
        max_limit = sym_cfg.get('unit_max_limit', 1)
        units = 1
        mtqty = self.symbols_config.get('mtqty', 0.01)
        trade_symbol = self.symbol_map.get(symbol, symbol)

        # Throttle expensive saves so they don't block other threads
        _last_daily_save = 0.0
        _last_hist_save = 0.0
        _DAILY_SAVE_INTERVAL = 60       # seconds between daily-trade saves
        _HIST_SAVE_INTERVAL = 300       # seconds between historical-summary saves

        # The open basket's fixed distances and ladder arming, and the post-close pause
        # (time, and whether that basket lost), persisted so a restart keeps them.
        state = self._load_state(symbol)
        _rebuild_pause = state is None          # no file: the pause comes back from the deal history
        state = state or {}
        state.setdefault('basket', None)
        state.setdefault('last_close', None)
        _block_logged = None                    # last entry-gate block written to the log (logged on change)
        _virtual_balance = None
        # the trace: the start-up block of the text log (branch, design, every constant, the state found)
        self._trace(symbol, 'loop_start', locals())

        while True:
            try:
                # Start of one full iteration's work (excludes the end-of-cycle sleep)
                _iter_start = time.perf_counter()

                # ── The terminal must answer and hold this bot's demo account, else this poll decides nothing ──
                if not self._poll_guard(symbol):
                    self._trace(symbol, 'poll_skipped', 'guard')
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue

                # ── Gather MT5 data under lock (split into small windows for fairness) ──
                with self.mt5_lock:
                    # Ensure symbol stays subscribed in Market Watch
                    mt5.symbol_select(trade_symbol, True)
                    source_df = self.position_helper.get_rates(trade_symbol, getattr(mt5, CANDLE_TIMEFRAME), CANDLE_COUNT)
                    market_status = self.position_helper.get_market_status(
                        trade_symbol, getattr(mt5, MARKET_STATUS_TIMEFRAME), lookback_minutes=MARKET_LOOKBACK_MINUTES
                    )
                time.sleep(0)  # yield so other symbol-threads can acquire the lock
                try:
                    with self.mt5_lock:
                        buy_positions = self.position_helper.get_buy_positions(trade_symbol)
                        sell_positions = self.position_helper.get_sell_positions(trade_symbol)
                        # the account again, right after the positions: a switch since the poll's first check
                        # would hand this poll another account's positions (read as "this basket closed outside")
                        _account_bad = self._account_problem()
                        account_info = self.position_helper.get_account_info()
                        server_time = self.position_helper._get_server_time(trade_symbol)
                        _tick = mt5.symbol_info_tick(trade_symbol)     # the decision quote (add gap)
                except TerminalReadError as e:
                    # The positions are not known this poll (not "none"): no sync, no bookkeeping, no decision.
                    self._poll_failed(symbol, str(e))
                    self._trace(symbol, 'poll_skipped', 'positions', str(e))
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue
                if _account_bad is not None:
                    # Not this bot's account any more: the poll decides nothing, as _poll_guard refuses it.
                    self._account_refused(symbol, _account_bad)
                    self._trace(symbol, 'poll_skipped', 'account_recheck', _account_bad)
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue
                self._poll_succeeded(symbol)
                _now = time.time()
                _bid = float(_tick.bid) if _tick is not None else None
                _ask = float(_tick.ask) if _tick is not None else None

                _buy_ct = buy_positions['count'] if buy_positions else 0
                _sell_ct = sell_positions['count'] if sell_positions else 0

                # ── This bot's basket: match the persisted state with its open positions ──
                with self.mt5_lock:
                    _usd_per_price = self._usd_per_price_of(symbol, trade_symbol, mtqty)
                    _changed = self._sync_basket(symbol, trade_symbol, state, buy_positions, sell_positions,
                                                 mtqty, _usd_per_price, _now)
                    if _rebuild_pause:
                        _rebuild_pause = False
                        if state.get('last_close') is None:
                            _lc = self._last_close_from_history(_now)
                            if _lc is not None:
                                state['last_close'] = _lc
                                _changed = True
                    if self._resolve_last_close(state, _now):
                        _changed = True
                if _changed:
                    self._save_state(symbol, state)
                basket = state.get('basket')
                _in_basket = basket is not None and (
                    (basket.get('side') == 'BUY' and _buy_ct > 0 and _sell_ct == 0)
                    or (basket.get('side') == 'SELL' and _sell_ct > 0 and _buy_ct == 0))
                if _in_basket:
                    basket['last_profit'] = (buy_positions if _buy_ct else sell_positions)['total_profit']
                # A fill the terminal does not list yet: its side is in a basket (no entry), on the basket's unit.
                _fill_pending = _buy_ct == 0 and _sell_ct == 0 and fill_pending(basket, _now)

                # ── Auto-step the running unit from live balance (only when flat) ──
                # Re-derive only while no positions are open so an active basket
                # stays on the unit it was opened with; the new tier applies to
                # the next basket. Balance is unavailable → keep the current unit.
                if _fill_pending:
                    units = int(basket['units'])
                elif _buy_ct == 0 and _sell_ct == 0:
                    balance = None
                    if virtual_balance_enabled():
                        with self.mt5_lock:
                            _virtual_balance = self._virtual_balance(_now)
                        balance = _virtual_balance
                    elif account_info:
                        balance = account_info.get('balance', 0)
                    if balance is not None:
                        if step_up_balance and step_up_balance > 0:
                            units = int(balance // step_up_balance) + 1
                        else:
                            units = 1
                        units = max(1, min(units, max_limit))
                elif _in_basket:
                    units = int(basket['units'])

                # ── Effective brake: manual override OR outside trading window ──
                # brake_manual=1 → always braked; else brake when outside the
                # configured trading_window (server-time based).
                in_window = self._is_in_trading_window(server_time, trading_window_cfg)
                brake = 1 if brake_manual or not in_window else 0

                # Save account data regardless of candle availability
                if account_info:
                    self._save_account_data(account_info, symbol)

                # ── Indicators & signals (only when candle data is available) ──
                buy_signal = Signal.DO_NOTHING
                sell_signal = Signal.DO_NOTHING
                analysis_data = {}
                has_candle_data = source_df is not None and len(source_df) > 0
                candle_is_fresh = False
                candle_age_min = None
                trend_now = 0              # sign of the TREND_TF MACD signal line, last closed bar
                trend_signal = None
                vol_now = None             # VOL_TF volatility unit, last closed bar (price units)
                _no_data = []              # timeframes the terminal returned no bars for this poll (their votes unknown)
                _short = []                # TREND_TF / VOL_TF with fewer than _MIN_CLOSED_BARS closed bars this poll
                _frames = {}               # the trace: the bars this poll fetched per timeframe (read, never changed)
                _signals = {}              # the trace: the forming bar's MACD signal line per slope timeframe

                if not has_candle_data:
                    print(f"[{symbol}] WARNING: No candle data returned by MT5")
                elif market_status and not market_status.get('is_open'):
                    print(f"[{symbol}] Market {market_status.get('status')} — {market_status.get('minutes_since_last')}m since last candle")

                if has_candle_data:
                    # Market liveness is judged from the M1 market probe (latest M1
                    # bar + tick), NOT from the SHA source bar. The SHA source is now
                    # M15, whose forming bar is up to 15 minutes "old" by design, so its
                    # age must never gate trading. market_status is tick-aware and
                    # timeframe-agnostic, so it stays correct regardless of the SHA
                    # source timeframe.
                    candle_is_fresh = bool(market_status.get('is_open')) if market_status else False

                    # Age of the latest M15 SHA bar — kept for logging/analysis only.
                    try:
                        last_candle_time = source_df['time'].iloc[-1]
                        if getattr(last_candle_time, 'tzinfo', None) is None:
                            last_candle_time = last_candle_time.replace(tzinfo=timezone.utc)
                        candle_age_min = (server_time - last_candle_time).total_seconds() / 60.0
                    except Exception:
                        candle_age_min = None

                    if not candle_is_fresh:
                        _mins = market_status.get('minutes_since_last') if market_status else None
                        print(f"[{symbol}] Market not live ({_mins}m since last activity) — SHA/trading skipped this cycle")

                if has_candle_data and candle_is_fresh:
                    # Capitalize columns for indicator compatibility
                    source_df.rename(columns={
                        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'
                    }, inplace=True)
                    
                    # Calculate RSI for multiple timeframes (entry filter + DCA ladder + final close).
                    # Fetched INDEPENDENTLY of the SHA source (its own small count via a
                    # lightweight fetch), so the mean-reversion ladder is never impacted
                    # by the SHA timeframe/candle-count. Union of all needed timeframes,
                    # de-duplicated while preserving order.
                    rsi_mtf = {}
                    slopes = {}   # D1/H4/H1/15M latest-pivot slopes (RSI+MACD) -> the weighted score
                    rsi_graphs = {}  # per-TF RSI series + pivot for the dashboard mini-charts
                    macd_graphs = {}  # per-TF MACD-histogram series + pivot for the mini-charts
                    # Votes for SLOPE_TIMEFRAMES plus every timeframe the strategy reads votes from
                    # (the section weights as they finally are, and a 'macd_turn' ladder's tiers).
                    slope_tfs = list(dict.fromkeys(list(SLOPE_TIMEFRAMES) + self.strategy.slope_timeframes()))
                    _trend_name = _tf_name(TREND_TF)
                    _vol_name = _tf_name(VOL_TF)
                    rsi_tf_list = []
                    for tf_name in (list(RSI_MTF_TIMEFRAMES)
                                    + list(RSI_DCA_LADDER_TIMEFRAMES)
                                    + slope_tfs
                                    + [RSI_FINAL_CLOSE_TIMEFRAME]
                                    + self.strategy.rsi_timeframes()
                                    + [n for n in (_trend_name, _vol_name) if n]):
                        if tf_name not in rsi_tf_list:
                            rsi_tf_list.append(tf_name)
                    for tf_name in rsi_tf_list:
                        with self.mt5_lock:
                            tf_df = self.position_helper.get_rates(
                                trade_symbol, getattr(mt5, tf_name), RSI_CANDLE_COUNT, simple=True
                            )
                        if tf_df is not None and len(tf_df) > 0:
                            _frames[tf_name] = tf_df
                            rsi_s = self.indicator.calculate_rsi(
                                tf_df['close'], length=RSI_LENGTH, ma_type=RSI_MA_TYPE
                            )
                            rsi_mtf[tf_name] = float(rsi_s.iloc[-1]) if len(rsi_s) > 0 else 50.0
                            macd_df = None
                            # RSI + MACD-histogram latest-pivot slopes on the slope timeframes
                            # (D1/H4/H1/15M -> the weighted score). Reuses this TF's RSI fetch -
                            # no extra call beyond the per-TF rates already pulled.
                            if tf_name in slope_tfs:
                                macd_df = self.indicator.calculate_macd(
                                    tf_df['close'], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL
                                )
                                # 15M / 1H / 4H / D1 latest-pivot slopes - identical computation;
                                # all four feed the weighted score (no level-based regime).
                                rsi_slope = self.indicator.latest_pivot_slope(
                                    rsi_s, lookback=PEAK_LOOKBACK, width=PIVOT_WIDTH,
                                    ob_level=RSI_PEAK_OB, os_level=RSI_PEAK_OS
                                )
                                # MACD has no fixed OB/OS; the signal line's sign
                                # selects the pivot side -> high (OB) when signal > 0,
                                # low (OS) when signal < 0.
                                _sig = float(macd_df['signal'].iloc[-1]) if len(macd_df) > 0 else 0.0
                                _signals[tf_name] = _sig
                                _macd_side = 'high' if _sig > 0 else ('low' if _sig < 0 else None)
                                macd_slope = self.indicator.latest_pivot_slope(
                                    macd_df['hist'], lookback=PEAK_LOOKBACK, width=PIVOT_WIDTH,
                                    side=_macd_side
                                )
                                _tf_key_ = tf_name.replace('TIMEFRAME_', '')
                                slopes[_tf_key_] = {
                                    'rsi': rsi_slope, 'macd': macd_slope,
                                }
                                # RSI mini-chart: RSI line + latest (OB/OS-band) pivot +
                                # peak->current line coloured by the RSI slope sign.
                                rsi_graphs[_tf_key_] = {
                                    'series': [round(float(v), 2) for v in rsi_s.tail(RSI_GRAPH_BARS).tolist()],
                                    'current': round(float(rsi_s.iloc[-1]), 2),
                                    'pivot_bars_ago': rsi_slope.get('bars_ago'),
                                    'pivot_value': (round(rsi_slope['value'], 2)
                                                    if rsi_slope.get('value') is not None else None),
                                    'sign': rsi_slope.get('sign', 0),
                                    'bands': [RSI_PEAK_OS, RSI_PEAK_OB],
                                    'clamp': [0, 100], 'name': 'RSI',
                                }
                                # MACD-histogram mini-chart: hist line + latest (signal-
                                # side) pivot + peak->current line coloured by its slope.
                                macd_graphs[_tf_key_] = {
                                    'series': [round(float(v), 5) for v in macd_df['hist'].tail(RSI_GRAPH_BARS).tolist()],
                                    'current': round(float(macd_df['hist'].iloc[-1]), 5),
                                    'pivot_bars_ago': macd_slope.get('bars_ago'),
                                    'pivot_value': (round(macd_slope['value'], 5)
                                                    if macd_slope.get('value') is not None else None),
                                    'sign': macd_slope.get('sign', 0),
                                    'bands': [0], 'clamp': None, 'name': 'MACD',
                                }
                            # H1 trend: the MACD SIGNAL line of the last CLOSED bar (row -2; row -1 is
                            # the forming bar, whose signal line only picks the MACD vote's pivot side).
                            # 0 or NaN -> no trend -> no entry on either side.
                            if tf_name == _trend_name:
                                if macd_df is None:
                                    macd_df = self.indicator.calculate_macd(
                                        tf_df['close'], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL
                                    )
                                trend_signal = float(macd_df['signal'].iloc[-2]) if len(macd_df) >= 2 else float('nan')
                                trend_now = 1 if trend_signal > 0 else (-1 if trend_signal < 0 else 0)
                            # Both need a full history: fewer than _MIN_CLOSED_BARS closed bars send no entry.
                            if tf_name in (_trend_name, _vol_name) and len(tf_df) - 1 < _MIN_CLOSED_BARS:
                                _short.append(_tf_key(tf_name))
                            # Volatility unit on the CLOSED bars (the forming row -1 excluded).
                            if tf_name == _vol_name and len(tf_df) - 1 >= _MIN_CLOSED_BARS:
                                vol_now = Indicator.vol_unit(tf_df['close'].to_numpy()[:-1], VOL_LEN)
                        else:
                            rsi_mtf[tf_name] = 50.0
                            _no_data.append(_tf_key(tf_name))
                    current_rsi = rsi_mtf.get('TIMEFRAME_M1', 50.0)

                    # A basket taken over without the bars of its open (levels pending) takes the
                    # volatility unit measured now.
                    if _in_basket and basket.get('levels_pending') and levels_complete(vol_now, _usd_per_price):
                        basket.update(basket_levels(vol_now, _usd_per_price))
                        basket['levels_pending'] = False
                        basket['vol_source'] = 'current'
                        self._save_state(symbol, state)
                    
                    # Calculate signal. `units` (effective, capped by max_limit) drives
                    # the lot size and the USD close target. `entry_allowed` is False
                    # while the post-close re-entry cooldown is still active: after a basket
                    # that lost, LOSS_COOLDOWN_S (if set) instead of REENTRY_COOLDOWN_SECONDS.
                    _lc = state.get('last_close') or {}
                    _last_close_time = float(_lc.get('time') or 0.0)
                    _pause = LOSS_COOLDOWN_S if (_lc.get('lost') and LOSS_COOLDOWN_S > 0) else REENTRY_COOLDOWN_SECONDS
                    entry_allowed = (time.time() - _last_close_time) >= _pause and not _fill_pending
                    # The basket's distances, fixed at its open; flat: the configured ones (unused).
                    if _in_basket:
                        _tgt_u = basket.get('target_usd_per_unit')
                        _sl_u = basket.get('stop_usd_per_unit')
                        _gap = float(basket.get('gap_px') or 0.0)
                        _armed = bool(basket.get('ladder_armed'))
                        _plist = _sorted_positions((buy_positions if _buy_ct else sell_positions).get('positions'))
                        _last_fill = float(_plist[-1].price_open) if _plist else None
                    else:
                        _flat_levels = basket_levels(None, _usd_per_price)
                        _tgt_u = _flat_levels['target_usd_per_unit']
                        _sl_u = _flat_levels['stop_usd_per_unit']
                        _gap, _armed, _last_fill = 0.0, False, None
                    close_threshold = None if _tgt_u is None else _tgt_u * units
                    stop_threshold = None if _sl_u is None else _sl_u * units
                    buy_signal, sell_signal, analysis_data = self.strategy.calculate_signal(
                        source_df,
                        buy_positions, sell_positions, units,
                        close_threshold=close_threshold,
                        rsi_value=current_rsi,
                        rsi_mtf=rsi_mtf,
                        slopes=slopes,
                        entry_allowed=entry_allowed,
                        stop_threshold=stop_threshold,
                        ladder_armed=_armed,
                        ladder_gap=_gap,
                        last_fill_price=_last_fill,
                        bid=_bid, ask=_ask,
                    )
                    # A ladder tier whose timeframe returned no bars: its vote is not known this poll (not a vote
                    # against the basket) -- no add, and the arming stays as it was.
                    _tier = analysis_data.get('ladder_tier')
                    if _in_basket and _tier and _tf_key(_tier) in _no_data:
                        analysis_data['ladder_armed'] = _armed
                        if buy_signal == Signal.BUY_MORE:
                            buy_signal = Signal.DO_NOTHING
                        if sell_signal == Signal.SELL_MORE:
                            sell_signal = Signal.DO_NOTHING
                    # The macd_turn ladder's arming is a fact of this poll's votes: keep it.
                    if _in_basket and bool(analysis_data.get('ladder_armed')) != _armed:
                        basket['ladder_armed'] = bool(analysis_data.get('ladder_armed'))
                        self._save_state(symbol, state)
                    # A close that left positions behind is finished first; so is a basket some of whose legs were
                    # closed outside the bot (the rest is closed at once).
                    if _in_basket and basket.get('close_pending'):
                        if basket['side'] == 'BUY':
                            buy_signal = Signal.CLOSE_BUY
                        else:
                            sell_signal = Signal.CLOSE_SELL
                        analysis_data['exit_reason'] = 'leg_closed_outside' if basket.get('outside_ids') else 'close_retry'
                    analysis_data['rsi_graphs'] = rsi_graphs
                    analysis_data['macd_graphs'] = macd_graphs
                    analysis_data['candle_fresh'] = True
                    analysis_data['trend'] = trend_now if TREND_TF is not None else None
                    analysis_data['trend_signal'] = trend_signal if trend_signal == trend_signal else None
                    analysis_data['vol_unit_now'] = vol_now
                    analysis_data['no_data'] = list(_no_data)
                    analysis_data['short_history'] = list(_short)
                    analysis_data['loss_pause_s'] = _pause
                    analysis_data['pause_left_s'] = max(0.0, round(_pause - (time.time() - _last_close_time), 1))
                    analysis_data['last_close_lost'] = _lc.get('lost')
                else:
                    analysis_data['candle_fresh'] = False

                # Always populate source metadata (regardless of fresh/stale)
                if has_candle_data:
                    analysis_data['source_candle_count'] = int(len(source_df))
                    analysis_data['rates_source'] = source_df.attrs.get('rates_source', 'unknown')
                    analysis_data['synthetic_bar'] = bool(source_df.attrs.get('synthetic_appended', False))
                    analysis_data['tick_rebuilt'] = bool(source_df.attrs.get('tick_rebuilt', False))
                    try:
                        analysis_data['last_source_candle_time'] = source_df['time'].iloc[-1].isoformat()
                    except Exception:
                        analysis_data['last_source_candle_time'] = None
                else:
                    analysis_data['source_candle_count'] = 0
                    analysis_data['rates_source'] = 'none'
                    analysis_data['synthetic_bar'] = False
                    analysis_data['tick_rebuilt'] = False
                    analysis_data['last_source_candle_time'] = None
                analysis_data['candle_age_min'] = round(float(candle_age_min), 2) if candle_age_min is not None else None

                # Running unit (auto-derived from balance) so the dashboard/logs
                # show the current tier and its inputs.
                analysis_data['unit_times'] = units
                analysis_data['step_up_balance'] = step_up_balance
                analysis_data['unit_max_limit'] = max_limit
                analysis_data['design'] = DESIGN_NAME
                analysis_data['fill_pending'] = bool(_fill_pending)
                analysis_data['virtual_balance'] = _virtual_balance if virtual_balance_enabled() else None
                analysis_data['basket_levels'] = ({
                    'units': basket.get('units'),
                    'target_usd': (None if basket.get('target_usd_per_unit') is None
                                   else round(basket['target_usd_per_unit'] * basket['units'], 2)),
                    'stop_usd': (None if basket.get('stop_usd_per_unit') is None
                                 else round(basket['stop_usd_per_unit'] * basket['units'], 2)),
                    'gap_px': basket.get('gap_px'),
                    'vol_unit': basket.get('vol_unit'),
                    'ladder_armed': basket.get('ladder_armed'),
                } if _in_basket else None)

                # ── Build JSON data (always saved so dashboard stays current) ──
                symbol_data = {
                    'symbol': symbol,
                    'mt5_symbol': trade_symbol,
                    'last_updated': datetime.now(tz=timezone.utc).isoformat(),
                    'server_time': server_time.isoformat(),
                    'market_status': market_status,
                    'account': account_info if account_info else {},
                    'positions': {
                        'buy': {
                            'count': buy_positions['count'] if buy_positions else 0,
                            'total_profit': buy_positions['total_profit'] if buy_positions else 0,
                            'total_volume': buy_positions['total_volume'] if buy_positions else 0,
                            'first_profit': buy_positions['first_profit'] if buy_positions else 0,
                            'first_volume': buy_positions['first_volume'] if buy_positions else 0,
                            'last_profit': buy_positions['last_profit'] if buy_positions else 0,
                            'last_volume': buy_positions['last_volume'] if buy_positions else 0,
                        },
                        'sell': {
                            'count': sell_positions['count'] if sell_positions else 0,
                            'total_profit': sell_positions['total_profit'] if sell_positions else 0,
                            'total_volume': sell_positions['total_volume'] if sell_positions else 0,
                            'first_profit': sell_positions['first_profit'] if sell_positions else 0,
                            'first_volume': sell_positions['first_volume'] if sell_positions else 0,
                            'last_profit': sell_positions['last_profit'] if sell_positions else 0,
                            'last_volume': sell_positions['last_volume'] if sell_positions else 0,
                        },
                    },
                    'signal': {
                        'buy_status': buy_signal.name,
                        'sell_status': sell_signal.name,
                    },
                    'analysis': analysis_data,
                    'order_response': None,
                    'demo': {
                        'branch': DEMO_BRANCH, 'magic': MAGIC, 'design': DESIGN_NAME,
                        'virtual_balance': analysis_data.get('virtual_balance'),
                        'basket': state.get('basket'), 'last_close': state.get('last_close'),
                    },
                }
                
                # Execute buy signal
                order_response = None
                close_response = None
                if has_candle_data and candle_is_fresh and buy_signal == Signal.BUY:
                    if not brake:
                        _why = entry_block_reason(1, trend_now, vol_now, _usd_per_price, no_data=_no_data,
                                                  short_history=_short)
                        if _why is None:
                            _levels = basket_levels(vol_now, _usd_per_price)   # fixed for this basket's life
                            order_response, _backstop = self._open_leg(1, trade_symbol, units * mtqty,
                                                                       _levels['stop_usd_per_unit'], _usd_per_price,
                                                                       _ask)
                            if self._order_done(order_response):
                                _t_fill = time.time()
                                state['basket'] = self._new_basket('BUY', units, _levels, _t_fill)
                                self._record_fill(state['basket'], order_response, _t_fill)   # a leg now, listed or not
                                self._save_state(symbol, state)
                            _block_logged = None
                            self._log_event(symbol, 'BUY_EXECUTED', 'ENTRY', {
                                'mt5_symbol': trade_symbol,
                                'qty': units * mtqty,
                                'target_usd': None if _levels['target_usd_per_unit'] is None else round(_levels['target_usd_per_unit'] * units, 2),
                                'stop_usd': None if _levels['stop_usd_per_unit'] is None else round(_levels['stop_usd_per_unit'] * units, 2),
                                'vol_unit': _levels['vol_unit'],
                                'backstop_sl': _backstop,
                                'response': str(order_response),
                            }, server_time=server_time)
                        elif _block_logged != ('BUY', _why):
                            _block_logged = ('BUY', _why)
                            self._log_event(symbol, 'BUY_SIGNAL', 'SIGNAL', {
                                'note': f'Entry blocked: {_why} — order skipped',
                                'trend_signal': analysis_data.get('trend_signal'), 'vol_unit': vol_now,
                                'no_data': list(_no_data), 'short_history': list(_short),
                            }, server_time=server_time)
                    else:
                        self._log_event(symbol, 'BUY_SIGNAL', 'SIGNAL', {
                            'note': 'Brake active — order skipped',
                        }, server_time=server_time)
                elif buy_signal == Signal.BUY_MORE:
                    vol = self.strategy.next_add_volume(buy_positions['total_volume'], buy_positions['count'], units, mtqty)
                    order_response, _backstop = self._open_leg(1, trade_symbol, vol,
                                                               basket.get('stop_usd_per_unit') if _in_basket else None,
                                                               _usd_per_price, _ask)
                    if _in_basket and self._order_done(order_response):
                        basket['ladder_armed'] = False      # the next add needs a new turn
                        self._record_fill(basket, order_response, time.time())   # a leg now, listed or not
                        self._save_state(symbol, state)
                    self._log_event(symbol, 'BUY_MORE_EXECUTED', 'ENTRY', {
                        'mt5_symbol': trade_symbol,
                        'qty': vol,
                        'fibo_level': buy_positions['count'] + 1,
                        'total_volume': buy_positions['total_volume'],
                        'total_profit': buy_positions['total_profit'],
                        'first_profit': buy_positions['first_profit'],
                        'backstop_sl': _backstop,
                        'response': str(order_response),
                    }, server_time=server_time)
                    time.sleep(ORDER_COOLDOWN_SECONDS)  # Wait for MT5 to register position
                elif buy_signal == Signal.CLOSE_BUY:
                    with self.mt5_lock:
                        close_response = self.position_helper.close_by_type(trade_symbol, 0)
                    # start the re-entry cooldown (only once the basket is really closed)
                    _closed = self._after_close(symbol, state, 'BUY', close_response, buy_positions,
                                                analysis_data.get('exit_reason'), time.time())
                    self._log_event(symbol, 'CLOSE_BUY', 'EXIT', {
                        'mt5_symbol': trade_symbol,
                        'positions_closed': close_response.get('closed_count', 0),
                        'total_profit': buy_positions['total_profit'] if buy_positions else 0,
                        'reason': analysis_data.get('exit_reason'),
                        'realised_pnl': _closed.get('pnl') if _closed else None,
                        'lost': _closed.get('lost') if _closed else None,
                        'response': close_response,
                    }, server_time=server_time)
                
                # Execute sell signal
                if has_candle_data and candle_is_fresh and sell_signal == Signal.SELL:
                    if not brake:
                        _why = entry_block_reason(-1, trend_now, vol_now, _usd_per_price, no_data=_no_data,
                                                  short_history=_short)
                        if _why is None:
                            _levels = basket_levels(vol_now, _usd_per_price)   # fixed for this basket's life
                            order_response, _backstop = self._open_leg(-1, trade_symbol, units * mtqty,
                                                                       _levels['stop_usd_per_unit'], _usd_per_price,
                                                                       _bid)
                            if self._order_done(order_response):
                                _t_fill = time.time()
                                state['basket'] = self._new_basket('SELL', units, _levels, _t_fill)
                                self._record_fill(state['basket'], order_response, _t_fill)   # a leg now, listed or not
                                self._save_state(symbol, state)
                            _block_logged = None
                            self._log_event(symbol, 'SELL_EXECUTED', 'ENTRY', {
                                'mt5_symbol': trade_symbol,
                                'qty': units * mtqty,
                                'target_usd': None if _levels['target_usd_per_unit'] is None else round(_levels['target_usd_per_unit'] * units, 2),
                                'stop_usd': None if _levels['stop_usd_per_unit'] is None else round(_levels['stop_usd_per_unit'] * units, 2),
                                'vol_unit': _levels['vol_unit'],
                                'backstop_sl': _backstop,
                                'response': str(order_response),
                            }, server_time=server_time)
                        elif _block_logged != ('SELL', _why):
                            _block_logged = ('SELL', _why)
                            self._log_event(symbol, 'SELL_SIGNAL', 'SIGNAL', {
                                'note': f'Entry blocked: {_why} — order skipped',
                                'trend_signal': analysis_data.get('trend_signal'), 'vol_unit': vol_now,
                                'no_data': list(_no_data), 'short_history': list(_short),
                            }, server_time=server_time)
                    else:
                        self._log_event(symbol, 'SELL_SIGNAL', 'SIGNAL', {
                            'note': 'Brake active — order skipped',
                        }, server_time=server_time)
                elif sell_signal == Signal.SELL_MORE:
                    vol = self.strategy.next_add_volume(sell_positions['total_volume'], sell_positions['count'], units, mtqty)
                    order_response, _backstop = self._open_leg(-1, trade_symbol, vol,
                                                               basket.get('stop_usd_per_unit') if _in_basket else None,
                                                               _usd_per_price, _bid)
                    if _in_basket and self._order_done(order_response):
                        basket['ladder_armed'] = False      # the next add needs a new turn
                        self._record_fill(basket, order_response, time.time())   # a leg now, listed or not
                        self._save_state(symbol, state)
                    self._log_event(symbol, 'SELL_MORE_EXECUTED', 'ENTRY', {
                        'mt5_symbol': trade_symbol,
                        'qty': vol,
                        'fibo_level': sell_positions['count'] + 1,
                        'total_volume': sell_positions['total_volume'],
                        'total_profit': sell_positions['total_profit'],
                        'first_profit': sell_positions['first_profit'],
                        'backstop_sl': _backstop,
                        'response': str(order_response),
                    }, server_time=server_time)
                    time.sleep(ORDER_COOLDOWN_SECONDS)  # Wait for MT5 to register position
                elif sell_signal == Signal.CLOSE_SELL:
                    with self.mt5_lock:
                        close_response = self.position_helper.close_by_type(trade_symbol, 1)
                    # start the re-entry cooldown (only once the basket is really closed)
                    _closed = self._after_close(symbol, state, 'SELL', close_response, sell_positions,
                                                analysis_data.get('exit_reason'), time.time())
                    self._log_event(symbol, 'CLOSE_SELL', 'EXIT', {
                        'mt5_symbol': trade_symbol,
                        'positions_closed': close_response.get('closed_count', 0),
                        'total_profit': sell_positions['total_profit'] if sell_positions else 0,
                        'reason': analysis_data.get('exit_reason'),
                        'realised_pnl': _closed.get('pnl') if _closed else None,
                        'lost': _closed.get('lost') if _closed else None,
                        'response': close_response,
                    }, server_time=server_time)
                
                # Attach order response if any
                if order_response is not None:
                    symbol_data['order_response'] = str(order_response)
                
                # Attach close response if any
                if close_response is not None:
                    symbol_data['close_response'] = close_response
                
                # ── Full-iteration timing (work only, excludes the trailing sleep) ──
                iteration_ms = round((time.perf_counter() - _iter_start) * 1000, 1)
                symbol_data['iteration_ms'] = iteration_ms
                symbol_data['analysis']['iteration_ms'] = iteration_ms
                print(f"[{symbol}] iteration {iteration_ms} ms")

                # Save to JSON
                self._save_symbol_data(symbol, symbol_data)
                
                # Save daily trade logs (throttled to reduce MT5 lock contention)
                _now_ts = time.time()
                if has_candle_data and candle_is_fresh:
                    try:
                        if _now_ts - _last_daily_save >= _DAILY_SAVE_INTERVAL:
                            self._save_daily_trades(symbol, mt5_symbol=trade_symbol)
                            _last_daily_save = _now_ts
                        if _now_ts - _last_hist_save >= _HIST_SAVE_INTERVAL:
                            self._save_historical_summary(symbol, mt5_symbol=trade_symbol)
                            _last_hist_save = _now_ts
                    except Exception:
                        # Non-critical, don't break the main loop (a WARN with the traceback in the text log)
                        self._trace(symbol, 'exception', 'SAVE', 'the daily-trade / history-summary files could not be '
                                    'saved (tried again next poll)', level='WARN')

                # ── The trace (tracelog.py): reads this poll's locals, writes the dashboard's files and the text log ──
                self._trace(symbol, 'poll', locals())

                time.sleep(max(brake, 1))  # At least 1s between cycles

                # Check if supervisor requested shutdown (mode change)
                if self._stop_event.is_set():
                    return

            except Exception as e:
                print(f"[{symbol}] Error: {e}")
                self._trace(symbol, 'exception', 'LOOP', f'the poll failed: {e!r}; the loop goes on in 1 s')
                time.sleep(1)
                if self._stop_event.is_set():
                    return
    
    # ───────────────────── the Turtle (STRATEGY = 'turtle'; its rules are in turtle.py) ─────────────────────
    def _turtle_state_path(self, symbol):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, f'{symbol}_turtle.json')

    def _load_turtle_state(self, symbol):
        """The persisted Turtle book or None: no file, unreadable, or written for another symbol / magic number /
        system (then it is rebuilt from the terminal)."""
        path = self._turtle_state_path(symbol)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            print(f"[{symbol}] note: Turtle state file {path} unreadable ({e}); rebuilding it from the terminal")
            self._trace(symbol, 'state_note', 'WARN', f'the Turtle state file {path} is unreadable ({e!r}): the book is '
                        'rebuilt from the terminal')
            return None
        if (not isinstance(data, dict) or data.get('symbol') != symbol or data.get('magic') != MAGIC
                or data.get('system') != TURTLE_SYSTEM or not isinstance(data.get('book'), dict)):
            print(f"[{symbol}] note: Turtle state file {path} is not this bot's (symbol/magic/system); rebuilding it")
            self._trace(symbol, 'state_note', 'WARN', f"the Turtle state file {path} is not this bot's (symbol / magic / "
                        'system): the book is rebuilt from the terminal')
            return None
        st = T.new_state()
        st.update({k: v for k, v in data['book'].items() if k in st})
        return st

    def _save_turtle_state(self, symbol, st):
        """Write the book atomically (a crash mid-write leaves the previous file)."""
        path = self._turtle_state_path(symbol)
        data = {'version': _STATE_VERSION, 'symbol': symbol, 'magic': MAGIC, 'design': DESIGN_NAME,
                'system': TURTLE_SYSTEM, 'saved_at': time.time(), 'book': st}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with self.thread_lock:
                with open(tmp, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp, path)
        except OSError as e:
            print(f"[{symbol}] Error: could not write the Turtle state file {path}: {e}")
            self._trace(symbol, 'state_note', 'ERROR', f'could not write the Turtle state file {path}: {e!r} (a restart '
                        'now would rebuild the trade from the terminal)')
            return
        self._trace(symbol, 'turtle_state_saved', st)

    def _turtle_closed_bars(self, trade_symbol, tf_name, count, tf_s, now):
        """The CLOSED bars of a timeframe at the terminal's time `now`: the last `count` bars of
        copy_rates_from_pos(..., 0, count + 1) whose open time + tf_s <= now (the bar still forming is dropped).
        A dict of arrays t (open time, s) / o / h / l / c, or None."""
        tf = getattr(mt5, tf_name, None)
        if tf is None:
            return None
        with self.mt5_lock:
            rates = mt5.copy_rates_from_pos(trade_symbol, tf, 0, int(count) + 1)
        if rates is None or len(rates) == 0:
            return None
        t = np.asarray(rates['time'], np.int64)
        keep = np.flatnonzero(t + int(tf_s) <= now)[-int(count):]
        return {'t': t[keep], 'o': np.asarray(rates['open'], np.float64)[keep],
                'h': np.asarray(rates['high'], np.float64)[keep], 'l': np.asarray(rates['low'], np.float64)[keep],
                'c': np.asarray(rates['close'], np.float64)[keep]}

    def _turtle_history(self, trade_symbol, now):
        """From this bot's deal history: the time of its last entry (the first leg of a trade: a position opened
        while none of its positions was open) and of its last closing deal; (None, None) when unknown."""
        with self.mt5_lock:
            deals = self.position_helper.get_bot_deals(_utc(now - _TURTLE_HISTORY_S), _utc(now + 86400))
        if not deals:
            return None, None
        deals = [d for d in deals if getattr(d, 'symbol', trade_symbol) == trade_symbol]
        open_ids, last_entry, last_out = set(), None, None
        for d in sorted(deals, key=lambda d: (_deal_time(d), int(getattr(d, 'ticket', 0) or 0))):
            pid = getattr(d, 'position_id', None)
            if getattr(d, 'entry', None) == 0:
                if not open_ids:
                    last_entry = _deal_time(d)
                open_ids.add(pid)
            elif _is_out_deal(d):
                open_ids.discard(pid)
                last_out = _deal_time(d)
        return last_entry, last_out

    def _turtle_rows(self, symbol, st, rows, rows_t, server_time):
        """Every D1 bar closed since the book's last one, oldest first: each raises an open trade's stop to its exit
        channel and arms its entry orders (a fresh book takes the last bar only). True when the book changed."""
        n = len(rows_t)
        if st['row'] is not None and int(st['row']) >= int(rows_t[-1]):
            return False
        if st['row'] is None:
            todo = [n - 1]
        else:
            todo = [b for b in range(n) if int(rows_t[b]) > int(st['row'])]
        if not todo:
            return False
        for b in todo:
            T.on_new_row(st, T.row_levels(rows, rows_t, b))
        lv = st['levels']
        self._log_event(symbol, 'TURTLE_LEVELS', 'SIGNAL', {
            'd1_bar': _iso(lv['bar_time']), 'bars_processed': len(todo), 'system': lv['system'],
            'buy_level': lv['buy'], 'sell_level': lv['sell'], 'n': lv['n'], 'use20': lv['use20'],
            'trade': {1: 'BUY', -1: 'SELL'}.get(st['side']), 'stop': st['stop'], 'stop_origin': T.stop_origin(st),
        }, server_time=server_time)
        return True

    def _turtle_sync(self, symbol, st, buy_positions, sell_positions, rows, rows_t, mtqty, now, server_time):
        """
        Match the book with this bot's open positions. The positions are the truth for the legs (fill price, open
        time, ticket); a leg the bot has just filled is kept _TURTLE_PENDING_S seconds until the terminal lists it.
        Positions the book does not hold (a start without the state file): the trade is rebuilt from them (turtle.py
        rebuild). A book whose positions are all gone: closed (the bot's exit finished, or closed outside it). Some
        legs gone outside the bot: closed at or beyond the trade's stop (their backstop, as the deal history shows)
        -> the other legs are closed at once (closing); closed by hand inside the stop -> the trade goes on, its stop
        kept. Returns (changed, hold, pending): hold = make no decision this poll, pending = a fill not listed yet.
        """
        nb = buy_positions['count'] if buy_positions else 0
        ns = sell_positions['count'] if sell_positions else 0
        if nb and ns:
            return False, True, False          # both sides open (not the Turtle's doing): hold still
        side = 1 if nb else (-1 if ns else 0)
        plist = _sorted_positions((buy_positions if nb else sell_positions).get('positions')) if side else []
        legs = [{'price': float(p.price_open), 'time': _pos_time(p), 'ticket': _pos_id(p)} for p in plist]
        if st['side'] != 0 and side in (0, st['side']):
            seen = {leg['ticket'] for leg in legs}
            young = [dict(leg) for leg in st['legs']
                     if leg.get('ticket') not in seen and now - float(leg['time']) < _TURTLE_PENDING_S]
            merged = sorted(legs + young, key=lambda x: (x['time'], x['ticket'] or 0))
            if not merged:
                outside = not st['closing']
                was = 'BUY' if st['side'] == 1 else 'SELL'
                T.on_exit(st, now)
                self._turtle_stop_passed = False
                if outside:
                    print(f"[{symbol}] note: the Turtle's {was} trade was closed outside the bot")
                    self._log_event(symbol, 'TURTLE_CLOSED_OUTSIDE', 'EXIT', {'side': was}, server_time=server_time)
                return True, False, False
            changed = [(round(a['price'], 8), a['ticket']) for a in merged] != \
                      [(round(a['price'], 8), a.get('ticket')) for a in st['legs']]
            if changed:
                gone = sorted({a.get('ticket') for a in st['legs']} - {a['ticket'] for a in merged} - {None})
                stop_was = st['stop']
                T.set_legs(st, merged)
                if gone and not st['closing']:          # (while the bot closes them itself, they go one by one)
                    beyond = self._turtle_closed_beyond_stop(gone, st['side'], stop_was, st['entry_time'], now)
                    if beyond is not False:
                        # Closed at or beyond the trade's stop (a leg's backstop always lies beyond it), or the history
                        # cannot say: the stop was passed while the bot did not look -- the other legs go at once,
                        # whatever the price does now. A leg closed by hand inside the stop leaves the trade on.
                        st['closing'] = True
                        self._turtle_stop_passed = True
                    print(f"[{symbol}] note: Turtle leg(s) {gone} closed outside the bot"
                          + ("; beyond the trade's stop: closing the others" if beyond is not False
                             else f"; the stop stays at {st['stop']}"))
                    self._log_event(symbol, 'TURTLE_LEG_CLOSED_OUTSIDE', 'EXIT', {
                        'tickets': gone, 'legs': len(st['legs']), 'stop': st['stop'],
                        'stop_origin': T.stop_origin(st), 'beyond_stop': beyond}, server_time=server_time)
            return changed, False, bool(young)
        if side == 0:
            return False, False, False
        # positions the book does not hold
        if st['side'] != 0:
            print(f"[{symbol}] note: the Turtle's open trade was replaced outside the bot; taking the positions over")
            T.on_exit(st, now)
            self._turtle_stop_passed = False
        units = max(1, int(round(float(plist[0].volume) / float(mtqty)))) if mtqty else 1
        new = T.rebuild(side, legs, units, rows, rows_t)
        if new is None:
            self._turtle_note(symbol, 'rebuild', "the open positions predate the D1 history: they are left alone",
                              server_time)
            return False, True, False
        new['last_exit_time'] = st.get('last_exit_time')
        st.clear()
        st.update(new)
        print(f"[{symbol}] note: Turtle {'BUY' if side == 1 else 'SELL'} trade of {len(legs)} leg(s) taken over from "
              f"the terminal: unit {units}, N at entry {st['n_entry']}, stop {st['stop']} ({T.stop_origin(st)})")
        self._log_event(symbol, 'TURTLE_REBUILT', 'SIGNAL', {
            'side': 'BUY' if side == 1 else 'SELL', 'legs': len(legs), 'units': units, 'n_entry': st['n_entry'],
            'stop': st['stop'], 'entry_d1_bar': _iso(st['entry_row'])}, server_time=server_time)
        return True, False, False

    def _turtle_closed_beyond_stop(self, gone, side, stop, since, now):
        """Legs closed outside the bot (`gone`, position ids): True when the deal history shows one of them closed at
        or beyond the trade's stop `stop` (a long's at or below it, a short's at or above), False when every one of
        them closed inside it (by hand), None when the history does not show them all (yet)."""
        if not _is_number(stop):
            return None
        frm = (float(since) if since else now) - 86400.0
        with self.mt5_lock:
            deals = self.position_helper.get_bot_deals(_utc(frm), _utc(now + 86400.0))
        if deals is None:
            return None
        outs = [d for d in deals if getattr(d, 'position_id', None) in set(gone) and _is_out_deal(d)]
        for d in outs:
            px = float(getattr(d, 'price', 0.0) or 0.0)
            if px > 0 and (px <= stop if side == 1 else px >= stop):
                return True
        return False if set(gone) <= {getattr(d, 'position_id', None) for d in outs} else None

    def _turtle_note(self, symbol, key, text, server_time, details=None):
        """Print and log a repeated note at most every _TURTLE_NOTE_S seconds (per key)."""
        notes = self.__dict__.setdefault('_turtle_notes', {})
        now = time.time()
        if now - notes.get(key, -1e18) < _TURTLE_NOTE_S:
            return
        notes[key] = now
        print(f"[{symbol}] WARNING: {text}" if key in ('rebuild', 'd1', 'order') else f"[{symbol}] note: {text}")
        self._log_event(symbol, 'TURTLE_NOTE', 'SIGNAL', dict(details or {}, note=text), server_time=server_time)

    def _turtle_units(self, account_info, step_up_balance, max_limit):
        """The unit for a new trade: the bot's rule on the virtual balance (or the account balance). (units, balance)"""
        balance = None
        if virtual_balance_enabled():
            with self.mt5_lock:
                balance = self._virtual_balance(time.time())
        elif account_info:
            balance = account_info.get('balance', 0)
        if balance is None:
            return 1, None
        return T.unit_rule(balance, step_up_balance, max_limit), balance

    def _turtle_backstop(self, trade_symbol, st, side, price, now, units=None):
        """
        The broker-side backstop (request sl) of a new Turtle leg filled at `price` (the decision quote: the ask of a
        buy, the bid of a sell): the trade's stop with that leg -- turtle.py's own rule (on_entry / on_add: the
        tighter of 2N from the newest fill and the exit channel, never looser than before) -- minus (a long) / plus
        (a short) TURTLE_BACKSTOP_N x N_entry, rounded to the symbol's digits; never moved afterwards. The bot's own
        stop only ever tightens and closes every leg at market, so it is always met first; the backstop acts only
        while the bot or the terminal is down. A leg it closes was closed beyond the trade's stop: the bot closes the
        other legs at once (_turtle_sync), or, all of them gone, ends the trade as closed outside it. 0.0 (none) when
        it cannot be known.
        """
        trial = copy.deepcopy(st)
        if trial['side'] == 0:
            T.on_entry(trial, side, price, now, units)
        else:
            T.on_add(trial, price, now)
        stop, n = trial.get('stop'), trial.get('n_entry')
        if not (_is_number(stop) and _is_number(n)):
            return 0.0
        sl = stop - TURTLE_BACKSTOP_N * n if side == 1 else stop + TURTLE_BACKSTOP_N * n
        digits = self._price_digits(trade_symbol)
        sl = round(sl, digits) if digits is not None else sl
        return float(sl) if sl > 0 else 0.0

    def _process_turtle(self, symbol):
        """
        The Turtle's poll loop (STRATEGY = 'turtle'), about once a second; turtle.py decides, this executes:
          market data and this bot's positions (MAGIC) -> the levels of the closed D1 bars (read again when a UTC
          day starts: every D1 bar closed since raises an open trade's stop and arms its entry orders) -> the vote of
          the last closed M15 bar (read again when one closes) -> the book matched with the positions (rebuilt from
          them without the state file) -> on a live market, one decision: the stop (every leg closed at market),
          else an add, else -- flat -- an entry (a market order; the unit from the virtual balance, fixed for the
          trade) -> the book in OUTPUT_DIR/state/<symbol>_turtle.json -> the dashboard JSON.
        Times are the terminal's (the last tick's): a bar is closed once a tick after its end has arrived.
        """
        from datetime import datetime

        sym_cfg = self.symbol_configs.get(symbol, {})
        brake_manual = self.symbols_config.get('brake', 0)
        step_up_balance = sym_cfg.get('step_up_balance', 0)
        max_limit = sym_cfg.get('unit_max_limit', 1)
        mtqty = self.symbols_config.get('mtqty', 0.01)
        trade_symbol = self.symbol_map.get(symbol, symbol)
        params = turtle_params()
        vote_name = _tf_name(TURTLE_VOTE_TF)
        vote_s = _TF_SECONDS[_tf_key(TURTLE_VOTE_TF)]
        vote_kw = dict(rsi_length=RSI_LENGTH, rsi_ma_type=RSI_MA_TYPE, macd_fast=MACD_FAST, macd_slow=MACD_SLOW,
                       macd_signal=MACD_SIGNAL, lookback=PEAK_LOOKBACK, width=PIVOT_WIDTH,
                       rsi_ob=RSI_PEAK_OB, rsi_os=RSI_PEAK_OS)

        st = self._load_turtle_state(symbol)
        _history_done = st is not None          # no state file: the armed orders / last exit from the deal history
        if st is None:
            st = T.new_state()
        rows = rows_t = None
        _rows_day = None
        vote, vote_info, vote_q, vote_bar = 0, None, None, None
        units = int(st['units']) if st['side'] else 1
        _virtual_balance = None
        _units_at = -1e18
        _last_daily_save = 0.0
        _last_hist_save = 0.0
        print(f"[{symbol}] {T.describe(TURTLE_SYSTEM)}")
        # the trace: the start-up block of the text log (branch, design, every constant, the book found)
        self._trace(symbol, 'loop_start', locals())

        while True:
            try:
                _iter_start = time.perf_counter()
                # ── the terminal must answer and hold this bot's demo account, else this poll decides nothing ──
                if not self._poll_guard(symbol):
                    self._trace(symbol, 'poll_skipped', 'guard')
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue
                try:
                    with self.mt5_lock:
                        mt5.symbol_select(trade_symbol, True)
                        market_status = self.position_helper.get_market_status(
                            trade_symbol, getattr(mt5, MARKET_STATUS_TIMEFRAME), lookback_minutes=MARKET_LOOKBACK_MINUTES
                        )
                        buy_positions = self.position_helper.get_buy_positions(trade_symbol)
                        sell_positions = self.position_helper.get_sell_positions(trade_symbol)
                        # the account again, right after the positions: a switch since the poll's first check would
                        # hand this poll another account's positions (read as legs closed outside the bot)
                        account_bad = self._account_problem()
                        account_info = self.position_helper.get_account_info()
                        server_time = self.position_helper._get_server_time(trade_symbol)
                        tick = mt5.symbol_info_tick(trade_symbol)
                except TerminalReadError as e:
                    # The positions are not known this poll (not "none"): the book is not matched with them (it would
                    # end the trade as closed outside the bot), and nothing is decided.
                    self._poll_failed(symbol, str(e))
                    self._trace(symbol, 'poll_skipped', 'positions', str(e))
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue
                if account_bad is not None:
                    # Not this bot's account any more: the poll decides nothing, as _poll_guard refuses it.
                    self._account_refused(symbol, account_bad)
                    self._trace(symbol, 'poll_skipped', 'account_recheck', account_bad)
                    time.sleep(1)
                    if self._stop_event.is_set():
                        return
                    continue
                self._poll_succeeded(symbol)
                bid = float(tick.bid) if tick is not None else None
                ask = float(tick.ask) if tick is not None else None
                now = _tick_time(tick)
                live = bool(market_status.get('is_open')) if market_status else False
                buy_signal = sell_signal = Signal.DO_NOTHING
                order_response = close_response = None
                exit_reason = None
                changed = False

                # ── the levels: the closed D1 bars, read again when a UTC day starts (and until they are there) ──
                if now is not None and (rows is None or int((now - _TURTLE_SETTLE_S) // T.DAY_S) != _rows_day):
                    d1 = self._turtle_closed_bars(trade_symbol, 'TIMEFRAME_D1', TURTLE_D1_BARS, T.DAY_S, now)
                    got = 0 if d1 is None else len(d1['t'])
                    if got >= TURTLE_MIN_D1_BARS:
                        rows = T.daily_rows(d1['o'], d1['h'], d1['l'], d1['c'], **params)
                        rows_t = d1['t']
                        _rows_day = int((now - _TURTLE_SETTLE_S) // T.DAY_S)
                        if got < TURTLE_D1_BARS:
                            self._turtle_note(symbol, 'd1_short', f'{got} closed D1 bars from the terminal (asked for '
                                              f'{TURTLE_D1_BARS}): N can differ from the backtest by a little', server_time)
                    else:
                        # (wording only: without levels yet it does not trade; with the day before's it goes on with
                        # them and their stop, and asks again every poll)
                        self._turtle_note(symbol, 'd1', f'{got} closed D1 bars from the terminal, at least '
                                          f'{TURTLE_MIN_D1_BARS} needed: '
                                          + ('not trading' if rows is None else
                                             'the bot goes on with the levels and the stop of the D1 bar before '
                                             'and asks again every poll'), server_time)
                # ── the vote of the last closed M15 bar, read again when an M15 bar closes ──
                _q = None if now is None else int((now - _TURTLE_SETTLE_S) // vote_s)
                if _q is not None and _q != vote_q:
                    b15 = self._turtle_closed_bars(trade_symbol, vote_name, TURTLE_VOTE_BARS, vote_s, now)
                    if b15 is not None and len(b15['c']) >= _TURTLE_MIN_VOTE_BARS:
                        vote, vote_info = T.closed_bar_vote(b15['c'], self.indicator, **vote_kw)
                        vote_q = _q
                        vote_bar = int(b15['t'][-1])
                    else:
                        self._turtle_note(symbol, 'm15', f"{0 if b15 is None else len(b15['c'])} closed "
                                          f"{TURTLE_VOTE_TF} bars from the terminal: no vote, no entry", server_time)
                vote_fresh = _q is not None and vote_q == _q

                # ── the book and this bot's positions ──
                hold, pending = True, False
                if rows is not None and now is not None:
                    _c, hold, pending = self._turtle_sync(symbol, st, buy_positions, sell_positions, rows, rows_t,
                                                          mtqty, now, server_time)
                    changed |= _c
                    changed |= self._turtle_rows(symbol, st, rows, rows_t, server_time)
                    if not _history_done:
                        _history_done = True
                        if st['side'] == 0:
                            last_entry, last_out = self._turtle_history(trade_symbol, now)
                            if last_entry is not None and st['levels'] and last_entry >= st['levels']['from_time']:
                                st['armed'] = False          # this D1 bar's orders already filled today
                            if last_out is not None:
                                st['last_exit_time'] = float(last_out)
                        changed = True
                if changed:
                    self._save_turtle_state(symbol, st)
                if st['side'] != 0:
                    units = int(st['units'])
                elif time.time() - _units_at >= 60.0:
                    units, _virtual_balance = self._turtle_units(account_info, step_up_balance, max_limit)
                    _units_at = time.time()

                # ── one decision, on a live market with the levels and a quote ──
                if live and not hold and bid is not None and ask is not None:
                    side = st['side']
                    if side != 0 and (st['closing'] or T.exit_due(st, bid, ask)):
                        positions = buy_positions if side == 1 else sell_positions
                        stop, origin = st['stop'], T.stop_origin(st)
                        with self.mt5_lock:
                            close_response = self.position_helper.close_by_type(trade_symbol, 0 if side == 1 else 1)
                        closed = int(close_response.get('closed_count', 0) or 0)
                        failed = int(close_response.get('failed_count', 0) or 0)
                        if getattr(self, '_turtle_stop_passed', False):
                            exit_reason = 'stop_passed_outside'       # a leg closed beyond the stop (_turtle_sync)
                            self._turtle_stop_passed = False
                        else:
                            exit_reason = 'stop' if not st['closing'] else 'close_retry'
                        details = {'mt5_symbol': trade_symbol, 'positions_closed': closed, 'failed': failed,
                                   'reason': exit_reason, 'stop': stop, 'stop_origin': origin,
                                   'bid': bid, 'ask': ask, 'legs': len(st['legs']),
                                   'total_profit': positions['total_profit'] if positions else 0,
                                   'response': close_response}
                        if failed == 0 and closed > 0:
                            T.on_exit(st, now)
                        else:
                            # Some legs not closed -- or none: close_by_type's own positions read found none of this
                            # bot's (another program switched the account just now, or the legs are gone): the book
                            # stays, and the close is decided again on the next poll. If the legs are really gone,
                            # the next _turtle_sync ends the trade (closing set: not as closed outside the bot).
                            st['closing'] = True
                        self._save_turtle_state(symbol, st)
                        if side == 1:
                            buy_signal = Signal.CLOSE_BUY
                        else:
                            sell_signal = Signal.CLOSE_SELL
                        self._log_event(symbol, 'CLOSE_BUY' if side == 1 else 'CLOSE_SELL', 'EXIT', details,
                                        server_time=server_time)
                    elif side != 0 and not pending:
                        lvl = T.add_due(st, bid, ask, now, TURTLE_MAX_LEGS)
                        if lvl is not None:
                            qty = st['units'] * mtqty
                            send = self.position_helper.buy if side == 1 else self.position_helper.sell
                            with self.mt5_lock:
                                backstop = self._turtle_backstop(trade_symbol, st, side, ask if side == 1 else bid, now)
                                order_response = send(trade_symbol, qty, sl=backstop, tp=0.0, auto_sltp=False)
                            ok = self._order_done(order_response)
                            if ok:
                                px = float(getattr(order_response, 'price', 0.0) or 0.0) or (ask if side == 1 else bid)
                                T.on_add(st, px, now, getattr(order_response, 'order', None) or None)
                                self._save_turtle_state(symbol, st)
                                self._log_event(symbol, 'BUY_MORE_EXECUTED' if side == 1 else 'SELL_MORE_EXECUTED',
                                                'ENTRY', {'mt5_symbol': trade_symbol, 'qty': qty, 'leg': len(st['legs']),
                                                          'level': lvl, 'fill': px, 'stop': st['stop'],
                                                          'backstop_sl': backstop,
                                                          'response': str(order_response)}, server_time=server_time)
                            else:
                                self._turtle_note(symbol, 'order', f'add refused: {order_response}', server_time)
                            if side == 1:
                                buy_signal = Signal.BUY_MORE
                            else:
                                sell_signal = Signal.SELL_MORE
                            time.sleep(ORDER_COOLDOWN_SECONDS)
                    elif side == 0 and not pending:
                        d = T.entry_due(st, bid, ask, vote if vote_fresh else 0, now)
                        if d != 0 and brake_manual:
                            self._turtle_note(symbol, 'brake', 'Brake active — Turtle entry skipped', server_time,
                                              {'side': 'BUY' if d == 1 else 'SELL'})
                        elif d != 0:
                            units, _virtual_balance = self._turtle_units(account_info, step_up_balance, max_limit)
                            _units_at = time.time()
                            qty = units * mtqty
                            lv = st['levels']
                            send = self.position_helper.buy if d == 1 else self.position_helper.sell
                            with self.mt5_lock:
                                backstop = self._turtle_backstop(trade_symbol, st, d, ask if d == 1 else bid, now, units)
                                order_response = send(trade_symbol, qty, sl=backstop, tp=0.0, auto_sltp=False)
                            if self._order_done(order_response):
                                px = float(getattr(order_response, 'price', 0.0) or 0.0) or (ask if d == 1 else bid)
                                T.on_entry(st, d, px, now, units, getattr(order_response, 'order', None) or None)
                                self._save_turtle_state(symbol, st)
                                self._log_event(symbol, 'BUY_EXECUTED' if d == 1 else 'SELL_EXECUTED', 'ENTRY', {
                                    'mt5_symbol': trade_symbol, 'qty': qty, 'units': units, 'balance': _virtual_balance,
                                    'level': lv['buy'] if d == 1 else lv['sell'], 'fill': px, 'vote': vote,
                                    'vote_bar': _iso(vote_bar), 'n_entry': st['n_entry'], 'stop': st['stop'],
                                    'stop_origin': T.stop_origin(st), 'd1_bar': _iso(lv['bar_time']),
                                    'use20': lv['use20'], 'backstop_sl': backstop,
                                    'response': str(order_response)}, server_time=server_time)
                            else:
                                self._turtle_note(symbol, 'order', f'entry refused: {order_response}', server_time)
                            if d == 1:
                                buy_signal = Signal.BUY
                            else:
                                sell_signal = Signal.SELL
                            time.sleep(ORDER_COOLDOWN_SECONDS)

                # ── the dashboard JSON ──
                lv = st.get('levels') or {}
                r_sign = int(((vote_info or {}).get('rsi') or {}).get('sign', 0) or 0)
                m_sign = int(((vote_info or {}).get('macd') or {}).get('sign', 0) or 0)
                full = len(st['legs']) >= TURTLE_MAX_LEGS
                analysis_data = {
                    'strategy': 'turtle',
                    'design': DESIGN_NAME,
                    'candle_fresh': live,
                    'slopes': {_tf_key(TURTLE_VOTE_TF): {'rsi': (vote_info or {}).get('rsi', {}),
                                                         'macd': (vote_info or {}).get('macd', {})}},
                    'entry_direction': {1: 'BUY', -1: 'SELL'}.get(vote if vote_fresh else 0, 'WAIT'),
                    'open_score': r_sign + m_sign, 'fc_score': r_sign + m_sign,
                    'entry_allowed': bool(st['armed']) and st['side'] == 0 and not brake_manual,
                    'exit_reason': exit_reason,
                    'unit_times': units, 'step_up_balance': step_up_balance, 'unit_max_limit': max_limit,
                    'virtual_balance': _virtual_balance if virtual_balance_enabled() else None,
                    'turtle': {
                        'system': TURTLE_SYSTEM, 'd1_bar': _iso(lv.get('bar_time')), 'd1_bars': 0 if rows_t is None else len(rows_t),
                        'buy_level': lv.get('buy'), 'sell_level': lv.get('sell'), 'n': lv.get('n'),
                        'use20': lv.get('use20'), 'armed': bool(st['armed']),
                        'vote': vote if vote_fresh else None, 'vote_bar': _iso(vote_bar),
                        'side': {1: 'BUY', -1: 'SELL'}.get(st['side']), 'legs': len(st['legs']),
                        'max_legs': TURTLE_MAX_LEGS, 'units': st['units'] or units, 'n_entry': st['n_entry'],
                        'stop': st['stop'], 'stop_origin': T.stop_origin(st),
                        'next_add': None if (full or st['side'] == 0) else T.add_level(st),
                        'entry_time': _iso(st['entry_time']), 'last_exit_time': _iso(st['last_exit_time']),
                        'pending_fill': pending, 'closing': bool(st['closing']), 'hold': hold,
                    },
                }
                symbol_data = {
                    'symbol': symbol,
                    'mt5_symbol': trade_symbol,
                    'last_updated': datetime.now(tz=timezone.utc).isoformat(),
                    'server_time': server_time.isoformat(),
                    'market_status': market_status,
                    'account': account_info if account_info else {},
                    'positions': {
                        name: {
                            'count': p['count'] if p else 0,
                            'total_profit': p['total_profit'] if p else 0,
                            'total_volume': p['total_volume'] if p else 0,
                            'first_profit': p['first_profit'] if p else 0,
                            'first_volume': p['first_volume'] if p else 0,
                            'last_profit': p['last_profit'] if p else 0,
                            'last_volume': p['last_volume'] if p else 0,
                        } for name, p in (('buy', buy_positions), ('sell', sell_positions))
                    },
                    'signal': {'buy_status': buy_signal.name, 'sell_status': sell_signal.name},
                    'analysis': analysis_data,
                    'order_response': None if order_response is None else str(order_response),
                    'demo': {'branch': DEMO_BRANCH, 'magic': MAGIC, 'design': DESIGN_NAME,
                             'virtual_balance': analysis_data.get('virtual_balance'), 'turtle_book': st},
                }
                if close_response is not None:
                    symbol_data['close_response'] = close_response
                iteration_ms = round((time.perf_counter() - _iter_start) * 1000, 1)
                symbol_data['iteration_ms'] = iteration_ms
                analysis_data['iteration_ms'] = iteration_ms
                print(f"[{symbol}] iteration {iteration_ms} ms")
                self._save_symbol_data(symbol, symbol_data)

                _now_ts = time.time()
                if live:
                    try:
                        if _now_ts - _last_daily_save >= 60:
                            self._save_daily_trades(symbol, mt5_symbol=trade_symbol)
                            _last_daily_save = _now_ts
                        if _now_ts - _last_hist_save >= 300:
                            self._save_historical_summary(symbol, mt5_symbol=trade_symbol)
                            _last_hist_save = _now_ts
                    except Exception:
                        # Non-critical, don't break the main loop (a WARN with the traceback in the text log)
                        self._trace(symbol, 'exception', 'SAVE', 'the daily-trade / history-summary files could not be '
                                    'saved (tried again next poll)', level='WARN')

                # ── the trace (tracelog.py): reads this poll's locals, writes the dashboard's files and the text log ──
                self._trace(symbol, 'poll', locals())

                time.sleep(1)
                if self._stop_event.is_set():
                    return

            except Exception as e:
                print(f"[{symbol}] Error: {e}")
                self._trace(symbol, 'exception', 'LOOP', f'the poll failed: {e!r}; the loop goes on in 1 s')
                time.sleep(1)
                if self._stop_event.is_set():
                    return

    def run_multithreaded_processing(self):
        """Step 4: Start processing for all symbols.
        
        Single-symbol mode: runs directly on the main thread (no threading overhead).
        Multi-symbol mode: spawns one thread per symbol (legacy, not recommended).
        """
        # Reset stop event for this run
        self._stop_event.clear()

        # ── Single-symbol: run directly on main thread (no threading) ──
        if len(self.symbols) == 1:
            symbol = self.symbols[0]
            print(f"\n{'='*60}")
            print(f"  Running single-symbol process: {symbol}")
            print(f"{'='*60}")
            print(f"Press Ctrl+C to stop\n")
            try:
                self.process_symbol(symbol)
            except KeyboardInterrupt:
                print("\n\n⚠ Stopping...")
                self._stop_event.set()
                raise
            return

        # ── Multi-symbol: threaded (legacy fallback) ──
        print(f"\n{'='*60}")
        print(f"  Starting Continuous Multithreaded Processing")
        print(f"  ⚠ Running {len(self.symbols)} symbols in threads — consider")
        print(f"    running separate processes with --symbol for each instead.")
        print(f"{'='*60}\n")
        
        max_workers = len(self.symbols)
        
        print(f"Launching {max_workers} threads (1 per symbol)...")
        print(f"Press Ctrl+C to stop\n")
        
        # Start threads — they will run until stop_event is set
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='Symbol') as executor:
            # Submit all symbol processing tasks (infinite loops)
            futures = [
                executor.submit(self.process_symbol, symbol) 
                for symbol in self.symbols
            ]
            
            # Keep main thread alive — futures complete when stop_event is set
            try:
                for future in as_completed(futures):
                    future.result()
                    if self._stop_event.is_set():
                        break
            except KeyboardInterrupt:
                print("\n\n⚠ Stopping all threads...")
                self._stop_event.set()
                executor.shutdown(wait=False, cancel_futures=True)
                raise
    
    def cleanup(self):
        """Step 5: Cleanup and shutdown MT5"""
        if self.mt5_initialized:
            mt5.shutdown()
            self.mt5_initialized = False
            print("\n✓ MT5 connection closed")
    
    def _init_cycle(self):
        """
        Single initialisation cycle: write mode to config → load credentials
        → load symbols → initialise MT5.  Returns True on success.
        """
        # ── Write current mode to active_config so dashboard can display it ──
        _acfg_path = os.path.join(OUTPUT_DIR, ACTIVE_CONFIG_FILENAME)
        try:
            with open(_acfg_path, 'r') as _af:
                _acfg = json.load(_af)
        except (FileNotFoundError, json.JSONDecodeError):
            _acfg = {}
        _acfg['mode'] = self.mode
        try:
            os.makedirs(os.path.dirname(_acfg_path) or '.', exist_ok=True)
            with open(_acfg_path, 'w') as _af:
                json.dump(_acfg, _af, indent=2)
        except OSError:
            pass

        print(f"\n{'#'*60}")
        print(f"#  JOB STARTED - {self.mode.upper()} MODE")
        print(f"{'#'*60}\n")
        print(f"✓ {design_summary()}")
        self._boot('INFO', 'START', f'job started ({self.mode} mode) on the branch {DEMO_BRANCH}, design {DESIGN_NAME!r}', {
            'mode': self.mode, 'branch': DEMO_BRANCH, 'design': DESIGN_NAME, 'strategy': STRATEGY, 'magic': MAGIC,
            'symbol': self.target_symbol, 'pid': os.getpid(), 'python': sys.version.split()[0]})

        # Step 1: Load Credentials
        if not self.load_credentials():
            print("\n✗ Job Failed: Could not load credentials")
            return False

        # Step 2: Load Symbols
        if not self.load_symbols():
            print("\n✗ Job Failed: Could not load symbols")
            return False

        # Step 3: Initialize MT5
        if not self.initialize_mt5():
            print("\n✗ Job Failed: Could not initialize MT5")
            return False

        return True

    def execute_job(self):
        """
        Main Job Orchestrator.
        Initialises MT5, starts worker threads, and runs until Ctrl+C.
        Mode is fixed from the command line — use start_job.bat to switch.
        """
        try:
            # ── The design in constants.py must be one this bot can run (checked once, before connecting) ──
            _problems = design_problems()
            if _problems:
                for _p in _problems:
                    print(f"✗ Design: {_p}")
                print("\n✗ Job Failed: the design in constants.py is refused (see above)")
                self._boot('ERROR', 'START', 'the design in constants.py is refused: ' + '; '.join(_problems))
                self._boot_flush()
                return False

            # ── Initialise (retry up to 3 times) ──
            for _attempt in range(1, 4):
                if self._init_cycle():
                    break
                print(f"\n⚠ Init attempt {_attempt}/3 failed, retrying in 5s...")
                self._boot('WARN', 'START', f'start attempt {_attempt}/3 failed ({self._init_problem or "see above"})')
                time.sleep(5)
            else:
                print("\n✗ All init attempts failed. Restart start_job.bat to try again.")
                self._boot('ERROR', 'START', 'all 3 start attempts failed: the job ends (the launcher starts it again)')
                self._boot_flush()
                return False

            # ── Run processing (blocks until Ctrl+C) ──
            self.run_multithreaded_processing()

            self.cleanup()
            print(f"\n{'#'*60}")
            print(f"#  JOB COMPLETED SUCCESSFULLY")
            print(f"{'#'*60}\n")
            self._boot('INFO', 'START', 'job completed')
            return True

        except KeyboardInterrupt:
            print("\n\n⚠ Job interrupted by user")
            self._boot('WARN', 'START', 'job stopped by the user (Ctrl+C)')
            self._boot_flush()
            self._stop_event.set()
            self.cleanup()
            return False
        except Exception as e:
            print(f"\n✗ Job Failed with exception: {e}")
            self._boot('ERROR', 'START', f'the job failed: {e!r}', exc=True)
            self._boot_flush()
            self._stop_event.set()
            self.cleanup()
            return False


def main():
    """
    Main entry point for the application
    
    Usage:
        app.py [mode]                      # Run all active symbols (legacy)
        app.py [mode] --symbol SYMBOL      # Run a SINGLE symbol only (recommended)
    
    Running one symbol per process avoids MT5 threading issues
    where SHA candle data can overlap between symbols.
    """
    import argparse

    parser = argparse.ArgumentParser(description='Alcadeias Trading Bot')
    parser.add_argument('mode', nargs='?', default='demo', choices=['demo', 'live'],
                        help='Account mode (default: demo)')
    parser.add_argument('--symbol', '-s', type=str, default=None,
                        help='Run only this symbol (e.g. BTCUSDm). '
                             'Recommended: run one process per symbol.')
    args = parser.parse_args()
    if DEMO_BRANCH and args.mode != 'demo':
        parser.error(f"this is the demo branch {DEMO_BRANCH}: mode '{args.mode}' is refused, it trades on demo only")

    # Create bot instance and execute job
    bot = MT5TradingBot(mode=args.mode, target_symbol=args.symbol)
    success = bot.execute_job()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if '__main__' == __name__:
    main()