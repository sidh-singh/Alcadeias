"""
The command line and the parts of the suite that depend on the machine it runs on.

* Each command offers the options it uses and no others; ``--live-root`` reaches the code
  that reads the live settings (and, for ``parity``, the live code itself).
* ``run --mode ticks`` adds the 0.1 s the live ``buy()`` / ``sell()`` sleep after an order.
* Result times are nanoseconds on every pandas version, and the millisecond conversions do
  not depend on the resolution of the column they are given.
* A machine without Chrome / Chromium / Edge only loses the PNG snapshots.
* Text files are read and written as UTF-8 and the console output survives a legacy code
  page, whatever the default encoding of the platform is.

No test here runs a backtest through the command line: the commands read the full tick store
under ``data/``, which the suite does not need. The engine entry points the commands call are
replaced by recorders, so what is checked is what the command line hands to them.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting import cli
from backtesting.config import BacktestConfig
from backtesting.engine import fast
from backtesting.viz import replay as R
from backtesting.viz import snapshot

STRATEGY_COMMANDS = ("run", "parity", "sweep", "robust")
# characters the logs and pages really use; none of the first four is ASCII and
# "→" and "✕" do not exist in cp1252
SAMPLE = "13 Aug → 13 Nov · ✕ – done"


# ───────────────────────────── helpers ─────────────────────────────

def other_checkout(root: Path, live_root: Path, **constants) -> Path:
    """
    A directory that looks like another checkout of the live bot: this branch's constants.py
    with some values replaced (the file is plain assignments, so a later line wins) and a
    symbols.json of its own, written as UTF-8 with non-ASCII text in it.
    """
    root.mkdir(parents=True, exist_ok=True)
    text = (live_root / "constants.py").read_text(encoding="utf-8")
    text += "\n" + "".join(f"{k} = {v!r}\n" for k, v in constants.items())
    (root / "constants.py").write_text(text, encoding="utf-8")
    (root / "symbols.json").write_text(json.dumps({
        # "Á" and "Í" are bytes cp1252 cannot decode when written as UTF-8
        "comment": "Ánalisis → Íntegro · ✕ – fenêtre",
        "brake": 1, "mtqty": 0.01,
        "trading_window": {"enabled": True, "start_day": "Monday", "start_time": "01:00",
                           "end_day": "Friday", "end_time": "22:00"},
        "symbols": [{"symbol": "XAUUSDm", "is_active": True, "step_up_balance": 4321, "unit_max_limit": 3}],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


@pytest.fixture
def checkout(tmp_path, live_root) -> Path:
    return other_checkout(tmp_path / "other_checkout", live_root, REENTRY_COOLDOWN_SECONDS=777)


@pytest.fixture
def recorded(monkeypatch):
    """
    Replace the engine entry points the commands call by recorders. ``recorded["cfg"]`` is the
    list of configurations they were given, ``recorded["live_root"]`` the live roots and
    ``recorded["jobs"]`` the worker count each grid was asked to use.
    """
    from backtesting.analysis import robustness, sweep
    from backtesting.engine import parity

    seen = {"cfg": [], "live_root": [], "mode": [], "jobs": {}}
    table = pd.DataFrame({"net_profit": [1.0], "baskets": [1]})

    def fake_run(cfg, prep=None, mode="sec", **kw):
        seen["cfg"].append(cfg)
        seen["mode"].append(mode)
        return types.SimpleNamespace(mode=mode, baskets=pd.DataFrame(), summary=lambda: {"net_profit": 0.0})

    def fake_parity(cfg, live_root=None, mode="ticks", **kw):
        seen["cfg"].append(cfg)
        seen["live_root"].append(live_root)
        return parity.ParityReport(ok=True, polls_ref=0, polls_fast=0, signal_mismatches=0, score_mismatches=0,
                                   rsi_max_abs_diff=0.0, fills_ref=0, fills_fast=0, fill_mismatches=0,
                                   balance_ref=0.0, balance_fast=0.0)

    def fake_grid(name):
        def grid(cfg, *a, n_jobs=None, **kw):
            seen["cfg"].append(cfg)
            seen["jobs"][name] = n_jobs
            return table.copy()
        return grid

    monkeypatch.setattr(fast, "run", fake_run)
    monkeypatch.setattr(parity, "check_parity", fake_parity)
    monkeypatch.setattr(sweep, "run_grid", fake_grid("run_grid"))
    for name in ("cost_grid", "start_shift", "segments", "timing_grid"):
        monkeypatch.setattr(robustness, name, fake_grid(name))
    monkeypatch.setattr(robustness, "bootstrap", lambda baskets, account, **kw: {"note": SAMPLE})
    return seen


def command_line(cmd: str, tmp_path: Path, *extra: str) -> list:
    """A command line for ``cmd`` that writes nothing outside ``tmp_path``."""
    out = {"run": ["--no-report"], "parity": ["--out", str(tmp_path / "parity.json")],
           "sweep": ["--out", str(tmp_path / "sweep.csv")], "robust": ["--out", str(tmp_path / "robust")]}[cmd]
    return [cmd, "--symbol", "XAUUSDm", *out, *extra]


# ───────────────────────────── which command takes which option ─────────────────────────────

@pytest.mark.parametrize("cmd", STRATEGY_COMMANDS)
def test_strategy_commands_take_window_account_and_live_root(cmd):
    args = cli.build_parser().parse_args(
        [cmd, "--symbol", "BTCUSDm", "--start", "2026-09-01", "--end", "2026-10-01", "--balance", "500",
         "--leverage", "200", "--set", "entry_s=4", "--set", 'open_weights={"H4":1}', "--live-root", "/some/checkout"])
    assert (args.symbol, args.start, args.end) == ("BTCUSDm", "2026-09-01", "2026-10-01")
    assert (args.balance, args.leverage, args.live_root) == (500.0, 200.0, "/some/checkout")
    assert cli._parse_sets(args.set) == {"entry_s": 4, "open_weights": {"H4": 1}}


@pytest.mark.parametrize("cmd", ["reproduce", "docs"])
def test_pipeline_commands_take_live_root(cmd):
    assert cli.build_parser().parse_args([cmd, "--live-root", "/some/checkout"]).live_root == "/some/checkout"


@pytest.mark.parametrize("cmd, option", [
    ("quality", ["--balance", "500"]), ("quality", ["--leverage", "200"]), ("quality", ["--set", "entry_s=4"]),
    ("quality", ["--live-root", "/x"]),
    ("data", ["--start", "2026-09-01"]), ("data", ["--set", "entry_s=4"]),
    ("reproduce", ["--start", "2026-09-01"]), ("reproduce", ["--balance", "500"]), ("reproduce", ["--set", "entry_s=4"]),
    ("docs", ["--end", "2026-10-01"]), ("docs", ["--leverage", "200"]),
    ("studio", ["--start", "2026-09-01"]), ("studio", ["--set", "entry_s=4"]), ("studio", ["--live-root", "/x"]),
])
def test_a_command_does_not_offer_an_option_it_would_ignore(cmd, option, capsys):
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args([cmd, *option])
    assert e.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_quality_still_takes_its_window():
    args = cli.build_parser().parse_args(["quality", "--symbol", "BTCUSDm", "--start", "2026-09-01", "--end", "2026-10-01"])
    assert (args.symbol, args.start, args.end) == ("BTCUSDm", "2026-09-01", "2026-10-01")


# ───────────────────────────── --live-root is used ─────────────────────────────

@pytest.mark.parametrize("cmd", STRATEGY_COMMANDS)
def test_live_root_selects_the_checkout_the_settings_come_from(cmd, checkout, recorded, tmp_path, live_root):
    here = BacktestConfig.live("XAUUSDm", repo_root=live_root)
    assert here.reentry_cooldown_s != 777.0 and here.step_up_balance != 4321.0   # or the test proves nothing

    assert cli.main(command_line(cmd, tmp_path, "--live-root", str(checkout))) == 0
    assert recorded["cfg"], "the command never reached the engine"
    for cfg in recorded["cfg"]:
        assert cfg.reentry_cooldown_s == 777.0          # constants.py of the other checkout
        assert cfg.step_up_balance == 4321.0            # symbols.json of the other checkout
        assert cfg.unit_max_limit == 3


@pytest.mark.parametrize("cmd", STRATEGY_COMMANDS)
def test_without_live_root_the_settings_are_this_checkouts(cmd, recorded, tmp_path, repo_root):
    here = BacktestConfig.live("XAUUSDm", repo_root=repo_root)
    assert cli.main(command_line(cmd, tmp_path)) == 0
    for cfg in recorded["cfg"]:
        assert cfg.reentry_cooldown_s == here.reentry_cooldown_s
        assert cfg.step_up_balance == here.step_up_balance


def test_parity_replays_the_live_code_of_the_live_root(checkout, recorded, tmp_path, repo_root):
    assert cli.main(command_line("parity", tmp_path, "--live-root", str(checkout))) == 0
    assert recorded["live_root"] == [checkout.resolve()]
    assert json.loads((tmp_path / "parity.json").read_text(encoding="utf-8"))["ok"] is True

    assert cli.main(command_line("parity", tmp_path)) == 0
    assert recorded["live_root"][-1] == repo_root


def test_overrides_apply_on_top_of_the_live_root(checkout, recorded, tmp_path):
    assert cli.main(command_line("run", tmp_path, "--live-root", str(checkout), "--balance", "500",
                                 "--leverage", "200", "--set", "reentry_cooldown_s=60")) == 0
    cfg = recorded["cfg"][-1]
    assert (cfg.initial_balance, cfg.leverage, cfg.reentry_cooldown_s) == (500.0, 200.0, 60.0)
    assert cfg.step_up_balance == 4321.0


def test_a_live_root_without_constants_is_refused_by_name(tmp_path, recorded):
    with pytest.raises(SystemExit) as e:
        cli.main(command_line("run", tmp_path, "--live-root", str(tmp_path / "nowhere")))
    assert "--live-root" in str(e.value) and "constants.py" in str(e.value)
    assert recorded["cfg"] == []


def test_robust_writes_its_tables_and_keeps_raw_tick_workers_few(recorded, tmp_path):
    assert cli.main(command_line("robust", tmp_path)) == 0
    out = tmp_path / "robust"
    assert {p.name for p in out.iterdir()} == {"costs.csv", "start_shift.csv", "segments.csv", "timing.csv", "bootstrap.json"}
    assert json.loads((out / "bootstrap.json").read_text(encoding="utf-8")) == {"note": SAMPLE}
    # every worker of a raw-tick grid loads the whole window of ticks; the per-second grid may use every core
    jobs = recorded["jobs"]
    assert jobs["cost_grid"] == jobs["start_shift"] == jobs["timing_grid"] == 2 and jobs["segments"] is None

    assert cli.main(command_line("robust", tmp_path, "--jobs", "8", "--no-ticks")) == 0
    assert jobs["cost_grid"] == jobs["start_shift"] == 3 and jobs["segments"] == 8


# ───────────────────────────── run: raw ticks or the per-second series ─────────────────────────────

@pytest.mark.parametrize("extra, mode, delay", [
    ([], "sec", 0),                                                      # the per-second series cannot represent it
    (["--mode", "sec"], "sec", 0),
    (["--mode", "ticks"], "ticks", 100),                                 # the sleep inside the live buy() / sell()
    (["--mode", "ticks", "--set", "open_order_delay_ms=0"], "ticks", 0),     # the user's value stands
    (["--mode", "ticks", "--set", "open_order_delay_ms=250"], "ticks", 250),
    (["--mode", "ticks", "--set", "entry_s=4"], "ticks", 100),           # another --set does not switch it off
])
def test_run_on_raw_ticks_models_the_order_sleep_unless_overridden(extra, mode, delay, recorded, tmp_path):
    assert cli.main(command_line("run", tmp_path, *extra)) == 0
    assert recorded["mode"] == [mode]
    assert recorded["cfg"][0].open_order_delay_ms == delay


def test_the_live_order_sleep_is_the_one_the_parity_check_uses():
    from backtesting.engine import parity
    assert cli.LIVE_OPEN_ORDER_DELAY_MS == parity.LIVE_OPEN_ORDER_DELAY_MS == 100


# ───────────────────────────── datetime resolution ─────────────────────────────

def test_ts_is_nanosecond_utc_and_exact():
    ms = np.array([0.0, 1_762_668_000_123.0, 1_762_671_599_999.0])        # the kernel hands times over as float64
    t = fast._ts(ms)
    assert str(t.dtype) == "datetime64[ns, UTC]"
    assert t.asi8.tolist() == [0, 1_762_668_000_123_000_000, 1_762_671_599_999_000_000]
    assert str(fast._ts(np.zeros(0)).dtype) == "datetime64[ns, UTC]"


def test_result_frames_carry_nanosecond_utc_times(live_cfg, engine_run):
    res = engine_run(live_cfg("BTCUSDm"), mode="sec")
    assert len(res.fills) and len(res.baskets) and len(res.equity)
    for frame, cols in ((res.fills, ("time", "fill_time", "pos_open_time")),
                        (res.baskets, ("open_time", "close_time")), (res.equity, ("time",))):
        for c in cols:
            assert str(frame[c].dtype) == "datetime64[ns, UTC]", c
    # and they are the kernel's milliseconds
    assert (R._ms(res.baskets["close_time"]) - R._ms(res.baskets["open_time"])
            == np.round(res.baskets["duration_s"].to_numpy() * 1000)).all()


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
@pytest.mark.parametrize("tz", ["UTC", None])
def test_milliseconds_do_not_depend_on_the_resolution_of_the_column(unit, tz):
    want = np.array([0, 1_762_668_000_000, 1_762_671_599_000, 1_762_671_600_000], dtype=np.int64)
    col = pd.Series(pd.to_datetime(want, unit="ms", utc=tz is not None)).dt.as_unit(unit)
    assert unit in str(col.dtype)
    got = R._ms(col)
    assert got.dtype == np.int64 and got.tolist() == want.tolist()
    assert R._ms(pd.DatetimeIndex(col)).tolist() == want.tolist()
    assert R._ms(col.iloc[:0]).tolist() == []


def test_milliseconds_keep_sub_second_parts_and_mark_missing_times():
    col = pd.Series(pd.to_datetime(["2026-11-09 06:00:00.123", None, "2026-11-09 06:00:00.999999"])).dt.as_unit("us")
    got = R._ms(col)
    assert got[0] == 1_794_204_000_123 and got[2] == 1_794_204_000_999      # 2026-11-09 06:00:00 UTC + 123 / 999 ms
    assert got[1] < 0                                   # NaT: never inside a window of real times


# ───────────────────────────── headless browser ─────────────────────────────

def test_browser_candidates_cover_macos_windows_and_linux():
    env = {"ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)",
           "LocalAppData": r"C:\Users\someone\AppData\Local"}
    c = snapshot.chrome_candidates(env)
    for path in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                 r"C:\Users\someone\AppData\Local\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        assert path in c, path
    assert len(c) == len(set(c))


def test_browser_candidates_without_the_windows_variables():
    c = snapshot.chrome_candidates({})
    assert all(isinstance(x, str) and x for x in c)
    assert not any("chrome.exe" in x or "msedge.exe" in x for x in c)
    assert "google-chrome" in c and "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" in c
    assert snapshot.chrome_candidates({"ProgramFiles": "", "LocalAppData": ""}) == c


def test_no_browser_means_no_snapshots_and_one_log_line(tmp_path, monkeypatch):
    import plotly.graph_objects as go

    monkeypatch.setattr(snapshot, "_CHROME_CANDIDATES",
                        [str(tmp_path / "missing" / "chrome"), "no-such-browser-a", "no-such-browser-b"])
    empty = tmp_path / "empty_bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert snapshot.find_chrome() is None
    assert snapshot.figure_png(go.Figure(), tmp_path / "img" / "x.png") is None
    assert not (tmp_path / "img").exists()

    lines = []
    assert snapshot.build_gallery(tmp_path / "results", log=lines.append) == []
    assert len(lines) == 1 and "skipping the PNG snapshots" in lines[0]
    assert not (tmp_path / "results").exists()


def test_an_empty_candidate_list_is_not_an_error(monkeypatch):
    monkeypatch.setattr(snapshot, "_CHROME_CANDIDATES", [])
    assert snapshot.find_chrome() is None


def test_a_browser_is_found_by_full_path_or_on_path(tmp_path, monkeypatch):
    full = tmp_path / "apps" / "Some Browser"
    full.parent.mkdir()
    full.write_bytes(b"")
    monkeypatch.setattr(snapshot, "_CHROME_CANDIDATES", [str(tmp_path / "apps" / "absent"), str(full), "chromium"])
    assert snapshot.find_chrome() == str(full)

    if os.name != "posix":
        return                                          # an executable on PATH is made differently elsewhere
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "chromium"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(snapshot, "_CHROME_CANDIDATES", [str(tmp_path / "apps" / "absent"), "google-chrome", "chromium"])
    assert snapshot.find_chrome() == str(exe)
    # a directory of that name in the working directory is not a browser
    (tmp_path / "google-chrome").mkdir()
    monkeypatch.chdir(tmp_path)
    assert snapshot.find_chrome() == str(exe)


# ───────────────────────────── consoles and files that are not UTF-8 ─────────────────────────────

def test_console_streams_are_switched_to_utf8(monkeypatch):
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    err = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    with pytest.raises(UnicodeEncodeError):
        out.write(SAMPLE)
        out.flush()
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    cli._utf8_console()
    out.write(SAMPLE)
    err.write(SAMPLE)
    out.flush()
    err.flush()
    assert out.buffer.getvalue().decode("utf-8") == SAMPLE
    assert err.buffer.getvalue().decode("utf-8") == SAMPLE


def test_a_stream_that_cannot_be_reconfigured_is_left_alone(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())       # no reconfigure()
    monkeypatch.setattr(sys, "stderr", None)                # pythonw, a detached service
    cli._utf8_console()
    print(SAMPLE)
    assert sys.stdout.getvalue() == SAMPLE + "\n"


# Runs in a child interpreter whose console is cp1252 and whose default text encoding is not
# UTF-8. argv: the other checkout, a scratch directory.
_LEGACY_SCRIPT = r'''
import builtins, importlib, io, json, locale, pkgutil, sys, warnings
from pathlib import Path

checkout, scratch = Path(sys.argv[1]), Path(sys.argv[2])
sample = json.loads(sys.argv[3])
default = locale.getpreferredencoding(False)
warn = getattr(builtins, "EncodingWarning", None)
print("console=%s default=%s warns=%s" % (sys.stdout.encoding, default, warn is not None and bool(sys.flags.warn_default_encoding)))
if warn is not None:
    # a text file opened by the package without an explicit encoding is an error here
    warnings.filterwarnings("error", category=warn, module=r"backtesting(\.|$)")

import backtesting
names = [m.name for m in pkgutil.walk_packages(backtesting.__path__, "backtesting.") if not m.name.endswith("__main__")]
for name in names:
    importlib.import_module(name)
print("imported=%d" % len(names))

from backtesting import cli
from backtesting.config import BacktestConfig
from backtesting.data import store

# symbols.json holds non-ASCII text in UTF-8
cfg = BacktestConfig.live("XAUUSDm", repo_root=checkout)
assert cfg.step_up_balance == 4321.0 and cfg.reentry_cooldown_s == 777.0, cfg

# a store whose meta.json holds non-ASCII text
d = store.month_dir(scratch / "store", "XAUUSDm", 2026, 11)
d.mkdir(parents=True)
meta = {"first": "2026-11-01T00:00:00+00:00", "last": "2026-11-30T23:59:59+00:00", "note": sample}
(d / "meta.json").write_bytes(json.dumps(meta, ensure_ascii=False).encode("utf-8"))
span = store.data_span("XAUUSDm", scratch / "store")
assert str(span[0]) == "2026-11-01 00:00:00+00:00" and str(span[1]) == "2026-11-30 23:59:59+00:00", span

# JSON written by the command line reads back as the same text
cli._write_json(scratch / "out" / "report.json", {"note": sample})
assert json.loads((scratch / "out" / "report.json").read_bytes().decode("utf-8")) == {"note": sample}

# a command that prints the characters the logs use, through main()
def chatty(args):
    print(sample)
    print(sample, file=sys.stderr)
    return 0

cli.cmd_studio = chatty
assert cli.main(["studio"]) == 0
print("finished")
'''


def test_a_legacy_console_and_default_encoding_do_not_break_the_suite(tmp_path, live_root, repo_root):
    """
    The situation of a Windows machine with redirected output: stdout / stderr in cp1252 and a
    default text encoding that is not UTF-8. Here the default is forced to ASCII through the C
    locale with UTF-8 mode off (on Windows ``-X utf8=0`` leaves the ANSI code page), which
    refuses every non-ASCII byte; on Python 3.10+ the child also turns "text file opened by
    the package without an encoding" into an error, which holds on any platform.
    """
    checkout = other_checkout(tmp_path / "other_checkout", live_root, REENTRY_COOLDOWN_SECONDS=777)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONWARNINGS", "PYTHONWARNDEFAULTENCODING")}
    env.update(PYTHONIOENCODING="cp1252", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0",
               LC_ALL="C", LC_CTYPE="C", LANG="C", PYTHONPATH=str(repo_root))
    p = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-X", "warn_default_encoding", "-c", textwrap.dedent(_LEGACY_SCRIPT),
         str(checkout), str(scratch), json.dumps(SAMPLE)],
        env=env, cwd=str(scratch), capture_output=True, timeout=300)
    out, err = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    assert p.returncode == 0, f"stdout:\n{out}\nstderr:\n{err}"
    lines = out.splitlines()
    assert lines[0].startswith("console=cp1252 "), lines[0]
    assert lines[-1] == "finished" and lines[-2] == SAMPLE      # written as UTF-8 although the console was cp1252
    assert SAMPLE in err.splitlines()
    assert int(lines[1].split("=")[1]) >= 20                     # every module of the package was imported
