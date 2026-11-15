"""
Tests of the demo-branch port: the design levers (trend, volatility unit, target / stop / cap, loss pause,
macd_turn ladder), the demo isolation (magic, comment, virtual balance) and restart recovery.

Run from the branch root:  python3 -m pytest tests_demo -q -p no:cacheprovider
Nothing here talks to a terminal: MetaTrader5 is replaced by tests_demo/fake_mt5.py.
"""
import subprocess
import sys
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


def run_bot(fake, clock, overrides=None, symbol='XAUUSDm', **kw):
    """Replay this branch's bot from its default constants plus `overrides`."""
    return F.run_bot(ROOT, fake, clock, symbol, overrides={**DEFAULTS, **(overrides or {})}, **kw)

_LIVE_FILES = ('app.py', 'strategy.py', 'indicator.py', 'mt5_helper.py', 'constants.py', 'symbols.json')


def pytest_configure(config):
    config.addinivalue_line('markers', 'slow: replays the whole bot loop over a synthetic market (tens of seconds)')


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
