# Swing Profile (BigBeluga): how it was ported, and how the two ports were reconciled

Written 28 Nov 2026, before any rule of study 2 was run for profit or loss. This is for a reader who trades but does
not read Pine Script, TradingView's language. Everything below is about indicator values, event counts and geometry.
No Swing Profile rule has been run and no profit or loss has been computed.

- **The code:** `backtesting/research/tradeiq2_ind_swing.py` (port A, the production module).
- **The second port:** `tests/tradeiq2_oracle_swing.py` (port B, kept as the oracle).
- **The tests:**
  - `tests/test_tradeiq2_ind_swing.py`: the reconciliation;
  - `tests/test_tradeiq2_ind_swing_a.py` and `tests/test_tradeiq2_ind_swing_b.py`: each port's own tests.
- **The rules:** `PREREG.md` section 6.4 (SP-W1 to SP-W3, the filters FD / F2 / LO, the 50% placebo) and claims 11-12
  of section 8, which read the same series.
- **The script:** "Swing Profile [BigBeluga]", Pine v6, CC BY-NC-SA 4.0. It is third-party code. Line numbers (l.)
  refer to the owner's plain-text copy (424 lines). The source is not in this repository.

**The bottom line.**
- Two engineers ported the script without seeing each other's work.
- On the 1H, 4H and 1D bars of XAUUSDm and BTCUSDm, from the study's data start to 2024-06-30, the two ports give
  the same numbers, bit for bit, on every output, every bar and every finished leg. Gold was also run from study 1's
  later start. No tolerance was needed anywhere, not even for BTC's fractional Binance volumes.
- The reconciliation found two mismatches. Neither changes a number on the real bars (section 4).
  - A leg that would need more than 100,000 price bins, Pine's limit on an array. Port B read it as "cannot be
    computed", the way both ports treat the script's other runtime errors. Port A computed up to 1,000,000 bins and
    stopped with an error above that. Port B was right; port A is fixed. Such a leg needs an ATR close to zero, which
    the study's bars never have: no leg there needs more than 111 bins.
  - A difference in the agreed output format: the direction codes were stored as 8-bit integers in port A and 64-bit
    in port B. Both use 8-bit now, like every direction code of the study.
- A third, unreviewed port written earlier to plan the study agrees on every leg and reproduces its own published
  numbers. Its few differences are all explained (section 5).
- Six readings add to the plan. They are proposed for `DEVIATIONS.md` (section 8). Four can change trades in
  2019-2022:
  - the forming leg has no direction when both stored swing points are one outside bar (BTC 1H: 115 bars);
  - a finished leg's side comes from its flip, not from the order of its swing points (one BTC 1H leg);
  - the delta is the script's own bin sum, not each bar's volume counted once (2 legs, 12 trigger-shaped bars);
  - a finished leg with tied POCs keeps the one nearest its flip bar's close (21 legs).

  The other two move at most one level on one bar, or only the last bits of a price.

## 1. What the script computes

All settings are the script's defaults: the swing length of 50 (l.11) is the only input that changes a number. The
ATR(200) and the bin size of half an ATR are constants (l.85). Nothing is tuned.

1. **Direction (l.66-72).**
   - A bar whose high equals the highest high of the last 50 bars (itself included) sets the script's flag
     `isDownMove` to true. The name is confusing: true means "the last extreme was a new high", so the leg that ended
     there was a down leg.
   - A bar whose low equals the lowest low of the last 50 bars sets it to false.
   - On a bar that is both, the low wins, because that line runs second.
2. **Swing points (l.75-82).**
   - A 50-bar high becomes a swing high one bar later, when the next bar's high is strictly lower. Its bar and price
     are stored. Of two equal highs in a row, the later one is stored.
   - Every newer swing high replaces the stored one. Swing lows mirror this.
   - So the script always holds exactly one swing high and one swing low.
3. **Flips (l.90).**
   - A flip is a bar where the flag changes: a new 50-bar high after a new low, or the reverse.
   - At a flip, the leg between the two stored swing points is "finished".
   - A flip to true (a new high) finishes the down leg, drawn orange with ▼. A flip to false (a new low) finishes the
     up leg, drawn lime with ▲.
4. **The volume profile of a leg (l.106-141).**
   - The price range between the two swing prices is cut into bins about half an ATR(200) wide. The ATR is that of
     the bar that computes the profile. The number of bins is rounded down (l.110), so each bin is slightly wider
     than half an ATR.
   - Every bar from the older swing point to the newer one, both included, adds its volume to every bin whose
     midpoint is less than one bin width from the bar's close. That is normally two bins: the bin holding the close
     and its nearer neighbour. The bars after the newer swing point, up to the flip, are not counted.
   - The volume of a green candle is "buy". A red candle's, and a doji's, is "sell".
5. **The point of control (POC, l.144-154).**
   - The POC is the bin with the most volume. The script draws its line at the middle of the bin.
   - When several bins tie, it draws a line for each.
   - The label shows the total, buy and sell volume and the delta, (buy - sell) / total x 100 (l.183-187). These are
     sums over the bins, so most bars are counted twice.
6. **The forming leg (l.200-403).**
   - On the chart's last bar only, the script draws the same profile for the currently stored pair, in white.
   - It changes from bar to bar. The ATR moves the bins, and a newly confirmed swing point moves the leg.
7. **Display only.** Boxes, the polyline, the heat map, the labels, the zigzag and the colours. Also a moving-average
   block (l.408-424), which plots nothing with its default type "None".

**What is known when.**
- A swing point is known one bar after it prints.
- A finished leg's POC and delta are known only at the close of its flip bar. That comes a median of 25-28 bars after
  the leg's newer swing point (90th percentile 48-56). The chart then draws them back over the leg, which makes old
  charts look better than they were. Reading them before the flip bar is look-ahead.
- At the flip, the close is already past that POC, in the new direction, in 66-72% of legs.
- The forming leg's POC can be computed at every bar from the swing points confirmed by then. The ports do that.
- The script has no signals, no alerts and no higher-timeframe requests. On TradingView's live bar the values can
  change until the bar closes. Closed bars never change.

## 2. What was compared, and how

- **The bars.** The study's 1H, 4H and 1D bars (`PREREG.md` section 2), up to 2024-06-30.
  - The M1 bars were read with `external.load_market(symbol, earliest=..., end="2024-07-01")`, so nothing from the
    hold-out was loaded. Study 1's `TMarket.tbars` built them into bars, which is what `tradeiq2_market.load`
    serves.
  - Gold starts on 2016-01-03 (with the 2016 warm-up months) and BTC on 2018-01-01. Gold was also run from
    2017-01-03, study 1's start; those bars are the later part of the same bars.
- **The volume (PREREG 2).**
  - Gold uses its tick volume.
  - BTC uses Binance BTCUSDT spot volume: study 1's hourly klines on our 1H bars, summed for 4H and 1D.
  - An hour without a Binance kline has volume 0. That happens on 61 1H bars and 5 4H bars of 2019-2022. No leg is
    left without volume.
- **The timeframes.** 1H and 4H are the plan's (PREREG 6.4). 1D was compared too, for information only. The plan does
  not use the script on 1D, where it finishes only 12-14 legs in four years.
- **What had to agree.**
  - All 13 per-bar outputs, on every bar: the flag, both stored swing points (bar and price), the flip, and for the
    forming leg its direction, low, high, POC, number of tied bins, delta and total.
  - Decimal numbers bit for bit, with missing values on the same bars. Even 0.0 against -0.0 would count as a
    difference. Yes/no flags and integers exactly, with the same data types.
  - The table of finished legs, one row per flip: bar, side, both swing bars, low, high, POC, every tied level, delta,
    total, 50% level and ATR.
  - The flip and swing-point event tables, with their times.
  - The 2019-2022 counts of section 6, which are recorded in the test.
- **Synthetic bars.**
  - Random inputs on random walks: swing lengths 2-60, ATR lengths 1-80, bin multipliers 0.05-2. The walks include
    prices on a 0.5 grid (which make ties), trending stretches and flat stretches. Volumes are whole ticks,
    Binance-like decimals with empty hours, or gamma-distributed.
  - The defaults on 1,200 bars, cut to 0-260 bars (the warm-up).
  - Degenerate inputs: flat bars (no ATR), zero volume, swing lengths 1 and 2, a tiny bin multiplier, and an ATR
    that decays towards zero over a flat stretch until the bin count passes the array limit.
  - Before the final test, 2,100 random cases (six seeds, each with the degenerate cases) were run in scratch: 900
    before the fix and 1,200 after it. Before the fix the only disagreements were the mismatch of section 4; after it
    there were none.
- **Is the test sharp?** Port B was deliberately misread in memory, one reading at a time, and compared with port A
  on gold 1H, BTC 1H and BTC 4H.
  - Caught on all three: the POC at l.132's midpoint, ties going to the lowest bin, one bin per bar, and the ATR in
    `external.wilder_atr`'s order (the last bits of the ATR at the flips).
  - Caught where the series has such bars: a same-bar forming leg read as "up" (1H only) and the side taken from the
    geometry (BTC 1H only).
  - Caught on BTC only: adding the bars oldest first, and numpy's or compensated sums. On gold they change nothing,
    because tick volumes are whole numbers and every sum is exact.
  - Not caught on any real series: `<=` instead of `<` in the bin test. On the real bars no close ever lies exactly
    one bin width from a bin's midpoint, so the reading cannot change a number there. The hand tests of both ports
    catch it.
  - A rewritten but correct copy of port B was, as it should be, not caught.
- **Arithmetic.** Both ports already did the same operations in the same order, so nothing had to be aligned:
  - volumes added from the newer swing back to the older one, as the loop of l.125 runs;
  - bins summed in index order with plain additions;
  - the bin midpoint and the drawn level computed exactly as written;
  - the ATR as TradingView's reference code (Wilder's average seeded with a plain mean; study 1's verified
    arithmetic).
- **Compiled or not.** Port A gives the same bits with its compiler (numba) switched off.
- **Running it.** The three test files pass together: 93 tests in about 33 s, at a peak of 1.4 GB of memory.

## 3. The Pine readings, with their evidence

Effects are counted on the 2019-2022 Development decision bars (section 6) of the study's 1H and 4H bars. They are
changed events or levels only: counts, never profit or loss. "Trap test" means a hand-computed test of the reading
in both ports.

| # | Item (lines) | Reading used | Evidence | The alternative, and what it would change |
|---|---|---|---|---|
| 1 | The 50-bar high and low (l.66-67) | The one-argument `ta.highest` / `ta.lowest` read the high and the low, the current bar included | Pine's reference for the one-argument form | The close: other events everywhere (trap test) |
| 2 | Their warm-up | Missing for the first 49 bars, so nothing happens before bar 49 | TradingView's built-ins (and PineTS) return na until 50 bars exist | The extreme of the bars so far: only the first 153-299 bars of each series differ (to 2016-03 on gold, 2018-02 on BTC); nothing from 2019 |
| 3 | A bar that is both a new high and a new low (l.69-72) | The low wins: the flag becomes false | l.71 runs after l.69 | The high wins: other flips. Such bars exist: 2 on gold 1H and 6 on BTC 1H in 2019-2022 |
| 4 | Confirming a swing point (l.75, l.80) | One bar late, strict: the next high must be strictly lower; of two equal highs the later is stored | As written | `<=` / `>=`: other swing points (trap test) |
| 5 | Order within a bar (l.69-90) | Flag, then swing points, then ATR, then flip: a swing point confirmed on the flip bar is the finished leg's end | As written | None |
| 6 | The flag's history on bar 0 (l.90) | False (Pine v6 yes/no values are never missing) | Pine v6 rules | Missing: also no flip on bar 0; nothing changes |
| 7 | Number of bins (l.110-111) | Rounded down; bin width = the range / the number of bins | Pine's `int()` truncates | Rounded to nearest: other POCs (trap test) |
| 8 | Bars of a leg (l.113-125) | From the older swing bar to the newer one, both included | As written | Up to the flip bar: other POCs (trap test) |
| 9 | Which bins a bar fills (l.131-141) | Every bin whose midpoint is strictly less than one bin width from the close: two normally, one on a midpoint or in the outer half of an edge bin, none from half a bin outside. A doji is sell | As written | One bin per bar, or a doji as buy: other POCs and deltas (trap tests). `<=`: nothing on our bars |
| 10 | Order of the additions (l.125-136, l.184-187) | Bars from the newer swing back; bins summed in index order, plain additions | The loop's own order; `array.sum`'s method is undocumented, and plain addition is the natural reading | Other orders: the last bits of BTC's totals and deltas, never a sign or a POC. Gold's sums are exact either way |
| 11 | The POC test (l.149, l.153) | "volume / maximum == 1", evaluated as "volume == maximum" | Exact for a positive maximum in IEEE arithmetic | None |
| 12 | The POC's price (l.154 against l.132) | The drawn line's level, (bin low + bin high) / 2 | It is the line the trader sees | l.132's midpoint: the last bits on about a quarter of the bars (at most 7e-12); no touch-and-hold bar changes |
| 13 | Tied POCs (l.153 draws them all) | The tied bin nearest the close of the bar that reads the profile: the bar itself for the forming leg, the flip bar for a finished leg. At an exactly equal distance, the lower bin. Every tied level is kept | PREREG 6.4 and the spec | The lowest bin: 4 / 9 / 1 legs differ (gold 1H, BTC 1H, BTC 4H). An exactly equal distance never occurs |
| 14 | Delta and total (l.183-187) | The bins' sums, as the label shows them; the delta as a fraction, not x100 | The script's own numbers | Each bar's volume once: another sign on 1 gold 1H leg and 1 BTC 4H leg; another FD verdict on 10 gold 1H and 2 BTC 1H trigger-shaped forming bars |
| 15 | The ATR (l.85) | `ta.atr(200)` as TradingView's reference code; a finished leg uses its flip bar's ATR, the forming leg its own bar's | Reference `pine_atr`; study 1 | `external.wilder_atr`'s order: last bits only, never a bin count. The swing bar's ATR: other POCs (trap test) |
| 16 | Legs that cannot be profiled (l.110-149) | No ATR yet, a swing point missing, 0 bins or more than 100,000: no POC, delta or total, but the leg keeps its row and the run goes on | These are runtime errors in Pine; there is no value to copy | Nothing from 2019. The last such legs: gold 2016-03-14 (4H), BTC 2018-02-14 (4H) |
| 17 | A leg whose bins hold no volume (l.149) | No POC, total 0, no delta | 0 / 0 is missing in Pine | Never on our bars |
| 18 | A finished leg's side (l.99, l.181) | From the flip: a flip to a new low finishes the up leg, even when the stored pair runs the other way | The script's colour and arrow | From the swing points' order: 1 BTC 1H leg in 2019-2022 (2022-09-21), 1 more in 2023 |
| 19 | The forming leg's direction (the script has none) | Up when the stored swing high is on a later bar than the stored swing low, down when earlier, none when both are one outside bar | The spec's definition for W1; with one bar neither is newer | "Up" or "down" there: 34 / 15 long / short trigger-shaped bars on BTC 1H, 2 / 6 on gold 1H |
| 20 | The forming leg at every bar (l.200-403, last bar only) | Every closed bar, as if it were the chart's last bar | PREREG 6.4 | TradingView's tick-by-tick updates of the live bar: not modelled |
| 21 | `calc_bars_count = 2000` (l.6) | Not copied: the script runs on the whole history from the data start | PREREG 3: indicators see the history before each window | The ATR seeded 2,000 bars before each bar: at most 1.6e-4 apart; another bin count on 2 / 3 / 10 / 5 bars (gold 1H / 4H, BTC 1H / 4H), never a flip bar; one trigger-shaped bar's POC moves |
| 22 | `max_bars_back = 5000` (l.6) | No limit | None needed | Never reached: the deepest look-back is 475 bars |
| 23 | Prices and volume | The bid; gold tick volume; BTC Binance volume | PREREG 2 | Exness tick volume for BTC: another POC on 154 of 458 1H legs and 34 of 108 4H legs, another delta sign on 35 / 6 |

## 4. Mismatches found, and how each was resolved

**Mismatch 1: a leg that needs more than 100,000 bins (l.110, l.117).**
- **What the script does.** The number of bins sizes three arrays (`array.new<float>(binCount, 0.)`). Pine limits an
  array to 100,000 elements, so a larger number stops the script with a runtime error. A leg with 0 bins stops it
  too (a division by zero, then a loop from 0 to -1). In both cases there is no Pine value to copy.
- **Port B** read such a leg as "cannot be computed": no POC, delta or total, no ties, the row kept, the run going
  on. That is how both ports treat the script's other runtime errors.
- **Port A** computed up to 1,000,000 bins and stopped with an error above that. The 1,000,000 was its own guard,
  not the script's.
- **Who was right.** Port B: the limit is Pine's, and it treats the leg like the other errors.
- **When it can happen.** Only with an ATR close to zero. For example, an ATR(3) that loses a third of its value on
  every bar of a long flat stretch. Random synthetic inputs found it (3 of the first 900 cases, plus a case built with
  a tiny bin multiplier). The study's bars never come near: the most bins any forming or finished leg needs is 111
  (BTC 1H), and port A's old guard was never hit.
- **The fix.** Port A now tests the bin count against 100,000 before converting it (`_n_bins`, `PINE_ARRAY_MAX`).
  An infinite count (a bin size of about 1e-323) is "cannot be computed" too.
  - Port A's own transcription in its tests got the same limit. It also got a guard for an ATR of exactly 0, which
    had made it divide by zero.
  - Port A's tests gained a hand test: exactly 100,000 bins are computed, 100,001 are not, nor is the smallest
    possible bin size, nor a forming leg of 786,432 bins.
- **Port B's own small fix.** That same infinite count made port B stop with an `OverflowError`. It now reads it as
  "cannot be computed" (`_bin_count`), with a test.
- **The reconciliation test.** A hand-made path (swing length 3, ATR length 1) whose bar 8 has a true range of 2^-17
  (786,432 bins: old port A computed them) or 2^-20 (6,291,456 bins: old port A stopped). Both ports now give no POC
  on that bar and agree on every bar. The limit itself is checked on both ports' single-leg functions.
- **Effect on the study:** none.

**Mismatch 2: the type of the direction codes (the agreed format, not Pine).**
- `f_dir` (the forming leg's direction) and `legs.dir` (a finished leg's side) were 8-bit integers in port A and
  64-bit in port B.
- Both are 8-bit now. That is the type of every direction code of the study: the ribbon's trend and flip, the Heikin
  Ashi direction, the ORB's active direction, the coil's breakout, the dashboard's label.
- Port B, its tests and its independent numpy check were changed. No value changed.

**No other mismatch.** Before and after the fixes, every value was equal bit for bit on all six real series and on
gold's three series from 2017. None of the arithmetic needed aligning.

**Differences that are not mismatches.**
- Port B's `KEYS` lists the 13 per-bar outputs, port A's the 14 returned keys (with `legs`). The returned outputs have
  the same keys in the same order.
- Both ports refuse the same bad inputs. Neither enforces the script's minimum swing length of 10, because the hand
  tests use 3.
- Each port has extras the other lacks. Port A has the swing logic on its own (`swings`) and a single-leg function
  that returns the bins. Port B has a switch to recompute every bar without its cache, which gives identical results.

**Corrections to the two ports' notes** (measured again here; port A's docstring is updated):
- **The gold start.** Port A quoted look-backs and dates for study 1's gold start (2017). The study's gold bars start
  in 2016, so: the deepest gold 1H look-back is 452 bars (430 from 2017), and the last gold 4H leg without a profile
  is from 2016-03-14 (2017-02-02 from 2017).
- **The bin range.** Port A's "8-82 bins" (gold 1H) is the range of the finished legs of 2019-2022. Forming legs
  reach 98 bins there, and 111 on BTC 1H, the most of any leg of the study's bars.
- **Windows.** Port A counted bars closing in (2019-01-01, 2023-01-01]. Port B counted bars opening from 2019-01-01 and
  closing by 2023-01-01. The harness's Development decision bars also require the fill before 2023-01-01. That drops
  gold's last 2022 bar, a Friday close filled on 2 January: gold 1H has 23,590 bars here against 23,591 in both
  reports. No other count changes.
- **Leg length.** Port A's median of 58 bars is the distance between the two swing bars. Port B's 59, used here, is
  the number of bars in the leg, both swing bars included.

## 5. A third opinion: the planning pass's probe

The study's specification was written with a quick, unreviewed probe (`study2/work/probe_swing_ha.py`, outside the
repository). It was only read: its function definitions were run, its main loop was not, and nothing of it was
imported into the repository.

- **Its own setup.** Study 1's bars (gold from 2017), tick volume on both symbols, and legs whose flip bar opens
  between 2019-01-01 and 2024-06-30.
- **Its published numbers come out exactly** (the spec's section 3.2):

| | Gold 1H | Gold 4H | Gold 1D | BTC 1H | BTC 4H | BTC 1D |
|---|---|---|---|---|---|---|
| Legs a year | 77.2 | 21.3 | 2.6 | 117.0 | 26.9 | 4.7 |
| Newer swing to flip, bars: median (90th percentile) | 27 (52) | 25 (50) | 32 (61) | 26 (57) | 28 (52) | 26 (58) |
| Close already past the POC at the flip | 66% | 64% | 43% | 67% | 68% | 46% |
| Median bins | 20 | 21 | 29 | 19 | 20 | 18 |
| Legs with a POC tie | 2.4% | 0.9% | 7.1% | 1.1% | 0.7% | 0% |

- **Leg by leg**, on the same bars and volume, against the ports: the same flip bars, the same swing bars, the same
  side, the same number of bins and of tied bins on every leg of all six series. The deltas are the same bit for bit.
- **The differences, each explained.**
  1. **The POC's price.** The probe takes l.132's bin midpoint; the ports take the drawn line's level (l.154). They
     differ in the last bits on about a quarter of the legs: at most 4.5e-13 on gold and 1.5e-11 on BTC.
  2. **Ties.** The probe takes the lowest tied bin. The ports take the one nearest the flip bar's close, as PREREG
     6.4 says. They differ by a whole bin on 6 / 1 / 1 gold legs and 7 / 0 / 0 BTC legs (1H / 4H / 1D, its window).
  3. **BTC's volume.** The probe uses Exness tick volume; the study uses Binance's (PREREG 2). On 2019-2022 Binance
     volume gives another POC on 154 of 458 BTC 1H legs and 34 of 108 4H legs, and another delta sign on 35 and 6.
     The flips and swing points do not depend on volume.
  4. **Arithmetic.** The probe's ATR adds in another order and differs from the ports' by at most 5.3e-15 relative.
     It never changes a bin count. Its sums run oldest bar first, through numpy. With tick volume (whole numbers)
     they are identical; with Binance volume its deltas differ by at most 3.7e-16, never in sign.
  5. **Legs without a profile.** The probe drops them; the ports keep a row. There are none from 2019.
- **The study's setup** (gold from 2016, Binance volume for BTC, the Development decision bars): the probe's function
  gives the same legs as the ports, and the counts of section 6.

## 6. Event counts per symbol and timeframe, 2019-2022

**The data.**
- The study's bars; values from port A and port B, which are identical.
- The window is the harness's Development decision bars: a bar counts if it closes after 2019-01-01 00:00 UTC and
  its fill (the first M1 bar at or after its close) comes before 2023-01-01 00:00. That is `tradeiq_market.run`'s
  rule.
- Counts and geometry only: no rule was run and no profit or loss was computed.

**The columns.**
- **Flips:** up legs / down legs finished.
- **Ties:** finished legs with a POC tie; in brackets those where the tie nearest the flip close is not the lowest.
- **Bins:** median (smallest - largest) over the finished legs.
- **Leg bars:** bars from the older to the newer swing point, both included: median / largest.
- **Delay:** bars from the newer swing point to the flip: median / 90th percentile.
- **Past POC:** flips whose close is already past the finished leg's POC in the new direction.
- **No direction:** forming bars whose two stored swing points are one bar (episodes in brackets).
- **Touch and hold:** bars with W1's shape on the forming POC, before W1's one-trade-per-anchor rule or any filter:
  long = leg up, low <= POC < close; short = leg down, high >= POC > close. In brackets the number of distinct swing
  lows (long) or highs (short) they belong to.

| Series | Bars | Flips | Legs a year | Swing highs / lows | Ties | Bins | Leg bars | Delay | Past POC | No direction | Forming bars with a tie | Touch and hold: long / short |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold 1H | 23,590 | 159 / 159 | 79.5 | 863 / 658 | 7 (4) | 20 (8-82) | 59 / 348 | 27 / 51 | 66% (211) | 46 (2) | 612 | 592 (112) / 491 (115) |
| Gold 4H | 6,385 | 44 / 44 | 22.0 | 250 / 163 | 0 | 20 (8-70) | 50.5 / 317 | 25 / 48 | 66% (58) | 0 | 5 | 158 (32) / 126 (30) |
| BTC 1H | 35,016 | 229 / 229 | 114.5 | 1,121 / 910 | 13 (9) | 19 (6-73) | 59 / 406 | 27 / 56 | 72% (329) | 115 (4) | 1,204 | 977 (162) / 869 (164) |
| BTC 4H | 8,756 | 54 / 54 | 27.0 | 343 / 220 | 1 (1) | 19 (6-69) | 56 / 377 | 28 / 56 | 69% (74) | 0 | 137 | 209 (35) / 191 (39) |
| Gold 1D (information) | 1,031 | 6 / 6 | 3.0 | 37 / 23 | 1 (1) | 29 (13-47) | 86.5 / 151 | 36 / 65 | 33% (4) | 0 | 11 | 10 (3) / 15 (3) |
| BTC 1D (information) | 1,459 | 7 / 7 | 3.5 | 66 / 31 | 0 | 29 (4-64) | 73 / 397 | 29 / 68 | 36% (5) | 0 | 0 | 4 (1) / 32 (6) |

- **Every bar from 2019 on has a forming POC, and every leg a profile.** Over the whole series to 2024-06-30 there are
  637 / 174 flips on gold 1H / 4H and 741 / 170 on BTC. The legs without a profile are the first few of each
  series: the last ones are gold 1H 2016-01-12 and 4H 2016-03-14, BTC 1H 2018-01-07 and 4H 2018-02-14.
- **Odd legs (BTC 1H only).** All times are bar opens, UTC.
  - Two one-bar legs, whose two swing points are the same outside bar: the flips of 2019-03-15 12:00 (bar
    2019-03-14 14:00) and 2020-08-05 12:00 (bar 2020-08-02 04:00).
  - One leg whose side contradicts the order of its swing points. On 2022-09-21, the 17:00 bar was a new high, a
    flip that finished a down leg. The 18:00 bar, the FOMC hour, was both a new high and a new low. The low wins, so
    it flipped back and finished the same stored pair again, this time as an "up" leg: two rows in a row with the
    same swing points, POC and delta and opposite sides.
  - In Validation (2023-2024H1) there is one more of each: the flips of 2023-09-07 20:00 and 2023-09-24 18:00.
  - None on gold or on 4H.
- **Forming bars without a direction.** On gold 1H, 8 bars after the FOMC hour of 2019-05-01 18:00 and 38 after that
  of 2022-09-21 18:00. On BTC 1H, 22 bars from 2019-03-14, 5 from 2019-12-09, 84 from 2020-08-02 and 4 from
  2022-09-21; in Validation 29 more from 2023-09-06. None on 4H.
- **After a flip, before the new extreme is confirmed,** the stored pair (and so the forming leg) is still the leg the
  flip just finished. On 2.6% of gold 1H bars and 2.2% of BTC 1H bars the forming leg's direction therefore
  disagrees with the script's flag. Touch-and-hold bars in those windows, long / short (on the flip bar itself in
  brackets):

  | Gold 1H | Gold 4H | BTC 1H | BTC 4H |
  |---|---|---|---|
  | 17 (6) / 14 (10) | 7 (5) / 2 (1) | 25 (16) / 25 (17) | 5 (5) / 3 (2) |

- **Volume.** 61 BTC 1H bars and 5 4H bars have no Binance volume (no kline in that hour); no leg is left empty.
- **Gold's start does not matter on 1H and 4H.** With study 1's bars from 2017-01-03, every count above is the same.
  Every per-bar value from 2019 is the same, and on 4H only the ATR at the flip differs in its last bits (56 of the 88
  legs, at most 6.4e-9 relative, the two ATRs equal from 2021-08-25). On 1D, which the plan does not use for this
  script, the 200-day ATR has not settled by 2019: the forming POC differs on 144 bars of 2019-2024H1.
- **1D is thin.** 12 and 14 legs in four years, below the 15-trade minimum, as the spec warned.
- **Limits that are never reached.** The deepest look-back of any profile is 475 bars (BTC 4H), far below the
  script's 5,000. No leg needs more than 111 bins.

## 7. What may still differ from TradingView

1. **The bars and the volume.**
   - TradingView's Exness charts are assumed to show the bid, as PREREG 2 does. Our bars are built from Exness's tick
     archive on UTC boundaries. TradingView's 4H bars for a broker symbol may follow another session, and its feed
     may differ tick by tick. So a 50-bar extreme, and with it a swing point or a flip, can fall on another bar.
   - TradingView's volume on these symbols is its own feed's tick count. For BTC the study uses Binance's volume by
     design (PREREG 2), so a TradingView user on BTCUSDm sees other POCs and deltas: 154 of 458 1H legs would have
     another POC with Exness's tick volume (section 5).
2. **The history the script runs on.** TradingView runs this script on the chart's last 2,000 bars only
   (`calc_bars_count`), so its ATR(200) is seeded there and moves as the chart grows. The ports run on the whole
   history. On 2019-2022 that changes the forming POC on 2-10 bars per series, never a flip and never a delta's sign.
   Only one of those bars has a touch-and-hold shape: the gold 4H bar opening 2019-04-02 12:00 UTC, a short under both
   readings.
3. **The built-in functions.**
   - `ta.atr` is native code on TradingView; the ports follow TradingView's published reference code.
   - How `array.sum` and `math.avg` round is not documented. Plain sequential sums and (a + b) / 2 are assumed.
   - Any difference would be in the last bits. On gold every sum is exact anyway (whole tick counts). On BTC the
     order of the additions never changed a sign or a POC (section 3, item 10).
4. **The live bar.** TradingView recomputes the forming leg on every tick, so its POC can move before the bar closes.
   Closed bars never change, and the study uses closed bars only.
5. **The forming leg** is drawn on the chart's last bar only. The study reads it at every bar, as a chart ending at
   that bar would show it. That is the script's own value for such a chart.
6. **Ties.** The script draws a line for every tied bin. Choosing one is the plan's rule (PREREG 6.4), not the
   script's.
7. **Legs TradingView cannot draw.** With no ATR yet, a swing point missing, 0 bins or more than 100,000, the script
   would stop with an error. The ports leave that leg without a profile and go on. This happens only in the first
   weeks of each series.

## 8. Readings that add to the plan (proposed entries for `DEVIATIONS.md`)

They are written before any Swing Profile result exists. They read the plan where it is silent; none changes a rule
as written. They can move the rows named. Counts are of the 2019-2022 Development decision bars unless stated.

1. **SP-W1 / SP-W2: "while the forming leg is up".**
   - **What.** The forming leg is up when its stored swing high is on a later bar than its stored swing low
     (`f_dir` +1), and down when earlier (-1). That is the spec's definition (3.5). When both stored swing points are
     the same bar, the leg has no direction (`f_dir` 0) and W1 / W2 do not trigger. That happens after an outside bar
     that was both the 50-bar high and the 50-bar low and was confirmed on both sides by the next bar.
   - **Why.** With one bar, neither swing point is newer, so "the leg's swing low" (W1's stop) and "its swing high"
     (W1's target) are not defined.
   - **Also.** On a flip bar, and until the new extreme is confirmed (usually one bar later), the stored pair is still
     the leg the flip just finished, and `f_dir` shows that leg. That is the script's own forming leg on those bars.
   - **Affects.** W1 and W2, with every filter, and their placebo.
     - No direction (1H only): gold 1H 46 bars (2 episodes, after the FOMC hours of 2019-05-01 and 2022-09-21), BTC
       1H 115 bars (4 episodes), and 29 more BTC 1H bars in Validation. On them 2 / 6 (gold) and 34 / 15 (BTC) bars
       have the long / short touch-and-hold shape that a direction would make triggers.
     - The windows after a flip: 17 / 14 long / short trigger-shaped bars on gold 1H, 7 / 2 on gold 4H, 25 / 25 on
       BTC 1H and 5 / 3 on BTC 4H (6 / 10, 5 / 1, 16 / 17 and 5 / 2 on the flip bar itself). A rule that also required
       the script's flag to agree would drop them.
2. **A finished leg's side (SP-W3, claim 12).**
   - **What.** A finished leg's side is that of its flip: a flip to a new 50-bar low finishes the up leg (+1), a flip
     to a new high the down leg (-1). That holds even when the stored swing points run the other way. Its swing bars
     are the older and the newer stored point.
   - **Why.** The flip is what the script colours and labels (l.99, l.181). The two disagree only when the flip bar
     is itself both a new high and a new low. Then the stored pair is still the previous leg's, and two rows in a row
     can share one pair, POC and delta with opposite sides.
   - **Affects.** W3 (which way "the new direction" points after those flips, and the one-trade-per-anchor bookkeeping
     when two rows share an anchor) and claim 12 (which legs count as up legs), on BTC 1H only:
     - 1 leg in Development against its geometry: the FOMC hour of 2022-09-21 18:00, which re-finishes the pair the
       17:00 flip had finished. 1 more in Validation (2023-09-24 18:00).
     - 2 one-bar legs in Development, whose profile is a single outside bar (2019-03-15 12:00, 2020-08-05 12:00), and
       1 more in Validation (2023-09-07 20:00).
3. **The delta and the total (FD, claim 12).**
   - **What.** A leg's delta is the script's (l.183-187): (buy - sell) / total, summed over the volume bins. A bar's
     volume counts in every bin it lands in (usually two). The ports return it as a fraction; the label shows it
     x100.
   - **Why.** It is the number the script's label shows, which is what the video's "a leg up with weak buying" reads.
   - **The alternative.** Each bar's volume counted once over the leg's bars.
   - **Affects.** FD rows and claim 12. With the alternative, the sign changes on 1 gold 1H finished leg (a down leg,
     flip of 2019-12-19 17:00) and 1 BTC 4H leg (an up leg, flip of 2021-09-20 08:00). FD's verdict changes on 10 of
     1,083 gold 1H and 2 of 1,846 BTC 1H trigger-shaped forming bars. Nothing changes on gold 4H.
4. **Tied POCs of a finished leg (SP-W3).**
   - **What.** When bins tie at the maximum, a finished leg's POC is the tied level nearest the close of its flip
     bar, and it stays that leg's POC (`legs.poc`). At an exactly equal distance the lower bin is taken. Every tied
     level is kept (`legs.poc_all`). The forming leg's tie is chosen again at every bar, with that bar's close.
   - **Why.** PREREG 6.4 says "nearest the current close". A finished leg's POC first exists at its flip bar, and that
     bar's close is the current close then.
   - **The alternative.** Choose again at every later bar from `legs.poc_all`.
   - **Affects.** W3 on the tied legs: 7 gold 1H, 13 BTC 1H and 1 BTC 4H legs (none on gold 4H). On 4, 9 and 1 of them
     the nearest tied bin is not the lowest. No exactly equal distance occurs in 2019-2024H1.
5. **The history the script runs on (`calc_bars_count = 2000`, l.6).**
   - **What.** The script runs from the first bar of the study's data (gold 2016-01-03, BTC 2018-01-01), so its
     ATR(200), and with it every bin size, is seeded there.
   - **Why.** PREREG 3 lets indicators see the history before each window, and this is the only reading that gives
     every bar one value. TradingView instead runs the script on the chart's last 2,000 bars, which re-seeds the ATR
     2,000 bars before the bar a live user looks at.
   - **Effect.** The ATR differs by at most 1.6e-4 relative. The number of bins, and so the forming POC, changes on
     2 / 3 / 10 / 5 bars (gold 1H / 4H, BTC 1H / 4H). That is never a flip bar and never a delta's sign. One of those
     bars has a touch-and-hold shape under both readings (the gold 4H bar opening 2019-04-02 12:00 UTC, a short), so
     only its POC-based levels move.
   - **Affects.** SP-W2 (the stop at POC + 1.5 ATR and its 2R target) on at most that one gold 4H bar.
6. **The POC's price.**
   - **What.** The POC is the drawn line's level, (bin low + bin high) / 2 (l.146-154). It is not the
     bin-assignment midpoint, bin low + bin width / 2 (l.132).
   - **Why.** It is the line the trader sees.
   - **Effect.** The two differ in the last bits on about a quarter of the bars: at most 4.5e-13 on gold and 7.3e-12
     on BTC. No touch-and-hold shape changes on any Development bar.
   - **Affects.** The W2 / W3 stop and target levels by at most 7.3e-12; no trigger.
