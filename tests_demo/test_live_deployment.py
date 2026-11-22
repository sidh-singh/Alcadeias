"""
What makes this tree one real-money branch: the deployment block of constants.py, the branch label, and the words
the bot uses for itself.

The 20 real-money branches are one code line. Everything that differs between them -- the label, the account, the
magic number, the folders, the port, the share of the balance, the safety limits -- is in ONE block of constants.py
that the branch generator writes. A second assignment of one of its names anywhere else in the file would silently
win or lose against the block (two bots in one state folder, a bot with another bot's magic number), so:
  * the block is delimited by exactly its two marker lines, above the design examples;
  * it holds exactly the deployment names, each assigned once in the whole file, there;
  * the names of the forward test (DEMO_BRANCH, the VIRTUAL_* pair) are gone from the code;
  * no text of app.py calls this bot, its account or its balance 'demo', 'virtual' or a 'slot'.
No value of the block is written in this file (the tests of every branch are the same): only its shape is checked.
"""
import ast
import ntpath
import re

from conftest import DEFAULTS, AS_WRITTEN, ROOT, SAFETY_OFF, wording_offenders
from conftest import found

BEGIN = '# ─── Deployment: this branch (written by the branch generator; one block per branch) ───'
END = '# ─── End of deployment ───'
EXAMPLES = '# ─── Design examples ───'
NAMES = ['BRANCH', 'PARTNER_BRANCH', 'ACCOUNT_SLOT', 'ACCOUNT_FOLDER', 'MAGIC', 'ORDER_COMMENT', 'OUTPUT_DIR',
         'DASHBOARD_HOST', 'DASHBOARD_PORT', 'ACCOUNT_SHARE', 'SAFETY_DEFAULT_ON', 'SAFETY_DROP_PCT', 'SAFETY_DAY_PCT',
         'SAFETY_STREAK_N', 'LOG_KEEP_DAYS', 'OLD_LOGINS_SHA256']
OLD_NAMES = ('DEMO_BRANCH', 'VIRTUAL_START_BALANCE', 'VIRTUAL_START_DATE')


def _constants_text():
    return (ROOT / 'constants.py').read_text(encoding='utf-8')


def _line_of(text, marker):
    """The 1-based number of the one line that is exactly `marker`."""
    hits = [i for i, line in enumerate(text.splitlines(), 1) if line == marker]
    assert len(hits) == 1, f'{marker!r} must be one whole line of constants.py, exactly once (found {len(hits)})'
    return hits[0]


def _assignments(text):
    """{name: [line, ...]} of every name constants.py binds, wherever: plain, annotated and augmented assignments,
    loop and with targets, imports, def / class."""
    found = {}

    def add(target, line):
        for node in ast.walk(target):
            if isinstance(node, ast.Name):
                found.setdefault(node.id, []).append(line)

    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                add(target, node.lineno)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            add(node.target, node.lineno)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            add(node.target, getattr(node, 'lineno', getattr(node.iter, 'lineno', 0)))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    add(item.optional_vars, node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found.setdefault((alias.asname or alias.name).split('.')[0], []).append(node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.setdefault(node.name, []).append(node.lineno)
    return found


def test_every_deployment_name_is_assigned_once_and_inside_the_block():
    text = _constants_text()
    begin, end = _line_of(text, BEGIN), _line_of(text, END)
    assert begin < end < _line_of(text, EXAMPLES)       # above the design examples: the tests' defaults hold it
    where = _assignments(text)
    for name in NAMES:
        lines = where.get(name, [])
        assert len(lines) == 1, f'{name} is assigned {len(lines)} times in constants.py (lines {lines}): once, in the block'
        assert begin < lines[0] < end, f'{name} is assigned at line {lines[0]}, outside the deployment block'
    # and the block holds nothing else: one plain assignment per name, in the generator's order, no other statement
    body = text.splitlines()[begin:end - 1]
    block = ast.parse('\n'.join(body))
    assert all(isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
               for node in block.body), 'the deployment block holds something that is not NAME = value'
    assert [node.targets[0].id for node in block.body] == NAMES
    assert [line.split(' = ')[0] for line in body] == NAMES         # one line each, no comment line, no blank line


def test_a_second_assignment_outside_the_block_is_found():
    """The check itself: the same file with one deployment name assigned again below the block (what a careless
    merge of a design block could leave) has two assignments of it, one outside."""
    text = _constants_text() + "\nOUTPUT_DIR = r'C:\\elsewhere'\n"
    lines = _assignments(text)['OUTPUT_DIR']
    assert len(lines) == 2 and not (_line_of(text, BEGIN) < lines[1] < _line_of(text, END))


def test_the_block_describes_one_bot_of_one_account():
    """The shape of the values (never the values): a branch live<n>_<design> and its partner on the same account,
    the account's folder, an own folder named like the branch, limits that are numbers."""
    c = AS_WRITTEN
    n = c['ACCOUNT_SLOT']
    assert isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 10
    for name in ('BRANCH', 'PARTNER_BRANCH'):
        assert isinstance(c[name], str) and re.fullmatch(rf'live{n}_[a-z]+\d+', c[name]), (name, c[name])
    assert c['BRANCH'] != c['PARTNER_BRANCH']
    assert c['ACCOUNT_FOLDER'] == f'live{n}_account'
    assert isinstance(c['MAGIC'], int) and not isinstance(c['MAGIC'], bool) and c['MAGIC'] > 0
    assert c['ORDER_COMMENT'] is None or (isinstance(c['ORDER_COMMENT'], str) and c['ORDER_COMMENT'])
    assert ntpath.isabs(c['OUTPUT_DIR']) and ntpath.basename(ntpath.normpath(c['OUTPUT_DIR'])) == c['BRANCH']
    assert isinstance(c['DASHBOARD_HOST'], str) and c['DASHBOARD_HOST']
    assert isinstance(c['DASHBOARD_PORT'], int) and 1024 < c['DASHBOARD_PORT'] < 65536
    assert isinstance(c['ACCOUNT_SHARE'], (int, float)) and 0 < c['ACCOUNT_SHARE'] <= 1
    assert isinstance(c['SAFETY_DEFAULT_ON'], bool)
    for name in ('SAFETY_DROP_PCT', 'SAFETY_DAY_PCT'):
        assert c[name] is None or (isinstance(c[name], (int, float)) and 0 < c[name] < 100), name
    assert c['SAFETY_STREAK_N'] is None or (isinstance(c['SAFETY_STREAK_N'], int) and c['SAFETY_STREAK_N'] >= 1)
    assert isinstance(c['LOG_KEEP_DAYS'], int) and c['LOG_KEEP_DAYS'] >= 1
    old = c['OLD_LOGINS_SHA256']
    assert isinstance(old, tuple) and old and all(isinstance(h, str) and re.fullmatch(r'[0-9a-f]{64}', h) for h in old)


def test_the_tests_defaults_are_the_block_with_the_safety_limits_off():
    """DEFAULTS (what every replay of the suite starts from) is the head of constants.py as written, except the three
    limits of the auto-safety: None = that rule is off, so a replay takes the strategy's trades. A test of the
    safety sets its own limits."""
    assert set(SAFETY_OFF) == {'SAFETY_DROP_PCT', 'SAFETY_DAY_PCT', 'SAFETY_STREAK_N'}
    assert all(DEFAULTS[k] is None for k in SAFETY_OFF)
    assert {k: v for k, v in DEFAULTS.items() if k not in SAFETY_OFF} == {k: v for k, v in AS_WRITTEN.items()
                                                                           if k not in SAFETY_OFF}
    assert all(name in AS_WRITTEN for name in NAMES)


def test_the_version_is_a_live_version_outside_the_block():
    text = _constants_text()
    lines = _assignments(text)['VERSION']
    assert len(lines) == 1 and not (_line_of(text, BEGIN) < lines[0] < _line_of(text, END))
    assert re.fullmatch(r'\d+\.\d+\.\d+-live\.\d+', AS_WRITTEN['VERSION'])


def test_the_names_of_the_forward_test_are_gone():
    """DEMO_BRANCH is the label BRANCH now, in every Python file of the tree; the VIRTUAL_* pair is gone from the
    bot's own files (the size comes from the real balance). No guard hangs on a label: there is no name left whose
    emptiness would switch a check off."""
    where = _assignments(_constants_text())
    assert not [name for name in OLD_NAMES if name in where]
    for path in sorted(ROOT.glob('*.py')):
        assert not found(path.read_text(encoding='utf-8'), 'DEMO_BRANCH'), path.name
    for name in ('app.py', 'mt5_helper.py', 'constants.py'):
        source = (ROOT / name).read_text(encoding='utf-8')
        assert 'VIRTUAL_START' not in source and 'virtual_balance' not in source, name


def test_the_design_block_of_the_branch_is_still_the_last_thing_in_the_file():
    """The branch's own design follows the examples (the generator replaces it): the deployment block is not in it,
    and it sets no deployment name."""
    text = _constants_text()
    tail = text.split(EXAMPLES, 1)[1]
    assert '# ─── Design of this branch' in tail
    assigned = {line.split(' = ')[0] for line in tail.splitlines() if re.match(r'^[A-Z][A-Z0-9_]* = ', line)}
    assert assigned and not assigned & set(NAMES) and not assigned & set(OLD_NAMES)


def test_no_text_of_app_py_says_demo_virtual_or_slot():
    """The wording of a real-money bot (the owner reads these texts in the console, the log and on the dashboard):
    no string literal of app.py outside its docstrings holds 'demo', 'virtual' or 'slot', except the name of the MT5
    constant and the word 'demo' alone (the terminal's name for a demo account: a refusal must be able to say what
    kind of account MetaTrader 5 holds)."""
    assert wording_offenders(ROOT / 'app.py') == []


def test_the_wording_check_finds_a_text_that_says_it(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text('"""a docstring may say demo, virtual or slot"""\n'
                   'A = getattr(object, "ACCOUNT_TRADE_MODE_DEMO", 0)\n'
                   'B = "demo"\n'
                   'C = f"the Virtual balance of {A}"\n'
                   'D = "give this SLOT its own terminal"\n'
                   'def f():\n    """demo"""\n    return "not the demo account"\n', encoding='utf-8')
    found = wording_offenders(bad)
    assert [line.split(':')[0] for line in found] == ['4', '5', '8'], found
