# TradeIQ video 3, "Supertrend": the transcript, read whole

28 Nov 2026. Notes for study 4, written before any rule exists or runs. Source:
`/Users/sidharthsingh/Desktop/study/trend/Supertrend Trading Analysis.rtf` (read-only). It is an automatic transcript
with timestamps, about 26,600 characters in 16 chapters, from 0:00 to 25:58, and it was read in full.

- **Nothing was run:** no backtest, and no market data was loaded.
- **Quotes and code:** the transcript is quoted only in phrases of a few words. No code from the scripts is copied
  here; where their logic matters, it is described in words (section 1.2).
- **"This year"** in the video means 2026. His test ends in October 2026, and his failure examples are from September
  and October "this year".

**Abbreviations.**

- **ST:** Supertrend (ATR 10, factor 3).
- **The six, in his order from 6 to 1:**
  - PPST: Pivot Point SuperTrend.
  - RMI: RMI Trend Sniper.
  - PS: Precision Sniper.
  - PMAX: Profit Maximizer.
  - SMB: Smart Money Breakout Signals.
  - VST: Volume SuperTrend AI.
- **R:** the risk of one trade. In his test, 1R is the 2 ATR stop distance.
- **PF:** profit factor, gross profit divided by gross loss.
- **"R a year on each market":** his yearly figure per market. Section 3.4 shows it is the pooled R spread evenly over
  11 markets and about 5.8 years.
- **G:** gold (XAUUSDm). **B:** BTC (BTCUSDm).

## 0. In short

- **Supertrend, his baseline.** He traded every Supertrend signal on 11 markets, on the 4H chart, from January 2021 to
  October 2026, with costs. One rule set applies to every indicator:
  - a signal on a closed candle, and entry at the next open;
  - a 2 ATR stop, which is 1R, and no target;
  - out on the opposite signal or the stop.

  Over 3,022 trades Supertrend "made money, barely": about 0.1R a trade, PF 1.17, and seven trades in ten lost.
- **The six.** He put 51 other buy/sell indicators through the same test and six passed his five checks. He ranks
  them by R per trade, as a multiple of Supertrend's:

  | Script | R per trade vs Supertrend |
  |---|---|
  | PPST | 2.2× |
  | RMI | 2.5× |
  | PS | 2.7× |
  | PMAX | 3.4× |
  | SMB | 4.4× |
  | VST | 12.9× |

- **The 10x claim.** Only VST is "10x", only per trade, and 42% of its profit is one Solana trade. Without that trade
  it is 7.5×. Per year, the six make only about 1.5 times what Supertrend makes.
- **Where the money came from.** All six win less often than Supertrend (19-27% of trades, against about 30%), but
  their winners are bigger. All made their money on the five coins and on gold, mostly on longs, in years when coins
  and gold went up. Forex was flat, except for VST, and the stock indexes lost.
- **One filter each.** For each script he names one filter from another family of indicators:
  - EMA200: PPST, PS, VST, and Supertrend itself;
  - ADX above 20: RMI and SMB;
  - the daily EMA50: PMAX, which he also says to trade long only.
- **Supertrend itself:**
  - it whipsaws in sideways markets;
  - it loses on 1H (PF 0.98);
  - an EMA200 lifts it to PF 1.33;
  - costs hurt it, because it trades about once a week.
- **His own tools.** None of the scripts is his. The video advertises five private TradeIQ MAX indicators and his
  paid backtest sheet. Neither is tested in the video, and we have neither.
- **Consistency.** His figures are internally consistent (section 3.4).

## 1. The files in `/Users/sidharthsingh/Desktop/study/trend/`

### 1.1 Which file is which

| File | What it is | In the video | Author (per the file) | Pine version; licence | Defaults compared with what he says |
|---|---|---|---|---|---|
| Supertrend Trading Analysis.rtf | the transcript | n/a | n/a | n/a | n/a |
| Supertrend Indicator.rtf | "Supertrend" | yes: the baseline | the file has no author line. The video says KivancOzbilgic wrote it (he also wrote PMAX), and its inputs and layout match those of the PMAX file | v4; none stated | ATR period 10, source the candle middle (hl2), multiplier 3, Wilder's ATR: matches |
| Pivot Point SuperTrend Indicator.rtf | "Pivot Point SuperTrend" | yes: #6 | LonesomeTheBlue | v4; MPL 2.0 | pivot period 2, ATR factor 3, ATR period 10, centre line hidden: matches |
| RMI Trend Sniper Indicator.rtf | "RMI Trend Sniper" | yes: #5 | TZack88 | v5; MPL 2.0 | length 14, levels 66 and 30: matches. The "fast EMA" is a 5-bar EMA of the close, which the video does not say |
| Precision Sniper Indicator.rtf | "Precision Sniper [WillyAlgoTrader]", version 2.3.0 | yes: #4 | Willy (WillyAlgoTrader) | v6; none stated | preset Auto. On 4H, Auto picks the "Swing" profile: EMAs 13 and 34, as he says, plus a trend EMA 89. See 1.2 for a version risk |
| Profit Maximizer Strategy.rtf | "Profit Maximizer" (PMax). Despite the file name, it is an indicator, not a strategy script | yes: #3 | KivancOzbilgic | v4; MPL 2.0 | ATR 10, multiplier 3, EMA 10: matches. The EMA is of the candle middle (hl2), not of the close |
| AlgoAlpha Smart Money Breakout Indicator.rtf | "Smart Money Breakout Signals [AlgoAlpha]" | yes: #2 | AlgoAlpha | v6; MPL 2.0 | time horizon 25, break confirmed on the candle close: matches |
| Volume SuperTrend AI Indicator.rtf | "Volume SuperTrend AI (Zeiierman)" | yes: #1 | Zeiierman | v6; CC BY-NC-SA 4.0 (non-commercial) | Supertrend length 10, factor 3, 3 neighbours, 10 data points: matches in substance |
| AlphaTrend Indicator.rtf | "AlphaTrend" | **no** | KivancOzbilgic | v5; MPL 2.0 | not applicable |
| hull_suite.rtf | "Hull Suite by InSilico" | **no** | InSilico | v4; none stated | not applicable. The file is **incomplete**: it stops after the Hull average is computed, with no plot, colour or signal |

**Shown in the video.** The seven scripts the video tests (the Supertrend baseline and all six) are all here and
complete. Their defaults are what he says he used.

**Not in the video.** AlphaTrend and Hull Suite are never named.

- **AlphaTrend:** an ATR trailing line steered by MFI(14). It signals when the line crosses its own value from two bars
  earlier.
- **Hull Suite:** Hull moving averages, length 55.
- **Where they came from:** both were saved at 11:28 and 11:32 on 28 Nov, about ten hours before the other files
  (21:55 to 22:00). Neither file is in the folders of the two earlier studies.
- **Open question:** both are trend tools and could be among the 51 he tested, but the transcript does not say. Whether
  they belong in study 4 is for the owner to decide.

**Mentioned but missing:**

- none of the seven scripts that the video tests is missing;
- **the 45 indicators that failed** his checks (51 tested, six passed): not named, no code;
- **the five private TradeIQ MAX indicators** (AI VWAP, Nebula Flow, Fibonacci AI, Volume Nexus, Apex Levels):
  advertised, private, and not tested in the video;
- **his filters** need no script, since EMA200, ADX and the daily EMA50 are built-ins. But he does not give their
  settings (section 5);
- **the TradeIQ backtest sheet**, which holds his per-trade results: behind the paid membership.

### 1.2 What the code says, where it matters for a port

Described in words only. Study 4's porting notes will go deeper.

- **Supertrend.**
  - The line sits 3 × ATR(10) below or above the candle middle. ATR is Wilder's average by default; a simple average
    of the true range is an option.
  - The lower band can only rise, and the upper band only fall, as long as the previous close stays on that band's
    side. Otherwise the band resets to its raw value.
  - The trend flips when the close crosses the previous bar's opposite band. It starts as an uptrend.
  - The Buy and Sell labels mark the flips.
  - The script lets the user pick another timeframe; by default it uses the chart's.
- **PPST.**
  - A pivot has 2 bars on each side, so it is known 2 bars after it forms.
  - The centre is a weighted running average, updated only on a pivot bar: two parts the old centre, one part the new
    pivot. If a bar is both a pivot high and a pivot low, the high is used.
  - The bands sit 3 × ATR(10) from the centre and ratchet like Supertrend's. A flip comes when the close crosses the
    previous bar's opposite band.
  - So the centre moves only with the swings, but the line also moves with the ATR on every bar. His claim that the
    line "only moves when the swings move" is true of the centre, not of the line.
  - A label prints on every flip.
- **RMI.**
  - It averages an RSI(14) of the close (Wilder's) with an MFI(14) of the typical price.
  - The MFI needs volume. On Exness that is tick volume; for BTC, studies 1 and 2 also used Binance spot volume.
  - It turns long when the average crosses above 66 and the 5-bar EMA of the close rose on that bar.
  - It turns short on any bar where the average is below 30 and that EMA fell. This is a level, not a cross.
  - A signal is a change of state. The band drawn around price is display only.
- **PS (version 2.3.0).**
  - **Profile.** On 4H, the Auto preset picks "Swing": EMAs 13 and 34, a trend EMA 89, RSI 21, ATR 20, a minimum score
    of 6 out of 10, and a stop of 2.5 ATR.
  - **Candidate.** A 13/34 EMA cross on a closed bar.
  - **The gate, in order:**
    - warm-up: 267 bars;
    - the date window: **by default, entries are allowed only from 1 Jan 2020**;
    - high volatility: an entry is skipped when ATR(20) is more than 1.3 times its 42-bar mean;
    - price momentum: the close must be beyond both the fast and the slow EMA;
    - RSI extreme: about 70.4 and 29.6 at RSI 21;
    - evidence: at least 60% of the available points;
    - a valid trade plan.
  - **Evidence, in the default "v2 decorrelated" model:**
    - the close against the trend EMA;
    - the slope of the trend EMA;
    - a close beyond the previous 10-bar high or low;
    - a rising MACD histogram;
    - ADX at 20 or more, with the DIs aligned;
    - volume above 1.2 times its previous 20-bar mean;
    - the side of the session VWAP (4H counts as intraday).

    On a chart with volume that makes 7 points, so at least 5 are needed.
  - **Version risk.** The video lists the evidence as trend, RSI, MACD, ADX and volume. That is the "v1 legacy" set
    (RSI side of 50, MACD sign), which the tooltip says belonged to version 2.2. He may have tested an earlier version.
  - **The labels depend on the script's own model trade:**
    - a candidate in the direction of the model's open trade is dropped;
    - a candidate the other way reverses the model trade;
    - after the model's trade is stopped (at its first or a moved-up stop) or reaches its third target (3R) within one
      cross cycle, a re-entry label ("RE") may print once, when price closes back across the fast EMA.
  - **Consequence for a port.** A port must run the model trade just to know which labels exist, before applying
    TradeIQ's exits:
    - the stop starts at 2.5 ATR and is widened to the 11-bar swing plus or minus 0.2 ATR, with a cap;
    - the targets are 1R, 2R and 3R;
    - the stop steps up to the entry and then to the first target;
    - the third target closes the trade.

    He does not say whether he traded the "RE" labels.
- **PMAX.**
  - A Supertrend computed on a 10-period EMA of the candle middle instead of on price.
  - The stops sit 3 × ATR(10) from the EMA and ratchet while the EMA stays on their side.
  - A flip comes when the EMA crosses the previous bar's opposite stop.
  - The Buy and Sell labels mark where the EMA crosses PMax. With any non-zero ATR, those crosses fall exactly on the
    flips.
  - Labels for price crossing PMax exist but are off by default.
- **SMB.**
  - Swing highs and lows have 25 bars on each side, so they are known 25 bars late.
  - A close above the last swing high is a bullish signal; a close below the last swing low is a bearish one. The
    option to count wicks instead of closes is off.
  - A swing that has been broken is spent. A second signal in the same direction needs a new swing, so two bullish
    signals in a row are possible.
  - The label reads CHoCH when the previous break went the other way, otherwise BOS.
  - Its three targets lie beyond the swing by one ninth, two ninths and one third of the price range covered from the
    swing to the break. A stop, used only in the script's statistics, lies a third of that range back. The hit-rate
    table counts touches of the targets, not trades.
- **VST.**
  - The centre is a volume-weighted average of the close: a 10-bar WMA of close times volume, divided by a 10-bar WMA
    of volume. The bands sit 3 × ATR(10) from it.
  - The flip test uses the current bar's ratcheted band, as Pine's built-in Supertrend does. The plain Supertrend uses
    the previous bar's band.
  - **The "AI" label:**
    - the script takes the last 10 values of the line, the current one included;
    - each value is tagged "up" when a 20-bar WMA of the close is above a 100-bar WMA of the line;
    - the label is a distance-weighted vote of the 3 values nearest to the current one;
    - it is exactly "up" or exactly "down" only when all three agree. Otherwise the line is drawn neutral (blue).
  - **Signals.** A buy triangle is a flip up while the vote is exactly "up"; a sell triangle is a flip down while it is
    exactly "down". The circles mark colour changes and are not signals, as he says.
  - **Volume source.** Volume enters the centre, so Exness tick volume and an exchange's volume give different flips
    and triangles.
  - **Version.** The file has cloud-drawing options, which suggests it is a later revision of the August 2023 script.

## 2. The video in order

### 2.1 The six at a glance

His numbers, pooled over 11 markets, on 4H, 2021-2026:

| Rank | Script (author), published | R per trade vs Supertrend | Trades | Win % | PF | R a year per market | Same, costs ×2 | Best markets (PF) | Weak spots | His filter, and the PF it gives |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | Supertrend (KivancOzbilgic) | 1× (about 0.1R) | 3,022 | about 30 | 1.17 | 5 | 2.3 | not given | loses on 1H; hurt by costs | EMA200 → 1.33 |
| 6 | PPST (LonesomeTheBlue), 2020 | 2.2× | 1,935 | 27 | 1.34 | 7 | 4.9 | SOL 2.6, BNB 2 | lost on the S&P 500, NASDAQ, EURUSD, GBPUSD | EMA200 → 1.47 in both halves, 9/11 markets |
| 5 | RMI (TZack88), Oct 2023 | 2.5× | 1,822 | 26 | 1.37 | 7.5 | 5.3 | SOL and BNB above 2; gold 1.45 | S&P 500 0.64; 2022 −72R, 2025 −59R | ADX > 20 → 1.43 |
| 4 | PS (WillyAlgoTrader), Mar 2026 | 2.7× | 1,987 | 26 | 1.42 | 9 | 6.5 | SOL 2.5, XRP 1.8, gold 1.6; 9/11 markets | shorts break even; 20 losses in a row | EMA200 → 1.59, 10/11 markets |
| 3 | PMAX (KivancOzbilgic), 2020 | 3.4× | 1,369 | 26 | 1.49 | almost 8 | 5.9 | SOL 2.65, ETH 2.1, BTC 1.8 | shorts lose; newer half 1.2; lost money in 2025 | daily EMA50 → 1.63 (newer half 1.53); trade long only |
| 2 | SMB (AlgoAlpha), Jan 2025 | 4.4× | 965 | 20 | 1.58 | 7 | 5.3 | SOL 3.3, gold 2.8; XRP and BNB above 2 | worst of the six on GBPUSD and both indexes; 26 losses in a row | ADX > 20 → 1.65 |
| 1 | VST (Zeiierman), Aug 2023 | 12.9× (7.5× without one trade) | 339 | 19 | 2.56 | about 7 | not given | USDJPY 3.3, EURUSD about 3; 9/11 markets | one trade is 42% of its profit; 20 losses in a row on gold; 2024 flat | EMA200 → 2.79 |

### 2.2 Chapter by chapter

**Chapter 1, "Supertrend: 3,022 trades, 0.1R each" (0:00).**

- Supertrend is one of the most used indicators on TradingView; the most popular version has 86,000 boosts.
- He traded every one of its signals: 11 markets, the 4H chart, almost six years, 3,022 trades, every cost included.
- It made money, barely: about 0.1R a trade. Seven signals in ten lost.
- He then ran 51 other buy/sell indicators through the same test. Six passed every check and made 2 to 13 times more
  per trade.
- He asks whether any of them is really 10× better. One is, he says, with a catch.

**Chapters 2 and 3: private indicators (0:55) and the backtest sheet (1:50).** These are advertising:

- five private TradeIQ MAX indicators (section 6);
- the TradeIQ backtest sheet, with every test in the video: exact rules, balance curve and every trade. The viewer can
  set the account size and the risk. It comes with the channel membership, from $7.99 a month.

**Chapter 4: what Supertrend does, and where it breaks (2:10).**

- **What it is.** A line 3 ATR from the middle of each candle, where ATR is the size of an average candle. In an
  uptrend the line sits under price and can only rise. A close below it flips the line above price and red: a sell.
  The defaults are ATR 10 and factor 3, which is what he tested.
- **In a clean trend that is all you need.** BTC, January 2023: one buy at $16,860, and the sell 26 days later near
  $22,800. Almost 30R from one signal.
- **The problem is the sideways part.** Every push through the line is a new signal. XRP, August to November 2022: 16
  losing trades in a row, each one small, together almost 15R.
- **This is not rare:**
  - four in ten Supertrend trades were losers closed within two days;
  - it trades about once a week on every market;
  - every trade pays fees.
- **The numbers to beat:**
  - PF 1.17, that is $1.17 back for every dollar lost;
  - 5R a year on each market;
  - doubling the costs took away more than half of that.

**Chapter 5: the test, and the honest answer about 10x (3:37).**

- The rules, markets and checks are in section 3.
- **The honest answer:**
  - per year, the six made about 1.5 times what Supertrend made;
  - with costs doubled, more than twice as much;
  - per trade, 2.2 to almost 13 times as much.

  Exactly one of them is over 10×, and only per trade, which is the number he ranks by.
- **On R:** at 1% risk a trade, 1R is 1% of the account. So 5R a year is about 5% a year on one market, before
  compounding.

**Chapter 6: #6, Pivot Point SuperTrend by LonesomeTheBlue (5:25).**

- **Basics.** From 2020; 2.2× Supertrend per trade.
- **What it does.** Supertrend hangs its line on every candle; this one hangs it on structure. Swing highs and lows
  (pivots) feed a running centre line, and the band sits 3 ATR from that centre, so one fast candle does not move it.
  On the chart it looks like Supertrend: green under price, red above, and a label on every flip. The centre line is
  hidden by default.
- **Example: gold 4H, March 2023.**
  - Supertrend catches the breakout (+6.8R), then takes six more trades in the range, none of them profitable. After
    five weeks, 1.6R is left.
  - PPST on the same candles: one buy at $1,863, no flip, and a sell near $1,995 35 days later: +6.3R. In his words,
    "one trade instead of seven".
- **Numbers:**
  - 1,935 trades (a third fewer than Supertrend), 27% winners;
  - PF 1.34 against Supertrend's 1.17;
  - 7R a year on each market against 5; with costs doubled, 4.9 against Supertrend's 2.3;
  - average winner 3.4R against Supertrend's 2.5;
  - best market Solana (2.6), then BNB (2);
  - it lost money on both stock indexes, EURUSD and GBPUSD.

  Its win rate is lower than Supertrend's, and he says the same holds for all six: "they win bigger".
- **It still gets chopped.** BTC, October 2026: a buy, and the stop within a day.
- **How to use it.** The 4H chart with the defaults (pivot period 2, ATR factor 3, ATR period 10), plus the EMA200:
  buys only above it, sells only below. That gave PF 1.47 in both halves, with 9 of the 11 markets profitable.

**Chapter 7: #5, RMI Trend Sniper by TZack88 (8:06).**

- **Basics.** Published October 2023; 2.5× per trade.
- **What it does.** It uses momentum, not a trailing line. It averages the RSI and the money flow index ("RSI with
  volume inside").
  - It buys when that average crosses above 66 while a fast EMA rises.
  - It sells when the average drops below 30, which takes "a real fall". So sells come late, and winners have room to
    run.
  - On the chart the candles turn green after a buy and red after a sell, with an arrow at each change. Green candles
    mean long.
- **Example: BNB 4H, October 2023**, a climb with sharp pullbacks.
  - Supertrend: four trades, four stops, −4.2R.
  - RMI: one buy at $213, held 24 days through the pullbacks, sold at $242: +8.1R. Then one short, which fails.
  - In total, +7R against −4R.
- **Numbers:**
  - 1,822 trades, 26% winners, PF 1.37, 7.5R a year on each market;
  - it held in both halves: PF 1.48 in the older half. The newer figure is garbled (section 9);
  - two or three trades a month on each market;
  - 5.3R a year with costs doubled;
  - its two best trades were both on coins: BNB early 2021 (96R) and XRP November 2024 (94R);
  - Solana and BNB above 2, gold 1.45;
  - the S&P 500 at 0.64, a loss, so he says to keep it off stock indexes;
  - bad years: 2022 cost it 72R across the 11 markets, and 2025 another 59R. It gives profit back when coins fall or go
    flat.
- **Failure.** BNB, October 2026: a buy, and the stop within two days.
- **How to use it.** It already has momentum and volume inside, so add trend strength, not another oscillator. ADX
  above 20 on the signal candle gave PF 1.43, almost the same in both halves. Keep the settings: length 14, levels 66
  and 30.

**Chapter 8: #4, Precision Sniper by WillyAlgoTrader (10:58).**

- **Basics.** Published March 2026; 2.7× per trade, and the most profit per year of the six.
- **What it does.** The trigger is a fast EMA crossing a slow one: 13 and 34 on 4H. On that candle it runs a checklist:
  - the close must be beyond both EMAs;
  - the RSI must not be extreme;
  - volatility must not be spiking;
  - most of its evidence (trend, RSI, MACD, ADX, volume) must agree.

  If anything fails, the cross is thrown away. The chart shows the two EMAs and a long or short label on each cross
  that passed. The script also draws its own stop and three targets; he did not use them, only his own rules.
- **Example: ETH 4H, February 2025**, a falling market with sharp bounces.
  - Supertrend: five trades, all stopped, −5.2R.
  - PS: one short at $2,641, held 23 days, down to about $2,280 (section 9): +5.1R. The long after it is stopped.
  - In total, +4R against −5R.
- **Numbers:**
  - 9R a year on each market, the best of the six;
  - 1,987 trades, 26% winners, PF 1.42;
  - 6.5R a year with costs doubled, against Supertrend's 2.3;
  - without its five best trades, still almost 300R across the 11 markets (Supertrend: 48R). In his words, "not one
    lucky run";
  - the widest spread: 9 of the 11 markets made money (Solana 2.5, XRP 1.8, gold 1.6). It is the only one of the six
    that made money on the NASDAQ.
- **Warnings.**
  - Longs made nearly all of its profit; shorts only broke even.
  - Its worst run was 20 losses in a row, on XRP.
  - Failure: gold, October 2026, a long on a Friday and the stop on the Monday.
- **How to use it.** Leave the preset on Auto, which picks the EMA lengths for the timeframe; that is what he tested.
  Add the EMA200: PF went from 1.42 to 1.59, with 10 of the 11 markets profitable.

**Chapter 9: "Before you delete it", on the timeframe, the EMA200 and costs (13:34).** To be fair to Supertrend, three
things made it a lot better:

- **Timeframe.** On 1H the raw signals lost money: more than 11,000 trades at PF 0.98. On 4H, with the same settings, PF
  1.17. If you trade it below 4H, change that first.
- **The EMA200.** Buys only above it, sells only below. The number of trades almost halved, PF went from 1.17 to 1.33,
  and the profit per trade almost doubled.
- **Costs**, "the quiet one."
  - Each of Supertrend's 3,000 trades pays a fee and a spread. Doubling the costs took 55% of its profit; PS lost only
    27%.
  - Fewer trades and bigger winners make costs matter less.
- **Verdict.** A filtered Supertrend is a fair tool. But its 1.33 is what the first three of the six made with no
  filter at all, and the next three are further ahead.

**Chapter 10: #3, Profit Maximizer (PMax) by KivancOzbilgic (14:55).**

- **Basics.** From 2020; 3.4× per trade. It is by the author of the Supertrend he tested, as that author's own fix for
  Supertrend.
- **What it does.** Supertrend flips when price closes through the line. PMax ignores price: it flips when a 10-period
  EMA crosses the PMax line, so one wild candle cannot flip it. On the chart the red line is PMax, the blue line is the
  EMA, and the labels sit where they cross.
- **Example: USDJPY 4H, September 2021.**
  - Supertrend: six trades in six weeks, five of them losers, −2R.
  - PMax waits a week longer, then buys once at 110.4. No sell label for 35 days; out at 113.6: +8.2R. The short after
    it is stopped.
  - In total, +7R against −2R.
- **Numbers:**
  - 1,369 trades (less than half of Supertrend's), 26% winners, PF 1.49;
  - almost 8R a year on each market, from about two trades a month;
  - 5.9 with costs doubled;
  - all five coins and gold made money: Solana 2.65, Ethereum 2.1, Bitcoin 1.8.

  Like Supertrend, it is always in the market: a sell label closes the long and opens a short. If you trade only the
  buys, a sell label means close and wait.
- **Warnings.**
  - The shorts lost money.
  - It was much stronger in the older half of the data: 1.81 against 1.2.
  - 2025 was a losing year.
  - Failure: Solana, September 2026, a buy and the stop a day later.
- **How to use it.**
  - Trade the buys, on coins and gold, on 4H. The defaults are ATR 10, multiplier 3 and EMA 10.
  - Check the daily chart first: when the signal agreed with the daily EMA50, PF rose to 1.63. The newer half improved
    the most, to 1.53.

**Chapter 11: #2, Smart Money Breakout Signals by AlgoAlpha (17:32).**

- **Basics.** Published January 2025; 4.4× per trade.
- **What it does.** It has no trailing line. It marks the important swing highs and lows (those with 25 candles on each
  side) and waits.
  - A close above the last swing high is a bullish signal; a close below the last swing low is a bearish one.
  - Inside a range, where Supertrend flips back and forth, it prints nothing.
  - Each signal comes with a line from the swing to the candle that broke it, a BOS or CHoCH label, and three targets.
    He traded the signal and ignored the targets.
- **Example: BTC 4H, June 2022.**
  - Supertrend: five trades, all losers, −3.7R.
  - SMB waits for the swing low to break: one short at $27,550, covered 26 days later at $22,130: +4.5R. The long after
    it is stopped.
  - In total, +3.5R against −3.7R.
- **Numbers:**
  - 965 trades (less than a third of Supertrend's), PF 1.58;
  - 7R a year on each market, from about one trade a month;
  - 5.3 with costs doubled;
  - win rate 20%: four signals in five lose, but the average winner is more than six times the average loser. In his
    words, "the whole edge";
  - Solana 3.3, gold 2.8, XRP and BNB above 2. On GBPUSD and both indexes it was the worst of the six;
  - its longest losing streak was 26 trades in a row, on BNB, spread over a whole year.

  **Lateness.** A swing needs 25 candles on each side, which is about four days on 4H. So a level is confirmed four days
  after it forms, and the signals come late: "the price for skipping the ranges".
- **How to use it.**
  - Coins and gold only, on 4H, with the default time horizon of 25.
  - Take every signal, since you cannot know in advance which one will be the big one. Keep the risk small.
  - To filter, ADX above 20 gave PF 1.65.

**Chapter 12: #1, Volume SuperTrend AI by Zeiierman (20:14).**

- **Basics.** Published August 2023; 12.9× per trade: "the 10x one".
- **What it does.**
  - A Supertrend built around a volume-weighted price, so heavy-volume candles pull the line harder.
  - A nearest-neighbours model then compares the line with its own recent history and labels the trend.
  - A buy or sell triangle prints only when the line flips and the label fully agrees. That is rare: on BTC the line
    flipped 246 times, and only 49 flips got a triangle, one in five. So the whole test had 339 trades, against
    Supertrend's 3,000.
  - The line changes colour with the label. The small circles are not signals; the triangle is.
- **Example: BNB, May 2025.**
  - One buy, then no sell triangle for 176 days. It got out at the end of October: +49R. The prices are garbled; see
    section 9.
  - In the same six months, Supertrend took 24 trades on BNB, lost 18 of them, and ended at +1.2R.

**Chapter 13: the catch (21:43).**

- **Numbers.** 19% winners, but the average winner is almost 12R. PF 2.56, with 9 of the 11 markets profitable. It is
  the one for forex traders: USDJPY 3.3, EURUSD almost 3. Its sells made money too.
- **The catch: one trade.** Solana, February 2021: bought at $9.50 and held 280 days to $185, a gain of 196R.
  - That trade is 42% of everything the indicator made.
  - Without it, VST is 7.5× Supertrend per trade: still the best of the six, but not 10×.
  - Per year it is no better than the others, at about 7R a year on each market. It makes the same profit from a ninth
    of the trades.
- **The hardest to trade.** The trade ignores the line's colour and is held until the opposite triangle, sometimes for
  months. On gold it lost 20 times in a row over three years, and 2024 was flat.
- **How to use it.**
  - The 4H chart, only the triangles, plus the EMA200: PF went from 2.56 to 2.79.
  - Be patient: about five signals a year on each market, and you cannot skip one.

**Chapter 14: where they work, and where they don't (23:06).** The story is the same for all six: coins and gold.

- **Coins:** on the five coins, each of the six made PF above 1.7.
- **Gold:** PF between 1.4 and 2.8.
- **Forex was flat.** Five of the six made about nothing on EURUSD, GBPUSD and USDJPY. VST was the exception, at 2.27.
- **The stock indexes lost.** On the S&P 500 and the NASDAQ, five of the six lost money on 4H. Only PS stayed above
  water, and only just.
- **Direction.** Longs carried all six. On five of them, the shorts were about break-even or worse.
- **Context.** From 2021 to 2026 coins and gold went up, and trend followers get paid for that. 2025 was flat or
  negative for most of the six, and Supertrend made nothing that year either.

**Chapter 15: which one to pick (24:10).**

- **Not all six.** They are separate tools, and they mostly catch the same big moves. Pick one:
  - closest to Supertrend in look: PMAX or PPST;
  - most profit per year: PS;
  - for breakouts: SMB;
  - for momentum: RMI;
  - for forex, or the fewest trades: VST.
- **One filter.** Pair it with one thing from a different family: the EMA200 for trend, ADX for trend strength, or the
  daily chart. Do not stack two trend lines: "they'll just agree".
- **Trade it the way it was tested:** the 4H chart; wait for the candle to close; enter at the next open; put the stop
  2 ATR away; no target; get out on the opposite signal, "not before".
- **Risk.** They win about one trade in four. Risk 1% a trade or less, and expect ten losses in a row.

**Chapter 16: outro (25:17).**

- Every one of the six beat Supertrend on the same test; only one got to 10×.
- The full results are in his backtest sheet (membership from $7.99 a month). The private indicators come with
  TradeIQ Max.
- Test every indicator on your own charts before risking money: "education, not financial advice".

## 3. His test

### 3.1 The rules (the same for every indicator)

- A signal on a closed candle; entry at the next candle's open; both long and short.
- A stop 2 ATR from the entry; that distance is 1R. No target. The trade runs until the opposite signal or the stop.
- Default settings and no confirmation, "just the signals".
- Every trade pays costs:
  - fees and slippage on crypto;
  - the spread on forex, gold and the indexes;
  - financing for as long as the trade is held.

  A stress run doubles every cost.

### 3.2 Markets and window

- **11 markets:** Bitcoin, Ethereum, Solana, BNB, XRP; EURUSD, GBPUSD, USDJPY; gold; the S&P 500 and the NASDAQ. He
  does not name his data feeds.
- **Window:** 4H, January 2021 to October 2026 (about 5.8 years). Supertrend is also shown on 1H.
- **Our data.** According to study 2's `DATA.md`, our tick store holds gold and BTC. It also holds USTECm (NASDAQ),
  EURUSDm and GBPUSDm, which studies 1 and 2 used for claim checks. ETH, SOL, BNB, XRP, USDJPY and the S&P 500 do not
  appear there.

### 3.3 The five checks and the ranking

An indicator made his list if it passed all five checks:

1. at least 200 trades;
2. a profit in the older half of the data and in the newer half;
3. a profit on most of the markets;
4. a profit without its five best trades;
5. a profit with every cost doubled.

Of the 51 indicators he tested besides Supertrend, six passed. He ranks them by profit per trade, as a multiple of
Supertrend's.

### 3.4 Do his numbers hang together?

His figures reproduce each other under two readings:

- "R a year on each market" is the total R divided by 64.2 market-years (11 markets × 5.83 years);
- "per trade" is the total R divided by the number of trades.

The table below is my arithmetic, from his numbers only.

| | Trades | R a year per market | Implied total R | Implied R per trade | Implied × Supertrend | His × Supertrend | Trades a month per market | Implied mean loser / mean winner (R) | Share of profit lost at costs ×2 |
|---|---|---|---|---|---|---|---|---|---|
| Supertrend | 3,022 | 5 | 321 | 0.106 | 1 | 1 ("about a tenth" of an R) | 3.9 (0.9 a week) | 0.89 / 2.44 (his 2.5) | 54% (his 55%) |
| PPST | 1,935 | 7 | 449 | 0.232 | 2.19 | 2.2 | 2.5 | 0.94 / 3.39 (his 3.4) | 30% |
| RMI | 1,822 | 7.5 | 481 | 0.264 | 2.49 | 2.5 | 2.4 (his "two or three") | 0.96 / 3.76 | 29% |
| PS | 1,987 | 9 | 578 | 0.291 | 2.74 | 2.7 | 2.6 | 0.94 / 3.78 | 28% (his 27%) |
| PMAX | 1,369 | 7.8 | 501 | 0.366 | 3.44 | 3.4 | 1.8 (his "about two") | 1.01 / 4.28 | 24% |
| SMB | 965 | 7 | 449 | 0.465 | 4.38 | 4.4 | 1.25 (his "about one") | 1.00 / 6.34 (his "more than six times") | 24% |
| VST | 339 | 7.27* | 467 | 1.377 | 12.96 | 12.9 | 0.44 (his "about five a year") | 1.09 / 11.9 (his "almost 12") | not given |

Notes on the table:

- \* VST's yearly figure comes from the Solana trade: 196R is 42% of the total, so the total is 467R. Without that
  trade, VST makes 0.80R a trade, which is 7.5× Supertrend, as he says.
- The mean loser and winner come from his win rates and PFs. Supertrend's win rate is taken as 30%.
- PMAX's "almost 8" is taken as 7.8.

**What the table shows:**

- **Consistent.** His figures agree with each other.
- **"R a year on each market"** is pooled R spread evenly over the markets, not a per-market median.
- **Losers average about 1R.** That is the 1R stop, plus costs and gaps, minus the losers that an opposite signal
  closed early.
- **Cost per trade.** The runs with costs doubled imply that one unit of his costs is about 0.06R a trade for
  Supertrend, rising to about 0.11R for SMB as holding times get longer. That fits a cost model that charges financing.

### 3.5 What his rules leave open (a pre-registration must settle these)

- **The stop's ATR.** Its length (14, or the indicator's own 10?) and the price it is measured from (the next open, or
  the signal candle's close).
- **Stop fills.** Whether the stop is checked against each bar's high and low (assumed), and how a gap through it
  fills.
- **Signals in the direction of an open trade.** Examples:
  - SMB: a BOS after a BOS;
  - PS: the "RE" labels, or a long after a short cross that its gate rejected;
  - VST: a second buy triangle, when the flip down between them printed none.

  Are such signals ignored, or do they reset the stop? And after a stop-out, is the next signal in the same direction
  taken? Supertrend, PPST, PMAX and RMI always alternate, so only the opposite-signal case arises for them.
- **Filters and exits.** When a filter blocks an opposite signal, does that signal still close the open trade? His
  exit is "the opposite signal"; the filter governs entries.
- **The halves.** Split by time (about mid-December 2023) or by number of trades?
- **"Profitable on most of the markets":** read as at least 6 of 11.
- **Which marks count as signals:**
  - PS's labels: does "RE" count?
  - SMB's BOS and CHoCH alike: yes, since he says to take every signal;
  - VST: the triangles only (yes).
- **Data:**
  - his feeds and their 4H session boundaries. As study 2 noted, TradingView's gold 4H and daily candles may follow
    the 17:00 New York day;
  - his volume: exchange volume for the coins, tick volume for the CFDs?
  - his cost and financing levels.
- **The 1H Supertrend test:** presumably the same rules, with the 1H ATR.

## 4. Testable claims, numbered

**Defaults for every row**, unless the row says otherwise:

- the script's default signals and his rules (3.1);
- the 4H chart, 1 January 2021 to 31 October 2026;
- costs ×1, both long and short.

**Pooled figures.** His figures pool 11 markets. On ours, each claim is checked per market (gold, BTC), so a pooled
figure becomes a check of the same direction, and a similar size, on that market.

**Column "Ours":**

- **G:** gold.
- **B:** BTC.
- **info:** testable only on the claim-check markets USTECm, EURUSDm or GBPUSDm.
- **no:** needs a market we do not hold.

### 4.1 Supertrend, the baseline

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 1 | It makes money, barely: about 0.1R a trade after costs (3,022 trades over 11 markets) | mean net R per trade: positive and small | G, B |
| 2 | Seven trades in ten lose | win rate (net R above 0): about 30% | G, B |
| 3 | PF 1.17, and 5R a year on each market | PF; R per year | G, B |
| 4 | Its average winner is 2.5R | mean R of the winning trades | G, B |
| 5 | Four in ten trades are losers closed within two days | share of all trades with net R below 0 and held under 48 hours | G, B |
| 6 | It trades about once a week on every market | trades per week (his figures imply 0.9) | G, B |
| 7 | Doubling every cost removes more than half its profit: 55%, from 5R to 2.3R a year | R at costs ×2 divided by R at ×1 | G, B |
| 8 | Without its five best trades it made only 48R over the 11 markets, out of about 320R | total R minus the five best trades; per market, the share of R in the five best | G, B |
| 9 | On 1H the same signals lose: more than 11,000 trades, PF 0.98 (4H: 1.17) | Supertrend on 1H against 4H: PF and R per trade | G, B |
| 10 | The EMA200 filter (buys only above it, sells only below) almost halves the trades, lifts PF from 1.17 to 1.33, and almost doubles R per trade | filtered against plain: trades, PF, R per trade | G, B |
| 11 | Supertrend made nothing in 2025 | R in calendar 2025 | G, B |
| 12 | His example episodes, at his feed's prices (see the list below the table) | the trades inside those windows: dates, prices, R | G, B for three of them; the rest no (information only) |

The episodes in claim 12:

- **BTC, January 2023:** one buy at about $16,860, sold 26 days later near $22,800, about 30R. Ours: B.
- **Gold, March 2023:** +6.8R on the breakout, then six trades that made nothing, with 1.6R left after five weeks.
  Ours: G.
- **BTC, June 2022:** five trades, all losers, −3.7R. Ours: B.
- **XRP, August to November 2022:** 16 losers in a row, about −15R. Ours: no.
- **BNB, October 2023:** four stops, −4.2R. Ours: no.
- **ETH, February 2025:** five stops, −5.2R. Ours: no.
- **USDJPY, September 2021:** six trades in six weeks, five losers, −2R. Ours: no.
- **BNB, May to October 2025:** 24 trades, 18 losers, +1.2R in total. Ours: no.

### 4.2 The six as a group

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 13 | Each of the six makes more R per trade than Supertrend: PPST 2.2×, RMI 2.5×, PS 2.7×, PMAX 3.4×, SMB 4.4×, VST 12.9× | R per trade divided by Supertrend's, per market; and the order | G, B |
| 14 | Per year they make about 1.5 times Supertrend's R; with costs doubled, more than 2 times | R per year divided by Supertrend's, at costs ×1 and ×2 | G, B |
| 15 | Each wins less often than Supertrend but has a bigger average winner ("they win bigger") | win rate and mean winner, against Supertrend's | G, B |
| 16 | Each passes the five checks: at least 200 trades; a profit in the older and in the newer half; a profit on most markets; a profit without its five best trades; a profit at costs ×2 | the checks, per market. The 200-trade and "most markets" checks only pooled over G and B, or as information | G, B |
| 17 | On the five coins, each of the six has PF above 1.7; on gold, their PFs lie between 1.4 and 2.8 | PF of each script on BTC (one of his five coins; he does not say whether 1.7 is per coin or pooled) and on gold | G, B |
| 18 | Forex is flat (five of the six make about nothing; VST makes 2.27), and the stock indexes lose (five of the six; only PS stays just above water) | PF of each script on EURUSDm and GBPUSDm (forex) and on USTECm (NASDAQ) | info |
| 19 | Longs carry all six; on five of them, the shorts are about break-even or worse (VST is the exception) | R from longs against R from shorts, per script | G, B |
| 20 | 2025 was flat or negative for most of the six | R in 2025, per script | G, B |
| 21 | They mostly catch the same big moves | overlap of the best trades across the six: how many of each script's five best trades share their dates with another script's five best | G, B |
| 22 | They win about one trade in four, and ten losses in a row will happen | win rates; the longest losing streak per script and market | G, B |

### 4.3 Pivot Point SuperTrend (PPST, LonesomeTheBlue), #6

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 23 | 1,935 trades (a third fewer than Supertrend), 27% winners, PF 1.34, 7R a year on each market, 4.9R a year at costs ×2, average winner 3.4R | the same figures; trades compared with Supertrend's | G, B |
| 24 | Its best market is Solana (PF 2.6), then BNB (2); it loses on the S&P 500, the NASDAQ, EURUSD and GBPUSD | PF on USTECm, EURUSDm and GBPUSDm | info |
| 25 | With the EMA200 filter: PF 1.47 in both halves, 9 of 11 markets profitable | the filtered PF in each half | G, B |
| 26 | One fast candle does not move the line; it moves only when the swings move | on the port, count the bars where the line moves without a new pivot. The band's ATR term changes every bar, so the literal claim is expected to fail. The practical version of the claim is fewer flips than Supertrend (claim 23) | G, B |
| 27 | Gold 4H, March 2023: one buy at about $1,863, no flip, sold 35 days later near $1,995, +6.3R, while Supertrend took seven trades. BTC, October 2026: a buy stopped within a day | those trades | G, B |

### 4.4 RMI Trend Sniper (RMI, TZack88), #5

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 28 | 1,822 trades, 26% winners, PF 1.37, 7.5R a year on each market, two or three trades a month on each market, 5.3R a year at costs ×2 | the same figures | G, B |
| 29 | It held in both halves: PF 1.48 in the older half; the newer figure is garbled, but must be below 1.37 | PF in each half | G, B |
| 30 | Its two best trades were on coins (BNB early 2021, 96R; XRP November 2024, 94R); Solana and BNB PF above 2; gold 1.45; the S&P 500 0.64 ("keep it away" from stock indexes) | PF on gold; USTECm as the nearest index | G; info |
| 31 | Bad years: 2022 cost it 72R and 2025 another 59R, across the 11 markets | R by calendar year | G, B |
| 32 | With ADX above 20 on the signal candle: PF 1.43, about the same in both halves | the filtered PF, overall and in each half | G, B |
| 33 | "Don't add another oscillator", add trend strength instead: an oscillator filter helps less than ADX. He gives no figure for an oscillator | needs an oscillator filter fixed in advance (for example, RSI(14) on the trade's side of 50), against ADX above 20 | G, B |
| 34 | Its sell needs a real fall, so it sells late and its winners run | median holding time and mean winner, against Supertrend's | G, B |
| 35 | BNB 4H, October 2023: one buy at $213, held 24 days through the pullbacks, sold at $242, +8.1R (Supertrend: four stops, −4.2R). BNB, October 2026: a buy stopped within two days | not testable on our data (no BNB) | no |

### 4.5 Precision Sniper (PS, WillyAlgoTrader), #4

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 36 | 9R a year on each market (the best of the six), 1,987 trades, 26% winners, PF 1.42, 6.5R a year at costs ×2 | the same figures | G, B |
| 37 | Doubling the costs takes only 27% of its profit (Supertrend: 55%) | R at ×2 divided by R at ×1, compared with Supertrend's | G, B |
| 38 | Without its five best trades, still almost 300R across the 11 markets (Supertrend: 48R) | R minus the five best trades, per market | G, B |
| 39 | It is the widest: 9 of 11 markets profitable (Solana 2.5, XRP 1.8, gold 1.6), and the only one of the six that made money on the NASDAQ | PF on gold; USTECm | G; info |
| 40 | Longs made nearly all of its profit; shorts only broke even; its worst run was 20 losses in a row (on XRP) | R of longs against shorts; the longest losing streak | G, B |
| 41 | With the EMA200 filter: PF from 1.42 to 1.59, with 10 of 11 markets profitable | filtered against plain | G, B |
| 42 | ETH 4H, February 2025: one short at $2,641, held 23 days, +5.1R, while Supertrend took five stops (−5.2R). Gold, October 2026: a long on a Friday, stopped on the Monday | the gold trade | G (the ETH example: no) |

### 4.6 Profit Maximizer (PMAX, KivancOzbilgic), #3

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 43 | 1,369 trades (less than half of Supertrend's), 26% winners, PF 1.49, almost 8R a year on each market from about two trades a month, 5.9R at costs ×2 | the same figures | G, B |
| 44 | All five coins and gold made money: Solana 2.65, Ethereum 2.1, Bitcoin 1.8 | PF on BTC (his figure: 1.8) and on gold (above 1) | G, B |
| 45 | Its shorts lost money; it was much stronger in the older half (PF 1.81, against 1.2 in the newer half); 2025 was a losing year | R by side; PF in each half; R in 2025 | G, B |
| 46 | Trade only the buys, on coins and gold (a sell label means close and wait) | long only against long and short | G, B |
| 47 | When the signal agrees with the daily chart's EMA50: PF 1.63, and the newer half improves the most, to 1.53 | the filtered PF, overall and in each half | G, B |
| 48 | One wild candle cannot flip it, because the EMA must cross the line: it flips less than Supertrend | flips per year, against Supertrend's | G, B |
| 49 | USDJPY 4H, September 2021: one buy at 110.4, no sell label for 35 days, out at 113.6, +8.2R (Supertrend: six trades, five lost, −2R). Solana, September 2026: a buy stopped a day later | not testable on our data (no USDJPY or SOL) | no |

### 4.7 Smart Money Breakout Signals (SMB, AlgoAlpha), #2

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 50 | 965 trades (less than a third of Supertrend's), PF 1.58, 7R a year on each market from about one trade a month, 5.3R at costs ×2 | the same figures | G, B |
| 51 | 20% winners (four in five lose), but the average winner is more than six times the average loser: "the whole edge" | win rate; mean winner divided by mean loser | G, B |
| 52 | Solana 3.3, gold 2.8, XRP and BNB above 2; the worst of the six on GBPUSD and both indexes | PF on gold; GBPUSDm and USTECm | G; info |
| 53 | Its longest losing streak was 26 trades, on BNB, across a whole year | the longest streak and how long it lasted | G, B (information) |
| 54 | With ADX above 20: PF 1.65 | filtered against plain | G, B |
| 55 | Inside a range it prints nothing, where Supertrend flips; and its signals come late, because a swing is confirmed 25 candles (about four days on 4H) after it forms | share of Supertrend's signals that fall in stretches with no SMB signal; bars from the swing to the signal | G, B |
| 56 | "Take every signal", since you cannot know which one will be the big one: the result rests on a few trades | share of R in the five best trades; R after skipping signals at random (a number of draws set in advance) | G, B |
| 57 | BTC 4H, June 2022: one short at $27,550, covered 26 days later at $22,130, +4.5R; the long after it was stopped (Supertrend: five losers, −3.7R) | those trades | B |

### 4.8 Volume SuperTrend AI (VST, Zeiierman), #1

| # | Claim (his figure) | What to measure | Ours |
|---|---|---|---|
| 58 | On BTC 4H the line flipped 246 times, and only 49 flips printed a triangle (one in five) | the counts on BTCUSDm 4H. They depend on the volume source (section 8) | B |
| 59 | 339 trades in all (about five a year on each market), 19% winners, an average winner of almost 12R, PF 2.56, about 7R a year on each market, 9 of 11 markets profitable | the same figures | G, B |
| 60 | Its sell signals made money too, unlike those of five of the six | R of the shorts | G, B |
| 61 | One trade (Solana, February 2021: $9.50 to $185 over 280 days, 196R) is 42% of all it made; without it, VST is 7.5× Supertrend per trade | share of R in the best trade, per market; R per trade without it | G, B |
| 62 | On gold it lost 20 times in a row over three years, and 2024 was flat | the longest losing streak on gold and how long it lasted; R in 2024 | G, B |
| 63 | With the EMA200 filter: PF from 2.56 to 2.79 | filtered against plain | G, B |
| 64 | It is "the one for forex": USDJPY 3.3, EURUSD almost 3; 2.27 across forex | PF on EURUSDm and GBPUSDm | info |
| 65 | BNB, May to October 2025: one buy, no sell triangle for 176 days, +49R (Supertrend: 24 trades, 18 lost, +1.2R) | not testable on our data (no BNB) | no |

### 4.9 His advice, stated as claims

| # | Claim | What to measure | Ours |
|---|---|---|---|
| 66 | Pair one script with one filter from another family (the EMA200, ADX above 20, the daily chart); a second trend line adds nothing ("they'll just agree") | a script plus a second trend line from the six (for example, PMAX and PPST agreeing), against the script plus the EMA200 or ADX | G, B |
| 67 | Exit on the opposite signal, "not before": no target beats a target | his exit against the scripts' own targets (PS: 1R to 3R; SMB: its three targets) and against a fixed 2R or 3R target | G, B |
| 68 | Trade it on 4H; below 4H is worse (he shows this only for Supertrend, claim 9) | the six on 1H against 4H | G, B |

### 4.10 Claims settled by the code (no data needed)

His descriptions of how each script works, paraphrased, with what the code says:

- **Supertrend.** A line 3 ATR from the middle of each candle, which only rises in an uptrend and flips on a close
  through it: true.
- **PPST.**
  - A centre line through the pivots, with the band 3 ATR from it: true.
  - One fast candle does not move it: true of the centre, but not of the line, which carries an ATR term that changes
    every bar.
- **RMI.** The average of the RSI and the MFI; a buy on a cross above 66 while a fast EMA rises; a sell below 30: true.
  The sell also needs that EMA to be falling, and the fast EMA is a 5-bar EMA.
- **PS.** A 13/34 cross on 4H under the Auto preset, followed by a checklist: true. But the evidence differs from the
  default in version 2.3.0:
  - the RSI is only a veto on extremes;
  - the MACD factor is its acceleration, not its sign;
  - three factors he does not mention are added: the trend EMA's slope, a structure break and the VWAP.
- **PMAX.** It ignores price, and flips when an EMA crosses the line: true. The EMA is of the candle middle, not of the
  close.
- **SMB.**
  - Swings with 25 candles on each side; a signal on a close beyond the last swing; nothing printed inside a range:
    true. With no new break, there is no signal.
  - A "dashed line" to the breaking candle: no. That line is solid; the target lines are the dashed ones. A trivial
    point.
- **VST.** A volume-weighted Supertrend with a nearest-neighbours label; a triangle only on a flip with full agreement;
  the circles are not the signal: true.

### 4.11 Not testable here

- The 86,000 boosts.
- That 51 other indicators were tested and six passed.
- The publication dates.
- The five private indicators.
- Every per-market figure on ETH, SOL, BNB, XRP, USDJPY and the S&P 500.

## 5. The combinations he recommends or builds

| # | Combination | His result | The rule, as he states it | What he leaves open |
|---|---|---|---|---|
| K1 | Supertrend + EMA200 | PF from 1.17 to 1.33; trades almost halved; R per trade almost doubled | buys only above the 200 EMA, sells only below it | which chart and price the EMA uses (4H close assumed); whether a blocked opposite signal still closes the trade |
| K2 | Supertrend on 4H, not 1H | 1H: more than 11,000 trades, PF 0.98; 4H: PF 1.17 | if you trade it below 4H, change that first | nothing |
| K3 | PPST + EMA200 | PF 1.47 in both halves; 9 of 11 markets | as K1 | as K1 |
| K4 | RMI + ADX above 20 | PF 1.43, almost the same in both halves | ADX above 20 on the signal candle; no extra oscillator | the ADX length (TradingView's default of 14 and 14 assumed); the DI direction is not used |
| K5 | PS (Auto preset) + EMA200 | PF from 1.42 to 1.59; 10 of 11 markets | as K1 | as K1. PS already has a trend EMA (89) and an ADX factor inside |
| K6 | PMAX long only, on coins and gold | no figure (its shorts lost money) | trade the buys; a sell label means close and wait | nothing |
| K7 | PMAX + the daily EMA50 | PF 1.63; the newer half 1.53 | take the signal when it agrees with the 50 EMA on the daily chart | what "agrees" means. Assumed: the last closed daily candle is above the daily EMA50 for a buy (this avoids using the day still forming) |
| K8 | SMB, on coins and gold only, + ADX above 20 | PF from 1.58 to 1.65 | take every signal; the filter is optional | as K4 |
| K9 | VST, triangles only, + EMA200 | PF from 2.56 to 2.79 | as K1; hold until the opposite triangle | as K1 |
| K10 | His recipe | no figure | see the list below | nothing |

**K10, his recipe:**

- one script (not all six) plus one filter from another family: the EMA200, ADX, or the daily chart;
- never two trend lines;
- the 4H chart;
- enter at the next open after a candle closes;
- a stop 2 ATR away, and no target;
- out on the opposite signal;
- risk 1% a trade or less.

**Which script he recommends for which trader:**

- the Supertrend look: PMAX or PPST;
- the most profit per year: PS;
- breakouts: SMB;
- momentum: RMI;
- forex, or the fewest trades: VST.

**His market advice:**

- PMAX and SMB on coins and gold only;
- RMI away from stock indexes;
- VST for forex.

## 6. His own scripts and strategy

- **None of the six is his, and neither is Supertrend.** PMAX (Profit Maximizer) is KivancOzbilgic's: the video calls
  it the Supertrend author's own fix for Supertrend, and the file carries KivancOzbilgic's header. Video 2 included two
  of his scripts (Session Hunter, Coil Breakout AI); this video has no TradeIQ script to port.
- **His private indicators (TradeIQ MAX).** Advertised at 0:55 and 25:34. They are not tested, no results are shown,
  and there is no code:
  - **AI VWAP:** a VWAP with a nearest-neighbours model that colours each candle green, red, or grey for "stay out";
  - **Nebula Flow:** eight momentum readings blended into one line, with a cloud that grows as momentum builds;
  - **Fibonacci AI:** Fibonacci levels drawn on the last impulse, with every pullback into the golden pocket scored;
  - **Volume Nexus:** buy and sell flow, relative volume, and a live volume profile;
  - **Apex Levels:** support and resistance that counts touches and signals when a level breaks.
- **His backtest sheet.** The source of every number in the video: rules, balance curves and every trade, with the
  account size and risk adjustable. It sits behind the $7.99-a-month membership, and we do not have it.
- **His "strategy".** In this video it is the test itself (3.1) plus the closing recipe (K10): one of the six with one
  filter from another family, on 4H, entry at the next open after a close, a 2 ATR stop, no target, out on the opposite
  signal, risk of 1% a trade or less, and the expectation of ten losses in a row.

## 7. What he says about Supertrend in general

- **What it is.** A line 3 ATR from the middle of each candle. It sits under price in an uptrend and only rises; a close
  through it flips it.
- **Settings.** He tests only the defaults (ATR 10, factor 3). He says nothing about other ATR lengths or factors, the
  ATR calculation method, other price sources, or Supertrend on a higher timeframe, and he does not tune it.
- **Where it works:** clean trends. BTC in January 2023 gave about 30R from one signal; gold's March 2023 breakout gave
  +6.8R.
- **Whipsaws.** In sideways markets, every push through the line is a new signal. His examples:
  - XRP 2022: 16 losers in a row, about 15R;
  - gold after March 2023: six trades, none profitable;
  - ETH, February 2025: five stops;
  - BTC, June 2022: five losers;
  - BNB, October 2023: four stops;
  - USDJPY, September 2021: five of six trades lost;
  - BNB, May to October 2025: 18 of 24 trades lost.
- **The statistics behind the whipsaws:**
  - four in ten trades are losers closed within two days;
  - it trades about once a week;
  - seven trades in ten lose;
  - its profit sits in a few big trends: without its five best trades, 48R of about 320R.
- **Costs**, "the quiet one." About 3,000 trades each pay fees and a spread, so doubling the costs takes 55% of its
  profit.
- **The fixes he shows:**
  - the 4H chart instead of 1H: PF from 0.98 to 1.17;
  - the EMA200 as a direction filter: PF 1.33, half the trades, twice the profit per trade.

  With a filter, Supertrend is "a fair tool", but no better than the first three alternatives without one.
- **How the six avoid the whipsaws** (his explanations):
  - PPST anchors the line on swing pivots;
  - RMI waits for a deep fall in momentum before selling;
  - PS filters the EMA cross with a checklist;
  - PMAX lets an EMA, not price, cross the line;
  - SMB trades only breaks of 25-bar swings and stays silent in ranges;
  - VST needs a nearest-neighbours label to agree with the flip (one flip in five on BTC).
- **His view of trend following:**
  - these tools win about one trade in four and live on a few big trends;
  - their money came from longs, on coins and gold, while those markets rose in 2021-2026;
  - 2025 was flat or negative for most of them, Supertrend included.

## 8. Before replicating this on gold and BTC

- **Selection.**
  - The six are the best of 52 indicators, chosen on the same data that produced the numbers. His checks on the two
    halves and on removing the five best trades guard against part of that, not all of it.
  - Each filter is the one he reports for that script, out of an unstated number tried on the same data.
- **His best markets were in a bull market, as he says.** Coins and gold rose in 2021-2026; the longs made the money,
  and the shorts did not.
- **His figures for our two markets are few:**
  - gold PFs: RMI 1.45, PS 1.6, SMB 2.8; PMAX above 1; all six between 1.4 and 2.8;
  - VST's run of 20 losses on gold;
  - BTC: PMAX's PF of 1.8 and VST's 246 flips and 49 triangles;
  - PF above 1.7 for all six on the five coins together;
  - his examples on gold (March 2023, October 2026) and on BTC (January 2023, June 2022, October 2026).
- **His ranking favours slow indicators.** R per trade grows as trades get fewer and longer. Per year the six differ
  much less: 7R to 9R, against Supertrend's 5R.
- **Profit is concentrated in a few trades:**
  - VST's best trade is 42% of its profit;
  - RMI's two best trades are 190R of about 480R;
  - Supertrend's five best trades are about 85% of its R.

  On one market, VST takes about 31 trades over the whole window, so results there will be noisy.
- **Costs.**
  - His costs include financing, and his stress test doubles them.
  - Studies 1 and 2 charged Exness spreads with no swap, and stressed them ×1.5.
  - PMAX, SMB and VST hold trades for weeks or months, so swaps could matter on Exness gold and BTC.
- **Script versions.** PS is version 2.3.0, and its evidence differs from his description (1.2). VST's file is a later
  revision. Neither file may be what he ran.
- **Volume.** RMI's MFI, PS's volume and VWAP factors and VST's centre all use volume, which on Exness is tick volume.
  For BTC, studies 1 and 2 also used Binance spot volume.
- **Licences.** VST is CC BY-NC-SA (non-commercial); the others that state a licence are MPL 2.0. Studies 1 and 2 kept
  the third-party sources out of the public repository and wrote their own ports.
- **Earlier work on Supertrend in this repository** (pointers only):
  - `backtest_results/improve/external_strategies.md`: Supertrend 10 × 3 on H4, always in and long only, on gold and
    BTC. On gold it lost in 2021 and 2022, and most of its gold profit came in 2025-26;
  - `backtest_results/final10/FINAL10.md`: entry #10, V3-lite with an H4 Supertrend filter;
  - `backtest_results/silver/SILVER.md`: C12, Supertrend H4 at 10 × 4.0;
  - `backtest_results/ladder/LADDER.md`.

## 9. Garbled or uncertain words in the transcript

- **Names:**
  - "Salana" = Solana;
  - "TZAC 88" = TZack88;
  - "Willie Algo Trader" = WillyAlgoTrader;
  - "Kievanch Obig" = KivancOzbilgic;
  - "Zyman" = Zeiierman;
  - "PAX" and "Pmax" = PMax;
  - "a DX" = ADX;
  - "VWOP" = VWAP;
  - "Nebulaf Flow" = Nebula Flow;
  - "R" written as "are", as in "15 are" and "7 are".
- **Numbers:**
  - **RMI's newer-half PF** is written as "seven". It must be below the overall 1.37, because a pooled PF lies between
    the PFs of its halves; perhaps 1.27.
  - **PS's ETH exit** is written as "228". It must mean about $2,280: a fall from $2,641 to $228 in 23 days would be a
    91% drop.
  - **VST's BNB example:**
    - "$66": BNB traded in the hundreds of dollars in May 2025, so the price has lost digits;
    - "$176 days" means 176 days;
    - the exit price is heard as "177", with music over it. That cannot be BNB's price at the end of October 2025, so
      it is garbled too.
  - **Repeated digits** from the captions: "2.2 2", "1.42 42", "1.65 65", "2.65, 65".
- **Merged sentences:**
  - in PPST's chapter, the caption runs "BNB made two" straight into the next sentence. It reads as: BNB made 2; on
    the two stock indexes and on EURUSD and GBPUSD it lost money;
  - "all five coins in gold" means all five coins and gold.
