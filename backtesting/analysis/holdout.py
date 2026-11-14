"""
Hold-out evaluation: does a choice made on the analysed windows carry over?

Two tables are built here, both from files the experiment pipeline writes:

``timeframe_carry_over``  groups every timeframe setting by how it did on the three
                          analysed quarters, then reports how each group did on the two
                          hold-out quarters that played no part in the grouping.
``candidate_table``       the short list of candidate settings on all five quarters and on
                          a real $2,000 account over the whole period.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ACCOUNT = 2000.0
ANALYSED = ["IS", "OOS1", "OOS2"]
HELD_OUT = ["HO2", "HO1"]
KEY = ["open", "fc", "entry", "fc_level"]
SHORT = {"IS": "Aug-Nov 2026", "OOS1": "May-Aug 2026", "OOS2": "Feb-May 2026",
         "HO2": "Nov 2025-Feb 2026", "HO1": "Aug-Nov 2025"}


def wiped(df: pd.DataFrame, w: str) -> pd.Series:
    """
    Would a real $2,000 account have been wiped in window ``w``?  Read from the account replay
    (``acct_wiped@w``: the run's baskets re-sized by the bot's own unit rule, see
    ``metrics.replay_account``). Results written before that column existed fall back to the
    cruder test "more than $2,000 below the start at one fixed unit", which misses wipe-outs
    that only happen because the account had stepped its unit up.
    """
    c = f"acct_wiped@{w}"
    if c in df.columns:
        return df[c].astype(bool)
    return df[f"max_loss_from_start@{w}"] >= ACCOUNT


def dip(df: pd.DataFrame, w: str) -> pd.Series:
    """Deepest the replayed $2,000 account stood below its start in window ``w`` (at most 2,000)."""
    c = f"acct_dip@{w}"
    return df[c] if c in df.columns else df[f"max_loss_from_start@{w}"].clip(upper=ACCOUNT)


def merged_timeframes(out: Path, sym: str) -> Optional[pd.DataFrame]:
    a, b = Path(out) / "sweeps" / f"{sym}_timeframes.csv", Path(out) / "sweeps" / f"{sym}_timeframes_holdout.csv"
    if not (a.exists() and b.exists()):
        return None
    m = pd.read_csv(a).merge(pd.read_csv(b), on=KEY)
    net_a = [f"net_profit@{w}" for w in ANALYSED]
    net_h = [f"net_profit@{w}" for w in HELD_OUT]
    m["a_pos"] = (m[net_a] > 0).sum(axis=1)
    m["a_ruin"] = sum(wiped(m, w).astype(int) for w in ANALYSED)
    m["a_total"] = m[net_a].sum(axis=1)
    m["a_worst"] = m[net_a].min(axis=1)
    m["h_pos"] = (m[net_h] > 0).sum(axis=1)
    m["h_ruin"] = sum(wiped(m, w).astype(int) for w in HELD_OUT)
    m["h_total"] = m[net_h].sum(axis=1)
    return m


def _group(m: pd.DataFrame) -> pd.Series:
    g = np.where((m["a_pos"] == 3) & (m["a_ruin"] == 0), "3 of 3 profitable, account never wiped",
        np.where(m["a_pos"] == 3, "3 of 3 profitable, but the account wiped in at least one",
        np.where(m["a_pos"] == 2, "2 of 3 profitable",
        np.where(m["a_pos"] == 1, "1 of 3 profitable", "0 of 3 profitable"))))
    return pd.Series(g, index=m.index)


GROUP_ORDER = ["3 of 3 profitable, account never wiped", "3 of 3 profitable, but the account wiped in at least one",
               "2 of 3 profitable", "1 of 3 profitable", "0 of 3 profitable"]


def timeframe_carry_over(out: Path, sym: str) -> Optional[Tuple[pd.DataFrame, Dict[str, float]]]:
    """(table by group, facts) -- facts hold the base rate over all settings and the rank correlation."""
    m = merged_timeframes(out, sym)
    if m is None:
        return None
    m = m.assign(group=_group(m))
    rows = []
    for g in GROUP_ORDER:
        x = m[m["group"] == g]
        if len(x) == 0:
            continue
        rows.append({"group": g, "settings": int(len(x)),
                     "both_holdout_profitable_pct": float((x["h_pos"] == 2).mean() * 100),
                     "one_or_more_pct": float((x["h_pos"] >= 1).mean() * 100),
                     "wiped_in_holdout_pct": float((x["h_ruin"] > 0).mean() * 100),
                     "mean_holdout_net_per_quarter": float(x["h_total"].mean() / len(HELD_OUT)),
                     "median_holdout_net_per_quarter": float(x["h_total"].median() / len(HELD_OUT))})
    ra, rh = m["a_total"].rank(), m["h_total"].rank()
    facts = {
        "settings": int(len(m)),
        "base_both_profitable_pct": float((m["h_pos"] == 2).mean() * 100),
        "base_wiped_pct": float((m["h_ruin"] > 0).mean() * 100),
        "base_mean_net_per_quarter": float(m["h_total"].mean() / len(HELD_OUT)),
        "rank_correlation": float(np.corrcoef(ra, rh)[0, 1]),
    }
    return pd.DataFrame(rows), facts


def best_survivors(out: Path, sym: str, n: int = 8) -> Optional[pd.DataFrame]:
    """Settings ranked on the analysed windows only (as one would have chosen them), with their hold-out result."""
    m = merged_timeframes(out, sym)
    if m is None:
        return None
    return m.sort_values(["a_ruin", "a_pos", "a_worst"], ascending=[True, False, False]).head(n)


def candidate_table(out: Path, sym: str) -> Optional[pd.DataFrame]:
    p = Path(out) / "candidates" / f"{sym}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    wins = [c.split("@")[1] for c in df.columns if c.startswith("net_profit@")]
    an = [w for w in ANALYSED if w in wins]
    ho = [w for w in HELD_OUT if w in wins]
    df["analysed_total"] = df[[f"net_profit@{w}" for w in an]].sum(axis=1)
    df["holdout_total"] = df[[f"net_profit@{w}" for w in ho]].sum(axis=1) if ho else np.nan
    df["quarters_profitable"] = (df[[f"net_profit@{w}" for w in an + ho]] > 0).sum(axis=1)
    df["quarters"] = len(an + ho)
    df["deepest_dip"] = pd.concat([dip(df, w) for w in an + ho], axis=1).max(axis=1)
    df["wiped_quarters"] = sum(wiped(df, w).astype(int) for w in an + ho)
    df["worst_basket"] = df[[f"largest_loss@{w}" for w in an + ho]].min(axis=1)
    df["baskets_per_quarter"] = df[[f"baskets@{w}" for w in an + ho]].mean(axis=1)
    pa = Path(out) / "candidates" / f"{sym}_account.csv"
    if pa.exists():
        a = pd.read_csv(pa)[["candidate", "net_profit", "max_dd_pct", "stopped_out", "max_lots"]]
        a.columns = ["candidate", "account_net", "account_max_dd_pct", "account_stopped_out", "account_max_lots"]
        df = df.merge(a, on="candidate", how="left")
    ens = candidate_ensemble(out, sym)
    if ens is not None:
        df = df.merge(ens, on="candidate", how="left")
    return df


def candidate_ensemble(out: Path, sym: str) -> Optional[pd.DataFrame]:
    """
    Per candidate, from ``candidates/<sym>_timing.csv`` (every quarter x eight loop timings on a fresh
    $2,000 with the unit auto-step): the spread over all quarter-runs and the median per quarter.
    """
    p = Path(out) / "candidates" / f"{sym}_timing.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p)
    t["stopped_out"] = t["stopped_out"].astype(bool)
    rows = []
    for cand, g in t.groupby("candidate", sort=False):
        r = {"candidate": cand, "ens_runs": int(len(g)),
             "ens_median": float(g["net_profit"].median()), "ens_mean": float(g["net_profit"].mean()),
             "ens_losing_runs": int((g["net_profit"] < 0).sum()), "ens_stopped_runs": int(g["stopped_out"].sum()),
             "ens_worst_run": float(g["net_profit"].min()), "ens_best_run": float(g["net_profit"].max()),
             "ens_worst_basket": float(g["largest_loss"].min()), "ens_max_lots": float(g["max_lots"].max()),
             "ens_baskets_per_quarter": float(g["baskets"].mean())}
        for w, gw in g.groupby("window", sort=False):
            r[f"ens_median@{w}"] = float(gw["net_profit"].median())
            r[f"ens_min@{w}"] = float(gw["net_profit"].min())
            r[f"ens_max@{w}"] = float(gw["net_profit"].max())
            r[f"ens_losing@{w}"] = int((gw["net_profit"] < 0).sum())
            r[f"ens_stopped@{w}"] = int(gw["stopped_out"].sum())
            r[f"ens_n@{w}"] = int(len(gw))
        rows.append(r)
    return pd.DataFrame(rows)
