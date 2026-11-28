# Trend Target Ribbon (BOSWaves): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values and event counts. No
ribbon rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_ribbon.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_ribbon.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_ribbon.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_ribbon_a.py` and `tests/test_tradeiq2_ind_ribbon_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.1 (with 6.8-6.10 and claims 1-3 of section 8, which read the same series).
- **The script:** "Trend Target Ribbon [BOSWaves]", Pine v6, MPL-2.0. It is third-party code. Line numbers (L...)
  refer to the owner's copy. The source is not in this repository.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- On the 1H, 4H and 1D bars of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports give
  the same numbers, bit for bit, on every output and every bar. Gold was also run from study 1's later start.
  No tolerance was needed anywhere.
- The reconciliation found one mismatch. It was in port A and is fixed. It can only appear with inputs other than the
  script's defaults, so it changes no number in this study (section 4).
- A third, unreviewed port written earlier to plan the study agrees on every flip and every stop (section 5).
- The registered stop (the "intended" one) is settled. The stop TradingView literally draws (row RIB-LIT, a
  sensitivity row that is never selected) rests on platform rules that can only be checked on TradingView itself.
  Three of these readings add to the plan and are proposed for `DEVIATIONS.md` (section 8).

## 1. What the script computes

All settings are the script's defaults (L14-39); nothing is tuned.

1. **The average (L88).** An ALMA of the close: length 34, offset 0.85, sigma 6.
   - It behaves like a bell-shaped (Gaussian) average over about the last 20 bars. Its peak weight sits 5 bars back,
     and 75% of the weight is on the last 10 bars.
   - On a steady trend it lags the price by 6.66 bars.
2. **The band (L89, L94-95).** The ALMA plus and minus 0.65 times the 34-bar standard deviation of the close.
3. **The slope (L90, L92).** The ALMA's change over 3 bars, divided by the ATR(14).
4. **Setups (L97-98).**
   - A bull setup is a bar whose slope is above 0.08 and whose close is above the upper band.
   - A bear setup is the mirror: slope below -0.08 and the close below the lower band.
   - Both conditions must hold on the same bar.
5. **Trend and flips (L100-110).**
   - The trend is the side of the most recent setup.
   - A **flip** is the first setup of the other side. That is the script's signal: a diamond and an alert.
   - Once set, the trend never goes back to "no trend". In particular, a stop-out does not reset it.
6. **The position a flip opens (L310-330, L419-422).**
   - The entry is the flip bar's close.
   - The stop of a long sits below "the lowest low of the last 12 bars" (a short's above the highest high).
   - The stop distance is kept between 0.75 and 3 ATR. That distance is 1R.
   - The four targets at 1R, 2R, 3R and 4R close nothing. They only get a check mark when price touches them
     (L626-631).
7. **Display only.**
   - The conviction (L120-123) sets the brightness: the absolute slope times 2, plus the close's distance from the
     ALMA in ATR times 0.35, capped at 1.
   - The ribbon edge (L125-128) is drawn at the ALMA -/+ 0.55 deviations.
   - Both are returned by the ports, but no registered rule uses them.

**Timing.**
- A flip is known at its bar's close and never changes afterwards. The script has no higher-timeframe requests, no
  pivots and no intrabar tricks.
- On TradingView's live, still-forming bar a flip can appear and vanish before the bar closes. This backtest uses
  closed bars only.

## 2. What was compared, and how

- **The bars.** The study's 1H, 4H and 1D bars (`PREREG.md` section 2), up to 2024-06-30.
  - The M1 bars were read with `external.load_market(symbol, earliest=..., end="2024-07-01")`, so nothing from the
    hold-out was loaded. Study 1's `TMarket.tbars` built them into bars, which is what `tradeiq2_market.load` serves.
  - Gold starts on 2016-01-03 (the 2016 warm-up months) and BTC on 2018-01-01.
  - Gold was also run from 2017-01-03, study 1's start, because the literal stop depends on where the bars start.
    Study 1's gold bars are exactly the later part of the study's bars.
- **What had to agree.**
  - All 15 outputs had to agree on every bar: the ALMA, deviation, ATR, slope, conviction, both ribbon edges, both
    setups, trend, flip, and the intended and literal stop distances of both sides.
  - Decimal numbers were compared bit for bit, with missing values on the same bars. Yes/no flags and integers were
    compared exactly.
  - The flip event table also had to agree: bar, times, side, close, ATR, both stops and conviction.
  - The 2019-2022 counts of section 6 are recorded in the test.
- **Synthetic bars.**
  - 72 random input sets inside the script's input ranges (L16-38), on random walks, walks rounded to whole dollars,
    trending paths and flat stretches with zero true ranges.
  - Five edge input sets: the defaults, every input at its lower bound, upper bounds, a stop floor above the cap, and
    flips before bar 49.
  - Each was also run on series cut to 0-60 bars (the warm-up).
  - Before the final test, 5,300 random input sets were run in scratch: 3,500 inside the script's ranges and 1,800
    outside them (lengths from 1, other multipliers). All of them agreed once the mismatch of section 4 was fixed.
- **Is the test sharp?** It was rerun with port A deliberately broken in memory:
  - the old literal-stop rule;
  - numpy's standard deviation;
  - a floored ALMA offset;
  - the literal stop with both ternary branches run.

  Each one fails it. The last three fail on the real bars as well. One kind of error cannot be caught here, and it
  is harmless: on this machine, with the script's inputs, an ALMA computed as a matrix product gives the same bits as
  the reference loop.
- **Arithmetic.** Both ports follow the order of TradingView's reference code ("same on Pine"), so nothing had to be
  aligned.
  - ALMA: the weights by `math.exp` / `math.pow`, the sum from the oldest bar, one division.
  - Mean and deviation: summed from the newest bar.
  - Wilder update: `alpha * x + (1 - alpha) * previous`.
- **Running it.** All three test files pass together: 90 tests in about 19 s, at a peak of 1.5 GB of memory.

## 3. The Pine readings, with their evidence

The effects are counted on the 2019-2022 Development decision bars (see section 6) of the study's bars. They are
changed flips or stops only: counts, never profit or loss.

| # | Item (lines) | Reading used | Evidence | The alternative, and what it would change |
|---|---|---|---|---|
| 1 | ALMA weight direction (L88) | The heaviest weights fall on recent bars: weight i applies to `close[33 - i]`, so i = 33 is the current bar | TradingView's reference `pine_alma`; lag 6.6607 bars on a ramp (hand tests in both ports) | Reversed weights: lag 26.34 bars; nearly every flip moves |
| 2 | ALMA offset not floored (L88) | m = 0.85 x 33 = 28.05 | `ta.alma`'s `floor` argument defaults to false, and the script passes only four arguments | m = 28: the flip changes on 32 / 14 / 2 bars (gold 1H / 4H / 1D) and 52 / 16 / 6 (BTC) |
| 3 | Deviation (L89) | Population deviation (divide by 34). A deviation of at most 1e-10 counts as 0. The reference's stray "15" is not copied, as in study 1 (its PORTING item 7) | `ta.stdev`'s `biased` defaults to true; reference `pine_stdev` | Sample deviation: the flip changes on 32 / 6 / 0 and 20 / 6 / 0 bars. The "15" slip changes 30 gold 1H and 4 gold 4H deviation values and moves one gold 1H flip by one bar on 2018-09-25; nothing in Development |
| 4 | ATR (L90) | Wilder's RMA seeded with the plain mean of the first 14 true ranges; bar 0's true range is high - low | `pine_atr` / `pine_rma`; PREREG 5 | Seeded with the first true range: from 2019 identical on 5 series, 3e-12 relative on BTC 1D; no flip moves |
| 5 | Slope while the ATR is missing (L92, L120) | 0.0 (the test `atr > 0` is false while the ATR is missing) | Pine: a comparison with na is false | "Missing" instead: only bars 0-12, where no setup is possible |
| 6 | Setup thresholds (L97-98), else-if (L105-110) | Strict `>` and `<`. The two setups cannot both hold, so the order of the tests never matters | As written | `>=` / `<=`: 0 setups change on any bar. The closest margins (section 6) are at least 10 million times wider than rounding |
| 7 | Trend start and memory (L100) | 0 at the first bar, then the side of the latest setup; nothing resets it | `var int trend = 0`; no line writes `trend` after a stop | A reset after a stop is a misreading (a trap test in both ports) |
| 8 | **Stop scope (L281, L315-317)** | **Both readings are computed.** Intended (registered): the lowest low (highest high) of the 12 bars before the flip bar. Literal (RIB-LIT): what TradingView computes when the lookup sits inside `if flip` | The input's tooltip (L33-34, "bars back used to locate swing structure"), the video ("a stop below the last swing low") and PREREG 6.1 for the intended reading; TradingView's warning CW10003 and its "Time series in scopes" page for the literal one | The literal stop equals the intended one on only 34-47% of flips. It sits at the 3-ATR cap on 71-78% (intended: 44-62%) and at the 0.75-ATR floor on 13-22% (intended: 0%) |
| 9 | Literal: what the call remembers | Only the values it was called with: the lows of bull-flip bars for `ta.lowest`, the highs of bear-flip bars for `ta.highest` | CW10003: "a local call stores values only for the bars where it runs"; PREREG 6.1 | Reading the chart's last 12 bars at each call: 43 / 38 / 35% and 44 / 43 / 45% of literal stops change |
| 10 | Literal: `[1]` | The call's result at its previous run (the previous flip of that side). The first flip of each side has none, so it gets 0.75 ATR | CW10003: `[1]` "reaches back to the last execution"; PREREG 6.1 ("a missing raw risk becomes 0.75 ATR") | The previous bar's value, which is always missing: every literal stop becomes 0.75 ATR (87 / 87 / 85% and 85 / 87 / 78% change) |
| 11 | Literal: the ternary (L315-317) | Only the branch taken runs: `ta.lowest` on bull flips, `ta.highest` on bear flips | Pine evaluates only the chosen branch; that is why it warns that such functions "should be called on each calculation" | Both branches run on every flip, so each call sees all flips: 19 / 17 / 21% and 20 / 20 / 24% change |
| 12 | Literal: a call with fewer than 12 values | Missing while the chart's bar index is below 11. From bar 11 on, the extreme of the values it has, even if fewer than 12 | PineTS's `ta.lowest` (it says it follows TradingView since 2026-10-09). Not checkable without TradingView | Missing until 12 values (the first 12 flips of each side get 0.75 ATR): no change on 1H / 4H; 0 of gold's 34 1D stops (4 on study 1's later-starting bars); 8 of BTC's 49 |
| 13 | Literal: where the history starts | The first bar of the study's data (gold 2016-01-03, BTC 2018-01-01) | TradingView's own chart start is unknown | Any gold start from 2016-01 to 2018-01 gives the same 2019-2022 stops (to 1e-9; the ATR's seed leaves smaller differences). A start in 2018-07 changes 4 of 34 gold 1D stops. A BTC start 3 or 6 months later changes 1 or 3 of 49 1D stops. Nothing on 1H / 4H. Flips never change |
| 14 | Clamp (L323-328) | min(max(raw, 0.75 ATR), 3 ATR); a missing or negative raw gives 0.75 ATR | As written | None |
| 15 | Entry and stop anchor (L310, L330) | The ports return the stop as a distance measured from the flip bar's close. The harness fills at the next M1 open and places the stop that distance from the fill | PREREG 4 and 6.1 | The script's absolute level (close - 1R) applied to the fill: other R levels, never other flips |
| 16 | Target check marks (L620-631) | Not counted on the flip bar: the harness counts touches after the fill only | The script runs this check on the entry bar too, on the part of the bar before the close | T1 touched by the flip bar's own wick: 1 / 0 / 0 and 4 / 0 / 0 flips (intended), 17 / 2 / 0 and 27 / 8 / 1 (literal) |
| 17 | The old position on a flip bar (L215-277 before L495-501) | The harness checks the old stop on every M1 bar of the flip bar | The script ends the old position at the flip without checking its stop on that bar | Only the exit reason and price of the old trade change |
| 18 | Source bars | The bid close of the study's bars (UTC boundaries; a short UTC day merged into the next) | PREREG 2 | TradingView's own Exness bars (section 7) |

## 4. Mismatches found, and how each was resolved

**One mismatch: the literal stop's lookup run before bar `stop_lookback - 1` (L281, L315-317).**
- **The rule both ports document.** The literal `ta.lowest(low, stopLookback)` runs only on bull-flip bars. Per
  PineTS's account of TradingView, it returns nothing (na) while the chart's bar index is below `stopLookback - 1`
  (bar 11 with the default lookback of 12), and from that bar on the lowest of the values it has seen. The next
  flip's `[1]` reads that result. So if a flip comes before that bar, the next flip of that side finds no structure
  level and gets 0.75 ATR. `ta.highest` on bear flips works the same way.
- **Port B** applied this rule.
- **Port A** applied only its second half. It took the lowest of the values seen even when the call had run before
  bar `stop_lookback - 1`.
- **Who was right.** Port B. Port A's own docstring cited the full rule, but its code dropped the bar-index part.
- **Why real bars never showed it.** With the script's defaults the first flip is at bar 36 or later, well past
  bar 11. On real bars the two ports were already equal before the fix.
- **How it was found.** Random synthetic inputs inside the script's ranges, for example ALMA, deviation and ATR of 5
  bars with a 50-bar stop lookback (allowed by L16-33). There a flip can come at bar 10, long before bar 49.
- **The fix.** `_previous_calls` in port A now takes the bars of the calls and leaves an na result for a call before
  bar `stop_lookback - 1`.
- **The tests.**
  - The reconciliation test has a hand-computed case. A zigzag flips at bars 10, 26, 41, 56, 71, 86, 101 and 116.
    The long of bar 71 now gets 0.75 ATR (old port A: 2.25) and the short of bar 56 gets 0.75 ATR (old: 1.25).
  - Port A's tests gained the same case (`trap01c`) and an input set that runs its own transcription through it.
- **Effect on the study:** none. Every input is the script's default.

**No other mismatch.**
- Before and after the fix, every output was equal bit for bit on all six real series and on both gold starts.
- None of the arithmetic needed aligning.

**Differences that are not mismatches (outside the shared contract).**
- **Input checks.** Port A refuses a negative minimum slope (the input's own minimum is 0, L28) and non-finite
  multipliers. Port B takes them as given.
  - With a negative minimum slope both setups could hold on one bar. Port B would then apply the script's else-if
    order, which port A's closed form does not have.
  - Inside the script's input ranges the two always agree.
- **Port B's extras.** Port B also has `script_positions` (the script's own drawing of positions) and switches for
  the alternative readings. Port A does not need them.

**Corrections to the two ports' own notes** (measured again here; port A's docstring is updated):
- **The literal stop and a later start.** Port A said a gold start a year later changes 5 of the 34 1D literal stops.
  Those 5 differ by less than 1e-9 relative, a trace of the ATR's seed. Counted with a 1e-9 tolerance, the number is
  0; at 18 months later it is 4.
- **"Missing until 12 values" on gold 1D.** Both ports said it changes 4 of gold's 34 1D literal stops. That holds on
  study 1's bars, which start in 2017. On the study's bars, which start in 2016, it is 0. BTC's 8 of 49 stands.
- **Windows.** The ports' 2019-2022 counts used slightly different windows (section 6).

## 5. A third opinion: the unreviewed scratch port of the planning pass

A planning pass, before the plan was written, wrote a quick port of the ribbon and counted events with it. That port
and its output are outside the repository and were only read. Its ribbon function was run on the same bars as the two
ports.

- **The same events.**
  - On all six series, and on both gold starts, it gives the same setups, trend and flips on every bar.
  - It gives the same intended and literal stop at every flip.
  - Its ALMA and deviation differ by at most 6e-16 relative, because it sums in another order. Its ATR differs by
    at most 2e-16 relative (its seed is numpy's mean).
- **The same counts.** Its recorded counts were reproduced exactly with its own window. Those fields are bars, flips
  a year, bull flips, the bars-between-flips percentiles, the trend-up share, the setup-bar share, the median raw
  risk, the shares at the cap and the floor (intended and literal), the literal-equals-intended share, the
  conviction p5 and median, and T1 touched on the flip bar.
- **The only differences:**
  - **The window.** The planning pass counted bars closing by 2023-01-01 00:00, and so did port B. The harness
    instead counts a decision in Development only if it fills before 2023-01-01. That drops one bar per series: gold's
    last 2022 bar (a Friday close, filled on 2 January) and BTC's bar closing at exactly 00:00 on 1 January. On BTC 1H
    that bar is a bear flip, so the counts are 636 / 635 here against 636 / 636 there. Port A also dropped the BTC
    bar, but it kept gold's.
  - **Rounding.** BTC 1D has 12.25 flips a year; the planning pass rounded it to 12.2.
- **One sentence of the plan's map is slightly off.** It says at least 25% of flips have their conviction capped
  at 1. That holds on gold. On BTC 1H it is 21.5% and on BTC 1D 18.4%, as port B had noted.
- **Bars between flips.** Port A gave a gold 1D median of 27 because it defined the gaps differently. The median of
  the gaps between flips inside the window is 25, the same as port B's and the planning pass's.

## 6. Event counts per symbol and timeframe, 2019-2022

**The data.**
- The study's bars; values from port A and port B, which are identical.
- The window is the harness's Development decision bars: a bar counts if it closes after 2019-01-01 00:00 UTC and
  its fill (the first M1 bar at or after its close) comes before 2023-01-01 00:00. That is `tradeiq_market.run`'s
  rule.
- Counts only: no rule was run and no profit or loss was computed.

**The columns.**
- **Gaps:** bars between consecutive flips inside the window, p5 / p25 / median / p75 / p95.
- **Conviction:** at the flips, p5 / median / share capped at 1.
- **Raw risk:** the intended stop's distance before the clamp, in ATR (median).
- **Cap / floor:** the share of flips whose stop is at 3 ATR / 0.75 ATR.
- **T1 on the flip bar:** flips whose 1R target the flip bar's own high (low) already reaches. The script would tick
  these; the harness does not count them. Intended / literal.

| Series | Bars | Setup bars (bull / bear) | Flips (bull / bear) | Flips a year | Gaps | Trend up | Conviction | Raw risk (median) | Intended: cap / floor | Literal: cap / floor | Literal = intended | T1 on the flip bar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold 1H | 23,590 | 5,079 / 4,395 | 429 / 429 | 214.5 | 5 / 12 / 20 / 37 / 73.2 | 53.1% | 0.44 / 0.78 / 25.1% | 2.99 ATR | 49.4% / 0% | 78.0% / 12.6% | 39.5% | 1 / 17 |
| Gold 4H | 6,385 | 1,480 / 1,176 | 124 / 124 | 62.0 | 5 / 12 / 20 / 33 / 66.1 | 52.9% | 0.48 / 0.82 / 32.3% | 3.16 ATR | 58.9% / 0% | 77.4% / 13.3% | 46.4% | 0 / 2 |
| Gold 1D | 1,031 | 247 / 174 | 17 / 17 | 8.5 | 4.2 / 14 / 25 / 38 / 65.2 | 54.7% | 0.49 / 0.77 / 26.5% | 3.25 ATR | 61.8% / 0% | 73.5% / 14.7% | 47.1% | 0 / 0 |
| BTC 1H | 35,016 | 6,988 / 6,355 | 636 / 635 | 317.75 | 6 / 13 / 21 / 35 / 70 | 50.9% | 0.41 / 0.71 / 21.5% | 2.87 ATR | 44.5% / 0% | 74.8% / 14.6% | 34.1% | 4 / 27 |
| BTC 4H | 8,756 | 1,844 / 1,574 | 161 / 161 | 80.5 | 6 / 12 / 21 / 34 / 67 | 51.5% | 0.44 / 0.76 / 26.1% | 2.98 ATR | 49.1% / 0% | 75.8% / 13.0% | 37.9% | 0 / 8 |
| BTC 1D | 1,459 | 334 / 236 | 24 / 25 | 12.25 | 6 / 12.75 / 20 / 34.25 / 92 | 53.6% | 0.45 / 0.79 / 18.4% | 3.05 ATR | 51.0% / 0% | 71.4% / 22.4% | 40.8% | 0 / 1 |

- **Warm-up.**
  - The first flips: gold 1H 2016-01-05 12:00 UTC (bar 36), 4H 2016-01-12 12:00, 1D 2016-03-24. BTC 1H 2018-01-02
    13:00, 4H 2018-01-08 08:00, 1D 2018-02-07.
  - From 2019 the trend is never "none" on any series.
  - To 2024-06-30 the series have 1,830 / 494 / 75 flips (gold 1H / 4H / 1D) and 2,055 / 512 / 83 (BTC).
- **The gold start makes no difference from 2019.** With study 1's gold bars (from 2017-01-03), every output is the
  same on every Development bar, the literal stops included. The two starts differ only before 2019: flips until
  2017-01-04 (1H), 2017-01-11 (4H) and 2017-02-24 (1D), and stops until late 2018 on 1D.
- **1D is thin.** Gold has 17 long flips in four years and BTC 24, close to the 15-trade minimum of PREREG 5 for the
  long-only 1D rows.
- **How close the data come to the thresholds** (bar 36 to 2024-06-30):
  - the slope is never closer than 1.07e-5 to -/+0.08 on a bar where the band condition holds (gold 1D);
  - the close is never closer to the band than 1.8e-6 ATR, or 1.2e-8 of the price, on a bar where the slope condition
    holds (BTC 1H).

  Rounding in another order of operations moves these values by about 1e-16 relative. No change of arithmetic can
  therefore move a setup.

## 7. What may still differ from TradingView

1. **The bars themselves.**
   - TradingView's Exness charts are assumed to show the bid, as PREREG 2 does.
   - Our bars are built from Exness's tick archive on UTC boundaries, and a short UTC day is merged into the next.
   - TradingView's 4H and 1D bars for a broker symbol may follow the broker's trading session instead (for example
     a daily bar from 22:00 or 23:00 UTC). Its feed may also differ tick by tick.
   - So a flip can fall on another bar than on a TradingView chart, most likely on 4H and 1D. On 1H the boundaries
     are the same.
2. **The built-in functions.**
   - `ta.alma`, `ta.stdev` and `ta.atr` are native code on TradingView. The ports follow TradingView's published
     reference code instead.
   - Any difference would be in the last bits. Section 6 shows that cannot move a setup on our bars.
3. **The literal stop (RIB-LIT only).** Readings 9-13 of section 3 are TradingView's documented behaviour (CW10003,
   "Time series in scopes") or PineTS's account of it. They cannot be checked without TradingView.
   - Reading 12 matters only on BTC 1D (8 of 49 stops).
   - Readings 9-11 matter on every series.
   - An export of the stop lines TradingView draws on any chart would settle them.
   - The intended stop, the one every eligible row uses, depends on none of this.
4. **The history start.** It affects only the literal stop, and only through the first 12 flips of each side
   (reading 13).
5. **The live bar.** TradingView recomputes the forming bar on every tick, so a flip, and a "once per bar" alert,
   can appear and then vanish before the close. Closed bars never change.
6. **The script's own trade drawing.** These differences are by design. They come from PREREG 4's execution rules,
   not from the port. The script draws:
   - the entry at the flip bar's close; our harness fills at the next M1 open;
   - target check marks from the flip bar's own wick (section 6, last column);
   - the old position ending at a flip without a stop check on that bar; the harness's M1 check can stop it out
     inside the flip bar instead.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

These three concern only RIB-LIT, the sensitivity row, which is never selected. They are written before any RIB-LIT
result exists. Nothing here changes an eligible row: the intended stop, the trend and the flips are exactly as
PREREG 6.1 states them.

1. **RIB-LIT: the literal stop's lookup sees only flips of its own side.**
   - **What.** PREREG 6.1 says that `ta.lowest` inside the flip branch "buffers only the lows of earlier flip bars".
     Port A and port B (reconciled) read this as earlier flip bars of the same side.
   - **How.** L315-317 put `ta.lowest(low, 12)[1]` and `ta.highest(high, 12)[1]` in the two branches of a ternary
     inside `if flip`, and Pine evaluates only the branch taken.
     - `ta.lowest` therefore runs on bull flips only and keeps the lows of bull-flip bars.
     - `ta.highest` runs on bear flips only and keeps the highs of bear-flip bars.
     - `[1]` is the call's previous result (TradingView's CW10003: it "reaches back to the last execution").
     - So the k-th bull flip's level is the lowest low of bull flips k-12 to k-1. The first bull flip has none and
       gets 0.75 ATR. Shorts mirror this.
   - **Why.** It is the only reading consistent with Pine's evaluation rules.
   - **The alternative.** Run both branches on every flip, so that each call sees all flips. That changes 17-24% of
     the 2019-2022 literal stops on every series (gold 1H / 4H / 1D: 161 / 43 / 7 stops; BTC 256 / 66 / 12).
   - **Affects:** the three RIB-LIT rows per symbol only.
2. **RIB-LIT: a lookup with fewer than 12 stored values.**
   - **What.** The plan does not say what the literal lookup returns before it holds 12 values. The ports return
     nothing (na) while the chart's bar index is below 11, and from bar 11 on the lowest (highest) of the values it
     holds, even if fewer than 12.
   - **Why.** That is PineTS's documented account of TradingView's `ta.lowest` / `ta.highest`. It cannot be checked
     without TradingView.
   - **The alternative.** Nothing until 12 values are stored, which gives the first 12 flips of each side 0.75 ATR.
     It changes no 2019-2022 literal stop on 1H or 4H and none on gold 1D (whose first 12 flips of each side come
     before 2019 on the study's bars). It changes 8 of BTC's 49 1D stops.
   - **Affects:** RIB-LIT on BTC 1D.
3. **RIB-LIT: where the chart's history starts.**
   - **What.** The literal stop of the first 12 flips of each side depends on the first bar of the chart. The study
     computes the ribbon from the first bar of the study's data: gold 2016-01-03 (with the 2016 warm-up months) and
     BTC 2018-01-01. TradingView's own chart start is unknown.
   - **Effect, measured on 2019-2022.**
     - Gold: any start from 2016-01 to 2018-01 gives the same stops (to 1e-9); a start in 2018-07 would change 4 of
       34 1D stops.
     - BTC: a start 3 or 6 months later would change 1 or 3 of 49 1D stops.
     - 1H and 4H are unaffected and the flips never change. The intended stop is unaffected too, except that a gold
       start as late as 2018-07 leaves the 1D ATR unsettled in early 2019 (2 of 34 intended stops move by more than
       1e-9 relative).
     - Gold's literal stops before 2019, which the Early window would score, do depend on the start: on 1D they
       differ until late 2018 between the 2016 and 2017 starts.
   - **Affects:** RIB-LIT rows; on BTC 1D early in Development; on gold only in any information-only scoring of the
     Early window.
