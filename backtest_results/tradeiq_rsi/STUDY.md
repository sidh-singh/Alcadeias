# The TradeIQ video, studied: four "better RSIs", what they do and what our test found

28 Nov 2026. These are the study notes behind `RESULTS.md`. It explains each indicator so you can use it without the
video: what it measures, how TradeIQ says to trade it, what he claims, and what our test on Exness gold (XAUUSDm)
and BTC (BTCUSDm) found. It ends with your MA200 idea and with how the indicators were rebuilt.

**The source.** The source is TradeIQ's video on four RSI replacements (17.5 minutes), its transcript, and the four
TradingView scripts you sent. He says he read 12 free RSI alternatives, rebuilt 8 and tested them against the RSI. He
used 7 markets (Bitcoin, Ethereum, Solana, gold, Nasdaq, S&P 500, EUR/USD), the 1-hour, 4-hour and daily charts,
2021 to now, with trading costs. His own results are in a paid sheet that we did not see, so we tested his claims
ourselves.

**Our test in brief.**

- **What ran:** 750 rule variants on 1-hour, 4-hour and daily charts, on real Exness ticks with real spreads.
- **The periods:** January 2019 to June 2024 was used to choose. July 2024 to November 2026 was kept back as an exam.
- **Results** are in dollars per 0.01 lot after costs. P/DD is net profit divided by the worst drawdown (above 1 is
  good).
- **The three numbers in a row** (for example "+345, −44, +1,875") are Development (2019 to 2022), Validation (2023 to
  June 2024) and the hold-out exam (July 2024 to November 2026).

## The four at a glance

| Video rank | Indicator | What it is for, per the video | Its rule, per the video | Beat the plain RSI? (pairs won, 3 periods) | Our verdict |
|---|---|---|---|---|---|
| 4 | **QQE MOD** | stay out when nothing is happening | buy on blue bars, sell on red, wait on gray | gold 31, 17, 22 of 48; BTC 22, 46, 19 of 48 | Cuts trades and losing streaks. It does not beat the RSI on profit. |
| 3 | **Bjorgum TSI** | remove the noise | above 0 only buys, below 0 only sells | gold **40, 51, 47** of 54; BTC 40, 47, 23 of 54 | The most consistent of the four on gold. On BTC it worked until mid-2024, then did not. |
| 2 | **Volume Weighted RSI** | follow the money (volume) | if the histogram shows chop, wait; else above 50 buy, below sell | gold 38, 30, 47 of 54; BTC 29, 16, 18 of 54 (Binance volume 44, 15, 28) | Better than the RSI on gold, worse on BTC: the opposite of what the video says. |
| 1 | **Laguerre RSI** | stop getting shaken out of a trend | above 50 up, below 50 down; pair with a trend filter | gold 36, 26, 38 of 54; BTC 37, 31, 25 of 54 | Far fewer trades. It won on gold 1H, but did not beat the RSI on every timeframe. |

A "pair" is the same chart, rule, filter and stop, once with the indicator and once with the plain RSI(14). The
indicator wins the pair when it makes more net profit. More than half of the pairs is a win for the claim.

## The plain RSI and the four problems the video names

**What it is.** RSI(14) compares the average up-move with the average down-move over 14 bars, on a 0 to 100 scale
(Wilder's smoothing). Above 50, up-moves dominate.

**The video's four problems with it:**

1. It is noisy: it crosses 50 many times inside a clean trend.
2. The 70 / 30 levels are wrong in a trend: the RSI can sit above 70 for weeks.
3. It never says "stay out": in a range every cross of 50 looks like a signal.
4. It ignores volume.

**What our test says.** These are fair descriptions. In like-for-like pairs the plain RSI trades two and a half
to three times as often as the Laguerre RSI, and about twice as often as QQE MOD and the TSI. But trading more did not
make it worse everywhere:

- On gold, the plain RSI on the 4-hour chart (long only, above the 4-hour MA200) was one of the three finalists, and
  it passed the exam.
- On BTC, the plain RSI with the same rule beat all three BTC finalists in the exam.

The RSI's reversal rule is the one that really fails: buy up through 30, sell down through 70. Its median result was a
loss in 2019 to 2022 and in the exam on both markets (gold −425 and −675, BTC −162 and −392).

## 1. QQE MOD (by Mihkel00): the video's number 4

**In one line:** a smoothed fast RSI with a volatility band. The bars turn blue or red only when momentum is strong;
otherwise they are gray.

**How it is calculated**

1. Take RSI(6) of the close and smooth it with a 5-bar EMA.
2. Measure how much that line moves bar to bar, and smooth that too. This works like an ATR, but for the RSI.
3. Build two trailing bands around the smoothed RSI with it, a wide one (factor 3.0) and a narrow one (1.61). Each
   gives a "trend line" that flips when the RSI crosses it.
4. Draw a Bollinger band (50 bars, 0.35 deviations) around the wide trend line.
5. Colour the bar:
   - **Blue** when the RSI is above 53 (50 plus the 3-point threshold) and above the upper Bollinger band.
   - **Red** when it is below 47 and below the lower band.
   - **Gray** otherwise.
6. The white line is the narrow trend line minus 50.

**Settings:** RSI 6, smoothing 5, factors 3.0 / 1.61, threshold 3, Bollinger 50 x 0.35 (the defaults).

**How the video says to trade it**

- Buy only when the bars are blue, sell only when they are red, and wait when they are gray.
- In a trend, stay in through a few gray bars on the pullbacks, as long as no red bar appears. Do not take profit
  at 70 like the RSI tells you.
- Read the colour, not the height of the bars.
- The white line crossing zero means momentum changed sides, "but the bars are what you trade".
- Pair it with your levels: blue bars at support, red bars at resistance. Put the stop beyond the level.

**Where the video says it fails:** at a sharp V-bottom the bars stay gray while price is already flying, so you get
in late. The bars also do not see resistance levels.

**What the video claims:** fewer trades than the RSI on every market and timeframe; it beats the RSI on most of them;
it has shorter losing streaks.

**What we tested:**

- long on blue, short on red, holding through gray (both sides, and long only);
- flat on gray (the "wait" rule);
- the white-line cross as a control;
- each with no filter, an MA200 filter or the TSI filter, and with or without a stop.

**What our test found**

- **Fewer trades: true.** It traded less than the RSI in all 48 pairs, on both markets and in all three periods.
  That is about half the RSI's trades (median 44% to 54%).
- **Shorter losing streaks: true.** Gold 34 and 40 of 48 pairs, BTC 42 and 48 of 48.
- **Beats the RSI on profit: mixed.** On gold it won 31, 17 and 22 of 48 pairs; on BTC 22, 46 and 19 of 48. It lost
  most pairs in the exam on both markets.
- **"Gray = wait" against "hold through gray":** neither is better every time. Across all variants on gold, waiting
  on gray had a lower median in 2019 to 2022 (−158 against +45) and a higher one afterwards (+130 against +79, then
  +1,876 against +1,614).
- **Its best gold variant was finalist 1 and passed the exam.** That is the 1-hour chart, long only, above the
  4-hour MA200: +1,552 per 0.01 lot, P/DD 2.48. But the plain RSI with the same rule made +1,511 (P/DD 2.35), so the
  QQE added little.
- **Its best BTC variant** (4-hour, long only, above the 4-hour MA200) made +274, +166 and +243.

The video's setup tested as described (blue buy, red sell, gray wait; no filter, no stop):

| Market | Chart | Development | Validation | Hold-out |
|---|---|---|---|---|
| Gold | 4-hour | +345 (P/DD 1.37) | −44 (−0.12) | +1,875 (1.73) |
| Gold | daily | −157 (−0.36) | +148 (0.55) | +902 (0.76) |
| BTC | 4-hour | −58 (−0.12) | −125 (−0.40) | +272 (0.71) |
| BTC | daily | +225 (0.91) | +132 (0.60) | +573 (2.08) |

**How you could use it.** Use the colour as a "stay in or stay out" guide. It cuts the number of trades in half and
shortens losing runs, and that is real. Do not expect it to make more money than the plain RSI. On gold it worked
best on the 1-hour chart, long only, with the 4-hour MA200 as a filter.

## 2. Bjorgum TSI (True Strength Index): the video's number 3

**In one line:** momentum smoothed twice, from −100 to +100. Above 0, momentum is up.

**How it is calculated**

1. Take each bar's price change.
2. Smooth it with a 25-bar EMA, then smooth the result again with a 5-bar EMA.
3. Do the same with the size of the change (ignoring its sign).
4. TSI = 100 x the first result / the second.
5. The signal line is the 14-bar EMA of the TSI.

**Settings:** speed "Fast": short 5, long 25, signal 14 (the default; the video says to leave it on Fast). The zero line
is hidden by default: turn on "Show Zero Line".

**How the video says to trade it**

- Use the zero line, not the signal line. Above 0, only look for buys; below 0, only sells.
- It is a trend filter, not an entry. Enter on a pullback to a level in the TSI's direction. While the TSI stays
  above 0 during a pullback, the trend is intact.
- Set alerts to "once per bar close".

**Where the video says it fails:** because it is smooth, it never catches the exact top or bottom; it confirms a move
after it has started. In a range it drifts around 0 and gives crosses that go nowhere.

**What the video claims:** the zero line works; the signal line is a coin flip; it beats the RSI on most markets with
about half the trades; it is good on crypto on the daily chart.

**What we tested:**

- long above 0 and short below (both sides), and long only above 0;
- the 30 / −30 reversal levels;
- the signal-line cross as a control;
- "TSI above 0" used as a filter for every other indicator (filter F3).

**What our test found**

- **The zero line makes money: true.** The plain zero-line rules (no filter) made money in 8 and 10 of 12 variants on
  both markets. In the exam it was 12 of 12 on gold and 8 of 12 on BTC.
- **The signal line is a coin flip: true on BTC, false on gold.**
  - On BTC the signal-line rules made money in only 1 and 0 of 6 variants, and the zero line beat them in 6 and 5 of
    6 pairs.
  - On gold the signal line did fine (4 of 6 made money in both periods); the zero line won only 2 and 3 of 6.
- **It beats the RSI.** On gold it won 40, 51 and 47 of 54 pairs: the most consistent of the four. On BTC it won 40
  and 47 of 54 up to June 2024, but only 23 of 54 in the exam.
- **About half the trades: true.** The median was 52% to 60% of the RSI's.
- **As a filter for other indicators** (only longs while the TSI is above 0), it helped on both markets by the plan's
  rule: gold 36, 36 and 40 of 60 pairs; BTC 55, 59 and 48 of 78.
- **Finalists.**
  - Gold: its best variant (1-hour, long only, above the 4-hour MA200) missed the third finalist slot by $0.52 of net
    over 5.5 years. Its exam result of +2,061 (P/DD 3.46) is information only.
  - BTC: its best variant (4-hour, long only, above the 4-hour MA200) was finalist 3 and passed with +252 (P/DD
    1.02). But the plain RSI with the same rule made +344 (P/DD 1.17).

The video's setup tested as described (zero line, no filter, no stop):

| Market | Chart | Long & short | Long only |
|---|---|---|---|
| Gold | 4-hour | +187, +223, +2,413 | +364, +359, +1,832 |
| Gold | daily | −15, −32, +2,294 | +261, +228, +1,769 |
| BTC | 4-hour | +139, +136, −69 | +133, +299, −49 |
| BTC | daily | +576, +306, +335 | +351, +384, +156 |

**How you could use it.** The TSI's zero line as a trend filter is the most useful idea in the video for these two
markets: "only buy while the TSI is above 0". It made money in most variants, it traded about half as often as the
RSI, and it worked as a filter on both markets. It is not an edge on its own over the plain RSI on BTC.

## 3. Volume Weighted RSI (by AlgoAlpha): the video's number 2

**In one line:** the RSI, but each bar's move counts in proportion to its volume. A histogram underneath shows chop.

**How it is calculated**

1. The RSI(14) formula, with each bar's gain and loss multiplied by that bar's volume. A big candle on big volume
   pushes it hard; a quiet drift barely moves it.
2. The consolidation histogram counts how often the line crossed 50 over the last bars, smoothed twice with Hull
   averages. It is above 0 while the line keeps flipping (chop), and exactly 0 after about 37 bars on one side.

**Settings:** RSI length 14, consolidation length 10 (the defaults).

**How the video says to trade it**

- Read it in two steps. First, the histogram: if the market is chopping, wait. If not, read the line: above 50 the
  money is buying, below 50 it is selling.
- It is a trend tool. Its 20 / 80 reversal markers are no better than the RSI's, so do not call tops and bottoms with
  it.
- It needs real volume: use it on crypto or stocks, not on forex or CFDs, which only have tick volume.
- Pair it with the higher timeframe. On the 4-hour chart, take its signals only in the direction of the daily trend:
  if Bitcoin is above its 200-day moving average, take only the moves above 50.

**What the video claims:** its trend rule beats the RSI on every crypto market and timeframe; its reversals are no
better than the RSI's; it needs real volume.

**What we tested:**

- the side of 50 (both sides, and long only);
- "stand aside while the histogram is above 0";
- the 20 / 80 reversals;
- each with the filters and stops.

Volume: Exness has no traded volume, so the tick count of each bar was used. TradingView does the same on CFD charts.
For BTC every rule was run a second time on Binance BTCUSDT spot volume: real exchange volume, 78 extra variants.

**What our test found**

- **It beat the RSI on gold** in all three periods: 38, 30 and 47 of 54 pairs. That is on tick volume, where the
  video says not to use it.
- **On BTC with tick volume it did not:** 29, 16 and 18 of 54. Its trend rule lost every 1-hour pair.
- **With Binance volume:** 44, 15 and 28 of 54. "Beats the RSI on every crypto timeframe" does not hold with either
  volume.
- **"It needs real volume": unclear.** Against the same rule on tick volume, Binance volume did better in 2019 to 2022
  (60 of 78) and in the exam (55 of 78), but worse in 2023 to June 2024 (11 of 78).
- **Reversals no better than the RSI's:** true on BTC (it won 1 and 2 of 6). False on gold, where its reversals beat
  the RSI's in 6 and 4 of 6 pairs (few trades).
- **The "stand aside in chop" rule did not pay.** On gold its variants had median results of −9 and −86, with only 2
  of 24 making money in 2023 to June 2024. On BTC the medians were −31 and −35.
- **Finalist.** Its best BTC variant (daily chart, stand aside in chop, 3-ATR stop) was finalist 2 and failed the exam
  (−109).

The video's setups tested as described (no stop):

| Market | Setup | Development | Validation | Hold-out |
|---|---|---|---|---|
| Gold | 4-hour, stand aside in chop, both sides | −91 | −96 | +705 |
| Gold | 4-hour, long only, only above the daily MA200 | +209 | +228 | +1,884 |
| BTC | 4-hour, stand aside in chop (tick volume) | −25 | −46 | +236 |
| BTC | 4-hour, stand aside in chop (Binance volume) | +167 | −102 | +273 |
| BTC | 4-hour, long only above the daily MA200 (tick volume) | +300 | +193 | +21 |
| BTC | 4-hour, long only above the daily MA200 (Binance volume) | +217 | +193 | −141 |

**How you could use it.** On BTC the video's exact pairing worked before mid-2024 and faded in the exam: 4-hour
signals, only above the daily 200 MA. The chop histogram did not make money as a stand-aside rule on either market.
If you use it on BTC, feed it real exchange volume, but do not expect it to beat the plain RSI.

## 4. Laguerre RSI (Ehlers, by KivancOzbilgic): the video's number 1

**In one line:** an RSI computed on a four-stage smoothing filter. It moves cleanly from one extreme to the other, and
it stays pinned near 100 in a strong uptrend.

**How it is calculated**

1. Run the price through four linked smoothing stages (a Laguerre filter, alpha 0.2).
2. Compare each stage with the next: add up the rising steps and the falling steps.
3. Laguerre RSI = 100 x rising / (rising + falling).

When all four stages line up upward the value is exactly 100, and it is exactly 0 when they line up downward. On
gold's 1-hour chart that happens on about 40% of bars.

**Settings:** alpha 0.2 (the default). Lines at 20 and 80.

**How the video says to trade it**

- Its alerts are buy when it crosses up through 20, sell when it crosses down through 80. But the video found the
  simpler reading better: above 50 momentum is up, below 50 it is down.
- Pinned near 100: a strong trend, stay in. The first clean drop through 50 is your warning, and your exit. Pinned
  near 0: strong selling, do not try to catch it.
- It is not faster than the RSI (it crosses 50 a few candles later), but it gives far fewer false signals.
- Its weakness is a sideways market, where it swings from 20 to 80 and back.
- On the 1-hour chart it was better than the RSI but mostly did not make money on its own. The 4-hour and daily are
  where it shines.
- Pair it with a trend filter (the TSI above 0, or the 200 moving average) and take only the signals in the trend's
  direction. Example: the 200 MA is rising, the Laguerre RSI drops below 50 on a pullback and crosses back above, and
  that is the entry.

**What the video claims:** it beats the RSI on most markets on every timeframe, in old and new data, with far fewer
trades. It is "the most consistent in the whole test", the one to use on every chart.

**What we tested:**

- the side of 50 (both sides, and long only);
- the 20 / 80 alerts;
- the TSI and MA200 filters;
- the stop.

**What our test found**

- **Far fewer trades: true.** The median was 34% to 42% of the RSI's trades.
- **Beats the RSI on every timeframe: false on both markets.**
  - It lost most 4-hour pairs in 2019 to 2022, on gold (2 of 18) and on BTC (3 of 18).
  - On gold it then lost most 1-hour and daily pairs in 2023 to June 2024; on BTC, most daily pairs.
  - Overall: gold 36, 26 and 38 of 54 pairs; BTC 37, 31 and 25 of 54.
- **On the 1-hour chart it mostly did not make money on its own:** false on gold, where it made money in 6 and 4 of
  6 variants; true on BTC (0 and 2 of 6).
- **4-hour and daily are where it shines:** true on BTC, false on gold. On gold the 1-hour chart did as well or
  better.
- **Pair it with a trend filter:**
  - MA200: helped on BTC (18 and 15 of 24 pairs); mixed on gold (1 and 13 of 24).
  - TSI above 0: did not help on gold (4 and 3 of 12); mixed on BTC.
- **Finalists.**
  - Gold: its best variant was finalist 2 and passed the exam: the 1-hour chart, long only, above the 1-hour MA200.
    It made +1,967 (P/DD 2.19) against +1,220 for the plain RSI with the same rule, with about 40% of the trades.
    This is the clearest win of any indicator over its RSI twin.
  - BTC: its best variant was finalist 1 and failed the exam: daily chart, long only, TSI above 0, 3-ATR stop. It
    made +114 (P/DD 0.29) against +229 for its RSI twin.
- **"The most consistent":** not on these two markets. On gold the TSI was more consistent against the RSI.

The video's setups tested as described (no stop):

| Market | Chart | Side of 50, both sides | Long only, TSI > 0 | Long only, above the MA200 | 20 / 80 alerts |
|---|---|---|---|---|---|
| Gold | 4-hour | −94, +328, +1,195 | +167, +367, +1,692 | +156, +332, +1,268 | −322, −292, +2,749 |
| Gold | daily | +102, −139, +2,953 | +408, +123, +2,083 | +185, +180, +1,895 | −37, +525, +179 |
| BTC | 4-hour | +139, +268, −199 | +158, +359, −133 | +263, +346, +178 | −618, +132, −304 |
| BTC | daily | +538, +138, +415 | +402, +264, +112 | +299, +258, +266 | +241, +393, −694 |

For comparison, the plain RSI on the side of 50, both sides, no filter:

- gold 4-hour +216, +108, +1,431; gold daily −235, −53, +652;
- BTC 4-hour +143, −82, −13; BTC daily +442, +182, +460.

**How you could use it.** It does what the video says about trading less: it stays on one side of 50 through a trend.
On gold's 1-hour chart, long only above the MA200, it was clearly better than the RSI. Elsewhere it was not reliably
better. Its 20 / 80 alerts were hit and miss: on BTC they lost money in most variants in 2019 to 2022, and in all
of them in the exam.

## 5. Your idea: the 200 moving average (MA200)

**What it is:** the simple average of the last 200 closes of the chart. Price above it means the long-term trend is
up.

**How we tested it**

- **As a filter on the same chart:** longs only while the bar closed above its MA200, shorts only below. A position
  closes when the filter turns against it.
- **As a higher-timeframe filter:** the same with the last closed bar of a bigger chart. The 4-hour MA200 was used for
  1-hour rules, and the daily MA200 for 1-hour and 4-hour rules.
- **As a strategy on its own:** long above the MA200 and short below, or long above and flat below.

**What our test found**

| Filter | Gold: pairs improved (3 periods) | BTC: pairs improved (3 periods) |
|---|---|---|
| MA200 of the same chart | 15, 46, 43 of 72 | 63, 66, 55 of 90 |
| MA200 of the 4-hour chart, 1-hour rules | 12, 19, 13 of 24 | **30, 29, 29 of 30** |
| MA200 of the daily chart, 1-hour and 4-hour rules | 7, 25, 42 of 48 | 45, 38, 42 of 60 |

- **BTC: the MA200 filter helped, most of all on the 1-hour chart.** The 4-hour MA200 improved almost every 1-hour
  rule in all three periods. Part of the gain is simply trading less: the median 1-hour BTC rule made 1,406 trades in
  2019 to 2022 without a filter and 937 with the 4-hour MA200, so it paid far fewer spreads. On the daily chart the
  daily MA200 did not help (3 of 30 in 2019 to 2022, 10 of 30 in the exam).
- **Gold: it depends on the years.** In 2019 to 2022 (a peak in August 2020, then two sideways years) the MA200
  filters cost money in most rules. From 2023, in a steady rise, they helped. The bots' final-ten study found the same
  for a 200-day filter on gold: less drawdown, but it gives up the choppy years.
- **The finalists.** Four of the six finalists use an MA200 filter, and so does the best TSI on gold. That fits the
  idea, but on gold a long-only rule above an MA200 is also a way to be long in a rising market.
- **MA200 alone.**
  - BTC, 4-hour chart, long above the MA200: it qualified (12th of 59) and made +324, +376 and +316 (exam P/DD 1.03),
    level with the TSI finalist.
  - Gold: no version qualified. The best, the 1-hour chart long above the MA200, had a 2019 to 2022 drawdown too large
    for its profit (P/DD 0.63).

**How you could use it.** On BTC, "only buy while price is above the 4-hour MA200" is the one rule in this study that
improved nearly every 1-hour rule in every period. That makes it worth testing on the bots' own BTC designs, in a new
pre-registered test or a demo forward run. It was not tested on the bots here. On gold, expect it to cut drawdowns in
trends and cost money in sideways years.

## What the video also says, which we did not test

- **The ones that lost to the RSI.**
  - Heikin Ashi RSI: twice the trades, lost on almost every market.
  - RSI Kernel Optimized: a tie with the RSI.
  - Stochastic Momentum Index: flipped twice as often; useful only for buying dips on Nasdaq and S&P 4-hour.
  - An eighth one is not named.
- **Setup tips:**
  - keep the default settings;
  - set alerts to once per bar close;
  - use one indicator, not all four, because they mostly agree;
  - watch it beside the RSI for a week.
- **His pick by market, and what our test says:**

| The video says | Our test on these two markets |
|---|---|
| Crypto: start with the Volume Weighted RSI | On BTC it was the weakest against the RSI (16 to 29 of 54 on tick volume). |
| Gold or indices on the 4-hour chart: the Laguerre RSI or the TSI | On gold 4-hour the TSI won 5, 16 and 16 of 18 pairs against the RSI; the Laguerre RSI won 2, 16 and 2 of 18. |
| Sideways traders: QQE MOD, the gray bars keep you out | It does keep you out: half the trades. It does not make more money. |
| One indicator for every chart: the Laguerre RSI | Not supported. It was mixed on gold and lost in the exam on BTC. |

## How the indicators were rebuilt (porting notes)

The full record is `PORTING.md`. In short:

- **Two independent ports.** Two engineers rewrote the four TradingView scripts in Python, each without seeing the
  other's work. On every 1-hour, 4-hour and daily bar of both markets, the two give the same numbers, bit for bit, on
  every line. The only difference is the QQE colour on the first six bars of a series, before the RSI exists.
- **The Pine details that decide the numbers** were settled from TradingView's reference and its recorded output:
  - **Hull average.** It rounds half-lengths down (a length of 5 uses 2). This one changes the VW RSI chop histogram
    on about 4% of bars, so it was fixed before any result.
  - **Integer division.** In AlgoAlpha's Pine v5 script, 2/3 is 0. This only scales the histogram.
  - **The QQE.** Its v6 copy starts without a trend direction until the first cross.
  - **The TSI signal line.** Your copy of the TSI script stops before the signal line. TradingView's published script
    continues with `ta.ema(tsi, 14)`, which is what was used.
- **No indicator line ever sits exactly on a level that a rule reads,** from 2019 on. A rounding difference from
  TradingView therefore cannot flip a signal. There is one exception: five BTC bars where the VW RSI histogram is
  exactly 0 in exact arithmetic.
- **What could still differ:** TradingView itself was not run. A CSV export of a TradingView chart would settle the
  last two readings (the EMA start and the Hull half-length). The EMA start changes no signal on our data.

## Where the numbers come from

- **The plan:** `PREREG.md` (frozen before any result) and `DEVIATIONS.md`.
- **Every variant's results:** `results_dev_val.csv`, `results_holdout.csv`, `results_full.csv`.
- **Comparisons with the RSI and with no filter:** `vs_rsi_summary.csv`, `vs_rsi_holdout_summary.csv`,
  `vs_f0_summary.csv`, `vs_f0_holdout_summary.csv`.
- **The claims:** `CLAIMS.md`.
- **Medians across variants:** quoted here only as descriptions of those files. They were not part of the selection.
