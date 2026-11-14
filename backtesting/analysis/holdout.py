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


def merged_timeframes(out: Path, sym: str) -> Optional[pd.DataFrame]:
    a, b = Path(out) / "sweeps" / f"{sym}_timeframes.csv", Path(out) / "sweeps" / f"{sym}_timeframes_holdout.csv"
    if not (a.exists() and b.exists()):
        return None
    m = pd.read_csv(a).merge(pd.read_csv(b), on=KEY)
    net_a = [f"net_profit@{w}" for w in ANALYSED]
    dip_a = [f"max_loss_from_start@{w}" for w in ANALYSED]
    net_h = [f"net_profit@{w}" for w in HELD_OUT]
    dip_h = [f"max_loss_from_start@{w}" for w in HELD_OUT]
    m["a_pos"] = (m[net_a] > 0).sum(axis=1)
    m["a_ruin"] = (m[dip_a] >= ACCOUNT).sum(axis=1)
    m["a_total"] = m[net_a].sum(axis=1)
    m["a_worst"] = m[net_a].min(axis=1)
    m["h_pos"] = (m[net_h] > 0).sum(axis=1)
    m["h_ruin"] = (m[dip_h] >= ACCOUNT).sum(axis=1)
    m["h_total"] = m[net_h].sum(axis=1)
    return m


def _group(m: pd.DataFrame) -> pd.Series:
    g = np.where((m["a_pos"] == 3) & (m["a_ruin"] == 0), "3 of 3 profitable, never $2,000 down",
        np.where(m["a_pos"] == 3, "3 of 3 profitable, but $2,000 down at some point",
        np.where(m["a_pos"] == 2, "2 of 3 profitable",
        np.where(m["a_pos"] == 1, "1 of 3 profitable", "0 of 3 profitable"))))
    return pd.Series(g, index=m.index)


GROUP_ORDER = ["3 of 3 profitable, never $2,000 down", "3 of 3 profitable, but $2,000 down at some point",
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
    df["deepest_dip"] = df[[f"max_loss_from_start@{w}" for w in an + ho]].max(axis=1)
    df["worst_basket"] = df[[f"largest_loss@{w}" for w in an + ho]].min(axis=1)
    df["baskets_per_quarter"] = df[[f"baskets@{w}" for w in an + ho]].mean(axis=1)
    pa = Path(out) / "candidates" / f"{sym}_account.csv"
    if pa.exists():
        a = pd.read_csv(pa)[["candidate", "net_profit", "max_dd_pct", "stopped_out", "max_lots"]]
        a.columns = ["candidate", "account_net", "account_max_dd_pct", "account_stopped_out", "account_max_lots"]
        df = df.merge(a, on="candidate", how="left")
    return df
