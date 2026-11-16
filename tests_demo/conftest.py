"""
Tests of the demo-branch port: the design levers (trend, volatility unit, target / stop / cap, loss pause,
macd_turn ladder), the demo isolation (magic, comment, virtual balance) and restart recovery; the Turtle
(STRATEGY = 'turtle', turtle.py): test_turtle_*.py, its replay against the backtest in test_turtle_replay.py.

Run from any folder:  python3 -B -m pytest <branch>/tests_demo -q -p no:cacheprovider
(-B: Python writes no bytecode into the branch; -p no:cacheprovider: pytest writes no cache folder.)
Nothing here talks to a terminal: MetaTrader5 is replaced by tests_demo/fake_mt5.py.
Nothing here writes outside pytest's tmp folders: every bot the tests build (this branch's and the live baseline
of test_live_equivalence.py) has its OUTPUT_DIR -- its state, logs and JSON files -- in the test's tmp_path; any
write into the real output folder (C:\\Alcadeias\\...: on the server the running demo bot's own files), whatever
function makes it, is refused and fails the run, and so does bytecode written into the branch (a run without -B):
see the end of this file.
"""
import ntpath
import os
import subprocess
import sys
import tempfile
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

START = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc).timestamp()   # a Tuesday, after VIRTUAL_START_DATE

# The tests exercise the code, not the design a branch has chosen: every bot here starts from the DEFAULT
# section of this branch's constants.py (everything above the '# ─── Design examples ───' marker, i.e. the
# live levers plus this branch's demo plumbing), then each test sets what it needs. A design block appended
# at the end of constants.py therefore changes nothing here; test_design.py checks that block on its own.
_EXAMPLES_MARKER = '# ─── Design examples ───'


def _default_constants():
    text = (ROOT / 'constants.py').read_text(encoding='utf-8')
    head = text.split(_EXAMPLES_MARKER, 1)[0]
    ns = {}
    exec(compile(head, str(ROOT / 'constants.py'), 'exec'), ns)
    return {k: v for k, v in ns.items() if k.isupper()}


DEFAULTS = _default_constants()
MAGIC = DEFAULTS['MAGIC']
DEMO_BRANCH = DEFAULTS['DEMO_BRANCH']
COMMENT = str(DEFAULTS['ORDER_COMMENT'] if DEFAULTS['ORDER_COMMENT'] is not None else DEMO_BRANCH)[:31]


# ───────────────────────── every bot the tests build writes in a tmp folder ─────────────────────────
# The branch's OUTPUT_DIR is an absolute Windows path (C:\Alcadeias\<branch>). On the server a test that leaves it
# there writes the running demo bot's own state file (a fake loss blocks its entries for hours) and logs; on macOS it
# makes a folder literally named 'C:\Alcadeias\<branch>' in the working folder. So every load of the bot's modules
# (F.bot_modules: the mods fixture, run_bot, the live baseline, a test's own load) gets an OUTPUT_DIR in a tmp folder
# -- and with it the state folder (OUTPUT_DIR/state, also the Turtle's) and the logs -- unless the test gives one that
# is not the real one.

REAL_OUTPUT_DIR = DEFAULTS['OUTPUT_DIR']


def _top_folder(path):
    """'C:\\Alcadeias\\demo_hedging_xauusd6' -> 'C:\\Alcadeias': the folder every bot's output is in on the server."""
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
    """Where a bot loaded now writes: the running test's tmp_path / 'bot_output'; outside a test (a module-scoped
    fixture) a new folder under pytest's basetemp; outside pytest (a probe script) a new temporary folder."""
    if _BotOutput.current is not None:
        return _BotOutput.current
    if _BotOutput.factory is not None:
        return _BotOutput.factory.mktemp('bot_output')
    return Path(tempfile.mkdtemp(prefix='bot_output_'))


def _bot_modules_in_tmp(load):
    @contextmanager
    def bot_modules(root, fake, clock, overrides=None):
        ov = dict(overrides or {})
        out = ov.get('OUTPUT_DIR')
        if out is None or is_real_output(out) or not os.path.isabs(str(out)):
            ov['OUTPUT_DIR'] = str(bot_output_dir())
        with load(root, fake, clock, ov) as mods:
            yield mods
    bot_modules.in_tmp = True
    return bot_modules


if not getattr(F.bot_modules, 'in_tmp', False):
    F.bot_modules = _bot_modules_in_tmp(F.bot_modules)     # (run_bot finds it here too)


def run_bot(fake, clock, overrides=None, symbol='XAUUSDm', **kw):
    """Replay this branch's bot from its default constants plus `overrides`."""
    return F.run_bot(ROOT, fake, clock, symbol, overrides={**DEFAULTS, **(overrides or {})}, **kw)

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


def pytest_unconfigure(config):
    _GUARD['on'] = False


@pytest.fixture(scope='session', autouse=True)
def _nothing_outside_tmp(tmp_path_factory):
    """The whole run writes nothing outside pytest's tmp folders: no write into the real output folder, no
    'C:\\Alcadeias...' folder left in the working folder, no bytecode in the branch."""
    cwd = Path.cwd()
    before = {p.name for p in cwd.iterdir()}
    _BotOutput.factory = tmp_path_factory
    try:
        yield
    finally:
        _BotOutput.factory = None
    left = sorted(p.name for p in cwd.iterdir() if p.name not in before and is_real_output(p))
    pyc = stray_bytecode(sys.flags.dont_write_bytecode, sys.pycache_prefix)
    problems = (list(REFUSED_WRITES) + [f'left in the working folder {cwd}: {n}' for n in left]
                + [f'bytecode written into the branch: {p} (run the tests with python3 -B, and delete '
                   f'{HERE / "__pycache__"})' for p in pyc])
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


@pytest.fixture(scope='session')
def root():
    return ROOT


@pytest.fixture(scope='session')
def baseline_root(tmp_path_factory):
    """The bot as it was before the port: the tree of the branch's demo-plumbing commit ('demo: <branch> - demo
    account only, ...': live v3.9.2 plus the demo plumbing), exported from git. Skipped when git or that
    commit is not there."""
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


# ───────────────────────────── terminal and account failures (the demo review) ─────────────────────────────

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
