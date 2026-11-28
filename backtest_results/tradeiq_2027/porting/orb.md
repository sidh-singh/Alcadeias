# Ultimate Opening Range Breakout (LuxAlgo): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values and event counts. No ORB
rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_orb.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_orb.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_orb.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_orb_a.py` and `tests/test_tradeiq2_ind_orb_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.5, with claims 6-9 of section 8.
- **The script:** "Ultimate Opening Range Breakout [LuxAlgo]", Pine v6, CC BY-NC-SA 4.0. It is third-party code.
  Line numbers (l.) refer to the owner's copy. The source is not in this repository.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- On the M5 and M15 bars of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports now give
  the same numbers, bit for bit, on every output and every bar. They also give the same table of sessions.
  - This holds in every configuration the plan runs: the plan's New York version, the literal UTC-5 clock, gold's
    COMEX range, BTC on all seven days, and BTC on either volume.
  - It also holds for two alternative readings of the day reset, which were run only to measure them.
  - No tolerance was needed anywhere.
- **What the reconciliation found.**
  - The ports never disagreed about what the script does on a bar, except for one reading that has no effect (the
    first bar of the data; section 4, M1).
  - The real mismatches were in the table of sessions. The ports differed on which sessions are rows, on the row of
    a session whose range a data hole wiped out, and on column names and codes. They also accepted different inputs.
  - All of it is settled, and both ports were changed.
- **A third opinion agrees.** The planning pass's unreviewed range probe gives the same range for every session and
  the same median widths (section 5).
- **The counts agree.** The 2019-2022 event counts on the study's bars equal both porters' own reports in every
  figure (section 6).
- **Readings for the plan.** Seven readings add to the plan and can move a result. They are proposed for
  `DEVIATIONS.md` in section 8. The most visible one: on M15 the COMEX range is 08:30-09:00, not 08:20-08:50.

## 1. What the script computes

All settings are the script's defaults (l.33-62), except where the plan corrects the clock and the days.

1. **The opening range (l.87, 147-171).**
   - It is the high and the low of the chart bars that open between 09:30 and 10:00 (l.33).
   - The script's clock is a fixed UTC-5 (l.35) on all seven days (l.34). The plan's version uses New York time with
     daylight saving, on weekdays.
   - On M5 the range uses six bars (09:30 to 09:55). On M15 it uses two (09:30 and 09:45). Both cover exactly
     09:30-10:00, so M5 and M15 give the same range.
   - On 1H no bar opens inside 09:30-10:00, so no range ever forms.
2. **The targets (l.185-193).** T1, T2 and T3 lie 1, 2 and 3 range widths beyond each edge of the range.
3. **The hit counts (l.195-214).**
   - From the 10:00 bar until the day ends, the first touch of each target counts once that day.
   - A touch counts whether or not price broke out. Up and down targets can both count on the same day.
   - The dashboard divides each count by the number of sessions (l.374-379). These are unconditional rates, not
     win rates (claim 8).
4. **Breakouts (l.243-244).**
   - A breakout up is a close above the range's high when the previous close was at or below it. A breakout down
     is the mirror, at the range's low.
   - Breakouts count from 10:00 on, until the day ends. They are the script's alerts (l.480-481).
5. **Labels (l.252-272).**
   - The first breakout of each side gets a "BULL BREAK" or "BEAR BREAK" label. There is at most one label per side
     per day.
   - Labels appear only while the display window is open: from the session's start to 17:00 ("New York Close",
     l.56-58, 216-225).
   - Each label carries an HV or LV tag: HV when the bar's volume is above the 20-bar average of volume, with the bar
     itself included (l.238-240).
6. **The script's own trade (l.252-286).**
   - The first label opens a trade if none is open. The script books the entry at the range edge, not at the close.
   - The trailing stop starts at the bar's low minus 2 x ATR(14) and only ratchets up (a short mirrors this).
   - The trade exits at a close beyond the trail, or at the first bar outside the display window. The exit is
     booked at that bar's close.
   - **The order of the statements matters.**
     - The bear label is processed before the long's exit test. A bear breakout on the bar where the long exits
       therefore uses up the bear label, and no short opens that day.
     - The day reset runs before the exit test. So a trade still open when the day ends vanishes without being
       booked.
     - On gold the day ends at 17:00 New York, and the next bar is the 18:00 reopen. So every gold trade still open
       at the 17:00 break vanishes, in summer and in winter.
   - After the first trade exits by its trail, a label of the other side can open a second trade the same day.
7. **Not ported**, because nothing in the study reads them:
   - the volume profile (l.84, 109-112, 157-179, 341-368);
   - the stop optimizer (l.288-304, off by default);
   - the drawing and the dashboard (l.309-476);
   - the "Target 3 Reached" alerts (l.482-483).

**Timing.**
- The range is final at the close of the 09:55 bar (M5) or the 09:45 bar (M15). It can be read from 10:00.
- A breakout, a label and a trail exit are known at their bar's close. The earliest real fill is the next M1 open,
  so a real entry is never at the range edge the script books.
- Closed bars never change: the script has no higher-timeframe requests, no pivots and no look-ahead.

## 2. What was compared, and how

- **The bars.** The study's own M5 and M15 bars (`tradeiq2_market.load(symbol, end="2024-07-01")`, then
  `mk.tbars('M5' | 'M15')`), with both studies' hold-out guards pointed at empty folders.
  - Gold starts on 2016-01-03 (the 2016 warm-up months) and BTC on 2018-01-01. Both end on 2024-06-30.
  - The bar counts are those in `DATA.md`: gold 596,786 M5 and 199,192 M15 bars; BTC 681,121 and 227,123.
  - The volume is PREREG 2's: tick volume for gold, Binance BTCUSDT 5-minute volume for BTC. BTC was also run on
    Exness tick volume.
- **The configurations.**
  - The plan's version: New York clock, weekdays, the exchange's day.
  - The literal UTC-5 clock (claim 9 and the O1 control).
  - Gold's COMEX range, 08:20-08:50 (ORB-CX).
  - BTC on all seven days (the O1 control).
  - Two alternative readings of the day reset, run only to measure them: midnight of the session clock (`clock0`),
    and for BTC a 17:00 New York day (`ny17`).
- **What had to agree.**
  - All 13 per-bar outputs, on every bar: in-session, new day, the range high and low, session ended, breakout up
    and down, label up and down, HV, ATR, the trade's direction and its trail.
  - The table of sessions, column by column: date, bars, range, levels, first breakout, labels, hits, and the
    script's two trades with their entry and exit bars, prices and exit reasons.
  - The trades' prices were compared for equality only. No price was printed, counted or summed.
  - Decimal numbers were compared bit for bit, with missing values on the same bars. Flags, integers and labels were
    compared exactly.
- **The 2019-2022 counts** of every configuration are recorded in the test (section 6). They are counts only: no
  rule is run.
- **A third opinion.** Every session's range was checked against the high and the low of the M1 bars in its 30
  minutes, which is the planning probe's computation (section 5).
- **Synthetic bars.**
  - Both ports' own random charts: gold-like and BTC-like bars, both daylight-saving changes of 2023, prices on a
    coarse grid (exact ties), and every input of the contract.
  - Forty charts with many data holes. These produce sessions cut by a hole, sessions wiped by a new day, ranges
    restarted inside a session, and sessions cut by the end of the data.
  - Hand-made edge cases: a chart that starts inside the session, 1H bars, an empty input, no volume, a session
    across 00:00 UTC, and two sessions in one UTC day.
  - Every chart was also cut at random bars and at bars inside a session.
- **The contract.** The same function signature and defaults, keys, columns, labels and dtypes, and the same refused
  inputs (28 kinds), in both ports.
- **Arithmetic.** Both ports follow TradingView's reference code and the script's order of operations, so nothing
  had to be aligned.
  - The 20-bar average is summed from the newest bar.
  - The ATR's update is `alpha * x + (1 - alpha) * previous`, seeded with a plain average.
  - The script's own expressions keep their order, for example `orHigh + width * multiple` and `low - ATR * 2`.
- **Running it.** The three test files pass together: 231 tests (9 skipped: configurations of the other symbol) in
  about three minutes, at a peak of 1.7 GB of memory.

## 3. The Pine readings, with their evidence

Effects are counted on 2019-2022 (bars closing in it; sessions whose first bar closes in it), from the study's bars.
They are changed sessions, labels or flags only: counts, never profit or loss.

| # | Item (lines) | Reading used | Evidence | The alternative, and what it would change |
|---|---|---|---|---|
| 1 | Which bars are in the session (l.87) | A bar is in when it OPENS inside [start, end). The end is exclusive, so the 10:00 bar is outside | Pine's `time(timeframe, session)` returns the bar's open time when that time is in the session; trap 1 in both ports | For 09:30-10:00 on M5 / M15 every reading agrees. For COMEX on M15: a bar that overlaps the session (08:15-09:00) changes 795 of the 1,030 ranges and 193 first breakouts; only whole bars inside (08:30-08:45) changes 784 ranges and 489 first breakouts |
| 2 | Session days (l.34, 87, 225) | The weekday of the session clock's date at the bar's open; "weekdays" = Pine's "23456" | Pine's `dayofweek` in the session's timezone | New York's weekday under the UTC-5 clock: identical (all windows lie between 08:20 and 18:00 New York) |
| 3 | The day reset (l.88) | The feed's own trading day: gold 17:00 New York with daylight saving (the 18:00 reopen and the Sunday open start a day); BTC 00:00 UTC | `time("D", "", tz)` has an empty session string, so the timezone cannot move the daily bar. TradingView's FX / metal CFDs run 17:00-17:00 New York; crypto exchanges' days start at 00:00 UTC | Midnight of the session clock (`clock0`): no label changes; 1,143 (M5) / 661 (M15) raw breakouts after 17:00 on gold; other hit flags on 176 of 1,031 gold and 232 of 1,042 BTC sessions; other first breakouts on 21 / 32 gold and 4 / 3 BTC sessions. A 17:00 New York day for BTC (`ny17`): other hit flags on 193 sessions, 6 first breakouts per timeframe. See section 8, item 2 |
| 4 | The day reset on the first bar (l.88) | No new day on bar 0 | `ta.change` has no previous value there, and a comparison with a missing value is false: study 1's reading and the other study-2 ports' (TradingView only warns against such comparisons) | A new day on bar 0 (port B's first reading): only that one flag changes; shown on the real bars |
| 5 | The range (l.166-171) | Highest high and lowest low of the session's bars ("High/Low") | As written | None |
| 6 | Breakout (l.243-244) | A close above the range, after a previous close at or below the previous bar's range high; false where a value is missing | `ta.crossover`'s documented definition. On the 10:00 bar the previous close always lies inside the range, so a 10:00 close beyond it is a breakout. A close exactly at the edge is not one | TradingView's runtime, which skips bars with missing values: identical here, because a breakout needs the session to have ended, and then the previous bar's range exists |
| 7 | Hits (l.195-214) | From the 10:00 bar (included) to the day reset, the first bar whose high reaches T_k (low for the down targets), with or without a breakout | As written | None |
| 8 | Display window (l.216-225) | From the session's start to 17:00 on the session clock, on the session's days | `orStartTime` is the first four characters of the session input; the end is "1700" | A fixed 09:30-17:00 New York would remove the ORB-CX labels between 08:50 and 09:30. Under the literal UTC-5 clock the window ends at 18:00 New York in summer; no rule enters after 16:00 anyway |
| 9 | HV tag (l.238-239) | Volume strictly above its 20-bar average, the bar included; LV while the average has fewer than 20 bars | As written; the average in TradingView's reference order of addition | Another order of addition: in 2019-2024H1 no label of a planned row changes; one gold M15 label of the UTC-5 control and one BTC label per timeframe on tick volume (unused). See section 8, item 6 |
| 10 | BTC's volume | Binance BTCUSDT 5-minute volume | PREREG 2 | Exness tick volume changes the tag of 316 of 1,472 labels (M5) and 264 of 1,391 (M15) |
| 11 | ATR (l.236) | Wilder's average of the true range over 14 bars, seeded with their plain mean; the first bar's true range is high - low | `pine_atr`; PREREG 5 | The harness's `atr14` (another order of the same arithmetic): 2e-15 relative; the trail's decimals differ on 331-1,512 bars per series and configuration, and no trade opens or closes on another bar |
| 12 | The trail on the entry bar (l.275) | The previous bar's trail, which is always missing on an entry bar, so the trail is that bar's low - 2 ATR | `nz(trailStop[1], ...)`; a trade never opens on a bar that ends one or resets the day | The just-set value: the same number. The misreading that would matter is a stale trail from an earlier trade (both ports test it) |
| 13 | Statement order (l.246, 252-286) | Day gates, then the bull label, the bear label, the long's exit, the short's exit | As written | Exits first: a short could open on the long's exit bar; a trade open at 17:00 on gold would be booked instead of vanishing |
| 14 | Exit reason when both exit conditions hold (l.276) | "trail" (the first condition) | As written | "window": a label only. It concerns 8 (M5) and 18 (M15) BTC exits, no gold exit |
| 15 | The script's trades per day | Up to two: the first label opens one; a label of the other side opens a second only after the first has closed | `activeDir` must be 0 at the label (l.255, 266) | None |
| 16 | Which sessions are rows (l.181-183) | The sessions the script counts: every range that reaches its first bar after the session | `totalSessions += 1` | Every range that started (port A's first reading): the same rows on the study's bars |
| 17 | A session wiped by a data hole (l.147, 181) | Counted, with no range; its span runs to the next reset | The reset on the session's end bar runs before the session is counted | The range of its bars (port A's first reading). Only gold's COMEX session of 2021-03-02 on M5 |
| 18 | A session with missing bars | Its range is that of the bars it has | As written | None on the 09:30 sessions from 2019; see section 8, item 5 |
| 19 | The first breakout of a day (the session table) | The first raw breakout from 10:00 to the day reset (the alert condition), labelled or not | The plan's claim 6 asks for "the first breakout" | The first label: identical on gold; 6 BTC sessions per timeframe differ (a first breakout after 17:00 New York). See section 8, item 3 |

## 4. Mismatches found, and how each was resolved

**M1. The day reset on the first bar (l.88).**
- **What differed.** Port A said bar 0 is not a new day. Port B said it is, because a missing value compared with 0
  is "not equal" in ordinary floating-point rules.
- **The source.** `ta.change` has no previous value on bar 0, so `isNewDay` compares a missing value with 0.
  TradingView only warns against such comparisons and does not say what they return.
- **Who was right.** Port A, by the study's rule. Study 1 read every comparison with a missing value as false, and so
  did the Session Hunter reconciliation for the same question. Port B was changed.
- **Effect: none.** On bar 0 every variable still holds its initial value, and a bar 0 inside the session resets
  anyway. The test runs port B's first reading on the real bars: only that one flag differs.

**M2. Which sessions are rows of the session table.**
- **What differed.** Port A had a row for every range that started, with a flag for those that never ended: a range
  cut by the end of the data, or one restarted by a new day inside the session. Port B had a row only for the
  sessions the script counts.
- **The source.** The dashboard's denominator is `totalSessions`, which counts a session at its first bar after the
  session (l.181-183).
- **Who was right.** Port B. A rule reading the table should not meet a session the script never counted. Port A now
  drops such ranges, and its `ended` column is gone.
- **Effect on the study: none.** On the study's bars every range reaches its end. On a cut (live) chart, a session
  still running at the cut is not a row.

**M3. The row of a session whose range a data hole wiped.**
- **The case.** Gold's COMEX session of 2021-03-02 on M5. Exness's data stop after the 08:20 bar and resume on
  Wednesday at 19:00 New York, which is a new trading day.
  - On that bar the day reset (l.147) wipes the range before l.181 counts the session.
  - So the script counts a session that has no range, and nothing can break out or hit a target on it.
- **What differed.**
  - Port A kept the range of the session's one bar (the 08:20 bar's high and low). It also ended the session's span
    at that same bar, an empty span.
  - Port B gave the row no range. It gave no first bar either, and ended the span at the next reset.
- **Who was right.**
  - Port B on the range: the table must show the range the script holds after the session. A one-bar "range" is not
    the opening range, and a rule could otherwise place orders at it.
  - Port B on the span: the session's flags hold from the reopen to the next reset (Thursday 08:20).
  - Port A on the first bar: the row keeps the session's own bars (08:20 to 08:20), so its date and bar count stay
    readable.
  - Both ports were changed.
- **Effect on the study: none.** There are no bars that day after 08:20, so no order could fill. The TIGHT filter is
  not applied to ORB-CX. On M15 that day has no session at all: its 08:15 bar opens before 08:20.

**M4. The format of the session table.**
- **What differed.**
  - Column names: port B's `day_key`, `range_start_bar`, `trade_dir`, `trade2_entry_bar`, ... against port A's
    `day`, `start_bar`, `trade_side`, `entry2_bar`, ...
  - The date: port B wrote YYYYMMDD of the range's last bar; port A the day number of its first bar.
  - Types: port B used small integers for the sides.
  - Exit codes: port B used Python's `None` for both "no trade" and "still open"; port A uses "" and "open".
  - Extra columns: port A had the first bar after the session, the span's end and the six target levels; port B had
    the next reset.
- **Resolution.** Port A's format, the production module's interface, without `ended`. Port B was changed. The two
  tables are now identical, column for column.

**M5. The inputs each port accepted.**
- **What differed.**
  - Port B accepted any fixed UTC offset, aliases and upper-case names, Pine's day digits and float times.
  - Port B had no "no volume" option and no `clock0` reading.
  - Port A accepted chart timeframes that do not divide a day.
- **Resolution.** Both ports now accept exactly the same inputs:
  - the clocks `ny` and `utc-5`;
  - the days `weekdays` and `all`;
  - the day boundaries `auto`, `ny17`, `utc0` and `clock0`;
  - integer times on the timeframe's grid, and a timeframe that divides 1,440 minutes;
  - a volume, or none.
- **The tests.** Both ports refuse the same 28 kinds of bad input.

**No other mismatch.**
- Every per-bar output agreed bit for bit on every real configuration from the first run, apart from M1's flag.
- The same held on all synthetic charts.
- No arithmetic had to be aligned.

**The tests added.**
- Port A: a hand-computed test of M2 and M3 (a wiped range, a session cut by the data end, a range restarted by a
  new day); and the refusal of a 7-minute timeframe.
- Port B: a test of the `clock0` reading and of "no volume". Its tests were updated to the shared table and to M1.

## 5. A third opinion: the planning pass's range probe

Before the plan was written, a planning pass ran `probe_sessions.py` (outside the repository, only read and run
here). For the ORB it computed the opening range from M1 bars: the high and the low of the bars opening 09:30-09:59
New York on weekdays, on 2019-01-01 to 2024-06-30. It kept the days with at least 80% of the full minute count. The
spec's table of range sizes and costs (its 0.6) comes from it. It counted no breakouts.

- **Run again here** (unchanged), it gives:
  - gold: 1,416 days, a median range of $5.994 (0.328% of price), a cost of 4.4% of the range;
  - BTC: 1,432 days, $179.685 (0.752%), 15.3%;
  - the literal UTC-5 range (14:30-15:00 UTC): medians of $4.935 (gold) and $166.175 (BTC).
- **The ports agree on every figure.**
  - The ports have exactly as many sessions in that span: 1,031 + 385 on gold and 1,042 + 390 on BTC.
  - The reconciliation test recomputes the M1 high and low for every session on both timeframes, on the New York
    clock, the UTC-5 clock and the COMEX range. Every session's range equals it, and every such date has a session.
  - The medians are the same: $5.994 and $179.685 on New York time, $4.935 and $166.175 on UTC-5.
- **No difference to explain.**
  - The probe's 80% filter drops no day in that span: no 09:30 session from 2019 on is missing a bar.
  - Gold's one short 09:30 session (2016-05-18) is warm-up and outside the probe's span.
- **The two porters' own counts** were made on bars starting in 2019. They equal the reconciled counts on the
  study's bars, which start in 2016 / 2018, in every figure, the script's exits included. So the earlier start
  moves nothing in 2019-2022.
- **The map's statements about the script check out on our bars.**
  - Every gold trade still open at 17:00 vanishes at the reopen: no gold exit by the window rule in any
    configuration, except `clock0`.
  - A BTC trade still open at 17:00 leaves by the window rule on the 17:00 bar. No BTC trade vanished in 2019-2022.
    In 2023-2024H1, one (M5) and two (M15) did: in April 2024 Exness's BTC data have holes from 15:00 or 16:00 to
    20:00 New York, and the first bar after the hole is already the next UTC day.
  - No range forms on 1H.
  - M5 and M15 give the same range and the same hit counts, but different breakouts.

## 6. Event counts per symbol and timeframe, 2019-2022

**The data.**
- The study's bars; values from port A and port B, which are identical.
- A label or breakout counts if its bar closes in 2019-2022. A session counts if its first bar does.
- Counts only: no rule was run and no profit or loss was computed.

**The plan's version** (New York clock, weekdays, the exchange's day; gold tick volume, BTC Binance volume):

| | Gold M5 | Gold M15 | BTC M5 | BTC M15 |
|---|---|---|---|---|
| Sessions | 1,031 | 1,031 | 1,042 | 1,042 |
| Median range width | $5.70 | $5.70 | $146.82 | $146.82 |
| Raw breakouts (alerts), up / down | 1,682 / 1,565 | 1,039 / 986 | 2,698 / 2,512 | 1,657 / 1,550 |
| Labels, up / down | 638 / 609 | 601 / 564 | 750 / 722 | 707 / 684 |
| HV labels, up / down | 337 / 410 | 407 / 421 | 562 / 564 | 478 / 499 |
| HV labels on tick volume (BTC) | | | 499 / 569 | 436 / 515 |
| Labels on the 10:00 bar | 288 | 393 | 264 | 363 |
| Labels on bars closing after 16:00 New York | 5 | 5 | 38 | 45 |
| Days with both labels | 254 | 197 | 445 | 368 |
| First breakout up / down / none | 502 / 491 / 38 | 498 / 470 / 63 | 529 / 504 / 9 | 524 / 505 / 13 |
| First breakouts closing after 16:00 / after 17:00 | 0 / 0 | 2 / 0 | 12 / 6 | 13 / 6 |
| Sessions reaching T1 / T2 / T3 up | 304 / 113 / 49 | 304 / 113 / 49 | 534 / 326 / 220 | 534 / 326 / 220 |
| Sessions reaching T1 / T2 / T3 down | 313 / 137 / 57 | 313 / 137 / 57 | 530 / 356 / 229 | 530 / 356 / 229 |
| Script's first trades, long / short | 502 / 491 | 498 / 470 | 525 / 502 | 520 / 503 |
| ... ended by trail / window / reset | 868 / 0 / 125 | 279 / 0 / 689 | 944 / 83 / 0 | 421 / 602 / 0 |
| Script's second trades | 187 | 47 | 286 | 55 |
| ... ended by trail / window / reset | 122 / 0 / 65 | 2 / 0 / 45 | 198 / 88 / 0 | 4 / 51 / 0 |
| Labels without a trade (a trade was open) | 67 | 150 | 159 | 313 |

- **Range width.** The median over 2019-2024H1 is $5.994 (gold) and $179.685 (BTC). Over 2019-2022 alone it is the
  $5.70 and $146.82 of the table.
- **Hits.** The hit counts are the same on M5 and M15, because the range and the day are the same.
- **Hits after the flat time.** Gold's hits all come before 16:55 New York, but one or two on M15. On BTC, 35 to 68
  of each level's first touches come after 16:55, because BTC's day runs to 00:00 UTC.
- **Hits before the breakout.** A target's first touch comes before that side's label in 0-3 gold sessions per
  level and 1-6 BTC sessions per level.
- **BTC's volume.** Binance volume is missing on 798 M5 and 269 M15 bars in 2019-2022: an outage, volume 0, LV.
- **Gold's script trades.** Gold's script trade never leaves by the window rule. The bar after 16:55 is the 18:00
  reopen, which is a new day, so a trade still open at the break is dropped (section 1). On M15 that is most trades.

**The controls and the alternative readings** (2019-2022; the volume as above):

| Configuration | Series | Sessions | Labels up / down | First breakout up / down / none | First trades: trail / window / reset |
|---|---|---|---|---|---|
| Literal UTC-5 clock | Gold M5 / M15 | 1,031 / 1,031 | 653 / 604 ; 613 / 557 | 534 / 460 / 37 ; 516 / 454 / 61 | 827 / 0 / 167 ; 215 / 0 / 755 |
| | BTC M5 / M15 | 1,042 / 1,042 | 773 / 725 ; 729 / 678 | 545 / 487 / 10 ; 548 / 480 / 14 | 952 / 73 / 0 ; 423 / 598 / 0 |
| BTC on all seven days | BTC M5 / M15 | 1,458 / 1,458 | 1,070 / 1,024 ; 1,012 / 973 | 741 / 708 / 9 ; 732 / 712 / 14 | 1,324 / 114 / 0 ; 616 / 818 / 0 |
| ORB-CX (COMEX 08:20-08:50) | Gold M5 / M15 | 1,031 / 1,030 | 722 / 688 ; 683 / 645 | 522 / 489 / 20 ; 511 / 496 / 23 | 955 / 0 / 56 ; 419 / 0 / 588 |
| Day at midnight (`clock0`) | Gold M5 / M15 | 1,031 / 1,031 | 638 / 609 ; 601 / 564 | 512 / 502 / 17 ; 513 / 487 / 31 | 882 / 80 / 31 ; 288 / 533 / 147 |
| | BTC M5 / M15 | 1,042 / 1,042 | 750 / 722 ; 707 / 684 | 531 / 506 / 5 ; 525 / 507 / 10 | 944 / 83 / 0 ; 421 / 602 / 0 |
| BTC day at 17:00 New York (`ny17`) | BTC M5 / M15 | 1,042 / 1,042 | 750 / 722 ; 707 / 684 | 525 / 502 / 15 ; 520 / 503 / 19 | 941 / 0 / 86 ; 403 / 0 / 620 |

- **The UTC-5 clock.** It moves the range by an hour from March to November. Its labels and first breakouts are
  therefore other events, not a shifted copy.
- **ORB-CX.** On M15 it is the 08:30-09:00 range (section 8, item 1). Gold's M15 COMEX range is one session
  shorter: on 2021-03-02 no bar opens in the session.
- **The day reset.** Neither alternative day boundary moves a label, an entry or the trade's state between 10:00
  and 16:55 New York. Each moves only what happens after 17:00: raw breakouts, hits, first breakouts and the script's
  bookkeeping.
- **Every count of section 6 is recorded** in `tests/test_tradeiq2_ind_orb.py`, with the HV labels and the hit counts
  of every configuration.

## 7. What may still differ from TradingView

1. **The bars.**
   - Our bars are built from Exness's tick archive, on the bid, on UTC boundaries. New York's offset from UTC is a
     whole number of hours, so they are New York bars too.
   - TradingView's Exness feed may differ tick by tick, and may have bars where our archive has holes. That
     concerns gold's 2016-05-18, and the COMEX sessions of 2021-03-02 and 2023-11-22.
2. **The trading day of the feed** (reading 3).
   - The ports assume 17:00 New York for gold and 00:00 UTC for BTC.
   - TradingView defines the daily bar of a broker's CFD by the broker's session, which could differ, especially for
     BTC on a CFD feed.
   - Section 6 shows what the alternatives change: hits, raw breakouts and first breakouts after 17:00, and the
     script's bookkeeping. They change no label and no entry.
3. **The clock.**
   - The script can only use fixed offsets (l.35). A TradingView user who wants New York time must switch between
     UTC-5 and UTC-4 by hand twice a year.
   - The plan's version uses the real New York clock instead, as PREREG 6.5 says. The literal clock is the control.
4. **Session membership for COMEX on M15** (reading 1). Pine's `time()` puts a bar in the session by its open time;
   that is the documented behaviour, but only a TradingView chart can confirm it for an 08:20 start on M15.
5. **Volume.**
   - On TradingView the HV tag of an Exness BTC chart reads Exness's own tick volume. The plan uses Binance volume
     for BTC (PREREG 2), so the study's HV / LV split for BTC is deliberately not TradingView's.
   - With Exness tick volume, 316 (M5) and 264 (M15) of BTC's 2019-2022 labels would carry the other tag.
6. **Built-in functions.**
   - `ta.sma` and `ta.atr` are native code on TradingView. The ports follow the published reference code.
   - Any difference would be in the last bits, and that moves no label, tag or trade on our bars (readings 9 and 11).
7. **Comparisons with a missing value** (reading 4). Not documented. The reading affects only the first bar's
   new-day flag.
8. **The live bar.** In real time, labels are drawn and removed tick by tick until the bar closes, and alerts fire on
   every cross unless set to "once per bar close". Closed bars never change.
9. **The script's own bookkeeping** is not a backtest, by design. It books entries at the range edge, ignores costs,
   and drops gold's trades at the break. The study's rules fill at the next M1 open and are flat by 16:55 New York
   (PREREG 4 and 6.5).

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

They are written before any ORB result exists. None changes a rule. Each says which rows it can move.

1. **ORB-CX on M15 is the 08:30-09:00 range.**
   - **What.** PREREG 6.5 names the COMEX-open range 08:20-08:50 New York, on both timeframes. The ports follow the
     script's session test (l.87), which takes a bar into the session when the bar opens inside it.
   - **The consequence.** 08:20 is not on the 15-minute grid. So on M15 the session's bars are the 08:30 and 08:45
     bars, the range covers 08:30-09:00, and the first bar after the session is the 09:00 bar. On M5 the range is
     exactly 08:20-08:50.
   - **The alternatives**, on gold M15 in 2019-2022 (1,030 sessions):
     - every bar that overlaps 08:20-08:50 (08:15-09:00) changes 795 ranges and 193 first breakouts;
     - only bars wholly inside (08:30-08:45) changes 784 ranges and 489 first breakouts.
   - **Affects:** the four ORB-CX rows on gold M15 (O1 and O5, with F0 and F2-4H). Not the M5 rows.
2. **The day reset is the feed's own trading day.**
   - **What.** The script ends its day, its hit window and its labels when the daily bar changes (l.88, 147, 246).
     PREREG 6.5 does not say which day that is. The ports take TradingView's convention:
     - gold's day starts at 17:00 New York, with daylight saving: the reset falls on the 18:00 reopen and on the
       Sunday open;
     - BTC's day starts at 00:00 UTC, 19:00 New York in winter and 20:00 in summer.
   - **Why.** The script's empty session string means its timezone input cannot move the daily bar.
   - **What it moves.** It sets the span in which hits, raw breakouts and the first breakout are counted: from the
     10:00 bar to the reset. It moves no label, no entry and no trail exit before 16:55 New York.
   - **The alternatives,** measured on 2019-2022:
     - Midnight on the session clock changes the hit flags of 176 of 1,031 gold sessions and 232 of 1,042 BTC
       sessions. It changes the first breakout of 21 (M5) / 32 (M15) gold sessions and 4 / 3 BTC sessions, and no
       label.
     - A 17:00 New York day for BTC changes the hit flags of 193 BTC sessions and 6 first breakouts per timeframe.
   - **Affects:** O4 (its causal hit rates) and its LV control, on both symbols and timeframes; claims 6 and 8. Not
     O1-O3 or O5.
3. **Claim 6 uses only first breakouts that close by 16:00 New York.**
   - **What.** The ports report the day's first breakout as the script's alert condition: the first close beyond
     the range from 10:00 up to the day reset. On BTC that can come after the 17:00 window, without a label.
   - **The reading.** Claim 6 asks whether the 16:00 close lies beyond the range on the side of the first breakout.
     That can be tested only when the first breakout's bar closes by 16:00. A session whose first breakout comes
     later counts as a session without a breakout.
   - **How many, in 2019-2022.**
     - First breakouts closing after 16:00: gold 0 (M5) and 2 (M15); BTC 12 and 13.
     - Of BTC's, 6 per timeframe come after 17:00.
   - **Affects:** claim 6 only.
4. **O4's hit rates count a target as the script does.**
   - **What.** A target counts when the session first touches it, from the 10:00 bar up to the day reset. Only
     sessions the script counts are in the denominator.
   - **What this implies.**
     - A touch after the 16:55 flat time counts, as on the script's dashboard, although an O4 trade is flat by
       then.
     - On BTC, 35 to 68 of each level's first touches in 2019-2022 come after 16:55. On gold, at most 2.
     - O4's rates are "after past breakouts in that direction". The ports record only a target's first touch. That
       touch comes before the breakout's label in 0-3 gold and 1-6 BTC sessions per level in 2019-2022, so the rule
       module must decide whether such a session counts as a hit after the breakout.
   - **Affects:** O4 (and its LV control) on both symbols; claim 8.
5. **A session with missing bars keeps the range of the bars it has.**
   - **What.** If a data hole runs from inside a session into the next trading day, the session is counted with no
     range at all, so it can give no breakout and no trade. This is the script's behaviour.
   - **Where, in 2019-2024H1.** Only on gold's ORB-CX:
     - 2021-03-02 on M5: one 08:20 bar, then no data until Wednesday 19:00. Counted with no range.
     - 2023-11-22 on M5 (the 08:20, 08:25 and 08:45 bars) and on M15 (the 08:45 bar only), in Validation.
   - **Not affected.** The 09:30 sessions of both symbols are complete from 2019. Gold's one short session,
     2016-05-18, is warm-up.
   - **Affects:** the ORB-CX rows (O1, O5) on 2023-11-22 in Validation, on both timeframes.
6. **The HV tag's arithmetic.**
   - **What.** HV means the breakout bar's volume is strictly above the 20-bar average, the bar included, as PREREG
     6.5 says. The average is summed in TradingView's reference order (study 1's `pine_sma`), and a bar is LV
     while fewer than 20 bars exist.
   - **Why it matters.** Integer tick volumes often equal their average exactly, so another order of addition can
     flip a tag at such a tie.
   - **The measured effect, in 2019-2024H1.**
     - No label of any planned HV, LV or HV + F2-4H row flips (gold tick volume, BTC Binance volume).
     - One gold M15 label of the UTC-5 control flips (O1, which does not read the tag).
     - One BTC label per timeframe flips on Exness tick volume, which the study does not use.
   - **Affects:** in principle the HV, LV and HV + F2-4H rows; in Development and Validation, none.
7. **O1's trail uses the ports' ATR, not the harness's.**
   - **What.** The script's trail is `low - 2 * ATR(14)` (a short: `high + ...`). The ports compute `ta.atr(14)` in
     the reference order, `alpha * tr + (1 - alpha) * previous` (study 1's `tradeiq_ind.atr`). The harness's
     `tradeiq2_market.atr14` uses `external.wilder_atr`, `(previous * 13 + tr) / 14`.
   - **The difference.** The two agree to 2e-15 relative. On the study's bars to 2024-06-30 the trail's decimals
     differ on 331-1,512 bars per series and configuration, and no bar's trade state changes.
   - **The reading.** O1 and O5 read the ports' `trail` and `active_dir` (or their `atr`), and do not rebuild the
     trail from `atr14`.
   - **Affects:** O1 and O5 (their trail exits), and only at an exact tie of a close with the trail.

## 9. Notes for the rule module

- **Entries.** A label on a bar that closes after 16:00 New York is not an entry (PREREG 6.5). There are 5 such gold
  labels and 38 (M5) / 45 (M15) BTC labels in 2019-2022. The label's tag and the trade the script opens still
  exist in the outputs.
- **The script's trades.** The `trade2_*` columns are the script's second trade of a day. O1 is "the script's trade",
  so a second label on the other side after a trail exit is a new event for it.
- **The session table.** A row exists from its `post_bar` (the 10:00 bar on the 09:30 session) and is complete at
  `span_end`. A causal hit rate counts only rows whose `span_end` lies before the decision. Rows with a missing
  `or_high` (the wiped session) have no range.
- **The volume.** BTC rows that read HV must pass Binance volume (`Context.volume`). Gold's is the tick volume.
- **The day reset.** `day_boundary='auto'` needs the symbol: `orb(..., symbol="XAUUSDm")`.
