"""
The launchers (*.bat in the branch folder, spec section 11), checked as text.

Nobody can run a .bat file where this code is written and tested, and the first time they run is on a server with
real money. So they follow strict rules that leave cmd.exe nothing to get wrong, and every rule is a check here:

  - plain ASCII, one kind of line ending, no tab, no blank at the end of a line;
  - no parenthesised block at all (in fact no bracket at all): every `if` is one line;
  - every `goto` has its label exactly once and every label is used;
  - `if errorlevel` only on the line right after a python or pip line, and the exit code of the bot is read on the
    line right after app.py and compared as text (78 and 2: only the owner can fix it; 0: the owner stopped it);
  - no `timeout` (it fails without a console): waits are `ping -n N 127.0.0.1 > nul`;
  - no default mode: only the word `live` starts the bot;
  - a percent sign is a known variable, or doubled;
  - branch_env.bat, the one launcher file that differs between branches, agrees with constants.py and symbols.json;
  - .gitattributes makes git write every .bat with CR LF, whatever the server's own git settings.

The checks are small functions that return what is wrong, and tests further down feed each of them a line that
breaks its rule, so a check that stops seeing anything fails too.

Because the rules leave only a handful of kinds of line (set, if ... goto, call, echo, exit /b, a program), a few
lines of Python can follow them the way cmd.exe does. "The launchers, walked through" below does that with the real
files and a stand-in for python.exe: every way through them (the wrong word, no Python, missing packages, each exit
code of the bot, the restart loop) is walked, and a line of a kind the walk does not know fails the test.

The README's first section, which the branch generator stamps like branch_env.bat, is checked at the end: it must
agree with constants.py and symbols.json, and nothing below it may name this branch's own values. The sections and
the steps of "First start" that the bot's and the dashboard's advice texts send the owner to must be there, about
what the advice says they are about.

No value of the deployment block is written here: the branch, the folders, the port and the limits are read from
the head of constants.py (conftest.DEFAULTS), the symbol from symbols.json.
"""
import ast
import json
import ntpath
import re
import subprocess

import pytest

from conftest import DEFAULTS, ROOT

BATS = sorted(p.name for p in ROOT.glob('*.bat'))
SYMBOLS = json.loads((ROOT / 'symbols.json').read_text(encoding='utf-8'))
ACTIVE = [s['symbol'] for s in SYMBOLS['symbols'] if s.get('is_active')]
SYMBOL = ACTIVE[0] if ACTIVE else None
# start_xauusd.bat for XAUUSDm, start_btcusd.bat for BTCUSDm: the name the owner knows from the old branches
SYMBOL_LAUNCHER = f"start_{(SYMBOL or '').lower().removesuffix('m')}.bat"
ENTRY_POINTS = ['start_job.bat', 'start_dashboard.bat', 'safety.bat', 'collect_logs.bat']   # started by the owner
HELPERS = ['branch_env.bat', 'find_python.bat']                                            # called by the others
PYTHON_LINE = re.compile(r'"%(PYTHON_EXE|DASH_PY)%" ')              # a line that runs python or pip
PAUSE = 'if not defined ALCADEIAS_NO_PAUSE pause'
# Variables Windows or the owner sets; every other %NAME% must be set by a launcher.
SYSTEM_VARIABLES = {'ERRORLEVEL', 'CD', 'LOCALAPPDATA', 'ALCADEIAS_PYTHON'}
PATH_VARIABLES = ('%PYTHON_EXE%', '%DASH_PY%', '%DASH_ENV%', '%OUT_DIR%', '%ALCADEIAS_PYTHON%', '%LOCALAPPDATA%',
                  '%CD%', '%~dp0')


def raw(name):
    return (ROOT / name).read_bytes()


def lines_of(name):
    """The lines of a launcher, without their line ends. (A byte that is not ASCII becomes '?' here; the byte
    check reports it.)"""
    return raw(name).decode('ascii', 'replace').replace('\r\n', '\n').split('\n')[:-1]


def kind(line):
    """'blank', 'comment', 'label', 'echo' or 'command'."""
    s = line.strip()
    low = s.lower()
    if not s:
        return 'blank'
    if low == 'rem' or low.startswith('rem '):
        return 'comment'
    if s.startswith(':'):
        return 'label'
    if low == 'echo.' or low.startswith('echo '):
        return 'echo'
    return 'command'


def commands(lines):
    """The lines cmd.exe acts on: not blank, not a comment."""
    return [ln for ln in lines if kind(ln) not in ('blank', 'comment')]


def set_names(lines):
    """The variables these lines set: set "NAME=..." or set NAME=..."""
    names = set()
    for ln in lines:
        names.update(m.group(1) for m in re.finditer(r'(?i)\bset\s+"?([A-Za-z_][A-Za-z0-9_]*)=', ln)
                     if kind(ln) == 'command')
    return names


KNOWN_VARIABLES = SYSTEM_VARIABLES | {n for name in BATS for n in set_names(lines_of(name))}


# ───────────────────────── the checks (each returns what is wrong) ─────────────────────────

def bytes_problems(data):
    """Plain ASCII, one kind of line ending, a line end at the end, no tab, no blank at the end of a line."""
    out = []
    if any(b > 126 for b in data):
        out.append('a byte that is not ASCII')
    if any(b < 32 and b not in (10, 13) for b in data):
        out.append('a control character (a tab?)')
    text = data.decode('ascii', 'replace')
    crlf, lf = text.count('\r\n'), text.count('\n')
    if text.count('\r') != crlf:
        out.append('a CR that is not followed by LF')
    if crlf not in (0, lf):
        out.append(f'mixed line endings ({crlf} CR LF, {lf - crlf} LF)')
    if not text.endswith('\n'):
        out.append('no line end after the last line')
    for i, ln in enumerate(text.replace('\r\n', '\n').split('\n'), 1):
        if ln != ln.rstrip():
            out.append(f'line {i} ends with a blank')
        if len(ln) > 1000:
            out.append(f'line {i} is {len(ln)} characters long')
    return out


def bracket_problems(lines):
    """No bracket anywhere: then there is no parenthesised block, and no text that could end one early."""
    return [f'line {i}: a bracket: {ln.strip()}' for i, ln in enumerate(lines, 1) if '(' in ln or ')' in ln]


def label_problems(lines):
    """Every goto has its label exactly once, every label is used, a label is a plain name on its own line."""
    out, labels, targets = [], [], []
    for i, ln in enumerate(lines, 1):
        k = kind(ln)
        if k == 'label':
            if not re.fullmatch(r':[A-Za-z][A-Za-z0-9_]*', ln):
                out.append(f'line {i}: not a plain label: {ln!r}')
            labels.append(ln.strip()[1:].lower())
        elif k == 'echo':
            if re.search(r'(?i)\bgoto\b', ln):
                out.append(f'line {i}: the word goto in a text')
        elif k == 'command':
            if re.search(r'(?i)\bcall\s+:', ln):
                out.append(f'line {i}: call of a label')
            found = re.findall(r'(?i)\bgoto\b(.*)$', ln)
            for rest in found:
                m = re.fullmatch(r'\s+([A-Za-z][A-Za-z0-9_]*)', rest)
                if not m:
                    out.append(f'line {i}: goto without a plain label at the end of the line: {ln.strip()}')
                else:
                    targets.append(m.group(1).lower())
    for name in sorted(set(targets)):
        if labels.count(name) != 1:
            out.append(f'goto {name}: the label is there {labels.count(name)} times')
    for name in sorted(set(labels)):
        if labels.count(name) > 1 and name not in targets:
            out.append(f'the label :{name} is there {labels.count(name)} times')
        if name not in targets:
            out.append(f'the label :{name} is never used')
    short = [name[:8] for name in set(labels)]
    if len(short) != len(set(short)):
        out.append('two labels start with the same 8 characters')
    return out


def errorlevel_problems(lines):
    """`if errorlevel` and %ERRORLEVEL% only on the line right after the program whose exit code they read."""
    out = []
    for i, ln in enumerate(lines):
        s, before = ln.strip(), (lines[i - 1].strip() if i else '')
        if kind(ln) != 'command':
            if '%ERRORLEVEL%' in s.upper() or re.search(r'(?i)\bif\s+(not\s+)?errorlevel\b', s):
                out.append(f'line {i + 1}: an exit code in a text or comment')
            continue
        if re.search(r'(?i)\bif\s+(not\s+)?errorlevel\b', s):
            if not re.match(r'(?i)if (not )?errorlevel 1 goto [a-z_]+$', s):
                out.append(f'line {i + 1}: not the plain form "if [not] errorlevel 1 goto label": {s}')
            if not PYTHON_LINE.match(before):
                out.append(f'line {i + 1}: if errorlevel does not follow a python or pip line')
        if '%ERRORLEVEL%' in s.upper():
            if re.fullmatch(r'set "[A-Z]+_EXIT=%ERRORLEVEL%"', s):
                if not PYTHON_LINE.match(before):
                    out.append(f'line {i + 1}: the exit code is not read on the line right after python')
            elif s == 'exit /b %ERRORLEVEL%':
                if not before.lower().startswith('call '):
                    out.append(f'line {i + 1}: exit /b %ERRORLEVEL% does not follow a call line')
            else:
                out.append(f'line {i + 1}: %ERRORLEVEL% used another way: {s}')
        if re.search(r'(?i)\bset\s+"?errorlevel=', s):
            out.append(f'line {i + 1}: ERRORLEVEL is set as a variable (it would hide the real exit code)')
    return out


_PERCENT = re.compile(r'%%|%~dp0|%~1|%\*|%1|%([A-Za-z_][A-Za-z0-9_]*)%')


def percent_problems(lines, known=None):
    """A percent sign is a variable the launchers know, %~dp0, %~1, %1, %*, or doubled (%%) in a text."""
    known = KNOWN_VARIABLES if known is None else known
    out = []
    for i, ln in enumerate(lines, 1):
        for m in _PERCENT.finditer(ln):
            if m.group(1) and m.group(1).upper() not in known:
                out.append(f'line {i}: %{m.group(1)}% is set by no launcher')
            if m.group(0) in ('%1', '%*', '%~1') and kind(ln) != 'command':
                out.append(f'line {i}: an argument in a text or comment')
        if '%' in _PERCENT.sub('', ln):
            out.append(f'line {i}: a single percent sign (write %% in a text): {ln.strip()}')
    return out


def text_problems(lines):
    """Texts and comments hold nothing cmd.exe acts on; quotes come in pairs; a folder or file from a variable is
    always inside quotes (it may hold a blank, a bracket or an ampersand)."""
    out = []
    for i, ln in enumerate(lines, 1):
        k, s = kind(ln), ln.strip()
        if ln.count('"') % 2:
            out.append(f'line {i}: an odd number of quotes')
        if k == 'comment' and re.search(r'[%&|<>^]', s):
            out.append(f'line {i}: a comment with a character cmd.exe acts on: {s}')
        if k == 'echo':
            body = re.sub(r' > "%DASH_ENV%\\[A-Za-z0-9_.]+\.flag"$', '', s)     # the one text written to a file
            if re.search(r'[&|<>^]', body):
                out.append(f'line {i}: a text with a character cmd.exe acts on: {s}')
            if re.match(r'(?i)echo (on|off)$', s) or '/?' in s:
                out.append(f'line {i}: a text cmd.exe takes for a switch: {s}')
        if k == 'command':
            rest = re.sub(r'( 1>nul 2>nul| > nul)$', '', s)
            if re.search(r'[&|<>^]', rest):
                out.append(f'line {i}: a redirection or a second command: {s}')
        if k in ('echo', 'command'):
            inside = ''.join(part for n, part in enumerate(ln.split('"')) if n % 2)
            for var in PATH_VARIABLES:
                if ln.count(var) != inside.count(var):
                    out.append(f'line {i}: {var} outside quotes')
    return out


def habit_problems(lines):
    """What a launcher must not do at all."""
    out = []
    for i, ln in enumerate(lines, 1):
        k, low = kind(ln), ln.strip().lower()
        if 'timeout' in low:
            out.append(f'line {i}: timeout (it fails without a console; wait with ping -n N 127.0.0.1 > nul)')
        if k != 'command':
            continue
        if re.search(r'\bping\b', low) and not re.fullmatch(r'ping -n \d+ 127\.0\.0\.1 > nul', low):
            out.append(f'line {i}: a wait that is not "ping -n N 127.0.0.1 > nul"')
        if re.search(r'\bpause\b', low) and low != PAUSE.lower():
            out.append(f'line {i}: a pause that ALCADEIAS_NO_PAUSE cannot switch off')
        if re.search(r'\bexit\b', low) and not re.search(r'\bexit /b( \d+| %[a-z_]+%)$', low):
            out.append(f'line {i}: exit without /b and a code (it would close the whole window)')
        if 'enabledelayedexpansion' in low or re.search(r'\bendlocal\b', low) or re.search(r'\bshift\b', low):
            out.append(f'line {i}: delayed expansion, endlocal or shift')
        if re.search(r'--upgrade|ensurepip|\.flag\b', low) and 'dash_' not in low:
            out.append(f'line {i}: an unpinned upgrade or a flag file: {low}')
        if 'pip install' in low and '-r requirements.txt' not in low:
            packages = low.split('pip install', 1)[1].split()
            if not packages or not all(re.fullmatch(r'[a-z0-9_-]+==[0-9.]+', p) for p in packages):
                out.append(f'line {i}: pip install without pinned versions: {low}')
        if re.search(r'\bset\s+"?[a-z_]+=(live|demo)"?$', low) or re.search(r'\bmode\b', low) or 'demo' in low:
            out.append(f'line {i}: a mode variable or a default mode: {low}')
        if re.match(r'(setx|reg|del|rd|rmdir|erase|move|copy|xcopy|robocopy|format|taskkill|start)\b', low):
            out.append(f'line {i}: a command a launcher has no business with: {low}')
    return out


ALL_CHECKS = (bracket_problems, label_problems, errorlevel_problems, percent_problems, text_problems,
              habit_problems)


# ───────────────────────── every launcher ─────────────────────────

def test_the_launchers_of_this_branch_are_exactly_these():
    """One launcher per job, and exactly one named after the symbol: a start_xauusd.bat left in a BTC branch would
    start the BTC bot under gold's name."""
    assert len(ACTIVE) == 1, 'symbols.json must have exactly one active symbol: one bot per branch'
    assert sorted(BATS) == sorted(ENTRY_POINTS + HELPERS + [SYMBOL_LAUNCHER])


@pytest.mark.parametrize('name', BATS)
def test_a_launcher_is_plain_ascii_with_one_kind_of_line_ending(name):
    assert bytes_problems(raw(name)) == []


@pytest.mark.parametrize('name', BATS)
def test_a_launcher_keeps_every_rule(name):
    lines = lines_of(name)
    problems = [f'{check.__name__}: {p}' for check in ALL_CHECKS for p in check(lines)]
    assert problems == []


@pytest.mark.parametrize('name', ENTRY_POINTS)
def test_a_launcher_the_owner_starts_begins_in_its_own_folder_with_its_own_variables(name):
    """setlocal: nothing it sets stays in a window that is used again (for another branch). cd /d "%~dp0": it finds
    app.py and branch_env.bat wherever it was started from (Task Scheduler, a shortcut)."""
    cmds = commands(lines_of(name))
    assert cmds[:3] == ['@echo off', 'setlocal', 'cd /d "%~dp0"']
    assert sum(c.lower().startswith('setlocal') for c in cmds) == 1
    assert sum('%~dp0' in c for c in cmds) == 1            # after the cd every file is named from this folder
    assert cmds[-1].startswith('exit /b ')
    for label in [c for c in cmds if c.startswith(':')]:
        after = cmds[cmds.index(label) + 1:]
        end = next(i for i, c in enumerate(after) if c.startswith(':') or c.startswith('exit /b '))
        assert after[end].startswith('exit /b ') or label in (':deps_ok', ':run_bot', ':env_ready', ':deps_ready'), \
            f'{label} runs into the next label'


@pytest.mark.parametrize('name', HELPERS)
def test_a_helper_leaves_its_variables_to_the_caller(name):
    cmds = commands(lines_of(name))
    assert not any(c.lower().startswith(('setlocal', 'cd ')) for c in cmds)


@pytest.mark.parametrize('name', [n for n in BATS if n not in HELPERS and n != SYMBOL_LAUNCHER])
def test_python_is_found_by_find_python_and_its_absence_stops_the_launcher(name):
    cmds = commands(lines_of(name))
    calls = [i for i, c in enumerate(cmds) if c == 'call find_python.bat']
    assert len(calls) == 1
    i = calls[0]
    assert cmds[i - 1] == 'set "PYTHON_EXE="' and cmds[i + 1] == 'if not defined PYTHON_EXE goto no_python'
    first_use = min(n for n, c in enumerate(cmds) if '%PYTHON_EXE%' in c)
    assert first_use > i + 1
    tail = cmds[cmds.index(':no_python') + 1:][:3]
    assert tail[0].startswith('echo ') and tail[1:] == [PAUSE, 'exit /b 1']


@pytest.mark.parametrize('name', ['start_job.bat', 'start_dashboard.bat'])
def test_the_branch_values_come_from_branch_env_and_a_missing_one_stops_the_launcher(name):
    """Cleared first: in a window used for another branch before, a missing file must not leave that branch's
    values in place. `if errorlevel` after the call would prove nothing (set leaves the exit code alone)."""
    cmds = commands(lines_of(name))
    i = cmds.index('call branch_env.bat')
    assert cmds[i - 4:i + 4] == ['set "BRANCH="', 'set "SYMBOL="', 'set "OUT_DIR="',
                                 'if not exist "branch_env.bat" goto no_env', 'call branch_env.bat',
                                 'if not defined BRANCH goto no_env', 'if not defined SYMBOL goto no_env',
                                 'if not defined OUT_DIR goto no_env']
    for var in ('%BRANCH%', '%SYMBOL%', '%OUT_DIR%'):
        assert all(var not in c for c in cmds[:i + 4])
    tail = cmds[cmds.index(':no_env') + 1:]
    tail = tail[:next(n for n, c in enumerate(tail) if c.startswith('exit /b')) + 1]
    assert tail[-2:] == [PAUSE, 'exit /b 1'] and not any('%BRANCH%' in c or '%SYMBOL%' in c for c in tail)


# ───────────────────────── start_job.bat ─────────────────────────

LOOP = [
    ':run_bot',
    '"%PYTHON_EXE%" -X utf8 -u app.py live --symbol %SYMBOL%',
    'set "BOT_EXIT=%ERRORLEVEL%"',
    'if "%BOT_EXIT%"=="78" goto needs_owner',
    'if "%BOT_EXIT%"=="2" goto needs_owner',
    'if "%BOT_EXIT%"=="0" goto stopped',
    'echo app.py ended with code %BOT_EXIT% - it starts again in 30 seconds. Close this window to stop the bot.',
    'ping -n 31 127.0.0.1 > nul',
    'goto run_bot',
]


def test_the_bot_loop_is_the_one_of_the_spec_line_for_line():
    """The exit code is read on the line right after app.py and compared as text: 78 and 2 need the owner (no
    restart), 0 was the owner's stop (no restart), anything else (1, a crash) starts the bot again after 30 s."""
    lines = lines_of('start_job.bat')
    i = lines.index(':run_bot')
    assert lines[i:i + len(LOOP)] == LOOP
    assert sum('app.py' in ln for ln in commands(lines) if kind(ln) == 'command') == 1
    assert sum(ln.strip().lower() == 'goto run_bot' for ln in lines) == 1


def test_only_the_word_live_starts_the_bot():
    """No default mode: a double-click (no word) and any other word end with what to type, a pause and code 1,
    before Python is looked for or anything is installed."""
    cmds = commands(lines_of('start_job.bat'))
    check = 'if /i not "%~1"=="live" goto wrong_mode'
    assert cmds.count(check) == 1
    first_python = min(i for i, c in enumerate(cmds) if PYTHON_LINE.match(c) or c == 'call find_python.bat')
    assert cmds.index('call branch_env.bat') < cmds.index(check) < first_python
    assert sum('%~1' in c for c in cmds) == 1 and not any('%1' in c or '%*' in c for c in cmds)
    tail = cmds[cmds.index(':wrong_mode') + 1:]
    tail = tail[:next(n for n, c in enumerate(tail) if c.startswith('exit /b')) + 1]
    assert 'echo     start_job.bat live' in tail and tail[-2:] == [PAUSE, 'exit /b 1']
    assert any('no demo mode' in c for c in tail)


def test_needs_the_owner_stops_for_good_and_says_so():
    cmds = commands(lines_of('start_job.bat'))
    i = cmds.index(':needs_owner')
    said = ('echo %BRANCH% has stopped and will NOT start again by itself. Read the lines above, fix what they say, '
            'then start this file again.')
    block = cmds[i + 1:i + 5]
    assert said in block and block[-2:] == [PAUSE, 'exit /b %BOT_EXIT%']
    j = cmds.index(':stopped')
    stop = cmds[j + 1:]
    stop = stop[:next(n for n, c in enumerate(stop) if c.startswith('exit /b')) + 1]
    assert stop[-2:] == [PAUSE, 'exit /b 0'] and any('NOT closed' in c for c in stop)


def test_the_packages_are_looked_for_at_every_start_and_installed_only_when_missing():
    """No flag file (it said 'installed' also after a failed pip) and no unpinned upgrade of the shared Python."""
    cmds = commands(lines_of('start_job.bat'))
    probe = '"%PYTHON_EXE%" -c "import MetaTrader5, pandas, numpy"'
    i = cmds.index(probe + ' 1>nul 2>nul')
    assert cmds[i + 1] == 'if not errorlevel 1 goto deps_ok'
    assert cmds[i + 2].startswith('echo ')
    assert cmds[i + 3:i + 8] == ['"%PYTHON_EXE%" -m pip install -r requirements.txt',
                                 'if errorlevel 1 goto deps_failed', probe, 'if errorlevel 1 goto deps_failed',
                                 ':deps_ok']
    assert i < cmds.index(':run_bot')
    assert sum('-m pip' in c for c in cmds if kind(c) == 'command') == 1
    # what the bot imports is what the probe imports
    for package in ('MetaTrader5', 'pandas'):
        assert any(ln.lower().startswith(package.lower() + '==')
                   for ln in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines())


def test_the_real_money_warning_and_its_five_seconds_come_before_the_bot():
    cmds = commands(lines_of('start_job.bat'))
    warn = next(i for i, c in enumerate(cmds) if 'TRADING WITH REAL MONEY' in c)
    wait = cmds.index('ping -n 6 127.0.0.1 > nul')
    assert cmds.index(':deps_ok') < warn < wait < cmds.index(':run_bot')
    assert [c for c in cmds if c.startswith('ping ')] == ['ping -n 6 127.0.0.1 > nul', 'ping -n 31 127.0.0.1 > nul']


def test_the_utf8_lines_of_the_old_launchers_are_kept_before_the_first_python_call():
    cmds = commands(lines_of('start_job.bat'))
    i = cmds.index('chcp 65001 > nul')
    assert cmds[i + 1:i + 3] == ['set PYTHONIOENCODING=utf-8', 'set PYTHONUTF8=1']
    assert i < min(n for n, c in enumerate(cmds) if PYTHON_LINE.match(c))


def test_the_symbols_own_launcher_only_forwards_to_start_job():
    """One launcher to keep right: start_<symbol>.bat is the three lines that hand over to start_job.bat."""
    assert lines_of(SYMBOL_LAUNCHER) == ['@echo off', 'call "%~dp0start_job.bat" %*', 'exit /b %ERRORLEVEL%']


# ───────────────────────── branch_env.bat, find_python.bat ─────────────────────────

def branch_env():
    lines = lines_of('branch_env.bat')
    assert len(lines) == 3
    values = {}
    for ln, name in zip(lines, ('BRANCH', 'SYMBOL', 'OUT_DIR')):
        m = re.fullmatch(r'set "' + name + r'=([^"%&|<>^()!]+)"', ln)
        assert m, f'not a plain set "{name}=..." line: {ln!r}'
        values[name] = m.group(1)
    return values


def test_branch_env_agrees_with_constants_and_symbols_json():
    """branch_env.bat repeats three values the bot has in constants.py and symbols.json. If they differ, the
    launcher starts another symbol than the bot is set up for, or the dashboard's environment lands in another
    bot's folder."""
    values = branch_env()
    assert values == {'BRANCH': DEFAULTS['BRANCH'], 'SYMBOL': SYMBOL, 'OUT_DIR': DEFAULTS['OUTPUT_DIR']}
    assert re.fullmatch(r'[A-Za-z0-9_]+', values['BRANCH']) and re.fullmatch(r'[A-Za-z0-9_.-]+', values['SYMBOL'])
    assert values['OUT_DIR'] == values['OUT_DIR'].strip() and not values['OUT_DIR'].endswith('\\')
    assert ntpath.isabs(values['OUT_DIR']) and ntpath.basename(values['OUT_DIR']) == values['BRANCH']
    # the per-symbol launcher's name follows the same symbol
    assert (ROOT / SYMBOL_LAUNCHER).is_file()


def test_find_python_tries_the_four_places_of_the_spec_in_their_order():
    cmds = commands(lines_of('find_python.bat'))
    assert cmds[:2] == ['@echo off', 'set "PYTHON_EXE="']
    places = [
        ('if defined ALCADEIAS_PYTHON ', '%ALCADEIAS_PYTHON%'),
        ('if not defined PYTHON_EXE ', r'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe'),
        ('if not defined PYTHON_EXE ', r'C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe'),
        ('if not defined PYTHON_EXE if defined LOCALAPPDATA ',
         r'%LOCALAPPDATA%\Programs\Python\Python311\python.exe'),
    ]
    assert cmds[2:6] == [f'{start}if exist "{path}" set "PYTHON_EXE={path}"' for start, path in places]
    assert cmds[6] == 'if defined PYTHON_EXE goto found'
    assert [c for c in cmds if 'PYTHON_EXE=' in c] == cmds[1:6]         # set nowhere else
    assert cmds[-2:] == [':found', 'exit /b 0']
    told = [c for c in cmds[7:-2]]
    assert told and all(kind(c) == 'echo' for c in told) and any('ALCADEIAS_PYTHON' in c for c in told)


# ───────────────────────── start_dashboard.bat, safety.bat, collect_logs.bat ─────────────────────────

def test_the_dashboard_gets_its_own_environment_in_the_bots_folder_with_the_pinned_versions():
    cmds = commands(lines_of('start_dashboard.bat'))
    pins = dict(ln.strip().split('==', 1) for ln in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
                if '==' in ln)
    flag = f'"%DASH_ENV%\\dash_{pins["dash"]}_plotly_{pins["plotly"]}.flag"'
    i = cmds.index(r'set "DASH_ENV=%OUT_DIR%\dash_env"')
    assert cmds[i + 1:i + 3] == [r'set "DASH_PY=%DASH_ENV%\Scripts\python.exe"', 'if exist "%DASH_PY%" goto env_ready']
    j = cmds.index('"%PYTHON_EXE%" -m venv "%DASH_ENV%"')
    assert cmds[j + 1:j + 4] == ['if errorlevel 1 goto venv_failed', ':env_ready', f'if exist {flag} goto deps_ready']
    k = cmds.index(f'"%DASH_PY%" -m pip install dash=={pins["dash"]} plotly=={pins["plotly"]}')
    assert cmds[k + 1:k + 4] == ['if errorlevel 1 goto pip_failed',
                                 f'echo Dashboard dependencies installed > {flag}', ':deps_ready']
    run = cmds.index('"%DASH_PY%" -u dashboard.py')
    assert i < j < k < run and cmds[run + 1] == 'set "DASH_EXIT=%ERRORLEVEL%"'
    assert cmds[-1] == 'exit /b 1' and 'exit /b %DASH_EXIT%' in cmds
    # the shared Python never gets dash or plotly: only the private environment's python installs
    assert [c for c in cmds if '-m pip' in c and kind(c) == 'command'] == [cmds[k]]
    # an argument is accepted and ignored: the dashboard has no mode
    assert not any(re.search(r'%~?1|%\*', c) for c in cmds)


def test_safety_bat_hands_one_word_to_safety_py():
    cmds = commands(lines_of('safety.bat'))
    assert cmds[3] == 'if "%~1"=="" goto usage'
    run = cmds.index('"%PYTHON_EXE%" -B safety.py %1')
    assert cmds[run + 1:run + 4] == ['set "SAFETY_EXIT=%ERRORLEVEL%"', PAUSE, 'exit /b %SAFETY_EXIT%']
    usage = cmds[cmds.index(':usage') + 1:]
    usage = usage[:next(n for n, c in enumerate(usage) if c.startswith('exit /b')) + 1]
    for word in ('status', 'unblock', 'on', 'off', 'new-account'):
        assert any(re.match(rf'echo\s+safety\.bat {word}\s', c) for c in usage), word
    assert usage[-2:] == [PAUSE, 'exit /b 1']
    assert b'branch_env' not in raw('safety.bat')                    # its folder comes from constants.py alone


def test_collect_logs_bat_runs_collect_logs_py():
    cmds = commands(lines_of('collect_logs.bat'))
    run = cmds.index('"%PYTHON_EXE%" -B collect_logs.py %*')
    assert cmds[run + 1:run + 4] == ['set "COLLECT_EXIT=%ERRORLEVEL%"', PAUSE, 'exit /b %COLLECT_EXIT%']
    assert (ROOT / 'collect_logs.py').is_file()


# ───────────────────────── git ─────────────────────────

def test_gitattributes_makes_every_bat_crlf():
    """Without it a server whose git does not convert line endings gets LF-only .bat files, in which cmd.exe can
    miss a label: the needs-owner stop, or the restart loop."""
    lines = [ln.strip() for ln in (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()]
    rules = [ln for ln in lines if ln and not ln.startswith('#')]
    assert '*.bat text eol=crlf' in rules
    assert [r for r in rules if 'bat' in r.lower() or r.startswith('* ')] == ['*.bat text eol=crlf']
    # and git itself reads it that way, where git is there (a copy of the files without git: the line above stands)
    try:
        done = subprocess.run(['git', '-C', str(ROOT), 'check-attr', 'text', 'eol', '--'] + BATS,
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return
    if done.returncode != 0:
        return
    said = done.stdout.splitlines()
    for name in BATS:
        assert f'{name}: text: set' in said and f'{name}: eol: crlf' in said, (name, said)


def test_gitignore_keeps_what_a_running_bot_leaves_out_of_git():
    lines = [ln.strip() for ln in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()]
    for rule in ('__pycache__/', '*.pyc', 'dash_env/'):
        assert rule in lines
    rules = [ln for ln in lines if ln and not ln.startswith('#')]
    # nothing the bot needs may be ignored by accident
    for name in ('mt5_credentials.json', 'symbols.json', 'constants.py', '*.json', '*.bat', '*.py', '*'):
        assert name not in rules


# ───────────────────────── the checks see what they are for ─────────────────────────

GOOD = ['@echo off', 'REM a comment', 'setlocal', 'cd /d "%~dp0"', 'set "BOT_EXIT="', ':again',
        '"%PYTHON_EXE%" -u app.py live', 'if errorlevel 1 goto failed', 'echo 100%% done in "%OUT_DIR%"',
        'goto again', ':failed', PAUSE, 'exit /b 1']


def test_the_checks_pass_a_launcher_that_keeps_the_rules():
    assert [p for check in ALL_CHECKS for p in check(GOOD)] == []
    assert bytes_problems('\r\n'.join(GOOD).encode() + b'\r\n') == []
    assert bytes_problems('\n'.join(GOOD).encode() + b'\n') == []


@pytest.mark.parametrize('check, bad', [
    (bracket_problems, 'if exist x ('),
    (bracket_problems, 'echo This is a demo ^(x^)'),
    (bracket_problems, 'echo Python is in C:\\Program Files (x86)'),
    (label_problems, 'goto nowhere'),
    (label_problems, ':unused'),
    (label_problems, ':again'),
    (label_problems, 'goto :eof'),
    (label_problems, 'call :again'),
    (label_problems, 'if errorlevel 1 goto again & echo x'),
    (label_problems, ':again_but_longer'),
    (label_problems, 'echo type goto to leave'),
    (errorlevel_problems, 'if errorlevel 1 goto failed'),
    (errorlevel_problems, 'if %ERRORLEVEL% NEQ 0 goto failed'),
    (errorlevel_problems, 'set "BOT_EXIT=%ERRORLEVEL%"'),
    (errorlevel_problems, 'exit /b %ERRORLEVEL%'),
    (errorlevel_problems, 'set ERRORLEVEL=0'),
    (errorlevel_problems, 'echo the code was %ERRORLEVEL%'),
    (percent_problems, 'echo 50% of the balance'),
    (percent_problems, 'echo the branch %BRANHC%'),
    (percent_problems, 'echo %BRANCH'),
    (percent_problems, 'echo started with %1'),
    (percent_problems, 'REM usage: %~1'),
    (text_problems, 'echo gold & BTC'),
    (text_problems, 'echo see the log > x.txt'),
    (text_problems, 'echo Python: %PYTHON_EXE%'),
    (text_problems, 'echo an odd "quote'),
    (text_problems, 'REM 50% of the time'),
    (text_problems, 'REM a | b'),
    (text_problems, '%PYTHON_EXE% -u app.py live'),
    (text_problems, '"%PYTHON_EXE%" -u app.py live >> log.txt'),
    (text_problems, '"%PYTHON_EXE%" -u app.py live & echo done'),
    (text_problems, 'echo off'),
    (habit_problems, 'timeout /t 5 /nobreak > nul'),
    (habit_problems, 'ping -n 6 localhost'),
    (habit_problems, 'pause'),
    (habit_problems, 'exit'),
    (habit_problems, 'exit /b'),
    (habit_problems, 'setlocal enabledelayedexpansion'),
    (habit_problems, 'endlocal'),
    (habit_problems, '"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel'),
    (habit_problems, '"%PYTHON_EXE%" -m pip install dash plotly'),
    (habit_problems, '"%PYTHON_EXE%" -m ensurepip'),
    (habit_problems, 'if not exist ".\\deps_installed.flag" goto install'),
    (habit_problems, 'set "MODE=live"'),
    (habit_problems, 'if "%MODE%"=="" set "MODE=demo"'),
    (habit_problems, 'del /q "%OUT_DIR%\\logs"'),
])
def test_each_check_catches_a_line_that_breaks_its_rule(check, bad):
    known = KNOWN_VARIABLES | {'OUT_DIR', 'PYTHON_EXE', 'BOT_EXIT', 'BRANCH', 'MODE'}
    lines = GOOD[:5] + [bad] + GOOD[5:]
    args = (lines, known) if check is percent_problems else (lines,)
    assert check(*args) != [], bad
    assert [p for c in ALL_CHECKS for p in (c(GOOD, known) if c is percent_problems else c(GOOD))] == []


def test_two_labels_that_start_with_the_same_8_characters_are_caught():
    """The old command.com read only the first 8 characters of a label. cmd.exe reads all of it; the launchers do
    not depend on that."""
    twins = GOOD + ['goto needs_owner_a', ':needs_owner_a', 'goto needs_owner_b', ':needs_owner_b', 'exit /b 1']
    assert label_problems(twins) == ['two labels start with the same 8 characters']
    labels = [ln[1:] for name in BATS for ln in lines_of(name) if kind(ln) == 'label']
    assert labels and all(len(label) <= 11 for label in labels)


@pytest.mark.parametrize('bad', [b'echo caf\xc3\xa9\r\n', b'echo x\n\techo y\n', b'echo x\r\necho y\n',
                                 b'echo x\recho y\r', b'echo x', b'echo x \r\n', b'\xef\xbb\xbf@echo off\r\n',
                                 b'REM \x97 a dash from Word\r\n'])
def test_the_byte_check_catches_what_cmd_cannot_read(bad):
    assert bytes_problems(bad) != []


# ───────────────────────── the launchers, walked through ─────────────────────────

HERE_ON_THE_SERVER = 'C:\\Bots\\this_branch\\'                 # where the clone is, in the walk
ADMINISTRATOR_PYTHON = r'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe'
ADMIN_PYTHON = r'C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe'


class Walk:
    """
    A paper cmd.exe for exactly the kinds of line the launchers may hold: it follows a launcher line by line,
    with a set of files that exist, the variables of the window, and a stand-in that answers every program line
    (python, pip) with an exit code. Any other kind of line stops the walk with an error, so the launchers cannot
    grow a construct the walk does not follow.

    What it keeps as cmd.exe does: variables are expanded when a line is read (%NAME%, %~1, %1, %*, %~dp0, %%);
    an undefined variable is empty; set "NAME=" removes it; names and labels ignore case; `if exist ""` is false;
    a called launcher shares the caller's variables unless it says setlocal, which puts them back when it ends;
    ERRORLEVEL is the exit code of the last program or called launcher, and set / echo / if / goto leave it alone.
    """

    def __init__(self, files=(), env=None, programs=None, sources=None):
        self.files = {f.lower() for f in list(BATS) + list(files)}
        self.env = {k.upper(): v for k, v in (env or {}).items()}
        self.programs = programs or (lambda line: 0)
        self.sources = dict(sources or {})          # a launcher with other lines than the real file's
        self.said, self.ran, self.waits, self.titles, self.written = [], [], [], [], []
        self.pauses = 0
        self.errorlevel = 0
        self.steps = 0

    def exists(self, path):
        return bool(path) and path.lower() in self.files

    def expand(self, text, args):
        def value(m):
            token = m.group(0)
            if token == '%%':
                return '%'
            if token == '%~dp0':
                return HERE_ON_THE_SERVER
            if token == '%~1':
                return args[0].strip('"') if args else ''
            if token == '%1':
                return args[0] if args else ''
            if token == '%*':
                return ' '.join(args)
            name = m.group(1).upper()
            if name in self.env:
                return self.env[name]
            return {'ERRORLEVEL': str(self.errorlevel), 'CD': HERE_ON_THE_SERVER.rstrip('\\')}.get(name, '')
        return _PERCENT.sub(value, text)

    def run(self, name, args=()):
        """Follow one launcher to its end; the exit code it leaves."""
        assert self.exists(name), f'{name} is not there'
        lines = self.sources.get(name) or lines_of(name)
        labels = {ln.strip()[1:].lower(): i for i, ln in enumerate(lines) if kind(ln) == 'label'}
        before = None                                # the variables as they were at setlocal
        i = 0
        try:
            while i < len(lines):
                self.steps += 1
                assert self.steps < 5000, 'the launcher does not end'
                line, i = lines[i], i + 1
                if kind(line) in ('blank', 'comment', 'label'):
                    continue
                text = self.expand(line.strip(), list(args))
                if text.lower() == 'setlocal':
                    before = dict(self.env)
                    continue
                todo = self.do(text)
                if todo is None:
                    continue
                if todo[0] == 'goto':
                    i = labels[todo[1].lower()] + 1
                else:
                    self.errorlevel = todo[1]
                    return todo[1]
            return self.errorlevel
        finally:
            if before is not None:
                self.env = before

    def do(self, text):
        """One line, already expanded: None, ('goto', label) or ('exit', code)."""
        low = text.lower()
        if low in ('@echo off',) or low == 'cd /d "' + HERE_ON_THE_SERVER.lower() + '"' or low == 'chcp 65001 > nul':
            return None
        if low == 'echo.':
            self.said.append('')
            return None
        if low.startswith('echo '):
            m = re.fullmatch(r'echo (.*) > "([^"]+)"', text)
            if m:
                self.written.append(m.group(2))
                self.files.add(m.group(2).lower())
            else:
                self.said.append(text[5:])
            return None
        if low.startswith('title '):
            self.titles.append(text[6:])
            return None
        m = re.fullmatch(r'ping -n (\d+) 127\.0\.0\.1 > nul', low)
        if m:
            self.waits.append(int(m.group(1)) - 1)
            return None
        m = re.fullmatch(r'set "([A-Za-z_][A-Za-z0-9_]*)=(.*)"', text) or \
            re.fullmatch(r'set ([A-Za-z_][A-Za-z0-9_]*)=(.*)', text)
        if m:
            if m.group(2) == '':
                self.env.pop(m.group(1).upper(), None)
            else:
                self.env[m.group(1).upper()] = m.group(2)
            return None
        for pattern, test in (
                (r'if (/i )?(not )?"([^"]*)"=="([^"]*)" (.+)',
                 lambda g: (g[2].lower() == g[3].lower()) if g[0] else (g[2] == g[3])),
                (r'if ()(not )?defined ([A-Za-z_][A-Za-z0-9_]*)() (.+)', lambda g: g[2].upper() in self.env),
                (r'if ()(not )?exist "([^"]*)"() (.+)', lambda g: self.exists(g[2])),
                (r'if ()(not )?errorlevel (\d+)() (.+)', lambda g: self.errorlevel >= int(g[2]))):
            m = re.fullmatch(pattern, text, flags=re.I)
            if m:
                g = m.groups()
                return self.do(g[4]) if test(g) != bool(g[1]) else None
        m = re.fullmatch(r'goto ([A-Za-z][A-Za-z0-9_]*)', text, flags=re.I)
        if m:
            return 'goto', m.group(1)
        m = re.fullmatch(r'exit /b (-?\d+)', text, flags=re.I)
        if m:
            return 'exit', int(m.group(1))
        if low == 'pause':
            self.pauses += 1
            return None
        m = re.fullmatch(r'call (?:"' + re.escape(HERE_ON_THE_SERVER) + r'([a-z_]+\.bat)"|([a-z_]+\.bat))(?: (.*))?',
                         text, flags=re.I)
        if m:
            self.errorlevel = self.run(m.group(1) or m.group(2), (m.group(3) or '').split())
            return None
        if text.startswith('"'):
            line = re.sub(r' 1>nul 2>nul$', '', text).rstrip()      # (%* without a word leaves a blank at the end)
            self.ran.append(line)
            self.errorlevel = int(self.programs(line))
            return None
        raise AssertionError(f'a line of a kind the walk does not know: {text}')


def bot_walk(app_codes=(), probe=(0,), pip=0, args=('live',), launcher='start_job.bat', python=ADMINISTRATOR_PYTHON,
             **kw):
    """Walk the bot's launcher: `app_codes` are the exit codes app.py gives, start after start (then 0: the owner
    stopped it); `probe` the exit codes of the package check; `pip` the exit code of the install."""
    app, probes = list(app_codes), list(probe)

    def programs(line):
        if ' app.py ' in line:
            return app.pop(0) if app else 0
        if ' -c "import ' in line:
            return probes.pop(0) if probes else 0
        if ' -m pip install ' in line:
            return pip
        raise AssertionError(f'a program line the test does not expect: {line}')

    walk = Walk(files=[python] if python else [], programs=programs, **kw)
    walk.code = walk.run(launcher, list(args))
    walk.starts = [line for line in walk.ran if ' app.py ' in line]
    return walk


APP_LINE = f'"{ADMINISTRATOR_PYTHON}" -X utf8 -u app.py live --symbol {SYMBOL}'


def test_walk_the_bot_starts_only_with_the_word_live():
    for args in ((), ('demo',), ('liv',), ('"demo"',), ('--symbol',)):
        walk = bot_walk(args=args)
        assert walk.code == 1 and walk.ran == [] and walk.pauses == 1, args
        assert '    start_job.bat live' in walk.said and 'Nothing was started.' in walk.said
    for args in (('live',), ('LIVE',), ('Live', 'and', 'more'), ('"live"',)):
        walk = bot_walk(args=args)
        assert walk.starts == [APP_LINE], args         # always the plain word live, whatever was typed


def test_walk_a_start_that_needs_the_owner_is_not_repeated():
    """78 (and 2: app.py could not even be started): once, then the window says so and waits."""
    for code in (78, 2):
        walk = bot_walk(app_codes=[code, 1, 1])
        assert walk.starts == [APP_LINE] and walk.code == code and walk.pauses == 1
        assert walk.waits == [5]                         # the real-money warning's 5 s, and no restart wait
        assert any('has stopped and will NOT start again by itself' in line for line in walk.said)
        assert DEFAULTS['BRANCH'] in walk.said[-1]


def test_walk_the_bot_is_started_again_30_s_after_every_other_end():
    """1 (it may heal by itself), a crash (a negative code), 3 (what Windows gives for abort()), 9009 (python.exe
    gone): each time 30 s, then again -- for as long as it takes. Only then 78 ends it."""
    codes = [1, -1073741819, 3, 9009, 120, 1, 78]
    walk = bot_walk(app_codes=codes)
    assert walk.starts == [APP_LINE] * len(codes)
    assert walk.waits == [5] + [30] * (len(codes) - 1)
    assert walk.code == 78 and walk.pauses == 1
    for code in codes[:-1]:
        assert (f'app.py ended with code {code} - it starts again in 30 seconds. Close this window to stop the '
                f'bot.') in walk.said


def test_walk_a_stop_by_the_owner_is_not_followed_by_a_restart():
    walk = bot_walk(app_codes=[1, 0, 1, 1])
    assert len(walk.starts) == 2 and walk.code == 0 and walk.waits == [5, 30] and walk.pauses == 1
    assert any('was stopped by you' in line for line in walk.said)
    assert any('open trades are NOT closed' in line for line in walk.said)


def test_walk_the_packages_are_installed_only_when_one_is_missing():
    probe = f'"{ADMINISTRATOR_PYTHON}" -c "import MetaTrader5, pandas, numpy"'
    pip = f'"{ADMINISTRATOR_PYTHON}" -m pip install -r requirements.txt'
    there = bot_walk(app_codes=[78])
    assert there.ran == [probe, APP_LINE]                              # nothing is installed
    missing = bot_walk(app_codes=[78], probe=[1, 0])
    assert missing.ran == [probe, pip, probe, APP_LINE]
    no_internet = bot_walk(app_codes=[78], probe=[1, 0], pip=1)
    assert no_internet.ran == [probe, pip] and no_internet.code == 1 and no_internet.pauses == 1
    still_missing = bot_walk(app_codes=[78], probe=[1, 1], pip=0)
    assert still_missing.ran == [probe, pip, probe] and still_missing.code == 1 and still_missing.starts == []
    for walk in (no_internet, still_missing):
        assert 'Nothing was started.' in walk.said and walk.waits == []
        assert f'    "{ADMINISTRATOR_PYTHON}" -m pip install -r requirements.txt' in walk.said


def test_walk_without_branch_env_nothing_starts_also_in_a_window_another_branch_used():
    """The three values are cleared before branch_env.bat is called: when the file is missing, or sets only some of
    them, the launcher must not go on with what another branch left in the window."""
    left = {'BRANCH': 'another_branch', 'SYMBOL': 'OTHERm', 'OUT_DIR': 'C:\\Alcadeias\\another_branch'}
    for launcher in ('start_job.bat', 'start_dashboard.bat'):
        gone = Walk(files=[ADMINISTRATOR_PYTHON], env=left)
        gone.files.discard('branch_env.bat')
        assert gone.run(launcher, ['live']) == 1 and gone.ran == [] and gone.pauses == 1, launcher
        assert any('branch_env.bat is missing or not complete' in line for line in gone.said)
        for missing in range(3):
            lines = [ln for n, ln in enumerate(lines_of('branch_env.bat')) if n != missing]
            part = Walk(files=[ADMINISTRATOR_PYTHON], env=left, sources={'branch_env.bat': lines})
            assert part.run(launcher, ['live']) == 1 and part.ran == [] and part.titles == [], (launcher, missing)
        assert gone.env == left                      # setlocal: the window's own variables are as they were


def test_walk_python_is_looked_for_in_the_four_places_in_their_order():
    own = r'D:\Tools\Python311\python.exe'
    user = r'C:\Users\trader\AppData\Local'
    user_python = user + r'\Programs\Python\Python311\python.exe'

    def found(files, **env):
        walk = Walk(files=files, env=env)
        walk.run('find_python.bat')
        return walk.env.get('PYTHON_EXE'), walk.said

    everything = [own, ADMINISTRATOR_PYTHON, ADMIN_PYTHON, user_python]
    assert found(everything, ALCADEIAS_PYTHON=own, LOCALAPPDATA=user)[0] == own
    assert found(everything, LOCALAPPDATA=user)[0] == ADMINISTRATOR_PYTHON
    assert found(everything[1:], ALCADEIAS_PYTHON=own, LOCALAPPDATA=user)[0] == ADMINISTRATOR_PYTHON
    assert found([ADMIN_PYTHON, user_python], LOCALAPPDATA=user)[0] == ADMIN_PYTHON
    assert found([user_python], LOCALAPPDATA=user)[0] == user_python
    assert found([user_python])[0] is None                              # (no LOCALAPPDATA: that place is not tried)
    assert found(everything, LOCALAPPDATA=user)[1] == []                # found: it says nothing
    nothing, said = found([], ALCADEIAS_PYTHON=own, LOCALAPPDATA=user, PYTHON_EXE='left by another window')
    assert nothing is None and any('Python 3.11 was not found' in line for line in said)
    assert any('ALCADEIAS_PYTHON' in line for line in said)


def test_walk_without_python_every_launcher_stops_and_says_where_it_looked():
    for launcher, args in (('start_job.bat', ['live']), ('start_dashboard.bat', []), ('safety.bat', ['status']),
                           ('collect_logs.bat', []), (SYMBOL_LAUNCHER, ['live'])):
        walk = Walk()
        assert walk.run(launcher, args) == 1 and walk.ran == [] and walk.pauses == 1, launcher
        assert any('Python 3.11 was not found' in line for line in walk.said), launcher
        assert walk.waits == []


def test_walk_no_pause_when_the_owner_switched_them_off():
    """Under Jenkins or Task Scheduler nobody presses a key: ALCADEIAS_NO_PAUSE ends every launcher with its code."""
    quiet = {'ALCADEIAS_NO_PAUSE': '1'}
    assert bot_walk(app_codes=[78], env=quiet).pauses == 0
    assert bot_walk(app_codes=[0], env=quiet).pauses == 0
    assert bot_walk(args=(), env=quiet).pauses == 0
    assert bot_walk(app_codes=[78], probe=[1, 1], env=quiet).pauses == 0
    for launcher, args in (('start_dashboard.bat', []), ('safety.bat', []), ('safety.bat', ['status']),
                           ('collect_logs.bat', [])):
        for files in ([], [ADMINISTRATOR_PYTHON]):
            walk = Walk(files=files, env=quiet, programs=lambda line: 1)
            walk.run(launcher, args)
            assert walk.pauses == 0, (launcher, files)


def test_walk_the_symbols_own_launcher_does_what_start_job_does():
    for codes, args in (([1, 78], ('live',)), ([0], ('live',)), ([], ())):
        a = bot_walk(app_codes=codes, args=args)
        b = bot_walk(app_codes=codes, args=args, launcher=SYMBOL_LAUNCHER)
        assert (a.code, a.ran, a.waits, a.said, a.pauses) == (b.code, b.ran, b.waits, b.said, b.pauses)
    walk = bot_walk(app_codes=[78], launcher=SYMBOL_LAUNCHER, env={'SYMBOL': 'left by another window'})
    assert walk.code == 78 and walk.env == {'SYMBOL': 'left by another window'}      # setlocal in start_job.bat


def test_walk_the_window_is_named_after_the_branch():
    walk = bot_walk(app_codes=[78])
    assert len(walk.titles) == 1 and DEFAULTS['BRANCH'] in walk.titles[0] and SYMBOL in walk.titles[0]
    assert 'REAL MONEY' in walk.titles[0]
    assert any('TRADING WITH REAL MONEY' in line for line in walk.said)


def dashboard_walk(files=(), venv=0, pip=0, dashboard=0, args=(), env=None):
    out = DEFAULTS['OUTPUT_DIR']
    env_python = out + r'\dash_env\Scripts\python.exe'

    def programs(line):
        if ' -m venv ' in line:
            if venv == 0:
                walk.files.add(env_python.lower())
            return venv
        if ' -m pip install ' in line:
            return pip
        if line.endswith(' -u dashboard.py'):
            return dashboard
        raise AssertionError(f'a program line the test does not expect: {line}')

    walk = Walk(files=[ADMINISTRATOR_PYTHON] + list(files), programs=programs, env=env)
    walk.code = walk.run('start_dashboard.bat', list(args))
    walk.env_python = env_python
    return walk


def test_walk_the_dashboard_builds_its_environment_once_and_then_only_starts():
    out = DEFAULTS['OUTPUT_DIR']
    pins = dict(ln.strip().split('==', 1) for ln in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
                if '==' in ln)
    flag = out + rf'\dash_env\dash_{pins["dash"]}_plotly_{pins["plotly"]}.flag'
    first = dashboard_walk()
    py = first.env_python
    assert first.ran == [f'"{ADMINISTRATOR_PYTHON}" -m venv "{out}\\dash_env"',
                         f'"{py}" -m pip install dash=={pins["dash"]} plotly=={pins["plotly"]}',
                         f'"{py}" -u dashboard.py']
    assert first.written == [flag]
    again = dashboard_walk(files=[py, flag], args=['live'])               # (a word after the name changes nothing)
    assert again.ran == [f'"{py}" -u dashboard.py'] and again.written == []
    half = dashboard_walk(files=[py])                                     # the environment is there, the packages not
    assert half.ran == [f'"{py}" -m pip install dash=={pins["dash"]} plotly=={pins["plotly"]}', f'"{py}" -u dashboard.py']
    # the shared Python never gets a package: every pip line is the environment's own python
    assert all(line.startswith(f'"{py}" ') for walk in (first, half) for line in walk.ran if ' pip ' in line)
    assert DEFAULTS['BRANCH'] in first.titles[0]


def test_walk_the_dashboard_stops_when_its_environment_cannot_be_made():
    no_venv = dashboard_walk(venv=1)
    assert no_venv.code == 1 and len(no_venv.ran) == 1 and no_venv.written == [] and no_venv.pauses == 1
    no_pip = dashboard_walk(pip=1)
    assert no_pip.code == 1 and len(no_pip.ran) == 2 and no_pip.written == [] and no_pip.pauses == 1
    for walk in (no_venv, no_pip):
        assert 'The dashboard was not started.' in walk.said
        assert not any(line.endswith(' -u dashboard.py') for line in walk.ran)
    ended = dashboard_walk(dashboard=1)
    assert ended.code == 1 and any('DASHBOARD STOPPED' in line for line in ended.said) and ended.pauses == 1


def test_walk_safety_bat_hands_one_word_to_safety_py_and_gives_back_its_code():
    for word, code in (('status', 0), ('unblock', 1), ('off', 0), ('new-account', 2)):
        walk = Walk(files=[ADMINISTRATOR_PYTHON], programs=lambda line: code)
        assert walk.run('safety.bat', [word, 'and', 'more']) == code
        assert walk.ran == [f'"{ADMINISTRATOR_PYTHON}" -B safety.py {word}'] and walk.pauses == 1
    nothing = Walk(files=[ADMINISTRATOR_PYTHON])
    assert nothing.run('safety.bat', []) == 1 and nothing.ran == [] and nothing.pauses == 1
    assert any('safety.bat unblock' in line for line in nothing.said)


def test_walk_collect_logs_bat_gives_back_the_code_of_collect_logs_py():
    for args, code in (([], 0), (['--out', 'D:\\exports'], 1)):
        walk = Walk(files=[ADMINISTRATOR_PYTHON], programs=lambda line: code)
        assert walk.run('collect_logs.bat', args) == code
        assert walk.ran == [' '.join([f'"{ADMINISTRATOR_PYTHON}" -B collect_logs.py'] + args)]
        assert walk.pauses == 1


def test_the_walk_stops_at_a_line_of_a_kind_it_does_not_know():
    for line in ('for %%f in (*.log) do echo %%f', 'start "" python app.py', 'if exist x (', 'timeout /t 5',
                 'goto :eof', 'exit', 'call :label', 'set /a N=1+1', 'choice /c YN'):
        walk = Walk(sources={'safety.bat': ['@echo off', line, 'exit /b 0']})
        with pytest.raises(AssertionError, match='does not know'):
            walk.run('safety.bat', ['status'])


# ───────────────────────── the README's branch section ─────────────────────────

README = (ROOT / 'README.md').read_text(encoding='utf-8')
START, END = '<!-- branch:start -->', '<!-- branch:end -->'
# The names the owner knows the five designs by (the titles of the demo branches' READMEs), by DESIGN_NAME.
DESIGN_LABELS = {'xau_v3lite': 'V3-lite', 'xau_top2': 'Top 2', 'xau_top1': 'Top 1', 'btc_top2': 'Top 2',
                 'btc_turtle_s2': 'Turtle System 2 + bot votes'}


def constants_as_written():
    """constants.py whole, design block included (DEFAULTS stops above the design examples)."""
    ns = {}
    exec(compile((ROOT / 'constants.py').read_text(encoding='utf-8'), str(ROOT / 'constants.py'), 'exec'), ns)
    return ns


def money(x):
    return f'${x:,.2f}'


def percent(x):
    return f'{x:g}%'


def readme_parts():
    assert README.count(START) == 1 and README.count(END) == 1
    head, rest = README.split(START, 1)
    section, below = rest.split(END, 1)
    assert head.strip() == '', 'the branch section is the first thing in the README'
    return section, below


def test_the_readmes_branch_section_agrees_with_constants_and_symbols_json():
    """The generator stamps this section per branch. A wrong line here sends the owner to another bot's folder,
    port or limits."""
    section, _ = readme_parts()
    c = constants_as_written()
    account_folder = ntpath.join(ntpath.dirname(c['OUTPUT_DIR']), c['ACCOUNT_FOLDER'])
    step = next(s['step_up_balance'] for s in SYMBOLS['symbols'] if s['symbol'] == SYMBOL)
    unit_max = next(s['unit_max_limit'] for s in SYMBOLS['symbols'] if s['symbol'] == SYMBOL)
    start = 1500.0
    title = section.strip().splitlines()[0]
    assert title.startswith('# ') and c['BRANCH'] in title and SYMBOL in title and 'REAL MONEY' in title
    assert DESIGN_LABELS[c['DESIGN_NAME']] in title
    assert ('Turtle' in title) == (c['STRATEGY'] == 'turtle')
    wanted = {
        'the branch': f"`{c['BRANCH']}`",
        'the partner branch': f"`{c['PARTNER_BRANCH']}`",
        'the account number': f"account {c['ACCOUNT_SLOT']}",
        'the bot folder': f"`{c['OUTPUT_DIR']}`",
        'the account folder': f'`{account_folder}`',
        'the dashboard address': f"http://localhost:{c['DASHBOARD_PORT']}",
        'the launcher': f'`{SYMBOL_LAUNCHER} live`',
        'the magic number': str(c['MAGIC']),
        'the drop limit': f"{percent(c['SAFETY_DROP_PCT'])} below",
        'the drop in dollars': f"a fall of {money(start * c['SAFETY_DROP_PCT'] / 100)}",
        'the balance of the drop block': f"a balance of {money(start * (1 - c['SAFETY_DROP_PCT'] / 100))}",
        'the day limit': f"{percent(c['SAFETY_DAY_PCT'])} lost",
        'the day limit in dollars': f"that is {money(start * c['SAFETY_DAY_PCT'] / 100)}",
        'the losing-trades limit': f"after {c['SAFETY_STREAK_N']} losing trades in a row",
        'the second unit': f"2 units from an account balance of ${step / c['ACCOUNT_SHARE']:,.0f}",
        'the most units': f'at most {unit_max} units',
        'the credentials file': '`mt5_credentials.json`',
    }
    missing = {what: text for what, text in wanted.items() if text not in section}
    assert missing == {}
    assert c['ACCOUNT_SHARE'] == 0.5 and 'half of the account balance' in section
    assert f'${start:,.0f}' in section


def test_below_its_branch_section_the_readme_is_the_same_for_every_branch():
    """Only the section between the two marks is stamped per branch. A value of this branch below it would stand
    unchanged, and wrong, in the README of the other 19."""
    _, below = readme_parts()
    c = constants_as_written()
    account_folder = ntpath.join(ntpath.dirname(c['OUTPUT_DIR']), c['ACCOUNT_FOLDER'])
    own = [c['BRANCH'], c['PARTNER_BRANCH'], c['OUTPUT_DIR'], account_folder, c['ACCOUNT_FOLDER'],
           str(c['DASHBOARD_PORT']), str(c['MAGIC']), SYMBOL_LAUNCHER, c['DESIGN_NAME']]
    found = [value for value in own if value in below]
    assert found == []
    assert not re.search(r'live\d+_', below), 'a real branch or account folder is named below the branch section'
    assert not re.search(r'\b8[12]\d\d\b', below), 'a dashboard port is named below the branch section'
    for heading in ('## 1. ', '## 2. ', '## 3. ', '## 4. ', '## 5. ', '## 6. ', '## 7. '):
        assert below.count('\n' + heading) == 1, heading


# What the advice texts of app.py, tracelog.py, dashboard.py and safety.py send the owner to: 'README, section 2,
# step 5', 'README, section 2, steps 4 and 5', 'README, section 2 "First start", step 4', 'README, section 6'; and,
# in a text that points to section 2, a bare '(step 5)' after it.
README_REF = re.compile(r'README, section (\d+)(?: "[^"]*")?(?:,? steps? (\d+)(?: and (\d+))?)?')
BARE_STEP_REF = re.compile(r'\(steps? (\d+)(?: and (\d+))?\)')
# The README's own pointers: 'step 1 of section 2', '(section 2, step 8)', and inside section 2 '(step 7)'.
README_OWN_REF = re.compile(r'\bsection (\d+), steps? (\d+)(?: and (\d+))?|\bsteps? (\d+)(?: and (\d+))?(?: of section (\d+))?')
README_SECTION_WORDS = {1: 'What this branch is', 2: 'First start', 3: 'safety', 4: 'Size', 5: 'Logs',
                        6: 'Warnings', 7: 'tests'}
# The steps of "First start" in their order (review ops #4: MetaTrader 5 is installed before its path goes into the
# credentials, and the port is closed to everybody else before a dashboard listens on it).
README_STEP_WORDS = {1: 'Clone each branch', 2: 'old bots', 3: 'BEFORE you change the credentials',
                     4: 'installed and logged in by hand', 5: 'mt5_credentials.json', 6: 'Fund the account',
                     7: 'port', 8: 'Start the gold bot', 9: 'PIN', 10: 'Check the page'}
# How a text that points to a step names what the step is about, by a word of the step's bold title. A pointer whose
# sentence names none of its step's words points to another step: one that moved, its pointers left behind. A step
# without words here is one no text points to.
POINTER_TOPICS = {
    'Clone each branch': (r'\bclone\b', r'\bown folder\b'),
    'old bots': (r'\bold (ladder )?bots?\b',),
    'logged in by hand': (r'\bby hand\b', r'\bSave password\b', r'\bLogin to Trade Account\b', r'\bAlgo Trading\b',
                          r'\bPython API\b', r'\blogged into\b', r'\bMetaTrader 5 installation\b'),
    'mt5_credentials.json': (r'\bmt5_credentials\.json\b', r'\bcredentials file\b', r'\blogin_(id|pass)\b',
                             r'\bterminal_path\b', r'\bGitHub\b'),
    'port': (r'\bport\b', r'\bfirewall\b', r'\baccept connections\b'),
    'Start the gold bot': (r'\bfour windows\b', r'\bdashboards? starts?\b'),
    'PIN': (r'\bPIN\b',),
}
CODE_WITH_ADVICE = ('app.py', 'tracelog.py', 'dashboard.py', 'safety.py', 'collect_logs.py')


def readme_sections():
    """{n: (title, body)} of the sections '## n. title' below the branch section."""
    _, below = readme_parts()
    out = {}
    for m in re.finditer(r'^## (\d+)\. (.*)\n((?:(?!^## ).*\n?)*)', below, re.M):
        out[int(m.group(1))] = (m.group(2), m.group(3))
    return out


def readme_steps(body):
    """{n: the bold title of step n} of a numbered list of steps ('3. **Start the bot ...**')."""
    return {int(m.group(1)): ' '.join(m.group(2).split())
            for m in re.finditer(r'^(\d+)\. \*\*(.+?)\*\*', body, re.M | re.S)}


def code_texts(name):
    """Every string a Python file of the branch holds, adjacent literals joined (as Python joins them); an f-string
    whole, its values as '{}' (not also its pieces one by one)."""
    tree = ast.parse((ROOT / name).read_text(encoding='utf-8'))
    pieces = {id(v) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for v in node.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in pieces:
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield ''.join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else '{}'
                          for v in node.values)


def readme_refs():
    """(file, section, step or None) of every README pointer in the bot's and the dashboard's texts."""
    out = set()
    for name in CODE_WITH_ADVICE:
        if not (ROOT / name).exists():
            continue
        for text in code_texts(name):
            for _, _, section, steps in code_pointers(text):
                out.update((name, section, step) for step in steps or [None])
    return sorted(out, key=lambda r: (r[0], r[1], r[2] or 0))


def code_pointers(text):
    """[(start, end, section, [steps])] of the README pointers of one text of the code, in their order."""
    found = [(m.start(), m.end(), int(m.group(1)), [int(x) for x in m.group(2, 3) if x])
             for m in README_REF.finditer(text)]
    if any(section == 2 for _, _, section, _ in found):
        found += [(m.start(), m.end(), 2, [int(x) for x in m.group(1, 2) if x]) for m in BARE_STEP_REF.finditer(text)
                  if not any(a <= m.start() < b for a, b, _, _ in found)]
    return sorted(found)


def readme_lines():
    """The README below its branch section as (section, line): a paragraph, a list item or a table cell joined into
    one line; code blocks left out."""
    _, below = readme_parts()
    out, section, current, code = [], 0, None, False
    for line in below.split('\n'):
        s = line.strip()
        if s.startswith('```'):
            code, current = not code, None
        elif code:
            continue
        elif re.match(r'## (\d+)\. ', s):
            section, current = int(re.match(r'## (\d+)\. ', s).group(1)), None
        elif not s:
            current = None
        elif s.startswith('|'):
            out += [[section, cell.strip()] for cell in s.strip('|').split('|')]
            current = None
        elif current is None or re.match(r'(- |\d+\. )', s):
            current = [section, s]
            out.append(current)
        else:
            current[1] += ' ' + s
    return [tuple(x) for x in out]


def readme_pointers(section, text):
    """[(start, end, section, [steps])] of the README's own pointers to steps in one of its lines."""
    found = []
    for m in README_OWN_REF.finditer(text):
        if m.group(1):
            found.append((m.start(), m.end(), int(m.group(1)), [int(x) for x in m.group(2, 3) if x]))
        else:
            found.append((m.start(), m.end(), int(m.group(6) or section), [int(x) for x in m.group(4, 5) if x]))
    return found


def sentence_start(text, at):
    """Where the sentence that holds position `at` starts: after a '.', '!' or '?' and a blank, outside brackets."""
    start, depth = 0, 0
    for i, ch in enumerate(text[:at]):
        depth += (ch in '([') - (ch in ')]')
        if ch in '.!?' and depth <= 0 and text[i + 1:i + 2].isspace():
            start = i + 1
    return start


def pointer_problems(where, text, pointers, steps):
    """What is wrong with the pointers of one text to steps of "First start" (`steps`: {n: the step's title}): a
    step that is not there, or a pointer whose sentence before it names nothing of what its step is about. A
    pointer to two steps is judged on the text since the pointer before it (it sums up more than one sentence)."""
    out = []
    for k, (start, end, section, numbers) in enumerate(pointers):
        if section != 2:
            continue
        before = pointers[k - 1][1] if k else 0
        scope = text[before:start] if len(numbers) > 1 else text[max(before, sentence_start(text, start)):start]
        for n in numbers:
            title = steps.get(n)
            words = next((w for key, w in POINTER_TOPICS.items() if title and key.lower() in title.lower()), None)
            if title is None:
                out.append(f'{where}: {text[start:end]!r}: there is no step {n}')
            elif words is None:
                out.append(f'{where}: {text[start:end]!r}: no text points to step {n} ("{title}")')
            elif not any(re.search(w, scope, re.I) for w in words):
                out.append(f'{where}: {text[start:end]!r} names step {n} ("{title}"), but it says: {scope.strip()!r}')
    return out


def test_the_readme_sections_and_steps_the_advice_texts_name_are_there_and_about_that():
    """The advice on the page and in the window says 'README, section 2, step 5' and the like: the owner opens the
    README there. A step renumbered, or a section moved, would send him to the wrong instruction while real money
    waits. Every pointer of the code must find its section, and its step of "First start"; and the sections and
    steps keep the topics the advice texts take them for."""
    sections = readme_sections()
    assert sorted(sections) == [1, 2, 3, 4, 5, 6, 7]
    for n, words in README_SECTION_WORDS.items():
        assert words.lower() in sections[n][0].lower(), (n, sections[n][0])
    steps = readme_steps(sections[2][1])
    assert sorted(steps) == list(range(1, len(steps) + 1)) and len(steps) >= 10, sorted(steps)
    for n, words in README_STEP_WORDS.items():
        assert words.lower() in steps[n].lower(), (n, steps[n])
    refs = readme_refs()
    assert any(step is not None for _, _, step in refs), 'no pointer to a step found: the pattern no longer matches'
    wrong = [(name, section, step) for name, section, step in refs
             if section not in sections or (step is not None and (section != 2 or step not in steps))]
    assert wrong == []


def test_the_readme_pointer_pattern_reads_every_form_the_texts_use():
    """The check above is only as good as its pattern."""
    found = [m.groups() for t in ('(README, section 2, step 5).', '(README, section 2, steps 4 and 5)',
                                  '(README, section 2 "First start", step 4)', 'README, section 6.',
                                  'README, section 2, steps 2 and 5')
             for m in README_REF.finditer(t)]
    assert found == [('2', '5', None), ('2', '4', '5'), ('2', '4', None), ('6', None, None), ('2', '2', '5')]
    bare = 'Log it in by hand (README, section 2, step 4); or correct login_pass and pull (step 5). (step 0.5N)'
    assert [p[2:] for p in code_pointers(bare)] == [(2, [4]), (2, [5])]
    assert code_pointers('Add step 0.5N (step 4).') == []              # a bare one only beside a README pointer
    own = 'Stop it (step 2 of section 2), then start the four windows (section 2, step 8) and see (step 7).'
    assert [p[2:] for p in readme_pointers(6, own)] == [(2, [2]), (2, [8]), (6, [7])]


def first_start_steps():
    return readme_steps(readme_sections()[2][1])


def step_about(words):
    """The number of the step of "First start" whose title holds these words."""
    found = [n for n, title in first_start_steps().items() if words.lower() in title.lower()]
    assert len(found) == 1, (words, found)
    return found[0]


def test_every_pointer_to_a_step_of_first_start_is_about_that_step():
    """The advice texts say 'Log MetaTrader 5 in by hand (README, section 2, step 4)', and the README says 'step 5
    of section 2'. When steps move (review ops #4 moved MetaTrader 5 before the credentials and the firewall before
    the dashboards), a pointer left behind sends the owner to the wrong step while real money waits. Each pointer,
    in the code and in the README, must stand in a sentence about what its step is about."""
    steps = first_start_steps()
    problems = []
    for name in CODE_WITH_ADVICE:
        if (ROOT / name).exists():
            for text in code_texts(name):
                problems += pointer_problems(name, text, code_pointers(text), steps)
    pointed = 0
    for section, line in readme_lines():
        found = readme_pointers(section, line)
        pointed += sum(p[2] == 2 for p in found)
        problems += pointer_problems(f'README section {section}', line, found, steps)
    assert pointed >= 8, 'the README points to fewer steps than it does: the pattern no longer matches'
    assert problems == []


def test_the_pointer_check_sees_a_pointer_left_behind():
    """The check above is only as good as its words: each wrong pointer below is caught, each right one passes."""
    steps = first_start_steps()
    mt5, creds, old = step_about('logged in by hand'), step_about('mt5_credentials.json'), step_about('old bots')
    port, pin, check = step_about('port'), step_about('PIN'), step_about('Check the page')

    def wrong(text):
        return pointer_problems('t', text, code_pointers(text), steps)

    right = [f'Log MetaTrader 5 in by hand, with "Save password" ticked (README, section 2, step {mt5}).',
             f'Put the four values into mt5_credentials.json on GitHub (README, section 2, step {creds}).',
             f'Log it in by hand (README, section 2, step {mt5}); if the password was wrong, correct login_pass and '
             f'pull (step {creds}).',
             f'Log MetaTrader 5 back in (File > Login to Trade Account). If an old bot switched it, stop the old bot '
             f'first (README, section 2, steps {old} and {mt5}).',
             f'Open its port to your own IP address only (README, section 2, step {port}).',
             f'There is no usable PIN on the server yet: {{}} (README, section 2, step {pin}).']
    for text in right:
        assert wrong(text) == [], text
    for text in [f'Log MetaTrader 5 in by hand (README, section 2, step {creds}).',
                 f'Put the four values into mt5_credentials.json on GitHub (README, section 2, step {mt5}).',
                 f'Log it in by hand (README, section 2, step {mt5}); or correct login_pass and pull (step {mt5}).',
                 f'Log MetaTrader 5 back in. If an old bot switched it, stop it (README, section 2, steps {old} and '
                 f'{creds}).',
                 f'Somebody else reaches this page: open its port to your own IP only (README, section 2, step {check}).',
                 f'There is no usable PIN yet (README, section 2, step {port}).',
                 'Stop the old bot (README, section 2, step 99).']:
        assert wrong(text) != [], text


def readme_step_texts():
    """{n: the whole text of step n of "First start", its lines joined}."""
    body = readme_sections()[2][1]
    marks = list(re.finditer(r'^(\d+)\. \*\*', body, re.M))
    return {int(m.group(1)): ' '.join(body[m.start():(marks[i + 1].start() if i + 1 < len(marks) else None)].split())
            for i, m in enumerate(marks)}


def readme_daily_rules():
    body = readme_sections()[6][1]
    assert body.count('**Rules for every day**') == 1
    return ' '.join(body.split('**Rules for every day**', 1)[1].split())


def test_the_first_start_installs_metatrader_before_the_credentials_and_closes_the_port_before_the_dashboards():
    """Review ops #4. terminal_path can only be written once this account's MetaTrader 5 is installed (a second
    account on the server needs a second installation). And the port must be closed to everybody else before a
    dashboard listens on it: at its first start Windows asks whether python.exe may accept connections, and 'Allow
    access' lets everybody in on every port; a firewall that is off makes the rule do nothing."""
    texts = readme_step_texts()

    def step(pattern):
        found = [n for n, text in texts.items() if re.search(pattern, text)]
        assert len(found) == 1, (pattern, found)
        return found[0]

    install = step(r'install a second MetaTrader 5 for it.*Note the full path of the `terminal64\.exe`')
    credentials = step(r"^\d+\. \*\*Put the new account's details into `mt5_credentials\.json`")
    firewall = step(r'netsh advfirewall firewall add rule name=')
    dashboards = step(r'In each of the two folders: `start_dashboard\.bat`')
    assert install < credentials and firewall < dashboards
    assert f'noted in step {install}' in texts[credentials]
    said = texts[firewall]
    for words in ('before the dashboards start', 'Check that Windows Defender Firewall is On',
                  '`netsh advfirewall show allprofiles state` must show `State ON` for every profile',
                  'Windows may ask whether python.exe may accept connections. Choose **Cancel**.'):
        assert words in said, words
    assert f'choose Cancel (step {firewall})' in texts[dashboards]


def test_the_daily_rules_bring_the_bots_back_after_a_sign_out_or_a_restart():
    """Review ops #2. Signing out of the server ends every bot and MetaTrader 5, and so does a restart; nothing
    starts them again by itself, and a task left at Task Scheduler's default ends its window after 3 days."""
    rules = readme_daily_rules()
    start = step_about('Start the gold bot')
    for words in ('**Never sign out of the server.** Signing out ends every bot, every dashboard and MetaTrader 5.',
                  'close the Remote Desktop window instead: that only disconnects',
                  f'**After the server has restarted, start the four windows of every account again** (section 2, '
                  f'step {start})',
                  '**Windows Update must not restart the server by itself.** Set it to notify only',
                  'then D (download only)', 'set its active hours',
                  'one Task Scheduler task for each bot and one for each dashboard', '"Create Task..."',
                  '"Run only when user is logged on"', '"At log on"', 'Start in: the branch folder',
                  'Program/script: `cmd.exe`', '`/c set ALCADEIAS_NO_PAUSE=1&& start_job.bat live`',
                  '`/c set ALCADEIAS_NO_PAUSE=1&& start_dashboard.bat`',
                  'untick "Stop the task if it runs longer than". With its default of 3 days'):
        assert words in rules, words
    # what the task's line sets is what the launchers read: without it a stop would wait for a key
    for launcher in ('start_job.bat', 'start_dashboard.bat'):
        assert PAUSE in commands(lines_of(launcher))


def test_the_readme_says_never_to_click_inside_a_bots_window_and_how_to_unfreeze_it():
    """Review ops #1. A click in the console window of a bot starts a selection (its title begins with 'Select'),
    and the bot's next line, and with it its whole loop and every exit, waits until Esc."""
    rules = readme_daily_rules()
    assert ("**Never click inside a bot's window.** If its title starts with `Select`, the bot is frozen: press "
            "Esc.") in rules
    rows = [line for line in readme_sections()[6][1].splitlines() if line.startswith('| Grey line `The bot is not '
                                                                                      'running`')]
    assert len(rows) == 1
    assert "never click inside it. If its title starts with `Select`, the bot is frozen: press Esc." in rows[0]
    assert 'never click inside it' in readme_step_texts()[step_about('Start the gold bot')]


def test_the_readme_says_what_the_review_changed_in_the_bot():
    """Where the README says what the bot does, it says what it does now: it never logs in a MetaTrader 5 an old bot
    uses, also after that MetaTrader 5 restarted (review money-paths #1); the zip holds random tokens in place of
    the account's fingerprints (ops #3); `safety.bat unblock` also repairs a damaged file of the safety (safety #1)."""
    _, below = readme_parts()
    text = ' '.join(below.split())
    for words in ('It never logs in a MetaTrader 5 that an old bot uses, also not after that MetaTrader 5 has '
                  'restarted.',
                  'While the old bot runs, the bot never logs that MetaTrader 5 in, also not after MetaTrader 5 has '
                  'restarted.',
                  'In the zip each fingerprint is replaced by a random token, so the zip holds neither the account '
                  'number nor anything that gives it back.',
                  'The zip you send with `collect_logs.bat` holds neither the number nor anything that gives it back',
                  '`safety.bat unblock` also repairs a damaged file of the safety: `safety_restart.json`',
                  'and tells you to run `safety.bat unblock` on the server. It writes the file anew and says so'):
        assert words in text, words
    # what the README says a button answers is what safety.py answers
    assert any('run "safety.bat unblock" on the server' in t and 'anew' in t for t in code_texts('safety.py'))
