# Study 4 (TradeIQ video 3, the Supertrend family) and filter round 2: the survey

Written 28 Nov 2026 in scratch, before any port, rule, pre-registration or backtest of study 4 exists.

**What this is built from.** It condenses the survey pass's files in this folder:
- `transcript.md`: the transcript, read whole;
- the nine porting specs `spec_*.md`;
- `infra.md`: the infrastructure map.

It also uses what studies 1-3, FINAL10 and the earlier Supertrend reports say. Each point names its source.

**What was not done.**
- Nothing was run, no market data was loaded, and no repository file was edited.
- The store was listed by symbol and month folder names only.
- The only arithmetic was on the video's own numbers (section 5.6).
- No third-party code is copied here. Formulas are restated in words, and the transcript is quoted only in phrases of a
  few words.

**Abbreviations.**
- **The scripts:**
  - ST: Supertrend (10, 3);
  - PPST: Pivot Point SuperTrend;
  - RMI: RMI Trend Sniper;
  - PS: Precision Sniper;
  - PMAX: Profit Maximizer (PMax);
  - SMB: Smart Money Breakout Signals;
  - VST: Volume SuperTrend AI;
  - AT: AlphaTrend;
  - HULL: Hull Suite.
- **Measures:** R is the risk of one trade, which in the video's test is the 2 ATR stop distance. PF is profit factor.
  G is gold (XAUUSDm) and B is BTC (BTCUSDm).
- **Windows (section 5.4):** d and v are the two selection halves; e1, e2 and e0 are the exams.

## 0. The answer in brief

1. **What the video is.**
   - **The baseline.** TradeIQ traded every Supertrend (10, 3) signal on 11 markets, on the 4H chart, from January 2021
     to October 2026.
   - **The test,** the same for every script: a signal on a closed candle, entry at the next open, a 2 ATR stop
     (= 1R), no target, and out on the opposite signal or the stop. Costs include financing, and a stress run doubles
     them.
   - **The six.** He ran 51 other indicators through the same test. He kept the six that passed his five checks and
     ranks them by R per trade against Supertrend: 2.2× to 12.9×.
   - **None of the seven scripts is TradeIQ's.** PMax is KivancOzbilgic's, who also wrote the Supertrend he tested.
2. **His own fine print is the real headline.**
   - Per year the six make only about 1.5 times Supertrend's R: 7-9R a year on each market, against 5R.
   - The "10×" is VST, per trade only, and 42% of VST's profit is one Solana trade.
   - The money came from longs on coins and gold in 2021-2026, a rising market. Forex was flat and the stock indexes
     lost.
3. **The files.**
   - All seven scripts of the video are present and complete, and their defaults are the ones he says he used.
   - Two more files, AlphaTrend and Hull Suite, are never mentioned in the video.
   - **The Hull Suite copy is truncated.** It has no plot, colour or alert, so it cannot be ported until the owner sends
     a complete copy.
4. **Porting.**
   - Six of the nine are small, 1-9 engineer-hours each for both ports: ST, PMAX, PPST, RMI, AT and HULL.
   - SMB and VST take 8-12 hours each.
   - PS is large: 2-3 days per port. Its labels depend on its own internal model trade, so the whole model must be
     ported.
   - Ported as specified, no script repaints on closed bars.
   - Four scripts read volume: RMI, AT, VST and PS. For BTC that repeats study 2's volume question.
5. **Claims.** There are 68 numbered claims:
   - 56 are testable on both gold and BTC;
   - 6 more on one of the two, or partly;
   - 3 only on the FX and NASDAQ claim markets;
   - 3 cannot be tested here (for claim 49, only its Solana half).

   **Correction to the claims list.** USDJPYm is in the store from 2017-11, so the video's USDJPY figures become
   information rows. Six of the video's eleven markets are in the store, not seven as `infra.md` says.
6. **Rules.**
   - **For every script:**
     - the video's row (4H, both sides, his filter);
     - long only;
     - 1H and 1D;
     - the script's own trade model, where it has one;
     - controls that ask whether its special part adds anything (the pivots, the EMA cross, volume, the kNN vote, the
       checklist).
   - **Our own combinations cover:**
     - the owner's MA200 idea, as SMA200 against the video's EMA200;
     - a higher-timeframe Supertrend;
     - volume;
     - Hull and AlphaTrend as filters and exits;
     - a direct test of the video's "one filter, never two trend lines" advice.
   - **Size:** about 1,200-1,500 rows, the size of study 2.
7. **Filter round 2 for the bots.**
   - About 34 single filters per design: Supertrend-family states on H1/H4/D1, plus the video's EMA200, ADX20 and daily
     EMA50.
   - They run on the five designs, plus Supertrend-family exits for the Turtle.
   - Development and the yardstick are study 3's.
8. **The split.**
   - The video chose its six and their filters on 2021-2026, with gold and BTC among its markets.
   - Studies 1-3 and FINAL10 have scored other rules in every year from 2017.
   - **Recommended: a reverse split.**
     - Select on 2021-01-01..2026-11-13, in two halves split at 2024-01-01 (close to his).
     - Examine on 2018-11-13..2021-01-01 (both symbols) and on gold 2017-01-01..2018-11-13.
     - Add the never-scored slivers (gold 2016-04..2017-01, BTC 2018-04..2018-11-13) and pre-registered forward
       re-scores.
   - **A relative leg** compares each champion with a matched Supertrend row, so that a trending or ranging window
     cannot decide on its own.
9. **Power.**
   - On 4H an exam window holds about 100 Supertrend trades per symbol, and about 10 VST trades.
   - So the exam can catch failures. It cannot rank the six.
10. **Effort.**
    - About 145-210 engineer-hours, 40-56 of them for Precision Sniper.
    - On study 2's pattern of parallel workflows, about 14-18 hours elapsed for study 4 and round 2 together. Study 2
      went from its frozen pre-registration to its final report in 9.5 hours.
    - Study 4 starts after studies 2 and 3 are committed.
11. **Before the pre-registration.**
    - Nine questions need the owner's answer (section 7.1).
    - About 26 readings must be registered (section 7.2).

## 1. The video in brief

### 1.1 His test

- **Markets and window.**
  - 11 markets: Bitcoin, Ethereum, Solana, BNB, XRP; EURUSD, GBPUSD, USDJPY; gold; the S&P 500 and the NASDAQ.
  - The 4H chart, January 2021 to October 2026: about 5.8 years, or 64.2 market-years.
  - Supertrend is also shown on 1H. His data feeds are not named.
- **The rules, the same for every indicator.**
  - Default settings and no confirmation.
  - A signal on a closed candle, entry at the next open, long and short.
  - A stop 2 ATR from the entry, which is 1R. No target.
  - Out on the opposite signal or the stop.
  - Costs: fees and slippage on crypto, the spread elsewhere, and financing while a trade is held. A stress run
    doubles every cost.
- **His five checks.** An indicator made the list only if it passed all five:
  1. at least 200 trades;
  2. profitable in the older half of the data and in the newer half;
  3. profitable on most markets;
  4. profitable without its five best trades;
  5. profitable with the costs doubled.

  Six of 51 passed. He ranks them by R per trade as a multiple of Supertrend's.
- **"R a year on each market"** is the pooled R spread evenly over 64.2 market-years. It is not a per-market median
  (`transcript.md` 3.4).

### 1.2 The six, and his numbers

These are his figures, pooled over 11 markets on 4H (`transcript.md` 2.1).

| Rank | Script (author) | R per trade vs ST | Trades | Win % | PF | R a year per market | Same at costs ×2 | His filter, and the PF it gives |
|---|---|---|---|---|---|---|---|---|
| baseline | Supertrend (KivancOzbilgic) | 1× (about 0.1R) | 3,022 | about 30 | 1.17 | 5 | 2.3 | EMA200 → 1.33 |
| 6 | PPST (LonesomeTheBlue) | 2.2× | 1,935 | 27 | 1.34 | 7 | 4.9 | EMA200 → 1.47 in both halves |
| 5 | RMI (TZack88) | 2.5× | 1,822 | 26 | 1.37 | 7.5 | 5.3 | ADX > 20 → 1.43 |
| 4 | PS (WillyAlgoTrader) | 2.7× | 1,987 | 26 | 1.42 | 9 | 6.5 | EMA200 → 1.59 |
| 3 | PMAX (KivancOzbilgic) | 3.4× | 1,369 | 26 | 1.49 | almost 8 | 5.9 | daily EMA50 → 1.63; long only |
| 2 | SMB (AlgoAlpha) | 4.4× | 965 | 20 | 1.58 | 7 | 5.3 | ADX > 20 → 1.65 |
| 1 | VST (Zeiierman) | 12.9× (7.5× without one trade) | 339 | 19 | 2.56 | about 7 | not given | EMA200 → 2.79 |

### 1.3 What he concludes and recommends

- **Supertrend.**
  - It "made money, barely".
  - It whipsaws in ranges: four in ten trades are losers closed within two days.
  - It trades about once a week, so costs hurt it: doubling them removes 55% of its profit.
  - It loses on 1H (PF 0.98).
  - An EMA200 direction filter lifts it to PF 1.33 with half the trades.
  - Filtered, it is a fair tool, but no better than the first three of the six unfiltered.
- **The six.**
  - They win less often than Supertrend (19-27% against about 30%), but "they win bigger".
  - On the five coins each has a PF above 1.7; on gold the PFs lie between 1.4 and 2.8.
  - Forex was flat for five of the six; VST was the exception at 2.27.
  - The stock indexes lost for five of the six; PS stayed just above water.
  - Longs carried all six. For five of them the shorts were about break-even or worse.
  - 2025 was flat or negative for most of them.
- **His recipe.**
  - Pick one script, not all six: they mostly catch the same big moves.
  - Add one filter from another family: EMA200 for trend, ADX for strength, or the daily chart. Never stack two trend
    lines: "they'll just agree".
  - Trade on 4H: wait for the close, enter at the next open, put the stop 2 ATR away, set no target, and exit on the
    opposite signal, "not before".
  - Risk 1% a trade or less, and expect ten losses in a row.
- **Which script for which trader:**
  - the Supertrend look: PMAX or PPST;
  - the most profit a year: PS;
  - breakouts: SMB;
  - momentum: RMI;
  - forex, or the fewest trades: VST.
- **Markets.** PMAX and SMB on coins and gold only; RMI kept off stock indexes; VST for forex.

### 1.4 What to keep in mind before replicating

- **Selection on the same data.**
  - The six are the best of 52 indicators, chosen on the data that produced the numbers.
  - Each filter is the best of an unstated number he tried.
  - His halves and his "without the five best trades" check guard against part of that, not all of it.
- **A bull market.** His best markets (the coins and gold) rose in 2021-2026, and the longs made the money.
- **His ranking favours slow scripts.** R per trade grows as trades get fewer and longer. Per year the six differ
  much less: 7-9R against Supertrend's 5R.
- **Profit sits in a few trades.**
  - VST's best trade is 42% of its profit.
  - RMI's two best trades are about 190R of about 480R.
  - Supertrend's five best trades are about 85% of its R.
- **Costs.**
  - He charges financing and stresses costs ×2.
  - Studies 1 and 2 charged Exness spreads with no swap and stressed them ×1.5. Study 1's PREREG gives the reason:
    the Standard account is swap-free.
- **Versions.**
  - PS's file is version 2.3.0. Its default evidence ("v2 decorrelated") does not match his spoken list (trend, RSI,
    MACD, ADX, volume). That list is the "v1 legacy" set, which the tooltip assigns to version 2.2.
  - VST's file is a later revision of the August 2023 script.
  - So neither file may be what he ran.
- **His numbers hang together.** Under the pooled reading of "R a year on each market" they reproduce each other. The
  implied multiples are 2.19, 2.49, 2.74, 3.44, 4.38 and 12.96, against his 2.2, 2.5, 2.7, 3.4, 4.4 and 12.9. Losers
  average about 1R, and Supertrend's doubled costs take 54% (his 55%) (`transcript.md` 3.4).
- **Garbled in the transcript.**
  - RMI's newer-half PF: it must be below 1.37.
  - VST's BNB prices.
  - PS's ETH exit: "228" must mean about $2,280.
- **His products.** Five private TradeIQ MAX indicators and a paid backtest sheet are advertised. Neither is tested
  in the video, and we have neither.
- **Supertrend has been run in this repository before.**
  - `backtest_results/improve/external_strategies.md`: Supertrend (10, 3) on H4 was gold's best rule of 2023-2026, but
    it lost in 2021 (−$24 a quarter) and in 2022 (−$48). Its profit came from the 2025-26 rally.
  - `backtest_results/final10/FINAL10.md`:
    - "V3-lite + H4 Supertrend filter" is the weakest gold hybrid (a 35.5% drawdown over 8 years as the bot runs it);
    - "Supertrend + bot votes" on BTC lost in the last year.
  - `backtest_results/silver/SILVER.md`: C12, Supertrend H4 (10, 4.0), was the best near miss. Its neighbour (10, 3.0)
    lost $239.
  - `backtest_results/ladder/LADDER.md`: a Supertrend H4 gate removed the wipes, but the ladder still lost about
    20-30% a quarter.

## 2. The nine scripts in one table

Details, traps and hand tests are in each `spec_*.md`. "Effort" is for two independent ports, their hand tests and
the bit-for-bit reconciliation, in the specs' engineer-hours.

| Script (module key): origin | What it computes | Signal a rule trades | Repaint risk | Data needs | Effort |
|---|---|---|---|---|---|
| **Supertrend** (`supertrend`): the baseline. Pine v4, 37 lines. No author or licence line; the video says KivancOzbilgic | A line 3 × ATR(10) (Wilder) below or above the candle middle (hl2). Each band ratchets while the previous close stays on its side. The trend flips when the close crosses the previous bar's final opposite band. +1 = up | Buy / Sell at every flip; always in the market | None on closed bars. The flip level is known a bar ahead, so an intrabar line-stop version exists. Live-bar flicker only | Bid OHLC of the chart timeframe | 14 computing lines, about 40 lines of Python, about 4 h. Low risk. It is not `ta.supertrend`: the flip uses the previous final band, and the warm-up fallback is the raw band. `external._supertrend` is a third opinion on flip bars |
| **Pivot Point SuperTrend** (`pivotst`): #6. LonesomeTheBlue, v4, MPL 2.0, 70 lines | Pivots with 2 bars on each side, confirmed 2 bars late. They feed a centre that takes two parts old centre to one part new pivot; the high wins on a bar with both. Bands 3 × ATR(10) from the centre ratchet. The trend flips when the close crosses the previous bar's band. The test does not depend on the current trend | Buy / Sell at every flip; always in | None on closed bars. Pivots are used only from their confirmation bar. The pivot marks and S/R circles are drawn 2 bars back (display only) | Bid OHLC | 24 computing lines, about 70 lines, 4-8 h. Most of it goes to counting the four pivot-tie readings. Low risk |
| **RMI Trend Sniper** (`rmi`): #5. TZack88, v5, MPL 2.0, 101 lines | The average of RSI(14) of the close and MFI(14) of hlc3 (no real RMI). The state turns positive on a strict cross above 66 while EMA(5) is rising. It turns negative on any bar below 30 while EMA(5) is falling, a level test. The band around price is display only | BUY / SELL at state changes. After the first one they strictly alternate | None on closed bars. The `var` state can flicker on the live bar. A 500-label cap applies to the display | OHLC and volume (the MFI half). Gold: tick volume. BTC: Binance volume, with Exness ticks as a sensitivity | 9 statements drive the signals. 80-120 lines, 5-7 h. Low risk. The MFI is shared with AT |
| **Precision Sniper** (`sniper`): #4. WillyAlgoTrader v2.3.0, v6, no licence line, 1,023 lines | An EMA cross. On 4H the Auto preset is Swing: EMAs 13/34 and a trend EMA 89. The cross is gated in order (next row) | Long / Short labels, plus one "RE" re-entry per cross cycle | None: it runs on confirmed bars only. Its HTF reads take the previous HTF bar (`htf_at_open`). The labels are path-dependent. The model fills at the signal close (optimistic, statistics only) | OHLC and volume (volume changes the evidence count), a daily VWAP anchor, the tick size, bar open and close times | About 280 computing lines. 2-3 days per port plus 1 day of reconciliation: 40-56 h. High risk: tick rounding, the four-phase engine, re-entries |
| (PS, continued) | **The gate, in order:** warm-up; a date window (entries only from 2020-01-01 by default); a volatility skip; momentum; an RSI(21) band at about 70.4 / 29.6; evidence of at least 5 of 7 factors; a valid plan. **The v2 factors:** trend side, trend slope, a 10-bar structure break, MACD acceleration, ADX/DI, a volume spike, the session VWAP. **The internal model trade** decides which labels print: a stop of 2.5 × ATR(20), widened to the 11-bar structure and capped at 3.75 ATR; targets at 1, 2 and 3R; step stops; all out at the third target | | | | |
| **PMax** (`pmax`): #3. KivancOzbilgic, v4, MPL 2.0, 105 lines. An indicator, despite the file name | Supertrend bands 3 × ATR(10) around EMA(10) of hl2. The ratchet tests the current EMA against the previous final band. The direction flips when the EMA crosses the previous band | Buy / Sell where the EMA crosses PMax. With ATR > 0 these are exactly the flips, an invariant each port can assert. Always in | None on closed bars | Bid OHLC | About 15 lines at the defaults, 5-9 h. Very low risk, but no Supertrend helper can be reused |
| **Smart Money Breakout Signals** (`smb`): #2. AlgoAlpha, v6, MPL 2.0, 290 lines | Pivots with 25 bars on each side, known 25 bars late (about four days on 4H), arm a level once. The first close strictly beyond it is a break: BOS, or CHoCH after an opposite break. A newer swing replaces an unbroken one. Targets and a stop sit at the broken level ± 1/9, 2/9 and 1/3 of the swing-to-break range | Bullish / bearish breaks. Two of one side in a row are possible | None at the close. The lines and labels are drawn back to the swing (display). `alert()` fires intrabar. Its statistics table is biased by look-ahead | OHLC only | About 35 lines for the signals, 75 with the levels. 9-10 h. Low risk. It reuses the strict pivot helper |
| **Volume SuperTrend AI** (`vstai`): #1. Zeiierman, v6, CC BY-NC-SA 4.0 (non-commercial), 195 lines. A later revision | `ta.supertrend`-style bands 3 × ATR(10) around WMA10(close × volume) / WMA10(volume). **The kNN vote:** among the last 10 values of the line (the current one included), the 3 nearest vote with the label "WMA20(close) > WMA100(line)". The vote is exactly up or down only when all three agree | Triangles: a flip of the line on a bar whose vote fully agrees with it. That is one flip in five on BTC, per the video | None on closed bars. The vote includes the current bar: self-inclusion, not look-ahead. The flip uses this bar's bands, so no level is known a bar ahead. Warm-up artefacts until bar 117 | OHLC and volume, which is load-bearing. Gold: tick volume. BTC: Binance, with Exness ticks as a sensitivity. Assert that no 10-bar window has zero volume | About 68 computing lines, about 150 lines of Python, 8-12 h. Medium risk: −1 = up; a stable tie order to the newer bar; the reference WMA weights; the na barrier |
| **AlphaTrend** (`alphatrend`): not in the video. KivancOzbilgic, v5, MPL 2.0, 56 lines | The ATR is SMA(14) of the true range (na on bar 0). In up mode (MFI(14) of hlc3 ≥ 50; RSI(14) with the no-volume switch) the line is max(low − ATR, previous); in down mode, min(high + ATR, previous). A missing previous value counts as 0, so the line can sit at 0 at the start. Raw signals come when the line crosses its own value two bars back. The labels are filtered with `barssince` | BUY / SELL labels; a side can repeat. "Confirmed" alarms come one bar later | None on closed bars. The path memory makes values depend on the data start until a merge bar | OHLC and volume, or the RSI switch (no volume) | About 12 statements plus 10 alert conditions. 80-120 lines plus the MFI and bars-since helpers, 5-7 h. Low risk |
| **Hull Suite** (`hull`): not in the video. InSilico, v4, no licence line. **Truncated** after the Hull average | HMA(55) = WMA(2·WMA(close, 27) − WMA(close, 55), 7). The square root of n is rounded, not floored. Thma and Ehma modes exist. **The missing tail** of the public script plots the line, has two "trending" alerts (HULL against HULL two bars back) and an optional 4H request | Provisional: the trending up / down crossovers, or the colour state | None at the defaults. The optional HTF mode repaints live and flickers | The close only | 6 statements in the copy and about 6 in the tail. 1-2 h once a complete copy exists. **Blocked until then** |

**Shared pieces, and traps that cross scripts.**
- **Three sign conventions.** ST, PPST and PMAX use +1 = up. VST uses −1 = up (`ta.supertrend`'s convention). Export
  each script's own sign and convert only in rule code.
- **Three Supertrend algorithms. Never reuse one helper for another.**
  - Kivanc's (ST): the flip is tested against the previous final band, and the warm-up fallback is the raw band.
  - PPST's: no fallback, and the trend test does not depend on the current trend.
  - VST's (`ta.supertrend`): the flip is tested against the current band, and the fallback is 0.
- **New Pine built-ins,** each to be written twice:
  - `ta.mfi` (RMI, AT);
  - `ta.barssince` (AT);
  - `ta.vwma` and the kNN step (VST);
  - `ta.vwap` with a daily anchor, `ta.macd` and session membership (PS).

  All three pivot scripts use equal left and right lengths at their defaults, so the house's strict symmetric pivot
  helper (`tradeiq2_ind_wyckoff.pivots`) covers them. Asymmetric pivots are not needed.
- **Verified helpers to reuse:**
  - `tradeiq_ind`: `sma`, `ema`, `rma`, `wma`, `hma` (equal to the Hull script's at length 55, but not at every
    length), `rsi`, `atr`, the crosses and `math_sum`;
  - study 2's DMI (`tradeiq2_ind_coil.adx` / `_dmi`), for PS's ADX factor and the ADX20 filter.
- **True range on bar 0.** `ta.tr` (na on bar 0) feeds AT's SMA ATR, ST's SMA option and the DMI. `ta.atr` uses
  high − low on bar 0. Every port must say which one it uses.
- **Warm-up.** Every port starts at the data start and runs at least 500 bars before the first scored bar.

## 3. Testable claims

The numbered list, with what to measure for each claim, is in `transcript.md` section 4. The combinations he builds
(K1-K10) are in its section 5.

### 3.1 What can be tested

| Testable on | Claims | Count |
|---|---|---|
| Gold and BTC | 1-11, 12 (three of its eight episodes), 13-17, 19-23, 25-29, 31-34, 36-38, 40-41, 43-48, 50-51, 53-56, 59-63, 66-68 | 56 |
| Gold only | 42 (the PS long of October 2026) | 1 |
| BTC only | 57 (the SMB short of June 2022), 58 (VST's flip and triangle counts) | 2 |
| Gold, plus information on the claim markets | 30, 39, 52 (gold PF, plus an index or FX PF) | 3 |
| Information only (EURUSDm, GBPUSDm, USDJPYm, USTECm) | 18, 24, 64 | 3 |
| Not testable (BNB, SOL) | 35, 65; 49's SOL half | 3 |

**A correction to `transcript.md`.** It took the claim markets from study 2's `DATA.md`, which lists USTECm, EURUSDm
and GBPUSDm. But the store also holds USDJPYm, from 2017-11 to 2026-11 (`infra.md` F7, and the store's folders). So
these gain an information row on USDJPYm:
- claim 12's USDJPY episode (Supertrend, September 2021: six trades in six weeks, −2R);
- claim 49's USDJPY half (PMAX, September 2021: +8.2R);
- the USDJPY figures in claims 18 and 64 (VST 3.3).

R and PF need no currency conversion. Six of the video's eleven markets are in the store: BTC, gold, EURUSD, GBPUSD,
USDJPY and the NASDAQ (USTECm). `infra.md` 4.5 and its gaps say seven; that is a slip.

### 3.2 The claims by group

| Group | Claims | What he says (his figures) | What to measure |
|---|---|---|---|
| Supertrend | 1-12 | about 0.1R a trade, about 30% winners, PF 1.17, 5R a year per market; mean winner 2.5R; four trades in ten are losers closed within two days; about one trade a week; costs ×2 remove 55%; 48R of about 320R without the five best trades; 1H loses (PF 0.98 on more than 11,000 trades); EMA200 → PF 1.33 with almost half the trades; nothing in 2025; episodes | the same figures per market; 1H against 4H; filtered against plain; R in 2025; the episode trades |
| The six together | 13-22 | each beats ST per trade (2.2× to 12.9×, in that order); about 1.5× ST per year and above 2× at costs ×2; win less, win bigger; each passes the five checks; PF above 1.7 on the coins and 1.4-2.8 on gold; forex flat, indexes lose; longs carry; 2025 flat or negative; the same big moves; about one in four win, ten losses in a row happen | ratios to ST at ×1 and ×2; the order; the five checks per market; R by side; R in 2025; date overlap of the best trades; losing streaks |
| PPST | 23-27 | 1,935 trades, 27% winners, PF 1.34, 7R a year (4.9 at ×2), mean winner 3.4R; EMA200 → 1.47 in both halves; the line moves only with the swings; gold March 2023: one trade instead of seven; a BTC failure in October 2026 | the figures; the line's moves without a new pivot (expected to fail, because the ATR term moves it on every bar); flips against ST; the episodes |
| RMI | 28-35 | 1,822 trades, 26%, PF 1.37, 7.5R a year, 5.3 at ×2; 1.48 in the older half; gold 1.45; 2022 −72R and 2025 −59R; ADX > 20 → 1.43; ADX beats another oscillator; it sells late, so winners run | the figures; PF per half; R by year; ADX20 against a pre-set oscillator filter; holding time and mean winner against ST |
| PS | 36-42 | 9R a year (the best), 1,987 trades, 26%, PF 1.42, 6.5 at ×2; costs ×2 take only 27%; almost 300R without the five best; 9 of 11 markets, gold 1.6, the only one above water on the NASDAQ; longs only; a 20-loss streak; EMA200 → 1.59; a gold failure in October 2026 | the figures; the cost share against ST's; R minus the five best; R by side; streaks; filtered against plain |
| PMAX | 43-49 | 1,369 trades, 26%, PF 1.49, almost 8R a year, 5.9 at ×2; all coins and gold profitable, BTC 1.8; shorts lose; older half 1.81 against 1.2; 2025 lost; trade the buys; daily EMA50 → 1.63 (newer half 1.53); flips less than ST | PF on BTC (1.8) and gold (above 1); R by side; PF per half; long only against both sides; D50 per half; flips a year against ST |
| SMB | 50-57 | 965 trades, PF 1.58, 7R a year, 5.3 at ×2; 20% winners, winners more than 6× losers; gold 2.8; a 26-loss streak over a year; ADX > 20 → 1.65; silent in ranges, about 4 days late; take every signal; BTC June 2022 short +4.5R | the figures; the winner/loser ratio; the streak and its span; ADX20; ST's signals in stretches without an SMB signal; the lag; random-skip draws set in advance; the episode |
| VST | 58-65 | BTC 246 flips, 49 triangles; 339 trades, 19%, mean winner almost 12R, PF 2.56, 9 of 11 markets; its shorts made money; one SOL trade is 42%; gold lost 20 in a row over 3 years, 2024 flat; EMA200 → 2.79; the forex one | flip and triangle counts on BTC (they depend on the volume source); the figures; R of shorts; the share of the best trade; the gold streak; R in 2024; filtered against plain |
| His advice | 66-68 | one filter from another family, never a second trend line; exit on the opposite signal and use no target; 4H beats 1H | script plus a second trend line against script plus EMA200 or ADX; his exit against the scripts' own targets and fixed 2R / 3R; the six on 1H against 4H |

### 3.3 Figures that apply to our markets directly

- **Gold PFs:** RMI 1.45, PS 1.6, SMB 2.8, PMAX above 1, and all six between 1.4 and 2.8.
- **BTC:** PMAX's PF 1.8, and VST's 246 flips with 49 triangles.
- **Coins:** each of the six above PF 1.7 on the five coins. He does not say whether that is per coin or pooled, so the
  BTC figure is a weak check.
- **VST on gold:** 20 losses in a row over three years, and a flat 2024.
- **Episodes:**
  - **BTC:**
    - January 2023, a Supertrend buy at about $16,860, sold near $22,800, about 30R;
    - June 2022, five Supertrend losers (−3.7R), and the SMB short at $27,550 covered at $22,130 (+4.5R);
    - October 2026, a PPST buy stopped within a day.
  - **Gold:**
    - March 2023, a Supertrend breakout of +6.8R followed by six non-profitable trades, and the PPST trade from $1,863
      to about $1,995 (+6.3R);
    - October 2026, a PS long stopped on the Monday.
  - These are checks of the ports on his feed's prices as much as of the scripts: his feed and 4H session boundaries
    are not ours.

### 3.4 Claims the code settles (no data needed)

- **PPST.** "One fast candle does not move it" is true of the centre. It is not true of the line, which carries an
  ATR term that changes on every bar.
- **RMI.** The sell also needs the 5-bar EMA to be falling. The "fast EMA" is EMA(5).
- **PS (version 2.3.0).**
  - The RSI is only a veto on extremes.
  - The MACD factor is its acceleration, not its sign.
  - Three factors he never mentions are added: the trend slope, a structure break and the VWAP.
- **PMAX.** Its EMA is of hl2, not of the close.
- **SMB, VST and ST.** As he describes them. One trivial slip: SMB's line to the breaking candle is solid, and the
  target lines are the dashed ones.

### 3.5 How to grade a claim (a proposal for the pre-registration)

- **Window and markets.**
  - Claims are a **replication on his own window** (2021-01-01 to 2026-11-01), per market, not an exam: he selected on
    those data.
  - Each pooled figure becomes, on gold and on BTC, a check of the same direction and of a similar size.
  - The claim markets are information only.
- **Verdict words:** "holds", "does not hold", "cannot be tested here". The tolerances are fixed in advance:
  - a PF or ratio claim holds when ours is on the same side of its boundary (PF above or below 1; a ratio above or
    below 1) and within ±25% of his figure;
  - an ordering claim (13) holds when the rank correlation of the six on that market is positive;
  - a "most" claim holds at 4 of 6 or more.
- **After the freeze,** the same table on e1 is information.

## 4. Candidate rules

### 4.1 The video's protocol, mapped to the harness

Each point maps onto study 2's engine (`infra.md` 3.1).
- **Decision.** At the close of the signal bar.
- **Fill.**
  - At the next M1 open: a buy at the ask, a sell at the bid.
  - One extra spread on every stop fill.
  - A gap through the stop fills at the open.
- **Stop.** 2 × ATR from the fill, which is 1R. The proposed ATR is the house `ta.atr(14)` of the signal timeframe;
  the script's own ATR is a sensitivity.
- **Exit.** No target. Out at the opposite signal, reversing at the same M1 open as study 2's RIB X0, or at the stop.
- **Event rule.**
  - A same-side signal while in a trade is ignored.
  - After a stop, the rule stays flat until the next signal of either side.
  - For the scripts that alternate (ST, PPST, PMAX, RMI) that next signal is always the opposite one.
- **Filters gate entries only.** A filter-blocked opposite signal still closes the open trade, as study 2's PREREG 5
  defines event filters. This is a reading to register: his rules leave it open.
- **Costs.**
  - Exness spreads at ×1.0, ×1.5 (the house stress) and ×2.0 (his fifth check).
  - No swap, the house model: the Standard account is swap-free (study 1's PREREG 4). A swap row is a sensitivity
    only if the owner says the long holds are charged.
- **R.** P/L divided by (k × risk), after costs: the harness's `r_stats`, the same R as the video's.
- **New scores,** beside study 2's:
  - R per trade and R per year;
  - net and R without the five best trades;
  - the longest losing streak and the R it lost;
  - the share of trades that lose and close within 2 days;
  - flips a year.

### 4.2 Rule families per script

Each family is also run long only (LO), on 1H, 4H and 1D, and with the common filter set of 4.3. Rows marked
"sensitivity" are scored but never selected.

| Family | The video's rows | The script's own model | Controls: does its special part help? | Sensitivities |
|---|---|---|---|---|
| ST | ST-LS 4H, no filter: the baseline of every relative check. ST-LS 4H E200 (K1). ST-LS 1H (K2) | ST-SAR: always in, no stop | `ta.supertrend(3, 10)`, a different band algorithm; buy-and-hold | stop on ATR(10); XTL, the line as an intrabar stop |
| PPST | PP-LS 4H; PP-LS 4H E200 (K3) | PP-SAR | ST on the same bars and exits: does anchoring on pivots help? | the other three pivot-tie readings; XTL on the previous bar's line |
| RMI | RMI-S 4H; RMI-S 4H ADX20 (K4) | RMI-LO (the script's "spot" alerts); RMI-ST, the state with no stop | RMI-R: RSI(14) alone in place of the RSI/MFI average (does volume help?). RMI-O: a pre-set oscillator filter, RSI(14) on the trade's side of 50, against ADX20 (claim 33) | BTC on Exness tick volume |
| PS | SNP-LS 4H (Auto); SNP-LS 4H E200 (K5); SNP-LO | SNP-M: its own stop, three targets and step stops, filled at the next open. SNP-A (A+ only), SNP-AA (A+ and A) | the 13/34 EMA cross alone, under the video's protocol: does the checklist help? | evidence model v1 (his spoken list); BTC tick volume; the VWAP day at 17:00 New York; the start date (question 8 of 7.1) |
| PMAX | PMAX-LS 4H; PMAX-LO 4H (K6); PMAX-LO 4H D50 (K7) | PMAX-SAR | ST on the same bars: does crossing with an EMA help? | stop on ATR(10); D50 readings (b) and (c); the hl2 / PMax price cross as an earlier exit |
| SMB | SMB-LS 4H, every signal; SMB-LS 4H ADX20 (K8) | SMB-X: its stop and far target as absolute levels, or equal sub-legs at the inner targets | a plain channel break, a close beyond the 50-bar high or low (ours): does "smart money" structure beat a channel? Random-skip draws set in advance (claim 56) | 1H and 1D (the 25-bar delay changes the rule); ADX ≥ 20 |
| VST | VS-T 4H: triangles only, held to the opposite triangle. VS-T 4H E200 (K9) | VS-C: the circles ("not the signal") | VS-F, every flip; VS-G, the label gate alone, without the vote; VS-E, the EMA200 gate alone; VS-P, a seeded random gate at the triangles' rate; VS-H, hl2 with `ta.supertrend(3, 10)` and the same gate (does volume weighting help?) | BTC on Exness ticks; an exit on the colour; 1H, which needs to be eligible because 4H is thin (section 5.6) |
| AT | AT-L 4H, the video's protocol (no claim of his) | AT-C, the Confirmed alarm one bar later; AT-X, exit on a close across the line | AT-R, the script's RSI switch: does volume help? | the reading for repeated same-side labels |
| HULL | HULL-S 4H, length 55: blocked until the tail is confirmed | HULL-C, the colour state | none | the Thma and Ehma modes (not eligible) |

### 4.3 The filters

| Id | Definition | Note |
|---|---|---|
| F0 | none | |
| E200 | long only while the close is above EMA(200) of the signal timeframe; short only while below | the video's filter (an EMA) |
| E200-4H / E200-1D | the same, on the last closed 4H or 1D bar | |
| F1, F2-4H, F2-1D | the house SMA200 filters of studies 1 and 2 | the owner's MA200, run beside E200 |
| ADX20 | ADX(14, 14) above 20 at the signal bar, from study 2's DMI port; both sides allowed | strict or ≥ is a reading |
| D50 | the decision close against the EMA(50) of the last closed 1D bar (reading a) | PMAX's advice. Readings (b), the daily close against its own EMA(50), and (c), the slope, are sensitivities |
| STH | the Supertrend (10, 3) direction of the last closed higher bar: 4H for 1H rules, 1D for 4H rules | ours |
| VOL | volume above its SMA(20) at the signal bar | ours; only on breakouts (C5) |
| LO | long only | |
| FR, FS | study 2's higher-timeframe ribbon and Market Structure Dashboard bias | partners of C7 |

### 4.4 Our own combinations

| # | Combination | Why |
|---|---|---|
| C1 | **MA200 on the Supertrend family:** ST, PPST and PMAX × {F1, F2-4H (1H rules), F2-1D, E200, E200-4H, E200-1D} | the owner's MA200 request (study 3); the video's EMA200 (K1, K3, K5, K9); study 1's lesson that MA200 helped BTC. It puts the EMA and the SMA head to head |
| C2 | **A higher-timeframe Supertrend (STH)** on every script's 1H and 4H rows | the video's "trade 4H, below is worse"; study 1's finding that the 4H MA200 on 1H rules helped BTC |
| C3 | **Two trend lines** (claim 66): PMAX × PPST agreement, ST × PMAX, and each script × HULL-F (the side of HMA(200)) | each against the same script × E200 or ADX20. The video says two trend lines "just agree": a direct test of his advice |
| C4 | **His filters cross-applied:** ADX20 and D50 on every script | he reports each filter on one or two scripts only; claim 66 is general |
| C5 | **Volume:** the three matched controls (RMI-R, AT-R, VS-H), and VOL on SMB's breakouts | does volume add anything, on gold's tick volume and on BTC's Binance volume? (study 2's ORB claim 7 asked the same) |
| C6 | **Exits:** XTL (the script's own line as an intrabar trailing stop, where the level is known a bar ahead: ST, PPST, PMAX, AT); fixed 2R and 3R targets (claim 67); XBE; the AlphaTrend line as the trailing exit of SMB's and PS's entries | his "no target, not before" against the alternatives; a slow entry with a fast trail |
| C7 | **Study 2's tools as partners:** the six × FS and × FR; Heikin Ashi's M2 overlay on the best trend rows | **Not clean on e1 / e2.** Study 3's exam found MSD-D1 helping gold Top 2 in T1 and T2. Study 2's only gold champion to pass both of its exams was a 4H HA-MANAGED M2 row. So these partners are chosen knowing results on the exam windows. Label them, and give them a verdict on e0 and the forward window only |
| C8 | **Long only everywhere** | the video's "longs carried all six"; the bots' own experience on gold |
| C9 | **His recipe (K10) as one row per script:** its video filter, 4H, his protocol | "trade it as tested" |

**Size.**
- **Rows per symbol, about 600:**
  - the base set: 9 families × 3 timeframes × 2 sides × 5-7 filters, about 340;
  - the 4H exit sensitivities, about 120;
  - the scripts' own models and controls, about 60;
  - the combinations, about 90.
- **The claim markets:** about 100-150 information rows.
- **In all:** about 1,200-1,500 rows, the size of study 2's 1,543. Study 2's 1,543 ran in about two minutes; the cost
  is in the ports.
- **Selection, as study 2:**
  - families: the nine scripts, plus COMBO for C3-C7;
  - champions: the best qualifier per symbol and family by P/DD over d + v;
  - finalists: the three best champions per symbol, at most one per script.

### 4.5 Filters for the bots' designs (filter round 2)

**The bases.**
- The five designs as FINAL10 published them: gold V3-lite, Top 1 and Top 2; BTC Top 2 and the Turtle.
- Optionally, gold Top 2 + SLOPE100-D1 and Top 2 + MSD-D1 as stacked bases. Study 3's exam found that only these
  pass T1 and T2. That is knowledge of T1 and T2 results, so stacked bases get a verdict on T0 and the forward window
  only.

**How a filter applies.** As in study 3: through `fast.run(..., regime=...)` with no engine edit. Values come from
closed bars only, and a filter can only block a new basket.

| Id | A long is allowed when (shorts are the mirror) | Timeframes | Count |
|---|---|---|---|
| ST | the Supertrend (10, 3) direction is up | H1, H4, D1 | 3 |
| PMAX | the PMax direction is up | H1, H4, D1 | 3 |
| PPST | the PPST trend is up | H1, H4, D1 | 3 |
| AT | the AlphaTrend line is above its value two bars back (its fill colour) | H1, H4, D1 | 3 |
| RMI | the RMI state is positive | H1, H4, D1 | 3 |
| HMA | HMA(55) is above its value two bars back. This is our reading: it needs only the part of the Hull copy we have | H1, H4, D1 | 3 |
| VST | the VST direction is up (−1 in its own sign) | H1, H4, D1 | 3 |
| PSX | PS's trend state: fast EMA above slow EMA, and the close above the trend EMA, with that timeframe's preset. It needs no internal model | H1, H4, D1 | 3 |
| SMB | the last break was bullish | H1, H4, D1 | 3 |
| E200 | the close is above EMA(200) | H1, H4, D1 | 3 |
| ADX20 | ADX(14) is above 20. Both sides are allowed then, and neither when it is not | H1, H4, D1 | 3 |
| D-E50 | the last closed daily close is above its EMA(50) | D1 | 1 |

**Size.**
- 34 single filters per design, so 170 on the five designs, or 238 with the stacked bases.
- Up to 3 pairs per design, by study 3's stage-2 rule.
- 7 Turtle exits: an exit at the ST, PMAX or PPST flip against the position on H4 and D1, and at AT's on D1. They go
  through `bot_filters.turtle_exit_plan`, with no edit of `external.py`.
- **In all: about 190-270 variants.**

**Scoring, as study 3.**
- Development, the yardstick, "better", the candidates, the raw-tick confirmation (8 timings) and the pass rule are
  all study 3's.
- Multiple testing counts rounds 1 and 2 together.

**Not clean, to be disclosed.**
- V3-lite × ST-H4 is in effect FINAL10's #10 hybrid. FINAL10's "new" window is T1.
- BTC's "Supertrend + bot votes" (FINAL10) is a related design.
- The ladder's Supertrend H4 gate is related at the level of the idea.

**Memory** (`infra.md` 6). A gold per-second prepare of 2021-2026 takes about 2.7 GB, and BTC's about twice that. Run
one design at a time, and BTC alone.

## 5. The data split

### 5.1 What has already been used

| Span | Gold | BTC | Used by |
|---|---|---|---|
| 2016 | warm-up only | (no data) | never scored |
| 2017-01 to 2018-11-12 | study 2's Early exam (every gold row; base rate 13%) and study 3's T2 | warm-up only | studies 2 and 3 |
| 2018-11-13 to 2020-12 | the Development data of studies 1 and 2 (2019-2022); study 3's T1; FINAL10's "new" and 8-year windows (Supertrend H4 hybrids included); the ladder | the same, from 2018-11-13 | studies 1-3, FINAL10, the ladder |
| 2021 to 2024-06 | the Development and Validation data of studies 1 and 2; study 3's Development; **the video's selection** | the same | everyone |
| 2024-07 to the data end | the hold-out of studies 1 and 2 (study 2: every row; base rate gold 63%, BTC 22%); study 3's Development; **the video's selection to 2026-10** | the same | everyone |
| 2026-11-13 to the data end | about two weeks, inside study 2's hold-out; study 3's forward | the same | studies 2 and 3 |

### 5.2 What is left

- **Never scored by anyone.**
  - Gold 2016-04-01 to 2017-01-01: 0.75 years, with the 27-29 June 2016 archive hole inside it.
  - BTC 2018-04-01 to 2018-11-13: 0.62 years, in the 2018 crash regime. Its archive quality is unchecked.
- **The forward data after 2026-11-13.** Two weeks now, and it grows only with time.
- **Transfer markets** the video never used: XAGUSDm, AUDUSDm, NZDUSDm, USDCADm, USDCHFm (from 2017-11) and US30m
  (from 2020-06). They are not the owner's markets, and the classic Supertrend has been run on silver.
- **Pre-2021 for these rules.** Before 2021 no Supertrend-family rule has been run under the video's protocol, and the
  window lies outside his selection. But it is not unseen by us:
  - other rules were scored there, so the market path and how trend rules fared are known. Study 2's ribbon failed
    gold's 2017-2018 window. In FINAL10's "new" window, the V3-lite + H4 Supertrend hybrid lost 13% on M1 bars and
    trailed plain V3-lite on the tick engine;
  - the classic Supertrend's direction was scored there as FINAL10 hybrids (`infra.md` F6).

**Why not study 2's split.**
- Its hold-out (2024-07 onward) lies inside the video's selection sample, and 63% of all gold rows passed it.
- BTC would get no exam outside the video's sample.
- Its Development years 2021-2022 are also the video's sample.

### 5.3 The recommendation for study 4: a reverse split

| Window | Span | Role |
|---|---|---|
| d | 2021-01-01 to 2024-01-01 | selection: his older half (he splits about mid-December 2023) |
| v | 2024-01-01 to 2026-11-13 | selection: his newer half |
| dv | d + v, as one continuous run | the ranking (P/DD) and the claims (cut at 2026-11-01) |
| e1 | 2018-11-13 to 2021-01-01 | exam 1, gold and BTC |
| e2 | gold 2017-01-01 to 2018-11-13 | exam 2 |
| e0 | gold 2016-04-01 to 2017-01-01; BTC 2018-04-01 to 2018-11-13 | exam 3, information-weighted |
| fwd | 2026-11-13 to the data end, then pre-registered re-scores | information now; a verdict at the re-scores |
| full | from the first exam start to the data end | accounts |

**The guard.**
- Before `FINALISTS.md` and its sha256 exist, nothing outside 2021-01-01 to 2026-11-13 is scored, and nothing after
  2026-11-13 is loaded.
- Indicators may read every bar from the data start.
- Nothing is ever scored before the hard floor: gold 2016-04-01, BTC 2018-04-01.
- This needs a new guard in `tradeiq3_market.py`: both inherited guards are open (`infra.md` F2).

**The exam rule, with an absolute leg and a relative leg.**
- **Absolute:** net above 0 at ×1.0 costs and P/DD of at least 0.5 (study 2's rule).
- **Relative:** R per year at least that of the **matched Supertrend row** on the same window: Supertrend under the
  video's protocol, on the same symbol, timeframe and sides, with no filter.
  - The relative leg stops a trending window from passing everything (study 2's gold hold-out: 63%) and a ranging one
    from failing everything (its Early window: 13%).
  - **R per year rather than R per trade.** R per trade rewards trading less: VST is 12.9× Supertrend per trade but
    only about 1.5× per year. R per trade is reported beside it.
- **Four verdict words:**
  - "passes": both legs;
  - "beats Supertrend, but loses": the relative leg only;
  - "makes money, but no better than Supertrend": the absolute leg only;
  - "fails".
- **What must pass.** Gold champions must pass e1 and e2; BTC champions must pass e1. e0 and the forward re-scores are
  information-weighted. Each verdict is shown with buy-and-hold, exposure-matched buy-and-hold and the base rate of
  every row, as in study 2.

**Limits of e0.**
- Gold's 4H warm-up from 2016-01-03 is only about 340 bars after the January and March holes, under the specs' 500.
- The ATR seed and PPST's centre have faded by then. EMA(200) still carries about 3% of its starting gap, and D1
  indicators have only about 57 bars.
- So e0 examines 1H and 4H rows without E200, and no D1 rows. AlphaTrend needs its merge-bar check. BTC's e0, from
  2018-01-01, has about 540 4H bars of warm-up.

**Precision Sniper's start date.**
- By default it enters only from 2020-01-01. It would then have no label in e2 or e0, and only 2020 in e1.
- Recommended: move the start to the data start for every PS row, as a declared deviation (question 8 of 7.1).
- The porting notes count the label differences against the default on 2020-2026.

**The forward window.**
- Re-score the frozen finalists at the first store refresh after 2027-02-13, and again after 2027-05-13. These are
  dates fixed now.
- Until then the forward window is information.

**Secondary checks.**
- **Transfer.** The frozen champions, unchanged, on the five transfer FX and silver markets and on US30m, in R, at ×1
  and ×2. This gives a "generalises" verdict, information-weighted. Silver is not clean for the classic Supertrend.
- **Statistical controls.**
  - Placebo entries matched on side, frequency, stop in ATR and holding time (study 2's Wyckoff pattern).
  - The deflated Sharpe ratio and the SPA p-value over every row of study 4.
  - **The cumulative count in RESULTS.md.** This is the fourth study of its kind on these two markets: about 2,600
    rows in studies 1-3, plus FINAL10's designs and the ladder's 2,661.

### 5.4 The recommendation for filter round 2

1. **Development** is study 3's: the 23 FINAL10 quarters plus the 5-year account, 2021-01-01 to 2026-11-13.
2. **T0, the primary exam, never scored.**
   - Gold tick designs on 2016-04-01 to 2017-01-01. Their 600 H1 bars of warm-up fit from 2016-01-03.
   - BTC designs and the Turtle on 2018-04-01 to 2018-11-13.
   - Only filters whose warm-up fits can be examined there:
     - every H1 filter;
     - H4 filters except E200-H4 on gold;
     - on D1, only ST, PMAX, PPST, AT and RMI (and ADX20-D1 on BTC).
   - The pre-registration lists the eligible set per symbol, computed from that warm-up rule.
3. **T1 and T2 again, as a second use.**
   - They are fresh for the new filters, but the bases' and round 1's results on them are known.
   - So the filters must be pre-registered from the video and the scripts only, never by analogy with round 1's
     winners.
4. **The pass rule.** A finalist passes T0 and T1, and gold finalists also T2, under `bot_filters.exam_pass`.
5. **Forward, then demo.** The forward window is information. A demo account comes before anything goes live.
6. **Joint sealing.** Neither study's exam runs before both are frozen. Round 2's T0, T1 and T2 coincide with study 4's
   e0, e1 and e2: seeing how the Supertrend family does as a bot filter there would leak into study 4's choices.

### 5.5 Power: the trades an exam window can hold

These are expected 4H trades per symbol, from his pooled rates (his trades divided by 64.2 market-years). Gold and BTC
may differ from his average market.

The last two columns are lower bounds. Each assumes every winner is his average winner. The real spread is wider,
because winners vary from small to 30R or more.

| Script | Trades a year (his) | dv | e1 | e2 (gold) | e0 gold / BTC | His mean R per trade | SD of R per trade, at least | Standard error of the mean in e1, at least |
|---|---|---|---|---|---|---|---|---|
| ST | 47 | 276 | 101 | 88 | 35 / 29 | 0.11 | 1.5 | 0.15 |
| PPST | 30 | 177 | 64 | 56 | 23 / 19 | 0.23 | 1.9 | 0.24 |
| RMI | 28 | 166 | 61 | 53 | 21 / 18 | 0.26 | 2.1 | 0.27 |
| PS | 31 | 182 | 66 (31 with the 2020 start) | 58 (0) | 23 / 19 (0) | 0.29 | 2.1 | 0.25 |
| PMAX | 21 | 125 | 46 | 40 | 16 / 13 | 0.37 | 2.3 | 0.34 |
| SMB | 15 | 88 | 32 | 28 | 11 / 9 | 0.47 | 2.9 | 0.52 |
| VST | 5 | 31 | 11 | 10 | 4 / 3 | 1.38 | 5.1 | 1.52 |

**What follows.**
- In one exam window the standard error of R per trade is as large as the edge itself. An exam can catch a gross
  failure. It cannot confirm the six's ranking, nor tell 0.1R from 0.3R. The pre-registration should say so.
- VST on 4H has about 31 trades in dv, at the house minimum of 30, and about 10 per exam window. Its 1H rows must be
  eligible, or VST's verdict is information only.
- 1D rows trade about a sixth as often as 4H rows.

### 5.6 Disclosures for the pre-registration

- **`infra.md` F6.** The classic Supertrend H4 (10, 3) has been scored from 2018-11-13:
  - as FINAL10 hybrids on gold and BTC;
  - as the ladder's gate;
  - standalone on silver.
- Studies 1-3 scored other rules on e1 and e2, and FINAL10 on e1.
- This survey read the exam results and base rates of studies 2 and 3.
- The ladder PREREG states that every year from 2016 to 2026 was "read" by earlier studies.
- C7's partners and round 2's stacked bases were chosen knowing T1 and T2 results.

## 6. The build plan

### 6.1 Layout (`infra.md` 5 and 6)

| Path | What |
|---|---|
| `backtest_results/tradeiq_supertrend/` | PREREG.md (+ .sha256), DATA.md, DEVIATIONS.md, `porting/<key>.md` × 9, STUDY.md, CANDIDATES.md, FINALISTS.md (+ .sha256), EXAM.md, CLAIMS.md, RESULTS.md, index.html, img/, CSVs. SID `tradeiq_supertrend` |
| `backtesting/research/tradeiq3_market.py` | the shim: study 4's guard, windows, loader (TMarket3, load3), and guarded scoring entry points over study 2's frozen engine. It re-exports, never edits |
| `backtesting/research/tradeiq3_filters.py` | E200, E200-4H / E200-1D, ADX20, D50, STH, VOL; it hands study 2's filter names on unchanged |
| `backtesting/research/tradeiq3_ind_common.py` | the missing built-ins (section 2) |
| `backtesting/research/tradeiq3_ind_<key>.py`, `tests/tradeiq3_oracle_<key>.py`, `tests/test_tradeiq3_ind_<key>.py` | port A, port B, and the reconciliation and trap tests |
| `backtesting/research/tradeiq3_rules_<key>.py`, `tradeiq3_rules_common.py`, `tradeiq3_rules_combo.py` | the rule modules. `signal_exec` gives every script the video's protocol in a few lines |
| `backtesting/research/tradeiq3.py` | the driver: grid, run, select, freeze, exam, accounts, claims, report |
| `backtesting/research/bot_filters2.py`, `backtest_results/bot_filters_trend/` | round 2. It imports `bot_filters` as a library. Its pages share the `bot_filters` colour group |

- **Every new file uses the `tradeiq3_` prefix.** A `tradeiq2_ind_*` file would change study 2's code identity and stop
  its exam and accounts (`infra.md` F4).
- **Pinned blobs.** `tradeiq2_market.py` (985bdb9), `tradeiq2_filters.py` (6b148d5) and `bot_filters.py` (c764f39)
  are imported and never edited.

### 6.2 Work packages, with hours

"Engineer-hours" add up the specs' estimates. "Elapsed" assumes parallel agent workflows, as in study 2. Study 2's
commits ran from the frozen PREREG at 12:56, to ports reconciled at 17:39, the run at 20:08, the freeze at 20:30, the
exam at 20:36, RESULTS at 21:55 and STUDY.md at 22:25.

| # | Work | Engineer-hours | Elapsed | Needs |
|---|---|---|---|---|
| 0 | The owner's answers (7.1), PREREG and sha256, DATA.md with counts and spans only: gold 2016's holes, BTC 2018's quality, the median spread in R on 4H per window (gold's 2016 monthly median spread was $0.45-0.50, per study 2's DATA.md), USDJPYm's span | 4-6 | 2-3 | studies 2 and 3 committed |
| 1 | The shim: the guard, windows, loader, `scores3` columns (R per year, the five-best check, streaks, early losers), the guarded entry points, tests | 6-8 | 2 | 0 |
| 2 | The filters and their tests | 2-3 | 1 | 1; the ST port, for STH |
| 3 | The common built-ins, each written twice: MFI, VWMA, VWAP with an anchor, MACD, bars-since, session membership, the kNN step | 4-6 | 1-2 | 0 |
| 4a | Ports and reconciliation for ST (4), PMAX (5-9), PPST (4-8), RMI (5-7) and AT (5-7) | 23-35 | 3-4 | 3 |
| 4b | SMB (9-10) and VST (8-12) | 17-22 | 4-5 | 3 |
| 4c | PS: two ports of 16-24 h each, plus 8 h of reconciliation | 40-56 | 5-7 (the long pole) | 3 |
| 4d | HULL | 1-2 | under 1 | a complete copy |
| 5 | The rule modules, `signal_exec`, the combinations, the claim extras, tests | 8-12 | 2 | 4 |
| 6 | The driver: its own claims registry of about 60 claims, `Evidence3`, qualification with the five checks, the report tables, tests | 10-16 | 2-3 | 1, 5 |
| 7 | The rules review (look-ahead and readings), DEVIATIONS | 2-4 | 1 | 5, 6 |
| 8 | grid, run, select; an independent re-derivation of the champions; the freeze | 3-5 | 1-1.5 | 7 |
| 9 | The exam (e1, e2, e0, base rates, a look-ahead recheck), accounts, claims, report | 3-5 | 1-1.5 | 8, and round 2 frozen |
| 10 | RESULTS.md, STUDY.md, CLAIMS.md | 6-8 | 2 | 9 |
| 11 | The comparison page: its sources, windows, a study-4 gate for the pre-2021 windows, the palette (round 2 goes in the `bot_filters` group), the 11.6 MB budget (all-variant curves only on the study page), tests; then the study page, PNGs and the publish | 3-5 | 1-1.5 | 9; the finishing studies' commit of `tests/test_compare_page.py` |
| 12 | Round 2's code: the registry, `FilterBook2`, the runners, the guard, the identity check, the export, tests | 8-12 | 2-3 | 4a and 4b, for filters that read study-4 ports |
| 13 | Round 2's runs: Development, one design at a time with BTC alone; the 8-timing raw-tick confirmation; the freeze; the exam after study 4's freeze; RESULTS | 4-6, plus compute | 5-8 | 12; its exam after 8 |
| | **Total** | **about 145-210** | **about 14-18** | |

### 6.3 Order and sequencing

1. **Wait for studies 2 and 3 to commit,** including study 3's compare CSVs and the comparison-page tests. Study 2's
   `CodeSnapshot` stops a run whose files change under it.
2. **Freeze the PREREG** before any P/L. Log every later reading in DEVIATIONS before the result it could affect.
3. **Ports before rules.** The real-bar reconciliation may read every bar. The event counts printed in
   `porting/*.md` come from d + v only.
4. **Start PS first.** It is the long pole. If it slips, the other eight scripts continue, and PS joins before `grid`.
5. **Round 2 rows** that read study-4 ports run only after those ports are reconciled.
6. **Neither exam** runs before both studies are frozen (5.4, point 6).
7. **Light compute.** One symbol at a time, with at most 2 workers. Round 2 runs one design at a time, BTC alone.
8. **Commit and push at each checkpoint,** as the owner asked on 28 Nov 2026.

### 6.4 Risks to the schedule

- **PS.** It needs 40-56 engineer-hours. Its tick rounding and four-phase engine are where bit-for-bit agreement can
  take longest.
- **HULL** is blocked until the owner sends a full copy. The HMA filter of round 2 does not need the tail.
- **Volume.**
  - VST's zero-volume checks and BTC's two volume sources double some of the reconciliation work.
  - The Binance klines end on 2026-11-26. The forward re-scores need fresh ones.
- **Memory.** Round 2's BTC prepare takes about 5.4 GB.
- **The comparison page.** It has 7 palette slots and an 11.6 MB budget.

## 7. Open questions for the pre-registration

### 7.1 For the owner

1. **AlphaTrend and Hull Suite** are not in the video. Should they be eligible scripts, controls, or left out?
   - Recommended: AlphaTrend eligible. Its copy is complete and small.
   - Recommended: Hull eligible once a complete copy exists. Until then its HMA serves only as our own filter.
2. **The Hull Suite copy** stops after the Hull average is computed. Can you export it again, or copy it again from
   TradingView?
3. **Markets.**
   - Gold and BTC are the eligible markets.
   - EURUSDm, GBPUSDm, USDJPYm and USTECm give information rows on his window.
   - Should we also download ETH, SOL, BNB, XRP and US500 from the Exness archive, if it has them? Not recommended:
     they are not your markets, they are heavy, and the coins' volume rows would need Binance klines.
   - Should the frozen champions also run on the transfer markets (silver, AUD, NZD, CAD, CHF, US30) for a
     "generalises" verdict?
4. **Swap.** The earlier studies took the Standard account as swap-free. Does that hold for BTC and gold trades held
   for weeks or months? The answer decides whether a swap row is needed for PMAX, SMB and VST.
5. **VST's licence** is CC BY-NC-SA (non-commercial). Research with our own port is what studies 1 and 2 did. May a
   VST-derived rule be proposed for the live bots?
   - Recommended: research and information only, unless you decide otherwise.
6. **The split.** Do you accept the reverse split: selection on 2021-2026 and exams before 2021? Do you accept the
   forward re-scores after 2027-02-13 and 2027-05-13?
7. **Round 2's bases.** The five designs. Should we also run gold Top 2 with SLOPE100-D1 or MSD-D1 as stacked bases,
   examined on T0 and the forward window only?
8. **Precision Sniper's start date.** May we move its "entries from 2020-01-01" default to the data start, as a
   declared deviation, so that it can sit the pre-2021 exams?
9. **Precision Sniper's cost in time.** It is 40-56 of the 145-210 engineer-hours. Should it run in the same wave
   (recommended, started first), or in a second wave after the other eight scripts?

### 7.2 Readings to register, with the proposed defaults

| # | Reading | Proposed default |
|---|---|---|
| 1 | The stop's ATR | 2 × `ta.atr(14)` (Wilder) of the signal timeframe at the signal close, measured from the fill. The script's own ATR is a sensitivity |
| 2 | Same-side signals | ignored while in a trade. After a stop, flat until the next signal of either side. AT's and SMB's repeated labels and PS's "RE" labels count as signals |
| 3 | A filter and the exit | filters gate entries only. A blocked opposite signal still exits |
| 4 | E200 | an EMA(200) of the close, seeded with the first value. F1 and F2 (SMA200) run beside it |
| 5 | ADX20 | study 2's DMI port at the signal bar's close, ADX strictly above 20. ≥ 20 is a sensitivity |
| 6 | D50 | the decision close against the EMA(50) of the last closed 1D bar. Readings (b) and (c) are sensitivities |
| 7 | STH | the Supertrend (10, 3) direction of the last closed higher bar (`htf_at`) |
| 8 | Volume | gold: tick volume. BTC: Binance BTCUSDT. Exness tick volume for BTC as a sensitivity row in every script that reads volume |
| 9 | The halves | d to 2024-01-01, then v (his split is about mid-December 2023) |
| 10 | The claims | his window, 2021-01-01 to 2026-11-01, per market, with the tolerances of 3.5 |
| 11 | Qualification | study 2's four rules, plus net above 0 without the five best trades, plus net above 0 at ×2 costs (his checks 4 and 5). Minimum trades over dv: 30 on 1H and 4H, 15 on 1D |
| 12 | The selection metric | P/DD over dv. R per trade and R per year are reported |
| 13 | The exam | the absolute and relative legs of 5.3. Gold: e1 and e2. BTC: e1. e0 and the forward window are information-weighted |
| 14 | Pivot ties | strict on both sides. The porting notes give counts under the three alternatives |
| 15 | EMA seeds | the first value. The effect of an SMA seed is measured |
| 16 | Bars | UTC 4H and 1D boundaries. TradingView's gold session is a disclosed difference |
| 17 | PS | the Auto preset (4H Swing, 1H Default, 1D Swing without the VWAP); evidence v2; volume as #8; the VWAP on the UTC day; the start date as question 8 of 7.1 decides; "RE" labels are signals; ticks of 0.001 (gold) and 0.01 (BTC) |
| 18 | VST | triangles only, held to the opposite triangle or the stop; ties go stably to the more recent bar; the reference WMA; assert no zero-volume 10-bar window |
| 19 | RMI | the EMA(5) seeded with the first value; the BUY is a strict cross; the SELL is a level test |
| 20 | AT | the true range is na on bar 0; the ATR is an SMA; the closed forms of the labels and of the Confirmed alarm (`spec_alphatrend.md` steps 9-10) |
| 21 | PMAX | assert invariant I1 (the labels are the flips); the source is hl2 |
| 22 | SMB | the pivot update runs before the break test; a newer swing replaces the old level; the range window leaves out the swing bar |
| 23 | HULL | the tail stays provisional until confirmed; a rule says whether it reads the colour or the alerts; the HTF mode is not used |
| 24 | Multiple testing | the SPA p-value and the deflated Sharpe over every row of study 4, per symbol; the cumulative count across studies 1-4, FINAL10 and the ladder in RESULTS; round 2 counts rounds 1 and 2 together |
| 25 | Disclosures | the list in 5.6 |
| 26 | Accounts | the $2,000 unit-rule accounts for the finalists over full and over the comparison page's windows; R-based per-market tables for the claims |

## 8. Sources in this folder

- `/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/study4/transcript.md`:
  the transcript, read whole. It holds the 68 claims, the combinations K1-K10, his test and his numbers.
- `/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/study4/spec_st.md`,
  `spec_ppst.md`, `spec_rmi.md`, `spec_sniper.md`, `spec_pmax.md`, `spec_smb.md`, `spec_vstai.md`,
  `spec_alphatrend.md` and `spec_hull.md`, all in the same folder: the porting specs.
- `/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/study4/infra.md`:
  what to reuse, what to add, and the hold-out analysis.
- **In the repository (read only):**
  - `backtest_results/tradeiq_2027/PREREG.md`, `DATA.md` and `RESULTS.md`;
  - `backtest_results/bot_filters/PREREG.md` and `RESULTS.md`;
  - `backtest_results/final10/FINAL10.md`;
  - `backtest_results/improve/external_strategies.md`;
  - `backtest_results/silver/SILVER.md`;
  - `backtest_results/ladder/LADDER.md`;
  - `backtest_results/tradeiq_rsi/PREREG.md`.
