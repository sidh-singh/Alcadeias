# Profit Maximizer (PMax), KivancOzbilgic: porting spec (study 4, TradeIQ video 3, script #3 of the video)

Written 28 Nov 2026 from the owner's copy, before any port, rule or backtest exists. Nothing here was run on market
data. Third-party code: it is restated below in formulas and plain words, never copied.

- **Source file:** `/Users/sidharthsingh/Desktop/study/trend/Profit Maximizer Strategy.rtf`
  (sha256 of the RTF `34460a3e8b133f036fb42fe621aef90e0f840946124b418a9b9bff09ae2e3c13`).
- **Plain-text copy used for line numbers (L..):** `textutil -convert txt -stdout "<file>"`, numbered from 1
  (sha256 of that text `5ef56134131f40a0cbc1088a6dc3ec5f826cc8de200683976358d32a0657c9be`). Content is on L1-L105.
- **Author:** KivancOzbilgic (developer and author lines, L3-L5). Licence: MPL-2.0 (L2).
- **Pine version:** v4 (L1). Declared as a study (an indicator, not a strategy), overlay, short title "PMax",
  display precision 2 and an (empty) resolution argument (L7).
- **Despite the file name it is not a strategy:** there are no orders, no strategy properties and no backtest of its
  own. It draws two lines, two kinds of labels and offers six alert conditions.
- **Module key:** `pmax` (as proposed in `infra.md` of this folder). It shares the band mechanics, but not the tests,
  with the classic SuperTrend of `spec_st.md`: see traps 2, 3 and 14.

## 0. Bottom line

- PMax is a SuperTrend whose bands hang on a moving average instead of on price: two ATR bands around a 10-bar EMA of
  the bar midpoint (hl2), a ratchet that only lets each band move in its trend's favour, and a direction that flips
  when **the EMA itself** (not price) crosses the band of the previous bar.
- The visible Buy / Sell labels are the crosses of the EMA and the PMax line. Whenever the ATR is above zero they are
  exactly the bars where the direction flips (section 3, invariant I1). The indicator is therefore always in the
  market: every Sell closes the long and opens a short, every Buy the reverse.
- **Timing:** every value uses only the current and earlier bars of the chart timeframe. No `security`, no pivots, no
  look-ahead. A label is final at the close of its bar. Only the forming bar can flicker in real time.
- **Data:** OHLC of the chart timeframe. No volume, no higher timeframe, no session.
- **Effort:** about 15 computing lines at the defaults (about 45 with all eight average types). Hours per port. The
  repository's study-1 primitives (`backtesting/research/tradeiq_ind.py`: `ema`, `atr`, `crossover`) already implement
  the arithmetic the defaults need.

## 1. Inputs and defaults (L8-L18)

| Input (title) | Variable | Type | Default | Used by the computation? |
|---|---|---|---|---|
| Source | `src` | source | **hl2** = (high + low) / 2 | yes: the average and the price-cross signals |
| ATR Length | `Periods` | int | **10** | yes |
| ATR Multiplier | `Multiplier` | float (step 0.1) | **3.0** | yes |
| Moving Average Type | `mav` | string; SMA, EMA, WMA, TMA, VAR, WWMA, ZLEMA, TSF | **EMA** | yes |
| Moving Average Length | `length` | int, min 1 | **10** | yes |
| Change ATR Calculation Method ? | `changeATR` | bool | **true** (Wilder ATR) | yes |
| Normalize ATR ? | `Normalize` | bool | **false** | yes (non-default branch) |
| Show Moving Average? | `showsupport` | bool | true | display |
| Show Crossing Signals? | `showsignalsk` | bool | true | display (the EMA / PMax labels) |
| Show Price/Pmax Crossing Signals? | `showsignalsc` | bool | **false** | display (price / PMax labels) |
| Highlighter On/Off ? | `highlighting` | bool | true | display (fill colours) |

The study's resolution argument is empty (L7): the script runs on the chart's own timeframe. TradingView then offers
a timeframe field in the settings; a non-empty value would run the whole script on that timeframe. Not the default and
not part of the port.

## 2. Pine primitives the port must reproduce (v4 names, v5/v6 equivalents)

All series are indexed by bar t = 0, 1, 2, ... from the first bar of the loaded data. `x[k]` is the value k bars back
and is na for t < k. A comparison involving na is false. `nz(a, b)` is b when a is na. `max` / `min` are na if
either argument is na.

| Primitive | Definition used by both ports | Notes |
|---|---|---|
| `hl2` | (high + low) / 2, added first, then divided | |
| `atr(n)` (= `ta.atr`) | Wilder average of the true range with `tr(true)`: TR[0] = high − low; TR[t] = max(max(high − low, abs(high − close[t−1])), abs(low − close[t−1])). ATR is na for t < n − 1; ATR[n−1] = SMA of TR[0..n−1]; then ATR[t] = (1/n)·TR[t] + (1 − 1/n)·ATR[t−1] | Pine reference `pine_atr` / `pine_rma`; `tradeiq_ind.atr` |
| `sma(x, n)` | the reference order: the sum over i = 0 (this bar) .. n−1 of x[t−i] / n | `tradeiq_ind.sma`; na until n values exist |
| `tr` (the variable) | as TR above, but **na on bar 0** (`tr(false)`) | used only by the non-default ATR branch |
| `ema(x, n)` | alpha = 2 / (n + 1); EMA[t] = alpha·x[t] + (1 − alpha)·EMA[t−1] | the start: section 8, trap 7 |
| `crossover(a, b)` | a[t] > b[t] and a[t−1] <= b[t−1]; false if any of the four is na | `tradeiq_ind.crossover`; `crossunder` is the mirror; `cross` = either |

Every multiplication and division is done in the script's left-to-right order (for example the normalized band
offset is (Multiplier·ATR) / close, the product first). That is what makes two ports equal bit for bit.

## 3. The computation on each bar, in order

At the defaults only steps 1-7 matter. Steps 2b-2g are computed on every bar by the script (L21-L38) but feed nothing
unless another average type is chosen.

1. **ATR (L19-L20).**
   - `changeATR` true (default): ATR = Wilder ATR(10) as in section 2. First value on bar 9.
   - `changeATR` false: ATR = SMA(`tr`, 10) with `tr` na on bar 0, so the first value is on bar 10 (TR of bars 1-10).
2. **The average MAvg (L39-L74).** `getMA` returns one of eight series; the input picks which. The choice is constant
   over the chart, so every branch's built-in functions run on every bar and keep consistent memory.
   - a. **EMA (default):** EMA(hl2, 10).
   - b. SMA: SMA(hl2, 10).
   - c. WMA: the reference WMA(hl2, 10) (`tradeiq_ind.wma`).
   - d. TMA: SMA(SMA(hl2, ceil(length / 2)), floor(length / 2) + 1), so SMA(SMA(hl2, 5), 6) at length 10.
   - e. VAR (a VIDYA, L21-L28): up = hl2 change if positive else 0, down = the mirror (both 0 on bar 0, because a
     comparison with na is false); vUD, vDD = their sums over **9** bars (fixed 9, not `length`);
     CMO = nz((vUD − vDD) / (vUD + vDD)), so 0 while the sums are na and when both are 0;
     a = (2 / (length + 1))·abs(CMO); VAR[t] = nz(a·hl2) + (1 − a)·nz(VAR[t−1]). It starts from 0, not from price.
   - f. WWMA (L29-L31): w = 1 / length; WWMA[t] = w·hl2 + (1 − w)·nz(WWMA[t−1]); also starts from 0.
   - g. ZLEMA (L32-L34): lag = length / 2 when that is a whole number, else (length − 1) / 2, so floor(length / 2)
     under either division reading (5 at length 10); ZLEMA = EMA(hl2 + (hl2 − hl2[lag]), length).
   - h. TSF (L35-L38): lrc0 = linreg(hl2, length, 0), lrc1 = linreg(hl2, length, 1); TSF = lrc0 + (lrc0 − lrc1).
     Pine's `linreg(x, n, off)` is intercept + slope·(n − 1 − off) of the least-squares line over the last n values.
3. **Raw bands (L75, L78).** With `Normalize` false (default):
   - longRaw[t] = MAvg[t] − (3.0·ATR[t]); shortRaw[t] = MAvg[t] + (3.0·ATR[t]).
   - With `Normalize` true the band offset is (3.0·ATR[t]) / close[t]: a distance of a few thousandths of a price unit,
     so the bands sit almost on the average. It is the script's literal arithmetic; do not "fix" it.
4. **The previous bands (L76, L79).**
   - longPrev[t] = longStop[t−1] if it is not na, else longRaw[t]. shortPrev the same with shortStop.
   - `longStop[t−1]` is the **final** value of the previous bar, after its ratchet (step 5). It is not the previous
     raw band.
5. **The ratchet (L77, L80).**
   - longStop[t] = max(longRaw[t], longPrev[t]) when MAvg[t] > longPrev[t], else longRaw[t].
   - shortStop[t] = min(shortRaw[t], shortPrev[t]) when MAvg[t] < shortPrev[t], else shortRaw[t].
   - The test uses the **current** MAvg against the previous band. The classic SuperTrend uses the previous close.
   - Both bands are updated on every bar, whatever the direction.
6. **Direction (L81-L83).** dir has no `var`; it is rebuilt each bar from its own history, which makes it persistent:
   - start: d = dir[t−1], or 1 on bar 0 (nz of na with the freshly declared 1);
   - if d = −1 and MAvg[t] > shortPrev[t], dir[t] = 1;
   - else if d = 1 and MAvg[t] < longPrev[t], dir[t] = −1;
   - else dir[t] = d.
   - Both tests are strict and use the **previous** bar's bands (longPrev, shortPrev), not this bar's ratcheted bands.
   - During the warm-up the bands are na, the tests are false, and dir stays 1.
7. **The PMax line (L84).** PMax[t] = longStop[t] if dir[t] = 1, else shortStop[t].
8. **Signals (L93, L95, L97, L99).**
   - Buy = crossover(MAvg, PMax); Sell = crossunder(MAvg, PMax). These are the labels shown by default.
   - Price Buy = crossover(src, PMax); Price Sell = crossunder(src, PMax), with src = **hl2** (not the close). Hidden by
     default; they also have alert conditions.

**Invariant I1 (assert it on every bar in both ports).** If ATR[t] > 0 and the bands are not na:
- dir[t] = 1 implies PMax[t] < MAvg[t] strictly: longRaw is below MAvg, and the ratchet takes longPrev only when MAvg
  is above it.
- dir[t] = −1 implies PMax[t] > MAvg[t] strictly.
- Hence Buy[t] holds exactly when dir[t−1] = −1 and dir[t] = 1, and Sell[t] exactly when dir[t−1] = 1 and dir[t] = −1.
  The labels are the direction flips.
- The first bar with a PMax (bar 9 at the defaults) has dir = 1 and never carries a label, because PMax[8] is na and
  the crossover is false.

**Warm-up at the defaults:** ATR from bar 9, MAvg from bar 0 (or bar 9 with the SMA start of the EMA), PMax from bar
9. The EMA's start fades by a factor 9/11 per bar: below 1e-8 of the initial gap after about 92 bars.

## 4. Outputs and when each is known

| Output | Lines | Definition | Known at | Repaint |
|---|---|---|---|---|
| "Moving Avg Line" (blue) | L85 | MAvg | close of bar t | none after the close (it moves with the forming bar's high and low) |
| "PMax" line (red) | L86 | PMax | close of bar t | as above |
| Buy / Sell labels | L94, L96 | the flips (I1), drawn on bar t at PMax·0.995 / PMax·1.005 (display offsets only) | close of bar t | none after the close; in real time a label can appear and vanish while the bar forms |
| Price Buy / Sell labels (off) | L98, L100 | crosses of hl2 and PMax | close of bar t | as above |
| Trend fills | L101-L105 | green while MAvg > PMax, red while below, between PMax and an invisible ohlc4 plot | close of bar t | display only |
| Alert conditions | L87-L92 | "Cross Alert" (either cross of MAvg and PMax), "Crossover Alarm" (Buy), "Crossunder Alarm" (Sell), and the three hl2 / PMax equivalents | per the user's alert frequency; at the bar close with "once per bar close" | an intrabar alert can fire for a cross that is gone at the close |

## 5. Repaint and look-ahead audit

- No `security` call, no `lookahead`, no pivots, no arrays, no labels moved back in time, no machine learning.
- Every input of bar t's value is from bar t or earlier: hl2[t], close[t−1] inside the true range, and the previous
  bands and direction.
- The only repainting is the ordinary forming-bar kind: hl2 and the true range change with every tick until the close.
- The non-default resolution setting of the study (L7) would run the script on another timeframe through TradingView's
  own mechanism. Not part of any rule.

## 6. Data needed

- OHLC of the chart timeframe: high and low for hl2 and the true range, close for the true range's previous close.
  Open is not used.
- No volume, no higher timeframe, no session, no symbol tick size (the script never rounds; precision 2 is display
  formatting only).
- History: about 10 bars for the first value; start the series at the data start so the EMA's start has faded long
  before any window.

## 7. How a rule could trade it

**What the script itself implies (L94-L100, the fills):** an always-in-the-market stop-and-reverse. Long from a Buy,
short from a Sell; each label reverses. The PMax line is the trailing level that the average, not price, must cross.

**The video's protocol (its section on the test, used for all six indicators):**
- the 4H chart and the defaults (ATR 10, multiplier 3, the 10-bar EMA);
- a signal on a closed candle and the entry at the next candle's open, long and short;
- a stop 2 ATR from the entry, which is 1R; no target;
- the exit at the opposite signal or the stop.
- Because the labels alternate, after a stop the next label is always of the other side, so a stopped long cannot
  re-enter until a Sell and a Buy have passed.

**Rules a pre-registration could list (our readings, nothing tested):**
- PMAX-LS (event rule): the video's protocol above. Stop: 2·ATR. Which ATR the video meant is not said; the
  candidates are the script's own ATR(10) or the study's usual ATR(14). The plan must name one.
- PMAX-LO: buys only; a Sell closes the long and waits. The video recommends this for coins and gold.
- PMAX-SAR (state rule, S0): long while dir = 1, short while dir = −1, no stop (the script's own logic).
- Filter "daily EMA50 agreement" (the video's add-on): longs only when the daily trend agrees. It is ambiguous, so the
  plan must pick a reading, for example:
  - (a) the decision close above the EMA(50) of the last closed D1 bar;
  - (b) the last closed D1 close above its own EMA(50);
  - (c) the EMA(50)'s slope.
  - `infra.md` names the filter `D50`, the side of the daily EMA(50) of the last closed 1D bar. Whether it compares
    the decision close, as in (a), or the daily close, as in (b), still has to be fixed.
  Note that it is an EMA, unlike the earlier studies' MA200, which is an SMA.
- The earlier studies' filters (F1, F2 with MA200 = SMA 200, F3, FR, FS) can be applied unchanged as event filters at
  the entry.
- Variant: the price-cross signals (hl2 crossing PMax) as an earlier exit of the label trades.

## 8. Traps for a port

| # | Item (lines) | Reading for both ports | The wrong or alternative reading | How much it matters |
|---|---|---|---|---|
| 1 | The previous band (L76-L80) | `longStop[t−1]` is the previous bar's **final** (ratcheted) value; it falls back to the current raw band only while na | Using the previous raw band | Every bar after the first ratchet. Hand test H1 |
| 2 | The ratchet's test (L77, L80) | The current MAvg against the previous band | close[t−1] or MAvg[t−1] (the classic SuperTrend) | Changes the bands after every pull-back. H1, bar 3 |
| 3 | The flip test (L83) | The current MAvg against the **previous** bands, strict | Against this bar's ratcheted bands | Changes flips. H1, bar 3: with this bar's band the sell would not happen |
| 4 | The direction's start (L81-L82) | 1 on bar 0; it stays 1 while the bands are na | Starting at 0 or na; a label on the first PMax bar | The first bars only. No label on bar 9 |
| 5 | Labels = flips (L93-L96) | Assert invariant I1 on every bar; use the flips as the signal | Recomputing crosses with other na rules | None if I1 holds. A failure of I1 means a bug |
| 6 | The source (L8) | hl2 for the average **and** for the price-cross signals | The close | Changes everything |
| 7 | How `ema` starts | First value (`pine_ema`; study 1's PREREG 5, `tradeiq_ind.ema(seed="first")`) | The SMA of the first 10 values (what TradingView's runtime appears to do; study 1 found the choice immaterial) | Below 1e-8 after about 92 bars. The direction path can differ only in the first days of the data |
| 8 | ATR (L19-L20) | Wilder RMA of `tr(true)`: TR[0] = high − low, an SMA start on bar 9 | The `tr` variable (na on bar 0) belongs only to the `changeATR` false branch, which is an SMA starting on bar 10 | First bars only, or a different ATR family if the branch is misread |
| 9 | Normalize (L75, L78) | (3·ATR) / close when true (non-default) | "Fixing" it into a percentage of price | Non-default only |
| 10 | Division in Pine v4 (L21, L29, L32, L54) | Input integers divide as floats (only literal pairs truncate), and the history operator floors a float offset. So 2 / 11, 1 / 10, lag 5, TMA 5 and 6 | Integer division: VAR and WWMA would collapse to 0, and an odd TMA length would change | None at the defaults (EMA). Only for VAR, WWMA and odd-length TMA |
| 11 | VAR and WWMA start from 0 (L28, L31) | As written (nz of the previous value is 0) | Starting from price | Non-default only: a warm-up of a few hundred bars |
| 12 | Conditional built-ins inside `getMA` (L39-L72) | Fine, because the type is an input that is constant over the chart | n/a | None |
| 13 | Precision 2 (L7) | Display formatting only; no rounding anywhere | Rounding MAvg or PMax to 2 decimals | Would change BTC and gold signals |
| 14 | Reusing a SuperTrend helper (`ladder_ind.supertrend`, `external.supertrend`) | Do not: PMax's ratchet and flip tests differ (traps 2 and 3), and its dir = +1 means up | Pine's `ta.supertrend` returns direction −1 for an uptrend, the opposite sign convention | Everything |
| 15 | MTF resolution (L7) | Not used (empty = chart timeframe) | | |

## 9. Hand-checkable test cases

**H1, bands and direction from given MAvg and ATR** (feed the band function directly: multiplier 3, ATR = 1.0 on every
bar, Normalize false, dir starting at 1):

| t | MAvg | longRaw | longPrev | longStop | shortRaw | shortPrev | shortStop | dir | PMax | Label |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 100.0 | 97.0 | 97.0 (fallback) | 97.0 | 103.0 | 103.0 (fallback) | 103.0 | 1 | 97.0 | none |
| 1 | 101.0 | 98.0 | 97.0 | 98.0 | 104.0 | 103.0 | 103.0 | 1 | 98.0 | none |
| 2 | 99.5 | 96.5 | 98.0 | 98.0 (ratchet holds) | 102.5 | 103.0 | 102.5 | 1 | 98.0 | none |
| 3 | 97.9 | 94.9 | 98.0 | 94.9 (reset) | 100.9 | 102.5 | 100.9 | −1 | 100.9 | Sell |
| 4 | 99.0 | 96.0 | 94.9 | 96.0 | 102.0 | 100.9 | 100.9 | −1 | 100.9 | none |
| 5 | 101.5 | 98.5 | 96.0 | 98.5 | 104.5 | 100.9 | 104.5 (reset) | 1 | 98.5 | Buy |

- Bar 3 is the trap of items 1-3. The flip happens because 97.9 < longPrev = 98.0. This bar's own long band (94.9) is
  below the average, so a port that tests the current band misses the Sell.
- Bar 5: the Buy happens because 101.5 > shortPrev = 100.9, although this bar's raw short band is 104.5.
- (Computed on 28 Nov 2026 with a five-line scratch check of these formulas; decimals as printed by float64, for
  example 94.9 = 97.9 − 3.0.)

**Other tests each port should carry:**
- H2: hl2 as the source. A bar whose close is far from its midpoint must move MAvg by alpha·(hl2 − EMA[t−1]).
- H3: the ATR start. TR[0] = high − low; ATR[9] = the mean of TR[0..9] in the reference order; ATR[10] = 0.1·TR[10] +
  0.9·ATR[9].
- H4: invariant I1 on a long synthetic random walk: labels equal flips on every bar, and no label on the first PMax bar.
- H5: the first PMax bar is 9 and dir is 1 there.

## 10. Porting effort

- **Lines that compute at the defaults:** L19-L20 (ATR), the EMA branch of L39-L74, L75-L84 (the bands and the
  direction), L93-L99 (signals): about 15 lines.
- **With all eight average types:** about 45 lines, plus a `linreg` helper for TSF.
- **Display only:** L85-L86, L94-L100 (label placement), L101-L105.
- **Estimate:** 2-4 hours per port with the study-1 primitives, and under an hour of reconciliation. Every decimal is
  an EMA, an RMA, or one addition or subtraction of them.

## 11. What the video says about it (paraphrased, for a later claims list)

- Ranked third of six, from 2020, by the author of the SuperTrend script the video tested.
- Per trade about 3.4 times the SuperTrend baseline: 1,369 trades on 11 markets on the 4H chart from January 2021 to
  October 2026, 26% winners, profit factor 1.49, almost 8R a year per market, 5.9 with costs doubled.
- Always in the market. The shorts lost money. Much stronger in the older half of the data (1.81 against 1.2 in the
  newer half). 2025 was a losing year.
- Recommended use: trade the buys on coins and gold on the 4H chart with the defaults; check the daily chart first.
  When the signal agreed with the daily 50 EMA, the profit factor was 1.63, and 1.53 in the newer half.
