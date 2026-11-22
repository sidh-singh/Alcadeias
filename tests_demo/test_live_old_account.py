"""
The old-account check.

Every real-money branch is pushed with the credentials of the OLD bot of its account, and the MetaTrader 5 that
file names is logged into exactly that old account today. A new bot started on the untouched file would find "its"
account in the terminal, pass every later check -- the number and the server of the credentials, real, hedging --
and trade the old account with real money, beside the old ladder bot. So, before any terminal call:
  * the bot refuses a "live" block whose account NUMBER is one the old bots traded (constants.OLD_LOGINS_SHA256:
    the numbers as SHA-256, never in clear), whatever else of the block was edited -- the password, the server,
    the terminal_path, an added key, the number typed as text;
  * only the owner can change the file: the job ends with EXIT_NEEDS_OWNER and one line that says what to put
    where (the first thing a new server must show him: README, "First start", step 3);
  * the one way to keep an old account on purpose is "keep_old_account": true in the block -- exactly the JSON
    value true.
(The stand-in files are made here: the branch's own mt5_credentials.json is never read by a test.)
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from conftest import BRANCH, DEFAULTS, ROOT, F, account_folder, boot_text, stand_in_files, start_job
from conftest import found

OLD = 43210987                              # the account the old bot of this branch traded (a number of this file)
OLD_OTHER = 55501234                        # ... and the old account of another one of the owner's accounts
NEW = F.ACCOUNT_LOGIN                       # the new account: the one the fake terminal holds
PARTNER = DEFAULTS['PARTNER_BRANCH']
SECRET = 'S3cret-Pa55-of-a-test'
OLD_BLOCK = {'terminal_path': F.TERMINAL_PATH, 'login_id': OLD, 'login_pass': SECRET, 'server': 'Old-Real7'}


def _mods(mods, held=OLD, server='Old-Real7'):
    """The bot's modules on a terminal that holds `held` (as on the server today: the old account), with the old
    accounts' fingerprints as the generator stamps them."""
    m = mods()
    sha = m.app.safety.login_sha
    m.app.OLD_LOGINS_SHA256 = m.constants.OLD_LOGINS_SHA256 = (sha(OLD), sha(OLD_OTHER))
    m.fake.account_login, m.fake.server = held, server
    return m


def _refused(m, bot, reached, capsys):
    """The start ended with 78 before any terminal call, and its last line is the old-account line."""
    out = capsys.readouterr().out
    last = out.strip().splitlines()[-1]
    assert bot.exit_code == m.app.EXIT_NEEDS_OWNER == 78 and not reached
    assert m.fake.calls == [] and m.fake.orders == []               # nothing reached the terminal
    assert bot.credentials is None and bot._login is None           # ... and the bot is left without an account
    assert 'still names the old account' in last
    return out, last


def test_the_untouched_file_is_refused_before_any_terminal_call(mods, capsys):
    """The terminal holds the old account, the file names it, the number and the server match, it is a real hedging
    USD account: every other check would pass. The bot never attaches."""
    m = _mods(mods)
    opened = stand_in_files(m, credentials=OLD_BLOCK)
    bot, reached = start_job(m)
    out, last = _refused(m, bot, reached, capsys)
    folder = ROOT.resolve()
    assert last == (
        f'✗ mt5_credentials.json in {folder} still names the old account (...0987) this branch was created with. '
        f"Put the new account's login_id, login_pass and server in its \"live\" block (and terminal_path, if this "
        f'account has its own MetaTrader 5), the same values in {BRANCH} and {PARTNER}, pull the change on this '
        f'server and start again. Only if this branch must really trade that old account: add "keep_old_account": '
        f'true to the "live" block, and make sure the old bot of that account is stopped.')
    assert opened.count('mt5_credentials.json') == 3                # the same answer at all three attempts
    assert out.count(last) == 2                                     # said when first met, and as the last word
    line = bot._boot_lines[-1]
    assert line[1:3] == ('ERROR', 'START') and line[4] == {'exit_code': 78, 'needs_owner': 'OLD_ACCOUNT'}
    # the number itself, the password and the fingerprints are in no line of the console or the log
    sha = m.app.safety.login_sha
    for text in (out, boot_text(bot)):
        assert not found(text, str(OLD)) and not found(text, SECRET) and not found(text, sha(OLD)) and not found(text, sha(OLD_OTHER))
    assert not account_folder(m).exists() and not (account_folder(m).parent / 'terminal_claims').exists()


@pytest.mark.parametrize('edit', [
    {'login_id': str(OLD)},                                         # the number typed as text
    {'login_id': f'  {OLD} '},
    {'terminal_path': r'C:\MT5 of the new account\terminal64.exe'},     # only terminal_path edited
    {'terminal_path': 'C:/fake/terminal64.exe'},
    {'login_pass': ''},                                             # the password blanked (the repository is public)
    {'login_pass': 'the-new-password'},                             # only the password changed
    {'server': 'New-Real9'},                                        # only the server changed
    {'server': '  old-real7 '},
    {'note': 'edited on GitHub', 'keep': 1},                        # an extra key
    {'keep_old_account': False},
    {'keep_old_account': 'true'},                                   # text, not the JSON value true
    {'keep_old_account': 1},
    {'keep_old_account': None},
    {'KEEP_OLD_ACCOUNT': True},                                     # another key
    {'login_id': OLD_OTHER},                                        # the block of another of the old accounts pasted in
])
def test_any_edit_that_keeps_an_old_account_number_is_still_refused(mods, capsys, edit):
    """The check that hashed the whole block passed after any of these edits, while the number -- and so the
    account the bot would trade -- was still the old one."""
    held = edit.get('login_id', OLD) if isinstance(edit.get('login_id', OLD), int) else OLD
    m = _mods(mods, held=held, server=str(edit.get('server', 'Old-Real7')).strip())
    F.INSTALLED.add(r'C:\MT5 of the new account\terminal64.exe')
    try:
        stand_in_files(m, credentials=dict(OLD_BLOCK, **edit))
        bot, reached = start_job(m)
        out, last = _refused(m, bot, reached, capsys)
    finally:
        F.INSTALLED.discard(r'C:\MT5 of the new account\terminal64.exe')
    tail = '...' + str(edit.get('login_id', OLD)).strip()[-4:]
    assert f'still names the old account ({tail})' in last and not found(out, str(held))


@pytest.mark.parametrize('edit', [
    {'terminal_path': ''},                                          # the rest of the block could not be used either
    {'terminal_path': None},
    {'server': ''},
    {'terminal_path': r'C:\No MetaTrader here\terminal64.exe'},     # (no such file: on a PC without MetaTrader 5 too)
    {'drop': 'terminal_path'},
    {'drop': 'server'},
])
def test_the_old_account_is_said_before_anything_else_of_the_block_is_judged(mods, capsys, edit):
    """The account number decides first: an old number is THE thing to change, whatever else of the block is
    missing or wrong -- and on a PC that has no MetaTrader 5 at all (the independent branch check, README "First
    start" step 3 on a new server) the line is still the old-account line."""
    m = _mods(mods)
    block = dict(OLD_BLOCK)
    if 'drop' in edit:
        del block[edit['drop']]
    else:
        block.update(edit)
    stand_in_files(m, credentials=block)
    bot, reached = start_job(m)
    out, last = _refused(m, bot, reached, capsys)
    assert not found(out, 'cannot be used') and not found(out, 'does not name a file')
    assert bot._credentials_problem == 'it still names the old account ...0987'


def test_a_login_id_that_is_no_account_number_is_not_taken_for_an_old_one(mods, capsys):
    """(Only an account number can be an old account's; anything else is the "cannot be used" refusal.)"""
    m = _mods(mods)
    stand_in_files(m, credentials=dict(OLD_BLOCK, login_id=f'{OLD}x'))
    bot, reached = start_job(m)
    out = capsys.readouterr().out
    assert bot.exit_code == 78 and not reached and m.fake.calls == []
    assert not found(out, 'old account') and 'cannot be used: login_id must be the account number' in out


def test_the_key_order_and_the_layout_of_the_file_do_not_matter(mods, capsys):
    m = _mods(mods)
    text = ('{\r\n\t"live": {"server": "Old-Real7",\r\n\t\t"login_pass": "%s", "login_id": %d,'
            '\r\n\t\t"terminal_path": "C:\\\\fake\\\\terminal64.exe"}\r\n}\r\n' % (SECRET, OLD))
    stand_in_files(m, credentials=text)
    bot, reached = start_job(m)
    _refused(m, bot, reached, capsys)


def test_the_new_account_in_the_file_starts(mods, capsys):
    """The owner did what the line says: the new account's number, password and server, the terminal logged into it
    by hand. Nothing of the old-account check is left in the way."""
    m = _mods(mods, held=NEW, server=F.ACCOUNT_SERVER)
    stand_in_files(m, credentials=F.CREDS)
    bot, reached = start_job(m)
    assert reached and not found(capsys.readouterr().out, 'old account')
    assert bot._login == NEW


def test_the_new_account_in_the_file_while_the_terminal_still_holds_the_old_one_is_left_alone(mods, capsys):
    """Day one, in the order of the README: the file is corrected first, the terminal still holds the old account.
    The bot does not log in over it (it would switch the old bot's account under it): TERMINAL_IN_USE, exit 1, and
    it starts by itself once the owner has logged the terminal into the new account."""
    m = _mods(mods, held=OLD, server='Old-Real7')
    stand_in_files(m, credentials=F.CREDS)
    bot, reached = start_job(m)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY and bot._init_problem.startswith('TERMINAL_IN_USE: ')
    assert 'login' not in [c[0] for c in m.fake.calls] and m.fake.account_login == OLD
    assert '(...0987 on Old-Real7)' in capsys.readouterr().out
    m.fake.account_login, m.fake.server = NEW, F.ACCOUNT_SERVER    # logged in by hand
    bot, reached = start_job(m)                                     # the launcher's next start
    assert reached


def test_keep_old_account_true_lets_the_branch_trade_its_old_account(mods, capsys):
    """The one way out, for an owner who really keeps an old account on a branch: exactly "keep_old_account": true.
    Every other check still applies (here: the terminal holds that account, a real hedging USD account)."""
    m = _mods(mods)
    opened = stand_in_files(m, credentials=dict(OLD_BLOCK, keep_old_account=True))
    bot, reached = start_job(m)
    assert reached and bot._login == OLD and bot.credentials['keep_old_account'] is True
    assert opened.count('mt5_credentials.json') == 1
    assert not found(capsys.readouterr().out, 'still names the old account')


def test_a_bot_given_old_credentials_by_hand_attaches_to_nothing(mods, capsys):
    """Behind the load: whoever gives a bot its credentials (a script, a replay), initialize_mt5 itself refuses an
    old account before any terminal call -- at the start and on a reconnect."""
    m = _mods(mods)
    run = F.Run()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', run, credentials=OLD_BLOCK)
    bot.mt5_initialized, bot.position_helper = False, None
    for reconnect in (False, True):
        assert bot.initialize_mt5(reconnect=reconnect) is False and m.fake.calls == []
        assert 'still names the old account (...0987)' in bot._init_problem
    assert 'Refused before attaching to any terminal' in capsys.readouterr().out
    bot.credentials = dict(OLD_BLOCK, keep_old_account=True)
    assert bot._old_account_problem() is None and bot.initialize_mt5() is True


def test_an_account_that_is_no_old_one_is_not_refused_by_this_check(mods):
    m = _mods(mods, held=NEW, server=F.ACCOUNT_SERVER)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    assert bot._old_account_problem() is None
    bot.credentials = None
    assert bot._old_account_problem() is None                       # (no credentials: that is another refusal)


def test_a_list_of_old_accounts_that_cannot_be_used_refuses_every_account(mods):
    """A harness that left the constant damaged (the start itself refuses such a branch as not finished by the
    generator: test_live_needs_owner.py): the check does not pass by accident."""
    m = _mods(mods, held=NEW, server=F.ACCOUNT_SERVER)
    m.app.OLD_LOGINS_SHA256 = None
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    bot.mt5_initialized, bot.position_helper = False, None
    assert 'not finished by the generator' in bot._old_account_problem()
    assert bot.initialize_mt5() is False and m.fake.calls == []


def test_the_fingerprints_are_of_the_number_as_a_whole_number(mods):
    """What the generator stamps and what the bot compares: safety.login_sha, the SHA-256 of the digits -- the same
    for 43210987, '43210987' and ' 43210987 '."""
    import hashlib
    sha = mods().app.safety.login_sha
    want = hashlib.sha256(str(OLD).encode('ascii')).hexdigest()
    assert sha(OLD) == sha(str(OLD)) == sha(f' {OLD} ') == want
    assert re.fullmatch(r'[0-9a-f]{64}', want) and sha(OLD) != sha(OLD_OTHER)


# ───────────────────────────── the whole thing, as a process ─────────────────────────────

def test_the_first_start_on_a_server_prints_the_old_account_line_and_ends_with_78(tmp_path):
    """README, "First start", step 3, as it really happens: `app.py live --symbol X` as a process of its own, in a
    copy of the branch that holds a credentials file with an old account number, and a MetaTrader5 module that
    notes every call it gets. The process prints the line, ends with 78, and never called the terminal.
    (In the copy: the output folder and the list of old accounts are the test's, and the 5 s between two start
    attempts are 0.05 s; nothing else differs from the branch's files.)"""
    copy = tmp_path / 'branch'
    copy.mkdir()
    for name in ('app.py', 'mt5_helper.py', 'indicator.py', 'strategy.py', 'turtle.py', 'safety.py', 'symbols.json'):
        shutil.copy(ROOT / name, copy / name)
    import hashlib
    constants = (ROOT / 'constants.py').read_text(encoding='utf-8')
    out_dir = tmp_path / 'out' / 'bot_output'
    constants, n1 = re.subn(r"(?m)^OUTPUT_DIR = .*$", lambda _: f'OUTPUT_DIR = {str(out_dir)!r}', constants)
    constants, n2 = re.subn(r"(?m)^OLD_LOGINS_SHA256 = .*$",
                            lambda _: f"OLD_LOGINS_SHA256 = ({hashlib.sha256(str(OLD).encode()).hexdigest()!r},)",
                            constants)
    assert (n1, n2) == (1, 1)
    (copy / 'constants.py').write_text(constants, encoding='utf-8')
    app = (copy / 'app.py').read_text(encoding='utf-8')
    assert app.count('_START_RETRY_S = 5.0') == 1
    (copy / 'app.py').write_text(app.replace('_START_RETRY_S = 5.0', '_START_RETRY_S = 0.05'), encoding='utf-8')
    (copy / 'mt5_credentials.json').write_text(json.dumps({'live': OLD_BLOCK}, indent=4), encoding='utf-8')
    (copy / 'MetaTrader5.py').write_text(            # every name is there (a constant, a function); a CALL is noted
        'import os\n'
        'def __getattr__(name):\n'
        '    if name.startswith("__"):\n'
        '        raise AttributeError(name)\n'
        '    def call(*a, **k):\n'
        '        with open(os.path.join(os.path.dirname(__file__), "terminal_was_called.txt"), "a") as f:\n'
        '            f.write(name + "\\n")\n'
        '    return call\n', encoding='utf-8')
    symbol = json.loads((ROOT / 'symbols.json').read_text(encoding='utf-8-sig'))['symbols'][0]['symbol']
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    done = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-u', 'app.py', 'live', '--symbol', symbol], cwd=copy,
                          env=env, capture_output=True, text=True, encoding='utf-8', timeout=300)
    assert done.returncode == 78, (done.stdout[-3000:], done.stderr[-3000:])
    last = done.stdout.strip().splitlines()[-1]
    assert last.startswith(f'✗ mt5_credentials.json in {copy.resolve()} still names the old account (...0987)')
    assert not (copy / 'terminal_was_called.txt').exists()          # no terminal call at all
    assert not found(done.stdout, str(OLD)) and not found(done.stdout, SECRET) and not found(done.stderr, 'Traceback')
    # what it left behind: its own folder (the lock file, the start block of the log), nothing beside it
    assert sorted(p.name for p in (tmp_path / 'out').iterdir()) == ['bot_output']
    written = '\n'.join(p.read_text(encoding='utf-8', errors='replace')
                        for p in out_dir.rglob('*') if p.is_file())
    assert not found(written, str(OLD)) and not found(written, SECRET)
