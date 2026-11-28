# Volume SuperTrend AI (Zeiierman, Pine v6): porting spec for study 4 (TradeIQ video 3)

Written 28 Nov 2026 in scratch, before any port, rule or backtest of study 4. Nothing here comes from market data.
The script is third-party code (CC BY-NC-SA 4.0). It is not copied here: every formula below is restated in our own
notation. The video is paraphrased, with a few-word phrase quoted at most.

**In one breath.**
- **The line.** A Supertrend whose centre is a 10-bar weighted average of close x volume divided by the same average of
  volume, where the classic Supertrend uses the middle of the candle. It keeps the band logic of Pine's built-in
  `ta.supertrend`.
- **The "AI" vote.** Each bar gets a label: 1 when the 20-bar WMA of the close is above the 100-bar WMA of the line,
  else 0. Among the last 10 bars, the current one included, the 3 whose line value is closest to the current value
  vote, weighted by closeness.
  - The colour is bullish only if all three labels are 1, bearish only if all three are 0, and neutral otherwise.
  - A buy (sell) triangle needs a flip of the line on a bar whose vote is fully bullish (bearish).
- **In the video.** It ranks 1st of 6, and the video tells you to trade only the triangles.

## 1. Identity

| Item | Value |
|---|---|
| Title in the code | "Volume SuperTrend AI (Zeiierman)" (l.5), overlay |
| Author | © Zeiierman (l.2). The video dates it to August 2023. |
| Licence | CC BY-NC-SA 4.0 (l.1) |
| Pine version | 6 (l.4). The copy carries a "cloud" block (l.152-174) that is display only. Whether the copy matches the 2023 publication line for line is not known. |
| Source | `/Users/sidharthsingh/Desktop/study/trend/Volume SuperTrend AI Indicator.rtf` (read-only), sha256 `185e1ea6b7be429542c38bd07d15b467bcfc844e13cc38d29554df7a4c449e6c` |
| Line numbers | "l." means a line of `textutil -convert txt -stdout "Volume SuperTrend AI Indicator.rtf"` (195 lines; ASCII but for the © of l.2) |
| Size | 195 lines, about 68 of which compute (section 11) |
| Module key | `vstai` (proposed in `infra.md` of this folder) |

## 2. Inputs

| l. | Variable | Label | Default | Effect |
|---|---|---|---|---|
| 23 | `k` | Neighbors | 3 (1-100) | computes: neighbours that vote |
| 24 | `n_` | Data | 10 (1-100) | computes |
| 25 | `n` | — | max(k, n_) = 10 | computes: bars in the vote's window |
| 29 | `KNN_PriceLen` | Price Trend | 20 (2-500, step 10) | computes: WMA length of the close for the labels |
| 30 | `KNN_STLen` | Prediction Trend | 100 (2-500, step 10) | computes: WMA length of the line for the labels |
| 31 | `aisignals` | AI Trend Signals | true | computes: false switches off all four signals |
| 32-33 | `Bullish_col`, `Bearish_col` | — | lime, red | display only (the circles and triangles) |
| 37 | `len` | Length | 10 (min 1) | computes: the centre's WMA length and the ATR length |
| 38 | `factor` | (factor) | 3.0 (step 0.1) | computes |
| 39 | `maSrc` | Moving Average Source | "WMA" (SMA / EMA / WMA / RMA / VWMA) | computes |
| 40-42 | `upCol`, `dnCol`, `neCol` | Bullish / Bearish / Neutral Color | lime, red, blue | **read by the signal logic** (trap 13). Only their being distinct matters, as they are at the defaults |
| 46-52 | `showCloud`, `cloudBull`, `cloudBear`, `cloudTransp`, `cloudRefLen`, `cloudLineSmooth`, `cloudLayers` | Cloud Fill | true, lime, red, 78, 10, 2, 3 | display only |
| 8-19 | `t1` ... `t12` | tooltips | text | none |

## 3. Pine rules this spec relies on (v6)

1. **Bars.** Bar 0 is the first bar handed to the port. `x[k]` is the value k bars back, na beyond the history. The
   history of a variable is its final value on that bar. History references inside a loop (`x[i]` for i = 0..9)
   follow the same rule.
2. **na.** Arithmetic with na gives na, and 0 / 0 is na. Every comparison with na is false; v6 yes/no values are never
   na. `nz(x)` is x, or 0.
3. **No `var`.** Everything is computed anew on each bar. The arrays (l.90-91, l.107-108) are created on every bar and
   fully overwritten before they are read.
4. **`switch` (l.56-61)** runs only the matching branch. `maSrc` is a constant input, so the WMA branch runs on every
   bar.
5. **v6 lazy `and` / `or`.** No effect here: no condition holds a stateful call.
6. **WMA (`ta.wma`)**, as TradingView's reference code, which is study 1's `tradeiq_ind.wma`:
   - for i = 0 (this bar) to n−1: weight = (n − i) · n (an exact integer); norm = norm + weight;
     sum = sum + x(t−i) · weight, each starting at 0.0;
   - the result is sum / norm;
   - it is na before n values exist, and na if any value in the window is na (the reference's arithmetic). See trap 6
     for the one series where this matters.
7. **ATR (`ta.atr`).** Wilder RMA of the true range with TR(0) = H(0) − L(0):
   - seeded at bar n−1 with the SMA of the first n values, each divided by n, newest first;
   - then α·x + (1 − α)·prev, with α = 1.0 / n.

   It equals study 1's `tradeiq_ind.atr` (a test).
8. **Loops.** `for i = a to b by 1` includes both ends. At the defaults every range is non-empty.
9. **Arithmetic.** IEEE double, in the order written, no fused multiply-add and no fast-math.

## 4. The computation, bar by bar

Notation: O, H, L, C, V are the bid open, high, low, close and the volume of bar t (section 6 for the volume). The
defaults are len = 10, f = 3.0, Lp = 20, Ls = 100, n = 10, k = 3. On every bar, in this order:

1. **Close x volume.** cv(t) = C(t) · V(t).
2. **The centre (l.56-61, default WMA).**
   - Wcv(t) = WMA_len(cv)(t) and Wv(t) = WMA_len(V)(t). Each is finished (sum / norm) **before** the division.
   - vw(t) = Wcv(t) / Wv(t). Its first value is at bar 9.
   - A window whose 10 volumes are all 0 gives 0 / 0 = na, and so do the raw bands. Step 6 then holds both bands at
     their previous values. The exception is a band the previous close is already beyond: it becomes na, and so does
     ST if that band is the active one.
   - The next bar with a valid centre restarts such a band from its raw value (the 0 fallback). On a synthetic
     12-bar zero-volume run the bands simply froze and ST stayed valid.
   - None of this happens with gold's tick volume or with Binance volume on 1H and up (section 6).
   - **The other options**, for sensitivity runs only:
     - SMA: SMA(cv) / SMA(V), a rolling VWAP;
     - EMA: EMA(cv) / EMA(V), seeded as PREREG 5 of study 2 says;
     - RMA: RMA(cv) / RMA(V);
     - VWMA: VWMA(cv) / VWMA(V) with VWMA(x) = SMA(x·V) / SMA(V), so the bars weigh V².
3. **ATR (l.63).** A(t) = ATR_len(t). Its first value is at bar 9.
4. **Raw bands (l.64-65).** hi_raw(t) = vw(t) + (f · A(t)) and lo_raw(t) = vw(t) − (f · A(t)): the product first.
5. **The previous final bands (l.66-67).**
   - pLo(t) = lo(t−1), or **0.0** when that is na or t = 0.
   - pHi(t) = hi(t−1), or **0.0**. This is the opposite of Kivanc's fallback.
6. **Ratchet (l.69-70, the logic of `ta.supertrend`).**
   - lo(t) = lo_raw(t) when lo_raw(t) > pLo(t) **or** C(t−1) < pLo(t); else pLo(t).
   - hi(t) = hi_raw(t) when hi_raw(t) < pHi(t) **or** C(t−1) > pHi(t); else pHi(t).
   - **Warm-up consequence** (comparisons with na are false):
     - lo = 0.0 on bars 0-8;
     - hi = 0.0 on bar 0 and **na on bars 1-8**: there C(t−1) > 0 holds, so hi takes the na raw value.

     Both are valid from bar 9. This was verified on synthetic walks.
7. **Direction (l.72-81).** Let pST(t) = ST(t−1) (na on bar 0).
   - If A(t−1) is na (bars 0-9; note A of the **previous** bar): dir(t) = +1.
   - Otherwise, if pST(t) == pHi(t) exactly (the previous line was on the upper band): dir(t) = −1 if C(t) > hi(t),
     else +1.
   - Otherwise: dir(t) = +1 if C(t) < lo(t), else −1.
   - The tests compare the close with **this bar's** final bands, from step 6.
   - **−1 means up** (bullish, the line is the lower band) and +1 means down. That is `ta.supertrend`'s convention,
     the opposite of the other two scripts of this study.
8. **The line (l.83).** ST(t) = lo(t) when dir(t) = −1, else hi(t).
   - Warm-up: ST(0) = 0.0, na on bars 1-8, valid from bar 9.
   - The first possible flip is on bar 10.
9. **The two averages of the label (l.87-88).**
   - P(t) = WMA_Lp(C)(t), from bar 19.
   - S(t) = WMA_Ls(ST)(t). It is na while any of ST(t−99), ..., ST(t) is na, so its **first value is at bar 108**
     (trap 6).
10. **Label of a bar (l.95).** lab(t) = 1 when P(t) > S(t), else 0. An na gives 0.
11. **The vote (l.90-142).**
    - For i = 0..n−1: x_i = ST(t−i) (na before bar 0) and y_i = lab(t−i) (**0** before bar 0, because the comparison
      is false). The query is q = ST(t), which is x_0.
    - d_i = |q − x_i| (na if either is na).
    - **Sort (l.116-125).** For pass i = 0..n−2 and j = 0..n−i−2: if d_j > d_(j+1) (strict, and false when either is
      na), swap the two distances and their original positions.
      - This is a **stable** sort by distance: equal distances keep their original order, so **the more recent bar
        comes first**.
      - An na distance never moves and nothing passes it. That happens only in the warm-up (bars 0-17), or after a
        window of zero volume made ST na (trap 10).
    - **Weights (l.127-137).** For the first k = 3 sorted positions j = 0, 1, 2, in that order:
      - w_j = 1 / (d_(j) + 1e-6);
      - ws = ws + w_j · y_(j) and tw = tw + w_j, both starting at 0.0;
      - knn(t) = ws / tw. It is na if any of the three distances is na.
12. **AI state (l.146).**
    - s(t) = +1 (colour `upCol`) when knn(t) == 1 exactly;
    - −1 (`dnCol`) when knn(t) == 0 exactly;
    - 0 (`neCol`, neutral) otherwise, na included.
13. **Signals (l.178-181).** Each is and-ed with `aisignals` (true).
    - start_up(t), the circle: s(t) = +1 and s(t−1) ≠ +1. start_dn(t): s(t) = −1 and s(t−1) ≠ −1. Both are false on
      bar 0. The extra "or the previous colour was neutral" is redundant while `neCol` differs from `upCol` and
      `dnCol`.
    - **tri_up(t)**, the triangle, the video's buy: dir(t) = −1 and dir(t−1) = +1 and knn(t) == 1.
    - **tri_dn(t)**: dir(t) = +1 and dir(t−1) = −1 and knn(t) == 0.
14. **Display only.**
    - The line coloured by s (l.147), and its split into an up plot and a down plot by bit equality of ST with lo or
      hi (l.149-150; on bar 0 both hold, as 0 == 0).
    - Circles and triangles drawn at ST(t) (l.183-186).
    - The cloud (l.152-174): an SMA_2 of ST, an EMA_10 of (O + C) / 2, three layers at 25 / 50 / 75% between them,
      and fills. Nothing reads it, so do not port it.

### What the "AI" amounts to

This was verified on synthetic walks, and it is exact at gold's and BTC's price levels.

- **The current bar always votes.** Its distance is 0, nothing can sort before it, and its weight is about 1e6.
- **knn(t) == 1 exactly iff all three neighbours' labels are 1.**
  - Then ws and tw are the same additions in the same order, so their ratio is exactly 1.
  - With mixed labels knn lies strictly between 0 and 1. The exception would be a neighbour weight below half an ulp of
    the total, which needs a distance above about 4e9: impossible here. The same holds for 0.
- **Equivalent form, for a cross-check.** s(t) = +1 iff lab(t) = lab(t−a) = lab(t−b) = 1, where a and b are the two
  lags in 1..9 whose ST values are nearest to ST(t), ties going to the smaller lag. s(t) = −1 iff all three are 0, and
  0 otherwise.
  - On synthetic walks this matched the literal loop on every bar from bar 18, where the window has no na left.
- **What the label is.** The 20-bar WMA of the close is above the 100-bar WMA of the line: a slow trend filter. The AI
  state is that filter, asked to agree on the current bar and on the two most similar recent bars.
- **Distance ties are the rule, not the exception.** The band often holds one value for several bars.
  - On synthetic walks the 3rd and 4th distances tie on about 60% of bars.
  - Breaking those ties oldest-first instead changes s(t) on 1.4-2.6% of bars. **The tie order is load-bearing.**
- **No future data.** The vote reads only bars up to t (section 5).

### First bar with a value (defaults)

| Output | First bar / warm-up value | Note |
|---|---|---|
| vw, A, raw bands | 9 | |
| lo | 0.0 on bars 0-8, valid from 9 | an artefact of the 0 fallback (trap 3) |
| hi | 0.0 on bar 0, na on 1-8, valid from 9 | |
| ST | 0.0 on bar 0, na on 1-8, valid from 9 | |
| dir | +1 on bars 0-9 | first possible flip bar 10 |
| P | 19 | |
| S | 108 | 107 under the "na skipped" reading (trap 6) |
| lab | 0 from bar 0 | always 0 before bar 108 |
| knn | na on bars 0-10, a value from 11 | |
| s | 0 (neutral) on bars 0-10, then −1 until labels can be 1 (bar 108 on) | so **start_dn fires on bar 11**, an artefact |
| tri_up / tri_dn | tri_dn from bar 11 at the earliest (it needs dir = −1 on the bar before); tri_up needs three labels of 1 within the last 10 bars, so bar 110 at the earliest | |
| Free of the warm-up artefacts | from bar 117 | |

**When the start stops mattering.** The WMA windows are at most 100 bars, the ATR seed fades within about 350 bars, and
the band ratchets join after resets. Run from the data start, with at least 500 bars of warm-up.

## 5. Outputs, and when each is known

| Output | Lines | Known at | Notes |
|---|---|---|---|
| Bands, dir, ST | 63-83 | close of bar t | They use C, V, H, L of bar t. **The flip compares C(t) with bands built from bar t itself, so no level is known a bar ahead** (unlike the other two scripts): the flip has no exact stop-order version. ST(t) can still serve as a trailing stop during bar t+1, since it is known at the close of t; that is a different rule from the flip. |
| P, S, lab | 87-96 | close of bar t | |
| knn, s (the colour) | 141-146 | close of bar t | |
| Triangles tri_up / tri_dn | 180-181 | close of bar t | drawn at ST(t) on the flip bar; not moved |
| Circles start_up / start_dn | 178-179 | close of bar t | the video says they are not the signal |
| Alerts | 190-195 | realtime | 6: each signal and the "any" combinations |

**Repainting and the "AI".**
- Closed bars never change.
- The vote is "trained" on the last 10 bars, **the current bar included** (its own label, at distance 0). That is
  self-inclusion, not look-ahead: everything is known at the close of bar t.
- No future bar is used, nothing is fitted on the whole history, there is no `request.security`, no pivot, no offset,
  and no label is moved back in time.
- On the live bar the close and the volume of the bar change with every tick. The line, the flips, the colour and the
  signals can appear and vanish until the close.

## 6. Data it needs

- Bid OHLC and volume of the signal timeframe. The open is used only by the cloud.
- **The volume is load-bearing**: the centre is volume-weighted.
  - **Gold:** tick volume (the house's).
  - **BTC:** Exness's BTCUSDm tick volume is a heartbeat, about one tick a second with a coefficient of variation of
    0.06 (PREREG 2 of study 2). With it, the centre is nearly a plain WMA10 of the close. Study 2 used Binance BTCUSDT
    spot volume for every rule that reads volume. The recommendation is the same here, with Exness tick volume as a
    sensitivity (what a TradingView user on BTCUSDm sees). Decide before any result.
  - **Zero volume.**
    - Ten zero-volume bars in a row make the centre na. The bands then freeze, and ST can become na (step 2).
    - An na ST inside the series blanks S for the next 100 bars under the reference reading: every label is then 0,
      so no buy triangle can print. It does not under the "na skipped" reading (trap 6).
    - Binance has hours without a kline (volume 0: 61 1H bars in 2019-2022, never ten in a row).
    - Assert on every series used that vw and ST have no na after bar 9, especially on M5 / M15 if any.
- No session, no higher timeframe.

## 7. How a rule could trade it

**What the script suggests.** Two kinds of markers, each with alerts: circles when the colour turns fully bullish or
bearish, and triangles when the line flips with a fully agreeing vote.

**The video.**
- Its test, the same for all seven scripts:
  - the signal on a closed candle;
  - entry at the next open, long and short;
  - a stop 2 ATR away = 1R, no target;
  - exit at the opposite signal or the stop;
  - costs including financing;
  - 4H.
- For this script: "take only the triangles", hold until the opposite triangle and ignore the colour, and add the
  200 EMA.
- It expects about five signals a year per market.

**Ideas for the PREREG (not decisions).**
- **VS-T.** Triangles only:
  - enter at the next open;
  - the stop at 2 x ATR from the fill (house ATR(14); the script's ATR(10) as a sensitivity);
  - exit at the opposite triangle or the stop;
  - after a stop, wait for the next triangle;
  - LS and LO.
- **Filters.** The video's EMA200 (name EMA or SMA in the plan), F1, F2-1D.
- **Exits.**
  - X0: the opposite triangle or the stop.
  - A colour-based exit (neutral or opposite colour) as a sensitivity.
  - XT2 / XP / XBE.
- **Controls, to see whether the "AI" adds anything:**
  - **VS-F:** every flip of the volume line, no gate.
  - **VS-G:** flips gated by lab(t) alone (WMA20(close) > WMA100(ST) on the flip bar), without the vote.
  - **VS-E:** flips gated by the EMA200 alone.
  - **VS-C:** the circles as entries (the video's "not the signal").
  - **VS-P:** a placebo, with flips gated at random at the triangles' own rate (seeded).
  - **VS-H:** the same pipeline on hl2 with `ta.supertrend(3, 10)`, to isolate the volume weighting.
- **Thinness.**
  - About 5 triangles a year per market gives about 20 per market in a four-year Development window on 4H. That is
    under the house's 30-trade minimum.
  - Plan 1H as well (more flips), or say beforehand how thin rows are read.
- **Holding time.** The trades last months (the video's examples run 176 and 280 days). The house model charges no
  swap (PREREG 4 of study 2); the video charges financing. The PREREG should add Exness swaps or state the omission for
  this script.
- **Claims to check** (information; the video pools 11 markets, 4H, 2021 to October 2026):
  - on BTC, 246 flips and 49 triangles (1 in 5);
  - 339 trades in all, 19% winners, an average winner near 12R;
  - a profit factor of 2.56, and 2.79 with the EMA200;
  - one SOL trade is 42% of the total;
  - about 7R a year per market;
  - on gold, 20 losses in a row over three years; 2024 flat;
  - it holds on forex too.

## 8. Traps for a port

| # | Lines | Trap | Reading to use | The alternative, and what it changes | Hand test |
|---|---|---|---|---|---|
| 1 | 76-83 | Sign | −1 = up (lower band), +1 = down: `ta.supertrend`'s convention | Mixing it with the other scripts' +1 = up: every side inverted. Export `dir` as the script has it and convert only in rule code | — |
| 2 | 56-61 | The centre | WMA_10(C · V) / WMA_10(V), each WMA finished first; the close, not hl2 | hl2, or one WMA of C weighted by V inside a single sum: other bands | 12 hand bars |
| 3 | 66-70 | Warm-up bands | lo = 0.0 on bars 0-8; hi = 0.0 on bar 0, na on 1-8; ST(0) = 0.0. Export these exact values | Starting the bands at na: at the defaults only the exported warm-up values change (and S(107) under trap 6's alternative); no signal moves. Keep the 0.0 values so both ports export the same bits | Bars 0-12 with len = 3 |
| 4 | 66-67 | `nz` fallback | 0.0 (not this bar's raw band, as in Kivanc's script) | The raw band: the warm-up only | — |
| 5 | 76-81 | Direction | +1 while A(t−1) is na; then the branch by exact equality pST == pHi; tests against **this** bar's final bands | The previous bar's bands (Kivanc-style), or A(t) instead of A(t−1): other flips, or a first flip on bar 9 | A bar whose close lies between hi(t) and hi(t−1) |
| 6 | 88 | **S over a series with 0.0 then na** | Reference arithmetic: na while any value in the window is na; first S at bar 108 | TradingView's remark that na values are "ignored": S(107) becomes the weighted mean of ST(0) = 0.0 and bars 9-107 (biased low). Identical from bar 108; it can change lab(107) and so knn / s on bars 107-116 only (no change on synthetic walks). The same choice decides what happens if ST is ever na inside the series (only after a zero-volume window, step 2): the reference blanks S for 100 bars, the alternative does not. Study 1's `wma` refuses series with such an na; port this one with a plain NaN-propagating window | Bars 100-120; an na ST at bar 300 |
| 7 | 57-61, 87-88 | WMA arithmetic | Weights (n − i) · n, newest first, sum / norm | Weights (n − i): the last bits differ on about 70% of bars (synthetic, 0.01 grid). A cumulative-sum WMA differs too | Random bars, compare bits |
| 8 | 93-96, 141-142 | The vote includes the current bar | x_0 = ST(t), y_0 = lab(t) | Leaving bar t out (a "true" prediction): other states on many bars | — |
| 9 | 116-125 | **Tie order** | Stable; equal distances go to the more recent bar | Oldest first: s changes on 1.4-2.6% of synthetic bars. NumPy's default argsort gave the right order on 10 elements in our test, but its tie order is not guaranteed across versions or CPUs: use `kind="stable"` or the literal loop | Two equal distances with different labels at the 3rd / 4th place |
| 10 | 116-125 | na distances | No swap when either is na: na acts as a barrier that no value crosses; knn na on bars 0-10 | Sorting na to the end (NumPy's way). At the defaults this gives the same knn (na on bars 0-10 either way). It differs with k ≤ 2 on bar 9 (where bar 0's 0.0 sits behind the barrier), and wherever ST is na inside the series (only after a zero-volume window) | Bars 9-18 with k = 2; a zero-volume window |
| 11 | 95 | Labels before bar 0 | 0 (the comparison is false) | na: no change at the defaults, because the bars whose window reaches before bar 0 already have na distances (knn na on bars 0-10). It matters only with other inputs | — |
| 12 | 146 | knn == 1 / == 0 exactly | Exact equality; anything else is neutral, na included | A threshold such as ≥ 0.5: a different indicator | Labels (1, 1, 0) → neutral |
| 13 | 146, 178-179 | Colours as state | Port the state s, not colours. At the defaults the three colours are distinct, so the logic is as in step 13 | Equal user colours would change the logic; not at the defaults | — |
| 14 | 25 | n = max(k, n_) | 10 at the defaults; k never exceeds n | — | — |
| 15 | 127-137 | Arithmetic of the vote | w = 1 / (d + 1e-6); ws then tw, in sorted order; knn = ws / tw | — | — |
| 16 | 180-181 | Triangles | The flip bar's own vote must be fully bullish (bearish) | The previous bar's vote, or the colour at any time: other triangles | A flip bar with s = 0 |
| 17 | 152-174 | Cloud | Display only; do not port | — | — |
| 18 | 178-179 | Bar 0 | Circles false on bar 0 | — | — |
| 19 | data | Volume source | Gold tick volume; BTC Binance (sensitivity: Exness ticks) | Section 6 | — |

## 9. Reconciliation checklist

- **Per-bar outputs, bit for bit, na on the same bars:**
  - Wcv, Wv, vw, A, lo, hi, ST, P, S, knn (float64);
  - dir (int8, the script's sign), lab (int8), the three neighbours' original lags (int8), s (int8);
  - start_up, start_dn, tri_up, tri_dn (bool).
- **Event tables.** Flips (bar, dir, ST), triangles and circles.
- **Real bars.** Gold and BTC at 1H, 4H and 1D, from the data start, over whatever spans the PREREG's window guard
  allows (`infra.md` proposes a reverse split). BTC with both volumes.
- **Synthetic bars.**
  - Random walks with integer and decimal volumes, and coarse price grids.
  - Flat stretches, where ST repeats and distances tie.
  - Zero-volume windows of 10+ bars: the na path through the ratchet, S and the vote.
  - len 1, 2 and 10; k = 1, 3 and n; n_ = 1, 3 and 10; all five `maSrc` options; series cut to 0-130 bars.
- **Cross-check.** The equivalent form of section 4 against the literal loop, on every bar from 18.
- **Is the test sharp?** Misread port B on purpose, one reading at a time:
  - weights (n − i);
  - ties oldest-first;
  - an unstable sort;
  - bar t left out of the vote;
  - "na skipped" in S;
  - the direction against the previous bands;
  - the raw-band fallback;
  - lab with ≥;
  - a knn threshold of 0.5;
  - the sign flipped.

  Each must be caught on the real bars or by a hand test.
- **Counts to report, events only and no profit or loss**, on the development window the PREREG names (study 2 used
  2019-2022; `infra.md` proposes 2021-2026 here):
  - flips a year; triangles a year and per flip (the video: 49 of 246 on BTC 4H, 2021-2026); circles a year;
  - the share of bars that are bullish, bearish or neutral;
  - triangles that the lab(t)-only gate (VS-G) also gives;
  - triangles under each BTC volume;
  - bars whose 3rd and 4th distances tie.

## 10. What may still differ from TradingView

1. **BTC's volume.** TradingView on BTCUSDm uses Exness tick volume. The study's Binance volume gives other centres by
   design.
2. **The bars.** The 4H session boundaries and the feed, as for every script.
3. **Native `wma` / `atr` arithmetic.** Last bits only. The exact-equality branch (pST == pHi) compares stored values,
   so it is robust. Distance ties come from identical ST values, which are identical under any arithmetic.
4. **The history start.** TradingView's warm-up artefacts sit at the chart's first bar; ours at the data start.
5. **The live bar.**
6. **The version.** The copy may differ from the 2023 publication (section 1). No signal reads the cloud.

## 11. Porting effort

- **Lines that compute: about 68 of 195** (l.25, 56-61, 63-83, 87-96, 100-137, 141-142, 146, 178-181). At the
  defaults 64 run, since one `switch` branch of five does.
- **The rest.** Inputs take 20 lines, tooltips 12, display about 23 (the cloud 16 of them), alerts 6.
- **A port.** About 150 lines of Python.
  - The per-bar vote is a 10-element sort (45 comparisons). On about 78k BTC 1H bars that takes seconds in plain
    Python and is trivial with numba.
  - The WMA100 can be vectorised the way study 1 does it, which keeps each bar's order of operations.
- **Two ports with hand tests, the reconciliation and the counts:** about 1 to 1.5 days.
- **Risk: medium.** It lies in the warm-up semantics (traps 3, 6, 10), the tie order (trap 9) and the volume choice
  (section 6). None is hard once written down, and each has a hand test.
