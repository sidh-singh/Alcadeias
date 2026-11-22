"""
QuickEdit in the console windows of the bot and the dashboard (Windows).

start_job.bat runs the bot in the console of its own window, and on Windows Server that console has QuickEdit on: one
left click into the window starts a selection, and from then on every write to the console waits until Esc, Enter
or a right click. The bot prints a line on every poll, so one click would stop its loop -- its stops, targets and
closes too. The dashboard's page server writes a line for every request: its page would stop answering. So both
switch QuickEdit off first thing (safety.quick_edit_off: GetStdHandle(STD_INPUT_HANDLE), GetConsoleMode,
SetConsoleMode with ENABLE_EXTENDED_FLAGS on and ENABLE_QUICK_EDIT_MODE off), say in the window whether it worked
-- the bot also in its log, as one INFO line -- and start whatever happens there.

Nothing here runs on Windows: kernel32 is a stand-in object; on this system the real call is a no-op.
"""
import ast
import importlib.util
import os
import sys

import pytest

from conftest import ROOT


def _load():
    spec = importlib.util.spec_from_file_location('safety_tested_quick_edit', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()

STD_INPUT_HANDLE = -10
QUICK_EDIT, EXTENDED = 0x0040, 0x0080
HANDLE = 0x54                              # (a console input handle as Windows gives one)


class Kernel32:
    """A stand-in for ctypes.windll.kernel32: the console's mode, and every call made to it. `fail`: {name: an
    exception it raises}; `refuse`: names that answer 0 (the call failed)."""

    def __init__(self, mode=0x01F7, handle=HANDLE, fail=None, refuse=()):
        self.mode, self.handle, self.fail, self.refuse = mode, handle, dict(fail or {}), set(refuse)
        self.calls = []

    def _answer(self, name):
        if name in self.fail:
            raise self.fail[name]
        return 0 if name in self.refuse else 1

    def GetStdHandle(self, which):                                  # noqa: N802 (the Windows names)
        self.calls.append(('GetStdHandle', which))
        if 'GetStdHandle' in self.fail:
            raise self.fail['GetStdHandle']
        return self.handle

    def GetConsoleMode(self, handle, mode_ref):                     # noqa: N802
        self.calls.append(('GetConsoleMode', handle))
        answer = self._answer('GetConsoleMode')
        if answer:
            mode_ref._obj.value = self.mode                         # (what the DWORD it points to receives)
        return answer

    def SetConsoleMode(self, handle, mode):                         # noqa: N802
        self.calls.append(('SetConsoleMode', handle, mode))
        answer = self._answer('SetConsoleMode')
        if answer:
            self.mode = mode
        return answer


# ───────────────────────────── safety.quick_edit_off ─────────────────────────────

@pytest.mark.skipif(os.name == 'nt', reason='the real console is only left alone where it is not Windows')
def test_on_this_system_it_is_a_no_op_that_never_raises():
    assert S.quick_edit_off() is None
    assert S.quick_edit_off(None) is None


@pytest.mark.parametrize('mode, expected', [
    (0x01F7, 0x01B7),           # the default of a console: QuickEdit and the extended flags on
    (0x0047, 0x0087),           # QuickEdit on, the extended flags off: they must be set for the change to count
    (0x00A7, 0x00A7),           # QuickEdit already off: set again, unchanged
    (0x0000, 0x0080),
])
def test_quick_edit_goes_off_and_the_extended_flags_on(mode, expected):
    k = Kernel32(mode=mode)
    assert S.quick_edit_off(k) == (True, None)
    assert k.calls == [('GetStdHandle', STD_INPUT_HANDLE), ('GetConsoleMode', HANDLE),
                       ('SetConsoleMode', HANDLE, (mode | EXTENDED) & ~QUICK_EDIT)]
    assert k.mode == expected and not k.mode & QUICK_EDIT and k.mode & EXTENDED


@pytest.mark.parametrize('kernel32', [
    Kernel32(fail={'GetStdHandle': OSError(6, 'The handle is invalid')}),
    Kernel32(fail={'GetConsoleMode': RuntimeError('anything')}),
    Kernel32(refuse={'GetConsoleMode'}),                            # input redirected: not a console
    Kernel32(handle=-1),                                            # INVALID_HANDLE_VALUE
    Kernel32(handle=0),
    Kernel32(handle=None),
], ids=['GetStdHandle raises', 'GetConsoleMode raises', 'GetConsoleMode fails', 'invalid handle', 'no handle',
        'None'])
def test_a_kernel32_that_raises_or_refuses_changes_nothing(kernel32):
    ok, why = S.quick_edit_off(kernel32)
    assert ok is False and isinstance(why, str) and why
    assert 'SetConsoleMode' not in [c[0] for c in kernel32.calls] and kernel32.mode == 0x01F7


@pytest.mark.parametrize('how', [{'fail': {'SetConsoleMode': OSError(5, 'Access is denied')}},
                                 {'refuse': {'SetConsoleMode'}}])
def test_a_mode_that_cannot_be_set_is_said_and_never_raised(how):
    k = Kernel32(**how)
    ok, why = S.quick_edit_off(k)
    assert ok is False and why and k.mode == 0x01F7


def test_a_kernel32_without_the_calls_is_no_exception_either():
    assert S.quick_edit_off(object())[0] is False


# ───────────────────────────── the bot: first thing in main(), one INFO line ─────────────────────────────

class _StubBot:
    """MT5TradingBot as main() uses it, without the trading: what it was told to log."""
    made = []

    def __init__(self, mode, target_symbol=None):
        self.boots, self.exit_code = [], 0
        _StubBot.made.append(self)

    def _boot(self, level, cat, msg, kv=None, exc=False):
        self.boots.append((level, cat, msg, kv))

    def execute_job(self):
        return True


def _main(m, monkeypatch, argv, answer):
    calls = []

    def quick_edit_off(kernel32=None):
        calls.append(kernel32)
        if isinstance(answer, BaseException):
            raise answer
        return answer
    monkeypatch.setattr(m.app.safety, 'quick_edit_off', quick_edit_off)
    monkeypatch.setattr(m.app, 'MT5TradingBot', _StubBot)
    monkeypatch.setattr(sys, 'argv', ['app.py'] + list(argv))
    _StubBot.made = []
    with pytest.raises(SystemExit) as end:
        m.app.main()
    return calls, end.value.code, (_StubBot.made[0] if _StubBot.made else None)


def test_the_bot_switches_quick_edit_off_first_and_logs_one_info_line(mods, monkeypatch, capsys):
    m = mods()
    calls, code, bot = _main(m, monkeypatch, ['live', '--symbol', 'XAUUSDm'], (True, None))
    line = 'QuickEdit is off in this window: a click inside it can no longer pause the bot.'
    assert calls == [None] and code == 0
    assert bot.boots == [('INFO', 'START', line, {'quick_edit_off': True})]
    assert f'✓ {line}' in capsys.readouterr().out
    # it could not be done: said as well, and the bot starts all the same
    calls, code, bot = _main(m, monkeypatch, ['live', '--symbol', 'XAUUSDm'], (False, 'OSError: Access is denied'))
    (level, cat, text, kv), = bot.boots
    assert (level, cat, kv) == ('INFO', 'START', {'quick_edit_off': False}) and code == 0
    assert text.startswith('QuickEdit could not be switched off in this window (OSError: Access is denied). Do not '
                           'click inside this window') and '"Select"' in text
    assert f'⚠ {text}' in capsys.readouterr().out


@pytest.mark.parametrize('answer', [None, RuntimeError('anything')], ids=['not Windows', 'raises'])
def test_where_there_is_nothing_to_do_or_it_fails_the_bot_starts_as_before(mods, monkeypatch, capsys, answer):
    m = mods()
    calls, code, bot = _main(m, monkeypatch, ['live'], answer)
    assert calls == [None] and code == 0 and bot.boots == []
    assert 'QuickEdit' not in capsys.readouterr().out


def test_it_comes_before_the_mode_word_is_even_read(mods, monkeypatch, capsys):
    m = mods()
    calls, code, bot = _main(m, monkeypatch, ['demo'], (True, None))
    assert calls == [None] and code == m.app.EXIT_NEEDS_OWNER and bot is None
    out = capsys.readouterr().out
    assert out.index('QuickEdit is off in this window') < out.index('This is the real-money branch')


def test_main_calls_it_as_its_first_statement():
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    first = main.body[1]                                            # (after the docstring)
    assert isinstance(first, ast.Assign) and ast.unparse(first.value) == '_console_quick_edit_off()'


# ───────────────────────────── the dashboard: first thing when started as a program ─────────────────────────────

@pytest.fixture
def dashboard():
    """dashboard.py imported from this branch (its constants.py, its safety.py), put back as it was afterwards."""
    pytest.importorskip('dash')
    pytest.importorskip('plotly')
    names = ('constants', 'dashboard', 'safety')
    saved = {n: sys.modules.get(n) for n in names}
    sys.path.insert(0, str(ROOT))
    try:
        for n in names:
            sys.modules.pop(n, None)
        import dashboard
        yield dashboard
    finally:
        sys.path.remove(str(ROOT))
        for n in names:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


def test_the_dashboard_says_whether_it_worked_in_plain_ascii(dashboard, monkeypatch):
    D = dashboard
    monkeypatch.setattr(D.safety, 'quick_edit_off', lambda kernel32=None: (True, None))
    assert D._quick_edit_line() == ('QuickEdit is off in this window: a click inside it can no longer pause the '
                                    'dashboard.')
    monkeypatch.setattr(D.safety, 'quick_edit_off', lambda kernel32=None: (False, 'OSError: Access is denied'))
    text = D._quick_edit_line()
    assert text.startswith('QuickEdit could not be switched off in this window (OSError: Access is denied). Do not '
                           'click inside this window') and text.isascii()
    monkeypatch.setattr(D.safety, 'quick_edit_off', lambda kernel32=None: None)
    assert D._quick_edit_line() is None

    def boom(kernel32=None):
        raise RuntimeError('anything')
    monkeypatch.setattr(D.safety, 'quick_edit_off', boom)
    assert D._quick_edit_line() is None
    # on this system, for real: nothing to do (and no exception)
    monkeypatch.undo()
    if os.name != 'nt':
        assert D._quick_edit_line() is None


def test_the_dashboards_main_block_switches_it_off_before_anything_else():
    tree = ast.parse((ROOT / 'dashboard.py').read_text(encoding='utf-8'))
    block = next(n for n in tree.body if isinstance(n, ast.If) and ast.unparse(n.test) == "__name__ == '__main__'")
    first, second = block.body[0], block.body[1]
    assert isinstance(first, ast.Assign) and ast.unparse(first.value) == '_quick_edit_line()'
    assert ast.unparse(second) == 'if _quick_edit:\n    _say(_quick_edit)'
