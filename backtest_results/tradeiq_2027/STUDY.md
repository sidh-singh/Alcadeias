# The TradeIQ video 2, studied: nine indicators for 2027, what they do and how we tested them

28 Nov 2026. These are the study notes of study 2 (`backtest_results/tradeiq_2027/`), written before its results. For
each of the nine scripts they say what it computes, what TradeIQ says and claims about it, and how we turned it into
rules for Exness gold (XAUUSDm) and BTC (BTCUSDm). The results, from `RESULTS.md`, were added later: the short
answer below and the paragraphs headed "What our test found".

> **The short answer**
>
> - **Gold:** the best finalist, the ribbon on 1H (long only, 4H MA200), made +2,264 per 0.01 lot in the hold-out
>   (July 2024 to November 2026), with a P/DD (profit / worst drawdown) of 4.55; buy-and-hold made +1,251 (0.58). But
>   it failed the Early exam (2017-2018) with +7 (0.07), and gold's rally made the hold-out easy: 63% of all gold
>   variants pass it. Only 1 of the 11 gold champions passed both exams.
> - **BTC:** 4 of the 6 champions passed the hold-out, against 22% of all BTC variants, while BTC itself lost money.
>   The best were two 4H trend rules with an MA200: the ribbon (+434, P/DD 1.78) and the dashboard's
>   break-of-structure trend (+372, 1.61).
> - **Your MA200 idea:** the 4H MA200 is the only filter that helped on both markets. The same chart's MA200 and the
>   daily MA200 did not help on gold and were mixed on BTC.
> - **The video's claims:** those about how the tools behave mostly hold (the ribbon flips less than a plain average
>   cross, the dashboard changes its higher rows live); those about making more money mostly do not (half out at the
>   second target instead of the script's exit, tightening on Heikin Ashi candles, the dashboard's bias as a filter).
> - **Should anything go to a bot? No.** With 1,543 variants tried, the best results of 2019-2022 cannot be told apart
>   from luck, and over the last five years the bots' current designs made more money (on years they were chosen on,
>   which flatters them). The 4H MA200 is now being tested on the bots' own designs (study 3).

**The source.** The source is TradeIQ's video "9 best TradingView indicators going into 2027" (about 17 minutes), its
transcript, and the code of eight of the nine scripts, which you sent. The ninth, Coil Breakout AI, is his own private
script. He says he read the code of this year's most popular and newest scripts and kept nine that do more than one
job and look good. Two are his own: Session Hunter (free) and Coil Breakout AI. The only test results in the video
are for his own two scripts.

**Our test in brief.**

- **What runs:** 1,543 rule variants: 775 on gold, 762 on BTC and 6 claim checks on other markets. 1,458 of them can
  be chosen (738 on gold, 720 on BTC); the other 85 (some controls, the placebos, the sensitivity and information
  rows) are scored but never chosen. Every input is the script's default unless the plan says otherwise.
- **The charts:** 5- and 15-minute (M5, M15) for the two session scripts (the opening range and Session Hunter);
  1-hour, 4-hour and daily (1H, 4H, 1D) for the others. Real Exness ticks and spreads, as in study 1.
- **The periods:** January 2019 to June 2024 is used to choose. July 2024 to November 2026 is kept back as the exam.
  Gold also has an Early exam: 2017 and 2018.
- **Results** are in dollars per 0.01 lot after costs. P/DD is net profit divided by the worst drawdown (above 1
  is good). The plan (`PREREG.md`) was frozen first; every later reading of it is in `DEVIATIONS.md`.

## The nine at a glance

| Video rank | Script (author) | What it draws | What the video claims (claim numbers of PREREG 8) | Our rule families |
|---|---|---|---|---|
| 9 | **Heikin Ashi Candles, Trend Strength & Trend Age** (LunqFX) | smoothed candles graded strong, steady, weak or indecision; the trend's age and how rare it is | manage trades with it, do not enter with it: hold on strong candles, tighten on weak ones (4; on the ribbon also 3); the panel's odds (5) | HA-MANAGED, HA-ENTRY |
| 8 | **Harmonic & Chart Patterns** (AI-AlgoCode) | 22 harmonic and 16 chart patterns, each with a trade plan: entry, stop and two targets | confirmed late and drawn back, so old charts flatter them (18); trade chart patterns on the breakout (19) | HP-HARMONIC, HP-CHART |
| 7 | **Ultimate Opening Range Breakout** (LuxAlgo) | the 09:30-10:00 New York range, its first breakout (high or low volume), targets, a trail, hit rates | the break often sets the day's direction (6); take high-volume breaks (7); hit rates are not win rates (8); the default clock is an hour late in summer (9) | ORB |
| 6 | **Session Hunter** (TradeIQ, free) | session levels, sweeps, and five ICT setups with a stop and three targets | his own test: best on the Nasdaq, smaller on forex, nothing held up on gold and crypto (10) | SH |
| 5 | **Swing Profile** (BigBeluga) | a volume profile on every swing leg: its busiest price (POC) and its buy-minus-sell volume | price often returns to the last leg's POC (11); a leg up on weak buying is a warning (12) | SP |
| 4 | **Market Structure Dashboard** (Flux Charts) | one trend bias from seven timeframes: structure, order blocks, fair value gaps, swing position | one look filters out many bad trades (13); the higher rows can change before their candle closes (14) | MSD-ALONE, MSD-FILTER, BOS |
| 3 | **Coil Breakout AI** (TradeIQ, private) | quiet "coils", graded breakouts, 1-3R lines and a trail | 731 trades, one in four won, average winner 8.5R; three filters helped (20; cannot be tested) | COIL (our own squeeze rule) |
| 2 | **Wyckoff** (theUltimator5) | accumulation and distribution ranges walked through the five Wyckoff phases; an entry | strict and rare (15); the risk is smallest at the spring and its test (16); use it on 4H or daily (17) | WY, WY-DERIVED |
| 1 | **Trend Target Ribbon** (BOSWaves) | a smooth average with a ribbon; trend flips with a stop and 1-4R targets | flips ignore most noise (1); take some profit at the second target (2); the stop never moves, so manage it (3) | RIB, ALMA-X (and STK, section 10) |

**Words used below.** **ATR** (average true range) is the typical size of one bar, over 14 bars. **R** is the risk: 1R
is the distance from the entry to the stop, so a 2R target lies twice that distance beyond the entry. A **variant**
(or row) is one complete rule: chart, entry, stop, exits and filter. A **family** is a group of variants that gets at
most one champion. **Look-ahead** is using a value before it could be known; our rules read only what is known at a
bar's close (except HP-DRAWN, an information row that looks ahead on purpose).

## 1. Heikin Ashi Candles, Trend Strength & Trend Age (by LunqFX): the video's number 9

**In one line:** averaged candles that keep one colour through a trend, graded by their shape, with a panel that says
how old the current run of one colour (a streak) is and how rare that age is.

**How it is calculated** (all defaults)

1. The Heikin Ashi close is the average of the bar's open, high, low and close; its open is the middle of the previous
   Heikin Ashi body. The candle is green when its close is at or above its open.
2. Each candle is graded INDECISION (a body of at most 25% of the candle, with wicks on both sides), STRONG (a wick
   against the colour of at most 5%), WEAK (the same colour as the last candle, with a smaller body) or STEADY.
3. The **rare age** is the candle at which 90% of past streaks of that colour were shorter; the panel also shows how
   often a streak of this age lasted 5 more candles. On our charts the median streak is 3 candles and the rare age
   comes at about the 9th or 10th candle (the 8th on BTC 1H).

**What the video says:** use it "not for entries", but to manage a trade you are already in: stay in while the candles
are strong, and move the stop closer when weak candles follow one another, or when an indecision candle follows a
strong run. **Claims tested:** 4 (M2, M3 and M5 against the same rule without them) and 5 (the panel's odds, computed
before each year, against that year). The overlays on the ribbon also serve the ribbon's claim 3.

**Our rules**

- **HA-MANAGED** (54 rows per symbol): six changes, each added to nine bases. **M1** exits on a colour flip against
  the trade; **M2** raises the stop to break-even (or that bar's low, if tighter) at indecision after 2 or more strong
  candles; **M3** does the same at every weak candle that is at least the second in a row; **M4** exits at the rare
  age; **M5** is M1 + M2; **HA-AND** takes the base's entries only when the candle has the entry's colour.
- **The bases:** the ribbon's flips (both sides, and long only) on 1H, 4H and 1D, and study 1's three finalists. On
  gold those are QQE MOD 1H, Laguerre RSI 1H and the RSI 4H, each long only above an MA200, with no stop; on BTC, the
  Laguerre RSI daily (long only, TSI above 0) and the volume-weighted RSI daily (standing aside in chop, on Exness
  tick volume as in study 1), both with a 3-ATR stop, and the TSI 4H, long only above the 4H MA200, with no stop.
- **HA-ENTRY** (24 rows, controls): **HA-H1** enters at a streak's first strong candle and exits at the flip;
  **HA-H2** is a colour stop-and-reverse. Both sides and long only; no filter or the next timeframe's MA200 (on 1D the
  chart's own); 1H, 4H, 1D; no stop.

**Readings that matter**

- The statistics use every streak since the data start, without the script's cap of 5,000 per colour (HA-R10).
- A trade reacts only to its own colour's events: a long tightens when a green run tires (HA-R1).
- Break-even is the actual fill; if price is already below it, M2 and M3 exit at the next open (HA-R7).
- The rare age is computed at every close, as the live alert would. The script computes it on the chart's last bar
  only, so a TradingView chart never shows a past one (porting/ha.md, reading 12).
- HA-AND refuses at most 2.5% of the ribbon's flips, so those rows are near copies of their bases (HA-R4).

**What our test found.** On gold both families gave a champion. M2 on study 1's RSI 4H finalist made Development
(2019-2022) +346 per 0.01 lot (P/DD 2.28), Validation (2023 to June 2024) +219 (1.86), hold-out (July 2024 to
November 2026) +853 (0.98) and Early (2017-2018) +75 (1.15): it is the only one of gold's 11 champions that passed
both exams, though the RSI rule without M2 made more in the hold-out (+1,479, P/DD 1.20) and less in Early (+41,
0.45). HA-H2 (the colour rule) on 1D, long only, made +310 (1.06), +166 (0.66), +943 (0.52) and +39 (0.20) in the
same order: it passed the hold-out only, with a hold-out P/DD below buy-and-hold's 0.58. On BTC, HA-AND on study 1's
Laguerre RSI daily finalist was finalist 1 (+425 (2.78) and +264 (1.74)), but in the hold-out it took the same 20
trades as that finalist and failed again (+114, P/DD 0.29). No BTC HA-ENTRY row qualified: the best, HA-H1 on 1D,
long only above the daily MA200, had only 5 of 16 positive Development quarters (+288 (1.19), then +274 (2.50) and +8
(0.02) in the hold-out). Claim 4 does not hold for profit (M2, M3 and M5 beat their base in at most 4 of 9 pairs in
each window, except BTC's M5: 5, then 0 of 9, mixed), but it holds for drawdown: M2 and M5 had a smaller one than
their base in most pairs on both markets, M3 only on gold. Claim 5 holds on both markets (the year's share fell
inside the panel's 95% range in 89% and 93% of gold cells, 80% and 93% of BTC cells); as managers of the ribbon's
trades (claim 3), the overlays did not help on gold (12 and 5 of 30 pairs) and were mixed on BTC.

## 2. Harmonic & Chart Patterns (by AI-AlgoCode): the video's number 8

**In one line:** a pattern hunter: it looks for 38 shapes in the chart's swings and draws a trade plan for each.

**How it is calculated** (all defaults)

1. A zigzag joins the swing highs and lows (a swing high is the highest high of the last 5 bars), about one swing
   every 7 bars. Its last points are X, A, B, C and D, with D the newest.
2. **22 harmonic patterns** (Bat, Butterfly, Crab, Gartley, Shark, AB=CD, 5-0, Three Drives and variants) test ratios
   between the legs and say the move into D is ending. **16 chart patterns** (double and triple tops and bottoms, head
   and shoulders, wedges, expanding triangles, pennants, flags) need a close beyond their neckline.
3. A pattern is **confirmed** at the next swing, a median of 3 bars after D, and then drawn back at D. A **forming**
   pattern uses the swing that is still moving as its D, and it can vanish.
4. **The plan.** Harmonic: entry at D, stop 13% of the A-to-D move beyond D, targets 38.2% and 61.8% of that move back
   (2.94R and 4.75R). Chart: entry at the neckline, stop half the pattern's height beyond it, targets 1 and 1.618
   heights (2R and 3.24R). A plan lasts 30 bars.

**What the video says:** a pattern is confirmed only at the next swing and then drawn back at D, so a past chart makes
the patterns look better timed than they were live. Treat it as "a map, not a signal", and trade chart patterns on the
neckline breakout, "where the entry is real". **Claims tested:** 18 (the plan as drawn at D, with look-ahead, against
the real entries) and 19 (a stop order at the neckline, and the forming entry, against the confirmed alert).

**Our rules** (event rules; every trade ends at the latest 30 bars after D)

- **HP-HF** (27 rows): a market entry at the first bar of each forming harmonic; TP1, TP2 or half at each; skipped if
  the close is already at or past TP1; no filter, the next timeframe's MA200 (F2) or its ribbon (FR), on 1D the
  chart's own; 1H, 4H, 1D. **HP-HC** (3, a control): the confirmed harmonic alert.
- **HP-CF** (12): the forming chart pattern; TP1 or TP2; F0, F2 or FR; 1H and 4H. **HP-CS** (4): a stop order at the
  neckline once all but the breakout close holds. **HP-CC** (2, a control): the confirmed chart alert.
- **HP-DRAWN** (10, information only): the plan as an old chart shows it, entered at D with look-ahead.

**Readings that matter**

- HP-HF enters once per forming pattern, at its first bar: 1,144 candidates on gold 1H in 2019-2022 (PATTERNS-P2).
- The TP1 skip drops 85 of those forming entries but 401 of 840 confirmed alerts: confirmation is late (PATTERNS-R4).
- HP-CS places its order even if the close is already past the neckline; it fills at the next open (PATTERNS-R6).
- F2 is the next chart up: the 4H MA200 on 1H, the daily on 4H; on 1D, the daily chart's own MA200 (PATTERNS-R1).

**What our test found.** No pattern row qualified on either market. The best were forming chart patterns on 4H
(HP-CF). On gold, with TP2 and no filter, HP-CF made Development +226 (P/DD 2.27), Validation +76 (0.95), hold-out
+103 (0.25) and Early +13 (0.18); it missed only because 7 of its 16 Development quarters were positive (8 were
needed). On BTC, with TP1 and the ribbon filter, it made +81 (2.57), +1 (0.06) and −4 (−0.04) in the same order, on 21
Development trades (30 were needed). The harmonics were worse: only 5 (gold) and 4 (BTC) of their 30 eligible rows
made money in Development; gold's best (1D, half at each target, ribbon filter) made +43 (0.49) on 10 trades and had
no trade in Validation, then +310 (2.48) on 2 hold-out trades and +0.4 on its 1 Early trade, and BTC's best (4H, TP1,
ribbon filter) made +120 (1.71), −68 (−0.68) and +16 (0.12). Claim 18 holds for the harmonics on both markets: drawn
back at D with look-ahead, they won more often than the real forming entries in 54 and 48 of 54 gold pairs and in all
54 BTC pairs in both windows; for the chart patterns it does not hold. Claim 19 does not hold: the stop order at the
neckline (HP-CS) beat the confirmed alert in 0 and 0 of 2 gold pairs and in 1 and 0 of 2 BTC pairs.

## 3. Ultimate Opening Range Breakout (by LuxAlgo): the video's number 7

**In one line:** the first half hour of New York stock trading (09:30-10:00) sets a range; the script labels the first
break of it and shows how far price usually travels.

**How it is calculated** (all defaults, except the clock and the days)

1. The range is the high and low of the bars opening from 09:30 to 10:00 (the same range on M5 and M15). Targets T1,
   T2 and T3 lie 1, 2 and 3 range widths beyond each edge. Example: a gold range of $2,000 to $2,006 has T1 at $2,012
   and T2 at $2,018 above it. The median width in 2019-2022 was $5.70 on gold and $147 on BTC.
2. From 10:00, the first close beyond each side gets a label, tagged HV when the bar's volume is above its 20-bar
   average, else LV. The first label opens the script's own trade if none is open, with a trail that starts at the
   bar's low minus 2 ATR and only rises (a short mirrors it).
3. A dashboard gives, per target, the share of days on which price reached it, with or without a breakout.
4. Its clock is a fixed UTC−5, an hour late from March to November. We use New York time, on weekdays (BTC too).

**What the video says:** a break of the range often decides the day's direction. Use it on 5- or 15-minute Nasdaq,
S&P 500 or US stock charts; take the high-volume breaks; pick the target by the hit rates, which count every day and
so are not win rates. **Claims tested:** 6 (the 16:00 close is beyond the range on the side of the first break), 7 (HV
against LV), 8 (the dashboard's rates against the rates after past breaks; O4 against O2 and O3) and 9 (UTC−5 against
New York time).

**Our rules** (event rules on M5 and M15; entries up to 16:00; flat by 16:55 New York, before gold's 17:00 break)

- **O1** is the script's trade (the trail or the flat time; no stop). **O2**, **O3** and **O4** put the stop at the
  range's far side: O2 aims at T1, O3 at T2, and O4 at the furthest target reached after at least half of the past
  breaks of that side (T1 while there are fewer than 60 such breaks, or when no target reaches half). **O5** sets stop
  orders at both edges from 10:00 to 16:00, one cancelling the other, with the stop at the far side and O1's exits.
- Filters: F0, HV, F2-4H, F2-1D, HV with F2-4H, and long only on gold. Controls: LV only, the UTC−5 clock, BTC on all
  seven days. Our own: ORB-CX and TIGHT (section 10). Gold has 82 rows (72 can be chosen), BTC 66 (54).

**Readings that matter**

- On M15 the COMEX range is 08:30-09:00: bars count by their open, and 08:20 is off the 15-minute grid (ORB-P1).
- On an early-close day the flat exit is booked at the last price before the break, not at the reopen (ORB-R16).
- O4 counts a target as hit only after that day's label, up to the flat time, on past days only (ORB-R5, ORB-R18).
- TIGHT, read as Session Hunter's own test, still keeps 93% of gold's and 98% of BTC's sessions (ORB-R8).

**What our test found.** Only 1 of gold's 72 eligible rows qualified, and none of BTC's 54: on M5 and M15 the spreads
eat most of the edge (the median M5 rule of the two session scripts lost 119 on gold and 246 on BTC in Development).
Gold's champion, O3 (target T2) on M5 with HV and the 4H MA200, made Development +126 (P/DD 1.24), Validation +6
(0.08), hold-out −14 (−0.05) and Early −87 (−0.90), so it failed both exams; the same rule without a filter made +436
(0.97) in the hold-out. BTC's best row, O1 (the script's own trade) on M15 with HV and the 4H MA200, made +128 (1.87),
+155 (2.56) and +75 (0.33) in the same order, but only 7 of its 16 Development quarters were positive. Claims 6, 8
(its first part) and 9 hold on both markets: the 16:00 close was beyond the first break's side on 57.0% and 54.3% of
gold's M5 breakout days (beyond the other side on 14.5%); T1 was reached on 29.9% of all side-days, but after 49.3% of
breakouts (gold M5); and the UTC−5 clock started the range at 10:30 New York on 676 of 1,031 gold sessions, all of
them in daylight saving. Claim 7 is mixed: HV beat LV in 8 and 4 of 8 gold pairs and 1 and 5 of 8 BTC pairs (and in
most hold-out pairs). Picking the target by the hit rates (O4, claim 8's second part) does not hold: O4 beat O2 (the
T1 target) in 0 and 0 of 12 gold pairs and 3 and 0 of 10 BTC pairs. Our COMEX-open range and the tight-range filter
(section 10) were mixed.

## 4. Session Hunter (by TradeIQ, free): the video's number 6

**In one line:** it draws each session's high and low (Asia, London, New York) and yesterday's high and low, and
signals five "ICT" setups when price trades through one of these levels. (ICT is a school of ideas about liquidity:
stops pile up beyond obvious highs and lows; price runs through them, a **sweep**, and often turns back.)

**How it is calculated** (New York time; a trading day runs from 20:00 to 20:00, Monday to Friday; all defaults)

1. Five setups, each at most once a day: **AS** fades a sweep of the Asia range (20:00-24:00) in 02:00-05:00; **LS**
   of the London range (02:00-05:00) in 07:00-11:00; **PD** of yesterday's high or low in 02:00-11:00. **AB** follows
   an Asia breakout in 02:00-05:00; **OR** an opening-range breakout in 10:00-12:00.
2. Confirmations: a **fair value gap** (FVG, a three-candle gap that shows a one-sided push), a **market structure
   shift** (MSS, a close beyond the last five bars) and the **1H trend** (the side of the 1-hour EMA200). The default
   is FVG + 1H trend.
3. The stop goes at the sweep's extreme or the range's middle (at least 0.5 ATR); the entry is the next bar's open;
   the targets are 1, 2 and 3R; the default exit holds to 16:00. A quirk: Monday almost never trades PD, because its
   "yesterday" is a Sunday session, which is not a weekday.

**What the video says** (his own test, on almost 6 years): the best was the Nasdaq, a sweep of yesterday's high or low
with the 1H trend, held to the close: a profit factor of 1.95 (gross profit divided by gross loss) on 290 trades, with
about 3 in 10 winning. Forex had a smaller edge, the "London Judas swing" (an Asia sweep, then an FVG and a structure
shift, on M15). On gold and crypto "nothing held up". **Claim tested:** 10, with his Nasdaq and forex setups on Exness
USTECm, EURUSDm and GBPUSDm (information only), every row on gold and BTC, and holding to 16:00 against the other
exits.

**Our rules** (event rules on M5 and M15; each setup is a "lane" with at most one trade a day)

- Confirmations K0 (none), K1 (FVG), K2 (FVG + 1H trend) and K3 (FVG + MSS, the forex preset). Exits E1 (hold to
  16:00, which its author says tested best), E2 (2R) and E3 (the swept range's far side; for the two breakouts, one
  range width beyond the broken edge; no trade when it is less than 1R away).
- On both charts: five setups x K1-K3 x E1-E2 (60 rows); K0 x E1 (10); K2 x E3 (10); the Custom (AS + LS), Forex
  (AS, K3) and Nasdaq (LS + PD) presets (6); K2 x E1 with the EMA replaced by F2-4H, F2-1D or F3 (30). That is 116
  rows, plus 2 information rows that give Monday Friday's levels.
- A guess written into the plan before any test: on gold, AB will make money and AS will lose, in both Development
  and Validation (the bots' improvement study had found the Asian-range breakout positive in 5 of 5 periods).

**Readings that matter**

- The 30 trend rows put your MA200 (or the TSI) inside the confirmation, where the EMA sat (SESSION-R5).
- The script's own cancels at entry are measured from the bar's bid open, as it measures them (SESSION-P3, -R4).
- An exit on a new trading day is booked at the last price before the gap, where the script prices it (SESSION-R12).
- E2's 2R target is measured from the actual fill (SESSION-R2).

**What our test found.** No Session Hunter row qualified on either market. Gold's best, the opening-range setup OR on
M15 with K2 (the 4H MA200 in place of the EMA), held to 16:00, made Development +56 (P/DD 0.44), Validation +132
(1.78), hold-out +44 (0.13) and Early −131 (−0.99); in Development it lost money at x1.5 costs. BTC's best, the Asia
breakout AB on M15 with K2 and the daily MA200, made −36 (−0.20), +92 (1.29) and −219 (−0.73) in the same order, and
none of BTC's 116 rows made money in Development. On his own markets (claim 10, information only) the Nasdaq rows had
a profit factor above 1, but only 1.09 to 1.44 in Development against his 1.95; the forex preset was mixed on EURUSD
and held on GBPUSD. "Nothing held up" on gold and BTC is mixed: few rows made money in Development (11 and 0 of 116),
but 59 and 72 of 116 did in Validation. Holding to 16:00 beat the 2R target on gold (20 and 17 of 30 pairs) but not
the far-side target E3 (3 and 5 of 10), and it was mixed on BTC. The plan's guess was half right: on gold the Asia
sweep (AS) lost in most rows (21 and 21 of 24), but the Asia breakout (AB) did not make money (only 3 and 2 of 22 rows
did).

## 5. Swing Profile (by BigBeluga): the video's number 5

**In one line:** a volume profile on every swing leg: the price where the leg traded the most volume (the **point of
control**, POC), and whether the leg was bought or sold.

**How it is calculated** (all defaults; gold tick volume, BTC Binance volume)

1. A new 50-bar high after a new 50-bar low (or the reverse) is a **flip**; it finishes the leg between the last swing
   low and swing high. In 2019-2022 gold had about 80 legs a year on 1H and 22 on 4H, BTC 115 and 27; the daily has
   too few.
2. The leg's range is cut into bins about half an ATR(200) wide; each bar adds its volume to the bins near its close.
   The POC is the busiest bin. Green candles count as buying, red as selling: the **delta** is (buy − sell) / total.
3. A finished leg's POC exists only at its flip, a median of 25-28 bars after its last swing point, and is then drawn
   back over the leg. The forming leg (in white) changes every bar; our rules read it as it is at each close.

Example: a leg up from $1,900 to $1,960 has its POC at $1,935. A bar dips to $1,934 and closes at $1,938 ("touch and
hold"): a long, with the stop at $1,900 and the target at $1,960.

**What the video says:** price often returns to the last leg's POC, so a pullback to it is where to look for an
entry. A rising leg with little buying behind it is a warning sign, however strong the price looks. **Claims
tested:** 11 (the forming POC is touched before the leg ends more often than the leg's 50% level; W1-W3 against their
placebo) and 12 (the next leg is bigger after up legs with negative delta than with positive).

**Our rules** (event rules on 1H and 4H; at most one trade per swing point; shorts mirror longs)

- **W1**, the video's use: while the forming leg is up, a touch and hold of its POC is a long, with the stop at the
  swing low, the target at the swing high, and an exit on a flip against it. **W2**: the stop 1.5 ATR beyond the POC,
  target 2R. **W3**: after a flip, a touch and hold of the finished leg's POC in the new direction, stop 1.5 ATR,
  target 2R.
- Filters: F0; FD, the leg's delta on the trade's side ("weak buying"); F2 (the 4H MA200 on 1H, the daily on 4H); long
  only. That is 24 rows, plus a placebo (12, never chosen) with the leg's 50% level in place of the POC.

**Readings that matter**

- One candidate per swing point, its first allowed touch; if a trade is still open then, that swing point gets no
  trade, and a later touch is not tried (SWING-R1).
- W3 looks from the bar after the flip, because the finished leg's POC is known only at the flip's close (SWING-R4).
- A finished leg's delta has its own sign in 93-97% of legs, so W3 with FD keeps only 1 to 16 candidates in 2019-2022
  (SWING-R6).
- The delta is the script's own bin sum, the number its label shows, so most bars count twice (SWING-P3).

**What our test found.** Only 2 of the 24 eligible rows qualified on each market, and both champions are W2 on 4H (the
stop 1.5 ATR beyond the POC, a 2R target). Gold's, long only, made Development +220 (P/DD 2.13), Validation +65
(1.34), hold-out +272 (0.91) and Early −51 (−0.51): it passed the hold-out only, on just 18 trades. BTC's, with the
daily MA200, made +176 (1.83) and +57 (0.59), then −57 (−0.26) in the hold-out, and failed. Claim 11 does not hold on
gold and is mixed on BTC: price touched the forming leg's POC in 85.2% of gold 1H legs and its 50% level in 81.7%, a
gap that chance could explain (p = 0.121), and on BTC the POC led clearly in Development only; the POC rules beat
their 50%-level placebo in 4 and 8 of 12 gold pairs and 5 and 6 of 12 BTC pairs. Claim 12 does not hold: in
Development gold 1H had only 5 up legs with weak buying (against 154 with more buying than selling), and the leg after
them was smaller, not bigger (median 6.60 ATR against 8.69). As a filter, weak buying (FD) did not help on gold (1 and
1 of 6 pairs) and was mixed on BTC.

## 6. Market Structure Dashboard (by Flux Charts): the video's number 4

**In one line:** a control panel that reads the market structure of up to seven timeframes and sums it into one bias:
BULLISH, LEAN BULL, NEUTRAL, LEAN BEAR or BEARISH.

**How it is calculated** (all defaults: swing length 5; the last 6 order blocks and 6 gaps per row)

1. Each timeframe at or above the chart's is a row (on a 1H chart: 1H, 4H, daily, weekly), with four votes of −1, 0 or
   +1: **structure** (higher highs and higher lows +1); the nearest **order block** (the extreme candle before a
   **break of structure**, a close beyond the last swing); the nearest **fair value gap**; and the **swing position**
   (the bottom 30% of the last swing +1, the top 30% −1).
2. The row scores (−4 to +4) are weighted: 1- and 5-minute 1; 15-minute, 1H and 4H 2; daily 3; weekly 4. Above 50% of
   the maximum the label is BULLISH, above 20% LEAN BULL. Example on a 1H chart: scores of +2, +1, +1 and 0 give 2x2 +
   2x1 + 3x1 + 4x0 = 9 of 44 (20.5%): LEAN BULL.
3. Live, the higher rows use the candle still forming. Our rules use each row's last closed bar, which is what the
   chart shows on past bars.

**What the video says:** check it once before every trade. His example: when the 4-hour, daily and weekly rows are all
bearish, he does not buy on the 5-minute chart. He says this one check keeps you out of many bad trades. **Claims
tested:** 13 (the trades the dashboard filters remove, and the filtered rules against the same rules without a filter
and with your MA200) and 14 (how often a higher row's live score differs from the score its bar closes with).

**Our rules** (state rules on 1H, 4H and 1D)

- **MSD-ALONE** (18 rows): A1 is long at LEAN BULL or better and short at LEAN BEAR or worse; A2 is long only; A3
  trades only at BULLISH or BEARISH. No stop, or a fixed 3-ATR stop.
- **MSD-FILTER** (120): study 1's RSI, Laguerre RSI, volume-weighted RSI, TSI and QQE MOD rules (both sides and long
  only, with or without the stop) with F4 (only on the dashboard's side) or F6, the video's veto (no long while the
  4H, daily and weekly rows all score below 0, no short while they all score above 0; on a 1D chart only the daily
  and weekly rows). Each is paired with study 1's own rows without a filter and with the MA200 filters.
- **BOS** (12), our own: long after a bullish break of structure, short after a bearish one; both sides or long only;
  no filter or the same chart's MA200; 3-ATR stop.

**Readings that matter**

- Our gold 4H, daily and weekly bars follow UTC days. In a scratch test with TradingView-style days from 17:00 New
  York, 4-18% of the labels changed (MSD-P7).
- BTC's daily and weekly rows depend on our data start until mid-2019, gold's until May 2018 (MSD-P3, MSD-P4).
- F6 vetoes a long only while every veto row (4H, daily, weekly) scores below 0; a row at 0 does not veto (MSD-R1).
- The weekly row is 4 of the 11 parts of a 1H chart's score, yet it confirms only about six swing points a year, each
  five weeks late (porting notes).

**What our test found.** The bias alone qualified only on gold: MSD-A2 on 1H (long only, no stop) made Development
+456 (P/DD 1.75), Validation +32 (0.11), hold-out +2,203 (1.85) and Early −72 (−0.43), and passed the hold-out only.
BTC's best MSD-ALONE row, MSD-A2 on 4H with the 3-ATR stop, made +246 (0.82) and +315 (2.23), then −400 (−0.57) in the
hold-out. The veto (F6) gave a champion on both markets: on gold with QQE MOD 1H, long only, +388 (1.38), +251 (1.14),
+1,645 (2.25) and Early +15 (0.10), a pass in the hold-out only; on BTC with the Laguerre RSI daily, both sides and
the stop (finalist 2), +724 (3.43) and +137 (0.60), then a pass with +367 (1.03). Our BOS rule was a BTC champion (4H,
long only above its MA200: +236 (1.01), +370 (3.69), then a pass with +372 (1.61)); on gold no BOS row qualified, and
the best (1D, long only) had only 10 Development trades (+337, P/DD 0.97), then +404 (2.41) on 3 trades in Validation,
+1,896 (1.59) on 6 in the hold-out and −34 (−0.26) in Early. Claim 13 does not hold for the bias filter (F4): it beat
the same rule without a filter in only 25 and 9 of 60 gold pairs and 19 and 21 of 60 BTC pairs, and on gold the trades
it removed made money (+727 and +8,461). The veto is mixed on both markets, and on BTC neither filter beat study 1's
MA200 filters. Claim 14 holds on both: a higher row's live score differed from the score its bar closed with at 19% to
29% of chart closes, and the live label differed from the chart's history at 19.1% (gold) and 20.0% (BTC) of 1H
closes.

## 7. Coil Breakout AI (by TradeIQ, private): the video's number 3, and our COIL rule

**In one line:** before a market moves it goes quiet; the script finds these "coils" and grades the breakout. It is
private (for TradeIQ Max members), so we could not read or test it. **COIL is our own rule, built only from the
video's description.**

**What the video says:** smaller candles and a tighter range make a coil. When it breaks with the trend, the breakout
gets a grade, A, B or C, from its candle size and volume against the last 100 breakouts, with 1, 2 and 3R lines and a
trend trail. **Claim 20:** on eight coins, 4H, since 2021: 731 trades; one in four won, yet its gains were almost three
times its losses, with an average winning trade of 8.5R; of its 11 optional filters, three helped: a big candle, a
surge in volume and trend strength. It cannot be tested: there is no code, and the coins are not our markets.

**Our COIL rule** (PREREG 6.9: the classic "squeeze")

1. **A squeeze bar:** the Bollinger band (the 20-bar average close ± 2 standard deviations) lies inside the Keltner
   channel (the same average ± 1.5 ATR(20)). In words: the closes move less than the bars' ranges suggest.
2. **A coil** is 6 or more squeeze bars in a row; its box is their highest high and lowest low. It is armed from the
   first bar without a squeeze (the "fire" bar) for 12 bars, or until a newer coil replaces it.
3. **The breakout** is the first close beyond the box, once per coil. Its trend check: COIL-RIB (the same chart's
   ribbon on the breakout's side), COIL-MA (its MA200) or COIL-0 (none). The stop is the opposite box edge, kept
   within 0.75 to 3 ATR.
4. **Exits:** X-TR, out at a close more than 3 ATR below the highest close since the entry (shorts mirror it), or at
   the stop; X-3R, the same plus a 3R target.
5. **Grades:** BIG (the bar's range at least 1.5 ATR), VOL (its volume at least 1.5 times the 20-bar average), ADX
   (trend strength: the ADX(14), which measures how strongly price trends in either direction, at least 20) and ALL3.

**Rows:** COIL-RIB x 2 exits x 5 grades ("none" included) x 1H, 4H and 1D (30), plus COIL-MA and COIL-0 with the trail
(6): 36 per symbol. Our grades are fixed thresholds, not a rank against the last 100 breakouts.

**Readings that matter**

- The armed window starts at the fire bar itself, which holds about half of the breakouts (33-56% by chart)
  (COIL-P4, porting notes).
- The box spans the whole squeeze run, so the stop is the 3-ATR cap on 80-90% of breakouts (COIL-P5, porting notes).
- The trail is recomputed every bar with that bar's ATR; it does not ratchet (COIL-R3).
- COIL-RIB removes little: the ribbon already agrees with 94-100% of breakouts (COIL-R11).
- Gold 1D has just the minimum 15 breakouts in 2019-2022: COIL-MA and every grade fall below it (porting notes and
  the coil rule module's counts).

**What our test found.** Only 6 (gold) and 1 (BTC) of the 36 coil rows qualified, but our coil reached the final three
on both markets, each time with the ribbon as its trend check and the 3R target. Gold's finalist 2 (1H, VOL grade)
made Development +367 (P/DD 3.89), Validation +172 (2.02), hold-out +463 (0.84) and Early −36 (−0.45): it passed the
hold-out only, and its hold-out P/DD ranked just 412th of the 699 eligible gold rows. BTC's finalist 3 (1D, no grade)
made +592 (3.23), +25 (0.18) and +166 (0.52) in the same order: a pass, but on only 11 trades. Claim 20 itself cannot
be tested, because the script is private, and COIL says nothing about it. On our coil, on 4H, the profit factor was
above 1 in 2 and 12 of 12 gold rows and in 6 and 7 of 12 BTC rows (mixed on both). The big-candle and volume grades
helped on BTC (4 and 5 of 6 pairs each) and ADX did not (3 and 3); on gold no grade helped, not even the finalist's
volume grade (0 and 2 of 6), and in the hold-out no grade helped on either market.

## 8. Wyckoff (by theUltimator5): the video's number 2

**In one line:** it finds the ranges where big players build a position (accumulation) or unload one (distribution),
and walks each range through the five Wyckoff phases to an entry.

**How it is calculated** (an accumulation; a distribution is the mirror; all defaults)

1. **Phase A:** a **selling climax**: a new 30-bar low in a downtrend, on at least 1.8 times the 50-bar average volume
   and a range of at least 1.5 ATR, confirmed when it is absorbed 3 to 8 bars later. **Phase B:** **secondary tests**
   of the low on lower volume; the range is mature after 30 to 60 bars and two tests.
2. **Phase C:** a **spring** (a dip below the range that closes back inside, trapping the sellers) and its **test**,
   or, without a spring, a quiet "terminal test" of the low; a spring before the range is mature is kept as
   provisional. **Phases D and E:** a **sign of strength** (SOS), a **last point of support** (LPS, a higher low),
   then the markup.
3. **The entry,** once per range: Standard at the Phase C test (else the first LPS), Aggressive at the test or the
   SOS, Conservative at the LPS only. The labels and schematics are drawn back in time; we read only the entry alert,
   which never repaints.

It is rare: in 2019-2022 the Standard entry fired 4 times on gold 1H, twice on gold 4H, 14 times on BTC 1H, 5 times on
BTC 4H and never on a daily chart. Gold uses tick volume, BTC Binance volume.

**What the video says:** it is strict, so it is rare, and when a setup does appear "it means something". Use it on the
4-hour or the daily, and wait for the spring and its test, where the risk is smallest. The grey path it draws ahead
is only the textbook shape, not a prediction. **Claims tested:** 15 (events per year, and a pooled test against random
entries), 16 (stop distance and result in R by entry type) and 17 (entries and results by chart).

**Our rules** (event rules on 1H, 4H and 1D)

- **WY** (36 rows): WY-STD (Standard), WY-STD-L (Standard, long only: "buy accumulation") and WY-AGG (Aggressive). The
  stop sits 0.15 ATR beyond the script's hard level (the entry is skipped if that is under 0.25 ATR from the close).
  Exits: X-S, out at the close of the first bar on which the script's range no longer backs the trade (a reset, a
  demotion, a change of side or the end of Phase E), or X-S3, X-S plus a 3R target. No filter, or the next
  timeframe's MA200 (on 1D the chart's own).
- **WY-DERIVED** (18), our own: WY-CL trades a confirmed climax (stop 0.15 ATR beyond it, out at 2R or after 50 bars);
  WY-SP enters at a spring's recovery bar, confirmed or provisional (stop 0.15 ATR beyond it, X-S or X-S3).
- A BTC control on Exness tick volume (3 rows). A row with under 15 Development trades reads "insufficient events",
  and one pooled test compares WY-STD's trades with 1,000 sets of random entries matched on chart, side, stop and
  holding time.

**Readings that matter**

- The hard level is the script's own: on a climax range without a spring it is the climax low (WYCKOFF-P1).
- Most WY-SP entries are provisional; X-S starts only once the range holds the trade's side (WYCKOFF-P3, WYCKOFF-R2).
- WY-DERIVED's 18 rows are WY-SP with X-S and X-S3 (12) and WY-CL with 2R or 50 bars (6) (WYCKOFF-R1).
- The engine runs from our data start; only gold's Early exam depends on that (WYCKOFF-P8).

**What our test found.** The script's own entries (WY) qualified on neither market: no WY row that made money in
Development had enough trades, and 47 gold and 46 BTC Wyckoff rows had fewer than 15. Gold's best WY row (WY-AGG on
4H, X-S3) traded twice in Development (+77, P/DD 1.50), twice in Validation (+40, 0.77), never in the hold-out and
twice in Early (+11, 0.42); BTC's best (WY-AGG on 1H, X-S) made +116 (1.65) on 16 trades, then −8 (−0.14) in
Validation and −9 (−0.16) in the hold-out. Our WY-CL gave gold's only Wyckoff champion (1H, out at 2R or after 50
bars): Development +145 (1.24), Validation +15 (0.13), hold-out +49 (0.09) and Early −42 (−0.69), so it failed both
exams; on BTC no WY-DERIVED row qualified (the best, WY-SP on 4H, made +93 (1.45) on 11 trades, +85 (1.90), then +9
(0.09) in the hold-out). Pair by pair, our climax and spring entries did not beat the script's Standard entries on
gold and were mixed on BTC. Claim 15 does not hold: the 43 Standard entries of both markets in 2019 to June 2024
averaged −0.27R, against −0.04R for 1,000 sets of random entries (p = 0.94), and the median Standard row gave 0.1
(gold) and 0.9 (BTC) entries a year in Development. Claim 16 holds for the stop but not for the result: the stop was
closest at the test (median 2.90 ATR, against 4.99 at the SOS and 6.94 at the LPS), yet the test entries earned the
least (−0.59R in Development, against +0.46R and +0.31R). Claim 17 does not hold on either market: the daily chart
gave no entry at all in 2019 to June 2024, and 4H beat 1H in both windows only on gold.

## 9. Trend Target Ribbon (by BOSWaves): the video's number 1

**In one line:** a smooth average with a ribbon on its support side; the trend flips only when the average slopes and
price closes clearly beyond a band around it, and each flip draws a trade plan.

**How it is calculated** (defaults: ALMA 34, offset 0.85, sigma 6; band 0.65; slope 0.08; stop look-back 12)

1. An ALMA of the close over 34 bars (a bell-shaped weighted average with 75% of its weight on the last 10 bars), a
   band of ± 0.65 standard deviations of the last 34 closes, and a slope: the ALMA's 3-bar change divided by the ATR.
2. A bull setup is a slope above 0.08 and a close above the upper band on the same bar (a bear setup is the mirror).
   The trend is the side of the latest setup; a **flip** is the first setup of the other side. In 2019-2022 gold
   flipped about 215 times a year on 1H, 62 on 4H and 8.5 on the daily; BTC about 318, 80 and 12.
3. The plan: entry at the flip's close; the stop beyond the extreme of the 12 bars before the flip, kept within 0.75
   to 3 ATR (that distance is 1R); targets at 1 to 4R that only get check marks. The glow is display only.

**What the video says:** the one he would put on every chart for 2027. It flips only when the slope and the close
agree, so most of the noise does not flip it. Take only the flips that agree with the higher timeframe, close part of
the trade at the second target and keep the rest open. The stop never moves, so manage the trade yourself. **Claims
tested:** 1 (RIB against ALMA-X, a plain cross of the same average), 2 (half out at 2R against all out at 2R and no
target) and 3 (break-even after 1R, and the Heikin Ashi overlays, against the fixed stop).

**Our rules** (event rules on 1H, 4H and 1D)

- **RIB-LS** buys bull flips and sells bear flips, reversing at the opposite flip; **RIB-LO** is long only. The stop
  is the "intended" one of the tooltip and the video, set from the actual fill.
- Exits: **X0**, the stop or the opposite flip (the script); **XT2**, all out at 2R; **XP**, half out at 2R (the
  video); **XBE**, the stop to break-even after 1R ("manage it").
- Filters at the flip: on 1H F0, F1, F2-4H, F2-1D, FR (the 4H ribbon), F3 and FS; on 4H the same without F2-4H (FR is
  the daily ribbon); on 1D F0, F1, F3 and FS. That is 136 rows, plus ALMA-X (6, a control) and RIB-LIT (3,
  TradingView's literal stop, never chosen).

**Readings that matter**

- A flip the filter refuses still closes the open opposite trade (its own exit); it just opens nothing (RIBBON-R1).
- The 2R target and XBE's 1R trigger are measured from the actual fill, not from the flip's close (RIBBON-R4).
- TradingView's literal stop reads only the earlier flip bars of its own side; it equals the intended one on only
  34-47% of flips (RIBBON-P1, porting notes).
- Each window starts flat: a trend already running at the window's start is not entered (RIBBON-R8).

**What our test found.** The ribbon gave gold's best rule of the study: RIB-LO on 1H with the script's exits (X0) and
the 4H MA200 (F2-4H), finalist 1, made Development +619 (P/DD 3.49), Validation +261 (1.33), hold-out +2,264 (4.55)
and Early +7 (0.07). It passed the hold-out, 25th of the 699 eligible gold rows by P/DD there, but failed the Early
exam, when gold moved sideways. On BTC only 3 of 136 eligible ribbon rows qualified (19 on gold); the champion, RIB-LS
on 4H with XBE (break-even after 1R) and the chart's own MA200 (F1), made +357 (1.38), +234 (2.15) and +434 (1.78) in
the same order, a pass. The control ALMA-X gave a gold champion too (4H, long only: +266 (1.05), +205 (0.75), +1,397
(0.98) and Early −9 (−0.07), a pass in the hold-out only); no BTC ALMA-X row qualified (the best, 1D, long only: +121
(0.32), +116 (0.51) and +343 (1.06)). Claim 1 holds on both markets: the ribbon took fewer trades than the plain ALMA
cross in all 6 pairs and made more net in 4 and 6 of 6. Claim 2 does not hold against the script's own exit (half out
at 2R won only 11 and 4 of 34 gold pairs and 13 and 0 of 34 BTC pairs), but holds against all out at 2R (23 and 29 of
34 on gold, 21 and 32 on BTC). Claim 3 is mixed: the break-even stop won 7 and 21 of 34 gold pairs and 24 and 10 of 34
BTC pairs, and the Heikin Ashi overlays did not help on gold and were mixed on BTC.

## 10. Our own combinations, and your MA200 idea

**The 2027 chart setup as a rule (STK).** The video's setup is one trend tool (the ribbon), one context tool (the
dashboard), then one tool for timing and one for levels. STK tests its first two parts as state rules with a 3-ATR
stop, both sides and long only, on 1H, 4H and 1D (18 rows).
**STK-RM** is long while the chart's ribbon is up and the bias is LEAN BULL or better (short in the mirror case);
**STK-RA** uses the ribbon and the higher-timeframe MA200 (on 1D, the chart's own); **STK-RMA** needs all three. The
video's crypto setup (Coil Breakout AI with the ribbon and the dashboard, on 4H) is covered by RIB with the dashboard
filter, STK-RM and COIL-RIB on 4H.

**What our test found.** STK-RA on gold 1H, long only (the ribbon and the 4H MA200, with the 3-ATR stop), was finalist
3: Development +504 (P/DD 2.43), Validation +279 (1.42), hold-out +2,259 (3.19) and Early +13 (0.14), so it passed the
hold-out only. It is the ribbon finalist's idea as a state rule, and in the hold-out it made about the same (+2,259
against +2,264) with a larger drawdown (709 against 498). Of the 18 STK rows, 5 qualified on gold and none on BTC;
BTC's best, STK-RA on 4H with the daily MA200, made +154 (0.52), +305 (2.12) and +176 (0.52) in the same order.
Against the ribbon alone (same side and chart, the script's exits, no filter), STK does not help on gold: it won only
5 and 3 of 18 pairs on net, then 15 of 18 in the hold-out, while it spent less time in a trade there in all 18 pairs.
On BTC it is mixed (12 and 5 of 18).

**The plan's other combinations** (PREREG 6.11), each a row described above:

| Combination | Why it is there |
|---|---|
| RIB x F2 / FR / FS / F3 | the video's advice to take the flips in the higher timeframe's direction; study 1's MA200 and TSI lessons |
| RIB x XP / XBE; Heikin Ashi on RIB | the video's partial profit and "manage it" |
| MSD-F4 / F6 on study 1's rules; BOS-trend | the dashboard as context, against your MA200; its structure engine as a system |
| WY x F2; WY-CL and WY-SP (WY-DERIVED) | Wyckoff with the trend; climaxes and springs come far more often than the full entry |
| SP x FD / F2 | the video's "weak buying" warning; pullbacks with the trend |
| SH x F2 / F3 | your MA200 (or the TSI) in place of the script's 1H EMA200 |
| ORB x HV / F2 | the video's volume advice; the trend |
| ORB-CX | gold's own US open: O1 and O5 on the COMEX-open range, 08:20-08:50 New York (08:30-09:00 on M15) |
| TIGHT | Session Hunter's tight-range idea, on O1 and O5: skip days whose opening range is wider than half the average daily range of the last 10 weekdays |
| HP x F2 / FR | harmonic pullbacks with the trend |
| COIL, COIL-RIB | the private script's idea, rebuilt, breaking "with the trend" of the ribbon |

Most are compared with the same row without the addition (a filter or an exit against its plain twin). Four are
compared with the script alone: STK with the ribbon, WY-DERIVED with WY-STD, ORB-CX with the New York range, and
TIGHT with the same rule without it.

**Your MA200 idea.** In study 1 the 4H MA200 improved almost every 1-hour BTC rule in all three periods; on gold the
MA200 filters cost money in most rules in 2019-2022 and helped from 2023. So every script gets them where they fit:

| Filter | What it means | Where it is used |
|---|---|---|
| F1 | longs only above the same chart's MA200, shorts only below | RIB, BOS, COIL-MA; in place of F2 on 1D (WY, WY-DERIVED, HP-HF, HA-ENTRY, STK-RA) |
| F2-4H | the same with the last closed 4H bar | the 1H rows (RIB, WY, WY-DERIVED, SP, HP, HA-ENTRY, STK-RA); ORB and SH |
| F2-1D | the same with the last closed daily bar | RIB on 1H and 4H; the 4H rows of WY, WY-DERIVED, SP, HP, HA-ENTRY and STK-RA; ORB and SH |
| F3 | study 1's TSI (5, 25) above 0 for longs, below 0 for shorts | RIB; SH (the TSI of the last closed 1H bar) |

A higher-timeframe value is always that of the last **closed** bar. On a state rule a filter that turns against the
trade closes it; on an event rule it only decides the entry. Each filtered row is paired with its unfiltered twin.

**What our test found.** Each filtered rule was paired with the same rule without a filter; by the plan's rule a
filter "helps" when it wins more than half of the pairs on net and on P/DD in both Development and Validation. The 4H
MA200 (F2-4H) is the only filter that helps on both markets: it won 36 and 35 of 54 gold pairs on net and 37 and 34 of
50 BTC pairs, and also most hold-out pairs (38 of 54 and 29 of 50). The same chart's MA200 (F1) did not help on gold
(14 and 16 of 46 pairs) and was mixed on BTC (37 of 46 in Development, then only 16 in Validation). The daily MA200
(F2-1D) did not help on gold (25 and 25 of 58) and was mixed on BTC (42 and 26 of 58, then 14 in the hold-out); the
TSI (F3) was mixed on both, and the video's own higher-timeframe filters (FR, FS) were mixed or did not help. Inside
the ribbon's own rows the 4H MA200 helped on BTC (8 and 6 of 8 pairs) but not on gold (4 and 3 of 8), and it did not
rescue the gold ribbon finalist in 2017-2018 (+7 with it, +31 without). Among the five champions with an MA200 filter,
that filter raised the hold-out P/DD in four (the gold ribbon: 4.55 against 2.37); the exception is gold's opening
range (−14 with HV and the 4H MA200, +436 without). Study 1 found the MA200 helped on BTC and was mixed on gold; here
the 4H MA200 helps on both.

## How the test works

- **The data:** Exness ticks, the bots' own source (gold to 25 November 2026, BTC to 26 November), built into UTC bars
  as in study 1; the indicators read the bid. Gold uses its tick volume. BTC's rules that read volume use Binance
  BTCUSDT volume, because Exness's BTC tick volume is a flat heartbeat of about one tick a second. (Two exceptions
  keep Exness tick volume: the Wyckoff control, and the Heikin Ashi rows on study 1's BTC volume-weighted RSI
  finalist, which read it as that finalist did.)
- **Fills and costs:** a decision at a bar's close fills at the next 1-minute open, a buy at the ask and a sell at the
  bid; a stop order (O5, HP-CS) fills when price reaches its level. Stops are checked every minute and pay one extra
  spread; if one minute touches the stop and the target, the stop wins. Every variant also runs with all spreads
  x1.5. One 0.01 lot: gold makes $1 per $1, BTC $0.01 per $1.
- **State and event rules:** a state rule is in while a condition holds (MSD-A1: long while the bias is LEAN BULL or
  better). An event rule enters on a flip, a sweep, a breakout or a pattern, and keeps its own exits. One trade at a
  time (for Session Hunter's presets, one per setup).

| Window | Dates | Use |
|---|---|---|
| Development | 2019-01-01 to 2022-12-31 | every variant; the choice |
| Validation | 2023-01-01 to 2024-06-30 | every variant; the choice |
| Hold-out (exam 1) | 2024-07-01 to the data end | the champions' verdict |
| Early (exam 2, gold only) | 2017-01-01 to 2018-12-31 | the gold champions' second verdict |

The bars before 2019 warm the indicators up (gold from January 2016, BTC from January 2018). Before this study no study
had scored the Early window (it was only warm-up); gold moved sideways in it, between $1,120 and $1,370. A guard in
the code refuses any bar from July 2024 on, and any score in 2017-2018, until `FINALISTS.md` and its sha256 exist. We
knew the hold-out's broad path from study 1's exam (gold's rally and its fall back, BTC's run to about $126k and
back), but no rule of this study had run there before the champions were frozen.

**A variant qualifies** (study 1's four rules) when:

1. its Development net profit is above 0, at normal and at 1.5x costs;
2. it has at least 30 Development trades (15 on the daily);
3. its Development P/DD is at least 1.0, with at least half of its calendar quarters positive;
4. its Validation net profit is above 0.

**Champions, finalists and the exam**

- **Champion:** per symbol and family, the qualifier with the best P/DD over January 2019 to June 2024. A family with
  no qualifier answers "none". The 16 families are those in the last column of "The nine at a glance".
- **Finalists:** per symbol, the three champions with the best P/DD, at most one per script. `FINALISTS.md` is frozen,
  with its sha256, before any hold-out or Early number exists.
- **Exam 1:** a champion passes the hold-out when its net profit is above 0 and its P/DD is at least 0.5. **Exam 2:**
  gold's champions take the same test on 2017-2018.
- **Also:** the same exam on every variant (the base rate; in study 1, 90% of gold's variants would have passed), luck
  checks for the number of variants tried (the deflated Sharpe ratio, White's Reality Check, Hansen's SPA), and
  buy-and-hold, study 1's finalists and the bots' designs side by side.

## What the video also says, which we did not test

- **Other markets:** the opening range on the Nasdaq, the S&P 500 and US stocks; the dashboard's veto on the 5-minute
  chart. Session Hunter's Nasdaq and forex results are checked only for information, on Exness symbols.
- **Options we did not test:** a shorter swing for the Swing Profile on short charts; the opening range's
  Fibonacci targets; Session Hunter's other four confirmations and its automatic preset; Wyckoff's Conservative entry.
- **Display and context:** the ribbon's glow, the Heikin Ashi colours, the opening range's volume profile, the
  dashboard's sessions, kill zones and day, week and month levels, the Swing Profile heat map, the Wyckoff schematic
  and its higher-timeframe scan, and the patterns' reversal zone. Also every tip that needs a level the trader already
  watches: we have no list of your levels.
- **Coil Breakout AI itself:** its A/B/C grade, its other eight filters and its grade-A result in 2025-2026.
- **The other 2027 setups:** the Nasdaq day trader's dashboard, Session Hunter and opening range on the 5-minute
  chart; Wyckoff with the Swing Profile on the daily (too few legs there). And the advice: use three or four tools,
  not nine.

## How the indicators were rebuilt (porting notes)

The full record is `porting/<script>.md`. In short:

- **Two independent ports.** For each script two engineers rewrote the code in Python without seeing each other's
  work. Port A (`backtesting/research/tradeiq2_ind_<key>.py`) is used; port B (`tests/tradeiq2_oracle_<key>.py`)
  checks it. COIL has no source code, so both ports were written from the same written rule.
- **Bit for bit.** On every bar of both symbols up to June 2024 the two agree bit for bit on every output, with no
  tolerance; also on synthetic charts and hand-computed traps. For seven scripts, copies broken on purpose showed that
  the comparison catches every planted misreading that changes a number on our bars. Quick planning ports or probes
  agree too (there is none for COIL).
- **What it found:** errors that cannot occur with the default inputs (the ribbon, Heikin Ashi), the dashboard's last
  weekly bar at a data end, the Swing Profile's limit of 100,000 price bins, and differences of format or contract
  (Wyckoff, the opening range, Session Hunter; in the last two also a first-bar reading that changes nothing on our
  bars). All were settled before any rule ran; the patterns and COIL had none.
- **Pine details that decide numbers:** undocumented tie rules (a handful of 1H events); a standard deviation that
  divides by n, not n − 1; Pine rounding a half upwards (rounding a half to even would move 6 gold 1H and 18 BTC 1H
  Wyckoff climaxes, among others); and where the history starts (Heikin Ashi, Wyckoff, the dashboard's weekly row).
- **What may still differ from TradingView:** TradingView itself was not run. Its gold 4H and daily bars may follow
  the 17:00 New York day (most visible on the dashboard); its statistics use only the bars your plan loads; live bars
  repaint; and our BTC volume is Binance's, so BTC's HV tags and POCs differ from an Exness chart. Where it was
  checked (the ribbon, the coil, Heikin Ashi, Wyckoff's trend score), no value comes within rounding of a threshold,
  so a last-digit difference from TradingView cannot flip a signal there.

## Where to read more

`PREREG.md` (the frozen plan), `DEVIATIONS.md` (every reading; the names in brackets above are its entries),
`DATA.md`, `porting/<script>.md`, and the docstrings of the rule modules,
`backtesting/research/tradeiq2_rules_<key>.py`.
