# LADDER: is there a DCA ladder that works on XAUUSDm and BTCUSDm?

19 Nov 2026, branch `backtest_hedging`. Nothing was committed. The rules were frozen before any run in `PREREG_LADDER.md`
(its sha256 was checked at the start and end of every step). Every rule change is logged in `DEVIATIONS.md` (B1-B11, X1-X15, T1-T9).
Details are in `SEARCH_XAUUSDm.md`, `SEARCH_BTCUSDm.md` and `stress/TABLES.md`.

## 1. The answer

**No. No DCA ladder works on gold or on BTC**, under the test written down before the search began.

- **Gold (XAUUSDm): "earns, does not survive".** The best designs make money, but they fall 60-90% from a peak along the way.
- **BTC (BTCUSDm): "survives, does not earn".** The safe designs make 2-4% a year. The ones that make more do it with the unit size, not with the ladder.
- **Your live bot (v3.9.2) wipes the account.** Fresh $2,000 accounts were started on the 13th of every month from Nov 2018 to Nov 2025 (85 starts), each run for 12 months.
  - **Gold:** 170 of 170 accounts were wiped.
  - **BTC:** 169 of 170 were wiped.
  - Every 8-year, 5-year and last-year account was wiped as well.
- **The slot-5 variant (flat ladder, H4 force-close) is no better.** It runs now on `hedging_xauusd5` and `hedging_btcusd5`.
  - **Gold:** 170 of 170 one-year accounts were wiped.
  - **BTC:** 164 of 170 were wiped.
  - The 8-year, 5-year and last-year accounts were wiped on both.
  - In the gold crash of March 2026, all 8 fresh accounts were wiped within a month.
- **Every ladder close to the live bot failed.** That is 785 designs per symbol: your ladder, slot 5, and a bounded version with 3 adds and a stop. They covered all nine of your points.
  - **None of the 785 had a positive average** over 22 test quarters, on either symbol.
- **What survived is not a DCA ladder.** It is the V3-lite frame with a single add. That frame has:
  - entries on H1 votes only, and only in the direction of the H1 trend;
  - a stop and a target sized by volatility;
  - no force-close, and a 4-hour pause after a loss.

### The closest things to a working ladder (none passes)

| Design | Gold or BTC | How it differs from your live bot | Profit per week per $2,000 bot (median; bad year = 10th percentile) | Worst drop (median account's worst) | Accounts wiped | Fails |
|---|---|---|---|---|---|---|
| **G1**: the walk-forward pick | gold | V3-lite frame, stop 12 volatility units (vol units), one 1-unit add on an M2 MACD turn at least 1 vol unit away. The unit is sized so the full ladder risks 30% of the balance ("pre-funded") | **+$54** (bad year −$2) | **83%** (57%) | 0 of 170 (0 of 384 in the 8-timing check) | S2 drawdown, S7 long accounts, S9 haircut |
| **G5**: the most robust of the gold top 5 | gold | the same frame, one add on an M2 MACD turn, no adds while ADX(14, H1) > 30, always 1 unit (0.01 lot) | +$6 (−$1) | 64% (12%) | 0 of 170 | S2 (59% on F4), S9 |
| **B1**: BTC's best by score | BTC | the same frame, only on the Donchian(H4) breakout side, up to 3 flat adds on a Bollinger %B extreme (H4), pre-funded unit | +$11 (−$2) | 40% (27%) | 0 of 170 | S8: adds in only 7% of baskets, and without them it made more; S9 |
| **B2** | BTC | the same, one add on an H4 RSI + MACD turn, volatility-sized unit | +$3 (+$1) | 22% (8%) | 0 of 170 | S8 (adds in 2% of baskets; no-add twin better), S9 |
| *For comparison:* V3-lite with **no ladder** (V3, on `demo_hedging_xauusd6`) | gold / BTC | no ladder at all | gold +$5 (+$1); BTC +$1 (−$1) | gold 45% (9%); BTC 19% (8%) | 0 / 0 | not a ladder |
| *For comparison:* V3L, gold **Top 1** (one add, your unit rule; on `demo_hedging_xauusd8`) | gold / BTC | as G1, but stop 8, add on M5, your unit rule | gold +$5 (−$4); BTC −$0 (−$6) | gold 42% (18%); BTC 34% (14%) | 0 / 0 | - |
| Your live bot (L0) | both | - | −$38 (the whole $2,000 lost within the year) | 100% | 170 of 170 / 169 of 170 | everything |
| Slot 5 (L5) | both | - | −$38 | 100% | 170 of 170 / 164 of 170 | everything |

**How to read the "per week" column.** It is the median 12-month dollar result, divided by 52, over all 85 start months and
2 loop timings. Gold's last two years (Nov 2024 to Nov 2026) were an exceptional trend. In those years even V3 with no ladder
made +154% a year, so every gold figure above is flattered by them.

**What I recommend.**
- No ladder design may go to live money (PREREG §5.5 item 7).
- **Stop the live v3.9.2 bot and slot 5 on real money, on both symbols.** In this test both wiped virtually every account.
- If you want to keep a ladder in the demo test, **gold Top 1 (V3L) is already running on `demo_hedging_xauusd8`**. It is the
  nearest thing to a ladder that did not blow up. Its single add helped on gold per unit (+$4,032 against +$2,848 without it on F4),
  but it did not help in the walk-forward test, and on BTC it loses.
- **G5 is the only new design worth a demo slot**, as an experiment and not as a pass. It never wiped, it carries over to BTC
  (0 of 96 wiped, 17% worst drop, +27% on BTC's last two years), and it is closest to the live demo code. But it fell 66% in
  the January-February 2026 gold crash (§2.5).

## 2. Stress tests of the survivors (the top 5 per symbol, plus the live bot, slot 5, V3L and V3)

The top 5 are the first five of the search's pool, ranked by the pre-registered score.
- **Gold:** G1 `V3L|STOP=ST3|GRAN=T12|SIZING=Z1` (the walk-forward pick); G2 `V3L|FC=FC5|TRIG-3RD=X-stoch|SIZING=Z1`;
  G3 `V3L|CONFIRM=C5|SIZING=Z1`; G4 `V3L|CONFIRM=C5|SIDE=S7|TIERS=T8|GRAN=T12`; G5 `V3L|GRAN=T12|GATE=GT5|SIZING=Z3`.
- **BTC:** B1 `V3L|CONFIRM=C9|TIERS=T11|DEPTH=D3|SIZE=flat|TRIG-3RD=X-bb|SIZING=Z1`; B2 `…|TRIG-MACD=M4|GAP=G0.5|SIZING=Z2`;
  B3 `…|DEPTH=D2|SIZE=flat|GAP=Ggeo1.5|SIZING=Z1`; B4 `V3L|CONFIRM=C11|TIERS=T11|SIZE=flat|GATE=GT5|SIZING=Z2` (WF1 pick);
  B5 `V3L|CONFIRM=C11|TIERS=T11|SIZE=plus1|SIZING=Z2` (WF2 / WF3 pick).
- **Sizing codes:** Z1 = pre-funded unit (30% risk), Z2 = volatility-sized unit, Z3 = 1 unit always, otherwise your unit rule.

### 2.1 Every fresh 12-month start ($2,000, bot sizing, ticks, loop timings 1-2; 85 starts, 170 accounts)

Returns are % over 12 months. Wiped = stopped out, or equity at or below $200 at any time.

| | wiped | worst DD | median DD | mean | median | 10th pct | worst | quarters > 0 |
|---|---|---|---|---|---|---|---|---|
| G1 | 0 | 83% | 57% | +158% | +141% | −4% | −65% | 71% |
| G2 | 0 | 85% | 60% | +103% | +51% | −40% | −72% | 59% |
| G3 | 0 | 89% | 57% | +269% | +108% | −52% | −85% | 61% |
| G4 | 0 | 90% | 21% | +27% | +18% | −6% | −72% | 60% |
| G5 | 0 | 64% | 12% | +18% | +16% | −2% | −19% | 67% |
| L0 gold | **170** | 100% | 100% | −100% | −100% | −100% | −100% | 3% |
| L5 gold | **170** | 100% | 100% | −100% | −100% | −100% | −100% | 2% |
| V3L gold | 0 | 42% | 18% | +47% | +12% | −10% | −30% | 63% |
| V3 gold | 0 | 45% | 9% | +34% | +12% | **+2%** | −4% | **78%** |
| B1 | 0 | 40% | 27% | +32% | +29% | −4% | −19% | 62% |
| B2 | 0 | 22% | 8% | +9% | +8% | +2% | −2% | 71% |
| B3 | 0 | 59% | 31% | +33% | +24% | −13% | −36% | 60% |
| B4 | 0 | 21% | 8% | +4% | +4% | −1% | −13% | 59% |
| B5 | 0 | 18% | 8% | +4% | +4% | −3% | −10% | 61% |
| L0 BTC | **169** | 100% | 100% | −100% | −100% | −100% | −100% | 0% |
| L5 BTC | **164** | 100% | 100% | −99% | −100% | −100% | −100% | 0% |
| V3L BTC | 0 | 34% | 14% | −0% | −1% | −16% | −28% | 42% |
| V3 BTC | 0 | 19% | 8% | +5% | +3% | −3% | −14% | 55% |

### 2.2 The 8 loop timings (48 fold starts × 8 timings = 384 accounts) and the four two-year folds

Fold cells read "mean % a year / accounts wiped of 96". F1 runs from Nov 2018, F2 from Nov 2020, F3 from Nov 2022, F4 from Nov 2024.

| | wiped of 384 | timings with mean > 0 | range of the 8 timing means | F1 | F2 | F3 | F4 |
|---|---|---|---|---|---|---|---|
| G1 | 0 | 8 | +183 to +218 | +113 / 0 | +183 / 0 | +154 / 0 | +349 / 0 |
| G2 | 0 | 8 | +137 to +147 | +234 / 0 | +18 / 0 | +6 / 0 | +308 / 0 |
| G3 | 0 | 8 | +380 to +388 | +182 / 0 | **−33** / 0 | +126 / 0 | +1,266 / 0 |
| G4 | **2** | 8 | +19 to +27 | +9 / 0 | +25 / 0 | +13 / 0 | +46 / **2** |
| G5 | 0 | 8 | +15 to +17 | +16 / 0 | +2 / 0 | +10 / 0 | +35 / 0 |
| L0 / L5 gold | 384 / 383 | 0 | −100 | all wiped | | | |
| V3L / V3 gold | 0 / 0 | 8 / 8 | +69 to +75 / +46 to +47 | +17 / +8 | −8 / +5 | +6 / +20 | +277 / +154 |
| B1 | 0 | 8 | +30 to +33 | −3 / 0 | +11 / 0 | +55 / 0 | +64 / 0 |
| B2 | 0 | 8 | +9.1 to +9.7 | +1 / 0 | +7 / 0 | +9 / 0 | +21 / 0 |
| B3 | 0 | 8 | +26 to +29 | −3 / 0 | +8 / 0 | +69 / 0 | +36 / 0 |
| B4 / B5 | 0 / 0 | 8 / 8 | +2.1 to +2.2 / +1.2 to +1.9 | +4 / +3 | +2 / +3 | +4 / +4 | −1 / −3 |
| L0 / L5 BTC | 383 / 371 | 0 | −100 / −99 | all but 1 / 13 wiped | | | |
| V3L / V3 BTC | 0 / 0 | **0** / 8 | −3.0 to −2.4 / +4.2 to +4.9 | +1 / +1 | −18 / −5 | −8 / +3 | +14 / +19 |

The loop timing barely matters for the frame designs: the 8 timing means lie within a few points of each other.

### 2.3 Costs × 1.5 and the step-up sizing (29 quarterly starts, timing 1)

Cells read "wiped / worst DD / median % / mean %".
- **Aggressive:** a $1,500 step, i.e. 2 units at $2,000.
- **Cautious:** a $5,000 step.
- **For Z designs,** the same scaling is applied to their own knob: Z1 risk 50% / 15%, Z2 k × 5/3 / × 1/2, and Z3 2 units / not possible.

| | × 1.0, $2,500 | spread × 1.5 | aggressive | cautious |
|---|---|---|---|---|
| G1 | 0 / 83 / +160 / +162 | 0 / 84 / +97 / +138 | **1** / 95 / +165 / +210 | 0 / 54 / +101 / +91 |
| G2 | 0 / 83 / +60 / +109 | 0 / 83 / +27 / +94 | **1** / 95 / +90 / +131 | 0 / 55 / +39 / +71 |
| G3 | 0 / 88 / +108 / +276 | 0 / 88 / +99 / +270 | **3** / 100 / +113 / +309 | 0 / 60 / +64 / +116 |
| G4 | 0 / 86 / +16 / +32 | 0 / 85 / +12 / +18 | **1** / 96 / +33 / +43 | 0 / 53 / +25 / +30 |
| G5 | 0 / 64 / +14 / +16 | 0 / 64 / +14 / +15 | **1** / 100 / +29 / +30 | n/a |
| L0 / L5 gold | 29 / 29 wiped | 29 / 29 | 29 / 29 | 29 / 29 |
| V3L gold | 0 / 42 / +12 / +48 | 0 / 42 / +10 / +47 | 0 / 49 / +24 / +97 | 0 / 33 / +12 / +30 |
| V3 gold | 0 / 45 / +12 / +32 | 0 / 45 / +13 / +32 | 0 / 55 / +24 / +60 | 0 / 26 / +12 / +24 |
| B1 | 0 / 40 / +27 / +29 | 0 / 44 / +17 / +23 | 0 / 60 / +24 / +37 | 0 / 21 / +18 / +18 |
| B2 | 0 / 20 / +8.5 / +9.5 | 0 / 19 / +7.5 / +8.2 | 0 / 20 / +11 / +11 | 0 / 20 / +7.5 / +8.6 |
| B3 | 0 / 57 / +29 / +29 | 0 / 56 / +22 / +24 | 0 / 78 / +19 / +29 | 0 / 31 / +17 / +22 |
| B4 / B5 | 0 / 18 / +3.5 / +4.0 · 0 / 17 / +3.9 / +3.7 | +2.4 / +2.1 · +0.6 / +1.4 | +3.5 / +5.2 · +3.6 / +4.6 | +2.8 / +2.8 · +2.6 / +2.8 |
| L0 / L5 BTC | 29 / 28 wiped | 29 / 29 | 29 / 29 | 29 / 28 |
| V3L BTC | 0 / 34 / +1.4 / +0.4 | 0 / 37 / −2.6 / −2.1 | 0 / 52 / −0.8 / +0.6 | 0 / 34 / +1.4 / +0.8 |
| V3 BTC | 0 / 18 / +3.3 / +5.3 | 0 / 21 / +2.9 / +4.1 | 0 / 34 / +6.6 / +10 | 0 / 18 / +3.3 / +5.4 |

- **Every gold ladder design wipes accounts at the aggressive step** (1-3 of 29). The cautious step cuts the worst drop to 53-60% but no lower.
- **Neither step rescues the live bot or slot 5.** Every account was wiped at every step.

### 2.4 Cross-asset (each design on the other symbol's last two years, F4, 96 accounts)

Cells read "wiped / worst DD / mean / median / quarters > 0".
- **Gold designs on BTC:**
  - G1 **5 wiped** / 96% / +25 / **−23** / 52%;
  - G2 0 / 75% / +4 / −12 / 46%;
  - G3 0 / 72% / +15 / +7 / 57%;
  - G4 0 / 50% / +18 / +14 / 67%;
  - **G5 0 / 17% / +28 / +27 / 69%**.
- **BTC designs on gold:**
  - B1 0 / 49% / +65 / +69 / 79%;
  - B2 0 / 52% / +17 / +20 / 63%;
  - B3 0 / 50% / +104 / +109 / 80%;
  - B4 0 / 37% / +48 / +50 / 74%;
  - B5 0 / 38% / +51 / +54 / 89%.
  - All five made less than V3 with no ladder (+154%) on the same fold.

### 2.5 The worst events (a fresh $2,000 account opened about 10 days before, run 3-4 weeks after; 8 timings)

Cells read "wiped of 8 / worst DD / median %".

| Gold | COVID Mar 2020 | 11 Aug 2020 −5.9% | 21 Oct 2025 −6.1% | **30 Jan-5 Feb 2026** (−10.1%, 2 Feb 10% range) | Mar 2026 (5 days −11%) |
|---|---|---|---|---|---|
| G1 | 0 / 32 / +28 | 0 / 36 / +37 | 0 / 30 / +12 | 0 / 40 / +22 | 0 / 26 / +35 |
| G2 | 0 / 23 / +62 | 0 / 29 / +31 | 0 / 21 / +19 | 0 / 59 / −17 | 0 / 25 / +12 |
| G3 | 0 / 23 / +113 | 0 / 38 / +19 | 0 / 18 / +25 | 0 / 35 / +50 | 0 / 19 / +49 |
| G4 | 0 / 8 / +20 | 0 / 6 / +11 | 0 / 27 / −14 | 0 / 73 / −13 | 0 / 41 / +128 |
| G5 | 0 / 5 / +11 | 0 / 7 / +7 | 0 / 17 / −1 | 0 / **66** / **−46** | 0 / 23 / +27 |
| L0 | 0 / 86 / −59 | **4** / 96 / −64 | 0 / 56 / −4 | **2** / 107 / +9 | **5** / 101 / −83 |
| L5 | 0 / 62 / −59 | 0 / 18 / −6 | 0 / 19 / −6 | **5** / 101 / −29 | **8** / 101 / −100 |
| V3L | 0 / 7 / +11 | 0 / 10 / +2 | 0 / 11 / +13 | 0 / 39 / +3 | 0 / 32 / +15 |
| V3 | 0 / 7 / −1 | 0 / 6 / −0 | 0 / 7 / +14 | 0 / 45 / −8 | 0 / 12 / +16 |

| BTC | 12 Mar 2020 −38.8% | 19 May 2021 −14.3% | May-Jun 2022 (LUNA, Celsius) | 9 Nov 2022 FTX | 5 Feb 2026 −14.0% | 12 months from 13 Nov 2021 (the bear; 2 timings) |
|---|---|---|---|---|---|---|
| B1 | 0 / 11 / +8 | 0 / 10 / +11 | 0 / 10 / +26 | 0 / 8 / +10 | 0 / 12 / +16 | 0 / 29 / +34 |
| B2 | 0 / 1 / +3 | 0 / 6 / +10 | 0 / 4 / +3 | 0 / 1 / +3 | 0 / 5 / +8 | 0 / 6 / +7 |
| B3 | 0 / 10 / +12 | 0 / 20 / +9 | 0 / 12 / +57 | 0 / 8 / +12 | 0 / 17 / +26 | 0 / 30 / +74 |
| B4 / B5 | 0 / 2 / +3 | 0 / 7 / +5 | 0 / 4 / +6-7 | 0 / 1 / +0 | 0 / 5-6 / +6-10 | 0 / 7-8 / +1-2 |
| L0 | 0 / 18 / −12 | **8** / 101 / −100 | **8** / 100 / −100 | 0 / 30 / −26 | 0 / 82 / −69 | **2 of 2** wiped |
| L5 | 0 / 10 / −8 | **8** / 100 / −100 | 0 / 59 / −58 | 0 / 7 / −6 | 0 / 43 / −42 | **2 of 2** wiped |
| V3L | 0 / 1 / +0 | 0 / 10 / −1 | 0 / 6 / −1 | 0 / 3 / −3 | 0 / 6 / +5 | 0 / 21 / −17 |
| V3 | 0 / 1 / −0 | 0 / 9 / −2 | 0 / 3 / +6 | 0 / 1 / +1 | 0 / 7 / +1 | 0 / 8 / +5 |

- **The fixed-unit gold designs (G4, G5, V3, V3L) took their worst hits in the January-February 2026 crash.** G1-G3 size the unit by the D1 ATR, so the unit was already small when volatility spiked.
- **The live bot and slot 5 were wiped in a few weeks** in the May 2021 and May-June 2022 BTC falls, and in the March 2026 gold fall.

### 2.6 The pre-registered pass test (PREREG §5.1) on the clean fold F4, with the haircut

The verdict itself is decided by the walk-forward picks (G1, G2, B4, B5). This table applies the same test to every top-5 design, for information.

| | S1 survival | S2 DD ≤ 50% | S3 profit | S4 quarters | S5 r/DD | S6 timings | S7 8y / 5y / 1y | S8 it is a ladder | S9 DSR ≥ 0.95 | passed |
|---|---|---|---|---|---|---|---|---|---|---|
| G1 | ✓ | ✗ 66% | ✓ | ✓ 79% | ✓ | ✓ | ✗ 8y DD 75% | ✓ | ✗ 0.008 | 6 / 9 |
| G2 | ✓ | ✗ 62% | ✓ | ✓ 87% | ✓ | ✓ | ✗ 5y DD 67% | ✓ | ✗ 0.005 | 6 / 9 |
| G3 | ✓ | ✗ 52% | ✓ | ✓ 91% | ✓ | ✓ | ✗ 8y DD 73%, 5y 83% | ✓ | ✗ 0.11 | 6 / 9 |
| G4 | ✗ 2 wiped | ✗ 95% | ✓ | ✗ 57% | ✗ | ✗ | ✗ | ✗ twin better | ✗ 0.006 | 1 / 9 |
| G5 | ✓ | ✗ 59% | ✓ +35% | ✓ 80% | ✓ 0.68 | ✓ | ✓ 8y +$2,120 DD 31%, 5y +$1,329 DD 36% | ✓ +35 vs +27 | ✗ 0.0002 | **7 / 9** |
| B1 | ✓ | ✓ 39% | ✓ +64% | ✓ 73% | ✓ 1.85 | ✓ | ✓ 8y +$5,851 DD 42% | ✗ adds 7%; twin +217% | ✗ 4e-7 | 7 / 9 |
| B2 | ✓ | ✓ 22% | ✓ +21% | ✓ 65% | ✓ 1.88 | ✓ | ✓ 8y +$1,419 DD 14% | ✗ adds 2%; twin +24% | ✗ 1e-6 | 7 / 9 |
| B3 | ✓ | ✗ 57% | ✓ | ✓ 66% | ✓ | ✓ | ✗ 8y DD 54% | ✗ twin +217% | ✗ 7e-8 | 5 / 9 |
| B4 | ✓ | ✓ 21% | ✗ −1.2% | ✗ 54% | ✗ | ✗ | ✓ | ✗ | ✗ | 3 / 9 |
| B5 | ✓ | ✓ 18% | ✗ −3.2% | ✗ 55% | ✗ | ✗ | ✓ | ✗ | ✗ | 3 / 9 |

- **Haircut (S9).** S9 corrects for having tried 1,493 gold designs and 1,168 BTC designs (and 1,200 before this study).
  - After that correction, no design's per-unit Sharpe ratio is distinguishable from luck. The best, G3, scored 0.11 against the 0.95 needed.
- **On BTC the "ladder" adds nothing.** B1 and B2 pass everything except S8 and S9, but their adds act in 2-7% of baskets. The same designs with no add made more (B1 / B3 twin +217%, B2 twin +24%).
- **Per unit (the edge without the sizing), the gold picks are no better than the references.** On F4: G1 +$2,708, G2 +$1,998, G3 +$4,459, G5 +$637, against V3 +$2,848 and V3L +$4,032.

## 3. Your nine points, one by one

Cells read "accounts wiped of 22 test quarters / mean % per quarter" on your live bot (L0), gold first and then BTC.
- **The live baseline:** gold 4 / −54.0, BTC 9 / −67.2.
- **None of the 785 L0 / L5 / LB designs had a positive mean on either symbol.** "Helped" below therefore means "lost less".
- Sources: SEARCH files §5 (stage A) and stage D, which re-ran each best level on F4.

**1-3. Ladder sizes**

| Shape | Gold | BTC | Effect |
|---|---|---|---|
| flat (1,1,1,…) | 2 / −29.4 | 6 / −43.9 | the least bad |
| +1 (1,2,3,…) | 4 / −49.3 | 7 / −60.1 | worse |
| Fibonacci (live) | 4 / −54.0 | 9 / −67.2 | baseline |
| doubling | 7 / −67.1 | 13 / −82.4 | the worst |

- Owner grid (132 designs of shape × tiers × trigger): **0 positive** on either symbol.
- On F4, flat still wiped 8 of 10 accounts on both symbols.

**4. Tier timeframes (longer, shorter, D1, W1)**

| Tiers | Gold | BTC |
|---|---|---|
| shorter [M5, M15, H1] | **2 / −32.8** (best) | 6 / −48 |
| + D1 | 4 / −47 to −59 | 8 / −71 |
| + D1, W1 | 6 / −57 | 10 / −75 |
| one timeframe repeated 5 times | 12-22 (all adds fire at once) | 12-18 |

- Fewer and slower adds lose less. D1 and W1 tiers did not help.

**5. Granularity (M2-M20, H2-H12)**

| Tiers | Gold | BTC |
|---|---|---|
| M2-M20 | 6 / −63 | 12 |
| M10-H6 | 6 / −63 | 10 |
| M30-H12 | 17 / −90 | 18 |
| 9 tiers | 18 / −86 | **22 of 22** |
| M6, M12, M20, H3, H8 | 4 / −52 | 8 |

- **M2 as the single add** of the V3-lite frame is the one granularity effect that survived: it is in G1 and G5.

**6. MACD instead of RSI**

| Trigger | Gold | BTC |
|---|---|---|
| MACD turn | 4 / −56 | 8 / −65 |
| MACD histogram | **20 / −96** | 16 / −92 |
| MACD cross | 4 / −56 | 8 / −68 |
| RSI and MACD turn together | **2 / −33** | 6 / −48 |

- In the V3-lite frame the add is already a MACD turn; that is what survives.

**7. A third indicator as the trigger**

| Trigger | Gold | BTC |
|---|---|---|
| Stochastic | 4 / −57 | 8 |
| Williams %R | 12 / −80 | 12 |
| CCI | 5 / −66 | 10 |
| Bollinger %B | **2 / −36** | 8 |
| EMA distance / ATR | 4 / −36 | **6 / −45** |
| RSI(2) | 4 / −63 | 10 |

- No trigger made a multi-add ladder earn.
- In the V3-lite frame, a Stochastic add (G2, gold) and a %B add (B1, BTC) are in the top 5.

**8. Switching sides**

| Side mode | Gold | BTC |
|---|---|---|
| only with the H4 trend | 1 / −27 | 3 / −39 |
| against the trend | 4 / −39 | 6 |
| counter-ladder | **2 / −25** | 4 / −36 |
| stop-and-reverse | 4 / −57 (× 2: 6 / −65) | 12 / −77 |
| **hedge ladder at depth** | **7 / −78** | **12 / −84** |

- An opposite-side (hedge) ladder when under water was the worst side mode on both symbols.
- Stop-and-reverse in the V3-lite frame (G4) is the only gold top-5 design that wiped accounts (2 on F4) and fell 95%.

**9. The agents' brainstorm**

| Lever | Gold | BTC |
|---|---|---|
| RSI 20 / 80 trigger | **0 / −18.5** (best single L0 change; it almost never adds) | **0 / −27.8** |
| gap of 2 vol units between adds | 0 / −19.8 | 2 / −32 |
| adds only with the H1 trend | 0 / −22.5 | 3 / −35 |
| maximum depth 1 | 2 / −33 | 6 / −44 |
| maximum depth 8 / 12 | 16 / 21 | 17 / 22 |
| basket stops in vol units | 4-7 / −72 to −79 (floating losses become realised) | 10-12 |
| % equity stops | 4 / −54 to −62 | 8-9 |
| time stops (incl. 24 h once 3 deep) | no effect (4 / −54.8) | no effect (9 / −67.2) |
| break-even exit once 3 deep | 4 / −50.0 | 8 / −66.3 |
| LIFO / overlap partial closes | 4 / −56.4, 4 / −52.7 | 10 / −71.1, 8 / −68.6 |
| no adds while ADX(14, H1) > 30 | 4 / −43.9 | 6 / −47.7 |
| abnormal-day pause for adds | 4 / −51.1 | 6 / −60.6 |
| no adds 20:30-22:30 UTC (rollover) | 4 / −49.6 | 8 / −65.7 |
| flat over the weekend (Fri 20:00 to Mon 01:00) | 4 / −54.4 | 6 / −58.4 (the best LB single, −8.0%) |

- **The pre-funded unit (Z1)** multiplies V3-lite-frame returns about 9 times and its drawdowns about 6 times. That is leverage, not edge.

**Entries**

| Entry set | Gold | BTC |
|---|---|---|
| {H4, M5} (what you believe is live) | 4 / −46.8 | 7 / −55 |
| {H1, M15} (live) | 4 / −54.0 | 9 / −67.2 |
| {H1, M15, D1}, entry 2 | 6 / −61 | 10 / −71 |
| {H1, M15, D1}, entry 4 | 2 / −34 | 6 / −46 |
| {H4, M5, D1}, entry 4 | **0 / −23** | **4 / −37** |
| H1 alone (as in V3-lite) | 4 / −44 | 6 |
| no entry agreement | 5 / −63 | 12 / −79 |

- **RSI plus a second indicator:** trend gates remove most wipes, but the ladder still loses about 20-30% a quarter.
  - Gold: EMA50 (H4) side 0 / −20, Supertrend (H4) 0 / −20, Donchian (H4) 0 / −21.
  - BTC: EMA50 (H4) 0 / −25, Supertrend 0 / −29, Donchian 0 / −33.
  - ADX and oscillator zones were less helpful.

**Exits**

| Force-close timeframe | Gold | BTC |
|---|---|---|
| M15 (live) | 4 | 9 |
| H1 | 8 | 10 |
| H4 | 6 | 8 |
| D1 | 4 | 10 |
| off | 13 | 12 |

- Your RSI force-close: 4 / −56 on gold.
- The H6 final close: 6 / −70 on gold, 10 on BTC.
- Targets of $0.5 to $10: none positive.
- **Only the V3-lite combination survives:** a stop and target in vol units, with force-close off.

**The slot-5 variant (flat 1,1,1,1,1,1 with an H4 force-close)**

| | Gold | BTC |
|---|---|---|
| 22 test quarters | 4 wiped, −53.2% | 8 wiped |
| one-year accounts, 2018-2024 | 288 of 288 wiped | 275 of 288 wiped |
| one-year accounts, 2024-26 | 95 of 96 wiped | 96 of 96 wiped |
| every start | 170 of 170 wiped | 164 of 170 wiped |
| 8-year / 5-year / last year | all wiped | all wiped |
| 184-quarter anchor | 181 lost | 184 of 184 lost |

- Its best single change still loses: on gold, {H4, M5, D1} with entry 4 (0 wiped, −11.3%); on BTC, the {H4, M5} entries (0 wiped, −20.2%).

## 4. What the bot would need to run each candidate

The demo branches (`demo_hedging_xauusd6/7/8`) already carry the V3-lite levers in `constants.py` design blocks. These are:
`OPEN_SCORE_WEIGHTS`, `ENTRY_AGREE_S`, `FORCE_CLOSE_ENABLED`, `TREND_TF`, `VOL_TF`, `VOL_LEN`, `TARGET_VOL`, `STOP_VOL`, `LOSS_COOLDOWN_S`,
`MAX_ADDS`, `LADDER_TRIGGER`, `LADDER_TFS`, `LADDER_GAP_VOL`, `LADDER_MULTIPLIERS`, plus the `step_up_balance` key in `symbols.json`.
The live v3.9.2 branches (`hedging_*`) have none of these levers. Running any candidate there means porting the demo code first.

| Candidate | Starting point | Settings only | New code |
|---|---|---|---|
| **V3L (gold Top 1)** | already on `demo_hedging_xauusd8` | - | none |
| **G5** | the `xau_top1` block | `LADDER_TFS = ['M2', …]`; a fixed 1 unit (a very large `step_up_balance` in `symbols.json`, so the unit stays 1) | an ADX(14, H1) gate on the last closed bar: no add while ADX > 30 |
| **G1** (walk-forward pick) | the `xau_top1` block | `STOP_VOL = 12.0`, `LADDER_TFS = ['M2', …]` | the pre-funded unit: the largest unit whose full ladder, filled one gap apart and then a further 1.5 × ATR(14, D1), loses at most 30% of the balance |
| B1 / B2 | the `btc_top2` block | Donchian / MACD-D1 side gates, H4 tiers, gaps | the Donchian(H4) side gate, %B or RSI + MACD add triggers, and the Z1 / Z2 units |

I have not checked these against the demo code poll by poll. None passed, so no parity work was started.

## 5. Caveats

- **All data has been seen before.** Every year from 2016 to 2026 of both symbols had been read by earlier studies.
  - F4 (Nov 2024 to Nov 2026) is clean for this study only.
  - On gold, F4 was an exceptional trend: V3 with no ladder made +154% a year there.
- **Many designs were tried.** 1,493 on gold and 1,168 on BTC in this study, and about 1,200 before it. The haircut (§2.6) accounts for this.
- **The engine is a model.** It is a tick-level replay parity-proved against the live `app.py`, but:
  - stops and targets are checked only on live polls;
  - swaps are 0;
  - the 8-year and 5-year accounts are one per-second replay each.
- **Some runs were cut to save machine time** (DEVIATIONS T2-T4):
  - the 36 extra start months used 2 loop timings, not 8;
  - the × 1.5 cost and step-sizing runs used quarterly starts with one timing.
- **Not yet done:** the independent rebuild of the best failing pick (PREREG §7 step 10).
- **The demo account is the real test.** None of this proves a design will work live.

## 6. Run counts, time, files

- **The searches:** 53,931 gold and 51,173 BTC account runs, plus 9,936 in the gold shadow stage, about 45 h of wall time.
- **This stress step:** about 4,900 runs on 8 workers, 2 h 04 min.
  - It repeated 116 rows by mistake. They matched the search rows to the cent, which checks that the runs are deterministic.
- **Files:** `stress/` (`gap_*`, `events_*`, `s15_*`, `steps_*`, `twinF4_*`, `xasset_*`, `cont_*_BTC`, `unitF4_XAU/`, `TABLES.md`,
  `stress_summary.json`).
  - The scripts are `stress.py` and `analyze.py` in the scratch folder `port_tmp/ladder/stress/`.
  - Rule notes are T1-T9 in `DEVIATIONS.md`.
