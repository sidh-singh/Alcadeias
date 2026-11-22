"""
The state files of a real-money bot say which account they were written on.

A bot folder may meet another account: the owner moves an account to a new number, or copies a folder. The open
basket or Turtle trade its state file describes is then in the OTHER account -- matched against this account's
positions it would be booked as closed outside the bot, with a result and a loss pause that are not this
account's. So every state file records the account (its SHA-256 and its tail, never the number) and the branch:
state/<SYMBOL>_state.json, the Turtle's book file (beside the book: the book itself is turtle.py's and takes no
other key), the Turtle's side file, state/live_start.json. At load:
  * another account's file is renamed aside -- <name>.other-account-<yyyymmdd_hhmmss>, UTC -- and not used; the
    existing rebuild from the bot's own positions takes over; one event STATE_OTHER_ACCOUNT, and when the file held
    an open basket or trade the owner is told that its positions may still be open in the other account;
  * a file without the field is this bot's (written before the field existed); if the rename fails the file is
    left and still not used; loading never raises.
The account is compared as the SHA-256 of the number as a whole number, so credentials that spell it as text
("12345678") are the same account: a restart keeps every file.

state/live_start.json is when this bot first traded this account: the reporting reads (the trades list, the
history summary) start a day before it. Nothing the bot decides on reads it.
"""
import hashlib
import json
import os
import re

import pytest

import test_turtle_bot as TB
from conftest import BRANCH, DEFAULTS, F, MAGIC, SCALED, START, account_folder, market, run_bot, stand_in_files, start_job
from conftest import found

SHA = hashlib.sha256(str(F.ACCOUNT_LOGIN).encode('ascii')).hexdigest()
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]
OTHER = 87654321
OTHER_SHA = hashlib.sha256(str(OTHER).encode('ascii')).hexdigest()
STAMP = {'branch': BRANCH, 'login_sha': SHA, 'login_tail': TAIL}
BASKET = {'side': 'BUY', 'units': 2, 'ids': [100001], 'first_time': 1.0, 'opened_at': 1.0, 'opened_by': 'bot',
          'target_usd_per_unit': 5.0, 'stop_usd_per_unit': 5.0, 'gap_px': 0.0, 'vol_unit': 1.0}
WIDE = dict(SCALED, MAX_ADDS=0, TARGET_VOL=10000.0, STOP_VOL=10000.0)       # a basket that stays open
SAFE_NAME = re.compile(r'[A-Za-z0-9_.-]+')


def _bot(mods, tmp_path, symbol='XAUUSDm', credentials=None, **overrides):
    m = mods(**overrides)
    run = F.Run()
    bot = F.make_bot(m, m.fake, symbol, run, state_dir=tmp_path / 'state', credentials=credentials)
    return m, bot, run


def _other(events):
    return [e for e in events if e['event'] == 'STATE_OTHER_ACCOUNT']


def _asides(folder):
    return sorted(p.name for p in folder.iterdir() if '.other-account-' in p.name)


# ───────────────────────────── what the files record ─────────────────────────────

def test_the_basket_state_file_records_its_account_and_branch(mods, tmp_path):
    m, bot, run = _bot(mods, tmp_path)
    state = {'basket': dict(BASKET), 'last_close': {'time': 5.0, 'pnl': -1.0, 'lost': True}}
    bot._save_state('XAUUSDm', state)
    path = tmp_path / 'state' / 'XAUUSDm_state.json'
    doc = json.loads(path.read_text())
    assert {k: doc[k] for k in STAMP} == STAMP and doc['magic'] == MAGIC and doc['symbol'] == 'XAUUSDm'
    assert doc['basket'] == BASKET and not found(path.read_text(), str(F.ACCOUNT_LOGIN))
    # what the loop gets back is the state as before: the stamp is the file's, not the basket's
    assert bot._load_state('XAUUSDm') == state and not run.events


def test_the_turtles_book_file_records_them_beside_the_book(mods, tmp_path):
    """The book is turtle.py's: it takes no other key and has none. The account is at the level where the file keeps
    its magic number."""
    m, bot, run = _bot(mods, tmp_path, symbol=TB.SYMBOL, **TB.TURTLE)
    book = dict(TB.T.new_state(), side=1, units=2, entry_time=1000.0, legs=[{'price': 1.0, 'time': 1000.0, 'ticket': 11}])
    bot._save_turtle_state(TB.SYMBOL, book)
    path = tmp_path / 'state' / f'{TB.SYMBOL}_turtle.json'
    doc = json.loads(path.read_text())
    assert {k: doc[k] for k in STAMP} == STAMP and doc['system'] == 2 and doc['magic'] == MAGIC
    assert set(doc['book']) == set(TB.T.new_state()) and not set(STAMP) & set(doc['book'])
    assert not found(path.read_text(), str(F.ACCOUNT_LOGIN))
    loaded = bot._load_turtle_state(TB.SYMBOL)
    assert set(loaded) == set(TB.T.new_state()) and loaded['side'] == 1 and loaded['units'] == 2 and not run.events


def test_the_side_file_and_the_live_start_record_them_too(mods, tmp_path):
    m, bot, run = _bot(mods, tmp_path, symbol=TB.SYMBOL, **TB.TURTLE)
    bot._save_turtle_side(TB.SYMBOL, {'entry_time': 1.0, 'ticket': 11, 'side': 1, 'units': 1, 'sizing': None})
    bot._note_live_start(TB.SYMBOL, None, None, {'balance': 1500.0})
    for name in (f'{TB.SYMBOL}_turtle_side.json', 'live_start.json'):
        doc = json.loads((tmp_path / 'state' / name).read_text())
        assert {k: doc[k] for k in STAMP} == STAMP, name
        assert not found((tmp_path / 'state' / name).read_text(), str(F.ACCOUNT_LOGIN))


# ───────────────────────────── a file of another account ─────────────────────────────

def _write_state(tmp_path, name, doc):
    folder = tmp_path / 'state'
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(doc))
    return folder / name


def _basket_doc(basket, sha=OTHER_SHA, tail='...4321', **more):
    doc = {'version': 1, 'symbol': 'XAUUSDm', 'magic': MAGIC, 'design': 'x', 'saved_at': 1.0, 'basket': basket,
           'last_close': {'time': 5.0, 'pnl': -9.0, 'lost': True}, 'branch': 'some_branch'}
    if sha is not None:
        doc.update(login_sha=sha, login_tail=tail)
    return dict(doc, **more)


def test_a_basket_state_of_another_account_is_put_aside_and_the_owner_is_told_about_its_trade(mods, tmp_path, capsys):
    m, bot, run = _bot(mods, tmp_path)
    doc = _basket_doc(dict(BASKET))
    path = _write_state(tmp_path, 'XAUUSDm_state.json', doc)
    t = m.clock.time()
    assert bot._load_state('XAUUSDm') is None                       # not used: the loop rebuilds from its positions
    assert not path.exists()
    aside = path.with_name('XAUUSDm_state.json.other-account-20261117_080000')     # yyyymmdd_hhmmss, UTC
    assert _asides(path.parent) == [aside.name] and json.loads(aside.read_text()) == doc
    (event,) = _other(run.events)
    assert event['tag'] == 'ERROR'
    d = event['details']
    assert d['problem'] == (
        "This bot's saved trade belongs to account ...4321. If its positions are still open there, close them by hand. "
        f"(The file XAUUSDm_state.json was written on account ...4321, not on this bot's {TAIL}: it was put aside as "
        f'{aside.name}, and the bot starts without it.)')
    assert (d['file'], d['set_aside_as'], d['file_login_tail'], d['own_login_tail'], d['held_open_trade']) == (
        'XAUUSDm_state.json', aside.name, '...4321', TAIL, True)
    assert d['file_branch'] == 'some_branch' and d['problem'] in capsys.readouterr().out
    assert not found(json.dumps(run.events), str(OTHER)) and not found(json.dumps(run.events), str(F.ACCOUNT_LOGIN))
    assert m.clock.time() == t                                      # (no waiting in the load)


def test_a_state_of_another_account_without_an_open_trade_is_put_aside_without_that_warning(mods, tmp_path):
    m, bot, run = _bot(mods, tmp_path)
    path = _write_state(tmp_path, 'XAUUSDm_state.json', _basket_doc(None))
    assert bot._load_state('XAUUSDm') is None and not path.exists() and len(_asides(path.parent)) == 1
    d = _other(run.events)[0]['details']
    assert d['held_open_trade'] is False and 'saved trade' not in d['problem']
    assert d['problem'].startswith(f"The file XAUUSDm_state.json was written on account ...4321, not on this bot's {TAIL}: ")


@pytest.mark.parametrize('side, banner', [(1, True), (-1, True), (0, False)])
def test_a_turtle_book_of_another_account_is_put_aside(mods, tmp_path, side, banner):
    m, bot, run = _bot(mods, tmp_path, symbol=TB.SYMBOL, **TB.TURTLE)
    book = dict(TB.T.new_state(), side=side, units=1 if side else 0)
    doc = {'version': 1, 'symbol': TB.SYMBOL, 'magic': MAGIC, 'design': 'x', 'system': 2, 'saved_at': 1.0,
           'branch': 'some_branch', 'login_sha': OTHER_SHA, 'login_tail': '...4321', 'book': book}
    path = _write_state(tmp_path, f'{TB.SYMBOL}_turtle.json', doc)
    assert bot._load_turtle_state(TB.SYMBOL) is None and not path.exists()
    assert _asides(path.parent) == [f'{TB.SYMBOL}_turtle.json.other-account-20261117_080000']
    d = _other(run.events)[0]['details']
    assert d['held_open_trade'] is banner
    assert d['problem'].startswith("This bot's saved trade belongs to account ...4321.") is banner


def test_a_file_without_the_account_is_this_bots(mods, tmp_path):
    """Written before the field existed (or by a replay without it): accepted, as the spec of the state files says."""
    m, bot, run = _bot(mods, tmp_path)
    path = _write_state(tmp_path, 'XAUUSDm_state.json', _basket_doc(dict(BASKET), sha=None))
    assert bot._load_state('XAUUSDm')['basket'] == BASKET and path.exists() and not run.events


def test_the_same_account_is_this_bots_however_the_credentials_spell_its_number(mods, tmp_path):
    m, bot, run = _bot(mods, tmp_path, credentials=F.account_credentials(login_id=f' {F.ACCOUNT_LOGIN} '))
    path = _write_state(tmp_path, 'XAUUSDm_state.json', _basket_doc(dict(BASKET), sha=SHA, tail=TAIL))
    assert bot._load_state('XAUUSDm')['basket'] == BASKET and path.exists() and not run.events


def test_a_file_that_cannot_be_renamed_is_left_and_still_not_used(mods, tmp_path, capsys):
    """Another program holds the file (the log export reads it this moment): the bot does not use it and goes on;
    its next save writes over it."""
    m, bot, run = _bot(mods, tmp_path)
    path = _write_state(tmp_path, 'XAUUSDm_state.json', _basket_doc(dict(BASKET)))

    def refused(src, dst):
        raise PermissionError(13, 'The process cannot access the file because it is being used by another process')
    m.app._replace_retry = refused
    assert bot._load_state('XAUUSDm') is None and path.exists() and _asides(path.parent) == []
    d = _other(run.events)[0]['details']
    assert d['set_aside_as'] is None and 'left where it is and not used (it could not be renamed: PermissionError' in d['problem']
    assert d['held_open_trade'] is True and 'close them by hand' in capsys.readouterr().out


@pytest.mark.parametrize('sha', [12345, ['x'], {'a': 1}, '', None, True])
def test_an_account_field_that_is_no_fingerprint_never_raises(mods, tmp_path, sha):
    m, bot, run = _bot(mods, tmp_path)
    doc = _basket_doc(dict(BASKET), sha=None)
    doc['login_sha'] = sha
    path = _write_state(tmp_path, 'XAUUSDm_state.json', doc)
    assert bot._load_state('XAUUSDm')['basket'] == BASKET and path.exists() and not run.events


@pytest.mark.parametrize('error', [RecursionError('maximum recursion depth exceeded'), MemoryError(),
                                   UnicodeDecodeError('utf-8', b'\xe4', 0, 1, 'invalid start byte'), KeyError('x')])
def test_loading_a_state_file_never_raises_whatever_the_read_meets(mods, tmp_path, error):
    """The loads run before the poll loop, outside its try: an exception there would end the job, and the launcher
    would start it again into the same exception every 30 s, with its trades unmanaged. Whatever the read meets,
    the file is not used and the loop starts (the book or the basket is rebuilt from the bot's own positions)."""
    m, bot, run = _bot(mods, tmp_path, symbol=TB.SYMBOL, **TB.TURTLE)
    _write_state(tmp_path, f'{TB.SYMBOL}_state.json', _basket_doc(dict(BASKET), sha=SHA, tail=TAIL, symbol=TB.SYMBOL))
    _write_state(tmp_path, f'{TB.SYMBOL}_turtle.json', {'symbol': TB.SYMBOL, 'magic': MAGIC, 'system': 2,
                                                      'book': dict(TB.T.new_state())})
    _write_state(tmp_path, f'{TB.SYMBOL}_turtle_side.json', {'symbol': TB.SYMBOL, 'magic': MAGIC, 'trade': {}})
    _write_state(tmp_path, 'live_start.json', {'time': 1.0})

    def fails(*a, **k):
        raise error
    m.app.json = type('json', (), {'load': staticmethod(fails), 'loads': staticmethod(fails),
                                   'dump': json.dump, 'dumps': json.dumps, 'JSONDecodeError': json.JSONDecodeError})
    assert bot._load_state(TB.SYMBOL) is None
    assert bot._load_turtle_state(TB.SYMBOL) is None
    assert bot._load_turtle_side(TB.SYMBOL) is None
    assert bot._load_live_start(TB.SYMBOL) is None
    assert _asides(tmp_path / 'state') == []                        # nothing put aside: nothing was judged


def test_a_bot_without_credentials_puts_nothing_aside(mods, tmp_path):
    """It has no account to compare with (and trades nothing: the guard refuses every poll)."""
    m, bot, run = _bot(mods, tmp_path)
    bot.credentials = None
    path = _write_state(tmp_path, 'XAUUSDm_state.json', _basket_doc(dict(BASKET)))
    assert bot._load_state('XAUUSDm') is not None and path.exists() and not run.events


# ───────────────────────────── in the loop ─────────────────────────────

def test_the_rebuild_from_the_bots_own_positions_takes_over(tmp_path):
    """The folder holds the basket state of another account (2 units, other positions). This account has one
    position of this bot (1 unit). The file is put aside and the loop does what it does without a file: it takes
    the basket over from the terminal -- 1 unit, from its own position -- and books nothing as closed outside."""
    fake, clock = market(20)
    ticket = fake.add_position(0, 0.01, 1999.0, START - 3000, magic=MAGIC)
    _write_state(tmp_path, 'XAUUSDm_state.json', _basket_doc(dict(BASKET, ids=[777001, 777002])))
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path / 'state')
    assert not [e for e in run.errors if 'saved trade belongs' not in e]
    assert len(_other(run.events)) == 1 and _other(run.events)[0]['details']['held_open_trade'] is True
    state = json.loads((tmp_path / 'state' / 'XAUUSDm_state.json').read_text())
    assert state['basket']['opened_by'] == 'rebuild' and state['basket']['units'] == 1 and state['basket']['ids'] == [ticket]
    assert state['last_close'] is None or state['last_close'].get('reason') != 'closed_outside'
    assert {k: state[k] for k in STAMP} == STAMP                    # ... and the new file is this account's
    assert fake.orders == [] and len(fake.positions) == 1          # nothing was closed, nothing opened
    assert _asides(tmp_path / 'state') == ['XAUUSDm_state.json.other-account-20261117_080000']


def test_a_restart_keeps_every_state_file_when_the_login_is_text_in_the_credentials(tmp_path):
    """The basket loop: the file has the number as a whole number, then the owner types it in quotes and the bot
    restarts inside an open basket. Nothing is put aside, the basket is the one of the file (not rebuilt), the live
    start is not written again."""
    fake, clock = market(60, restarts=[30])
    fake.add_position(0, 0.02, 1999.0, START - 3000, magic=MAGIC)
    seen = {}

    def on_new_bot(bot, n):
        if n == 1:
            seen['state'] = (tmp_path / 'XAUUSDm_state.json').read_text()
            seen['live'] = (tmp_path / 'live_start.json').read_text()
            bot.credentials = F.account_credentials(fake, login_id=f'{F.ACCOUNT_LOGIN}')
            assert bot.credentials['login_id'] == F.ACCOUNT_LOGIN and bot._login == F.ACCOUNT_LOGIN
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=on_new_bot)
    assert run.restarts == 1 and not run.errors and not _other(run.events)
    # (the safety's own state file beside them; its queue of closed trades is written only once there is one)
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == [
        'XAUUSDm_state.json', 'live_start.json', 'safety_state.json']
    before, after = json.loads(seen['state']), json.loads((tmp_path / 'XAUUSDm_state.json').read_text())
    assert after['basket']['opened_at'] == before['basket']['opened_at']        # the file's basket, not a new takeover
    assert after['login_sha'] == before['login_sha'] == SHA
    assert (tmp_path / 'live_start.json').read_text() == seen['live']
    assert all(p['nb'] == 1 and p['units'] == 2 for p in run.polls)


def test_a_turtle_restart_keeps_its_book_its_side_file_and_its_live_start_when_the_login_is_text(tmp_path):
    fake, clock = TB._market(TB._long_trip(), restarts=(1000,))
    seen = {}

    def on_bot(bot, n):
        if n == 1:
            seen.update({p.name: p.read_text() for p in tmp_path.iterdir() if p.is_file()})
            bot.credentials = F.account_credentials(fake, login_id=f' {F.ACCOUNT_LOGIN} ')
    books = []
    run = TB._run(fake, clock, tmp_path, books=books, on_bot=on_bot)
    # (with the safety's own two: its Tracker's state, and the position ids of the open trade for its result)
    names = [f'{TB.SYMBOL}_turtle.json', f'{TB.SYMBOL}_turtle_side.json', 'live_start.json', 'safety_closes.json',
             'safety_state.json']
    assert run.restarts == 1 and not run.errors and sorted(seen) == sorted(names)
    assert json.loads(seen[names[0]])['book']['side'] == 1          # the restart was inside the open trade
    assert json.loads(seen['safety_closes.json'])['turtle']['ids']   # ... and its legs were kept for its result
    assert not _other(run.events) and 'TURTLE_REBUILT' not in [e['event'] for e in run.events]
    assert not [p.name for p in tmp_path.iterdir() if p.is_file() and p.name not in names]
    entry = {b['entry_time'] for b in books if b['side'] == 1}
    assert len(entry) == 1                                          # one trade, before and after the restart
    for name in names[:4]:
        assert json.loads((tmp_path / name).read_text())['login_sha'] == SHA
    assert json.loads((tmp_path / 'live_start.json').read_text()) == json.loads(seen['live_start.json'])


def test_a_turtle_folder_that_meets_another_account_starts_fresh_and_says_so(tmp_path):
    """The account moves to a new number while a Turtle trade is open: the terminal now holds the new account (no
    position of this bot there) and the bot restarts with the new credentials. The book, the side file and the live
    start of the old account are put aside; the bot is flat on the new account and does not book the old trade as
    closed; the owner is told that the old trade may still be open there."""
    fake, clock = TB._market(TB._long_trip(), restarts=(1000,))
    stash = {}

    def move(f):
        stash['positions'], f.positions = f.positions, []
        f.account_login = OTHER
    fake.at(START + 998.2, move)                                    # (seen by the old process's last polls)
    run = TB._run(fake, clock, tmp_path)
    assert run.restarts == 1
    events = _other(run.events)
    assert sorted(e['details']['file'] for e in events) == [f'{TB.SYMBOL}_turtle.json', f'{TB.SYMBOL}_turtle_side.json',
                                                           'live_start.json', 'safety_closes.json']
    held = {e['details']['file']: e['details']['held_open_trade'] for e in events}
    assert held == {f'{TB.SYMBOL}_turtle.json': True, f'{TB.SYMBOL}_turtle_side.json': False, 'live_start.json': False,
                    'safety_closes.json': False}
    assert all(e['details']['file_login_tail'] == TAIL and e['details']['own_login_tail'] == '...4321' for e in events)
    # (and the safety's two: its Tracker puts its own state of the old account aside, the queue is app.py's)
    assert len(_asides(tmp_path)) == 5 and all(SAFE_NAME.fullmatch(n) for n in _asides(tmp_path))
    assert sorted(n.split('.other-account-')[0] for n in _asides(tmp_path)) == sorted(
        [f'{TB.SYMBOL}_turtle.json', f'{TB.SYMBOL}_turtle_side.json', 'live_start.json', 'safety_closes.json',
         'safety_state.json'])
    assert 'TURTLE_CLOSED_OUTSIDE' not in [e['event'] for e in run.events]      # the old trade is not "closed"
    assert len(stash['positions']) >= 1                             # (it is still open in the old account)
    for name in (f'{TB.SYMBOL}_turtle.json', 'live_start.json'):    # what the bot wrote since is the new account's
        assert json.loads((tmp_path / name).read_text())['login_sha'] == OTHER_SHA


# ───────────────────────────── the names of the files ─────────────────────────────

def test_every_file_name_the_start_builds_is_one_windows_accepts(mods, tmp_path):
    """Letters, digits, '_', '-' and '.' only -- never < > : " / \\ | ? * (a colon in a time would make the rename
    fail on the server and pass here) -- and a time in a name is yyyymmdd_hhmmss, UTC. Everything the start-up
    hardening writes, in one folder tree: the lock, the claims, the login record, the live start, a state put
    aside, a damaged claim put aside."""
    fake, clock = market(900)
    clock.end_ms = 10 ** 15
    m = mods(fake=fake, clock=clock)
    stand_in_files(m)
    fake.login_error = (-6, 'Terminal: Authorization failed')
    fake.logged_in, fake.account_login = False, 0
    start_job(m)                                                    # a refused login: the login record
    fake.login_error, fake.logged_in, fake.account_login = None, True, F.ACCOUNT_LOGIN
    account_folder(m).mkdir(exist_ok=True)
    (account_folder(m) / 'account_claim.json').write_text('{"damaged": ')
    assert start_job(m)[1]                                          # the claims; the damaged claim put aside
    bot = F.make_bot(m, fake, 'XAUUSDm', F.Run())                   # (writes into OUTPUT_DIR/state, as on the server)
    state = os.path.join(m.app.OUTPUT_DIR, 'state')
    with open(os.path.join(state, 'XAUUSDm_state.json'), 'w') as f:
        json.dump(_basket_doc(dict(BASKET)), f)
    assert bot._load_state('XAUUSDm') is None
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})
    names = [name for _, folders, files in os.walk(tmp_path) for name in folders + files]
    for wanted in ('XAUUSDm.lock', 'terminal_claims', 'account_claim.json', 'live_start.json'):
        assert wanted in names, (wanted, sorted(names))
    assert any(re.fullmatch(r'[0-9a-f]{40}\.json', name) for name in names)             # the terminal's claim
    assert all(SAFE_NAME.fullmatch(name) for name in names), [n for n in names if not SAFE_NAME.fullmatch(n)]
    aside = sorted(name for name in names if '.other-account-' in name or '.not-readable-' in name)
    assert [re.sub(r'\d', '0', name) for name in aside] == ['XAUUSDm_state.json.other-account-00000000_000000',
                                                            'account_claim.json.not-readable-00000000_000000']
    assert all(re.search(r'-2026111[67]_\d{6}$', name) for name in aside)               # yyyymmdd_hhmmss, UTC
    a = m.app
    assert a._name_stamp(0) == '19700101_000000' and a._name_stamp(START + 86399.9) == '20261118_075959'
    assert a._file_part('BTC/USD:m*?') == 'BTC_USD_m__' and a._file_part('..') == '_' and a._file_part('') == '_'


# ───────────────────────────── state/live_start.json ─────────────────────────────

def _live(tmp_path):
    return json.loads((tmp_path / 'state' / 'live_start.json').read_text())


def _positions(*times):
    import types
    if not times:
        return None
    return {'count': len(times), 'positions': [types.SimpleNamespace(time=int(t), time_msc=int(t * 1000), ticket=k)
                                               for k, t in enumerate(times)]}


def test_the_live_start_is_written_at_the_first_good_poll_and_never_again(mods, tmp_path):
    m, bot, run = _bot(mods, tmp_path)
    assert bot._load_live_start('XAUUSDm') is None and bot._reporting_since() is None
    now = m.clock.time()
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})
    doc = _live(tmp_path)
    assert doc == {'time': now, 'time_utc': doc['time_utc'], 'account_balance': 1500.0, 'login_sha': SHA,
                   'login_tail': TAIL, 'branch': BRANCH, 'symbol': 'XAUUSDm', 'magic': MAGIC, 'written_at': now,
                   'history_read': True}
    assert doc['time_utc'].startswith('2026-11-17T08:00:0') and bot._live_start == doc
    assert bot._reporting_since() == now - 86400.0                  # where the reporting reads start
    text = (tmp_path / 'state' / 'live_start.json').read_text()
    assert not found(text, str(F.ACCOUNT_LOGIN))
    assert sorted(p.name for p in (tmp_path / 'state').iterdir()) == ['live_start.json']      # no temp file left
    # later polls, a later day, another balance, older deals arriving in the history: it is not written again
    reads = []
    deals = m.fake.history_deals_get
    m.fake.history_deals_get = lambda *a, **k: reads.append(1) or deals(*a, **k)
    m.fake.add_deal(5, 0, 0, 0.01, 2000.0, 0.0, now - 5000, MAGIC)
    m.clock.end_ms = 10 ** 15
    for _ in range(5):
        m.clock.sleep(40000)
        bot._note_live_start('XAUUSDm', _positions(now - 9000), None, {'balance': 999.0})
    assert (tmp_path / 'state' / 'live_start.json').read_text() == text and reads == []
    # ... and a restart reads it back
    m2, bot2, run2 = _bot(mods, tmp_path)
    assert bot2._load_live_start('XAUUSDm') == doc and not run2.events
    bot2._note_live_start('XAUUSDm', None, None, {'balance': 1.0})
    assert (tmp_path / 'state' / 'live_start.json').read_text() == text


def test_the_live_start_is_the_earliest_of_now_the_oldest_position_and_the_first_deal(mods, tmp_path):
    """The state folder was lost (a new server) while the bot had traded for weeks: 'now' would cut its closed trades
    out of the trades list. Its oldest open position and its first deal in the account's history say when it really
    started. The other bot's deals (another magic number) and a deposit say nothing about this bot."""
    m, bot, run = _bot(mods, tmp_path)
    now = m.clock.time()
    m.fake.add_deal(7, 0, 0, 0.01, 2000.0, 0.0, now - 40 * 86400, MAGIC + 1)       # the other bot of the account
    m.fake.add_balance_operation(1500.0, time_s=now - 50 * 86400)                # the deposit
    bot._note_live_start('XAUUSDm', _positions(now - 3600, now - 60), _positions(now - 1800), {'balance': 1500.0})
    assert _live(tmp_path)['time'] == now - 3600                    # the oldest open position
    os.remove(tmp_path / 'state' / 'live_start.json')
    bot._load_live_start('XAUUSDm')
    bot._live_start_retry_at = 0.0
    m.fake.add_deal(5, 0, 0, 0.01, 2000.0, 0.0, now - 20 * 86400, MAGIC)         # this bot's first deal, 20 days ago
    m.fake.add_deal(5, 1, 1, 0.01, 2001.0, 1.0, now - 19 * 86400, MAGIC)
    bot._note_live_start('XAUUSDm', _positions(now - 3600), None, {'balance': 1500.0})
    doc = _live(tmp_path)
    assert doc['time'] == now - 20 * 86400 and doc['history_read'] is True


def test_a_history_that_cannot_be_read_is_tried_again_later_and_only_then(mods, tmp_path):
    """One read of the deal history, after the poll's order section, in its own try. When the terminal does not
    answer it the file is written with the other two, and the read is tried again a minute later -- not on every
    poll -- until it has succeeded once. The time can only move back."""
    m, bot, run = _bot(mods, tmp_path)
    now = m.clock.time()
    m.fake.add_deal(5, 0, 0, 0.01, 2000.0, 0.0, now - 7 * 86400, MAGIC)
    reads = []
    deals = m.fake.history_deals_get
    m.fake.history_deals_get = lambda *a, **k: reads.append(m.clock.time() - now) or deals(*a, **k)
    m.fake.history_none = True
    bot._note_live_start('XAUUSDm', _positions(now - 600), None, {'balance': 1500.0})
    doc = _live(tmp_path)
    assert (doc['time'], doc['history_read'], doc['account_balance']) == (now - 600, False, 1500.0)
    for _ in range(59):                                             # the polls of the next minute: no read
        m.clock.sleep(1)
        bot._note_live_start('XAUUSDm', _positions(now - 600), None, {'balance': 1.0})
    assert reads == [0.0]
    m.clock.sleep(1)
    bot._note_live_start('XAUUSDm', None, None, {'balance': 2.0})   # a minute later: read again, still nothing
    assert reads == [0.0, 60.0] and _live(tmp_path) == doc
    m.fake.history_none = False
    m.clock.sleep(60)
    bot._note_live_start('XAUUSDm', None, None, {'balance': 3.0})
    done = _live(tmp_path)
    assert reads == [0.0, 60.0, 120.0] and done['history_read'] is True
    assert done['time'] == now - 7 * 86400 and done['account_balance'] == 1500.0     # (the first poll's balance)
    for _ in range(3):                                              # complete: nothing more, for good
        m.clock.sleep(600)
        bot._note_live_start('XAUUSDm', None, None, {'balance': 4.0})
    assert len(reads) == 3 and _live(tmp_path) == done
    # a restart while the history was still unread goes on trying
    (tmp_path / 'state' / 'live_start.json').write_text(json.dumps(doc))
    m2, bot2, run2 = _bot(mods, tmp_path)
    m2.fake.add_deal(5, 0, 0, 0.01, 2000.0, 0.0, now - 9 * 86400, MAGIC)
    assert bot2._load_live_start('XAUUSDm')['history_read'] is False
    bot2._note_live_start('XAUUSDm', None, None, {'balance': 5.0})
    assert _live(tmp_path)['time'] == now - 9 * 86400 and _live(tmp_path)['history_read'] is True


def test_the_history_read_is_inside_the_terminal_lock_and_the_file_write_outside_it(mods, tmp_path, monkeypatch):
    m, bot, run = _bot(mods, tmp_path)
    seen = []
    deals = m.fake.history_deals_get
    m.fake.history_deals_get = lambda *a, **k: seen.append(('history', bot.mt5_lock.locked())) or deals(*a, **k)
    replace = os.replace
    monkeypatch.setattr(os, 'replace', lambda s, d: seen.append(('write', bot.mt5_lock.locked())) or replace(s, d))
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})
    assert seen == [('history', True), ('write', False)]


def test_a_live_start_that_cannot_be_written_never_reaches_the_poll(mods, tmp_path, capsys):
    m, bot, run = _bot(mods, tmp_path)
    (tmp_path / 'state').write_text('a file where the state folder should be')
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})     # no exception
    assert bot._live_start is None and 'could not write' in capsys.readouterr().out
    os.remove(tmp_path / 'state')
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})     # not at once: a minute later
    assert not (tmp_path / 'state').exists()
    m.clock.sleep(60)
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})
    assert _live(tmp_path)['history_read'] is True

    def boom(*a, **k):
        raise RuntimeError('anything')
    bot._live_start = None
    bot._live_start_retry_at = 0.0
    bot._account_stamp = boom
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})     # whatever fails in it: never raised


@pytest.mark.parametrize('content', ['', '{"time": ', '[]', '{}', '{"time": "now"}', '{"time": true}'])
def test_a_live_start_file_that_holds_no_time_is_written_anew(mods, tmp_path, content):
    m, bot, run = _bot(mods, tmp_path)
    _write_state(tmp_path, 'live_start.json', {})
    (tmp_path / 'state' / 'live_start.json').write_text(content)
    assert bot._load_live_start('XAUUSDm') is None and not run.events
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})
    assert _live(tmp_path)['time'] == m.clock.time()


def test_the_live_start_of_another_account_is_put_aside_and_this_accounts_is_written(mods, tmp_path):
    m, bot, run = _bot(mods, tmp_path)
    old = {'time': 1000.0, 'account_balance': 9.0, 'login_sha': OTHER_SHA, 'login_tail': '...4321', 'branch': 'x',
           'history_read': True}
    _write_state(tmp_path, 'live_start.json', old)
    assert bot._load_live_start('XAUUSDm') is None
    assert _asides(tmp_path / 'state') == ['live_start.json.other-account-20261117_080000']
    assert _other(run.events)[0]['details']['held_open_trade'] is False
    bot._note_live_start('XAUUSDm', None, None, {'balance': 1500.0})
    doc = _live(tmp_path)
    assert doc['login_sha'] == SHA and doc['time'] == m.clock.time() and doc['account_balance'] == 1500.0


def test_the_loop_writes_the_live_start_at_its_first_poll_from_this_bots_own_position(tmp_path):
    """In the whole loop: the first poll that passed the guard writes it, from the poll's own positions read."""
    fake, clock = market(20)
    fake.add_position(0, 0.01, 1999.0, START - 3000, magic=MAGIC)
    fake.add_position(1, 0.01, 1999.0, START - 9000, magic=MAGIC + 1)           # the other bot's: not this bot's start
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path)
    # (a trade of another magic on this symbol is a warning of its own: 6.1, test_live_safety_loop.py)
    assert [e for e in run.errors if "Trades that are not this bot's" not in e] == [] and len(run.errors) == 1
    doc = json.loads((tmp_path / 'live_start.json').read_text())
    assert doc['time'] == START - 3000 and doc['history_read'] is True and doc['account_balance'] == 2000.0
    assert START <= doc['written_at'] <= START + 5                  # at the first poll, not later


def test_a_poll_the_guard_refuses_writes_no_live_start(tmp_path):
    fake, clock = market(20)
    fake.account_login = OTHER                                      # not this bot's account: every poll is refused

    def on_new_bot(bot, n):
        bot.credentials = dict(F.CREDS)
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=on_new_bot)
    assert run.polls == [] and not (tmp_path / 'live_start.json').exists()


# ───────────────────────────── the history summary starts at the live start ─────────────────────────────

def test_the_history_summary_counts_from_a_day_before_the_live_start(mods, tmp_path):
    """A report only (the dashboard's History tab). On an account that was traded before -- "keep_old_account" --
    the ten-year read would add up deals that are not this bot's live run."""
    m = mods()
    now = m.clock.time()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run(), keep_writers=True)
    for days_ago, profit in ((30, 100.0), (2, -7.0), (0.5, 3.0)):
        m.fake.add_deal(int(days_ago * 100), 1, 1, 0.01, 2000.0, profit, now - days_ago * 86400, MAGIC)
    path = os.path.join(m.app.OUTPUT_DIR, 'daily_trade', 'XAUUSDm', 'historical_summary.json')
    bot._save_historical_summary('XAUUSDm')                         # not known yet: the old window
    doc = json.load(open(path))
    assert (doc['total_deals'], doc['total_profit'], doc['period'], doc['since_utc']) == (3, 96.0, 'Last 10 years', None)
    bot._live_start = {'time': now - 86400 * 1.5}                   # this bot's live start: a day and a half ago
    bot._save_historical_summary('XAUUSDm')
    doc = json.load(open(path))
    assert (doc['total_deals'], doc['total_profit']) == (2, -4.0)   # from 2.5 days ago on
    assert doc['period'] == 'since 14 Nov 2026' and doc['since_utc'].startswith('2026-11-14T20:00:0')
