# Wyckoff (theUltimator5): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values, event counts, bar times and
stop geometry in ATR. No Wyckoff rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_wyckoff.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_wyckoff.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_wyckoff.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_wyckoff_a.py` and `tests/test_tradeiq2_ind_wyckoff_b.py`: each port's own tests (one
    hand-computed case for each of the specification's 12 traps, synthetic properties, the real-bar vectors).
- **The rules:** `PREREG.md` section 6.3, and claims 15-17 of section 8, which read the same outputs.
- **The script:** "Wyckoff [theUltimator5]", Pine v6, 3,199 lines, of which about 1,000 compute and the rest draw.
  It is third-party code. Line numbers (L...) refer to the owner's copy. The source is not in this repository.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- The two ports give the same numbers, bit for bit, on every output and every bar. The bars: XAUUSDm and BTCUSDm,
  1H, 4H and 1D, from the study's data start to 2024-06-30. The volumes: gold's tick volume, BTC's Binance and Exness
  tick volume, and gold without volume as an extra check.
- The engine's internal series agree bit for bit as well: the trend score, the swing length, the swing points, the
  resets and the range's maturity. No tolerance was needed anywhere.
- The reconciliation found one mismatch: the two ports numbered campaigns differently. It was settled on port B's
  numbering, the script's own `s.startBar`, and port A changed. It cannot move a signal or an exit. Two API defaults
  also differ (`mintick`, the chart's seconds), and they are shown to be immaterial on these bars (section 4).
- A third, unreviewed port, written earlier to plan the study, puts every event of 28 kinds on the same bar, on all
  12 series. Its planning counts for the spring family were higher by exactly the "adoption" bars, which the plan's
  wording excludes (section 5).
- Eight readings add to the plan and are proposed for `DEVIATIONS.md` (section 8). Three of them matter most:
  - the S-W stop's "hard level";
  - the WY-SP exit after a provisional spring, where a literal X-S would close the trade one bar after entry;
  - the size of the WY-SP stop.

## 1. What the script computes

All settings are the script's defaults. Only "Entry Strictness" (L28; Standard by default) reaches the signals, and
the study takes all three settings (Standard, Aggressive, Conservative) from one pass. The script follows one campaign
at a time through the five Wyckoff phases:

1. **Phase A, the stop of a trend (L1254-1311).**
   - A **selling climax** (SC) is a bar that makes a new 30-bar low in a downtrend.
     - Its volume is at least 1.8 times the 50-bar average, and its range at least 1.5 times the ATR(14). Both
       thresholds are relaxed by 0.8 in a strong trend.
     - These four are required, plus one of two more clues (a score of 5 of 6): a close in the upper 65% of the bar,
       or an "exceptional" bar (the highest volume of 30 bars, or a range of 2.25 ATR).
     - The downtrend comes from a prior-trend score (-100 to 100; at most -15 is a downtrend, 35 in size a strong
       trend). Its window is 25-80 bars long and ends 2-8 bars before the bar. It adds up the net move in ATR, the
       efficiency of the path, the swing structure and the slope of the SMA(200).
   - A **buying climax** (BC) is the mirror.
   - The "climax confirmed" alert comes when the climax is **absorbed**, 3 to 8 bars later:
     - the volume of the last 3 bars holds up;
     - those bars do not undercut the climax low by more than 0.5 ATR;
     - the close is at least 0.35 ATR above the low.
   - The **automatic rally** (AR) is the highest high of the 30 bars after an SC. It must be at least 2 ATR above the
     low.
2. **Phase B, building the cause (L1313-1475).**
   - Phase B starts at the first **secondary test** (ST): a swing low near the SC's low, on lower volume and a
     narrower bar than the climax.
   - Later STs move the range low to a robust median of the last three.
   - Swings at the other edge are "opposite tests".
   - Swings that alternate between the bottom and top quarters of the range are "traversals".
   - The range becomes **mature** when four conditions hold:
     - 30 to 60 bars of Phase B (more for wider swings and taller ranges);
     - two STs;
     - a range height between 1.125 and 16 climax ATRs;
     - two of four supporting clues.
3. **Phase C, the test (L1328-1369, L1477-1502, L1531-1610).** There are two routes:
   - **The spring route.** A **spring** is a dip of 0.15 to 2.5 ATR below the range low that closes back inside
     within 3 to 8 bars. The recovery bar must score at least 3 of 4: a close in the upper part of the bar, an up bar,
     no volume surge, and a real range. Its **test** is a later swing low that holds the spring on lower volume.
   - **The terminal test** (no spring). A swing low near support whose volume or range is below 85% of the STs'
     average, with the other at most 105%.
   - In a range that is not yet mature, a spring is stored as **provisional**, with no alert.
   - The **UTAD** is the upside mirror of a spring.
4. **Phase D, strength (L1613-1676).**
   - A **sign of strength** (SOS) is a strong bar after the test. It closes above the range, or makes two closes in
     the range's top 35%.
   - A breakout straight from Phase B also counts when it **adopts** a provisional spring.
   - A **last point of support** (LPS) is a later higher swing low, within 1.5 ATR of the old range top, on quiet
     volume.
5. **Phase E, markup (L1696-1727).**
   - It needs 3 to 5 closes above the range and enough confidence.
   - It sets the **regime** (markup or markdown), which the script keeps for good. The regime decides later whether
     a campaign of the other side needs an LPS before its Phase E.
6. **Retirement (L1181-1234, L1643-1676).** A campaign is dropped when it fails:
   - invalidation: 2 closes 0.5 ATR beyond the "hard level";
   - no absorption;
   - no range forms;
   - price departs from Phase B without a provisional spring;
   - no activity for too long;
   - Phase E ends (3 closes back below mid-range, or 300 bars).

   A Phase D campaign whose last 3 closes fall below mid-range is **demoted** back to Phase B. It keeps its used
   entry slot.
7. **The entry (L1729-1747; the alert L2236-2238).** At most one per campaign and setting:
   - **Standard** fires on the bar of a Phase C test (the spring's test or a terminal test), given validation of at
     least 50, confidence of at least 60 and 6 of 9 readiness clues. Failing that, it fires on the first qualifying
     LPS.
   - **Aggressive** uses the test, or the SOS when there was no test.
   - **Conservative** uses the LPS only, with stricter scores.
   - The alert fires at the close of that bar ("long entry qualified"). Its direction is the campaign's outcome.

**Timing.**
- Every decision is taken at a bar's close, from bars up to that close.
- Swing points are confirmed `pLen` bars after the swing bar. `pLen` is 2-10 bars and usually 4. So an ST, a test or
  an LPS becomes known, and its alert fires, `pLen` bars after the low it describes.
- The labels (SC, AR, ST, Spring, Test, LPS), the phase letters and the schematics are drawn back in time, at the
  swing or the climax bar. They are never used.
- The entry alert never repaints.

**What the study reads** (PREREG 6.3; one value per bar, at its close; `W.CONTRACT_KEYS`):

| Output | Meaning | Used by |
|---|---|---|
| `entry_std`, `entry_agg`, `entry_con` | +1 / -1 on the bar the entry alert fires, per setting | WY-STD, WY-STD-L (+1 only), WY-AGG |
| `hard_lo`, `hard_hi` | the script's hard level (`f_hardLevel`, L723-729), see section 3 | the S-W stop |
| `in_cde`, `campaign`, `outcome`, `phase` | whether the campaign holds an outcome in Phases C-E; its id (the seed bar); its side; its phase | the X-S exit |
| `climax`, `climax_px` | +1 SC / -1 BC on the bar the climax is confirmed; the climax bar's low / high | WY-CL |
| `exc`, `exc_px` | +1 spring / -1 UTAD on the recovery bar of a confirmed or provisional excursion; its extreme then | WY-SP |
| `ev_sc` ... `ev_phase_e` | the 13 alert bits (the script's alerts L3188-3197) | counts, claims 15-17 |
| `range_lo`, `range_hi` | the script's current range edges | information |

The kind of an entry (claim 16) comes from the bits on its bar. A test or CTest bit makes a test entry, an LPS or
LPSY bit an LPS entry, and an SOS or SOW bit alone an SOS entry (Aggressive only). On our bars the bits never
overlap, and this equals the script's own `entryKind` (L1747).

## 2. What was compared, and how

- **The bars.** The study's 1H, 4H and 1D bars (`PREREG.md` section 2), up to 2024-06-30.
  - The M1 bars were read with `external.load_market(symbol, earliest=..., end="2024-07-01")`, so nothing from the
    hold-out was loaded. Study 1's `TMarket.tbars` built them into bars, which is what `tradeiq2_market.load` serves.
  - Gold starts on 2016-01-03 (the 2016 warm-up months) and BTC on 2018-01-01: 49,956 / 13,500 / 2,183 gold bars and
    56,840 / 14,225 / 2,372 BTC bars on 1H / 4H / 1D.
  - Gold was also run from 2017-01-03, study 1's start, because the outputs depend on where the bars start. Both
    ports agree there too (checked in scratch), and the test checks that the engine started there equals the 2016
    start on every bar closing after 2018-01-01 (section 3, item 17).
- **The volumes.**
  - Gold on tick volume.
  - BTC on Binance BTCUSDT volume (`tradeiq2_market.binance_volume`; PREREG 2), and on Exness tick volume for the
    control rows.
  - Gold without volume (the script's own fallback, effort = the bar's range) was added to exercise that branch. It
    is not a PREREG series.
  - That makes 12 series.
- **What had to agree, on every bar of every series.**
  - All 28 contract outputs. Integers and yes/no flags were compared exactly. Decimal numbers had to be the same 64
    bits, with missing values on the same bars.
  - The event tables:
    - every entry, with its setting, side, kind, close, hard level, campaign and X-S exit bar;
    - every climax confirmation and its price;
    - every spring / UTAD recovery, its extreme and whether it was confirmed or provisional;
    - every alert bit.
  - 29 internal series of the engine:
    - the effort, the spread, the average effort and its previous value;
    - the raw ATR, the ATR with its fallback, and the previous ATR;
    - the close position and the relative effort;
    - the prior 30-bar extremes and the new-low / new-high flags;
    - the adaptive swing length and its 3-bar-old value;
    - the trend window's length and end;
    - the SOS / SOW scores;
    - the bar's swing length and its swing points, and whether they are new;
    - the prior-trend score;
    - both reset codes;
    - Phase B maturity;
    - the alert mask.

    Port B's values come from its own inspection hook (`Engine.trace`). That hook only reads, and the plain port B
    gives the same outputs.
  - The X-S exit of every entry, in both ports' readings of the contract (section 4).
  - The 2019-2022 counts of section 6, recorded in the test.
- **Is the test sharp?** Its bit-for-bit comparison was applied, in scratch, to port B deliberately broken in memory:
  - **A true sorted median in the range-edge rule,** in place of the script's `e1 + e2 + e3 - max - min` (L693).
    Range edges then differ in the last bit on 55 (low) and 205 (high) gold 1H bars, for example
    1772.8840000000005 against 1772.884. The bit-for-bit comparison catches it; `numpy.allclose` at 1e-12 would not.
  - **Python's round-half-to-even** in place of Pine's round-half-up. Ten outputs change on gold 1H: phases,
    campaigns, range and hard levels, the climax bits.
- **Arithmetic.** Both ports already followed the script's order of operations, so nothing had to be aligned:
  - SMA: `x[i] / n` added from the newest bar.
  - Wilder ATR: `alpha * TR + (1 - alpha) * previous`, seeded with the SMA of the first 14 true ranges; the first
    bar's true range is high - low.
  - `math.sum`: added from the newest bar.
  - The trend score: `disp + erPart + swingPart + smaPart` in that order; the path summed from the oldest bar.
  - The climax thresholds: `avgEffPrev * 1.8 * relaxK`.
  - The range-edge median: as above.
- **How close it came to a threshold.** On the trend score, which decides "downtrend" (at most -15) and "strong
  trend" (at least 35 in size), no bar of any series comes within 1e-4 of a threshold. So a last-bit difference
  there could not have flipped a decision on these bars.
- **Running it.**
  - All three test files pass together: 85 tests (17 + 43 + 25) in about 95 s, at a peak of 1.4 GB resident
    (0.57 GB of the process's own memory). One symbol's bars are in memory at a time.
  - Port A needs about 0.1-0.5 s for a 1H series once numba has compiled it (25 s, cached). Port B, plain Python,
    needs 6-7 s.

## 3. The Pine readings, with their evidence

1. **Swing points with a length that changes from bar to bar (L1105-1107).**
   - **The reading.** `pLen` is the campaign's `pivLen` while a campaign exists, else the ATR-adaptive `liveLen`. It
     is taken from the state at the start of the bar, because L1105 runs before the bar's update at L1162.
   - `ta.pivothigh(high, pLen, pLen)` is read as stateless: each bar checks the window of its own `pLen`, and the
     swing is known `pLen` bars after its bar.
   - **Evidence.** TradingView's reference gives these built-ins series lengths and asks for `max_bars_back` when the
     lengths are series. That fits a look-back over each bar's own window. Both ports, and the scratch port, read it
     this way.
2. **Ties in the swing points (L1106-1107).**
   - **The reading.** Strict on both sides: a swing high must be above every other high of its window. This is
     PREREG 6.2's reading for the dashboard.
   - **Measured.** Accepting equal neighbours changes 0.0-0.1% of the swing candidates and no entry on any series:
     - on the newer side (or both), one extra ST on gold 1H at 2023-09-13 22:00, and that range's spring recovery two
       bars earlier, at 14:00 instead of 16:00 on 2023-09-14 (Validation);
     - on the older side, one extra ST on gold 4H without volume, in the warm-up (2018-11-07).
3. **The trend score's loop (L590, `for k = n - 1 to 0`).**
   - **The reading.** It counts down, so closes and swing points are visited oldest first. Higher highs, lower highs,
     higher lows and lower lows compare consecutive swings in time order.
   - The swing series inside it (L593-594) is the history of the bar-by-bar swing values, each found with its own
     bar's length.
   - **Evidence.** Pine's `for ... to` steps by -1 when the start is above the end. Counting up would swap higher
     highs with lower highs.
4. **Rounding.**
   - **The reading.** `math.round` rounds ties up, which Pine documents. So the recovery limit for a swing length of
     6 is `round(4.5)` = 5, and the swing length at 4 × 0.625 = 2.5 is 3. `int()` truncates.
   - The ports compute ties-up as `floor(x) + (x - floor(x) >= 0.5)`, which is also exact just below one half.
   - **Measured.** Python's half-to-even would move 6 gold 1H and 18 BTC 1H climax confirmations, among others (port
     B's measurement), and changes ten outputs on gold 1H (section 2).
5. **Precedence at L1592.**
   - **The reading.** `recAge > recLimit or not depthOK and depth > 2.5a` means `recAge > recLimit or ((not depthOK)
     and depth > 2.5a)`.
   - **Evidence.** Pine's precedence is `not` before `and` before `or`.
6. **Warm-up.**
   - **The reading.** `ta.sma`, `ta.atr`, `ta.highest` and `ta.lowest` are missing until their full length. The
     script's own fallbacks then apply as written: the ATR falls back to the bar's range, the average effort to the
     bar's effort, and the previous values to the current fallback (L1067-1072, L1109-1114). So no climax can occur
     before bar 30.
7. **`syminfo.mintick`.**
   - **The reading.** 0.001 for gold and 0.01 for BTC, the repository's digits. They are also the price grid of our
     bars.
   - The tick is only a floor (`max(x, mintick)`). It binds on bars with high = low: 90 gold 1H bars, 4 gold 4H
     bars and 2 BTC 1H bars.
   - **Measured.** Swapping 0.001 and 0.01 changes no output on any series.
8. **`timeframe.in_seconds` (L961).**
   - **The reading.** The chart's bar length. It only scales the "age since the last event" clue of the readiness
     count.
   - **Evidence.** That age is 0 on every bar where an entry can fire, because each entry trigger is set together
     with the event stamp. A 1-second chart gives identical outputs.
9. **Volume (L1063-1066).**
   - **The reading.** A missing volume counts as 0.
   - The script uses the bar's range as the effort only while the cumulative volume is still 0. After the first
     volume it never does again. So a Binance hour without a kline has effort 0, not the range.
   - BTC's Exness tick volume is a heartbeat: the climax volume gate passes on 0.6% of BTC 1H bars with it, against
     10.3% with Binance volume (port A's test).
10. **`_commit = barstate.isconfirmed` (L1795).** Every historical bar is a closed bar, and the engine updates once
    per bar.
11. **The three settings in one pass.**
    - **The reading.** The entry slot (`s.entryTime`) is read only by the entry check itself (L1729). So three slots
      give exactly what three runs of the script would. A demotion keeps the slot (`f_demoteToB`, L909-930, does
      not touch it).
    - **Evidence.** Port B's tests compare one pass with three single-setting passes.
12. **The entry alert.**
    - **The reading.** `int(cEntryT) == time` (L2236): the alert fires on the bar whose close sets the slot, in the
      direction of the outcome at that close.
    - The stored entry labels (L1798, L2229-2234) are not used. They carry the current outcome, so a demotion
      followed by a UTAD can draw a "short entry" at an old long's time. Port B found 4 such sequences on our bars.
13. **The hard level (`hard_lo` / `hard_hi`).**
    - **The reading.** The script's own `f_hardLevel` (L723-729), the level its invalidation tests:
      - for a long, the spring's extreme when the campaign holds an accumulation outcome from a spring;
      - otherwise the lower of the original and the current range low. On a selling-climax campaign that is the
        climax low, because the robust range low never goes below it (L690-698);
      - shorts mirror this.
    - **Evidence.** It is the "hard level" PREREG 6.3 names. It reproduces the specification's stop geometry (claim
      16; section 6).
    - The plain range edge is a different level at most entries (section 8, entry 1).
14. **The hold (`in_cde`) and the X-S exit.**
    - **The reading.** `in_cde` is True when the campaign holds an outcome in Phases C-E at the close and was not
      demoted during the bar.
    - It is False on a bar where a demotion is followed by a new test or spring, because PREREG 6.3 lists "a
      demotion" among the breaks. On our bars that happens once: BTC 1H (Binance), 2023-11-22 00:00, Validation.
15. **The spring family's bar (`exc`).**
    - **The reading.** The recovery bar of a confirmed or provisional excursion (L1574). The breakout bar that later
      adopts a provisional spring (L1654-1660) is not a new recovery.
    - **Evidence.** PREREG 6.3: "enter at the recovery bar". Section 5 gives the counts.
16. **The campaign id.** The seed bar's index (`s.startBar`, L734). It is unique: at most one seed per bar (L1265).
17. **Where the engine starts.**
    - **The reading.** The engine runs from the first bar given, and the study passes the bars from the data start.
    - **Measured.** Gold from 2017-01-03 gives exactly the 2016 start's outputs on every bar closing after
      2018-01-01. The two runs differ only inside 2017, through 2017-09-03.
    - BTC started on 2018-07-01 gives exactly the same outputs from 2019 on. Started on 2018-10-01, BTC 1D on Binance
      volume would differ until 2019-05-03.
    - Port A's test also shows that gold 4H started only 300 bars before 2019 differs until 2022-01, entries
      included.
18. **What is not ported, because no output depends on it.**
    - The preliminary support / supply (L1237-1252; it feeds only the BIT_PS bit, which nothing reads). Port B ports
      it, port A does not.
    - The campaign type and context (`ctxBull` / `ctxBear`, `regimeBar`).
    - The swing triplets, scores and times kept for labels.
    - The higher-timeframe scan and override (L1766-1770, L1897-2008; display only, and the alerts are on the chart's
      timeframe).
    - Every drawing.
19. **Two smaller points.**
    - Pine v6's lazy `and` / `or` is immaterial: no condition has a side effect.
    - The readiness check's own validation call (L971) uses `nz(s.pivLen, pivotLen)` and `s.birthTrend`. Inside a
      campaign both are always set, so it equals the entry check's call.
20. **An observation, not a choice.** The 25-bar "opposite cycle" gates (L1175-1176) can never block, because Phase
    C needs at least 36 bars after the climax. The regime acts only through the Phase E rule that an LPS is needed
    after an opposite regime (L1702, L1716).

## 4. Mismatches found, and how each was resolved

The two ports were written independently, and each author listed the same contract questions: the hard level, the
same-bar demotion, the adoption bars and the tick. They had answered all of them the same way. On the real bars no
output, no event and no internal series differed. Three things did differ.

1. **The campaign id (a contract choice, not a Pine reading).**
   - Port A numbered campaigns 0, 1, 2, ... in seeding order. Port B used the seed bar's index, the script's own
     `s.startBar`. The partitions (which bars belong to which campaign) were identical on every series.
   - **Resolved on `s.startBar`; port A changed.**
     - It is the script's field.
     - It locates the climax that seeded the campaign.
     - It shifts exactly with the start of the bars, so start-invariance can be checked on the ids too.
   - Port A's kernel now writes `s.startBar`, and the two counter slots left its outside-state array. Port A's tests
     changed with it:
     - the state helper;
     - three trap tests that asserted ids;
     - a new invariant: the id is the seed bar;
     - the start-invariance test, which now compares the ids, shifted.
   - It cannot move a signal or an exit.
2. **API defaults.**
   - Port A's `mintick` defaults to gold's 0.001; port B infers the price grid.
   - Port A's chart seconds default to the smallest step of the open times; port B takes the most frequent step.
   - On every series the inferred grid is the repository's tick and the two steps are equal. Port A run with its
     defaults, or with the other symbol's tick and a 1-second chart, gives exactly the same outputs (tested).
   - **Left as they are and documented.** The study passes `mintick=W.MINTICK[symbol]`.
3. **The alert mask's BIT_PS bit (internal, not a contract output).** Port B sets it, port A does not port it.
   Nothing in the script reads it (no `f_hasBit` call and no alert), so the internal comparison reads port B's mask
   without it, as the test explains.

Since both ports agree, a common error would go unseen by the comparison. That is why each port also carries one
hand-computed test for every trap of the specification, and why the third opinion below was run.

## 5. A third opinion: the unreviewed scratch port of the planning pass

The specification's scratch port (`work/wy_port.py`, read-only, never imported from the repository) uses different
arithmetic:
- pandas rolling means and sums;
- a Wilder update written `(x + (n - 1) v) / n`;
- `floor(x + 0.5)` rounding.

It was run on the same 12 series, over the whole span from the data start to 2024-06-30. For each of 28 kinds of
event, its list of bars was compared with the reconciled ports': the 13 alert bits, the seeds, the six reset
reasons, the demotions, the provisional excursions, and the entries per setting and side. **Every list is
identical.** The hard level at every one of its entries equals the ports' value.

The only difference from the specification's planning numbers is one of definition. Its spring-family counts (D-SP:
gold 1H / 4H / 1D 66 / 11 / 0, BTC on Binance 123 / 26 / 4) counted the provisional recoveries plus every
Spring/UTAD alert bit. That includes the bit a breakout sets when it adopts a provisional spring. The recovery bars
are 64 / 11 / 0 and 122 / 25 / 4; the difference is exactly the adoption bars (gold 1H 2, BTC 1H 1, BTC 4H 1).
PREREG 6.3 enters WY-SP at the recovery bar, so the adoption bars are not entries (section 8, entry 2).

## 6. Event counts per symbol and timeframe, 2019-2022

Bars closing in Development, 2019-01-01 to 2022-12-31, from the study's data start. The two ports give these numbers,
the test records them, and the scratch port puts each event on the same bar. The ST row counts all secondary tests;
the AR row counts the starts of Phase B (an AR and the first ST, reported together). The spring / UTAD bits include
the adoption bars. "Recovery bars" are WY-SP's candidates. Entries are given as long / short.

**Gold, tick volume**

| Event | 1H | 4H | 1D |
|---|---|---|---|
| Climax confirmed, SC / BC (WY-CL) | 52 / 105 | 22 / 28 | 1 / 5 |
| Phase B starts (AR) / all STs | 33 / 65 | 6 / 13 | 1 / 1 |
| Spring / UTAD bits | 7 / 9 | 2 / 2 | 0 / 0 |
| Test / terminal test (CTest) | 1 / 1 | 1 / 0 | 0 / 0 |
| SOS / SOW | 3 / 5 | 2 / 0 | 0 / 0 |
| LPS / LPSY | 0 / 2 | 1 / 0 | 0 / 0 |
| Phase E | 5 | 1 | 0 |
| Recovery bars, spring / UTAD side (WY-SP) | 33 / 31 | 5 / 6 | 0 / 0 |
| of which confirmed / provisional | 14 / 50 | 4 / 7 | 0 / 0 |
| Adoption bars | 2 | 0 | 0 |
| Entries: Standard | 1 / 3 | 1 / 1 | 0 / 0 |
| Entries: Aggressive | 4 / 5 | 1 / 1 | 0 / 0 |
| Entries: Conservative | 0 / 2 | 1 / 0 | 0 / 0 |

**BTC, Binance volume**

| Event | 1H | 4H | 1D |
|---|---|---|---|
| Climax confirmed, SC / BC (WY-CL) | 183 / 192 | 36 / 59 | 7 / 11 |
| Phase B starts (AR) / all STs | 69 / 110 | 12 / 23 | 4 / 4 |
| Spring / UTAD bits | 9 / 8 | 4 / 3 | 0 / 0 |
| Test / terminal test (CTest) | 7 / 8 | 3 / 1 | 0 / 0 |
| SOS / SOW | 4 / 5 | 2 / 0 | 0 / 0 |
| LPS / LPSY | 2 / 1 | 1 / 0 | 0 / 0 |
| Phase E | 5 | 2 | 0 |
| Recovery bars, spring / UTAD side (WY-SP) | 53 / 69 | 15 / 10 | 2 / 2 |
| of which confirmed / provisional | 16 / 106 | 6 / 19 | 0 / 4 |
| Adoption bars | 1 | 1 | 0 |
| Entries: Standard | 7 / 7 | 4 / 1 | 0 / 0 |
| Entries: Aggressive | 8 / 8 | 4 / 1 | 0 / 0 |
| Entries: Conservative | 2 / 1 | 1 / 0 | 0 / 0 |

**BTC, Exness tick volume (the control)**
- 1H: SC 30, BC 22, AR 11, ST 17, spring 1, UTAD 3, CTest 1, nothing else. Recovery bars 9 / 12 (4 confirmed). One
  Standard and one Aggressive short, no Conservative entry.
- 4H: SC 7, BC 1, nothing else.
- 1D: SC 2, nothing else.

**Gold without volume (information; not a PREREG series)**
- 1H: SC 81, BC 151, AR 47, ST 93, spring 9, UTAD 10, test 3, CTest 11, SOS 7, SOW 7, LPS 2, LPSY 3, Phase E 8.
  Recovery bars 37 / 40 (16 confirmed), 3 adoption bars. Entries: Standard 7 / 8, Aggressive 9 / 8, Conservative
  2 / 3.
- 4H: SC 26, BC 33, AR 8, ST 20, spring 1, UTAD 4, test 3, nothing else. Recovery bars 5 / 10 (5 confirmed). Entries:
  Standard 0 / 3, Aggressive 0 / 3, none Conservative.
- 1D: SC 1, BC 11, AR 1, ST 2, nothing else.

**The Standard entries of Development** (bar open, UTC; the kind from the bar's bits)
- **Gold 1H:**
  - 2020-07-16 07:00, short, CTest;
  - 2021-06-28 19:00, long, Test;
  - 2021-10-31 23:00, short, LPSY;
  - 2021-11-23 04:00, short, LPSY.
- **Gold 4H:**
  - 2020-05-24 20:00, short, Test;
  - 2022-01-04 08:00, long, LPS.
- **BTC 4H (Binance):**
  - 2019-01-24 16:00, long, Test;
  - 2020-06-10 12:00, short, CTest;
  - 2020-07-04 12:00, long, Test;
  - 2021-06-25 00:00, long, Test;
  - 2021-12-25 00:00, long, LPS.
- **BTC 1H (Binance):** 14 entries, 7 terminal tests (CTest), 4 tests and 3 LPS:
  - 2019: 02-23 15:00 short CTest; 03-20 15:00 short CTest; 08-11 03:00 long CTest; 12-30 10:00 short Test;
  - 2020: 04-09 12:00 short CTest; 09-08 17:00 long Test;
  - 2021: 03-02 12:00 long LPS; 03-23 21:00 short LPSY; 04-27 09:00 long LPS; 05-12 03:00 long Test; 08-17 10:00
    long CTest; 10-10 19:00 short Test;
  - 2022: 01-03 07:00 long CTest; 12-06 04:00 short CTest.
- **BTC 1H (tick):** one entry, 2021-09-25 03:00, short, CTest.

**What this says about the claims** (counts only)
- **Claim 15, "strict and rare".** Over the four years: one Standard entry a year on gold 1H, half a year on gold 4H,
  none on 1D. On BTC (Binance): 3.5 a year on 1H, 1.25 on 4H, none on 1D.
- **Claim 17, "on the 4-hour or the daily".** In these four years the daily gives no entry, no confirmed spring and no
  test on either symbol. BTC's daily has 4 provisional recoveries.
- **Claim 16, "the risk is smallest at the spring and the test".** The distance from the entry's close to the hard
  level, in ATR(14) of the entry bar, pooled over gold (tick) and BTC (Binance), three timeframes, Development:
  - a median 2.7 at Standard test entries (n 18);
  - 4.8 at Aggressive SOS entries (n 14);
  - 6.8 at LPS entries (n 7);
  - the specification's numbers, reproduced by both ports (port A's test).

## 7. What may still differ from TradingView

1. **No TradingView output was available.** Both ports were checked against the source, the specification, each
   other and the scratch port, never against the script running on TradingView.
2. **The data are not any TradingView chart's.**
   - The prices are Exness's bid.
   - Gold's volume is Exness's tick count. A TradingView CFD feed counts its own ticks.
   - BTC's volume is Binance's, on Exness's prices. Binance's own BTCUSDT chart has slightly different prices
     (DATA.md: a median 0.07% apart, more in 2018-19).
   - Our 4H and 1D bars are on UTC boundaries, with short days merged into the next day. A TradingView CFD chart's
     days and 4-hour bars usually follow the feed's session (often 17:00 New York). So dates and some events differ.
3. **Where the chart starts.**
   - The script's regime and last swing bars never reset, so the first months of any chart depend on where it starts.
   - TradingView loads a history whose length depends on the user's plan. On our bars, 6-12 months of history were
     enough for every later bar (section 3, item 17). A chart that starts later than ours can differ early on.
4. **Undocumented built-in behaviour.**
   - Ties in `ta.pivothigh` / `ta.pivotlow` (measured: no entry moves).
   - Their internals when the length changes from bar to bar (not measurable here).
5. **Floats.**
   - Pine computes in 64-bit floats, and both ports keep the script's order of operations, so the same bits are
     expected.
   - That cannot be confirmed without TradingView. On these bars no trend-score decision was within 1e-4 of its
     threshold, and the last-bit differences of the median mutation (section 2) moved no event.
6. **What a TradingView user sees that the study does not use.**
   - The higher-timeframe override (on by default) can show another timeframe's campaign and entry labels. A
     higher-timeframe entry label sits at that bar's open, up to one higher-timeframe bar before it was known.
   - The labels and schematics are drawn back in time, and historical schematics keep only campaigns that reached
     Phase C.
   - The stored entry labels can show phantom entries.
   - The study uses only the chart timeframe's entry alert, decided at the close, as PREREG 6.3 says.
7. **The live chart.** The engine updates only on confirmed bars, so on a live chart the alerts come at the bar's
   close, as on historical bars. This holds if the alert is set to fire once per bar close.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

These readings settle points that PREREG 6.3 leaves open, and each can move a result. They are proposed for
`DEVIATIONS.md`, to be logged before any Wyckoff result exists. Readings 1, 2, 5, 6, 7 and 8 are what the ports compute.
Readings 3 and 4 are for the study's rule code: the ports supply what it needs (`campaign`, `outcome`, `phase`,
`in_cde`, `exc_px`).

1. **S-W: "the hard level" is the script's `f_hardLevel`.**
   - **What.** On selling-climax longs without a spring, the S-W stop goes under the climax low, not under the
     current range low (shorts mirror this).
   - **Measured.** The plain range edge is a different level at 5 of 7 gold 1H, 3 of 4 gold 4H, 20 of 23 BTC 1H and
     9 of 9 BTC 4H Standard entries of 2019 to mid-2024. It is 0.8-1.4 ATR closer to the close in the median.
   - **Affects:** every S-W row, the skip guard, the 3R targets, the pooled test and claim 16.
2. **WY-SP enters at the recovery bar, never at the adoption bar.** The planning counts included the adoption bars.
3. **WY-SP's X-S after a provisional excursion.**
   - **The problem.** At a provisional recovery the campaign is still in Phase B with no outcome, so a literal X-S
     closes the trade on the next bar. That happens on every provisional recovery of our bars, and provisional
     recoveries are most WY-SP entries (gold 1H 50 of 64, BTC 1H 106 of 122 in Development).
   - **Proposed.** X-S starts once the campaign first holds the trade's side in Phases C-E. Before that, the trade
     exits on a reset or re-seed of its campaign, or when the campaign takes the opposite outcome.
4. **WY-SP's stop.**
   - **The extreme.** `exc_px`, the extreme as known at the recovery bar. It is fixed: the script's later extension
     of an untested spring moves the hard level, never this stop.
   - **The distance.** PREREG 6.3 gives none. Proposed: 0.15·ATR, as S-W and WY-CL use.
5. **A demotion ends the hold even when the same bar re-enters Phase C.** Once on our bars: BTC 1H, 2023-11-22 00:00
   (Validation). It is the X-S exit of the Standard and the Aggressive long of 2023-11-17 19:00.
6. **Swing-point ties are strict, as for the dashboard.** Measured: one gold 1H spring recovery in Validation moves
   by two bars; no entry moves.
7. **Swing points with a bar-by-bar length are read as stateless.** Supported by TradingView's own remark, but not
   measurable here.
8. **The engine runs from the study's data start.** Development and Validation do not depend on it; gold's Early
   window (exam 2) does, inside 2017.
