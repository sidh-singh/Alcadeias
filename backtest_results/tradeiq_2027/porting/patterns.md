# Harmonic & Chart Patterns (AI-AlgoCode): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about swings, pattern events, levels and counts.
No pattern rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_patterns.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_patterns.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_patterns.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_patterns_a.py` and `tests/test_tradeiq2_ind_patterns_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.7 (rows HP-HF, HP-HC, HP-CF, HP-CS, HP-CC, HP-DRAWN) and claims 18-19 of
  section 8.
- **The script:** "Harmonic & Chart Patterns [AI-AlgoCode]", Pine v6, MPL-2.0, 830 lines. It is third-party code.
  Line numbers (L...) refer to the owner's copy. The source is not in this repository. Only its 38 pattern names,
  its 144 ratio constants and the dispatch of its pattern test are in the code, as tables generated from the source
  text, never typed by hand.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- On the 1H, 4H and 1D bars of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports give
  the same swings, the same confirmed and forming patterns, the same points and the same trade levels, bit for bit,
  on every bar. Gold was also run from study 1's later start. No tolerance was needed anywhere.
- The reconciliation found no mismatch. Neither port's behaviour changed. Three sentences in port B's notes were
  wrong and are corrected (section 4).
- A third, unreviewed port written earlier to plan the study gives the same events, bar by bar (section 5).
- Two readings matter for results:
  - TradingView does not document how its 5-bar high test breaks ties. That moves a handful of events on 1H
    (section 3, R1).
  - Which rows define "the first bar of each forming instance" for each rule. This one is large: on gold 1H it is
    1,144 or 1,290 harmonic entry bars in 2019-2022 (section 8).
- Six readings that add to the plan are proposed for `DEVIATIONS.md` (section 8).

## 1. What the script computes

All settings are the script's defaults (L19-92): depth 5, minimum swing 0% (no filter), all 38 patterns on, and the
plan multipliers of L35-41. Nothing is tuned. The script reads only the high, low and close of the chart's own bars.

1. **The zigzag (L535-572).**
   - A bar is a "5-bar high" when its high is the highest of the last 5 highs, itself included. A "5-bar low" is the
     same with lows. A tie with an earlier bar counts (section 3, R1). There is no test before the 5th bar.
   - On each bar the high side is handled first. If the bar is a 5-bar high:
     - when the latest swing is a high and this bar's high is strictly higher, the swing moves to this bar;
     - when the latest swing is a low (or there is none), this bar becomes a new swing high.
   - Then the low side, the same way for a 5-bar low. One exception: no new swing low is added on a bar that already
     set the latest swing.
   - So swings alternate high and low. An outside bar (a 5-bar high and a 5-bar low at once) counts as a high only,
     even if its low is below the current swing low. It becomes a new low only when the latest swing is a high that
     the bar does not exceed.
   - Only the newest swing (the "live" one) can move. It is fixed when the next one appears. Each swing remembers the
     close of the bar that set it.
   - The result is about one swing every 7 bars, on every timeframe.
2. **Swing sets (L575-580).** A pattern reads 11 swings, newest first. The newest of them is point D (Q0), then C
   (Q1), B (Q2), A (Q3) and X (Q4).
   - A confirmed check uses the 11 swings before the newest one. D is the swing that has just been fixed.
   - A forming check uses the 11 newest swings. D is the live swing.
3. **The 38 patterns (L292-531).**
   - **22 harmonics (ids 0-21):** Bat, ALT Bat, Butterfly, Crab, Gartley, Deep Crab, Shark, AB=CD, ALT AB=CD, 5-0
     and Three Drives, bearish first, then bullish.
     - Each tests 2 to 4 ratios of swing legs against windows. The 144 window edges are at L146-289.
     - The basic test (inR, L293-294) asks whether a point lies strictly inside a window measured on a leg from A
       to B. For a bearish test the leg must run down (A above B), for a bullish test up. Otherwise the test is
       always false.
     - The windows are not the textbook ones, and bullish is not the mirror of bearish. Examples: Bat XD is 0.3-1.8
       bearish and 0.5-2.5 bullish; the bearish Gartley's XD is 1.618-2.618. The source says they were generated from
       an MT5 program (L13).
   - **16 chart patterns (ids 22-37):** double top and bottom, head and shoulders and its inverse, triple top and
     bottom, wedges, expanding triangles, pennants, flags.
     - Each is a list of inequalities among the swings Q1-Q8. Point D (Q0) is never read.
     - Each ends with a breakout test: the close beyond the "neckline" Q2. Bearish ids need the close below Q2,
       bullish ids above it.
   - Every pattern is checked on every set. The first hit in registry order is the one drawn and alerted, and it
     sets the alert's direction. The others only add "+n" to its label. The order is bearish harmonics, bullish
     harmonics, then chart patterns.
4. **The two detections.**
   - **Confirmed (L780-795).** On a bar where a new swing appears, with at least 12 swings. The close the chart
     patterns test is the close of D's bar, not the current close. The alert fires at that bar's close ("once per
     bar close", L825). The pattern is then drawn back at D, a median of 3 bars earlier, which is why an old chart
     looks as if every pattern caught the turn.
   - **Forming (L798-813).** The script computes it only on the chart's last bar, on every tick, with the current
     close and at least 11 swings. The study runs it at every bar close, on the zigzag as it stands after that bar
     (PREREG 6.7): what a live user sees at that close. A forming pattern can change or vanish on a later bar.
5. **The trade plan (L694-718).**
   - **Harmonic:** AD = |Q3 - Q0|. For the 5-0, Q3 is its B, not its A.
     - Entry: D.
     - Stop: D - dir x 0.13 x AD.
     - TP1: D + dir x 0.382 x AD (2.94R).
     - TP2: D + dir x 0.618 x AD (4.75R).
   - **Chart:** h = |Q1 - Q2|.
     - Entry: Q2, the neckline.
     - Stop: Q2 - dir x 0.5 x h.
     - TP1: Q2 + dir x h (2R).
     - TP2: Q2 + dir x 1.618 x h (3.24R).
   - There are no levels when AD or h is 0. That never happens on our bars.
6. **Display only.** The lines, labels, the PRZ box (D +/- 0.06 AD), the plan drawn on the last bar (L814-820) and the
   overlap gate. Under the gate, a confirmed pattern is not drawn when it overlaps by more than half a pattern still
   on the chart (the newest 15, L767-792). The alert is not gated. Port A returns the gate's verdict as `drawn`.

**Facts of the script the ports found** (each has a test):
- **The bearish Gartley (id 4) can never fire.** Its XB, AC and BD windows keep XD below
  0.618 x (0.382 + 3.618 x 0.618) = 1.61788, under its own XD minimum of 1.618.
- **Two patterns can never be the first hit.**
  - The bullish ALT AB=CD (19) has exactly the bullish AB=CD's windows (18), so it fires with 18 every time.
  - The bearish ALT AB=CD's windows (8) lie inside the bearish AB=CD's (7), so it fires only with 7.
  - So only 19 of the 22 harmonic ids can ever be drawn or alerted. On our bars the bullish Butterfly (13) and the
    bullish falling wedge (34) were never the first hit either, but that is not proven.
- **Harmonic hits on one swing set never point both ways.** Every bearish harmonic needs Q2 above Q3, and every
  bullish one needs it below. So all harmonic hits of a bar share the direction and the plan (which reads only Q0,
  Q3 and the direction). All chart hits of a bar in one direction share their plan too (it reads only Q1, Q2 and
  the direction).
- **Predicates 28-33 accept a shifted alternation.** The wedges, expanding triangles and pennants never say which
  swings are highs, so they also pass with the alternation shifted by one. They are kept literally. In 2019-2022,
  19-33% of the forming chart instances come from this (gold 1H 42 of 160, BTC 1H 59 of 235).
- **A chart test reads the close only in its last condition.** So "every condition but the breakout" (HP-CS)
  depends on the fixed swings only. It can change only on a bar where a swing is added.
- **The overlap gate's 15-pattern history never decides on our bars.** No first hit is suppressed by any drawn
  pattern except the newest one. That holds on all six series, so any history length from 1 to 60 gives the same
  `drawn`.

## 2. What was compared, and how

- **The bars.** The study's 1H, 4H and 1D bars (`PREREG.md` section 2), up to 2024-06-30.
  - The M1 bars were read with `external.load_market(symbol, earliest=..., end="2024-07-01")`, so nothing from the
    hold-out was loaded. Study 1's `TMarket.tbars` built them into bars, which is what `tradeiq2_market.load` serves.
    Both studies' hold-out guards pointed at an empty folder.
  - Gold starts on 2016-01-03 (the 2016 warm-up months) and BTC on 2018-01-01.
  - Gold was also run from 2017-01-03, study 1's start, because the zigzag depends on where the bars start. Study 1's
    gold bars are exactly the later part of the study's bars.
- **What had to agree.** Integers and yes/no flags exactly. Decimal numbers bit for bit, with missing values in the
  same places and the same sign.
  - The swing list: bar, price, the close that set it, high or low.
  - Per bar:
    - the swing count and the "swing added" flag;
    - the two 5-bar tests;
    - the script's own swing count (capped at 60);
    - the live swing;
    - the 11 swings the forming test reads, and their bars. These were read from port B's bar-by-bar script state.
  - The confirmed and the forming tables, row by row, with every column:
    - bar, id, name, kind, direction, first hit, number of hits, number of points;
    - the close the test read;
    - every point and its bar;
    - entry, stop, TP1, TP2;
    - for forming rows, the instance key and its first-bar flag.

    Port B lists the points oldest first and port A newest first. One adapter maps one onto the other.
  - Port A's extra columns, recomputed from port B's values: the decision bar's close, the unit (AD or h), and
    `drawn` against port B's own gate.
  - HP-CS's series: "every condition but the breakout close", for each of the 16 chart ids on every bar.
  - The 2019-2022 counts of section 6, recorded in the test for both ports.
- **Synthetic bars.**
  - 10 random walks of 1,200-2,500 bars: prices rounded to 1 or 0 decimals (ties), added outside bars, repeated
    highs and lows, and depths 2, 3, 5, 9, 21 and 50.
  - 40 short or degenerate series of 0-100 bars: flat prices (every bar ties, so every bar is a swing), a straight
    rise, a slow fall and a regular saw.
  - Before the test was written, a wider pass of 340 such series (17,030 confirmed and 147,192 forming rows) also
    agreed.
- **The tables.** The names, the 144 constants (with their order), the dispatch, the directions, the point counts
  and the plan inputs are equal in both ports. Each port also regenerates its own tables from the source text in its
  own tests. When the source is on the machine (`TRADEIQ2_PATTERNS_SOURCE`, the study's scratch copy, or the owner's
  `.txt` or `.rtf`), the test also checks this: the close appears in each chart test exactly once, as its last
  condition, with the side its direction needs. That is what makes HP-CS's series exact.
- **Is the comparison sharp?** It was checked in scratch by breaking port A on purpose. It caught each of these:
  - a window test with `<=` instead of `<` (already on the real bars);
  - the other tie rule;
  - swapped targets;
  - TP1 computed in another floating-point order;
  - a different overlap threshold, or `>=` in it;
  - an HP-CS test that ignores the side;
  - a returning pattern counted as a new instance;
  - the confirmed test reading the current close.

  Only a history of 14 drawn patterns instead of 15 went unseen, because that history never decides (section 1).
- **Cost.** The test file runs in about 27 s at a peak of 1.5 GB.

## 3. The Pine readings, with their evidence

**R1. Ties in the 5-bar test (`ta.highestbars` / `ta.lowestbars` == 0, L541-542).**
- **Reading.** The newest bar wins a tie, so a high equal to the window's highest counts as a 5-bar high.
- **Evidence.** TradingView's reference does not say. PineTS, an open-source re-implementation of Pine and the
  spec's source, keeps the newest. Both ports and the planning port read it that way.
- **Why it matters little.** A tie cannot move the live swing, because a move needs a strictly higher high or lower
  low (L546, L558). It matters only when the latest swing is on the other side.
- **The alternative, measured.** With the oldest bar winning, over the 2019-2022 decision bars:
  - the 5-bar tests differ on 7 / 2 / 0 gold bars (1H / 4H / 1D) and 6 / 0 / 0 BTC bars;
  - 2 gold 1H and 4 BTC 1H swings fall on other bars;
  - gold 1H gains one confirmed first hit (a bearish Three Drives), and 5 of its 2,025 forming instances change;
  - nothing else changes.
- Both ports implement the alternative for measurement, and the test records this effect.

**R2. Before the 5th bar (L541).** The test has no value, and a comparison with no value is false, so no swing
starts on bars 0-3. Only the first bars are affected.

**R3. Where the chart starts.**
- **Reading.** Bar 0 is the first bar of the study's data: gold 2016-01-03, BTC 2018-01-01. TradingView's own chart
  start is unknown.
- **Evidence.**
  - Gold from 2016 and from 2017 gives the same 2019-2022 swings, detections, instance keys and `drawn` flags, in
    both ports.
  - Started 300 or 1,000 bars late, the zigzag joins the full run within 150 bars (port A's test). Port B found the
    swings rejoin within 4-12 bars and the events within 45-169 bars.

**R4. Forming patterns at every bar close (PREREG 6.7).**
- **Reading.** The test runs on the zigzag after the bar, with that bar's close and at least 11 swings. The script
  itself runs it only on the last bar (L802).
- **Not modelled.** A pattern that appears and vanishes inside a bar (section 7).

**R5. When a confirmed pattern is known.**
- **Reading.** At the close of the bar where the next swing appears. The script's `alert()` fires once per bar close
  (L825).
- **Not modelled.** Its `alertcondition`s (L826-827) could be set to fire intrabar, on a swing that the close then
  undoes. Example: after a swing high, a bar first makes a new 5-bar low, then exceeds the high. At the close it is a
  high, the low is dropped, and no swing was added.

**R6. What an instance is (the ports' contract).**
- **Definition.** A forming instance is the pattern id plus the bars of its fixed swings, Q1 to Q(n-1), without the
  live D. It can exist only while that D is the live swing.
- **Returns.** If the pattern stops holding and holds again while D is still live, it is the same instance. That
  happens to 30 of gold 1H's 2,025 instances (37 times).
- **The first-bar flag.** `first_bar_of_instance` marks the first bar of the key over all hits.
- **Derivable alternatives.** The first bar as the first hit, or each return counted as new, both follow from
  `instance_key` and `first_hit`. Section 8 proposes which rows each rule reads.

**R7. Lazy `and` / `or` (Pine v6).** The swing price is never read on an empty swing list (L550, L562-563). This
affects no value.

**R8. Arithmetic.**
- **Reading.** IEEE doubles, in the script's own forms, left to right, with no fused multiply-add.
  - The window edges are computed as (A - B) x max + B and B - (B - A) x min.
  - The levels are computed as D - dir x 0.13 x AD.
- **Evidence.** Both ports agree bit for bit. The direction is +/-1, so the grouping of dir x k x AD cannot change a
  bit.

**R9. The 60-swing cap and the index clamp (L569-579).** No read under the 12- and 11-swing gates reaches the cap or
the clamp. Both ports keep every swing and report the script's capped count.

**R10. A zero-size pattern (L704, L713).** It gets no levels. That never happens on our bars.

**R11. The overlap gate (L767-792).** It decides the drawing only; the alert and the confirmed rows are never gated
(L793-795). Port A's `drawn` emulates it from the first bar given.

**R12. Predicates 28-33 are kept literally.** Nothing was "fixed" to the textbook side (see section 1).

**R13. Inputs.** The bid high, low and close. The bars must be complete (no missing values), which ours are.

## 4. Mismatches found, and how each was resolved

**There were none.**
- The two ports agreed on the first run, on all six real series, and on every synthetic series.
- Neither port's behaviour was changed.

**The authors' reports differ in a few counts, and that is not a port difference.** Examples: gold 4H has
6,387 / 6,386 / 6,385 bars in 2019-2022; BTC 1H has 1,752 / 1,751 first-hit instances. These differences come from
the window's edges:
- port A took bars closing from 2019-01-01 00:00 (inclusive) to before 2023-01-01 00:00;
- port B and the planning pass took bars closing after 2019-01-01 00:00 and by 2023-01-01 00:00 (inclusive);
- the harness counts a decision only if it fills before 2023-01-01 (DEVIATIONS 3). That drops gold's last 2022 bar
  of each timeframe (a Friday close, filled on 2 January at 23:00, when gold reopened) and BTC's bar closing at
  exactly 00:00 on 1 January.

Section 6 uses the harness's window.

**Port B's notes had three errors, now corrected (text only).**
- They gave 0.618 x 2.618 = 1.61788. That product is 1.617924; the bound is 0.618 x 2.617924 = 1.61788.
- They gave the copy 829 lines. It has 830; the last, `//#endregion`, has no line end.
- They said gold's bars start in 2017. That is study 1's loader; the study's starts in 2016.

**A note for whoever runs the tests later.** Port A's own two source tests read only a `.txt` copy, and the owner's
folder holds only `.rtf` files. When the study's scratch copy is gone, those two tests skip (they do not fail). Port
B's source tests and the reconciliation test read the `.rtf`. The reconciliation test asserts that port A's tables
equal port B's, so the check of port A's tables against the source still runs through port B.

## 5. A third opinion: the unreviewed scratch port of the planning pass

The planning pass, before the plan was written, wrote a quick port of the script and counted events with it. That
port and its output are outside the repository and were only read and run from the scratch folder. It was run on
its own bars (study 1's loader, to 2023-01-01), next to both ports.

- **The same events, bar by bar, on all six series:**
  - the same bars with a new swing;
  - the same confirmed detections: bar, hit list, first hit, D's bar, every point and every level;
  - the same forming rows: bar, hit list, first hit, the 11 swings and their bars, and every level.
- **The other tie reading too.** Under it, its swings and confirmed detections equal port B's, and its swings equal
  port A's.
- **The same statistics.** All 20 pattern statistics of its `probe_out.json` were recomputed from port A on its
  window (bars closing after 2019-01-01 00:00 and by 2023-01-01 00:00). They are identical on all six series:
  - swings a year and bars per swing;
  - confirmed detections a year and as a share of swings;
  - first hits by family and by id;
  - the shares with several ids and with both directions;
  - chart hits as any hit and as first hit;
  - the delay from D to confirmation;
  - the distance in R from D, and the share past TP1, at the confirmation close;
  - the chart close beyond the neckline;
  - the forming bar share;
  - first-hit instances a year and by family;
  - chart instances over all hits, their close beyond the neckline, and their split by direction and by the side of
    the live swing.
- **No difference to explain.** Its "distinct instances" (gold 1H 320.8 a year) count first-hit keys by their first
  first-hit bar, which is the first-hit reading of section 8. Its chart instances (40 a year) count all chart hits.

## 6. Event counts per symbol and timeframe, 2019-2022

The harness's Development decision bars: closing after 2019-01-01 00:00 and filled before 2023-01-01 00:00. Counts
from the study's bars; both ports give the same numbers, and the test records them. Counts only, no profit or loss.

**Swings and confirmed patterns**

| | Gold 1H | Gold 4H | Gold 1D | BTC 1H | BTC 4H | BTC 1D |
|---|---|---|---|---|---|---|
| Bars | 23,590 | 6,385 | 1,031 | 35,016 | 8,756 | 1,459 |
| Swings added (a year) | 3,404 (851) | 912 (228) | 140 (35) | 5,030 (1,257.5) | 1,247 (311.8) | 210 (52.5) |
| Confirmed detections (a year) | 950 (237.5) | 260 (65) | 41 (10.3) | 1,342 (335.5) | 337 (84.3) | 48 (12) |
| First hit harmonic / chart | 840 / 110 | 230 / 30 | 35 / 6 | 1,182 / 160 | 302 / 35 | 42 / 6 |
| First hit bullish / bearish | 437 / 513 | 109 / 151 | 18 / 23 | 597 / 745 | 139 / 198 | 22 / 26 |
| Hit rows (all ids) | 1,465 | 417 | 61 | 2,152 | 517 | 78 |
| Several ids / both directions | 354 / 21 | 108 / 9 | 14 / 1 | 538 / 34 | 138 / 15 | 22 / 1 |
| A chart hit behind a harmonic first hit | 23 | 9 | 1 | 36 | 15 | 1 |
| Drawn (overlap gate) | 641 | 173 | 30 | 938 | 244 | 39 |
| D to confirmation, bars: p25 / median / p75 / p95 | 1 / 3 / 4 / 9 | 1 / 3 / 5 / 7 | 2 / 3 / 4 / 7 | 2 / 3 / 5 / 9 | 2 / 3 / 4 / 7.2 | 2 / 3 / 4 / 7 |

**Forming patterns and the rows' candidates**

| | Gold 1H | Gold 4H | Gold 1D | BTC 1H | BTC 4H | BTC 1D |
|---|---|---|---|---|---|---|
| Bars with a forming hit (share) | 7,025 (29.8%) | 2,036 (31.9%) | 349 (33.9%) | 9,927 (28.3%) | 2,560 (29.2%) | 397 (27.2%) |
| Forming hit rows | 10,735 | 3,194 | 541 | 15,195 | 3,843 | 676 |
| Instances over all hits: harmonic / reversal / continuation | 1,865 / 134 / 26 | 531 / 43 / 4 | 80 / 5 / 2 | 2,564 / 189 / 46 | 624 / 51 / 8 | 112 / 9 / 0 |
| Instances as first hit: harmonic / chart (a year, all) | 1,144 / 139 (320.8) | 310 / 39 (87.3) | 49 / 6 (13.8) | 1,546 / 205 (437.8) | 403 / 47 (112.5) | 69 / 8 (19.3) |
| Instances that come back (times) | 30 (37) | 12 (13) | 0 (0) | 41 (56) | 13 (14) | 2 (2) |
| HP-HF entry bars, first-hit reading (over all hits) | 1,144 (1,290) | 310 (343) | 49 (57) | 1,546 (1,745) | 403 (448) | 69 (77) |
| of which the close is at or beyond TP1 (skipped) | 85 | 14 | 2 | 146 | 31 | 3 |
| HP-CF chart instances, any chart id (shifted alternation) | 160 (42) | 47 (9) | 7 (2) | 235 (59) | 59 (11) | 9 (3) |
| HP-CS armed chart instances | 312 | 80 | 11 | 421 | 113 | 25 |

- The bearish Gartley never fires anywhere. No level is missing anywhere.
- On no Development bar do chart hits point both ways. Harmonic hits never can (section 1).
- "Instances as first hit" reproduces the plan's map: 321 / 87 / 14 a year on gold and 438 / 112 / 19 on BTC.
- HP-CF's chart instances are the plan's map's 40 / 11.8 / 1.8 and 58.8 / 14.8 / 2.2 a year.
- PREREG 6.7 runs HP-CF, HP-CS and HP-CC on 1H and 4H only; 1D's 7-9 chart instances are why.

## 7. What may still differ from TradingView

- **The tie rule (R1).** It cannot be checked without TradingView. Its effect is a handful of 1H events.
- **The bars.**
  - TradingView draws the same Exness bid prices, but from its own feed.
  - Its 4H and 1D bars may follow the symbol's trading session, while ours follow UTC days (a short day merged into
    the next). Different bars give different swings, so 4H and 1D patterns can differ there.
  - Holes in the data can differ too.
  - 1H bars are the most comparable.
- **The chart's start (R3).** The patterns are unaffected a few dozen bars after it. On our bars the overlap gate
  looks back only at the newest drawn pattern, so it settles at the first drawn pattern both charts share.
- **Real time (R4, R5).**
  - On TradingView the forming pattern is recomputed on every tick. One that appears and vanishes inside a bar is
    invisible here.
  - The forming `alertcondition`s (L828-829) can fire intrabar, depending on the alert's settings, and the confirmed
    ones too.
  - The backtest decides only at bar closes.
- **The MT5 origin.** The ratio windows come from an MT5 generator (L13) that we do not have. Fidelity to it, and
  whether the patterns match their textbook names, cannot be tested.
- **Display limits** (500 lines, 500 labels, 100 polylines, L14-15) affect only the drawing.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

They are written before any pattern rule result exists. None changes the script; each says which rows of the ports'
output a rule reads, where PREREG 6.7 is silent.

1. **Patterns: ties in the 5-bar high / low test (L541-542).**
   - **What.** Both ports (and the planning port) let the newest bar win a tie, so a high equal to the window's
     highest is a 5-bar high.
   - **Why.** That is PineTS's implementation, the only documented one; TradingView's reference is silent.
   - **Effect.** Over 2019-2022 the other reading changes the 5-bar tests on 7 / 2 / 0 gold bars (1H / 4H / 1D) and
     6 / 0 / 0 BTC bars, and moves 2 gold 1H and 4 BTC 1H swings. Its only events are one more confirmed first hit
     on gold 1H (a bearish Three Drives) and 5 of gold 1H's 2,025 forming instances.
   - **Affects:** every HP row, through those events, on 1H.
2. **Patterns: what a forming instance is and which bar is its first (PREREG 6.7, "the first bar of each forming
   instance").**
   - **The instance.** The pattern id plus the bars of its fixed swings Q1 to Q(n-1). It lives only while its D is
     the live swing. A return while D is still live is the same instance (gold 1H: 30 of 2,025 instances, 37 times).
   - **HP-HF.** It reads the forming first hit: the pattern the script draws and its forming alert reports
     (L808-813). An instance's first bar is the first bar on which its key is the first hit. Gold 1H has 1,144 such
     harmonic entry bars in Development; this is the plan's map's 321 instances a year.
   - **HP-CF.** It reads every chart id, as the plan's map's C-F row says, including chart patterns hidden behind a
     harmonic first hit. Its first bar is the first bar of the key over all hits (`first_bar_of_instance`). Gold 1H
     has 160 instances, against 139 as first hits.
   - **One entry per bar and side.** On one bar all harmonic hits share the direction and the plan, and all chart
     hits of one direction share theirs. So a rule enters at most once per bar and side.
   - **Why.** HP-HF's "forming harmonic" is the script's forming pattern, what a live user sees. The plan's map's
     counts, which sized the plan, used first hits for harmonics and all hits for chart patterns.
   - **The alternative.** First bars over all hits for HP-HF give 1,290 entry bars on gold 1H instead of 1,144: 215
     bars are only in that reading and 69 only in this one. It also counts the duplicates 8 and 19.
   - **Affects:** HP-HF, HP-CF, and HP-CS through its keys.
3. **Patterns: the confirmed controls (HP-HC, HP-CC).**
   - **What.** The confirmed alert names one pattern, the first hit (L783, L793-795). HP-HC reads the detections
     whose first hit is a harmonic, HP-CC those whose first hit is a chart pattern (gold 1H: 840 and 110 of 950).
     A chart pattern behind a harmonic first hit raises no chart alert (23 on gold 1H).
   - **The decision close.** It is the detection bar's close (port A's `close`), not `c0`, the close of D's bar
     that the chart tests read (L781). The rule "skipped when the close is already beyond TP1" reads the decision
     close.
   - **Affects:** HP-HC, HP-CC, and claim 19's comparison.
4. **Patterns: HP-CS's "every condition except the breakout close".**
   - **What.** It is the chart test without its last condition: close above Q2 for a bullish id, below for a bearish
     one. This is the only place the close is read (L322-480; a test checks the source). It is evaluated on the
     forming state, as `HP.armed(pid, out["forming_q"])`, with p2 = Q2.
   - **Known when.** It reads only the fixed swings Q1-Q8. So it is known at the close of the bar where the latest
     swing was added and holds, unchanged, until the next swing is added. At that bar the same swings pass to the
     confirmed check.
   - **The order.** Its key is that of a forming instance. The stop order is placed at the close of the bar where
     the key is first armed, and is valid while the key stays armed.
   - **Counts.** Gold 1H has 312 armed chart instances in Development, BTC 1H 421.
   - **Affects:** HP-CS.
5. **Patterns: "30 bars after D" for a forming entry.**
   - **What.** D is the live swing at the decision close (the row's `b0`). A later move of the live swing does not
     move the time stop. For HP-CS it is the live D at the order's placement. A confirmed row's D is fixed.
   - **Affects:** HP-HF, HP-CF, HP-CS (and HP-HC, HP-CC through their fixed D).
6. **Patterns: HP-DRAWN's patterns.**
   - **What.** The script draws a confirmed first hit only when it does not overlap a pattern still on the chart
     (L785, L790-792). The alert is not gated. HP-DRAWN (information only) is computed on the same confirmed first
     hits as the controls (harmonic first hits as HP-HC, chart first hits as HP-CC), so each pair differs only in
     the entry time. The drawn subset (`drawn`: gold 1H 641 of 950) is reported beside it.
   - **Note.** On our bars no first hit is suppressed by any drawn pattern but the newest, so the 15-pattern history
     does not matter.
   - **Affects:** HP-DRAWN and claim 18, information only.

## 9. Notes for the study's code

- **Run.** `from backtesting.research import tradeiq2_ind_patterns as HP`, then `out = HP.patterns(b.h, b.l, b.c)`
  on `b = mk.tbars(tf)`.
  - Bar indexes (`t_bar`, `b0`..`b8`) count from 0, the first bar given. Map them to times with `b.tc[t_bar]`.
  - Port A takes under a second per series. Port B takes a few seconds and is for tests only.
- **The rows each rule reads.** `fm = out["forming"]`, `cf = out["confirmed"]`.
  - **HP-HF.** `f = fm[fm.first_hit & (fm.id <= 21)]`, then keep `~f.instance_key.duplicated()`: one row per entry
    bar. Market entry after `t_bar`'s close. Stop `sl`, targets `tp1` / `tp2`, time stop `b0 + 30`. Skip when
    `close` is at or beyond `tp1`.
  - **HP-HC.** `cf[cf.first_hit & (cf.id <= 21)]`, with the decision close `close`.
  - **HP-CF.** `fm[(fm.id >= 22) & fm.first_bar_of_instance]`, one entry per (`t_bar`, `dir`).
  - **HP-CC.** `cf[cf.first_hit & (cf.id >= 22)]`.
  - **HP-CS.** For each chart id, `HP.armed(pid, out["forming_q"])`, with the key
    `(pid,) + tuple(out["forming_qbar"][t, 1:HP.PTS[pid]])` and the neckline `out["forming_q"][t, 2]`. The levels are
    `HP.plan_levels(pid, out["forming_q"][t])` (unit, entry, stop, TP1, TP2).
  - **HP-DRAWN.** `cf[cf.first_hit]`, with D's bar `b0` and the drawn levels `entry` / `sl` / `tp1` / `tp2`.
    `drawn` marks the subset on the chart.
- **Two traps.**
  - `c0` is not the decision close on confirmed rows.
  - A chart row's `p0` (the live D) is not its entry; its entry is `p2`.
