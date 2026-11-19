# SEARCH_XAUUSDm: the pre-registered ladder search on XAUUSDm

Step "search XAUUSDm", 18-19 Nov 2026, branch `backtest_hedging`. Nothing was committed. `PREREG_LADDER.md` sha256 was
checked with `shasum -c` at the start and at the end: OK. `git diff` of tracked files is empty. Raw rows of every run are
in `search_XAUUSDm.csv`. The picks are in `picks_XAUUSDm.json`, written before their test folds were read. Interpretations
and deviations are X1-X15 in `DEVIATIONS.md`. X12-X15 were added in the finishing step, after the first workflow was cut
off. X12 and X15 were written after the results they concern were read; X13's shadow rule was written before its runs.

## Verdict (PREREG §5.2): **EARNS, DOES NOT SURVIVE**. No DCA ladder works on XAUUSDm.

- **Every multi-add ladder failed.** Ladders built on the live bot (L0), the slot-5 variant (L5) and the bounded live
  ladder (LB) were 785 designs, covering the owner's points 1-9, the entry and exit questions, and the brainstorm.
  - **None of the 785** had a positive mean return over the 22 R1 quarters.
  - None reached R3: all 120 R3 places went to variants of V3-lite with one add (V3L).
  - The live bot wiped **288 of 288** one-year accounts in F1-F3 and **96 of 96** in F4. Slot 5 wiped 288 of 288
    and 95 of 96. On the 8-year, 5-year and last-year accounts, L0, L5 and LB were all wiped. LB was wiped on 8y and
    5y, but none of its one-year accounts was.
- **What survives is not a DCA ladder.** It is the V3-lite frame (H1 votes, H1 trend filter, stop and target in H1
  volatility units, force-close off, a 4 h pause after a loss) with **one add of one unit**. The large returns come
  from the **Z1 pre-funded unit**: a compounding unit sized so the whole ladder risks 30% of the balance. That is
  leverage, not an edge.
- **The walk-forward pick** was `V3L|STOP=ST3|GRAN=T12|SIZING=Z1`: V3-lite, a stop at 12 volatility units, one add on
  an M2 MACD turn at least 1 volatility unit away, and the Z1 unit.
  - It never wiped an account (0 of 96 in every test fold, at spread × 1.0 and × 1.5). Its returns were very large:
    mean +154% a year on F3 and +349% on F4.
  - But its **worst drawdowns were 66-83%** in every split, and the 8-year account fell **75%** from a peak. A
    typical (median) account fell 58-61% at some point.
  - It fails S2 (every split), S7, S8 (WF2) and S9 (DSR ≈ 0.008). Because S3 passes and S2 fails, the pre-registered
    verdict is "earns, does not survive". "Survive" here is the 50% drawdown limit, not wipes.
- **Per unit (the edge without the sizing), the pick is no better than the references.**
  - On F4 the pick made **+$2,708 per unit**, V3-lite with no ladder (ref V3) **+$2,848**, and V3L **+$4,032**.
  - The daily Sharpe ratios were 0.068, 0.117 and 0.110.
- **The references beat the picks for an account you could live with.** V3 (no ladder) and V3L (one add, the bot's
  own unit rule) had worst DDs of 32-38% on F4 and the 8-year account, never wiped, and made +$9,957 (V3) and
  +$13,168 (V3L) on the 8-year account.
- **On gold, F4 (Nov 2024 to Nov 2026) was an exceptional trend.** Every trend-following frame earned on it: V3 made
  +154% a year with 100% of account-quarters positive. Read the F4 returns with that in mind.

## 1. What ran

| Stage | Pairs at R1 | To R2 | Notes |
|---|---|---|---|
| A: one dimension at a time around L0, L5, LB, V3L, plus the 4 bases and ref V3 | 448 | 153 (incl. 5 refs) | 45 skips, as built |
| O: the owner's grid. SIZE × tiers {T0, T1, T3, T5, T6, T12, T13} × trigger {RSI, M3, X-emadist} on L0; × {T0, T1, T12, T13} on LB | 132 (111 new, 21 = stage-A designs) | 46 (40 run) | best TRIG-MACD = M3 (R1 fallback: no MACD level reached R2 on L0 / LB) and best TRIG-3RD = X-emadist, by R2 (X2) |
| B: factorial `stageB_plan_XAUUSDm.json` | 378 | 126 | importance GAP > LEVEL > CONFIRM > GATE; bases V3L and LB; levels GAP {GD1, G0.5, G2}, LEVEL {LV30, LVL, =}, CONFIRM {C1, C11, C8}, GATE {GT5, GT1, GT3}, × 4 sizes. **The plan was scored on the 13 R2-only quarters, not on R1 + R2 (X13).** See the shadow below |
| C: 30 neighbours of the 10 best R2 pairs | 252 (239 distinct, 232 new) | 119 (113 run) | the 10 parents were all V3L designs |
| **Total (as run)** | **N = 1,169 pairs**, or **1,493** with the shadow (budget 3,500) | 444 promotions, 432 pairs run at R2 | |
| R3: 120 best by R2, plus 5 refs | 125 × 42 one-year accounts, plus the per-unit F1-F3 run | | 121 were V3L-based (incl. the ref) |
| R4: pool of 15 + 5 refs, F1-F4 (96 accounts per fold) | 7,680 accounts | | picks written before F2, F3 and F4 were run; spread × 1.5 (picks + 5 best) and × 2.0 (picks); no-ladder twins; 8y / 5y / 1y; 184 anchor; per-unit F4; cross-asset on BTC F4 |
| D: best level of every dimension around L0 and LB, on F4 (5 one-year accounts × 2 seeds) | 40 designs + L0, LB | | 2 LB levels corrected and run on 19 Nov (X12) |
| Shadow B (X13): the stage-B plan scored on R1 + R2 | 324 (all new, all LB-based) | 108 | none beat a later cut, so the cascade stopped (§4a) |

- **Runs:** 53,931 account runs, plus 9,936 in the shadow. These include 131 per-unit runs.
  - R1: 25,718 = 1,169 × 22. R2: 11,232 = 432 × 26 (X11: R2 adds only the 13 missing quarters). R3: 5,250.
  - R4: 9,696 including the variants. Continuous: 100. Anchor: 1,288. Stage D: 420. Cross-asset: 96.
- **Machine time: 24.7 h of wall time** (18 Nov 03:50 to 19 Nov 04:29 IST) on 4 workers, sharing 8 cores with the
  BTC step.
  - R1 + R2 (stages A-C): 10.6 h.
  - R3: 6.4 h, plus 1.0 h for the per-unit run.
  - R4: 5.0 h. Extras: 1.6 h.
  - The finishing step on 19 Nov (8 workers): stage-D fix, 1 min; shadow B, 56 min.
- **No cuts were needed.** F4 was run for the whole pool (X6).

## 2. Survival: the honest picture (fresh $2,000 accounts, bot sizing, ticks, live loop timing)

"Wiped" follows the PREREG rule: equity at or below $200 at any time, even if the account later recovers.

| Family | R1: pairs with 0 wipes in 22 quarters | R1: pairs with mean > 0 | Share of R1 quarter accounts wiped | F1-F3 one-year accounts wiped (R4, 288) | F4 (96) | 8y / 5y / last year (8) |
|---|---|---|---|---|---|---|
| L0 live v3.9.2 (191 designs) | 26 | **0** | 20.2% | **288**, mean −100% | **96**, −100% | wiped / wiped / 8 of 8 wiped |
| L5 slot-5 (117) | 10 | **0** | 15.0% | **288** | 95, −99.3% | wiped / wiped / 8 of 8 wiped |
| LB bounded live (477) | 477 | **0** | 0 | 0, but −27.5% a year | 0, −4.2%, DD 30.8% | **wiped / wiped** / +$104, 0 of 8 |
| V3L one add (383) | 383 | 280 | 0 | 0, +4.8% a year (ref); pool +7.8 to +150% | 0, +277%, DD 37.3% (ref) | +$13,168 DD 32.5% / +$10,433 DD 31.5% / +$2,144, 0 of 8 |
| ref V3, no ladder | 1 | 1 | 0 | 0, +10.9% a year | 0, **+154%, DD 38.2%, 100% quarters > 0** | +$9,957 DD 33.0% / +$8,748 DD 30.6% / +$1,668, 0 of 8 |
| WF3 pick (V3L + ST3 + T12 + Z1) | | | | 0, +150% a year, **DD up to 83%** | 0, +349%, **DD 65.9%** | **+$42,836 DD 75.3%** / +$40,753 DD 41.8% / +$2,208, 0 of 8 (DD 58.5%) |

- **At R3,** only Z1 designs among the V3L family lost an account: V3L|SIZING=Z1 lost 2 of 42 and two others lost 1
  each. L0 and L5 lost **42 of 42** one-year accounts.
- **Old anchor view (184 quarters, today's store):**
  - live L0: mean **−$1,017**, **172 of 184 lost**, 34 wiped. This matches the 172 of 184 quoted in the brief.
  - L5: −$900, **181 lost**, 22 wiped.
  - LB: −$93, 156 lost, 0 wiped.
  - V3: +$151, 32 lost. V3L: +$185, 64 lost.
  - WF1 pick: +$344, 70 lost. WF2 / WF3 pick: +$747, 48 lost.
- **Per unit, F1-F3 (6 years):** L0 −$32,827; L5 −$23,852; LB −$3,065; V3L +$807; V3 +$1,205; WF3 pick +$1,828;
  WF1 pick +$1,278.
- **Per unit, F4:** L0 −$6,863; L5 −$10,398; LB −$45; V3L +$4,032; V3 +$2,848; WF3 pick +$2,708.

## 3. Walk-forward picks and the pass test (PREREG §5.1)

| Split | Pick (written before the test fold) | Train: wiped, min Q |
|---|---|---|
| WF1 (F1 → F2) | `V3L|FC=FC5|TRIG-3RD=X-stoch|SIZING=Z1`: the owner's RSI force-close (H1 and H4); the add on a closed-bar Stochastic(14,3) ≤ 20 / ≥ 80; Z1 | 0, 4.41 |
| WF2 (F1-F2 → F3) | `V3L|STOP=ST3|GRAN=T12|SIZING=Z1` | 0, 1.49 |
| WF3 (F1-F3 → F4) | the same as WF2 | 0, 1.49 |

**The WF3 pick's full settings** (in `search_XAUUSDm.csv` and the registry):
- **Entries:** H1 votes only (`open_weights` {H1: 1}, `entry_agree_s` 0), and the H1 trend filter.
- **Exits:** force-close off. Target 10 and stop 12 H1 volatility units (vol_len 24). A 4 h pause after a loss.
- **The add:** one add (`max_adds` 1) of 1 × unit, on an M2 MACD turn, at least 1 volatility unit from the first fill.
- **Unit:** pre-funded. The largest unit for which the full ladder, filled one gap apart down to the last tier and
  then a further 1.5 × ATR(D1), loses at most 30% of the balance.

| Test (96 accounts) | S1 wiped ×1 / ×1.5 | S2 worst DD | S3 mean / median / mean ×1.5 | S4 quarters > 0 | S5 median r/DD (×1.5) | S6 timings > 0 | S7 8y / 5y / 1y | S8 adds; vs twin | S9 DSR |
|---|---|---|---|---|---|---|---|---|---|
| WF1 on F2 | **0 / 0** | 80.1% ✗ | **+17.9 / +9.1 / +15.5** | 44% ✗ | 0.15 ✗ (0.13 ✗) | **8** | 8y +$32,368 DD 46.4; 5y +$24,252 **DD 67.3** ✗; 1y 0 of 8 | **62%; +17.9 vs +9.1** | - |
| WF2 on F3 | **0 / 0** | 83.0% ✗ | **+153.7 / +163.9 / +175.7** | **72%** | **2.68 (3.45)** | **8** | **8y DD 75.3** ✗; 5y +$40,753 DD 41.8; 1y 0 of 8 | 74%; **+153.7 vs +197.5** ✗ | - |
| WF3 on F4 | **0 / 0** | 65.9% ✗ | **+349.1 / +299.9 / +314.3** | **79%** | **5.19 (4.22)** | **8** | as WF2 ✗ | **68%; +349.1 vs +54.4** | **0.008** ✗ |

- **Spread × 2.0, for information:** −10.4% (F2), +185.2% (F3), +303.5% (F4). On F3, the × 1.5 and × 2.0 runs made
  *more* than × 1.0. The Z1 compounding path is chaotic: small cost changes move the result a lot.
- **Comfortable columns:** WF1 meets S3 and S6. WF2 and WF3 meet S3, S4, S5 and S6. No split meets S2.
- **The S8 twin under Z1 is not the same size (X15).** With no add, Z1 puts the whole 30% risk budget on one position.
  - The F4 twin therefore wiped 40 of 96 accounts.
  - The pick "beats its twin" on F4 because its first position is smaller, not because the add helps. On F3 the twin
    beat the pick.
- **The pick's risk in F4:** median DD 57.7%, worst basket −$5,627, 1.68 positions per basket on average (at most 2),
  in the market 66% of the time, 12 baskets a month, 0 margin refusals. Per-timing means were +274% to +418%.
- **Haircut (§5.4):**
  - SR̂ = 0.068 a day (T = 516 trading days, skew 0.48, kurtosis 11.1).
  - Var[SR] = 0.0026 over the 125 R3 per-unit runs. N = 1,493 (1,169 as run plus the 324 shadow designs).
  - SR₀ = 0.173, so **DSR = 0.0079**. With N + 1,200: 0.0046. With N = 1,169 as run, SR₀ = 0.169 and DSR = 0.0098.
  - With only the V3 / V3L runs' dispersion (Var 6.2 × 10⁻⁵), SR₀ = 0.026 and DSR = 0.83 (at N = 1,493). That is still below 0.95.
- **Selection inflation:**
  - Account level: the pick's R3 score Q = 1.54 rose to Q = 5.30 on F4. F4 was gold's strongest trend.
  - Per unit: +$305 a year in F1-F3 became +$1,354 a year in F4, a ratio of 4.4. V3 rose 7.1× and V3L 15× on the same
    split, so against the references the pick **lost ground** out of sample.
- **Cross-asset, for information** (no grade, because the pick is not WORKS):
  - The gold WF3 pick on BTCUSDm F4: **5 of 96 wiped**, worst DD 95.9%, mean +24.7%, **median −23.2%**, 52% of
    quarters positive. It fails S1 and S2 on BTC.
  - The BTC pick on gold F4 (BTC step): 0 wiped, DD 37.8%, mean +50.7%.

## 4. The best configurations by the pre-registered score

All 15 pool members are V3L variants. R3 is 42 one-year accounts per design (F1-F3); R4 is 96 accounts per fold.

| # | Design (V3L + …) | R3 wiped, mean, max DD, Q | F1 / F2 / F3 mean (R4) | F4: wiped, mean, median, worst DD, adds, quarters > 0 | F4 ×1.5 |
|---|---|---|---|---|---|
| 1 | ST3 stop 12, T12 (add on M2), **Z1** = **WF2 / WF3 pick** | 0, +128.5%, 83.4%, 1.54 | +112.8 / +182.7 / +153.7 | 0, +349.1%, +299.9%, 65.9%, 68%, 79% | +314.3% |
| 2 | FC5 RSI force-close, Stochastic add, **Z1** = **WF1 pick** | 0, +79.7%, 82.7%, 0.96 | +234.1 / +17.9 / +6.2 | 0, +308.4%, +304.9%, 62.2%, 56%, 87% | +293.6% |
| 3 | C5 (ADX(H4) ≥ 25, DI side), **Z1** | 0, +79.9%, 87.8%, 0.91 | +182.2 / **−32.7** / +125.9 | 0, **+1,266%**, 51.6%, 50%, 91% | +1,261% |
| 4 | C5, S7 stop-and-reverse ×2, T8, T12 (live unit) | 0, +21.3%, 28.9%, 0.74 | +8.5 / +24.9 / +13.0 | **2 wiped**, +46.4%, +18.8%, **94.9%**, 63%, 57% | +28.4% |
| 5 | T12, GT5 (no adds while ADX(H1) > 30), Z3 (1 unit) | 0, +12.6%, 18.8%, 0.67 | +15.6 / +2.4 / +10.3 | 0, +34.5%, +33.0%, 59.4%, 53%, 80% | +32.5% |

- **Pool members 6-15** are the same family: confirmation C1 / C11, flat add, gaps GD1 / G2 / G0.5, gate GT1 / GT5, or
  ST3 with a time stop, gap or partial-close tweak. All had 0 wipes in F1-F4.
  - The nine without Z1 made −9.3 to +29.2% a fold in F1-F3.
  - ST3 + Gint300 + GT9 + Z1 made +42 to +133%, with a worst DD of 76-83%.
- **The worst F4 drawdowns were 39-81% (most 54-68%).** ST3 + Ggeo1.5 and ST3 + P1 behave exactly like ST3 alone: with
  one add, the geometric gap and LIFO close change nothing.
- **References on the same protocol:** V3L made +16.5 / −8.1 / +6.0 / **+277.0** (F4 DD 37.3%). V3 made +8.1 / +5.1 /
  +19.6 / **+153.6** (F4 DD 38.2%).
- **Near-miss lists (§5.5 item 3; R3, 120 non-reference designs, 42 one-year accounts F1-F3).** "Survives" means
  0 wiped and max DD ≤ 50%. "Earns" means mean and median > 0.
  - **Survives and earns: 107.** Best five:
    1. C5 + S7 + T8 + T12: Q 0.74, +21.3%, DD 29.
    2. T12 + GT5 + Z3: 0.67, +12.6%, DD 19.
    3. C1 + flat + GD1 + GT1: 0.67, +10.0%, DD 15.
    4. C11 + flat + G2 + GT5 + Z2: 0.66, +10.8%, DD 16.
    5. ST3: 0.65, +13.7%, DD 21.
    - On F4, all but #4 had drawdowns of 59-95%. #4 had F2 −9.3%.
  - **Survives, does not earn: 1.** C11 + TG7 + flat + G2 + GT5: mean +3.6%, median ≤ 0, DD 17.
  - **Earns, does not survive: 11, all Z1.** The best five: the WF3 pick (Q 1.54, DD 83), the WF1 pick (0.96, DD 83),
    C5 + Z1 (0.91, DD 88), ST3 + Gint300 + GT9 + Z1 (0.65, DD 82), and C11 + plus1 + X-stoch + G2 + GT5 + Z1 (0.57, DD 74).
- **Conditional on today's costs (§5.2), not a pass.** On F4 alone, two pool members meet S1 (at × 1.0) and S2-S6:
  - C11 + flat + G2 + GT5 + Z2: DD 38.8%, +51.2%, 77% of quarters positive, r/DD 2.19.
  - TM3 + T12 + Z3 + P1: DD 42.3%, +94.9%, 84%, r/DD 3.08.
  - Neither had a × 1.5 run or a twin, because they were not among the 5 best. Both made less than V3 (+153.6%) and V3L
    (+277%) on the same fold, at the same DD.

### 4a. The shadow stage B (X13): the stage-B plan as X3 / X11 define it

- **The plan used for stage B was scored on only the 13 R2-only quarters.** The rule says R1 + R2.
- **The correct plan:** dimensions LEVEL > GAP > ENTRY > CONFIRM, bases V3L and LB, levels LEVEL {LV20, LV30, LV25},
  GAP {G2, GD1, =}, ENTRY {E10, E3, E8}, CONFIRM {C10, C1, C4}.
  - Its levels have no "=" for LEVEL, and an RSI level does not apply to V3L's MACD-turn add (stage A also skips LEVEL
    on V3L).
  - So the factorial builds **only LB designs**: 4 sizes × 3⁴ = **324**, all new.
- **Results:**
  - R1 (22 quarters): **324 of 324 had 0 wipes, and none had a positive mean.** The best R1 mean was −2.0% a quarter
    and the best Q −0.20.
  - 108 were promoted to R2. The best R2 design was `LB|ENTRY=E10|CONFIRM=C1|SIZE=*|LEVEL=LV20`: 0 wiped, −5.6 to
    −5.8% a quarter, DD 38-40%, Q −0.145.
- **The pre-declared cascade stopped at once.** No shadow design beat the 10th stage-C parent (Q 0.275) or the 120th
  R3 entry (Q 0.115), so no R3 or R4 run was needed. The shadow cannot have changed the pool, the picks or the verdict.
- **Cost:** 9,936 runs and 56 min of wall time on 8 workers.

## 5. The owner's points, one by one (stage A R1 unless stated: 22 quarter accounts; base L0 = 4 wiped, mean −54.0% a quarter, DD 100%)

Cells read "wiped of 22 / mean % a quarter". Stage D is the best stage-A level on F4 (5 one-year accounts × 2 seeds).
There, L0 was 10 of 10 wiped (−100%) and LB 0 of 10 (−7.2%, DD 27%).

| Question | L0 (live) | LB (bounded) | V3L / elsewhere | Stage D on F4 |
|---|---|---|---|---|
| **1-3 sizes** | **flat 2 / −29.4**; +1 4 / −49.3; Fibonacci (live) 4 / −54.0; **doubling 7 / −67.1**. Owner grid (84 L0 designs): mean wipes per 22 quarters flat 1.2, +1 2.7, Fibonacci 3.3, doubling 6.0; **0 of 132 grid designs positive** | flat −5.4, +1 −7.3, doubling −7.2, Fibonacci −7.3 (3 adds and a stop cap the shape) | V3L: +1 +3.0 against flat +5.6; every pool member uses a single 1-unit add | L0 flat: 8 of 10 wiped, −92.6%. LB flat −17.3% |
| **4 tier timeframes** | shorter T1 [M5,M15,H1] **2 / −32.8** (best); T2 [M1,M5,M15] 4 / −44.0; longer T3 (+D1) 4 / −47.0, T4 [M15…W1] 4 / −47.9, T5 (+D1) 4 / −59.0, T6 (+D1,W1) 6 / −57.0, T7 [H1,H4,D1] 5 / −51.9; one timeframe ×5 (T8-T11): 12, 18, **22, 22** wiped (all adds fire together) | −5.3 (T11) to −6.5, all a little better than LB −7.3 | V3L: T2 +5.9, T11 +1.0 | L0 T1: 8 of 10 wiped, −90.8%. LB T8 −20.8% |
| **5 granularity** | T12 (M2-M20) 6 / −63.3; T13 (M10-H6) 6 / −62.5; T14 (M30-H12) 17 / −89.9; T15 (9 tiers) 18 / −85.8; T16 (M6,M12,M20,H3,H8) 4 / −52.2 | −6.1 to −7.3 | **T12 is in the WF2 / WF3 pick.** With one add it means only "add on an M2 MACD turn" (V3L + T12 +6.2 against +5.6) | L0 T16: 10 of 10. LB T12 −18.0% |
| **6 MACD trigger** | turn 4 / −55.7; **histogram 20 / −96.3**; cross 4 / −56.1; **RSI and turn 2 / −32.7**. Owner grid L0: RSI 5.1 wipes / −48.8%, M3 3.2 / −46.0%, EMA-distance 1.6 / −30.5% | M3 −6.6 (best), histogram −10.1 | V3L already adds on a MACD turn; M2 +6.2 | L0 M4: 9 of 10 wiped. LB M3 −26.4% |
| **7 third indicator** | Stochastic 4 / −57.2; %R 12 / −79.8; CCI 5 / −65.8; **%B 2 / −36.1**; **EMA-distance/ATR 4 / −36.0**; RSI(2) 4 / −63.0; RSI cross 4 / −40.1; price step 2 / −36.9 | EMA-distance −6.2 (best); price step −10.3 | V3L: %B +7.6, RSI(2) +7.6, **Stochastic +7.4 (in the WF1 pick)** | L0 %B: 10 of 10. LB EMA-distance −13.6% |
| **8 side switching** | with H4 trend 1 / −27.3; against 4 / −39.1; against D1 2 / −36.0; D1-RSI side 4 / −51.6; **stop-and-reverse 4 / −57.2 (×2: 6 / −65.3)**; **hedge-on-depth 7 / −78.0** (the worst side mode); **counter-ladder 2 / −25.2** | trend sides S1-S4 −15.9 to −19.6 (DD 48-74%); S5 / S8 / S9 ≈ the base | V3L: S5-S7 +3.7 against +5.6. S7 is in pool #4, which wiped 2 accounts and had a 94.9% DD on F4 | L0 with H4 trend: 1 of 10 wiped, +57.9% but DD 105%. LB with D1 trend −12.4% |
| **9 brainstorm** | **RSI 20/80: 0 / −18.5** (R2: 0 of 48, −16.6%, DD 66%; the best single L0 change, because it almost never adds); 25/75 0 / −22.3; 40/60 18; 45/55 22; looser deeper 15. **Gap 2 vol units: 0 / −19.8** (DD 64%); 1 vol unit 2; 300 s 4. **Adds only with the H1 trend: 0 / −22.5**. Depth 1: 2 / −33.2; 8: 16; 12: 21. Volatility stops 4-12 units **4-7 / −72 to −79** (they turn floating losses into realised ones); % stops 10-30% 4 / −54 to −62. Time stops: **no effect**. Targets: TG7 (8 vol) −30.4 the best; $0.5 −58.4. LIFO / overlap close −56 / −53. Anti-martingale 2 / −41.4. Z1 / Z2 / Z3 sizing ≈ the base | targets $5-$10 / 4-8 vol units −3.5 to −3.8 (the best LB singles); gaps and gates −6.1 to −8.0 | **Z1 is the lever that moves V3L: +49.8% a quarter, DD 64%** (all other V3L singles +7.6% or less); ST3 +6.6 | L0 RSI 20/80: 4 of 10 wiped, −74.5%; gap 2: 6 of 10; H1-trend adds 6 of 10. LB target $10 **+33.5%** DD 40%; anti-martingale +15.7% DD 49% |
| **Entries: {H4,M5} vs {H1,M15}, ± D1** | {H4,M5} 4 / −46.8 (= live 4 / −54.0, slightly better); pre-v3.9.0 set 8 / −57.5; {H1,M15,D1} `entry_s` 2: 6 / −61.1, `entry_s` 4: 2 / −34.1; {H4,M5,D1} `entry_s` 2: 6 / −46.6, **`entry_s` 4: 0 / −23.1**; {H4,H1,M15}/4 2 / −31.2; {H1} 4 / −44.4; RSI-only 4 / −46.0; no agreement 5 / −63.3 | {H1}, {H4,H1,M15}/4 and {H4,M5,D1}/4 −3.6 to −3.8; pre-v3.9.0 −13.2; no agreement −12.6 | V3L uses {H1} with no agreement; no other set beats it (−1.0 to +5.6 against +5.6) | L0 {H4,M5,D1}/4: 7 of 10 wiped, −78.6%. LB no agreement −25.5% (DD 62%) |
| **RSI + a 2nd indicator** | **EMA50(H4) side 0 / −20.0**; **Supertrend(H4) 0 / −19.7** (DD 56%); Donchian(H4) 0 / −21.1; EMA200(D1) 1 / −30.7; ADX < 25 1 / −33.4; ADX ≥ 25 DI side 4; oscillator zones (Stochastic, CCI, %B) 4; variance ratio 4; D1 MACD 3 / −30.5 | oscillator zones best: Stochastic −1.8% (DD 5%), CCI −2.1%, %B −2.3%. All negative | C5 (ADX DI side) is in pool #3 and #4; C1 / C11 are in pool #6-#15 | **L0 EMA50(H4): 0 of 10 wiped, +42.3% but DD 64%**. LB CCI zone +4.4% DD 19% |
| **Exits** | force-close H1 / H4 / D1 / off: 8 / 6 / 4 / **13** wiped (off −12.4%: some accounts fall to ≤ $200 and recover); owner's RSI force-close 4 / −56.3; H6 final close 6 / −69.7; targets as above | force-close H1 ≈ the base (−7.3%); H4 −14.1% | stop and target in volatility units, force-close off (V3L) are what survive; RSI force-close (FC5) is in the WF1 pick | L0 force-close D1: 10 of 10 wiped. LB H1 −9.1% |
| **Slot 5 (L5) on gold** | R1 4 of 22 quarters wiped, −53.2%; R3 **42 of 42** years wiped; R4 F1-F3 **288 of 288**; **F4 95 of 96**; 8y, 5y and last year all wiped; anchor **181 of 184 lost** | | its best single changes ({H4,M5,D1}/4: 0 wiped, −11.3%, DD 35%; force-close off 4 / −6.0%; counter-ladder 0 / −20.7%) still lose | |

## 6. What each dimension did, in one line

- **Ladder shape:** flat > +1 > Fibonacci > doubling, as on BTC. Every shape loses on L0, L5 and LB, and doubling wipes
  the most.
- **Depth and tiers:** fewer, slower adds lose less. Repeated timeframes (all adds fire at once), long 6-9-tier lists
  and depth 8-12 wipe the most. D1 / W1 tiers did not help.
- **Trigger (RSI level, MACD, third indicator):** a stricter trigger (RSI 20/80, RSI + MACD turn, %B, EMA distance)
  adds less and so loses less. **No trigger made a multi-add ladder earn.** The MACD histogram was the worst trigger.
- **Side switching:** hedge-on-depth and stop-and-reverse made the live ladder worse. Trading with the H4 trend and the
  counter-ladder were the least bad, but still lost 25-27% a quarter.
- **Entries and confirmation:** stricter entries ({H4,M5,D1} with `entry_s` 4) and trend gates (EMA50 H4, Supertrend,
  Donchian) remove the R1 wipes. The live ladder still loses about 20% a quarter.
- **Exits and risk:** wider gaps, trend-only adds and the best targets cut losses. Volatility stops on the live ladder
  made it worse. Time stops did nothing. None turned a loss into a profit.
- **Sizing:** the Z1 pre-funded unit multiplies V3L's returns about 9× at R1, and its drawdowns about 6×. Every pick
  and every "earns, does not survive" design carries it.
- **The V3L frame** (stop and target in volatility units, force-close off, H1 entries, one add) is the only frame that
  earns. Its single add is not reliably useful:
  - The pick's no-ladder twin beat it on F3.
  - Per unit on F4, V3L with its add (+$4,032) beat V3 with no add (+$2,848), but the walk-forward pick (+$2,708) did not.

## 7. Files

- `search_XAUUSDm.csv`: 63,867 rows: the 53,931 rows as run, plus the 9,936 shadow rows (R1 / R2, `stage` Bfix). The columns are those of `search_BTCUSDm.csv`, plus
  `q_pnl` (X14):
  - `stage`: A, O, B, C, Bfix or Cfix, joined by "+", with "(ref)" for references and "+D" for stage-D rows;
  - `rung`: R1, R2, R3, R4-F1…F4, cont-8y / 5y / 1y, anchor-184, stageD-F4-1y, xasset-F4, unit-F1F3, unit-F4;
  - `variant`: @spread1.5, @spread2 or @noladder.
- `picks_XAUUSDm.json`, `stageB_plan_XAUUSDm.json` (as run), `runs_XAUUSDm/stageB_fix/stageB_plan_R1R2.json` (the correct plan), `DEVIATIONS.md` (X1-X15).
- `runs_XAUUSDm/`:
  - stage and rung CSVs, `final_eval.json` (N = 1,493; `final_eval_asrun_N1169.json` is the as-run copy), `R4_fold_metrics.csv`, `stageO_table.csv`, `dims_stageA_R1.csv`;
  - `stageD_table_v2.csv` (X12; `stageD_table.csv` is the superseded v1);
  - `stageB_fix/` (the X13 shadow).
- Scripts are in the scratch folder `port_tmp/ladder/xau/`:
  - `chain1.py` (A-C, R3 list), `chain2.py` (R3, pool, R4 and picks), `chain3.py` (extras);
  - `funnel.py`, `evaluate.py`, `final_eval.py`, `r4run.py`;
  - `stageD_fix.py`, `shadowB.py`, `gather.py`, `collect.py`;
  - `registry.json` (`registry_before_X13.json` is the as-run registry).

**Recommendation.** No ladder design may go to live money on XAUUSDm. The live bot (v3.9.2) and slot 5 should not run on
gold with real money: on every long account they wipe the balance. The walk-forward pick also may not go to live money.
It fails S2, S7, S8 and S9, and its returns come from a unit that risks 30% of the balance per basket, with drawdowns of
66-83%.

If anything goes to the demo account, the evidence favours the V3-lite frame at the bot's own unit:
- either with no ladder (ref V3: F1-F3 +10.9% a year, F4 +154%, DD ≤ 38%);
- or with its single add (ref V3L).

That is not a DCA ladder. F4 was an unusually strong gold trend, so the demo account is the honest test. The independent
rebuild (PREREG §7 step 10) of the WF3 pick, the best failing pick, is still to do.
