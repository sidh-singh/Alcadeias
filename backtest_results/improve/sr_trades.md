# Support and resistance as a trading rule

**The question.** Do higher-timeframe support and resistance levels - swing highs and lows of H1,
H4 and D1, the previous day's and the previous week's high and low - make money on XAUUSDm and
BTCUSDm when they are traded the way a chartist trades them? And if a rule makes money, is the
level what makes it?

**How it was answered.** Levels are found with no hindsight (a swing counts only once the bars to
its right have closed). Eight rules - bounce with, against and regardless of the trend, break and
retest, breakout, range fade - plus the confirmations a chartist would add are simulated on M1 bars,
stop and target sized in ATR, the spread paid on every trade. Every rule is then run again on 30
sets of **placebo levels**: the same levels moved 1 to 3 ATR, to prices where there is no level.
Everything was chosen on August 2025 - November 2026 (DEV) and then run once, unchanged, on
February 2024 - June 2025 (CONFIRM).

R is the unit used throughout: 1 R is what a trade loses when its stop is hit. Per 0.01 lot a
bounce risks about $13 on gold and $3 on BTC in DEV, $5 and $4 in CONFIRM.

## The short version

1. **Buying support and selling resistance loses money** - on both symbols, in both periods.
   Per trade, after the spread: gold −0.12 R (DEV, 752 trades) and −0.15 R (CONFIRM, 830); BTC
   −0.19 R (1,202) and −0.15 R (1,036). Per 0.01 lot that is −$229 and −$109 a quarter on gold,
   −$136 and −$79 on BTC. It is negative in 11 of the 12 symbol half-years and +0.01 R in the twelfth.
2. **Trading with the trend does not rescue it, and no confirmation does.** With the H4 trend:
   gold −0.06 and −0.12 R, BTC −0.18 and −0.11 R. RSI below 35 / above 65, RSI divergence, a
   reversal bar, a zone several timeframes agree on, an untouched level, a level that held before:
   none is positive in both periods on either symbol. Bounces at D1 and weekly levels, the ones
   the eye trusts most, are no better (gold −0.26 and −0.29 R, BTC −0.09 and −0.26 R).
3. **The level adds nothing to a bounce.** The same rule at placebo prices does as well or better:
   real minus placebo is −0.08 ± 0.05 R and −0.04 ± 0.04 R on gold, −0.13 ± 0.04 R and −0.02 ± 0.04 R
   on BTC. It is never above zero; in DEV all 30 placebo sets beat the real levels on both symbols.
4. **Why it looks as if levels work.** With a small target (a quarter of the stop distance) a
   bounce "works" 73 - 75 % of the time at a real level - and 74 - 78 % of the time at a placebo
   price. Price bounces a little almost everywhere; a level is not special.
5. **Breakouts are the only rules that are not negative, and none passed the test.** The one
   candidate picked on DEV, the BTC breakout (+0.09 R), lost on CONFIRM (−0.06 R). One rule is
   positive in both periods without having been the candidate: on gold, a breakout in the direction
   of the H4 trend made +0.13 ± 0.10 R (+$93 a quarter per 0.01 lot) and +0.23 ± 0.10 R (+$79), and
   was positive in 5 of 6 half-years. It is a lead, not an edge: it was not the rule named in
   advance, nearly all of its profit is buys in a market that rose in both periods, and in DEV
   the same rule at placebo prices made the same.
6. **For the bot:** support / resistance should not be coded as an entry at the level, as a ladder
   trigger or as a target. The gold breakout-with-trend rule is written out below so that it can be
   given one clean test on data that has not been touched (2023) before anything is built on it.

## What was tested

Everything below was decided on the newer history (DEV, 1 July 2025 to 12 November 2026) and written
down before the older history (CONFIRM, 1 January 2024 to 30 June 2025) was read.

### The levels

Prices are bid prices and times are UTC, as on the Exness MT5 chart. "ATR" is always the 14-bar
average true range of the H1 chart at its last closed bar, so every distance means the same thing
on gold and on BTC, in quiet and in wild months.

| Level | What it is | Known from | Kept until |
|---|---|---|---|
| H1 swing high / low | an H1 bar whose high is above the highs of the 5 bars before it and not below the highs of the 5 bars after it (mirror for a low) | the close of the 5th bar after it | 5 days later |
| H4 swing high / low | the same on H4 with 3 bars on each side | the close of the 3rd bar after it | 20 days later |
| D1 swing high / low | the same on D1 with 2 days on each side | the close of the 2nd day after it | 90 days later |
| Previous day's high / low | high and low of the last finished UTC day; a day with under six hours of quotes (gold's Sunday evening) is counted with the next day | the end of that day | the end of the next day |
| Previous week's high / low | high and low of the last finished week, Sunday 00:00 to Sunday 00:00 | the end of that week | the end of the next week |

A level that appears within 0.15 ATR of one that is still on the chart joins it: the two are one
**zone**, which stays at the price of its first level and remembers which of the five sources it
holds. That count is the "number of timeframes agreeing". The zone that is traded is the level
± 0.15 ATR.

### What happens at a zone

- A zone is **support** while price is above it and **resistance** while price is below it.
- It is **armed** once an M1 bar has closed at least 1 ATR away from it. Only an armed zone can be
  touched, so a touch is a real return to the level and not a wiggle around it.
- **Touch**: the low of an M1 bar reaches the top of an armed support zone (the high reaches the
  bottom of an armed resistance zone).
- **Reversal bar**: an M15 bar reaches the zone and closes back beyond the level in the bounce
  direction and beyond its own open.
- **Break**: an H1 bar closes beyond the far edge of the zone. The zone changes role (broken
  resistance becomes support). A second break retires it; a later swing at the same price starts it afresh.

### The trade

The same for every rule, so that rules differ only in when they enter:

| | |
|---|---|
| Entry | at the close of the M1 bar of the event: a buy at the ask (bid + the bar's mean spread), a sell at the bid |
| Stop | 0.5 ATR beyond the level on the losing side (0.15 ATR of zone + 0.35 ATR) |
| Risk (1R) | the distance from entry to stop, spread included; about 0.65 ATR on a typical bounce and 0.95 ATR on a typical breakout |
| Target | 2 × the risk |
| Time stop | 24 hours |
| Inside a bar | the stop is checked before the target, so a bar that reaches both is a loss; a gap through the stop is filled at the open; a target is never filled better than its price; a short is closed on the ask |
| Not taken | spread above 0.10 ATR; a stop nearer than 0.1 or farther than 1.5 ATR; a bounce whose M1 bar has already closed beyond the far edge of the zone |
| Positions | one at a time per rule; a signal that arrives while a trade is open is skipped |
| Costs | the recorded spread on every round trip; no commission and no swap, as in the backtester |

### The rules

| | Rule | Enters when | Direction |
|---|---|---|---|
| a | Bounce with the trend | touch of a zone that has not been broken, and the bounce points with the trend | buy support in an uptrend, sell resistance in a downtrend |
| b1 | Bounce against the trend | the same touch, bounce against the trend | buy support in a downtrend, sell resistance in an uptrend |
| b2 | Bounce, any trend | every such touch | buy support, sell resistance |
| c | Break and retest | the first touch of a zone after its break, from the new side | with the break |
| c+ | Break and retest, with the trend | the same, only with the trend | with the break |
| d | Breakout | an H1 bar closes beyond a zone that had not been broken | with the break |
| d+ | Breakout, with the trend | the same, only with the trend | with the break |
| e | Range fade | touch of an unbroken zone while the H4 chart is flat | buy support, sell resistance |

- **Trend** = the sign of the H4 MACD (12, 26, 9) signal line at the last closed H4 bar: the
  backtester's `trend_tf=H4`. **Flat** = H4 ADX(14) below 20.
- **Confirmations**, each added to rule a and to rule b2: M15 RSI(14) below 35 for a buy / above
  65 for a sell at the touch (the forming M15 bar valued at the touch price); RSI divergence (price
  lower than the previous M15 swing low while the RSI low is at least 2 points higher; mirror for
  highs; M15 swings with 3 bars each side, the previous swing no older than 12 hours); the M15
  reversal bar as the trigger instead of the first touch; a zone holding 2 or more sources; a level
  never touched before; a level touched before.
- **Timeframe of the level**, for rules b2 and d: zones holding only H1 swings / previous-day
  levels, zones holding an H4 swing, zones holding a D1 swing or a weekly level.

That is 26 rules.

### Placebo levels

The control that decides the question. Every zone is moved to a price that is not a level: up or
down (a coin flip) by a random 1 to 3 ATR, redrawn until it lies at least 0.5 ATR from every real
zone that is live at that moment. Its time of birth, lifetime and sources stay the same, and the
same code then runs the same rules, trend filter, stop and target on it. Thirty such sets (seeds 1
to 30). A second version, the "plain placebo", is the shift alone with no draw rejected. Two readings:

- **real − placebo**: expectancy of the real trades minus that of all placebo trades, with a
  standard error and a 95 % interval from resampling whole weeks (the same weeks for both, so the
  market they share cancels out);
- **placebo sets at least as good**: how many of the 30 sets did as well as the real levels. If
  levels meant nothing, the real set would land anywhere among them; 0 or 1 of 30 says the real
  levels are better than chance, 29 or 30 of 30 says they are worse.

### Periods and statistics

| Period | History | Entries taken | Used for |
|---|---|---|---|
| DEV | 1 Jul 2025 – 12 Nov 2026 | 1 Aug 2025 – 12 Nov 2026 | choosing every definition and parameter |
| CONFIRM | 1 Jan 2024 – 30 Jun 2025 | 1 Feb 2024 – 30 Jun 2025 | one run of the unchanged code |

The first 31 days of each period only warm up the indicators and the level book. Nothing before
1 January 2024 was read.

Results are in **R** (multiples of the risk of each trade; the only unit that is the same on both
symbols and in both periods) and in **USD per 0.01 lot**. "± SE" is a standard error from resampling
whole weeks. A rule counts as having an edge only if it is positive after the spread in both
periods, in most half-years, and better than its placebo; with a 2R target and no edge a rule wins
one trade in three and loses the spread.

**How much was tried.** On DEV: the 26 rules under 11 parameter sets (the one above and ten
one-at-a-time changes to target, stop, zone width, holding time, trend definition, swing size and
arming distance), on 2 symbols: 572 rule results, each with its 30 placebo sets; and the base set
against two other ways of drawing the placebo prices. Nothing was grid-searched and the parameter
set above was written down before any result was seen. On CONFIRM, once: the 26 rules under the
parameter set above, the same against the plain placebo, and the quarter-size target for one table.
One more set was run on DEV after CONFIRM, as a check and not as a candidate: entering on the touch
itself instead of at the close of the M1 bar.

## What DEV showed, and what was fixed before the older history was read

On DEV (entries 1 August 2025 to 12 November 2026), with the definitions above:

- **Bounces lose.** Buying support and selling resistance loses after the spread on both symbols -
  with the trend, against it and regardless of it - in every one of the 11 parameter sets tried
  (rule b2: gold −0.12 R per trade over 752 trades, BTC −0.19 R over 1,202). No confirmation changes
  that: the only cell above zero is gold's divergence filter on rule a, +0.08 ± 0.29 R on 25 trades.
  The range fade (e) is −0.03 ± 0.11 R on gold and −0.27 ± 0.07 R on BTC.
- **A bounce at a real level does worse than a bounce at a placebo level.** Real minus placebo for
  rule b2: gold −0.08 ± 0.05 R, BTC −0.13 ± 0.04 R; on both symbols all 30 placebo sets did at
  least as well as the real levels.
- **Breakouts are the only rule above zero on both symbols**, by little: rule d gold +0.03 ± 0.07 R,
  BTC +0.09 ± 0.06 R. On BTC it is positive in all three half-years and better than all 30 placebo
  sets (real minus placebo +0.13 ± 0.05 R). On gold it equals its placebo and all of the gain is one half-year.

**Candidate chosen on DEV:** rule d, the breakout on the H1 close, on BTC. Gold has no candidate.

**What CONFIRM should show if the DEV picture is real, written before CONFIRM was read:**

1. the bounce rules (a, b1, b2, e) lose after the spread on both symbols and no confirmation turns them positive;
2. a bounce at a real level does no better than a bounce at a placebo level, on both symbols;
3. on BTC the breakout (d) is positive after the spread and better than its placebo;
4. on gold no rule is positive in both periods.

**What is run on CONFIRM, once:** the 26 rules with the base parameter set and 30 placebo sets
(seeds 1 to 30); the same with the plain placebo (the shift alone, no draw rejected), as a check on the
control; and the quarter-target set, for the bounce-frequency table only. Nothing else, and nothing re-tuned.

## Results

### What was run

| Symbol | Period | Entries taken | M1 bars read | Mean H1 ATR, $ per 0.01 lot | Median spread, $ | Levels: H1 swing / H4 swing / D1 swing / previous day / previous week | Zones | Zones live on average | ... of them within 3 ATR of price | Time price spends inside a zone: real / placebo | Events: touch / reversal bar / break |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSDm | DEV | 2025-08-01 .. 2026-11-12 | 486,535 | 19.67 | 0.24 | 1027 / 420 / 89 / 710 / 144 | 827 | 17.1 | 3.2 | 11% / 13% | 1918 / 1167 / 1348 |
| XAUUSDm | CONFIRM | 2024-02-01 .. 2025-06-30 | 525,921 | 7.60 | 0.16 | 1091 / 490 / 99 / 772 / 158 | 883 | 16.6 | 3.1 | 10% / 13% | 2137 / 1276 / 1445 |
| BTCUSDm | DEV | 2025-08-01 .. 2026-11-12 | 714,976 | 5.10 | 0.14 | 1502 / 607 / 137 / 994 / 144 | 1043 | 20.7 | 3.6 | 12% / 14% | 3322 / 2134 / 2086 |
| BTCUSDm | CONFIRM | 2024-02-01 .. 2025-06-30 | 782,269 | 5.86 | 0.29 | 1645 / 661 / 148 / 1092 / 158 | 1142 | 19.3 | 3.6 | 11% / 13% | 3556 / 2292 / 2298 |

Two things to read off this table: zones are sparse (about three within 3 ATR of price, price
inside one about a tenth of the time), so "at a level" and "not at a level" are different places;
and the placebo zones are touched about as often as the real ones.

### 1. Every rule, both periods

"Real − placebo" is the expectancy of the rule at the real levels minus the same rule at the
placebo levels. "Placebo sets at least as good" counts how many of the 30 placebo sets matched or
beat the real levels: near 15 means the levels made no difference, near 0 that they helped, near
30 that they hurt.

**Both symbols together** (R is the only unit the two share):

| Rule | DEV: trades | R ± SE | real − placebo, R ± SE | CONFIRM: trades | R ± SE | real − placebo, R ± SE |
|---|---|---|---|---|---|---|
| a: Bounce with the trend | 894 | −0.13 ± 0.04 | −0.08 ± 0.04 | 886 | −0.12 ± 0.04 | −0.01 ± 0.04 |
| b1: Bounce against the trend | 1087 | −0.18 ± 0.04 | −0.12 ± 0.04 | 1000 | −0.18 ± 0.04 | −0.06 ± 0.04 |
| b2: Bounce, any trend | 1954 | −0.17 ± 0.03 | −0.11 ± 0.03 | 1866 | −0.15 ± 0.03 | −0.03 ± 0.03 |
| c: Break and retest | 869 | −0.04 ± 0.05 | −0.02 ± 0.05 | 835 | +0.02 ± 0.05 | +0.02 ± 0.05 |
| c+: Break and retest, with the trend | 542 | −0.06 ± 0.06 | −0.06 ± 0.06 | 533 | +0.02 ± 0.06 | +0.02 ± 0.06 |
| d: Breakout on the H1 close | 911 | +0.06 ± 0.05 | +0.07 ± 0.04 | 882 | +0.01 ± 0.04 | +0.02 ± 0.04 |
| d+: Breakout on the H1 close, with the trend | 529 | +0.08 ± 0.06 | +0.02 ± 0.06 | 482 | +0.11 ± 0.06 | +0.08 ± 0.05 |
| e: Range fade (H4 flat) | 589 | −0.17 ± 0.06 | −0.09 ± 0.06 | 641 | −0.12 ± 0.05 | −0.02 ± 0.05 |

**Gold:**

| Rule | DEV: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good | CONFIRM: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 349 | −0.06 ± 0.07 | −1.74 | −118 | −0.04 ± 0.07 | 22 of 30 | 389 | −0.12 ± 0.07 | −0.91 | −63 | −0.06 ± 0.06 | 26 of 30 |
| b1: Bounce against the trend | 416 | −0.16 ± 0.06 | −1.23 | −99 | −0.08 ± 0.07 | 28 of 30 | 448 | −0.17 ± 0.06 | −0.66 | −52 | −0.02 ± 0.05 | 20 of 30 |
| b2: Bounce, any trend | 752 | −0.12 ± 0.05 | −1.56 | −229 | −0.08 ± 0.05 | 30 of 30 | 830 | −0.15 ± 0.04 | −0.75 | −109 | −0.04 ± 0.04 | 26 of 30 |
| c: Break and retest | 338 | −0.01 ± 0.07 | −0.30 | −20 | −0.03 ± 0.07 | 17 of 30 | 376 | +0.08 ± 0.07 | +0.51 | +34 | +0.07 ± 0.07 | 4 of 30 |
| c+: Break and retest, with the trend | 213 | +0.05 ± 0.09 | +0.92 | +38 | −0.01 ± 0.10 | 14 of 30 | 244 | +0.14 ± 0.09 | +0.68 | +29 | +0.12 ± 0.10 | 0 of 30 |
| d: Breakout on the H1 close | 378 | +0.03 ± 0.07 | +0.01 | +1 | −0.01 ± 0.07 | 18 of 30 | 412 | +0.08 ± 0.07 | +0.95 | +69 | +0.05 ± 0.06 | 7 of 30 |
| d+: Breakout on the H1 close, with the trend | 225 | +0.13 ± 0.10 | +2.12 | +93 | +0.00 ± 0.10 | 15 of 30 | 230 | +0.23 ± 0.10 | +1.94 | +79 | +0.16 ± 0.08 | 0 of 30 |
| e: Range fade (H4 flat) | 233 | −0.03 ± 0.11 | −0.59 | −27 | +0.03 ± 0.12 | 10 of 30 | 318 | −0.08 ± 0.08 | −0.31 | −18 | −0.00 ± 0.07 | 14 of 30 |

**BTC:**

| Rule | DEV: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good | CONFIRM: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 545 | −0.18 ± 0.05 | −0.56 | −59 | −0.11 ± 0.05 | 29 of 30 | 497 | −0.11 ± 0.05 | −0.36 | −31 | +0.04 ± 0.06 | 5 of 30 |
| b1: Bounce against the trend | 671 | −0.20 ± 0.06 | −0.58 | −75 | −0.15 ± 0.05 | 30 of 30 | 552 | −0.19 ± 0.06 | −0.55 | −53 | −0.08 ± 0.06 | 28 of 30 |
| b2: Bounce, any trend | 1202 | −0.19 ± 0.04 | −0.58 | −136 | −0.13 ± 0.04 | 30 of 30 | 1036 | −0.15 ± 0.04 | −0.43 | −79 | −0.02 ± 0.04 | 20 of 30 |
| c: Break and retest | 531 | −0.05 ± 0.06 | −0.27 | −28 | −0.02 ± 0.06 | 19 of 30 | 459 | −0.03 ± 0.06 | −0.23 | −18 | −0.02 ± 0.06 | 21 of 30 |
| c+: Break and retest, with the trend | 329 | −0.13 ± 0.08 | −0.44 | −28 | −0.10 ± 0.08 | 29 of 30 | 289 | −0.08 ± 0.07 | −0.54 | −28 | −0.07 ± 0.07 | 27 of 30 |
| d: Breakout on the H1 close | 533 | +0.09 ± 0.06 | +0.55 | +57 | +0.13 ± 0.05 | 0 of 30 | 470 | −0.06 ± 0.06 | −0.79 | −65 | +0.00 ± 0.05 | 14 of 30 |
| d+: Breakout on the H1 close, with the trend | 304 | +0.04 ± 0.08 | +0.23 | +14 | +0.04 ± 0.07 | 6 of 30 | 252 | −0.00 ± 0.08 | −0.53 | −24 | +0.01 ± 0.07 | 12 of 30 |
| e: Range fade (H4 flat) | 356 | −0.27 ± 0.07 | −0.83 | −57 | −0.16 ± 0.07 | 30 of 30 | 323 | −0.16 ± 0.07 | −0.20 | −12 | −0.03 ± 0.07 | 19 of 30 |

How the four expectations written down before CONFIRM came out:

| | Expectation | CONFIRM | |
|---|---|---|---|
| 1 | bounces (a, b1, b2, e) lose after the spread on both symbols; no confirmation turns them positive | gold −0.12, −0.17, −0.15, −0.08 R; BTC −0.11, −0.19, −0.15, −0.16 R; the only confirmation cell above zero is BTC's divergence filter on rule a, +0.15 ± 0.19 R on 52 trades (it was −0.09 R in DEV) | held |
| 2 | a bounce at a real level does no better than at a placebo level | rule b2: gold −0.04 ± 0.04 R, BTC −0.02 ± 0.04 R | held, though the gap is smaller than in DEV |
| 3 | on BTC the breakout (d) is positive and better than its placebo | −0.06 ± 0.06 R, −$65 a quarter; real − placebo 0.00 ± 0.05 R | **failed** |
| 4 | on gold no rule is positive in both periods | d, d+ and c+ are | **failed** - see section 3 |

### 2. Half-year by half-year

R per trade, with the number of trades in brackets. 2024H1 to 2025H1 are CONFIRM, 2025H2 to
2026H2 are DEV. 2024H1 and 2025H2 hold five months of entries (the first month of each period is
warm-up) and 2026H2 four and a half.

**Gold:**

| Rule | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | 2026H2 |
|---|---|---|---|---|---|---|
| a: Bounce with the trend | −0.13 (109) | −0.04 (129) | −0.19 (151) | −0.13 (88) | −0.16 (130) | +0.10 (131) |
| b1: Bounce against the trend | −0.26 (133) | −0.11 (168) | −0.17 (147) | −0.19 (142) | −0.18 (148) | −0.09 (126) |
| b2: Bounce, any trend | −0.20 (240) | −0.08 (295) | −0.17 (295) | −0.17 (228) | −0.18 (272) | −0.01 (252) |
| c: Break and retest | +0.03 (107) | +0.25 (131) | −0.04 (138) | +0.01 (96) | −0.10 (135) | +0.08 (107) |
| c+: Break and retest, with the trend | −0.04 (75) | +0.44 (76) | +0.03 (93) | −0.07 (66) | −0.03 (87) | +0.32 (60) |
| d: Breakout on the H1 close | +0.11 (117) | +0.11 (142) | +0.03 (153) | −0.06 (129) | +0.19 (135) | −0.05 (114) |
| d+: Breakout on the H1 close, with the trend | +0.10 (68) | +0.34 (78) | +0.24 (84) | −0.00 (90) | +0.33 (76) | +0.05 (59) |
| e: Range fade (H4 flat) | −0.14 (109) | −0.09 (95) | −0.00 (114) | −0.30 (63) | −0.11 (84) | +0.25 (86) |

**BTC:**

| Rule | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | 2026H2 |
|---|---|---|---|---|---|---|
| a: Bounce with the trend | +0.15 (54) | −0.21 (212) | −0.08 (231) | −0.16 (169) | −0.17 (196) | −0.22 (180) |
| b1: Bounce against the trend | −0.14 (74) | −0.25 (241) | −0.13 (237) | −0.26 (226) | −0.24 (250) | −0.08 (195) |
| b2: Bounce, any trend | +0.01 (125) | −0.23 (450) | −0.10 (461) | −0.22 (389) | −0.21 (442) | −0.14 (371) |
| c: Break and retest | −0.20 (56) | −0.05 (198) | +0.02 (205) | +0.02 (166) | −0.17 (208) | +0.02 (157) |
| c+: Break and retest, with the trend | −0.08 (36) | −0.18 (125) | +0.03 (128) | +0.07 (102) | −0.27 (136) | −0.16 (91) |
| d: Breakout on the H1 close | −0.10 (66) | −0.06 (205) | −0.04 (199) | +0.01 (177) | +0.11 (205) | +0.14 (151) |
| d+: Breakout on the H1 close, with the trend | +0.04 (44) | −0.08 (110) | +0.07 (98) | +0.07 (104) | +0.07 (121) | −0.05 (79) |
| e: Range fade (H4 flat) | +0.27 (26) | −0.20 (122) | −0.19 (175) | −0.36 (122) | −0.36 (137) | −0.02 (97) |

BTC's first half of 2024 holds few trades: its spread was then about a tenth of the H1 ATR, four
times today's, and the rule "no entry when the spread is above 0.10 ATR" refused 414 of its 608
touches. The same refusals apply to the placebo levels.

**Real minus placebo, the same way** (R per trade at real levels minus R per trade at placebo
levels; real trades in brackets). Gold:

| Rule | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | 2026H2 |
|---|---|---|---|---|---|---|
| a: Bounce with the trend | −0.06 (109) | −0.03 (129) | −0.07 (151) | −0.30 (88) | −0.08 (130) | +0.21 (131) |
| b1: Bounce against the trend | −0.10 (133) | +0.01 (168) | +0.01 (147) | −0.14 (142) | −0.08 (148) | −0.02 (126) |
| b2: Bounce, any trend | −0.08 (240) | −0.02 (295) | −0.02 (295) | −0.21 (228) | −0.10 (272) | +0.08 (252) |
| c: Break and retest | +0.10 (107) | +0.20 (131) | −0.07 (138) | −0.06 (96) | −0.10 (135) | +0.09 (107) |
| c+: Break and retest, with the trend | −0.01 (75) | +0.34 (76) | +0.05 (93) | −0.21 (66) | −0.09 (87) | +0.32 (60) |
| d: Breakout on the H1 close | +0.12 (117) | +0.09 (142) | −0.05 (153) | −0.11 (129) | +0.15 (135) | −0.07 (114) |
| d+: Breakout on the H1 close, with the trend | +0.10 (68) | +0.23 (78) | +0.16 (84) | −0.24 (90) | +0.24 (76) | +0.02 (59) |
| e: Range fade (H4 flat) | −0.06 (109) | −0.13 (95) | +0.17 (114) | −0.43 (63) | +0.03 (84) | +0.38 (86) |

BTC:

| Rule | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | 2026H2 |
|---|---|---|---|---|---|---|
| a: Bounce with the trend | +0.15 (54) | −0.07 (212) | +0.11 (231) | −0.11 (169) | −0.09 (196) | −0.12 (180) |
| b1: Bounce against the trend | −0.07 (74) | −0.11 (241) | −0.06 (237) | −0.13 (226) | −0.18 (250) | −0.12 (195) |
| b2: Bounce, any trend | +0.05 (125) | −0.08 (450) | +0.02 (461) | −0.13 (389) | −0.14 (442) | −0.11 (371) |
| c: Break and retest | −0.19 (56) | −0.06 (198) | +0.05 (205) | +0.15 (166) | −0.18 (208) | +0.03 (157) |
| c+: Break and retest, with the trend | −0.19 (36) | −0.21 (125) | +0.10 (128) | +0.15 (102) | −0.29 (136) | −0.08 (91) |
| d: Breakout on the H1 close | −0.02 (66) | −0.03 (205) | +0.04 (199) | +0.14 (177) | +0.10 (205) | +0.15 (151) |
| d+: Breakout on the H1 close, with the trend | −0.04 (44) | −0.09 (110) | +0.14 (98) | +0.05 (104) | +0.04 (121) | +0.02 (79) |
| e: Range fade (H4 flat) | +0.41 (26) | −0.09 (122) | −0.05 (175) | −0.23 (122) | −0.26 (137) | +0.07 (97) |

The bounce (b2) is below its placebo in 9 of the 12 symbol half-years. Nothing in the breakout
rows holds its sign through all six half-years on either symbol.

### 3. The rules that are not negative

**BTC breakout (d), the candidate.** In DEV it looked convincing: +0.09 ± 0.06 R, positive in all
three half-years and in 10 of the 11 parameter sets, better than every one of the 30 placebo sets
(real − placebo +0.13 ± 0.05 R). On CONFIRM it made −0.06 ± 0.06 R (−$0.79 a trade) and exactly
matched its placebo. It did not survive, and it is the measure of how good a rule can look on
fifteen months and still be nothing.

**Gold breakout with the H4 trend (d+).** Positive in both periods:

| | DEV | CONFIRM | Both |
|---|---|---|---|
| Trades | 225 | 230 | 455 (42 a quarter) |
| R per trade | +0.13 ± 0.10 | +0.23 ± 0.10 | +0.18 ± 0.07 |
| $ per trade, 0.01 lot | +2.12 | +1.94 | |
| $ per quarter | +93 | +79 | +85 |
| Win rate | 38 % | 42 % | |
| Worst losing run | 17 trades, −$121 | 8 trades, −$61 | |
| Half-years above zero | 2 of 3 (the third −0.00) | 3 of 3 | 5 of 6 |
| Buys: trades, R | 133, +0.18 | 164, +0.33 | |
| Sells: trades, R | 92, +0.04 | 66, +0.00 | |
| Same rule at placebo levels, R | +0.12 | +0.07 | |
| Real − placebo, R | +0.00 ± 0.10 | +0.16 ± 0.08 | |
| Placebo sets at least as good | 15 of 30 | 0 of 30 | |

Why this is a lead and not a result:

- It was not the rule named before CONFIRM was read. It is the best of the 52 rule-and-symbol
  cells looked at after both periods were known: 39 of them are negative in both periods, 8 are
  mixed and 5 are positive in both (gold c+, d, d+; breakouts of D1 / weekly levels on both
  symbols, on 64 to 74 trades each). With no edge anywhere, about three of the 14 cells that are
  not bounces would be positive in both periods by chance.
- Nearly all of the profit is buys, and gold rose in both periods. A rule that buys new highs in a
  rising market makes money without any level.
- In DEV the level contributed nothing: an H1 close through a placebo price, with the trend, made
  +0.12 R against +0.13 R at the real levels. In CONFIRM the real levels were better than all 30
  placebo sets. One period each way is not evidence that the level matters.
- Without the trend filter the gold breakout (d) is +0.03 and +0.08 R: the trend filter is doing
  the work, which is what the earlier improvement search found for the bot's own entries.

**Break and retest with the trend on gold (c+)** is +0.05 ± 0.09 and +0.14 ± 0.09 R; two of its six
half-years carry it (+0.44 and +0.32) and the other four are near zero. On BTC it is −0.13 and −0.08 R.

### 4. Why it can look as if levels work

Rule b2 with three sizes of target. "Won by a coin-flip market" is the win rate a market with no
memory and no costs would give for that target.

| Target | Symbol | Period | Trades at real levels | Won at real levels | Won at placebo levels | Won by a coin-flip market | R at real levels | R at placebo levels |
|---|---|---|---|---|---|---|---|---|
| 0.25 × the risk | XAUUSDm | DEV | 919 | 75% | 78% | 80% | −0.07 | −0.03 |
| 0.25 × the risk | XAUUSDm | CONFIRM | 1015 | 73% | 76% | 80% | −0.09 | −0.05 |
| 0.25 × the risk | BTCUSDm | DEV | 1524 | 73% | 76% | 80% | −0.09 | −0.05 |
| 0.25 × the risk | BTCUSDm | CONFIRM | 1315 | 73% | 74% | 80% | −0.08 | −0.08 |
| 1 × the risk | XAUUSDm | DEV | 860 | 45% | 48% | 50% | −0.11 | −0.04 |
| 1 × the risk | BTCUSDm | DEV | 1404 | 44% | 47% | 50% | −0.11 | −0.05 |
| 2 × the risk | XAUUSDm | DEV | 752 | 30% | 32% | 33% | −0.12 | −0.05 |
| 2 × the risk | XAUUSDm | CONFIRM | 830 | 29% | 30% | 33% | −0.15 | −0.11 |
| 2 × the risk | BTCUSDm | DEV | 1202 | 27% | 31% | 33% | −0.19 | −0.07 |
| 2 × the risk | BTCUSDm | CONFIRM | 1036 | 29% | 29% | 33% | −0.15 | −0.12 |

With a quarter-size target three bounces in four "work". They work just as often - a little more
often - at prices that are not levels, and the one in four that fails costs four winners, so the
rule still loses. Seeing price turn at a level most of the time is real; it says nothing about the level.

### 5. Confirmations

Each confirmation is added to rule a (with the trend) and to rule b2 (any trend) and run as a rule
of its own.

**Gold:**

| Rule | DEV: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good | CONFIRM: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 349 | −0.06 ± 0.07 | −1.74 | −118 | −0.04 ± 0.07 | 22 of 30 | 389 | −0.12 ± 0.07 | −0.91 | −63 | −0.06 ± 0.06 | 26 of 30 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 258 | −0.03 ± 0.08 | −1.32 | −66 | −0.04 ± 0.09 | 18 of 30 | 274 | −0.16 ± 0.08 | −1.36 | −66 | −0.13 ± 0.08 | 30 of 30 |
| a.div: Bounce with the trend + RSI divergence | 25 | +0.08 ± 0.29 | −1.69 | −8 | −0.11 ± 0.32 | 22 of 30 | 32 | −0.11 ± 0.25 | −1.19 | −7 | −0.14 ± 0.25 | 18 of 30 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 157 | −0.14 ± 0.11 | −3.47 | −106 | −0.15 ± 0.11 | 29 of 30 | 190 | −0.12 ± 0.10 | −0.86 | −29 | −0.05 ± 0.10 | 20 of 30 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 182 | −0.09 ± 0.11 | −1.88 | −67 | −0.07 ± 0.11 | 22 of 30 | 206 | −0.09 ± 0.10 | −0.81 | −30 | −0.05 ± 0.10 | 20 of 30 |
| a.fresh: Bounce with the trend + first touch of the level | 261 | −0.02 ± 0.08 | −1.36 | −69 | −0.04 ± 0.08 | 19 of 30 | 298 | −0.14 ± 0.08 | −1.29 | −68 | −0.09 ± 0.08 | 26 of 30 |
| a.tested: Bounce with the trend + level touched before | 138 | −0.17 ± 0.11 | −3.68 | −99 | −0.07 ± 0.10 | 24 of 30 | 159 | −0.09 ± 0.10 | −0.41 | −12 | −0.02 ± 0.09 | 14 of 30 |
| b2: Bounce, any trend | 752 | −0.12 ± 0.05 | −1.56 | −229 | −0.08 ± 0.05 | 30 of 30 | 830 | −0.15 ± 0.04 | −0.75 | −109 | −0.04 ± 0.04 | 26 of 30 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 541 | −0.09 ± 0.05 | −1.13 | −120 | −0.04 ± 0.06 | 24 of 30 | 574 | −0.14 ± 0.05 | −0.89 | −90 | −0.04 ± 0.05 | 22 of 30 |
| b2.div: Bounce, any trend + RSI divergence | 49 | −0.06 ± 0.17 | +0.42 | +4 | −0.02 ± 0.19 | 17 of 30 | 72 | −0.02 ± 0.17 | −0.32 | −4 | +0.12 ± 0.17 | 9 of 30 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 326 | −0.13 ± 0.07 | −2.21 | −140 | −0.04 ± 0.08 | 21 of 30 | 389 | −0.10 ± 0.07 | −0.49 | −33 | +0.02 ± 0.07 | 9 of 30 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 435 | −0.16 ± 0.07 | −2.22 | −188 | −0.11 ± 0.07 | 29 of 30 | 497 | −0.12 ± 0.06 | −0.70 | −62 | +0.01 ± 0.06 | 12 of 30 |
| b2.fresh: Bounce, any trend + first touch of the level | 554 | −0.10 ± 0.06 | −1.22 | −131 | −0.07 ± 0.07 | 27 of 30 | 614 | −0.11 ± 0.05 | −0.74 | −80 | −0.01 ± 0.05 | 18 of 30 |
| b2.tested: Bounce, any trend + level touched before | 308 | −0.19 ± 0.07 | −2.98 | −179 | −0.09 ± 0.08 | 26 of 30 | 345 | −0.20 ± 0.06 | −0.87 | −53 | −0.06 ± 0.06 | 28 of 30 |

**BTC:**

| Rule | DEV: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good | CONFIRM: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 545 | −0.18 ± 0.05 | −0.56 | −59 | −0.11 ± 0.05 | 29 of 30 | 497 | −0.11 ± 0.05 | −0.36 | −31 | +0.04 ± 0.06 | 5 of 30 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 364 | −0.22 ± 0.06 | −0.65 | −46 | −0.16 ± 0.06 | 30 of 30 | 347 | −0.10 ± 0.07 | −0.23 | −14 | +0.02 ± 0.08 | 9 of 30 |
| a.div: Bounce with the trend + RSI divergence | 43 | −0.09 ± 0.24 | +0.08 | +1 | −0.34 ± 0.21 | 28 of 30 | 52 | +0.15 ± 0.19 | +0.37 | +3 | +0.19 ± 0.20 | 5 of 30 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 282 | −0.05 ± 0.08 | −0.11 | −6 | −0.01 ± 0.08 | 13 of 30 | 260 | −0.13 ± 0.08 | −0.69 | −32 | +0.02 ± 0.08 | 11 of 30 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 292 | −0.21 ± 0.06 | −0.57 | −32 | −0.16 ± 0.06 | 29 of 30 | 255 | −0.10 ± 0.08 | −0.28 | −13 | +0.03 ± 0.09 | 10 of 30 |
| a.fresh: Bounce with the trend + first touch of the level | 396 | −0.22 ± 0.07 | −0.59 | −45 | −0.17 ± 0.07 | 30 of 30 | 356 | −0.12 ± 0.06 | −0.43 | −27 | +0.01 ± 0.07 | 15 of 30 |
| a.tested: Bounce with the trend + level touched before | 226 | −0.09 ± 0.08 | −0.28 | −13 | +0.01 ± 0.08 | 12 of 30 | 223 | −0.17 ± 0.07 | −0.73 | −29 | −0.03 ± 0.09 | 19 of 30 |
| b2: Bounce, any trend | 1202 | −0.19 ± 0.04 | −0.58 | −136 | −0.13 ± 0.04 | 30 of 30 | 1036 | −0.15 ± 0.04 | −0.43 | −79 | −0.02 ± 0.04 | 20 of 30 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 818 | −0.21 ± 0.05 | −0.59 | −94 | −0.14 ± 0.05 | 30 of 30 | 743 | −0.12 ± 0.05 | −0.34 | −45 | −0.03 ± 0.05 | 23 of 30 |
| b2.div: Bounce, any trend + RSI divergence | 99 | −0.27 ± 0.13 | −0.58 | −11 | −0.22 ± 0.14 | 30 of 30 | 106 | −0.04 ± 0.12 | +0.11 | +2 | +0.01 ± 0.13 | 14 of 30 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 539 | −0.18 ± 0.06 | −0.82 | −86 | −0.09 ± 0.06 | 30 of 30 | 508 | −0.06 ± 0.05 | −0.24 | −22 | +0.05 ± 0.06 | 5 of 30 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 729 | −0.22 ± 0.05 | −0.64 | −91 | −0.15 ± 0.05 | 30 of 30 | 610 | −0.12 ± 0.05 | −0.34 | −36 | +0.00 ± 0.06 | 16 of 30 |
| b2.fresh: Bounce, any trend + first touch of the level | 820 | −0.21 ± 0.05 | −0.57 | −91 | −0.17 ± 0.05 | 30 of 30 | 723 | −0.13 ± 0.05 | −0.42 | −53 | −0.02 ± 0.05 | 19 of 30 |
| b2.tested: Bounce, any trend + level touched before | 572 | −0.19 ± 0.05 | −0.59 | −66 | −0.10 ± 0.04 | 30 of 30 | 493 | −0.26 ± 0.06 | −0.85 | −74 | −0.11 ± 0.06 | 29 of 30 |

No row is positive in both periods. RSI divergence has too few trades to say anything (25 to 106
per period): on rule a it changes sign between the periods on both symbols, on rule b2 it is
negative in both. Waiting for a reversal bar means a later entry and a wider stop; it is negative
in all eight symbol-period cells.

### 6. Does the timeframe of the level matter?

**Gold:**

| Rule | DEV: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good | CONFIRM: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b2: Bounce, any trend | 752 | −0.12 ± 0.05 | −1.56 | −229 | −0.08 ± 0.05 | 30 of 30 | 830 | −0.15 ± 0.04 | −0.75 | −109 | −0.04 ± 0.04 | 26 of 30 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 486 | −0.10 ± 0.06 | −1.36 | −128 | −0.06 ± 0.06 | 25 of 30 | 476 | −0.17 ± 0.06 | −0.80 | −67 | −0.07 ± 0.06 | 28 of 30 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 235 | −0.16 ± 0.08 | −2.95 | −135 | −0.07 ± 0.09 | 28 of 30 | 330 | −0.10 ± 0.07 | −0.76 | −45 | −0.02 ± 0.07 | 19 of 30 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 106 | −0.26 ± 0.13 | −2.48 | −51 | −0.21 ± 0.13 | 30 of 30 | 126 | −0.29 ± 0.13 | −1.46 | −33 | −0.12 ± 0.13 | 26 of 30 |
| d: Breakout on the H1 close | 378 | +0.03 ± 0.07 | +0.01 | +1 | −0.01 ± 0.07 | 18 of 30 | 412 | +0.08 ± 0.07 | +0.95 | +69 | +0.05 ± 0.06 | 7 of 30 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 263 | −0.04 ± 0.08 | −1.42 | −73 | −0.04 ± 0.08 | 21 of 30 | 276 | +0.09 ± 0.08 | +1.17 | +57 | +0.06 ± 0.08 | 3 of 30 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 131 | −0.05 ± 0.13 | +1.50 | +38 | −0.12 ± 0.14 | 27 of 30 | 159 | +0.04 ± 0.10 | −0.15 | −4 | +0.04 ± 0.11 | 10 of 30 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 64 | +0.33 ± 0.18 | −0.18 | −2 | +0.12 ± 0.20 | 8 of 30 | 71 | +0.23 ± 0.18 | +2.46 | +31 | +0.16 ± 0.20 | 5 of 30 |

**BTC:**

| Rule | DEV: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good | CONFIRM: trades | R ± SE | $ per trade | $ per quarter | real − placebo, R ± SE | placebo sets at least as good |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b2: Bounce, any trend | 1202 | −0.19 ± 0.04 | −0.58 | −136 | −0.13 ± 0.04 | 30 of 30 | 1036 | −0.15 ± 0.04 | −0.43 | −79 | −0.02 ± 0.04 | 20 of 30 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 726 | −0.18 ± 0.05 | −0.54 | −76 | −0.11 ± 0.05 | 30 of 30 | 627 | −0.19 ± 0.05 | −0.63 | −70 | −0.07 ± 0.06 | 27 of 30 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 410 | −0.30 ± 0.06 | −0.95 | −76 | −0.25 ± 0.06 | 30 of 30 | 372 | −0.09 ± 0.07 | −0.28 | −19 | +0.03 ± 0.07 | 11 of 30 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 191 | −0.09 ± 0.10 | −0.28 | −10 | −0.02 ± 0.10 | 18 of 30 | 149 | −0.26 ± 0.09 | −0.74 | −20 | −0.13 ± 0.09 | 29 of 30 |
| d: Breakout on the H1 close | 533 | +0.09 ± 0.06 | +0.55 | +57 | +0.13 ± 0.05 | 0 of 30 | 470 | −0.06 ± 0.06 | −0.79 | −65 | +0.00 ± 0.05 | 14 of 30 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 385 | +0.11 ± 0.08 | +0.63 | +47 | +0.19 ± 0.07 | 0 of 30 | 337 | −0.07 ± 0.07 | −0.76 | −45 | +0.02 ± 0.07 | 10 of 30 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 189 | −0.02 ± 0.10 | +0.08 | +3 | +0.01 ± 0.10 | 13 of 30 | 168 | −0.05 ± 0.10 | −0.75 | −22 | +0.00 ± 0.10 | 18 of 30 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 69 | +0.08 ± 0.19 | +0.32 | +4 | +0.01 ± 0.19 | 13 of 30 | 74 | +0.18 ± 0.17 | +0.27 | +4 | +0.16 ± 0.16 | 2 of 30 |

Bounces at the biggest levels - a D1 swing or a weekly high / low - are negative in all four
symbol-periods and below their placebo in all four; on gold they are the worst class in both
periods. Breakouts of those levels are above zero in all four, on 64 to 74 trades each with a
standard error near 0.18 R; on gold in DEV the same trades lost money in dollars. Too few trades
to act on.

### 7. Buys and sells apart

**Gold:**

| Rule | DEV: buys | R | sells | R | CONFIRM: buys | R | sells | R |
|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 196 | +0.00 | 153 | −0.13 | 244 | −0.11 | 145 | −0.14 |
| b1: Bounce against the trend | 205 | −0.02 | 211 | −0.29 | 143 | −0.17 | 305 | −0.17 |
| b2: Bounce, any trend | 396 | −0.02 | 356 | −0.24 | 383 | −0.13 | 447 | −0.16 |
| c: Break and retest | 168 | −0.04 | 170 | +0.01 | 218 | +0.28 | 158 | −0.19 |
| c+: Break and retest, with the trend | 114 | +0.10 | 99 | −0.00 | 163 | +0.24 | 81 | −0.07 |
| d: Breakout on the H1 close | 206 | +0.04 | 172 | +0.02 | 238 | +0.24 | 174 | −0.13 |
| d+: Breakout on the H1 close, with the trend | 133 | +0.18 | 92 | +0.04 | 164 | +0.33 | 66 | +0.00 |
| e: Range fade (H4 flat) | 126 | +0.09 | 107 | −0.16 | 150 | −0.13 | 168 | −0.03 |

**BTC:**

| Rule | DEV: buys | R | sells | R | CONFIRM: buys | R | sells | R |
|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 254 | −0.20 | 291 | −0.17 | 270 | −0.11 | 227 | −0.11 |
| b1: Bounce against the trend | 378 | −0.19 | 293 | −0.21 | 246 | −0.32 | 306 | −0.08 |
| b2: Bounce, any trend | 626 | −0.20 | 576 | −0.19 | 509 | −0.21 | 527 | −0.08 |
| c: Break and retest | 278 | −0.09 | 253 | −0.02 | 229 | −0.17 | 230 | +0.11 |
| c+: Break and retest, with the trend | 154 | −0.19 | 175 | −0.08 | 145 | −0.17 | 144 | +0.02 |
| d: Breakout on the H1 close | 257 | +0.11 | 276 | +0.06 | 240 | −0.12 | 230 | −0.00 |
| d+: Breakout on the H1 close, with the trend | 131 | +0.09 | 173 | +0.00 | 137 | −0.05 | 115 | +0.06 |
| e: Range fade (H4 flat) | 184 | −0.29 | 172 | −0.24 | 134 | −0.27 | 189 | −0.08 |

### 8. The parameter sets tried on DEV

One change at a time around the base set. Each cell: trades: R per trade / real − placebo (placebo
sets at least as good). The last two rows are not among the 11 sets chosen before CONFIRM: entering
on the touch was added afterwards as a check on the fill, and the plain placebo is the base set
against the other control.

| Set | Change |
|---|---|
| target 0.25R, 1R, 3R | target a quarter of, equal to, three times the risk |
| wide stop | stop 1 ATR beyond the level instead of 0.5 |
| wide zone, narrow zone | zone ± 0.30 ATR; zone ± 0.05 ATR with the stop still 0.5 ATR from the level |
| hold 72h | time stop after 72 hours |
| trend D1 | trend = the D1 close against its 20-day EMA |
| major swings | swings need 8 / 5 / 3 bars on each side (H1 / H4 / D1) |
| arm 0.5 | a zone is armed 0.5 ATR away |
| enter on the touch | bounces and retests are entered the moment the bid reaches the zone instead of at the close of that M1 bar; every touch is entered, also the ones that go straight through; the ATR, trend and confirmations are those of the M1 close before; breakouts are unchanged |
| plain placebo | placebo prices are the shift alone; no draw is rejected for being near a real level |

**Gold:**

| Parameter set | a | b1 | b2 | c | c+ | d | d+ | e |
|---|---|---|---|---|---|---|---|---|
| base | 349: −0.06 / −0.04 (22) | 416: −0.16 / −0.08 (28) | 752: −0.12 / −0.08 (30) | 338: −0.01 / −0.03 (17) | 213: +0.05 / −0.01 (14) | 378: +0.03 / −0.01 (18) | 225: +0.13 / +0.00 (15) | 233: −0.03 / +0.03 (10) |
| target 0.25R | 427: −0.05 / −0.04 (30) | 493: −0.08 / −0.03 (29) | 919: −0.07 / −0.03 (29) | 368: −0.01 / +0.02 (5) | 227: +0.05 / +0.09 (0) | 468: −0.01 / +0.01 (7) | 267: −0.01 / +0.00 (14) | 293: −0.03 / +0.00 (18) |
| target 1R | 402: −0.03 / −0.03 (23) | 462: −0.17 / −0.10 (30) | 860: −0.11 / −0.07 (30) | 350: +0.02 / +0.04 (4) | 219: +0.11 / +0.10 (1) | 430: +0.03 / +0.03 (6) | 255: +0.09 / +0.06 (5) | 267: −0.07 / −0.02 (19) |
| target 3R | 320: −0.06 / −0.07 (21) | 391: −0.10 / −0.01 (19) | 685: −0.08 / −0.03 (23) | 323: +0.03 / −0.05 (20) | 209: +0.16 / +0.00 (16) | 345: +0.02 / −0.08 (29) | 203: +0.21 / +0.00 (15) | 215: +0.06 / +0.10 (4) |
| wide stop | 257: −0.04 / −0.05 (22) | 301: −0.12 / +0.00 (17) | 522: −0.07 / −0.01 (17) | 287: +0.00 / −0.07 (26) | 190: +0.15 / −0.02 (18) | 226: +0.17 / +0.09 (3) | 135: +0.34 / +0.20 (1) | 168: +0.03 / +0.10 (3) |
| wide zone | 340: −0.06 / −0.09 (28) | 410: −0.11 / −0.01 (15) | 709: −0.10 / −0.06 (28) | 329: −0.01 / −0.09 (28) | 218: +0.08 / −0.05 (22) | 295: −0.06 / −0.14 (30) | 174: −0.03 / −0.19 (30) | 220: −0.07 / −0.03 (18) |
| narrow zone | 273: −0.10 / −0.09 (25) | 326: −0.17 / −0.09 (28) | 595: −0.13 / −0.09 (30) | 285: −0.02 / −0.04 (19) | 177: +0.04 / −0.02 (20) | 413: +0.03 / −0.00 (14) | 240: +0.11 / +0.01 (11) | 179: −0.08 / −0.02 (15) |
| hold 72h | 348: −0.06 / −0.05 (23) | 414: −0.16 / −0.08 (28) | 748: −0.12 / −0.08 (29) | 338: +0.00 / −0.02 (15) | 213: +0.07 / −0.00 (14) | 376: +0.03 / −0.02 (22) | 224: +0.15 / +0.02 (12) | 233: −0.02 / +0.03 (11) |
| trend D1 | 356: −0.07 / −0.07 (27) | 410: −0.14 / −0.06 (28) | 752: −0.12 / −0.08 (30) | 338: −0.01 / −0.03 (17) | 209: +0.04 / −0.02 (18) | 378: +0.03 / −0.01 (18) | 226: +0.12 / +0.03 (9) | 233: −0.03 / +0.03 (10) |
| major swings | 248: −0.08 / −0.08 (22) | 324: −0.12 / −0.03 (19) | 570: −0.10 / −0.05 (24) | 243: +0.01 / −0.03 (22) | 164: +0.06 / −0.03 (24) | 296: +0.02 / −0.02 (18) | 187: +0.12 / −0.00 (13) | 185: −0.18 / −0.16 (29) |
| arm 0.5 | 414: −0.06 / −0.04 (24) | 495: −0.11 / −0.05 (28) | 887: −0.10 / −0.06 (29) | 438: −0.06 / −0.05 (22) | 272: +0.03 / −0.00 (14) | 378: +0.03 / −0.01 (18) | 225: +0.13 / +0.00 (15) | 273: +0.00 / +0.07 (5) |
| enter on the touch | 396: −0.14 / −0.11 (28) | 474: −0.18 / −0.10 (29) | 865: −0.16 / −0.10 (30) | 359: −0.04 / −0.05 (26) | 231: +0.03 / −0.02 (18) | 378: +0.03 / −0.01 (18) | 225: +0.13 / +0.00 (15) | 264: −0.06 / −0.03 (18) |
| plain placebo | 349: −0.06 / −0.03 (21) | 416: −0.16 / −0.04 (22) | 752: −0.12 / −0.05 (28) | 338: −0.01 / −0.01 (16) | 213: +0.05 / −0.00 (14) | 378: +0.03 / +0.01 (14) | 225: +0.13 / +0.00 (16) | 233: −0.03 / +0.08 (5) |

**BTC:**

| Parameter set | a | b1 | b2 | c | c+ | d | d+ | e |
|---|---|---|---|---|---|---|---|---|
| base | 545: −0.18 / −0.11 (29) | 671: −0.20 / −0.15 (30) | 1202: −0.19 / −0.13 (30) | 531: −0.05 / −0.02 (19) | 329: −0.13 / −0.10 (29) | 533: +0.09 / +0.13 (0) | 304: +0.04 / +0.04 (6) | 356: −0.27 / −0.16 (30) |
| target 0.25R | 687: −0.08 / −0.02 (25) | 837: −0.10 / −0.05 (30) | 1524: −0.09 / −0.04 (30) | 586: −0.01 / +0.03 (1) | 359: −0.01 / +0.03 (4) | 667: +0.02 / +0.03 (0) | 364: +0.01 / +0.01 (14) | 454: −0.13 / −0.05 (30) |
| target 1R | 636: −0.11 / −0.04 (27) | 769: −0.12 / −0.08 (30) | 1404: −0.11 / −0.06 (30) | 555: −0.02 / +0.05 (1) | 341: −0.07 / −0.02 (22) | 618: −0.00 / +0.03 (7) | 341: −0.03 / −0.03 (26) | 421: −0.13 / −0.05 (28) |
| target 3R | 502: −0.18 / −0.09 (27) | 616: −0.21 / −0.16 (30) | 1062: −0.21 / −0.14 (30) | 517: −0.07 / −0.02 (18) | 327: −0.07 / −0.02 (16) | 491: +0.12 / +0.14 (0) | 282: +0.08 / +0.05 (6) | 328: −0.28 / −0.15 (29) |
| wide stop | 394: −0.09 / −0.03 (23) | 458: −0.17 / −0.14 (30) | 791: −0.14 / −0.09 (30) | 439: +0.04 / +0.04 (5) | 276: −0.01 / −0.01 (18) | 353: +0.05 / +0.06 (3) | 197: +0.04 / +0.00 (17) | 238: −0.22 / −0.12 (27) |
| wide zone | 527: −0.11 / −0.07 (28) | 659: −0.09 / −0.03 (21) | 1106: −0.10 / −0.04 (27) | 526: +0.07 / +0.10 (0) | 341: +0.05 / +0.07 (6) | 407: +0.11 / +0.13 (0) | 234: +0.13 / +0.12 (2) | 341: −0.18 / −0.07 (27) |
| narrow zone | 422: −0.11 / −0.04 (21) | 527: −0.28 / −0.20 (30) | 944: −0.20 / −0.13 (30) | 452: −0.05 / +0.00 (16) | 283: −0.13 / −0.09 (27) | 582: +0.08 / +0.14 (0) | 326: +0.10 / +0.13 (0) | 276: −0.27 / −0.16 (30) |
| hold 72h | 543: −0.19 / −0.11 (30) | 668: −0.20 / −0.15 (30) | 1190: −0.19 / −0.13 (30) | 529: −0.06 / −0.02 (20) | 328: −0.14 / −0.10 (29) | 523: +0.07 / +0.13 (0) | 301: +0.05 / +0.05 (6) | 349: −0.27 / −0.16 (30) |
| trend D1 | 543: −0.20 / −0.12 (30) | 673: −0.18 / −0.13 (30) | 1202: −0.19 / −0.13 (30) | 531: −0.05 / −0.02 (19) | 327: −0.04 / +0.00 (19) | 533: +0.09 / +0.13 (0) | 296: +0.07 / +0.10 (1) | 356: −0.27 / −0.16 (30) |
| major swings | 395: −0.22 / −0.13 (30) | 522: −0.18 / −0.13 (30) | 913: −0.20 / −0.12 (30) | 392: −0.09 / −0.07 (27) | 244: −0.14 / −0.12 (28) | 411: +0.09 / +0.12 (0) | 230: +0.09 / +0.09 (1) | 284: −0.31 / −0.18 (30) |
| arm 0.5 | 656: −0.14 / −0.07 (28) | 807: −0.21 / −0.15 (30) | 1437: −0.18 / −0.12 (30) | 664: +0.01 / +0.04 (6) | 397: −0.02 / −0.01 (16) | 533: +0.09 / +0.13 (0) | 304: +0.04 / +0.04 (6) | 429: −0.23 / −0.13 (30) |
| enter on the touch | 614: −0.25 / −0.16 (30) | 774: −0.24 / −0.16 (30) | 1379: −0.25 / −0.16 (30) | 563: −0.04 / +0.00 (14) | 351: −0.10 / −0.06 (24) | 533: +0.09 / +0.13 (0) | 304: +0.04 / +0.04 (6) | 411: −0.31 / −0.21 (30) |
| plain placebo | 545: −0.18 / −0.10 (30) | 671: −0.20 / −0.14 (30) | 1202: −0.19 / −0.12 (30) | 531: −0.05 / −0.01 (20) | 329: −0.13 / −0.10 (28) | 533: +0.09 / +0.14 (0) | 304: +0.04 / +0.05 (6) | 356: −0.27 / −0.13 (29) |

Rules a, b1 and b2 are negative in all 11 sets on both symbols, and again when entered on the
touch; the range fade is negative in all 11 on BTC and in 8 of 11 on gold. BTC's breakout was above
zero in 10 of the 11 and above its placebo in all of them - and still failed on CONFIRM.

## What this means for the bot

| Use of a level | What was measured | Verdict |
|---|---|---|
| **Entry filter**: enter at support / resistance | rules a, b1, b2, e: negative in both periods on both symbols, 11 parameter sets, 6 confirmations, 3 level timeframes | do not code it |
| **Ladder trigger**: add to a losing position only at the next support | an add at support is rule b1 / b2 - a buy where price has fallen back to a level. It loses 0.12 to 0.20 R per add in every symbol and period, and never less than an add at a price that is not a level | do not code it; a level is not a safer place to add |
| **Target**: take profit at the next resistance | a level turns price no more often than any other price (section 4), so a target there is just a target at that distance | no advantage over a target at a fixed distance |
| **Entry trigger**: an H1 close beyond a level, with the H4 trend | gold: positive in both periods (section 3); BTC: +0.04 and −0.00 R | a lead for gold only; test it on untouched data first |

### The level book, in a form the engine can hold

Whichever use is tested next, this is the part to code. All of it runs on closed bars.

```
ATR          Wilder ATR(14) of H1, last closed bar
sources      H1 swing   5 bars each side   known at the close of the 5th bar after it     kept 5 days
             H4 swing   3 bars each side   known at the close of the 3rd bar after it     kept 20 days
             D1 swing   2 days each side   known at the close of the 2nd day after it     kept 90 days
             previous day's high / low     from the end of that UTC day                   to the end of the next
             previous week's high / low    from the end of that week (Sunday 00:00 UTC)   to the end of the next
swing high   a bar whose high is above the highs of the k bars before it and not below the highs of the k bars after it
zone         a new level within 0.15 ATR of a live zone joins it; otherwise it starts a zone at its own price
band         level ± 0.15 ATR
side         support while price is above the level, resistance while below
break        an H1 bar closes beyond the far edge of the band: the side flips; the second break retires the zone
armed        an M1 bar has closed 1 ATR or more away from the level on its current side
touch        the low (support) or high (resistance) of an M1 bar reaches the band of an armed zone; the zone is disarmed
```

### The one rule worth a clean test: gold breakout with the trend (d+)

```
symbol       XAUUSDm
trend        sign of the H4 MACD(12,26,9) signal line at the last closed H4 bar        (the engine's trend_tf=H4)
trigger      an H1 bar closes more than 0.15 ATR beyond a level that has not been broken since it formed,
             in the direction of the trend: above a resistance in an uptrend -> buy, below a support in a downtrend -> sell
entry        market, at that H1 close
stop         0.5 ATR on the other side of the level
target       2 x (entry − stop)
time stop    24 hours
skip         stop distance above 1.5 ATR (the close is already more than 1 ATR past the level); spread above 0.10 ATR
position     one at a time, no adds
```

As tested: 42 trades a quarter, +0.18 ± 0.07 R a trade over both periods, about +$85 a quarter per
0.01 lot, worst losing run 17 trades. The test it still needs is one run of exactly this on 2023,
which nothing here has read. If it is not clearly positive there, drop it.

## How far to trust this

- **Bounces losing is the firm result.** 3,820 trades of rule b2 over 32 months on two symbols,
  −0.17 ± 0.03 R and −0.15 ± 0.03 R in the two periods, the same sign in 11 of 12 half-years and in
  every parameter set, and confirmed on data the rule was not built on.
- **"A level is worse than a random price" is not firm.** It is clear in DEV (−0.11 ± 0.03 R, both
  symbols together) and small in CONFIRM (−0.03 ± 0.03 R). What both periods agree on is that a
  level is not better.
- **The intervals.** "± SE" comes from resampling whole weeks. "Placebo sets at least as good"
  holds the market fixed and only asks whether the real levels beat random level prices on that one
  path; it can read 30 of 30 while the interval still includes zero, as for gold's bounce in DEV.
- **One definition of a level.** A chartist chooses levels by eye; this is one written-down
  version of that with ten variations around it. Levels drawn by hand, round numbers and volume
  levels were not tested.
- **M1 bars, not ticks, and the fill.** Entries are market orders at the close of the M1 bar of
  the signal, up to a minute after the touch. As a check made after CONFIRM, on DEV only, the
  bounce and retest rules were also entered the moment the bid reaches the zone - what a bot that
  acts on every tick would do, including on the touches that go straight through. The bounce gets
  worse, not better: rule b2 makes −0.16 ± 0.04 R on gold and −0.25 ± 0.03 R on BTC, 0.10 and 0.16 R
  below its placebo, negative in all three half-years on both. Inside a bar the stop is assumed to
  come before the target, which is the pessimistic order; with stops 0.5 ATR and more from the
  level few bars reach both. Costs are the recorded spread; no commission, no swap on positions
  held overnight, no slippage beyond a gap through the stop.
- **Gaps in the history.** Gold's daily break and weekends, and the few holes in the BTC archive
  (hours in April 2024; a day or two in April 2025, August 2025 and March 2026), are gaps between
  bars: a trade open across one is carried to the next bar, and a stop the gap jumped over is
  filled at that bar's open.
- **What was not tested:** swing trades with stops of several ATR held for days; any of this
  combined with the bot's own RSI / MACD entries inside the engine.
- **The placebo was tightened once, in DEV, before any CONFIRM run.** Its first version kept
  placebo prices away from every level that had not aged out, retired ones included; no such price
  existed for 11 - 18 % of zones and the rest were pushed into untraded territory. The final
  version keeps them away from live levels only (0.1 - 0.2 % of zones left without a free price).
  With the first version gold's bounce read −0.01 ± 0.05 R against its placebo instead of
  −0.08 ± 0.05 R; BTC's read −0.14 ± 0.04 R instead of −0.13 ± 0.04 R. The plain placebo, with no
  draw rejected, is shown next to the final one below and agrees with it.

## Reproduce

```
export ALCADEIAS_STORE_DIR=/path/to/data/store          # only if the tick store is not in data/store
python -m backtesting.research.sr_trades run DEV --sets all                                  # 13 sets, about 6 minutes
python -m backtesting.research.sr_trades run CONFIRM --sets "base,plain placebo,target 0.25R"
python -m backtesting.research.sr_trades tables DEV CONFIRM                                  # the tables of this report
python -m backtesting.research.sr_trades levels DEV                                          # level counts and density only
python -m pytest tests/test_sr_trades.py -q
```

The runs are stored as JSON under `data/sr_trades/` (or `SR_TRADES_OUT`). Code:
`backtesting/research/sr_trades.py`. Tests: `tests/test_sr_trades.py` - the simulator on hand-made
bars, the level logic, and the check that history cut off at any bar, or followed by a different
future, gives the same levels, events and entries up to that bar.

## Appendix: every rule

For each symbol and period, two tables. The first is in USD per 0.01 lot after the spread; "spread
paid" is the average spread of a round trip in R. The second sets the real levels against the 30
placebo sets; its last column splits the placebo trades by where the placebo price lies - moved
back inside the range the swing came from, or out beyond the swing.

### Gold, DEV

| Rule | Trades | Risk per trade $ (1R) | Win | Avg win $ | Avg loss $ | Expectancy $ ± SE | Expectancy R ± SE | Spread paid, R | $ per quarter | Worst losing run: trades ($) | Exit by stop / target / time, % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 349 | 14.20 | 32% | +26.22 | −14.78 | −1.74 ± 1.22 | −0.06 ± 0.07 | 0.02 | −118 | 19 (−270) | 68 / 31 / 1 |
| b1: Bounce against the trend | 416 | 11.61 | 28% | +24.01 | −11.22 | −1.23 ± 0.75 | −0.16 ± 0.06 | 0.02 | −99 | 13 (−154) | 71 / 27 / 1 |
| b2: Bounce, any trend | 752 | 12.81 | 30% | +25.25 | −12.80 | −1.56 ± 0.71 | −0.12 ± 0.05 | 0.02 | −229 | 24 (−336) | 70 / 29 / 1 |
| c: Break and retest | 338 | 14.57 | 34% | +27.93 | −14.86 | −0.30 ± 1.42 | −0.01 ± 0.07 | 0.02 | −20 | 10 (−126) | 66 / 33 / 1 |
| c+: Break and retest, with the trend | 213 | 14.69 | 37% | +28.61 | −15.07 | +0.92 ± 1.77 | +0.05 ± 0.09 | 0.02 | +38 | 11 (−125) | 63 / 35 / 1 |
| d: Breakout on the H1 close | 378 | 20.13 | 35% | +35.75 | −19.62 | +0.01 ± 1.28 | +0.03 ± 0.07 | 0.01 | +1 | 14 (−95) | 63 / 32 / 5 |
| d+: Breakout on the H1 close, with the trend | 225 | 18.11 | 38% | +34.77 | −17.71 | +2.12 ± 1.90 | +0.13 ± 0.10 | 0.01 | +93 | 17 (−121) | 60 / 36 / 4 |
| e: Range fade (H4 flat) | 233 | 10.73 | 33% | +20.67 | −10.87 | −0.59 ± 1.32 | −0.03 ± 0.11 | 0.03 | −27 | 17 (−164) | 67 / 31 / 1 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 258 | 14.65 | 33% | +27.22 | −15.10 | −1.32 ± 1.28 | −0.03 ± 0.08 | 0.02 | −66 | 15 (−361) | 67 / 32 / 1 |
| a.div: Bounce with the trend + RSI divergence | 25 | 12.27 | 36% | +19.61 | −13.66 | −1.69 ± 3.83 | +0.08 ± 0.29 | 0.02 | −8 | 8 (−84) | 64 / 36 / 0 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 157 | 18.31 | 30% | +32.83 | −18.99 | −3.47 ± 2.38 | −0.14 ± 0.11 | 0.02 | −106 | 10 (−132) | 70 / 27 / 3 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 182 | 14.75 | 30% | +28.34 | −14.97 | −1.88 ± 1.56 | −0.09 ± 0.11 | 0.02 | −67 | 9 (−43) | 69 / 30 / 1 |
| a.fresh: Bounce with the trend + first touch of the level | 261 | 13.41 | 33% | +24.51 | −14.08 | −1.36 ± 1.31 | −0.02 ± 0.08 | 0.02 | −69 | 16 (−226) | 67 / 32 / 2 |
| a.tested: Bounce with the trend + level touched before | 138 | 15.24 | 28% | +27.98 | −15.71 | −3.68 ± 1.73 | −0.17 ± 0.11 | 0.02 | −99 | 10 (−123) | 72 / 28 / 0 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 541 | 12.98 | 31% | +25.48 | −12.91 | −1.13 ± 0.76 | −0.09 ± 0.05 | 0.02 | −120 | 16 (−175) | 69 / 30 / 1 |
| b2.div: Bounce, any trend + RSI divergence | 49 | 12.37 | 31% | +27.45 | −11.51 | +0.42 ± 2.56 | −0.06 ± 0.17 | 0.02 | +4 | 9 (−43) | 67 / 31 / 2 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 326 | 18.01 | 30% | +33.82 | −17.92 | −2.21 ± 1.46 | −0.13 ± 0.07 | 0.02 | −140 | 13 (−181) | 69 / 27 / 4 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 435 | 12.79 | 28% | +25.15 | −12.89 | −2.22 ± 0.91 | −0.16 ± 0.07 | 0.02 | −188 | 13 (−150) | 71 / 28 / 0 |
| b2.fresh: Bounce, any trend + first touch of the level | 554 | 12.43 | 30% | +24.49 | −12.40 | −1.22 ± 0.80 | −0.10 ± 0.06 | 0.02 | −131 | 25 (−330) | 69 / 29 / 2 |
| b2.tested: Bounce, any trend + level touched before | 308 | 13.31 | 27% | +25.47 | −13.48 | −2.98 ± 1.20 | −0.19 ± 0.07 | 0.02 | −179 | 12 (−155) | 73 / 27 / 0 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 486 | 12.32 | 30% | +23.85 | −12.39 | −1.36 ± 0.95 | −0.10 ± 0.06 | 0.02 | −128 | 15 (−221) | 69 / 29 / 2 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 235 | 12.82 | 28% | +23.59 | −13.32 | −2.95 ± 1.28 | −0.16 ± 0.08 | 0.02 | −135 | 11 (−383) | 71 / 28 / 0 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 106 | 14.91 | 25% | +33.44 | −14.16 | −2.48 ± 2.16 | −0.26 ± 0.13 | 0.02 | −51 | 10 (−233) | 75 / 25 / 1 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 263 | 19.98 | 33% | +34.87 | −19.66 | −1.42 ± 1.66 | −0.04 ± 0.08 | 0.01 | −73 | 10 (−254) | 65 / 30 / 5 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 131 | 19.93 | 34% | +40.17 | −18.06 | +1.50 ± 2.48 | −0.05 ± 0.13 | 0.01 | +38 | 15 (−229) | 65 / 27 / 8 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 64 | 22.45 | 44% | +33.04 | −26.02 | −0.18 ± 3.91 | +0.33 ± 0.18 | 0.01 | −2 | 5 (−197) | 53 / 44 / 3 |

Against the placebo levels:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 349 | 32% | −0.06 | 354 | 33% | −0.01 | −0.04 ± 0.07 | −0.19 .. +0.09 | 22 of 30 | −0.01 / −0.01 |
| b1: Bounce against the trend | 416 | 28% | −0.16 | 458 | 31% | −0.08 | −0.08 ± 0.07 | −0.21 .. +0.05 | 28 of 30 | −0.03 / −0.12 |
| b2: Bounce, any trend | 752 | 30% | −0.12 | 787 | 32% | −0.05 | −0.08 ± 0.05 | −0.17 .. +0.02 | 30 of 30 | −0.02 / −0.08 |
| c: Break and retest | 338 | 34% | −0.01 | 349 | 35% | +0.02 | −0.03 ± 0.07 | −0.17 .. +0.12 | 17 of 30 | −0.03 / +0.09 |
| c+: Break and retest, with the trend | 213 | 37% | +0.05 | 217 | 36% | +0.06 | −0.01 ± 0.10 | −0.19 .. +0.19 | 14 of 30 | −0.01 / +0.14 |
| d: Breakout on the H1 close | 378 | 35% | +0.03 | 440 | 36% | +0.04 | −0.01 ± 0.07 | −0.13 .. +0.13 | 18 of 30 | −0.02 / +0.16 |
| d+: Breakout on the H1 close, with the trend | 225 | 38% | +0.13 | 248 | 38% | +0.12 | +0.00 ± 0.10 | −0.18 .. +0.21 | 15 of 30 | +0.03 / +0.25 |
| e: Range fade (H4 flat) | 233 | 33% | −0.03 | 252 | 32% | −0.06 | +0.03 ± 0.12 | −0.21 .. +0.25 | 10 of 30 | −0.02 / −0.10 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 258 | 33% | −0.03 | 210 | 34% | +0.02 | −0.04 ± 0.09 | −0.22 .. +0.13 | 18 of 30 | −0.01 / +0.05 |
| a.div: Bounce with the trend + RSI divergence | 25 | 36% | +0.08 | 20 | 40% | +0.19 | −0.11 ± 0.32 | −0.73 .. +0.52 | 22 of 30 | +0.22 / +0.14 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 157 | 30% | −0.14 | 178 | 35% | +0.01 | −0.15 ± 0.11 | −0.38 .. +0.07 | 29 of 30 | −0.01 / +0.05 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 182 | 30% | −0.09 | 157 | 33% | −0.02 | −0.07 ± 0.11 | −0.30 .. +0.15 | 22 of 30 | −0.03 / −0.01 |
| a.fresh: Bounce with the trend + first touch of the level | 261 | 33% | −0.02 | 254 | 34% | +0.01 | −0.04 ± 0.08 | −0.20 .. +0.12 | 19 of 30 | +0.01 / +0.03 |
| a.tested: Bounce with the trend + level touched before | 138 | 28% | −0.17 | 146 | 30% | −0.11 | −0.07 ± 0.10 | −0.27 .. +0.12 | 24 of 30 | −0.10 / −0.12 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 541 | 31% | −0.09 | 512 | 32% | −0.05 | −0.04 ± 0.06 | −0.15 .. +0.08 | 24 of 30 | −0.03 / −0.07 |
| b2.div: Bounce, any trend + RSI divergence | 49 | 31% | −0.06 | 54 | 33% | −0.04 | −0.02 ± 0.19 | −0.37 .. +0.35 | 17 of 30 | +0.16 / −0.17 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 326 | 30% | −0.13 | 387 | 32% | −0.09 | −0.04 ± 0.08 | −0.19 .. +0.11 | 21 of 30 | −0.05 / −0.15 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 435 | 28% | −0.16 | 411 | 32% | −0.05 | −0.11 ± 0.07 | −0.25 .. +0.03 | 29 of 30 | −0.03 / −0.07 |
| b2.fresh: Bounce, any trend + first touch of the level | 554 | 30% | −0.10 | 561 | 33% | −0.03 | −0.07 ± 0.07 | −0.21 .. +0.06 | 27 of 30 | +0.00 / −0.07 |
| b2.tested: Bounce, any trend + level touched before | 308 | 27% | −0.19 | 329 | 30% | −0.10 | −0.09 ± 0.08 | −0.24 .. +0.06 | 26 of 30 | −0.10 / −0.10 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 486 | 30% | −0.10 | 513 | 32% | −0.04 | −0.06 ± 0.06 | −0.18 .. +0.05 | 25 of 30 | −0.02 / −0.06 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 235 | 28% | −0.16 | 223 | 31% | −0.09 | −0.07 ± 0.09 | −0.25 .. +0.11 | 28 of 30 | −0.03 / −0.16 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 106 | 25% | −0.26 | 122 | 32% | −0.05 | −0.21 ± 0.13 | −0.46 .. +0.06 | 30 of 30 | +0.02 / −0.10 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 263 | 33% | −0.04 | 315 | 34% | −0.00 | −0.04 ± 0.08 | −0.19 .. +0.12 | 21 of 30 | −0.04 / +0.09 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 131 | 34% | −0.05 | 128 | 38% | +0.07 | −0.12 ± 0.14 | −0.38 .. +0.16 | 27 of 30 | −0.03 / +0.23 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 64 | 44% | +0.33 | 63 | 41% | +0.21 | +0.12 ± 0.20 | −0.25 .. +0.53 | 8 of 30 | +0.08 / +0.31 |

### Gold, CONFIRM

| Rule | Trades | Risk per trade $ (1R) | Win | Avg win $ | Avg loss $ | Expectancy $ ± SE | Expectancy R ± SE | Spread paid, R | $ per quarter | Worst losing run: trades ($) | Exit by stop / target / time, % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 389 | 5.31 | 30% | +9.84 | −5.48 | −0.91 ± 0.45 | −0.12 ± 0.07 | 0.04 | −63 | 15 (−193) | 70 / 29 / 1 |
| b1: Bounce against the trend | 448 | 4.55 | 28% | +9.40 | −4.51 | −0.66 ± 0.30 | −0.17 ± 0.06 | 0.05 | −52 | 15 (−32) | 72 / 27 / 0 |
| b2: Bounce, any trend | 830 | 4.90 | 29% | +9.62 | −4.94 | −0.75 ± 0.27 | −0.15 ± 0.04 | 0.04 | −109 | 13 (−39) | 71 / 28 / 1 |
| c: Break and retest | 376 | 5.21 | 36% | +10.46 | −5.13 | +0.51 ± 0.40 | +0.08 ± 0.07 | 0.04 | +34 | 10 (−56) | 62 / 36 / 2 |
| c+: Break and retest, with the trend | 244 | 5.15 | 38% | +10.15 | −5.15 | +0.68 ± 0.50 | +0.14 ± 0.09 | 0.04 | +29 | 8 (−74) | 61 / 38 / 1 |
| d: Breakout on the H1 close | 412 | 7.72 | 37% | +15.20 | −7.29 | +0.95 ± 0.54 | +0.08 ± 0.07 | 0.03 | +69 | 11 (−113) | 61 / 34 / 5 |
| d+: Breakout on the H1 close, with the trend | 230 | 7.26 | 42% | +14.39 | −6.98 | +1.94 ± 0.83 | +0.23 ± 0.10 | 0.03 | +79 | 8 (−61) | 57 / 40 / 3 |
| e: Range fade (H4 flat) | 318 | 4.52 | 31% | +9.01 | −4.53 | −0.31 ± 0.41 | −0.08 ± 0.08 | 0.05 | −18 | 13 (−53) | 69 / 30 / 1 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 274 | 5.38 | 28% | +9.45 | −5.66 | −1.36 ± 0.60 | −0.16 ± 0.08 | 0.04 | −66 | 27 (−302) | 72 / 28 / 1 |
| a.div: Bounce with the trend + RSI divergence | 32 | 6.12 | 31% | +10.27 | −6.40 | −1.19 ± 1.64 | −0.11 ± 0.25 | 0.03 | −7 | 9 (−76) | 69 / 28 / 3 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 190 | 7.22 | 32% | +12.96 | −7.24 | −0.86 ± 0.74 | −0.12 ± 0.10 | 0.03 | −29 | 8 (−45) | 68 / 27 / 4 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 206 | 5.34 | 31% | +9.87 | −5.52 | −0.81 ± 0.71 | −0.09 ± 0.10 | 0.04 | −30 | 17 (−205) | 69 / 30 / 1 |
| a.fresh: Bounce with the trend + first touch of the level | 298 | 5.33 | 29% | +9.19 | −5.62 | −1.29 ± 0.54 | −0.14 ± 0.08 | 0.04 | −68 | 16 (−194) | 71 / 28 / 1 |
| a.tested: Bounce with the trend + level touched before | 159 | 5.18 | 31% | +10.32 | −5.19 | −0.41 ± 0.59 | −0.09 ± 0.10 | 0.04 | −12 | 11 (−40) | 69 / 30 / 1 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 574 | 4.85 | 29% | +9.19 | −4.96 | −0.89 ± 0.37 | −0.14 ± 0.05 | 0.05 | −90 | 24 (−246) | 71 / 28 / 1 |
| b2.div: Bounce, any trend + RSI divergence | 72 | 5.19 | 33% | +9.64 | −5.29 | −0.32 ± 0.96 | −0.02 ± 0.17 | 0.04 | −4 | 7 (−76) | 67 / 32 / 1 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 389 | 6.84 | 31% | +13.22 | −6.75 | −0.49 ± 0.52 | −0.10 ± 0.07 | 0.03 | −33 | 16 (−93) | 69 / 28 / 3 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 497 | 4.78 | 29% | +9.25 | −4.84 | −0.70 ± 0.39 | −0.12 ± 0.06 | 0.05 | −62 | 17 (−72) | 71 / 29 / 1 |
| b2.fresh: Bounce, any trend + first touch of the level | 614 | 5.00 | 30% | +9.40 | −5.11 | −0.74 ± 0.34 | −0.11 ± 0.05 | 0.04 | −80 | 13 (−67) | 70 / 29 / 1 |
| b2.tested: Bounce, any trend + level touched before | 345 | 4.75 | 27% | +9.61 | −4.74 | −0.87 ± 0.33 | −0.20 ± 0.06 | 0.04 | −53 | 13 (−39) | 73 / 27 / 0 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 476 | 5.08 | 28% | +10.24 | −5.07 | −0.80 ± 0.35 | −0.17 ± 0.06 | 0.04 | −67 | 23 (−59) | 72 / 28 / 0 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 330 | 4.74 | 30% | +8.71 | −4.88 | −0.76 ± 0.38 | −0.10 ± 0.07 | 0.05 | −45 | 16 (−65) | 70 / 29 / 1 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 126 | 4.68 | 24% | +9.03 | −4.74 | −1.46 ± 0.69 | −0.29 ± 0.13 | 0.05 | −33 | 13 (−96) | 76 / 24 / 0 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 276 | 7.72 | 37% | +15.46 | −7.20 | +1.17 ± 0.65 | +0.09 ± 0.08 | 0.03 | +57 | 8 (−79) | 61 / 34 / 4 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 159 | 7.66 | 36% | +13.04 | −7.72 | −0.15 ± 0.87 | +0.04 ± 0.10 | 0.03 | −4 | 7 (−116) | 62 / 33 / 6 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 71 | 8.30 | 41% | +17.39 | −7.86 | +2.46 ± 1.63 | +0.23 ± 0.18 | 0.03 | +31 | 6 (−81) | 58 / 39 / 3 |

Against the placebo levels:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 389 | 30% | −0.12 | 406 | 32% | −0.06 | −0.06 ± 0.06 | −0.18 .. +0.06 | 26 of 30 | −0.05 / −0.09 |
| b1: Bounce against the trend | 448 | 28% | −0.17 | 480 | 29% | −0.15 | −0.02 ± 0.05 | −0.12 .. +0.07 | 20 of 30 | −0.09 / −0.21 |
| b2: Bounce, any trend | 830 | 29% | −0.15 | 864 | 30% | −0.11 | −0.04 ± 0.04 | −0.11 .. +0.03 | 26 of 30 | −0.06 / −0.17 |
| c: Break and retest | 376 | 36% | +0.08 | 403 | 34% | +0.01 | +0.07 ± 0.07 | −0.07 .. +0.21 | 4 of 30 | −0.04 / +0.09 |
| c+: Break and retest, with the trend | 244 | 38% | +0.14 | 253 | 35% | +0.02 | +0.12 ± 0.10 | −0.07 .. +0.32 | 0 of 30 | −0.06 / +0.11 |
| d: Breakout on the H1 close | 412 | 37% | +0.08 | 480 | 35% | +0.03 | +0.05 ± 0.06 | −0.07 .. +0.16 | 7 of 30 | +0.02 / +0.06 |
| d+: Breakout on the H1 close, with the trend | 230 | 42% | +0.23 | 272 | 37% | +0.07 | +0.16 ± 0.08 | +0.01 .. +0.32 | 0 of 30 | +0.02 / +0.14 |
| e: Range fade (H4 flat) | 318 | 31% | −0.08 | 312 | 31% | −0.07 | −0.00 ± 0.07 | −0.14 .. +0.12 | 14 of 30 | −0.04 / −0.11 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 274 | 28% | −0.16 | 254 | 33% | −0.03 | −0.13 ± 0.08 | −0.29 .. +0.03 | 30 of 30 | −0.02 / −0.05 |
| a.div: Bounce with the trend + RSI divergence | 32 | 31% | −0.11 | 30 | 35% | +0.03 | −0.14 ± 0.25 | −0.65 .. +0.37 | 18 of 30 | −0.00 / +0.08 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 190 | 32% | −0.12 | 199 | 33% | −0.07 | −0.05 ± 0.10 | −0.25 .. +0.14 | 20 of 30 | −0.05 / −0.12 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 206 | 31% | −0.09 | 198 | 33% | −0.04 | −0.05 ± 0.10 | −0.24 .. +0.13 | 20 of 30 | −0.02 / −0.08 |
| a.fresh: Bounce with the trend + first touch of the level | 298 | 29% | −0.14 | 284 | 32% | −0.05 | −0.09 ± 0.08 | −0.24 .. +0.07 | 26 of 30 | −0.05 / −0.06 |
| a.tested: Bounce with the trend + level touched before | 159 | 31% | −0.09 | 169 | 32% | −0.07 | −0.02 ± 0.09 | −0.19 .. +0.17 | 14 of 30 | −0.06 / −0.10 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 574 | 29% | −0.14 | 572 | 30% | −0.11 | −0.04 ± 0.05 | −0.13 .. +0.05 | 22 of 30 | −0.05 / −0.16 |
| b2.div: Bounce, any trend + RSI divergence | 72 | 33% | −0.02 | 72 | 29% | −0.14 | +0.12 ± 0.17 | −0.20 .. +0.45 | 9 of 30 | −0.12 / −0.15 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 389 | 31% | −0.10 | 426 | 30% | −0.13 | +0.02 ± 0.07 | −0.12 .. +0.15 | 9 of 30 | −0.05 / −0.25 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 497 | 29% | −0.12 | 480 | 29% | −0.13 | +0.01 ± 0.06 | −0.11 .. +0.12 | 12 of 30 | −0.07 / −0.20 |
| b2.fresh: Bounce, any trend + first touch of the level | 614 | 30% | −0.11 | 602 | 31% | −0.10 | −0.01 ± 0.05 | −0.10 .. +0.08 | 18 of 30 | −0.05 / −0.17 |
| b2.tested: Bounce, any trend + level touched before | 345 | 27% | −0.20 | 369 | 29% | −0.13 | −0.06 ± 0.06 | −0.19 .. +0.05 | 28 of 30 | −0.11 / −0.17 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 476 | 28% | −0.17 | 513 | 30% | −0.10 | −0.07 ± 0.06 | −0.18 .. +0.04 | 28 of 30 | −0.07 / −0.17 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 330 | 30% | −0.10 | 297 | 31% | −0.08 | −0.02 ± 0.07 | −0.16 .. +0.11 | 19 of 30 | −0.05 / −0.12 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 126 | 24% | −0.29 | 135 | 28% | −0.17 | −0.12 ± 0.13 | −0.37 .. +0.12 | 26 of 30 | −0.12 / −0.21 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 276 | 37% | +0.09 | 324 | 35% | +0.03 | +0.06 ± 0.08 | −0.09 .. +0.20 | 3 of 30 | +0.02 / +0.06 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 159 | 36% | +0.04 | 165 | 34% | −0.00 | +0.04 ± 0.11 | −0.17 .. +0.25 | 10 of 30 | +0.02 / −0.04 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 71 | 41% | +0.23 | 75 | 37% | +0.06 | +0.16 ± 0.20 | −0.21 .. +0.55 | 5 of 30 | +0.04 / +0.08 |

### BTC, DEV

| Rule | Trades | Risk per trade $ (1R) | Win | Avg win $ | Avg loss $ | Expectancy $ ± SE | Expectancy R ± SE | Spread paid, R | $ per quarter | Worst losing run: trades ($) | Exit by stop / target / time, % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 545 | 3.20 | 28% | +6.33 | −3.18 | −0.56 ± 0.19 | −0.18 ± 0.05 | 0.05 | −59 | 14 (−46) | 72 / 27 / 1 |
| b1: Bounce against the trend | 671 | 3.28 | 27% | +6.76 | −3.25 | −0.58 ± 0.19 | −0.20 ± 0.06 | 0.05 | −75 | 17 (−59) | 73 / 27 / 0 |
| b2: Bounce, any trend | 1202 | 3.25 | 27% | +6.56 | −3.22 | −0.58 ± 0.13 | −0.19 ± 0.04 | 0.05 | −136 | 17 (−82) | 73 / 27 / 0 |
| c: Break and retest | 531 | 3.48 | 32% | +6.63 | −3.56 | −0.27 ± 0.23 | −0.05 ± 0.06 | 0.05 | −28 | 10 (−43) | 68 / 32 / 1 |
| c+: Break and retest, with the trend | 329 | 3.53 | 30% | +6.85 | −3.58 | −0.44 ± 0.32 | −0.13 ± 0.08 | 0.05 | −28 | 16 (−72) | 70 / 29 / 1 |
| d: Breakout on the H1 close | 533 | 5.01 | 37% | +9.69 | −4.90 | +0.55 ± 0.35 | +0.09 ± 0.06 | 0.03 | +57 | 12 (−42) | 62 / 35 / 3 |
| d+: Breakout on the H1 close, with the trend | 304 | 5.11 | 36% | +9.75 | −5.01 | +0.23 ± 0.46 | +0.04 ± 0.08 | 0.03 | +14 | 12 (−45) | 64 / 33 / 3 |
| e: Range fade (H4 flat) | 356 | 2.89 | 25% | +5.50 | −2.90 | −0.83 ± 0.21 | −0.27 ± 0.07 | 0.06 | −57 | 14 (−47) | 75 / 24 / 1 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 364 | 3.19 | 26% | +6.47 | −3.17 | −0.65 ± 0.21 | −0.22 ± 0.06 | 0.05 | −46 | 13 (−37) | 74 / 26 / 0 |
| a.div: Bounce with the trend + RSI divergence | 43 | 3.48 | 30% | +7.86 | −3.29 | +0.08 ± 1.07 | −0.09 ± 0.24 | 0.04 | +1 | 13 (−33) | 70 / 30 / 0 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 282 | 4.48 | 33% | +8.47 | −4.34 | −0.11 ± 0.38 | −0.05 ± 0.08 | 0.04 | −6 | 10 (−38) | 66 / 30 / 4 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 292 | 3.12 | 27% | +6.33 | −3.09 | −0.57 ± 0.23 | −0.21 ± 0.06 | 0.05 | −32 | 10 (−28) | 73 / 26 / 1 |
| a.fresh: Bounce with the trend + first touch of the level | 396 | 3.25 | 26% | +6.72 | −3.19 | −0.59 ± 0.24 | −0.22 ± 0.07 | 0.05 | −45 | 18 (−54) | 74 / 26 / 0 |
| a.tested: Bounce with the trend + level touched before | 226 | 3.16 | 31% | +6.10 | −3.15 | −0.28 ± 0.27 | −0.09 ± 0.08 | 0.05 | −13 | 8 (−27) | 69 / 30 / 1 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 818 | 3.21 | 27% | +6.57 | −3.18 | −0.59 ± 0.15 | −0.21 ± 0.05 | 0.05 | −94 | 14 (−63) | 73 / 26 / 0 |
| b2.div: Bounce, any trend + RSI divergence | 99 | 3.50 | 24% | +8.04 | −3.34 | −0.58 ± 0.58 | −0.27 ± 0.13 | 0.05 | −11 | 13 (−42) | 76 / 24 / 0 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 539 | 4.75 | 28% | +8.92 | −4.68 | −0.82 ± 0.29 | −0.18 ± 0.06 | 0.04 | −86 | 19 (−78) | 71 / 26 / 3 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 729 | 3.28 | 26% | +6.73 | −3.24 | −0.64 ± 0.16 | −0.22 ± 0.05 | 0.05 | −91 | 17 (−41) | 74 / 26 / 0 |
| b2.fresh: Bounce, any trend + first touch of the level | 820 | 3.30 | 27% | +6.81 | −3.24 | −0.57 ± 0.15 | −0.21 ± 0.05 | 0.05 | −91 | 16 (−75) | 73 / 26 / 0 |
| b2.tested: Bounce, any trend + level touched before | 572 | 3.25 | 27% | +6.50 | −3.23 | −0.59 ± 0.16 | −0.19 ± 0.05 | 0.05 | −66 | 17 (−62) | 73 / 27 / 1 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 726 | 3.14 | 28% | +6.26 | −3.12 | −0.54 ± 0.18 | −0.18 ± 0.05 | 0.05 | −76 | 16 (−61) | 72 / 27 / 0 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 410 | 3.34 | 23% | +6.76 | −3.31 | −0.95 ± 0.23 | −0.30 ± 0.06 | 0.05 | −76 | 18 (−72) | 77 / 23 / 1 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 191 | 3.62 | 30% | +7.34 | −3.60 | −0.28 ± 0.35 | −0.09 ± 0.10 | 0.05 | −10 | 11 (−52) | 70 / 30 / 0 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 385 | 4.83 | 38% | +9.34 | −4.76 | +0.63 ± 0.43 | +0.11 ± 0.08 | 0.03 | +47 | 17 (−53) | 62 / 35 / 3 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 189 | 5.43 | 34% | +10.43 | −5.21 | +0.08 ± 0.56 | −0.02 ± 0.10 | 0.03 | +3 | 9 (−53) | 66 / 31 / 3 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 69 | 5.65 | 36% | +10.84 | −5.66 | +0.32 ± 1.08 | +0.08 ± 0.19 | 0.03 | +4 | 8 (−45) | 62 / 35 / 3 |

Against the placebo levels:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 545 | 28% | −0.18 | 530 | 31% | −0.08 | −0.11 ± 0.05 | −0.20 .. −0.00 | 29 of 30 | −0.09 / −0.05 |
| b1: Bounce against the trend | 671 | 27% | −0.20 | 722 | 32% | −0.06 | −0.15 ± 0.05 | −0.25 .. −0.05 | 30 of 30 | −0.05 / −0.06 |
| b2: Bounce, any trend | 1202 | 27% | −0.19 | 1212 | 31% | −0.07 | −0.13 ± 0.04 | −0.20 .. −0.05 | 30 of 30 | −0.08 / −0.05 |
| c: Break and retest | 531 | 32% | −0.05 | 546 | 32% | −0.04 | −0.02 ± 0.06 | −0.13 .. +0.11 | 19 of 30 | −0.05 / −0.02 |
| c+: Break and retest, with the trend | 329 | 30% | −0.13 | 355 | 32% | −0.04 | −0.10 ± 0.08 | −0.25 .. +0.07 | 29 of 30 | −0.04 / −0.03 |
| d: Breakout on the H1 close | 533 | 37% | +0.09 | 618 | 33% | −0.04 | +0.13 ± 0.05 | +0.02 .. +0.24 | 0 of 30 | −0.03 / −0.06 |
| d+: Breakout on the H1 close, with the trend | 304 | 36% | +0.04 | 354 | 34% | −0.00 | +0.04 ± 0.07 | −0.10 .. +0.18 | 6 of 30 | +0.02 / −0.03 |
| e: Range fade (H4 flat) | 356 | 25% | −0.27 | 365 | 30% | −0.11 | −0.16 ± 0.07 | −0.30 .. −0.00 | 30 of 30 | −0.11 / −0.11 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 364 | 26% | −0.22 | 335 | 32% | −0.06 | −0.16 ± 0.06 | −0.28 .. −0.04 | 30 of 30 | −0.06 / −0.05 |
| a.div: Bounce with the trend + RSI divergence | 43 | 30% | −0.09 | 33 | 41% | +0.25 | −0.34 ± 0.21 | −0.71 .. +0.11 | 28 of 30 | +0.25 / +0.24 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 282 | 33% | −0.05 | 265 | 33% | −0.04 | −0.01 ± 0.08 | −0.17 .. +0.16 | 13 of 30 | −0.08 / +0.05 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 292 | 27% | −0.21 | 249 | 32% | −0.05 | −0.16 ± 0.06 | −0.28 .. −0.03 | 29 of 30 | −0.05 / −0.05 |
| a.fresh: Bounce with the trend + first touch of the level | 396 | 26% | −0.22 | 362 | 32% | −0.04 | −0.17 ± 0.07 | −0.31 .. −0.02 | 30 of 30 | −0.06 / −0.01 |
| a.tested: Bounce with the trend + level touched before | 226 | 31% | −0.09 | 234 | 30% | −0.10 | +0.01 ± 0.08 | −0.13 .. +0.16 | 12 of 30 | −0.12 / −0.07 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 818 | 27% | −0.21 | 820 | 31% | −0.07 | −0.14 ± 0.05 | −0.23 .. −0.05 | 30 of 30 | −0.06 / −0.07 |
| b2.div: Bounce, any trend + RSI divergence | 99 | 24% | −0.27 | 92 | 32% | −0.05 | −0.22 ± 0.14 | −0.48 .. +0.07 | 30 of 30 | −0.02 / −0.07 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 539 | 28% | −0.18 | 568 | 31% | −0.09 | −0.09 ± 0.06 | −0.20 .. +0.05 | 30 of 30 | −0.09 / −0.09 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 729 | 26% | −0.22 | 666 | 31% | −0.07 | −0.15 ± 0.05 | −0.24 .. −0.06 | 30 of 30 | −0.07 / −0.07 |
| b2.fresh: Bounce, any trend + first touch of the level | 820 | 27% | −0.21 | 791 | 32% | −0.04 | −0.17 ± 0.05 | −0.26 .. −0.07 | 30 of 30 | −0.04 / −0.03 |
| b2.tested: Bounce, any trend + level touched before | 572 | 27% | −0.19 | 590 | 30% | −0.10 | −0.10 ± 0.04 | −0.19 .. −0.01 | 30 of 30 | −0.12 / −0.07 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 726 | 28% | −0.18 | 763 | 31% | −0.06 | −0.11 ± 0.05 | −0.22 .. −0.01 | 30 of 30 | −0.08 / −0.04 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 410 | 23% | −0.30 | 396 | 32% | −0.06 | −0.25 ± 0.06 | −0.36 .. −0.13 | 30 of 30 | −0.07 / −0.05 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 191 | 30% | −0.09 | 173 | 31% | −0.06 | −0.02 ± 0.10 | −0.23 .. +0.18 | 18 of 30 | −0.08 / −0.06 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 385 | 38% | +0.11 | 442 | 32% | −0.08 | +0.19 ± 0.07 | +0.04 .. +0.34 | 0 of 30 | −0.08 / −0.07 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 189 | 34% | −0.02 | 201 | 33% | −0.03 | +0.01 ± 0.10 | −0.18 .. +0.21 | 13 of 30 | +0.00 / −0.08 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 69 | 36% | +0.08 | 83 | 36% | +0.06 | +0.01 ± 0.19 | −0.35 .. +0.37 | 13 of 30 | +0.16 / −0.02 |

### BTC, CONFIRM

| Rule | Trades | Risk per trade $ (1R) | Win | Avg win $ | Avg loss $ | Expectancy $ ± SE | Expectancy R ± SE | Spread paid, R | $ per quarter | Worst losing run: trades ($) | Exit by stop / target / time, % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 497 | 4.15 | 30% | +8.46 | −4.09 | −0.36 ± 0.22 | −0.11 ± 0.05 | 0.08 | −31 | 14 (−58) | 70 / 29 / 0 |
| b1: Bounce against the trend | 552 | 4.04 | 27% | +8.53 | −3.93 | −0.55 ± 0.31 | −0.19 ± 0.06 | 0.09 | −53 | 26 (−120) | 73 / 27 / 0 |
| b2: Bounce, any trend | 1036 | 4.09 | 29% | +8.51 | −4.00 | −0.43 ± 0.19 | −0.15 ± 0.04 | 0.08 | −79 | 17 (−84) | 71 / 28 / 0 |
| c: Break and retest | 459 | 4.30 | 32% | +8.41 | −4.34 | −0.23 ± 0.31 | −0.03 ± 0.06 | 0.08 | −18 | 14 (−63) | 68 / 32 / 0 |
| c+: Break and retest, with the trend | 289 | 4.34 | 31% | +8.22 | −4.44 | −0.54 ± 0.37 | −0.08 ± 0.07 | 0.08 | −28 | 14 (−57) | 69 / 31 / 0 |
| d: Breakout on the H1 close | 470 | 6.02 | 32% | +10.79 | −6.16 | −0.79 ± 0.36 | −0.06 ± 0.06 | 0.06 | −65 | 12 (−84) | 68 / 30 / 2 |
| d+: Breakout on the H1 close, with the trend | 252 | 5.95 | 34% | +10.45 | −6.11 | −0.53 ± 0.53 | −0.00 ± 0.08 | 0.06 | −24 | 16 (−121) | 65 / 32 / 2 |
| e: Range fade (H4 flat) | 323 | 3.85 | 28% | +8.58 | −3.65 | −0.20 ± 0.34 | −0.16 ± 0.07 | 0.09 | −12 | 15 (−55) | 72 / 28 / 0 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 347 | 4.21 | 30% | +8.71 | −4.11 | −0.23 ± 0.28 | −0.10 ± 0.07 | 0.08 | −14 | 12 (−52) | 70 / 30 / 1 |
| a.div: Bounce with the trend + RSI divergence | 52 | 4.40 | 38% | +8.28 | −4.57 | +0.37 ± 0.90 | +0.15 ± 0.19 | 0.08 | +3 | 5 (−28) | 62 / 38 / 0 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 260 | 5.91 | 30% | +11.15 | −5.86 | −0.69 ± 0.54 | −0.13 ± 0.08 | 0.06 | −32 | 11 (−70) | 70 / 27 / 3 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 255 | 4.27 | 30% | +8.74 | −4.18 | −0.28 ± 0.33 | −0.10 ± 0.08 | 0.08 | −13 | 13 (−59) | 70 / 30 / 0 |
| a.fresh: Bounce with the trend + first touch of the level | 356 | 4.18 | 29% | +8.56 | −4.14 | −0.43 ± 0.31 | −0.12 ± 0.06 | 0.08 | −27 | 13 (−55) | 71 / 29 / 0 |
| a.tested: Bounce with the trend + level touched before | 223 | 4.10 | 28% | +7.97 | −4.08 | −0.73 ± 0.32 | −0.17 ± 0.07 | 0.08 | −29 | 13 (−57) | 72 / 27 / 1 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 743 | 4.09 | 29% | +8.49 | −4.00 | −0.34 ± 0.24 | −0.12 ± 0.05 | 0.08 | −45 | 19 (−70) | 71 / 29 / 0 |
| b2.div: Bounce, any trend + RSI divergence | 106 | 4.37 | 32% | +9.31 | −4.23 | +0.11 ± 0.71 | −0.04 ± 0.12 | 0.08 | +2 | 7 (−25) | 68 / 32 / 0 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 508 | 5.95 | 32% | +11.41 | −5.80 | −0.24 ± 0.39 | −0.06 ± 0.05 | 0.06 | −22 | 11 (−85) | 67 / 30 / 3 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 610 | 4.09 | 30% | +8.44 | −4.01 | −0.34 ± 0.24 | −0.12 ± 0.05 | 0.08 | −36 | 15 (−77) | 70 / 29 / 0 |
| b2.fresh: Bounce, any trend + first touch of the level | 723 | 4.16 | 29% | +8.53 | −4.10 | −0.42 ± 0.23 | −0.13 ± 0.05 | 0.08 | −53 | 21 (−70) | 71 / 29 / 0 |
| b2.tested: Bounce, any trend + level touched before | 493 | 3.94 | 25% | +8.25 | −3.85 | −0.85 ± 0.27 | −0.26 ± 0.06 | 0.09 | −74 | 19 (−74) | 75 / 24 / 1 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 627 | 4.05 | 27% | +8.37 | −3.98 | −0.63 ± 0.24 | −0.19 ± 0.05 | 0.09 | −70 | 16 (−43) | 73 / 27 / 0 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 372 | 4.06 | 30% | +8.25 | −4.01 | −0.28 ± 0.26 | −0.09 ± 0.07 | 0.08 | −19 | 13 (−54) | 70 / 30 / 0 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 149 | 4.22 | 25% | +9.32 | −4.07 | −0.74 ± 0.45 | −0.26 ± 0.09 | 0.08 | −20 | 13 (−46) | 75 / 25 / 0 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 337 | 6.11 | 31% | +11.12 | −6.21 | −0.76 ± 0.45 | −0.07 ± 0.07 | 0.06 | −45 | 10 (−53) | 68 / 30 / 2 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 168 | 6.06 | 33% | +10.45 | −6.21 | −0.75 ± 0.64 | −0.05 ± 0.10 | 0.06 | −22 | 10 (−70) | 67 / 30 / 3 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 74 | 6.10 | 39% | +10.84 | −6.54 | +0.27 ± 1.07 | +0.18 ± 0.17 | 0.06 | +4 | 7 (−55) | 61 / 39 / 0 |

Against the placebo levels:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 497 | 30% | −0.11 | 475 | 29% | −0.15 | +0.04 ± 0.06 | −0.08 .. +0.15 | 5 of 30 | −0.15 / −0.14 |
| b1: Bounce against the trend | 552 | 27% | −0.19 | 587 | 30% | −0.11 | −0.08 ± 0.06 | −0.19 .. +0.03 | 28 of 30 | −0.11 / −0.10 |
| b2: Bounce, any trend | 1036 | 29% | −0.15 | 1034 | 29% | −0.12 | −0.02 ± 0.04 | −0.09 .. +0.05 | 20 of 30 | −0.13 / −0.12 |
| c: Break and retest | 459 | 32% | −0.03 | 501 | 33% | −0.01 | −0.02 ± 0.06 | −0.15 .. +0.10 | 21 of 30 | −0.02 / +0.00 |
| c+: Break and retest, with the trend | 289 | 31% | −0.08 | 315 | 33% | −0.00 | −0.07 ± 0.07 | −0.21 .. +0.06 | 27 of 30 | −0.02 / +0.01 |
| d: Breakout on the H1 close | 470 | 32% | −0.06 | 569 | 32% | −0.06 | +0.00 ± 0.05 | −0.10 .. +0.10 | 14 of 30 | −0.09 / −0.02 |
| d+: Breakout on the H1 close, with the trend | 252 | 34% | −0.00 | 310 | 34% | −0.01 | +0.01 ± 0.07 | −0.12 .. +0.16 | 12 of 30 | −0.06 / +0.05 |
| e: Range fade (H4 flat) | 323 | 28% | −0.16 | 318 | 29% | −0.13 | −0.03 ± 0.07 | −0.15 .. +0.12 | 19 of 30 | −0.12 / −0.15 |
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | 347 | 30% | −0.10 | 307 | 30% | −0.12 | +0.02 ± 0.08 | −0.12 .. +0.18 | 9 of 30 | −0.15 / −0.07 |
| a.div: Bounce with the trend + RSI divergence | 52 | 38% | +0.15 | 33 | 32% | −0.03 | +0.19 ± 0.20 | −0.18 .. +0.60 | 5 of 30 | +0.04 / −0.11 |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | 260 | 30% | −0.13 | 250 | 29% | −0.15 | +0.02 ± 0.08 | −0.14 .. +0.19 | 11 of 30 | −0.15 / −0.16 |
| a.src2: Bounce with the trend + zone holds 2 or more sources | 255 | 30% | −0.10 | 212 | 29% | −0.13 | +0.03 ± 0.09 | −0.14 .. +0.22 | 10 of 30 | −0.15 / −0.10 |
| a.fresh: Bounce with the trend + first touch of the level | 356 | 29% | −0.12 | 330 | 29% | −0.14 | +0.01 ± 0.07 | −0.13 .. +0.16 | 15 of 30 | −0.14 / −0.14 |
| a.tested: Bounce with the trend + level touched before | 223 | 28% | −0.17 | 204 | 29% | −0.15 | −0.03 ± 0.09 | −0.19 .. +0.15 | 19 of 30 | −0.14 / −0.15 |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | 743 | 29% | −0.12 | 702 | 30% | −0.10 | −0.03 ± 0.05 | −0.12 .. +0.07 | 23 of 30 | −0.12 / −0.08 |
| b2.div: Bounce, any trend + RSI divergence | 106 | 32% | −0.04 | 88 | 32% | −0.05 | +0.01 ± 0.13 | −0.24 .. +0.26 | 14 of 30 | +0.06 / −0.12 |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | 508 | 32% | −0.06 | 519 | 31% | −0.11 | +0.05 ± 0.06 | −0.07 .. +0.15 | 5 of 30 | −0.12 / −0.10 |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | 610 | 30% | −0.12 | 537 | 30% | −0.12 | +0.00 ± 0.06 | −0.12 .. +0.12 | 16 of 30 | −0.13 / −0.11 |
| b2.fresh: Bounce, any trend + first touch of the level | 723 | 29% | −0.13 | 689 | 30% | −0.11 | −0.02 ± 0.05 | −0.12 .. +0.09 | 19 of 30 | −0.12 / −0.09 |
| b2.tested: Bounce, any trend + level touched before | 493 | 25% | −0.26 | 480 | 29% | −0.15 | −0.11 ± 0.06 | −0.23 .. +0.00 | 29 of 30 | −0.16 / −0.14 |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | 627 | 27% | −0.19 | 645 | 30% | −0.12 | −0.07 ± 0.06 | −0.18 .. +0.05 | 27 of 30 | −0.12 / −0.11 |
| b2.h4: Bounce, any trend, level holds an H4 swing | 372 | 30% | −0.09 | 325 | 29% | −0.13 | +0.03 ± 0.07 | −0.11 .. +0.18 | 11 of 30 | −0.16 / −0.08 |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | 149 | 25% | −0.26 | 165 | 29% | −0.12 | −0.13 ± 0.09 | −0.32 .. +0.04 | 29 of 30 | −0.10 / −0.14 |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | 337 | 31% | −0.07 | 407 | 31% | −0.09 | +0.02 ± 0.07 | −0.12 .. +0.15 | 10 of 30 | −0.11 / −0.05 |
| d.h4: Breakout on the H1 close, level holds an H4 swing | 168 | 33% | −0.05 | 178 | 33% | −0.05 | +0.00 ± 0.10 | −0.19 .. +0.19 | 18 of 30 | −0.01 / −0.10 |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | 74 | 39% | +0.18 | 81 | 34% | +0.01 | +0.16 ± 0.16 | −0.15 .. +0.47 | 2 of 30 | −0.13 / +0.16 |

### The main rules against the plain placebo

The same real trades; the placebo prices are the shift alone, with no draw rejected.

Gold, DEV:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 349 | 32% | −0.06 | 368 | 33% | −0.02 | −0.03 ± 0.07 | −0.17 .. +0.10 | 21 of 30 | −0.02 / −0.02 |
| b1: Bounce against the trend | 416 | 28% | −0.16 | 407 | 30% | −0.12 | −0.04 ± 0.06 | −0.16 .. +0.08 | 22 of 30 | −0.09 / −0.14 |
| b2: Bounce, any trend | 752 | 30% | −0.12 | 757 | 31% | −0.07 | −0.05 ± 0.05 | −0.14 .. +0.04 | 28 of 30 | −0.05 / −0.10 |
| c: Break and retest | 338 | 34% | −0.01 | 340 | 34% | −0.00 | −0.01 ± 0.06 | −0.13 .. +0.12 | 16 of 30 | −0.01 / +0.01 |
| c+: Break and retest, with the trend | 213 | 37% | +0.05 | 200 | 36% | +0.06 | −0.00 ± 0.09 | −0.17 .. +0.17 | 14 of 30 | +0.03 / +0.09 |
| d: Breakout on the H1 close | 378 | 35% | +0.03 | 425 | 36% | +0.02 | +0.01 ± 0.06 | −0.10 .. +0.13 | 14 of 30 | −0.01 / +0.08 |
| d+: Breakout on the H1 close, with the trend | 225 | 38% | +0.13 | 230 | 39% | +0.12 | +0.00 ± 0.09 | −0.16 .. +0.18 | 16 of 30 | +0.05 / +0.22 |
| e: Range fade (H4 flat) | 233 | 33% | −0.03 | 235 | 30% | −0.11 | +0.08 ± 0.11 | −0.15 .. +0.28 | 5 of 30 | −0.07 / −0.15 |

Gold, CONFIRM:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 389 | 30% | −0.12 | 418 | 32% | −0.05 | −0.07 ± 0.06 | −0.19 .. +0.04 | 29 of 30 | −0.04 / −0.07 |
| b1: Bounce against the trend | 448 | 28% | −0.17 | 436 | 28% | −0.15 | −0.02 ± 0.05 | −0.12 .. +0.07 | 18 of 30 | −0.10 / −0.20 |
| b2: Bounce, any trend | 830 | 29% | −0.15 | 836 | 30% | −0.10 | −0.04 ± 0.04 | −0.11 .. +0.03 | 27 of 30 | −0.07 / −0.15 |
| c: Break and retest | 376 | 36% | +0.08 | 384 | 34% | +0.01 | +0.07 ± 0.07 | −0.06 .. +0.20 | 6 of 30 | −0.02 / +0.07 |
| c+: Break and retest, with the trend | 244 | 38% | +0.14 | 234 | 35% | +0.03 | +0.11 ± 0.09 | −0.06 .. +0.30 | 2 of 30 | −0.02 / +0.08 |
| d: Breakout on the H1 close | 412 | 37% | +0.08 | 455 | 36% | +0.06 | +0.03 ± 0.05 | −0.08 .. +0.13 | 13 of 30 | +0.06 / +0.05 |
| d+: Breakout on the H1 close, with the trend | 230 | 42% | +0.23 | 246 | 38% | +0.09 | +0.14 ± 0.08 | −0.00 .. +0.29 | 2 of 30 | +0.08 / +0.11 |
| e: Range fade (H4 flat) | 318 | 31% | −0.08 | 299 | 31% | −0.09 | +0.01 ± 0.07 | −0.13 .. +0.15 | 15 of 30 | −0.05 / −0.13 |

BTC, DEV:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 545 | 28% | −0.18 | 548 | 31% | −0.08 | −0.10 ± 0.04 | −0.18 .. −0.01 | 30 of 30 | −0.09 / −0.08 |
| b1: Bounce against the trend | 671 | 27% | −0.20 | 664 | 32% | −0.06 | −0.14 ± 0.05 | −0.23 .. −0.05 | 30 of 30 | −0.04 / −0.07 |
| b2: Bounce, any trend | 1202 | 27% | −0.19 | 1174 | 31% | −0.07 | −0.12 ± 0.04 | −0.19 .. −0.05 | 30 of 30 | −0.07 / −0.07 |
| c: Break and retest | 531 | 32% | −0.05 | 536 | 32% | −0.04 | −0.01 ± 0.05 | −0.12 .. +0.09 | 20 of 30 | −0.06 / −0.01 |
| c+: Break and retest, with the trend | 329 | 30% | −0.13 | 333 | 33% | −0.03 | −0.10 ± 0.07 | −0.24 .. +0.04 | 28 of 30 | −0.05 / −0.00 |
| d: Breakout on the H1 close | 533 | 37% | +0.09 | 601 | 33% | −0.05 | +0.14 ± 0.05 | +0.04 .. +0.24 | 0 of 30 | −0.05 / −0.06 |
| d+: Breakout on the H1 close, with the trend | 304 | 36% | +0.04 | 328 | 34% | −0.01 | +0.05 ± 0.07 | −0.09 .. +0.18 | 6 of 30 | −0.01 / −0.00 |
| e: Range fade (H4 flat) | 356 | 25% | −0.27 | 348 | 29% | −0.14 | −0.13 ± 0.07 | −0.26 .. +0.02 | 29 of 30 | −0.13 / −0.14 |

BTC, CONFIRM:

| Rule | Real trades | Real win | Real R | Placebo trades per set | Placebo win | Placebo R | Real − placebo, R ± SE | 95 % interval | Placebo sets at least as good | Placebo R: price inside the range / beyond the swing |
|---|---|---|---|---|---|---|---|---|---|---|
| a: Bounce with the trend | 497 | 30% | −0.11 | 473 | 29% | −0.13 | +0.01 ± 0.05 | −0.08 .. +0.12 | 10 of 30 | −0.13 / −0.12 |
| b1: Bounce against the trend | 552 | 27% | −0.19 | 544 | 30% | −0.12 | −0.07 ± 0.05 | −0.17 .. +0.03 | 28 of 30 | −0.09 / −0.14 |
| b2: Bounce, any trend | 1036 | 29% | −0.15 | 991 | 29% | −0.12 | −0.02 ± 0.03 | −0.09 .. +0.05 | 21 of 30 | −0.11 / −0.14 |
| c: Break and retest | 459 | 32% | −0.03 | 481 | 33% | −0.01 | −0.02 ± 0.06 | −0.13 .. +0.09 | 17 of 30 | −0.01 / −0.01 |
| c+: Break and retest, with the trend | 289 | 31% | −0.08 | 301 | 32% | −0.04 | −0.03 ± 0.06 | −0.15 .. +0.09 | 21 of 30 | −0.05 / −0.04 |
| d: Breakout on the H1 close | 470 | 32% | −0.06 | 539 | 33% | −0.05 | −0.02 ± 0.05 | −0.11 .. +0.09 | 23 of 30 | −0.07 / +0.00 |
| d+: Breakout on the H1 close, with the trend | 252 | 34% | −0.00 | 286 | 34% | +0.01 | −0.01 ± 0.07 | −0.14 .. +0.14 | 19 of 30 | −0.06 / +0.10 |
| e: Range fade (H4 flat) | 323 | 28% | −0.16 | 304 | 28% | −0.17 | +0.01 ± 0.06 | −0.11 .. +0.14 | 11 of 30 | −0.17 / −0.17 |

### Confirmations and level timeframes, half-year by half-year

R per trade (trades).

Gold:

| Rule | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | 2026H2 |
|---|---|---|---|---|---|---|
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | −0.19 (81) | +0.03 (83) | −0.27 (110) | −0.18 (72) | −0.19 (97) | +0.28 (89) |
| a.div: Bounce with the trend + RSI divergence | +0.33 (8) | −0.33 (9) | −0.20 (15) | −1.00 (8) | +0.29 (7) | +0.80 (10) |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | −0.21 (55) | +0.03 (61) | −0.18 (74) | −0.01 (39) | −0.13 (63) | −0.25 (55) |
| a.src2: Bounce with the trend + zone holds 2 or more sources | −0.16 (61) | +0.02 (69) | −0.14 (76) | −0.30 (47) | −0.19 (71) | +0.17 (64) |
| a.fresh: Bounce with the trend + first touch of the level | −0.06 (85) | −0.02 (96) | −0.30 (117) | −0.18 (72) | −0.12 (90) | +0.18 (99) |
| a.tested: Bounce with the trend + level touched before | −0.11 (44) | +0.00 (57) | −0.15 (58) | +0.07 (28) | −0.28 (58) | −0.19 (52) |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | −0.17 (180) | −0.02 (194) | −0.24 (200) | −0.13 (168) | −0.20 (205) | +0.09 (168) |
| b2.div: Bounce, any trend + RSI divergence | −0.07 (21) | +0.11 (27) | −0.12 (24) | −0.50 (20) | +0.20 (15) | +0.29 (14) |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | −0.19 (117) | −0.05 (127) | −0.09 (145) | −0.13 (92) | −0.07 (126) | −0.20 (108) |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | −0.23 (158) | +0.02 (175) | −0.18 (164) | −0.24 (138) | −0.28 (151) | +0.05 (146) |
| b2.fresh: Bounce, any trend + first touch of the level | −0.05 (180) | −0.09 (208) | −0.18 (226) | −0.17 (176) | −0.13 (197) | −0.00 (181) |
| b2.tested: Bounce, any trend + level touched before | −0.35 (97) | −0.05 (129) | −0.23 (119) | −0.25 (85) | −0.28 (117) | −0.04 (106) |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | −0.18 (126) | −0.25 (167) | −0.10 (183) | −0.16 (149) | −0.11 (174) | −0.04 (163) |
| b2.h4: Bounce, any trend, level holds an H4 swing | −0.14 (106) | +0.03 (123) | −0.23 (101) | −0.27 (74) | −0.34 (81) | +0.12 (80) |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | −0.46 (39) | +0.02 (44) | −0.44 (43) | −0.16 (32) | −0.35 (43) | −0.23 (31) |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | +0.08 (75) | +0.12 (92) | +0.07 (109) | −0.12 (91) | −0.02 (91) | +0.02 (81) |
| d.h4: Breakout on the H1 close, level holds an H4 swing | +0.22 (49) | −0.07 (59) | −0.01 (51) | −0.35 (44) | +0.38 (50) | −0.26 (37) |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | −0.21 (19) | +0.32 (25) | +0.44 (27) | +0.64 (22) | +0.00 (24) | +0.41 (18) |

BTC:

| Rule | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | 2026H2 |
|---|---|---|---|---|---|---|
| a.rsi: Bounce with the trend + M15 RSI below 35 / above 65 | +0.40 (38) | −0.22 (148) | −0.11 (161) | −0.28 (115) | −0.13 (128) | −0.26 (121) |
| a.div: Bounce with the trend + RSI divergence | −0.40 (5) | +0.38 (24) | +0.04 (23) | +0.07 (14) | +0.36 (11) | −0.50 (18) |
| a.rev: Bounce with the trend + M15 reversal bar as the trigger | +0.10 (29) | −0.24 (104) | −0.09 (127) | −0.05 (90) | +0.17 (108) | −0.33 (84) |
| a.src2: Bounce with the trend + zone holds 2 or more sources | +0.38 (26) | −0.29 (109) | −0.03 (120) | −0.25 (81) | −0.14 (112) | −0.24 (99) |
| a.fresh: Bounce with the trend + first touch of the level | +0.05 (40) | −0.26 (146) | −0.05 (170) | −0.15 (125) | −0.18 (147) | −0.32 (124) |
| a.tested: Bounce with the trend + level touched before | +0.08 (27) | −0.19 (95) | −0.23 (101) | −0.12 (67) | −0.04 (81) | −0.12 (78) |
| b2.rsi: Bounce, any trend + M15 RSI below 35 / above 65 | +0.07 (89) | −0.21 (322) | −0.09 (332) | −0.21 (265) | −0.20 (307) | −0.21 (246) |
| b2.div: Bounce, any trend + RSI divergence | −0.40 (15) | +0.02 (47) | +0.02 (44) | +0.03 (29) | −0.31 (35) | −0.49 (35) |
| b2.rev: Bounce, any trend + M15 reversal bar as the trigger | −0.03 (77) | −0.15 (210) | +0.01 (221) | −0.16 (175) | −0.03 (205) | −0.39 (159) |
| b2.src2: Bounce, any trend + zone holds 2 or more sources | +0.01 (71) | −0.23 (265) | −0.04 (274) | −0.23 (230) | −0.22 (280) | −0.22 (219) |
| b2.fresh: Bounce, any trend + first touch of the level | −0.03 (90) | −0.25 (306) | −0.04 (327) | −0.17 (270) | −0.20 (310) | −0.25 (240) |
| b2.tested: Bounce, any trend + level touched before | −0.18 (65) | −0.30 (216) | −0.26 (212) | −0.20 (187) | −0.27 (201) | −0.10 (184) |
| b2.h1: Bounce, any trend, level from H1 swings / previous day only | +0.01 (83) | −0.28 (272) | −0.15 (272) | −0.18 (231) | −0.18 (271) | −0.17 (224) |
| b2.h4: Bounce, any trend, level holds an H4 swing | −0.21 (38) | −0.15 (169) | +0.00 (165) | −0.32 (147) | −0.30 (146) | −0.29 (117) |
| b2.d1: Bounce, any trend, level holds a D1 swing or a weekly high / low | +0.04 (23) | −0.38 (58) | −0.25 (68) | −0.14 (59) | −0.28 (75) | +0.21 (57) |
| d.h1: Breakout on the H1 close, level from H1 swings / previous day only | −0.19 (49) | −0.06 (145) | −0.05 (143) | +0.03 (120) | +0.08 (152) | +0.24 (113) |
| d.h4: Breakout on the H1 close, level holds an H4 swing | −0.14 (19) | −0.20 (81) | +0.16 (68) | −0.09 (69) | +0.05 (66) | −0.02 (54) |
| d.d1: Breakout on the H1 close, level holds a D1 swing or a weekly high / low | +0.25 (12) | +0.30 (30) | +0.03 (32) | −0.31 (22) | +0.56 (27) | −0.15 (20) |
