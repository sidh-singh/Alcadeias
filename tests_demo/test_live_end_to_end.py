"""
From the bot to its files to the dashboard, end to end, with real files only (nothing in them made by hand).

A replay of the bot on the fake terminal -- the basket loop with the scaled design on test_dashboard.py's market
(seed 4: a losing basket closes at 324 s, the loss pause ends at 564 s, the next entry is wanted at 601 s) -- with the
safety ON and a small limit, until it trips. Then, at the end of the poll the dashboard would show it, the
dashboard's safety bar and status are built from the files the bot wrote -- its trace, its status file, the control
files, the block file (dashboard.JSON_DIR = the bot's OUTPUT_DIR, ACCOUNT_DIR = its account folder, the page's clock
the bot's) -- and its buttons are pressed through the dashboard's own action callback (a POST to
/_dash-update-component, as the page sends it once its question was answered with OK), with the PIN of the PIN file
safety.ensure_pin made. The bot runs on, reads what the press wrote, and the bar follows:

  * a block of this bot (1 losing trade in a row): THIS BOT BLOCKED; the entry the strategy wants is held; Unblock ->
    the bot trades again at once, and the bar is back to SAFETY ON with the count at 0;
  * a block of the account (the loss of the UTC day, limit 0.1%): ACCOUNT BLOCKED with the block file's sentence and
    numbers; Unblock -> counting again from the balance of now, the bot trades again, SAFETY ON;
  * the account blocked (the drop from the high, limit 0.1%), then Turn safety OFF -> the bot opens again although the
    block file is still there, SAFETY OFF; Turn safety ON (no PIN) -> a fresh start: the high and today's start are
    the balance of now, the count is 0, SAFETY ON;
  * 6.2 C: an old bot on this bot's MetaTrader 5 switches it to its own account while this bot holds a trade (the
    Turtle's long trip, three legs open): the red banner says so from the trace of the refused polls, with what to
    do -- stop the old bot, then log MetaTrader 5 back in --, and it goes when the account is back and the old bot
    has stopped.
"""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

import test_turtle_bot as TB
from conftest import DEFAULTS, F, MAGIC, SCALED, START, account_dir_of, market, run_bot

pytest.importorskip('dash')
pytest.importorskip('plotly')
import test_dashboard_safety as DS  # noqa: E402  (its readers of the bar: _meters, _said, _press_body, _answer)

SYMBOL = 'XAUUSDm'
BRANCH = DEFAULTS['BRANCH']
LIMITS_OFF = {'SAFETY_DROP_PCT': None, 'SAFETY_DAY_PCT': None, 'SAFETY_STREAK_N': None}
OLD_TERMINAL = r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'      # the old bots' MetaTrader 5
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]


def _bot_words(branch=BRANCH):
    """'the gold bot' / 'the BTC bot', from the branch name as the safety words it (live1_xt2 -> gold)."""
    return {'x': 'the gold bot', 'b': 'the BTC bot'}[str(branch).partition('_')[2][:1]]


def _cap(s):
    return s[:1].upper() + s[1:]


def _utc(t):
    return datetime.fromtimestamp(t, tz=timezone.utc)


def _stamp(t):
    """'17 Nov 08:05' (UTC), as the bar and the safety's sentences write a moment."""
    d = _utc(t)
    return f'{d.day} {d:%b} {d:%H:%M}'


def _money(x):
    return f'${x:,.2f}'


@pytest.fixture(scope='module')
def D():
    """dashboard.py imported from this branch (its constants.py, its safety.py), put back as it was afterwards."""
    names = ('constants', 'dashboard', 'safety')
    saved = {n: sys.modules.get(n) for n in names}
    sys.path.insert(0, str(DS.ROOT))
    try:
        for n in names:
            sys.modules.pop(n, None)
        import dashboard
        yield dashboard
    finally:
        sys.path.remove(str(DS.ROOT))
        for n in names:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


class Page:
    """The dashboard of one bot, pointed at the files of a running replay: what the page shows at a poll, and its
    buttons pressed as the browser presses them."""

    def __init__(self, D, out, symbol, clock):
        self.D, self.out, self.symbol, self.clock = D, str(out), symbol, clock
        self.acct = str(account_dir_of(out))
        D.JSON_DIR, D.ACCOUNT_DIR = self.out, self.acct
        D._now = clock.time                       # (the page's clock is the bot's: the trace's times are on it)
        self.client = D.server.test_client()
        self.pin = None

    def make_pin(self):
        """The PIN file, as a dashboard started as a program makes it (safety.ensure_pin), and the PIN read from it."""
        S = self.D.safety
        S.ensure_pin(self.acct)
        with open(S.pin_path(self.acct), encoding='utf-8-sig') as f:
            self.pin = f.read().strip()
        return self.pin

    def trace(self):
        try:
            with open(os.path.join(self.out, f'{self.symbol}_trace.json'), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def show(self):
        """Everything the page shows of the safety now, from the files: the bar (as the 5 s refresh callback draws
        it), the status callback's banners and alert, the meters, and the files the bar is drawn from."""
        D, S = self.D, self.D.safety
        for cache in (D._CACHE, D._EVENTS_CACHE, D._ERR_CACHE, D._DAY_BANNERS, D._CONFIG_CACHE):
            cache.clear()
        d = D.load(self.symbol)
        m = D.safety_state(self.symbol, d)
        head, view, cls, seen, unblock, off, on, pin_field, q_unblock, q_off, q_on = D._safety_view(1, self.symbol, None)
        status, banners, alert = D._status(1, self.symbol)
        try:
            with open(S.status_path(self.acct, BRANCH), encoding='utf-8') as f:
                status_file = json.load(f)
        except (OSError, ValueError):
            status_file = None
        hide = {'display': 'none'}
        bars = [json.loads(DS._text(b)) for b in banners if b is not None]
        return {'t': self.clock.time(), 'state': m['state'], 'label': m['label'], 'kind': m['kind'],
                'lines': list(m['lines']), 'notes': list(m['notes']), 'meters': DS._meters(m),
                'bar': DS._text([head, view]), 'cls': cls, 'seen': seen,
                'buttons': {'unblock': unblock != hide, 'off': off != hide, 'on': on != hide, 'pin': pin_field != hide},
                'questions': {'unblock': q_unblock, 'off': q_off, 'on': q_on},
                'banners': DS._said([b for b in bars if 'statebar' in str((b.get('props') or {}).get('className'))]),
                'alert': alert, 'trace': d.get('trace'), 'controls': S.read_controls(self.acct),
                'status_file': status_file,
                'blocks': sorted(n for n in (os.listdir(self.acct) if os.path.isdir(self.acct) else [])
                                 if n.startswith('safety_block_'))}

    def press(self, button, pin=None):
        """A press of `button` over HTTP, with what the bar showed (safety-seen, from the refresh callback) as the page
        sends it: (HTTP status, the result line's text, the PIN field's new value)."""
        seen = self.D._safety_view(1, self.symbol, None)[3]
        r = self.client.post('/_dash-update-component', json=DS._press_body(self.D, button, pin, seen))
        text = r.get_data(as_text=True)
        if r.status_code != 200:
            return r.status_code, text[-300:], None
        line, field = DS._answer(text)
        return 200, line, field


class Scenario:
    """Steps run in order at the end of the bot's polls (after its trace was written): each waits for its moment
    (`when(trace)`), then records what the page shows and presses a button if it has one. Nothing here raises into
    the bot's loop: a problem is kept and fails the test after the replay."""

    def __init__(self, page, fake):
        self.page, self.fake = page, fake
        self.steps, self.seen, self.problems, self.pressed = [], {}, [], {}

    def step(self, name, when, press=None):
        """press: (button, with the PIN?) pressed right after the page was recorded."""
        self.steps.append((name, when, press))

    def opened_since(self, name):
        """This bot's opening orders since the press of step `name` (none before it was pressed)."""
        t = self.pressed.get(name)
        return [] if t is None else _opens(self.fake, after=t)

    def on_new_bot(self, bot, n):
        real = bot._trace

        def spy(symbol, method, *a, **k):
            real(symbol, method, *a, **k)
            if method in ('poll', 'poll_skipped') and self.steps:
                try:
                    self._next()
                except Exception as e:  # noqa: BLE001 -- kept, and the test fails after the replay
                    self.problems.append(f'{type(e).__name__}: {e}')
                    self.steps = []
        bot._trace = spy

    def _next(self):
        name, when, press = self.steps[0]
        tr = self.page.trace()
        if tr is None or not when(tr):
            return
        self.steps.pop(0)
        self.seen[name] = self.page.show()
        if press is not None:
            button, with_pin = press
            self.pressed[name] = self.page.clock.time()
            self.seen[name]['press'] = self.page.press(button, self.page.pin if with_pin else None)
            self.seen[name]['after_press'] = self.page.D.safety.read_controls(self.page.acct)


def _state(tr):
    return (tr.get('safety') or {}).get('state')


def _held_entry(tr):
    h = tr.get('open_hold') or {}
    return h.get('kind') == 'entry' and h.get('why') == 'safety'


def _opens(fake, after=None):
    return [o for o in fake.orders if 'position' not in o and (after is None or o['_t_ms'] / 1000.0 >= after)]


def _replay(D, tmp_path, limits, build, seconds=760):
    """The scaled basket design on test_dashboard.py's market with the real writers, the safety ON at `limits` and
    the PIN file made; build(scenario) gives the steps. (the fake terminal, the page, the scenario)"""
    out = tmp_path / 'bot_output'
    fake, clock = market(seconds, seed=4)
    page = Page(D, out, SYMBOL, clock)
    page.make_pin()
    sc = Scenario(page, fake)
    build(sc)
    names = [s[0] for s in sc.steps]
    run_bot(fake, clock, overrides={**SCALED, **LIMITS_OFF, **limits, 'OUTPUT_DIR': str(out), 'SAFETY_DEFAULT_ON': True},
            state_dir=out / 'state', keep_writers=True, on_new_bot=sc.on_new_bot)
    assert not sc.problems, sc.problems
    assert list(sc.seen) == names, f'the replay reached {list(sc.seen)} of {names}'
    return fake, page, sc


def _first_close(fake):
    """The first basket's close: (the time of its closing deals, the account balance after them)."""
    outs = sorted((d for d in fake.deals if d.entry == 1 and d.magic == MAGIC), key=lambda d: d.time_msc)
    first_t = outs[0].time_msc
    legs = [d for d in outs if abs(d.time_msc - first_t) < 1000]
    return first_t / 1000.0, round(2000.0 + sum(d.profit for d in legs), 2)


def _audit(page):
    with open(os.path.join(page.acct, 'safety_audit.jsonl'), encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]


def _presses(page):
    """The audit lines of the presses made on the page (the bots' own lines aside)."""
    return [a for a in _audit(page) if str(a.get('by', '')).startswith('dashboard ')]


def _no_open_between(fake, t0, t1):
    return [o for o in _opens(fake, after=t0) if o['_t_ms'] / 1000.0 < t1]


# ───────────────────────────── a block of this bot: losing trades in a row ─────────────────────────────

@pytest.mark.slow
def test_a_block_of_this_bot_reaches_the_bar_from_the_bots_files_and_unblock_on_the_page_lets_it_trade(D, tmp_path):
    def build(sc):
        sc.step('blocked', lambda tr: _state(tr) == 'bot_blocked')
        sc.step('held', lambda tr: _state(tr) == 'bot_blocked' and _held_entry(tr), press=('safety-unblock', True))
        sc.step('trading', lambda tr: _state(tr) == 'on' and bool(sc.opened_since('held')))
    fake, page, sc = _replay(D, tmp_path, {'SAFETY_STREAK_N': 1}, build)
    t_close, balance = _first_close(fake)
    blocked, held, trading = sc.seen['blocked'], sc.seen['held'], sc.seen['trading']
    # ── blocked: what the bot wrote, and the bar drawn from it ──
    st = blocked['status_file']
    assert (st['state'], st['bot_blocked'], st['account_blocked'], st['period']) == ('bot_blocked', True, False, 'start')
    since = st['since']
    assert 0 <= since - t_close < 15                       # (counted once the deal history showed the result)
    assert (blocked['state'], blocked['label'], blocked['kind'], blocked['cls']) == (
        'bot_blocked', 'THIS BOT BLOCKED', 'neg', 'safetybar sb-neg')
    assert blocked['lines'][0].startswith(f'{_cap(_bot_words())} opens no new trade since {_stamp(since)}: it lost 1 '
                                          'trade in a row (limit 1). Its open trade keeps its stop and target.')
    assert blocked['buttons'] == {'unblock': True, 'off': True, 'on': False, 'pin': True}
    assert blocked['questions']['unblock'].startswith(f'Unblock {_bot_words()}? Its count of losing trades goes back '
                                                      'to 0.')
    drop, day, streak = blocked['meters']
    assert (drop[1], day[1]) == ('off', 'off') and 'this rule is off' in drop[2] and 'this rule is off' in day[2]
    assert streak[:3] == ('Losing trades in a row (this bot)', '1 of 1', 'a winning trade sets it back to 0')
    assert 'prog-red' in streak[4]
    assert blocked['alert'] and 'THIS BOT BLOCKED' in json.dumps(blocked['alert'])        # (banner, sound, notice)
    assert blocked['controls']['block'] is None and blocked['blocks'] == []        # (no account block file)
    assert blocked['seen'] == {'period': 'start', 'enabled': True, 'scope': 'bot'}
    # ── the entry the strategy wanted while blocked was held, nothing was sent; Unblock pressed on the page ──
    pressed = sc.pressed['held']
    assert held['state'] == 'bot_blocked' and held['trace']['open_hold']['why'] == 'safety'
    assert not _no_open_between(fake, t_close + 0.5, pressed)
    status, line, field = held['press']
    assert (status, field) == (200, '')
    assert (f'Unblocked at {_utc(pressed):%H:%M:%S} UTC: losing trades in a row start again from 0. The account\'s '
            "high and today's start are unchanged.") in line
    after = held['after_press']
    assert after['period'] not in ('start', None) and after['scope'] == 'bot' and after['enabled'] is True
    presses = _presses(page)
    assert len(presses) == 1 and presses[0]['by'] == f'dashboard {BRANCH} from 127.0.0.1'
    assert page.pin not in [str(v) for a in _audit(page) for v in a.values()]   # (never the PIN)
    # ── the bot trades again at once, and the bar is back to SAFETY ON with the count at 0 ──
    first = sc.opened_since('held')[0]
    assert first['_t_ms'] / 1000.0 - pressed < 5.0
    assert (trading['state'], trading['label'], trading['kind'], trading['cls']) == ('on', 'SAFETY ON', 'pos',
                                                                                     'safetybar sb-pos')
    assert trading['lines'] == [f'Watching account {TAIL}. New trades are allowed.']
    assert trading['meters'][2][:2] == ('Losing trades in a row (this bot)', '0 of 1')
    assert trading['buttons'] == {'unblock': False, 'off': True, 'on': False, 'pin': True}
    assert trading['status_file']['period'] == after['period'] and trading['status_file']['bot_blocked'] is False
    assert not [b for b in trading['banners'] if b[0] == 'statebar statebar-red']
    assert trading['trace']['account']['balance'] == pytest.approx(balance)
    # every state file of the real-money layer the bot wrote names the account and the branch (spec 3.5; the
    # safety's own state the fingerprint and the branch, spec 5.4) -- the journal's state among them
    state = tmp_path / 'bot_output' / 'state'
    sha = D.safety.login_sha(F.ACCOUNT_LOGIN)
    want = {f'{SYMBOL}_state.json': True, 'live_start.json': True, 'safety_closes.json': True,
            f'{SYMBOL}_journal_state.json': True, 'safety_state.json': False}
    unstamped = []
    for name, with_tail in want.items():
        doc = json.loads((state / name).read_text(encoding='utf-8'))
        if (doc.get('branch'), doc.get('login_sha')) != (BRANCH, sha) or (with_tail and doc.get('login_tail') != TAIL):
            unstamped.append(name)
    assert not unstamped, unstamped


# ───────────────────────────── a block of the account: the loss of the day ─────────────────────────────

@pytest.mark.slow
def test_an_account_block_reaches_the_bar_with_the_block_files_numbers_and_unblock_counts_from_now(D, tmp_path):
    def build(sc):
        sc.step('blocked', lambda tr: _state(tr) == 'account_blocked')
        sc.step('held', lambda tr: _state(tr) == 'account_blocked' and _held_entry(tr),
                press=('safety-unblock', True))
        sc.step('trading', lambda tr: _state(tr) == 'on' and bool(sc.opened_since('held')))
    fake, page, sc = _replay(D, tmp_path, {'SAFETY_DAY_PCT': 0.1}, build)
    t_close, balance = _first_close(fake)
    lost = round((2000.0 - balance) / 2000.0 * 100.0, 6)
    assert lost >= 0.1                                        # (the market: the first basket loses more than 0.1 %)
    blocked, held, trading = sc.seen['blocked'], sc.seen['held'], sc.seen['trading']
    # ── the block file the bot made, and the bar drawn from it ──
    assert blocked['blocks'] == ['safety_block_start.json']
    blk = blocked['controls']['block']
    assert blk is not None and blk['rules'] == ['DAY']
    st = blocked['status_file']
    assert (st['state'], st['account_blocked'], st['bot_blocked']) == ('account_blocked', True, False)
    since = st['since']
    assert 0 <= since - t_close < 15
    assert (blocked['state'], blocked['label'], blocked['kind'], blocked['cls']) == (
        'account_blocked', 'ACCOUNT BLOCKED', 'neg', 'safetybar sb-neg')
    assert blocked['lines'][0] == (f'Both bots open no new trade and add nothing to open trades since {_stamp(since)}. '
                                   'Open trades keep their stop and target. Press Unblock to trade again.')
    day_text = f'{_utc(START).day} {_utc(START):%b}'
    reason = (f'The account lost {lost:.1f}% on {day_text}, UTC day (limit 0.1%): balance {_money(balance)}, '
              f'{_money(2000.0)} when counting started that day at {_utc(START):%H:%M}.')
    assert reason in blocked['lines'], blocked['lines']
    assert f'{_cap(_bot_words())} ({BRANCH}) saw it.' in blocked['lines']
    drop, day, streak = blocked['meters']
    assert day[0] == 'Loss today (account, UTC day)' and day[1] == f'{lost:.1f}% of the 0.1% limit'
    assert day[2].startswith(f'balance {_money(balance)} · {_money(2000.0)} ')
    assert day[2].endswith(f'blocked at {_money(2000.0 * (1 - 0.001))}') and 'prog-red' in day[4]
    assert day[3].startswith('the numbers of the block') and 'they stay until Unblock' in day[3]
    assert drop[1] == 'off' and streak[1] == 'off'
    assert blocked['buttons'] == {'unblock': True, 'off': True, 'on': False, 'pin': True}
    assert blocked['questions']['unblock'].startswith(f'Unblock account {TAIL}? Counting starts again from now for both '
                                                      f'bots: the high becomes the balance of now ({_money(balance)})')
    assert blocked['alert'] and 'ACCOUNT BLOCKED' in json.dumps(blocked['alert'])
    # ── the wanted entry held; Unblock pressed on the page ──
    pressed = sc.pressed['held']
    assert held['state'] == 'account_blocked' and not _no_open_between(fake, t_close + 0.5, pressed)
    status, line, field = held['press']
    assert (status, field) == (200, '')
    assert f'Unblocked at {_utc(pressed):%H:%M:%S} UTC. Counting again from the current balance.' in line
    after = held['after_press']
    assert after['period'] not in ('start', None) and after['scope'] == 'account' and after['block'] is None
    # ── counting from the balance of the unblock; the bot trades again; SAFETY ON ──
    assert sc.opened_since('held')[0]['_t_ms'] / 1000.0 - pressed < 5.0
    assert (trading['state'], trading['label'], trading['kind']) == ('on', 'SAFETY ON', 'pos')
    view = trading['trace']['safety']
    assert view['period'] == after['period'] and view['day']['since'] == 'restart'
    assert view['drop']['peak'] == pytest.approx(balance) and view['day']['day0'] == pytest.approx(balance)
    drop, day, streak = trading['meters']
    assert day[1] == '0.0% of the 0.1% limit' and f'{_money(balance)} at the unblock, ' in day[2]
    assert trading['blocks'] == ['safety_block_start.json']            # (the old one stays; it is not this id's)


# ───────────────────────────── Turn safety OFF while blocked, then ON ─────────────────────────────

@pytest.mark.slow
def test_turn_off_while_blocked_lets_the_bot_open_and_turn_on_starts_counting_afresh(D, tmp_path):
    def build(sc):
        sc.step('blocked', lambda tr: _state(tr) == 'account_blocked' and _held_entry(tr), press=('safety-off', True))
        sc.step('off', lambda tr: _state(tr) == 'off' and bool(sc.opened_since('blocked')), press=('safety-on', False))
        sc.step('on', lambda tr: _state(tr) == 'on' and (tr.get('safety') or {}).get('period') == sc.seen['off'][
            'after_press']['period'])
    fake, page, sc = _replay(D, tmp_path, {'SAFETY_DROP_PCT': 0.1}, build)
    t_close, balance = _first_close(fake)
    blocked, off, on = sc.seen['blocked'], sc.seen['off'], sc.seen['on']
    assert blocked['state'] == 'account_blocked' and blocked['controls']['block']['rules'] == ['DROP']
    # ── OFF, with the PIN: the bot opens although the block file of this id is still there ──
    t_off = sc.pressed['blocked']
    status, line, field = blocked['press']
    assert (status, field) == (200, '') and f'Safety is OFF since {_utc(t_off):%H:%M:%S} UTC.' in line
    assert blocked['after_press']['enabled'] is False and blocked['after_press']['block'] is not None
    assert not _no_open_between(fake, t_close + 0.5, t_off)
    assert sc.opened_since('blocked')[0]['_t_ms'] / 1000.0 - t_off < 5.0
    assert (off['state'], off['label'], off['kind']) == ('off', 'SAFETY OFF', 'warn')
    assert off['lines'][0] == (f'No limit is applied: both bots of account {TAIL} trade exactly as the strategy says. '
                               'The meters are for information only.')
    assert off['blocks'] == ['safety_block_start.json'] and off['controls']['block'] is not None
    assert off['buttons'] == {'unblock': False, 'off': False, 'on': True, 'pin': False}
    assert off['questions']['on'].startswith(f'Turn the safety ON for account {TAIL}? Counting starts now')
    # ── ON, without a PIN: a fresh start -- the high and today's start are the balance of now, the count 0 ──
    t_on = sc.pressed['off']
    status, line, field = off['press']
    assert status == 200 and (f'Safety is ON since {_utc(t_on):%H:%M:%S} UTC. Counting starts from the current '
                              'balance.') in line
    fresh = off['after_press']
    assert fresh['enabled'] is True and fresh['period'] not in ('start', None) and fresh['block'] is None
    view = on['trace']['safety']
    now_balance = on['trace']['account']['balance']
    assert (on['state'], on['label'], on['kind']) == ('on', 'SAFETY ON', 'pos')
    assert view['period'] == fresh['period'] and view['day']['since'] == 'restart' and view['streak']['count'] == 0
    assert view['drop']['peak'] == pytest.approx(now_balance) and view['day']['day0'] == pytest.approx(now_balance)
    assert on['meters'][0][1] == '0.0% of the 0.1% limit'
    assert [p['by'] for p in _presses(page)] == [f'dashboard {BRANCH} from 127.0.0.1'] * 2


# ───────────────────────────── 6.2 C: an old bot switched this bot's MetaTrader 5 ─────────────────────────────

def _old_bot(tmp_path, fake, t_from, t_to):
    """The old bot's file in the folder above OUTPUT_DIR, rewritten every 20 s of the bot's clock from t_from to
    t_to (seconds after START): the old bot runs then."""
    path = tmp_path / 'XAUUSDm.json'

    def touch(f):
        path.write_text('{}', encoding='utf-8')
        t = f.clock.time()
        os.utime(path, (t, t))
    for s in range(int(t_from), int(t_to), 20):
        fake.at(START + s, touch)


def test_an_old_bot_that_switched_this_bots_metatrader_is_said_from_the_trace_of_the_refused_polls(D, tmp_path):
    """The Turtle's long trip holds three legs from 1138 s. At 1200 s an old bot starts on this bot's MetaTrader 5
    and logs it into its own account (...9876); at 1300 s the account is back and the old bot stops. The refused
    polls write no positions, but the trace says the account is refused and an old bot runs on this MetaTrader 5:
    the page's red banner is the spec's (6.2 C), in the bot's console the same; afterwards the old bot's banner
    while its files are fresh (6.2 B), then none, and the trade is closed at its stop as without the old bot."""
    out = tmp_path / 'bot_output'
    fake, clock = TB._market(TB._long_trip()[:3])
    _old_bot(tmp_path, fake, 1200, 1300)
    other = 98769876
    fake.at(START + 1200, lambda f: setattr(f, 'account_login', other))
    fake.at(START + 1300, lambda f: setattr(f, 'account_login', F.ACCOUNT_LOGIN))
    page = Page(D, out, TB.SYMBOL, clock)
    sc = Scenario(page, fake)
    sc.step('switched', lambda tr: tr.get('stale') is True and (tr.get('health') or {}).get('account_ok') is False
            and clock.time() - START > 1215)
    sc.step('back', lambda tr: tr.get('stale') is False and clock.time() - START > 1305)
    sc.step('gone', lambda tr: tr.get('stale') is False and clock.time() - START > 1300 + 130)
    lines = []
    run = TB._run(fake, clock, out / 'state', overrides={'OUTPUT_DIR': str(out)}, keep_writers=True,
                  on_bot=sc.on_new_bot, credentials=F.account_credentials(None, terminal_path=OLD_TERMINAL))
    assert not sc.problems, sc.problems
    assert list(sc.seen) == ['switched', 'back', 'gone'], list(sc.seen)
    switched, back, gone = sc.seen['switched'], sc.seen['back'], sc.seen['gone']
    tail = '...' + str(other)[-4:]
    tr = switched['trace']
    assert tr['health']['login_tail'] == tail and tr['foreign']['old_bot_same_terminal'] is True
    legs = len(tr['turtle']['trade']['legs'])
    assert legs == 3
    red = [b[1] for b in switched['banners'] if b[0] == 'statebar statebar-red']
    assert len(red) == 1 and red[0].startswith(
        f'MetaTrader 5 was switched to account {tail}. This bot has {legs} open trades it cannot manage. Stop the old '
        f'bot, then log MetaTrader 5 back into {TAIL}.'), red
    said = [e for e in run.errors if 'MetaTrader 5 was switched to account' in e]
    assert said and f'This bot has {legs} open trades it cannot manage. Stop the old bot' in said[0]
    # the account back, the old bot's files still fresh: its own red banner (6.2 B), no more the switch
    assert not [b for b in back['banners'] if 'was switched' in b[1]]
    assert [b for b in back['banners'] if b[1].startswith('An old bot is running on this server and uses the same '
                                                          'MetaTrader 5.')]
    # the old bot gone: no banner of it
    assert not [b for b in gone['banners'] if 'old bot' in b[1].lower() or 'was switched' in b[1]]
    assert gone['trace']['foreign']['old_bot_age_s'] is None
