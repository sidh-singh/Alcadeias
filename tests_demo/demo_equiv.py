"""
What tests_demo/test_live_equivalence_demo.py is built from (that file says what it proves):

  * the two trees of a design. The reference is the demo branch the owner tested, at its pinned commit, read from
    git with `git show` into a tmp folder (never anybody's working files, never mt5_credentials.json). The live
    tree is this tree as the branch generator stamps it for that design: a copy of this tree's own Python files
    whose constants.py ends with the design block of the demo commit's constants.py, as written there -- every
    lever that block sets, minus the one line the live code has no name for (VIRTUAL_START_DATE). Nothing of a
    design is typed here;
  * the fake markets, pinned. Each was found once by running the demo tree on the harness's random walk and
    choosing, poll by poll, the slope of the ticks still to come (towards the open trade's target, then towards the
    next one's stop, ...); what is kept is the seed and the list of slopes, from which the same ticks are made
    again with no bot in the loop. The Turtle's market is a formula (400 daily bars, a 55-day breakout late in the
    UTC day);
  * the replays (run_bot of tests_demo/fake_mt5.py on both trees) and the comparison, poll by poll;
  * what the auto-safety did in a replay: every view its Tracker gave the poll loop, and its files.
"""
import ast
import bisect
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from conftest import F, ROOT, START, baskets

PROOF = os.environ.get('ALCADEIAS_PROOF') == '1'      # the lead's release run: nothing may skip

# The demo branches the owner tested, at the commit each live design is cut from (spec, section 1):
# code -> (commit, the DESIGN_NAME its constants.py must hold, its symbol). The branches, in this order:
# demo_hedging_xauusd6 (Gold V3-lite), _xauusd7 (Gold Top 2), _xauusd8 (Gold Top 1), _btcusd8 (BTC Top 2),
# _btcusd6 (BTC Turtle System 2 + bot votes).
DESIGNS = {
    'xv3': ('b3a11f9a4af07cf9c31e3d1ddb42d719af442cca', 'xau_v3lite', 'XAUUSDm'),
    'xt2': ('9270618abb16ce16382c237fe3cf7d8ceb73c515', 'xau_top2', 'XAUUSDm'),
    'xt1': ('45816859bd968f3f56c36b60b47146f08eb6687e', 'xau_top1', 'XAUUSDm'),
    'bt2': ('da85e9a1e44fa25800879917b20c17ccb01f8b2e', 'btc_top2', 'BTCUSDm'),
    'bs2': ('660932b80a1905c684c16d2fd4e847fd1e87b0fd', 'btc_turtle_s2', 'BTCUSDm'),
}

# The auto-safety's limits of each design: DROP %, DAY %, losing trades in a row (spec, section 1): those of the
# first account that runs the design. For four designs these are also the narrowest of every account that runs it;
# for Gold V3-lite accounts 5 to 7 have a narrower drop limit (25 / 15 / 6), far above anything the market reaches.
# A tree whose own design this is runs its ON replay at the limits written in its own constants.py instead
# (on_limits): on a stamped branch the proof then holds for exactly the limits that ship there.
# (The one table of deployment values a test of this suite holds: no single tree has the limits of all five.)
LIMITS = {
    'xt2': (20.0, 10.0, 10),      # account 1
    'bt2': (20.0, 10.0, 9),       # account 1
    'bs2': (20.0, 12.5, 5),       # account 2
    'xv3': (30.0, 12.5, 6),       # account 4
    'xt1': (35.0, 20.0, 9),       # account 8
}


def written_limits(root=None):
    """The safety limits written in a tree's constants.py (this tree by default): (DROP %, DAY %, STREAK)."""
    c = constants_of(ROOT if root is None else root)
    return (c['SAFETY_DROP_PCT'], c['SAFETY_DAY_PCT'], c['SAFETY_STREAK_N'])


def on_limits(code):
    """The limits the ON replays of design `code` run with: this tree's own, as written, when `code` is this tree's
    design; else the design's LIMITS."""
    if constants_of(ROOT).get('DESIGN_NAME') == DESIGNS[code][1]:
        return written_limits()
    return LIMITS[code]

# what a bot process of a demo branch loads (turtle.py: the Turtle's line only)
_DEMO_FILES = ('app.py', 'constants.py', 'strategy.py', 'indicator.py', 'mt5_helper.py', 'tracelog.py', 'turtle.py',
               'symbols.json')
_NEVER = ('mt5_credentials.json',)                          # never read, never copied
DESIGN_MARK = '# ─── Design of this branch'               # the design block: from this line to the end of constants.py
DEPLOY_MARKS = ('# ─── Deployment: this branch', '# ─── End of deployment ───')
DEMO_ONLY = {'DEMO_BRANCH', 'VIRTUAL_START_BALANCE', 'VIRTUAL_START_DATE'}     # what the live code line removed


# ───────────────────────── the two trees ─────────────────────────

class NotThere(Exception):
    """git, this repository or a pinned commit is missing: the comparison cannot be made here."""


def not_there(reason):
    """Skip the test -- or, in the lead's release run (ALCADEIAS_PROOF=1), fail it: there the proof may not be
    left out."""
    if PROOF:
        pytest.fail(f'ALCADEIAS_PROOF=1 and the demo tree cannot be read from git: {reason}', pytrace=False)
    pytest.skip(reason)


def _git(*args):
    try:
        return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, check=True).stdout
    except OSError as e:
        raise NotThere(f'git cannot be run ({type(e).__name__}: {e})') from e
    except subprocess.CalledProcessError as e:
        said = (e.stderr or b'').decode('utf-8', 'replace').strip().splitlines()
        raise NotThere(f"git {' '.join(args[:2])} failed" + (f': {said[0]}' if said else '')) from e


def export_demo_tree(code, folder):
    """The bot files of the pinned demo commit of design `code`, written into `folder` with `git show` (as
    conftest's baseline_root does for the old live code). Raises NotThere when git, the repository or the commit
    is missing."""
    sha, design_name, symbol = DESIGNS[code]
    _git('rev-parse', '--git-dir')
    try:
        _git('cat-file', '-e', sha + '^{commit}')
    except NotThere as e:
        raise NotThere(f'commit {sha[:7]} (the demo branch of {code}) is not in this repository: fetch the demo '
                       f'branches ({e})') from e
    names = _git('ls-tree', '--name-only', sha).decode('utf-8').split()
    folder = Path(folder)
    for name in _DEMO_FILES:
        if name in names and name not in _NEVER:
            (folder / name).write_bytes(_git('show', f'{sha}:{name}'))
    # the reference must be the demo branch of this design, or the comparison proves nothing
    c = constants_of(folder)
    assert DEMO_ONLY <= set(c), f'{sha[:7]} is not a demo branch (no {sorted(DEMO_ONLY - set(c))})'
    assert c['DESIGN_NAME'] == design_name, f"{sha[:7]} holds the design {c['DESIGN_NAME']!r}, not {design_name!r}"
    assert _symbols(folder)['symbol'] == symbol
    return folder


def constants_of(root):
    """Every upper-case name of root/constants.py, the file executed by itself."""
    path = Path(root) / 'constants.py'
    ns = {}
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), ns)
    return {k: v for k, v in ns.items() if k.isupper()}


def _symbols(root):
    cfg = json.loads((Path(root) / 'symbols.json').read_text(encoding='utf-8'))
    (sym,) = [s for s in cfg['symbols'] if s.get('is_active')]
    return dict(sym, mtqty=cfg['mtqty'], trading_window=cfg['trading_window'], brake=cfg['brake'])


def _split_design(text, what):
    head, mark, tail = text.rpartition(DESIGN_MARK)
    assert mark, f'{what}: no design block (a line starting with {DESIGN_MARK!r})'
    return head, mark + tail


def deployment_names(root=ROOT):
    """The names the deployment block of a live constants.py assigns (what differs from branch to branch)."""
    text = (Path(root) / 'constants.py').read_text(encoding='utf-8')
    first, last = DEPLOY_MARKS
    assert text.count(first) == 1 and text.count(last) == 1, 'constants.py: the deployment block is not marked'
    ns = {}
    exec(text[text.index(first):text.index(last)], ns)
    return {k for k in ns if k.isupper()}


def stamp_live_tree(demo_root, folder):
    """This tree as the branch generator stamps it for the design of `demo_root`: a copy of every Python file of
    this tree (the working files, as they are now) in `folder`, constants.py ending with the design block of the
    demo commit instead of this tree's own, and the demo branch's symbols.json. Returns (folder, the names the
    block sets, the names of the block the live code line has no use for)."""
    folder = Path(folder)
    for path in sorted(ROOT.glob('*.py')):
        shutil.copyfile(path, folder / path.name)
    head, _own = _split_design((ROOT / 'constants.py').read_text(encoding='utf-8'), 'this tree')
    _, block = _split_design((Path(demo_root) / 'constants.py').read_text(encoding='utf-8'), 'the demo commit')
    ns = {}
    exec(compile(head, 'constants.py (above the design block)', 'exec'), ns)
    known = {k for k in ns if k.isupper()}
    levers, dropped, drop_lines = [], [], set()
    for node in ast.parse(block).body:
        assert isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets), \
            f'the design block of the demo commit holds more than plain assignments (line {node.lineno})'
        names = [t.id for t in node.targets]
        if all(n in known for n in names):
            levers += names
        else:
            dropped += names
            drop_lines.update(range(node.lineno, node.end_lineno + 1))
    kept = [line for i, line in enumerate(block.splitlines(), 1) if i not in drop_lines]
    (folder / 'constants.py').write_text(head + '\n'.join(kept) + '\n', encoding='utf-8')
    shutil.copyfile(Path(demo_root) / 'symbols.json', folder / 'symbols.json')
    return folder, levers, dropped


class Design:
    """One design: its demo tree, its stamped live tree, and what its demo branch's symbols.json says."""

    def __init__(self, code, demo_root, live_root, levers, dropped):
        self.code = code
        self.commit, self.design_name, self.symbol = DESIGNS[code]
        self.demo_root, self.live_root = Path(demo_root), Path(live_root)
        self.levers, self.dropped = list(levers), list(dropped)
        self.demo = constants_of(demo_root)                 # every constant of the demo commit
        self.live = constants_of(live_root)                 # every constant of the stamped live tree
        sym = _symbols(demo_root)
        self.step, self.unit_max = sym['step_up_balance'], sym['unit_max_limit']
        self.mtqty, self.window = sym['mtqty'], sym['trading_window']
        self.turtle = self.demo.get('STRATEGY') == 'turtle'
        # the demo bot sizes from this much virtual money plus its own closed profit: the fake account starts with it
        self.balance = float(self.demo['VIRTUAL_START_BALANCE'])
        self.demo_comment = str(self.demo['ORDER_COMMENT'] if self.demo['ORDER_COMMENT'] is not None
                                else self.demo['DEMO_BRANCH'])[:31]

    def virtual_start(self):
        """VIRTUAL_START_DATE of the demo commit as seconds: the demo bot counts its deals from here."""
        dt = datetime.fromisoformat(str(self.demo['VIRTUAL_START_DATE']).strip())
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()

    def bot_kw(self, step=None):
        """What symbols.json gives the bot (the demo branch's file; `step`: another step_up_balance)."""
        return dict(step_up=self.step if step is None else step, max_limit=self.unit_max, window=self.window,
                    mtqty=self.mtqty)


def build_design(code, demo_folder, live_folder):
    demo_root = export_demo_tree(code, demo_folder)
    live_root, levers, dropped = stamp_live_tree(demo_root, live_folder)
    return Design(code, demo_root, live_root, levers, dropped)


# ───────────────────────── the fake markets ─────────────────────────
# The four basket designs: 30 days of history and one tick a second from the harness's random walk (one seed), plus
# a drift: from tick k on, every tick adds `slope` to the price (segments = [(k, slope), ...]). The drift was chosen
# while the demo tree ran on the market (see the module's docstring); here it is fixed. All four start at START
# (Tuesday 08:00 UTC, inside both trading windows) and end inside that hour, so the H1 trend and the H1 volatility
# unit are those of the history for the whole run. Times below are seconds after START.
#   restart: when the bot process dies in the restart replay; restart_seconds: where that replay ends (just after
#   the next basket opened).
BASKET_MARKETS = {
    # Gold V3-lite, a buy first. 137 s: the entry (H1 votes and trend up, the M15 votes agree). 302 s: closed at its
    # target (8 volatility units). 602 s: the next entry, when the 300 s pause ended. 750 s: closed at its stop.
    # Then the price goes back to where an entry is wanted, and the 12-hour loss pause holds it to the end.
    'xv3': dict(seed=6, sigma=0.15, price0=2000.0, spread=0.12, contract=100.0, seconds=1090,
                segments=[(0, 0.0), (1, 0.3), (137, 0.0), (138, 0.422056), (303, 0.0), (603, -0.478331), (751, 0.0),
                          (752, 0.3), (776, 0.0)],
                restart=198.5, restart_seconds=632),
    # Gold Top 2, a sell first, on a wilder market: the H1 volatility unit is above its cap ($12 per unit), so the
    # cap sets target and stop. 51 s entry, 205 s target, 505 s entry, 641 s stop, then the 12-hour loss pause.
    'xt2': dict(seed=8, sigma=0.30, price0=2000.0, spread=0.12, contract=100.0, seconds=981,
                segments=[(0, 0.0), (1, -0.6), (51, 0.0), (52, -0.587294), (206, 0.0), (506, 0.3328), (642, 0.0)],
                restart=112.5, restart_seconds=535),
    # Gold Top 1, a sell first. 99 s entry; the price goes 1.5 volatility units against it (the M5 MACD vote turns
    # against the basket: the ladder is armed) and waits there; 301 s: the M5 vote is with the basket again: the
    # ladder add, more than a unit worse than the entry; 442 s: both legs closed at the target. 742 s entry, 889 s
    # stop, then the 4-hour loss pause.
    'xt1': dict(seed=20, sigma=0.15, price0=2000.0, spread=0.12, contract=100.0, seconds=1229,
                segments=[(0, 0.0), (1, -0.3), (99, 0.0), (100, 0.204589), (151, -0.007956), (303, -0.315926),
                          (443, 0.0), (743, 0.397141), (890, 0.0), (891, -0.3), (1002, 0.0)],
                restart=200.5, restart_seconds=775),
    # BTC Top 2, a buy first. 90 s entry, 254 s target, 554 s entry, 703 s stop, then the 4-hour loss pause.
    'bt2': dict(seed=4, sigma=7.0, price0=60000.0, spread=10.0, contract=1.0, seconds=1043,
                segments=[(0, 0.0), (1, 14.0), (90, 0.0), (91, 22.861647), (255, 0.0), (555, -20.7272), (704, 0.0)],
                restart=151.5, restart_seconds=585),
}


# With ALCADEIAS_PROOF=1, the whole loss pause of two designs (12 hours, 4 hours). The design's market again from
# another hour of that Tuesday (the same seed gives the same H1 / M15 bars, so the same two baskets), then the
# market closed -- no tick at all from second closed[0] to second closed[1]: the bot polls and decides nothing, the
# pause runs on the clock -- and open again 7 minutes before the pause ends, with an entry wanted all along: it must
# go on the poll the pause ends, on the levels of the H1 bar closed since; that third basket closes at its target.
# Both runs cross 00:00 UTC (a new day for the safety's daily rule and for the logs).
LONG_MARKETS = {
    'xt2': dict(BASKET_MARKETS['xt2'], start=START + 6 * 3600, seconds=44031, closed=(996, 43421),      # from 14:00
                segments=[(0, 0.0), (1, -0.6), (51, 0.0), (52, -0.587294), (206, 0.0), (506, 0.3328), (642, 0.0),
                          (1417, -0.587294), (1582, 0.0)]),
    'bt2': dict(BASKET_MARKETS['bt2'], start=START + 14 * 3600, seconds=15297, closed=(1058, 14683),    # from 22:00
                segments=[(0, 0.0), (1, 14.0), (90, 0.0), (91, 22.861647), (255, 0.0), (555, -20.7272), (704, 0.0),
                          (1479, 27.832235), (1648, 0.0)]),
}


def basket_ticks(seed, sigma, price0, spread, seconds, segments, start=START, closed=None, **_):
    """(history M1 bars, tick times, bid, ask) of a basket market: the walk plus the drift, in cents; closed =
    (a, b): no tick between second a and second b after `start` (the walk goes on where it stopped)."""
    n = seconds + 120 - ((closed[1] - closed[0]) if closed else 0)
    m1, t_ms, walk, _ask = F.random_walk_market(start, n, seed=seed, sigma_per_s=sigma, price0=price0, spread=spread,
                                               warm_days=30)
    step = np.zeros(len(walk))
    for i, (k, slope) in enumerate(segments):
        step[k:(segments[i + 1][0] if i + 1 < len(segments) else len(walk))] = slope
    bid = np.round(walk + np.cumsum(step), 2)
    if closed:
        t_ms = t_ms.copy()
        t_ms[closed[0]:] += (closed[1] - closed[0]) * 1000
    return m1, t_ms, bid, np.round(bid + spread, 2)


def basket_market(design, restart=False, long=False):
    """The fake terminal and clock of a basket design's market; restart: the shorter replay in which the bot is
    restarted once inside the first basket; long: the market of the whole loss pause."""
    k = (LONG_MARKETS if long else BASKET_MARKETS)[design.code]
    start = k.get('start', START)
    seconds = k['restart_seconds'] if restart else k['seconds']
    m1, t_ms, bid, ask = basket_ticks(**dict(k, seconds=seconds))
    clock = F.FakeClock(start + 0.5, start + seconds, restarts_s=[start + k['restart']] if restart else ())
    fake = F.FakeMT5(design.symbol, t_ms, bid, ask, clock, warm_m1=m1, contract_size=k['contract'],
                     balance=design.balance)
    return fake, clock


# The Turtle: BTC around 60,000. 400 whole UTC days of 15-minute bars, then the day of the run up to 23:15, then one
# tick a second. The last 19 days stay inside 60,150 .. 60,770 (so N is about 660 and the 55-day high is 60,775);
# the day before them goes down to 59,300: that is the 20-day low -- the exit channel -- until it leaves the 20-day
# window when the run's own day closes. In the run: 23:16 the ask passes the 55-day high with the M15 vote up (the
# real vote, on the history's last hours: a dip, then a rally): the entry; 23:23 half an N higher: the pyramid;
# 00:00 the D1 bar closes: the exit channel is now 60,145, above the 2N stop: the stop goes up to it; 00:11 the bid
# falls through it: both legs closed.
TURTLE_T0 = datetime(2026, 11, 17, 23, 15, tzinfo=timezone.utc).timestamp()
TURTLE_DAY = TURTLE_T0 - (23 * 3600 + 15 * 60)                       # 00:00 UTC of the run's first day
TURTLE_SPREAD = 10.0
TURTLE_SEGMENTS = [(60745.0, 60790.0, 150), (60790.0, 61160.0, 420), (61160.0, 61180.0, 60),      # (bid from, to, seconds)
                   (61180.0, 61150.0, 900), (61150.0, 61190.0, 900), (61190.0, 61160.0, 450),
                   (61160.0, 60100.0, 540), (60100.0, 60130.0, 240)]
TURTLE_RESTART = 240.5                                               # 23:19: after the entry, before the pyramid


def turtle_history(days=400):
    """15-minute bars: `days` whole days before TURTLE_DAY, then that day's 93 bars up to 23:15."""
    t = (int(TURTLE_DAY) - 900 * np.arange(days * 96, 0, -1)).astype(np.int64)
    d = (t - int(TURTLE_DAY)) // 86400                                # -days .. -1
    x = ((t - int(TURTLE_DAY)) % 86400) / 86400.0
    centre = np.where(d >= -19, 60460.0, np.where(d >= -55, 59700.0 + (d + 55) * (600.0 / 34.0),
                                                  59500.0 + 300.0 * np.sin(2 * np.pi * d / 30.0)))
    swing = np.where(d >= -19, 310.0, np.where(d >= -55, 320.0, 450.0))
    p = centre + swing * np.sin(2 * np.pi * x)
    p = np.where(d == -20, 60460.0 - 1160.0 * np.sin(np.pi * x) ** 2, p)      # the one deep day
    k = np.arange(93)                                                 # the run's day: flat, a dip, the rally
    today = np.where(k < 60, 60460.0 + 140.0 * k / 60,
                     np.where(k < 83, 60600.0 - 350.0 * (k - 60) / 23, 60250.0 + 495.0 * (k - 83) / 9))
    today = today + 12.0 * np.sin(k * 1.7)
    t = np.concatenate([t, (int(TURTLE_DAY) + 900 * k).astype(np.int64)])
    c = np.round(np.concatenate([p, today]), 2)
    o = np.concatenate([[c[0]], c[:-1]])
    return {'t': t, 'o': o, 'h': np.maximum(o, c) + 5, 'l': np.minimum(o, c) - 5, 'c': c, 'n': np.ones(len(t), np.int64)}


def turtle_market(design, restart=False):
    bid = np.round(np.concatenate([np.linspace(a, b, s, endpoint=False) for a, b, s in TURTLE_SEGMENTS]), 2)
    k = len(bid)
    t_ms = (int(TURTLE_T0) * 1000 + 1000 + 1000 * np.arange(k)).astype(np.int64)
    clock = F.FakeClock(TURTLE_T0 + 1.5, TURTLE_T0 + k, restarts_s=[TURTLE_T0 + TURTLE_RESTART] if restart else ())
    fake = F.FakeMT5(design.symbol, t_ms, bid, bid + TURTLE_SPREAD, clock, warm_m1=turtle_history(),
                     contract_size=1.0, balance=design.balance)
    return fake, clock


def market(design, restart=False, long=False):
    """A new fake terminal (and its clock) on the design's market, the account holding the demo bot's virtual
    start balance."""
    fake, clock = turtle_market(design, restart=restart) if design.turtle else basket_market(design, restart, long)
    # the demo bot counts its own deals from VIRTUAL_START_DATE: every deal of the replay must be after it
    assert clock.time() >= design.virtual_start(), 'the market starts before the demo bot counts its deals'
    return fake, clock


def market_start(design, long=False):
    return TURTLE_T0 if design.turtle else (LONG_MARKETS[design.code]['start'] if long else START)


def restart_time(design):
    """When the bot is restarted in the restart replay (fake seconds since 1970)."""
    return TURTLE_T0 + TURTLE_RESTART if design.turtle else START + BASKET_MARKETS[design.code]['restart']


# ───────────────────────── the replays ─────────────────────────

class Replay:
    """One replay of one tree: `run` (the harness's record: polls, events, errors, restarts), `fake` (the terminal
    it traded on: orders, deals, balance, positions), `out` (its OUTPUT_DIR), and for the live tree `views`: every
    view the safety's Tracker gave the poll loop."""

    def __init__(self, name, design, run, fake, out, views=None, limits=None):
        self.name, self.design, self.run, self.fake, self.out = name, design, run, fake, Path(out)
        self.views, self.limits = views, limits
        self.polls, self.events = run.polls, run.events


@contextmanager
def watching_the_safety(views):
    """While the block runs, every view safety.Tracker.poll returns is noted in `views` (a few keys of it). The
    class is watched, not an object: wherever the bot builds its Tracker, its polls are seen; a tree whose loop
    has no Tracker leaves `views` empty. Yields watch(bot): call it with each new bot, so that the safety module of
    that bot's own app module is watched too."""
    watched = []

    def watch_module(module):
        cls = getattr(module, 'Tracker', None)
        if cls is None or any(c is cls for c, _ in watched):
            return
        original = cls.poll

        def poll(self, *args, **kwargs):
            view = original(self, *args, **kwargs)
            try:
                v = view if isinstance(view, dict) else {}
                views.append({'now': args[0] if args else kwargs.get('now'),
                              **{k: v.get(k) for k in ('enabled', 'blocked', 'hold', 'pending', 'error', 'state',
                                                       'limits')}})
            except Exception:           # (watching must never reach the bot)
                pass
            return view
        cls.poll = poll
        watched.append((cls, original))

    def watch(bot):
        watch_module(getattr(sys.modules.get(type(bot).__module__), 'safety', None))

    watch_module(sys.modules.get('safety'))
    try:
        yield watch
    finally:
        for cls, original in watched:
            cls.poll = original


def _this_trees_safety():
    """app.py's `import safety` must find this tree's own safety.py, as in every other test of the suite -- not the
    copy that lies beside the stamped app.py (the same file, but whichever is imported first stays in sys.modules
    for the whole session). Imported here from this tree when nothing has imported it yet."""
    if 'safety' not in sys.modules:
        spec = importlib.util.spec_from_file_location('safety', ROOT / 'safety.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules['safety'] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop('safety', None)
            raise


def replay_demo(design, fake, clock, out, step=None):
    """The demo tree, as its commit has it: its constants.py whole (design block, VIRTUAL_START_BALANCE and date,
    magic), its own mode word, on a demo account (the only kind it trades). Only OUTPUT_DIR is given."""
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_DEMO
    run = F.run_bot(design.demo_root, fake, clock, design.symbol, overrides={'OUTPUT_DIR': str(out)}, mode='demo',
                    **design.bot_kw(step))
    return Replay('demo', design, run, fake, out)


def replay_live(design, fake, clock, out, share=1.0, limits=None, step=None):
    """The stamped live tree in mode 'live' on the fake's real account. Besides OUTPUT_DIR only deployment values
    are given: ACCOUNT_SHARE, and the safety -- limits None: OFF (no limit and the switch off), else ON with
    (DROP %, DAY %, losing trades in a row)."""
    ov = {'OUTPUT_DIR': str(out), 'ACCOUNT_SHARE': share}
    if limits is None:
        ov.update(SAFETY_DEFAULT_ON=False, SAFETY_DROP_PCT=None, SAFETY_DAY_PCT=None, SAFETY_STREAK_N=None)
    else:
        ov.update(SAFETY_DEFAULT_ON=True, SAFETY_DROP_PCT=limits[0], SAFETY_DAY_PCT=limits[1],
                  SAFETY_STREAK_N=limits[2])
    views = []
    _this_trees_safety()
    with watching_the_safety(views) as watch:
        run = F.run_bot(design.live_root, fake, clock, design.symbol, overrides=ov, mode='live',
                        on_new_bot=lambda bot, n: watch(bot), **design.bot_kw(step))
    return Replay('live, safety ' + ('OFF' if limits is None else 'ON'), design, run, fake, out, views, limits)


# ───────────────────────── the comparison ─────────────────────────

OWN_MARK = ('magic', 'comment')        # the two keys of a request by which a bot knows its own orders: they differ
# What a poll decided, as the harness records it for both trees (not: the live tree's own 'sizing', 'open_hold').
POLL_KEYS = ('t', 'buy', 'sell', 'fresh', 'open_score', 'fc_score', 'nb', 'ns', 'profit', 'units', 'entry_allowed',
             'exit_reason', 'rsi', 'ladder_armed', 'trend', 'vol', 'levels', 'pause_left', 'no_data',
             'short_history', 'votes')


def requests(replay):
    """Every order request the bot sent, whole and in order, with the fake time of the send ('_t_ms'), without the
    bot's own mark."""
    return [{k: v for k, v in o.items() if k not in OWN_MARK} for o in replay.fake.orders]


def requests_by_poll(replay):
    """{poll number: the requests sent in that poll} (a request belongs to the last poll that began before it)."""
    starts = [p['t'] for p in replay.polls]
    out = {}
    for r in requests(replay):
        out.setdefault(bisect.bisect_right(starts, r['_t_ms']) - 1, []).append(r)
    return out


def deals(replay):
    return [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit, d.position_id, d.reason)
            for d in replay.fake.deals]


def _when(t_ms):
    return datetime.fromtimestamp(t_ms / 1000.0, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + ' UTC'


def _types(reqs):
    """The type of every value of the requests: 0 and 0.0 are equal in Python, not to MetaTrader 5."""
    return [{k: type(v).__name__ for k, v in r.items()} for r in reqs]


def difference(ref, other):
    """None when `other` did what `ref` did: the same polls at the same fake times, in every poll the same order
    requests (whole dicts, the bot's own mark aside: every key, every value and its type) and the same decision,
    then the same deals, open positions and balance. Else the first difference, as text: the poll, its fake time,
    and both sides."""
    a, b = ref.polls, other.polls
    ra, rb = requests_by_poll(ref), requests_by_poll(other)
    for i in range(min(len(a), len(b))):
        if a[i]['t'] != b[i]['t']:
            return (f'poll {i}: the {ref.name} bot polled at {_when(a[i]["t"])}, the {other.name} bot at '
                    f'{_when(b[i]["t"])}')
        if ra.get(i, []) != rb.get(i, []):
            return (f'poll {i} ({_when(a[i]["t"])}): the order requests differ\n  {ref.name}: {ra.get(i, [])}\n'
                    f'  {other.name}: {rb.get(i, [])}')
        if _types(ra.get(i, [])) != _types(rb.get(i, [])):
            return (f'poll {i} ({_when(a[i]["t"])}): the order requests hold the same values in other types\n'
                    f'  {ref.name}: {_types(ra.get(i, []))}\n  {other.name}: {_types(rb.get(i, []))}')
        for k in POLL_KEYS:
            if a[i][k] != b[i][k]:
                return (f'poll {i} ({_when(a[i]["t"])}): {k} differs\n  {ref.name}: {a[i][k]!r}\n'
                        f'  {other.name}: {b[i][k]!r}')
    if len(a) != len(b):
        return f'the {ref.name} bot made {len(a)} polls, the {other.name} bot {len(b)}'
    if ra != rb:                              # (a request before the first poll)
        return f'the order requests differ\n  {ref.name}: {requests(ref)}\n  {other.name}: {requests(other)}'
    da, db = deals(ref), deals(other)
    if da != db:
        i = next((i for i, (x, y) in enumerate(zip(da, db)) if x != y), min(len(da), len(db)))
        return (f'the deals differ from deal {i} on (time, type, entry, volume, price, profit, position, reason)\n'
                f'  {ref.name}: {da[i:i + 2]}\n  {other.name}: {db[i:i + 2]}')
    pa, pb = ([(p['ticket'], p['type'], p['volume'], p['price_open'], p.get('sl'), p.get('tp'))
               for p in r.fake.positions] for r in (ref, other))
    if pa != pb:
        return f'the positions left open differ\n  {ref.name}: {pa}\n  {other.name}: {pb}'
    if ref.fake.balance != other.fake.balance:
        return f'the final balance differs: {ref.name} {ref.fake.balance!r}, {other.name} {other.fake.balance!r}'
    return None


# ───────────────────────── what happened in a replay ─────────────────────────

def opens(replay):
    """The opening requests (entries, ladder adds, pyramids), as sent."""
    return [o for o in replay.fake.orders if 'position' not in o]


def closes(replay):
    return [o for o in replay.fake.orders if 'position' in o]


def exits(replay):
    """[(poll number, fake ms, exit reason)] of the polls that decided an exit."""
    return [(i, p['t'], p['exit_reason']) for i, p in enumerate(replay.polls) if p['exit_reason']]


def events(replay, *names):
    return [e for e in replay.events if e['event'] in names]


def closed_baskets(replay):
    """The closed baskets / Turtle trades of the replay from the terminal's deals: side, legs, P/L, times."""
    return baskets(replay.fake)


def entry_wanted(design, p):
    """+1 / -1 when the poll `p` of a flat basket bot wants an entry that only a pause can hold back: the votes
    give a direction (the OPEN score at the entry threshold, the agreement score with it), the trend is on that
    side, the volatility unit is known. Else 0."""
    c = design.demo
    o, f = p.get('open_score'), p.get('fc_score')
    if o is None or f is None or p['nb'] + p['ns']:
        return 0
    d = 1 if (o >= c['ENTRY_S'] and f >= c['ENTRY_AGREE_S']) else (
        -1 if (o <= -c['ENTRY_S'] and f <= -c['ENTRY_AGREE_S']) else 0)
    if d == 0 or p.get('trend') != d or not p.get('vol') or p.get('no_data') or p.get('short_history'):
        return 0
    return d


# ───────────────────────── what the safety left behind ─────────────────────────

def _tree_safety():
    """This tree's safety.py, loaded by itself (it imports nothing of the bot): for account_dir()."""
    spec = importlib.util.spec_from_file_location('safety_of_demo_equiv', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def account_folder(replay):
    """The account's shared folder of a live replay: safety.account_dir(OUTPUT_DIR, ACCOUNT_FOLDER)."""
    return Path(_tree_safety().account_dir(str(replay.out), replay.design.live['ACCOUNT_FOLDER']))


def block_files(replay):
    folder = account_folder(replay)
    return sorted(p.name for p in folder.glob('safety_block_*.json')) if folder.is_dir() else []


def audit_lines(replay):
    """The lines of the account folder's safety_audit.jsonl ([] without the file)."""
    path = account_folder(replay) / 'safety_audit.jsonl'
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def safety_state_file(replay):
    """Where the bot's Tracker keeps its state: state/safety_state.json in the bot folder."""
    return replay.out / replay.design.live['STATE_SUBDIR'] / 'safety_state.json'


# The events by which the live layer says it held, blocked or could not judge something (spec, section 14): none
# of them may occur in a replay that is to prove "nothing was held back".
HOLD_EVENTS = ('SAFETY_ERROR', 'SAFETY_SKIP', 'SAFETY_BLOCKED', 'SAFETY_UNBLOCKED', 'CLOSE_RESULT_UNKNOWN',
               'OTHER_PROGRAM', 'FOREIGN_POSITIONS', 'OLD_BOT_SAME_TERMINAL', 'OLD_BOT_RUNNING', 'TURTLE_ADDS_STOPPED',
               'BUY_REFUSED', 'SELL_REFUSED', 'BUY_MORE_REFUSED', 'SELL_MORE_REFUSED')


def fresh_starts(replay):
    """The audit file's lines of a fresh start of the counting (the first start of the safety is one)."""
    return [line for line in audit_lines(replay) if isinstance(line, dict) and line.get('event') == 'fresh_start']


def never_blocked(replay):
    """Why the safety blocked or held something in a live replay ([] = it never did): a block file in the account
    folder, a line in the audit file that is not a start, a poll that held an open back (the poll local _open_hold,
    which the harness records), an event of the live layer that says it held, blocked or could not judge, a view
    of the Tracker that says blocked, hold or error (every view poll() gave the loop: watching_the_safety)."""
    said = []
    if block_files(replay):
        said.append(f'block files in the account folder: {block_files(replay)}')
    other = [line for line in audit_lines(replay) if not (isinstance(line, dict) and line.get('event') == 'fresh_start')]
    if other:
        said.append(f'the audit file holds more than starts: {other[:3]}')
    held = [(i, p['open_hold']) for i, p in enumerate(replay.polls) if p.get('open_hold')]
    if held:
        said.append(f'{len(held)} polls held an open back, the first: poll {held[0][0]} {held[0][1]}')
    said_so = events(replay, *HOLD_EVENTS)
    if said_so:
        said.append(f'{len(said_so)} events of a hold or a block, the first: {said_so[0]}')
    bad = [v for v in replay.views or [] if v['blocked'] or v['hold'] or v['error']]
    if bad:
        said.append(f"{len(bad)} of the Tracker's {len(replay.views)} views say blocked, hold or error, the first: {bad[0]}")
    return said


def safety_gaps(replay, restart_at=None):
    """Where the Tracker of a live replay was missing from the poll loop ([] = nowhere): it must have polled in
    (nearly) every poll of the bot -- after a restart at `restart_at` (fake seconds) too -- once it polled at all.
    A replay with no view at all is a tree without a Tracker in its loop: that is for the ON test to say, not for
    every replay."""
    views = replay.views or []
    if not views:
        return []
    parts = [('the replay', lambda t: True)]
    if restart_at is not None:
        parts = [('the bot before the restart', lambda t: t < restart_at),
                 ('the bot after the restart', lambda t: t >= restart_at)]
    said = []
    for what, inside in parts:
        polls = sum(1 for p in replay.polls if inside(p['t'] / 1000.0))
        seen = sum(1 for v in views if v['now'] is not None and inside(float(v['now'])))
        if seen < 0.9 * polls:
            said.append(f'{what}: the Tracker polled {seen} times in {polls} polls')
    return said

