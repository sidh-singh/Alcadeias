
## BTCUSDm search step: interpretations and deviations (each written before any result it could affect)

Written 18 Nov 2026, before the first BTCUSDm study run. PREREG sha256 checked OK. The runner is `ladder_study.py`
unchanged; at most 4 workers (another agent runs XAUUSDm at the same time).

B1. **R1 promotion.** Promoted = the top third by score (ceil(n/3)) of the stage's pairs, plus every pair with 0 wipes and
    mean return > 0; if that is more than half of the stage, only the best floor(n/2) by score go. The references
    (L0, L5, LB, V3L, V3) are carried to R2 and R3 whatever their score (PREREG §7 step 3); they sit outside the cap.
B2. **"Best TRIG-MACD / TRIG-3RD level from A"** (stage O) = the level with the best R2 score among that dimension's
    stage-A designs on the stage-O bases L0 and LB; if none of them reached R2, the best R1 score.
B3. **Dimension importance** (stage B). The lexicographic score is made scalar as S = Q − 1000 × wiped (so key 1 still
    dominates). Gain of a dimension on a base = the best S among its levels that reached R2 minus the base's R2 S. The
    average is over the bases where at least one level reached R2; a dimension with no level at R2 anywhere is not eligible.
    "The 2 bases with the best single-change R2 score" = the bases whose best stage-A single-change design has the best R2
    score. The "best 3 levels" of a dimension (the base value '=' counts as a level with gain 0) are ranked by their mean
    S gain over the 2 chosen bases, using the bases where the level reached R2; if fewer than 3 have R2 values, the rest
    are filled by R1 score gain. The plan is written to `stageB_plan_BTCUSDm.json` before stage B runs.
B4. **Stage C** takes the 10 best non-reference pairs by R2 score over stages A, O and B together.
B5. **R3** takes the at most 120 best pairs by R2 score over stages A, O, B and C (plus the references outside the cap).
    The per-unit run (§5.4 trial dispersion) is run for every R3 pair.
B6. **R4.** F1-F3 run for the pool and the references; the WF1 / WF2 / WF3 picks are written to `picks_BTCUSDm.json`
    before their test folds are read. F4 is then run for the WF3 pick, the references, and the 5 best pool members by R3
    score (needed for the cost stress of §3.3); spread × 1.5 (and × 2.0 for information) on the test folds of the picks
    and of those 5. Cross-asset: the BTC WF3 pick also runs on XAUUSDm F4; the gold pick on BTC F4 if the gold step has
    written it by the time this step ends, otherwise that half is left to the gold step / final report.
B7. **Files.** Stage CSVs in the scratch folder `port_tmp/ladder/btc/`; every row of every run is collected into
    `search_BTCUSDm.csv` at the end, with the stage and rung columns (the multiple-testing count).

B8. **R2 reuses the R1 rows.** The 11 R1 quarters (8 regular + 3 stress) are all among the 24 R2 quarters, and a run is
    deterministic given (design, window, seed). The R2 file of each stage is seeded with the R1 rows of its promoted
    pairs and the runner (resumable) runs only the 13 missing quarters. Results are identical; machine time is saved.
B9. **Stage-B base choice: a bug in my helper, fixed before any stage-B result.** The first stage-B plan picked the bases
    L0 and L5 because my helper took each base's first single-change design in table order instead of in R2-score
    order (B3 says: the bases whose best single-change design has the best R2 score). The run was stopped during its
    first R1 window; no stage-B row had been written. The helper now keeps the score order, the unused stage-B
    designs were removed from the registry, and the plan was recomputed and rewritten. The importance ranking (which
    does not depend on the bases) was unchanged by the fix.
B10. **Account-quarters (S4)** are read from each 12-month account's equity (floating included, recorded hourly) at
    the 3-, 6-, 9- and 12-month marks; a quarter after a wipe counts as not positive. Coded in `r4.py` before any
    R4 run (it needs the equity series, so R4 runs with hourly recording; checked bit-identical to the light runs on
    3 designs). Logged here late, at the end of the step; it changed no rule.
B11. **Gold pick on BTC (cross-asset).** The gold step had not written `picks_XAUUSDm.json` when this step ended, so the
    gold WF3 pick on BTCUSDm F4 is left to the gold step (its X6 runs it). The BTC WF3 pick was run on XAUUSDm F4.

## XAUUSDm search step: interpretations and deviations (each written before any result it could affect)

Written 18 Nov 2026, after stage-A R1 was launched and before any XAUUSDm study result was read. PREREG sha256 checked
OK. Runner: `ladder_study.py` unchanged, driven by a thin wrapper (`port_tmp/ladder/xau/run_rung.py`); at most 4 workers.
Stage-A design list regenerated from the runner and found identical to the build's (448 designs, 45 skips).

X1-X5. **The same interpretations as B1-B5 above** (R1 promotion with the references outside the cap; best TRIG-MACD /
    TRIG-3RD level for stage O; dimension importance with S = Q − 1000 × wiped; stage-C parents; R3 = 120 best by R2
    score plus the references, per-unit run for every R3 pair), so that both symbols are judged by one rule.
    Added for gold: if two of the 4 most important dimensions write the same setting (TIERS and GRAN both set the tier
    list; TRIG-MACD and TRIG-3RD both set the trigger), the lower-ranked one is replaced by the next dimension, because
    a factorial of the two would only overwrite one with the other. The plan goes to `stageB_plan_XAUUSDm.json`.
X6. **R4 (as pre-registered, not cut).** F1-F3 run for the pool and the references; the WF1 / WF2 / WF3 picks are written
    to `picks_XAUUSDm.json` before their test folds are read (F2 and F3 are also training folds of the later splits, so
    the order is: F1 → write WF1 → F2 → write WF2 → F3 → write WF3 → F4). F4 is run for the whole pool and the
    references after the WF3 pick is written. If machine time runs short, F4 is cut to the WF3 pick, the references and
    the 5 best pool members by R3 score (as B6), and the cut is logged here. Spread × 1.5 on the test folds of the 3 picks
    and of the 5 best pool members; × 2.0 for information on the picks' test folds only. Cross-asset: the gold WF3 pick
    is run on BTCUSDm F4 (96 accounts) in this step.
X7. **Continuous accounts, no-ladder twins, anchor view.** 8y / 5y per second and last year (8 timings, ticks) for the
    picks, the references and the 5 best pool members; no-ladder twins (`max_adds=0`) of the picks on their test folds;
    the 184-run anchor view for the picks, L5 and the references.
X8. **Stage D** on F4 with the R3 protocol = the 5 one-year accounts starting 2024-11-13, 2025-02-13, 2025-05-13,
    2025-08-13, 2025-11-13 (the last ends 2026-11-13) × seeds 1, 2, for the best stage-A level (by R2 score, else R1) of
    every dimension around L0 and around LB, plus L0 and LB themselves on the same windows for comparison.
X9. **Files.** Raw rows per stage and rung in `backtest_results/ladder/runs_XAUUSDm/`; all rows collected into
    `search_XAUUSDm.csv` at the end with stage and rung columns (the multiple-testing count).
X10. **Duplicates across stages.** A stage-O, B or C design whose effective configuration (`ladder_study.canonical`)
    equals one already run in an earlier stage is not run again: it takes the earlier design's name and rows, and its
    own label is kept as an alias. It still belongs to the later stage's population for that stage's R1 promotion
    (and is run at R2 if promoted there and not yet run). N (§5.4) counts distinct configurations that reached R1.
X11. **R2 reuses the R1 rows.** The 11 R1 quarters are all on the R2 grid of 24 quarters, and a run is deterministic in
    (design, window, seed). So R2 runs only the 13 other quarters, and the R2 score reads the R1 rows plus these.
    Speed measured on the first R1 window: 4.5 s a tick quarter per worker with both symbols' 8 workers on the 8 cores
    (against 1.4 s alone), so the whole funnel is expected to need ≈ 35 h of wall time for gold.

## XAUUSDm finish step (19 Nov 2026, after the first workflow was cut off by a usage limit)

PREREG sha256 checked OK at the start. Every stage (A, O, B, C, R3, per-unit, pool, R4 F1-F4 with the picks written
before their test folds, twins, spread × 1.5 / × 2.0, continuous 8y / 5y / 1y, cross-asset, per-unit F4, stage D,
anchor) had finished by 04:29 IST. `final_eval.py` was checked against PREREG §5.1-5.4 and re-run: its output
`final_eval.json` is byte-identical to the one written at 04:30. Up to 8 workers from here on (no other job runs).

X12. **Stage D, two levels (logged after the stage-D rows were read; it affects only 2 rows of an information table).**
    Chain3 ran the stage-D plan `stageD_plan.json` with LB:ENTRY = E8 and LB:CONFIRM = C10, which are the best *R1* levels.
    But E10 and C7 have full R2 scores, and X8 says to use the R2 score first. The cut-off session had already written
    the corrected `stageD_plan_v2.json` (04:31). I recomputed it and it matches the rule. The old helper version is
    not on disk, so I cannot reconstruct the cause. The 2 missing designs (LB|ENTRY=E10, LB|CONFIRM=C7: 20 runs) were
    run on 19 Nov, and `stageD_table_v2.csv` replaces `stageD_table.csv`. The E8 / C10 rows are kept.
    - The stage-O choice uses the same helper, so I rechecked it on the stage-A R2 rows: it is unchanged. TRIG-MACD had
      no level at R2 on L0 / LB, so the R1 fallback gives M3. TRIG-3RD by R2 gives X-emadist.
X13. **Stage-B plan scored on the 13 R2-only quarters (found in this step).** `funnel.stage_b_plan` reads
    `rows("R2")`, which holds only the 13 quarters that X11 adds. X3 / X11 define the R2 score as R1 + R2 (24 quarters,
    48 rows). The saved `stageB_plan_XAUUSDm.json` is reproduced exactly by the R2-only reading. The R1 + R2 reading
    gives the same bases (V3L, LB) but a different plan: dimensions LEVEL, GAP, ENTRY, CONFIRM instead of GAP, LEVEL,
    CONFIRM, GATE, with levels LEVEL {LV20, LV30, LV25}, GAP {G2, GD1, =}, ENTRY {E10, E3, E8}, CONFIRM {C10, C1, C4}.
    - Every later step used the full R1 + R2 score: promotion, stage-C parents, the R3 list.
    - Rerunning B → C → R3 → R4 would take most of a day. So this rule was fixed before any result of it was read:
      1. **Shadow stage B:** the corrected factorial runs through R1 and R2. Designs are registered as stage "Bfix",
         duplicates take earlier names (X10), and the rows go to `runs_XAUUSDm/stageB_fix/`.
      2. Any shadow design whose R2 score beats the 10th stage-C parent (S = 0.275) gets its stage-C neighbours run
         through R1 / R2 as well.
      3. Any shadow design (or neighbour) whose R2 score beats the 120th R3 entry (S = 0.115) runs at R3.
      4. Any whose R3 score beats the 15th pool member (Q = 0.629) runs R4 F1-F3, and the WF pick rule is re-applied as
         a shadow.
    - The written picks stand. They were fixed before their test folds were read, and a shadow cannot be blind to F4.
    - N (§5.4) counts the shadow designs too.
X14. **`search_XAUUSDm.csv`** has the same columns as `search_BTCUSDm.csv`, plus `q_pnl`, the dollar P/L per account
    quarter (r4run). `q_ret` is derived from it, starting at $2,000. The no-ladder twins carry `variant` = `@noladder`
    (`#noladder` in the raw files). The cross-asset rows carry `symbol` = BTCUSDm. `reused_R1_row` is empty, because
    X11 never copied R1 rows into R2 files.
X15. **The no-ladder twin under Z1 is not the same size (a remark, not a rule change).** With `max_adds=0`, the
    pre-funded unit puts the whole 30% risk budget on one position, so the twin's unit is larger than the pick's
    first position. The pre-registered S8 test (`max_adds=0` on the same design) is applied as written, and this is
    reported next to it.
X13 outcome (written after the shadow ran):
- **The corrected factorial is LB-only:** 324 designs. No LEVEL level is "=", and LEVEL does not apply to V3L, so no
  V3L combination was built.
- **R1:** all 324 had 0 wipes, and none had a positive mean. The best mean was −2.0% a quarter.
- **R2:** 108 were promoted. The best scored Q −0.145.
- **None beat a later cut**, so the cascade stopped after R2 (9,936 runs, 56 min).
- N for §5.4 is now 1,493. `final_eval.json` is recomputed with it (DSR 0.0079). The as-run copy is
  `final_eval_asrun_N1169.json` (DSR 0.0098).

## Stress step (19 Nov 2026): interpretations, written before any stress run

PREREG sha256 checked OK at the start. Up to 8 workers (gold and BTC chains, 4 each). Scripts in the scratch folder
`port_tmp/ladder/stress/`; rows in `backtest_results/ladder/stress/`.

T1. **Designs.** Top 5 per symbol = the first 5 pool members by R3 score (the pool order; it equals the R3 Q order).
    For comparison: L0 (live v3.9.2), L5 (slot 5), and the two references the search reports point to, V3 (no ladder) and
    V3L (one add, the bot's unit rule). 9 designs per symbol.
T2. **Every fresh 12-month start** = the 13th of each month from 2018-11-13 to 2025-11-13 (85 starts). 48 are the R4 fold
    accounts (8 timings, reused) and 2025-11-13 is the last-year account (8 timings, reused where it exists). The 36 gap
    starts (Nov-Oct of 2019-20, 2021-22, 2023-24) run now in ticks mode with timings 1 and 2 only, to save machine time;
    the 8-timing check is read on the 48 fold starts.
T3. **Cost × 1.5** on the 29 quarterly starts (every third month from 2018-11-13), timing 1. Existing × 1.5 rows with the
    same window and timing are reused.
T4. **Step-up sizing.** Base $2,500 (reused). Aggressive $1,500, cautious $5,000, on the 29 quarterly starts, timing 1.
    Designs whose unit does not use the step get the equivalent scaling of their own knob: Z1 `pf_risk` 0.50 / 0.15
    (base 0.30); Z2 `vt_k` × 5/3 / × 1/2; Z3 (`fixed_units` 1) aggressive `fixed_units` 2, cautious not possible (already
    the minimum lot).
T5. **Worst events**, chosen from the D1 data (largest falls, 2018-11 to 2026-11), each a fresh $2,000 account from about
    10 days before to 3-4 weeks after, 8 timings, ticks:
    gold: 2020-02-28→03-31 (COVID, 5-day −10%), 2020-08-01→09-01 (08-11 −5.9%), 2025-10-10→11-10 (10-21 −6.1%),
    2026-01-20→02-20 (01-30 −10.1%, 02-02 a 10% range, 02-05 −6.2%), 2026-03-06→04-06 (5-day −11%);
    BTC: 2020-03-01→04-01 (03-12 −38.8%), 2021-05-09→06-09 (05-19 −14.3%), 2022-05-01→07-01 (LUNA, Celsius 06-13
    −15.5%), 2022-11-01→12-01 (FTX 11-09 −14.2%), 2026-01-25→02-25 (02-05 −14.0%). BTC's 2021-22 bear is also the
    12-month start 2021-11-13 of T2.
T6. **Cross-asset**: each top-5 design on the other symbol's F4 (96 accounts), rebuilt with `ST.build` for the target
    symbol (Z2's `vt_k` recomputed), as B6 / X6. The two WF3 picks' runs exist and are reused.
T7. **Pass test for each top-5 design** (S1-S9 on F4, for information; F4 was not read by the R3 ranking that defines the
    top 5). The verdict stays the walk-forward one (PREREG §5.2). Missing pieces run now: no-ladder twins on F4 (96),
    per-unit F4 runs (for DSR) where missing, continuous 8y / 5y / 1y for BTC #1-#3. DSR uses each symbol's N and
    Var[SR] as in the search steps (gold N 1,493, BTC N 1,168).
T8. **Profit per week per $2,000 bot** = the median (and 10th percentile) 12-month dollar result over all starts and
    timings, divided by 52.18. It is not compounded further.
T9. **Outcome notes (written after the runs).** The BTC search file names its variant rows with the suffix in `design`
    (`…@noladder`, `…@spread1.5`), which my reuse check did not strip. So 96 twin rows (B5) and 20 × 1.5 rows (F4, seed 1)
    were run again. All 116 equal the search rows to the cent and the basket count, so they serve as a determinism check.
    The analysis (`stress/analyze.py`) strips the suffix. Machine time: 11:38-13:42 IST (2 h 04 min), 8 workers, about
    4,900 account runs. PREREG sha256 checked OK at the end; `git diff` of tracked files is empty.
