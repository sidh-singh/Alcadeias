"""
The lock rule (spec rules 3 and 4): mt5_lock is a plain lock -- a helper never takes it itself, its caller does --
and nothing writes a file while it is held (the two old exceptions: the LEG_CLOSED_OUTSIDE event inside the
basket's sync and the ACCOUNT_REFUSED event of the order guard). Every replay of the suite runs with
fake_mt5.StrictLock, which fails the test where the real lock would hang; here one replay per loop -- an entry, a
multi-leg close, a refused order, a block of the safety, an unblock -- with every file write watched: open() for
writing, os.replace, os.remove, os.makedirs, os.rename, os.link under the test's folder, while the bot holds its lock.
"""
import builtins
import importlib.util
import os
import traceback

import pytest

import test_turtle_bot as TB
from conftest import DEFAULTS, F, ROOT, SCALED, START, market, run_bot

_spec = importlib.util.spec_from_file_location('safety_of_the_lock_tests', ROOT / 'safety.py')
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

_ALLOWED_EVENTS = ('LEG_CLOSED_OUTSIDE', 'ACCOUNT_REFUSED')


class Watch:
    """Every write under `root` made while a bot of `bots` holds its mt5_lock (not while a test hook runs)."""

    def __init__(self, root, monkeypatch):
        self.root = os.path.realpath(str(root))
        self.bots, self.bad, self.paused, self.event = [], [], False, None
        real_open = builtins.open

        def watched_open(file, mode='r', *a, **k):
            if isinstance(mode, str) and set(mode) & set('wax+'):
                self.check('open', file)
            return real_open(file, mode, *a, **k)
        monkeypatch.setattr(builtins, 'open', watched_open)
        for name in ('replace', 'remove', 'makedirs', 'rename', 'link'):
            real = getattr(os, name)

            def watched(*a, _real=real, _name=name, **k):
                self.check(_name, a[-1] if _name in ('replace', 'rename', 'link') else a[0])
                return _real(*a, **k)
            monkeypatch.setattr(os, name, watched)

    def check(self, what, path):
        try:
            p = os.path.realpath(os.fsdecode(os.fspath(path)))
        except (TypeError, ValueError):
            return
        if self.paused or not p.startswith(self.root):
            return
        if any(getattr(b, 'mt5_lock', None) is not None and b.mt5_lock.locked() for b in self.bots):
            if self.event in _ALLOWED_EVENTS:
                return
            self.bad.append(f'{what} {p}\n' + ''.join(traceback.format_stack(limit=8)[:-2]))

    def hook(self, fn):
        """A test's own action at a fake time (it may run inside a terminal call, so inside the bot's lock): not the
        bot's write."""
        def run(f):
            self.paused = True
            try:
                fn(f)
            finally:
                self.paused = False
        return run

    def on_bot(self, bot, n):
        self.bots.append(bot)
        log_event = bot._log_event

        def logged(symbol, event, tag, details=None, server_time=None):
            was, self.event = self.event, event
            try:
                return log_event(symbol, event, tag, details, server_time)
            finally:
                self.event = was
        bot._log_event = logged


def _press(tmp_path, action):
    def go(f):
        S.press(str(tmp_path / DEFAULTS['ACCOUNT_FOLDER']), action, None, 'command line', f.clock.time(),
                need_pin=False)
    return go


def test_the_turtle_writes_no_file_while_it_holds_mt5_lock(tmp_path, monkeypatch):
    watch = Watch(tmp_path, monkeypatch)
    fake, clock = TB._market(TB._long_trip())
    fake.at(START + 830.0, lambda f: setattr(f, 'refuse_orders', 1))            # the first add refused once
    fake.at(START + 2400.0, watch.hook(_press(tmp_path, 'unblock')))           # after the losing trade's block
    run = TB._run(fake, clock, tmp_path / 'state', on_bot=watch.on_bot, keep_writers=True,
                  overrides={'SAFETY_STREAK_N': 1})
    ev = [e['event'] for e in run.events]
    assert 'BUY_MORE_REFUSED' in ev and 'SAFETY_BLOCKED' in ev and 'SAFETY_UNBLOCKED' in ev
    assert len(TB._closes(fake)) == 4 and not fake.positions                   # a 4-leg close
    assert (tmp_path / 'state' / 'safety_state.json').is_file()
    assert watch.bad == [], watch.bad[0]


@pytest.mark.slow
def test_the_basket_writes_no_file_while_it_holds_mt5_lock(tmp_path, monkeypatch):
    watch = Watch(tmp_path, monkeypatch)
    fake, clock = market(2400, seed=21)
    fake.refuse_orders = 1
    fake.at(START + 1800.0, watch.hook(_press(tmp_path, 'unblock')))
    run = run_bot(fake, clock, overrides={**SCALED, 'SAFETY_STREAK_N': 1}, state_dir=tmp_path / 'state',
                  on_new_bot=watch.on_bot, keep_writers=True)
    ev = [e['event'] for e in run.events]
    assert ('BUY_REFUSED' in ev or 'SELL_REFUSED' in ev) and 'SAFETY_BLOCKED' in ev and 'SAFETY_UNBLOCKED' in ev
    assert any('position' in o for o in fake.orders)
    assert watch.bad == [], watch.bad[0]


def test_the_strict_lock_fails_where_the_real_one_would_hang():
    lock = F.StrictLock()
    with lock:
        assert lock.locked()
        with pytest.raises(F.LockReentered):
            lock.acquire()
    assert not lock.locked()
    assert lock.acquire() and lock.locked()
    lock.release()
