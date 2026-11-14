# Support and resistance from the higher timeframes: does price react there, and can it be traded?

Gold (XAUUSDm) and BTC (BTCUSDm), M1 bid bars built from the Exness ticks. Two periods: **DEV**, 1 Aug 2025 to
12 Nov 2026, on which every definition was chosen, and **CONFIRM**, 1 Feb 2024 to 29 Jun 2025, on which the
finished code was then run once. Code: `backtesting/research/sr.py`; tests: `tests/test_sr_levels.py`.

## 1. The answer

**No. Price comes to these levels, but it does not hold at them more often than at any other price; it holds a
little less often. None of five trades built on the levels makes money after the spread in both periods on
either symbol, and no kind of level or state of the market changes that. The study supports no support /
resistance rule for the engine.**

|  | Gold, DEV | Gold, CONFIRM | BTC, DEV | BTC, CONFIRM |
|---|---|---|---|---|
| Approaches to a level, per quarter | 709 | 602 | 1221 | 1253 |
| Turned back 1 ATR before going 0.5 ATR through it: at the levels | 34.9 % | 33.6 % | 35.5 % | 35.2 % |
| ... at control prices | 37.7 % | 37.7 % | 36.8 % | 40.1 % |
| ... a coin with these distances | 37.5 % | 37.5 % | 37.5 % | 37.5 % |
| Difference levels minus control, points (95 %) | -2.8 [-6.4, +0.9] | **-4.1 [-6.9, -1.5]** | -1.2 [-4.6, +1.8] | **-4.9 [-8.0, -2.5]** |
| Pulled back 0.5 ATR before going 1 ATR through it: levels / control | 67 % / 69 % | 66 % / 69 % | 67 % / 69 % | 68 % / 72 % |
| Bounce trade: ATR per trade after spread (95 %) | **-0.047 [-0.075, -0.020]** | **-0.085 [-0.106, -0.064]** | **-0.060 [-0.079, -0.039]** | **-0.108 [-0.124, -0.091]** |
| ... USD per trade / per quarter, 0.01 lot | -0.92 / -652 | -0.62 / -376 | -0.20 / -247 | -0.53 / -666 |
| Rejection trade: ATR per trade after spread (95 %) | -0.026 [-0.074, +0.021] | -0.019 [-0.073, +0.030] | **-0.074 [-0.111, -0.037]** | **-0.094 [-0.129, -0.059]** |
| ... USD per trade / per quarter, 0.01 lot | -0.20 / -66 | -0.28 / -81 | -0.38 / -238 | -0.44 / -277 |
| Retest: ATR per trade after spread (95 %) | -0.022 [-0.084, +0.037] | -0.023 [-0.061, +0.013] | +0.008 [-0.031, +0.046] | **-0.088 [-0.127, -0.054]** |
| ... USD per trade / per quarter, 0.01 lot | +0.00 / +1 | -0.26 / -54 | +0.11 / +36 | -0.42 / -125 |
| Through trade: ATR per trade after spread (95 %) | -0.003 [-0.035, +0.028] | -0.010 [-0.037, +0.017] | **-0.032 [-0.056, -0.011]** | **-0.053 [-0.070, -0.036]** |
| ... USD per trade / per quarter, 0.01 lot | +0.08 / +53 | +0.08 / +51 | -0.23 / -282 | -0.29 / -366 |
| Breakout trade: ATR per trade after spread (95 %) | -0.019 [-0.062, +0.021] | +0.009 [-0.030, +0.047] | -0.023 [-0.058, +0.008] | **-0.063 [-0.090, -0.035]** |
| ... USD per trade / per quarter, 0.01 lot | -0.63 / -364 | +0.15 / +70 | -0.16 / -156 | -0.35 / -355 |

Bold: the 95 % interval excludes zero. The ATR is that of H1 bars; "control prices" are the same map of levels
moved to where it marks nothing (section 3.4).

- **The levels do not hold.** When price came back to a level from at least an ATR away, it turned and
  travelled one ATR before going half an ATR through the level in 34 to 36 % of approaches, in both periods and
  on both symbols. At control prices, approached by the same market in the same weeks, the figure is 37 to
  40 %; a coin with those distances gives 37.5 %. The difference is against the levels in all four columns and
  beyond chance on CONFIRM.
- **So the bounce trade loses, and by more than the spread.** Buying every support and selling every
  resistance at the touch lost 0.05 to 0.11 ATR per trade: 0.03 to 0.06 ATR before the spread, the rest the
  spread itself. It lost in each of the six half-years on both symbols. On a 0.01 lot that is 0.2 to 0.9 USD a
  trade, or 250 to 670 USD a quarter if every touch is taken.
- **Nothing makes a level work** (sections 4.2 and 4.3). Not the timeframe: zones with an H4 or D1 swing or a
  day / week high or low did worse than plain H1 swings. Not confluence, not the first touch, not agreement
  with the H4 and D1 trend, not a stretched RSI, not an RSI divergence, not a slow approach, not a ranging
  market, not the session. On CONFIRM every one of the 46 rows of that table is negative on both symbols.
- **Waiting for the level to hold does not help** (4.4). Entered only after an M15 bar has closed half an ATR
  back from the level, the trade wins as often as it loses and pays the spread. The retest of a broken level
  from its other side is no better.
- **The other side does not pay either** (4.5). A level is run through a little more often than a control
  price, by 3 to 5 points in all four columns. That is the one regularity that repeats, and it is worth less
  than the spread: trading through the level at the touch made between -0.05 and 0.00 ATR per trade, and
  trading the break after an M15 close beyond it between -0.06 and +0.01.
- **A stop behind a level is not protected by it.** That is the same fact read from the other side: a stop
  half an ATR behind a level was reached first in 65 / 66 % of gold's approaches (DEV / CONFIRM) and 64 / 65 % of
  BTC's, against 62 / 62 % and 63 / 60 % at the same distance behind a price that marks nothing.
- **What looked like something on DEV did not repeat** (4.6). Three rows of 334, all in gold, met the profit
  half of the rule set beforehand; none met it again on CONFIRM. No row has a profit interval above zero in
  both periods; 96 have it below zero in both. What remains is a pair of hypotheses about gold on the through
  and breakout side, stated in 4.6 for a period that has not been looked at.

Section 2 explains why a chart nevertheless looks as if the levels worked. The level detector itself is
delivered and tested for look-ahead (section 7), so any other idea about levels can be tried on it.

## 2. Why a chart says otherwise

Anyone who marks H1, H4 and D1 levels on a chart sees price turn at them. That observation is correct, and two
base rates explain it without any edge.

**Levels are everywhere.** With the swings of three timeframes, yesterday's and last week's high, low and close
and the round numbers on the chart, the nearest support and the nearest resistance are each about 0.7 ATR from
price at a typical moment in gold and 0.5 ATR in BTC (DEV). So four to six in ten of all turning points of the H1
chart lie within a quarter of an ATR of a level that was already drawn (gold 53 / 44 %, BTC 56 / 59 %; DEV / CONFIRM).
That is what the eye collects. But 43 / 36 % and 53 / 55 % of *all* hourly highs and lows lie that close to a
level, turning point or not. What matters is how often a high or low at a level goes on to become a turning
point. That is about as often at the real levels (gold 11.7 / 11.8 %, BTC 10.7 / 10.8 %) as at the lines of the
control maps, the same levels moved to where they mark nothing (11.3 / 12.1 % and 11.8 / 11.4 %): less often in
seven of the eight comparisons of the two tables, more often in one.

**Gold**

|  |  | DEV: bar highs and lows | DEV: of them at a level | DEV: turning points | DEV: of them at a level | DEV: became a turning point: at a level | DEV: elsewhere | CONFIRM: bar highs and lows | CONFIRM: of them at a level | CONFIRM: turning points | CONFIRM: of them at a level | CONFIRM: became a turning point: at a level | CONFIRM: elsewhere |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 bars | real levels | 15172 | 43.1% | 1448 | 52.7% | 11.7% | 7.9% | 16582 | 35.9% | 1605 | 43.6% | 11.8% | 8.5% |
| H1 bars | control maps | 15172 | 37.9% | 1448 | 44.9% | 11.3% (11.1 to 11.5) | 8.5% | 16582 | 26.0% | 1605 | 32.6% | 12.1% (11.1 to 12.7) | 8.8% |
| H4 bars | real levels | 4100 | 47.0% | 389 | 55.3% | 11.2% | 8.0% | 4494 | 39.7% | 461 | 45.8% | 11.8% | 9.2% |
| H4 bars | control maps | 4100 | 41.0% | 389 | 51.0% | 11.8% (11.3 to 12.3) | 7.9% | 4494 | 28.8% | 461 | 40.3% | 14.4% (13.0 to 15.2) | 8.6% |

**BTC**

|  |  | DEV: bar highs and lows | DEV: of them at a level | DEV: turning points | DEV: of them at a level | DEV: became a turning point: at a level | DEV: elsewhere | CONFIRM: bar highs and lows | CONFIRM: of them at a level | CONFIRM: turning points | CONFIRM: of them at a level | CONFIRM: became a turning point: at a level | CONFIRM: elsewhere |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 bars | real levels | 22310 | 53.0% | 2250 | 56.4% | 10.7% | 9.3% | 24612 | 55.2% | 2469 | 59.3% | 10.8% | 9.1% |
| H1 bars | control maps | 22310 | 43.7% | 2250 | 50.9% | 11.8% (11.6 to 12.0) | 8.8% | 24612 | 47.4% | 2469 | 53.6% | 11.4% (11.2 to 11.5) | 8.8% |
| H4 bars | real levels | 5578 | 55.8% | 569 | 57.1% | 10.4% | 9.9% | 6162 | 57.7% | 617 | 60.1% | 10.4% | 9.4% |
| H4 bars | control maps | 5578 | 47.1% | 569 | 56.8% | 12.3% (11.3 to 12.8) | 8.3% | 6162 | 50.8% | 617 | 60.7% | 12.0% (11.6 to 12.4) | 8.0% |

"Turning point": a bar whose high (low) is not exceeded by the three bars before and after it, which is known
only afterwards. "At a level": within 0.25 ATR of a level known at that minute. The control row is the mean of
the four moved maps, with their range in brackets. A high or low near *any* line, real or moved, becomes a
turning point more often than one elsewhere (10 to 14 % against 8 to 10 %): lines are dense where the
market has been going back and forth, and that is where it turns most often. That is a statement about choppy
markets, not about the lines.

**Price reacts at any price.** After travelling an ATR to reach a price, the market pulls back half an ATR
before going a further ATR through it about two times in three: 67 / 66 % at gold's levels and 69 / 69 % at
its control prices, 67 / 68 % and 69 / 72 % for BTC (DEV / CONFIRM); a coin gives 69 %. Two reactions in three look like a rule on
a chart. They are what any price does, and the levels do it slightly less often.

## 3. What was measured

### 3.1 Levels

A level is a price together with the moment from which it is known. Nothing is used before that moment.

| Kind | Definition | Known from | Kept until |
|---|---|---|---|
| Swing high / low of H1, H4, D1 | a bar whose high (low) is above (below) the 3 bars before it and not below (above) the 3 bars after it | the close of the third bar after it | 500 bars of its own timeframe later (H1: 3 weeks, H4: 12 weeks, D1: more than a year), or broken twice |
| Previous day's high, low, close | the UTC day, as on the MT5 chart; gold's short Sunday session is counted with Monday | midnight UTC after that day | the end of the next trading day, or broken twice |
| Previous week's high, low, close | Monday to Sunday | Monday 00:00 UTC (gold: Saturday 00:00, so Sunday's reopening already reads it) | the end of the next week, or broken twice |
| Round numbers | gold: multiples of 50 (minor) and of 100 (major); BTC: of 1,000 and of 5,000 | always | always |

One price extreme is one level, however many of these it is. A D1 swing high is by construction also an H4 and
an H1 swing high, and often the previous day's high: it is kept once and gains each class at the moment that
class becomes known. All prices are bid prices; all distances below are in units of the **ATR(14) of H1 bars**
as it stood at the last closed H1 bar: at the touches of these periods a median of 17 USD of price in gold and
478 USD in BTC on DEV, and 6.5 USD and 533 USD on CONFIRM. That unit is what lets periods and symbols be
compared. On a 0.01 lot one ATR is worth that many USD in gold and a hundredth of it in BTC.

### 3.2 Approach, touch, zone, break

Each level is followed minute by minute:

- **Side.** Once an M15 bar has closed 0.25 ATR above a level it is a support; 0.25 ATR below, a resistance.
- **Break.** An M15 close 0.25 ATR beyond the level on the other side. The level changes role (a broken
  resistance is a support from then on); a swing or day / week level broken a second time is dropped.
- **Approach and touch.** A touch is the first minute in which price comes within **0.10 ATR** of a level,
  provided it has closed at least **1 ATR** away from it since the last touch. Coming back after a small wiggle
  is not a new approach.
- **Zone.** Levels of the same side within **0.25 ATR** of the touched one form its zone and share the touch,
  so one approach to a cluster of levels is one event. The level reached first carries the event; the zone's
  *strength* is the sum of its levels' weights (H1 swing 1, H4 swing 2, D1 swing 3, previous-day high / low 2
  and close 1, previous-week high / low 3 and close 2, round minor 1, major 2) plus its earlier touches (at most 3).

A row "H4 swing" in the tables therefore means: an approach to a zone that holds an H4 swing.

### 3.3 Five trades

All are 0.01 lot, pay the mean spread of the minute of entry, and are closed at the market if neither end is
reached within 24 hours (about 1 % of gold's bounce trades and 0.1 % of BTC's). The path is followed
on M1 bars; a minute that holds both ends counts as the stop, and a bar that opens beyond a stop exits at its open.

| Trade | Entry | Target | Stop |
|---|---|---|---|
| **Bounce** | at the touch, away from the level: buy a support, sell a resistance | 1 ATR from the touch price | 0.5 ATR beyond the level (0.6 ATR from entry) |
| **Rejection** | the same direction, but only after an M15 bar has closed 0.5 ATR back from the level (within 4 hours, and before any M15 close 0.25 ATR beyond it): the trader who waits to see the level hold | 1 ATR from that close | 1 ATR |
| **Retest** | the bounce trade at a level that has been broken once, when price returns to it from its new side | as the bounce | as the bounce |
| **Through** | at the touch, with the approach: sell a support, buy a resistance | 0.5 ATR beyond the level | 1 ATR back from the touch price |
| **Breakout** | at the M15 close that breaks the level (0.25 ATR beyond it), with the break; a zone counts once, when its last level has gone | 1 ATR from that close | 1 ATR |

In the minute of the touch the bounce trade can only be stopped (its stop lies beyond the touch price, so it was
certainly reached after the entry; the bar's other extreme may have come before it). The through trade is the
mirror image and is treated the hard way: if that minute also reaches its stop, the stop counts.

### 3.4 Two yardsticks

**A random walk.** A price without drift reaches the nearer of two barriers first in proportion to the
distances: the bounce trade's target is reached first with probability 0.6 / 1.6 = **37.5 %**, the rejection
and breakout trades' with 50 %, the through trade's with 62.5 %. At those rates each trade loses exactly the spread.

**A control map.** The comparison that isolates the levels themselves. The whole level map is moved by a fixed
fraction of price (gold: -1.0 %, -0.6 %, +0.6 %, +1.0 %; BTC: -1.5 %, -0.9 %, +0.9 %, +1.5 %; from one and a
half to about five ATRs) and the study is run again on each moved map. The moved levels have the same number, lifetimes,
classes and clustering as the real ones and are approached by the same market in the same weeks, but they stand
where nothing marks them. Control events closer than 0.5 ATR to a real level are left out. Before rates are
compared, the control events are re-weighted to the real events' mix of half-year, side (support / resistance),
session (four) and volatility state (H1 ATR against its 20-day median: low, normal, high).

### 3.5 Periods, costs, statistics

- **DEV** 1 Aug 2025 to 12 Nov 2026 (July 2025 only builds the level map); **CONFIRM** 1 Feb 2024 to 29 Jun 2025
  (January 2024 only builds the map). Trades are not opened in the last 24 hours of a period. No bar before
  1 Jan 2024 is read.
- **Cost**: the recorded spread of the minute of entry. At these touches it averaged 0.25 USD per 0.01 lot in
  gold on DEV (1.4 % of an ATR) and 0.18 USD on CONFIRM (3.0 %); in BTC 0.15 USD (3.3 %) and 0.36 USD
  (7.2 %). The spread weighs more on CONFIRM because gold's ATR was a third of its DEV size and BTC's
  spread twice as wide. No commission, no swap, no slippage on stops.
- **Intervals** are 95 % bootstrap intervals from 1,000 resamples of whole calendar weeks (the real and the
  control events of a week together), so that several touches of the same swing do not count as independent
  observations. An interval that excludes zero is printed in bold.
- **A candidate** is a row with at least 100 trades whose profit per trade is positive in every half-year, with
  its interval above zero, *and* whose target-first rate is above the control's with the interval above zero.
  This rule was written down before any result was seen.

### 3.6 What was fixed when

Before any outcome was looked at: every definition in 3.1 to 3.5 except those named next, the bounce, retest and
breakout trades, the tables by kind of level and by state of the market, the candidate rule. Added on DEV after
the first tables, and before CONFIRM was read: the through trade and the rejection trade, the split into ranging
and trending markets (efficiency ratio of the last 120 H1 closes below 0.06 / above 0.125, roughly its lower and
upper third), the table of other controls and the hindsight count of section 2. The code was then committed and
run on CONFIRM once. Nothing that produces a number was changed afterwards; only the function that counts the
rows against the candidate rule (4.6) was added to the report.

## 4. Results

How to read the tables. *Trades (per quarter)*: how many there were, and how many a quarter. *Target first*:
the share of trades that reached their target before their stop, at the levels and at the matched control
(trades closed after 24 hours left out). *Difference*: the first minus the second, in percentage points.
*ATR per trade*: profit after the spread, every trade counted. *USD per trade (per quarter)*: the same for a
0.01 lot, and what taking every such trade would have added up to in a quarter. *By half-year*: ATR per trade
in 2025 H2 / 2026 H1 / 2026 H2 for DEV and in 2024 H1 / 2024 H2 / 2025 H1 for CONFIRM. Bold: the 95 %
interval excludes zero. A coin would take the bounce and retest trades to their target 37.5 % of the time, the
rejection and breakout trades 50 %, the through trade 62.5 %.

### 4.1 Every trade at a glance

**Gold**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bounce: buy a support, sell a resistance at the touch | 3634 (709) | 34.9% vs 37.7% | -2.8 [-6.4, +0.9] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 37.7% | **-4.1 [-6.9, -1.5]** | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| bounce, only H4 / D1 swings and day / week highs and lows | 1083 (211) | 31.7% vs 36.5% | -4.9 [-10.9, +1.4] | **-0.101 [-0.156, -0.049]** | -2.13 (-449) | -0.143 / -0.137 / -0.014 | 1242 (220) | 32.4% vs 39.8% | **-7.3 [-11.4, -1.8]** | **-0.104 [-0.149, -0.061]** | -0.76 (-168) | -0.179 / -0.052 / -0.096 |
| bounce, only with the H4 and the D1 trend | 1561 (305) | 35.3% vs 42.5% | -7.3 [-12.2, +0.0] | -0.035 [-0.076, +0.006] | -1.26 (-385) | -0.008 / -0.037 / -0.063 | 1516 (269) | 33.6% vs 37.9% | **-4.3 [-8.6, -0.2]** | **-0.081 [-0.114, -0.047]** | -0.73 (-197) | -0.121 / -0.075 / -0.057 |
| bounce after the level has held for an M15 close (rejection) | 1727 (337) | 49.5% vs 48.5% | +1.0 [-4.9, +6.8] | -0.026 [-0.074, +0.021] | -0.20 (-66) | +0.020 / -0.014 / -0.088 | 1611 (286) | 50.6% vs 48.3% | +2.3 [-2.3, +7.3] | -0.019 [-0.073, +0.030] | -0.28 (-81) | -0.044 / -0.013 / -0.004 |
| bounce at a broken level retested from its other side | 959 (187) | 36.4% vs 37.3% | -0.9 [-6.7, +6.3] | -0.022 [-0.084, +0.037] | +0.00 (+1) | -0.043 / +0.036 / -0.071 | 1184 (210) | 37.4% vs 39.8% | -2.4 [-7.2, +3.1] | -0.023 [-0.061, +0.013] | -0.26 (-54) | -0.041 / -0.001 / -0.029 |
| through: with the approach at the touch | 3634 (709) | 63.5% vs 60.8% | +2.7 [-1.2, +6.5] | -0.003 [-0.035, +0.028] | +0.08 (+53) | -0.016 / +0.002 / +0.003 | 3396 (602) | 64.0% vs 60.8% | **+3.2 [+0.5, +6.2]** | -0.010 [-0.037, +0.017] | +0.08 (+51) | -0.031 / -0.025 / +0.021 |
| breakout: with the break after an M15 close beyond | 2948 (575) | 49.6% vs 47.7% | +2.0 [-1.6, +6.1] | -0.019 [-0.062, +0.021] | -0.63 (-364) | +0.002 / -0.022 / -0.037 | 2672 (474) | 51.9% vs 49.2% | +2.6 [-1.1, +6.1] | +0.009 [-0.030, +0.047] | +0.15 (+70) | +0.018 / -0.014 / +0.022 |

**BTC**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bounce: buy a support, sell a resistance at the touch | 6258 (1221) | 35.5% vs 36.8% | -1.2 [-4.6, +1.8] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 40.1% | **-4.9 [-8.0, -2.5]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| bounce, only H4 / D1 swings and day / week highs and lows | 1866 (364) | 34.0% vs 35.1% | -1.1 [-7.5, +4.1] | **-0.086 [-0.126, -0.041]** | -0.34 (-124) | -0.036 / -0.079 / -0.155 | 1960 (348) | 33.8% vs 42.9% | **-9.1 [-13.7, -3.6]** | **-0.132 [-0.169, -0.097]** | -0.71 (-246) | -0.208 / -0.120 / -0.089 |
| bounce, only with the H4 and the D1 trend | 2658 (519) | 36.6% vs 38.4% | -1.8 [-5.5, +3.2] | **-0.042 [-0.074, -0.011]** | -0.10 (-50) | -0.040 / -0.017 / -0.076 | 2951 (523) | 35.4% vs 43.0% | **-7.6 [-12.1, -2.4]** | **-0.104 [-0.133, -0.079]** | -0.56 (-295) | -0.150 / -0.110 / -0.067 |
| bounce after the level has held for an M15 close (rejection) | 3177 (620) | 47.9% vs 51.1% | -3.2 [-6.9, +0.5] | **-0.074 [-0.111, -0.037]** | -0.38 (-238) | -0.080 / -0.075 / -0.066 | 3552 (630) | 48.8% vs 50.2% | -1.3 [-5.3, +2.3] | **-0.094 [-0.129, -0.059]** | -0.44 (-277) | -0.175 / -0.096 / -0.028 |
| bounce at a broken level retested from its other side | 1644 (321) | 39.8% vs 36.5% | +3.3 [-1.4, +8.6] | +0.008 [-0.031, +0.046] | +0.11 (+36) | -0.011 / +0.044 / -0.016 | 1681 (298) | 36.7% vs 43.7% | **-7.1 [-12.1, -1.0]** | **-0.088 [-0.127, -0.054]** | -0.42 (-125) | -0.125 / -0.084 / -0.066 |
| through: with the approach at the touch | 6258 (1221) | 62.6% vs 59.6% | +3.0 [-0.5, +6.2] | **-0.032 [-0.056, -0.011]** | -0.23 (-282) | -0.040 / -0.045 / -0.004 | 7065 (1253) | 63.7% vs 58.7% | **+5.0 [+2.4, +8.3]** | **-0.053 [-0.070, -0.036]** | -0.29 (-366) | -0.114 / -0.028 / -0.034 |
| breakout: with the break after an M15 close beyond | 4915 (959) | 50.5% vs 50.6% | -0.2 [-3.8, +2.6] | -0.023 [-0.058, +0.008] | -0.16 (-156) | -0.024 / -0.044 / +0.008 | 5677 (1007) | 50.3% vs 51.8% | -1.4 [-4.9, +1.6] | **-0.063 [-0.090, -0.035]** | -0.35 (-355) | -0.142 / -0.033 / -0.033 |

In no cell of these two tables is a profit interval above zero. The bounce trade, the one the question is
about, loses in all four columns: at all levels, at the higher-timeframe levels only, and with the trend.
Two cells are positive at all: gold's breakout on CONFIRM (+0.009 ATR, interval through zero) and BTC's retest
on DEV (+0.008), which turned to -0.088 on CONFIRM. The USD column can differ in sign from the ATR column
(gold's through trade): an ATR of gold was worth 8 USD in mid-2025 and 26 USD in early 2026, so the USD figure
weights the volatile months more; neither is distinguishable from zero.

### 4.2 The bounce trade by kind of level

Rows overlap: a zone that holds a D1 swing and the previous week's high is in both rows.

**Gold**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all levels | 3634 (709) | 34.9% vs 37.7% | -2.8 [-6.4, +0.9] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 37.7% | **-4.1 [-6.9, -1.5]** | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| H1 swing (not H4) | 1673 (326) | 35.6% vs 38.9% | -3.3 [-7.7, +2.1] | -0.033 [-0.073, +0.008] | -0.72 (-235) | -0.022 / -0.023 / -0.057 | 1702 (302) | 33.3% vs 37.2% | **-3.9 [-8.1, -0.2]** | **-0.088 [-0.120, -0.055]** | -0.64 (-194) | -0.115 / -0.084 / -0.064 |
| H4 swing (not D1) | 670 (131) | 31.7% vs 35.8% | -4.1 [-12.4, +3.3] | **-0.101 [-0.165, -0.036]** | -1.96 (-256) | -0.187 / -0.107 / -0.014 | 877 (155) | 33.6% vs 39.3% | -5.7 [-10.7, +0.8] | **-0.084 [-0.129, -0.041]** | -0.61 (-94) | -0.139 / -0.051 / -0.072 |
| D1 swing | 122 (24) | 24.2% vs 38.8% | -14.6 [-31.4, +2.0] | **-0.222 [-0.361, -0.081]** | -6.76 (-161) | +0.112 / -0.309 / -0.279 | 128 (23) | 29.9% vs 28.5% | +1.5 [-12.8, +16.3] | **-0.150 [-0.304, -0.006]** | -0.92 (-21) | -0.386 / -0.085 / -0.068 |
| previous-day high / low | 538 (105) | 31.3% vs 37.9% | -6.6 [-13.0, +0.4] | **-0.108 [-0.174, -0.046]** | -1.88 (-197) | -0.196 / -0.144 / +0.024 | 609 (108) | 31.4% vs 39.2% | **-7.8 [-12.8, -0.9]** | **-0.124 [-0.185, -0.066]** | -0.93 (-100) | -0.175 / -0.058 / -0.153 |
| previous-day close | 381 (74) | 41.2% vs 39.6% | +1.6 [-6.0, +9.1] | +0.057 [-0.025, +0.139] | +1.60 (+119) | +0.085 / +0.161 / -0.137 | 366 (65) | 33.8% vs 38.8% | -5.1 [-11.2, +3.6] | **-0.088 [-0.152, -0.025]** | -0.48 (-31) | -0.160 / -0.049 / -0.068 |
| previous-week high / low | 145 (28) | 32.4% vs 42.1% | -9.7 [-23.5, +2.8] | -0.088 [-0.233, +0.049] | -1.87 (-53) | +0.125 / -0.212 / -0.199 | 152 (27) | 24.5% vs 37.7% | **-13.2 [-26.5, -2.8]** | **-0.227 [-0.332, -0.134]** | -1.78 (-48) | -0.415 / -0.146 / -0.185 |
| previous-week close | 125 (24) | 39.2% vs 37.4% | +1.8 [-15.2, +15.6] | +0.015 [-0.090, +0.124] | +1.53 (+37) | +0.025 / +0.037 / -0.034 | 131 (23) | 40.5% vs 48.4% | -7.9 [-20.2, +6.3] | +0.015 [-0.151, +0.168] | -0.33 (-8) | -0.126 / +0.095 / +0.018 |
| round number, minor | 713 (139) | 31.6% vs 36.7% | -5.1 [-11.2, +0.4] | **-0.094 [-0.147, -0.036]** | -2.69 (-374) | +0.000 / -0.086 / -0.203 | 307 (54) | 37.5% vs 37.3% | +0.2 [-6.0, +7.8] | -0.024 [-0.101, +0.055] | -0.21 (-12) | +0.129 / -0.112 / -0.035 |
| round number, major | 733 (143) | 36.2% vs 36.3% | -0.2 [-7.2, +7.0] | -0.023 [-0.076, +0.031] | +0.11 (+16) | -0.050 / -0.019 / -0.008 | 289 (51) | 32.5% vs 35.8% | -3.3 [-8.0, +3.1] | **-0.102 [-0.166, -0.040]** | -0.84 (-43) | -0.121 / -0.143 / -0.069 |
| any H4 / D1 swing or day / week high / low | 1083 (211) | 31.7% vs 36.5% | -4.9 [-10.9, +1.4] | **-0.101 [-0.156, -0.049]** | -2.13 (-449) | -0.143 / -0.137 / -0.014 | 1242 (220) | 32.4% vs 39.8% | **-7.3 [-11.4, -1.8]** | **-0.104 [-0.149, -0.061]** | -0.76 (-168) | -0.179 / -0.052 / -0.096 |

**BTC**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all levels | 6258 (1221) | 35.5% vs 36.8% | -1.2 [-4.6, +1.8] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 40.1% | **-4.9 [-8.0, -2.5]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| H1 swing (not H4) | 2799 (546) | 36.1% vs 38.9% | -2.8 [-7.0, +1.2] | **-0.052 [-0.082, -0.021]** | -0.17 (-90) | -0.099 / -0.049 / -0.013 | 2997 (531) | 35.5% vs 42.2% | **-6.7 [-10.8, -2.9]** | **-0.108 [-0.131, -0.084]** | -0.51 (-271) | -0.152 / -0.083 / -0.098 |
| H4 swing (not D1) | 1176 (229) | 34.6% vs 35.6% | -1.0 [-8.5, +5.2] | **-0.076 [-0.122, -0.033]** | -0.24 (-55) | -0.007 / -0.098 / -0.148 | 1252 (222) | 34.5% vs 41.7% | **-7.2 [-14.1, -0.1]** | **-0.124 [-0.167, -0.080]** | -0.61 (-136) | -0.189 / -0.117 / -0.077 |
| D1 swing | 263 (51) | 32.6% vs 27.6% | +5.0 [-8.0, +14.6] | -0.104 [-0.203, +0.004] | -0.68 (-35) | -0.119 / -0.062 / -0.166 | 245 (43) | 30.6% vs 37.5% | -6.9 [-17.0, +3.6] | **-0.165 [-0.239, -0.093]** | -1.02 (-44) | -0.404 / -0.193 / -0.054 |
| previous-day high / low | 868 (169) | 31.4% vs 37.3% | -5.9 [-12.6, +0.5] | **-0.130 [-0.192, -0.075]** | -0.54 (-91) | -0.095 / -0.124 / -0.177 | 932 (165) | 33.4% vs 43.3% | **-9.9 [-15.6, -3.8]** | **-0.140 [-0.192, -0.093]** | -0.78 (-129) | -0.213 / -0.109 / -0.116 |
| previous-day close | 481 (94) | 32.8% vs 45.5% | **-12.6 [-21.3, -3.8]** | **-0.108 [-0.178, -0.037]** | -0.37 (-35) | -0.074 / -0.130 / -0.122 | 518 (92) | 33.3% vs 39.6% | -6.4 [-12.9, +0.3] | **-0.143 [-0.201, -0.089]** | -0.62 (-57) | -0.204 / -0.172 / -0.065 |
| previous-week high / low | 171 (33) | 38.0% vs 35.6% | +2.4 [-10.5, +17.4] | -0.021 [-0.165, +0.110] | -0.21 (-7) | +0.050 / -0.009 / -0.133 | 192 (34) | 32.3% vs 33.7% | -1.4 [-14.1, +11.6] | **-0.147 [-0.261, -0.039]** | -0.86 (-29) | -0.400 / -0.068 / -0.073 |
| previous-week close | 144 (28) | 41.0% vs 42.2% | -1.2 [-14.9, +12.1] | +0.024 [-0.107, +0.136] | +0.38 (+11) | +0.095 / +0.055 / -0.123 | 145 (26) | 30.3% vs 46.8% | **-16.4 [-29.5, -1.4]** | **-0.185 [-0.314, -0.067]** | -0.60 (-15) | -0.400 / -0.147 / -0.094 |
| round number, minor | 2202 (430) | 36.1% vs 35.5% | +0.7 [-4.5, +5.4] | **-0.048 [-0.085, -0.014]** | -0.23 (-97) | -0.069 / -0.032 / -0.037 | 2784 (494) | 34.0% vs 38.9% | **-4.9 [-8.4, -1.4]** | **-0.117 [-0.141, -0.091]** | -0.67 (-331) | -0.155 / -0.125 / -0.087 |
| round number, major | 513 (100) | 32.7% vs 29.9% | +2.8 [-5.4, +8.9] | **-0.097 [-0.164, -0.018]** | -0.23 (-23) | -0.097 / -0.075 / -0.132 | 640 (113) | 35.6% vs 38.9% | -3.3 [-10.2, +3.5] | **-0.089 [-0.143, -0.035]** | -0.51 (-57) | -0.201 / -0.023 / -0.090 |
| any H4 / D1 swing or day / week high / low | 1866 (364) | 34.0% vs 35.1% | -1.1 [-7.5, +4.1] | **-0.086 [-0.126, -0.041]** | -0.34 (-124) | -0.036 / -0.079 / -0.155 | 1960 (348) | 33.8% vs 42.9% | **-9.1 [-13.7, -3.6]** | **-0.132 [-0.169, -0.097]** | -0.71 (-246) | -0.208 / -0.120 / -0.089 |

No kind of level holds better than the control in both periods, and the higher timeframes are not the stronger
ones. Zones with an H4 or D1 swing or a day / week high or low lost -0.10 / -0.10 ATR per trade in gold
and -0.09 / -0.13 in BTC (DEV / CONFIRM), more than plain H1 swings (-0.03 / -0.09 and -0.05 / -0.11), and on
CONFIRM they held 7 and 9 points less often than the control. The previous day's high and low is among
the worst rows in every column. Three rows are above zero on DEV, none with its interval above zero: gold's
previous-day close (+0.057) and the previous-week close on both symbols (+0.015 and +0.024). On CONFIRM
they made -0.088, +0.015 and -0.185; gold's week close, the one that stayed positive, rests on 131 trades
with an interval from -0.15 to +0.17. D1 swings and the week's levels have 120 to 260 trades a period, so
their intervals are wide.

The loss is there in every half-year (all levels; gold DEV and CONFIRM, then BTC):

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2025H2 | 1060 (207) | 35.5% vs 39.0% | -3.5 [-7.6, +0.4] | -0.036 [-0.091, +0.016] | -0.39 (-81) | -0.036 |
| 2026H1 | 1496 (292) | 35.2% vs 38.1% | -2.9 [-9.4, +3.2] | -0.039 [-0.078, +0.002] | -1.12 (-326) | -0.039 |
| 2026H2 | 1078 (210) | 33.8% vs 35.8% | -1.9 [-9.4, +5.8] | **-0.069 [-0.120, -0.012]** | -1.17 (-246) | -0.069 |

|  | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2024H1 | 1032 (183) | 32.9% vs 36.7% | -3.8 [-9.5, +0.9] | **-0.114 [-0.149, -0.083]** | -0.59 (-107) | -0.114 |
| 2024H2 | 1164 (206) | 33.9% vs 40.9% | **-7.0 [-11.9, -2.6]** | **-0.076 [-0.121, -0.039]** | -0.52 (-107) | -0.076 |
| 2025H1 | 1200 (213) | 33.8% vs 35.4% | -1.6 [-6.3, +3.0] | **-0.067 [-0.098, -0.034]** | -0.76 (-162) | -0.067 |

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2025H2 | 2128 (415) | 35.5% vs 33.6% | +1.9 [-3.5, +7.8] | **-0.062 [-0.092, -0.029]** | -0.31 (-129) | -0.062 |
| 2026H1 | 2376 (464) | 36.6% vs 38.2% | -1.6 [-7.1, +3.7] | **-0.045 [-0.078, -0.011]** | -0.10 (-45) | -0.045 |
| 2026H2 | 1754 (342) | 34.2% vs 38.8% | **-4.5 [-9.2, -0.4]** | **-0.079 [-0.111, -0.043]** | -0.21 (-73) | -0.079 |

|  | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2024H1 | 1907 (338) | 35.4% vs 41.3% | **-5.8 [-9.5, -1.8]** | **-0.158 [-0.185, -0.130]** | -0.66 (-224) | -0.158 |
| 2024H2 | 2565 (455) | 34.5% vs 39.6% | **-5.1 [-10.5, -0.5]** | **-0.103 [-0.123, -0.082]** | -0.53 (-242) | -0.103 |
| 2025H1 | 2593 (460) | 35.7% vs 39.8% | -4.2 [-9.5, +0.2] | **-0.076 [-0.103, -0.049]** | -0.44 (-200) | -0.076 |

### 4.3 What might make a level work

The bounce trade again, split by the state of the level and of the market at the touch. "Trade with the
trend" means buying a support in an uptrend or selling a resistance in a downtrend. RSI is read from the
trade's side: "stretched" is oversold at a support, overbought at a resistance. Divergence: price is back at an
old low (high) while the M15 RSI stands at least 3 points higher (lower) than in the bar that made it.

**Gold**

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| side | support (buy) | 1835 (358) | 36.0% vs 40.9% | **-4.9 [-8.9, -0.8]** | -0.026 [-0.062, +0.009] | -0.52 (-185) | +0.022 / -0.041 / -0.050 | 1732 (307) | 35.2% vs 38.1% | -2.9 [-7.3, +1.5] | **-0.056 [-0.090, -0.021]** | -0.55 (-168) | -0.076 / -0.044 / -0.050 |
| side | resistance (sell) | 1799 (351) | 33.7% vs 34.4% | -0.7 [-6.0, +4.6] | **-0.068 [-0.106, -0.030]** | -1.33 (-467) | -0.089 / -0.037 / -0.088 | 1664 (295) | 31.9% vs 37.3% | **-5.4 [-9.1, -2.4]** | **-0.115 [-0.153, -0.079]** | -0.71 (-208) | -0.156 / -0.109 / -0.086 |
| levels in the zone | 1 | 2218 (433) | 36.3% vs 37.6% | -1.3 [-5.0, +2.6] | -0.026 [-0.061, +0.009] | -0.33 (-141) | -0.029 / -0.000 / -0.059 | 2179 (386) | 33.8% vs 38.1% | **-4.3 [-7.6, -0.8]** | **-0.081 [-0.108, -0.055]** | -0.61 (-236) | -0.093 / -0.092 / -0.059 |
| levels in the zone | 2 | 997 (195) | 34.7% vs 39.7% | -5.0 [-11.0, +1.5] | -0.047 [-0.098, +0.013] | -1.39 (-271) | +0.024 / -0.064 / -0.083 | 902 (160) | 32.6% vs 36.8% | -4.3 [-9.5, +1.1] | **-0.102 [-0.148, -0.058]** | -0.69 (-111) | -0.138 / -0.060 / -0.114 |
| levels in the zone | 3 or more | 419 (82) | 27.8% vs 41.1% | -13.3 [-25.0, +0.2] | **-0.157 [-0.236, -0.078]** | -2.94 (-241) | -0.206 / -0.161 / -0.087 | 315 (56) | 34.7% vs 37.3% | -2.6 [-12.3, +5.9] | -0.062 [-0.146, +0.019] | -0.51 (-29) | -0.245 / -0.026 / -0.001 |
| zone strength | 1-2 | 1074 (210) | 36.7% vs 37.6% | -1.0 [-6.6, +3.9] | -0.023 [-0.073, +0.027] | -0.47 (-99) | -0.056 / +0.020 / -0.037 | 1296 (230) | 33.0% vs 37.3% | **-4.3 [-9.4, -0.3]** | **-0.093 [-0.127, -0.060]** | -0.71 (-162) | -0.109 / -0.100 / -0.070 |
| zone strength | 3-4 | 1102 (215) | 36.5% vs 37.1% | -0.6 [-5.0, +4.2] | -0.023 [-0.069, +0.021] | -0.27 (-57) | +0.024 / +0.007 / -0.100 | 1038 (184) | 33.9% vs 37.4% | -3.5 [-7.3, +0.6] | **-0.083 [-0.127, -0.041]** | -0.56 (-103) | -0.104 / -0.064 / -0.082 |
| zone strength | 5-6 | 1000 (195) | 34.1% vs 40.0% | **-5.9 [-11.7, -0.4]** | -0.053 [-0.106, +0.002] | -0.89 (-174) | -0.024 / -0.052 / -0.078 | 772 (137) | 33.8% vs 36.6% | -2.7 [-7.8, +2.5] | **-0.081 [-0.134, -0.031]** | -0.60 (-83) | -0.099 / -0.100 / -0.047 |
| zone strength | 7 or more | 458 (89) | 28.5% vs 35.5% | -7.0 [-19.1, +6.7] | **-0.148 [-0.225, -0.073]** | -3.60 (-321) | -0.149 / -0.204 / -0.033 | 290 (51) | 34.4% vs 36.8% | -2.4 [-11.8, +7.9] | -0.067 [-0.159, +0.022] | -0.54 (-28) | -0.302 / +0.018 / -0.061 |
| earlier touches | none (first touch) | 852 (166) | 35.7% vs 36.8% | -1.0 [-6.8, +3.3] | -0.037 [-0.087, +0.015] | -0.85 (-142) | -0.073 / -0.032 / -0.001 | 1050 (186) | 31.7% vs 36.4% | **-4.7 [-10.3, -0.1]** | **-0.116 [-0.161, -0.071]** | -0.85 (-157) | -0.131 / -0.162 / -0.056 |
| earlier touches | 1 | 664 (130) | 36.9% vs 40.6% | -3.7 [-10.6, +4.5] | -0.020 [-0.089, +0.052] | +0.07 (+10) | -0.042 / +0.061 / -0.095 | 810 (144) | 33.4% vs 41.2% | **-7.8 [-12.4, -1.5]** | **-0.088 [-0.143, -0.034]** | -0.68 (-97) | -0.158 / +0.044 / -0.143 |
| earlier touches | 2 | 407 (79) | 36.5% vs 42.5% | -6.0 [-15.2, +2.9] | -0.021 [-0.100, +0.058] | -0.41 (-33) | -0.007 / -0.015 / -0.042 | 508 (90) | 34.9% vs 36.8% | -2.0 [-9.8, +5.7] | -0.065 [-0.137, +0.006] | -0.20 (-18) | -0.104 / -0.096 / -0.001 |
| earlier touches | 3 or more | 1711 (334) | 33.3% vs 38.2% | **-4.9 [-10.1, -0.7]** | **-0.068 [-0.106, -0.030]** | -1.46 (-487) | -0.014 / -0.077 / -0.100 | 1028 (182) | 35.0% vs 37.2% | -2.2 [-5.7, +2.6] | **-0.060 [-0.104, -0.017]** | -0.57 (-103) | -0.057 / -0.071 / -0.052 |
| role (not round numbers) | never broken | 1576 (307) | 34.2% vs 38.2% | -4.0 [-8.6, +0.5] | **-0.060 [-0.100, -0.016]** | -1.26 (-388) | -0.051 / -0.076 / -0.049 | 1759 (312) | 30.1% vs 35.6% | **-5.6 [-9.9, -1.6]** | **-0.141 [-0.176, -0.108]** | -0.97 (-303) | -0.208 / -0.122 / -0.104 |
| role (not round numbers) | broken once, retested from the other side | 959 (187) | 36.4% vs 37.3% | -0.9 [-6.7, +6.3] | -0.022 [-0.084, +0.037] | +0.00 (+1) | -0.043 / +0.036 / -0.071 | 1184 (210) | 37.4% vs 39.8% | -2.4 [-7.2, +3.1] | -0.023 [-0.061, +0.013] | -0.26 (-54) | -0.041 / -0.001 / -0.029 |
| age (not round numbers) | under 1 day | 1218 (238) | 36.9% vs 37.1% | -0.2 [-5.5, +5.7] | -0.019 [-0.071, +0.038] | -0.46 (-109) | -0.046 / +0.054 / -0.071 | 1383 (245) | 31.3% vs 38.4% | **-7.0 [-10.5, -1.7]** | **-0.125 [-0.155, -0.095]** | -0.86 (-212) | -0.161 / -0.108 / -0.108 |
| age (not round numbers) | 1-5 days | 843 (164) | 31.9% vs 39.1% | **-7.2 [-12.3, -1.4]** | **-0.092 [-0.147, -0.039]** | -1.18 (-194) | -0.136 / -0.090 / -0.061 | 911 (162) | 34.7% vs 37.1% | -2.4 [-8.0, +3.8] | **-0.060 [-0.102, -0.020]** | -0.47 (-76) | -0.057 / -0.068 / -0.055 |
| age (not round numbers) | 5-20 days | 392 (76) | 37.8% vs 37.9% | -0.1 [-10.8, +8.7] | -0.001 [-0.081, +0.080] | -0.08 (-6) | +0.107 / -0.126 / +0.026 | 543 (96) | 34.3% vs 41.7% | -7.3 [-16.1, +0.0] | **-0.069 [-0.127, -0.016]** | -0.65 (-62) | -0.191 / +0.021 / -0.060 |
| age (not round numbers) | over 20 days | 82 (16) | 26.8% vs 35.9% | -9.1 [-27.0, +10.5] | **-0.184 [-0.341, -0.042]** | -4.84 (-77) | -0.238 / -0.185 / -0.157 | 106 (19) | 33.3% vs 23.6% | +9.7 [-3.3, +26.5] | -0.092 [-0.217, +0.039] | -0.35 (-7) | -0.174 / -0.192 / +0.110 |
| H4 trend (MACD signal line) | trade with it | 1837 (358) | 35.5% vs 41.9% | -6.4 [-10.8, +0.3] | -0.033 [-0.070, +0.005] | -1.16 (-416) | +0.003 / -0.033 / -0.069 | 1824 (323) | 34.5% vs 38.9% | **-4.5 [-8.7, -0.3]** | **-0.068 [-0.099, -0.036]** | -0.63 (-205) | -0.103 / -0.044 / -0.063 |
| H4 trend (MACD signal line) | trade against it | 1797 (351) | 34.2% vs 35.1% | -0.9 [-6.0, +4.2] | **-0.061 [-0.102, -0.020]** | -0.67 (-236) | -0.075 / -0.045 / -0.068 | 1572 (279) | 32.6% vs 35.9% | -3.3 [-7.5, +0.5] | **-0.104 [-0.139, -0.068]** | -0.61 (-170) | -0.127 / -0.112 / -0.073 |
| D1 trend (close vs EMA20) | trade with it | 1887 (368) | 35.2% vs 40.6% | -5.3 [-10.4, +0.7] | -0.038 [-0.076, +0.003] | -1.12 (-413) | -0.006 / -0.045 / -0.059 | 1843 (327) | 33.2% vs 38.1% | **-5.0 [-9.1, -1.1]** | **-0.089 [-0.116, -0.057]** | -0.77 (-251) | -0.123 / -0.081 / -0.066 |
| D1 trend (close vs EMA20) | trade against it | 1747 (341) | 34.5% vs 36.0% | -1.6 [-6.4, +3.2] | **-0.057 [-0.094, -0.020]** | -0.70 (-240) | -0.069 / -0.033 / -0.079 | 1553 (275) | 34.0% vs 37.3% | -3.3 [-7.1, +0.7] | **-0.080 [-0.116, -0.042]** | -0.45 (-125) | -0.104 / -0.071 / -0.069 |
| H4 and D1 trend | with both | 1561 (305) | 35.3% vs 42.5% | -7.3 [-12.2, +0.0] | -0.035 [-0.076, +0.006] | -1.26 (-385) | -0.008 / -0.037 / -0.063 | 1516 (269) | 33.6% vs 37.9% | **-4.3 [-8.6, -0.2]** | **-0.081 [-0.114, -0.047]** | -0.73 (-197) | -0.121 / -0.075 / -0.057 |
| H4 and D1 trend | against both | 1471 (287) | 34.0% vs 36.3% | -2.3 [-7.3, +3.0] | **-0.064 [-0.104, -0.022]** | -0.72 (-208) | -0.089 / -0.037 / -0.075 | 1245 (221) | 32.9% vs 35.4% | -2.5 [-6.9, +1.2] | **-0.098 [-0.138, -0.054]** | -0.53 (-116) | -0.125 / -0.112 / -0.061 |
| M15 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 482 (94) | 36.7% vs 32.7% | +4.0 [-7.1, +11.9] | -0.024 [-0.098, +0.046] | -0.01 (-1) | +0.083 / -0.078 / -0.024 | 506 (90) | 36.0% vs 34.5% | +1.5 [-7.7, +8.9] | -0.046 [-0.102, +0.012] | -0.41 (-37) | -0.077 / -0.052 / -0.013 |
| M15 RSI at the touch | 30-50 (50-70) | 2253 (440) | 34.8% vs 40.6% | **-5.8 [-10.3, -0.2]** | **-0.047 [-0.082, -0.009]** | -1.09 (-478) | -0.045 / -0.035 / -0.067 | 2072 (367) | 31.8% vs 40.2% | **-8.4 [-12.2, -4.0]** | **-0.110 [-0.139, -0.080]** | -0.82 (-301) | -0.174 / -0.079 / -0.088 |
| M15 RSI at the touch | not stretched | 899 (175) | 34.0% vs 36.3% | -2.2 [-8.2, +5.2] | **-0.059 [-0.108, -0.010]** | -0.99 (-173) | -0.066 / -0.027 / -0.097 | 818 (145) | 36.5% vs 35.9% | +0.6 [-3.5, +7.2] | -0.046 [-0.100, +0.012] | -0.26 (-38) | -0.004 / -0.084 / -0.047 |
| H1 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 309 (60) | 35.7% vs 34.3% | +1.4 [-7.8, +13.4] | -0.038 [-0.119, +0.046] | -0.61 (-37) | -0.019 / -0.083 / +0.015 | 237 (42) | 36.2% vs 39.2% | -3.0 [-14.4, +7.0] | -0.045 [-0.136, +0.051] | -0.31 (-13) | +0.001 / -0.157 / -0.003 |
| H1 RSI at the touch | 30-50 (50-70) | 1794 (350) | 34.0% vs 40.2% | **-6.2 [-10.8, -1.2]** | **-0.064 [-0.103, -0.025]** | -1.27 (-446) | -0.063 / -0.077 / -0.048 | 1729 (307) | 32.9% vs 34.5% | -1.6 [-6.5, +3.1] | **-0.093 [-0.130, -0.057]** | -0.69 (-212) | -0.127 / -0.086 / -0.072 |
| H1 RSI at the touch | not stretched | 1531 (299) | 35.7% vs 37.9% | -2.3 [-7.6, +3.6] | -0.029 [-0.074, +0.017] | -0.57 (-170) | -0.007 / +0.011 / -0.113 | 1430 (254) | 33.9% vs 40.7% | **-6.8 [-10.4, -2.4]** | **-0.081 [-0.119, -0.046]** | -0.59 (-150) | -0.121 / -0.054 / -0.072 |
| RSI divergence (unbroken extremes) | yes | 567 (111) | 29.7% vs 38.8% | **-9.1 [-17.2, -0.1]** | **-0.130 [-0.193, -0.069]** | -2.44 (-270) | -0.210 / -0.139 / -0.044 | 659 (117) | 29.1% vs 42.3% | **-13.2 [-22.0, -3.1]** | **-0.161 [-0.215, -0.110]** | -1.11 (-129) | -0.218 / -0.118 / -0.150 |
| RSI divergence (unbroken extremes) | no | 842 (164) | 35.4% vs 39.9% | -4.6 [-11.2, +3.7] | -0.041 [-0.089, +0.007] | -1.14 (-187) | -0.008 / -0.083 / -0.023 | 931 (165) | 30.6% vs 34.6% | -4.0 [-11.8, +3.8] | **-0.128 [-0.177, -0.082]** | -0.89 (-146) | -0.195 / -0.142 / -0.064 |
| approach in the last hour | under 0.5 ATR | 795 (155) | 36.7% vs 38.9% | -2.2 [-9.1, +4.5] | -0.023 [-0.075, +0.026] | -0.78 (-121) | -0.018 / -0.002 / -0.059 | 689 (122) | 35.4% vs 37.2% | -1.8 [-8.8, +4.0] | **-0.063 [-0.119, -0.004]** | -0.45 (-55) | -0.016 / -0.042 / -0.117 |
| approach in the last hour | 0.5-1.5 ATR | 2007 (392) | 34.4% vs 37.7% | -3.3 [-7.8, +1.3] | **-0.060 [-0.093, -0.027]** | -1.35 (-531) | -0.034 / -0.072 / -0.069 | 1853 (329) | 32.2% vs 38.3% | **-6.0 [-9.9, -1.2]** | **-0.109 [-0.138, -0.083]** | -0.84 (-275) | -0.147 / -0.105 / -0.083 |
| approach in the last hour | over 1.5 ATR | 759 (148) | 35.4% vs 40.2% | -4.9 [-14.2, +2.7] | -0.038 [-0.089, +0.022] | -0.04 (-6) | -0.059 / +0.004 / -0.073 | 783 (139) | 35.5% vs 40.9% | -5.3 [-11.5, +0.2] | -0.049 [-0.112, +0.016] | -0.31 (-43) | -0.119 / -0.036 / +0.017 |
| last five days (efficiency ratio of H1 closes) | ranging (under 0.06) | 1116 (218) | 36.2% vs 38.8% | -2.6 [-8.0, +4.6] | -0.032 [-0.089, +0.023] | -0.73 (-159) | +0.017 / -0.051 / -0.045 | 1225 (217) | 35.4% vs 35.5% | -0.1 [-7.1, +4.6] | **-0.058 [-0.098, -0.022]** | -0.43 (-94) | -0.059 / -0.037 / -0.081 |
| last five days (efficiency ratio of H1 closes) | in between | 1194 (233) | 34.0% vs 38.5% | -4.5 [-10.8, +1.7] | **-0.053 [-0.098, -0.008]** | -1.47 (-342) | +0.033 / -0.085 / -0.088 | 1047 (186) | 34.3% vs 41.6% | **-7.4 [-12.3, -1.3]** | **-0.071 [-0.122, -0.025]** | -0.49 (-91) | -0.133 / -0.080 / -0.016 |
| last five days (efficiency ratio of H1 closes) | trending (over 0.125) | 1324 (258) | 34.5% vs 37.7% | -3.2 [-9.5, +2.2] | **-0.054 [-0.099, -0.010]** | -0.59 (-152) | -0.119 / +0.005 / -0.075 | 1124 (199) | 31.0% vs 37.3% | **-6.3 [-10.6, -1.5]** | **-0.127 [-0.166, -0.084]** | -0.96 (-191) | -0.163 / -0.117 / -0.109 |
| session (UTC) | Asia 22-07 | 1332 (260) | 32.5% vs 38.1% | **-5.6 [-11.4, -0.4]** | **-0.082 [-0.122, -0.041]** | -1.75 (-455) | -0.076 / -0.081 / -0.089 | 1005 (178) | 32.2% vs 39.3% | **-7.1 [-12.9, -1.6]** | **-0.102 [-0.143, -0.063]** | -0.75 (-133) | -0.133 / -0.118 / -0.074 |
| session (UTC) | London 07-12 | 561 (109) | 38.3% vs 35.6% | +2.8 [-5.6, +11.2] | +0.005 [-0.073, +0.083] | -1.19 (-130) | +0.072 / +0.031 / -0.110 | 697 (124) | 34.3% vs 34.4% | -0.1 [-6.6, +5.7] | **-0.082 [-0.138, -0.027]** | -0.68 (-84) | -0.092 / -0.031 / -0.124 |
| session (UTC) | London + New York 12-16 | 1146 (224) | 35.4% vs 41.0% | -5.5 [-11.3, +0.7] | -0.042 [-0.090, +0.008] | +0.10 (+22) | -0.067 / -0.023 / -0.043 | 1276 (226) | 32.8% vs 39.0% | **-6.2 [-11.5, -1.0]** | **-0.098 [-0.142, -0.053]** | -0.71 (-160) | -0.116 / -0.085 / -0.092 |
| session (UTC) | New York 16-22 | 595 (116) | 36.0% vs 32.0% | +4.0 [-3.0, +11.4] | -0.026 [-0.093, +0.042] | -0.76 (-89) | -0.004 / -0.033 / -0.042 | 418 (74) | 38.3% vs 35.3% | +3.0 [-4.1, +9.5] | -0.007 [-0.083, +0.070] | +0.01 (+1) | -0.107 / -0.033 / +0.098 |
| volatility (H1 ATR vs its 20-day median) | low | 682 (133) | 35.4% vs 38.9% | -3.6 [-9.6, +3.1] | -0.034 [-0.087, +0.021] | -0.44 (-58) | -0.044 / -0.029 / -0.030 | 601 (107) | 33.4% vs 36.9% | -3.5 [-13.3, +3.5] | **-0.095 [-0.162, -0.032]** | -0.38 (-41) | -0.165 / -0.072 / -0.024 |
| volatility (H1 ATR vs its 20-day median) | normal | 2187 (427) | 34.3% vs 37.9% | -3.6 [-7.5, +0.3] | **-0.059 [-0.093, -0.024]** | -1.04 (-445) | -0.042 / -0.043 / -0.088 | 2180 (387) | 34.3% vs 37.9% | **-3.6 [-7.0, -0.6]** | **-0.071 [-0.101, -0.041]** | -0.54 (-209) | -0.086 / -0.061 / -0.073 |
| volatility (H1 ATR vs its 20-day median) | high | 765 (149) | 36.0% vs 35.8% | +0.2 [-8.0, +8.2] | -0.023 [-0.070, +0.029] | -1.00 (-149) | -0.018 / -0.038 / +0.029 | 615 (109) | 31.1% vs 37.6% | **-6.5 [-11.2, -2.4]** | **-0.122 [-0.180, -0.073]** | -1.15 (-126) | -0.128 / -0.164 / -0.087 |

**BTC**

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| side | support (buy) | 3206 (626) | 34.9% vs 37.6% | -2.7 [-8.2, +2.6] | **-0.070 [-0.103, -0.039]** | -0.28 (-174) | -0.067 / -0.079 / -0.060 | 3611 (640) | 36.3% vs 40.7% | **-4.4 [-8.5, -0.9]** | **-0.092 [-0.112, -0.071]** | -0.43 (-273) | -0.126 / -0.090 / -0.068 |
| side | resistance (sell) | 3052 (595) | 36.2% vs 35.9% | +0.3 [-3.3, +4.2] | **-0.050 [-0.082, -0.015]** | -0.12 (-73) | -0.056 / -0.009 / -0.098 | 3454 (612) | 34.0% vs 39.5% | **-5.5 [-9.9, -1.8]** | **-0.124 [-0.154, -0.097]** | -0.64 (-394) | -0.195 / -0.117 / -0.084 |
| levels in the zone | 1 | 3798 (741) | 36.4% vs 37.4% | -1.0 [-4.2, +2.6] | **-0.048 [-0.072, -0.025]** | -0.12 (-85) | -0.047 / -0.003 / -0.109 | 4274 (758) | 36.5% vs 40.7% | **-4.2 [-7.4, -1.3]** | **-0.088 [-0.109, -0.066]** | -0.41 (-309) | -0.114 / -0.104 / -0.050 |
| levels in the zone | 2 | 1703 (332) | 34.2% vs 35.6% | -1.4 [-8.1, +3.0] | **-0.081 [-0.126, -0.039]** | -0.38 (-126) | -0.087 / -0.119 / -0.020 | 2016 (357) | 34.8% vs 40.0% | **-5.2 [-9.7, -0.6]** | **-0.114 [-0.145, -0.082]** | -0.55 (-198) | -0.233 / -0.066 / -0.079 |
| levels in the zone | 3 or more | 757 (148) | 34.3% vs 37.9% | -3.6 [-13.6, +5.3] | **-0.074 [-0.136, -0.015]** | -0.24 (-36) | -0.071 / -0.097 / -0.051 | 775 (137) | 29.0% vs 37.2% | **-8.2 [-15.9, -1.4]** | **-0.204 [-0.263, -0.147]** | -1.16 (-160) | -0.226 / -0.192 / -0.202 |
| zone strength | 1-2 | 1558 (304) | 35.0% vs 40.2% | **-5.2 [-10.2, -0.8]** | **-0.072 [-0.109, -0.033]** | -0.14 (-43) | -0.059 / -0.043 / -0.119 | 1647 (292) | 36.3% vs 42.6% | **-6.3 [-12.1, -1.1]** | **-0.100 [-0.135, -0.070]** | -0.39 (-113) | -0.130 / -0.114 / -0.051 |
| zone strength | 3-4 | 2320 (453) | 36.4% vs 35.4% | +0.9 [-3.4, +4.6] | **-0.047 [-0.079, -0.014]** | -0.16 (-74) | -0.061 / -0.009 / -0.080 | 2728 (484) | 36.9% vs 39.7% | -2.9 [-6.5, +0.7] | **-0.080 [-0.106, -0.050]** | -0.36 (-175) | -0.099 / -0.091 / -0.054 |
| zone strength | 5-6 | 1728 (337) | 35.3% vs 34.7% | +0.6 [-5.6, +6.3] | **-0.063 [-0.104, -0.025]** | -0.27 (-92) | -0.071 / -0.079 / -0.028 | 1964 (348) | 33.2% vs 38.8% | **-5.6 [-10.9, -1.1]** | **-0.136 [-0.170, -0.103]** | -0.74 (-257) | -0.254 / -0.104 / -0.090 |
| zone strength | 7 or more | 652 (127) | 34.5% vs 32.9% | +1.6 [-10.4, +9.8] | **-0.071 [-0.140, -0.001]** | -0.30 (-38) | -0.046 / -0.087 / -0.090 | 726 (129) | 31.7% vs 36.1% | -4.4 [-16.1, +5.0] | **-0.157 [-0.209, -0.109]** | -0.94 (-121) | -0.232 / -0.120 / -0.155 |
| earlier touches | none (first touch) | 1197 (234) | 32.0% vs 39.0% | **-7.0 [-13.6, -3.0]** | **-0.123 [-0.161, -0.082]** | -0.37 (-86) | -0.106 / -0.096 / -0.171 | 1280 (227) | 37.1% vs 41.0% | -3.9 [-10.6, +1.0] | **-0.088 [-0.130, -0.045]** | -0.27 (-61) | -0.164 / -0.084 / -0.017 |
| earlier touches | 1 | 978 (191) | 37.8% vs 42.8% | -5.0 [-10.7, +1.0] | -0.024 [-0.073, +0.024] | -0.00 (-1) | -0.007 / -0.041 / -0.017 | 1034 (183) | 35.0% vs 41.6% | **-6.5 [-12.4, -0.3]** | **-0.119 [-0.168, -0.069]** | -0.57 (-104) | -0.129 / -0.131 / -0.095 |
| earlier touches | 2 | 667 (130) | 36.0% vs 33.9% | +2.2 [-4.6, +9.6] | -0.053 [-0.111, +0.013] | -0.26 (-33) | -0.102 / +0.068 / -0.154 | 711 (126) | 36.8% vs 43.0% | -6.2 [-14.6, +0.8] | **-0.086 [-0.130, -0.041]** | -0.35 (-44) | -0.129 / -0.067 / -0.068 |
| earlier touches | 3 or more | 3416 (667) | 36.0% vs 34.8% | +1.2 [-3.2, +5.0] | **-0.050 [-0.079, -0.024]** | -0.19 (-127) | -0.055 / -0.049 / -0.043 | 4040 (716) | 34.3% vs 38.4% | **-4.1 [-7.2, -1.2]** | **-0.115 [-0.136, -0.095]** | -0.64 (-457) | -0.171 / -0.109 / -0.087 |
| role (not round numbers) | never broken | 2482 (484) | 32.4% vs 40.0% | **-7.6 [-12.4, -3.8]** | **-0.113 [-0.147, -0.078]** | -0.43 (-207) | -0.091 / -0.137 / -0.105 | 2701 (479) | 34.1% vs 39.6% | **-5.5 [-10.4, -1.5]** | **-0.132 [-0.159, -0.104]** | -0.61 (-291) | -0.181 / -0.132 / -0.090 |
| role (not round numbers) | broken once, retested from the other side | 1644 (321) | 39.8% vs 36.5% | +3.3 [-1.4, +8.6] | +0.008 [-0.031, +0.046] | +0.11 (+36) | -0.011 / +0.044 / -0.016 | 1681 (298) | 36.7% vs 43.7% | **-7.1 [-12.1, -1.0]** | **-0.088 [-0.127, -0.054]** | -0.42 (-125) | -0.125 / -0.084 / -0.066 |
| age (not round numbers) | under 1 day | 2102 (410) | 34.7% vs 41.1% | **-6.4 [-10.5, -1.6]** | **-0.078 [-0.114, -0.043]** | -0.25 (-104) | -0.095 / -0.078 / -0.063 | 2269 (402) | 34.7% vs 40.7% | **-6.0 [-10.3, -1.6]** | **-0.122 [-0.150, -0.093]** | -0.59 (-236) | -0.153 / -0.136 / -0.080 |
| age (not round numbers) | 1-5 days | 1279 (250) | 35.4% vs 38.4% | -2.9 [-8.1, +1.8] | **-0.062 [-0.099, -0.025]** | -0.21 (-52) | -0.037 / -0.074 / -0.071 | 1408 (250) | 35.3% vs 43.7% | **-8.4 [-14.9, -1.5]** | **-0.116 [-0.158, -0.071]** | -0.49 (-122) | -0.193 / -0.083 / -0.086 |
| age (not round numbers) | 5-20 days | 574 (112) | 35.4% vs 34.3% | +1.1 [-8.9, +9.9] | -0.057 [-0.115, +0.003] | -0.21 (-24) | -0.018 / -0.066 / -0.103 | 574 (102) | 38.0% vs 34.9% | +3.1 [-5.8, +12.0] | **-0.058 [-0.114, -0.000]** | -0.24 (-24) | -0.055 / -0.063 / -0.054 |
| age (not round numbers) | over 20 days | 171 (33) | 42.7% vs 27.9% | +14.8 [-1.3, +27.6] | +0.055 [-0.055, +0.170] | +0.24 (+8) | +0.042 / +0.103 / -0.055 | 131 (23) | 27.5% vs 32.8% | -5.3 [-22.8, +10.3] | **-0.223 [-0.298, -0.144]** | -1.46 (-34) | -0.269 / -0.222 / -0.167 |
| H4 trend (MACD signal line) | trade with it | 3183 (621) | 36.1% vs 38.3% | -2.2 [-6.4, +2.3] | **-0.049 [-0.081, -0.018]** | -0.15 (-95) | -0.047 / -0.034 / -0.072 | 3621 (642) | 35.5% vs 42.7% | **-7.3 [-11.3, -2.9]** | **-0.103 [-0.125, -0.080]** | -0.55 (-353) | -0.137 / -0.113 / -0.070 |
| H4 trend (MACD signal line) | trade against it | 3075 (600) | 34.9% vs 38.0% | -3.1 [-7.6, +1.4] | **-0.071 [-0.099, -0.041]** | -0.25 (-152) | -0.075 / -0.056 / -0.086 | 3444 (611) | 34.9% vs 38.3% | **-3.4 [-7.8, -0.4]** | **-0.113 [-0.141, -0.086]** | -0.51 (-313) | -0.179 / -0.093 / -0.083 |
| D1 trend (close vs EMA20) | trade with it | 3231 (630) | 35.7% vs 36.7% | -1.0 [-4.8, +3.6] | **-0.055 [-0.083, -0.024]** | -0.17 (-105) | -0.064 / -0.020 / -0.089 | 3623 (642) | 36.0% vs 42.4% | **-6.5 [-10.6, -1.9]** | **-0.096 [-0.120, -0.073]** | -0.52 (-331) | -0.148 / -0.093 / -0.060 |
| D1 trend (close vs EMA20) | trade against it | 3027 (591) | 35.4% vs 37.5% | -2.1 [-6.7, +1.9] | **-0.066 [-0.099, -0.034]** | -0.24 (-142) | -0.060 / -0.070 / -0.067 | 3442 (610) | 34.4% vs 38.8% | **-4.4 [-9.2, -1.0]** | **-0.120 [-0.148, -0.092]** | -0.55 (-335) | -0.170 / -0.113 / -0.092 |
| H4 and D1 trend | with both | 2658 (519) | 36.6% vs 38.4% | -1.8 [-5.5, +3.2] | **-0.042 [-0.074, -0.011]** | -0.10 (-50) | -0.040 / -0.017 / -0.076 | 2951 (523) | 35.4% vs 43.0% | **-7.6 [-12.1, -2.4]** | **-0.104 [-0.133, -0.079]** | -0.56 (-295) | -0.150 / -0.110 / -0.067 |
| H4 and D1 trend | against both | 2502 (488) | 35.6% vs 38.0% | -2.4 [-7.1, +2.3] | **-0.061 [-0.097, -0.028]** | -0.20 (-97) | -0.056 / -0.060 / -0.071 | 2772 (491) | 34.1% vs 38.7% | **-4.7 [-9.9, -1.2]** | **-0.126 [-0.157, -0.097]** | -0.56 (-277) | -0.189 / -0.109 / -0.094 |
| M15 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 917 (179) | 32.1% vs 35.4% | -3.3 [-14.2, +3.5] | **-0.109 [-0.161, -0.057]** | -0.39 (-69) | -0.066 / -0.092 / -0.189 | 970 (172) | 37.8% vs 40.9% | -3.0 [-11.0, +3.3] | **-0.067 [-0.112, -0.022]** | -0.21 (-37) | -0.145 / -0.059 / -0.014 |
| M15 RSI at the touch | 30-50 (50-70) | 3754 (732) | 35.6% vs 37.2% | -1.7 [-5.5, +2.5] | **-0.062 [-0.088, -0.035]** | -0.18 (-134) | -0.066 / -0.048 / -0.078 | 4324 (767) | 34.7% vs 38.7% | **-4.0 [-8.2, -0.2]** | **-0.116 [-0.139, -0.095]** | -0.58 (-443) | -0.159 / -0.113 / -0.088 |
| M15 RSI at the touch | not stretched | 1587 (310) | 37.5% vs 37.2% | +0.3 [-4.8, +5.2] | -0.027 [-0.062, +0.009] | -0.14 (-43) | -0.049 / -0.013 / -0.019 | 1771 (314) | 34.9% vs 40.6% | **-5.7 [-10.3, -1.1]** | **-0.110 [-0.147, -0.077]** | -0.59 (-187) | -0.164 / -0.104 / -0.078 |
| H1 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 632 (123) | 33.2% vs 27.2% | +6.1 [-4.5, +12.9] | **-0.084 [-0.147, -0.016]** | -0.36 (-44) | -0.008 / -0.109 / -0.191 | 547 (97) | 36.9% vs 43.2% | -6.3 [-14.8, +2.7] | **-0.074 [-0.131, -0.002]** | -0.36 (-35) | -0.138 / -0.090 / +0.004 |
| H1 RSI at the touch | 30-50 (50-70) | 3006 (587) | 35.1% vs 39.4% | **-4.3 [-9.2, -0.4]** | **-0.071 [-0.098, -0.042]** | -0.19 (-113) | -0.055 / -0.049 / -0.115 | 3585 (636) | 34.5% vs 39.8% | **-5.3 [-9.3, -1.0]** | **-0.120 [-0.145, -0.097]** | -0.52 (-330) | -0.165 / -0.122 / -0.087 |
| H1 RSI at the touch | not stretched | 2620 (511) | 36.7% vs 37.2% | -0.5 [-4.6, +3.7] | **-0.042 [-0.075, -0.011]** | -0.17 (-89) | -0.086 / -0.024 / -0.018 | 2933 (520) | 35.6% vs 39.3% | -3.6 [-8.1, +0.3] | **-0.099 [-0.130, -0.070]** | -0.58 (-301) | -0.154 / -0.083 / -0.075 |
| RSI divergence (unbroken extremes) | yes | 913 (178) | 32.4% vs 31.4% | +1.1 [-7.8, +9.9] | **-0.111 [-0.163, -0.054]** | -0.36 (-64) | -0.024 / -0.156 / -0.137 | 952 (169) | 33.4% vs 42.0% | **-8.5 [-18.0, -0.7]** | **-0.139 [-0.191, -0.092]** | -0.68 (-115) | -0.173 / -0.139 / -0.112 |
| RSI divergence (unbroken extremes) | no | 1349 (263) | 32.4% vs 38.3% | -5.9 [-12.9, +0.5] | **-0.114 [-0.156, -0.069]** | -0.49 (-129) | -0.148 / -0.107 / -0.090 | 1521 (270) | 34.3% vs 38.9% | **-4.6 [-12.4, -0.5]** | **-0.129 [-0.168, -0.090]** | -0.58 (-155) | -0.182 / -0.124 / -0.090 |
| approach in the last hour | under 0.5 ATR | 1340 (261) | 36.5% vs 36.7% | -0.2 [-6.1, +6.1] | **-0.046 [-0.087, -0.006]** | -0.20 (-53) | -0.071 / -0.013 / -0.059 | 1586 (281) | 34.4% vs 36.7% | -2.3 [-6.4, +2.5] | **-0.118 [-0.157, -0.077]** | -0.58 (-164) | -0.137 / -0.135 / -0.091 |
| approach in the last hour | 0.5-1.5 ATR | 3472 (677) | 36.4% vs 36.7% | -0.4 [-4.0, +3.5] | **-0.049 [-0.076, -0.022]** | -0.11 (-74) | -0.029 / -0.051 / -0.072 | 3949 (700) | 35.7% vs 42.3% | **-6.6 [-10.5, -2.3]** | **-0.101 [-0.124, -0.077]** | -0.51 (-356) | -0.158 / -0.087 / -0.071 |
| approach in the last hour | over 1.5 ATR | 1424 (278) | 32.9% vs 42.0% | **-9.1 [-16.2, -2.1]** | **-0.097 [-0.135, -0.059]** | -0.42 (-117) | -0.126 / -0.060 / -0.113 | 1516 (269) | 34.8% vs 40.2% | **-5.4 [-11.8, -0.0]** | **-0.114 [-0.152, -0.077]** | -0.54 (-144) | -0.184 / -0.108 / -0.070 |
| last five days (efficiency ratio of H1 closes) | ranging (under 0.06) | 2344 (457) | 35.1% vs 36.9% | -1.8 [-6.3, +2.5] | **-0.070 [-0.100, -0.036]** | -0.24 (-110) | -0.074 / -0.077 / -0.057 | 2676 (474) | 33.6% vs 41.1% | **-7.5 [-12.0, -2.4]** | **-0.137 [-0.168, -0.107]** | -0.57 (-269) | -0.240 / -0.126 / -0.085 |
| last five days (efficiency ratio of H1 closes) | in between | 1967 (384) | 36.2% vs 38.4% | -2.2 [-7.3, +2.2] | **-0.052 [-0.088, -0.019]** | -0.18 (-67) | -0.077 / -0.016 / -0.070 | 2044 (362) | 37.0% vs 38.4% | -1.4 [-8.5, +3.2] | **-0.076 [-0.108, -0.043]** | -0.48 (-172) | -0.060 / -0.095 / -0.068 |
| last five days (efficiency ratio of H1 closes) | trending (over 0.125) | 1947 (380) | 35.4% vs 34.2% | +1.2 [-4.9, +6.3] | **-0.056 [-0.097, -0.018]** | -0.18 (-69) | -0.037 / -0.035 / -0.129 | 2345 (416) | 35.4% vs 40.9% | **-5.5 [-9.2, -0.8]** | **-0.103 [-0.130, -0.077]** | -0.54 (-225) | -0.153 / -0.088 / -0.068 |
| session (UTC) | Asia 22-07 | 1949 (380) | 33.9% vs 38.9% | **-5.0 [-9.3, -0.3]** | **-0.087 [-0.120, -0.052]** | -0.29 (-109) | -0.103 / -0.078 / -0.083 | 2036 (361) | 33.5% vs 41.6% | **-8.1 [-13.5, -3.0]** | **-0.133 [-0.168, -0.099]** | -0.64 (-232) | -0.148 / -0.137 / -0.118 |
| session (UTC) | London 07-12 | 926 (181) | 35.1% vs 37.7% | -2.6 [-10.9, +2.5] | **-0.072 [-0.123, -0.022]** | -0.34 (-61) | -0.093 / -0.058 / -0.064 | 1063 (188) | 34.3% vs 37.6% | -3.2 [-11.8, +4.4] | **-0.129 [-0.175, -0.080]** | -0.52 (-98) | -0.194 / -0.128 / -0.077 |
| session (UTC) | London + New York 12-16 | 1929 (376) | 35.0% vs 36.1% | -1.1 [-6.6, +3.6] | **-0.070 [-0.103, -0.039]** | -0.25 (-94) | -0.057 / -0.051 / -0.105 | 2029 (360) | 36.0% vs 40.4% | -4.4 [-9.8, +0.2] | **-0.098 [-0.126, -0.070]** | -0.48 (-171) | -0.167 / -0.090 / -0.054 |
| session (UTC) | New York 16-22 | 1454 (284) | 38.8% vs 34.3% | +4.5 [-1.7, +12.4] | -0.003 [-0.042, +0.042] | +0.06 (+18) | -0.005 / +0.016 / -0.033 | 1937 (343) | 36.5% vs 39.6% | -3.1 [-8.4, +1.6] | **-0.081 [-0.107, -0.051]** | -0.48 (-165) | -0.136 / -0.069 / -0.055 |
| volatility (H1 ATR vs its 20-day median) | low | 1663 (324) | 30.8% vs 38.7% | **-7.9 [-12.0, -4.0]** | **-0.148 [-0.183, -0.109]** | -0.44 (-142) | -0.142 / -0.126 / -0.187 | 1750 (310) | 34.6% vs 39.5% | **-4.9 [-10.1, -0.8]** | **-0.145 [-0.194, -0.100]** | -0.45 (-141) | -0.261 / -0.141 / -0.076 |
| volatility (H1 ATR vs its 20-day median) | normal | 3364 (656) | 36.4% vs 38.3% | -1.8 [-5.5, +1.5] | **-0.045 [-0.071, -0.018]** | -0.22 (-147) | -0.055 / -0.034 / -0.048 | 3586 (636) | 35.6% vs 39.9% | **-4.3 [-7.9, -0.8]** | **-0.100 [-0.122, -0.078]** | -0.48 (-305) | -0.119 / -0.100 / -0.084 |
| volatility (H1 ATR vs its 20-day median) | high | 1231 (240) | 39.5% vs 30.2% | +9.3 [-2.6, +17.7] | +0.019 [-0.026, +0.058] | +0.18 (+43) | +0.009 / +0.043 / -0.005 | 1729 (307) | 34.9% vs 41.2% | -6.3 [-14.2, +0.6] | **-0.086 [-0.114, -0.056]** | -0.72 (-220) | -0.136 / -0.077 / -0.063 |

Not one row is above zero in both periods. On DEV 45 of the 46 rows are negative in gold and 43 in BTC; on
CONFIRM all 46 are negative on both symbols. Going through what a trader would look at:

- **Trend.** Buying a support in an uptrend and selling a resistance in a downtrend (H4 and D1 agreeing) lost
  -0.035 / -0.081 ATR in gold and -0.042 / -0.104 in BTC; against both trends -0.064 / -0.098 and -0.061 / -0.126. With
  the trend is less bad than against it, in every column, and still loses.
- **First touch, unbroken level.** A first touch (-0.037 / -0.116 gold, -0.123 / -0.088 BTC) is no better than a
  later one. A level that has never been broken is where the bounce trade does worst with the largest
  samples (-0.060 / -0.141 and -0.113 / -0.132), 4 to 8 points below the control in every column.
- **Confluence.** Zones of three or more levels lost -0.157 / -0.062 in gold and -0.074 / -0.204 in BTC; the
  strongest zones (strength 7 or more) -0.148 / -0.067 and -0.071 / -0.157. More levels at one price do not make it hold.
- **RSI.** With the M15 RSI stretched (under 30 at a support, over 70 at a resistance): -0.024 / -0.046 gold,
  -0.109 / -0.067 BTC; with the H1 RSI stretched -0.038 / -0.045 and -0.084 / -0.074.
- **Divergence.** Price back at an old extreme with the RSI diverging in the trade's favour lost
  -0.130 / -0.161 in gold and -0.111 / -0.139 in BTC, with the interval below zero in all four columns: it is
  not a reason to expect the level to hold.
- **Speed, market, time.** A slow approach (-0.023 / -0.063, -0.046 / -0.118), a market that has gone sideways for
  five days (-0.032 / -0.058, -0.070 / -0.137) lose. So does every session, except gold's London morning on DEV
  (+0.005, interval from -0.07 to +0.08), which made -0.082 on CONFIRM. The late New York session is the least
  bad in three of the four columns; no session is above zero twice.

### 4.4 Waiting for the level to hold, and the retest

The rejection trade is entered only after an M15 bar has closed half an ATR back from the touched level. That
happened after about half of all touches (gold 48 / 47 %, BTC 51 / 50 %; DEV / CONFIRM); in the others the level was
broken first or price stayed at it for four hours.

**Gold, rejection**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all rejections | 1727 (337) | 49.5% vs 48.5% | +1.0 [-4.9, +6.8] | -0.026 [-0.074, +0.021] | -0.20 (-66) | +0.020 / -0.014 / -0.088 | 1611 (286) | 50.6% vs 48.3% | +2.3 [-2.3, +7.3] | -0.019 [-0.073, +0.030] | -0.28 (-81) | -0.044 / -0.013 / -0.004 |
| H1 swing (not H4) | 797 (156) | 50.8% vs 49.1% | +1.7 [-6.0, +8.2] | -0.001 [-0.075, +0.080] | +0.07 (+10) | -0.001 / +0.042 / -0.049 | 812 (144) | 52.1% vs 47.4% | +4.7 [-2.7, +12.6] | +0.008 [-0.067, +0.088] | -0.03 (-4) | -0.019 / -0.025 / +0.063 |
| H4 swing (not D1) | 293 (57) | 47.1% vs 46.9% | +0.1 [-11.6, +10.6] | -0.074 [-0.195, +0.058] | -0.71 (-41) | -0.094 / -0.021 / -0.120 | 415 (74) | 50.4% vs 46.6% | +3.8 [-6.2, +13.9] | -0.022 [-0.127, +0.085] | -0.06 (-5) | -0.153 / +0.071 / -0.011 |
| D1 swing | 47 (9) | 50.0% vs 47.5% | +2.5 [-25.0, +28.1] | -0.021 [-0.308, +0.270] | -3.53 (-32) | +0.584 / -0.065 / -0.310 | 56 (10) | 44.6% vs 46.4% | -1.7 [-19.5, +18.4] | -0.137 [-0.447, +0.127] | -1.69 (-17) | -0.324 / +0.047 / -0.281 |
| previous-day high / low | 239 (47) | 47.5% vs 50.1% | -2.7 [-15.0, +11.3] | -0.057 [-0.204, +0.104] | +0.25 (+12) | -0.018 / +0.054 / -0.181 | 276 (49) | 48.5% vs 52.1% | -3.6 [-13.1, +9.9] | -0.061 [-0.182, +0.054] | -0.32 (-16) | -0.142 / +0.014 / -0.085 |
| previous-day close | 207 (40) | 51.2% vs 51.1% | +0.2 [-14.7, +14.2] | +0.011 [-0.146, +0.157] | +1.33 (+54) | -0.007 / +0.058 / -0.049 | 177 (31) | 52.0% vs 54.5% | -2.5 [-13.6, +10.9] | +0.010 [-0.138, +0.161] | +0.24 (+8) | +0.096 / -0.071 / +0.034 |
| previous-week high / low | 63 (12) | 54.0% vs 56.4% | -2.5 [-23.3, +20.8] | +0.067 [-0.240, +0.355] | +0.55 (+7) | +0.026 / +0.205 / -0.091 | 61 (11) | 47.5% vs 43.2% | +4.3 [-17.2, +24.3] | -0.076 [-0.327, +0.196] | -0.56 (-6) | -0.539 / +0.244 / -0.132 |
| previous-week close | 68 (13) | 51.5% vs 58.1% | -6.6 [-25.4, +14.8] | +0.022 [-0.202, +0.237] | +1.25 (+17) | +0.154 / -0.055 / +0.095 | 69 (12) | 55.1% vs 57.8% | -2.7 [-29.4, +18.5] | +0.072 [-0.226, +0.308] | +0.37 (+5) | -0.209 / +0.228 / +0.030 |
| round number, minor | 350 (68) | 45.5% vs 47.2% | -1.8 [-13.1, +8.1] | **-0.110 [-0.228, -0.001]** | -2.94 (-201) | +0.063 / -0.127 / -0.274 | 152 (27) | 55.3% vs 45.1% | +10.2 [-4.8, +23.7] | +0.080 [-0.093, +0.246] | +0.71 (+19) | +0.221 / -0.007 / +0.050 |
| round number, major | 346 (68) | 53.2% vs 47.7% | +5.5 [-4.5, +17.0] | +0.049 [-0.058, +0.149] | +3.19 (+216) | -0.002 / +0.023 / +0.145 | 132 (23) | 41.5% vs 44.9% | -3.4 [-15.6, +6.0] | **-0.189 [-0.359, -0.025]** | -2.54 (-60) | -0.237 / -0.156 / -0.191 |
| any H4 / D1 swing or day / week high / low | 481 (94) | 47.2% vs 47.8% | -0.7 [-11.1, +7.3] | -0.069 [-0.174, +0.048] | -0.37 (-35) | -0.037 / -0.024 / -0.141 | 571 (101) | 49.7% vs 48.0% | +1.7 [-6.9, +9.9] | -0.034 [-0.130, +0.060] | -0.26 (-26) | -0.185 / +0.076 / -0.029 |
| first touch of the zone | 407 (79) | 51.7% vs 47.2% | +4.5 [-4.2, +12.6] | +0.020 [-0.061, +0.093] | +0.43 (+34) | -0.039 / +0.092 / +0.003 | 482 (85) | 48.5% vs 44.7% | +3.8 [-3.8, +11.2] | -0.061 [-0.155, +0.040] | -0.60 (-52) | -0.108 / -0.064 / -0.015 |
| zone touched before | 1320 (258) | 48.8% vs 49.1% | -0.4 [-6.5, +6.1] | -0.040 [-0.096, +0.018] | -0.39 (-100) | +0.042 / -0.041 / -0.117 | 1129 (200) | 51.4% vs 48.4% | +3.1 [-2.3, +8.9] | -0.001 [-0.067, +0.060] | -0.15 (-29) | -0.013 / +0.007 / +0.001 |
| with the H4 trend | 898 (175) | 51.4% vs 50.5% | +0.9 [-5.6, +8.2] | +0.014 [-0.055, +0.093] | +0.41 (+72) | +0.062 / +0.070 / -0.116 | 908 (161) | 50.4% vs 49.9% | +0.5 [-5.6, +7.2] | -0.022 [-0.094, +0.052] | -0.48 (-78) | -0.025 / -0.024 / -0.019 |
| against the H4 trend | 829 (162) | 47.3% vs 48.7% | -1.3 [-8.8, +5.5] | -0.069 [-0.147, +0.000] | -0.86 (-138) | -0.030 / -0.103 / -0.059 | 703 (125) | 50.7% vs 47.5% | +3.3 [-3.3, +9.4] | -0.015 [-0.098, +0.073] | -0.02 (-3) | -0.066 / +0.001 / +0.018 |
| with the D1 trend | 920 (180) | 51.4% vs 50.7% | +0.7 [-7.0, +8.2] | +0.013 [-0.058, +0.086] | -0.25 (-46) | +0.066 / +0.020 / -0.056 | 910 (161) | 48.0% vs 48.4% | -0.4 [-7.8, +6.8] | -0.071 [-0.141, +0.007] | -0.81 (-131) | -0.148 / -0.023 / -0.048 |
| against the D1 trend | 807 (157) | 47.3% vs 45.9% | +1.3 [-5.9, +8.9] | -0.070 [-0.155, +0.009] | -0.13 (-21) | -0.040 / -0.052 / -0.121 | 701 (124) | 53.9% vs 49.2% | +4.7 [-1.4, +10.7] | +0.048 [-0.038, +0.134] | +0.40 (+50) | +0.091 / -0.001 / +0.061 |
| last five days ranging | 564 (110) | 49.5% vs 54.4% | -5.0 [-12.9, +6.4] | -0.027 [-0.101, +0.055] | +0.17 (+19) | +0.036 / +0.088 / -0.194 | 595 (105) | 50.5% vs 43.2% | +7.4 [-0.4, +14.7] | -0.023 [-0.112, +0.061] | -0.49 (-52) | -0.029 / +0.012 / -0.056 |
| last five days trending | 619 (121) | 49.7% vs 47.3% | +2.4 [-7.5, +11.8] | -0.016 [-0.108, +0.062] | +0.24 (+29) | -0.031 / +0.018 / -0.066 | 513 (91) | 47.8% vs 48.3% | -0.5 [-8.9, +7.7] | -0.071 [-0.169, +0.023] | -0.49 (-45) | -0.123 / -0.064 / -0.031 |

**BTC, rejection**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all rejections | 3177 (620) | 47.9% vs 51.1% | -3.2 [-6.9, +0.5] | **-0.074 [-0.111, -0.037]** | -0.38 (-238) | -0.080 / -0.075 / -0.066 | 3552 (630) | 48.8% vs 50.2% | -1.3 [-5.3, +2.3] | **-0.094 [-0.129, -0.059]** | -0.44 (-277) | -0.175 / -0.096 / -0.028 |
| H1 swing (not H4) | 1436 (280) | 48.5% vs 54.8% | **-6.2 [-11.8, -0.6]** | **-0.063 [-0.117, -0.012]** | -0.33 (-91) | -0.054 / -0.061 / -0.073 | 1492 (265) | 48.7% vs 53.8% | -5.1 [-11.1, +0.9] | **-0.103 [-0.160, -0.047]** | -0.38 (-100) | -0.192 / -0.106 / -0.017 |
| H4 swing (not D1) | 581 (113) | 48.3% vs 45.3% | +3.0 [-8.8, +11.0] | -0.066 [-0.166, +0.027] | -0.33 (-37) | -0.093 / -0.073 / -0.015 | 635 (113) | 48.2% vs 52.4% | -4.2 [-14.7, +4.0] | **-0.111 [-0.184, -0.037]** | -0.48 (-54) | -0.171 / -0.111 / -0.060 |
| D1 swing | 139 (27) | 50.7% vs 48.3% | +2.5 [-19.9, +28.0] | -0.015 [-0.243, +0.231] | +0.34 (+9) | +0.190 / -0.113 / -0.167 | 119 (21) | 46.2% vs 55.4% | -9.2 [-25.7, +16.2] | -0.127 [-0.355, +0.101] | -0.62 (-13) | -0.411 / -0.425 / +0.205 |
| previous-day high / low | 416 (81) | 44.7% vs 56.7% | **-12.1 [-24.0, -2.5]** | **-0.140 [-0.248, -0.039]** | -0.56 (-46) | -0.021 / -0.155 / -0.252 | 445 (79) | 48.0% vs 52.7% | -4.7 [-14.3, +5.9] | **-0.114 [-0.214, -0.018]** | -0.67 (-53) | -0.187 / -0.112 / -0.059 |
| previous-day close | 221 (43) | 39.1% vs 56.6% | **-17.5 [-28.7, -5.4]** | **-0.249 [-0.383, -0.102]** | -1.19 (-51) | -0.241 / -0.321 / -0.160 | 256 (45) | 41.3% vs 55.2% | **-13.9 [-27.1, -4.8]** | **-0.248 [-0.377, -0.135]** | -1.56 (-71) | -0.368 / -0.203 / -0.199 |
| previous-week high / low | 97 (19) | 36.1% vs 45.2% | -9.1 [-35.8, +14.1] | **-0.309 [-0.497, -0.122]** | -1.54 (-29) | -0.462 / -0.213 / -0.238 | 88 (16) | 48.9% vs 38.6% | +10.2 [-8.4, +28.4] | -0.090 [-0.288, +0.124] | -0.26 (-4) | -0.481 / -0.189 / +0.286 |
| previous-week close | 76 (15) | 51.3% vs 58.0% | -6.7 [-21.1, +11.8] | -0.004 [-0.247, +0.229] | +0.03 (+0) | +0.320 / -0.315 / -0.082 | 66 (12) | 45.5% vs 62.7% | **-17.2 [-39.0, -1.0]** | -0.153 [-0.407, +0.118] | -0.88 (-10) | -0.029 / -0.180 / -0.187 |
| round number, minor | 1100 (215) | 49.1% vs 53.2% | -4.2 [-10.4, +2.4] | -0.047 [-0.110, +0.019] | -0.30 (-64) | -0.085 / -0.065 / +0.050 | 1367 (242) | 49.4% vs 50.2% | -0.8 [-5.6, +4.5] | **-0.074 [-0.120, -0.025]** | -0.45 (-109) | -0.175 / -0.049 / -0.029 |
| round number, major | 269 (52) | 42.5% vs 48.9% | -6.4 [-19.6, +6.4] | **-0.181 [-0.299, -0.055]** | -1.19 (-62) | -0.231 / -0.057 / -0.315 | 322 (57) | 50.3% vs 48.4% | +1.9 [-7.7, +12.9] | -0.053 [-0.162, +0.051] | -0.29 (-17) | +0.023 / -0.143 / -0.008 |
| any H4 / D1 swing or day / week high / low | 929 (181) | 47.7% vs 49.1% | -1.3 [-10.6, +5.6] | **-0.077 [-0.156, -0.007]** | -0.25 (-45) | -0.027 / -0.085 / -0.134 | 976 (173) | 47.7% vs 53.6% | -5.8 [-13.8, +1.8] | **-0.117 [-0.181, -0.057]** | -0.54 (-94) | -0.182 / -0.174 / -0.014 |
| first touch of the zone | 576 (112) | 49.7% vs 48.1% | +1.6 [-6.2, +7.7] | -0.039 [-0.117, +0.043] | -0.17 (-19) | +0.030 / -0.074 / -0.054 | 668 (118) | 48.2% vs 51.6% | -3.4 [-10.8, +5.2] | **-0.115 [-0.193, -0.035]** | -0.35 (-42) | -0.293 / -0.069 / +0.008 |
| zone touched before | 2601 (507) | 47.5% vs 52.4% | **-4.9 [-9.2, -1.0]** | **-0.082 [-0.127, -0.040]** | -0.43 (-218) | -0.100 / -0.075 / -0.069 | 2884 (511) | 49.0% vs 50.3% | -1.3 [-5.3, +2.8] | **-0.090 [-0.125, -0.053]** | -0.46 (-235) | -0.145 / -0.103 / -0.035 |
| with the H4 trend | 1615 (315) | 48.6% vs 52.4% | -3.8 [-9.9, +2.6] | **-0.059 [-0.113, -0.003]** | -0.33 (-104) | -0.058 / -0.055 / -0.064 | 1851 (328) | 48.6% vs 54.0% | -5.3 [-11.4, +0.7] | **-0.098 [-0.159, -0.035]** | -0.57 (-186) | -0.148 / -0.116 / -0.043 |
| against the H4 trend | 1562 (305) | 47.1% vs 50.9% | -3.9 [-8.7, +1.5] | **-0.091 [-0.137, -0.040]** | -0.44 (-134) | -0.100 / -0.096 / -0.069 | 1701 (302) | 49.0% vs 46.4% | +2.6 [-4.8, +7.5] | **-0.090 [-0.148, -0.033]** | -0.30 (-91) | -0.203 / -0.076 / -0.011 |
| with the D1 trend | 1649 (322) | 47.7% vs 51.2% | -3.6 [-9.9, +2.7] | **-0.078 [-0.134, -0.021]** | -0.35 (-111) | -0.095 / -0.064 / -0.076 | 1866 (331) | 49.8% vs 52.0% | -2.2 [-7.7, +4.3] | **-0.076 [-0.132, -0.016]** | -0.37 (-123) | -0.203 / -0.031 / -0.012 |
| against the D1 trend | 1528 (298) | 48.1% vs 52.4% | -4.3 [-8.8, +1.1] | **-0.071 [-0.124, -0.013]** | -0.42 (-126) | -0.066 / -0.087 / -0.053 | 1686 (299) | 47.7% vs 49.2% | -1.5 [-9.3, +4.0] | **-0.115 [-0.179, -0.051]** | -0.51 (-154) | -0.140 / -0.163 / -0.045 |
| last five days ranging | 1149 (224) | 48.2% vs 47.0% | +1.2 [-6.6, +9.1] | **-0.066 [-0.130, -0.002]** | -0.31 (-70) | -0.083 / -0.096 / -0.014 | 1307 (232) | 47.7% vs 52.9% | -5.2 [-10.7, +1.5] | **-0.119 [-0.170, -0.069]** | -0.45 (-105) | -0.209 / -0.104 / -0.077 |
| last five days trending | 1005 (196) | 49.1% vs 50.2% | -1.0 [-8.8, +6.2] | -0.047 [-0.112, +0.013] | -0.33 (-66) | -0.059 / -0.003 / -0.109 | 1181 (209) | 47.1% vs 46.6% | +0.4 [-7.0, +6.6] | **-0.126 [-0.182, -0.067]** | -0.65 (-136) | -0.201 / -0.137 / -0.021 |

**Gold, retest of a broken level**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all retests | 959 (187) | 36.4% vs 37.3% | -0.9 [-6.7, +6.3] | -0.022 [-0.084, +0.037] | +0.00 (+1) | -0.043 / +0.036 / -0.071 | 1184 (210) | 37.4% vs 39.8% | -2.4 [-7.2, +3.1] | -0.023 [-0.061, +0.013] | -0.26 (-54) | -0.041 / -0.001 / -0.029 |
| H1 swing (not H4) | 539 (105) | 34.7% vs 37.1% | -2.5 [-8.2, +6.9] | -0.048 [-0.115, +0.016] | -0.59 (-62) | -0.047 / +0.001 / -0.098 | 647 (115) | 38.4% vs 36.1% | +2.3 [-4.7, +9.3] | -0.009 [-0.070, +0.047] | -0.12 (-14) | -0.023 / +0.003 / -0.006 |
| H4 swing (not D1) | 252 (49) | 40.6% vs 41.4% | -0.8 [-14.4, +10.7] | +0.040 [-0.072, +0.150] | +2.07 (+102) | -0.068 / +0.103 / +0.052 | 339 (60) | 37.4% vs 42.2% | -4.7 [-12.3, +5.9] | -0.017 [-0.097, +0.061] | -0.35 (-21) | -0.040 / +0.029 / -0.048 |
| D1 swing | 40 (8) | 30.0% vs 33.5% | -3.5 [-28.9, +16.8] | -0.132 [-0.402, +0.162] | -8.73 (-68) | +0.587 / -0.328 / -0.294 | 50 (9) | 34.7% vs 29.5% | +5.2 [-24.3, +31.0] | -0.072 [-0.303, +0.136] | -0.48 (-4) | -0.258 / -0.067 / +0.046 |
| previous-day high / low | 154 (30) | 35.3% vs 36.2% | -0.9 [-14.9, +9.9] | -0.049 [-0.178, +0.089] | +0.97 (+29) | -0.180 / +0.149 / -0.111 | 196 (35) | 34.9% vs 37.6% | -2.7 [-15.6, +9.4] | -0.074 [-0.180, +0.031] | -0.82 (-29) | -0.014 / -0.026 / -0.212 |
| previous-day close | 158 (31) | 36.1% vs 38.5% | -2.4 [-16.3, +14.6] | -0.023 [-0.163, +0.107] | +1.11 (+34) | -0.140 / +0.181 / -0.155 | 172 (30) | 33.9% vs 49.5% | -15.6 [-26.0, +2.8] | -0.089 [-0.185, +0.009] | -0.40 (-12) | -0.119 / -0.121 / -0.012 |
| previous-week high / low | 47 (9) | 36.2% vs 36.5% | -0.4 [-27.8, +20.1] | -0.025 [-0.276, +0.192] | +0.42 (+4) | +0.186 / -0.068 / -0.197 | 51 (9) | 30.0% vs 36.3% | -6.3 [-27.2, +11.7] | -0.128 [-0.344, +0.081] | -1.18 (-11) | -0.476 / +0.033 / -0.096 |
| previous-week close | 52 (10) | 36.5% vs 42.3% | -5.8 [-37.0, +14.4] | -0.025 [-0.241, +0.143] | +1.59 (+16) | -0.043 / +0.024 / -0.083 | 67 (12) | 49.3% vs 60.6% | -11.4 [-30.9, +11.6] | +0.156 [-0.096, +0.357] | +0.53 (+6) | +0.100 / +0.193 / +0.128 |
| within 4 h of the break | 323 (63) | 36.3% vs 32.6% | +3.7 [-7.4, +13.8] | -0.032 [-0.124, +0.057] | -1.10 (-69) | -0.073 / +0.001 / -0.040 | 400 (71) | 37.7% vs 41.3% | -3.6 [-11.3, +5.7] | -0.027 [-0.101, +0.050] | -0.27 (-19) | +0.026 / +0.018 / -0.135 |
| 4-24 h after the break | 359 (70) | 33.8% vs 38.1% | -4.3 [-15.7, +3.7] | -0.072 [-0.165, +0.016] | -0.17 (-12) | -0.138 / +0.129 / -0.212 | 394 (70) | 36.6% vs 40.6% | -4.0 [-15.2, +5.8] | -0.045 [-0.136, +0.049] | -0.38 (-26) | -0.148 / -0.009 / +0.027 |
| more than a day after the break | 277 (54) | 39.9% vs 27.8% | +12.0 [-0.0, +22.1] | +0.052 [-0.059, +0.162] | +1.51 (+82) | +0.135 / -0.030 / +0.062 | 390 (69) | 37.9% vs 31.7% | +6.2 [-3.5, +14.0] | +0.003 [-0.066, +0.072] | -0.12 (-9) | -0.005 / -0.010 / +0.025 |
| first touch since the break | 630 (123) | 36.8% vs 34.8% | +2.0 [-4.9, +9.6] | -0.023 [-0.090, +0.049] | +0.23 (+28) | -0.078 / +0.060 / -0.072 | 765 (136) | 38.6% vs 39.4% | -0.8 [-7.0, +5.2] | -0.009 [-0.064, +0.051] | -0.10 (-13) | -0.037 / +0.040 / -0.029 |
| later touch since the break | 329 (64) | 35.7% vs 49.7% | -14.0 [-25.2, +0.2] | -0.022 [-0.121, +0.077] | -0.42 (-27) | +0.020 / -0.017 / -0.069 | 419 (74) | 35.2% vs 36.9% | -1.7 [-9.6, +7.5] | -0.050 [-0.115, +0.017] | -0.55 (-41) | -0.049 / -0.064 / -0.029 |
| with the H4 trend | 566 (110) | 37.4% vs 43.0% | -5.7 [-12.9, +5.5] | -0.004 [-0.087, +0.078] | +0.66 (+73) | -0.038 / +0.053 / -0.041 | 710 (126) | 37.3% vs 41.5% | -4.2 [-10.2, +3.3] | -0.019 [-0.070, +0.032] | -0.39 (-49) | -0.055 / +0.021 / -0.024 |
| against the H4 trend | 393 (77) | 35.1% vs 32.9% | +2.1 [-8.5, +13.4] | -0.049 [-0.138, +0.024] | -0.94 (-72) | -0.051 / +0.008 / -0.102 | 474 (84) | 37.6% vs 35.9% | +1.6 [-6.7, +9.4] | -0.030 [-0.102, +0.039] | -0.05 (-5) | -0.021 / -0.031 / -0.038 |

**BTC, retest of a broken level**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all retests | 1644 (321) | 39.8% vs 36.5% | +3.3 [-1.4, +8.6] | +0.008 [-0.031, +0.046] | +0.11 (+36) | -0.011 / +0.044 / -0.016 | 1681 (298) | 36.7% vs 43.7% | **-7.1 [-12.1, -1.0]** | **-0.088 [-0.127, -0.054]** | -0.42 (-125) | -0.125 / -0.084 / -0.066 |
| H1 swing (not H4) | 969 (189) | 40.7% vs 37.6% | +3.1 [-3.9, +10.0] | +0.023 [-0.024, +0.068] | +0.16 (+29) | -0.064 / +0.067 / +0.043 | 999 (177) | 38.0% vs 43.7% | -5.7 [-11.4, +1.7] | **-0.069 [-0.112, -0.027]** | -0.27 (-49) | -0.112 / -0.027 / -0.080 |
| H4 swing (not D1) | 424 (83) | 39.4% vs 33.9% | +5.5 [-3.7, +15.1] | +0.002 [-0.078, +0.077] | +0.14 (+11) | +0.090 / -0.043 / -0.073 | 431 (76) | 36.0% vs 41.4% | -5.4 [-16.1, +6.7] | **-0.099 [-0.181, -0.023]** | -0.57 (-44) | -0.132 / -0.168 / -0.004 |
| D1 swing | 93 (18) | 45.7% vs 39.1% | +6.6 [-14.5, +23.9] | +0.106 [-0.051, +0.256] | +0.64 (+12) | +0.077 / +0.203 / -0.060 | 81 (14) | 34.6% vs 43.6% | -9.0 [-27.9, +11.0] | -0.106 [-0.243, +0.011] | -1.02 (-15) | -0.259 / -0.083 / -0.068 |
| previous-day high / low | 277 (54) | 34.8% vs 38.0% | -3.3 [-12.7, +8.3] | -0.075 [-0.163, +0.011] | -0.27 (-14) | -0.026 / -0.091 / -0.109 | 248 (44) | 32.7% vs 36.2% | -3.5 [-14.1, +6.6] | **-0.156 [-0.254, -0.060]** | -1.05 (-46) | -0.197 / -0.132 / -0.145 |
| previous-day close | 190 (37) | 35.3% vs 37.4% | -2.2 [-14.6, +14.0] | -0.069 [-0.178, +0.037] | -0.17 (-6) | -0.130 / +0.070 / -0.158 | 202 (36) | 32.7% vs 50.7% | **-18.0 [-32.4, -4.1]** | **-0.149 [-0.253, -0.051]** | -0.58 (-21) | -0.154 / -0.164 / -0.128 |
| previous-week high / low | 64 (12) | 46.9% vs 39.2% | +7.7 [-12.3, +26.0] | +0.123 [-0.112, +0.320] | +0.50 (+6) | +0.140 / +0.168 / +0.022 | 64 (11) | 43.8% vs 27.3% | +16.4 [-4.0, +34.0] | +0.038 [-0.112, +0.189] | +0.02 (+0) | -0.089 / +0.010 / +0.150 |
| previous-week close | 61 (12) | 44.3% vs 44.1% | +0.2 [-18.6, +31.1] | +0.077 [-0.189, +0.267] | +0.69 (+8) | -0.019 / +0.372 / -0.339 | 53 (9) | 34.0% vs 57.4% | -23.4 [-48.5, +4.2] | -0.125 [-0.357, +0.084] | -0.09 (-1) | +0.025 / -0.081 / -0.286 |
| within 4 h of the break | 556 (108) | 41.9% vs 38.4% | +3.4 [-3.7, +12.8] | +0.038 [-0.029, +0.116] | +0.10 (+11) | -0.028 / +0.117 / +0.017 | 603 (107) | 36.8% vs 39.5% | -2.7 [-10.6, +5.2] | **-0.089 [-0.151, -0.033]** | -0.40 (-43) | -0.124 / -0.096 / -0.053 |
| 4-24 h after the break | 652 (127) | 39.2% vs 37.9% | +1.3 [-7.1, +8.8] | -0.005 [-0.059, +0.047] | +0.10 (+13) | -0.051 / +0.036 / -0.012 | 634 (112) | 35.4% vs 42.9% | **-7.6 [-16.6, -0.7]** | **-0.106 [-0.163, -0.045]** | -0.60 (-68) | -0.135 / -0.094 / -0.098 |
| more than a day after the break | 436 (85) | 38.1% vs 36.1% | +2.0 [-7.2, +10.8] | -0.011 [-0.084, +0.067] | +0.14 (+12) | +0.060 / -0.027 / -0.081 | 444 (79) | 38.3% vs 42.9% | -4.7 [-13.8, +7.6] | -0.063 [-0.146, +0.017] | -0.18 (-15) | -0.110 / -0.054 / -0.036 |
| first touch since the break | 1014 (198) | 40.6% vs 37.8% | +2.8 [-3.4, +9.3] | +0.018 [-0.041, +0.078] | +0.08 (+15) | -0.054 / +0.073 / +0.027 | 1064 (189) | 38.2% vs 43.8% | -5.6 [-11.5, +0.8] | **-0.063 [-0.111, -0.017]** | -0.26 (-48) | -0.134 / -0.054 / -0.023 |
| later touch since the break | 630 (123) | 38.5% vs 34.4% | +4.1 [-4.7, +14.5] | -0.008 [-0.071, +0.047] | +0.17 (+20) | +0.061 / -0.001 / -0.088 | 617 (109) | 34.1% vs 38.7% | -4.6 [-13.5, +3.7] | **-0.131 [-0.189, -0.075]** | -0.70 (-77) | -0.110 / -0.137 / -0.143 |
| with the H4 trend | 976 (190) | 38.3% vs 36.5% | +1.9 [-5.3, +8.4] | -0.016 [-0.065, +0.037] | -0.02 (-3) | -0.033 / +0.017 / -0.044 | 1005 (178) | 36.6% vs 44.5% | -8.0 [-12.5, +0.9] | **-0.091 [-0.139, -0.040]** | -0.53 (-94) | -0.076 / -0.110 / -0.085 |
| against the H4 trend | 668 (130) | 41.9% vs 37.3% | +4.6 [-3.4, +11.4] | +0.043 [-0.019, +0.102] | +0.30 (+39) | +0.015 / +0.094 / +0.021 | 676 (120) | 36.8% vs 44.0% | **-7.2 [-14.4, -0.2]** | **-0.084 [-0.142, -0.029]** | -0.26 (-31) | -0.209 / -0.049 / -0.038 |

A level that has just held for an M15 close is a coin: the rejection trade reached its target first in
49.5 / 50.6 % of gold trades and 47.9 / 48.8 % of BTC trades (DEV / CONFIRM; a coin gives 50 %), and made
-0.026 / -0.019 and -0.074 / -0.094 ATR after the spread. No row of it has an interval above zero in either period. The retest of a broken level,
the "old resistance becomes support" trade, made -0.022 / -0.023 in gold and +0.008 / -0.088 in BTC: BTC's small plus
on DEV became a clear minus on CONFIRM, 7 points below the control.

### 4.5 The other side: through the level, and the breakout

**Gold, through trade by kind of level**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all levels | 3634 (709) | 63.5% vs 60.8% | +2.7 [-1.2, +6.5] | -0.003 [-0.035, +0.028] | +0.08 (+53) | -0.016 / +0.002 / +0.003 | 3396 (602) | 64.0% vs 60.8% | **+3.2 [+0.5, +6.2]** | -0.010 [-0.037, +0.017] | +0.08 (+51) | -0.031 / -0.025 / +0.021 |
| H1 swing (not H4) | 1673 (326) | 62.6% vs 59.1% | +3.5 [-1.9, +8.0] | -0.020 [-0.064, +0.023] | -0.12 (-39) | -0.037 / -0.013 / -0.012 | 1702 (302) | 64.1% vs 61.3% | +2.7 [-1.3, +6.8] | -0.012 [-0.046, +0.021] | +0.08 (+25) | -0.035 / -0.019 / +0.017 |
| H4 swing (not D1) | 670 (131) | 67.1% vs 63.1% | +4.0 [-3.5, +12.5] | +0.055 [-0.008, +0.115] | +1.34 (+175) | +0.123 / +0.087 / -0.049 | 877 (155) | 64.3% vs 59.3% | +4.9 [-1.6, +10.2] | -0.006 [-0.053, +0.046] | +0.12 (+18) | -0.007 / -0.043 / +0.037 |
| D1 swing | 122 (24) | 75.0% vs 57.0% | **+18.0 [+0.0, +36.9]** | **+0.181 [+0.036, +0.324]** | +6.09 (+145) | -0.143 / +0.254 / +0.250 | 128 (23) | 68.5% vs 71.5% | -3.0 [-18.3, +11.7] | +0.063 [-0.083, +0.219] | +0.44 (+10) | +0.280 / -0.031 / +0.033 |
| previous-day high / low | 538 (105) | 66.5% vs 60.5% | +6.0 [-0.5, +12.0] | +0.042 [-0.018, +0.105] | +0.81 (+85) | +0.093 / +0.110 / -0.085 | 609 (108) | 65.8% vs 57.7% | **+8.1 [+1.0, +13.4]** | +0.019 [-0.048, +0.088] | +0.34 (+37) | +0.036 / -0.067 / +0.106 |
| previous-day close | 381 (74) | 57.4% vs 58.8% | -1.4 [-9.1, +7.2] | **-0.097 [-0.179, -0.010]** | -2.32 (-172) | -0.122 / -0.210 / +0.105 | 366 (65) | 63.5% vs 59.5% | +4.0 [-4.4, +10.1] | -0.018 [-0.083, +0.039] | -0.06 (-4) | -0.007 / -0.058 / +0.016 |
| previous-week high / low | 145 (28) | 67.6% vs 57.9% | +9.7 [-2.8, +23.5] | +0.060 [-0.077, +0.205] | +1.37 (+39) | -0.152 / +0.185 / +0.168 | 152 (27) | 74.8% vs 62.3% | **+12.5 [+1.8, +26.3]** | **+0.161 [+0.063, +0.269]** | +1.38 (+37) | +0.329 / +0.058 / +0.148 |
| previous-week close | 125 (24) | 60.8% vs 61.5% | -0.7 [-13.9, +15.8] | -0.043 [-0.150, +0.061] | -2.07 (-50) | -0.055 / -0.060 / +0.002 | 131 (23) | 58.0% vs 51.6% | +6.5 [-8.4, +19.7] | -0.104 [-0.267, +0.076] | -0.14 (-3) | +0.037 / -0.181 / -0.115 |
| round number, minor | 713 (139) | 66.7% vs 62.0% | +4.6 [-1.3, +11.1] | +0.048 [-0.004, +0.101] | +1.66 (+231) | -0.019 / +0.037 / +0.136 | 307 (54) | 61.2% vs 62.2% | -1.0 [-8.4, +5.0] | -0.049 [-0.128, +0.025] | -0.28 (-15) | -0.203 / +0.009 / -0.012 |
| round number, major | 733 (143) | 62.7% vs 63.3% | -0.6 [-7.8, +6.4] | -0.017 [-0.069, +0.036] | -0.89 (-127) | +0.028 / -0.011 / -0.069 | 289 (51) | 66.1% vs 63.1% | +3.0 [-2.8, +7.7] | +0.028 [-0.038, +0.100] | +0.39 (+20) | -0.063 / +0.071 / +0.039 |
| any H4 / D1 swing or day / week high / low | 1083 (211) | 66.5% vs 62.5% | +4.0 [-2.1, +10.1] | +0.043 [-0.013, +0.100] | +1.27 (+269) | +0.052 / +0.107 / -0.047 | 1242 (220) | 65.4% vs 58.7% | **+6.7 [+1.0, +11.1]** | +0.012 [-0.037, +0.060] | +0.25 (+54) | +0.040 / -0.051 / +0.056 |

**BTC, through trade by kind of level**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all levels | 6258 (1221) | 62.6% vs 59.6% | +3.0 [-0.5, +6.2] | **-0.032 [-0.056, -0.011]** | -0.23 (-282) | -0.040 / -0.045 / -0.004 | 7065 (1253) | 63.7% vs 58.7% | **+5.0 [+2.4, +8.3]** | **-0.053 [-0.070, -0.036]** | -0.29 (-366) | -0.114 / -0.028 / -0.034 |
| H1 swing (not H4) | 2799 (546) | 62.6% vs 58.3% | **+4.3 [+0.3, +8.7]** | **-0.034 [-0.065, -0.002]** | -0.20 (-108) | +0.010 / -0.040 / -0.067 | 2997 (531) | 63.3% vs 56.8% | **+6.6 [+2.9, +10.8]** | **-0.064 [-0.089, -0.039]** | -0.29 (-156) | -0.135 / -0.054 / -0.018 |
| H4 swing (not D1) | 1176 (229) | 62.9% vs 55.9% | **+7.0 [+0.3, +14.0]** | -0.028 [-0.074, +0.024] | -0.23 (-52) | -0.094 / -0.029 / +0.068 | 1252 (222) | 64.3% vs 56.2% | **+8.1 [+1.2, +15.2]** | **-0.050 [-0.092, -0.007]** | -0.23 (-52) | -0.095 / -0.025 / -0.040 |
| D1 swing | 263 (51) | 62.1% vs 61.0% | +1.1 [-11.3, +16.4] | -0.039 [-0.159, +0.069] | -0.29 (-15) | -0.159 / -0.001 / +0.044 | 245 (43) | 68.2% vs 61.6% | +6.5 [-4.1, +16.2] | +0.032 [-0.036, +0.100] | +0.26 (+11) | +0.132 / +0.069 / -0.036 |
| previous-day high / low | 868 (169) | 67.4% vs 58.4% | **+9.0 [+2.7, +15.7]** | +0.041 [-0.017, +0.105] | +0.16 (+27) | -0.006 / +0.032 / +0.105 | 932 (165) | 66.0% vs 55.8% | **+10.2 [+3.9, +15.7]** | -0.023 [-0.070, +0.028] | +0.00 (+1) | -0.070 / -0.018 / +0.008 |
| previous-day close | 481 (94) | 66.1% vs 52.7% | **+13.4 [+5.2, +22.2]** | +0.024 [-0.046, +0.094] | +0.03 (+3) | -0.009 / +0.051 / +0.029 | 518 (92) | 66.0% vs 59.3% | +6.7 [-0.4, +13.6] | -0.022 [-0.077, +0.035] | -0.18 (-16) | -0.067 / +0.036 / -0.049 |
| previous-week high / low | 171 (33) | 60.2% vs 60.1% | +0.2 [-14.7, +14.0] | -0.066 [-0.204, +0.080] | -0.28 (-9) | -0.166 / -0.059 / +0.058 | 192 (34) | 66.1% vs 62.8% | +3.3 [-9.3, +15.6] | -0.011 [-0.118, +0.094] | +0.04 (+1) | +0.088 / -0.036 / -0.048 |
| previous-week close | 144 (28) | 59.0% vs 57.8% | +1.2 [-12.1, +14.9] | -0.087 [-0.198, +0.044] | -0.68 (-19) | -0.165 / -0.116 / +0.066 | 145 (26) | 69.0% vs 52.6% | **+16.4 [+2.4, +30.0]** | +0.033 [-0.075, +0.153] | -0.13 (-3) | +0.094 / +0.026 / +0.002 |
| round number, minor | 2202 (430) | 62.0% vs 62.4% | -0.3 [-5.0, +4.8] | **-0.038 [-0.073, -0.002]** | -0.24 (-104) | -0.033 / -0.046 / -0.036 | 2784 (494) | 64.9% vs 60.5% | **+4.4 [+0.8, +8.2]** | **-0.025 [-0.050, -0.002]** | -0.17 (-85) | -0.091 / +0.006 / -0.013 |
| round number, major | 513 (100) | 65.9% vs 67.0% | -1.1 [-7.7, +8.2] | +0.021 [-0.054, +0.087] | -0.13 (-13) | +0.021 / +0.007 / +0.047 | 640 (113) | 63.4% vs 59.6% | +3.9 [-3.3, +10.8] | -0.046 [-0.101, +0.005] | -0.31 (-35) | -0.036 / -0.087 / -0.015 |
| any H4 / D1 swing or day / week high / low | 1866 (364) | 63.4% vs 58.5% | +4.8 [-1.0, +11.8] | -0.021 [-0.071, +0.024] | -0.19 (-68) | -0.091 / -0.027 / +0.072 | 1960 (348) | 65.1% vs 55.7% | **+9.5 [+4.0, +14.4]** | -0.034 [-0.066, +0.003] | -0.10 (-35) | -0.075 / -0.015 / -0.023 |

**Gold, breakout trade**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all breaks | 2948 (575) | 49.6% vs 47.7% | +2.0 [-1.6, +6.1] | -0.019 [-0.062, +0.021] | -0.63 (-364) | +0.002 / -0.022 / -0.037 | 2672 (474) | 51.9% vs 49.2% | +2.6 [-1.1, +6.1] | +0.009 [-0.030, +0.047] | +0.15 (+70) | +0.018 / -0.014 / +0.022 |
| H1 swing (not H4) | 1148 (224) | 49.2% vs 47.4% | +1.8 [-3.9, +7.0] | -0.031 [-0.097, +0.042] | -0.88 (-197) | +0.017 / -0.051 / -0.058 | 1288 (228) | 50.4% vs 49.5% | +0.9 [-3.8, +5.5] | -0.020 [-0.060, +0.024] | -0.23 (-52) | -0.007 / -0.019 / -0.035 |
| H4 swing (not D1) | 408 (80) | 49.2% vs 50.0% | -0.8 [-10.4, +9.6] | -0.022 [-0.121, +0.073] | -0.24 (-19) | -0.124 / -0.026 / +0.092 | 507 (90) | 53.6% vs 48.3% | +5.3 [-2.4, +11.3] | +0.043 [-0.034, +0.122] | +0.43 (+39) | +0.058 / -0.015 / +0.090 |
| D1 swing | 78 (15) | 51.3% vs 47.5% | +3.9 [-24.0, +25.3] | +0.012 [-0.213, +0.246] | -1.26 (-19) | +0.317 / -0.178 / +0.117 | 78 (14) | 49.3% vs 49.3% | -0.0 [-17.0, +15.1] | -0.036 [-0.259, +0.176] | -0.26 (-4) | +0.041 / -0.362 / +0.212 |
| previous-day high / low | 381 (74) | 51.1% vs 44.5% | +6.5 [-0.7, +13.3] | +0.010 [-0.081, +0.111] | +0.71 (+53) | -0.054 / +0.043 / +0.046 | 409 (73) | 53.8% vs 49.8% | +4.1 [-6.5, +10.9] | +0.050 [-0.026, +0.133] | +0.33 (+24) | +0.046 / +0.044 / +0.061 |
| previous-day close | 355 (69) | 55.1% vs 47.4% | +7.7 [-1.0, +16.0] | **+0.088 [+0.012, +0.168]** | +1.67 (+116) | +0.090 / +0.115 / +0.053 | 429 (76) | 52.9% vs 52.0% | +1.0 [-9.7, +11.8] | +0.026 [-0.080, +0.130] | +0.38 (+29) | +0.035 / +0.035 / +0.008 |
| previous-week high / low | 80 (16) | 56.2% vs 48.6% | +7.6 [-10.8, +27.4] | +0.111 [-0.103, +0.318] | +1.83 (+29) | +0.170 / +0.053 / +0.115 | 109 (19) | 50.9% vs 42.7% | +8.3 [-7.9, +23.6] | -0.011 [-0.179, +0.166] | +0.00 (+0) | +0.010 / -0.095 / +0.029 |
| previous-week close | 80 (16) | 52.5% vs 43.2% | +9.3 [-13.6, +25.5] | +0.036 [-0.193, +0.262] | +0.83 (+13) | -0.169 / +0.321 / -0.053 | 103 (18) | 52.4% vs 37.4% | +15.0 [-6.6, +26.6] | +0.018 [-0.166, +0.189] | +0.54 (+10) | -0.195 / +0.128 / +0.106 |
| round number, minor | 670 (131) | 47.9% vs 47.5% | +0.4 [-5.0, +5.6] | -0.052 [-0.121, +0.023] | -1.10 (-144) | -0.146 / +0.017 / -0.087 | 243 (43) | 57.5% vs 47.0% | **+10.5 [+2.8, +17.8]** | **+0.121 [+0.005, +0.242]** | +1.26 (+54) | +0.267 / -0.004 / +0.170 |
| round number, major | 641 (125) | 49.3% vs 50.1% | -0.8 [-7.0, +5.7] | -0.023 [-0.096, +0.054] | -0.69 (-86) | +0.071 / -0.038 / -0.060 | 267 (47) | 50.6% vs 49.9% | +0.7 [-8.4, +9.3] | -0.008 [-0.130, +0.116] | +0.29 (+14) | -0.081 / -0.063 / +0.053 |
| any H4 / D1 swing or day / week high / low | 705 (138) | 50.2% vs 47.8% | +2.4 [-4.4, +9.2] | -0.006 [-0.078, +0.070] | -0.04 (-6) | -0.046 / -0.012 / +0.046 | 783 (139) | 52.6% vs 47.6% | +5.1 [-1.3, +9.7] | +0.024 [-0.037, +0.088] | +0.23 (+32) | +0.060 / -0.044 / +0.056 |
| first break of the level | 982 (192) | 52.2% vs 42.6% | **+9.5 [+3.1, +16.7]** | +0.031 [-0.034, +0.095] | +0.68 (+131) | +0.062 / +0.079 / -0.059 | 1189 (211) | 50.3% vs 49.7% | +0.6 [-5.2, +6.4] | -0.025 [-0.087, +0.034] | -0.33 (-69) | +0.024 / -0.049 / -0.050 |
| second break (it had changed role) | 859 (168) | 49.0% vs 49.5% | -0.4 [-7.0, +5.6] | -0.033 [-0.103, +0.040] | -1.05 (-176) | -0.026 / -0.086 / +0.022 | 1055 (187) | 52.8% vs 51.1% | +1.7 [-2.6, +6.6] | +0.028 [-0.022, +0.077] | +0.42 (+79) | +0.003 / +0.025 / +0.056 |
| break with the H4 trend | 1488 (290) | 52.1% vs 50.3% | +1.8 [-3.5, +7.5] | +0.030 [-0.042, +0.100] | -0.48 (-139) | +0.082 / +0.011 / +0.003 | 1328 (235) | 53.8% vs 49.3% | +4.5 [-0.3, +9.7] | +0.046 [-0.014, +0.107] | +0.34 (+81) | +0.061 / +0.001 / +0.077 |
| break against the H4 trend | 1460 (285) | 47.1% vs 45.5% | +1.6 [-4.9, +7.4] | **-0.070 [-0.131, -0.013]** | -0.79 (-225) | -0.084 / -0.055 / -0.076 | 1344 (238) | 50.0% vs 50.2% | -0.2 [-5.7, +4.5] | -0.028 [-0.088, +0.034] | -0.05 (-12) | -0.023 / -0.030 / -0.031 |
| break with the D1 trend | 1472 (287) | 51.8% vs 49.4% | +2.4 [-3.4, +7.7] | +0.024 [-0.049, +0.093] | -0.46 (-131) | +0.077 / -0.007 / +0.017 | 1296 (230) | 53.1% vs 46.8% | **+6.3 [+1.5, +10.7]** | +0.033 [-0.026, +0.097] | +0.27 (+63) | -0.006 / +0.022 / +0.074 |
| break against the D1 trend | 1476 (288) | 47.5% vs 45.5% | +2.0 [-3.9, +7.9] | -0.062 [-0.130, +0.003] | -0.81 (-233) | -0.072 / -0.036 / -0.090 | 1376 (244) | 50.7% vs 52.1% | -1.4 [-6.6, +3.3] | -0.014 [-0.073, +0.042] | +0.03 (+7) | +0.038 / -0.049 / -0.028 |
| level had been touched before | 2772 (541) | 48.9% vs 47.5% | +1.4 [-2.2, +5.4] | -0.033 [-0.078, +0.009] | -0.83 (-449) | -0.023 / -0.032 / -0.043 | 2423 (430) | 51.3% vs 49.4% | +1.9 [-1.5, +5.2] | -0.002 [-0.043, +0.038] | +0.09 (+39) | -0.005 / -0.031 / +0.029 |
| level never touched | 176 (34) | 60.2% vs 53.5% | +6.8 [-9.5, +26.0] | **+0.190 [+0.057, +0.315]** | +2.47 (+85) | +0.341 / +0.137 / +0.074 | 249 (44) | 57.1% vs 56.3% | +0.7 [-13.2, +23.1] | +0.109 [-0.004, +0.231] | +0.69 (+30) | +0.197 / +0.158 / -0.048 |

**BTC, breakout trade**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all breaks | 4915 (959) | 50.5% vs 50.6% | -0.2 [-3.8, +2.6] | -0.023 [-0.058, +0.008] | -0.16 (-156) | -0.024 / -0.044 / +0.008 | 5677 (1007) | 50.3% vs 51.8% | -1.4 [-4.9, +1.6] | **-0.063 [-0.090, -0.035]** | -0.35 (-355) | -0.142 / -0.033 / -0.033 |
| H1 swing (not H4) | 1865 (364) | 51.0% vs 51.2% | -0.2 [-5.6, +4.3] | -0.015 [-0.066, +0.031] | -0.13 (-46) | -0.046 / -0.022 / +0.027 | 1998 (354) | 49.6% vs 51.0% | -1.4 [-6.3, +3.5] | **-0.085 [-0.119, -0.051]** | -0.49 (-172) | -0.134 / -0.073 / -0.058 |
| H4 swing (not D1) | 619 (121) | 47.9% vs 45.9% | +2.0 [-9.2, +10.9] | -0.075 [-0.151, +0.001] | -0.31 (-37) | -0.003 / -0.104 / -0.122 | 650 (115) | 52.2% vs 53.9% | -1.8 [-10.7, +5.8] | -0.031 [-0.104, +0.042] | -0.12 (-14) | -0.081 / -0.053 / +0.040 |
| D1 swing | 132 (26) | 54.5% vs 45.1% | +9.4 [-14.1, +25.8] | +0.063 [-0.099, +0.211] | +0.32 (+8) | +0.005 / +0.107 / +0.029 | 130 (23) | 53.1% vs 59.8% | -6.7 [-20.1, +8.0] | +0.003 [-0.166, +0.140] | -0.06 (-1) | -0.174 / +0.200 / -0.061 |
| previous-day high / low | 503 (98) | 51.9% vs 50.4% | +1.5 [-7.2, +11.4] | +0.003 [-0.089, +0.099] | +0.11 (+11) | +0.011 / -0.002 / +0.002 | 509 (90) | 50.4% vs 46.5% | +3.8 [-5.0, +13.9] | -0.071 [-0.155, +0.015] | -0.24 (-22) | -0.177 / +0.003 / -0.057 |
| previous-day close | 575 (112) | 53.0% vs 49.8% | +3.2 [-5.5, +12.0] | +0.025 [-0.049, +0.096] | +0.11 (+13) | +0.061 / -0.048 / +0.089 | 610 (108) | 51.8% vs 52.5% | -0.7 [-11.2, +10.3] | -0.039 [-0.106, +0.032] | -0.20 (-22) | -0.125 / +0.027 / -0.033 |
| previous-week high / low | 84 (16) | 56.0% vs 53.3% | +2.7 [-20.2, +36.5] | +0.090 [-0.124, +0.311] | +0.32 (+5) | +0.121 / +0.256 / -0.130 | 104 (18) | 51.9% vs 51.8% | +0.1 [-17.7, +18.9] | -0.033 [-0.199, +0.143] | +0.10 (+2) | -0.117 / +0.204 / -0.188 |
| previous-week close | 104 (20) | 50.0% vs 27.4% | **+22.6 [+9.6, +36.3]** | -0.034 [-0.188, +0.134] | -0.18 (-4) | -0.008 / -0.005 / -0.091 | 107 (19) | 55.1% vs 32.1% | **+23.1 [+1.0, +37.1]** | +0.020 [-0.183, +0.210] | +0.23 (+4) | +0.033 / +0.164 / -0.132 |
| round number, minor | 1913 (373) | 49.8% vs 50.0% | -0.2 [-6.1, +2.1] | -0.034 [-0.077, +0.009] | -0.25 (-93) | -0.026 / -0.058 / -0.006 | 2530 (449) | 49.1% vs 52.6% | -3.4 [-7.8, +0.4] | **-0.078 [-0.112, -0.041]** | -0.51 (-227) | -0.170 / -0.044 / -0.051 |
| round number, major | 449 (88) | 49.7% vs 49.4% | +0.3 [-7.3, +6.1] | -0.038 [-0.116, +0.061] | -0.32 (-28) | -0.050 / -0.042 / -0.010 | 555 (98) | 52.3% vs 54.0% | -1.7 [-10.5, +5.5] | -0.015 [-0.117, +0.090] | +0.05 (+5) | -0.141 / +0.046 / +0.002 |
| any H4 / D1 swing or day / week high / low | 1023 (200) | 50.8% vs 48.7% | +2.1 [-5.1, +8.9] | -0.017 [-0.084, +0.055] | -0.04 (-7) | +0.018 / -0.029 / -0.035 | 1058 (188) | 52.0% vs 52.3% | -0.3 [-6.7, +6.3] | -0.033 [-0.092, +0.025] | -0.13 (-25) | -0.112 / -0.002 / +0.002 |
| first break of the level | 1513 (295) | 51.9% vs 51.4% | +0.6 [-5.4, +7.0] | +0.002 [-0.056, +0.060] | +0.01 (+3) | -0.042 / +0.005 / +0.042 | 1578 (280) | 50.4% vs 52.6% | -2.2 [-8.8, +2.7] | **-0.072 [-0.125, -0.020]** | -0.39 (-110) | -0.155 / -0.055 / -0.015 |
| second break (it had changed role) | 1391 (271) | 50.5% vs 49.7% | +0.9 [-4.8, +6.8] | -0.022 [-0.079, +0.031] | -0.13 (-34) | +0.008 / -0.050 / -0.016 | 1464 (260) | 52.2% vs 50.6% | +1.7 [-4.1, +8.1] | -0.029 [-0.082, +0.025] | -0.12 (-32) | -0.081 / +0.006 / -0.024 |
| break with the H4 trend | 2451 (478) | 51.3% vs 50.6% | +0.7 [-5.5, +4.8] | -0.007 [-0.060, +0.042] | -0.06 (-28) | +0.007 / -0.002 / -0.033 | 2825 (501) | 50.8% vs 53.7% | -3.0 [-8.1, +1.1] | **-0.055 [-0.093, -0.015]** | -0.42 (-213) | -0.099 / -0.040 / -0.034 |
| break against the H4 trend | 2464 (481) | 49.7% vs 52.0% | -2.4 [-7.6, +1.5] | -0.039 [-0.102, +0.018] | -0.27 (-128) | -0.056 / -0.088 / +0.046 | 2852 (506) | 49.9% vs 50.2% | -0.3 [-5.9, +4.8] | **-0.070 [-0.112, -0.029]** | -0.28 (-142) | -0.190 / -0.025 / -0.033 |
| break with the D1 trend | 2447 (477) | 51.2% vs 52.2% | -1.0 [-6.8, +2.9] | -0.009 [-0.062, +0.041] | -0.03 (-16) | -0.002 / +0.023 / -0.069 | 2815 (499) | 51.1% vs 52.7% | -1.6 [-6.3, +1.9] | **-0.049 [-0.086, -0.009]** | -0.36 (-182) | -0.123 / -0.001 / -0.042 |
| break against the D1 trend | 2468 (482) | 49.8% vs 50.1% | -0.3 [-4.7, +3.8] | -0.037 [-0.092, +0.011] | -0.29 (-140) | -0.047 / -0.117 / +0.077 | 2862 (507) | 49.6% vs 50.5% | -0.9 [-6.4, +3.4] | **-0.076 [-0.123, -0.036]** | -0.34 (-173) | -0.161 / -0.065 / -0.025 |
| level had been touched before | 4590 (896) | 50.6% vs 50.5% | +0.0 [-3.7, +2.7] | -0.021 [-0.057, +0.011] | -0.15 (-139) | -0.021 / -0.047 / +0.015 | 5334 (946) | 50.2% vs 51.8% | -1.7 [-5.4, +1.5] | **-0.066 [-0.095, -0.037]** | -0.37 (-350) | -0.149 / -0.042 / -0.030 |
| level never touched | 325 (63) | 49.2% vs 49.0% | +0.2 [-18.1, +18.1] | -0.052 [-0.129, +0.032] | -0.27 (-17) | -0.071 / -0.012 / -0.082 | 343 (61) | 53.3% vs 48.7% | +4.6 [-12.5, +21.5] | -0.010 [-0.100, +0.088] | -0.08 (-5) | -0.060 / +0.108 / -0.092 |

A level is run through a little more often than a control price. The through trade reached its target first
in 63.5 / 64.0 % of gold trades against 60.8 / 60.8 % at control prices, and in 62.6 / 63.7 % against
59.6 / 58.7 % in BTC (DEV / CONFIRM): +2.7 / +3.2 and +3.0 / +5.0 points, beyond chance on CONFIRM. This is the
mirror image of 4.2 and the one regularity that repeats in all four columns. It is an effect, not a trade:
before the spread it is worth 0.00 to 0.02 ATR per trade, and the spread (1.4 to 7 % of an ATR) takes more than
that: -0.003 / -0.010 ATR per trade in gold, -0.032 / -0.053 in BTC. Gold's through rows at the higher-timeframe levels
are slightly positive in both periods (+0.043 / +0.012), with intervals through zero; BTC's are not (-0.021 / -0.034).

Once an M15 bar has closed beyond the level, the move is over as far as these data can tell: the breakout
trade continued to its target in 49.6 / 51.9 % of gold trades and 50.5 / 50.3 % of BTC trades, and made -0.019 / +0.009 and
-0.023 / -0.063 ATR. Breaks with the H4 or D1 trend do better than breaks against it in gold in both periods
(+0.030 / +0.046 against -0.070 / -0.028), which agrees with what the improvement search found about the trend (`IMPROVEMENT.md`); the
intervals of the with-trend rows include zero.

### 4.6 The rows that looked like something

Across the tables of 4.2 to 4.5 and the appendix there are 334 rows on the two symbols. By the rule set
beforehand (at least 100 trades, positive in every half-year with the profit interval above zero, and ahead of
the control with that interval above zero) **no row is a candidate on DEV**. Three rows, all in gold, met the
profit half of it, and went to CONFIRM as leads, with the same rows of BTC for comparison:

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| through trade at a zone of three or more levels | gold | 419 (82) | 69.8% vs 57.8% | +12.0 [-0.7, +23.1] | **+0.096 [+0.018, +0.180]** | +2.18 (+178) | +0.087 / +0.147 / +0.007 | 315 (56) | 62.7% vs 62.1% | +0.7 [-7.4, +10.0] | -0.023 [-0.106, +0.072] | -0.04 (-2) | +0.138 / -0.080 / -0.052 |
| breakout of a previous-day close | gold | 355 (69) | 55.1% vs 47.4% | +7.7 [-1.0, +16.0] | **+0.088 [+0.012, +0.168]** | +1.67 (+116) | +0.090 / +0.115 / +0.053 | 429 (76) | 52.9% vs 52.0% | +1.0 [-9.7, +11.8] | +0.026 [-0.080, +0.130] | +0.38 (+29) | +0.035 / +0.035 / +0.008 |
| breakout of a level never touched before | gold | 176 (34) | 60.2% vs 53.5% | +6.8 [-9.5, +26.0] | **+0.190 [+0.057, +0.315]** | +2.47 (+85) | +0.341 / +0.137 / +0.074 | 249 (44) | 57.1% vs 56.3% | +0.7 [-13.2, +23.1] | +0.109 [-0.004, +0.231] | +0.69 (+30) | +0.197 / +0.158 / -0.048 |
| through trade at a zone of three or more levels | BTC | 757 (148) | 63.7% vs 59.1% | +4.6 [-4.3, +15.4] | -0.013 [-0.082, +0.057] | -0.25 (-37) | -0.046 / +0.026 / -0.017 | 775 (137) | 69.9% vs 60.8% | **+9.2 [+2.3, +17.3]** | +0.046 [-0.009, +0.102] | +0.36 (+50) | -0.052 / +0.072 / +0.087 |
| breakout of a previous-day close | BTC | 575 (112) | 53.0% vs 49.8% | +3.2 [-5.5, +12.0] | +0.025 [-0.049, +0.096] | +0.11 (+13) | +0.061 / -0.048 / +0.089 | 610 (108) | 51.8% vs 52.5% | -0.7 [-11.2, +10.3] | -0.039 [-0.106, +0.032] | -0.20 (-22) | -0.125 / +0.027 / -0.033 |
| breakout of a level never touched before | BTC | 325 (63) | 49.2% vs 49.0% | +0.2 [-18.1, +18.1] | -0.052 [-0.129, +0.032] | -0.27 (-17) | -0.071 / -0.012 / -0.082 | 343 (61) | 53.3% vs 48.7% | +4.6 [-12.5, +21.5] | -0.010 [-0.100, +0.088] | -0.08 (-5) | -0.060 / +0.108 / -0.092 |

- **Through trade at zones of three or more levels**: gone (-0.023 ATR on CONFIRM).
- **Breakout of a previous-day close**: a third of its DEV size on CONFIRM, interval from -0.08 to +0.13, level
  with the control (52.9 % against 52.0 %). Not confirmed.
- **Breakout of a level never touched before**: the same sign and half the size (+0.109 ATR, interval from
  -0.004 to +0.231, negative in the last half-year), about 44 trades and 30 USD a quarter on a 0.01 lot.
  It is the nearest thing to a repeat in the study and it is not about the level: breaks of the control map's
  never-touched lines continued just as often (56.3 % against 57.1 %). What it shows is gold moving on when it
  enters prices it has not visited lately, which is gold's trend of these three years; BTC shows nothing of
  it. It does not meet the rule and is not proposed as one.

The whole count, by symbol (a row is "in every period" under a heading if it is there in both):

**Gold**

|  | rows | profit interval above zero | below zero | profit rule met | profit and control rule met |
|---|---|---|---|---|---|
| DEV | 167 | 7 | 28 | 3 | 0 |
| CONFIRM | 167 | 5 | 50 | 2 | 1 |
| in every period | 167 | 0 | 20 | 0 | 0 |

**BTC**

|  | rows | profit interval above zero | below zero | profit rule met | profit and control rule met |
|---|---|---|---|---|---|
| DEV | 167 | 0 | 80 | 0 | 0 |
| CONFIRM | 167 | 0 | 134 | 0 | 0 |
| in every period | 167 | 0 | 76 | 0 | 0 |

Chance alone puts about 8 of 334 intervals above zero. There are 7 on DEV and 5 on CONFIRM, all in gold, all on
the through or breakout side, and no row is among them twice. Below zero there are 108 and 184, and
96 rows are below zero in both periods.

Two rows meet the profit rule on CONFIRM without having met it on DEV: gold's through trade at unbroken
extremes without RSI divergence (+0.059 ATR after +0.004 on DEV), and gold's through trade at the previous week's
high or low, which on CONFIRM also runs ahead of the control:

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| through trade at the previous week's high or low | gold | 145 (28) | 67.6% vs 57.9% | +9.7 [-2.8, +23.5] | +0.060 [-0.077, +0.205] | +1.37 (+39) | -0.152 / +0.185 / +0.168 | 152 (27) | 74.8% vs 62.3% | **+12.5 [+1.8, +26.3]** | **+0.161 [+0.063, +0.269]** | +1.38 (+37) | +0.329 / +0.058 / +0.148 |
| through trade at the previous week's high or low | BTC | 171 (33) | 60.2% vs 60.1% | +0.2 [-14.7, +14.0] | -0.066 [-0.204, +0.080] | -0.28 (-9) | -0.166 / -0.059 / +0.058 | 192 (34) | 66.1% vs 62.8% | +3.3 [-9.3, +15.6] | -0.011 [-0.118, +0.094] | +0.04 (+1) | +0.088 / -0.036 / -0.048 |

**What is left is a hypothesis, not a rule.** Two gold rows are positive in five of the six half-years: the
breakout of a level never touched before (about 40 trades a quarter, +2.47 / +0.69 USD a trade on a 0.01 lot) and the
through trade at the previous week's high or low (about 27 trades a quarter, +1.37 / +1.38 USD a trade). Both say
what the 3 to 5 points of 4.5 say: gold tended to carry on through marked prices where a trader expects it to
turn, as a market in a three-year rise would. Neither passed the test set for it. The first was chosen on DEV
and fell short on CONFIRM, and the control map does as well as the levels there. The second was noticed on
CONFIRM, which is not a test. BTC shows neither. They can be tested fairly only on a period that has not been
looked at, and for that they are, exactly:

1. *Gold, breakout of an untouched level.* An M15 bar closes at least 0.25 ATR beyond a level (any kind of
   3.1) that has had no touch since it was made, with no unbroken level of the same side within 0.25 ATR
   further on. Enter at that close with the break; target 1 ATR, stop 1 ATR, 24-hour limit.
2. *Gold, through last week's high or low.* Price, having closed at least 1 ATR away since the last touch,
   comes within 0.10 ATR of a zone that holds the previous week's high or low. Enter with the approach (buy
   coming up to it, sell coming down to it); target 0.5 ATR beyond the level touched, stop 1 ATR back from the
   touch price, 24-hour limit.

### 4.7 Does the answer depend on the definitions?

Other targets and stops for the bounce trade (all levels). "Random walk" is the share of trades a driftless
price would take to the target.

**Gold**

|  | random walk | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| target 0.5 / stop 0.25 | 41.2% | 3634 (709) | 38.8% vs 42.3% | -3.5 [-7.7, +0.1] | **-0.027 [-0.043, -0.011]** | -0.35 (-249) | -0.029 / -0.021 / -0.033 | 3396 (602) | 37.9% vs 42.5% | **-4.6 [-6.9, -2.8]** | **-0.051 [-0.063, -0.039]** | -0.35 (-208) | -0.064 / -0.055 / -0.036 |
| target 0.5 / stop 0.5 | 54.5% | 3634 (709) | 52.0% vs 55.7% | **-3.7 [-7.4, -0.2]** | **-0.032 [-0.051, -0.014]** | -0.54 (-385) | -0.032 / -0.025 / -0.041 | 3396 (602) | 50.9% vs 56.3% | **-5.5 [-8.0, -3.2]** | **-0.061 [-0.077, -0.045]** | -0.41 (-249) | -0.077 / -0.057 / -0.051 |
| target 0.5 / stop 1.0 | 68.8% | 3634 (709) | 67.1% vs 69.1% | -2.0 [-4.8, +1.5] | -0.026 [-0.059, +0.005] | -0.41 (-290) | -0.027 / -0.020 / -0.034 | 3396 (602) | 66.1% vs 69.4% | **-3.2 [-6.5, -0.5]** | **-0.059 [-0.089, -0.029]** | -0.44 (-268) | -0.064 / -0.055 / -0.058 |
| target 1.0 / stop 0.25 | 25.9% | 3634 (709) | 24.0% vs 25.9% | -1.9 [-5.3, +1.0] | **-0.034 [-0.054, -0.016]** | -0.54 (-386) | -0.028 / -0.027 / -0.050 | 3396 (602) | 23.2% vs 25.7% | **-2.6 [-4.9, -0.6]** | **-0.062 [-0.077, -0.044]** | -0.45 (-269) | -0.076 / -0.061 / -0.050 |
| target 1.0 / stop 0.5 | 37.5% | 3634 (709) | 34.9% vs 37.7% | -2.8 [-6.4, +0.9] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 37.7% | **-4.1 [-6.9, -1.5]** | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| target 1.0 / stop 1.0 | 52.4% | 3634 (709) | 49.1% vs 52.4% | -3.3 [-6.6, +0.5] | **-0.070 [-0.112, -0.027]** | -1.61 (-1142) | -0.043 / -0.084 / -0.076 | 3396 (602) | 48.5% vs 51.7% | **-3.2 [-6.6, -0.4]** | **-0.100 [-0.140, -0.059]** | -0.81 (-487) | -0.121 / -0.085 / -0.096 |
| target 2.0 / stop 0.25 | 14.9% | 3634 (709) | 13.8% vs 15.8% | -2.0 [-5.0, +0.8] | **-0.029 [-0.055, -0.000]** | -0.38 (-268) | -0.016 / -0.016 / -0.058 | 3396 (602) | 13.7% vs 13.8% | -0.2 [-2.5, +1.8] | **-0.051 [-0.077, -0.025]** | -0.36 (-217) | -0.086 / -0.048 / -0.024 |
| target 2.0 / stop 0.5 | 23.1% | 3634 (709) | 21.0% vs 24.3% | -3.3 [-7.3, +0.9] | **-0.053 [-0.090, -0.010]** | -0.93 (-660) | -0.028 / -0.041 / -0.094 | 3396 (602) | 20.5% vs 21.5% | -1.0 [-3.9, +1.6] | **-0.083 [-0.113, -0.053]** | -0.59 (-355) | -0.128 / -0.070 / -0.057 |
| target 2.0 / stop 1.0 | 35.5% | 3634 (709) | 31.8% vs 37.8% | **-5.9 [-10.2, -1.1]** | **-0.098 [-0.154, -0.040]** | -2.02 (-1430) | -0.058 / -0.095 / -0.142 | 3396 (602) | 33.2% vs 33.1% | +0.1 [-3.7, +3.2] | **-0.084 [-0.137, -0.031]** | -0.63 (-382) | -0.123 / -0.082 / -0.052 |

**BTC**

|  | random walk | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| target 0.5 / stop 0.25 | 41.2% | 6258 (1221) | 39.0% vs 41.2% | -2.2 [-5.0, +0.7] | **-0.046 [-0.056, -0.037]** | -0.20 (-242) | -0.051 / -0.040 / -0.049 | 7065 (1253) | 39.4% vs 43.8% | **-4.4 [-7.0, -2.1]** | **-0.085 [-0.096, -0.074]** | -0.44 (-553) | -0.119 / -0.075 / -0.068 |
| target 0.5 / stop 0.5 | 54.5% | 6258 (1221) | 52.9% vs 55.5% | -2.6 [-6.1, +0.7] | **-0.044 [-0.058, -0.030]** | -0.15 (-179) | -0.047 / -0.027 / -0.064 | 7065 (1253) | 52.1% vs 58.2% | **-6.1 [-8.9, -3.9]** | **-0.096 [-0.110, -0.083]** | -0.49 (-618) | -0.135 / -0.084 / -0.078 |
| target 0.5 / stop 1.0 | 68.8% | 6258 (1221) | 67.0% vs 69.2% | -2.2 [-4.9, +0.4] | **-0.052 [-0.071, -0.032]** | -0.18 (-219) | -0.055 / -0.028 / -0.080 | 7065 (1253) | 67.6% vs 71.8% | **-4.2 [-6.8, -1.7]** | **-0.086 [-0.103, -0.069]** | -0.41 (-520) | -0.111 / -0.090 / -0.064 |
| target 1.0 / stop 0.25 | 25.9% | 6258 (1221) | 24.0% vs 25.1% | -1.1 [-3.8, +1.3] | **-0.056 [-0.070, -0.042]** | -0.23 (-282) | -0.061 / -0.046 / -0.063 | 7065 (1253) | 24.1% vs 27.6% | **-3.5 [-6.2, -1.2]** | **-0.095 [-0.109, -0.082]** | -0.48 (-600) | -0.136 / -0.091 / -0.069 |
| target 1.0 / stop 0.5 | 37.5% | 6258 (1221) | 35.5% vs 36.8% | -1.2 [-4.6, +1.8] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 40.1% | **-4.9 [-8.0, -2.5]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| target 1.0 / stop 1.0 | 52.4% | 6258 (1221) | 50.6% vs 51.5% | -0.8 [-3.9, +2.3] | **-0.065 [-0.092, -0.039]** | -0.22 (-270) | -0.067 / -0.045 / -0.090 | 7065 (1253) | 50.7% vs 54.0% | -3.3 [-6.8, +0.3] | **-0.106 [-0.131, -0.082]** | -0.48 (-603) | -0.131 / -0.112 / -0.081 |
| target 2.0 / stop 0.25 | 14.9% | 6258 (1221) | 13.6% vs 14.5% | -0.9 [-3.6, +1.0] | **-0.060 [-0.082, -0.039]** | -0.24 (-294) | -0.059 / -0.054 / -0.068 | 7065 (1253) | 13.6% vs 16.0% | **-2.4 [-4.7, -0.3]** | **-0.099 [-0.116, -0.082]** | -0.49 (-617) | -0.158 / -0.101 / -0.055 |
| target 2.0 / stop 0.5 | 23.1% | 6258 (1221) | 21.0% vs 23.3% | -2.4 [-5.8, +0.4] | **-0.078 [-0.107, -0.052]** | -0.26 (-318) | -0.067 / -0.072 / -0.100 | 7065 (1253) | 21.3% vs 24.4% | **-3.1 [-5.9, -0.9]** | **-0.110 [-0.133, -0.087]** | -0.55 (-688) | -0.162 / -0.122 / -0.061 |
| target 2.0 / stop 1.0 | 35.5% | 6258 (1221) | 33.4% vs 35.7% | -2.2 [-5.7, +1.0] | **-0.078 [-0.118, -0.039]** | -0.27 (-325) | -0.050 / -0.073 / -0.119 | 7065 (1253) | 33.9% vs 35.2% | -1.3 [-4.7, +1.7] | **-0.105 [-0.141, -0.072]** | -0.47 (-583) | -0.130 / -0.120 / -0.074 |

Other definitions of a level: swings with 2 or 5 bars on each side instead of 3, a touch zone of 0.05 or 0.20
ATR instead of 0.10.

**Gold**

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| as defined (swing: 3 bars each side; touch zone 0.10 ATR) | all levels | 3634 (709) | 34.9% vs 37.7% | -2.8 [-6.4, +0.9] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 37.7% | **-4.1 [-6.9, -1.5]** | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| as defined (swing: 3 bars each side; touch zone 0.10 ATR) | H4 / D1 swings and day / week highs and lows | 1083 (211) | 31.7% vs 36.5% | -4.9 [-10.9, +1.4] | **-0.101 [-0.156, -0.049]** | -2.13 (-449) | -0.143 / -0.137 / -0.014 | 1242 (220) | 32.4% vs 39.8% | **-7.3 [-11.4, -1.8]** | **-0.104 [-0.149, -0.061]** | -0.76 (-168) | -0.179 / -0.052 / -0.096 |
| swing: 2 bars each side | all levels | 4240 (827) | 35.4% vs 37.8% | -2.4 [-6.3, +1.3] | **-0.038 [-0.064, -0.011]** | -0.78 (-645) | -0.014 / -0.027 / -0.077 | 4082 (724) | 34.1% vs 37.8% | **-3.7 [-6.9, -0.5]** | **-0.077 [-0.097, -0.057]** | -0.58 (-420) | -0.090 / -0.069 / -0.073 |
| swing: 2 bars each side | H4 / D1 swings and day / week highs and lows | 1409 (275) | 32.2% vs 34.5% | -2.3 [-8.3, +3.3] | **-0.090 [-0.139, -0.046]** | -1.81 (-498) | -0.105 / -0.123 / -0.035 | 1551 (275) | 33.3% vs 37.1% | -3.8 [-8.3, +0.9] | **-0.091 [-0.128, -0.055]** | -0.69 (-189) | -0.154 / -0.055 / -0.073 |
| swing: 5 bars each side | all levels | 3059 (597) | 34.5% vs 36.7% | -2.3 [-6.0, +1.5] | **-0.053 [-0.081, -0.024]** | -1.03 (-616) | -0.040 / -0.042 / -0.081 | 2688 (477) | 33.7% vs 36.9% | **-3.3 [-5.9, -0.7]** | **-0.085 [-0.113, -0.057]** | -0.61 (-289) | -0.139 / -0.069 / -0.059 |
| swing: 5 bars each side | H4 / D1 swings and day / week highs and lows | 915 (179) | 31.1% vs 35.3% | -4.1 [-10.4, +2.1] | **-0.109 [-0.167, -0.055]** | -2.13 (-381) | -0.126 / -0.157 / -0.032 | 1038 (184) | 31.4% vs 37.9% | **-6.5 [-10.6, -0.7]** | **-0.120 [-0.174, -0.068]** | -0.93 (-172) | -0.198 / -0.033 / -0.146 |
| touch zone 0.05 ATR | all levels | 3468 (677) | 33.0% vs 35.9% | -2.8 [-6.1, +0.6] | **-0.043 [-0.071, -0.015]** | -0.79 (-538) | -0.042 / -0.033 / -0.057 | 3238 (574) | 31.5% vs 35.7% | **-4.2 [-7.1, -1.4]** | **-0.084 [-0.107, -0.060]** | -0.60 (-343) | -0.105 / -0.075 / -0.074 |
| touch zone 0.05 ATR | H4 / D1 swings and day / week highs and lows | 1048 (204) | 30.3% vs 36.1% | **-5.8 [-11.3, -0.2]** | **-0.088 [-0.141, -0.038]** | -1.69 (-346) | -0.140 / -0.114 / -0.003 | 1202 (213) | 31.5% vs 37.6% | **-6.1 [-10.6, -0.7]** | **-0.086 [-0.130, -0.044]** | -0.58 (-124) | -0.134 / -0.060 / -0.072 |
| touch zone 0.20 ATR | all levels | 4087 (797) | 39.5% vs 41.5% | -2.0 [-5.5, +1.1] | **-0.033 [-0.060, -0.006]** | -0.73 (-582) | -0.005 / -0.032 / -0.064 | 3781 (670) | 38.0% vs 40.8% | -2.9 [-5.8, +0.1] | **-0.077 [-0.102, -0.053]** | -0.56 (-374) | -0.116 / -0.066 / -0.056 |
| touch zone 0.20 ATR | H4 / D1 swings and day / week highs and lows | 1217 (237) | 37.2% vs 40.4% | -3.2 [-9.2, +3.1] | **-0.075 [-0.139, -0.019]** | -1.79 (-426) | -0.078 / -0.114 / -0.019 | 1394 (247) | 36.4% vs 42.9% | **-6.5 [-11.4, -0.2]** | **-0.103 [-0.151, -0.055]** | -0.71 (-176) | -0.183 / -0.050 / -0.093 |

**BTC**

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| as defined (swing: 3 bars each side; touch zone 0.10 ATR) | all levels | 6258 (1221) | 35.5% vs 36.8% | -1.2 [-4.6, +1.8] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 40.1% | **-4.9 [-8.0, -2.5]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| as defined (swing: 3 bars each side; touch zone 0.10 ATR) | H4 / D1 swings and day / week highs and lows | 1866 (364) | 34.0% vs 35.1% | -1.1 [-7.5, +4.1] | **-0.086 [-0.126, -0.041]** | -0.34 (-124) | -0.036 / -0.079 / -0.155 | 1960 (348) | 33.8% vs 42.9% | **-9.1 [-13.7, -3.6]** | **-0.132 [-0.169, -0.097]** | -0.71 (-246) | -0.208 / -0.120 / -0.089 |
| swing: 2 bars each side | all levels | 7091 (1384) | 35.9% vs 37.7% | -1.9 [-5.4, +1.1] | **-0.055 [-0.074, -0.036]** | -0.18 (-251) | -0.052 / -0.045 / -0.073 | 7870 (1395) | 35.1% vs 41.4% | **-6.3 [-9.6, -3.2]** | **-0.109 [-0.125, -0.095]** | -0.54 (-760) | -0.155 / -0.105 / -0.080 |
| swing: 2 bars each side | H4 / D1 swings and day / week highs and lows | 2314 (451) | 34.1% vs 37.2% | -3.1 [-10.0, +2.5] | **-0.083 [-0.122, -0.043]** | -0.32 (-146) | -0.034 / -0.080 / -0.148 | 2413 (428) | 34.1% vs 43.5% | **-9.4 [-14.7, -4.7]** | **-0.128 [-0.159, -0.098]** | -0.67 (-288) | -0.206 / -0.107 / -0.090 |
| swing: 5 bars each side | all levels | 5265 (1027) | 35.4% vs 37.4% | -2.1 [-5.1, +0.7] | **-0.063 [-0.082, -0.043]** | -0.21 (-218) | -0.046 / -0.046 / -0.108 | 6053 (1073) | 34.7% vs 39.2% | **-4.5 [-7.4, -1.6]** | **-0.114 [-0.130, -0.097]** | -0.59 (-629) | -0.159 / -0.111 / -0.084 |
| swing: 5 bars each side | H4 / D1 swings and day / week highs and lows | 1562 (305) | 33.5% vs 36.8% | -3.2 [-8.3, +1.6] | **-0.094 [-0.139, -0.048]** | -0.38 (-117) | -0.041 / -0.083 / -0.169 | 1658 (294) | 33.8% vs 41.1% | **-7.3 [-12.8, -1.8]** | **-0.133 [-0.172, -0.096]** | -0.73 (-214) | -0.216 / -0.118 / -0.087 |
| touch zone 0.05 ATR | all levels | 5931 (1157) | 32.9% vs 34.7% | -1.7 [-5.5, +1.5] | **-0.069 [-0.088, -0.048]** | -0.25 (-285) | -0.067 / -0.048 / -0.099 | 6686 (1185) | 33.0% vs 38.0% | **-5.0 [-7.9, -2.5]** | **-0.110 [-0.127, -0.094]** | -0.55 (-653) | -0.158 / -0.104 / -0.080 |
| touch zone 0.05 ATR | H4 / D1 swings and day / week highs and lows | 1781 (347) | 31.8% vs 33.6% | -1.8 [-8.2, +4.2] | **-0.088 [-0.129, -0.043]** | -0.34 (-120) | -0.039 / -0.077 / -0.159 | 1843 (327) | 31.2% vs 39.4% | **-8.2 [-12.5, -2.9]** | **-0.141 [-0.180, -0.105]** | -0.76 (-248) | -0.218 / -0.127 / -0.097 |
| touch zone 0.20 ATR | all levels | 6992 (1364) | 39.2% vs 41.0% | -1.8 [-5.4, +1.1] | **-0.062 [-0.083, -0.041]** | -0.20 (-279) | -0.058 / -0.046 / -0.089 | 7949 (1409) | 39.4% vs 42.9% | **-3.5 [-6.5, -1.0]** | **-0.100 [-0.117, -0.083]** | -0.48 (-678) | -0.140 / -0.110 / -0.059 |
| touch zone 0.20 ATR | H4 / D1 swings and day / week highs and lows | 2098 (409) | 38.1% vs 39.7% | -1.6 [-7.8, +2.9] | **-0.081 [-0.123, -0.039]** | -0.31 (-127) | -0.039 / -0.076 / -0.141 | 2209 (392) | 38.5% vs 43.2% | **-4.6 [-9.3, -0.3]** | **-0.117 [-0.152, -0.083]** | -0.57 (-225) | -0.167 / -0.118 / -0.079 |

Other controls: each of the four moved maps alone, and every control event without the 0.5-ATR exclusion.

**Gold**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control as used: four maps, events near a real level left out | 3634 (709) | 34.9% vs 37.7% | -2.8 [-6.4, +0.9] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 37.7% | **-4.1 [-6.9, -1.5]** | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| only the map moved by -1.0 % | 3634 (709) | 34.9% vs 39.3% | -4.4 [-9.6, +2.8] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 44.0% | **-10.4 [-14.8, -5.0]** | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| only the map moved by -0.6 % | 3634 (709) | 34.9% vs 35.6% | -0.7 [-5.1, +3.8] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 36.7% | -3.2 [-7.7, +0.9] | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| only the map moved by +0.6 % | 3634 (709) | 34.9% vs 36.6% | -1.7 [-6.1, +2.7] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 35.3% | -1.7 [-5.5, +1.9] | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| only the map moved by +1.0 % | 3634 (709) | 34.9% vs 39.5% | -4.7 [-10.2, +0.7] | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 37.9% | -4.3 [-7.9, +0.0] | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| every control event, also those near a real level | 3634 (709) | 34.9% vs 36.5% | **-1.7 [-3.1, -0.1]** | **-0.047 [-0.075, -0.020]** | -0.92 (-652) | -0.036 / -0.039 / -0.069 | 3396 (602) | 33.6% vs 35.5% | **-1.9 [-3.2, -0.8]** | **-0.085 [-0.106, -0.064]** | -0.62 (-376) | -0.114 / -0.076 / -0.067 |
| touches in a quiet minute only (range up to 0.5 ATR), control as used | 2955 (577) | 36.0% vs 37.4% | -1.4 [-5.4, +2.2] | -0.030 [-0.061, +0.000] | -0.59 (-340) | -0.025 / -0.010 / -0.065 | 2747 (487) | 34.6% vs 38.0% | **-3.3 [-6.5, -0.2]** | **-0.068 [-0.092, -0.044]** | -0.57 (-278) | -0.073 / -0.061 / -0.071 |
| touches in a quiet minute only, every control event | 2955 (577) | 36.0% vs 37.8% | **-1.8 [-3.5, -0.1]** | -0.030 [-0.061, +0.000] | -0.59 (-340) | -0.025 / -0.010 / -0.065 | 2747 (487) | 34.6% vs 36.4% | **-1.7 [-3.4, -0.3]** | **-0.068 [-0.092, -0.044]** | -0.57 (-278) | -0.073 / -0.061 / -0.071 |

**BTC**

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control as used: four maps, events near a real level left out | 6258 (1221) | 35.5% vs 36.8% | -1.2 [-4.6, +1.8] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 40.1% | **-4.9 [-8.0, -2.5]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| only the map moved by -1.5 % | 6258 (1221) | 35.5% vs 38.9% | -3.3 [-7.0, +0.9] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 41.6% | **-6.4 [-10.9, -2.8]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| only the map moved by -0.9 % | 6258 (1221) | 35.5% vs 41.2% | **-5.6 [-9.8, -1.2]** | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 40.2% | **-5.0 [-9.2, -0.1]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| only the map moved by +0.9 % | 6258 (1221) | 35.5% vs 34.8% | +0.7 [-5.0, +5.1] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 41.7% | **-6.6 [-11.0, -2.4]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| only the map moved by +1.5 % | 6258 (1221) | 35.5% vs 34.0% | +1.6 [-3.1, +5.2] | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 38.7% | -3.5 [-7.9, +0.8] | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| every control event, also those near a real level | 6258 (1221) | 35.5% vs 37.0% | **-1.4 [-2.5, -0.4]** | **-0.060 [-0.079, -0.039]** | -0.20 (-247) | -0.062 / -0.045 / -0.079 | 7065 (1253) | 35.2% vs 37.0% | **-1.8 [-2.7, -1.1]** | **-0.108 [-0.124, -0.091]** | -0.53 (-666) | -0.158 / -0.103 / -0.076 |
| touches in a quiet minute only (range up to 0.5 ATR), control as used | 4667 (911) | 37.5% vs 38.7% | -1.2 [-4.7, +2.5] | **-0.029 [-0.052, -0.005]** | -0.06 (-53) | -0.034 / -0.009 / -0.049 | 5738 (1017) | 36.3% vs 41.0% | **-4.7 [-8.0, -1.6]** | **-0.088 [-0.104, -0.071]** | -0.46 (-467) | -0.129 / -0.085 / -0.060 |
| touches in a quiet minute only, every control event | 4667 (911) | 37.5% vs 38.9% | **-1.3 [-2.5, -0.1]** | **-0.029 [-0.052, -0.005]** | -0.06 (-53) | -0.034 / -0.009 / -0.049 | 5738 (1017) | 36.3% vs 38.6% | **-2.3 [-3.2, -1.4]** | **-0.088 [-0.104, -0.071]** | -0.46 (-467) | -0.129 / -0.085 / -0.060 |

Without any target or stop: where price stood one and four hours after a touch, in ATRs from the touch price,
counted towards the bounce.

**Gold**

|  | DEV: events | DEV: real levels, ATR (95 %) | DEV: control | DEV: difference (95 %) | CONFIRM: events | CONFIRM: real levels, ATR (95 %) | CONFIRM: control | CONFIRM: difference (95 %) |
|---|---|---|---|---|---|---|---|---|
| 1 h after the touch | 3634 | -0.024 [-0.085, +0.031] | +0.019 | -0.043 [-0.131, +0.051] | 3396 | -0.025 [-0.085, +0.037] | +0.020 | -0.045 [-0.120, +0.019] |
| 4 h after the touch | 3634 | -0.068 [-0.159, +0.011] | +0.010 | -0.077 [-0.185, +0.048] | 3396 | +0.008 [-0.077, +0.107] | +0.007 | +0.002 [-0.138, +0.103] |

**BTC**

|  | DEV: events | DEV: real levels, ATR (95 %) | DEV: control | DEV: difference (95 %) | CONFIRM: events | CONFIRM: real levels, ATR (95 %) | CONFIRM: control | CONFIRM: difference (95 %) |
|---|---|---|---|---|---|---|---|---|
| 1 h after the touch | 6258 | -0.040 [-0.106, +0.028] | -0.091 | +0.051 [-0.048, +0.139] | 7065 | -0.014 [-0.045, +0.017] | +0.020 | -0.034 [-0.095, +0.027] |
| 4 h after the touch | 6258 | -0.079 [-0.161, +0.002] | -0.079 | -0.000 [-0.144, +0.143] | 7065 | -0.042 [-0.101, +0.016] | +0.001 | -0.043 [-0.154, +0.072] |

The picture does not move. Whatever the target and the stop, the levels hold no more often than the control
prices. Swings drawn with two or five bars, and a narrower or wider touch zone, give the same loss. Each of the
four control maps alone, and the control without the 0.5-ATR exclusion, puts the levels at or below the control
in eight of ten cases on DEV and in all ten on CONFIRM. Without the exclusion the control is several times
larger; the difference is then 1.4 to 1.9 points against the levels in all four columns, with its interval
below zero in all four.

News minutes do not make the result. A fifth to a quarter of all touches fall in a minute wider than half an ATR, at
the levels as at control prices (gold 19 / 19 % of touches at levels and 19 / 20 % of all control touches, DEV / CONFIRM; BTC
25 / 19 % and 28 / 21 %). Leaving those out (the last two rows of the control table; a check, not a rule,
because the range of a minute is known only when it is over) the bounce trade still loses and the levels still
hold less often than the control.

One and four hours after a touch, price stands where it stands after the touch of a control price.

## 5. How many things were tried

- One definition of a level and four variants of it (4.7); five trades; nine target / stop shapes of the bounce
  trade; one control and five variants of it.
- 334 table rows on the two symbols in each period (the tables of 4.2 to 4.5 and the through trade by state, in the
  appendix); they are counted in 4.6. With that many rows a handful of intervals lie above zero by chance
  alone: about one in forty.
- Not varied: the zone tolerance and the break buffer (0.25 ATR), the distance that makes an approach (1 ATR),
  the lifetime of a level, the class weights, the 0.5 ATR of the rejection trade, the 24-hour limit.

## 6. Limits

- **Two periods, 32 months together.** Gold rose through almost all of it; BTC both rose and fell.
- **Mechanical levels.** A trader chooses levels with judgement; this study can only test levels a rule can
  draw. The four variants of the rule agree with each other (4.7).
- **One-minute bars.** In 1.6 / 2.4 % of gold's touches (DEV / CONFIRM) and 1.8 / 1.1 % of BTC's the minute of the
  touch is so wide (news) that it holds both ends of the trade. The bounce trade's result in such a minute is
  certain. The through trade is counted as stopped although it may have reached its target first, which
  understates it by at most 1.6 ATR times that share: 0.03 / 0.04 ATR per trade in gold and 0.03 / 0.02 in BTC. Read
  in its favour throughout, gold's through trade would stand at about +0.02 to +0.03 ATR and BTC's at 0.00 to
  -0.04: still nothing to trade, and those are the minutes in which real fills are worst.
- **Stops are filled at their price** (or at the open after a gap). In the news minutes above a real stop would
  fill worse, so losses are, if anything, understated.
- **The level map starts empty** a month before each period, so levels older than that (old H4 and D1 swings)
  are missing in the first months.
- **No commission, swap or slippage**, as in the rest of the backtester.

## 7. The level detector

`backtesting.research.sr.nearest_levels(m1, symbol)` takes M1 bid bars as `backtesting.data.store.load_m1`
returns them and gives one row per M15 close with the nearest support and resistance known at that close:

| Column (`sup_...` and `res_...`) | Meaning |
|---|---|
| `price`, `dist` | the level, and the distance from the close in H1 ATRs (slightly negative while the level is being tested) |
| `kind`, `mask`, `tf` | how it came about (high, low, close, round); its classes, one bit each; the largest of them (`D1`, `W`, `H4`, `D`, `H1`, `round`) |
| `age_s`, `touches`, `flips`, `armed` | seconds since the extreme; approaches so far; times broken; whether price has been 1 ATR away since the last touch |
| `n_zone`, `zone_mask`, `strength` | known levels of the same side within 0.25 ATR; their classes; the zone's weight |

`t_close` is the time the row may be used from, `atr` the H1 ATR known then. `sr.scan(sr.prepare(m1, symbol))`
returns in addition every touch and break as an event (minute, level, side, entry price, zone). All parameters
are fields of `sr.SRParams`; `base_tf` changes the decision clock from M15 to M5. Sixteen months of M1 bars
take about half a second.

Causality is tested, not assumed: `tests/test_sr_levels.py` cuts the real bars of the fixture store, and a
75-day random history with weekends and daily breaks, at arbitrary minutes and requires every earlier row of
the table and every earlier event to be identical to what the full history gives. To use the table in a
backtest, compute it once from the M1 bars of the run and read, at each poll, the last row whose `t_close` is
not after the poll.

```
python -m backtesting.research.sr levels XAUUSDm 2026-10-01 2026-11-13
```

## 8. Reproduce

```
export ALCADEIAS_STORE_DIR=/path/to/data/store          # the tick store, months 2024-01 to 2026-11
python -m backtesting.research.sr study    DEV     out   # a few minutes a period
python -m backtesting.research.sr variants DEV     out
python -m backtesting.research.sr study    CONFIRM out
python -m backtesting.research.sr variants CONFIRM out
python -m backtesting.research.sr report   out            # every table of this file
python -m pytest tests/test_sr_levels.py -q
```

## Appendix: the through trade by the state of the level and of the market

**Gold**

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| side | support (buy) | 1835 (358) | 61.7% vs 57.3% | **+4.4 [+0.4, +8.8]** | -0.033 [-0.080, +0.009] | -0.50 (-180) | -0.096 / -0.004 / -0.016 | 1732 (307) | 62.0% vs 60.5% | +1.5 [-3.0, +6.0] | **-0.044 [-0.092, -0.002]** | -0.03 (-10) | -0.073 / -0.062 / -0.001 |
| side | resistance (sell) | 1799 (351) | 65.4% vs 64.4% | +1.0 [-4.3, +6.6] | +0.028 [-0.011, +0.067] | +0.67 (+234) | +0.057 / +0.008 / +0.023 | 1664 (295) | 66.1% vs 61.2% | **+5.0 [+1.8, +8.8]** | +0.025 [-0.013, +0.061] | +0.21 (+61) | +0.013 / +0.014 / +0.044 |
| levels in the zone | 1 | 2218 (433) | 62.3% vs 61.1% | +1.1 [-2.8, +5.0] | -0.022 [-0.055, +0.011] | -0.51 (-221) | -0.010 / -0.039 / -0.012 | 2179 (386) | 63.8% vs 60.1% | **+3.7 [+0.2, +7.1]** | -0.014 [-0.046, +0.017] | +0.06 (+24) | -0.052 / -0.004 / +0.010 |
| levels in the zone | 2 | 997 (195) | 63.7% vs 58.4% | +5.3 [-1.7, +11.3] | -0.002 [-0.067, +0.052] | +0.49 (+96) | -0.080 / +0.022 / +0.032 | 902 (160) | 65.0% vs 62.3% | +2.7 [-3.1, +8.5] | +0.003 [-0.053, +0.056] | +0.18 (+28) | -0.021 / -0.050 / +0.076 |
| levels in the zone | 3 or more | 419 (82) | 69.8% vs 57.8% | +12.0 [-0.7, +23.1] | **+0.096 [+0.018, +0.180]** | +2.18 (+178) | +0.087 / +0.147 / +0.007 | 315 (56) | 62.7% vs 62.1% | +0.7 [-7.4, +10.0] | -0.023 [-0.106, +0.072] | -0.04 (-2) | +0.138 / -0.080 / -0.052 |
| zone strength | 1-2 | 1074 (210) | 62.4% vs 61.0% | +1.4 [-3.6, +7.3] | -0.021 [-0.070, +0.028] | -0.21 (-45) | +0.017 / -0.057 / -0.022 | 1296 (230) | 64.0% vs 60.5% | +3.5 [-1.0, +8.8] | -0.012 [-0.055, +0.031] | +0.10 (+22) | -0.027 / -0.025 / +0.015 |
| zone strength | 3-4 | 1102 (215) | 61.3% vs 60.7% | +0.7 [-4.1, +5.0] | -0.035 [-0.079, +0.013] | -0.80 (-172) | -0.072 / -0.057 / +0.025 | 1038 (184) | 64.1% vs 61.3% | +2.8 [-1.6, +6.7] | -0.011 [-0.054, +0.031] | +0.04 (+7) | -0.050 / -0.019 / +0.031 |
| zone strength | 5-6 | 1000 (195) | 64.6% vs 59.0% | +5.5 [-0.1, +11.1] | +0.008 [-0.047, +0.060] | +0.08 (+15) | -0.022 / +0.015 / +0.020 | 772 (137) | 63.8% vs 62.3% | +1.6 [-3.6, +7.4] | -0.012 [-0.076, +0.050] | +0.12 (+16) | -0.067 / +0.010 / +0.014 |
| zone strength | 7 or more | 458 (89) | 69.3% vs 64.5% | +4.8 [-8.4, +17.5] | **+0.090 [+0.017, +0.163]** | +2.85 (+255) | +0.031 / +0.189 / -0.043 | 290 (51) | 64.2% vs 63.1% | +1.2 [-8.8, +10.9] | +0.001 [-0.100, +0.103] | +0.11 (+6) | +0.222 / -0.111 / +0.030 |
| earlier touches | none (first touch) | 852 (166) | 63.2% vs 61.3% | +1.9 [-2.5, +7.8] | -0.009 [-0.059, +0.038] | +0.13 (+21) | +0.035 / -0.013 / -0.058 | 1050 (186) | 65.1% vs 61.7% | +3.4 [-1.3, +9.1] | +0.005 [-0.049, +0.058] | +0.22 (+42) | -0.018 / +0.031 / +0.001 |
| earlier touches | 1 | 664 (130) | 61.8% vs 57.9% | +3.9 [-4.4, +11.0] | -0.029 [-0.101, +0.039] | -1.02 (-132) | -0.013 / -0.101 / +0.042 | 810 (144) | 63.9% vs 57.6% | **+6.2 [+0.1, +11.1]** | -0.014 [-0.072, +0.043] | +0.09 (+12) | +0.009 / -0.150 / +0.089 |
| earlier touches | 2 | 407 (79) | 62.3% vs 53.9% | +8.3 [-1.4, +16.2] | -0.020 [-0.101, +0.064] | -0.22 (-17) | -0.036 / -0.011 / -0.015 | 508 (90) | 63.9% vs 62.0% | +1.9 [-5.6, +9.5] | -0.014 [-0.085, +0.053] | -0.24 (-22) | -0.016 / +0.021 / -0.045 |
| earlier touches | 3 or more | 1711 (334) | 64.7% vs 60.4% | +4.3 [-0.1, +9.3] | +0.014 [-0.027, +0.051] | +0.54 (+181) | -0.051 / +0.041 / +0.023 | 1028 (182) | 63.1% vs 61.8% | +1.3 [-3.8, +5.3] | -0.022 [-0.073, +0.026] | +0.10 (+18) | -0.099 / -0.011 / +0.020 |
| role (not round numbers) | never broken | 1576 (307) | 64.7% vs 59.9% | **+4.9 [+0.1, +9.6]** | +0.014 [-0.028, +0.055] | +0.50 (+153) | +0.013 / +0.037 / -0.010 | 1759 (312) | 67.1% vs 62.4% | **+4.7 [+0.8, +9.2]** | **+0.037 [+0.002, +0.073]** | +0.39 (+121) | +0.063 / +0.000 / +0.052 |
| role (not round numbers) | broken once, retested from the other side | 959 (187) | 61.0% vs 61.4% | -0.3 [-7.6, +5.7] | -0.042 [-0.107, +0.025] | -0.88 (-165) | -0.056 / -0.063 / -0.001 | 1184 (210) | 60.5% vs 59.3% | +1.3 [-4.6, +6.5] | **-0.066 [-0.111, -0.020]** | -0.23 (-49) | -0.108 / -0.074 / -0.011 |
| age (not round numbers) | under 1 day | 1218 (238) | 62.1% vs 61.2% | +0.9 [-4.9, +6.0] | -0.024 [-0.081, +0.029] | -0.20 (-47) | -0.005 / -0.089 / +0.030 | 1383 (245) | 65.2% vs 59.8% | **+5.4 [+0.1, +9.1]** | +0.009 [-0.031, +0.048] | +0.23 (+58) | -0.002 / -0.029 / +0.055 |
| age (not round numbers) | 1-5 days | 843 (164) | 65.6% vs 58.9% | **+6.7 [+0.7, +12.4]** | +0.023 [-0.033, +0.078] | +0.15 (+24) | +0.034 / +0.056 / -0.026 | 911 (162) | 62.9% vs 61.3% | +1.6 [-4.5, +6.9] | -0.032 [-0.081, +0.017] | -0.05 (-8) | -0.095 / -0.015 / +0.007 |
| age (not round numbers) | 5-20 days | 392 (76) | 60.4% vs 59.2% | +1.2 [-7.7, +13.0] | -0.051 [-0.137, +0.035] | -0.76 (-58) | -0.143 / +0.088 / -0.112 | 543 (96) | 64.7% vs 57.3% | +7.4 [-0.3, +16.4] | +0.001 [-0.057, +0.063] | +0.23 (+22) | +0.083 / -0.089 / +0.026 |
| age (not round numbers) | over 20 days | 82 (16) | 73.2% vs 61.4% | +11.7 [-7.1, +29.7] | **+0.158 [+0.014, +0.317]** | +4.36 (+70) | +0.209 / +0.162 / +0.129 | 106 (19) | 66.7% vs 76.4% | -9.7 [-26.5, +3.3] | +0.038 [-0.090, +0.160] | -0.00 (-0) | +0.098 / +0.143 / -0.144 |
| H4 trend (MACD signal line) | trade with it | 1837 (358) | 62.1% vs 56.1% | +6.0 [-0.8, +10.7] | -0.028 [-0.073, +0.015] | +0.11 (+40) | -0.074 / -0.013 / -0.005 | 1824 (323) | 63.2% vs 59.6% | +3.5 [-0.8, +8.0] | -0.025 [-0.067, +0.009] | +0.08 (+27) | -0.039 / -0.059 / +0.017 |
| H4 trend (MACD signal line) | trade against it | 1797 (351) | 65.1% vs 63.8% | +1.2 [-3.9, +6.3] | +0.023 [-0.018, +0.064] | +0.04 (+13) | +0.041 / +0.018 / +0.011 | 1572 (279) | 65.0% vs 62.8% | +2.2 [-1.7, +6.5] | +0.006 [-0.038, +0.047] | +0.08 (+24) | -0.024 / +0.013 / +0.027 |
| D1 trend (close vs EMA20) | trade with it | 1887 (368) | 62.3% vs 57.7% | +4.6 [-1.7, +10.1] | -0.025 [-0.075, +0.021] | +0.06 (+22) | -0.066 / +0.003 / -0.022 | 1843 (327) | 64.6% vs 60.6% | **+3.9 [+0.1, +8.3]** | -0.002 [-0.042, +0.032] | +0.22 (+72) | -0.009 / -0.017 / +0.017 |
| D1 trend (close vs EMA20) | trade against it | 1747 (341) | 64.9% vs 62.4% | +2.5 [-2.5, +7.0] | +0.020 [-0.016, +0.057] | +0.09 (+31) | +0.037 / +0.001 / +0.030 | 1553 (275) | 63.4% vs 61.3% | +2.1 [-1.9, +6.3] | -0.020 [-0.068, +0.023] | -0.08 (-21) | -0.059 / -0.033 / +0.027 |
| H4 and D1 trend | with both | 1561 (305) | 62.0% vs 55.8% | +6.3 [-1.2, +12.1] | -0.030 [-0.079, +0.017] | +0.15 (+46) | -0.068 / -0.008 / -0.020 | 1516 (269) | 63.7% vs 60.6% | +3.1 [-1.1, +7.6] | -0.016 [-0.062, +0.023] | +0.16 (+43) | -0.024 / -0.035 / +0.007 |
| H4 and D1 trend | against both | 1471 (287) | 65.4% vs 62.7% | +2.7 [-2.9, +7.9] | +0.027 [-0.014, +0.069] | +0.13 (+37) | +0.056 / +0.009 / +0.022 | 1245 (221) | 64.1% vs 63.0% | +1.1 [-2.8, +5.7] | -0.008 [-0.066, +0.040] | -0.02 (-5) | -0.047 / +0.001 / +0.016 |
| M15 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 482 (94) | 62.3% vs 66.5% | -4.2 [-12.9, +7.0] | -0.016 [-0.088, +0.059] | -0.92 (-87) | -0.109 / +0.039 / -0.028 | 506 (90) | 63.4% vs 64.1% | -0.7 [-8.3, +8.8] | -0.016 [-0.077, +0.044] | +0.02 (+2) | -0.025 / +0.000 / -0.021 |
| M15 RSI at the touch | 30-50 (50-70) | 2253 (440) | 64.4% vs 58.2% | **+6.3 [+0.7, +10.8]** | +0.009 [-0.030, +0.044] | +0.45 (+199) | +0.010 / +0.003 / +0.016 | 2072 (367) | 66.7% vs 58.9% | **+7.8 [+3.2, +11.7]** | **+0.032 [+0.001, +0.065]** | +0.34 (+125) | +0.063 / -0.002 / +0.039 |
| M15 RSI at the touch | not stretched | 899 (175) | 62.0% vs 60.6% | +1.4 [-7.0, +8.0] | -0.027 [-0.087, +0.029] | -0.34 (-59) | -0.048 / -0.023 / -0.013 | 818 (145) | 57.6% vs 59.7% | -2.1 [-8.7, +1.4] | **-0.114 [-0.182, -0.048]** | -0.52 (-76) | -0.247 / -0.097 / +0.001 |
| H1 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 309 (60) | 64.0% vs 65.7% | -1.7 [-13.7, +7.3] | +0.010 [-0.073, +0.090] | +0.05 (+3) | -0.004 / +0.050 / -0.042 | 237 (42) | 63.8% vs 60.3% | +3.6 [-6.0, +15.7] | -0.010 [-0.104, +0.080] | -0.08 (-3) | -0.083 / +0.109 / -0.030 |
| H1 RSI at the touch | 30-50 (50-70) | 1794 (350) | 64.7% vs 57.9% | **+6.8 [+2.0, +11.6]** | +0.015 [-0.026, +0.056] | +0.47 (+164) | +0.024 / +0.046 / -0.033 | 1729 (307) | 65.2% vs 64.4% | +0.8 [-4.0, +5.9] | +0.009 [-0.029, +0.051] | +0.18 (+56) | +0.005 / -0.005 / +0.025 |
| H1 RSI at the touch | not stretched | 1531 (299) | 62.1% vs 60.4% | +1.7 [-4.9, +7.5] | -0.027 [-0.081, +0.025] | -0.38 (-113) | -0.067 / -0.056 / +0.059 | 1430 (254) | 62.6% vs 57.4% | **+5.1 [+0.6, +9.1]** | -0.034 [-0.085, +0.016] | -0.01 (-2) | -0.062 / -0.065 / +0.026 |
| RSI divergence (unbroken extremes) | yes | 567 (111) | 68.7% vs 54.5% | **+14.1 [+5.8, +22.8]** | **+0.074 [+0.014, +0.136]** | +1.59 (+176) | +0.161 / +0.096 / -0.034 | 659 (117) | 65.1% vs 56.5% | +8.6 [-1.4, +17.7] | +0.008 [-0.053, +0.070] | +0.28 (+33) | +0.011 / -0.084 / +0.093 |
| RSI divergence (unbroken extremes) | no | 842 (164) | 64.0% vs 59.8% | +4.2 [-4.3, +10.8] | +0.004 [-0.044, +0.051] | +0.44 (+72) | -0.019 / +0.049 / -0.027 | 931 (165) | 68.5% vs 64.4% | +4.1 [-3.6, +12.0] | **+0.059 [+0.014, +0.109]** | +0.46 (+76) | +0.103 / +0.068 / +0.018 |
| approach in the last hour | under 0.5 ATR | 795 (155) | 62.3% vs 59.5% | +2.7 [-4.2, +9.4] | -0.021 [-0.069, +0.030] | +0.05 (+8) | -0.024 / -0.033 / +0.001 | 689 (122) | 63.3% vs 62.3% | +1.0 [-4.6, +7.7] | -0.017 [-0.080, +0.043] | +0.00 (+0) | -0.113 / -0.034 / +0.076 |
| approach in the last hour | 0.5-1.5 ATR | 2007 (392) | 65.0% vs 61.7% | +3.3 [-1.2, +7.7] | +0.025 [-0.007, +0.056] | +0.75 (+292) | +0.001 / +0.041 / +0.025 | 1853 (329) | 65.9% vs 61.3% | **+4.6 [+0.0, +8.5]** | +0.023 [-0.009, +0.053] | +0.32 (+106) | +0.031 / -0.003 / +0.040 |
| approach in the last hour | over 1.5 ATR | 759 (148) | 59.8% vs 56.0% | +3.8 [-4.0, +14.0] | -0.059 [-0.137, +0.006] | -1.56 (-231) | -0.051 / -0.062 / -0.064 | 783 (139) | 60.3% vs 56.0% | +4.2 [-1.7, +11.0] | -0.071 [-0.143, +0.001] | -0.32 (-45) | -0.062 / -0.071 / -0.081 |
| last five days (efficiency ratio of H1 closes) | ranging (under 0.06) | 1116 (218) | 63.3% vs 59.8% | +3.5 [-3.3, +8.7] | -0.006 [-0.062, +0.052] | +0.06 (+13) | -0.053 / +0.015 / +0.003 | 1225 (217) | 62.5% vs 62.6% | -0.0 [-5.0, +7.4] | -0.034 [-0.073, +0.010] | -0.07 (-15) | -0.099 / -0.037 / +0.038 |
| last five days (efficiency ratio of H1 closes) | in between | 1194 (233) | 64.0% vs 59.8% | +4.2 [-1.7, +10.8] | -0.001 [-0.047, +0.047] | +0.59 (+137) | -0.077 / +0.052 / +0.000 | 1047 (186) | 63.4% vs 56.9% | **+6.6 [+0.1, +11.5]** | -0.019 [-0.073, +0.032] | -0.03 (-6) | +0.014 / -0.040 / -0.031 |
| last five days (efficiency ratio of H1 closes) | trending (over 0.125) | 1324 (258) | 63.3% vs 60.3% | +3.1 [-2.9, +9.3] | -0.003 [-0.048, +0.044] | -0.37 (-96) | +0.050 / -0.047 / +0.006 | 1124 (199) | 66.2% vs 61.4% | +4.8 [-0.4, +10.0] | +0.023 [-0.032, +0.083] | +0.36 (+71) | +0.005 / +0.001 / +0.062 |
| session (UTC) | Asia 22-07 | 1332 (260) | 66.6% vs 61.6% | **+5.1 [+0.1, +10.7]** | +0.040 [-0.009, +0.083] | +1.12 (+290) | +0.004 / +0.052 / +0.056 | 1005 (178) | 67.0% vs 60.3% | **+6.7 [+1.2, +12.3]** | +0.033 [-0.007, +0.073] | +0.29 (+52) | +0.002 / +0.053 / +0.036 |
| session (UTC) | London 07-12 | 561 (109) | 61.3% vs 64.4% | -3.1 [-11.5, +5.2] | -0.034 [-0.112, +0.041] | +0.67 (+73) | -0.096 / -0.064 / +0.078 | 697 (124) | 65.4% vs 64.6% | +0.8 [-4.8, +7.2] | +0.016 [-0.041, +0.076] | +0.28 (+35) | -0.000 / -0.031 / +0.077 |
| session (UTC) | London + New York 12-16 | 1146 (224) | 61.9% vs 56.3% | +5.6 [-0.9, +11.6] | -0.027 [-0.077, +0.023] | -1.35 (-301) | +0.013 / -0.025 / -0.066 | 1276 (226) | 62.3% vs 58.3% | +4.0 [-1.4, +9.8] | -0.037 [-0.096, +0.019] | +0.03 (+7) | -0.076 / -0.059 / +0.040 |
| session (UTC) | New York 16-22 | 595 (116) | 61.9% vs 64.6% | -2.7 [-11.0, +5.0] | -0.024 [-0.094, +0.044] | -0.07 (-9) | -0.035 / -0.009 / -0.034 | 418 (74) | 59.4% vs 63.4% | -4.0 [-10.9, +3.8] | -0.078 [-0.165, +0.014] | -0.59 (-44) | +0.011 / -0.074 / -0.153 |
| volatility (H1 ATR vs its 20-day median) | low | 682 (133) | 61.4% vs 58.2% | +3.2 [-3.0, +9.2] | -0.048 [-0.130, +0.019] | -0.59 (-78) | -0.069 / -0.013 / -0.076 | 601 (107) | 60.2% vs 59.3% | +0.9 [-6.1, +11.3] | **-0.081 [-0.145, -0.010]** | -0.32 (-35) | -0.062 / -0.171 / -0.034 |
| volatility (H1 ATR vs its 20-day median) | normal | 2187 (427) | 64.3% vs 60.6% | +3.7 [-0.5, +7.9] | +0.011 [-0.024, +0.045] | +0.23 (+98) | +0.005 / +0.000 / +0.027 | 2180 (387) | 64.3% vs 61.0% | **+3.3 [+0.1, +6.9]** | -0.007 [-0.043, +0.026] | +0.06 (+24) | -0.032 / -0.021 / +0.027 |
| volatility (H1 ATR vs its 20-day median) | high | 765 (149) | 63.2% vs 63.6% | -0.4 [-9.0, +8.7] | -0.004 [-0.056, +0.044] | +0.23 (+34) | -0.018 / +0.017 / -0.052 | 615 (109) | 66.9% vs 61.7% | **+5.2 [+0.4, +10.4]** | +0.045 [-0.025, +0.115] | +0.56 (+62) | +0.005 / +0.097 / +0.047 |

**BTC**

|  |  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| side | support (buy) | 3206 (626) | 63.0% vs 58.6% | +4.3 [-2.1, +9.8] | -0.026 [-0.064, +0.009] | -0.21 (-131) | -0.043 / -0.007 / -0.029 | 3611 (640) | 62.5% vs 58.2% | **+4.3 [+0.7, +8.6]** | **-0.076 [-0.100, -0.051]** | -0.44 (-281) | -0.158 / -0.046 / -0.040 |
| side | resistance (sell) | 3052 (595) | 62.3% vs 60.7% | +1.6 [-2.0, +4.9] | **-0.038 [-0.071, -0.008]** | -0.25 (-151) | -0.037 / -0.084 / +0.021 | 3454 (612) | 65.0% vs 59.3% | **+5.7 [+1.9, +10.3]** | **-0.030 [-0.057, -0.003]** | -0.14 (-84) | -0.062 / -0.011 / -0.028 |
| levels in the zone | 1 | 3798 (741) | 61.7% vs 59.1% | +2.6 [-0.8, +5.4] | **-0.047 [-0.070, -0.024]** | -0.31 (-226) | -0.050 / -0.090 / +0.015 | 4274 (758) | 62.3% vs 58.2% | **+4.1 [+1.1, +7.6]** | **-0.077 [-0.100, -0.053]** | -0.44 (-333) | -0.158 / -0.031 / -0.060 |
| levels in the zone | 2 | 1703 (332) | 64.3% vs 60.0% | +4.3 [-0.1, +11.0] | -0.006 [-0.052, +0.040] | -0.06 (-19) | -0.017 / +0.030 / -0.043 | 2016 (357) | 64.3% vs 59.2% | **+5.1 [+0.6, +9.5]** | **-0.043 [-0.070, -0.013]** | -0.23 (-83) | -0.038 / -0.061 / -0.029 |
| levels in the zone | 3 or more | 757 (148) | 63.7% vs 59.1% | +4.6 [-4.3, +15.4] | -0.013 [-0.082, +0.057] | -0.25 (-37) | -0.046 / +0.026 / -0.017 | 775 (137) | 69.9% vs 60.8% | **+9.2 [+2.3, +17.3]** | +0.046 [-0.009, +0.102] | +0.36 (+50) | -0.052 / +0.072 / +0.087 |
| zone strength | 1-2 | 1558 (304) | 62.6% vs 53.6% | **+9.0 [+4.1, +13.3]** | -0.034 [-0.075, +0.004] | -0.29 (-88) | -0.037 / -0.070 / +0.014 | 1647 (292) | 62.4% vs 55.4% | **+7.0 [+1.4, +12.9]** | **-0.086 [-0.122, -0.049]** | -0.46 (-135) | -0.162 / -0.040 / -0.066 |
| zone strength | 3-4 | 2320 (453) | 62.1% vs 61.2% | +0.8 [-2.6, +4.8] | **-0.039 [-0.073, -0.006]** | -0.25 (-111) | -0.037 / -0.073 / +0.003 | 2728 (484) | 61.9% vs 59.6% | +2.3 [-1.3, +5.9] | **-0.080 [-0.110, -0.050]** | -0.48 (-232) | -0.168 / -0.035 / -0.057 |
| zone strength | 5-6 | 1728 (337) | 63.1% vs 62.5% | +0.6 [-5.4, +7.0] | -0.025 [-0.066, +0.019] | -0.15 (-51) | -0.030 / -0.007 / -0.042 | 1964 (348) | 65.8% vs 60.1% | **+5.7 [+0.9, +11.0]** | -0.015 [-0.043, +0.016] | -0.07 (-25) | -0.001 / -0.020 / -0.020 |
| zone strength | 7 or more | 652 (127) | 63.2% vs 62.8% | +0.4 [-8.4, +13.4] | -0.019 [-0.105, +0.066] | -0.25 (-32) | -0.079 / +0.022 / +0.019 | 726 (129) | 67.8% vs 62.4% | +5.4 [-4.1, +17.1] | +0.015 [-0.034, +0.068] | +0.20 (+26) | -0.053 / +0.005 / +0.061 |
| earlier touches | none (first touch) | 1197 (234) | 64.8% vs 51.4% | **+13.4 [+7.9, +18.5]** | +0.001 [-0.043, +0.040] | -0.16 (-37) | -0.015 / -0.025 / +0.047 | 1280 (227) | 62.0% vs 56.2% | **+5.8 [+0.7, +12.5]** | **-0.093 [-0.137, -0.052]** | -0.54 (-123) | -0.124 / -0.066 / -0.095 |
| earlier touches | 1 | 978 (191) | 61.1% vs 52.8% | **+8.3 [+2.5, +13.9]** | **-0.057 [-0.106, -0.009]** | -0.34 (-64) | -0.080 / -0.042 / -0.054 | 1034 (183) | 63.3% vs 57.4% | +5.9 [-0.8, +12.1] | **-0.068 [-0.124, -0.015]** | -0.31 (-57) | -0.169 / -0.019 / -0.027 |
| earlier touches | 2 | 667 (130) | 62.2% vs 63.5% | -1.3 [-8.2, +5.7] | -0.039 [-0.108, +0.023] | -0.20 (-26) | -0.006 / -0.159 / +0.075 | 711 (126) | 62.5% vs 55.3% | **+7.2 [+0.8, +15.4]** | **-0.076 [-0.117, -0.032]** | -0.43 (-54) | -0.144 / -0.046 / -0.048 |
| earlier touches | 3 or more | 3416 (667) | 62.4% vs 62.9% | -0.5 [-4.5, +4.2] | **-0.034 [-0.063, -0.004]** | -0.23 (-155) | -0.044 / -0.030 / -0.026 | 4040 (716) | 64.6% vs 61.0% | **+3.6 [+0.6, +6.9]** | **-0.033 [-0.054, -0.011]** | -0.18 (-132) | -0.085 / -0.014 / -0.019 |
| role (not round numbers) | never broken | 2482 (484) | 65.4% vs 53.9% | **+11.4 [+6.9, +15.6]** | +0.010 [-0.026, +0.044] | -0.03 (-12) | -0.020 / +0.032 / +0.012 | 2701 (479) | 64.8% vs 59.0% | **+5.9 [+1.8, +10.6]** | **-0.044 [-0.074, -0.013]** | -0.20 (-94) | -0.101 / -0.009 / -0.031 |
| role (not round numbers) | broken once, retested from the other side | 1644 (321) | 59.1% vs 60.5% | -1.4 [-6.8, +3.9] | **-0.089 [-0.130, -0.049]** | -0.47 (-150) | -0.077 / -0.129 / -0.054 | 1681 (298) | 62.1% vs 55.5% | **+6.6 [+0.7, +11.8]** | **-0.082 [-0.118, -0.043]** | -0.40 (-121) | -0.176 / -0.052 / -0.043 |
| age (not round numbers) | under 1 day | 2102 (410) | 64.4% vs 56.6% | **+7.8 [+2.8, +11.9]** | -0.005 [-0.040, +0.032] | -0.08 (-33) | +0.011 / -0.006 / -0.018 | 2269 (402) | 64.4% vs 58.3% | **+6.1 [+1.9, +10.3]** | **-0.049 [-0.081, -0.019]** | -0.20 (-79) | -0.130 / +0.001 / -0.034 |
| age (not round numbers) | 1-5 days | 1279 (250) | 62.3% vs 56.7% | **+5.6 [+0.7, +10.7]** | **-0.041 [-0.082, -0.004]** | -0.21 (-52) | -0.074 / -0.032 / -0.023 | 1408 (250) | 63.5% vs 55.1% | **+8.5 [+1.5, +15.3]** | **-0.065 [-0.106, -0.024]** | -0.35 (-87) | -0.108 / -0.059 / -0.037 |
| age (not round numbers) | 5-20 days | 574 (112) | 61.5% vs 58.5% | +3.0 [-6.6, +13.5] | -0.049 [-0.122, +0.022] | -0.36 (-41) | -0.094 / -0.059 / +0.030 | 574 (102) | 60.6% vs 61.9% | -1.3 [-9.8, +7.8] | **-0.098 [-0.160, -0.033]** | -0.56 (-57) | -0.227 / -0.076 / -0.051 |
| age (not round numbers) | over 20 days | 171 (33) | 52.6% vs 53.6% | -0.9 [-14.0, +17.7] | **-0.188 [-0.309, -0.068]** | -1.11 (-37) | -0.246 / -0.203 / -0.042 | 131 (23) | 68.7% vs 65.3% | +3.4 [-12.5, +20.6] | +0.037 [-0.042, +0.114] | +0.41 (+9) | -0.006 / +0.063 / +0.045 |
| H4 trend (MACD signal line) | trade with it | 3183 (621) | 62.6% vs 59.9% | +2.6 [-1.8, +7.0] | **-0.033 [-0.067, -0.001]** | -0.21 (-132) | -0.039 / -0.053 / -0.001 | 3621 (642) | 63.2% vs 56.5% | **+6.7 [+2.5, +11.0]** | **-0.061 [-0.085, -0.038]** | -0.30 (-195) | -0.153 / -0.021 / -0.036 |
| H4 trend (MACD signal line) | trade against it | 3075 (600) | 62.7% vs 57.3% | +5.4 [-0.1, +9.6] | -0.030 [-0.063, +0.002] | -0.25 (-150) | -0.040 / -0.036 / -0.007 | 3444 (611) | 64.2% vs 60.3% | **+3.9 [+0.8, +8.4]** | **-0.045 [-0.072, -0.019]** | -0.28 (-171) | -0.075 / -0.036 / -0.031 |
| D1 trend (close vs EMA20) | trade with it | 3231 (630) | 62.1% vs 61.5% | +0.6 [-4.7, +5.0] | **-0.041 [-0.077, -0.009]** | -0.32 (-199) | -0.058 / -0.071 / +0.014 | 3623 (642) | 62.7% vs 56.6% | **+6.0 [+1.6, +10.2]** | **-0.071 [-0.095, -0.046]** | -0.35 (-226) | -0.141 / -0.043 / -0.045 |
| D1 trend (close vs EMA20) | trade against it | 3027 (591) | 63.3% vs 58.0% | **+5.2 [+0.7, +9.3]** | -0.021 [-0.052, +0.010] | -0.14 (-83) | -0.022 / -0.018 / -0.025 | 3442 (610) | 64.8% vs 60.1% | **+4.8 [+1.3, +9.9]** | **-0.035 [-0.062, -0.007]** | -0.23 (-139) | -0.084 / -0.013 / -0.022 |
| H4 and D1 trend | with both | 2658 (519) | 62.0% vs 60.3% | +1.7 [-3.3, +5.6] | **-0.042 [-0.077, -0.009]** | -0.28 (-145) | -0.052 / -0.071 / +0.003 | 2951 (523) | 63.1% vs 55.9% | **+7.2 [+2.1, +12.0]** | **-0.063 [-0.090, -0.035]** | -0.32 (-167) | -0.143 / -0.029 / -0.035 |
| H4 and D1 trend | against both | 2502 (488) | 62.8% vs 57.6% | **+5.2 [+0.0, +9.8]** | -0.028 [-0.061, +0.006] | -0.20 (-96) | -0.030 / -0.029 / -0.025 | 2772 (491) | 65.1% vs 59.9% | **+5.2 [+1.4, +10.7]** | **-0.030 [-0.059, -0.001]** | -0.23 (-112) | -0.061 / -0.019 / -0.018 |
| M15 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 917 (179) | 63.8% vs 58.9% | +4.9 [-6.2, +17.3] | -0.011 [-0.095, +0.064] | -0.32 (-58) | -0.085 / -0.011 / +0.088 | 970 (172) | 61.1% vs 57.6% | +3.6 [-2.3, +11.7] | **-0.094 [-0.140, -0.051]** | -0.63 (-108) | -0.133 / -0.079 / -0.081 |
| M15 RSI at the touch | 30-50 (50-70) | 3754 (732) | 63.2% vs 59.6% | +3.6 [-0.6, +7.3] | -0.023 [-0.051, +0.002] | -0.20 (-145) | -0.026 / -0.041 / +0.006 | 4324 (767) | 64.4% vs 60.0% | **+4.4 [+0.7, +8.6]** | **-0.043 [-0.065, -0.019]** | -0.22 (-168) | -0.106 / -0.016 / -0.023 |
| M15 RSI at the touch | not stretched | 1587 (310) | 60.7% vs 61.6% | -0.9 [-5.7, +4.4] | **-0.064 [-0.098, -0.030]** | -0.25 (-79) | -0.043 / -0.072 / -0.075 | 1771 (314) | 63.4% vs 58.5% | **+4.9 [+0.4, +9.8]** | **-0.057 [-0.095, -0.020]** | -0.29 (-90) | -0.122 / -0.031 / -0.036 |
| H1 RSI at the touch | stretched (under 30 at support, over 70 at resistance) | 632 (123) | 60.4% vs 66.5% | -6.1 [-17.3, +8.3] | -0.063 [-0.149, +0.023] | -0.63 (-77) | -0.193 / -0.000 / +0.082 | 547 (97) | 62.3% vs 55.7% | +6.7 [-2.0, +15.0] | **-0.067 [-0.134, -0.013]** | -0.47 (-45) | -0.084 / -0.026 / -0.100 |
| H1 RSI at the touch | 30-50 (50-70) | 3006 (587) | 63.6% vs 57.0% | **+6.6 [+2.8, +11.1]** | -0.016 [-0.043, +0.011] | -0.18 (-107) | -0.038 / -0.036 / +0.034 | 3585 (636) | 64.2% vs 58.5% | **+5.7 [+1.2, +9.8]** | **-0.049 [-0.073, -0.021]** | -0.32 (-201) | -0.116 / -0.020 / -0.029 |
| H1 RSI at the touch | not stretched | 2620 (511) | 62.1% vs 61.1% | +1.0 [-3.4, +5.2] | **-0.042 [-0.076, -0.007]** | -0.19 (-97) | +0.004 / -0.066 / -0.062 | 2933 (520) | 63.4% vs 60.4% | +3.1 [-0.9, +7.7] | **-0.056 [-0.086, -0.025]** | -0.23 (-119) | -0.118 / -0.039 / -0.029 |
| RSI divergence (unbroken extremes) | yes | 913 (178) | 64.8% vs 56.0% | **+8.9 [+0.2, +17.6]** | -0.001 [-0.055, +0.052] | -0.09 (-16) | -0.091 / +0.044 / +0.028 | 952 (169) | 65.1% vs 52.8% | **+12.3 [+4.2, +21.9]** | -0.040 [-0.091, +0.014] | -0.14 (-23) | -0.100 / -0.008 / -0.026 |
| RSI divergence (unbroken extremes) | no | 1349 (263) | 65.6% vs 55.2% | **+10.4 [+3.9, +16.4]** | +0.015 [-0.032, +0.058] | +0.02 (+5) | +0.032 / +0.007 / +0.008 | 1521 (270) | 64.8% vs 59.8% | **+5.0 [+0.8, +13.1]** | **-0.043 [-0.084, -0.002]** | -0.22 (-59) | -0.105 / -0.014 / -0.020 |
| approach in the last hour | under 0.5 ATR | 1340 (261) | 63.2% vs 62.1% | +1.0 [-5.6, +7.1] | -0.022 [-0.063, +0.020] | -0.11 (-29) | -0.002 / -0.051 / -0.007 | 1586 (281) | 64.5% vs 63.0% | +1.5 [-3.1, +5.7] | -0.037 [-0.076, +0.005] | -0.22 (-62) | -0.140 / +0.007 / -0.012 |
| approach in the last hour | 0.5-1.5 ATR | 3472 (677) | 63.1% vs 63.0% | +0.1 [-3.8, +3.6] | -0.024 [-0.049, +0.000] | -0.22 (-150) | -0.043 / -0.026 / +0.001 | 3949 (700) | 63.9% vs 57.3% | **+6.7 [+2.4, +10.6]** | **-0.051 [-0.074, -0.029]** | -0.24 (-171) | -0.097 / -0.032 / -0.034 |
| approach in the last hour | over 1.5 ATR | 1424 (278) | 60.7% vs 48.4% | **+12.3 [+4.6, +17.1]** | **-0.062 [-0.114, -0.014]** | -0.37 (-104) | -0.078 / -0.085 / -0.012 | 1516 (269) | 62.2% vs 56.7% | **+5.5 [+0.8, +12.5]** | **-0.078 [-0.116, -0.037]** | -0.49 (-131) | -0.133 / -0.057 / -0.059 |
| last five days (efficiency ratio of H1 closes) | ranging (under 0.06) | 2344 (457) | 63.6% vs 61.7% | +1.9 [-2.6, +6.6] | -0.016 [-0.051, +0.016] | -0.12 (-53) | -0.021 / -0.014 / -0.013 | 2676 (474) | 64.8% vs 57.9% | **+6.9 [+1.9, +11.6]** | **-0.039 [-0.066, -0.010]** | -0.28 (-133) | -0.069 / -0.019 / -0.037 |
| last five days (efficiency ratio of H1 closes) | in between | 1967 (384) | 62.1% vs 56.3% | **+5.9 [+1.6, +10.3]** | **-0.040 [-0.075, -0.006]** | -0.21 (-79) | -0.015 / -0.080 / -0.018 | 2044 (362) | 62.4% vs 61.0% | +1.4 [-3.3, +8.6] | **-0.073 [-0.110, -0.035]** | -0.31 (-113) | -0.177 / -0.040 / -0.037 |
| last five days (efficiency ratio of H1 closes) | trending (over 0.125) | 1947 (380) | 61.9% vs 62.5% | -0.6 [-7.3, +6.7] | -0.042 [-0.091, +0.007] | -0.40 (-150) | -0.079 / -0.047 / +0.032 | 2345 (416) | 63.6% vs 57.6% | **+6.0 [+1.6, +9.6]** | **-0.052 [-0.076, -0.029]** | -0.29 (-120) | -0.111 / -0.027 / -0.024 |
| session (UTC) | Asia 22-07 | 1949 (380) | 64.7% vs 56.0% | **+8.7 [+4.2, +12.9]** | -0.001 [-0.035, +0.029] | -0.08 (-30) | +0.013 / -0.022 / +0.012 | 2036 (361) | 65.0% vs 57.4% | **+7.6 [+2.8, +12.6]** | **-0.036 [-0.070, -0.000]** | -0.23 (-85) | -0.140 / -0.009 / +0.013 |
| session (UTC) | London 07-12 | 926 (181) | 63.5% vs 58.9% | +4.6 [-1.4, +12.9] | -0.018 [-0.064, +0.031] | -0.08 (-15) | -0.013 / -0.034 / -0.003 | 1063 (188) | 65.3% vs 61.6% | +3.6 [-3.8, +12.1] | -0.034 [-0.081, +0.011] | -0.23 (-43) | -0.073 / +0.002 / -0.035 |
| session (UTC) | London + New York 12-16 | 1929 (376) | 63.3% vs 61.9% | +1.4 [-3.1, +6.7] | -0.019 [-0.048, +0.014] | -0.14 (-51) | -0.033 / -0.024 / +0.001 | 2029 (360) | 62.8% vs 58.0% | **+4.9 [+0.2, +10.5]** | **-0.070 [-0.100, -0.039]** | -0.34 (-123) | -0.122 / -0.037 / -0.062 |
| session (UTC) | New York 16-22 | 1454 (284) | 58.4% vs 61.9% | -3.5 [-13.0, +3.5] | **-0.098 [-0.152, -0.050]** | -0.65 (-185) | -0.121 / -0.108 / -0.041 | 1937 (343) | 62.5% vs 59.3% | +3.1 [-1.6, +8.5] | **-0.066 [-0.102, -0.035]** | -0.33 (-115) | -0.103 / -0.054 / -0.052 |
| volatility (H1 ATR vs its 20-day median) | low | 1663 (324) | 66.1% vs 53.8% | **+12.3 [+7.3, +16.6]** | +0.005 [-0.037, +0.040] | +0.01 (+2) | -0.010 / -0.016 / +0.053 | 1750 (310) | 64.0% vs 59.4% | **+4.6 [+0.6, +9.8]** | **-0.082 [-0.118, -0.041]** | -0.34 (-106) | -0.114 / -0.048 / -0.084 |
| volatility (H1 ATR vs its 20-day median) | normal | 3364 (656) | 62.5% vs 59.5% | +3.1 [-0.2, +6.8] | **-0.028 [-0.056, -0.002]** | -0.14 (-94) | -0.020 / -0.040 / -0.024 | 3586 (636) | 63.6% vs 58.5% | **+5.1 [+1.3, +8.8]** | **-0.052 [-0.077, -0.027]** | -0.30 (-188) | -0.136 / -0.026 / -0.013 |
| volatility (H1 ATR vs its 20-day median) | high | 1231 (240) | 58.2% vs 68.0% | -9.8 [-19.6, +3.4] | **-0.091 [-0.140, -0.032]** | -0.79 (-190) | -0.119 / -0.100 / -0.027 | 1729 (307) | 63.8% vs 58.4% | +5.3 [-1.4, +13.3] | -0.027 [-0.060, +0.004] | -0.23 (-72) | -0.063 / -0.017 / -0.014 |

By half-year, all levels (gold DEV and CONFIRM, then BTC):

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2025H2 | 1060 (207) | 62.5% vs 59.8% | +2.7 [-1.6, +7.2] | -0.016 [-0.079, +0.048] | -0.21 (-43) | -0.016 |
| 2026H1 | 1496 (292) | 64.0% vs 61.0% | +3.0 [-3.4, +9.6] | +0.002 [-0.042, +0.043] | +0.22 (+65) | +0.002 |
| 2026H2 | 1078 (210) | 63.9% vs 61.5% | +2.4 [-5.1, +10.3] | +0.003 [-0.050, +0.059] | +0.15 (+32) | +0.003 |

|  | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2024H1 | 1032 (183) | 63.5% vs 59.8% | +3.7 [-1.6, +10.3] | -0.031 [-0.084, +0.020] | -0.07 (-13) | -0.031 |
| 2024H2 | 1164 (206) | 63.0% vs 57.9% | **+5.1 [+0.9, +10.3]** | -0.025 [-0.079, +0.035] | -0.05 (-10) | -0.025 |
| 2025H1 | 1200 (213) | 65.5% vs 64.5% | +1.0 [-3.4, +5.6] | +0.021 [-0.014, +0.054] | +0.34 (+73) | +0.021 |

|  | DEV: trades (per quarter) | DEV: target first: levels vs control | DEV: difference, points (95 %) | DEV: ATR per trade (95 %) | DEV: USD per trade (per quarter) | DEV: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2025H2 | 2128 (415) | 62.2% vs 63.3% | -1.1 [-9.0, +5.6] | -0.040 [-0.089, +0.005] | -0.31 (-130) | -0.040 |
| 2026H1 | 2376 (464) | 62.0% vs 58.1% | +3.9 [-1.0, +8.5] | **-0.045 [-0.078, -0.013]** | -0.29 (-136) | -0.045 |
| 2026H2 | 1754 (342) | 64.1% vs 57.2% | **+6.8 [+2.3, +11.1]** | -0.004 [-0.035, +0.024] | -0.05 (-16) | -0.004 |

|  | CONFIRM: trades (per quarter) | CONFIRM: target first: levels vs control | CONFIRM: difference, points (95 %) | CONFIRM: ATR per trade (95 %) | CONFIRM: USD per trade (per quarter) | CONFIRM: ATR per trade by half-year |
|---|---|---|---|---|---|---|
| 2024H1 | 1907 (338) | 63.3% vs 57.3% | **+6.0 [+2.3, +9.8]** | **-0.114 [-0.142, -0.087]** | -0.61 (-205) | -0.114 |
| 2024H2 | 2565 (455) | 64.4% vs 59.0% | **+5.3 [+0.7, +10.9]** | **-0.028 [-0.056, -0.003]** | -0.13 (-58) | -0.028 |
| 2025H1 | 2593 (460) | 63.4% vs 59.5% | +3.9 [-0.6, +9.2] | **-0.034 [-0.061, -0.005]** | -0.22 (-102) | -0.034 |
