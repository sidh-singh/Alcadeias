# Session Hunter (TradeIQ): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values, event counts and timings.
No Session Hunter rule has been run for profit or loss, and no exit of the script's own trade manager was looked at
on real data.

- **The code:** `backtesting/research/tradeiq2_ind_session.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_session.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_session.py`: the reconciliation (48 tests, about 3.3 minutes, at most 1.7 GB);
  - `tests/test_tradeiq2_ind_session_a.py` and `tests/test_tradeiq2_ind_session_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.6, and claim 10 of section 8.
- **The script:** "Session Hunter [TradeIQ]", Pine v6, MPL-2.0, 535 lines. It is third-party code. Line numbers
  (L...) refer to the owner's copy. The source is not in this repository.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- On the M5 and M15 bars of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports give the
  same numbers, bit for bit, on every series the setups read and on every signal of every configuration the plan
  runs. The script's own exits, in its three exit modes, agree as well (compared for equality only). No tolerance was
  needed anywhere, and no number of either port changed on the study's bars.
- The same holds on the claim markets (USTECm M5 and M15, EURUSDm and GBPUSDm M15) and on random charts built to hit
  the rare branches.
- What differed was the contract (the names and labels of the exit columns, and which odd inputs are refused) and one
  Pine reading: whether the chart's very first bar starts a new trading day. Both are settled (section 4). The
  reading cannot change anything on the study's bars, because both symbols' data start on a weekend day.
- An unreviewed probe written to plan the study gives the same session ranges and the same Sunday count, once its
  own choice of days is applied (section 5).
- Three readings add to the plan and are proposed for `DEVIATIONS.md` (section 8): how much 1H history the script's
  EMA200 is computed on, how the information-only Monday variant is built, and from which price E3's "less than 1R
  away" is measured. The last one is material for the E3 rows.

## 1. What the script computes

All settings are the script's defaults (L50-82); nothing is tuned.

**The clock.** Everything runs on New York time, with daylight saving.
- A trading day runs from 20:00 to 20:00 New York and is named after the calendar day it ends on. So the Asian
  session of 20:00-24:00 belongs to the next day (L129-130).
- Only Monday to Friday days trade (L131-132). Gold's Sunday 18:05-20:00 bars, and BTC's whole Saturday and Sunday,
  form days of their own that never trade.
- A bar belongs to a session or window only when the whole bar is inside it (L134). The 16:00-20:00 "close" period is
  decided by the bar's open alone (L140).

**The levels.**
- Asia high and low (20:00-24:00), the London kill zone high and low (02:00-05:00), and the opening range (09:30-10:00,
  only on charts below 1H). Each is final on the first bar after its session.
- Yesterday's high, low, open and close: those of the previous trading day, if it was a weekday (L190-199).
- The midnight open (the first bar from 00:00) and the average range of the last 10 weekdays (once there are 5).

**The five setups.** Each runs on its own, at most once a day.
- AS fades a sweep of the Asian range in 02:00-05:00; LS fades a sweep of the London range in 07:00-11:00; PD fades a
  sweep of yesterday's high or low in 02:00-11:00; AB follows a breakout of the Asian range in 02:00-05:00; OR follows
  a breakout of the opening range in 10:00-12:00.
- A fade (L331-347): price trades beyond the level (the sweep), then a bar closes back inside the range: the signal
  is against the sweep. If both sides are swept first, the setup is dead for the day. A bar that fails the
  confirmations does not end the setup. The sweep and the close back inside can be on different bars.
- A breakout (L350-358): the first close beyond the range that passes the confirmations. If that close is more than
  4 ATR from the middle of the range, the day ends without a trade.

**The confirmations** (L312-328). All the ticked ones must hold:
- FVG: a fair-value gap in the trade's direction in any of the last four three-bar groups;
- MSS: the close beyond the previous five bars;
- HTF: the close on the trade's side of the 1H EMA200;
- PD: a long below the midnight open, a short above it;
- RV: volume at least 1.5 times its 20-bar average;
- TIGHT: the range under half the average day;
- YC: yesterday's candle pointing the trade's way.

The plan's sets are K0 (none), K1 (FVG), K2 (FVG + HTF, the default) and K3 (FVG + MSS, the Forex preset).

**The trade** (L399-492).
- The stop is the sweep's extreme for a fade, or the middle of the range for a breakout. If that is closer than
  0.5 ATR to the signal bar's close, it moves to 0.5 ATR from that close.
- The entry is the next bar's open. It is cancelled if that bar opens at or after 16:00, starts a new day, or opens at
  or beyond the stop.
- Exits, in the script's order: a new day (at the last close), the first bar from 16:00 (at its open), the stop, the
  target. The three exit modes the plan uses: hold to 16:00 (E1), a 2R target (E2), and the far side of the range
  (E3, cancelled when it is less than 1R away).

**The Monday quirk.** Gold's short Sunday session (from about 18:05 to 20:00 New York) and BTC's weekend are days of
their own, and they are not weekdays. So on Monday "the previous day was a weekday" is false, and Monday never trades
the previous-day setup (PD) or the YC confirmation. The plan keeps this as coded; a variant that gives Monday
Friday's levels is information only.

## 2. What was compared, and how

**The bars.** Exactly what the study uses, from `tradeiq2_market.load(symbol, end="2024-07-01")`, with both studies'
hold-out guards pointed at empty folders:

| | Gold | BTC |
|---|---|---|
| First bar | Sunday 2016-01-03 18:00 New York | Sunday 2017-12-31 19:00 New York (2018-01-01 00:00 UTC) |
| Last bar closes | 2024-07-01 00:00 UTC | 2024-07-01 00:00 UTC |
| M5 / M15 bars | 596,786 / 199,192 | 681,121 / 227,123 |
| 1H bars for the EMA200 (before 2019) | 49,956 (17,564) | 56,840 (8,721) |

**What had to be equal.** Integers, booleans and labels exactly; every float bit for bit (NaN in the same places,
every other value equal, and even the sign of a zero).

1. **The 1H EMA200** at each chart bar's open, with either `ta.ema` seed, and its direction.
2. **Every per-bar series the setups read** (36 series on every bar): the clock (minute, day, weekday, new day,
   session membership, the 16:00-20:00 period), ATR(14), the volume average, the FVG flags, the five-bar high and
   low, yesterday's levels, the weekday flags, the midnight open, the average range, the three sessions' levels and
   done flags, and each setup's signal.
3. **The event tables**: one row per signal with setup, bar, time, direction, stop, target reference, range, entry
   bar, the cancel at entry, and the script's own exits in its three exit modes.

**The configurations**, on both symbols and both timeframes:
- K0, K1, K2 and K3 with all five setups. The three presets are subsets of these rows, and each setup alone gives
  its own rows: checked on port A.
- K2 with the Monday variant, and K2 with the 1H EMA replaced by the study's F2-4H, F2-1D and F3 filters.
- Beyond the grid: RV on the study's volume (gold tick volume, BTC Binance BTCUSDT 5m volume), all seven
  confirmations at once, and reading R1's alternative in port B.

In all, about 133,000 signal rows were compared.

**More checks.**
- The claim markets of claim 10: the Nasdaq preset and PD + HTF on USTECm M5 and M15, and the Forex preset on EURUSDm
  and GBPUSDm M15, with every per-bar series, from their data start to 2024-06-30.
- Four random charts from port A's tests: gold's and BTC's schedules, M5, M15 and 1H, both 2019 daylight-saving
  changes, holes, opening gaps, ties. Edits on them force every cancel at entry and a new-day exit. Each was run with
  nine confirmation sets, the Monday variant, a 1.25 ATR minimum stop and a subset of setups.
- The contract: the same names, constants, columns, dtypes, defaults and refused inputs.

**The exits on real bars were compared for equality only.** Their prices, reasons and R values were never printed,
counted, summed or otherwise looked at. A failing assertion names a column and a number of rows, never a value.

## 3. The Pine readings, with their evidence

Readings where the source leaves a choice, and what both ports now do. "Effect" is measured on the study's bars.

| # | Question | Both ports | Evidence | Effect on our bars |
|---|---|---|---|---|
| R1 | Is the chart's first bar a new day? (L133: the day before bar 0 is missing) | No: a comparison with a missing value is false | Study 1's rule for every such comparison, and the other study-2 ports'. TradingView's manual only warns against such comparisons | None: both data starts are a weekend day, which never becomes "yesterday". On bars that start on 2019-01-01 the other reading adds one BTC PD signal (2019-01-01) |
| R2 | How `ta.ema` starts (L145) | From its first value | Study 1's reading | None: the other start gives the same htfE, bit for bit, from 2019 |
| R3 | `ta.highest(high, 5)` before five bars exist (L148, L152) | Missing | Pine's rule for windowed functions | Bars 0-4 only |
| R4 | The average range (L211) | Ranges added oldest first, then divided | The array's order | None: no planned row uses TIGHT |
| R5 | ATR and the volume average (L143-144) | Study 1's verified order of arithmetic (TradingView's "same on Pine" code) | Study 1's two ports agreed on it bit for bit | Bit-identical in both ports |
| R6 | When the 1H EMA is read (L145, `[1]` with `lookahead_on`) | The last 1H bar closed at or before the chart bar's open | PREREG 6.6; the map, 2.2 | Fixed by the plan |
| R7 | How much 1H history the EMA sees (L145) | Every 1H bar from the data start | The longest history is the closest to converged | Against 1H bars cut at 2019-01-02, 5-10 K2 signals per chart differ, all in January 2019 (section 8) |
| R8 | Window membership (L134-140) | The whole bar inside the window; the 16:00 rule by the bar's open; OR only below 1H | The source | The plan's reading |
| R9 | The Monday quirk (L199, L327, L362) | As coded | The source | pWk is false on 280 of 286 gold Mondays and on all 286 BTC Mondays (2019-01-07 to 2024-06-24) |
| R10 | The Monday variant (information only) | Monday, like every weekday, reads the last finished weekday | The shortest change that gives Monday Friday's levels | K2 PD signals: gold 234 / 193, BTC 147 / 116 (M5 / M15), against 188 / 158 and 117 / 93 (section 8) |
| R11 | Labels when two cancels hold at once (L428, L433) | The first in the source: 'closeT' before 'new_day', 'risk<=0' before 'open_beyond_stop' | The order of the source | Labels only: the trade is dropped either way |
| R12 | Where a new-day exit is booked (L454-455) | On the new day's first bar, at the previous bar's close | The script books it there | A representation only |
| R13 | Pine v6 booleans and lazy evaluation (L225-227, L360-364) | A boolean of the bar before bar 0 is false; a switched-off setup is never evaluated | Pine v6 | None |
| R14 | The `dead` flag (L340-341) | As coded | The source | Redundant: once both sides are swept, no close can count again that day |
| R15 | Comparisons with a missing ATR (the first 13 bars, L356, L401) | False: the minimum stop is not applied, and a breakout ends the day without a signal | The same rule as R1 | First bars only |
| R16 | The HTF confirmation as a direction (L319) | Passes when the direction equals the trade's; 0 or missing fails both sides | "not na(htfE) and dd * (close - htfE) > 0" | Equivalent. F2 / F3 enter as "long allowed minus short allowed" |
| R17 | Volume for RV (L144, L323) | Whatever the caller passes: the study's is gold ticks and BTC Binance | PREREG 2 | No planned row uses RV |

**The arithmetic.** Both ports follow the source's order, so their floats agree bit for bit:
- stop = close - (dd x minStop) x ATR;
- target reference = side + dd x (rH - rL);
- the middle = (rH + rL) / 2;
- the 2R target = open + (d x 2) x risk;
- R = (d x (x - e) - 2 x 0) / risk.

Nothing had to be reordered: no two numbers differed even in the last bit.

**R1 in more detail.** Port B was written with the opposite reading. It treated a missing value like a computer's
"not a number", for which "not equal" is true. Then the partial first day is a day of its own and can be
"yesterday". TradingView's reference does not say what such a comparison gives. Study 1 and every other study-2 port
read all comparisons with a missing value as false, so port B now does too. Port B keeps the other reading as an
option (`first_bar_new_day=True`) to measure it.

On the study's bars the two readings give the same value of every series the setups read, and the same rows. This
is tested on both symbols and both timeframes. Only the first bar's new-day flag and the first day's running
high, low and open differ, and nothing reads those before the day ends.

On a TradingView chart the first bar is wherever the loaded history begins, so this reading can only touch the
first day or two of any chart.

## 4. Mismatches found, and how each was resolved

No number differed. These were the differences.

| # | What | Port A | Port B | Resolution |
|---|---|---|---|---|
| 1 | Reading R1: the first bar is a new day | No | Yes | Port A's reading (port B changed). The evidence is in section 3. It changes nothing on the study's bars |
| 2 | The exit columns' names | `exit_price_<m>`, `exit_reason_<m>` | `exit_px_<m>`, `reason_<m>` | Port A's names (port B changed) |
| 3 | The label when no exit exists yet | 'open' (entered, still open), 'pending' (no entry bar yet) | None for both | Port A's labels (port B changed): a cancelled trade, a pending one and an open one are now told apart |
| 4 | The label for E3's own cancel (L437) | 'cancel_lt_1R' | 'tgt<1R' | Port A's (port B changed) |
| 5 | The order of the cancel labels in `CANCELS` | closeT, new_day, open_beyond_stop, risk<=0 | closeT, new_day, risk<=0, open_beyond_stop | Port A's order (port B changed) |
| 6 | A minimum stop of 0 | Accepted | Refused | Refused in both. The script's input cannot go below 0.1 (L81). Port A changed, and one hand test now uses 0.1 |
| 7 | A single string as the list of setups or confirmations | Refused | Taken as one name | Refused in both (port B changed): "FVG" is not a list of names |
| 8 | No volume, or no 1H direction, when nothing reads them | Allowed | Refused | Allowed in both (port B changed). Missing ones are still refused when RV or HTF needs them |
| 9 | Prices that are not finite | Refused | Not checked | Refused in both (port B changed) |
| 10 | What can be compared | Port A did not expose the EMA values or its shared series | | Port A now exposes `htf_ema` and `shared_series`, which its own code uses. Port B gained `htf_ema` (its `htf_ema_at_open`) and a `length` on `htf_ema_dir` |

The port tests were changed for these contract changes only:
- port B's tests now expect R1's reading (three places), port A's names and labels, and the new refused inputs;
- port A's tests use a 0.1 minimum stop where they used 0, and check the new refused inputs.

## 5. A third opinion: the probes of the planning pass

The planning folder (`study2/work`, read-only, never imported by the repository) has no Session Hunter signal port.
It has `probe_sessions.py`, which measured the session clock and session ranges from M1 bars with its own code. It
was run as it is, from 2019-01-01 to 2024-06-30. Its figures were then compared with the levels the reconciled port
gives the setups.

| | Probe | Reconciled port, the probe's days | Reconciled port, the script's days |
|---|---|---|---|
| Gold opening range: days, median | 1,416, $5.994 | 1,416, $5.9945 | 1,416, $5.9945 |
| Gold London range | 1,417, $7.169 | 1,417, $7.169 | 1,417, $7.169 |
| Gold Asia range | 1,134, $6.226 | 1,134, $6.2265 | 1,416, $6.43 |
| BTC opening range | 1,432, $179.685 | 1,432, $179.685 | 1,433, $179.12 |
| BTC London range | 1,433, $274.63 | 1,433, $274.63 | 1,434, $273.535 |
| BTC Asia range | 1,434, $299.415 | 1,434, $299.415 | 1,434, $333.765 |
| Gold Sundays with bars; with a bar before 20:00 | 283; 281 (99.3%), the first at a median 18:05 | 283; 281, median 18:05 | |
| BTC Sundays with bars; with a bar before 20:00 | 287; 287 | 287; 287 | |

**The differences are only in which days are counted.**
- The probe dates a session by its calendar day and keeps Monday-Friday calendar days with at least 80% of the
  session's minutes. With those days, the port gives the probe's figures exactly. The probe prints three decimals.
- The script's own Asia session belongs to the next trading day. So its weekday days take the Sunday-Thursday
  evenings; the probe took Monday-Friday evenings, and gold has no Friday evening. That is why the script's Asia
  medians are wider ($6.43 against $6.23 on gold, $334 against $299 on BTC). This matters if the map's
  cost-per-range table (0.6) is used for the Asia setups.
- The 80% filter drops one BTC day from the opening range and one from London.

**The Monday quirk follows from the Sunday count.** Of gold's 286 Mondays from 2019-01-07 to 2024-06-24, 280 have
pWk false. The 6 exceptions:
- 2 Sundays opened at or after 20:00 (2019-04-21 Easter, 20:10; 2024-04-07, 20:00);
- 4 holiday Mondays opened at 18:00 with no Sunday session (2022-12-26, 2023-01-02, 2023-12-25, 2024-01-01). Their
  "Monday" is an 18:00-20:00 stub, so the next Tuesday's "yesterday" is that two-hour stub, as coded.

BTC has a Sunday day every week, so pWk is false on all 286 Mondays.

**The two authors' own counts are a further check.** Each counted signals on bars from 2019-01-01 with their own
port, before seeing the other. Their 2019-2022 counts agree on every setup, confirmation set, symbol and timeframe,
with one exception. Port B's original reading R1 made the 19:00-20:00 stub of 2018-12-31 a day of its own. That gave
BTC one more PD signal, on 2019-01-01 at 02:30 New York, in each set whose confirmations it passed. The reconciled
port reproduces port A's counts, both on the study's bars and on those 2019 bars.

## 6. Event counts per symbol and timeframe, 2019-2022

Signals decided in Development (the signal bar closes in 2019-01-01 to 2022-12-31), on the study's bars, with the
script's own 1H trend for HTF. Each cell is AS / LS / PD / AB / OR, then the total and the longs. For K0-K3, bars
that start on 2019-01-01 give exactly the same counts.

**XAUUSDm M5** (1,035 weekday trading days)

| Set | AS / LS / PD / AB / OR | Total | Long |
|---|---|---|---|
| K0 | 731 / 872 / 519 / 382 / 910 | 3,414 | 1,691 |
| K1 | 604 / 759 / 471 / 340 / 870 | 3,044 | 1,514 |
| K2 | 302 / 376 / 188 / 238 / 575 | 1,679 | 937 |
| K3 | 507 / 659 / 410 / 283 / 784 | 2,643 | 1,344 |
| K2 with F2-4H | 296 / 360 / 207 / 203 / 464 | 1,530 | 820 |
| K2 with F2-1D | 325 / 371 / 228 / 196 / 459 | 1,579 | 1,060 |
| K2 with F3 | 250 / 246 / 89 / 238 / 559 | 1,382 | 758 |

**XAUUSDm M15**

| Set | AS / LS / PD / AB / OR | Total | Long |
|---|---|---|---|
| K0 | 662 / 813 / 498 / 762 / 865 | 3,600 | 1,810 |
| K1 | 393 / 482 / 370 / 656 / 716 | 2,617 | 1,347 |
| K2 | 196 / 243 / 158 / 407 / 476 | 1,480 | 843 |
| K3 | 228 / 304 / 280 / 452 / 548 | 1,812 | 953 |
| K2 with F2-4H | 195 / 220 / 168 / 344 / 364 | 1,291 | 717 |
| K2 with F2-1D | 220 / 237 / 187 / 337 / 366 | 1,347 | 932 |
| K2 with F3 | 150 / 160 / 78 / 454 / 486 | 1,328 | 726 |

**BTCUSDm M5** (1,044 weekday trading days)

| Set | AS / LS / PD / AB / OR | Total | Long |
|---|---|---|---|
| K0 | 603 / 775 / 399 / 300 / 947 | 3,024 | 1,487 |
| K1 | 455 / 646 / 343 / 228 / 887 | 2,559 | 1,269 |
| K2 | 222 / 312 / 117 / 113 / 594 | 1,358 | 700 |
| K3 | 373 / 529 / 301 / 166 / 790 | 2,159 | 1,118 |
| K2 with F2-4H | 207 / 300 / 138 / 111 / 539 | 1,295 | 680 |
| K2 with F2-1D | 232 / 318 / 161 / 118 / 532 | 1,361 | 676 |
| K2 with F3 | 192 / 227 / 48 / 127 / 568 | 1,162 | 599 |

**BTCUSDm M15**

| Set | AS / LS / PD / AB / OR | Total | Long |
|---|---|---|---|
| K0 | 552 / 716 / 374 / 589 / 915 | 3,146 | 1,543 |
| K1 | 294 / 432 / 281 / 480 / 737 | 2,224 | 1,110 |
| K2 | 141 / 220 / 93 / 276 / 467 | 1,197 | 619 |
| K3 | 172 / 254 / 215 / 312 / 543 | 1,496 | 779 |
| K2 with F2-4H | 133 / 219 / 118 / 248 / 414 | 1,132 | 606 |
| K2 with F2-1D | 158 / 221 / 129 / 243 / 401 | 1,152 | 596 |
| K2 with F3 | 115 / 164 / 51 / 315 / 472 | 1,117 | 567 |

**The presets** are subsets of these rows:

| Preset | Gold M5 | Gold M15 | BTC M5 | BTC M15 |
|---|---|---|---|---|
| Custom: AS + LS, K2 | 678 | 439 | 534 | 361 |
| Forex: AS, K3 | 507 | 228 | 373 | 172 |
| Nasdaq: LS + PD, K2 | 564 | 401 | 429 | 313 |

**Cancels at entry, and E3's own cancel.**
- The script's cancels at entry (the next bar opens from 16:00, starts a new day, or opens at or beyond the stop)
  never happen under K1-K3 on these bars, and once under K0 (BTC M5, an open beyond the stop).
- E3's cancel (the far side of the range is less than 1R from the entry open) is a fact of the geometry at entry. It
  applies to 507 / 748 (gold M5 / M15) and 415 / 596 (BTC) of the K2 signals.

**The Monday variant.** K2 PD signals are 234 / 193 (gold M5 / M15) and 147 / 116 (BTC), against the script's
188 / 158 and 117 / 93. Of the variant's signals, 47 / 36 and 30 / 23 fall on Mondays, against 1 / 1 and 0 / 0 in
the script. Gold's one Monday signal in the script is on Easter Monday 2019-04-22, whose Sunday opened at 20:10, so
there was no Sunday day. No other setup changes.

**Claim 10's markets** (Development: USTECm from 2020-07-01, the FX pairs from 2019-01-01, to 2022-12-31):
- USTECm M5: the Nasdaq preset has 235 LS and 119 PD signals; PD + HTF has 132 PD.
- USTECm M15: 152 LS and 90 PD; PD + HTF has 120 PD.
- The Forex preset (AS, K3) on M15: 240 signals on EURUSDm, 213 on GBPUSDm.

## 7. What may still differ from TradingView

1. **The bars.** These are Exness bid bars built from M1 on UTC boundaries. A TradingView chart of another feed has
   other prices, holes and session times, and it builds its own 1H bars for `request.security`.
2. **The 1H history of the EMA200** (R7). TradingView computes it on the history it loads, which can start near the
   chart's first bar. Ours has two to three years of warm-up before 2019 for gold and one for BTC. USTECm has only
   484 1H bars before its Development start (2020-07-01). There the EMA's first value still weighs about 0.8% on
   2020-07-01. The two seeds differ by at most 0.017% of the price there and change no signal, but an EMA with
   years of history could differ by about 0.8% of the gap between the 2020-06-01 close and its own value.
3. **Comparisons with a missing value** (R1, R15). TradingView does not document them. They touch only the first bars
   of a chart.
4. **Exact ties in floating point.** Both ports follow the source's order of arithmetic and study 1's verified
   order for the built-ins. TradingView's internal summation could differ in the last bit. That could only flip a
   comparison that is an exact tie, such as a close exactly on the EMA, a stop exactly 0.5 ATR away, or a range
   exactly half the average. From 2019 the 1H trend is never exactly tied on our bars.
5. **The Auto preset.** It depends on how TradingView classifies the symbol (`syminfo.type`, L98). The plan runs each
   preset explicitly instead.
6. **Real time.** On TradingView a signal label can flicker inside a bar until it closes. Alerts fire once per bar
   close. History does not repaint.
7. **The script's own exits are not the study's execution.** The port reports them (cost 0, the chart's bid open,
   exits on chart bars, a gap through the stop filled at the stop) for the reconciliation and for comparison. Every
   scored number must come from PREREG 4's execution: fills at the next M1 open with the spread, stops on M1 bars,
   gaps filled at the open. Two notes for the study's code:
   - the script's own cancels at entry (`cancelled`) are part of the rules "as coded", and should be applied as well
     as PREREG 4's rule on the fill. For a long, the bid open can be at or below the stop while the ask is above it:
     the script cancels, PREREG 4's rule alone would not;
   - E3's "less than 1R away" (`exit_reason_liq == 'cancel_lt_1R'`) is measured from the chart's bid open. A test on
     the actual fill (a buy at the ask) would cancel more longs: on the K2 signals of Development, 95 / 67 more on
     gold (M5 / M15) and 188 / 120 more on BTC. This is proposed as reading 3 of section 8.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

1. **Session Hunter: the 1H history of the script's EMA200.** The script's 1H trend (`htfE`, its L145) is computed on
   every 1H bar of the study's market from the data start: gold 2016-01-03, BTC 2018-01-01, USTECm 2020-06-01,
   EURUSDm and GBPUSDm 2017-11-01. It is read at the chart bar's open as PREREG 6.6 says, with `ta.ema` started from
   its first close. PREREG 6.6 fixes when htfE is read but not how much 1H history it is computed on. A TradingView
   chart uses the 1H history it loads, which can start near the chart's first bar.
   - Why: the longest history is the closest to a converged EMA, and both ports were reconciled on it.
   - Effect, against 1H bars cut at 2019-01-02: the HTF direction differs on 536 / 182 gold bars (M5 / M15, the last
     on 2019-02-26 / 2019-01-25) and 539 / 183 BTC bars (the last on 2019-01-06). 10 / 10 / 6 / 5 K2 signals of
     Development differ, all before 2019-01-24.
   - The EMA's start changes nothing: the two starts give the same htfE, bit for bit, from 2019 on gold and BTC. On
     USTECm they differ by at most 0.017% of the price and change no signal.
   - Rows: every Session Hunter row that uses HTF (the K2 core rows, K2 x E3, the Custom and Nasdaq presets, claim
     10's USTECm rows), in January 2019 only (on USTECm, early July 2020).
2. **Session Hunter: the Monday variant (information only).** PREREG 6.6 asks for "a variant that gives Monday
   Friday's levels". In it, "the previous trading day was a weekday" (`pWk`) is replaced by "a weekday has finished
   since the data start", in the PD setup and in the YC confirmation only. So every weekday trades the levels of the
   last finished weekday: Monday those of Friday, and likewise a Tuesday after a Monday without bars. Nothing else
   changes, including a holiday Monday that opens at 18:00: its two-hour stub stays Tuesday's "yesterday", as in the
   script.
   - Why: it is the smallest change to the script that gives Monday Friday's levels, and it leaves every other day
     and setup as coded.
   - Effect: K2 PD signals in Development go from 188 to 234 (gold M5), 158 to 193 (gold M15), 117 to 147 (BTC M5)
     and 93 to 116 (BTC M15). Of these, 47 / 36 / 30 / 23 fall on Mondays; no other row changes.
   - Rows: the information-only Monday-variant rows.
3. **Session Hunter: the cancels at entry are the script's own, on the chart's bid open, E3's included.** PREREG 6.6
   keeps "the cancels at entry ... as coded" and gives E3 as "cancelled when it is less than 1R away", but does not
   say from which price the 1R is measured. The study applies the script's own decisions at the entry bar (the
   port's `cancelled`, and `exit_reason_liq == 'cancel_lt_1R'` for E3), measured as the script measures them: from
   the entry bar's bid open, with risk = |open - stop| (L431-439). PREREG 4's rule on the actual fill (a buy at the
   ask, a sell at the bid, of the first M1 bar at or after the signal close) applies on top.
   - Why: these are the script's cancels "as coded". The fill's M1 bar opens the chart's entry bar on every K2
     signal of Development (checked on both symbols and timeframes), so the two differ only by the spread, on longs.
   - Effect: with the 1R measured from the fill instead, E3 would cancel 95 / 67 more of the K2 signals of
     Development on gold (M5 / M15) and 188 / 120 more on BTC, all longs, against 507 / 748 and 415 / 596. The other
     cancels do not change anything there: no K2 entry opens from 16:00, starts a new day, or opens or fills at or
     beyond its stop in Development.
   - Rows: the E3 rows (K2 x E3, both timeframes, both symbols); the cancels also apply to E1 and E2, where they
     change nothing in Development.

Reading R1 (the first bar is not a new day) is not proposed as a deviation: on the study's bars it cannot change any
series or row (section 3).

## 9. Files, and how to re-run

    NUMBA_CACHE_DIR=<scratch> python3 -B -m pytest tests/test_tradeiq2_ind_session.py tests/test_tradeiq2_ind_session_a.py \
        tests/test_tradeiq2_ind_session_b.py -q --assert=plain -p no:cacheprovider

- The real-bar tests are skipped when the tick store is absent. The RV test on BTC is skipped without the Binance
  5m klines.
- The counts of section 6 and the probe comparison of section 5 come from scratch scripts outside the repository.
  They read the same bars with the reconciled port A, and only counts, times and ranges.
