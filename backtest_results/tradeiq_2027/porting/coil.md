# Coil breakout (our own rule): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values, event counts and event
geometry. No coil rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_coil.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_coil.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_coil.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_coil_a.py` and `tests/test_tradeiq2_ind_coil_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.9 (lines 434-465: COIL-RIB, COIL-MA and COIL-0, the grades BIG, VOL, ADX and
  ALL3; 36 rows per symbol), with the common definitions of section 5 and claim 20 of section 8.
- **The script:** there is none to port. TradeIQ's "Coil Breakout AI" is private (PREREG lines 18-19 and 26). The rule
  is the study's own, written in PREREG 6.9 from the video's description, and made precise by a contract that both
  port authors were given. Its only TradingView code is the platform's documented built-in functions: the 20-bar
  average (`ta.sma`), the standard deviation (`ta.stdev`), Wilder's ATR (`ta.atr`, `ta.rma`, `ta.tr`), `ta.change`,
  `fixnan`, and the ADX of `ta.dmi`, taken from TradingView's built-in "Directional Movement Index" script.

**The bottom line.**
- Two engineers ported the rule without seeing each other's work.
- On the 1H, 4H and 1D bars of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports give
  the same numbers, bit for bit, on every output and every bar. Gold was also run from study 1's later start. No
  tolerance and no change of arithmetic were needed.
- They also agree on 25,000 random synthetic cases (other settings, short series, flat and constant markets, rounded
  prices), and on every hand-made case of each port's own tests run through the other port.
- **The reconciliation found no mismatch.** Neither port's code was changed. Their docstrings now record the
  reconciliation.
- There is no third port: no planning pass ported the coil.
- **The reading that matters most** (section 3, reading 12). On the bar where a newer squeeze run reaches 6 bars, the
  old coil is replaced before that bar's close is tested. The other order would add 6 Development breakouts on BTC (5
  on 1H, 1 on 1D) and 1 Validation breakout on gold 1H. Both ports chose this reading independently. Eight readings
  add to the plan and are proposed for `DEVIATIONS.md` (section 8).
- **Two facts for the plan** (section 6):
  - the stop is nearly always the 3-ATR cap. The opposite box edge lies more than 3 ATR(14) from the breakout close
    on 80-90% of breakouts, and never closer than the 0.75-ATR floor;
  - gold 1D has exactly 15 Development breakouts, the 1D minimum of PREREG 5. Any filter, any grade, or a breakout
    skipped because a trade is still open takes a gold 1D COIL row below it.

## 1. What the rule computes

All settings are the plan's (PREREG 6.9); nothing is tuned.

1. **The squeeze (PREREG line 442).**
   - Each bar gets two envelopes around the average close of the last 20 bars:
     - the Bollinger band, plus and minus 2 standard deviations of those 20 closes;
     - the Keltner channel, plus and minus 1.5 times ATR(20), Wilder's average true range over 20 bars.
   - A bar is a **squeeze bar** when the Bollinger band lies strictly inside the Keltner channel. In words: the
     closes have moved less than the bars' ranges would suggest. Both envelopes share the same middle line, so this is
     the same as "2 standard deviations < 1.5 ATR(20)".
2. **The coil (line 443).**
   - A coil is a run of at least 6 squeeze bars in a row.
   - Its **box** spans the highest high and the lowest low of all the run's bars, however long the run is. The
     median run is 11 to 15 bars.
3. **Armed (line 444).**
   - A run is over at the first bar that is not a squeeze bar. That is the bar on which the squeeze "fires".
   - From that bar on, the coil is armed for 12 bars, that bar included.
   - Two things end the armed window early:
     - the coil's breakout;
     - a newer run of squeeze bars reaching 6 bars. That run is a new coil, and it replaces the old one on that bar.
   - A newer run of only 1 to 5 squeeze bars does neither: it does not replace the coil or pause its count.
4. **The breakout (line 445).**
   - On an armed bar, a close above the box is a long breakout. A close below it is a short one.
   - The close decides, not the wick, and a close exactly on the edge is no breakout.
   - Only the first breakout of each coil counts. Either side ends the coil.
5. **The ADX (line 461).** TradingView's `ta.dmi(14, 14)` ADX, which the ADX grade compares with 20.
6. **Not computed by the ports.** The study's rule module computes these from the ports' outputs and the bars:
   - the trend filters (the ribbon, the MA200);
   - the BIG and VOL grades;
   - the stop: the opposite box edge, clamped to 0.75-3 ATR(14);
   - the exits: the trend trail and the 3R target.

**Timing.**
- Every value is known at the close of its bar.
- The end of a run is known only at the close of the first bar without a squeeze. That is why the coil is armed from
  that bar, and why that bar's own close is the first one tested.
- The study decides at the breakout bar's close and fills at the next M1 open (PREREG 4).
- Nothing repaints: the rule has no higher-timeframe requests and no pivots. Both ports check that cutting the bars
  after any bar changes nothing before it.

**Example (gold 1H, schematic).**
- Squeeze bars close at 03:00, 04:00, ... 13:00: an 11-bar run. Its box is the run's highest high and lowest low.
- The 14:00 bar has no squeeze, so the coil is armed on the 14:00 bar and on the 11 bars after it.
- The first of those bars that closes above the box high is a long breakout; one that closes below the box low is a
  short one.
- If a new run of 6 squeeze bars builds before either happens, the old box is dropped on the new run's 6th bar.

## 2. What was compared, and how

- **The bars.** The study's harness, `tradeiq2_market.load(symbol, end="2024-07-01")`. Study 1's and study 2's
  hold-out guards were both closed, so nothing from 2024-07-01 on was loaded.
  - 1H, 4H and 1D are study 1's bars: bid prices on UTC boundaries, and a UTC day with fewer than 360 M1 bars is
    merged into the next.
  - Gold starts on 2016-01-03 (the 2016 warm-up months) and BTC on 2018-01-01.
  - Gold was also run from 2017-01-03, study 1's start. Both port authors measured on those bars. Study 1's gold bars
    are exactly the later part of the study's bars.
- **What had to agree.**
  - All nine outputs, on every bar:
    - the squeeze flag and the run length;
    - the armed flag and the armed box (high and low);
    - the breakout and the broken box (high and low);
    - the ADX.
  - Decimal numbers were compared by their 64-bit patterns, with missing values on the same bars. Yes/no flags and
    integers were compared exactly.
  - Two event tables had to be identical:
    - the breakout table: bar, times, side, close, box, ADX, armed-bar number, and whether it fell on a squeeze bar;
    - the coil table: first and last armed bar, run length, box, and how the coil ended (breakout, expiry, replaced
      or the data end).
  - The 2019-2022 counts of section 6 are recorded in the test, for both ports.
- **Each port's hand cases through the other port.**
  - The test replays the hand-made tests of both ports' own files: 23 of port A's (its 19 traps and 4 others) and 27
    of port B's (its 25 traps and 2 others).
  - Meanwhile every call those tests make to a port (the coil, the ADX, `ta.dmi`, the bands, and the coil logic on
    a given squeeze series) also runs in the other port, and the two results are compared bit for bit.
- **Synthetic bars.**
  - 240 random cases in the test, and 25,000 more in scratch before it. All of them agreed.
  - The bars came from both ports' generators: quiet and active regimes, random coil sequences, prices on a tick
    grid, flat stretches with zero ranges, constant markets (also at a price of 1e16), and gold- and BTC-like quotes.
  - Random settings: every length from 1, multipliers from 0, `min_bars` and `armed_bars` from 1, series of 0 to
    2,500 bars.
  - The two coil machines were also compared on random squeeze series, including runs still open at the last bar.
- **Is the test sharp?** It was rerun with port A deliberately broken in memory, one plausible misreading at a time
  (scratch, outside the repository). There were 23 such mutants. Each one fails the test, most of them in 20 tests or
  more. Section 2a lists them.
- **Arithmetic.** Both ports follow the order of TradingView's reference code ("same on Pine"), so nothing had to be
  aligned:
  - the 20-bar mean and deviation are summed from the newest bar, each term divided first;
  - the Wilder update is `alpha * x + (1 - alpha) * previous`, after a seed that is the mean of the first values;
  - the band sums are formed first and then compared;
  - the DMI script's statements are evaluated left to right.
- **Running it.** The reconciliation file has 81 tests and takes about 8 s. All three coil test files pass together:
  169 tests in about 21 s, at a peak footprint of about 0.6 GB (1.3 GB resident).

### 2a. The mutation check

Each line is one wrong reading planted in port A. Every one makes the reconciliation test fail.

| Mutant | What it changes | Caught by the real bars? |
|---|---|---|
| test-first replacement | the old coil can still break out on the newer run's 6th bar | yes |
| replace when the new coil arms | the old coil stays armed through the newer run | yes |
| a shorter run disarms | any newer squeeze bar disarms the coil | yes |
| box of the last 6 bars | instead of the whole run | yes |
| box includes the arming bar | the fire bar's own high and low | yes |
| armed one bar later | from the bar after the fire bar | yes |
| 13 or 11 armed bars | the window length | yes |
| `>=` / `<=` breakout | closes on the box edge break out | yes (gold's 2017-2018 ties) |
| once per side | a coil can break out once each way | yes |
| sample deviation | divides by 19 | yes |
| SMA of the true range | LazyBear's channel width | yes |
| EMA middle line | TradingView's `ta.kc` basis | yes |
| ATR seeded with the first true range | instead of the 20-bar mean | yes |
| DMI with `ta.tr(true)` | a true range on bar 0 | yes (last bits in the warm-up) |
| DMI tie to +DM | `up >= down` | yes |
| DX in percent before smoothing | another order of the same arithmetic | yes (last bits) |
| no `fixnan` | +DI / -DI left missing | no: only port B's underflow trap reaches it |
| no `sum == 0` guard | 0 / 0 in DX | no: both ports' hand cases and the random bars |
| `ta.change` of 0 on bar 0 | the DM averages start a bar early | yes |
| `100 * (rma / trur)` | another order for +DI | yes (last bits) |
| `<=` / `>=` squeeze | bands touching the channel | no: the hand cases' flat bars and the random bars |
| widths compared | `upper - lower` of each envelope | no: port A's trap at a price of 1e16 and the random bars |

- **The control.** A plain-Python copy of port A's coil logic with the correct readings, put in its place, passes all
  81 tests. So each mutant fails only because of its misreading.
- **The real bars alone** catch 19 of the 23 mutants. The other four change behaviour our bars never reach: `fixnan`
  acting, the `sum == 0` guard acting, a band exactly on the channel, and the reduced form of the squeeze. The
  replayed hand cases or the random bars catch those four.

## 3. The readings, with their evidence

The effects are counted on the 2019-2022 Development decision bars (section 6) of the study's bars. They are written
"gold 1H / 4H / 1D; BTC 1H / 4H / 1D", and they count changed squeeze bars or changed breakouts only, never profit or
loss. "Contract" means the contract both port authors were given.

| # | Item (PREREG line) | Reading used | Evidence | The alternative, and what it would change |
|---|---|---|---|---|
| 1 | The Keltner channel (l.442; PREREG 5) | SMA(20) of the close, plus and minus 1.5 x `ta.atr(20)` (Wilder's average of the true range, seeded with the mean of the first 20) | The plan's words; PREREG 5 defines ATR as `ta.atr` | TradingView's `ta.kc` (EMA middle, EMA of the range): 3,268 / 708 / 117; 5,652 / 1,257 / 290 squeeze bars and 312 / 68 / 14; 508 / 129 / 24 breakouts. An SMA of the true range (LazyBear, TTM): 1,672 / 332 / 39; 2,501 / 571 / 155 squeeze bars and 272 / 42 / 10; 332 / 96 / 19 breakouts |
| 2 | The deviation (l.442) | Population (divides by 20), `ta.stdev`'s default. A deviation of at most 1e-10 counts as 0, and the reference's stray "15" is not copied (study 1's PORTING item 7) | `ta.stdev`'s `biased` defaults to true; reference `pine_stdev` | Sample deviation (divides by 19): 514 / 122 / 15; 697 / 190 / 40 squeeze bars and 85 / 18 / 2; 119 / 27 / 9 breakouts. Without the zeroing: no bit changes on our bars (port B's mutant check) |
| 3 | "lies inside" (l.442) | Strict: the upper band below the channel's top and the lower band above its bottom. The four lines are formed, then compared | The plan's words; the classic squeeze is strict | Non-strict, or the reduced "2 sd < 1.5 ATR": 0 bars change to 2024-06-30. No band ever touches the channel; the closest approach from 2019 is 4.0e-6 ATR(20) (BTC 1D) |
| 4 | The ATR's start | Seeded with the mean of the first 20 true ranges; bar 0's true range is high - low | Reference `pine_atr`; PREREG 5 | Seeded with the first true range: no squeeze bar from 2019 changes (the ATR differs by at most 1.4e-8 relative) |
| 5 | Warm-up | No squeeze while a line is missing (bars 0-18); the ADX exists from bar 27 | A comparison with a missing value is false in Pine | Only the first weeks of 2016 (gold) and 2018 (BTC) |
| 6 | Counting bars | In chart bars: a weekend or a data hole between two bars neither ends a run nor stretches the window | Pine counts bars, not time | Breaking runs at gaps would change gold's runs across its daily break and weekends |
| 7 | A coil (l.443) | At least 6 squeeze bars in a row: 5 is no coil | The plan's words; contract | None |
| 8 | **The box (l.443)** | The highest high and lowest low of **all** the run's bars, not the closes, without the fire bar | "the highest high and lowest low of those bars"; contract | The last 6 bars: 80 / 13 / 2; 112 / 22 / 5 breakouts change. The first 6 bars: 214 / 87 / 9; 454 / 110 / 21. The closes: 268 / 79 / 8; 404 / 115 / 21 |
| 9 | **Armed from the fire bar, for 12 bars (l.444)** | Bars e+1 to e+12 for a run ending on bar e. The first armed bar is the first bar without a squeeze, and its own close is tested | "12 bars after its last squeeze bar"; contract. The run's end is known no earlier | Armed one bar later: 370 / 50 / 15; 556 / 144 / 22 breakouts change. The fire bar holds 187 / 25 / 8; 289 / 72 / 11 of the breakouts. 11 bars: 7 / 1 / 0; 12 / 3 / 1 lost. 13 bars: 7 / 2 / 0; 3 / 3 / 0 added |
| 10 | **A shorter newer run inside the window (l.444)** | Its squeeze bars count towards the 12, and the coil can break out on them | Only a "new coil" ends the window early, and fewer than 6 bars are no coil; contract | 11 / 1 / 0; 19 / 6 / 2 breakouts fall on such bars. Disarming the coil at the newer run's first squeeze bar: 29 / 3 / 0; 39 / 9 / 3 breakouts lost. Pausing the count on squeeze bars: 27 / 3 / 0; 30 / 7 / 3 change |
| 11 | **What replaces (l.444)** | A newer run reaching 6 squeeze bars, the moment it is a coil | "until a new coil replaces it"; contract | Replacing only when the newer coil arms (its run ends): 3 / 1 / 0; 8 / 1 / 1 breakouts added (Validation: 1 / 0 / 0; 4 / 0 / 0) |
| 12 | **The replacement bar (l.444)** | The old coil is dropped before that bar's close is tested, so it cannot break out there | The state at a close follows that bar's squeeze, as on the fire bar, and only then is the close tested; both ports chose it independently | Test first, then replace: 0 / 0 / 0; 5 / 0 / 1 breakouts added (BTC 1H at 2021-09-18 05:00 long, 2022-03-03 16:00 short, 2022-09-30 15:00 long, 2022-10-07 07:00 short, 2022-11-28 00:00 short; BTC 1D 2022-08-20 short; bar close times, UTC). Validation: 1 on gold 1H (2023-06-07 14:00 long) |
| 13 | The breakout (l.445) | The first close strictly above the box (long) or below it (short) on an armed bar; the wick does not count; once per coil, either side ending it | "the first close above the box ... once per coil"; contract | `>=` / `<=`: nothing changes from 2019 (no armed close sits exactly on an edge; the nearest is 0.003 away on gold 1H). In the gold Early window two closes do: 1H 2017-08-14 10:00 and 4H 2018-09-04 16:00, where `>=` / `<=` would change 2 and 1 breakout bars |
| 14 | The breakout bar's `armed` flag | The breakout bar is armed, with its box; nothing is armed after it | Contract | Only the meaning of the `armed` array changes, never a breakout |
| 15 | A run still going at the last bar | Not armed: it is not known to have ended | No look-ahead | Only at the very end of the data |
| 16 | **The ADX (l.461)** | `ta.dmi(14, 14)` as TradingView's built-in DMI script computes it: the change of the high and the low (missing on bar 0); a tie or an inside bar gives no directional movement; `ta.tr` without a value on bar 0; +DI = `fixnan(100 * rma(+DM) / rma(TR))`; DX divided by 1 when +DI + -DI is 0; ADX = 100 x the 14-bar Wilder average of DX | TradingView's built-in script (the `ta.dmi` reference gives no code) | `ta.tr(true)`: identical from 2019 on five series, 1.4e-14 on BTC 1D. DX in percent before smoothing: at most 5.7e-14. A tie given to +DM: 1 such bar on gold 1H and 1 on BTC 1H in Development; it moves the ADX by up to 1.3 (gold) and 4.8 (BTC) for a while and flips the 20 grade on 4 BTC 1H bars, none a breakout. `fixnan` and the guard never act after bar 14 (the true-range average is at least 0.95). Another study's ADX (`ladder_ind.adx`) agrees to 8.5e-14 |
| 17 | Source bars | The bid of the study's bars (UTC boundaries, a short day merged into the next); gold from 2016-01-03 | PREREG 2 | TradingView's own Exness bars (section 7). Gold from 2017-01-03 instead: the same values on every bar from 2019 but the last bit of 10 1D ADX values |

## 4. Mismatches found, and how each was resolved

**None.**
- Before any change, every output was equal bit for bit on all six real series and on both gold starts.
- All synthetic cases and all replayed hand cases agreed as well.
- So neither port's code was changed. Both docstrings gained a paragraph recording the reconciliation.

**Differences that are not mismatches (outside the shared contract).**
- **Helpers.** Port B also exposes the bands (`squeeze_lines`), the coil logic on a given squeeze series
  (`coil_from_squeeze`) and the full `ta.dmi` triple (`dmi`). Port A has the same pieces as private functions
  (`_bands`, `_machine`, `_dmi`).
  - The replay compares these pieces too.
  - Port B's `coil_from_squeeze` and port A's `_machine` also agree on random squeeze series that no real squeeze
    produces.
- **Input checks.** These are the same in both ports, tested with the same cases:
  - prices must be finite, one-dimensional and of equal length;
  - lengths and counts must be integers of at least 1 (an integral float is accepted);
  - multipliers must be finite and at least 0.
  - Only the error messages differ.

**The two ports' own notes, checked again here.** Every figure in both docstrings was reproduced, except for two
differences of convention:
- **Counting expired coils.** Port A counts a coil that expires by its last armed bar. That gives BTC 1H 123 and BTC
  1D 1 expired coils in 2019-2022. Port B counts each coil by its first armed bar, which gives 122 and 2. Both are
  right for their own definition; this note uses port B's.
- **The window.** Both authors counted bars closing in [2019-01-01, 2023-01-01) on study 1's bars. The harness's
  Development decision bars (section 6) leave out two kinds of bar:
  - the bar that closes at exactly 2019-01-01 00:00 (BTC 1H, 4H and 1D; gold 4H and 1D);
  - gold's last 2022 bar, which closes on 30-31 December and fills at 23:01 UTC on 2 January 2023.

  None of these bars is a breakout, so every event count is the same. Only the bar count changes, and the squeeze
  count changes by one bar on gold 1H, gold 1D and BTC 4H.
- **Port A's note on reading 10** said that disarming or pausing the coil on squeeze bars "would remove or move" the
  breakouts on squeeze bars. The full effect is larger, because disarming also removes the coil's later breakouts:
  29 / 3 / 0; 39 / 9 / 3 lost (reading 10).

## 5. A third opinion

There is none. No planning pass ported the coil, so the study's map for it is empty.

The independent checks used instead:
- **Port A's own tests** have a bar-by-bar transcription with one switch per misreading. It handles the coil as a
  list of coils rather than a bar loop.
- **Port B's own tests** have a formulation in numpy that builds the coil from the runs of the squeeze series, and
  study 1's verified Pine oracle for the averages.
- **Another study's ADX,** `ladder_ind.adx`, was written independently elsewhere in the repository. It agrees to
  8.5e-14 on all six series.
- **The planning numbers agree.** Both authors' 2019-2022 counts (squeeze bars, coils, breakouts, their timing and
  the effect of each alternative) were computed independently and agree with each other. They also agree with the
  counts measured here.

## 6. Event counts per symbol and timeframe, 2019-2022

**The data.**
- The study's bars; the values come from port A and port B, which are identical.
- The window is the harness's Development decision bars: a bar counts if it closes after 2019-01-01 00:00 UTC and
  fills (at the first M1 bar at or after its close) before 2023-01-01 00:00. That is `tradeiq_market.run`'s rule.
- Counts and geometry only: no rule was run and no profit or loss was computed.

**The columns.**
- **Coils:** coils armed in the window, counted at their first armed bar.
- **Ended B / E / R:** how each of those coils ended: by its breakout, by expiring after 12 armed bars, or replaced by
  a newer run's 6th bar.
- **Bar 1 / bar 12:** breakouts on the first and on the twelfth armed bar.
- **On a squeeze bar:** breakouts on a squeeze bar of a newer, shorter run (reading 10).
- **ADX >= 20:** breakouts that pass the ADX grade.
- **Runs:** the median and the longest run of the window's coils, in bars.

| Series | Bars | Squeeze bars | Coils | Ended B / E / R | Breakouts long / short | Bar 1 | Bar 12 | On a squeeze bar | ADX >= 20 | Runs (median / max) |
|---|---|---|---|---|---|---|---|---|---|---|
| Gold 1H | 23,590 | 6,982 | 430 | 338 / 69 / 23 | 193 / 145 | 187 | 7 | 11 | 188 | 11 / 57 |
| Gold 4H | 6,385 | 1,634 | 91 | 75 / 12 / 4 | 47 / 28 | 25 | 1 | 1 | 46 | 13 / 51 |
| Gold 1D | 1,031 | 290 | 16 | 15 / 1 / 0 | 8 / 7 | 8 | 0 | 0 | 7 | 13.5 / 37 |
| BTC 1H | 35,016 | 14,324 | 707 | 521 / 122 / 64 | 275 / 246 | 289 | 12 | 19 | 332 | 15 / 84 |
| BTC 4H | 8,756 | 2,914 | 161 | 129 / 26 / 6 | 72 / 57 | 72 | 3 | 6 | 81 | 13 / 62 |
| BTC 1D | 1,459 | 484 | 27 | 23 / 2 / 2 | 14 / 9 | 11 | 1 | 2 | 16 | 15 / 43 |

**The geometry at the breakouts** (for planning; the stop, the clamp and the BIG grade are the study's). The ATR is
the study's `ta.atr(14)` of the signal bars (`tradeiq2_market.atr14`). The raw stop is the distance from the breakout
close to the opposite box edge, before the clamp.

| Series | Box height (median) | Raw stop (median) | Raw stop above 3 ATR (capped) | Raw stop below 0.75 ATR (floored) | BIG (range >= 1.5 ATR) |
|---|---|---|---|---|---|
| Gold 1H | 3.25 ATR | 3.93 ATR | 287 of 338 (85%) | 0 | 173 (51%) |
| Gold 4H | 3.49 ATR | 4.18 ATR | 66 of 75 (88%) | 0 | 39 (52%) |
| Gold 1D | 3.50 ATR | 3.82 ATR | 12 of 15 (80%) | 0 | 4 (27%) |
| BTC 1H | 3.36 ATR | 4.15 ATR | 468 of 521 (90%) | 0 | 314 (60%) |
| BTC 4H | 3.35 ATR | 4.05 ATR | 112 of 129 (87%) | 0 | 69 (53%) |
| BTC 1D | 3.17 ATR | 4.39 ATR | 20 of 23 (87%) | 0 | 15 (65%) |

- **Most breakouts come at once.** The fire bar itself (armed bar 1) holds about half of them: 55 / 33 / 53% on
  gold and 55 / 56 / 48% on BTC.
- **The stop is nearly always the cap.** A coil's box is about 3.2-3.5 ATR(14) tall. The breakout close lies beyond
  one edge, so the opposite edge is further still. PREREG 6.9's stop is therefore the 3-ATR cap on 80-90% of
  breakouts and the opposite box edge itself on the rest; the 0.75-ATR floor never acts.
- **1D is thin.**
  - Gold has 15 Development breakouts, exactly the 1D minimum of PREREG 5. The BIG grade keeps 4 of them and the ADX
    grade 7, so the graded gold 1D rows cannot reach the minimum. The other gold 1D rows reach it only if their
    filter removes no breakout and no breakout is skipped while a trade is still open.
  - BTC 1D has 23 breakouts (BIG 15, ADX 16). Its filtered and graded rows can also fall close to or below 15.
- **The other windows** (counts only).
  - Validation (2023-01-01 to 2024-06-30) has 123 / 27 / 4 breakouts on gold and 186 / 49 / 9 on BTC.
  - The gold Early window (2017-2018, exam 2), read with the 2016 warm-up, has 208 / 44 / 6 coils and 173 / 34 / 5
    breakouts.
- **How close the data come to the thresholds** (from 2019 to 2024-06-30):
  - the bands never come closer to the channel than 4.0e-6 ATR(20), or 1.0e-7 of the price (BTC 1D);
  - no armed close sits exactly on a box edge;
  - no breakout bar's ADX is within 0.0014 of 20 (BTC 1H).

  Rounding in another order of operations moves these values by about 1e-16 relative (1e-13 for the ADX). So no
  change of arithmetic, here or in TradingView's native code, can move an event. The test asserts these margins.

## 7. What may still differ from TradingView

1. **There is nothing to compare with.**
   - The original Coil Breakout AI is private. Our rule is our reading of the video's description, so it may differ
     from TradeIQ's in any detail: the squeeze, the box, the window, the grades or the exits.
   - That is why claim 20 (731 trades on eight coins on 4H since 2021, a quarter winners, an 8.5R average winner)
     cannot be checked. The COIL rows test the idea, not the product.
2. **The bars.**
   - TradingView's Exness charts are assumed to show the bid, as PREREG 2 does.
   - Our bars are built from Exness's tick archive on UTC boundaries, and a short UTC day is merged into the next.
   - TradingView's 4H and 1D bars for a broker symbol may follow the broker's session instead, for example a daily
     bar from 22:00 UTC, and its feed may differ tick by tick.
   - So squeezes and breakouts can fall on other bars than on a TradingView chart, most likely on 4H and 1D. On 1H
     the boundaries are the same.
3. **The built-in functions.**
   - `ta.sma`, `ta.stdev`, `ta.atr` and `ta.dmi` are native code on TradingView. The ports follow TradingView's
     published reference code and, for `ta.dmi`, its built-in DMI script.
   - Any difference would be in the last bits, which section 6's margins show cannot move an event on our bars.
   - The DMI script's `ta.tr` (no true range on bar 0) and `ta.tr(true)` give the same ADX from 2019 to within
     1.4e-14.
4. **The history start.**
   - TradingView starts a chart at its own first bar. Its 1H history can be much shorter than ours.
   - The ATR(20) forgets its start as (19/20)^n and the ADX as (13/14)^n, so a few hundred bars wash it out.
   - On our bars gold's 2016 and 2017 starts give identical coils from 2019. In 2017 the later start's ADX is still
     warming up: the ADX >= 20 grade differs on 27 / 29 / 29 bars of 2017 (1H / 4H / 1D; a missing ADX counted as
     below 20). One gold 4H squeeze bar also differs, the one closing 2017-01-10 08:00, and no breakout does. That is
     why the study warms gold up from 2016 for the Early window.
5. **The live bar.** On TradingView the forming bar's squeeze, arming and breakout can appear and vanish before its
   close. The study uses closed bars only and fills at the next M1 open.
6. **Exact ties.** Only an exact tie can make the strictness of the breakout matter (reading 13). There are two in the
   gold Early window, none from 2019, and the hold-out is unseen.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

These are written before any COIL result exists. None of them changes a rule of PREREG 6.9. Each one fixes a point
the plan leaves open, and each one can move a COIL result. The counts are Development breakouts on the study's bars,
"gold 1H / 4H / 1D; BTC 1H / 4H / 1D".

1. **COIL: what replaces an armed coil.** PREREG 6.9 keeps a coil armed "for 12 bars after its last squeeze bar, or
   until a new coil replaces it". The ports read "a new coil" as a newer run of squeeze bars that reaches 6 bars:
   by the plan's own definition it is a coil from that bar on. It replaces the armed coil on that bar, not later when
   the newer run ends and its coil arms. The alternative would keep the old coil armed through the newer run's later
   bars and add 3 / 1 / 0; 8 / 1 / 1 breakouts (1 / 0 / 0; 4 / 0 / 0 in Validation). Affects all 36 COIL rows per
   symbol.
2. **COIL: the replacement bar.** On the bar where a newer run reaches 6 squeeze bars, the old coil is dropped before
   that bar's close is tested, so the old box cannot break out on it. The reason: a coil's state at a close follows
   that bar's squeeze, as on the fire bar (armed because its squeeze is off), and only then is the close tested. Both
   ports chose this reading independently. Testing the old box first would add 0 / 0 / 0; 5 / 0 / 1 breakouts (bar
   close times, UTC: BTC 1H 2021-09-18 05:00, 2022-03-03 16:00, 2022-09-30 15:00, 2022-10-07 07:00, 2022-11-28 00:00;
   BTC 1D 2022-08-20) and one in Validation (gold 1H 2023-06-07 14:00). Affects COIL rows on BTC 1H and 1D, and gold
   1H in Validation.
3. **COIL: a newer run of 1-5 squeeze bars inside the armed window.** It is no coil, so it neither replaces the armed
   coil nor pauses its 12-bar count. Its squeeze bars are armed bars and can be breakout bars. The reason: the plan
   names only two early ends of the window, the 12 bars and a new coil. 11 / 1 / 0; 19 / 6 / 2 breakouts fall on such
   bars. Disarming the coil at a newer run's first squeeze bar would lose 29 / 3 / 0; 39 / 9 / 3 breakouts, and pausing
   the count on squeeze bars would change 27 / 3 / 0; 30 / 7 / 3. Affects all COIL rows.
4. **COIL: the armed window is the fire bar and the 11 bars after it.** For a run ending on bar e, the coil is armed
   on bars e+1 to e+12, counted in chart bars (a weekend or a data hole neither ends a run nor stretches the window).
   Bar e+1 is the first bar without a squeeze, the bar that shows the run has ended, and its own close is tested. The
   reason: "12 bars after its last squeeze bar" read literally; the run's end is not known any earlier. The fire bar
   holds 187 / 25 / 8; 289 / 72 / 11 breakouts. Arming one bar later would change 370 / 50 / 15; 556 / 144 / 22
   breakouts. An 11-bar window would lose 7 / 1 / 0; 12 / 3 / 1 and a 13-bar window add 7 / 2 / 0; 3 / 3 / 0. Affects
   all COIL rows.
5. **COIL: the box spans the whole run.** "Its box is the highest high and lowest low of those bars" is read as all
   the run's squeeze bars, however many: the median run is 11-15 bars. Highs and lows are used, not closes, and the
   fire bar is not included. The box also sets the stop (the opposite edge). A box of the run's last 6 bars would
   change 80 / 13 / 2; 112 / 22 / 5 breakouts, its first 6 bars 214 / 87 / 9; 454 / 110 / 21, and the closes
   268 / 79 / 8; 404 / 115 / 21. Affects all COIL rows.
6. **COIL: the population deviation.** "stdev(close, 20)" is Pine's `ta.stdev` with its default `biased = true`: it
   divides by 20. A deviation of at most 1e-10 counts as 0, as in the reference code and study 1. The sample
   deviation (divide by 19) would change 514 / 122 / 15; 697 / 190 / 40 squeeze bars and 85 / 18 / 2; 119 / 27 / 9
   breakouts. Affects all COIL rows.
7. **COIL: strict comparisons and exact ties.** A squeeze needs the Bollinger band strictly inside the Keltner
   channel ("lies inside"), and a breakout needs a close strictly above or below the box ("above", "below"). From
   2019 to 2024-06-30 no band touches the channel and no armed close equals a box edge, so the reading changes
   nothing in Development or Validation. In the gold Early window (exam 2) two closes sit exactly on a box edge (1H
   2017-08-14 10:00 and 4H 2018-09-04 16:00), where `>=` / `<=` would change 2 and 1 breakout bars. Affects gold
   COIL rows in the Early window, and any later bar with an exact tie.
8. **COIL: the ADX is that of TradingView's built-in DMI script.** "Pine `ta.dmi(14, 14)` ADX" is computed as the
   built-in "Directional Movement Index" script does, since the `ta.dmi` reference gives no code. A tie (`up ==
   down`) or an inside bar gives no directional movement, the true range is missing on bar 0, +DI and -DI are carried
   forward by `fixnan`, and DX is divided by 1 when +DI + -DI is 0. The readings that are equal in exact arithmetic
   (`ta.tr(true)`, another order of the scaling) differ by less than 1e-13. Giving a tie to +DM instead would flip
   the ADX >= 20 grade on 4 BTC 1H Development bars, none of them a breakout bar, so it changes no result to
   2024-06-30. No breakout bar's ADX comes within 0.0014 of 20. Affects the ADX and ALL3 grades of COIL-RIB, and
   only where a directional-movement tie shortly before a breakout moves its ADX across 20.
