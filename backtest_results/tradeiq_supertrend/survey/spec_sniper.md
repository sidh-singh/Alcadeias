# Precision Sniper [WillyAlgoTrader] v2.3.0: porting spec (study 4, TradeIQ video 3, script #4 of the video)

Written 28 Nov 2026 from the owner's copy, before any port, rule or backtest exists. Nothing here was run on market
data. Third-party code: it is restated below in formulas and plain words, never copied.

- **Source file:** `/Users/sidharthsingh/Desktop/study/trend/Precision Sniper Indicator.rtf`
  (sha256 of the RTF `b20effbd5220044f77591bab54ea9ee1533517a57ed3c9c95c901e3c58ea2f55`).
- **Plain-text copy used for line numbers (L..):** `textutil -convert txt -stdout "<file>"`, numbered from 1
  (1,023 lines; sha256 of that text `b120403455f6c2851f55179c8a1ec9af19c2c60ce45f41d85a5b4a375753d62c`).
- **Author:** "Willy | WillyAlgoTrader" (L3-L5). Script version 2.3.0 (L6, L10). No licence line in the copy.
- **Pine version:** v6 (L1). An indicator, overlay, with at most 500 labels and 30 lines kept on the chart (L8). It is
  not a strategy: its "trades" are an internal model drawn on the chart and summarised in a dashboard.
- **Module key:** `sniper` (as proposed in `infra.md` of this folder).

## 0. Bottom line

**What it is.**
- An EMA-crossover entry engine. The fast EMA crossing the slow EMA opens a candidate, and the candidate becomes a
  "Long" or "Short" label only if it passes a gate:
  - data ready, the date window and the session;
  - volatility not spiking (ATR against its 42-bar mean);
  - price momentum: the close beyond both EMAs;
  - RSI not extreme;
  - an optional higher-timeframe filter;
  - enough evidence from up to 8 weighted factors;
  - a valid stop and target plan.
- It plans a stop (an ATR stop, widened to the last 11 bars' structure and capped) and three targets at 1R, 2R and 3R.
- It then runs an **internal model trade**: entry at the signal bar's close, stop first on ambiguous bars, a step stop
  after each target, a full exit at TP3, a reversal on the next opposite label.

**The labels depend on that internal trade.** This is the trap that decides the port:
- a candidate in the direction of a model trade that is still open is dropped;
- one re-entry per crossover cycle ("Long RE" / "Short RE") is allowed only after the model trade of that cycle has
  closed, by a stop or at TP3.
- So the label stream is not a function of indicator values alone. The whole internal model must be ported, even for
  a rule that trades the labels with its own stop, as the video did.

**The defaults that matter:**
- The preset is Auto, by chart timeframe: 4H and 1D are "Swing" (EMA 13 / 34 / 89, RSI 21, ATR 20, score 6/10, stop
  2.5 ATR); 1H and M15 are "Default" (9 / 21 / 55, RSI 13, ATR 14, score 5/10, stop 1.5 ATR); M5 is "Scalping".
- Evidence model v2. The higher timeframe is off: the mode reads "Soft score", but the timeframe is empty.
- The session VWAP is on for intraday charts.
- **No entry before 2020-01-01 00:00 UTC**: the bar's open time must be at or after the start input.
  - Under the reverse split proposed in `infra.md` (selection from 2021, exam windows before 2021), the default would
    leave the exam nearly empty: no label at all in E2 (gold 2017-01-01 to 2018-11-13), and in E1 (2018-11-13 to
    2021-01-01) labels only in 2020.
  - The start date is therefore a pre-registration decision (trap 3), not a detail.

**Timing.**
- The whole model runs only on confirmed bars. A label is known at the close of its bar and never repaints.
- The two `request.security` calls use the previous bar of the requested timeframe with `lookahead_on`, the standard
  non-repainting form. One feeds the higher-timeframe filter (off); the other only the display.
- The 3 / 3 pivots feed only the "nearest level" plots, from their confirmation bar on.

**Data:** OHLC and volume (tick volume is acceptable: it switches on two factors and raises the evidence maximum from
5 to 7), a daily anchor for the VWAP, the chart timeframe in seconds and the symbol's tick size.

**Effort:** high.
- About 280 computing lines drive the labels: indicators about 60; evidence, plan and gate about 90; the four-phase
  engine about 130. About 50 more lines are its statistics. About 650 lines of inputs, dashboard, drawings and alerts
  need no port.
- Two to three days per port plus reconciliation. It needs EMA, ATR, SMA, RSI, MACD, DMI / ADX, a session VWAP,
  highest / lowest and a tick-exact trade engine.

## 1. Inputs and defaults

"Labels?" says whether the input can change which labels appear (the signal stream). "Stats" means it changes only
the model's R numbers and the dashboard.

**Main / data (L34-L41)**

| Input (title) | Variable | Default | Labels? |
|---|---|---|---|
| Price source | `sourceChoice` | **Close** (also HL2, HLC3, OHLC4) | yes: the EMAs, RSI and MACD only; momentum and execution use real OHLC |
| Preset | `presetInput` | **Auto** (also Conservative, Default, Aggressive, Scalping, Swing, Crypto 24/7, Custom) | yes (section 3) |
| HTF mode | `htfMode` | Soft score (also Off, Hard filter) | only with a higher timeframe |
| Higher timeframe (empty = OFF) | `htfInput` | **"" (off)** | yes when set |
| Session VWAP | `vwapMode` | **Auto** (also On, Off) | yes |
| Warmup periods | `warmupMult` | **3** (2..10) | yes |
| Entry/statistics start | `startInput` | **2020-01-01 00:00 UTC** | yes |
| Entry/statistics end | `endInput` | 2100-01-01 00:00 UTC | yes (no effect in practice) |

**Entry engine (L42-L55)**

| Input | Variable | Default | Labels? |
|---|---|---|---|
| EMA fast / slow / trend (Custom) | `emaFastInput` / `emaSlowInput` / `emaTrendInput` | 9 / 21 / 55 | only with the Custom preset |
| RSI length (Custom) | `rsiLenInput` | 13 | Custom only |
| Minimum score / 10 (Custom) | `scoreInput` | 5 | Custom only |
| Grade filter | `gradeFilter` | **All** (also "A+ and A", "A+ Only") | yes |
| Hide C grade | `hideC` | **true** | yes (raises the required ratio to at least 0.5) |
| High volatility | `volMode` | **Skip Signals** (also Off, Widen SL) | yes |
| High ATR / mean ATR | `volThreshold` | **1.3** | yes |
| High-vol stop multiplier | `volWiden` | 1.5 | only with Widen SL |
| Evidence model | `evidenceModel` | **v2 decorrelated** (also v1 legacy) | yes |
| Re-entries per crossover cycle | `maxReentries` | **1** (0..3) | yes |
| Extra confirmation bars after crossover | `confirmWindow` | **0** | yes |
| Maximum distance to fast EMA / ATR | `maxExtension` | **0 (off)** | yes when > 0 |

**Risk / execution model (L56-L74)**

| Input | Variable | Default | Labels? |
|---|---|---|---|
| ATR length (Custom) | `atrLenInput` | 14 | Custom only |
| ATR stop multiplier (Custom) | `slMultInput` | 1.5 | Custom only |
| TP1 R / TP2 R / TP3 R | `tp1Mult` / `tp2Mult` / `tp3Mult` | **1 / 2 / 3** | yes, through the internal trade |
| Close original position at TP1 / TP2 (%) | `tp1Pct` / `tp2Pct` | 0 / 0 (a whole-position model) | stats |
| Step stop after targets | `trailInput` | **true** | yes |
| Close remaining position at TP3 | `fullTP3` | **true** | yes |
| Use window structure | `structureInput` | **true** | yes |
| Previous bars for structure (+ current) | `swingLookback` | **10** | yes |
| Structure cap floor (ATR) | `capFloorATR` | **2.0** | yes |
| Structure beyond cap | `structurePolicy` | **Cap and flag** (also Skip entry) | yes |
| Minimum initial risk (ticks) | `minRiskTicks` | **2** | yes |
| Commission per side (%) / spread (ticks) / slippage (ticks) | `commissionPct` / `spreadTicks` / `slipTicks` | 0 / 0 / 0 | stats |
| Cost warning / initial R | `costWarningR` | 0.2 | display |
| Require positive trade prices | `positiveOnly` | **true** | yes (never binds on gold or BTC) |

**Context / session (L76-L82)**

| Input | Variable | Default | Labels? |
|---|---|---|---|
| Trading window | `sessionMode` | **Info only** (also Off, Filter entries) | only with Filter entries |
| Session hours | `sessionHours` | 0000-0000 (24 hours) | with Filter entries |
| Session days (1 = Sun ... 7 = Sat) | `sessionDays` | 1234567 | with Filter entries |
| Session timezone (IANA) | `sessionTZ` | Etc/UTC | with Filter entries; also the dashboard's time formatting |
| Show nearest known levels | `showLevels` | true | display |
| Confirmed pivot bars left/right | `pivotLen` | 3 | display (the levels) |
| Signal extension warning (R) | `lateR` | 0.5 | display |

**Display, sizing and alerts (L83-L126): none changes a label.**
- Sizing calculator: off, manual equity 10,000, 1% risk, etc.
- Dashboard sections, journal, marker sizes, colours (bull #00B876, bear #E34850, neutral #FFEB3B), label offset 20.
- Alerts: JSON batch off, entry, target, stop-change and exit events on, candidate events off, instance tag "main".

**Fixed constants (L12-L25):**

| Constant | Value |
|---|---|
| ADX trend threshold | 20 |
| ATR mean length | 42 |
| Volume mean length | 20 |
| Volume spike | 1.2 |
| Structure buffer | 0.2 ATR |
| Structure cap | 1.5 × the ATR stop |
| RSI band | 25 at length 14 |
| Factors | 8 |
| Low-volatility ratio | 0.7 (display) |
| Journal | 50 |
| Form strip | 10 |
| Pivots kept per side | 10 |
| Alert length | 4,000 characters |

## 2. Configuration checks (L140-L164)

On the first bar the script stops with a runtime error when any of these fails:
- tick at least 1e-8;
- standard candles (no Heikin Ashi or Renko);
- a time-based chart;
- fast < slow < trend;
- TP1 < TP2 < TP3;
- TP1% + TP2% < 100;
- start < end;
- an enabled higher timeframe strictly above the chart's;
- session days made of the digits 1-7;
- session hours starting with HHMM;
- dashboard and journal in different corners.

A port should refuse the same configurations. It must run on the study's ordinary OHLC bars: Heikin Ashi input is
refused by design.

## 3. The profile (L129-L138)

The preset from the chart timeframe in seconds s (Auto):
- s <= 300: Scalping;
- else s <= 3600: Default;
- else s < 14400: Conservative;
- else: Swing.

**4H (14,400 s) is Swing,** although the tooltip's wording ("<4h Conservative") could be read otherwise. The Auto
preset never selects Aggressive or Crypto 24/7.

| Preset | fast / slow / trend | RSI | ATR | min score /10 | stop × ATR |
|---|---|---|---|---|---|
| Scalping | 5 / 13 / 34 | 8 | 10 | 4 | 0.8 |
| Aggressive | 8 / 18 / 50 | 11 | 12 | 3 | 1.2 |
| Default | 9 / 21 / 55 | 13 | 14 | 5 | 1.5 |
| Conservative | 12 / 26 / 89 | 14 | 14 | 7 | 2.0 |
| Swing | 13 / 34 / 89 | 21 | 20 | 6 | 2.5 |
| Crypto 24/7 | 9 / 21 / 55 | 14 | 20 | 5 | 2.0 |
| Custom | the Custom inputs (9 / 21 / 55, 13, 14, 5, 1.5) | | | | |

**What that gives on the study's charts with the defaults** (volume present, HTF off; the arithmetic is section 6;
the float products were checked in float64 on 28 Nov 2026):

| Chart | Preset | RSI band (rejects longs at >= / shorts at <=) | Cap on the stop | Warm-up bars | Evidence max | Required (ratio × max) | Minimum factors |
|---|---|---|---|---|---|---|---|
| M5 | Scalping | 83.07189 / 16.92811 | max(1.2, 2.0) = 2.0 ATR | max(34·3, 10 + 42) = 102 | 7 | 0.5 × 7 = 3.5 | 4 of 7 |
| M15, 1H | Default | 75.94373 / 24.05627 | max(2.25, 2.0) = 2.25 ATR | max(55·3, 14 + 42) = 165 | 7 | 0.5 × 7 = 3.5 | 4 of 7 |
| 2H | Conservative | 75 / 25 | 3.0 ATR | 267 | 7 | 0.7 × 7 = 4.8999999999999995 | 5 of 7 |
| **4H** | **Swing** | **70.41241 / 29.58759** | **3.75 ATR** | **267** | **7** | **0.6 × 7 = 4.2** | **5 of 7** |
| 1D | Swing | 70.41241 / 29.58759 | 3.75 ATR | 267 | 6 (no VWAP on a daily chart) | 0.6 × 6 = 3.5999999999999996 | 4 of 6 |

Notes on the table:
- The required ratio is max(min score / 10, 0.5 because Hide C is on, the grade filter's 0.8 or 0.65 or 0).
- The RSI band is min(35, max(15, 25·sqrt(14 / RSI length))) around 50.
- Warm-up = max(trend length × warmupMult, ATR length + 42).

## 4. Pine primitives the port must reproduce

Bars are t = 0, 1, ... from the first bar of the data; `x[k]` is k bars back, na for t < k. A comparison involving na
is false; booleans are never na in v6; `math.max` / `math.min` with na give na.

| Primitive | Definition for both ports | Repository helper |
|---|---|---|
| EMA(x, n) | alpha = 2 / (n + 1); E[t] = alpha·x[t] + (1 − alpha)·E[t−1]. **Start:** the first value (study 1's PREREG 5); the alternative is TradingView's apparent start, the SMA of the first n values (trap 22) | `tradeiq_ind.ema(seed="first")` |
| RMA(x, n) | alpha = 1 / n; na until n values exist; seeded with their SMA; then alpha·x + (1 − alpha)·previous | `tradeiq_ind.rma` |
| SMA(x, n) | the reference order: the sum over i = 0 .. n−1 of x[t−i] / n | `tradeiq_ind.sma` |
| ATR(n) | RMA of the true range with TR[0] = high − low | `tradeiq_ind.atr` |
| RSI(x, n) | RMA(n) of max(change, 0) and of max(−change, 0); change is na on bar 0; RSI = 100 if the loss average is 0, 0 if the gain average is 0, else 100 − 100 / (1 + up / down). First value on bar n | `tradeiq_ind.rsi` |
| MACD(x, 12, 26, 9) | line = EMA(x, 12) − EMA(x, 26); signal = EMA(line, 9); hist = line − signal | from `ema` |
| DMI(14, 14) | the reading verified in study 2 (TradingView's built-in DMI script), spelled out below | `tradeiq2_ind_coil` (`_dmi`), oracle `tests/tradeiq2_oracle_coil.dmi` |
| highest(x, n) / lowest(x, n) | the max / min of bars t−n+1 .. t; na until n bars exist | `tradeiq2_ind_wyckoff.highest` / `lowest` |
| crossover(a, b) | a > b now and a <= b on the previous bar; false if any is na | `tradeiq_ind.crossover` / `crossunder` |
| VWAP(src) | Σ src·volume / Σ volume since the anchor bar, which is included. The one-argument `ta.vwap` is documented with a default anchor equal to `timeframe.change("1D")`: the first chart bar of each new daily bar. 0 / 0 is na | new; sums run oldest to newest |
| hlc3 | (high + low + close) / 3, added in that order | |
| `math.round_to_mintick(x)` | the nearest multiple of the tick, ties up | integer ticks (trap 13) |
| pivot high / low (3, 3) | strict on both sides, the value of bar t − 3 on bar t | `tradeiq2_ind_wyckoff.pivots(..., ties="strict")`; display only |

**The DMI in words.**
- up = high[t] − high[t−1]; down = low[t−1] − low[t]. Both are na on bar 0.
- +DM = up when up > down and up > 0, else 0 (na where up is na). −DM = down when down > up and down > 0, else 0.
- trur = RMA14 of the true range **with na on bar 0** (unlike the ATR's).
- +DI = 100·RMA14(+DM) / trur and −DI likewise, each forward-filled (`fixnan`).
- s = +DI + −DI; ADX = 100·RMA14(abs(+DI − −DI) / (1 if s = 0 else s)).
- +DI and −DI start on bar 14, the ADX on bar 27.

## 5. The series computed on every bar, in source order (L199-L281, L302-L306)

Every series below is computed on every bar, confirmed or not. No `ta.*` call sits inside a condition, so there is no
conditional-memory trap. In the formulas, d = +1 for long and −1 for short.

| # | Lines | Series | Definition, na handling |
|---|---|---|---|
| 1 | L199 | source | the close (default) |
| 2 | L200-L202 | emaFast, emaSlow, emaTrend | EMA(source, fast / slow / trend length) |
| 3 | L203-L204 | atr, atrMean | ATR(ATR length); SMA(atr, 42), first value on bar (ATR length − 1) + 41 |
| 4 | L205 | rsi | RSI(source, RSI length) |
| 5 | L206 | hist | MACD(source, 12, 26, 9) histogram (fixed lengths, whatever the preset) |
| 6 | L207 | diPlus, diMinus, adx | DMI(14, 14) on high, low and close (not on the source) |
| 7 | L209 | volMean | SMA(volume, 20) **of the previous bar**: bars t−20 .. t−1, so the current bar does not dilute its own spike |
| 8 | L210 | vwap | VWAP(hlc3), daily anchor (trap 5) |
| 9 | L211-L213 | hasVolume (`var`, false) | becomes true for good on the first **confirmed** bar with volume > 0 |
| 10 | L214 | vwapEnabled | the chart is intraday and (VWAP mode On, or Auto with a preset other than Crypto 24/7). With Auto it is true on every intraday chart, BTC included; false on 1D |
| 11 | L215-L217 | volumeReady, vwapReady, volAbove | volumeReady = (not hasVolume) or (volume not na, volume >= 0, volMean not na and > 0). vwapReady = not (vwapEnabled and hasVolume) or vwap not na. volAbove = hasVolume and volumeReady and volume > volMean·1.2 (strict) |
| 12 | L218-L219 | htfFast, htfSlow, htfClosedAt, htfReady, htfBias | trap 4. Off by default, so htfBias = 0 |
| 13 | L220-L222 | warmupBars, warmed, ready | warmed = t >= warmupBars. ready = warmed and atr > 0 and atrMean > 0 and rsi not na and hist[t−1] not na and adx not na and volumeReady and vwapReady and (HTF off, or htfReady with both HTF EMAs present) |
| 14 | L223-L226 | volRatio, highVol, stopMultiplier | volRatio = atr / atrMean when atrMean > 0, else na. highVol = volRatio > 1.3 (strict). stopMultiplier = 1.5 only with Widen SL and highVol, else 1 |
| 15 | L227-L231 | bullCross, bearCross, bullResume, bearResume | crossover / crossunder(emaFast, emaSlow); bullResume = crossover(close, emaFast) and emaFast > emaSlow; bearResume = crossunder(close, emaFast) and emaFast < emaSlow |
| 16 | L233-L235 | rsiUpper, rsiLower | 50 ± min(35, max(15, 25·sqrt(14.0 / RSI length))) |
| 17 | L237-L238 | bullMomentum, bearMomentum | close > emaFast and close > emaSlow; the mirror (strict) |
| 18 | L239-L241 | trendDir, trending, regime | trendDir = 1 if emaFast > emaSlow and close > emaTrend; −1 for the mirror; else 0. trending = adx >= 20. regime = 0 (not trending), 1 (trending and trendDir ≠ 0), 2 (mixed). Stats and display only |
| 19 | L243 | scoreMax | 5 + (1 if hasVolume) + (1 if vwapEnabled and hasVolume) + (1.5 if HTF on and Soft score) |
| 20 | L246-L249 | trendSlope, histDelta, priorHigh, priorLow | emaTrend[t] − emaTrend[t − fast length]; hist[t] − hist[t−1]; highest(high, 10) and lowest(low, 10) **of the previous bar** (bars t−10 .. t−1) |
| 21 | L277-L278 | bullScore, bearScore | the evidence of section 6.1 for d = +1 and d = −1 |
| 22 | L279 | requiredRatio | max(min score / 10.0, max(0.5 if Hide C else 0, 0.8 for "A+ Only", 0.65 for "A+ and A", else 0)) |
| 23 | L280-L281 | swingLow, swingHigh | lowest(low, 11) and highest(high, 11) **including** the current bar |
| 24 | L302-L305 | inSession, sessionAllowed | inSession: the bar is inside the session spec in its timezone ("0000-0000" on all seven days is the whole day, so always true). sessionAllowed = mode ≠ Filter entries, or inSession |
| 25 | L306 | dateAllowed | the bar's **open** time >= start and its **close** time < end |

Display only, not needed for labels: the session start, high and low (L309-L316), the prior day's high and low
(L317), and the arrays of the last 10 confirmed 3 / 3 pivots (L318-L330).

## 6. Evidence, plan and gate

### 6.1 Evidence (L261-L276)

The score of side d is the sum of the weights of the factors that are on. The factors are evaluated on the bar of the
decision.

| i | Name (v2) | On when | Weight | Used when |
|---|---|---|---|---|
| 0 | Trend side | d·(close − emaTrend) > 0 | 1 | always |
| 1 | Trend slope | d·trendSlope > 0 | 1 | always (v1: the RSI zone, 50 < rsi < upper for longs, lower < rsi < 50 for shorts) |
| 2 | Structure break | long: close > priorHigh; short: close < priorLow | 1 | always (v1: the MACD sign, d·hist > 0) |
| 3 | MACD accel | d·histDelta > 0 | 1 | always |
| 4 | ADX / DI | trending and d·(diPlus − diMinus) > 0 | 1 | always |
| 5 | Volume spike | volAbove (**the same for both sides**) | 1 | hasVolume |
| 6 | VWAP side | vwapEnabled and hasVolume and d·(close − vwap) > 0 | 1 | intraday with volume |
| 7 | HTF bias | HTF on, Soft score, and htfBias = d | **1.5** | HTF Soft score only |

All comparisons are strict. A factor whose inputs are na is off.

### 6.2 The plan of side d (L283-L300)

Evaluated whenever a candidate is pending; it reads only series of section 5:
1. e = round_to_mintick(close).
2. atrDistance = (atr·slMult)·stopMultiplier; atrStop = e − d·atrDistance.
3. structStop = swingLow − atr·0.2 for a long; swingHigh + atr·0.2 for a short.
4. rawStop = the wider of the two when "Use window structure" is on: min(atrStop, structStop) for a long, max for a
   short. Otherwise atrStop. Structure only ever widens the stop.
5. capDistance = max(atrDistance·1.5, atr·capFloorATR).
6. capped = structure on and abs(e − rawStop) > capDistance (strict). bounded = e − d·capDistance if capped, else
   rawStop.
7. stop = roundDown(bounded) for a long, roundUp(bounded) for a short:
   - roundDown(x) = round_to_mintick(floor(x / tick + 1e-8)·tick);
   - roundUp(x) = round_to_mintick(ceil(x / tick − 1e-8)·tick).
8. risk = abs(e − stop).
9. p_k = round_to_mintick(e + d·risk·tpMult_k) for k = 1, 2, 3 (1, 2, 3 R), multiplied left to right.
10. valid when all of these hold:
    - risk not na and risk >= minRiskTicks·tick − tick·1e-6;
    - d·(e − stop) > 0, d·(p1 − e) > 0, d·(p2 − p1) > 0, d·(p3 − p2) > 0;
    - with "positive prices", the smallest of e, stop, p1, p2 and p3 is > 0.
11. Also returned (display): the stop's origin, one of "ATR", "Structure" or "ATR capped".

### 6.3 The gate of side d (L474-L501)

The first failing test gives the code:

| Code | Test (fails when) |
|---|---|
| 1 | not ready |
| 2 | not dateAllowed |
| 3 | not sessionAllowed |
| 4 | volatility mode Skip Signals and highVol |
| 5 | no momentum on side d |
| 6 | RSI extreme: long and rsi >= rsiUpper, or short and rsi <= rsiLower (**non-strict**) |
| 7 | HTF Hard filter and htfBias ≠ d |
| 8 | evidence + 1e-9 < requiredRatio·scoreMax |
| 9 | plan not valid |
| 10 | structure policy Skip entry and the plan is capped |
| 11 | maximum extension > 0 and abs(close − emaFast) / atr > it |
| 0 | accepted |

## 7. The engine on each confirmed bar (L507-L686)

On historical bars every bar is confirmed. In real time only the closing tick is. So every step below happens exactly
once per bar, at its close, in this order.

**State that persists (signal-relevant part; L410-L447).**
- The trade object:
  - active (false), dir (0), entryBar (na), entry, initialStop, stop, risk, tp1, tp2, tp3;
  - hit1 / hit2 / hit3 (false), remaining (1.0);
  - grossR / costR (0), and fields for the statistics only.
- cycleDir (0), cycleBar (na), reentriesUsed (0).
- pendingDir (0), pendingBar (na), pendingReentry (false).
- The statistics counters (total, wins, totalR, ...): stats only.

**Phase 1: the old position (L510-L546).** It runs only if a trade is active and was entered on an earlier bar
("managed").
1. s = the trade's current stop. It was set at entry or moved by an earlier bar's phase 3.
2. stopped = (long: low <= s; short: high >= s).
3. For k = 1, 2, 3: touch_k = not hit_k and (long: high >= tp_k; short: low <= tp_k).
4. **If stopped, the stop comes first**, whatever the targets did:
   - fill = min(open, s) for a long, max(open, s) for a short, so a gap through the stop fills at the open;
   - the trade closes at the fill with reason "SL" if s equals the initial stop, else "Step stop";
   - targets touched on this bar only set the "ambiguous" flag (stats). Phase 1 ends.
5. **Else**, for k = 1, 2, 3 in order: if touch_k, then hit_k = true and the partial close at tp_k is taken (0% by
   default, so nothing). If k = 3 and "close remaining at TP3" is on, the trade closes at tp3 with reason "TP3".
6. MFE / MAE bookkeeping (stats).

**Phase 2: candidates (L550-L615).**
1. **Every** fast / slow cross resets the cycle: cycleDir = its side, cycleBar = t, reentriesUsed = 0. This happens on
   every cross, also before the warm-up ends and outside the date window.
2. If there is a cross, dateAllowed and warmed: a pending candidate, if any, is cancelled (never at the defaults:
   see step 4). A new candidate is created: pendingDir = the cross side, pendingBar = t, not a re-entry.
3. **Else**, if no candidate is pending, reentriesUsed < maxReentries, dateAllowed and warmed, all three must hold:
   - the cycle side's resume trigger fires on this bar (a long cycle: close crosses above emaFast while emaFast >
     emaSlow; the mirror for a short cycle);
   - the last trade (state **after** phase 1) is closed and was on the cycle's side;
   - it was entered at or after cycleBar.
   Then a **re-entry candidate** is created on the cycle's side.
4. If a candidate is pending:
   - compute its plan (6.2) and gate code (6.3). If the side's momentum fails, the code becomes 5 whatever it was
     (a broken candidate never survives).
   - lastChance = t − pendingBar >= confirmWindow: always true at the default 0, so every candidate is decided on its
     own bar.
   - alreadyOpen = a trade is active on the candidate's side.
   - If code = 0 and not alreadyOpen: **accepted**. The signal is the side, and the plan's numbers are kept for the
     entry. A re-entry adds 1 to reentriesUsed. The candidate is cleared.
   - Else: if lastChance, code = 5, alreadyOpen or not dateAllowed, the candidate is dropped. Otherwise it waits
     (only possible with confirmWindow > 0).

**Phase 3: bar-close actions on a position that survived phase 1 (L618-L629).**
1. If the signal is the opposite side of the trade: the trade closes at the close with reason "Reversal".
2. Else if the bar's close time >= end: it closes at the close, "Date end".
3. Else, with step stops on: next = tp2 if hit3, tp1 if hit2, entry if hit1, else the current stop. If d·(next −
   stop) > 0.1·tick, the stop becomes next **from the next bar on**.
   - After TP1 the stop is the entry price; after TP2 it is TP1. With TP3 closing all, "tp2 if hit3" never acts.

**Phase 4: accounting of a trade that closed in phase 1 or 3 (L632-L673).**
- Statistics only: net R, wins / losses at ±1e-8, the drawdown in R, groups, factor tables, the journal.
- The exit label is drawn on the exit bar at the exit price.

**Entry (L675-L686).** If there is a signal and no trade is active, which is always the case after phases 1 and 3:
- a new trade opens at e with the plan's stop (as initialStop and stop), risk and targets;
- entryBar = t; score, grade, regime and factors are stored (stats);
- the "Long" / "Short" label is drawn at the bar's low / high, with " RE" for a re-entry and the grade;
- confirmedBuy / confirmedSell are set for the alerts.

**The consequences for the label stream.**
- Crosses alternate. A same-side candidate can therefore meet an open same-side trade only after an opposite cross
  was rejected, which leaves the old trade running. That candidate is dropped ("Same direction already open").
- A long can live through any number of rejected bear crosses. It ends only by its stop, TP3, an **accepted** short,
  or the date end.
- A re-entry needs an accepted entry in the same cycle that has since closed, by stop, step stop or TP3. A reversal
  always starts a new cycle.
  - Rejected re-entry candidates do not use up the allowance, so later resume bars can try again.
  - A re-entry can be created on the very bar where the stop was hit, since phase 1 runs first.
- Several labels can therefore follow one crossover: the cross label and at most one RE label at the defaults.

**Grades (L173).** gradeOf(score / scoreMax): A+ at >= 0.8, A at >= 0.65, B at >= 0.5, else C. With Hide C on, C
never passes the gate.

## 8. Outputs and when each is known

| Output | Lines | Known at | Repaint / look-ahead |
|---|---|---|---|
| EMA ribbon: fast, slow, trend, the fill | L733-L736 | close of each bar | none after the close (moves while the bar forms) |
| Trend background (off) | L737 | close | display |
| "Nearest resistance / support (known now)" | L739-L743 | close | uses only the 3 / 3 pivots after their confirmation (3 bars late), the previous day's high / low, and the session's high / low **excluding** the current bar. Display only |
| Entry labels "Long" / "Short" (+ " RE", grade) | L685-L686 | **close of the signal bar**; drawn on it | never on an unconfirmed bar; no repaint |
| Exit labels (reason and net R) | L672-L673 | close of the exit bar; drawn at the exit price | a stop or target touched inside the bar is reported at its close |
| Trade level lines (entry, initial SL, TP1-3, step SL) | L747-L789 | from the entry bar; the right end is moved on the last bar | the step stop line starts when the new stop took effect |
| `alert()` text or JSON batch | L689-L697 | once per bar close | events of the old and the new trade on one bar travel together |
| Alert conditions (Buy / Sell, A+ only, A+ and A, B or better, TP1 / TP2 / TP3 hit, stop hit, position closed, stop changed, candidate cancelled, any signal) | L700-L715 | close: the flags are set only on confirmed bars | none |
| Dashboard, journal, watermark | L853-L1023 | last bar only | the candidate status and the evidence gauge are evaluated **live** on the forming bar (marked "[live]") and say "awaiting bar close"; information only |

## 9. Repaint and look-ahead audit

- **Entries and exits:** decided only on confirmed bars, from that bar's and earlier data. No repaint.
- **The internal model's prices:**
  - the entry fills at the signal bar's close: optimistic, but it is the decision price, not a future one;
  - stops before targets on an ambiguous bar: conservative;
  - a gap through the stop fills at the open;
  - target fills at the level even on a gap: optimistic, stats only.
- **`request.security` (L218):** the previous bar's values of the higher timeframe with `lookahead_on`: the HTF bar
  that had closed by the chart bar's open. Non-repainting on history and live. Off by default.
- **`request.security` (L317):** the same form for the previous daily high and low. Display only.
- **Pivots (L318-L330):** confirmed 3 bars late and used only from then on, for the display.
- No labels moved back in time, no machine learning, no future bars.

## 10. Data needed

- **OHLC** of the chart timeframe. Open is used by the model's stop fills; high, low and close everywhere.
- **Volume.**
  - It turns on factor 5 (a spike against the 20 prior bars) and factor 6 (VWAP side), and raises scoreMax from 5 to
    7 intraday (6 on 1D). So it changes the required count of factors.
  - Gold has only tick volume. TradingView's Exness feed shows tick volume too, so tick counts are the "as
    TradingView" reading for both symbols.
  - The harness's default for BTC is Binance BTCUSDT volume (`Context.volume`, study 2's convention); its
    `source="tick"` gives Exness tick volume.
  - The plan must choose; it changes labels.
- **A daily anchor for the VWAP** on intraday charts: the first chart bar of each day.
  - With the study's UTC bars that is 00:00 UTC.
  - TradingView's Exness gold may roll its day elsewhere (study 2 measured a 17:00 New York session as the largest
    known difference for gold). BTC's day is 00:00 UTC on either reading.
- **The chart timeframe in seconds** (the Auto preset) and whether it is intraday.
- **The symbol's tick:** 0.001 for XAUUSDm and 0.01 for BTCUSDm (the store's digits, as in study 2). It is used in
  stop and target rounding, the 2-tick minimum risk and the step-stop threshold.
- **Times:** each bar's open and close time (the date window). The session filter is 24 hours and information only by
  default.
- **No higher timeframe** by default. If enabled, the HTF bars of section 12, trap 4.
- **History:** the warm-up is 165-267 bars. Entries start at 2020-01-01 by default, so data from 2016 / 2018 is plenty.

## 11. How a rule could trade it

**The script's own model (sections 6-7).**
- Entry at the signal close.
- Stop: the plan's stop, ATR × 2.5 on 4H, widened to the 11-bar structure minus 0.2 ATR, capped at 3.75 ATR.
- Targets at 1R, 2R and 3R; the stop steps to the entry after TP1 and to TP1 after TP2, from the next bar.
- All out at TP3, or reversed at the next opposite label.

**The video's protocol** (the same for all six indicators):
- the 4H chart with the preset left on Auto (EMA 13 / 34);
- the label on a closed candle, the entry at the next open, long and short;
- a stop 2 ATR away (1R), no target;
- the exit at the opposite label or the stop. The script's own stop and targets were not used.
- Add-on it tried: the 200 EMA, buys above and sells below.

**Rules a pre-registration could list (our readings, nothing tested):**
- **SNP-LS** (event rule):
  - the labels as the chart shows them (sections 7-8), including RE labels;
  - entry at the next M1 open after the label bar; stop 2·ATR; exit at the next opposite label or the stop;
  - one position. A same-side label while in a trade is ignored. After a stop, the next label of either side enters.
  - The plan must name the ATR: the script's own (20 on 4H) or the studies' ATR(14).
- **SNP-LO:** longs only. A Short label closes the long. The video found the shorts about break-even.
- **SNP-EMA200:** SNP-LS or LO with the video's filter: close > EMA(200) of the chart for longs, below for shorts, at
  the signal close (`E200` in `infra.md`). It is an EMA. The earlier studies' MA200 (an SMA) can run as F1 / F2 rows
  beside it.
- **SNP-M** (the script's model as an executable plan):
  - the plan's absolute stop, TP1-TP3, the step stops applied from the next chart bar (not the next M1 bar), all out
    at TP3, reversal on the opposite label;
  - the entry moves to the next open, so the study's absolute-level rules apply;
  - the plan must say whether "break-even" is the script's entry (the signal close) or the actual fill.
- **Grade rows:** the script's own alert options, labels of grade A+ only, or A+ and A.
- **Not recommended as rows:** the HTF filter (off by default), partial percentages (stats only), confirmation
  windows (a research option of the script).
- The default start date must be decided (trap 3) before any of these runs.

## 12. Traps for a port

| # | Item (lines) | Reading for both ports | The alternative | How much it matters |
|---|---|---|---|---|
| 1 | Labels depend on the internal trade (L575, L591, L609) | Port the whole model: phases 1-3 and the entry. The labels are what the chart shows | Emitting every accepted cross candidate | Material. Measure the difference (labels added or lost) during the reconciliation |
| 2 | The Auto preset (L130) | By seconds: <= 300 Scalping, <= 3600 Default, < 14400 Conservative, else Swing; **4H = Swing** | Reading "<4h" as including 4H | Everything on 4H |
| 3 | The default date window (L40, L306) | Entries only on bars opening at or after 2020-01-01 00:00 UTC. The model is idle before | Treating the start as display. Moving it to the data start is a **deviation** to pre-register: the label stream after 2020 then also changes, because the internal trade state differs | Decisive for any window before 2020: the reverse split's exam windows in `infra.md` (E2 entirely, E1 until 2020) would have no labels. Also the first trades of 2020 |
| 4 | The HTF request (L218-L219) | Off: an empty timeframe, although the mode says "Soft score". When on, each chart bar gets the HTF bar that had **closed by the chart bar's open** (the previous one), which is the harness's `tradeiq2_market.htf_at_open`. Its EMAs are computed on HTF closes; ready when that HTF bar's index >= slow length × warmupMult | The harness's `htf_at` (the HTF bar closing at or before the chart bar's **close**): on the last chart bar of each HTF bar it reads that HTF bar (k), where the script reads the one before (k − 1) | None by default |
| 5 | The VWAP anchor (L210) | The first chart bar of each study day (UTC) | TradingView's session day for the feed | Factor 6 on every intraday bar of gold |
| 6 | Volume (L209-L217, L243) | A pre-registration choice. The study harness's default (`tradeiq2_market` `Context.volume(tf, source="auto")`, study 2's PREREG 2) is tick volume for gold and Binance BTCUSDT volume for BTC; TradingView's Exness feed would show tick volume for both (`source="tick"`). hasVolume latches on the first confirmed bar with volume > 0 | No volume (scoreMax 5, two factors fewer) | Changes the evidence counts and the labels. Both BTC readings are worth a reconciliation count |
| 7 | Windows | volMean: bars t−20 .. t−1; priorHigh / priorLow: t−10 .. t−1; swingLow / swingHigh: t−10 .. t (11 bars) | Off by one | Material for factors 2 and 5 and for the stop |
| 8 | The evidence threshold (L493) | Rejected when evidence + 1e-9 < ratio × max, so an evidence equal to the product passes. Section 3 gives the minimum counts (4H: 5 of 7) | Comparing without the 1e-9 | None in practice. Scores are whole numbers, or halves with the HTF. A float64 check of every ratio (0.1-1.0, 0.65, 0.8) against every maximum (5, 6, 7, 6.5, 7.5, 8.5) found no product a hair away from a reachable score: each is either exact (0.6 × 5 = 3.0, 0.7 × 5 = 3.5) or between two scores. Keep the epsilon anyway |
| 9 | RSI band (L233, L489) | The band scales with sqrt(14 / length). A long is rejected at rsi >= upper (non-strict) | A fixed 70 / 30 | Material |
| 10 | Momentum (L587-L588) | A candidate without momentum is terminal (code 5), even when a higher-priority gate also failed | | Matters only with confirmWindow > 0 |
| 11 | One-bar candidates (L590) | confirmWindow 0: decided on their own bar; the cancel branch never acts | | |
| 12 | The stop plan (L283-L300) | Structure only widens; the cap is max(1.5 × ATR stop, 2 ATR); "Cap and flag" accepts capped plans | Structure tightening the stop; Skip entry | The internal trade, hence trap 1 |
| 13 | Tick rounding (L186-L187, L284-L297) | Work in integer ticks: k_e = round(close / tick); the stop k = floor(bounded / tick + 1e-8) (long) or ceil(bounded / tick − 1e-8) (short), with bounded / tick in float64 exactly as written; k_p = k_e + d·k_risk·m for the default whole multipliers m (for a non-whole m an exact half tick can occur; then compute e + d·risk·m in float64 as written and round half up, because Pine's float noise decides that case). Prices as floats are k / 10^digits | Raw float arithmetic: k·0.001 differs from k / 1000 in the last bit for about 13% of gold prices (scratch check). Without the 1e-8 nudge a level a hair below a tick drops a whole tick | Exact ties at the stop and targets are common with tick prices |
| 14 | Comparisons of tick prices (L513-L516, L625) | In integer ticks: low <= stop, high >= target, open <= stop for the gap, the step move >= 1 tick. The author's comment (L141) says Pine rounds comparison operands to 9 decimals, which integer ticks reproduce for tick-valued operands | Raw float compares of a computed level with a data price | Decides touches on exact ties |
| 15 | Phase 1 order (L510-L546) | No check on the entry bar; stop first; the gap fill at the open; targets with >=; several targets on one bar; TP3 closes all | Targets first; checking the entry bar | The internal trade, hence trap 1 |
| 16 | The step stop (L623-L629) | Moved in phase 3, effective from the **next** bar; after TP1 to the entry (the signal close), after TP2 to TP1; it moves only if it improves by more than 0.1 tick | Immediate moves inside the bar | Same |
| 17 | Reversal (L619-L620, L675) | On an accepted opposite label: exit at the close, then the new entry at the same close | | |
| 18 | Re-entries (L572-L581, L602-L603) | Section 7, phase 2, step 3: after an accepted trade of this cycle closed; at most 1 accepted per cycle; rejected attempts do not count; possible on the stop bar | Re-entry after any close; counting attempts | Adds "RE" labels |
| 19 | The cycle reset (L558-L561) | On every cross, before warm-up and outside the window too | Only on candidate crosses | Re-entry eligibility |
| 20 | ADX (L207, L240) | Study 2's DMI reading (the true range na on bar 0, `fixnan`, the s = 0 guard); trending = adx >= 20; always 14 / 14 | `ta.tr(true)`; a tie given to +DM | Study 2 measured 1e-14-level differences and a few flips of the 20 threshold |
| 21 | MACD (L206) | Fixed 12 / 26 / 9 on the price source; readiness needs hist[t−1] | Preset lengths | |
| 22 | How the EMA starts | The first value (the studies' convention) | The SMA start (TradingView's apparent behaviour). It changes the first few hundred bars: EMA(89) on 4H keeps about 0.25% of the start's difference after the 267-bar warm-up | None after 2020 with data from 2016 / 2018; matters only if the start date moves to the data start (trap 3) |
| 23 | The script's ATR | Preset ATR: 20 on 4H / 1D, 14 on 1H / M15, 10 on M5 | The studies' ATR(14) | The internal stop and the volatility gate |
| 24 | Bar counting | warmed counts from the first bar of our data | TradingView counts from the first loaded bar | None after warm-up |
| 25 | Session (L302-L305) | "0000-0000" on days 1-7 is the whole day; info only | | None |
| 26 | Statistics (L346-L386, L631-L671) | Only if the dashboard is to be checked: R = ((fraction·dir)·(px − entry)) / risk with risk = abs(e − stop) in float64; win if net R > 1e-8, loss if < −1e-8 | | Not signal-relevant |
| 27 | TradingView's label budget (L8) | 500 labels, entries and exits together, so only the latest ~250 trades are visible on a chart | | Visual checks against TradingView only |
| 28 | Gold's bars (study convention) | UTC 4H and D boundaries | TradingView's gold session | The 4H bars, the VWAP anchor and the prior-day levels differ from TradingView's |
| 29 | Evidence model | v2 (the default) | v1: the video's spoken list (trend, RSI, MACD, ADX, volume) matches v1's names, but the video says it kept the defaults | A sensitivity row at most |

## 13. Hand-checkable test cases

All of these run on synthetic bars or on the plan and engine functions directly. Make the preset lengths, the start
date and the tick parameters so they stay small.

- **H1, the profile.** Auto at 300, 900, 3600, 7200, 14400 and 86400 seconds gives Scalping, Default, Default,
  Conservative, Swing and Swing. vwapEnabled is true intraday, false at 86400.
- **H2, the thresholds.** The minimum factor counts of section 3. With volume off (scoreMax 5) and ratio 0.6, an
  evidence of exactly 3 passes (0.6 × 5 = 3.0 in float64) and 2 fails. On 4H with volume, 4 of 7 fails and 5 passes.
- **H3, rounding (tick 0.001).**
  - roundDown(1999.9999999999998) = 2000.000 (without the nudge, 1999.999);
  - roundUp(2000.0000000000002) = 2000.000 (without it, 2000.001);
  - roundDown(1999.9995) = 1999.999. (Checked in float64 on 28 Nov 2026.)
- **H4, the stop plan (Swing preset).** A long where the 11-bar low − 0.2 ATR lies below e − 2.5 ATR is widened to it. Below
  e − 3.75 ATR it is capped at e − 3.75 ATR, still valid, and the origin says "capped". A structure stop above the
  ATR stop is ignored.
- **H5, stop first.** A bar whose low touches the stop and whose high touches TP1 closes the trade at the stop, and
  hit1 stays false. A bar that opens below a long's stop fills at the open.
- **H6, the step stop.** TP1 touched on bar k moves the stop to the entry from bar k + 1. A low at the entry price on
  bar k itself does not stop the trade; the same low on bar k + 1 does ("Step stop", about 0R).
- **H7, suppression.**
  - Bull cross accepted (long open), bear cross rejected (for example on the RSI band), the long survives, the next
    bull cross: no label, reason "Same direction already open".
  - If the long had been stopped on that very bar before the cross: a label.
- **H8, re-entry.**
  - Long accepted on a bull cross and stopped. Later, close crosses back above the fast EMA while fast > slow: a "Long
    RE" candidate, gated as usual. A second re-entry in the same cycle is refused.
  - A rejected first re-entry leaves the allowance unused.
  - A bull cross that was itself rejected gives no re-entry in that cycle.
- **H9, the date window.** No candidate on a bar opening before the start, even with a cross. The cycle state still
  updates.
- **H10, reversal.** An accepted Short label while a long is open: the long exits at that close and the short enters
  at the same close (two events in one alert batch).
- **H11, windows.** volMean excludes bar t; priorHigh excludes bar t; swingLow includes bar t (one test each with the
  extreme on bar t).
- **H12, VWAP.** The anchor resets on the first bar of a new day; the first bar's VWAP equals its hlc3.
- **H13, readiness.** No label before warmupBars, nor while volMean is 0 with hasVolume true.

## 14. Porting effort

- **Indicators** (L199-L249, L277-L281): about 60 lines. All primitives exist in the repository except the session
  VWAP and the shifted highest / lowest (trivial).
- **Evidence, plan, gate** (L250-L300, L474-L501): about 90 lines, the tick logic included.
- **Engine** (L507-L686 without the alert and label text): about 130 lines. A sequential loop over bars with a small
  state; numba-friendly.
- **Statistics** (phase 4, L346-L386): about 50 lines. Needed only to check the dashboard's numbers.
- **Not ported:** inputs, the display helpers, the alert texts and JSON (L387-L408, L502-L505, L688-L715), the levels
  and the dashboard (L717-L1023).
- **Estimate:** two to three days per port, one day of reconciliation.
  - The risky parts are traps 1, 3, 13-18 and the VWAP anchor.
  - Every decimal is either a primitive's output, one of the plan's few operations in the written order, or a tick
    multiple. Bit-for-bit agreement is realistic.

## 15. What the video says about it (paraphrased, for a later claims list)

- Ranked fourth of six; published in March 2026. Per trade about 2.7 times the SuperTrend baseline, and the most per
  year of the six: about 9R a year per market.
- 1,987 trades on 11 markets (4H, January 2021 to October 2026), 26% winners, profit factor 1.42; 6.5R a year with
  costs doubled.
- Without its five best trades still almost 300R across the markets. Nine of 11 markets profitable, gold 1.6; the only
  one of the six above water on the NASDAQ.
- The longs made nearly all the profit; the shorts about broke even. The worst run was 20 losses in a row (XRP).
- Recommended use: leave the preset on Auto and add the 200 EMA (buys above, sells below). That took the profit
  factor from 1.42 to 1.59, with 10 of 11 markets profitable.
- With costs doubled it lost 27% of its profit, against 55% for SuperTrend.
