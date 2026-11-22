"""
What safety.py may say and may be (spec rule 8, sections 5.2 and 13 "Wording"): the words its strings must not
hold, the sentences it shows the owner, what it imports, that it reads no clock and keeps no module-level state,
and the names and signatures the other parts of the bot call it by.

Run:  python3 -B -m pytest tests_demo/test_safety_wording.py -q -p no:cacheprovider
"""
import ast
import importlib.util
import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from conftest import found

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / 'safety.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)


def _load():
    spec = importlib.util.spec_from_file_location('safety_tested_wording', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()
T0 = datetime(2026, 11, 21, 14, 5, tzinfo=timezone.utc).timestamp()

NEVER = ('demo', 'virtual', 'slot', 'epoch', 'latch', 'rebase')      # rule 8, in no string at all
FIELD_NAME = re.compile(r'^[a-z_][a-z0-9_]*$')


def _docstrings(tree):
    """The string nodes that are docstrings: the first statement of the module, of a class or of a function."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _string_literals(tree):
    """(line, text) of every string literal that is not a docstring; the fixed parts of f-strings are among them."""
    skip = _docstrings(tree)
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip]


def test_no_string_of_safety_py_holds_a_word_the_owner_must_not_read():
    """
    Exactly what is checked: every string literal of safety.py that is not a docstring (the module's, a class's or
    a function's first statement), the fixed text of f-strings included, compared without regard to case.

    - It must not contain 'demo', 'virtual', 'slot', 'epoch', 'latch' or 'rebase' anywhere, not even as part of a
      longer word or of a dict key.
    - It may contain 'period' only when the WHOLE literal is a field name (lower-case letters, digits and
      underscores, such as 'period' or 'account_period'): the spec names that field of the state, the view and
      `expect`. In any literal with a space or punctuation, that is in anything that can be a sentence, 'period'
      is refused.
    Comments and docstrings are not strings the program can show, and are not checked.
    """
    literals = _string_literals(TREE)
    assert len(literals) > 400                                       # (the walk really found the module's strings)
    bad = []
    for line, text in literals:
        low = text.lower()
        for word in NEVER:
            if word in low:
                bad.append((line, word, text[:60]))
        if 'period' in low and not FIELD_NAME.match(text):
            bad.append((line, 'period', text[:60]))
    assert bad == []
    # the check itself: it does see a word inside an f-string and tells a field name from a sentence
    probe = ast.parse("x = {'period': 1}\ny = f'the {n} demo slots'\nz = 'the period ended'\n"
                      "def f():\n    'a docstring may say epoch'\n    return 'account_period'\n")
    found = sorted(t for _, t in _string_literals(probe))
    assert found == [' demo slots', 'account_period', 'period', 'the ', 'the period ended']
    assert [bool(FIELD_NAME.match(t)) for t in found] == [False, True, True, False, False]


def _everything_the_module_says(tmp_path):
    """Sentences of every state, every answer of a press, the status lines and the usage text."""
    said = []
    acct = tmp_path / 'acct'
    gold = S.Tracker(str(acct), str(tmp_path / 'g' / 'state' / 'safety_state.json'), 'acct_x9', 'acct_b9',
                     S.Limits(20.0, 10.0, 3), login=12345678)
    btc = S.Tracker(str(acct), str(tmp_path / 'b' / 'state' / 'safety_state.json'), 'acct_b9', 'acct_x9',
                    S.Limits(20.0, 10.0, 3), login=12345678)

    def tick(tr, now, balance, cash=None, read_at=None, waiting=0):
        view = tr.poll(now, balance, cash, read_at, waiting)
        tr.flush(now)
        said.extend(view['reasons'])
        if view['error']:
            said.append(view['error'])
        return view

    said.extend(gold.view()['reasons'] + [gold.view()['error']])     # before load
    for tr in (gold, btc):
        tr.load(T0)
        tick(tr, T0, 1500.0)
        tick(tr, T0 + 1, 1500.0, [], T0 + 0.5)
    gold.on_trade_closed(T0 + 2, 'a', -1.0)
    gold.on_trade_closed(T0 + 3, 'b', -1.0)
    tick(gold, T0 + 4, 1500.0, waiting=1)                            # waiting for a result
    tick(gold, T0 + 4.5, 1500.0, waiting=2)
    gold.on_trade_closed(T0 + 5, 'c', -1.0)
    tick(btc, T0 + 5.5, 1500.0)
    tick(gold, T0 + 6, 1500.0)                                       # blocked for losing trades, partner known
    btc.note_other_program(T0 + 7, 'another program holds 2 trades of its own on BTCUSDm')
    tick(btc, T0 + 8, 1500.0)
    tick(gold, T0 + 9, 1500.0)
    tick(gold, T0 + 10, 1100.0)                                      # a limit is being checked
    tick(gold, T0 + 14, 1100.0, [], T0 + 13.5)                       # the account is blocked
    tick(btc, T0 + 15, 1100.0)
    tick(btc, T0 + 16, 1100.0)
    (acct / 'safety_block_start.json').write_bytes(b'')              # a block that says nothing
    fresh = S.Tracker(str(acct), None, 'acct_b9', None, S.Limits(20.0, 10.0, 3))
    fresh.load(T0 + 17)
    tick(fresh, T0 + 18, 1100.0)
    S.ensure_pin(str(acct))
    pin = (acct / 'safety_pin.txt').read_text().strip()
    web = 'dashboard acct_x9 from 10.0.0.9'
    for i, (action, typed, kw) in enumerate([
            ('unblock', '', {}), ('unblock', 'wrong', {}), ('unblock', pin, {'expect': {'period': 'x', 'enabled': True}}),
            ('new-account', pin, {}), ('nothing', pin, {}), ('unblock', pin, {}), ('unblock', pin, {}),
            ('off', pin, {}), ('off', pin, {}), ('on', None, {}), ('on', None, {}),
            ('off', 'w1', {}), ('off', 'w2', {}), ('off', 'w3', {}), ('off', 'w4', {}), ('off', 'w5', {}),
            ('off', pin, {})]):
        said.append(S.press(str(acct), action, typed, web, T0 + 20 + i, **kw)[1])
    for action in ('unblock', 'off', 'on', 'new-account', 'off'):
        said.append(S.press(str(acct), action, None, 'command line', T0 + 60, need_pin=False)[1])
    tick(gold, T0 + 70, 1100.0)
    assert tick(gold, T0 + 71, 1100.0)['enabled'] is False           # OFF
    said.extend(S.status_lines(str(acct), T0 + 80))
    (acct / 'safety_pin.txt').write_text('a b')
    said.append(S.press(str(acct), 'off', 'x', web, T0 + 90000)[1])
    (acct / 'safety_pin.txt').unlink()
    said.append(S.press(str(acct), 'off', 'x', web, T0 + 90001)[1])
    (acct / 'safety_restart.json').write_text('{')
    said.append(S.press(str(acct), 'on', None, web, T0 + 90002)[1])
    said.extend(S.status_lines(str(acct), T0 + 90003))
    said.extend(S.status_lines(str(tmp_path / 'nowhere'), T0))
    said.append(S._USAGE)
    stuck = S.Tracker(str(tmp_path / 'acct2'), str(tmp_path / 's' / 'state' / 'safety_state.json'), 'acct_x9', None,
                      S.Limits(20.0, 10.0, 3), login=12345678)
    stuck.load(T0)
    tick(stuck, T0, 1500.0)
    for dt in range(1, 612, 10):
        tick(stuck, T0 + dt, 1700.0)                                 # a rise nobody could judge for ten minutes
    real_open = open

    def no_state(path, mode='r', *a, **k):
        if str(path).endswith('.tmp') and 'safety_state' in str(path):
            raise PermissionError(13, 'Permission denied')
        return real_open(path, mode, *a, **k)
    S.open = no_state                                                # a state file that cannot be saved
    try:
        tick(stuck, T0 + 615, 1700.0, [], T0 + 614.5)
        tick(stuck, T0 + 800, 1700.0)
    finally:
        del S.open
    lost = S.Tracker(str(tmp_path / 'file' / 'acct'), None, 'acct_x9', None, S.Limits())
    (tmp_path / 'file').write_text('x')
    lost.load(T0)
    said.extend(lost.poll(T0, 1500.0)['reasons'] + [lost.view()['error']])
    return [s for s in said if s]


def test_no_sentence_the_module_shows_holds_one_of_those_words(tmp_path):
    """The same rule on what the module really says: the sentences of every state of the bar, every answer of a
    button press, the lines of `safety.bat status` and the usage text hold none of rule 8's words, 'period'
    included, and are plain ASCII (they are printed in a console on the server)."""
    said = _everything_the_module_says(tmp_path)
    assert len(set(said)) > 40
    for sentence in said:
        low = sentence.lower()
        for word in NEVER + ('period',):
            assert word not in low, (word, sentence)
        sentence.encode('ascii')
        assert '12345678' not in sentence                            # rule 9: never the whole account number
    joined = '\n'.join(said)
    for expected in ('Watching account ...5678. New trades are allowed.',
                     'The safety check failed: no new trades until it works again or the safety is turned OFF.',
                     'Nothing is blocked.', 'The safety is already ON.', 'The safety is already OFF.',
                     'Wrong PIN. 4 more tries, then the buttons lock for 10 minutes.',
                     'The details of this block cannot be read.',
                     'No limit is applied: both bots of account ...5678 trade exactly as the strategy says. The '
                     'meters are for information only.',
                     'The safety changed since this page was refreshed. Check the bar and press again.',
                     'The safety files cannot be read right now. Nothing was changed; try again.',
                     "the account's cash history could not be read since 14:05 UTC, so a change of the balance "
                     'cannot be judged',
                     'the safety state could not be saved since 14:15 UTC (PermissionError'):
        assert expected in joined, expected


def test_safety_py_imports_the_standard_library_only_and_constants_only_inside_main():
    """Spec 5.2: the dashboard runs in an environment with only dash and plotly, and a module that imported
    constants at import time would keep the first test's constants for the whole test run."""
    top = set()
    for node in TREE.body:
        if isinstance(node, ast.Import):
            top.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            top.add((node.module or '').split('.')[0])
    assert top == {'hashlib', 'hmac', 'json', 'math', 'ntpath', 'os', 're', 'secrets', 'sys', 'threading', 'time',
                   'datetime'}
    assert top <= set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else True
    inner = []
    for fn in ast.walk(TREE):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                if isinstance(node, ast.Import):
                    inner += [(fn.name, a.name) for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    inner.append((fn.name, node.module))
    # (ctypes only where QuickEdit of a Windows console is switched off: a Python without it must still import this)
    assert inner == [('quick_edit_off', 'ctypes'), ('main', 'constants')]
    for name in ('MetaTrader5', 'numpy', 'pandas', 'tracelog', 'mt5_helper', 'dash'):
        assert not re.search(rf'^\s*(import|from)\s+{name}\b', SOURCE, re.M), name


def test_safety_py_reads_no_clock_except_in_main():
    """Every function takes `now`. The only clock reads are main()'s time.time() (the command line) and the short
    time.sleep() between two tries of a refused file move or read."""
    uses = []
    for fn in [n for n in ast.walk(TREE) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'time':
                uses.append((fn.name, node.attr))
    assert sorted(set(uses)) == [('_read_json', 'sleep'), ('_replace_retry', 'sleep'), ('main', 'time')]
    for forbidden in ('.now(', '.utcnow(', '.today(', 'perf_counter', 'monotonic', 'time_ns', 'gmtime(', 'localtime('):
        assert not found(SOURCE, forbidden), forbidden


def test_safety_py_keeps_no_module_level_state_but_the_lock_of_press():
    mutable = []
    for node in TREE.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets, value = [t.id for t in node.targets if isinstance(t, ast.Name)], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target.id], node.value
        for name in targets:
            if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
                mutable.append(name)
            elif isinstance(value, ast.Call) and not (
                    isinstance(value.func, ast.Attribute) and value.func.attr == 'compile'
                    or isinstance(value.func, ast.Name) and value.func.id == 'datetime'):
                mutable.append(name)
    assert mutable == ['_PRESS_LOCK']
    assert isinstance(S._PRESS_LOCK, type(__import__('threading').Lock()))
    for name, value in vars(S).items():
        if name.isupper() or (name.startswith('_') and name[1:].isupper()):
            assert isinstance(value, (str, int, float, tuple, re.Pattern, datetime, type(S._PRESS_LOCK))), name


def _params(fn):
    return [(p.name, p.default if p.default is not inspect.Parameter.empty else '<needed>')
            for p in inspect.signature(fn).parameters.values() if p.name != 'self']


def test_the_names_and_signatures_the_other_parts_of_the_bot_use():
    """Spec 5.2. app.py, tracelog.py, dashboard.py and collect_logs.py call these by name: a change here is a change
    in three other files. (Arguments added after the spec's last one, with a default, are allowed.)"""
    assert _params(S.Limits) == [('drop_pct', None), ('day_pct', None), ('streak_n', None)]
    assert _params(S.Tracker) == [('account_dir', '<needed>'), ('state_path', '<needed>'), ('branch', '<needed>'),
                                  ('partner_branch', '<needed>'), ('limits', '<needed>'), ('default_on', True),
                                  ('login', None), ('confirm_s', 3.0), ('cash_wait_s', 60.0)]
    assert _params(S.Tracker.load) == [('now', '<needed>')]
    assert _params(S.Tracker.poll) == [('now', '<needed>'), ('balance', '<needed>'), ('cash_deals', None),
                                       ('cash_read_at', None), ('pending_results', 0)]
    assert _params(S.Tracker.on_trade_closed) == [('now', '<needed>'), ('trade_key', '<needed>'),
                                                  ('net_pl', '<needed>')]
    assert _params(S.Tracker.note_other_program) == [('now', '<needed>'), ('text', '<needed>')]
    assert _params(S.Tracker.flush) == [('now', '<needed>')]
    assert _params(S.Tracker.needs_cash) == [] and _params(S.Tracker.cash_since) == []
    assert _params(S.Tracker.view) == []
    assert _params(S.read_controls)[:1] == [('account_dir', '<needed>')]
    assert all(default != '<needed>' for _, default in _params(S.read_controls)[1:])
    assert _params(S.read_statuses) == [('account_dir', '<needed>')]
    assert _params(S.pin_path) == [('account_dir', '<needed>')] == _params(S.ensure_pin)
    assert _params(S.press)[:7] == [('account_dir', '<needed>'), ('action', '<needed>'), ('pin', '<needed>'),
                                    ('by', '<needed>'), ('now', '<needed>'), ('need_pin', True), ('expect', None)]
    assert all(default != '<needed>' for _, default in _params(S.press)[7:])
    assert _params(S.main)[:1] == [('argv', None)]
    assert _params(S.account_dir) == [('output_dir', '<needed>'), ('folder', '<needed>')]
    assert _params(S.mask_login) == [('login', '<needed>')] == _params(S.login_sha)
    assert (S.SWITCH_FILE, S.RESTART_FILE, S.PIN_FILE, S.AUDIT_FILE, S.LOCKOUT_FILE, S.CLAIM_FILE) == (
        'safety_switch.json', 'safety_restart.json', 'safety_pin.txt', 'safety_audit.jsonl', 'safety_lockout.json',
        'account_claim.json')
    assert S.FIRST_ID == 'start' and S.CONFIRM_S == 3.0 and S.CASH_WAIT_S == 60.0 and S.ERROR_AFTER_S == 60.0
    assert S.ERROR_SENTENCE == ('The safety check failed: no new trades until it works again or the safety is '
                                'turned OFF.')


def test_the_view_has_exactly_the_keys_of_the_spec_plus_one_label():
    view = S.build_view(None, S.Limits(), T0)
    assert sorted(view) == sorted(['enabled', 'blocked', 'hold', 'pending', 'account_blocked', 'bot_blocked',
                                   'blocked_scope', 'reasons', 'since', 'period', 'at', 'started_at', 'error', 'drop',
                                   'day', 'streak', 'partner', 'limits', 'account_dir', 'login_tail', 'state'])
    assert view['state'] == 'on'                                     # (a label for the bar's colour: on / checking /
    json.dumps(view, allow_nan=False)                                # account_blocked / bot_blocked / off / error)
