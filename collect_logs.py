"""
Put this bot's logs, journal and state into one zip file, to send when something has to be looked at.

Run it with collect_logs.bat in the branch folder (a double-click is enough). The bot may keep running. The zip
goes into the folder `exports` beside the bot's output folder (C:\\Alcadeias\\exports on the server) and is named
<BRANCH>_<yyyymmdd_hhmmss>.zip, the time in UTC. The last lines it prints give the full path of the zip.

What goes in, and nothing else:
  bot/         logs/, journal/, state/, daily_trade/ and the top-level *.json files of the bot's output folder
  account/     the files of the account folder (the safety files the two bots of one account share)
  SKIPPED.txt  what this export is, what could not be read, and what was left out on purpose

What never goes in, wherever it lies and whatever else its name holds:
  mt5_credentials.json, safety_pin.txt, safety_lockout.json, login_attempt.json (and copies or leftovers of them),
  any small file that holds a "login_pass" entry (a renamed copy of the credentials file), a folder called .git or
  dash_env, a link (links are not followed), and the bot's lock file.
And no login_sha: the fingerprint of the account number the bot's files keep beside its last 4 digits (which give
the number back at once) is replaced by a random stand-in, the same for the same value within one zip.
The owner clones the branch wherever he likes: the rules above hold also when the repository itself is the bot's
output folder, so this file never needs to know where the repository is.

Rules it keeps (spec section 8):
  - Standard library only, so it runs on the bare Python of the server.
  - It only reads the bot's files and never waits on them. A file the running bot holds open is read as far as it
    can be read; what is missing is listed in SKIPPED.txt inside the zip. Small files (the JSON files the bot
    replaces every poll) are read in one go and closed before they are compressed, so the bot's own write is not
    in its way for longer than the dashboard's read is.
  - It refuses when the zip could leave less than 2 GB free on its disk: the bots share that disk.
  - It keeps the newest 5 zips of its own branch and deletes its older ones. It touches no other file there.
  - Nothing is written anywhere but in the exports folder.
  - Never a traceback for the owner: every refusal is one plain sentence and exit code 1.

The folders come from constants.py (OUTPUT_DIR, ACCOUNT_FOLDER, BRANCH) through safety.account_dir, so this file
and the bot can never disagree about them. --bot-dir, --account-dir and --out replace them (the tests use these).
"""
import argparse
import calendar
import importlib.util
import ntpath
import os
import re
import secrets
import shutil
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

BOT_FOLDERS = ('logs', 'journal', 'state', 'daily_trade')     # of the bot's output folder, with all they hold
NEVER_FILES = ('mt5_credentials.json', 'safety_pin.txt', 'safety_lockout.json', 'login_attempt.json')
NEVER_FOLDERS = ('.git', 'dash_env')
# A file is left out when its name holds one of these, in any case. The stems of NEVER_FILES catch what is left
# of them or copied from them ('safety_lockout.json.4312.9f3a1c2e.tmp', 'mt5_credentials - Copy.json',
# 'mt5_credentials.json.orig' after a git merge); the last words are there for a copy under a name of its own.
NEVER_NAME_PARTS = ('mt5_credentials', 'safety_pin', 'safety_lockout', 'login_attempt',
                    'credential', 'password', 'passwd', 'secret')
EXPORTS_FOLDER = 'exports'
MIN_FREE_BYTES = 2 * 2 ** 30          # what must stay free on the disk of the exports folder
KEEP_ZIPS = 5                         # zips of this branch that are kept
WHOLE_READ_BYTES = 8 * 2 ** 20        # up to this size a file is read in one go and closed before it is compressed
CHUNK_BYTES = 2 ** 20
STALE_PART_S = 3600                   # a half-written zip of this branch older than this is swept
_ZIP_MEMBER_LIMIT = zipfile.ZIP64_LIMIT - 2 ** 24      # the most a member may hold without the zip64 format

_SAFE_NAME = re.compile(r'[A-Za-z0-9_.-]+')
# The entry that only the credentials file has: "login_pass": ... A log line that only talks about login_pass
# does not match (no quotes and colon around it), so the bot's own files are never taken for a copy of it.
_PASSWORD_ENTRY = re.compile(rb'"login_pass"\s*:', re.IGNORECASE)
_PASSWORD_ENTRY_UTF16 = '"login_pass"'.encode('utf-16-le')
# The state files, the claims, live_start.json, the journal state and the status files hold login_sha -- the plain
# SHA-256 of the account number -- beside its last 4 digits: with those, the number is found again in milliseconds.
# In the zip every such value is a random stand-in of the same length instead, the same for the same value within
# one zip (equal accounts still compare equal) and new in every zip.
_LOGIN_SHA_ENTRY = re.compile(rb'"login_sha"\s*:\s*"([0-9a-fA-F]{64})"')
_SHA_LEN = 64


class Refused(Exception):
    """The export is not made; the text is the one plain sentence the owner reads."""


class _Item:
    """One file to put into the zip."""
    __slots__ = ('path', 'arc', 'size', 'mtime')

    def __init__(self, path, arc, size, mtime):
        self.path, self.arc, self.size, self.mtime = path, arc, size, mtime


class _Report:
    """What an export did: the files it plans, what it could not read and what it left out on purpose."""

    def __init__(self):
        self.items = []
        self.unreadable = []          # (name in the zip, why)
        self.left_out = []            # (name in the zip, why)
        self.notes = []               # general remarks for SKIPPED.txt
        self.written = 0              # files in the zip (without SKIPPED.txt)
        self.bytes = 0                # their size before compression
        self.zip_path = None
        self.zip_bytes = 0
        self.pruned = []              # older zips of this branch that were deleted
        self.prune_failed = []


# ───────────────────────── the rules: what is never taken ─────────────────────────

def never_file(name):
    """True for a file that must never be exported, by its name alone."""
    n = str(name).casefold()
    return any(part in n for part in NEVER_NAME_PARTS)


def never_folder(name):
    return str(name).casefold() in NEVER_FOLDERS


def holds_password_entry(data):
    """True when these bytes hold the credentials file's password entry (the file under any name)."""
    return bool(_PASSWORD_ENTRY.search(data)) or _PASSWORD_ENTRY_UTF16 in data


def _why(err):
    """One short line about an error: its kind and the system's own words (without the file's path: the line it
    goes into names the file already)."""
    text = getattr(err, 'strerror', None) or str(err)
    return f'{type(err).__name__}: {text}'


class _Hider:
    """The login_sha values of one export and their random stand-ins: replace(data) gives the bytes with every
    such value (in any letter case) replaced by its stand-in, which has the same length."""

    def __init__(self, values):
        values = sorted({v.lower() for v in values})
        self.tokens = {v: secrets.token_hex(_SHA_LEN // 2).encode('ascii') for v in values}
        self._pattern = re.compile(b'|'.join(re.escape(v) for v in values), re.IGNORECASE) if values else None

    def replace(self, data):
        if self._pattern is None:
            return data
        return self._pattern.sub(lambda m: self.tokens[m.group(0).lower()], data)


def _login_shas(report):
    """Every login_sha value the planned files hold, as bytes: each file of up to WHOLE_READ_BYTES is read once,
    whole (the files that hold one are small); one that cannot be read is left to the export's own read."""
    found = set()
    for item in report.items:
        if item.size > WHOLE_READ_BYTES:
            continue
        try:
            with open(item.path, 'rb') as f:
                data = f.read(WHOLE_READ_BYTES + 1)
        except OSError:
            continue
        found.update(m.group(1) for m in _LOGIN_SHA_ENTRY.finditer(data))
    return found


# ───────────────────────── the plan: which files ─────────────────────────

def _plan_file(report, entry, arc):
    """One directory entry that is not a folder: plan it, or note why not."""
    name = entry.name
    try:
        if entry.is_symlink():
            report.left_out.append((arc, 'a link: links are not followed'))
            return
        if not entry.is_file(follow_symlinks=False):
            return                                              # (a pipe, a device: not a file of the bot)
        if never_file(name):
            report.left_out.append((arc, 'never exported: login details, the PIN or its lock-out'))
            return
        if name.casefold().endswith('.lock'):
            report.left_out.append((arc, 'the lock file of the running bot: nothing is in it'))
            return
        st = entry.stat(follow_symlinks=False)
    except OSError as e:
        report.unreadable.append((arc, _why(e)))
        return
    report.items.append(_Item(entry.path, arc, int(st.st_size), st.st_mtime))


def _entries(report, folder, arc):
    """The entries of a folder, by name; a folder that cannot be listed is noted and gives none."""
    try:
        with os.scandir(folder) as it:
            return sorted(it, key=lambda e: e.name)
    except OSError as e:
        report.unreadable.append((arc + '/', f'the folder could not be listed ({_why(e)})'))
        return []


def _plan_tree(report, folder, arc):
    """A folder with everything below it, except what is never taken."""
    for entry in _entries(report, folder, arc):
        child = f'{arc}/{entry.name}'
        try:
            link = entry.is_symlink()
            is_dir = (not link) and entry.is_dir(follow_symlinks=False)
        except OSError as e:
            report.unreadable.append((child, _why(e)))
            continue
        if is_dir:
            if never_folder(entry.name):
                report.left_out.append((child + '/', 'never exported'))
            else:
                _plan_tree(report, entry.path, child)
        else:
            _plan_file(report, entry, child)


def plan(bot_dir, account_dir):
    """What an export of these two folders would hold. Reads only the folders' listings."""
    report = _Report()
    for entry in _entries(report, bot_dir, 'bot'):
        arc = f'bot/{entry.name}'
        try:
            link = entry.is_symlink()
            is_dir = (not link) and entry.is_dir(follow_symlinks=False)
        except OSError as e:
            report.unreadable.append((arc, _why(e)))
            continue
        if is_dir:
            if entry.name.casefold() in BOT_FOLDERS:
                _plan_tree(report, entry.path, arc)
            continue                                            # (any other folder is not the bot's data)
        if entry.name.casefold().endswith('.json'):
            _plan_file(report, entry, arc)
    if account_dir and os.path.isdir(account_dir):
        for entry in _entries(report, account_dir, 'account'):
            arc = f'account/{entry.name}'
            try:
                link = entry.is_symlink()
                is_dir = (not link) and entry.is_dir(follow_symlinks=False)
            except OSError as e:
                report.unreadable.append((arc, _why(e)))
                continue
            if not is_dir:
                _plan_file(report, entry, arc)
    elif account_dir:
        report.notes.append(f'The account folder {account_dir} does not exist: nothing of it is in this zip.')
    else:
        report.notes.append('No account folder was named: nothing of it is in this zip.')
    return report


# ───────────────────────── the zip ─────────────────────────

def _zip_time(mtime):
    """A file time for the zip (UTC; the format knows the years 1980 to 2107 only)."""
    try:
        t = time.gmtime(mtime)[:6]
    except (OverflowError, OSError, ValueError):
        t = (1980, 1, 1, 0, 0, 0)
    if t[0] < 1980:
        return (1980, 1, 1, 0, 0, 0)
    if t[0] > 2107:
        return (2107, 12, 31, 23, 59, 58)
    return t


def _member(item, compression):
    info = zipfile.ZipInfo(item.arc, date_time=_zip_time(item.mtime))
    info.compress_type = compression
    info.external_attr = 0o644 << 16
    return info


def _close(f):
    """Close a file the export only read; a close that fails says nothing about the zip."""
    try:
        f.close()
    except OSError:
        pass


def _add(zf, item, report, compression, hider=None):
    """Put one file into the zip: all of it, or as much as can be read, with every login_sha replaced by its
    stand-in (`hider`). A read that fails is noted, never raised; an error from writing the zip itself is raised (the
    disk of the exports folder, not the bot's file)."""
    hide = hider.replace if hider is not None else (lambda data: data)
    try:
        src = open(item.path, 'rb')
    except FileNotFoundError:
        # A temp file the bot was just writing (<name>.<pid>.<hex>.tmp) is renamed onto its real name within a
        # millisecond: that it is gone is the normal case, and the real file is in the zip.
        if not item.arc.casefold().endswith('.tmp'):
            report.unreadable.append((item.arc, 'gone before it was read: the bot replaced or deleted it meanwhile'))
        return
    except OSError as e:
        report.unreadable.append((item.arc, f'could not be opened ({_why(e)})'))
        return
    try:
        try:
            first = src.read(WHOLE_READ_BYTES + 1)
        except OSError as e:
            report.unreadable.append((item.arc, f'could not be read ({_why(e)})'))
            return
        if len(first) <= WHOLE_READ_BYTES:
            _close(src)                                         # before the slow part: the bot may replace the file
            if holds_password_entry(first):
                report.left_out.append((item.arc, 'never exported: it holds a login_pass entry, so it is taken '
                                                  'for a copy of the credentials file'))
                return
            zf.writestr(_member(item, compression), hide(first))
            report.written += 1
            report.bytes += len(first)
            return
        # A large file (a day's log, the journal): compressed while it is read. The bot only appends to these.
        info = _member(item, compression)
        info.file_size = max(item.size, len(first))             # (a hint: it picks the zip64 format when needed)
        limit = None if info.file_size * 1.05 > zipfile.ZIP64_LIMIT else _ZIP_MEMBER_LIMIT
        done = 0
        held = b''          # the last bytes read: a login_sha may go on in the next chunk (a stand-in has its length)
        with zf.open(info, 'w') as dest:
            chunk = first
            while chunk:
                if limit is not None and done + len(chunk) > limit:
                    report.unreadable.append((item.arc, f'cut after {done:,} bytes: it grew past 2 GB while it '
                                                        f'was read'))
                    break
                data = hide(held + chunk)
                cut = max(0, len(data) - (_SHA_LEN - 1))
                dest.write(data[:cut])
                held = data[cut:]
                done += len(chunk)
                try:
                    chunk = src.read(CHUNK_BYTES)
                except OSError as e:
                    report.unreadable.append((item.arc, f'only its first {done:,} bytes could be read '
                                                        f'({_why(e)})'))
                    break
            dest.write(held)
        report.written += 1
        report.bytes += done
    finally:
        _close(src)


def _size_text(n):
    if n >= 2 ** 30:
        return f'{n / 2 ** 30:.2f} GB'
    if n >= 2 ** 20:
        return f'{n / 2 ** 20:.1f} MB'
    if n >= 1024:
        return f'{n / 1024:.1f} KB'
    return f'{int(n)} bytes'


def _skipped_text(report, branch, bot_dir, account_dir, now):
    lines = [
        'Alcadeias log export',
        f'branch: {branch}',
        f'made at: {time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))} UTC',
        f'bot folder: {bot_dir}',
        f'account folder: {account_dir}',
        f'files in this zip: {report.written} ({_size_text(report.bytes)} before compression), and this file',
        '',
        'In this zip: bot/ holds logs/, journal/, state/, daily_trade/ and the top-level .json files of the bot',
        'folder; account/ holds the files of the account folder. Nothing else is taken.',
    ]
    if report.notes:
        lines += [''] + list(report.notes)
    lines += ['', f'Could not be read, or not completely ({len(report.unreadable)}):']
    lines += [f'  {arc}: {why}' for arc, why in report.unreadable] or ['  nothing: every file was read to its end']
    lines += ['', f'Left out on purpose ({len(report.left_out)}):']
    lines += [f'  {arc}: {why}' for arc, why in report.left_out] or ['  nothing']
    return '\r\n'.join(lines) + '\r\n'


def space_needed(items):
    """The most the zip can need on the disk: every file as it is, plus the zip's own bookkeeping per file."""
    items = list(items)
    return sum(i.size for i in items) + 1024 * (len(items) + 1) + 2 ** 16


def _free_bytes(folder):
    """Free space on the disk of `folder` (a function of its own so that a test can stand in for the disk)."""
    return shutil.disk_usage(folder).free


def _stamp(now):
    return time.strftime('%Y%m%d_%H%M%S', time.gmtime(now))


def _zips_of(out_dir, branch, suffix='.zip'):
    """{file name: its time} of this branch's exports in `out_dir`: exactly <branch>_<yyyymmdd_hhmmss><suffix>."""
    pattern = re.compile(re.escape(branch) + r'_(\d{8}_\d{6})' + re.escape(suffix))
    found = {}
    try:
        names = os.listdir(out_dir)
    except OSError:
        return found
    for name in names:
        m = pattern.fullmatch(name)
        if not m:
            continue
        try:
            found[name] = calendar.timegm(time.strptime(m.group(1), '%Y%m%d_%H%M%S'))
        except ValueError:
            continue                                            # (digits that are not a date: not ours)
    return found


def _prune(out_dir, branch, keep, report):
    """Keep the newest `keep` zips of this branch, by the time in their names; delete its older ones."""
    zips = _zips_of(out_dir, branch)
    for name in sorted(zips, key=lambda n: (zips[n], n), reverse=True)[max(1, int(keep)):]:
        try:
            os.remove(os.path.join(out_dir, name))
            report.pruned.append(name)
        except OSError as e:
            report.prune_failed.append((name, _why(e)))


def _sweep_parts(out_dir, branch, now):
    """Half-written zips of this branch that an interrupted run left, older than an hour."""
    for name, t in _zips_of(out_dir, branch, suffix='.zip.part').items():
        if now - t >= STALE_PART_S:
            try:
                os.remove(os.path.join(out_dir, name))
            except OSError:
                pass


def _replace_retry(src, dst, waits=(0.05, 0.1, 0.2, 0.4, 0.8)):
    """os.replace; on Windows a virus scanner can hold a file that was just written for a moment."""
    for wait in waits:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            time.sleep(wait)
    os.replace(src, dst)


def _full(path):
    """The folder as a full path. A Windows path stays as it is written on any system (on the server it is a
    full path already; anywhere else it names nothing, and the messages should still show it as it is)."""
    path = str(path)
    return path if (os.path.isabs(path) or ntpath.isabs(path)) else os.path.abspath(path)


def _inside(path, folder):
    """True when `path` is `folder` or lies in it."""
    p = os.path.normcase(os.path.realpath(path))
    f = os.path.normcase(os.path.realpath(folder))
    return p == f or p.startswith(f.rstrip(os.sep) + os.sep)


def collect(bot_dir, account_dir, out_dir, branch, now=None, min_free=MIN_FREE_BYTES, keep=KEEP_ZIPS):
    """Write <out_dir>/<branch>_<yyyymmdd_hhmmss>.zip from the two folders and return the report.
    Raises Refused (one plain sentence) when no zip is made; then nothing is left behind."""
    now = time.time() if now is None else float(now)
    branch = str(branch)
    if not _SAFE_NAME.fullmatch(branch):
        raise Refused(f'the branch name {branch!r} cannot be used in a file name (letters, digits, _ - . only).')
    bot_dir, out_dir = _full(bot_dir), _full(out_dir)
    account_dir = _full(account_dir) if account_dir else None
    if not os.path.isdir(bot_dir):
        raise Refused(f'the bot folder {bot_dir} does not exist. Has this bot been started on this server yet?')
    for folder in (bot_dir, account_dir):
        if folder and _inside(out_dir, folder):
            raise Refused(f'the zip cannot be made in {out_dir}: that is inside {folder}, the folder it copies. '
                          f'Choose another folder.')

    report = plan(bot_dir, account_dir)
    if not report.items:
        raise Refused(f'the bot folder {bot_dir} holds no logs, journal or state yet. Has this bot been started '
                      f'on this server yet?')

    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        raise Refused(f'the folder {out_dir} could not be made ({_why(e)}).')
    need = space_needed(report.items)
    try:
        free = int(_free_bytes(out_dir))
    except OSError as e:
        raise Refused(f'the free space of the disk of {out_dir} could not be read ({_why(e)}), so the zip is not '
                      f'made: the bots need room on that disk.')
    if free - need < min_free:
        raise Refused(f'the zip could need up to {_size_text(need)}, and the disk of {out_dir} has '
                      f'{_size_text(free)} free. {_size_text(min_free)} must stay free for the bots. Delete old '
                      f'files there (older zip files in {out_dir} are safe to delete) and run this again.')

    _sweep_parts(out_dir, branch, now)
    stamp_t = now
    while True:                                                 # (two runs in the same second: the next second)
        final = os.path.join(out_dir, f'{branch}_{_stamp(stamp_t)}.zip')
        if not os.path.lexists(final) and not os.path.lexists(final + '.part'):
            break
        stamp_t += 1
    part = final + '.part'
    try:
        import zlib  # noqa: F401  (in every Python of python.org; without it the zip is stored, not compressed)
        compression = zipfile.ZIP_DEFLATED
    except ImportError:
        compression = zipfile.ZIP_STORED
    hider = _Hider(_login_shas(report))
    if hider.tokens:
        report.notes.append(f'Every login_sha (a fingerprint of an account number) is replaced in this zip by a '
                            f'random stand-in of the same length: {len(hider.tokens)} value(s), each the same '
                            f'wherever it stands in this zip, and different in every zip.')
    try:
        with zipfile.ZipFile(part, 'w', compression=compression, allowZip64=True) as zf:
            for item in report.items:
                _add(zf, item, report, compression, hider)
            info = zipfile.ZipInfo('SKIPPED.txt', date_time=_zip_time(now))
            info.compress_type = compression
            info.external_attr = 0o644 << 16
            zf.writestr(info, _skipped_text(report, branch, bot_dir, account_dir, now).encode('utf-8'))
        _replace_retry(part, final)
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as e:
        try:
            os.remove(part)
        except OSError:
            pass
        raise Refused(f'the zip file could not be written in {out_dir} ({_why(e)}).')
    report.zip_path = final
    try:
        report.zip_bytes = os.path.getsize(final)
    except OSError:
        report.zip_bytes = 0
    _prune(out_dir, branch, keep, report)
    return report


# ───────────────────────── the command line ─────────────────────────

def _load(name):
    """A module of this folder, loaded from its file: this branch's own constants.py and safety.py, whatever else
    the Python path holds."""
    path = os.path.join(HERE, name + '.py')
    spec = importlib.util.spec_from_file_location(f'_collect_logs_{name}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def folders(bot_dir=None, account_dir=None, out_dir=None):
    """(branch, bot folder, account folder, exports folder) of this branch: from constants.py through
    safety.account_dir; each given folder replaces its default, and the defaults follow a given bot folder."""
    constants, safety = _load('constants'), _load('safety')
    branch = str(constants.BRANCH)
    bot = str(bot_dir) if bot_dir else constants.OUTPUT_DIR
    account = str(account_dir) if account_dir else safety.account_dir(bot, constants.ACCOUNT_FOLDER)
    out = str(out_dir) if out_dir else safety.account_dir(bot, EXPORTS_FOLDER)
    return branch, bot, account, out


def _say(text=''):
    """Print one line; a character the console cannot show never stops the export."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'backslashreplace').decode('ascii'), flush=True)


def main(argv=None):
    sys.dont_write_bytecode = True      # (loading constants.py below must leave no __pycache__ in the branch)
    parser = argparse.ArgumentParser(
        prog='collect_logs',
        description="Put this bot's logs, journal and state into one zip file to send. It never holds "
                    "mt5_credentials.json or the safety PIN.")
    parser.add_argument('--out', help='the folder for the zip (default: the folder exports beside the bot folder)')
    parser.add_argument('--bot-dir', help="the bot's output folder (default: OUTPUT_DIR of constants.py)")
    parser.add_argument('--account-dir', help='the account folder (default: beside the bot folder)')
    args = parser.parse_args(argv)
    try:
        branch, bot_dir, account_dir, out_dir = folders(args.bot_dir, args.account_dir, args.out)
    except Exception as e:      # constants.py or safety.py missing, broken, or without the names of this branch
        _say(f'Nothing was collected: the settings of this branch could not be read ({_why(e)}). '
             f'Run this file from the branch folder, beside constants.py and safety.py.')
        return 1
    _say(f'Collecting the logs of {branch} ...')
    _say(f'  bot folder:     {bot_dir}')
    _say(f'  account folder: {account_dir}')
    try:
        report = collect(bot_dir, account_dir, out_dir, branch)
    except Refused as e:
        _say(f'Nothing was collected: {e}')
        return 1
    except Exception as e:      # never a traceback for the owner
        _say(f'Nothing was collected: something unexpected went wrong ({_why(e)}).')
        return 1
    _say(f'The zip file is ready: {report.zip_path}')
    _say(f'It holds {report.written} files ({_size_text(report.bytes)}; the zip is {_size_text(report.zip_bytes)}). '
         f'It does not hold mt5_credentials.json or the safety PIN.')
    for note in report.notes:
        _say(note)
    if report.unreadable:
        _say(f'{len(report.unreadable)} file(s) could not be read, or not to the end. They are listed in '
             f'SKIPPED.txt inside the zip. The rest of the zip is complete.')
    if report.pruned:
        _say(f'{len(report.pruned)} older zip file(s) of {branch} were deleted: the newest {KEEP_ZIPS} are kept.')
    for name, why in report.prune_failed:
        _say(f'The old zip file {name} could not be deleted ({why}). Delete it by hand when you like.')
    _say('Run collect_logs.bat in the other branch of this account too, and send both zip files.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
