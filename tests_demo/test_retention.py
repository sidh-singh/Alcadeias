"""
The files of a real-money bot that grow, and what bounds them (tracelog.py; spec section 8).

  * logs/: the three day files of the bot's symbol (the text log, the events, the samples). Today and the
    LOG_KEEP_DAYS (7) UTC days before it are kept; a file goes only when its name is one of the three day patterns,
    by the date in the name -- never by its age on the disk --, oldest first, at the start, at every new UTC day and
    once an hour. The strategy log, another symbol's files and every other name stay.
  * Past 50 MB in a day the text log and the events file take only WARN and ERROR lines; past 100 MB one 'N lines
    dropped' line a minute. All day files together stay under LOG_MAX_BYTES: the oldest days go, never today's.
  * With less than 2 GB free on the disk DEBUG / INFO lines and the samples are dropped, and the trace says so.
  * Temp files a killed process left of the bot's own files go after a day: only those names, only in the bot's
    folder itself and in state/.
  * daily_trade/<SYMBOL>/ keeps its newest 400 day files.
  * Nothing else is ever deleted: no state file, no file set aside, not the journal, nothing of dash_env.
Sizes here are small numbers given to the writer; the real ones are the module's constants (checked at the end).
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import DEFAULTS, F, START
from conftest import found

SYMBOL = 'XAUUSDm'
DAY = datetime.fromtimestamp(START, tz=timezone.utc).strftime('%Y-%m-%d')
SUFFIXES = ('.log', '_events.jsonl', '_samples.jsonl')        # the three day files of a symbol


def day(days_back, t=START):
    return f'{datetime.fromtimestamp(t - days_back * 86400, tz=timezone.utc):%Y-%m-%d}'


def rec(t, level='INFO', msg='hello', kv=None):
    return (t, level, 'TEST', msg, kv, None, None)


def names(folder):
    return sorted(os.listdir(folder))


def seed_days(folder, days, symbol=SYMBOL, text='x\n'):
    """The three day files of `symbol` for each of `days` (days back from START)."""
    for d in days:
        for suffix in SUFFIXES:
            (folder / f'{symbol}_{day(d)}{suffix}').write_text(text)


def days_left(folder, symbol=SYMBOL):
    """{suffix: the days (back from START) that still have that day file}."""
    out = {s: [] for s in SUFFIXES}
    for n in os.listdir(folder):
        for s in SUFFIXES:
            if n.startswith(symbol + '_2') and n.endswith(s) and len(n) == len(symbol) + 11 + len(s):
                try:
                    d = datetime.strptime(n[len(symbol) + 1:len(symbol) + 11], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                except ValueError:
                    continue                                       # (a name that only looks like a day file)
                out[s].append(round((START - START % 86400 - d.timestamp()) / 86400))
    return {s: sorted(v) for s, v in out.items()}


class Clock:
    def __init__(self, t=START):
        self.t = float(t)

    def __call__(self):
        return self.t


# ───────────────────────────── retention: by name and date ─────────────────────────────

def test_day_files_and_their_retention(mods, tmp_path):
    """Today and the 7 UTC days before it are kept, for each of the three day files; older ones go at the first
    write and again when a new UTC day begins. Everything else in the folder stays: the strategy log, another
    symbol's old files, names that only look like a day file."""
    tl = mods().tracelog
    w = tl.LogWriter(tmp_path, SYMBOL, journal_dir=tmp_path / 'journal')
    assert w.keep_days == DEFAULTS['LOG_KEEP_DAYS'] == tl.LOG_KEEP_DAYS == 7
    seed_days(tmp_path, (1, 5, 7, 8, 9, 60))
    seed_days(tmp_path, (9, 60), symbol='BTCUSDm')
    seed_days(tmp_path, (60,), symbol=SYMBOL + 'x')                    # a symbol whose name begins with this one's
    others = [f'{SYMBOL}_strategy_log.json', f'{SYMBOL}_events.jsonl', f'{SYMBOL}_events.1.jsonl',
              f'{SYMBOL}_{day(60)}.txt', f'{SYMBOL}_{day(60)}.log.bak', f'{SYMBOL}_{day(60)}_events.jsonl.old',
              f'{SYMBOL}_2026-99-99.log', f'x{SYMBOL}_{day(60)}.log', f'{SYMBOL}_{day(60)}_trades.jsonl', 'notes.txt']
    for n in others:
        (tmp_path / n).write_text('kept\n')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / f'{SYMBOL}_{day(60)}.log').write_text('kept\n')
    midnight = (int(START) // 86400 + 1) * 86400
    assert w.write([rec(START), rec(midnight - 0.001)], samples=[(START, '{"t":1}')])
    assert days_left(tmp_path) == {s: [0, 1, 5, 7] for s in SUFFIXES}          # the 8th day back and older are gone
    assert days_left(tmp_path, 'BTCUSDm') == {s: [9, 60] for s in SUFFIXES}    # another symbol's files: not touched
    assert days_left(tmp_path, SYMBOL + 'x') == {s: [60] for s in SUFFIXES}
    assert w.write([rec(midnight + 0.5)], samples=[(midnight + 0.5, '{"t":2}')])   # a new UTC day: retention again
    assert days_left(tmp_path) == {s: [-1, 0, 1, 5] for s in SUFFIXES}         # the day that was 7 back is 8 back now
    for n in others:
        assert (tmp_path / n).read_text() == 'kept\n', n
    assert (tmp_path / 'sub' / f'{SYMBOL}_{day(60)}.log').exists()
    today = (tmp_path / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    assert today[-1].startswith(f'{DAY} 23:59:59.999 UTC | INFO | TEST | hello')
    assert (tmp_path / f'{SYMBOL}_{day(-1)}.log').read_text(encoding='utf-8').startswith(f'{day(-1)} 00:00:00.500 UTC')
    assert (tmp_path / f'{SYMBOL}_{day(-1)}_samples.jsonl').read_text() == '{"t":2}\n'


def test_a_day_file_goes_by_the_date_in_its_name_never_by_its_age_on_the_disk(mods, tmp_path):
    """A file of 30 days ago that was touched a minute ago goes; a file of yesterday whose time on the disk says
    last year stays. Oldest first."""
    tl = mods().tracelog
    seed_days(tmp_path, (1, 20, 30, 40))
    now = time.time()
    for n in os.listdir(tmp_path):
        old = day(1) in n
        os.utime(tmp_path / n, (now - (400 * 86400 if old else 60),) * 2)
    removed = []
    real = os.remove

    def spying_remove(path):
        removed.append(os.path.basename(str(path)))
        return real(path)
    tl.os.remove, keep = spying_remove, tl.os.remove
    try:
        w = tl.LogWriter(tmp_path, SYMBOL, journal_dir=tmp_path / 'journal')
        assert w.write([rec(START)])
    finally:
        tl.os.remove = keep
    assert days_left(tmp_path)['.log'] == [0, 1] and days_left(tmp_path)['_samples.jsonl'] == [1]
    assert [n[len(SYMBOL) + 1:len(SYMBOL) + 11] for n in removed] == [day(40)] * 3 + [day(30)] * 3 + [day(20)] * 3


def test_retention_deletes_a_day_file_named_in_another_case(mods, tmp_path):
    """On Windows a day begun by a start that failed before symbols.json was read can be named XAUUSDM_<day>.log: it
    is still this bot's file."""
    tl = mods().tracelog
    old = day(40)
    (tmp_path / f'{SYMBOL.upper()}_{old}.log').write_text('x\n')
    (tmp_path / f'{SYMBOL.upper()}_{old}_EVENTS.JSONL').write_text('x\n')
    w = tl.LogWriter(tmp_path, SYMBOL, journal_dir=tmp_path / 'journal')
    assert w.write([rec(START)])
    assert not any(old in n for n in os.listdir(tmp_path)), os.listdir(tmp_path)


def test_retention_runs_at_the_start_at_a_new_day_and_once_an_hour(mods, tmp_path):
    """An old day file that appears while the bot runs (or could not be deleted before) goes within the hour, not
    only at the next midnight; a file that cannot be deleted is skipped and the others still go."""
    tl = mods().tracelog
    clock = Clock()
    w = tl.LogWriter(tmp_path, SYMBOL, journal_dir=tmp_path / 'journal', clock=clock)
    seed_days(tmp_path, (20,))
    assert w.write([rec(clock.t)])                                     # the start
    assert days_left(tmp_path)['.log'] == [0]
    seed_days(tmp_path, (30, 31))
    stuck = f'{SYMBOL}_{day(31)}.log'
    real = os.remove

    def refusing(path):
        if os.path.basename(str(path)) == stuck:
            raise PermissionError(13, 'The process cannot access the file because it is being used')
        return real(path)
    clock.t += 1800
    assert w.write([rec(clock.t)])
    assert days_left(tmp_path)['.log'] == [0, 30, 31]                  # half an hour later: not yet
    tl.os.remove, keep = refusing, tl.os.remove
    try:
        clock.t += 1801
        assert w.write([rec(clock.t)])                                 # the hour is over: they go, but for the held one
    finally:
        tl.os.remove = keep
    assert days_left(tmp_path) == {'.log': [0, 31], '_events.jsonl': [0], '_samples.jsonl': []}
    clock.t += 3601
    assert w.write([rec(clock.t)])                                     # ... which goes an hour later
    assert days_left(tmp_path)['.log'] == [0]


@pytest.mark.parametrize('given, kept', [(0, 1), (-5, 1), (1, 1), (3, 3), ('7', 7), (None, 7), ('seven', 7)])
def test_the_days_kept_are_at_least_one(mods, tmp_path, given, kept):
    """LogWriter uses max(1, days): with 0 the file of today would be deleted at every start. What is not a number
    counts as the default."""
    tl = mods().tracelog
    w = tl.LogWriter(tmp_path, SYMBOL, keep_days=given, journal_dir=tmp_path / 'journal')
    assert w.keep_days == kept
    seed_days(tmp_path, (0, kept, kept + 1))
    assert w.write([rec(START)])
    assert days_left(tmp_path)['.log'] == [0, kept] and (tmp_path / f'{SYMBOL}_{DAY}.log').stat().st_size > 2


def test_the_trace_takes_the_days_kept_from_the_branch(mods, tmp_path):
    """LOG_KEEP_DAYS of the deployment block reaches the writer; the journal lies beside the logs, not in them."""
    m = mods(LOG_KEEP_DAYS=3)
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=tmp_path / 'bot_output')
    tr = bot._tracer(SYMBOL)
    assert tr.writer.keep_days == 3
    assert tr.writer.dir == str(tmp_path / 'bot_output' / 'logs')
    assert tr.writer.journal_dir == str(tmp_path / 'bot_output' / 'journal')


# ───────────────────────────── the caps of a day ─────────────────────────────

def test_past_the_days_cap_only_warn_and_error_lines_and_past_the_stop_a_count_a_minute(mods, tmp_path):
    """The text log and the events file alike (each on its own size): past day_cap only WARN and ERROR lines are
    added, with one line that says so; past day_stop nothing more, but one 'N lines dropped' line a minute. A new
    UTC day starts afresh."""
    tl = mods().tracelog
    clock = Clock()
    w = tl.LogWriter(tmp_path, SYMBOL, day_cap=6000, day_stop=12000, journal_dir=tmp_path / 'journal', clock=clock)
    levels = ('INFO', 'DEBUG', 'ORDER', 'FILL', 'CLOSE', 'WARN', 'ERROR')
    for i in range(700):
        clock.t = START + i
        assert w.write([rec(clock.t, level=levels[i % 7], msg=f'line {i}', kv={'i': i})])
    for name, parse in ((f'{SYMBOL}_{DAY}.log', lambda ln: ln.split(' | ')[1:4:2]),
                        (f'{SYMBOL}_{DAY}_events.jsonl', lambda ln: [json.loads(ln)['level'], json.loads(ln)['msg']])):
        lines = (tmp_path / name).read_text(encoding='utf-8').splitlines()
        rows = [parse(ln) for ln in lines]
        note = [k for k, (lv, msg) in enumerate(rows) if msg.startswith('this file passed ')]
        assert len(note) == 1 and rows[note[0]][0] == 'WARN', name
        assert '6000' not in rows[note[0]][1] and 'only WARN and ERROR lines' in rows[note[0]][1]
        before, after = rows[:note[0]], rows[note[0] + 1:]
        assert {lv for lv, _ in before} == set(levels)                       # every level, up to the cap
        size_before = len('\n'.join(lines[:note[0]]).encode()) + 1
        assert 6000 - 300 <= size_before <= 6000 + 300, (name, size_before)
        drops = [k for k, (lv, msg) in enumerate(after) if ' lines dropped: this file is past ' in msg]
        assert drops and {lv for lv, _ in after[:drops[0]]} == {'WARN', 'ERROR'}, name
        # past the stop: nothing but the count, once a minute (a line a second came in)
        tail = after[drops[0]:]
        assert all(' lines dropped: ' in msg and lv == 'WARN' for lv, msg in tail), name
        counts = [int(msg.split(' ', 1)[0]) for _, msg in tail]
        assert counts[0] >= 1 and all(c == 60 for c in counts[1:]) and 2 <= len(tail) <= 12
        size = os.path.getsize(tmp_path / name)
        assert 12000 <= size <= 12000 + 300 + 300 * len(tail), (name, size)
        # every line written or counted: the lines of the file, and those the counts name, are all 700 but the
        # INFO / DEBUG / ORDER / FILL / CLOSE lines left out between the cap and the stop, and the last count's rest
        kept = len(rows) - 1 - len(tail)
        assert kept + sum(counts) <= 700
    # the next UTC day: every line again
    midnight = (int(START) // 86400 + 1) * 86400
    clock.t = midnight + 5
    assert w.write([rec(clock.t, msg='a new day'), rec(clock.t, level='DEBUG', msg='with every level')])
    nxt = (tmp_path / f'{SYMBOL}_{day(-1)}.log').read_text(encoding='utf-8').splitlines()
    assert [ln.split(' | ')[3] for ln in nxt] == ['a new day', 'with every level']


def test_a_restart_keeps_counting_the_days_bytes(mods, tmp_path):
    """The cap is the day's, not the process's: a bot started again at noon finds the day's file as large as it is."""
    tl = mods().tracelog
    (tmp_path / f'{SYMBOL}_{DAY}.log').write_text('x' * 5000 + '\n')
    (tmp_path / f'{SYMBOL}_{DAY}_events.jsonl').write_text('{"x":"' + 'y' * 13000 + '"}\n')
    w = tl.LogWriter(tmp_path, SYMBOL, day_cap=6000, day_stop=12000, journal_dir=tmp_path / 'journal')
    assert w.write([rec(START + k, msg='m' * 150) for k in range(8)] + [rec(START + 9, level='ERROR', msg='an error')])
    text = (tmp_path / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    assert sum('| INFO | TEST | mmm' in ln for ln in text) == 8 and any('this file passed' in ln for ln in text)
    assert w.write([rec(START + 20, msg='left out'), rec(START + 21, level='WARN', msg='kept')])
    text = (tmp_path / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8')
    assert not found(text, 'left out') and '| WARN | TEST | kept' in text
    events = (tmp_path / f'{SYMBOL}_{DAY}_events.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(events) == 2 and 'lines dropped: this file is past' in events[1]   # already past the stop at the start


def test_all_day_files_together_stay_under_the_size_guard(mods, tmp_path):
    """LOG_MAX_BYTES per bot, today's files counted: the oldest days go first, in one pass, never today's; a file that
    cannot be deleted is skipped; when today's files alone are above it, nothing is deleted (and nothing hangs)."""
    tl = mods().tracelog
    clock = Clock()
    seed_days(tmp_path, (1, 2, 3, 4, 5), text='x' * 1000)             # 5 days x 3 files x 1000 bytes
    seed_days(tmp_path, (3,), symbol='BTCUSDm', text='x' * 50000)       # another symbol's: not counted, not touched
    (tmp_path / f'{SYMBOL}_strategy_log.json').write_text('x' * 50000)
    stuck = f'{SYMBOL}_{day(5)}_events.jsonl'
    real = os.remove

    def refusing(path):
        if os.path.basename(str(path)) == stuck:
            raise PermissionError(13, 'in use')
        return real(path)
    tl.os.remove, keep = refusing, tl.os.remove
    try:
        w = tl.LogWriter(tmp_path, SYMBOL, max_bytes=8000, journal_dir=tmp_path / 'journal', clock=clock)
        assert w.write([rec(clock.t)])
    finally:
        tl.os.remove = keep
    left = sorted(n for n in os.listdir(tmp_path) if n.startswith(SYMBOL + '_2'))
    total = sum(os.path.getsize(tmp_path / n) for n in left)
    assert total <= 8000 and stuck in left
    # oldest first: of day 5 only the file that could not be deleted is left, then day 4 went, then as much of day 3
    # as was needed
    assert not [n for n in left if day(5) in n and n != stuck] and not [n for n in left if day(4) in n]
    assert len([n for n in left if day(1) in n]) == len([n for n in left if day(2) in n]) == 3
    assert days_left(tmp_path, 'BTCUSDm') == {s: [3] for s in SUFFIXES}
    assert (tmp_path / f'{SYMBOL}_strategy_log.json').stat().st_size == 50000
    # today's files alone above the guard: they stay, and so does what could not be deleted
    (tmp_path / f'{SYMBOL}_{DAY}_events.jsonl').write_text('x' * 20000)
    clock.t += 3601
    t0 = time.perf_counter()
    assert w.write([rec(clock.t)])
    assert time.perf_counter() - t0 < 2.0
    left = sorted(n for n in os.listdir(tmp_path) if n.startswith(SYMBOL + '_2'))
    assert [n for n in left if DAY in n] == [f'{SYMBOL}_{DAY}.log', f'{SYMBOL}_{DAY}_events.jsonl']
    assert [n for n in left if DAY not in n] == []                      # every older day went for it


# ───────────────────────────── a disk that is nearly full ─────────────────────────────

def _usage(free):
    return lambda path: type('usage', (), {'total': 100 * 2 ** 30, 'used': 100 * 2 ** 30 - free, 'free': free})()


def test_with_little_free_space_only_what_matters_is_logged(mods, tmp_path, monkeypatch):
    """Under 2 GB free (asked once a minute): DEBUG and INFO lines and the samples are dropped; orders, fills, closes,
    warnings and errors are still logged, and the journal goes on. When there is room again every line is back."""
    tl = mods().tracelog
    clock = Clock()
    asked = []

    def usage(path):
        asked.append(path)
        return _usage(free[0])(path)
    free = [1 * 2 ** 30]
    monkeypatch.setattr(tl.shutil, 'disk_usage', usage)
    w = tl.LogWriter(tmp_path / 'logs', SYMBOL, journal_dir=tmp_path / 'journal', clock=clock)
    levels = ('DEBUG', 'INFO', 'ORDER', 'FILL', 'CLOSE', 'WARN', 'ERROR')
    for i in range(70):
        clock.t = START + i
        assert w.write([rec(clock.t, level=levels[i % 7], msg=f'line {i}')], samples=[(clock.t, '{"n":%d}' % i)],
                       journal=[(clock.t, 'order', json.dumps({'t': clock.t, 'utc': 'x', 'kind': 'order', 'n': i}))])
    assert w.disk_low is True and w.disk_free == 2 ** 30
    assert len(asked) == 2 and asked[0] == str(tmp_path)                 # once a minute (the nearest folder that exists)
    text = (tmp_path / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    assert len(text) == 50 and {ln.split(' | ')[1] for ln in text} == {'ORDER', 'FILL', 'CLOSE', 'WARN', 'ERROR'}
    events = (tmp_path / 'logs' / f'{SYMBOL}_{DAY}_events.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(events) == 50
    assert not (tmp_path / 'logs' / f'{SYMBOL}_{DAY}_samples.jsonl').exists()
    assert len((tmp_path / 'journal' / f'{SYMBOL}_{DAY[:4]}.jsonl').read_text().splitlines()) == 70
    free[0] = 5 * 2 ** 30
    clock.t = START + 130
    assert w.write([rec(clock.t, level='DEBUG', msg='back')], samples=[(clock.t, '{"n":"back"}')])
    assert w.disk_low is False
    assert (tmp_path / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()[-1].endswith('| back')
    assert (tmp_path / 'logs' / f'{SYMBOL}_{DAY}_samples.jsonl').read_text() == '{"n":"back"}\n'
    # a disk that cannot be asked keeps the last answer and never raises
    monkeypatch.setattr(tl.shutil, 'disk_usage', lambda path: (_ for _ in ()).throw(OSError('no such device')))
    clock.t += 61
    assert w.write([rec(clock.t, level='DEBUG', msg='still logged')]) and w.disk_low is False


def test_a_nearly_full_disk_is_in_the_trace_the_log_and_the_journal(mods, tmp_path, monkeypatch):
    """health.disk_low is the state the dashboard's red banner reads; the log has one ERROR line when it starts
    (event=DISK_LOW) and an INFO line when it ends; the journal the problem's start and its end."""
    m = mods()
    out = tmp_path / 'bot_output'
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    tr = bot._tracer(SYMBOL)
    free = [1 * 2 ** 30]
    monkeypatch.setattr(m.tracelog.shutil, 'disk_usage', lambda path: _usage(free[0])(path))

    def poll(dt):
        m.clock.now_ms += int(dt * 1000)
        tr.poll_skipped('positions', 'positions_get(XAUUSDm) returned None')
        with open(out / f'{SYMBOL}_trace.json', encoding='utf-8') as f:
            return json.load(f)
    assert poll(1)['health']['disk_low'] is False                       # (asked with this poll's own write)
    for _ in range(3):
        snap = poll(1)
    assert snap['health']['disk_low'] is True
    free[0] = 3 * 2 ** 30
    snap = poll(61)
    snap = poll(1)
    assert snap['health']['disk_low'] is False
    tr.poll({'state': {'basket': None, 'last_close': None}})            # a poll that read the terminal: problems end
    m.clock.now_ms += 61000
    tr.poll({'state': {'basket': None, 'last_close': None}})
    lines = (out / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    low = [ln for ln in lines if '| ERROR | DISK | ' in ln]
    assert len(low) == 1 and 'less than 2 GB is free on the disk' in low[0] and 'event=DISK_LOW' in low[0]
    assert 'collect_logs.bat' in low[0]
    assert sum('| INFO | DISK | there is room on the disk again' in ln for ln in lines) == 1
    with open(out / 'journal' / f'{SYMBOL}_{DAY[:4]}.jsonl', encoding='utf-8') as f:
        issues = [json.loads(ln) for ln in f if '"code":"DISK_LOW"' in ln]
    assert [x['state'] for x in issues] == ['start', 'end']


# ───────────────────────────── old temp files ─────────────────────────────

def _old(path, days=2.0):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_only_old_temp_files_of_the_bots_own_files_are_swept(mods, tmp_path):
    """A process killed between a write and its rename leaves '<file>.<pid>.tmp' (this module), '<file>.tmp' (app.py's
    state files) or '<file>.<pid>.<hex>.tmp' (the safety's state). After a day they go: only these names, only in the
    bot's folder itself and in state/. A young one may be a write in progress; any other name is not this bot's to
    delete; nothing below the two folders is looked at."""
    m = mods()
    out = tmp_path / 'bot_output'
    state = out / 'state'
    for folder in (state, out / 'journal', out / 'dash_env', out / 'daily_trade' / SYMBOL, out / 'logs'):
        folder.mkdir(parents=True)
    swept = [out / f'{SYMBOL}_trace.json.4242.tmp', out / f'{SYMBOL}_bars.json.1.tmp', out / f'{SYMBOL}_trades.json.77.tmp',
             state / f'{SYMBOL}_state.json.tmp', state / f'{SYMBOL}_turtle.json.tmp',
             state / f'{SYMBOL}_turtle_side.json.tmp', state / 'safety_state.json.4242.0a1b2c3d.tmp',
             state / 'safety_closes.json.tmp', state / 'safety_closes.json.9.tmp', state / 'live_start.json.31.ff00aa11.tmp',
             state / f'{SYMBOL}_journal_state.json.4242.tmp', state / f'{SYMBOL}_exit_reasons.json.4242.tmp',
             state / f'{SYMBOL}_turtle_trades.json.4242.tmp']
    kept_old = [out / 'notes.tmp', out / f'{SYMBOL}_trace.json.tmp.bak', out / f'{SYMBOL}_trace.json.abc.tmp',
                out / f'BTCUSDm_trace.json.4242.tmp', out / f'x{SYMBOL}_trace.json.4242.tmp',
                out / f'{SYMBOL}_trace.json.4242.zz.tmp', out / f'{SYMBOL}_trace.json.4242.tmp.old',
                out / f'{SYMBOL}_trace.json', out / f'{SYMBOL}.json', out / 'account.json',
                state / f'{SYMBOL}_state.json', state / 'safety_state.json', state / 'live_start.json',
                state / f'{SYMBOL}_journal_state.json.keep',
                state / 'safety_state.json.not-readable-20261101_000000',
                state / f'{SYMBOL}_state.json.other-account-20261101_000000',
                state / f'{SYMBOL}_turtle.json.other-account-20261101_000000',
                state / 'unknown.json.4242.tmp', state / f'{SYMBOL}.lock',
                out / 'journal' / f'{SYMBOL}_2026.jsonl', out / 'journal' / f'{SYMBOL}_2026.jsonl.4242.tmp',
                out / 'dash_env' / f'{SYMBOL}_trace.json.4242.tmp', out / 'daily_trade' / SYMBOL / 'x.json.tmp',
                out / 'logs' / f'{SYMBOL}_trace.json.4242.tmp', tmp_path / f'{SYMBOL}_trace.json.4242.tmp']
    young = [out / f'{SYMBOL}_trace.json.555.tmp', state / 'safety_closes.json.123.tmp']
    (state / f'{SYMBOL}_exit_reasons.json.dir.tmp').mkdir()              # (a folder is never removed)
    (state / f'{SYMBOL}_exit_reasons.json.5.tmp').mkdir()
    for p in swept + kept_old + young:
        p.write_text('{}')
    for p in swept + kept_old + [state / f'{SYMBOL}_exit_reasons.json.5.tmp']:
        _old(p)
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    bot.state_dir = None
    m.app.OUTPUT_DIR = m.constants.OUTPUT_DIR = str(out)
    tr = bot._tracer(SYMBOL)
    tr.poll_skipped('positions', 'x')                                    # the first poll: the start's sweep
    for p in swept:
        assert not p.exists(), p
    for p in kept_old + young:
        assert p.exists(), p
    assert (state / f'{SYMBOL}_exit_reasons.json.5.tmp').is_dir()
    assert m.tracelog.temp_file_of('safety_state.json.12.0a1B.tmp', {'safety_state.json'})
    for name in ('safety_state.json', 'safety_state.json.tmp.x', 'safety_state.json.0a1b.tmp', 'safety_state.jsonx.tmp',
                 'safety_state.json.12.0a1b.zz.tmp', 'safety_state.json.not-readable-20261101_000000',
                 'xsafety_state.json.tmp'):
        assert not m.tracelog.temp_file_of(name, {'safety_state.json'}), name


# The allow-list of the sweep, written here on its own (spec 8 and 14): the files this bot writes in its folder and
# in state/, and the three temp forms of them. Nothing else may ever go.
OWN_TOP = (f'{SYMBOL}_trace.json', f'{SYMBOL}_bars.json', f'{SYMBOL}_trades.json', f'{SYMBOL}.json', 'account.json',
           str(DEFAULTS['ACTIVE_CONFIG_FILENAME']))
OWN_STATE = (f'{SYMBOL}_state.json', f'{SYMBOL}_turtle.json', f'{SYMBOL}_turtle_side.json', 'safety_state.json',
             'safety_closes.json', 'live_start.json', f'{SYMBOL}_journal_state.json', f'{SYMBOL}_exit_reasons.json',
             f'{SYMBOL}_turtle_trades.json')
ASIDE = ('.not-readable-20261101_000000', '.other-account-20261101_000000')
ENDINGS = ('', '.tmp', '.1.tmp', '.4242.tmp', '.4242.0a1b2c3d.tmp', '.31.FF00AA11.tmp', '.tmp.tmp', '.x.tmp',
           '.4242.zz.tmp', '.4242.0a1b.zz.tmp', '.4242.tmp.old', '.0a1b.tmp', '..tmp', '.4242..tmp', '.-1.tmp',
           '.4242.0a1b2c3d', '.tmp~', '.TMP', ' .tmp', '.4242.0a1b2c3d.tmp.tmp')


def _allowed(folder_kind, name):
    """The rule of the sweep, as the spec words it: a temp file of one of the bot's own files of that folder."""
    import re
    own = {'top': OWN_TOP, 'state': OWN_STATE}.get(folder_kind, ())
    return any(re.fullmatch(re.escape(base) + r'(?:\.\d+(?:\.[0-9a-fA-F]+)?)?\.tmp', name) for base in own)


def test_the_temp_sweep_deletes_nothing_outside_its_allow_list(mods, tmp_path):
    """Every name built from the bot's own file names, the process lock state/<SYMBOL>.lock, the names of files set
    aside (<name>.not-readable-<time>, <name>.other-account-<time>) and another symbol's or another program's files,
    each with every ending of a list of near misses, in the bot's folder, in state/ and in four folders the sweep must
    not look into -- all of them two days old, the lock held by the bot as a running one holds it. After the sweep
    exactly the temp files of the allow-list (the rule above, written apart from the code) are gone; every other file
    is there, unchanged (the bot's own files themselves aside: it writes them), and the lock is still held."""
    m = mods()
    out = tmp_path / 'bot_output'
    state = out / 'state'
    others = {'journal': out / 'journal', 'dash_env': out / 'dash_env', 'logs': out / 'logs',
              'daily': out / 'daily_trade' / SYMBOL, 'parent': tmp_path, 'account': tmp_path / DEFAULTS['ACCOUNT_FOLDER']}
    for folder in [state] + list(others.values()):
        folder.mkdir(parents=True, exist_ok=True)
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    bot.state_dir = None
    m.app.OUTPUT_DIR = m.constants.OUTPUT_DIR = str(out)
    assert bot._take_process_lock() is True                            # state/<SYMBOL>.lock, held from here on
    assert len(bot._process_locks) == 1
    lock = Path(next(iter(bot._process_locks)))
    assert lock.parent == state and lock.name.lower() == f'{SYMBOL}.lock'.lower() and lock.exists()
    bases = OWN_TOP + OWN_STATE + (lock.name, 'BTCUSDm_trace.json', 'BTCUSDm_state.json', 'mt5_credentials.json',
                                   'safety_pin.txt', 'unknown.json', f'{SYMBOL}_journal_state.json.keep')
    bases += tuple(b + a for b in OWN_TOP + OWN_STATE for a in ASIDE)
    made = {}
    for kind, folder in [('top', out), ('state', state)] + list(others.items()):
        for base in bases:
            for ending in ENDINGS:
                p = folder / (base + ending)
                if p == lock or p.exists():
                    continue
                p.write_text(f'{kind} {base}{ending}', encoding='utf-8')
                _old(p)
                made[p] = kind
    _old(lock)
    assert len(made) > 2000
    swept_expected = {p for p, kind in made.items() if _allowed(kind, p.name)}
    assert len(swept_expected) == (len(OWN_TOP) + len(OWN_STATE)) * 5      # (five endings of the list are temp forms)
    tr = bot._tracer(SYMBOL)
    tr.poll_skipped('positions', 'x')                                    # the first poll: the start's sweep
    wrong = [f'{"deleted" if not p.exists() else "kept"}: {p.relative_to(tmp_path)}' for p in made
             if p.exists() == (p in swept_expected)]
    written = {(out, n) for n in OWN_TOP} | {(state, n) for n in OWN_STATE}      # (the bot writes these itself)
    wrong += [f'changed: {p.relative_to(tmp_path)}' for p, kind in made.items() if p.exists()
              and (p.parent, p.name) not in written and p.read_text(encoding='utf-8') != f'{kind} {p.name}']
    assert not wrong, f'{len(wrong)} wrong, e.g. {wrong[:8]}'
    # the lock: still there, still held by this process (the bot's own locking call on it is refused)
    assert lock.exists() and str(lock) in bot._process_locks
    fd = os.open(str(lock), os.O_RDWR)
    try:
        assert m.app._lock_fd(fd) is False
    finally:
        os.close(fd)
        bot._release_process_lock()


def test_the_sweep_comes_again_at_a_new_day_and_once_an_hour(mods, tmp_path):
    m = mods()
    out = tmp_path / 'bot_output'
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    tr = bot._tracer(SYMBOL)
    left = out / f'{SYMBOL}_trace.json.4242.tmp'

    def poll(dt):
        m.clock.now_ms += int(dt * 1000)
        tr.poll_skipped('positions', 'x')
    poll(1)
    left.write_text('{}')
    _old(left)
    poll(1800)
    assert left.exists()                                                 # within the hour: not looked for
    poll(1801)
    assert not left.exists()
    left.write_text('{}')
    _old(left)
    m.clock.now_ms = int(((int(START) // 86400 + 1) * 86400 + 1) * 1000)   # just after 00:00 UTC
    tr.poll_skipped('positions', 'x')
    assert not left.exists()


# ───────────────────────────── the daily files ─────────────────────────────

def test_the_newest_400_daily_trade_files_are_kept(mods, tmp_path):
    """daily_trade/<SYMBOL>/<dd>_<mon>_<yyyy>.json: app.py writes one per server day and never deletes one. The newest
    400 by the date in the name stay (the name does not sort by date); the summary and any other name stay; another
    symbol's folder is not touched."""
    m = mods()
    out = tmp_path / 'bot_output'
    folder = out / 'daily_trade' / SYMBOL
    other = out / 'daily_trade' / 'BTCUSDm'
    folder.mkdir(parents=True)
    other.mkdir(parents=True)
    days = [datetime.fromtimestamp(START - k * 86400, tz=timezone.utc) for k in range(430)]
    for d in days:
        (folder / (d.strftime('%d_%b_%Y').lower() + '.json')).write_text('{}')
        (other / (d.strftime('%d_%b_%Y').lower() + '.json')).write_text('{}')
    extra = ['historical_summary.json', '17_nov_2026.json.bak', '2026-11-17.json', '45_nov_2026.json', '01_xyz_2026.json',
             'notes.txt']
    for n in extra:
        (folder / n).write_text('{}')
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    m.app.OUTPUT_DIR = m.constants.OUTPUT_DIR = str(out)
    bot._tracer(SYMBOL).poll_skipped('positions', 'x')
    left = set(os.listdir(folder))
    assert set(extra) <= left and len(left) == 400 + len(extra)
    assert all((d.strftime('%d_%b_%Y').lower() + '.json' in left) == (k < 400) for k, d in enumerate(days))
    assert len(os.listdir(other)) == 430
    assert m.tracelog._daily_date('17_nov_2026.json') == (2026, 11, 17)
    assert m.tracelog._daily_date('17_NOV_2026.json') == (2026, 11, 17)
    assert m.tracelog._daily_date('historical_summary.json') is None


# ───────────────────────────── nothing else is touched ─────────────────────────────

def test_a_running_bot_deletes_nothing_but_old_day_files_and_old_temp_files(mods, tmp_path, monkeypatch):
    """A bot folder with everything in it -- state files, files set aside, the journal of last year, dash_env, the daily
    files, another symbol's files, the safety's files beside it -- through a start, an hour and a midnight of polls:
    every file is still there with its content, but the expired day files and the old temp files."""
    m = mods()
    out = tmp_path / 'bot_output'
    account = tmp_path / str(DEFAULTS['ACCOUNT_FOLDER'])
    keep = {
        out / f'{SYMBOL}.json': '{"a":1}', out / 'account.json': '{"b":1}', out / 'active_config.json': '{"mode":"live"}',
        out / 'BTCUSDm_trace.json': '{"other":"symbol"}',
        out / 'state' / f'{SYMBOL}_state.json': '{"basket":null}', out / 'state' / 'safety_state.json': '{"v":1}',
        out / 'state' / 'safety_closes.json': '{"q":[]}', out / 'state' / 'live_start.json': '{"time":1794000000}',
        out / 'state' / f'{SYMBOL}.lock': '', out / 'state' / 'safety_state.json.not-readable-20250101_000000': 'x',
        out / 'state' / f'{SYMBOL}_state.json.other-account-20250101_000000': 'x',
        out / 'journal' / f'{SYMBOL}_2024.jsonl': '{"kind":"start"}\n', out / 'journal' / 'BTCUSDm_2025.jsonl': '{}\n',
        out / 'dash_env' / 'pyvenv.cfg': 'home = x', out / 'dash_env' / f'{SYMBOL}_2020-01-01.log': 'not a log of ours',
        out / 'daily_trade' / SYMBOL / '01_jan_2020.json': '{}',
        out / 'daily_trade' / SYMBOL / 'historical_summary.json': '{}',
        out / 'logs' / f'{SYMBOL}_strategy_log.json': '[]', out / 'logs' / f'BTCUSDm_{day(300)}.log': 'x',
        out / 'logs' / f'{SYMBOL}_{day(3)}.log': 'three days ago\n',
        out / f'{SYMBOL}_{day(300)}.log': 'a day file outside logs/ is not looked at',
        account / 'safety_switch.json': '{"enabled":true}', account / 'safety_pin.txt': '123456',
        account / 'safety_audit.jsonl': '{}\n', account / 'safety_state.json.1.aa.tmp': 'the safety sweeps its own',
    }
    gone = {
        out / 'logs' / f'{SYMBOL}_{day(300)}.log': 'x', out / 'logs' / f'{SYMBOL}_{day(300)}_events.jsonl': 'x',
        out / 'logs' / f'{SYMBOL}_{day(9)}_samples.jsonl': 'x', out / f'{SYMBOL}_trace.json.99.tmp': '{}',
        out / 'state' / 'safety_state.json.99.0a0b0c0d.tmp': '{}',
    }
    for p, text in {**keep, **gone}.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    for p in list(keep) + list(gone):
        _old(p, 500)
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    bot.state_dir = None
    m.app.OUTPUT_DIR = m.constants.OUTPUT_DIR = str(out)
    deleted = []
    real = os.remove
    monkeypatch.setattr(m.tracelog.os, 'remove', lambda p: (deleted.append(str(p)), real(p))[1])
    tr = bot._tracer(SYMBOL)
    tr.loop_start({'state': {'basket': None, 'last_close': None}, 'sym_cfg': {}, '_rebuild_pause': True})
    midnight = (int(START) // 86400 + 1) * 86400
    for t in (START + 1, START + 2, START + 3700, START + 7400, midnight - 1, midnight + 1, midnight + 2, midnight + 3700):
        m.clock.now_ms = int(t * 1000)
        tr.poll({'state': {'basket': None, 'last_close': None}})
        tr.poll_skipped('positions', 'x')
    for p, text in keep.items():
        assert p.exists() and p.read_text() == text, p
    for p in gone:
        assert not p.exists(), p
    assert sorted(deleted) == sorted(str(p) for p in gone)              # ... and nothing else was ever removed
    # what the bot itself wrote meanwhile is all inside its own folder
    made = {str(p.relative_to(tmp_path)).split(os.sep)[0] for p in tmp_path.rglob('*') if p.is_file()}
    assert made == {'bot_output', str(DEFAULTS['ACCOUNT_FOLDER'])}


def test_the_real_sizes_are_the_spec_s(mods):
    tl = mods().tracelog
    mb, gb = 2 ** 20, 2 ** 30
    assert (tl.LOG_DAY_CAP_BYTES, tl.LOG_DAY_STOP_BYTES, tl.LOG_MAX_BYTES) == (50 * mb, 100 * mb, 500 * mb)
    assert (tl.DISK_LOW_BYTES, tl.DISK_CHECK_S, tl.TIDY_EVERY_S, tl.TEMP_SWEEP_AGE_S) == (2 * gb, 60.0, 3600.0, 86400.0)
    assert (tl.DAILY_TRADE_KEEP, tl.JOURNAL_DAY_BYTES, tl.JOURNAL_NOTE_S) == (400, 5 * mb, 3600.0)
    w = tl.LogWriter('logs', 'X')
    assert (w.day_cap, w.day_stop, w.max_bytes, w.journal_budget, w.disk_low_bytes) == (
        50 * mb, 100 * mb, 500 * mb, 5 * mb, 2 * gb)
