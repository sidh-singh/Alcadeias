import MetaTrader5 as mt5
import copy
import errno
import fnmatch
import hashlib
import json
import ntpath
import numbers
import os
import re
import secrets
import sys
import threading
import time
import types
from contextlib import contextmanager
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
    # this branch (the deployment block of constants.py): the label, the account it is one of, this bot's own mark
    # on its orders, and its share of the account balance
    BRANCH, ACCOUNT_SLOT, MAGIC, ACCOUNT_SHARE,
    # ... the other bot of the account, the folder the two share, the accounts the old bots traded, and the values
    # the start checks before it trusts the block (the safety's limits, the days of logs kept)
    PARTNER_BRANCH, ACCOUNT_FOLDER, OLD_LOGINS_SHA256, LOG_KEEP_DAYS,
    SAFETY_DEFAULT_ON, SAFETY_DROP_PCT, SAFETY_DAY_PCT, SAFETY_STREAK_N,
    # the Turtle (STRATEGY = 'turtle')
    TURTLE_SYSTEM, TURTLE_N_LEN, TURTLE_STOP_N, TURTLE_ADD_N, TURTLE_MAX_LEGS, TURTLE_TICK, TURTLE_BACKSTOP_N,
    TURTLE_VOTE_TF, TURTLE_VOTE_BARS, TURTLE_D1_BARS, TURTLE_MIN_D1_BARS,
)

# How the process ends tells the launcher (start_job.bat) what to do next.
EXIT_OK = 0                      # stopped by the owner (Ctrl+C): the launcher stops
EXIT_RETRY = 1                   # a failure that may heal by itself: the launcher starts the bot again after 30 s
EXIT_NEEDS_OWNER = 78            # something only the owner can fix: the launcher says so and does NOT start it again
                                 # (not 2 or 3: Python and Windows end a crashed process with those)

try:
    import safety                    # the account's shared helpers (the account number's tail, its folder) and the
                                     # auto-safety; the bot does not run without it, so a plain import
except Exception as _e:
    # safety.py is missing or damaged (a pull that did not finish, a file changed on the server). Starting the bot
    # again cannot repair that, so a bot started as a program says what to do and ends with EXIT_NEEDS_OWNER: the
    # launcher then does not start it again every 30 s. Imported by something else (a test, a replay), the import
    # fails as any import does.
    if __name__ == '__main__':
        print(f'safety.py in {Path(__file__).resolve().parent} could not be loaded ({type(_e).__name__}: {_e}). '
              f'The branch folder is damaged or not complete: run "git pull" in it (or clone the branch again), '
              f'then start again.')
        sys.exit(EXIT_NEEDS_OWNER)
    raise
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

_MODE = 'live'                   # the only mode of this branch, and the block of mt5_credentials.json it reads


def _wrong_mode_text():
    return f'This is the real-money branch {BRANCH}: start it with "start_job.bat live".'


def _err_text(e):
    """An exception for the text log and the dashboard: its type and its message. Never repr(e): the repr of a
    decode error holds every byte it was decoding (a whole credentials file, passwords included)."""
    try:
        return f'{type(e).__name__}: {e}'
    except Exception:
        return type(e).__name__


def _replace_retry(src, dst):
    """os.replace, tried again for about 0.24 s while Windows refuses it (PermissionError: a reader such as the
    dashboard has dst open this moment)."""
    for wait in (0.005, 0.01, 0.02, 0.04, 0.06, 0.1, None):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if wait is None:
                raise
            time.sleep(wait)


# ─── the small files of the start: who runs, which account a folder and a MetaTrader 5 belong to ───
# They are read and written by the two bots of an account at the same time, so: a write goes into a temp file of
# a name no other write uses and is then moved over the file (a reader never meets half of it); a read never
# raises (missing, held by another program this moment, or not JSON are answers). None of them is touched while
# mt5_lock is held: no order, close or terminal read ever waits for the disk because of them.
_NAME_BAD = re.compile(r'[^A-Za-z0-9_.-]')       # everything a file name this module builds never holds


def _file_part(text):
    """`text` as part of a file name: letters, digits, '_', '-' and '.' only (Windows refuses < > : " / \\ | ? *)."""
    s = _NAME_BAD.sub('_', str(text))
    return s if s.strip('.') else '_'


def _name_stamp(t):
    """A time as part of a file name: yyyymmdd_hhmmss, UTC (no colon: Windows refuses it)."""
    from datetime import datetime
    return datetime.fromtimestamp(float(t), tz=timezone.utc).strftime('%Y%m%d_%H%M%S')


def _clock_text(t, now=None):
    """'02:14 UTC' for the owner; with the day ('22 Nov 02:14 UTC') when it is not today's (`now`)."""
    from datetime import datetime
    try:
        d = datetime.fromtimestamp(float(t), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return 'an unknown time'
    text = f'{d.hour:02d}:{d.minute:02d} UTC'
    try:
        today = datetime.fromtimestamp(float(time.time() if now is None else now), tz=timezone.utc).date()
    except (TypeError, ValueError, OverflowError, OSError):
        today = d.date()
    return text if d.date() == today else f"{d.day} {d.strftime('%b')} {text}"


def _json_text(data):
    return json.dumps(data, indent=1, sort_keys=True, default=str)


def _tmp_name(path):
    """A temp file beside `path` that no other write uses: <name>.<pid>.<8 hex>.tmp."""
    return f'{path}.{os.getpid()}.{secrets.token_hex(4)}.tmp'


def _write_json_atomic(path, data):
    """Write a small JSON file whole or not at all: a temp file of its own name (_tmp_name), then os.replace
    (tried again briefly while Windows refuses it). Raises OSError / ValueError: the caller notes it and goes on."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = _tmp_name(path)
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(_json_text(data))
        _replace_retry(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _create_json_exclusive(path, data):
    """Create a small JSON file only if it is not there yet, whole or not at all: True = this call made it, False =
    it was there already (the other bot of the account was first). The content is written to a temp file first and
    the file is made from it as a hard link, which the system refuses when the name exists; on a disk without hard
    links, the plain exclusive creation. Any other failure raises OSError."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    text = _json_text(data)
    tmp = _tmp_name(path)
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        try:
            os.link(tmp, path)
            return True
        except FileExistsError:
            return False
        except (OSError, AttributeError, NotImplementedError):
            pass                            # no hard links here: the plain exclusive creation below
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    try:
        f = open(path, 'x', encoding='utf-8', newline='\n')
    except FileExistsError:
        return False
    with f:
        f.write(text)
    return True


def _read_json_file(path, tries=1):
    """A small JSON file: ('ok', value), ('missing', None), ('unreadable', why) -- it is there but could not be
    opened or read (another program holds it this moment) -- or ('invalid', why) -- it was read and is not JSON.
    `tries` above 1: a refusal is tried again after a few hundredths of a second. Never raises."""
    why = ''
    for attempt in range(max(1, int(tries))):
        if attempt:
            time.sleep(0.05)
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except FileNotFoundError:
            return 'missing', None
        except OSError as e:
            why = _err_text(e)
            continue
        except Exception as e:              # (a path that is no path: never an exception into the start)
            return 'unreadable', _err_text(e)
        try:
            return 'ok', json.loads(raw.decode('utf-8-sig'))
        except Exception as e:              # (UnicodeDecodeError is a ValueError; anything else: still not JSON)
            return 'invalid', type(e).__name__
    return 'unreadable', why


def _remove_file(path):
    """Delete a file if it is there. True when it is gone afterwards; never raises."""
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def _parent_folder():
    """The folder this bot's own folder (OUTPUT_DIR) is in: C:\\Alcadeias on the server. The account's folder, the
    terminal claims and the old bots' files are in it. By the rule of safety.account_dir: Windows rules for a
    Windows path whatever system this runs on, else the system's own."""
    out = str(OUTPUT_DIR)
    drive, _ = ntpath.splitdrive(out)
    if drive or '\\' in out:
        return ntpath.dirname(ntpath.normpath(out))
    return os.path.dirname(os.path.normpath(out))


def _account_folder():
    """The folder the two bots of this account share, beside OUTPUT_DIR (safety.account_dir)."""
    return safety.account_dir(OUTPUT_DIR, ACCOUNT_FOLDER)


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


def _hide_login(obj, login, tail, depth=0, _path=None):
    """
    A copy of `obj` -- its dicts, lists and tuples, 64 levels deep -- with the account number `login` replaced by
    `tail` ('...1234') wherever it stands: a whole number equal to it, and in a text every run of digits that is that
    number, also with zeros in front ('C:\\MT5_12345678\\terminal64.exe' -> 'C:\\MT5_...5678\\terminal64.exe'). Any
    other value whose text holds the number becomes that text, masked (the strategy log writes such a value as its
    text anyway). What _log_event writes goes through this, as tracelog's own files go through its net: the number is
    in no file and on no page (the History tab shows the strategy log). login None: `obj` as it is. Never loops on a
    container that holds itself.
    """
    if login is None or obj is None or isinstance(obj, (bool, float)):
        return obj
    if isinstance(obj, numbers.Integral):
        return tail if int(obj) == login else obj
    if isinstance(obj, str):
        digits = str(login)
        if digits not in obj:
            return obj
        return re.sub(r'(?<!\d)0*' + digits + r'(?!\d)', tail, obj)
    if isinstance(obj, (dict, list, tuple)):
        if depth >= 64:
            return obj
        path = set() if _path is None else _path
        if id(obj) in path:
            return obj
        path.add(id(obj))
        try:
            if isinstance(obj, dict):
                return {_hide_login(k, login, tail, depth + 1, path) if isinstance(k, (str, numbers.Integral)) else k:
                        _hide_login(v, login, tail, depth + 1, path) for k, v in obj.items()}
            return [_hide_login(v, login, tail, depth + 1, path) for v in obj]
        finally:
            path.discard(id(obj))
    try:
        text = str(obj)
    except Exception:
        return obj
    return _hide_login(text, login, tail) if str(login) in text else obj


def _utc(ts):
    """Epoch seconds -> aware UTC datetime (what the terminal's time arguments expect)."""
    from datetime import datetime
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


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


def sizing_record(account_balance, sizing_balance, step, units, mtqty, unit_max, source, t=None):
    """
    How the unit in effect was sized: the poll local _sizing (the trace and the dashboard read it), kept with an
    open basket (its 'sizing') and in the Turtle's side file.
      share                         ACCOUNT_SHARE: this bot's part of the account (the other bot has the rest)
      account_balance               the account's balance the unit was derived from (closed trades only)
      sizing_balance                share x account_balance, to the cent: what the unit rule counted
      step, unit_max                symbols.json: step_up_balance, unit_max_limit
      units, lot                    the unit, and units x mtqty
      next_unit_at_account_balance  the ACCOUNT balance from which a new trade gets one more unit:
                                    units x step / share; None at the cap (and without a step)
      source                        'balance': derived on this poll from the account balance (flat);
                                    'entry': fixed at the entry of the open trade (an open trade keeps its unit);
                                    'positions': an open trade taken over from the terminal without its record
                                    (the unit from its oldest position's volume, the balances not known);
                                    'unknown': flat and the balance is not known -- no new trade is opened
      t                             when the balance was read (epoch seconds)
    """
    share = ACCOUNT_SHARE if _is_number(ACCOUNT_SHARE) else None
    nxt = lot = None
    try:                                        # (a record for the trace only: it must never cost a poll)
        if (share and share > 0 and _is_number(step) and step > 0 and _is_number(units) and _is_number(unit_max)
                and units < unit_max):
            nxt = round(units * step / share, 2)
        if _is_number(units) and _is_number(mtqty):
            lot = round(units * mtqty, 6)
    except Exception:
        nxt = lot = None
    return {'share': share, 'account_balance': account_balance, 'sizing_balance': sizing_balance, 'step': step,
            'units': units, 'lot': lot, 'unit_max': unit_max, 'next_unit_at_account_balance': nxt,
            'source': source, 't': t}


def _open_hold_text(hold):
    """One plain sentence for why an opening order was not sent (the strategy log's note)."""
    why = (hold or {}).get('why')
    if why == 'balance_unknown':
        return ('the account balance is not known on this poll, or not above 0, so the size of a new trade cannot '
                'be worked out')
    if why in _OPEN_HOLD_WORDS:
        return _OPEN_HOLD_WORDS[why]
    return str(why)


def open_trade_sizing(record, units, step, mtqty, unit_max):
    """The sizing of an open basket / Turtle trade: the record made at its entry (it keeps that unit until it is
    closed, whatever the balance does), else -- a trade taken over from the terminal, or a record that is not this
    trade's -- its unit alone."""
    if isinstance(record, dict) and record.get('units') == units:
        return dict(record, source='entry')
    return sizing_record(None, None, step, units, mtqty, unit_max, 'positions')


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
    p.extend(deployment_problems())
    return p


_SHA256_TEXT = re.compile(r'[0-9a-f]{64}')


def deployment_problems():
    """Why the deployment block of constants.py (this branch's own values) cannot be used (empty = fine). The
    branch generator writes the block; a value missing or mistyped there must stop the start, never switch a
    check off without anybody noticing. No text here holds a value of OLD_LOGINS_SHA256."""
    p = []
    if not _is_int(MAGIC) or MAGIC <= 0:
        # (None or 0 = no mark at all: every position of the symbol would be this bot's, the other bot's and an
        # old bot's too)
        p.append(f'MAGIC must be a whole number above 0 (this bot finds its own trades by it), not {MAGIC!r}')
    if not _is_number(ACCOUNT_SHARE) or not 0 < ACCOUNT_SHARE <= 1:
        p.append(f"ACCOUNT_SHARE must be a number above 0 and at most 1 (this bot's part of the account balance), "
                 f'not {ACCOUNT_SHARE!r}')
    if not _is_int(LOG_KEEP_DAYS) or LOG_KEEP_DAYS < 1:
        p.append(f'LOG_KEEP_DAYS must be a whole number of 1 or more (the days of logs kept), not {LOG_KEEP_DAYS!r}')
    old = OLD_LOGINS_SHA256
    if (not isinstance(old, tuple) or not old
            or not all(isinstance(h, str) and _SHA256_TEXT.fullmatch(h) for h in old)):
        p.append("OLD_LOGINS_SHA256 must name the accounts the old bots traded (a tuple of SHA-256 texts, 64 "
                 "characters 0-9 a-f each, not empty): this branch was not finished by the generator")
    if not isinstance(ACCOUNT_FOLDER, str) or not ACCOUNT_FOLDER.strip('.') or _NAME_BAD.search(ACCOUNT_FOLDER):
        p.append(f"ACCOUNT_FOLDER must be the name of the account's folder (letters, digits, '_', '-' and '.' "
                 f'only), not {ACCOUNT_FOLDER!r}')
    if not isinstance(SAFETY_DEFAULT_ON, bool):
        p.append(f'SAFETY_DEFAULT_ON must be True or False, not {SAFETY_DEFAULT_ON!r}')
    limits = []                             # the problems of the three limits (a mistyped limit must not read as "off")
    for name, value in (('SAFETY_DROP_PCT', SAFETY_DROP_PCT), ('SAFETY_DAY_PCT', SAFETY_DAY_PCT)):
        if value is not None and (not _is_number(value) or not 0 <= value < 100):
            limits.append(f'{name} must be a percentage from 0 to below 100 (None or 0 = that rule is off), not '
                          f'{value!r}')
    if SAFETY_STREAK_N is not None and (not _is_number(SAFETY_STREAK_N) or SAFETY_STREAK_N < 0
                                        or SAFETY_STREAK_N != int(SAFETY_STREAK_N)):
        limits.append(f'SAFETY_STREAK_N must be a whole number of 0 or more (None or 0 = that rule is off), not '
                      f'{SAFETY_STREAK_N!r}')
    if not limits:
        try:                                # ... and what the safety itself accepts: it is given exactly these three
            safety.Limits(SAFETY_DROP_PCT, SAFETY_DAY_PCT, SAFETY_STREAK_N)
        except Exception as e:
            limits.append(f'the safety limits of this branch cannot be used: {e}')
    return p + limits


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
                f'votes {TURTLE_VOTE_TF} closed bars', f'magic {MAGIC}', _sizing_summary()]
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
    bits.append(_sizing_summary())
    return ' | '.join(bits)


def _sizing_summary():
    """'units from 0.5 x the account balance' (the start-up line)."""
    share = f'{ACCOUNT_SHARE:g}' if _is_number(ACCOUNT_SHARE) else repr(ACCOUNT_SHARE)
    return f'units from {share} x the account balance'


# ─── the terminal ───
_RECONNECT_AFTER = 5                         # polls in a row without the terminal (terminal_info() None) before the
                                             # bot connects again: mt5.shutdown(), then initialize_mt5()
_RECONNECT_BACKOFF_S = (5.0, 10.0, 30.0, 60.0)   # waits after a reconnect that failed (the last one repeats)
_LOG_REPEAT_S = 900.0                        # a problem that lasts (reconnects that fail, the terminal held by another
                                             # account) is logged again at most this often
_PENDING_FILL_S = 10.0                       # a basket the bot just opened waits this long for the terminal to list
                                             # its position (as the Turtle's legs do)
_MIN_CLOSED_BARS = 300                       # closed VOL_TF / TREND_TF bars an entry (and a rebuilt basket's unit)
                                             # needs: with fewer the EWMA unit is off by up to 12% (BTC H1, 100 bars)
_ACCOUNT_GRACE_S = 60.0                      # right after mt5.initialize(), a terminal that shows no account is read
                                             # again about once a second for this long before the bot may log in: a
                                             # terminal just started or restarted (a reboot of the server) logs into
                                             # its saved account by itself, and that can take most of a minute
_IPC_ERRORS = (-10005, -10000)               # last_error() codes of a broken connection to the terminal (IPC)
_START_ATTEMPTS = 3                          # start attempts of one process, _START_RETRY_S apart; then it ends and
_START_RETRY_S = 5.0                         # the launcher starts it again (or not: EXIT_NEEDS_OWNER)
_RECHECK_S = 2.0                             # an account that looks like one only the owner can change (another
                                             # server, not real, not hedging, not in US dollars) is read once more
                                             # this long after: a terminal that has just started may not have filled
                                             # in its account yet
# The bot's own login (only on a terminal that shows no account for _ACCOUNT_GRACE_S): after a login that did not
# go through, the next one is allowed this long after it -- the first, the second ... failure in a row; the last
# wait repeats. A wrong password in the file must not become a login every 90 s against a real trade server, from
# two bots, for as long as nobody looks: the launcher keeps starting the bot, the bot keeps attaching, and a
# terminal that finishes logging into its saved account (or that the owner logs in by hand) is picked up at once.
_LOGIN_WAITS_S = (900.0, 1800.0, 3600.0, 7200.0, 21600.0)
_LOGIN_ATTEMPT_FILE = 'login_attempt.json'   # in the account's folder: the last own login of either bot (the budget)
_PASSWORD_PLACEHOLDERS = ('placeholder', 'change_me', 'xxx')    # a login_pass that is no password (any letter case)
_TERMINAL_CLAIMS_DIR = 'terminal_claims'     # beside OUTPUT_DIR: one small file per MetaTrader 5 (the account whose
                                             # bots last passed the account checks on it)
_LOCK_TRIES = 3                              # a lock still held is asked again _LOCK_RETRY_S later, this often in all:
_LOCK_RETRY_S = 1.0                          # the system frees the lock of a process that has just ended a moment later
# An old bot (a hedging_* branch) still running on this server: it rewrites these files in ITS output folder --
# the parent folder of this bot's OUTPUT_DIR -- about once a second; nothing of the real-money branches writes
# there. A file changed less than _OLD_BOT_ALIVE_S ago: an old bot is alive. Looked at every _OLD_BOT_CHECK_S.
_OLD_BOT_FILES = ('account.json', 'XAUUSDm.json', 'BTCUSDm.json')
_OLD_BOT_ALIVE_S = 120.0
_OLD_BOT_CHECK_S = 10.0
_OLD_BOT_TEXT = ('An old bot is running on this server and uses the same MetaTrader 5. It trades whatever account '
                 "that MetaTrader 5 is logged into, and it would add to and close this bot's trades. Stop it; this "
                 'bot then starts by itself.')
_LIVE_START_FILE = 'live_start.json'         # OUTPUT_DIR/state: when this bot first traded this account (the
                                             # reporting reads -- the trades list, the history summary -- start there)
_LIVE_START_RETRY_S = 60.0                   # a history read or a write of it that failed is tried again this often
# What MetaTrader 5 can say that stops every order of a program (a warning, never a refusal: the bot goes on and
# every close is still tried): the reasons as the trace names them, and as the owner reads them.
_TRADING_NOT_ALLOWED = {
    'algo_trading_off': 'Algo Trading is switched off in MetaTrader 5 (the button in its toolbar)',
    'python_api_disabled': ('MetaTrader 5 blocks trading from Python (Tools > Options > Expert Advisors: "Disable '
                            'automatic trading via external Python API" is ticked)'),
    'account_trade_disabled': ('the account may not trade (it is logged in with a read-only investor password, or '
                               'the broker has switched trading off)'),
    'account_expert_disabled': 'the broker does not let programs trade this account',
}


# ─── the auto-safety in the poll loop (safety.py) and the orders it holds back ───
# Each poll: before its decision the Tracker's view (memory only) and the one flag every opening order of the
# poll is tested against; after its orders -- never between the positions read and the orders, never inside
# mt5_lock -- the cash read, the results of closed trades, the safety's files, its journal lines and the events.
_SAFETY_STATE_FILE = 'safety_state.json'     # OUTPUT_DIR/state: the Tracker's own state (safety.py writes it)
_SAFETY_CLOSES_FILE = 'safety_closes.json'   # OUTPUT_DIR/state: closed trades waiting for their result, and the
                                             # position ids of the Turtle's running trade (this module writes it)
_SAFETY_RETRY_S = 5.0                        # a step after the orders that failed is tried again this often
_SAFETY_SAY_S = 60.0                         # a step that keeps failing is printed / logged this often
_RESULT_WAIT_S = 600.0                       # a closed trade whose result the deal history does not show this long
                                             # counts with what the bot saw at its close (else as a loss)
_SKIP_SAY_S = 900.0                          # SAFETY_SKIP of one (kind, side) again after this long
# Refused opening orders: the first refusal starts a streak; while it is younger than _BACKOFF_AFTER_S the bot
# tries again at the poll's pace (as the demo bot does: gold is close-only for 90 s after the daily break and
# 210 s after the weekend), then once per _BACKOFF_EVERY_S[0], and after _BACKOFF_SLOW_AFTER_S once per
# _BACKOFF_EVERY_S[1]. A filled open ends it, and so do _BACKOFF_IDLE_S without an open wanted.
_BACKOFF_AFTER_S = 240.0
_BACKOFF_SLOW_AFTER_S = 900.0
_BACKOFF_EVERY_S = (30.0, 60.0)
_BACKOFF_IDLE_S = 600.0
_REFUSED_ONE_BY_ONE = 3                      # refusals of a streak logged one by one; then one line per ...
_REFUSED_SUMMARY_S = 30.0
_HOLD_BLOCKS = ('old_bot', 'safety', 'safety_checking')     # holds that are a block (5.8: a pyramid missed in one)
# The opening order the strategy wanted and this poll did not send, in the owner's words (the strategy log).
_OPEN_HOLD_WORDS = {
    'safety': 'the safety has blocked new trades (the bar at the top of the page says why)',
    'safety_checking': 'the safety is checking a change of the account balance that would reach a limit',
    'old_bot': ('an old bot is running on this server and uses the same MetaTrader 5: no new trade while it runs '
                '(the safety switch does not change that)'),
    'refused_backoff': 'the broker refused the last orders, so the next one is tried a little later',
}


def _cap(text):
    """The sentence with its first letter in capitals."""
    s = str(text)
    return s[:1].upper() + s[1:]


def _magic_owner(magic):
    """'the gold bot of account 3' for a magic number of the real-money branches (270000 + 100 x account + 10 x
    (1 gold, 2 BTC) + design digit), None for any other."""
    try:
        m = int(magic)
    except (TypeError, ValueError):
        return None
    if not 270100 <= m <= 271099:
        return None
    n, kind = (m - 270000) // 100, ((m - 270000) % 100) // 10
    bot = {1: 'gold', 2: 'BTC'}.get(kind)
    return f'the {bot} bot of account {n}' if bot and 1 <= n <= 10 else None


def _foreign_text(mt5_symbol, foreign):
    """The warning for trades on this bot's symbol that are not its own (6.1)."""
    magics = []
    for ex in (foreign or {}).get('examples') or []:
        m = ex.get('magic') if isinstance(ex, dict) else None
        if m is not None and m not in magics:
            magics.append(m)
    named = []
    for m in magics:
        owner = _magic_owner(m)
        named.append(f'magic {m}: {owner}' if owner else f'magic {m}')
    which = f" ({', '.join(named)})" if named else ''
    return (f"Trades that are not this bot's are open on {mt5_symbol} in this account{which}. Nothing manages them "
            "here: close them yourself. If the old ladder bot still runs on this account, stop it: it will add to "
            "or close this bot's trades.")


def _old_bot_elsewhere_text(tail):
    """The note for an old bot alive on this server with ANOTHER MetaTrader 5 than this bot's (no refusal: it
    trades the account its own MetaTrader 5 is logged into)."""
    return ("An old bot is running on this server, with another MetaTrader 5 than this bot's. This bot starts. Make "
            f'sure the old bot does not trade account {tail}: a MetaTrader 5 logged into that account too would let '
            "it add to and close this bot's trades.")


def _ipc_error(err):
    """True when last_error() reports a broken connection to the terminal (an IPC error, -10000 to -10005) or gives no
    code at all: an answer the terminal gave then says nothing about its account."""
    code = err[0] if isinstance(err, (tuple, list)) and err else None
    if isinstance(code, bool) or not isinstance(code, int):
        return True
    return _IPC_ERRORS[0] <= code <= _IPC_ERRORS[1]


# The MetaTrader 5 of the old bots on the server (the hedging_* branches): every credentials file names it as
# terminal_path until the owner gives an account its own installation. An old bot that still runs logs that
# MetaTrader 5 into its own account at every start and treats every position of its symbol as its own, so a bot
# whose terminal_path is this one must know it (_old_bots_terminal: the rule about an old bot on this server).
_OLD_BOT_TERMINALS = (r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe',)


def _norm_path(path):
    """A Windows path as the terminal reads it: '/' and '\\' alike, no doubled separators or '.', any case."""
    return ntpath.normpath(str(path).strip().strip('"').strip()).casefold()


def _same_file(a, b):
    try:
        return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)
    except (OSError, ValueError):
        return False


def _old_bots_terminal(path):
    """True when `path` is the old bots' MetaTrader 5: its terminal64.exe, its folder or a file in it -- however it is
    spelt (on the server also another spelling of the same file, such as a short 8.3 name)."""
    p = _norm_path(path)
    raw = str(path).strip().strip('"').strip()
    for old in _OLD_BOT_TERMINALS:
        exe = _norm_path(old)
        folder = ntpath.dirname(exe)
        if p in (exe, folder) or p.startswith(folder + '\\'):
            return True
        old_folder = ntpath.dirname(old)
        if _same_file(raw, old) or _same_file(raw, old_folder) or _same_file(ntpath.dirname(raw), old_folder):
            return True
    return False


def _account_name():
    """'account 2': which of the owner's accounts this branch trades (ACCOUNT_SLOT of the deployment block; never
    read from the branch's name, whose last digit is the design's)."""
    return f'account {ACCOUNT_SLOT}'


def _terminal_file_exists(path):
    """True when terminal_path names a file on this server: the terminal64.exe of the account's MetaTrader 5."""
    try:
        return os.path.isfile(str(path))
    except (OSError, ValueError, TypeError):
        return False


def _terminal_claim_path(path):
    """The claim file of the MetaTrader 5 at `path`: <the folder OUTPUT_DIR is in>/terminal_claims/<sha1 of the
    path as the terminal reads it (_norm_path: any spelling of the same path is the same file)>.json."""
    name = hashlib.sha1(_norm_path(path).encode('utf-8')).hexdigest() + '.json'
    return os.path.join(safety.account_dir(OUTPUT_DIR, _TERMINAL_CLAIMS_DIR), name)


def _login_wait_s(failed):
    """How long after an own login that did not go through -- the `failed`-th in a row -- the next one may be made."""
    try:
        n = int(failed)
    except (TypeError, ValueError):
        n = len(_LOGIN_WAITS_S)
    return _LOGIN_WAITS_S[max(1, min(n, len(_LOGIN_WAITS_S))) - 1]


def _password_usable(value):
    """True when login_pass is something the bot may log in with: text, not empty, not a stand-in for a password."""
    return (isinstance(value, str) and bool(value.strip())
            and value.strip().casefold() not in _PASSWORD_PLACEHOLDERS)


# ─── one process per branch ───
# Two processes of one bot share the magic number, the symbol and the state files: both would see "flat" and both
# would send the entry. So a starting bot takes a system lock on OUTPUT_DIR/state/<SYMBOL>.lock and keeps the file
# open for as long as it runs. The system frees the lock when the file is closed or the process ends, however it
# ends: a crash leaves nothing to clean up.
_ON_WINDOWS = os.name == 'nt'


def _lock_fd(fd):
    """An exclusive lock on the open file `fd`, without waiting: True = this process holds it now, False = it is
    held already (another process of this bot runs). Any other failure of the locking call raises OSError: the
    caller then goes on without the lock (a warning; a lock that cannot be asked must not keep a bot from its
    trades)."""
    if _ON_WINDOWS:
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)            # msvcrt locks from the file position: always the first byte
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EDEADLK):        # a locking violation: the byte is locked already
                return False
            raise
        return True
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            return False
        raise
    return True


class _ProcessLock:
    """The open lock file of a running bot. The lock lasts as long as the file is open: until the job ends
    (close), the process ends, or this object goes away with its bot (a test)."""

    def __init__(self, fd, path):
        self.fd = fd
        self.path = path

    def close(self):
        fd, self.fd = self.fd, None
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _login_number(value):
    """An account number as a whole number above 0: from a JSON whole number or a string of digits (an owner who
    types the quotes still starts); None for anything else -- a number with a fraction, true / false, text with
    other characters, 0 (what a terminal answers while it holds no account)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit() and int(text) > 0:
            return int(text)
    return None


def usable_credentials(block):
    """
    The one normalisation of a credentials block -- the "live" block of mt5_credentials.json, or what a replay gives
    the bot: (the block as the bot keeps it, None), or (None, why it cannot be used). Kept: login_id as a whole
    number (_login_number), server and terminal_path without spaces around them, every other key as it is. Not
    usable: no block, a login_id that is not an account number, an empty server, an empty terminal_path
    (mt5.initialize() would then attach to a MetaTrader 5 it picks itself). The reason names the key and never
    holds a value of the block: a password typed into the wrong line must not reach a log.
    """
    if not isinstance(block, dict):
        return None, 'the block is missing or is not a { ... } object'
    login = _login_number(block.get('login_id'))
    if login is None:
        return None, 'login_id must be the account number: a whole number above 0'
    server = block.get('server')
    server = '' if server is None or isinstance(server, bool) else str(server).strip()
    if not server:
        return None, 'server is empty: it must be the trade server of the account, as MetaTrader 5 shows it'
    path = block.get('terminal_path')
    path = '' if path is None or isinstance(path, bool) else str(path).strip()
    if not path:
        return None, ('terminal_path is empty: it must be the full path of the terminal64.exe of the MetaTrader 5 '
                      'this account is logged into')
    return dict(block, login_id=login, server=server, terminal_path=path), None


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
    
    def __init__(self, mode=_MODE, target_symbol=None):
        """
        Initialize the trading bot
        
        Args:
            mode (str): 'live', the only mode of this branch: the word the process was started with. It selects
                        nothing: whatever it is, the bot trades only the real, hedging account of its credentials
                        (the "live" block); load_credentials and execute_job refuse to start with another word.
            target_symbol (str): If set, only process this single symbol.
                                 Recommended to avoid MT5 threading issues.
        """
        self.mode = str(mode).strip().lower()
        self.target_symbol = target_symbol.strip().upper() if target_symbol else None
        # The account this bot trades: the credentials block as normalised once (the `credentials` property below)
        # and, from it, the account number, its tail for every text and the trade server. All None until a usable
        # block is loaded: the bot then refuses every poll and every order (_account_problem), and never takes the
        # account it finds in the terminal as its own.
        self._credentials = None
        self._credentials_problem = None
        self._login = None
        self._login_tail = None
        self._server = None
        self.exit_code = EXIT_RETRY               # how the process ends (set by execute_job; main() exits with it)
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
        self._digits = {}                        # trade symbol -> price digits (the backstop is rounded to them)
        # Why the account the terminal showed last was refused (None = it is this bot's and may be traded).
        self._account_bad = None
        # What the terminal said last about its account and about itself, for the trace (read only, also on a
        # skipped poll): _acct = {login_tail, server, currency, leverage, trade_allowed, trade_expert, trade_mode,
        # margin_mode} (_account_problem), _terminal = {build, ping_ms, trade_allowed, tradeapi_disabled, connected}
        # (_terminal_problem). Never the full account number.
        self._acct = None
        self._terminal = None
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
        # (TERMINAL_IN_USE): for each event, each problem logged and when (_log_limited).
        self._limited_logged = {}
        # The dashboard's trace and the text log (tracelog.py), one per symbol, in trace_dir (None = OUTPUT_DIR).
        # Nothing the bot decides reads them; every call into them is wrapped (_trace), trace_enabled False = none.
        self.trace_dir = None
        self.trace_enabled = True
        self._tracers = {}
        self._boot_lines = []                    # lines logged before a symbol's trace exists (job start, login)
        self._guard_why = None                   # why the last poll guard refused: ('terminal' | 'account', problem)
        self._reconnects_done = 0
        # The start. _cred_stat: (st_mtime_ns, st_size) of the credentials file as this process loaded it (the
        # login budget tells a corrected file by it). _owner_verdict: this start attempt ended on something only
        # the owner can change -- (key, the line that says what to change) -- else None; _owner_said: the line
        # already printed in full. _process_locks: the lock files this process holds (one process per branch).
        self._cred_stat = None
        self._owner_verdict = None
        self._owner_said = None
        self._process_locks = {}
        # An old bot on this server (_old_bot_alive: looked at every _OLD_BOT_CHECK_S, kept as a flag the start and
        # the poll loop read): how old its newest file is (None = no such file), and when that was last looked at.
        self._old_bot_alive_flag = False
        self._old_bot_age_s = None
        self._old_bot_checked_at = None
        # Why MetaTrader 5 lets no program trade right now (the reasons of _TRADING_NOT_ALLOWED), [] = it does.
        self._trade_blocked = []
        # When this bot first traded this account (state/live_start.json): the record, None until it is known;
        # a history read or a write of it that failed is tried again from _live_start_retry_at.
        self._live_start = None
        self._live_start_retry_at = 0.0
        # The auto-safety (safety.py) in the poll loop. _tracker: this bot's Tracker (None until it could be
        # built; tried again after every poll), _tracker_ok: its last load() succeeded; _cash_next: the account's
        # balance operations read at the end of the last poll, for the next one ((list, time of the read), or
        # (None, None)); _safety_view: the view the last poll decided on; _switch_seen: the switch as this
        # process read it last (only for a poll without a usable Tracker).
        self._tracker = None
        self._tracker_ok = False
        self._cash_next = (None, None)
        self._safety_view = None
        self._switch_seen = None
        # The one flag every opening order of a poll is tested against -- by the four tests before a send and,
        # last, by open_guard in buy() / sell(): None = opens allowed, else {'why', 'until', 'refusals'}. Set
        # before each poll's decision; a close never reads it.
        self._opens_stop = None
        # Refused opening orders (the slower retry; the refusal events): None, or the streak -- {'first' (the
        # first refusal by the broker, None while only unanswered ones), 'count' (broker refusals), 'last_try',
        # 'wanted' (an open was last wanted), 'n' (every open that did not fill), 'logged_at', 'unlogged'}. In
        # memory only: a restart starts afresh.
        self._refusal = None
        # Closed trades waiting for their result (the losing-trades rule), and the position ids of the Turtle's
        # running trade: state/safety_closes.json, written after the orders when changed.
        self._closes = {'turtle': None, 'queue': []}
        self._closes_dirty = False
        # The steps after the orders: not before this time after a failure (5 s), and when each was last said.
        self._step_retry = {}
        self._step_said = {}
        # What the warnings of the loop said last (an event and a console line when it starts or changes).
        self._said = {}
        self._events_due = []           # events decided in the order section, logged after it

    # ───────────────────── the credentials: normalised once, wherever they come from ─────────────────────
    @property
    def credentials(self):
        """The credentials block this bot runs on, as usable_credentials() keeps it (login_id a whole number, server
        and terminal_path without spaces around them); None while none is loaded or the block given cannot be used.
        Read-only: the account is changed by giving the bot a new block, never by editing this one in place (the
        account number the checks compare with would not follow)."""
        return self._credentials

    @credentials.setter
    def credentials(self, block):
        """Whoever gives the bot its credentials -- load_credentials (the "live" block of the file), a replay, a
        test -- they pass the one normalisation here, so the account is compared the same way everywhere
        (_same_account). A block that cannot be used leaves the bot without an account: it then trades nothing."""
        creds, problem = (None, None) if block is None else usable_credentials(block)
        self._credentials = types.MappingProxyType(creds) if creds else None
        self._credentials_problem = problem
        self._login = creds['login_id'] if creds else None
        self._login_tail = safety.mask_login(self._login) if creds else None
        self._server = creds['server'] if creds else None

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

    def _boot_flush(self, held_back=False):
        """The job ends before any symbol's loop started: its lines go to the log of the symbol it was started for --
        unless held_back: each of its 3 start attempts was refused on a problem _log_limited held back this time
        (TERMINAL_IN_USE: logged at most every _LOG_REPEAT_S): the launcher starts a refused bot
        again every 30 s, and its start-up lines come with the refusal's own line, not at every restart. A start with
        any other failure (a failed login, an exception, Ctrl+C) is always written."""
        if self._boot_lines and not self._tracers:
            if held_back:
                return
            self._tracer(self.symbols[0] if self.symbols else self._symbol_spelling(self.target_symbol))

    def _start_held_back(self):
        """True when this start attempt (execute_job: right after it, with _init_problem reset before it) was refused
        on a problem that _log_limited did not log this time (it is in _limited_logged with the time of its last
        entry). Read only."""
        try:
            problem = self._init_problem
            return bool(problem) and any(problem in seen for seen in (self._limited_logged or {}).values())
        except Exception:
            return False

    def _symbol_spelling(self, name):
        """The symbol as symbols.json spells it ('XAUUSDm' for --symbol xauusdm), else name ('bot' for none): the
        text log's file name then matches the one the running bot writes (Windows keeps the case of the first)."""
        if not name:
            return 'bot'
        try:
            with open(Path(__file__).parent / 'symbols.json', 'r', encoding='utf-8-sig') as f:
                cfg = json.load(f)
            for item in cfg.get('symbols', []):
                sym = item.get('symbol') if isinstance(item, dict) else None
                if isinstance(sym, str) and sym.upper() == str(name).upper():
                    return sym
        except Exception:
            pass
        return name

    def _order_observed(self, request, result, refused=False, ms=None, quote=None):
        """MT5PositionHelper._send / _open: every order request and its result, to the trace of its symbol (inside
        mt5_lock). refused: True = the account guard stopped it, 'safety' = open_guard did; quote: the tick the
        request was built from ({'bid', 'ask', 't_msc'})."""
        self._trace(self._symbol_of((request or {}).get('symbol')), 'order', request, result, refused, ms, quote)

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
        
    # ───────────────────── the start: what only the owner can put right ─────────────────────
    def _needs_owner(self, key, line):
        """This start attempt ended on something only the owner can change: `line` says what, in one sentence a
        trader can act on; `key` names the cause (and what it found), so that execute_job can tell whether its
        start attempts all gave the same answer. Only then does the process end with EXIT_NEEDS_OWNER: a file a
        pull is rewriting this moment, or a terminal that has not filled in its account yet, gives another answer
        five seconds later, and a bot that holds trades must come back by itself. The line is printed and logged
        in full the first time; execute_job prints it once more as its last word."""
        self._owner_verdict = (str(key), str(line))
        if not self._init_problem:
            self._init_problem = str(line)
        if self._owner_said == self._owner_verdict:
            print('✗ The same answer as the attempt before (the line above says what to change).')
            return
        self._owner_said = self._owner_verdict
        print(f'✗ {line}')
        self._boot('ERROR', 'START', str(line), {'needs_owner': str(key)})

    @staticmethod
    def _branch_folder():
        """The folder of this branch on the server: where app.py, mt5_credentials.json and symbols.json are."""
        return Path(__file__).resolve().parent

    @staticmethod
    def _file_stat(path):
        """(st_mtime_ns, st_size) of a file, None when it cannot be asked. Never raises, never opens the file."""
        try:
            st = os.stat(path)
            return (int(st.st_mtime_ns), int(st.st_size))
        except Exception:
            return None

    def _old_account_problem(self, block=None):
        """Why the account of the loaded credentials -- or of `block`, a "live" block as the file holds it, before
        anything else of it is judged -- may not be traded by this branch (None = it may): it is one of the accounts
        the old bots traded (OLD_LOGINS_SHA256) and the block does not say "keep_old_account": true.
        The branches are pushed with the old accounts' details, and the MetaTrader 5 every one of those files
        names is logged into exactly that account today: untouched credentials would pass every later check on the
        wrong account. Whatever else of the block was edited or left out -- the password, the server, the path, an
        added key, the number typed as text -- the account number decides. A block whose login_id is no account
        number at all is not judged here (it cannot be used, which is another refusal)."""
        if block is None:
            creds, login = self._credentials, self._login
            if creds is None:
                return None
        else:
            creds = block if hasattr(block, 'get') else None
            login = _login_number(creds.get('login_id')) if creds is not None else None
            if login is None:
                return None
        old = OLD_LOGINS_SHA256
        if not isinstance(old, (tuple, list, set, frozenset)):
            return 'OLD_LOGINS_SHA256 of constants.py cannot be used: this branch was not finished by the generator'
        if creds.get('keep_old_account') is True:       # (exactly the JSON value true: not "true", not 1)
            return None
        if safety.login_sha(login) not in old:
            return None
        tail = safety.mask_login(login)
        return (f'mt5_credentials.json in {self._branch_folder()} still names the old account ({tail}) '
                f"this branch was created with. Put the new account's login_id, login_pass and server in its "
                f'"{_MODE}" block (and terminal_path, if this account has its own MetaTrader 5), the same values in '
                f'{BRANCH} and {PARTNER_BRANCH}, pull the change on this server and start again. Only if this '
                f'branch must really trade that old account: add "keep_old_account": true to the "{_MODE}" block, '
                f'and make sure the old bot of that account is stopped.')

    def load_credentials(self):
        """Step 1: Load MT5 credentials from JSON file: its "live" block, normalised once (the `credentials`
        property). Another mode word is refused before the file is opened. Nothing of the file's content is ever
        printed or logged: every failure has a fixed text (an account number as its tail only).
        A file that is missing, is not valid JSON or UTF-8, has no usable "live" block, still names the old
        account, or whose terminal_path is no file on this server is something only the owner can change
        (_needs_owner); a file that cannot be opened or read this moment (a pull is rewriting it, no permission)
        is a start attempt that failed and is tried again."""
        if self.mode != _MODE:
            print(f"✗ {_wrong_mode_text()}")
            self._boot('ERROR', 'START', f"mode '{self.mode}' refused. {_wrong_mode_text()}")
            return False
        self.credentials = None             # a load that fails leaves the bot without an account, not with an older one
        self._cred_stat = None
        json_path = Path(__file__).parent / 'mt5_credentials.json'
        folder = self._branch_folder()
        fix = (f'Correct it on GitHub (the same in {BRANCH} and {PARTNER_BRANCH}), pull the change on this server '
               f'and start again.')
        stat = self._file_stat(json_path)   # (before the read: a file changed while it is read counts as changed)
        try:
            with open(json_path, 'r', encoding='utf-8-sig') as f:
                credentials = json.load(f)
        except FileNotFoundError:
            self._needs_owner('CREDENTIALS_MISSING',
                              f'mt5_credentials.json is missing in {folder}. Put it back (in that folder: git '
                              f'checkout -- mt5_credentials.json, then git pull) and start again.')
            return False
        except json.JSONDecodeError as e:
            # (the place of the fault, never the text around it: the file holds a password)
            where = f'line {e.lineno}, column {e.colno}'
            self._needs_owner(f'CREDENTIALS_NOT_JSON {where}',
                              f'mt5_credentials.json in {folder} is not valid JSON ({where}): a quote, a comma or '
                              f'a doubled backslash is wrong there. {fix}')
            return False
        except UnicodeError:
            # (Notepad's ANSI or PowerShell's UTF-16): the error's repr would hold the file's bytes, so a fixed text
            self._needs_owner('CREDENTIALS_NOT_UTF8',
                              f'mt5_credentials.json in {folder} is not UTF-8 text: save it as UTF-8 (Notepad: Save '
                              f'as, Encoding UTF-8). {fix}')
            return False
        except Exception as e:
            # Held by another program this moment (a pull rewriting it), no permission, a disk error: nothing the
            # file's text can be blamed for, so it is tried again -- never "needs the owner".
            print(f"✗ Error: mt5_credentials.json could not be read this time ({type(e).__name__}); trying again")
            self._boot('ERROR', 'START', f'mt5_credentials.json could not be read this time ({type(e).__name__}): '
                       'the start is tried again')
            return False

        if not isinstance(credentials, dict) or _MODE not in credentials:
            self._needs_owner('CREDENTIALS_NO_BLOCK',
                              f'mt5_credentials.json in {folder} has no "{_MODE}" block. It needs one with '
                              f'terminal_path, login_id, login_pass and server. {fix}')
            return False
        block = credentials[_MODE]
        # The account first: before the rest of the block is judged, before any terminal call and before the path.
        # At the very first start on a server the owner must meet this line, whatever else the block holds and
        # whatever MetaTrader 5 is installed there (on a test PC none is) ...
        problem = self._old_account_problem(block)
        if problem:
            self._credentials_problem = (f'it still names the old account '
                                         f"{safety.mask_login(_login_number(block.get('login_id')))}")
            self._needs_owner('OLD_ACCOUNT', problem)
            return False
        # ... then the rest of the block, as the one normalisation keeps it ...
        creds, problem = usable_credentials(block)
        if creds is None:
            self._credentials_problem = problem
            self._needs_owner(f'CREDENTIALS_BLOCK {problem}',
                              f'The "{_MODE}" block of mt5_credentials.json in {folder} cannot be used: {problem}. '
                              f'{fix}')
            return False
        self.credentials = creds
        # ... then the MetaTrader 5 it names (its value is not shown: a password typed on the wrong line must not
        # reach a log)
        if not _terminal_file_exists(creds['terminal_path']):
            self.credentials = None
            self._credentials_problem = 'terminal_path does not name a file on this server'
            self._needs_owner('TERMINAL_PATH_NOT_A_FILE',
                              f'terminal_path in the "{_MODE}" block of mt5_credentials.json in {folder} does not '
                              f"name a file on this server. It must be the full path of the terminal64.exe of this "
                              f"account's MetaTrader 5, every backslash written twice. {fix}")
            return False
        self._cred_stat = stat
        print(f"✓ Credentials loaded: this bot's account {self._login_tail} on {self._server}")
        self._boot('INFO', 'START', f"credentials loaded: this bot's account {self._login_tail} on {self._server}")
        return True

    def load_symbols(self):
        """Step 2: Load symbols configuration from JSON file. A file that is missing, is not valid JSON, holds no
        active symbol or not the one this bot was started for, or whose step_up_balance / unit_max_limit cannot
        size a trade is something only the owner can change (_needs_owner); a file that cannot be read this
        moment is a start attempt that failed and is tried again."""
        json_path = Path(__file__).parent / 'symbols.json'
        folder = self._branch_folder()
        fix = 'Correct it on GitHub, pull the change on this server and start again.'
        try:
            with open(json_path, 'r', encoding='utf-8-sig') as f:
                config = json.load(f)
        except FileNotFoundError:
            self._needs_owner('SYMBOLS_MISSING',
                              f'symbols.json is missing in {folder}. Put it back (in that folder: git checkout -- '
                              f'symbols.json, then git pull) and start again.')
            return False
        except json.JSONDecodeError as e:
            where = f'line {e.lineno}, column {e.colno}'
            self._needs_owner(f'SYMBOLS_NOT_JSON {where}',
                              f'symbols.json in {folder} is not valid JSON ({where}): a quote, a comma or a bracket '
                              f'is wrong there. {fix}')
            return False
        except UnicodeError:
            self._needs_owner('SYMBOLS_NOT_UTF8',
                              f'symbols.json in {folder} is not UTF-8 text: save it as UTF-8 (Notepad: Save as, '
                              f'Encoding UTF-8). {fix}')
            return False
        except Exception as e:
            print(f"✗ Error: symbols.json could not be read this time ({type(e).__name__}); trying again")
            self._boot('ERROR', 'START', f'symbols.json could not be read this time ({_err_text(e)}): the start is '
                       'tried again')
            return False

        sym_list = config.get('symbols') if isinstance(config, dict) else None
        if not isinstance(sym_list, list):
            sym_list = []
        self.symbols_config = config if isinstance(config, dict) else None

        # Build per-symbol config lookup from the array (only active symbols)
        self.symbols = []
        self.symbol_configs = {}
        skipped = []
        for entry in sym_list:
            name = entry.get('symbol', '') if isinstance(entry, dict) else ''
            if not name or not isinstance(name, str):
                continue
            if not entry.get('is_active', True):
                skipped.append(name)
                continue
            self.symbols.append(name)
            self.symbol_configs[name] = entry

        if skipped:
            print(f"⊘ Skipped inactive symbols: {', '.join(skipped)}")

        if not self.symbols:
            self._needs_owner('SYMBOLS_NONE_ACTIVE',
                              f'symbols.json in {folder} holds no active symbol: its "symbols" list needs the '
                              f'entry of this bot\'s symbol with "is_active": true. {fix}')
            return False

        # ── Single-symbol mode: filter to target_symbol only ──
        if self.target_symbol:
            # Match case-insensitively against configured symbol names
            matched = [s for s in self.symbols if s.upper() == self.target_symbol]
            if not matched:
                active = ', '.join(self.symbols)
                self._needs_owner(f'SYMBOLS_NOT_THIS {self.target_symbol}',
                                  f'symbols.json in {folder} does not hold the symbol {self.target_symbol} this '
                                  f'bot was started for (active in it: {active}). {fix}')
                return False
            self.symbols = matched
            self.symbol_configs = {s: self.symbol_configs[s] for s in matched}
            print(f"⚡ Single-symbol mode: {matched[0]}")

        # What sizes every trade: the balance step of one more unit, and the most units a trade may have
        for name in self.symbols:
            step = self.symbol_configs[name].get('step_up_balance')
            if not _is_number(step) or step <= 0:
                self._needs_owner(f'SYMBOLS_STEP {name}',
                                  f'symbols.json in {folder}: "step_up_balance" of {name} must be a number above 0 '
                                  f'(the balance step of one more unit), not {step!r}. {fix}')
                return False
            cap = self.symbol_configs[name].get('unit_max_limit')
            if not _is_int(cap) or cap < 1:
                self._needs_owner(f'SYMBOLS_UNIT_MAX {name}',
                                  f'symbols.json in {folder}: "unit_max_limit" of {name} must be a whole number of '
                                  f'1 or more (the most units of one trade), not {cap!r}. {fix}')
                return False

        print(f"✓ Loaded {len(self.symbols)} symbols: {', '.join(self.symbols)}")
        return True

    @contextmanager
    def _terminal_calls(self, reconnect):
        """The terminal calls of initialize_mt5. On a reconnect they are made inside mt5_lock, as every terminal
        call of a running bot is; at the start no poll runs yet and nothing else uses the terminal. Between them
        the lock is free: the small files of the start (the claims, the login budget) and the strategy log are
        read and written outside it, never inside."""
        if reconnect:
            with self.mt5_lock:
                yield
        else:
            yield

    def _detach(self, reconnect):
        """mt5.shutdown(): the bot lets go of the terminal; the terminal and its account are left as they are."""
        with self._terminal_calls(reconnect):
            try:
                mt5.shutdown()
            except Exception:
                pass

    def initialize_mt5(self, reconnect=False):
        """Step 3: Initialize and login to MT5 -- at the start (reconnect False) and again when a running bot has
        lost the terminal (_reconnect). In this order:
          1. Before any terminal call: a bot without usable credentials, or whose credentials still name an old
             account, attaches to nothing (with an empty terminal_path mt5.initialize() would pick a MetaTrader 5
             itself). At the start only: an old bot alive on the same MetaTrader 5 -> the bot does not attach.
          2. mt5.initialize(path=terminal_path), never with credentials, and the account the terminal holds
             (_account_held: read again about once a second for _ACCOUNT_GRACE_S while it shows none).
          3. It holds this bot's account (_same_account: the number and the server) -> used as it is, no login. It
             holds another account -> left alone, never a login (TERMINAL_IN_USE; the same number on another
             server: SERVER_MISMATCH). The account is not known (an IPC error) -> no login, tried again.
          4. It shows no account -> the bot logs in only when its rules allow it (_own_login: no old bot alive on
             this MetaTrader 5 when it is the old bots', a password in the file, no other account's claim on this
             MetaTrader 5, the login budget).
          5. The account checks: the account of the credentials, a real account, a hedging account, kept in US
             dollars. At the start only: the account folder must belong to this account (_account_claim_ok).
          6. The MetaTrader 5 is noted as this account's and the login budget is cleared (_note_attached); a
             MetaTrader 5 that lets no program trade is a warning, never a refusal (_check_trading_allowed).
        What only the owner can change is marked as such at the start alone (_needs_owner); a reconnect never
        ends the process: it fails, is logged (RECONNECT_FAILED) and is tried again with the back-off."""
        print(f"\n{'='*60}")
        print(f"  Initializing MT5 - {self.mode.upper()} Account")
        print(f"{'='*60}\n")

        # ── 1. before any terminal call ──
        # No usable credentials (so no terminal_path either), or still the old account: refused before
        # mt5.initialize() could attach to anything
        problem = self._no_credentials_problem() or self._old_account_problem()
        if problem:
            self._init_problem = problem
            print(f"✗ Refused before attaching to any terminal: {problem}")
            self._boot('ERROR', 'START', f'refused before attaching to any terminal: {problem}')
            return False
        path = self.credentials['terminal_path']
        # An old bot that still runs on this MetaTrader 5 trades whatever account it is logged into and takes
        # every position of its symbol for its own: a bot that is only starting does not start beside it. (A
        # running bot that reconnects must get back to its trades: the poll loop then opens nothing new. Neither of
        # them ever logs this MetaTrader 5 in while such an old bot is alive: _login_refusal.)
        old_bot = not reconnect and self._old_bot_alive(force=True)
        if old_bot and _old_bots_terminal(path):
            problem = f'OLD_BOT_SAME_TERMINAL: {_OLD_BOT_TEXT}'
            self._init_problem = problem
            print(f"✗ Not attaching: {_OLD_BOT_TEXT}")
            self._log_limited('OLD_BOT_SAME_TERMINAL', problem, {
                'terminal_path': path, 'old_bot_age_s': self._old_bot_age_s, 'own_login_tail': self._login_tail})
            return False
        if old_bot:
            # (another MetaTrader 5: no reason not to start -- but the owner hears of it in this window at the start;
            # the poll loop keeps the flag for the trace's amber banner)
            print(f"⚠ {_old_bot_elsewhere_text(self._login_tail)}")
            self._said['old_bot_printed'] = 'other'     # (the loop's first poll then logs it without a second print)
            self._boot('WARN', 'START', _old_bot_elsewhere_text(self._login_tail),
                       {'old_bot_age_s': self._old_bot_age_s})

        # ── 2. attach, and the account the terminal holds before any login ──
        # A login switches the account of EVERY process attached to the terminal (the bots of another account, an
        # old bot), so this bot logs in only on a terminal that shows no account for the whole grace period, and
        # never on one that holds another account (_account_held).
        held = unknown = mismatch = None
        with self._terminal_calls(reconnect):
            if not mt5.initialize(path=path):
                error = mt5.last_error()
                self._init_problem = f'initialize failed: {error}'
                print(f"✗ MT5 initialization failed: {error}. MetaTrader 5 at {path} did not answer: if this lasts, "
                      f"open that MetaTrader 5 by hand and check that it starts and logs in. The bot tries again by "
                      f"itself.")
                self._boot('ERROR', 'TERMINAL', f'MT5 initialize failed: {self._init_problem}')
                return False
            print(f"✓ MT5 initialized successfully")
            print(f"✓ MT5 version: {mt5.version()}")
            self._boot('INFO', 'TERMINAL', 'MT5 initialized', {'version': mt5.version()})
            held, unknown = self._account_held()
            if held is not None:
                self._note_account(held)        # (the trace's account facts, also when the start is refused on it)
                if not self._same_account(held) and self._same_login(held):
                    mismatch = self._server_mismatch(held, confirm=not reconnect)
            if unknown is not None or (held is not None and not self._same_account(held)):
                try:
                    mt5.shutdown()              # detach; the terminal and its account are left as they are
                except Exception:
                    pass

        # ── 3. an account that is not known, or not this bot's: no login, the terminal is left alone ──
        if unknown is not None:
            self._init_problem = unknown
            print(f"✗ Not logging in: {unknown}; detached, trying again later")
            self._boot('WARN', 'ACCOUNT', f'no login: {unknown}; the bot detached and tries again later (the terminal and '
                       'its account are left as they are)')
            return False
        if mismatch is not None:
            text, confirmed = mismatch
            problem = f'SERVER_MISMATCH: {text}'
            self._init_problem = problem
            if confirmed:                   # (at the start only: its line is printed there)
                self._needs_owner(f"SERVER_MISMATCH {getattr(held, 'server', None)}", text)
            else:
                print(f"✗ Refused: {text}")
            self._log_limited('SERVER_MISMATCH', problem, {
                'terminal_path': path, 'login_tail': safety.mask_login(getattr(held, 'login', None)),
                'server': getattr(held, 'server', None), 'own_login_tail': self._login_tail,
                'own_server': self._server})
            return False
        if held is not None and not self._same_account(held):
            problem = self._terminal_in_use_problem(held)
            self._init_problem = problem
            print(f"✗ Refused: {problem}")
            self._terminal_in_use(problem, held)
            return False

        # ── 4. no account for the whole grace period: the bot's own login, when its rules allow one ──
        if held is None:
            if not self._own_login(path, reconnect):
                return False
        else:
            print(f"✓ The terminal already holds this bot's account {self._login_tail} ({held.server}): no login")
            self._boot('INFO', 'ACCOUNT', f"no login: the terminal already holds this bot's account "
                       f"{self._login_tail} ({held.server})", {'login_tail': self._login_tail, 'server': held.server})

        # ── 5. the account checks ──
        # Only ever this bot's account: the login and the server of the credentials (not an account another
        # program switched the terminal to in the meantime), a real account, a hedging account, kept in US dollars
        kind = problem = None
        confirmed = False
        with self._terminal_calls(reconnect):
            account_info = mt5.account_info()
            if account_info is not None:
                kind, problem = self._account_check(account_info, with_currency=True)
                if kind in self._OWNER_KINDS and not reconnect:
                    confirmed = self._kind_confirmed(kind)
            if account_info is None or kind is not None:
                try:
                    mt5.shutdown()
                except Exception:
                    pass
            else:
                try:                        # (what MetaTrader 5 says about trading by programs: for the warning)
                    info = mt5.terminal_info()
                    if info is not None:
                        self._note_terminal(info)
                except Exception:
                    pass
        if account_info is None:
            self._init_problem = 'no account info'
            print("✗ Failed to get account info")
            self._boot('ERROR', 'ACCOUNT', 'logged in, but account_info() returned None')
            return False
        if kind is not None:
            self._init_problem = problem
            if not confirmed:
                print(f"✗ Refused: {problem}")
            self._boot('ERROR', 'ACCOUNT', f'refused, not trading: {problem}', {
                'login_tail': safety.mask_login(getattr(account_info, 'login', None)),
                'trade_mode': getattr(account_info, 'trade_mode', None),
                'margin_mode': getattr(account_info, 'margin_mode', None),
                'currency': getattr(account_info, 'currency', None)})
            if confirmed:                   # (at the start only: its line is printed there)
                self._needs_owner(f'ACCOUNT_KIND {kind}', self._owner_kind_text(kind, problem))
            return False
        # At the start: the account folder must belong to this account, and to no other folder on this server
        if not reconnect and not self._account_claim_ok():
            self._detach(reconnect)
            return False

        # ── 6. this bot's account: the MetaTrader 5 is noted as its own, the login budget is cleared ──
        self._note_attached(path)
        self._init_problem = None
        self._limited_logged = {}
        self._boot('INFO', 'ACCOUNT', f"{'logged in: ' if held is None else ''}account {self._login_tail} on "
                   f'{account_info.server}; checks passed (the account of the credentials, a real account, a hedging '
                   'account, kept in US dollars)', {
                       'login_tail': self._login_tail, 'server': account_info.server,
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

        with self._terminal_calls(reconnect):
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

        # A MetaTrader 5 that lets no program trade: a warning the owner must see at once, never a refusal
        self._check_trading_allowed()
        return True

    # ───────────────────── the start: the account the terminal holds, and the bot's own login ─────────────────────
    def _same_login(self, acct):
        """True when `acct` has the account NUMBER of this bot's credentials (whatever its server)."""
        try:
            return bool(self._login) and int(getattr(acct, 'login', None)) == self._login
        except (TypeError, ValueError):
            return False

    def _server_mismatch(self, held, confirm):
        """The terminal holds this bot's account number on another server than the credentials name: (the line for
        the owner, confirmed). In practice the "server" of the file was not changed with the account. Confirmed --
        only the owner can change it -- when the terminal is connected to its trade server and a second read
        _RECHECK_S later shows the same number on the same other server: a terminal that has just started may not
        have filled in its account yet. (Terminal calls: made inside the caller's window.)"""
        server = getattr(held, 'server', None)
        text = (f"MetaTrader 5 is logged into account {safety.mask_login(getattr(held, 'login', None))} on "
                f"{server if server else 'a server it does not name'}, but mt5_credentials.json says {self._server}. "
                f'Correct "server" in the "{_MODE}" block and start again.')
        if not confirm or not str(server or '').strip():
            return text, False
        try:
            info = mt5.terminal_info()
            if info is None or getattr(info, 'connected', False) is not True:
                return text, False
            time.sleep(_RECHECK_S)
            again = mt5.account_info()
        except Exception:
            return text, False
        same = (again is not None and self._same_login(again) and not self._same_account(again)
                and str(getattr(again, 'server', '') or '').strip().casefold() == str(server).strip().casefold())
        return text, bool(same)

    _OWNER_KINDS = ('not_real', 'not_hedging', 'not_usd')      # what _account_check finds that only the owner can change

    def _kind_confirmed(self, kind):
        """An account of the wrong kind (`kind` of _account_check) is something only the owner can change when
        the terminal is connected to its trade server and a second read _RECHECK_S later says the same: 'real'
        and 'hedging' are both 2 and a field not filled in yet reads 0 -- one unsettled read after a reboot must
        not leave the bot down. (Terminal calls: made inside the caller's window; at the start only.)"""
        try:
            info = mt5.terminal_info()
            if info is None or getattr(info, 'connected', False) is not True:
                return False
            time.sleep(_RECHECK_S)
            again = mt5.account_info()
        except Exception:
            return False
        return again is not None and self._account_check(again, with_currency=True)[0] == kind

    def _owner_kind_text(self, kind, problem):
        """The line for the owner when the account of the credentials is of a kind this bot does not trade."""
        if kind == 'not_usd':
            return problem                  # (it says what to use)
        what = {'not_real': 'This branch trades real money only',
                'not_hedging': 'This bot needs a hedging account (it holds one position for each order)'}[kind]
        return (f'{problem[:1].upper()}{problem[1:]}. {what}: put the details of a real, hedging account kept in US '
                f'dollars in the "{_MODE}" block of mt5_credentials.json (the same in {BRANCH} and '
                f'{PARTNER_BRANCH}), pull the change and start again.')

    def _login_budget(self, now):
        """
        May the bot log in now, by the record of the last own login of either bot of the account
        (<account folder>/login_attempt.json: {at, failed, code, cred_mtime_ns, cred_size, by, files})?
        Returns {'allowed', 'failed' (own logins in a row that did not go through), 'files', and when not allowed
        'why', 'refused_at', 'next_at', 'code'}. Allowed when the file is missing; when the credentials file of
        THIS branch changed since this branch's own last login (`files`: each branch's file as it was then -- the
        other bot's file is another file, with another date, and says nothing about a new password); or when the
        wait of _LOGIN_WAITS_S for `failed` is over. A file that cannot be read this moment allows nothing; one
        that holds no usable record counts as the last of the waits, from the time it was written. Never raises.
        """
        path = os.path.join(_account_folder(), _LOGIN_ATTEMPT_FILE)
        status, rec = _read_json_file(path, tries=3)
        if status == 'missing':
            return {'allowed': True, 'failed': 0, 'files': {}}
        if status == 'unreadable':
            return {'allowed': False, 'why': 'budget_unreadable', 'failed': 0, 'files': {}}
        at = failed = code = None
        files = {}
        if status == 'ok' and isinstance(rec, dict):
            at = float(rec['at']) if _is_number(rec.get('at')) else None
            failed = rec['failed'] if _is_int(rec.get('failed')) and rec['failed'] >= 0 else None
            code = rec.get('code')
            files = {str(k): v for k, v in rec['files'].items()} if isinstance(rec.get('files'), dict) else {}
        if at is None or failed is None:
            stat = self._file_stat(path)
            at = stat[0] / 1e9 if stat else float(now)
            failed, files = len(_LOGIN_WAITS_S), {}
        mine = files.get(str(BRANCH))
        if (self._cred_stat is not None and isinstance(mine, (list, tuple))
                and tuple(mine) != tuple(self._cred_stat)):
            return {'allowed': True, 'failed': 0, 'files': files}
        wait = _login_wait_s(failed)
        if abs(float(now) - at) >= wait:        # (abs: a clock that was set back must not lock the login for good)
            return {'allowed': True, 'failed': failed, 'files': files}
        return {'allowed': False, 'why': 'login_budget', 'failed': failed, 'files': files, 'refused_at': at,
                'next_at': at + wait, 'code': code}

    def _login_record(self, now, budget, code=None):
        """The record of an own login made at `now` (login_attempt.json), written BEFORE the login: a login that
        never answers, or a process that dies in it, still counts."""
        from datetime import datetime
        stat = self._cred_stat
        files = dict(budget.get('files') or {})
        if stat is not None:
            files[str(BRANCH)] = [stat[0], stat[1]]
        return {'at': float(now), 'at_utc': datetime.fromtimestamp(float(now), tz=timezone.utc).isoformat(),
                'failed': int(budget.get('failed') or 0) + 1, 'code': code,
                'cred_mtime_ns': stat[0] if stat else None, 'cred_size': stat[1] if stat else None,
                'by': str(BRANCH), 'files': files}

    def _login_refusal(self, path, now):
        """Why the bot may not log this MetaTrader 5 in itself right now: None = it may (and the budget to write),
        else (why, the reason as the owner reads it, details). The rules, in this order: no old bot alive while this
        is the old bots' MetaTrader 5 (rule A of 6.2, here for every login, the start's and a reconnect's alike: a
        login switches the account of every program attached to the terminal, so the old ladder bot would then trade
        this account and add to or close this bot's trades; a terminal that already holds this bot's account is
        used without a login, so the bot still gets back to its open trades); a password in the file that is one;
        no claim of another account on this MetaTrader 5 (terminal_claims: the account whose bots last passed the
        account checks here -- a login would switch that account's bots off); the login budget. File reads only,
        outside mt5_lock; never raises."""
        try:
            old_bot = self._old_bot_alive(force=True) and _old_bots_terminal(path)
        except Exception:
            old_bot = False
        if old_bot:
            return ('old_bot', _OLD_BOT_TEXT, {'old_bot_age_s': self._old_bot_age_s}), None
        if not _password_usable(self.credentials.get('login_pass')):
            return ('no_password', 'mt5_credentials.json holds no password for it', {}), None
        status, claim = _read_json_file(_terminal_claim_path(path), tries=3)
        if status != 'missing':
            sha = claim.get('login_sha') if status == 'ok' and isinstance(claim, dict) else None
            if not isinstance(sha, str) or not sha:
                return ('claim_unreadable', 'the file that says which account this MetaTrader 5 belongs to cannot '
                        'be read right now', {}), None
            if sha != safety.login_sha(self._login):
                n, tail = claim.get('account'), claim.get('login_tail')
                whose = f'account {n}' if _is_int(n) else 'another account'
                return ('terminal_claimed', f'this MetaTrader 5 belongs to {whose}'
                        + (f' ({tail})' if isinstance(tail, str) and tail else ''),
                        {'claimed_by_account': n if _is_int(n) else None,
                         'claimed_by_branch': claim.get('branch'), 'claimed_login_tail': tail}), None
        budget = self._login_budget(now)
        if budget['allowed']:
            return None, budget
        if budget.get('why') == 'budget_unreadable':
            return ('budget_unreadable', "the record of the bot's last own login cannot be read right now", {}), None
        at, nxt = budget.get('refused_at'), budget.get('next_at')
        how = 'was refused' if budget.get('code') is not None else 'did not go through'
        return ('login_budget', f"the bot's own login {how} at {_clock_text(at, now)} and it tries the password "
                f'again at {_clock_text(nxt, now)}',
                {'refused_at': at, 'next_login_at': nxt, 'failed': budget.get('failed'), 'code': budget.get('code')}), None

    def _own_login(self, path, reconnect):
        """
        The terminal showed no account for _ACCOUNT_GRACE_S. The bot calls mt5.login only when _login_refusal
        allows it, and writes the login budget BEFORE the call. Otherwise -- and after a login that did not go
        through, whatever its code -- the attempt fails with advice and the bot detaches: the launcher (or the
        reconnect back-off) keeps attaching, so a terminal that finishes logging into its saved account, or that
        the owner logs in by hand, is picked up at once. Never "needs the owner": after an unattended restart
        the bot must come back by itself. True when the terminal is logged in now.
        """
        now = time.time()
        own = {'terminal_path': path, 'own_login_tail': self._login_tail, 'server': self._server}
        refusal, budget = self._login_refusal(path, now)
        record = None
        if refusal is None:
            record = self._login_record(now, budget)
            try:
                _write_json_atomic(os.path.join(_account_folder(), _LOGIN_ATTEMPT_FILE), record)
            except Exception as e:          # no record, no login: without it nothing would bound the next ones
                refusal = ('budget_unwritable', f"the record of the bot's own logins cannot be written "
                           f'({_err_text(e)})', {})
        if refusal is not None:
            why, reason, details = refusal
            if why == 'old_bot':
                # (rule A's line and event: logging in by hand would hand the account to the old bot just the same)
                problem = f'OLD_BOT_SAME_TERMINAL: {_OLD_BOT_TEXT}'
                self._init_problem = problem
                print(f"✗ Not logging in: {_OLD_BOT_TEXT}")
                self._detach(reconnect)
                self._log_limited('OLD_BOT_SAME_TERMINAL', problem, {
                    'terminal_path': path, 'old_bot_age_s': self._old_bot_age_s, 'own_login_tail': self._login_tail})
                return False
            text = (f'MetaTrader 5 at {path} is not logged into any account. Log it into {self._login_tail} by hand '
                    f'(File > Login to Trade Account, Save password). The bot does not log in itself: {reason}. '
                    f'It looks again every 30 seconds.')
            problem = f'LOGIN_WAIT: {text}'
            self._init_problem = problem
            print(f"✗ Not logging in: {text}")
            self._detach(reconnect)
            self._log_limited('LOGIN_WAIT', problem, dict(details, why=why, **own))
            return False

        # Login to MT5 account (the terminal showed no account for _ACCOUNT_GRACE_S), with the account number
        # as normalised (a whole number: the terminal refuses text)
        print(f"… the terminal showed no account for {_ACCOUNT_GRACE_S:g} s: logging in")
        self._boot('WARN', 'ACCOUNT', f'the terminal showed no account for {_ACCOUNT_GRACE_S:g} s: the bot logs in '
                   f"itself (this bot's account {self._login_tail} on {self._server}). Log this MetaTrader 5 into "
                   'that account once by hand, with Save password: then the bot never has to',
                   {'login_tail': self._login_tail, 'server': self._server})
        error = None
        with self._terminal_calls(reconnect):
            authorized = mt5.login(
                login=self._login,
                password=self.credentials.get('login_pass'),
                server=self._server
            )
            if not authorized:
                error = self._last_error()
                try:
                    mt5.shutdown()
                except Exception:
                    pass
        if authorized:
            return True
        code = error[0] if isinstance(error, (tuple, list)) and error else None
        try:                                # (the code beside the record made before the login; best effort)
            _write_json_atomic(os.path.join(_account_folder(), _LOGIN_ATTEMPT_FILE),
                               dict(record, code=code if _is_int(code) else str(code)))
        except Exception:
            pass
        nxt = now + _login_wait_s(record['failed'])
        text = (f'The server refused account {self._login_tail} on {self._server}: check login_id, login_pass and '
                f'server. The bot tries the password again at {_clock_text(nxt, now)}; a MetaTrader 5 that is '
                f'logged in by hand is used at once.')
        problem = f'LOGIN_REFUSED: {text} (last_error {error})'
        self._init_problem = problem
        print(f"✗ Login failed: {error}. {text}")
        self._log_limited('LOGIN_REFUSED', problem, dict(own, last_error=str(error), failed=record['failed'],
                                                         next_login_at=nxt))
        return False

    # ───────────────────── the start: which account a folder and a MetaTrader 5 belong to ─────────────────────
    @staticmethod
    def _claim_account(claim):
        """(login_sha, server) of a claim file's content, (None, None) when it holds no usable account."""
        if not isinstance(claim, dict):
            return None, None
        sha = claim.get('login_sha')
        if not isinstance(sha, str) or not _SHA256_TEXT.fullmatch(sha):
            return None, None
        server = claim.get('server')
        return sha, (str(server).strip() if isinstance(server, str) and server.strip() else None)

    def _same_claim(self, claim):
        """True when a claim names this bot's account: its number (as SHA-256) and, where the claim has one, its
        server (letter case aside)."""
        sha, server = self._claim_account(claim)
        return (sha is not None and sha == safety.login_sha(self._login)
                and (server is None or server.casefold() == str(self._server).casefold()))

    def _claimed_elsewhere(self):
        """(account number or folder name, claim) of ANOTHER account's folder on this server (live*_account beside
        this bot's) whose claim names this bot's account; None when there is none. Reads only; never raises."""
        try:
            parent = _parent_folder()
            own = str(ACCOUNT_FOLDER).casefold()
            for name in sorted(os.listdir(parent)):
                if name.casefold() == own or not fnmatch.fnmatchcase(name.casefold(), 'live*_account'):
                    continue
                status, claim = _read_json_file(os.path.join(parent, name, safety.CLAIM_FILE))
                if status == 'ok' and self._same_claim(claim):
                    n = claim.get('account')
                    if not _is_int(n):
                        m = re.fullmatch(r'live(\d+)_account', name.casefold())
                        n = int(m.group(1)) if m else None
                    return (f'account {n}' if n is not None else f'the folder {name}'), claim
        except Exception:
            pass
        return None

    def _account_claim_ok(self):
        """
        At the start, after the account checks: the account folder belongs to ONE account
        (<account folder>/account_claim.json: {login_sha, login_tail, server, set_at, by}, made by the first bot of
        the account that passes the account checks, and never rewritten). True = this bot's account is the
        folder's (the claim is made when there is none). False = the start attempt fails:
          * the claim names another account -- the two branches of the account hold different credentials, or
            the block of another account was pasted in -- or another account's folder on this server names this
            one: only the owner can change that (_needs_owner);
          * the claim cannot be read this moment: tried again.
        A claim that holds no usable account (a damaged file) is put aside and made anew; a claim that cannot be
        made (the folder cannot be written) is a warning: the bot goes on, the next start tries again.
        File reads and writes only, outside mt5_lock.
        """
        from datetime import datetime
        folder = _account_folder()
        path = os.path.join(folder, safety.CLAIM_FILE)
        name = _account_name()
        # another account's folder on this server that names this account: this bot's credentials are another
        # account's (before a claim is made here: a wrong account must not become this folder's)
        other = self._claimed_elsewhere()
        if other is not None:
            whose, _claim = other
            self._needs_owner(f'ACCOUNT_CLAIMED_ELSEWHERE {whose}',
                              f'Account {self._login_tail} is already traded by the bots of {whose} on this '
                              f'server. {BRANCH} belongs to {name}: put the details of its own account in '
                              f'mt5_credentials.json (the same in {BRANCH} and {PARTNER_BRANCH}), pull the change '
                              f'and start again.')
            return False
        now = time.time()
        mine = {'login_sha': safety.login_sha(self._login), 'login_tail': self._login_tail, 'server': self._server,
                'set_at': datetime.fromtimestamp(now, tz=timezone.utc).isoformat(), 'set_t': now,
                'by': str(BRANCH), 'account': ACCOUNT_SLOT}
        for _ in range(3):
            status, claim = _read_json_file(path, tries=3)
            if status == 'unreadable':
                self._init_problem = f'the file {path} cannot be read this moment ({claim}): the start is tried again'
                print(f"✗ {self._init_problem}")
                self._boot('ERROR', 'START', self._init_problem)
                return False
            if status in ('ok', 'invalid') and self._claim_account(claim)[0] is None:
                # not a claim (a damaged file): put aside, and the first bot that starts makes it anew
                aside = f'{path}.not-readable-{_name_stamp(now)}'
                try:
                    _replace_retry(path, aside)
                except Exception as e:
                    self._init_problem = (f'the file {path} holds no account and could not be put aside '
                                          f'({_err_text(e)}): the start is tried again')
                    print(f"✗ {self._init_problem}")
                    self._boot('ERROR', 'START', self._init_problem)
                    return False
                print(f"⚠ {path} held no account: put aside as {os.path.basename(aside)} and made anew")
                self._boot('WARN', 'START', f'{path} held no account: put aside as {os.path.basename(aside)} and '
                           'made anew')
                status = 'missing'
            if status == 'missing':
                try:
                    if _create_json_exclusive(path, mine):
                        print(f"✓ {name}'s folder {folder} now belongs to account {self._login_tail}")
                        self._boot('INFO', 'START', f"{name}'s folder {folder} now belongs to account "
                                   f'{self._login_tail} on {self._server} (set by {BRANCH})')
                        return True
                except Exception as e:
                    print(f"⚠ Could not write {path} ({_err_text(e)}): the bot goes on; the next start tries again")
                    self._boot('WARN', 'START', f'could not write {path} ({_err_text(e)}): the bot goes on without '
                               'it; the next start tries again')
                    return True
                continue                    # the other bot of the account made it this instant: read it
            if self._same_claim(claim):
                return True
            tail = claim.get('login_tail') if isinstance(claim.get('login_tail'), str) else '...?'
            try:
                day = datetime.fromtimestamp(float(claim.get('set_t')), tz=timezone.utc)
                day = f"{day.day} {day.strftime('%b %Y')}"
            except (TypeError, ValueError, OverflowError, OSError):
                day = 'on a day it does not name'
            own_text, its_text = self._login_tail, tail
            if tail == self._login_tail:    # the same number on another server: say the servers too
                own_text, its_text = f'{own_text} on {self._server}', f"{tail} on {claim.get('server')}"
            by = claim.get('by') if isinstance(claim.get('by'), str) and claim.get('by') else 'the other bot'
            # (the key goes into the log: the account as its tail, never its fingerprint)
            self._needs_owner(f"ACCOUNT_CLAIM {its_text}",
                              f"{BRANCH} is set to account {own_text}, but {name}'s folder belongs to {its_text} "
                              f"(set {day} by {by}). Both bots of an account use one account: correct "
                              f'mt5_credentials.json. If {name} really moves to a new account: stop both bots, run '
                              f'"safety.bat new-account", start again.')
            return False
        # (made and gone again three times in a row: another program is at the file; the next start settles it)
        return True

    def _note_attached(self, path):
        """The bot passed the account checks on the MetaTrader 5 at `path`: that terminal is noted as this
        account's (terminal_claims/<sha1 of the path>.json: {login_sha, login_tail, account, branch, at} -- no bot
        of another account then logs in there), and the login budget is cleared (the terminal holds the account:
        whatever a login was refused for is over). Each in its own try: a file that cannot be written is a line in
        the log and nothing else. Outside mt5_lock."""
        from datetime import datetime
        now = time.time()
        try:
            _write_json_atomic(_terminal_claim_path(path), {
                'login_sha': safety.login_sha(self._login), 'login_tail': self._login_tail, 'account': ACCOUNT_SLOT,
                'branch': str(BRANCH), 'at': now,
                'at_utc': datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
                'server': self._server, 'terminal_path': str(path)})
        except Exception as e:
            self._boot('WARN', 'START', f'could not note this MetaTrader 5 as the one of account {self._login_tail} '
                       f'({_err_text(e)}); the bot goes on')
        try:
            if not _remove_file(os.path.join(_account_folder(), _LOGIN_ATTEMPT_FILE)):
                self._boot('WARN', 'START', "could not delete the record of the bot's own logins; the bot goes on")
        except Exception:
            pass

    # ───────────────────── a MetaTrader 5 that lets no program trade ─────────────────────
    def _trading_not_allowed(self):
        """Why no order of this bot can go through right now, from what the terminal said last about itself and
        its account (self._terminal, self._acct): a list of the reasons of _TRADING_NOT_ALLOWED, [] = nothing
        stands in the way. A fact the terminal does not report counts as no problem."""
        t, a = self._terminal or {}, self._acct or {}
        reasons = []
        if t.get('trade_allowed') is False:
            reasons.append('algo_trading_off')
        if t.get('tradeapi_disabled') is True:
            reasons.append('python_api_disabled')
        if a.get('trade_allowed') is False:
            reasons.append('account_trade_disabled')
        if a.get('trade_expert') is False:
            reasons.append('account_expert_disabled')
        return reasons

    def _check_trading_allowed(self, symbol=None):
        """A warning only, never a refusal: when MetaTrader 5 starts or stops standing in the way of every order
        (_trading_not_allowed), a console line and an event -- TRADING_NOT_ALLOWED with the reasons, TRADING_ALLOWED
        when it is over. The bot goes on as before: every close is still tried, and an order the terminal refuses
        is logged as refused. Called where the terminal has just been read (the end of initialize_mt5, the poll
        guard), outside mt5_lock; never raises."""
        try:
            reasons = self._trading_not_allowed()
            if reasons == self._trade_blocked:
                return
            was, self._trade_blocked = self._trade_blocked, reasons
            symbol = symbol or self._symbol_of(None)
            if reasons:
                text = ('MetaTrader 5 does not let this bot trade: '
                        + '; '.join(_TRADING_NOT_ALLOWED[r] for r in reasons)
                        + '. Until that is changed the bot can neither open nor close: its open trades have only '
                          'their stop at the broker.')
                print(f"[{symbol}] WARNING: {text}")
                self._log_event(symbol, 'TRADING_NOT_ALLOWED', 'ERROR', {'reasons': list(reasons), 'problem': text})
            else:
                print(f"[{symbol}] note: MetaTrader 5 lets this bot trade again")
                self._log_event(symbol, 'TRADING_ALLOWED', 'SIGNAL', {
                    'was': list(was), 'note': 'MetaTrader 5 lets this bot trade again'})
        except Exception:
            pass

    # ───────────────────── an old bot on this server ─────────────────────
    def _old_bot_alive(self, force=False):
        """
        True while an old bot (a hedging_* branch) runs on this server: the newest of its files (_OLD_BOT_FILES,
        in the folder this bot's OUTPUT_DIR is in) was changed less than _OLD_BOT_ALIVE_S ago. Looked at again at
        most every _OLD_BOT_CHECK_S (force: now) and kept as a flag between: self._old_bot_alive_flag, with
        self._old_bot_age_s (how old that newest file is; None = there is none). File dates only: no terminal
        call, never inside mt5_lock; never raises (a folder that cannot be read: no old bot seen).
        """
        try:
            now = time.time()
            at = self._old_bot_checked_at
            if not force and at is not None and 0 <= now - at < _OLD_BOT_CHECK_S:
                return self._old_bot_alive_flag
            self._old_bot_checked_at = now
            parent = _parent_folder()
            newest = None
            for name in _OLD_BOT_FILES:
                try:
                    t = os.stat(os.path.join(parent, name)).st_mtime
                except OSError:
                    continue
                newest = t if newest is None else max(newest, t)
            self._old_bot_age_s = None if newest is None else round(now - newest, 1)
            # (abs: a file dated a little ahead of this clock is as fresh as one a little behind it)
            self._old_bot_alive_flag = newest is not None and abs(now - newest) < _OLD_BOT_ALIVE_S
        except Exception:
            self._old_bot_alive_flag, self._old_bot_age_s = False, None
        return self._old_bot_alive_flag

    def _old_bot_same_terminal(self):
        """True while an old bot is alive (the flag of _old_bot_alive: no file is read here) AND this bot's
        terminal_path is the old bots' MetaTrader 5: the old bot then trades this bot's account."""
        try:
            return bool(self._old_bot_alive_flag and self._credentials is not None
                        and _old_bots_terminal(self._credentials['terminal_path']))
        except Exception:
            return False

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
        """Fetch this bot's deal history for a specific symbol -- since its live start -- and save its summary to
        its folder (thread-safe)"""
        import os
        from datetime import datetime
        
        # Per-symbol folder: <OUTPUT_DIR>/daily_trade/{symbol}/
        output_dir = os.path.join(OUTPUT_DIR, DAILY_TRADE_SUBDIR, symbol)
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, HISTORICAL_SUMMARY_FILENAME)
        
        # Fetch only this symbol's deals: from a day before this bot's live start (state/live_start.json), and for
        # the configured history period while that is not known yet. A report only: nothing is decided on it.
        deal_symbol = mt5_symbol or symbol
        since = self._reporting_since()
        with self.mt5_lock:
            if since is None:
                all_deals = self.position_helper.get_deals_since(days=HISTORICAL_SUMMARY_DAYS, symbol=deal_symbol)
            else:
                all_deals = self.position_helper.get_deal_history(_utc(since), _utc(time.time() + 86400.0), deal_symbol)
        
        total_net = sum(d.get('net_profit', d['profit']) for d in all_deals)
        total_volume = sum(d['volume'] for d in all_deals)
        avg_net = round(total_net / len(all_deals), 2) if all_deals else 0
        
        summary = {
            'symbol': symbol,
            'last_updated': datetime.now(tz=timezone.utc).isoformat(),
            'period': 'Last 10 years' if since is None else f"since {_utc(since).strftime('%d %b %Y')}",
            'since_utc': None if since is None else _iso(since),
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
        # Never the full account number in the file (the dashboard's History tab shows it): a MetaTrader 5 folder
        # named after the account puts it into every terminal_path and problem text
        entry = self._without_login(entry)

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

    def _without_login(self, obj):
        """`obj` with this bot's account number replaced by its tail (_hide_login), for a file. Never raises: what
        cannot be masked is not written as it is."""
        try:
            return _hide_login(obj, self._login, self._login_tail)
        except Exception as e:
            return {'not_written': f'the values could not be masked ({type(e).__name__})'}

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

    # ───────────────────── per-basket state, loss pause, sizing ─────────────────────
    def _state_path(self, symbol):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, f'{symbol}_state.json')

    # Every state file of a real-money bot says which account it was written on: the account number as its
    # SHA-256 and its tail (never the number), and the branch. A file of another account is not this bot's: the
    # trade it describes is in that account.
    def _account_stamp(self):
        """What a state file records of the account it is written on, and of the branch."""
        return {'branch': BRANCH, 'login_sha': safety.login_sha(self._login), 'login_tail': self._login_tail}

    def _other_account_file(self, symbol, path, data, held_trade=False):
        """
        True when a state file read from `path` (`data`, its parsed content) was written on another account than
        this bot's: its login_sha is there and is not this account's. The file is then put aside -- renamed
        <name>.other-account-<yyyymmdd_hhmmss> (UTC) -- and not used: the caller rebuilds from the bot's own
        positions, as without a file. If the rename fails the file is left and still not used (the next save
        writes over it). One event STATE_OTHER_ACCOUNT; `held_trade`: the file held an open basket or Turtle trade
        -- then the owner is told that its positions may still be open in the other account, where nothing manages
        them. A file without the field is this bot's (written before the field existed); a bot without
        credentials has no account to compare with. Never raises; never called inside mt5_lock.
        """
        try:
            sha = data.get('login_sha') if isinstance(data, dict) else None
            own = safety.login_sha(self._login)
            if not isinstance(sha, str) or not sha or own is None or sha == own:
                return False
            tail = data.get('login_tail') if isinstance(data.get('login_tail'), str) else '...?'
            name = os.path.basename(path)
            aside = f'{path}.other-account-{_name_stamp(time.time())}'
            try:
                _replace_retry(path, aside)
                kept = f'put aside as {os.path.basename(aside)}'
            except Exception as e:
                aside = None
                kept = f'left where it is and not used (it could not be renamed: {_err_text(e)})'
            if held_trade:
                text = (f"This bot's saved trade belongs to account {tail}. If its positions are still open there, "
                        f"close them by hand. (The file {name} was written on account {tail}, not on this bot's "
                        f"{self._login_tail}: it was {kept}, and the bot starts without it.)")
            else:
                text = (f"The file {name} was written on account {tail}, not on this bot's {self._login_tail}: it was "
                        f'{kept}, and the bot starts without it.')
            print(f"[{symbol}] WARNING: {text}")
            self._log_event(symbol, 'STATE_OTHER_ACCOUNT', 'ERROR', {
                'file': name, 'set_aside_as': os.path.basename(aside) if aside else None,
                'file_login_tail': tail, 'own_login_tail': self._login_tail, 'file_branch': data.get('branch'),
                'held_open_trade': bool(held_trade), 'problem': text})
            return True
        except Exception:
            return True                     # (it IS another account's: not used, whatever went wrong telling so)

    def _load_state(self, symbol):
        """The persisted state ({'basket': ..., 'last_close': ...}) or None: no file, unreadable, written
        for another symbol / magic number, or written on another account (then it is rebuilt from the terminal).
        Never raises."""
        path = self._state_path(symbol)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:              # (OSError, not JSON, not text ...: loading never raises)
            print(f"[{symbol}] note: state file {path} unreadable ({e}); rebuilding it from the terminal")
            self._trace(symbol, 'state_note', 'WARN', f'the state file {path} is unreadable ({_err_text(e)}): it is rebuilt from '
                        'the terminal')
            return None
        if not isinstance(data, dict) or data.get('symbol') != symbol or data.get('magic') != MAGIC:
            print(f"[{symbol}] note: state file {path} is not this bot's (symbol/magic); rebuilding it from the terminal")
            self._trace(symbol, 'state_note', 'WARN', f"the state file {path} is not this bot's (symbol / magic): it is "
                        'rebuilt from the terminal')
            return None
        if self._other_account_file(symbol, path, data, held_trade=isinstance(data.get('basket'), dict)):
            return None
        return {'basket': data.get('basket'), 'last_close': data.get('last_close')}

    def _save_state(self, symbol, state):
        """Write the state atomically (a crash mid-write leaves the previous file), with the account it is written
        on (_account_stamp)."""
        path = self._state_path(symbol)
        data = {'version': _STATE_VERSION, 'symbol': symbol, 'magic': MAGIC, 'design': DESIGN_NAME,
                **self._account_stamp(),
                'saved_at': time.time(), 'basket': state.get('basket'), 'last_close': state.get('last_close')}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with self.thread_lock:
                with open(tmp, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                _replace_retry(tmp, path)
        except OSError as e:
            print(f"[{symbol}] Error: could not write the state file {path}: {e}")
            self._trace(symbol, 'state_note', 'ERROR', f'could not write the state file {path}: {_err_text(e)} (a restart now '
                        'would rebuild the basket from the terminal)')
            return
        self._trace(symbol, 'state_saved', state)

    # ───────────────────── when this bot first traded this account (state/live_start.json) ─────────────────────
    def _live_start_path(self):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, _LIVE_START_FILE)

    def _load_live_start(self, symbol):
        """state/live_start.json as this bot left it, kept in self._live_start: the record ({'time',
        'account_balance', 'login_sha', 'login_tail', 'branch', 'history_read', ...}) or None -- no file, not
        readable, without a time, or written on another account (then put aside as every state file of another
        account, and written anew by _note_live_start). Read once, before the loop. Never raises."""
        self._live_start = None
        try:
            path = self._live_start_path()
            status, data = _read_json_file(path)
            if status == 'ok' and isinstance(data, dict) and _is_number(data.get('time')):
                if not self._other_account_file(symbol, path, data):
                    self._live_start = data
        except Exception:
            self._live_start = None
        return self._live_start

    def _note_live_start(self, symbol, buy_positions, sell_positions, account_info):
        """
        state/live_start.json: when this bot first traded this account. Written at the first poll that passed the
        account guard (called at the end of a poll, after its order section) and not again while it is this
        account's:
          time             the earliest of now, the open time of this bot's oldest open position (this poll's own
                           positions read) and this bot's first deal in the account's history (ONE read of the deal
                           history, made here, in its own try);
          account_balance  the account's balance at that poll;
          login_sha, login_tail, branch   the account it was written on (_account_stamp);
          history_read     False while the deal history could not be read: the file then holds the earlier of the
                           other two, and the read is tried again every _LIVE_START_RETRY_S until it succeeds once
                           (the time can only move back).
        Nothing the bot decides on reads this file: the reads it decides on keep their own windows. The reporting
        reads start a day before `time` (the trace's trades list, _save_historical_summary), so a new account's
        figures hold this bot's trades and no older ones. Never raises: a failure is a line, at most once a minute.
        """
        path = None
        try:
            known = self._live_start
            if known is not None and known.get('history_read') is True:
                return                          # complete: nothing more for the life of this process
            now = time.time()
            if now < self._live_start_retry_at:
                return
            self._live_start_retry_at = now + _LIVE_START_RETRY_S
            times = [now]
            for side in (buy_positions, sell_positions):
                for p in (side or {}).get('positions') or []:
                    times.append(_pos_time(p))
            history_read = False
            try:
                with self.mt5_lock:
                    deals = self.position_helper.get_bot_deals(_utc(now - HISTORICAL_SUMMARY_DAYS * 86400.0),
                                                               _utc(now + 86400.0))
                if deals is not None:
                    history_read = True
                    times.extend(_deal_time(d) for d in deals)
            except Exception:
                history_read = False            # (the terminal did not answer: the other two, and again later)
            if known is not None:
                times.append(float(known['time']))
            start = min(float(t) for t in times if _is_number(t))
            if known is not None and not history_read and start >= float(known['time']):
                return                          # nothing new to say yet
            balance = known.get('account_balance') if known is not None else (account_info or {}).get('balance')
            record = {'time': start, 'time_utc': _iso(start), 'account_balance': balance, **self._account_stamp(),
                      'symbol': symbol, 'magic': MAGIC, 'written_at': now, 'history_read': history_read}
            path = self._live_start_path()
            _write_json_atomic(path, record)
            self._live_start = record
        except Exception as e:
            self._write_failed(symbol, f'state/{_LIVE_START_FILE}', path or _LIVE_START_FILE, e)

    def _reporting_since(self):
        """Where the reporting reads of the deal history start (epoch seconds): a day before this bot's live start;
        None while that is not known (the read then keeps its old window)."""
        known = self._live_start
        if isinstance(known, dict) and _is_number(known.get('time')):
            return float(known['time']) - 86400.0
        return None

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

    def _sizing_balance(self, account_info):
        """
        (sizing balance, account balance): what the unit rule counts for this bot is ACCOUNT_SHARE x the balance of
        the real account -- the booked balance (closed trades of both bots, deposits, withdrawals; an open trade
        counts when it closes) -- rounded to cents. (None, None) when the balance is not known on this poll (no
        account read, not a number, a share that is none): the caller then opens nothing new, and so it does for a
        sizing balance that is not above 0 (an account not funded yet).
        `account_info`: the poll's MT5PositionHelper.get_account_info() (a dict, or None).
        """
        balance = account_info.get('balance') if isinstance(account_info, dict) else None
        if not _is_number(balance) or not _is_number(ACCOUNT_SHARE) or not 0 < ACCOUNT_SHARE <= 1:
            return None, None
        return round(ACCOUNT_SHARE * balance, 2), balance

    def _open_held(self, kind, side, price, sizing_known=True):
        """
        The last test before an opening order is sent -- kind 'entry' (a new basket, a new Turtle trade), 'add'
        (a ladder add) or 'pyramid' (a Turtle add): None = send it, else why this poll does not (the poll local
        _open_hold, which the trace reads):
          {'why', 'side' ('BUY' / 'SELL'), 'kind', 'price' (the quote the order would have gone out at),
           'until' (epoch seconds when it is tried again, None = when the reason ends), 'refusals',
           'since' (for 'refused_backoff': epoch seconds of the first refusal of the streak, which the dashboard's
           banner names; None for every other why)}
        Every why but one comes from the flag the poll set before its decision (self._opens_stop, _opens_check),
        the same flag open_guard reads in buy() / sell():
          'old_bot'          an old bot runs on this server with this bot's MetaTrader 5 (the safety switch does
                             not lift it);
          'safety'           the safety blocks new trades (a limit, a block of this bot, a failing check);
          'safety_checking'  the safety checks a change of the balance that would reach a limit (a hold);
          'refused_backoff'  the broker refused the opens of the last 4 minutes or more: one try per 30 s, after
                             15 minutes per 60 s ('until': the next try, 'refusals': how many in a row).
        And 'balance_unknown': an entry while the sizing balance is not known or not above 0 -- the unit cannot be
        sized, so nothing new is opened on this poll (an add and a pyramid use the unit of their open trade and are
        not held by it). Never asked for a close: nothing here can hold back an exit. Never raises: a fault holds
        the order back ('safety') -- the next poll decides again.
        """
        try:
            now = time.time()
            if self._refusal is not None:
                self._refusal['wanted'] = now           # (the slower retry lasts while opens are wanted)
            stop = self._opens_stop
            if stop is not None and stop.get('why') != 'refused_backoff':
                return {'why': stop.get('why'), 'side': side, 'kind': kind, 'price': price, 'until': None,
                        'refusals': 0, 'since': None}
            if kind == 'entry' and not sizing_known:
                return {'why': 'balance_unknown', 'side': side, 'kind': kind, 'price': price, 'until': None,
                        'refusals': 0, 'since': None}
            if stop is not None:
                return {'why': 'refused_backoff', 'side': side, 'kind': kind, 'price': price,
                        'until': stop.get('until'), 'refusals': stop.get('refusals') or 0,
                        'since': stop.get('since')}
            return None
        except Exception:
            return {'why': 'safety', 'side': side, 'kind': kind, 'price': price, 'until': None, 'refusals': 0,
                    'since': None}

    def _basket_pnl(self, ids, since, now, closing_deals=False):
        """Realised P/L of the positions `ids` (profit + swap + commission + fee of all their deals, rounded to
        cents) once the history holds a closing deal for every one of them, else None. Also returns the time
        of the last closing deal. closing_deals: a third value, the closing deals of the same read --
        [{'position_id', 'reason', 'magic', 'time'}] (who closed each leg: the bot, another program, the broker's
        stop, a hand), None while the P/L is None. (The caller holds mt5_lock.)"""
        if not ids:
            return (None, None, None) if closing_deals else (None, None)
        frm = (since if since else now) - 2 * 86400
        deals = self.position_helper.get_bot_deals(_utc(frm), _utc(now + 86400))
        if deals is None:
            return (None, None, None) if closing_deals else (None, None)
        idset = {int(i) for i in ids}
        mine = [d for d in deals if getattr(d, 'position_id', None) in idset]
        outs = [d for d in mine if _is_out_deal(d)]
        if not idset <= {getattr(d, 'position_id', None) for d in outs}:
            return (None, None, None) if closing_deals else (None, None)
        pnl = 0.0
        for d in sorted(mine, key=lambda d: (_deal_time(d), int(getattr(d, 'ticket', 0) or 0))):
            pnl += _deal_net(d)
        if not closing_deals:
            return round(pnl, 2), max(_deal_time(d) for d in outs)
        closes = [{'position_id': getattr(d, 'position_id', None), 'reason': getattr(d, 'reason', None),
                   'magic': getattr(d, 'magic', None), 'time': _deal_time(d)} for d in outs]
        return round(pnl, 2), max(_deal_time(d) for d in outs), closes

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

    def _new_basket(self, side, units, levels, opened_at, opened_by='bot', sizing=None):
        """A basket as the state keeps it. `sizing`: how its unit was sized at the entry (sizing_record: the account
        balance, the share, the sizing balance, the step, the units), kept for the basket's life and across a
        restart; a basket taken over from the terminal has none."""
        b = dict(levels, side=side, units=int(units), ids=[], first_time=None, opened_at=float(opened_at),
                 opened_by=opened_by, ladder_armed=False, close_pending=False,
                 levels_pending=False, vol_source='open' if levels.get('vol_unit') is not None else None,
                 last_profit=0.0)
        if isinstance(sizing, dict):
            b['sizing'] = dict(sizing)
        return b

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
        # The P/L of this poll's positions is the trade's whole result only when this one close took every leg the
        # basket ever had: not after an earlier close of some of them (close_pending), not with a leg this poll's
        # positions did not list (an add filled and closed before any read listed it)
        listed = {_pos_id(p) for p in ((positions or {}).get('positions') or [])}
        whole = not (basket is not None and basket.get('close_pending')) and set(ids) <= listed
        lc = {'time': float(now), 'pnl': profit, 'lost': bool(profit < 0), 'resolved': False, 'source': 'decision',
              'reason': 'closed_outside' if outside else reason, 'side': side, 'ids': ids,
              'open_time': basket.get('first_time') if basket is not None else None, 'attempts': 0}
        if outside:
            lc['outside_ids'] = outside
        if not whole:
            lc['partial_close'] = True      # (its decision P/L is not the trade's: _closes_basket keeps none)
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

    # ───────────────────── this bot's account: the only account it trades on ─────────────────────
    @staticmethod
    def _last_error():
        try:
            return mt5.last_error()
        except Exception as e:          # a broken terminal connection can raise instead of answering
            return repr(e)

    def _same_account(self, acct):
        """True when `acct` (the terminal's account_info()) is the account of this bot's credentials: the same
        account number and the same trade server -- spaces and letter case aside, since the terminal and the owner
        may spell the server differently. A field the terminal does not report is never the same account, and a bot
        without loaded credentials has none: it never takes the account it finds as its own."""
        if acct is None or not self._login or not self._server:
            return False
        try:
            login = int(getattr(acct, 'login', None))
        except (TypeError, ValueError):
            return False
        server = getattr(acct, 'server', None)
        if server is None:
            return False
        return login == self._login and str(server).strip().casefold() == self._server.casefold()

    def _note_account(self, acct):
        """What the terminal has just said about its account, kept for the trace (self._acct; the account number as
        its tail only). Only reads `acct`; never raises."""
        try:
            self._acct = {
                'login_tail': safety.mask_login(getattr(acct, 'login', None)),
                'server': getattr(acct, 'server', None), 'currency': getattr(acct, 'currency', None),
                'leverage': getattr(acct, 'leverage', None), 'trade_allowed': getattr(acct, 'trade_allowed', None),
                'trade_expert': getattr(acct, 'trade_expert', None), 'trade_mode': getattr(acct, 'trade_mode', None),
                'margin_mode': getattr(acct, 'margin_mode', None)}
        except Exception:
            self._acct = None

    def _account_problem(self, acct=None):
        """
        Why the account the terminal is logged into may not be traded by this bot right now (None = it may). Read
        when the bot starts or reconnects, at the start of every poll, right after the positions read and before
        every order, always in this order:
          1. it is the account of the credentials (_same_account: the number and the server);
          2. it is a real account (trade_mode ACCOUNT_TRADE_MODE_REAL);
          3. it is a retail hedging account (the basket holds one position per fill).
        Any other program attached to the terminal (the other bot of the account, an old bot) can log it into
        another account at any time; this bot then waits and never logs in again over it. A bot without loaded
        credentials refuses every account: there is no "take the first account seen" for real money.
        Texts carry the tail of an account number (...1234), never the number.
        """
        if acct is None:
            acct = mt5.account_info()
        return self._account_check(acct)[1]

    def _account_check(self, acct, with_currency=False):
        """
        _account_problem with the kind of the problem: (None, None) = the account may be traded, else (kind, the
        problem's text) for the first of: 'no_answer' (account_info() gave nothing), 'no_credentials',
        'other_account', 'not_real', 'not_hedging'. with_currency -- when the bot starts or reconnects, not on a
        poll (the currency of an account never changes) -- then also 'currency_unknown' and 'not_usd': the unit
        rule, every target and every stop count in US dollars. The kinds 'not_real', 'not_hedging' and 'not_usd'
        are an account only the owner can exchange (_OWNER_KINDS). Only reads `acct`.
        """
        if acct is None:
            return 'no_answer', f'account_info() returned None (last_error {self._last_error()})'
        self._note_account(acct)
        if self._login is None:
            return 'no_credentials', self._no_credentials_problem()
        tail = safety.mask_login(getattr(acct, 'login', None))
        if not self._same_account(acct):
            return 'other_account', (f"MetaTrader 5 is logged into account {tail} on {getattr(acct, 'server', '?')}, "
                                     f"not this bot's account {self._login_tail} on {self._server}")
        real = getattr(mt5, 'ACCOUNT_TRADE_MODE_REAL', 2)
        mode = getattr(acct, 'trade_mode', None)
        if mode != real:
            return 'not_real', (f'account {tail} is not a real account: MetaTrader 5 reports it as '
                                f'{self._trade_mode_name(mode)} (trade_mode {mode}, real is {real})')
        hedging = getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING', 2)
        margin = getattr(acct, 'margin_mode', None)
        if margin != hedging:
            return 'not_hedging', f'account {tail} is not a hedging account (margin_mode {margin}, hedging is {hedging})'
        if with_currency:
            currency = getattr(acct, 'currency', None)
            if not isinstance(currency, str) or not currency.strip():
                return 'currency_unknown', (f'MetaTrader 5 does not say which currency account {tail} is kept in '
                                            f'(this bot counts in US dollars)')
            if currency.strip().upper() != 'USD':
                return 'not_usd', (f'Account {tail} is kept in {currency.strip()}. This bot counts in US dollars: '
                                   f'use a USD account.')
        return None, None

    def _no_credentials_problem(self):
        """Why this bot may attach to no terminal and trade no account (None = it may): it has no usable credentials
        -- none loaded, or a block the one normalisation refused. With an empty terminal_path mt5.initialize() would
        attach to a MetaTrader 5 it finds itself, on the server the old bots'."""
        if self._login is not None:
            return None
        why = self._credentials_problem or 'none loaded'
        return (f'this bot has no usable account details (the "{_MODE}" block of mt5_credentials.json: {why}): it '
                f'attaches to no MetaTrader 5 and trades nothing')

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
                self._boot('INFO', 'ACCOUNT', f'the terminal shows no account yet (account_info() answered {what}, '
                           f'last_error {err}): the bot reads it again every second for up to {_ACCOUNT_GRACE_S:g} s '
                           'before any login (a terminal that has just started logs into its saved account by itself)')
            time.sleep(1.0)

    @staticmethod
    def _trade_mode_name(mode):
        names = {getattr(mt5, 'ACCOUNT_TRADE_MODE_DEMO', 0): 'demo', getattr(mt5, 'ACCOUNT_TRADE_MODE_CONTEST', 1): 'contest',
                 getattr(mt5, 'ACCOUNT_TRADE_MODE_REAL', 2): 'real'}
        return names.get(mode, f'trade_mode {mode}')

    def _terminal_in_use_problem(self, acct):
        path = (self.credentials or {}).get('terminal_path')
        own = self._login_tail
        return (f"TERMINAL_IN_USE: MetaTrader 5 at {path} is logged into another account "
                f"({safety.mask_login(getattr(acct, 'login', None))} on {getattr(acct, 'server', '?')}), not this "
                f"bot's {own}. First make sure the old bot of this account is stopped. If this MetaTrader 5 is meant "
                f"for {own}: in it choose File > Login to Trade Account, enter {own} and tick Save password. If it "
                f"belongs to another account: install a second MetaTrader 5 in its own folder and put the path of its "
                f"terminal64.exe in terminal_path of both branches of this account. The bot never switches the "
                f"account itself; it tries again every 30 seconds.")

    def _terminal_in_use(self, problem, acct):
        """initialize_mt5 found the terminal logged into another account and left it alone: an ERROR event
        TERMINAL_IN_USE, limited by _log_limited. (Called outside mt5_lock: it writes the strategy log.)"""
        self._log_limited('TERMINAL_IN_USE', problem, {
            'terminal_path': (self.credentials or {}).get('terminal_path'),
            'login_tail': safety.mask_login(getattr(acct, 'login', None)),
            'server': getattr(acct, 'server', None), 'trade_mode': self._trade_mode_name(getattr(acct, 'trade_mode', None)),
            'own_login_tail': self._login_tail})

    # The events _log_limited writes: what initialize_mt5 refuses to start (or to reconnect) on and that can last
    # while the launcher starts the bot again every 30 s -- the terminal holds another account, or this bot's
    # number on another server; it shows no account and the bot may not log in; the bot's own login was refused;
    # an old bot runs on the same MetaTrader 5.
    _LIMITED_EVENTS = ('TERMINAL_IN_USE', 'SERVER_MISMATCH', 'LOGIN_WAIT', 'LOGIN_REFUSED', 'OLD_BOT_SAME_TERMINAL')

    def _log_limited(self, event, problem, details):
        """An ERROR event `event` (details + problem) for a problem initialize_mt5 refuses to start on: the first time
        the problem is seen, then at most every _LOG_REPEAT_S while it lasts, for each problem on its own (a terminal
        held in turn by two other accounts: each is logged, not every attempt) -- also across the launcher's restarts
        of app.py (a start reads the entries refused starts left at the head of the strategy log), so a problem that
        lasts does not fill the 200-entry log. True when it was logged. (It writes the strategy log: never called
        while mt5_lock is held.)"""
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
        at its head (_LIMITED_EVENTS); None when it is not there: no log, or another entry comes
        first (the bot ran in between, so this is a new occurrence)."""
        from datetime import datetime
        problem = self._without_login(problem)      # (as _log_event wrote it: the account number masked)
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
        details = {'problem': problem, 'own_login_tail': self._login_tail}
        if request is not None:
            details['request'] = {k: request.get(k) for k in ('action', 'symbol', 'type', 'volume', 'position')
                                  if k in request}
        self._log_event(symbol, 'ACCOUNT_REFUSED', 'ERROR', details, server_time=server_time)

    def _account_ok(self, symbol, server_time=None):
        """At the start of a poll: True when the terminal holds this bot's account (_account_problem). Otherwise the
        poll decides nothing -- no sync with the positions of another account (they would book this bot's basket as
        closed), no order -- until the account is right again (then an ACCOUNT_OK event)."""
        with self.mt5_lock:
            problem = self._account_problem()
        if problem is not None:
            self._account_refused(symbol, problem, server_time=server_time)
            return False
        if self._account_bad is not None:
            print(f"[{symbol}] note: the terminal holds this bot's account {self._login_tail} again: trading")
            self._log_event(symbol, 'ACCOUNT_OK', 'SIGNAL', {'login_tail': self._login_tail, 'was': self._account_bad},
                            server_time=server_time)
            self._account_bad = None
        return True

    def _order_guard(self, request):
        """Before every order_send (MT5PositionHelper._send): account_info() is read again and nothing is sent
        -- an open, an add or a close: it would reach another account -- unless it is still this bot's account
        (_account_problem); a refused request is an ERROR event, and the polls after it decide nothing until the
        account is right again (_account_ok). (Called inside the caller's mt5_lock.)"""
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
        new helper; a replay brings its own), _open_guard in front of its opening orders (buy() / sell()), and the
        trace's observer of every request and result behind them. Called at the start of every poll too, so a
        helper made by a reconnect has all three."""
        helper = self.position_helper
        if helper is not None and getattr(helper, 'order_guard', None) is None:
            helper.order_guard = self._order_guard
        if helper is not None and getattr(helper, 'open_guard', False) is None:
            helper.open_guard = self._open_guard
        if helper is not None and getattr(helper, 'order_observer', False) is None:
            helper.order_observer = self._order_observed

    def _open_guard(self, request):
        """The last line of defence in front of an opening order (MT5PositionHelper.buy / sell; a close never comes
        here): False = not sent. It reads the one flag the poll set before its decision (self._opens_stop: the
        safety, an old bot on this MetaTrader 5, the slower retry after refused orders) -- no file, no terminal,
        no Tracker. The poll's own tests stop such an order before the send, so this refuses only what they missed.
        (Called inside the caller's mt5_lock.)"""
        return self._opens_stop is None

    def _poll_guard(self, symbol):
        """At the start of every poll: True when the poll may read the terminal and decide -- the terminal answers
        and is connected, and it holds this bot's account: the account of the credentials, a real account, a
        hedging account, checked in that order (_account_problem)."""
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
        # (a warning only, from what the two reads above said: memory, and an event when it starts, changes or ends)
        self._check_trading_allowed(symbol)
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
            return f'terminal_info() raised {_err_text(e)}', True
        if info is None:
            return f'terminal_info() returned None (last_error {self._last_error()})', True
        self._note_terminal(info)
        if getattr(info, 'connected', True) is False:
            return f'the terminal is not connected to the trade server (last_error {self._last_error()})', False
        return None, False

    def _note_terminal(self, info):
        """What the terminal has just said about itself, kept for the trace (self._terminal). Only reads `info`;
        never raises. ping_ms: the terminal reports its last ping to the trade server in microseconds."""
        try:
            ping = getattr(info, 'ping_last', None)
            self._terminal = {
                'build': getattr(info, 'build', None),
                'ping_ms': round(ping / 1000.0, 1) if _is_number(ping) else None,
                'trade_allowed': getattr(info, 'trade_allowed', None),
                'tradeapi_disabled': getattr(info, 'tradeapi_disabled', None),
                'connected': getattr(info, 'connected', None)}
        except Exception:
            self._terminal = None

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
                'failed_polls': self._failed_polls, 'login_tail': self._login_tail})
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
        account for _ACCOUNT_GRACE_S, and only when the login rules allow one), the account checks, the symbol map
        and a new helper behind the order guard. True when the bot is on its own account again. Whatever it finds,
        a reconnect never ends the process: it fails and is tried again with the back-off (_try_reconnect).
        The terminal calls are made inside mt5_lock (initialize_mt5 takes it for each group of them, and frees it
        where it reads or writes a file)."""
        print(f"[{symbol}] reconnecting to the MT5 terminal ...")
        with self.mt5_lock:
            try:
                mt5.shutdown()
            except Exception:
                pass
            self.mt5_initialized = False
        try:
            return bool(self.initialize_mt5(reconnect=True))
        except Exception as e:              # (no credentials, a terminal that raises ...)
            self._init_problem = f'initialize_mt5 raised {_err_text(e)}'
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

    # ───────────────────── the auto-safety in the poll loop (safety.py) ─────────────────────
    # Where each part sits in a poll, both loops (the exits are never behind any of it):
    #   before the decision, memory only: _safety_poll (the Tracker's view, the one flag of the poll) and
    #     _foreign_now (what is on this symbol that is not this bot's, an old bot on this server);
    #   the four tests before a send (entry, ladder add, Turtle entry, Turtle pyramid): _open_held reads the flag;
    #     open_guard in buy() / sell() reads it once more;
    #   after the orders, beside the trace: _safety_after_orders (the cash read, the results of closed trades, the
    #     safety's files, its journal lines, state/safety_closes.json, the events and console lines).
    def _safety_path(self, name):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, name)

    def _safety_say(self, symbol, key, text, e=None):
        """A problem of the safety's own work in the loop: a console line and a WARN in the text log, at most once
        a minute per key. The poll goes on: nothing of the safety can stop it. Never raises."""
        try:
            now = time.time()
            if 0 <= now - self._step_said.get(key, -1e18) < _SAFETY_SAY_S:
                return
            self._step_said[key] = now
            msg = text if e is None else f'{text}: {_err_text(e)}'
            print(f"[{symbol}] WARNING: {msg}; the poll goes on")
            self._trace(symbol, 'exception', 'SAFETY', f'{msg}; the poll goes on', level='WARN')
        except Exception:
            pass

    def _safety_start(self, symbol):
        """This bot's Tracker: built once (the account folder, state/safety_state.json, the branch and its partner,
        the limits of the deployment block, this account) and loaded. True when it is usable. Called before the
        poll loop, and after the orders of every poll while it is not (until then new trades are blocked while
        the safety is ON: _safety_poll). Never raises; a failure is never remembered as "the safety is OFF"."""
        try:
            if self._tracker is None:
                limits = safety.Limits(SAFETY_DROP_PCT, SAFETY_DAY_PCT, SAFETY_STREAK_N)
                self._tracker = safety.Tracker(
                    _account_folder(), self._safety_path(_SAFETY_STATE_FILE), BRANCH, PARTNER_BRANCH, limits,
                    default_on=bool(SAFETY_DEFAULT_ON), login=self._login)
            self._tracker_ok = bool(self._tracker.load(time.time()))
        except Exception as e:
            self._tracker_ok = False
            self._safety_say(symbol, 'start', 'the safety could not be started', e)
        return self._tracker_ok

    def _safety_poll(self, symbol, account_info):
        """
        Before the poll's decision, in memory only (no file, no terminal): the safety's view for this poll (the
        poll local _safety) and the one flag every opening order of this poll is tested against
        (self._opens_stop: _opens_check). The Tracker gets this poll's booked balance, the balance operations read
        at the end of the last poll and how many closed trades of this bot still wait for their result; then the
        old ladder bot's trades on this symbol, when there are any (6.3), are noted to it -- after the poll, so an
        Unblock pressed while they are still open does not let one poll through.
        No usable Tracker, or it failed: new trades are blocked while the safety is ON (_safety_fallback).
        Time is always this module's time.time(), never the Turtle's tick time. Never raises.
        """
        try:
            return self._safety_poll_view(symbol, account_info)
        except Exception as e:              # (a fault even outside the Tracker: no open on this poll, the exits go on)
            self._opens_stop = {'why': 'safety', 'until': None, 'refusals': 0}
            self._safety_say(symbol, 'poll', 'the safety check failed', e)
            return {'enabled': True, 'blocked': True, 'hold': False, 'pending': False, 'error': _err_text(e),
                    'state': 'error', 'reasons': [getattr(safety, 'ERROR_SENTENCE', 'The safety check failed.')]}

    def _safety_poll_view(self, symbol, account_info):
        now = time.time()
        cash, cash_at = self._cash_next
        self._cash_next = (None, None)
        view = error = None
        tr = self._tracker
        try:
            if tr is None:
                error = 'SafetyNotStarted: the safety could not be started yet'
            else:
                balance = account_info.get('balance') if isinstance(account_info, dict) else None
                view = tr.poll(now, balance, cash, cash_at, len(self._closes.get('queue') or []))
                other = self._old_bot_trades_text(symbol)
                if other:
                    view = tr.note_other_program(now, other)
                if not isinstance(view, dict):
                    raise TypeError(f'the safety answered {type(view).__name__}, not its view')
        except Exception as e:
            view, error = None, _err_text(e)
        if view is None:
            view = self._safety_fallback(now, error)
        self._safety_view = view
        try:
            self._opens_stop = self._opens_check(view, now)
        except Exception:
            self._opens_stop = {'why': 'safety', 'until': None, 'refusals': 0}
        return view

    def _safety_fallback(self, now, error):
        """The view of a poll without a usable Tracker (it could not be built, or it failed): blocked while the
        safety is ON -- the switch as the account folder says it now (safety.read_controls; reads only), else as
        this process read it last, else SAFETY_DEFAULT_ON. The last view's meters are kept for the page; error
        says why ('<type>: <message>'). Never raises."""
        enabled = None
        try:
            ctl = safety.read_controls(_account_folder(), default_on=bool(SAFETY_DEFAULT_ON))
            if ctl.get('readable') and isinstance(ctl.get('enabled'), bool):
                enabled = self._switch_seen = ctl['enabled']
        except Exception:
            enabled = None
        if enabled is None:
            enabled = self._switch_seen if isinstance(self._switch_seen, bool) else bool(SAFETY_DEFAULT_ON)
        try:
            try:
                limits = safety.Limits(SAFETY_DROP_PCT, SAFETY_DAY_PCT, SAFETY_STREAK_N)
            except Exception:
                limits = safety.Limits()
            fresh = safety.build_view(None, limits, now, {
                'enabled': enabled, 'error': error, 'error_since': now, 'account_dir': _account_folder(),
                'login_tail': self._login_tail, 'branch': BRANCH, 'partner_branch': PARTNER_BRANCH})
        except Exception:
            fresh = {'reasons': [], 'since': None}
        last = self._safety_view if isinstance(self._safety_view, dict) else None
        view = dict(last if last is not None else fresh)
        view.update(enabled=enabled, blocked=enabled, hold=False, error=error, at=now,
                    state='error' if enabled else 'off', reasons=list(fresh.get('reasons') or []),
                    since=fresh.get('since'))
        return view

    def _opens_check(self, view, now):
        """The one flag of this poll (self._opens_stop), set before its decision: why no opening order may be
        sent now -- {'why', 'until', 'refusals'} -- or None (they may):
          'old_bot'          an old bot runs on this server with this bot's MetaTrader 5 (6.2): the safety switch
                             does not lift it;
          'safety'           the safety's view says blocked (a limit, a block of this bot, a failing check);
          'safety_checking'  it holds: a change of the balance that would reach a limit is being checked, or a
                             closed trade whose result could be the last losing one is waited for;
          'refused_backoff'  the broker has refused this bot's opens for 4 minutes: the next try at 'until', the
                             streak's first refusal at 'since'.
        A refusal streak with no open wanted for 10 minutes is over here."""
        if self._old_bot_same_terminal():
            return {'why': 'old_bot', 'until': None, 'refusals': 0}
        if view.get('blocked'):
            return {'why': 'safety', 'until': None, 'refusals': 0}
        if view.get('hold'):
            return {'why': 'safety_checking', 'until': None, 'refusals': 0}
        r = self._refusal
        if r is not None and not 0 <= now - float(r.get('wanted') or now) < _BACKOFF_IDLE_S:
            self._refusal = r = None
        if r is not None and r.get('first') is not None:
            age = now - float(r['first'])
            if age >= _BACKOFF_AFTER_S:
                every = _BACKOFF_EVERY_S[0] if age < _BACKOFF_SLOW_AFTER_S else _BACKOFF_EVERY_S[1]
                until = float(r['last_try']) + every
                if now < until:
                    return {'why': 'refused_backoff', 'until': until, 'refusals': int(r.get('count') or 0),
                            'since': float(r['first'])}
        return None

    def _foreign_now(self, own_open=None):
        """The poll local _foreign, from what this poll's positions read already showed (no terminal call, no file):
        {'positions' (trades on this symbol that are not this bot's), 'examples' (the first three), 'old_bot_age_s'
        (how old the old bot's newest file is, while one is alive; else None), 'old_bot_same_terminal'}. Never
        raises."""
        try:
            if own_open is not None:
                self._own_open = int(own_open)
            lf = getattr(self.position_helper, 'last_foreign', None)
            lf = lf if isinstance(lf, dict) else {}
            alive = self._old_bot_alive_flag is True
            return {'positions': int(lf.get('count') or 0), 'examples': [dict(x) for x in lf.get('examples') or []],
                    'old_bot_age_s': self._old_bot_age_s if alive else None,
                    'old_bot_same_terminal': bool(self._old_bot_same_terminal())}
        except Exception:
            return {'positions': 0, 'examples': [], 'old_bot_age_s': None, 'old_bot_same_terminal': False}

    def _old_bot_trades_text(self, symbol):
        """'another program holds 2 trades of its own on XAUUSDm' when this poll's positions read showed trades
        with the old ladder bot's mark (no magic, no comment, its automatic stops: mt5_helper.old_bot_mark), else
        None. Memory only."""
        lf = getattr(self.position_helper, 'last_foreign', None)
        n = int((lf or {}).get('old_bot') or 0) if isinstance(lf, dict) else 0
        if n <= 0:
            return None
        return f"another program holds {n} trade{'' if n == 1 else 's'} of its own on {self.symbol_map.get(symbol, symbol)}"

    def _note_open_answer(self, symbol, name, response, details, server_time=None):
        """The answer to an opening order this poll sent (name 'BUY' / 'SELL' for an entry, 'BUY_MORE' /
        'SELL_MORE' for an add; both loops). Filled: <name>_EXECUTED, and a streak of refusals is over. Anything
        else: <name>_REFUSED with the retcode and the broker's comment -- the first 3 of a streak one by one, then
        one line at most every 30 s with how many since. Only an answer of the broker (a retcode) counts for the
        slower retry (_opens_check): a request a guard stopped, or one MetaTrader 5 did not answer, never reached
        the broker. In the order section, as the event it replaces; memory and the strategy log only. True when
        filled."""
        if self._order_done(response):
            self._refusal = None
            self._log_event(symbol, f'{name}_EXECUTED', 'ENTRY', details, server_time=server_time)
            return True
        d = dict(details or {})
        try:
            now = time.time()
            r = self._refusal
            if r is None:
                r = self._refusal = {'first': None, 'count': 0, 'last_try': now, 'wanted': now, 'n': 0,
                                     'logged_at': None, 'unlogged': 0}
            r['wanted'] = now
            r['n'] += 1
            retcode = getattr(response, 'retcode', None) if response is not None else None
            if retcode is not None:
                if r['first'] is None:
                    r['first'] = now
                r['count'] += 1
                r['last_try'] = now
            if (r['n'] > _REFUSED_ONE_BY_ONE and r['logged_at'] is not None
                    and 0 <= now - r['logged_at'] < _REFUSED_SUMMARY_S):
                r['unlogged'] += 1
                return False
            unlogged, r['logged_at'], r['unlogged'] = r['unlogged'], now, 0
            d.update(retcode=retcode, comment=getattr(response, 'comment', None) if response is not None else None,
                     refusals=r['n'], broker_refusals=r['count'], refusing_since=r['first'])
            if response is None:
                d['no_answer'] = True       # (nothing reached the broker: the log must not say it refused)
                d['note'] = ('MetaTrader 5 gave no answer: the order was not sent (a guard stopped it) or the '
                             'terminal did not answer')
            if r['n'] > _REFUSED_ONE_BY_ONE:
                d.update(summary=True, not_logged_since=unlogged)
            print(f"[{symbol}] note: {name} not filled: "
                  + (d['note'] if response is None else f"retcode {retcode} ({d.get('comment')})")
                  + f"; {r['n']} in a row (an order that closes a trade is never held back)")
        except Exception:
            pass
        self._log_event(symbol, f'{name}_REFUSED', 'ORDER', d, server_time=server_time)
        return False

    # ── the losing-trades rule: closed trades waiting for their result (state/safety_closes.json) ──
    @staticmethod
    def _clean_ids(ids):
        out = []
        for i in ids or []:
            try:
                v = int(i)
            except (TypeError, ValueError):
                continue
            if v > 0 and v not in out:
                out.append(v)
        return out

    def _load_closes(self, symbol):
        """state/safety_closes.json as this bot left it: {'turtle': the position ids of the Turtle's running trade
        ({'entry_time', 'ids', 'decision_pnl'}) or None, 'queue': closed trades waiting for their result
        [{'trade_key', 'ids', 'opened_at', 'closed_at', 'decision_pnl', 'kind', 'reason'}]}; empty without the
        file, for another symbol or magic number, or written on another account (then put aside, as every state
        file of another account). Read once, before the loop. Never raises."""
        self._closes, self._closes_dirty = {'turtle': None, 'queue': []}, False
        try:
            path = self._safety_path(_SAFETY_CLOSES_FILE)
            status, data = _read_json_file(path)
            if status != 'ok' or not isinstance(data, dict):
                return
            if data.get('symbol') != symbol or data.get('magic') != MAGIC or self._other_account_file(symbol, path, data):
                return
            queue = []
            for e in data.get('queue') or []:
                if not isinstance(e, dict) or not _is_number(e.get('closed_at')) or e.get('trade_key') is None:
                    continue
                queue.append({'trade_key': e['trade_key'], 'ids': self._clean_ids(e.get('ids')),
                              'opened_at': e.get('opened_at') if _is_number(e.get('opened_at')) else None,
                              'closed_at': float(e['closed_at']),
                              'decision_pnl': e.get('decision_pnl') if _is_number(e.get('decision_pnl')) else None,
                              'kind': e.get('kind'), 'reason': e.get('reason')})
            tu = data.get('turtle')
            if isinstance(tu, dict):
                tu = {'entry_time': tu.get('entry_time'), 'ids': self._clean_ids(tu.get('ids')),
                      'decision_pnl': tu.get('decision_pnl') if _is_number(tu.get('decision_pnl')) else None}
            else:
                tu = None
            self._closes = {'turtle': tu, 'queue': queue[-50:]}
        except Exception:
            self._closes = {'turtle': None, 'queue': []}

    def _save_closes(self, symbol):
        """state/safety_closes.json, when it changed (after the orders; never inside mt5_lock). False = it could
        not be written (tried again after 5 s)."""
        if not self._closes_dirty:
            return True
        data = {'version': _STATE_VERSION, 'symbol': symbol, 'magic': MAGIC, **self._account_stamp(),
                'saved_at': time.time(), 'turtle': self._closes.get('turtle'), 'queue': self._closes.get('queue')}
        _write_json_atomic(self._safety_path(_SAFETY_CLOSES_FILE), data)
        self._closes_dirty = False
        return True

    def _queue_close(self, ids, opened_at, decision_pnl, kind, reason=None):
        """A trade of this bot has ended: it waits in the queue for its result (memory; saved after the orders).
        trade_key = its smallest position id (counted once by the Tracker, whatever happens after)."""
        ids = self._clean_ids(ids)
        key = min(ids) if ids else f'{kind}-{opened_at}'
        queue = self._closes.setdefault('queue', [])
        if any(e.get('trade_key') == key for e in queue):
            return
        queue.append({'trade_key': key, 'ids': sorted(ids),
                      'opened_at': float(opened_at) if _is_number(opened_at) else None, 'closed_at': time.time(),
                      'decision_pnl': float(decision_pnl) if _is_number(decision_pnl) else None,
                      'kind': kind, 'reason': reason})
        del queue[:-50]
        self._closes_dirty = True

    def _closes_basket(self, lc, was=None):
        """The basket loop: `lc` is the state's last_close after the sync or after this bot's close; when it is a
        new one (not `was`) and not the start's rebuild from the history, the basket it books has ended and waits
        for its result. The P/L at the close decision stands in when the history never shows it -- only for this
        bot's own close that took every leg at once (an outside close, or one spread over several polls, is not known
        whole: it then counts as a loss). Memory only."""
        try:
            if not isinstance(lc, dict) or lc is was or lc.get('source') == 'history_rebuild':
                return
            own = lc.get('source') == 'decision' and not lc.get('outside_ids') and not lc.get('partial_close')
            self._queue_close(lc.get('ids'), lc.get('open_time'), lc.get('pnl') if own else None, 'basket',
                              lc.get('reason'))
        except Exception:
            pass

    def _closes_turtle(self, st, listed=None, ended=None):
        """
        The Turtle loop, before its decision and after its orders: the position ids of the running trade,
        collected over its whole life (every leg of the book -- the order ticket of each fill, each listing of the
        sync) and kept in state/safety_closes.json until the trade ends. A trade that ended in the sync (`ended`:
        (side, entry_time) of the book just before the sync, when the sync ended it: all legs gone, or replaced)
        waits in the queue for its result, with all of those ids. So does the record of a trade the book does not
        hold any more after a restart: the book holds another trade (none of the same legs), or it is flat while
        the terminal lists none of this bot's positions (`listed` 0). A book rebuilt from the positions after a
        restart keeps the record (the same legs). Memory only; never raises.
        """
        try:
            rec = self._closes.get('turtle')
            legs = self._clean_ids([leg.get('ticket') for leg in st.get('legs') or [] if isinstance(leg, dict)])
            if isinstance(rec, dict):
                same = bool(st.get('side')) and (rec.get('entry_time') == st.get('entry_time')
                                                 or bool(set(rec.get('ids') or []) & set(legs)))
                if ended is not None and ended[1] == rec.get('entry_time'):
                    gone = True                     # (the sync has just ended this very trade)
                elif same:
                    gone = False
                    if rec.get('entry_time') != st.get('entry_time'):
                        rec['entry_time'] = st.get('entry_time')
                        self._closes_dirty = True
                else:
                    gone = bool(st.get('side')) or listed == 0
                if gone:
                    self._queue_close(rec.get('ids'), rec.get('entry_time'), rec.get('decision_pnl'), 'turtle')
                    self._closes['turtle'] = rec = None
                    self._closes_dirty = True
            if not st.get('side'):
                return
            if not isinstance(rec, dict):
                rec = self._closes['turtle'] = {'entry_time': st.get('entry_time'), 'ids': [], 'decision_pnl': None}
                self._closes_dirty = True
            for i in legs:
                if i not in rec['ids']:
                    rec['ids'].append(i)
                    self._closes_dirty = True
        except Exception:
            pass

    def _turtle_close_seen(self, st, positions):
        """The bot's own close has taken the last legs of the Turtle's trade: it waits in the queue for its result
        with every position id the trade had (just before T.on_exit wipes the book). Its P/L at this decision
        stands in if the history never shows the result -- only when this one close took every leg (a close
        finished over several polls is not known whole: it then counts as a loss). Memory only; never raises."""
        try:
            self._closes_turtle(st)                 # (its legs of this poll are among its ids)
            rec = self._closes.get('turtle')
            ids = list(rec.get('ids') or []) if isinstance(rec, dict) else []
            ids += [leg.get('ticket') for leg in st.get('legs') or [] if isinstance(leg, dict)]
            # (whole: every leg the trade ever had is among this poll's positions -- not one closed by hand inside the
            # stop earlier, whose P/L the positions' total does not hold)
            listed = {_pos_id(p) for p in ((positions or {}).get('positions') or [])}
            whole = set(self._clean_ids(ids)) <= listed
            decision = positions.get('total_profit') if (positions and not st.get('closing') and whole) else None
            self._queue_close(ids, st.get('entry_time'), decision, 'turtle', 'stop')
            self._closes['turtle'] = None
            self._closes_dirty = True
        except Exception:
            pass

    def _resolve_close(self, symbol):
        """After the orders: the oldest closed trade waiting for its result. In the deal history (every leg has its
        closing deal: _basket_pnl, the same read as the loss pause's) -> counted by the Tracker (once, by its
        smallest position id) and taken off the queue; a leg another program closed (reason EXPERT, a magic not
        this bot's) blocks this bot (6.3). Not there for 10 minutes -> counted with the P/L the bot saw at its
        close, else as a loss (CLOSE_RESULT_UNKNOWN). Only with a loaded Tracker (else it waits). One history read,
        inside mt5_lock (taken here, the caller holds none)."""
        queue = self._closes.get('queue') or []
        tr = self._tracker
        if not queue or tr is None or not self._tracker_ok:
            return True
        e = queue[0]
        now = time.time()
        with self.mt5_lock:
            pnl, _t, deals = self._basket_pnl(e.get('ids') or [], e.get('opened_at') or e.get('closed_at'), now,
                                              closing_deals=True)
        if pnl is not None:
            tr.on_trade_closed(now, e['trade_key'], pnl)
            queue.pop(0)
            self._closes_dirty = True
            expert = getattr(mt5, 'DEAL_REASON_EXPERT', 3)
            other = [d for d in deals or [] if d.get('reason') == expert and d.get('magic') != MAGIC]
            if other:
                at = max(float(d.get('time') or now) for d in other)
                text = f"another program closed this bot's trade at {_clock_text(at, now)}"
                tr.note_other_program(now, text)
                self._events_due.append(('OTHER_PROGRAM', 'ERROR', {
                    'problem': f"{_cap(text)}: a program with magic {other[0].get('magic')} closed position(s) "
                               f"{sorted({d.get('position_id') for d in other})}. If the old ladder bot still runs "
                               "on this account, stop it.",
                    'trade_key': e['trade_key'], 'magic': other[0].get('magic'), 'source': 'close'}))
            return True
        if not 0 <= now - float(e.get('closed_at') or now) < _RESULT_WAIT_S:
            seen = e.get('decision_pnl')
            tr.on_trade_closed(now, e['trade_key'], seen)
            queue.pop(0)
            self._closes_dirty = True
            counted = (f'counted with the P/L the bot saw at its close (${seen:,.2f})' if _is_number(seen)
                       else 'counted as a losing trade')
            self._events_due.append(('CLOSE_RESULT_UNKNOWN', 'ERROR', {
                'problem': (f'The result of the closed trade {e["trade_key"]} is not in the deal history after '
                            f'{_RESULT_WAIT_S / 60:g} minutes: {counted} for the losing-trades rule.'),
                'trade_key': e['trade_key'], 'ids': list(e.get('ids') or []), 'decision_pnl': seen}))
        return True

    def _read_cash(self):
        """After the orders, while the Tracker needs them: the account's balance operations since cash_since(), for
        the next poll ((list, the time of this read); (None, None) when the read failed: False, tried again after
        5 s). One terminal call, inside mt5_lock (taken here, the caller holds none)."""
        tr = self._tracker
        if tr is None or not tr.needs_cash():
            return True
        since = float(tr.cash_since())
        at = time.time()
        with self.mt5_lock:
            deals = self.position_helper.get_cash_deals(since, at + 86400.0)
        if deals is None:
            self._cash_next = (None, None)
            return False
        self._cash_next = (deals, at)
        return True

    def _journal(self, symbol, kind, fields):
        """A line of the permanent journal (tracelog queues it; never raises)."""
        try:
            f = {(f'item_{k}' if k in ('symbol', 'method', 'self') else k): v for k, v in dict(fields or {}).items()}
            self._trace(symbol, 'journal', kind, **f)
        except Exception:
            pass

    def _after_step(self, symbol, name, fn, *args):
        """One step after the orders, on its own: an exception is said at most once a minute (_safety_say), and a
        step that failed (or answered False) is tried again after _SAFETY_RETRY_S, not on every poll."""
        now = time.time()
        at = self._step_retry.get(name)
        if at is not None and 0 <= at - now <= _SAFETY_RETRY_S:
            return
        try:
            ok = fn(*args)
        except Exception as e:
            ok = False
            self._safety_say(symbol, name, f'the safety step "{name}" failed', e)
        if ok is False:
            self._step_retry[name] = now + _SAFETY_RETRY_S
        else:
            self._step_retry.pop(name, None)

    def _safety_after_orders(self, symbol, open_hold, foreign, server_time=None):
        """
        After the poll's orders, beside the trace: everything of the safety that reads the terminal or the disk,
        each step on its own (_after_step: none can stop the poll; one that failed is tried again after 5 s):
          1. the account's balance operations, while the Tracker needs them (for the next poll);
          2. the oldest closed trade waiting for its result (the losing-trades rule; 6.3);
          3. the Tracker built / loaded again while it is not usable; its files (flush); its journal lines;
          4. state/safety_closes.json when it changed;
          5. the events and console lines of what began, changed or ended (_safety_events).
        Never raises.
        """
        try:
            self._after_step(symbol, 'cash', self._read_cash)
            self._after_step(symbol, 'results', self._resolve_close, symbol)
            if self._tracker is None or not self._tracker_ok:
                self._after_step(symbol, 'start', self._safety_start, symbol)
            tr = self._tracker
            if tr is not None:
                self._after_step(symbol, 'flush', tr.flush, time.time())
                self._after_step(symbol, 'journal', self._safety_journal, symbol, tr)
            self._after_step(symbol, 'closes', self._save_closes, symbol)
            self._after_step(symbol, 'events', self._safety_events, symbol, open_hold, foreign, server_time)
            del self._events_due[:-50]          # (bounded, should the events keep failing)
        except Exception as e:
            self._safety_say(symbol, 'after', 'the safety steps after the orders failed', e)

    def _safety_journal(self, symbol, tr):
        for e in tr.take_events() or []:
            if isinstance(e, dict):
                self._journal(symbol, 'safety', e)
        return True

    def _safety_events(self, symbol, open_hold, foreign, server_time=None):
        """The events and console lines of the safety and of other activity on the account, each when it begins,
        changes or ends (the dashboard's banners come from the trace's state, not from these): SAFETY_ERROR,
        SAFETY_BLOCKED / SAFETY_UNBLOCKED, SAFETY_SKIP (and the journal's skip line: once per kind and side, again
        after 15 minutes), FOREIGN_POSITIONS, OLD_BOT_SAME_TERMINAL / OLD_BOT_RUNNING, OTHER_PROGRAM, and those the
        order section left for here (CLOSE_RESULT_UNKNOWN, TURTLE_ADDS_STOPPED ...)."""
        now = time.time()
        view = self._safety_view if isinstance(self._safety_view, dict) else {}
        said = self._said
        mt5_symbol = self.symbol_map.get(symbol, symbol)
        # the safety check fails (it blocks new trades while ON)
        err = view.get('error') if view.get('enabled') is not False else None
        if err:
            if said.get('safety_error') != err:
                said['safety_error'], said['safety_error_at'] = err, now
                print(f"[{symbol}] WARNING: the safety check failed: {err}. No new trade until it works again or the "
                      f"safety is turned OFF; open trades are still managed")
                self._log_event(symbol, 'SAFETY_ERROR', 'ERROR', {'problem': err, 'state': view.get('state')},
                                server_time=server_time)
            elif not 0 <= now - float(said.get('safety_error_at') or 0.0) < _SAFETY_SAY_S:
                said['safety_error_at'] = now
                print(f"[{symbol}] WARNING: the safety check still fails: {err}")
        elif said.get('safety_error'):
            said['safety_error'] = None
            print(f"[{symbol}] note: the safety check works again")
        # a block of the account or of this bot: once per new block, and when it is lifted
        enabled = view.get('enabled') is not False
        blocked = enabled and bool(view.get('account_blocked') or view.get('bot_blocked'))
        key = (view.get('blocked_scope'), view.get('period')) if blocked else None
        was = said.get('safety_block')
        if key != was:
            said['safety_block'] = key
            if key is not None:
                reasons = [str(x) for x in view.get('reasons') or [] if x]
                print(f"[{symbol}] WARNING: SAFETY BLOCK: {' '.join(reasons)}")
                self._log_event(symbol, 'SAFETY_BLOCKED', 'ERROR', {
                    'scope': key[0], 'reasons': reasons, 'since': view.get('since'), 'state': view.get('state'),
                    'drop': view.get('drop'), 'day': view.get('day'), 'streak': view.get('streak')},
                    server_time=server_time)
            elif was is not None:
                print(f"[{symbol}] note: the safety block is lifted: new trades are allowed again")
                self._log_event(symbol, 'SAFETY_UNBLOCKED', 'SIGNAL', {'was': was[0], 'enabled': enabled},
                                server_time=server_time)
        # an opening order the strategy wanted and this poll held back (not a balance that is not known: that has
        # its own "Entry held" line)
        if isinstance(open_hold, dict) and open_hold.get('why') and open_hold.get('why') != 'balance_unknown':
            k = (open_hold.get('kind'), open_hold.get('side'))
            skips = said.setdefault('skips', {})
            if k not in skips or not 0 <= now - skips[k] < _SKIP_SAY_S:
                skips[k] = now
                d = {'hold': dict(open_hold), 'kind': open_hold.get('kind'), 'side': open_hold.get('side'),
                     'price': open_hold.get('price'), 'safety_state': view.get('state'),
                     'safety_reasons': [str(x) for x in view.get('reasons') or [] if x]}
                self._log_event(symbol, 'SAFETY_SKIP', 'SIGNAL', d, server_time=server_time)
                self._journal(symbol, 'skip', dict(open_hold, safety_state=view.get('state'),
                                                   safety_reasons=d['safety_reasons']))
        # trades on this symbol that are not this bot's (6.1)
        fo = foreign if isinstance(foreign, dict) else {}
        n = int(fo.get('positions') or 0)
        magics = tuple(sorted({str(x.get('magic')) for x in fo.get('examples') or [] if isinstance(x, dict)}))
        key = (n, magics) if n else None
        if key != said.get('foreign'):
            was = said.get('foreign')
            said['foreign'] = key
            if key is not None:
                text = _foreign_text(mt5_symbol, fo) + f" ({n} such trade{'' if n == 1 else 's'})"
                print(f"[{symbol}] WARNING: {text}")
                self._log_event(symbol, 'FOREIGN_POSITIONS', 'ERROR', {
                    'positions': n, 'examples': list(fo.get('examples') or []), 'problem': text},
                    server_time=server_time)
            elif was is not None:
                print(f"[{symbol}] note: no trade that is not this bot's is open on {mt5_symbol} any more")
        # an old bot on this server (6.2): with this bot's MetaTrader 5 it blocks every open; with another, a note
        state = 'same' if fo.get('old_bot_same_terminal') else ('other' if fo.get('old_bot_age_s') is not None else None)
        if state != said.get('old_bot'):
            was = said.get('old_bot')
            said['old_bot'] = state
            printed = said.pop('old_bot_printed', None)
            if state == 'same':
                print(f"[{symbol}] WARNING: {_OLD_BOT_TEXT} Until then this bot opens nothing new; its open trades "
                      f"are managed as always.")
                self._log_event(symbol, 'OLD_BOT_SAME_TERMINAL', 'ERROR', {
                    'problem': _OLD_BOT_TEXT, 'old_bot_age_s': self._old_bot_age_s, 'running': True},
                    server_time=server_time)
            elif state == 'other':
                text = _old_bot_elsewhere_text(self._login_tail)
                if printed != 'other':
                    print(f"[{symbol}] note: {text}")          # (an amber warning: nothing is held back)
                self._log_event(symbol, 'OLD_BOT_RUNNING', 'SIGNAL', {
                    'problem': text, 'old_bot_age_s': self._old_bot_age_s}, server_time=server_time)
            elif was is not None:
                print(f"[{symbol}] note: the old bot on this server has stopped (its files no longer change)")
        # the old ladder bot's own trades on this symbol (6.3: this bot is blocked through the safety)
        other = self._old_bot_trades_text(symbol)
        if other != said.get('other_program'):
            said['other_program'] = other
            if other:
                text = (f"{_cap(other)} in this account (no magic number, no comment, the old ladder bot's stops). "
                        'If the old ladder bot still runs on this account, stop it, close its trades, then press '
                        'Unblock.')
                print(f"[{symbol}] WARNING: {text}")
                self._log_event(symbol, 'OTHER_PROGRAM', 'ERROR', {'problem': text, 'source': 'positions'},
                                server_time=server_time)
        # what the order section left for here
        due, self._events_due = self._events_due, []
        for event, tag, details in due:
            note = (details or {}).get('problem') or (details or {}).get('note')
            if note:
                print(f"[{symbol}] WARNING: {note}")
            self._log_event(symbol, event, tag, details, server_time=server_time)
        return True

    def _old_bot_switched_note(self, symbol):
        """A poll the guard refused while an old bot runs on this bot's MetaTrader 5 (6.2 C): the console says
        what happened, once per account it switched to. Never raises."""
        try:
            if not (self._guard_why and self._guard_why[0] == 'account' and self._old_bot_same_terminal()):
                self._said.pop('old_bot_switched', None)
                return
            tail = (self._acct or {}).get('login_tail') or '...?'
            n = int(getattr(self, '_own_open', 0) or 0)
            key = (tail, n)
            if self._said.get('old_bot_switched') == key:
                return
            self._said['old_bot_switched'] = key
            print(f"[{symbol}] WARNING: MetaTrader 5 was switched to account {tail}. This bot has {n} open "
                  f"trade{'' if n == 1 else 's'} it cannot manage. Stop the old bot, then log MetaTrader 5 back into "
                  f"{self._login_tail}.")
        except Exception:
            pass

    @staticmethod
    def _turtle_rec_matches(st, rec):
        """True when the side file's record `rec` is the book's open trade's (the same entry time, or its first
        fill among the trade's legs)."""
        if not isinstance(rec, dict) or not st.get('side'):
            return False
        if rec.get('entry_time') is not None and rec.get('entry_time') == st.get('entry_time'):
            return True
        ticket = rec.get('ticket')
        return ticket is not None and any(isinstance(leg, dict) and leg.get('ticket') == ticket
                                          for leg in st.get('legs') or [])

    def process_symbol(self, symbol):
        """
        Process a single symbol (will be called in separate threads)
        Lightweight and optimized - runs in infinite loop

        One poll, in the backtester's order (kernels.py run_kernel; map: scratchpad map_levers.md §2):
          market data + this bot's positions (MAGIC) -> the basket's state matched with them ->
          unit (only while flat, from this bot's share of the account balance) -> brake -> liveness (a dead
          poll decides nothing)
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
        # The balance the tiers count is this bot's share of the real account balance
        # (_sizing_balance: ACCOUNT_SHARE x the balance; the other bot of the account has
        # the rest), and an open basket keeps the unit recorded at its open (after a
        # restart: its oldest position's volume / mtqty). While that balance is not known,
        # or not above 0, no new basket is opened (_open_held).
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
        _sizing = None                          # how the unit in effect was sized (sizing_record): the trace reads it
        _sizing_known = False                   # the sizing balance was known and above 0 on the last flat poll
        _open_hold = None                       # why this poll did not send an open it wanted (_open_held), else None
        self._load_live_start(symbol)           # when this bot first traded this account (the reporting reads)
        # the safety: the closed trades still waiting for their result, and this bot's Tracker (built and loaded;
        # tried again after every poll while it is not usable -- new trades are blocked meanwhile while it is ON)
        self._load_closes(symbol)
        self._safety_start(symbol)
        _safety = self._safety_view             # the safety's view this poll decided on (the trace reads it)
        _safety_blocked = False                 # it blocks or holds new trades on this poll
        _foreign = None                         # what is on this symbol that is not this bot's; an old bot
        # the trace: the start-up block of the text log (branch, design, every constant, the state found)
        self._trace(symbol, 'loop_start', locals())

        while True:
            try:
                # Start of one full iteration's work (excludes the end-of-cycle sleep)
                _iter_start = time.perf_counter()
                _open_hold = None
                # An old bot on this server: its files' dates, looked at every 10 s on every pass -- a pass the
                # guard refuses too -- and kept as a flag (no terminal call, outside mt5_lock)
                self._old_bot_alive()

                # ── The terminal must answer and hold this bot's account, else this poll decides nothing ──
                if not self._poll_guard(symbol):
                    self._old_bot_switched_note(symbol)
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
                _lc_was = state.get('last_close')
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
                # a basket the sync booked as ended (closed outside the bot, replaced): it waits for its result
                # (the losing-trades rule; memory only, resolved after the orders)
                self._closes_basket(state.get('last_close'), _lc_was)
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
                # the next basket. Balance is unavailable → keep the current unit
                # (and open no new basket on this poll: _sizing_known, _open_held).
                if _fill_pending:
                    units = int(basket['units'])
                    _sizing = open_trade_sizing(basket.get('sizing'), units, step_up_balance, mtqty, max_limit)
                elif _buy_ct == 0 and _sell_ct == 0:
                    # this bot's share of the real account balance (the poll's own account read: no other call)
                    balance, _account_balance = self._sizing_balance(account_info)
                    _sizing_known = balance is not None and balance > 0
                    if _sizing_known:
                        if step_up_balance and step_up_balance > 0:
                            units = int(balance // step_up_balance) + 1
                        else:
                            units = 1
                        units = max(1, min(units, max_limit))
                    _sizing = sizing_record(_account_balance, balance, step_up_balance, units, mtqty, max_limit,
                                            'balance' if _sizing_known else 'unknown', _now)
                elif _in_basket:
                    units = int(basket['units'])
                    _sizing = open_trade_sizing(basket.get('sizing'), units, step_up_balance, mtqty, max_limit)

                # ── Effective brake: manual override OR outside trading window ──
                # brake_manual=1 → always braked; else brake when outside the
                # configured trading_window (server-time based).
                in_window = self._is_in_trading_window(server_time, trading_window_cfg)
                brake = 1 if brake_manual or not in_window else 0

                # ── The safety, in memory only: its view for this poll, and the one flag every opening order of
                # this poll is tested against (the tests before a send, then open_guard in buy() / sell()) ──
                _safety = self._safety_poll(symbol, account_info)
                _safety_blocked = bool(_safety.get('blocked') or _safety.get('hold'))
                _foreign = self._foreign_now(_buy_ct + _sell_ct)

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
                    # The last test before an add is sent: the one flag of this poll (the safety, an old bot on
                    # this MetaTrader 5, the slower retry after refused orders). The add is not sent; the arming
                    # stays as the votes have it (analysis_data['ladder_armed'] is not touched), so the add comes
                    # on the first poll it is allowed, as after a restart. (A close to finish replaces the add
                    # below anyway: no add was going out then.)
                    if (not (_in_basket and basket.get('close_pending'))
                            and (buy_signal == Signal.BUY_MORE or sell_signal == Signal.SELL_MORE)):
                        _add_buy = buy_signal == Signal.BUY_MORE
                        _held = self._open_held('add', 'BUY' if _add_buy else 'SELL', _ask if _add_buy else _bid)
                        if _held is not None:
                            _open_hold = _held
                            if _add_buy:
                                buy_signal = Signal.DO_NOTHING
                            else:
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
                analysis_data['sizing'] = _sizing
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
                    'bot': {
                        'branch': BRANCH, 'magic': MAGIC, 'design': DESIGN_NAME,
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
                            # the last test before the send: an entry every gate above lets through
                            _open_hold = self._open_held('entry', 'BUY', _ask, sizing_known=_sizing_known)
                        if _why is None and _open_hold is None:
                            _levels = basket_levels(vol_now, _usd_per_price)   # fixed for this basket's life
                            order_response, _backstop = self._open_leg(1, trade_symbol, units * mtqty,
                                                                       _levels['stop_usd_per_unit'], _usd_per_price,
                                                                       _ask)
                            if self._order_done(order_response):
                                _t_fill = time.time()
                                state['basket'] = self._new_basket('BUY', units, _levels, _t_fill, sizing=_sizing)
                                self._record_fill(state['basket'], order_response, _t_fill)   # a leg now, listed or not
                                self._save_state(symbol, state)
                            _block_logged = None
                            # BUY_EXECUTED only for a fill; else BUY_REFUSED (and the slower retry counts it)
                            self._note_open_answer(symbol, 'BUY', order_response, {
                                'mt5_symbol': trade_symbol,
                                'qty': units * mtqty,
                                'target_usd': None if _levels['target_usd_per_unit'] is None else round(_levels['target_usd_per_unit'] * units, 2),
                                'stop_usd': None if _levels['stop_usd_per_unit'] is None else round(_levels['stop_usd_per_unit'] * units, 2),
                                'vol_unit': _levels['vol_unit'],
                                'backstop_sl': _backstop,
                                'response': str(order_response),
                            }, server_time=server_time)
                        elif _why is None:
                            if _block_logged != ('BUY', _open_hold['why']):
                                _block_logged = ('BUY', _open_hold['why'])
                                self._log_event(symbol, 'BUY_SIGNAL', 'SIGNAL', {
                                    'note': f"Entry held: {_open_hold_text(_open_hold)} — order skipped",
                                    'hold': dict(_open_hold), 'account': dict(account_info or {}),
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
                    # BUY_MORE_EXECUTED only for a fill; else BUY_MORE_REFUSED (and the slower retry counts it)
                    self._note_open_answer(symbol, 'BUY_MORE', order_response, {
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
                    self._closes_basket(_closed)    # really closed: it waits for its result (memory only)
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
                            # the last test before the send: an entry every gate above lets through
                            _open_hold = self._open_held('entry', 'SELL', _bid, sizing_known=_sizing_known)
                        if _why is None and _open_hold is None:
                            _levels = basket_levels(vol_now, _usd_per_price)   # fixed for this basket's life
                            order_response, _backstop = self._open_leg(-1, trade_symbol, units * mtqty,
                                                                       _levels['stop_usd_per_unit'], _usd_per_price,
                                                                       _bid)
                            if self._order_done(order_response):
                                _t_fill = time.time()
                                state['basket'] = self._new_basket('SELL', units, _levels, _t_fill, sizing=_sizing)
                                self._record_fill(state['basket'], order_response, _t_fill)   # a leg now, listed or not
                                self._save_state(symbol, state)
                            _block_logged = None
                            # SELL_EXECUTED only for a fill; else SELL_REFUSED (and the slower retry counts it)
                            self._note_open_answer(symbol, 'SELL', order_response, {
                                'mt5_symbol': trade_symbol,
                                'qty': units * mtqty,
                                'target_usd': None if _levels['target_usd_per_unit'] is None else round(_levels['target_usd_per_unit'] * units, 2),
                                'stop_usd': None if _levels['stop_usd_per_unit'] is None else round(_levels['stop_usd_per_unit'] * units, 2),
                                'vol_unit': _levels['vol_unit'],
                                'backstop_sl': _backstop,
                                'response': str(order_response),
                            }, server_time=server_time)
                        elif _why is None:
                            if _block_logged != ('SELL', _open_hold['why']):
                                _block_logged = ('SELL', _open_hold['why'])
                                self._log_event(symbol, 'SELL_SIGNAL', 'SIGNAL', {
                                    'note': f"Entry held: {_open_hold_text(_open_hold)} — order skipped",
                                    'hold': dict(_open_hold), 'account': dict(account_info or {}),
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
                    # SELL_MORE_EXECUTED only for a fill; else SELL_MORE_REFUSED (and the slower retry counts it)
                    self._note_open_answer(symbol, 'SELL_MORE', order_response, {
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
                    self._closes_basket(_closed)    # really closed: it waits for its result (memory only)
                    self._log_event(symbol, 'CLOSE_SELL', 'EXIT', {
                        'mt5_symbol': trade_symbol,
                        'positions_closed': close_response.get('closed_count', 0),
                        'total_profit': sell_positions['total_profit'] if sell_positions else 0,
                        'reason': analysis_data.get('exit_reason'),
                        'realised_pnl': _closed.get('pnl') if _closed else None,
                        'lost': _closed.get('lost') if _closed else None,
                        'response': close_response,
                    }, server_time=server_time)
                
                # An open this poll wanted and did not send (the trace reads the local; the old status file too)
                analysis_data['open_hold'] = _open_hold

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

                # ── When this bot first traded this account (state/live_start.json): written once, here, after the
                # order section; the trace's reporting reads start there ──
                self._note_live_start(symbol, buy_positions, sell_positions, account_info)

                # ── The safety after the orders: the cash read, the results of closed trades, its files, its
                # journal lines, the events (each step on its own; none can stop the poll) ──
                self._safety_after_orders(symbol, _open_hold, _foreign, server_time)

                # ── The trace (tracelog.py): reads this poll's locals, writes the dashboard's files and the text log ──
                self._trace(symbol, 'poll', locals())

                time.sleep(max(brake, 1))  # At least 1s between cycles

                # Check if supervisor requested shutdown (mode change)
                if self._stop_event.is_set():
                    return

            except Exception as e:
                print(f"[{symbol}] Error: {e}")
                self._trace(symbol, 'exception', 'LOOP', f'the poll failed: {_err_text(e)}; the loop goes on in 1 s')
                time.sleep(1)
                if self._stop_event.is_set():
                    return
    
    # ───────────────────── the Turtle (STRATEGY = 'turtle'; its rules are in turtle.py) ─────────────────────
    def _turtle_state_path(self, symbol):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, f'{symbol}_turtle.json')

    def _load_turtle_state(self, symbol):
        """The persisted Turtle book or None: no file, unreadable, written for another symbol / magic number /
        system, or written on another account (then it is rebuilt from the terminal). Never raises."""
        path = self._turtle_state_path(symbol)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:              # (OSError, not JSON, not text ...: loading never raises)
            print(f"[{symbol}] note: Turtle state file {path} unreadable ({e}); rebuilding it from the terminal")
            self._trace(symbol, 'state_note', 'WARN', f'the Turtle state file {path} is unreadable ({_err_text(e)}): the book is '
                        'rebuilt from the terminal')
            return None
        if (not isinstance(data, dict) or data.get('symbol') != symbol or data.get('magic') != MAGIC
                or data.get('system') != TURTLE_SYSTEM or not isinstance(data.get('book'), dict)):
            print(f"[{symbol}] note: Turtle state file {path} is not this bot's (symbol/magic/system); rebuilding it")
            self._trace(symbol, 'state_note', 'WARN', f"the Turtle state file {path} is not this bot's (symbol / magic / "
                        'system): the book is rebuilt from the terminal')
            return None
        # (written on another account: put aside, and the book is rebuilt from this bot's own positions)
        if self._other_account_file(symbol, path, data, held_trade=bool(data['book'].get('side'))):
            return None
        st = T.new_state()
        st.update({k: v for k, v in data['book'].items() if k in st})
        return st

    def _save_turtle_state(self, symbol, st):
        """Write the book atomically (a crash mid-write leaves the previous file). The account it is written on
        (_account_stamp) goes beside the book, where the file keeps its magic number: the book itself is
        turtle.py's and takes no other key."""
        path = self._turtle_state_path(symbol)
        data = {'version': _STATE_VERSION, 'symbol': symbol, 'magic': MAGIC, 'design': DESIGN_NAME,
                'system': TURTLE_SYSTEM, **self._account_stamp(), 'saved_at': time.time(), 'book': st}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with self.thread_lock:
                with open(tmp, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                _replace_retry(tmp, path)
        except OSError as e:
            print(f"[{symbol}] Error: could not write the Turtle state file {path}: {e}")
            self._trace(symbol, 'state_note', 'ERROR', f'could not write the Turtle state file {path}: {_err_text(e)} (a restart '
                        'now would rebuild the trade from the terminal)')
            return
        self._trace(symbol, 'turtle_state_saved', st)

    # What the bot keeps of the open Turtle trade beside its book: turtle.py's book takes no other key (and is not
    # this bot's to change), so the record made at the entry -- how the unit was sized -- has its own small file,
    # OUTPUT_DIR/state/<symbol>_turtle_side.json. Nothing is decided on it; the trace and the dashboard show it.
    def _turtle_side_path(self, symbol):
        base = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        return os.path.join(base, f'{symbol}_turtle_side.json')

    def _load_turtle_side(self, symbol):
        """The record of the open Turtle trade from the side file ({'entry_time', 'ticket', 'side', 'units',
        'sizing'}), or None: no file, unreadable, not this bot's (symbol / magic), written on another account (then
        the file is put aside as every state file of another account is), or no trade in it. Never raises."""
        try:
            path = self._turtle_side_path(symbol)
            with open(path, 'r') as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get('symbol') != symbol or data.get('magic') != MAGIC:
                return None
            # another account's trade: not this bot's record (the book's own file says whether a trade was open)
            if self._other_account_file(symbol, path, data):
                return None
            rec = data.get('trade')
            return rec if isinstance(rec, dict) else None
        except Exception:
            return None

    def _save_turtle_side(self, symbol, rec):
        """Write the side file atomically: `rec` the open trade's record, None once the trade has ended. With the
        account as its tail and its SHA-256 (never the number) and the branch, as every state file of a real-money
        bot. A write that fails is noted and never raised: the record only describes the trade."""
        path = self._turtle_side_path(symbol)
        try:
            data = {'version': _STATE_VERSION, 'symbol': symbol, 'magic': MAGIC, **self._account_stamp(),
                    'saved_at': time.time(), 'trade': rec}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with self.thread_lock:
                with open(tmp, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                _replace_retry(tmp, path)
        except Exception as e:
            print(f"[{symbol}] note: could not write the Turtle side file {path}: {_err_text(e)}")
            self._trace(symbol, 'state_note', 'WARN', f'could not write the Turtle side file {path}: {_err_text(e)} '
                        '(only the record of how the open trade was sized; trading is not affected)')

    @staticmethod
    def _turtle_side_record(st, sizing):
        """The side file's record of the trade the book has just opened."""
        legs = st.get('legs') or []
        first = legs[0] if legs and isinstance(legs[0], dict) else {}
        return {'entry_time': st.get('entry_time'), 'ticket': first.get('ticket'),
                'side': st.get('side'), 'units': st.get('units'),
                'sizing': dict(sizing) if isinstance(sizing, dict) else None}

    @staticmethod
    def _turtle_side_sizing(st, rec):
        """The sizing the side file's record `rec` holds for the book's open trade; None when the record is not
        that trade's (another entry time, and its first fill is not among the trade's legs)."""
        if not isinstance(rec, dict) or not st.get('side'):
            return None
        same = rec.get('entry_time') is not None and rec.get('entry_time') == st.get('entry_time')
        ticket = rec.get('ticket')
        if not same and ticket is not None:
            same = any(isinstance(leg, dict) and leg.get('ticket') == ticket for leg in st.get('legs') or [])
        return rec.get('sizing') if same else None

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
        """The unit for a new trade: the bot's rule (turtle.py unit_rule) on this bot's share of the account balance.
        (units, sizing balance, account balance); units None while the sizing balance is not known or not above 0:
        no new trade is opened then."""
        balance, account_balance = self._sizing_balance(account_info)
        if balance is None or not balance > 0:
            return None, balance, account_balance
        return T.unit_rule(balance, step_up_balance, max_limit), balance, account_balance

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
          else an add, else -- flat -- an entry (a market order; the unit from this bot's share of the account
          balance, fixed for the trade) -> the book in OUTPUT_DIR/state/<symbol>_turtle.json -> the dashboard JSON.
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
        _sizing = None                          # how the unit in effect was sized (sizing_record): the trace reads it
        _open_hold = None                       # why this poll did not send an open it wanted (_open_held), else None
        _trade_rec = self._load_turtle_side(symbol)     # the open trade's record beside the book (its sizing)
        _units_at = -1e18
        _last_daily_save = 0.0
        _last_hist_save = 0.0
        self._load_live_start(symbol)           # when this bot first traded this account (the reporting reads)
        # the safety: the closed trades still waiting for their result (and the position ids of the running trade),
        # and this bot's Tracker (built and loaded; tried again after every poll while it is not usable -- new trades
        # are blocked meanwhile while it is ON)
        self._load_closes(symbol)
        self._safety_start(symbol)
        _safety = self._safety_view             # the safety's view this poll decided on (the trace reads it)
        _safety_blocked = False                 # it blocks or holds new trades on this poll
        _foreign = None                         # what is on this symbol that is not this bot's; an old bot
        print(f"[{symbol}] {T.describe(TURTLE_SYSTEM)}")
        # the trace: the start-up block of the text log (branch, design, every constant, the book found)
        self._trace(symbol, 'loop_start', locals())

        while True:
            try:
                _iter_start = time.perf_counter()
                _open_hold = None
                _side_dirty = False                 # the side file's record changed in the order section (5.8)
                # An old bot on this server: its files' dates, looked at every 10 s on every pass -- a pass the
                # guard refuses too -- and kept as a flag (no terminal call, outside mt5_lock)
                self._old_bot_alive()
                # ── the terminal must answer and hold this bot's account, else this poll decides nothing ──
                if not self._poll_guard(symbol):
                    self._old_bot_switched_note(symbol)
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
                _ended = None                       # the trade the sync ended (the safety's losing-trades rule)
                if rows is not None and now is not None:
                    _was = (st['side'], st['entry_time'])
                    _c, hold, pending = self._turtle_sync(symbol, st, buy_positions, sell_positions, rows, rows_t,
                                                          mtqty, now, server_time)
                    if _was[0] != 0 and (st['side'] == 0 or st['entry_time'] != _was[1]):
                        _ended = _was
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
                    # an open trade keeps its unit, and the record of how it was sized
                    units = int(st['units'])
                    _sizing = open_trade_sizing(self._turtle_side_sizing(st, _trade_rec), units, step_up_balance,
                                                mtqty, max_limit)
                    _units_at = -1e18               # flat again: the unit shown is re-derived on that poll
                elif time.time() - _units_at >= 60.0:
                    _u, _sb, _ab = self._turtle_units(account_info, step_up_balance, max_limit)
                    if _u is not None:              # (not known: the unit shown stays, and it is asked again next poll)
                        units = _u
                        _units_at = time.time()
                    _sizing = sizing_record(_ab, _sb, step_up_balance, units, mtqty, max_limit,
                                            'balance' if _u is not None else 'unknown', time.time())

                # ── the safety, in memory only: the running trade's position ids (a trade the sync ended waits for
                # its result), the view for this poll, and the one flag every opening order of this poll is tested
                # against (the tests before a send, then open_guard in buy() / sell()) ──
                _listed = (buy_positions or {}).get('count', 0) + (sell_positions or {}).get('count', 0)
                self._closes_turtle(st, _listed, _ended)
                _safety = self._safety_poll(symbol, account_info)
                _safety_blocked = bool(_safety.get('blocked') or _safety.get('hold'))
                _foreign = self._foreign_now(_listed)

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
                            # the trade is over: it waits for its result with every leg it had (before the book
                            # is wiped; memory only)
                            self._turtle_close_seen(st, positions)
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
                        _rec_now = self._turtle_rec_matches(st, _trade_rec)
                        if lvl is not None and _rec_now and _trade_rec.get('adds_stopped'):
                            lvl = None              # a pyramid the safety held back ran away: no more adds (5.8)
                        if lvl is not None:
                            # the last test before the send: the one flag of this poll (the safety, an old bot on
                            # this MetaTrader 5, the slower retry after refused orders)
                            _held = self._open_held('pyramid', 'BUY' if side == 1 else 'SELL', ask if side == 1 else bid)
                            _missed = _trade_rec.get('missed_add') if _rec_now else None
                            if _held is not None:
                                _open_hold, lvl = _held, None
                                if _held['why'] in _HOLD_BLOCKS and not isinstance(_missed, dict):
                                    # held back by a block: remembered with the trade, for the first poll after it
                                    if not _rec_now:
                                        _trade_rec = self._turtle_side_record(st, None)
                                    _trade_rec['missed_add'] = {'level': T.add_level(st), 'step': st['add_step'],
                                                                'at': time.time()}
                                    _side_dirty = True
                            elif isinstance(_missed, dict):
                                # (5.8) the first poll the add may go out after a block: only while the price is not
                                # more than one add step (0.5 N of the entry) beyond its level -- one late add far
                                # beyond it would move the stop of the whole trade and end a winner early; farther
                                # than that the trade takes no more adds
                                _lvl0, _step = _missed.get('level'), _missed.get('step')
                                _beyond = (ask - _lvl0) if side == 1 else (_lvl0 - bid)
                                _trade_rec['missed_add'] = None
                                _side_dirty = True
                                if _is_number(_lvl0) and _is_number(_step) and _beyond > _step:
                                    _trade_rec['adds_stopped'] = True
                                    lvl = None
                                    self._events_due.append(('TURTLE_ADDS_STOPPED', 'SIGNAL', {
                                        'note': (f"The price ran more than one add step ({_step:g}) past the add that was "
                                                 f"held back during the block (level {_lvl0:g}, now "
                                                 f"{ask if side == 1 else bid:g}): this trade takes no more adds. Its "
                                                 "stop and its exit are as before."),
                                        'level': _lvl0, 'step': _step, 'price': ask if side == 1 else bid,
                                        'side': 'BUY' if side == 1 else 'SELL'}))
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
                                _details = {'mt5_symbol': trade_symbol, 'qty': qty, 'leg': len(st['legs']),
                                            'level': lvl, 'fill': px, 'stop': st['stop'], 'backstop_sl': backstop,
                                            'response': str(order_response)}
                            else:
                                _details = {'mt5_symbol': trade_symbol, 'qty': qty, 'level': lvl,
                                            'backstop_sl': backstop, 'response': str(order_response)}
                            # BUY_MORE_EXECUTED only for a fill; else BUY_MORE_REFUSED (the slower retry counts it)
                            self._note_open_answer(symbol, 'BUY_MORE' if side == 1 else 'SELL_MORE', order_response,
                                                   _details, server_time=server_time)
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
                            # the unit of the new trade, from this poll's account read
                            _u, _sb, _ab = self._turtle_units(account_info, step_up_balance, max_limit)
                            if _u is not None:
                                units = _u
                                _units_at = time.time()
                            _sizing = sizing_record(_ab, _sb, step_up_balance, units, mtqty, max_limit,
                                                    'balance' if _u is not None else 'unknown', time.time())
                            # the last test before the send: an entry every gate above lets through
                            _open_hold = self._open_held('entry', 'BUY' if d == 1 else 'SELL', ask if d == 1 else bid,
                                                         sizing_known=_u is not None)
                            if _open_hold is not None:
                                # held on this poll: no order, the armed orders stay armed (as under the brake)
                                self._turtle_note(symbol, 'hold_' + str(_open_hold['why']),
                                                  f'Turtle entry held: {_open_hold_text(_open_hold)}', server_time,
                                                  {'side': _open_hold['side'], 'hold': dict(_open_hold),
                                                   'account': dict(account_info or {})})
                        if d != 0 and not brake_manual and _open_hold is None:
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
                                # how this trade was sized, kept beside the book for its life (and across a restart)
                                _trade_rec = self._turtle_side_record(st, _sizing)
                                self._save_turtle_side(symbol, _trade_rec)
                                _details = {
                                    'mt5_symbol': trade_symbol, 'qty': qty, 'units': units,
                                    'account_balance': _ab, 'sizing_balance': _sb,
                                    'level': lv['buy'] if d == 1 else lv['sell'], 'fill': px, 'vote': vote,
                                    'vote_bar': _iso(vote_bar), 'n_entry': st['n_entry'], 'stop': st['stop'],
                                    'stop_origin': T.stop_origin(st), 'd1_bar': _iso(lv['bar_time']),
                                    'use20': lv['use20'], 'backstop_sl': backstop,
                                    'response': str(order_response)}
                            else:
                                _details = {'mt5_symbol': trade_symbol, 'qty': qty, 'units': units,
                                            'level': lv['buy'] if d == 1 else lv['sell'], 'vote': vote,
                                            'backstop_sl': backstop, 'response': str(order_response)}
                            # BUY_EXECUTED only for a fill; else BUY_REFUSED (it replaces the old refusal note, and
                            # the slower retry counts it)
                            self._note_open_answer(symbol, 'BUY' if d == 1 else 'SELL', order_response, _details,
                                                   server_time=server_time)
                            if d == 1:
                                buy_signal = Signal.BUY
                            else:
                                sell_signal = Signal.SELL
                            time.sleep(ORDER_COOLDOWN_SECONDS)

                # ── after the order section: a fill's position id joins the trade's (the losing-trades rule), and a
                # pyramid the order section held back during a block, or stopped (5.8), goes into the side file ──
                self._closes_turtle(st)
                if _side_dirty and _trade_rec is not None:
                    self._save_turtle_side(symbol, _trade_rec)

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
                    'sizing': _sizing, 'open_hold': _open_hold,
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
                    'bot': {'branch': BRANCH, 'magic': MAGIC, 'design': DESIGN_NAME, 'turtle_book': st},
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

                # ── the side file: the record of a trade that has ended goes (after the order section, never before).
                # Not while this bot still has positions: a trade whose book was lost is rebuilt from them (as soon as
                # the D1 bars are there), and its record is still its own ──
                if _trade_rec is not None and st['side'] == 0 and not buy_positions and not sell_positions:
                    _trade_rec = None
                    self._save_turtle_side(symbol, None)

                # ── when this bot first traded this account (state/live_start.json): written once, here, after the
                # order section; the trace's reporting reads start there ──
                self._note_live_start(symbol, buy_positions, sell_positions, account_info)

                # ── the safety after the orders: the cash read, the results of closed trades, its files, its journal
                # lines, the events (each step on its own; none can stop the poll) ──
                self._safety_after_orders(symbol, _open_hold, _foreign, server_time)

                # ── the trace (tracelog.py): reads this poll's locals, writes the dashboard's files and the text log ──
                self._trace(symbol, 'poll', locals())

                time.sleep(1)
                if self._stop_event.is_set():
                    return

            except Exception as e:
                print(f"[{symbol}] Error: {e}")
                self._trace(symbol, 'exception', 'LOOP', f'the poll failed: {_err_text(e)}; the loop goes on in 1 s')
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
        self._boot('INFO', 'START', f'job started ({self.mode} mode) on the branch {BRANCH}, design {DESIGN_NAME!r}', {
            'mode': self.mode, 'branch': BRANCH, 'design': DESIGN_NAME, 'strategy': STRATEGY, 'magic': MAGIC,
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

    # ───────────────────── one process per branch ─────────────────────
    def _process_lock_names(self):
        """The symbols this process is started for, as symbols.json spells them (one lock file each): the symbol of
        --symbol, or without one every active symbol. A symbol that file does not hold, or a file that cannot be
        read: the word the process was started with."""
        names = []
        try:
            with open(Path(__file__).parent / 'symbols.json', 'r', encoding='utf-8-sig') as f:
                cfg = json.load(f)
            for item in cfg.get('symbols', []):
                sym = item.get('symbol') if isinstance(item, dict) else None
                if not isinstance(sym, str) or not sym:
                    continue
                if self.target_symbol:
                    if sym.upper() == self.target_symbol:
                        names.append(sym)
                elif item.get('is_active', True):
                    names.append(sym)
        except Exception:
            names = []
        return names or [self.target_symbol or 'bot']

    def _take_process_lock(self):
        """
        One process per branch: an exclusive system lock, taken without waiting, on
        OUTPUT_DIR/state/<SYMBOL>.lock; the file stays open -- and locked -- until the job ends
        (_release_process_lock) or the process does. False = another process of this bot holds it (asked
        _LOCK_TRIES times, _LOCK_RETRY_S apart: a process that has just ended lets go a moment later). True = this
        process holds it now -- or the lock could not be asked at all (the folder, the file or the locking call
        failed for another reason than "held"): a warning, and the bot goes on, since a lock that cannot be asked
        must not keep a bot from its open trades.
        """
        folder = self.state_dir or os.path.join(OUTPUT_DIR, STATE_SUBDIR)
        taken = []
        for name in self._process_lock_names():
            path = os.path.join(folder, f'{_file_part(name)}.lock')
            if path in self._process_locks:
                continue
            lock, held = None, False
            try:
                os.makedirs(folder, exist_ok=True)
                lock = _ProcessLock(os.open(path, os.O_RDWR | os.O_CREAT, 0o644), path)
                for attempt in range(_LOCK_TRIES):
                    if attempt:
                        time.sleep(_LOCK_RETRY_S)
                    if _lock_fd(lock.fd):
                        held = True
                        break
            except Exception as e:
                if lock is not None:
                    lock.close()
                print(f"⚠ Could not check whether {BRANCH} already runs on this server ({_err_text(e)}): starting "
                      f"without that check. Make sure this bot runs in one window only.")
                self._boot('WARN', 'START', f'the lock file {path} could not be used ({_err_text(e)}): started '
                           'without the check that this bot runs once only')
                continue
            except BaseException:
                if lock is not None:
                    lock.close()
                raise
            if not held:
                lock.close()
                for other in taken:         # (none is kept when one of them is refused)
                    self._process_locks.pop(other).close()
                return False
            self._process_locks[path] = lock
            taken.append(path)
        return True

    def _release_process_lock(self):
        """The job is over: the lock files are closed (the system frees their locks)."""
        locks, self._process_locks = self._process_locks, {}
        for lock in locks.values():
            lock.close()

    @staticmethod
    def _same_answer(verdicts):
        """The (key, line) every start attempt ended on, when all of them ended on the same thing only the owner
        can change; else None (one of them failed another way, or found something else: it may heal by itself)."""
        if len(verdicts) < _START_ATTEMPTS or any(v is None for v in verdicts):
            return None
        if len({v[0] for v in verdicts}) != 1:
            return None
        return verdicts[-1]

    def execute_job(self):
        """
        Main Job Orchestrator.
        Initialises MT5, starts worker threads, and runs until Ctrl+C.
        The mode is the word on the command line, and this branch has one: 'live'.
        Returns True when the trading loop ran and came back. How the process should end is left in self.exit_code
        (main() exits with it), and the launcher acts on it:
          EXIT_OK           only after Ctrl+C: stopped by the owner, not started again;
          EXIT_NEEDS_OWNER  a start only the owner can put right, with one line that says what to change: another
                            mode word, a second process of this bot, a design or a deployment block that cannot
                            run, and -- when all start attempts gave the same answer -- symbols.json or the
                            credentials file, an account of another server or kind, the account's folder belonging
                            to another account. Not started again;
          EXIT_RETRY        everything else: it may heal by itself, the launcher starts the bot again after 30 s
                            (also a trading loop that came back without Ctrl+C: a bot with open trades must not
                            stay down).
        """
        self.exit_code = EXIT_RETRY
        try:
            return self._run_job()
        finally:
            self._release_process_lock()

    def _run_job(self):
        try:
            # ── This branch trades real money and has one mode: any other word ends here, before anything is read ──
            if self.mode != _MODE:
                print(f"✗ {_wrong_mode_text()}")
                self.exit_code = EXIT_NEEDS_OWNER
                self._boot('ERROR', 'START', f"mode '{self.mode}' refused. {_wrong_mode_text()}",
                           {'exit_code': self.exit_code, 'needs_owner': 'WRONG_MODE'})
                self._boot_flush()
                return False

            # ── One process per branch: a second one would send every order a second time ──
            if not self._take_process_lock():
                # (said in this window only: the log files are the running bot's)
                print(f"✗ This bot ({BRANCH}) is already running in another window on this server. This window stops.")
                self.exit_code = EXIT_NEEDS_OWNER
                return False

            # ── The design in constants.py must be one this bot can run (checked once, before connecting) ──
            _problems = design_problems()
            if _problems:
                for _p in _problems:
                    print(f"✗ Design: {_p}")
                print(f"\n✗ constants.py of {BRANCH} cannot be used (the lines above say why). It is written for "
                      f"this branch and is not edited by hand: put it back as it was pushed (in "
                      f"{self._branch_folder()}: git checkout -- constants.py, then git pull) and start again.")
                self.exit_code = EXIT_NEEDS_OWNER
                self._boot('ERROR', 'START', 'the design in constants.py is refused: ' + '; '.join(_problems),
                           {'exit_code': self.exit_code, 'needs_owner': 'DESIGN_REFUSED'})
                self._boot_flush()
                return False

            # ── Initialise (retry up to 3 times) ──
            _held = []                       # each failed attempt: refused on a problem _log_limited held back?
            _verdicts = []                   # each failed attempt: what only the owner can change, or None
            self._owner_said = None
            for _attempt in range(1, _START_ATTEMPTS + 1):
                self._init_problem = None    # (this attempt's own problem only)
                self._owner_verdict = None
                if self._init_cycle():
                    break
                _held.append(self._start_held_back())
                _verdicts.append(self._owner_verdict)
                print(f"\n⚠ Init attempt {_attempt}/{_START_ATTEMPTS} failed, retrying in {_START_RETRY_S:g}s...")
                self._boot('WARN', 'START', f'start attempt {_attempt}/{_START_ATTEMPTS} failed '
                           f'({self._init_problem or "see above"})')
                time.sleep(_START_RETRY_S)
            else:
                _owner = self._same_answer(_verdicts)
                if _owner is not None:
                    # the same answer every time, and one that starting again cannot change
                    _key, _line = _owner
                    print(f"\n✗ {BRANCH} cannot start, and starting it again will not change that. What to change:")
                    print(f"✗ {_line}")
                    self.exit_code = EXIT_NEEDS_OWNER
                    self._boot('ERROR', 'START', f'all {_START_ATTEMPTS} start attempts failed with the same answer, '
                               f'which only the owner can change: {_line}',
                               {'exit_code': self.exit_code, 'needs_owner': _key})
                    self._boot_flush()
                    return False
                print("\n✗ All init attempts failed: the launcher starts the bot again in 30 seconds.")
                self._boot('ERROR', 'START', f'all {_START_ATTEMPTS} start attempts failed '
                           f'({self._init_problem or "see above"}): the job ends (the launcher starts it again in 30 '
                           'seconds)', {'exit_code': self.exit_code})
                self._boot_flush(held_back=all(_held))
                return False

            # ── Run processing (blocks until Ctrl+C) ──
            self.run_multithreaded_processing()

            # The trading loop came back without Ctrl+C. Nothing is meant to end it, so this is not "stopped by
            # the owner": the launcher starts the bot again (a bot with open trades must not stay down).
            self.cleanup()
            print(f"\n{'#'*60}")
            print(f"#  THE TRADING LOOP ENDED BY ITSELF - the launcher starts the bot again in 30 seconds")
            print(f"{'#'*60}\n")
            self._boot('ERROR', 'START', 'the trading loop ended by itself: the job ends (the launcher starts it again '
                       'in 30 seconds)', {'exit_code': self.exit_code})
            return True

        except KeyboardInterrupt:
            print("\n\n⚠ Job interrupted by user")
            self._boot('WARN', 'START', 'job stopped by the user (Ctrl+C)')
            self._boot_flush()
            self._stop_event.set()
            self.cleanup()
            self.exit_code = EXIT_OK             # stopped by the owner: the launcher must not start it again
            return False
        except Exception as e:
            print(f"\n✗ Job Failed with exception: {e}")
            self.exit_code = EXIT_RETRY
            self._boot('ERROR', 'START', f'the job failed: {_err_text(e)}', {'exit_code': self.exit_code}, exc=True)
            self._boot_flush()
            self._stop_event.set()
            self.cleanup()
            return False


def _console_quick_edit_off():
    """
    Windows: QuickEdit off in the bot's console window (safety.quick_edit_off). With it on, one click into the window
    starts a selection and every write to the console waits until Esc is pressed: the bot prints on every poll, so
    its loop -- stops, targets and closes too -- would stand still. Says in the window whether it worked and returns
    (that line, True / False) for the bot's log; None elsewhere (nothing to do). Never raises.
    """
    try:
        said = safety.quick_edit_off()
        if said is None:
            return None
        ok, why = said
        if ok:
            text = 'QuickEdit is off in this window: a click inside it can no longer pause the bot.'
        else:
            text = (f'QuickEdit could not be switched off in this window ({why}). Do not click inside this window: '
                    'a click pauses the bot, its stops and closes too, until Esc is pressed (the title of the window '
                    'then starts with "Select").')
        print(f"{'✓' if ok else '⚠'} {text}")
        return text, bool(ok)
    except Exception:
        return None


def main():
    """
    Main entry point for the application
    
    Usage:
        app.py live --symbol SYMBOL      # Run a SINGLE symbol only (how start_job.bat starts the bot)
        app.py live                      # Run all active symbols (legacy)
    
    Running one symbol per process avoids MT5 threading issues
    where SHA candle data can overlap between symbols.

    This branch trades real money and has one mode: the word must be `live`. Anything else -- no word at all, the
    old `demo` -- prints how to start it and ends with EXIT_NEEDS_OWNER, so the launcher does not start it again.
    The process ends with the bot's exit_code (execute_job): 0 after Ctrl+C, EXIT_NEEDS_OWNER when only the owner
    can put the start right, 1 for everything that may heal by itself.
    """
    # First of all (Windows): a click into this window must not pause the bot (_console_quick_edit_off)
    console = _console_quick_edit_off()

    import argparse

    parser = argparse.ArgumentParser(description='Alcadeias Trading Bot')
    # (no `choices` for the mode: argparse would answer a wrong word with its own text and exit code 2)
    parser.add_argument('mode', nargs='?', default=None,
                        help="must be 'live': this branch trades real money")
    parser.add_argument('--symbol', '-s', type=str, default=None,
                        help='Run only this symbol (e.g. BTCUSDm). '
                             'Recommended: run one process per symbol.')
    args = parser.parse_args()
    if str(args.mode or '').strip().lower() != _MODE:
        print(_wrong_mode_text())
        sys.exit(EXIT_NEEDS_OWNER)

    # Create bot instance and execute job
    bot = MT5TradingBot(mode=_MODE, target_symbol=args.symbol)
    if console is not None:
        bot._boot('INFO', 'START', console[0], {'quick_edit_off': console[1]})
    bot.execute_job()

    # Exit with the code the launcher reads
    sys.exit(bot.exit_code)


if '__main__' == __name__:
    main()