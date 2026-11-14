"""
Parameter optimiser whose first concern is generalisation.

    python -m backtesting optimise --space ladder --symbol XAUUSDm               # search on the development period
    python -m backtesting optimise --space ladder --symbol XAUUSDm --report-only # rebuild the report, run nothing
    python -m backtesting optimise --space ladder --symbol XAUUSDm \
        --start 2024-01-01 --holdout-to 2025-07-01                               # confirm on months never used to choose
    python -m backtesting optimise --space ladder --symbol XAUUSDm --validate    # short list on raw ticks, real account

It makes it easy to try many settings "just by changing parameters" and hard to be fooled by the
best of them. Full guide: ``backtesting/OPTIMISER.md``.

How it works
------------
* A **search space** is a JSON file (``backtesting/spaces/*.json``): fixed overrides on top of the
  live settings (``base``), the parameters to vary (a list of values or a numeric range each),
  ``conditions`` that switch off parameters which cannot matter, ``constraints`` every setting has
  to meet, and named ``references`` (the live settings are always one of them). Any field of
  ``BacktestConfig`` can be a parameter; nothing here knows the fields by name.
* **Samplers**, reproducible from a seed: the full grid, a stratified random sample, and local
  refinement (one parameter moved to a neighbouring value around the best settings so far).
* **Evaluation.** The period is cut into consecutive blocks (three months by default) and every
  block into months. A setting is run once per block on the per-second series with one fixed
  0.01-lot unit on a balance too large to stop out, exactly as the sweeps do; what is kept is the
  net P/L of every month (by basket close time), the baskets, the worst basket and what the same
  baskets would have done to a real account with the bot's unit rule. Every result is appended to
  ``evaluations.jsonl`` as it arrives, so an interrupted run continues where it stopped.
* **Choosing** uses the selection months only. The default objective is ``lcb``: the mean monthly
  net minus one standard error, which prefers a setting that is positive month after month to one
  with a single lucky month. Settings that wipe the replayed account, or dip too deep, are not eligible.
* **Diagnostics**, all computed from the stored month-by-setting matrix: hold-out months that play
  no part in choosing; a walk-forward (choose on the past, score the next block); the probability
  of backtest overfitting by combinatorially symmetric cross-validation; a haircut for the number
  of settings tried; and stability (averages per parameter value, and the neighbours of each top setting).
* **Validation** of the short list on raw ticks under eight random loop timings per block, on the
  real account with the live unit rule.

Which data to use
-----------------
``DEV`` (the default period) is where settings are developed and chosen. ``CONFIRM`` is used once,
as a hold-out, for what was fixed on ``DEV``. A period that starts before ``RESERVED_BEFORE`` is
refused unless ``--allow-reserved`` is given: that history is kept for one final test of one
frozen setting. (Its last weeks are still read as indicator warm-up of a period that starts on
``RESERVED_BEFORE``; no result comes from them.)
"""

from __future__ import annotations

import ast
import gc
import hashlib
import itertools
import json
import math
import os
import re
import shlex
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

from .config import BacktestConfig, REPO_ROOT, SYMBOLS, TF_SECONDS

# ── the data protocol (see the module docstring) ──
DEV = ("2025-07-01", "2026-11-13")          # develop, explore and choose here
CONFIRM = ("2024-01-01", "2025-07-01")      # only to confirm what was fixed on DEV (use it as the hold-out)
RESERVED_BEFORE = "2024-01-01"              # earlier history is kept for one final test

SPACES_DIR = Path(__file__).resolve().parent / "spaces"
RESULTS_DIR = REPO_ROOT / "backtest_results" / "optimise"

OBJECTIVES = ("lcb", "mean", "median", "sharpe", "worst_block")
# A month counts in the statistics when at least this share of it lies inside its block; shorter
# pieces (the days after the last full month of a period) are shown in monthly.csv and used nowhere.
MIN_COVERAGE = 0.5
ENUM_LIMIT = 200_000                        # a space with more raw combinations than this is sampled, never enumerated
STORE_FORMAT = 1                            # version of the rows in evaluations.jsonl
# fields the optimiser sets itself: the period, and the sizing every setting is measured at
RESERVED_FIELDS = ("symbol", "variant", "start", "end", "initial_balance", "fixed_units")

# What the report calls convincing. They only word the summary; every number is printed next to them.
P_LUCK_MAX = 0.10       # chance that a search without any edge does as well as the best setting
PBO_MAX = 0.25          # share of half / half splits in which the best of one half is below the median of the other
PLATEAU_MIN = 0.5       # neighbours' average objective as a share of the setting's own
MIN_BASKETS = 100       # fewer closed baskets than this in the selection months is a small sample

Canon = Tuple[Optional[int], ...]           # one value index per parameter; None = switched off by a condition


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ───────────────────────────── blocks and months ─────────────────────────────

_SPAN = re.compile(r"^\s*(\d+)\s*(min|minutes?|h|hours?|d|days?|w|weeks?|mo|months?)\s*$", re.IGNORECASE)
_MINUTES = {"min": 1, "h": 60, "d": 1440, "w": 10080}


def parse_span(text) -> Tuple[str, int]:
    """'3mo' -> ('month', 3); '2w', '10d', '6h', '20min' -> ('minute', n). Months are calendar months."""
    m = _SPAN.match(str(text))
    if not m or int(m.group(1)) <= 0:
        raise ValueError(f"cannot read the length {text!r}: write it like 3mo, 1mo, 2w, 10d, 6h or 20min")
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit.startswith("mo"):
        return ("month", n)
    return ("minute", n * _MINUTES["min" if unit.startswith("min") else unit[0]])


def _ts(x) -> pd.Timestamp:
    """A UTC time without a timezone attached (the store's times are UTC)."""
    t = pd.Timestamp(x)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo is not None else t


def _shift(t: pd.Timestamp, span: Tuple[str, int], k: int) -> pd.Timestamp:
    unit, n = span
    return t + pd.DateOffset(months=n * k) if unit == "month" else t + pd.Timedelta(minutes=n * k)


def _when(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%d") if t == t.normalize() else t.strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class Month:
    """One slice of a block: a calendar month by default."""
    label: str
    start: pd.Timestamp
    end: pd.Timestamp
    block: int
    coverage: float         # share of the nominal slice that lies inside the block

    @property
    def full(self) -> bool:
        return self.coverage >= MIN_COVERAGE


@dataclass(frozen=True)
class Block:
    """One consecutive piece of the period; every setting is run once on each."""
    index: int
    start: pd.Timestamp
    end: pd.Timestamp
    months: Tuple[int, ...]         # positions in ``Period.months``
    id: str                         # what a stored result is matched on: start, end and how it was sliced

    @property
    def label(self) -> str:
        return f"{_when(self.start)} → {_when(self.end)}"

    @property
    def window(self) -> Tuple[str, str]:
        return (self.start.strftime("%Y-%m-%d %H:%M:%S"), self.end.strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class Period:
    start: pd.Timestamp
    end: pd.Timestamp
    block_span: Tuple[str, int]
    slice_span: Tuple[str, int]
    blocks: List[Block]
    months: List[Month]

    @property
    def unit(self) -> str:
        """What one column of the monthly matrix is called in the report."""
        return "month" if self.slice_span == ("month", 1) else "slice"

    def edges_ms(self, block: Block) -> List[int]:
        from .data import store
        ms = [store.to_ms(self.months[i].start) for i in block.months]
        return ms + [store.to_ms(block.end)]


def make_period(start, end, block: str = "3mo", slice_: str = "1mo") -> Period:
    """
    Cut [start, end) into consecutive blocks of length ``block`` and every block into slices of
    length ``slice_`` (months). Both are counted from the start date, so a period that begins on
    the first of a month gets calendar quarters and calendar months. The last block, and the last
    month of a block, are cut short where the period ends.
    """
    a, z = _ts(start), _ts(end)
    if not a < z:
        raise ValueError(f"the period must end after it starts ({a} .. {z})")
    bs, ss = parse_span(block), parse_span(slice_)
    blocks: List[Block] = []
    months: List[Month] = []
    k = 0
    while _shift(a, bs, k) < z:
        b0, b1 = _shift(a, bs, k), min(_shift(a, bs, k + 1), z)
        mine, j = [], 0
        while _shift(b0, ss, j) < b1:
            m0, nominal = _shift(b0, ss, j), _shift(b0, ss, j + 1)
            m1 = min(nominal, b1)
            label = m0.strftime("%Y-%m") if ss == ("month", 1) and m0.day == 1 and m0 == m0.normalize() else _when(m0)
            mine.append(len(months))
            months.append(Month(label, m0, m1, k, float((m1 - m0) / (nominal - m0))))
            j += 1
        blocks.append(Block(k, b0, b1, tuple(mine), f"{b0:%Y-%m-%dT%H:%M}/{b1:%Y-%m-%dT%H:%M}/{ss[0]}{ss[1]}"))
        k += 1
    return Period(a, z, bs, ss, blocks, months)


def holdout_mask(period: Period, holdout_from=None, holdout_to=None) -> np.ndarray:
    """
    Per block: True when it is held out. The hold-out runs from ``holdout_from`` (default: the start
    of the period) to ``holdout_to`` (default: its end) and has to begin and end where a block does,
    so that no block is half chosen-on and half held-out.
    """
    n = len(period.blocks)
    if holdout_from is None and holdout_to is None:
        return np.zeros(n, bool)
    lo = _ts(holdout_from) if holdout_from is not None else period.start
    hi = _ts(holdout_to) if holdout_to is not None else period.end
    edges = [b.start for b in period.blocks] + [period.end]
    for name, t in (("--holdout-from", lo), ("--holdout-to", hi)):
        if t not in edges:
            raise ValueError(f"{name} {_when(t)} is not where a block starts or ends; the blocks of this period "
                             f"change on {', '.join(_when(e) for e in edges)}")
    mask = np.array([lo <= b.start and b.end <= hi for b in period.blocks])
    if not mask.any():
        raise ValueError("the hold-out contains no block")
    if mask.all():
        raise ValueError("the hold-out covers the whole period: nothing is left to choose on")
    return mask


# ───────────────────────────── the search space ─────────────────────────────

class SpaceError(ValueError):
    """Something in a search-space file cannot be used; the message says what and where."""


def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def _compact(v) -> str:
    return json.dumps(v, separators=(",", ":"), sort_keys=True, default=str)


def _same(a, b) -> bool:
    """Equality that keeps True apart from 1 (JSON has both)."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


_FIELD_TYPES: Dict[str, str] = {f.name: str(f.type) for f in fields(BacktestConfig)}


def _coerce(name: str, value):
    """
    A number in the type its configuration field has, so that 20 and 20.0 (JSON keeps them apart)
    are one setting and not two.
    """
    t = _FIELD_TYPES.get(name, "")
    plain = "List" not in t and "Dict" not in t
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and plain and "float" in t:
        return float(value)
    if isinstance(value, int) and t == "bool" and value in (0, 1):
        return bool(value)
    if isinstance(value, float) and t == "int" and value.is_integer():
        return int(value)
    if isinstance(value, list) and "List[float]" in t:
        return [float(x) for x in value]
    return value


def config_key(cfg: BacktestConfig) -> str:
    """
    Short hash of everything in a configuration except its period: the identity of a setting.
    (It starts with a letter so that no spreadsheet or CSV reader takes it for a number.)
    """
    def plain(v):
        """Every number as a float, so that 1 and 1.0 (the same configuration) are the same setting."""
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        if isinstance(v, dict):
            return {str(k): plain(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [plain(x) for x in v]
        return v

    d = cfg.to_dict()
    d.pop("start", None)
    d.pop("end", None)
    return "s" + hashlib.sha1(json.dumps(plain(d), sort_keys=True, default=str).encode()).hexdigest()[:11]


class Expr:
    """
    A condition or a constraint: a small expression over parameter names, for example
    ``max_adds == 0`` or ``target_usd_per_unit <= 2 * stop_loss_usd_per_unit``.

    Allowed: names of configuration fields, numbers, strings, ``None`` / ``null``, ``true`` /
    ``false``, comparisons (``== != < <= > >= in not in is``), ``and or not``, ``+ - * / // %``,
    lists, ``a if c else b`` and the functions ``abs min max len``. A parameter whose values are
    lists or dicts is compared by the label of the value.
    """
    _NODES = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.BinOp,
              ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Compare, ast.Eq, ast.NotEq, ast.Lt,
              ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.Name, ast.Load, ast.Constant,
              ast.Tuple, ast.List, ast.Call, ast.IfExp)
    _CALLS = {"abs": abs, "min": min, "max": max, "len": len}
    _WORDS = {"null": None, "none": None, "true": True, "false": False}

    def __init__(self, text, names: Iterable[str], where: str):
        self.text, self.where = str(text).strip(), where
        try:
            tree = ast.parse(self.text, mode="eval")
        except SyntaxError as e:
            raise SpaceError(f"{where}: cannot read {self.text!r} ({e.msg})") from None
        used: Set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, self._NODES):
                raise SpaceError(f"{where}: {type(node).__name__} is not allowed in {self.text!r}")
            if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in self._CALLS
                                               or node.keywords):
                raise SpaceError(f"{where}: only {', '.join(self._CALLS)} can be called in {self.text!r}")
            if isinstance(node, ast.Name):
                used.add(node.id)
        self.names = used - set(self._CALLS) - set(self._WORDS)
        unknown = sorted(self.names - set(names))
        if unknown:
            raise SpaceError(f"{where}: {', '.join(unknown)} in {self.text!r} is not a field of BacktestConfig")
        self._code = compile(tree, "<search space>", "eval")

    def __call__(self, env: Dict[str, Any]) -> bool:
        try:
            return bool(eval(self._code, {"__builtins__": {}}, {**self._CALLS, **self._WORDS, **env}))
        except Exception as e:
            seen = ", ".join(f"{n}={env.get(n)!r}" for n in sorted(self.names))
            raise SpaceError(f"{self.where}: {self.text!r} cannot be worked out with {seen} "
                             f"({type(e).__name__}: {e})") from None


@dataclass
class Param:
    """One parameter of a space: an ordered list of values to choose from."""
    name: str
    values: List[Any]           # as written in the file (price-scaled parameters: before scaling)
    labels: List[Any]           # what tables and expressions show: the value, or the name / compact JSON of a list or dict
    config: List[Any]           # the value handed to BacktestConfig (scaled, in the field's type)
    price: bool = False
    ordered: bool = True        # neighbours are the values next to it; otherwise every other value is one

    def index(self, label) -> Optional[int]:
        for i, (lab, val) in enumerate(zip(self.labels, self.values)):
            if _same(lab, label) or (not _is_scalar(label) and val == label):
                return i
        return None


@dataclass
class Condition:
    when: Expr
    fix: Dict[int, int]         # parameter position -> value index it is set to
    ignore: List[int]           # parameter positions that cannot matter (left at the base configuration)


def _range_values(name: str, spec: dict) -> list:
    try:
        lo, hi = spec["range"]
    except (TypeError, ValueError):
        raise SpaceError(f"parameter {name}: \"range\" is [lowest, highest]") from None
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (lo, hi)) or hi < lo:
        raise SpaceError(f"parameter {name}: \"range\" is [lowest, highest], two numbers")
    if spec.get("log"):
        n = int(spec.get("n", 0))
        if n < 2 or lo <= 0:
            raise SpaceError(f"parameter {name}: a log range needs \"n\" (2 or more values) and a lowest value above 0")
        digits = int(spec.get("digits", 3))
        vals = [float(f"{lo * (hi / lo) ** (i / (n - 1)):.{digits}g}") for i in range(n)]
    elif "step" in spec:
        step = spec["step"]
        if not isinstance(step, (int, float)) or isinstance(step, bool) or step <= 0:
            raise SpaceError(f"parameter {name}: \"step\" must be a number above 0")
        vals = [round(lo + i * step, 10) for i in range(int(math.floor((hi - lo) / step + 1e-9)) + 1)]
    elif "n" in spec:
        n = int(spec["n"])
        if n < 2:
            raise SpaceError(f"parameter {name}: \"n\" must be 2 or more")
        vals = [round(lo + (hi - lo) * i / (n - 1), 10) for i in range(n)]
    else:
        raise SpaceError(f"parameter {name}: a range needs \"step\", or \"n\" (with \"log\": true for a log scale)")
    whole = all(isinstance(x, int) for x in (lo, hi, spec.get("step", 0))) and not spec.get("log") and "n" not in spec
    if spec.get("int", whole):
        vals = [int(round(v)) for v in vals]
    out: list = []
    for v in vals:
        if v not in out:
            out.append(v)
    return out


class Space:
    """
    A search space bound to the live settings it varies.

    ``live`` is the configuration every setting starts from (the optimiser passes the live
    settings of the symbol at one fixed unit); without it the defaults of ``BacktestConfig``
    stand in, which is enough to read, check and sample a space.
    """

    KEYS = ("name", "description", "base", "parameters", "conditions", "constraints", "references", "price_units")

    def __init__(self, spec: dict, live: Optional[BacktestConfig] = None, name: Optional[str] = None):
        if not isinstance(spec, dict):
            raise SpaceError("a search space is a JSON object")
        extra = sorted(set(spec) - set(self.KEYS))
        if extra:
            raise SpaceError(f"unknown key(s) in the search space: {', '.join(extra)} (known: {', '.join(self.KEYS)})")
        self.name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(spec.get("name") or name or "space"))
        self.description = str(spec.get("description") or "")
        self.live = live if live is not None else BacktestConfig()
        # the price move worth 1 USD on one unit: gold 1, BTC 100
        self.px = 1.0 / (self.live.mtqty * self.live.spec.contract_size)
        params = spec.get("parameters") or {}
        if not isinstance(params, dict):
            raise SpaceError("\"parameters\" maps a parameter name to its values")
        self.price_fields: Set[str] = set(spec.get("price_units") or []) | {
            n for n, p in params.items() if isinstance(p, dict) and p.get("scale") == "price"}
        self.base: Dict[str, Any] = dict(spec.get("base") or {})
        refs = spec.get("references") or {}
        self._check_names("base", self.base)
        self._check_names("parameters", params)
        self._check_names("price_units", self.price_fields)
        for rname, ov in refs.items():
            if not isinstance(ov, dict):
                raise SpaceError(f"reference {rname}: give the overrides on top of the live settings as an object")
            self._check_names(f"reference {rname}", ov)
        both = sorted(set(self.base) & set(params))
        if both:
            raise SpaceError(f"{', '.join(both)}: in \"base\" and in \"parameters\"; a field is fixed or varied, not both")
        self.base_overrides = {k: self._to_config(k, v) for k, v in self.base.items()}
        self.base_cfg = self._replace(self.live, self.base_overrides, "base")
        self.params: List[Param] = [self._param(n, p) for n, p in params.items()]
        self._pos = {p.name: j for j, p in enumerate(self.params)}
        # where a parameter starts from when a condition has switched it off: the value the base
        # configuration has if that is one of its values, otherwise the first one listed
        self.anchor: List[int] = []
        self._base_env: Dict[str, Any] = {}
        for f in fields(BacktestConfig):
            v = getattr(self.base_cfg, f.name)
            if f.name in self.price_fields and isinstance(v, (int, float)) and not isinstance(v, bool):
                v = v / self.px
            self._base_env[f.name] = v
        for p in self.params:
            at = getattr(self.base_cfg, p.name)
            hit = [i for i, c in enumerate(p.config) if getattr(self._replace(self.base_cfg, {p.name: c}, p.name), p.name) == at]
            self.anchor.append(hit[0] if hit else 0)
        names = set(_FIELD_TYPES)
        self.conditions: List[Condition] = []
        for k, c in enumerate(spec.get("conditions") or [], 1):
            where = f"condition {k}"
            if (not isinstance(c, dict) or "when" not in c or set(c) - {"when", "fix", "ignore", "note"}
                    or not (c.get("fix") or c.get("ignore"))):
                raise SpaceError(f"{where}: write {{\"when\": \"...\", \"ignore\": [names]}} and / or \"fix\": {{name: value}}")
            fix: Dict[int, int] = {}
            for pname, label in (c.get("fix") or {}).items():
                j = self._position(pname, where)
                i = self.params[j].index(label)
                if i is None:
                    raise SpaceError(f"{where}: {label!r} is not one of the values of {pname}")
                fix[j] = i
            ignore = [self._position(n, where) for n in (c.get("ignore") or [])]
            self.conditions.append(Condition(Expr(c["when"], names, where), fix, ignore))
        self.constraints: List[Expr] = [Expr(t, names, f"constraint {k}") for k, t in enumerate(spec.get("constraints") or [], 1)]
        # named settings to compare with: overrides on top of the LIVE settings (not of "base")
        self.references: Dict[str, Dict[str, Any]] = {"live": {}}
        for rname, ov in refs.items():
            cfg_ov = {k: self._to_config(k, v) for k, v in ov.items()}
            self._replace(self.live, cfg_ov, f"reference {rname}")
            self.references[str(rname)] = cfg_ov

    # ── reading ──
    @classmethod
    def load(cls, path_or_name, live: Optional[BacktestConfig] = None) -> "Space":
        """A space from a JSON file, or by the name of one of the files in ``backtesting/spaces/``."""
        p = Path(str(path_or_name)).expanduser()
        if not p.is_file():
            named = SPACES_DIR / f"{path_or_name}.json"
            if not named.is_file():
                known = ", ".join(sorted(x.stem for x in SPACES_DIR.glob("*.json"))) or "none"
                raise SpaceError(f"no search space {str(path_or_name)!r}: not a file, and not one of the shipped spaces ({known})")
            p = named
        try:
            spec = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            raise SpaceError(f"{p}: not valid JSON ({e})") from None
        return cls(spec, live=live, name=p.stem)

    def _check_names(self, where: str, names: Iterable[str]) -> None:
        unknown = sorted(set(names) - set(_FIELD_TYPES))
        if unknown:
            raise SpaceError(f"{where}: unknown BacktestConfig field(s): {', '.join(unknown)}")
        taken = sorted(set(names) & set(RESERVED_FIELDS))
        if taken:
            raise SpaceError(f"{where}: {', '.join(taken)} is set by the optimiser (the period and the sizing every "
                             f"setting is measured at) and cannot be part of a space")

    def _position(self, name: str, where: str) -> int:
        if name not in self._pos:
            raise SpaceError(f"{where}: {name} is not a parameter of this space")
        return self._pos[name]

    def _to_config(self, name: str, value):
        if name in self.price_fields and isinstance(value, (int, float)) and not isinstance(value, bool):
            value = value * self.px
        return _coerce(name, value)

    def _replace(self, cfg: BacktestConfig, overrides: dict, where: str) -> BacktestConfig:
        try:
            out = cfg.replace(**overrides)
            try:
                tfs = out.timeframes()
            except TypeError:               # sorting by the length of a timeframe nobody knows
                tfs = [None]
            if any(tf not in TF_SECONDS for tf in tfs):
                raise ValueError(f"it names a timeframe the backtester does not know; known: {', '.join(TF_SECONDS)}")
            return out
        except (TypeError, ValueError, KeyError, IndexError) as e:
            raise SpaceError(f"{where}: BacktestConfig does not accept {overrides!r} ({e})") from None

    def _param(self, name: str, spec) -> Param:
        if isinstance(spec, list):
            spec = {"values": spec}
        if not isinstance(spec, dict) or ("values" in spec) == ("range" in spec):
            raise SpaceError(f"parameter {name}: give either \"values\" (a list, or names mapped to values) or \"range\"")
        extra = sorted(set(spec) - {"values", "range", "step", "n", "log", "digits", "int", "scale", "ordered", "note"})
        if extra:
            raise SpaceError(f"parameter {name}: unknown key(s) {', '.join(extra)}")
        if spec.get("scale") not in (None, "price"):
            raise SpaceError(f"parameter {name}: the only \"scale\" is \"price\" (for a log range write \"log\": true)")
        if "range" in spec:
            values = _range_values(name, spec)
            labels = list(values)
        elif isinstance(spec["values"], dict):
            labels, values = list(spec["values"].keys()), list(spec["values"].values())
        elif isinstance(spec["values"], list):
            values = list(spec["values"])
            labels = [v if _is_scalar(v) else _compact(v) for v in values]
        else:
            raise SpaceError(f"parameter {name}: \"values\" is a list, or names mapped to values")
        if not values:
            raise SpaceError(f"parameter {name}: no values")
        config = [self._to_config(name, v) for v in values]
        held = [getattr(self._replace(self.base_cfg, {name: c}, f"parameter {name}, value {lab!r}"), name)
                for lab, c in zip(labels, config)]
        for i in range(len(held)):
            if any(_same(held[i], held[k]) for k in range(i)):
                raise SpaceError(f"parameter {name}: the value {labels[i]!r} is listed twice")
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
        return Param(name, values, labels, config, price=name in self.price_fields,
                     ordered=bool(spec.get("ordered", numeric)))

    def fingerprint(self) -> str:
        """Changes whenever a stored setting could mean something else: base, values, conditions, constraints."""
        blob = {"base": self.base, "price": sorted(self.price_fields),
                "parameters": [[p.name, p.values, p.labels, p.ordered] for p in self.params],
                "conditions": [[c.when.text, sorted(c.fix.items()), sorted(c.ignore)] for c in self.conditions],
                "constraints": [e.text for e in self.constraints]}
        return hashlib.sha1(json.dumps(blob, sort_keys=True, default=str).encode()).hexdigest()[:12]

    # ── settings ──
    def size(self) -> int:
        """Raw number of combinations, before conditions and constraints."""
        return int(np.prod([len(p.values) for p in self.params], dtype=object)) if self.params else 1

    def _env(self, cur: Sequence[Optional[int]]) -> Dict[str, Any]:
        env = dict(self._base_env)
        for p, i in zip(self.params, cur):
            if i is not None:
                env[p.name] = p.labels[i]
        return env

    def _applies(self, e: Expr, cur: Sequence[Optional[int]]) -> bool:
        """An expression that names a parameter which a condition has switched off says nothing about the setting."""
        return not any(cur[self._pos[n]] is None for n in e.names if n in self._pos)

    def canonical(self, raw: Sequence[Optional[int]]) -> Optional[Canon]:
        """
        The one form every equivalent choice of values is reduced to: conditions applied until
        nothing changes (a parameter that cannot matter becomes None, a value that equals another
        is replaced by it). None when a constraint is not met. A condition or constraint that names
        a switched-off parameter is passed over.
        """
        cur: List[Optional[int]] = list(raw)
        if len(cur) != len(self.params):
            raise SpaceError(f"a setting needs {len(self.params)} values, got {len(cur)}")
        for _ in range(len(self.conditions) + 2):
            changed = False
            for c in self.conditions:
                if not self._applies(c.when, cur) or not c.when(self._env(cur)):
                    continue
                for j in c.ignore:
                    if cur[j] is not None:
                        cur[j], changed = None, True
                for j, i in c.fix.items():
                    if cur[j] is not None and cur[j] != i:
                        cur[j], changed = i, True
            if not changed:
                break
        else:
            raise SpaceError("the conditions of this space contradict each other: they never settle on one form")
        env = self._env(cur)
        if not all(k(env) for k in self.constraints if self._applies(k, cur)):
            return None
        return tuple(cur)

    def timeframes(self) -> List[str]:
        """
        The timeframes a setting of this space may read: those of the base, of every value of every
        parameter put on the base, and of the references. (A combination can in principle add one
        more; the processes that run the settings then prepare it when it first appears.)
        """
        tfs = set(self.base_cfg.timeframes())
        for p in self.params:
            for c in p.config:
                tfs |= set(self._replace(self.base_cfg, {p.name: c}, p.name).timeframes())
        for ov in self.references.values():
            tfs |= set(self.live.replace(**ov).timeframes())
        return sorted(tfs, key=TF_SECONDS.get)

    def values(self, canon: Canon) -> Dict[str, Any]:
        """Parameter -> the value as the file writes it (its label), without the parameters switched off."""
        return {p.name: p.labels[i] for p, i in zip(self.params, canon) if i is not None}

    def overrides(self, canon: Canon) -> Dict[str, Any]:
        """Everything a setting changes relative to the LIVE settings: the base of the space, then its own values."""
        out = dict(self.base_overrides)
        out.update({p.name: p.config[i] for p, i in zip(self.params, canon) if i is not None})
        return out

    def config(self, canon: Canon) -> BacktestConfig:
        return self._replace(self.live, self.overrides(canon), f"setting {self.describe(canon)}")

    def key(self, canon: Canon) -> str:
        return config_key(self.config(canon))

    def describe(self, canon: Canon) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.values(canon).items()) or "the base settings"

    # ── samplers ──
    def grid(self, limit: Optional[int] = None) -> List[Canon]:
        """Every distinct setting, in the order of the file. Refused when there are more than ``limit``."""
        if self.size() > ENUM_LIMIT:
            raise SpaceError(f"the grid has {self.size():,} raw combinations, too many to enumerate (limit {ENUM_LIMIT:,}): "
                             f"use the random sampler")
        seen: Set[Canon] = set()
        out: List[Canon] = []
        for raw in itertools.product(*(range(len(p.values)) for p in self.params)):
            c = self.canonical(raw)
            if c is not None and c not in seen:
                seen.add(c)
                out.append(c)
        if limit is not None and len(out) > limit:
            raise SpaceError(f"the grid has {len(out):,} settings after conditions and constraints, above the limit of "
                             f"{limit:,}: use the random sampler (--sampler random --n ...), or raise the limit (--max-grid)")
        return out

    def random(self, n: int, seed: int = 1) -> List[Canon]:
        """
        Up to ``n`` distinct settings, the same list for the same seed; a larger ``n`` continues the
        list of a smaller one. A space with no more than ``n`` settings is returned whole.

        Stratified: each new setting takes, for every parameter, one of the values that the
        settings drawn so far contain least often (which of them: at random). Every value of every
        parameter is therefore covered evenly, to within one setting, wherever the conditions and
        constraints leave room for it. A draw that breaks a constraint, or that the conditions
        reduce to a setting already taken, is drawn again; when that keeps happening the choice
        widens to values used once more than the least-used, then twice more, and so on.
        """
        n = int(n)
        if n <= 0:
            return []
        every: Optional[List[Canon]] = None
        if self.size() <= ENUM_LIMIT:
            every = self.grid()
            if len(every) <= n:
                return every
        rng = np.random.default_rng(int(seed))
        used = [np.zeros(len(p.values), np.int64) for p in self.params]
        seen: Set[Canon] = set()
        out: List[Canon] = []
        tries, most, misses, slack = 0, 200 * n + 10_000, 0, 0
        while len(out) < n and tries < most:
            tries += 1
            raw = []
            for count in used:
                least = np.flatnonzero(count <= count.min() + slack)
                raw.append(int(least[rng.integers(len(least))]))
            c = self.canonical(raw)
            if c is None or c in seen:
                misses += 1
                if misses % 20 == 0:
                    slack += 1
                continue
            seen.add(c)
            out.append(c)
            misses = slack = 0
            for count, i in zip(used, c):
                if i is not None:                # a parameter a condition switched off was not used
                    count[i] += 1
        for c in every or []:                    # the draws kept missing: fill up in the order of the file
            if len(out) >= n:
                break
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def neighbours(self, canon: Canon) -> List[Canon]:
        """
        The settings one step away: one parameter moved to the value next to it (any other value for
        a parameter without an order). A parameter that such a step switches on starts from its
        anchor value.
        """
        raw = [i if i is not None else self.anchor[j] for j, i in enumerate(canon)]
        seen: Set[Canon] = {tuple(canon)}
        out: List[Canon] = []
        for j, p in enumerate(self.params):
            if canon[j] is None:
                continue
            steps = (canon[j] - 1, canon[j] + 1) if p.ordered else tuple(i for i in range(len(p.values)) if i != canon[j])
            for i in steps:
                if 0 <= i < len(p.values):
                    c = self.canonical(raw[:j] + [i] + raw[j + 1:])
                    if c is not None and c not in seen:
                        seen.add(c)
                        out.append(c)
        return out


# ───────────────────────────── the tick data behind a period ─────────────────────────────

_META_KEYS = ("store_version", "ticks", "seconds", "m1_bars", "first", "last")


def check_data(symbol: str, period: Period) -> Optional[str]:
    """
    Stop when a month of the period is not in the tick store. Returns a warning when the store
    holds little history before the period: the indicators of the first block then start cold.
    """
    from .data import store
    have = set(store.available_months(symbol))
    last = period.end - pd.Timedelta(milliseconds=1)
    need = [(p.year, p.month) for p in pd.period_range(period.start, last, freq="M")]
    missing = [f"{y}-{m:02d}" for (y, m) in need if (y, m) not in have]
    if missing:
        raise ValueError(f"the tick store has no {symbol} data for {', '.join(missing)}: build those months first "
                         f"(python -m backtesting data --from {missing[0]} --to {missing[-1]})")
    before = period.start - pd.Timedelta(days=30)
    if (before.year, before.month) not in have:
        return (f"the store holds no {symbol} history for {before:%Y-%m}, the month before the period starts: the "
                f"indicators of the first block run without their usual warm-up")
    return None


def data_stamps(symbol: str, period: Period, reach: Optional[pd.Timedelta] = None) -> List[str]:
    """
    Per block, a fingerprint of the tick history it is computed from: its own months and the
    ones before them that warm up the indicators, as far back as ``reach`` (default: a year). A
    stored result is reused only while this is unchanged, so a month that is rebuilt, or history
    that arrives later, recomputes exactly the blocks it touches.
    """
    from .data import store
    reach = pd.Timedelta(days=366) if reach is None else reach
    metas: Dict[Tuple[int, int], list] = {}
    for (y, m) in store.available_months(symbol):
        try:
            meta = json.loads((store.month_dir(store.DEFAULT_STORE_DIR, symbol, y, m) / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        metas[(y, m)] = [meta.get(k) for k in _META_KEYS]
    out = []
    for b in period.blocks:
        lo, hi = b.start - reach, b.end - pd.Timedelta(milliseconds=1)
        h = hashlib.sha1()
        for ym in sorted(metas):
            if (lo.year, lo.month) <= ym <= (hi.year, hi.month):
                h.update(json.dumps([list(ym), metas[ym]], default=str).encode())
        out.append("d" + h.hexdigest()[:9])
    return out


# ───────────────────────────── stored results ─────────────────────────────

class Store:
    """
    ``evaluations.jsonl``: the settings of a run and every (setting, block) result, one JSON object
    per line, appended as results arrive.

    The first line is a stamp: the space, the symbol, the engine build, the live rules and the
    account the replay uses. A file with another stamp is never reused: it is renamed
    ``evaluations.stale-<time>.jsonl`` and a new one is started (the settings in the renamed files
    still count as tried). Every result also carries the block it belongs to and the fingerprint of
    that block's tick data, and is used only for exactly that block and data, so changing the
    period keeps the blocks that are still part of it.
    """

    NAME = "evaluations.jsonl"

    def __init__(self, directory, stamp: Dict[str, Any], log: Callable[[str], None] = _log, read_only: bool = False):
        self.dir = Path(directory)
        self.path = self.dir / self.NAME
        self.stamp = json.loads(json.dumps(stamp))            # as it will read back
        self.settings: Dict[str, dict] = {}                   # key -> setting row, in the order they were added
        self.evals: Dict[Tuple[str, str], dict] = {}          # (key, block id) -> result row
        self._fh = None
        self._read(log, read_only)

    def _read(self, log, read_only: bool) -> None:
        if not self.path.exists():
            return
        raw = self.path.read_bytes()
        cut = raw.rfind(b"\n") + 1
        if cut != len(raw) and not read_only:
            # the last line was cut short by an interruption: drop it, so the next result starts on its own line
            with open(self.path, "r+b") as f:
                f.truncate(cut)
        rows = []
        for line in raw[:cut].decode("utf-8", "replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue                                      # a damaged line is a result to compute again
            if isinstance(row, dict):
                rows.append(row)
        if not rows:                                          # nothing was ever written: an empty file is a new one
            return
        head = rows[0].get("stamp") if rows[0].get("kind") == "header" else None
        if head != self.stamp:
            differs = sorted(k for k in set(self.stamp) | set(head or {}) if (head or {}).get(k) != self.stamp.get(k))
            what = f"another {', '.join(differs)}" if head else "an unknown build"
            if read_only:
                raise ValueError(f"{self.path} was written for {what}; run without --report-only to start again")
            aside, k = self.path.with_name(f"evaluations.stale-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"), 1
            while aside.exists():
                aside, k = self.path.with_name(f"evaluations.stale-{time.strftime('%Y%m%d-%H%M%S')}-{k}.jsonl"), k + 1
            os.replace(self.path, aside)
            log(f"{self.path.name} was written for {what}: kept as {aside.name}, starting again")
            return
        for row in rows[1:]:
            if row.get("kind") == "setting" and "key" in row:
                self.settings.setdefault(row["key"], row)
            elif row.get("kind") == "eval" and "key" in row and "block" in row:
                self.evals[(row["key"], row["block"])] = row

    def _write(self, row: dict) -> None:
        if self._fh is None:
            self.dir.mkdir(parents=True, exist_ok=True)
            fresh = not self.path.exists() or self.path.stat().st_size == 0
            self._fh = open(self.path, "a", encoding="utf-8")
            if fresh:
                head = {"kind": "header", "stamp": self.stamp, "written": time.strftime("%Y-%m-%d %H:%M:%S")}
                self._fh.write(json.dumps(head, sort_keys=True, separators=(",", ":")) + "\n")
        self._fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        self._fh.flush()

    def add_setting(self, key: str, canon: Canon, values: dict, overrides: dict, origin: str, round_: int = 0) -> bool:
        """Record a candidate setting; False when it is already there."""
        if key in self.settings:
            return False
        row = {"kind": "setting", "key": key, "canon": list(canon), "values": values, "overrides": overrides,
               "origin": origin, "round": int(round_)}
        self.settings[key] = row
        self._write(row)
        return True

    def add_eval(self, row: dict) -> None:
        self.evals[(row["key"], row["block"])] = row
        self._write(row)

    def get(self, key: str, block_id: str, data: str) -> Optional[dict]:
        """The stored result of a setting on a block, if it was computed from the tick data the block has now."""
        row = self.evals.get((key, block_id))
        return row if row is not None and row.get("data") == data else None

    def earlier_keys(self) -> Set[str]:
        """Settings tried in earlier runs whose results were set aside in this directory, and are not part of this run."""
        keys: Set[str] = set()
        for p in sorted(self.dir.glob("evaluations.stale-*.jsonl")):
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                if '"kind":"setting"' in line:
                    try:
                        keys.add(json.loads(line)["key"])
                    except (ValueError, KeyError):
                        pass
        return keys - set(self.settings)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


# ───────────────────────────── running settings ─────────────────────────────

def month_pnl(baskets: pd.DataFrame, edges_ms: Sequence[int], open_profit: float = 0.0) -> Tuple[List[float], List[int]]:
    """
    Net P/L and number of baskets per month of a block, by the time each basket closed. A basket
    still open when the block ends is not in ``baskets``; its floating result (``open_profit``)
    goes to the last month, so the months add up to the block's net P/L.
    """
    n = len(edges_ms) - 1
    pnl, count = np.zeros(n), np.zeros(n, np.int64)
    if len(baskets):
        closed = pd.DatetimeIndex(baskets["close_time"]).as_unit("ms").asi8
        where = np.clip(np.searchsorted(np.asarray(edges_ms, np.int64), closed, side="right") - 1, 0, n - 1)
        pnl = np.bincount(where, weights=baskets["pnl"].to_numpy(float), minlength=n).astype(float)
        count = np.bincount(where, minlength=n)
    pnl[-1] += float(open_profit)
    return [round(float(x), 4) for x in pnl], [int(c) for c in count]


_W: Dict[str, Any] = {}        # what one process holds: the live settings and ONE prepared block of data


def _w_init(live: dict, account: float, store_dir: Optional[str] = None, child: bool = False) -> None:
    os.environ.setdefault("NUMBA_NUM_THREADS", "1")
    if child:
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)      # Ctrl-C is for the parent, which then stops the workers
    _W.clear()
    _W.update(live=BacktestConfig.from_dict(live), account=float(account), store_dir=store_dir, block=None, prep=None)


def _w_eval(task: dict) -> dict:
    """One setting on one block: per-second series, one fixed unit, a balance too large to stop out."""
    from .analysis.metrics import score_row
    from .engine.fast import prepare, run

    live: BacktestConfig = _W["live"]
    prep = _W["prep"]
    if prep is None or _W["block"] != task["block"] or not set(task["tfs"]) <= set(prep.tfs):
        tfs = set(task["tfs"]) | (set(prep.tfs) if prep is not None and _W["block"] == task["block"] else set())
        _W["prep"] = prep = None                 # let go of the previous block first: one block of data per process
        gc.collect()
        kw = {"store_dir": _W["store_dir"]} if _W["store_dir"] else {}
        prep = prepare(live.symbol, task["start"], task["end"], sorted(tfs, key=TF_SECONDS.get), mode="sec", **kw)
        _W.update(block=task["block"], prep=prep)
    cfg = live.replace(start=task["start"], end=task["end"], **task["overrides"])
    if len(prep._cache) > 3:                     # indicator arrays per indicator setting: keep the memory bounded
        prep._cache.clear()
    t0 = time.time()
    res = run(cfg, prep, light=True)
    row = score_row(res, _W["account"])
    pnl, count = month_pnl(res.baskets, task["edges"], res.scalars["open_profit_at_end"])
    return {"kind": "eval", "key": task["key"], "block": task["block"], "data": task["data"],
            "net": float(row["net_profit"]), "pnl": pnl, "n": count, "baskets": int(row["baskets"]),
            "worst_basket": float(row["largest_loss"]), "wiped": bool(row["acct_wiped"]), "dip": float(row["acct_dip"]),
            "acct_net": float(row["acct_net"]), "max_units": int(row["acct_max_units"]),
            "max_loss": float(row["max_loss_from_start"]), "ladder_adds": int(row["ladder_adds"]),
            "max_lots": float(row["max_lots"]), "open_profit": round(float(res.scalars["open_profit_at_end"]), 2),
            "sec": round(time.time() - t0, 2)}


class Evaluator:
    """
    Runs (setting, block) tasks, in this process (``n_jobs`` 1) or in worker processes. A process
    prepares the data of a block when it meets the first task of that block and drops it when it
    meets another block, so it never holds more than one; tasks are handed out block by block.
    """

    def __init__(self, live: BacktestConfig, account: float, n_jobs: int = 2, store_dir: Optional[str] = None):
        self.live, self.account, self.store_dir = live, float(account), store_dir
        self.n_jobs = max(1, int(n_jobs or 1))
        self.runs = 0                            # evaluations computed so far
        self._pool = None

    def __enter__(self) -> "Evaluator":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)      # a run in progress finishes, nothing new starts
            self._pool = None
        if _W.get("owner") == id(self):
            _W.clear()

    def run(self, tasks: Sequence[dict]) -> Iterable[dict]:
        """Results in the order they finish."""
        if not tasks:
            return
        if self.n_jobs == 1:
            if _W.get("owner") != id(self):
                _w_init(self.live.to_dict(), self.account, self.store_dir)
                _W["owner"] = id(self)
            for task in tasks:
                row = _w_eval(task)
                self.runs += 1
                yield row
            return
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from concurrent.futures.process import BrokenProcessPool
        if self._pool is None:
            self._pool = ProcessPoolExecutor(self.n_jobs, mp_context=mp.get_context("spawn"), initializer=_w_init,
                                             initargs=(self.live.to_dict(), self.account, self.store_dir, True))
        futures = [self._pool.submit(_w_eval, task) for task in tasks]         # handed out in this order
        try:
            for done in as_completed(futures):
                row = done.result()
                self.runs += 1
                yield row
        except BrokenProcessPool:
            # a pool that lost a process would otherwise wait for its result for ever
            self._pool = None
            raise RuntimeError("a worker process died (out of memory?). Every finished run is saved: run the same "
                               "command again, with a smaller --jobs if memory is short") from None
        finally:
            for f in futures:
                f.cancel()


def _dur(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    return f"{seconds / 3600:.1f} h" if seconds >= 5400 else f"{seconds / 60:.0f} min" if seconds >= 90 else f"{seconds:.0f} s"


def evaluate(ev: Evaluator, store: Store, tasks: Sequence[dict], log: Callable[[str], None] = _log,
             what: str = "", every_s: float = 30.0) -> int:
    """Run the tasks, appending every result to the store as it arrives, with a progress line every ``every_s`` seconds."""
    total, done, t0 = len(tasks), 0, time.time()
    last = t0
    if total > 50:
        log(f"  {what}{total:,} runs to do on {ev.n_jobs} process{'es' if ev.n_jobs > 1 else ''}")
    for row in ev.run(tasks):
        store.add_eval(row)
        done += 1
        now = time.time()
        if now - last >= every_s and done < total:
            each = (now - t0) / done
            log(f"  {what}{done:,} of {total:,} runs done · {each * ev.n_jobs:.1f} s per run · about {_dur((total - done) * each)} left")
            last = now
    if total:
        log(f"  {what}{total:,} runs in {_dur(time.time() - t0)}")
    return done


# ───────────────────────────── the stored matrix ─────────────────────────────

@dataclass
class Table:
    """What was measured for some settings on the blocks and months of a period (NaN = not evaluated)."""
    keys: List[str]
    pnl: np.ndarray         # settings x months: net P/L of one unit, USD
    count: np.ndarray       # settings x months: baskets closed
    net: np.ndarray         # settings x blocks: net P/L of the block
    wiped: np.ndarray       # settings x blocks: 1 when the replayed account was wiped
    dip: np.ndarray         # settings x blocks: deepest the replayed account stood below its start, USD
    worst: np.ndarray       # settings x blocks: worst basket, USD


def build_table(store: Store, keys: Sequence[str], period: Period, stamps: Sequence[str]) -> Table:
    s_n, m_n, b_n = len(keys), len(period.months), len(period.blocks)
    pnl, count = np.full((s_n, m_n), np.nan), np.full((s_n, m_n), np.nan)
    net, wiped, dip, worst = (np.full((s_n, b_n), np.nan) for _ in range(4))
    for s, key in enumerate(keys):
        for b in period.blocks:
            row = store.get(key, b.id, stamps[b.index])
            if row is None or len(row.get("pnl", ())) != len(b.months):
                continue
            cols = list(b.months)
            pnl[s, cols], count[s, cols] = row["pnl"], row["n"]
            net[s, b.index], wiped[s, b.index] = row["net"], float(bool(row["wiped"]))
            dip[s, b.index], worst[s, b.index] = row["dip"], row["worst_basket"]
    return Table(list(keys), pnl, count, net, wiped, dip, worst)


@dataclass
class Role:
    """Some blocks of a period (the selection blocks, or the held-out ones) and their full months."""
    blocks: np.ndarray              # block positions, in time order
    months: np.ndarray              # positions of the FULL months of those blocks: what every statistic uses
    groups: List[np.ndarray]        # per block: where its full months sit in ``months``
    every: np.ndarray               # positions of all months of those blocks, the short ones included


def role_of(period: Period, blocks: Sequence[int]) -> Role:
    months: List[int] = []
    every: List[int] = []
    groups: List[np.ndarray] = []
    for bi in blocks:
        mine = [m for m in period.blocks[int(bi)].months if period.months[m].full]
        groups.append(np.arange(len(months), len(months) + len(mine)))
        months += mine
        every += list(period.blocks[int(bi)].months)
    return Role(np.asarray(list(blocks), int), np.asarray(months, int), groups, np.asarray(every, int))


# ───────────────────────────── objectives and diagnostics: arrays in, numbers out ─────────────────────────────
# X is always a (settings x months) matrix of monthly net P/L, ``groups`` the columns of each block,
# ``wiped`` / ``dip`` the (settings x blocks) account replay. Nothing below runs a backtest.

def _stats(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mean, standard deviation and standard error of the mean of every row."""
    s_n, n = X.shape
    mean = X.mean(axis=1) if n else np.zeros(s_n)
    sd = X.std(axis=1, ddof=1) if n > 1 else np.zeros(s_n)
    return mean, sd, (sd / math.sqrt(n) if n > 1 else np.zeros(s_n))


def _cols(groups: Sequence[np.ndarray]) -> np.ndarray:
    return np.concatenate([np.asarray(g, int) for g in groups]) if len(groups) else np.zeros(0, int)


def objective(name: str, X: np.ndarray, groups: Optional[Sequence[np.ndarray]] = None) -> np.ndarray:
    """
    The figure a setting is ranked by, for every row of ``X``, over the months in ``groups``
    (all of them when ``groups`` is None):

    ``lcb``          mean monthly net minus one standard error (the default)
    ``mean``         mean monthly net
    ``median``       median monthly net
    ``sharpe``       mean monthly net divided by its standard deviation
    ``worst_block``  net of the worst block
    """
    X = np.asarray(X, float)
    if groups is None:
        groups = [np.arange(X.shape[1])]
    Y = X[:, _cols(groups)]
    if name not in OBJECTIVES:
        raise ValueError(f"unknown objective {name!r}; known: {', '.join(OBJECTIVES)}")
    if Y.shape[1] == 0:
        return np.zeros(X.shape[0])
    mean, sd, se = _stats(Y)
    if name == "lcb":
        value = mean - se
    elif name == "mean":
        value = mean
    elif name == "median":
        value = np.median(Y, axis=1)
    elif name == "sharpe":
        value = np.where(sd > 1e-12, mean / np.maximum(sd, 1e-12), 0.0)
    else:
        value = np.min(np.stack([X[:, np.asarray(g, int)].sum(axis=1) for g in groups if len(g)], axis=1), axis=1)
    # P/L is kept to a hundredth of a cent: rounding here makes equal settings tie exactly instead of by float noise
    return np.round(value, 9)


def eligible(wiped: np.ndarray, dip: np.ndarray, allow_wiped: bool = False, max_dip: float = 0.0) -> np.ndarray:
    """Rows that may be chosen: never wiped on these blocks, never dipped deeper than ``max_dip`` (0 = no limit)."""
    wiped, dip = np.nan_to_num(np.asarray(wiped, float)), np.nan_to_num(np.asarray(dip, float))
    ok = np.ones(wiped.shape[0], bool)
    if wiped.shape[1] == 0:
        return ok
    if not allow_wiped:
        ok &= ~(wiped > 0).any(axis=1)
    if max_dip and max_dip > 0:
        ok &= dip.max(axis=1) <= max_dip
    return ok


def ranking(obj: np.ndarray, mean: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """Row positions, best first: eligible rows before the others, by objective, then mean, then the order tried."""
    return np.lexsort((np.arange(len(obj)), -np.asarray(mean, float), -np.asarray(obj, float), ~np.asarray(ok, bool)))


def _best(obj: np.ndarray, mean: np.ndarray, ok: np.ndarray) -> int:
    order = ranking(obj, mean, ok)
    return int(order[0]) if len(order) and ok[order[0]] else -1


def walk_forward(X: np.ndarray, groups: Sequence[np.ndarray], wiped: np.ndarray, dip: np.ndarray, name: str = "lcb",
                 allow_wiped: bool = False, max_dip: float = 0.0) -> Optional[dict]:
    """
    Choose on all blocks up to t, score block t + 1, move on. Each step sees only the months and
    the account replays of earlier blocks; the months it scores are joined into one out-of-sample
    series: what re-optimising after every block, with past data only, would have made.
    When no setting is eligible on the past blocks the step stays out (zero).
    """
    X = np.asarray(X, float)
    steps = []
    for k in range(1, len(groups)):
        test, past = np.asarray(groups[k], int), list(groups[:k])
        if len(test) == 0 or len(_cols(past)) == 0:
            continue
        obj, mean = objective(name, X, past), objective("mean", X, past)
        s = _best(obj, mean, eligible(wiped[:, :k], dip[:, :k], allow_wiped, max_dip))
        steps.append({"block": k, "chosen": s, "months": test,
                      "train_months": int(len(_cols(past))),
                      "train_objective": float(obj[s]) if s >= 0 else float("nan"),
                      "train_mean": float(mean[s]) if s >= 0 else float("nan"),
                      "pnl": X[s, test].copy() if s >= 0 else np.zeros(len(test)),
                      "wiped": bool(s >= 0 and np.nan_to_num(wiped[s, k]) > 0)})
    if not steps:
        return None
    pnl = np.concatenate([st["pnl"] for st in steps])
    n = len(pnl)
    chosen = [st["train_mean"] for st in steps if st["chosen"] >= 0]
    return {"steps": steps, "months": np.concatenate([st["months"] for st in steps]), "pnl": pnl, "n": n,
            "total": float(pnl.sum()), "mean": float(pnl.mean()),
            "se": float(pnl.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0, "positive": int((pnl > 0).sum()),
            "train_mean": float(np.mean(chosen)) if chosen else float("nan"),
            "wiped_steps": int(sum(st["wiped"] for st in steps)), "stayed_out": int(sum(st["chosen"] < 0 for st in steps))}


def cscv(X: np.ndarray, groups: Sequence[np.ndarray], wiped: np.ndarray, dip: np.ndarray, name: str = "lcb",
         allow_wiped: bool = False, max_dip: float = 0.0, max_splits: int = 20_000, seed: int = 0) -> Optional[dict]:
    """
    Probability of backtest overfitting by combinatorially symmetric cross-validation (Bailey,
    Borwein, Lopez de Prado, Zhu): the blocks are split into two halves in every possible way; the
    best eligible setting of one half is looked up on the other half, where its rank among all
    settings is recorded (0 = worst, 1 = best).

    ``pbo``        share of splits in which it lands below the median there (0.5 is what noise gives)
    ``is_mean``    its average monthly net on the half it was chosen on
    ``oos_mean``   its average monthly net on the other half
    ``oos_loss``   share of splits in which it lost money on the other half
    ``oos_wiped``  share of splits in which the replayed account was wiped on the other half

    With an odd number of blocks the halves differ by one block and both ways round are used.
    More than ``max_splits`` splits are sampled at random.
    """
    X = np.asarray(X, float)
    g_n = len(groups)
    if g_n < 2 or X.shape[0] < 2:
        return None
    half = g_n // 2
    sizes = [half] if g_n % 2 == 0 else [half, g_n - half]
    total = sum(math.comb(g_n, k) for k in sizes)
    if total <= max_splits:
        splits = [c for k in sizes for c in itertools.combinations(range(g_n), k)]
    else:
        rng = np.random.default_rng(seed)
        splits = [tuple(sorted(rng.permutation(g_n)[: sizes[i % len(sizes)]].tolist())) for i in range(max_splits)]
    ranks, below, is_mean, oos_mean, oos_wiped, skipped = [], [], [], [], [], 0
    for chosen_on in splits:
        other = [g for g in range(g_n) if g not in chosen_on]
        g_in, g_out = [groups[g] for g in chosen_on], [groups[g] for g in other]
        if len(_cols(g_in)) == 0 or len(_cols(g_out)) == 0:
            skipped += 1
            continue
        obj_in, mean_in = objective(name, X, g_in), objective("mean", X, g_in)
        s = _best(obj_in, mean_in, eligible(wiped[:, list(chosen_on)], dip[:, list(chosen_on)], allow_wiped, max_dip))
        if s < 0:
            skipped += 1
            continue
        obj_out, mean_out = objective(name, X, g_out), objective("mean", X, g_out)
        rank = float(((obj_out < obj_out[s]).sum() + 0.5 * (obj_out == obj_out[s]).sum()) / len(obj_out))
        ranks.append(rank)
        below.append(1.0 if rank < 0.5 else 0.5 if rank == 0.5 else 0.0)
        is_mean.append(float(mean_in[s]))
        oos_mean.append(float(mean_out[s]))
        oos_wiped.append(bool((np.nan_to_num(wiped[s, other]) > 0).any()))
    if not ranks:
        return None
    return {"splits": len(ranks), "of": int(total), "skipped": int(skipped), "pbo": float(np.mean(below)),
            "rank_median": float(np.median(ranks)), "is_mean": float(np.mean(is_mean)),
            "oos_mean": float(np.mean(oos_mean)), "oos_loss": float(np.mean(np.asarray(oos_mean) < 0)),
            "oos_wiped": float(np.mean(oos_wiped)), "ranks": np.asarray(ranks)}


_ERF = np.vectorize(math.erf, otypes=[float])


def expected_max_normal(n: float) -> float:
    """Expected largest of ``n`` independent standard normal draws (``n`` need not be whole; 0 for n <= 1)."""
    if n <= 1.0:
        return 0.0
    x = np.linspace(-9.0, 9.0, 7201)
    pdf = np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
    cdf = 0.5 * (1.0 + _ERF(x / math.sqrt(2.0)))
    y = x * n * pdf * cdf ** (n - 1.0)
    return float(np.sum((y[1:] + y[:-1]) * np.diff(x)) / 2.0)


def effective_trials(emax: float) -> float:
    """How many independent draws have ``emax`` as their expected maximum (the inverse of ``expected_max_normal``)."""
    if not emax > 0:
        return 1.0
    lo, hi = 0.0, math.log(1e9)
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if expected_max_normal(math.exp(mid)) < emax:
            lo = mid
        else:
            hi = mid
    return float(math.exp((lo + hi) / 2.0))


def haircut(X: np.ndarray, groups: Sequence[np.ndarray], ok: np.ndarray, name: str = "lcb", n_boot: int = 2000,
            seed: int = 0, extra_trials: int = 0) -> Optional[dict]:
    """
    What the search would show if no setting had any edge: the haircut for the number of settings tried.

    Every eligible setting has its own average taken away (zero edge, its month-to-month spread and
    its likeness to the other settings kept), the months are then drawn again with replacement, the
    same months for all settings, and the best setting is picked exactly as the real search picks it.
    Repeated ``n_boot`` times this gives what picking the best of that many edgeless settings yields:

    ``null_mean``       average monthly net of the picked setting (``null_mean_p95``: its 95th percentile)
    ``null_objective``  its average objective
    ``p``               share of such searches whose best objective reaches the real one
    ``n_eff``           the number of independent settings that would produce the same spread of
                        best results (similar settings count as one; this is why the haircut is
                        smaller than for as many unrelated settings)
    ``independent``     the same haircut if the settings were unrelated: a typical standard error
                        times the expected largest of that many standard normal draws

    ``extra_trials`` are settings tried elsewhere (other spaces, by hand, in earlier runs) among
    which this result was also chosen: ``p_all`` and the ``null_*`` figures allow for them as if
    they were as alike as the settings here.
    """
    X = np.asarray(X, float)
    cols = _cols(groups)
    pool = np.flatnonzero(ok)
    n = len(cols)
    if len(pool) == 0 or n < 2 or n_boot < 1:
        return None
    P = X[np.ix_(pool, cols)]
    sizes = np.cumsum([0] + [len(g) for g in groups])
    packs = [np.arange(sizes[i], sizes[i + 1]) for i in range(len(groups))]     # the blocks, on the redrawn months
    obj, (mean, _, se) = objective(name, P, packs), _stats(P)
    b = _best(obj, mean, np.ones(len(pool), bool))
    C = P - mean[:, None]
    moving = se > 0
    rng = np.random.default_rng(seed)
    null_obj, null_mean, null_t = np.empty(n_boot), np.empty(n_boot), np.zeros(n_boot)
    for r in range(n_boot):
        B = C[:, rng.integers(0, n, n)]
        ob, mb = objective(name, B, packs), B.mean(axis=1)
        j = int(np.argmax(ob))
        null_obj[r], null_mean[r] = ob[j], mb[j]
        if moving.any():
            null_t[r] = (mb[moving] / se[moving]).max()
    n_eff = effective_trials(float(null_t.mean()) * math.sqrt(n / (n - 1.0)))
    more = (len(pool) + max(0, int(extra_trials))) / len(pool)
    grow = expected_max_normal(n_eff * more) / expected_max_normal(n_eff) if more > 1 and n_eff > 1.0001 else 1.0
    p = float((1 + (null_obj >= obj[b] - 1e-12).sum()) / (n_boot + 1))
    return {"best": int(pool[b]), "objective": float(obj[b]), "mean": float(mean[b]), "se": float(se[b]),
            "null_objective": float(null_obj.mean()), "null_mean": float(null_mean.mean() * grow),
            "null_mean_p95": float(np.quantile(null_mean, 0.95) * grow), "p": p, "p_all": float(1.0 - (1.0 - p) ** more),
            "pool": int(len(pool)), "extra": max(0, int(extra_trials)), "n_eff": float(n_eff), "n_boot": int(n_boot),
            "independent": float(math.sqrt(np.mean(se ** 2)) * expected_max_normal(len(pool) * more))}


def carry_over(chosen_by: np.ndarray, later: np.ndarray, ok: np.ndarray) -> Optional[dict]:
    """
    Does the order of the settings on the months they were ranked on say anything about the
    held-out months? ``spearman`` is the rank correlation over all settings; ``top_*`` is what the
    best tenth of the eligible settings went on to do there, next to the average setting.
    """
    chosen_by, later = np.asarray(chosen_by, float), np.asarray(later, float)
    if len(chosen_by) < 10:
        return None
    ra, rb = pd.Series(chosen_by).rank().to_numpy(), pd.Series(later).rank().to_numpy()
    rho = float(np.corrcoef(ra, rb)[0, 1]) if ra.std() > 0 and rb.std() > 0 else float("nan")
    pool = np.flatnonzero(ok)
    top = pool[np.argsort(-chosen_by[pool], kind="stable")][: max(1, len(pool) // 10)] if len(pool) else pool
    return {"n": int(len(later)), "spearman": rho, "top_n": int(len(top)),
            "top_mean": float(later[top].mean()) if len(top) else float("nan"),
            "top_positive": float((later[top] > 0).mean()) if len(top) else float("nan"),
            "all_mean": float(later.mean()), "all_positive": float((later > 0).mean())}


# ───────────────────────────── a run: options, analysis ─────────────────────────────

@dataclass
class Options:
    """Everything one ``optimise`` run is told (the command line fills this in)."""
    space: str
    symbol: str = "XAUUSDm"
    start: str = DEV[0]
    end: str = DEV[1]
    block: str = "3mo"
    slice: str = "1mo"
    holdout_from: Optional[str] = None
    holdout_to: Optional[str] = None
    holdout_top_only: bool = False      # run the held-out blocks for the short list and the references only
    sampler: str = "random"             # random | grid | stored (no new settings)
    n: int = 200
    seed: int = 1
    max_grid: int = 2000
    refine_rounds: int = 2
    refine_top: int = 5
    objective: str = "lcb"
    allow_wiped: bool = False
    max_dip: float = 1000.0             # deepest the replayed account may stand below its start, USD (0 = no limit)
    account: float = 2000.0
    top: int = 10
    also_tried: int = 0                 # settings tried elsewhere that this result was also chosen among
    bootstrap: int = 2000
    validate: bool = False
    validate_top: int = 5
    validate_seeds: int = 8
    report_only: bool = False
    jobs: int = 2
    out: Optional[str] = None
    live_root: Optional[str] = None
    allow_reserved: bool = False


@dataclass
class Analysis:
    """Everything the output files are written from. Positions index ``keys`` unless stated otherwise."""
    space: Space
    period: Period
    hold: np.ndarray                    # per block: held out
    o: Options
    stamp: Dict[str, Any]
    sel: Role
    ho: Role
    table: Table                        # all candidate settings stored, every block and month
    rows: np.ndarray                    # positions in ``table`` of the candidates complete on the selection blocks
    keys: List[str]                     # those candidates, in the order they were tried
    settings: List[dict]                # their stored rows: values, canon, overrides, origin, round
    X: np.ndarray                       # their monthly net on the full selection months
    ok: np.ndarray                      # eligible under the account constraints
    order: np.ndarray                   # best first
    s: Dict[str, np.ndarray]            # selection figures per candidate
    h: Dict[str, np.ndarray]            # hold-out figures per candidate (NaN where not run)
    nb: Dict[str, np.ndarray]           # one-step neighbours per candidate
    refs: List[dict]                    # reference settings with their own figures
    ref_table: Table
    params: pd.DataFrame                # averages by parameter value
    haircut: Optional[dict] = None
    pbo: Optional[dict] = None
    wf: Optional[dict] = None
    carry: Optional[dict] = None
    looks: List[dict] = field(default_factory=list)       # every time this hold-out was reported in this directory
    sample: int = 0                     # settings of the grid or random sample: the pool of the walk-forward and of the split test
    incomplete: int = 0
    earlier: int = 0
    notes: List[str] = field(default_factory=list)
    validation: Optional[pd.DataFrame] = None
    live_root: Optional[Path] = None

    @property
    def best(self) -> int:
        """Position of the best eligible candidate, -1 when there is none."""
        return int(self.order[0]) if len(self.order) and self.ok[self.order[0]] else -1

    def top(self, k: Optional[int] = None) -> List[int]:
        """The short list: the best ``k`` eligible candidates."""
        k = self.o.top if k is None else k
        return [int(i) for i in self.order[:k] if self.ok[i]]


_FIGURES = ("months", "objective", "mean", "se", "lcb", "median", "sharpe", "worst_block", "total", "positive", "t",
            "baskets", "baskets_per_month", "worst_basket", "wiped_blocks", "max_dip")


def summarise(table: Table, rows: Sequence[int], role: Role, name: str) -> Dict[str, np.ndarray]:
    """
    The figures of some settings on the blocks of one role (NaN for a setting not run on all of them).
    Monthly figures are over the full months; ``baskets``, ``worst_basket``, ``wiped_blocks`` and
    ``max_dip`` cover the whole blocks.
    """
    rows = np.asarray(rows, int)
    out = {k: np.full(len(rows), np.nan) for k in _FIGURES}
    if len(rows) == 0 or len(role.blocks) == 0:
        return out
    done = ~np.isnan(table.net[np.ix_(rows, role.blocks)]).any(axis=1)
    r = rows[done]
    if len(r) == 0:
        return out
    X = table.pnl[np.ix_(r, role.months)]
    mean, _, se = _stats(X)
    figures = {"months": np.full(len(r), float(X.shape[1])),
               "baskets": table.count[np.ix_(r, role.every)].sum(axis=1),
               "worst_basket": table.worst[np.ix_(r, role.blocks)].min(axis=1),
               "wiped_blocks": (table.wiped[np.ix_(r, role.blocks)] > 0).sum(axis=1).astype(float),
               "max_dip": table.dip[np.ix_(r, role.blocks)].max(axis=1)}
    if X.shape[1]:
        figures.update({"objective": objective(name, X, role.groups), "mean": mean, "se": se, "lcb": mean - se,
                        "median": np.median(X, axis=1), "sharpe": objective("sharpe", X),
                        "worst_block": objective("worst_block", X, role.groups), "total": X.sum(axis=1),
                        "positive": (X > 0).sum(axis=1).astype(float),
                        "t": np.divide(mean, se, out=np.zeros(len(r)), where=se > 0),
                        "baskets_per_month": table.count[np.ix_(r, role.months)].mean(axis=1)})
    for k, v in figures.items():
        out[k][done] = v
    return out


def _neighbour_figures(space: Space, settings: Sequence[dict], obj: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Per setting: how many settings lie one step away (``of``), how many of them have been run
    (``n``), their average objective (``objective``) and how many of them have a positive one
    (``positive``). A setting whose neighbours do about as well sits on a plateau; one that towers
    over them is a spike, and spikes rarely repeat.
    """
    at = {tuple(rec["canon"]): i for i, rec in enumerate(settings)}
    out = {k: np.full(len(settings), np.nan) for k in ("of", "n", "objective", "positive")}
    for i, rec in enumerate(settings):
        around = space.neighbours(tuple(rec["canon"]))
        run = [at[c] for c in around if c in at]
        out["of"][i], out["n"][i] = len(around), len(run)
        if run:
            out["objective"][i], out["positive"][i] = float(obj[run].mean()), float((obj[run] > 0).sum())
    return out


def _parameter_averages(space: Space, settings: Sequence[dict], s: Dict[str, np.ndarray], ok: np.ndarray,
                        h: Dict[str, np.ndarray]) -> pd.DataFrame:
    """
    For every value of every parameter: the average over all settings that contain it. Only the
    settings of the grid or of the random sample count (they cover the values evenly; refinement
    crowds around the best), and a setting in which a condition switched the parameter off is left out.
    """
    design = np.array([rec.get("origin") in ("grid", "random") for rec in settings], bool)
    rows = []
    for j, p in enumerate(space.params):
        for i, label in enumerate(p.labels):
            pick = np.array([design[k] and rec["canon"][j] == i for k, rec in enumerate(settings)], bool)
            if not pick.any():
                continue
            held = h["mean"][pick]
            rows.append({"parameter": p.name, "value": label, "settings": int(pick.sum()),
                         "objective": float(s["objective"][pick].mean()), "mean": float(s["mean"][pick].mean()),
                         "positive": float((s["mean"][pick] > 0).mean()), "eligible": float(ok[pick].mean()),
                         "holdout_mean": float(np.nanmean(held)) if np.isfinite(held).any() else float("nan")})
    return pd.DataFrame(rows, columns=["parameter", "value", "settings", "objective", "mean", "positive", "eligible", "holdout_mean"])


def analyse(space: Space, store: Store, period: Period, hold: np.ndarray, stamps: Sequence[str], o: Options,
            stamp: Optional[dict] = None, live_root: Optional[Path] = None) -> Analysis:
    """Rank the stored settings on the selection months and compute every diagnostic. Runs no backtest."""
    sel, ho = role_of(period, np.flatnonzero(~hold)), role_of(period, np.flatnonzero(hold))
    cand = list(store.settings)
    table = build_table(store, cand, period, stamps)
    complete = ~np.isnan(table.net[:, sel.blocks]).any(axis=1) if cand else np.zeros(0, bool)
    rows = np.flatnonzero(complete)
    keys = [cand[i] for i in rows]
    settings = [store.settings[k] for k in keys]
    X = table.pnl[np.ix_(rows, sel.months)]
    W, D = table.wiped[np.ix_(rows, sel.blocks)], table.dip[np.ix_(rows, sel.blocks)]
    s, h = summarise(table, rows, sel, o.objective), summarise(table, rows, ho, o.objective)
    ok = eligible(W, D, o.allow_wiped, o.max_dip)
    order = ranking(np.nan_to_num(s["objective"]), np.nan_to_num(s["mean"]), ok)
    refs = []
    ref_keys = [config_key(space.live.replace(**ov)) for ov in space.references.values()]
    ref_table = build_table(store, ref_keys, period, stamps)
    rs = summarise(ref_table, np.arange(len(ref_keys)), sel, o.objective)
    rh = summarise(ref_table, np.arange(len(ref_keys)), ho, o.objective)
    for i, (name, ov) in enumerate(space.references.items()):
        refs.append({"name": name, "key": ref_keys[i], "overrides": ov, "s": {k: float(v[i]) for k, v in rs.items()},
                     "h": {k: float(v[i]) for k, v in rh.items()}})
    a = Analysis(space=space, period=period, hold=np.asarray(hold, bool), o=o, stamp=dict(stamp or {}), sel=sel, ho=ho,
                 table=table, rows=rows, keys=keys, settings=settings, X=X, ok=ok, order=order, s=s, h=h,
                 nb=_neighbour_figures(space, settings, np.nan_to_num(s["objective"])), refs=refs, ref_table=ref_table,
                 params=_parameter_averages(space, settings, s, ok, h), incomplete=int(len(cand) - len(rows)),
                 earlier=len(store.earlier_keys()), live_root=live_root)
    if len(rows) and X.shape[1] >= 2:
        extra = a.earlier + max(0, int(o.also_tried))
        a.haircut = haircut(X, sel.groups, ok, o.objective, n_boot=o.bootstrap, seed=o.seed, extra_trials=extra)
        # The two tests that imitate "choose on part of the data" use the grid or random sample only. Refinement
        # decided what to run by looking at every selection month, so its settings would carry that hindsight
        # into the parts of those tests that are meant to be unseen.
        sample = np.flatnonzero([rec.get("origin") in ("grid", "random") for rec in settings])
        a.sample = int(len(sample))
        a.pbo = cscv(X[sample], sel.groups, W[sample], D[sample], o.objective, o.allow_wiped, o.max_dip, seed=o.seed)
        a.wf = walk_forward(X[sample], sel.groups, W[sample], D[sample], o.objective, o.allow_wiped, o.max_dip)
        if a.wf is not None:
            for st in a.wf["steps"]:
                st["chosen"] = int(sample[st["chosen"]]) if st["chosen"] >= 0 else -1       # as a position in ``keys``
            # the same out-of-sample months for: the final best setting (hindsight), the average setting, each reference
            cols = a.wf["months"]
            a.wf["hindsight_mean"] = float(X[a.best, cols].mean()) if a.best >= 0 else float("nan")
            a.wf["average_mean"] = float(X[np.ix_(sample, cols)].mean())
            a.wf["references"] = {r["name"]: float(ref_table.pnl[i, sel.months[cols]].mean())
                                  for i, r in enumerate(refs) if np.isfinite(r["s"]["months"])}
        held = np.isfinite(h["mean"])
        if held.sum() >= 10:
            a.carry = carry_over(np.nan_to_num(s["objective"])[held], h["mean"][held], ok[held])
    return a


# ───────────────────────────── output files ─────────────────────────────

def _m(x, digits: int = 1) -> str:
    """A signed amount; a dash when there is none."""
    return "–" if x is None or not np.isfinite(x) else f"{x:+,.{digits}f}"


def _n(x, digits: int = 0) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{x:,.{digits}f}"


def _pc(x) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100.0 * x:.0f}%"


def _show(label) -> str:
    """A parameter value as a table shows it."""
    if label is None:
        return "none"
    if isinstance(label, bool):
        return "true" if label else "false"
    if isinstance(label, float):
        return f"{label:g}"
    return str(label)


def _md(head: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def run_command(symbol: str, start: str, end: str, overrides: Dict[str, Any], live_root: Optional[Path] = None,
                fixed_unit: bool = False) -> str:
    """
    The ``python -m backtesting run`` line for a setting: every override relative to the live
    settings as ``--set name=<JSON>``. ``fixed_unit`` adds the sizing the optimiser measures at
    (one unit, a balance too large to stop out), which reproduces a block's stored figure exactly.
    """
    parts = ["python", "-m", "backtesting", "run", "--symbol", symbol, "--start", start, "--end", end]
    if fixed_unit:
        from .experiments import SWEEP_BALANCE
        parts += ["--balance", f"{SWEEP_BALANCE:.0f}", "--set", "fixed_units=1"]
    for k in sorted(overrides):
        parts += ["--set", f"{k}={json.dumps(overrides[k])}"]
    if live_root is not None and Path(live_root).resolve() != REPO_ROOT.resolve():
        parts += ["--live-root", str(live_root)]
    return " ".join(shlex.quote(p) for p in parts)


def _account(wiped_blocks: float, max_dip: float) -> str:
    if not np.isfinite(max_dip):
        return "–"
    return f"wiped in {int(wiped_blocks)}" if wiped_blocks > 0 else f"dip {max_dip:,.0f}"


def trials_frame(a: Analysis) -> pd.DataFrame:
    """One row per setting, best first (eligible settings before the others), then the references."""
    held = len(a.ho.blocks) > 0
    rows = []

    def figures(row: dict, s: Dict[str, Any], h: Dict[str, Any], at) -> None:
        for k in _FIGURES:
            row[k] = s[k][at] if at is not None else s[k]
        if held:
            for k in _FIGURES:
                row[f"holdout_{k}"] = h[k][at] if at is not None else h[k]

    for rank, i in enumerate(a.order, 1):
        rec = a.settings[i]
        row: Dict[str, Any] = {"rank": rank if a.ok[i] else np.nan, "name": "", "key": a.keys[i], "origin": rec["origin"],
                               "round": rec["round"]}
        for p in a.space.params:
            # empty = a condition switched the parameter off; "none" = the value null (no stop, no trend filter ...)
            row[p.name] = ("none" if rec["values"][p.name] is None else rec["values"][p.name]) if p.name in rec["values"] else ""
        row["eligible"] = bool(a.ok[i])
        figures(row, a.s, a.h, i)
        row.update(neighbours=a.nb["n"][i], neighbours_of=a.nb["of"][i], neighbour_objective=a.nb["objective"][i],
                   overrides=json.dumps(rec["overrides"], sort_keys=True))
        rows.append(row)
    for r in a.refs:
        row = {"rank": np.nan, "name": r["name"], "key": r["key"], "origin": "reference", "round": np.nan}
        row.update({p.name: "" for p in a.space.params})
        row["eligible"] = bool(np.isfinite(r["s"]["max_dip"]) and eligible(np.array([[r["s"]["wiped_blocks"]]]),
                                                                           np.array([[r["s"]["max_dip"]]]),
                                                                           a.o.allow_wiped, a.o.max_dip)[0])
        figures(row, r["s"], r["h"], None)
        row.update(neighbours=np.nan, neighbours_of=np.nan, neighbour_objective=np.nan,
                   overrides=json.dumps(r["overrides"], sort_keys=True))
        rows.append(row)
    df = pd.DataFrame(rows)
    whole = ("rank", "round", "months", "positive", "baskets", "wiped_blocks", "neighbours", "neighbours_of")
    for col in df.columns:
        if col in whole or (col.startswith("holdout_") and col[len("holdout_"):] in whole):
            df[col] = pd.array([None if not np.isfinite(v) else int(v) for v in df[col].astype(float)], dtype="Int64")
        elif col in _FIGURES or col.startswith("holdout_") or col == "neighbour_objective":
            df[col] = df[col].astype(float).round(4)
    return df


def month_names(a: Analysis) -> List[str]:
    """Column names of monthly.csv: the month, marked when it is held out or covers only part of a month."""
    return [m.label + (" hold-out" if a.hold[m.block] else "") + ("" if m.full else " partial") for m in a.period.months]


def monthly_frame(a: Analysis) -> pd.DataFrame:
    """Settings x months: net P/L of one unit, in the order of trials.csv."""
    names = month_names(a)
    rows = [[rank if a.ok[i] else "", "", a.keys[i]] + list(a.table.pnl[a.rows[i]]) for rank, i in enumerate(a.order, 1)]
    rows += [["", r["name"], r["key"]] + list(a.ref_table.pnl[j]) for j, r in enumerate(a.refs)]
    return pd.DataFrame(rows, columns=["rank", "name", "key"] + names)


def _selection_window(a: Analysis) -> Tuple[str, str]:
    blocks = [a.period.blocks[i] for i in a.sel.blocks]
    return _when(blocks[0].start), _when(blocks[-1].end)


def believe(a: Analysis) -> Tuple[str, List[str], Dict[str, str]]:
    """
    The summary of the report in plain words: a headline, one line per piece of evidence, and for
    each test "pass", "unclear" or "fail".
    """
    o, unit = a.o, a.period.unit
    checks: Dict[str, str] = {}
    if not a.keys:
        return "**Nothing to judge yet:** no setting has been run on all the selection blocks.", [], checks
    b = a.best
    if b < 0:
        wiped, deep = int((a.s["wiped_blocks"] > 0).sum()), int((a.s["max_dip"] > o.max_dip).sum()) if o.max_dip > 0 else 0
        return (f"**No setting can be recommended.** None of the {len(a.keys):,} settings meets the account limits on the "
                f"selection {unit}s: {wiped:,} wiped the replayed {o.account:,.0f} USD account in at least one block"
                + (f", {deep:,} stood more than {o.max_dip:,.0f} USD below its start" if o.max_dip > 0 else "")
                + ". The tables below rank them regardless.", [], checks)
    s = {k: float(v[b]) for k, v in a.s.items()}
    months = int(s["months"])
    lines = [f"**On the {unit}s it was chosen on.** The best setting made {_m(s['mean'])} USD a {unit} on average over "
             f"{months} {unit}s, standard error {_n(s['se'], 1)}: a lower bound of {_m(s['lcb'])}. {int(s['positive'])} of "
             f"{months} {unit}s were positive; {int(s['baskets']):,} baskets closed, the worst at {_m(s['worst_basket'])}."]
    if a.haircut:
        hc = a.haircut
        tried = f"{hc['pool']:,} eligible settings" + (f" (and {hc['extra']:,} tried elsewhere)" if hc["extra"] else "")
        checks["luck"] = "pass" if hc["p_all"] < P_LUCK_MAX else "unclear" if hc["p_all"] < 0.25 else "fail"
        lines.append(f"**Luck.** It is the best of {tried}. If none of them had any edge, the one picked the same way "
                     f"would still show about {_m(hc['null_mean'])} a {unit} (below {_m(hc['null_mean_p95'])} in 95% of such "
                     f"searches), and {_pc(hc['p_all'])} of such searches reach the objective found here. "
                     + {"pass": "Luck alone rarely does this well.", "unclear": "Luck alone does this well fairly often.",
                        "fail": "This is what the best of that many edgeless settings looks like."}[checks["luck"]])
    if a.pbo:
        c = a.pbo
        checks["halves"] = ("pass" if c["pbo"] < PBO_MAX and c["oos_mean"] > 0 else
                            "fail" if c["pbo"] >= 0.5 or c["oos_mean"] <= 0 else "unclear")
        lines.append(f"**Half and half.** Over {c['splits']:,} ways of splitting the blocks into two halves, the best setting of "
                     f"one half ranked below the median on the other half in {_pc(c['pbo'])} of them (0% is ideal, 50% is what "
                     f"noise gives). It averaged {_m(c['is_mean'])} a {unit} on the half it was chosen on and {_m(c['oos_mean'])} "
                     f"on the other, where it lost money in {_pc(c['oos_loss'])} of the splits"
                     + (f" and wiped the replayed account in {_pc(c['oos_wiped'])}" if c["oos_wiped"] > 0 else "") + ".")
    if a.wf:
        w = a.wf
        checks["walk-forward"] = "pass" if w["mean"] - w["se"] > 0 else "fail" if w["mean"] <= 0 else "unclear"
        lines.append(f"**Walk-forward.** Choosing again after every block from the earlier {unit}s only, and trading the next "
                     f"block, made {_m(w['total'])} over {w['n']} {unit}s: {_m(w['mean'])} a {unit}, standard error "
                     f"{_n(w['se'], 1)}, {w['positive']} of {w['n']} positive. The settings chosen had averaged "
                     f"{_m(w['train_mean'])} on the {unit}s they were chosen on."
                     + (f" The replayed account was wiped in {w['wiped_steps']} of those blocks." if w["wiped_steps"] else ""))
    if np.isfinite(a.nb["n"][b]) and a.nb["n"][b] >= 2:
        avg, own = float(a.nb["objective"][b]), s["objective"]
        checks["neighbours"] = "pass" if avg > 0 and avg >= PLATEAU_MIN * own else "fail" if avg <= 0 else "unclear"
        lines.append(f"**Neighbours.** {int(a.nb['n'][b])} of the {int(a.nb['of'][b])} settings one step away were run: they "
                     f"average an objective of {_m(avg)} against its own {_m(own)}, and {int(a.nb['positive'][b])} of them "
                     f"are positive. "
                     + {"pass": "It sits on a plateau.", "unclear": "It stands well above its neighbours.",
                        "fail": "It is a spike: the settings around it do not work."}[checks["neighbours"]])
    if len(a.ho.blocks) and np.isfinite(a.h["months"][b]):
        h = {k: float(v[b]) for k, v in a.h.items()}
        if np.isfinite(h["mean"]):
            checks["hold-out"] = ("fail" if h["mean"] <= 0 or h["wiped_blocks"] > 0 else
                                  "pass" if h["lcb"] > 0 else "unclear")
            lines.append(f"**Hold-out.** On the {int(h['months'])} held-out {unit}s, which played no part in choosing, it made "
                         f"{_m(h['mean'])} a {unit} (standard error {_n(h['se'], 1)}), {_m(h['total'])} in all, worst block "
                         f"{_m(h['worst_block'])}; account replay: {_account(h['wiped_blocks'], h['max_dip'])}.")
    if s["baskets"] < MIN_BASKETS:
        lines.append(f"**Small sample.** {int(s['baskets'])} baskets is too few to tell a small edge from none.")
    if s["lcb"] <= 0:
        who = f"Even the best of the {len(a.keys):,} settings" if len(a.keys) > 1 else "The one setting run"
        head = (f"**No edge in this space.** {who} is not reliably positive on the {unit}s it was chosen on "
                f"(lower bound {_m(s['lcb'])} USD a {unit}).")
    else:
        failed = [k for k, v in checks.items() if v == "fail"]
        unclear = [k for k, v in checks.items() if v == "unclear"]
        passed = [k for k, v in checks.items() if v == "pass"]
        if not failed and not unclear and len(passed) >= 3 and "hold-out" in passed:
            head = ("**Holds up on every test run here, the held-out months included.** That is as much as a backtest can "
                    "say; the next test is a demo account, not more searching.")
        elif not failed and not unclear and len(passed) >= 3:
            head = (f"**Holds up on the {unit}s it was chosen on.** It passes every test that needs no held-out data. The "
                    f"next step is to confirm it once on {unit}s that played no part in choosing (`--holdout-from` / "
                    f"`--holdout-to`), not more searching.")
        elif "luck" in failed and ("halves" in failed or "walk-forward" in failed):
            head = (f"**Probably overfitted.** The best setting looks good on the {unit}s it was chosen on, and that is what "
                    f"the best of this many settings looks like; choosing on past data did not carry over.")
        else:
            said = []
            if passed:
                said.append("passes " + ", ".join(passed))
            if unclear:
                said.append("is unclear on " + ", ".join(unclear))
            if failed:
                said.append("fails " + ", ".join(failed))
            head = f"**Not proven.** The best setting {'; '.join(said)}. Treat the result as a lead, not as an edge."
    return head, lines, checks


def report_md(a: Analysis) -> str:
    """report.md: what was tried, the top settings with selection and hold-out side by side, and what to believe."""
    o, sp, per, unit = a.o, a.space, a.period, a.period.unit
    held = len(a.ho.blocks) > 0
    head, lines, _ = believe(a)
    sel_m = [per.months[i] for i in a.sel.months]
    ho_m = [per.months[i] for i in a.ho.months]
    short = [m.label for m in per.months if not m.full]
    origins: Dict[str, int] = {}
    for rec in a.settings:
        origins[rec["origin"]] = origins.get(rec["origin"], 0) + 1
    span = lambda ms: f"{ms[0].label} … {ms[-1].label}" if len(ms) > 1 else ms[0].label if ms else "none"
    L: List[str] = [f"# Optimiser report: `{sp.name}` on {o.symbol}", ""]
    if sp.description:
        L += [sp.description, ""]
    facts = [
        ["Period", f"{_when(per.start)} → {_when(per.end)} in {len(per.blocks)} blocks of {o.block}"],
        ["Chosen on", f"{len(sel_m)} {unit}s ({span(sel_m)})"],
        ["Held out", f"{len(ho_m)} {unit}s ({span(ho_m)}), never used to choose" if held else
         "nothing: add `--holdout-from` / `--holdout-to` to keep blocks out of the choice"],
        ["Settings", f"{len(a.keys):,} run (" + ", ".join(f"{n:,} {k}" for k, n in origins.items()) + f") of "
         f"{sp.size():,} raw combinations in the space"
         + (f"; {a.incomplete:,} more are stored but not yet run on every selection block" if a.incomplete else "")
         + (f"; {a.earlier:,} others were tried in earlier runs kept in this directory" if a.earlier else "")
         + (f"; {o.also_tried:,} tried elsewhere (`--also-tried`)" if o.also_tried else "")],
        ["Objective", {"lcb": f"`lcb`: mean net per {unit} minus one standard error", "mean": f"`mean`: mean net per {unit}",
                       "median": f"`median`: median net per {unit}", "sharpe": f"`sharpe`: mean net per {unit} over its standard deviation",
                       "worst_block": "`worst_block`: net of the worst block"}[o.objective]],
        ["Not eligible", ("nothing is excluded for wiping the account" if o.allow_wiped else
                          f"a setting that wipes the replayed {o.account:,.0f} USD account in any selection block")
         + (f", or takes it more than {o.max_dip:,.0f} USD below its start" if o.max_dip > 0 else "")
         + f" ({int((~a.ok).sum()):,} of {len(a.keys):,})"],
        ["Figures", f"USD for one fixed 0.01-lot unit on the per-second series, per {unit}, unless they say \"account\""],
    ]
    if short:
        facts.append(["Shown only", f"{', '.join(short)}: less than half a {unit} inside the period, in monthly.csv but in no statistic"])
    if a.stamp:
        facts.append(["Build", f"engine {a.stamp.get('engine')}, live rules {a.stamp.get('live')}, space {a.stamp.get('space')}, "
                               f"written {time.strftime('%Y-%m-%d %H:%M')}"])
    L += [_md(["", ""], facts), ""]
    L += ["## What to believe", "", head, ""] + [f"- {x}" for x in lines] + [""]
    for note in a.notes:
        L += [f"> Note: {note}", ""]
    if not a.keys:
        return "\n".join(L) + "\n"

    # ── the top settings ──
    shown = list(a.order[: o.top])
    rank = {int(i): k for k, i in enumerate(a.order, 1)}
    tag = lambda i: f"{rank[int(i)]}" if a.ok[i] else f"({rank[int(i)]})"
    L += [f"## The top {len(shown)} settings", "",
          f"Ranked by the objective on the selection {unit}s only. A number in brackets marks a setting that is not eligible.", ""]
    L += [_md(["#", "key"] + [p.name for p in sp.params] + ["neighbours run", "their objective"],
              [[tag(i), f"`{a.keys[i]}`"] + [_show(a.settings[i]["values"][p.name]) if p.name in a.settings[i]["values"] else "–"
                                              for p in sp.params]
               + [f"{_n(a.nb['n'][i])} of {_n(a.nb['of'][i])}", _m(a.nb["objective"][i])] for i in shown]), ""]
    cols = ["#", f"mean / {unit}", "± SE", "lower bound", "worst block", f"{unit}s up", f"baskets / {unit}", "worst basket", "account"]
    if held:
        cols += [f"held out: mean / {unit}", "± SE", "worst block", "account"]

    def line(label: str, s: Dict[str, float], h: Dict[str, float]) -> list:
        row = [label, _m(s["mean"]), _n(s["se"], 1), _m(s["lcb"]), _m(s["worst_block"]),
               f"{_n(s['positive'])} of {_n(s['months'])}", _n(s["baskets_per_month"], 1), _m(s["worst_basket"]),
               _account(s["wiped_blocks"], s["max_dip"])]
        if held:
            row += [_m(h["mean"]), _n(h["se"], 1), _m(h["worst_block"]), _account(h["wiped_blocks"], h["max_dip"])]
        return row

    body = [line(tag(i), {k: float(v[i]) for k, v in a.s.items()}, {k: float(v[i]) for k, v in a.h.items()}) for i in shown]
    body += [line(f"{r['name']} (reference)", r["s"], r["h"]) for r in a.refs]
    L += ["### Selection" + (" and hold-out, side by side" if held else ""), "", _md(cols, body), "",
          f"\"account\" is the replay of the same baskets on {o.account:,.0f} USD with the bot's unit rule, a fresh account in "
          f"every block: the deepest it stood below its start, or in how many blocks it was wiped. References are named in "
          f"the space file (overrides on the live settings) and are never candidates.", ""]
    if held and len(a.looks) > 1:
        L += [f"This hold-out has now been reported {len(a.looks)} times in this directory (first on {a.looks[0]['time']}), each "
              f"time with other settings in front of it. Every look after the first makes it less of a hold-out.", ""]
    digits = 0 if np.nanmax(np.abs(a.table.net[a.rows[shown]])) >= 100 else 1
    blocks = [f"{_when(b.start)} →" + (" (held out)" if a.hold[b.index] else "") for b in per.blocks]
    L += ["### Block by block", "",
          _md(["#"] + blocks, [[tag(i)] + [_m(x, digits) for x in a.table.net[a.rows[i]]] for i in shown]
              + [[f"{r['name']} (reference)"] + [_m(x, digits) for x in a.ref_table.net[j]] for j, r in enumerate(a.refs)]), "",
          "Net of each block, named by the day it starts. A result that comes from one block is one event, not an edge.", ""]

    # ── more than luck? ──
    L += ["## Is the best result more than luck?", ""]
    if a.haircut:
        hc = a.haircut
        L += [_md(["", f"mean / {unit}", "objective"],
                  [["the best setting", _m(hc["mean"]), _m(hc["objective"])],
                   [f"the best of {hc['pool']:,} settings without any edge, on average", _m(hc["null_mean"]), _m(hc["null_objective"])],
                   ["… 95% of the time below", _m(hc["null_mean_p95"]), ""],
                   [f"… if the {hc['pool'] + hc['extra']:,} settings were unrelated to each other", _m(hc["independent"]), ""]]), "",
              f"Searches without any edge that reach the objective found here: **{_pc(hc['p_all'])}**"
              + (f" ({_pc(hc['p'])} before allowing for the {hc['extra']:,} settings tried elsewhere)" if hc["extra"] else "")
              + f". The settings are alike: they spread their best results like about {_n(hc['n_eff'])} unrelated ones. "
              f"({hc['n_boot']:,} resamples of the {unit}s, every setting with its own average taken away.)", ""]
    else:
        L += [f"Not computed: it needs at least two full {unit}s and one eligible setting.", ""]

    # ── overfitting probability ──
    pool = (f"Chosen among the {a.sample:,} settings of the sample. The {len(a.keys) - a.sample:,} settings added by refinement "
            f"are left out here: what to refine was decided by looking at every selection {unit}."
            if a.sample < len(a.keys) else f"Chosen among all {a.sample:,} settings.")
    L += ["## Does choosing on one half work on the other?", ""]
    if a.pbo:
        c = a.pbo
        L += [pool, "", _md(["", ""],
                  [["Splits of the blocks into two halves",
                    f"{c['splits']:,}" + (f" of {c['of']:,} (sampled)" if c["of"] > c["splits"] + c["skipped"] else "")],
                   ["Best of one half below the median of the other (probability of overfitting)", f"**{_pc(c['pbo'])}**"],
                   ["Its typical rank on the other half (0% worst, 100% best)", _pc(c["rank_median"])],
                   [f"Its mean / {unit} on the half it was chosen on", _m(c["is_mean"])],
                   [f"Its mean / {unit} on the other half", _m(c["oos_mean"])],
                   ["Splits in which it lost money on the other half", _pc(c["oos_loss"])],
                   ["Splits in which the replayed account was wiped on the other half", _pc(c["oos_wiped"])]]), ""]
        if c["splits"] < 30:
            L += [f"With {len(a.sel.blocks)} blocks there are only {c['splits']} splits, so this percentage moves in coarse steps; "
                  f"shorter blocks (`--block 1mo`) give more.", ""]
    else:
        L += [f"Not computed: it needs at least two blocks with full {unit}s and two settings.", ""]

    # ── walk-forward ──
    L += ["## Walk-forward: choosing with past data only", ""]
    if a.wf:
        w = a.wf
        L += [pool, ""]
        rows, digits = [], 0 if np.abs(w["pnl"]).max() >= 100 else 1
        for st in w["steps"]:
            blk = per.blocks[a.sel.blocks[st["block"]]]
            who = f"#{tag(st['chosen'])} `{a.keys[st['chosen']]}`" if st["chosen"] >= 0 else "none eligible: stayed out"
            rows.append([_when(blk.start), who, _m(st["train_objective"]), _m(st["train_mean"]), blk.label,
                         " ".join(_m(x, digits) for x in st["pnl"]), _m(float(st["pnl"].sum()), digits),
                         "wiped" if st["wiped"] else ""])
        L += [_md(["chosen on everything before", "setting chosen", "its objective then", f"its mean / {unit} then",
                   "block traded", f"net by {unit}", "together", "account"], rows), ""]
        comp = [["re-chosen after every block (out of sample)", _m(w["mean"]), _n(w["se"], 1), _m(w["total"])],
                [f"the final best setting on the same {unit}s (hindsight: they helped choose it)", _m(w["hindsight_mean"]), "", ""],
                [f"the average setting of the sample on the same {unit}s", _m(w["average_mean"]), "", ""]]
        comp += [[f"{name} (reference) on the same {unit}s", _m(v), "", ""] for name, v in w.get("references", {}).items()]
        L += [_md([f"over the {w['n']} {unit}s traded", f"mean / {unit}", "± SE", "total"], comp), ""]
    else:
        L += [f"Not computed: it needs at least two blocks with full {unit}s.", ""]

    # ── stability ──
    L += ["## Stability", "", "### Average by parameter value", ""]
    if len(a.params):
        cols = ["parameter", "value", "settings", "average objective", f"average mean / {unit}", "with a positive mean", "eligible"]
        if held:
            cols.append(f"held out: average mean / {unit}")
        rows = []
        for _, r in a.params.iterrows():
            row = [r["parameter"], _show(r["value"]), int(r["settings"]), _m(r["objective"]), _m(r["mean"]),
                   _pc(r["positive"]), _pc(r["eligible"])]
            rows.append(row + ([_m(r["holdout_mean"])] if held else []))
        L += [_md(cols, rows), "",
              "Over the settings of the grid or random sample that contain the value (refinement crowds around the best and is "
              "left out; so is a setting in which a condition switched the parameter off). A value that is good on average "
              "over everything it was combined with is worth more than one good row.", ""]
    else:
        L += ["No grid or random sample in this run.", ""]
    if held and a.carry:
        c = a.carry
        L += [f"### Does the ranking carry over to the held-out {unit}s?", "",
              _md(["", ""], [["Settings run on both", f"{c['n']:,}"],
                             [f"Rank correlation: objective on the selection {unit}s against mean on the held-out {unit}s",
                              f"{c['spearman']:+.2f}"],
                             [f"Best tenth by the selection objective ({c['top_n']}): held-out mean / {unit}", _m(c["top_mean"])],
                             ["… of them positive there", _pc(c["top_positive"])],
                             [f"All settings: held-out mean / {unit}", _m(c["all_mean"])],
                             ["… of them positive there", _pc(c["all_positive"])]]), ""]

    # ── validation ──
    if a.validation is not None and len(a.validation):
        L += _validation_md(a)

    # ── reproduce ──
    L += ["## Reproduce", ""]
    if a.best >= 0:
        start, end = _selection_window(a)
        ov = a.settings[a.best]["overrides"]
        last = per.blocks[a.sel.blocks[-1]]
        L += ["The best setting on the real account over the selection period (one run, the unit stepping with the balance):", "",
              "```", run_command(o.symbol, start, end, ov, a.live_root), "```", "",
              f"Its last selection block exactly as measured here (stored net {_m(float(a.table.net[a.rows[a.best], last.index]), 2)}):", "",
              "```", run_command(o.symbol, *last.window, ov, a.live_root, fixed_unit=True), "```", ""]
    L += ["Files next to this report: `trials.csv` (every setting), `monthly.csv` (settings x months), `best.json`, "
          "`evaluations.jsonl` (raw results; the same command continues an interrupted run). "
          "How to read all of this: `backtesting/OPTIMISER.md`.", ""]
    return "\n".join(L) + "\n"


def _validation_md(a: Analysis) -> List[str]:
    v, o = a.validation, a.o
    dd = "max_dd_pct"
    L = ["## The short list on raw ticks", "",
         f"Every tick replayed, {v['seed'].nunique()} random loop timings per block, the real {o.account:,.0f} USD account with the "
         f"live unit rule (a fresh account in every block). One run of a block is one path; the spread over timings is part "
         f"of what a setting is worth.", ""]
    for role in ("selection", "hold-out"):
        part = v[v["role"] == role]
        if not len(part):
            continue
        blocks = list(dict.fromkeys(part["window"]))
        digits = 0 if part["net_profit"].abs().max() >= 100 else 1
        rows = []
        for name, g in part.groupby("setting", sort=False):
            med = g.groupby("window")["net_profit"].median()
            rows.append([name] + [_m(med.get(w, np.nan), digits) for w in blocks]
                        + [_m(float(med.mean()), digits), f"{int((g['net_profit'] < 0).sum())} of {len(g)}",
                           f"{int(g['stopped_out'].astype(bool).sum())} of {len(g)}",
                           f"{g[dd].median():.1f}% / {g[dd].max():.1f}%", _m(float(g['largest_loss'].min()), digits)])
        L += [f"### {role.capitalize()} blocks (median net of the account per block, USD)", "",
              _md(["setting"] + blocks + ["average block", "runs that lost", "stopped out", "max drawdown median / worst",
                                          "worst basket"], rows), ""]
    return L


def best_json(a: Analysis) -> dict:
    """best.json: the top setting, how to run it, and the figures the report words its summary from."""
    o, per = a.o, a.period
    head, lines, checks = believe(a)
    clean = lambda d: {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in d.items()}
    out: Dict[str, Any] = {
        "space": a.space.name, "symbol": o.symbol, "objective": o.objective, "written": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stamp": a.stamp,
        "period": {"start": _when(per.start), "end": _when(per.end), "block": o.block, "slice": o.slice,
                   "selection_months": [per.months[i].label for i in a.sel.months],
                   "holdout_months": [per.months[i].label for i in a.ho.months]},
        "constraints": {"allow_wiped": o.allow_wiped, "max_dip": o.max_dip, "account": o.account},
        "settings_run": len(a.keys), "settings_eligible": int(a.ok.sum()), "settings_tried_earlier": a.earlier,
        "also_tried": o.also_tried, "verdict": head.replace("**", ""), "evidence": [x.replace("**", "") for x in lines],
        "checks": checks, "best": None,
    }
    for name, d in (("haircut", a.haircut), ("overfitting", a.pbo), ("walk_forward", a.wf), ("carry_over", a.carry)):
        if d:
            out[name] = clean({k: v for k, v in d.items() if isinstance(v, (int, float, str, bool))})
    if a.best >= 0:
        b, rec = a.best, a.settings[a.best]
        start, end = _selection_window(a)
        last = per.blocks[a.sel.blocks[-1]]
        out["best"] = {
            "key": a.keys[b], "values": rec["values"], "overrides": rec["overrides"], "origin": rec["origin"],
            "run": run_command(o.symbol, start, end, rec["overrides"], a.live_root),
            "run_last_block": run_command(o.symbol, *last.window, rec["overrides"], a.live_root, fixed_unit=True),
            "last_block_net": float(a.table.net[a.rows[b], last.index]),
            "selection": clean({k: float(v[b]) for k, v in a.s.items()}),
            "holdout": clean({k: float(v[b]) for k, v in a.h.items()}) if len(a.ho.blocks) else None,
            "neighbours": clean({k: float(v[b]) for k, v in a.nb.items()}),
        }
    out["references"] = [{"name": r["name"], "key": r["key"], "overrides": r["overrides"], "selection": clean(r["s"]),
                          "holdout": clean(r["h"]) if len(a.ho.blocks) else None} for r in a.refs]
    return out


def _record_look(a: Analysis, out: Path) -> List[dict]:
    """
    Keep count of how often a hold-out has been looked at: every report that shows held-out
    figures for another short list, another set of settings or another hold-out adds an entry to
    ``holdout_looks.json``. A hold-out that is consulted again and again while the space is being
    changed slowly turns into selection data; the report says how often it has happened.
    """
    path = out / "holdout_looks.json"
    try:
        looks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        looks = []
    shown = [a.keys[i] for i in a.top() if np.isfinite(a.h["months"][i])]
    if not len(a.ho.blocks) or not shown:
        return looks
    seen = [a.stamp.get("space"), [a.period.blocks[i].id for i in a.ho.blocks], len(a.keys), shown]
    what = hashlib.sha1(json.dumps(seen).encode()).hexdigest()[:12]
    if all(x.get("what") != what for x in looks):
        looks.append({"time": time.strftime("%Y-%m-%d %H:%M"), "what": what, "settings": len(a.keys),
                      "holdout": [a.period.blocks[i].label for i in a.ho.blocks]})
        path.write_text(json.dumps(looks, indent=1), encoding="utf-8")
    return looks


def write_outputs(a: Analysis, out: Path) -> Dict[str, Path]:
    """trials.csv, monthly.csv, best.json and report.md, from the analysis alone."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    a.looks = _record_look(a, out)
    paths = {k: out / k for k in ("trials.csv", "monthly.csv", "best.json", "report.md")}
    trials_frame(a).to_csv(paths["trials.csv"], index=False)
    monthly_frame(a).to_csv(paths["monthly.csv"], index=False)
    paths["best.json"].write_text(json.dumps(best_json(a), indent=2, default=str), encoding="utf-8")
    paths["report.md"].write_text(report_md(a), encoding="utf-8")
    return paths


# ───────────────────────────── validation on raw ticks ─────────────────────────────

def validation(a: Analysis, out: Path, stamps: Sequence[str], log: Callable[[str], None] = _log,
               run: bool = True) -> Optional[pd.DataFrame]:
    """
    The short list (the best ``validate_top`` eligible settings and every reference) on raw ticks:
    each block under several random loop timings, on the real account with the live unit rule
    (``robustness.timing_ensemble``). Finished blocks are kept in ``validation.csv`` and not run
    again; with ``run`` False nothing is run and what is stored is returned.

    Rows: setting x block x loop timing, with ``setting`` (its place in the ranking or the name of
    the reference), ``role`` (selection / hold-out) and the metrics of ``metrics.score_row``.
    """
    from . import experiments as E
    from .analysis import robustness

    o, per = a.o, a.period
    names: Dict[str, str] = {}
    short: List[Tuple[str, dict]] = []
    for label, key, ov in ([(f"#{k}", a.keys[i], a.settings[i]["overrides"]) for k, i in enumerate(a.top(o.validate_top), 1)]
                           + [(f"{r['name']} (reference)", r["key"], r["overrides"]) for r in a.refs]):
        if key in names:
            names[key] += f" = {label}"
        else:
            names[key] = label
            short.append((key, ov))
    seeds = list(range(1, int(o.validate_seeds) + 1))
    path, side = Path(out) / "validation.csv", Path(out) / "validation.json"
    stamp = {"engine": a.stamp.get("engine"), "live": a.stamp.get("live"), "symbol": o.symbol, "account": float(o.account),
             "jitter_ms": int(robustness.ENSEMBLE_JITTER_MS)}
    have = pd.DataFrame()
    if path.exists() and side.exists():
        try:
            if json.loads(side.read_text(encoding="utf-8")) == stamp:
                have = pd.read_csv(path, dtype={"key": str, "block": str, "data": str})
        except (OSError, ValueError):
            pass
    cfg = E.live_config(o.symbol, a.live_root or REPO_ROOT, initial_balance=float(o.account))
    for b in per.blocks:
        done: Set[str] = set()
        if len(have):
            mine = have[(have["block"] == b.id) & (have["data"] == stamps[b.index]) & have["seed"].isin(seeds)]
            per_key = mine.groupby("key")["seed"].nunique()
            done = set(per_key[per_key >= len(seeds)].index)
        todo = [(key, ov) for key, ov in short if key not in done]
        if not todo or not run:
            continue
        log(f"  raw ticks {b.label}: {len(todo)} settings x {len(seeds)} loop timings")
        df = robustness.timing_ensemble(cfg, {b.label: b.window}, seeds=seeds, n_jobs=max(1, min(int(o.jobs or 1), 3)),
                                        overrides=[ov for _, ov in todo], override_labels=[{"key": key} for key, _ in todo])
        df["block"], df["data"] = b.id, stamps[b.index]
        have = pd.concat([have, df], ignore_index=True) if len(have) else df
        Path(out).mkdir(parents=True, exist_ok=True)
        have.to_csv(path, index=False)
        side.write_text(json.dumps(stamp), encoding="utf-8")
    if not len(have):
        return None
    now = {b.id: stamps[b.index] for b in per.blocks}
    current = np.array([now.get(blk) == d for blk, d in zip(have["block"], have["data"])], bool)
    keep = have[have["key"].isin(names) & have["seed"].isin(seeds) & current]
    keep = keep.drop_duplicates(subset=["key", "block", "seed"], keep="last").copy()
    if not len(keep):
        return None
    role = {b.id: "hold-out" if a.hold[b.index] else "selection" for b in per.blocks}
    place = {key: k for k, (key, _) in enumerate(short)}
    when = {b.id: b.index for b in per.blocks}
    keep["setting"], keep["role"] = keep["key"].map(names), keep["block"].map(role)
    keep = keep.assign(_s=keep["key"].map(place), _b=keep["block"].map(when)).sort_values(["_s", "_b", "seed"])
    return keep.drop(columns=["_s", "_b"]).reset_index(drop=True)


# ───────────────────────────── one run ─────────────────────────────

def optimise(o: Options, log: Callable[[str], None] = _log) -> Dict[str, Any]:
    """
    One run of the optimiser: sample the space, run what is not stored yet on the selection
    blocks, refine around the best, run the held-out blocks, then rank, diagnose and write the
    output files. Every step is skipped for what the store already holds, so the same call after
    an interruption continues it and a second call computes nothing.

    Returns ``out`` (the directory), ``paths`` (the files written), ``evaluated`` (backtests run
    by this call), ``settings``, ``best`` (key of the top setting or None), ``verdict`` and the
    ``analysis`` itself.
    """
    from . import experiments as E

    if o.objective not in OBJECTIVES:
        raise ValueError(f"unknown objective {o.objective!r}; known: {', '.join(OBJECTIVES)}")
    if o.sampler not in ("random", "grid", "stored"):
        raise ValueError(f"unknown sampler {o.sampler!r}; known: random, grid, stored")
    if o.symbol not in SYMBOLS:
        raise ValueError(f"unknown symbol {o.symbol!r}; known: {', '.join(SYMBOLS)}")
    if _ts(o.start) < _ts(RESERVED_BEFORE) and not o.allow_reserved:
        raise ValueError(f"the period starts before {RESERVED_BEFORE}. That history is reserved for one final test of one "
                         f"frozen setting; searching on it would use it up. --allow-reserved lifts the guard.")
    live_root = Path(o.live_root).expanduser().resolve() if o.live_root else REPO_ROOT
    live = E.live_config(o.symbol, live_root, fixed_units=1, initial_balance=E.SWEEP_BALANCE)
    space = Space.load(o.space, live=live)
    period = make_period(o.start, o.end, o.block, o.slice)
    hold = holdout_mask(period, o.holdout_from, o.holdout_to)
    if not any(period.months[m].full for b, held in zip(period.blocks, hold) if not held for m in b.months):
        raise ValueError(f"the blocks to choose on hold no full {period.unit}: the statistics need at least one "
                         f"(--slice {o.slice}; a shorter slice, or a longer period)")
    note = check_data(o.symbol, period)
    # how far back a block reads: the engine warms every timeframe up on DEFAULT_WARM_BARS bars of history
    from .engine.fast import DEFAULT_WARM_BARS
    slowest = max(TF_SECONDS[tf] for tf in space.timeframes())
    stamps = data_stamps(o.symbol, period, pd.Timedelta(seconds=DEFAULT_WARM_BARS * slowest * 1.7) + pd.Timedelta(days=7))
    out = Path(o.out).expanduser() if o.out else RESULTS_DIR / f"{space.name}_{o.symbol}"
    stamp = {"format": STORE_FORMAT, "space": space.fingerprint(), "symbol": o.symbol, "engine": E.engine_fingerprint(),
             "live": E.live_fingerprint(live_root), "account": float(o.account)}
    store = Store(out, stamp, log, read_only=o.report_only)
    refs = [(config_key(live.replace(**ov)), ov) for ov in space.references.values()]
    sel_blocks, hold_blocks = [int(i) for i in np.flatnonzero(~hold)], [int(i) for i in np.flatnonzero(hold)]
    log(f"optimise {space.name} on {o.symbol}: {_when(period.start)} → {_when(period.end)} in {len(period.blocks)} blocks "
        f"({len(sel_blocks)} to choose on, {len(hold_blocks)} held out) · engine {stamp['engine']} · {out}")
    if note:
        log("note: " + note)
    now = {b.id: stamps[b.index] for b in period.blocks}
    moved = {block for (_, block), row in store.evals.items() if block in now and row.get("data") != now[block]}
    changed = [b.label for b in period.blocks if b.id in moved]
    if changed:
        log(f"the tick history under or before {len(changed)} of the {len(period.blocks)} blocks has changed since their "
            f"results were stored ({'; '.join(changed)}): those results are not used, the blocks are computed again")
    timeframes: Dict[str, List[str]] = {"": space.timeframes()}

    def candidates() -> List[Tuple[str, dict]]:
        return [(key, rec["overrides"]) for key, rec in store.settings.items()]

    def tasks(wanted: Sequence[Tuple[str, dict]], blocks: Sequence[int]) -> List[dict]:
        """What is not stored yet, block by block. Every process prepares all timeframes any setting so far reads."""
        wanted = list(dict(wanted).items())
        for key, ov in wanted:
            if key not in timeframes:
                timeframes[key] = live.replace(**ov).timeframes()
        tfs = sorted({tf for v in timeframes.values() for tf in v}, key=TF_SECONDS.get)
        todo = []
        for bi in blocks:
            b = period.blocks[bi]
            start, end = b.window
            edges = period.edges_ms(b)
            todo += [{"key": key, "overrides": ov, "block": b.id, "start": start, "end": end, "edges": edges, "tfs": tfs,
                      "data": stamps[bi]} for key, ov in wanted if store.get(key, b.id, stamps[bi]) is None]
        return todo

    def add(canons: Sequence[Canon], origin: str, round_: int) -> int:
        return sum(store.add_setting(space.key(c), c, space.values(c), space.overrides(c), origin, round_) for c in canons)

    def best_so_far(k: int, max_round: Optional[int] = None) -> List[str]:
        """Keys of the best ``k`` eligible settings on the selection months, among those found up to a refinement round."""
        keys = [key for key, rec in store.settings.items() if max_round is None or rec["round"] <= max_round]
        t, sel = build_table(store, keys, period, stamps), role_of(period, sel_blocks)
        rows = np.flatnonzero(~np.isnan(t.net[:, sel.blocks]).any(axis=1)) if keys else np.zeros(0, int)
        if not len(rows) or not len(sel.months):
            return []
        X = t.pnl[np.ix_(rows, sel.months)]
        ok = eligible(t.wiped[np.ix_(rows, sel.blocks)], t.dip[np.ix_(rows, sel.blocks)], o.allow_wiped, o.max_dip)
        order = ranking(objective(o.objective, X, sel.groups), objective("mean", X, sel.groups), ok)
        return [keys[rows[i]] for i in order[:k] if ok[i]]

    evaluated = 0
    try:
        with Evaluator(live, o.account, o.jobs) as ev:
            if not o.report_only:
                if o.sampler == "grid":
                    fresh = add(space.grid(limit=o.max_grid), "grid", 0)
                    log(f"grid: {len(store.settings):,} settings, {fresh:,} new")
                elif o.sampler == "random":
                    fresh = add(space.random(o.n, o.seed), "random", 0)
                    log(f"stratified random sample (n {o.n}, seed {o.seed}) of {space.size():,} raw combinations: "
                        f"{len(store.settings):,} settings stored, {fresh:,} new")
                if not store.settings:
                    raise ValueError(f"no settings to run: nothing is stored in {out} and the sampler is {o.sampler!r}")
                evaluate(ev, store, tasks(candidates() + refs, sel_blocks), log, "selection blocks: ")
                for r in range(1, int(o.refine_rounds) + 1):
                    around = best_so_far(o.refine_top, max_round=r - 1)
                    fresh = sum(add(space.neighbours(tuple(store.settings[key]["canon"])), "refine", r) for key in around)
                    todo = tasks(candidates(), sel_blocks)
                    log(f"refinement round {r}: {fresh:,} new settings one step from the best {len(around)}")
                    if not todo:
                        break                          # nothing around the best is left untried
                    evaluate(ev, store, todo, log, f"round {r}: ")
                if hold_blocks:
                    held = ([(key, store.settings[key]["overrides"]) for key in best_so_far(o.top)] if o.holdout_top_only
                            else candidates())
                    evaluate(ev, store, tasks(held + refs, hold_blocks), log, "held-out blocks: ")
            evaluated = ev.runs
    finally:
        store.close()
    if evaluated and (E.engine_fingerprint() != stamp["engine"] or E.live_fingerprint(live_root) != stamp["live"]):
        # worker processes import whatever is on disk when they start: the results of this call may mix two builds
        raise RuntimeError("the backtester or the live rules changed on disk while the optimiser was running; start it "
                           "again: the stored results no longer carry the current stamp and are computed afresh")
    a = analyse(space, store, period, hold, stamps, o, stamp, live_root)
    if not a.keys:
        why = (f" (the tick history under or before {len(changed)} of its blocks has changed since their results were "
               f"stored)" if changed else "")
        raise ValueError(f"no setting in {out} has been run on every selection block of this period yet{why}"
                         + (": run without --report-only" if o.report_only else ""))
    if note:
        a.notes.append(note)
    a.validation = validation(a, out, stamps, log, run=bool(o.validate) and not o.report_only)
    paths = write_outputs(a, out)
    head, _, _ = believe(a)
    return {"out": out, "paths": paths, "evaluated": evaluated, "settings": len(a.keys),
            "best": a.keys[a.best] if a.best >= 0 else None, "verdict": head.replace("**", ""), "analysis": a}


# ───────────────────────────── command line ─────────────────────────────

def add_arguments(sp) -> None:
    """The options of ``python -m backtesting optimise``."""
    sp.add_argument("--space", required=True,
                    help="search space: a JSON file, or the name of one in backtesting/spaces/ (v2, ladder, entries)")
    sp.add_argument("--symbol", default="XAUUSDm", choices=list(SYMBOLS))
    sp.add_argument("--start", default=DEV[0], help="inclusive, UTC (default %(default)s: the development period)")
    sp.add_argument("--end", default=DEV[1], help="exclusive, UTC (default %(default)s)")
    sp.add_argument("--block", default="3mo", help="length of the blocks every setting is run on, counted from --start: "
                                                   "3mo, 1mo, 2w, 10d ... (default %(default)s)")
    sp.add_argument("--slice", default="1mo", help="length of the pieces a block's P/L is kept in; the statistics are over "
                                                   "these (default %(default)s: calendar months)")
    sp.add_argument("--holdout-from", default=None, metavar="DATE",
                    help="blocks from here (default: --start) to --holdout-to are never used to choose; they are reported "
                         "next to the selection result. Must be a block boundary")
    sp.add_argument("--holdout-to", default=None, metavar="DATE", help="end of the hold-out (default: --end)")
    sp.add_argument("--holdout-top-only", action="store_true",
                    help="run the held-out blocks for the short list and the references only (saves time; the tables that "
                         "compare all settings across the two periods are then left out)")
    sp.add_argument("--sampler", default="random", choices=["random", "grid", "stored"],
                    help="random: a stratified sample of --n settings (the whole space when it is no larger); grid: every "
                         "setting, refused above --max-grid; stored: no new settings, finish and report what is stored")
    sp.add_argument("--n", type=int, default=200, help="settings in the random sample (default %(default)s)")
    sp.add_argument("--seed", type=int, default=1, help="seed of the sample and of the resampling (default %(default)s)")
    sp.add_argument("--max-grid", type=int, default=2000, help="largest grid the grid sampler accepts (default %(default)s)")
    sp.add_argument("--refine-rounds", type=int, default=2,
                    help="rounds of local refinement: run every setting one step away from the best ones (default %(default)s; 0 = off)")
    sp.add_argument("--refine-top", type=int, default=5, help="how many of the best settings each round refines around (default %(default)s)")
    sp.add_argument("--objective", default="lcb", choices=list(OBJECTIVES),
                    help="what the settings are ranked by on the selection months (default lcb: mean monthly net minus one standard error)")
    sp.add_argument("--allow-wiped", action="store_true", help="keep settings that wipe the replayed account eligible")
    sp.add_argument("--max-dip", type=float, default=1000.0,
                    help="a setting whose replayed account stands more than this many USD below its start in any selection "
                         "block is not eligible (default %(default)s; 0 = no limit)")
    sp.add_argument("--account", type=float, default=2000.0, help="the account the replay uses, USD (default %(default)s)")
    sp.add_argument("--top", type=int, default=10, help="settings shown in the report (default %(default)s)")
    sp.add_argument("--also-tried", type=int, default=0, metavar="N",
                    help="settings tried elsewhere (other spaces, by hand) among which this result was also chosen; the "
                         "haircut for luck allows for them")
    sp.add_argument("--bootstrap", type=int, default=2000, help="resamples behind the haircut (default %(default)s)")
    sp.add_argument("--validate", action="store_true",
                    help="also replay the short list on raw ticks: random loop timings per block, the real account with the live unit rule")
    sp.add_argument("--validate-top", type=int, default=5, help="settings taken to the validation, besides the references (default %(default)s)")
    sp.add_argument("--validate-seeds", type=int, default=8, help="loop timings per block in the validation (default %(default)s)")
    sp.add_argument("--report-only", action="store_true", help="run nothing: rebuild the output files from what is stored")
    sp.add_argument("--jobs", type=int, default=2, help="worker processes; each holds one block of data, about 0.6 GB (default %(default)s)")
    sp.add_argument("--out", default=None, help="output directory (default backtest_results/optimise/<space>_<symbol>)")
    sp.add_argument("--live-root", default=None, metavar="DIR",
                    help="checkout whose constants.py and symbols.json are the live settings (default: this checkout)")
    sp.add_argument("--allow-reserved", action="store_true",
                    help=f"let the period start before {RESERVED_BEFORE} (history reserved for one final test)")


def command(args) -> int:
    """``python -m backtesting optimise``: run, then print where the report is and what it concludes."""
    o = Options(**{f.name: getattr(args, f.name) for f in fields(Options) if hasattr(args, f.name)})
    try:
        res = optimise(o)
    except KeyboardInterrupt:
        print("interrupted: every finished run is saved, the same command continues from there", flush=True)
        return 130
    except (SpaceError, ValueError, RuntimeError) as e:
        raise SystemExit(f"optimise: {e}") from None
    a: Analysis = res["analysis"]
    print(f"\n{res['settings']:,} settings ranked, {res['evaluated']:,} backtests run by this call")
    print(res["verdict"])
    if a.best >= 0:
        values = a.settings[a.best]["values"]
        print("best: " + (", ".join(f"{p.name}={_show(values[p.name])}" for p in a.space.params if p.name in values)
                          or "the base settings of the space"))
    print(f"report: {res['paths']['report.md']}")
    return 0
