# AlphaTrend (KivancOzbilgic): porting spec for study 4

Written 28 Nov 2026, before any port, rule or backtest of study 4 exists. No market data was loaded to write it.
It is meant for two engineers who will port the script independently and then reconcile the two ports bit for bit,
as studies 1 and 2 did (`backtest_results/tradeiq_rsi/PORTING.md`, `backtest_results/tradeiq_2027/porting/*.md`).

- **Source.** `/Users/sidharthsingh/Desktop/study/trend/AlphaTrend Indicator.rtf` (16,347 bytes). It is read-only
  third-party code (MPL-2.0). Do not copy it into the repository. This spec describes it in words and formulas only.
- **Line numbers.** L1-L56 are the lines of `textutil -convert txt -stdout` on that file (56 lines, 3,002
  characters).
  - The conversion loses nothing. The RTF's only hidden group is its colour table, and the file ends after L51's
    alert and some blank lines.
- **Status.** The copy is complete. It declares its plots, labels and ten alerts, and nothing is cut off.
- **The video.** The transcript of TradeIQ video 3 (`Supertrend Trading Analysis.rtf`) never names AlphaTrend.
  - So there is no video usage to follow and no video number to check.
  - The video says it ran "51 other" indicators (chapter 1) without naming them. Whether AlphaTrend was one of them is
    unknown.
  - The file's timestamp (11:32) is ten hours before the video's other files (21:55-22:00).
- **Synthetic checks.** The timing claims of sections 4 and 9 were checked in scratch, on synthetic random walks and
  random signal sequences only:
  - the first valid bars;
  - the zero line;
  - the label filter's closed form (3,000 random sequences, 0 mismatches);
  - the Confirmed alarm's closed form (0 mismatches).

## 0. The bottom line

- **What it is.** AlphaTrend is a trailing line like a Supertrend band, but it switches side on a momentum test, not on
  a close through the line.
  - **The momentum test.** By default it is the 14-bar Money Flow Index of the typical price, at or above 50. With
    the "no volume data" switch it is the 14-bar RSI of the close instead.
  - **"Up" mode.** The line is the larger of `low - ATR` and its own previous value, so it can only rise.
  - **"Down" mode.** The line is the smaller of `high + ATR` and its previous value, so it can only fall.
  - **On a change of mode** it inherits the other mode's level (step 5).
  - **Its ATR is not Wilder's.** It is a 14-bar SIMPLE average of the true range.
- **Signals.** A signal is the line crossing its own value of two bars back. The BUY / SELL labels add an alternation
  filter built from `ta.barssince`.
- **Timing.** Everything is known at the bar's close. There is no `request.security`, no look-ahead, no pivot, no
  `var` state and no array. Nothing repaints on closed bars.
- **Data.** It needs volume by default. For BTC this repeats study 2's volume question (section 7).
- **Size.** About 12 statements compute the line and the labels, and about 10 more are alert conditions. It is a
  small port.
- **The traps that change numbers.** All are covered in section 9:
  - the simple-average ATR;
  - `ta.tr` has no value on bar 0;
  - `nz` turns a missing previous line into 0, so the line can sit at 0 at the start;
  - the label filter is not "the last signal was the other side";
  - the "Confirmed" alarm is not "the label, one bar later";
  - labels can repeat a side.

## 1. Identity

| Item | Value |
|---|---|
| Name | "AlphaTrend", short title "AT" (L5) |
| Author | KivancOzbilgic, author and developer (L2-L3) |
| Licence | Mozilla Public License 2.0 (L1) |
| Pine version | 5 (L4) |
| Declaration (L5) | `indicator`; overlay on price; price format with display precision 2; `timeframe` argument = empty string (the chart's timeframe) |
| Scope | A single global script: no functions, no loops, no `var`, no arrays, no drawings other than `plot`, `fill` and `plotshape` |

## 2. Inputs (every one, with its default)

| Line | Variable | Title (short) | Type | Default | Read by |
|---|---|---|---|---|---|
| L6 | `coeff` | "Multiplier" | float, step 0.1 | 1.0 | L12-L13 |
| L7 | `AP` | "Common Period" | int | 14 | L8 (SMA of TR), L15 (RSI or MFI length) |
| L9 | `src` | (no title) | source | close | L15, RSI branch only |
| L10 | `showsignalsk` | "Show Signals?" | bool | true | L32, L34 (labels only; the alerts ignore it) |
| L11 | `novolumedata` | "Change calculation (no volume data)?" | bool | false | L15: false selects MFI, true selects RSI |
| L5 | (declaration) | the "Timeframe" setting | timeframe | "" = chart | the whole script (section 6) |

- No input has a minimum or a maximum. Everything below assumes the defaults, `AP` >= 1 and `coeff` >= 0.
- `src` never reaches the MFI. The MFI always reads `hlc3`.

## 3. Conventions used in this spec

- **Bars.** Bar t = 0 is the first bar given to the port. `x[k]` at bar t is x at bar t - k, and it is na when
  t - k < 0. Values are IEEE doubles.
- **na rules (Pine):**
  - arithmetic with na gives na;
  - every comparison with na is false;
  - a ternary whose condition is na or false takes its else branch;
  - `nz(x)` is 0 when x is na;
  - `math.max` and `math.min` of na are na.
- **Arithmetic order.** It follows TradingView's "same on Pine" reference code, exactly as the house helpers in
  `backtesting/research/tradeiq_ind.py` do:
  - `ta.sma`: s = 0, then for i = 0 (this bar) to n - 1, s = s + x[t-i] / n;
  - `math.sum`: s = 0, then for i = 0 to n - 1, s = s + x[t-i].
  - Two ports must use this order, or a running sum, but the same one, to agree bit for bit. TradingView's own
    runtime order is unknown and may differ in the last bits.
- **Division.** Division is IEEE: x / 0 = +inf for x > 0, and 0 / 0 is na (NaN). This is the house reading (study 1's
  note on `pine_rsi`). See trap 9.

## 4. The computation on each bar, in order

**Step 1: the true range (L8, `ta.tr`).**
- TR[0] = na. The built-in variable `ta.tr` is `ta.tr(false)`, which has no value when the previous close is missing.
- For t >= 1: TR = max(high - low, abs(high - close[t-1]), abs(low - close[t-1])).
- This is NOT the bar-0 rule of `ta.atr`, which uses `ta.tr(true)` and gives high - low on bar 0. Trap 2.

**Step 2: the script's ATR (L8).**
- ATR_AT = SMA(TR, 14), in the pine_sma order of section 3.
- It is na while any of its 14 values is na. **First value: bar 14** (the TRs of bars 1-14).

**Step 3: the two candidate levels (L12-L13).**
- upT = low - (ATR_AT x coeff) and downT = high + (ATR_AT x coeff): the multiplication comes first.
- With coeff = 1.0 the product is exact.
- Both are na on bars 0-13.

**Step 4: the momentum switch (L15, the first ternary).** `up_mode` is true when:
- by default, MFI(hlc3, 14) >= 50;
- with `novolumedata`, RSI(src, 14) >= 50;
- either way, an na value makes `up_mode` false.

**The MFI** (TradingView's `pine_mfi` reference):
1. tp = hlc3 = (high + low + close) / 3, added left to right and then divided by 3.
2. dtp = tp - tp[1], which is na on bar 0.
3. The positive term is volume x (0 if dtp <= 0, else tp).
   - On bar 0, dtp is na, so the test is false and the term is volume x tp.
4. The negative term is volume x (0 if dtp >= 0, else tp).
   - On bar 0 this term is also volume x tp.
   - A bar with dtp = 0 adds to neither side.
5. upper and lower are the 14-bar `math.sum` of the two terms. **First value: bar 13.**
6. MFI = 100 - (100 / (1 + upper / lower)). In IEEE:
   - lower = 0 with upper > 0 gives 100;
   - upper = lower = 0 gives na, so `up_mode` is false;
   - upper = 0 gives 0.
   - MFI = 50 exactly (upper == lower) counts as up (`>=`).

**The RSI branch** (only with the switch):
- It is `ta.rsi(src, 14)`: the house `rsi()`, with Wilder averages seeded by an SMA. First value: bar 14.
- The house value is 100 when the average loss is 0, and 0 when the average gain is 0.

Only one of the two calls runs, on every bar, because the input never changes from bar to bar (trap 13).

**Step 5: the line (L14-L15).**
- L14 resets the variable to 0.0 on every bar. It is not `var`, so AT[t-1] is the value the previous bar ended with.
- Let p = AT[t-1], or 0 if that is na or t = 0 (`nz`).
- In up mode: AT = p if upT < p, else upT. When upT exists this is max(upT, p); a tie gives upT, the same number.
- In down mode: AT = p if downT > p, else downT, which is min(downT, p).
- The nested ternary is right-associative: (switch) ? (up choice) : (down choice).

What follows from this:
- **(a) AT is na on bars 0-13.** upT and downT are na there, so the tests are false and the na level is taken.
- **(b) The zero line.**
  - On bar 14, p = 0.
  - If bar 14 is in up mode, AT = upT.
  - If bar 14 is in down mode, AT = 0, because downT > 0 always. AT then stays exactly 0 until the first up-mode bar,
    where it jumps to upT.
  - This was checked in scratch: a falling synthetic walk with MFI[14] = 36.7 sat at 0 from bar 14 past bar 59.
- **(c) A ratchet with memory.**
  - In up mode the line can only rise or stay flat. In down mode it can only fall or stay flat.
  - On a change of mode the line keeps its old level until price clears it by one ATR_AT:
    - after a change to up mode, until low - ATR_AT > p;
    - after a change to down mode, until high + ATR_AT < p.
  - So the line can stay flat for a long time, at a level set long before.

**Step 6: the lagged line and the fill colour (L17, L19, L21). Display only.**
- The lagged line is AT2 = AT[t-2].
- The colour is green if AT > AT[2], and dark red if AT < AT[2].
- When neither holds (a tie, or an na): green if AT[1] > AT[3], otherwise dark red.
- As a state: +1 / -1.

**Step 7: raw signals (L23-L24).**
- buy = `ta.crossover(AT, AT[2])`: AT[t] > AT[t-2] and AT[t-1] <= AT[t-3].
- sell = `ta.crossunder(AT, AT[2])`: AT[t] < AT[t-2] and AT[t-1] >= AT[t-3].
- All four values must exist, so the **first possible signal is on bar 17**.
- A buy and a sell cannot happen on the same bar.
- A flat line (AT[t-1] == AT[t-3]) lets a second raw buy follow a first one with no sell in between.

**Step 8: the counters (L27-L30), with `ta.barssince`.**
- K1 = the number of bars since the latest raw buy (0 on a buy bar), and na if there has never been one. K2 is the
  same for sells.
- O1 = `ta.barssince(buy[1])`, which equals K1[t-1]. O2 equals K2[t-1].
- buy[1] on bar 0 counts as false.

**Step 9: the labels (L32, L34).**
- BUY on bar t = buy[t] and K1[t-1] > K2[t], and it is drawn only if `showsignalsk`. SELL mirrors it: sell[t] and
  K2[t-1] > K1[t].
- **The closed form.** Let v be the latest raw buy before t and w the latest raw sell up to t. Then:
  - BUY holds exactly when both exist and w >= v + 2.
  - Mirror for SELL.
- What follows:
  - The first raw buy and the first raw sell are never labelled, because their counters are na.
  - A raw buy repeated with no raw sell in between is not labelled.
  - **A raw sell one bar after the previous raw buy does not count.** So the next raw buy is not labelled, and the
    label stream can show SELL, SELL, or BUY, BUY. Example: raw B at bar 100, raw S at 101, raw B at 110, raw S at 120
    give the labels B(100), S(101), S(120), if 100 and 101 qualify.
- **Position (display).** BUY is drawn at AT[t-2] x 0.9999 and SELL at AT[t-2] x 1.0001, on bar t itself.

**Step 10: the alerts (L37-L51).** They are listed in section 5. Two of them need care.
- **Potential BUY / SELL (L37-L38)** are the label conditions without `showsignalsk`.
- **Confirmed BUY (L40)** on bar t is buy[t-1] and O1[t-1] > K2[t], that is buy[t-1] and K1[t-2] > K2[t].
  - It is not the label one bar later.
  - Let v be the latest raw buy before t-1 and w the latest raw sell up to t. It never fires if v does not exist
    (and, in the second case below, if w does not exist). Otherwise it fires exactly when either:
    - there is a raw sell on bar t itself and v < t - 2; or
    - there is no raw sell on bar t and w >= v + 3.
  - So on w = v + 2 the label shows but the Confirmed alarm stays silent.
  - Confirmed SELL (L41) mirrors it.

## 5. Outputs, and when each is known

| Output | Lines | Definition | Known |
|---|---|---|---|
| AlphaTrend line (blue, width 3) | L14-L15, L18 | AT[t] | at the close of t (first value bar 14) |
| Lagged line (red, width 3) | L19 | AT[t-2] | at the close of t |
| Fill colour | L17, L21 | +1 / -1 (step 6) | at the close of t; display |
| Raw buy / sell | L23-L24 | step 7 | at the close of t (from bar 17) |
| BUY / SELL labels | L32, L34 | step 9 | at the close of t; drawn on bar t, never moved back |
| "Potential BUY / SELL Alarm" | L37-L38 | the labels without the show switch | at the close of t (live: can fire intrabar) |
| "Confirmed BUY / SELL Alarm" | L40-L41 | step 10 | at the close of t + 1 |
| "Price Cross Alert" | L45 | `ta.cross(close, AT)`: (close > AT) differs from the previous bar's (close > AT) | at the close of t |
| "Candle CrossOver / CrossUnder Alarm" | L46-L47 | crossover(low, AT); crossunder(high, AT) | at the close of t |
| The three "After Bar Close" alerts | L49-L51 | the same three on the values of bars t-2 and t-1 | reported on bar t |

The house cross helpers (`tradeiq_ind.crossover / crossunder / cross`) define these crosses exactly, including na.

## 6. Repaint and look-ahead audit

- **`request.security`: none.**
  - The declaration's `timeframe` argument is the empty string, which means the chart's timeframe.
  - If a user picks another timeframe in the settings, TradingView runs the whole script on that timeframe. Its
    "wait for timeframe closes" default shows a value only when that timeframe's bar closes. Not used here.
- **Look-ahead: none.** There is no negative history index, no plot offset, and no `barstate` logic.
- **Pivots, machine learning, arrays, drawings moved back in time: none.** The labels are `plotshape` on the signal
  bar.
- **`ta.barssince`.** TradingView's manual warns that it can repaint. It does not on closed historical bars. On the
  live bar the counters, like everything else, are recomputed on every tick.
- **The live bar.** The line, the raw signals and the "Potential" alerts can appear and disappear before the close.
  That is why the script also has "Confirmed" alarms one bar later. A backtest on closed bars sees the final values.
- **Dependence on the data start.** This is not a repaint, but it matters for bit-for-bit work.
  - The line has path memory (step 5c), and the first labels depend on the first raw signals.
  - Two runs that start on different bars give the same line from the first bar on which the line ratchets past both
    runs' levels (an up-mode bar with upT above both, or a down-mode bar with downT below both). From then on they are
    identical.
  - The ports must start on the same first bar. The study should measure this merge bar for two starts, as study 2
    did for the ribbon's literal stop (its porting/ribbon.md item 13).

## 7. Data it needs

- **Prices.** The OHLC of the signal timeframe. The study's convention is the bid, on UTC bars, built as in study 2.
- **Volume** (default MFI branch):
  - **Gold:** Exness tick volume (the sum of the M1 tick counts), as in study 2.
  - **BTC:** Exness BTC tick volume is a near-constant heartbeat (study 2 PREREG section 2: about one tick a second,
    coefficient of variation 0.06).
    - With a near-constant volume, the MFI becomes roughly "the share of rising typical prices among the last 14
      bars", a count, not a volume-weighted flow.
    - Study 2 used Binance BTCUSDT spot volume for every rule that reads volume. Study 4 should do the same and keep
      Exness volume as a sensitivity row. It must register which.
  - **Bars with no Binance kline** (volume 0, study 1 DEVIATIONS 5) add nothing to either sum.
  - **On TradingView, a symbol without volume** gives an na MFI. `up_mode` is then always false and the line sits
    at 0. That is what the L11 switch is for.
- **The RSI branch** needs the close only.
- **Nothing else.** No higher timeframe, no session, no time of day.

## 8. How a rule could trade it

**What the script itself suggests:**
- the BUY / SELL labels as entries;
- "Confirmed" alarms for traders who wait one bar;
- the price and candle crosses of the line (L45-L51), usable as exits or confirmations;
- the line itself as a trailing level. In up mode it sits below price at a ratcheting low - ATR_AT.

**The video's common test** (transcript chapter 5, and chapter 15 "which one to pick"), applied for comparability:
- a signal on a closed candle;
- entry at the next open, long and short;
- a stop 2 ATR away, which is 1R;
- no target;
- exit on the opposite signal or the stop;
- the 4-hour chart, default settings.

The video's optional filters are:
- the 200 EMA (buys above, sells below);
- ADX above 20 on the signal candle;
- the daily chart.

Candidate rows, to be frozen in study 4's pre-registration:

| Row | Entry | Exit | Notes |
|---|---|---|---|
| AT-L (main) | BUY / SELL label at the close of t; fill at the next M1 open | the opposite label (stop and reverse), or the stop at 2 x `ta.atr(14)` (Wilder, the study's ATR, not the script's SMA ATR) | event rule: after a stop, wait for the next label. A label of the side already held is ignored. A label of either side opens a trade when flat |
| AT-C | the "Confirmed" alarm, one bar later (step 10) | as AT-L | measures the cost of waiting for confirmation |
| AT-X | as AT-L | the close crossing the line against the trade (L49's cross, acted on at the next open), or the stop | uses the line as a closing-basis trailing stop |
| AT-R | as AT-L, with the RSI switch (L11) | as AT-L | needs no volume; answers the BTC volume question |
| Filters | EMA200 (video) or the house F1 (SMA200: register which); ADX(14) > 20 at the signal bar, as study 2 defined ADX (`porting/coil.md` item 16); a daily trend filter; long only | | the video reports that long trades carried its winners |

Timeframes: 4H first, as the video tests; 1H and 1D as in studies 1 and 2.

**Decisions to register:**
- the BTC volume source;
- what a repeated same-side label does;
- the stop's ATR;
- EMA or SMA 200;
- whether AT-X acts on the close cross or on an intrabar touch of the line.

## 9. Traps for a port (the readings to register)

"Effect" says what the alternative would change. Counts on the study's bars must be measured by the ports, not
guessed.

| # | Item (lines) | Reading | Evidence | The alternative, and its effect |
|---|---|---|---|---|
| 1 | The ATR (L8) | SMA(14) of the true range | as written | Wilder's `ta.atr(14)`: a different line everywhere |
| 2 | True range on bar 0 (L8) | na (the `ta.tr` variable is `ta.tr(false)`) | Pine v5 reference for `ta.tr`; study 2 saw the same in the DMI script (`porting/coil.md` item 16) | high - low on bar 0 (the house `true_range`, which is `ta.tr(true)`): the first ATR moves to bar 13. The bar-14 zero-line state (5b) and every value up to the merge bar of section 6 can change. A port that reuses the house helper must set TR[0] to na |
| 3 | SMA order (L8) | pine_sma order (section 3) | the house's verified `sma` | a running sum: last-bit differences, which can flip an exact `upT < p` test only if the two values agree to the last bit |
| 4 | The switch (L15) | MFI >= 50, not strict | as written | `>`: changes only bars with upper == lower exactly |
| 5 | MFI source (L15) | the change of hlc3, not of the close. A zero change adds to neither sum | `pine_mfi` | the change of the close: other flows |
| 6 | MFI on bar 0 | both sums get volume x tp | `pine_mfi`: a comparison with na is false | none: it only touches MFI[13], and the line needs ATR_AT, which starts at bar 14 |
| 7 | hlc3 (L15) | (high + low + close) / 3, added left to right | Pine's definition of `hlc3` | another order: last bits |
| 8 | MFI sums | `math.sum`, added from this bar back | house `math_sum` | a running sum: last bits |
| 9 | MFI division by zero | IEEE: lower = 0 gives 100, 0 / 0 gives na (false) | house reading (study 1's RSI note) | Pine turning every x / 0 into na: such bars become down mode. Count the 14-bar windows with lower = 0 on the study's bars before freezing. They are expected to be rare on 1H and above (14 bars without one falling typical price) |
| 10 | `nz(AT[1])` (L15) | 0 before the first value. So there is a zero line while the start is in down mode | Pine `nz` | starting from the first upT or downT instead removes the zero line and changes the first raw signals |
| 11 | Ternary nesting (L15) | right-associative: switch ? (up choice) : (down choice) | Pine grammar | none if parsed correctly |
| 12 | Crosses (L23-L24, L45-L51) | crossover: > now and <= on the previous bar. crossunder: < and >=. cross: the side of > changes. All need non-na values | house helpers; the Pine reference | treating a tie on the previous bar differently changes signals after flat stretches, which are common (step 7) |
| 13 | RSI / MFI in a ternary (L15) | only the chosen call runs, on every bar (the input is constant) | Pine's warning about calls in branches | computing both is harmless |
| 14 | `ta.barssince` (L27-L30) | 0 on the event bar; na before the first event; event[1] on bar 0 is false. O1 = K1[t-1] and O2 = K2[t-1] | Pine v5 reference | counting from 1, or 0 before the first event: other labels near the start, and in every w = v + 1 case |
| 15 | The label filter (L32, L34) | the closed form of step 9 (w >= v + 2) | derived, and brute-forced in scratch | "the last raw signal was the other side" (w >= v + 1): it differs whenever a raw sell comes exactly one bar after a raw buy |
| 16 | The Confirmed alarm (L40-L41) | the closed form of step 10 | derived, and brute-forced in scratch | "the label one bar later": it differs on w = v + 2, and when a raw signal of the other side falls on bar t |
| 17 | Labels repeat a side | possible (step 9 example) | derived | a rule that assumes strict alternation would reverse twice, or never |
| 18 | Display precision (L5) | 2 decimals on screen only | `format.price`, precision 2 | when comparing with TradingView's Data Window, allow 0.005 |
| 19 | The data start | the first bar of the study's data | section 6 | another start changes values until the merge bar. Measure it |
| 20 | Volume | section 7 | study 2 PREREG 2 | Exness BTC tick volume: a count-like MFI and other signals (a sensitivity row) |
| 21 | Not used here | no `ta.supertrend` (no direction sign convention), no `ta.atr`, no pivots, no `request.security` | read L1-L56 | none |

## 10. The shared contract for the two ports, and the hand tests

**Each port returns, per bar** (float64 with NaN for na; booleans; ints with na as a sentinel):
- TR, ATR_AT, upT, downT;
- tp, upper, lower, MFI (and the RSI for AT-R);
- up_mode, AT, AT[t-2], the colour state;
- the raw buy and sell, K1, K2, O1, O2;
- BUY and SELL labels, Potential and Confirmed BUY / SELL;
- the six cross alerts.

All must agree bit for bit (floats compared with ==, NaN on the same bars) on every bar of the study's 1H / 4H / 1D
gold and BTC bars, with both volume sources for BTC.

**Hand tests each port must pass:**
1. **TR on bar 0:** na. ATR_AT first exists on bar 14.
2. **Zero line:** a falling path where MFI[14] < 50 gives AT = 0 from bar 14 until the first MFI >= 50 bar, then upT.
   - The jump is a raw buy, provided it is on bar 17 or later.
   - It is not labelled, because there is no earlier buy.
3. **Ratchet:** in up mode a lower upT leaves AT unchanged. After a change to down mode, AT keeps the old level while
   high + ATR_AT >= the level.
4. **Flat line:** AT flat for 2 bars, then rising, gives a second raw buy without a sell. It is not labelled.
5. **The w = v + 1 case:** raw B at 100, raw S at 101, raw B at 110. There is no BUY label at 110, and the next raw
   sell is labelled SELL again.
6. **The Confirmed alarm on w = v + 2:** the label shows, and Confirmed stays silent on the next bar.
7. **MFI with lower = 0:** a 14-bar window with no falling typical price gives 100. With zero volume in all 14 bars,
   the MFI is na and the bar is in down mode.
8. **MFI = 50 exactly** (equal flows) gives up mode.

**Sharpness check, as in study 2.** Rerun the reconciliation with these deliberate breaks:
- Wilder ATR;
- TR[0] = high - low;
- `>` instead of `>=` at 50;
- `nz` replaced by the first level;
- the w >= v + 1 filter;
- Confirmed as the label shifted by one bar.

Each must fail at least one test.

## 11. Porting effort

- **Lines that compute.**
  - About 12 statements for the line and the labels: L8, L12-L15, L23-L24, L27-L30, and the conditions of L32 and
    L34.
  - About 10 alert conditions: L37-L41 and L45-L51.
  - Plus 1 colour rule (L17).
- **A port.** About 80-120 lines of Python, plus an MFI helper (about 20 lines) and a bars-since helper (about 10).
  - The house `tradeiq_ind` already has `sma`, `rsi`, `math_sum` and the three crosses.
  - Its `true_range` is `ta.tr(true)`, so this port must blank bar 0.
  - Neither `ta.mfi` nor `ta.barssince` has a verified port yet. The study-4 infrastructure map (`infra.md` 4.3)
    puts them in `tradeiq3_ind_common.py`: port A imports them, and port B writes its own from the reference code.
    The RMI port shares the MFI.
- **Time.** A few hours per port, with tests. The reconciliation should be short, because the arithmetic is simple
  and the traps are listed.
- **Risk:** low. The open decisions are about data (the volume source) and rules (repeated labels), not about Pine.
