"""
Which account a MetaTrader 5 and an account folder belong to.

The account guard proves that the terminal holds the account of this bot's credentials file. Nothing in it proves
that the file names the right account: twenty files are edited by hand, and all of them arrive naming the same
terminal_path. Two small files tie things together:

  * the TERMINAL claim, <the folder OUTPUT_DIR is in>/terminal_claims/<sha1 of the path>.json: written whenever a
    bot passes the account checks on a MetaTrader 5. A bot of ANOTHER account never logs in there, also when that
    terminal shows no account for a minute (after a restart): its login would switch the first account's bots off.
  * the ACCOUNT claim, <account folder>/account_claim.json: made once, by the first bot of the account that passes
    the account checks. At every start after them: a claim that names another account -- the two branches of the
    account hold different credentials, or the block of another account was pasted in -- is something only the
    owner can change (78), and so is another account's folder on this server that names this bot's account.

Both hold the account as its SHA-256 and its tail, never the number; both are written whole or not at all, outside
mt5_lock; a missing, half-written or unreadable one never raises.
"""
import hashlib
import json
import os
import re
import threading

import pytest

from conftest import (BRANCH, DEFAULTS, F, account_folder, boot_text, market, names_calls, stand_in_files,
                      start_job)
from conftest import found

TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]
PARTNER = DEFAULTS['PARTNER_BRANCH']
SLOT = DEFAULTS['ACCOUNT_SLOT']
OTHER_SLOT = SLOT % 10 + 1                  # another of the owner's accounts (never this branch's own number)
OTHER_LOGIN = 87654321                      # ... and the account its bots trade
OTHER_PATH = r'C:\MT5 of another account\terminal64.exe'


def _sha(login):
    return hashlib.sha256(str(login).encode('ascii')).hexdigest()


def _terminal_claim(m, path=F.TERMINAL_PATH):
    return json.loads(open(m.app._terminal_claim_path(path), encoding='utf-8').read())


def _account_claim_path(m):
    return account_folder(m) / 'account_claim.json'


def _account_claim(m):
    return json.loads(_account_claim_path(m).read_text(encoding='utf-8'))


def _as_the_other_account(m, tmp_path):
    """The bot's modules become a bot of ANOTHER account on the same server: its own branch, account number, account
    folder and output folder (beside the first one's, as C:\\Alcadeias\\<branch> is)."""
    m.app.BRANCH, m.app.PARTNER_BRANCH = f'other{OTHER_SLOT}_a', f'other{OTHER_SLOT}_b'
    m.app.ACCOUNT_SLOT, m.app.ACCOUNT_FOLDER = OTHER_SLOT, f'live{OTHER_SLOT}_account'
    m.app.OUTPUT_DIR = str(tmp_path / 'other_bot_output')
    return dict(F.CREDS, login_id=OTHER_LOGIN)


def _world(mods, seconds=900):
    fake, clock = market(seconds)
    clock.end_ms = 10 ** 15
    return mods(fake=fake, clock=clock)


# ───────────────────────────── the terminal claim ─────────────────────────────

def test_a_bot_that_passes_the_account_checks_notes_the_terminal_as_its_accounts(mods, tmp_path):
    m = _world(mods)
    stand_in_files(m)
    t0 = m.clock.time()
    bot, reached = start_job(m)
    assert reached
    folder = tmp_path / 'terminal_claims'                           # beside the bot's own folder
    name = hashlib.sha1(r'c:\fake\terminal64.exe'.encode()).hexdigest() + '.json'
    assert [p.name for p in folder.iterdir()] == [name]             # ... and no temp file left
    claim = _terminal_claim(m)
    assert claim == {'login_sha': _sha(F.ACCOUNT_LOGIN), 'login_tail': TAIL, 'account': SLOT, 'branch': BRANCH,
                     'at': t0, 'at_utc': claim['at_utc'], 'server': F.ACCOUNT_SERVER, 'terminal_path': F.TERMINAL_PATH}
    assert not found((folder / name).read_text(), str(F.ACCOUNT_LOGIN))


@pytest.mark.parametrize('spelling', ['C:/fake/terminal64.exe', 'c:\\FAKE\\Terminal64.EXE', ' C:\\fake\\terminal64.exe ',
                                      'C:\\fake\\.\\terminal64.exe', 'C:\\\\fake\\\\terminal64.exe'])
def test_the_same_terminal_spelt_another_way_is_the_same_claim(mods, spelling):
    """The two branches of an account may spell the path differently; the claim is by the path as the terminal
    reads it."""
    a = mods().app
    assert a._terminal_claim_path(spelling) == a._terminal_claim_path(F.TERMINAL_PATH)
    assert a._terminal_claim_path(OTHER_PATH) != a._terminal_claim_path(F.TERMINAL_PATH)
    assert re.fullmatch(r'[0-9a-f]{40}\.json', os.path.basename(a._terminal_claim_path(spelling)))


def test_no_login_on_a_terminal_that_another_accounts_bots_have_claimed(mods, tmp_path, capsys):
    """Two accounts whose files name one terminal_path (they all arrive like that). The first account's bots run on
    it. The terminal restarts and shows no account for the minute: the other account's bot -- a password in its
    file, no refused login behind it -- must NOT log in: it would take the terminal, and the first account's bots
    would sit refused with their trades open. It says whose MetaTrader 5 this is, and ends with 1."""
    m = _world(mods)
    stand_in_files(m)
    assert start_job(m)[1]                                          # the first account's bot: the terminal is its
    m.fake.logged_in, m.fake.account_login = False, 0               # ... which now restarts, and shows no account
    calls = len(m.fake.calls)
    stand_in_files(m, credentials=_as_the_other_account(m, tmp_path))
    events = []
    capsys.readouterr()
    bot, reached = start_job(m, events=events)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY and m.fake.logins == []
    assert names_calls(m.fake)[calls:] == ['initialize', 'shutdown'] * 3
    text = (f'MetaTrader 5 at {F.TERMINAL_PATH} is not logged into any account. Log it into ...4321 by hand (File > '
            f'Login to Trade Account, Save password). The bot does not log in itself: this MetaTrader 5 belongs to '
            f'account {SLOT} ({TAIL}). It looks again every 30 seconds.')
    assert bot._init_problem == f'LOGIN_WAIT: {text}' and f'✗ Not logging in: {text}' in capsys.readouterr().out
    assert [e['event'] for e in events] == ['LOGIN_WAIT']
    d = events[0]['details']
    assert (d['why'], d['claimed_by_account'], d['claimed_by_branch'], d['claimed_login_tail']) == (
        'terminal_claimed', SLOT, BRANCH, TAIL)
    assert not (tmp_path / f'live{OTHER_SLOT}_account').exists()    # no login was made: nothing to remember
    assert _terminal_claim(m)['login_sha'] == _sha(F.ACCOUNT_LOGIN)      # the claim is still the first account's


def test_the_bots_of_the_claiming_account_may_log_in_there(mods):
    """The same restart, seen by a bot of the account the terminal belongs to: it logs in (its other rules allow
    it), and the claim stays its account's."""
    m = _world(mods)
    stand_in_files(m)
    assert start_job(m)[1]
    m.fake.logged_in, m.fake.account_login = False, 0
    m.app.BRANCH, m.app.PARTNER_BRANCH = PARTNER, BRANCH            # (the other bot of the same account)
    bot, reached = start_job(m)
    assert reached and [g['ok'] for g in m.fake.logins] == [True] and m.fake.account_login == F.ACCOUNT_LOGIN
    claim = _terminal_claim(m)
    assert (claim['login_sha'], claim['branch']) == (_sha(F.ACCOUNT_LOGIN), PARTNER)


def test_a_terminal_nobody_has_claimed_may_be_logged_in(mods, tmp_path):
    m = _world(mods)
    m.fake.logged_in, m.fake.account_login = False, 0
    stand_in_files(m)
    assert not (tmp_path / 'terminal_claims').exists()
    bot, reached = start_job(m)
    assert reached and len(m.fake.logins) == 1 and _terminal_claim(m)['login_tail'] == TAIL


@pytest.mark.parametrize('content', ['', '{"login_sha": ', '[]', '{}', '{"login_sha": null}', '{"login_sha": 12}',
                                     None])
def test_a_claim_that_cannot_be_read_allows_no_login(mods, content):
    """Whose terminal it is cannot be told: no login. (It never raises; and the first bot that passes the account
    checks there -- the owner logs the terminal in by hand -- writes the claim anew.)"""
    m = _world(mods)
    path = m.app._terminal_claim_path(F.TERMINAL_PATH)
    os.makedirs(os.path.dirname(path))
    if content is None:
        os.mkdir(path)                                              # (a folder in its place: the open is refused)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    m.fake.logged_in, m.fake.account_login = False, 0
    stand_in_files(m)
    bot, reached = start_job(m)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY and m.fake.logins == []
    assert 'the file that says which account this MetaTrader 5 belongs to cannot be read right now' in bot._init_problem
    if content is not None:
        m.fake.logged_in, m.fake.account_login = True, F.ACCOUNT_LOGIN      # logged in by hand
        assert start_job(m)[1] and _terminal_claim(m)['login_sha'] == _sha(F.ACCOUNT_LOGIN)


def test_a_terminal_logged_into_another_account_by_hand_becomes_that_accounts(mods, tmp_path):
    """The owner gives the terminal to another account (he logs it in by hand): that account's bot passes the checks
    there and the claim is its account's from then on."""
    m = _world(mods)
    stand_in_files(m)
    assert start_job(m)[1]
    m.fake.account_login = OTHER_LOGIN                              # by hand
    stand_in_files(m, credentials=_as_the_other_account(m, tmp_path))
    bot, reached = start_job(m)
    assert reached and m.fake.logins == []
    claim = _terminal_claim(m)
    assert (claim['login_sha'], claim['login_tail'], claim['account']) == (_sha(OTHER_LOGIN), '...4321', OTHER_SLOT)


def test_a_claim_that_cannot_be_written_does_not_stop_the_bot(mods):
    m = _world(mods)
    stand_in_files(m)
    write = m.app._write_json_atomic

    def refused(path, data):
        if 'terminal_claims' in str(path):
            raise PermissionError(13, 'Permission denied')
        return write(path, data)
    m.app._write_json_atomic = refused
    bot, reached = start_job(m)
    assert reached and 'could not note this MetaTrader 5' in boot_text(bot)


# ───────────────────────────── the account claim ─────────────────────────────

def test_the_first_bot_of_an_account_claims_its_folder_and_the_second_finds_it(mods, capsys):
    m = _world(mods)
    stand_in_files(m)
    t0 = m.clock.time()
    bot, reached = start_job(m)
    assert reached
    claim = _account_claim(m)
    assert claim == {'login_sha': _sha(F.ACCOUNT_LOGIN), 'login_tail': TAIL, 'server': F.ACCOUNT_SERVER,
                     'set_at': claim['set_at'], 'set_t': t0, 'by': BRANCH, 'account': SLOT}
    assert claim['set_at'].startswith('2026-11-17T08:00:0')
    assert sorted(p.name for p in account_folder(m).iterdir()) == ['account_claim.json']       # no temp file left
    assert not found(_account_claim_path(m).read_text(), str(F.ACCOUNT_LOGIN))
    assert f"account {SLOT}'s folder {account_folder(m)} now belongs to account {TAIL}" in capsys.readouterr().out
    # the other bot of the account, and this one again an hour later: the claim is found, and never rewritten
    before = _account_claim_path(m).read_bytes()
    m.clock.sleep(3600)
    m.app.BRANCH, m.app.PARTNER_BRANCH = PARTNER, BRANCH
    assert start_job(m)[1]
    m.app.BRANCH, m.app.PARTNER_BRANCH = BRANCH, PARTNER
    assert start_job(m)[1]
    assert _account_claim_path(m).read_bytes() == before
    assert not found(capsys.readouterr().out, 'now belongs to')


def test_the_two_bots_of_an_account_on_different_accounts(mods, capsys):
    """The gold branch's file got the new account, the BTC branch's file another one (a typing mistake, a block
    pasted from another account), each with a MetaTrader 5 that holds it: both would run, each on its own account at
    half size, sharing one safety folder -- one bot's block would stop the other, and the account rules would follow
    two balances. The second bot finds the folder claimed for another account and does not start: 78, and the line
    says both accounts, who set the claim, and what to do."""
    m = _world(mods)
    stand_in_files(m)
    assert start_job(m)[1]                                          # the gold bot: the folder is its account's
    m.clock.sleep(86400 * 3)
    m.app.BRANCH, m.app.PARTNER_BRANCH = PARTNER, BRANCH            # the BTC bot of the same account ...
    F.INSTALLED.add(OTHER_PATH)
    try:
        m.fake.account_login = OTHER_LOGIN                          # ... on a MetaTrader 5 that holds another account
        stand_in_files(m, credentials=dict(F.CREDS, login_id=OTHER_LOGIN, terminal_path=OTHER_PATH))
        calls = len(m.fake.calls)
        capsys.readouterr()
        bot, reached = start_job(m)
    finally:
        F.INSTALLED.discard(OTHER_PATH)
    assert bot.exit_code == m.app.EXIT_NEEDS_OWNER == 78 and not reached and m.fake.orders == []
    assert names_calls(m.fake)[calls:] == ['initialize', 'shutdown'] * 3     # attached, checked, let go: no login
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == (
        f"✗ {PARTNER} is set to account ...4321, but account {SLOT}'s folder belongs to {TAIL} (set 17 Nov 2026 by "
        f'{BRANCH}). Both bots of an account use one account: correct mt5_credentials.json. If account {SLOT} really '
        f'moves to a new account: stop both bots, run "safety.bat new-account", start again.')
    assert bot._boot_lines[-1][4]['exit_code'] == 78
    assert _account_claim(m)['login_sha'] == _sha(F.ACCOUNT_LOGIN)      # the claim is untouched
    assert not os.path.exists(m.app._terminal_claim_path(OTHER_PATH))   # and its terminal was not noted as this account's
    assert not found(boot_text(bot), str(OTHER_LOGIN)) and not found(boot_text(bot), str(F.ACCOUNT_LOGIN))


def test_the_same_number_on_another_server_is_another_account(mods, capsys):
    m = _world(mods)
    stand_in_files(m)
    assert start_job(m)[1]
    m.fake.server = 'Fake-Real9'
    stand_in_files(m, credentials=dict(F.CREDS, server='Fake-Real9'))
    bot, reached = start_job(m)
    assert bot.exit_code == 78 and not reached
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert (f"{BRANCH} is set to account {TAIL} on Fake-Real9, but account {SLOT}'s folder belongs to {TAIL} on "
            f'{F.ACCOUNT_SERVER} (set ') in last


def test_an_account_that_the_folder_of_another_account_already_holds(mods, tmp_path, capsys):
    """The whole block of another account pasted into this branch (number, password, server, path): this branch's
    bots would attach to that account's MetaTrader 5, pass every check and trade it -- four bots each sizing from
    half the balance. That account's folder on this server names the account: 78, and no claim is made here."""
    m = _world(mods)
    other = tmp_path / f'live{OTHER_SLOT}_account'
    other.mkdir()
    (other / 'account_claim.json').write_text(json.dumps({
        'login_sha': _sha(F.ACCOUNT_LOGIN), 'login_tail': TAIL, 'server': F.ACCOUNT_SERVER.upper(),
        'set_at': '2026-11-10T09:00:00+00:00', 'set_t': 1794300000.0, 'by': f'other{OTHER_SLOT}_a',
        'account': OTHER_SLOT}))
    stand_in_files(m)
    bot, reached = start_job(m)
    assert bot.exit_code == m.app.EXIT_NEEDS_OWNER == 78 and not reached and m.fake.orders == []
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith(f'✗ Account {TAIL} is already traded by the bots of account {OTHER_SLOT} on this server. '
                           f'{BRANCH} belongs to account {SLOT}: ')
    assert not account_folder(m).exists()                           # a wrong account never becomes this folder's


@pytest.mark.parametrize('what', ['another number', 'another server', 'no claim', 'damaged', 'not an account folder'])
def test_what_another_accounts_folder_holds_that_is_no_conflict(mods, tmp_path, what):
    """Another account's folder that names another number, or this number on another server (another account), that
    has no claim yet or a damaged one, and a folder that is no account folder at all: this bot starts, and claims
    its own folder."""
    m = _world(mods)
    name = 'notes_account' if what == 'not an account folder' else f'live{OTHER_SLOT}_account'
    other = tmp_path / name
    other.mkdir()
    claim = {'login_sha': _sha(F.ACCOUNT_LOGIN), 'login_tail': TAIL, 'server': F.ACCOUNT_SERVER, 'by': 'x'}
    if what == 'another number':
        claim['login_sha'] = _sha(OTHER_LOGIN)
    elif what == 'another server':
        claim['server'] = 'Fake-Real9'
    if what == 'damaged':
        (other / 'account_claim.json').write_text('{"login_sha": "')
    elif what != 'no claim':
        (other / 'account_claim.json').write_text(json.dumps(claim))
    stand_in_files(m)
    bot, reached = start_job(m)
    assert reached and _account_claim(m)['login_sha'] == _sha(F.ACCOUNT_LOGIN)


def test_another_accounts_folder_is_named_by_its_number_also_when_its_claim_does_not_say_it(mods, tmp_path):
    m = _world(mods)
    other = tmp_path / f'LIVE{OTHER_SLOT}_Account'                  # (Windows does not mind the letter case)
    other.mkdir()
    (other / 'account_claim.json').write_text(json.dumps({'login_sha': _sha(F.ACCOUNT_LOGIN), 'by': 'x'}))
    stand_in_files(m)
    bot, reached = start_job(m)
    assert bot.exit_code == 78 and not reached
    assert f'is already traded by the bots of account {OTHER_SLOT} on this server' in bot._owner_verdict[1]


def test_safety_bat_new_account_lets_the_folder_move_to_a_new_account(mods, capsys):
    """An account really moves to a new number: both bots stopped, `safety.bat new-account` (it deletes the claim),
    both files corrected. The first bot that starts claims the folder for the new account."""
    m = _world(mods)
    stand_in_files(m)
    assert start_job(m)[1]
    m.fake.account_login = OTHER_LOGIN
    stand_in_files(m, credentials=dict(F.CREDS, login_id=OTHER_LOGIN))
    bot, reached = start_job(m)
    assert bot.exit_code == 78 and 'run "safety.bat new-account"' in capsys.readouterr().out
    ok, _ = m.app.safety.press(str(account_folder(m)), 'new-account', None, 'command line', m.clock.time(),
                               need_pin=False)
    assert ok and not _account_claim_path(m).exists()
    bot, reached = start_job(m)
    assert reached and _account_claim(m)['login_sha'] == _sha(OTHER_LOGIN) and _account_claim(m)['login_tail'] == '...4321'


@pytest.mark.parametrize('content', ['', '{"login_sha": "abc', '[1]', '{}', '{"login_sha": "not a fingerprint"}'])
def test_a_claim_file_that_holds_no_account_is_put_aside_and_made_anew(mods, content, capsys):
    """A damaged file must not leave a bot down with its trades open, and cannot be asked anything: it is kept under
    another name and the claim is made anew (the account guard itself does not depend on it)."""
    m = _world(mods)
    account_folder(m).mkdir()
    _account_claim_path(m).write_text(content)
    stand_in_files(m)
    bot, reached = start_job(m)
    assert reached and _account_claim(m)['login_sha'] == _sha(F.ACCOUNT_LOGIN)
    names = sorted(p.name for p in account_folder(m).iterdir())
    assert names == ['account_claim.json', 'account_claim.json.not-readable-20261117_080000']
    assert (account_folder(m) / names[1]).read_text() == content
    assert 'held no account: put aside as account_claim.json.not-readable-20261117_080000' in capsys.readouterr().out


def test_a_claim_that_cannot_be_read_this_moment_fails_the_attempt_and_is_tried_again(mods):
    m = _world(mods)
    account_folder(m).mkdir()
    _account_claim_path(m).mkdir()                                  # (a folder in its place: the open is refused)
    stand_in_files(m)
    bot, reached = start_job(m)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY and bot._owner_verdict is None
    assert 'cannot be read this moment' in bot._init_problem and names_calls(m.fake) == ['initialize', 'shutdown'] * 3


def test_a_claim_that_cannot_be_made_is_a_warning_and_the_bot_starts(mods, capsys):
    """The account folder cannot be written (a full disk, Windows refuses): the bot holds the account of its
    credentials all the same -- it starts, and the next start tries the claim again."""
    m = _world(mods)
    stand_in_files(m)

    def refused(path, data):
        raise PermissionError(13, 'Permission denied')
    m.app._create_json_exclusive = refused
    bot, reached = start_job(m)
    assert reached and not _account_claim_path(m).exists()
    assert 'the bot goes on; the next start tries again' in capsys.readouterr().out


def test_a_running_bot_that_reconnects_is_not_stopped_by_a_claim(mods):
    """The claim is the start's check. A running bot that loses the terminal reconnects to its account whatever the
    folder's claim says by then: it holds trades, and its own account guard is what protects them."""
    m = _world(mods)
    run = F.Run()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', run)
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5() is True and _account_claim(m)['by'] == BRANCH
    _account_claim_path(m).write_text(json.dumps({'login_sha': _sha(OTHER_LOGIN), 'login_tail': '...4321',
                                                  'server': F.ACCOUNT_SERVER, 'by': 'someone', 'set_t': 1.0}))
    t0 = m.clock.time()
    m.fake.down(t0 + 0.5, t0 + 30.5)
    for _ in range(200):
        m.clock.sleep(1)
        if bot._poll_guard('XAUUSDm') and m.clock.time() > t0 + 31:
            break
    assert bot.mt5_initialized and run.events[-1]['event'] == 'TERMINAL_RECONNECTED'
    assert bot._owner_verdict is None
    bot.mt5_initialized, bot.position_helper = False, None         # ... and the next START is refused on it
    assert bot.initialize_mt5() is False and bot._owner_verdict[0].startswith('ACCOUNT_CLAIM ')


# ───────────────────────────── written whole or not at all ─────────────────────────────

def test_two_bots_making_the_claim_in_the_same_instant_make_one(mods, tmp_path):
    """The gold and the BTC bot of an account start together: both find no claim, both try to make it. Exactly one
    does; the file is whole whenever it exists."""
    a = mods().app
    for round_no in range(40):
        path = str(tmp_path / f'round{round_no}' / 'account_claim.json')
        made, seen, go = [], [], threading.Event()

        def bot(k):
            go.wait()
            made.append(a._create_json_exclusive(path, {'by': f'bot{k}', 'pad': 'x' * 2000}))
            seen.append(a._read_json_file(path))
        threads = [threading.Thread(target=bot, args=(k,)) for k in range(4)]
        for t in threads:
            t.start()
        go.set()
        for t in threads:
            t.join()
        assert sorted(made) == [False, False, False, True]
        assert all(status == 'ok' and data['pad'] == 'x' * 2000 for status, data in seen)     # never half a file
        assert os.listdir(os.path.dirname(path)) == ['account_claim.json']                    # no temp file left


def test_the_claim_is_made_once_also_on_a_disk_without_hard_links(mods, tmp_path, monkeypatch):
    a = mods().app
    path = str(tmp_path / 'f' / 'account_claim.json')

    def no_links(src, dst):
        raise OSError(95, 'Operation not supported')
    monkeypatch.setattr(os, 'link', no_links)
    assert a._create_json_exclusive(path, {'by': 'first'}) is True
    assert a._create_json_exclusive(path, {'by': 'second'}) is False
    assert a._read_json_file(path) == ('ok', {'by': 'first'}) and os.listdir(os.path.dirname(path)) == ['account_claim.json']


def test_a_small_file_is_read_without_ever_raising(mods, tmp_path):
    a = mods().app
    read = a._read_json_file
    assert read(str(tmp_path / 'none.json')) == ('missing', None)
    assert read(str(tmp_path / 'no_folder' / 'none.json')) == ('missing', None)
    (tmp_path / 'ok.json').write_text('\ufeff{"a": 1}', encoding='utf-8')          # (a byte-order mark is no fault)
    assert read(str(tmp_path / 'ok.json')) == ('ok', {'a': 1})
    for k, text in enumerate([b'', b'{"a": ', b'\xff\xfe\x00', b'nul\x00']):
        (tmp_path / f'bad{k}.json').write_bytes(text)
        assert read(str(tmp_path / f'bad{k}.json'))[0] == 'invalid'
    (tmp_path / 'folder.json').mkdir()
    assert read(str(tmp_path / 'folder.json'), tries=3)[0] == 'unreadable'
    assert read('a\x00b')[0] == 'unreadable' and read(None)[0] == 'unreadable'


def test_a_small_file_is_written_whole_under_a_temp_name_of_its_own(mods, tmp_path, monkeypatch):
    a = mods().app
    path = str(tmp_path / 'new_folder' / 'x.json')
    temps = []
    replace = os.replace

    def spy(src, dst):
        temps.append(os.path.basename(src))
        assert json.loads(open(src).read()) == {'k': len(temps)}    # complete before it is moved over the file
        return replace(src, dst)
    monkeypatch.setattr(os, 'replace', spy)
    a._write_json_atomic(path, {'k': 1})
    a._write_json_atomic(path, {'k': 2})
    assert a._read_json_file(path) == ('ok', {'k': 2}) and os.listdir(os.path.dirname(path)) == ['x.json']
    assert len(set(temps)) == 2 and all(re.fullmatch(rf'x\.json\.{os.getpid()}\.[0-9a-f]{{8}}\.tmp', t) for t in temps)

    def failing(src, dst):
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr(os, 'replace', failing)
    with pytest.raises(OSError):
        a._write_json_atomic(path, {'k': 3})
    assert a._read_json_file(path) == ('ok', {'k': 2}) and os.listdir(os.path.dirname(path)) == ['x.json']


def test_the_folders_beside_the_bots_own_are_found_by_the_rule_of_the_account_folder(mods):
    """One rule for 'the folder OUTPUT_DIR is in' (safety.account_dir): Windows rules for a Windows path on any
    system, so the raw constant never becomes a folder of that name in the working folder."""
    import ntpath
    m = mods()
    a = m.app
    here = a.OUTPUT_DIR
    assert os.path.join(a._parent_folder(), 'x') == a.safety.account_dir(here, 'x')
    assert a._account_folder() == a.safety.account_dir(here, m.constants.ACCOUNT_FOLDER)
    a.OUTPUT_DIR = r'C:\Alcadeias\some_branch'
    assert a._parent_folder() == r'C:\Alcadeias'
    assert ntpath.join(a._parent_folder(), 'x') == a.safety.account_dir(a.OUTPUT_DIR, 'x') == r'C:\Alcadeias\x'
    assert a._terminal_claim_path(F.TERMINAL_PATH).startswith('C:\\Alcadeias\\terminal_claims')
    a.OUTPUT_DIR = here
