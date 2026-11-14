"""
Backtest configuration.

Every number the live bot hard-codes in ``constants.py`` / ``symbols.json`` is a field
here, so the strategy can be re-run with different timeframes, thresholds, ladder
shapes and costs without touching the live files.

``BacktestConfig.live(symbol)`` returns the configuration the live branch you are
standing on actually runs: it *reads* this branch's ``constants.py`` and
``symbols.json``, so a hedging branch yields the ``+$unit`` target variant and a
netting branch yields the slope profit-book variant automatically.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parents[1]

# Timeframe code -> seconds. Buckets are plain UTC epochs (Exness MT5 server time = UTC+0),
# which reproduces MT5's bar boundaries for every timeframe up to D1.
TF_SECONDS: Dict[str, int] = {
    "M1": 60, "M2": 120, "M3": 180, "M5": 300, "M10": 600, "M15": 900, "M30": 1800,
    "H1": 3600, "H2": 7200, "H4": 14400, "H6": 21600, "H8": 28800, "H12": 43200,
    "D1": 86400,
}
TF_ORDER: List[str] = sorted(TF_SECONDS, key=TF_SECONDS.get)

# Fibonacci lot ladder exactly as Strategy._get_next_fibo_volume produces it:
# position 1 = 1 unit, then 2, 3, 5, 8, 13, ... (the first two Fibonacci numbers dropped).
FIBO: List[float] = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]

Weight = Union[float, Tuple[float, float]]  # scalar = same weight on RSI and MACD; tuple = (rsi, macd)


@dataclass(frozen=True)
class SymbolSpec:
    """Contract facts for one instrument on an Exness Standard MT5 account."""
    name: str
    contract_size: float            # units of the asset per 1.00 lot
    digits: int                     # price decimals
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_leverage: Optional[float] = None   # broker cap for the instrument (None = account leverage)
    swap_long: float = 0.0          # USD per 1.00 lot per night (Standard accounts are swap-free here)
    swap_short: float = 0.0
    quote: str = "USD"
    # A market that trades around the clock has no session breaks, so a silence of hours in its tick
    # history is a hole in the archive, not a closed market (see BacktestConfig.data_hole_s). 0 = the
    # instrument has real closures (gold: daily break, weekend, holidays) and silences are left alone.
    data_hole_s: float = 0.0


SYMBOLS: Dict[str, SymbolSpec] = {
    # 1 lot = 100 troy oz. 0.01 lot = 1 oz, so $1.00 of basket P/L = a $1.00 move in gold.
    "XAUUSDm": SymbolSpec("XAUUSDm", contract_size=100.0, digits=3),
    # 1 lot = 1 BTC. 0.01 lot = 0.01 BTC, so $1.00 of basket P/L = a $100 move in BTC.
    # Exness fixes crypto leverage at 1:400 regardless of the account setting.
    # It trades 24/7; the longest real silences in the archive are weekend maintenance windows of
    # up to ~45 minutes, so three hours without a tick means missing history.
    "BTCUSDm": SymbolSpec("BTCUSDm", contract_size=1.0, digits=2, max_leverage=400.0, data_hole_s=3 * 3600.0),
}


def _norm_weights(w: Optional[Dict[str, Weight]]) -> Dict[str, Tuple[float, float]]:
    out: Dict[str, Tuple[float, float]] = {}
    for tf, v in (w or {}).items():
        if tf not in TF_SECONDS:
            raise ValueError(f"unknown timeframe {tf!r}; known: {', '.join(TF_ORDER)}")
        if isinstance(v, (tuple, list)):
            r, m = float(v[0]), float(v[1])
        else:
            r = m = float(v)
        if r != 0.0 or m != 0.0:
            out[tf] = (r, m)
    return out


# How long fresh entries stay out after a hole in the tick history: 38 H4 bars (see BacktestConfig.data_hole_quarantine_s).
DATA_HOLE_QUARANTINE_S = 38 * 4 * 3600.0


@dataclass
class BacktestConfig:
    # ── what / when ──────────────────────────────────────────────────────────
    symbol: str = "XAUUSDm"
    variant: str = "hedging"            # label only; behaviour is set by the exit fields below
    start: str = "2026-08-13"           # inclusive, 00:00 UTC
    end: str = "2026-11-13"             # exclusive, 00:00 UTC

    # ── account ──────────────────────────────────────────────────────────────
    initial_balance: float = 2000.0
    leverage: float = 2000.0            # account leverage; the instrument cap (SymbolSpec) still applies
    stop_out_level: float = 0.0         # margin level % at which the broker liquidates (Exness Standard: 0)

    # ── sizing (symbols.json) ────────────────────────────────────────────────
    mtqty: float = 0.01                 # lots per unit
    step_up_balance: float = 2500.0     # unit = floor(balance / step) + 1, re-derived only while flat
    unit_max_limit: int = 10
    fixed_units: int = 0                # >0 pins the unit (disables the balance auto-step)

    # ── indicators (constants.py) ────────────────────────────────────────────
    rsi_length: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    peak_lookback: int = 20             # bars scanned for the latest pivot
    pivot_width: int = 2                # bars needed each side to confirm a pivot
    rsi_peak_ob: float = 60.0           # an RSI pivot HIGH counts only at/above this
    rsi_peak_os: float = 40.0           # an RSI pivot LOW  counts only at/below this

    # ── per-section slope scores ─────────────────────────────────────────────
    # {TF: weight} or {TF: (rsi_weight, macd_weight)}. score = sum(w_rsi*rsi_sign + w_macd*macd_sign).
    open_weights: Dict[str, Weight] = field(default_factory=lambda: {"H1": 1, "M15": 1})
    fc_weights: Dict[str, Weight] = field(default_factory=lambda: {"M15": 1})
    book_weights: Dict[str, Weight] = field(default_factory=lambda: {"M15": 1})
    open_grey_fill: bool = True         # a grey (0) sign borrows the other indicator's sign on that TF
    book_grey_fill: bool = True
    fc_grey_fill: bool = False
    entry_s: float = 2.0                # |open_score| needed to open
    entry_agree_s: float = 2.0          # force-close score must agree by at least this to open
    ladder_s: float = 2.0               # ladder add blocked once open_score is this far adverse
    force_close_s: float = 1.0          # close when fc_score is this far against the basket
    book_s: float = 1.0                 # netting: book when book_score is this far against (and in profit)

    # ── exits ────────────────────────────────────────────────────────────────
    target_usd_per_unit: Optional[float] = 1.0      # hedging: close when basket profit > unit * this. None = off
    book_enabled: bool = False                      # netting: slope profit-book
    profit_protect_usd_per_unit: float = 1.0        # netting: profit needed before a book can fire
    force_close_enabled: bool = True

    # ── RSI DCA ladder ───────────────────────────────────────────────────────
    ladder_enabled: bool = True
    ladder_tfs: List[str] = field(default_factory=lambda: ["M1", "M5", "M15", "H1", "H4"])
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    ladder_multipliers: List[float] = field(default_factory=lambda: list(FIBO))

    # ── timing (app.py loop) ─────────────────────────────────────────────────
    reentry_cooldown_s: float = 300.0   # no fresh entry for this long after any close
    poll_interval_ms: int = 1000        # the live loop sleeps 1 s between iterations
    open_order_delay_ms: int = 0        # extra wait after an open (live: 0.1 s inside buy()/sell())
    add_order_delay_ms: int = 1000      # extra wait after a ladder add (live: ORDER_COOLDOWN_SECONDS)
    latency_ms: int = 0                 # decision -> fill delay; the fill uses the quote at that later time
    # The live loop sleeps for the period and then spends a varying time on its MT5 calls, so its
    # polls do not sit on a fixed grid. With a jitter every pass takes 0..poll_jitter_ms longer,
    # drawn from a reproducible sequence (poll_jitter_seed). 0 = the fixed grid of the parity runs.
    poll_jitter_ms: int = 0
    poll_jitter_seed: int = 0
    market_lookback_s: float = 180.0    # market "live" only if a tick arrived within this window
    # Broker "close-only" mode after a session break: quotes flow and closes are accepted, new
    # orders are refused. Exness gold: ~90 s after the daily break, ~3.5 min after the weekly
    # open. Breaks are read off the tick gaps (>= 30 min / >= 24 h); BTC has none.
    close_only_after_break_s: float = 90.0
    close_only_after_weekend_s: float = 210.0
    # Holes in the tick history (data hygiene, nothing the live bot ever meets). When a market that
    # never closes goes silent for this long the archive is missing those hours. Replaying across
    # such a hole would freeze the bot for the missing time and hand whatever it holds the whole
    # price change in one jump. Instead the open basket is closed at the last quote before the hole
    # (reason "data_hole": the P/L of the missing hours is unknown, none of it is booked) and no
    # fresh basket is opened for a quarantine after the history resumes. data_hole_s: None = the
    # symbol's own setting (SymbolSpec.data_hole_s: BTC three hours, gold off); 0 = off.
    #
    # The quarantine exists because the bars straddle the hole: the first bar after it carries the
    # whole price change, and every bar-count window (RSI smoothing, the pivot scan) still reaches
    # back across it. It is 38 H4 bars (6.3 days): peak_lookback + 2 x pivot_width + rsi_length bars
    # of the slowest timeframe the strategy family reads, with the live indicator settings. It is
    # one fixed length on purpose, the same for every configuration, so that the rows of a sweep or
    # a what-if table are all kept out of the market for the same days. It removes most, not all,
    # of the distortion.
    data_hole_s: Optional[float] = None
    data_hole_quarantine_s: float = DATA_HOLE_QUARANTINE_S

    # ── trading window (symbols.json; server time = UTC) ─────────────────────
    window_enabled: bool = True
    window_start_min: int = 60          # minutes since Monday 00:00 (XAU: Monday 01:00)
    window_end_min: int = 4 * 1440 + 22 * 60   # XAU: Friday 22:00
    brake: bool = False                 # manual brake: blocks fresh entries only

    # ── costs ────────────────────────────────────────────────────────────────
    spread_mult: float = 1.0            # scales the recorded bid/ask spread
    extra_spread: float = 0.0           # added to the spread, in price units
    slippage: float = 0.0               # adverse price units on every fill
    commission_per_lot: float = 0.0     # USD per 1.00 lot per side (Standard: 0)

    # ── experimental levers (all OFF by default = exact live behaviour) ──────
    slope_on_closed_bars: bool = False  # read slope signs from closed bars only (no intrabar repaint)
    ladder_on_closed_bars: bool = False # read ladder RSI from closed bars only
    min_hold_s: float = 0.0             # no force-close / book for this long after the basket opens
    fc_confirm_s: float = 0.0           # force-close must persist this long before it fires
    entry_confirm_s: float = 0.0        # entry direction must persist this long before it fires
    stop_loss_usd_per_unit: Optional[float] = None   # hard basket stop, USD per unit
    ladder_min_gap: float = 0.0         # min adverse price move since the last fill before the next add
    ladder_min_interval_s: float = 0.0  # min time since the basket's last fill before the next add
    max_hold_s: float = 0.0             # close the basket once it has been open this long (0 = off)
    target_per_lot: bool = False        # target = $ x (basket lots / mtqty) instead of $ x unit for the whole basket
    max_adds: int = 99                  # cap on ladder adds (live ladder = 5)
    allow_long: bool = True
    allow_short: bool = True
    entry_hours_utc: Optional[List[int]] = None      # restrict fresh entries to these UTC hours
    # Trend filter: fresh entries only in the direction (trend_mode +1) of this timeframe's trend, or only
    # against it (-1). The trend is the sign of the MACD signal line of that timeframe's last CLOSED bar,
    # the same line the live MACD vote uses to choose its pivot side. None = off.
    trend_tf: Optional[str] = None
    trend_mode: int = 1
    entry_max_spread: float = 0.0       # no fresh entry while the quoted spread is wider than this, in price units (0 = off)
    loss_cooldown_s: float = 0.0        # wait this long (instead of reentry_cooldown_s) after a basket that lost (0 = off)

    # ── output ───────────────────────────────────────────────────────────────
    record_interval_s: int = 60         # equity / score sampling for the charts

    # ───────────────────────────── helpers ─────────────────────────────
    def __post_init__(self):
        self.open_weights = _norm_weights(self.open_weights)
        self.fc_weights = _norm_weights(self.fc_weights)
        self.book_weights = _norm_weights(self.book_weights)
        for tf in self.ladder_tfs:
            if tf not in TF_SECONDS:
                raise ValueError(f"unknown ladder timeframe {tf!r}")
        if self.symbol not in SYMBOLS:
            raise ValueError(f"unknown symbol {self.symbol!r}; known: {', '.join(SYMBOLS)}")
        # the entry is always one unit: element 0 of the ladder is that entry, the adds start at element 1
        if len(self.ladder_multipliers) and float(self.ladder_multipliers[0]) != 1.0:
            raise ValueError("ladder_multipliers[0] is the entry and must be 1 (the adds are elements 1, 2, ...)")
        if self.fixed_units and self.fixed_units > self.unit_max_limit:
            raise ValueError(f"fixed_units={self.fixed_units} exceeds unit_max_limit={self.unit_max_limit}")

    @property
    def spec(self) -> SymbolSpec:
        return SYMBOLS[self.symbol]

    @property
    def effective_data_hole_s(self) -> float:
        """Silence (seconds) treated as a hole in the tick history; 0 = never."""
        return float(self.spec.data_hole_s if self.data_hole_s is None else self.data_hole_s)

    @property
    def effective_data_hole_quarantine_s(self) -> float:
        """How long fresh entries stay out after a hole in the tick history (see ``data_hole_quarantine_s``)."""
        return float(self.data_hole_quarantine_s)

    @property
    def effective_leverage(self) -> float:
        cap = self.spec.max_leverage
        return min(self.leverage, cap) if cap else self.leverage

    @property
    def n_ladder_adds(self) -> int:
        return min(len(self.ladder_tfs), self.max_adds) if self.ladder_enabled else 0

    def timeframes(self) -> List[str]:
        """Every timeframe this configuration reads, coarse-sorted."""
        used = set(self.open_weights) | set(self.fc_weights)
        if self.book_enabled:
            used |= set(self.book_weights)
        if self.ladder_enabled:
            used |= set(self.ladder_tfs[: self.n_ladder_adds])
        if self.trend_tf:
            used.add(self.trend_tf)
        return sorted(used, key=TF_SECONDS.get)

    def replace(self, **kw) -> "BacktestConfig":
        """A copy with the named fields changed. A misspelt field name is an error, never a silent no-op."""
        unknown = sorted(set(kw) - {f.name for f in fields(self)})
        if unknown:
            raise TypeError(f"unknown BacktestConfig field(s): {', '.join(unknown)}")
        d = self.to_dict()
        d.update(kw)
        return BacktestConfig.from_dict(d)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("open_weights", "fc_weights", "book_weights"):
            d[k] = {tf: list(v) for tf, v in getattr(self, k).items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BacktestConfig":
        known = {f.name for f in fields(cls)}
        return cls(**{k: copy.deepcopy(v) for k, v in d.items() if k in known})

    def key(self) -> str:
        """Stable short hash of the full configuration (cache / result naming)."""
        blob = json.dumps(self.to_dict(), sort_keys=True, default=str).encode()
        return hashlib.sha1(blob).hexdigest()[:12]

    def describe_scores(self) -> str:
        def fmt(w):
            parts = []
            for tf in sorted(w, key=TF_SECONDS.get, reverse=True):
                r, m = w[tf]
                parts.append(f"{tf}x{r:g}" if r == m else f"{tf}(rsi {r:g}, macd {m:g})")
            return " + ".join(parts) or "-"
        s = f"open[{fmt(self.open_weights)}] fc[{fmt(self.fc_weights)}]"
        if self.book_enabled:
            s += f" book[{fmt(self.book_weights)}]"
        return s

    # ───────────────────────────── live defaults ─────────────────────────────
    @classmethod
    def live(cls, symbol: str = "XAUUSDm", repo_root: Path = REPO_ROOT, **overrides) -> "BacktestConfig":
        """The configuration this branch's live bot runs, read from constants.py + symbols.json."""
        c = load_live_constants(repo_root)
        is_netting = hasattr(c, "BOOK_SCORE_WEIGHTS")
        kw = dict(
            symbol=symbol,
            variant="netting" if is_netting else "hedging",
            rsi_length=c.RSI_LENGTH,
            macd_fast=c.MACD_FAST, macd_slow=c.MACD_SLOW, macd_signal=c.MACD_SIGNAL,
            peak_lookback=c.PEAK_LOOKBACK, pivot_width=c.PIVOT_WIDTH,
            rsi_peak_ob=float(c.RSI_PEAK_OB), rsi_peak_os=float(c.RSI_PEAK_OS),
            open_weights=dict(c.OPEN_SCORE_WEIGHTS),
            fc_weights=dict(c.FORCE_CLOSE_SCORE_WEIGHTS),
            entry_s=float(c.ENTRY_S), entry_agree_s=float(c.ENTRY_AGREE_S),
            ladder_s=float(c.LADDER_S), force_close_s=float(c.FORCE_CLOSE_S),
            rsi_oversold=float(c.RSI_OVERSOLD), rsi_overbought=float(c.RSI_OVERBOUGHT),
            ladder_tfs=[t.replace("TIMEFRAME_", "") for t in c.RSI_DCA_LADDER_TIMEFRAMES],
            reentry_cooldown_s=float(c.REENTRY_COOLDOWN_SECONDS),
            add_order_delay_ms=int(c.ORDER_COOLDOWN_SECONDS * 1000),
            market_lookback_s=float(c.MARKET_LOOKBACK_MINUTES * 60),
        )
        if is_netting:
            kw.update(
                book_enabled=True,
                book_weights=dict(c.BOOK_SCORE_WEIGHTS),
                book_s=float(c.BOOK_S),
                profit_protect_usd_per_unit=float(c.PROFIT_PROTECT_USD_PER_UNIT),
                target_usd_per_unit=None,
            )
        else:
            # app.py passes close_threshold=units -> the target is $1 of basket profit per unit.
            kw.update(book_enabled=False, target_usd_per_unit=1.0)
        kw.update(_symbols_json(symbol, repo_root))
        kw.update(overrides)
        return cls(**kw)


_DAY = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6}


def _week_minutes(day: str, hhmm: str) -> int:
    """Same arithmetic as MT5TradingBot._day_time_to_week_minutes."""
    d = _DAY.get(str(day).strip().lower(), 0)
    try:
        hh, mm = str(hhmm).strip().split(":")
        return d * 1440 + int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return d * 1440


# symbols.json differs between the XAU and BTC deployment branches only in the symbol
# name and the trading window. These are the two windows the fleet runs; whichever
# symbol this branch's symbols.json holds is read from the file, the other from here.
_FLEET_WINDOWS = {
    "XAUUSDm": dict(enabled=True, start_day="Monday", start_time="01:00", end_day="Friday", end_time="22:00"),
    "BTCUSDm": dict(enabled=True, start_day="Monday", start_time="00:00", end_day="Sunday", end_time="23:59"),
}


def _symbols_json(symbol: str, repo_root: Path) -> dict:
    out = {}
    cfg, entry = {}, {}
    p = Path(repo_root) / "symbols.json"
    if p.exists():
        cfg = json.loads(p.read_text(encoding="utf-8"))
        for e in cfg.get("symbols", []):
            if e.get("symbol") == symbol:
                entry = e
    # Sizing fields are identical across the fleet, so the first entry is a safe fallback.
    if not entry and cfg.get("symbols"):
        entry = {k: v for k, v in cfg["symbols"][0].items() if k != "symbol"}
        win = _FLEET_WINDOWS.get(symbol, cfg.get("trading_window", {}))
    else:
        win = cfg.get("trading_window", _FLEET_WINDOWS.get(symbol, {}))
    out["mtqty"] = float(cfg.get("mtqty", 0.01))
    out["brake"] = bool(cfg.get("brake", 0))
    out["step_up_balance"] = float(entry.get("step_up_balance", 0) or 0)
    out["unit_max_limit"] = int(entry.get("unit_max_limit", 1))
    out["window_enabled"] = bool(win.get("enabled", False))
    out["window_start_min"] = _week_minutes(win.get("start_day", "Monday"), win.get("start_time", "00:00"))
    out["window_end_min"] = _week_minutes(win.get("end_day", "Saturday"), win.get("end_time", "00:00"))
    return out


_CONSTANTS_CACHE: Dict[str, tuple] = {}


def load_live_constants(repo_root: Path = REPO_ROOT):
    """
    The live ``constants.py`` found in ``repo_root``, loaded from that exact file.

    It is executed under a private module name (``constants.py`` is plain assignments), so
    asking for several checkouts in one process -- this branch and a netting worktree, say --
    always returns each one's own values, whatever ``sys.path`` / ``sys.modules`` hold.
    """
    import importlib.util

    path = (Path(repo_root) / "constants.py").resolve()
    stamp = path.stat().st_mtime_ns
    hit = _CONSTANTS_CACHE.get(str(path))
    if hit is not None and hit[0] == stamp:
        return hit[1]
    name = "_alcadeias_live_constants_" + hashlib.sha1(str(path).encode()).hexdigest()[:10]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _CONSTANTS_CACHE[str(path)] = (stamp, mod)
    return mod
