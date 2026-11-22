"""
The real-money side of the dashboard (dashboard.py): the safety bar at the top of every tab, its three buttons, the
banners of what needs the owner, the real-money badge, chip and tiles.

The page has no login and its port is open, so the rules of the buttons are tested where they are enforced: in the
function behind the callback (safety_action) and in safety.press, with real files in tmp_path, called as functions
and over HTTP. Every folder here is made by hand: a bot folder with a trace as the bot writes it (SPEC section 9),
and beside it the account folder, filled by real safety.Tracker objects (the two bots of one account) and by the
presses themselves. No bot runs here; the bot's own side of the safety is in test_live_*.py and test_safety_*.py.
"""
import ast
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

from conftest import ROOT, wording_offenders
from conftest import differs, found

pytest.importorskip('dash')
plotly = pytest.importorskip('plotly')

SYM = 'XAUUSDm'                        # (any symbol name: the trace file names it)
LOGIN = 12345678                       # the fake account: the page may show '...5678' and nothing more of it
TAIL = '...5678'
OWN_PIN = 'Alc-7391-pin'               # a PIN the owner typed into the file himself (4 to 32 characters, no blank)
ERROR_CARD = ('could not be shown', 'could not be drawn')


def at(day, hour=0, minute=0, second=0):
    """A time of November 2026, UTC."""
    return datetime(2026, 11, day, hour, minute, second, tzinfo=timezone.utc).timestamp()


NOW = at(21, 14, 5)                    # "21 Nov 14:05", as in the texts of the spec


@pytest.fixture(scope='module')
def D():
    """dashboard.py imported from this branch (its constants.py, its safety.py), put back as it was afterwards."""
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


def _text(obj):
    """Everything a component tree would send to the browser, as one text."""
    return json.dumps(obj, cls=plotly.utils.PlotlyJSONEncoder, ensure_ascii=False)


def _files(*folders):
    """{path: (size, modification time)} of every file and folder under the folders: what a write would change."""
    out = {}
    for folder in folders:
        folder = str(folder)
        if not os.path.exists(folder):
            out[folder] = None
            continue
        for base, dirs, names in os.walk(folder):
            for n in dirs + names:
                p = os.path.join(base, n)
                st = os.stat(p)
                out[p] = (st.st_size if os.path.isfile(p) else None, st.st_mtime_ns if os.path.isfile(p) else None)
    return out


class Account:
    """One account made by hand in tmp_path: this bot's folder (bot_output, with its trace), the account folder
    beside it, and the two bots' safety as two real Tracker objects on that folder."""

    def __init__(self, D, tmp_path, limits=(20.0, 10.0, 10), partner_limits=None, partner_login=LOGIN,
                 start=at(12, 9), balance=1500.0, pin=OWN_PIN):
        self.D, self.S = D, D.safety
        self.root = tmp_path
        self.bot = str(tmp_path / 'bot_output')
        self.acct = str(tmp_path / D.ACCOUNT_FOLDER)
        os.makedirs(self.bot)
        S = self.S
        self.me = S.Tracker(self.acct, os.path.join(self.bot, 'state', 'safety_state.json'), D.BRANCH, D.PARTNER_BRANCH,
                            S.Limits(*limits), True, LOGIN)
        self.other = S.Tracker(self.acct, str(tmp_path / 'partner_state.json'), D.PARTNER_BRANCH, D.BRANCH,
                               S.Limits(*(partner_limits or limits)), True, partner_login)
        self.t = start
        D.JSON_DIR, D.ACCOUNT_DIR = self.bot, None
        for cache in (D._CACHE, D._EVENTS_CACHE, D._ERR_CACHE, D._DAY_BANNERS, D._CONFIG_CACHE):
            cache.clear()
        self.clock(NOW)
        if pin is not None:
            self.pin(pin)
        if balance is not None:
            self.settle(balance, start)

    def clock(self, now):
        self.now = now
        self.D._now = lambda: now

    def poll(self, balance, when=None, cash=True, who='both', waiting=0):
        """One poll of the bots at `when` (cash: the cash history was read in that poll, so a change can settle)."""
        if when is not None:
            self.t = when
        for name, tracker in (('me', self.me), ('other', self.other)):
            if who in ('both', name):
                tracker.load(self.t)
                tracker.poll(self.t, balance, [] if cash else None, self.t if cash else None, waiting)
                tracker.flush(self.t)
        return self.me.view()

    def settle(self, balance, when, who='both'):
        """A balance the safety has judged by `when`: seen 4 s before, then again with the cash history read."""
        self.poll(balance, when - 4.0, who=who)
        return self.poll(balance, when, who=who)

    def trace(self, view='mine', age=2.0, **sections):
        """Write this bot's trace as of `age` seconds ago: its safety view and whatever sections the test gives."""
        view = self.me.view() if view == 'mine' else view
        balance = ((view or {}).get('drop') or {}).get('balance') if isinstance(view, dict) else None
        tr = {'schema': 1, 't': self.now - age, 'symbol': SYM, 'branch': self.D.BRANCH, 'mode': 'live',
              'strategy': 'basket', 'stale': False, 'safety': view,
              'account': {'login_tail': TAIL, 'balance': balance, 'equity': balance},
              'health': {'account_ok': True, 'connected': True, 'trade_mode_name': 'real', 'margin_mode_name': 'hedging',
                         'login_tail': TAIL, 'own_login_tail': TAIL}}
        for key, value in sections.items():
            if isinstance(value, dict) and isinstance(tr.get(key), dict):
                tr[key] = dict(tr[key], **value)
            else:
                tr[key] = value
        with open(os.path.join(self.bot, f'{SYM}_trace.json'), 'w', encoding='utf-8') as f:
            json.dump(tr, f)
        self.D._CACHE.clear()
        return tr

    def seen_now(self, age=2.0, rounds=1):
        """The bots were polled `age` seconds ago and this bot wrote its trace then: the usual running state.
        (rounds=3: three polls 2 s apart, after which each bot has read what the other wrote in the first.)"""
        balance = self.me.view()['drop']['balance']
        for k in range(rounds - 1, -1, -1):
            view = self.poll(balance, self.now - age - 2.0 * k)
        self.trace(view, age=age)
        return view

    def model(self):
        return self.D.safety_state(SYM, self.D.load(SYM))

    def pin(self, own=None):
        """The PIN of this account: `own` written into the PIN file as the owner would, else the file as it is, else
        made as the dashboard makes it when it starts as a program (6 random digits)."""
        path = self.S.pin_path(self.acct)
        if own is not None:
            os.makedirs(self.acct, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(own + '\n')
        elif not os.path.exists(path):
            self.S.ensure_pin(self.acct)
        with open(path, encoding='utf-8') as f:
            return f.read().strip()

    def press(self, button, pin=None, seen='shown', clicks=1, remote='203.0.113.9'):
        """A press as the callback hands it on: the one button triggered, its click count, the PIN field, what the
        bar showed. (answer text, ok, the PIN field's new value)"""
        seen = self.model()['seen'] if seen == 'shown' else seen
        result, field = self.D.safety_action([f'{button}.submit_n_clicks'], {button: clicks}, pin, seen, remote)
        if result is self.D.no_update:
            return None, None, field
        text = _text(result)
        return result.children[-1], 'sb-answer-ok' in text, field

    def controls(self):
        return self.S.read_controls(self.acct)


@pytest.fixture
def acct(D, tmp_path):
    return Account(D, tmp_path)


def _meters(m):
    """[(label, head, detail, sub, classes)] of the three meters of a bar."""
    out = []

    def walk(o):
        if isinstance(o, dict):
            props = o.get('props') or {}
            cls = str(props.get('className') or '')
            if cls.startswith('prog '):
                kids = {}

                def leaves(x):
                    if isinstance(x, dict):
                        p = x.get('props') or {}
                        c = str(p.get('className') or '')
                        if c in ('prog-label', 'prog-pct', 'prog-detail', 'prog-sub'):
                            kids[c] = p.get('children')
                        for v in p.values():
                            leaves(v)
                    elif isinstance(x, list):
                        for v in x:
                            leaves(v)
                leaves(o)
                out.append((kids.get('prog-label'), kids.get('prog-pct'), kids.get('prog-detail'), kids.get('prog-sub'), cls))
                return
            for v in props.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads(_text(m['meters'])))
    return out


def _bar(D, m):
    """The whole bar as the browser gets it: the part that stays in view and the part under it."""
    return _text([D.safety_head(m), D.safety_detail(m)])


# ───────────────────────────── the bar in every state ─────────────────────────────

def test_the_bar_while_the_safety_is_on_and_watching(D, acct):
    """Green SAFETY ON with the safety's own sentence; the three meters with the bot's own figures in the words of
    the spec; of the buttons only Turn safety OFF (with the PIN field); what the files said goes back with a press."""
    acct.settle(1612.40, at(14, 9))
    acct.settle(1457.60, at(21, 0, 0, 6))              # the first balance of 21 Nov: the day's start
    for k in range(7):
        acct.me.on_trade_closed(at(21, 9, k), f'lost{k}', -1.5)
    acct.settle(1412.40, at(21, 13))
    acct.seen_now()
    m = acct.model()
    assert (m['state'], m['label'], m['kind']) == ('on', 'SAFETY ON', 'pos')
    assert m['lines'] == [f'Watching account {TAIL}. New trades are allowed.']
    assert m['show'] == {'unblock': False, 'off': True, 'on': False, 'pin': True}
    assert m['seen'] == {'period': 'start', 'enabled': True, 'scope': None} and m['alert'] is None
    drop, day, streak = _meters(m)
    assert drop[:3] == ('Drop from the high (account)', '12.4% of the 20% limit',
                        'balance $1,412.40 · high $1,612.40 on 14 Nov · blocks at $1,289.92')
    assert day[:3] == ('Loss today (account, UTC day)', '3.1% of the 10% limit',
                       'balance $1,412.40 · $1,457.60 at 00:00 UTC · blocks at $1,311.84')
    assert streak[:3] == ('Losing trades in a row (this bot)', '7 of 10', 'a winning trade sets it back to 0')
    assert 'prog-ok' in drop[4] and 'prog-ok' in day[4] and 'prog-amber' in streak[4]      # 70 % of its limit: amber
    bar = _bar(D, m)
    assert 'Closed trades only: an open trade counts when it closes.' in bar
    assert 'sb-pill sb-pill-pos' in bar and 'SAFETY ON' in bar
    for bad in ERROR_CARD:
        assert not found(bar, bad)


def test_a_meter_turns_amber_from_70_percent_of_its_limit_and_red_from_90(D, acct):
    for balance, level in ((1300.0, 'prog-ok'), (1290.0, 'prog-amber'), (1231.0, 'prog-amber'), (1230.0, 'prog-red')):
        a = Account(D, acct.root / f'b{int(balance)}', limits=(20.0, None, None))
        a.settle(balance, at(21, 13))                  # 13.3 %, 14 %, 17.9 % and 18 % below 1,500: of a 20 % limit
        a.seen_now()
        drop, day, streak = _meters(a.model())
        assert level in drop[4], (balance, drop)
        # a rule without a limit is said to be off, never drawn as an empty meter of 0 %
        assert day[1:3] == ('off', 'this rule is off: no limit is set') and 'prog-info' in day[4]
        assert streak[1:3] == ('off', 'this rule is off: no limit is set')


def test_the_bar_while_a_limit_is_being_checked(D, acct):
    """Amber CHECKING from the moment the balance reaches a limit until the bot knows it is a loss: the bot's own
    sentence; nothing is blocked yet, so no Unblock."""
    acct.poll(1194.0, NOW - 3.0, cash=False)           # the fall is there, the cash history is not read yet
    acct.trace(age=3.0)
    m = acct.model()
    assert (m['state'], m['label'], m['kind']) == ('checking', 'CHECKING', 'warn')
    assert m['lines'] == ['A limit was reached at 14:04. Checking that it is a loss and not a withdrawal (up to 1 '
                          'minute). No new trade until then.']
    assert m['show']['unblock'] is False and m['show']['off'] is True and m['alert'] is None
    assert 'sb-pill sb-pill-warn' in _bar(D, m)
    # ... and the wait for the result of a closed trade that could be the last loss of the limit
    b = Account(D, acct.root / 'results', limits=(None, None, 3))
    for k in range(2):
        b.me.on_trade_closed(at(21, 13, k), f'lost{k}', -2.0)
    b.poll(1500.0, NOW - 2.0, waiting=1)
    b.trace()
    m = b.model()
    assert m['state'] == 'checking' and 'waits for the result of its last closed trade' in m['lines'][0]
    assert _meters(m)[2][1:3] == ('2 of 3', 'a winning trade sets it back to 0 · 1 closed trade waits for the result')


@pytest.mark.parametrize('rule', ['drop', 'day', 'both'])
def test_the_bar_of_a_blocked_account_says_which_limit_with_the_numbers_of_the_block(D, tmp_path, rule):
    """Red ACCOUNT BLOCKED: the safety's sentence, the reason from the block file with its numbers and the bot that
    saw it; the two account meters show the block file's numbers, and keep them while the balance moves on; Unblock
    and Turn safety OFF are offered; the question of Unblock says what starts again, with the balance of now."""
    acct = Account(D, tmp_path, limits=(20.0, 10.0, 10))
    if rule == 'day':                                  # 10.2 % lost in the day, 10.2 % below the high
        acct.settle(1500.0, at(21, 0, 0, 6))
        acct.settle(1347.10, at(21, 14, 5))
        reasons = ['The account lost 10.2% on 21 Nov, UTC day (limit 10%): balance $1,347.10, $1,500.00 at the start '
                   'of that day.']
        figures = (('10.2% of the 20% limit', 'balance $1,347.10 · high $1,500.00 on 12 Nov · blocked at $1,200.00'),
                   ('10.2% of the 10% limit', 'balance $1,347.10 · $1,500.00 at 00:00 UTC · blocked at $1,350.00'))
        balance = 1347.10
    elif rule == 'drop':                               # 20.4 % below the high, of it 9.5 % today
        acct.settle(1320.0, at(21, 0, 0, 6))
        acct.settle(1194.0, at(21, 14, 5))
        reasons = ['The account fell 20.4% below its high (limit 20%): balance $1,194.00, high $1,500.00 on 12 Nov.']
        figures = (('20.4% of the 20% limit', 'balance $1,194.00 · high $1,500.00 on 12 Nov · blocked at $1,200.00'),
                   ('9.5% of the 10% limit', 'balance $1,194.00 · $1,320.00 at 00:00 UTC · blocked at $1,188.00'))
        balance = 1194.0
    else:
        acct.settle(1500.0, at(21, 0, 0, 6))
        acct.settle(1194.0, at(21, 14, 5))
        reasons = ['The account fell 20.4% below its high (limit 20%): balance $1,194.00, high $1,500.00 on 12 Nov.',
                   'The account lost 20.4% on 21 Nov, UTC day (limit 10%): balance $1,194.00, $1,500.00 at the start '
                   'of that day.']
        figures = (('20.4% of the 20% limit', 'balance $1,194.00 · high $1,500.00 on 12 Nov · blocked at $1,200.00'),
                   ('20.4% of the 10% limit', 'balance $1,194.00 · $1,500.00 at 00:00 UTC · blocked at $1,350.00'))
        balance = 1194.0
    acct.clock(at(21, 14, 6))
    acct.seen_now()
    m = acct.model()
    assert (m['state'], m['label'], m['kind']) == ('account_blocked', 'ACCOUNT BLOCKED', 'neg')
    saw = f'{D.bot_words(D.BRANCH)} ({D.BRANCH}) saw it.'
    assert m['lines'] == ['Both bots open no new trade and add nothing to open trades since 21 Nov 14:05. Open '
                          'trades keep their stop and target. Press Unblock to trade again.'] + reasons \
        + [saw[:1].upper() + saw[1:]]
    assert m['show'] == {'unblock': True, 'off': True, 'on': False, 'pin': True}
    drop, day, _ = _meters(m)
    assert (drop[1], drop[2]) == figures[0] and (day[1], day[2]) == figures[1]
    assert 'the numbers of the block (21 Nov 14:05): they stay until Unblock' == drop[3] == day[3]
    assert f"Unblock account {TAIL}? Counting starts again from now for both bots: the high becomes the balance of " \
           f"now ({D.money(balance)}), today's loss counts from now, both losing-trade counts go to 0. A bot with a " \
           'standing signal may open a trade within seconds.' == m['dialogs']['unblock']
    # the block goes to the banner, the sound and the browser notification (the alert store), once per block
    assert m['alert']['level'] == 'red' and m['alert']['head'] == 'ACCOUNT BLOCKED: '
    assert 'since 21 Nov 14:05' in m['alert']['text']
    bar = _bar(D, m)
    assert 'sb-pill sb-pill-neg' in bar and 'ACCOUNT BLOCKED' in bar and reasons[0] in bar
    # an hour later a trade that was open has closed with a profit: the meters are still the block's
    acct.clock(at(21, 15, 6))
    acct.settle(balance + 40.0, at(21, 15, 5))
    acct.seen_now()
    m2 = acct.model()
    assert m2['state'] == 'account_blocked' and [x[1:4] for x in _meters(m2)[:2]] == [drop[1:4], day[1:4]]
    assert m2['alert']['key'] == m['alert']['key']     # the same block: announced once


def test_a_block_file_blocks_the_bar_whatever_the_bot_says(D, acct):
    """The block file is what blocks: the bar is red from it alone -- before this bot has taken it, while this bot is
    not running, and when the file's details cannot be read."""
    acct.settle(1194.0, at(21, 14, 5), who='other')    # the other bot met the limit; this bot has not polled since
    acct.trace(view=acct.me.view(), age=2.0)           # (it writes its trace, with its safety view of before)
    m = acct.model()
    assert m['state'] == 'account_blocked' and m['show']['unblock'] is True
    saw = f'{D.bot_words(D.PARTNER_BRANCH, other=True)} ({D.PARTNER_BRANCH}) saw it.'
    assert m['lines'][0].startswith('Both bots open no new trade and add nothing to open trades since 21 Nov 14:05.')
    assert m['lines'][-1] == saw[:1].upper() + saw[1:]
    assert _meters(m)[0][1] == '20.4% of the 20% limit'
    acct.clock(NOW + 7200.0)                           # two hours later neither bot runs: still red, and said
    m = acct.model()
    assert (m['state'], m['kind']) == ('account_blocked', 'neg')
    assert ('', 'The bot is not running (last seen 14:04). A button press is applied when it starts.') in m['notes']
    with open(D.safety.block_path(acct.acct, 'start'), 'w', encoding='utf-8') as f:
        f.write('')                                    # an empty block file still blocks
    m = acct.model()
    assert m['state'] == 'account_blocked' and 'The details of this block cannot be read.' in m['lines']


def test_the_bar_of_a_bot_blocked_for_losing_trades_in_a_row(D, acct):
    """Red THIS BOT BLOCKED with the bot's own sentence; its meter is full; Unblock asks about this bot alone, and
    says that the account's high and today's loss stay."""
    for k in range(10):
        acct.me.on_trade_closed(at(21, 13, 55 + k // 6, k), f'lost{k}', -2.0)
    acct.seen_now(rounds=3)
    m = acct.model()
    me = D.bot_words(D.BRANCH)
    assert (m['state'], m['label'], m['kind']) == ('bot_blocked', 'THIS BOT BLOCKED', 'neg')
    assert m['lines'][0].startswith(f'{me[:1].upper() + me[1:]} opens no new trade since 21 Nov 13:5')
    assert 'it lost 10 trades in a row (limit 10). Its open trade keeps its stop and target.' in m['lines'][0]
    other = D.bot_words(D.PARTNER_BRANCH, other=True)
    assert m['lines'][0].endswith(f'{other[:1].upper() + other[1:]} is not blocked.')
    assert m['show'] == {'unblock': True, 'off': True, 'on': False, 'pin': True}
    streak = _meters(m)[2]
    assert streak[1] == '10 of 10' and 'prog-red' in streak[4]
    assert m['dialogs']['unblock'] == (f"Unblock {me}? Its count of losing trades goes back to 0. The account's high "
                                       "and today's loss stay. If its signal still stands it may open a trade within "
                                       'seconds.')
    assert m['alert']['level'] == 'red' and m['alert']['head'] == 'THIS BOT BLOCKED: '
    # its open trade closes with a loss while it is blocked: counted (the meter stays full), the block is the same
    key = m['alert']['key']
    acct.me.on_trade_closed(at(21, 14, 4), 'the open one', -2.0)
    acct.seen_now()
    m = acct.model()
    streak = _meters(m)[2]
    assert streak[1] == '11 of 10' and 'prog-red' in streak[4] and '"width": "100.0%"' in _text(m['meters'])
    assert 'it lost 10 trades in a row (limit 10)' in m['lines'][0] and m['alert']['key'] == key


def test_the_bar_of_a_bot_blocked_because_another_program_trades_its_market(D, acct):
    """Section 6.3: the same bar and the same Unblock, with the text that names the old ladder bot."""
    acct.me.note_other_program(at(21, 14, 5), "another program closed this bot's trade at 14:05 UTC")
    acct.seen_now()
    m = acct.model()
    assert (m['state'], m['label']) == ('bot_blocked', 'THIS BOT BLOCKED')
    market = D.bot_market(D.BRANCH)
    assert f"another program is trading {market} in this account (another program closed this bot's trade at 14:05 " \
           'UTC). If the old ladder bot still runs on this account, stop it, then press Unblock.' in m['lines'][0]
    assert 'make sure that program is stopped first' in m['dialogs']['unblock']


def test_the_bar_while_the_safety_is_off(D, acct):
    """Amber SAFETY OFF: no limit is applied, the meters are for information only (drawn neutral, however far the
    balance has fallen); only Turn safety ON is offered, and it needs no PIN."""
    ok, _ = D.safety.press(acct.acct, 'off', None, 'command line', at(21, 12), need_pin=False)
    assert ok
    acct.settle(1100.0, at(21, 13))                    # far beyond both limits: nothing blocks while OFF
    acct.seen_now()
    m = acct.model()
    assert (m['state'], m['label'], m['kind']) == ('off', 'SAFETY OFF', 'warn')
    assert m['lines'] == [f'No limit is applied: both bots of account {TAIL} trade exactly as the strategy says. The '
                          'meters are for information only.']
    assert m['show'] == {'unblock': False, 'off': False, 'on': True, 'pin': False}
    assert m['seen'] == {'period': 'start', 'enabled': False, 'scope': None} and m['alert'] is None
    drop, day, streak = _meters(m)
    assert drop[1] == '26.7% of the 20% limit' and 'prog-info' in drop[4] and 'prog-info' in day[4]
    assert m['dialogs']['on'] == (f'Turn the safety ON for account {TAIL}? Counting starts now: the high is the '
                                  "balance of now, today's loss counts from now, both losing-trade counts start at 0.")
    assert 'sb-pill sb-pill-warn' in _bar(D, m)
    # pressed OFF a moment ago and the bot has not taken it yet: OFF at once, with the line that says so
    b = Account(D, acct.root / 'just', limits=(20.0, 10.0, 10))
    b.seen_now()
    D.safety.press(b.acct, 'off', None, 'command line', NOW - 1.0, need_pin=False)
    m = b.model()
    assert m['state'] == 'off' and ('', 'Pressed at 14:04, not applied yet.') in m['notes']
    assert m['lines'][0].startswith('No limit is applied: both bots of account')


def test_the_bar_when_the_safety_check_failed(D, acct):
    """Red SAFETY CHECK FAILED from the bot's `error`: since when, that open trades are still managed, the way out
    (OFF), and what failed; also for the bare view the bot writes when it has no usable safety at all."""
    view = dict(acct.poll(1500.0, NOW - 2.0), error='the safety state could not be saved since 14:02 UTC '
                '(PermissionError: [Errno 13] Permission denied)', blocked=True, state='error', since=at(21, 14, 2),
                reasons=[D.safety.ERROR_SENTENCE])
    acct.trace(view)
    m = acct.model()
    assert (m['state'], m['label'], m['kind']) == ('error', 'SAFETY CHECK FAILED', 'neg')
    assert m['lines'] == ['This bot could not check the safety since 14:02, so it opens no new trade. Open trades '
                          'are still managed. Turn safety OFF to trade without it.']
    assert ('', 'What failed: the safety state could not be saved since 14:02 UTC (PermissionError: [Errno 13] '
                'Permission denied).') in m['notes']
    assert m['show']['off'] is True and m['show']['unblock'] is False
    assert m['alert']['level'] == 'red' and m['alert']['head'] == 'SAFETY CHECK FAILED: '
    acct.trace({'enabled': True, 'blocked': True, 'error': 'ImportError: no Tracker'})    # (no time, no meters)
    m = acct.model()
    assert m['state'] == 'error' and m['lines'][0].startswith('This bot could not check the safety, so it opens no')
    for bad in ERROR_CARD:
        assert not found(_bar(D, m), bad)
    # while the safety is OFF a failing check stops nothing: the bar is OFF, and says that the check fails
    D.safety.press(acct.acct, 'off', None, 'command line', NOW - 60.0, need_pin=False)
    acct.trace(dict(view, enabled=False, blocked=False, state='off'))
    m = acct.model()
    assert m['state'] == 'off' and m['alert'] is None
    assert any(k == 'warn' and text.startswith('The safety check of this bot is failing') for k, text in m['notes'])


def test_the_bar_of_a_bot_that_is_not_running(D, acct):
    """A trace and a status older than 60 s: the grey line with the time the bot was last seen; ON is no longer
    green and no longer says "watching"; the meters are drawn as old."""
    acct.settle(1412.40, at(21, 13))
    acct.seen_now()
    assert acct.model()['kind'] == 'pos'
    acct.clock(NOW + 57.0)
    assert acct.model()['notes'] == []                 # last seen 59 s ago: still running
    acct.clock(NOW + 300.0)
    m = acct.model()
    assert (m['state'], m['label'], m['kind']) == ('on', 'SAFETY ON', '')
    assert m['lines'] == []
    assert m['notes'] == [('', 'The bot is not running (last seen 14:04). A button press is applied when it starts.')]
    assert all('prog-info' in x[4] for x in _meters(m)) and 'sb-old' in _text(m['meters'])
    bar = _bar(D, m)
    assert 'sb-pill sb-pill-idle' in bar and not found(bar, 'Watching account')
    assert m['show']['off'] is True                    # a press now is applied when the bot starts
    # a bot that never wrote here: said so, nothing raised
    b = Account(D, acct.root / 'never', balance=None)
    m = b.model()
    assert m['kind'] == '' and m['notes'][0][1].startswith('The bot has not written here yet')
    assert m['notes'][0][1].endswith('A button press is applied when it starts.')
    assert [x[1] for x in _meters(m)] == ['—', '—', '—']
    for bad in ERROR_CARD:
        assert not found(_bar(D, m), bad)


def test_a_press_the_bot_has_not_applied_yet_is_said(D, acct):
    """The files hold another id than the bot's view (Unblock or ON was pressed and the bot has not polled since):
    the bar shows what the files say, with 'Pressed at 12:00, not applied yet.'"""
    acct.settle(1194.0, at(21, 11))                    # blocked at 11:00
    acct.clock(at(21, 12, 0, 3))
    acct.seen_now()
    assert acct.model()['state'] == 'account_blocked'
    ok, _ = D.safety.press(acct.acct, 'unblock', None, 'command line', at(21, 12, 0, 2), need_pin=False)
    assert ok
    m = acct.model()                                   # the bot's last poll was a second before the press
    assert (m['state'], m['kind']) == ('on', '') and m['lines'] == []
    assert m['notes'] == [('', 'Pressed at 12:00, not applied yet.')]
    assert m['show']['unblock'] is False and m['alert'] is None
    assert 'sb-old' in _text(m['meters'])              # the figures are still those of before the press
    acct.poll(1194.0, at(21, 12, 0, 5))                # the bot's next poll reads the press ...
    acct.clock(at(21, 12, 0, 9))
    acct.seen_now()                                    # ... and the one after it counts from it: applied
    m = acct.model()
    assert (m['state'], m['kind'], m['notes']) == ('on', 'pos', [])
    day = _meters(m)[1]
    assert day[1] == '0.0% of the 10% limit' and '$1,194.00 at the unblock, 12:00' in day[2]
    # a bot that runs but does not take the press for minutes: said, with what to do
    D.safety.press(acct.acct, 'off', None, 'command line', at(21, 12, 1), need_pin=False)
    acct.clock(at(21, 12, 5))
    acct.trace(dict(acct.me.view(), at=acct.now - 2.0))        # (it polls, and its view still says ON)
    m = acct.model()
    assert m['state'] == 'off'
    assert m['notes'][0][1].startswith('Pressed at 12:01, not applied yet. The bot runs but has not taken it for 4 min')


def test_a_bot_that_cannot_read_the_terminal_shows_its_last_safety_check(D, acct):
    """Skipped polls: the trace is fresh (the bot runs) but carries the safety of its last good poll."""
    acct.settle(1412.40, at(21, 13))
    view = acct.poll(1412.40, NOW - 600.0)
    acct.trace(view, age=1.0, stale=True)
    m = acct.model()
    assert m['state'] == 'on' and m['kind'] == ''
    assert m['notes'] == [('', 'This bot last checked the safety at 13:55: it cannot read the terminal now, and the '
                               'figures are from then. A button press is applied at its next good poll.')]


def test_the_other_bot_of_the_account_in_its_three_forms(D, acct):
    """'<Market> bot (<branch>): running' / 'BLOCKED since 21 Nov 14:05, 9 losing trades in a row' (red, and it is
    said in the part of the bar that stays in view, with Unblock offered and its question about that bot) / 'not seen
    for 5 min'; and a bot that never started."""
    market = D.bot_market(D.PARTNER_BRANCH)
    name = f"{market[:1].upper() + market[1:] if market else 'Other'} bot ({D.PARTNER_BRANCH})"
    assert acct.model()['partner'][1].startswith(f'{name}: not seen for 9.')     # (days: its start of 12 Nov)
    acct.seen_now()
    m = acct.model()
    assert m['partner'] == ('pos', f'{name}: running')
    assert f'{name}: running' in _bar(D, m) and 'sb-partner-pos' in _bar(D, m)
    b = Account(D, acct.root / 'blocked', limits=(20.0, 10.0, 10), partner_limits=(20.0, 10.0, 9))
    for k in range(9):
        b.other.on_trade_closed(at(21, 14, 5), f'lost{k}', -2.0)
    b.seen_now()
    m = b.model()
    assert m['partner'] == ('neg', f'{name}: BLOCKED since 21 Nov 14:05, 9 losing trades in a row')
    assert m['state'] == 'on' and m['partner'] in m['notes']      # this bot trades on; the bar says who is blocked
    assert m['show']['unblock'] is True
    other = D.bot_words(D.PARTNER_BRANCH, other=True)
    assert m['dialogs']['unblock'].startswith(f'Unblock {other}? Its count of losing trades goes back to 0.')
    assert m['alert']['level'] == 'amber' and name in m['alert']['text']
    assert 'sb-partner-neg' in _bar(D, m)
    b.clock(NOW + 300.0)                               # five minutes later this bot still runs, the other does not
    b.poll(1500.0, NOW + 298.0, who='me')
    b.trace()
    m = b.model()
    assert m['partner'] == ('neg', f'{name}: not seen for 5 min (when last seen: BLOCKED since 21 Nov 14:05, 9 '
                                   'losing trades in a row)')
    c = Account(D, acct.root / 'quiet')
    c.seen_now()
    c.clock(NOW + 300.0)
    c.poll(1500.0, NOW + 298.0, who='me')
    c.trace()
    assert c.model()['partner'] == ('', f'{name}: not seen for 5 min')
    os.remove(D.safety.status_path(c.acct, D.PARTNER_BRANCH))
    assert c.model()['partner'] == ('', f'{name}: not seen yet (it has not started on this server)')


def test_the_bots_are_named_as_the_safety_names_them(D):
    """'the gold bot' / 'the BTC bot' on the page are the words of the safety's own sentences."""
    for branch in (D.BRANCH, D.PARTNER_BRANCH, 'live1_xt2', 'live1_bt2', 'odd', None):
        assert D.bot_words(branch) == D.safety._bot(branch)
        assert D.bot_words(branch, other=True) == D.safety._bot(branch, other=True)
    assert {D.bot_market(D.BRANCH), D.bot_market(D.PARTNER_BRANCH)} == {'gold', 'BTC'}


# ───────────────────────────── the meters ─────────────────────────────

def test_the_account_meters_show_the_larger_of_the_two_bots_figures(D, tmp_path):
    """Each bot keeps its own high and its own start of the day: after one of them was down they differ. Both
    dashboards show the larger figure, marked with the bot that counted it when they differ by more than 0.1 point;
    a status that is old, or of another id, is not used."""
    acct = Account(D, tmp_path, limits=(20.0, 10.0, 10))
    acct.settle(1600.0, at(14, 9), who='other')        # this bot was down while the account stood at its high
    acct.settle(1500.0, at(15, 9))
    acct.settle(1480.0, at(21, 0, 0, 6), who='other')  # ... and at 00:00 UTC of today
    acct.settle(1440.0, at(21, 9))
    acct.seen_now()
    m = acct.model()
    drop, day, _ = _meters(m)
    other = D.bot_words(D.PARTNER_BRANCH, other=True)
    assert drop[1] == '10.0% of the 20% limit'
    assert drop[2] == f'balance $1,440.00 · high $1,600.00 on 14 Nov · blocks at $1,280.00 · as counted by {other}'
    # (this bot's own day began with its first balance of today, 1,440 at 09:00: 0 % lost by its count)
    assert day[1] == '2.7% of the 10% limit'
    assert day[2] == f'balance $1,440.00 · $1,480.00 at 00:00 UTC · blocks at $1,332.00 · as counted by {other}'
    # the other bot stops: five minutes later its figures are old, the page shows this bot's own
    acct.clock(NOW + 300.0)
    acct.poll(1440.0, NOW + 298.0, who='me')
    acct.trace()
    drop, day, _ = _meters(acct.model())
    assert drop[1] == '4.0% of the 20% limit' and 'as counted by' not in drop[2]
    # two bots that agree to within 0.1 point: no mark
    b = Account(D, tmp_path / 'agree')
    b.settle(1440.0, at(21, 9))
    b.seen_now()
    assert all('as counted by' not in x[2] for x in _meters(b.model()))
    # this bot's own figure is the larger one: shown, and marked as its own
    c = Account(D, tmp_path / 'mine')
    c.settle(1600.0, at(14, 9), who='me')
    c.settle(1440.0, at(21, 9))
    c.seen_now()
    drop = _meters(c.model())[0]
    assert drop[1] == '10.0% of the 20% limit' and drop[2].endswith(f'as counted by {D.bot_words(D.BRANCH)}')


def test_where_todays_loss_counts_from_is_said(D, tmp_path):
    """'... at 00:00 UTC'; a bot that was not running at 00:00: the first balance it saw; at the very first start:
    its first start (never 'the unblock'); after ON: when the safety was turned ON."""
    a = Account(D, tmp_path / 'first', start=at(21, 10, 30, 4))       # its first start is today at 10:30
    a.seen_now()
    assert '$1,500.00 at the bot\'s first start, 10:30' in _meters(a.model())[1][2]
    b = Account(D, tmp_path / 'late')
    b.settle(1500.0, at(21, 8, 30, 4))                 # (the bot was started at 08:30 today)
    b.seen_now()
    assert '$1,500.00 at 08:30, the first balance the bot saw that day' in _meters(b.model())[1][2]
    c = Account(D, tmp_path / 'on')
    D.safety.press(c.acct, 'off', None, 'command line', at(21, 9), need_pin=False)
    c.poll(1500.0, at(21, 9, 0, 5))
    D.safety.press(c.acct, 'on', None, 'command line', at(21, 9, 30), need_pin=False)
    c.poll(1500.0, at(21, 9, 30, 5))                   # (this poll reads the press, the next one counts from it)
    c.poll(1500.0, at(21, 9, 30, 7))
    c.seen_now()
    assert '$1,500.00 when the safety was turned ON, 09:30' in _meters(c.model())[1][2]


# ───────────────────────────── the buttons: every rule is the server's ─────────────────────────────

NOT_A_PRESS = [
    ([], {'safety-off': 1}),                                                   # nothing triggered
    (None, {'safety-off': 1}),
    (['safety-off.submit_n_clicks', 'safety-unblock.submit_n_clicks'], {'safety-off': 1, 'safety-unblock': 1}),
    (['tick.n_intervals'], {'safety-off': 1}),                                 # not a button
    (['safety-toggle.submit_n_clicks'], {'safety-toggle': 1}),
    (['safety-off.n_clicks'], {'safety-off': 1}),                              # another property of the button
    (['safety-off'], {'safety-off': 1}),
    ([7], {'safety-off': 1}),
    ('safety-off.submit_n_clicks', {'safety-off': 1}),                         # (a text, not a list of one)
    (['safety-off.submit_n_clicks'], {'safety-off': None}),                    # no click count above 0
    (['safety-off.submit_n_clicks'], {'safety-off': 0}),
    (['safety-off.submit_n_clicks'], {'safety-off': -1}),
    (['safety-off.submit_n_clicks'], {'safety-off': True}),
    (['safety-off.submit_n_clicks'], {'safety-off': '1'}),
    (['safety-off.submit_n_clicks'], {'safety-off': 1.0}),
    (['safety-off.submit_n_clicks'], {'safety-on': 1}),                        # the count of another button
    (['safety-off.submit_n_clicks'], None),
    (['safety-on.submit_n_clicks'], {'safety-on': 0}),
]


@pytest.mark.parametrize('triggered, clicks', NOT_A_PRESS)
def test_what_is_not_a_press_changes_nothing_and_writes_nothing(D, tmp_path, triggered, clicks):
    """A request that is not one button pressed once: no answer (the browser's field and line stay as they are), and
    no file is read, written or made -- not the audit file, not the count of wrong PINs, not even the folder."""
    acct = Account(D, tmp_path, balance=None, pin=None)
    pin = 'whatever'
    seen = {'period': 'start', 'enabled': True}
    assert not os.path.exists(acct.acct)
    assert D.safety_action(triggered, clicks, pin, seen, '203.0.113.9') == (D.no_update, D.no_update)
    assert not os.path.exists(acct.acct)
    acct.poll(1500.0, NOW - 2.0)
    before = _files(acct.acct, acct.bot)
    assert D.safety_action(triggered, clicks, pin, seen, '203.0.113.9') == (D.no_update, D.no_update)
    assert not differs(_files(acct.acct, acct.bot), before)


@pytest.mark.parametrize('button', ['safety-unblock', 'safety-off'])
@pytest.mark.parametrize('pin', [None, 123456, ['123456'], {'pin': '1'}, True, 12.5])
def test_unblock_and_off_with_a_pin_that_is_not_text_are_not_a_press(D, acct, button, pin):
    acct.pin()
    before = _files(acct.acct)
    assert D.safety_action([f'{button}.submit_n_clicks'], {button: 1}, pin, acct.model()['seen'], None) == \
        (D.no_update, D.no_update)
    assert not differs(_files(acct.acct), before) and acct.controls()['enabled'] is True


def test_an_empty_pin_field_is_answered_without_a_file_being_touched(D, acct):
    """A click on Unblock or OFF with nothing typed: 'Type the PIN first ...' (the very sentence safety.py gives for
    it), the field emptied, nothing written, not counted as a wrong PIN -- five of them lock nothing."""
    acct.pin()
    acct.settle(1194.0, at(21, 14))                    # blocked: Unblock applies
    acct.seen_now()
    before = _files(acct.acct)
    for button in ('safety-unblock', 'safety-off'):
        for pin in ('', '   ', '\t\n'):
            for _ in range(6):
                text, ok, field = acct.press(button, pin)
                assert text == f'Type the PIN first. It is in the file {D.safety.PIN_FILE} in {acct.acct} on the server.'
                assert ok is False and field == ''
    assert not differs(_files(acct.acct), before)
    assert acct.controls()['locked_until'] is None and acct.controls()['block'] is not None
    # the same words as the safety's own answer to an empty PIN
    assert D.safety.press(acct.acct, 'off', '', 'test', NOW, need_pin=True, expect=acct.model()['seen'])[1] == text
    # a text too long to be a PIN is answered here too, and is no try either
    for _ in range(6):
        text, ok, field = acct.press('safety-off', 'x' * 33)
        assert 'a PIN has at most 32 characters' in text and ok is False and field == ''
    assert not differs(_files(acct.acct), before) and acct.controls()['enabled'] is True
    # ... and what is around a PIN does not count: the right PIN with blanks around it is the right PIN
    text, ok, _ = acct.press('safety-off', f'  {acct.pin()}\n')
    assert ok and text.startswith('Safety is OFF since')


def test_a_wrong_pin_says_how_many_tries_are_left_and_five_lock_the_buttons(D, acct):
    """The safety's own answers, shown as they are: the tries that are left, the lock with its end; while locked
    even the right PIN is refused, and the bar says until when and how to do without the PIN; Turn safety ON is never
    locked. After the lock the right PIN works."""
    pin = acct.pin()
    acct.settle(1194.0, at(21, 14))
    acct.seen_now()
    wrong = 'not-the-pin'
    for left in (4, 3, 2, 1):
        text, ok, field = acct.press('safety-unblock', wrong)
        assert text == f"Wrong PIN. {left} more {'try' if left == 1 else 'tries'}, then the buttons lock for 10 minutes."
        assert ok is False and field == ''
    text, ok, _ = acct.press('safety-off', wrong)      # (the count is one for both buttons)
    assert text == ('Wrong PIN. Too many wrong PINs: the buttons are locked until 14:15 UTC. On the server, '
                    '"safety.bat unblock" (or on, off) works without the PIN.') and ok is False
    for button in ('safety-unblock', 'safety-off'):
        text, ok, _ = acct.press(button, pin)          # the right PIN, while locked: refused without a comparison
        assert text.startswith('Too many wrong PINs: the buttons are locked until 14:15 UTC.') and ok is False
    c = acct.controls()
    assert c['block'] is not None and c['enabled'] is True and c['period'] == 'start'
    m = acct.model()
    assert ('warn', 'The buttons are locked until 14:15 UTC after too many wrong PINs. On the server, "safety.bat '
                    'unblock" (or on, off) works without the PIN. If you did not type them, somebody else reaches this '
                    'page: open its port to your own IP address only (README, section 2, step 7).') in m['notes']
    acct.clock(at(21, 14, 15, 1))                      # the lock is over
    acct.seen_now()
    text, ok, _ = acct.press('safety-unblock', pin)
    assert ok and text == 'Unblocked at 14:15:01 UTC. Counting again from the current balance.'
    # the PIN is in no file but its own: not in the audit lines, not in the lock record
    for name in os.listdir(acct.acct):
        if name != D.safety.PIN_FILE:
            with open(os.path.join(acct.acct, name), encoding='utf-8') as f:
                body = f.read()
            assert not found(body, pin) and not found(body, wrong), name


def test_turn_safety_on_needs_no_pin_and_is_never_locked(D, acct):
    pin = acct.pin()
    acct.seen_now()
    assert acct.press('safety-off', pin)[1] is True
    for _ in range(5):
        assert acct.press('safety-unblock', 'wrong!')[1] is False      # five wrong PINs: the buttons are locked
    assert acct.controls()['locked_until'] > NOW
    m = acct.model()
    assert m['show'] == {'unblock': False, 'off': False, 'on': True, 'pin': False}
    for pin_field in (None, '', 'anything', 7):
        text, ok, field = acct.press('safety-on', pin_field, clicks=3)
        assert ok and field == ''
    assert text == 'The safety is already ON.' and acct.controls()['enabled'] is True


def test_no_usable_pin_on_the_server_is_said_in_the_bar_and_by_the_press(D, tmp_path):
    """Without a PIN file (no dashboard of the account was started as a program yet) Unblock and OFF cannot be
    pressed from the page: the bar says so, and so does the press. The file the dashboard makes at its start holds 6
    digits, and they work."""
    acct = Account(D, tmp_path, pin=None)
    acct.seen_now()
    m = acct.model()
    note = next(text for k, text in m['notes'] if k == 'warn' and text.startswith('There is no usable PIN'))
    assert 'the PIN file named below is not there. Start this dashboard with start_dashboard.bat' in note
    assert note.endswith('(README, section 2, step 9).')
    text, ok, _ = acct.press('safety-off', '123456')
    assert ok is False and text.startswith('There is no PIN yet: start the dashboard once on the server')
    assert acct.controls()['enabled'] is True
    # a PIN file that is there but holds no usable PIN (too short): the owner must put it right himself
    acct.pin('123')
    note = next(text for k, text in acct.model()['notes'] if text.startswith('There is no usable PIN'))
    assert 'the PIN file named below cannot be used. Open it in Notepad' in note
    text, ok, _ = acct.press('safety-off', '123')
    assert ok is False and text.startswith('The PIN file cannot be used') and acct.controls()['enabled'] is True
    os.remove(D.safety.pin_path(acct.acct))
    made = acct.pin()                                  # (safety.ensure_pin, as the dashboard calls it at its start)
    assert re.fullmatch(r'\d{6}', made)
    assert not any('no usable PIN' in text for _, text in acct.model()['notes'])
    text, ok, _ = acct.press('safety-off', made)
    assert ok and text.startswith('Safety is OFF since')


def test_a_page_that_is_not_fresh_changes_nothing(D, acct):
    """`expect`: the press carries what the bar showed. When the files say something else by then -- the other
    dashboard or safety.bat was faster, or the page is old -- nothing is changed and the answer says to look again.
    A page that shows nothing yet (an empty store) cannot press either."""
    pin = acct.pin()
    acct.seen_now()
    old = acct.model()['seen']
    assert D.safety.press(acct.acct, 'off', None, 'command line', NOW - 1.0, need_pin=False)[0]      # safety.bat off
    before = acct.controls()
    changed = 'The safety changed since this page was refreshed. Check the bar and press again.'
    assert acct.press('safety-off', pin, seen=old)[0] == changed
    assert acct.press('safety-on', None, seen=old)[0] == changed               # the old page still showed ON
    for seen in ({}, None, 'start', {'period': 'start'}, {'enabled': False}, [], 0):
        assert acct.press('safety-on', None, seen=seen)[0] == changed, seen
        assert acct.press('safety-unblock', pin, seen=seen)[0] == changed, seen
    after = acct.controls()
    assert (after['enabled'], after['period'], after['switched_at']) == (False, 'start', before['switched_at'])
    text, ok, _ = acct.press('safety-on', None)                                # the page as it is now: accepted
    assert ok and text.startswith('Safety is ON since 14:05:00 UTC.')


def test_the_three_buttons_through_real_files(D, acct):
    """Unblock of a blocked account, Turn safety OFF, Turn safety ON, pressed as the page presses them: the files
    change as safety.py says, both bots follow, the audit file names the dashboard and the address, and the PIN field
    comes back empty every time."""
    pin = acct.pin()
    acct.settle(1194.0, at(21, 14))
    acct.seen_now()
    assert acct.me.view()['blocked'] and acct.other.view()['blocked']
    text, ok, field = acct.press('safety-unblock', pin, remote='198.51.100.7')
    assert ok and field == '' and text == 'Unblocked at 14:05:00 UTC. Counting again from the current balance.'
    c = acct.controls()
    assert c['period'] != 'start' and c['scope'] == 'account' and c['block'] is None and c['enabled'] is True
    assert c['pressed_by'] == f'dashboard {D.BRANCH} from 198.51.100.7'
    acct.clock(NOW + 5.0)
    acct.poll(1194.0, NOW + 1.0)
    acct.seen_now()
    assert not acct.me.view()['blocked'] and not acct.other.view()['blocked']
    assert acct.me.view()['drop']['peak'] == 1194.0    # counting again from the balance of now
    assert acct.model()['state'] == 'on' and acct.model()['kind'] == 'pos'
    text, ok, field = acct.press('safety-unblock', pin)
    assert ok and text == 'Nothing is blocked.' and field == ''
    text, ok, field = acct.press('safety-off', pin, remote='198.51.100.7')
    assert ok and field == '' and text == 'Safety is OFF since 14:05:05 UTC.'
    assert acct.controls()['enabled'] is False and acct.controls()['switched_by'] == f'dashboard {D.BRANCH} from 198.51.100.7'
    acct.seen_now()
    assert acct.model()['state'] == 'off'
    assert acct.press('safety-off', pin)[0] == 'The safety is already OFF.'
    off_id = acct.controls()['period']
    text, ok, field = acct.press('safety-on', None)
    assert ok and field == '' and text == 'Safety is ON since 14:05:05 UTC. Counting starts from the current balance.'
    c = acct.controls()
    assert c['enabled'] is True and c['period'] != off_id      # ON starts the counting again, under a new id
    with open(os.path.join(acct.acct, D.safety.AUDIT_FILE), encoding='utf-8') as f:
        lines = [json.loads(x) for x in f if x.strip()]
    done = [(x['action'], x['by']) for x in lines if x.get('result') == 'done']
    assert done == [('unblock', f'dashboard {D.BRANCH} from 198.51.100.7'), ('off', f'dashboard {D.BRANCH} from 198.51.100.7'),
                    ('on', f'dashboard {D.BRANCH} from 203.0.113.9')]
    assert not found(json.dumps(lines), pin)


def test_unblock_of_a_bot_leaves_the_accounts_figures(D, acct):
    """Unblock after a block for losing trades: that bot's count goes to 0; the high and today's loss stay."""
    pin = acct.pin()
    acct.settle(1600.0, at(14, 9))
    acct.settle(1500.0, at(21, 9))
    for k in range(10):
        acct.me.on_trade_closed(at(21, 13, k), f'lost{k}', -2.0)
    acct.seen_now()
    assert acct.model()['state'] == 'bot_blocked'
    text, ok, _ = acct.press('safety-unblock', pin)
    assert ok and text == ("Unblocked at 14:05:00 UTC: losing trades in a row start again from 0. The account's high "
                           "and today's start are unchanged.")
    assert acct.controls()['scope'] == 'bot'
    acct.clock(NOW + 5.0)
    acct.poll(1500.0, NOW + 1.0)
    view = acct.seen_now()
    assert view['bot_blocked'] is False and view['streak']['count'] == 0
    assert view['drop']['peak'] == 1600.0 and round(view['drop']['pct'], 2) == 6.25


def test_an_unblock_confirmed_for_one_bot_does_not_lift_an_account_block_the_page_never_showed(D, tmp_path):
    """The bar shows THIS BOT BLOCKED and its question says "the account's high and today's loss stay". While the
    question is open (the page does not refresh then) the account itself is blocked under the same counting. The
    press carries what Unblock offered (safety-seen's scope): refused as a stale page's, nothing written, the account
    stays blocked. The page as it is now offers the account, and that press lifts it."""
    a = Account(D, tmp_path, limits=(20.0, 10.0, 3))
    pin = a.pin()
    a.settle(1600.0, at(21, 9))
    for k in range(3):
        a.me.on_trade_closed(at(21, 10, k), f'loss{k}', -5.0)
    a.seen_now()
    m = a.model()
    assert m['state'] == 'bot_blocked' and m['seen'] == {'period': 'start', 'enabled': True, 'scope': 'bot'}
    assert "The account's high and today's loss stay." in m['dialogs']['unblock']
    page = m['seen']
    a.settle(1200.0, at(21, 14, 4))                      # a 25 % fall: the account is blocked, same counting
    assert a.controls()['block'] is not None and a.controls()['period'] == 'start'
    text, ok, field = a.press('safety-unblock', pin, seen=page)
    assert (text, ok, field) == ('The safety changed since this page was refreshed. Check the bar and press again.',
                                 False, '')
    c = a.controls()
    assert c['period'] == 'start' and c['block'] is not None and c['pressed_at'] is None      # nothing written
    a.seen_now()
    m = a.model()
    assert m['state'] == 'account_blocked' and m['seen']['scope'] == 'account'
    assert m['dialogs']['unblock'].startswith(f'Unblock account {TAIL}? Counting starts again from now for both bots')
    text, ok, _ = a.press('safety-unblock', pin)         # the page as it is now
    assert ok and text == 'Unblocked at 14:05:00 UTC. Counting again from the current balance.'
    assert a.controls()['scope'] == 'account'


# ── over HTTP: the callbacks as a program on the network reaches them ──

def _serve(D):
    from werkzeug.serving import make_server
    srv = make_server('127.0.0.1', 0, D.server, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _post(port, body):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/_dash-update-component', data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def _press_body(D, button, pin, seen, clicks=1, changed=None):
    """The request the page sends when the question of a button was answered with OK."""
    key = next(k for k in D.app.callback_map if 'safety-result.children' in k and 'safety-pin.value' in k)
    counts = {'safety-unblock': None, 'safety-off': None, 'safety-on': None, button: clicks}
    return {'output': key,
            'outputs': [{'id': 'safety-result', 'property': 'children'}, {'id': 'safety-pin', 'property': 'value'}],
            'inputs': [{'id': b, 'property': 'submit_n_clicks', 'value': counts[b]}
                       for b in ('safety-unblock', 'safety-off', 'safety-on')],
            'state': [{'id': 'safety-pin', 'property': 'value', 'value': pin},
                      {'id': 'safety-seen', 'property': 'data', 'value': seen}],
            'changedPropIds': [f'{button}.submit_n_clicks'] if changed is None else changed}


def _answer(text):
    """(the result line's text, the PIN field's new value) of a 200 answer."""
    resp = json.loads(text)['response']
    return _text(resp['safety-result']['children']), resp['safety-pin']['value']


def test_the_same_post_twice_changes_the_state_once(D, acct):
    """Over a real socket: a press of Turn safety OFF with the right PIN is sent twice (a double click, a replay of
    the request). The first one switches the safety OFF; the second finds that the page it speaks for is no longer
    what the files say, and changes nothing."""
    pin = acct.pin()
    acct.settle(1194.0, at(21, 14))
    acct.seen_now()
    seen = acct.model()['seen']
    srv = _serve(D)
    try:
        body = _press_body(D, 'safety-off', pin, seen)
        status, text = _post(srv.server_port, body)
        assert status == 200
        line, field = _answer(text)
        assert 'Safety is OFF since 14:05:00 UTC.' in line and field == ''
        first = acct.controls()
        assert first['enabled'] is False and first['switched_by'] == f'dashboard {D.BRANCH} from 127.0.0.1'
        status, text = _post(srv.server_port, body)
        assert status == 200 and 'The safety changed since this page was refreshed.' in _answer(text)[0]
        assert acct.controls() == first
        # the same for Unblock: one new id, not two
        acct.seen_now()
        assert D.safety.press(acct.acct, 'on', None, 'command line', NOW, need_pin=False)[0]
        acct.poll(1194.0, NOW + 10.0)
        acct.poll(1194.0, NOW + 12.0)                  # counting again from 1,194 under the new id ...
        acct.settle(1000.0, NOW + 30.0)                # ... and blocked again: 16 % lost in the day
        acct.clock(NOW + 40.0)
        acct.seen_now()
        seen = acct.model()['seen']
        body = _press_body(D, 'safety-unblock', pin, seen)
        status, text = _post(srv.server_port, body)
        assert status == 200 and 'Unblocked at' in _answer(text)[0]
        new_id = acct.controls()['period']
        assert new_id != seen['period']
        status, text = _post(srv.server_port, body)
        assert status == 200 and 'The safety changed since this page was refreshed.' in _answer(text)[0]
        assert acct.controls()['period'] == new_id
    finally:
        srv.shutdown()


def test_the_buttons_over_http_follow_the_same_rules(D, acct):
    """What any program on the network can send: a request without a click, with two buttons, with a button the page
    does not have, with a PIN that is not text -- 204, nothing written; a wrong PIN -- the count-down; an empty one --
    'Type the PIN first'; Turn safety ON -- no PIN asked."""
    pin = acct.pin()
    acct.seen_now()
    seen = acct.model()['seen']
    srv = _serve(D)
    try:
        before = _files(acct.acct, acct.bot)
        for body in (_press_body(D, 'safety-off', pin, seen, clicks=None),
                     _press_body(D, 'safety-off', pin, seen, clicks=0),
                     _press_body(D, 'safety-off', pin, seen, clicks='1'),
                     _press_body(D, 'safety-off', pin, seen, changed=[]),
                     _press_body(D, 'safety-off', pin, seen, changed=['safety-off.submit_n_clicks',
                                                                      'safety-on.submit_n_clicks']),
                     _press_body(D, 'safety-off', pin, seen, changed=['safety-toggle.submit_n_clicks']),
                     _press_body(D, 'safety-off', pin, seen, changed=['tick.n_intervals']),
                     _press_body(D, 'safety-off', None, seen),
                     _press_body(D, 'safety-off', 123456, seen),
                     _press_body(D, 'safety-unblock', [pin], seen)):
            status, text = _post(srv.server_port, body)
            assert status == 204, (body['inputs'], body['changedPropIds'], status, text[-300:])
        assert not differs(_files(acct.acct, acct.bot), before) and acct.controls()['enabled'] is True
        status, text = _post(srv.server_port, _press_body(D, 'safety-off', '', seen))
        assert status == 200 and 'Type the PIN first.' in _answer(text)[0]
        assert not differs(_files(acct.acct, acct.bot), before)
        status, text = _post(srv.server_port, _press_body(D, 'safety-off', 'not-the-pin', seen))
        line, field = _answer(text)
        assert status == 200 and 'Wrong PIN. 4 more tries, then the buttons lock for 10 minutes.' in line and field == ''
        assert acct.controls()['enabled'] is True
        status, text = _post(srv.server_port, _press_body(D, 'safety-off', pin, seen))
        assert status == 200 and 'Safety is OFF since' in _answer(text)[0] and acct.controls()['enabled'] is False
        status, text = _post(srv.server_port, _press_body(D, 'safety-on', None, {'period': seen['period'],
                                                                                 'enabled': False}))
        assert status == 200 and 'Safety is ON since' in _answer(text)[0] and acct.controls()['enabled'] is True
    finally:
        srv.shutdown()


def test_every_callback_with_empty_inputs_writes_nothing(D, acct):
    """Every callback of the page, sent with None for every input (what a probe of the port sends): 200 or 204, and
    no file of the bot folder or the account folder is made or changed -- the safety's buttons included."""
    acct.pin()
    acct.settle(1194.0, at(21, 14))
    acct.seen_now()
    srv = _serve(D)
    try:
        before = _files(acct.acct, acct.bot)
        asked = 0
        for key, cb in D.app.callback_map.items():
            if 'callback' not in cb:                   # (runs in the browser only)
                continue
            outs = [dict(zip(('id', 'property'), o.rsplit('.', 1))) for o in key.strip('.').split('...')]
            for sym in (None, SYM, '../' + SYM):
                ins = [dict(i, value=sym if i['id'] == 'symbol' else None) for i in cb['inputs']]
                body = {'output': key, 'outputs': outs if key.startswith('..') else outs[0], 'inputs': ins,
                        'state': [dict(i, value=None) for i in cb.get('state', [])],
                        'changedPropIds': [f"{ins[0]['id']}.{ins[0]['property']}"]}
                status, text = _post(srv.server_port, body)
                assert status in (200, 204), (key, status, text[-800:])
                asked += 1
        assert asked >= 30 and not differs(_files(acct.acct, acct.bot), before)
        assert acct.controls()['block'] is not None and acct.controls()['enabled'] is True
    finally:
        srv.shutdown()


def test_the_refresh_callback_fills_the_bar_and_says_which_buttons_apply(D, acct):
    """_safety_view, called as the tick calls it: the two parts of the bar, its colour class, what the files said
    (for the next press), which of the three buttons and the PIN field are shown, and the three questions."""
    acct.pin()
    acct.seen_now()
    show, hide = {}, {'display': 'none'}
    head, view, cls, seen, unblock, off, on, pin_field, q_unblock, q_off, q_on = D._safety_view(1, SYM, None)
    assert cls == 'safetybar sb-pos' and seen == {'period': 'start', 'enabled': True, 'scope': None}
    assert (unblock, off, on, pin_field) == (hide, show, hide, show)
    assert 'SAFETY ON' in _text(head) and 'Drop from the high (account)' in _text(view)
    assert q_off == (f'Turn the safety OFF for account {TAIL}? No drop, daily-loss or losing-trades limit will stop '
                     'new trades of either bot until you turn it ON. Anything blocked now may trade at once.')
    acct.settle(1194.0, NOW + 20.0)
    acct.clock(NOW + 30.0)
    acct.seen_now()
    head, view, cls, seen, unblock, off, on, pin_field, q_unblock, q_off, q_on = D._safety_view(2, SYM, None)
    assert cls == 'safetybar sb-neg' and (unblock, off, on, pin_field) == (show, show, hide, show)
    assert q_unblock.startswith(f'Unblock account {TAIL}? Counting starts again from now for both bots')
    D.safety.press(acct.acct, 'off', None, 'command line', NOW + 31.0, need_pin=False)
    head, view, cls, seen, unblock, off, on, pin_field, q_unblock, q_off, q_on = D._safety_view(3, SYM, None)
    assert cls == 'safetybar sb-warn' and (unblock, off, on, pin_field) == (hide, hide, show, hide)
    assert seen['enabled'] is False and q_on.startswith(f'Turn the safety ON for account {TAIL}?')
    # a symbol the page does not have, and no folder at all: the bar is still drawn
    for sym in ('../x', None, 7):
        assert 'SAFETY' in _text(D._safety_view(4, sym, None)[0])
    D.JSON_DIR = str(acct.root / 'nowhere' / 'bot_output')
    out = D._safety_view(5, SYM, None)
    assert out[2] == 'safetybar sb-idle' and out[3] == {'period': 'start', 'enabled': True, 'scope': None}


def test_a_bar_that_cannot_be_worked_out_keeps_its_buttons(D, acct, monkeypatch):
    """A fault in the bar's own code must not take the buttons away: the fallback says what failed, keeps what the
    files say for the next press, and the press still goes through safety.press."""
    pin = acct.pin()
    acct.seen_now()

    def boom(*a, **k):
        raise RuntimeError('a file of a shape nobody expected')
    monkeypatch.setattr(D, 'safety_meters', boom)
    m = D.safety_state(SYM, D.load(SYM))
    assert m['seen'] == {'period': 'start', 'enabled': True} and m['show']['off'] is True
    assert 'The safety bar could not be drawn (RuntimeError' in m['notes'][0][1]
    out = D._safety_view(1, SYM, None)
    assert out[3] == {'period': 'start', 'enabled': True} and out[5] == {}
    text, ok, _ = acct.press('safety-off', pin, seen=m['seen'])
    assert ok and acct.controls()['enabled'] is False


# ───────────────────────────── real money: the badge, the chip, the tiles ─────────────────────────────

def _live_sections(balance=1512.40):
    return dict(
        account={'balance': balance, 'equity': balance + 9.3, 'margin': 18.4, 'margin_free': balance - 9.1,
                 'margin_level': 8120.5, 'floating_own': 12.4, 'floating_account': -3.1, 'units': 1, 'lot': 0.01,
                 'day_realised': 12.4, 'login_tail': TAIL, 'server': 'Fake-Real', 'currency': 'USD', 'leverage': 200},
        sizing={'share': 0.5, 'account_balance': balance, 'sizing_balance': round(balance / 2, 2), 'step': 1250,
                'units': 1, 'lot': 0.01, 'unit_max': 10, 'next_unit_at_account_balance': 2500.0, 'source': 'balance'},
        health={'uptime_s': 600.0, 'loop_ms': 20.0, 'trace_ms': 1.0, 'started_utc': '2026-11-21T13:55:00Z'})


def test_the_real_money_badge_the_chip_and_the_seven_tiles(D, acct):
    """Beside the title: LIVE · REAL MONEY. The chip: 'Real account ...5678 · hedging', green when the bot accepted
    its account. The seven tiles in their places, with the real account's own figures."""
    acct.settle(1512.40, at(21, 0, 0, 6))
    acct.poll(1512.40, NOW - 2.0)
    acct.trace(**_live_sections())
    with open(os.path.join(acct.bot, f'{SYM}_trades.json'), 'w', encoding='utf-8') as f:
        json.dump({'t': NOW - 5.0, 'closed': [], 'summary': {'net': 37.25, 'closed': 3}, 'since_t': at(21)}, f)
    os.makedirs(os.path.join(acct.bot, 'state'), exist_ok=True)
    with open(os.path.join(acct.bot, 'state', 'live_start.json'), 'w', encoding='utf-8') as f:
        json.dump({'time': at(20, 9), 'account_balance': 1500.0, 'login_tail': TAIL}, f)
    d = D.load(SYM)
    status = json.loads(_text(D.status_bar(SYM, d)))
    text = _text(status)
    for bad in ERROR_CARD:
        assert not found(text, bad)
    assert '"LIVE · REAL MONEY", "className": "badge badge-live"' in text
    assert f'Real account {TAIL} · hedging' in text and '"chip chip-pos"' in text and 'Account refused' not in text

    tiles = []

    def walk(o):
        if isinstance(o, dict):
            p = o.get('props') or {}
            if str(p.get('className') or '').startswith('tile'):
                kids = p.get('children') or []
                tiles.append(tuple(_plain(k) for k in kids if k))
                return
            for v in p.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    def _plain(o):
        if isinstance(o, dict):
            return _plain((o.get('props') or {}).get('children'))
        if isinstance(o, list):
            return ''.join(_plain(x) for x in o)
        return '' if o is None else str(o)
    walk(status)
    assert [t[0] for t in tiles] == ['Account balance', 'Unit · lot', 'Open P/L (this bot)', 'Closed P/L (this bot)',
                                     'Equity (account)', 'Free margin · margin level', 'Bot running']
    assert tiles[0][1:] == ('$1,512.40', 'today +$12.40, booked by both bots · since 00:00 UTC')
    assert tiles[1][1:] == ('1 · 0.01 lot', 'half of $1,512.40 = $756.20 -> 1 unit (0.01 lot); 2 units from an '
                                            'account balance of $2,500')
    assert tiles[2][1:] == ('+$12.40', 'account: -$3.10')
    assert tiles[3][1:] == ('+$37.25', 'since 20 Nov 2026, its first live start')
    assert tiles[4][1:] == ('$1,521.70', 'balance + open P/L of both bots')
    assert tiles[5][1:] == ('$1,503 · 8,120%', 'margin in use $18.40')
    assert tiles[6][1] == '10.0 min'
    # the layout names the bot as what it is, and the old words are gone from the whole page
    layout = _text(D.serve_layout())
    assert 'real money' in layout and '"id": "safety-pin"' in layout and '"type": "password"' in layout


def test_the_tiles_of_other_days(D, acct):
    """A bot that was not running at 00:00 counts today from its first poll; a unit at its cap; a balance that is
    not known: no new trade, said; an account the bot refuses is never shown as a real account."""
    acct.settle(1500.0, at(21, 8, 30, 4))
    acct.poll(1500.0, NOW - 2.0)
    s = _live_sections(1500.0)
    s['account'].pop('day_realised')                   # (worked out from the day's own start balance then)
    acct.trace(**s)
    text = _text(D.status_bar(SYM, D.load(SYM)))
    assert 'today $0.00, booked by both bots · since 08:30 (the bot was not running at 00:00)' in text
    assert f'{SYM}_trades.json is missing' in text     # the closed P/L is not known: a dash, not $0.00
    s['sizing'].update(units=10, lot=0.1, sizing_balance=20000.0, account_balance=40000.0,
                       next_unit_at_account_balance=None, source='entry')
    acct.trace(**s)
    assert ('half of $40,000.00 = $20,000.00 -> 10 units (0.10 lot); 10 units is the most this bot trades (as counted '
            'when the open trade opened)') in _text(D.status_bar(SYM, D.load(SYM)))
    s['sizing'].update(sizing_balance=None, account_balance=None)
    acct.trace(**s)
    assert 'the account balance is not known: no new trade until it is' in _text(D.status_bar(SYM, D.load(SYM)))
    s['health'].update(account_ok=False, account_problem=f'MetaTrader 5 is logged into account ...9876, not {TAIL}',
                       trade_mode_name='demo', login_tail='...9876')
    acct.trace(**s)
    text = _text(D.status_bar(SYM, D.load(SYM)))
    assert 'Account refused: MetaTrader 5 is logged into account ...9876' in text and not found(text, 'Real account')
    assert '"chip chip-neg"' in text
    # a trace of nulls: dashes, no error
    acct.trace(account=None, sizing=None, health=None, safety=None)
    text = _text(D.status_bar(SYM, D.load(SYM)))
    for bad in ERROR_CARD:
        assert not found(text, bad)
    assert 'LIVE · REAL MONEY' in text


def _ident(text, label):
    """The value of one item of the line under the symbol ('magic ', 'branch ', 'account ') in a status bar's text."""
    m = re.search(re.escape(json.dumps(label)) + r', \{"props": \{"children": "([^"]*)"', text)
    return m.group(1) if m else None


def test_the_line_under_the_symbol_names_this_bot_with_its_magic_number_as_the_terminal_shows_it(D, acct):
    """This branch's own name, account and magic number -- the magic in plain digits, as the Magic column of
    MetaTrader 5 shows it (never with a thousands separator). A trace written by another bot (another branch or magic
    number in the file: a folder of another bot, or one left from before) is said in red; the line still names this
    bot, and the trades list gives the same plain magic number."""
    magic = D._C.MAGIC
    acct.seen_now()
    text = _text(D.status_bar(SYM, D.load(SYM)))      # (a trace without a magic of its own: this branch's)
    assert (_ident(text, 'magic '), _ident(text, 'branch '), _ident(text, 'account ')) == \
        (str(magic), D.BRANCH, str(D.ACCOUNT_SLOT))
    assert not found(text, f'{magic:,}') and not found(text, "another bot's")
    acct.trace(magic=magic)                            # what the bot writes: its own magic number
    text = _text(D.status_bar(SYM, D.load(SYM)))
    assert _ident(text, 'magic ') == str(magic) and not found(text, "another bot's")
    acct.trace(magic=26126, branch='hedging_btcusd2')  # (an old bot's numbers)
    text = _text(D.status_bar(SYM, D.load(SYM)))
    assert "This trace is another bot's (branch hedging_btcusd2, magic 26126)" in text
    assert '"chip chip-neg"' in text and _ident(text, 'magic ') == str(magic) and _ident(text, 'branch ') == D.BRANCH
    assert not found(text, '26,126')
    acct.trace(magic=float(magic))                     # (the same number written as a float is the same bot)
    assert not found(_text(D.status_bar(SYM, D.load(SYM))), "another bot's")
    with open(os.path.join(acct.bot, f'{SYM}_trades.json'), 'w', encoding='utf-8') as f:
        json.dump({'t': NOW - 5.0, 'closed': [], 'summary': {}, 'magic': magic}, f)
    listed = _text(D.trades_list(D.load(SYM)))
    assert f'(its magic {magic})' in listed and not found(listed, f'{magic:,}')
    assert (D.id_text(123456), D.id_text(123456.0), D.id_text('123456'), D.id_text(None)) == \
        ('123456', '123456', '123456', '—')
    # a real account's tickets have 9 or 10 digits: they too are shown as the terminal shows them
    ticket = 1234567890
    legs = _text(D.legs_table([{'n': 1, 'ticket': ticket, 'open_t': NOW - 60, 'price': 2650.5, 'lots': 0.01}], 2))
    row = _text(D.trade_row(1, {'id': ticket, 'side': 'BUY', 'legs': [{'position_id': ticket, 'side': 'BUY'}]}, 2))
    for text in (legs, row):
        assert f'"{ticket}"' in text and not found(text, '1,234,567,890')


# ───────────────────────────── the banners of what needs the owner ─────────────────────────────

def _banners(D, acct, **sections):
    acct.trace(**sections)
    d = D.load(SYM)
    return [json.loads(_text(b)) for b in D.state_banners(SYM, d, D.safety_state(SYM, d))]


def _said(banners):
    """[(the banner's class, its words)] -- the words without the mark in front."""
    def plain(o):
        if isinstance(o, dict):
            return plain((o.get('props') or {}).get('children'))
        if isinstance(o, list):
            return ''.join(plain(x) for x in o)
        return '' if o is None else str(o)
    return [(b['props']['className'], plain(b['props']['children'][1:])) for b in banners]


def test_a_healthy_bot_has_no_banner_and_a_trace_without_the_new_sections_raises_nothing(D, acct):
    acct.seen_now()
    assert _banners(D, acct) == []
    assert _banners(D, acct, foreign={'positions': 0, 'examples': [], 'old_bot_age_s': None,
                                      'old_bot_same_terminal': False}, open_hold=None,
                    health={'trading_not_allowed': [], 'disk_low': False}) == []
    for odd in ({'foreign': None, 'open_hold': None, 'health': None, 'safety': None, 'account': None},
                {'foreign': [], 'open_hold': 'x', 'health': {'trading_not_allowed': 'yes', 'disk_low': 'no'}},
                {'foreign': {'positions': None, 'examples': None, 'old_bot_age_s': 'soon'}, 'open_hold': {'why': None}}):
        assert _banners(D, acct, **odd) == [], odd
    # files left by an old bot that stopped long ago are not "an old bot is running"
    assert _banners(D, acct, foreign={'positions': 0, 'old_bot_age_s': 86400.0 * 30, 'old_bot_same_terminal': False}) == []


@pytest.mark.parametrize('key, words', [
    ('algo_trading_off', 'Algo Trading is switched off in MetaTrader 5: the bot can neither open nor close.'),
    ('python_api_disabled', 'MetaTrader 5 does not let Python programs trade'),
    ('account_trade_disabled', 'Trading is switched off for this account at the broker'),
    ('account_expert_disabled', 'The broker does not allow automated trading on this account'),
    ('something_new', 'MetaTrader 5 does not let the bot trade (something_new): the bot can neither open nor close.'),
])
def test_the_banner_when_the_bot_can_neither_open_nor_close(D, acct, key, words):
    acct.seen_now()
    said = _said(_banners(D, acct, health={'trading_not_allowed': [key]}))
    assert len(said) == 1 and said[0][0] == 'statebar statebar-red'
    assert words in said[0][1] and 'the bot can neither open nor close' in said[0][1]
    assert 'only the emergency stop at the broker' in said[0][1]


def test_the_banners_of_other_activity_on_the_account(D, acct):
    """Trades that are not this bot's (with whose they are, when their magic number says so); an old bot on the same
    MetaTrader 5 (red) or on another one (amber, only while its files are fresh); MetaTrader 5 switched to another
    account."""
    acct.seen_now()
    foreign = {'positions': 2, 'old_bot_age_s': None, 'old_bot_same_terminal': False, 'examples': [
        {'ticket_tail': '...4521', 'magic': 0, 'comment': '', 'volume': 0.01, 'side': 'BUY', 'sl': 0.0, 'tp': 5300.0,
         'price_open': 2650.0},
        {'ticket_tail': '...4533', 'magic': 270113, 'comment': 'x', 'volume': 0.02, 'side': 'SELL', 'sl': 2700.0,
         'tp': 0.0, 'price_open': 2640.0}]}
    said = _said(_banners(D, acct, foreign=foreign))
    assert len(said) == 1 and said[0][0] == 'statebar statebar-red'
    assert said[0][1].startswith(f"Trades that are not this bot's are open on {SYM} in this account (magic 0, magic "
                                 '270113). Nothing manages them here: close them yourself. If the old ladder bot still '
                                 "runs on this account, stop it: it will add to or close this bot's trades.")
    assert '2 such trades' in said[0][1] and 'ticket ...4521' in said[0][1]
    assert 'magic 270113: the gold bot of account 1' in said[0][1]
    assert D.magic_words(270324) == 'magic 270324: the BTC bot of account 3' and D.magic_words(271023).endswith('account 10')
    assert D.magic_words(26126) == 'magic 26126' and D.magic_words(0) == 'magic 0' and D.magic_words(None) == 'magic unknown'
    said = _said(_banners(D, acct, foreign={'positions': 0, 'old_bot_age_s': 3.0, 'old_bot_same_terminal': True}))
    assert said == [('statebar statebar-red', said[0][1])] and said[0][1].startswith(
        'An old bot is running on this server and uses the same MetaTrader 5. It trades whatever account that '
        "MetaTrader 5 is logged into, and it would add to and close this bot's trades.")
    assert 'turning the safety OFF does not change that' in said[0][1]
    said = _said(_banners(D, acct, foreign={'positions': 0, 'old_bot_age_s': 40.0, 'old_bot_same_terminal': False}))
    assert said[0][0] == 'statebar statebar-amber' and said[0][1].startswith('An old bot is running on this server')
    assert 'its files changed 40 s ago' in said[0][1] and 'another MetaTrader 5' in said[0][1]
    said = _said(_banners(
        D, acct, foreign={'positions': 0, 'old_bot_age_s': 2.0, 'old_bot_same_terminal': True},
        health={'account_ok': False, 'login_tail': '...9876', 'own_login_tail': TAIL},
        basket={'open': {'side': 'BUY', 'legs': [{'ticket': 1}, {'ticket': 2}]}}))
    assert said == [('statebar statebar-red', 'MetaTrader 5 was switched to account ...9876. This bot has 2 open '
                                              f'trades it cannot manage. Stop the old bot, then log MetaTrader 5 back into {TAIL}.')]


def test_the_banners_of_two_bots_that_do_not_agree(D, tmp_path):
    """The two bots of an account on different accounts, or with different account limits (red), from the bot's own
    comparison in its view; and a bot whose account folder is not the one this page reads."""
    a = Account(D, tmp_path / 'accounts', partner_login=87654321)
    a.poll(1500.0, NOW - 4.0)
    a.seen_now()
    said = _said(_banners(D, a))
    assert len(said) == 1 and said[0][0] == 'statebar statebar-red'
    assert said[0][1].startswith(f'The two bots of account {D.ACCOUNT_SLOT} are logged into different accounts '
                                 f'({TAIL} and ...4321).')
    assert f'mt5_credentials.json of {D.BRANCH} and {D.PARTNER_BRANCH}' in said[0][1]
    b = Account(D, tmp_path / 'limits', limits=(20.0, 10.0, 10), partner_limits=(25.0, 15.0, 10))
    b.poll(1500.0, NOW - 4.0)
    b.seen_now()
    said = _said(_banners(D, b))
    assert len(said) == 1 and said[0][0] == 'statebar statebar-red'
    assert said[0][1].startswith(f'The two bots of account {D.ACCOUNT_SLOT} have different safety limits.')
    assert 'drop 20%, day 10%' in said[0][1] and 'drop 25%, day 15%' in said[0][1]
    c = Account(D, tmp_path / 'folders')
    c.seen_now()
    elsewhere = str(tmp_path / 'elsewhere' / D.ACCOUNT_FOLDER)
    c.trace(dict(c.me.view(), account_dir=elsewhere))
    d = D.load(SYM)
    said = _said([json.loads(_text(x)) for x in D.state_banners(SYM, d, D.safety_state(SYM, d))])
    assert len(said) == 1 and said[0][0] == 'statebar statebar-red'
    assert said[0][1].startswith('This page and the bot use different account folders.') and elsewhere in said[0][1]
    assert 'a button pressed here does not reach the bot' in said[0][1]


def test_the_banners_of_a_full_disk_and_of_refused_orders(D, acct):
    acct.seen_now()
    said = _said(_banners(D, acct, health={'disk_low': True}))
    assert said[0][0] == 'statebar statebar-red' and said[0][1].startswith('DISK_LOW: less than 2 GB is free')
    said = _said(_banners(D, acct, open_hold={'why': 'refused_backoff', 'side': 'BUY', 'kind': 'entry', 'price': 2650.0,
                                              'until': NOW + 28.0, 'refusals': 37}))
    assert said[0][0] == 'statebar statebar-amber'
    assert said[0][1].startswith("The broker refuses this bot's new orders (37 refusals). The bot tries again at "
                                 '14:05:28: after 4 minutes of refusals only every 30 seconds, after 15 minutes every '
                                 'minute. Orders that close a trade are always sent at once.')
    # held for another reason: no banner (the bar and the headline say it); the Live tab names the reason
    assert _banners(D, acct, open_hold={'why': 'safety', 'side': 'BUY', 'kind': 'add'}) == []
    acct.trace(open_hold={'why': 'safety', 'side': 'BUY', 'kind': 'add'}, decision={'action': 'HOLD', 'headline': 'x'})
    assert 'add held: the safety blocks new trades' in _text(D.now_header(D.load(SYM)))


def test_what_the_page_says_of_a_full_disk_a_login_by_hand_and_the_python_api_option_is_true(D, acct):
    """A nearly full disk stops only the everyday log lines (DEBUG, INFO) and the samples: orders, fills, closes,
    warnings, errors and the journal go on (tracelog.LogWriter). A terminal logged in by hand is found within about a
    minute (35 s at a start, up to the 60 s back-off of a reconnect), not 30 s. The MetaTrader 5 option has one name
    in every text. active_config.json is the bot's file."""
    acct.seen_now()
    banner = _said(_banners(D, acct, health={'disk_low': True}))[0][1]
    meaning = next(m for c, _, m, _ in D.ISSUE_KINDS if c == 'DISK_LOW')
    for text in (banner, meaning):
        assert 'only warnings and errors' not in text and '(DEBUG, INFO) and the per-minute samples out' in text
        assert 'rders, fills, closes, warnings, errors and the journal are still written' in text
    login_wait = [t for c, _, _, t in D.ISSUE_KINDS if c == 'LOGIN_WAIT'] + [D.LOGIN_WAIT_TODO['no_password']]
    for text in login_wait:
        assert 'within 30 seconds' not in text and 'starts by itself within about a minute' in text
    app_tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    app_words = next(ast.literal_eval(n.value) for n in app_tree.body
                     if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', None) == '_TRADING_NOT_ALLOWED')
    texts = [app_words['python_api_disabled'], D.TRADING_OFF_WORDS['python_api_disabled'][0],
             D.TRADING_OFF_TODO['python_api_disabled']]
    for text in texts:
        assert '"Disable automatic trading via external Python API"' in text, text
    constants = (ROOT / 'constants.py').read_text(encoding='utf-8')
    line = next(x for x in constants.splitlines() if x.startswith('ACTIVE_CONFIG_FILENAME'))
    assert 'Dashboard writes' not in line and 'The bot writes' in line
    source = (ROOT / 'dashboard.py').read_text(encoding='utf-8')
    assert source.count('ACTIVE_CONFIG_FILENAME') == 1                  # (imported, never opened)


def test_the_banner_of_refused_orders_names_when_the_refusals_began(D, acct):
    """app.py's _open_hold carries 'since' -- the first refusal of the streak -- when why is refused_backoff: the
    amber banner says since when (UTC), how many, and when the next try is."""
    acct.seen_now()
    said = _said(_banners(D, acct, open_hold={'why': 'refused_backoff', 'side': 'SELL', 'kind': 'add', 'price': 2650.0,
                                              'until': NOW + 28.0, 'refusals': 12, 'since': NOW - 300.0}))
    assert said[0][0] == 'statebar statebar-amber'
    assert said[0][1].startswith("The broker refuses this bot's new orders since 14:00 (12 refusals). The bot tries "
                                 'again at 14:05:28')
    # a refused_backoff without the time (an older bot) leaves it out, and one refusal is "1 refusal"
    said = _said(_banners(D, acct, open_hold={'why': 'refused_backoff', 'until': None, 'refusals': 1, 'since': None}))
    assert said[0][1].startswith("The broker refuses this bot's new orders (1 refusal). The bot tries again: after")


def _readme_refs(text):
    """Every 'README, section N[, step(s) a[ and b]]' of a text: [(section, [steps])]."""
    out = []
    for m in re.finditer(r'README, section (\d+)(?:(?: "[^"]+")?, steps? (\d+)(?: and (\d+))?)?', text):
        out.append((int(m.group(1)), [int(x) for x in m.group(2, 3) if x]))
    return out


def _readme_parts():
    """{section: its text} and {step of section 2: its text}, from README.md as the branch has it."""
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    sections = {}
    for m in re.finditer(r'^## (\d+)\. .*?(?=^## |\Z)', text, re.S | re.M):
        sections[int(m.group(1))] = m.group(0)
    steps = {}
    first = sections.get(2, '')
    for m in re.finditer(r'^(\d+)\. \*\*.*?(?=^\d+\. \*\*|\Z)', first, re.S | re.M):
        steps[int(m.group(1))] = m.group(0)
    return sections, steps


# what each place of the README the advice texts point to must be about (a word of its own text)
README_WORDS = {(2, 2): 'Stop the old bots', (2, 3): 'start_job.bat live', (2, 4): 'Login to Trade Account',
                (2, 5): 'login_pass', (2, 7): 'netsh advfirewall', (2, 9): 'safety_pin.txt',
                (3, None): 'Unblock', (5, None): 'collect_logs.bat', (6, None): 'What to do'}


def test_every_advice_of_the_real_money_kinds_points_to_a_readme_place_that_says_it(D):
    """The issue kinds of the real-money layer (spec 14) -- and LOGIN_WAIT for each of its six reasons, and
    TRADING_NOT_ALLOWED for each of its four switches -- tell the owner what to do and where the README says more:
    every 'README, section N, step M' they name is there, and is about it."""
    sections, steps = _readme_parts()
    assert set(sections) >= {1, 2, 3, 4, 5, 6, 7} and set(steps) >= set(range(1, 11))
    kinds = {c: todo for c, _, _, todo in D.ISSUE_KINDS}
    texts = {code: kinds[code] for code in (
        'OLD_ACCOUNT', 'SERVER_MISMATCH', 'ACCOUNT_CLAIM', 'WRONG_MODE', 'DESIGN_REFUSED', 'TERMINAL_IN_USE',
        'LOGIN_REFUSED', 'LOGIN_WAIT', 'ACCOUNT_KIND', 'ACCOUNT_REFUSED', 'SYMBOLS_FILE', 'CREDENTIALS_FILE',
        'ACCOUNT_NOT_KNOWN', 'BOT_LOGIN', 'TRADING_NOT_ALLOWED', 'STATE_OTHER_ACCOUNT', 'OLD_BOT_SAME_TERMINAL',
        'OLD_BOT_RUNNING', 'FOREIGN_POSITIONS', 'OTHER_PROGRAM', 'SAFETY_ERROR', 'SAFETY_BLOCKED', 'SAFETY_SKIP',
        'CLOSE_RESULT_UNKNOWN', 'TURTLE_ADDS_STOPPED', 'BUY_REFUSED', 'SELL_REFUSED', 'BUY_MORE_REFUSED',
        'SELL_MORE_REFUSED', 'DISK_LOW')}
    assert set(D.LOGIN_WAIT_TODO) == {'no_password', 'claim_unreadable', 'terminal_claimed', 'login_budget',
                                      'budget_unreadable', 'budget_unwritable'}
    assert set(D.TRADING_OFF_TODO) == set(D.TRADING_OFF_WORDS)
    texts.update({f'LOGIN_WAIT {k}': v for k, v in D.LOGIN_WAIT_TODO.items()})
    texts.update({f'TRADING_NOT_ALLOWED {k}': v for k, v in D.TRADING_OFF_TODO.items()})
    wrong = []
    for name, todo in texts.items():
        refs = _readme_refs(todo)
        if not refs:
            wrong.append(f'{name}: no README place named')
        for section, at in refs:
            if section not in sections:
                wrong.append(f'{name}: section {section} is not in README.md')
            for step in at or [None]:
                if section == 2 and step is not None and step not in steps:
                    wrong.append(f'{name}: section 2 has no step {step}')
                    continue
                word = README_WORDS.get((section, step)) or README_WORDS.get((section, None))
                where = steps.get(step, '') if (section == 2 and step is not None) else sections.get(section, '')
                if word is None:
                    wrong.append(f'{name}: README, section {section}{f", step {step}" if step else ""} is not a place '
                                 'the advice may point to')
                elif word not in where:
                    wrong.append(f'{name}: README, section {section}{f", step {step}" if step else ""} does not say '
                                 f'{word!r}')
    assert not wrong, wrong
    # (and their words are the owner's)
    shown = json.dumps([D.LOGIN_WAIT_TODO, D.TRADING_OFF_TODO]).lower()
    assert not [w for w in ('epoch', 'latch', 'rebase', 'period', 'slot', 'virtual', 'demo') if w in shown]


def _event(msg, level='WARN', **kv):
    return {'t': NOW - 60.0, 'level': level, 'cat': 'ACCOUNT', 'msg': msg, 'kv': kv}


def test_the_advice_of_login_wait_follows_its_reason_and_trading_not_allowed_its_switches(D, acct):
    """LOGIN_WAIT: the line the bot writes when MetaTrader 5 shows no account and it may not log in itself now names
    the reason in `why`; the advice is that reason's. In Changes & issues the newest line's advice is shown.
    TRADING_NOT_ALLOWED: the advice of each switch the line names (its `reasons`)."""
    text = ('LOGIN_WAIT: MetaTrader 5 at C:\\MT5\\terminal64.exe is not logged into any account. Log it into ...5678 by '
            'hand (File > Login to Trade Account, Save password). The bot does not log in itself: {}. It looks again '
            'every 30 seconds.')
    for why, reason, words in (
            ('no_password', 'mt5_credentials.json holds no password for it', 'holds no password the bot can use'),
            ('terminal_claimed', 'this MetaTrader 5 belongs to account 3 (...4321)', 'a MetaTrader 5 installation of its own'),
            ('login_budget', "the bot's own login was refused at 02:14 UTC and it tries the password again at 02:29 UTC",
             'it waits before it tries the password again'),
            ('claim_unreadable', 'the file that says which account this MetaTrader 5 belongs to cannot be read right now',
             'terminal_claims'),
            ('budget_unreadable', "the record of the bot's last own login cannot be read right now", 'cannot be read'),
            ('budget_unwritable', "the record of the bot's own logins cannot be written (OSError: x)", 'cannot be written')):
        code, meaning, todo = D.issue_kind(_event(text.format(reason), event='LOGIN_WAIT', why=why))
        assert code == 'LOGIN_WAIT' and todo == D.LOGIN_WAIT_TODO[why] and words in todo, why
    # a line without a why (an older bot), or with one this page does not know: the kind's own advice
    generic = next(t for c, _, _, t in D.ISSUE_KINDS if c == 'LOGIN_WAIT')
    assert D.issue_kind(_event(text.format('x'), event='LOGIN_WAIT'))[2] == generic
    assert D.issue_kind(_event(text.format('x'), event='LOGIN_WAIT', why='brand_new'))[2] == generic
    # Changes & issues: two reasons in the events file, the newest one's advice
    logs = os.path.join(acct.bot, 'logs')
    os.makedirs(logs, exist_ok=True)
    day = datetime.fromtimestamp(NOW, tz=timezone.utc).strftime('%Y-%m-%d')
    with open(os.path.join(logs, f'{SYM}_{day}_events.jsonl'), 'w', encoding='utf-8') as f:
        for k, why in enumerate(('no_password', 'login_budget')):
            e = _event(text.format(why), level='WARN', event='LOGIN_WAIT', why=why)
            e['t'] = NOW - 600.0 + 60.0 * k
            f.write(json.dumps(e) + '\n')
    D._EVENTS_CACHE.clear()
    rows = {r['code']: r for r in D.issues(SYM)[0]}
    assert rows['LOGIN_WAIT']['count'] == 2 and rows['LOGIN_WAIT']['todo'] == D.LOGIN_WAIT_TODO['login_budget']
    # TRADING_NOT_ALLOWED: the advice of each switch, in the line's order
    off = 'MetaTrader 5 does not let this bot trade: x. Until that is changed the bot can neither open nor close.'
    todo = D.issue_kind(_event(off, level='ERROR', event='TRADING_NOT_ALLOWED',
                               reasons=['python_api_disabled', 'algo_trading_off']))[2]
    assert todo == D.TRADING_OFF_TODO['python_api_disabled'] + ' ' + D.TRADING_OFF_TODO['algo_trading_off']
    assert D.issue_kind(_event(off, level='ERROR', event='TRADING_NOT_ALLOWED'))[2] == next(
        t for c, _, _, t in D.ISSUE_KINDS if c == 'TRADING_NOT_ALLOWED')


def test_a_trade_that_ended_without_the_bot_is_said_for_24_hours(D, acct):
    """From the trades file: a trade closed by the emergency stop at the broker, a stop-out or by hand in the last
    24 hours, with what its deals say; one the bot closed itself, or an older one, is not."""
    acct.seen_now()

    def trade(k, reason, text, close_t, pnl, deals):
        return {'id': k, 'side': 'BUY', 'legs': [{'position_id': k, 'deal_reasons': deals}], 'close_t': close_t,
                'close_price': 2650.5, 'pnl': pnl, 'exit_reason': reason, 'exit_reason_text': text}
    doc = {'t': NOW - 5.0, 'summary': {}, 'closed': [
        trade(1, 'backstop', 'the broker\'s stop', NOW - 30 * 3600.0, -20.0, ['sl']),          # older than a day
        trade(2, 'target', 'target', NOW - 3 * 3600.0, 15.0, ['expert']),                      # the bot's own close
        trade(3, 'backstop', 'the broker\'s stop', NOW - 2 * 3600.0, -24.5, ['sl']),
        trade(4, 'closed_outside', 'closed outside the bot', NOW - 3600.0, 3.2, ['client', 'mobile'])]}
    with open(os.path.join(acct.bot, f'{SYM}_trades.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f)
    said = _said(_banners(D, acct))
    assert len(said) == 1 and said[0][0] == 'statebar statebar-amber'
    assert said[0][1].startswith('A trade of this bot was closed by something else. In the last 24 hours 2 trades '
                                 'ended without the bot deciding it')
    assert "the broker's stop; the deals say: sl), -$24.50" in said[0][1]
    assert 'closed outside the bot; the deals say: client, mobile), +$3.20' in said[0][1]
    assert '-$20.00' not in said[0][1] and '+$15.00' not in said[0][1]


def test_what_happened_once_shows_for_24_hours_through_the_issues_list(D, acct):
    """STATE_OTHER_ACCOUNT, OTHER_PROGRAM and CLOSE_RESULT_UNKNOWN are moments, not states of the trace: their line
    of the log shows as a banner for 24 hours (and stays in Changes & issues). A saved trade of another account is
    said in the bot's own words (they name that account and say what to do: SPEC 3.5), red; a state file of another
    account that held no open trade is only a line of Changes & issues."""
    acct.seen_now()
    logs = os.path.join(acct.bot, 'logs')
    os.makedirs(logs)
    day = datetime.fromtimestamp(NOW, tz=timezone.utc).strftime('%Y-%m-%d')
    other = ("This bot's saved trade belongs to account ...1234. If its positions are still open there, close them by "
             'hand. (The file XAUUSDm_state.json was written on account ...1234, not on this bot\'s ...5678: it was put '
             'aside as XAUUSDm_state.json.other-account-20261121_130500, and the bot starts without it.)')
    lines = [
        {'t': NOW - 3600.0, 'level': 'ERROR', 'cat': 'STATE', 'msg': other,
         'kv': {'event': 'STATE_OTHER_ACCOUNT', 'held_open_trade': True, 'file_login_tail': '...1234'}},
        {'t': NOW - 1800.0, 'level': 'WARN', 'cat': 'EVENT', 'msg': 'CLOSE_RESULT_UNKNOWN: the result of trade 7 was '
                                                                     'not found in the deal history for 600 s'},
        {'t': NOW - 30 * 3600.0, 'level': 'WARN', 'cat': 'EVENT', 'msg': "OTHER_PROGRAM: another program closed this "
                                                                          "bot's trade at 08:05 UTC"}]
    path = os.path.join(logs, f'{SYM}_{day}_events.jsonl')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(''.join(json.dumps(x) + '\n' for x in lines))
    said = _said(_banners(D, acct))
    assert [x[0] for x in said] == ['statebar statebar-red', 'statebar statebar-amber']
    assert said[0][1] == 'STATE_OTHER_ACCOUNT (13:05). ' + other
    assert said[1][1].startswith('CLOSE_RESULT_UNKNOWN (13:35). The result of a closed trade could not be read')
    rows = {r['code']: r for r in D.issues(SYM)[0]}
    assert set(rows) == {'STATE_OTHER_ACCOUNT', 'CLOSE_RESULT_UNKNOWN', 'OTHER_PROGRAM'}
    assert rows['OTHER_PROGRAM']['count_24h'] == 0     # older than a day: in the list, no banner
    # another program within the day: amber, with what it means and what to do
    lines.append({'t': NOW - 600.0, 'level': 'ERROR', 'cat': 'ACCOUNT', 'kv': {'event': 'OTHER_PROGRAM'},
                  'msg': "another program closed this bot's trade at 13:55 UTC"})
    # a state file of another account without an open trade: no banner (the issue list has it)
    lines[0] = dict(lines[0], msg='The file XAUUSDm_state.json was written on account ...1234, not on this bot\'s '
                                  '...5678: it was put aside, and the bot starts without it.',
                    kv={'event': 'STATE_OTHER_ACCOUNT', 'held_open_trade': False})
    with open(path, 'w', encoding='utf-8') as f:
        f.write(''.join(json.dumps(x) + '\n' for x in lines))
    said = _said(_banners(D, acct))
    assert [x[0] for x in said] == ['statebar statebar-amber', 'statebar statebar-amber']
    assert said[0][1].startswith('OTHER_PROGRAM (13:55). Another program traded this bot\'s symbol in this account')
    assert 'then press Unblock' in said[0][1] and said[1][1].startswith('CLOSE_RESULT_UNKNOWN (13:35).')
    assert 'STATE_OTHER_ACCOUNT' in {r['code'] for r in D.issues(SYM)[0]}
    # one start that put two files aside: the one that held a trade is said, though the line of the other came later
    lines.insert(0, {'t': NOW - 3610.0, 'level': 'ERROR', 'cat': 'STATE', 'msg': other,
                     'kv': {'event': 'STATE_OTHER_ACCOUNT', 'held_open_trade': True}})
    with open(path, 'w', encoding='utf-8') as f:
        f.write(''.join(json.dumps(x) + '\n' for x in lines))
    said = _said(_banners(D, acct))
    assert [x[0] for x in said] == ['statebar statebar-amber', 'statebar statebar-red', 'statebar statebar-amber']
    assert said[1][1] == 'STATE_OTHER_ACCOUNT (13:04). ' + other


def test_a_block_and_the_banners_reach_every_tab_and_the_alert_store(D, acct):
    """The status callback (every tab, every 5 s): the banners in the banner area, the block as the alert banner,
    and in the alert store for the optional sound and browser notification -- together with a position that is close
    to its stop, when there is one."""
    acct.settle(1194.0, at(21, 14))
    acct.seen_now()
    acct.trace(health={'disk_low': True})
    status, banners, alert = D._status(1, SYM)
    text = _text(banners)
    assert 'DISK_LOW: less than 2 GB is free' in text and 'statebar statebar-red' in text
    assert 'alertbar alertbar-red' in text and 'ACCOUNT BLOCKED: ' in text
    assert alert['level'] == 'red' and alert['key'].startswith('safety:account_blocked:start:')
    assert alert['head'] == 'ACCOUNT BLOCKED: ' and 'neither bot of the account opens a new trade' in alert['text']
    assert not found(text, 'the Live tab has the details')  # (the words of the closeness banner)
    # the browser notification of a block is titled by the block's own words, not as a position "Very close"
    assert "var head = alert.head || (red ? 'Very close: ' : 'Getting close: ');" in SRC
    assert 'new Notification(head + document.title' in SRC
    close = {'level': 'amber', 'text': 'BUY basket 75% of the way to its stop loss ($2.00 away)', 'key': 'stop:amber:X'}
    both = D.combined_alert(D.safety_state(SYM, D.load(SYM))['alert'], close)
    assert both['level'] == 'red' and both['key'].endswith('|stop:amber:X') and 'Getting close: BUY basket' in both['text']
    assert D.combined_alert(None, close) is close
    assert D.combined_alert(None, {'level': None, 'text': None, 'key': None}) == {'level': None, 'text': None, 'key': None}
    assert 'Getting close: ' in _text(D.alert_banner(close)) and 'the Live tab has the details' in _text(D.alert_banner(close))


# ───────────────────────────── the account number is nowhere; the source ─────────────────────────────

def test_the_page_made_by_hand_holds_no_account_number_and_no_fingerprint_of_it(D, acct):
    """The trace and the state files of a real-money bot hold the last 4 digits and, to recognise the account, its
    fingerprint. The raw views show neither a `login` key nor the fingerprint (8 digits are found from their
    fingerprint by trying them all), and no file of the account folder; the settings never show the fingerprints of
    the old accounts."""
    pin = acct.pin()
    acct.seen_now()
    sha = D.safety.login_sha(LOGIN)
    os.makedirs(os.path.join(acct.bot, 'state'), exist_ok=True)
    state = {'version': 1, 'login_sha': sha, 'login_tail': TAIL, 'login': LOGIN, 'login_id': str(LOGIN),
             'branch': D.BRANCH, 'basket': {'own_login': LOGIN, 'side': 'BUY'}, 'legs': [{'login': LOGIN, 'id': 5}]}
    for name in (f'{SYM}_state.json', f'{SYM}_turtle.json', 'live_start.json', 'safety_closes.json'):
        with open(os.path.join(acct.bot, 'state', name), 'w', encoding='utf-8') as f:
            json.dump(state, f)
    acct.trace(health={'login': LOGIN, 'demo_login': LOGIN})          # (a trace of the old kind: full numbers)
    raw = _text(D.raw_view(SYM))
    assert not found(raw, str(LOGIN)) and not found(raw, sha) and TAIL in raw and '"side": "BUY"' in raw.replace('\\"', '"')
    assert 'safety state of this bot' in raw and 'basket state' in raw
    for name in os.listdir(acct.acct):                 # no file of the account folder is a raw file
        assert not found(raw, name), name
    assert not found(raw, pin)
    settings = _text(D.settings_view(SYM, D.load(SYM)))
    assert not found(settings, 'OLD_LOGINS_SHA256')
    for value in D._C.OLD_LOGINS_SHA256:
        assert not found(settings, value)
    assert 'ACCOUNT_FOLDER' in settings and 'SAFETY_DROP_PCT' in settings and 'ACCOUNT_SHARE' in settings
    assert D.hidden_setting('OLD_LOGINS_SHA256') and D.hidden_setting('SAFETY_PIN') and D.hidden_setting('login_pass')
    assert D.hidden_setting('API_SECRET') and not D.hidden_setting('SAFETY_DROP_PCT') and not D.hidden_setting('MAGIC')
    assert D.without_logins({'login': 1, 'login_tail': TAIL, 'own_login_tail': TAIL, 'login_sha': 'x', 'a': [{'login_id': 2}]}) \
        == {'login_tail': TAIL, 'own_login_tail': TAIL, 'a': [{}]}
    # the whole page in every state of this file: the bar, the status bar, the banners, the layout
    d = D.load(SYM)
    page = _text([D._safety_view(1, SYM, None), D._status(1, SYM), D.serve_layout(), D.status_bar(SYM, d)])
    assert not found(page, sha) and not found(page, pin)
    assert not found(page.replace(str(acct.root), ''), str(LOGIN))        # (pytest's own folder names may hold digits)


def test_the_settings_come_from_the_journals_start_line(D, acct):
    """History & settings reads the newest `start` line of the bot's journal (kept for good), so the settings a bot
    started with months ago are still there after the text log of that day was deleted; what constants.py holds
    now is marked when it differs; the deployment block is its own group."""
    acct.seen_now()
    started = at(21, 13, 55)
    os.makedirs(os.path.join(acct.bot, 'journal'))
    consts = {'BRANCH': D.BRANCH, 'DESIGN_NAME': 'journal_design', 'STRATEGY': 'basket', 'ACCOUNT_SHARE': 0.25,
              'SAFETY_DROP_PCT': 33.0, 'OLD_LOGINS_SHA256': ['f' * 64], 'CANDLE_COUNT': 300, 'SAFETY_PIN': '1'}
    lines = [{'t': started - 86400.0, 'kind': 'start', 'constants': dict(consts, DESIGN_NAME='the start before')},
             {'t': started - 10.0, 'kind': 'order', 'action': 'start of an order'},
             {'t': started, 'kind': 'start', 'version': '3.9.2-live.1', 'constants': consts,
              'account': {'login_tail': TAIL, 'login': LOGIN, 'server': 'Fake-Real', 'balance': 1500.0}},
             {'t': started + 3600.0, 'kind': 'start', 'constants': dict(consts, DESIGN_NAME='a later start')}]
    with open(D.journal_path(SYM, 2026), 'w', encoding='utf-8') as f:
        f.write(''.join(json.dumps(x) + '\n' for x in lines) + '{"kind": "start", cut in the mid')
    acct.trace(health={'started_utc': '2026-11-21T13:55:00Z'})
    text = _text(D.settings_view(SYM, D.load(SYM)))
    assert 'as the bot wrote them when it started, 2026-11-21 13:55:00 UTC (its journal)' in text
    assert 'journal_design' in text and not found(text, 'the start before') and not found(text, 'a later start')
    assert 'constants.py now' in text and not found(text, 'OLD_LOGINS_SHA256') and not found(text, 'SAFETY_PIN') and not found(text, 'f' * 64)
    assert 'This branch: the bot, its account, its share and its safety limits' in text
    assert not found(text, str(LOGIN)) and 'Fake-Real' in text
    assert set(D.deploy_keys()) >= {'BRANCH', 'PARTNER_BRANCH', 'ACCOUNT_FOLDER', 'MAGIC', 'OUTPUT_DIR', 'ACCOUNT_SHARE',
                                    'SAFETY_DROP_PCT', 'SAFETY_DAY_PCT', 'SAFETY_STREAK_N', 'LOG_KEEP_DAYS'}
    assert 'OLD_LOGINS_SHA256' not in D.deploy_keys()
    # no journal and no log of the start day: constants.py as the dashboard read it, the hidden names still hidden
    os.remove(D.journal_path(SYM, 2026))
    D._CONFIG_CACHE.clear()
    text = _text(D.settings_view(SYM, D.load(SYM)))
    assert "constants.py as the dashboard read it at its start" in text and not found(text, 'OLD_LOGINS_SHA256')


def test_the_events_reader_takes_the_two_newest_day_files(D, acct):
    """One events file per UTC day: the views read the two existing files with the newest dates (so a start that was
    refused before days without the bot is still found), each cached by itself; the Log tab reads the file of the
    day that is selected."""
    acct.seen_now()
    logs = os.path.join(acct.bot, 'logs')
    os.makedirs(logs)
    for day, hour in (('2026-11-14', 9), ('2026-11-19', 10), ('2026-11-21', 11)):
        t = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() + hour * 3600
        with open(os.path.join(logs, f'{SYM}_{day}_events.jsonl'), 'w', encoding='utf-8') as f:
            f.write(json.dumps({'t': t, 'level': 'WARN', 'cat': 'DATA', 'msg': f'line of {day}'}) + '\n')
        with open(os.path.join(logs, f'{SYM}_{day}.log'), 'w', encoding='utf-8') as f:
            f.write(f'{day} {hour:02d}:00:00.000 UTC | WARN | DATA | line of {day}\n')
    with open(os.path.join(logs, f'OTHER_2026-11-22_events.jsonl'), 'w', encoding='utf-8') as f:
        f.write(json.dumps({'t': NOW, 'level': 'ERROR', 'cat': 'X', 'msg': 'another symbol'}) + '\n')
    assert [d_ for d_, _ in D.events_files(SYM)] == ['2026-11-21', '2026-11-19', '2026-11-14']
    assert [os.path.basename(p) for p in D.events_paths(SYM)] == [f'{SYM}_2026-11-19_events.jsonl',
                                                                  f'{SYM}_2026-11-21_events.jsonl']
    evs, cut, problem = D.read_events(SYM)
    assert [e['msg'] for e in evs] == ['line of 2026-11-19', 'line of 2026-11-21'] and not cut and problem is None
    assert {os.path.basename(k[0]) for k in D._EVENTS_CACHE} == {f'{SYM}_2026-11-19_events.jsonl',
                                                                 f'{SYM}_2026-11-21_events.jsonl'}
    first = D._EVENTS_CACHE[(os.path.join(logs, f'{SYM}_2026-11-19_events.jsonl'), D.EVENTS_TAIL_BYTES)]
    D.read_events(SYM)
    assert D._EVENTS_CACHE[(os.path.join(logs, f'{SYM}_2026-11-19_events.jsonl'), D.EVENTS_TAIL_BYTES)] is first
    count, rows, _ = D._log(0, 'log', SYM, list(D.LOG_LEVELS), '', [], 200, 'events', '2026-11-21', 'live', None)
    assert 'line of 2026-11-19' in _text(rows) and 'line of 2026-11-21' in _text(rows) and not found(_text(rows), 'another symbol')
    count, rows, _ = D._log(0, 'log', SYM, list(D.LOG_LEVELS), '', [], 200, 'events', '2026-11-14', 'live', None)
    assert 'line of 2026-11-14' in _text(rows) and not found(_text(rows), 'line of 2026-11-21')
    assert f'{SYM}_2026-11-14_events.jsonl' in count
    files, opts, day = D._log_files(0, 'log', SYM, None)
    assert f'kept: today and the last {D.LOG_KEEP_DAYS} days' in _text(D.serve_layout())
    assert f'{SYM}_2026-11-21_events.jsonl' in _text(files) and 'journal' in _text(files)
    assert D.read_events('../' + SYM) == ([], False, 'missing')


# ── the source ──

SRC = (ROOT / 'dashboard.py').read_text(encoding='utf-8')


def test_the_wording_of_dashboard_py_is_a_real_accounts(D):
    """No text of dashboard.py calls this bot, its account or its balance by the words of the forward test it came
    from: no string literal (docstrings aside) says demo, virtual or slot. And what the owner reads on the bar holds
    none of the words the spec keeps away from him."""
    assert wording_offenders(ROOT / 'dashboard.py') == []
    shown = json.dumps([D.SAFETY_LABELS, D.SAFETY_NOTE, D.PIN_WARNING, D.HOLD_WORDS, D.TRADING_OFF_WORDS,
                        [(c, m, t) for c, _, m, t in D.ISSUE_KINDS]]).lower()
    for word in ('epoch', 'latch', 'rebase', 'period', 'slot', 'virtual', 'demo account'):
        assert not found(shown, word), word
    # the advice of every issue kind points at the README of the real-money branches
    assert not found(SRC, 'How to run') and not found(SRC, 'LIVE_TERMINAL_PATH') and not found(SRC, 'VIRTUAL_')
    for code, _, meaning, todo in D.ISSUE_KINDS:
        assert meaning and todo, code
    codes = [c for c, _, _, _ in D.ISSUE_KINDS]
    assert len(codes) == len(set(codes))
    for code in ('OLD_ACCOUNT', 'SERVER_MISMATCH', 'TRADING_NOT_ALLOWED', 'FOREIGN_POSITIONS', 'OLD_BOT_SAME_TERMINAL',
                 'OLD_BOT_RUNNING', 'OTHER_PROGRAM', 'STATE_OTHER_ACCOUNT', 'LOGIN_REFUSED', 'LOGIN_WAIT', 'SAFETY_ERROR',
                 'SAFETY_SKIP', 'SAFETY_BLOCKED', 'CLOSE_RESULT_UNKNOWN', 'TURTLE_ADDS_STOPPED', 'BUY_REFUSED',
                 'SELL_REFUSED', 'BUY_MORE_REFUSED', 'SELL_MORE_REFUSED', 'DISK_LOW', 'TERMINAL_IN_USE'):
        assert code in codes, code


def test_only_the_action_callback_presses_and_always_with_the_pin_required():
    """The source: dashboard.py names neither the PIN file nor a press without the PIN; safety.press is called in
    exactly one place, with need_pin=True and the page's `expect`; the PIN file is made only when the dashboard is
    started as a program, where it also prints where the file is and that the PIN is not encrypted -- in plain ASCII,
    because the launcher sets no UTF-8 mode."""
    assert not found(SRC, 'safety_pin') and not found(SRC, 'need_pin=False') and not found(SRC, 'need_pin = False')
    tree = ast.parse(SRC)
    presses = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == 'press']
    assert len(presses) == 1 and SRC.count('.press(') == 1
    kw = {k.arg: k.value for k in presses[0].keywords}
    assert isinstance(kw['need_pin'], ast.Constant) and kw['need_pin'].value is True and 'expect' in kw
    owner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                 and any(c is presses[0] for c in ast.walk(n)))
    assert owner.name == 'safety_action'
    callers = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name != 'safety_action'
               and any(isinstance(c, ast.Call) and getattr(c.func, 'id', None) == 'safety_action' for c in ast.walk(n))]
    assert callers == ['_safety_press']
    # the start as a program
    main = next(n for n in tree.body if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                and getattr(n.test.left, 'id', None) == '__name__')
    in_main = {id(c) for c in ast.walk(main)}
    made = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == 'ensure_pin']
    assert len(made) == 1 and id(made[0]) in in_main
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'print':
            holder = next(f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                          and any(c is n for c in ast.walk(f)))
            assert holder.name == '_say'               # the one print of the file: ASCII, whatever the text
    said = [c.value for n in ast.walk(main) for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
    assert said and all(s.isascii() for s in said)
    assert any('PIN' in s for s in said) and 'PIN_WARNING' in ast.unparse(main) and 'http://localhost:{DASHBOARD_PORT}' in SRC
    assert 'ensure_pin' in ast.unparse(main) and 'pin_path' in ast.unparse(main)


def test_the_page_uses_nothing_newer_than_dash_2_14(D):
    """The tests run on Dash 2.14, the server on 2.18: no `running=`, no Patch, no set_props, no duplicate outputs."""
    for word in ('running=', 'Patch(', 'set_props', 'allow_duplicate', 'background=', 'on_error'):
        assert not found(SRC, word), word
    # the three buttons are three fixed things behind their own question; nothing toggles
    layout = _text(D.serve_layout())
    for button, label in (('safety-unblock', 'Unblock'), ('safety-off', 'Turn safety OFF'), ('safety-on', 'Turn safety ON')):
        assert re.search(r'"type": "ConfirmDialogProvider"', layout) and f'"id": "{button}"' in layout and label in layout
    assert layout.count('"type": "ConfirmDialogProvider"') == 3 and not found(layout, 'toggle')
    assert '"autoComplete": "off"' in layout and '"persistence": false' in layout
    assert D.PIN_WARNING in layout and D.PIN_WARNING == (
        'The page has no login and the PIN is sent without encryption: on a network you do not trust, press the '
        'buttons on the server or run safety.bat.')
    assert json.dumps(D.safety.pin_path(D.account_dir()))[1:-1] in layout              # the path, never the PIN
    keys = list(D.app.callback_map)
    assert sum('safety-result.children' in k for k in keys) == 1      # one action callback
    assert layout.index('"id": "safety"') < layout.index('"className": "topbar"') < layout.index('"className": "tabbar"')


def test_the_account_folder_is_worked_out_at_call_time(D, tmp_path):
    """ACCOUNT_DIR = None: the account folder is the one beside JSON_DIR, as the bot derives it from its OUTPUT_DIR;
    a test points either of them elsewhere."""
    D.JSON_DIR, D.ACCOUNT_DIR = str(tmp_path / 'a' / 'bot_output'), None
    assert D.account_dir() == str(tmp_path / 'a' / D.ACCOUNT_FOLDER) == D.safety.account_dir(D.JSON_DIR, D.ACCOUNT_FOLDER)
    D.JSON_DIR = str(tmp_path / 'b' / 'bot_output')
    assert D.account_dir() == str(tmp_path / 'b' / D.ACCOUNT_FOLDER)
    D.ACCOUNT_DIR = str(tmp_path / 'c')
    assert D.account_dir() == str(tmp_path / 'c')
    D.ACCOUNT_DIR = None
    assert not os.path.exists(str(tmp_path / 'b'))     # (looking never makes a folder)
    assert D.ACCOUNT_FOLDER == sys.modules['constants'].ACCOUNT_FOLDER
    assert 'ACCOUNT_DIR = None' in SRC
