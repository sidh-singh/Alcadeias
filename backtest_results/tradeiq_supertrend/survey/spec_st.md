# Supertrend (KivancOzbilgic, Pine v4): porting spec for study 4 (TradeIQ video 3)

Written 28 Nov 2026 in scratch, before any port, rule or backtest of study 4. Nothing here comes from market data.
The script is third-party code. It is not copied here: every formula below is restated in our own notation. The video
is paraphrased, with a few-word phrase quoted at most.

**In one breath.** A line sits 3 ATR(10) below the middle of each candle in an uptrend, or 3 ATR above it in a
downtrend. While the close stays beyond it, the line can only tighten. When a close crosses the previous bar's line,
the trend flips and the script prints Buy or Sell. In the video it is the baseline that the six other scripts are
measured against.

## 1. Identity

| Item | Value |
|---|---|
| Title in the code | "Supertrend" (l.2), overlay on the price chart |
| Author | Not named in the file. The video says the Supertrend it tested is by the author of PMax, KivancOzbilgic, and calls it the most-boosted version. The code matches his widely used public Supertrend. Licence: none stated in the copy. |
| Pine version | 4 (l.1) |
| Source | `/Users/sidharthsingh/Desktop/study/trend/Supertrend Indicator.rtf` (read-only), sha256 `678895e889a86213267e62ed4a4282674a36cbeca5adadcf2f09c420728af938` |
| Line numbers | "l." means a line of `textutil -convert txt -stdout "Supertrend Indicator.rtf"` (37 lines, plain ASCII) |
| Size | 37 lines, 14 of which compute (section 11) |
| Module key | `supertrend` (proposed in `infra.md` of this folder) |

## 2. Inputs

| l. | Variable | Label in the settings | Default | Type | Effect |
|---|---|---|---|---|---|
| 4 | `Periods` | ATR Period | 10 | integer | computes |
| 5 | `src` | Source | `hl2` = (high + low) / 2 | source | computes |
| 6 | `Multiplier` | ATR Multiplier | 3.0 (step 0.1) | float | computes |
| 7 | `changeATR` | Change ATR Calculation Method ? | true | bool | computes: **true = Pine's ATR (Wilder RMA of the true range); false = a simple average of the true range**. The label reads the wrong way round: "change" on is the standard ATR. |
| 8 | `showsignals` | Show Buy/Sell Signals ? | true | bool | display only (the Buy / Sell text labels) |
| 9 | `highlighting` | Highlighter On/Off ? | true | bool | display only (the green / red fills) |
| 2 | `resolution=""` in `study()` | (adds a timeframe setting) | "" = the chart's timeframe | string | none at the default. If a user picks another timeframe, TradingView runs the whole script on it. That is outside the defaults and not specified here. |
| 2 | `format.price`, `precision=2` | — | — | — | display only: 2 decimals in the status line. **Nothing is rounded in the calculation.** |

Nothing is tuned: the study uses every default.

## 3. Pine rules this spec relies on

These are the conventions of studies 1 and 2 (`backtesting/research/tradeiq_ind.py`, the "Pine semantics" block of its
docstring). Each port implements them itself; both must equal study 1's verified helpers bit for bit, which is a test.

1. **Bars.** Bar 0 is the first bar handed to the port, normally the study's data start. `x[k]` is the value k bars
   back, and it is na when fewer than k bars exist. The history of a variable is its **final** value on that bar, after
   every reassignment (`:=`) on that bar.
2. **na.** Arithmetic with na gives na. Every comparison with na is false, so `cond ? a : b` gives b. v4's `max` /
   `min` with an na argument give na. `nz(x, y)` is x, or y when x is na.
3. **No `var`.** This script declares none. Every variable is computed anew on each bar, and state carries over only
   through `x[1]`.
4. **True range.**
   - TR(t) = max(max(H(t) − L(t), |H(t) − C(t−1)|), |L(t) − C(t−1)|) for t ≥ 1. Max is exact, so the order of the
     three terms does not matter.
   - `tr(true)` (inside `atr()`): on bar 0, TR(0) = H(0) − L(0).
   - v4's built-in **variable** `tr` is `tr(false)`: **na on bar 0**.
5. **SMA (`sma`, `ta.sma`)**, as TradingView's reference code: s = 0.0; for i = 0 (this bar) to n−1: s = s +
   x(t−i) / n. Each term is divided before it is added, newest first. The result is na until n values exist, and na
   if any value in the window is na.
6. **RMA (Wilder) and ATR.**
   - RMA_n is na until n values exist. Its first value is the SMA of rule 5 over those n values, at bar n−1 when the
     input has no leading na. After that, A(t) = α·x(t) + (1 − α)·A(t−1), with α = 1.0 / n and (1 − α) computed as
     1.0 − α.
   - `atr(n)` = RMA_n of `tr(true)`.
7. **Arithmetic.** IEEE double, operations in the order written, no fused multiply-add and no fast-math.

## 4. The computation, bar by bar

Notation: H(t), L(t), C(t) are bar t's bid high, low and close; M = `Multiplier` = 3.0; P = `Periods` = 10. Every
step runs on every bar, in this order.

1. **Source (l.5).** src(t) = (H(t) + L(t)) / 2.
2. **The SMA version of the ATR (l.10).** atr2(t) = SMA_P of TR(false).
   - It is computed on every bar and used only when `changeATR` is false.
   - TR(false) is na on bar 0, so the first full window is bars 1..10 and atr2 starts at **bar 10**.
3. **The ATR in use (l.11).** atr(t) = RMA_P of TR(true) when `changeATR` is true (the default).
   - Its first value is at **bar 9**: the mean of TR(9), TR(8), ..., TR(0), each divided by 10, added in that order.
   - The call sits inside a conditional. `changeATR` is a constant input, so the RMA advances on every bar: compute
     it on every bar.
4. **Lower band, the script's `up` (l.12-14).**
   - raw_up(t) = src(t) − (M · atr(t)). It is na while atr is.
   - prev_up(t) (the script's `up1`, l.13) = U(t−1), the previous bar's **final** lower band, after its own ratchet.
     When U(t−1) is na (bar 0 and the warm-up), it is **this bar's raw_up(t)**: the `nz` falls back to the raw band,
     not to 0.
   - U(t) = max(raw_up(t), prev_up(t)) when C(t−1) > prev_up(t), else raw_up(t) (l.14).
     - The test is strict: a previous close exactly on the band resets it to the raw value.
     - On bar 0, C(−1) is na and the test is false.
5. **Upper band, the script's `dn` (l.15-17).** The mirror:
   - raw_dn(t) = src(t) + (M · atr(t));
   - prev_dn(t) = D(t−1), or raw_dn(t) when that is na;
   - D(t) = min(raw_dn(t), prev_dn(t)) when C(t−1) < prev_dn(t), else raw_dn(t).
6. **Trend (l.18-20).**
   - The trend starts at +1 on bar 0 and otherwise begins each bar with the previous bar's value (l.18-19).
   - Then (l.20): T(t) = +1 if T(t−1) = −1 and C(t) > prev_dn(t); −1 if T(t−1) = +1 and C(t) < prev_up(t); else
     T(t−1).
   - Both tests are strict. Both compare the close with the **previous bar's final band** (prev_up / prev_dn), **not**
     with U(t) / D(t) of this bar.
   - **+1 means up** (the line is under price).
7. **Signals.**
   - buy(t) = T(t) = +1 and T(t−1) = −1 (l.22). sell(t) is the mirror (l.26).
   - change(t) = T(t) ≠ T(t−1) (l.36).
   - All three are false on bar 0, where T(−1) is na.
8. **The plotted line (l.21, l.25).**
   - line(t) = U(t) when T(t) = +1, else D(t). It is drawn with breaks where it switches side.
   - The Buy circle and label sit at U(t) on a buy bar (l.23-24); the Sell ones at D(t) (l.27-28).
9. **Display only.** The `ohlc4` helper plot (l.29) and the two fills (l.30-33). Nothing reads them.

**Both bands run on every bar, whatever the trend.**
- In a downtrend, the lower band still ratchets up while closes hold above it, and resets to its raw value after a
  close below it. The upper band does the same in an uptrend.
- A flip simply switches which band is plotted. Nothing resets at a flip.

**First bar with a value (defaults, bar 0 = the first bar given).**

| Output | First bar | Note |
|---|---|---|
| atr | 9 | 10 with `changeATR` = false |
| U, D, line | 9 | |
| T | 0 | +1 from bar 0. It cannot change before bar 9. On bar 9, prev_up is bar 9's own raw band, so a flip there needs a close below hl2 − 3 ATR, i.e. a bar range above 6 ATR. In practice the first flip comes later. |
| buy / sell / change | 9 at the earliest | |

**When the start stops mattering.**
- The ATR seed fades as 0.9^k. It is below 1e-16 relative after about 350 bars.
- Two runs with different starts then share their bands once both have reset a band, and their trend after the next
  flip.
- Run from the data start, with at least 500 bars before the first scored bar (the house runs years ahead).

## 5. Outputs, and when each is known

| Output | Lines | Value | Known at | Notes |
|---|---|---|---|---|
| Trend T(t) | 18-20 | +1 / −1 | close of bar t | never na |
| Buy / Sell | 22, 26 | yes / no | close of bar t | drawn on the flip bar itself, at the new band; never moved in time |
| Direction change | 36 | yes / no | close of bar t | |
| The line | 21, 25 | U(t) or D(t) | close of bar t | it uses H, L and C of bar t |
| **The level bar t+1 is tested against** | 13, 16 | prev_up(t+1) = U(t), prev_dn(t+1) = D(t) | **close of bar t, one bar ahead** | A stop order at U(t) during bar t+1 is the intrabar version of the close-based flip. That is a different rule (section 7). |
| Alerts | 34, 35, 37 | Buy, Sell, change | realtime only | three `alertcondition`s on the conditions above |

**Repainting.**
- None on closed bars: every value uses bar t and earlier only. There are no pivots and no offsets.
- There is no `security` call at the defaults (see `resolution` in section 2).
- On TradingView's live bar the script runs on every tick. A flip can appear and vanish before the bar closes, and an
  alert that fires before the close can fire on a flip that does not survive it. The study uses closed bars only.

## 6. Data it needs

- Bid OHLC of the signal timeframe: H and L for hl2 and the true range, C for the tests.
- No volume, no session, no higher timeframe.
- The video tested 4H, and reports that 1H loses (section 7).

## 7. How a rule could trade it

**What the script itself suggests.** It is always in the market: Buy flips to long, Sell flips to short. The coloured
fill marks the current trend, a state that holds until the next flip.

**The video's test** (the same for all seven scripts of video 3):
- the signal comes on a closed candle;
- entry at the next candle's open, long and short;
- a stop 2 ATR away, which is 1R;
- no target: the trade runs until the opposite signal or the stop;
- costs: fees and slippage on crypto, the spread on the other markets, and financing while a trade is held;
- 11 markets on 4H from January 2021 to October 2026, default settings, no confirmation.

The video does not say which ATR length the stop uses.

**Ideas for the PREREG (not decisions).**
- **ST-LS.** The video's rule:
  - reverse at every flip;
  - the stop at 2 x ATR from the fill (house: `ta.atr(14)`, PREREG 5 of study 2; the script's own ATR(10) as a
    sensitivity);
  - exit at the opposite flip or the stop;
  - after a stop, flat until the next flip (an event rule).
- **ST-LO.** The same, long only: a Sell only exits.
- **Filters.**
  - The video's 200 EMA: buys only above it, sells only below it. It is an **EMA**, not the house's SMA200, so the
    PREREG must name which.
  - The house's F1 (SMA200 of the same timeframe), F2-4H / F2-1D, and LO.
- **Exits.**
  - X0: the script's close-based flip.
  - A sensitivity with the line itself as an intrabar trailing stop (touch of U(t−1) / D(t−1)). This is possible
    because the level is known one bar ahead.
  - The house's XT2 / XP / XBE.
- **Timeframes.** 1H, 4H (the video's) and 1D.
- **Controls.**
  - TradingView's built-in `ta.supertrend(3, 10)`. It is a different algorithm (trap 4), so it is a real control and
    not a duplicate.
  - Buy-and-hold.
- **Claims to check** (information only, on our two markets; the video's numbers are pooled over 11):
  - a profit factor of about 1.17 on 4H and 0.98 on 1H;
  - about 7 losing signals in 10;
  - about one trade a week per market;
  - about 4 in 10 trades are losers closed within 2 days;
  - the 200 EMA about halves the trades and lifts the profit factor to about 1.33;
  - doubled costs remove about 55% of the profit.
- **Swap.** The video charges financing. The house model has none (PREREG 4 of study 2). Supertrend trades last days,
  so this matters little here. It matters more for the Volume SuperTrend AI.

## 8. Traps for a port

| # | Lines | Trap | Reading to use | The alternative, and what it changes | Hand test |
|---|---|---|---|---|---|
| 1 | 10-11 | `tr` vs `atr()` | The SMA option averages v4's variable `tr` = `tr(false)`, na on bar 0. The default `atr()` uses `tr(true)` | `tr(true)` in the SMA: atr2 starts at bar 9 with bar 0's range in it; only with `changeATR` = false | Periods = 3: atr2 starts at bar 3; atr at bar 2 |
| 2 | 11 | ATR type | Wilder RMA seeded with the SMA of the first P true ranges | SMA or EMA of TR: other bands on every bar | 12 hand bars, P = 3 |
| 3 | 20 | Sign | +1 = up (line below price), −1 = down | `ta.supertrend` and the Volume SuperTrend AI use −1 = up. A port must not mix the two | — |
| 4 | 12-20 | It is **not** `ta.supertrend` | Follow these lines. (a) The flip compares C(t) with the **previous** bar's final band; `ta.supertrend` compares it with the **current** bar's band, already ratcheted. (b) Here a previous close exactly on the band resets it; there it keeps it. (c) The warm-up fallback here is this bar's raw band; there it is 0 | Swapping in a generic Supertrend moves flips. On 2,500 synthetic random-walk bars: one extra flip and 28 bars on the other side | A path where C(t) lies between U(t−1) and U(t) |
| 5 | 13-14, 16-17 | Which "previous band" | U(t−1) / D(t−1) is the **final** band of the previous bar, after its ratchet | The raw band of the previous bar: other bands and flips | Two bars where the ratchet held |
| 6 | 13, 16 | `nz` fallback | This bar's raw band | 0 (what `ta.supertrend` does): the first valid bar's tests become C > 0 / C < 0, so no flip is possible there, where the script can flip on a bar range above 6 ATR. Warm-up only | First valid bar with a 7-ATR range |
| 7 | 14, 17, 20 | Strict tests | `>` / `<` everywhere: equality resets the band (l.14, l.17) and does not flip (l.20) | `>=` / `<=`: other bands and flips, on bars with an exact equality. Synthetic walks never had one; real bars on a 0.01 grid might | C(t−1) = U(t−1) exactly; C(t) = prev_up exactly |
| 8 | 18-19 | Start | T = +1 on bar 0 | na or −1 at the start: different first flip in the warm-up only | Bar 0 |
| 9 | 12-17 | Both bands every bar | Update both bands on every bar, whatever the trend | Updating only the active band, or resetting at a flip: other levels after every flip | A flip, then 3 bars |
| 10 | 12, 15 | Order of the arithmetic | src − (M · atr) and src + (M · atr): the product first, one rounding each | src − M·atr fused (FMA) or atr·M added in another order: the last bits | — |
| 11 | 2 | `precision=2` | Display only; no rounding | Rounding the bands to 2 decimals: other flips on near-ties | — |
| 12 | 14, 17 | `max` / `min` | They return one of their operands exactly | — | — |
| 13 | 22, 26, 36 | Bar 0 events | false (T(−1) is na) | true for `change` on bar 0: warm-up only | — |

## 9. Reconciliation checklist (two independent ports)

- **Per-bar outputs to compare, bit for bit, with na on the same bars:**
  - atr and atr2 (float64);
  - U, D, line (float64);
  - T (int8);
  - buy, sell, change (bool).
- **Event table.** Each flip bar with its side and level.
- **Real bars.** Gold and BTC at 1H, 4H and 1D, from the study's data start, over whatever spans the PREREG's window
  guard allows. `infra.md` proposes a reverse split for this study.
- **Synthetic bars.**
  - Random walks on fine and coarse price grids (a 0.5 grid makes equalities), trending and flat stretches, and gaps.
  - Periods 1, 2, 3, 10 and 50; multipliers 0.5, 3 and 10; both values of `changeATR`; series cut to 0-30 bars (the
    warm-up).
- **Is the test sharp?** Misread port B on purpose, one reading at a time:
  - the flip against the current band;
  - `>=` in the ratchet;
  - the `nz` fallback to 0;
  - the SMA ATR from bar 9;
  - the sign flipped;
  - the raw previous band.

  Each must be caught.
- **Counts to report, events only and no profit or loss**, on the development window the PREREG names (study 2 used
  2019-2022; `infra.md` proposes 2021-2026 here):
  - flips a year per series;
  - median bars between flips, and the share of flips that reverse within 12 bars (4H: 2 days);
  - flip bars that differ from `ta.supertrend(3, 10)`.
- **A third opinion already in the repository: `external._supertrend` (L1385) with `external.wilder_atr` (L301).**
  It is the same band and flip logic (KivancOzbilgic's), already used by FINAL10, the ladder study and the silver
  study. Use it on flip bars, not on bits. Its known differences from this spec:
  1. Its ATR seeds with `np.mean` and updates as (v·(n−1) + x)/n, so its last bits differ from the reference
     arithmetic.
  2. It outputs 0 before the ATR exists, where the script holds +1.
  3. On the first bar with an ATR it applies neither the ratchet nor the flip test. The script can flip there, which
     needs a bar range above 6 ATR.
  4. It has no SMA-ATR option.

  Any other difference in flip bars is a finding.
- **Disclosure** (`infra.md` F6). The classic Supertrend H4 (10, 3) has already been scored as a filter or hybrid by
  FINAL10, the ladder study and the silver study. Its direction on gold and BTC from 2018-11-13 is therefore not a
  clean test. The PREREG has to say so.

## 10. What may still differ from TradingView

1. **The bars.** The house builds 4H bars on UTC boundaries from the Exness tick archive. TradingView's 4H bars for a
   broker symbol may follow another session, and its feed may differ tick by tick. A flip can land on another bar.
2. **The ATR's last bits.** TradingView's `atr` is native code. The ports follow its published reference code.
3. **The history start.** TradingView seeds the ATR at the chart's first loaded bar. The effect is gone after a few
   hundred bars.
4. **The live bar** (section 5).

## 11. Porting effort

- **Lines that compute: 14 of 37** (l.10-20, 22, 26, 36). Inputs take 6 lines; plots, fills and alerts 15.
- **A port.** About 40 lines of Python: one loop over the bars, numba or plain Python. Two ATR helpers come from the
  house's existing conventions.
- **Two independent ports with hand tests and the reconciliation:** about half a day. Low risk. The only real traps
  are 4-6.
