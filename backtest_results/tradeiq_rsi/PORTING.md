# How TradeIQ's four indicators were ported from TradingView, and how the port was checked

Written 28 Nov 2026, before any rule of the study was run. This is for a reader who knows trading but not Pine
Script, TradingView's language. It covers four things: what each indicator computes, step by step; the Pine details
that decided the numbers; how two independent ports were compared and reconciled; and what could still differ from
TradingView.

- **The code:** `backtesting/research/tradeiq_ind.py`.
- **The tests:** `tests/test_tradeiq_ind.py`, with the second port kept as the oracle in `tests/tradeiq_oracle.py`.
- **The rules:** the plan is `PREREG.md`. The readings below are logged in `DEVIATIONS.md` (entries 10-18).

**The bottom line.** Two engineers ported the scripts without seeing each other's work. On the 1H, 4H and 1D bars of
XAUUSDm and BTCUSDm, from the data start to the hold-out start, the two ports give the same floating-point numbers,
bit for bit, on every line from the first bar. The single exception is a naming convention on the first six bars,
covered in section 4. The final module equals both. None of the Pine readings that are still uncertain changes any
signal on our bars, except one: the HMA rounding of item 2 in section 3. That one is now fixed in the log, before any
result. Rounding can matter on only five BTC bars of the consolidation score, where the value is a hair from 0 and the
module gives the exact answer (section 3).

## 1. Pine in a nutshell

- **One bar at a time.** A Pine script runs once per bar, oldest bar first. A variable holds one value per bar (a
  "series"), and `x[1]` is the value it had on the previous bar.
- **Missing values.** `na` means "no value yet". It is what an average returns before it has seen enough bars.
  Arithmetic with `na` gives `na`, and a comparison with `na` is false.
- **Built-in functions remember.** `ta.sma`, `ta.ema`, `ta.rsi` and the like keep their own memory from bar to bar.
  TradingView's reference describes each one with a few lines of "same on Pine" code, and the port follows that code,
  including the order of its arithmetic.
- **Integer division.** In Pine version 5, dividing one integer constant by another drops the fraction: `2/3` is 0.
  This mattered for one script (item 3 in section 3).
- **Inputs.** The indicators read the bid close, as TradingView's CFD charts show it. Volume is the tick count of
  the bar; for BTC there is also Binance's BTC volume, used only by the "RV" variants (`PREREG.md` section 2).

## 2. The indicators, step by step

Every setting below is the script's default. Nothing was tuned. "First value" is the first bar, counting the first
bar of the data as bar 0, on which the line exists.

### 2.1 RSI(14), the baseline (`plain_rsi`, TradingView's `ta.rsi(close, 14)`)

1. Each bar's change is close minus the previous close. The gain is the change when it is positive, else 0. The loss
   is minus the change when it is negative, else 0.
2. The average gain and the average loss use Wilder's smoothing (`ta.rma`). The first value is the simple mean of
   the first 14. After that, each bar adds 1/14 of the new value to 13/14 of the old average.
3. RSI = 100 - 100 / (1 + average gain / average loss). It is 100 when the average loss is 0, and 0 when the average
   gain is 0.

First value: bar 14. **The rules read** the side of 50, and crossings up through 30 and down through 70.

### 2.2 Laguerre RSI, alpha 0.2 (`laguerre_rsi`; Ehlers, script by KivancOzbilgic)

1. Four filter stages smooth the close. With gamma = 1 - alpha = 0.8:
   - `L0 = 0.2 x close + 0.8 x L0[1]`, a fast exponential smoothing;
   - `L1 = -0.8 x L0 + L0[1] + 0.8 x L1[1]`, and L2 and L3 alike, each delayed from the stage before it (Laguerre
     all-pass stages).
2. Look at the three steps L0 to L1, L1 to L2 and L2 to L3. Add the rising ones (`cu`) and the falling ones (`cd`).
3. LaRSI = 100 x cu / (cu + cd). It is 0 when nothing moves.

The line is exactly 100 whenever the four stages stand in rising order, and exactly 0 in falling order. That happens
on about 40% of gold 1H bars; it is how the indicator is built, not a tie. The stages start from 0 on bar 0 (the
script's `nz`). The start-up transient fades as 0.8 to the power n, so it is gone long before 2019.

First value: bar 0. **The rules read** the side of 50, and crossings up through 20 and down through 80.

### 2.3 Volume Weighted RSI and its consolidation score (`vwrsi`, `range_score`; AlgoAlpha)

**The RSI line** is the RSI of 2.1, with each bar's gain and loss multiplied by that bar's volume. Both weighted
averages are also divided by the average volume, which cancels in the ratio. So the line is
100 - 100 / (1 + RMA14(gain x volume) / RMA14(loss x volume)).

The volume average starts one bar before the others, because volume exists on bar 0 while the change does not. Since
it cancels, only rounding depends on it. A bar with volume 0 (an hour without a Binance kline, `DEVIATIONS.md`
entry 5) leaves the line exactly where it was.

**The consolidation score** says how often the line has recently flipped across 50. Above 0 means "chopping", which
is what the R3 rule stands aside in:

1. The direction is +1 when the line is above 50, else -1. A missing value counts as -1, because `na > 50` is false.
2. The flip marker is 1 on a bar whose direction differs from the previous bar's, else 0.
3. `p` is the 10-bar average of flip / 10.
4. `f` is 5 x HMA5(p), where HMA is the Hull moving average.
5. The score is max(HMA20(f), 0).

The score is exactly 0 once the line has stayed on one side of 50 for 37 bars. From 2019 it is above 0 on 60-66% of
bars with tick volume, and on 56-63% with Binance volume. The plotted histogram is the score x 50.

First value: bar 14 for the RSI line, bar 45 for the score. **The rules read** the side of 50, crossings up through 20
and down through 80, and score > 0.

### 2.4 Bjorgum TSI, speed "Fast" (`bjorgum_tsi`)

1. The change is close minus the previous close.
2. Smooth it twice: an EMA over 25 bars, then an EMA over 5 bars of that. Smooth the absolute change the same way.
3. TSI = 100 x (the smoothed change / the smoothed absolute change), so it lies between -100 and +100.
4. The signal is the 14-bar EMA of the TSI. This is line 95 of the public script; the owner's copy stops at line 94
   (`DEVIATIONS.md` entry 16).

Each EMA uses alpha = 2/(n+1) and starts from its first value, as `PREREG.md` section 5 says (`DEVIATIONS.md` entry
11 measures the alternative).

First value: bar 1 for both lines. **The rules read** the side of 0 (rules R1 and R2, and filter F3), crossings up
through -30 and down through +30 (R4), and crossings of the signal (a control).

### 2.5 QQE MOD (`qqe_mod`; Mihkel00; the owner's copy is a Pine v6 rewrite)

The script runs the same procedure twice, a "primary" and a "secondary" QQE:

1. Take the RSI(6) of the close and smooth it with an EMA(5). Call this the smoothed RSI.
2. The smoothed RSI's own volatility is its absolute bar-to-bar change, smoothed by an EMA(11) (11 = 2 x 6 - 1).
   Multiplied by a factor (3.0 for the primary, 1.61 for the secondary), it gives the band distance.
3. Two bands are kept around the smoothed RSI, like trailing stops:
   - the **long band** = smoothed RSI - distance. While the RSI stays above it, it can only rise.
   - the **short band** = smoothed RSI + distance. While the RSI stays below it, it can only fall.
4. The direction becomes +1 when the RSI crosses the previous bar's short band. It becomes -1 when the previous bar's
   long band crosses the RSI. The short-band test comes first; otherwise the direction stays as it was. The **trend
   line** is the long band in direction +1, else the short band.
5. A Bollinger band is drawn on the primary trend line minus 50: its 50-bar mean, plus and minus 0.35 times its
   50-bar standard deviation.
6. The colour of the bar:
   - **BLUE** when the secondary smoothed RSI - 50 > 3 and the primary smoothed RSI - 50 > the upper band;
   - **RED** when the secondary smoothed RSI - 50 < -3 and the primary smoothed RSI - 50 < the lower band;
   - **GRAY** otherwise.
7. The **white line** is the secondary trend line minus 50.

The two smoothed RSIs are identical, because both use 6 and 5; only the band factor differs. The script declares a
primary "threshold" input that it never uses. First values: bar 6 for the smoothed RSI, bar 7 for the bands and trend
lines, bar 56 for the Bollinger band. Until bar 56 the colour is GRAY.

**The rules read** the colour (R1: BLUE long, RED short, GRAY keeps the position; R3: GRAY flat) and the white line's
crossings of 0 (a control).

### 2.6 MA200 and ATR14 (`ma200`, `atr14`)

- **MA200** is the plain 200-bar average of the close. It first exists on bar 199.
- **ATR14** is Wilder's average of the true range. The true range is the largest of high - low, |high - previous
  close| and |low - previous close|; on bar 0 it is just high - low. ATR14 first exists on bar 13, and it sets the
  stop variant S1.

The harness's `tradeiq_market.s1_stop` takes the ATR from `external.wilder_atr` instead. That function writes the
same formula with a different order of arithmetic, and the two agree to within 1.5e-15 relative on every bar.

Every line has its first value long before 2019. The slowest, the daily MA200, starts in October 2017 on gold and in
July 2018 on BTC.

## 3. The Pine details that decided the numbers

Measured on the bars of both symbols and all three timeframes, from 2019-01-01 to 2024-06-30. These are indicator
values only: no rule was run.

| # | The question | What the module does | Why | Effect on our bars | Log |
|---|---|---|---|---|---|
| 1 | How `ta.ema` starts | From its first value | `PREREG.md` 5, and the reference's `pine_ema`. TradingView's runtime appears to start from the SMA of the first `length` values instead | None. All lines are bit for bit equal under both starts, except BTC 1D's TSI (up to 1.8e-10) and signal (up to 4.3e-10). No state differs | 11 |
| 2 | `ta.hma(p, 5)`: the half of 5 | 2 (rounded down); the final length is floor(sqrt 5) = 2 | TradingView's own HMA script; TradingView's output for HMA(5) and HMA(9) | **Material.** Rounding the half up (3) would change "score > 0" on 4.1-4.6% of bars | 12 |
| 3 | AlgoAlpha's `(2/3)` | 0 (integer division in Pine v5), so f = 5 x HMA | TradingView's migration guide to v6 | Scales the histogram only. "Score > 0" is unchanged | 13 |
| 4 | `ta.cross(a, b)` | "a > b" changed since the previous bar | The reference gives no formula; PineTS's reading | None. The other reading (crossover or crossunder) gives identical QQE lines and colours; there is no exact tie | 14 |
| 5 | QQE direction before its first cross | na (the trend line is the short band) | The v6 copy has no `nz(..., 1)`, unlike the original v4 script | Only the first days of the data | 14 |
| 6 | QQE colour before the Bollinger band exists | GRAY | Comparisons with na are false, so neither BLUE nor RED holds (`PREREG.md` 5) | Only bars 0-55 | 10, 14 |
| 7 | `ta.stdev`: deviations at or below 1e-10 | Counted as 0 | The reference's code. Its `SUM()` also returns 15 for deviations in (1e-10, 1e-4], which is plainly a documentation slip and is not copied | Taking the 15 literally would move the band on 23 bars and change no colour | 15 |
| 8 | RSI when an average is 0 | 100 if no loss, 0 if no gain | TradingView's RSI script; AlgoAlpha's line 46 | None. From 2019 no RSI, VWRSI or QQE RSI is ever exactly 0 or 100 | - |
| 9 | `math.max(na, 0)` | na | Pine's na rules | Only the VWRSI warm-up | - |
| 10 | TSI before any move (0/0) | na | - | Only the warm-up | - |
| 11 | The TSI signal line | EMA(TSI, 14) | Line 95 of the public script, read on 28 Nov 2026 | Settles `PREREG.md` 5's assumption | 16 |
| 12 | A value missing inside a series | Refused with `ValueError` | TradingView only says such values are "ignored". The study's inputs never have one, because a Binance hour without a kline has volume 0 | None (it never happens) | - |

**Exact ties.** From 2019, no line ever sits exactly on a threshold a rule reads. These are the closest it comes on
any of the six series:

| Distance from 2019 | Smallest | Where |
|---|---|---|
| RSI to 70 / 50 / 30 | 3.1e-6 / 1.6e-4 / 1.3e-3 | gold 1H / BTC 4H / BTC 1H |
| LaRSI to 80 / 50 / 20 | 2.5e-4 / 3.0e-4 / 9.7e-4 | gold 4H / gold 1H / gold 1H |
| VWRSI to 50 / 20 / 80 (tick volume) | 3.8e-5 / 3.5e-4 / 8.6e-4 | BTC 1H / BTC 1H / gold 1H |
| VWRSI to 50 (Binance volume) | 2.3e-4 | BTC 4H |
| TSI to 0 / -30 / +30, and to its signal | 5.5e-4 / 5.2e-4 / 2.8e-3, and 1.1e-4 | gold 4H / gold 1H / BTC 1H, and gold 4H |
| QQE: secondary RSI - 50 to +3 / -3 | 6.6e-5 / 5.5e-5 | gold 1H / BTC 1H |
| QQE: primary RSI - 50 to the upper / lower band | 6.5e-5 / 6.3e-5 | BTC 1H / gold 1H |
| QQE: smoothed RSI to the previous short / long band (its crosses) | 9.5e-6 / 1.5e-4 | BTC 1D / gold 4H |
| White line to 0 | 1.0e-4 | BTC 1H |
| Close to MA200 | 4.6e-8 of the price (1.1e-3 USD); in dollars the closest is 5.9e-4 USD | BTC 1H; gold 1H |
| Smallest positive consolidation score | 5.3e-7 | every series |
| Consolidation score before its clamp, just below 0 | -2.6e-19 on five bars (exactly 0 in exact arithmetic); otherwise nothing in (-1e-9, 0) | BTC 1H (1 bar with tick volume, 3 with Binance volume), BTC 4H (1, Binance) |

A difference in the last digits therefore cannot flip any state the rules read; TradingView's own rounding is about
1e-12 on lines of this size. The one exception is "score > 0" on those five BTC bars (`DEVIATIONS.md` entry 18).

**The five BTC bars.**

- **Why they are dust.** On each of them the score's two HMAs cancel exactly. The exact value, computed in rational
  arithmetic, is 0, while our floats give -2.6e-19. The clamp `max(·, 0)` makes that 0, which is also the exact
  answer: not chopping.
- **The rest of the score is exact.** Every other bar where the score is 0 has no flip of the RSI across 50 inside
  the 37 bars the score reads, so any order of arithmetic gives exactly 0 there.
- **What could still differ.** A runtime that adds in another order could produce +2.6e-19 on the five bars, and call
  them chopping.
- **Where it matters.** Only BTC's R3 VWRSI rows. Four of the five bars are on Binance volume, the "RV" rows.

## 4. The two ports and how they were reconciled

**Who did what.** Two engineers worked from the same plain-text copies of the scripts, each without opening the
other's folder:

- **Port A**: numpy, 32 tests.
- **Port B**: bar loops compiled with numba, 30 tests, plus a second, statement-by-statement transcription (the "Pine
  VM").

Each checked its own arithmetic by hand-worked cases, by an independent transcription of the Pine code, and against
the reference's code. Port A also reproduced TradingView's printed output, as recorded in the PineTS project's tests,
for `sma`, `ema`, `rma`, `wma`, `hma`, `stdev`, `rsi`, `math.sum`, `atr`, `tsi` and the crosses.

**The comparison.** The bars came through the study's guarded loader (`tradeiq_market.load`), which serves nothing at
or after 2024-07-01 00:00 UTC. Both ports computed every line on all six series: 24 lines on gold, and 26 on BTC with
the VWRSI and its score on Binance volume as well. That is every line in the table of section 2, plus the QQE's bands
and trend directions.

The comparison looked at the floats from bar 0 and from bar 300. It also checked 20-24 event series built from the
lines, which are what the rules read: each side of 50 or 0, each crossing of 20/80, 30/70 and ±30, score > 0, the
colour, the R1 state of the QQE, the white line's side, and the close against MA200.

| Series | Bars (from 2019) | Floats differing | Events differing |
|---|---|---|---|
| XAUUSDm 1H | 44,190 (32,392) | 0 | 0 |
| XAUUSDm 4H | 11,955 (8,769) | 0 | 0 |
| XAUUSDm 1D | 1,932 (1,417) | 0 | 0 |
| BTCUSDm 1H | 56,840 (48,119) | 0 | 0 |
| BTCUSDm 4H | 14,225 (12,036) | 0 | 0 |
| BTCUSDm 1D | 2,372 (2,007) | 0 | 0 |

"0" means bit for bit equal on every bar from bar 0. The one exception is the QQE colour on bars 0-5 of each series,
where the RSI does not exist yet: port A says GRAY and port B says "no value". The plan defines GRAY as "neither BLUE
nor RED", and both readings lead to the same state (GRAY keeps or stays flat), so the module says GRAY.

**What reading the code found.** Some differences between the ports cannot show on our bars, because they only
matter for inputs the study never has:

- **A value missing inside a series.**
  - Port A handles it as TradingView's runtime does, according to the PineTS recordings: the averages skip it, and a
    cross compares with the last bar where both values existed.
  - Port B refuses it in the averages. Its crosses compare with the previous bar, as the reference's definitions
    read.
  - The module refuses it everywhere, the crosses included, so that no undocumented behaviour is relied on silently.
- **A fractional length.** An odd consolidation length would hand `ta.hma` a length like 4.5. Port A refused it, port
  B rounded it down. The module refuses it.
- **Different readings, kept only for measuring.** Port B had optional alternatives (an SMA start for the EMA, a
  rounded HMA half, a second reading of the cross). Port A had the SMA start. The module keeps only the SMA start of
  `ta.ema` (`seed="sma"`), because that measurement is part of the log (entry 11). The others were measured with
  scratch code.

**The module.** `tradeiq_ind.py` keeps port A's arithmetic, so it equals port A on every bar and port B on every bar
but the six warm-up colours. It was rewritten for clarity:

- one function per indicator, each docstring quoting the Pine lines it follows;
- `qqe_bands` and `qqe_colour` functions for the band logic and the colour rule, so that hand-made cases (a bar
  with zero band distance, exact ties at the thresholds) can test them;
- named results (`VWRSI`, `TSI`, `QQE`);
- `compute_all` for every line by name.

It takes 0.3 s for all lines on BTC 1H (56,840 bars).

**The tests** (`tests/test_tradeiq_ind.py`, 42 tests, about 5 s):

- the hand-worked cases of both ports;
- TradingView's printed values (BTCUSDC weekly; a leading-na WMA);
- the invariants: ranges, the bands around the RSI, the colour logic and its strict thresholds, the TSI against the
  drift, constant and zero volume, the first bars, no look-ahead, inputs left alone, na refused;
- bit-for-bit equality with port B and with port B's Pine VM on synthetic bars, under both EMA starts;
- on the real bars, when the tick store is present: bit-for-bit equality with port B on all six series and on
  Binance volume, agreement with `external.py`'s RSI, ATR and SMA, and twelve values per date recorded when the ports
  were reconciled.

**Whether the tests catch mistakes.** 27 plausible porting mistakes were applied one at a time to the module's
source, in memory. Each made at least one test fail, except the last row, which cannot change any value:

| Mistake | Tests failing (of 42) |
|---|---|
| HMA half rounded up | 12 |
| `ta.cross` as crossover-or-crossunder | 2 |
| `(2/3)` as 0.667 | 10 |
| QQE: the long-band cross tested first | 8 |
| LaRSI's first coefficient = alpha instead of 1 - gamma (they differ in the last bit) | 6 |
| stdev without the 1e-10 zeroing | 1 |
| EMA started from the SMA by default | 6 |
| RSI without the zero-average guard | 2 |
| TSI's two EMAs in the other order (5 first) | 7 |
| QQE direction 1 before its first cross (the v4 script's `nz`) | 9 |
| SMA added oldest first (the same mean in exact arithmetic) | 8 |
| WMA weights reversed | 14 |
| VWRSI's volume average started with the gains (it cancels; only rounding) | 7 |
| RMA started from its first value | 14 |
| The first true range na | 10 |
| Consolidation score: an na source gives an na direction | 4 |
| EMA alpha = 1/n | 14 |
| Bollinger band on the secondary trend line | 9 |
| White line from the primary trend line | 9 |
| A value missing inside a series accepted | 1 |
| VWRSI loss = the absolute change | 10 |
| QQE band ratchet without the first half of its condition (long band / short band) | 1 / 1 |
| Colour comparisons not strict (BLUE at +3 / RED at -3 / at the band) | 1 / 1 / 1 |
| LaRSI's down-step test `<=` instead of `<` (it then adds 0: no value can change) | none possible |

## 5. What could still differ from TradingView

- **No chart export.** Neither port could run TradingView. The reference text was read from the data TradingView's
  reference page loads, and from a third-party plain-text copy. TradingView's runtime output was read from the PineTS
  project's tests, whose authors recorded it from TradingView charts. The two readings this matters for are the EMA
  start (immaterial, item 1) and the HMA half (item 2, supported by TradingView's own HMA script and by its recorded
  output). A TradingView CSV export of `ta.hma(close, 5)` and `ta.ema(close, 14)` on any chart would settle both
  beyond doubt.
- **Rounding.** TradingView's internal arithmetic is not documented. For example, its `ta.stdev` differs from the
  reference formula by about 2e-9 relative on BTC prices (port A, from the recordings), which is about 1e-12 on the
  QQE's ±50 scale. The margins in section 3 are millions of times larger.
- **Hold-out bars.** The reconciliation used the guarded loader, so no bar of the hold-out was read. The porting
  engineers' own checks did compute indicator values on the whole store, the hold-out bars included, but they ran no
  rule and produced no result.
