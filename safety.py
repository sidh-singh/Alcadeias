"""
The auto-safety of a real-money account, and the small helpers every part of the bot shares.

Standard library only: the bot (app.py), the trace (tracelog.py) and the dashboard (dashboard.py, which runs in
its own Python environment with only dash and plotly) all import this file. It never imports MetaTrader5 and
never imports constants at module level; time, folders and limits are passed in.

The parts, in this order:
  1. the shared helpers (account_dir, mask_login, login_sha, quick_edit_off);
  2. the words the owner reads: dates, money, and the sentences of every state of the safety;
  3. the rules, as functions of a state and the inputs of one poll (decide, count_trade, note_other, build_view):
     no file and no clock, so every rule can be tested by itself;
  4. the files of the account folder: how each one is read and written while two bots, two dashboards and a
     command line use the folder at the same time;
  5. Tracker: one per bot, the file shell around the rules;
  6. press: what a button or the command line may change; main: the command line (safety.bat).

What the safety does. Three rules watch the booked balance of the account (closed trades only):
  - drop from the high (account): the balance is X% or more below its highest balance since counting started;
  - loss today (account): the balance is Y% or more below the balance at 00:00 UTC;
  - losing trades in a row (this bot): this bot closed N trades in a row with a net loss.
A met rule blocks: the bot opens nothing new (no entry, no ladder add, no pyramid). Its open trades keep their
normal management. A block never ends by itself: the owner unblocks it (the dashboard with the PIN, or safety.bat
on the server). With the safety OFF nothing blocks and the bots trade exactly as the strategy says.

Every time in this file is seconds since 1970, UTC, and is passed in as `now`: the module reads no clock (only
main(), the command line, does).
"""
import hashlib
import hmac
import json
import math
import ntpath
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone


# ───────────────────────── shared helpers ─────────────────────────

def account_dir(output_dir, folder):
    """
    The account's shared folder: beside the bot's own folder, C:\\Alcadeias\\live<n>_account on the server.
    The two bots and the two dashboards of one account meet there (the safety files).

    Windows rules when `output_dir` is a Windows path (a drive letter or a backslash), whatever system this runs
    on: the raw constant then gives the real server folder on a Mac too, where the tests' write guard refuses
    it, instead of a folder in the working directory. Any other path: the system's own rules, so a bot whose
    OUTPUT_DIR is <a private tmp folder>/bot_output has its account folder in that private folder.
    """
    out = str(output_dir)
    drive, _ = ntpath.splitdrive(out)
    if drive or '\\' in out:
        return ntpath.join(ntpath.dirname(ntpath.normpath(out)), str(folder))
    return os.path.join(os.path.dirname(os.path.normpath(out)), str(folder))


def _login_int(login):
    """The account number as a whole number: a JSON whole number or a string of digits; anything else: None."""
    if isinstance(login, bool):
        return None
    if isinstance(login, int):
        return login if login >= 0 else None
    if isinstance(login, str):
        s = login.strip()
        if s.isascii() and s.isdigit():
            return int(s)
    return None


def mask_login(login):
    """'...1234': the only form of the account number that goes into a file or onto a page."""
    n = _login_int(login)
    if n is None:
        return '...?'
    return '...' + str(n)[-4:]


def login_sha(login):
    """What a file stores to recognise the account without holding its number: SHA-256 (hex) of the number as
    text. None when `login` is not an account number."""
    n = _login_int(login)
    if n is None:
        return None
    return hashlib.sha256(str(n).encode('ascii')).hexdigest()


# The console window of a bot or a dashboard on Windows: with QuickEdit on (the default of Windows Server), one
# click into the window starts a selection, and from then on every write to that console waits until Esc, Enter or
# a right click. The bot prints on every poll, so its loop -- its stops and closes too -- would stand still.
_STD_INPUT_HANDLE = -10
_ENABLE_QUICK_EDIT_MODE = 0x0040
_ENABLE_EXTENDED_FLAGS = 0x0080              # (must be set for a change of QuickEdit to count)


def quick_edit_off(kernel32=None):
    """
    Windows only: switch QuickEdit off in the console window this process runs in, so that a click into the window
    cannot pause the program. Returns None where there is nothing to do (not Windows), else (True, None) when
    QuickEdit is off now, or (False, why) when it could not be switched off. `kernel32` stands in for
    ctypes.windll.kernel32 (a test gives its own; then it runs on any system). Never raises: a start must never
    stop on it.
    """
    try:
        if kernel32 is None and os.name != 'nt':
            return None
        import ctypes
        if kernel32 is None:
            kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
        if handle is None or handle in (0, -1):
            return False, 'the window has no console input'
        mode = ctypes.c_uint32(0)
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False, 'the mode of the console could not be read'
        if not kernel32.SetConsoleMode(handle, (mode.value | _ENABLE_EXTENDED_FLAGS) & ~_ENABLE_QUICK_EDIT_MODE):
            return False, 'the mode of the console could not be changed'
        return True, None
    except Exception as e:                           # (anything at all: the program starts as it would without it)
        return False, f'{type(e).__name__}: {e}'


# ───────────────────────── the files of the safety, and its fixed numbers ─────────────────────────
# Account folder (shared by the two bots and the two dashboards of one account):
SWITCH_FILE = 'safety_switch.json'        # ON / OFF                          written by press
RESTART_FILE = 'safety_restart.json'      # the id counting last started with written by press
PIN_FILE = 'safety_pin.txt'               # the PIN of the buttons            written by ensure_pin, or the owner
AUDIT_FILE = 'safety_audit.jsonl'         # who pressed what, every block     appended by press and the bots
LOCKOUT_FILE = 'safety_lockout.json'      # wrong PINs and the button lock    written by press
CLAIM_FILE = 'account_claim.json'         # the account of this folder (app.py's file; press only deletes it)
# and per fresh-start id safety_block_<id>.json (the bot that met a limit first), per bot
# safety_status_<branch>.json (that bot). Bot folder: state/safety_state.json (that bot).

FIRST_ID = 'start'                        # the id while nobody has pressed Unblock or ON yet

CONFIRM_S = 3.0             # a balance change counts once the cash history was read this long after it
BASELINE_MARGIN_S = 2.0     # a cash operation dated up to this long after a fresh start is inside its starting balance
CASH_WAIT_S = 60.0          # a fall whose cash history cannot be read is taken as a loss after this long
ERROR_AFTER_S = 60.0        # a state or block file that cannot be written for this long: "the safety check failed"
STUCK_AFTER_S = 600.0       # a balance change that cannot be judged for this long (no cash history): the same
STATUS_EVERY_S = 20.0       # a bot rewrites its status file at least this often (a reader calls 60 s old "stopped")
PARTNER_STALE_S = 60.0      # the other bot's status file older than this: not running
RETRY_S = 5.0               # a file write that failed is tried again this often, not on every poll
KEEP_TRADES = 500           # the newest closed trades a bot remembers it has counted
HOLD_NOTE_S = 10.0          # a wait longer than this is worth a line in the journal

_LOCK_START_S = 600.0       # 5 wrong PINs lock the buttons for 10 minutes,
_LOCK_MAX_S = 86400.0       # twice as long each further time, up to 24 hours;
_WRONG_MAX = 5
_QUIET_RESET_S = 86400.0    # 24 hours without a wrong PIN: the next lock is 10 minutes again
_REFUSED_LINES_AN_HOUR = 20  # refused presses written to the audit file per hour; the rest is counted only
_BOT_LINES_AN_HOUR = 30     # audit lines one bot writes per hour (a guard against a loop, far above real use)

STATE_VERSION = 1

_ID_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')      # what a fresh-start id may look like (a file name part)
_NAME_BAD = re.compile(r'[^A-Za-z0-9_.-]')                      # everything a file name of this module never holds
_TMP_NAME = re.compile(r'^safety_[A-Za-z0-9_.-]+\.json\.\d+\.[0-9a-f]{8}\.tmp$')

# press() is called from the dashboard's request threads: one press at a time (the PIN counter must not be
# outrun by parallel requests). The only module-level state of this file.
_PRESS_LOCK = threading.Lock()


def _file_part(text):
    """`text` as part of a file name: letters, digits, '_', '-' and '.' only (Windows refuses < > : " / \\ | ? *)."""
    return _NAME_BAD.sub('_', str(text)) or '_'


def block_path(account_dir, restart_id):
    """The block file of one fresh-start id: it exists = the account is blocked for that id."""
    return os.path.join(str(account_dir), f'safety_block_{_file_part(restart_id)}.json')


def status_path(account_dir, branch):
    """The status file of one bot."""
    return os.path.join(str(account_dir), f'safety_status_{_file_part(branch)}.json')


def pin_path(account_dir):
    """Where the PIN of the buttons is kept (the dashboard shows this path, never the PIN)."""
    return os.path.join(str(account_dir), PIN_FILE)


# ───────────────────────── numbers, dates and money as the owner reads them ─────────────────────────

_T0 = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _num(x):
    """`x` as a float when it is a usable number (not True / False, not NaN, not infinite), else None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _utc(t):
    """Seconds since 1970 as a UTC datetime, by plain arithmetic (no call that depends on the system); None when
    `t` is not a usable time."""
    n = _num(t)
    if n is None:
        return None
    try:
        return _T0 + timedelta(seconds=n)
    except OverflowError:
        return None


def _day_key(t):
    """The UTC day of a time, 'YYYY-MM-DD' (how the state names a day)."""
    d = _utc(t)
    return None if d is None else f'{d.year:04d}-{d.month:02d}-{d.day:02d}'


def _iso(t):
    d = _utc(t)
    return None if d is None else f'{d.year:04d}-{d.month:02d}-{d.day:02d}T{d.hour:02d}:{d.minute:02d}:{d.second:02d}Z'


def _name_stamp(t):
    """A time as part of a file name: yyyymmdd_hhmmss, UTC (no colon: Windows refuses it)."""
    d = _utc(t) or _T0
    return f'{d.year:04d}{d.month:02d}{d.day:02d}_{d.hour:02d}{d.minute:02d}{d.second:02d}'


def _day_text(t):
    """'21 Nov'."""
    d = _utc(t)
    return 'an unknown day' if d is None else f'{d.day} {_MONTHS[d.month - 1]}'


def _clock(t, seconds=False):
    """'14:05' (or '14:07:10'), UTC."""
    d = _utc(t)
    if d is None:
        return 'an unknown time'
    return f'{d.hour:02d}:{d.minute:02d}:{d.second:02d}' if seconds else f'{d.hour:02d}:{d.minute:02d}'


def _stamp(t):
    """'21 Nov 14:05', UTC."""
    return 'an unknown time' if _utc(t) is None else f'{_day_text(t)} {_clock(t)}'


def _day_key_text(key):
    """'2026-11-21' -> '21 Nov'."""
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', str(key or ''))
    if not m or not 1 <= int(m.group(2)) <= 12:
        return 'that day'
    return f'{int(m.group(3))} {_MONTHS[int(m.group(2)) - 1]}'


def _day_key_start(key):
    """'2026-11-21' -> the time of its 00:00 UTC; None when it is not a day."""
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', str(key or ''))
    try:
        return (datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc) - _T0).total_seconds()
    except (AttributeError, ValueError, OverflowError):
        return None


def _money(x):
    """'$1,194.00'."""
    n = _num(x)
    if n is None:
        return 'an unknown amount'
    n = round(n, 2)
    return ('-' if n < 0 else '') + f'${abs(n):,.2f}'


def _pct(x):
    """'20.4%'."""
    n = _num(x)
    return 'an unknown share' if n is None else f'{n:.1f}%'


def _plain(x):
    """A limit without needless zeros: 20.0 -> '20', 12.5 -> '12.5'."""
    n = _num(x)
    return '?' if n is None else f'{n:g}'


def _length(seconds):
    """How long, in words: '10 minutes', '1 minute', '2 hours 40 minutes', '24 hours', '45 seconds'."""
    s = int(round(_num(seconds) or 0))
    if s < 60 or s % 60:
        if s < 120:
            return f'{s} second' + ('' if s == 1 else 's')
        s = int(round(s / 60.0)) * 60
    hours, minutes = divmod(s // 60, 60)
    parts = []
    if hours:
        parts.append(f'{hours} hour' + ('' if hours == 1 else 's'))
    if minutes or not parts:
        parts.append(f'{minutes} minute' + ('' if minutes == 1 else 's'))
    return ' '.join(parts)


def _ago(seconds):
    """An age in words: '3 seconds', '5 minutes', '2 hours', '4 days'."""
    s = max(0.0, _num(seconds) or 0.0)
    if s < 120:
        return f'{int(s)} second' + ('' if int(s) == 1 else 's')
    if s < 7200:
        return f'{int(s // 60)} minutes'
    if s < 172800:
        return f'{int(s // 3600)} hours'
    return f'{int(s // 86400)} days'


def _market(branch):
    """'gold' or 'BTC' from the branch name: the letter after its underscore (live1_xt2 -> x -> gold,
    live1_bt2 -> b -> BTC). None for any other name."""
    _, sep, tail = str(branch or '').partition('_')
    return {'x': 'gold', 'b': 'BTC'}.get(tail[:1].lower()) if sep else None


def _bot(branch, other=False):
    """'the gold bot' / 'the BTC bot'; a branch name that does not say which: 'this bot' ('the other bot')."""
    m = _market(branch)
    if m:
        return f'the {m} bot'
    return 'the other bot' if other else 'this bot'


def _cap(text):
    return text[:1].upper() + text[1:]


# ───────────────────────── the sentences of every state ─────────────────────────
# One place for every sentence the safety shows, so the dashboard, the status file, the block file and the
# command line say the same thing. Dates are '21 Nov 14:05' (UTC), money '$1,194.00', the account its tail.

ERROR_SENTENCE = 'The safety check failed: no new trades until it works again or the safety is turned OFF.'


def _say_watching(tail):
    return f'Watching account {tail}. New trades are allowed.'


def _say_off(tail):
    return (f'No limit is applied: both bots of account {tail} trade exactly as the strategy says. '
            'The meters are for information only.')


def _say_checking(since, wait_s):
    return (f'A limit was reached at {_clock(since)}. Checking that it is a loss and not a withdrawal '
            f'(up to {_length(wait_s)}). No new trade until then.')


def _say_waiting(branch, waiting, count, limit):
    trades = 'its last closed trade' if waiting == 1 else f'its last {waiting} closed trades'
    loss = 'it is a loss' if waiting == 1 else 'they are losses'
    return (f'{_cap(_bot(branch))} waits for the result of {trades}. If {loss}, it has lost {count + waiting} '
            f'trades in a row (limit {limit}). No new trade until the result is known.')


def _say_account_blocked(since):
    when = '' if since is None else f' since {_stamp(since)}'
    return (f'Both bots open no new trade and add nothing to open trades{when}. Open trades keep their stop and '
            'target. Press Unblock to trade again.')


def block_sentences(rules, numbers):
    """Why the account is blocked: one sentence per rule that was met, with the numbers taken at that moment.
    They go into the block file, so both dashboards show the same reason."""
    n = numbers if isinstance(numbers, dict) else {}
    out = []
    balance = _money(n.get('balance'))
    for rule in rules or ():
        if rule == 'DROP':
            high_day = '' if _utc(n.get('peak_at')) is None else f" on {_day_text(n.get('peak_at'))}"
            out.append(f"The account fell {_pct(n.get('drop_pct'))} below its high (limit "
                       f"{_plain(n.get('drop_limit'))}%): balance {balance}, high {_money(n.get('peak'))}{high_day}.")
        elif rule == 'DAY':
            taken_at, midnight = _num(n.get('day0_at')), _day_key_start(n.get('day'))
            if n.get('day_since') == 'restart' and taken_at is not None:
                start = f"{_money(n.get('day0'))} when counting started that day at {_clock(taken_at)}"
            elif taken_at is not None and midnight is not None and taken_at - midnight > 300.0:
                # (the bot was not running at 00:00: its day starts with the first balance it saw)
                start = f"{_money(n.get('day0'))} at {_clock(taken_at)}, the first balance this bot saw that day"
            else:
                start = f"{_money(n.get('day0'))} at the start of that day"
            out.append(f"The account lost {_pct(n.get('day_pct'))} on {_day_key_text(n.get('day'))}, UTC day (limit "
                       f"{_plain(n.get('day_limit'))}%): balance {balance}, {start}.")
    return out


def _say_seen_by(branch):
    return f'{_cap(_bot(branch))} ({branch}) saw it.' if branch else None


def _say_bot_blocked(branch, block, partner_note):
    """The sentence of a block of this bot alone (losing trades in a row, or another program in its market)."""
    since = block.get('at')
    when = '' if since is None else f' since {_stamp(since)}'
    head = f'{_cap(_bot(branch))} opens no new trade{when}: '
    if block.get('rule') == 'OTHER_PROGRAM':
        what = _market(branch) or 'its market'
        detail = str(block.get('text') or '').strip()
        return (head + f'another program is trading {what} in this account' + (f' ({detail})' if detail else '')
                + '. If the old ladder bot still runs on this account, stop it, then press Unblock.')
    detail = str(block.get('text') or '').strip() or 'it lost too many trades in a row'
    return head + f'{detail}. Its open trade keeps its stop and target.' + (f' {partner_note}' if partner_note else '')


def _streak_text(count, limit):
    return f"it lost {count} trade{'' if count == 1 else 's'} in a row (limit {limit})"


# ───────────────────────── the limits ─────────────────────────

def _limit_pct(value, name):
    if value is None:
        return None
    n = _num(value)
    if n is None or n < 0:
        raise ValueError(f'{name} must be a percentage above 0, or None / 0 for "this rule is off": {value!r}')
    return n or None


def _limit_count(value, name):
    if value is None:
        return None
    n = _num(value)
    if n is None or n < 0 or n != int(n):
        raise ValueError(f'{name} must be a whole number above 0, or None / 0 for "this rule is off": {value!r}')
    return int(n) or None


class Limits:
    """
    The three limits of one bot: `drop_pct` (the account's drop from its high, in percent), `day_pct` (the
    account's loss in one UTC day, in percent) and `streak_n` (this bot's losing trades in a row).
    None or 0 = that rule is off. A value that is not a number is refused here (ValueError): a mistyped limit must
    not switch a rule off without anybody noticing.
    """

    def __init__(self, drop_pct=None, day_pct=None, streak_n=None):
        self.drop_pct = _limit_pct(drop_pct, 'drop_pct')
        self.day_pct = _limit_pct(day_pct, 'day_pct')
        self.streak_n = _limit_count(streak_n, 'streak_n')

    def as_dict(self):
        return {'drop_pct': self.drop_pct, 'day_pct': self.day_pct, 'streak_n': self.streak_n}

    def __eq__(self, other):
        return isinstance(other, Limits) and self.as_dict() == other.as_dict()

    def __repr__(self):
        return f'Limits(drop_pct={self.drop_pct!r}, day_pct={self.day_pct!r}, streak_n={self.streak_n!r})'


def _as_limits(limits):
    if isinstance(limits, Limits):
        return limits
    if limits is None:
        return Limits()
    if isinstance(limits, dict):
        return Limits(limits.get('drop_pct'), limits.get('day_pct'), limits.get('streak_n'))
    return Limits(*limits)


# ───────────────────────── the rules: a state and the inputs of one poll, no file, no clock ─────────────────────────

def new_state(branch=None, sha=None):
    """The state of a bot that has counted nothing yet (see the spec, 5.4, for every field)."""
    return {
        'version': STATE_VERSION, 'login_sha': sha, 'branch': branch,
        'period': None,               # the fresh-start id this bot counts under (None: it never started)
        'account_period': None,       # the id of the last start that reset the account's figures (see decide, step 1)
        'started_at': None,           # when counting started
        'peak': None, 'peak_at': None,                      # the high, and when the balance reached it
        'day': None, 'day0': None, 'day0_at': None, 'day_since': None,       # the day rule counts from day0
        'day_start_balance': None, 'day_start_at': None, 'day_cash': 0.0,    # the day's own start (for "today +$12")
        'streak': 0,                  # this bot's losing trades in a row
        'bot_block': None, 'account_block': None,
        'settled_balance': None, 'settled_at': None,        # the last balance the rules have judged
        'change_first': None, 'change_last': None, 'seen_balance': None,     # a balance change still being checked
        'cash_seen': {}, 'cash_baseline_done': False, 'cash_read_ok_at': None,
        'counted_trades': [],
        'enabled_last': None, 'block_exists_last': None, 'fresh_pending': False,
    }


def _cents(x):
    return int(round(x * 100.0))


def _pct_below(reference, balance):
    """How far `balance` is below `reference`, in percent; 0 when it is above, or when there is nothing to
    compare with yet (an account that was never funded has a high of 0)."""
    if reference is None or balance is None or not reference > 0:
        return 0.0
    return max(0.0, (reference - balance) / reference * 100.0)


def _met(pct, limit):
    """A limit is met at the limit itself. Rounded to 6 places first: 12094.30 -> 10884.87 is a 10% loss, but
    floating point makes it 9.999999999999988."""
    return limit is not None and round(pct, 6) >= limit


def _clean_deals(cash_deals):
    """The balance operations of one read as (ticket, amount, time), oldest first; anything that is not one is
    left out (a deal without a ticket is known by its time and amount)."""
    out = []
    for d in cash_deals or ():
        if not isinstance(d, dict):
            continue
        amount = _num(d.get('amount'))
        if amount is None:
            continue
        when = _num(d.get('time'))
        ticket = d.get('ticket')
        if isinstance(ticket, bool) or ticket is None or ticket == '':
            key = f'{when}:{amount}'
        elif isinstance(ticket, float) and ticket == int(ticket):
            key = str(int(ticket))
        else:
            key = str(ticket)
        out.append((key, amount, when))
    out.sort(key=lambda x: (x[2] is None, x[2] or 0.0, x[0]))
    return out


def _pruned_cash(seen, read_ok_at):
    """Tickets no later read can return again are forgotten (reads start an hour before the last good one), so
    the list stays short however long the account lives."""
    if len(seen) <= 200:
        return seen
    edge = None if read_ok_at is None else read_ok_at - 3600.0 - 86400.0
    kept = {k: t for k, t in seen.items() if edge is None or t is None or t >= edge}
    if len(kept) > 2000:
        newest = sorted(kept.items(), key=lambda kv: (kv[1] is not None, kv[1] or 0.0))[-2000:]
        kept = dict(newest)
    return kept


def _complete_fresh(s, now, balance, today):
    """Counting starts (again) from this balance: the high and the day rule both start here."""
    if s.get('day') != today or s.get('day_start_balance') is None:
        # (the day's own start is not touched by a fresh start, unless the day itself is new)
        s['day_start_balance'], s['day_start_at'], s['day_cash'] = balance, now, 0.0
    s['peak'] = s['day0'] = s['settled_balance'] = s['seen_balance'] = balance
    s['day'], s['day_since'] = today, 'restart'
    s['started_at'] = s['peak_at'] = s['day0_at'] = s['settled_at'] = now
    # The deposits of before are inside this balance: the first cash read after this only marks them as seen.
    s['cash_seen'], s['cash_baseline_done'], s['cash_read_ok_at'] = {}, False, None
    s['change_first'] = s['change_last'] = None
    s['fresh_pending'] = False


def _roll_day(s, now, balance, today):
    """A new UTC day: the day rule counts from the balance of now."""
    s['day'], s['day_since'] = today, 'midnight'
    s['day0'] = s['day_start_balance'] = balance
    s['day0_at'] = s['day_start_at'] = now
    s['day_cash'] = 0.0


def _apply_cash(s, deals, balance, now, read_at, change_first, events):
    """
    Deposits and withdrawals must not look like profit or loss. Each balance operation not seen before scales the
    high and the day's reference by the same factor as the balance, so the percentages do not move: with b0 = the
    balance before it, f = (b0 + amount) / b0. b0 starts at the last judged balance and moves on with each
    operation, oldest first.

    An operation dated at or before the last judged balance is inside that balance already (its history line
    arrived late): it is only remembered. Scaling for it now would count a deposit twice.
    """
    seen = dict(s.get('cash_seen') or {})
    b0 = s['settled_balance']
    edge = s.get('settled_at')
    late_by = None if (change_first is None or read_at is None) else round(read_at - change_first, 3)
    for key, amount, when in deals:
        if key in seen:
            continue
        seen[key] = when
        counted = not (when is None or (edge is not None and when <= edge))
        if counted and amount != 0:
            if b0 > 0 and b0 + amount > 0 and s.get('peak') is not None and s.get('day0') is not None:
                f = (b0 + amount) / b0
                s['peak'], s['day0'] = s['peak'] * f, s['day0'] * f
            else:
                # (an account that was empty, or is emptied: there is nothing to scale)
                s['peak'] = s['day0'] = balance
                s['peak_at'] = s['day0_at'] = now
            s['day_start_balance'] = (s.get('day_start_balance') or 0.0) + amount
            s['day_cash'] = (s.get('day_cash') or 0.0) + amount
            b0 += amount
        events.append({'event': 'cash', 'ticket': key, 'amount': amount, 'time': when, 'counted': counted,
                       'found_after_s': late_by, 'at': now})
    s['cash_seen'] = _pruned_cash(seen, s.get('cash_read_ok_at'))


def _account_trip(s, limits, now):
    """The account rules on the balance just judged: None, or the block (which rules, and the numbers of now)."""
    balance = s['settled_balance']
    drop = _pct_below(s.get('peak'), balance)
    day = _pct_below(s.get('day0'), balance)
    rules = [name for name, pct, limit in (('DROP', drop, limits.drop_pct), ('DAY', day, limits.day_pct))
             if _met(pct, limit)]
    if not rules:
        return None
    return {'period': s['period'], 'rules': rules, 'at': now,
            'numbers': {'balance': balance, 'peak': s.get('peak'), 'peak_at': s.get('peak_at'), 'drop_pct': drop,
                        'drop_limit': limits.drop_pct, 'day': s.get('day'), 'day0': s.get('day0'),
                        'day0_at': s.get('day0_at'), 'day_since': s.get('day_since'), 'day_pct': day,
                        'day_limit': limits.day_pct}}


def _bot_rule(s, limits, enabled, now, events):
    """Rule 11: N losing trades in a row block this bot (not while the safety is OFF)."""
    if enabled and s.get('bot_block') is None and limits.streak_n and s.get('streak', 0) >= limits.streak_n:
        s['bot_block'] = {'rule': 'STREAK', 'text': _streak_text(s['streak'], limits.streak_n),
                          'count': s['streak'], 'limit': limits.streak_n, 'at': now}
        events.append({'event': 'trip', 'scope': 'bot', 'rule': 'STREAK', 'count': s['streak'],
                       'limit': limits.streak_n, 'id': s.get('period'), 'at': now})


def _block_file_known(state, controls):
    """Does the block file of the id this state counts under exist, as far as anybody could tell: what the last
    look at the folder found; when the folder could not be asked, the answer of before (it is part of the state)."""
    c = controls or {}
    known = c.get('block_exists') if c.get('block_id') == state.get('period') else None
    if known is None:
        known = state.get('block_exists_last')
    return known is True


def account_blocked(state, controls):
    """Is the account blocked for the id this state counts under: its block file exists, or this bot met an
    account limit itself (its state says so, whether or not the file could be written)."""
    own = state.get('account_block')
    return _block_file_known(state, controls) or (isinstance(own, dict) and own.get('period') == state.get('period'))


def decide(state, limits, now, balance=None, cash_deals=None, cash_read_at=None, pending_results=0, controls=None,
           confirm_s=CONFIRM_S, cash_wait_s=CASH_WAIT_S):
    """
    One poll of the safety (the spec, 5.5): returns (the new state, what came of it). `state` is not changed.

    `controls` is what the folder said at the last look: {'restart_status': 'ok' (the restart file was read) /
    'missing' / None (it could not be read), 'restart_id', 'restart_scope', 'restart_account_id', 'enabled',
    'block_id', 'block_exists' (True / False / None = could not tell), 'watching_since' (when this process
    started to look at the balance; None = always)}.

    The second value: {'events': [...], 'enabled', 'account_blocked', 'tripped' (this poll met an account limit:
    the block file is to be created), 'settled', 'pending', 'hold', 'hold_why' ('limit' / 'results'),
    'hold_since', 'waiting'}.
    """
    s = dict(state)
    c = controls or {}
    limits = _as_limits(limits)
    now = float(now)
    today = _day_key(now)
    events = []
    enabled = c.get('enabled')
    enabled = True if not isinstance(enabled, bool) else enabled

    # 1. A fresh start: the restart file was READ and names another id than the one this bot counts under.
    #    (A file that is missing or cannot be read never starts anything: a block must not end by a lost file.)
    read_ok = c.get('restart_status') == 'ok' and isinstance(c.get('restart_id'), str)
    rid = c.get('restart_id') if read_ok else None
    scope = c.get('restart_scope')
    acct_id = c.get('restart_account_id') if isinstance(c.get('restart_account_id'), str) else None
    judge_again = False
    if s.get('period') is None:
        # The first start: the same as a fresh start of the whole account, taken with the first balance.
        s['period'] = rid or FIRST_ID
        s['account_period'] = (acct_id or (rid if scope != 'bot' else None)) if rid else FIRST_ID
        s['fresh_pending'] = True
    elif rid is not None and rid != s['period']:
        # A bot that was stopped can miss a press. The restart file therefore also names the id of the last
        # start that reset the account's figures: a bot that has not taken that one takes it now, even when the
        # newest press only unblocked a bot.
        missed = acct_id is not None and acct_id != s.get('account_period')
        if scope == 'bot' and not missed:
            # Unblock of one bot: its count goes back to 0. The high, the day and the other bot stay.
            was_blocked = s.get('account_block') is not None or bool(s.get('block_exists_last'))
            s['period'] = rid
            if s.get('bot_block') is not None:
                s['streak'], s['bot_block'] = 0, None
            s['account_block'], s['block_exists_last'] = None, None
            # (An account limit met in the same instant as that press belonged to the old id. The figures did
            # not change, so the rules are judged again below and the block is made anew under the new id.)
            judge_again = was_blocked
            events.append({'event': 'fresh_start', 'scope': 'bot', 'id': rid, 'at': now})
        else:
            s['period'] = rid
            s['account_period'] = acct_id or rid
            s['streak'], s['bot_block'], s['account_block'], s['block_exists_last'] = 0, None, None, None
            s['fresh_pending'] = True

    s['block_exists_last'] = _block_file_known(s, c)
    blocked = account_blocked(s, c)
    if isinstance(s.get('enabled_last'), bool) and s['enabled_last'] != enabled:
        events.append({'event': 'switch', 'enabled': enabled, 'id': s.get('period'), 'at': now})
    s['enabled_last'] = enabled

    # 2. Without a balance nothing is judged; with one, a waiting fresh start is taken now.
    B = _num(balance)
    if B is not None and s.get('fresh_pending'):
        first = s.get('started_at') is None
        _complete_fresh(s, now, B, today)
        events.append({'event': 'fresh_start', 'scope': 'first' if first else 'account', 'id': s['period'],
                       'balance': B, 'at': now})
    started = not s.get('fresh_pending') and s.get('settled_balance') is not None
    tripped = settled = False

    if started and B is not None:
        S = s['settled_balance']
        read_at = _num(cash_read_at) if cash_deals is not None else None
        if (read_at is not None and not s.get('cash_baseline_done') and s.get('started_at') is not None
                and read_at < s['started_at']):
            read_at = None                 # (made before counting started: it is not the first read of this start)
        deals = None
        if read_at is not None:
            read_at = min(read_at, now)
            deals = _clean_deals(cash_deals)
            if s.get('cash_read_ok_at') is None or read_at > s['cash_read_ok_at']:
                s['cash_read_ok_at'] = read_at
            if not s.get('cash_baseline_done'):
                # 4a. The first read after a fresh start: what it returns up to the start (BASELINE_MARGIN_S later
                #     at most: the history's clock and this one) is inside the starting balance. An operation made
                #     after the start -- the first reads may fail for a while -- is not: it waits, unseen, and is
                #     scaled when the change of the balance it made settles (4b), as every later one is.
                seen = dict(s.get('cash_seen') or {})
                edge = s['started_at'] + BASELINE_MARGIN_S
                inside = 0
                for key, _amount, when in deals:
                    if when is None or when <= edge:
                        seen[key] = when
                        inside += 1
                s['cash_seen'], s['cash_baseline_done'] = seen, True
                events.append({'event': 'cash_start', 'tickets': inside, 'later': len(deals) - inside, 'at': now})

        # 3. A balance that differs from the last judged one (to the cent) is not judged at once: it may be a
        #    deposit or a withdrawal, and the history that tells arrives a moment after the balance.
        if _cents(B) != _cents(S):
            if s.get('change_first') is None or s.get('change_last') is None:
                s['change_first'] = s['change_last'] = now
            elif s.get('seen_balance') is None or _cents(B) != _cents(s['seen_balance']):
                s['change_last'] = now
            if now < s['change_last']:                    # (the clock of the server was set back)
                s['change_last'] = now
            if now < s['change_first']:
                s['change_first'] = now
            by_read = read_at is not None and read_at >= s['change_last'] + confirm_s
            # No history for a minute: a fall is taken as a loss. The minute counts while this process was
            # looking: a bot that was stopped in the middle of a check tries the history first after its restart.
            wait_from = s['change_first']
            watching = _num(c.get('watching_since'))
            if watching is not None and watching > wait_from:
                wait_from = watching
            by_wait = B < S and now - wait_from >= cash_wait_s
            if by_read or by_wait:
                first_seen = s['change_first']
                # 5. A change first seen on the day before is judged against that day (a loss at 23:59:58
                #    belongs to the day it was made), and only then does the new day start.
                of_old_day = s.get('day') != today and _day_key(first_seen) != today
                if deals is not None:
                    _apply_cash(s, deals, B, now, read_at, first_seen, events)          # 4b
                if s.get('day') != today and not of_old_day:
                    _roll_day(s, now, B, today)
                if s.get('peak') is None or B > s['peak']:                              # 6
                    s['peak'], s['peak_at'] = B, now
                s['settled_balance'], s['settled_at'] = B, now
                s['change_first'] = s['change_last'] = None
                settled = True
                if enabled and not blocked:                                             # 10
                    trip = _account_trip(s, limits, now)
                    if trip is not None:
                        s['account_block'] = trip
                        blocked = tripped = True
                if s.get('day') != today:
                    _roll_day(s, now, B, today)
        else:
            s['change_first'] = s['change_last'] = None
            if s.get('day') != today:
                _roll_day(s, now, B, today)                                             # 5
        s['seen_balance'] = B

    if judge_again and started and enabled and not blocked and not tripped:
        trip = _account_trip(s, limits, now)
        if trip is not None:
            s['account_block'] = trip
            blocked = tripped = True
    if tripped:
        events.append({'event': 'trip', 'scope': 'account', 'rules': list(s['account_block']['rules']),
                       'numbers': dict(s['account_block']['numbers']), 'id': s['period'], 'at': now})

    _bot_rule(s, limits, enabled, now, events)                                          # 11

    # 9. The hold: no new trade while a change that would meet a limit is still being checked, or while a closed
    #    trade whose result is not known yet could be the Nth loss. It ends by itself. Not while OFF (8).
    pending = started and s.get('change_first') is not None
    waiting = _num(pending_results)
    waiting = max(0, int(waiting)) if waiting is not None else 0
    hold, hold_why, hold_since = False, None, None
    if enabled:
        open_balance = B if B is not None else s.get('seen_balance')
        if pending and not blocked and open_balance is not None:
            day_counts = s.get('day') == today or _day_key(s['change_first']) != today
            if (_met(_pct_below(s.get('peak'), open_balance), limits.drop_pct)
                    or (day_counts and _met(_pct_below(s.get('day0'), open_balance), limits.day_pct))):
                hold, hold_why, hold_since = True, 'limit', s['change_first']
        if (not hold and s.get('bot_block') is None and limits.streak_n and waiting > 0
                and s.get('streak', 0) + waiting >= limits.streak_n):
            hold, hold_why = True, 'results'

    return s, {'events': events, 'enabled': enabled, 'account_blocked': blocked, 'tripped': tripped,
               'settled': settled, 'pending': bool(pending), 'hold': hold, 'hold_why': hold_why,
               'hold_since': hold_since, 'waiting': waiting}


def count_trade(state, limits, now, trade_key, net_pl, enabled=True):
    """
    A trade of this bot closed with `net_pl` (profit, swap, commission and fee together): a loss adds 1 to the
    losing trades in a row, anything else sets them back to 0. A key counted before changes nothing (the bot may
    report a close twice, for example after a restart). A result that is not a number counts as a loss: the unsafe
    reading would be to let an unknown result reset the count. Returns (the new state, events).
    """
    s = dict(state)
    limits = _as_limits(limits)
    events = []
    key = str(trade_key)
    counted = list(s.get('counted_trades') or [])
    if key in counted:
        return s, events
    pl = _num(net_pl)
    s['streak'] = (s.get('streak') or 0) + 1 if (pl is None or pl < 0) else 0
    counted.append(key)
    s['counted_trades'] = counted[-KEEP_TRADES:]
    events.append({'event': 'trade', 'key': key, 'net': pl, 'in_a_row': s['streak'], 'at': float(now)})
    _bot_rule(s, limits, bool(enabled), float(now), events)
    return s, events


def note_other(state, now, text, enabled=True):
    """Another program trades this bot's market in this account (the spec, 6.3): this bot is blocked until the owner
    unblocks it. Not while the safety is OFF, and not on top of a block it already has. Returns (state, events)."""
    s = dict(state)
    events = []
    if enabled and s.get('bot_block') is None:
        detail = ' '.join(str(text or '').split())[:300]
        s['bot_block'] = {'rule': 'OTHER_PROGRAM', 'text': detail, 'count': None, 'limit': None, 'at': float(now)}
        events.append({'event': 'trip', 'scope': 'bot', 'rule': 'OTHER_PROGRAM', 'text': detail,
                       'id': s.get('period'), 'at': float(now)})
    return s, events


def _differs(a, b):
    a, b = _num(a), _num(b)
    if a is None and b is None:
        return False
    return a is None or b is None or abs(a - b) > 1e-9


def partner_view(status, partner_branch, limits, my_sha, my_tail, now):
    """The other bot of the account, from its status file: None when it has none. The two account limits and the
    account must be the same for both bots (the losing-trades limit is each bot's own)."""
    if not isinstance(status, dict):
        return None
    limits = _as_limits(limits)
    seen = _num(status.get('at'))
    theirs = status.get('limits') if isinstance(status.get('limits'), dict) else None
    limits_differ = bool(theirs is not None and (_differs(theirs.get('drop_pct'), limits.drop_pct)
                                                 or _differs(theirs.get('day_pct'), limits.day_pct)))
    their_sha, their_tail = status.get('login_sha'), status.get('login_tail')
    if isinstance(their_sha, str) and my_sha:
        account_differs = their_sha != my_sha
    elif isinstance(their_tail, str) and '?' not in their_tail and '?' not in str(my_tail):
        account_differs = their_tail != my_tail
    else:
        account_differs = False
    drop = status.get('drop') if isinstance(status.get('drop'), dict) else {}
    day = status.get('day') if isinstance(status.get('day'), dict) else {}
    return {'branch': partner_branch, 'seen_at': seen, 'blocked': status.get('blocked') is True,
            'bot_blocked': status.get('bot_blocked') is True, 'drop_pct': _num(drop.get('pct')),
            'day_pct': _num(day.get('pct')), 'limits_differ': limits_differ, 'account_differs': account_differs,
            'period': status.get('period') if isinstance(status.get('period'), str) else None,
            'stale': seen is None or now - seen > PARTNER_STALE_S or now < seen - PARTNER_STALE_S}


def build_view(state, limits, now, facts=None):
    """
    What the bot, the trace and the dashboard see of the safety (the spec, section 9, `_safety`). Every key is
    always there. `facts` is what does not live in the state: {'enabled', 'account_blocked', 'hold', 'hold_why',
    'hold_since', 'pending', 'waiting', 'error', 'error_since', 'block' (the block file's content, or this bot's
    own block), 'block_since', 'partner', 'account_dir', 'login_tail', 'branch', 'partner_branch', 'cash_wait_s'}.
    """
    s = state if isinstance(state, dict) else new_state()
    f = facts or {}
    limits = _as_limits(limits)
    now = float(now)
    tail = f.get('login_tail') or '...?'
    branch = f.get('branch')
    enabled = f.get('enabled') is not False
    error = f.get('error') or None
    acct = bool(f.get('account_blocked'))
    block = s.get('bot_block') if isinstance(s.get('bot_block'), dict) else None
    hold = bool(f.get('hold')) and enabled
    waiting = int(f.get('waiting') or 0)
    known = not s.get('fresh_pending') and s.get('settled_balance') is not None
    balance = s.get('settled_balance') if known else None
    blocked = enabled and (acct or block is not None or error is not None)

    partner = f.get('partner') if isinstance(f.get('partner'), dict) else None
    reasons, since, state_name = [], None, 'on'
    if not enabled:
        reasons, state_name = [_say_off(tail)], 'off'
    else:
        if error is not None:
            reasons.append(ERROR_SENTENCE)
            since, state_name = f.get('error_since'), 'error'
        if acct:
            info = f.get('block') if isinstance(f.get('block'), dict) else {}
            at = _num(info.get('at'))
            at = at if at is not None else _num(f.get('block_since'))
            reasons.append(_say_account_blocked(at))
            said = []
            if isinstance(info.get('reasons'), list):
                said = [x for x in info['reasons'] if isinstance(x, str) and x][:6]
            if not said and isinstance(info.get('rules'), list) and info['rules']:
                said = block_sentences(info['rules'], info.get('numbers'))
                seen_by = _say_seen_by(info.get('branch'))
                if seen_by:
                    said.append(seen_by)
            reasons.extend(said or ['The details of this block cannot be read.'])
            if state_name == 'on':
                since, state_name = at, 'account_blocked'
        if block is not None:
            note = ''
            if (not acct and partner is not None and not partner.get('stale')
                    and partner.get('period') == s.get('period')):
                other = _cap(_bot(f.get('partner_branch'), other=True))
                note = f'{other} is blocked as well.' if partner.get('bot_blocked') else f'{other} is not blocked.'
            reasons.append(_say_bot_blocked(branch, block, note))
            if state_name == 'on':
                since, state_name = block.get('at'), 'bot_blocked'
        if hold:
            # (also said under a block of this bot: the account is being checked at the same time)
            if f.get('hold_why') == 'results':
                reasons.append(_say_waiting(branch, max(1, waiting), s.get('streak') or 0, limits.streak_n))
            else:
                reasons.append(_say_checking(f.get('hold_since'), f.get('cash_wait_s') or CASH_WAIT_S))
            if state_name == 'on':
                since, state_name = f.get('hold_since'), 'checking'
        if not reasons:
            reasons.append(_say_watching(tail))

    return {
        'enabled': enabled, 'blocked': bool(blocked), 'hold': hold, 'pending': bool(f.get('pending')),
        'account_blocked': acct, 'bot_blocked': block is not None,
        'blocked_scope': ('account' if acct else 'bot' if block is not None else None) if enabled else None,
        'reasons': reasons, 'since': since, 'period': s.get('period'), 'at': now,
        'started_at': s.get('started_at'), 'error': error, 'state': state_name,
        'drop': {'pct': _pct_below(s.get('peak'), balance) if known else 0.0, 'limit': limits.drop_pct,
                 'peak': s.get('peak') if known else None, 'peak_at': s.get('peak_at') if known else None,
                 'balance': balance},
        'day': {'pct': _pct_below(s.get('day0'), balance) if known else 0.0, 'limit': limits.day_pct,
                'day0': s.get('day0') if known else None, 'day0_at': s.get('day0_at') if known else None,
                'day': s.get('day'), 'since': s.get('day_since'), 'start_balance': s.get('day_start_balance'),
                'start_at': s.get('day_start_at'), 'cash': s.get('day_cash') or 0.0},
        'streak': {'count': s.get('streak') or 0, 'limit': limits.streak_n, 'waiting': waiting},
        'partner': partner, 'limits': limits.as_dict(), 'account_dir': f.get('account_dir'), 'login_tail': tail,
    }


# ───────────────────────── reading and writing the files ─────────────────────────
# Windows, and several programs on one folder:
#  - every file but the block file and the audit file is written whole to a temp file of its own name and then
#    moved over the old one (os.replace): a reader sees the old file or the new one, never half of one;
#  - Windows refuses that move for a moment while another program has the old file open (PermissionError): the
#    move is tried again briefly; and a reader can meet the same refusal: it then keeps what it knew;
#  - a file that is not there is an answer (the default); a file that is there but cannot be read is NOT.

_REPLACE_WAITS_S = (0.005, 0.01, 0.02, 0.04, 0.06, 0.1)        # about 0.24 s in all (as tracelog.write_json_atomic)


def _replace_retry(src, dst, waits=_REPLACE_WAITS_S):
    for wait in tuple(waits) + (None,):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if wait is None:
                raise
            time.sleep(wait)


def _write_atomic(path, text, durable=False):
    """Write `text` to `path` through a temp file of a name no other write uses (<name>.<pid>.<8 hex>.tmp: two
    dashboards and a command line may write the same file in the same instant). `durable`: the bytes are on the
    disk before the move, so a power cut cannot leave an empty file under the real name. Raises OSError."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = f'{path}.{os.getpid()}.{secrets.token_hex(4)}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
            if durable:
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
        _replace_retry(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _dumps(obj):
    return json.dumps(obj, indent=1, sort_keys=True, allow_nan=False, default=str)


def _create_exclusive(path, text):
    """Create `path` only if it is not there (two bots may try in the same instant: one wins). True = this call made
    it, False = it was there already; any other failure raises OSError. Once the file exists the block stands, so a
    failed write of its content is not an error: the content is information only."""
    try:
        f = open(path, 'x', encoding='utf-8', newline='\n')
    except FileExistsError:
        return False
    try:
        f.write(text)
    except (OSError, ValueError):
        pass
    finally:
        try:
            f.close()
        except OSError:
            pass
    return True


def _read_json(path, tries=1):
    """('ok', value), ('missing', None), ('unreadable', why): the file is there but could not be opened or read
    (another program holds it this moment), or ('invalid', why): it was read and is not JSON. `tries` above 1: a
    refusal is tried again after a few milliseconds (for a button press, which has no next poll to wait for)."""
    why = ''
    for attempt in range(max(1, tries)):
        if attempt:
            time.sleep(0.01 * attempt)
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except FileNotFoundError:
            return 'missing', None
        except OSError as e:
            why = f'{type(e).__name__}: {e}'
            continue
        try:
            return 'ok', json.loads(raw.decode('utf-8-sig'))
        except ValueError as e:                      # (UnicodeDecodeError is one)
            return 'invalid', f'{type(e).__name__}: {e}'
    return 'unreadable', why


def _append_line(path, obj):
    """One JSON line at the end of the audit file. Raises OSError."""
    line = json.dumps(obj, sort_keys=True, allow_nan=False, default=str) + '\n'
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(line)


def _read_restart(account_dir, tries=1):
    """The restart file: {'status': 'ok' / 'missing' / 'unreadable', 'id', 'scope', 'account_id', 't', 'by', 'why'}.
    Missing means the id 'start'. A file that was read but does not hold a usable id counts as unreadable."""
    status, data = _read_json(os.path.join(str(account_dir), RESTART_FILE), tries)
    if status == 'missing':
        return {'status': 'missing', 'id': FIRST_ID, 'scope': None, 'account_id': FIRST_ID, 't': None, 'by': None,
                'why': None}
    if status == 'ok' and isinstance(data, dict) and isinstance(data.get('id'), str) and _ID_OK.match(data['id']):
        scope = data.get('scope') if data.get('scope') in ('account', 'bot') else 'account'
        acct = data.get('account_id')
        acct = acct if isinstance(acct, str) and _ID_OK.match(acct) else (data['id'] if scope == 'account' else None)
        return {'status': 'ok', 'id': data['id'], 'scope': scope, 'account_id': acct, 't': _num(data.get('t')),
                'by': data.get('by') if isinstance(data.get('by'), str) else None,
                'why': data.get('why') if isinstance(data.get('why'), str) else None}
    return {'status': 'unreadable', 'id': None, 'scope': None, 'account_id': None, 't': None, 'by': None, 'why': None}


def _read_switch(account_dir, tries=1):
    """The switch file: {'status': 'ok' / 'missing' / 'unreadable', 'enabled' (None unless ok), 't', 'by'}."""
    status, data = _read_json(os.path.join(str(account_dir), SWITCH_FILE), tries)
    if status == 'missing':
        return {'status': 'missing', 'enabled': None, 't': None, 'by': None}
    if status == 'ok' and isinstance(data, dict) and isinstance(data.get('enabled'), bool):
        return {'status': 'ok', 'enabled': data['enabled'], 't': _num(data.get('t')),
                'by': data.get('by') if isinstance(data.get('by'), str) else None}
    return {'status': 'unreadable', 'enabled': None, 't': None, 'by': None}


def _block_exists(account_dir, restart_id):
    """(True, its time) when the block file of that id is there, (False, None) when it is not, (None, None) when the
    folder could not be asked (the caller then keeps what it knew)."""
    try:
        st = os.stat(block_path(account_dir, restart_id))
    except FileNotFoundError:
        return False, None
    except OSError:
        return None, None
    return True, st.st_mtime


def _read_block(account_dir, restart_id):
    """What the block file says (information only: the file blocks by being there): a dict, or None when it is
    empty or cannot be read."""
    status, data = _read_json(block_path(account_dir, restart_id))
    if status != 'ok' or not isinstance(data, dict):
        return None
    rules = data.get('rules') if isinstance(data.get('rules'), list) else []
    reasons = data.get('reasons') if isinstance(data.get('reasons'), list) else []
    return {'period': str(restart_id), 'at': _num(data.get('at')),
            'branch': data.get('branch') if isinstance(data.get('branch'), str) else None,
            'rules': [r for r in rules if r in ('DROP', 'DAY')],
            'numbers': data.get('numbers') if isinstance(data.get('numbers'), dict) else {},
            'reasons': [x for x in reasons if isinstance(x, str)][:6]}


def _valid_pin(text):
    """A PIN is 4 to 32 printable ASCII characters without spaces."""
    return isinstance(text, str) and 4 <= len(text) <= 32 and all(33 <= ord(ch) <= 126 for ch in text)


def _read_pin(account_dir):
    """('ok', the PIN), ('missing', None) or ('bad', None). Read as UTF-8 with or without a byte-order mark
    (Notepad writes one); a file saved in another encoding is 'bad', not a wrong PIN."""
    try:
        with open(pin_path(account_dir), 'rb') as f:
            raw = f.read(4096)
    except FileNotFoundError:
        return 'missing', None
    except OSError:
        return 'bad', None
    try:
        text = raw.decode('utf-8-sig').strip()
    except ValueError:
        return 'bad', None
    return ('ok', text) if _valid_pin(text) else ('bad', None)


def ensure_pin(account_dir):
    """Create the PIN file with 6 random digits if there is none (the dashboard calls this when it starts as a
    program). An existing file is the owner's and is never touched. Never returns or prints the PIN; never raises:
    without a PIN file the buttons answer that there is none."""
    try:
        os.makedirs(str(account_dir), exist_ok=True)
        pin = ''.join(secrets.choice('0123456789') for _ in range(6))
        with open(pin_path(account_dir), 'x', encoding='ascii', newline='\n') as f:
            f.write(pin + '\n')
    except OSError:                                  # (FileExistsError: it is there, by an earlier start or the owner)
        pass
    return None


def read_controls(account_dir, default_on=True):
    """
    What the files of the account folder say now, for the dashboard and for a bot that has no Tracker:
    {'enabled', 'period', 'scope', 'block', 'locked_until', 'pin_set', 'readable', ...}.

    - 'enabled': the switch; `default_on` while nobody has switched it. A switch file that cannot be read also
      gives `default_on` (and 'readable' False): the safe side, the safety counts as ON.
    - 'period': the fresh-start id ('start' while there is no restart file; None when the file cannot be read).
    - 'block': None, or the block of that id: {'period', 'readable', 'at', 'branch', 'rules', 'numbers',
      'reasons', 'file_time'} ('readable' False: the file is there, which blocks, but says nothing).
    - 'locked_until': until when wrong PINs lock the buttons (None: not locked; compare with the time of now).
    - 'pin_set': the PIN file holds a usable PIN.
    - 'readable': False when the restart file, the switch file or the folder could not be read just now.
    - also 'pressed_at' / 'pressed_by' / 'pressed_why' (the restart file) and 'switched_at' / 'switched_by'.
    Never raises.
    """
    out = {'enabled': bool(default_on), 'period': None, 'scope': None, 'block': None, 'locked_until': None,
           'pin_set': False, 'readable': False, 'pressed_at': None, 'pressed_by': None, 'pressed_why': None,
           'switched_at': None, 'switched_by': None}
    try:
        folder = str(account_dir)
        restart = _read_restart(folder)
        switch = _read_switch(folder)
        readable = restart['status'] != 'unreadable' and switch['status'] != 'unreadable'
        if switch['status'] == 'ok':
            out.update(enabled=switch['enabled'], switched_at=switch['t'], switched_by=switch['by'])
        if restart['status'] != 'unreadable':
            out.update(period=restart['id'], scope=restart['scope'], pressed_at=restart['t'],
                       pressed_by=restart['by'], pressed_why=restart['why'])
            exists, file_time = _block_exists(folder, restart['id'])
            if exists is None:
                readable = False
            elif exists:
                info = _read_block(folder, restart['id'])
                out['block'] = dict(info or {'period': restart['id'], 'at': None, 'branch': None, 'rules': [],
                                             'numbers': {}, 'reasons': []},
                                    readable=info is not None, file_time=file_time)
        status, lock = _read_json(os.path.join(folder, LOCKOUT_FILE))
        if status == 'ok' and isinstance(lock, dict):
            until = _num(lock.get('locked_until'))
            out['locked_until'] = until if until and until > 0 else None
        out['pin_set'] = _read_pin(folder)[0] == 'ok'
        out['readable'] = readable
    except Exception:                                # (by contract: a caller in the poll loop gets an answer)
        out['readable'] = False
    return out


def read_statuses(account_dir):
    """{branch: its status file} for every bot of the account folder whose status file can be read now. A status
    is that bot's last view (build_view) plus 'branch', 'login_sha', 'written_at' and the details of its blocks.
    Never raises."""
    out = {}
    try:
        folder = str(account_dir)
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        if not (name.startswith('safety_status_') and name.endswith('.json')):
            continue
        try:
            status, data = _read_json(os.path.join(folder, name))
        except Exception:
            continue
        if status != 'ok' or not isinstance(data, dict):
            continue
        branch = data.get('branch')
        if not isinstance(branch, str) or not branch:
            branch = name[len('safety_status_'):-len('.json')]
        out[branch] = data
    return out


# ───────────────────────── the state file of a bot ─────────────────────────

def _clean_bot_block(value, fallback_at=None):
    """A saved block of this bot. Anything that is not None is a block: a damaged entry must not unblock."""
    if value is None:
        return None
    v = value if isinstance(value, dict) else {}
    count, limit = _num(v.get('count')), _num(v.get('limit'))
    return {'rule': v.get('rule') if v.get('rule') in ('STREAK', 'OTHER_PROGRAM') else 'STREAK',
            'text': str(v.get('text') or '')[:300],
            'count': None if count is None else int(count), 'limit': None if limit is None else int(limit),
            'at': _num(v.get('at')) if _num(v.get('at')) is not None else fallback_at}


def _clean_account_block(value, period):
    if value is None:
        return None
    v = value if isinstance(value, dict) else {}
    its = v.get('period') if isinstance(v.get('period'), str) else period
    return {'period': its, 'rules': [r for r in v.get('rules') if r in ('DROP', 'DAY')]
            if isinstance(v.get('rules'), list) else [],
            'numbers': dict(v['numbers']) if isinstance(v.get('numbers'), dict) else {}, 'at': _num(v.get('at'))}


def state_from_file(data):
    """The state a state file holds, every field checked; None when it is not a state of this version (the file is
    then put aside). A state that says it has started but lacks a number a poll needs starts again with the next
    balance, keeping its count of losing trades and its blocks."""
    if not isinstance(data, dict) or data.get('version') != STATE_VERSION:
        return None
    period = data.get('period')
    if period is not None and not (isinstance(period, str) and _ID_OK.match(period)):
        return None
    s = new_state()
    s['period'] = period
    s['account_period'] = data.get('account_period') if isinstance(data.get('account_period'), str) else None
    for key in ('started_at', 'peak', 'peak_at', 'day0', 'day0_at', 'day_start_balance', 'day_start_at',
                'settled_balance', 'settled_at', 'change_first', 'change_last', 'seen_balance', 'cash_read_ok_at'):
        s[key] = _num(data.get(key))
    s['day_cash'] = _num(data.get('day_cash')) or 0.0
    s['day'] = data.get('day') if isinstance(data.get('day'), str) else None
    s['day_since'] = data.get('day_since') if data.get('day_since') in ('midnight', 'restart') else None
    streak = _num(data.get('streak'))
    s['streak'] = int(streak) if streak is not None and streak > 0 else 0
    s['bot_block'] = _clean_bot_block(data.get('bot_block'))
    s['account_block'] = _clean_account_block(data.get('account_block'), period)
    seen = data.get('cash_seen')
    s['cash_seen'] = {str(k): _num(v) for k, v in seen.items()} if isinstance(seen, dict) else {}
    s['cash_baseline_done'] = data.get('cash_baseline_done') is True
    trades = data.get('counted_trades')
    s['counted_trades'] = [str(k) for k in trades][-KEEP_TRADES:] if isinstance(trades, list) else []
    for key in ('enabled_last', 'block_exists_last'):
        s[key] = data.get(key) if isinstance(data.get(key), bool) else None
    s['fresh_pending'] = data.get('fresh_pending') is True
    s['login_sha'] = data.get('login_sha') if isinstance(data.get('login_sha'), str) else None
    s['branch'] = data.get('branch') if isinstance(data.get('branch'), str) else None
    if s['change_first'] is None or s['change_last'] is None:
        s['change_first'] = s['change_last'] = None
    if period is not None and not s['fresh_pending']:
        needed = ('started_at', 'peak', 'day0', 'settled_balance', 'settled_at', 'day_start_balance', 'day',
                  'day_since')
        if any(s[k] is None for k in needed):
            s['fresh_pending'] = True
    return s


# ───────────────────────── Tracker: one per bot ─────────────────────────

class Tracker:
    """
    The safety of one bot: the rules above, plus the files.

        tracker = Tracker(account_dir, state_path, BRANCH, PARTNER_BRANCH, Limits(...), default_on, login)
        tracker.load(now)                      # False: not usable yet, call again
        each poll, before the decision:        view = tracker.poll(now, balance, cash, cash_at, pending_results)
                                               no new trade while view['blocked'] or view['hold']
        each poll, after the orders:           the cash read when tracker.needs_cash(); tracker.flush(now)
        when a trade's result is known:        tracker.on_trade_closed(now, trade_key, net_pl)

    poll() works in memory only (rule 2: nothing may sit in front of a close): the one thing it does with the disk
    is to create the block file in the poll that meets an account limit. Everything else, the reading of what the
    owner pressed included, happens in load() and flush(). None of the five raises: a problem becomes
    view['error'], and while the safety is ON an error blocks new trades.

    One thread calls these (the poll loop). The views they return are not changed afterwards: treat them as
    read-only.
    """

    def __init__(self, account_dir, state_path, branch, partner_branch, limits, default_on=True, login=None,
                 confirm_s=CONFIRM_S, cash_wait_s=CASH_WAIT_S):
        self.account_dir = str(account_dir)
        self.state_path = None if state_path is None else str(state_path)    # None: nothing is saved (a replay)
        self.branch = str(branch)
        self.partner_branch = str(partner_branch) if partner_branch else None
        self.limits = _as_limits(limits)
        self.default_on = bool(default_on)
        self.login_sha = login_sha(login)
        self.login_tail = mask_login(login)
        self.confirm_s = float(confirm_s)
        self.cash_wait_s = float(cash_wait_s)

        self._state = None                  # None until load() has succeeded
        self._loaded_at = None              # when it did
        self._ctl = {'restart': None, 'enabled': self.default_on, 'switch_read': False, 'block_id': None,
                     'block_exists': None, 'block_info': None, 'block_time': None, 'partner': None}
        self._waiting = 0                   # pending_results of the last poll
        self._unjudged_s = 0.0              # for how long polls have seen a balance change they could not judge
        self._polled_at = None              # the time of the last poll that had a balance
        self._last = {'hold': False, 'hold_why': None, 'hold_since': None, 'pending': False}
        self._hold_noted = False
        self._events = []                   # what happened, for the journal (take_events)
        self._audit = []                    # lines owed to the audit file
        self._audit_hour, self._audit_lines, self._audit_more = None, 0, 0
        self._load_error = 'the safety files were not loaded yet'
        self._load_error_since = None
        self._poll_error = None             # a problem inside poll / on_trade_closed / note_other_program
        self._poll_error_since = None
        self._flush_error = None            # a problem inside flush that is not a refused file write
        self._flush_error_since = None
        self._state_saved = None            # the text of the state file as last written
        self._state_fail_since = None       # since when the state file cannot be written
        self._state_error = None
        self._block_fail_since = None       # since when the block file cannot be created
        self._block_error = None
        self._retry_at = {}                 # 'state' / 'status' / 'audit' -> not before this time
        self._status_key = None
        self._status_at = None
        self._view = build_view(None, self.limits, 0.0, self._facts(0.0))

    # ── what does not live in the state ──
    def _error(self, now):
        """(text, since) of what makes the safety check fail now, or (None, None)."""
        if self._state is None:
            return f'the safety state could not be loaded ({self._load_error})', self._load_error_since
        if self._poll_error is not None:
            return self._poll_error, self._poll_error_since
        if self._flush_error is not None:
            return self._flush_error, self._flush_error_since
        # A rise of the balance waits for the cash history, however long (it may be a deposit). While it waits the
        # rules judge nothing new: after ten minutes of polls without a readable history that is a failing check,
        # not a wait. (With both account rules off there is nothing the history could change.)
        first = self._state.get('change_first')
        judged = self.limits.drop_pct is not None or self.limits.day_pct is not None
        if first is not None and judged and self._unjudged_s >= STUCK_AFTER_S:
            since = max(first, self._loaded_at or first)
            return (f"the account's cash history could not be read since {_clock(since)} UTC, so a change of the "
                    'balance cannot be judged'), since
        own = self._state.get('account_block')
        owes_block = isinstance(own, dict) and own.get('period') == self._state.get('period')
        for since, what, why in ((self._state_fail_since, 'the safety state could not be saved', self._state_error),
                                 (self._block_fail_since if owes_block else None,
                                  'the block file could not be written', self._block_error)):
            if since is not None and abs(now - since) >= ERROR_AFTER_S:
                return f'{what} since {_clock(since)} UTC ({why})', since
        return None, None

    def _block_info(self):
        """The details of the account block of the id this bot counts under: the block file's (the bot that met
        the limit first), else this bot's own."""
        s = self._state or {}
        if self._ctl['block_id'] == s.get('period') and isinstance(self._ctl['block_info'], dict):
            return self._ctl['block_info']
        own = s.get('account_block')
        if isinstance(own, dict) and own.get('period') == s.get('period'):
            return {'period': own.get('period'), 'at': own.get('at'), 'branch': self.branch,
                    'rules': own.get('rules') or [], 'numbers': own.get('numbers') or {}, 'reasons': []}
        return None

    def _facts(self, now, out=None):
        s = self._state
        error, error_since = self._error(now)
        o = out or {}
        enabled = o.get('enabled') if isinstance(o.get('enabled'), bool) else bool(self._ctl['enabled'])
        if out is not None:
            acct = bool(o.get('account_blocked'))
        else:
            acct = s is not None and account_blocked(s, self._controls())
        last = o if out is not None else self._last
        partner = None
        if self.partner_branch:
            partner = partner_view(self._ctl['partner'], self.partner_branch, self.limits, self.login_sha,
                                   self.login_tail, now)
        return {'enabled': enabled, 'account_blocked': acct, 'hold': last.get('hold'),
                'hold_why': last.get('hold_why'), 'hold_since': last.get('hold_since'),
                'pending': last.get('pending'), 'waiting': self._waiting, 'error': error, 'error_since': error_since,
                'block': self._block_info(), 'block_since': self._ctl['block_time'], 'partner': partner,
                'account_dir': self.account_dir, 'login_tail': self.login_tail, 'branch': self.branch,
                'partner_branch': self.partner_branch, 'cash_wait_s': self.cash_wait_s}

    def _controls(self):
        """The last look at the folder, as decide() takes it."""
        r = self._ctl['restart'] or {}
        return {'restart_status': r.get('status'), 'restart_id': r.get('id'), 'restart_scope': r.get('scope'),
                'restart_account_id': r.get('account_id'), 'enabled': bool(self._ctl['enabled']),
                'block_id': self._ctl['block_id'], 'block_exists': self._ctl['block_exists'],
                'watching_since': self._loaded_at}

    def _remake_view(self, now, out=None):
        if out is not None:
            self._last = {k: out.get(k) for k in ('hold', 'hold_why', 'hold_since', 'pending')}
        self._view = build_view(self._state, self.limits, now, self._facts(now, out))
        return self._view

    def _failed(self, now, where, e):
        """A problem inside the safety itself: by contract it becomes view['error'], which blocks while ON.
        ON or OFF is what flush() read last, not what the last good poll saw: when the check fails for good, the
        owner's way out is to turn the safety OFF, and that press must reach the bot."""
        try:
            now = float(now)
        except (TypeError, ValueError):
            now = (self._view or {}).get('at') or 0.0
        if self._poll_error is None:
            self._poll_error_since = now
        self._poll_error = f'{where}: {type(e).__name__}: {e}'
        try:
            return self._remake_view(now)
        except Exception:
            pass
        # (Even the view cannot be made: the barest one, by hand.)
        enabled = self._ctl.get('enabled') is not False
        self._view = {
            'enabled': enabled, 'blocked': enabled, 'hold': False, 'pending': False, 'account_blocked': False,
            'bot_blocked': False, 'blocked_scope': None,
            'reasons': [ERROR_SENTENCE if enabled else _say_off(self.login_tail)],
            'since': self._poll_error_since if enabled else None, 'period': None, 'at': now, 'started_at': None,
            'error': self._poll_error, 'state': 'error' if enabled else 'off',
            'drop': {'pct': 0.0, 'limit': self.limits.drop_pct, 'peak': None, 'peak_at': None, 'balance': None},
            'day': {'pct': 0.0, 'limit': self.limits.day_pct, 'day0': None, 'day0_at': None, 'day': None,
                    'since': None, 'start_balance': None, 'start_at': None, 'cash': 0.0},
            'streak': {'count': 0, 'limit': self.limits.streak_n, 'waiting': 0},
            'partner': None, 'limits': self.limits.as_dict(), 'account_dir': self.account_dir,
            'login_tail': self.login_tail}
        return self._view

    def _note(self, events, now):
        """Remember what happened: for the journal (take_events) and, the blocks and fresh starts, for the audit
        file of the account folder."""
        for e in events or ():
            self._events.append(dict(e, branch=self.branch))
            if e.get('event') in ('trip', 'fresh_start', 'state_put_aside'):
                self._audit.append(dict(e, at=_iso(e.get('at') if e.get('at') is not None else now), t=e.get('at'),
                                        by=f'bot {self.branch}'))
        del self._events[:-200]
        del self._audit[:-200]

    # ── load ──
    def load(self, now):
        """Read the state file and the control files. True: usable. False: not yet (the account folder cannot be
        made, or the state file is there but cannot be read this moment): call again; until then the bot has no
        usable safety and must open nothing while the safety is ON. Never raises."""
        try:
            now = float(now)
            if self._state is not None:
                return True
            if self._load_error_since is None:
                self._load_error_since = now
            return self._load(now)
        except Exception as e:
            self._load_error = f'{type(e).__name__}: {e}'
            try:
                self._remake_view(float(now))
            except Exception:
                pass
            return False

    def _load(self, now):
        try:
            os.makedirs(self.account_dir, exist_ok=True)
        except OSError as e:
            self._load_error = f'the account folder {self.account_dir} cannot be made: {type(e).__name__}: {e}'
            self._remake_view(now)
            return False
        status, data = ('missing', None) if self.state_path is None else _read_json(self.state_path)
        if status == 'unreadable':
            # (Another program holds the file this moment. Putting it aside would wipe a block: try again.)
            self._load_error = f'the state file cannot be read: {data}'
            self._remake_view(now)
            return False
        state, aside = None, None
        if status == 'ok':
            state = state_from_file(data)
            if state is None:
                aside = 'not-readable'
            elif self.login_sha and state.get('login_sha') and state['login_sha'] != self.login_sha:
                state, aside = None, 'other-account'            # another account's figures: never judged here
        elif status == 'invalid':
            aside = 'not-readable'
        self._read_folder(now, state)
        events = []
        if aside is not None:
            target = f'{self.state_path}.{aside}-{_name_stamp(now)}'
            try:
                os.replace(self.state_path, target)
                moved = os.path.basename(target)
            except OSError:
                moved = None                                    # (left where it is; the next save replaces it)
            events.append({'event': 'state_put_aside', 'why': aside, 'kept_as': moved, 'at': now})
        if state is None:
            state = new_state(self.branch, self.login_sha)
            if aside != 'other-account':
                self._keep_blocks(state)
        state['branch'] = self.branch
        if self.login_sha:
            state['login_sha'] = self.login_sha
        self._state = state
        if not self._ctl['switch_read'] and isinstance(state.get('enabled_last'), bool):
            self._ctl['enabled'] = state['enabled_last']        # (first read failed: what this bot knew last)
        self._state_saved = None                                # (the first flush writes the file once)
        self._loaded_at = now
        self._load_error = None
        self._note(events, now)
        self._sweep(now)
        self._remake_view(now)
        return True

    def _keep_blocks(self, state):
        """The state file is gone or was put aside as damaged. A block must not vanish with it: this bot's own
        status file still shows it. It is kept when that status is of the same account and of the id counting
        runs under now (after an Unblock the id is another one, and the old block is rightly gone)."""
        status, mine = _read_json(status_path(self.account_dir, self.branch), tries=3)
        if status != 'ok' or not isinstance(mine, dict) or not isinstance(mine.get('period'), str):
            return
        if self.login_sha and isinstance(mine.get('login_sha'), str) and mine['login_sha'] != self.login_sha:
            return
        restart = self._ctl['restart'] or {}
        current = restart.get('id') if restart.get('status') in ('ok', 'missing') else mine['period']
        if mine['period'] != current or not _ID_OK.match(mine['period']):
            return
        bot_block = _clean_bot_block(mine.get('bot_block'), _num(mine.get('since')))
        if mine.get('bot_blocked') is True and bot_block is None:
            bot_block = _clean_bot_block({}, _num(mine.get('since')))
        own = _clean_account_block(mine.get('account_block'), current)
        if own is not None and own.get('period') != current:
            own = None
        if bot_block is None and own is None:
            return
        # The figures (the high, the day) are gone with the state: they start again with the next balance. The
        # blocks and the count of losing trades are kept.
        state['period'] = current
        if restart.get('status') == 'ok':
            state['account_period'] = restart.get('account_id')
        else:
            state['account_period'] = FIRST_ID if current == FIRST_ID else None
        state['fresh_pending'] = True
        state['bot_block'] = bot_block
        streak = mine.get('streak') if isinstance(mine.get('streak'), dict) else {}
        state['streak'] = max(0, int(_num(streak.get('count')) or 0))
        state['account_block'] = own

    def _sweep(self, now):
        """Temp files a crash left in the account folder (safety_*.json.<pid>.<8 hex>.tmp), a day old: removed."""
        try:
            for name in os.listdir(self.account_dir):
                if not _TMP_NAME.match(name):
                    continue
                path = os.path.join(self.account_dir, name)
                try:
                    if now - os.stat(path).st_mtime > 86400.0:
                        os.remove(path)
                except OSError:
                    pass
        except OSError:
            pass

    # ── the control files, read in load() and flush() for the next poll ──
    def _read_folder(self, now, state=None):
        """Read what the owner pressed (restart, switch), whether the account is blocked, and the other bot's
        status. A file that cannot be read keeps what was known; a missing file is its default."""
        s = state if state is not None else self._state
        restart = _read_restart(self.account_dir)
        if restart['status'] in ('ok', 'missing'):
            self._ctl['restart'] = restart
        switch = _read_switch(self.account_dir)
        if switch['status'] == 'ok':
            self._ctl['enabled'], self._ctl['switch_read'] = switch['enabled'], True
        elif switch['status'] == 'missing':
            self._ctl['enabled'], self._ctl['switch_read'] = self.default_on, True
        # The block file of the id the NEXT poll counts under (a new id read just now is taken by that poll).
        known = self._ctl['restart'] or {}
        period = (s or {}).get('period')
        if period is None:
            target = known.get('id') if known.get('status') == 'ok' else FIRST_ID
        elif known.get('status') == 'ok' and known.get('id') != period:
            target = known['id']
        else:
            target = period
        exists, file_time = _block_exists(self.account_dir, target)
        if self._ctl['block_id'] != target:
            self._ctl.update(block_id=target, block_exists=None, block_info=None, block_time=None)
        if exists is not None:
            self._ctl['block_exists'] = exists
            self._ctl['block_time'] = file_time if exists else None
            if not exists:
                self._ctl['block_info'] = None
            elif self._ctl['block_info'] is None:
                self._ctl['block_info'] = _read_block(self.account_dir, target)
        if self.partner_branch:
            status, theirs = _read_json(status_path(self.account_dir, self.partner_branch))
            if status == 'ok' and isinstance(theirs, dict):
                self._ctl['partner'] = theirs
            elif status == 'missing':
                self._ctl['partner'] = None

    # ── the poll ──
    def poll(self, now, balance, cash_deals=None, cash_read_at=None, pending_results=0):
        """One poll: `balance` is the booked balance of the account (None when it is not known); `cash_deals` the
        balance operations read at `cash_read_at` ({'ticket', 'amount', 'time'}; None when no read succeeded
        since the last poll); `pending_results` how many closed trades of this bot still wait for their result.
        Returns the view (section 9 of the spec). No new trade while view['blocked'] or view['hold']."""
        try:
            now = float(now)
            if self._state is None:
                return self._remake_view(now)
            state, out = decide(self._state, self.limits, now, balance, cash_deals, cash_read_at, pending_results,
                                self._controls(), self.confirm_s, self.cash_wait_s)
            self._state = state
            self._waiting = out['waiting']
            if _num(balance) is not None:
                # (Time the bot really watched, from one poll that could not judge to the next: a pause of the
                # polls, the terminal away for an hour, is not time in which the history could have been read.)
                step = 0.0 if self._polled_at is None else min(max(now - self._polled_at, 0.0), 10.0)
                self._unjudged_s = self._unjudged_s + step if (out['pending'] and self._last.get('pending')) else 0.0
                self._polled_at = now
            self._poll_error = self._poll_error_since = None
            self._note(out['events'], now)
            if out['tripped']:
                self._make_block_file(now)          # the one file a poll may write
            self._note_hold(now, out)
            return self._remake_view(now, out)
        except Exception as e:
            return self._failed(now, 'the safety check', e)

    def _note_hold(self, now, out):
        """A hold that lasts is worth a line in the journal: once when it is 10 s old, once when it ends."""
        if out.get('hold'):
            since = out.get('hold_since')
            if since is None:
                since = self._last.get('hold_since') if self._last.get('hold') else now
                out['hold_since'] = since
            if not self._hold_noted and now - since >= HOLD_NOTE_S:
                self._hold_noted = True
                self._events.append({'event': 'hold', 'why': out.get('hold_why'), 'since': since,
                                     'seconds': round(now - since, 1), 'at': now, 'branch': self.branch})
        else:
            if self._hold_noted:
                since = self._last.get('hold_since')
                self._events.append({'event': 'hold_end', 'since': since, 'at': now, 'branch': self.branch,
                                     'seconds': None if since is None else round(now - since, 1)})
            self._hold_noted = False

    def _make_block_file(self, now):
        """Create the block file of the account block this bot holds in its state, if nobody has yet. The block
        stands without the file (the state has it); the file is what blocks the other bot."""
        s = self._state
        own = s.get('account_block') if s else None
        if not isinstance(own, dict) or own.get('period') != s.get('period'):
            return
        period = s['period']
        reasons = block_sentences(own.get('rules'), own.get('numbers'))
        seen_by = _say_seen_by(self.branch)
        content = {'period': period, 'rules': own.get('rules'), 'numbers': own.get('numbers'), 'at': own.get('at'),
                   'at_utc': _iso(own.get('at')), 'branch': self.branch, 'login_tail': self.login_tail,
                   'reasons': reasons + ([seen_by] if seen_by else [])}
        try:
            made = _create_exclusive(block_path(self.account_dir, period), _dumps(content) + '\n')
        except OSError as e:
            if self._block_fail_since is None:
                self._block_fail_since = now
            self._block_error = f'{type(e).__name__}: {e}'
            return
        self._block_fail_since = self._block_error = None
        if self._ctl['block_id'] != period:
            self._ctl.update(block_id=period, block_info=None, block_time=None)
        self._ctl['block_exists'] = True
        if made:
            self._ctl['block_info'] = {'period': period, 'at': own.get('at'), 'branch': self.branch,
                                       'rules': own.get('rules') or [], 'numbers': own.get('numbers') or {},
                                       'reasons': content['reasons']}

    # ── the two things the bot reports ──
    def on_trade_closed(self, now, trade_key, net_pl):
        """A trade of this bot closed and its result is known. Counted once per `trade_key`. Returns the view."""
        try:
            now = float(now)
            if self._state is None:
                return self._remake_view(now)
            state, events = count_trade(self._state, self.limits, now, trade_key, net_pl, bool(self._ctl['enabled']))
            self._state = state
            self._note(events, now)
            return self._remake_view(now)
        except Exception as e:
            return self._failed(now, 'counting a closed trade', e)

    def note_other_program(self, now, text):
        """Another program trades this bot's market in this account: block this bot (6.3). Returns the view."""
        try:
            now = float(now)
            if self._state is None:
                return self._remake_view(now)
            state, events = note_other(self._state, now, text, bool(self._ctl['enabled']))
            self._state = state
            self._note(events, now)
            return self._remake_view(now)
        except Exception as e:
            return self._failed(now, 'noting another program', e)

    # ── the end of a poll ──
    def flush(self, now):
        """The file work of a poll, after its orders: what the owner pressed since and whether the account is
        blocked (for the next poll), a block file still owed, the state file, the status file, the audit lines.
        Each step by itself: one that fails does not stop the others, and is tried again later. Never raises."""
        try:
            now = float(now)
        except (TypeError, ValueError):
            return None
        problem = None
        for step in (self._flush_folder, self._flush_block, self._flush_state, self._flush_status, self._flush_audit):
            try:
                step(now)
            except Exception as e:
                problem = problem or f'the safety files: {type(e).__name__}: {e}'
        # (A refused write is handled inside its step and becomes an error after a minute. Anything else here is
        # a fault of the safety itself: it shows at once, in the view of the next poll, and blocks while ON.)
        if problem is None:
            self._flush_error = self._flush_error_since = None
        else:
            if self._flush_error is None:
                self._flush_error_since = now
            self._flush_error = problem
        return None

    def _due(self, what, now):
        at = self._retry_at.get(what)
        return at is None or now >= at or now < at - RETRY_S

    def _flush_block(self, now):
        """The block file of a block this bot holds: created now if it is not there (it could not be written in
        the poll that met the limit, or somebody removed it: the block stands, so does its file)."""
        s = self._state
        own = s.get('account_block') if s else None
        if not isinstance(own, dict) or own.get('period') != s.get('period'):
            self._block_fail_since = self._block_error = None
            return
        if self._ctl['block_id'] != s['period']:
            return                                  # (a new id was read: the next poll starts afresh under it)
        if self._ctl['block_exists'] is True:
            self._block_fail_since = self._block_error = None
            return
        try:
            os.makedirs(self.account_dir, exist_ok=True)
        except OSError:
            pass
        self._make_block_file(now)

    def _flush_state(self, now):
        if self._state is None or self.state_path is None:
            return
        text = _dumps(self._state)
        if text == self._state_saved or not self._due('state', now):
            return
        try:
            _write_atomic(self.state_path, text, durable=True)
        except (OSError, ValueError) as e:
            if self._state_fail_since is None:
                self._state_fail_since = now
            self._state_error = f'{type(e).__name__}: {e}'
            self._retry_at['state'] = now + RETRY_S
            return
        self._state_saved = text
        self._state_fail_since = self._state_error = None
        self._retry_at.pop('state', None)

    def _flush_folder(self, now):
        if self._state is None:
            # (not loaded: still read the switch, so the view says whether the failing check blocks)
            switch = _read_switch(self.account_dir)
            if switch['status'] == 'ok':
                self._ctl['enabled'] = switch['enabled']
            elif switch['status'] == 'missing':
                self._ctl['enabled'] = self.default_on
            return
        self._read_folder(now)

    def _flush_status(self, now):
        view = self._view
        if not isinstance(view, dict):
            return
        key = json.dumps({k: v for k, v in view.items() if k not in ('at', 'partner')}, sort_keys=True, default=str)
        fresh = self._status_at is not None and 0 <= now - self._status_at < STATUS_EVERY_S
        if (key == self._status_key and fresh) or not self._due('status', now):
            return
        s = self._state or {}
        # ('at' stays the time of the bot's last poll: that is what tells a reader whether the bot is running.)
        status = dict(view, branch=self.branch, partner_branch=self.partner_branch,
                      login_sha=self.login_sha, written_at=now, written_at_utc=_iso(now), version=STATE_VERSION,
                      bot_block=s.get('bot_block'), account_block=s.get('account_block'))
        try:
            _write_atomic(status_path(self.account_dir, self.branch), _dumps(status))
        except (OSError, ValueError):
            self._retry_at['status'] = now + RETRY_S
            return
        self._status_key, self._status_at = key, now
        self._retry_at.pop('status', None)

    def _flush_audit(self, now):
        if not self._audit or not self._due('audit', now):
            return
        hour = int(now // 3600)
        if hour != self._audit_hour:
            if self._audit_more:
                self._audit.insert(0, {'at': _iso(now), 'by': f'bot {self.branch}', 'more': self._audit_more})
            self._audit_hour, self._audit_lines, self._audit_more = hour, 0, 0
        path = os.path.join(self.account_dir, AUDIT_FILE)
        while self._audit:
            if self._audit_lines >= _BOT_LINES_AN_HOUR:
                self._audit_more += len(self._audit)
                del self._audit[:]
                break
            try:
                _append_line(path, self._audit[0])
            except (OSError, ValueError):
                self._retry_at['audit'] = now + RETRY_S
                return
            del self._audit[0]
            self._audit_lines += 1
        self._retry_at.pop('audit', None)

    # ── the cash read the bot owes ──
    def needs_cash(self):
        """True while the bot must read the account's balance operations at the end of its poll: a balance change
        is being checked, or the first read after a fresh start is still owed."""
        s = self._state
        if s is None or s.get('fresh_pending') or s.get('started_at') is None:
            return False
        return s.get('change_first') is not None or not s.get('cash_baseline_done')

    def cash_since(self):
        """From when to read them: an hour before the last read that succeeded; before the first one, a day before
        counting started (whatever was paid in then is inside the starting balance and is only marked as seen)."""
        s = self._state or {}
        if s.get('cash_read_ok_at') is not None:
            return s['cash_read_ok_at'] - 3600.0
        if s.get('started_at') is not None:
            return s['started_at'] - 86400.0
        return max(0.0, (self._load_error_since or 0.0) - 86400.0)

    def view(self):
        """The last view (what poll() returned last)."""
        return self._view

    def take_events(self):
        """What happened since the last call, oldest first, for the journal: {'event': 'trip' / 'fresh_start' /
        'switch' / 'cash' / 'cash_start' / 'trade' / 'hold' / 'hold_end' / 'state_put_aside', 'at', ...}. 'cash'
        carries 'found_after_s': how long after the balance moved the operation was found in the history."""
        events, self._events = self._events, []
        return events


# ───────────────────────── press: the buttons and the command line ─────────────────────────

_ACTIONS = ('unblock', 'off', 'on', 'new-account')

_MSG_UNREADABLE = 'The safety files cannot be read right now. Nothing was changed; try again.'
_MSG_UNWRITABLE = 'The safety files cannot be written right now. Nothing was changed; try again.'
_MSG_CHANGED = 'The safety changed since this page was refreshed. Check the bar and press again.'
# The restart file is there but cannot be read or holds no usable id (saved in another encoding, cut short): the
# bots keep counting under the id they had, a block stays, and only the command line can write the file anew.
_MSG_RESTART_UNREADABLE = (f'{_MSG_UNREADABLE} If this answer stays, run "safety.bat unblock" on the server: it '
                           f'writes {RESTART_FILE} anew, and both bots count again from the current balance.')
_REPAIRED = f'{RESTART_FILE} could not be read, so it was written anew.'


def _new_id(now):
    """A fresh-start id: the time of the press and 6 random hex digits. Compared for equality only; never used
    twice, so an old block file can never block a later start."""
    return f'{_name_stamp(now)}-{secrets.token_hex(3)}'


def _read_lockout(account_dir):
    """The wrong-PIN record. A missing or damaged file is an empty record (it is written anew); a file that cannot
    be opened raises OSError: the caller then refuses, it must not compare a PIN without knowing the count."""
    record = {'wrong': 0, 'locked_until': 0.0, 'lock_s': _LOCK_START_S, 'last_wrong_at': 0.0,
              'refused_hour': None, 'refused_lines': 0, 'refused_more': 0}
    status, data = _read_json(os.path.join(str(account_dir), LOCKOUT_FILE), tries=4)
    if status == 'unreadable':
        raise OSError(str(data))
    if status == 'ok' and isinstance(data, dict):
        for key in ('wrong', 'refused_lines', 'refused_more'):
            n = _num(data.get(key))
            record[key] = int(n) if n is not None and n > 0 else 0
        for key in ('locked_until', 'last_wrong_at'):
            n = _num(data.get(key))
            record[key] = n if n is not None and n > 0 else 0.0
        n = _num(data.get('lock_s'))
        record['lock_s'] = min(_LOCK_MAX_S, max(_LOCK_START_S, n)) if n is not None else _LOCK_START_S
        n = _num(data.get('refused_hour'))
        record['refused_hour'] = None if n is None else int(n)
    return record


def _write_lockout(account_dir, record, durable=True):
    _write_atomic(os.path.join(str(account_dir), LOCKOUT_FILE), _dumps(record), durable=durable)


def _audit_press(account_dir, now, by, action, result, message, extra=None, capped=False):
    """One line of the audit file for a press. Accepted presses: always. Refused ones (`capped`): at most 20 an
    hour, the rest is only counted and written as one line {'refused_more': n} when the next hour's first press
    comes. Never the PIN. Never raises: the audit file must not decide whether a press works."""
    try:
        path = os.path.join(str(account_dir), AUDIT_FILE)
        line = dict(extra or {}, at=_iso(now), t=now, by=str(by)[:200], action=action, result=result,
                    message=message)
        record = None
        try:
            record = _read_lockout(account_dir)
        except OSError:
            if capped:
                return                              # (cannot count: better no line than lines without a limit)
        hour = int(now // 3600)
        changed = False
        if record is not None and record['refused_hour'] != hour and (capped or record['refused_more'] > 0):
            # A new hour: say once how many refused presses of the old one were not written.
            if record['refused_more'] > 0 and record['refused_hour'] is not None:
                _append_line(path, {'at': _iso(now), 'refused_more': record['refused_more'],
                                    'in_the_hour_from': _iso(record['refused_hour'] * 3600.0)})
            record.update(refused_hour=hour, refused_lines=0, refused_more=0)
            changed = True
        if capped:
            if record['refused_lines'] >= _REFUSED_LINES_AN_HOUR:
                record['refused_more'] += 1
                _write_lockout(account_dir, record, durable=False)   # (a count: not worth a disk flush per request)
                return
            record['refused_lines'] += 1
            changed = True
        if changed:
            _write_lockout(account_dir, record, durable=False)
        _append_line(path, line)
    except Exception:
        pass


def _expect_differs(expect, current_id, enabled):
    """The page sends back what its bar showed ({'period', 'enabled'}). None: the caller does not check (the command
    line). Anything else that is not exactly the state of now: the page is old."""
    if expect is None:
        return False
    if not isinstance(expect, dict) or 'period' not in expect or 'enabled' not in expect:
        return True
    return expect['period'] != current_id or expect['enabled'] is not enabled


def _lock_text(until, now):
    same_day = _day_key(until) == _day_key(now)
    return f'{_clock(until)} UTC' if same_day else f'{_stamp(until)} UTC'


def _check_pin(folder, pin, now):
    """
    The PIN of an Unblock or an OFF from the page: ('right', None), or (why not, the answer for the owner) with
    why not = 'locked', 'no_pin', 'empty', 'wrong' or 'files'.

    The order matters. Locked: no comparison at all. No usable PIN on the server, or nothing typed: refused, not
    counted as a wrong PIN. Else the try is counted and SAVED before the comparison, so requests sent in the same
    instant cannot each get a free guess; a right PIN then sets the count and the lock length back to the start.
    """
    try:
        record = _read_lockout(folder)
    except OSError:
        return 'files', _MSG_UNREADABLE
    quiet_since = max(record['last_wrong_at'], record['locked_until'])
    if quiet_since and now - quiet_since >= _QUIET_RESET_S:
        # 24 hours without a wrong PIN: the next lock is short again. (Counted from the end of a lock: the time
        # the buttons were locked is not time somebody behaved.)
        record['lock_s'] = _LOCK_START_S
    if record['locked_until'] > now:
        return 'locked', (f'Too many wrong PINs: the buttons are locked until '
                          f'{_lock_text(record["locked_until"], now)}. On the server, "safety.bat unblock" '
                          '(or on, off) works without the PIN.')
    status, real = _read_pin(folder)
    if status == 'missing':
        return 'no_pin', (f'There is no PIN yet: start the dashboard once on the server (it makes {PIN_FILE} in '
                          f'{folder}), or make that file in Notepad with 4 to 32 letters and digits.')
    if status != 'ok':
        return 'no_pin', (f'The PIN file cannot be used: open {PIN_FILE} in {folder} in Notepad, keep only letters '
                          'and digits, save as UTF-8.')
    typed = pin.strip() if isinstance(pin, str) else ''
    if not typed:
        return 'empty', f'Type the PIN first. It is in the file {PIN_FILE} in {folder} on the server.'
    record['wrong'] += 1
    try:
        _write_lockout(folder, record)
    except OSError:
        return 'files', _MSG_UNWRITABLE             # (a try that cannot be counted is not compared)
    right = hmac.compare_digest(hashlib.sha256(typed.encode('utf-8', 'replace')).digest(),
                                hashlib.sha256(real.encode('utf-8')).digest())
    if right:
        record.update(wrong=0, lock_s=_LOCK_START_S, locked_until=0.0, last_wrong_at=0.0)
        try:
            _write_lockout(folder, record)
        except OSError:
            pass                                    # (the PIN was right: a count that cannot be cleared is no refusal)
        return 'right', None
    record['last_wrong_at'] = now
    if record['wrong'] >= _WRONG_MAX:
        record['locked_until'] = now + record['lock_s']
        answer = (f'Wrong PIN. Too many wrong PINs: the buttons are locked until '
                  f'{_lock_text(record["locked_until"], now)}. On the server, "safety.bat unblock" (or on, off) '
                  'works without the PIN.')
        record['wrong'] = 0
        record['lock_s'] = min(_LOCK_MAX_S, record['lock_s'] * 2.0)       # the next lock is twice as long
    else:
        left = _WRONG_MAX - record['wrong']
        answer = (f'Wrong PIN. {left} more ' + ('try' if left == 1 else 'tries')
                  + f', then the buttons lock for {_length(record["lock_s"])}.')
    try:
        _write_lockout(folder, record)
    except OSError:
        pass
    return 'wrong', answer


def press(account_dir, action, pin, by, now, need_pin=True, expect=None, default_on=True):
    """
    A button of the dashboard, or a command of safety.bat: `action` is 'unblock', 'off', 'on' or 'new-account'.
    Returns (ok, message): ok False = refused (nothing was changed); the message is for the owner.

    - `need_pin` (the dashboard, always): 'unblock' and 'off' need the PIN of safety_pin.txt; 5 wrong ones lock
      both for 10 minutes, twice as long each further time, up to 24 hours. 'on' never needs it and is never
      locked: the safety can always be switched back on. The command line passes need_pin=False.
    - `expect`: what the page showed ({'period', 'enabled'}, and 'scope': what its Unblock offered, 'account' or
      'bot'); when the files say something else now, nothing is changed (a page that is 5 s old must not do the
      opposite of what its button says): also an Unblock offered for a bot while the account is blocked now, or
      offered for the account while it is not blocked any more.
    - A restart file that cannot be read or parsed changes nothing -- except the command line's 'unblock' and 'on',
      which write it anew with a new id (a fresh start of the whole account) and say so; the page's answer then
      tells the owner to run "safety.bat unblock" on the server.
    - `by`: who, for the audit file ('dashboard <BRANCH> from <address>' or 'command line'). Never the PIN.
    - `default_on`: the switch while nobody has pressed it (SAFETY_DEFAULT_ON of the branch).
    Never raises.
    """
    with _PRESS_LOCK:
        try:
            return _press(str(account_dir), action, pin, by, float(now), bool(need_pin), expect, bool(default_on))
        except Exception as e:
            return False, f'The safety could not be changed ({type(e).__name__}: {e}). Try again.'


def _press(folder, action, pin, by, now, need_pin, expect, default_on):
    if action not in _ACTIONS:
        return False, f'Unknown action {action!r}: use unblock, off or on.'
    if action == 'new-account' and need_pin:
        return False, 'This is done on the server only: run "safety.bat new-account" there.'
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as e:
        return False, f'The account folder {folder} cannot be used ({type(e).__name__}: {e}). Nothing was changed.'

    def refuse(message, count=True):
        if count:
            _audit_press(folder, now, by, action, 'refused', message, capped=need_pin)
        return False, message

    if need_pin and action in ('unblock', 'off'):
        why_not, answer = _check_pin(folder, pin, now)
        if why_not != 'right':
            # (an empty PIN field is not a try: no audit line, as for a click the page answers by itself)
            return refuse(answer, count=why_not != 'empty')

    restart = _read_restart(folder, tries=4)
    switch = _read_switch(folder, tries=4)
    if switch['status'] == 'unreadable':
        return refuse(_MSG_UNREADABLE)
    # A restart file that cannot be read or parsed: the command line's unblock and on write it anew -- a fresh start
    # of the whole account under a new id, which is what both do anyway --, so there is always a way out of it.
    # Everything else changes nothing and says that way.
    repair = restart['status'] == 'unreadable'
    if repair and (need_pin or action not in ('unblock', 'on')):
        return refuse(_MSG_RESTART_UNREADABLE)
    current = restart['id']
    enabled = switch['enabled'] if switch['status'] == 'ok' else default_on
    if _expect_differs(expect, current, enabled):
        return refuse(_MSG_CHANGED)
    at = f'{_clock(now, seconds=True)} UTC'
    was = {'id': current, 'enabled': enabled}

    def start_again(scope, why):
        """Write a new id: every bot that reads it starts counting again (the whole account, or one bot)."""
        new = _new_id(now)
        for _ in range(8):
            # Two presses in the same second could draw the same 6 hex digits (1 in 16 million). The id must
            # differ from the one in use, and no block file may wait under it: an old block never blocks a new start.
            if new != current and _block_exists(folder, new)[0] is False:
                break
            new = _new_id(now)
        account_id = new if scope == 'account' else restart['account_id']
        _write_atomic(os.path.join(folder, RESTART_FILE),
                      _dumps({'id': new, 'scope': scope, 'account_id': account_id, 'at': _iso(now), 't': now,
                              'by': str(by)[:200], 'why': why}) + '\n', durable=True)
        return new

    def switch_to(value):
        _write_atomic(os.path.join(folder, SWITCH_FILE),
                      _dumps({'enabled': value, 'at': _iso(now), 't': now, 'by': str(by)[:200]}) + '\n',
                      durable=True)

    def done(message, **extra):
        _audit_press(folder, now, by, action, 'done', message, extra=dict(extra, was=was))
        return True, message

    try:
        if action == 'unblock':
            if not need_pin:
                # The command line: one command on the server clears every block, whatever the files show.
                if repair:
                    new = start_again('account', f'unblock from the command line ({RESTART_FILE} could not be read)')
                    return done(f'{_REPAIRED} Unblocked at {at}. Counting again from the current balance.', id=new,
                                scope='account', repaired=RESTART_FILE)
                new = start_again('account', 'unblock from the command line')
                return done(f'Unblocked at {at}. Counting again from the current balance.', id=new, scope='account')
            exists, _ = _block_exists(folder, current)
            if exists is None:
                return refuse(_MSG_UNREADABLE)
            statuses = [st for st in read_statuses(folder).values() if st.get('period') == current]
            account = bool(exists) or any(st.get('account_blocked') is True for st in statuses)
            # What the page's question offered: an Unblock confirmed for one bot ("the account's high stays") must not
            # lift a block of the account that came after the page was drawn, and one confirmed for the account
            # must not become something else when that block is gone.
            offered = expect.get('scope') if isinstance(expect, dict) else None
            if (offered == 'bot' and account) or (offered == 'account' and not account):
                return refuse(_MSG_CHANGED)
            if account:
                new = start_again('account', 'unblock of the account')
                return done(f'Unblocked at {at}. Counting again from the current balance.', id=new, scope='account')
            if any(st.get('bot_blocked') is True for st in statuses):
                new = start_again('bot', 'unblock of one bot')
                return done(f"Unblocked at {at}: losing trades in a row start again from 0. The account's high and "
                            "today's start are unchanged.", id=new, scope='bot')
            return True, 'Nothing is blocked.'
        if action == 'off':
            if not enabled:
                return True, 'The safety is already OFF.'
            switch_to(False)
            return done(f'Safety is OFF since {at}.')
        if action == 'on':
            if repair:                                  # (the command line only: see above)
                new = start_again('account', f'on from the command line ({RESTART_FILE} could not be read)')
                if enabled:
                    return done(f'{_REPAIRED} The safety is ON; counting starts again from the current balance.',
                                id=new, scope='account', repaired=RESTART_FILE)
                try:
                    switch_to(True)
                except OSError as e:
                    return refuse(f'{_REPAIRED} The safety is still OFF: its switch file cannot be written right now '
                                  f'({type(e).__name__}: {e}). Press ON again.')
                return done(f'{_REPAIRED} Safety is ON since {at}. Counting starts from the current balance.', id=new,
                            scope='account', repaired=RESTART_FILE)
            if enabled:
                return True, 'The safety is already ON.'
            # The new id first, the switch second: a crash between the two leaves the safety OFF with a fresh
            # start, never ON against the old high.
            new = start_again('account', 'on')
            try:
                switch_to(True)
            except OSError as e:
                return refuse(f'The safety is still OFF: its switch file cannot be written right now '
                              f'({type(e).__name__}: {e}). Press ON again.')
            return done(f'Safety is ON since {at}. Counting starts from the current balance.', id=new,
                        scope='account')
        # new-account: this folder moves to another account. The claim goes first: if it cannot be removed the
        # bots would refuse the new account anyway, so nothing else is changed.
        try:
            os.remove(os.path.join(folder, CLAIM_FILE))
        except FileNotFoundError:
            pass
        new = start_again('account', 'new-account')
        return done(f'The account of this folder was cleared at {at}. The first bot that starts sets the new '
                    'account, and counting starts from its balance.', id=new, scope='account')
    except OSError as e:
        return refuse(f'{_MSG_UNWRITABLE} ({type(e).__name__}: {e})')


# ───────────────────────── the command line (safety.bat) ─────────────────────────

_USAGE = '''Usage: python safety.py status|unblock|on|off|new-account [--account-dir FOLDER]
  status       show the switch, the blocks and what each bot of the account says
  unblock      lift every block of this account; both bots count again from the current balance
  on           turn the safety on; counting starts from the current balance
  off          turn the safety off: no limit stops new trades until it is turned on again
  new-account  this account folder moves to another account: stop both bots first
No PIN is asked here: whoever can run this on the server may press.'''


def status_lines(account_dir, now, default_on=True):
    """The safety of one account folder in plain lines, for `safety.bat status`."""
    folder = str(account_dir)
    now = float(now)
    lines = [f'Account folder: {folder}']
    if not os.path.isdir(folder):
        return lines + ['It is not there yet: no bot or dashboard of this account has started on this server.']
    c = read_controls(folder, default_on)
    if not c['readable']:
        lines.append('Some safety files cannot be read right now: what follows may be incomplete. Try again.')
    if c['switched_at'] is None:
        lines.append(f"Safety: {'ON' if c['enabled'] else 'OFF'} (nobody has switched it yet).")
    else:
        who = f", by {c['switched_by']}" if c['switched_by'] else ''
        lines.append(f"Safety: {'ON' if c['enabled'] else 'OFF'} since {_stamp(c['switched_at'])} UTC{who}.")
    if c['period'] == FIRST_ID:
        lines.append("Counting: from each bot's first start (nobody has pressed Unblock or ON yet).")
    elif c['period'] is not None:
        notes = [x for x in (c['pressed_why'], f"by {c['pressed_by']}" if c['pressed_by'] else None) if x]
        why = f" ({', '.join(notes)})" if notes else ''
        lines.append(f"Counting started again on {_stamp(c['pressed_at'])} UTC{why}.")
    block = c['block']
    if block is None:
        lines.append('Account block: none.')
    else:
        at = block.get('at') if block.get('at') is not None else block.get('file_time')
        said = ' '.join(block.get('reasons') or []) or 'The details of this block cannot be read.'
        lines.append(f'ACCOUNT BLOCKED since {_stamp(at)} UTC. {said}')
        if not c['enabled']:
            lines.append('(The safety is OFF, so this block stops nothing now.)')
    lines.append(f"PIN of the buttons: {'set' if c['pin_set'] else 'NOT usable'}, file {pin_path(folder)}")
    if c['locked_until'] and c['locked_until'] > now:
        lines.append(f"The buttons are locked until {_stamp(c['locked_until'])} UTC after wrong PINs "
                     '(this command line is not).')
    statuses = read_statuses(folder)
    if not statuses:
        lines.append('No bot of this account has written its status yet.')
    for branch in sorted(statuses):
        st = statuses[branch]
        seen = _num(st.get('at'))
        name = f'{_cap(_bot(branch))} ({branch})'
        if seen is None:
            lines.append(f'{name}: its status file says nothing usable.')
            continue
        age = now - seen
        running = f'seen {_ago(age)} ago' if age <= PARTNER_STALE_S else \
            f'NOT RUNNING: last seen {_ago(age)} ago ({_stamp(seen)} UTC)'
        lines.append(f'{name}: {running}.')
        if isinstance(st.get('period'), str) and c['period'] is not None and st['period'] != c['period']:
            lines.append('    It has not taken the last press yet (it does at its next poll, or when it starts).')
        for sentence in st.get('reasons') or []:
            if isinstance(sentence, str):
                lines.append(f'    {sentence}')
        if st.get('error'):
            lines.append(f"    Problem: {st['error']}")
        drop = st.get('drop') if isinstance(st.get('drop'), dict) else {}
        day = st.get('day') if isinstance(st.get('day'), dict) else {}
        streak = st.get('streak') if isinstance(st.get('streak'), dict) else {}
        meters = []
        if drop.get('limit') is not None:
            meters.append(f"drop from the high {_pct(drop.get('pct'))} of the {_plain(drop.get('limit'))}% limit")
        if day.get('limit') is not None:
            meters.append(f"loss today {_pct(day.get('pct'))} of the {_plain(day.get('limit'))}% limit")
        if streak.get('limit') is not None:
            meters.append(f"losing trades in a row {streak.get('count')} of {streak.get('limit')}")
        if meters:
            lines.append('    ' + _cap(', '.join(meters)) + '.')
    return lines


def main(argv=None, now=None):
    """python safety.py status|unblock|on|off|new-account [--account-dir FOLDER]

    Without --account-dir the folder is the one of this branch (constants.OUTPUT_DIR and ACCOUNT_FOLDER).
    'status' prints the state; the others press without the PIN, as 'command line'. Returns the exit code:
    0 done, 1 refused, 2 the command was not understood. `now` is for tests: the command line reads the clock."""
    args = list(sys.argv[1:] if argv is None else argv)
    folder, words, i = None, [], 0
    while i < len(args):
        a = str(args[i])
        if a == '--account-dir' and i + 1 < len(args):
            folder = str(args[i + 1])
            i += 2
            continue
        if a.startswith('--account-dir='):
            folder = a.split('=', 1)[1]
            i += 1
            continue
        words.append(a)
        i += 1
    command = words[0].lower() if len(words) == 1 else None
    if command not in ('status',) + _ACTIONS or folder == '':
        print(_USAGE)
        return 2
    default_on = True
    if folder is None:
        try:
            import constants        # (only here: everything else in this file takes its folders as arguments)
            folder = account_dir(constants.OUTPUT_DIR, constants.ACCOUNT_FOLDER)
            default_on = bool(getattr(constants, 'SAFETY_DEFAULT_ON', True))
        except Exception as e:
            print(f'The account folder of this branch cannot be found in constants.py ({type(e).__name__}: {e}). '
                  'Give it with --account-dir FOLDER.')
            return 1
        if os.name != 'nt' and (ntpath.splitdrive(folder)[0] or '\\' in folder):
            print(f'The account folder of this branch is {folder}, a folder of the Windows server. Run this on the '
                  'server, or give a folder with --account-dir FOLDER.')
            return 1
    t = time.time() if now is None else float(now)
    if command == 'status':
        for line in status_lines(folder, t, default_on):
            print(line)
        return 0
    ok, message = press(folder, command, None, 'command line', t, need_pin=False, default_on=default_on)
    print(message)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
