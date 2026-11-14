"""
Backtest Studio -- watch the bot trade history as if it were running live.

    python -m backtesting studio            # then open http://127.0.0.1:8060

One row of controls (symbol, period, starting balance, the strategy parameters) runs the
fast engine over the chosen period. The result stays on the server and two tabs read it:

* **Results** -- headline tiles, the market with every fill (``report.market_figure``,
  served one window at a time) and a sortable / filterable table of baskets;
* **Replay**  -- pick a basket (or a time) and play it back: candles that form second by
  second, entries / ladder adds / exits as they happen, the OPEN / FORCE-CLOSE (/ BOOK)
  score meters with their thresholds, the ladder RSI tiers, the account and an event log.

How it is put together
----------------------
* Nothing big goes to the browser. Results, the prepared tick arrays and replay sessions
  live in ``Studio`` (small LRU caches keyed by ids kept in ``dcc.Store``); the browser
  gets one figure, one table page or one replay frame at a time.
* Playback is ONE callback. A ``dcc.Interval`` ticks every 400 ms; a client-side gate lets
  a tick through only once the previous frame has arrived (Dash throws away the response
  of a callback that is re-triggered while still in flight, so a free-running timer would
  starve a slow frame); the server moves the playhead by ``speed x real time elapsed``.
* The replay shows exactly the trades of the full run -- see ``viz/replay.py``.
* The look is ``viz/theme.py`` (shared with the static report, taken from the live
  dashboard). Extra CSS is inlined through ``app.index_string``; nothing is added to the
  repo-level ``assets/`` folder, which belongs to the live dashboard.

``Studio`` holds every operation as a plain method, so the test-suite (and a notebook) can
drive it without a browser; ``create_app`` only wires those methods to Dash callbacks.
"""

from __future__ import annotations

import dataclasses
import math
import re
import sys
import threading
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs

import numpy as np
import pandas as pd
from dash import Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update
from dash.exceptions import PreventUpdate

from ..config import REPO_ROOT, SYMBOLS, TF_SECONDS, BacktestConfig
from ..data import store
from ..engine import fast
from . import replay as R
from . import report as RP
from . import theme as T

TF_CHOICES = ["M1", "M5", "M15", "M30", "H1", "H4"]     # the timeframes the parameter panel offers
MARKET_TFS = ["M5", "M15", "H1", "H4"]
MARKET_SPANS = [("1D", 1), ("3D", 3), ("1W", 7), ("1M", 30), ("All", 0)]
SPEEDS = [1, 5, 20, 60, 300, 1800]
TICK_MS = 400
PAGE_SIZE = 15
MAX_MARKET_BARS = 12_000        # candles sent for one market view before the timeframe is coarsened
MAX_LADDER_ADDS = 5

PRM_IDS = ["prm-open-tfs", "prm-fc-tfs", "prm-book-tfs", "prm-entry-s", "prm-agree-s", "prm-fc-s",
           "prm-ladder-s", "prm-book-s", "prm-target", "prm-protect", "prm-rsi-os", "prm-rsi-ob",
           "prm-max-adds", "prm-cooldown"]
PRM_KEYS = ["open_tfs", "fc_tfs", "book_tfs", "entry_s", "entry_agree_s", "force_close_s",
            "ladder_s", "book_s", "target", "protect", "rsi_os", "rsi_ob", "max_adds", "cooldown"]

TABLE_COLS = [("basket", "#"), ("open", "Opened (UTC)"), ("side", "Side"), ("n_pos", "Positions"),
              ("lots", "Lots"), ("held", "Held"), ("reason", "Exit"), ("mae", "Worst floating"), ("pnl", "P/L")]
_NUMERIC = {"basket": "basket", "n_pos": "n_pos", "lots": "lots", "held": "held_s", "mae": "mae", "pnl": "pnl"}
_TEXT = {"open": "open", "side": "side", "reason": "reason"}


class StudioError(ValueError):
    """Something the user can fix. The message is written for the screen."""


# ───────────────────────────── server-side state ─────────────────────────────

@dataclass
class RunEntry:
    """One finished backtest, kept on the server."""
    id: str
    cfg: BacktestConfig
    result: fast.Result
    summary: dict
    table: pd.DataFrame
    warnings: List[str]
    seconds: float
    span_ms: Tuple[int, int]
    _m1: Optional[dict] = field(default=None, repr=False)


@dataclass
class Frame:
    """What one step of the replay state machine decided."""
    pb: dict
    session: Optional[R.ReplaySession] = None
    t_ms: int = 0
    tf: str = "M1"
    render: bool = False
    window_changed: bool = False
    playing: bool = False
    slider: Optional[int] = None
    message: str = ""


def _ms_to_day(ms: int) -> date:
    return store.ms_to_dt(ms).date()


def _parse_number(text: str) -> Optional[float]:
    """'+$1,234.5' / '10m' / '2h' -> float (durations in seconds); None when it is not a number."""
    s = str(text).strip().lower().replace("$", "").replace(",", "").replace("+", "").replace("#", "")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([smhd]?)", s)
    if not m:
        return None
    return float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


_FILTER = re.compile(r"^\{(?P<col>[^}]+)\}\s*(?P<op>[is]?(?:contains|datestartswith|>=|<=|!=|=|>|<|eq|ne|ge|le|gt|lt))"
                     r"\s*(?P<val>.*)$", re.I)
_OPS = {"eq": "=", "ne": "!=", "ge": ">=", "le": "<=", "gt": ">", "lt": "<"}


def parse_filter(query: str) -> List[Tuple[str, str, str]]:
    """A DataTable ``filter_query`` -> [(column id, operator, value text)]; unreadable parts are skipped."""
    out = []
    for part in (query or "").split(" && "):
        m = _FILTER.match(part.strip())
        if not m:
            continue
        op = m.group("op").lower()
        if op[0] in "is" and op[1:] in ("contains", "datestartswith", ">=", "<=", "!=", "=", ">", "<",
                                         "eq", "ne", "ge", "le", "gt", "lt"):
            op = op[1:]                      # the case-sensitivity prefix DataTable puts in front
        val = m.group("val").strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'`":
            val = val[1:-1]
        out.append((m.group("col"), _OPS.get(op, op), val))
    return out


class Studio:
    """Caches and every operation behind the screen. Thread-safe; no Dash objects go in or out
    except the small HTML fragments built by the module-level helpers."""

    def __init__(self, store_dir: Optional[Path] = None, max_runs: int = 4, max_sessions: int = 6):
        self.store_dir = Path(store_dir) if store_dir is not None else store.DEFAULT_STORE_DIR
        self._lock = threading.RLock()
        self._runs: "OrderedDict[str, RunEntry]" = OrderedDict()
        self._sessions: "OrderedDict[tuple, R.ReplaySession]" = OrderedDict()
        self._prep: Optional[Tuple[tuple, fast.Prepared]] = None        # one period of ticks at a time
        self._max_runs, self._max_sessions = max_runs, max_sessions

    # ── data & defaults ──

    def span(self, symbol: str) -> Optional[Tuple[date, date]]:
        """First / last UTC day with ticks in the store."""
        try:
            sp = store.data_span(symbol, self.store_dir)
        except (OSError, ValueError, KeyError):
            sp = None
        if not sp:
            return None
        return sp[0].date(), sp[1].date()

    def symbols(self) -> List[str]:
        return list(SYMBOLS)

    def default_symbol(self) -> str:
        with_data = [s for s in SYMBOLS if self.span(s)]
        return (with_data or list(SYMBOLS))[0]

    def default_dates(self, symbol: str, preset: str = "3M") -> Tuple[Optional[str], Optional[str]]:
        """(first day, last day) -- both inclusive -- of a preset that ends on the last day with data."""
        sp = self.span(symbol)
        if not sp:
            return None, None
        first, last = sp
        nxt = pd.Timestamp(last) + pd.Timedelta(days=1)
        start = {"7D": nxt - pd.Timedelta(days=7), "30D": nxt - pd.Timedelta(days=30),
                 "3M": nxt - pd.DateOffset(months=3), "All": pd.Timestamp(first)}.get(preset, pd.Timestamp(first))
        start = max(start.date(), first)
        return start.isoformat(), last.isoformat()

    def live(self, symbol: str) -> BacktestConfig:
        return BacktestConfig.live(symbol)

    def defaults(self, symbol: str) -> dict:
        """The parameter panel as the live bot runs it."""
        c = self.live(symbol)
        order = lambda w: sorted(w, key=TF_SECONDS.get)
        used = set(c.open_weights) | set(c.fc_weights) | (set(c.book_weights) if c.book_enabled else set())
        return dict(
            open_tfs=order(c.open_weights), fc_tfs=order(c.fc_weights), book_tfs=order(c.book_weights),
            entry_s=c.entry_s, entry_agree_s=c.entry_agree_s, force_close_s=c.force_close_s, ladder_s=c.ladder_s,
            book_s=c.book_s, target=c.target_usd_per_unit if c.target_usd_per_unit is not None else 1.0,
            protect=c.profit_protect_usd_per_unit, rsi_os=c.rsi_oversold, rsi_ob=c.rsi_overbought,
            max_adds=min(MAX_LADDER_ADDS, c.n_ladder_adds), cooldown=c.reentry_cooldown_s,
            netting=bool(c.book_enabled), variant=c.variant,
            tf_choices=sorted(set(TF_CHOICES) | used, key=TF_SECONDS.get),
            ladder_tfs=list(c.ladder_tfs), leverage=c.effective_leverage)

    def build_config(self, symbol: str, start, end, balance, params: Optional[dict] = None
                     ) -> Tuple[BacktestConfig, List[str]]:
        """
        Controls -> configuration. ``start`` / ``end`` are the first and last UTC day (both
        inclusive). Anything left empty keeps its live value. Returns (config, warnings).
        """
        if symbol not in SYMBOLS:
            raise StudioError(f"Unknown symbol {symbol!r}.")
        sp = self.span(symbol)
        if not sp:
            raise StudioError(f"There is no tick data for {symbol} in the store - run "
                              "`python -m backtesting data` to download it.")
        if not start or not end:
            raise StudioError("Pick a start and an end date.")
        try:
            d0, d1 = pd.Timestamp(str(start)[:10]).date(), pd.Timestamp(str(end)[:10]).date()
        except (ValueError, TypeError):
            raise StudioError("Those dates could not be read.") from None
        if d1 < d0:
            raise StudioError("The end date is before the start date.")
        if d1 < sp[0] or d0 > sp[1]:
            raise StudioError(f"No {symbol} ticks between {d0} and {d1}: the store holds {sp[0]} to {sp[1]}.")
        try:
            bal = float(balance)
        except (TypeError, ValueError):
            raise StudioError("Enter a starting balance.") from None
        if not math.isfinite(bal) or bal <= 0:
            raise StudioError("The starting balance must be above zero.")

        live = self.live(symbol)
        p = dict(params or {})
        warn: List[str] = []

        def num(key, default, lo=0.0, hi=None, label=None):
            v = p.get(key)
            if v is None or v == "":
                return float(default)
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise StudioError(f"{label or key} must be a number.") from None
            if not math.isfinite(v) or v < lo or (hi is not None and v > hi):
                raise StudioError(f"{label or key} must be between {lo:g} and {hi:g}." if hi is not None
                                  else f"{label or key} cannot be below {lo:g}.")
            return v

        def weights(key, live_w):
            tfs = p.get(key)
            if tfs is None:
                return dict(live_w)
            bad = [tf for tf in tfs if tf not in TF_SECONDS]
            if bad:
                raise StudioError(f"Unknown timeframe {bad[0]!r}.")
            return {tf: live_w.get(tf, (1.0, 1.0)) for tf in tfs}     # a live timeframe keeps its live weight

        kw = dict(start=d0.isoformat(), end=(d1 + timedelta(days=1)).isoformat(), initial_balance=bal,
                  open_weights=weights("open_tfs", live.open_weights), fc_weights=weights("fc_tfs", live.fc_weights),
                  entry_s=num("entry_s", live.entry_s, label="ENTRY_S"),
                  entry_agree_s=num("entry_agree_s", live.entry_agree_s, label="ENTRY_AGREE_S"),
                  force_close_s=num("force_close_s", live.force_close_s, label="FORCE_CLOSE_S"),
                  ladder_s=num("ladder_s", live.ladder_s, label="LADDER_S"),
                  rsi_oversold=num("rsi_os", live.rsi_oversold, 0, 100, "Ladder RSI oversold"),
                  rsi_overbought=num("rsi_ob", live.rsi_overbought, 0, 100, "Ladder RSI overbought"),
                  reentry_cooldown_s=num("cooldown", live.reentry_cooldown_s, label="Re-entry cooldown"))
        if kw["rsi_oversold"] >= kw["rsi_overbought"]:
            raise StudioError("Ladder RSI oversold must be below overbought.")
        adds = int(num("max_adds", min(MAX_LADDER_ADDS, live.n_ladder_adds), 0, MAX_LADDER_ADDS, "Max ladder adds"))
        kw["max_adds"] = live.max_adds if adds >= len(live.ladder_tfs) else adds
        if live.book_enabled:
            kw.update(book_weights=weights("book_tfs", live.book_weights),
                      book_s=num("book_s", live.book_s, label="BOOK_S"),
                      profit_protect_usd_per_unit=num("protect", live.profit_protect_usd_per_unit,
                                                      label="Protect $ per unit"))
        elif live.target_usd_per_unit is not None:
            kw["target_usd_per_unit"] = num("target", live.target_usd_per_unit, label="Target $ per unit")
        cfg = live.replace(**kw)

        r_open, r_fc = R.score_range(cfg.open_weights), R.score_range(cfg.fc_weights)
        if not cfg.open_weights:
            warn.append("OPEN has no timeframe: the open score stays 0, so the bot never enters.")
        elif cfg.entry_s > r_open:
            warn.append(f"ENTRY_S {cfg.entry_s:g} is above the OPEN score range ±{r_open:g}: the bot can never enter.")
        if cfg.entry_agree_s > r_fc:
            warn.append(f"ENTRY_AGREE_S {cfg.entry_agree_s:g} is above the FORCE-CLOSE range ±{r_fc:g}: "
                        "the bot can never enter.")
        if cfg.force_close_s > r_fc:
            warn.append(f"FORCE_CLOSE_S {cfg.force_close_s:g} is above the FORCE-CLOSE range ±{r_fc:g}: "
                        "force-close can never fire.")
        if cfg.book_enabled and cfg.book_s > R.score_range(cfg.book_weights):
            warn.append(f"BOOK_S {cfg.book_s:g} is above the BOOK range ±{R.score_range(cfg.book_weights):g}: "
                        "the profit-book can never fire.")
        return cfg, warn

    def recap(self, symbol: str, params: dict) -> Tuple[str, bool, List[str]]:
        """One readable line of the parameter panel, whether it differs from live, and warnings."""
        d = self.defaults(symbol)
        p = {k: (d[k] if params.get(k) is None or params.get(k) == "" else params[k]) for k in PRM_KEYS}
        tfs = lambda v: "+".join(sorted(v, key=lambda x: TF_SECONDS.get(x, 0), reverse=True)) or "none"
        g = lambda v: f"{float(v):g}"
        bits = [f"OPEN {tfs(p['open_tfs'])} at ±{g(p['entry_s'])} (agree ±{g(p['entry_agree_s'])})",
                f"FORCE-CLOSE {tfs(p['fc_tfs'])} at ±{g(p['force_close_s'])}"]
        if d["netting"]:
            bits.append(f"BOOK {tfs(p['book_tfs'])} at ±{g(p['book_s'])} above ${g(p['protect'])}/unit")
        else:
            bits.append(f"target ${g(p['target'])}/unit")
        bits.append(f"ladder RSI {g(p['rsi_os'])}/{g(p['rsi_ob'])}, {int(float(p['max_adds']))} adds, gate ±{g(p['ladder_s'])}")
        bits.append(f"cooldown {g(p['cooldown'])} s")
        skip = {"target"} if d["netting"] else {"book_tfs", "book_s", "protect"}
        norm = lambda v: sorted(v) if isinstance(v, (list, tuple)) else float(v)
        try:
            modified = any(norm(p[k]) != norm(d[k]) for k in PRM_KEYS if k not in skip)
        except (TypeError, ValueError):
            modified = True
        warn: List[str] = []
        try:
            sp = self.span(symbol)
            if sp:
                _, warn = self.build_config(symbol, sp[1], sp[1], 2000.0, params)
        except StudioError as e:
            warn = [str(e)]
        return " · ".join(bits), modified, warn

    # ── running ──

    def _prepared(self, cfg: BacktestConfig) -> fast.Prepared:
        """Rows + bars for the period, with every panel timeframe built once (so a parameter
        change re-runs without re-loading ticks, and replays reuse the very same arrays)."""
        key = (cfg.symbol, store.to_ms(cfg.start), store.to_ms(cfg.end))
        need = set(cfg.timeframes())
        if self._prep is not None and self._prep[0] == key and need <= set(self._prep[1].tfs):
            return self._prep[1]
        self._prep = None                               # free the previous period before loading the next
        tfs = sorted(set(TF_CHOICES) | need, key=TF_SECONDS.get)
        try:
            prep = fast.prepare(cfg.symbol, cfg.start, cfg.end, tfs, mode="sec", store_dir=self.store_dir)
        except ValueError as e:
            raise StudioError(f"No {cfg.symbol} ticks in the store between {cfg.start} and {cfg.end} - run "
                              "`python -m backtesting data` to download that period.") from e
        self._prep = (key, prep)
        return prep

    def run(self, cfg: BacktestConfig, warnings: Sequence[str] = ()) -> RunEntry:
        """Run (or fetch from the cache) one backtest. About a second per month of data."""
        key = cfg.key()
        with self._lock:
            hit = self._runs.get(key)
            if hit is not None:
                self._runs.move_to_end(key)
                return hit
            t0 = time.time()
            res = fast.run(cfg, self._prepared(cfg), store_dir=self.store_dir)
            entry = RunEntry(id=key, cfg=cfg, result=res, summary=res.summary(), table=_basket_table(res),
                             warnings=list(warnings), seconds=time.time() - t0, span_ms=R.run_span(res))
            self._runs[key] = entry
            while len(self._runs) > self._max_runs:
                old, _ = self._runs.popitem(last=False)
                for k in [k for k in self._sessions if k[0] == old]:
                    del self._sessions[k]
            return entry

    def entry(self, run_id: Optional[str]) -> Optional[RunEntry]:
        if not run_id:
            return None
        with self._lock:
            return self._runs.get(run_id)

    # ── results tab ──

    def table_page(self, run_id: Optional[str], page: int = 0, size: int = PAGE_SIZE, sort_by=None,
                   filter_query: str = "") -> Tuple[List[dict], int, str]:
        """One page of the baskets table: (rows, page count, note). Sorting and filtering use the
        numbers behind the formatted cells."""
        e = self.entry(run_id)
        if e is None or len(e.table) == 0:
            return [], 1, "No baskets." if e is not None else ""
        df = e.table
        mask = np.ones(len(df), bool)
        for col, op, val in parse_filter(filter_query):
            num = _parse_number(val)
            if col in _NUMERIC and op in ("=", "!=", ">", "<", ">=", "<=") and num is not None:
                x = df[_NUMERIC[col]].to_numpy(dtype=float)
                mask &= {"=": np.isclose(x, num), "!=": ~np.isclose(x, num), ">": x > num, "<": x < num,
                         ">=": x >= num, "<=": x <= num}[op]
            elif col in _NUMERIC or col in _TEXT:
                s = df["d_" + col].str.lower()
                v = val.lower()
                if op == "=" and col in _TEXT:
                    mask &= (s.str.replace("▲ ", "").str.replace("▼ ", "") == v).to_numpy()
                elif op == "!=":
                    mask &= ~s.str.contains(v, regex=False).to_numpy()
                elif op == "datestartswith":
                    mask &= s.str.startswith(v).to_numpy()
                else:
                    mask &= s.str.contains(v, regex=False).to_numpy()
        view = df[mask]
        if sort_by:
            col = sort_by[0].get("column_id")
            key = _NUMERIC.get(col) or _TEXT.get(col)
            if key:
                view = view.sort_values(key, ascending=sort_by[0].get("direction", "asc") == "asc", kind="stable")
        n = len(view)
        pages = max(1, math.ceil(n / size))
        page = min(max(int(page or 0), 0), pages - 1)
        rows = [{"id": int(r.basket), "basket": r.d_basket, "open": r.d_open, "side": r.d_side, "n_pos": r.d_n_pos,
                 "lots": r.d_lots, "held": r.d_held, "reason": r.d_reason, "mae": r.d_mae, "pnl": r.d_pnl}
                for r in view.iloc[page * size:(page + 1) * size].itertuples()]
        net = float(view["pnl"].sum()) if n else 0.0
        note = (f"{n:,} of {len(df):,} baskets" if n != len(df) else f"{n:,} baskets") + \
               f" · net {R.fmt_money(net)}" + (f" · page {page + 1} of {pages}" if pages > 1 else "")
        return rows, pages, note

    def _m1(self, e: RunEntry) -> dict:
        if e._m1 is None:
            e._m1 = store.load_m1(e.cfg.symbol, e.cfg.start, e.cfg.end, self.store_dir) or {}
        return e._m1

    def market_range(self, e: RunEntry, days: float) -> Tuple[int, int]:
        """The last ``days`` of the run (0 = all of it), in epoch ms."""
        a, z = store.to_ms(e.cfg.start), e.span_ms[1]
        m1 = self._m1(e)
        if m1 and len(m1["t"]):
            a, z = max(a, int(m1["t"][0]) * 1000), min(z, int(m1["t"][-1]) * 1000 + 60_000)
        return (max(a, z - int(days * 86_400_000)) if days else a), z

    def market(self, e: RunEntry, tf: str, x0_ms: int, x1_ms: int):
        """``report.market_figure`` for one visible range: (figure, note, (x0, x1)).

        Only the bars and fills in and around the visible range are sent; the y axes are
        fitted to it and the trade marks sized for it (what the static report does in JS)."""
        m1 = self._m1(e)
        if not m1 or len(m1["t"]) == 0:
            return _blank_fig("No M1 bars in the store for this period."), "", (x0_ms, x1_ms)
        a_all, z_all = int(m1["t"][0]) * 1000, int(m1["t"][-1]) * 1000 + 60_000
        x0_ms, x1_ms = max(min(x0_ms, z_all - 60_000), a_all), min(max(x1_ms, a_all + 60_000), z_all)
        if x1_ms - x0_ms < 120_000:
            x1_ms = min(x0_ms + 120_000, z_all)
        pad = (x1_ms - x0_ms) // 2
        lo, hi = max(a_all, x0_ms - pad), min(z_all, x1_ms + pad)
        used = tf if tf in MARKET_TFS else "M15"
        order = sorted(set(MARKET_TFS) | {"H1", "H4"}, key=TF_SECONDS.get)
        while (hi - lo) / (TF_SECONDS[used] * 1000) > MAX_MARKET_BARS and used != order[-1]:
            used = order[order.index(used) + 1]
        tb = m1["t"].astype(np.int64) * 1000
        i0, i1 = int(np.searchsorted(tb, lo, "left")), int(np.searchsorted(tb, hi, "left"))
        if i1 <= i0:
            return _blank_fig("No bars in this range."), "", (x0_ms, x1_ms)
        res = e.result
        f, b, q = res.fills, res.baskets, res.equity
        ft, bo, bc, qt = R._ms(f["time"]), R._ms(b["open_time"]), R._ms(b["close_time"]), R._ms(q["time"])
        view = dataclasses.replace(res, fills=f[(ft >= lo) & (ft < hi)], baskets=b[(bc >= lo) & (bo < hi)],
                                   equity=q[(qt >= lo) & (qt < hi)], trace=None)
        fig = RP.market_figure(view, {k: v[i0:i1] for k, v in m1.items()}, tfs=(used,), default_tf=used, height=900)
        x0, x1 = pd.Timestamp(x0_ms, unit="ms"), pd.Timestamp(x1_ms, unit="ms")
        fig.update_xaxes(range=[x0, x1])
        days = (x1_ms - x0_ms) / 86_400_000
        size = 4 if days > 21 else 6 if days > 6 else 8 if days > 1.5 else 11
        for tr in fig.data:
            if tr.meta == "trade":
                tr.marker.size = size
        _fit_y(fig, x0_ms, x1_ms)
        fig.update_layout(uirevision=f"{e.id}:{used}:{x0_ms}:{x1_ms}")
        note = "" if used == tf else f"{used} candles at this zoom ({tf} would be too many bars)"
        return fig, note, (int(x0_ms), int(x1_ms))

    # ── replay tab ──

    def _prep_for(self, e: RunEntry) -> fast.Prepared:
        """The very arrays the full run was computed from (re-loaded if another period replaced them)."""
        return self._prepared(e.cfg)

    def session(self, e: RunEntry, when_ms: int, end_ms: int, window: Optional[R.ReplayWindow] = None
                ) -> R.ReplaySession:
        key = (e.id, int(when_ms), int(end_ms))
        with self._lock:
            s = self._sessions.get(key)
            if s is not None:
                self._sessions.move_to_end(key)
                return s
            win = window or R.replay_window(e.result, int(when_ms), (int(end_ms) - int(when_ms)) / 1000.0)
            s = R.ReplaySession.build(win, prep=self._prep_for(e), store_dir=self.store_dir)
            self._sessions[(e.id, win.visible_from_ms, win.end_ms)] = s
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
            return s

    def _request_window(self, e: RunEntry, rq: Optional[dict]) -> Tuple[R.ReplayWindow, int]:
        """The window (and playhead) a replay request asks for; the run's first basket by default."""
        res = e.result
        rq = rq or {}
        if rq.get("basket") is not None:
            return R.window_for_basket(res, int(rq["basket"]))
        if rq.get("at") is not None:
            win = R.replay_window(res, int(rq["at"]), R.DEFAULT_SPAN_S)
            return win, win.visible_from_ms
        ot, oid, _ = R.basket_opens(res)
        if len(ot):
            return R.window_for_basket(res, int(oid[0]))
        win = R.replay_window(res, e.span_ms[0], R.DEFAULT_SPAN_S)
        return win, win.visible_from_ms

    def transport(self, trigger: Optional[str], pb: Optional[dict], *, run_id: Optional[str] = None,
                  rq: Optional[dict] = None, speed: float = 1.0, tf: str = "M1", slider: Optional[int] = None,
                  drag: Optional[int] = None, goto: Optional[str] = None, pulse_n: Optional[int] = None,
                  now: Optional[float] = None) -> Frame:
        """
        One step of the replay: a tick, a button, the slider, or a new request.

        ``pb`` is the playback state the browser holds: run id, window (``when`` .. ``end``),
        playhead ``t`` (epoch ms), ``playing``, the server time of the last frame (``wall``)
        and the key of the frame it is showing. Returns the next state and what to redraw.
        Raises ``PreventUpdate`` for an echo that changes nothing.
        """
        now = time.time() if now is None else now
        pb = dict(pb or {})
        tf = tf if tf in R.CANDLE_TFS else R.CANDLE_TFS[0]
        want = (rq or {}).get("run") if trigger == "st-rq" else (pb.get("run") or run_id)
        e = self.entry(want)
        base = {"ack": pulse_n, "playing": False, "dv": drag}
        if e is None:
            return Frame(pb=base, tf=tf, message="Run a backtest first." if not want else
                         "Those results are no longer in memory - press Run backtest again.")
        res = e.result
        poll = int(e.cfg.poll_interval_ms)
        run_z = e.span_ms[1]
        when, end, t = pb.get("when"), pb.get("end"), pb.get("t")
        playing = bool(pb.get("playing"))
        fresh = pb.get("run") != e.id or when is None or end is None or t is None
        win: Optional[R.ReplayWindow] = None
        msg = ""
        try:
            if trigger == "st-rq" or fresh:
                win, t = self._request_window(e, rq if trigger == "st-rq" else None)
                playing = bool((rq or {}).get("play")) if trigger == "st-rq" else False
            elif trigger == "rp-go":
                at = _parse_time(goto, t)
                if at is None:
                    msg = "Could not read that time - write it like 2026-11-09 06:15."
                else:
                    win = R.replay_window(res, at, R.DEFAULT_SPAN_S)
                    t, playing = win.visible_from_ms, False
            elif trigger in ("rp-prev", "rp-next"):
                nb = R.neighbour_basket(res, int(t), 1 if trigger == "rp-next" else -1)
                if nb is None:
                    msg = "No later basket in this run." if trigger == "rp-next" else "No earlier basket in this run."
                elif when <= nb[1] < end:
                    t = nb[1]
                else:
                    win, t = R.window_for_basket(res, nb[0])
            elif trigger in ("rp-back", "rp-fwd"):
                t = self.session(e, when, end).step(int(t), 1 if trigger == "rp-fwd" else -1)
                playing = False
            elif trigger == "rp-play":
                playing = not playing
                if playing and t >= end:
                    if end + poll < run_z:
                        win = R.replay_window(res, end, R.DEFAULT_SPAN_S)
                        t = win.visible_from_ms
                    else:
                        t = when
            elif trigger == "rp-slider":
                if slider is None or slider == pb.get("sv"):
                    raise PreventUpdate
                t = int(when) + int(slider) * 1000
            elif trigger == "st-pulse":
                if not playing:
                    raise PreventUpdate
                elapsed = min(max(now - float(pb.get("wall") or now), 0.0), 1.5)
                t = int(t) + int(round(float(speed or 1) * elapsed * 1000))
                if t >= end:
                    if end + poll < run_z:                 # roll into the next window, still playing
                        win = R.replay_window(res, end, R.DEFAULT_SPAN_S)
                        t = win.visible_from_ms
                    else:
                        t, playing = end, False
            if win is not None:
                when, end = win.visible_from_ms, win.end_ms
            sess = self.session(e, when, end, window=win)
        except R.ReplayError as err:
            if fresh:
                return Frame(pb=dict(base, run=e.id), tf=tf, message=str(err))
            msg, win = str(err), None
            when, end, t = pb.get("when"), pb.get("end"), pb.get("t")
            sess = self.session(e, when, end)
        t = sess.clamp(t)
        fk = list(sess.frame_key(t, tf))
        changed = win is not None or fresh
        sv = int((t - sess.vis_ms) // 1000)
        dragging = drag is not None and drag != pb.get("dv") and trigger == "st-pulse"
        out = {"run": e.id, "when": int(when), "end": int(end), "t": int(t), "playing": bool(playing), "wall": now,
               "ack": pulse_n, "sv": pb.get("sv") if dragging else sv, "dv": drag, "fk": fk}
        return Frame(pb=out, session=sess, t_ms=int(t), tf=tf, render=changed or fk != pb.get("fk"),
                     window_changed=changed, playing=bool(playing),
                     slider=None if dragging or (not changed and sv == pb.get("sv")) else sv, message=msg)


# ───────────────────────────── pure helpers ─────────────────────────────

def _parse_time(text: Optional[str], around_ms: Optional[int]) -> Optional[int]:
    """'2026-11-09 06:15[:30]' or '06:15' (on the playhead's day) -> epoch ms."""
    s = (text or "").strip().replace("T", " ")
    if not s:
        return None
    try:
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", s):
            if around_ms is None:
                return None
            s = f"{store.ms_to_dt(int(around_ms)):%Y-%m-%d} {s}"
        return store.to_ms(pd.Timestamp(s))
    except (ValueError, TypeError):
        return None


def _basket_table(res) -> pd.DataFrame:
    """Baskets with the raw numbers (sorting / filtering) next to the cells as shown (``d_*``)."""
    b = res.baskets
    rows = pd.DataFrame({
        "basket": b["basket"].astype(int) if len(b) else pd.Series(dtype=int),
        "open": b["open_time"].dt.strftime("%Y-%m-%d %H:%M:%S") if len(b) else pd.Series(dtype=str),
        "side": b["side"], "n_pos": b["n_pos"].astype(int) if len(b) else pd.Series(dtype=int),
        "lots": b["lots"].astype(float).round(2) if len(b) else pd.Series(dtype=float),
        "held_s": b["duration_s"].astype(float) if len(b) else pd.Series(dtype=float),
        "reason": b["reason"].map(lambda r: R.REASON_SHORT.get(r, r)) if len(b) else pd.Series(dtype=str),
        "mae": b["mae"].astype(float) if len(b) else pd.Series(dtype=float),
        "pnl": b["pnl"].astype(float) if len(b) else pd.Series(dtype=float),
    })
    # a basket still open when the run ends has fills but no basket row: list it too
    f = res.fills
    if len(f) and int(res.scalars.get("open_positions_at_end", 0)) > 0:
        last = f[f["basket"] == f["basket"].max()]
        if (last["action"] != "close").all():
            t0 = last["time"].iloc[0]
            end_ms = R.run_span(res)[1]
            rows = pd.concat([rows, pd.DataFrame([{
                "basket": int(last["basket"].iloc[0]), "open": t0.strftime("%Y-%m-%d %H:%M:%S"),
                "side": last["side"].iloc[0], "n_pos": int(len(last)), "lots": round(float(last["lots"].sum()), 2),
                "held_s": (end_ms - int(t0.value // 1_000_000)) / 1000.0, "reason": "still open",
                "mae": float(res.scalars.get("open_profit_at_end", 0.0)),
                "pnl": float(res.scalars.get("open_profit_at_end", 0.0))}])], ignore_index=True)
    if len(rows) == 0:
        return rows
    rows["d_basket"] = rows["basket"].map(lambda i: f"#{int(i)}")
    rows["d_open"] = rows["open"]
    rows["d_side"] = rows["side"].map(lambda s: "▲ BUY" if s == "BUY" else "▼ SELL")
    rows["d_n_pos"] = rows["n_pos"].map(str)
    rows["d_lots"] = rows["lots"].map(lambda v: f"{v:.2f}")
    rows["d_held"] = rows["held_s"].map(R.fmt_dur)
    rows["d_reason"] = rows["reason"]
    rows["d_mae"] = rows["mae"].map(R.fmt_money)
    rows["d_pnl"] = rows["pnl"].map(R.fmt_money)
    return rows


def _fit_y(fig, x0_ms: int, x1_ms: int) -> None:
    """Fit every y axis of a figure to the marks inside the visible x range."""
    ext: Dict[str, List[float]] = {}
    for tr in fig.data:
        if tr.visible is False or tr.x is None:
            continue
        lo, hi = (tr.low, tr.high) if tr.type == "candlestick" else (tr.y, tr.y)
        if lo is None or len(tr.x) == 0:
            continue
        x = pd.to_datetime(pd.Series(list(tr.x)), errors="coerce")
        xm = (x.astype("int64") // 1_000_000).to_numpy()
        ok = x.notna().to_numpy() & (xm >= x0_ms) & (xm <= x1_ms)
        lo = pd.to_numeric(pd.Series(list(lo)), errors="coerce").to_numpy(dtype=float)
        hi = pd.to_numeric(pd.Series(list(hi)), errors="coerce").to_numpy(dtype=float)
        ok &= np.isfinite(lo) & np.isfinite(hi)
        if not ok.any():
            continue
        cur = ext.setdefault(tr.yaxis or "y", [math.inf, -math.inf])
        cur[0], cur[1] = min(cur[0], float(lo[ok].min())), max(cur[1], float(hi[ok].max()))
    for ya, (a, z) in ext.items():
        name = "yaxis" if ya == "y" else "yaxis" + ya[1:]
        if ya == "y3":                                   # open lots: keep the zero line in view
            a, z = min(a, 0.0), max(z, 0.0)
        pad = (z - a) * 0.07 or abs(z) * 0.001 or 1.0
        if ya == "y4":
            pad = max(pad, 0.5)
        fig.layout[name].range = [a - pad, z + pad]


def _relayout_range(relayout: Optional[dict]):
    """A plotly relayout event -> (x0 ms, x1 ms), 'auto' (reset) or None (not about the x axis)."""
    if not relayout:
        return None
    lo = hi = None
    for k, v in relayout.items():
        if re.fullmatch(r"xaxis\d*\.autorange", k) and v:
            return "auto"
        if re.fullmatch(r"xaxis\d*\.range", k) and isinstance(v, (list, tuple)) and len(v) == 2:
            lo, hi = v
        elif re.fullmatch(r"xaxis\d*\.range\[0\]", k):
            lo = v
        elif re.fullmatch(r"xaxis\d*\.range\[1\]", k):
            hi = v
    if lo is None or hi is None:
        return None
    try:
        a, z = store.to_ms(pd.Timestamp(lo)), store.to_ms(pd.Timestamp(hi))
    except (ValueError, TypeError):
        return None
    return (a, z) if z > a else None


def _blank_fig(text: str = "") -> dict:
    lay = T.plotly_layout(margin=dict(l=10, r=10, t=10, b=10),
                          xaxis=dict(visible=False), yaxis=dict(visible=False),
                          annotations=[dict(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                                            font=dict(color=T.INK_MUTED, size=13))] if text else [])
    return {"data": [], "layout": lay}


def slider_marks(vis_ms: int, end_ms: int) -> dict:
    """Clock labels along the replay slider (the slider counts seconds from the window start)."""
    span_s = max((end_ms - vis_ms) / 1000.0, 1.0)
    step = next((s for s in (300, 600, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400) if span_s / s <= 8), 86400)
    first = (vis_ms // (step * 1000) + 1) * step * 1000
    marks = {}
    day0 = _ms_to_day(vis_ms)
    for ms in range(int(first), int(end_ms), step * 1000):
        d = store.ms_to_dt(ms)
        label = f"{d:%H:%M}" if d.date() == day0 or d.hour or d.minute else f"{d:%b %d}"
        marks[int((ms - vis_ms) // 1000)] = {"label": label}
    return marks


# ───────────────────────────── HTML fragments ─────────────────────────────

def _lab(text: str):
    return html.Span(text, className="lab")


def _seg(id_: str, options: Sequence[Tuple[object, str]], value):
    """A segmented single choice (radio buttons drawn as one control)."""
    return dcc.RadioItems(id=id_, className="segr", value=value,
                          options=[{"label": html.Span(lab), "value": val} for val, lab in options])


def _chips(id_: str, options: Sequence[str], value: Sequence[str]):
    """A multi-select drawn as toggle chips."""
    return dcc.Checklist(id=id_, className="segr chips", value=list(value),
                         options=[{"label": html.Span(o), "value": o} for o in options])


def _field(label: str, child, hide: bool = False, hint: str = ""):
    return html.Div([html.Div(label, className="lab"), child, html.Div(hint, className="hint") if hint else None],
                    className="fld", style={"display": "none"} if hide else None)


def _number(id_: str, value, step=1, lo=0, hi=None, width=88):
    return dcc.Input(id=id_, type="number", value=value, step=step, min=lo, max=hi, className="num",
                     style={"width": f"{width}px"})


def _status(text: str, kind: str = "", extra: Sequence[str] = ()):
    kids: list = [html.Span(text, className="s-" + kind if kind else None)]
    for w in extra:
        kids.append(html.Div(w, className="s-warn"))
    return kids


def _tile(label: str, value: str, note: str = "", cls: str = ""):
    return html.Div([html.Div(label, className="label"), html.Div(value, className=("value " + cls).strip()),
                     html.Div(note, className="note")], className="tile")


def _sign(x: float) -> str:
    return "pos" if x > 0 else "neg" if x < 0 else ""


def results_head(e: RunEntry):
    cfg, s, ct = e.cfg, e.summary, e.result.counters
    last = (pd.Timestamp(cfg.end) - pd.Timedelta(days=1)).date()
    flat = max(ct.get("polls_flat", 0), 1)
    funnel = (f"While flat the bot polled {ct.get('polls_flat', 0):,} times: the open score wanted a trade but the "
              f"force-close score vetoed it on {ct.get('polls_entry_blocked_chop', 0) / flat * 100:.1f}% of those polls, "
              f"the re-entry cooldown held a ready signal back on {ct.get('polls_entry_blocked_cooldown', 0) / flat * 100:.1f}% "
              f"and the trading window on {ct.get('polls_entry_blocked_window', 0) / flat * 100:.1f}%.")
    return [html.Div(className="res-title", children=[
        html.H1(f"{cfg.symbol} · {cfg.variant}"),
        html.Span(f"{cfg.start} → {last} UTC · {cfg.describe_scores()} · ${cfg.initial_balance:,.0f} at 1:{cfg.effective_leverage:g} "
                  f"· per-second tick replay, {int(e.result.scalars.get('rows', 0)):,} rows", className="sub")]),
        html.P(funnel, className="lede")]


def results_tiles(e: RunEntry):
    """The headline: one hero figure and the tiles the owner asked for."""
    s, m = e.summary, R.fmt_money
    net = s["net_profit"]
    nan = float("nan")
    num = lambda v, nd=2: "-" if v is None or not math.isfinite(v) else f"{v:,.{nd}f}"
    hero_note = (f"{num(s['return_pct'])}% over {num(s['days'], 0)} days · final equity {m(s['final_equity'], False)}"
                 + (" · ACCOUNT STOPPED OUT" if s["stopped_out"] else "")
                 + (f" · {m(s['open_profit_at_end'])} still open" if abs(s["open_profit_at_end"]) > 0.005 else ""))
    hero = html.Div([html.Div(f"Net result on ${s['initial_balance']:,.0f}", className="label"),
                     html.Div(m(net), className="value " + _sign(net)),
                     html.Div(hero_note, className="note")], className="card big")
    avg_win, avg_loss = s.get("avg_win", 0.0), s.get("avg_loss", 0.0)
    tiles = [
        _tile("Return", f"{num(s['return_pct'])}%", f"on ${s['initial_balance']:,.0f} in {num(s['days'], 0)} days",
              _sign(s["return_pct"])),
        _tile("Max drawdown", m(s["max_drawdown_usd"], False), f"{num(s['max_drawdown_pct'], 1)}% of the equity peak"),
        _tile("Win rate", f"{num(s.get('win_rate_pct', nan), 1)}%",
              f"needs {num(s['breakeven_win_rate_pct'], 1)}% to break even" if "breakeven_win_rate_pct" in s else ""),
        _tile("Profit factor", num(s.get("profit_factor", nan)), "gross profit / gross loss"),
        _tile("Baskets", f"{s['baskets']:,}", f"{num(s['baskets_per_day'], 1)} per day · {s['ladder_adds']:,} ladder adds"),
        _tile("Average win", m(avg_win), "per winning basket"),
        _tile("Average loss", m(avg_loss), f"{num(abs(avg_loss) / avg_win, 1)}x the average win" if avg_win else ""),
        _tile("Worst basket", m(s.get("largest_loss", 0.0)), f"worst floating {m(s['max_floating_loss'])}"),
    ]
    return html.Div([hero, html.Div(tiles, className="tiles")], className="hero")


def _empty_results():
    return html.Div(className="card empty", children=[
        html.H3("No backtest yet"),
        html.P("Choose a symbol and a period above and press Run backtest. The strategy parameters start at the "
               "values the live bot runs on this branch; open the panel to change a timeframe or a threshold and "
               "run again to compare."),
        html.P("Results: headline numbers, the market with every fill, and the baskets table. "
               "Replay: click a basket and watch it trade second by second.", className="cap")])


def _legend_key(replay: bool = False):
    def sw(color, shape, text):
        return html.Span([html.Span(shape, style={"color": color}), " " + text])
    items = [sw(T.UP, "▲", "entry long"), sw(T.DOWN, "▼", "entry short"), sw(T.INK_2, "△", "ladder add"),
             sw(T.INK_2, "●", "exit: target"), sw(T.INK_2, "◆", "profit-book"), sw(T.INK_2, "✕", "force-close"),
             sw(T.INK_2, "■", "stop-loss"), sw(T.INK_2, "★", "stop-out"),
             sw(T.UP, "■", "exit won"), sw(T.DOWN, "■", "exit lost")]
    if replay:
        items += [sw(T.ACCENT, "━", "average entry"), html.Span("thin lines = each position's entry price")]
    return html.Div(items, className="key")


def _pct(x: float, axis: float) -> float:
    return max(0.0, min(100.0, (x + axis) / (2.0 * axis) * 100.0))


def _mark_label(pct: float, text: str):
    if pct < 9:
        st = {"left": "0", "transform": "none"}
    elif pct > 91:
        st = {"right": "0", "left": "auto", "transform": "none"}
    else:
        st = {"left": f"{pct:.2f}%"}
    return html.Span(text, style=st)


def score_meter(title: str, key_color: str, formula: str, value: float, axis: float, thr: float,
                top: Tuple[str, str], chip: Tuple[str, str, str], thr_colors: Tuple[str, str],
                agree: Optional[float] = None):
    """
    A -axis..+axis meter for one section score (the live dashboard's gauge).

    ``thr`` is the acting threshold, drawn at -thr / +thr with the ``top`` labels; ``agree``
    adds the entry-agreement marks with labels under the track. The fill grows from the
    centre and takes the UP / DOWN colour only beyond the threshold; ``chip`` (glyph, text,
    colour) names the zone in words, so nothing is read from colour alone.
    """
    axis = max(float(axis), 1.0)
    p, zero = _pct(value, axis), 50.0
    t_neg, t_pos = _pct(-thr, axis), _pct(thr, axis)
    beyond = abs(value) >= thr and value != 0
    fill = T.NEUTRAL if not beyond else (T.UP if value > 0 else T.DOWN)
    track = [html.Div(className="mt-band", style={"left": f"{t_neg:.2f}%", "width": f"{t_pos - t_neg:.2f}%"}),
             html.Div(className="mt-fill", style={"left": f"{min(p, zero):.2f}%", "width": f"{abs(p - zero):.2f}%",
                                                  "background": fill}),
             html.Div(className="mt-zero", style={"left": f"{zero}%"}),
             html.Div(className="mt-thr", style={"left": f"{t_neg:.2f}%", "background": thr_colors[0]}),
             html.Div(className="mt-thr", style={"left": f"{t_pos:.2f}%", "background": thr_colors[1]})]
    below = [_mark_label(0, f"-{axis:g}"), _mark_label(100, f"+{axis:g}")]
    if agree is not None:
        a_neg, a_pos = _pct(-agree, axis), _pct(agree, axis)
        track += [html.Div(className="mt-agree", style={"left": f"{a_neg:.2f}%"}),
                  html.Div(className="mt-agree", style={"left": f"{a_pos:.2f}%"})]
        if 9 <= a_neg <= 91:
            below += [_mark_label(a_neg, f"open ≤ -{agree:g}"), _mark_label(a_pos, f"open ≥ +{agree:g}")]
        else:
            below = [_mark_label(0, f"open ≤ -{agree:g}"), _mark_label(100, f"open ≥ +{agree:g}")]
    else:
        below.insert(1, _mark_label(50, "0"))
    track.append(html.Div(className="mt-dot", style={"left": f"{p:.2f}%", "background": fill}))
    return html.Div(className="mt", children=[
        html.Div(className="mt-h", children=[
            html.Span([html.I(style={"background": key_color}), title, html.Span(formula, className="f")], className="t"),
            html.Span([html.Span(chip[0], style={"color": chip[2]}), " " + chip[1]], className="chip")]),
        html.Div(className="mt-b", children=[
            html.Div(f"{value:+g}" if value else "0", className="mt-v"),
            html.Div([html.Div([_mark_label(t_neg, top[0]), _mark_label(t_pos, top[1])], className="mt-lab"),
                      html.Div(track, className="mt-track"),
                      html.Div(below, className="mt-lab low")])])])


def rsi_row(tf: str, value: Optional[float], os_: float, ob: float, armed: bool, side: int):
    """One ladder tier: the RSI on a 0..100 track with the oversold / overbought marks. The
    armed tier (the one that would add the next position) has its trigger zone tinted."""
    if value is None:
        return html.Div([html.Span(tf, className="tf"), html.Div(className="rs-track off"),
                         html.Span("off", className="rv")], className="rs")
    hit = armed and ((side > 0 and value <= os_) or (side < 0 and value >= ob))
    lo_col = T.UP if armed and side > 0 else T.NEUTRAL
    hi_col = T.DOWN if armed and side < 0 else T.NEUTRAL
    dot = (T.UP if side > 0 else T.DOWN) if hit else T.INK_2
    track = [html.Div(className="rs-zone", style={"left": "0", "width": f"{os_:.1f}%", "background": lo_col,
                                                  "opacity": 0.45 if armed and side > 0 else 0.2}),
             html.Div(className="rs-zone", style={"left": f"{ob:.1f}%", "width": f"{100 - ob:.1f}%",
                                                  "background": hi_col, "opacity": 0.45 if armed and side < 0 else 0.2}),
             html.Div(className="rs-mark", style={"left": f"{os_:.1f}%"}),
             html.Div(className="rs-mark", style={"left": f"{ob:.1f}%"}),
             html.Div(className="mt-dot", style={"left": f"{max(0.0, min(100.0, value)):.1f}%", "background": dot})]
    return html.Div([html.Span(tf, className="tf"), html.Div(track, className="rs-track"),
                     html.Span(f"{value:.1f}", className="rv"),
                     html.Span("ARMED" if armed else "", className="arm")],
                    className="rs armed" if armed else "rs")


def replay_panel(st: dict, events: List[dict], cfg: BacktestConfig):
    """The side panel of the replay: account, score meters, ladder RSI, status, event log."""
    m, d = R.fmt_money, st["digits"]
    n, side = abs(st["npos"]), st["side"]
    if side > 0:
        chip = [html.Span("▲", style={"color": T.UP}), f" LONG {n}"]
    elif side < 0:
        chip = [html.Span("▼", style={"color": T.DOWN}), f" SHORT {n}"]
    else:
        chip = [html.Span("●", style={"color": T.NEUTRAL}), " FLAT"]
    edge = T.UP if side > 0 else T.DOWN if side < 0 else T.AXIS
    px = lambda v: "-" if v is None else R.fmt_price(v, d)
    kv = lambda k, v, cls="": html.Div([html.Div(k, className="k"), html.Div(v, className=("v " + cls).strip())],
                                       className="kv")
    quote = (f"bid {px(st['bid'])} · ask {px(st['ask'])} · spread {st['spread']:.{d}f}"
             if st["spread"] is not None else f"bid {px(st['bid'])}")
    out = [
        html.Div([html.Span(st["symbol"], className="sym"), html.Span(chip, className="chip big")],
                 className="sp-h", style={"borderBottomColor": edge}),
        html.Div(className="kvs", children=[
            kv("Balance", m(st["balance"], False)), kv("Equity", m(st["equity"], False)),
            kv("Floating P/L", m(st["floating"]), _sign(st["floating"])),
            kv("Unit", str(st["basket_units"] or st["units"])), kv("Open lots", f"{st['lots']:+.2f}" if n else "0.00"),
            kv("Avg entry", px(st["avg"]))]),
        html.Div(quote, className="quote"),
    ]
    if st["positions"]:
        out.append(html.Div("positions  " + "   ".join(f"{p['lots']:.2f} @ {px(p['price'])}" for p in st["positions"]),
                            className="quote"))

    # score meters
    o, fcs = st["open_score"], st["fc_score"]
    fmt_w = lambda w: " + ".join(f"{(r if r == mm else (r + mm) / 2):g}·{tf}" for tf, (r, mm) in
                                 sorted(w.items(), key=lambda kv_: TF_SECONDS.get(kv_[0], 0), reverse=True)) or "none"
    if o >= cfg.entry_s:
        oc = ("▲", "BUY zone", T.UP)
    elif o <= -cfg.entry_s:
        oc = ("▼", "SELL zone", T.DOWN)
    else:
        oc = ("●", f"wait · inside ±{cfg.entry_s:g}", T.NEUTRAL)
    out.append(score_meter("OPEN score", T.SCORE_COLOR["open_score"], fmt_w(cfg.open_weights), o,
                           st["ranges"]["open"], cfg.entry_s, (f"SELL -{cfg.entry_s:g}", f"BUY +{cfg.entry_s:g}"),
                           oc, (T.DOWN, T.UP)))
    fc_col = T.SCORE_COLOR["fc_score"]
    if side > 0:
        fc_chip = ("✕", "closes the LONG", fc_col) if fcs <= -cfg.force_close_s else ("●", "hold", T.NEUTRAL)
    elif side < 0:
        fc_chip = ("✕", "closes the SHORT", fc_col) if fcs >= cfg.force_close_s else ("●", "hold", T.NEUTRAL)
    elif fcs >= cfg.entry_agree_s:
        fc_chip = ("▲", "agrees with a BUY", T.UP)
    elif fcs <= -cfg.entry_agree_s:
        fc_chip = ("▼", "agrees with a SELL", T.DOWN)
    else:
        fc_chip = ("●", "no agreement", T.NEUTRAL)
    out.append(score_meter("FORCE-CLOSE score", fc_col, fmt_w(cfg.fc_weights), fcs, st["ranges"]["fc"],
                           cfg.force_close_s, (f"close long -{cfg.force_close_s:g}", f"close short +{cfg.force_close_s:g}"),
                           fc_chip, (fc_col, fc_col), agree=cfg.entry_agree_s))
    if st["has_book"]:
        bks, bk_col = st["book_score"], T.SCORE_COLOR["book_score"]
        armed = n > 0 and st["target"] is not None and st["floating"] > st["target"]
        fire = armed and ((side > 0 and bks <= -cfg.book_s) or (side < 0 and bks >= cfg.book_s))
        bk_chip = ("◆", "books the profit", bk_col) if fire else \
            ("●", "armed - in profit" if armed else f"needs profit > {m(st['target'] or cfg.profit_protect_usd_per_unit, False)}",
             T.NEUTRAL)
        out.append(score_meter("BOOK score", bk_col, fmt_w(cfg.book_weights), bks, st["ranges"]["book"], cfg.book_s,
                               (f"book long -{cfg.book_s:g}", f"book short +{cfg.book_s:g}"), bk_chip, (bk_col, bk_col)))

    # ladder RSI tiers
    tiers = st["tiers"]
    rows = []
    for k, tf in enumerate(cfg.ladder_tfs[:max(len(cfg.ladder_tfs), 0)]):
        val = st["rsi"][k] if k < len(tiers) and k < len(st["rsi"]) else None
        rows.append(rsi_row(tf, val, cfg.rsi_oversold, cfg.rsi_overbought, st["armed"] == k and val is not None, side))
    out.append(html.Div(className="sec", children=[
        html.Div([html.Span("Ladder RSI"),
                  html.Span(f"add a long at ≤ {cfg.rsi_oversold:g} · a short at ≥ {cfg.rsi_overbought:g}", className="f")],
                 className="sec-h"), *rows]))

    # status + cooldown
    total = max(cfg.reentry_cooldown_s, 1e-9)
    left = st["cooldown_s"]
    cool = html.Div(className="cool", children=[
        html.Span("Re-entry cooldown", className="k"),
        html.Div(html.Div(style={"width": f"{min(100.0, left / total * 100):.1f}%"}), className="cool-bar"),
        html.Span(f"{int(left // 60)}:{int(left % 60):02d} left" if left > 0 else "clear", className="rv")])
    out.append(html.Div(className="sec", children=[
        html.Div(html.Span("Status"), className="sec-h"),
        *[html.Div(s, className="stat") for s in st["status"]], cool]))

    # event log
    def row(ev):
        tag = ev["tag"]
        if tag in ("BUY", "SELL"):
            g = html.Span("▲" if tag == "BUY" else "▼", style={"color": T.UP if tag == "BUY" else T.DOWN})
        elif tag == "ADD":
            g = html.Span("△" if ev["text"].startswith("BUY") else "▽",
                          style={"color": T.UP if ev["text"].startswith("BUY") else T.DOWN})
        elif tag == "CLOSE":
            g = html.Span("■", style={"color": T.DOWN if " -$" in ev["text"] else T.UP})
        else:
            g = html.Span("○", style={"color": T.INK_MUTED})
        return html.Div([html.Span(ev["time"], className="lt"), html.Span([g, " " + tag], className="lg"),
                         html.Span(ev["text"], className="lx"), html.Span(ev["detail"], className="ld")],
                        className="ev", title=f"{ev['date']} {ev['time']} UTC")
    out.append(html.Div(className="sec log", children=[
        html.Div([html.Span("Event log"), html.Span("latest first", className="f")], className="sec-h"),
        html.Div([row(ev) for ev in events] or [html.Div("Nothing has happened yet in this window.", className="stat")],
                 className="evs")]))
    return out


def _panel_empty(text: str = "Run a backtest, then press Play - or click a basket on the Results tab."):
    return [html.Div([html.Span("Replay", className="sym")], className="sp-h"),
            html.Div(text, className="stat", style={"padding": "14px"})]


def replay_clock(t_ms: Optional[int]):
    if t_ms is None:
        return [html.Span("----.--.--", className="d"), html.Span("--:--:--", className="t"), html.Span("UTC", className="z")]
    d = store.ms_to_dt(t_ms)
    return [html.Span(f"{d:%a %Y-%m-%d}", className="d"), html.Span(f"{d:%H:%M:%S}", className="t"),
            html.Span("UTC", className="z")]


def replay_head(sess: R.ReplaySession) -> str:
    w = sess.window
    f = lambda ms: f"{store.ms_to_dt(ms):%Y-%m-%d %H:%M}"
    n = len(sess.basket_marks())
    how = {"basket_open": f"engine started on basket #{w.basket_base}'s entry ({f(w.anchor_ms)})",
           "flat": "engine started flat at the window start",
           "run_start": "engine started at the start of the backtest"}[w.kind]
    return (f"Replay window {f(w.visible_from_ms)} → {f(w.end_ms)} UTC · {n} basket{'s' if n != 1 else ''} open in it · "
            f"same trades as the full run ({how})")


# ───────────────────────────── page chrome ─────────────────────────────

CSS = T.CSS + """
/* ── Backtest Studio ── */
body { overflow-y: scroll; }
::-webkit-scrollbar { width: 8px; height: 8px; } ::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(212,168,67,0.28); border-radius: 8px; }
::selection { background: rgba(212,168,67,0.3); color: var(--ink); }
.gradient-bar { height: 3px; background: linear-gradient(90deg, #d4a843, #4a8ecc, #f0e6c0, #4a8ecc, #d4a843); }
.hdr { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 24px;
  background: linear-gradient(180deg, rgba(6,11,24,0.97), rgba(10,16,37,0.95)); border-bottom: 1px solid var(--border); }
.hdr-l { display: flex; align-items: center; gap: 12px; }
.hdr .mascot { width: 44px; height: 44px; object-fit: contain; filter: drop-shadow(0 0 8px rgba(212,168,67,0.35)); }
.hdr .mark { font-size: 18px; font-weight: 800; letter-spacing: 3.5px;
  background: linear-gradient(135deg, #f0e6c0, #d4a843, #4a8ecc); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent; background-clip: text; }
.hdr .tag { font-size: 10px; color: var(--muted); letter-spacing: 1.8px; text-transform: uppercase; margin-top: 1px; }
.hdr-r { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.lab { font-size: 10px; font-weight: 600; color: var(--muted); letter-spacing: 1.2px; text-transform: uppercase; white-space: nowrap; }
.badge { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--ink); padding: 4px 12px; border-radius: 8px;
  background: rgba(192,168,100,0.10); border: 1px solid rgba(192,168,100,0.25); margin-right: 8px; }
.badge.ghost { font-weight: 500; letter-spacing: 0.3px; color: var(--ink-2); background: transparent; }
.ctl { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 20px; padding: 12px 24px 10px; background: #0a1025;
  border-bottom: 1px solid var(--border); }
.grp { display: flex; flex-direction: column; gap: 4px; } .grp .row { display: flex; align-items: center; gap: 8px; }
.grow { flex: 1 1 auto; }
.btn, .tr-btns button, .seg button, .go { font: inherit; font-size: 12.5px; color: var(--ink-2); background: var(--surface);
  border: 1px solid var(--axis); border-radius: 8px; padding: 7px 14px; cursor: pointer; white-space: nowrap; }
.btn:hover, .tr-btns button:hover, .go:hover { background: var(--surface-2); color: var(--ink); }
.btn:focus-visible, .tr-btns button:focus-visible, .go:focus-visible, .segr input:focus-visible + span { outline: 2px solid var(--accent); outline-offset: 1px; }
.btn.primary { color: #0c1328; background: var(--accent); border-color: var(--accent); font-weight: 700; padding: 8px 22px; }
.btn.primary:hover { background: #e3bb5c; color: #0c1328; }
.btn.primary[data-dash-is-loading="true"] { opacity: 0.55; pointer-events: none; }
.btn .caret { margin-left: 8px; color: var(--muted); }
.seg button { border-radius: 0; border-width: 0 1px 0 0; padding: 6px 11px; }
.run-status { font-size: 12.5px; color: var(--ink-2); max-width: 520px; text-align: right; min-height: 18px; align-self: center; }
.run-status .s-err { color: var(--ink); border-left: 3px solid var(--down); padding-left: 8px; display: inline-block; text-align: left; }
.run-status .s-ok::before { content: "\\2713  "; color: var(--up); }
.run-status .s-warn { color: var(--ink-2); font-size: 12px; border-left: 3px solid var(--accent); padding-left: 8px; margin-top: 3px; text-align: left; }
.run-status[data-dash-is-loading="true"] > * { display: none; }
.run-status[data-dash-is-loading="true"]::after { content: "Running the backtest \\2026"; color: var(--ink); }
.run-status[data-dash-is-loading="true"]::before { content: ""; display: inline-block; width: 12px; height: 12px; margin-right: 8px;
  border: 2px solid var(--axis); border-top-color: var(--accent); border-radius: 50%; vertical-align: -2px; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.recap { padding: 6px 24px; font-size: 12px; color: var(--muted); background: #0a1025; border-bottom: 1px solid var(--border); }
.recap b { color: var(--ink-2); font-weight: 600; } .recap .mod { color: var(--ink); border: 1px solid var(--accent); border-radius: 8px; padding: 0 7px; margin-right: 8px; font-size: 11px; }
.recap .w { display: block; color: var(--ink-2); border-left: 3px solid var(--accent); padding-left: 8px; margin-top: 4px; }
.params { display: none; padding: 14px 24px 16px; background: var(--surface); border-bottom: 1px solid var(--border); }
.params.open { display: block; }
.prow { display: flex; flex-wrap: wrap; gap: 14px 26px; align-items: flex-start; margin-bottom: 12px; }
.fld { display: flex; flex-direction: column; gap: 5px; } .fld .hint { font-size: 11px; color: var(--muted); }
.num, .txt { font: inherit; font-size: 13px; color: var(--ink); background: var(--page); border: 1px solid var(--axis); border-radius: 8px;
  padding: 6px 8px; font-variant-numeric: tabular-nums; }
.num:focus, .txt:focus { outline: none; border-color: var(--accent); } .num:invalid { border-color: var(--down); }
.txt { width: 168px; } input::placeholder { color: #56607e; }
/* segmented radios / toggle chips: the input is hidden, the span after it is the control */
.segr { display: inline-flex; border: 1px solid var(--axis); border-radius: 8px; overflow: hidden; background: var(--surface); }
.segr label { display: inline-flex; margin: 0; cursor: pointer; position: relative; }
.segr input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.segr label span { padding: 6px 12px; font-size: 12.5px; color: var(--ink-2); border-right: 1px solid var(--axis); white-space: nowrap; }
.segr label:last-child span { border-right: 0; }
.segr label:hover span { background: var(--surface-2); color: var(--ink); }
.segr input:checked + span { background: var(--surface-2); color: var(--ink); font-weight: 650; box-shadow: inset 0 -2px 0 var(--accent); }
.tabs-wrap { padding: 0 24px; background: #0a1025; border-bottom: 1px solid var(--border); }
.tab-content, .tabs-wrap .tab-container + div { display: none; }
.pane { padding: 18px 24px 40px; max-width: 1800px; margin: 0 auto; }
.pane.off { height: 0; padding-top: 0; padding-bottom: 0; overflow: hidden; visibility: hidden; }
.res-body.off { display: none; }
.res-title { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 4px; }
.res-title h1 { font-size: 20px; font-weight: 650; margin: 0; } .res-title .sub { color: var(--ink-2); font-size: 12.5px; }
p.lede { color: var(--ink-2); margin: 2px 0 14px; max-width: 1100px; font-size: 13px; }
#res-tiles[data-dash-is-loading="true"], #res-head[data-dash-is-loading="true"] { opacity: 0.4; transition: opacity 0.2s; }
.empty { max-width: 760px; margin: 30px auto; padding: 22px 26px; } .empty h3 { font-size: 16px; margin: 0 0 8px; } .empty p { color: var(--ink-2); margin: 0 0 8px; }
.note { color: var(--muted); font-size: 12px; margin-left: 10px; }
.key span span { font-size: 12px; }
/* replay: transport */
.transport { padding: 10px 14px 6px; margin-bottom: 12px; }
.tr-row { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px 20px; }
.tr-btns { display: inline-flex; gap: 6px; } .tr-btns button.play { min-width: 96px; color: #0c1328; background: var(--accent); border-color: var(--accent); font-weight: 700; }
.tr-btns button.play:hover { background: #e3bb5c; color: #0c1328; }
.clock { display: flex; align-items: baseline; gap: 10px; font-variant-numeric: tabular-nums; }
.clock .d { color: var(--ink-2); font-size: 13px; } .clock .t { font-size: 26px; font-weight: 680; letter-spacing: 0.5px; color: var(--ink); }
.clock .z { color: var(--muted); font-size: 11px; letter-spacing: 1.2px; }
.tr-slider { padding: 10px 2px 0; } .rp-head { color: var(--muted); font-size: 12px; padding: 2px 4px 4px; }
.rp-head .msg { color: var(--ink); border-left: 3px solid var(--accent); padding-left: 8px; margin-left: 10px; }
.rc-slider { padding: 5px 0 !important; } .rc-slider-rail { background: var(--axis) !important; height: 4px; }
.rc-slider-track { background: var(--accent) !important; height: 4px; }
.rc-slider-handle { border: 2px solid var(--accent) !important; background: var(--surface) !important; opacity: 1 !important; box-shadow: none !important; }
.rc-slider-dot { display: none; } .rc-slider-mark-text { color: var(--muted) !important; font-size: 11px; }
.rc-slider-mark { top: 16px; }
.rp-grid { display: grid; grid-template-columns: minmax(0, 1fr) 396px; gap: 12px; height: calc(100vh - 354px); min-height: 620px; }
.rp-chart { display: flex; flex-direction: column; min-height: 0; padding: 6px 6px 2px; }
.rp-chart .key { margin: 2px 8px 0; font-size: 12px; } .rp-chart .dash-graph { flex: 1 1 auto; min-height: 0; }
/* replay: side panel */
.sp { padding: 0; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.sp-h { display: flex; justify-content: space-between; align-items: center; padding: 9px 14px; border-bottom: 2px solid var(--axis); }
.sp-h .sym { font-weight: 700; letter-spacing: 1px; font-size: 14px; }
.chip { font-size: 11px; font-weight: 650; color: var(--ink); background: var(--page); border: 1px solid var(--axis); border-radius: 9px;
  padding: 2px 9px; white-space: nowrap; } .chip.big { font-size: 12.5px; padding: 3px 12px; letter-spacing: 0.5px; }
.kvs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--grid); border-bottom: 1px solid var(--grid); }
.kv { background: var(--surface); padding: 7px 14px 8px; } .kv .k { font-size: 10px; color: var(--muted); letter-spacing: 0.9px; text-transform: uppercase; }
.kv .v { font-size: 15px; font-weight: 650; color: var(--ink); font-variant-numeric: tabular-nums; margin-top: 1px; }
.quote { padding: 5px 14px; font-size: 11.5px; color: var(--ink-2); border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; white-space: pre-wrap; }
.mt { padding: 8px 14px 9px; border-bottom: 1px solid var(--grid); }
.mt-h { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px; }
.mt-h .t, .sec-h { font-size: 11px; font-weight: 700; letter-spacing: 0.6px; color: var(--ink-2); text-transform: uppercase;
  display: flex; align-items: center; gap: 7px; min-width: 0; }
.mt-h .t i { width: 14px; height: 3px; border-radius: 2px; flex: none; }
.f { font-size: 10.5px; font-weight: 400; color: var(--muted); letter-spacing: 0; text-transform: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mt-b { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 10px; align-items: center; }
.mt-v { font-size: 20px; font-weight: 700; text-align: right; color: var(--ink); font-variant-numeric: tabular-nums; }
.mt-lab { position: relative; height: 14px; font-size: 10px; color: var(--muted); } .mt-lab.low { margin-top: 3px; }
.mt-lab span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
.mt-track, .rs-track { position: relative; height: 12px; background: var(--page); border: 1px solid var(--axis); border-radius: 6px; }
.mt-band { position: absolute; top: 0; bottom: 0; background: var(--muted); opacity: 0.16; }
.mt-fill { position: absolute; top: 2px; bottom: 2px; border-radius: 3px; }
.mt-zero { position: absolute; top: -2px; bottom: -2px; width: 1px; background: var(--muted); }
.mt-thr { position: absolute; top: -4px; bottom: -4px; width: 2px; margin-left: -1px; border-radius: 1px; }
.mt-agree { position: absolute; bottom: -5px; width: 0; height: 0; margin-left: -4px; border-left: 4px solid transparent;
  border-right: 4px solid transparent; border-bottom: 5px solid var(--ink-2); }
.mt-dot { position: absolute; top: 50%; width: 12px; height: 12px; border-radius: 50%; transform: translate(-50%, -50%); border: 2px solid var(--surface); }
.sec { padding: 8px 14px 9px; border-bottom: 1px solid var(--grid); } .sec-h { justify-content: space-between; margin-bottom: 5px; }
.rs { display: grid; grid-template-columns: 30px minmax(0, 1fr) 38px 46px; gap: 8px; align-items: center; padding: 3px 0; }
.rs .tf { font-size: 11.5px; font-weight: 650; color: var(--ink-2); } .rs.armed .tf { color: var(--ink); }
.rs-track { height: 8px; border-radius: 4px; } .rs-track.off { opacity: 0.35; }
.rs-zone { position: absolute; top: 0; bottom: 0; } .rs-mark { position: absolute; top: -3px; bottom: -3px; width: 1px; background: var(--ink-2); }
.rs .mt-dot { width: 10px; height: 10px; }
.rv { font-size: 12px; color: var(--ink); text-align: right; font-variant-numeric: tabular-nums; }
.arm { font-size: 9.5px; font-weight: 700; letter-spacing: 0.6px; color: var(--ink); } .rs.armed .arm { border: 1px solid var(--accent); border-radius: 7px; padding: 0 4px; text-align: center; }
.stat { font-size: 12px; color: var(--ink-2); padding: 1px 0; }
.cool { display: grid; grid-template-columns: auto minmax(0, 1fr) 62px; gap: 8px; align-items: center; margin-top: 5px; }
.cool .k { font-size: 11px; color: var(--muted); } .cool-bar { height: 6px; background: var(--page); border: 1px solid var(--axis); border-radius: 3px; overflow: hidden; }
.cool-bar div { height: 100%; background: var(--ink-2); }
.log { flex: 1 1 auto; min-height: 90px; display: flex; flex-direction: column; border-bottom: 0; }
.evs { overflow-y: auto; flex: 1 1 auto; min-height: 0; margin-right: -8px; padding-right: 8px; }
.ev { display: grid; grid-template-columns: 54px 62px minmax(0, 1fr); column-gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--grid); font-size: 12px; }
.ev .lt { color: var(--muted); font-variant-numeric: tabular-nums; } .ev .lg { color: var(--ink-2); font-weight: 650; font-size: 11px; }
.ev .lx { color: var(--ink); font-variant-numeric: tabular-nums; } .ev .ld { grid-column: 3; color: var(--muted); font-size: 11px; }
/* widgets that carry their own (light) styles */
.DateRangePickerInput { background: var(--surface); border: 1px solid var(--axis); border-radius: 8px; overflow: hidden; }
.DateInput { background: transparent; width: 104px; }
.DateInput_input { background: var(--surface); color: var(--ink); font: inherit; font-size: 13px; padding: 6px 8px 4px; border-bottom: 2px solid transparent;
  font-variant-numeric: tabular-nums; }
.DateInput_input__focused { border-bottom-color: var(--accent); } .DateRangePickerInput_arrow_svg { fill: var(--muted); width: 18px; height: 18px; }
.DateInput_fang { display: none; } .DateRangePicker_picker { background: var(--surface-2); z-index: 60; border: 1px solid var(--axis); border-radius: 10px; }
.DayPicker, .DayPicker__horizontal, .CalendarMonth, .CalendarMonthGrid, .DayPicker_transitionContainer { background: var(--surface-2); }
.DayPicker__withBorder { box-shadow: none; } .CalendarMonth_caption { color: var(--ink); font-size: 14px; } .DayPicker_weekHeader { color: var(--muted); }
.DayPicker table { width: auto; } .DayPicker th, .DayPicker td { padding: 0; text-align: center; white-space: normal; position: static; }
.DayPicker th { background: transparent; border: 0; }
.CalendarDay__default { background: var(--surface-2); border: 1px solid var(--grid); color: var(--ink); }
.CalendarDay__default:hover { background: var(--axis); border-color: var(--axis); color: var(--ink); }
.CalendarDay__blocked_out_of_range, .CalendarDay__blocked_out_of_range:hover { background: var(--surface); color: #46506e; border-color: var(--grid); }
.CalendarDay__selected_span, .CalendarDay__hovered_span, .CalendarDay__hovered_span:hover { background: rgba(212,168,67,0.16); border-color: rgba(212,168,67,0.22); color: var(--ink); }
.CalendarDay__selected, .CalendarDay__selected:active, .CalendarDay__selected:hover { background: var(--accent); border-color: var(--accent); color: #0c1328; }
.DayPickerNavigation_button__default { background: var(--surface); border-color: var(--axis); } .DayPickerNavigation_button__default:hover { border-color: var(--accent); }
.DayPickerNavigation_svg__horizontal { fill: var(--ink-2); } .DayPickerKeyboardShortcuts_buttonReset { display: none; }
.dash-table-container .dash-spreadsheet-container table { width: 100%; }
.dash-table-container th, .dash-table-container td { position: static; }
.dash-table-container .dash-filter input { color: var(--ink) !important; text-align: left !important; font-size: 12px !important; }
.dash-table-container .dash-filter input::placeholder { color: #56607e !important; }
.dash-table-container .previous-next-container { color: var(--ink-2); padding: 8px 4px 2px; }
.dash-table-container .previous-next-container button { color: var(--ink-2) !important; background: transparent; }
.dash-table-container .previous-next-container button:hover { color: var(--accent) !important; }
.dash-table-container .previous-next-container button:disabled { color: #46506e !important; }
.dash-table-container input.current-page { background: var(--surface) !important; color: var(--ink) !important; border-bottom: 1px solid var(--axis) !important; }
.dash-table-container .page-number, .dash-table-container .last-page { color: var(--ink-2); }
.dash-table-container .dash-spreadsheet tr:hover td { background: var(--surface-2) !important; cursor: pointer; }
.dash-table-container .column-header--sort { color: var(--muted) !important; }
.dash-table-tooltip { background: var(--surface-2) !important; color: var(--ink) !important; border: 1px solid var(--axis) !important; }
@media (max-width: 1180px) { .rp-grid { grid-template-columns: 1fr; height: auto; } .rp-chart { height: 640px; } .sp { max-height: 720px; } }
"""

INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>""" + CSS + """</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
"""

_TAB = {"background": "transparent", "color": T.INK_MUTED, "border": "none", "borderBottom": "2px solid transparent",
        "padding": "11px 26px", "fontSize": "12px", "fontWeight": "600", "letterSpacing": "1.5px", "fontFamily": T.FONT}
_TAB_ON = dict(_TAB, color=T.INK, borderBottom=f"2px solid {T.ACCENT}", fontWeight="700")
_GRAPH_CFG = {"displaylogo": False, "scrollZoom": True, "responsive": True,
              "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}

# Lets a tick through only when the previous frame has been acknowledged (or after 5 s of silence).
_GATE_JS = """
function(n, pb, pulse) {
    var now = Date.now();
    if (pulse && pb && pb.ack !== pulse.n && (now - pulse.w) < 5000) { return window.dash_clientside.no_update; }
    return {n: ((pulse && pulse.n) || 0) + 1, w: now};
}
"""
_TABS_JS = "function(v) { return [v === 'replay' ? 'pane off' : 'pane', v === 'replay' ? 'pane' : 'pane off']; }"
_TOGGLE_JS = "function(n) { return (n || 0) % 2 === 1 ? 'params open' : 'params'; }"


def build_layout(studio: Studio):
    """The whole page. Called on every page load, so dates follow the store."""
    sym = studio.default_symbol()
    d = studio.defaults(sym)
    sp = studio.span(sym)
    start, end = studio.default_dates(sym)
    net = d["netting"]
    tfs = d["tf_choices"]
    table_style = [{"if": {"column_id": c}, "textAlign": "left"} for c in ("basket", "open", "side", "reason")]
    return html.Div(className="studio", children=[
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="st-run"), dcc.Store(id="st-rq"), dcc.Store(id="st-pb"), dcc.Store(id="st-pulse"),
        dcc.Store(id="st-auto"), dcc.Store(id="st-mk"),
        dcc.Interval(id="rp-tick", interval=TICK_MS, disabled=True),
        html.Div(className="gradient-bar"),
        html.Div(className="hdr", children=[
            html.Div(className="hdr-l", children=[
                html.Img(src="/_studio/mascot.png", className="mascot", alt=""),
                html.Div([html.Div("ALCADEIAS", className="mark"),
                          html.Div("Backtest Studio · the live strategy on real ticks", className="tag")])]),
            html.Div(className="hdr-r", children=[
                _lab("Variant"), html.Span(d["variant"].upper(), className="badge"),
                _lab("Exit"), html.Span("slope profit-book" if net else "+$ per unit target", className="badge ghost"),
                _lab("Engine"), html.Span("tick replay · 1 s poll · forming-bar indicators", className="badge ghost")])]),

        # ── controls: one row above everything it scopes ──
        html.Div(className="ctl", children=[
            html.Div([_lab("Symbol"), _seg("ctl-symbol", [(s, s) for s in studio.symbols()], sym)], className="grp"),
            html.Div([_lab("Period · UTC days, both included"), html.Div(className="row", children=[
                dcc.DatePickerRange(id="ctl-dates", display_format="YYYY-MM-DD", start_date=start, end_date=end,
                                    min_date_allowed=sp[0] if sp else None,
                                    max_date_allowed=(sp[1] + timedelta(days=1)) if sp else None,
                                    initial_visible_month=end, minimum_nights=0, updatemode="bothdates",
                                    start_date_placeholder_text="start", end_date_placeholder_text="end"),
                html.Span(className="seg", children=[
                    html.Button("7D", id="ctl-p7", n_clicks=0, title="The last 7 days of data"),
                    html.Button("30D", id="ctl-p30", n_clicks=0, title="The last 30 days of data"),
                    html.Button("3M", id="ctl-p90", n_clicks=0, title="The last 3 months of data"),
                    html.Button("All", id="ctl-pall", n_clicks=0, title="Everything in the store")])])], className="grp"),
            html.Div([_lab("Start balance, USD"), _number("ctl-balance", 2000, step=100, lo=0, width=104)], className="grp"),
            html.Div([_lab(" "), html.Button(["Strategy parameters", html.Span("▾", className="caret")],
                                                 id="prm-toggle", n_clicks=0, className="btn")], className="grp"),
            html.Div(className="grow"),
            html.Div(id="run-status", className="run-status", children=_status(
                f"{sym}: ticks from {sp[0]} to {sp[1]}" if sp else "No tick data in the store yet - run `python -m backtesting data`.")),
            html.Button("Run backtest", id="run-btn", n_clicks=0, className="btn primary"),
        ]),
        html.Div(id="prm-recap", className="recap"),
        html.Div(id="prm-panel", className="params", children=[
            html.Div(className="prow", children=[
                _field("OPEN timeframes", _chips("prm-open-tfs", tfs, d["open_tfs"]),
                       hint="fresh entry + the ladder gate"),
                _field("FORCE-CLOSE timeframes", _chips("prm-fc-tfs", tfs, d["fc_tfs"]),
                       hint="reversal exit + entry agreement"),
                _field("BOOK timeframes", _chips("prm-book-tfs", tfs, d["book_tfs"]), hide=not net,
                       hint="profit-book once in profit")]),
            html.Div(className="prow", children=[
                _field("ENTRY_S", _number("prm-entry-s", d["entry_s"]), hint="|open score| to enter"),
                _field("ENTRY_AGREE_S", _number("prm-agree-s", d["entry_agree_s"]), hint="force-close score must agree"),
                _field("FORCE_CLOSE_S", _number("prm-fc-s", d["force_close_s"]), hint="against the basket"),
                _field("LADDER_S", _number("prm-ladder-s", d["ladder_s"]), hint="adds blocked beyond"),
                _field("BOOK_S", _number("prm-book-s", d["book_s"]), hide=not net, hint="against, in profit"),
                _field("Target, $ per unit", _number("prm-target", d["target"], step=0.25), hide=net,
                       hint="close above this profit"),
                _field("Protect, $ per unit", _number("prm-protect", d["protect"], step=0.25), hide=not net,
                       hint="profit needed to book"),
                _field("Ladder RSI oversold", _number("prm-rsi-os", d["rsi_os"], hi=100), hint="add to a long at or below"),
                _field("Ladder RSI overbought", _number("prm-rsi-ob", d["rsi_ob"], hi=100), hint="add to a short at or above"),
                _field("Max ladder adds", _number("prm-max-adds", d["max_adds"], hi=MAX_LADDER_ADDS),
                       hint=" → ".join(d["ladder_tfs"][:MAX_LADDER_ADDS])),
                _field("Re-entry cooldown, s", _number("prm-cooldown", d["cooldown"], step=10), hint="after any close")]),
            html.Div(className="prow", style={"marginBottom": 0}, children=[
                html.Button("Reset to the live values", id="prm-reset", n_clicks=0, className="btn"),
                html.Span(f"Leverage 1:{d['leverage']:g} · lots, unit step and the trading window come from symbols.json · "
                          "scores are raw sums: a section with N timeframes ranges ±2N, so re-check its thresholds when "
                          "you change its timeframes.", className="note", style={"alignSelf": "center"})]),
        ]),
        html.Div(className="tabs-wrap", children=dcc.Tabs(
            id="tabs", value="results", children=[
                dcc.Tab(label="RESULTS", value="results", style=_TAB, selected_style=_TAB_ON),
                dcc.Tab(label="REPLAY", value="replay", style=_TAB, selected_style=_TAB_ON)],
            style={"border": "none", "background": "transparent", "width": "320px"})),

        # ── results ──
        html.Div(id="pane-results", className="pane", children=[
            html.Div(id="res-head"),
            html.Div(id="res-tiles", children=_empty_results()),
            html.Div(id="res-body", className="res-body off", children=[
                html.H2("Market, trades and account"),
                html.P("Every fill at the price it filled at; equity, open lots and the section scores share the time "
                       "axis. Drag to pan, scroll to zoom - the chart loads the range you look at.", className="lede"),
                _legend_key(),
                html.Div(className="controls", children=[
                    _lab("Candles"), _seg("mk-tf", [(t, t) for t in MARKET_TFS], "M15"),
                    _lab("Show the last"), _seg("mk-span", [(k, k) for k, _ in MARKET_SPANS], "1W"),
                    html.Span(id="mk-note", className="note")]),
                html.Div(className="card flush", children=dcc.Graph(
                    id="mk-graph", figure=_blank_fig(), config=_GRAPH_CFG, style={"height": "900px"})),
                html.H2("Baskets"),
                html.P("One row per basket (a fresh entry plus its ladder adds, closed together). Click a row to "
                       "replay it. Filters take numbers and comparisons - try < 0 under P/L, > 10m under Held, "
                       "force under Exit.", className="lede"),
                html.Div(className="card", children=[
                    dash_table.DataTable(
                        id="tbl", columns=[{"name": n, "id": i} for i, n in TABLE_COLS], data=[],
                        page_current=0, page_size=PAGE_SIZE, page_action="custom", page_count=1,
                        sort_action="custom", sort_mode="single", sort_by=[],
                        filter_action="custom", filter_query="",
                        filter_options={"case": "insensitive", "placeholder_text": "filter"},
                        style_as_list_view=True, cell_selectable=True,
                        style_table={"overflowX": "auto"},
                        style_header={"backgroundColor": T.SURFACE, "color": T.INK_MUTED, "fontWeight": "600",
                                      "border": "none", "borderBottom": f"1px solid {T.AXIS}", "fontFamily": T.FONT,
                                      "fontSize": "12px", "padding": "7px 10px", "textAlign": "right"},
                        style_filter={"backgroundColor": T.PAGE, "color": T.INK, "border": "none",
                                      "borderBottom": f"1px solid {T.GRID}", "padding": "2px 10px"},
                        style_cell={"backgroundColor": T.SURFACE, "color": T.INK, "border": "none",
                                    "borderBottom": f"1px solid {T.GRID}", "fontFamily": T.FONT, "fontSize": "12.5px",
                                    "padding": "7px 10px", "textAlign": "right", "fontVariantNumeric": "tabular-nums"},
                        style_header_conditional=table_style, style_cell_conditional=table_style,
                        style_data_conditional=_table_rules(None),
                        tooltip_header={"held": "Time from the first entry to the close. Filter: > 10m, < 90s, > 2h",
                                        "mae": "The worst floating P/L seen while the basket was open",
                                        "pnl": "Realised P/L of the basket. Filter: < 0, > 1.5",
                                        "reason": "target · force-close · profit-book · stop-out"},
                        tooltip_delay=300, tooltip_duration=None),
                    html.Div(id="tbl-note", className="note", style={"margin": "8px 0 0"})]),
            ]),
        ]),

        # ── replay ──
        html.Div(id="pane-replay", className="pane off", children=[
            html.Div(className="card transport", children=[
                html.Div(className="tr-row", children=[
                    html.Div([_lab("Transport"), html.Div(className="tr-btns", children=[
                        html.Button("« Basket", id="rp-prev", n_clicks=0, title="Jump to the previous basket entry"),
                        html.Button("‹ Step", id="rp-back", n_clicks=0, title="One poll back"),
                        html.Button("▶︎ Play", id="rp-play", n_clicks=0, className="play"),
                        html.Button("Step ›", id="rp-fwd", n_clicks=0, title="One poll forward"),
                        html.Button("Basket »", id="rp-next", n_clicks=0, title="Jump to the next basket entry")])],
                             className="grp"),
                    html.Div([_lab("Speed · x real time"), _seg("rp-speed", [(s, f"{s}x") for s in SPEEDS], 20)],
                             className="grp"),
                    html.Div([_lab("Candles"), _seg("rp-tf", [(t, t) for t in R.CANDLE_TFS], "M1")], className="grp"),
                    html.Div([_lab("Jump to · UTC"), html.Div(className="row", children=[
                        dcc.Input(id="rp-goto", type="text", placeholder="2026-11-09 06:15", className="txt",
                                  debounce=True),
                        html.Button("Go", id="rp-go", n_clicks=0, className="go")])], className="grp"),
                    html.Div(className="grow"),
                    html.Div(id="rp-clock", className="clock", children=replay_clock(None))]),
                html.Div(className="tr-slider", children=dcc.Slider(
                    id="rp-slider", min=0, max=3600, step=1, value=0, marks={}, updatemode="mouseup")),
                html.Div([html.Span(id="rp-head"), html.Span(id="rp-msg")], className="rp-head")]),
            html.Div(className="rp-grid", children=[
                html.Div(className="card flush rp-chart", children=[
                    _legend_key(replay=True),
                    dcc.Graph(id="rp-graph", figure=_blank_fig("Run a backtest to load the replay."), responsive=True,
                              config={"displayModeBar": False, "scrollZoom": True, "responsive": True},
                              style={"height": "100%"})]),
                html.Div(id="rp-panel", className="card sp", children=_panel_empty())]),
        ]),
        html.Div("Times are UTC (Exness server time). A basket is one fresh entry plus its ladder adds, closed together. "
                 "Past results on historical ticks are not a forecast.", className="foot", style={"margin": "0 24px 24px"}),
    ])


def _table_rules(basket: Optional[int]) -> List[dict]:
    """Row marks: a coloured rule beside the P/L (the sign in the text says the same), the replayed row tinted."""
    rules = [{"if": {"filter_query": '{pnl} contains "+"', "column_id": "pnl"}, "borderLeft": f"3px solid {T.UP}"},
             {"if": {"filter_query": '{pnl} contains "-"', "column_id": "pnl"}, "borderLeft": f"3px solid {T.DOWN}"},
             {"if": {"state": "active"}, "backgroundColor": T.SURFACE_2, "border": f"1px solid {T.AXIS}"},
             {"if": {"state": "selected"}, "backgroundColor": T.SURFACE_2, "border": "none",
              "borderBottom": f"1px solid {T.GRID}"}]
    if basket is not None:
        rules.append({"if": {"filter_query": f"{{id}} = {int(basket)}"}, "backgroundColor": "rgba(212,168,67,0.10)"})
    return rules


# ───────────────────────────── the app ─────────────────────────────

def create_app(store_dir: Optional[Path] = None) -> Dash:
    """Build the Dash app (``app.studio`` is the ``Studio`` behind it)."""
    studio = Studio(store_dir)
    app = Dash(__name__, title="Alcadeias · Backtest Studio", update_title=None,
               assets_folder=str(Path(__file__).with_name("_studio_assets")), include_assets_files=False)
    app.index_string = INDEX
    app.layout = lambda: build_layout(studio)
    app.studio = studio

    mascot = REPO_ROOT / "assets" / "alcadeias.png"       # read-only: the live dashboard's own image

    @app.server.route("/_studio/mascot.png")
    def _mascot():
        import flask
        if mascot.exists():
            return flask.send_file(str(mascot), mimetype="image/png", max_age=86400)
        return flask.Response(status=404)

    # ── chrome: tabs, the parameter panel, the tick gate (all client-side) ──
    app.clientside_callback(_TABS_JS, Output("pane-results", "className"), Output("pane-replay", "className"),
                            Input("tabs", "value"))
    app.clientside_callback(_TOGGLE_JS, Output("prm-panel", "className"), Input("prm-toggle", "n_clicks"))
    app.clientside_callback(_GATE_JS, Output("st-pulse", "data"), Input("rp-tick", "n_intervals"),
                            State("st-pb", "data"), State("st-pulse", "data"), prevent_initial_call=True)

    # ── a link can carry the state: ?symbol=BTCUSDm&start=2026-11-09&end=2026-11-09&run=1&tab=replay&play=1 ──
    @app.callback(Output("ctl-symbol", "value"), Output("ctl-balance", "value"), Output("st-auto", "data"),
                  Output("tabs", "value"), Output("rp-speed", "value"), Output("rp-tf", "value"),
                  Input("url", "search"))
    def from_url(search):
        q = {k: v[-1] for k, v in parse_qs((search or "").lstrip("?")).items()}
        if not q:
            raise PreventUpdate
        symbol = q.get("symbol") if q.get("symbol") in SYMBOLS else None
        balance = _parse_number(q.get("balance", ""))
        speed = _parse_number(q.get("speed", ""))
        auto = {"symbol": symbol, "start": q.get("start"), "end": q.get("end"), "balance": balance,
                "run": q.get("run") in ("1", "true", "yes"), "play": q.get("play") in ("1", "true", "yes"),
                "basket": int(q["basket"]) if q.get("basket", "").isdigit() else None,
                "at": _parse_time(q.get("at"), None), "n": time.time()}
        return (symbol or no_update, balance if balance else no_update, auto,
                q["tab"] if q.get("tab") in ("results", "replay") else no_update,
                int(speed) if speed in SPEEDS else no_update, q["tf"] if q.get("tf") in R.CANDLE_TFS else no_update)

    @app.callback(Output("ctl-dates", "min_date_allowed"), Output("ctl-dates", "max_date_allowed"),
                  Output("ctl-dates", "initial_visible_month"), Output("ctl-dates", "start_date"),
                  Output("ctl-dates", "end_date"), Output("run-status", "children", allow_duplicate=True),
                  Input("ctl-symbol", "value"), Input("ctl-p7", "n_clicks"), Input("ctl-p30", "n_clicks"),
                  Input("ctl-p90", "n_clicks"), Input("ctl-pall", "n_clicks"), Input("st-auto", "data"),
                  State("ctl-dates", "start_date"), State("ctl-dates", "end_date"), prevent_initial_call=True)
    def dates(symbol, _a, _b, _c, _d, auto, start, end):
        sp = studio.span(symbol)
        if not sp:
            return (None, None, no_update, None, None,
                    _status(f"No tick data for {symbol} in the store - run `python -m backtesting data`.", "err"))
        trig = ctx.triggered_id
        preset = {"ctl-p7": "7D", "ctl-p30": "30D", "ctl-p90": "3M", "ctl-pall": "All"}.get(trig)
        if preset:
            start, end = studio.default_dates(symbol, preset)
        elif trig == "st-auto" and auto and (auto.get("start") or auto.get("end")):
            start, end = auto.get("start") or start, auto.get("end") or end
        if not start or not end:
            start, end = studio.default_dates(symbol)
        clip = lambda s: min(max(pd.Timestamp(str(s)[:10]).date(), sp[0]), sp[1]).isoformat()
        try:
            start, end = clip(start), clip(end)
        except (ValueError, TypeError):
            start, end = studio.default_dates(symbol)
        if end < start:
            start = end
        return (sp[0], sp[1] + timedelta(days=1), end, start, end,
                _status(f"{symbol}: ticks from {sp[0]} to {sp[1]}") if trig == "ctl-symbol" else no_update)

    @app.callback(*[Output(i, "value") for i in PRM_IDS], Input("prm-reset", "n_clicks"),
                  State("ctl-symbol", "value"), prevent_initial_call=True)
    def reset_params(_n, symbol):
        d = studio.defaults(symbol)
        return [d[k] for k in PRM_KEYS]

    @app.callback(Output("prm-recap", "children"), Input("ctl-symbol", "value"), *[Input(i, "value") for i in PRM_IDS])
    def recap(symbol, *vals):
        try:
            text, modified, warn = studio.recap(symbol, dict(zip(PRM_KEYS, vals)))
        except Exception as e:                            # never let a half-typed number break the bar
            return [html.B("Parameters "), f"could not be read ({e})"]
        return [html.Span("modified", className="mod") if modified else html.B("Live parameters  "), text,
                *[html.Span(w, className="w") for w in warn]]

    # ── run ──
    @app.callback(Output("st-run", "data"), Output("run-status", "children"), Output("res-head", "children"),
                  Output("res-tiles", "children"), Output("res-body", "className"), Output("st-rq", "data"),
                  Output("run-btn", "disabled"),
                  Input("run-btn", "n_clicks"), Input("st-auto", "data"),
                  State("ctl-symbol", "value"), State("ctl-dates", "start_date"), State("ctl-dates", "end_date"),
                  State("ctl-balance", "value"), *[State(i, "value") for i in PRM_IDS], prevent_initial_call=True)
    def run(_n, auto, symbol, start, end, balance, *vals):
        rq_extra = {}
        if ctx.triggered_id == "st-auto":
            if not auto or not auto.get("run"):
                raise PreventUpdate
            # the controls are being filled by other callbacks at this very moment: read the link itself
            symbol = auto.get("symbol") or symbol
            d0, d1 = studio.default_dates(symbol)
            start, end = auto.get("start") or start or d0, auto.get("end") or end or d1
            balance = auto.get("balance") or balance
            rq_extra = {k: auto[k] for k in ("basket", "at", "play") if auto.get(k)}
        try:
            cfg, warn = studio.build_config(symbol, start, end, balance, dict(zip(PRM_KEYS, vals)))
            e = studio.run(cfg, warn)
        except (StudioError, R.ReplayError) as err:
            return no_update, _status(str(err), "err"), no_update, no_update, no_update, no_update, False
        except Exception as err:                          # a bug: say so, keep the page alive
            traceback.print_exc(file=sys.stderr)
            return (no_update, _status(f"The backtest failed: {type(err).__name__}: {err}", "err"),
                    no_update, no_update, no_update, no_update, False)
        s = e.summary
        done = (f"{cfg.symbol} {cfg.start} → {(pd.Timestamp(cfg.end) - pd.Timedelta(days=1)).date()}: "
                f"{s['baskets']:,} baskets, net {R.fmt_money(s['net_profit'])} · {e.seconds:.1f} s")
        return ({"id": e.id, "n": time.time()}, _status(done, "ok", e.warnings), results_head(e), results_tiles(e),
                "res-body", dict(rq_extra, run=e.id, n=time.time()), False)

    # ── results: market ──
    @app.callback(Output("mk-graph", "figure"), Output("mk-note", "children"), Output("st-mk", "data"),
                  Input("st-run", "data"), Input("mk-tf", "value"), Input("mk-span", "value"),
                  Input("mk-graph", "relayoutData"), State("st-mk", "data"), prevent_initial_call=True)
    def market(run_, tf, span, relayout, mk):
        e = studio.entry((run_ or {}).get("id"))
        if e is None:
            raise PreventUpdate
        trig = ctx.triggered_id
        same = bool(mk) and mk.get("run") == e.id
        days = dict(MARKET_SPANS).get(span, 7)
        if trig == "mk-graph":
            rng = _relayout_range(relayout)
            if rng is None:
                raise PreventUpdate
            x0, x1 = studio.market_range(e, days) if rng == "auto" else rng
            if same and abs(x0 - mk["x0"]) < 1000 and abs(x1 - mk["x1"]) < 1000:
                raise PreventUpdate
        elif trig == "mk-tf" and same:
            x0, x1 = mk["x0"], mk["x1"]
        else:
            x0, x1 = studio.market_range(e, days)
        fig, note, (x0, x1) = studio.market(e, tf, int(x0), int(x1))
        return fig, note, {"run": e.id, "x0": x0, "x1": x1}

    # ── results: baskets table ──
    @app.callback(Output("tbl", "data"), Output("tbl", "page_count"), Output("tbl", "page_current"),
                  Output("tbl-note", "children"), Output("tbl", "active_cell"), Output("tbl", "selected_cells"),
                  Input("st-run", "data"), Input("tbl", "page_current"), Input("tbl", "sort_by"),
                  Input("tbl", "filter_query"), prevent_initial_call=True)
    def table(run_, page, sort_by, query):
        if ctx.triggered_id != "tbl" or any(p["prop_id"] != "tbl.page_current" for p in ctx.triggered):
            page = 0                                      # a new run, sort or filter starts at the first page
        rows, pages, note = studio.table_page((run_ or {}).get("id"), page or 0, PAGE_SIZE, sort_by, query or "")
        return rows, pages, min(page or 0, pages - 1), note, None, []

    @app.callback(Output("st-rq", "data", allow_duplicate=True), Output("tabs", "value", allow_duplicate=True),
                  Input("tbl", "active_cell"), State("st-run", "data"), prevent_initial_call=True)
    def pick_basket(cell, run_):
        if not cell or cell.get("row_id") is None or not run_:
            raise PreventUpdate
        return {"run": run_["id"], "basket": int(cell["row_id"]), "n": time.time()}, "replay"

    @app.callback(Output("tbl", "style_data_conditional"), Input("st-rq", "data"), prevent_initial_call=True)
    def mark_row(rq):
        return _table_rules((rq or {}).get("basket"))

    # ── replay: everything that moves the playhead ──
    @app.callback(Output("st-pb", "data"), Output("rp-graph", "figure"), Output("rp-panel", "children"),
                  Output("rp-clock", "children"), Output("rp-slider", "value"), Output("rp-slider", "max"),
                  Output("rp-slider", "marks"), Output("rp-tick", "disabled"), Output("rp-play", "children"),
                  Output("rp-head", "children"), Output("rp-msg", "children"),
                  Input("st-pulse", "data"), Input("rp-play", "n_clicks"), Input("rp-back", "n_clicks"),
                  Input("rp-fwd", "n_clicks"), Input("rp-prev", "n_clicks"), Input("rp-next", "n_clicks"),
                  Input("rp-slider", "value"), Input("rp-tf", "value"), Input("rp-go", "n_clicks"),
                  Input("st-rq", "data"),
                  State("st-pb", "data"), State("rp-speed", "value"), State("rp-slider", "drag_value"),
                  State("rp-goto", "value"), State("st-run", "data"), prevent_initial_call=True)
    def replay(pulse, _p, _b, _f, _pv, _nx, slider, tf, _go, rq, pb, speed, drag, goto, run_):
        trig = ctx.triggered_id
        try:
            fr = studio.transport(trig, pb, run_id=(run_ or {}).get("id"), rq=rq, speed=speed or 1, tf=tf or "M1",
                                  slider=slider, drag=drag, goto=goto, pulse_n=(pulse or {}).get("n"))
        except PreventUpdate:
            # still acknowledge the tick, or the gate would hold the next ones back
            if trig == "st-pulse" and pb is not None:
                return (dict(pb, ack=(pulse or {}).get("n")),) + (no_update,) * 10
            raise
        except Exception as err:
            traceback.print_exc(file=sys.stderr)
            keep = dict(pb or {}, ack=(pulse or {}).get("n"), playing=False)
            return (keep, no_update, no_update, no_update, no_update, no_update, no_update, True, "▶︎ Play",
                    no_update, html.Span(f"Replay failed: {type(err).__name__}: {err}", className="msg"))
        play_label = "❙❙ Pause" if fr.playing else "▶︎ Play"
        msg = html.Span(fr.message, className="msg") if fr.message else ""
        s = fr.session
        if s is None:
            return (fr.pb, _blank_fig(fr.message), _panel_empty(fr.message), replay_clock(None), 0, no_update,
                    no_update, True, play_label, "", "")
        if fr.render:
            fig = s.figure(fr.t_ms, fr.tf)
            panel = replay_panel(s.state(fr.t_ms), s.recent_events(fr.t_ms), s.cfg)
        else:
            fig = panel = no_update
        return (fr.pb, fig, panel, replay_clock(fr.t_ms), no_update if fr.slider is None else fr.slider,
                max(1, int(math.ceil((s.end_ms - s.vis_ms) / 1000))) if fr.window_changed else no_update,
                slider_marks(s.vis_ms, s.end_ms) if fr.window_changed else no_update,
                not fr.playing, play_label, replay_head(s) if fr.window_changed else no_update, msg)

    return app


def serve(host: str = "127.0.0.1", port: int = 8060, debug: bool = False, store_dir: Optional[Path] = None) -> None:
    """Start the Studio (blocking)."""
    app = create_app(store_dir)
    print(f"Backtest Studio: http://{host}:{port}/   (Ctrl+C to stop)", flush=True)
    app.run(host=host, port=port, debug=debug)
