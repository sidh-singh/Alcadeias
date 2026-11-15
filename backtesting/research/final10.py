"""
The final ten: every design and published strategy tested so far, narrowed to ten per symbol by one fixed rule, then
run for eight years (Nov 2018 - Nov 2026), five years and the last year on fresh $2,000 accounts.

    python -m backtesting.research.final10 select            the pre-registered lists (backtest_results/final10/selection.json)
    python -m backtesting.research.final10 run [--symbols ..] the runs (CSV files in backtest_results/final10/)
    python -m backtesting.research.final10 supplement        not pre-registered: the V3-lite hybrids on the tick engine
    python -m backtesting.research.final10 report            FINAL10.md (from FINAL10.template.md) and the charts

The selection (frozen before any 2018-2020 data was read)
---------------------------------------------------------
* Pool: every row with results in all five periods 2021, 2022, 2023, 2024-25 and 2025-26. That is the bot's own designs from
  round 4 (raw ticks, eight loop timings) and the ten published strategies with every parameter set, variant and sizing
  (M1 bars, ``external.py``). The live logic and the owner's rules design are not candidates. They run alongside as
  references, as do our own designs that miss the cut. The bar-level copy of V3-lite is a calibration row, not a
  candidate.
* One yardstick for all: fresh $2,000 accounts per quarter, the bot's own test format (for our designs the median of the
  eight loop timings in each quarter). For each period, the average profit per quarter.
* Eligible: profit in at least 4 of the 5 periods, never wiped, worst fresh-quarter drawdown at most 50%.
* Ranked by profit per unit of drawdown: the average profit per quarter over the five periods divided by the worst
  fresh-quarter drawdown in per cent.
* At most two rows of any one published strategy (variants and parameter sets of one strategy are near-copies). Each of
  our own designs counts on its own: they are different parameter sets chosen by the optimiser. Rows with identical
  results in all five periods count once.
* The ten best per symbol are the finalists.

What is new data: 13 Nov 2018 - 31 Dec 2020 had never been read by any study. Everything from 2021 on helped choose these
rows, so the five-year and one-year windows are in-sample; the 2018-2020 window is the honest test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from ..config import REPO_ROOT

RESULTS = REPO_ROOT / "backtest_results"
IMPROVE = RESULTS / "improve"
OUT = RESULTS / "final10"
SYMBOLS = ("XAUUSDm", "BTCUSDm")
P5 = ("2021", "2022", "2023", "2024-25", "2025-26")

MIN_PERIODS_UP = 4
MAX_DD_PCT = 50.0
FAMILY_CAP = 2
N_FINAL = 10

# the test windows, [start, end) UTC; each is one fresh $2,000 account
DATA_END = "2026-11-13"
WINDOWS: Dict[str, tuple] = {
    "8y": ("2018-11-13", DATA_END),          # eight years
    "5y": ("2021-11-13", DATA_END),          # five years
    "new": ("2018-11-13", "2021-01-01"),     # the part of the eight years no study had read
    "1y": ("2025-11-13", DATA_END),          # the last year
}
WINDOW_NAMES = {"8y": "8 years, Nov 2018 - Nov 2026", "5y": "5 years, Nov 2021 - Nov 2026",
                "new": "new data, Nov 2018 - Dec 2020", "1y": "last year, Nov 2025 - Nov 2026"}
# history read before a window for the indicators of the bar-level rows (12-month momentum needs a year)
HISTORY_FROM = {"XAUUSDm": "2017-01-01", "BTCUSDm": "2018-01-01"}
PROTOCOL = {
    "windows": {k: {"start": a, "end": z, "what": WINDOW_NAMES[k]} for k, (a, z) in WINDOWS.items()},
    "account": "one fresh $2,000 account per window, nothing withdrawn, leverage 1:2000, swap-free; sizing as the row "
               "says (the bot's unit rule: unit = floor(balance / 2,500) + 1 lots of 0.01, at most 10, unless risk-sized)",
    "engines": {"own designs": "the tick engine: per-second replay (one loop timing) for 8y / 5y / new, raw ticks under "
                               "eight loop timings for 1y (median, with the range)",
                "published strategies and V3-lite hybrids": "external.py's M1-bar simulator, unchanged, with history from "
                                                            "2017-01 (gold) / 2018-01 (BTC) for the indicators"},
    "rankings": {"highest equity": "final equity of the window's account",
                 "lowest drawdown": "maximum drawdown, % of the running equity peak",
                 "combined": "annual return (CAGR, %) / maximum drawdown (%); for 1y the return over the year"},
    "honest test": "the 'new' window: 13 Nov 2018 - 31 Dec 2020 had not been read by any earlier study",
}

# the bot's designs: their names in the round-4 files
OWN = ("V3-lite", "Top 1", "Top 2", "Top 3")
REFERENCES = ("Live", "Owner's rules + H1 trend + 4 h pause")
SHORT_FAMILY = {"london": "Session breakout", "rsi2": "Connors RSI(2)", "tsmom": "TSMOM", "ma": "Long moving average",
                "noise": "Noise-area momentum", "supertrend": "Supertrend", "turtle": "Turtle", "donchian": "Donchian ensemble",
                "lasthalf": "Last half-hour", "maxmin": "MAX / MIN", "v3lite": "V3-lite (bar level)"}


# ───────────────────────────── the evidence ─────────────────────────────

def _design_name(label: str) -> str:
    return label.split(":")[0].strip()


def own_designs(symbol: str) -> Dict[str, dict]:
    """The bot's designs of round 4 with their exact settings (overrides of the live configuration)."""
    raw = json.loads((IMPROVE / "round4" / f"top3_v4_{symbol}_designs.json").read_text())
    return {_design_name(k): v for k, v in raw.items()}


def own_design_labels(symbol: str) -> Dict[str, str]:
    raw = json.loads((IMPROVE / "round4" / f"top3_v4_{symbol}_designs.json").read_text())
    return {_design_name(k): k for k in raw}


def evidence() -> pd.DataFrame:
    """One row per candidate and symbol: average profit per quarter on fresh $2,000 accounts in each of the five periods,
    the worst fresh-quarter drawdown, losing quarters and whether any account was wiped."""
    rows: List[dict] = []
    ext = pd.concat([pd.read_csv(IMPROVE / "external_strategies.csv", dtype={"period": str}),
                     pd.read_csv(IMPROVE / "external_strategies_holdout_2021_22.csv", dtype={"period": str})],
                    ignore_index=True)
    for (sym, strat, name, params, variant, sizing), g in ext.groupby(
            ["symbol", "strategy", "name", "params", "variant", "sizing"], sort=False):
        g = g.set_index("period")
        if not set(P5) <= set(g.index):
            continue
        rows.append(dict(symbol=sym, kind="published", engine="bars", family=strat, name=name, params=params,
                         variant=variant, sizing=sizing, rule=str(g.loc["2023", "rule"]),
                         **{p: float(g.loc[p, "fresh_avg_q"]) for p in P5},
                         dd_fresh=float(g.loc[list(P5), "fresh_dd_worst"].max()),
                         lost_q=int(g.loc[list(P5), "fresh_lost"].sum()), n_q=int(g.loc[list(P5), "fresh_n"].sum()),
                         wiped=bool(g.loc[list(P5), "fresh_wiped"].astype(str).eq("True").any()
                                    or g.loc[list(P5), "wiped"].astype(str).eq("True").any())))
    period_of = {"FINAL": "2023", "CONFIRM": "2024-25", "DEV": "2025-26"}
    for sym in SYMBOLS:
        dev = pd.read_csv(IMPROVE / "round4" / f"top3_v4_dev_{sym}.csv")
        ho = pd.read_csv(IMPROVE / "round4" / f"top3_v4_holdout_{sym}.csv")
        dev["P"] = dev["period"].map(period_of)
        ho["P"] = np.where(ho["segment"].str.startswith("2021"), "2021", "2022")
        d = pd.concat([dev, ho], ignore_index=True)
        for label, g in d.groupby("design", sort=False):
            q = g.groupby(["P", "window", "segment"]).agg(
                net=("net_profit", "median"), dd=("max_dd_pct", "median"),
                wiped=("stopped_out", lambda s: s.astype(str).eq("True").any())).reset_index()
            per = q.groupby("P")["net"].mean()
            nm = _design_name(label)
            rows.append(dict(symbol=sym, kind="own" if nm in OWN else "reference", engine="ticks", family=nm, name=nm,
                             params=label, variant="-", sizing="bot unit rule", rule=label,
                             **{p: float(per.get(p, np.nan)) for p in P5},
                             dd_fresh=float(q["dd"].max()), lost_q=int((q["net"] < 0).sum()), n_q=int(len(q)),
                             wiped=bool(q["wiped"].any())))
    E = pd.DataFrame(rows)
    E["periods_up"] = (E[list(P5)] > 0).sum(axis=1)
    E["mean_q"] = E[list(P5)].mean(axis=1)
    E["worst_period"] = E[list(P5)].min(axis=1)
    E["profit_per_dd"] = E["mean_q"] / E["dd_fresh"].clip(lower=1.0)
    E["eligible"] = ((E["periods_up"] >= MIN_PERIODS_UP) & (~E["wiped"]) & (E["dd_fresh"] <= MAX_DD_PCT)
                     & (E["mean_q"] > 0) & E["kind"].isin(["own", "published"]) & (E["family"] != "v3lite"))
    return E


def label_of(r) -> str:
    """A short, unique display name."""
    if r["kind"] != "published":
        return r["name"]
    fam = SHORT_FAMILY.get(r["family"], r["family"])
    if r["family"] == "london":
        fam = "London breakout" if str(r["symbol"]).startswith("XAU") else "Daily volatility breakout"
    var = {"standalone": "", "+ bot votes": " + bot votes", "+ H1 trend": " + H1 trend",
           "V3-lite + regime": "", "risk-sized": " (risk-sized)"}[r["variant"]]
    alt = " [alt]" if r["params"] == "alt" else ""
    if r["variant"] == "V3-lite + regime":
        return "V3-lite + " + REGIME_NAMES.get((r["family"], r["params"]), f"{fam}{alt} regime")
    return f"{fam}{alt}{var}"


# what each published strategy's regime is, when it filters V3-lite's entries (external.py, Built.regime)
REGIME_NAMES = {("rsi2", "default"): "200-day trend filter", ("rsi2", "alt"): "200-day trend filter",
                ("tsmom", "default"): "1/3/12-month momentum filter", ("tsmom", "alt"): "12-month momentum filter",
                ("supertrend", "default"): "H4 Supertrend filter", ("supertrend", "alt"): "H4 Supertrend long-only filter",
                ("donchian", "default"): "Donchian-ensemble filter", ("donchian", "alt"): "Donchian-ensemble long/short filter",
                ("ma", "default"): "moving-average filter", ("ma", "alt"): "moving-average [alt] filter"}


def select(E: pd.DataFrame) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for sym in SYMBOLS:
        t = E[(E["symbol"] == sym) & E["eligible"]].copy()
        t["_key"] = t["family"] + "|" + t[list(P5)].round(2).astype(str).agg("|".join, axis=1)
        t = t.drop_duplicates("_key", keep="first")
        t = t.sort_values(["profit_per_dd", "mean_q"], ascending=False, kind="stable")
        chosen, per_family = [], {}
        for _, r in t.iterrows():
            fam = r["family"]
            if r["kind"] == "published":
                if per_family.get(fam, 0) >= FAMILY_CAP:
                    continue
                per_family[fam] = per_family.get(fam, 0) + 1
            chosen.append(r)
            if len(chosen) == N_FINAL:
                break
        out[sym] = [_spec(r, rank) for rank, r in enumerate(chosen, 1)]
    return out


def _spec(r, rank: Optional[int]) -> dict:
    s = dict(rank=rank, label=label_of(r), kind=r["kind"], engine=r["engine"], family=r["family"], name=r["name"],
             params=r["params"], variant=r["variant"], sizing=r["sizing"], rule=r["rule"],
             evidence={p: round(float(r[p]), 1) for p in P5},
             periods_up=int(r["periods_up"]), mean_q=round(float(r["mean_q"]), 1), dd_fresh=round(float(r["dd_fresh"]), 1),
             profit_per_dd=round(float(r["profit_per_dd"]), 2), lost_q=int(r["lost_q"]), n_q=int(r["n_q"]))
    if r["engine"] == "ticks":
        s["overrides"] = own_designs(r["symbol"])[r["name"]]
    return s


def references(E: pd.DataFrame, chosen: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """Run alongside, not ranked: the live logic, the owner's rules design, our designs that missed the cut, and the
    bar-level V3-lite (how the two engines compare)."""
    out = {}
    for sym in SYMBOLS:
        names = {c["name"] for c in chosen[sym] if c["kind"] == "own"}
        t = E[E["symbol"] == sym]
        refs = [_spec(r, None) for _, r in t[t["name"].isin(REFERENCES)].iterrows()]
        refs += [_spec(r, None) for _, r in t[(t["kind"] == "own") & ~t["name"].isin(names)].iterrows()]
        refs += [_spec(r, None) for _, r in t[t["family"] == "v3lite"].iterrows()]
        out[sym] = refs
    return out


def write_selection(path: Path = OUT / "selection.json") -> dict:
    E = evidence()
    chosen = select(E)
    doc = {"rule": {"pool": "every row with results in 2021, 2022, 2023, 2024-25 and 2025-26",
                    "yardstick": "fresh $2,000 account per quarter; average profit per quarter in each period",
                    "eligible": f"profit in at least {MIN_PERIODS_UP} of 5 periods, never wiped, worst fresh-quarter "
                                f"drawdown at most {MAX_DD_PCT:.0f}%",
                    "rank": "average profit per quarter over the five periods / worst fresh-quarter drawdown (%)",
                    "diversity": f"at most {FAMILY_CAP} rows per published strategy; each own design counts on its own",
                    "n": N_FINAL},
           "protocol": PROTOCOL,
           "pool_size": {s: int((E["symbol"] == s).sum()) for s in SYMBOLS},
           "eligible": {s: int(((E["symbol"] == s) & E["eligible"]).sum()) for s in SYMBOLS},
           "final": chosen, "references": references(E, chosen)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, default=str))
    E.drop(columns=[c for c in E.columns if c.startswith("_")]).to_csv(path.parent / "evidence.csv", index=False)
    return doc


# ───────────────────────────── the warm re-check (after the results) ─────────────────────────────
# The study the selection read gave its slow indicators little history: its 2021-22 run read nothing before Jan 2021
# and its 2023-26 run nothing before Dec 2022. A filter that needs a year of history (12-month momentum) was then
# undefined for months and its rows simply did not trade; that counted as a period "up" or as the one allowed miss.
# Here every published row is re-run on the same five periods and quarter edges, with history from 2017 (gold) /
# 2018 (BTC), and the same rule is applied. Nothing in it reads 2018-2020 results; the older bars only warm the
# indicators up. Our own designs' evidence is unchanged (tick engine, round 4).

WARM_PERIODS = {"2021": ("2021-02-01", "2022-01-01"), "2022": ("2022-01-01", "2023-01-01"),
                "2023": ("2023-02-01", "2024-01-01"), "2024-25": ("2024-01-01", "2025-07-01"),
                "2025-26": ("2025-07-01", "2026-11-13")}
WARM_BLOCKS = {"2021": ["2021-02-01", "2021-04-01", "2021-07-01", "2021-10-01", "2022-01-01"],
               "2022": ["2022-01-01", "2022-04-01", "2022-07-01", "2022-10-01", "2023-01-01"],
               "2023": ["2023-02-01", "2023-05-01", "2023-08-01", "2023-11-01", "2024-01-01"],
               "2024-25": ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01", "2025-04-01", "2025-07-01"],
               "2025-26": ["2025-08-13", "2025-11-13", "2026-02-13", "2026-05-13", "2026-08-13", "2026-11-13"]}


def warm_external(symbols: Sequence[str] = SYMBOLS, log=print) -> pd.DataFrame:
    """external.evaluate() on the five selection periods with a warm history (same periods and quarter edges)."""
    from . import external as X
    rows = []
    for sym in symbols:
        m = X.load_market(sym, earliest=HISTORY_FROM[sym], end=DATA_END)
        sig = X.bot_signals(m)
        saved = X.PERIODS, X.ENGINE_BLOCKS
        X.PERIODS, X.ENGINE_BLOCKS = dict(WARM_PERIODS), dict(WARM_BLOCKS)
        try:
            r, _ = X.evaluate(m, sig, log=lambda *a, **k: None)
        finally:
            X.PERIODS, X.ENGINE_BLOCKS = saved
        rows += r
        log(f"{sym}: {len(r)} warm rows")
    return pd.DataFrame(rows)


def evidence_from(ext: pd.DataFrame) -> pd.DataFrame:
    """The evidence table with the published rows taken from ``ext`` (all five periods in one frame) and our designs'
    rows as in ``evidence()``."""
    base = evidence()
    own = base[base["kind"].isin(["own", "reference"])]
    rows = []
    for (sym, strat, name, params, variant, sizing), g in ext.groupby(
            ["symbol", "strategy", "name", "params", "variant", "sizing"], sort=False):
        g = g.set_index("period")
        rows.append(dict(symbol=sym, kind="published", engine="bars", family=strat, name=name, params=params,
                         variant=variant, sizing=sizing, rule=str(g.loc["2023", "rule"]),
                         **{p: float(g.loc[p, "fresh_avg_q"]) for p in P5},
                         **{f"trades_{p}": int(g.loc[p, "trades"]) for p in P5},
                         dd_fresh=float(g.loc[list(P5), "fresh_dd_worst"].max()),
                         lost_q=int(g.loc[list(P5), "fresh_lost"].sum()), n_q=int(g.loc[list(P5), "fresh_n"].sum()),
                         wiped=bool(g.loc[list(P5), "fresh_wiped"].astype(bool).any() or g.loc[list(P5), "wiped"].astype(bool).any())))
    E = pd.concat([pd.DataFrame(rows), own.drop(columns=[c for c in own.columns if c not in set(base.columns)])],
                  ignore_index=True)
    E["periods_up"] = (E[list(P5)] > 0).sum(axis=1)
    E["mean_q"] = E[list(P5)].mean(axis=1)
    E["worst_period"] = E[list(P5)].min(axis=1)
    E["profit_per_dd"] = E["mean_q"] / E["dd_fresh"].clip(lower=1.0)
    E["eligible"] = ((E["periods_up"] >= MIN_PERIODS_UP) & (~E["wiped"]) & (E["dd_fresh"] <= MAX_DD_PCT)
                     & (E["mean_q"] > 0) & E["kind"].isin(["own", "published"]) & (E["family"] != "v3lite"))
    return E


def warm_check(out: Path = OUT, log=print) -> dict:
    ext = warm_external(log=log)
    ext.to_csv(Path(out) / "warm_external.csv", index=False)
    E = evidence_from(ext)
    E.to_csv(Path(out) / "evidence_warm.csv", index=False)
    chosen = select(E)
    doc = {"note": "the same rule on warm evidence (published rows re-run with history from 2017 / 2018); "
                   "computed after the results; not a pre-registration",
           "eligible": {s: int(((E["symbol"] == s) & E["eligible"]).sum()) for s in SYMBOLS},
           "final": chosen}
    (Path(out) / "selection_warm.json").write_text(json.dumps(doc, indent=1, default=str))
    pre = load_selection(Path(out) / "selection.json")
    for sym in SYMBOLS:
        a = [r["label"] for r in pre["final"][sym]]
        b = [r["label"] for r in chosen[sym]]
        log(f"{sym}: out {[x for x in a if x not in b]}, in {[x for x in b if x not in a]}")
    return doc


def run_warm_additions(out: Path = OUT, windows: Sequence[str] = tuple(WINDOWS), log=print) -> None:
    """The rows the warm re-check selects that the pre-registered list does not hold, on every window."""
    out = Path(out)
    pre = load_selection(out / "selection.json")
    warm = json.loads((out / "selection_warm.json").read_text())
    for sym in SYMBOLS:
        have = {r["label"] for r in pre["final"][sym]}
        new = [dict(r, warm_rank=r["rank"], rank=None, kind="warm") for r in warm["final"][sym] if r["label"] not in have]
        if not new:
            continue
        res, yrs, curves, trades = run_bars(sym, new, windows, None, log)
        for row in res:
            row["warm_rank"] = next(r["warm_rank"] for r in new if r["label"] == row["label"])
        tag = f"{sym}_warm"
        pd.DataFrame(res).to_csv(out / f"runs_{tag}.csv", index=False)
        pd.DataFrame(yrs).to_csv(out / f"years_{tag}.csv", index=False)
        pd.concat(curves, ignore_index=True).to_csv(out / f"equity_{tag}.csv.gz", index=False)
        if trades:
            pd.concat(trades, ignore_index=True).to_csv(out / f"trades_{tag}.csv.gz", index=False)
        log(f"{sym}: {len(new)} warm additions done")


# ───────────────────────────── running ─────────────────────────────

ACCOUNT = 2000.0
DAY_S = 86400
YEAR_S = 365.25 * DAY_S


def load_selection(path: Path = OUT / "selection.json") -> dict:
    return json.loads(Path(path).read_text())


def _ts(sec) -> pd.Timestamp:
    return pd.Timestamp(int(sec), unit="s", tz="UTC")


def _window_s(w: str) -> tuple:
    from ..data import store
    a, z = WINDOWS[w]
    return store.to_ms(a) // 1000, store.to_ms(z) // 1000


def account_metrics(daily: pd.Series, final: float, max_dd_pct: float, a_s: int, z_s: int, pnl: np.ndarray,
                    wiped: bool, wiped_at: Optional[pd.Timestamp]) -> dict:
    """The figures reported for one account. ``daily``: equity at the start of each trading day (UTC timestamps),
    ``max_dd_pct`` the engine's own drawdown (every tick / second, or the worst price of every M1 bar)."""
    years = (z_s - a_s) / YEAR_S
    net = final - ACCOUNT
    ret = net / ACCOUNT * 100.0
    cagr = ((final / ACCOUNT) ** (1.0 / years) - 1.0) * 100.0 if final > 0 and years > 0 else -100.0
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    s = daily.sort_index()
    peak = s.cummax()
    under = s < peak - 1e-9
    longest, run_start = 0.0, None
    for t, u in under.items():
        if u and run_start is None:
            run_start = t
        elif not u and run_start is not None:
            longest = max(longest, (t - run_start).total_seconds() / DAY_S)
            run_start = None
    if run_start is not None:
        longest = max(longest, (_ts(z_s) - run_start).total_seconds() / DAY_S)
    month = s.groupby(s.index.strftime("%Y-%m")).first()
    m_pnl = np.diff(np.concatenate([month.to_numpy(), [final]]))
    # stored with more digits than shown, so a figure is rounded once, when it is displayed
    return {"final_equity": round(final, 2), "net": round(net, 2), "return_pct": round(ret, 4),
            "cagr_pct": round(cagr, 4), "max_dd_pct": round(max_dd_pct, 4),
            "return_per_dd": round((cagr if years >= 1.0 else ret) / max(max_dd_pct, 0.01), 3),
            "trades": int(len(pnl)), "trades_per_year": round(len(pnl) / years, 1),
            "win_rate_pct": round(len(wins) / len(pnl) * 100.0, 1) if len(pnl) else np.nan,
            "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if len(losses) and losses.sum() < 0 else np.nan,
            "avg_trade": round(float(pnl.mean()), 2) if len(pnl) else np.nan,
            "worst_trade": round(float(pnl.min()), 2) if len(pnl) else np.nan,
            "best_trade": round(float(pnl.max()), 2) if len(pnl) else np.nan,
            "losing_months": int((m_pnl < 0).sum()), "months": int(len(m_pnl)),
            "longest_underwater_days": round(longest, 0),
            "wiped": bool(wiped), "wiped_at": str(wiped_at.date()) if wiped and wiped_at is not None else ""}


def yearly(daily: pd.Series, final: float, a_s: int, z_s: int) -> List[dict]:
    """Profit of each calendar year of an account (the first and last years are partial)."""
    s = daily.sort_index()
    out = []
    years = sorted({t.year for t in s.index})
    for y in years:
        part = s[s.index.year == y]
        if part.empty:
            continue
        start_eq = part.iloc[0] if y != _ts(a_s).year else ACCOUNT
        nxt = s[s.index.year > y]
        end_eq = nxt.iloc[0] if len(nxt) else final
        out.append({"year": y, "start_equity": round(float(start_eq), 2), "end_equity": round(float(end_eq), 2),
                    "pnl": round(float(end_eq - start_eq), 2),
                    "return_pct": round(float((end_eq - start_eq) / start_eq * 100.0), 1) if start_eq > 0 else np.nan})
    return out


# the bar-level rows ------------------------------------------------------------------------------------------------

def _bar_plan(X, m, sig, v3, built: dict, row: dict):
    """The trade plan and sizing of one published / hybrid row, exactly as ``external.evaluate`` builds it."""
    if row["family"] == "v3lite":
        return v3, X.BOT
    key = (row["family"], row["params"])
    if key not in built:
        build = X.STRATEGY_BY_KEY[row["family"]].for_symbol(m.symbol)[row["params"]][1]
        built[key] = build(m)
    b = built[key]
    v = row["variant"]
    if v == "standalone":
        plan, sizing = b.plan, X.BOT
    elif v == "risk-sized":
        plan, sizing = b.risk, b.risk_sizing
    elif v == "+ bot votes":
        plan, sizing = X.filtered(b.plan, m, sig.votes_at), X.BOT
    elif v == "+ H1 trend":
        plan, sizing = X.filtered(b.plan, m, sig.trend_at), X.BOT
    elif v == "V3-lite + regime":
        rt, rv = b.regime
        plan, sizing = X.filtered(v3, m, lambda T, rt=rt, rv=rv: X.value_at(rt, rv, T, 0)), X.BOT
    else:
        raise ValueError(f"unknown variant {v!r}")
    if sizing.label != row["sizing"]:
        raise ValueError(f"{row['label']}: sizing {sizing.label!r} is not the selected {row['sizing']!r}")
    return plan, sizing


def _day_bounds(m, a_ix: int, z_ix: int) -> np.ndarray:
    """M1 indices: the window start, the first bar of every later UTC day, the window end."""
    day = m.t[a_ix:z_ix] // DAY_S
    starts = a_ix + np.flatnonzero(np.diff(day, prepend=day[0] - 1) != 0) if len(day) else np.zeros(0, np.int64)
    return np.unique(np.concatenate([[a_ix], starts, [z_ix]])).astype(np.int64)


def _bar_account(X, m, plan, sizing, a_ix: int, z_ix: int):
    """``external.account`` / ``run_target`` with daily equity marks and the trades' prices kept."""
    bnd = _day_bounds(m, a_ix, z_ix)
    trades = pd.DataFrame()
    if isinstance(plan, X.TargetPlan):
        res = X.run_target(m, plan, a_ix, z_ix, bnd)
        if len(res.trades_pnl):
            trades = pd.DataFrame({"open_time": [_ts(m.t[i]) for i in res.trades_eix],
                                   "close_time": [_ts(m.t[min(i, len(m) - 1)]) for i in res.trades_xix],
                                   "side": np.where(res.trades_dir > 0, "BUY", "SELL"), "pnl": res.trades_pnl})
    else:
        p = X.run_path(m, plan, a_ix, z_ix)
        steps, pnl, bal, dd, wiped, wix, n_done, eqb = X._account_kernel(
            m.t, m.o, m.h, m.l, m.c, m.sp, m.k, p.dir, p.eix, p.epx, p.xix, p.xpx, p.why, p.risk, p.expo, p.leg0, p.nleg,
            p.leix, p.lepx, X._MODE[sizing.mode], float(sizing.rf), float(sizing.cap_lev), bool(sizing.brake),
            np.asarray(bnd[1:-1], np.int64), X._YEARS, X.ACCOUNT, X.STEP_UP, float(X.UNIT_MAX))
        done = np.arange(len(steps)) < n_done
        sel = np.flatnonzero(done & (steps > 0))
        res = X.Result(pnl[sel], p.dir[sel], p.eix[sel], p.xix[sel], int((done & (steps == 0)).sum()), float(bal),
                       float(dd), bool(wiped), int(m.t[wix]) if wiped else None,
                       np.concatenate([[X.ACCOUNT], eqb, [bal]]), orders=int(len(sel) + p.nleg[sel].sum()))
        if len(sel):
            trades = pd.DataFrame({"open_time": [_ts(m.t[i]) for i in p.eix[sel]],
                                   "close_time": [_ts(m.t[min(i, len(m) - 1)]) for i in p.xix[sel]],
                                   "side": np.where(p.dir[sel] > 0, "BUY", "SELL"), "entry": p.epx[sel],
                                   "exit": p.xpx[sel], "lots": steps[sel] * 0.01, "legs": p.nleg[sel],
                                   "why": [X.WHY_NAMES.get(int(w), str(w)) for w in p.why[sel]], "pnl": pnl[sel]})
    daily = pd.Series(res.blocks[:-1], index=[_ts(m.t[i]) if i < len(m) else _ts(m.t[-1]) for i in bnd[:-1]])
    daily.iloc[0] = X.ACCOUNT
    return res, daily, trades


def run_bars(symbol: str, rows: List[dict], windows: Sequence[str], cache_dir: Optional[Path] = None, log=print):
    from . import external as X
    t0 = pd.Timestamp.now()
    m = X.load_market(symbol, earliest=HISTORY_FROM[symbol], end=DATA_END)
    sig = X.bot_signals(m, cache_dir)
    v3 = X.v3lite(m, sig)
    log(f"{symbol}: {len(m):,} M1 bars {_ts(m.t[0])} .. {_ts(m.t[-1])}, the bot's votes ready "
        f"({(pd.Timestamp.now() - t0).total_seconds():.0f}s)")
    built: dict = {}
    out, years, curves, trades_all = [], [], [], []
    for row in rows:
        plan, sizing = _bar_plan(X, m, sig, v3, built, row)
        for w in windows:
            a_s, z_s = _window_s(w)
            a_ix, z_ix = int(np.searchsorted(m.t, a_s, "left")), int(np.searchsorted(m.t, z_s, "left"))
            res, daily, trades = _bar_account(X, m, plan, sizing, a_ix, z_ix)
            met = account_metrics(daily, res.final, res.max_dd * 100.0, a_s, z_s, res.trades_pnl, res.wiped,
                                  _ts(res.wipe_t) if res.wiped else None)
            met.update(skipped_trades=int(res.skipped))
            out.append({**_ident(symbol, row, w), **met})
            if w == "8y":
                years += [{**_ident(symbol, row, w), **y} for y in yearly(daily, res.final, a_s, z_s)]
            curves.append(pd.DataFrame({"symbol": symbol, "label": row["label"], "window": w,
                                        "time": daily.index, "equity": daily.to_numpy()}))
            if len(trades):
                trades_all.append(trades.assign(symbol=symbol, label=row["label"], window=w))
            log(f"  {symbol} {row['label']:42s} {w:3s} final {res.final:10.2f}  DD {res.max_dd * 100:5.1f}%  "
                f"trades {len(res.trades_pnl):5d}{'  WIPED ' + met['wiped_at'] if res.wiped else ''}")
    return out, years, curves, trades_all


# the tick-engine rows ----------------------------------------------------------------------------------------------

def _ident(symbol: str, row: dict, w: str) -> dict:
    return {"symbol": symbol, "label": row["label"], "rank": row.get("rank"), "kind": row["kind"], "engine": row["engine"],
            "window": w, "start": WINDOWS[w][0], "end": WINDOWS[w][1]}


def _tick_daily(res) -> pd.Series:
    e = res.equity.set_index("time")["equity"]
    d = e.groupby(e.index.floor("D")).first()
    if len(d):
        d.iloc[0] = ACCOUNT
    return d


def _tick_trades(res) -> pd.DataFrame:
    b = res.baskets
    if b is None or not len(b):
        return pd.DataFrame()
    return pd.DataFrame({"open_time": b["open_time"], "close_time": b["close_time"], "side": b["side"],
                         "entry": b["first_price"], "exit": b["close_price"], "lots": b["lots"], "legs": b["n_pos"],
                         "why": b["reason"], "pnl": b["pnl"]})


def _tick_one(symbol: str, row: dict, w: str, cfg, prep, extra: Optional[dict] = None):
    from ..engine import fast
    res = fast.run(cfg.replace(**row["overrides"], **(extra or {})), prep, regime=row.get("_regime"))
    s = res.summary()
    a_s, z_s = _window_s(w)
    daily = _tick_daily(res)
    pnl = res.baskets["pnl"].to_numpy(np.float64) if len(res.baskets) else np.zeros(0)
    wiped = bool(s.get("stopped_out"))
    met = account_metrics(daily, float(s["final_equity"]), float(s["max_drawdown_pct"]), a_s, z_s, pnl, wiped,
                          pd.Timestamp(s["stopped_out_at"]) if wiped and s.get("stopped_out_at") else None)
    met.update(max_lots=float(s.get("max_lots", np.nan)), skipped_trades=0)
    return res, daily, met


def run_ticks(symbol: str, rows: List[dict], windows: Sequence[str], seeds: Sequence[int], log=print):
    import gc
    from .. import experiments as E
    from ..analysis.robustness import live_timing
    from ..engine import fast
    out, years, curves, trades_all, ens = [], [], [], [], []
    tfs_all = set()
    for row in rows:
        tfs_all |= set(E.live_config(symbol).replace(**row["overrides"]).timeframes())
    tfs = sorted(tfs_all | {"M1", "M5", "M15", "H1", "H4"}, key=["M1", "M5", "M15", "M30", "H1", "H4", "D1"].index)
    for w in windows:
        a, z = WINDOWS[w]
        mode = "ticks" if w == "1y" else "sec"
        t0 = pd.Timestamp.now()
        prep = fast.prepare(symbol, a, z, tfs, mode=mode)
        base = E.live_config(symbol, start=a, end=z)
        log(f"{symbol} {w}: {mode} data ready ({(pd.Timestamp.now() - t0).total_seconds():.0f}s)")
        for row in rows:
            if mode == "sec":
                res, daily, met = _tick_one(symbol, row, w, base, prep)
                rep, runs = (res, daily, met), [met]
            else:
                runs, keep = [], []
                for sd in seeds:
                    res, daily, met = _tick_one(symbol, row, w, base, prep, live_timing(sd))
                    runs.append(met)
                    keep.append((met["final_equity"], sd, res, daily, met))
                    ens.append({**_ident(symbol, row, w), "seed": int(sd), **met})
                keep.sort(key=lambda k: k[0])
                _, sd, res, daily, met = keep[len(keep) // 2]          # the median timing (upper median of eight)
                met = dict(met)
                rep = (res, daily, met)
            res, daily, met = rep
            fe = [r["final_equity"] for r in runs]
            met.update(runs=len(runs), final_min=round(min(fe), 2), final_max=round(max(fe), 2),
                       final_median=round(float(np.median(fe)), 2),
                       dd_median=round(float(np.median([r["max_dd_pct"] for r in runs])), 2),
                       dd_worst=round(max(r["max_dd_pct"] for r in runs), 2),
                       wiped_runs=int(sum(r["wiped"] for r in runs)))
            a_s, z_s = _window_s(w)
            out.append({**_ident(symbol, row, w), **met})
            if w == "8y":
                years += [{**_ident(symbol, row, w), **y} for y in yearly(daily, met["final_equity"], a_s, z_s)]
            curves.append(pd.DataFrame({"symbol": symbol, "label": row["label"], "window": w,
                                        "time": daily.index, "equity": daily.to_numpy()}))
            tr = _tick_trades(res)
            if len(tr):
                trades_all.append(tr.assign(symbol=symbol, label=row["label"], window=w))
            log(f"  {symbol} {row['label']:42s} {w:3s} final {met['final_equity']:10.2f}  DD {met['max_dd_pct']:5.1f}%  "
                f"trades {met['trades']:5d}" + (f"  timings {met['final_min']:.0f} .. {met['final_max']:.0f}" if len(runs) > 1 else "")
                + (f"  WIPED {met['wiped_at']}" if met["wiped"] else ""))
        del prep
        gc.collect()
    return out, years, curves, trades_all, ens


def supplement_rows(symbol: str, sel: dict) -> List[dict]:
    """
    Not pre-registered: the finalists' V3-lite hybrids as the bot would run them. The hybrids were chosen and tested on
    the M1-bar simulator, which reads the bot's votes on closed bars; the live bot reads them on the still-forming bar.
    Here each hybrid runs on the tick engine with V3-lite's settings and the same regime series (``external.py``'s own
    builder, from closed D1 / H4 bars, as a step function of time). Plus V3-lite on the tick engine with its votes read
    on closed bars, which separates the effect of the vote timing from the rest of the engine difference.
    """
    from . import external as X
    v3 = own_designs(symbol)["V3-lite"]
    rows = [dict(label="V3-lite, votes on closed bars", rank=None, kind="supplement", engine="ticks",
                 overrides={**v3, "slope_on_closed_bars": True})]
    hybrids = [r for r in sel["final"][symbol] if r["variant"] == "V3-lite + regime"]
    if hybrids:
        m = X.load_market(symbol, earliest=HISTORY_FROM[symbol], end=DATA_END)
        for r in hybrids:
            b = X.STRATEGY_BY_KEY[r["family"]].for_symbol(symbol)[r["params"]][1](m)
            rt, rv = b.regime
            rows.append(dict(label=f"{r['label']}, as the bot runs it", rank=None, kind="supplement", engine="ticks",
                             overrides=dict(v3), of=r["label"],
                             _regime=(np.asarray(rt, np.int64) * 1000, np.asarray(rv, np.int64))))
        del m
    return rows


def run_supplement(symbols: Sequence[str] = SYMBOLS, windows: Sequence[str] = tuple(WINDOWS), out: Path = OUT,
                   seeds: Sequence[int] = tuple(range(1, 9)), log=print) -> None:
    sel = load_selection(Path(out) / "selection.json")
    for sym in symbols:
        rows = supplement_rows(sym, sel)
        res, yrs, curves, trades, ens = run_ticks(sym, rows, windows, seeds, log)
        tag = f"{sym}_supplement"
        pd.DataFrame(res).to_csv(Path(out) / f"runs_{tag}.csv", index=False)
        pd.DataFrame(yrs).to_csv(Path(out) / f"years_{tag}.csv", index=False)
        pd.concat(curves, ignore_index=True).to_csv(Path(out) / f"equity_{tag}.csv.gz", index=False)
        if trades:
            pd.concat(trades, ignore_index=True).to_csv(Path(out) / f"trades_{tag}.csv.gz", index=False)
        if ens:
            pd.DataFrame(ens).to_csv(Path(out) / f"timings_1y_{tag}.csv", index=False)
        log(f"{sym}: supplement done")


def run(symbols: Sequence[str] = SYMBOLS, windows: Sequence[str] = tuple(WINDOWS), engines: Sequence[str] = ("bars", "ticks"),
        out: Path = OUT, cache_dir: Optional[Path] = None, seeds: Sequence[int] = tuple(range(1, 9)), log=print) -> None:
    sel = load_selection(out / "selection.json")
    out = Path(out)
    for sym in symbols:
        rows = sel["final"][sym] + sel["references"][sym]
        parts = {}
        if "bars" in engines:
            parts["bars"] = run_bars(sym, [r for r in rows if r["engine"] == "bars"], windows, cache_dir, log)
        if "ticks" in engines:
            parts["ticks"] = run_ticks(sym, [r for r in rows if r["engine"] == "ticks"], windows, seeds, log)
        for eng, p in parts.items():
            res, yrs, curves, trades = p[:4]
            tag = f"{sym}_{eng}"
            pd.DataFrame(res).to_csv(out / f"runs_{tag}.csv", index=False)
            pd.DataFrame(yrs).to_csv(out / f"years_{tag}.csv", index=False)
            if curves:
                pd.concat(curves, ignore_index=True).to_csv(out / f"equity_{tag}.csv.gz", index=False)
            if trades:
                pd.concat(trades, ignore_index=True).to_csv(out / f"trades_{tag}.csv.gz", index=False)
            if eng == "ticks" and p[4]:
                pd.DataFrame(p[4]).to_csv(out / f"timings_1y_{sym}.csv", index=False)
        log(f"{sym}: done")


# ───────────────────────────── the report ─────────────────────────────

KIND_NAME = {"own": "our design (tick engine)", "hybrid": "V3-lite + published filter (M1 bars)",
             "published": "published strategy (M1 bars)", "reference": "reference (not ranked)",
             "supplement": "V3-lite + filter as the bot runs it (tick engine, not pre-registered)",
             "warm": "added by the warm re-check (M1 bars, not pre-registered)"}
# one name per row everywhere in the write-up (the labels in the result files stay as selected)
DISPLAY = {"Long moving average + H1 trend": "MA 41/356 + H1 trend",
           "Long moving average [alt] + H1 trend": "MA 34/339 + H1 trend",
           "London breakout (risk-sized)": "London breakout, 1% risk",
           "Turtle (risk-sized)": "Turtle, 1% risk",
           "Noise-area momentum (risk-sized)": "Noise-area momentum, vol-targeted",
           "Turtle [alt] + bot votes": "Turtle System 2 + bot votes",
           "TSMOM [alt] (risk-sized)": "TSMOM 12-month, vol-targeted",
           "Donchian ensemble [alt] + H1 trend": "Donchian ensemble long/short + H1 trend",
           "Donchian ensemble [alt] + bot votes": "Donchian ensemble long/short + bot votes"}


def display(label: str) -> str:
    for k, v in DISPLAY.items():
        if label == k or label.startswith(k + ","):
            return v + label[len(k):]
    return label


def load_runs(out: Path = OUT) -> pd.DataFrame:
    """Every account of the run, one row per symbol, strategy and window. For the last year our designs ran under eight
    loop timings: their headline figures are the medians (final equity and drawdown), the range is kept."""
    d = pd.concat([pd.read_csv(p) for p in sorted(Path(out).glob("runs_*_*.csv"))], ignore_index=True)
    sel = load_selection(Path(out) / "selection.json")
    variant = {(s, r["label"]): r["variant"] for s in SYMBOLS for r in sel["final"][s] + sel["references"][s]}
    d["group"] = [("supplement" if k == "supplement" else "warm" if k == "warm" else "reference" if pd.isna(rk)
                   else ("hybrid" if variant.get((s, lab)) == "V3-lite + regime" else k))
                  for s, lab, rk, k in zip(d["symbol"], d["label"], d["rank"], d["kind"])]
    d["name"] = d["label"].map(display)
    # a wiped account's months run to the window's end (the engine's equity series stops at the stop-out)
    n_months = {w: len(pd.period_range(pd.Timestamp(a), pd.Timestamp(z) - pd.Timedelta(seconds=1), freq="M"))
                for w, (a, z) in WINDOWS.items()}
    wiped = d["wiped"].astype(bool)
    d.loc[wiped, "months"] = d.loc[wiped, "window"].map(n_months)
    if "final_median" in d:
        m = d["final_median"].notna()
        d.loc[m, "final_equity"] = d.loc[m, "final_median"]
        d.loc[m, "max_dd_pct"] = d.loc[m, "dd_median"]
    span = {w: (pd.Timestamp(a) , pd.Timestamp(z)) for w, (a, z) in WINDOWS.items()}
    yrs = d["window"].map(lambda w: (span[w][1] - span[w][0]).total_seconds() / YEAR_S)
    d["net"] = d["final_equity"] - ACCOUNT
    d["return_pct"] = d["net"] / ACCOUNT * 100.0
    d["cagr_pct"] = np.where(d["final_equity"] > 0, ((d["final_equity"] / ACCOUNT) ** (1.0 / yrs) - 1.0) * 100.0, -100.0)
    d["return_per_dd"] = np.where(yrs >= 1.0, d["cagr_pct"], d["return_pct"]) / d["max_dd_pct"].clip(lower=0.01)
    return d


def _usd0(x) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"${x:,.0f}"


def _pct(x, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    if signed and abs(x) < 0.05:
        return "0.0%"
    return f"{x:+.1f}%".replace("-", "−") if signed else f"{x:.1f}%"


def _barely(r) -> bool:
    """A row that skipped most of its signals (too small for 0.01 lot): its drawdown says little."""
    return bool(r.get("skipped_trades", 0) and r["skipped_trades"] > r["trades"])


def table(d: pd.DataFrame, symbol: str, window: str, groups: Optional[Sequence[str]] = None) -> str:
    keep = d["group"].isin(groups) if groups else ~d["group"].isin(["supplement", "warm"])
    t = d[(d["symbol"] == symbol) & (d["window"] == window) & keep].copy()
    t["_ref"] = t["rank"].isna()
    t = t.sort_values(["_ref", "final_equity"], ascending=[True, False])
    growth = "Growth / year" if window != "1y" else "Return"
    head = ["Strategy", "Engine", "Final equity", growth, "Max DD", f"{growth} ÷ DD", "Trades", "Win rate",
            "Profit factor", "Losing months", "Longest dip", "Notes"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, r in t.iterrows():
        if not r["_ref"]:
            name = f"**#{int(r['rank'])} {r['name']}**"
        elif r["group"] == "warm":
            name = f"*{r['name']}* (warm re-check #{int(r['warm_rank'])})"
        elif r["group"] == "supplement":
            name = f"*{r['name']}* (not pre-registered)"
        else:
            name = f"*{r['name']}* (reference)"
        notes = []
        if r.get("wiped"):
            notes.append(f"wiped {r['wiped_at']}")
        elif r["final_equity"] < 50:
            notes.append("account destroyed")
        if r.get("skipped_trades", 0) and r["skipped_trades"] > 0:
            n_sig = int(r["skipped_trades"] + r["trades"])
            notes.append(("barely traded: " if _barely(r) else "") +
                         f"{int(r['skipped_trades'])} of {n_sig} signals too small for 0.01 lot")
        if r.get("runs", 1) and r.get("runs", 1) > 1:
            notes.append(f"median of 8 timings, range {_usd0(r['final_min'])} – {_usd0(r['final_max'])}")
        g = r["cagr_pct"] if window != "1y" else r["return_pct"]
        lines.append("| " + " | ".join([
            name, "ticks" if r["engine"] == "ticks" else "M1 bars", _usd0(r["final_equity"]), _pct(g, True),
            _pct(r["max_dd_pct"]), f"{r['return_per_dd']:.2f}", f"{int(r['trades']):,}",
            _pct(r["win_rate_pct"]), "n/a" if pd.isna(r["profit_factor"]) else f"{r['profit_factor']:.2f}",
            f"{int(r['losing_months'])} of {int(r['months'])}", f"{int(r['longest_underwater_days'])} days",
            "; ".join(notes)]) + " |")
    return "\n".join(lines)


def rankings(d: pd.DataFrame, symbol: str, window: str, n: int = 3) -> Dict[str, List[str]]:
    """Among the ten finalists. Rows that skipped most of their signals are left out of the drawdown ranking (they
    barely traded) and named after it."""
    t = d[(d["symbol"] == symbol) & (d["window"] == window) & d["rank"].notna()]
    fmt = lambda r: f"#{int(r['rank'])} {r['name']} ({_usd0(r['final_equity'])}, DD {_pct(r['max_dd_pct'])})"
    active = t[~t.apply(_barely, axis=1)]
    low = [fmt(r) for _, r in active.sort_values("max_dd_pct").head(n).iterrows()]
    out = {"highest equity": [fmt(r) for _, r in t.sort_values("final_equity", ascending=False).head(n).iterrows()],
           "lowest drawdown": low,
           "best balance": [fmt(r) for _, r in t.sort_values("return_per_dd", ascending=False).head(n).iterrows()]}
    skipped = t[t.apply(_barely, axis=1)]
    if len(skipped):
        out["lowest drawdown"].append("not ranked, barely traded: " + "; ".join(
            f"#{int(r['rank'])} {r['name']} (DD {_pct(r['max_dd_pct'])}, {int(r['trades'])} trades)" for _, r in skipped.iterrows()))
    return out


def years_table(out: Path, symbol: str) -> pd.DataFrame:
    """Return in each calendar year of the eight-year accounts; blank once an account is destroyed (under $50)."""
    y = pd.concat([pd.read_csv(p) for p in sorted(Path(out).glob(f"years_{symbol}_*.csv")) if p.stat().st_size > 2],
                  ignore_index=True)
    y.loc[y["start_equity"] < 50, "return_pct"] = np.nan
    return y.pivot_table(index="label", columns="year", values="return_pct", aggfunc="first", dropna=False)


def _color(group: str) -> str:
    from ..viz import theme as T
    return {"own": T.SERIES[0], "hybrid": T.SERIES[1], "published": T.SERIES[2]}.get(group, T.CONTEXT)


SHORT_REF = {"Owner's rules + H1 trend + 4 h pause": "Owner's rules", "V3-lite (bar level)": "V3-lite, bars"}
_POSITIONS = {"top center": (0, 1), "bottom center": (0, -1), "middle right": (1, 0), "middle left": (-1, 0),
              "top right": (1, 1), "top left": (-1, 1), "bottom right": (1, -1), "bottom left": (-1, -1)}


def _place_labels(xs, ys, texts, xr, yr, wpx: float, hpx: float, char_px: float = 8.6, line_px: float = 16.0,
                  xlog: bool = False) -> List[str]:
    """A text position for every dot so that labels overlap neither each other nor the dots, as far as they can.
    Works in pixels of the plot area (``wpx`` x ``hpx``) for the axis ranges ``xr`` / ``yr`` (``xr`` in log10 units
    when ``xlog``)."""
    if xlog:
        px = [(np.log10(max(x, 1e-9)) - xr[0]) / (xr[1] - xr[0]) * wpx for x in xs]
    else:
        px = [(x - xr[0]) / (xr[1] - xr[0]) * wpx for x in xs]
    py = [(y - yr[0]) / (yr[1] - yr[0]) * hpx for y in ys]
    dots = [(x - 7, y - 7, x + 7, y + 7) for x, y in zip(px, py)]
    placed: List[tuple] = []
    out = []

    def overlap(a, b):
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))

    for i, (x, y, t) in enumerate(zip(px, py, texts)):
        w = len(t) * char_px
        best, best_cost = "top center", None
        for name, (dx, dy) in _POSITIONS.items():
            cx = x + dx * (8 + w / 2) if dx else x
            cy = y + dy * (6 + line_px / 2) if dy else y
            box = (cx - w / 2, cy - line_px / 2, cx + w / 2, cy + line_px / 2)
            cost = sum(overlap(box, b) for b in placed) + sum(overlap(box, d) for j, d in enumerate(dots) if j != i)
            # a label must sit nearer its own dot than any other, judged from the label's nearest edge, or it reads as
            # the other dot's
            def edge(qx, qy, bx=box):
                return float(np.hypot(max(bx[0] - qx, 0.0, qx - bx[2]), max(bx[1] - qy, 0.0, qy - bx[3])))
            own = edge(x, y)
            for j, (ox, oy) in enumerate(zip(px, py)):
                if j != i:
                    dj = edge(ox, oy)
                    if dj < own + 10:
                        cost += (own + 10 - dj) * 80.0
            if box[0] < 0 or box[2] > wpx or box[1] < 0 or box[3] > hpx:
                cost += 1e6
            if best_cost is None or cost < best_cost - 1e-9:
                best, best_cost, best_box = name, cost, box
            if cost == 0:
                break
        placed.append(best_box)
        out.append(best)
    return out


def figure_risk_return(d: pd.DataFrame, window: str):
    """Per symbol: maximum drawdown against growth, one dot per account. Finalists are labelled with their number (the
    key under each panel names them), references by a short name; wiped accounts are left out (they are in the tables)."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from ..viz import theme as T
    gl = "growth per year (CAGR)" if window != "1y" else "return over the year"
    width, height, margin = 1500, 820, dict(l=64, r=24, t=96, b=230)
    hs = 0.09
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Gold (XAUUSDm)", "BTC (BTCUSDm)"], horizontal_spacing=hs)
    shown = set()
    wpx = (width - margin["l"] - margin["r"]) * (1 - hs) / 2
    hpx = height - margin["t"] - margin["b"]
    # one kind of drawdown axis for the whole figure: logarithmic if either panel spans more than a factor of 8
    spans = []
    for sym in SYMBOLS:
        tt = d[(d["symbol"] == sym) & (d["window"] == window) & (d["final_equity"] > 50) & (d["group"] != "warm")]
        if len(tt):
            spans.append(float(tt["max_dd_pct"].max()) / max(float(tt["max_dd_pct"].min()), 0.05))
    fig_log = any(s > 8 for s in spans)
    for c, sym in enumerate(SYMBOLS, 1):
        t = d[(d["symbol"] == sym) & (d["window"] == window) & (d["final_equity"] > 50) & (d["group"] != "warm")].copy()
        t = t[~t["label"].str.contains("votes on closed bars", regex=False)]
        t["_y"] = t["cagr_pct"] if window != "1y" else t["return_pct"]
        ranks = {r["label"]: r["rank"] for _, r in d[(d["symbol"] == sym) & (d["group"] == "hybrid")].iterrows()}
        t["_short"] = [f"{int(ranks.get(lab.replace(', as the bot runs it', ''), 0))}t" if grp == "supplement"
                       else (str(int(rk)) if pd.notna(rk) else SHORT_REF.get(lab, lab))
                       for rk, lab, grp in zip(t["rank"], t["label"], t["group"])]
        # one account far above the rest (a compounding risk-sized row) is noted at the top edge, not plotted:
        # it would squeeze every other dot into a sliver
        off = None
        ys_sorted = t["_y"].sort_values(ascending=False)
        if len(ys_sorted) >= 3 and ys_sorted.iloc[0] > 2.5 * max(ys_sorted.iloc[1], 1.0) and ys_sorted.iloc[0] - ys_sorted.iloc[1] > 25:
            off = t.loc[ys_sorted.index[0]]
            t = t.drop(index=ys_sorted.index[0])
        xmin, xmax = (float(t["max_dd_pct"].min()), float(t["max_dd_pct"].max())) if len(t) else (1.0, 10.0)
        xlog = fig_log
        ylo, yhi = (float(t["_y"].min()), float(t["_y"].max())) if len(t) else (0.0, 1.0)
        pad = max(0.08 * (yhi - ylo), 1.0)
        xr = [np.log10(max(xmin, 0.05) * 0.7), np.log10(xmax * 1.35)] if xlog else [0.0, xmax * 1.12 + 1.0]
        yr = [min(0.0, ylo - pad), yhi + pad]
        t = t.assign(_ord=t["rank"].fillna(99)).sort_values("_ord")
        t["_pos"] = _place_labels(t["max_dd_pct"].tolist(), t["_y"].tolist(), t["_short"].tolist(), xr, yr, wpx, hpx,
                                  xlog=xlog)
        off_note = "" if off is None else (
            f"↑ not plotted, far above the scale: {off['_short']} {display(off['label'])}, {off['_y']:+.0f}% "
            f"{'a year' if window != '1y' else 'over the year'}, max DD {off['max_dd_pct']:.1f}%<br>")
        for grp in ("own", "hybrid", "published", "reference", "supplement"):
            g = t[t["group"] == grp]
            if g.empty:
                continue
            y = g["_y"]
            short = g["_short"].tolist()
            full = [(f"#{int(rk)} " if pd.notna(rk) else "") + display(lab) for rk, lab in zip(g["rank"], g["label"])]
            fig.add_trace(go.Scatter(
                x=g["max_dd_pct"], y=y, mode="markers+text", text=short, textposition=g["_pos"].tolist(),
                textfont=dict(color=T.INK, size=12), name=KIND_NAME[grp], legendgroup=grp, showlegend=grp not in shown,
                marker=dict(size=11, color=_color("hybrid" if grp == "supplement" else grp),
                            symbol="diamond" if grp == "supplement" else "circle", line=dict(color=T.SURFACE, width=2)),
                customdata=np.stack([g["final_equity"], g["trades"], full], axis=1),
                hovertemplate="<b>%{y:.1f}%</b> " + gl + " · max DD %{x:.1f}%<br>final $%{customdata[0]:,.0f} · "
                              "%{customdata[1]} trades<br>%{customdata[2]}<extra></extra>"), row=1, col=c)
            shown.add(grp)
        fin = d[(d["symbol"] == sym) & (d["window"] == window) & d["rank"].notna()].sort_values("rank")
        names = [f"{int(r['rank'])} {r['name']}" for _, r in fin.iterrows()]
        half = (len(names) + 1) // 2
        key = off_note + "<br>".join(f"{a:<46s}  {b}" if b else a for a, b in zip(names[:half], names[half:] + [""] * half))
        if (t["group"] == "supplement").any():
            key += "<br>◆ 3t, 4t, ...: the same hybrid on the tick engine, as the bot would run it (not pre-registered)"
        fig.add_annotation(text=key, xref=f"x{'' if c == 1 else c} domain", yref=f"y{'' if c == 1 else c} domain",
                           x=0.0, y=-0.16, xanchor="left", yanchor="top", align="left", showarrow=False,
                           font=dict(color=T.INK_2, size=11, family="ui-monospace, Menlo, monospace"))
        xticks = [v for v in (0.2, 0.5, 1, 2, 5, 10, 20, 50, 100) if 10 ** xr[0] <= v <= 10 ** xr[1]] if xlog else None
        fig.update_xaxes(T.axis(title_text="maximum drawdown, % of the equity peak (less is better)"
                                           + (", log scale" if xlog else ""),
                                type="log" if xlog else "linear", range=xr,
                                **({"tickvals": xticks, "ticktext": [f"{v:g}" for v in xticks]} if xlog else {})),
                         row=1, col=c)
        fig.update_yaxes(T.axis(title_text=gl + ", % (more is better)", range=yr), row=1, col=c)
    fig.update_layout(**T.plotly_layout(height=height, hovermode="closest", margin=margin))
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0))
    for a in fig.layout.annotations:
        if a.text in ("Gold (XAUUSDm)", "BTC (BTCUSDm)"):
            a.font = dict(color=T.INK, size=13)
    return fig


def _log_ticks(lo: float, hi: float) -> List[float]:
    cands = [100, 200, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 7500, 10000, 15000, 20000, 30000, 50000,
             75000, 100000, 150000, 200000]
    ticks = [v for v in cands if lo <= v <= hi]
    while len(ticks) > 7:
        ticks = ticks[::2]
    return ticks


def figure_equity(d: pd.DataFrame, curves: pd.DataFrame, symbol: str, window: str, cols: int = 3,
                  labels: Optional[Sequence[str]] = None, colors: Optional[Dict[str, str]] = None):
    """Small multiples: one panel per account. All panels share one log scale, except an account far above the rest
    (a compounding risk-sized row), which gets its own and says so. A wiped or destroyed account is marked."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from ..viz import theme as T
    t = d[(d["symbol"] == symbol) & (d["window"] == window)].copy()
    t = t[t["label"].isin(labels)] if labels is not None else t[~t["group"].isin(["supplement", "warm"])]
    t["_ref"] = t["rank"].isna()
    if labels is not None:
        t["_ord"] = t["label"].map({lab: i for i, lab in enumerate(labels)})
        t = t.sort_values("_ord")
    else:
        t = t.sort_values(["_ref", "rank", "final_equity"], ascending=[True, True, False])
    n = len(t)
    rows = int(np.ceil(n / cols))
    cv = curves[(curves["symbol"] == symbol) & (curves["window"] == window)]
    alive_rows = t[t["final_equity"] > 50]
    finals = alive_rows["final_equity"].sort_values(ascending=False)
    outlier = finals.index[0] if len(finals) >= 3 and finals.iloc[0] > 3 * finals.iloc[1] else None
    common = cv[cv["label"].isin(alive_rows.drop(index=[outlier] if outlier is not None else []).loc[:, "label"])]["equity"]
    lo, hi = float(common.min()) * 0.92, float(common.max()) * 1.08

    def title(r):
        head = f"#{int(r['rank'])} " if pd.notna(r["rank"]) else ("" if labels is not None else "ref · ")
        own = " (own scale)" if r.name == outlier else ""
        return f"{head}{r['name']} — {_usd0(r['final_equity'])}, DD {_pct(r['max_dd_pct'])}{own}"
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=[title(r) for _, r in t.iterrows()], shared_xaxes=True,
                        vertical_spacing=0.06 if rows > 3 else 0.1, horizontal_spacing=0.05)
    for i, (idx, r) in enumerate(t.iterrows()):
        rr, cc = i // cols + 1, i % cols + 1
        e = cv[cv["label"] == r["label"]]
        y = e["equity"].clip(lower=1.0)
        color = (colors or {}).get(r["label"]) or _color("hybrid" if r["group"] == "supplement" else r["group"])
        fig.add_trace(go.Scatter(x=e["time"], y=y, mode="lines", line=dict(color=color, width=1.6), name=r["name"],
                                 showlegend=False,
                                 hovertemplate="<b>$%{y:,.0f}</b><br>%{x|%d %b %Y}<extra>" + r["name"] + "</extra>"),
                      row=rr, col=cc)
        fig.add_hline(y=ACCOUNT, line=dict(color=T.AXIS, width=1), row=rr, col=cc)
        if window == "8y":
            fig.add_vrect(x0=WINDOWS["new"][0], x1=WINDOWS["new"][1], fillcolor=T.INK_MUTED, opacity=0.08,
                          line_width=0, row=rr, col=cc)
        if idx == outlier:
            olo, ohi = float(e["equity"].min()) * 0.92, float(e["equity"].max()) * 1.08
            oticks = _log_ticks(olo, ohi)
            fig.update_yaxes(T.axis(type="log", range=[np.log10(olo), np.log10(ohi)], tickvals=oticks,
                                    ticktext=[f"${v:,.0f}" for v in oticks]), row=rr, col=cc)
        else:
            ticks = _log_ticks(lo, hi)
            fig.update_yaxes(T.axis(type="log", range=[np.log10(lo), np.log10(hi)], tickvals=ticks,
                                    ticktext=[f"${v:,.0f}" for v in ticks], showticklabels=(cc == 1)), row=rr, col=cc)
        if r["final_equity"] <= 50 and len(e):
            dead = e[e["equity"] < 50]
            when = pd.Timestamp(dead["time"].iloc[0]) if len(dead) else pd.Timestamp(e["time"].iloc[-1])
            word = "wiped" if bool(r.get("wiped")) else "destroyed"
            if word == "wiped" and isinstance(r.get("wiped_at"), str) and r["wiped_at"]:
                when = pd.Timestamp(r["wiped_at"], tz="UTC")          # the stop-out itself, as the tables give it
            fig.add_trace(go.Scatter(x=[when], y=[lo * 1.06], mode="markers+text", text=[f"{word} {when:%d %b %Y}"],
                                     textposition="middle right", textfont=dict(color=T.INK, size=11),
                                     marker=dict(symbol="x-thin", size=12, line=dict(color=T.DOWN, width=2)),
                                     showlegend=False, hoverinfo="skip"), row=rr, col=cc)
    fig.update_xaxes(T.axis())
    fig.update_layout(**T.plotly_layout(height=max(420, 230 * rows), hovermode="closest",
                                        margin=dict(l=64, r=16, t=48, b=30)))
    fig.update_annotations(font=dict(color=T.INK_2, size=11))
    return fig


def figure_years(out: Path, d: pd.DataFrame, symbol: str):
    import plotly.graph_objects as go
    from ..viz import theme as T
    y = years_table(out, symbol)
    t = d[(d["symbol"] == symbol) & (d["window"] == "8y") & ~d["group"].isin(["supplement", "warm"])].copy()
    t["_ref"] = t["rank"].isna()
    order = t.sort_values(["_ref", "rank", "final_equity"], ascending=[True, True, False])["label"].tolist()
    order = [o for o in order if o in y.index]
    y = y.loc[order]
    names = [(f"#{int(rk)} " if pd.notna(rk) else "ref · ") + display(lab)
             for lab in order for rk in [t.loc[t["label"] == lab, "rank"].iloc[0]]]
    cols = [f"{c}" + (" (Nov–Dec)" if c == 2018 else " (to 13 Nov)" if c == 2026 else "") for c in y.columns]
    z = y.to_numpy(dtype=float)
    cap = 60.0

    def blend(c1, c2, f):
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{int(round(x + (yv - x) * f)):02x}" for x, yv in zip(a, b))
    mid = T.SURFACE_2
    scale = [[0.0, blend(mid, T.DOWN, 0.8)], [0.5, mid], [1.0, blend(mid, T.UP, 0.8)]]
    text = [[("–" if not np.isfinite(v) else "0%" if round(v) == 0 else f"{int(round(v)):+d}%".replace("-", "−"))
             for v in row] for row in z]
    fig = go.Figure(go.Heatmap(z=np.clip(z, -cap, cap), x=cols, y=names, colorscale=scale, zmid=0, zmin=-cap, zmax=cap,
                               text=text, texttemplate="%{text}", textfont=dict(color=T.INK, size=11),
                               customdata=z, xgap=2, ygap=2,
                               hovertemplate="<b>%{customdata:+.1f}%</b> in %{x}<br>%{y}<extra></extra>",
                               colorbar=dict(title=dict(text="return in the year", font=dict(color=T.INK_MUTED, size=11)),
                                             ticksuffix="%", tickfont=dict(color=T.INK_MUTED, size=10), outlinewidth=0)))
    fig.update_yaxes(T.axis(autorange="reversed", showgrid=False))
    fig.update_xaxes(T.axis(side="top", showgrid=False))
    fig.update_layout(**T.plotly_layout(height=70 + 34 * len(names), hovermode="closest",
                                        margin=dict(l=260, r=20, t=40, b=20)))
    return fig


def figure_trades(out: Path, curves: pd.DataFrame, symbol: str, label: str, window: str = "1y", tf: str = "4h"):
    """Price (H4 candles of the bid) with every trade of one account: entry, exit and the line between them, coloured
    by the trade's result; the account's equity below (its own axis, not a second scale on the price)."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from ..data import store
    from ..viz import theme as T
    a, z = WINDOWS[window]
    m1 = store.load_m1(symbol, a, z)
    px = pd.DataFrame({"o": m1["o"], "h": m1["h"], "l": m1["l"], "c": m1["c"]},
                      index=pd.to_datetime(m1["t"], unit="s", utc=True))
    bars = px.resample(tf, label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    tr = pd.concat([pd.read_csv(p, parse_dates=["open_time", "close_time"]) for p in sorted(Path(out).glob(f"trades_{symbol}_*.csv.gz"))],
                   ignore_index=True)
    tr = tr[(tr["label"] == label) & (tr["window"] == window)].copy()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(go.Candlestick(x=bars.index, open=bars["o"], high=bars["h"], low=bars["l"], close=bars["c"], name="price (bid, H4)",
                                 increasing=dict(line=dict(color=T.UP, width=1), fillcolor=T.UP),
                                 decreasing=dict(line=dict(color=T.DOWN, width=1), fillcolor=T.DOWN),
                                 showlegend=False, hoverinfo="skip"), row=1, col=1)
    if len(tr):
        won = tr["pnl"] > 0
        for ok, color, nm in ((True, T.UP, "won"), (False, T.DOWN, "lost")):
            g = tr[won == ok]
            xs, ys = [], []
            for _, r in g.iterrows():
                xs += [r["open_time"], r["close_time"], None]
                ys += [r["entry"], r["exit"], None]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=1.2), opacity=0.8,
                                     name=f"trade {nm}", hoverinfo="skip", legendgroup=nm), row=1, col=1)
        for side, sym_, nm in (("BUY", "triangle-up", "buy entry"), ("SELL", "triangle-down", "sell entry")):
            g = tr[tr["side"] == side]
            fig.add_trace(go.Scatter(x=g["open_time"], y=g["entry"], mode="markers", name=nm,
                                     marker=dict(symbol=sym_, size=9, color=T.INK, line=dict(color=T.SURFACE, width=1.5)),
                                     customdata=np.stack([g["pnl"], g["close_time"].astype(str)], axis=1),
                                     hovertemplate="<b>%{customdata[0]:+,.2f} USD</b><br>" + side +
                                                   " %{y:,.2f} · %{x|%d %b %H:%M}<br>closed %{customdata[1]}<extra></extra>"),
                          row=1, col=1)
        fig.add_trace(go.Scatter(x=tr["close_time"], y=tr["exit"], mode="markers", name="exit",
                                 marker=dict(symbol="x-thin", size=8, line=dict(color=T.INK_2, width=1.5)),
                                 customdata=np.stack([tr["pnl"], tr["why"].astype(str)], axis=1),
                                 hovertemplate="<b>%{customdata[0]:+,.2f} USD</b> exit %{y:,.2f}<br>%{customdata[1]} · "
                                               "%{x|%d %b %H:%M}<extra></extra>"), row=1, col=1)
    e = curves[(curves["symbol"] == symbol) & (curves["label"] == label) & (curves["window"] == window)]
    fig.add_trace(go.Scatter(x=e["time"], y=e["equity"], mode="lines", line=dict(color=T.SERIES[0], width=1.8),
                             name="equity", hovertemplate="<b>$%{y:,.0f}</b> %{x|%d %b %Y}<extra>equity</extra>"), row=2, col=1)
    fig.add_hline(y=ACCOUNT, line=dict(color=T.AXIS, width=1), row=2, col=1)
    fig.update_xaxes(T.axis(rangeslider=dict(visible=False)))
    fig.update_yaxes(T.axis(title_text="price"), row=1, col=1)
    fig.update_yaxes(T.axis(title_text="equity, USD", tickprefix="$"), row=2, col=1)
    fig.update_layout(**T.plotly_layout(height=760, hovermode="closest", margin=dict(l=70, r=20, t=40, b=30)))
    return fig


def _write_fig(fig, out: Path, name: str, title: str, subtitle: str, width: int = 1500) -> Optional[Path]:
    from ..viz import snapshot
    html = out / f"{name}.html"
    fig.write_html(html, include_plotlyjs="../assets/plotly.min.js", full_html=True,
                   config={"displaylogo": False, "responsive": True})
    return snapshot.figure_png(fig, out / "img" / f"{name}.png", width=width, title=title, subtitle=subtitle)


def years_md(out: Path, d: pd.DataFrame, symbol: str) -> str:
    y = years_table(out, symbol)
    t = d[(d["symbol"] == symbol) & (d["window"] == "8y") & ~d["group"].isin(["supplement", "warm"])].copy()
    t["_ref"] = t["rank"].isna()
    order = [o for o in t.sort_values(["_ref", "rank", "final_equity"], ascending=[True, True, False])["label"] if o in y.index]
    cols = list(y.columns)
    head = ["Strategy"] + [f"{c}" + ("*" if c in (2018, 2026) else "") for c in cols]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for lab in order:
        rk = t.loc[t["label"] == lab, "rank"].iloc[0]
        name = f"#{int(rk)} {display(lab)}" if pd.notna(rk) else f"*{display(lab)}*"
        lines.append("| " + " | ".join([name] + [_pct(y.loc[lab, c], True) if pd.notna(y.loc[lab, c]) else "–"
                                                 for c in cols]) + " |")
    return "\n".join(lines)


def supplement_md(d: pd.DataFrame, symbol: str) -> str:
    """V3-lite and its hybrids on both engines, every window: final equity and maximum drawdown."""
    t = d[d["symbol"] == symbol]
    rows = [("V3-lite", "M1 bars, votes on closed bars", "V3-lite (bar level)"),
            ("V3-lite", "tick engine, votes on closed bars", "V3-lite, votes on closed bars"),
            ("V3-lite", "tick engine, votes on the forming bar (as the bot)", "V3-lite")]
    for lab in t.loc[t["group"] == "hybrid", "label"].unique():
        rows.append((lab, "M1 bars, votes on closed bars (pre-registered)", lab))
        rows.append((lab, "tick engine, votes on the forming bar (as the bot)", f"{lab}, as the bot runs it"))
    head = ["Design", "Engine and vote timing"] + [WINDOW_NAMES[w].split(",")[0] for w in WINDOWS]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for design, how, lab in rows:
        cells = []
        for w in WINDOWS:
            r = t[(t["label"] == lab) & (t["window"] == w)]
            cells.append("–" if r.empty else f"{_usd0(r['final_equity'].iloc[0])}, DD {_pct(r['max_dd_pct'].iloc[0])}")
        lines.append("| " + " | ".join([design, how] + cells) + " |")
    return "\n".join(lines)


def _period_trades() -> Dict[tuple, int]:
    """Trades of each published row in each selection period, as the study the selection read had them."""
    ext = pd.concat([pd.read_csv(IMPROVE / "external_strategies.csv", dtype={"period": str}),
                     pd.read_csv(IMPROVE / "external_strategies_holdout_2021_22.csv", dtype={"period": str})],
                    ignore_index=True)
    return {(r.symbol, r.strategy, r.params, r.variant, r.sizing, r.period): int(r.trades) for r in ext.itertuples()}


def _source(r) -> str:
    return "ours" if r["kind"] == "own" else ("hybrid" if r["variant"] == "V3-lite + regime" else "published")


def finalists_md(symbol: str, evidence_file: str = "evidence.csv", selection_file: str = "selection.json") -> str:
    """The finalists with the evidence that chose them, rounded once from evidence.csv; a period in which the row
    took no trade at all says so."""
    E = pd.read_csv(OUT / evidence_file)
    sel = json.loads((OUT / selection_file).read_text())
    trades = _period_trades()
    head = ["#", "Strategy", "Source"] + list(P5) + ["Periods up", "Worst-quarter DD", "Score"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for f in sel["final"][symbol]:
        m = (E["symbol"] == symbol) & (E["name"] == f["name"]) & (E["params"] == f["params"]) & \
            (E["variant"] == f["variant"]) & (E["sizing"] == f["sizing"])
        r = E[m].iloc[0]
        cells = []
        for p in P5:
            n = trades.get((symbol, r["family"], r["params"], r["variant"], r["sizing"], p)) if r["kind"] == "published" else None
            if f"trades_{p}" in r and pd.notna(r.get(f"trades_{p}")):
                n = int(r[f"trades_{p}"])
            cells.append("no trades" if n == 0 else f"{r[p]:+.0f}".replace("-", "−"))
        lines.append("| " + " | ".join([str(f["rank"]), display(f["label"]), _source(r)] + cells +
                                        [f"{int(r['periods_up'])} of 5", f"{r['dd_fresh']:.1f}%", f"{r['profit_per_dd']:.2f}"]) + " |")
    return "\n".join(lines)


def warm_md(symbol: str) -> str:
    """The pre-registered published / hybrid finalists: the evidence the selection read against the same rows run warm."""
    cold = pd.read_csv(OUT / "evidence.csv")
    warm = pd.read_csv(OUT / "evidence_warm.csv")
    sel = load_selection()
    trades = _period_trades()
    head = ["#", "Strategy", "As selected (cold start)", "Re-run warm", "Periods up, cold → warm", "Still eligible"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for f in sel["final"][symbol]:
        if f["engine"] != "bars":
            continue
        key = lambda E: E[(E["symbol"] == symbol) & (E["name"] == f["name"]) & (E["params"] == f["params"]) &
                          (E["variant"] == f["variant"]) & (E["sizing"] == f["sizing"])].iloc[0]
        c, w = key(cold), key(warm)
        cs = " / ".join("no trades" if trades.get((symbol, c["family"], c["params"], c["variant"], c["sizing"], p)) == 0
                        else f"{c[p]:+.0f}".replace("-", "−") for p in P5)
        ws = " / ".join("no trades" if int(w[f"trades_{p}"]) == 0 else f"{w[p]:+.0f}".replace("-", "−") for p in P5)
        lines.append("| " + " | ".join([str(f["rank"]), display(f["label"]), cs, ws,
                                        f"{int(c['periods_up'])} → {int(w['periods_up'])}",
                                        "yes" if bool(w["eligible"]) else "**no**"]) + " |")
    return "\n".join(lines)


def warm_ten_md(d: pd.DataFrame, symbol: str) -> str:
    """The ten the same rule picks on warm evidence, with their accounts in every window."""
    doc = json.loads((OUT / "selection_warm.json").read_text())
    pre = {r["label"] for r in load_selection()["final"][symbol]}
    head = ["Warm #", "Strategy", "In the pre-registered ten?"] + [WINDOW_NAMES[w].split(",")[0] for w in WINDOWS]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    t = d[d["symbol"] == symbol]
    for f in doc["final"][symbol]:
        cells = []
        for w in WINDOWS:
            r = t[(t["label"] == f["label"]) & (t["window"] == w) & (t["group"] != "supplement")]
            cells.append("–" if r.empty else f"{_usd0(r['final_equity'].iloc[0])}, DD {_pct(r['max_dd_pct'].iloc[0])}")
        lines.append("| " + " | ".join([str(f["rank"]), display(f["label"]), "yes" if f["label"] in pre else "**new**"]
                                       + cells) + " |")
    return "\n".join(lines)


def fill(template: str, out: Path, d: pd.DataFrame) -> str:
    """Replace ``{{table:WINDOW:SYMBOL}}``, ``{{years:SYMBOL}}``, ``{{rank:WINDOW:SYMBOL}}`` and
    ``{{supplement:SYMBOL}}`` in the write-up."""
    import re

    def sub(mt):
        kind, *args = mt.group(1).split(":")
        if kind == "supplement":
            return supplement_md(d, args[0])
        if kind == "finalists":
            return finalists_md(args[0])
        if kind == "warm":
            return warm_md(args[0])
        if kind == "warmten":
            return warm_ten_md(d, args[0])
        if kind == "warmtable":
            return table(d, args[1], args[0], groups=["warm"])
        if kind == "table":
            return table(d, args[1], args[0])
        if kind == "years":
            return years_md(out, d, args[0])
        if kind == "rank":
            r = rankings(d, args[1], args[0])
            lines = []
            for k, v in r.items():
                ranked = [s for s in v if not s.startswith("not ranked")]
                notes = [s for s in v if s.startswith("not ranked")]
                lines.append(f"- **{k.capitalize()}** (among the ten): " + "; ".join(f"{i}. {s}" for i, s in enumerate(ranked, 1))
                             + ("" if not notes else f". *{notes[0][0].upper() + notes[0][1:]}.*"))
            return "\n".join(lines)
        raise KeyError(mt.group(0))
    return re.sub(r"\{\{([^}]+)\}\}", sub, template)


def report(out: Path = OUT, images: bool = True, log=print) -> pd.DataFrame:
    out = Path(out)
    d = load_runs(out)
    d.to_csv(out / "results.csv", index=False)
    tpl = out / "FINAL10.template.md"
    if tpl.exists():
        (out / "FINAL10.md").write_text(fill(tpl.read_text(), out, d))
    curves = pd.concat([pd.read_csv(p, parse_dates=["time"]) for p in sorted(out.glob("equity_*_*.csv.gz"))],
                       ignore_index=True)
    if images:
        for w in WINDOWS:
            _write_fig(figure_risk_return(d, w), out, f"risk_return_{w}", f"Risk and return · {WINDOW_NAMES[w]}",
                       "one fresh $2,000 account per strategy; up and to the left is better; wiped accounts not shown")
            for sym in SYMBOLS:
                _write_fig(figure_equity(d, curves, sym, w), out, f"equity_{w}_{sym}",
                           f"{sym} · equity of one $2,000 account · {WINDOW_NAMES[w]}",
                           "log scale; the line at $2,000 is the starting balance" +
                           ("; shaded: Nov 2018 - Dec 2020, never read by any earlier study" if w == "8y" else ""))
                log(f"  charts {w} {sym}")
        for sym in SYMBOLS:
            _write_fig(figure_years(out, d, sym), out, f"years_{sym}", f"{sym} · return in each calendar year",
                       "the eight-year account (Nov 2018 - Nov 2026); return on the equity at the start of the year")
            from ..viz import theme as T
            labs = ["V3-lite", "V3-lite, votes on closed bars", "V3-lite (bar level)"]
            cols_ = {"V3-lite": T.SERIES[0], "V3-lite, votes on closed bars": T.CONTEXT, "V3-lite (bar level)": T.SERIES[1]}
            for lab in d.loc[(d["symbol"] == sym) & (d["group"] == "hybrid"), "label"].unique():
                labs += [lab, f"{lab}, as the bot runs it"]
                cols_[lab], cols_[f"{lab}, as the bot runs it"] = T.SERIES[1], T.SERIES[0]
            _write_fig(figure_equity(d, curves, sym, "8y", labels=labs, colors=cols_), out, f"equity_8y_{sym}_v3lite_engines",
                       f"{sym} · V3-lite and its hybrids on both engines · 8 years",
                       "blue: tick engine, votes read on the forming bar, as the bot reads them; orange: M1 bars, votes on "
                       "closed bars (as pre-registered); grey: tick engine, votes on closed bars (the control)")
        for sym, label in TRADE_CHARTS:
            if ((d["symbol"] == sym) & (d["label"] == label) & (d["window"] == "1y")).any():
                slug = "".join(ch if ch.isalnum() else "_" for ch in label.lower()).strip("_")
                _write_fig(figure_trades(out, curves, sym, label), out, f"trades_1y_{sym}_{slug}",
                           f"{sym} · {label} · every trade of the last year",
                           "H4 candles of the bid; ▲ buy / ▼ sell entry, × exit, the line coloured by the result; "
                           "for our designs the middle run of the eight loop timings (by final equity)", width=1500)
                log(f"  trades chart {sym} {label}")
    return d


def checks(out: Path = OUT, log=print) -> None:
    """The checks the write-up cites, saved as files: the bar runner against the study's published numbers
    (regression_check.csv), the account a risk-sized signal needs for 0.01 lot (signal_sizes.csv), and the changed
    tick engine against the main run (identity_check.csv)."""
    from . import external as X
    from .. import experiments as E
    from ..engine import fast
    out = Path(out)
    sel = load_selection(out / "selection.json")
    ext = pd.read_csv(IMPROVE / "external_strategies.csv", dtype={"period": str})
    reg, sizes = [], []
    for sym in SYMBOLS:
        rows = [r for r in sel["final"][sym] + sel["references"][sym] if r["engine"] == "bars"]
        for hist in (X.EARLIEST, HISTORY_FROM[sym]):
            m = X.load_market(sym, earliest=hist, end=DATA_END)
            sig = X.bot_signals(m)
            v3 = X.v3lite(m, sig)
            built: dict = {}
            for row in rows:
                plan, sizing = _bar_plan(X, m, sig, v3, built, row)
                for per, (a, z) in X.PERIODS.items():
                    a_ix, z_ix = m.ix(a), m.ix(z)
                    res, _, _ = _bar_account(X, m, plan, sizing, a_ix, z_ix)
                    mod = X._run(m, plan, sizing, a_ix, z_ix, X.block_bounds(m, a, z))
                    c = ext[(ext.symbol == sym) & (ext.strategy == row["family"]) & (ext.params == row["params"]) &
                            (ext.variant == row["variant"]) & (ext.period == per)]
                    pub = float(c["final_equity"].iloc[0]) if len(c) else np.nan
                    reg.append(dict(symbol=sym, label=row["label"], history_from=hist, period=per,
                                    runner=round(res.final, 2), simulator=round(mod.final, 2), published=pub,
                                    runner_equals_simulator=bool(abs(res.final - mod.final) < 1e-6 and abs(res.max_dd - mod.max_dd) < 1e-12),
                                    equals_published=bool(abs(res.final - pub) < 0.005)))
                if hist == HISTORY_FROM[sym] and row["variant"] == "risk-sized":
                    for w in ("8y", "1y"):
                        a_s, z_s = _window_s(w)
                        p = X.run_path(m, plan, int(np.searchsorted(m.t, a_s)), int(np.searchsorted(m.t, z_s)))
                        if sizing.mode == "risk":
                            ok = p.risk > 0
                            need = p.risk[ok] * m.k / sizing.rf
                        else:
                            ok = np.isfinite(p.expo) & (p.expo > 0)
                            need = p.epx[ok] * m.k / p.expo[ok]
                        sizes.append(dict(symbol=sym, label=row["label"], window=w, signals=int(len(p)),
                                          median_account_for_001_lot=round(float(np.median(need)), 0),
                                          p25=round(float(np.percentile(need, 25)), 0), p75=round(float(np.percentile(need, 75)), 0),
                                          share_needing_more_than_2000=round(float(np.mean(need > ACCOUNT)) * 100.0, 1)))
            log(f"  checks {sym} history from {hist}")
    pd.DataFrame(reg).to_csv(out / "regression_check.csv", index=False)
    pd.DataFrame(sizes).to_csv(out / "signal_sizes.csv", index=False)
    runs = pd.concat([pd.read_csv(out / f"runs_{s}_ticks.csv") for s in SYMBOLS], ignore_index=True)
    ident = []
    for sym in SYMBOLS:
        a, z = WINDOWS["new"]
        prep = fast.prepare(sym, a, z, ["M1", "M5", "M15", "H1", "H4"], mode="sec")
        for name, ov in own_designs(sym).items():
            s = fast.run(E.live_config(sym, start=a, end=z).replace(**ov), prep).summary()
            old = runs[(runs.symbol == sym) & (runs.label == name) & (runs.window == "new")].iloc[0]
            ident.append(dict(symbol=sym, design=name, window="new", changed_engine=round(float(s["final_equity"]), 2),
                              main_run=float(old["final_equity"]), dd_changed_engine=round(float(s["max_drawdown_pct"]), 2),
                              dd_main_run=float(old["max_dd_pct"]),
                              identical=bool(abs(s["final_equity"] - old["final_equity"]) < 0.005
                                             and abs(round(float(s["max_drawdown_pct"]), 2) - old["max_dd_pct"]) < 0.005)))
        del prep
    pd.DataFrame(ident).to_csv(out / "identity_check.csv", index=False)
    log(f"regression: {sum(r['equals_published'] for r in reg if r['history_from'] == X.EARLIEST)} of "
        f"{sum(1 for r in reg if r['history_from'] == X.EARLIEST)} equal the published figures; identity: "
        f"{sum(r['identical'] for r in ident)} of {len(ident)} identical")


def refine_tick_dd(out: Path = OUT, log=print) -> None:
    """The first tick runs stored drawdowns with two decimals; a value ending in 5 rounds either way when shown with
    one. Those accounts (single-run windows) are run again with the same configuration and keep the engine's own
    three-decimal figure."""
    from .. import experiments as E
    from ..engine import fast
    out = Path(out)
    sel = load_selection(out / "selection.json")
    for sym in SYMBOLS:
        sup = {r["label"]: r for r in supplement_rows(sym, sel)}
        own = {k: dict(label=k, overrides=v) for k, v in own_designs(sym).items()}
        for eng in ("ticks", "supplement"):
            path = out / f"runs_{sym}_{eng}.csv"
            df = pd.read_csv(path)
            amb = df[df["window"].isin(["8y", "5y", "new"]) & (((df["max_dd_pct"] * 100).round().astype(int) % 10) == 5)]
            for w, g in amb.groupby("window"):
                a, z = WINDOWS[w]
                rows = [(sup if eng == "supplement" else own)[lab] for lab in g["label"]]
                tfs = set()
                for r in rows:
                    tfs |= set(E.live_config(sym).replace(**r["overrides"]).timeframes())
                tfs = sorted(tfs | {"M1", "M5", "M15", "H1", "H4"}, key=["M1", "M5", "M15", "M30", "H1", "H4", "D1"].index)
                prep = fast.prepare(sym, a, z, tfs, mode="sec")
                for r in rows:
                    s = fast.run(E.live_config(sym, start=a, end=z).replace(**r["overrides"]), prep,
                                 regime=r.get("_regime")).summary()
                    i = df.index[(df["label"] == r["label"]) & (df["window"] == w)][0]
                    if abs(float(s["final_equity"]) - float(df.at[i, "final_equity"])) > 0.005:
                        raise RuntimeError(f"{sym} {r['label']} {w}: the rerun differs from the stored account")
                    dd = round(float(s["max_drawdown_pct"]), 3)
                    log(f"  {sym} {r['label']} {w}: max DD {df.at[i, 'max_dd_pct']} -> {dd}")
                    df.at[i, "max_dd_pct"] = dd
                    if "dd_median" in df and pd.notna(df.at[i, "dd_median"]) and int(df.at[i, "runs"]) == 1:
                        df.at[i, "dd_median"] = dd
                        df.at[i, "dd_worst"] = dd
                del prep
            df.to_csv(path, index=False)


# the strategies whose last-year trades are drawn on the price chart
TRADE_CHARTS = (("XAUUSDm", "V3-lite"), ("XAUUSDm", "V3-lite + 200-day trend filter, as the bot runs it"),
                ("BTCUSDm", "Turtle + bot votes"), ("BTCUSDm", "Top 3"))


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.final10")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    r = sub.add_parser("run")
    r.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    r.add_argument("--windows", nargs="+", default=list(WINDOWS), choices=list(WINDOWS))
    r.add_argument("--engines", nargs="+", default=["bars", "ticks"], choices=["bars", "ticks"])
    r.add_argument("--cache", default=None, help="directory for the bot's cached bar-level votes")
    r.add_argument("--out", default=str(OUT))
    rp = sub.add_parser("report")
    rp.add_argument("--out", default=str(OUT))
    rp.add_argument("--no-images", action="store_true")
    sp = sub.add_parser("supplement", help="not pre-registered: the V3-lite hybrids on the tick engine")
    sp.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    sp.add_argument("--windows", nargs="+", default=list(WINDOWS), choices=list(WINDOWS))
    sp.add_argument("--out", default=str(OUT))
    sub.add_parser("warm", help="after the results: the published rows' evidence re-run warm, the same rule, new rows run")
    sub.add_parser("checks", help="save the regression, account-size and identity checks the write-up cites")
    a = ap.parse_args(argv)
    if a.cmd == "warm":
        warm_check()
        run_warm_additions()
        return
    if a.cmd == "checks":
        checks()
        return
    if a.cmd == "supplement":
        run_supplement(a.symbols, a.windows, Path(a.out))
        return
    if a.cmd == "report":
        report(Path(a.out), images=not a.no_images)
        return
    if a.cmd == "run":
        run(a.symbols, a.windows, a.engines, Path(a.out), Path(a.cache) if a.cache else None)
        return
    if a.cmd == "select":
        doc = write_selection()
        for sym in SYMBOLS:
            print(f"\n{sym}: {doc['eligible'][sym]} of {doc['pool_size'][sym]} candidates eligible")
            for c in doc["final"][sym]:
                ev = " / ".join(f"{v:+.0f}" for v in c["evidence"].values())
                print(f"  {c['rank']:2d}. {c['label']:42s} {c['engine']:5s} {ev:28s} mean {c['mean_q']:+7.1f}/q  "
                      f"worst DD {c['dd_fresh']:4.1f}%  ratio {c['profit_per_dd']:.2f}")
            print("  references: " + ", ".join(r["label"] for r in doc["references"][sym]))


if __name__ == "__main__":
    main()
