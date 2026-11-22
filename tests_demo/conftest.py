"""
Tests of a real-money branch: the design levers (trend, volatility unit, target / stop / cap, loss pause,
macd_turn ladder), the account the bot may trade (a real, hedging account: the one of its credentials), its own
mark on its orders (magic, comment), sizing from its share of the account balance, and restart recovery; the Turtle
(STRATEGY = 'turtle', turtle.py): test_turtle_*.py, its replay against the backtest in test_turtle_replay.py.

Run from any folder:  python3 -B -m pytest <branch>/tests_demo -q -p no:cacheprovider
(-B: Python writes no bytecode into the branch; -p no:cacheprovider: pytest writes no cache folder.)
Nothing here talks to a terminal: MetaTrader5 is replaced by tests_demo/fake_mt5.py (a real, hedging USD account;
every bot gets the credentials of that account).
Nothing here writes outside pytest's tmp folders: every bot the tests build (this branch's and the old code's
baseline of test_live_equivalence.py) has its OUTPUT_DIR -- its state, logs and JSON files -- in a folder named
bot_output inside a new private folder (the test's tmp_path), so the account's shared folder, which lies beside
OUTPUT_DIR (safety.account_dir), is private to the test too; any write into the real output folder
(C:\\Alcadeias\\...: on the server the running bots' own files and their accounts' safety files), whatever function
makes it, is refused and fails the run, and so does bytecode written into the branch (a run without -B): see the
end of this file.
No test holds a value of the deployment block of constants.py (branch, magic, port, limits): they read DEFAULTS.
"""
import ntpath
import os
import subprocess
import sys
import tempfile
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True      # keep __pycache__ out of the branch

import fake_mt5 as F  # noqa: E402

START = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc).timestamp()   # a Tuesday

# The tests exercise the code, not the design a branch has chosen: every bot here starts from the DEFAULT
# section of this branch's constants.py (everything above the '# ─── Design examples ───' marker, i.e. the
# live levers plus this branch's deployment block), then each test sets what it needs. A design block appended
# at the end of constants.py therefore changes nothing here; test_design.py checks that block on its own.
# The auto-safety's limits are OFF in DEFAULTS (None = that rule is off): a replay must take the strategy's
# trades, not stop after a few losses in a row. A test of the safety sets its own limits; AS_WRITTEN has the values as
# the branch has them.
_EXAMPLES_MARKER = '# ─── Design examples ───'


def _default_constants():
    text = (ROOT / 'constants.py').read_text(encoding='utf-8')
    head = text.split(_EXAMPLES_MARKER, 1)[0]
    ns = {}
    exec(compile(head, str(ROOT / 'constants.py'), 'exec'), ns)
    return {k: v for k, v in ns.items() if k.isupper()}


AS_WRITTEN = _default_constants()                 # the head of constants.py exactly as this branch has it
SAFETY_OFF = {'SAFETY_DROP_PCT': None, 'SAFETY_DAY_PCT': None, 'SAFETY_STREAK_N': None}
DEFAULTS = {**AS_WRITTEN, **SAFETY_OFF}
MAGIC = DEFAULTS['MAGIC']
BRANCH = DEFAULTS['BRANCH']
COMMENT = str(DEFAULTS['ORDER_COMMENT'] if DEFAULTS['ORDER_COMMENT'] is not None else BRANCH)[:31]
SHARE = DEFAULTS['ACCOUNT_SHARE']           # this bot's part of the account balance (units are sized from it)


# ───────────────────────── every bot the tests build writes in a tmp folder ─────────────────────────
# The branch's OUTPUT_DIR is an absolute Windows path (C:\Alcadeias\<branch>). On the server a test that leaves it
# there writes the running bot's own state file (a fake loss blocks its entries for hours) and logs; on macOS it
# makes a folder literally named 'C:\Alcadeias\<branch>' in the working folder. So every load of the bot's modules
# (F.bot_modules: the mods fixture, run_bot, the old code's baseline, a test's own load) gets an OUTPUT_DIR in a tmp
# folder -- and with it the state folder (OUTPUT_DIR/state, also the Turtle's) and the logs -- unless the test gives
# one that is not the real one.
# The account's shared folder (the safety files of the two bots of one account) is not inside OUTPUT_DIR but BESIDE
# it: safety.account_dir(OUTPUT_DIR, ACCOUNT_FOLDER) = <the folder OUTPUT_DIR is in>/<ACCOUNT_FOLDER>. So the
# OUTPUT_DIR a bot gets here is always <a new private folder>/bot_output: the folder beside it then belongs to that
# test (or that module fixture, or that probe) alone, and a block or a switch one replay leaves there never reaches
# the next. A test that chooses its own OUTPUT_DIR must do the same (tmp_path / 'bot_output', never tmp_path itself,
# whose parent every test of the run shares): shared_account_dir() says so, and the run fails at its end when a
# shared account folder was made.

REAL_OUTPUT_DIR = DEFAULTS['OUTPUT_DIR']


def _top_folder(path):
    """'C:\\Alcadeias\\<branch>' -> 'C:\\Alcadeias': the folder every bot's output (and every account's shared folder) is
    in on the server."""
    drive, rest = ntpath.splitdrive(ntpath.normpath(str(path)))
    parts = [p for p in rest.split('\\') if p]
    return drive + '\\' + parts[0] if parts else ntpath.normpath(str(path))


REAL_OUTPUT_ROOT = _top_folder(REAL_OUTPUT_DIR)


def is_real_output(path):
    """True for a path in the server's output folders (C:\\Alcadeias\\...): on Windows in that folder; elsewhere a
    name that starts with 'C:\\Alcadeias' (what the Windows path becomes there, relative to the working folder)."""
    try:
        p = os.path.abspath(os.fsdecode(os.fspath(path)))
    except (TypeError, ValueError):
        return False                                   # (a file descriptor)
    if os.name == 'nt':
        p, r = os.path.normcase(p), os.path.normcase(REAL_OUTPUT_ROOT).rstrip('\\')
        return p == r or p.startswith(r + '\\')
    root = REAL_OUTPUT_ROOT.casefold()
    return any(part.casefold().startswith(root) for part in p.split(os.sep))


class _BotOutput:
    current = None        # the running test's folder for the bots' output: tmp_path / 'bot_output'
    factory = None        # pytest's tmp_path_factory (a module fixture's bot: a new tmp folder for each load)


def bot_output_dir():
    """Where a bot loaded now writes: <a new private folder>/bot_output in every case, so the account folder
    beside it is private too. In a test: the test's tmp_path / 'bot_output' (the same for every bot of the test, so
    a restart finds its files, and two bots of one test share their account folder as the two bots of an account
    do); outside a test (a module-scoped fixture): in a new folder under pytest's basetemp; outside pytest (a probe
    script): in a new temporary folder."""
    if _BotOutput.current is not None:
        return _BotOutput.current
    if _BotOutput.factory is not None:
        return _BotOutput.factory.mktemp('bot') / 'bot_output'
    return Path(tempfile.mkdtemp(prefix='bot_')) / 'bot_output'


def _shared_folders():
    """Folders every test of the run (or every program of this PC) can write in: pytest's basetemp and the system's
    temporary folder. An account folder directly in one of them would be shared between tests."""
    out = [Path(tempfile.gettempdir()).resolve()]
    if _BotOutput.factory is not None:
        out.append(Path(_BotOutput.factory.getbasetemp()).resolve())
    return out


def account_dir_of(output_dir):
    """The account folder of a bot whose OUTPUT_DIR is `output_dir`: the folder ACCOUNT_FOLDER beside it (what
    safety.account_dir gives for a path of this system)."""
    return Path(os.path.normpath(str(output_dir))).parent / str(DEFAULTS['ACCOUNT_FOLDER'])


def shared_account_dir(output_dir):
    """True when the account folder beside `output_dir` would lie in a folder the tests share (a test gave its
    tmp_path itself, or a folder straight under the system's temporary folder, as OUTPUT_DIR)."""
    try:
        return account_dir_of(output_dir).parent.resolve() in _shared_folders()
    except OSError:
        return False


def _bot_modules_in_tmp(load):
    @contextmanager
    def bot_modules(root, fake, clock, overrides=None):
        ov = dict(overrides or {})
        out = ov.get('OUTPUT_DIR')
        if out is None or is_real_output(out) or not os.path.isabs(str(out)):
            ov['OUTPUT_DIR'] = str(bot_output_dir())
        elif shared_account_dir(out):
            warnings.warn(f'tests_demo: OUTPUT_DIR {out} has its account folder {account_dir_of(out)} in a folder '
                          f"every test shares: give the bot <a private folder>/bot_output (tmp_path / 'bot_output')",
                          stacklevel=3)
        with load(root, fake, clock, ov) as mods:
            yield mods
    bot_modules.in_tmp = True
    return bot_modules


if not getattr(F.bot_modules, 'in_tmp', False):
    F.bot_modules = _bot_modules_in_tmp(F.bot_modules)     # (run_bot finds it here too)


def run_bot(fake, clock, overrides=None, symbol='XAUUSDm', **kw):
    """Replay this branch's bot from its default constants plus `overrides`."""
    return F.run_bot(ROOT, fake, clock, symbol, overrides={**DEFAULTS, **(overrides or {})}, **kw)


# ───────────────────────── a whole start, as the launcher makes it ─────────────────────────
# The branch's own mt5_credentials.json is never read by a test, and its symbols.json names the branch's symbol:
# a test of the start gives the bot stand-ins for both (app.py finds them where it opens the two files).

def symbols_config(symbol='XAUUSDm', step=2500, unit_max=10, **changes):
    """A symbols.json with one active symbol (`changes` on top of the whole file)."""
    return dict({'brake': 0, 'mtqty': 0.01, 'trading_window': {'enabled': False},
                 'symbols': [{'symbol': symbol, 'is_active': True, 'step_up_balance': step,
                              'unit_max_limit': unit_max}]}, **changes)


def stand_in_files(m, credentials=None, symbols=None):
    """The bot's modules `m` find these where they open mt5_credentials.json / symbols.json; every other file is the
    real one. For each: a dict (credentials: the "live" block; symbols: the whole file), a str (the file's text as
    it is), an exception (raised by the open: FileNotFoundError() = the file is missing), a callable (asked at each
    open for one of those), or None (credentials: the fake's account, F.CREDS; symbols: one active XAUUSDm).
    Returns the list of the names it was opened under, in order."""
    import builtins
    import io
    import json
    opened = []

    def content(spec, wrap):
        if callable(spec):
            spec = spec()
        if isinstance(spec, BaseException):
            raise spec
        return spec if isinstance(spec, str) else json.dumps(wrap(spec))

    def fake_open(path, *a, **k):
        name = os.path.basename(str(path))
        if name == 'mt5_credentials.json':
            opened.append(name)
            return io.StringIO(content(F.CREDS if credentials is None else credentials, lambda b: {'live': b}))
        if name == 'symbols.json':
            opened.append(name)
            return io.StringIO(content(symbols_config() if symbols is None else symbols, lambda c: c))
        return builtins.open(path, *a, **k)
    m.app.open = fake_open
    return opened


def start_job(m, symbol='XAUUSDm', events=None, loop=None):
    """One start of app.py as main() makes it, up to the trading loop: (the bot, True when the start got as far as
    the loop). The loop itself is not run (`loop`: what runs in its place, given the bot), so a start that passed
    ends here with EXIT_RETRY -- the stand-in loop comes back at once -- and bot.exit_code is otherwise what the
    launcher would read. `events`: a list that gets every event the bot logs ({'event', 'tag', 'details'}), beside
    the strategy log the bot really writes. The trace (tracelog.py) is off: what the bot said is in its console
    lines and in bot._boot_lines, the lines it hands to the text log ((time, level, category, text, values, ...))."""
    bot = m.app.MT5TradingBot(mode='live', target_symbol=symbol)
    bot.trace_enabled = False
    reached = []

    def stand_in_loop():
        reached.append(True)
        if loop is not None:
            loop(bot)
    bot.run_multithreaded_processing = stand_in_loop
    if events is not None:
        log_event = bot._log_event

        def recording(sym, event, tag, details=None, server_time=None):
            events.append({'event': event, 'tag': tag, 'details': dict(details or {})})
            log_event(sym, event, tag, details, server_time)
        bot._log_event = recording
    bot.execute_job()
    return bot, bool(reached)


def boot_text(bot):
    """Everything a bot handed to the text log before its trace existed, as one text."""
    return '\n'.join(f'{rec[1]} | {rec[2]} | {rec[3]} | {rec[4]}' for rec in bot._boot_lines)


def account_folder(m):
    """The account folder of the bot's modules `m` (as the bot derives it)."""
    return Path(m.app.safety.account_dir(m.app.OUTPUT_DIR, m.constants.ACCOUNT_FOLDER))


def names_calls(fake):
    """The names of the terminal's session calls so far: 'initialize', 'login', 'shutdown'."""
    return [c[0] for c in fake.calls]


# ───────────────────────── assertions on large values report a short message ─────────────────────────
# A test that searches a whole page, every file of a folder or a whole trace asserts on the short list of what is
# wrong (found, changed), never with `x not in big_text` or `big == big`: when one of those fails, pytest explains it
# with difflib over the whole values -- on a page dumped as one line of megabytes that took more than two hours once
# and stalled the run. In case a test still does, short_explanations() below keeps pytest's explanation short.

def found(haystack, *needles, width=90, most=3):
    """Where any of `needles` is in `haystack` (a text, bytes, or any container `in` works on): for a text a short
    piece around each of the first `most` places ("'needle' at 1234: ...text..."), for a container the needles it
    holds; [] = none is there. Assert on it: `assert not found(page, secret), where`."""
    out = []
    if isinstance(haystack, (str, bytes)):
        text = haystack
        for needle in needles:
            n = needle.encode('utf-8') if isinstance(text, bytes) and isinstance(needle, str) else needle
            i = text.find(n)
            while i >= 0 and len(out) < most:
                piece = text[max(0, i - width):i + len(n) + width]
                if isinstance(piece, bytes):
                    piece = piece.decode('utf-8', 'replace')
                out.append(f'{needle!r} at {i}: ...{piece}...')
                i = text.find(n, i + max(1, len(n)))
        return out
    return [f'{needle!r}'[:200] for needle in needles if needle in haystack][:most]


def changed(before, after, most=10):
    """What differs between two snapshots {key: value} (a folder's files and their sizes and times, a set of
    files' contents): ['added <key>', 'removed <key>', 'changed <key>'], the first `most`; [] = the same. Assert on
    it: `assert not changed(before, _tree(folder))`."""
    out = [f'added {k}' for k in after if k not in before]
    out += [f'removed {k}' for k in before if k not in after]
    out += [f'changed {k}' for k in before if k in after and before[k] != after[k]]
    return out[:most]


def differs(left, right):
    """[] when left == right, else a few short lines that say where they differ (the lengths, the first items or
    keys that differ): for assertions on whole replays and snapshots -- `assert not differs(orders(run.fake),
    orders(ref.fake))` -- whose failure must not print, or diff, the whole values."""
    if left == right:
        return []
    return _differences(left, right) or [f'{type(left).__name__} != {type(right).__name__}'[:200]]


def _differences(left, right):
    """Where two values that are not equal differ, in a few lines of at most a few hundred characters."""
    out = []
    if isinstance(left, (str, bytes)) and isinstance(right, type(left)):
        i = next((k for k, (a, b) in enumerate(zip(left, right)) if a != b), min(len(left), len(right)))
        out += [f'lengths {len(left)} and {len(right)}, the first difference at {i}:',
                f'  left:  ...{left[max(0, i - 60):i + 60]!r}...', f'  right: ...{right[max(0, i - 60):i + 60]!r}...']
    elif isinstance(left, dict) and isinstance(right, dict):
        from itertools import islice
        out += [f'only left: {k!r}'[:160] for k in islice((k for k in left if k not in right), 5)]
        out += [f'only right: {k!r}'[:160] for k in islice((k for k in right if k not in left), 5)]
        diff = list(islice((k for k in left if k in right and left[k] != right[k]), 3))
        out += [f'differs at {k!r}: {left[k]!r}'[:300] + f' != {right[k]!r}'[:300] for k in diff]
    elif isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            out.append(f'lengths {len(left)} and {len(right)}')
        i = next((k for k, (a, b) in enumerate(zip(left, right)) if a != b), None)
        if i is not None:
            out += [f'the first difference at index {i}:', f'  left:  {left[i]!r}'[:400], f'  right: {right[i]!r}'[:400]]
        elif len(left) != len(right):
            longer = left if len(left) > len(right) else right
            out.append(f'  the first extra item: {longer[min(len(left), len(right))]!r}'[:400])
    elif isinstance(left, (set, frozenset)) and isinstance(right, (set, frozenset)):
        out += [f'only left: {x!r}'[:160] for x in list(left - right)[:5]]
        out += [f'only right: {x!r}'[:160] for x in list(right - left)[:5]]
    return out


_LARGE = 20000          # characters (a text, bytes) or items (a list, dict, set) from which a side counts as large


def _large(value, budget=_LARGE):
    """True when `value` is large to explain: a text of _LARGE characters or more, or a container with that many
    items or nested items (counted with a bounded walk: the measure itself stays cheap)."""
    if isinstance(value, (str, bytes, bytearray)):
        return len(value) >= budget
    stack, seen = [value], 0
    while stack:
        v = stack.pop()
        if isinstance(v, (str, bytes, bytearray)):
            seen += 1 + len(v) // 64
        elif isinstance(v, dict):
            seen += len(v)
            stack.extend(v.values())
        elif isinstance(v, (list, tuple, set, frozenset)):
            seen += len(v)
            stack.extend(v)
        else:
            seen += 1
        if seen >= budget // 10:
            return True
    return False


def _short_compare(op, left, right):
    """A few lines that say what differs, in place of pytest's diff of the whole values: its summary line (both
    sides cut short), the sizes, and where the needle is / where the two differ."""
    from _pytest._io.saferepr import saferepr

    def size(v):
        return f'{type(v).__name__} of {len(v)}' if hasattr(v, '__len__') else type(v).__name__
    lines = [f'{saferepr(left, maxsize=60)} {op} {saferepr(right, maxsize=60)}',
             f'(a large value: {size(left)} {op} {size(right)}; only a short explanation is drawn)']
    if op == 'not in' and isinstance(right, (str, bytes)) and isinstance(left, type(right)):
        lines += found(right, left, width=70, most=2)
    elif op == '==':
        lines += _differences(left, right)
    return lines


def short_explanations():
    """Make pytest's explanation of a failing comparison short when one of its sides is large (_large): its own
    explanation of `x not in text` and of `a == b` runs difflib over the whole values, which on a large one can take
    hours. Small values keep pytest's own explanation. Done once, at the start of the run; nothing happens if this
    pytest has no such function (the assertions of the suite are short on their own: found, changed)."""
    try:
        from _pytest.assertion import util
    except Exception:  # noqa: BLE001 -- another pytest: the suite's own assertions stay short anyway
        return False
    full = getattr(util, 'assertrepr_compare', None)
    if full is None or getattr(full, 'short_for_large', False):
        return full is not None

    def assertrepr_compare(config, op, left, right, *args, **kwargs):
        # (only `not in` and `==` are explained with difflib; pytest's other explanations stay cheap)
        try:
            if op in ('not in', '==') and (_large(left) or _large(right)):
                return _short_compare(op, left, right)
        except Exception:  # noqa: BLE001 -- the explanation must never fail the test in another way
            return None
        return full(config, op, left, right, *args, **kwargs)

    assertrepr_compare.short_for_large = True
    util.assertrepr_compare = assertrepr_compare
    return True


# ───────────────────────── the wording of a real-money branch ─────────────────────────
# Nothing the owner can read may call this bot, its account or its balance by the words of the forward test it came
# from: no string literal of the bot's code says 'demo', 'virtual' or 'slot' (docstrings and comments are not shown
# to anybody and are not checked). Two exact literals are allowed: the name of the MT5 constant, and 'demo' itself --
# the name of the "demo" block of the credentials file and of the terminal's trade mode: a refusal has to be able to
# say that the account MetaTrader 5 holds is a demo account.
WORDING = ('demo', 'virtual', 'slot')
WORDING_ALLOWED = ('ACCOUNT_TRADE_MODE_DEMO', 'demo')


def string_literals(path):
    """(line, text) of every string literal of a Python file that is not a docstring, in the file's order; the
    fixed parts of an f-string count one by one."""
    import ast
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))
    found = [(node.lineno, node.col_offset, node.value) for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]
    return [(line, text) for line, _, text in sorted(found)]


def wording_offenders(path, words=WORDING, allowed=WORDING_ALLOWED):
    """The string literals of a Python file (docstrings aside) that hold one of `words`, letter case ignored, and
    are not one of the `allowed` exact literals: ['<line>: <text>', ...]."""
    return [f'{line}: {text!r}' for line, text in string_literals(path)
            if text not in allowed and any(w in text.casefold() for w in words)]

_LIVE_FILES = ('app.py', 'strategy.py', 'indicator.py', 'mt5_helper.py', 'constants.py', 'symbols.json')


# The check: while pytest runs, every write into the real output folder is refused -- it never happens -- and recorded,
# whatever function makes it. An audit hook (sys.addaudithook: Python raises an audit event inside every file
# operation) sees open() for writing -- builtins.open, io.open, os.open, pathlib -- and mkdir, rename / replace, remove /
# unlink, rmdir, truncate, chmod, chown, utime, link, symlink and shutil's copies, moves, rmtree and archives. At the
# end the run fails if any was tried, if a 'C:\Alcadeias...' folder appeared in the working folder, or if Python wrote
# bytecode into the branch (a run without -B).
_GUARD = getattr(sys, '_tests_demo_guard', None)      # (one hook per process: an audit hook cannot be removed)
if _GUARD is None:
    _GUARD = sys._tests_demo_guard = {'on': False, 'refused': []}
REFUSED_WRITES = _GUARD['refused']
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_CHANGED_PATHS = {         # audit event -> the positions of its arguments that name a path it changes
    'os.mkdir': (0,), 'os.rename': (0, 1), 'os.remove': (0,), 'os.rmdir': (0,), 'os.truncate': (0,),
    'os.chmod': (0,), 'os.chown': (0,), 'os.chflags': (0,), 'os.utime': (0,), 'os.link': (1,), 'os.symlink': (1,),
    'os.setxattr': (0,), 'os.removexattr': (0,),
    'shutil.copyfile': (1,), 'shutil.copymode': (1,), 'shutil.copystat': (1,), 'shutil.copytree': (1,),
    'shutil.move': (0, 1), 'shutil.rmtree': (0,), 'shutil.chown': (0,), 'shutil.make_archive': (0,),
    'shutil.unpack_archive': (1,),
}


def changed_paths(event, args):
    """The paths an audited operation would change (none for a read)."""
    if event == 'open':
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        if (isinstance(flags, int) and flags & _WRITE_FLAGS) or (isinstance(mode, str) and set(mode) & set('wax+')):
            return tuple(args[:1])
        return ()
    return tuple(args[i] for i in _CHANGED_PATHS.get(event, ()) if i < len(args))


def _audit(event, args):
    if not _GUARD['on'] or (event != 'open' and event not in _CHANGED_PATHS):
        return
    for p in changed_paths(event, args):
        if isinstance(p, (str, bytes, os.PathLike)) and is_real_output(p):
            _GUARD['refused'].append(f'{event} {p!r}')
            raise PermissionError(f'tests_demo: {event} {p!r} refused: a test must not write in the real output '
                                  f'folder {REAL_OUTPUT_DIR} (its bot belongs in tmp_path)')


if not _GUARD.get('hooked'):
    sys.addaudithook(_audit)
    _GUARD['hooked'] = True


def stray_bytecode(dont_write_bytecode, pycache_prefix, folder=HERE):
    """The bytecode files Python wrote into the branch: pytest writes this file's own (tests_demo/__pycache__/
    conftest.*.pyc) when it loads it -- before the `sys.dont_write_bytecode = True` above -- unless Python was started
    with -B or PYTHONDONTWRITEBYTECODE (dont_write_bytecode), or PYTHONPYCACHEPREFIX puts bytecode elsewhere."""
    cache = Path(folder) / '__pycache__'
    if dont_write_bytecode or pycache_prefix or not cache.is_dir():
        return []
    return sorted(str(p) for p in cache.iterdir())


def pytest_configure(config):
    config.addinivalue_line('markers', 'slow: replays the whole bot loop over a synthetic market (tens of seconds)')
    _GUARD['on'] = True                     # from before the tests are collected
    short_explanations()                    # (a failing comparison of large values explains itself in short)


def pytest_unconfigure(config):
    _GUARD['on'] = False


@pytest.fixture(scope='session', autouse=True)
def _nothing_outside_tmp(tmp_path_factory):
    """The whole run writes nothing outside pytest's tmp folders: no write into the real output folder, no
    'C:\\Alcadeias...' folder left in the working folder, no bytecode in the branch."""
    cwd = Path.cwd()
    before = {p.name for p in cwd.iterdir()}
    _BotOutput.factory = tmp_path_factory
    # (beside a bot's folder: the account folder -- claim, login budget, safety files -- and the claims of the
    # MetaTrader 5 installations; made in a shared folder, one test's account would be in the next test's way)
    shared = [d / name for d in _shared_folders() for name in (str(DEFAULTS['ACCOUNT_FOLDER']), 'terminal_claims')]
    shared = [d for d in shared if not d.exists()]          # (one an earlier run left is not this run's)
    try:
        yield
    finally:
        _BotOutput.factory = None
    left = sorted(p.name for p in cwd.iterdir() if p.name not in before and is_real_output(p))
    pyc = stray_bytecode(sys.flags.dont_write_bytecode, sys.pycache_prefix)
    problems = (list(REFUSED_WRITES) + [f'left in the working folder {cwd}: {n}' for n in left]
                + [f'bytecode written into the branch: {p} (run the tests with python3 -B, and delete '
                   f'{HERE / "__pycache__"})' for p in pyc]
                + [f"a folder every test shares was made beside a bot's folder: {d} (a bot's OUTPUT_DIR must be "
                   f"<a private folder>/bot_output, e.g. tmp_path / 'bot_output', so that the folders beside it -- "
                   f"its account folder, the terminal claims -- are its own)"
                   for d in shared if d.exists()])
    if problems:
        pytest.fail('tests_demo wrote outside its tmp folders:\n  ' + '\n  '.join(problems[:20]), pytrace=False)


@pytest.fixture(autouse=True)
def _bot_output_in_tmp_path(tmp_path):
    """The bots a test builds write in its tmp_path / 'bot_output' (all of them, so a restart finds its files)."""
    _BotOutput.current = tmp_path / 'bot_output'
    try:
        yield _BotOutput.current
    finally:
        _BotOutput.current = None


@pytest.fixture(scope='session', autouse=True)
def _traces_in_temp(tmp_path_factory):
    """The trace files and text log (tracelog.py) of a bot that make_bot builds without a trace_dir go to a new folder
    under this pytest temp folder (F.TRACE_ROOT); a bot with keep_writers writes them into its OUTPUT_DIR, which is in
    the test's tmp_path (_bot_modules_in_tmp above)."""
    F.TRACE_ROOT = str(tmp_path_factory.mktemp('trace'))
    try:
        yield
    finally:
        F.TRACE_ROOT = None


@pytest.fixture(scope='session')
def root():
    return ROOT


@pytest.fixture(scope='session')
def baseline_root(tmp_path_factory):
    """The bot as it was before the port: the tree of the commit the first demo branch started from ('demo: <branch>
    - demo account only, ...': the old live code v3.9.2, which knows no magic number and checks no account),
    exported from git. Its bot runs in its own mode ('demo'; F.run_bot(..., mode='demo')): only the mode word
    differs, the old code trades whatever account the terminal holds. Skipped when git or that commit is not
    there."""
    try:
        sha = subprocess.run(['git', '-C', str(ROOT), 'log', '--format=%H', '--grep', '^demo: .* - demo account only',
                              '-n', '1'], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sha = ''
    if not sha:
        pytest.skip("no 'demo: ...' commit to compare with")
    out = tmp_path_factory.mktemp('baseline')
    for name in _LIVE_FILES:
        blob = subprocess.run(['git', '-C', str(ROOT), 'show', f'{sha}:{name}'], capture_output=True, check=True).stdout
        (out / name).write_bytes(blob)
    # the baseline must be the code BEFORE the port, or the comparison proves nothing
    assert b'FORCE_CLOSE_ENABLED' not in (out / 'constants.py').read_bytes(), f'{sha} already holds the port'
    return out


@pytest.fixture
def mods(tmp_path):
    """The bot's modules on a small fake terminal (a few hours of quotes), for unit-level tests, from the
    default constants plus overrides: mods(TREND_TF='H1'). mods(_as_written=True) loads constants.py as it
    is, design block included."""
    stack = []

    def _load(fake=None, clock=None, _as_written=False, **overrides):
        if fake is None:
            m1, t, b, a = F.random_walk_market(START, 3600, seed=11, warm_days=30)
            clock = F.FakeClock(START + 0.5, START + 3600)
            fake = F.FakeMT5('XAUUSDm', t, b, a, clock, warm_m1=m1, contract_size=100.0)
        cm = F.bot_modules(ROOT, fake, clock, overrides if _as_written else {**DEFAULTS, **overrides})
        m = cm.__enter__()
        stack.append(cm)
        m.fake, m.clock = fake, clock
        return m

    yield _load
    while stack:
        stack.pop().__exit__(None, None, None)


def market(seconds, seed=3, sigma=0.15, warm_days=30, symbol='XAUUSDm', contract=100.0, price0=2000.0,
           spread=0.12, balance=2000.0, restarts=(), report_contract_size=True):
    """A synthetic random-walk market and a fake terminal on it, starting at START."""
    m1, t, b, a = F.random_walk_market(START, seconds + 120, seed=seed, sigma_per_s=sigma, price0=price0,
                                       spread=spread, warm_days=warm_days)
    clock = F.FakeClock(START + 0.5, START + seconds, restarts_s=[START + r for r in restarts])
    fake = F.FakeMT5(symbol, t, b, a, clock, warm_m1=m1, contract_size=contract, balance=balance,
                     report_contract_size=report_contract_size)
    return fake, clock


# The design levers on fast timeframes (the backtester's scaled parity grid, map_parity §7): every rule fires
# within minutes of synthetic quotes. XAU Top 1 shape: H1 -> M1 entry votes, M5 trend, M1 volatility unit,
# one 1-unit add on a macd_turn of the M1 vote at >= 1 unit against the entry, a longer pause after a loss.
SCALED = {
    'DESIGN_NAME': 'scaled_test',
    'OPEN_SCORE_WEIGHTS': {'M1': 1}, 'FORCE_CLOSE_SCORE_WEIGHTS': {'M1': 1},
    'SLOPE_TIMEFRAMES': ['TIMEFRAME_M1'],
    'ENTRY_AGREE_S': 0, 'FORCE_CLOSE_ENABLED': False,
    'TREND_TF': 'M5', 'VOL_TF': 'M1', 'VOL_LEN': 10,
    'TARGET_USD_PER_UNIT': None, 'STOP_LOSS_USD_PER_UNIT': None,
    'TARGET_VOL': 2.0, 'STOP_VOL': 2.0, 'VOL_CAP_USD_PER_UNIT': 0.0,
    'LOSS_COOLDOWN_S': 240, 'REENTRY_COOLDOWN_SECONDS': 30,
    'MAX_ADDS': 1, 'LADDER_TRIGGER': 'macd_turn', 'LADDER_TFS': ['M1', 'M5', 'M15', 'H1', 'H4'],
    'LADDER_GAP_VOL': 1.0, 'LADDER_MULTIPLIERS': [1, 1, 1, 1],
}


def crafted_market(h1_closes, tick_prices, spread=0.1, contract=100.0, symbol='XAUUSDm', balance=2000.0):
    """H1 history bars closing at `h1_closes` (flat inside each hour, so every timeframe agrees), the last one
    ending at START, then one tick per second at `tick_prices` from START + 1 s."""
    n = len(h1_closes)
    t_h1 = int(START) - 3600 * np.arange(n, 0, -1)
    t_m1 = (t_h1[:, None] + 60 * np.arange(60)[None, :]).ravel().astype(np.int64)
    c = np.repeat(np.asarray(h1_closes, float), 60)
    m1 = {'t': t_m1, 'o': c, 'h': c, 'l': c, 'c': c, 'n': np.ones(len(c), np.int64)}
    k = len(tick_prices)
    t_ms = (int(START) * 1000 + 1000 + 1000 * np.arange(k)).astype(np.int64)
    bid = np.asarray(tick_prices, float)
    clock = F.FakeClock(START + 1.5, START + k)
    fake = F.FakeMT5(symbol, t_ms, bid, bid + spread, clock, warm_m1=m1, contract_size=contract, balance=balance)
    return fake, clock


def baskets(fake, magic=None):
    """The closed baskets in the fake terminal's deal history: open/close times, side, legs, P/L."""
    by_pos = {}
    for d in fake.deals:
        if magic is not None and d.magic != magic and d.entry == 0:
            continue
        by_pos.setdefault(d.position_id, []).append(d)
    legs = []
    for pid, ds in by_pos.items():
        din = [d for d in ds if d.entry == 0]
        dout = [d for d in ds if d.entry == 1]
        if din and dout:
            legs.append(dict(pid=pid, t_in=din[0].time_msc / 1000.0, t_out=dout[0].time_msc / 1000.0,
                             side=din[0].type, vol=din[0].volume, price_in=din[0].price, profit=dout[0].profit))
    legs.sort(key=lambda x: x['t_in'])
    out = []
    for leg in legs:
        if out and abs(out[-1]['t_close'] - leg['t_out']) < 1.0 and leg['side'] == out[-1]['side']:
            out[-1]['legs'].append(leg)
            out[-1]['pnl'] = round(out[-1]['pnl'] + leg['profit'], 2)
        else:
            out.append(dict(t_open=leg['t_in'], t_close=leg['t_out'], side=leg['side'], legs=[leg],
                            pnl=round(leg['profit'], 2)))
    return out


# ───────────────────────────── terminal and account failures ─────────────────────────────

NO_LADDER = dict(SCALED, MAX_ADDS=0)      # no arming state: polls that decide nothing can be skipped exactly


def deals_of(fake):
    return [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit) for d in fake.deals]


def quiet_window(run, fake, seconds):
    """Start (terminal seconds) of a stretch of `seconds` inside a basket in which `run` decided nothing: every poll
    DO_NOTHING with a basket open, no order sent. Skipping those polls changes nothing that follows."""
    order_t = [o['_t_ms'] for o in fake.orders]
    polls = run.polls
    for i, p in enumerate(polls):
        if p['t'] < (START + 120) * 1000 or p['nb'] + p['ns'] == 0:
            continue
        t0, t1 = p['t'], p['t'] + seconds * 1000
        window = [q for q in polls[i:] if q['t'] <= t1 + 1000]
        if window[-1]['t'] < t1:
            break
        if (all(q['buy'] == q['sell'] == 'DO_NOTHING' and q['nb'] + q['ns'] > 0 for q in window)
                and not any(t0 - 1000 <= t <= t1 + 1000 for t in order_t)):
            return t0 / 1000.0
    raise AssertionError('no quiet window')


def recording_states(saved):
    """on_new_bot hook: every state the bot saves, as JSON, into `saved`."""
    import json

    def on_new_bot(bot, n):
        save = bot._save_state

        def rec(symbol, state):
            saved.append(json.loads(json.dumps(state, default=str)))
            save(symbol, state)
        bot._save_state = rec
    return on_new_bot


def booked_outside(saved):
    """The saved states that book a basket as closed outside the bot or take one over from the terminal."""
    return [s for s in saved if (s.get('last_close') or {}).get('reason') == 'closed_outside'
            or (s.get('basket') or {}).get('opened_by') == 'rebuild']
