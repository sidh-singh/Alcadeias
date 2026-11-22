"""
The log export (collect_logs.py, spec section 8): the zip the owner sends when something has to be looked at.

Each rule of the export has a test here: it takes only what it names; it never takes the credentials, the PIN, the
PIN's lock-out, the login budget, a .git or a dash_env folder -- also when the repository itself was cloned into
the bot's output folder, and under whatever name a copy of the credentials file hides; it copes with files a running
bot holds open and lists them in SKIPPED.txt inside the zip; it refuses when the zip would leave less than 2 GB
free; it keeps the newest 5 zips of its branch; it prints the full path of the zip; it changes nothing in the folders
it copies; it needs the standard library only.

Everything is built in the test's tmp_path. No test names a value of the deployment block: the branch, the output
folder and the account folder are read from the head of constants.py (conftest.DEFAULTS).
"""
import ast
import builtins
import importlib.util
import io
import json
import os
import re
import sys
import time
import zipfile

import pytest

from conftest import DEFAULTS, ROOT


def _load(name):
    """A module of the branch folder, from its file (the tests' own modules stay as they are)."""
    spec = importlib.util.spec_from_file_location(f'{name}_under_test', ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CL = _load('collect_logs')

LABEL = 'unit_export'                       # collect() takes the branch as a value: any name does for its rules
SYMBOL = 'XAUUSDm'
SECRET = 'S3cr3t-pa55word-of-the-real-account'
PIN = '918273'
LOGIN = '12345678'
NOW = 1795428930.0                          # a fixed time for the zip's name (any time does)
GB = 2 ** 30


def _credentials():
    return json.dumps({'live': {'terminal_path': 'C:\\MT5\\terminal64.exe', 'login_id': int(LOGIN),
                                'login_pass': SECRET, 'server': 'Fake-Real'}}, indent=4)


# What the bot writes into its output folder: all of this belongs in the zip.
BOT_DATA = {
    f'{SYMBOL}.json': '{"bot": {"branch": "x"}}',
    f'{SYMBOL}_trace.json': '{"schema": 1, "health": {"connect_problem": "check login_id, login_pass and server"}}',
    f'{SYMBOL}_bars.json': '{"tf": {}}',
    f'{SYMBOL}_trades.json': '{"closed": []}',
    'account.json': '{"balance": 1500.0}',
    'active_config.json': '{"mode": "live"}',
    f'logs/{SYMBOL}_2026-11-20.log': 'an old day\n',
    f'logs/{SYMBOL}_2026-11-21.log': ('2026-11-21 08:00:00.000 UTC | INFO | START | Put the new account\'s login_id, '
                                     'login_pass and server in its "live" block\n') * 40,
    f'logs/{SYMBOL}_2026-11-21_events.jsonl': '{"t": 1, "level": "INFO", "msg": "in its \\"live\\" block"}\n' * 30,
    f'logs/{SYMBOL}_2026-11-21_samples.jsonl': '{"bid": 1.0}\n' * 30,
    f'logs/{SYMBOL}_strategy_log.json': '[]',
    f'journal/{SYMBOL}_2026.jsonl': '{"kind": "start"}\n{"kind": "order"}\n',
    f'state/{SYMBOL}_state.json': '{"basket": null}',
    f'state/{SYMBOL}_journal_state.json': '{"journaled": []}',
    'state/safety_state.json': '{"version": 1}',
    'state/safety_closes.json': '{"queue": []}',
    'state/live_start.json': '{"time": 1}',
    f'state/{SYMBOL}_state.json.other-account-20261121_140500': '{"basket": null}',
    f'daily_trade/{SYMBOL}/21_nov_2026.json': '{"deals": []}',
    f'daily_trade/{SYMBOL}/historical_summary.json': '{"days": 1}',
}
# What also lies there when the owner cloned the repository INTO the bot's output folder (the README says not
# to), ran the dashboard there and kept copies of his login details: none of this may be in the zip.
REPOSITORY = {
    '.git/config': '[remote "origin"]\n\turl = https://example.invalid/bot.git\n',
    '.git/HEAD': 'ref: refs/heads/x\n',
    '.git/objects/ab/cdef0123': 'blob ' + SECRET,
    'mt5_credentials.json': None,                                   # (filled with _credentials())
    'MT5_Credentials - Copy.json': None,
    'mt5_credentials.json.orig': None,
    'my_logins_backup.json': None,                                  # a copy under a name of its own
    'app.py': '# the bot\n',
    'constants.py': "BRANCH = 'x'\n",
    'README.md': 'read me\n',
    'start_job.bat': '@echo off\n',
    'notes.txt': 'not a json file\n',
    'tests_demo/test_x.py': '\n',
    'tests_demo/data.json': '{}',
    'dash_env/Scripts/python.exe': 'MZ',
    'dash_env/pyvenv.cfg': 'home = C:\\Python311\n',
    'dash_env/Lib/site-packages/dash/package.json': '{}',
    '__pycache__/app.cpython-311.pyc': 'x',
    f'state/{SYMBOL}.lock': '',
    'state/mt5_credentials.json': None,                             # a stray copy inside a folder that IS taken
    'logs/.git/config': 'nested',
    'logs/dash_env/x.json': '{}',
    'journal/Safety_PIN.txt': PIN,
}
ACCOUNT_DATA = {
    'safety_switch.json': '{"enabled": true}',
    'safety_restart.json': '{"id": "20261121_140500-a1b2c3", "scope": "account"}',
    'safety_block_20261121_140500-a1b2c3.json': '{"rules": ["DROP"]}',
    'safety_status_one.json': '{"blocked": true}',
    'safety_status_two.json': '{"blocked": true}',
    'safety_audit.jsonl': '{"action": "unblock", "by": "command line"}\n',
    'account_claim.json': '{"login_tail": "...5678"}',
}
ACCOUNT_NEVER = {
    'safety_pin.txt': PIN,
    'safety_lockout.json': '{"wrong": 2, "pin_tried": "' + PIN + '"}',
    'login_attempt.json': '{"failed": 1, "note": "' + SECRET + '"}',
    'safety_lockout.json.4312.9f3a1c2e.tmp': '{"wrong": 1, "pin_tried": "' + PIN + '"}',
    'login_attempt.json.tmp': SECRET,
    'safety_pin - Copy.txt': PIN,
    'inner/deep.json': '{"not": "taken: only the files of the account folder itself"}',
}


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_credentials() if text is None else text, encoding='utf-8', newline='')


@pytest.fixture
def export_dirs(tmp_path):
    """(bot folder, account folder, exports folder): a bot's output folder as it is on the server after a day of
    trading, with the repository cloned inside it, and its account folder."""
    bot, account, out = tmp_path / 'bot_output', tmp_path / 'the_account', tmp_path / 'exports'
    _write(bot, BOT_DATA)
    _write(bot, REPOSITORY)
    _write(account, ACCOUNT_DATA)
    _write(account, ACCOUNT_NEVER)
    return bot, account, out


def _zip_of(report):
    with zipfile.ZipFile(report.zip_path) as zf:
        assert zf.testzip() is None
        return {name: zf.read(name) for name in zf.namelist()}


def _expected_members():
    return ({f'bot/{rel}' for rel in BOT_DATA} | {f'account/{name}' for name in ACCOUNT_DATA} | {'SKIPPED.txt'})


def _snapshot(*roots):
    seen = {}
    for root in roots:
        for folder, _dirs, names in os.walk(root):
            for name in names:
                path = os.path.join(folder, name)
                st = os.stat(path)
                with open(path, 'rb') as f:
                    seen[path] = (st.st_size, st.st_mtime_ns, f.read())
    return seen


# ───────────────────────── what is taken, and what never is ─────────────────────────

def test_the_zip_holds_only_what_the_export_names(export_dirs):
    """logs/, journal/, state/, daily_trade/ and the top-level *.json files of the bot folder, and the files of the
    account folder: each one, with its content, and nothing else -- tested with the repository cloned inside the bot
    folder."""
    bot, account, out = export_dirs
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    assert set(members) == _expected_members()
    for rel, text in BOT_DATA.items():
        assert members[f'bot/{rel}'] == text.encode('utf-8'), rel
    for name, text in ACCOUNT_DATA.items():
        assert members[f'account/{name}'] == text.encode('utf-8'), name
    assert report.written == len(BOT_DATA) + len(ACCOUNT_DATA) and not report.unreadable


def test_the_credentials_the_pin_and_the_repository_are_never_in_the_zip(export_dirs):
    """Never a file called mt5_credentials.json, safety_pin.txt, safety_lockout.json or login_attempt.json, never a
    folder called .git or dash_env: not at the top, not inside a folder that is taken, not in another spelling, not
    as a leftover or a copy -- and the password and the PIN are in no byte of the zip."""
    bot, account, out = export_dirs
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    for name, data in members.items():
        low = name.lower()
        for word in ('mt5_credentials', 'safety_pin', 'safety_lockout', 'login_attempt', '.git', 'dash_env',
                     'backup', '.lock', '__pycache__', 'tests_demo', 'app.py'):
            assert word not in low, name
        for secret in (SECRET, PIN):
            assert secret.encode() not in data, name
            assert secret.encode('utf-16-le') not in data, name
    with open(report.zip_path, 'rb') as f:
        raw = f.read()
    for secret in (SECRET, PIN, 'terminal64.exe'):               # (only the credentials file names the terminal)
        assert secret.encode() not in raw


def test_the_export_never_opens_a_file_it_must_not_take(export_dirs, monkeypatch):
    """It leaves the credentials and the PIN alone by their names: it does not open them to look. (Only the copy
    under a name of its own, which no name rule can know, is read and then left out.)"""
    bot, account, out = export_dirs
    opened = []

    def recording_open(path, *args, **kwargs):
        opened.append(os.fspath(path))
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(CL, 'open', recording_open, raising=False)
    CL.collect(bot, account, out, LABEL, now=NOW)
    assert opened, 'the test no longer sees the export\'s reads'
    for path in opened:
        rel = os.path.relpath(path, bot.parent).replace(os.sep, '/').lower()
        for word in ('mt5_credentials', 'safety_pin', 'safety_lockout', 'login_attempt', '/.git/', '/dash_env/',
                     '.lock'):
            assert word not in rel, path
    assert str(bot / 'my_logins_backup.json') in opened


def test_a_copy_of_the_credentials_under_another_name_is_left_out_by_what_it_holds(export_dirs):
    """A small file with a "login_pass" entry is the credentials file, whatever it is called (also saved as UTF-16,
    as PowerShell's redirect does). A log line that only talks about login_pass is not."""
    bot, account, out = export_dirs
    (bot / 'old_details.json').write_bytes(b'\xff\xfe' + _credentials().encode('utf-16-le'))
    (account / 'safety_note.json').write_text('{"Login_Pass" : "' + SECRET + '"}', encoding='utf-8')
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    assert set(members) == _expected_members()
    left = dict(report.left_out)
    for arc in ('bot/my_logins_backup.json', 'bot/old_details.json', 'account/safety_note.json'):
        assert 'login_pass' in left[arc], arc
    assert CL.holds_password_entry(b'{"login_pass": "x"}') and CL.holds_password_entry(b'{ "login_pass" :1}')
    assert not CL.holds_password_entry(b'check login_id, login_pass and server')
    assert not CL.holds_password_entry(b'{"msg": "put login_pass in its \\"live\\" block: now"}')
    # the trace and the log of the fixture talk about login_pass and are in the zip
    assert b'login_pass' in members[f'bot/{SYMBOL}_trace.json']
    assert b'login_pass' in members[f'bot/logs/{SYMBOL}_2026-11-21.log']


@pytest.mark.parametrize('name', ['mt5_credentials.json', 'MT5_CREDENTIALS.JSON', 'mt5_credentials.json.orig',
                                  'mt5_credentials - Copy.json', 'Copy of mt5_credentials.json',
                                  'safety_pin.txt', 'Safety_Pin.TXT', 'safety_pin.txt.bak', 'safety_lockout.json',
                                  'safety_lockout.json.4312.9f3a1c2e.tmp', 'login_attempt.json',
                                  'login_attempt.json.77.0a1b2c3d.tmp', 'my passwords.json', 'secrets.json'])
def test_names_that_are_never_taken(name):
    assert CL.never_file(name)


@pytest.mark.parametrize('name', ['safety_switch.json', 'safety_restart.json', 'safety_audit.jsonl',
                                  'safety_state.json', 'safety_closes.json', 'account_claim.json', 'live_start.json',
                                  'account.json', f'{SYMBOL}_trace.json', f'{SYMBOL}_2026-11-21.log',
                                  'safety_status_any_branch.json', 'safety_block_20261121_140500-a1b2c3.json'])
def test_names_of_the_bots_own_files_are_taken(name):
    assert not CL.never_file(name)


def test_the_four_never_files_and_two_never_folders_of_the_spec():
    assert set(CL.NEVER_FILES) == {'mt5_credentials.json', 'safety_pin.txt', 'safety_lockout.json',
                                   'login_attempt.json'}
    assert set(CL.NEVER_FOLDERS) == {'.git', 'dash_env'}
    assert set(CL.BOT_FOLDERS) == {'logs', 'journal', 'state', 'daily_trade'}
    for name in CL.NEVER_FILES:
        assert CL.never_file(name) and CL.never_file(name.upper())
    for name in CL.NEVER_FOLDERS:
        assert CL.never_folder(name) and CL.never_folder(name.upper())
    assert not CL.never_folder('logs') and not CL.never_folder('git')


def test_a_link_is_not_followed(export_dirs):
    """A link inside a folder that is taken could lead anywhere (the credentials, the repository): it is left out
    and listed."""
    bot, account, out = export_dirs
    try:
        os.symlink(bot / 'mt5_credentials.json', bot / 'logs' / 'harmless.json')
        os.symlink(bot / '.git', bot / 'state' / 'history', target_is_directory=True)
        os.symlink(bot / 'mt5_credentials.json', bot / 'linked.json')
    except (OSError, NotImplementedError):
        pytest.skip('this system does not let the test make a link')
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    assert set(members) == _expected_members()
    left = dict(report.left_out)
    for arc in ('bot/logs/harmless.json', 'bot/state/history', 'bot/linked.json'):
        assert 'link' in left[arc], arc
    assert all(SECRET.encode() not in data for data in members.values())


def test_skipped_txt_says_what_the_export_is_and_what_it_left_out(export_dirs):
    bot, account, out = export_dirs
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    text = _zip_of(report)['SKIPPED.txt'].decode('utf-8')
    assert f'branch: {LABEL}' in text and 'UTC' in text
    assert str(bot) in text and str(account) in text
    assert f'files in this zip: {len(BOT_DATA) + len(ACCOUNT_DATA)}' in text
    assert 'Could not be read, or not completely (0):' in text and 'every file was read to its end' in text
    for arc in ('bot/mt5_credentials.json', 'bot/state/mt5_credentials.json', 'bot/logs/.git/', 'bot/logs/dash_env/',
                'bot/journal/Safety_PIN.txt', 'account/safety_pin.txt', 'account/safety_lockout.json',
                'account/login_attempt.json', f'bot/state/{SYMBOL}.lock', 'bot/my_logins_backup.json'):
        assert f'  {arc}: ' in text, arc
    for secret in (SECRET, PIN, LOGIN):
        assert secret not in text


def test_nothing_in_the_folders_it_copies_is_changed(export_dirs):
    """The export only reads: after it the bot folder and the account folder hold the same files with the same
    bytes and the same times, and the zip is the only new file anywhere."""
    bot, account, out = export_dirs
    before = _snapshot(bot, account)
    top_before = sorted(p.name for p in bot.parent.iterdir())
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    assert _snapshot(bot, account) == before
    assert sorted(p.name for p in bot.parent.iterdir()) == sorted(top_before + [out.name])
    assert [p.name for p in out.iterdir()] == [os.path.basename(report.zip_path)]


# ───────────────────────── the account number's fingerprint ─────────────────────────

def _sha(login):
    import hashlib
    return hashlib.sha256(str(login).encode('ascii')).hexdigest()


OTHER_LOGIN = '87654321'                    # the other account an old file or a claim may name
ANOTHER_HASH = 'ab' * 32                    # a 64-hex value that is no login_sha (it stays as it is)


def _fingerprinted_bot(tmp_path):
    """A bot folder and its account folder as the real-money bot leaves them: login_sha beside login_tail in the state
    files, live_start.json, the journal state, the claim and the status files; one state file set aside from another
    account; the value also in a log line."""
    me, other = _sha(LOGIN), _sha(OTHER_LOGIN)
    stamp = {'branch': 'x', 'login_sha': me, 'login_tail': '...5678'}
    bot, account, out = tmp_path / 'bot_output', tmp_path / 'the_account', tmp_path / 'exports'
    _write(bot, {
        f'state/{SYMBOL}_state.json': json.dumps(dict(stamp, basket=None)),
        'state/safety_state.json': json.dumps(dict(stamp, version=1), indent=2),
        'state/safety_closes.json': json.dumps(dict(stamp, queue=[])),
        'state/live_start.json': json.dumps({'time': 1, 'login_sha': me, 'login_tail': '...5678'}),
        f'state/{SYMBOL}_journal_state.json': json.dumps(dict(stamp, journaled=[], checksum=ANOTHER_HASH)),
        f'state/{SYMBOL}_state.json.other-account-20261121_140500': json.dumps(
            {'login_sha': other.upper(), 'login_tail': '...4321'}),
        f'logs/{SYMBOL}_2026-11-21.log': f'08:00 | WARN | STATE | put aside: login_sha={me} was {other}\n',
        f'{SYMBOL}_trace.json': '{"schema": 1}',
    })
    _write(account, {
        'account_claim.json': json.dumps({'login_sha': me, 'login_tail': '...5678', 'server': 'Fake-Real'}),
        'safety_status_one.json': json.dumps({'branch': 'one', 'login_sha': me, 'login_tail': '...5678'}),
        'safety_status_two.json': json.dumps({'branch': 'two', 'login_sha': me, 'login_tail': '...5678'}),
    })
    return bot, account, out, me, other


def test_no_login_sha_leaves_in_the_zip_and_each_value_gets_one_random_stand_in(tmp_path):
    """login_sha is the plain SHA-256 of the account number, and the files keep its last 4 digits beside it: the
    number comes back in milliseconds. The zip the owner sends away holds a random stand-in instead -- the same for
    the same value wherever it stands in that zip (both bots' status files still name one account), another for
    another account, new in every zip -- and every file keeps its shape."""
    bot, account, out, me, other = _fingerprinted_bot(tmp_path)
    before = _snapshot(bot, account)
    members = _zip_of(CL.collect(bot, account, out, LABEL, now=NOW))
    assert _snapshot(bot, account) == before                                 # (only the zip is made anew)
    blob = b''.join(members.values())
    assert me.encode() not in blob and other.encode() not in blob.lower()
    tokens = {}
    for arc, data in members.items():
        if arc.endswith('.json') or '.json.' in arc:
            doc = json.loads(data)
            if 'login_sha' in doc:
                assert re.fullmatch(r'[0-9a-f]{64}', doc['login_sha']) and doc['login_tail'] in ('...5678', '...4321')
                tokens.setdefault(doc['login_tail'], set()).add(doc['login_sha'])
    assert len(tokens['...5678']) == 1 and len(tokens['...4321']) == 1 and tokens['...5678'] != tokens['...4321']
    mine, theirs = next(iter(tokens['...5678'])), next(iter(tokens['...4321']))
    assert members[f'bot/logs/{SYMBOL}_2026-11-21.log'] == \
        f'08:00 | WARN | STATE | put aside: login_sha={mine} was {theirs}\n'.encode()
    assert json.loads(members[f'bot/state/{SYMBOL}_journal_state.json'])['checksum'] == ANOTHER_HASH
    assert members[f'bot/{SYMBOL}_trace.json'] == b'{"schema": 1}'
    text = members['SKIPPED.txt'].decode('utf-8')
    assert 'Every login_sha (a fingerprint of an account number) is replaced in this zip' in text
    assert '2 value(s)' in text
    # the next zip: other stand-ins
    again = _zip_of(CL.collect(bot, account, out, LABEL, now=NOW + 60))
    assert json.loads(again['account/account_claim.json'])['login_sha'] not in (mine, me)


def test_a_login_sha_in_a_large_file_is_replaced_also_across_the_chunks_it_is_read_in(tmp_path, monkeypatch):
    bot, account, out, me, other = _fingerprinted_bot(tmp_path)
    monkeypatch.setattr(CL, 'WHOLE_READ_BYTES', 400)
    monkeypatch.setattr(CL, 'CHUNK_BYTES', 50)
    lines = ''.join(f'{i:04d} | INFO | the account {me} at line {i}\n' for i in range(40))
    (bot / 'logs' / f'{SYMBOL}_2026-11-22.log').write_text(lines, encoding='utf-8', newline='')
    members = _zip_of(CL.collect(bot, account, out, LABEL, now=NOW))
    mine = json.loads(members['account/account_claim.json'])['login_sha']
    assert members[f'bot/logs/{SYMBOL}_2026-11-22.log'] == lines.replace(me, mine).encode()
    assert me.encode() not in b''.join(members.values())


def test_without_a_login_sha_the_files_go_into_the_zip_byte_for_byte(export_dirs):
    bot, account, out = export_dirs
    members = _zip_of(CL.collect(bot, account, out, LABEL, now=NOW))
    for rel, text in BOT_DATA.items():
        assert members[f'bot/{rel}'] == text.encode('utf-8'), rel
    assert 'Every login_sha' not in members['SKIPPED.txt'].decode('utf-8')         # (nothing was replaced)


# ───────────────────────── files a running bot holds open ─────────────────────────

class _FailingFile(io.BytesIO):
    """A file that gives `good` bytes and then fails as a locked file does on Windows."""

    def __init__(self, data, good):
        super().__init__(data)
        self._good = good

    def read(self, size=-1):
        if self.tell() >= self._good:
            raise PermissionError(13, 'Permission denied')
        return super().read(min(size, self._good - self.tell()) if size and size > 0 else self._good - self.tell())


def _open_with(failures):
    """An open() for the export: `failures` = {file name: an exception to raise, or bytes readable before a
    failure}."""
    def opener(path, *args, **kwargs):
        todo = failures.get(os.path.basename(os.fspath(path)))
        if isinstance(todo, BaseException):
            raise todo
        if todo is not None:
            with builtins.open(path, 'rb') as f:
                return _FailingFile(f.read(), todo)
        return builtins.open(path, *args, **kwargs)
    return opener


def test_a_file_the_bot_holds_open_is_skipped_and_listed_and_the_rest_is_complete(export_dirs, monkeypatch):
    """A file that cannot be opened, one that cannot be read and one that is gone by the time it is read: each is
    listed in SKIPPED.txt inside the zip; every other file is in the zip, whole."""
    bot, account, out = export_dirs
    monkeypatch.setattr(CL, 'open', _open_with({
        f'{SYMBOL}_trace.json': PermissionError(13, 'The process cannot access the file'),
        'safety_state.json': 0,
        f'{SYMBOL}_bars.json': FileNotFoundError(2, 'No such file or directory'),
    }), raising=False)
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    lost = {f'bot/{SYMBOL}_trace.json', 'bot/state/safety_state.json', f'bot/{SYMBOL}_bars.json'}
    assert set(members) == _expected_members() - lost
    assert {arc for arc, _ in report.unreadable} == lost
    text = members['SKIPPED.txt'].decode('utf-8')
    assert 'Could not be read, or not completely (3):' in text
    for arc in lost:
        assert f'  {arc}: ' in text
    assert 'PermissionError' in text and 'gone before it was read' in text
    for rel, data in BOT_DATA.items():
        if f'bot/{rel}' not in lost:
            assert members[f'bot/{rel}'] == data.encode('utf-8')


def test_a_temp_file_the_bot_finished_meanwhile_is_no_problem(export_dirs, monkeypatch):
    """The bot writes a state file as <name>.<pid>.<hex>.tmp and renames it within a millisecond. One that is in the
    folder's listing and gone at the read is the normal case: no alarm, and the real file is in the zip. A leftover
    temp file of a crashed process is still taken."""
    bot, account, out = export_dirs
    (bot / 'state' / 'safety_state.json.4312.0a1b2c3d.tmp').write_text('{"version": 1}', encoding='utf-8')
    (account / 'safety_status_one.json.77.9f8e7d6c.tmp').write_text('{"blocked": false}', encoding='utf-8')
    (bot / 'state' / 'left_by_a_crash.json.99.tmp').write_text('{"old": true}', encoding='utf-8')
    gone = FileNotFoundError(2, 'No such file or directory')
    monkeypatch.setattr(CL, 'open', _open_with({'safety_state.json.4312.0a1b2c3d.tmp': gone,
                                                'safety_status_one.json.77.9f8e7d6c.tmp': gone}), raising=False)
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    assert report.unreadable == []
    assert set(members) == _expected_members() | {'bot/state/left_by_a_crash.json.99.tmp'}
    assert members['bot/state/safety_state.json'] == BOT_DATA['state/safety_state.json'].encode()


def test_a_large_file_that_fails_in_the_middle_keeps_what_was_read(export_dirs, monkeypatch):
    """Read what can be read: a day's log that fails after its first part is in the zip up to there, and
    SKIPPED.txt says how much of it that is."""
    bot, account, out = export_dirs
    monkeypatch.setattr(CL, 'WHOLE_READ_BYTES', 400)
    monkeypatch.setattr(CL, 'CHUNK_BYTES', 300)
    big = 'the first lines of the day\n' * 200
    (bot / 'logs' / f'{SYMBOL}_2026-11-22.log').write_text(big, encoding='utf-8', newline='')
    monkeypatch.setattr(CL, 'open', _open_with({f'{SYMBOL}_2026-11-22.log': 1001}), raising=False)
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    arc = f'bot/logs/{SYMBOL}_2026-11-22.log'
    assert members[arc] == big.encode()[:1001]
    assert dict(report.unreadable)[arc].startswith('only its first 1,001 bytes could be read (PermissionError')
    assert f'  {arc}: only its first 1,001 bytes' in members['SKIPPED.txt'].decode('utf-8')
    # every other large file went through the same path and is whole
    whole = f'bot/logs/{SYMBOL}_2026-11-21.log'
    assert members[whole] == BOT_DATA[f'logs/{SYMBOL}_2026-11-21.log'].encode()


def test_a_log_that_grows_while_it_is_read_gives_a_good_zip(export_dirs, monkeypatch):
    """The bot keeps writing: a file longer at the read than at the listing is taken as it is then."""
    bot, account, out = export_dirs
    monkeypatch.setattr(CL, 'WHOLE_READ_BYTES', 400)
    monkeypatch.setattr(CL, 'CHUNK_BYTES', 300)
    log = bot / 'logs' / f'{SYMBOL}_2026-11-21.log'
    more = 'a line the bot wrote meanwhile\n' * 100

    def growing_open(path, *args, **kwargs):
        if os.fspath(path) == str(log):
            with builtins.open(path, 'a', encoding='utf-8', newline='') as f:
                f.write(more)
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(CL, 'open', growing_open, raising=False)
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    members = _zip_of(report)
    assert members[f'bot/logs/{SYMBOL}_2026-11-21.log'] == (BOT_DATA[f'logs/{SYMBOL}_2026-11-21.log'] + more).encode()
    assert not report.unreadable


def test_small_files_are_closed_before_they_are_compressed(export_dirs, monkeypatch):
    """The bot replaces its JSON files every poll, and on Windows that fails while another program has the file
    open. So the export holds such a file only for the read itself: it is closed before the zip gets it."""
    bot, account, out = export_dirs
    handles = {}

    def tracking_open(path, *args, **kwargs):
        f = builtins.open(path, *args, **kwargs)
        handles[os.path.basename(os.fspath(path))] = f
        return f

    seen = {}
    real = zipfile.ZipFile.writestr

    def writestr(self, info, data, *args, **kwargs):
        name = os.path.basename(info.filename)
        if name in handles:
            seen[name] = handles[name].closed
        return real(self, info, data, *args, **kwargs)

    monkeypatch.setattr(CL, 'open', tracking_open, raising=False)
    monkeypatch.setattr(zipfile.ZipFile, 'writestr', writestr)
    CL.collect(bot, account, out, LABEL, now=NOW)
    assert seen[f'{SYMBOL}_trace.json'] is True and seen['safety_switch.json'] is True
    assert all(seen.values()) and all(f.closed for f in handles.values())


# ───────────────────────── the disk ─────────────────────────

def test_it_refuses_when_the_zip_would_leave_less_than_2_gb_free(export_dirs, monkeypatch):
    bot, account, out = export_dirs
    assert CL.MIN_FREE_BYTES == 2 * GB
    need = CL.space_needed(CL.plan(bot, account).items)
    assert need >= sum(len(t.encode()) for t in BOT_DATA.values()) + sum(len(t.encode()) for t in ACCOUNT_DATA.values())
    asked = []

    def free(folder):
        asked.append(str(folder))
        return 2 * GB + need - 1

    monkeypatch.setattr(CL, '_free_bytes', free)
    before = _snapshot(bot, account)
    with pytest.raises(CL.Refused) as refused:
        CL.collect(bot, account, out, LABEL, now=NOW)
    text = str(refused.value)
    assert '2.00 GB must stay free' in text and str(out) in text and 'run this again' in text
    assert asked == [str(out)]                                  # the disk of the exports folder is the one asked
    assert list(out.iterdir()) == [] and _snapshot(bot, account) == before
    # one byte more free: the zip is made
    monkeypatch.setattr(CL, '_free_bytes', lambda folder: 2 * GB + need)
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    assert os.path.isfile(report.zip_path)


def test_it_refuses_when_the_free_space_cannot_be_read(export_dirs, monkeypatch):
    bot, account, out = export_dirs

    def free(folder):
        raise OSError(5, 'Input/output error')

    monkeypatch.setattr(CL, '_free_bytes', free)
    with pytest.raises(CL.Refused, match='free space'):
        CL.collect(bot, account, out, LABEL, now=NOW)
    assert list(out.iterdir()) == []


def test_a_zip_that_cannot_be_finished_leaves_nothing_behind(export_dirs, monkeypatch):
    """No half-written zip that could be sent by mistake: a failed write leaves neither a .zip nor a .part."""
    bot, account, out = export_dirs

    def full_disk(src, dst, *args, **kwargs):
        raise OSError(28, 'No space left on device')

    monkeypatch.setattr(CL, '_replace_retry', full_disk)
    with pytest.raises(CL.Refused, match='could not be written'):
        CL.collect(bot, account, out, LABEL, now=NOW)
    assert list(out.iterdir()) == []


def _stamp(t):
    return time.strftime('%Y%m%d_%H%M%S', time.gmtime(t))


def test_it_keeps_the_newest_5_zips_of_its_branch_and_touches_nothing_else(export_dirs):
    bot, account, out = export_dirs
    out.mkdir()
    assert CL.KEEP_ZIPS == 5
    old = [f'{LABEL}_{_stamp(NOW - 86400 * days)}.zip' for days in range(1, 8)]          # 7 older exports
    others = [f'{LABEL}0_{_stamp(NOW - 86400 * 30)}.zip',          # another branch whose name starts the same
              f'x{LABEL}_{_stamp(NOW - 86400 * 30)}.zip',
              f'other_{_stamp(NOW - 86400 * 30)}.zip',
              f'{LABEL}_{_stamp(NOW - 86400 * 30)}.zip.bak',
              f'{LABEL}_notes.txt', f'{LABEL}_20261301_000000.zip',  # (month 13: not a date, not ours)
              f'{LABEL}_{_stamp(NOW - 86400 * 30)}.ZIP.txt', 'keep_me.zip']
    for name in old + others:
        (out / name).write_bytes(b'old')
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    new = f'{LABEL}_{_stamp(NOW)}.zip'
    assert os.path.basename(report.zip_path) == new
    assert sorted(p.name for p in out.iterdir()) == sorted([new] + old[:4] + others)
    assert sorted(report.pruned) == sorted(old[4:]) and not report.prune_failed


def test_the_newest_zips_are_chosen_by_the_time_in_the_name_not_by_the_files_age(export_dirs):
    bot, account, out = export_dirs
    out.mkdir()
    old = [f'{LABEL}_{_stamp(NOW - 3600 * hours)}.zip' for hours in range(1, 7)]
    for i, name in enumerate(old):
        (out / name).write_bytes(b'old')
        os.utime(out / name, (NOW + i * 1000, NOW + i * 1000))     # the oldest names are the newest files
    CL.collect(bot, account, out, LABEL, now=NOW)
    assert sorted(p.name for p in out.iterdir()) == sorted([f'{LABEL}_{_stamp(NOW)}.zip'] + old[:4])


def test_two_exports_in_the_same_second_are_two_zips(export_dirs):
    bot, account, out = export_dirs
    first = CL.collect(bot, account, out, LABEL, now=NOW)
    second = CL.collect(bot, account, out, LABEL, now=NOW)
    assert os.path.basename(first.zip_path) == f'{LABEL}_{_stamp(NOW)}.zip'
    assert os.path.basename(second.zip_path) == f'{LABEL}_{_stamp(NOW + 1)}.zip'
    assert _zip_of(first).keys() == _zip_of(second).keys()


def test_a_half_written_zip_of_an_interrupted_run_is_swept_after_an_hour(export_dirs):
    bot, account, out = export_dirs
    out.mkdir()
    stale = f'{LABEL}_{_stamp(NOW - 7200)}.zip.part'
    fresh = f'{LABEL}_{_stamp(NOW - 60)}.zip.part'                  # maybe another export that is still running
    foreign = f'{LABEL}0_{_stamp(NOW - 7200)}.zip.part'
    for name in (stale, fresh, foreign):
        (out / name).write_bytes(b'half')
    CL.collect(bot, account, out, LABEL, now=NOW)
    names = {p.name for p in out.iterdir()}
    assert stale not in names and {fresh, foreign} <= names


def test_the_zips_name_holds_the_branch_and_the_utc_time_and_only_safe_characters(export_dirs):
    """Spec rule 12: letters, digits, _ - . only; the time as yyyymmdd_hhmmss, UTC."""
    bot, account, out = export_dirs
    report = CL.collect(bot, account, out, LABEL, now=NOW)
    name = os.path.basename(report.zip_path)
    assert re.fullmatch(r'[A-Za-z0-9_.-]+', name)
    assert name == f'{LABEL}_{time.strftime("%Y%m%d_%H%M%S", time.gmtime(NOW))}.zip'
    for bad in ('a/b', 'a\\b', 'a:b', 'a b', '', 'a*b', '..\\x', 'a"b', 'a|b', 'a?b', 'a<b>'):
        with pytest.raises(CL.Refused):
            CL.collect(bot, account, out, bad, now=NOW)
    assert [p.name for p in out.iterdir()] == [name]


# ───────────────────────── folders that are not as expected ─────────────────────────

def test_without_a_bot_folder_nothing_is_made(tmp_path):
    out = tmp_path / 'exports'
    with pytest.raises(CL.Refused, match='does not exist'):
        CL.collect(tmp_path / 'no_such_bot', tmp_path / 'no_account', out, LABEL, now=NOW)
    assert not out.exists()
    (tmp_path / 'empty_bot').mkdir()
    with pytest.raises(CL.Refused, match='holds no logs'):
        CL.collect(tmp_path / 'empty_bot', tmp_path / 'no_account', out, LABEL, now=NOW)
    assert not out.exists()


def test_without_an_account_folder_the_bots_files_are_still_exported(export_dirs, tmp_path):
    bot, _account, out = export_dirs
    report = CL.collect(bot, tmp_path / 'no_such_account', out, LABEL, now=NOW)
    members = _zip_of(report)
    assert set(members) == {f'bot/{rel}' for rel in BOT_DATA} | {'SKIPPED.txt'}
    assert 'does not exist: nothing of it is in this zip' in members['SKIPPED.txt'].decode('utf-8')
    assert any('does not exist' in note for note in report.notes)


def test_the_zip_is_never_made_inside_a_folder_it_copies(export_dirs):
    """Or the next export would hold the last one, and a half-written zip would be read into itself."""
    bot, account, out = export_dirs
    for inside in (bot, bot / 'logs', bot / 'exports', account, account / 'zips'):
        with pytest.raises(CL.Refused, match='inside'):
            CL.collect(bot, account, inside, LABEL, now=NOW)
    assert not (bot / 'exports').exists() and not (account / 'zips').exists()
    assert not [p for p in bot.rglob('*.zip*')] and not [p for p in account.rglob('*.zip*')]


# ───────────────────────── the command line ─────────────────────────

def test_main_prints_the_full_path_of_the_zip_in_a_plain_sentence(export_dirs, capsys):
    bot, account, out = export_dirs
    code = CL.main(['--bot-dir', str(bot), '--account-dir', str(account), '--out', str(out)])
    printed = capsys.readouterr().out
    assert code == 0, printed
    zips = [p for p in out.iterdir()]
    assert len(zips) == 1 and os.path.isabs(str(zips[0]))
    assert f'The zip file is ready: {zips[0]}\n' in printed
    assert re.fullmatch(re.escape(DEFAULTS['BRANCH']) + r'_\d{8}_\d{6}\.zip', zips[0].name)
    assert f"Collecting the logs of {DEFAULTS['BRANCH']}" in printed
    assert 'It does not hold mt5_credentials.json or the safety PIN.' in printed
    assert 'Traceback' not in printed
    for secret in (SECRET, PIN, LOGIN):
        assert secret not in printed
    with zipfile.ZipFile(zips[0]) as zf:
        assert set(zf.namelist()) == _expected_members()


def test_main_says_in_one_sentence_why_nothing_was_collected(tmp_path, capsys):
    code = CL.main(['--bot-dir', str(tmp_path / 'never_started'), '--out', str(tmp_path / 'exports')])
    printed = capsys.readouterr().out
    assert code == 1
    assert 'Nothing was collected: the bot folder' in printed and 'does not exist' in printed
    assert 'Traceback' not in printed and not (tmp_path / 'exports').exists()


def test_main_tells_about_files_it_could_not_read_and_zips_it_deleted(export_dirs, capsys, monkeypatch):
    bot, account, out = export_dirs
    out.mkdir()
    branch = DEFAULTS['BRANCH']
    for days in range(1, 7):
        (out / f'{branch}_{_stamp(time.time() - 86400 * days)}.zip').write_bytes(b'old')
    monkeypatch.setattr(CL, 'open', _open_with({f'{SYMBOL}_trace.json': PermissionError(13, 'held')}),
                        raising=False)
    assert CL.main(['--bot-dir', str(bot), '--account-dir', str(account), '--out', str(out)]) == 0
    printed = capsys.readouterr().out
    assert '1 file(s) could not be read, or not to the end. They are listed in SKIPPED.txt inside the zip.' in printed
    assert f'2 older zip file(s) of {branch} were deleted: the newest 5 are kept.' in printed
    assert len([p for p in out.iterdir() if p.name.startswith(branch + '_')]) == 5


def test_the_folders_come_from_constants_through_safety_account_dir(monkeypatch, capsys):
    """Without an option the export reads the bot's own folders: OUTPUT_DIR, the account folder beside it
    (safety.account_dir, as the bot derives it) and the folder exports beside both. The disk is not touched here:
    on the server these are the real folders."""
    S = _load('safety')
    real_bot = DEFAULTS['OUTPUT_DIR']
    want = (DEFAULTS['BRANCH'], real_bot, S.account_dir(real_bot, DEFAULTS['ACCOUNT_FOLDER']),
            S.account_dir(real_bot, 'exports'))
    assert CL.folders() == want
    assert want[2] != want[1] and want[3] != want[1] and want[2] != want[3]
    calls = []

    def no_disk(bot_dir, account_dir, out_dir, branch, **kwargs):
        calls.append((branch, bot_dir, account_dir, out_dir))
        raise CL.Refused('this is a test.')

    monkeypatch.setattr(CL, 'collect', no_disk)
    assert CL.main([]) == 1
    assert calls == [want]
    assert 'Nothing was collected: this is a test.' in capsys.readouterr().out


def test_a_given_bot_folder_takes_its_account_folder_and_its_exports_from_beside_it(tmp_path):
    bot = tmp_path / 'somewhere' / 'bot_output'
    branch, bot_dir, account_dir, out_dir = CL.folders(bot_dir=str(bot))
    assert branch == DEFAULTS['BRANCH'] and bot_dir == str(bot)
    assert account_dir == str(tmp_path / 'somewhere' / DEFAULTS['ACCOUNT_FOLDER'])
    assert out_dir == str(tmp_path / 'somewhere' / 'exports')
    assert CL.folders(str(bot), str(tmp_path / 'a'), str(tmp_path / 'o'))[1:] == (str(bot), str(tmp_path / 'a'),
                                                                                str(tmp_path / 'o'))


def test_main_never_shows_a_traceback(monkeypatch, capsys, tmp_path):
    def broken(*args, **kwargs):
        raise RuntimeError('something nobody thought of')

    monkeypatch.setattr(CL, 'collect', broken)
    assert CL.main(['--bot-dir', str(tmp_path), '--out', str(tmp_path / 'o')]) == 1
    printed = capsys.readouterr().out
    assert 'Nothing was collected: something unexpected went wrong (RuntimeError: something nobody thought of)' \
        in printed
    monkeypatch.setattr(CL, 'folders', broken)
    assert CL.main([]) == 1
    assert 'the settings of this branch could not be read' in capsys.readouterr().out


# ───────────────────────── the file itself ─────────────────────────

def test_collect_logs_needs_the_standard_library_only():
    """It runs on the bare Python of the server, also when the bot's packages are broken."""
    tree = ast.parse((ROOT / 'collect_logs.py').read_text(encoding='utf-8'))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split('.')[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imported.add(node.module.split('.')[0])
    assert imported and imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
    # constants.py and safety.py of the branch are loaded from their files, by name
    source = (ROOT / 'collect_logs.py').read_text(encoding='utf-8')
    assert "_load('constants'), _load('safety')" in source


def test_collect_logs_never_names_the_servers_folders_itself():
    """The folders come from constants.py: no path of the server is written into the code (a docstring may name
    one as an example)."""
    tree = ast.parse((ROOT / 'collect_logs.py').read_text(encoding='utf-8'))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and ast.get_docstring(node) is not None:
            docstrings.add(id(node.body[0].value))
    texts = [node.value for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]
    assert len(texts) > 50
    for text in texts:
        assert 'alcadeias\\' not in text.lower() and 'c:\\' not in text.lower(), text[:80]
