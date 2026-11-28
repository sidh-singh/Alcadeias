# RMI Trend Sniper (TZack88): porting spec for study 4

Written 28 Nov 2026, before any port, rule or backtest of study 4 exists. No market data was loaded to write it.
It is meant for two engineers who will port the script independently and reconcile the two ports bit for bit, as in
studies 1 and 2.

- **Source.** `/Users/sidharthsingh/Desktop/study/trend/RMI Trend Sniper Indicator.rtf` (4,020 bytes). It is
  read-only third-party code (MPL-2.0). Do not copy it into the repository. This spec describes it in words and
  formulas only.
- **Line numbers.** L1-L101 are the lines of `textutil -convert txt -stdout` on that file (101 lines, 3,528
  characters).
  - The conversion loses nothing. The RTF's only hidden group is its colour table, and the file ends with the second
    alert (L101).
- **Status.** The copy is complete: inputs, state, signals, the band, plots, labels and two alerts.
- **The video.** This is number five of TradeIQ video 3. Transcript chapter 7 ("5 RMI Trend Sniper [TZack88]") is on
  the plain-text lines 193-259 of `Supertrend Trading Analysis.rtf`. Section 8 lists the video's description, its
  advice and its numbers.
- **Synthetic checks.** The warm-up bars of section 4 were checked in scratch, on a synthetic random walk only:
  - RSI from bar 14;
  - ATR(30) from bar 29;
  - the band from bar 49;
  - the range average from bar 38.

## 0. The bottom line

- **The line it reads.** Despite the name, it reads no Relative Momentum Index. It averages the ordinary RSI(14) of the
  close (1-bar changes, Wilder averages) and the MFI(14) of the typical price.
- **The state.**
  - It turns **positive** on a bar where that average crosses above 66 (strictly, from strictly below) while the
    5-bar EMA of the close is rising.
  - It turns **negative** on any bar where the average is below 30 while the EMA is falling.
  - The state persists in two `var` booleans.
- **The signals** are the state changes: BUY when it turns positive, SELL when it turns negative.
  - After the first signal they strictly alternate.
  - The first signal can be of either side.
- **The band is display only.** It is a range-weighted average of the close, minus or plus a band of
  4 x min(0.3 ATR(30), 0.3% of the close) taken 20 bars back. Nothing in the signals reads it.
- **Timing.** Everything is known at the bar's close. There is no `request.security`, no look-ahead and no pivot.
  Labels sit on the signal bar. Nothing repaints on closed bars.
- **Data.** It needs volume (the MFI half), which repeats study 2's BTC volume question.
- **Size.** 9 statements drive the signals. A small port.

## 1. Identity

| Item | Value |
|---|---|
| Name | "RMI Trend Sniper" (L5) |
| Author | TZack88 (L2) |
| Licence | Mozilla Public License 2.0 (L1) |
| Pine version | 5 (L4) |
| Declaration (L5) | `indicator`; overlay on price; at most 500 labels kept on the chart |
| Structure | two `var` booleans (L8-L9); two user methods, `_Band` (L51-L52) and `rangeMA` (L58-L62), each called once per bar at global scope; no arrays, no loops, no `request.*` |

## 2. Inputs (every one, with its default) and the hard-coded constants

| Line | Variable | Title (short) | Type | Default | Read by |
|---|---|---|---|---|---|
| L13 | `Length` | "RMI Length" | int | 14 | the RSI's two Wilder averages (L21-L22) and the MFI length (L24) |
| L14 | `pmom` | "Positive above" | int | 66 | the BUY condition (L31-L32) |
| L15 | `nmom` | "Negative below" | int | 30 | the BUY condition (L33) and the SELL condition (L36) |
| L16 | `filleshow` | "Show Range MA" | bool | true | the band plots only (L73-L76, L84-L85) |
| L17 | `bull` | (colour) | colour | #00bcd4 | display |
| L18 | `bear` | (colour) | colour | #ff5252 | display |

- **Constants that are not inputs:**
  - the EMA length 5 (L34, L37);
  - in the band (L51-L55): ATR length 30, factor 0.3, 0.3% of the close, a 20-bar delay, and / 2 x 8;
  - the range-average length 20 (L66).
- The group strings (L10-L12) are labels. "Range Vales" (L11) is never used.
- No input has a minimum or a maximum.

## 3. Conventions used in this spec

- **Bars.** Bar t = 0 is the first bar given to the port. `x[k]` at bar t is x at bar t - k, and it is na when
  t - k < 0. Values are IEEE doubles.
- **na rules (Pine):**
  - arithmetic with na gives na;
  - a comparison with na is false;
  - `math.max` and `math.min` of na are na;
  - `math.avg` with an na is na.
- **Arithmetic order.** It follows TradingView's "same on Pine" reference code, as the house helpers in
  `backtesting/research/tradeiq_ind.py` do:
  - `ta.sma`: x[t-i] / n added from this bar back;
  - `math.sum`: added from this bar back;
  - Wilder `ta.rma` and `ta.ema`: alpha x value + (1 - alpha) x previous.
  - The two ports must share this order.
- **Division.** Division is IEEE: x / 0 = +inf for x > 0, and 0 / 0 is na.

## 4. The computation on each bar, in order

**Step 0: the state (L8-L9).**
- `positive` and `negative` are `var` booleans. Both are false before bar 0, and they keep their values from bar to
  bar.

**Step 1: the bar range (L19).** BarRange = high - low.

**Step 2: the RSI's averages (L21-L22).**
- dc = close - close[1], which is na on bar 0.
- up = RMA(max(dc, 0), 14) and down = RMA(-min(dc, 0), 14).
- RMA is Wilder's average (`ta.rma`):
  - na until 14 values exist;
  - seeded with their SMA. The values of bars 1-14 give the **first value on bar 14**;
  - then (1/14) x value + (1 - 1/14) x previous.
- -min(dc, 0) is -0.0 on a rising bar. That is harmless (trap 2).

**Step 3: the RSI (L23).**
- If down == 0, rsi = 100.
- Otherwise, if up == 0, rsi = 0.
- Otherwise, rsi = 100 - (100 / (1 + up / down)).
- While up and down are na, both tests are false and the formula gives na.
- This is exactly the house `tradeiq_ind.rsi(close, 14)`.

**Step 4: the MFI (L24).** `ta.mfi(hlc3, 14)`, by TradingView's `pine_mfi` reference:
1. tp = (high + low + close) / 3, added left to right.
2. dtp = tp - tp[1].
3. The positive term is volume x (0 if dtp <= 0, else tp). The negative term is volume x (0 if dtp >= 0, else tp).
   - On bar 0, dtp is na, so both terms are volume x tp.
   - A zero change adds to neither side.
4. upper and lower are the 14-bar `math.sum` of the two terms.
5. MFI = 100 - (100 / (1 + upper / lower)). **First value: bar 13.** In IEEE:
   - lower = 0 with upper > 0 gives 100;
   - 0 / 0 gives na.

**Step 5: the average (L25).**
- rsi_mfi = (rsi + mf) / 2. **First value: bar 14.**
- (a + b) / 2 and a / 2 + b / 2 are the same double. Halving is exact in binary, so the order of `math.avg` cannot
  matter.

**Step 6: the EMA's direction (L34, L37).**
- e = EMA(close, 5), with alpha = 2 / (5 + 1) and the update alpha x close + (1 - alpha) x e[1].
- de = e - e[1].
- The two calls are separate (L34 and L37) but compute the same thing.
- **The seed.** It follows the house reading: the first value (study 1 PREREG 5; study 2 `porting/session.md` R2).
  - With the first value as seed, de first exists on bar 1. With an SMA seed (what TradingView's runtime appears to
    do), it first exists on bar 5.
  - Either way this is before the first possible signal (step 9).
  - The gap between the two seeds shrinks by a factor of 2/3 every bar, so it falls below the last bit within
    roughly 60-100 bars. After that the two runs usually become identical: study 1 found every line equal from 2019
    under both seeds, except BTC 1D's TSI. Measure it on the study's bars.

**Step 7: the BUY condition (L31-L34).**
- p_mom = rsi_mfi[t-1] < 66, and rsi_mfi[t] > 66, and rsi_mfi[t] > 30, and de > 0.
- All the comparisons are strict, and an na makes the whole condition false.
- **First possible bar: 15.** rsi_mfi[t-1] must exist.

**Step 8: the SELL condition (L36-L37).**
- n_mom = rsi_mfi[t] < 30 and de < 0.
- It is a LEVEL test, not a cross. It holds on every bar below 30 with a falling EMA.
- **First possible bar: 14.**

**Step 9: the state update (L40-L46), in this order.**
1. If p_mom: positive = true and negative = false.
2. Then, if n_mom: positive = false and negative = true.
- p_mom and n_mom can never both hold, for any inputs: p_mom needs rsi_mfi > `nmom` and n_mom needs rsi_mfi < `nmom`.
  So the order never matters.
- Before the first event both states are false.
- After the first event exactly one of them is true on every bar.

**Step 10: the signals (L90-L93 labels, L100-L101 alerts).**
- **BUY** on bar t is positive[t] and not positive[t-1].
- **SELL** on bar t is negative[t] and not negative[t-1].
- After the first signal, BUY and SELL strictly alternate.
- A p_mom while the state is already positive, or an n_mom while it is already negative, changes nothing.

**Step 11: the band (L51-L55). Display only.**
- m = min(0.3 x ATR30, close x (0.3 / 100)).
  - ATR30 is `ta.atr(30)`: Wilder's RMA of `ta.tr(true)`. Bar 0's true range is high - low, and the first ATR is on
    bar 29.
  - 0.3 / 100 is the same double as 0.003.
- **The history operator binds to the `math.min` call.** So Band[t] = m[t-20] / 2 x 8, which is exactly
  4 x m[t-20], since scaling by powers of two is exact.
- **First value: bar 49.**

**Step 12: the range-weighted average (L58-L62, L66). Display only.**
- S[t] is the 20-bar `math.sum` of BarRange.
- weight[t] = BarRange[t] / S[t]: each bar is weighted by ITS OWN window's sum.
- num is the 20-bar sum of close x weight, and tw is the 20-bar sum of weight.
- rwma = num / tw. **First value: bar 38.**
- This is not sum(close x range) / sum(range). On a synthetic walk in scratch the two differ by up to 0.67 price
  units. Trap 10.

**Step 13: the plotted line, the band edges and the labels (L69-L96). Display only.**
- The line RWMA is:
  - rwma - Band while positive;
  - rwma + Band while negative;
  - na before the first event (L70).
- The band edges are max = RWMA + Band and min = RWMA - Band (L81-L82).
- The colours (L69, L88) and the coloured candles (L95-L96) follow the state. Before any event the candles are red.
- The labels are created on the signal bar itself, at `bar_index`:
  - a SELL label at max + Band / 2 (red, pointing down) when negative turns on (L90-L91);
  - a BUY label at min - Band / 2 (green, pointing up) when positive turns on (L92-L93).
  - Only the newest 500 labels stay on the chart.

## 5. Outputs, and when each is known

| Output | Lines | Definition | Known |
|---|---|---|---|
| State (positive / negative / neither) | L8-L9, L40-L46 | step 9 | at the close of t |
| "BUY" alert, green label | L92-L93, L100 | positive turns on | at the close of t (first possible bar 15) |
| "SELL" alert, red label | L90-L91, L101 | negative turns on | at the close of t (first possible bar 14) |
| RWMA line (4 copies with fading glow, title "RRTH") | L70, L73-L76 | step 13 | at the close of t (needs bar 49 and a state); display |
| Band edges and gradient fills | L81-L87 | step 13 | at the close of t; display |
| Candle and bar colours | L88, L95-L96 | green while positive, else red | at the close of t; display |
| Close plotted in the pane | L79 | display only | - |

## 6. Repaint and look-ahead audit

- **`request.security`, look-ahead, pivots, arrays, machine learning: none.**
- **The band uses values 20 bars old.** That is a lag, not a look-ahead.
- **Labels** are created at the current `bar_index` and never moved back.
- **`var` state on the live bar.** TradingView restores `var` values before each realtime tick and commits them at
  the close. So a BUY or SELL can appear and vanish within the live bar, and alerts set to fire intrabar can fire on
  a state that the closed bar does not keep. Closed bars are final.
- **`max_labels_count = 500`** (L5). Older labels are deleted from the chart. A visual count of signals on
  TradingView over a long history undercounts. Display only.
- **Dependence on the data start.** It is weak. The state is set by the latest event, and the RSI, MFI and EMA
  converge.
  - Two starts give the same state from the first event after both have warmed up.
  - The Wilder averages of the RSI keep start-dependent last bits for a while. Measure, as for the other scripts.

## 7. Data it needs

- **Prices.** The OHLC of the signal timeframe: the bid, on UTC bars, as in study 2.
- **Volume** (the MFI half of the average):
  - **Gold:** Exness tick volume.
  - **BTC:** Binance BTCUSDT spot volume, as study 2 did for every rule that reads volume. Exness BTC tick volume is
    a near-constant heartbeat (study 2 PREREG 2), which turns the MFI into roughly the share of rising typical prices
    in 14 bars. Keep it as a sensitivity row.
  - Hours with no Binance kline (volume 0) add nothing to either sum.
- **Nothing else.** No higher timeframe, no session, no time of day.
- The display band needs nothing extra: ATR(30) and a 20-bar range average come from the same bars.

## 8. How a rule could trade it

**The script's own hint.**
- The two alerts sit under the comment "SPOT Trading Alerts" (L99). That suggests buying on BUY and selling the
  holding on SELL, which is long only.
- The colours give a state reading: green candles while positive.

**The video** (chapter 7; quoted only in short phrases):
- It averages RSI and the MFI.
- It buys when the average crosses above 66 "while a fast EMA is rising".
- It sells when the average drops below 30, so "the sell comes late".
- It reads the chart as "If the candles are green, you're long".
- Its advice:
  - "don't add another oscillator"; add trend strength instead, with ADX above 20 on the signal candle;
  - "leave the settings alone" (14, 66, 30).
- The common test (chapter 5) is a signal on a closed candle and entry at the next open, long and short. The stop is
  2 ATR = 1R, with no target. The exit is the opposite signal or the stop. It uses the 4-hour chart and default
  settings.

Candidate rows, to be frozen in study 4's pre-registration:

| Row | Entry | Exit | Notes |
|---|---|---|---|
| RMI-S (main) | BUY / SELL at the close of t; fill at the next M1 open | the opposite signal (stop and reverse) or the stop at 2 x `ta.atr(14)` | event rule: after a stop, wait for the next signal. Signals alternate, so a stopped long re-enters long only after a SELL and a new BUY |
| RMI-A | as RMI-S, only if ADX(14) > 20 on the signal bar (study 2's ADX, `porting/coil.md` item 16) | as RMI-S | the video's own filter |
| RMI-E / RMI-D | as RMI-S with EMA200, or with a daily-chart filter | as RMI-S | the video's general advice (chapter 15) |
| RMI-LO | BUY only | SELL or the stop | the script's "spot" hint; the video says the longs carried the results |
| RMI-ST | the state, with no stop: long while positive, short while negative | the state change | the video's chart reading, kept as a sensitivity row |

Timeframes: 4H first (the video), then 1H and 1D.

**The video's numbers, to check later.** This is information only; the video's 11 markets and feeds are not ours.
- **The whole test.** 1,822 trades, 26% winners, profit factor 1.37, 7.5R a year on each market, and profitable in
  both halves (1.48 in the older half; the newer half's figure is garbled in the transcript). Two or three trades a
  month on each market.
- **Costs and markets.**
  - With costs doubled, 5.3R a year.
  - Profit factor above 2 on SOL and BNB, 1.45 on gold, 0.64 on the S&P 500.
- **By year.** -72R in 2022 and -59R in 2025, summed over the 11 markets.
- **The filter.** ADX above 20 gives a profit factor of 1.43, almost the same in both halves.
- **The window.** The test runs from January 2021 to October 2026, on the 4H chart.
- On our markets, only the gold profit factor (1.45) is a direct claim.

**Decisions to register:**
- the BTC volume source;
- the EMA seed (the house first value);
- the stop's ATR;
- EMA or SMA 200;
- whether RMI-A reads the ADX at the signal bar's close (the video says "on the signal candle").

## 9. Traps for a port (the readings to register)

| # | Item (lines) | Reading | Evidence | The alternative, and its effect |
|---|---|---|---|---|
| 1 | The name (L21-L23) | the RSI of 1-bar changes, not the classic RMI (changes over a momentum lookback) | as written | a classic RMI: a different indicator |
| 2 | The loss series (L22) | -min(dc, 0). It equals the house's max(-dc, 0) except that it is -0.0 on rising bars. Harmless: the sums and averages give +0.0, and `down == 0` is true either way | IEEE | compare floats with ==, not raw bytes |
| 3 | RMA seed (L21-L22) | the SMA of the first 14 changes (bars 1-14). First value on bar 14 | `pine_rma`; house `rma` | seeded with the first value: start-dependent last bits only |
| 4 | RSI guard (L23) | down == 0 gives 100 before up == 0 gives 0 | as written; house `_rsi_formula` | the reference `pine_rsi` gives na when both are 0 (a flat 14 bars; not on real 1H+ bars) |
| 5 | MFI (L24) | `pine_mfi`: the change of hlc3; a zero change adds to neither; both terms on bar 0 (immaterial, because rsi is na until bar 14); sums from this bar back; IEEE division | TradingView reference; house order | Pine turning x / 0 into na: such bars get an na average and no event. Count the windows with lower = 0 before freezing |
| 6 | The BUY cross (L31-L32) | previous < 66 strictly and current > 66 strictly | as written | `ta.crossover` (previous <= 66): a previous value of exactly 66.0 would then count |
| 7 | The SELL test (L36) | a level below 30, not a cross. Only the bar where the state turns negative is a signal | as written | treating it as a cross: later SELLs |
| 8 | EMA seed (L34, L37) | the first value (house) | study 1 PREREG 5 / DEVIATIONS 11 | the SMA seed: at most the first ~100 bars' last bits |
| 9 | `and` evaluation (L31-L37) | Pine v5 evaluates every operand on every bar, so each EMA call updates every bar | Pine v5. Lazy `and` / `or` only arrives in v6 | emulating v6 laziness would leave gaps in the EMA's history and move the EMA |
| 10 | `rangeMA` weights (L58-L62) | each bar's range divided by its own 20-bar range sum, then a weighted mean with those weights | as written | the simple range-weighted mean: another line (display only) |
| 11 | The band (L52) | `[20]` applies to the `math.min(...)` result; Band = 4 x min(0.3 x ATR30, 0.003 x close), 20 bars back; ATR30 uses `ta.tr(true)` | Pine precedence; `pine_atr` | the delay on the close term only, or no delay: another band (display only) |
| 12 | A zero range sum (L59) | division by zero gives na in the window for 20 bars | IEEE | impossible on real 1H+ bars (20 bars with high == low) |
| 13 | The first state | both false. Before the first event: no line and red candles. The first signal can be a SELL | `var` initial values | starting long or short: one extra trade at the start |
| 14 | Thresholds (L14-L15) | int inputs compared as floats (66.0, 30.0) | Pine casting | none |
| 15 | Labels (L5, L90-L93) | 500 kept; display only | `max_labels_count` | none for the ports |
| 16 | Not used here | no `ta.supertrend`, no pivots, no `request.security`, no HTF | read L1-L101 | none |

## 10. The shared contract for the two ports, and the hand tests

**Each port returns, per bar** (float64 with NaN for na; booleans):
- dc, up, down, rsi, tp, upper, lower, mf, rsi_mfi;
- e, de, p_mom, n_mom, positive, negative, BUY, SELL;
- for display: ATR30, m, Band, S, weight, num, tw, rwma, RWMA, max, min.

The signal series must agree bit for bit on the study's 1H / 4H / 1D gold and BTC bars, with both BTC volume
sources. The display series must agree too, if any rule reads them.

**Hand tests:**
1. **rsi_mfi[t-1] = 66.0 exactly** and rsi_mfi[t] = 70 with a rising EMA: no BUY.
2. **n_mom on 5 bars in a row:** one SELL, on the first.
3. **A first event that is n_mom:** the first signal is a SELL. Before it, RWMA is na and both states are false.
4. **Band[t] = 4 x min(0.3 x ATR30[t-20], 0.003 x close[t-20])**, with the first value on bar 49.
5. **rwma on a hand series** with alternating ranges 1 and 3 differs from sum(close x range) / sum(range).
6. **de = 0 exactly** (the close equals the previous EMA): neither p_mom nor n_mom.
7. **Warm-up:** rsi is first on bar 14, mf on 13, rsi_mfi on 14, rwma on 38 and Band on 49.

**Sharpness check.** Rerun with these deliberate breaks:
- `<=` on the previous bar of the BUY;
- a crossing SELL;
- an SMA EMA seed with the first-value comparison (it must fail only in the first ~100 bars);
- the simple range mean;
- the delay on one term only.

## 11. Porting effort

- **Lines that compute.**
  - 9 statements drive the signals: L21-L25, L31-L37, L40-L46 and L100-L101.
  - About 10 more draw the band: L51-L55, L58-L66, L70, L81-L82 and L90-L93.
- **A port.** About 80-120 lines of Python.
  - The house `tradeiq_ind` has `rsi` (equal to L21-L23), `rma`, `ema`, `atr` (`ta.tr(true)`, correct for L52) and
    `math_sum`.
  - Only the MFI is new. It is shared with the AlphaTrend port, in `tradeiq3_ind_common.py` as the study-4
    infrastructure map (`infra.md` 4.3) proposes. Port B writes its own from TradingView's reference code.
- **Time.** A few hours per port, with tests.
- **Risk:** low. The only material choices are the BTC volume source and the EMA seed.
