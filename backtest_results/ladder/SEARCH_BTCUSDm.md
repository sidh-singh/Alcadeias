# SEARCH_BTCUSDm: the pre-registered ladder search on BTCUSDm

Step "search BTCUSDm", 18 Nov 2026, branch `backtest_hedging`. Nothing was committed. `PREREG_LADDER.md` sha256 was checked
with `shasum -c` at the start and at the end: OK. `git diff` of tracked files is empty. Raw rows of every run are in
`search_BTCUSDm.csv`, and the picks are in `picks_BTCUSDm.json`, written before their test folds were read. Interpretations
and deviations are B1-B11 in `DEVIATIONS.md`. Each was written before any result it could affect, except B10, which is
noted as late.

## Verdict (PREREG §5.2): **SURVIVES, DOES NOT EARN**. No DCA ladder works on BTCUSDm.

- **Every multi-add ladder failed.** Ladders built on the live bot (L0), the slot-5 variant (L5) and the bounded live
  ladder (LB) were 785 designs, covering the owner's points 1-9, the entry and exit questions, and the brainstorm.
  - None of the 785 had a positive mean return over the 22 R1 quarters.
  - None reached R3: all 120 R3 places went to variants of V3-lite with one add (V3L).
  - The live bot wiped **288 of 288** one-year accounts in F1-F3 and **95 of 96** in F4. The slot-5 variant wiped
    275 of 288 and 96 of 96.
- **What survives is not a DCA ladder.** It is the V3-lite frame with a single add. That frame has H1 votes, an H1 trend
  filter, a stop at 8 volatility units, a target at 10, force-close off and a 4 h pause after a loss.
- **The walk-forward pick** was `V3L|CONFIRM=C11|TIERS=T11|SIZE=plus1|SIZING=Z2`: V3-lite, new baskets only in the
  direction of the D1 MACD trend, one add of 2 units on an H4 MACD turn at least 1 volatility unit away, and a
  volatility-targeted unit.
  - It never wiped an account.
  - It made only +2 to +4% a year in F2-F3, and lost 3.2% a year on F4 (the clean fold).
  - Its one add **hurt** on F4: −3.23% against +1.03% for the same design with no add.
  - It fails S3, S4, S5, S6 (WF3), S8 (WF3) and S9.
- **A no-ladder reference did better.** V3-lite with no ladder (ref V3) made +18.7% a year on F4 and +$914 over the
  8-year account, more than any ladder pick.

## 1. What ran

| Stage | Pairs at R1 | To R2 | Notes |
|---|---|---|---|
| A: one dimension at a time around L0, L5, LB, V3L, plus the 4 bases and ref V3 | 448 | 153 (incl. 5 refs) | 45 skips, as built |
| O: the owner's grid. SIZE × tiers {T0, T1, T3, T5, T6, T12, T13} × trigger {RSI, M1, X-rsicross} on L0 and LB | 132 (111 new, 21 = stage-A designs) | 44 | best TRIG-MACD = M1 and best TRIG-3RD = X-rsicross, both taken from LB at R2 (B2) |
| B: factorial `stageB_plan_BTCUSDm.json` | 378 | 126 | importance LEVEL > CONFIRM > ENTRY > TIERS; bases V3L and L5; levels LEVEL {=, LV20, LV25}, CONFIRM {C8, C11, C9}, ENTRY {E6, E1, =}, TIERS {T11, T7, T4}, × 4 sizes |
| C: 30 neighbours of the 10 best R2 pairs | 231 | 77 | all 10 parents were V3L designs |
| **Total** | **N = 1,168 pairs** (budget 3,500) | 400 promotions, 395 pairs at R2 | |
| R3: 120 best by R2, plus 5 refs | 125 × 42 one-year accounts, plus the per-unit F1-F3 run | | all 120 were V3L-based |
| R4: pool of 15 + 5 refs on F1-F3 (96 accounts per fold) | 5,760 accounts | | then picks; F4 for the pick, the refs and the 5 best pool members; spread × 1.5 / × 2.0; no-ladder twins; 8y / 5y / 1y; 184 anchor; per-unit F4; cross-asset |
| D: best level of every dimension around L0 and LB, on F4 (5 one-year accounts × 2 seeds) | 40 designs | | |

- **Runs:** 51,173 account runs were executed. R2 also reused 8,690 identical R1 rows (B8).
- **Machine time:** 20.4 h of wall time on 4 workers, sharing 8 cores with the gold step. Per step: R1+R2 8.0 h, R3
  4.8 h plus 0.8 h per-unit, R4 6.9 h.
- **No cuts were needed.**
- **One helper bug was fixed before any stage-B row existed.** It had picked the wrong stage-B bases (B9).

## 2. Survival: the honest picture (fresh $2,000 accounts, bot sizing, ticks, live loop timing)

| Family | R1: pairs with 0 wipes in 22 quarters | R1: pairs with mean > 0 | Share of R1 quarter accounts wiped | F1-F3 one-year accounts wiped (R4, 288) | F4 (96) | 8y / 5y / last year (8) |
|---|---|---|---|---|---|---|
| L0 live v3.9.2 (191 designs) | 4 | **0** | 35.3% | **288** | **95**, mean −99.5% | wiped / wiped / 8 of 8 wiped |
| L5 slot-5 (441) | 199 | **0** | 15.9% | 275 | 96, −100% | wiped / wiped / 8 of 8 wiped |
| LB bounded live (153) | 151 | **0** | 0.1% | 38 | 0, −7.1%, DD 30% | wiped / wiped / +$48, 0 of 8 |
| V3L one add (382) | 382 | 98 | 0 | 0 | 0, +14.2%, DD 22% | −$166 (DD 49.6%) / −$19 / +$62 |
| ref V3, no ladder | 1 | 1 | 0 | 0 | 0, **+18.7%**, DD 18.5% | **+$914** (DD 18.3%) / +$898 / +$191 |

- **Old anchor view (184 runs, today's store, PREREG wipe rule of equity ≤ $200):**
  - live L0: mean −$1,470, 174 lost, 105 wiped. The engine's stop-out alone gives 96 wiped, as in BUILD note 1.
  - L5: −$1,295, **184 of 184 lost**, 75 wiped.
  - LB: −$192, 162 lost, 0 wiped.
  - V3L: +$2.6, 95 lost. V3: +$39.6, 80 lost.
  - Picks: WF1 +$13.9 (106 lost); WF2 / WF3 +$19.3 (92 lost).
- **Per unit, F1-F3, 6 years:** L0 −$51,027; L5 −$33,333; LB −$4,867; V3L −$433; V3 +$297; WF3 pick +$452.
  On F4: L0 −$11,797; L5 −$7,532; LB −$365; V3L +$266; V3 +$443; WF3 pick +$111.

## 3. Walk-forward picks and the pass test (PREREG §5.1)

| Split | Pick (written before the test fold) | Train: wiped, min Q |
|---|---|---|
| WF1 (F1 → F2) | `V3L|CONFIRM=C11|TIERS=T11|SIZE=flat|GATE=GT5|SIZING=Z2` (WF2's pick, plus no adds while ADX(14,H1) > 30, flat add) | 0, 0.654 |
| WF2 (F1-F2 → F3) | `V3L|CONFIRM=C11|TIERS=T11|SIZE=plus1|SIZING=Z2` | 0, 0.231 |
| WF3 (F1-F3 → F4) | the same as WF2 | 0, 0.231 |

The WF3 pick's full settings are in `picks_BTCUSDm.json`:
- **Entries and sizing:** H1 votes (`entry_s` 2, no agreement), trend filters H1 MACD signal and D1 MACD signal,
  vol-target unit k = 0.490.
- **The add:** one add (`max_adds` 1), 2 × unit, on an H4 MACD turn at least 1 H1 volatility unit (24 bars) from the
  last fill.
- **Exits:** stop at 8 volatility units, target at 10, force-close off, 4 h pause after a loss.

| Test (96 accounts) | S1 wiped ×1 / ×1.5 | S2 worst DD | S3 mean / median / mean ×1.5 | S4 quarters > 0 | S5 median r/DD (×1.5) | S6 timings > 0 | S7 8y / 5y / 1y | S8 adds; vs twin | S9 DSR |
|---|---|---|---|---|---|---|---|---|---|
| WF1 on F2 | **0 / 0** | **10.3%** | +2.02 / +2.49 / **−1.98** ✗ | **60.4%** | 0.28 ✗ (−0.15) | **8** | **+$736 DD 13.9 / +$281 DD 16.4 / 0 of 8** | **11.2%; +2.02 vs +1.55** | - |
| WF2 on F3 | **0 / 0** | **12.8%** | **+3.83 / +3.61 / +0.81** | 54.2% ✗ | **0.51** (0.03 ✗) | **8** | **+$858 DD 12.4 / +$402 DD 14.6 / 0 of 8** | **14.0%; +3.83 vs +2.18** | - |
| WF3 on F4 | **0 / 0** | **17.8%** | −3.23 / −3.50 / −4.92 ✗ | 55.5% ✗ | −0.26 ✗ (−0.33) | 0 ✗ | **as WF2** | 15.8%; **−3.23 vs +1.03** ✗ | **≈ 0** ✗ |

- **Spread × 2.0, for information:** −9.09% (F2), +0.22% (F3), −5.26% (F4).
- **Comfortable columns:** only S2, S6 (WF1, WF2) and S7 are met.
- **Haircut (§5.4):**
  - SR̂ = 0.0098 a day (T = 726 trading days, skew 0.75, kurtosis 8.3).
  - Var[SR] = 0.0040 over the 125 R3 per-unit runs (the L0, L5 and LB references dominate it). N = 1,168.
  - SR₀ = 0.209, so **DSR ≈ 4 × 10⁻⁸**. With N + 1,200: 5 × 10⁻⁹.
  - With only the V3 / V3L runs' dispersion, SR₀ would still be 0.040, four times SR̂.
- **Selection inflation:**
  - Per unit: F1-F3 +$75 a year, F4 +$55 a year (0.74×).
  - Account level: the pick's R3 score Q = 0.34 became Q = −0.18 on F4.
- **Cross-asset, for information** (no grade, because the pick is not WORKS): on XAUUSDm F4 the BTC pick had 0 of 96
  wiped, worst DD 37.8%, mean +50.7%, median +53.7%, 89% of quarters positive and 8 of 8 timings. Gold's strong 2025-26 rise drives this result. The gold pick on BTC F4 was not run here, because the gold step had not written its picks (B11).

## 4. The best configurations by the pre-registered score

Stages B and C were nearly all V3L, so the leaders below are all V3L variants. Scores are R3 one-year accounts
(42 per design, F1-F3); F4 rows are the R4 fold (96 accounts).

| # | Design (V3L + …) | R3 wiped, mean, max DD, Q | F1 / F2 / F3 mean (R4) | F4 mean, worst DD, adds | F4 ×1.5 |
|---|---|---|---|---|---|
| 1 | C9 Donchian(H4) side, T11, **D3** (3 adds), flat, **Bollinger %B** add, **Z1 pre-funded unit** | 0, +28.3%, 32.8%, 0.86 | −3.1 / +11.1 / +54.8 | **+64.3%, 38.7%, 6.7%** | +58.3% |
| 2 | C9, T11, flat, **M4** (RSI + MACD turn), gap 0.5, Z2 | 0, +7.7%, 10.3%, 0.75 | +1.4 / +6.7 / +8.6 | +21.1%, 22.0%, 2.0% | +19.6% |
| 3 | C9, T11, **D2**, flat, geometric gap 1.5, Z1 | 0, +32.4%, 50.3%, 0.64 | −3.1 / +7.5 / +69.0 | +36.3%, **56.9%** | +34.5% |
| 4 | C11, T11, flat, GT5 (ADX gate), Z2 = **WF1 pick** | 0, +4.6%, 13.2%, 0.35 | +3.9 / +2.0 / +3.9 | −1.2%, 21.3%, 14.6% | −1.2% |
| 5 | C11, T11, +1, Z2 = **WF2 / WF3 pick** | 0, +4.5%, 13.1%, 0.34 | +3.0 / +2.7 / +3.8 | −3.2%, 17.8%, 15.8% | −4.9% |

- Pool members 6-15 are the same family: C9 or C11 confirmation, T11 or T7 tiers, flat or +1, with a time stop,
  depth, gap or RSI-force-close tweak. All had 0 wipes, R3 mean +2.8 to +12.2% a year, and Q 0.21 to 0.31.
- **Why #1-#3 were not picked.** Their F1 mean was negative, so their minimum training Q lost to #4 / #5. They earn
  through Z1, a unit that is larger and adapts to volatility, during BTC's 2023-25 trend: +55 to +69% a year in F3.
- **Conditional on today's costs, not a pass (§5.2).**
  - #1 and #2 meet S1-S6 on F4 alone, at spread × 1.0 and × 1.5.
  - #1: worst DD 38.7%, 73% of quarters positive, median r/DD 1.85. #2: 22.0%, 65%, 1.88.
  - But their add acts in only 6.7% and 2.0% of baskets, so S8 fails: they are not ladders.
  - S7 (continuous accounts) was not run for them.
  - V3 with no ladder also does well on F4 (+18.7%).

## 5. The owner's points, one by one (stage A R1 unless stated: 22 quarter accounts; base L0 = 9 wiped, mean −67.2% a quarter)

| Question | L0 (live) | LB (bounded) | V3L / elsewhere | Stage D: best L0 level on F4 (10 accounts) |
|---|---|---|---|---|
| **1-3 sizes** | flat 6 wiped / −43.9%; +1 7 / −60.1%; **doubling 13 / −82.4%**; Fibonacci (live) 9 / −67.2%. Owner grid: mean wipes per 22 quarters flat 4.0, +1 7.1, Fibonacci 7.8, doubling 9.6; **0 of 132 grid designs positive** | all ≈ −10% (3 adds and a stop cap the shape) | +1 is the only shape in the pick (the single add at 2 units) | flat: 8 of 10 wiped, −88.7% |
| **4 tier timeframes** | shorter T1 [M5,M15,H1] 6 / −48%; T2 6 / −56%; longer T5 (+D1) 8 / −71%, T6 (+D1,W1) 10 / −75%, T4 9 / −62%, T7 [H1,H4,D1] 8 / −55%; one timeframe ×5 (T8-T11) 12-18 wiped (all adds fire together) | T1-T11 −8.6 to −9.9%, all better than LB's −11.2% (fewer adds) | **T11 (add on H4) is in every pick** | T1: 9 of 10 wiped |
| **5 granularity** | T12 (M2-M20) 12; T13 (M10-H6) 10; T14 (M30-H12) 18; T15 (9 tiers) **22 of 22**; T16 8 | −9.7 to −11.2% | T13 on V3L +0.06% | T16: 9 of 10 |
| **6 MACD trigger** | turn 8 / −64.8%; histogram 16 / −91.7%; cross 8 / −68.0%; **RSI and turn 6 / −47.6%** | −10.3 to −14.0% | M4 is in pool #2 | M4: 10 of 10 |
| **7 third indicator** | Stochastic 8; %R 12; CCI 10; %B 8; **EMA-distance/ATR 6 (−45%)**; RSI(2) 10; RSI cross 8; price step 6 | −10.3 to −15.5% | %B in pool #1 | EMA-distance: 8 of 10 |
| **8 side switching** | with H4 trend 3 / −39%; against 6; against D1 4; D1-RSI side 6; **stop-and-reverse 12 / −77% (×2: −85%)**; **hedge-on-depth 12 / −84%**; counter-ladder 4 / −35.5% | S5 −9.3%, S9 −13.7%, S6 −16.6%, S7 −22.3% | stop-and-reverse is the best single V3L change at R1 (+1.56%); it reached R3 but not the pool | with H4 trend: 4 of 10, −58.9% |
| **9 brainstorm** | **RSI 20/80: 0 wiped, −27.8%** (R2 0 of 48, −25.8%, DD 82%); 25/75 2; 40/60 18; 45/55 22. Gap 2 vol: 2 / −32%. Adds only with the H1 trend: 3 / −35%. Depth 1: 6 / −44%; 8: 17; 12: 22. Vol stops 10-12 (they turn floating losses into realised ones); % stops 8-9. Time stops: **no effect** (L0 baskets never last 5 h; the M15 force-close ends them). LIFO 10, overlap 8, anti-martingale 8, pre-funded / vol-target unit 9 (−77%) | gates and gaps −7.5 to −11%; Friday-flat best (−8.0%) | | RSI 20/80: 4 of 10, −69.6%; gap 2: 6 of 10; H1-trend adds: 2 of 10, −67.5% |
| **Entries: {H4,M5} vs {H1,M15}, ± D1** | {H4,M5} 7 / −55%; pre-v3.9.0 set 8 / −53%; {H1,M15,D1} `entry_s` 2: 10 / −71%, `entry_s` 4: 6 / −46%; **{H4,M5,D1} `entry_s` 4: 4 / −37%**; {H1} 6; RSI-only votes 6; no agreement 12 / −79% | {H4,M5} −12.3; {H1,M15,D1}/4 −6.1; {H4,M5,D1}/4 −7.5; {H1} −5.7 | adding D1 helps only with `entry_s` 4 (stricter), never with `entry_s` 2 | {H4,M5,D1}/4: **0 of 10 wiped but −40.6%** |
| **RSI + a 2nd indicator** | **EMA50(H4) side 0 / −24.5%** (R2 0 of 48, −21.3%); Supertrend(H4) 0 / −29%; Donchian(H4) 0 / −33%; EMA200(D1) 6; ADX 4-6; Stoch/CCI/%B zones 6 | oscillator zones best: %B −2.7%, Stoch −2.9% (DD 9-10%) | **D1 MACD trend (C11) and Donchian (C9) define every V3L leader** | EMA50(H4): 0 of 10, −52.6% |
| **Exits** | force-close H1 / H4 / D1 / off: 10 / 8 / 10 / 12; RSI force-close 8; H6 final close 10; target $0.5 10, $2 7, $5-$10 6, b/e 8 | force-close off ≈ the base at R2 (−10.4% vs −10.2%), +9.1% on F4 | target and stop in volatility units (V3L) are what survive | |
| **Slot 5 (L5) on BTC** | R1 8 of 22 quarters wiped; R3 40 of 42 years; R4 F1-F3 275 of 288; **F4 96 of 96**; 8y, 5y and last year all wiped; anchor 184 of 184 lost | | its best single changes (force-close off: 2 wiped, −12.3%; {H4,M5} entries: 0 wiped, −20.2%) still lose | |

## 6. What each dimension did, in one line

- **Ladder shape:** flat > +1 > Fibonacci > doubling. Every shape loses; doubling wipes the most.
- **Depth and tiers:** fewer, slower adds lose less. Each extra tier (D1, W1, 9-tier lists, repeated timeframes)
  adds wipes.
- **Trigger (RSI, MACD, third indicator):** a stricter or confirmed trigger means fewer adds, which loses less, but no
  trigger made the ladder earn. RSI ≤ 20 was the best single change on the live bot, and it works only by almost
  never adding.
- **Side switching:** reversing at the stop and hedging at depth made it worse. A counter-ladder or trading with the
  trend was less bad.
- **Entries and confirmation:** trend gates (EMA50 H4, Supertrend, Donchian, D1 MACD) remove most wipes, but the
  ladder still loses 20-30% a quarter.
- **Exits and risk:** targets, stops, time stops, partial closes and sizing rules never turned a loss into a profit.
- **The V3L frame** (stop and target in volatility units, force-close off) is the only frame that survives.
  - Its single add helped on F2-F3: about +0.5 to +1.6 points a year over the no-add twin.
  - It hurt on F4.

## 7. Files

- `search_BTCUSDm.csv`: 59,863 rows. Columns: `stage` (A, O, B, C or ref), `rung` (R1, R2, R3, R4-F1…F4, cont-8y,
  5y or 1y, anchor-184, stageD-F4-1y, xasset-F4, unit-F1F3, unit-F4) and `variant` (@spread1.5, @spread2,
  @noladder). R2 rows that reuse R1 quarters carry `reused_R1_row`.
- `picks_BTCUSDm.json`, `stageB_plan_BTCUSDm.json`, `DEVIATIONS.md` (B1-B11).
- Scripts and stage files are in the scratch folder `port_tmp/ladder/btc/`:
  - `pipeline.py`, `stage.py`, `r4.py`, `evalx.py`;
  - `registry.json`, `stages.json`, `stageO_plan.json`, `pool.json`, `evalx.json`, `dims_BTCUSDm.csv`, `stageD_table.csv`.

**Recommendation.** No ladder design may go to live money on BTCUSDm. The live bot and slot 5 should not run on BTC
with real money. If anything goes to the demo account, the evidence favours V3-lite without the ladder (ref V3), not
any ladder. The independent rebuild (PREREG §7 step 10) of the WF3 pick, the best failing pick, is still to do.
