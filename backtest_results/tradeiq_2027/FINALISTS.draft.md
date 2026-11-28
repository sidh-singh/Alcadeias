# TradeIQ's 9 indicators for 2027: the champions and finalists (DRAFT, not frozen)

Written by `python -B -m backtesting.research.tradeiq2 select` on 28 Nov 2026 14:37 UTC: **a draft**. It is what `freeze` would write now, from the same CSVs; it is not `FINALISTS.md`, nothing is frozen, and the guard stays closed.

The rule (PREREG 7): a variant qualifies when (1) its Development net profit is above 0 at x1.0 and at x1.5 costs, (2) it has at least the minimum of Development trades of PREREG 5 (30 on M5, M15, 1H and 4H; 15 on 1D), (3) its Development profit / max drawdown is at least 1.0 with at least 50% of the quarters positive, and (4) its Validation net profit is above 0 at x1.0; rows marked not eligible or information only never qualify. The champion of a symbol and family is its qualifier with the highest profit / max drawdown over Development + Validation together (one continuous run, 2019-01-01 to 2024-06-30, x1.0); ties go to Development's profit / max drawdown, then to the id. The finalists of a symbol are its three champions with the highest D+V profit / max drawdown, at most one per script (RIB with ALMA-X; MSD-ALONE, MSD-FILTER and BOS; WY with WY-DERIVED; HP-HARMONIC with HP-CHART; HA-ENTRY with HA-MANAGED; every other family on its own), ties as for the champions. They were recomputed from `results_dev_val.csv` by this command and are those of `qualification.csv` and `CANDIDATES.md`.

## The champions and the finalists

The exam (`python -B -m backtesting.research.tradeiq2 exam`) reads its variants from this block, one per line: the role, then the id.

```text
finalist XAUUSDm|1H|RIB|LO|X0|F2-4H
finalist XAUUSDm|1H|COIL|COIL-RIB|X-3R|VOL
finalist XAUUSDm|1H|STK|STK-RA|LO|S1
champion XAUUSDm|4H|HA-MANAGED|M2|RSI-R2-F1-S0
champion XAUUSDm|4H|SP|W2|POC|LO
champion XAUUSDm|1H|MSD-FILTER|MSD-F6|QQE|R2|S0
champion XAUUSDm|1D|HA-ENTRY|HA-H2|LO|F0
champion XAUUSDm|4H|ALMA-X|LO|X0|F0
champion XAUUSDm|1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0
champion XAUUSDm|M5|ORB|O3|HV+F2-4H
champion XAUUSDm|1H|MSD-ALONE|MSD-A2|S0
finalist BTCUSDm|1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1
finalist BTCUSDm|1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1
finalist BTCUSDm|1D|COIL|COIL-RIB|X-3R|none
champion BTCUSDm|4H|BOS|BOS-trend|LO|F1|S1
champion BTCUSDm|4H|SP|W2|POC|F2-1D
champion BTCUSDm|4H|RIB|LS|XBE|F1
```

### Gold (XAUUSDm): 11 champions, 3 finalists (65 qualifiers)

| # | Rank | Role | Family | Script group | Variant | TF | Filter | Stop |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | finalist | RIB | RIB | `XAUUSDm|1H|RIB|LO|X0|F2-4H` | 1H | F2-4H | intended |
| 2 | 2 | finalist | COIL | COIL | `XAUUSDm|1H|COIL|COIL-RIB|X-3R|VOL` | 1H | ribbon | opposite box edge, 0.75-3 ATR(14) |
| 3 | 4 | finalist | STK | STK | `XAUUSDm|1H|STK|STK-RA|LO|S1` | 1H | LO | S1 |
| 4 | 5 | champion | HA-MANAGED | HA | `XAUUSDm|4H|HA-MANAGED|M2|RSI-R2-F1-S0` | 4H | - | - |
| 5 | 12 | champion | SP | SP | `XAUUSDm|4H|SP|W2|POC|LO` | 4H | LO | level-1.5ATR |
| 6 | 24 | champion | MSD-FILTER | MSD | `XAUUSDm|1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | 1H | MSD-F6 | S0 |
| 7 | 36 | champion | HA-ENTRY | HA | `XAUUSDm|1D|HA-ENTRY|HA-H2|LO|F0` | 1D | F0 | none |
| 8 | 44 | champion | ALMA-X | RIB | `XAUUSDm|4H|ALMA-X|LO|X0|F0` | 4H | F0 | intended |
| 9 | 52 | champion | WY-DERIVED | WY | `XAUUSDm|1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | 1H | F0 | S-CL |
| 10 | 55 | champion | ORB | ORB | `XAUUSDm|M5|ORB|O3|HV+F2-4H` | M5 | HV+F2-4H | far side |
| 11 | 64 | champion | MSD-ALONE | MSD | `XAUUSDm|1H|MSD-ALONE|MSD-A2|S0` | 1H | F0 | S0 |

The rule rows:

1. `XAUUSDm|1H|RIB|LO|X0|F2-4H` (finalist; script RIB, family RIB, 1-hour; filter F2-4H, stop intended): The Trend Target Ribbon's flip (slope > 0.08 ATR over 3 bars and the close beyond ALMA -/+ 0.65 dev) on 1H bars of the bid (UTC): a bull flip opens a long, the next bear flip closes it (long only); filled at the open of the next M1 bar; stop riskDist = min(max(close - the lowest low of the 12 bars before, 0.75 ATR), 3 ATR) (a short's mirrored), set from the fill and never moved; exit at the stop or at the close of the next (opposite) flip; filter: longs only while the last closed 4H bar is above its MA200, shorts only while below, checked at the flip's close (it never closes an open trade). Code: tradeiq2_rules_ribbon.py c51009eac6717225277a34e3f3413be4c8c83d05 with the shared files below.
2. `XAUUSDm|1H|COIL|COIL-RIB|X-3R|VOL` (finalist; script COIL, family COIL, 1-hour; filter ribbon, stop opposite box edge, 0.75-3 ATR(14)): Our coil breakout COIL-RIB (PREREG 6.9; TradeIQ's Coil Breakout AI is private) on 1H bars of the bid (UTC): a coil is at least 6 consecutive bars whose Bollinger band (SMA 20 +- 2 population stdev) lies inside the Keltner channel (SMA 20 +- 1.5 ATR 20); its box spans the run's highest high and lowest low; it is armed for 12 bars from the first bar after the run, until a newer coil replaces it; the first close above the box opens a long, below it a short (once per coil), decided at that close and filled at the open of the next M1 bar; trend filter: the Trend Target Ribbon's trend of the same timeframe on the breakout's side at the breakout's close; grade: VOL: the breakout bar's volume is at least 1.5 x its 20-bar average, the bar included (gold tick volume, BTC Binance volume); stop: the distance from the breakout close to the opposite box edge, clamped to 0.75-3 x ATR(14), set from the fill and never moved; all out at 3R (3 x the stop distance from the fill), else the trend trail (the close below the highest close since the entry minus 3 x ATR(14), a short's mirrored) or the stop. One position at a time: a breakout while a trade is open is skipped. Code: tradeiq2_rules_coil.py d0733293c4bca6688ea9df4db28313d25b0b6362 with the shared files below.
3. `XAUUSDm|1H|STK|STK-RA|LO|S1` (finalist; script STK, family STK, 1-hour; filter LO, stop S1): The video's 2027 chart setup STK-RA on 1H bars of the bid (UTC), a state rule: long while the ribbon's trend is up and the higher timeframe's MA200 (F2-4H) agrees, otherwise flat (long only). Stop S1: 3 x ATR(14) from the fill, fixed. An entry where the state changes (also after a stop), at the open of the next M1 bar; the position closes where the state changes. Code: tradeiq2_rules_ribbon.py c51009eac6717225277a34e3f3413be4c8c83d05 with the shared files below.
4. `XAUUSDm|4H|HA-MANAGED|M2|RSI-R2-F1-S0` (champion; script HA, family HA-MANAGED, 4-hour; filter -, stop -): Heikin Ashi management M2: at an INDECISION candle right after 2 or more STRONG candles of a streak of the position's colour, the stop moves to the tighter of break-even (the entry fill) and that bar's low (a short: the lower of the fill and the bar's high), from the next M1 open; a level the price has already crossed there is a market exit; Heikin Ashi (LunqFX, the script's defaults) on the base's 4H bars; a long reacts to bullish candles' events, a short to bearish ones; after a Heikin Ashi exit or a stop the base stays flat until its own state changes. The base (XAUUSDm|4H|RSI|R2|F1|S0): 4-hour bars of the bid (UTC); long while the RSI(14) of the close is above 50, flat while below (long only); filter: a long only while the bar closed above its 200-bar SMA, a short only below it; stop: no stop: exits by the rule only. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).. Code: tradeiq2_rules_ha.py 8863ff0c752e109f306cd3804ae11fb888acd77b with the shared files below.
5. `XAUUSDm|4H|SP|W2|POC|LO` (champion; script SP, family SP, 4-hour; filter LO, stop level-1.5ATR): Swing Profile [BigBeluga] (swing length 50, bins of 0.5 ATR(200)) on 4-hour bars of the bid (tick volume), W2: as W1 (a touch and hold of the forming leg's point of control (POC)), with the stop at the point of control (POC) - 1.5 ATR(14) (shorts +) and the target at 2R; exit at the close of a flip against the trade, else the stop or the target; the first such bar of each anchor that the filter allows, one trade per swing anchor (the leg's swing low for longs, its swing high for shorts); filled at the next M1 open, stop and target as distances from the fill; filter: long only, checked at the entry's close; one position at a time. Code: tradeiq2_rules_swing.py 7f715e2a4e90de72d75fe51f3e89fb428f2c327c with the shared files below.
6. `XAUUSDm|1H|MSD-FILTER|MSD-F6|QQE|R2|S0` (champion; script MSD, family MSD-FILTER, 1-hour; filter MSD-F6, stop S0): 1-hour bars of the bid (UTC); the Market Structure Dashboard's bias on the 1H chart (rows 1H, 4H, D, W; each higher row from its last closed bar, model A). MSD-F6: study 1's QQE R2 state: QQE MOD's colour (BLUE long, RED short, GRAY keeps the side), long only (R2); a long is flat while the 4H, D and W rows all score below 0, a short while they all score above 0 (the video's veto, a state filter). A state rule: in at the close where the state turns, out where it changes; no stop (S0). Decided at the close of a signal bar, filled at the open of the first M1 bar at or after that close (a buy at the ask, a sell at the bid). Code: tradeiq2_rules_msd.py f5b9f1ace19caa734e7ca355ac9114290c7988e6 with the shared files below.
7. `XAUUSDm|1D|HA-ENTRY|HA-H2|LO|F0` (champion; script HA, family HA-ENTRY, daily; filter F0, stop none): Heikin Ashi entry control HA-H2 (LunqFX's candles and phases with the script's defaults) on 1D bars of the bid (UTC), an event rule: long at the close of a Heikin Ashi flip to bullish, out at the close of the next flip to bearish (long only); no filter; no stop. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid). Code: tradeiq2_rules_ha.py 8863ff0c752e109f306cd3804ae11fb888acd77b with the shared files below.
8. `XAUUSDm|4H|ALMA-X|LO|X0|F0` (champion; script RIB, family ALMA-X, 4-hour; filter F0, stop intended): The close crossing the ribbon's ALMA(34, 0.85, 6) (the control of the ribbon's flips: no slope or band condition) on 4H bars of the bid (UTC): a cross up opens a long, the next cross down closes it (long only); filled at the open of the next M1 bar; stop riskDist = min(max(close - the lowest low of the 12 bars before, 0.75 ATR), 3 ATR) (a short's mirrored), set from the fill and never moved; exit at the stop or at the close of the next (opposite) cross; filter: no filter, checked at the cross's close (it never closes an open trade). Code: tradeiq2_rules_ribbon.py c51009eac6717225277a34e3f3413be4c8c83d05 with the shared files below.
9. `XAUUSDm|1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` (champion; script WY, family WY-DERIVED, 1-hour; filter F0, stop S-CL): Wyckoff [theUltimator5] on 1-hour bars of the bid (tick volume): enter on the bar that confirms a selling climax (long) or a buying climax (short) at the next M1 open; stop at the climax extreme -/+ 0.15 ATR(14), fixed; exit at a 2R target or at the close of the 50th bar; no filter; one position at a time. Code: tradeiq2_rules_wyckoff.py a3c8540110a7b2ea0f06be99e2b44e8a8286c5f7 with the shared files below.
10. `XAUUSDm|M5|ORB|O3|HV+F2-4H` (champion; script ORB, family ORB, 5-minute; filter HV+F2-4H, stop far side): LuxAlgo's Ultimate Opening Range Breakout on M5 bars of the bid: the 09:30-10:00 New York range (daylight saving included) on New York weekdays; a market entry at a labelled breakout; target T2 = the range edge + 2 range widths, stop at the far side. Filter: HV and F2-4H together (volume: tick volume). Entries decided by 16:00 New York, everything flat at the last bar close at or before 16:55 New York, one position at a time.. Code: tradeiq2_rules_orb.py f0d0be92db9a3e18606787a9e2f212e79b013ed4 with the shared files below.
11. `XAUUSDm|1H|MSD-ALONE|MSD-A2|S0` (champion; script MSD, family MSD-ALONE, 1-hour; filter F0, stop S0): 1-hour bars of the bid (UTC); the Market Structure Dashboard's bias on the 1H chart (rows 1H, 4H, D, W; each higher row from its last closed bar, model A). MSD-A2: long while the label is LEAN BULL or BULLISH, flat otherwise (long only). A state rule: in at the close where the state turns, out where it changes; no stop (S0). Decided at the close of a signal bar, filled at the open of the first M1 bar at or after that close (a buy at the ask, a sell at the bid). Code: tradeiq2_rules_msd.py f5b9f1ace19caa734e7ca355ac9114290c7988e6 with the shared files below.

Development, 2019-01-01 to 2022-12-31 (per 0.01 lot after costs):

| # | Variant | Net x1.0 | Net x1.5 | Trades | Max DD | Profit / DD | Positive quarters | Win rate | Profit factor | Avg R | Weekly Sharpe (ann.) | Time in market |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|RIB|LO|X0|F2-4H` | +619 | +580 | 207 | 178 | 3.49 | 12/16 | 37% | 1.59 | 0.41 | 1.17 | 26% |
| 2 | `1H|COIL|COIL-RIB|X-3R|VOL` | +367 | +352 | 94 | 94 | 3.89 | 11/16 | 36% | 1.57 | 0.20 | 0.86 | 11% |
| 3 | `1H|STK|STK-RA|LO|S1` | +504 | +450 | 278 | 207 | 2.43 | 10/16 | 33% | 1.36 | 0.22 | 0.89 | 32% |
| 4 | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | +346 | +305 | 235 | 152 | 2.28 | 12/16 | 27% | 1.40 | - | 0.82 | 27% |
| 5 | `4H|SP|W2|POC|LO` | +220 | +175 | 31 | 103 | 2.13 | 11/16 | 45% | 1.85 | 0.32 | 0.63 | 10% |
| 6 | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | +388 | +301 | 592 | 281 | 1.38 | 10/16 | 38% | 1.16 | - | 0.56 | 48% |
| 7 | `1D|HA-ENTRY|HA-H2|LO|F0` | +310 | +291 | 130 | 293 | 1.06 | 9/16 | 41% | 1.26 | - | 0.42 | 54% |
| 8 | `4H|ALMA-X|LO|X0|F0` | +266 | +195 | 458 | 253 | 1.05 | 9/16 | 26% | 1.12 | 0.02 | 0.36 | 53% |
| 9 | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | +145 | +103 | 157 | 117 | 1.24 | 9/16 | 42% | 1.16 | 0.09 | 0.39 | 13% |
| 10 | `M5|ORB|O3|HV+F2-4H` | +126 | +37 | 362 | 101 | 1.24 | 9/16 | 49% | 1.15 | -0.00 | 0.53 | 6% |
| 11 | `1H|MSD-ALONE|MSD-A2|S0` | +456 | +378 | 541 | 261 | 1.75 | 12/16 | 52% | 1.34 | - | 0.66 | 41% |

Validation, 2023-01-01 to 2024-06-30, and Development + Validation as one run:

| # | Variant | Val net x1.0 | Val net x1.5 | Val trades | Val max DD | Val profit / DD | Val positive quarters | D+V net | D+V max DD | D+V profit / DD (the ranking) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|RIB|LO|X0|F2-4H` | +261 | +252 | 83 | 197 | 1.33 | 4/6 | +907 | 197 | 4.6106 |
| 2 | `1H|COIL|COIL-RIB|X-3R|VOL` | +172 | +168 | 43 | 85 | 2.02 | 4/6 | +539 | 131 | 4.1123 |
| 3 | `1H|STK|STK-RA|LO|S1` | +279 | +267 | 105 | 197 | 1.42 | 4/6 | +790 | 207 | 3.8092 |
| 4 | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | +219 | +209 | 81 | 118 | 1.86 | 3/6 | +572 | 152 | 3.7611 |
| 5 | `4H|SP|W2|POC|LO` | +65 | +64 | 11 | 48 | 1.34 | 3/6 | +285 | 103 | 2.7561 |
| 6 | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | +251 | +227 | 222 | 220 | 1.14 | 4/6 | +645 | 281 | 2.2985 |
| 7 | `1D|HA-ENTRY|HA-H2|LO|F0` | +166 | +162 | 41 | 251 | 0.66 | 3/6 | +580 | 293 | 1.9777 |
| 8 | `4H|ALMA-X|LO|X0|F0` | +205 | +188 | 164 | 275 | 0.75 | 4/6 | +494 | 275 | 1.8006 |
| 9 | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | +15 | -14 | 71 | 113 | 0.13 | 3/6 | +160 | 117 | 1.3682 |
| 10 | `M5|ORB|O3|HV+F2-4H` | +6.18 | -6.66 | 108 | 81 | 0.08 | 4/6 | +132 | 101 | 1.3035 |
| 11 | `1H|MSD-ALONE|MSD-A2|S0` | +32 | +1.17 | 285 | 292 | 0.11 | 3/6 | +488 | 521 | 0.9364 |

### BTC (BTCUSDm): 6 champions, 3 finalists (36 qualifiers)

| # | Rank | Role | Family | Script group | Variant | TF | Filter | Stop |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | finalist | HA-MANAGED | HA | `BTCUSDm|1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | 1D | - | - |
| 2 | 2 | finalist | MSD-FILTER | MSD | `BTCUSDm|1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | 1D | MSD-F6 | S1 |
| 3 | 4 | finalist | COIL | COIL | `BTCUSDm|1D|COIL|COIL-RIB|X-3R|none` | 1D | ribbon | opposite box edge, 0.75-3 ATR(14) |
| 4 | 17 | champion | BOS | MSD | `BTCUSDm|4H|BOS|BOS-trend|LO|F1|S1` | 4H | F1 | S1 |
| 5 | 21 | champion | SP | SP | `BTCUSDm|4H|SP|W2|POC|F2-1D` | 4H | F2-1D | level-1.5ATR |
| 6 | 30 | champion | RIB | RIB | `BTCUSDm|4H|RIB|LS|XBE|F1` | 4H | F1 | intended |

The rule rows:

1. `BTCUSDm|1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` (finalist; script HA, family HA-MANAGED, daily; filter -, stop -): Heikin Ashi management HA-AND: the base's entries are taken only when the Heikin Ashi candle of their decision bar has their colour (bullish for a long, bearish for a short); a refused entry is not taken later; the base's exits are its own; Heikin Ashi (LunqFX, the script's defaults) on the base's 1D bars; a long reacts to bullish candles' events, a short to bearish ones; after a Heikin Ashi exit or a stop the base stays flat until its own state changes. The base (BTCUSDm|1D|LaRSI|R2|F3|S1): daily bars of the bid (UTC); long while the 100 x Laguerre RSI (alpha 0.2) of the close is above 50, flat while below (long only); filter: a long only while the TSI (5 / 25) of the bar is above 0, a short only below it; stop: a stop 3 x ATR(14) of the signal timeframe from the entry fill, never moved (one extra spread on a stop fill); after a stop, flat until the state changes. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).. Code: tradeiq2_rules_ha.py 8863ff0c752e109f306cd3804ae11fb888acd77b with the shared files below.
2. `BTCUSDm|1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` (finalist; script MSD, family MSD-FILTER, daily; filter MSD-F6, stop S1): daily bars of the bid (UTC); the Market Structure Dashboard's bias on the 1D chart (rows D, W; each higher row from its last closed bar, model A). MSD-F6: study 1's LaRSI R1 state: 100 x Laguerre RSI (alpha 0.2) (middle 50), both sides (R1); a long is flat while the D and W rows all score below 0, a short while they all score above 0 (the video's veto, a state filter). A state rule: in at the close where the state turns, out where it changes; a fixed stop 3 x ATR(14) of the signal timeframe from the entry fill (study 1's S1), after which the rule stays flat until its state changes. Decided at the close of a signal bar, filled at the open of the first M1 bar at or after that close (a buy at the ask, a sell at the bid). Code: tradeiq2_rules_msd.py f5b9f1ace19caa734e7ca355ac9114290c7988e6 with the shared files below.
3. `BTCUSDm|1D|COIL|COIL-RIB|X-3R|none` (finalist; script COIL, family COIL, daily; filter ribbon, stop opposite box edge, 0.75-3 ATR(14)): Our coil breakout COIL-RIB (PREREG 6.9; TradeIQ's Coil Breakout AI is private) on 1D bars of the bid (UTC): a coil is at least 6 consecutive bars whose Bollinger band (SMA 20 +- 2 population stdev) lies inside the Keltner channel (SMA 20 +- 1.5 ATR 20); its box spans the run's highest high and lowest low; it is armed for 12 bars from the first bar after the run, until a newer coil replaces it; the first close above the box opens a long, below it a short (once per coil), decided at that close and filled at the open of the next M1 bar; trend filter: the Trend Target Ribbon's trend of the same timeframe on the breakout's side at the breakout's close; grade: no grade; stop: the distance from the breakout close to the opposite box edge, clamped to 0.75-3 x ATR(14), set from the fill and never moved; all out at 3R (3 x the stop distance from the fill), else the trend trail (the close below the highest close since the entry minus 3 x ATR(14), a short's mirrored) or the stop. One position at a time: a breakout while a trade is open is skipped. Code: tradeiq2_rules_coil.py d0733293c4bca6688ea9df4db28313d25b0b6362 with the shared files below.
4. `BTCUSDm|4H|BOS|BOS-trend|LO|F1|S1` (champion; script MSD, family BOS, 4-hour; filter F1, stop S1): 4-hour bars of the bid (UTC); the Market Structure Dashboard's structure engine on the 4H row (breaks of structure of its 5 / 5 pivots). BOS-trend: long after a bullish break of structure of the 4H row, flat after a bearish one (long only); filter F1: a long only while the close is above its MA200 (same timeframe). A state rule: in at the close where the state turns, out where it changes; a fixed stop 3 x ATR(14) of the signal timeframe from the entry fill (study 1's S1), after which the rule stays flat until its state changes. Decided at the close of a signal bar, filled at the open of the first M1 bar at or after that close (a buy at the ask, a sell at the bid). Code: tradeiq2_rules_msd.py f5b9f1ace19caa734e7ca355ac9114290c7988e6 with the shared files below.
5. `BTCUSDm|4H|SP|W2|POC|F2-1D` (champion; script SP, family SP, 4-hour; filter F2-1D, stop level-1.5ATR): Swing Profile [BigBeluga] (swing length 50, bins of 0.5 ATR(200)) on 4-hour bars of the bid (Binance BTCUSDT volume), W2: as W1 (a touch and hold of the forming leg's point of control (POC)), with the stop at the point of control (POC) - 1.5 ATR(14) (shorts +) and the target at 2R; exit at the close of a flip against the trade, else the stop or the target; the first such bar of each anchor that the filter allows, one trade per swing anchor (the leg's swing low for longs, its swing high for shorts); filled at the next M1 open, stop and target as distances from the fill; filter: longs only while the last closed 1D bar is above its MA200, shorts only while below, checked at the entry's close; one position at a time. Code: tradeiq2_rules_swing.py 7f715e2a4e90de72d75fe51f3e89fb428f2c327c with the shared files below.
6. `BTCUSDm|4H|RIB|LS|XBE|F1` (champion; script RIB, family RIB, 4-hour; filter F1, stop intended): The Trend Target Ribbon's flip (slope > 0.08 ATR over 3 bars and the close beyond ALMA -/+ 0.65 dev) on 4H bars of the bid (UTC): a bull flip opens a long, a bear flip a short (the opposite flip exits and reverses); filled at the open of the next M1 bar; stop riskDist = min(max(close - the lowest low of the 12 bars before, 0.75 ATR), 3 ATR) (a short's mirrored), set from the fill and never moved; the stop moves to the fill (break-even) once price has gone 1R in favour; else the stop or the next flip; filter: longs only while the close is above the MA200 of the same timeframe, shorts only while below, checked at the flip's close (it never closes an open trade). Code: tradeiq2_rules_ribbon.py c51009eac6717225277a34e3f3413be4c8c83d05 with the shared files below.

Development, 2019-01-01 to 2022-12-31 (per 0.01 lot after costs):

| # | Variant | Net x1.0 | Net x1.5 | Trades | Max DD | Profit / DD | Positive quarters | Win rate | Profit factor | Avg R | Weekly Sharpe (ann.) | Time in market |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | +425 | +419 | 23 | 153 | 2.78 | 9/16 | 43% | 4.73 | 1.74 | 0.74 | 43% |
| 2 | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | +724 | +708 | 72 | 211 | 3.43 | 10/16 | 53% | 2.41 | 0.61 | 0.89 | 89% |
| 3 | `1D|COIL|COIL-RIB|X-3R|none` | +592 | +589 | 18 | 183 | 3.23 | 12/16 | 56% | 4.36 | 0.75 | 0.90 | 43% |
| 4 | `4H|BOS|BOS-trend|LO|F1|S1` | +236 | +213 | 118 | 233 | 1.01 | 8/16 | 26% | 1.38 | 0.51 | 0.40 | 37% |
| 5 | `4H|SP|W2|POC|F2-1D` | +176 | +99 | 38 | 96 | 1.83 | 9/16 | 37% | 2.01 | 0.02 | 0.68 | 11% |
| 6 | `4H|RIB|LS|XBE|F1` | +357 | +320 | 172 | 259 | 1.38 | 9/16 | 28% | 1.34 | 0.29 | 0.54 | 54% |

Validation, 2023-01-01 to 2024-06-30, and Development + Validation as one run:

| # | Variant | Val net x1.0 | Val net x1.5 | Val trades | Val max DD | Val profit / DD | Val positive quarters | D+V net | D+V max DD | D+V profit / DD (the ranking) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | +264 | +262 | 10 | 151 | 1.74 | 3/6 | +689 | 159 | 4.3244 |
| 2 | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | +137 | +134 | 24 | 229 | 0.60 | 4/6 | +857 | 229 | 3.7508 |
| 3 | `1D|COIL|COIL-RIB|X-3R|none` | +25 | +24 | 7 | 139 | 0.18 | 3/6 | +617 | 183 | 3.3679 |
| 4 | `4H|BOS|BOS-trend|LO|F1|S1` | +370 | +363 | 45 | 100 | 3.69 | 4/6 | +607 | 233 | 2.5993 |
| 5 | `4H|SP|W2|POC|F2-1D` | +57 | +56 | 14 | 98 | 0.59 | 2/6 | +233 | 98 | 2.3923 |
| 6 | `4H|RIB|LS|XBE|F1` | +234 | +225 | 57 | 109 | 2.15 | 3/6 | +590 | 284 | 2.0748 |

## The exam (PREREG 7)

Each champion is run over the hold-out (exam 1), Gold (XAUUSDm) 2024-07-01 00:00 to 2026-11-26 UTC (exclusive); BTC (BTCUSDm) 2024-07-01 00:00 to 2026-11-27 UTC (exclusive), and each gold champion also over the Early window (exam 2), 2017-01-01 to 2019-01-01 (exclusive), each as one continuous run that starts flat at its first bar, at x1.0 and x1.5 costs. **A champion passes an exam when its net profit there is above 0 at x1.0 and its profit / max drawdown is at least 0.5.** Gold's verdicts: passes both, passes the hold-out only, passes Early only, fails; BTC's: pass or fail. Then the same exam over every variant, for information (the base rate).

## The selection's inputs and the code

Provenance: the grid was checked against PREREG 6's count table (COUNT_TABLE) and the markets were the store's (tradeiq2_market.load).

The sha256 of the files the champions were read from (`exam` and `accounts` refuse files that differ):

```text
sha256 grid.csv 05a33efadc58f0fac4ce42ef7eb174e326f7b0389506c70b0d71ecbb9bdabbe2
sha256 results_dev_val.csv 199d43931982134b040b40e960aeb1e9adc5eb0ae91d6e2bf7101c544366be62
sha256 qualification.csv 7227f835e472a919fde86bfb45bb61678978e31f031ad9354923f340ae08b2b6
sha256 run_info.csv 11be888e1a6c80bd34f65bf294f62991bcad95d0885b26495fa75dcab4d71be8
sha256 CANDIDATES.md 00c3cb96d5cad25b69be41f979574b1d74c3b740272c55470e18d48e9a2eafc2
```

The environment:

```text
env python 3.10.11
env numpy 1.26.3
env pandas 2.1.4
env numba 0.66.0
```

The code (git blob ids, `git hash-object`):

```text
blob tradeiq2.py 0d2ca9519506940bb8be16446a6dc1682df1be1d
blob tradeiq2_market.py 985bdb991d8069d8728bc2a33531ff3c4a597f13
blob tradeiq2_filters.py 6b148d5bc06920447c91e115f9f556f5361fbb96
blob tradeiq_market.py dc784854b60c0bcb4b01b189b8a7cd5516267b04
blob tradeiq_ind.py 2a6483a415eb50b9b5e067fe899f4922e085ce9f
blob tradeiq.py d0ad7f06a2268eb14d99d78965edc789a3aba125
blob external.py 5f037a44b07e954cd0a857e677914eec42205c90
blob balke.py c7e86b6febce665096f18b1b95cc10711557ed00
blob config.py 5585bf412626c3eb4bbb5aaf04daa55e3b78eaa2
blob store.py 3dda14c5133e1be9af5a4d9c299236bb1b493b92
blob tradeiq2_ind_coil.py 2d734f1864c5313bfc77d399c1abf52dc98572eb
blob tradeiq2_ind_ha.py e9d1844fdbfd5c62d75eb86a525425ce50497b73
blob tradeiq2_ind_msd.py 6dc2ce35e979fd762b8764480fc4a8364b9b4738
blob tradeiq2_ind_orb.py bd506a18fb2661f2fe72f740cbe83cf218fc4d8e
blob tradeiq2_ind_patterns.py a49132d15c8a45d73ce86431df2790c8769b7d99
blob tradeiq2_ind_ribbon.py 100379b349c9d11d5f4a11f094ff1783c1ecaac8
blob tradeiq2_ind_session.py 34a52bfbdf25ec3aba59cc52630c76fe38b047a8
blob tradeiq2_ind_swing.py 8c80fa218caf3a8074c1888f9d24b1048ce4742c
blob tradeiq2_ind_wyckoff.py 78c9b467ab17a9535f04f990c0c961cfefb4fe72
blob tradeiq2_rules_ribbon.py c51009eac6717225277a34e3f3413be4c8c83d05
blob tradeiq2_rules_msd.py f5b9f1ace19caa734e7ca355ac9114290c7988e6
blob tradeiq2_rules_wyckoff.py a3c8540110a7b2ea0f06be99e2b44e8a8286c5f7
blob tradeiq2_rules_swing.py 7f715e2a4e90de72d75fe51f3e89fb428f2c327c
blob tradeiq2_rules_orb.py f0d0be92db9a3e18606787a9e2f212e79b013ed4
blob tradeiq2_rules_session.py 863d1c978503fe87fb5cebd6eaa095d47043667e
blob tradeiq2_rules_patterns.py af576e8fa6ff717d4b9487190d10b16c4dcc0285
blob tradeiq2_rules_ha.py 8863ff0c752e109f306cd3804ae11fb888acd77b
blob tradeiq2_rules_coil.py d0733293c4bca6688ea9df4db28313d25b0b6362
blob silver.py cbc46c58add01afb7eea6dc3737cba3649b87d1b
blob final10.py 5e675ee0774ef6f7a22bca7794571503d3ee4b59
```

| File | Blob id now | Equal to run_info.csv |
|---|---|---|
| tradeiq2.py | `0d2ca9519506940bb8be16446a6dc1682df1be1d` | yes |
| tradeiq2_market.py | `985bdb991d8069d8728bc2a33531ff3c4a597f13` | yes |
| tradeiq2_filters.py | `6b148d5bc06920447c91e115f9f556f5361fbb96` | yes |
| tradeiq_market.py | `dc784854b60c0bcb4b01b189b8a7cd5516267b04` | yes |
| tradeiq_ind.py | `2a6483a415eb50b9b5e067fe899f4922e085ce9f` | yes |
| tradeiq.py | `d0ad7f06a2268eb14d99d78965edc789a3aba125` | yes |
| external.py | `5f037a44b07e954cd0a857e677914eec42205c90` | yes |
| balke.py | `c7e86b6febce665096f18b1b95cc10711557ed00` | yes |
| config.py | `5585bf412626c3eb4bbb5aaf04daa55e3b78eaa2` | yes |
| store.py | `3dda14c5133e1be9af5a4d9c299236bb1b493b92` | yes |
| tradeiq2_ind_coil.py | `2d734f1864c5313bfc77d399c1abf52dc98572eb` | yes |
| tradeiq2_ind_ha.py | `e9d1844fdbfd5c62d75eb86a525425ce50497b73` | yes |
| tradeiq2_ind_msd.py | `6dc2ce35e979fd762b8764480fc4a8364b9b4738` | yes |
| tradeiq2_ind_orb.py | `bd506a18fb2661f2fe72f740cbe83cf218fc4d8e` | yes |
| tradeiq2_ind_patterns.py | `a49132d15c8a45d73ce86431df2790c8769b7d99` | yes |
| tradeiq2_ind_ribbon.py | `100379b349c9d11d5f4a11f094ff1783c1ecaac8` | yes |
| tradeiq2_ind_session.py | `34a52bfbdf25ec3aba59cc52630c76fe38b047a8` | yes |
| tradeiq2_ind_swing.py | `8c80fa218caf3a8074c1888f9d24b1048ce4742c` | yes |
| tradeiq2_ind_wyckoff.py | `78c9b467ab17a9535f04f990c0c961cfefb4fe72` | yes |
| tradeiq2_rules_ribbon.py | `c51009eac6717225277a34e3f3413be4c8c83d05` | yes |
| tradeiq2_rules_msd.py | `f5b9f1ace19caa734e7ca355ac9114290c7988e6` | yes |
| tradeiq2_rules_wyckoff.py | `a3c8540110a7b2ea0f06be99e2b44e8a8286c5f7` | yes |
| tradeiq2_rules_swing.py | `7f715e2a4e90de72d75fe51f3e89fb428f2c327c` | yes |
| tradeiq2_rules_orb.py | `f0d0be92db9a3e18606787a9e2f212e79b013ed4` | yes |
| tradeiq2_rules_session.py | `863d1c978503fe87fb5cebd6eaa095d47043667e` | yes |
| tradeiq2_rules_patterns.py | `af576e8fa6ff717d4b9487190d10b16c4dcc0285` | yes |
| tradeiq2_rules_ha.py | `8863ff0c752e109f306cd3804ae11fb888acd77b` | yes |
| tradeiq2_rules_coil.py | `d0733293c4bca6688ea9df4db28313d25b0b6362` | yes |
| silver.py | `cbc46c58add01afb7eea6dc3737cba3649b87d1b` | yes |
| final10.py | `5e675ee0774ef6f7a22bca7794571503d3ee4b59` | yes |
