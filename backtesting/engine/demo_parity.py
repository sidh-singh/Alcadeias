"""
Parity of a demo branch: its own ``app.py``, replayed on the simulated terminal, against the fast
engine running the design the branch was built from.

    python -m backtesting.engine.demo_parity <demo_root> <SYMBOL> <design> <start> <end> [options]

    <demo_root>  a checkout (or an export) of a demo branch: app.py, strategy.py, indicator.py,
                 mt5_helper.py, constants.py (with the demo contract), symbols.json
    <SYMBOL>     XAUUSDm or BTCUSDm
    <design>     a row of backtest_results/improve/round4/top3_v4_<SYMBOL>_designs.json:
                 "V3-lite", "Top 1", "Top 2", "Top 3" (or "Live")
    <start> <end>  the window, UTC ("2026-11-02 22:00")

The configuration is ``BacktestConfig.live(SYMBOL)`` (this checkout's live constants) with that row's
overrides, which is exactly what the research ran. Then:

1. Static check. The branch's constants.py and symbols.json must hold that design: every constant the
   design sets (``reference.design_constants``; levers that cannot act are skipped), the sizing and the
   trading window. The replay below sets the constants from the design, so this is what ties the result
   to the branch as it will run.
2. Parity. The branch's app.py is replayed by ``reference.run_reference`` on raw ticks and the fast engine
   runs the design on the same ticks with the timing of the existing parity checks (1 s polls, the 0.1 s
   sleep after an order, ``parity.fast_config_for_parity``). Every live poll must agree (signal, scores,
   position, floating profit, unit, and the cooldown state, which pins the pause after a loss), and every
   fill and the final balance. By default a poll where the branch's strategy holds an entry back that the
   kernel holds back at execution (trend, window, ...) is accepted (``--strict-gates`` refuses it); the
   fills must match either way.
3. Isolation (unless ``--plain``). The account is shared, as a demo account is: it holds $10,000, a
   manual position on the symbol and another bot's position, another bot's trades close during the
   window, and this bot itself closed a trade the day before its VIRTUAL_START_DATE. A branch that sizes
   from its own virtual balance and manages its own positions only (its MAGIC) is not affected by any of
   it, so the parity must still be exact. Every order of the bot must carry its MAGIC (closes included:
   on MT5 a closing deal has the magic of the request that closed it) and its comment.

Exit code 0 when all three pass. The Turtle branches (STRATEGY='turtle') have no fast-engine counterpart
and are refused.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

from ..config import FIBO, REPO_ROOT, BacktestConfig, _symbols_json, load_live_constants
from ..data import store
from . import kernels as K
from .fast import SIGNAL_NAMES, prepare, run
from .parity import ParityReport, compare, fast_config_for_parity
from .reference import (CONTRACT_NAMES, MAX_COMMENT_LEN, ReferenceResult, SimMT5, contract_of, design_constants,
                        run_reference)

DESIGNS_DIR = REPO_ROOT / "backtest_results" / "improve" / "round4"

# fields of a demo branch's analysis data recorded at every poll (trace columns x_<key>), shown around a divergence
DIAGNOSTIC_KEYS = ("trend", "trend_signal", "vol_unit_now", "loss_pause_s", "pause_left_s", "last_close_lost",
                   "virtual_balance", "exit_reason")

# what the isolation set-up puts on the shared account
SHARED_ACCOUNT_BALANCE = 10_000.0
FOREIGN_PROFIT = 600.0      # large enough that counting it moves a $2,000 bot to the next unit ($2,500 steps)


# ───────────────────────────── the design ─────────────────────────────

def designs_file(symbol: str) -> Path:
    return DESIGNS_DIR / f"top3_v4_{symbol}_designs.json"


def design_overrides(symbol: str, design: str):
    """(row name, overrides) of ``design`` in the round-4 designs file of ``symbol``. "Top 1" matches the row
    "Top 1: open_weights=...", case and spaces ignored."""
    rows = json.loads(designs_file(symbol).read_text(encoding="utf-8"))
    norm = lambda s: "".join(str(s).split()).lower()
    want = norm(design)
    for name, ov in rows.items():
        if norm(name) == want or norm(name.split(":")[0]) == want:
            return name, dict(ov)
    raise SystemExit(f"no design {design!r} in {designs_file(symbol)}; rows: "
                     f"{', '.join(n.split(':')[0] for n in rows)}")


def design_config(symbol: str, design: str, start, end, **extra) -> BacktestConfig:
    """``BacktestConfig.live(symbol)`` of this checkout with the design's overrides, over [start, end);
    ``extra`` fields are set on top (they win over the design's)."""
    _, ov = design_overrides(symbol, design)
    return BacktestConfig.live(symbol, repo_root=REPO_ROOT, start=str(start), end=str(end)).replace(**{**ov, **extra})


# ───────────────────────────── 1. static check ─────────────────────────────

def _tf(x):
    return None if x is None else str(x).replace("TIMEFRAME_", "")


def _num_eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b) and isinstance(a, bool) == isinstance(b, bool)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)
    return a == b


def _weights_eq(a: dict, b: dict) -> bool:
    a = {_tf(k): float(v) for k, v in (a or {}).items() if float(v) != 0.0}
    b = {_tf(k): float(v) for k, v in (b or {}).items() if float(v) != 0.0}
    return a == b


def static_check(cfg: BacktestConfig, demo_root: Path) -> List[str]:
    """
    Where the branch's constants.py / symbols.json do not hold the design of ``cfg``. Levers that cannot
    act under the design are not compared (the ladder's settings and gate without adds, the RSI levels
    without an RSI-level ladder, the volatility length without a volatility timeframe, the force-close
    threshold with the force-close off).
    """
    c = load_live_constants(demo_root)
    problems: List[str] = []
    try:
        if not contract_of(c):
            return [f"{demo_root}/constants.py defines none of the demo contract ({', '.join(CONTRACT_NAMES[:4])}, ...)"]
    except ValueError as e:
        return [str(e)]
    if str(c.STRATEGY) != "basket":
        return [f"STRATEGY={c.STRATEGY!r}: this branch does not run the basket logic of the designs"]
    want = design_constants(cfg)
    n_adds_want = min(len(want["LADDER_TFS"]), int(want["MAX_ADDS"]))
    n_adds_have = min(len(list(c.LADDER_TFS)), int(c.MAX_ADDS))

    def diff(name, have, wanted):
        problems.append(f"{name}: branch {have!r}, design {wanted!r}")

    for name in ("OPEN_SCORE_WEIGHTS", "FORCE_CLOSE_SCORE_WEIGHTS"):
        if not _weights_eq(getattr(c, name), want[name]):
            diff(name, getattr(c, name), want[name])
    for name in ("ENTRY_S", "ENTRY_AGREE_S", "RSI_LENGTH",
                 "MACD_FAST", "MACD_SLOW", "MACD_SIGNAL", "PEAK_LOOKBACK", "PIVOT_WIDTH", "RSI_PEAK_OB", "RSI_PEAK_OS",
                 "REENTRY_COOLDOWN_SECONDS", "ORDER_COOLDOWN_SECONDS", "MARKET_LOOKBACK_MINUTES",
                 "STOP_LOSS_USD_PER_UNIT", "TARGET_VOL", "STOP_VOL", "VOL_CAP_USD_PER_UNIT", "LOSS_COOLDOWN_S",
                 "VIRTUAL_START_BALANCE"):
        if not _num_eq(getattr(c, name), want[name]):
            diff(name, getattr(c, name), want[name])
    if bool(c.FORCE_CLOSE_ENABLED) != want["FORCE_CLOSE_ENABLED"]:
        diff("FORCE_CLOSE_ENABLED", c.FORCE_CLOSE_ENABLED, want["FORCE_CLOSE_ENABLED"])
    elif want["FORCE_CLOSE_ENABLED"] and not _num_eq(c.FORCE_CLOSE_S, want["FORCE_CLOSE_S"]):
        diff("FORCE_CLOSE_S", c.FORCE_CLOSE_S, want["FORCE_CLOSE_S"])
    for name in ("TREND_TF", "VOL_TF"):
        if _tf(getattr(c, name)) != want[name]:
            diff(name, getattr(c, name), want[name])
    if want["VOL_TF"] is not None and not _num_eq(int(c.VOL_LEN), want["VOL_LEN"]):
        diff("VOL_LEN", c.VOL_LEN, want["VOL_LEN"])
    target_have = c.TARGET_USD_PER_UNIT
    if target_have == "live":
        target_have = getattr(c, "STRATEGY_HEDGE", None)
    target_want = want.get("STRATEGY_HEDGE") if want["TARGET_USD_PER_UNIT"] == "live" else None
    if not _num_eq(target_have, target_want):
        diff("TARGET_USD_PER_UNIT ($ per unit)", target_have, target_want)
    if n_adds_have != n_adds_want:
        diff("ladder adds (min(len(LADDER_TFS), MAX_ADDS))", n_adds_have, n_adds_want)
    elif n_adds_want:
        if [_tf(t) for t in list(c.LADDER_TFS)[:n_adds_want]] != want["LADDER_TFS"][:n_adds_want]:
            diff("LADDER_TFS (the tiers used)", list(c.LADDER_TFS)[:n_adds_want], want["LADDER_TFS"][:n_adds_want])
        if str(c.LADDER_TRIGGER) != want["LADDER_TRIGGER"]:
            diff("LADDER_TRIGGER", c.LADDER_TRIGGER, want["LADDER_TRIGGER"])
        if not _num_eq(c.LADDER_GAP_VOL, want["LADDER_GAP_VOL"]):
            diff("LADDER_GAP_VOL", c.LADDER_GAP_VOL, want["LADDER_GAP_VOL"])
        for name in ("LADDER_S",) + (("RSI_OVERSOLD", "RSI_OVERBOUGHT") if want["LADDER_TRIGGER"] == "rsi_level" else ()):
            if not _num_eq(getattr(c, name), want[name]):
                diff(name, getattr(c, name), want[name])
        mult = lambda m: [float(x) for x in (FIBO if m is None else m)]
        have_m, want_m = mult(c.LADDER_MULTIPLIERS), mult(want["LADDER_MULTIPLIERS"])
        pad = lambda m: m + [m[-1]] * 64
        if pad(have_m)[1:n_adds_want + 1] != pad(want_m)[1:n_adds_want + 1]:
            diff("LADDER_MULTIPLIERS (the adds used)", c.LADDER_MULTIPLIERS, want["LADDER_MULTIPLIERS"])
    # (SLOPE_TIMEFRAMES is not compared: a demo branch adds the timeframes its sections and tiers read at run
    #  time; a missing one would show in the replay as scores that differ)
    sj_path = Path(demo_root) / "symbols.json"
    entries = json.loads(sj_path.read_text(encoding="utf-8")).get("symbols", []) if sj_path.exists() else []
    if not any(e.get("symbol") == cfg.symbol and e.get("is_active", False) for e in entries):
        problems.append(f"symbols.json has no active {cfg.symbol} entry (the bot would not start on it)")
    sj = _symbols_json(cfg.symbol, demo_root)
    for key in ("mtqty", "brake", "step_up_balance", "unit_max_limit", "window_enabled", "window_start_min",
                "window_end_min"):
        if not _num_eq(sj[key], getattr(cfg, key)):
            diff(f"symbols.json {key}", sj[key], getattr(cfg, key))
    return problems


def branch_labels(demo_root: Path) -> dict:
    """What the branch calls itself: DESIGN_NAME, DEMO_BRANCH, MAGIC, the order comment it sends."""
    c = load_live_constants(demo_root)
    comment = getattr(c, "ORDER_COMMENT", None)
    if comment is None and getattr(c, "DEMO_BRANCH", None):
        comment = str(c.DEMO_BRANCH)[:MAX_COMMENT_LEN]
    return dict(design_name=getattr(c, "DESIGN_NAME", None), demo_branch=getattr(c, "DEMO_BRANCH", None),
                magic=getattr(c, "MAGIC", None), comment=comment,
                strategy=getattr(c, "STRATEGY", None), virtual_start_date=getattr(c, "VIRTUAL_START_DATE", None))


def _git(demo_root: Path) -> str:
    try:
        head = subprocess.run(["git", "-C", str(demo_root), "log", "-1", "--format=%h %s"], capture_output=True,
                              text=True, timeout=20).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(demo_root), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=20).stdout.strip()
        return f"{head}{' (+ uncommitted changes)' if dirty else ''}" if head else "not a git checkout"
    except (OSError, subprocess.SubprocessError):
        return "not a git checkout"


# ───────────────────────────── 3. the shared account ─────────────────────────────

def shared_account(cfg: BacktestConfig, magic: int) -> dict:
    """
    ``run_reference`` keywords for an account this bot shares: a larger balance, a manual position and
    another bot's position open on the symbol, another bot's trades (this symbol and another one) closing
    during the window, and a winning trade of this very bot the evening before its virtual start date
    (VIRTUAL_START_DATE is the day the window starts; a win, so no pause follows from it either way).
    """
    start_ms, end_ms = store.to_ms(cfg.start), store.to_ms(cfg.end)
    day0 = (start_ms // 86_400_000) * 86_400_000
    span = max(end_ms - start_ms, 120_000)
    other = "BTCUSDm" if cfg.symbol != "BTCUSDm" else "XAUUSDm"
    before = day0 - 6 * 3_600_000
    history = [
        dict(t_ms=before - 3_600_000, type=SimMT5.DEAL_TYPE_BUY, entry=SimMT5.DEAL_ENTRY_IN, magic=magic,
             volume=cfg.mtqty, price=1.0, position_id=900001, order=900001, comment="own, before the start"),
        dict(t_ms=before, type=SimMT5.DEAL_TYPE_SELL, entry=SimMT5.DEAL_ENTRY_OUT, magic=magic, volume=cfg.mtqty,
             price=1.0, profit=FOREIGN_PROFIT, position_id=900001, order=900002, comment="own, before the start"),
    ]
    scheduled = []
    for k, (sym, mg) in enumerate(((cfg.symbol, magic + 1), (other, magic + 2))):
        t_in, t_out = start_ms + span * (k + 1) // 8, start_ms + span * (k + 2) // 8
        scheduled += [
            dict(t_ms=t_in, type=SimMT5.DEAL_TYPE_SELL, entry=SimMT5.DEAL_ENTRY_IN, magic=mg, volume=0.02, price=1.0,
                 symbol=sym, position_id=910001 + k, order=910001 + k, comment="another bot"),
            dict(t_ms=t_out, type=SimMT5.DEAL_TYPE_BUY, entry=SimMT5.DEAL_ENTRY_OUT, magic=mg, volume=0.02,
                 price=1.0, profit=FOREIGN_PROFIT, symbol=sym, position_id=910001 + k, order=920001 + k,
                 comment="another bot"),
        ]
    positions = [dict(type=SimMT5.ORDER_TYPE_BUY, volume=0.01, magic=0, comment=""),
                 dict(type=SimMT5.ORDER_TYPE_SELL, volume=0.01, magic=magic + 1, comment="another bot")]
    return dict(account_balance=SHARED_ACCOUNT_BALANCE, history=history, positions=positions, scheduled=scheduled)


def isolation_check(ref: ReferenceResult, labels: dict) -> List[str]:
    """What the bot did on the shared account that it should not have."""
    problems = []
    d = ref.deals
    magic, comment = labels.get("magic"), labels.get("comment")
    if magic is None:
        problems.append("the branch defines no MAGIC: its orders cannot be told from anyone else's")
    if len(d):
        foreign = d["foreign"].eq(True) if "foreign" in d else pd.Series(False, index=d.index)
        own = d[~foreign]
        if foreign.any():
            problems.append(f"the bot closed {int(foreign.sum())} position(s) it did not open (a manual one or "
                            f"another bot's)")
        if magic is not None:
            for entry, what in (("in", "opening"), ("out", "closing")):
                part = own[own["entry"] == entry]
                wrong = part[part["magic"].astype(np.int64) != int(magic)]
                if len(wrong):
                    problems.append(f"{len(wrong)} of {len(part)} {what} deals carry magic "
                                    f"{sorted(set(wrong['magic'].astype(int)))} instead of {magic}"
                                    + (" (MT5 gives a closing deal the magic of the close request: the virtual "
                                       "balance would miss the bot's own results)" if entry == "out" else ""))
        if comment is not None:
            part = own[own["entry"] == "in"]
            wrong = part[part["comment"].astype(str) != str(comment)]
            if len(wrong):
                problems.append(f"{len(wrong)} of {len(part)} opening deals carry the comment "
                                f"{sorted(set(wrong['comment'].astype(str)))[:3]} instead of {comment!r}")
    if ref.invalid_requests:
        problems.append(f"{ref.invalid_requests} order request(s) the MetaTrader5 package refuses outright "
                        f"(order_send returns None): a comment over {MAX_COMMENT_LEN} characters, a bad magic ...")
    return problems


# ───────────────────────────── 2. the replay and the comparison ─────────────────────────────

@dataclass
class DemoParity:
    demo_root: str
    symbol: str
    design: str
    row: str
    cfg: BacktestConfig
    labels: dict
    git: str
    static_problems: List[str]
    report: ParityReport
    isolation: bool
    isolation_problems: List[str]
    ref: ReferenceResult = field(repr=False)
    fast: object = field(repr=False)
    elapsed_s: float = 0.0
    replay_overrides: dict = field(default_factory=dict)   # what the replay changed of the design (--set ...)

    @property
    def ok(self) -> bool:
        return self.report.ok and not self.static_problems and not self.isolation_problems


def run_demo_parity(demo_root, symbol: str, design: str, start, end, store_dir: Path = store.DEFAULT_STORE_DIR,
                    isolation: bool = True, strict_gates: bool = False, mode: str = "ticks",
                    initial_balance: Optional[float] = None, overrides: Optional[dict] = None,
                    progress=None) -> DemoParity:
    """
    Steps 1-3 of the module docstring for one window; ``progress(n, t_ms)`` reports the live loop.
    ``initial_balance`` and ``overrides`` (BacktestConfig fields) change the replayed design only, not the
    design the branch is checked against: a scaled-down variant fires every rule in a short window.
    """
    demo_root = Path(demo_root).expanduser().resolve()
    if not (demo_root / "app.py").is_file() or not (demo_root / "constants.py").is_file():
        raise SystemExit(f"{demo_root}: no app.py / constants.py")
    row, _ = design_overrides(symbol, design)
    extra = {} if initial_balance is None else {"initial_balance": float(initial_balance)}
    extra.update(overrides or {})
    cfg = design_config(symbol, design, start, end, **extra)
    labels = branch_labels(demo_root)
    if labels["strategy"] is not None and str(labels["strategy"]) != "basket":
        raise SystemExit(f"{demo_root} runs STRATEGY={labels['strategy']!r}: the fast engine has no counterpart "
                         f"of it, there is nothing to compare poll by poll")
    # (the branch is checked against the design itself; --initial-balance / --set only change the replay)
    static = static_check(design_config(symbol, design, start, end), demo_root)
    t0 = time.time()
    kw = shared_account(cfg, int(labels["magic"])) if (isolation and labels["magic"] is not None) else {}
    ref = run_reference(cfg, live_root=demo_root, mode=mode, store_dir=store_dir, progress=progress,
                        trace_keys=DIAGNOSTIC_KEYS, **kw)
    fcfg = fast_config_for_parity(cfg)
    prep = prepare(fcfg.symbol, fcfg.start, fcfg.end, fcfg.timeframes(), mode=mode, store_dir=store_dir)
    fast = run(fcfg, prep, trace=True, warn_off_grid=False)
    rep = compare(cfg, ref, fast, blocked_entries_ok=not strict_gates, check_entry_allowed=True)
    iso = isolation_check(ref, labels) if isolation else []
    if isolation and labels["magic"] is None:
        iso = ["the branch defines no MAGIC: the shared-account check was not run"]
    return DemoParity(demo_root=str(demo_root), symbol=symbol, design=design, row=row, cfg=cfg, labels=labels,
                      git=_git(demo_root), static_problems=static, report=rep, isolation=isolation,
                      isolation_problems=iso, ref=ref, fast=fast, elapsed_s=round(time.time() - t0, 1),
                      replay_overrides=dict(extra))


def _ts(ms) -> str:
    if ms is None or (isinstance(ms, float) and math.isnan(ms)):
        return "-"
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def live_baskets(ref: ReferenceResult) -> pd.DataFrame:
    """The bot's baskets from its fills (and the close reasons it logged)."""
    d = ref.deals
    reasons = [e["details"].get("reason") for e in ref.events
               if e["event"] in ("CLOSE_BUY", "CLOSE_SELL") and (e["details"].get("positions_closed") or 0) > 0]
    rows, cur, n_open = [], None, 0
    for _, x in d.iterrows():
        if x["entry"] == "in":
            if n_open == 0:
                cur = dict(open=int(x["t_ms"]), side="BUY" if int(x["type"]) == 0 else "SELL", legs=0, lots=0.0,
                           first_price=float(x["price"]), close=None, pnl=0.0)
            cur["legs"] += 1
            cur["lots"] = round(cur["lots"] + float(x["volume"]), 2)
            n_open += 1
        elif cur is not None:
            cur["pnl"] = round(cur["pnl"] + float(x["profit"]), 2)
            n_open -= 1
            if n_open == 0:
                cur["close"] = int(x["t_ms"])
                rows.append(cur)
                cur = None
    if cur is not None:
        rows.append(cur)
    for k, r in enumerate(rows):
        r["reason"] = (reasons[k] if k < len(reasons) else "") if r["close"] is not None else "(open)"
    return pd.DataFrame(rows, columns=["open", "side", "legs", "lots", "first_price", "close", "pnl", "reason"])


def fast_baskets(fast) -> pd.DataFrame:
    b = fast.baskets
    if not len(b):
        rows = []
    else:
        ms = lambda s: (s.dt.as_unit("ns").astype("int64") // 1_000_000).tolist()
        rows = [dict(open=o, side=s, legs=int(n), lots=round(float(l), 2), first_price=float(p), close=c,
                     pnl=round(float(v), 2), reason=r)
                for o, s, n, l, p, c, v, r in zip(ms(b["open_time"]), b["side"], b["n_pos"], b["lots"],
                                                    b["first_price"], ms(b["close_time"]), b["pnl"], b["reason"])]
    f = fast.fills
    if len(f) and fast.scalars.get("open_positions_at_end", 0) > 0:
        opens = f[f["action"] == "open"]
        o = opens.iloc[-1]
        legs = int(fast.scalars["open_positions_at_end"])
        rows.append(dict(open=int(o["time"].value // 1_000_000), side=o["side"], legs=legs,
                         lots=round(float(fast.scalars.get("open_lots_at_end", 0.0)), 2), first_price=float(o["price"]),
                         close=None, pnl=0.0, reason="(open)"))
    return pd.DataFrame(rows, columns=["open", "side", "legs", "lots", "first_price", "close", "pnl", "reason"])


def _context(res: DemoParity, around_ms: Optional[int], k: int = 3) -> List[str]:
    """Polls of both engines around a time, side by side."""
    if around_ms is None:
        return []
    rt = res.ref.trace[res.ref.trace["fresh"]].reset_index(drop=True)
    ft = res.fast.trace
    t_ref = rt["t_ms"].to_numpy(np.int64)
    i = int(np.searchsorted(t_ref, around_ms, side="left"))
    out = ["    poll time (UTC)              signal(live/fast)  open      fc        n_pos   profit (live/fast)    "
           "unit  cooldown ok"]
    for j in range(max(0, i - k), min(len(rt), i + k + 1)):
        fj = ft[j] if j < len(ft) else None
        mark = ">>" if j == i else "  "
        fs = (f"{SIGNAL_NAMES[int(fj[K.T_SIGNAL])]:>10s}" if fj is not None else "         -")
        out.append(f"  {mark}{_ts(rt['t_ms'][j])}  {SIGNAL_NAMES[int(rt['signal'][j])]:>10s}/{fs}  "
                   f"{rt['open_score'][j]:>4}/{(fj[K.T_OPEN_SCORE] if fj is not None else float('nan')):<4}  "
                   f"{rt['fc_score'][j]:>4}/{(fj[K.T_FC_SCORE] if fj is not None else float('nan')):<4}  "
                   f"{int(rt['n_pos'][j]):>2}/{(int(fj[K.T_NPOS]) if fj is not None else 0):<2}  "
                   f"{float(rt['profit'][j]):>9.2f}/{(fj[K.T_PROFIT] if fj is not None else float('nan')):<9.2f}  "
                   f"{int(rt['units'][j]):>2}/{(int(fj[K.T_UNITS]) if fj is not None else 0):<2}  "
                   f"{bool(rt['entry_allowed'][j])!s:>5}/{(bool(fj[K.T_ENTRY_ALLOWED] > 0.5) if fj is not None else '-')}")
    if i < len(rt):
        extra = {c[2:]: rt[c][i] for c in rt.columns if c.startswith("x_") and rt[c][i] is not None
                 and not (isinstance(rt[c][i], float) and math.isnan(rt[c][i]))}
        if extra:
            out.append("    the branch's own view at >>: " + ", ".join(f"{k}={v}" for k, v in extra.items()))
    return out


def format_result(res: DemoParity, max_rows: int = 40) -> str:
    rep, cfg, ref, fast = res.report, res.cfg, res.ref, res.fast
    lb = res.labels
    L: List[str] = []
    verdict = "PASS" if res.ok else "FAIL"
    L.append(f"DEMO PARITY {verdict}: {Path(res.demo_root).name} vs the fast engine running {res.symbol} {res.design!r}")
    L.append(f"  branch      {res.demo_root} @ {res.git}")
    L.append(f"  labels      DESIGN_NAME={lb['design_name']!r} DEMO_BRANCH={lb['demo_branch']!r} MAGIC={lb['magic']} "
             f"comment={lb['comment']!r}")
    L.append(f"  design row  {res.row}")
    if res.replay_overrides:
        L.append(f"  replayed with  {res.replay_overrides}  (the branch is still checked against the design row)")
    L.append(f"  window      {cfg.start} -> {cfg.end} UTC, raw ticks, 1 s polls + 0.1 s after an order; "
             f"bot balance ${cfg.initial_balance:,.2f}"
             + (f" on a shared ${SHARED_ACCOUNT_BALANCE:,.0f} account" if res.isolation else " (account of its own)"))
    L.append(f"  replay      {res.elapsed_s:.0f} s, {ref.iterations:,} loop passes")
    L.append("")
    L.append("1. constants.py / symbols.json hold the design: " + ("yes" if not res.static_problems else "NO"))
    L += [f"   - {p}" for p in res.static_problems]
    L.append("")
    L.append("2. parity of the replayed app.py with the fast engine: " + ("yes" if rep.ok else "NO"))
    L += ["   " + line for line in str(rep).splitlines()]
    c = fast.counters
    L.append(f"   rules the fast engine applied in the window: entries {c['entries']}, adds {c['ladder_adds']}, "
             f"target closes {c['closes_target']}, stop closes {c['closes_stop_loss']}, force-closes "
             f"{c['closes_force']}; entry polls held back by the trend {c['polls_entry_blocked_trend']}, by a "
             f"cooldown / loss pause {c['polls_entry_blocked_cooldown']}, by the trading window "
             f"{c['polls_entry_blocked_window']}")
    # signals
    sig_live = ref.trace[ref.trace["fresh"]]["signal"].value_counts().to_dict()
    sig_fast = pd.Series(fast.trace[:, K.T_SIGNAL].astype(int)).value_counts().to_dict() if len(fast.trace) else {}
    keys = sorted(set(sig_live) | set(sig_fast))
    L.append("   signals per poll (live / fast): " + ", ".join(
        f"{SIGNAL_NAMES[int(k)]} {sig_live.get(k, 0)}/{sig_fast.get(k, 0)}" for k in keys))
    # baskets
    lb_, fb_ = live_baskets(ref), fast_baskets(fast)
    L.append(f"   baskets (live {len(lb_)} / fast {len(fb_)}):")
    L.append("     #  live: open (UTC)           side legs   lots  first price  close (UTC)              p/l      reason"
             "      | fast: open, close, p/l, reason")
    for k in range(min(max(len(lb_), len(fb_)), max_rows)):
        a = lb_.iloc[k] if k < len(lb_) else None
        b = fb_.iloc[k] if k < len(fb_) else None
        left = (f"{_ts(a['open'])}  {a['side']:<4} {int(a['legs']):>4} {a['lots']:>6.2f} {a['first_price']:>12.3f}  "
                f"{_ts(a['close'])}  {a['pnl']:>8.2f}  {str(a['reason']):<10}") if a is not None else " " * 96
        right = (f"{_ts(b['open'])}, {_ts(b['close'])}, {b['pnl']:.2f}, {b['reason']}") if b is not None else "-"
        same = (a is not None and b is not None and abs(int(a["open"]) - int(b["open"])) <= 1500
                and a["side"] == b["side"] and int(a["legs"]) == int(b["legs"])
                and abs(float(a["pnl"]) - float(b["pnl"])) <= 0.0051 * max(int(a["legs"]), 1))
        L.append(f"   {'  ' if same else '!!'}{k:>2}  {left} | {right}")
    L.append(f"   balance: bot {rep.balance_ref:,.2f} / fast {rep.balance_fast:,.2f}"
             + (f" (the shared account ends at {ref.account_balance:,.2f})" if res.isolation else ""))
    if rep.first_divergence_ms is not None:
        L.append(f"   first divergence at {_ts(rep.first_divergence_ms)}: {rep.first_divergence}")
        L += _context(res, rep.first_divergence_ms)
    L.append("")
    if res.isolation:
        L.append("3. isolation on a shared account (other positions and trades, a larger balance, an own trade "
                 "before the virtual start): " + ("yes" if not res.isolation_problems and rep.ok else "NO"))
        L += [f"   - {p}" for p in res.isolation_problems]
        if not rep.ok:
            L.append("   - the parity above ran on that shared account: a bot that is not isolated fails it there "
                     "(re-run with --plain to tell a logic difference from an isolation one)")
    else:
        L.append("3. isolation: not checked (--plain)")
    L.append("")
    L.append(f"VERDICT: {verdict}")
    return "\n".join(L)


def to_json(res: DemoParity) -> dict:
    return dict(ok=res.ok, demo_root=res.demo_root, git=res.git, symbol=res.symbol, design=res.design, row=res.row,
                start=res.cfg.start, end=res.cfg.end, replay_overrides=res.replay_overrides, labels=res.labels,
                static_problems=res.static_problems,
                isolation=res.isolation, isolation_problems=res.isolation_problems,
                parity=dataclasses.asdict(res.report), elapsed_s=res.elapsed_s,
                baskets_live=live_baskets(res.ref).to_dict("records"),
                baskets_fast=fast_baskets(res.fast).to_dict("records"),
                fast_counters=res.fast.counters, contract=res.ref.contract)


def _parse_sets(pairs: Sequence[str]) -> dict:
    """FIELD=VALUE pairs, the value read as JSON when it is JSON (as the backtesting CLI's --set)."""
    out = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"--set expects FIELD=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        try:
            out[k.strip()] = json.loads(v)
        except ValueError:
            low = v.strip().lower()
            out[k.strip()] = None if low in ("none", "null") else True if low == "true" else False if low == "false" else v
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backtesting.engine.demo_parity",
                                description="replay a demo branch's app.py and compare it with the fast engine "
                                            "running the design it implements")
    p.add_argument("demo_root", help="checkout of the demo branch (app.py, constants.py, ...)")
    p.add_argument("symbol", choices=["XAUUSDm", "BTCUSDm"])
    p.add_argument("design", help='"V3-lite", "Top 1", "Top 2", "Top 3" (a row of the round-4 designs file)')
    p.add_argument("start", help='window start, UTC ("2026-11-02 22:00")')
    p.add_argument("end", help="window end, UTC (exclusive)")
    p.add_argument("--store", default=str(store.DEFAULT_STORE_DIR), help="tick store (default: data/store)")
    p.add_argument("--plain", action="store_true", help="an account holding this bot alone (no isolation check)")
    p.add_argument("--strict-gates", action="store_true",
                   help="count a poll where the strategy already holds back an entry that the kernel holds back "
                        "at execution (trend, window ...) as a signal mismatch")
    p.add_argument("--initial-balance", type=float, default=None,
                   help="the bot's starting balance (default: the design's, $2,000); e.g. 2490 makes a win step "
                        "the unit up inside the window")
    p.add_argument("--set", action="append", metavar="FIELD=VALUE", default=[],
                   help="change a BacktestConfig field of the replayed design (JSON values; repeatable), e.g. a "
                        "scaled-down variant that fires every rule in a short window; the branch's constants are "
                        "still checked against the design row")
    p.add_argument("--mode", choices=["ticks", "sec"], default="ticks")
    p.add_argument("--json", default=None, help="also write the result to this JSON file")
    p.add_argument("--quiet", action="store_true", help="no progress lines")
    a = p.parse_args(argv)
    t0 = time.time()
    prog = None if a.quiet else (lambda n, t: print(f"  live loop: {n:,} passes, at {_ts(t)} ({time.time() - t0:.0f} s)",
                                                    file=sys.stderr, flush=True))
    res = run_demo_parity(a.demo_root, a.symbol, a.design, a.start, a.end, store_dir=Path(a.store),
                          isolation=not a.plain, strict_gates=a.strict_gates, mode=a.mode,
                          initial_balance=a.initial_balance, overrides=_parse_sets(a.set), progress=prog)
    print(format_result(res))
    if a.json:
        Path(a.json).write_text(json.dumps(to_json(res), indent=2, default=str), encoding="utf-8")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
