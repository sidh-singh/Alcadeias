# Heikin Ashi Candles, Trend Strength & Trend Age (LunqFX): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values and event counts. No Heikin
Ashi rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_ha.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_ha.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_ha.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_ha_a.py` and `tests/test_tradeiq2_ind_ha_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.8, with claims 3-5 of section 8. Study 3 (`backtest_results/bot_filters/`)
  reads the same series for its HA filter rows and its Turtle exits HA-M1 and HA-M4.
- **The script:** "Heikin Ashi Candles, Trend Strength & Trend Age Stats [LunqFX]", Pine v6, 327 lines. It is
  third-party code. Line numbers (l.) refer to the owner's plain-text copy. The source is not in this repository.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- On the 1H, 4H and 1D bars of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports give the
  same numbers, bit for bit, on every output and every bar. That includes the table of finished streaks and the
  trend-age statistics. Gold was also run from study 1's later start. No tolerance was needed anywhere, and no
  arithmetic had to be aligned.
- The reconciliation found two mismatches, both in port B and both fixed. Neither can appear with the script's own
  settings, so neither changes any number in this study (section 4).
- A third, unreviewed port written earlier to plan the study agrees on every count it computes (section 5).
- Three readings add to the plan and can move a result. They are proposed for `DEVIATIONS.md` (section 8). Three
  choices belong to the rule code, not to the port; section 9 lists them with the facts that bear on them.

## 1. What the script computes

All settings are the script's defaults (l.20-28); nothing is tuned.

1. **Heikin Ashi candles (l.79-83).** An averaged candle drawn for every bar.
   - The HA close is the average of the bar's open, high, low and close.
   - The HA open is the midpoint of the previous HA candle's open and close. On the very first bar it is the
     midpoint of that bar's open and close.
   - The HA high and low are the bar's high and low, stretched to include the HA body.
2. **Colour (l.85).** Bullish when the HA close is at or above the HA open (an exact tie counts as bullish), bearish
   otherwise.
3. **Phase (l.93-94).** Each candle gets one of four grades. The tests run in this order and the first that holds
   wins:
   - **INDECISION:** a small body (at most 25% of the candle's range) with a wick on both sides (each at least 10% of
     the range).
   - **STRONG:** no wick against the colour (at most 5% of the range). This is the classic "no lower wick" bullish
     candle, or "no upper wick" bearish one. A candle with no range at all also counts as STRONG.
   - **WEAK:** the same colour as the previous candle and a smaller body than it, whatever that candle's grade.
   - **STEADY:** everything else.
4. **Streaks and their age (l.99-160).** A streak is a run of candles of one colour. Its age counts its candles,
   the current one included.
   - A **flip** is a change of colour. It ends one streak and starts the next at age 1.
   - **First STRONG candle:** the first STRONG candle of a streak. It can be the flip candle itself.
   - **INDECISION after a STRONG run:** an INDECISION candle that comes right after 2 or more STRONG candles in a
     row of the same streak. It never fires on a flip candle.
5. **Trend-age statistics (l.166-184, 204-212).** Each finished streak's length is stored by colour. The script
   keeps the latest 5,000 of each colour.
   - **Percentile:** the share of finished streaks of the current colour that were shorter than the current age.
   - **Rare age:** the candle at which that share first reaches 90%. It happens at most once per streak.
   - **The panel** also shows "reached age A, then 5 or more candles more" and "after the first STRONG candle, 5 or
     more candles more", as percentages.
   - The script computes all of this on the chart's last bar only. On a chart's history it never shows a rare age,
     and its rare-age alert works only live.
6. **Display only:** the candles' colours, the length labels, the age label and the panel (about 200 lines).

**What the study adds (PREREG 6.8).**
- The statistics are computed at every bar from the streaks finished before it, using all history from the data
  start. The rare age at bar t is what the script's live alert would say at t's close.
- A rare age needs at least 50 finished streaks of that colour.
- `weak_run` counts consecutive WEAK candles, for rule M3 ("2 consecutive WEAK candles").

**Timing.** Every value is final at its bar's close. The script has no higher-timeframe requests and no look-ahead.
A streak becomes known at the close of the flip candle that ends it. On TradingView's live, still-forming bar the
colour, the phase and the events can change before the bar closes. This backtest uses closed bars only.

## 2. What was compared, and how

- **The bars.** The study's 1H, 4H and 1D bars (`PREREG.md` section 2), up to 2024-06-30.
  - The M1 bars were read with `external.load_market(symbol, earliest=..., end="2024-07-01")`, so nothing from the
    hold-out was loaded. Study 1's `TMarket.tbars` built them into bars, which is what `tradeiq2_market.load` serves.
  - Gold starts on 2016-01-03 (the 2016 warm-up months) and BTC on 2018-01-01. Study 3's `FilterBook` starts at the
    same places.
  - Gold was also run from 2017-01-03, study 1's start, because the statistics depend on where the bars start.
    Study 1's gold bars are exactly the later part of the study's bars.
  - These are the only timeframes the plan uses for this script: Heikin Ashi runs on its base's timeframe, and every
    base (study 1's finalists and the ribbon rows) is on 1H, 4H or 1D.
- **What had to agree.**
  - All 14 per-bar outputs, on every bar: the four HA prices, colour, phase, flip, age, the STRONG run, the WEAK run,
    the two events, the percentile and the rare age.
  - The table of finished streaks: first and last bar, colour, length, whether it had a STRONG candle, at which age,
    and whether it ran 5 or more candles after it.
  - Decimal numbers were compared bit for bit, with missing values on the same bars. Integers and yes/no flags were
    compared exactly.
  - The event table (flips, first STRONG candles, INDECISION after a STRONG run, the second WEAK candle in a row,
    rare ages) had to agree too, with each event's bar, times, colour, age, runs and percentile.
  - The panel's helpers, which claim 5 reads, had to agree at the start of every year and at random bars: the stored
    lengths, the "reached A, then 5 more" counts, the STRONG-continuation counts and the percentile.
  - The 2019-2022 counts of section 6 are recorded in the test, for both ports.
- **Synthetic bars.**
  - Random walks; walks rounded to whole units (so exact ties occur); walks with flat stretches (zero-range candles).
  - Bars built to give exact HA shapes: ties, zero ranges, dojis after STRONG runs, WEAK runs.
  - Random inputs inside the script's input ranges (l.20-28) and minimums from 0 to 120 streaks.
  - Small caps on the stored lengths (a private argument of both ports), below and above the minimum.
  - Series of 0 to 9 bars.
  - Before the final test, 3,600 such cases were run in scratch (section 4).
- **Is the test sharp?** It was rerun against 19 deliberately broken copies of port B (built in memory from its
  source; nothing in the repository was changed). The results are in the table below; "real" means the six real
  series and gold from 2017.

  | Misreading built into port B | Caught on real bars | Caught on synthetic bars |
  |---|---|---|
  | HA open seeded with the bar's open | yes, 9 of 9 series | yes |
  | HA close summed in another order (only the last bits change) | yes, 9 of 9 | yes |
  | HA high without the HA open | yes, 9 of 9 | yes |
  | STRONG run not reset at a flip | yes, 9 of 9 | yes |
  | First-STRONG marker not reset at a flip | yes, 9 of 9 | yes |
  | INDECISION tested against the STRONG run before the flip's reset | yes, 9 of 9 | yes |
  | A finished streak's length stored under the new colour | yes, 9 of 9 | yes |
  | The first streak left out of the statistics | yes, 9 of 9 | yes |
  | The 50-streak minimum counted over both colours | yes, 9 of 9 | yes |
  | The percentile as 100 × (count / number) (only the last bits change) | yes, 9 of 9 | yes |
  | Rare only above 90%, not at 90% | yes, 7 of 9 (where an exact 90.0% occurs) | yes |
  | No cap on the stored lengths | yes, 3 of 9 (the 1H series, where the cap binds) | no (too short to reach 5,000) |
  | The minimum counted on the capped array (old port B) | no (the same at the cap of 5,000) | yes, with small caps |
  | A tie read as bearish | no (no tie in our data) | yes |
  | WEAK with "smaller or equal" | no (no equal bodies in our data) | yes |
  | STRONG tested before INDECISION | no (they exclude each other at the default 5%) | yes, with other inputs |
  | A zero-range candle not STRONG | no (none in our data) | yes |
  | HA close times 0.25 instead of divided by 4 | no | no: the two are the same number, bit for bit |
  | Doji thresholds as ratios (body / range) instead of products | no | no: the same phase on every bar |

  Every misreading that changes a value on our bars is caught by the real bars. Every other one is caught by the
  synthetic bars, except the last two, which compute the same values here and are harmless.
- **Arithmetic.** Both ports already follow the script's order of operations, so nothing had to be aligned:
  - the HA close: open + high + low + close, added left to right, then divided by 4;
  - the HA open: (previous HA open + previous HA close) / 2;
  - each threshold as the input times the range (`0.25 * range`, `0.1 * range`, `0.05 * range`);
  - the percentile as (100 × count) / number of stored lengths.
- **Running it.** The three test files pass together: 89 tests in about 48 s, at a peak of 1.5 GB of memory.

## 3. The Pine readings, with their evidence

The effects are counted on the Development decision bars (section 6) and the Validation bars (closing after
2023-01-01, to 2024-06-30) of the study's bars. They are changed values or events only: counts, never profit or loss.

| # | Item (lines) | Reading used | Evidence | The alternative, and what it would change |
|---|---|---|---|---|
| 1 | HA open on the first bar (l.80-81) | (open + close) / 2 on the first bar given, then the usual recursion | `haO` is declared without `var`, so its previous value is missing only on the first bar | The bar's open (as other HA scripts do): the seed fades by half every bar and is gone, bit for bit, within 51-57 bars on our charts (port B, 300 random starts). Nothing in Development can change |
| 2 | HA close (l.79) | (open + high + low + close) / 4, added left to right | As written; Pine evaluates left to right | Another order changes the last bits of the HA prices (the test catches it), never a colour or phase: no wick, body or body difference on our bars comes closer to its threshold than 4e-10 of the price, against rounding of about 2e-16 |
| 3 | A tie (l.85) | Bullish (`>=`) | As written | Bearish: no bar of the six series has an exact tie, so nothing changes here |
| 4 | Order of the phase tests (l.94) | INDECISION, then STRONG, then WEAK, then STEADY | The script's nested conditions, read left to right | STRONG first: nothing changes at the default 5% (a doji's wicks are at least 10% of its range). WEAK first would change many phases |
| 5 | Zero-range candle (l.93-94) | STRONG (its opposite wick, 0, is at most 5% of 0) and bullish (a tie) | As written | No zero-range candle on our bars |
| 6 | WEAK (l.94) | Same colour as the previous candle and a strictly smaller body than the previous candle's, whatever its grade. Never on the first bar | As written; a comparison with a missing value is false in Pine | "Smaller or equal": no two consecutive same-colour bodies are exactly equal on our bars. Comparing with the last non-doji body instead would change phases (port A's trap test) |
| 7 | STRONG run reset before the INDECISION test (l.147, l.156) | An INDECISION candle on a flip bar never counts; a STRONG run of the previous streak never counts | l.147 resets the run in the flip branch, which runs before l.156 | Counting INDECISION flip candles after a STRONG run of the previous streak would add 683 / 209 / 38 (gold 1H / 4H / 1D) and 887 / 216 / 43 (BTC) Development events to the 973 / 284 / 31 and 1,383 / 310 / 61 |
| 8 | First STRONG candle on the flip bar (l.146, l.158-160) | Yes: a STRONG flip candle is its streak's first STRONG candle, at age 1 | l.146 clears the marker at the flip, before l.158 tests it | Excluding flip bars would move about a third of the events: 1,260 of 3,831 on gold 1H, 1,793 of 5,823 on BTC 1H, similar on every series |
| 9 | Where a finished streak's length goes (l.126-130) | Into the array of the streak that ended, at the close of the flip candle | `a = sDir == 1 ? bullL : bearL` before `sDir` is changed | Into the new colour's array: other percentiles everywhere (port A's trap test) |
| 10 | The first streak (l.121-125) | Counted, although it starts at the first bar given and its true start is unknown | The script counts it | Leaving it out changes the rare age on 11 gold 4H bars and 1 gold 1D bar of Development; nothing else (with study 1's start: 4 gold 1D bars in Development, 4 in Validation) |
| 11 | The cap of 5,000 lengths per colour (l.131-132) | Kept | As written; PREREG's "all history from the data start" is read as where the history starts | No cap: it binds on 1H only, BTC from 2022-04-21 and gold from 2022-11-28. The percentile then differs on 398 gold / 4,500 BTC 1H Development bars and 6,594 / 9,659 Validation bars; the rare age on none |
| 12 | Rare age at every bar (l.209-212) | Computed at every bar, as if it were the chart's last bar (PREREG 6.8) | The value the live alert computes at that bar's close | The literal script: no rare age on any historical bar, so no M4 or HA-M4 exit at all |
| 13 | The 50-streak minimum (PREREG 6.8) | Counts every finished streak of the current colour, also those the cap dropped | The plan's words. Equal to counting the stored lengths, because 5,000 > 50 | The script's own rule (one finished streak) changes the rare age only in the warm-up, on no Development or Validation bar. The minimum is reached on 2016-01-27 (gold 1H), 2016-04-19 (gold 4H), 2017-11-07 (gold 1D), 2018-01-18 (BTC 1H), 2018-03-08 (BTC 4H) and 2019-02-03/04 (BTC 1D) |
| 14 | The percentile (l.166-173, l.212) | (100 × count) / number stored; "shorter" is strict; rare when it is at least 90 | As written | An exact 90.0% occurs on 3 gold 4H bars and 1 gold 1D bar of Development, each a rare age; "above 90" would remove them. 100 × (count / number) gives the same rare ages |
| 15 | Where the history starts | The study's data start: gold 2016-01-03, BTC 2018-01-01 | PREREG 6.8 ("all history from the data start") with PREREG 2 (gold's 2016 warm-up) | Gold from 2017-01-03 (as spec 4.2 says): the rare age differs on 12 / 12 / 10 Development bars (1H / 4H / 1D) and 0 / 0 / 2 Validation bars; candles, colours, phases and every other event are identical from 2017-03-05 at the latest. A start one year later moves more (gold from 2018: 12 / 49 / 28 bars; BTC from 2019: 296 / 312 / 28, and 1 / 4 / 0 flips in early January 2019) |
| 16 | The WEAK run (PREREG M3; not in the script) | Consecutive WEAK candles of the current streak; 0 on any other candle | "2 consecutive WEAK candles" | None: a WEAK candle has the previous candle's colour, so a run can never cross a flip. On our bars the run never exceeds 3 (4 once on BTC 1H) |
| 17 | Thresholds (l.93-94) | Products: `body <= 0.25 * range`, and so on | As written | Ratios (`body / range <= 0.25`): the same phase on every bar of the six series |
| 18 | A missing price | Refused | The script's handling of a missing price is not ported | Our bars have none |
| 19 | Source bars | The bid of the study's bars (UTC boundaries; a short UTC day merged into the next) | PREREG 2 | TradingView's own Exness bars (section 7) |

## 4. Mismatches found, and how each was resolved

Two mismatches, both in port B. On the real bars the two ports were already equal before the fixes.

**1. The 50-streak minimum with a small cap on the stored lengths.**
- **What differed.** PREREG 6.8 says a rare-age rule needs "at least 50 finished streaks of that colour".
  - Port A counts every finished streak of the colour.
  - Port B counted the lengths its capped array held.
  - With the script's cap of 5,000, the array holds the smaller of the finished count and 5,000, so the two tests
    are the same for any minimum up to 5,000.
- **How it was found.** In scratch, 3,600 synthetic cases were run with random inputs, short series and small caps
  (a private argument of both ports, used only to study the cap). 126 cases differed. In every one the cap was below
  the minimum, and only the rare age differed.
- **Who was right.** Port A, which follows the plan's words. Port B's contract table also said "at least
  `min_streaks` finished streaks of that colour", but its reading 11 and its code counted the array.
- **The fix.** Port B now counts every finished streak of each colour. The independent formulation in its tests was
  changed the same way.
- **The tests.**
  - A hand-computed case is in the reconciliation test, and the same case is in port B's tests.
  - Bull streaks of 9, 1, 1, 1 and a fifth bull streak, with a cap of 3. At the fifth streak's age 2 the stored
    lengths are 1, 1, 1, so 100% are shorter: a rare age. Four bull streaks have finished, so a minimum of 4 is met.
    Old port B (3 stored) said no.
- **Effect on the study:** none. The cap is the script's 5,000.

**2. An infinite value for a whole-number input.**
- **What differed.** For an infinite `ahead_n`, `rare_pct` or `min_streaks`, port B raised Python's OverflowError
  (it rounded the value down before checking that it was finite). Port A raised ValueError, as both ports' contracts
  say.
- **The fix.** Port B checks finiteness first. Both ports' tests now cover it.
- **Effect on the study:** none; no value changes.

**No other mismatch.**
- Before and after the fixes, every output was equal bit for bit on all six real series and on gold from 2017.
- All 3,600 synthetic cases agree after the fixes.

**Differences that are not mismatches (outside the shared contract).**
- **Speed.** Port A takes milliseconds for a series. Port B takes about 8 s for BTC 1H, because it scans the stored
  lengths twice per bar, as the script does.
- **Helpers.** Port A has `panel_at` and `kept_lengths`; port B has `strong_continuation` and `lengths_known_at`.
  They give the same numbers (tested).
- **The constant `KEYS`.** Port A's includes `streaks`, port B's does not. Both return the same keys in the same
  order.

**Corrections to the two ports' own notes** (measured again here; both docstrings are updated):
- **The bars.** Both ports measured their readings on study 1's bars, where gold starts on 2017-01-03. The study's
  gold bars start on 2016-01-03. That moves a few figures:
  - the cap binds on gold 1H from 2022-11-28, not 2023-11-27, so the percentile also differs on 398 gold 1H
    Development bars (port A had said none of gold's);
  - leaving out the first streak changes 11 gold 4H and 1 gold 1D Development rare ages, not "gold 1D only, 4 bars"
    (port B; that figure holds for study 1's start);
  - the 50-streak minimum is reached in 2016 for gold 1H and 4H, and on 2017-11-07 for gold 1D;
  - gold's Development rare ages are 481 / 150 / 15 (1H / 4H / 1D), against 481 / 148 / 13 from study 1's start.
- **Windows.** The two ports counted 2019-2022 slightly differently: port A included the bar closing at exactly
  2023-01-01 00:00, port B the bar closing at exactly 2019-01-01 00:00. So gold 4H had 1,554 against 1,555 flips and
  BTC 4H 2,230 against 2,229. This report uses the harness's Development decision bars (section 6).

## 5. A third opinion: the unreviewed scratch port of the planning pass

A planning pass, before the plan was written, wrote a quick port of the script's candles, phases and events
(`ha_events` in its probe) and counted events with it. That port is outside the repository and was only read. Its
function was extracted from the file and run on the same bars as the two ports; the rest of the probe was never run.

- **The same events.** On all nine series (the six, plus gold from 2017), it gives the same numbers as both ports
  for everything it computes: bars, finished streaks, the median and 90th percentile of their lengths, first STRONG
  candles, INDECISION after a STRONG run, and the four phase shares.
  - Example, gold 1H from 2016: 49,956 bars, 12,337 streaks, median 3, 90th percentile 9, 8,063 first STRONG
    candles, 2,126 INDECISION after a STRONG run.
  - From 2017: 44,190 bars, 10,879 streaks, 7,103 and 1,889.
- **What it does not compute:** the percentile, the rare age and the WEAK run. Those rest on the two ports alone,
  and on the independent formulations inside each port's tests.
- **The plan's map quotes the probe's figures** (spec 4.3). They hold on the study's bars:
  - "About 1,450 / 385 / 62 colour flips a year on gold" are whole-history rates from 2017 (10,879 / 2,893 / 462
    streaks over 7.5 years). Development alone has 1,466.5 / 388.5 / 65.0.
  - "About 17 INDECISION-after-STRONG events per 100 streaks" is roughly right: 13.9-18.3 on 1H and 4H, 17.4 on BTC
    1D in Development. Gold 1D has 11.9.
  - The phase shares (STRONG 46-52%, STEADY 12-13%, WEAK 7-8%, INDECISION 29-33%) hold to rounding: over the whole
    history BTC 1H has 45.8% STRONG, and 45.5% in Development.
  - The median length of 3 and the 90th percentile of 8-9 hold, and so does "a first STRONG candle in about 65% of
    streaks" (62.2-68.0% in Development).

## 6. Event counts per symbol and timeframe, 2019-2022

**The data.**
- The study's bars; values from port A and port B, which are identical.
- The window is the harness's Development decision bars: a bar counts if it closes after 2019-01-01 00:00 UTC and
  its fill (the first M1 bar at or after its close) comes before 2023-01-01 00:00. That is `tradeiq_market.run`'s
  rule.
- Counts only: no rule was run and no profit or loss was computed.

**The columns.**
- **Flips:** colour changes, to bullish / to bearish. Every flip ends one finished streak.
- **Streaks:** the lengths of the streaks that finished in the window: median / 90th percentile / longest.
- **With STRONG:** the share of those streaks with a STRONG candle. **5+ after:** of those, the share that ran 5 or
  more candles after their first STRONG candle (the panel's SK / SN).
- **First STRONG:** first STRONG candles (of them on the flip candle itself). The HA-H1 entry.
- **INDECISION after STRONG:** the M2 trigger, and per 100 finished streaks.
- **Weak 2:** bars with a WEAK run of exactly 2 (at least 2). The M3 trigger.
- **Rare age:** bars where the streak reaches its rare age, bullish / bearish streaks, and the median age at which it
  happens. The M4 exit.

| Series | Bars | Flips (bull / bear) | Flips a year | Streaks | With STRONG | 5+ after | First STRONG (on flip) | INDECISION after STRONG (per 100) | Weak 2 (≥ 2) | Rare age (bull / bear), median age |
|---|---|---|---|---|---|---|---|---|---|---|
| Gold 1H | 23,590 | 5,866 (2,933 / 2,933) | 1,466.5 | 3 / 8 / 41 | 65.3% | 26.8% | 3,831 (1,260) | 973 (16.6) | 132 (138) | 481 (245 / 236), 10 |
| Gold 4H | 6,385 | 1,554 (777 / 777) | 388.5 | 3 / 9 / 37 | 65.0% | 28.0% | 1,010 (318) | 284 (18.3) | 30 (30) | 150 (74 / 76), 9 |
| Gold 1D | 1,031 | 260 (130 / 130) | 65.0 | 3 / 8 / 19 | 66.5% | 24.3% | 173 (48) | 31 (11.9) | 11 (11) | 15 (9 / 6), 10 |
| BTC 1H | 35,016 | 9,211 (4,605 / 4,606) | 2,302.8 | 3 / 8 / 25 | 63.2% | 23.1% | 5,823 (1,793) | 1,383 (15.0) | 193 (201) | 871 (440 / 431), 8 |
| BTC 4H | 8,756 | 2,229 (1,115 / 1,114) | 557.2 | 3 / 8 / 23 | 62.2% | 26.5% | 1,386 (453) | 310 (13.9) | 49 (53) | 201 (117 / 84), 9 |
| BTC 1D | 1,459 | 350 (175 / 175) | 87.5 | 3 / 9 / 22 | 68.0% | 28.2% | 239 (72) | 61 (17.4) | 8 (8) | 30 (17 / 13), 10 |

**Phase shares** in Development (STRONG / STEADY / WEAK / INDECISION):
- gold 50.3 / 12.2 / 7.6 / 29.9% (1H), 51.2 / 11.7 / 7.1 / 30.0% (4H), 49.5 / 11.7 / 8.6 / 30.2% (1D);
- BTC 45.5 / 13.4 / 7.9 / 33.1% (1H), 46.5 / 13.0 / 7.9 / 32.5% (4H), 51.2 / 11.9 / 8.0 / 29.0% (1D).

**Validation (2023-01-01 to 2024-06-30), for information:** flips / first STRONG / INDECISION after STRONG / Weak 2 /
rare age:
- gold 2,207 / 1,429 / 388 / 44 / 182 (1H), 589 / 392 / 103 / 11 / 43 (4H), 82 / 57 / 18 / 1 / 12 (1D);
- BTC 3,443 / 2,200 / 509 / 74 / 304 (1H), 841 / 519 / 111 / 22 / 63 (4H), 121 / 74 / 21 / 4 / 11 (1D).

**Notes.**
- **Warm-up.** The percentile exists from the first days: gold from 2016-01-04 (1H), 2016-01-06 (4H) and 2016-01-19
  (1D); BTC from 2018-01-01 (1H), 2018-01-02 (4H) and 2018-01-09 (1D). It exists on every Development bar.
- **Gold from study 1's start** (2017-01-03) gives the same counts except the rare ages: 481 / 148 / 13 in
  Development instead of 481 / 150 / 15. On 1H the total is the same, but 12 bars differ.
- **The rare age is about the 9th or 10th candle** of a streak on every series (8 on BTC 1H). About 8% of finished
  streaks reach it (gold 1H: 481 of 5,866).
- **1D is thin.** Gold has 15 rare ages and 31 INDECISION-after-STRONG events in four years. BTC 1D has 8 WEAK
  pairs. A management overlay on 1D will change only a handful of trades.
- **The WEAK run** reaches 3 on 6 gold 1H, 8 BTC 1H and 4 BTC 4H Development bars, and never on the others.

## 7. What may still differ from TradingView

1. **The bars themselves.**
   - TradingView's Exness charts are assumed to show the bid, as PREREG 2 does.
   - Our bars are built from Exness's tick archive on UTC boundaries, and a short UTC day is merged into the next.
   - TradingView's 4H and 1D bars for a broker symbol may follow the broker's session instead, for example gold's
     daily bar closing at the New York close. Its feed may also differ tick by tick.
   - Each HA candle depends on the previous one. So a bar boundary that differs on every bar gives other HA candles
     on every bar, and colours can differ anywhere, most on 1D. On 1H the boundaries are the same.
2. **How much history the chart has.** This is the script's own weakness, which the video names ("more history,
   better numbers").
   - TradingView computes the statistics from the bars the chart has loaded. That number depends on the account plan.
     On intraday charts it is usually much shorter than our history (gold from January 2016, BTC from January 2018,
     about 50,000 1H bars each); a daily chart may hold as much as ours, from another start date.
   - So the percentiles on a TradingView chart, and with them the rare age, will differ from ours. Our figures are
     those of a chart with all our history loaded.
   - The cap of 5,000 lengths per colour binds only after more than 10,000 streaks, about 40,000 bars. Our 1H series
     reach it (BTC from April 2022, gold from November 2022); most TradingView charts never would.
3. **The rare age on history.** The script computes it only on the chart's last bar, so a TradingView chart never
   shows a past rare age. Ours is what its live alert would say at each bar's close (PREREG 6.8).
4. **The 50-streak minimum** is the plan's, not the script's. It changes no Development or Validation bar.
5. **The live bar.** TradingView recomputes the forming bar on every tick, so a flip, an event and a "once per bar"
   alert can appear and then vanish before the close. Closed bars never change.
6. **Arithmetic.** Pine computes in the same 64-bit floating point. Both ports follow the script's order of
   operations, and no value on our bars is within 4e-10 of the price of a threshold, so a colour or phase cannot
   depend on rounding.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

These are written before any Heikin Ashi result exists. Each can move a result; the tie, zero-range, seed and
arithmetic readings of section 3 cannot, on our bars.

1. **The statistics keep the script's cap of 5,000 streaks per colour.**
   - **What.** PREREG 6.8 computes the streak statistics "using all history from the data start". The ports read
     this as where the history starts and keep the script's own cap (l.131-132): each colour keeps its latest 5,000
     finished lengths for the percentile and the rare age.
   - **Why.** It is the script as written. The plan does not say to drop the cap.
   - **Effect, measured to 2024-06-30.** The cap binds on 1H only: BTC from 2022-04-21, gold from 2022-11-28.
     - The percentile then differs on 4,500 BTC and 398 gold Development bars, and on 9,659 and 6,594 Validation
       bars.
     - The rare age differs on no bar, because the age at which 90% is reached stays the same.
     - The hold-out was not computed.
   - **Affects:** claim 5's calibration on 1H for 2023 and 2024 (the years whose "before the year" statistics are
     capped), and the M4 rows on 1H bases only if the hold-out shows a difference. Not study 3: its HA-M4 exits run
     on 4H and 1D, where the cap does not bind.
2. **The statistics start at the study's data start: gold 2016-01-03, BTC 2018-01-01.**
   - **What.** "All history from the data start" is read as the first bar the study's harness loads
     (`tradeiq2_market.load`, PREREG 2), which includes gold's 2016 warm-up months. Spec 4.2 had said "gold 2017".
   - **Why.** PREREG 2 downloaded 2016 as warm-up, and the harness serves gold from 2016-01-03. Study 3's filter
     bars start there too.
   - **Effect.** Against a 2017-01-03 start, the gold rare age differs on 12 / 12 / 10 Development bars (1H / 4H /
     1D) and 0 / 0 / 2 Validation bars. Candles, colours, phases and every other event are identical from
     2017-03-05 at the latest; the percentile differs on most bars. BTC has no earlier data.
   - **Also.** It gives gold's Early window (2017-2018, scored only after the freeze) warmed-up candles from its
     first day, and the 50-streak minimum from 2016 on 1H and 4H. On 1D the minimum is reached only on 2017-11-07,
     so gold 1D rare ages cannot fire in the Early window before then.
   - **Affects:** gold's M4 rows on 1H, 4H and 1D (Development, Validation and the Early exam), and claim 5 on gold.
     Not study 3: its HA-M4 exits belong to the Turtle, which trades BTC, and its HA filter rows read only the colour.
3. **The first streak of the history counts.**
   - **What.** The first streak starts at the first bar given, so its true start, and its true length, are unknown.
     The ports count it like any other streak, as the script does.
   - **Why.** It is the script as written, and the plan says "all history".
   - **Effect.** Leaving it out changes the rare age on 11 gold 4H bars and 1 gold 1D bar of Development, none of
     Validation, and nothing on the other four series to 2024-06-30. The percentile moves slightly on most bars.
   - **Affects:** gold's M4 rows on 4H and 1D, and claim 5 on gold. Not study 3's BTC HA-M4 exits, which it does not
     change to 2024-06-30.

## 9. Choices for the rule code (the port does not make them)

The ports return every series these rules need. Three choices remain for whoever writes M2-M5, HA-H1 and the HA
exits. These facts may help:

1. **Which colour's events count for a position.**
   - The INDECISION-after-STRONG event and the WEAK run fire in both colours. In Development the events split about
     evenly: gold 1H 500 in bullish and 473 in bearish streaks; BTC 1H 733 and 650.
   - The video's "strong candles, you hold; ... indecision after a strong run, you tighten up" is about the
     position's own direction. That suggests a long reacts to events of a bullish streak and a short to those of a
     bearish one.
   - The same question applies to M4. Study 3's HA-M4 exits a long when a bullish streak reaches its rare age, and a
     short on a bearish one.
2. **"That bar's low" (M2, M3).** Here the choice rarely matters.
   - An INDECISION candle has wicks on both sides, so its HA high and low are exactly the bar's own high and low.
     M2's level is the same price either way, on every bar (tested on all six series).
   - A WEAK candle has a wick against its colour. So for a long on a bullish WEAK candle, and a short on a bearish
     one, the HA low (high) is also the bar's own (tested).
   - For M3 the two can differ only when the WEAK candles have the other colour than the position. Spec 4.5 says
     the bar's real low.
3. **When M3 fires.** At the second WEAK candle in a row (`weak_run == 2`, once per run), or on every candle that
   extends the run (`weak_run >= 2`). The difference is small: a third WEAK candle in a row occurs on 6 gold 1H, 8 BTC
   1H and 4 BTC 4H Development bars, and on none of the other three series.

Two facts that are not choices:
- **HA-H1's entry can be the flip candle.** About a third of first STRONG candles are flip candles (section 6). That
  is the script's definition, and it is what the ports return.
- **BTC 1D's 50-streak minimum** is reached only on 2019-02-03 (bearish) and 2019-02-04 (bullish), inside
  Development. No rare age is lost: the script's own one-streak rule gives the same Development bars.
