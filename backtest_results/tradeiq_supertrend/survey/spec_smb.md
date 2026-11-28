# Smart Money Breakout Signals [AlgoAlpha]: porting spec (study 4, TradeIQ video 3, script #2 of the video)

Written 28 Nov 2026 from the owner's copy, before any port, rule or backtest exists. Nothing here was run on market
data. Third-party code: it is restated below in formulas and plain words, never copied.

- **Source file:** `/Users/sidharthsingh/Desktop/study/trend/AlgoAlpha Smart Money Breakout Indicator.rtf`
  (sha256 of the RTF `84b4b47f2fa1076dbea6697ce44eacbe4aaee97bf1609f31b65a04d48d96d981`).
- **Plain-text copy used for line numbers (L..):** `textutil -convert txt -stdout "<file>"`, numbered from 1
  (290 lines; sha256 of that text `63bdb45e6e3efb540c94c7dfb68b9705642e34dc9edce9c0b69ee6c50592f281`).
- **Author:** AlgoAlpha (L2). Licence: MPL-2.0 (L1).
- **Pine version:** v6 (L3). An indicator, overlay, titled "Smart Money Breakout Signals [AlgoAlpha]" (L4).
- **Module key:** `smb` (as proposed in `infra.md` of this folder).

## 0. Bottom line

- The script finds swing highs and lows with 25 bars on each side (`ta.pivothigh` / `ta.pivotlow`, 25 / 25). The
  last confirmed swing high becomes a level, armed once.
- **Bullish signal:** the first close strictly above the armed level (a break of structure). The bearish signal is
  the mirror. Each level breaks at most once. A newer swing replaces an unbroken older one.
- At each signal it also draws three dashed target lines and keeps a stop, all measured from the **broken level**
  (not from the close) as fractions of the range between the swing and the break. A small table on the last bar shows
  "win rates" of the three targets.
- **Timing:** a swing is known 25 bars after it happened (on 4H, 100 hours: about four days). The break is decided at
  the close of the breaking bar with levels that were already confirmed. The signal does not repaint at the close.
  The BOS line and its label are drawn back in time, from the swing bar and at the midpoint, and only once the break
  has happened.
- **Traps:** pivot ties (undocumented); the pivot update comes before the break test on the same bar (a break of the
  old level can be swallowed); the range window excludes the swing bar; the operation order of the levels. The stats
  table counts target hits on the signal bar itself (before the close that made the signal) and never resets two of
  its trackers at the stop, so its win rates are biased up. They are not trade results.
- **Data:** OHLC only.
- **Effort:** about 35 computing lines for the signals and about 75 with the levels and the table's counters. About
  half a day per port; the repository's strict pivot helper can be reused.

## 1. Inputs and defaults (L6-L10)

| Input (title) | Variable | Type | Default | Used by the computation? |
|---|---|---|---|---|
| Market Structure Time-Horizon | `swingSize` | int | **25** | yes: pivot left and right bars |
| BOS Confirmation Type | `bosConfType` | string: 'Candle Close', 'Wicks' | **'Candle Close'** | yes: close or high / low for the break |
| Show CHoCH | `choch` | bool | true | label text only |
| Bullish Color | `BULL` | colour | #00ffbb | display |
| Bearish Color | `BEAR` | colour | #ff1100 | display |

Constants inside the body: RR = 1 (L80), the range divisor 3 (L78), the target fractions 1, 2/3 and 1/3 of the
distance (L103-L105, L118-L120).

## 2. Pine primitives the port must reproduce

Bars are indexed t = 0, 1, ... from the first bar of the data. A comparison involving na is false. In v6, booleans are
never na.

| Primitive | Definition used by both ports | Notes |
|---|---|---|
| `ta.pivothigh(high, L, L)` | On bar t (t >= 2L), the value high[t−L] if it is **strictly** greater than each of the L highs before it (bars t−2L .. t−L−1) and each of the L highs after it (bars t−L+1 .. t); else na | The repository's reading: `tradeiq2_ind_wyckoff.pivots(x, L, high=True, ties="strict")`; study 2 logged the tie rule as undocumented (trap 1) |
| `ta.pivotlow(low, L, L)` | The mirror with strictly smaller | as above |
| `ta.highest(x)` (one argument) | The highest **high** of the last x bars including the current one (bars t−x+1 .. t); x may change from bar to bar | The one-argument form reads `high`; `ta.lowest(x)` reads `low` |
| `bar_index` | t | |

## 3. The computation on each bar, in order

**State (all `var`, so it persists; the function `MS` is called once per bar at L58, so its `var` variables form one
persistent set).**

| Variable | Initial | Meaning |
|---|---|---|
| `prevHigh`, `prevLow` | na | the last confirmed swing high / low (the level) |
| `prevHighIndex`, `prevLowIndex` | na | the bar index of that swing |
| `highActive`, `lowActive` | false | the level is armed (not yet broken) |
| `prevSwing` | 0 | 2 HH, 1 LH, −1 HL, −2 LL; never read again (unused) |
| `prevBreakoutDir` | 0 | +1 / −1, the side of the last break; label text only |
| `active`, `active1`, `active2` | 0 | the script's "position" state and its two inner-target trackers |
| `TP`, `TP1`, `TP2`, `SL` | 0.0 | the levels of the latest signal |
| `total`, `tp1s`, `tp2s`, `tp3s` | 0 | the table's counters |

**Step 1, the swings (L13-L14).** pivHi[t] = pivot high value confirmed on bar t (that is, of bar t − 25) or na;
pivLo[t] likewise.

**Step 2, a new swing high (L26-L35).** If pivHi[t] is not na:
- it is labelled HH when pivHi >= prevHigh, else LH. With prevHigh na the comparison is false, so the very first swing
  is LH. Equal counts as HH. The labels feed nothing.
- Then prevHigh = pivHi, highActive = true, prevHighIndex = t − 25.
- So a newer swing high **replaces** the old level even if the old one was never broken, and re-arms the side.

**Step 3, a new swing low (L36-L45).** The mirror: HL when pivLo >= prevLow, else LL; prevLow = pivLo, lowActive =
true, prevLowIndex = t − 25.

**Step 4, the break tests (L46-L55), after steps 2-3 on the same bar.**
- highSrc = close and lowSrc = close for 'Candle Close' (default); high and low for 'Wicks'.
- highBroken[t] = highActive and highSrc[t] > prevHigh (strict). If true, highActive = false.
- lowBroken[t] = lowActive and lowSrc[t] < prevLow (strict). If true, lowActive = false.
- Consequences:
  - The confirmation bar of a swing high can never break it. Its high is strictly below the swing under the strict
    reading, and at most equal under any tie reading.
  - But the update comes first. If the bar that confirms a new swing high is also the first bar to close above the
    **old** level, that break is lost: the test now compares with the new, higher level. Hand test H2.
  - With 'Candle Close' a bar cannot break both sides. Both levels would have to be armed with prevHigh < close <
    prevLow, which a confirmed and unbroken pair cannot produce. With 'Wicks' an outside bar can break both
    (section 3, step 7).

**Step 5, the drawings and the break's span (L60-L74).** length = 0 on every bar; then:
- On a bullish break: a solid line from (prevHighIndex, prevHigh) to (t, prevHigh); a label at x = floor(t − (t −
  prevHighIndex) / 2) reading "CHoCH" if prevBreakoutDir was −1 (and `choch` is on), else "BOS"; an `alert()` with
  frequency once per bar; prevBreakoutDir = 1; length = t − prevHighIndex.
- On a bearish break: the mirror, with prevBreakoutDir = −1 and length = t − prevLowIndex. With both on one bar the
  bearish block runs second, so length and prevBreakoutDir are the bearish ones, and its label reads CHoCH.

**Step 6, the range (L76-L78).**
- x = max(1, length): 1 on bars without a break, the span on break bars.
- v = highest high of the last x bars minus the lowest low of the last x bars, both windows ending at t.
- So the window is bars prevHighIndex + 1 .. t: **it excludes the swing bar itself** and includes the breaking bar.
- dist = v / 3.

**Step 7, the levels (L97-L125).** trigger = 0 on every bar (L79).
- On a bullish break:
  - active = active1 = active2 = 1; trigger = 1; total += 1;
  - TP = prevHigh + dist; TP1 = prevHigh + (dist·2)/3; TP2 = prevHigh + (dist·1)/3; SL = prevHigh − dist / 1.
- On a bearish break:
  - active = active1 = active2 = −1; trigger = 1; total += 1;
  - TP = prevLow − dist; TP1 = prevLow − (dist·2)/3; TP2 = prevLow − (dist·1)/3; SL = prevLow + dist / 1.
- With both on one bar: total += 2 and the bearish values are the ones kept.
- Naming trap: TP is the **far** level (one third of the range beyond the level), TP1 two ninths, TP2 one ninth. The
  stop is one third of the range back through the level.

**Step 8, the counters (L127-L143).** Run on every bar, the signal bar included:
- if active = 1 and high > TP: tp1s += 1 (active is not reset here);
- if active1 = 1 and high > TP1: tp2s += 1, active1 = 0;
- if active2 = 1 and high > TP2: tp3s += 1, active2 = 0;
- the mirrors with low < TP, TP1, TP2 for −1.

**Step 9, the end of the script's position (L147-L148).**
- active = 0 when (active = 1 and (high > TP or low < SL)) or (active = −1 and (low < TP or high > SL)), unless this
  bar is a signal bar whose previous bar was not one (trigger = 1 and trigger[t−1] = 0).
- So on an ordinary signal bar the position survives its own bar. On a signal bar right after another signal bar it
  can end on that same bar.
- On bar 0, trigger[t−1] is na and the exception does not apply (irrelevant: no signal can exist before bar 50).
- active1 and active2 are **not** reset by the stop. They stay armed until hit or until the next signal.

**Step 10, display (L150-L171).** The target lines are stretched while active and dropped from their arrays
otherwise (the objects stay on the chart). The bar colour is grey for active = 0, bull for 1, bear for −1. Signal
shapes are drawn below or above bar t on highBroken / lowBroken.

**Step 11, the table (L179-L285, last bar only).** Three "win rates" are shown under shifted names:
- "TP1 Win Rate" = tp3s / total (the one-ninth level);
- "TP2" = tp2s / total (two ninths);
- "TP3" = tp1s / total (the far level);
- each × 100, formatted with up to two decimals, or "No Trades".

## 4. Outputs and when each is known

| Output | Lines | Known at | Repaint / look-ahead |
|---|---|---|---|
| Bullish / Bearish Signal shapes | L170-L171 | close of the breaking bar t | none after the close. The level was confirmed at least one bar earlier: a swing is confirmed 25 bars after it, and no break can happen on its own confirmation bar |
| `alertcondition` "Bullish Signal" / "Bearish Signal" | L289-L290 | per the user's alert frequency; final at the close | an alert set to fire intrabar can fire on a bar that closes back inside |
| `alert()` "Bullish / Bearish Breakout Detected" | L66, L72 | **intrabar**, once per bar, on the first tick the condition holds in real time | can fire for a break that is gone at the close. The `var` flags are rolled back between ticks, so the level itself is not consumed by an intrabar break |
| BOS / CHoCH line | L64, L70 | drawn at the break, from the swing bar to the break bar | **drawn back in time** (from the swing bar); visual only |
| BOS / CHoCH label | L65, L71 | drawn at the break, at the midpoint bar | **back in time**; visual only |
| TP lines and fill | L107-L110, L122-L125 | drawn at the break, starting at the swing bar | back in time; visual only |
| Bar colour (the position state) | L168 | close of each bar | the hits are evaluated on the bar's high and low, the signal bar included (steps 8-9) |
| Stats table | L179-L285 | last bar | **biased**: see trap 9 |

Pivots themselves are plotted nowhere. The 25-bar confirmation delay is the "signals come late" the video describes.

## 5. Repaint and look-ahead audit

- No `request.security`, no lookahead, no machine learning.
- Pivots are used only from their confirmation bar on: no future bar enters a signal.
- Labels and lines are placed back in time, but only at the moment of the break. A chart viewer may think the level
  was known at the swing bar; it was known 25 bars later.
- The script's own stats use the signal bar's high and low, which happen before the close that creates the signal.
  They are look-ahead flawed (trap 9). Signals are not affected.

## 6. Data needed

- OHLC: highs and lows for the swings and the range; closes for the break (highs and lows in 'Wicks' mode). Open is
  not used.
- No volume, no higher timeframe, no session, no tick size.
- History: 51 bars before the first swing can be confirmed (bar 50). The data start decides which swings exist at
  first, so start at the data start and let a few swings pass before any window.
- On TradingView a level that stays unbroken for very long makes the dynamic `ta.highest` reach far back. That may
  exceed the automatic history buffer and stop the script with a runtime error on some charts. A port has no such
  limit. Signals do not depend on it; only the levels do.

## 7. How a rule could trade it

**What the script implies (steps 7-9):**
- At a bullish break, long. The stop is the level minus a third of the swing-to-break range; the targets are the
  level plus 1/9, 2/9 and 3/9 of the range. The position ends at the far target or the stop, checked from the next
  bar. An opposite break flips it; a same-side break resets the levels.
- Because the levels hang on the broken level and not on the close, the nearer targets are often already behind a
  close that broke far through the level. Under the study's absolute-level rules (study 2's PREREG section 4), such an
  entry would be dropped or exit at once.

**The video's protocol (the same for all six indicators):**
- the 4H chart and the defaults (time horizon 25, candle close);
- a signal on a closed candle, the entry at the next open, long and short;
- a stop 2 ATR away (1R), no target;
- the exit at the opposite signal or the stop.
- "Take every signal"; the script's targets were ignored.
- Filter tried: ADX above 20 on the signal candle.

**Rules a pre-registration could list (our readings, nothing tested):**
- SMB-LS (event rule): the video's protocol.
  - A same-side signal while in a trade is ignored (one position). After a stop, the next signal of either side can
    enter (unlike PMax, two bullish signals in a row are common).
  - The plan must name the ATR: ATR(14) as in the earlier studies, since the script has none.
- SMB-LO: longs only; a bearish signal closes the long.
- SMB-X (the script's levels as absolute stop and target): stop at SL, all out at TP (the far level), or a split at
  TP1 / TP2. Entries whose fill is already at or beyond a level follow the study's absolute-level rules.
- Filters:
  - ADX(14) at the signal bar against 20 (`ADX20` in `infra.md`). The video says "above", so strict, but study 2's
    coil grade used >= 20; the plan must pick one. It uses study 2's verified `ta.dmi` port
    (`backtesting/research/tradeiq2_ind_coil.py`).
  - The earlier studies' MA200 filters F1 / F2, and the MSD bias FS.
- Timeframes: 4H is the video's. 1H (25 hours of delay) and 1D (25 days) change the character completely; list them
  only as sensitivity rows.

## 8. Traps for a port

| # | Item (lines) | Reading for both ports | The alternative | How much it matters |
|---|---|---|---|---|
| 1 | Pivot ties (L13-L14) | Strict on both sides (the repository's reading in studies 2-3) | An equal value allowed on the left or on the right side (undocumented by TradingView; `ties="left"` / `"right"` of the wyckoff helper) | With 25 / 25, an equal high among 50 neighbours is rare. Measure the changed signals under both alternatives during the reconciliation, as study 2 did |
| 2 | The confirmation delay | The swing of bar t − 25 exists from bar t on; its index is t − 25 | Placing the level at the swing bar (look-ahead) | All signals |
| 3 | Update before the test (L26-L55) | A new swing replaces the level first, then the break is tested, so a break of the old level on that bar is lost | Testing first | H2 |
| 4 | Replacement (L33, L43) | A newer swing replaces an unbroken older one and re-arms the side, even if it is lower (for highs) | Keeping the highest, or only unbroken ones | All signals |
| 5 | One break per level (L50-L55) | After a break the side is disarmed until the next swing | Re-arming on a pull-back | All signals |
| 6 | Strict break (L50, L53) | close > level (bull), close < level (bear); an equal close does not break | >= | Rare, but tested in H2 (bar 7) |
| 7 | The range window (L76-L77) | x = t − swing index; window t − x + 1 .. t, so the swing bar is excluded; one-argument `ta.highest` / `ta.lowest` read high / low | Including the swing bar, or using closes | Levels only |
| 8 | Level arithmetic (L103-L106, L118-L121) | dist = v / 3; the levels are level ± dist, level ± (dist·2)/3, level ± (dist·1)/3, and the stop level ∓ dist / 1, in this order | dist·(2/3) differs in the last bit | Bit-for-bit only |
| 9 | The stats (L127-L148, L191-L193) | Port them literally if the table's numbers are to be checked against the video: the signal bar's own high or low counts (it precedes the close that made the signal), tp1s can count twice for one signal, and active1 / active2 survive the stop | Treating the table as trade win rates | The table's rates are biased up. Not a trade result |
| 10 | The position's end (L147) | Not tested on a signal bar that follows a non-signal bar; tested on a signal bar that follows a signal bar | Always skipping the signal bar | The script's own position model only |
| 11 | Both breaks on one bar ('Wicks' only) | The bull block runs, then the bear block overrides active, the levels, length and the direction; total += 2 | | Non-default mode only |
| 12 | CHoCH (L65, L71) | Text only: CHoCH when the previous break was of the other side; the first break is BOS (prevBreakoutDir starts at 0) | Using CHoCH as a separate signal | None for the signals |
| 13 | `alert()` frequency (L66, L72) | Intrabar in real time; irrelevant on history | | Live use only |
| 14 | HH / LH and prevSwing (L27-L42) | Computed but unused; equal swings count as HH / HL here (the opposite of the Market Structure Dashboard's convention, where equal counts as lower) | Copying the dashboard's convention | None for the signals |
| 15 | Data start | The first swings depend on where the data start | | First weeks only |

## 9. Hand-checkable test cases

Make `swingSize` a parameter so these run with L = 2 (verified on 28 Nov 2026 with a scratch check of the formulas
above; no market data).

**H1, a break and its levels** (L = 2; columns high, low, close):

| t | high | low | close | What happens |
|---|---|---|---|---|
| 0 | 10 | 9 | 9.5 | |
| 1 | 11 | 10 | 10.5 | |
| 2 | 13 | 11 | 12 | the future swing high |
| 3 | 12 | 10.5 | 11 | |
| 4 | 11.5 | 10 | 10.2 | swing high 13 (bar 2) confirmed: level 13, armed |
| 5 | 12.5 | 10.1 | 12.4 | 12.4 is not above 13 |
| 6 | 13.5 | 12 | 13.2 | swing low 10 (bar 4) confirmed first; then **bullish signal** (13.2 > 13) |

- At bar 6: x = 6 − 2 = 4, so the window is bars 3-6: highest high 13.5, lowest low 10, v = 3.5, dist = 3.5 / 3.
- The levels: TP = 14.166666666666666, TP1 = 13.777777777777779, TP2 = 13.38888888888889, SL = 11.833333333333334.
- The counters: the signal bar's own high (13.5) is above TP2, so tp3s = 1 already on the signal bar (trap 9).
- The position is kept on bar 6 (trap 10).

**H2, a swallowed break and a strict tie** (L = 2):

| t | high | low | close | What happens |
|---|---|---|---|---|
| 0 | 8 | 7 | 7.5 | |
| 1 | 9 | 8 | 8.5 | |
| 2 | 10 | 8.5 | 9 | the future swing high |
| 3 | 9.5 | 8 | 8.2 | |
| 4 | 9.2 | 7.8 | 8.0 | swing high 10 (bar 2) confirmed: level 10 |
| 5 | 9.8 | 8.1 | 9.5 | |
| 6 | 12 | 9 | 9.9 | a wick above 10, close below: no break; swing low 7.8 (bar 4) confirmed |
| 7 | 11.5 | 9.5 | 10.0 | close equals 10: no break (trap 6) |
| 8 | 11.8 | 10.2 | 11.0 | swing high 12 (bar 6) confirmed first, so 11.0 > 12 is false: **no signal**. Testing first would signal |

**Other tests each port should carry:**
- H3: pivot ties. Equal highs inside the 2L + 1 window give no swing (strict); measure the alternatives.
- H4: replacement. A lower swing high replaces an unbroken higher one; a later close between the two breaks the new
  level only.
- H5: consecutive signal bars. Two bullish breaks on adjacent bars (possible after a fresh swing): the second bar's
  position end is tested on that bar (trap 10).
- H6: 'Wicks' mode. An outside bar through both armed levels gives both signals, and the bearish state wins.

## 10. Porting effort

- **Signals:** L12-L58 (swings, levels, flags, breaks): about 35 lines.
- **Levels and the script's position:** L60-L148 without the drawing calls: about 40 lines more.
- **Display only:** L150-L171, L179-L285 (except the three ratios at L191-L193).
- **Estimate:** about half a day per port with the strict pivot helper (`tradeiq2_ind_wyckoff.pivots`). The dynamic
  `highest` / `lowest` is a plain scan. Reconciliation is quick: every decimal is a copied price or one of the
  operations of trap 8.

## 11. What the video says about it (paraphrased, for a later claims list)

- Ranked second of six; published January 2025.
- Per trade about 4.4 times the SuperTrend baseline: 965 trades on the 11 markets (4H, January 2021 to October 2026),
  profit factor 1.58, about 7R a year per market from about one trade a month, 5.3 with costs doubled.
- Win rate 20%; the average winner more than six times the average loser.
- By market: gold 2.8, and strong on coins. The worst of the six on GBPUSD and the stock indexes. Its longest losing
  streak was 26 trades (BNB, a full year).
- Recommended use: coins and gold only, 4H, the default horizon of 25, every signal, small risk. ADX above 20 took the
  profit factor to 1.65.
- The video notes the four-day confirmation delay on 4H.
