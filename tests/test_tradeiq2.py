"""
Study 2's driver (``backtesting/research/tradeiq2.py``) on the stub rule modules of ``tests/tradeiq2_stub_rules.py``
(seeded states and events, not study-2 rules) and on synthetic markets of August to October 2020. No real market data
is read (``M.load``, the store, the Binance volume and the driver's default loader raise), the guard's folder is an
empty tmp folder, the windows are short synthetic ones (``M.WINDOWS`` patched) and so are the guard's hold-out start
and Early window (``M.HOLDOUT_START``, ``M.CUT_S``, ``M.EARLY``, ``M.EARLY_S``: before the tmp freeze the guard refuses
the synthetic hold-out and Early window exactly as it refuses the real ones), the stub loader cuts each market at the
end it is asked for, and the driver's discovery of the real rule modules raises: nothing of the study's rules,
hold-out or Early window is touched here, even after the tmp freeze.

* The grid: the plan's count table sums to PREREG 7's 738 / 720 eligible rows; the stubs' grid is counted and checked;
  duplicate ids, bad fields and a wrong count stop with every difference listed.
* ``run``: 2 workers give the bytes of 1; a resumed run skips the complete variants and computes the missing,
  truncated, damaged, unreadable and failed ones; a change of the code during a run stops it; a change of the data
  recomputes everything; a dying worker stops its batch; the markets are loaded only to the hold-out start.
* PREREG 7's qualification on hand-made tables, each condition at and next to its threshold; the champions and
  finalists with ties and the one-per-script-group rule; multiple testing over both universes.
* ``freeze`` writes what ``M.frozen()`` accepts (in the tmp study folder), parses its text first, rolls back a failure
  after writing, refuses a second time, refuses stale code, moved data, a changed grid and a champion whose
  Development row needs later bars; the test-only options are refused on the study folder itself.
* ``exam`` and ``accounts`` refuse before the freeze; after it they refuse other code (unless allowed and recorded)
  and moved inputs; the exam voids a champion whose rows change on the data to the data end; the verdicts, the base
  rate and every variant's look-ahead check on the synthetic markets.
* The accounts' export round-trips through COMPARE DATA CONTRACT v1 (the driver's check and the page's own
  validator), checked against direct runs; the references (buy-and-hold, study 1's finalists) sit next to them.
* ``claims`` and ``report`` run on the stub grid, name the module functions they cannot find, refuse a claim row
  counted outside the windows, and pair the filters and our combinations by the PREREG's names.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2 as D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_stub_rules as STUB  # noqa: E402

WINDOWS = {"dev": ("2020-09-07", "2020-10-05"), "val": ("2020-10-05", "2020-10-12"),
           "devval": ("2020-09-07", "2020-10-12"), "holdout": ("2020-10-12", "2020-10-23"),
           "full": ("2020-09-07", "2020-10-23"), "early": ("2020-08-24", "2020-09-07")}
OUTPUTS = ("grid.csv", "results_dev_val.csv", "quarters_dev_val.csv", "trades_dev_val.csv.gz",
           "weekly_dev_val.csv.gz", "buy_and_hold.csv")
ORACLE = {s: f"{s}|1H|RIB|LO|ORACLE|F0" for s in M.SYMBOLS}
DRAWN = {s: f"{s}|1H|HP-HARMONIC|HP-DRAWN|TP1" for s in M.SYMBOLS}


def quiet(*_a, **_k):
    pass


@pytest.fixture(autouse=True)
def sealed(tmp_path, monkeypatch):
    """The guards read empty tmp folders; the windows, the hold-out start and the Early window are synthetic; real
    market data cannot be reached; the code identity is the harness, the driver and the stubs (the ports being
    written in parallel are left out)."""
    d2, d1 = tmp_path / "study2", tmp_path / "study1"
    d2.mkdir()
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    for k, v in WINDOWS.items():
        monkeypatch.setitem(M.WINDOWS, k, v)
    monkeypatch.setattr(M, "HOLDOUT_START", WINDOWS["holdout"][0])
    monkeypatch.setattr(M, "CUT_S", M.s_of(WINDOWS["holdout"][0]))
    monkeypatch.setattr(M, "EARLY", WINDOWS["early"])
    monkeypatch.setattr(M, "EARLY_S", tuple(M.s_of(x) for x in WINDOWS["early"]))
    monkeypatch.setattr(D, "port_files", lambda: [])

    def real(*_a, **_k):
        raise AssertionError("a test reached for real market data")
    for mod, name in ((M, "load"), (D, "_load_default"), (M.store, "load_m1"), (TM, "binance_volume"),
                      (M, "binance_volume"), (M, "binance_volume_5m"), (D, "binance_identity")):
        monkeypatch.setattr(mod, name, real)

    def rules(*_a, **_k):
        raise AssertionError("a test reached for the study's rule modules (only the stubs may run here)")
    monkeypatch.setattr(D, "find_modules", rules)
    return d2


def fake_binance(monkeypatch):
    """Study 1's BTC rows read Binance volume (its VWRSI-RV lines): the synthetic tick volume stands in for it."""
    monkeypatch.setattr(TM, "binance_volume", lambda mk, tf: (np.asarray(mk.tbars(tf).vol, np.float64),
                                                              np.zeros(len(mk.tbars(tf)), np.int64)))


def run_stubs(d, workers=1, modules=None, counts=None, loader=None, log=quiet):
    return D.run(d, STUB.MODULES if modules is None else modules, STUB.COUNTS if counts is None else counts,
                 workers=workers, loader=loader or STUB.LOADER, log=log)


def selected(d, modules=None, counts=None):
    run_stubs(d, modules=modules, counts=counts)
    return D.select(d, STUB.MODULES if modules is None else modules, log=quiet)["qualification"]


def frozen(d, modules=None, counts=None):
    qual = selected(d, modules, counts)
    D.freeze(d, STUB.MODULES if modules is None else modules, STUB.COUNTS if counts is None else counts,
             require_all=False, loader=STUB.LOADER, log=quiet)
    return qual


def copied_modules(tmp_path, base=None):
    """The stubs with their __file__ on a copy of the stub file, so that a test can change 'the code'."""
    f = tmp_path / "code" / "tradeiq2_stub_rules.py"
    f.parent.mkdir(exist_ok=True)
    f.write_bytes(Path(STUB.__file__).read_bytes())
    return {k: SimpleNamespace(**{**vars(m), "__file__": str(f)}) for k, m in (base or STUB.MODULES).items()}, f


def peeking_state(ctx, k: int = 24):
    """The generator's oracle where the served market holds at least ``k`` more bars, else flat: a state that needs
    later bars (like a pattern confirmed only later), i.e. look-ahead that a market cut earlier reveals."""
    st = STUB.oracle_state(ctx, "1H").copy()
    st[-k:] = 0
    return st


def coil_module(rows):
    """A test-only 'coil' module of gold 1H rows: 'peek' (``peeking_state``), 'peek-val' (the generator's oracle in
    Development, ``peeking_state`` from the Validation start on), 'peek-loser' (the oracle's opposite, flat on the
    served market's last bars: it never qualifies, and it looks ahead) and 'legs' (the generator's oracle with
    PREREG 4's 50/50 partial exits)."""
    kinds = dict(rows)

    def variants(s):
        if s != M.GOLD:
            return []
        return [M.Variant(f"{s}|1H|COIL|{rest}", s, "1H", "COIL", "COIL") for rest, _ in rows]

    def build(v, ctx):
        kind = kinds[v.id.split("|", 3)[3]]
        if kind == "legs":
            return M.state_exec("1H", STUB.oracle_state(ctx, "1H"), STUB._stop(ctx, "1H"),
                                legs=(M.Leg(0.5, target_r=2.0), M.Leg(0.5, no_target=True)))
        st = peeking_state(ctx)
        if kind == "peek-loser":
            st = np.where(np.arange(len(st)) < len(st) - 24, 1 - STUB.oracle_state(ctx, "1H"), 0) * STUB._live(
                ctx.bars("1H"))
        if kind == "peek-val":
            b = ctx.bars("1H")
            st = np.where(b.t >= M.s_of(M.window_span("val", v.symbol)[0]), st, STUB.oracle_state(ctx, "1H"))
        return M.state_exec("1H", st)
    return SimpleNamespace(variants=variants, build=build, __file__=STUB.__file__)


def loser_module():
    """A test-only 'swing' module with one gold 1H row (family SP) that is the generator's oracle inside Development +
    Validation and its opposite outside: it qualifies, and fails both exams (and it is causal for the cut checks)."""
    def variants(s):
        return [M.Variant(f"{s}|1H|SP|LOSER", s, "1H", "SP", "SP")] if s == M.GOLD else []

    def build(v, ctx):
        b = ctx.bars("1H")
        up = STUB.oracle_state(ctx, "1H")
        inside = (b.t >= M.s_of(WINDOWS["devval"][0])) & (b.tc <= M.s_of(WINDOWS["devval"][1]))
        return M.state_exec("1H", np.where(inside, up, 1 - up) * STUB._live(b))
    return SimpleNamespace(variants=variants, build=build, __file__=STUB.__file__)


def with_coil(rows, no_btc_oracle=False, loser=False):
    """The stubs plus ``coil_module(rows)`` (and ``loser_module`` as 'swing'), with their count table; optionally
    without BTC's oracle row (BTC then has no champion)."""
    mods = dict(STUB.MODULES, coil=coil_module(rows))
    table = STUB.TABLE + (("coil", "COIL", True, len(rows), 0, "test"),)
    if loser:
        mods["swing"] = loser_module()
        table += (("swing", "SP", True, 1, 0, "test"),)
    if no_btc_oracle:
        rib = STUB.MODULES["ribbon"]
        mods["ribbon"] = SimpleNamespace(**{**vars(rib), "variants": lambda s: [
            v for v in rib.variants(s) if not (s == M.BTC and "ORACLE" in v.id)]})
        table = tuple(("ribbon", "RIB", True, 5, 4, "test") if r[:3] == ("ribbon", "RIB", True) else r for r in table)
    return mods, D.counts_of(table)


# ───────────────────────────── the grid ─────────────────────────────

def test_the_plan_table_sums_to_prereg_7s_sizes():
    el = {s: 0 for s in D.SYMBOLS}
    for c in D.PREREG_COUNTS:
        if c.eligible and c.symbol in el:
            el[c.symbol] += c.n
    assert el == D.PLAN_ELIGIBLE == {"XAUUSDm": 738, "BTCUSDm": 720}
    assert {c.family for c in D.PREREG_COUNTS} == set(D.FAMILIES)
    assert all(c.family in D.MODULE_FAMILIES[c.module] for c in D.PREREG_COUNTS)

    def n(module, sym="XAUUSDm", eligible=True, family=None):
        return sum(c.n or 0 for c in D.PREREG_COUNTS if c.module == module and c.symbol == sym
                   and c.eligible == eligible and (family is None or c.family == family))
    assert n("ribbon", family="RIB") == 2 * 4 * (7 + 6 + 4) and n("ribbon", family="STK") == 3 * 2 * 3
    assert n("msd") == 150 and n("wyckoff") == 54 and n("swing") == 24 and n("session") == 116
    assert n("patterns") == 48 and n("ha") == 54 + 24 and n("coil") == 36
    assert n("orb") == 50 + 10 + 8 + 4 and n("orb", "BTCUSDm") == 50 + 4
    assert n("wyckoff", "BTCUSDm", False) == 3 and n("wyckoff", "XAUUSDm", False) == 0
    # every family is in exactly one script group, as PREREG 7 lists them
    assert {g: sorted(f for f in D.FAMILIES if D.GROUP[f] == g) for g in set(D.GROUP.values())} == {
        "RIB": ["ALMA-X", "RIB"], "MSD": ["BOS", "MSD-ALONE", "MSD-FILTER"], "WY": ["WY", "WY-DERIVED"],
        "HP": ["HP-CHART", "HP-HARMONIC"], "HA": ["HA-ENTRY", "HA-MANAGED"], "SP": ["SP"], "ORB": ["ORB"],
        "SH": ["SH"], "COIL": ["COIL"], "STK": ["STK"]}
    # the page's common windows the accounts cover: 5y and 1y on both symbols, 8y and new on gold (PREREG 9)
    assert [w for w, which, _ in D.ACCOUNT_PLAN if which == "all"] == ["5y", "8y", "1y", "new"]
    assert set(D.GOLD_ONLY) >= {"8y", "new", "early"}
    assert {"backtesting/config.py", "backtesting/data/store.py"} <= set(D.RUN_CODE)


def test_the_stub_grid_is_counted_checked_and_written(sealed):
    g, pairs = D.checked_grid(STUB.MODULES, STUB.COUNTS)
    assert len(g) == len(pairs) == STUB.N_VARIANTS and g.vid.is_unique
    assert list(g.columns) == list(D.GRID_COLUMNS)
    assert list(g.symbol.drop_duplicates()) == ["XAUUSDm", "BTCUSDm", "USTECm"]
    assert not g[g.symbol == "USTECm"].eligible.any()
    assert (g.group == g.family.map(D.GROUP)).all()
    rep = D.count_report(g, STUB.COUNTS, STUB.MODULES)
    assert set(rep.status) == {"ok", "not checked"}
    assert sorted(rep[rep.status == "not checked"].symbol) == ["EURUSDm", "GBPUSDm", "USTECm"]
    assert D.main(["grid", "--study-dir", str(sealed), "--rules", STUB.__file__]) == 0
    assert pd.read_csv(sealed / "grid.csv").vid.tolist() == g.vid.tolist()


def _module(variants):
    return SimpleNamespace(variants=variants, build=lambda v, ctx: None, __file__=STUB.__file__)


def test_duplicate_ids_and_bad_fields_stop_the_grid_with_every_problem():
    def coil(s):
        if s not in M.SYMBOLS:
            return []
        return [M.Variant(f"{s}|4H|COIL|A", s, "4H", "COIL", "COIL"), M.Variant(f"{s}|4H|COIL|A", s, "4H", "COIL",
                                                                               "COIL"),
                M.Variant(f"{s}|4H|COIL|B", s, "4H", "COIL", "RIB"), M.Variant(f"{s}|1H|COIL|C", s, "4H", "COIL",
                                                                              "COIL"),
                M.Variant(f"{s}|2H|COIL|D", s, "2H", "COIL", "COIL"), M.Variant(f"{s}|4H|COIL|`E`", s, "4H", "COIL",
                                                                               "COIL"), "not a variant"]
    with pytest.raises(D.GridError) as e:
        D.checked_grid({"coil": _module(coil)}, counts=())
    msg = str(e.value)
    for s in M.SYMBOLS:
        assert f"duplicate id '{s}|4H|COIL|A'" in msg
        assert f"{s}|4H|COIL|B has family 'RIB', not one of coil's (COIL)" in msg
        assert f"'{s}|1H|COIL|C' does not start with symbol|tf|" in msg
        assert f"{s}|2H|COIL|D has timeframe '2H'" in msg
        assert f"'{s}|4H|COIL|`E`' holds white space or a backtick" in msg
    assert msg.count("is not a tradeiq2_market.Variant") == 2

    def session(s):
        return [M.Variant(f"{s}|M5|SH|X", s, "M5", "SH", "SH", eligible=True)]
    with pytest.raises(D.GridError, match=re.escape("USTECm|M5|SH|X is eligible, but the claim markets are")):
        D.checked_grid({"session": _module(session)}, counts=())
    with pytest.raises(D.GridError, match="not a rule module"):
        D.checked_grid({"nine": _module(session)})
    with pytest.raises(D.GridError, match=re.escape("no build()")):
        D.checked_grid({"coil": SimpleNamespace(variants=coil)})


def test_a_wrong_count_stops_with_the_differences():
    table = list(STUB.TABLE)
    table[0] = ("ribbon", "RIB", True, 6, 5, "stub, one too many on gold")
    g, _ = D.checked_grid(STUB.MODULES, STUB.COUNTS)
    diff = D.count_differences(g, D.counts_of(tuple(table)), STUB.MODULES)
    assert diff[["module", "symbol", "family", "eligible", "expected", "got", "status"]].values.tolist() == [
        ["ribbon", "XAUUSDm", "RIB", True, 6, 5, "DIFFERS"]]
    with pytest.raises(D.GridError, match=r"ribbon\s+XAUUSDm\s+RIB\s+True\s+6\s+5\s+DIFFERS"):
        D.checked_grid(STUB.MODULES, D.counts_of(tuple(table)))
    # a family the table does not know for that module and eligibility is listed as such
    no_orb_controls = tuple(r for r in STUB.TABLE if r[:3] != ("orb", "ORB", False))
    diff = D.count_differences(g, D.counts_of(no_orb_controls), STUB.MODULES)
    assert set(diff.status) == {"not in the plan"} and sorted(diff.symbol) == ["BTCUSDm", "XAUUSDm"]
    # the plan's own table against the stubs: the families differ, and those the stubs lack count 0
    with pytest.raises(D.GridError) as e:
        D.checked_grid(STUB.MODULES)
    msg = str(e.value)
    assert re.search(r"ribbon\s+XAUUSDm\s+RIB\s+True\s+136\s+5\s+DIFFERS", msg)
    assert re.search(r"msd\s+BTCUSDm\s+BOS\s+True\s+12\s+0\s+DIFFERS", msg)
    assert not re.search(r"wyckoff\s+XAUUSDm\s+WY\s+False", msg)        # gold has no WY control: 0 = 0


# ───────────────────────────── the guard on the synthetic dates ─────────────────────────────

def test_the_guard_refuses_the_synthetic_hold_out_and_early_window_before_the_freeze(sealed):
    with pytest.raises(M.HoldOutError):
        STUB.market("XAUUSDm", "2020-10-20")                   # an end past the (synthetic) hold-out start
    ctx = M.Context(STUB.LOADER("XAUUSDm", None))              # end None, not frozen: cut at the hold-out start
    assert int(ctx.mk.end_s) == M.CUT_S
    ex = STUB.MODULES["ribbon"].build(M.Variant(ORACLE["XAUUSDm"], "XAUUSDm", "1H", "RIB", "RIB"), ctx)
    with pytest.raises(M.HoldOutError, match="Early window"):
        M.run_exec(ctx.mk, ex, *WINDOWS["early"])
    with pytest.raises((M.HoldOutError, ValueError)):
        M.run_exec(ctx.mk, ex, *WINDOWS["holdout"])
    assert M.run_exec(ctx.mk, ex, *WINDOWS["dev"]).net != 0


# ───────────────────────────── run: workers, resume, failures, identity ─────────────────────────────

def test_a_run_with_two_workers_is_the_run_with_one(tmp_path):
    a, b = tmp_path / "w1", tmp_path / "w2"
    logs = []
    sa, sb = run_stubs(a, workers=1), run_stubs(b, workers=2, log=logs.append)
    assert sa["computed"] == sb["computed"] == STUB.N_VARIANTS and sa["missing"] == sb["missing"] == []
    for f in OUTPUTS:
        assert (a / f).read_bytes() == (b / f).read_bytes(), f
    assert any("workers' peak" in x for x in logs)              # the workers' memory is in the progress note
    drop = ["seconds", "workers", "written_utc"]
    pd.testing.assert_frame_equal(pd.read_csv(a / "run_info.csv").drop(columns=drop),
                                  pd.read_csv(b / "run_info.csv").drop(columns=drop))
    res = D.read_results(a)
    assert len(res) == STUB.N_VARIANTS * 3 and res.vid.tolist()[::3] == D.read_grid(a).vid.tolist()
    assert list(res.columns[:13]) == list(D.IDENT_COLS) + ["window", "start", "end"]
    for c in ("net", "profit_dd", "pos_q_share", "avg_r", "pf_r", "r_trades", "n_candidates", "n_busy",
              "n_dropped_stop", "net_x15", "avg_r_x15", "n_taken_x15", "legs", "lanes"):
        assert c in res.columns, c
    assert list(pd.read_csv(a / "quarters_dev_val.csv").columns) == list(D.QUARTER_COLS)
    assert list(pd.read_csv(a / "weekly_dev_val.csv.gz").columns) == list(D.WEEK_COLS)
    tr = pd.read_csv(a / "trades_dev_val.csv.gz")
    assert list(tr.columns) == list(D.TRADE_COLS) and set(tr.window) == {"dev", "val"} and set(tr.cost) == {1.0, 1.5}
    assert list(pd.read_csv(a / "buy_and_hold.csv").columns) == list(D.BH_COLS)
    info = pd.read_csv(a / "run_info.csv")
    assert list(info.columns[:7]) == list(D.INFO_COLS) + list(D.DATA_COLS) and (info.done == info.variants).all()
    assert {"env python", "env numpy", "env pandas", "env numba", "blob config.py", "blob store.py"} <= set(info.columns)
    assert info.data_sha1.str.len().eq(40).all()
    assert (a / "run_parts" / ".gitignore").read_text().strip().endswith("*")
    # the legs row and the lanes row are there with their counts and shapes
    d = res[res.window == "dev"].set_index("vid")
    assert d.loc["XAUUSDm|M5|SH|PRESET-CUSTOM|K2|E1", "n_taken"] > 0
    assert (d.loc["XAUUSDm|M5|SH|PRESET-CUSTOM|K2|E1", "lanes"], d.loc["XAUUSDm|1H|RIB|LS|XP|F0", "legs"]) == (2, 2)
    assert d.loc["XAUUSDm|M15|ORB|O5|F0", "n_unfilled"] >= 0 and d.loc["XAUUSDm|1H|RIB|LS|XP|F0", "trades"] > 0


def test_run_loads_every_market_only_to_the_hold_out_start(sealed):
    ends = []

    def loader(symbol, end):
        ends.append((symbol, end))
        return STUB.LOADER(symbol, end)
    run_stubs(sealed, loader=loader)
    assert sorted(ends) == sorted((s, WINDOWS["holdout"][0]) for s in ("XAUUSDm", "BTCUSDm", "USTECm"))


def test_a_resumed_run_skips_the_complete_variants_and_computes_the_rest(sealed):
    n = STUB.N_VARIANTS
    assert run_stubs(sealed)["computed"] == n
    ref = {f: (sealed / f).read_bytes() for f in OUTPUTS}
    again = run_stubs(sealed)
    assert (again["computed"], again["skipped"], again["markets"]) == (0, n, 3)    # loaded for their identity
    parts = sorted((sealed / "run_parts" / D.DEVVAL).rglob("*.pkl.gz"))
    assert len(parts) == n
    p1, p2 = parts[3], parts[17]
    p1.write_bytes(p1.read_bytes()[:50])                      # a half-written part
    D._side(p2).unlink()                                      # a part whose sidecar never got written
    (p1.parent / f".{p1.name}.tmp999").write_bytes(b"half")  # a temporary file left by a killed worker
    st = run_stubs(sealed)
    assert (st["computed"], st["skipped"]) == (2, n - 2)
    assert not list((sealed / "run_parts").rglob(".*.tmp*"))
    for f, b in ref.items():
        assert (sealed / f).read_bytes() == b, f
    # a run of one symbol and one module assembles every complete part all the same
    st = D.run(sealed, STUB.MODULES, STUB.COUNTS, symbols=["BTCUSDm"], keys=["orb"], loader=STUB.LOADER, log=quiet)
    assert (st["computed"], st["done"]) == (0, n)


def test_a_damaged_or_unreadable_part_is_computed_again(sealed):
    run_stubs(sealed)
    ref = {f: (sealed / f).read_bytes() for f in OUTPUTS}
    parts = sorted((sealed / "run_parts" / D.DEVVAL).rglob("*.pkl.gz"))
    b = bytearray(parts[5].read_bytes())
    b[-12] ^= 0xFF                                            # one byte flipped: the same size, another sha1
    parts[5].write_bytes(bytes(b))
    assert run_stubs(sealed)["computed"] == 1
    for f, x in ref.items():
        assert (sealed / f).read_bytes() == x, f
    # a part whose sidecar matches but whose pickle cannot be read (e.g. another pandas): incomplete at the assembly
    junk = gzip.compress(b"not a pickle", mtime=0)
    parts[7].write_bytes(junk)
    side = json.loads(D._side(parts[7]).read_text())
    side.update(size=len(junk), sha1=hashlib.sha1(junk).hexdigest())
    D._side(parts[7]).write_text(json.dumps(side, sort_keys=True))
    st = run_stubs(sealed)
    assert st["computed"] == 0 and len(st["missing"]) == 1 and not D._side(parts[7]).exists()
    st = run_stubs(sealed)
    assert st["computed"] == 1 and st["missing"] == []
    for f, x in ref.items():
        assert (sealed / f).read_bytes() == x, f


def test_a_failing_variant_leaves_no_half_written_csv_and_is_computed_after_the_fix(tmp_path):
    ref, d = tmp_path / "ref", tmp_path / "broken"
    run_stubs(ref)

    def build(v, ctx):
        if v.id.endswith("|O2|F0"):
            raise RuntimeError("boom")
        return STUB.MODULES["orb"].build(v, ctx)
    broken = dict(STUB.MODULES, orb=SimpleNamespace(variants=STUB.MODULES["orb"].variants, build=build,
                                                    __file__=STUB.__file__))
    with pytest.raises(D.RunError, match=re.escape("XAUUSDm|M15|ORB|O2|F0")):
        run_stubs(d, workers=2, modules=broken)
    assert not (d / "results_dev_val.csv").exists() and not (d / "trades_dev_val.csv.gz").exists()
    done = len([p for p in (d / "run_parts" / D.DEVVAL).rglob("*.json") if p.parent.name != "_market"])
    order = [v.id for _, v in D.collect(STUB.MODULES)[0]]
    o2 = order.index("XAUUSDm|M15|ORB|O2|F0")
    assert done == o2 + 2                                     # gold's variants up to its orb module, but O2, are kept
    st = run_stubs(d)
    assert st["computed"] == STUB.N_VARIANTS - done
    for f in OUTPUTS:
        assert (d / f).read_bytes() == (ref / f).read_bytes(), f


def test_a_worker_that_dies_stops_its_batch_with_the_variant_it_held(sealed):
    parent = os.getpid()
    target = "XAUUSDm|M15|ORB|O2|F0"

    def build(v, ctx):
        if v.id == target and os.getpid() != parent:
            os.kill(os.getpid(), signal.SIGKILL)                # an OS memory kill, in a worker only
        return STUB.MODULES["orb"].build(v, ctx)
    mods = dict(STUB.MODULES, orb=SimpleNamespace(variants=STUB.MODULES["orb"].variants, build=build,
                                                  __file__=STUB.__file__))
    t0 = time.time()
    with pytest.raises(D.RunError, match=r"died \(exit code -9\).*it held " + re.escape(target)):
        run_stubs(sealed, workers=2, modules=mods)
    assert time.time() - t0 < 120
    assert not (sealed / "results_dev_val.csv").exists()
    st = run_stubs(sealed)                                    # after the fix (in process): the rest only
    assert st["missing"] == [] and 0 < st["computed"] < STUB.N_VARIANTS


def test_a_change_of_the_code_during_a_run_stops_it(sealed, tmp_path):
    mods, f = copied_modules(tmp_path)
    old = D.T1.blob_id(f)

    def loader(symbol, end):
        if symbol == M.BTC:
            f.write_text(f.read_text() + "\n# edited while gold's parts were being computed\n")
        return STUB.LOADER(symbol, end)
    with pytest.raises(D.CodeChangedError, match="tradeiq2_stub_rules.py"):
        D.run(sealed, mods, STUB.COUNTS, loader=loader, log=quiet)
    sides = [json.loads(p.read_text()) for p in (sealed / "run_parts" / D.DEVVAL).rglob("*.json")
             if p.parent.name != "_market"]
    # every part kept carries the code it was computed with (the run's snapshot), none the edited file's
    assert sides and {s["stamp"]["blobs"]["blob tradeiq2_stub_rules.py"] for s in sides} == {old}
    assert {s["stamp"]["ident"]["symbol"] for s in sides} == {M.GOLD}
    assert not (sealed / "results_dev_val.csv").exists()
    st = D.run(sealed, mods, STUB.COUNTS, loader=STUB.LOADER, log=quiet)      # the edited code: every part again
    assert (st["computed"], st["skipped"]) == (STUB.N_VARIANTS, 0)
    assert (pd.read_csv(sealed / "run_info.csv")["blob tradeiq2_stub_rules.py"] == D.T1.blob_id(f)).all()


def _moved(symbol, end):
    """The stub market with every price x1.0001: other data."""
    mk = STUB.LOADER(symbol, end)
    m1 = {"t": mk.t.copy(), "o": mk.o * 1.0001, "h": mk.h * 1.0001, "l": mk.l * 1.0001, "c": mk.c * 1.0001,
          "spread_mean": mk.sp.copy(), "n": mk.n.copy()}
    return M.TMarket2(symbol, m1, mk.end_s)


def test_a_change_of_the_data_recomputes_every_part_and_stops_the_freeze(sealed):
    run_stubs(sealed)
    sha = pd.read_csv(sealed / "run_info.csv").groupby("symbol").data_sha1.first()
    D.select(sealed, STUB.MODULES, log=quiet)
    with pytest.raises(RuntimeError, match="the data served now differ"):
        D.freeze(sealed, STUB.MODULES, STUB.COUNTS, require_all=False, loader=_moved, log=quiet)
    assert not (sealed / D.FINALISTS_MD).exists()
    st = run_stubs(sealed, loader=_moved)
    assert (st["computed"], st["skipped"]) == (STUB.N_VARIANTS, 0)
    now = pd.read_csv(sealed / "run_info.csv").groupby("symbol").data_sha1.first()
    assert (now != sha).all()


# ───────────────────────────── PREREG 7: qualification, champions, finalists ─────────────────────────────

def results_table(specs):
    """Hand-made results_dev_val rows: per variant a dict with 'vid' and optionally 'family', 'tf', 'eligible' and
    per window ('dev', 'val', 'devval') the scores that differ from a row that passes everything."""
    rows = []
    for sp in specs:
        vid = sp["vid"]
        fam = sp.get("family", "RIB")
        mod = next(k for k, f in D.MODULE_FAMILIES.items() if fam in f)
        for w in D.RUN_WINDOWS:
            r = {"vid": vid, "module": mod, "symbol": vid.split("|")[0], "tf": sp.get("tf", "1H"), "script": fam,
                 "family": fam, "group": D.GROUP[fam], "eligible": sp.get("eligible", True), "info": "",
                 "params": "{}", "window": w, "net": 100.0, "net_x15": 90.0, "trades": 40, "max_dd": 10.0,
                 "profit_dd": 10.0, "pos_q_share": 0.75, "sharpe_w": 1.0}
            r.update(sp.get(w, {}))
            rows.append(r)
    return pd.DataFrame(rows)


def test_qualification_at_and_next_to_every_threshold():
    G = "XAUUSDm|1H|RIB|"
    tiny = 1e-9
    specs = [{"vid": G + "ok"},
             {"vid": G + "dev0", "dev": {"net": 0.0}}, {"vid": G + "devtiny", "dev": {"net": tiny}},
             {"vid": G + "x15_0", "dev": {"net_x15": 0.0}}, {"vid": G + "x15neg", "dev": {"net_x15": -tiny}},
             {"vid": G + "x15tiny", "dev": {"net_x15": tiny}},
             {"vid": G + "pdd1", "dev": {"profit_dd": 1.0}}, {"vid": G + "pddlow", "dev": {"profit_dd": 1.0 - 1e-12}},
             {"vid": G + "pddnan", "dev": {"profit_dd": np.nan}},
             {"vid": G + "q50", "dev": {"pos_q_share": 0.5}}, {"vid": G + "q49", "dev": {"pos_q_share": 0.5 - 1e-12}},
             {"vid": G + "val0", "val": {"net": 0.0}}, {"vid": G + "valtiny", "val": {"net": tiny}},
             {"vid": G + "valx15", "val": {"net": tiny, "net_x15": -50.0}},
             {"vid": G + "noteligible", "eligible": False},
             {"vid": "USTECm|M5|SH|claim", "family": "SH", "tf": "M5", "eligible": False}]
    for tf, lo in (("M5", 30), ("M15", 30), ("1H", 30), ("4H", 30), ("1D", 15)):
        fam = {"M5": "SH", "M15": "ORB", "1H": "RIB", "4H": "COIL", "1D": "WY"}[tf]
        specs += [{"vid": f"XAUUSDm|{tf}|{fam}|t{lo}", "family": fam, "tf": tf, "dev": {"trades": lo}},
                  {"vid": f"XAUUSDm|{tf}|{fam}|t{lo - 1}", "family": fam, "tf": tf, "dev": {"trades": lo - 1}}]
    q = D.qualification(results_table(specs)).set_index("vid")
    want = {"ok": "1111", "dev0": "0111", "devtiny": "1111", "x15_0": "0111", "x15neg": "0111", "x15tiny": "1111",
            "pdd1": "1111", "pddlow": "1101", "pddnan": "1101", "q50": "1111", "q49": "1101", "val0": "1110",
            "valtiny": "1111", "valx15": "1111", "noteligible": "1111"}
    for k, bits in want.items():
        got = "".join(str(int(q.at[G + k, c])) for c in ("q1", "q2", "q3", "q4"))
        assert got == bits, k
        assert q.at[G + k, "qualifies"] == (bits == "1111" and k != "noteligible"), k
    for tf, lo in (("M5", 30), ("M15", 30), ("1H", 30), ("4H", 30), ("1D", 15)):
        fam = {"M5": "SH", "M15": "ORB", "1H": "RIB", "4H": "COIL", "1D": "WY"}[tf]
        assert q.at[f"XAUUSDm|{tf}|{fam}|t{lo}", "q2"] and not q.at[f"XAUUSDm|{tf}|{fam}|t{lo - 1}", "q2"], tf
        assert q.at[f"XAUUSDm|{tf}|{fam}|t{lo}", "min_trades"] == lo
    assert not q.at["USTECm|M5|SH|claim", "qualifies"] and np.isnan(q.at["USTECm|M5|SH|claim", "rank"])
    assert q.at["XAUUSDm|1D|WY|t14", "insufficient_events"] and not q.at["XAUUSDm|1D|WY|t15", "insufficient_events"]
    with pytest.raises(ValueError, match="exactly one dev, val and devval row"):
        D.qualification(results_table([{"vid": G + "ok"}]).iloc[:2])


def test_champions_and_finalists_ties_and_one_per_script_group():
    G, B = "XAUUSDm|1H|", "BTCUSDm|4H|"

    def sp(vid, fam, dv, dpdd, dev=None, **kw):
        return {"vid": vid, "family": fam, "devval": {"profit_dd": dv}, "dev": {"profit_dd": dpdd, **(dev or {})},
                **kw}
    specs = [sp(G + "RIB|A", "RIB", 3.0, 2.0), sp(G + "RIB|B", "RIB", 3.0, 2.5),          # a tie on D+V: B by dev
             sp(G + "ALMA-X|C", "ALMA-X", 2.9, 2.0),                                       # champion, RIB's group
             sp(G + "SH|D", "SH", 2.0, 1.8),
             sp(G + "ORB|E", "ORB", 2.0, 1.5), sp(G + "SP|G", "SP", 2.0, 1.5),             # a full tie: by the id
             sp(G + "SH|H", "SH", 5.0, 5.0, val={"net": -1.0}),                            # fails q4
             sp(G + "COIL|I", "COIL", 9.0, 9.0, eligible=False),                           # not eligible
             sp(B + "STK|J", "STK", 1.5, 1.2), sp(B + "COIL|K", "COIL", 1.0, 1.1, dev={"net": -1.0})]
    q = D.qualification(results_table(specs)).set_index("vid")
    assert q[q.qualifies].index.tolist() == [G + x for x in ("RIB|A", "RIB|B", "ALMA-X|C", "SH|D", "ORB|E", "SP|G")] \
        + [B + "STK|J"]
    assert {v: int(q.at[v, "rank"]) for v in q.index[q.qualifies]} == {
        G + "RIB|B": 1, G + "RIB|A": 2, G + "ALMA-X|C": 3, G + "SH|D": 4, G + "ORB|E": 5, G + "SP|G": 6, B + "STK|J": 1}
    ch = q[q.champion].sort_values(["symbol", "champion_rank"])
    assert ch.index.tolist() == [B + "STK|J"] + [G + x for x in ("RIB|B", "ALMA-X|C", "SH|D", "ORB|E", "SP|G")]
    assert q[q.finalist].index.tolist() == [G + "RIB|B", G + "SH|D", G + "ORB|E", B + "STK|J"]
    assert int(q.at[G + "RIB|A", "family_rank"]) == 2
    assert D.champions_in_order(q.reset_index()) == [("finalist", G + "RIB|B"), ("champion", G + "ALMA-X|C"),
                                                     ("finalist", G + "SH|D"), ("finalist", G + "ORB|E"),
                                                     ("champion", G + "SP|G"), ("finalist", B + "STK|J")]
    ct = D.champions_table(q.reset_index()).set_index(["symbol", "family"])
    assert ct.loc[("XAUUSDm", "COIL"), "champion"] == "none" and ct.loc[("BTCUSDm", "COIL"), "champion"] == "none"
    assert len(ct) == 2 * len(D.FAMILIES)
    fb = D.family_best(q.reset_index()).set_index(["symbol", "family"])
    assert fb.loc[("BTCUSDm", "COIL"), "vid"] == B + "COIL|K" and not fb.loc[("BTCUSDm", "COIL"), "champion"]
    assert ("XAUUSDm", "COIL") not in fb.index                  # no eligible row


def test_multiple_testing_counts_every_variant_run_and_the_eligible_ones_apart(sealed):
    qual = selected(sealed)
    mt = pd.read_csv(sealed / "multiple_testing.csv")
    assert list(mt.universe.drop_duplicates()) == ["all variants run", "eligible variants"]
    for s in M.SYMBOLS:
        n_all = int((qual.symbol == s).sum())
        n_el = int(((qual.symbol == s) & qual.eligible).sum())
        a = mt[(mt.symbol == s) & (mt.universe == "all variants run")]
        e = mt[(mt.symbol == s) & (mt.universe == "eligible variants")]
        assert (a.N == n_all).all() and (e.N == n_el).all() and n_all == STUB.N_GOLD > n_el
        assert (a.N_all == n_all).all() and (a.N_eligible == n_el).all()
        assert set(a.role.str[:15]) >= {"best dev Sharpe", "would-be finali"}
    text = (sealed / "CANDIDATES.md").read_text()
    assert "all variants run" in text and "eligible variants" in text


def test_partial_exit_rows_carry_the_0_02_lot_note(sealed):
    mods, counts = with_coil([("LEGS", "legs")])
    qual = selected(sealed, mods, counts)
    q = qual.set_index("vid")
    assert q.at["XAUUSDm|1H|COIL|LEGS", "champion"] and q.at["XAUUSDm|1H|COIL|LEGS", "legs"] == 2
    draft = (sealed / D.DRAFT_MD).read_text()
    line = next(x for x in draft.splitlines() if x.startswith(tuple(f"{j}. `XAUUSDm|1H|COIL|LEGS`" for j in
                                                                    range(1, 20))))
    assert "0.02 lot per unit" in line
    assert "0.02 lot per unit" in (sealed / "CANDIDATES.md").read_text()
    assert D.legs_note(1) == "" and D.legs_note(2) == D.LEGS_NOTE


# ───────────────────────────── freeze ─────────────────────────────

def test_freeze_writes_what_the_guard_accepts_and_refuses_a_second_time(sealed):
    qual = selected(sealed)
    assert not M.frozen()
    with pytest.raises(D.GridError, match="needs every rule module"):
        D.freeze(sealed, STUB.MODULES, STUB.COUNTS, loader=STUB.LOADER)
    good = (sealed / "qualification.csv").read_bytes()
    bad = pd.read_csv(sealed / "qualification.csv")
    bad.loc[0, "qualifies"] = not bad.loc[0, "qualifies"]
    bad.to_csv(sealed / "qualification.csv", index=False)
    with pytest.raises(AssertionError, match="qualification.csv is not the selection"):
        D.freeze(sealed, STUB.MODULES, STUB.COUNTS, require_all=False, loader=STUB.LOADER, log=quiet)
    (sealed / "qualification.csv").write_bytes(good)
    assert not (sealed / D.FINALISTS_MD).exists() and not M.frozen()
    f = D.freeze(sealed, STUB.MODULES, STUB.COUNTS, require_all=False, loader=STUB.LOADER, log=quiet)
    assert M.frozen()
    text = f.read_bytes()
    assert (sealed / "FINALISTS.md.sha256").read_text() == hashlib.sha256(text).hexdigest() + "  FINALISTS.md\n"
    roles, blobs = D.read_frozen(sealed)
    assert roles == D.champions_in_order(qual) == [("finalist", ORACLE["XAUUSDm"]), ("finalist", ORACLE["BTCUSDm"])]
    assert blobs == D.blobs_of(D.all_code(STUB.MODULES)) and "blob tradeiq2_stub_rules.py" in blobs
    fz = D.read_frozen_all(sealed)
    assert set(fz.inputs) == set(D.INPUT_FILES) and fz.inputs["grid.csv"] == D.sha256_of(sealed / "grid.csv")
    assert fz.env == D.env_versions()
    assert D.read_frozen(sealed, D.DRAFT_MD) == (roles, blobs)
    assert b"(frozen)" in text and b"DRAFT" in (sealed / D.DRAFT_MD).read_bytes() and b"TEST FREEZE" in text
    chk = pd.read_csv(sealed / "freeze_checks.csv")
    assert chk.result.all() and set(chk.vid) == {ORACLE["XAUUSDm"], ORACLE["BTCUSDm"]}
    with pytest.raises(FileExistsError):
        D.freeze(sealed, STUB.MODULES, STUB.COUNTS, require_all=False, loader=STUB.LOADER, log=quiet)
    assert D.main(["freeze", "--study-dir", str(sealed), "--rules", STUB.__file__]) == 2
    assert M.frozen() and f.read_bytes() == text
    # once frozen, run and select would rewrite the files FINALISTS.md was frozen from: they refuse
    with pytest.raises(FileExistsError, match="would rewrite"):
        run_stubs(sealed)
    with pytest.raises(FileExistsError, match="would rewrite"):
        D.select(sealed, STUB.MODULES, log=quiet)
    assert D.main(["select", "--study-dir", str(sealed), "--rules", STUB.__file__]) == 2
    f.write_bytes(text + b" ")                                 # one byte more: the guard closes again
    assert not M.frozen()


def test_freeze_parses_its_text_before_writing_and_removes_a_failed_freeze(sealed, monkeypatch):
    rib = STUB.MODULES["ribbon"]
    fenced = dict(STUB.MODULES, ribbon=SimpleNamespace(**{
        **vars(rib), "describe": lambda v: "long while up; the settings:\n```text\nlength 21, offset 0.85\n```\n"
                                           "finalist " + v.id}))
    selected(sealed, fenced)
    real_frozen = M.frozen
    monkeypatch.setattr(M, "frozen", lambda: False)               # the guard does not see the file: roll back
    with pytest.raises(AssertionError, match="does not see FINALISTS.md as frozen"):
        D.freeze(sealed, fenced, STUB.COUNTS, require_all=False, loader=STUB.LOADER, log=quiet)
    assert not (sealed / D.FINALISTS_MD).exists() and not (sealed / "FINALISTS.md.sha256").exists()
    monkeypatch.setattr(M, "frozen", real_frozen)
    f = D.freeze(sealed, fenced, STUB.COUNTS, require_all=False, loader=STUB.LOADER, log=quiet)
    text = f.read_text()
    assert "length 21, offset 0.85" in text and "```text\nlength" not in text
    assert D.read_frozen(sealed)[0] == [("finalist", ORACLE["XAUUSDm"]), ("finalist", ORACLE["BTCUSDm"])]
    assert M.frozen()
    with pytest.raises(ValueError, match="unreadable line"):
        D.parse_frozen("```text\nfinalist a|b|c\nlength 21\n```\n")


def test_freeze_refuses_stale_code_and_a_changed_grid(sealed, tmp_path):
    mods, f = copied_modules(tmp_path)
    D.run(sealed, mods, STUB.COUNTS, loader=STUB.LOADER, log=quiet)
    f.write_text(f.read_text() + "\n# edited after the run\n")
    logs = []
    D.select(sealed, mods, log=logs.append)
    assert any(x.startswith("WARNING") and "tradeiq2_stub_rules.py" in x for x in logs)
    assert "**Stale results:** tradeiq2_stub_rules.py" in (sealed / "CANDIDATES.md").read_text()
    with pytest.raises(RuntimeError, match="tradeiq2_stub_rules.py differ from what wrote results_dev_val.csv"):
        D.freeze(sealed, mods, STUB.COUNTS, require_all=False, loader=STUB.LOADER, log=quiet)
    assert not (sealed / D.FINALISTS_MD).exists()
    # a grid that is not grid.csv's (here: one RIB row fewer on BTC, and a table that counts it)
    mods2, counts2 = with_coil([], no_btc_oracle=True)
    mods2.pop("coil")
    counts2 = tuple(c for c in counts2 if c.module != "coil")
    with pytest.raises(D.GridError, match="grid.csv is not the rule modules' grid"):
        D.freeze(sealed, mods2, counts2, require_all=False, loader=STUB.LOADER, log=quiet)


def test_freeze_refuses_a_champion_whose_development_row_needs_later_bars(sealed):
    mods, counts = with_coil([("PEEK", "peek")])
    q = selected(sealed, mods, counts).set_index("vid")
    assert q.at["XAUUSDm|1H|COIL|PEEK", "champion"]
    with pytest.raises(AssertionError, match=r"look-ahead: the Development rows of XAUUSDm\|1H\|COIL\|PEEK change"):
        D.freeze(sealed, mods, counts, require_all=False, loader=STUB.LOADER, log=quiet)
    assert not (sealed / D.FINALISTS_MD).exists() and not M.frozen()
    chk = pd.read_csv(sealed / "freeze_checks.csv", keep_default_na=False).set_index("vid")
    assert not chk.at["XAUUSDm|1H|COIL|PEEK", "result"] and "net" in chk.at["XAUUSDm|1H|COIL|PEEK", "differs"]
    assert chk.at[ORACLE["XAUUSDm"], "result"]


def test_the_test_only_options_are_refused_on_the_study_folder(sealed, tmp_path, monkeypatch):
    real = tmp_path / "the_study"
    real.mkdir()
    monkeypatch.setattr(D, "REAL_STUDY_DIR", real)
    assert D.main(["run", "--rules", STUB.__file__]) == 2       # no --study-dir: the default is the study folder
    assert D.main(["freeze", "--study-dir", str(real), "--rules", STUB.__file__]) == 2
    for fn in (lambda: D.run(real, STUB.MODULES, STUB.COUNTS, loader=STUB.LOADER, log=quiet),
               lambda: D.freeze(real, STUB.MODULES, STUB.COUNTS, require_all=False, loader=STUB.LOADER, log=quiet),
               lambda: D.exam(real, STUB.MODULES, STUB.COUNTS, loader=STUB.LOADER, log=quiet),
               lambda: D.accounts(real, tmp_path / "cmp", STUB.MODULES, STUB.COUNTS, loader=STUB.LOADER, log=quiet),
               lambda: D.run(real, {"ribbon": STUB.MODULES["ribbon"]}, log=quiet)):
        with pytest.raises(D.StudyFolderError):
            fn()
    with pytest.raises(D.StudyFolderError, match="rule module 'ribbon'"):
        D.run(real, {"ribbon": STUB.MODULES["ribbon"]}, log=quiet)
    assert list(real.iterdir()) == [] and not (tmp_path / "cmp").exists()


# ───────────────────────────── exam and accounts ─────────────────────────────

def test_exam_and_accounts_refuse_before_the_freeze(sealed, tmp_path):
    qual = selected(sealed)
    with pytest.raises(M.HoldOutError, match="run `freeze` first"):
        D.exam(sealed, STUB.MODULES, STUB.COUNTS, loader=STUB.LOADER, log=quiet)
    with pytest.raises(M.HoldOutError, match="run `freeze` first"):
        D.accounts(sealed, tmp_path / "cmp", STUB.MODULES, STUB.COUNTS, loader=STUB.LOADER, log=quiet)
    with pytest.raises(M.HoldOutError):
        D.exam_base_rate(sealed, [], STUB.MODULES, qual)
    other = tmp_path / "elsewhere"
    other.mkdir()
    with pytest.raises(ValueError, match="only to the study folder the guard reads"):
        D.exam(other, STUB.MODULES, STUB.COUNTS, loader=STUB.LOADER, log=quiet)
    assert D.main(["exam", "--study-dir", str(sealed), "--rules", STUB.__file__]) == 2
    assert D.main(["accounts", "--study-dir", str(sealed), "--rules", STUB.__file__,
                   "--compare-dir", str(tmp_path / "cmp")]) == 2
    assert not (sealed / "exam.csv").exists() and not (tmp_path / "cmp").exists()
    assert not list((sealed / "run_parts").glob("exam*")) and not (sealed / "run_parts" / D.ACCJOB).exists()


def test_the_exam_and_the_accounts_take_only_the_frozen_code_and_inputs(sealed, tmp_path):
    mods, f = copied_modules(tmp_path)
    frozen(sealed, mods)
    f.write_text(f.read_text() + "\n# a change after the freeze\n")
    with pytest.raises(D.CodeChangedError, match="tradeiq2_stub_rules.py differ from the code FINALISTS.md records"):
        D.exam(sealed, mods, STUB.COUNTS, loader=STUB.LOADER, log=quiet)
    assert not (sealed / "exam.csv").exists()
    with pytest.raises(D.CodeChangedError):
        D.accounts(sealed, tmp_path / "cmp", mods, STUB.COUNTS, loader=STUB.LOADER, references=False, log=quiet)
    D.exam(sealed, mods, STUB.COUNTS, loader=STUB.LOADER, base_rate=False, allow_code_change=True, log=quiet)
    inf = pd.read_csv(sealed / "exam_info.csv", keep_default_na=False)
    assert inf.code_as_frozen.astype(str).eq("False").all() and "tradeiq2_stub_rules.py" in inf.code_changed.iloc[0]
    assert "**not** the code FINALISTS.md records (tradeiq2_stub_rules.py" in (sealed / "EXAM.md").read_text()
    # the exam of record is never overwritten by yet other code
    f.write_text(f.read_text() + "\n# and another\n")
    with pytest.raises(FileExistsError, match="the exam of record is never overwritten"):
        D.exam(sealed, mods, STUB.COUNTS, loader=STUB.LOADER, base_rate=False, allow_code_change=True, log=quiet)
    # an input FINALISTS.md was frozen from that moved
    (sealed / "CANDIDATES.md").write_text((sealed / "CANDIDATES.md").read_text() + "\n")
    with pytest.raises(D.FrozenInputsError, match="CANDIDATES.md differs"):
        D.exam(sealed, mods, STUB.COUNTS, loader=STUB.LOADER, allow_code_change=True, log=quiet)


def test_the_exam_voids_a_champion_whose_rows_change_on_the_data_to_the_data_end(sealed):
    mods, counts = with_coil([("PEEKVAL", "peek-val")], no_btc_oracle=True, loser=True)
    qual = frozen(sealed, mods, counts)
    assert qual.set_index("vid").loc[["XAUUSDm|1H|COIL|PEEKVAL", "XAUUSDm|1H|SP|LOSER"], "champion"].all()
    assert not qual[qual.symbol == M.BTC].champion.any()            # BTC has no champion here
    with pytest.raises(AssertionError, match=r"look-ahead: .*XAUUSDm\|1H\|COIL\|PEEKVAL.*void"):
        D.exam(sealed, mods, counts, loader=STUB.LOADER, log=quiet)
    ex = pd.read_csv(sealed / "exam.csv").drop_duplicates("vid").set_index("vid")
    assert ex.at["XAUUSDm|1H|COIL|PEEKVAL", "verdict"] == "void (look-ahead)"
    assert not ex.at["XAUUSDm|1H|COIL|PEEKVAL", "lookahead_ok"]
    assert ex.at[ORACLE["XAUUSDm"], "verdict"] == "passes both"
    assert ex.at["XAUUSDm|1H|SP|LOSER", "verdict"] == "fails"          # an exam can be failed
    chk = pd.read_csv(sealed / "exam_checks.csv", keep_default_na=False).set_index("vid")
    assert not chk.at["XAUUSDm|1H|COIL|PEEKVAL", "result"] and chk.at[ORACLE["XAUUSDm"], "result"]
    assert "void (look-ahead)" in (sealed / "EXAM.md").read_text()
    # buy-and-hold over the exam windows is there for every symbol, the one without a champion included
    assert set(pd.read_csv(sealed / "exam_buy_and_hold.csv").symbol) == {"XAUUSDm", "BTCUSDm"}


def test_every_variant_is_checked_for_look_ahead_after_the_freeze(sealed):
    mods, counts = with_coil([("PEEKLOSER", "peek-loser")])
    q = frozen(sealed, mods, counts).set_index("vid")
    assert not q.at["XAUUSDm|1H|COIL|PEEKLOSER", "qualifies"]       # no champion: the freeze cannot see it
    with pytest.raises(AssertionError, match=r"look-ahead: Development / Validation rows changed .*COIL\|PEEKLOSER"):
        D.exam(sealed, mods, counts, loader=STUB.LOADER, log=quiet)
    chk = pd.read_csv(sealed / "exam_checks.csv", keep_default_na=False)
    every = chk[chk.check.str.startswith("every variant's")].iloc[0]
    assert str(every.result) == "False" and every.differs == "XAUUSDm|1H|COIL|PEEKLOSER"
    assert pd.read_csv(sealed / "exam.csv").lookahead_ok.all()      # the champions themselves are fine
    assert "every variant's D, V and D+V" in (sealed / "EXAM.md").read_text()


def test_the_exam_rule_and_every_verdict():
    net = [0.0, 1e-9, 1e-9, 1.0, 1.0, -1.0, 5.0]
    pdd = [1.0, 0.5, 0.5 - 1e-9, np.nan, 0.5, 2.0, 0.4999]
    assert D.exam_rule(net, pdd).tolist() == [False, True, False, False, True, False, False]
    assert {(h, e): D.verdict_of("XAUUSDm", h, e) for h in (True, False) for e in (True, False)} == {
        (True, True): "passes both", (True, False): "passes the hold-out only", (False, True): "passes Early only",
        (False, False): "fails"}
    assert (D.verdict_of("BTCUSDm", True, None), D.verdict_of("BTCUSDm", 0, None)) == ("pass", "fail")


def _vmap():
    return {v.id: (k, v) for k, v in D.collect(STUB.MODULES)[0]}


def test_the_accounts_export_round_trips_through_the_contract(sealed, tmp_path):
    from backtesting.research import compare_page as CP
    qual = selected(sealed)
    cmp = tmp_path / "compare"
    plan = (("dev", "all", (1.0, 1.5)), ("devval", "focus", (1.0,)))
    D.accounts(sealed, cmp, STUB.MODULES, STUB.COUNTS, plan=plan, workers=2, loader=STUB.LOADER,
               require_frozen=False, references=False, log=quiet)
    assert D.check_export(cmp) == []
    assert CP.validate(cmp)["errors"] == []                     # the page's own validator (it imports no tradeiq2)
    se = pd.read_csv(cmp / "tradeiq_2027__series.csv", dtype=str, keep_default_na=False)
    me = pd.read_csv(cmp / "tradeiq_2027__metrics.csv", dtype=str, keep_default_na=False)
    cu = pd.read_csv(cmp / "tradeiq_2027__curves_dev.csv.gz", dtype={"series_id": str, "date": str})
    assert sorted(p.name for p in cmp.iterdir()) == ["tradeiq_2027__curves_dev.csv.gz",
                                                    "tradeiq_2027__curves_devval.csv.gz",
                                                    "tradeiq_2027__metrics.csv", "tradeiq_2027__series.csv"]
    g = D.read_grid(sealed)
    gb = g[g.symbol.isin(D.SYMBOLS) & ~g.vid.isin(DRAWN.values())]   # the rows that look ahead are not on the page
    assert se.series_id.tolist() == ["tradeiq_2027:" + v for v in gb.vid]
    assert list(se.columns) == list(D.SERIES_COLS) and list(me.columns) == list(D.METRIC_COLS)
    focus = set(qual[qual.champion].vid) | set(D.family_best(qual).vid)
    assert len(me) == 4 * len(gb) + 2 * len(focus)
    role = dict(zip(se.series_id.str.split(":", n=1).str[1], se.role))
    assert role[ORACLE["XAUUSDm"]] == "finalist" and role["XAUUSDm|1H|RIB|LS|X0|F0"] == "variant"
    elig = dict(zip(se.series_id.str.split(":", n=1).str[1], se.eligible))
    assert {v: elig[v] for v in gb.vid} == {v: str(int(x)) for v, x in zip(qual.vid, qual.qualifies) if v in elig}
    assert "0.02 lot" in se.set_index("series_id").at["tradeiq_2027:XAUUSDm|1H|RIB|LS|XP|F0", "notes"]
    vm = _vmap()
    for vid in (ORACLE["XAUUSDm"], ORACLE["BTCUSDm"], "BTCUSDm|M5|SH|PRESET-CUSTOM|K2|E1", "XAUUSDm|1H|RIB|LS|XP|F0",
                "XAUUSDm|M15|ORB|O5|F0", "XAUUSDm|1H|HA-MANAGED|M1|RIB-LS-X0-F0"):
        key, v = vm[vid]
        ctx = M.Context(STUB.market(v.symbol))
        a, z = M.window_span("dev", v.symbol)
        r = M.run_exec(ctx.mk, STUB.MODULES[key].build(v, ctx), a, z, 1.0)
        curve, summ = M.account_curve(r)
        m = me[(me.series_id == "tradeiq_2027:" + vid) & (me.window == "dev") & (me.cost == "1.0")].set_index("basis")
        assert float(m.at["account", "final_usd"]) == pytest.approx(summ["final"], abs=1e-4), vid
        assert float(m.at["account", "max_dd_pct"]) == pytest.approx(summ["max_dd_pct"], abs=1e-4), vid
        dd_usd = float(m.at["account", "max_dd_usd"])
        assert float(m.at["account", "p_dd"]) == pytest.approx((summ["final"] - 2000.0) / dd_usd, rel=1e-3, abs=1e-6)
        assert (m.at["unit", "start_usd"], m.at["unit", "return_pct"], m.at["unit", "max_dd_pct"]) == ("0.0", "", "")
        assert float(m.at["unit", "net_usd"]) == pytest.approx(r.net, abs=1e-4)          # dollars: 4 decimals
        assert float(m.at["unit", "max_dd_usd"]) == pytest.approx(r.max_dd, abs=1e-4)
        if summ.get("max_units") == 1.0 and len(r.lanes) == 0 and len(r.legs) == 1:
            # one unit throughout: the account's dollar drawdown is the unit run's
            assert float(m.at["account", "max_dd_usd"]) == pytest.approx(r.max_dd, abs=1e-4), vid
        # the account's weekly Sharpe is the page's: the weekly P/L in $ at the Saturday edges
        ct = (curve.time.astype("int64") // 10**9).to_numpy()
        wk = np.diff(curve.equity.to_numpy()[np.searchsorted(ct, TM._edges_weeks(r.a_s, r.z_s))])
        want = np.mean(wk) / np.std(wk, ddof=1) * np.sqrt(52.0)
        assert float(m.at["account", "sharpe_w"]) == pytest.approx(want, abs=1e-5), vid
        c = cu[cu.series_id == "tradeiq_2027:" + vid]
        days = np.unique(r.m.t[r.ia:r.iz] // 86400)
        opening = (pd.Timestamp(a) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        assert c.date.tolist() == [opening] + pd.to_datetime(days * 86400, unit="s").strftime("%Y-%m-%d").tolist()
        assert c.equity_usd.iloc[0] == 2000.0 and c.equity_usd.iloc[-1] == pytest.approx(summ["final"], abs=1e-6)
        assert np.allclose(c.equity_usd.to_numpy()[1:], curve.equity.to_numpy()[np.searchsorted(
            ct, np.minimum((days + 1) * 86400, r.z_s))], atol=1e-9)
    # a broken file is caught by the contract's check
    se.loc[0, "role"] = "hero"
    se.to_csv(cmp / "tradeiq_2027__series.csv", index=False)
    assert D.check_export(cmp) == ["series.role holds ['hero']"]
    # a second export without the dev window replaces this source's files whole: no stale curve file is left
    D.accounts(sealed, cmp, STUB.MODULES, STUB.COUNTS, plan=(("devval", "focus", (1.0,)),), loader=STUB.LOADER,
               require_frozen=False, references=False, log=quiet)
    assert sorted(p.name for p in cmp.iterdir()) == ["tradeiq_2027__curves_devval.csv.gz",
                                                    "tradeiq_2027__metrics.csv", "tradeiq_2027__series.csv"]
    assert D.check_export(cmp) == [] and CP.validate(cmp)["errors"] == []


def test_the_page_curve_opens_at_2000_and_stops_at_a_wipe_out(tmp_path):
    a = M.s_of("2020-09-07")
    t = a + np.arange(0, 5 * 86400, 3600)                       # hourly stand-ins for the M1 bars of 5 days
    r = SimpleNamespace(m=SimpleNamespace(t=t), ia=0, iz=len(t), a_s=a, z_s=a + 5 * 86400)
    curve = pd.DataFrame({"time": pd.to_datetime(TM._edges_days(a, a + 5 * 86400), unit="s", utc=True),
                          "equity": [2000.0, 2100.0, 1500.0, 0.0, 0.0, 0.0]})
    out = D.day_marks(r, curve)
    assert out.date.tolist() == ["2020-09-06", "2020-09-07", "2020-09-08", "2020-09-09", "2020-09-10", "2020-09-11"]
    assert out.equity_usd.tolist() == [2000.0, 2100.0, 1500.0, 0.0, 0.0, 0.0]
    wiped = D.day_marks(r, curve, wiped=True, wix=int(np.searchsorted(t, a + 2 * 86400 + 5 * 3600)))
    assert wiped.date.tolist() == ["2020-09-06", "2020-09-07", "2020-09-08", "2020-09-09"]
    assert wiped.equity_usd.tolist() == [2000.0, 2100.0, 1500.0, 0.0]
    # the contract's check: a wiped account's curve must stop at the wipe-out
    sid = "tradeiq_2027:XAUUSDm|1H|RIB|X"
    pd.DataFrame([{"series_id": sid, "source": D.SID, "study": D.STUDY_NAME, "symbol": "XAUUSDm", "label": "x",
                   "kind": "rule", "family": "RIB", "tf": "1H", "filter": "", "role": "variant", "eligible": 0,
                   "exam": "", "notes": "", "sizing": "", "tags": ""}],
                 columns=list(D.SERIES_COLS)).to_csv(tmp_path / f"{D.SID}__series.csv", index=False)
    row = {c: "" for c in D.METRIC_COLS}
    row.update(series_id=sid, window="dev", start="2020-09-07", end="2020-09-12", cost=1.0, basis="account",
               start_usd=2000.0, final_usd=0.0, net_usd=-2000.0, wiped=1, dd_marks="M1")
    pd.DataFrame([row], columns=list(D.METRIC_COLS)).to_csv(tmp_path / f"{D.SID}__metrics.csv", index=False)
    for curve_rows, ok in ((wiped, True), (out, False)):
        curve_rows.assign(series_id=sid)[list(D.CURVE_COLS)].to_csv(tmp_path / f"{D.SID}__curves_dev.csv.gz",
                                                                    index=False)
        problems = D.check_export(tmp_path)
        assert (problems == []) == ok, problems
    assert "does not stop at the wipe-out" in problems[0]


def test_the_exam_and_the_accounts_after_the_freeze_on_the_synthetic_markets(sealed, tmp_path, monkeypatch):
    fake_binance(monkeypatch)
    frozen(sealed)
    D.exam(sealed, STUB.MODULES, STUB.COUNTS, workers=2, loader=STUB.LOADER, log=quiet)
    ex = pd.read_csv(sealed / "exam.csv")
    assert sorted(zip(ex.vid, ex.window)) == sorted([(ORACLE["XAUUSDm"], "holdout"), (ORACLE["XAUUSDm"], "early"),
                                                     (ORACLE["BTCUSDm"], "holdout")])
    assert dict(zip(ex.vid, ex.verdict)) == {ORACLE["XAUUSDm"]: "passes both", ORACLE["BTCUSDm"]: "pass"}
    assert ex["pass"].all() and set(ex.role) == {"finalist"} and ex.lookahead_ok.all()
    assert {"bh_exposure_matched_net", "net_above_exposure_matched", "edge_over_bh"} <= set(ex.columns)
    assert ex.bh_exposure_matched_net.to_numpy() == pytest.approx((ex.time_in_mkt * ex.bh_net).to_numpy())
    chk = pd.read_csv(sealed / "exam_checks.csv", keep_default_na=False)
    assert chk.result.astype(str).eq("True").all()
    every = chk[chk.check.str.startswith("every variant's")]
    assert len(every) == 1 and "2 that look ahead by design left out" in every.check.iloc[0]
    ho, ea = D.read_results(sealed, "results_holdout.csv"), D.read_results(sealed, "results_early.csv")
    assert ho.vid.tolist() == D.read_grid(sealed).vid.tolist() and set(ho.window) == {"holdout"}
    assert set(ea.symbol) == {"XAUUSDm"} and len(ea) == STUB.N_GOLD
    rc = D.read_results(sealed, "results_recheck_dev_val.csv")
    assert len(rc) == 3 * STUB.N_VARIANTS
    br = pd.read_csv(sealed / "base_rate.csv").set_index(["symbol", "window", "rows"])
    assert br.at[("XAUUSDm", "both", "finalists"), "share"] == 1.0 and br.at[("BTCUSDm", "holdout", "champions"),
                                                                              "pass"] == 1
    assert br.at[("XAUUSDm", "holdout", "all rows"), "n"] == STUB.N_GOLD
    assert br.at[("USTECm", "holdout", "claim-check rows (information)"), "n"] == 1
    assert ("BTCUSDm", "holdout", "buy-and-hold") in br.index and ("BTCUSDm", "early", "finalists") not in br.index
    assert "passes both" in (sealed / "EXAM.md").read_text()
    mt = pd.read_csv(sealed / "multiple_testing.csv")
    assert set(mt.universe) == {"all variants run", "eligible variants"}
    plan = (("full", "focus", D.COSTS), ("holdout", "focus", D.COSTS), ("early", "focus", D.COSTS),
            ("val", "all", (1.0,)))
    D.accounts(sealed, tmp_path / "cmp", STUB.MODULES, STUB.COUNTS, plan=plan, loader=STUB.LOADER, log=quiet)
    assert D.check_export(tmp_path / "cmp") == []
    se = pd.read_csv(tmp_path / "cmp" / "tradeiq_2027__series.csv", dtype=str, keep_default_na=False)
    assert se.set_index("series_id").at["tradeiq_2027:" + ORACLE["XAUUSDm"], "exam"] == "pass"
    assert "passes both" in se.set_index("series_id").at["tradeiq_2027:" + ORACLE["XAUUSDm"], "notes"]
    assert not se.series_id.str.contains("HP-DRAWN").any()
    me = pd.read_csv(tmp_path / "cmp" / "tradeiq_2027__metrics.csv", dtype=str, keep_default_na=False)
    assert set(me[me.series_id == "tradeiq_2027:" + ORACLE["BTCUSDm"]].window) == {"full", "holdout", "val"}
    for w in ("full", "holdout", "early"):
        assert (sealed / f"curves_{w}.csv").exists()
    assert set(pd.read_csv(sealed / "curves_early.csv").symbol) == {"XAUUSDm"}
    # next to the accounts (PREREG 7): buy-and-hold and study 1's six finalists, run with study 1's code
    cs = pd.read_csv(sealed / "curves_summary.csv")
    refs = cs[cs.source != "this study"]
    assert set(refs.source) == {D.REF_BH, D.REF_S1}                 # the bots: no rebuild on synthetic spans
    s1 = D.study1_finalists()
    assert sorted(set(refs[refs.source == D.REF_S1].vid)) == sorted(s1) and len(s1) == 6
    assert set(refs[(refs.symbol == M.GOLD)].window) == {"full", "holdout", "early"}
    assert set(refs[(refs.symbol == M.BTC)].window) == {"full", "holdout"}
    bh = refs[(refs.source == D.REF_BH) & (refs.symbol == M.GOLD) & (refs.window == "holdout")].iloc[0]
    hb = pd.read_csv(sealed / "exam_buy_and_hold.csv").query("symbol == 'XAUUSDm' and window == 'holdout' and "
                                                             "cost == 1.0").iloc[0]
    assert bh.unit_net_usd == pytest.approx(hb.bh_net) and bh.account_final_usd == pytest.approx(2000.0 + hb.bh_net)
    assert set(pd.read_csv(sealed / "curves_holdout.csv").vid) >= set(s1) | {"XAUUSDm|buy-and-hold"}
    # the claims add the hold-out's evidence, for information, once it exists
    D.claims(sealed, STUB.MODULES, partial=True, loader=STUB.LOADER, log=quiet)
    ho_claims = pd.read_csv(sealed / "claims_holdout.csv")
    assert sorted(set(ho_claims.claim)) == list(range(1, 21))
    assert "Hold-out (information)" in (sealed / "CLAIMS.md").read_text()
    D.report(sealed, STUB.MODULES, log=quiet)
    assert "passes both" in (sealed / "RESULTS_TABLES.md").read_text()


# ───────────────────────────── claims, report, the command line ─────────────────────────────

def test_claims_and_report_run_on_the_stub_grid_and_name_what_they_miss(sealed):
    assert D.main(["run", "--study-dir", str(sealed), "--rules", STUB.__file__, "--workers", "1"]) == 0
    assert D.main(["select", "--study-dir", str(sealed), "--rules", STUB.__file__]) == 0
    cl = D.claims(sealed, STUB.MODULES, partial=True, loader=STUB.LOADER, log=quiet)
    assert sorted(set(cl.claim)) == list(range(1, 21))
    assert set(cl.verdict) <= {"holds", "does not hold", "mixed", "cannot be tested", "not computed", "information"}
    notes = " ".join(cl[cl.verdict == "not computed"].note)
    assert "tradeiq2_rules_orb has none of claim6, claim_6" in notes
    assert "tradeiq2_rules_swing (not found) has none of claim11" in notes
    assert (cl[cl.claim == 20].verdict == "cannot be tested").any()
    c13 = cl[cl.claim == 13]
    assert (c13.verdict != "not computed").all()                         # the MSD-F4 stub and study 1's rows
    assert c13.part.str.contains("their number and net").sum() == 4      # 2 kinds x 2 symbols
    assert c13[c13.part.str.contains("their number and net")].dev.str.contains(" trades, net ").all()
    assert "## Not computed yet" in (sealed / "CLAIMS.md").read_text()
    ev = D.Evidence(sealed, D.read_results(sealed).query("window != 'devval'"), D.read_grid(sealed),
                    pd.read_csv(sealed / "qualification.csv"), STUB.MODULES)
    with pytest.raises(D.MissingExtra, match="claim 6: tradeiq2_rules_orb has none of claim6"):
        D.claims_table(ev, numbers=[6])
    rep = D.report(sealed, STUB.MODULES, log=quiet)
    assert len(rep["vs_study1_msd"]) == 2 * 2 * 3 and set(rep["vs_study1_msd"].study1_filter) == {"F0", "F1", "F2-1D"}
    assert set(rep["vs_study1_msd"].kind) == {"MSD-F4", "MSD-F6"}
    assert set(rep["vs_f0"].vid) == {"XAUUSDm|1H|RIB|LS|X0|F1", "BTCUSDm|1H|RIB|LS|X0|F1"}
    assert rep["vs_f0"].f0_vid.str.endswith("|LS|X0|F0").all()
    assert dict(zip(rep["combos"].vid, rep["combos"].base_vid)) == {
        f"{s}|1H|STK|STK-RM|LS|S1": f"{s}|1H|RIB|LS|X0|F0" for s in M.SYMBOLS} and rep["combos_unmatched"].empty
    b = rep["vs_study1_best"].set_index(["symbol", "family"])
    assert b.at[("XAUUSDm", "RIB"), "study1_vid"].startswith("XAUUSDm|1H|")
    assert b.at[("XAUUSDm", "SH"), "study1_vid"] == "none"                 # study 1 has no M5 rows
    assert (sealed / "RESULTS_TABLES.md").exists()


def test_claim_functions_count_only_inside_the_evidence_windows(sealed):
    selected(sealed)
    ev = D.Evidence(sealed, D.read_results(sealed).query("window != 'devval'"), D.read_grid(sealed),
                    pd.read_csv(sealed / "qualification.csv"), STUB.MODULES, loader=STUB.LOADER)
    assert ev.span("dev", M.GOLD) == WINDOWS["dev"] and ev.span("val", M.BTC) == WINDOWS["val"]
    m = ev.in_window(M.GOLD, "1H", "val")
    b = ev.context(M.GOLD).bars("1H")
    assert m.any() and int(ev.context(M.GOLD).mk.end_s) == M.CUT_S
    assert (b.t[m] >= M.s_of(WINDOWS["val"][0])).all() and (b.tc[m] <= M.s_of(WINDOWS["val"][1])).all()
    assert ev.years(M.GOLD) == [("dev", 2020, "2020-09-07", "2020-10-05"), ("val", 2020, "2020-10-05", "2020-10-12")]
    ev.check_rows([{"part": "x", "symbol": M.GOLD, "year": 2020, "start": "2020-09-07", "end": "2020-10-12"}], "t")
    for row, word in (({"year": 2019}, "year 2019"), ({"start": "2020-08-24"}, "start 2020-08-24"),
                      ({"end": "2020-10-20"}, "end 2020-10-20")):
        with pytest.raises(D.ClaimWindowError, match=word):
            ev.check_rows([{"part": "x", "symbol": M.GOLD, **row}], "t")
    # through the registry: a claim function that counts gold's (synthetic) Early window is refused, not skipped
    orb = STUB.MODULES["orb"]
    mods = dict(STUB.MODULES, orb=SimpleNamespace(**{**vars(orb), "claim6": lambda e: [
        {"part": "the range sets the day", "symbol": M.GOLD, "start": WINDOWS["early"][0], "dev": "", "val": "",
         "dev_ok": True, "val_ok": True}]}))
    ev2 = D.Evidence(sealed, ev.res, ev.grid, ev.qual, mods, loader=STUB.LOADER)
    with pytest.raises(D.ClaimWindowError, match="tradeiq2_rules_orb|orb.claim6"):
        D.claims_table(ev2, numbers=[6], partial=True)


def test_evidence_trades_without_ids_gives_every_variant_of_the_window(sealed):
    """``Evidence.trades(window)`` (no ids) is every variant's trades of that window at the cost, as a claim extra
    calls it (``tradeiq2_rules_wyckoff.claim16`` picks its own rows); with ids, only theirs."""
    selected(sealed)
    ev = D.Evidence(sealed, D.read_results(sealed).query("window != 'devval'"), D.read_grid(sealed),
                    pd.read_csv(sealed / "qualification.csv"), STUB.MODULES, loader=STUB.LOADER)
    allt = pd.read_csv(sealed / "trades_dev_val.csv.gz", float_precision="round_trip")
    for w in ("dev", "val"):
        want = allt[(allt.window == w) & (allt.cost == 1.0)].reset_index(drop=True)
        got = ev.trades(w)
        assert len(want) > 0 and got.reset_index(drop=True).equals(want), w
        some = sorted(set(want.vid))[:2]
        assert set(ev.trades(w, some).vid) == set(some)
        x15 = ev.trades(w, cost=1.5)
        assert len(x15) and (x15.cost == 1.5).all() and set(x15.vid) <= set(allt.vid)


def test_the_filters_and_our_combinations_pair_by_the_prereg_names():
    G = "XAUUSDm|"
    specs = [{"vid": G + "1H|SP|W1|F0", "family": "SP"}, {"vid": G + "1H|SP|W1|FD", "family": "SP"},
             {"vid": G + "1H|SP|W1|LO", "family": "SP"},
             {"vid": G + "M5|ORB|O1|F0", "family": "ORB", "tf": "M5"},
             {"vid": G + "M5|ORB|O1|HV", "family": "ORB", "tf": "M5"},
             {"vid": G + "M5|ORB|O1|HV+F2-4H", "family": "ORB", "tf": "M5"},
             {"vid": G + "M5|ORB|O1|TIGHT", "family": "ORB", "tf": "M5"},
             {"vid": G + "M5|ORB|ORB-CX|O1|F0", "family": "ORB", "tf": "M5"},
             {"vid": G + "M5|SH|AS|K2|E1", "family": "SH", "tf": "M5"},
             {"vid": G + "M5|SH|AS|K2|E1|F2-4H", "family": "SH", "tf": "M5"},
             {"vid": G + "1H|RIB|LO|X0|F0"}, {"vid": G + "1H|RIB|LO|X0|F1"}, {"vid": G + "1H|RIB|LS|X0|F0"},
             {"vid": G + "1H|STK|STK-RM|LS|S1", "family": "STK"},
             {"vid": G + "1D|WY|WY-STD|X-S|F0", "family": "WY", "tf": "1D"},
             {"vid": G + "1D|WY|WY-STD|X-S3|F0", "family": "WY", "tf": "1D"},
             {"vid": G + "1D|WY-DERIVED|WY-CL|F0", "family": "WY-DERIVED", "tf": "1D"},
             {"vid": G + "1D|WY-DERIVED|WY-SP|F1", "family": "WY-DERIVED", "tf": "1D"}]
    res = results_table(specs)
    vf, un = D.vs_f0(res)
    pairs = dict(zip(vf.vid, vf.f0_vid))
    assert pairs == {G + "1H|SP|W1|FD": G + "1H|SP|W1|F0", G + "1H|SP|W1|LO": G + "1H|SP|W1|F0",
                     G + "M5|ORB|O1|HV": G + "M5|ORB|O1|F0", G + "M5|ORB|O1|HV+F2-4H": G + "M5|ORB|O1|F0",
                     G + "M5|SH|AS|K2|E1|F2-4H": G + "M5|SH|AS|K2|E1", G + "1H|RIB|LO|X0|F1": G + "1H|RIB|LO|X0|F0"}
    assert vf.set_index("vid").at[G + "M5|SH|AS|K2|E1|F2-4H", "against"] == "the row without the filter token"
    assert un == [G + "1D|WY-DERIVED|WY-SP|F1"]                      # no F0 row, no row without the token
    assert G + "1H|RIB|LO|X0|F0" not in pairs                         # on RIB, LO is the side, not a filter
    cb, cun = D.combos_table(res)
    assert dict(zip(cb.vid, cb.base_vid)) == {
        G + "M5|ORB|O1|TIGHT": G + "M5|ORB|O1|F0", G + "M5|ORB|ORB-CX|O1|F0": G + "M5|ORB|O1|F0",
        G + "1H|STK|STK-RM|LS|S1": G + "1H|RIB|LS|X0|F0", G + "1D|WY-DERIVED|WY-CL|F0": G + "1D|WY|WY-STD|X-S|F0"}
    assert cun == [G + "1D|WY-DERIVED|WY-SP|F1"]
    s = D._summary(cb, (("symbol", "combination"),))
    assert set(s.combination) == set(D.COMBO_NAMES.values()) and (s.n == 1).all()


def test_claim_17_counts_the_scripts_wyckoff_rows_only():
    specs = [{"vid": f"XAUUSDm|{tf}|WY|WY-STD|X-S|F0", "family": "WY", "tf": tf, "dev": {"net": n},
              "val": {"net": n}} for tf, n in (("1H", -1.0), ("4H", 5.0), ("1D", 5.0))]
    specs += [{"vid": f"XAUUSDm|{tf}|WY-DERIVED|WY-CL|F0", "family": "WY-DERIVED", "tf": tf, "dev": {"net": n},
               "val": {"net": n}} for tf, n in (("1H", 9.0), ("4H", -9.0), ("1D", -9.0))]
    res = results_table(specs).assign(n_candidates=7)
    grid = pd.DataFrame({"vid": res.vid.unique(), "params": "{}"})
    ev = D.Evidence(Path("."), res[res.window != "devval"], grid, D.qualification(res), {})
    rows = D.CLAIMS[17][1](ev)
    assert rows[0]["dev"] == "1H 0%, 4H 100%, 1D 100%" and rows[0]["dev_ok"] and rows[0]["val_ok"]
    assert rows[1]["verdict"] == "information" and rows[1]["dev"] == "1H 40 (7), 4H 40 (7), 1D 40 (7)"


def test_the_pairing_of_msd_rows_with_study_1_and_the_token_swaps():
    v = M.Variant("BTCUSDm|1H|MSD-FILTER|MSD-F6|VWRSI|R2|S1", "BTCUSDm", "1H", "MSD", "MSD-FILTER")
    assert D.study1_pairs(v, {}) == {F: f"BTCUSDm|1H|VWRSI-RV|R2|{F}|S1" for F in ("F0", "F1", "F2-4H", "F2-1D")}
    v = M.Variant("XAUUSDm|1D|MSD-FILTER|MSD-F4|S0", "XAUUSDm", "1D", "MSD", "MSD-FILTER", params={"base": "TSI",
                                                                                                    "rule": "R1"})
    assert D.study1_pairs(v, {}) == {"F0": "XAUUSDm|1D|TSI|R1|F0|S0", "F1": "XAUUSDm|1D|TSI|R1|F1|S0"}
    with pytest.raises(D.ClaimError, match="cannot read its study-1 base"):
        D.study1_pairs(M.Variant("XAUUSDm|1D|MSD-FILTER|MSD-F4", "XAUUSDm", "1D", "MSD", "MSD-FILTER"), {})
    with pytest.raises(D.ClaimError, match="not in study 1's results"):
        D.study1_pairs(M.Variant("XAUUSDm|1D|MSD-FILTER|RSI|R1|S0", "XAUUSDm", "1D", "MSD", "MSD-FILTER"), {},
                       s1_ids={"XAUUSDm|1D|RSI|R1|F0|S0"})
    assert D.swap("XAUUSDm|1H|RIB|LS|XP|F2-4H", "XP", "X0") == "XAUUSDm|1H|RIB|LS|X0|F2-4H"
    assert D.swap("XAUUSDm|4H|COIL|RIB|X-TR|BIG", "BIG", None) == "XAUUSDm|4H|COIL|RIB|X-TR"
    assert D.swap("XAUUSDm|1H|RIB|LS|X0|F0", "XP", "X0") is None
    assert D.setting("a|1H|RIB|LS|X0|FR", "{}", D.FILTER_KEYS, D.FILTER_TOKENS) == "FR"
    assert D.setting("a|1H|RIB|LS|X0|FR", {"filter": "F2-4H"}, D.FILTER_KEYS, D.FILTER_TOKENS) == "F2-4H"
    assert D.span("8y", "XAUUSDm") == ("2018-11-13", "2026-11-13")
    with pytest.raises(ValueError, match="gold's only"):
        D.span("8y", "BTCUSDm")
    assert D.one_line("a\n```text\nb`c`\t d") == "a '''text b'c' d"
