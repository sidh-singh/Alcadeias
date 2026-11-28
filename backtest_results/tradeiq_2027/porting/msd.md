# Market Structure Dashboard (Flux Charts): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values and event counts. No
dashboard rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_msd.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_msd.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_msd.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_msd_a.py` and `tests/test_tradeiq2_ind_msd_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.2 (MSD-A1..A3, MSD-F4, MSD-F6, BOS-trend), 6.10 (STK-RM, STK-RMA) and claims
  13-14 of section 8; study 3's MSD filter (`backtest_results/bot_filters/PREREG.md`) reads the same bias.
- **The script:** "Market Structure Dashboard | Flux Charts", Pine v6, MPL-2.0, (c) fluxchart. It is third-party code.
  Line numbers (L...) refer to the owner's copy (1,749 lines). The source is not in this repository.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- On the 1H, 4H and 1D charts of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports give
  the same numbers, bit for bit, on every output and every bar. The same holds for each timeframe row on its own
  bars, for every event (pivots, breaks of structure, order blocks with their price levels, fair value gaps) and for
  the weekly bars. Gold was also run from study 1's later start. No tolerance was needed anywhere.
- Model B, the live "forming candle" version that claim 14 needs, exists only in port A. It is now checked bar for
  bar against an independent construction on port B's engine, and agrees everywhere.
- The reconciliation found one mismatch, in port B's weekly bars at a data end inside a week. It is fixed. It cannot
  appear on the study's bars before the hold-out, which end on a Monday (section 4).
- A third implementation, the read-only probes of the planning pass, builds its own bars. It agrees on every bar,
  every pivot under all four tie readings and every daily and weekly break of structure (section 5).
- Two facts matter for the plan (section 8):
  - BTC's daily and weekly rows still depend on where our data start until the end of June 2019. That affects 849 /
    260 / 60 Development labels (1H / 4H / 1D charts).
  - Gold's dashboard depends on the data start until 2018-05-19, well inside the gold Early window (exam 2).

## 1. What the script computes

All settings are the script's defaults (L62-127, L165, L172); nothing is tuned. The dashboard is a context tool: it
produces no entry, stop or target. Its one output that matters for trading is the **trend bias**, one of five labels:
BULLISH, LEAN BULL, NEUTRAL, LEAN BEAR, BEARISH.

1. **The rows (L62-88, L692).**
   - The bias is a weighted vote over the timeframes at or above the chart's.
   - On a 1H chart the rows are 1H, 4H, D and W, with weights 2, 2, 3 and 4. On a 4H chart they are 4H, D and W; on a
     1D chart, D and W.
   - The lower rows (1m, 5m, 15m) are switched off on these charts and count nowhere.
2. **Each row runs on its own bars (L695-701)** and gives four votes of -1, 0 or +1:
   - **Structure (L249-250, L369-425).**
     - A pivot high is a bar whose high is strictly above the highs of the 5 bars before it and the 5 bars after it,
       so it is known 5 bars late (5 weeks on the weekly row). Pivot lows are the mirror.
     - A new pivot high is "higher" (HH) if it is above the previous pivot high, otherwise "lower" (LH); an equal one
       counts as lower. Pivot lows give HL or LL in the same way.
     - The vote is +1 when the latest high and the latest low are both "higher", -1 when both are "lower", else 0.
     - On top of that comes a "real-time" check on every bar that is never stored: a close above the pivot high
       before the latest one counts as HH, and a close below the pivot low before the latest one counts as LL.
   - **Order block (L483-586).**
     - A break of structure (BOS) is a close above the last unbroken pivot high (with the previous close at or below
       it). The bearish break is the mirror. Each pivot can break only once, and a newer pivot replaces an unbroken
       one.
     - At a bullish break, the candle with the lowest low between the pivot and the break (at most 51 bars) becomes a
       bullish zone, wick to wick. A bearish break gives the candle with the highest high.
     - A zone that touches or overlaps a zone of the same side is dropped, and a row keeps at most 6 order blocks.
     - A bullish zone dies when a close falls below its bottom; a bearish one when a close rises above its top.
     - The vote is the side of the nearest surviving zone, measured from the row's close to a bullish zone's top or a
       bearish zone's bottom. A tie between the two sides goes bearish, and no zone gives 0.
   - **Fair value gap (L251-254, L589-623).**
     - A three-candle gap, found on the bar after the third candle. Bullish: the third candle's low is above the first
       candle's high, the middle candle closed up (above its open or above the previous close), and the gap comes
       from the middle candle only.
     - At most 6 gaps are kept, and a gap dies when a wick trades through it.
     - The vote is the side of the nearest gap, as for order blocks.
   - **Swing position (L705-708, computed at L1330 with the chart's own close).**
     - Where the chart's close sits in the row's last swing range, from the last pivot low to the last pivot high.
     - Below the range: -1. Above it: +1. In its bottom 30%: +1 ("discount"). In its top 30%: -1 ("premium"). In the
       middle: 0.
     - When the last pivot high is below the last pivot low, the range shrinks to one tick, and the vote is simply
       which side of the swing low the close is on.
3. **The label (L703-737, L1323-1346).**
   - The row score is the sum of its four votes, from -4 to +4.
   - The points are the weighted sum of the row scores. The maximum is 4 times the weights: 44, 36 and 28 on the 1H,
     4H and 1D charts.
   - Above 50% of the maximum the label is BULLISH, above 20% LEAN BULL, below -50% BEARISH, below -20% LEAN BEAR,
     otherwise NEUTRAL. The comparisons are strict, so exactly 50% is LEAN.
4. **BOS-trend** is our own rule (PREREG 6.2), not the script's: the side of the chart row's most recent break of
   structure.
5. **Not ported**, because nothing in the bias or in a registered rule uses them: the EMA trend column (off in the
   bias, L121; port A returns it for information), the volume and volatility states, sessions, kill zones,
   previous-day/week/month levels and the alerts (L1111-1293, L1636-1749).

**Timing.**
- The script draws its table on the last bar only and keeps no history. The bias therefore has to be rebuilt bar by
  bar; TradingView cannot show what the dashboard said yesterday.
- **Model A** (the study's model) gives each higher row the values of its last CLOSED bar, which is what TradingView
  shows on historical bars (PREREG 5 and 6.2). A day is visible on a 1H chart from the 1H bar that closes with it.
- **Model B** (claim 14) is what the live dashboard shows at a chart close. Each higher row is computed on its forming
  candle: the row's state after its last closed bar, stepped once on the candle so far (its open, the high and low so
  far, and the current close), and then rolled back.

## 2. What was compared, and how

- **The bars.** The study's harness, `tradeiq2_market.load(symbol, end="2024-07-01")`, with study 2's hold-out guard
  closed, so nothing from 2024-07-01 on was loaded.
  - 1H, 4H and 1D are study 1's bars (UTC boundaries; a UTC day with fewer than 360 M1 bars is merged into the next).
    The weekly row is the harness's `tbars("1W")`.
  - Gold starts on 2016-01-03 (the 2016 warm-up months) and BTC on 2018-01-01.
  - Gold was also run from 2017-01-03, study 1's start: the span both port authors and the planning probes used.
    Study 1's gold bars are exactly the later part of the study's bars.
- **What had to agree.**
  - Every dashboard output on all three charts, with the same types: label, score, maximum, and for each active row
    its score and four votes, plus `bos` and `bos_trend`. That is 25 outputs on the 1H chart, 20 on 4H and 15 on 1D.
  - Each of the four rows on its own bars: the pivot prices and swing levels (decimal numbers compared by their
    64-bit patterns, with missing values on the same bars), the structure vote and the two types after the
    real-time check, the two zone votes, the reclaim flags and the number of zones held.
  - The event tables of every row: pivots (bar, price), breaks of structure (bar, side), order blocks made (bar,
    side, top, bottom), order blocks dropped as overlapping, fair value gaps (bar, side).
  - The weekly bars of both ports' builders and of the harness, bar for bar.
  - Model B: port A's forming-bar values at every chart bar against port B's row stepped on the same forming candle
    and rolled back afterwards, as Pine does before each live tick. On the way the check also confirms that the
    forming candle ends as the closed bar (open, high, low and close) and that the rollbacks leave the closed-bar
    path untouched.
- **Synthetic markets** (six, built by the study's own harness from synthetic M1 bars, all ending on a Wednesday so
  that the last 4H, day and week bars are still forming; both models). They cover what the real bars do not reach:
  - gold's calendar: the Sunday stub, the daily break, a short holiday Friday and a two-day hole, with prices on a
    0.5 grid, so equal highs and lows are common;
  - BTC climbing from 2,000 to 260,000, so that old zones end up more than 100,000 away from the close (the
    script's "invisible beyond 100,000" sentinel, L427-449);
  - a flat market with rare spikes, which gives bars that are both a pivot high and a pivot low.
- **A mutation check of the reconciliation test** (scratch, outside the repository). One wrong reading at a time was
  planted in one port, and the test failed every time:
  - the real-time check against the latest pivot instead of the one before it;
  - gaps mitigated by the close instead of the wick;
  - pivot ties allowed;
  - the swing vote's 30% threshold made inclusive;
  - weeks by the close time instead of the close time minus one second (this one shows on 24/7 data only: gold
    has no Sunday day bar);
  - a strict merge (`<` instead of `<=`);
  - model B's rollback leaking the zone arrays;
  - model B's running high and low replaced by the last chart bar's.
  One planted change was not caught, rightly: model B's forming open. A bar's own open never enters its own step
  (only `_green[2]` reads an open, two bars later).
- **Running it.** All three test files pass together: 80 tests in about 50 s, at a peak of 1.4-1.6 GB of memory
  (one M1 store in memory at a time). The reconciliation file alone has 19 tests and takes about 30 s at about
  1.3 GB. Set `NUMBA_CACHE_DIR` to a scratch folder, as for port A's own tests.

## 3. The Pine readings, with their evidence

The effects are changed labels on chart bars closing in Development (2019-01-01 to 2022-12-31) of the study's bars:
gold / BTC, each as 1H / 4H / 1D chart. They are counts, never profit or loss. Both ports implement every reading
below in the same way.

| # | Item (lines) | Reading used | Evidence | The alternative, and what it would change |
|---|---|---|---|---|
| 1 | Pivot ties (L249-250) | Strict on both sides: the pivot's high must beat all 10 neighbours | PREREG 6.2; TradingView does not document ties | An equal value allowed on the newer side: 15 / 0 / 0 and 0 / 0 / 0 labels. On the older side: 7 / 0 / 0 and 7 / 0 / 0. On both: 16 / 0 / 0 and 7 / 0 / 0. Extra pivots over the whole span: gold 1H 5 / 5 / 10 of 6,200, gold 4H 2, BTC 1H 1 / 1 / 2, none on D or W |
| 2 | Equal pivots in the structure (L384, L393) | An equal high is LH, an equal low LL | `currH > prevH ? 1 : -1` | None. (The overlay labels at L664 and L677 call a tie HH or HL; display only, off by default) |
| 3 | The real-time check (L405-417) | Against the pivot before the latest one (`prevL`, `prevH`); applied on every bar, never stored | As written | Against the latest pivot (a tempting "fix"): 3,237 of gold's 1H-chart labels to 2024-06 change. A trap test in both ports |
| 4 | Whose close the swing vote uses (L705-708, L1330) | The chart's close, against the row's swing high and low | L1330 is outside `request.security` | The row's own close: 2,629 / 709 / 73 and 2,902 / 711 / 70 |
| 5 | The tick in the swing range (L706) | 0.001 gold, 0.01 BTC (the store's price digits) | `syminfo.mintick` of the Exness symbols | Ten times the tick: 0 labels anywhere. It matters only when the last pivot high is below the last pivot low and the close is within a tick of the swing low |
| 6 | Inverted swing ranges (L706) | As written: the range becomes one tick | `math.max(swingH - swingL, syminfo.mintick)` | Not an alternative, a trap. Such bars are 0.90 / 0.91 / 0.97 / 0% of gold's Development row bars (1H / 4H / D / W) and 0.15 / 0.59 / 0.96 / 0% of BTC's |
| 7 | Missing values (L703, L706, L1338) | A row without a value yet votes 0 but still counts in the maximum; a missing swing gives a swing vote of 0 | `dirScore(na)` is 0; `math.max` with na is na; `tfActive` depends on the timeframes only | Only the first bars of the data (2016 / 2018) |
| 8 | Zone caps (L165, L172, L475-477, L616-620, L688-689) | 6 zones per row and kind, both sides together; a new gap is capped before the mitigation | The bias's own arrays are built with `obLookback` and `fvgLookback`, inputs of "Visual Overlays" | Caps treated as display only, or the order swapped: trap tests in both ports |
| 9 | What kills a zone (L455-473) | Order blocks by the close, gaps by the wick, also on a gap's detection bar | As written | Gaps by the close: 8,527 of gold's 1H-row gap votes to 2024-06 change |
| 10 | The order-block candle (L483-499, L509-524) | Bars after the pivot up to the break bar, at most 51; the latest bar on a tie; the candle's full range | `for i = 0 to max(0, min(barsBack, 50))`, strict `<` from the break bar back | Trap test in both ports |
| 11 | Overlap (L501-507) | Touching counts as overlap; only zones of the same side | `top >= ob.bottom and bottom <= ob.top` | Trap test in both ports. 271 / 65 / 10 / 3 gold and 463 / 104 / 14 / 0 BTC Development order blocks are dropped this way (1H / 4H / D / W) |
| 12 | Break of structure (L325-326, L537-565) | The new pivot is stored before the break is tested; each pivot breaks once; at most one break per bar | As written | Trap test in both ports |
| 13 | The gap pattern (L251-254) | Candles k-3, k-2, k-1, found on bar k; "green" includes a close above the previous close | As written | Trap test in both ports |
| 14 | Nearest zone (L426-453) | Both best distances start at 100,000.0 (a price): a zone 100,000 or more from the close is ignored; a bull / bear tie is bearish | As written | Unreachable before the hold-out (no BTC close above 100,000); reachable in it. Ported literally |
| 15 | Active rows and maximum (L692, L1336-1340) | 1H chart: 1H, 4H, D, W (44); 4H: 36; 1D: 28 | As written | None |
| 16 | The label (L1343-1344) | Computed in integers: BULLISH when 2p > m, LEAN BULL when 5p > m, and the mirrors | Equal to the script's division for every reachable score (both ports assert it on every bar; the planning probe checked every chart) | None possible |
| 17 | When a closed higher bar reaches the chart (L695-701) | At the chart bar with `tc_row <= tc_chart` (`tradeiq_market.htf_at`) | PREREG 5 | TradingView's historical placement, on the last chart bar inside the higher bar: 47 / 3 / 0 and 2 / 1 / 0 (section 7) |
| 18 | Weekly bars (PREREG 2) | The ISO week of a day bar's last UTC day; the week closes with its last day bar; a forming last week closes at its ISO end | DEVIATIONS 1 | Weeks by the day bar's open time: 4,132 / 1,265 / 248 and 0 / 0 / 0 |
| 19 | Day and 4H boundaries (PREREG 2) | UTC, as study 1 | PREREG 2 | TradingView's 17:00 New York session for gold: section 7 |
| 20 | Where the history starts (PREREG 3) | The first bar of the study's data | PREREG 3 | A start 182 days later: gold 0 / 0 / 0, BTC 849 / 260 / 60, all before 2019-07-01 (section 6) |
| 21 | Model B (claim 14) | The row's state after its last closed bar plus one tentative step on the forming candle (open of its first chart bar, high and low so far, the chart close), nothing kept; a chart bar inside no higher bar (only at a data end) takes the last closed values | Pine rolls `var` state back before every live tick (the map, section 2.3) | Model B's label differs from model A's on 19.1 / 18.1 / 13.7% and 19.9 / 20.0 / 15.5% of Development bars |
| 22 | `bos` and BOS-trend (L537-565, L633) | The chart row's `trackPivotBreaks`, the same as the script's chart-level call | As written | None |

## 4. Mismatches found, and how each was resolved

**One mismatch: port B's weekly bars when the data end inside a week.**
- **The rule.** Model A shows a higher row only from its last closed bar (PREREG 5). A week whose days are still
  coming is not closed. DEVIATIONS 1 already reads it that way: "A last week that the data end cuts before its ISO
  end closes at that ISO end, so it is never read as closed."
- **Port A** (`weekly_bars(day_bars, end_s)`) and the harness (`TMarket2.tbars("1W")`) apply that rule.
- **Port B's** `weekly_bars(day_bars)` had no data end. A forming last week closed with its last day bar, so on day
  bars cut on a Wednesday the last chart bars would have read Monday to Wednesday as a closed week.
- **Who was right.** Port A. This is not a Pine question but the plan's: a forming week is not a closed bar.
- **Why the real bars never showed it.** The study's bars end on Monday 2024-07-01 00:00 UTC, exactly at a week
  boundary. It would have shown at the hold-out's ends (gold on a Thursday, BTC on a Friday), and in any test that
  cuts the data inside a week.
- **The fix.** Port B's `weekly_bars` takes an optional `end_s` with port A's meaning, and its bars gained a
  `complete` flag. Without `end_s` it behaves as before.
- **The tests.**
  - Port B's own tests gained a hand-computed case,
    `test_weekly_bars_a_forming_last_week_closes_at_its_iso_end`.
  - The reconciliation compares both builders on real day bars cut on a Wednesday, and both builders against the
    harness on the six synthetic markets, which all end inside a week.
- **Effect on the study:** none before the hold-out.

**No other mismatch.**
- Every output was equal bit for bit on both symbols, both gold starts and the six synthetic markets, under both
  models.
- No arithmetic needed aligning. Every computed decimal number is a single operation done in Pine's order by both
  ports:
  - the zone distances `top - close` and `bottom - close` (L435, L439);
  - the swing range and percentage `(close - swingL) / swingRange * 100` (L706-707).
  Every other decimal is a copied price, and every dashboard output is an integer.

**Differences that are not mismatches** (outside the shared contract):
- **Model B** is port A's alone (by the task). It is now cross-checked through port B's engine (section 2).
- **Extras.** Port A has `row_values`, `rows_for`, `convergence` and `swing_factor`. Port B has `ties=` for the tie
  readings and the zone distances. Neither is part of the contract.
- **Tick lookup.** Port B also reads a `mintick` attribute from the chart's bars before falling back to the symbol;
  port A uses the symbol. The study's bars carry no such attribute, so both use 0.001 and 0.01.
- **Input checks.** Port A requires open times that increase and closes after opens; port B requires closes that
  increase. Both accept every bar set of the study.

**Corrections to the two ports' own notes** (measured again here, on the study's 2016 span):
- **The convergence check compares too little.** The map's check compares a row's votes and swing levels, and it
  says gold's rows agree from 2018-05-19. The row's full internal state (both zone arrays and the pivot and break
  trackers) becomes identical later: on gold's weekly row only after the week closing 2019-06-15, on BTC's after the
  week closing 2019-08-26. Between the two dates model A's values were already identical, but model B's were not:
  - gold: 7 / 3 / 1 Development labels differ against a start 182 days later, the last closing on 2019-01-22;
  - BTC: 807 / 262 / 61, the last closing at 2019-06-26 00:00.
  From those weeks on, the runs from the two starts are identical for good, the hold-out included.
- **Model B against model A.** Port A reported 19.0 / 18.0 / 13.6% for gold on study 1's 2017 start (4,491 / 1,152 /
  140 bars). On the study's 2016 span they are 19.1 / 18.1 / 13.7% (4,497 / 1,155 / 141), for the reason just given.
  BTC's are unchanged.
- **Weeks by open time.** Port B measured 4,073 / 1,249 / 244 changed gold labels on study 1's span. On the study's
  span it is 4,132 / 1,265 / 248.
- **Convergence dates.** Port A gives the open time of the first agreeing bar, port B its close time: BTC's daily row
  2019-06-26 against 2019-06-27, and the weekly row 2019-06-24 against 2019-07-01. These are the same bars.
- **Gold's weeks.** On the study's span there are 443: 428 open with the Sunday stub, 7 on a Monday, 4 on a Tuesday,
  1 on a Wednesday and 3 on a Friday (holiday Fridays merged into the next Monday). On study 1's span there are 391
  (379 / 7 / 3 / 0 / 2).

## 5. A third opinion: the probes of the planning pass

The map's author wrote three read-only probes before the plan (scratch `work/msd/probe_pivots.py`,
`probe_warmup.py`, `probe_ties.py`). They read the store's M1 files directly and build their own 1H, 4H, day and week
bars, with their own pivot test and their own break-of-structure loop. They were run as they are, and their functions
were also called on their own bars, from outside the repository. They cover study 1's span: gold from 2017-01-03,
BTC from 2018-01-01, to 2024-06-30.

- **The same bars.** All four rows of both symbols are identical to the harness's, bar for bar (open and close times,
  open, high, low, close).
- **The same pivots.** Strict pivots fall on the same bars, and so do the extra pivots of each tie reading:
  - gold 1H: 2,699 highs and 2,764 lows; ties on the newer side add 4 / 1, on the older side 3 / 2, on both 7 / 3;
  - gold 4H: 792 / 816, plus 2 highs with ties on the newer side;
  - gold D and W: 117 / 108 and 23 / 26, no extra pivots;
  - BTC 1H: 3,775 / 3,793, plus 1 / 1 / 2 highs;
  - BTC 4H, D and W: 932 / 933, 139 / 158 and 17 / 19, no extra pivots.
- **The same derived counts.**
  - Bars that are both a pivot high and a pivot low: gold 32 / 45 / 2 / 0 and BTC 94 / 20 / 2 / 0 (1H / 4H / D / W).
  - Inverted swing ranges: gold 269 / 120 / 10 / 0 and BTC 119 / 53 / 23 / 7.
  - Weeks: gold 391 (379 opening on Sunday, 7 Monday, 3 Tuesday, 2 Friday) and BTC 339, all opening on Monday.
- **The same warm-up.**
  - Structure is ready (two pivots on each side) at the close of gold's daily bar of 2017-02-23 and weekly bar of
    2017-08-19, and of BTC's 2018-02-03 and 2018-09-03.
  - The breaks of structure before 2019 are gold D 27, gold W 5 (2 bullish, 3 bearish), BTC D 14 and BTC W 2 (both
    bearish).
  - The complete lists of daily and weekly breaks to 2024-06 (gold 85 and 19, BTC 107 and 12) are identical, event
    by event.
- **The label rule.** `probe_ties.py` confirms that the integer rule and the script's division give the same label
  for every reachable score of every chart.
- **Differences:** none. These counts are in the reconciliation test (`PROBE_PIVOTS`, `PROBE_WARMUP`,
  `PROBE_WEEK_OPENS`), so a change to either port that moved them would fail it.

## 6. Event counts per symbol and timeframe, 2019-2022

**The data.**
- The study's bars; values from port A and port B, which are identical.
- The window is the chart or row bars that close after 2019-01-01 00:00 UTC and at or before 2023-01-01 00:00, as in
  both ports' reports and the recorded values of the test. The harness counts a Development decision only if it
  fills before 2023-01-01, which drops one bar per series: gold's last 2022 bar, closing on Friday 30 December, and
  BTC's bar closing at exactly 00:00 on 1 January.
- Counts only: no rule was run and no profit or loss was computed.

**The charts** (model A unless stated):
- **A1 / A2 / A3:** how often the state of MSD-A1 (long / flat / short), A2 (long / flat) and A3 (BULLISH long,
  BEARISH short, else flat) changes.
- **F6 veto:** the share of bars on which MSD-F6 would hold a long flat (the 4H, D and W rows all score below 0; on a
  1D chart D and W) or a short flat (all above 0).

| Chart | Bars | BULLISH / LEAN BULL / NEUTRAL / LEAN BEAR / BEARISH | Label changes (a year) | A1 / A2 / A3 changes | BOS bull / bear | BOS-trend flips | BOS-trend long | F6 veto long / short | Model B label differs |
|---|---|---|---|---|---|---|---|---|---|
| Gold 1H | 23,591 | 3,540 / 6,034 / 9,047 / 4,072 / 898 | 3,137 (784) | 2,038 / 1,081 / 1,106 | 576 / 506 | 540 | 54.0% | 6.4% / 16.5% | 19.1% |
| Gold 4H | 6,386 | 1,327 / 1,294 / 2,314 / 1,028 / 423 | 984 (246) | 607 / 323 / 386 | 159 / 146 | 158 | 55.3% | 6.4% / 16.4% | 18.1% |
| Gold 1D | 1,032 | 298 / 151 / 302 / 177 / 104 | 241 (60) | 154 / 78 / 102 | 28 / 17 | 18 | 55.0% | 17.6% / 32.3% | 13.7% |
| BTC 1H | 35,017 | 4,898 / 10,670 / 13,985 / 4,866 / 598 | 4,391 (1,098) | 3,196 / 2,016 / 1,204 | 882 / 770 | 806 | 54.3% | 3.1% / 19.5% | 19.9% |
| BTC 4H | 8,757 | 1,542 / 2,644 / 3,177 / 1,180 / 214 | 1,313 (328) | 892 / 560 / 430 | 222 / 193 | 210 | 54.0% | 3.2% / 19.4% | 20.0% |
| BTC 1D | 1,460 | 345 / 425 / 408 / 226 / 56 | 320 (80) | 212 / 130 / 114 | 36 / 29 | 30 | 54.0% | 7.1% / 38.4% | 15.5% |

**The rows** (each on its own bars):

| Row | Bars | Pivot highs / lows (a year) | Both on one bar | BOS bull / bear | Order blocks made bull / bear | Dropped as overlapping | Gaps bull / bear | Inverted swing range |
|---|---|---|---|---|---|---|---|---|
| Gold 1H | 23,591 | 1,445 / 1,508 (738) | 14 | 576 / 506 | 423 / 388 | 271 | 2,385 / 2,149 | 0.90% |
| Gold 4H | 6,386 | 418 / 443 (215) | 25 | 159 / 146 | 121 / 119 | 65 | 698 / 575 | 0.91% |
| Gold D | 1,032 | 67 / 63 (32.5) | 1 | 28 / 17 | 21 / 14 | 10 | 123 / 100 | 0.97% |
| Gold W | 209 | 11 / 15 (6.5) | 0 | 5 / 5 | 4 / 3 | 3 | 30 / 20 | 0% |
| BTC 1H | 35,017 | 2,309 / 2,338 (1,162) | 53 | 882 / 770 | 628 / 561 | 463 | 2,974 / 2,659 | 0.15% |
| BTC 4H | 8,757 | 568 / 579 (287) | 14 | 222 / 193 | 157 / 154 | 104 | 800 / 679 | 0.59% |
| BTC D | 1,460 | 84 / 99 (46) | 2 | 36 / 29 | 27 / 24 | 14 | 178 / 124 | 0.96% |
| BTC W | 208 | 11 / 9 (5) | 0 | 4 / 4 | 4 / 4 | 0 | 30 / 23 | 0% |

- **The weekly row is slow.** It carries 4 of 11 parts of the 1H chart's maximum (4 of 9 on 4H, 4 of 7 on 1D), yet
  it confirms about six pivots a year, each five weeks late, and made 7 (gold) and 8 (BTC) order blocks in four
  years.
- **Whole span** (data start to 2024-06-30): gold 49,956 / 13,500 / 2,183 / 443 bars (1H / 4H / D / W), BTC 56,840 /
  14,225 / 2,372 / 339. Gold's 1H row has 3,069 / 3,131 pivots (730 a year).
- **Warm-up on the study's span.**
  - Structure is ready on gold's rows at the closes of 2016-01-05 (1H), 2016-01-12 (4H), 2016-03-23 (D) and
    2017-01-21 (W). The weekly row is therefore ready three weeks into the gold Early window.
  - BTC's rows are ready on 2018-01-02, 2018-01-09, 2018-02-03 and 2018-09-03.
  - From 2019 every row of both symbols has both swing levels and both structure types on every bar.
  - BOS-trend is never "none" from 2019.
- **Does the start of the data matter?** The map's pre-registered check compares each row from the data start with
  the same row started 182 days later.
  - **Gold** (on the study's span).
    - The rows' votes and swing levels agree from the bar closing at 2016-07-15 15:00 (1H), 2016-07-21 00:00 (4H),
      2016-11-24 (D) and 2018-05-19 (W).
    - On the charts no Development or Validation label differs, against either a later start or study 1's 2017
      start.
    - Before 2018-05-19 labels do differ. Against a start 182 days later: 2,734 / 876 / 213 of the Early window's
      11,798 / 3,186 / 515 chart bars. Against the 2017 start: 3,962 / 1,223 / 241.
  - **BTC.**
    - The votes agree from 2018-07-12 (1H), 2018-07-27 (4H), 2019-06-27 (D) and 2019-07-01 (W).
    - 849 / 260 / 60 Development labels (1H / 4H / 1D charts) differ, the last on 2019-06-30. They come from the
      daily row's order-block vote and the weekly row's structure, order-block and gap votes.
    - The breaks of structure and BOS-trend never differ.
  - **The full internal state** converges later still (section 4), which matters for model B only.

## 7. What may still differ from TradingView

1. **Gold's bars: UTC days against TradingView's trading session.**
   - The study's day, 4H and week bars are on UTC boundaries (PREREG 2). TradingView's forex and CFD gold symbols
     (for example OANDA:XAUUSD) roll the day at 17:00 New York, align their 4H bars to that, and start the week with
     Sunday's session.
   - This was measured with session bars built from the same M1 data (a scratch measurement; one plausible
     TradingView session). Through Development the label in force at a 1H close differs on 13.4% of 1H closes for
     the 1H chart, 18.3% for the 4H chart and 4.4% for the 1D chart. The long / flat / short side differs on 8.9%,
     11.2% and 2.9%.
   - **This is the largest known difference from TradingView.** On the 1H chart the chart bars are the same under
     both clocks; only the 4H, D and W rows move.
   - BTC (TradingView: UTC days and Monday weeks) is not affected, except that our harness merges a short UTC day,
     which only happens at data holes.
2. **When a closed higher bar is shown.**
   - Gold's Friday 20:00 4H bar, Friday's day bar and the week all close at Saturday 00:00 UTC, about three hours
     after the last trade. Model A shows them on Sunday's first bar.
   - TradingView, on historical bars, shows a higher bar on the last chart bar inside it (both port authors read it
     so; it cannot be checked here without TradingView). That is Friday's last bar.
   - In Development this concerns 234 / 213 / 209 gold 1H bars (4H / D / W rows) and 11 / 8 gold 4H bars. It changes
     47 / 3 / 0 gold labels and 2 / 1 / 0 BTC labels (data holes).
3. **Pivot ties** are undocumented (section 3, item 1): 16 gold and 7 BTC 1H-chart labels in Development at most.
4. **The history start.** A TradingView chart has a longer history.
   - For model A, gold's dashboard from 2018-05-19 does not depend on where its history starts (both alternatives
     measured).
   - BTC's does until 2019-06-30.
   - For model B, see section 4.
5. **The live bar.** TradingView's dashboard repaints during a higher candle (model B, the video's own caveat):
   model B's label differs from model A's on 13.7-20.0% of Development chart bars.
6. **The feed.** TradingView's own Exness symbols may differ from the tick archive tick by tick. The bias uses the
   bid, as PREREG 2.
7. **The 100,000 sentinel in the hold-out.** BTC traded above 100,000 in the hold-out, so a bullish zone more than
   100,000 below the close becomes invisible there, as on TradingView. It is ported literally; it never occurs
   before 2024-07.
8. **No history to compare with.** The script keeps none, so the port can be compared with TradingView only bar by
   bar in Bar Replay. The map's optional manual check: BINANCE:BTCUSDT 4H at weekly closes, where models A and B
   agree.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

Each is written before any dashboard result exists. None changes a rule of PREREG 6.2.

1. **Dashboard: the weekly row (adds a measurement to entry 1).** The dashboard's W row is the harness's weekly bars
   of entry 1. A merged 1D bar belongs to the ISO week of its last UTC day, so gold's Sunday session opens the new
   week (428 of 443 weeks to 2024-06), and a short holiday Friday merged into the next Monday opens the following
   week (3 weeks). A week closes with its last day bar (gold: Saturday 00:00 UTC). Both ports' builders and the
   harness give the same bars (`tests/test_tradeiq2_ind_msd.py`). The alternative, the week of a day bar's open
   time, would move every gold Monday into the week before. It changes 4,132 / 1,265 / 248 gold Development labels
   (1H / 4H / 1D charts) and none on BTC. **Affects:** every MSD row on gold, MSD-F6, STK-RM / STK-RMA and study 3's
   MSD filter.
2. **Dashboard: when a closed higher-timeframe bar reaches the chart.** Model A takes each higher row from its last
   bar with close time at or before the chart bar's close (`htf_at`, PREREG 5). PREREG 6.2 says this "is what
   TradingView shows on historical bars". That holds except where no chart bar closes at the higher bar's close.
   Gold's Friday 20:00 4H bar, its Friday day bar and its week close at Saturday 00:00 UTC, so they reach a gold 1H
   chart at Sunday's first bar. TradingView shows them on Friday's last bar. The plan's definition is kept. In
   Development this concerns 234 / 213 / 209 gold 1H bars (4H / D / W rows) and 11 / 8 gold 4H bars. It changes 47 /
   3 / 0 gold and 2 / 1 / 0 BTC labels (1H / 4H / 1D charts). **Affects:** every MSD row, MSD-F6, STK-RM / STK-RMA and
   study 3's MSD filter.
3. **Dashboard: BTC's rows depend on the data start until mid-2019.** Each row runs from the first bar of the data
   (BTC 2018-01-01), as PREREG 3 lets indicators read the history before a window. The map's pre-registered
   convergence check compares each row with the same row started 182 days later. BTC's daily row agrees from
   2019-06-27 and its weekly row from 2019-07-01. Before that, 849 / 260 / 60 of BTC's Development labels (1H / 4H /
   1D charts) differ between the two starts, all before 2019-07-01. Breaks of structure and BOS-trend do not differ.
   The map suggested starting BTC's dashboard Development window after convergence. PREREG 3 does not, and its
   windows are kept. The dependence is reported with the MSD results, as the share of BTC MSD-family trades decided
   before 2019-07-01. **Affects:** BTC's MSD-A1..A3, MSD-F4, MSD-F6 and STK-RM / STK-RMA rows, in the first half of
   2019 only.
4. **Dashboard: gold's Early window (exam 2) is not converged until 2018-05-19.** With the 2016 warm-up, gold's rows
   agree with a start 182 days later only from the weekly bar closing 2018-05-19. Gold's weekly structure is first
   ready on 2017-01-21. Against that later start, 2,734 / 876 / 213 of the Early window's 11,798 / 3,186 / 515 chart
   labels (1H / 4H / 1D) differ, all before 2018-05-19. Against study 1's 2017 start, 3,962 / 1,223 / 241 differ.
   From 2018-05-19 on, the labels do not depend on the start. Exam 2 is scored as registered; this dependence is
   reported with it. **Affects:** exam 2 of a gold champion of the MSD-ALONE or MSD-FILTER family or of STK-RM /
   STK-RMA, and the Early-window base rate of those rows. BOS-trend is not affected.
5. **Dashboard: pivot ties, logged as PREREG 6.2 asks.** Pivots are strict on both sides. TradingView does not
   document equal highs or lows. To 2024-06, allowing an equal value on the newer side, the older side or both adds
   5, 5 or 10 of gold's 6,200 1H pivots, 2 gold 4H highs, 1, 1 or 2 BTC 1H highs, and none on D or W. It changes 15,
   7 or 16 gold and 0, 7 or 7 BTC 1H-chart Development labels, and none on the 4H or 1D charts. **Affects:** the MSD
   rows on 1H charts.
6. **Dashboard: the tick in the swing range.** `syminfo.mintick` (L706) is 0.001 on gold and 0.01 on BTC, the store's
   price digits. It matters only when the last pivot high lies below the last pivot low and the close is within one
   tick of the swing low. Ten times the tick changes no Development label. **Affects:** in principle every MSD row;
   measured, none.
7. **Dashboard: gold's 4H, D and W rows on UTC boundaries.** The bars are UTC (PREREG 2), not TradingView's gold
   session (day from 17:00 New York, 4H bars aligned to it, the week from Sunday's session). The map asked to log
   it, and it qualifies PREREG 6.2's "what TradingView shows". A scratch measurement with session bars from the same
   M1 data gives a different label at 13.4% / 18.3% / 4.4% of Development's 1H closes (1H / 4H / 1D charts), and a
   different long / flat / short side at 8.9% / 11.2% / 2.9%. **Affects:** gold's MSD rows, as a difference from
   TradingView only. The plan's bars are kept. BTC is not affected.
8. **Dashboard: model B for claim 14.** Model B, the live dashboard at a chart close, takes each higher row's state
   after its last closed bar and steps it once, tentatively, on the forming candle: its first chart bar's open, the
   high and low of its chart bars so far, and the chart close. Nothing is kept. Chart bars inside no higher bar take
   the last closed values; that happens only at a data end. Port A computes it, and the reconciliation checks it at
   every chart bar against port B's engine rolled back after each step. Model B's label differs from model A's on
   19.1 / 18.1 / 13.7% (gold) and 19.9 / 20.0 / 15.5% (BTC) of Development bars. Claim 14's "the closed one" is read
   as the score the higher bar ends with: its own committed values (`row_values` at that bar), with the swing vote
   taken at its own close. Where a chart bar closes with the higher bar, that equals model A on that chart bar.
   Gold's week, its Friday day bar and its Friday 20:00 4H bar close when no chart bar closes, so there only the
   row's own values can supply it. **Affects:** claim 14 only (information).
9. **Dashboard: what MSD-F6's "row score" is.** F6 reads the chart's own dashboard: s_4H, s_D and s_W are the
   script's per-row scores before the weight (L710-722). Each is the sum of the structure, order-block, gap and swing
   votes, and the swing vote uses the chart's close (L1330). On a 1H chart, s_4H can therefore change from one 1H
   bar to the next inside a 4H bar, while its other three votes stay those of the last closed 4H bar. The map's
   other reading, "the row's structure is -1", is not used. **Affects:** MSD-F6 only.

## 9. Notes for the study's code

- **Building the rows.** Use `tradeiq2_ind_msd.rows_for(mk)`, or the harness's `mk.tbars(tf)` for '1H', '4H', '1D'
  and '1W'. Both mark a forming last week at the data end. `weekly_bars(day_bars)` without `end_s` is right only for
  data that end on a Monday 00:00 UTC. The hold-out's ends (gold 2026-11-26, BTC 2026-11-27) and study 3's span are
  not.
- **The outputs the rules read.**
  - `label` for MSD-A1..A3, F4 (FS), STK-RM / STK-RMA and study 3's MSD filter.
  - `s_4H`, `s_1D`, `s_1W` for F6 (a 1D chart has no `s_4H`).
  - `bos_trend` for BOS-trend.
  - `structure_dashboard(rows, tf, "B")` for claim 14.
- **Speed.** Port A gives all three charts of a symbol in well under a second. Port B takes a few seconds and is
  for tests only.
- **Claim 14 on gold.** No 1H bar closes at the close of gold's week, Friday day bar or Friday 20:00 4H bar
  (Saturday 00:00 UTC). Take "the score that bar ends with" from the row's own values (`row_values` of that bar,
  with the swing vote at its own close), not from model A at a chart bar (section 8, item 8).
