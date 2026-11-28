# Pivot Point SuperTrend (LonesomeTheBlue, Pine v4): porting spec for study 4 (TradeIQ video 3)

Written 28 Nov 2026 in scratch, before any port, rule or backtest of study 4. Nothing here comes from market data.
The script is third-party code (MPL 2.0). It is not copied here: every formula below is restated in our own notation.
The video is paraphrased.

**In one breath.** Small swing points (a high above the two bars on each side, or a low below them) are confirmed two
bars late. A running centre line is a weighted average of them: each new pivot counts one third, the old centre two
thirds. The bands sit 3 ATR(10) above and below that centre and ratchet like a Supertrend. When a close crosses the
previous bar's band, the trend flips and the script prints Buy or Sell. The video ranks it 6th of 6.

## 1. Identity

| Item | Value |
|---|---|
| Title in the code | "Pivot Point SuperTrend" (l.5), overlay |
| Author | © LonesomeTheBlue (l.2). The video dates it to 2020. |
| Licence | Mozilla Public License 2.0 (l.1) |
| Pine version | 4 (l.4) |
| Source | `/Users/sidharthsingh/Desktop/study/trend/Pivot Point SuperTrend Indicator.rtf` (read-only), sha256 `4ec2f84737bcfcafbd3a65a080e9ae3dbe27dc7371ed9e49e3e00a5044123646` |
| Line numbers | "l." means a line of `textutil -convert txt -stdout "Pivot Point SuperTrend Indicator.rtf"` (70 lines; ASCII but for the © of l.2) |
| Size | 70 lines, 24 of which compute (section 11) |
| Module key | `pivotst` (proposed in `infra.md` of this folder) |

## 2. Inputs

| l. | Variable | Label | Default | Type | Effect |
|---|---|---|---|---|---|
| 6 | `prd` | Pivot Point Period | 2 (1-50) | integer | computes: bars on each side of a pivot, and its confirmation delay |
| 7 | `Factor` | ATR Factor | 3 (min 1, step 0.1) | see trap 11 | computes |
| 8 | `Pd` | ATR Period | 10 (min 1) | integer | computes |
| 9 | `showpivot` | Show Pivot Points | false | bool | display only |
| 10 | `showlabel` | Show Buy/Sell Labels | true | bool | display only |
| 11 | `showcl` | Show PP Center Line | false | bool | display only |
| 12 | `showsr` | Show Support/Resistance | false | bool | display only |

The video uses the defaults: period 2, factor 3, ATR 10.

## 3. Pine rules this spec relies on

These are the conventions of studies 1 and 2 (`backtesting/research/tradeiq_ind.py` docstring). Each port implements
them itself.

1. **Bars.** Bar 0 is the first bar handed to the port. `x[k]` is the value k bars back, na when fewer than k bars
   exist. The history of a variable is its **final** value on that bar, after every `:=`.
2. **na.** Arithmetic with na gives na. Every comparison with na is false. v4's `max` / `min` with na give na.
   `nz(x, y)` is x, or y when x is na; `nz(x)` is x, or 0.
3. **v4 numbers as yes/no.** A float used as a condition (`x ? a : b`, `if x`, `x and y`) is true when it is neither
   na nor 0. Prices are never 0 here, so "true" means "not na".
4. **`var` (l.23).** `center` keeps its value from bar to bar and starts as na. Every other variable is computed anew
   on each bar (TUp, TDown, Trend, support and resistance are declared afresh on every bar, then reassigned), and
   carries state only through `x[1]`.
5. **ATR.** `atr(n)` = Wilder RMA of the true range with `tr(true)`:
   - TR(0) = H(0) − L(0); else max(max(H − L, |H − C(t−1)|), |L − C(t−1)|);
   - the RMA is seeded at bar n−1 with the SMA of the first n values, each divided by n before it is added, newest
     first;
   - then α·x + (1 − α)·prev, with α = 1.0 / n and (1 − α) = 1.0 − α.

   Both ports must equal study 1's `tradeiq_ind.atr` bit for bit (a test).
6. **`pivothigh(prd, prd)` / `pivotlow(prd, prd)`** (v4, default sources high / low):
   - the value exists only on the **confirmation bar** t, for the candidate bar c = t − prd;
   - there is no value before bar 2·prd (the window needs 2·prd + 1 bars);
   - the value is H(c) (or L(c)).

   Ties are not documented by TradingView (trap 1).
7. **Arithmetic.** IEEE double, in the order written, no fused multiply-add.

## 4. The computation, bar by bar

Notation: H(t), L(t), C(t) are the bid high, low and close; p = `prd` = 2; F = `Factor` = 3; n = `Pd` = 10. On every
bar, in this order:

1. **Pivots (l.15-16).** For t ≥ 2p, with c = t − p:
   - PH(t) = H(c) if H(c) > H(j) for every j from c − p to c + p, j ≠ c. Otherwise na.
   - PL(t) = L(c) if L(c) < L(j) for every such j. Otherwise na.
   - **Strict on both sides** is the house reading (trap 1).
   - For t < 2p, both are na. A pivot is known **p = 2 bars after its bar**.
2. **The new pivot of the bar (l.24).** lastpp(t) = PH(t) if it exists, else PL(t) if it exists, else na.
   - When one bar is both a pivot high and a pivot low (an outside bar that holds the highest high and the lowest low
     of its 5-bar window), **only the high enters the centre**. Both still update support and resistance (step 8).
3. **The centre (l.23-30, `var`).** When lastpp(t) exists:
   - if the centre is still na, it becomes lastpp(t);
   - otherwise centre = ((centre · 2) + lastpp(t)) / 3. That is the doubling first (exact), then one rounded addition,
     then one rounded division.
   - With no new pivot, the centre keeps its value. centre(t) is the value after this bar's update. It stays na until
     the first pivot and is never na afterwards.
4. **Raw bands (l.33-34).** A(t) = ATR_n(t).
   - Up(t) = centre(t) − (F · A(t)) and Dn(t) = centre(t) + (F · A(t)): the product first, then one rounding.
   - The script calls `atr(Pd)` twice. Both calls give the same value; compute it once.
5. **Ratcheted bands (l.37-41).**
   - TUp(t) = max(Up(t), TUp(t−1)) when C(t−1) > TUp(t−1), else Up(t).
   - TDown(t) = min(Dn(t), TDown(t−1)) when C(t−1) < TDown(t−1), else Dn(t).
   - There is **no `nz`**: when TUp(t−1) is na, the test is false and TUp(t) = Up(t). Both tests are strict.
6. **Trend (l.39, l.42).**
   - Trend(t) = +1 if C(t) > TDown(t−1); else −1 if C(t) < TUp(t−1); else Trend(t−1). On bar 0 the fallback is +1
     (an `nz` whose default is 1).
   - The tests read the **previous** bar's ratcheted bands. They do **not** depend on the current trend (unlike
     Kivanc's script).
   - The up-test runs first, so it wins if both hold. That needs crossed bands, TUp(t−1) > TDown(t−1): never seen on
     synthetic walks, but possible after a large drop of the centre.
   - +1 means up.
7. **The trailing line (l.43).** TSL(t) = TUp(t) when Trend(t) = +1, else TDown(t). It uses **this** bar's bands, so
   it includes a pivot confirmed on bar t.
8. **Support / resistance (l.58-61).**
   - support(t) = PL(t) if it exists, else support(t−1) (na until the first pivot low).
   - resistance(t) is the same with PH.
   - Nothing else reads them.
9. **Signals (l.52-53, l.68-70).**
   - buy(t) = Trend(t) = +1 and Trend(t−1) = −1; sell(t) is the mirror.
   - "Trend Changed" = Trend(t) − Trend(t−1) ≠ 0, false on bar 0.
10. **Display only.**
    - The line's colour (l.46): lime when this and the previous Trend are +1, red when both are −1, **none on a flip
      bar**, so the line shows a gap there.
    - The plot of the line (l.47), the centre line (l.49), the Buy / Sell labels at TSL(t) (l.54-55), the H / L
      pivot marks (l.19-20) and the support / resistance circles (l.64-65).
    - The pivot marks and the circles are drawn with **offset −p**, that is, on the pivot bar (section 5).

**First bar with a value (defaults).**

| Output | First bar | Note |
|---|---|---|
| PH / PL | 4 at the earliest (candidate bar 2) | |
| centre | the first pivot's confirmation bar | |
| A (ATR) | 9 | |
| Up, Dn, TUp, TDown, TSL | max(9, first pivot bar) | |
| Trend | 0 (+1) | it can first change on the bar after the bands exist |
| buy / sell | the same | |

**When the start stops mattering.**
- The centre forgets its start as (2/3)^k after k pivots: below 1e-16 relative after about 91 pivots. With p = 2 a
  pivot comes every few bars, so that is a few hundred bars.
- The ATR seed fades as 0.9^k (about 350 bars). The ratcheted bands of two runs join once both have reset.
- Run from the data start, with at least 500 bars of warm-up.

## 5. Outputs, and when each is known

| Output | Lines | Known at | Notes |
|---|---|---|---|
| PH(t), PL(t) | 15-16 | close of bar t, about bar t − 2 | **confirmed 2 bars late**; never use them at the pivot bar |
| centre(t) | 23-30 | close of bar t | moves only on a confirmation bar |
| Up / Dn / TUp / TDown / TSL | 33-43 | close of bar t | use H, L, C of bar t (the ATR) |
| **The levels bar t+1's trend is tested against** | 40-42 | TUp(t), TDown(t): **close of bar t, one bar ahead** | A stop at TSL(t) during bar t+1 is the intrabar version of the flip (section 7). A pivot confirmed on bar t moves the trend test only from bar t+1. |
| Trend, Buy / Sell, change | 42, 52-53, 70 | close of bar t | Buy / Sell drawn on the flip bar at TSL(t); not moved in time |
| Pivot marks, S/R circles (display) | 19-20, 64-65 | drawn 2 bars **back** | **visual look-ahead**: an old chart shows them at the pivot bar, 2 bars before they existed |
| Alerts | 68-70 | realtime | Buy, Sell, Trend Changed |

**Repainting.**
- The trend line and its signals do not repaint on closed bars. Pivots enter them only on their confirmation bar.
- The pivot marks and S/R circles are shifted back 2 bars for display (above).
- There is no `security` call and no lookahead. On the live bar, everything can change until the close.

## 6. Data it needs

- Bid OHLC of the signal timeframe. No volume, no session, no higher timeframe.
- The video tested 4H.

## 7. How a rule could trade it

**What the script suggests.** It is always in the market: Buy and Sell at every flip, and the trailing line (its name
says "trailing stop loss") shows where the trend is wrong.
- The video says the line moves only when the swings move. That is half true: the centre moves only at pivots, but
  the band is centre ± 3 ATR, so it also follows the ATR on every bar, within the ratchet.

**The video's test** (the same for all seven scripts):
- the signal comes on a closed candle;
- entry at the next candle's open, long and short;
- a stop 2 ATR away = 1R; no target;
- exit at the opposite signal or the stop;
- costs including financing;
- 11 markets, 4H, January 2021 to October 2026, defaults.

**How the video says to use it:** 4H, the defaults, and the 200 EMA: buys only above it, sells only below it.

**Ideas for the PREREG (not decisions).**
- **PP-LS.** Reverse at every flip; the stop at 2 x ATR from the fill (house ATR(14); the script's ATR(10) as a
  sensitivity); exit at the opposite flip or the stop; after a stop, wait for the next flip.
- **PP-LO.** Long only.
- **Filters.**
  - The video's EMA200 (an EMA, not the house SMA200, so the PREREG must name which).
  - F1, F2-1D, LO.
- **Exits.**
  - X0 (the close-based flip).
  - A sensitivity with TSL(t−1) as an intrabar trailing stop (known one bar ahead).
  - XT2 / XP / XBE.
- **Timeframes.** 4H (the video's), 1H and 1D.
- **Controls.**
  - Kivanc's Supertrend on the same bars (the video's baseline).
  - The same rule with the other pivot-tie readings (trap 1), as a sensitivity.
  - Buy-and-hold.
- **Claims to check** (information; the video pools 11 markets):
  - about a third fewer trades than Supertrend (1,935 against 3,022);
  - 27% winners;
  - a profit factor of 1.34 against 1.17;
  - about 7R a year per market against 5, and 4.9 against 2.3 with doubled costs;
  - an average winner of 3.4R against 2.5R;
  - with the EMA200, a profit factor of 1.47 in both halves of the data and 9 of 11 markets positive;
  - the example of gold 4H in March-April 2023: one trade where Supertrend took seven.

## 8. Traps for a port

| # | Lines | Trap | Reading to use | The alternative, and what it changes | Hand test |
|---|---|---|---|---|---|
| 1 | 15-16 | **Pivot ties** (TradingView does not document them) | Strict on both sides: the centre bar must beat all 2p neighbours. This is the house reading of study 2 (PREREG 6.2, DEVIATIONS MSD-P5, WYCKOFF-P6) | An equal value allowed on the older side, the newer side or both. With p = 2 this matters more than in study 2. On a synthetic 0.5 price grid the pivot highs went from 260 to 370 / 368 / 518; on a 0.01 grid by under 1%. Count them on the real bars under all four readings, and log the result | Equal highs at c−1 and c; at c and c+2 |
| 2 | 15-16 | Confirmation delay and value | PH exists on bar c + p with the value H(c). The script never uses it earlier | Using it at bar c: look-ahead of 2 bars on every pivot | A pivot at bar 2, known at bar 4 |
| 3 | 24 | High and low pivot on one bar | Only PH enters the centre; both update S/R | PL first, or both in turn: another centre. On synthetic walks about 1.5% of bars are such bars | An outside bar |
| 4 | 24-25 | Numbers as yes/no | na → false (0 → false; prices are never 0) | — | — |
| 5 | 23-30 | Centre arithmetic | `var`, seeded by the first pivot, then ((centre · 2) + p) / 3 | centre + (p − centre) / 3, or 2/3 · centre + p/3: the last bits differ on most pivots (synthetic) and spread into the bands | Three pivots by hand |
| 6 | 23-34 | Order within a bar | Centre update, then bands, then trend | Bands from the previous centre: other bands on every confirmation bar | A pivot confirmed on a bar with a flip |
| 7 | 40-41 | No fallback in the ratchet | TUp(t−1) na → TUp(t) = Up(t) | An `nz` to 0 changes no number at positive prices (max(Up, 0) = Up, and min(Dn, 0) is never reached); written down so that neither port adds one | First valid bar |
| 8 | 42 | Trend test | Previous bar's bands; strict; up-test first; no condition on the current trend | Current bands: other flips. Kivanc's trend-conditioned test differs only with crossed bands: a +1 trend whose close lies between them would flip down there and stays up here | C(t) = TDown(t−1) exactly → no flip; crossed bands by hand |
| 9 | 42 | Start | +1 on bar 0 | — | Bar 0 |
| 10 | 43 | Which bands the line shows | This bar's TUp / TDown | The previous bar's: the plotted line and every stop placed on it lag one bar | — |
| 11 | 7 | `Factor` is written as the integer 3, with a 0.1 step | 3 · A = 3.0 · A exactly; no number changes at the default | Whether TradingView offers fractional factors in the settings matters only for a sensitivity run | — |
| 12 | 33-34 | ATR called twice | Same value; compute once | — | — |
| 13 | 19-20, 64-65 | Offsets | Display only; never shift the data | Reading S/R at the pivot bar: look-ahead | — |
| 14 | 46 | Colour gap on flip bars | Display only | — | — |
| 15 | 70 | `change(Trend)` on bar 0 | na → false | — | — |
| 16 | 15-16 | Window at the start | No pivot before bar 2p | A shortened window at the start: extra pivots in the first bars only | Bars 0-4 |

## 9. Reconciliation checklist

- **Per-bar outputs, bit for bit, na on the same bars:**
  - PH, PL, centre, A, Up, Dn, TUp, TDown, TSL, support, resistance (float64);
  - Trend (int8);
  - buy, sell, change (bool).
- **Event tables.**
  - Pivots, with their candidate bar and confirmation bar.
  - Flips, with side and TSL.
- **Real bars.** Gold and BTC at 1H, 4H and 1D, from the data start, over whatever spans the PREREG's window guard
  allows (`infra.md` proposes a reverse split).
- **Synthetic bars.**
  - Random walks on 0.01 and 0.5 grids (ties), flat stretches, single outside bars.
  - p from 1 to 5; factors 1, 3 and 10; ATR lengths 1, 2, 10 and 50; series cut to 0-20 bars.
- **Is the test sharp?** Misread port B on purpose, one reading at a time:
  - each tie reading;
  - PL first in lastpp;
  - centre + (p − c)/3;
  - bands from the previous centre;
  - `nz` in the ratchet;
  - the trend test against the current bands;
  - a pivot used at its own bar.

  Each must be caught on the real bars or by a hand test.
- **Counts to report, events only and no profit or loss**, on the development window the PREREG names (study 2 used
  2019-2022; `infra.md` proposes 2021-2026 here):
  - pivots a year;
  - pivots that change under each tie reading;
  - bars with both pivots;
  - flips a year, against Kivanc's Supertrend on the same bars;
  - bars with crossed bands (TUp(t−1) > TDown(t−1));
  - median centre step per pivot in ATR.

## 10. What may still differ from TradingView

1. **Pivot ties** (trap 1). They cannot be checked without TradingView.
2. **The bars.** The 4H session boundaries and the feed, as for every script.
3. **The ATR's last bits.** Native code against the reference code.
4. **The history start.** It is forgotten after a few hundred bars (section 4).
5. **The live bar.**

## 11. Porting effort

- **Lines that compute: 24 of 70** (l.15-16, 23-30, 33-34, 37-43, 52-53, 58-61). Inputs take 7 lines; display and
  alerts about 15.
- **A port.** About 70 lines of Python: a pivot function with a tie switch, then one loop.
- **Two ports with hand tests and the reconciliation:** half a day to a day. Most of the time goes to counting the
  four tie readings on the real bars and logging them.
