# Hull Suite (InSilico): porting spec for study 4

Written 28 Nov 2026, before any port, rule or backtest of study 4 exists. No market data was loaded to write it.
It is meant for two engineers who will port the script independently and reconcile the two ports bit for bit, as in
studies 1 and 2.

- **Source.** `/Users/sidharthsingh/Desktop/study/trend/hull_suite.rtf` (9,420 bytes). It is read-only third-party
  code. Do not copy it into the repository. This spec describes it in words and formulas only.
- **Line numbers.** L1-L36 are the lines of `textutil -convert txt -stdout` on that file (36 lines, 1,457
  characters).
- **The video.** The transcript of TradeIQ video 3 never names the Hull Suite or a Hull average. There is no video
  usage to follow and no video number to check. The file's timestamp (11:28) is ten hours before the video's other
  files.

## 0. The bottom line: the owner's copy is truncated

**The evidence:**
- The RTF itself ends right after L35, the line that computes the Hull average (`_hull`), and a blank line. It is not
  a conversion problem: the raw file's last control words close the document there.
- 7 of the 11 inputs are never read in the copy:
  - the higher-timeframe switch and its timeframe (L11-L12);
  - the colour switch (L14);
  - the candle-colour switch (L15);
  - the band switch (L16);
  - the line thickness (L17);
  - the band transparency (L18).
- The copy has no plot, no fill, no colour, no alert and no `barcolor`. Pine refuses to compile a script without an
  output call. So this copy cannot be the script the owner sees on TradingView.

**What is missing.** Everything after L35: the higher-timeframe request, the trend reading, the plots and the alerts.
Section 5 describes them from the widely published "Hull Suite by InSilico" script. That part is a recollection, not
something read from the owner's file.

**What to do before porting:**
- ask the owner for a complete export of the script, or copy it again from TradingView;
- check this spec's section 5 against it;
- record the difference, if any, in study 4's DEVIATIONS.

The computation in the copy (sections 2-4) is complete and portable as it stands.

**Size and character:**
- At the defaults the line is a plain Hull moving average of the close, HMA(55) = WMA(2 x WMA(close, 27) -
  WMA(close, 55), 7). It first exists on bar 60.
- It uses no volume, no session and, at the defaults, no other timeframe. Nothing repaints at the defaults.
- It is a tiny port: 6 computing statements in the copy, about 6 more in the missing tail.

## 1. Identity

| Item | Value |
|---|---|
| Name | "Hull Suite by InSilico" (L3) |
| Author | InSilico (L2: a basic Hull pack "tinkered by" InSilico) |
| Licence | no licence line in the copy. The public script is open source on TradingView |
| Pine version | 4 (L1) |
| Declaration (L3) | `study` (v4's name for an indicator), overlay on price |
| Structure | four user functions (L22, L24, L26, L29-L32); no `var`, no loops, no arrays; one `security` call in the missing tail (section 5) |

## 2. Inputs (every one, with its default)

| Line | Variable | Title (short) | Type | Default | Read in the copy? |
|---|---|---|---|---|---|
| L6 | `src` | "Source" | source | close | yes (L35) |
| L7 | `modeSwitch` | "Hull Variation" | string: Hma, Thma, Ehma | "Hma" | yes (L30-L32) |
| L8 | `length` | the length (its title says 180-200 for floating support and resistance, 55 for swing entries) | int | 55 | yes (L35) |
| L9 | `lengthMult` | "Length multiplier" (its title: for viewing higher timeframes with a straight band) | float | 1.0 | yes (L35) |
| L11 | `useHtf` | show the Hull of another timeframe (its title: good for scalping) | bool | false | no (tail) |
| L12 | `htf` | "Higher timeframe" | resolution | "240" (4 hours) | no (tail) |
| L14 | `switchColor` | colour the Hull by its trend | bool | true | no (tail) |
| L15 | `candleCol` | colour the candles by the Hull's trend | bool | false | no (tail) |
| L16 | `visualSwitch` | "Show as a Band?" | bool | true | no (tail) |
| L17 | `thicknesSwitch` | "Line Thickness" | int | 1 | no (tail) |
| L18 | `transpSwitch` | "Band Transparency" | int, step 5 | 40 | no (tail) |

- No input has a minimum or a maximum.
- The mode strings are case-sensitive. A value other than the three options gives na (L32), which cannot happen from
  the settings dialog.

## 3. Conventions used in this spec

- **Bars.** Bar t = 0 is the first bar given to the port. `x[k]` at bar t is x at bar t - k, and it is na when
  t - k < 0. Values are IEEE doubles.
- **na rules.** Arithmetic with na gives na; a comparison with na is false.
- **Pine v4 integers:**
  - `int(x)` truncates toward zero;
  - `round(x)` rounds to the nearest integer, ties up, and returns an int;
  - the quotient of two ints is read as the truncated int (trap 2).
- **`wma(x, k)`**, by TradingView's reference code (`pine_wma`), as the house `tradeiq_ind.wma` implements it:
  - norm = 0 and s = 0;
  - for i = 0 (this bar) to k - 1: the weight is (k - i) x k, norm = norm + weight, and s = s + x[t-i] x weight;
  - the result is s / norm;
  - it is na if any of the k values is na.
- **`ema(x, k)`**: alpha = 2 / (k + 1), then alpha x value + (1 - alpha) x previous. It is seeded by the house reading,
  the first value (study 1 PREREG 5). It is used only in the Ehma mode.

## 4. The computation in the copy, on each bar

**Step 1: the working length (L35).**
- len = int(length x lengthMult), the double product truncated toward zero. At the defaults, 55 x 1.0 = 55.
- Examples: 55 x 1.1 = 60.50000000000001 gives 60, and 55 x 0.7 = 38.5 gives 38.

**Step 2: the mode switch (L29-L32), tested in this order:**
1. "Hma": HMA(src, len).
2. "Ehma": EHMA(src, len).
3. "Thma": THMA(src, len / 2). Note the half: at the defaults THMA receives 27, not 55.
4. Anything else: na.

The condition is a constant input, so only the chosen branch runs, and it runs on every bar. A port may compute only
that mode.

**Step 3: HMA(x, n) (L22), the default mode.**
- h = n / 2 (integer: 27 at 55) and q = round(sqrt(n)) (7 at 55, since sqrt(55) = 7.416).
- raw = 2 x WMA(x, h) - WMA(x, n): the doubling first, then the subtraction.
- HMA = WMA(raw, q).
- First values:
  - WMA(x, 27) on bar 26;
  - WMA(x, 55) on bar 54, so raw on bar 54;
  - **HMA on bar 60.**
- At n = 55 this equals the house `tradeiq_ind.hma(close, 55)`: the same lengths 27, 55 and 7, and the same WMA
  arithmetic. For other lengths the house helper is NOT this function (trap 3).
- **A ramp check** (scratch, synthetic): on x_t = t, HMA(55) lags the ramp by exactly 4/3 bar.
  - With n = 190 the lag is 4.0 under this script's rounding (q = 14) and 3.667 under `ta.hma`'s floor (q = 13).

**Step 4: EHMA(x, n) (L24), the Ehma mode.**
- EMA(2 x EMA(x, n / 2) - EMA(x, n), round(sqrt(n))): EMA lengths 27, 55 and 7 at the defaults.
- With the first-value seed every EMA exists from bar 0. With an SMA seed the line would first exist on bar 60.

**Step 5: THMA(x, m) (L26), the Thma mode, called with m = len / 2 (27).**
- WMA(3 x WMA(x, m / 3) - WMA(x, m / 2) - WMA(x, m), m).
  - The inner WMA lengths are 9, 13 and 27, and the outer one is 27.
  - The arithmetic order is ((WMA9 x 3) - WMA13) - WMA27, the multiplication by 3 written after the WMA.
- First value: bar 26 + 26 = 52.

**Step 6: the output of the copy (L35).**
- `_hull` is the chosen line.
- The copy ends here. Nothing is plotted or alerted.

## 5. The missing tail: what the public script does after L35

**This section is not from the owner's copy.** It is described from the published "Hull Suite by InSilico" (Pine v4).
Every item must be confirmed against a complete copy before a port relies on it.

**(a) The series.**
- HULL = `_hull` on the chart's timeframe.
- If `useHtf` is on, HULL is instead the value of `_hull` requested from the same ticker at the `htf` resolution,
  with v4's `security` defaults: gaps off, look-ahead off.
- The request names the ticker without its exchange prefix (`syminfo.ticker`).

**(b) The two lines.** MHULL = HULL, and SHULL = HULL two bars back. The band is drawn between them.

**(c) The trend colour.**
- With `switchColor`: green when HULL > HULL two bars back, otherwise red. A tie or an na gives red.
- Without it: orange.

**(d) The plots.**
- The MHULL line.
- The SHULL line, only with `visualSwitch`.
- A fill between them in the trend colour, with transparency `transpSwitch` (40).
- The line width is `thicknesSwitch`.

**(e) The two alerts.**
- "Hull trending up": MHULL crosses over SHULL. That is HULL[t] > HULL[t-2] and HULL[t-1] <= HULL[t-3].
- "Hull trending down": SHULL crosses over MHULL. That is HULL[t] < HULL[t-2] and HULL[t-1] >= HULL[t-3].
- On the chart's timeframe, the first possible alert is on bar 63.

**(f) Candle colours.** With `candleCol` (off by default), the candles take the trend colour.

**Expected outputs** (to confirm):
- the trend state (+1 green, -1 red), from bar 62;
- the up alert and the down alert;
- the two lines.

## 6. Outputs, and when each is known

| Output | Lines | Known |
|---|---|---|
| `_hull` (the Hull line), in the copy | L35 | at the close of t (from bar 60 at the defaults) |
| Trend colour, MHULL, SHULL, band (tail) | section 5 (b)-(d) | at the close of t |
| "Hull trending up / down" alerts (tail) | section 5 (e) | at the close of t |
| With `useHtf` (tail, off by default) | section 5 (a) | historical bars: the value of the last closed 4H bar. Live bars: the 4H bar still forming |

## 7. Repaint and look-ahead audit

- **At the defaults: none.** It is a pure WMA chain of the close. It has no pivots, no labels, no `var`, no arrays
  and no look-ahead.
- **With `useHtf` (tail, off by default):**
  - **The request.** It uses `security` without look-ahead and without the `[1]` idiom.
    - On historical bars each 4H value appears on the 1H bar that closes the 4H bar. Before that, the chart shows the
      previous 4H bar's value. So there is no future leak in history.
    - On live bars the value follows the 4H bar still forming. A chart watched live differs from the same chart
      reloaded: the classic `security` repaint.
    - A backtest should use the last closed 4H bar, as the house `tradeiq_market.htf_at` does.
  - **The ticker.** `syminfo.ticker` drops the exchange prefix. TradingView can then serve another feed's bars for
    the same ticker name.
  - **The two-bar comparison.** HULL two bars back counts CHART bars. Gaps are off, so the 4H value is constant over
    the four 1H bars of a 4H period. The test "HULL > HULL two bars back" is then true only on the first two 1H bars
    after each 4H step up.
    - So the colour flickers, red on half of the bars even in a steady rise.
    - The "trending up" alert fires on every 4H step up, not on trend changes.
    - The higher-timeframe mode is therefore not a trend reading. Use a 4H HMA computed on 4H bars instead.

## 8. Data it needs

- **Prices.** The close of the signal timeframe (`src` defaults to the close): the bid, on UTC bars, as in study 2.
- **Higher timeframe.** Only with `useHtf`: 4H bars of the same symbol.
- **Not needed:** volume, session, time of day.

## 9. How a rule could trade it

**This is provisional until the tail is confirmed.**

**What the script suggests:**
- the trend colour as the trend;
- the two alerts as trend changes;
- length 55 "for swing entry", and 180-200 as floating support and resistance;
- the higher-timeframe option for scalping.

**The video's common test** (chapter 5, and chapter 15's advice), applied for comparability:
- a signal on a closed candle;
- entry at the next open, long and short;
- a stop 2 ATR away, which is 1R;
- no target;
- exit on the opposite signal or the stop;
- the 4H chart, default settings.

Candidate rows:

| Row | Entry | Exit | Notes |
|---|---|---|---|
| HULL-S (main) | "trending up" / "trending down" at the close of t; fill at the next M1 open | the opposite alert (stop and reverse) or the stop at 2 x `ta.atr(14)` | event rule: after a stop, wait for the next alert. The alerts alternate as long as HULL never exactly equals HULL two bars back; after such a tie, two alerts of one side can follow each other (trap 9). A same-side alert while already in that side is ignored |
| HULL-C | the colour state: long while green, short while red | the colour change | a sensitivity row. It differs from HULL-S only around exact ties and in the stop handling |
| HULL-F | another rule's entry, only on the side of the close against HMA(200) (the "floating S/R" length) | the other rule's | a trend filter for the other study-4 scripts. It should be pre-registered as a combination, not as a Hull rule |
| Filters | EMA200 (video) or the house F1 (SMA200: register which); ADX(14) > 20 at the signal bar (study 2's `porting/coil.md` item 16); a daily-chart filter; long only | | the video's general advice |

- **Timeframes:** 4H first, then 1H and 1D.
- **Modes:** Hma (the default) first. Thma and Ehma only as sensitivity rows, if at all.
- **Expect many flips.** A 55-bar HMA turns often. The video's cost lesson (chapter 9: frequent signals lose more of
  their profit to costs) applies.

## 10. Traps for a port (the readings to register)

| # | Item (lines) | Reading | Evidence | The alternative, and its effect |
|---|---|---|---|---|
| 1 | **The truncated copy** | port L1-L35 as written. Sections 5 and 7 (tail) are only provisional | section 0 | porting a remembered tail without checking it: the signal definitions may differ |
| 2 | Integer halves and thirds (L22, L24, L26, L32) | n / 2, m / 3, m / 2 and len / 2 are truncated ints: 27 (n = 55), 9, 13 and 27 | Pine v4 types the quotient of two ints as an int, and the built-in `wma` / `ema` take integer lengths. Either way the length used is the truncated quotient. TradingView's own `ta.hma` uses the floored half (study 1 DEVIATIONS 12) | a fractional 27.5 has no known mechanism. One value from TradingView's Data Window (HMA(55) on a known bar) would settle it. Not checkable here |
| 3 | `round(sqrt(n))` (L22, L24) | rounded, ties up: 7 at 55 | Pine v4 `round` | the floor used by `ta.hma` and the house `hma`: equal at 55, 180 and 200, but different for n = 57-63, 73-80, 91-99, ..., 183-195, 211-224. Inside the title's 180-200 range, 183-195 differ (the ramp lag is 4.0 against 3.667 at 190) |
| 4 | `int(length x lengthMult)` (L35) | the double product, truncated | Pine `int` | rounding instead: 61 instead of 60 for 55 x 1.1 |
| 5 | WMA arithmetic | `pine_wma`: weights (k - i) x k, accumulated from this bar back, one division at the end | the reference; house `wma` (verified in study 1 against TradingView's printed values) | the textbook weights (k - i) / (k(k+1)/2), or a convolution: last-bit differences, which can flip an exact tie of HULL against HULL two bars back |
| 6 | THMA's length (L32) | THMA receives len / 2 = 27 | as written | passing 55: another line |
| 7 | EMA seed (L24) | the first value (house) | study 1 PREREG 5 | the SMA seed: different values until about 60-100 bars, in the Ehma mode only |
| 8 | Branches in the switch (L29-L32) | only the chosen function runs, on every bar | Pine branch evaluation; a constant input | none |
| 9 | Ties: the colour against the alerts (tail) | the colour is a strict ">" (a tie gives red). The alerts are crossovers: strict now, non-strict on the previous bar | section 5 (c), (e) | around an exact tie (HULL == HULL two bars back) the colour can turn red one bar before the down alert, or the down alert can fire with no colour change. A port must say which of the two a rule reads |
| 10 | The higher timeframe (tail) | not used by the rules. If it is used, take the last closed 4H bar and compare 4H bars with 4H bars | section 7 | TradingView's literal chart-bar comparison: flicker, and an alert on every 4H step |
| 11 | Not used here | no `ta.supertrend` (no direction sign), no `ta.atr`, no pivots, no volume | read L1-L36 | none |

## 11. The shared contract for the two ports, and the hand tests

**Each port returns, per bar:**
- len;
- WMA(close, 27), WMA(close, 55), raw, HMA (and, if a mode row exists, EHMA and THMA with their parts);
- after the tail is confirmed: HULL, SHULL, the trend state, and the up and down alerts.

All must agree bit for bit on the study's 1H / 4H / 1D gold and BTC bars.

**Hand tests:**
1. **Ramp:** HMA(55) of x_t = t is t - 4/3 from bar 60 (to rounding).
2. **Length readings at 190:** a ramp lag of 4.0 (q = 14); the floor version gives 3.667. The test must catch a floor.
3. **Warm-up:** WMA27 from bar 26, WMA55 from 54, HMA from 60; THMA(27) from 52.
4. **`int(55 x 1.1)` = 60.**
5. **Tie case (tail):** a flat stretch where HULL equals HULL two bars back. The colour is red, and the down alert
   fires only on the first strict fall.

**Sharpness check.** Rerun with these deliberate breaks:
- a rounded half (28);
- the floored root;
- textbook WMA weights;
- THMA with 55.

## 12. Porting effort

- **Lines that compute.**
  - In the copy: L22, L24, L26, L29-L32 and L35, which is 6 statements plus 4 inputs read.
  - In the tail: about 6 more (HULL, MHULL, SHULL, the colour, two alerts).
- **A port.** About 40-60 lines of Python.
  - The house `tradeiq_ind.wma` and `ema` can be reused.
  - The house `hma` is exact at 55 but must not be used for other lengths (trap 3).
- **Time.** Under an hour per port once a complete copy exists. The reconciliation is trivial.
- **Blocked** on the truncated copy, for everything after L35.
