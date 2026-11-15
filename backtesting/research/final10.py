"""
The final ten: every design and published strategy tested so far, narrowed to ten per symbol by one fixed rule, then
run for eight years (Nov 2018 - Nov 2026), five years and the last year on fresh $2,000 accounts.

    python -m backtesting.research.final10 select            the pre-registered lists (backtest_results/final10/selection.json)
    python -m backtesting.research.final10 run [--symbols ..] the runs (CSV files in backtest_results/final10/)
    python -m backtesting.research.final10 report            FINAL10.md tables and the charts

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


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.final10")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    a = ap.parse_args(argv)
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
