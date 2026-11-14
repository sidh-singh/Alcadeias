# Loss-recovery and position-management mechanisms, on identical entries

The live bot averages down with a Fibonacci ladder and has no stop. This report asks what else can be
done with a position that goes wrong, and measures every answer on the **same entries**, so that the
rows of a table differ in the mechanism and in nothing else.

## The answer in short

Forty-two ways of managing a position were run on the same entries, on gold and BTC, in two periods:
DEV (August 2025 to November 2026), where everything was defined, and CONFIRM (February 2024 to June
2025), on which the finished code was then run once. That is 32,553 entries in twelve "cells" (three
entry lists x two symbols x two periods).

1. **No mechanism made the entries worth more.** Each mechanism was compared, entry by entry, with a
   plain comparison row. Of 468 such comparisons, 68 are more than two standard errors on the losing
   side and 9 on the winning side (chance alone gives about eleven each way), and none of the 9
   appears in both periods. What the losers have in common is that they open more units: across
   mechanisms the change in expectancy follows the extra spread paid, with a slope close to -1.
2. **What a mechanism does choose is the shape of the result.** Each has its own win rate, the same
   within a few points on both symbols, all three entry lists and both periods (first table below).
   A higher win rate is paid for with a larger rare loss, not with a better result.
3. **The live ladder is the extreme case.** Without a stop it closed 99.8 to 100 % of baskets at +$1.
   In every one of the twelve cells one basket stood at least $1,358 under water at 0.01 lot (68 % of
   a 2,000 account), in seven of the twelve a single basket emptied the account, and the deepest was
   -$68,514. With a basket stop of $60 or $200 one basket can no longer take the account, and the
   result is negative in 23 of 24 cells (-$0.12 to -$2.55 per entry).
4. **A ladder that does not take more than a fixed amount exists.** Equal lots, at most two adds, a
   hard budget in dollars, no add that does not fit the budget, and no position held while the market
   is closed: of 31,952 baskets none lost more than $60.00, 3 % of a 2,000 account (sixteen lost up to
   $15 more than their own, smaller budget, at trading pauses no calendar knows). **It is not better
   than not adding.** Inside the same budget the single position won more often (83 to 87 % against
   76 to 81 %) and earned the same within noise (the ladder was $0.06 per entry worse on average, and
   $0.28 to $0.37 worse on BTC in 2024-25, where the spread was widest: the spread on its adds).
5. **A hedge lock is a close and a re-entry.** On all 32,510 baskets that ran to their end, opening
   the opposite position at -1 ATR and unlocking it on the next signal paid exactly what closing at
   -1 ATR and re-entering on that signal paid (largest difference 10^-12 USD), while holding two
   positions instead of one. A lock that is simply closed later costs one spread more than the stop
   it replaced: -$0.07 to -$0.18 per entry here, measured to a fraction of a cent.
6. **Zone recovery and doubling after a loss** lose more than anything else that has a stop: zone
   recovery opens 5.5 to 6.9 units per entry and is negative in 19 to 22 of 24 cells (depending on how
   a bar is read), on BTC in all twelve; sizing by the last result multiplies the swings and emptied
   the account in 6 of 12 cells each way.
7. **The entries themselves.** Under the plain 1 ATR trade none of the three lists has an edge. With
   the H1 trend: gold +0.46 ± 0.57 on DEV, -0.08 ± 0.23 on CONFIRM; BTC -0.00 ± 0.12 and -0.39 ± 0.14
   (the spread there was $0.34). The one row that is above zero in all four with-trend cells is the
   wide $20 / $20 exit of V2 (gold +1.20 ± 0.67 and +0.69 ± 0.86, BTC +0.61 ± 0.85 and +1.01 ± 0.69);
   no single cell is beyond two standard errors, so it is encouraging and it is not proof.

Every mechanism over all twelve cells (R = the ATR of the entry hour on 0.01 lot):

<!-- table overview -->
| Mechanism | Win %, lowest to highest | Expectancy per entry in % of the median R, lowest to highest | Expectancy above zero (of 12) | Units opened per entry | Worst basket, Gold / BTC | Worst floating loss, Gold / BTC | $2,000 account emptied (of 12) | of which by one basket |
|---|---|---|---|---|---|---|---|---|
| **Single position, fixed stop and target** |  |  |  |  |  |  |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 46 to 51 | -7.4 to +2.7 | 2 | 1.0 to 1.0 | -121 / -22 | -121 / -22 | 0 | 0 |
| Fixed stop 2 ATR, target 2 ATR | 48 to 53 | -6.8 to +9.2 | 3 | 1.0 to 1.0 | -243 / -45 | -243 / -45 | 0 | 0 |
| Fixed stop 1 ATR, target 2 ATR | 31 to 35 | -5.9 to +2.7 | 4 | 1.0 to 1.0 | -121 / -22 | -121 / -22 | 0 | 0 |
| Fixed stop 2 ATR, target 1 ATR | 64 to 68 | -5.8 to +4.3 | 4 | 1.0 to 1.0 | -243 / -40 | -243 / -40 | 0 | 0 |
| Fixed stop $20, target $20 (the V2 exit) | 48 to 53 | -9.1 to +19.0 | 6 | 1.0 to 1.0 | -51 / -21 | -51 / -21 | 0 | 0 |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |  |  |  |  |  |  |
| Live ladder, no stop | 100 to 100 | -188.9 to +21.4 | 6 | 2.0 to 5.6 | -40,078 / -8,365 | -68,514 / -10,342 | 7 | 7 |
| Live ladder, basket stop $60 | 94 to 98 | -38.0 to -2.5 | 0 | 1.9 to 5.3 | -96 / -63 | -96 / -63 | 7 | 0 |
| Live ladder, basket stop $200 | 98 to 100 | -41.0 to +4.4 | 1 | 1.9 to 5.5 | -241 / -200 | -241 / -200 | 6 | 0 |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |  |  |  |  |  |  |
| Budget 1 R, no add | 61 to 67 | -8.8 to +1.2 | 1 | 1.0 to 1.0 | -121 / -22 | -121 / -22 | 0 | 0 |
| Budget 1 R, 2 adds 0.17 ATR apart | 45 to 54 | -15.0 to +1.6 | 2 | 2.3 to 2.4 | -121 / -22 | -121 / -22 | 3 | 0 |
| Budget 2 R, no add | 77 to 81 | -6.1 to +2.5 | 1 | 1.0 to 1.0 | -243 / -39 | -243 / -39 | 0 | 0 |
| Budget 2 R, 2 adds 0.33 ATR apart | 65 to 72 | -17.9 to +0.0 | 1 | 2.0 to 2.1 | -243 / -45 | -243 / -45 | 2 | 0 |
| Budget 3 R, no add | 83 to 87 | -9.7 to +2.8 | 2 | 1.0 to 1.0 | -364 / -58 | -364 / -58 | 0 | 0 |
| Budget 3 R, 1 add 1 ATR apart | 80 to 84 | -11.1 to +2.7 | 1 | 1.3 to 1.4 | -364 / -58 | -364 / -58 | 0 | 0 |
| Budget 3 R, 2 adds 0.5 ATR apart | 76 to 81 | -12.2 to +2.8 | 3 | 1.8 to 1.9 | -364 / -67 | -364 / -67 | 1 | 0 |
| Budget 3 R, 3 adds 0.3 ATR apart | 70 to 76 | -21.9 to +1.6 | 1 | 2.4 to 2.5 | -364 / -67 | -364 / -67 | 3 | 0 |
| Budget 3 R, 4 adds 0.2 ATR apart | 67 to 73 | -24.5 to +0.9 | 3 | 3.0 to 3.2 | -364 / -67 | -364 / -67 | 6 | 0 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 76 to 80 | -12.1 to +1.6 | 2 | 1.8 to 1.9 | -222 / -60 | -222 / -60 | 1 | 0 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 76 to 80 | -12.1 to +2.3 | 2 | 1.8 to 1.9 | -119 / -60 | -119 / -60 | 1 | 0 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 75 to 80 | -12.1 to +1.3 | 2 | 1.7 to 1.9 | -60 / -60 | -60 / -60 | 1 | 0 |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |  |  |  |  |  |  |
| Add when the M5 MACD histogram turns | 79 to 84 | -11.2 to +3.0 | 2 | 1.4 to 1.5 | -364 / -56 | -364 / -64 | 1 | 0 |
| Add when the M15 MACD histogram turns | 81 to 85 | -8.9 to +6.5 | 1 | 1.3 to 1.3 | -364 / -56 | -364 / -61 | 0 | 0 |
| Add when the M5 RSI comes back through 35 / 65 | 81 to 85 | -10.3 to +5.5 | 2 | 1.3 to 1.3 | -364 / -58 | -364 / -64 | 0 | 0 |
| Add when the M15 RSI comes back through 35 / 65 | 82 to 86 | -8.7 to +5.5 | 2 | 1.1 to 1.2 | -364 / -58 | -364 / -59 | 0 | 0 |
| **Stops that follow the price (single position)** |  |  |  |  |  |  |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 30 to 34 | -9.8 to +2.0 | 1 | 1.0 to 1.0 | -121 / -22 | -121 / -22 | 0 | 0 |
| Break-even at +1 ATR (stop 1, target 2) | 23 to 26 | -8.1 to +3.0 | 3 | 1.0 to 1.0 | -121 / -22 | -121 / -22 | 0 | 0 |
| Trailing stop 1 ATR, no target | 34 to 38 | -9.1 to +3.8 | 3 | 1.0 to 1.0 | -120 / -18 | -120 / -18 | 1 | 0 |
| Trailing stop 2 ATR, no target | 35 to 39 | -6.5 to +6.3 | 8 | 1.0 to 1.0 | -241 / -38 | -241 / -39 | 0 | 0 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 46 to 51 | -7.7 to +4.7 | 2 | 1.0 to 1.0 | -121 / -22 | -121 / -22 | 0 | 0 |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |  |  |  |  |  |  |
| Pyramid, 2 adds | 20 to 24 | -14.5 to +6.9 | 4 | 1.5 to 1.5 | -120 / -20 | -120 / -20 | 2 | 0 |
| Pyramid, 4 adds | 20 to 24 | -15.4 to +7.9 | 2 | 1.6 to 1.6 | -120 / -20 | -120 / -20 | 2 | 0 |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |  |  |  |  |  |  |
| Hedge lock, unlocked by the next vote signal | 60 to 63 | -11.3 to +4.0 | 2 | 1.5 to 1.5 | -243 / -43 | -243 / -43 | 0 | 0 |
| Close at -1 ATR, re-enter on the next vote signal | 60 to 63 | -11.3 to +4.0 | 2 | 1.5 to 1.5 | -243 / -43 | -243 / -43 | 0 | 0 |
| Hedge lock, both legs closed 4 h later | 46 to 51 | -10.9 to +2.0 | 2 | 1.5 to 1.5 | -122 / -23 | -122 / -23 | 0 | 0 |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |  |  |  |  |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 90 to 94 | -50.1 to +6.2 | 2 | 5.5 to 6.3 | -1,502 / -247 | -1,502 / -258 | 7 | 0 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 73 to 78 | -51.6 to -10.4 | 0 | 6.1 to 6.9 | -501 / -83 | -501 / -90 | 9 | 0 |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |  |  |  |  |  |  |
| Stop and reverse, same size | 46 to 51 | -12.8 to +1.2 | 3 | 1.5 to 1.5 | -243 / -45 | -243 / -45 | 0 | 0 |
| Stop and reverse, double size | 71 to 75 | -18.4 to +3.8 | 3 | 2.0 to 2.1 | -364 / -67 | -364 / -67 | 1 | 0 |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |  |  |  |  |  |  |
| Martingale: double after a loss, up to x8 | 46 to 51 | -23.7 to +22.2 | 3 | 2.3 to 2.8 | -971 / -180 | -971 / -180 | 6 | 0 |
| Anti-martingale: double after a win, up to x8 | 46 to 51 | -19.1 to +3.9 | 4 | 2.3 to 2.5 | -915 / -155 | -915 / -155 | 6 | 0 |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |  |  |  |  |  |  |
| Daily loss limit 1 R | 45 to 51 | -10.7 to +3.1 | 2 | 1.0 to 1.0 | -121 / -20 | -121 / -20 | 0 | 0 |
| Daily loss limit 2 R | 46 to 51 | -8.3 to +0.9 | 3 | 1.0 to 1.0 | -121 / -22 | -121 / -22 | 0 | 0 |
<!-- /table -->

## How it was measured

**Entries.** Three fixed lists per symbol, each made at the close of an M15 bar:

| List | An entry is made when |
|---|---|
| with the H1 trend | the bot's RSI vote and MACD vote on M15 agree, and that direction is the H1 trend (sign of the MACD(12,26,9) signal line of the last closed H1 bar) |
| votes only | the two votes agree, no trend filter |
| random | a coin flip says "enter" (probability one half at each M15 close) and a second coin flip picks the direction; fixed seed. This list has no edge by construction |

"No basket is open" has to mean the same for every mechanism, otherwise they would not see the same
entries. It is read off the reference trade (stop 1 ATR, target 1 ATR): the next entry is the first
signal after the reference trade of the previous entry has closed. Every mechanism is then applied to
every entry of the list, each basket on its own.

**Simulator** (`backtesting/research/recovery.py`). M1 bid bars; a buy pays the ask (bid + the bar's
mean spread), a sell gets the bid; P/L = price difference x units x USD per 1.00 of price (0.01 lot:
1.00 for gold, 0.01 for BTC). Inside a bar the price is taken to run open, unfavourable extreme,
favourable extreme, close, so a stop is met before a target of the same bar; a level the open has
already passed is filled at the open, so gaps over the daily break and the weekend are in the results.
Indicator rules (ladder tiers, signal adds, the unlock of a hedge) act at the close of an M1 bar.
Everything used at a close comes from bars that had closed by then; the tests prove it by cutting the
history at arbitrary bars and by replacing the future with nonsense.

**Units.** Distances are multiples of the H1 ATR(14) of the last closed H1 bar at the entry. **R** is
the value of one such ATR on 0.01 lot: on gold a median of $17.41 on DEV and $6.61 on CONFIRM (up to
$126 in the wildest hour), on BTC $4.67 and $5.31 (up to $22). All money is USD for a base size of
0.01 lot. As a share of a 2,000 account at 0.01 lot, budgets of 1 R, 2 R and 3 R were 0.9 %, 1.7 % and
2.6 % at the median on gold in DEV (0.3 %, 0.7 % and 1.0 % in CONFIRM) and 0.2 % to 0.8 % on BTC; a
budget of $60 is 3 %.

**Columns.** *Expectancy per entry* is the mean result of a basket, after spread; the standard error
after ± treats entries of the same calendar week as one cluster, because overlapping baskets are not
independent. *Worst floating loss* is the lowest a basket stood before it was closed. The *$2,000
account* columns replay the list in time order on 2,000 USD at 0.01 lot, one basket at a time (an
entry that arrives while the mechanism's previous basket is still open is skipped, as the bot would);
drawdown is from the highest closed balance to the lowest equity. An account can be *emptied* in two
ways, and the tables say which: by one basket (the last basket alone lost at least half of the
starting 2,000), or by many losses (at 0.01 lot a 2,000 account does not survive a few thousand
entries that each lose the spread and more).

**Periods and protocol.** DEV is 2025-07-01 to 2026-11-12, CONFIRM 2024-01-01 to 2025-06-30. The
first month of each only warms the indicators up, so entries run from 1 August 2025 and from
1 February 2024. A basket still open when its period ends is closed at the last bar. No bar before
2024 was read. Every definition and number in the code was fixed on DEV and committed before the
CONFIRM months were complete in the tick store and before any of them was read; CONFIRM was then run
once. Afterwards two descriptive columns
were added (what emptied an account; how many baskets lost more than their budget) and the files were
written again from scratch; every earlier figure came out the same.

**How many variants.** 42 mechanisms; 40 were fixed before the first run, and two (the ladder that is
flat over the weekend, and over every closure) were added after the first DEV run showed weekend gaps
going through the stop. None was tuned: stops, targets and spacings are round numbers. Nothing was
selected, so every row is reported. Besides these, every row was run again under two other readings
of the order inside a bar, and the reference trade under four other random seeds on DEV; both checks
are reported under "How far to trust this".

## The mechanisms

<!-- table design -->
| Mechanism | Largest position (x 0.01 lot) | Worst loss of one basket by design |
|---|---|---|
| **Single position, fixed stop and target** |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 1 | 1 R |
| Fixed stop 2 ATR, target 2 ATR | 1 | 2 R |
| Fixed stop 1 ATR, target 2 ATR | 1 | 1 R |
| Fixed stop 2 ATR, target 1 ATR | 1 | 2 R |
| Fixed stop $20, target $20 (the V2 exit) | 1 | $20 |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |
| Live ladder, no stop | 32 | no limit |
| Live ladder, basket stop $60 | 32 | $60 |
| Live ladder, basket stop $200 | 32 | $200 |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |
| Budget 1 R, no add | 1 | 1 R |
| Budget 1 R, 2 adds 0.17 ATR apart | 3 | 1 R |
| Budget 2 R, no add | 1 | 2 R |
| Budget 2 R, 2 adds 0.33 ATR apart | 3 | 2 R |
| Budget 3 R, no add | 1 | 3 R |
| Budget 3 R, 1 add 1 ATR apart | 2 | 3 R |
| Budget 3 R, 2 adds 0.5 ATR apart | 3 | 3 R |
| Budget 3 R, 3 adds 0.3 ATR apart | 4 | 3 R |
| Budget 3 R, 4 adds 0.2 ATR apart | 5 | 3 R |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 3 | 3 R, at most $60 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 3 | 3 R, at most $60 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 3 | 3 R, at most $60 |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |
| Add when the M5 MACD histogram turns | 3 | 3 R |
| Add when the M15 MACD histogram turns | 3 | 3 R |
| Add when the M5 RSI comes back through 35 / 65 | 3 | 3 R |
| Add when the M15 RSI comes back through 35 / 65 | 3 | 3 R |
| **Stops that follow the price (single position)** |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 1 | 1 R |
| Break-even at +1 ATR (stop 1, target 2) | 1 | 1 R |
| Trailing stop 1 ATR, no target | 1 | 1 R |
| Trailing stop 2 ATR, no target | 1 | 2 R |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 1 | 1 R |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |
| Pyramid, 2 adds | 3 | 1 R |
| Pyramid, 4 adds | 5 | 1 R |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |
| Hedge lock, unlocked by the next vote signal | 2 (1 long + 1 short) | 2 R + spreads |
| Close at -1 ATR, re-enter on the next vote signal | 1 | 2 R + spreads |
| Hedge lock, both legs closed 4 h later | 2 (1 long + 1 short) | 1 R + 1 spread |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 22 (both sides) | 15 R + spreads |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 12.9 (both sides) | 4.06 R + spreads |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |
| Stop and reverse, same size | 1 | 2 R |
| Stop and reverse, double size | 2 | 3 R |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |
| Martingale: double after a loss, up to x8 | 8 | 8 R (15 R over four losses) |
| Anti-martingale: double after a win, up to x8 | 8 | 8 R |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |
| Daily loss limit 1 R | 1 | 1 R a basket, about 1 R a day |
| Daily loss limit 2 R | 1 | 1 R a basket, about 2 R a day |
<!-- /table -->

What each one does, when it helps and how it fails:

- **Fixed stop and target** (the reference). One position, closed at a fixed loss or a fixed profit.
  *Helps:* the loss of a basket is known before it is opened, so size can be set from it. *Fails:* it
  does nothing for direction; a gap can still fill beyond the stop. The ratio of stop to target sets
  the win rate (a stop twice as far as the target wins about two times in three), not the expectancy.
- **The live ladder.** Up to five adds of 2, 3, 5, 8 and 13 units while RSI(14) of M1, M5, M15, H1, H4
  is beyond 35 / 65; the whole basket is closed at +1 USD. This is the ladder alone: the bot's
  force-close on the M15 slope score is not part of it. *Helps:* after every add a smaller bounce is
  enough, so nearly every basket ends at +1 USD. *Fails:* the position is largest exactly when the
  market is running against it, and without a stop one basket that does not bounce takes the account.
- **Averaging down inside a fixed budget.** Equal lots at price levels fixed at the entry, at most
  four adds, target 0.5 ATR above the average entry, and a hard stop on the basket's total loss: the
  budget. The spacing is derived from the budget, so that the stop sits one more step beyond the last
  add and the full basket then loses exactly the budget; an add the budget cannot carry is not made.
  *Helps:* it keeps what a ladder is good for (a better average entry, so a smaller bounce closes the
  basket in profit) while the worst case is fixed before the first order. *Fails:* for the same budget
  the stop is nearer than that of a single position, because the adds have used the room.
- **Averaging down released by a signal.** The same budget and target, but an add is made only when the
  price is at least 0.5 ATR beyond the last fill *and* an event says the move may be turning: the MACD
  histogram of M5 or M15 turns back in the basket's favour, or RSI(14) of M5 or M15 comes back through
  35 / 65. An event, not a state: "RSI is below 35" is true all the way down, "RSI came back above 35"
  happens once. *Helps:* fewer adds into a straight move. *Fails:* a turn signal is often only a pause,
  and a sharp reversal can leave the basket without any add.
- **Break-even stop.** After a favourable move the stop goes to the price paid. *Helps:* a trade that
  was ahead cannot become a loss. *Fails:* ordinary pull-backs close trades at zero that would have
  reached the target.
- **Trailing stop.** The stop follows the best price at a fixed distance; there is no target. *Helps:*
  it lets a trend run. *Fails:* it gives back one trail from every peak and is stopped again and again
  in a range.
- **Scale-out.** Half is closed at +1 ATR, the stop of the rest goes to the price paid and then trails.
  *Helps:* something is banked while exposure remains. *Fails:* half of every runner was sold early.
  It needs 0.02 lot as the base size.
- **Averaging up (pyramiding).** An equal add every 1 ATR in profit, trailing stop on the whole basket.
  The mirror image of the ladder: the position is largest when the trade is right. *Helps:* the worst
  case stays 1 R however many adds there are. *Fails:* few winners (one basket in five), and a
  reversal just after an add gives the open profit back.
- **Hedge lock.** At the stop level the opposite position is opened instead of closing. From then on
  the result is frozen. *Helps:* nothing that closing would not do. *Fails:* to end the lock one leg
  has to be closed, which is a fresh entry at that moment; closing both legs together costs one spread
  more than a plain stop.
- **Zone recovery.** When the first position is down by the zone, a larger opposite position is
  opened; if the price comes back, a still larger one in the first direction; and so on until one
  side's target is reached. *Helps:* it wins from either side as long as the price leaves the zone
  before the legs run out. *Fails:* a market that crosses the zone back and forth makes the position
  grow 1, 3, 6, 12, and the loss when no leg is left is many times the first risk.
- **Stop and reverse.** At the stop the position is closed and the opposite one opened, once. *Helps:*
  if moves that take out a stop tend to continue. *Fails:* in a range it is stopped twice.
- **Martingale and anti-martingale sizing.** The next basket is doubled after a loss (martingale) or
  after a win (anti-martingale). A size chosen from past results multiplies whatever expectancy the
  entries have by the average size and widens the swings.
- **Daily loss limit.** No new basket for the rest of the UTC day once the day has lost that much.
  *Helps:* it bounds what one bad day can cost. *Fails:* it does not change what a basket is worth.

## Results, one table per entry list

Every cell holds the DEV value, a slash, and the CONFIRM value. First a few rows of each family for the
entries with the H1 trend, both symbols side by side; the full tables follow.

<!-- table summary:trend -->
| Mechanism | Gold: expectancy per entry (± s.e.) | Gold: win % | Gold: worst basket | Gold: worst floating loss | Gold: $2,000 account emptied | BTC: expectancy per entry (± s.e.) | BTC: win % | BTC: worst basket | BTC: worst floating loss | BTC: $2,000 account emptied |
|---|---|---|---|---|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | +0.46 / -0.08 (± 0.57 / 0.23) | 51 / 50 | -121 / -44 | -121 / -44 | no / no | -0.00 / -0.39 (± 0.12 / 0.14) | 50 / 46 | -17 / -22 | -17 / -22 | no / no |
| Fixed stop $20, target $20 (the V2 exit) | +1.20 / +0.69 (± 0.67 / 0.86) | 53 / 52 | -37 / -44 | -37 / -44 | no / no | +0.61 / +1.01 (± 0.85 / 0.69) | 52 / 52 | -20 / -21 | -20 / -21 | no / no |
| Live ladder, no stop | +1.00 / +1.00 (± 0.00 / 0.00) | 100 / 100 | +1 / +1 | -30,176 / -1,606 | one basket / no | +1.00 / +0.72 (± 0.00 / 0.28) | 100 / 100 | -1 / -578 | -1,806 / -1,745 | no / no |
| Live ladder, basket stop $200 | -0.15 / -0.47 (± 0.39 / 0.46) | 99 / 99 | -241 / -200 | -241 / -200 | no / no | -0.12 / -2.18 (± 0.34 / 0.57) | 99 / 98 | -200 / -200 | -200 / -200 | no / many losses |
| Budget 3 R, no add | +0.49 / -0.23 (± 1.09 / 0.40) | 87 / 85 | -364 / -92 | -364 / -92 | no / no | +0.01 / -0.27 (± 0.17 / 0.19) | 86 / 83 | -46 / -55 | -46 / -55 | no / no |
| Budget 3 R, 2 adds 0.5 ATR apart | +0.48 / -0.43 (± 1.24 / 0.53) | 81 / 79 | -364 / -76 | -364 / -79 | no / no | -0.07 / -0.65 (± 0.22 / 0.23) | 80 / 76 | -44 / -67 | -44 / -67 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | +0.22 / -0.61 (± 0.77 / 0.47) | 77 / 76 | -60 / -60 | -60 / -60 | no / no | -0.07 / -0.64 (± 0.22 / 0.23) | 80 / 76 | -44 / -60 | -44 / -60 | no / no |
| Add when the M15 RSI comes back through 35 / 65 | +0.95 / -0.25 (± 1.16 / 0.33) | 86 / 84 | -364 / -64 | -364 / -66 | no / no | -0.17 / -0.35 (± 0.18 / 0.20) | 84 / 82 | -46 / -55 | -46 / -59 | no / no |
| Trailing stop 1 ATR, no target | +0.67 / -0.21 (± 0.90 / 0.29) | 38 / 37 | -99 / -44 | -99 / -44 | no / no | -0.02 / -0.44 (± 0.16 / 0.17) | 37 / 34 | -14 / -18 | -14 / -18 | no / no |
| Pyramid, 2 adds | +1.21 / -0.63 (± 1.51 / 0.45) | 24 / 22 | -99 / -44 | -99 / -44 | no / no | +0.01 / -0.64 (± 0.29 / 0.27) | 22 / 20 | -15 / -18 | -15 / -18 | no / no |
| Hedge lock, unlocked by the next vote signal | +0.69 / -0.06 (± 0.67 / 0.38) | 61 / 63 | -218 / -70 | -218 / -70 | no / no | +0.03 / -0.40 (± 0.15 / 0.16) | 61 / 60 | -30 / -43 | -30 / -43 | no / no |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.80 / -0.81 (± 1.24 / 0.42) | 78 / 78 | -370 / -130 | -393 / -130 | no / no | -1.24 / -2.74 (± 0.27 / 0.36) | 77 / 73 | -78 / -83 | -78 / -90 | no / many losses |
| Martingale: double after a loss, up to x8 | +3.86 / -0.24 (± 1.38 / 1.00) | 51 / 50 | -517 / -352 | -517 / -352 | no / no | +0.00 / -0.74 (± 0.42 / 0.47) | 50 / 46 | -121 / -161 | -121 / -161 | no / many losses |
| Daily loss limit 2 R | -0.06 / -0.20 (± 0.68 / 0.22) | 49 / 49 | -121 / -27 | -121 / -27 | no / no | +0.04 / -0.44 (± 0.12 / 0.16) | 51 / 46 | -17 / -20 | -17 / -20 | no / no |
<!-- /table -->

### Gold, entries with the H1 trend

<!-- table main:XAUUSDm:trend -->
Entries: 1,437 / 1,643. One R (the ATR of the entry hour on 0.01 lot): median $17.41 / $6.61, 95th percentile $37.41 / $14.76, largest $121.43 / $26.87. Every cell is DEV / CONFIRM; amounts in USD for a base size of 0.01 lot; position in units of 0.01 lot.

| Mechanism | Baskets | Expectancy per entry (± s.e.) | Win % | Worst basket | 1st percentile | Largest position held | Worst floating loss | $2,000 account: result | deepest drawdown | emptied |
|---|---|---|---|---|---|---|---|---|---|---|
| **Single position, fixed stop and target** |  |  |  |  |  |  |  |  |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 1,437 / 1,643 | +0.46 / -0.08 (± 0.57 / 0.23) | 51 / 50 | -121 / -44.0 | -60.8 / -18.7 | 1 / 1 | -121 / -44.0 | +666 / -139 | 636 / 427 | no / no |
| Fixed stop 2 ATR, target 2 ATR | 1,437 / 1,643 | -0.99 / -0.12 (± 2.44 / 0.57) | 50 / 49 | -243 / -59.2 | -129 / -35.3 | 1 / 1 | -243 / -59.2 | +111 / -21 | 1,217 / 451 | no / no |
| Fixed stop 1 ATR, target 2 ATR | 1,437 / 1,643 | +0.32 / -0.13 (± 1.46 / 0.33) | 35 / 33 | -121 / -44.0 | -76.6 / -18.9 | 1 / 1 | -121 / -44.0 | +393 / +101 | 982 / 413 | no / no |
| Fixed stop 2 ATR, target 1 ATR | 1,437 / 1,643 | +0.42 / +0.01 (± 1.04 / 0.44) | 68 / 66 | -243 / -59.2 | -104 / -31.1 | 1 / 1 | -243 / -59.2 | +559 / +62 | 798 / 380 | no / no |
| Fixed stop $20, target $20 (the V2 exit) | 1,437 / 1,643 | +1.20 / +0.69 (± 0.67 / 0.86) | 53 / 52 | -37.1 / -44.0 | -20.0 / -20.0 | 1 / 1 | -37.1 / -44.0 | +1,475 / +354 | 501 / 418 | no / no |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |  |  |  |  |  |  |  |  |
| Live ladder, no stop | 1,437 / 1,643 | +1.00 / +1.00 (± 0.00 / 0.00) | 100 / 100 | +1.0 / +1.0 | +1.0 / +1.0 | 32 / 32 | -30,176 / -1,606 | -2,000 / +1,504 | 2,521 / 1,606 | 2026-01-16, one basket / no |
| Live ladder, basket stop $60 | 1,437 / 1,643 | -0.44 / -0.28 (± 0.24 / 0.23) | 98 / 98 | -60.0 / -90.8 | -60.0 / -60.0 | 32 / 32 | -60.0 / -90.8 | -646 / -445 | 703 / 528 | no / no |
| Live ladder, basket stop $200 | 1,437 / 1,643 | -0.15 / -0.47 (± 0.39 / 0.46) | 99 / 99 | -241 / -200 | +1.0 / +1.0 | 32 / 32 | -241 / -200 | -231 / -632 | 854 / 1,118 | no / no |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |  |  |  |  |  |  |  |  |
| Budget 1 R, no add | 1,437 / 1,643 | +0.21 / -0.25 (± 0.45 / 0.18) | 67 / 65 | -121 / -44.0 | -52.2 / -17.1 | 1 / 1 | -121 / -44.0 | +301 / -405 | 554 / 490 | no / no |
| Budget 1 R, 2 adds 0.17 ATR apart | 1,437 / 1,643 | +0.28 / -0.54 (± 0.57 / 0.22) | 54 / 51 | -121 / -28.4 | -63.6 / -18.5 | 3 / 3 | -121 / -28.4 | +404 / -883 | 854 / 1,026 | no / no |
| Budget 2 R, no add | 1,437 / 1,643 | +0.44 / -0.14 (± 0.87 / 0.31) | 81 / 79 | -243 / -47.4 | -73.5 / -30.3 | 1 / 1 | -243 / -47.4 | +160 / -159 | 863 / 355 | no / no |
| Budget 2 R, 2 adds 0.33 ATR apart | 1,437 / 1,643 | -0.09 / -0.56 (± 0.87 / 0.34) | 72 / 70 | -243 / -80.1 | -104 / -33.8 | 3 / 3 | -243 / -80.1 | -127 / -924 | 1,084 / 1,039 | no / no |
| Budget 3 R, no add | 1,437 / 1,643 | +0.49 / -0.23 (± 1.09 / 0.40) | 87 / 85 | -364 / -91.6 | -96.5 / -44.7 | 1 / 1 | -364 / -91.6 | +631 / -20 | 587 / 273 | no / no |
| Budget 3 R, 1 add 1 ATR apart | 1,437 / 1,643 | +0.46 / -0.47 (± 1.13 / 0.48) | 84 / 82 | -364 / -71.2 | -99.4 / -45.5 | 2 / 2 | -364 / -71.2 | +350 / -561 | 969 / 762 | no / no |
| Budget 3 R, 2 adds 0.5 ATR apart | 1,437 / 1,643 | +0.48 / -0.43 (± 1.24 / 0.53) | 81 / 79 | -364 / -76.1 | -110 / -48.4 | 3 / 3 | -364 / -78.7 | +564 / -392 | 933 / 681 | no / no |
| Budget 3 R, 3 adds 0.3 ATR apart | 1,437 / 1,643 | -0.91 / -0.59 (± 1.24 / 0.56) | 76 / 75 | -364 / -111 | -153 / -48.4 | 4 / 4 | -364 / -111 | -1,243 / -919 | 2,030 / 1,002 | no / no |
| Budget 3 R, 4 adds 0.2 ATR apart | 1,437 / 1,643 | +0.16 / -1.01 (± 1.24 / 0.54) | 73 / 71 | -364 / -147 | -153 / -50.6 | 5 / 5 | -364 / -147 | +228 / -1,654 | 1,787 / 1,790 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,437 / 1,643 | +0.27 / -0.53 (± 0.79 / 0.55) | 79 / 79 | -60.0 / -76.1 | -60.0 / -50.5 | 3 / 3 | -60.0 / -76.1 | +295 / -570 | 821 / 767 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 1,404 / 1,618 | +0.40 / -0.57 (± 0.80 / 0.56) | 79 / 79 | -60.0 / -76.1 | -60.0 / -50.8 | 3 / 3 | -60.0 / -76.1 | +404 / -605 | 973 / 776 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 1,353 / 1,580 | +0.22 / -0.61 (± 0.77 / 0.47) | 77 / 76 | -60.0 / -60.0 | -60.0 / -48.4 | 3 / 3 | -60.0 / -60.0 | +94 / -694 | 980 / 886 | no / no |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |  |  |  |  |  |  |  |  |
| Add when the M5 MACD histogram turns | 1,437 / 1,643 | +0.51 / -0.40 (± 1.14 / 0.41) | 84 / 82 | -364 / -71.2 | -99.4 / -46.2 | 3 / 3 | -364 / -71.2 | +150 / -395 | 1,132 / 721 | no / no |
| Add when the M15 MACD histogram turns | 1,437 / 1,643 | +1.12 / -0.20 (± 1.12 / 0.37) | 85 / 83 | -364 / -70.5 | -102 / -45.3 | 3 / 3 | -364 / -70.5 | +621 / -219 | 1,201 / 516 | no / no |
| Add when the M5 RSI comes back through 35 / 65 | 1,437 / 1,643 | +0.95 / -0.38 (± 1.15 / 0.39) | 85 / 82 | -364 / -63.7 | -96.8 / -45.3 | 3 / 3 | -364 / -65.7 | +993 / -558 | 1,058 / 656 | no / no |
| Add when the M15 RSI comes back through 35 / 65 | 1,437 / 1,643 | +0.95 / -0.25 (± 1.16 / 0.33) | 86 / 84 | -364 / -63.7 | -95.6 / -44.7 | 3 / 3 | -364 / -65.7 | +863 / -262 | 1,031 / 453 | no / no |
| **Stops that follow the price (single position)** |  |  |  |  |  |  |  |  |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 1,437 / 1,643 | +0.35 / -0.22 (± 0.56 / 0.22) | 34 / 32 | -121 / -44.0 | -52.2 / -17.1 | 1 / 1 | -121 / -44.0 | +503 / -354 | 800 / 539 | no / no |
| Break-even at +1 ATR (stop 1, target 2) | 1,437 / 1,643 | +0.07 / -0.14 (± 0.93 / 0.28) | 26 / 24 | -121 / -44.0 | -60.8 / -18.7 | 1 / 1 | -121 / -44.0 | +231 / +15 | 693 / 402 | no / no |
| Trailing stop 1 ATR, no target | 1,437 / 1,643 | +0.67 / -0.21 (± 0.90 / 0.29) | 38 / 37 | -98.7 / -44.0 | -45.1 / -14.7 | 1 / 1 | -98.7 / -44.0 | +320 / -13 | 743 / 427 | no / no |
| Trailing stop 2 ATR, no target | 1,437 / 1,643 | +0.10 / +0.35 (± 2.37 / 0.71) | 37 / 36 | -220 / -59.2 | -92.8 / -27.5 | 1 / 1 | -220 / -59.2 | +257 / +284 | 1,044 / 400 | no / no |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 1,437 / 1,643 | +0.82 / -0.21 (± 0.80 / 0.26) | 51 / 50 | -121 / -44.0 | -60.8 / -18.7 | 1 / 1 | -121 / -44.0 | +836 / +33 | 466 / 401 | no / no |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |  |  |  |  |  |  |  |  |
| Pyramid, 2 adds | 1,437 / 1,643 | +1.21 / -0.63 (± 1.51 / 0.45) | 24 / 22 | -98.7 / -44.0 | -51.9 / -15.0 | 3 / 3 | -98.7 / -44.0 | +390 / -475 | 1,501 / 726 | no / no |
| Pyramid, 4 adds | 1,437 / 1,643 | +1.38 / -0.69 (± 1.65 / 0.47) | 24 / 22 | -98.7 / -44.0 | -51.9 / -15.0 | 5 / 5 | -98.7 / -44.0 | +571 / -557 | 1,469 / 747 | no / no |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |  |  |  |  |  |  |  |  |
| Hedge lock, unlocked by the next vote signal | 1,437 / 1,643 | +0.69 / -0.06 (± 0.67 / 0.38) | 61 / 63 | -218 / -70.4 | -75.7 / -35.2 | 2 / 2 | -218 / -70.4 | +625 / +42 | 642 / 404 | no / no |
| Close at -1 ATR, re-enter on the next vote signal | 1,437 / 1,643 | +0.69 / -0.06 (± 0.67 / 0.38) | 61 / 63 | -218 / -70.4 | -75.7 / -35.2 | 1 / 1 | -218 / -70.4 | +625 / +42 | 642 / 404 | no / no |
| Hedge lock, both legs closed 4 h later | 1,437 / 1,643 | +0.35 / -0.17 (± 0.58 / 0.24) | 51 / 50 | -122 / -44.1 | -61.2 / -18.8 | 2 / 2 | -122 / -44.2 | +648 / -169 | 513 / 311 | no / no |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |  |  |  |  |  |  |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 1,437 / 1,643 | -2.10 / -0.23 (± 2.18 / 0.98) | 93 / 93 | -1,364 / -259 | -415 / -148 | 22 / 22 | -1,364 / -259 | -2,000 / -362 | 2,158 / 1,426 | 2026-03-02, many losses / no |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 1,437 / 1,643 | -1.80 / -0.81 (± 1.24 / 0.42) | 78 / 78 | -370 / -130 | -147 / -58.9 | 12.9 / 12.9 | -393 / -130 | -487 / -788 | 2,534 / 1,159 | no / no |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |  |  |  |  |  |  |  |  |
| Stop and reverse, same size | 1,437 / 1,643 | +0.22 / -0.13 (± 0.54 / 0.22) | 51 / 50 | -211 / -73.6 | -80.2 / -32.1 | 1 / 1 | -211 / -73.6 | -22 / -122 | 652 / 350 | no / no |
| Stop and reverse, double size | 1,437 / 1,643 | -0.03 / -0.17 (± 0.81 / 0.35) | 74 / 75 | -317 / -129 | -120 / -48.1 | 2 / 2 | -317 / -129 | -496 / -200 | 1,126 / 467 | no / no |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |  |  |  |  |  |  |  |  |
| Martingale: double after a loss, up to x8 | 1,437 / 1,643 | +3.86 / -0.24 (± 1.38 / 1.00) | 51 / 50 | -517 / -352 | -198 / -78.8 | 8 / 8 | -517 / -352 | +5,543 / -386 | 1,938 / 2,109 | no / no |
| Anti-martingale: double after a win, up to x8 | 1,437 / 1,643 | +0.69 / -0.01 (± 2.15 / 0.76) | 51 / 50 | -800 / -215 | -215 / -79.4 | 8 / 8 | -800 / -215 | +986 / -17 | 2,428 / 1,321 | no / no |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |  |  |  |  |  |  |  |  |
| Daily loss limit 1 R | 814 / 915 | -0.08 / -0.11 (± 0.79 / 0.27) | 50 / 50 | -121 / -26.9 | -52.6 / -17.2 | 1 / 1 | -121 / -26.9 | -66 / -99 | 564 / 250 | no / no |
| Daily loss limit 2 R | 1,176 / 1,347 | -0.06 / -0.20 (± 0.68 / 0.22) | 49 / 49 | -121 / -26.9 | -54.6 / -17.8 | 1 / 1 | -121 / -26.9 | -73 / -272 | 810 / 431 | no / no |
<!-- /table -->

### Gold, votes only

<!-- table main:XAUUSDm:votes -->
Entries: 2,536 / 2,953. One R (the ATR of the entry hour on 0.01 lot): median $17.55 / $6.66, 95th percentile $37.60 / $14.83, largest $125.01 / $26.87. Every cell is DEV / CONFIRM; amounts in USD for a base size of 0.01 lot; position in units of 0.01 lot.

| Mechanism | Baskets | Expectancy per entry (± s.e.) | Win % | Worst basket | 1st percentile | Largest position held | Worst floating loss | $2,000 account: result | deepest drawdown | emptied |
|---|---|---|---|---|---|---|---|---|---|---|
| **Single position, fixed stop and target** |  |  |  |  |  |  |  |  |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 2,536 / 2,953 | -0.37 / -0.11 (± 0.42 / 0.16) | 48 / 49 | -121 / -45.0 | -56.1 / -18.3 | 1 / 1 | -121 / -45.0 | -940 / -327 | 1,603 / 912 | no / no |
| Fixed stop 2 ATR, target 2 ATR | 2,536 / 2,953 | -0.93 / -0.46 (± 0.95 / 0.32) | 49 / 48 | -243 / -70.0 | -113 / -36.6 | 1 / 1 | -243 / -70.0 | -1,330 / -533 | 2,311 / 952 | no / no |
| Fixed stop 1 ATR, target 2 ATR | 2,536 / 2,953 | +0.08 / -0.19 (± 0.64 / 0.22) | 33 / 32 | -121 / -45.0 | -61.2 / -19.1 | 1 / 1 | -121 / -45.0 | -843 / -534 | 1,372 / 716 | no / no |
| Fixed stop 2 ATR, target 1 ATR | 2,536 / 2,953 | -1.01 / -0.32 (± 0.56 / 0.26) | 65 / 65 | -243 / -70.0 | -98.8 / -33.8 | 1 / 1 | -243 / -70.0 | -1,673 / -288 | 2,648 / 683 | no / no |
| Fixed stop $20, target $20 (the V2 exit) | 2,536 / 2,953 | -0.13 / -0.60 (± 0.33 / 0.42) | 50 / 48 | -37.1 / -45.0 | -20.0 / -20.0 | 1 / 1 | -37.1 / -45.0 | -346 / -359 | 874 / 880 | no / no |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |  |  |  |  |  |  |  |  |
| Live ladder, no stop | 2,536 / 2,953 | -4.38 / -12.57 (± 5.37 / 13.54) | 100 / 100 | -13,647 / -40,078 | +1.0 / +1.0 | 32 / 32 | -68,514 / -46,081 | -2,000 / -2,000 | 2,139 / 2,148 | 2025-09-01, one basket / 2024-03-01, one basket |
| Live ladder, basket stop $60 | 2,536 / 2,953 | -0.94 / -0.70 (± 0.25 / 0.17) | 97 / 97 | -60.0 / -66.8 | -60.0 / -60.0 | 32 / 32 | -60.0 / -66.8 | -2,000 / -1,925 | 2,030 / 1,979 | 2026-07-21, many losses / no |
| Live ladder, basket stop $200 | 2,536 / 2,953 | -0.75 / -0.29 (± 0.34 / 0.29) | 99 / 99 | -241 / -200 | +1.0 / +1.0 | 32 / 32 | -241 / -200 | -1,784 / -1,080 | 2,018 / 1,765 | no / no |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |  |  |  |  |  |  |  |  |
| Budget 1 R, no add | 2,536 / 2,953 | -0.08 / -0.20 (± 0.28 / 0.14) | 66 / 65 | -121 / -45.0 | -48.9 / -17.6 | 1 / 1 | -121 / -45.0 | -210 / -600 | 868 / 843 | no / no |
| Budget 1 R, 2 adds 0.17 ATR apart | 2,536 / 2,953 | +0.13 / -0.56 (± 0.35 / 0.17) | 53 / 50 | -121 / -26.9 | -58.9 / -18.2 | 3 / 3 | -121 / -26.9 | +331 / -1,664 | 818 / 1,892 | no / no |
| Budget 2 R, no add | 2,536 / 2,953 | -0.15 / -0.40 (± 0.47 / 0.21) | 79 / 78 | -243 / -70.0 | -73.3 / -31.8 | 1 / 1 | -243 / -70.0 | -269 / -351 | 1,264 / 589 | no / no |
| Budget 2 R, 2 adds 0.33 ATR apart | 2,536 / 2,953 | -0.18 / -0.49 (± 0.55 / 0.26) | 71 / 70 | -243 / -112 | -94.4 / -34.9 | 3 / 3 | -243 / -112 | -477 / -1,457 | 1,439 / 1,770 | no / no |
| Budget 3 R, no add | 2,536 / 2,953 | -0.41 / -0.65 (± 0.61 / 0.30) | 85 / 84 | -364 / -91.6 | -98.8 / -46.2 | 1 / 1 | -364 / -91.6 | -1,140 / -611 | 1,457 / 1,034 | no / no |
| Budget 3 R, 1 add 1 ATR apart | 2,536 / 2,953 | -0.85 / -0.74 (± 0.75 / 0.31) | 82 / 81 | -364 / -117 | -108 / -45.9 | 2 / 2 | -364 / -117 | -1,493 / -1,109 | 2,389 / 1,361 | no / no |
| Budget 3 R, 2 adds 0.5 ATR apart | 2,536 / 2,953 | -0.68 / -0.54 (± 0.73 / 0.36) | 79 / 78 | -364 / -79.8 | -110 / -48.3 | 3 / 3 | -364 / -79.8 | -1,269 / -762 | 2,117 / 1,448 | no / no |
| Budget 3 R, 3 adds 0.3 ATR apart | 2,536 / 2,953 | -1.03 / -0.58 (± 0.80 / 0.38) | 75 / 75 | -364 / -114 | -126 / -49.0 | 4 / 4 | -364 / -114 | -2,000 / -1,084 | 2,125 / 1,888 | 2026-02-02, many losses / no |
| Budget 3 R, 4 adds 0.2 ATR apart | 2,536 / 2,953 | -0.56 / -0.88 (± 0.87 / 0.39) | 72 / 71 | -364 / -152 | -131 / -51.1 | 5 / 5 | -364 / -152 | -1,414 / -2,000 | 2,724 / 2,072 | no / 2025-04-17, many losses |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 2,536 / 2,953 | -0.87 / -0.54 (± 0.61 / 0.35) | 77 / 78 | -157 / -78.3 | -60.0 / -48.8 | 3 / 3 | -157 / -78.3 | -1,807 / -779 | 2,097 / 1,465 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 2,489 / 2,911 | -0.67 / -0.55 (± 0.61 / 0.34) | 77 / 78 | -119 / -78.3 | -60.0 / -48.7 | 3 / 3 | -119 / -78.3 | -1,221 / -773 | 1,947 / 1,327 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 2,406 / 2,855 | -0.60 / -0.51 (± 0.59 / 0.30) | 75 / 76 | -60.0 / -60.0 | -60.0 / -45.7 | 3 / 3 | -60.0 / -60.0 | -1,012 / -711 | 1,696 / 1,149 | no / no |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |  |  |  |  |  |  |  |  |
| Add when the M5 MACD histogram turns | 2,536 / 2,953 | -0.93 / -0.75 (± 0.75 / 0.29) | 82 / 81 | -364 / -114 | -108 / -46.4 | 3 / 3 | -364 / -114 | -2,000 / -1,224 | 2,592 / 1,478 | 2026-10-07, many losses / no |
| Add when the M15 MACD histogram turns | 2,536 / 2,953 | -0.16 / -0.59 (± 0.65 / 0.27) | 83 / 82 | -364 / -114 | -100 / -46.2 | 3 / 3 | -364 / -114 | -1,777 / -953 | 2,492 / 1,315 | no / no |
| Add when the M5 RSI comes back through 35 / 65 | 2,536 / 2,953 | -0.34 / -0.68 (± 0.67 / 0.30) | 83 / 82 | -364 / -114 | -98.9 / -46.3 | 3 / 3 | -364 / -114 | -1,327 / -919 | 1,918 / 1,239 | no / no |
| Add when the M15 RSI comes back through 35 / 65 | 2,536 / 2,953 | +0.14 / -0.58 (± 0.62 / 0.26) | 85 / 83 | -364 / -115 | -98.8 / -45.0 | 3 / 3 | -364 / -115 | -805 / -573 | 1,313 / 1,005 | no / no |
| **Stops that follow the price (single position)** |  |  |  |  |  |  |  |  |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 2,536 / 2,953 | -0.10 / -0.17 (± 0.32 / 0.16) | 32 / 32 | -121 / -45.0 | -48.9 / -17.6 | 1 / 1 | -121 / -45.0 | -261 / -502 | 955 / 968 | no / no |
| Break-even at +1 ATR (stop 1, target 2) | 2,536 / 2,953 | -0.21 / -0.12 (± 0.56 / 0.18) | 25 / 24 | -121 / -45.0 | -56.1 / -18.5 | 1 / 1 | -121 / -45.0 | -110 / -200 | 748 / 829 | no / no |
| Trailing stop 1 ATR, no target | 2,536 / 2,953 | -0.76 / -0.24 (± 0.43 / 0.20) | 35 / 36 | -120 / -45.0 | -42.4 / -14.8 | 1 / 1 | -120 / -45.0 | -2,000 / -254 | 2,031 / 784 | 2026-08-06, many losses / no |
| Trailing stop 2 ATR, no target | 2,536 / 2,953 | +0.04 / -0.33 (± 1.26 / 0.42) | 36 / 35 | -241 / -70.0 | -84.5 / -28.4 | 1 / 1 | -241 / -70.0 | +426 / +68 | 1,217 / 516 | no / no |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 2,536 / 2,953 | -0.36 / -0.18 (± 0.42 / 0.18) | 48 / 49 | -121 / -45.0 | -56.1 / -18.3 | 1 / 1 | -121 / -45.0 | -668 / -181 | 1,135 / 822 | no / no |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |  |  |  |  |  |  |  |  |
| Pyramid, 2 adds | 2,536 / 2,953 | -1.46 / -0.66 (± 0.75 / 0.30) | 22 / 22 | -120 / -45.0 | -47.8 / -15.8 | 3 / 3 | -120 / -45.0 | -2,000 / -1,067 | 2,091 / 1,547 | 2026-03-03, many losses / no |
| Pyramid, 4 adds | 2,536 / 2,953 | -1.52 / -0.74 (± 0.84 / 0.31) | 21 / 22 | -120 / -45.0 | -47.8 / -15.8 | 5 / 5 | -120 / -45.0 | -2,000 / -1,214 | 2,120 / 1,687 | 2026-03-03, many losses / no |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |  |  |  |  |  |  |  |  |
| Hedge lock, unlocked by the next vote signal | 2,536 / 2,953 | -0.33 / -0.10 (± 0.75 / 0.26) | 60 / 63 | -238 / -68.2 | -78.7 / -32.0 | 2 / 2 | -238 / -68.2 | -940 / -327 | 1,603 / 912 | no / no |
| Close at -1 ATR, re-enter on the next vote signal | 2,536 / 2,953 | -0.33 / -0.10 (± 0.75 / 0.26) | 60 / 63 | -238 / -68.2 | -78.7 / -32.0 | 1 / 1 | -238 / -68.2 | -940 / -327 | 1,603 / 912 | no / no |
| Hedge lock, both legs closed 4 h later | 2,536 / 2,953 | -0.49 / -0.20 (± 0.42 / 0.16) | 48 / 49 | -122 / -45.1 | -56.4 / -18.4 | 2 / 2 | -122 / -45.2 | -1,025 / -449 | 1,105 / 812 | no / no |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |  |  |  |  |  |  |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 2,536 / 2,953 | +0.14 / -0.26 (± 1.98 / 0.77) | 94 / 93 | -1,364 / -265 | -400 / -142 | 22 / 22 | -1,364 / -265 | -2,000 / -2,000 | 2,014 / 2,107 | 2025-11-05, many losses / 2025-02-27, many losses |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 2,536 / 2,953 | -1.94 / -0.80 (± 1.01 / 0.32) | 78 / 78 | -501 / -132 | -153 / -59.2 | 12.9 / 12.9 | -501 / -132 | -2,000 / -2,000 | 2,442 / 2,031 | 2026-02-13, many losses / 2025-02-21, many losses |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |  |  |  |  |  |  |  |  |
| Stop and reverse, same size | 2,536 / 2,953 | -0.04 / +0.07 (± 0.65 / 0.16) | 49 / 49 | -216 / -68.3 | -76.4 / -29.8 | 1 / 1 | -216 / -68.3 | -144 / -277 | 1,177 / 646 | no / no |
| Stop and reverse, double size | 2,536 / 2,953 | +0.29 / +0.25 (± 0.97 / 0.25) | 74 / 75 | -324 / -91.5 | -115 / -44.8 | 2 / 2 | -324 / -91.5 | +466 / -169 | 1,777 / 631 | no / no |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |  |  |  |  |  |  |  |  |
| Martingale: double after a loss, up to x8 | 2,536 / 2,953 | -0.84 / -0.20 (± 1.26 / 0.57) | 48 / 49 | -896 / -360 | -216 / -85.7 | 8 / 8 | -896 / -360 | -2,000 / -2,000 | 2,221 / 2,674 | 2025-10-17, many losses / 2025-04-22, many losses |
| Anti-martingale: double after a win, up to x8 | 2,536 / 2,953 | -0.97 / -0.37 (± 1.37 / 0.53) | 48 / 49 | -727 / -181 | -219 / -80.7 | 8 / 8 | -727 / -181 | -2,000 / -2,000 | 3,804 / 2,140 | 2026-10-02, many losses / 2025-04-24, many losses |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |  |  |  |  |  |  |  |  |
| Daily loss limit 1 R | 1,134 / 1,298 | -0.59 / -0.35 (± 0.56 / 0.26) | 49 / 48 | -112 / -26.9 | -57.6 / -18.1 | 1 / 1 | -112 / -26.9 | -667 / -456 | 846 / 571 | no / no |
| Daily loss limit 2 R | 1,821 / 2,126 | -0.45 / -0.04 (± 0.39 / 0.17) | 49 / 49 | -120 / -26.9 | -53.2 / -17.6 | 1 / 1 | -120 / -26.9 | -811 / -80 | 1,250 / 543 | no / no |
<!-- /table -->

### Gold, random entries

<!-- table main:XAUUSDm:random -->
Entries: 2,524 / 2,844. One R (the ATR of the entry hour on 0.01 lot): median $17.43 / $6.73, 95th percentile $36.51 / $15.15, largest $125.68 / $27.34. Every cell is DEV / CONFIRM; amounts in USD for a base size of 0.01 lot; position in units of 0.01 lot.

| Mechanism | Baskets | Expectancy per entry (± s.e.) | Win % | Worst basket | 1st percentile | Largest position held | Worst floating loss | $2,000 account: result | deepest drawdown | emptied |
|---|---|---|---|---|---|---|---|---|---|---|
| **Single position, fixed stop and target** |  |  |  |  |  |  |  |  |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 2,524 / 2,844 | +0.17 / -0.25 (± 0.43 / 0.16) | 50 / 48 | -121 / -50.9 | -53.5 / -18.6 | 1 / 1 | -121 / -50.9 | +442 / -714 | 718 / 792 | no / no |
| Fixed stop 2 ATR, target 2 ATR | 2,524 / 2,844 | +0.23 / -0.02 (± 0.90 / 0.33) | 50 / 49 | -243 / -70.0 | -104 / -36.3 | 1 / 1 | -243 / -70.0 | +559 / -252 | 858 / 745 | no / no |
| Fixed stop 1 ATR, target 2 ATR | 2,524 / 2,844 | +0.47 / -0.13 (± 0.72 / 0.22) | 33 / 32 | -121 / -50.9 | -61.2 / -19.2 | 1 / 1 | -121 / -50.9 | +453 / -582 | 1,175 / 871 | no / no |
| Fixed stop 2 ATR, target 1 ATR | 2,524 / 2,844 | +0.02 / -0.22 (± 0.68 / 0.21) | 66 / 65 | -243 / -70.0 | -94.5 / -34.2 | 1 / 1 | -243 / -70.0 | +29 / -1,168 | 964 / 1,341 | no / no |
| Fixed stop $20, target $20 (the V2 exit) | 2,524 / 2,844 | -0.35 / -0.35 (± 0.42 / 0.38) | 49 / 49 | -40.7 / -50.9 | -20.0 / -20.0 | 1 / 1 | -40.7 / -50.9 | -38 / +143 | 745 / 634 | no / no |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |  |  |  |  |  |  |  |  |
| Live ladder, no stop | 2,524 / 2,844 | +1.00 / -10.09 (± 0.00 / 11.12) | 100 / 100 | +1.0 / -31,554 | +1.0 / +1.0 | 32 / 32 | -2,331 / -37,556 | +2,422 / -2,000 | 2,331 / 3,309 | no / 2024-11-11, one basket |
| Live ladder, basket stop $60 | 2,524 / 2,844 | -2.55 / -1.19 (± 0.30 / 0.24) | 94 / 96 | -60.0 / -95.9 | -60.0 / -60.0 | 32 / 32 | -60.0 / -95.9 | -2,000 / -2,000 | 2,029 / 2,015 | 2026-01-26, many losses / 2025-03-31, many losses |
| Live ladder, basket stop $200 | 2,524 / 2,844 | -2.02 / -0.76 (± 0.47 / 0.32) | 98 / 99 | -200 / -200 | -200 / +1.0 | 32 / 32 | -200 / -200 | -2,000 / -2,000 | 2,029 / 2,016 | 2026-02-24, many losses / 2025-01-27, many losses |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |  |  |  |  |  |  |  |  |
| Budget 1 R, no add | 2,524 / 2,844 | -0.36 / -0.14 (± 0.34 / 0.11) | 65 / 65 | -121 / -32.7 | -50.7 / -17.6 | 1 / 1 | -121 / -32.7 | -900 / -398 | 1,170 / 504 | no / no |
| Budget 1 R, 2 adds 0.17 ATR apart | 2,524 / 2,844 | -1.51 / -0.18 (± 0.37 / 0.16) | 50 / 52 | -121 / -26.6 | -59.4 / -17.5 | 3 / 3 | -121 / -26.6 | -2,000 / -518 | 2,008 / 653 | 2026-04-02, many losses / no |
| Budget 2 R, no add | 2,524 / 2,844 | -0.20 / -0.15 (± 0.49 / 0.16) | 79 / 79 | -243 / -70.0 | -75.8 / -30.2 | 1 / 1 | -243 / -70.0 | -664 / -374 | 988 / 619 | no / no |
| Budget 2 R, 2 adds 0.33 ATR apart | 2,524 / 2,844 | -0.34 / -0.38 (± 0.50 / 0.24) | 70 / 70 | -243 / -60.5 | -89.3 / -34.7 | 3 / 3 | -243 / -60.5 | -867 / -1,077 | 1,444 / 1,319 | no / no |
| Budget 3 R, no add | 2,524 / 2,844 | -0.55 / -0.25 (± 0.60 / 0.18) | 85 / 84 | -364 / -79.8 | -107 / -42.4 | 1 / 1 | -364 / -79.8 | -537 / -341 | 1,389 / 736 | no / no |
| Budget 3 R, 1 add 1 ATR apart | 2,524 / 2,844 | -0.34 / -0.37 (± 0.74 / 0.21) | 83 / 82 | -364 / -117 | -109 / -44.3 | 2 / 2 | -364 / -117 | -1,248 / -769 | 1,614 / 979 | no / no |
| Budget 3 R, 2 adds 0.5 ATR apart | 2,524 / 2,844 | +0.09 / -0.09 (± 0.59 / 0.22) | 80 / 79 | -364 / -79.8 | -110 / -45.3 | 3 / 3 | -364 / -79.8 | +351 / -197 | 1,338 / 597 | no / no |
| Budget 3 R, 3 adds 0.3 ATR apart | 2,524 / 2,844 | +0.27 / -0.43 (± 0.78 / 0.30) | 75 / 75 | -364 / -79.9 | -117 / -49.9 | 4 / 4 | -364 / -79.9 | +1,916 / -630 | 2,051 / 996 | no / no |
| Budget 3 R, 4 adds 0.2 ATR apart | 2,524 / 2,844 | -0.77 / -0.70 (± 0.69 / 0.37) | 71 / 71 | -364 / -89.3 | -124 / -51.8 | 5 / 5 | -364 / -89.3 | -2,000 / -2,000 | 2,291 / 2,005 | 2026-10-09, many losses / 2025-04-24, many losses |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 2,524 / 2,844 | -0.25 / -0.13 (± 0.49 / 0.23) | 78 / 79 | -222 / -60.0 | -60.0 / -45.4 | 3 / 3 | -222 / -60.0 | -431 / -318 | 1,477 / 679 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 2,477 / 2,792 | -0.33 / -0.11 (± 0.50 / 0.22) | 77 / 79 | -104 / -60.0 | -60.0 / -45.3 | 3 / 3 | -104 / -60.0 | -614 / -314 | 1,369 / 586 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 2,410 / 2,732 | -0.39 / -0.10 (± 0.52 / 0.20) | 76 / 77 | -60.0 / -60.0 | -60.0 / -43.5 | 3 / 3 | -60.0 / -60.0 | -545 / -450 | 1,534 / 805 | no / no |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |  |  |  |  |  |  |  |  |
| Add when the M5 MACD histogram turns | 2,524 / 2,844 | +0.04 / -0.35 (± 0.70 / 0.19) | 82 / 82 | -364 / -114 | -103 / -44.7 | 3 / 3 | -364 / -114 | +744 / -518 | 1,153 / 734 | no / no |
| Add when the M15 MACD histogram turns | 2,524 / 2,844 | -0.59 / -0.28 (± 0.62 / 0.21) | 82 / 82 | -364 / -114 | -105 / -44.3 | 3 / 3 | -364 / -114 | -913 / -903 | 1,555 / 974 | no / no |
| Add when the M5 RSI comes back through 35 / 65 | 2,524 / 2,844 | -0.02 / -0.42 (± 0.57 / 0.18) | 83 / 82 | -364 / -114 | -105 / -44.3 | 3 / 3 | -364 / -114 | -102 / -529 | 1,664 / 862 | no / no |
| Add when the M15 RSI comes back through 35 / 65 | 2,524 / 2,844 | -0.43 / -0.21 (± 0.54 / 0.19) | 84 / 84 | -364 / -115 | -109 / -43.2 | 3 / 3 | -364 / -115 | -986 / -760 | 1,397 / 1,059 | no / no |
| **Stops that follow the price (single position)** |  |  |  |  |  |  |  |  |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 2,524 / 2,844 | -0.31 / -0.06 (± 0.37 / 0.14) | 33 / 33 | -121 / -32.7 | -50.7 / -17.6 | 1 / 1 | -121 / -32.7 | -777 / -173 | 1,200 / 446 | no / no |
| Break-even at +1 ATR (stop 1, target 2) | 2,524 / 2,844 | +0.53 / -0.11 (± 0.56 / 0.19) | 25 / 24 | -121 / -50.9 | -53.5 / -18.6 | 1 / 1 | -121 / -50.9 | +1,085 / -144 | 1,025 / 561 | no / no |
| Trailing stop 1 ATR, no target | 2,524 / 2,844 | -0.30 / +0.03 (± 0.46 / 0.20) | 36 / 36 | -120 / -32.7 | -42.3 / -15.0 | 1 / 1 | -120 / -32.7 | -486 / -173 | 1,408 / 821 | no / no |
| Trailing stop 2 ATR, no target | 2,524 / 2,844 | +1.09 / +0.29 (± 1.27 / 0.39) | 37 / 37 | -241 / -70.0 | -76.9 / -27.9 | 1 / 1 | -241 / -70.0 | +1,659 / +376 | 1,063 / 375 | no / no |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 2,524 / 2,844 | +0.32 / -0.22 (± 0.52 / 0.17) | 50 / 48 | -121 / -50.9 | -53.5 / -18.6 | 1 / 1 | -121 / -50.9 | +418 / -476 | 1,246 / 579 | no / no |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |  |  |  |  |  |  |  |  |
| Pyramid, 2 adds | 2,524 / 2,844 | -0.26 / +0.01 (± 0.82 / 0.34) | 22 / 21 | -120 / -32.7 | -43.9 / -16.1 | 3 / 3 | -120 / -32.7 | -63 / -300 | 2,380 / 1,426 | no / no |
| Pyramid, 4 adds | 2,524 / 2,844 | -0.21 / -0.07 (± 0.95 / 0.35) | 22 / 21 | -120 / -32.7 | -43.9 / -16.1 | 5 / 5 | -120 / -32.7 | -91 / -398 | 2,657 / 1,517 | no / no |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |  |  |  |  |  |  |  |  |
| Hedge lock, unlocked by the next vote signal | 2,524 / 2,844 | -0.38 / -0.24 (± 0.53 / 0.20) | 61 / 61 | -243 / -70.3 | -79.0 / -33.3 | 2 / 2 | -243 / -70.3 | -1,294 / -266 | 1,514 / 587 | no / no |
| Close at -1 ATR, re-enter on the next vote signal | 2,524 / 2,844 | -0.38 / -0.24 (± 0.53 / 0.20) | 61 / 61 | -243 / -70.3 | -79.0 / -33.3 | 1 / 1 | -243 / -70.3 | -1,294 / -266 | 1,514 / 587 | no / no |
| Hedge lock, both legs closed 4 h later | 2,524 / 2,844 | +0.06 / -0.34 (± 0.44 / 0.16) | 50 / 48 | -122 / -51.0 | -53.9 / -18.7 | 2 / 2 | -122 / -51.0 | -1,226 / -1,000 | 1,539 / 1,011 | no / no |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |  |  |  |  |  |  |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 2,524 / 2,844 | -1.26 / +0.42 (± 1.71 / 0.67) | 93 / 93 | -1,502 / -278 | -372 / -147 | 22 / 22 | -1,502 / -278 | -2,000 / +758 | 2,265 / 854 | 2026-01-26, many losses / no |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 2,524 / 2,844 | -2.06 / -0.96 (± 0.85 / 0.36) | 78 / 78 | -465 / -112 | -153 / -61.1 | 12.9 / 12.9 | -465 / -112 | -2,000 / -2,000 | 2,262 / 2,014 | 2026-04-08, many losses / 2025-01-03, many losses |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |  |  |  |  |  |  |  |  |
| Stop and reverse, same size | 2,524 / 2,844 | +0.14 / -0.15 (± 0.45 / 0.18) | 50 / 48 | -243 / -69.1 | -79.5 / -32.7 | 1 / 1 | -243 / -69.1 | -152 / -429 | 1,104 / 828 | no / no |
| Stop and reverse, double size | 2,524 / 2,844 | +0.11 / -0.05 (± 0.67 / 0.26) | 75 / 74 | -364 / -120 | -119 / -48.7 | 2 / 2 | -364 / -120 | -242 / +9 | 1,391 / 1,008 | no / no |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |  |  |  |  |  |  |  |  |
| Martingale: double after a loss, up to x8 | 2,524 / 2,844 | +0.95 / -0.69 (± 1.65 / 0.53) | 50 / 48 | -971 / -262 | -197 / -80.4 | 8 / 8 | -971 / -262 | -2,000 / -2,000 | 2,016 / 2,115 | 2025-10-23, many losses / 2025-04-07, many losses |
| Anti-martingale: double after a win, up to x8 | 2,524 / 2,844 | -0.33 / -0.95 (± 1.36 / 0.45) | 50 / 48 | -915 / -219 | -208 / -94.6 | 8 / 8 | -915 / -219 | -2,000 / -2,000 | 3,159 / 2,333 | 2026-03-02, many losses / 2025-02-28, many losses |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |  |  |  |  |  |  |  |  |
| Daily loss limit 1 R | 1,168 / 1,230 | +0.18 / -0.27 (± 0.75 / 0.28) | 50 / 48 | -120 / -27.3 | -49.8 / -18.2 | 1 / 1 | -120 / -27.3 | +212 / -329 | 666 / 538 | no / no |
| Daily loss limit 2 R | 1,822 / 2,013 | +0.01 / -0.22 (± 0.56 / 0.19) | 49 / 48 | -120 / -27.3 | -52.2 / -18.8 | 1 / 1 | -120 / -27.3 | +18 / -449 | 683 / 577 | no / no |
<!-- /table -->

### BTC, entries with the H1 trend

<!-- table main:BTCUSDm:trend -->
Entries: 1,970 / 2,086. One R (the ATR of the entry hour on 0.01 lot): median $4.67 / $5.31, 95th percentile $8.88 / $11.46, largest $18.98 / $22.49. Every cell is DEV / CONFIRM; amounts in USD for a base size of 0.01 lot; position in units of 0.01 lot.

| Mechanism | Baskets | Expectancy per entry (± s.e.) | Win % | Worst basket | 1st percentile | Largest position held | Worst floating loss | $2,000 account: result | deepest drawdown | emptied |
|---|---|---|---|---|---|---|---|---|---|---|
| **Single position, fixed stop and target** |  |  |  |  |  |  |  |  |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 1,970 / 2,086 | -0.00 / -0.39 (± 0.12 / 0.14) | 50 / 46 | -17.3 / -22.5 | -10.3 / -14.1 | 1 / 1 | -17.3 / -22.5 | -8 / -805 | 190 / 862 | no / no |
| Fixed stop 2 ATR, target 2 ATR | 1,970 / 2,086 | +0.43 / +0.14 (± 0.29 / 0.40) | 53 / 50 | -38.0 / -45.0 | -20.2 / -28.2 | 1 / 1 | -38.0 / -45.0 | +153 / -161 | 296 / 516 | no / no |
| Fixed stop 1 ATR, target 2 ATR | 1,970 / 2,086 | +0.12 / -0.23 (± 0.17 / 0.25) | 35 / 32 | -19.0 / -22.5 | -11.0 / -14.5 | 1 / 1 | -19.0 / -22.5 | +167 / -207 | 169 / 493 | no / no |
| Fixed stop 2 ATR, target 1 ATR | 1,970 / 2,086 | +0.20 / -0.24 (± 0.18 / 0.24) | 68 / 65 | -34.6 / -38.8 | -18.9 / -26.4 | 1 / 1 | -34.6 / -38.8 | +164 / -791 | 186 / 868 | no / no |
| Fixed stop $20, target $20 (the V2 exit) | 1,970 / 2,086 | +0.61 / +1.01 (± 0.85 / 0.69) | 52 / 52 | -20.1 / -20.5 | -20.0 / -20.0 | 1 / 1 | -20.1 / -20.5 | +406 / +109 | 192 / 494 | no / no |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |  |  |  |  |  |  |  |  |
| Live ladder, no stop | 1,970 / 2,086 | +1.00 / +0.72 (± 0.00 / 0.28) | 100 / 100 | -1.3 / -578 | +1.0 / +1.0 | 32 / 32 | -1,806 / -1,745 | +1,739 / +1,797 | 1,806 / 1,745 | no / no |
| Live ladder, basket stop $60 | 1,970 / 2,086 | -0.42 / -1.54 (± 0.23 / 0.24) | 98 / 96 | -60.0 / -60.0 | -60.0 / -60.0 | 32 / 32 | -60.0 / -60.0 | -679 / -2,000 | 925 / 2,012 | no / 2025-01-13, many losses |
| Live ladder, basket stop $200 | 1,970 / 2,086 | -0.12 / -2.18 (± 0.34 / 0.57) | 99 / 98 | -200 / -200 | +1.0 / -200 | 32 / 32 | -200 / -200 | -158 / -2,000 | 679 / 2,125 | no / 2024-11-05, many losses |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |  |  |  |  |  |  |  |  |
| Budget 1 R, no add | 1,970 / 2,086 | -0.04 / -0.47 (± 0.09 / 0.10) | 67 / 61 | -15.3 / -22.5 | -9.7 / -13.2 | 1 / 1 | -15.3 / -22.5 | -85 / -975 | 199 / 982 | no / no |
| Budget 1 R, 2 adds 0.17 ATR apart | 1,970 / 2,086 | -0.11 / -0.79 (± 0.12 / 0.14) | 52 / 45 | -19.0 / -22.5 | -10.1 / -13.5 | 3 / 3 | -19.0 / -22.5 | -221 / -1,638 | 364 / 1,641 | no / no |
| Budget 2 R, no add | 1,970 / 2,086 | -0.01 / -0.26 (± 0.14 / 0.16) | 80 / 77 | -30.6 / -36.5 | -18.0 / -22.9 | 1 / 1 | -30.6 / -38.8 | +50 / -651 | 181 / 721 | no / no |
| Budget 2 R, 2 adds 0.33 ATR apart | 1,970 / 2,086 | +0.00 / -0.95 (± 0.16 / 0.20) | 71 / 65 | -30.3 / -45.0 | -19.1 / -26.4 | 3 / 3 | -30.3 / -45.0 | +5 / -2,000 | 278 / 2,013 | no / 2025-06-22, many losses |
| Budget 3 R, no add | 1,970 / 2,086 | +0.01 / -0.27 (± 0.17 / 0.19) | 86 / 83 | -45.9 / -54.8 | -23.9 / -31.9 | 1 / 1 | -45.9 / -54.8 | -10 / -329 | 205 / 513 | no / no |
| Budget 3 R, 1 add 1 ATR apart | 1,970 / 2,086 | -0.05 / -0.36 (± 0.18 / 0.20) | 83 / 80 | -43.8 / -54.8 | -26.1 / -32.9 | 2 / 2 | -43.8 / -55.1 | -81 / -594 | 324 / 737 | no / no |
| Budget 3 R, 2 adds 0.5 ATR apart | 1,970 / 2,086 | -0.07 / -0.65 (± 0.22 / 0.23) | 80 / 76 | -43.8 / -67.5 | -26.6 / -35.4 | 3 / 3 | -43.8 / -67.5 | -41 / -1,294 | 344 / 1,398 | no / no |
| Budget 3 R, 3 adds 0.3 ATR apart | 1,970 / 2,086 | -0.20 / -1.16 (± 0.22 / 0.23) | 75 / 70 | -43.8 / -67.5 | -27.3 / -38.5 | 4 / 4 | -43.8 / -67.5 | -287 / -2,000 | 364 / 2,013 | no / 2025-04-03, many losses |
| Budget 3 R, 4 adds 0.2 ATR apart | 1,970 / 2,086 | +0.01 / -1.30 (± 0.22 / 0.30) | 73 / 67 | -45.4 / -67.5 | -28.0 / -39.0 | 5 / 5 | -45.4 / -67.5 | +14 / -2,000 | 363 / 2,021 | no / 2025-01-23, many losses |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,970 / 2,086 | -0.07 / -0.64 (± 0.22 / 0.23) | 80 / 76 | -43.8 / -60.0 | -26.6 / -35.4 | 3 / 3 | -43.8 / -60.0 | -41 / -1,286 | 344 / 1,390 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 1,970 / 2,086 | -0.07 / -0.64 (± 0.22 / 0.23) | 80 / 76 | -43.8 / -60.0 | -26.6 / -35.4 | 3 / 3 | -43.8 / -60.0 | -41 / -1,286 | 344 / 1,390 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 1,970 / 2,086 | -0.07 / -0.64 (± 0.22 / 0.23) | 80 / 76 | -43.8 / -60.0 | -26.6 / -35.4 | 3 / 3 | -43.8 / -60.0 | -41 / -1,286 | 344 / 1,390 | no / no |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |  |  |  |  |  |  |  |  |
| Add when the M5 MACD histogram turns | 1,970 / 2,086 | -0.04 / -0.59 (± 0.16 / 0.23) | 83 / 79 | -43.8 / -54.8 | -26.4 / -34.3 | 3 / 3 | -43.8 / -63.9 | -57 / -1,177 | 344 / 1,209 | no / no |
| Add when the M15 MACD histogram turns | 1,970 / 2,086 | -0.07 / -0.33 (± 0.18 / 0.20) | 84 / 81 | -43.8 / -54.8 | -26.1 / -32.3 | 3 / 3 | -43.8 / -61.0 | -210 / -861 | 333 / 985 | no / no |
| Add when the M5 RSI comes back through 35 / 65 | 1,970 / 2,086 | +0.02 / -0.33 (± 0.18 / 0.20) | 84 / 81 | -43.8 / -54.8 | -25.3 / -32.6 | 3 / 3 | -43.8 / -63.9 | -16 / -807 | 206 / 871 | no / no |
| Add when the M15 RSI comes back through 35 / 65 | 1,970 / 2,086 | -0.17 / -0.35 (± 0.18 / 0.20) | 84 / 82 | -45.9 / -54.8 | -26.1 / -32.3 | 3 / 3 | -45.9 / -59.2 | -290 / -699 | 435 / 783 | no / no |
| **Stops that follow the price (single position)** |  |  |  |  |  |  |  |  |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 1,970 / 2,086 | -0.09 / -0.52 (± 0.10 / 0.13) | 32 / 30 | -15.3 / -22.5 | -9.7 / -13.2 | 1 / 1 | -15.3 / -22.5 | -178 / -1,080 | 259 / 1,100 | no / no |
| Break-even at +1 ATR (stop 1, target 2) | 1,970 / 2,086 | +0.04 / -0.29 (± 0.14 / 0.19) | 26 / 24 | -17.3 / -22.5 | -10.3 / -14.1 | 1 / 1 | -17.3 / -22.5 | +50 / -279 | 174 / 462 | no / no |
| Trailing stop 1 ATR, no target | 1,970 / 2,086 | -0.02 / -0.44 (± 0.16 / 0.17) | 37 / 34 | -13.8 / -18.2 | -8.2 / -11.5 | 1 / 1 | -13.8 / -18.2 | -58 / -610 | 159 / 688 | no / no |
| Trailing stop 2 ATR, no target | 1,970 / 2,086 | +0.22 / +0.09 (± 0.29 / 0.41) | 39 / 38 | -28.1 / -33.0 | -16.6 / -21.7 | 1 / 1 | -28.1 / -38.8 | +324 / +304 | 324 / 206 | no / no |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 1,970 / 2,086 | -0.01 / -0.38 (± 0.14 / 0.16) | 50 / 46 | -17.3 / -22.5 | -10.3 / -14.1 | 1 / 1 | -17.3 / -22.5 | -36 / -450 | 182 / 549 | no / no |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |  |  |  |  |  |  |  |  |
| Pyramid, 2 adds | 1,970 / 2,086 | +0.01 / -0.64 (± 0.29 / 0.27) | 22 / 20 | -14.8 / -18.2 | -8.9 / -11.8 | 3 / 3 | -14.8 / -18.2 | +37 / -744 | 322 / 898 | no / no |
| Pyramid, 4 adds | 1,970 / 2,086 | -0.02 / -0.72 (± 0.32 / 0.27) | 22 / 20 | -14.8 / -18.2 | -8.9 / -11.8 | 5 / 5 | -14.8 / -18.2 | -15 / -856 | 363 / 1,013 | no / no |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |  |  |  |  |  |  |  |  |
| Hedge lock, unlocked by the next vote signal | 1,970 / 2,086 | +0.03 / -0.40 (± 0.15 / 0.16) | 61 / 60 | -29.9 / -42.7 | -17.8 / -23.5 | 2 / 2 | -29.9 / -42.7 | +9 / -907 | 249 / 938 | no / no |
| Close at -1 ATR, re-enter on the next vote signal | 1,970 / 2,086 | +0.03 / -0.40 (± 0.15 / 0.16) | 61 / 60 | -29.9 / -42.7 | -17.8 / -23.5 | 1 / 1 | -29.9 / -42.7 | +9 / -907 | 249 / 938 | no / no |
| Hedge lock, both legs closed 4 h later | 1,970 / 2,086 | -0.08 / -0.57 (± 0.12 / 0.15) | 50 / 46 | -17.5 / -22.8 | -10.5 / -14.4 | 2 / 2 | -17.5 / -22.8 | -48 / -1,051 | 157 / 1,051 | no / no |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |  |  |  |  |  |  |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 1,970 / 2,086 | -0.14 / -2.66 (± 0.48 / 0.65) | 94 / 90 | -228 / -219 | -103 / -124 | 22 / 22 | -228 / -258 | +147 / -2,000 | 673 / 2,009 | no / 2024-06-25, many losses |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 1,970 / 2,086 | -1.24 / -2.74 (± 0.27 / 0.36) | 77 / 73 | -78.4 / -83.3 | -39.6 / -52.6 | 12.9 / 12.9 | -78.4 / -89.6 | -1,745 / -2,000 | 1,845 / 2,008 | no / 2024-06-14, many losses |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |  |  |  |  |  |  |  |  |
| Stop and reverse, same size | 1,970 / 2,086 | -0.10 / -0.68 (± 0.13 / 0.16) | 50 / 46 | -30.6 / -45.0 | -18.5 / -26.0 | 1 / 1 | -30.6 / -45.0 | -207 / -1,316 | 357 / 1,329 | no / no |
| Stop and reverse, double size | 1,970 / 2,086 | -0.20 / -0.98 (± 0.18 / 0.22) | 74 / 71 | -45.9 / -67.5 | -27.7 / -39.0 | 2 / 2 | -45.9 / -67.5 | -407 / -1,782 | 571 / 1,805 | no / no |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |  |  |  |  |  |  |  |  |
| Martingale: double after a loss, up to x8 | 1,970 / 2,086 | +0.00 / -0.74 (± 0.42 / 0.47) | 50 / 46 | -121 / -161 | -53.3 / -58.5 | 8 / 8 | -121 / -161 | +4 / -2,000 | 941 / 2,056 | no / 2024-08-20, many losses |
| Anti-martingale: double after a win, up to x8 | 1,970 / 2,086 | +0.00 / -1.01 (± 0.44 / 0.39) | 50 / 46 | -114 / -107 | -59.4 / -61.7 | 8 / 8 | -114 / -107 | +4 / -2,000 | 945 / 2,081 | no / 2025-05-06, many losses |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |  |  |  |  |  |  |  |  |
| Daily loss limit 1 R | 1,086 / 1,035 | +0.15 / -0.55 (± 0.14 / 0.19) | 51 / 45 | -17.3 / -20.2 | -10.7 / -13.1 | 1 / 1 | -17.3 / -20.2 | +160 / -567 | 102 / 579 | no / no |
| Daily loss limit 2 R | 1,574 / 1,671 | +0.04 / -0.44 (± 0.12 / 0.16) | 51 / 46 | -17.3 / -20.2 | -10.3 / -13.8 | 1 / 1 | -17.3 / -20.2 | +68 / -732 | 147 / 795 | no / no |
<!-- /table -->

### BTC, votes only

<!-- table main:BTCUSDm:votes -->
Entries: 3,539 / 3,909. One R (the ATR of the entry hour on 0.01 lot): median $4.71 / $5.30, 95th percentile $9.02 / $11.21, largest $19.25 / $22.49. Every cell is DEV / CONFIRM; amounts in USD for a base size of 0.01 lot; position in units of 0.01 lot.

| Mechanism | Baskets | Expectancy per entry (± s.e.) | Win % | Worst basket | 1st percentile | Largest position held | Worst floating loss | $2,000 account: result | deepest drawdown | emptied |
|---|---|---|---|---|---|---|---|---|---|---|
| **Single position, fixed stop and target** |  |  |  |  |  |  |  |  |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 3,539 / 3,909 | -0.05 / -0.39 (± 0.08 / 0.09) | 50 / 46 | -19.2 / -22.5 | -10.6 / -13.8 | 1 / 1 | -19.2 / -22.5 | -178 / -1,537 | 366 / 1,586 | no / no |
| Fixed stop 2 ATR, target 2 ATR | 3,539 / 3,909 | -0.13 / -0.04 (± 0.19 / 0.21) | 50 / 49 | -38.5 / -45.0 | -21.3 / -26.4 | 1 / 1 | -38.5 / -45.0 | +163 / +408 | 490 / 388 | no / no |
| Fixed stop 1 ATR, target 2 ATR | 3,539 / 3,909 | -0.07 / -0.31 (± 0.12 / 0.13) | 33 / 31 | -19.2 / -22.5 | -11.1 / -13.9 | 1 / 1 | -19.2 / -22.5 | -314 / -356 | 328 / 530 | no / no |
| Fixed stop 2 ATR, target 1 ATR | 3,539 / 3,909 | -0.03 / -0.30 (± 0.11 / 0.15) | 67 / 64 | -37.2 / -38.8 | -19.7 / -24.3 | 1 / 1 | -37.2 / -38.8 | +78 / -984 | 325 / 1,039 | no / no |
| Fixed stop $20, target $20 (the V2 exit) | 3,539 / 3,909 | +0.12 / -0.40 (± 0.36 / 0.34) | 50 / 49 | -20.1 / -20.5 | -20.0 / -20.0 | 1 / 1 | -20.1 / -20.5 | +69 / +122 | 667 / 423 | no / no |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |  |  |  |  |  |  |  |  |
| Live ladder, no stop | 3,539 / 3,909 | +1.00 / -3.07 (± 0.00 / 2.33) | 100 / 100 | +1.0 / -7,091 | +1.0 / +1.0 | 32 / 32 | -1,358 / -9,594 | +3,081 / -2,000 | 1,358 / 2,037 | no / 2024-02-07, one basket |
| Live ladder, basket stop $60 | 3,539 / 3,909 | -0.46 / -1.75 (± 0.15 / 0.22) | 98 / 95 | -60.0 / -62.9 | -60.0 / -60.0 | 32 / 32 | -60.0 / -62.9 | -1,733 / -2,000 | 1,850 / 2,020 | no / 2024-06-11, many losses |
| Live ladder, basket stop $200 | 3,539 / 3,909 | +0.21 / -1.98 (± 0.20 / 0.37) | 100 / 99 | -200 / -200 | +1.0 / -200 | 32 / 32 | -200 / -200 | +338 / -2,000 | 490 / 2,037 | no / 2024-04-30, many losses |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |  |  |  |  |  |  |  |  |
| Budget 1 R, no add | 3,539 / 3,909 | -0.01 / -0.40 (± 0.05 / 0.07) | 66 / 61 | -19.2 / -22.5 | -10.0 / -13.0 | 1 / 1 | -19.2 / -22.5 | -44 / -1,558 | 199 / 1,614 | no / no |
| Budget 1 R, 2 adds 0.17 ATR apart | 3,539 / 3,909 | -0.20 / -0.80 (± 0.08 / 0.11) | 51 / 45 | -19.2 / -22.5 | -10.4 / -13.2 | 3 / 3 | -19.2 / -22.5 | -697 / -2,000 | 834 / 2,000 | no / 2024-10-17, many losses |
| Budget 2 R, no add | 3,539 / 3,909 | -0.04 / -0.27 (± 0.08 / 0.12) | 80 / 77 | -37.2 / -38.8 | -18.1 / -21.3 | 1 / 1 | -37.2 / -38.8 | -87 / -694 | 314 / 913 | no / no |
| Budget 2 R, 2 adds 0.33 ATR apart | 3,539 / 3,909 | -0.01 / -0.80 (± 0.13 / 0.15) | 71 / 66 | -37.2 / -45.0 | -19.1 / -24.5 | 3 / 3 | -37.2 / -45.0 | -48 / -2,000 | 380 / 2,000 | no / 2024-09-17, many losses |
| Budget 3 R, no add | 3,539 / 3,909 | -0.08 / -0.36 (± 0.10 / 0.14) | 85 / 83 | -45.9 / -58.1 | -25.6 / -30.1 | 1 / 1 | -45.9 / -58.1 | +13 / -547 | 429 / 740 | no / no |
| Budget 3 R, 1 add 1 ATR apart | 3,539 / 3,909 | -0.14 / -0.34 (± 0.12 / 0.16) | 83 / 80 | -55.9 / -58.1 | -26.3 / -30.6 | 2 / 2 | -55.9 / -58.1 | -662 / -710 | 979 / 1,201 | no / no |
| Budget 3 R, 2 adds 0.5 ATR apart | 3,539 / 3,909 | +0.01 / -0.64 (± 0.13 / 0.17) | 80 / 76 | -43.8 / -67.5 | -25.7 / -32.0 | 3 / 3 | -43.8 / -67.5 | -144 / -2,000 | 520 / 2,036 | no / 2025-04-25, many losses |
| Budget 3 R, 3 adds 0.3 ATR apart | 3,539 / 3,909 | -0.03 / -0.93 (± 0.17 / 0.19) | 76 / 71 | -45.4 / -67.5 | -27.0 / -34.4 | 4 / 4 | -45.4 / -67.5 | -98 / -2,000 | 516 / 2,000 | no / 2024-10-10, many losses |
| Budget 3 R, 4 adds 0.2 ATR apart | 3,539 / 3,909 | +0.03 / -1.14 (± 0.19 / 0.21) | 73 / 67 | -55.9 / -67.5 | -27.8 / -36.3 | 5 / 5 | -55.9 / -67.5 | +100 / -2,000 | 472 / 2,000 | no / 2024-05-14, many losses |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 3,539 / 3,909 | +0.01 / -0.64 (± 0.13 / 0.17) | 80 / 76 | -43.8 / -60.0 | -25.7 / -32.0 | 3 / 3 | -43.8 / -60.0 | -144 / -2,000 | 520 / 2,036 | no / 2025-04-25, many losses |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 3,539 / 3,909 | +0.01 / -0.64 (± 0.13 / 0.17) | 80 / 76 | -43.8 / -60.0 | -25.7 / -32.0 | 3 / 3 | -43.8 / -60.0 | -144 / -2,000 | 520 / 2,036 | no / 2025-04-25, many losses |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 3,539 / 3,909 | +0.01 / -0.64 (± 0.13 / 0.17) | 80 / 76 | -43.8 / -60.0 | -25.7 / -32.0 | 3 / 3 | -43.8 / -60.0 | -144 / -2,000 | 520 / 2,036 | no / 2025-04-25, many losses |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |  |  |  |  |  |  |  |  |
| Add when the M5 MACD histogram turns | 3,539 / 3,909 | -0.10 / -0.52 (± 0.12 / 0.17) | 83 / 79 | -55.9 / -54.8 | -26.1 / -31.6 | 3 / 3 | -55.9 / -63.9 | -260 / -1,464 | 484 / 1,495 | no / no |
| Add when the M15 MACD histogram turns | 3,539 / 3,909 | -0.13 / -0.32 (± 0.12 / 0.15) | 83 / 81 | -55.9 / -54.8 | -26.4 / -30.1 | 3 / 3 | -55.9 / -61.0 | -301 / -677 | 648 / 1,225 | no / no |
| Add when the M5 RSI comes back through 35 / 65 | 3,539 / 3,909 | -0.09 / -0.43 (± 0.11 / 0.16) | 83 / 81 | -55.9 / -58.1 | -25.6 / -31.2 | 3 / 3 | -55.9 / -63.9 | -330 / -1,004 | 567 / 1,476 | no / no |
| Add when the M15 RSI comes back through 35 / 65 | 3,539 / 3,909 | -0.16 / -0.39 (± 0.11 / 0.15) | 84 / 82 | -55.9 / -58.1 | -26.0 / -30.9 | 3 / 3 | -55.9 / -59.2 | -341 / -724 | 698 / 793 | no / no |
| **Stops that follow the price (single position)** |  |  |  |  |  |  |  |  |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 3,539 / 3,909 | -0.04 / -0.40 (± 0.06 / 0.08) | 33 / 31 | -19.2 / -22.5 | -10.0 / -13.0 | 1 / 1 | -19.2 / -22.5 | -156 / -1,567 | 279 / 1,637 | no / no |
| Break-even at +1 ATR (stop 1, target 2) | 3,539 / 3,909 | -0.07 / -0.43 (± 0.11 / 0.11) | 25 / 23 | -19.2 / -22.5 | -10.6 / -13.8 | 1 / 1 | -19.2 / -22.5 | -307 / -1,251 | 392 / 1,300 | no / no |
| Trailing stop 1 ATR, no target | 3,539 / 3,909 | +0.02 / -0.48 (± 0.10 / 0.09) | 37 / 34 | -15.8 / -18.4 | -8.3 / -10.9 | 1 / 1 | -17.7 / -18.4 | -144 / -1,234 | 332 / 1,306 | no / no |
| Trailing stop 2 ATR, no target | 3,539 / 3,909 | -0.10 / -0.35 (± 0.21 / 0.23) | 37 / 36 | -29.8 / -37.7 | -16.8 / -19.9 | 1 / 1 | -31.1 / -38.8 | -253 / +147 | 561 / 288 | no / no |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 3,539 / 3,909 | -0.06 / -0.41 (± 0.09 / 0.09) | 50 / 46 | -19.2 / -22.5 | -10.6 / -13.8 | 1 / 1 | -19.2 / -22.5 | -270 / -830 | 382 / 993 | no / no |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |  |  |  |  |  |  |  |  |
| Pyramid, 2 adds | 3,539 / 3,909 | +0.02 / -0.77 (± 0.19 / 0.18) | 22 / 20 | -15.8 / -18.4 | -8.7 / -11.4 | 3 / 3 | -17.7 / -18.4 | -124 / -2,000 | 605 / 2,000 | no / 2025-05-05, many losses |
| Pyramid, 4 adds | 3,539 / 3,909 | +0.02 / -0.81 (± 0.20 / 0.20) | 22 / 20 | -15.8 / -18.4 | -8.7 / -11.4 | 5 / 5 | -17.7 / -18.4 | -117 / -2,000 | 643 / 2,000 | no / 2025-04-01, many losses |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |  |  |  |  |  |  |  |  |
| Hedge lock, unlocked by the next vote signal | 3,539 / 3,909 | -0.14 / -0.60 (± 0.14 / 0.15) | 62 / 61 | -37.9 / -42.7 | -18.7 / -23.6 | 2 / 2 | -37.9 / -42.7 | -178 / -1,538 | 366 / 1,587 | no / no |
| Close at -1 ATR, re-enter on the next vote signal | 3,539 / 3,909 | -0.14 / -0.60 (± 0.14 / 0.15) | 62 / 60 | -37.9 / -42.7 | -18.7 / -23.6 | 1 / 1 | -37.9 / -42.7 | -178 / -1,537 | 366 / 1,586 | no / no |
| Hedge lock, both legs closed 4 h later | 3,539 / 3,909 | -0.12 / -0.57 (± 0.08 / 0.10) | 50 / 46 | -19.4 / -22.8 | -10.8 / -14.1 | 2 / 2 | -20.4 / -22.8 | +249 / -834 | 121 / 886 | no / no |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |  |  |  |  |  |  |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 3,539 / 3,909 | -0.67 / -2.33 (± 0.38 / 0.50) | 93 / 91 | -237 / -247 | -109 / -127 | 22 / 22 | -251 / -258 | -1,014 / -2,000 | 1,439 / 2,027 | no / 2024-06-18, many losses |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 3,539 / 3,909 | -1.22 / -2.50 (± 0.20 / 0.32) | 77 / 74 | -79.5 / -83.3 | -38.9 / -48.6 | 12.9 / 12.9 | -79.5 / -89.6 | -2,000 / -2,000 | 2,056 / 2,003 | 2026-05-30, many losses / 2024-04-30, many losses |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |  |  |  |  |  |  |  |  |
| Stop and reverse, same size | 3,539 / 3,909 | -0.10 / -0.66 (± 0.10 / 0.11) | 50 / 46 | -38.5 / -45.0 | -18.1 / -25.2 | 1 / 1 | -38.5 / -45.0 | +17 / -1,876 | 384 / 1,898 | no / no |
| Stop and reverse, double size | 3,539 / 3,909 | -0.15 / -0.94 (± 0.14 / 0.16) | 74 / 71 | -57.7 / -67.5 | -27.1 / -37.8 | 2 / 2 | -57.7 / -67.5 | -19 / -2,000 | 683 / 2,012 | no / 2025-02-10, many losses |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |  |  |  |  |  |  |  |  |
| Martingale: double after a loss, up to x8 | 3,539 / 3,909 | -0.41 / -1.25 (± 0.35 / 0.34) | 50 / 46 | -154 / -180 | -56.6 / -67.4 | 8 / 8 | -154 / -180 | -1,461 / -2,000 | 1,923 / 2,023 | no / 2024-04-24, many losses |
| Anti-martingale: double after a win, up to x8 | 3,539 / 3,909 | +0.11 / -0.84 (± 0.32 / 0.32) | 50 / 46 | -138 / -122 | -55.7 / -65.5 | 8 / 8 | -138 / -122 | +393 / -2,000 | 1,055 / 2,003 | no / 2024-10-25, many losses |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |  |  |  |  |  |  |  |  |
| Daily loss limit 1 R | 1,475 / 1,433 | -0.31 / -0.43 (± 0.14 / 0.19) | 48 / 46 | -19.2 / -20.2 | -11.1 / -13.3 | 1 / 1 | -19.2 / -20.2 | -457 / -619 | 547 / 676 | no / no |
| Daily loss limit 2 R | 2,477 / 2,495 | -0.13 / -0.41 (± 0.10 / 0.12) | 49 / 46 | -19.2 / -20.2 | -10.6 / -14.3 | 1 / 1 | -19.2 / -20.2 | -327 / -1,015 | 420 / 1,069 | no / no |
<!-- /table -->

### BTC, random entries

<!-- table main:BTCUSDm:random -->
Entries: 3,396 / 3,716. One R (the ATR of the entry hour on 0.01 lot): median $4.74 / $5.27, 95th percentile $9.11 / $11.41, largest $19.25 / $22.49. Every cell is DEV / CONFIRM; amounts in USD for a base size of 0.01 lot; position in units of 0.01 lot.

| Mechanism | Baskets | Expectancy per entry (± s.e.) | Win % | Worst basket | 1st percentile | Largest position held | Worst floating loss | $2,000 account: result | deepest drawdown | emptied |
|---|---|---|---|---|---|---|---|---|---|---|
| **Single position, fixed stop and target** |  |  |  |  |  |  |  |  |  |  |
| Fixed stop 1 ATR, target 1 ATR (reference) | 3,396 / 3,716 | -0.19 / -0.10 (± 0.08 / 0.12) | 48 / 48 | -19.2 / -22.5 | -11.0 / -13.1 | 1 / 1 | -19.2 / -22.5 | -656 / -374 | 747 / 664 | no / no |
| Fixed stop 2 ATR, target 2 ATR | 3,396 / 3,716 | -0.13 / -0.10 (± 0.20 / 0.24) | 50 / 49 | -38.5 / -45.0 | -21.3 / -26.4 | 1 / 1 | -38.5 / -45.0 | +32 / -163 | 286 / 645 | no / no |
| Fixed stop 1 ATR, target 2 ATR | 3,396 / 3,716 | -0.18 / -0.02 (± 0.13 / 0.16) | 33 / 32 | -19.2 / -22.5 | -11.2 / -13.6 | 1 / 1 | -19.2 / -22.5 | -494 / -320 | 679 / 647 | no / no |
| Fixed stop 2 ATR, target 1 ATR | 3,396 / 3,716 | -0.06 / -0.01 (± 0.12 / 0.15) | 66 / 65 | -37.2 / -39.7 | -19.9 / -24.2 | 1 / 1 | -37.2 / -39.7 | -84 / +60 | 435 / 310 | no / no |
| Fixed stop $20, target $20 (the V2 exit) | 3,396 / 3,716 | -0.16 / +0.19 (± 0.34 / 0.34) | 50 / 50 | -20.1 / -20.1 | -20.0 / -20.0 | 1 / 1 | -20.1 / -20.1 | -197 / +175 | 574 / 373 | no / no |
| **Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket** |  |  |  |  |  |  |  |  |  |  |
| Live ladder, no stop | 3,396 / 3,716 | -1.61 / -5.29 (± 2.46 / 3.34) | 100 / 100 | -8,365 / -7,247 | +1.0 / +1.0 | 32 / 32 | -10,342 / -8,478 | -2,000 / -2,000 | 2,731 / 2,066 | 2026-01-20, one basket / 2024-02-14, one basket |
| Live ladder, basket stop $60 | 3,396 / 3,716 | -1.14 / -2.00 (± 0.18 / 0.23) | 96 / 95 | -62.1 / -62.4 | -60.0 / -60.0 | 32 / 32 | -62.1 / -62.4 | -2,000 / -2,000 | 2,000 / 2,020 | 2025-12-22, many losses / 2024-06-03, many losses |
| Live ladder, basket stop $200 | 3,396 / 3,716 | -1.19 / -1.97 (± 0.34 / 0.42) | 99 / 98 | -200 / -200 | -200 / -200 | 32 / 32 | -200 / -200 | -2,000 / -2,000 | 2,070 / 2,060 | 2025-12-22, many losses / 2024-05-01, many losses |
| **Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry** |  |  |  |  |  |  |  |  |  |  |
| Budget 1 R, no add | 3,396 / 3,716 | -0.17 / -0.22 (± 0.07 / 0.08) | 65 / 63 | -19.2 / -22.5 | -10.2 / -12.5 | 1 / 1 | -19.2 / -22.5 | -568 / -806 | 611 / 917 | no / no |
| Budget 1 R, 2 adds 0.17 ATR apart | 3,396 / 3,716 | -0.27 / -0.76 (± 0.10 / 0.12) | 50 / 46 | -19.2 / -22.5 | -10.5 / -13.3 | 3 / 3 | -19.2 / -22.5 | -923 / -2,000 | 963 / 2,001 | no / 2024-12-23, many losses |
| Budget 2 R, no add | 3,396 / 3,716 | -0.12 / -0.18 (± 0.09 / 0.12) | 79 / 78 | -37.2 / -38.8 | -18.5 / -22.3 | 1 / 1 | -37.2 / -38.8 | -425 / -253 | 586 / 615 | no / no |
| Budget 2 R, 2 adds 0.33 ATR apart | 3,396 / 3,716 | -0.23 / -0.49 (± 0.12 / 0.14) | 70 / 67 | -33.7 / -45.0 | -19.7 / -24.4 | 3 / 3 | -34.6 / -45.0 | -795 / -1,821 | 991 / 1,911 | no / no |
| Budget 3 R, no add | 3,396 / 3,716 | -0.14 / -0.08 (± 0.11 / 0.15) | 85 / 84 | -50.5 / -58.1 | -26.5 / -29.0 | 1 / 1 | -50.5 / -58.1 | -228 / -424 | 469 / 733 | no / no |
| Budget 3 R, 1 add 1 ATR apart | 3,396 / 3,716 | -0.24 / -0.28 (± 0.14 / 0.15) | 82 / 81 | -55.9 / -58.1 | -27.1 / -31.2 | 2 / 2 | -55.9 / -58.1 | -664 / -440 | 816 / 830 | no / no |
| Budget 3 R, 2 adds 0.5 ATR apart | 3,396 / 3,716 | -0.29 / -0.42 (± 0.15 / 0.15) | 78 / 77 | -50.5 / -67.5 | -27.5 / -32.9 | 3 / 3 | -50.5 / -67.5 | -1,054 / -1,403 | 1,256 / 1,586 | no / no |
| Budget 3 R, 3 adds 0.3 ATR apart | 3,396 / 3,716 | -0.42 / -0.51 (± 0.16 / 0.16) | 74 / 72 | -50.5 / -67.5 | -28.5 / -33.8 | 4 / 4 | -50.5 / -67.5 | -1,161 / -1,820 | 1,350 / 1,965 | no / no |
| Budget 3 R, 4 adds 0.2 ATR apart | 3,396 / 3,716 | -0.36 / -0.69 (± 0.18 / 0.22) | 71 / 68 | -50.5 / -67.5 | -28.9 / -35.8 | 5 / 5 | -51.4 / -67.5 | -1,239 / -2,000 | 1,529 / 2,010 | no / 2024-07-26, many losses |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 3,396 / 3,716 | -0.29 / -0.41 (± 0.15 / 0.15) | 78 / 77 | -50.5 / -60.0 | -27.5 / -32.9 | 3 / 3 | -50.5 / -60.0 | -1,054 / -1,396 | 1,256 / 1,578 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 3,396 / 3,716 | -0.29 / -0.41 (± 0.15 / 0.15) | 78 / 77 | -50.5 / -60.0 | -27.5 / -32.9 | 3 / 3 | -50.5 / -60.0 | -1,054 / -1,396 | 1,256 / 1,578 | no / no |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 3,396 / 3,716 | -0.29 / -0.41 (± 0.15 / 0.15) | 78 / 77 | -50.5 / -60.0 | -27.5 / -32.9 | 3 / 3 | -50.5 / -60.0 | -1,054 / -1,396 | 1,256 / 1,578 | no / no |
| **Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R** |  |  |  |  |  |  |  |  |  |  |
| Add when the M5 MACD histogram turns | 3,396 / 3,716 | -0.30 / -0.26 (± 0.14 / 0.16) | 81 / 80 | -55.9 / -46.1 | -27.5 / -31.9 | 3 / 3 | -55.9 / -62.0 | -1,004 / -601 | 1,134 / 923 | no / no |
| Add when the M15 MACD histogram turns | 3,396 / 3,716 | -0.30 / -0.33 (± 0.13 / 0.17) | 82 / 81 | -55.9 / -46.1 | -27.5 / -30.8 | 3 / 3 | -55.9 / -59.1 | -709 / -796 | 838 / 1,106 | no / no |
| Add when the M5 RSI comes back through 35 / 65 | 3,396 / 3,716 | -0.28 / -0.31 (± 0.14 / 0.15) | 82 / 81 | -55.9 / -58.1 | -27.7 / -31.7 | 3 / 3 | -55.9 / -62.0 | -572 / -656 | 737 / 911 | no / no |
| Add when the M15 RSI comes back through 35 / 65 | 3,396 / 3,716 | -0.15 / -0.32 (± 0.12 / 0.16) | 84 / 82 | -55.9 / -58.1 | -26.7 / -31.7 | 3 / 3 | -55.9 / -58.1 | -320 / -808 | 504 / 1,079 | no / no |
| **Stops that follow the price (single position)** |  |  |  |  |  |  |  |  |  |  |
| Break-even at +0.5 ATR (stop 1, target 1) | 3,396 / 3,716 | -0.18 / -0.20 (± 0.07 / 0.11) | 32 / 31 | -19.2 / -22.5 | -10.2 / -12.5 | 1 / 1 | -19.2 / -22.5 | -596 / -753 | 630 / 895 | no / no |
| Break-even at +1 ATR (stop 1, target 2) | 3,396 / 3,716 | -0.20 / -0.12 (± 0.11 / 0.15) | 24 / 24 | -19.2 / -22.5 | -11.0 / -13.1 | 1 / 1 | -19.2 / -22.5 | -869 / -378 | 952 / 556 | no / no |
| Trailing stop 1 ATR, no target | 3,396 / 3,716 | -0.19 / -0.28 (± 0.08 / 0.12) | 36 / 34 | -13.8 / -18.4 | -8.7 / -10.9 | 1 / 1 | -17.7 / -18.4 | -286 / -400 | 366 / 620 | no / no |
| Trailing stop 2 ATR, no target | 3,396 / 3,716 | -0.11 / +0.14 (± 0.21 / 0.32) | 37 / 37 | -30.1 / -37.7 | -16.8 / -20.1 | 1 / 1 | -31.1 / -37.7 | -626 / +336 | 703 / 248 | no / no |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 3,396 / 3,716 | -0.23 / -0.12 (± 0.08 / 0.13) | 48 / 48 | -19.2 / -22.5 | -11.0 / -13.1 | 1 / 1 | -19.2 / -22.5 | -470 / -174 | 527 / 519 | no / no |
| **Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket** |  |  |  |  |  |  |  |  |  |  |
| Pyramid, 2 adds | 3,396 / 3,716 | -0.30 / -0.45 (± 0.14 / 0.20) | 21 / 20 | -16.1 / -20.1 | -9.2 / -11.3 | 3 / 3 | -17.7 / -20.1 | -502 / -757 | 659 / 1,185 | no / no |
| Pyramid, 4 adds | 3,396 / 3,716 | -0.35 / -0.44 (± 0.14 / 0.22) | 21 / 20 | -16.1 / -20.1 | -9.2 / -11.3 | 5 / 5 | -17.7 / -20.1 | -618 / -817 | 723 / 1,233 | no / no |
| **Hedge lock: at -1 ATR the opposite position is opened instead of closing** |  |  |  |  |  |  |  |  |  |  |
| Hedge lock, unlocked by the next vote signal | 3,396 / 3,716 | -0.19 / -0.28 (± 0.11 / 0.15) | 61 / 62 | -37.9 / -42.3 | -18.6 / -23.1 | 2 / 2 | -37.9 / -42.3 | -380 / -525 | 483 / 773 | no / no |
| Close at -1 ATR, re-enter on the next vote signal | 3,396 / 3,716 | -0.19 / -0.28 (± 0.11 / 0.15) | 61 / 62 | -37.9 / -42.3 | -18.6 / -23.1 | 1 / 1 | -37.9 / -42.3 | -380 / -525 | 483 / 773 | no / no |
| Hedge lock, both legs closed 4 h later | 3,396 / 3,716 | -0.27 / -0.28 (± 0.08 / 0.13) | 48 / 48 | -19.4 / -22.8 | -11.2 / -13.4 | 2 / 2 | -19.5 / -22.8 | -482 / -118 | 548 / 451 | no / no |
| **Zone recovery: alternating, growing opposite positions until one side's target is reached** |  |  |  |  |  |  |  |  |  |  |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 3,396 / 3,716 | -0.60 / -1.31 (± 0.34 / 0.48) | 93 / 92 | -220 / -242 | -107 / -122 | 22 / 22 | -220 / -242 | -1,431 / -2,000 | 1,733 / 2,011 | no / 2025-03-20, many losses |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 3,396 / 3,716 | -1.46 / -2.42 (± 0.19 / 0.26) | 76 / 73 | -79.5 / -82.0 | -40.4 / -48.4 | 12.9 / 12.9 | -79.5 / -82.0 | -2,000 / -2,000 | 2,028 / 2,000 | 2026-02-06, many losses / 2024-05-28, many losses |
| **Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once** |  |  |  |  |  |  |  |  |  |  |
| Stop and reverse, same size | 3,396 / 3,716 | -0.26 / -0.30 (± 0.10 / 0.15) | 48 / 48 | -38.5 / -45.0 | -19.1 / -24.2 | 1 / 1 | -38.5 / -45.0 | -377 / -418 | 518 / 561 | no / no |
| Stop and reverse, double size | 3,396 / 3,716 | -0.33 / -0.51 (± 0.15 / 0.20) | 73 / 72 | -57.7 / -67.5 | -28.7 / -36.3 | 2 / 2 | -57.7 / -67.5 | -468 / -939 | 608 / 1,086 | no / no |
| **Size of the NEXT basket (the reference trade, re-sized by what the last one did)** |  |  |  |  |  |  |  |  |  |  |
| Martingale: double after a loss, up to x8 | 3,396 / 3,716 | -0.46 / -0.23 (± 0.30 / 0.35) | 48 / 48 | -122 / -158 | -55.9 / -65.4 | 8 / 8 | -122 / -158 | -1,576 / -870 | 1,987 / 1,857 | no / no |
| Anti-martingale: double after a win, up to x8 | 3,396 / 3,716 | -0.32 / +0.19 (± 0.29 / 0.51) | 48 / 48 | -135 / -155 | -53.8 / -63.1 | 8 / 8 | -135 / -155 | -1,087 / +710 | 1,752 / 1,790 | no / no |
| **Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)** |  |  |  |  |  |  |  |  |  |  |
| Daily loss limit 1 R | 1,493 / 1,555 | -0.11 / -0.07 (± 0.15 / 0.19) | 49 / 48 | -19.2 / -19.8 | -10.3 / -13.0 | 1 / 1 | -19.2 / -19.8 | -165 / -101 | 288 / 399 | no / no |
| Daily loss limit 2 R | 2,316 / 2,522 | -0.17 / +0.01 (± 0.10 / 0.16) | 48 / 49 | -19.2 / -22.5 | -10.9 / -12.6 | 1 / 1 | -19.2 / -22.5 | -386 / +27 | 446 / 447 | no / no |
<!-- /table -->

## What the numbers say

### 1. Nothing here turns entries without an edge into money

The random list is the test: its entries are coin flips. For each mechanism the table below gives the
units it opens per entry, the spread it pays on them, and its result before and after that spread.

Gold:

<!-- table cost:XAUUSDm -->
| Mechanism | Units opened per entry | Spread paid per entry | Result before spread (± s.e.) | Result after spread |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | 1.00 / 1.00 | 0.23 / 0.18 | +0.41 / -0.07 (± 0.44 / 0.16) | +0.17 / -0.25 |
| Fixed stop 2 ATR, target 2 ATR | 1.00 / 1.00 | 0.24 / 0.18 | +0.47 / +0.16 (± 0.90 / 0.33) | +0.23 / -0.02 |
| Fixed stop 1 ATR, target 2 ATR | 1.00 / 1.00 | 0.23 / 0.18 | +0.71 / +0.04 (± 0.72 / 0.22) | +0.47 / -0.13 |
| Fixed stop 2 ATR, target 1 ATR | 1.00 / 1.00 | 0.23 / 0.18 | +0.25 / -0.05 (± 0.68 / 0.21) | +0.02 / -0.22 |
| Fixed stop $20, target $20 (the V2 exit) | 1.00 / 1.00 | 0.23 / 0.18 | -0.12 / -0.18 (± 0.42 / 0.38) | -0.35 / -0.35 |
| Live ladder, no stop | 4.10 / 4.92 | 0.94 / 0.87 | +1.94 / -9.22 (± 0.05 / 11.11) | +1.00 / -10.09 |
| Live ladder, basket stop $60 | 3.95 / 4.78 | 0.90 / 0.85 | -1.65 / -0.35 (± 0.28 / 0.23) | -2.55 / -1.19 |
| Live ladder, basket stop $200 | 4.04 / 4.88 | 0.92 / 0.87 | -1.10 / +0.10 (± 0.45 / 0.31) | -2.02 / -0.76 |
| Budget 1 R, no add | 1.00 / 1.00 | 0.23 / 0.18 | -0.13 / +0.04 (± 0.34 / 0.11) | -0.36 / -0.14 |
| Budget 1 R, 2 adds 0.17 ATR apart | 2.35 / 2.34 | 0.54 / 0.41 | -0.97 / +0.23 (± 0.36 / 0.16) | -1.51 / -0.18 |
| Budget 2 R, no add | 1.00 / 1.00 | 0.23 / 0.18 | +0.03 / +0.03 (± 0.49 / 0.16) | -0.20 / -0.15 |
| Budget 2 R, 2 adds 0.33 ATR apart | 2.04 / 2.01 | 0.47 / 0.36 | +0.13 / -0.02 (± 0.51 / 0.23) | -0.34 / -0.38 |
| Budget 3 R, no add | 1.00 / 1.00 | 0.23 / 0.18 | -0.31 / -0.08 (± 0.60 / 0.18) | -0.55 / -0.25 |
| Budget 3 R, 1 add 1 ATR apart | 1.34 / 1.34 | 0.31 / 0.24 | -0.02 / -0.13 (± 0.74 / 0.21) | -0.34 / -0.37 |
| Budget 3 R, 2 adds 0.5 ATR apart | 1.83 / 1.81 | 0.43 / 0.32 | +0.52 / +0.23 (± 0.59 / 0.22) | +0.09 / -0.09 |
| Budget 3 R, 3 adds 0.3 ATR apart | 2.42 / 2.37 | 0.56 / 0.42 | +0.83 / -0.01 (± 0.78 / 0.30) | +0.27 / -0.43 |
| Budget 3 R, 4 adds 0.2 ATR apart | 3.09 / 3.00 | 0.72 / 0.53 | -0.06 / -0.17 (± 0.69 / 0.36) | -0.77 / -0.70 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1.82 / 1.81 | 0.42 / 0.32 | +0.17 / +0.19 (± 0.49 / 0.23) | -0.25 / -0.13 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 1.81 / 1.80 | 0.42 / 0.32 | +0.09 / +0.21 (± 0.50 / 0.22) | -0.33 / -0.11 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 1.78 / 1.78 | 0.41 / 0.31 | +0.02 / +0.21 (± 0.52 / 0.20) | -0.39 / -0.10 |
| Add when the M5 MACD histogram turns | 1.45 / 1.42 | 0.33 / 0.25 | +0.38 / -0.10 (± 0.70 / 0.19) | +0.04 / -0.35 |
| Add when the M15 MACD histogram turns | 1.30 / 1.29 | 0.30 / 0.23 | -0.29 / -0.05 (± 0.61 / 0.20) | -0.59 / -0.28 |
| Add when the M5 RSI comes back through 35 / 65 | 1.33 / 1.32 | 0.31 / 0.23 | +0.29 / -0.19 (± 0.57 / 0.18) | -0.02 / -0.42 |
| Add when the M15 RSI comes back through 35 / 65 | 1.17 / 1.17 | 0.27 / 0.21 | -0.16 / +0.00 (± 0.54 / 0.19) | -0.43 / -0.21 |
| Break-even at +0.5 ATR (stop 1, target 1) | 1.00 / 1.00 | 0.23 / 0.18 | -0.08 / +0.12 (± 0.37 / 0.14) | -0.31 / -0.06 |
| Break-even at +1 ATR (stop 1, target 2) | 1.00 / 1.00 | 0.23 / 0.18 | +0.76 / +0.06 (± 0.56 / 0.19) | +0.53 / -0.11 |
| Trailing stop 1 ATR, no target | 1.00 / 1.00 | 0.23 / 0.18 | -0.07 / +0.21 (± 0.46 / 0.20) | -0.30 / +0.03 |
| Trailing stop 2 ATR, no target | 1.00 / 1.00 | 0.23 / 0.18 | +1.32 / +0.46 (± 1.27 / 0.39) | +1.09 / +0.29 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 1.00 / 1.00 | 0.23 / 0.18 | +0.55 / -0.04 (± 0.52 / 0.17) | +0.32 / -0.22 |
| Pyramid, 2 adds | 1.50 / 1.51 | 0.35 / 0.27 | +0.10 / +0.28 (± 0.82 / 0.34) | -0.26 / +0.01 |
| Pyramid, 4 adds | 1.57 / 1.58 | 0.37 / 0.28 | +0.15 / +0.21 (± 0.95 / 0.35) | -0.21 / -0.07 |
| Hedge lock, unlocked by the next vote signal | 1.50 / 1.52 | 0.35 / 0.27 | -0.03 / +0.03 (± 0.53 / 0.20) | -0.38 / -0.24 |
| Close at -1 ATR, re-enter on the next vote signal | 1.50 / 1.52 | 0.35 / 0.27 | -0.03 / +0.03 (± 0.53 / 0.20) | -0.38 / -0.24 |
| Hedge lock, both legs closed 4 h later | 1.50 / 1.52 | 0.35 / 0.27 | +0.41 / -0.07 (± 0.44 / 0.16) | +0.06 / -0.34 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 5.59 / 5.59 | 1.31 / 1.00 | +0.05 / +1.42 (± 1.70 / 0.65) | -1.26 / +0.42 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 6.26 / 6.27 | 1.48 / 1.12 | -0.58 / +0.16 (± 0.83 / 0.35) | -2.06 / -0.96 |
| Stop and reverse, same size | 1.50 / 1.52 | 0.35 / 0.27 | +0.49 / +0.12 (± 0.45 / 0.18) | +0.14 / -0.15 |
| Stop and reverse, double size | 2.00 / 2.04 | 0.47 / 0.36 | +0.58 / +0.31 (± 0.67 / 0.25) | +0.11 / -0.05 |
| Martingale: double after a loss, up to x8 | 2.48 / 2.61 | 0.57 / 0.46 | +1.53 / -0.23 (± 1.64 / 0.52) | +0.95 / -0.69 |
| Anti-martingale: double after a win, up to x8 | 2.47 / 2.35 | 0.58 / 0.42 | +0.25 / -0.53 (± 1.37 / 0.46) | -0.33 / -0.95 |
| Daily loss limit 1 R | 1.00 / 1.00 | 0.23 / 0.18 | +0.41 / -0.09 (± 0.75 / 0.28) | +0.18 / -0.27 |
| Daily loss limit 2 R | 1.00 / 1.00 | 0.23 / 0.18 | +0.24 / -0.05 (± 0.56 / 0.19) | +0.01 / -0.22 |
<!-- /table -->

BTC:

<!-- table cost:BTCUSDm -->
| Mechanism | Units opened per entry | Spread paid per entry | Result before spread (± s.e.) | Result after spread |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | 1.00 / 1.00 | 0.14 / 0.34 | -0.05 / +0.24 (± 0.08 / 0.12) | -0.19 / -0.10 |
| Fixed stop 2 ATR, target 2 ATR | 1.00 / 1.00 | 0.14 / 0.34 | +0.01 / +0.24 (± 0.20 / 0.24) | -0.13 / -0.10 |
| Fixed stop 1 ATR, target 2 ATR | 1.00 / 1.00 | 0.14 / 0.34 | -0.04 / +0.31 (± 0.13 / 0.16) | -0.18 / -0.02 |
| Fixed stop 2 ATR, target 1 ATR | 1.00 / 1.00 | 0.14 / 0.34 | +0.09 / +0.33 (± 0.12 / 0.15) | -0.06 / -0.01 |
| Fixed stop $20, target $20 (the V2 exit) | 1.00 / 1.00 | 0.14 / 0.34 | -0.02 / +0.53 (± 0.34 / 0.34) | -0.16 / +0.19 |
| Live ladder, no stop | 5.42 / 5.57 | 0.77 / 1.91 | -0.83 / -3.38 (± 2.45 / 3.31) | -1.61 / -5.29 |
| Live ladder, basket stop $60 | 5.22 / 5.33 | 0.75 / 1.81 | -0.39 / -0.19 (± 0.17 / 0.21) | -1.14 / -2.00 |
| Live ladder, basket stop $200 | 5.38 / 5.50 | 0.77 / 1.88 | -0.42 / -0.10 (± 0.33 / 0.38) | -1.19 / -1.97 |
| Budget 1 R, no add | 1.00 / 1.00 | 0.14 / 0.34 | -0.02 / +0.12 (± 0.07 / 0.08) | -0.17 / -0.22 |
| Budget 1 R, 2 adds 0.17 ATR apart | 2.36 / 2.38 | 0.34 / 0.80 | +0.07 / +0.04 (± 0.10 / 0.12) | -0.27 / -0.76 |
| Budget 2 R, no add | 1.00 / 1.00 | 0.14 / 0.34 | +0.03 / +0.15 (± 0.09 / 0.12) | -0.12 / -0.18 |
| Budget 2 R, 2 adds 0.33 ATR apart | 2.03 / 2.07 | 0.29 / 0.70 | +0.06 / +0.21 (± 0.12 / 0.13) | -0.23 / -0.49 |
| Budget 3 R, no add | 1.00 / 1.00 | 0.14 / 0.34 | +0.00 / +0.26 (± 0.11 / 0.14) | -0.14 / -0.08 |
| Budget 3 R, 1 add 1 ATR apart | 1.35 / 1.36 | 0.19 / 0.46 | -0.04 / +0.18 (± 0.14 / 0.14) | -0.24 / -0.28 |
| Budget 3 R, 2 adds 0.5 ATR apart | 1.82 / 1.85 | 0.26 / 0.63 | -0.03 / +0.22 (± 0.15 / 0.14) | -0.29 / -0.42 |
| Budget 3 R, 3 adds 0.3 ATR apart | 2.39 / 2.46 | 0.35 / 0.84 | -0.08 / +0.33 (± 0.16 / 0.15) | -0.42 / -0.51 |
| Budget 3 R, 4 adds 0.2 ATR apart | 3.05 / 3.13 | 0.44 / 1.06 | +0.08 / +0.37 (± 0.18 / 0.20) | -0.36 / -0.69 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1.82 / 1.85 | 0.26 / 0.63 | -0.03 / +0.22 (± 0.15 / 0.14) | -0.29 / -0.41 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 1.82 / 1.85 | 0.26 / 0.63 | -0.03 / +0.22 (± 0.15 / 0.14) | -0.29 / -0.41 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 1.82 / 1.85 | 0.26 / 0.63 | -0.03 / +0.22 (± 0.15 / 0.14) | -0.29 / -0.41 |
| Add when the M5 MACD histogram turns | 1.42 / 1.44 | 0.20 / 0.49 | -0.09 / +0.23 (± 0.14 / 0.15) | -0.30 / -0.26 |
| Add when the M15 MACD histogram turns | 1.28 / 1.30 | 0.19 / 0.44 | -0.11 / +0.12 (± 0.13 / 0.17) | -0.30 / -0.33 |
| Add when the M5 RSI comes back through 35 / 65 | 1.32 / 1.34 | 0.19 / 0.45 | -0.09 / +0.14 (± 0.14 / 0.15) | -0.28 / -0.31 |
| Add when the M15 RSI comes back through 35 / 65 | 1.17 / 1.18 | 0.17 / 0.40 | +0.02 / +0.07 (± 0.12 / 0.15) | -0.15 / -0.32 |
| Break-even at +0.5 ATR (stop 1, target 1) | 1.00 / 1.00 | 0.14 / 0.34 | -0.03 / +0.13 (± 0.07 / 0.10) | -0.18 / -0.20 |
| Break-even at +1 ATR (stop 1, target 2) | 1.00 / 1.00 | 0.14 / 0.34 | -0.05 / +0.22 (± 0.11 / 0.15) | -0.20 / -0.12 |
| Trailing stop 1 ATR, no target | 1.00 / 1.00 | 0.14 / 0.34 | -0.04 / +0.06 (± 0.08 / 0.12) | -0.19 / -0.28 |
| Trailing stop 2 ATR, no target | 1.00 / 1.00 | 0.14 / 0.34 | +0.03 / +0.48 (± 0.21 / 0.32) | -0.11 / +0.14 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 1.00 / 1.00 | 0.14 / 0.34 | -0.08 / +0.22 (± 0.08 / 0.13) | -0.23 / -0.12 |
| Pyramid, 2 adds | 1.50 / 1.51 | 0.22 / 0.51 | -0.08 / +0.07 (± 0.14 / 0.20) | -0.30 / -0.45 |
| Pyramid, 4 adds | 1.57 / 1.57 | 0.23 / 0.54 | -0.13 / +0.09 (± 0.14 / 0.22) | -0.35 / -0.44 |
| Hedge lock, unlocked by the next vote signal | 1.52 / 1.52 | 0.22 / 0.52 | +0.03 / +0.24 (± 0.11 / 0.15) | -0.19 / -0.28 |
| Close at -1 ATR, re-enter on the next vote signal | 1.52 / 1.52 | 0.22 / 0.52 | +0.03 / +0.24 (± 0.11 / 0.15) | -0.19 / -0.28 |
| Hedge lock, both legs closed 4 h later | 1.52 / 1.52 | 0.22 / 0.51 | -0.05 / +0.24 (± 0.08 / 0.12) | -0.27 / -0.28 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | 5.69 / 5.98 | 0.83 / 2.06 | +0.22 / +0.75 (± 0.33 / 0.45) | -0.60 / -1.31 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | 6.48 / 6.84 | 0.94 / 2.35 | -0.52 / -0.07 (± 0.18 / 0.22) | -1.46 / -2.42 |
| Stop and reverse, same size | 1.52 / 1.52 | 0.22 / 0.52 | -0.04 / +0.21 (± 0.10 / 0.15) | -0.26 / -0.30 |
| Stop and reverse, double size | 2.03 / 2.04 | 0.29 / 0.70 | -0.04 / +0.19 (± 0.15 / 0.20) | -0.33 / -0.51 |
| Martingale: double after a loss, up to x8 | 2.62 / 2.64 | 0.38 / 0.91 | -0.08 / +0.68 (± 0.29 / 0.33) | -0.46 / -0.23 |
| Anti-martingale: double after a win, up to x8 | 2.44 / 2.39 | 0.35 / 0.81 | +0.03 / +1.00 (± 0.30 / 0.53) | -0.32 / +0.19 |
| Daily loss limit 1 R | 1.00 / 1.00 | 0.14 / 0.33 | +0.03 / +0.26 (± 0.15 / 0.19) | -0.11 / -0.07 |
| Daily loss limit 2 R | 1.00 / 1.00 | 0.14 / 0.33 | -0.02 / +0.34 (± 0.10 / 0.15) | -0.17 / +0.01 |
<!-- /table -->

Before the spread, the results of the mechanisms with a bounded loss scatter around zero: more than
two standard errors away are 3 of 41 on gold DEV, 1 of 41 on gold CONFIRM, 2 of 41 on BTC DEV and 4
of 41 on BTC CONFIRM (all rows of a table share one random list, so they move together: on BTC
CONFIRM that list came out 1.9 standard errors lucky for the reference itself). After the spread a
mechanism is worse than the reference roughly in proportion to the units it opens: the reference pays
$0.14 to $0.34 per entry, a two-add ladder about twice that, the live ladder two to six times and
zone recovery five to seven times.

The paired comparisons say the same more sharply. Each mechanism has a comparison row (for a ladder,
the single position with the same budget and target; for most others, the reference), and the
difference is taken entry by entry:

- 468 comparisons (39 mechanisms x 12 cells; the no-stop ladder and the timed lock are discussed
  separately). Beyond two standard errors: 68 on the losing side, 9 on the winning side.
- The 9 winners do not repeat. The largest, martingale sizing on gold with the trend (+3.39 ± 1.08 on
  DEV), is -0.15 ± 0.81 on CONFIRM. Three of them are the daily loss limit on BTC lists that lose
  money, where trading less loses less.
- The losers do repeat: the live ladder with a stop, zone recovery, and on BTC CONFIRM (spread 6 % of
  R) nearly every mechanism that adds. Across the 36 mechanisms that have a bounded loss and take
  every entry, the change in expectancy against the comparison row equals the extra spread paid times
  -1.15 (correlation -0.69 over 432 values; -0.86 without zone recovery and the live ladder with a
  stop, the two whose results depend most on how a bar is read). On BTC CONFIRM alone the mean change
  is -$0.35 where the mean extra spread is $0.33.

<details><summary>The change against the comparison row, all six lists</summary>

Gold, with the H1 trend:

<!-- table change:XAUUSDm:trend -->
| Mechanism | Compared with | Change in expectancy per entry (± s.e.) |
|---|---|---|
| Fixed stop 2 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -1.46 / -0.03 (± 2.04 / 0.43) |
| Fixed stop 1 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -0.15 / -0.05 (± 1.05 / 0.18) |
| Fixed stop 2 ATR, target 1 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -0.05 / +0.10 (± 0.67 / 0.28) |
| Fixed stop $20, target $20 (the V2 exit) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.73 / +0.77 (± 0.55 / 0.74) |
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | +0.54 / +1.09 (± 0.57 / 0.23) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.90 / -0.20 (± 0.59 / 0.24) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.61 / -0.38 (± 0.60 / 0.39) |
| Budget 1 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.25 / -0.16 (± 0.35 / 0.14) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | +0.07 / -0.29 (± 0.47 / 0.16) |
| Budget 2 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.03 / -0.06 (± 0.61 / 0.21) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | -0.52 / -0.42 (± 0.54 / 0.21) |
| Budget 3 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.03 / -0.14 (± 0.78 / 0.28) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | -0.03 / -0.24 (± 0.45 / 0.19) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.01 / -0.21 (± 0.69 / 0.27) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | -1.41 / -0.37 (± 0.74 / 0.31) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | -0.34 / -0.78 (± 1.04 / 0.36) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.22 / -0.31 (± 0.86 / 0.28) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.12 / -0.03 (± 0.16 / 0.06) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.07 / -0.05 (± 0.28 / 0.14) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | +0.02 / -0.17 (± 0.54 / 0.18) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | +0.63 / +0.02 (± 0.45 / 0.17) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | +0.45 / -0.16 (± 0.48 / 0.18) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | +0.46 / -0.02 (± 0.35 / 0.19) |
| Break-even at +0.5 ATR (stop 1, target 1) | Fixed stop 1 ATR, target 1 ATR (reference) | -0.11 / -0.13 (± 0.31 / 0.09) |
| Break-even at +1 ATR (stop 1, target 2) | Fixed stop 1 ATR, target 2 ATR | -0.24 / -0.01 (± 0.66 / 0.13) |
| Trailing stop 1 ATR, no target | Fixed stop 1 ATR, target 1 ATR (reference) | +0.20 / -0.12 (± 0.63 / 0.18) |
| Trailing stop 2 ATR, no target | Fixed stop 2 ATR, target 2 ATR | +1.10 / +0.47 (± 1.10 / 0.51) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | Trailing stop 1 ATR, no target | +0.15 / -0.00 (± 0.39 / 0.12) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | +0.54 / -0.42 (± 0.71 / 0.22) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | +0.71 / -0.48 (± 0.89 / 0.25) |
| Hedge lock, unlocked by the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.23 / +0.02 (± 0.34 / 0.20) |
| Close at -1 ATR, re-enter on the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.23 / +0.02 (± 0.34 / 0.20) |
| Hedge lock, both legs closed 4 h later | Fixed stop 1 ATR, target 1 ATR (reference) | -0.11 / -0.09 (± 0.00 / 0.00) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | -2.56 / -0.15 (± 2.27 / 1.02) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | -2.27 / -0.72 (± 1.28 / 0.49) |
| Stop and reverse, same size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.25 / -0.04 (± 0.45 / 0.21) |
| Stop and reverse, double size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.49 / -0.09 (± 0.90 / 0.42) |
| Martingale: double after a loss, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | +3.39 / -0.15 (± 1.08 / 0.80) |
| Anti-martingale: double after a win, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | +0.22 / +0.07 (± 1.73 / 0.61) |
| Daily loss limit 1 R | Fixed stop 1 ATR, target 1 ATR (reference) | -0.51 / +0.02 (± 0.36 / 0.16) |
| Daily loss limit 2 R | Fixed stop 1 ATR, target 1 ATR (reference) | -0.51 / -0.08 (± 0.27 / 0.12) |
<!-- /table -->

Gold, votes only:

<!-- table change:XAUUSDm:votes -->
| Mechanism | Compared with | Change in expectancy per entry (± s.e.) |
|---|---|---|
| Fixed stop 2 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -0.56 / -0.34 (± 0.94 / 0.25) |
| Fixed stop 1 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.45 / -0.08 (± 0.52 / 0.14) |
| Fixed stop 2 ATR, target 1 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -0.64 / -0.21 (± 0.49 / 0.15) |
| Fixed stop $20, target $20 (the V2 exit) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.24 / -0.49 (± 0.31 / 0.38) |
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | -4.01 / -12.46 (± 5.40 / 13.55) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.57 / -0.59 (± 0.44 / 0.20) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.38 / -0.18 (± 0.55 / 0.29) |
| Budget 1 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.29 / -0.09 (± 0.36 / 0.09) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | +0.21 / -0.36 (± 0.32 / 0.12) |
| Budget 2 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.22 / -0.29 (± 0.62 / 0.14) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | -0.04 / -0.09 (± 0.53 / 0.18) |
| Budget 3 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.03 / -0.54 (± 0.79 / 0.22) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | -0.45 / -0.09 (± 0.36 / 0.12) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.27 / +0.10 (± 0.61 / 0.18) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | -0.62 / +0.07 (± 0.73 / 0.25) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | -0.15 / -0.23 (± 0.94 / 0.28) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.46 / +0.11 (± 0.73 / 0.18) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.21 / -0.01 (± 0.13 / 0.04) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.30 / +0.05 (± 0.25 / 0.09) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | -0.53 / -0.10 (± 0.41 / 0.17) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | +0.24 / +0.06 (± 0.32 / 0.13) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | +0.07 / -0.04 (± 0.32 / 0.12) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | +0.55 / +0.07 (± 0.24 / 0.12) |
| Break-even at +0.5 ATR (stop 1, target 1) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.27 / -0.06 (± 0.30 / 0.07) |
| Break-even at +1 ATR (stop 1, target 2) | Fixed stop 1 ATR, target 2 ATR | -0.28 / +0.08 (± 0.46 / 0.09) |
| Trailing stop 1 ATR, no target | Fixed stop 1 ATR, target 1 ATR (reference) | -0.39 / -0.13 (± 0.51 / 0.13) |
| Trailing stop 2 ATR, no target | Fixed stop 2 ATR, target 2 ATR | +0.97 / +0.13 (± 0.88 / 0.29) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | Trailing stop 1 ATR, no target | +0.40 / +0.06 (± 0.42 / 0.10) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | -0.70 / -0.42 (± 0.41 / 0.13) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | -0.76 / -0.50 (± 0.52 / 0.15) |
| Hedge lock, unlocked by the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.05 / +0.02 (± 0.38 / 0.12) |
| Close at -1 ATR, re-enter on the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.05 / +0.02 (± 0.38 / 0.12) |
| Hedge lock, both legs closed 4 h later | Fixed stop 1 ATR, target 1 ATR (reference) | -0.12 / -0.09 (± 0.00 / 0.00) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | +0.51 / -0.15 (± 1.84 / 0.83) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | -1.57 / -0.69 (± 0.94 / 0.38) |
| Stop and reverse, same size | Fixed stop 1 ATR, target 1 ATR (reference) | +0.33 / +0.18 (± 0.37 / 0.13) |
| Stop and reverse, double size | Fixed stop 1 ATR, target 1 ATR (reference) | +0.66 / +0.36 (± 0.74 / 0.26) |
| Martingale: double after a loss, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.47 / -0.09 (± 0.96 / 0.45) |
| Anti-martingale: double after a win, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.60 / -0.26 (± 1.12 / 0.43) |
| Daily loss limit 1 R | Fixed stop 1 ATR, target 1 ATR (reference) | +0.11 / -0.04 (± 0.35 / 0.12) |
| Daily loss limit 2 R | Fixed stop 1 ATR, target 1 ATR (reference) | +0.05 / +0.08 (± 0.25 / 0.08) |
<!-- /table -->

Gold, random:

<!-- table change:XAUUSDm:random -->
| Mechanism | Compared with | Change in expectancy per entry (± s.e.) |
|---|---|---|
| Fixed stop 2 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.06 / +0.23 (± 0.70 / 0.28) |
| Fixed stop 1 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.30 / +0.12 (± 0.50 / 0.13) |
| Fixed stop 2 ATR, target 1 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -0.15 / +0.03 (± 0.42 / 0.13) |
| Fixed stop $20, target $20 (the V2 exit) | Fixed stop 1 ATR, target 1 ATR (reference) | -0.52 / -0.10 (± 0.46 / 0.33) |
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | +0.83 / -9.84 (± 0.44 / 11.10) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | -2.72 / -0.94 (± 0.53 / 0.27) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | -2.20 / -0.51 (± 0.67 / 0.39) |
| Budget 1 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.53 / +0.11 (± 0.32 / 0.11) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | -1.15 / -0.04 (± 0.33 / 0.13) |
| Budget 2 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.38 / +0.10 (± 0.40 / 0.16) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | -0.14 / -0.23 (± 0.39 / 0.19) |
| Budget 3 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.72 / -0.00 (± 0.51 / 0.18) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | +0.21 / -0.11 (± 0.51 / 0.15) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | +0.64 / +0.16 (± 0.45 / 0.17) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | +0.82 / -0.17 (± 0.68 / 0.24) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | -0.23 / -0.44 (± 0.57 / 0.32) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | +0.29 / +0.12 (± 0.53 / 0.17) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.07 / +0.03 (± 0.16 / 0.05) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.12 / +0.03 (± 0.22 / 0.10) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | +0.59 / -0.10 (± 0.53 / 0.13) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | -0.04 / -0.03 (± 0.39 / 0.13) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | +0.53 / -0.17 (± 0.39 / 0.15) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | +0.12 / +0.05 (± 0.27 / 0.10) |
| Break-even at +0.5 ATR (stop 1, target 1) | Fixed stop 1 ATR, target 1 ATR (reference) | -0.48 / +0.19 (± 0.22 / 0.08) |
| Break-even at +1 ATR (stop 1, target 2) | Fixed stop 1 ATR, target 2 ATR | +0.06 / +0.02 (± 0.33 / 0.09) |
| Trailing stop 1 ATR, no target | Fixed stop 1 ATR, target 1 ATR (reference) | -0.48 / +0.28 (± 0.39 / 0.15) |
| Trailing stop 2 ATR, no target | Fixed stop 2 ATR, target 2 ATR | +0.86 / +0.30 (± 0.86 / 0.35) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | Trailing stop 1 ATR, no target | +0.62 / -0.25 (± 0.29 / 0.12) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | +0.05 / -0.02 (± 0.43 / 0.16) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | +0.09 / -0.10 (± 0.57 / 0.18) |
| Hedge lock, unlocked by the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | -0.56 / +0.01 (± 0.26 / 0.13) |
| Close at -1 ATR, re-enter on the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | -0.56 / +0.01 (± 0.26 / 0.13) |
| Hedge lock, both legs closed 4 h later | Fixed stop 1 ATR, target 1 ATR (reference) | -0.11 / -0.09 (± 0.00 / 0.00) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | -1.44 / +0.67 (± 1.77 / 0.68) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | -2.23 / -0.71 (± 0.86 / 0.38) |
| Stop and reverse, same size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.03 / +0.10 (± 0.34 / 0.11) |
| Stop and reverse, double size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.06 / +0.20 (± 0.69 / 0.22) |
| Martingale: double after a loss, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | +0.78 / -0.44 (± 1.35 / 0.42) |
| Anti-martingale: double after a win, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.50 / -0.70 (± 1.06 / 0.34) |
| Daily loss limit 1 R | Fixed stop 1 ATR, target 1 ATR (reference) | -0.09 / +0.14 (± 0.28 / 0.12) |
| Daily loss limit 2 R | Fixed stop 1 ATR, target 1 ATR (reference) | -0.17 / +0.09 (± 0.22 / 0.08) |
<!-- /table -->

BTC, with the H1 trend:

<!-- table change:BTCUSDm:trend -->
| Mechanism | Compared with | Change in expectancy per entry (± s.e.) |
|---|---|---|
| Fixed stop 2 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.43 / +0.52 (± 0.26 / 0.33) |
| Fixed stop 1 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.13 / +0.16 (± 0.12 / 0.15) |
| Fixed stop 2 ATR, target 1 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.20 / +0.15 (± 0.13 / 0.16) |
| Fixed stop $20, target $20 (the V2 exit) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.62 / +1.39 (± 0.86 / 0.63) |
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | +1.00 / +1.11 (± 0.12 / 0.30) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.42 / -1.16 (± 0.24 / 0.25) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.12 / -1.79 (± 0.35 / 0.54) |
| Budget 1 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.04 / -0.08 (± 0.07 / 0.09) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | -0.07 / -0.32 (± 0.09 / 0.11) |
| Budget 2 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.01 / +0.13 (± 0.12 / 0.14) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | +0.01 / -0.70 (± 0.13 / 0.18) |
| Budget 3 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / +0.11 (± 0.14 / 0.17) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | -0.06 / -0.08 (± 0.15 / 0.14) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.08 / -0.37 (± 0.16 / 0.19) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | -0.20 / -0.89 (± 0.19 / 0.22) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | -0.00 / -1.03 (± 0.18 / 0.29) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.08 / -0.37 (± 0.16 / 0.19) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.00 / +0.00 (± 0.00 / 0.00) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.00 / +0.00 (± 0.00 / 0.00) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | -0.04 / -0.31 (± 0.12 / 0.14) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | -0.08 / -0.05 (± 0.12 / 0.13) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | +0.01 / -0.05 (± 0.12 / 0.13) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | -0.18 / -0.08 (± 0.10 / 0.10) |
| Break-even at +0.5 ATR (stop 1, target 1) | Fixed stop 1 ATR, target 1 ATR (reference) | -0.09 / -0.13 (± 0.07 / 0.07) |
| Break-even at +1 ATR (stop 1, target 2) | Fixed stop 1 ATR, target 2 ATR | -0.08 / -0.06 (± 0.09 / 0.11) |
| Trailing stop 1 ATR, no target | Fixed stop 1 ATR, target 1 ATR (reference) | -0.01 / -0.05 (± 0.11 / 0.13) |
| Trailing stop 2 ATR, no target | Fixed stop 2 ATR, target 2 ATR | -0.21 / -0.05 (± 0.26 / 0.28) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | Trailing stop 1 ATR, no target | +0.00 / +0.06 (± 0.08 / 0.09) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | +0.03 / -0.20 (± 0.15 / 0.13) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | +0.00 / -0.28 (± 0.18 / 0.14) |
| Hedge lock, unlocked by the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.04 / -0.01 (± 0.07 / 0.10) |
| Close at -1 ATR, re-enter on the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.04 / -0.01 (± 0.07 / 0.10) |
| Hedge lock, both legs closed 4 h later | Fixed stop 1 ATR, target 1 ATR (reference) | -0.07 / -0.18 (± 0.00 / 0.01) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.13 / -2.27 (± 0.46 / 0.63) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | -1.24 / -2.35 (± 0.28 / 0.34) |
| Stop and reverse, same size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.10 / -0.30 (± 0.08 / 0.09) |
| Stop and reverse, double size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.20 / -0.59 (± 0.17 / 0.18) |
| Martingale: double after a loss, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / -0.35 (± 0.34 / 0.38) |
| Anti-martingale: double after a win, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / -0.63 (± 0.36 / 0.31) |
| Daily loss limit 1 R | Fixed stop 1 ATR, target 1 ATR (reference) | +0.09 / +0.11 (± 0.07 / 0.09) |
| Daily loss limit 2 R | Fixed stop 1 ATR, target 1 ATR (reference) | +0.04 / +0.03 (± 0.04 / 0.06) |
<!-- /table -->

BTC, votes only:

<!-- table change:BTCUSDm:votes -->
| Mechanism | Compared with | Change in expectancy per entry (± s.e.) |
|---|---|---|
| Fixed stop 2 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -0.08 / +0.35 (± 0.17 / 0.18) |
| Fixed stop 1 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | -0.02 / +0.08 (± 0.08 / 0.09) |
| Fixed stop 2 ATR, target 1 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.02 / +0.09 (± 0.08 / 0.10) |
| Fixed stop $20, target $20 (the V2 exit) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.17 / -0.01 (± 0.36 / 0.35) |
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | +1.05 / -2.68 (± 0.08 / 2.32) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.41 / -1.35 (± 0.15 / 0.21) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | +0.26 / -1.59 (± 0.22 / 0.36) |
| Budget 1 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.04 / -0.01 (± 0.06 / 0.07) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | -0.18 / -0.40 (± 0.07 / 0.09) |
| Budget 2 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / +0.12 (± 0.07 / 0.11) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | +0.03 / -0.53 (± 0.11 / 0.11) |
| Budget 3 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | -0.03 / +0.04 (± 0.10 / 0.12) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | -0.06 / +0.01 (± 0.09 / 0.12) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | +0.09 / -0.28 (± 0.12 / 0.17) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | +0.05 / -0.57 (± 0.16 / 0.17) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | +0.11 / -0.79 (± 0.18 / 0.19) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | +0.09 / -0.28 (± 0.12 / 0.17) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.00 / +0.00 (± 0.00 / 0.00) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.00 / +0.00 (± 0.00 / 0.00) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | -0.01 / -0.17 (± 0.09 / 0.13) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | -0.05 / +0.04 (± 0.08 / 0.10) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | -0.01 / -0.08 (± 0.10 / 0.11) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | -0.08 / -0.03 (± 0.06 / 0.08) |
| Break-even at +0.5 ATR (stop 1, target 1) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / -0.01 (± 0.04 / 0.06) |
| Break-even at +1 ATR (stop 1, target 2) | Fixed stop 1 ATR, target 2 ATR | +0.00 / -0.12 (± 0.06 / 0.07) |
| Trailing stop 1 ATR, no target | Fixed stop 1 ATR, target 1 ATR (reference) | +0.07 / -0.09 (± 0.08 / 0.10) |
| Trailing stop 2 ATR, no target | Fixed stop 2 ATR, target 2 ATR | +0.03 / -0.31 (± 0.16 / 0.26) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | Trailing stop 1 ATR, no target | -0.08 / +0.07 (± 0.07 / 0.08) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | -0.00 / -0.29 (± 0.10 / 0.10) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | -0.00 / -0.33 (± 0.13 / 0.13) |
| Hedge lock, unlocked by the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | -0.09 / -0.21 (± 0.07 / 0.07) |
| Close at -1 ATR, re-enter on the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | -0.09 / -0.21 (± 0.07 / 0.07) |
| Hedge lock, both legs closed 4 h later | Fixed stop 1 ATR, target 1 ATR (reference) | -0.07 / -0.18 (± 0.00 / 0.01) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.62 / -1.93 (± 0.36 / 0.48) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | -1.17 / -2.10 (± 0.23 / 0.29) |
| Stop and reverse, same size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.05 / -0.27 (± 0.06 / 0.06) |
| Stop and reverse, double size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.10 / -0.54 (± 0.12 / 0.12) |
| Martingale: double after a loss, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.36 / -0.86 (± 0.31 / 0.28) |
| Anti-martingale: double after a win, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | +0.16 / -0.44 (± 0.28 / 0.27) |
| Daily loss limit 1 R | Fixed stop 1 ATR, target 1 ATR (reference) | -0.08 / +0.23 (± 0.06 / 0.08) |
| Daily loss limit 2 R | Fixed stop 1 ATR, target 1 ATR (reference) | -0.04 / +0.13 (± 0.05 / 0.06) |
<!-- /table -->

BTC, random:

<!-- table change:BTCUSDm:random -->
| Mechanism | Compared with | Change in expectancy per entry (± s.e.) |
|---|---|---|
| Fixed stop 2 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.06 / -0.00 (± 0.17 / 0.20) |
| Fixed stop 1 ATR, target 2 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / +0.08 (± 0.09 / 0.09) |
| Fixed stop 2 ATR, target 1 ATR | Fixed stop 1 ATR, target 1 ATR (reference) | +0.14 / +0.09 (± 0.09 / 0.09) |
| Fixed stop $20, target $20 (the V2 exit) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.03 / +0.29 (± 0.33 / 0.32) |
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | -1.42 / -5.19 (± 2.45 / 3.33) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.95 / -1.90 (± 0.17 / 0.24) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | -1.00 / -1.87 (± 0.34 / 0.44) |
| Budget 1 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.03 / -0.12 (± 0.06 / 0.07) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | -0.10 / -0.55 (± 0.07 / 0.09) |
| Budget 2 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.08 / -0.08 (± 0.08 / 0.10) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | -0.12 / -0.31 (± 0.10 / 0.10) |
| Budget 3 R, no add | Fixed stop 1 ATR, target 1 ATR (reference) | +0.05 / +0.02 (± 0.11 / 0.13) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | -0.10 / -0.20 (± 0.10 / 0.11) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.15 / -0.33 (± 0.14 / 0.13) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | -0.28 / -0.43 (± 0.14 / 0.17) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | -0.22 / -0.61 (± 0.18 / 0.19) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | -0.15 / -0.33 (± 0.14 / 0.13) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.00 / +0.00 (± 0.00 / 0.00) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.00 / +0.00 (± 0.00 / 0.00) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | -0.16 / -0.18 (± 0.11 / 0.12) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | -0.16 / -0.24 (± 0.09 / 0.09) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | -0.14 / -0.23 (± 0.09 / 0.09) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | -0.01 / -0.24 (± 0.07 / 0.08) |
| Break-even at +0.5 ATR (stop 1, target 1) | Fixed stop 1 ATR, target 1 ATR (reference) | +0.02 / -0.10 (± 0.05 / 0.05) |
| Break-even at +1 ATR (stop 1, target 2) | Fixed stop 1 ATR, target 2 ATR | -0.01 / -0.09 (± 0.07 / 0.07) |
| Trailing stop 1 ATR, no target | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / -0.18 (± 0.07 / 0.09) |
| Trailing stop 2 ATR, no target | Fixed stop 2 ATR, target 2 ATR | +0.02 / +0.25 (± 0.22 / 0.21) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | Trailing stop 1 ATR, no target | -0.04 / +0.16 (± 0.05 / 0.07) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | -0.11 / -0.17 (± 0.08 / 0.10) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | -0.17 / -0.16 (± 0.08 / 0.13) |
| Hedge lock, unlocked by the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / -0.18 (± 0.08 / 0.07) |
| Close at -1 ATR, re-enter on the next vote signal | Fixed stop 1 ATR, target 1 ATR (reference) | +0.01 / -0.18 (± 0.08 / 0.07) |
| Hedge lock, both legs closed 4 h later | Fixed stop 1 ATR, target 1 ATR (reference) | -0.08 / -0.17 (± 0.00 / 0.01) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.41 / -1.21 (± 0.33 / 0.47) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | -1.27 / -2.32 (± 0.17 / 0.22) |
| Stop and reverse, same size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.07 / -0.20 (± 0.07 / 0.07) |
| Stop and reverse, double size | Fixed stop 1 ATR, target 1 ATR (reference) | -0.14 / -0.41 (± 0.14 / 0.14) |
| Martingale: double after a loss, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.27 / -0.13 (± 0.24 / 0.27) |
| Anti-martingale: double after a win, up to x8 | Fixed stop 1 ATR, target 1 ATR (reference) | -0.13 / +0.29 (± 0.25 / 0.43) |
| Daily loss limit 1 R | Fixed stop 1 ATR, target 1 ATR (reference) | +0.14 / +0.07 (± 0.07 / 0.09) |
| Daily loss limit 2 R | Fixed stop 1 ATR, target 1 ATR (reference) | +0.08 / +0.11 (± 0.05 / 0.06) |
<!-- /table -->

</details>

### 2. The mechanism sets the win rate; the price is the size of the rare loss

The win-rate column of the first table barely moves from cell to cell: 20 to 24 % for the pyramid, 46
to 51 % for the reference, 64 to 68 % with a stop twice the target, 83 to 87 % for a single position
with a 3 R budget and a small target, 90 to 94 % for zone recovery with legs 1 / 3 / 6 / 12, 94 to
98 % for the live ladder with a $60 stop, 100 % without a stop. Entries, symbol and year hardly
matter; the geometry of the exit decides. The expectancy column does not follow the win rate at all.
What follows it is the size of the loss when it comes: -1 R for the reference, -3 R for the 87 %
position, -15 R for zone recovery, no limit for the ladder.

Three groups come out of the tables:

| Group | Mechanisms | What they do to the result |
|---|---|---|
| Trade many small losses for a few large ones, expectancy unchanged or worse | the live ladder, averaging down (by level or by signal), a stop wider than the target, zone recovery, stop and reverse with double size, martingale sizing, a hedge lock | win rate up, rare loss larger; those that open more units also pay more spread |
| Trade many small wins for a few large ones, expectancy unchanged | a target wider than the stop, break-even, trailing stop, pyramiding, anti-martingale sizing | win rate down, loss capped at the first stop |
| Cap the damage without changing what a basket is worth | a hard stop in dollars, the budget, no add that does not fit it, being flat while the market is closed, a daily loss limit | bound one basket or one day |

### 3. What caps the damage, and what a stop cannot cap

A stop in ATR units caps the loss in R, and R itself moves: on gold from $5 to over $120 at 0.01 lot
within DEV. "3 R" was $52 at the median, $112 at the 95th percentile and $364 in the wildest hour, which is
18 % of a 2,000 account for one basket. A cap in dollars is what fixes the share of the balance: the
row "Budget 3 R but never more than $60" takes the smaller of the two.

A stop also cannot act while the market is closed. Price jumps over gold's closures, at 0.01 lot:

<!-- table gaps:XAUUSDm -->
| Closure | Period | Closures | Median jump | 99th percentile | Largest | Largest, in R |
|---|---|---|---|---|---|---|
| daily break | DEV | 283 | $2.04 | $27.36 | $33.91 | 1.1 |
| weekend or holiday | DEV | 73 | $6.36 | $84.49 | $98.03 | 4.0 |
| daily break | CONFIRM | 318 | $0.59 | $6.89 | $43.81 | 1.9 |
| weekend or holiday | CONFIRM | 80 | $2.13 | $28.89 | $44.57 | 3.3 |
<!-- /table -->

With three units open such a jump counts three times. The same $60 ladder shows it:

| Gold, ladder with a $60 budget | Worst basket, DEV | Worst basket, CONFIRM |
|---|---|---|
| held over every closure | -$222 | -$78 |
| flat over the weekend (from Friday 20:30 UTC) | -$119 | -$78 |
| flat over every closure (also 20:30 to 23:05 UTC daily) | -$60.00 | -$60.00 |

Being flat cost nothing measurable (change in expectancy between -$0.12 and +$0.30 per entry, none
beyond 1.6 standard errors).

The dollar cap held everywhere: with the calendar rule no gold basket, and with or without it no BTC
basket, lost more than $60.00. A basket's own budget is smaller than the cap whenever 3 R is, which
is most of the time, and that smaller amount was overshot in 4 of 13,336 baskets on gold (by $6.42 at
most) and in 12 of 18,616 on BTC (by $15.14 at most): holidays, early closes and exchange pauses that
a fixed calendar does not know. BTC had 25 trading pauses of half an hour or more in CONFIRM, with
jumps of up to $8 (1.7 R) per unit. A stop makes a loss beyond the budget impossible only while the
market trades without a break; what remains is a jump times the units held, which is the reason to
keep the position small.

<details><summary>How often a basket lost more than it was built to lose, every mechanism with a fixed loss (three lists together)</summary>

Gold:

<!-- table budget:XAUUSDm -->
| Mechanism | Baskets | Largest budget of one basket | Baskets that lost more than their budget | Largest loss beyond the budget | Worst basket |
|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | 6,497 / 7,440 | $126 / $27 | 32 / 30 | $30.08 / $35.61 | -121 / -50.9 |
| Fixed stop 2 ATR, target 2 ATR | 6,497 / 7,440 | $251 / $55 | 52 / 37 | $58.46 / $23.59 | -243 / -70.0 |
| Fixed stop 1 ATR, target 2 ATR | 6,497 / 7,440 | $126 / $27 | 45 / 45 | $33.32 / $35.61 | -121 / -50.9 |
| Fixed stop 2 ATR, target 1 ATR | 6,497 / 7,440 | $251 / $55 | 34 / 24 | $55.80 / $23.59 | -243 / -70.0 |
| Fixed stop $20, target $20 (the V2 exit) | 6,497 / 7,440 | $20 / $20 | 26 / 21 | $20.66 / $30.88 | -40.7 / -50.9 |
| Live ladder, basket stop $60 | 6,497 / 7,440 | $60 / $60 | 0 / 8 | $0.00 / $35.91 | -60.0 / -95.9 |
| Live ladder, basket stop $200 | 6,497 / 7,440 | $200 / $200 | 2 / 0 | $41.24 / $0.00 | -241 / -200 |
| Budget 1 R, no add | 6,497 / 7,440 | $126 / $27 | 26 / 21 | $30.08 / $21.70 | -121 / -45.0 |
| Budget 1 R, 2 adds 0.17 ATR apart | 6,497 / 7,440 | $126 / $27 | 18 / 18 | $81.86 / $13.53 | -121 / -28.4 |
| Budget 2 R, no add | 6,497 / 7,440 | $251 / $55 | 19 / 14 | $43.95 / $23.59 | -243 / -70.0 |
| Budget 2 R, 2 adds 0.33 ATR apart | 6,497 / 7,440 | $251 / $55 | 22 / 18 | $88.88 / $65.09 | -243 / -112 |
| Budget 3 R, no add | 6,497 / 7,440 | $377 / $82 | 16 / 11 | $54.48 / $28.37 | -364 / -91.6 |
| Budget 3 R, 1 add 1 ATR apart | 6,497 / 7,440 | $377 / $82 | 12 / 12 | $87.91 / $47.19 | -364 / -117 |
| Budget 3 R, 2 adds 0.5 ATR apart | 6,497 / 7,440 | $377 / $82 | 14 / 11 | $161.98 / $13.70 | -364 / -79.8 |
| Budget 3 R, 3 adds 0.3 ATR apart | 6,497 / 7,440 | $377 / $82 | 13 / 14 | $151.35 / $44.14 | -364 / -114 |
| Budget 3 R, 4 adds 0.2 ATR apart | 6,497 / 7,440 | $377 / $82 | 20 / 17 | $148.14 / $82.14 | -364 / -152 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 6,497 / 7,440 | $60 / $60 | 14 / 11 | $162.23 / $18.32 | -222 / -78.3 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 6,370 / 7,321 | $60 / $60 | 6 / 7 | $58.69 / $18.32 | -119 / -78.3 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 6,169 / 7,167 | $60 / $60 | 1 / 3 | $0.15 / $6.42 | -60.0 / -60.0 |
| Add when the M5 MACD histogram turns | 6,497 / 7,440 | $377 / $82 | 11 / 8 | $89.50 / $44.37 | -364 / -114 |
| Add when the M15 MACD histogram turns | 6,497 / 7,440 | $377 / $82 | 14 / 10 | $96.73 / $44.61 | -364 / -114 |
| Add when the M5 RSI comes back through 35 / 65 | 6,497 / 7,440 | $377 / $82 | 13 / 8 | $54.48 / $44.37 | -364 / -114 |
| Add when the M15 RSI comes back through 35 / 65 | 6,497 / 7,440 | $377 / $82 | 16 / 9 | $54.48 / $45.08 | -364 / -115 |
| Break-even at +0.5 ATR (stop 1, target 1) | 6,497 / 7,440 | $126 / $27 | 27 / 22 | $30.08 / $21.70 | -121 / -45.0 |
| Break-even at +1 ATR (stop 1, target 2) | 6,497 / 7,440 | $126 / $27 | 34 / 31 | $30.08 / $35.61 | -121 / -50.9 |
| Trailing stop 1 ATR, no target | 6,497 / 7,440 | $126 / $27 | 18 / 12 | $30.08 / $21.70 | -120 / -45.0 |
| Trailing stop 2 ATR, no target | 6,497 / 7,440 | $251 / $55 | 13 / 8 | $43.95 / $23.59 | -241 / -70.0 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 6,497 / 7,440 | $126 / $27 | 32 / 30 | $30.08 / $35.61 | -121 / -50.9 |
| Stop and reverse, same size | 6,497 / 7,440 | $251 / $55 | 31 / 35 | $18.02 / $36.95 | -243 / -73.6 |
| Stop and reverse, double size | 6,497 / 7,440 | $377 / $82 | 31 / 34 | $36.03 / $73.90 | -364 / -129 |
| Martingale: double after a loss, up to x8 | 6,497 / 7,440 | $1,005 / $209 | 32 / 31 | $240.62 / $173.58 | -971 / -360 |
| Anti-martingale: double after a win, up to x8 | 6,497 / 7,440 | $915 / $219 | 33 / 31 | $118.51 / $37.44 | -915 / -219 |
| Daily loss limit 1 R | 3,116 / 3,443 | $121 / $27 | 12 / 9 | $29.63 / $6.42 | -121 / -27.3 |
| Daily loss limit 2 R | 4,819 / 5,486 | $121 / $27 | 19 / 14 | $29.63 / $6.42 | -121 / -27.3 |
<!-- /table -->

BTC:

<!-- table budget:BTCUSDm -->
| Mechanism | Baskets | Largest budget of one basket | Baskets that lost more than their budget | Largest loss beyond the budget | Worst basket |
|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | 8,905 / 9,711 | $19 / $22 | 4 / 16 | $0.08 / $0.43 | -19.2 / -22.5 |
| Fixed stop 2 ATR, target 2 ATR | 8,905 / 9,711 | $38 / $45 | 4 / 9 | $0.03 / $1.68 | -38.5 / -45.0 |
| Fixed stop 1 ATR, target 2 ATR | 8,905 / 9,711 | $19 / $22 | 10 / 21 | $0.08 / $0.43 | -19.2 / -22.5 |
| Fixed stop 2 ATR, target 1 ATR | 8,905 / 9,711 | $38 / $45 | 4 / 7 | $0.03 / $1.68 | -37.2 / -39.7 |
| Fixed stop $20, target $20 (the V2 exit) | 8,905 / 9,711 | $20 / $20 | 6 / 11 | $0.07 / $0.52 | -20.1 / -20.5 |
| Live ladder, basket stop $60 | 8,905 / 9,711 | $60 / $60 | 2 / 3 | $2.13 / $2.94 | -62.1 / -62.9 |
| Live ladder, basket stop $200 | 8,905 / 9,711 | $200 / $200 | 0 / 0 | $0.00 / $0.00 | -200 / -200 |
| Budget 1 R, no add | 8,905 / 9,711 | $19 / $22 | 2 / 11 | $0.03 / $0.43 | -19.2 / -22.5 |
| Budget 1 R, 2 adds 0.17 ATR apart | 8,905 / 9,711 | $19 / $22 | 21 / 17 | $0.52 / $2.11 | -19.2 / -22.5 |
| Budget 2 R, no add | 8,905 / 9,711 | $38 / $45 | 2 / 5 | $0.03 / $1.68 | -37.2 / -38.8 |
| Budget 2 R, 2 adds 0.33 ATR apart | 8,905 / 9,711 | $38 / $45 | 2 / 10 | $0.08 / $0.39 | -37.2 / -45.0 |
| Budget 3 R, no add | 8,905 / 9,711 | $58 / $67 | 2 / 1 | $0.02 / $0.07 | -50.5 / -58.1 |
| Budget 3 R, 1 add 1 ATR apart | 8,905 / 9,711 | $58 / $67 | 3 / 5 | $0.06 / $3.36 | -55.9 / -58.1 |
| Budget 3 R, 2 adds 0.5 ATR apart | 8,905 / 9,711 | $58 / $67 | 1 / 11 | $0.23 / $15.14 | -50.5 / -67.5 |
| Budget 3 R, 3 adds 0.3 ATR apart | 8,905 / 9,711 | $58 / $67 | 11 / 6 | $1.53 / $6.92 | -50.5 / -67.5 |
| Budget 3 R, 4 adds 0.2 ATR apart | 8,905 / 9,711 | $58 / $67 | 1 / 14 | $0.08 / $7.00 | -55.9 / -67.5 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 8,905 / 9,711 | $58 / $60 | 1 / 11 | $0.23 / $15.14 | -50.5 / -60.0 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | 8,905 / 9,711 | $58 / $60 | 1 / 11 | $0.23 / $15.14 | -50.5 / -60.0 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | 8,905 / 9,711 | $58 / $60 | 1 / 11 | $0.23 / $15.14 | -50.5 / -60.0 |
| Add when the M5 MACD histogram turns | 8,905 / 9,711 | $58 / $67 | 4 / 13 | $0.12 / $5.42 | -55.9 / -54.8 |
| Add when the M15 MACD histogram turns | 8,905 / 9,711 | $58 / $67 | 4 / 1 | $0.13 / $0.16 | -55.9 / -54.8 |
| Add when the M5 RSI comes back through 35 / 65 | 8,905 / 9,711 | $58 / $67 | 4 / 5 | $0.12 / $0.22 | -55.9 / -58.1 |
| Add when the M15 RSI comes back through 35 / 65 | 8,905 / 9,711 | $58 / $67 | 2 / 0 | $0.02 / $0.00 | -55.9 / -58.1 |
| Break-even at +0.5 ATR (stop 1, target 1) | 8,905 / 9,711 | $19 / $22 | 2 / 11 | $0.03 / $0.43 | -19.2 / -22.5 |
| Break-even at +1 ATR (stop 1, target 2) | 8,905 / 9,711 | $19 / $22 | 4 / 16 | $0.08 / $0.43 | -19.2 / -22.5 |
| Trailing stop 1 ATR, no target | 8,905 / 9,711 | $19 / $22 | 0 / 4 | $0.00 / $0.43 | -15.8 / -18.4 |
| Trailing stop 2 ATR, no target | 8,905 / 9,711 | $38 / $45 | 0 / 3 | $0.00 / $1.68 | -30.1 / -37.7 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | 8,905 / 9,711 | $19 / $22 | 4 / 16 | $0.08 / $0.43 | -19.2 / -22.5 |
| Stop and reverse, same size | 8,905 / 9,711 | $38 / $45 | 5 / 15 | $0.08 / $0.43 | -38.5 / -45.0 |
| Stop and reverse, double size | 8,905 / 9,711 | $58 / $67 | 7 / 18 | $0.15 / $0.43 | -57.7 / -67.5 |
| Martingale: double after a loss, up to x8 | 8,905 / 9,711 | $154 / $180 | 4 / 16 | $0.08 / $1.03 | -154 / -180 |
| Anti-martingale: double after a win, up to x8 | 8,905 / 9,711 | $140 / $155 | 4 / 17 | $0.17 / $0.43 | -138 / -155 |
| Daily loss limit 1 R | 4,054 / 4,023 | $19 / $20 | 1 / 7 | $0.08 / $0.13 | -19.2 / -20.2 |
| Daily loss limit 2 R | 6,367 / 6,688 | $19 / $22 | 4 / 11 | $0.08 / $0.13 | -19.2 / -22.5 |
<!-- /table -->

</details>

### 4. The ladder: what it buys and what it costs

The owner's reason for the ladder is that it covers the loss when a position goes the wrong way.
Basket by basket that is true, and the tables show both the truth and the bill.

*The live ladder.* Take only the baskets in which it added (with the H1 trend: 219 and 435 on gold,
676 and 756 on BTC). The plain reference trade on those same entries won 22 to 35 % of the time and
lost $2.05 to $4.14 on average. The ladder without a stop brought 99.9 to 100 % of them back to +$1.
That is the benefit, and it is real. The bill is in the floating-loss column: -$30,176 and -$1,606
on gold, -$1,806 and -$1,745 on BTC for one basket at 0.01 lot, against an account of 2,000. With a
$60 stop the ladder still rescued 85 to 93 % of those baskets, and their average result was -$3.15 to
-$7.95, worse than without any ladder, because the baskets that hit the stop do so with up to 32
units.

*Equal lots inside a budget.* With a budget of 3 R the two-add ladder (adds 0.5 and 1.0 ATR against
the entry, stop at 1.5 ATR) won 76 to 81 % of its baskets. A single position with its stop at 1 ATR
won 61 to 67 %, with its stop at 2 ATR 77 to 81 %. So the ladder does win more often than a position
with the same stop distance: about as often as one whose stop is a third further away. But it puts
3 R at risk to do so, and a single position that is given the same 3 R can afford a stop at 3 ATR and
wins 83 to 87 %. In the baskets that needed an add, the single position came back to its target in
69 to 73 % and the ladder in 55 to 60 %; the mean results were the same within noise on gold (-$9.35
against -$9.38 on DEV, -$4.03 against -$4.44 on CONFIRM) and a little worse for the ladder on BTC
(-$2.49 against -$2.65, -$3.06 against -$3.75; only the last difference reaches two standard errors).

*More adds are worse, not better.* Inside the same 3 R, four adds 0.2 ATR apart won 67 to 73 %, paid
the spread on three units per entry, and emptied the account by many small losses in 6 of 12 cells;
no add, in none.

*A signal instead of a level* changes little: adds released by an M5 or M15 turn open fewer units
(1.2 to 1.5 per entry against 1.8 to 1.9) and so pay less spread, and their change against the
no-add position is between -$0.53 and +$0.63 per entry with no pattern across cells.

<details><summary>The baskets in which a mechanism added, against the same baskets without the adds</summary>

Gold, with the H1 trend:

<!-- table adds:XAUUSDm:trend -->
| Mechanism | Compared with | Baskets with an add | Won without the adds, % | Won with them, % | Mean result without | Mean result with | Difference (± s.e.) |
|---|---|---|---|---|---|---|---|
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | 219 / 435 | 35 / 31 | 100 / 100 | -4.14 / -2.46 | +1.00 / +1.00 | +5.15 / +3.46 (± 0.92 / 0.34) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | 218 / 435 | 35 / 31 | 85 / 92 | -3.80 / -2.46 | -7.95 / -3.84 | -4.15 / -1.38 (± 1.62 / 0.80) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | 219 / 435 | 35 / 31 | 96 / 97 | -4.14 / -2.46 | -6.53 / -4.54 | -2.38 / -2.09 (± 2.66 / 1.56) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | 1,078 / 1,237 | 56 / 54 | 38 / 35 | -2.92 / -1.57 | -2.82 / -1.96 | +0.09 / -0.39 (± 0.63 / 0.21) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | 855 / 1,002 | 68 / 66 | 53 / 51 | -5.88 / -2.62 | -6.76 / -3.31 | -0.88 / -0.69 (± 0.91 / 0.35) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | 464 / 553 | 58 / 56 | 51 / 46 | -19.27 / -8.03 | -19.37 / -8.75 | -0.10 / -0.71 (± 1.39 / 0.55) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | 702 / 838 | 73 / 71 | 60 / 59 | -9.35 / -4.03 | -9.38 / -4.44 | -0.03 / -0.41 (± 1.41 / 0.53) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | 896 / 1,031 | 78 / 76 | 62 / 61 | -5.14 / -2.58 | -7.39 / -3.16 | -2.26 / -0.59 (± 1.19 / 0.49) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | 1,029 / 1,187 | 81 / 80 | 63 / 60 | -3.13 / -1.75 | -3.60 / -2.83 | -0.47 / -1.08 (± 1.46 / 0.50) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | 700 / 838 | 73 / 71 | 57 / 58 | -8.95 / -4.03 | -9.66 / -4.63 | -0.71 / -0.60 (± 1.60 / 0.55) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 678 / 815 | 57 / 58 | 57 / 58 | -9.38 / -4.64 | -9.32 / -4.74 | +0.06 / -0.10 (± 0.21 / 0.11) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 642 / 776 | 57 / 58 | 55 / 55 | -9.65 / -4.78 | -9.40 / -4.83 | +0.25 / -0.06 (± 0.35 / 0.21) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | 484 / 552 | 62 / 59 | 53 / 50 | -17.33 / -7.27 | -17.27 / -7.79 | +0.06 / -0.52 (± 1.59 / 0.54) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | 375 / 436 | 57 / 54 | 51 / 47 | -20.66 / -8.81 | -18.25 / -8.72 | +2.42 / +0.09 (± 1.71 / 0.65) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | 381 / 445 | 56 / 54 | 50 / 43 | -21.03 / -8.73 | -19.32 / -9.31 | +1.72 / -0.58 (± 1.78 / 0.67) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | 227 / 268 | 55 / 51 | 50 / 43 | -22.07 / -10.21 | -19.19 / -10.33 | +2.88 / -0.12 (± 2.20 / 1.15) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | 551 / 623 | 99 / 98 | 62 / 59 | +20.54 / +7.02 | +21.95 / +5.91 | +1.41 / -1.12 (± 1.83 / 0.58) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | 551 / 623 | 99 / 98 | 62 / 59 | +20.54 / +7.02 | +22.39 / +5.75 | +1.85 / -1.27 (± 2.33 / 0.67) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | 706 / 824 | 0 / 0 | 86 / 86 | -19.70 / -7.67 | -24.91 / -7.97 | -5.21 / -0.30 (± 4.65 / 2.03) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | 941 / 1,101 | 25 / 25 | 66 / 68 | -9.74 / -3.92 | -13.20 / -5.00 | -3.46 / -1.08 (± 1.95 / 0.74) |
<!-- /table -->

Gold, votes only:

<!-- table adds:XAUUSDm:votes -->
| Mechanism | Compared with | Baskets with an add | Won without the adds, % | Won with them, % | Mean result without | Mean result with | Difference (± s.e.) |
|---|---|---|---|---|---|---|---|
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | 434 / 820 | 33 / 29 | 100 / 100 | -6.06 / -2.94 | -30.44 / -47.88 | -24.39 / -44.94 (± 31.52 / 48.42) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | 433 / 820 | 33 / 29 | 82 / 90 | -5.79 / -2.94 | -9.98 / -5.11 | -4.19 / -2.17 (± 1.06 / 0.57) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | 434 / 820 | 33 / 29 | 95 / 98 | -6.06 / -2.94 | -9.28 / -3.66 | -3.22 / -0.72 (± 1.73 / 1.01) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | 1,890 / 2,182 | 54 / 53 | 37 / 33 | -3.46 / -1.60 | -3.17 / -2.09 | +0.29 / -0.49 (± 0.43 / 0.16) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | 1,529 / 1,776 | 66 / 63 | 52 / 50 | -6.78 / -3.17 | -6.84 / -3.31 | -0.06 / -0.15 (± 0.89 / 0.29) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | 862 / 1,008 | 56 / 52 | 48 / 44 | -20.67 / -9.23 | -21.99 / -9.50 | -1.32 / -0.27 (± 1.07 / 0.36) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,282 / 1,525 | 70 / 68 | 58 / 58 | -10.62 / -4.80 | -11.17 / -4.59 | -0.54 / +0.20 (± 1.20 / 0.34) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | 1,588 / 1,831 | 76 / 74 | 60 / 59 | -6.59 / -3.35 | -7.58 / -3.25 | -0.99 / +0.11 (± 1.17 / 0.40) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | 1,812 / 2,076 | 79 / 77 | 61 / 58 | -4.51 / -2.52 | -4.72 / -2.84 | -0.21 / -0.32 (± 1.31 / 0.40) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,280 / 1,525 | 70 / 68 | 55 / 58 | -10.07 / -4.80 | -11.47 / -4.58 | -1.39 / +0.21 (± 1.18 / 0.34) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,247 / 1,495 | 55 / 58 | 55 / 57 | -11.14 / -4.60 | -11.02 / -4.60 | +0.13 / +0.00 (± 0.12 / 0.07) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,182 / 1,436 | 55 / 57 | 53 / 55 | -11.40 / -4.63 | -10.74 / -4.49 | +0.66 / +0.13 (± 0.31 / 0.14) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | 885 / 1,002 | 60 / 56 | 51 / 47 | -17.71 / -8.31 | -19.23 / -8.61 | -1.51 / -0.30 (± 1.18 / 0.51) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | 662 / 774 | 55 / 51 | 49 / 45 | -20.99 / -9.98 | -20.06 / -9.76 | +0.92 / +0.22 (± 1.24 / 0.49) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | 684 / 800 | 54 / 51 | 47 / 44 | -22.37 / -9.74 | -22.13 / -9.88 | +0.25 / -0.13 (± 1.21 / 0.43) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | 394 / 496 | 49 / 45 | 47 / 40 | -23.59 / -12.22 | -20.05 / -11.80 | +3.54 / +0.42 (± 1.57 / 0.72) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | 911 / 1,104 | 99 / 97 | 60 / 58 | +18.81 / +7.07 | +16.85 / +5.94 | -1.96 / -1.13 (± 1.15 / 0.36) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | 911 / 1,104 | 99 / 97 | 60 / 58 | +18.81 / +7.07 | +16.68 / +5.74 | -2.12 / -1.34 (± 1.45 / 0.40) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,314 / 1,510 | 0 / 0 | 88 / 86 | -19.52 / -7.59 | -18.53 / -7.88 | +0.99 / -0.29 (± 3.55 / 1.62) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,730 / 2,001 | 24 / 25 | 68 / 68 | -9.93 / -3.86 | -12.23 / -4.87 | -2.30 / -1.01 (± 1.37 / 0.56) |
<!-- /table -->

Gold, random:

<!-- table adds:XAUUSDm:random -->
| Mechanism | Compared with | Baskets with an add | Won without the adds, % | Won with them, % | Mean result without | Mean result with | Difference (± s.e.) |
|---|---|---|---|---|---|---|---|
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | 740 / 1,165 | 40 / 35 | 100 / 100 | -2.91 / -1.90 | +1.02 / -26.08 | +3.93 / -24.18 (± 0.79 / 27.02) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | 739 / 1,165 | 40 / 35 | 80 / 91 | -2.75 / -1.90 | -11.04 / -4.36 | -8.28 / -2.46 (± 1.24 / 0.55) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | 740 / 1,165 | 40 / 35 | 95 / 98 | -2.91 / -1.90 | -9.31 / -3.31 | -6.39 / -1.41 (± 1.68 / 0.79) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | 1,903 / 2,131 | 54 / 53 | 34 / 36 | -3.67 / -1.50 | -5.20 / -1.56 | -1.53 / -0.06 (± 0.44 / 0.17) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | 1,542 / 1,729 | 66 / 65 | 51 / 50 | -6.43 / -2.79 | -6.66 / -3.17 | -0.23 / -0.38 (± 0.63 / 0.31) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | 858 / 975 | 55 / 54 | 50 / 46 | -20.87 / -8.21 | -20.25 / -8.53 | +0.62 / -0.32 (± 1.50 / 0.43) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,317 / 1,422 | 70 / 69 | 61 / 58 | -9.97 / -4.42 | -8.75 / -4.09 | +1.23 / +0.33 (± 0.85 / 0.34) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | 1,599 / 1,791 | 76 / 75 | 61 / 60 | -6.36 / -2.72 | -5.07 / -3.00 | +1.29 / -0.28 (± 1.07 / 0.38) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | 1,824 / 2,028 | 79 / 78 | 60 / 59 | -4.47 / -1.96 | -4.78 / -2.58 | -0.31 / -0.62 (± 0.79 / 0.44) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,314 / 1,422 | 70 / 69 | 58 / 58 | -9.49 / -4.42 | -9.30 / -4.18 | +0.19 / +0.24 (± 0.91 / 0.35) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,284 / 1,392 | 57 / 58 | 57 / 58 | -9.51 / -4.13 | -9.27 / -4.08 | +0.24 / +0.05 (± 0.22 / 0.08) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,220 / 1,332 | 57 / 58 | 55 / 56 | -9.82 / -4.06 | -9.28 / -4.00 | +0.54 / +0.06 (± 0.33 / 0.13) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | 914 / 980 | 60 / 58 | 53 / 50 | -17.25 / -7.41 | -15.63 / -7.70 | +1.62 / -0.29 (± 1.45 / 0.39) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | 690 / 752 | 56 / 53 | 47 / 46 | -19.96 / -8.84 | -20.11 / -8.94 | -0.15 / -0.10 (± 1.42 / 0.48) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | 725 / 803 | 57 / 54 | 51 / 46 | -19.97 / -8.42 | -18.14 / -9.01 | +1.84 / -0.59 (± 1.35 / 0.52) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | 409 / 459 | 50 / 48 | 44 / 43 | -23.19 / -10.49 | -22.45 / -10.18 | +0.74 / +0.30 (± 1.69 / 0.63) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | 919 / 1,056 | 98 / 97 | 60 / 56 | +20.09 / +7.92 | +20.22 / +7.87 | +0.13 / -0.06 (± 1.18 / 0.44) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | 919 / 1,056 | 98 / 97 | 60 / 56 | +20.09 / +7.92 | +20.34 / +7.67 | +0.24 / -0.26 (± 1.56 / 0.49) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,265 / 1,484 | 0 / 0 | 86 / 87 | -19.58 / -7.69 | -22.44 / -6.41 | -2.87 / +1.28 (± 3.54 / 1.30) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,715 / 1,942 | 26 / 24 | 68 / 68 | -9.06 / -4.13 | -12.35 / -5.17 | -3.29 / -1.03 (± 1.27 / 0.56) |
<!-- /table -->

BTC, with the H1 trend:

<!-- table adds:BTCUSDm:trend -->
| Mechanism | Compared with | Baskets with an add | Won without the adds, % | Won with them, % | Mean result without | Mean result with | Difference (± s.e.) |
|---|---|---|---|---|---|---|---|
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | 676 / 756 | 28 / 22 | 100 / 100 | -2.05 / -2.82 | +1.00 / +0.24 | +3.05 / +3.05 (± 0.19 / 0.78) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | 676 / 756 | 28 / 22 | 93 / 88 | -2.05 / -2.82 | -3.15 / -6.02 | -1.10 / -3.20 (± 0.64 / 0.61) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | 676 / 756 | 28 / 22 | 98 / 96 | -2.05 / -2.82 | -2.27 / -7.77 | -0.22 / -4.95 (± 0.97 / 1.46) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | 1,518 / 1,657 | 57 / 51 | 37 / 31 | -0.79 / -1.37 | -0.88 / -1.77 | -0.09 / -0.40 (± 0.11 / 0.13) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | 1,220 / 1,340 | 68 / 65 | 54 / 46 | -1.53 / -2.07 | -1.51 / -3.15 | +0.02 / -1.08 (± 0.22 / 0.29) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | 643 / 787 | 57 / 56 | 49 / 48 | -5.09 / -5.64 | -5.27 / -5.86 | -0.18 / -0.22 (± 0.44 / 0.38) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | 979 / 1,121 | 72 / 69 | 59 / 55 | -2.49 / -3.06 | -2.65 / -3.75 | -0.16 / -0.69 (± 0.32 / 0.35) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | 1,269 / 1,403 | 78 / 75 | 62 / 56 | -1.35 / -1.86 | -1.67 / -3.19 | -0.32 / -1.32 (± 0.30 / 0.32) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | 1,442 / 1,582 | 81 / 78 | 63 / 56 | -0.90 / -1.33 | -0.90 / -2.68 | -0.00 / -1.35 (± 0.25 / 0.38) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | 979 / 1,121 | 72 / 69 | 59 / 55 | -2.49 / -3.06 | -2.65 / -3.74 | -0.16 / -0.68 (± 0.32 / 0.35) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 979 / 1,121 | 59 / 55 | 59 / 55 | -2.65 / -3.74 | -2.65 / -3.74 | +0.00 / +0.00 (± 0.00 / 0.00) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 979 / 1,121 | 59 / 55 | 59 / 55 | -2.65 / -3.74 | -2.65 / -3.74 | +0.00 / +0.00 (± 0.00 / 0.00) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | 644 / 790 | 60 / 61 | 52 / 49 | -4.46 / -4.73 | -4.59 / -5.56 | -0.14 / -0.82 (± 0.37 / 0.37) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | 506 / 616 | 57 / 57 | 48 / 48 | -5.19 / -5.48 | -5.51 / -5.67 | -0.32 / -0.19 (± 0.46 / 0.44) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | 507 / 632 | 56 / 55 | 48 / 47 | -5.33 / -5.72 | -5.30 / -5.89 | +0.03 / -0.17 (± 0.45 / 0.42) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | 322 / 388 | 50 / 55 | 40 / 46 | -6.52 / -6.05 | -7.62 / -6.45 | -1.10 / -0.41 (± 0.58 / 0.53) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | 739 / 762 | 98 / 92 | 59 / 55 | +4.96 / +5.50 | +5.03 / +4.95 | +0.07 / -0.56 (± 0.40 / 0.36) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | 739 / 762 | 98 / 92 | 59 / 55 | +4.96 / +5.50 | +4.96 / +4.73 | +0.00 / -0.77 (± 0.48 / 0.40) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | 984 / 1,121 | 0 / 0 | 87 / 82 | -5.00 / -5.86 | -5.27 / -10.09 | -0.27 / -4.23 (± 0.91 / 1.16) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,334 / 1,479 | 26 / 24 | 66 / 62 | -2.38 / -3.02 | -4.21 / -6.34 | -1.83 / -3.32 (± 0.42 / 0.47) |
<!-- /table -->

BTC, votes only:

<!-- table adds:BTCUSDm:votes -->
| Mechanism | Compared with | Baskets with an add | Won without the adds, % | Won with them, % | Mean result without | Mean result with | Difference (± s.e.) |
|---|---|---|---|---|---|---|---|
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | 1,213 / 1,390 | 27 / 23 | 100 / 100 | -2.07 / -2.71 | +1.00 / -10.45 | +3.07 / -7.74 (± 0.14 / 6.47) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,213 / 1,390 | 27 / 23 | 93 / 87 | -2.07 / -2.71 | -3.27 / -6.73 | -1.20 / -4.01 (± 0.43 / 0.54) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,213 / 1,390 | 27 / 23 | 99 / 96 | -2.07 / -2.71 | -1.32 / -7.39 | +0.75 / -4.67 (± 0.59 / 0.99) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | 2,703 / 3,062 | 56 / 51 | 36 / 30 | -0.79 / -1.33 | -1.04 / -1.83 | -0.24 / -0.51 (± 0.09 / 0.12) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | 2,149 / 2,484 | 67 / 64 | 52 / 46 | -1.71 / -2.14 | -1.66 / -2.98 | +0.04 / -0.84 (± 0.19 / 0.17) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | 1,154 / 1,453 | 55 / 55 | 47 / 47 | -5.47 / -5.97 | -5.64 / -5.93 | -0.17 / +0.04 (± 0.29 / 0.33) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,757 / 2,111 | 70 / 69 | 60 / 55 | -2.72 / -3.17 | -2.54 / -3.70 | +0.18 / -0.52 (± 0.24 / 0.31) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | 2,239 / 2,582 | 77 / 75 | 62 / 56 | -1.61 / -2.08 | -1.52 / -2.94 | +0.09 / -0.86 (± 0.25 / 0.26) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | 2,563 / 2,925 | 80 / 78 | 62 / 56 | -1.07 / -1.48 | -0.92 / -2.53 | +0.15 / -1.05 (± 0.25 / 0.26) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,757 / 2,111 | 70 / 69 | 60 / 55 | -2.72 / -3.17 | -2.54 / -3.69 | +0.18 / -0.52 (± 0.24 / 0.31) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,757 / 2,111 | 60 / 55 | 60 / 55 | -2.54 / -3.69 | -2.54 / -3.69 | +0.00 / +0.00 (± 0.00 / 0.00) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,757 / 2,111 | 60 / 55 | 60 / 55 | -2.54 / -3.69 | -2.54 / -3.69 | +0.00 / +0.00 (± 0.00 / 0.00) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | 1,138 / 1,454 | 59 / 60 | 51 / 49 | -4.73 / -5.07 | -4.78 / -5.52 | -0.05 / -0.45 (± 0.28 / 0.35) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | 834 / 1,077 | 55 / 56 | 48 / 48 | -5.59 / -5.85 | -5.80 / -5.71 | -0.21 / +0.14 (± 0.33 / 0.37) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | 861 / 1,118 | 52 / 54 | 45 / 46 | -5.96 / -6.16 | -5.98 / -6.44 | -0.03 / -0.28 (± 0.39 / 0.37) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | 501 / 676 | 48 / 52 | 40 / 44 | -7.08 / -6.89 | -7.66 / -7.08 | -0.58 / -0.19 (± 0.41 / 0.49) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | 1,343 / 1,418 | 97 / 94 | 58 / 54 | +5.01 / +5.32 | +5.00 / +4.53 | -0.01 / -0.79 (± 0.27 / 0.28) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | 1,343 / 1,418 | 97 / 94 | 58 / 54 | +5.01 / +5.32 | +5.00 / +4.41 | -0.01 / -0.91 (± 0.33 / 0.36) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,784 / 2,106 | 0 / 0 | 86 / 83 | -5.08 / -5.81 | -6.31 / -9.40 | -1.23 / -3.59 (± 0.72 / 0.89) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | 2,379 / 2,781 | 25 / 24 | 66 / 63 | -2.54 / -2.99 | -4.28 / -5.95 | -1.74 / -2.96 (± 0.34 / 0.40) |
<!-- /table -->

BTC, random:

<!-- table adds:BTCUSDm:random -->
| Mechanism | Compared with | Baskets with an add | Won without the adds, % | Won with them, % | Mean result without | Mean result with | Difference (± s.e.) |
|---|---|---|---|---|---|---|---|
| Live ladder, no stop | Fixed stop 1 ATR, target 1 ATR (reference) | 1,566 / 1,703 | 33 / 33 | 100 / 100 | -1.52 / -1.58 | -4.66 / -12.72 | -3.13 / -11.15 (± 5.35 / 7.29) |
| Live ladder, basket stop $60 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,566 / 1,703 | 33 / 33 | 92 / 89 | -1.52 / -1.58 | -3.64 / -5.56 | -2.12 / -3.98 (± 0.37 / 0.51) |
| Live ladder, basket stop $200 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,566 / 1,703 | 33 / 33 | 98 / 97 | -1.52 / -1.58 | -3.75 / -5.49 | -2.23 / -3.91 (± 0.71 / 0.92) |
| Budget 1 R, 2 adds 0.17 ATR apart | Budget 1 R, no add | 2,578 / 2,892 | 53 / 52 | 35 / 30 | -1.02 / -1.15 | -1.16 / -1.85 | -0.14 / -0.70 (± 0.09 / 0.11) |
| Budget 2 R, 2 adds 0.33 ATR apart | Budget 2 R, no add | 2,104 / 2,359 | 66 / 65 | 51 / 48 | -1.75 / -2.02 | -1.94 / -2.50 | -0.19 / -0.48 (± 0.16 / 0.16) |
| Budget 3 R, 1 add 1 ATR apart | Budget 3 R, no add | 1,174 / 1,327 | 56 / 56 | 48 / 47 | -5.23 / -5.62 | -5.52 / -6.17 | -0.28 / -0.55 (± 0.29 / 0.30) |
| Budget 3 R, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,735 / 1,971 | 70 / 70 | 58 / 56 | -2.73 / -2.79 | -3.02 / -3.42 | -0.29 / -0.63 (± 0.27 / 0.25) |
| Budget 3 R, 3 adds 0.3 ATR apart | Budget 3 R, no add | 2,179 / 2,434 | 76 / 76 | 60 / 58 | -1.64 / -1.71 | -2.09 / -2.36 | -0.44 / -0.65 (± 0.23 / 0.26) |
| Budget 3 R, 4 adds 0.2 ATR apart | Budget 3 R, no add | 2,479 / 2,750 | 79 / 79 | 60 / 57 | -1.13 / -1.18 | -1.44 / -2.00 | -0.31 / -0.82 (± 0.25 / 0.25) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | Budget 3 R, no add | 1,735 / 1,971 | 70 / 70 | 58 / 56 | -2.73 / -2.79 | -3.02 / -3.42 | -0.29 / -0.63 (± 0.27 / 0.25) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,735 / 1,971 | 58 / 56 | 58 / 56 | -3.02 / -3.42 | -3.02 / -3.42 | +0.00 / +0.00 (± 0.00 / 0.00) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | 1,735 / 1,971 | 58 / 56 | 58 / 56 | -3.02 / -3.42 | -3.02 / -3.42 | +0.00 / +0.00 (± 0.00 / 0.00) |
| Add when the M5 MACD histogram turns | Budget 3 R, no add | 1,174 / 1,381 | 60 / 61 | 50 / 51 | -4.48 / -4.56 | -4.93 / -5.04 | -0.45 / -0.48 (± 0.30 / 0.32) |
| Add when the M15 MACD histogram turns | Budget 3 R, no add | 891 / 1,052 | 57 / 59 | 48 / 47 | -5.21 / -5.14 | -5.82 / -6.00 | -0.61 / -0.86 (± 0.34 / 0.33) |
| Add when the M5 RSI comes back through 35 / 65 | Budget 3 R, no add | 943 / 1,120 | 57 / 57 | 48 / 46 | -5.16 / -5.38 | -5.67 / -6.15 | -0.51 / -0.76 (± 0.30 / 0.31) |
| Add when the M15 RSI comes back through 35 / 65 | Budget 3 R, no add | 544 / 636 | 52 / 53 | 46 / 42 | -6.09 / -6.35 | -6.14 / -7.78 | -0.05 / -1.42 (± 0.44 / 0.47) |
| Pyramid, 2 adds | Trailing stop 1 ATR, no target | 1,242 / 1,379 | 97 / 93 | 58 / 55 | +4.89 / +5.62 | +4.59 / +5.17 | -0.30 / -0.45 (± 0.21 / 0.28) |
| Pyramid, 4 adds | Trailing stop 1 ATR, no target | 1,242 / 1,379 | 97 / 93 | 58 / 55 | +4.89 / +5.62 | +4.43 / +5.18 | -0.46 / -0.44 (± 0.23 / 0.34) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | Fixed stop 1 ATR, target 1 ATR (reference) | 1,755 / 1,941 | 0 / 0 | 87 / 84 | -5.14 / -5.71 | -5.93 / -8.02 | -0.79 / -2.31 (± 0.63 / 0.90) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | Fixed stop 1 ATR, target 1 ATR (reference) | 2,337 / 2,627 | 25 / 26 | 65 / 62 | -2.61 / -2.66 | -4.46 / -5.94 | -1.84 / -3.28 (± 0.25 / 0.31) |
<!-- /table -->

</details>

### 5. A hedge lock is a close and a later re-entry

Long from an ask of A, stop level reached at a bid of b1. Lock: sell one unit at b1. From here the two
positions together are worth (b1 - A) minus the spread it will cost to get out, whatever the market
does: the same as having closed at b1. To get out of the lock one leg is closed. If the short is
bought back at an ask of a2 and the long is later sold at b3, the total is (b1 - a2) + (b3 - A). Had
the long been closed at b1 and a new long bought at a2 and sold at b3, the total would be
(b1 - A) + (b3 - a2). These are the same four fills and the same money. The simulation runs both as
separate rows, with different code, and agrees:

| | Hedge lock, unlocked by the next vote signal | Close at -1 ATR, re-enter on the next vote signal |
|---|---|---|
| Result per entry, all twelve cells | identical | identical |
| Largest difference on any of the 32,510 baskets that ran to their end | 0.000000000001 USD | |
| Positions held at once | 2 | 1 |

The other 43 of the 32,553 baskets were cut off by the end of a period or by a hole in the BTC
archive. Where a lock was still on at that moment it cost one spread more than its twin, which was
already flat: a lock always has to be closed, a closed position does not.

What a lock adds is the second leg's spread when no new trade is wanted. The row "both legs closed
4 h later" is the plain stop plus that one spread, on the 49 to 54 % of baskets that reach the stop:

| Change against the plain stop, per entry | Gold | BTC |
|---|---|---|
| DEV | -$0.11 (± 0.005) | -$0.07 (± 0.003) |
| CONFIRM | -$0.09 (± 0.003) | -$0.18 (± 0.010) |

A broker may also charge swap on both legs. There is no market view a lock can express that a flat
account cannot.

### 6. The entries

The mechanisms were the subject here, but the reference rows also say what the entries are worth.

| Reference trade (stop 1 ATR, target 1 ATR), USD per entry | Gold DEV | Gold CONFIRM | BTC DEV | BTC CONFIRM |
|---|---|---|---|---|
| with the H1 trend | +0.46 ± 0.57 | -0.08 ± 0.23 | -0.00 ± 0.12 | -0.39 ± 0.14 |
| votes only | -0.37 ± 0.42 | -0.11 ± 0.16 | -0.05 ± 0.08 | -0.39 ± 0.09 |
| random | +0.17 ± 0.44 | -0.25 ± 0.16 | -0.19 ± 0.08 | -0.10 ± 0.12 |
| spread paid per entry | 0.23 | 0.18 | 0.14 | 0.34 |

No list is distinguishable from "loses the spread". The small plus of the with-trend list on gold in
DEV is not there in CONFIRM. The V2 exit ($20 stop, $20 target, a much longer trade than 1 ATR on
BTC and on gold before 2026) is the one row above zero in all four with-trend cells and in 10 of 12
half-years; on CONFIRM, which it was never fitted to, it made +0.69 ± 0.86 on gold and +1.01 ± 0.69
on BTC per entry. Read together that is about 1.6 standard errors: worth carrying forward, not yet an
edge.

<details><summary>Expectancy per entry by half-year, all six lists</summary>

Gold, with the H1 trend:

<!-- table halves:XAUUSDm:trend -->
| Mechanism | DEV 2025 H2 (n=493) | DEV 2026 H1 (n=526) | DEV 2026 H2 (n=418) | CONFIRM 2024 H1 (n=480) | CONFIRM 2024 H2 (n=597) | CONFIRM 2025 H1 (n=566) |
|---|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | +0.23 (± 0.77) | +0.43 (± 1.35) | +0.79 (± 0.58) | -0.56 (± 0.30) | +0.47 (± 0.30) | -0.27 (± 0.53) |
| Fixed stop 2 ATR, target 2 ATR | +1.76 (± 1.89) | -3.88 (± 6.40) | -0.62 (± 1.30) | -1.55 (± 0.55) | +0.45 (± 0.72) | +0.50 (± 1.37) |
| Fixed stop 1 ATR, target 2 ATR | +1.05 (± 1.21) | -0.59 (± 3.82) | +0.58 (± 0.94) | -0.81 (± 0.38) | +0.50 (± 0.48) | -0.24 (± 0.75) |
| Fixed stop 2 ATR, target 1 ATR | +0.19 (± 1.28) | +0.24 (± 2.54) | +0.91 (± 0.79) | -0.93 (± 0.44) | +0.64 (± 0.47) | +0.15 (± 1.11) |
| Fixed stop $20, target $20 (the V2 exit) | +3.12 (± 1.43) | +0.29 (± 1.02) | +0.05 (± 0.65) | -0.22 (± 1.77) | +0.90 (± 1.51) | +1.23 (± 1.22) |
| Live ladder, no stop | +1.00 (± 0.00) | +1.00 (± 0.00) | +1.00 (± 0.00) | +1.00 (± 0.00) | +1.00 (± 0.00) | +1.00 (± 0.00) |
| Live ladder, basket stop $60 | -0.23 (± 0.43) | -0.51 (± 0.40) | -0.60 (± 0.46) | -0.65 (± 0.40) | -0.02 (± 0.40) | -0.24 (± 0.40) |
| Live ladder, basket stop $200 | +0.60 (± 0.41) | -0.61 (± 0.77) | -0.44 (± 0.80) | -0.25 (± 0.69) | -0.35 (± 0.79) | -0.78 (± 0.88) |
| Budget 1 R, no add | +0.33 (± 0.50) | +0.04 (± 1.11) | +0.28 (± 0.42) | -0.31 (± 0.20) | +0.22 (± 0.21) | -0.68 (± 0.43) |
| Budget 1 R, 2 adds 0.17 ATR apart | +0.88 (± 0.64) | -0.43 (± 1.35) | +0.46 (± 0.71) | -0.63 (± 0.36) | -0.00 (± 0.28) | -1.02 (± 0.49) |
| Budget 2 R, no add | +0.47 (± 1.04) | +0.45 (± 2.15) | +0.37 (± 0.60) | -0.38 (± 0.28) | +0.44 (± 0.30) | -0.55 (± 0.83) |
| Budget 2 R, 2 adds 0.33 ATR apart | +0.08 (± 1.20) | -0.67 (± 2.05) | +0.43 (± 0.85) | -0.71 (± 0.40) | +0.36 (± 0.40) | -1.41 (± 0.82) |
| Budget 3 R, no add | +0.65 (± 1.24) | +0.74 (± 2.71) | +0.00 (± 0.76) | -0.56 (± 0.38) | +0.43 (± 0.30) | -0.64 (± 1.09) |
| Budget 3 R, 1 add 1 ATR apart | +0.03 (± 1.35) | +0.67 (± 2.74) | +0.71 (± 1.02) | -0.86 (± 0.46) | +0.22 (± 0.40) | -0.85 (± 1.27) |
| Budget 3 R, 2 adds 0.5 ATR apart | -0.87 (± 1.50) | +1.87 (± 2.91) | +0.31 (± 1.27) | -0.62 (± 0.48) | +0.41 (± 0.44) | -1.17 (± 1.43) |
| Budget 3 R, 3 adds 0.3 ATR apart | -0.28 (± 1.84) | -2.90 (± 2.76) | +0.85 (± 1.47) | -1.18 (± 0.56) | +0.61 (± 0.50) | -1.36 (± 1.44) |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.01 (± 1.78) | -0.94 (± 2.82) | +1.74 (± 1.41) | -1.23 (± 0.55) | +0.30 (± 0.54) | -2.20 (± 1.36) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.27 (± 1.25) | +0.63 (± 1.55) | +0.47 (± 1.24) | -0.62 (± 0.48) | +0.41 (± 0.44) | -1.46 (± 1.49) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | +0.16 (± 1.23) | +0.22 (± 1.61) | +0.92 (± 1.20) | -0.59 (± 0.46) | +0.37 (± 0.42) | -1.57 (± 1.53) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.17 (± 1.26) | -0.04 (± 1.54) | +1.01 (± 1.10) | -0.67 (± 0.42) | +0.12 (± 0.43) | -1.35 (± 1.28) |
| Add when the M5 MACD histogram turns | -0.08 (± 1.36) | +1.11 (± 2.80) | +0.47 (± 0.92) | -0.45 (± 0.44) | +0.23 (± 0.37) | -1.02 (± 1.05) |
| Add when the M15 MACD histogram turns | +0.79 (± 1.17) | +2.06 (± 2.76) | +0.35 (± 0.99) | -0.50 (± 0.42) | +0.30 (± 0.33) | -0.48 (± 0.96) |
| Add when the M5 RSI comes back through 35 / 65 | +0.34 (± 1.57) | +2.05 (± 2.66) | +0.28 (± 1.05) | -0.42 (± 0.42) | -0.10 (± 0.38) | -0.65 (± 1.02) |
| Add when the M15 RSI comes back through 35 / 65 | +0.39 (± 1.58) | +2.30 (± 2.67) | -0.08 (± 1.03) | -0.59 (± 0.40) | +0.18 (± 0.35) | -0.40 (± 0.84) |
| Break-even at +0.5 ATR (stop 1, target 1) | +0.30 (± 0.62) | +0.14 (± 1.41) | +0.66 (± 0.49) | -0.46 (± 0.26) | +0.24 (± 0.24) | -0.49 (± 0.55) |
| Break-even at +1 ATR (stop 1, target 2) | +0.36 (± 0.93) | -0.66 (± 2.32) | +0.65 (± 0.80) | -0.59 (± 0.39) | +0.45 (± 0.38) | -0.38 (± 0.63) |
| Trailing stop 1 ATR, no target | +0.92 (± 1.04) | -0.53 (± 2.19) | +1.87 (± 0.73) | -0.77 (± 0.34) | +0.16 (± 0.29) | -0.11 (± 0.73) |
| Trailing stop 2 ATR, no target | +1.02 (± 1.89) | +0.62 (± 6.16) | -1.63 (± 1.69) | -1.61 (± 0.75) | +1.16 (± 0.85) | +1.16 (± 1.71) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | +0.53 (± 0.98) | +0.74 (± 1.94) | +1.25 (± 0.68) | -0.62 (± 0.33) | +0.29 (± 0.30) | -0.39 (± 0.62) |
| Pyramid, 2 adds | +1.61 (± 1.71) | -0.27 (± 3.60) | +2.60 (± 1.69) | -1.24 (± 0.45) | -0.49 (± 0.41) | -0.26 (± 1.18) |
| Pyramid, 4 adds | +1.57 (± 1.84) | +0.12 (± 3.90) | +2.73 (± 2.02) | -1.29 (± 0.44) | -0.64 (± 0.41) | -0.23 (± 1.25) |
| Hedge lock, unlocked by the next vote signal | -0.34 (± 0.89) | +1.15 (± 1.52) | +1.33 (± 0.74) | -0.45 (± 0.46) | +0.67 (± 0.36) | -0.49 (± 0.94) |
| Close at -1 ATR, re-enter on the next vote signal | -0.34 (± 0.89) | +1.15 (± 1.52) | +1.33 (± 0.74) | -0.45 (± 0.46) | +0.67 (± 0.36) | -0.49 (± 0.94) |
| Hedge lock, both legs closed 4 h later | +0.15 (± 0.77) | +0.29 (± 1.35) | +0.67 (± 0.58) | -0.68 (± 0.30) | +0.40 (± 0.31) | -0.35 (± 0.53) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -1.86 (± 2.37) | -4.27 (± 4.69) | +0.36 (± 3.66) | -1.08 (± 0.88) | -0.27 (± 0.98) | +0.52 (± 2.58) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -0.34 (± 1.43) | -3.32 (± 2.78) | -1.63 (± 1.84) | -2.07 (± 0.56) | -0.36 (± 0.49) | -0.20 (± 0.99) |
| Stop and reverse, same size | -0.09 (± 0.59) | +0.34 (± 1.20) | +0.41 (± 0.83) | -0.53 (± 0.39) | +0.43 (± 0.28) | -0.37 (± 0.43) |
| Stop and reverse, double size | -0.40 (± 0.98) | +0.26 (± 1.73) | +0.04 (± 1.31) | -0.50 (± 0.60) | +0.38 (± 0.36) | -0.47 (± 0.81) |
| Martingale: double after a loss, up to x8 | +1.09 (± 2.79) | +5.81 (± 2.49) | +4.66 (± 1.43) | -1.68 (± 1.38) | +0.94 (± 1.04) | -0.25 (± 2.43) |
| Anti-martingale: double after a win, up to x8 | +0.27 (± 2.01) | +0.96 (± 5.38) | +0.84 (± 2.04) | -0.92 (± 0.84) | +2.37 (± 1.46) | -1.75 (± 1.33) |
| Daily loss limit 1 R | +0.22 (± 0.99) | -0.30 (± 1.79) | -0.18 (± 1.07) | -0.72 (± 0.38) | +0.60 (± 0.35) | -0.35 (± 0.60) |
| Daily loss limit 2 R | -0.35 (± 0.77) | -0.36 (± 1.69) | +0.64 (± 0.65) | -0.47 (± 0.30) | +0.28 (± 0.36) | -0.49 (± 0.44) |
<!-- /table -->

Gold, votes only:

<!-- table halves:XAUUSDm:votes -->
| Mechanism | DEV 2025 H2 (n=852) | DEV 2026 H1 (n=928) | DEV 2026 H2 (n=756) | CONFIRM 2024 H1 (n=862) | CONFIRM 2024 H2 (n=1,057) | CONFIRM 2025 H1 (n=1,034) |
|---|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | -1.20 (± 0.53) | +0.15 (± 0.91) | -0.07 (± 0.63) | -0.38 (± 0.15) | -0.01 (± 0.14) | +0.02 (± 0.42) |
| Fixed stop 2 ATR, target 2 ATR | +0.30 (± 0.65) | -1.41 (± 2.33) | -1.73 (± 1.27) | -0.55 (± 0.47) | -0.24 (± 0.40) | -0.59 (± 0.72) |
| Fixed stop 1 ATR, target 2 ATR | -0.45 (± 0.62) | +0.54 (± 1.51) | +0.10 (± 0.87) | -0.25 (± 0.28) | -0.11 (± 0.23) | -0.23 (± 0.53) |
| Fixed stop 2 ATR, target 1 ATR | -0.53 (± 0.59) | -2.04 (± 1.23) | -0.28 (± 0.91) | -0.65 (± 0.27) | +0.06 (± 0.27) | -0.44 (± 0.64) |
| Fixed stop $20, target $20 (the V2 exit) | +0.32 (± 0.55) | +0.01 (± 0.54) | -0.81 (± 0.67) | -1.01 (± 0.82) | -0.02 (± 0.52) | -0.87 (± 0.84) |
| Live ladder, no stop | -15.01 (± 15.92) | +1.00 (± 0.00) | +1.00 (± 0.00) | -45.50 (± 46.11) | +1.00 (± 0.00) | +1.00 (± 0.00) |
| Live ladder, basket stop $60 | -0.63 (± 0.35) | -1.36 (± 0.47) | -0.77 (± 0.42) | -0.49 (± 0.23) | -0.73 (± 0.31) | -0.84 (± 0.32) |
| Live ladder, basket stop $200 | -1.11 (± 0.63) | -0.56 (± 0.59) | -0.59 (± 0.55) | -0.40 (± 0.50) | -0.71 (± 0.55) | +0.22 (± 0.45) |
| Budget 1 R, no add | -0.44 (± 0.38) | +0.45 (± 0.52) | -0.33 (± 0.52) | -0.11 (± 0.12) | -0.01 (± 0.14) | -0.48 (± 0.36) |
| Budget 1 R, 2 adds 0.17 ATR apart | +0.26 (± 0.53) | +0.28 (± 0.68) | -0.20 (± 0.55) | -0.40 (± 0.24) | -0.59 (± 0.21) | -0.67 (± 0.40) |
| Budget 2 R, no add | +0.45 (± 0.40) | -0.31 (± 1.11) | -0.61 (± 0.71) | -0.34 (± 0.22) | -0.09 (± 0.15) | -0.78 (± 0.56) |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.68 (± 0.67) | +0.43 (± 1.11) | -0.37 (± 0.99) | -0.54 (± 0.23) | -0.03 (± 0.24) | -0.93 (± 0.67) |
| Budget 3 R, no add | +0.36 (± 0.57) | -0.58 (± 1.40) | -1.04 (± 0.92) | -0.39 (± 0.31) | -0.17 (± 0.19) | -1.34 (± 0.79) |
| Budget 3 R, 1 add 1 ATR apart | +0.27 (± 0.59) | -1.78 (± 1.84) | -0.98 (± 0.95) | -0.66 (± 0.31) | -0.36 (± 0.20) | -1.19 (± 0.83) |
| Budget 3 R, 2 adds 0.5 ATR apart | -0.57 (± 0.82) | -0.01 (± 1.54) | -1.63 (± 1.27) | -0.40 (± 0.25) | -0.03 (± 0.26) | -1.18 (± 0.98) |
| Budget 3 R, 3 adds 0.3 ATR apart | -1.00 (± 1.24) | -0.88 (± 1.66) | -1.24 (± 1.12) | -0.51 (± 0.39) | +0.01 (± 0.30) | -1.24 (± 0.97) |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.81 (± 0.92) | -0.13 (± 1.77) | -0.80 (± 1.70) | -0.81 (± 0.30) | -0.36 (± 0.36) | -1.46 (± 1.02) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.84 (± 0.83) | -0.42 (± 1.07) | -1.47 (± 1.27) | -0.40 (± 0.25) | -0.03 (± 0.26) | -1.17 (± 0.93) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | -0.72 (± 0.77) | -0.10 (± 1.12) | -1.32 (± 1.28) | -0.34 (± 0.25) | -0.09 (± 0.26) | -1.20 (± 0.92) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.86 (± 0.63) | +0.16 (± 1.08) | -1.21 (± 1.29) | -0.38 (± 0.22) | -0.06 (± 0.25) | -1.08 (± 0.80) |
| Add when the M5 MACD histogram turns | +0.02 (± 0.52) | -1.62 (± 1.90) | -1.16 (± 0.90) | -0.64 (± 0.30) | -0.43 (± 0.23) | -1.17 (± 0.74) |
| Add when the M15 MACD histogram turns | +0.66 (± 0.70) | -0.47 (± 1.46) | -0.72 (± 0.97) | -0.66 (± 0.28) | -0.16 (± 0.24) | -0.96 (± 0.68) |
| Add when the M5 RSI comes back through 35 / 65 | +0.09 (± 0.60) | -0.28 (± 1.55) | -0.90 (± 0.99) | -0.46 (± 0.28) | -0.34 (± 0.24) | -1.21 (± 0.79) |
| Add when the M15 RSI comes back through 35 / 65 | +0.46 (± 0.59) | +0.75 (± 1.39) | -0.96 (± 0.97) | -0.57 (± 0.27) | -0.38 (± 0.18) | -0.78 (± 0.68) |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.68 (± 0.44) | +0.33 (± 0.58) | +0.02 (± 0.60) | -0.14 (± 0.14) | -0.09 (± 0.15) | -0.28 (± 0.40) |
| Break-even at +1 ATR (stop 1, target 2) | -1.09 (± 0.59) | +0.47 (± 1.32) | -0.04 (± 0.72) | -0.31 (± 0.23) | -0.11 (± 0.18) | +0.04 (± 0.45) |
| Trailing stop 1 ATR, no target | -0.99 (± 0.61) | -1.93 (± 0.77) | +0.93 (± 0.76) | -0.35 (± 0.21) | -0.18 (± 0.16) | -0.20 (± 0.51) |
| Trailing stop 2 ATR, no target | +0.51 (± 1.36) | +0.59 (± 2.79) | -1.17 (± 2.02) | -0.80 (± 0.51) | +0.05 (± 0.50) | -0.31 (± 1.01) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | -1.32 (± 0.59) | +0.06 (± 0.87) | +0.21 (± 0.69) | -0.46 (± 0.16) | -0.15 (± 0.14) | +0.02 (± 0.49) |
| Pyramid, 2 adds | -1.57 (± 0.95) | -3.62 (± 1.49) | +1.30 (± 1.21) | -0.75 (± 0.34) | -0.68 (± 0.22) | -0.57 (± 0.79) |
| Pyramid, 4 adds | -1.71 (± 1.00) | -3.59 (± 1.76) | +1.22 (± 1.26) | -0.81 (± 0.34) | -0.77 (± 0.24) | -0.65 (± 0.82) |
| Hedge lock, unlocked by the next vote signal | -1.91 (± 0.86) | +0.87 (± 1.72) | -0.01 (± 1.00) | -0.46 (± 0.26) | +0.01 (± 0.23) | +0.10 (± 0.67) |
| Close at -1 ATR, re-enter on the next vote signal | -1.91 (± 0.86) | +0.87 (± 1.72) | -0.01 (± 1.00) | -0.46 (± 0.26) | +0.01 (± 0.23) | +0.10 (± 0.67) |
| Hedge lock, both legs closed 4 h later | -1.28 (± 0.53) | +0.01 (± 0.92) | -0.20 (± 0.64) | -0.49 (± 0.15) | -0.10 (± 0.15) | -0.07 (± 0.42) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -1.64 (± 2.20) | -2.14 (± 4.38) | +4.95 (± 2.77) | -0.49 (± 0.73) | -2.03 (± 1.09) | +1.75 (± 1.75) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.27 (± 1.34) | -2.97 (± 2.14) | -1.44 (± 1.57) | -1.46 (± 0.50) | -1.01 (± 0.49) | -0.02 (± 0.63) |
| Stop and reverse, same size | -1.70 (± 0.77) | +1.38 (± 1.49) | +0.09 (± 0.77) | -0.39 (± 0.28) | +0.11 (± 0.21) | +0.41 (± 0.34) |
| Stop and reverse, double size | -2.21 (± 1.05) | +2.61 (± 2.27) | +0.26 (± 1.08) | -0.41 (± 0.50) | +0.24 (± 0.33) | +0.81 (± 0.44) |
| Martingale: double after a loss, up to x8 | -2.74 (± 1.81) | +0.31 (± 2.50) | -0.10 (± 2.08) | -0.52 (± 0.57) | +0.37 (± 0.57) | -0.53 (± 1.45) |
| Anti-martingale: double after a win, up to x8 | -1.71 (± 2.10) | +0.30 (± 3.05) | -1.69 (± 1.18) | -0.80 (± 0.55) | +0.09 (± 0.59) | -0.48 (± 1.32) |
| Daily loss limit 1 R | -1.10 (± 0.97) | -0.40 (± 0.98) | -0.35 (± 0.88) | -0.28 (± 0.27) | -0.11 (± 0.24) | -0.69 (± 0.70) |
| Daily loss limit 2 R | -1.21 (± 0.53) | -0.42 (± 0.79) | +0.29 (± 0.68) | -0.26 (± 0.20) | -0.00 (± 0.20) | +0.11 (± 0.41) |
<!-- /table -->

Gold, random:

<!-- table halves:XAUUSDm:random -->
| Mechanism | DEV 2025 H2 (n=843) | DEV 2026 H1 (n=936) | DEV 2026 H2 (n=745) | CONFIRM 2024 H1 (n=779) | CONFIRM 2024 H2 (n=1,018) | CONFIRM 2025 H1 (n=1,047) |
|---|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | +0.07 (± 0.51) | +0.40 (± 1.06) | +0.01 (± 0.42) | -0.13 (± 0.23) | -0.28 (± 0.21) | -0.31 (± 0.36) |
| Fixed stop 2 ATR, target 2 ATR | -0.41 (± 1.11) | +1.30 (± 2.09) | -0.39 (± 1.01) | -0.45 (± 0.35) | -0.57 (± 0.37) | +0.84 (± 0.76) |
| Fixed stop 1 ATR, target 2 ATR | +0.00 (± 0.78) | +1.14 (± 1.73) | +0.17 (± 0.75) | -0.15 (± 0.26) | -0.57 (± 0.22) | +0.30 (± 0.51) |
| Fixed stop 2 ATR, target 1 ATR | -0.14 (± 0.86) | +0.48 (± 1.59) | -0.38 (± 0.74) | -0.26 (± 0.28) | -0.50 (± 0.27) | +0.07 (± 0.45) |
| Fixed stop $20, target $20 (the V2 exit) | -0.77 (± 0.91) | -0.29 (± 0.60) | +0.05 (± 0.69) | +0.42 (± 0.67) | -0.94 (± 0.54) | -0.36 (± 0.75) |
| Live ladder, no stop | +1.00 (± 0.00) | +1.01 (± 0.01) | +1.00 (± 0.00) | -39.51 (± 40.67) | +1.01 (± 0.01) | +1.00 (± 0.00) |
| Live ladder, basket stop $60 | -2.04 (± 0.54) | -3.62 (± 0.48) | -1.78 (± 0.40) | -1.82 (± 0.51) | -0.19 (± 0.27) | -1.70 (± 0.38) |
| Live ladder, basket stop $200 | -1.14 (± 0.66) | -2.86 (± 0.89) | -1.97 (± 0.82) | -1.58 (± 0.64) | -0.37 (± 0.53) | -0.54 (± 0.52) |
| Budget 1 R, no add | -0.23 (± 0.31) | -0.34 (± 0.80) | -0.52 (± 0.44) | -0.06 (± 0.14) | -0.04 (± 0.14) | -0.30 (± 0.26) |
| Budget 1 R, 2 adds 0.17 ATR apart | -0.42 (± 0.31) | -3.04 (± 0.87) | -0.83 (± 0.32) | -0.46 (± 0.24) | +0.00 (± 0.19) | -0.16 (± 0.36) |
| Budget 2 R, no add | -0.32 (± 0.42) | +0.15 (± 1.14) | -0.52 (± 0.74) | -0.20 (± 0.21) | -0.12 (± 0.20) | -0.13 (± 0.35) |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.82 (± 0.73) | +0.76 (± 1.03) | -1.20 (± 0.68) | -0.26 (± 0.30) | -0.18 (± 0.23) | -0.66 (± 0.56) |
| Budget 3 R, no add | -1.09 (± 0.65) | +0.14 (± 1.35) | -0.80 (± 0.85) | -0.31 (± 0.19) | -0.19 (± 0.26) | -0.28 (± 0.42) |
| Budget 3 R, 1 add 1 ATR apart | -0.04 (± 0.44) | -0.50 (± 1.78) | -0.46 (± 1.15) | -0.64 (± 0.31) | -0.29 (± 0.28) | -0.23 (± 0.46) |
| Budget 3 R, 2 adds 0.5 ATR apart | -0.11 (± 0.49) | +0.96 (± 1.24) | -0.78 (± 1.09) | -0.35 (± 0.38) | -0.22 (± 0.29) | +0.22 (± 0.45) |
| Budget 3 R, 3 adds 0.3 ATR apart | +0.03 (± 0.68) | +2.36 (± 1.68) | -2.08 (± 1.22) | -0.31 (± 0.35) | -0.05 (± 0.34) | -0.89 (± 0.68) |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.93 (± 0.95) | +0.77 (± 1.36) | -2.52 (± 1.05) | -0.42 (± 0.47) | -0.51 (± 0.34) | -1.09 (± 0.87) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.23 (± 0.57) | +0.18 (± 0.88) | -0.82 (± 1.05) | -0.35 (± 0.38) | -0.22 (± 0.29) | +0.10 (± 0.48) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | -0.34 (± 0.65) | +0.25 (± 0.87) | -1.05 (± 1.02) | -0.26 (± 0.32) | -0.19 (± 0.27) | +0.10 (± 0.49) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.17 (± 0.66) | +0.10 (± 0.91) | -1.23 (± 1.07) | -0.41 (± 0.34) | -0.24 (± 0.29) | +0.27 (± 0.41) |
| Add when the M5 MACD histogram turns | -0.03 (± 0.51) | +0.81 (± 1.67) | -0.84 (± 0.99) | -0.49 (± 0.32) | -0.26 (± 0.26) | -0.34 (± 0.38) |
| Add when the M15 MACD histogram turns | -1.10 (± 0.54) | +0.65 (± 1.33) | -1.57 (± 1.03) | -0.19 (± 0.26) | -0.33 (± 0.32) | -0.31 (± 0.42) |
| Add when the M5 RSI comes back through 35 / 65 | -0.53 (± 0.67) | +0.82 (± 1.19) | -0.50 (± 0.98) | -0.34 (± 0.27) | -0.39 (± 0.27) | -0.51 (± 0.36) |
| Add when the M15 RSI comes back through 35 / 65 | -1.22 (± 0.68) | +0.78 (± 1.12) | -1.03 (± 0.81) | -0.29 (± 0.22) | -0.31 (± 0.26) | -0.05 (± 0.42) |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.01 (± 0.45) | -0.51 (± 0.83) | -0.39 (± 0.50) | -0.09 (± 0.18) | -0.10 (± 0.17) | +0.00 (± 0.31) |
| Break-even at +1 ATR (stop 1, target 2) | +0.38 (± 0.66) | +1.28 (± 1.32) | -0.24 (± 0.59) | -0.19 (± 0.27) | -0.35 (± 0.22) | +0.17 (± 0.42) |
| Trailing stop 1 ATR, no target | -0.76 (± 0.39) | -0.33 (± 1.05) | +0.24 (± 0.73) | -0.38 (± 0.24) | -0.25 (± 0.19) | +0.60 (± 0.47) |
| Trailing stop 2 ATR, no target | +1.55 (± 1.61) | +2.15 (± 2.75) | -0.77 (± 1.83) | -0.06 (± 0.45) | -0.62 (± 0.46) | +1.43 (± 0.87) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | +0.02 (± 0.50) | +0.73 (± 1.28) | +0.14 (± 0.47) | -0.17 (± 0.25) | -0.35 (± 0.21) | -0.13 (± 0.39) |
| Pyramid, 2 adds | -1.06 (± 0.64) | -0.24 (± 1.85) | +0.64 (± 1.38) | -0.50 (± 0.44) | -0.63 (± 0.27) | +1.01 (± 0.78) |
| Pyramid, 4 adds | -1.21 (± 0.71) | -0.26 (± 2.16) | +0.96 (± 1.59) | -0.51 (± 0.48) | -0.67 (± 0.28) | +0.85 (± 0.80) |
| Hedge lock, unlocked by the next vote signal | -0.94 (± 0.58) | +0.53 (± 1.23) | -0.89 (± 0.64) | -0.10 (± 0.28) | -0.21 (± 0.28) | -0.38 (± 0.43) |
| Close at -1 ATR, re-enter on the next vote signal | -0.94 (± 0.58) | +0.53 (± 1.23) | -0.89 (± 0.64) | -0.10 (± 0.28) | -0.21 (± 0.28) | -0.38 (± 0.43) |
| Hedge lock, both legs closed 4 h later | -0.01 (± 0.51) | +0.27 (± 1.06) | -0.12 (± 0.43) | -0.24 (± 0.24) | -0.37 (± 0.21) | -0.40 (± 0.36) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -1.39 (± 2.41) | -0.63 (± 3.77) | -1.92 (± 2.21) | -0.73 (± 1.00) | +0.32 (± 0.86) | +1.36 (± 1.42) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.01 (± 0.83) | -3.78 (± 1.87) | -1.09 (± 1.35) | -1.05 (± 0.53) | -1.27 (± 0.41) | -0.59 (± 0.81) |
| Stop and reverse, same size | -0.10 (± 0.58) | +0.51 (± 0.97) | -0.04 (± 0.67) | +0.07 (± 0.27) | -0.27 (± 0.24) | -0.21 (± 0.40) |
| Stop and reverse, double size | -0.28 (± 0.79) | +0.62 (± 1.46) | -0.09 (± 1.07) | +0.28 (± 0.37) | -0.26 (± 0.34) | -0.10 (± 0.56) |
| Martingale: double after a loss, up to x8 | +0.07 (± 2.16) | +2.62 (± 3.67) | -0.15 (± 2.21) | -0.79 (± 0.79) | -0.83 (± 0.88) | -0.48 (± 1.04) |
| Anti-martingale: double after a win, up to x8 | -0.35 (± 1.56) | -0.93 (± 3.30) | +0.47 (± 1.38) | +0.15 (± 0.80) | -1.54 (± 0.44) | -1.19 (± 0.98) |
| Daily loss limit 1 R | +0.25 (± 0.66) | +0.83 (± 1.99) | -0.59 (± 0.77) | +0.03 (± 0.31) | -0.48 (± 0.31) | -0.28 (± 0.64) |
| Daily loss limit 2 R | +0.37 (± 0.48) | +0.24 (± 1.46) | -0.68 (± 0.56) | -0.24 (± 0.27) | -0.29 (± 0.24) | -0.14 (± 0.41) |
<!-- /table -->

BTC, with the H1 trend:

<!-- table halves:BTCUSDm:trend -->
| Mechanism | DEV 2025 H2 (n=584) | DEV 2026 H1 (n=789) | DEV 2026 H2 (n=597) | CONFIRM 2024 H1 (n=515) | CONFIRM 2024 H2 (n=788) | CONFIRM 2025 H1 (n=783) |
|---|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | +0.05 (± 0.24) | +0.12 (± 0.16) | -0.22 (± 0.22) | -0.83 (± 0.18) | -0.12 (± 0.17) | -0.36 (± 0.30) |
| Fixed stop 2 ATR, target 2 ATR | +0.37 (± 0.73) | +0.67 (± 0.36) | +0.17 (± 0.46) | -0.66 (± 0.48) | +1.09 (± 0.64) | -0.30 (± 0.76) |
| Fixed stop 1 ATR, target 2 ATR | +0.30 (± 0.37) | +0.12 (± 0.22) | -0.05 (± 0.34) | -0.53 (± 0.27) | +0.23 (± 0.31) | -0.48 (± 0.54) |
| Fixed stop 2 ATR, target 1 ATR | +0.26 (± 0.39) | +0.38 (± 0.28) | -0.11 (± 0.31) | -0.86 (± 0.28) | +0.10 (± 0.40) | -0.17 (± 0.44) |
| Fixed stop $20, target $20 (the V2 exit) | +2.84 (± 1.35) | +1.27 (± 1.02) | -2.43 (± 1.87) | +1.93 (± 1.52) | +1.01 (± 1.13) | +0.40 (± 1.06) |
| Live ladder, no stop | +1.00 (± 0.00) | +1.00 (± 0.00) | +1.00 (± 0.00) | -0.12 (± 1.17) | +1.00 (± 0.00) | +1.00 (± 0.00) |
| Live ladder, basket stop $60 | -0.25 (± 0.33) | -0.70 (± 0.38) | -0.23 (± 0.45) | -2.08 (± 0.59) | -1.55 (± 0.38) | -1.18 (± 0.37) |
| Live ladder, basket stop $200 | -0.03 (± 0.56) | -0.27 (± 0.63) | -0.01 (± 0.55) | -2.51 (± 1.30) | -2.06 (± 0.75) | -2.08 (± 1.06) |
| Budget 1 R, no add | -0.05 (± 0.19) | +0.02 (± 0.13) | -0.12 (± 0.15) | -0.89 (± 0.17) | -0.17 (± 0.14) | -0.49 (± 0.20) |
| Budget 1 R, 2 adds 0.17 ATR apart | -0.29 (± 0.24) | -0.00 (± 0.18) | -0.08 (± 0.20) | -1.23 (± 0.31) | -0.46 (± 0.19) | -0.82 (± 0.23) |
| Budget 2 R, no add | -0.13 (± 0.31) | +0.18 (± 0.18) | -0.14 (± 0.26) | -0.85 (± 0.18) | +0.03 (± 0.29) | -0.16 (± 0.28) |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.04 (± 0.38) | -0.01 (± 0.26) | +0.06 (± 0.20) | -1.49 (± 0.36) | -0.47 (± 0.26) | -1.09 (± 0.40) |
| Budget 3 R, no add | -0.03 (± 0.38) | +0.18 (± 0.24) | -0.18 (± 0.25) | -0.95 (± 0.31) | -0.04 (± 0.31) | -0.07 (± 0.34) |
| Budget 3 R, 1 add 1 ATR apart | -0.15 (± 0.36) | +0.07 (± 0.27) | -0.11 (± 0.32) | -1.15 (± 0.29) | -0.13 (± 0.37) | -0.07 (± 0.32) |
| Budget 3 R, 2 adds 0.5 ATR apart | +0.05 (± 0.53) | -0.02 (± 0.27) | -0.25 (± 0.36) | -1.40 (± 0.40) | -0.59 (± 0.31) | -0.20 (± 0.43) |
| Budget 3 R, 3 adds 0.3 ATR apart | -0.28 (± 0.55) | -0.08 (± 0.32) | -0.26 (± 0.22) | -1.74 (± 0.40) | -0.59 (± 0.34) | -1.36 (± 0.44) |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.14 (± 0.53) | +0.07 (± 0.34) | +0.07 (± 0.29) | -2.07 (± 0.49) | -0.62 (± 0.39) | -1.49 (± 0.62) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.05 (± 0.53) | -0.02 (± 0.27) | -0.25 (± 0.36) | -1.40 (± 0.40) | -0.59 (± 0.31) | -0.19 (± 0.43) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | +0.05 (± 0.53) | -0.02 (± 0.27) | -0.25 (± 0.36) | -1.40 (± 0.40) | -0.59 (± 0.31) | -0.19 (± 0.43) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | +0.05 (± 0.53) | -0.02 (± 0.27) | -0.25 (± 0.36) | -1.40 (± 0.40) | -0.59 (± 0.31) | -0.19 (± 0.43) |
| Add when the M5 MACD histogram turns | -0.36 (± 0.37) | +0.22 (± 0.22) | -0.06 (± 0.25) | -1.50 (± 0.31) | -0.23 (± 0.36) | -0.35 (± 0.43) |
| Add when the M15 MACD histogram turns | -0.29 (± 0.39) | +0.19 (± 0.25) | -0.21 (± 0.30) | -1.05 (± 0.26) | -0.17 (± 0.35) | -0.02 (± 0.36) |
| Add when the M5 RSI comes back through 35 / 65 | +0.18 (± 0.36) | +0.06 (± 0.26) | -0.21 (± 0.31) | -1.09 (± 0.26) | -0.08 (± 0.32) | -0.07 (± 0.39) |
| Add when the M15 RSI comes back through 35 / 65 | -0.23 (± 0.36) | +0.00 (± 0.25) | -0.34 (± 0.35) | -1.25 (± 0.34) | -0.17 (± 0.33) | +0.07 (± 0.32) |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.04 (± 0.22) | -0.01 (± 0.15) | -0.24 (± 0.18) | -0.89 (± 0.18) | -0.21 (± 0.14) | -0.58 (± 0.27) |
| Break-even at +1 ATR (stop 1, target 2) | -0.03 (± 0.30) | +0.25 (± 0.15) | -0.16 (± 0.30) | -0.71 (± 0.24) | +0.12 (± 0.26) | -0.41 (± 0.38) |
| Trailing stop 1 ATR, no target | +0.03 (± 0.34) | -0.10 (± 0.21) | +0.05 (± 0.32) | -0.73 (± 0.21) | -0.02 (± 0.26) | -0.66 (± 0.32) |
| Trailing stop 2 ATR, no target | +0.55 (± 0.53) | +0.17 (± 0.41) | -0.04 (± 0.61) | +0.04 (± 0.64) | +0.42 (± 0.68) | -0.21 (± 0.76) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | -0.00 (± 0.29) | +0.06 (± 0.18) | -0.12 (± 0.30) | -0.80 (± 0.21) | -0.03 (± 0.20) | -0.45 (± 0.32) |
| Pyramid, 2 adds | +0.18 (± 0.62) | -0.37 (± 0.34) | +0.36 (± 0.61) | -0.93 (± 0.25) | -0.12 (± 0.48) | -0.97 (± 0.49) |
| Pyramid, 4 adds | +0.15 (± 0.65) | -0.48 (± 0.34) | +0.44 (± 0.70) | -1.03 (± 0.26) | -0.29 (± 0.47) | -0.95 (± 0.51) |
| Hedge lock, unlocked by the next vote signal | +0.22 (± 0.27) | +0.06 (± 0.20) | -0.18 (± 0.31) | -1.09 (± 0.33) | -0.12 (± 0.20) | -0.22 (± 0.31) |
| Close at -1 ATR, re-enter on the next vote signal | +0.22 (± 0.27) | +0.06 (± 0.20) | -0.18 (± 0.31) | -1.09 (± 0.33) | -0.12 (± 0.20) | -0.22 (± 0.31) |
| Hedge lock, both legs closed 4 h later | -0.05 (± 0.25) | +0.05 (± 0.17) | -0.27 (± 0.23) | -1.13 (± 0.20) | -0.27 (± 0.17) | -0.50 (± 0.31) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | +0.32 (± 1.15) | -0.02 (± 0.65) | -0.74 (± 0.76) | -6.63 (± 1.66) | -1.22 (± 0.82) | -1.50 (± 0.78) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.87 (± 0.38) | -1.11 (± 0.52) | -0.81 (± 0.34) | -4.54 (± 0.74) | -2.01 (± 0.50) | -2.29 (± 0.59) |
| Stop and reverse, same size | -0.05 (± 0.27) | -0.02 (± 0.17) | -0.26 (± 0.22) | -1.28 (± 0.24) | -0.25 (± 0.19) | -0.72 (± 0.34) |
| Stop and reverse, double size | -0.15 (± 0.41) | -0.17 (± 0.25) | -0.30 (± 0.27) | -1.73 (± 0.35) | -0.38 (± 0.30) | -1.09 (± 0.43) |
| Martingale: double after a loss, up to x8 | +0.70 (± 0.66) | +0.10 (± 0.54) | -0.82 (± 0.99) | -2.65 (± 0.68) | -0.42 (± 0.66) | +0.20 (± 0.92) |
| Anti-martingale: double after a win, up to x8 | +0.91 (± 1.14) | -0.55 (± 0.55) | -0.15 (± 0.56) | -1.59 (± 0.59) | -0.21 (± 0.71) | -1.44 (± 0.65) |
| Daily loss limit 1 R | +0.18 (± 0.31) | +0.21 (± 0.19) | +0.02 (± 0.26) | -0.84 (± 0.27) | -0.19 (± 0.30) | -0.73 (± 0.35) |
| Daily loss limit 2 R | -0.04 (± 0.25) | +0.19 (± 0.18) | -0.08 (± 0.23) | -0.80 (± 0.22) | -0.32 (± 0.21) | -0.32 (± 0.32) |
<!-- /table -->

BTC, votes only:

<!-- table halves:BTCUSDm:votes -->
| Mechanism | DEV 2025 H2 (n=1,082) | DEV 2026 H1 (n=1,364) | DEV 2026 H2 (n=1,093) | CONFIRM 2024 H1 (n=1,028) | CONFIRM 2024 H2 (n=1,444) | CONFIRM 2025 H1 (n=1,437) |
|---|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | +0.13 (± 0.16) | -0.18 (± 0.13) | -0.07 (± 0.12) | -0.88 (± 0.17) | -0.26 (± 0.15) | -0.18 (± 0.14) |
| Fixed stop 2 ATR, target 2 ATR | -0.22 (± 0.34) | -0.38 (± 0.34) | +0.25 (± 0.27) | -0.43 (± 0.41) | +0.23 (± 0.36) | -0.04 (± 0.35) |
| Fixed stop 1 ATR, target 2 ATR | +0.16 (± 0.24) | -0.21 (± 0.20) | -0.13 (± 0.20) | -0.81 (± 0.20) | -0.08 (± 0.20) | -0.19 (± 0.23) |
| Fixed stop 2 ATR, target 1 ATR | +0.10 (± 0.22) | -0.15 (± 0.19) | -0.00 (± 0.16) | -0.77 (± 0.31) | -0.25 (± 0.20) | -0.02 (± 0.25) |
| Fixed stop $20, target $20 (the V2 exit) | +0.04 (± 0.50) | -0.33 (± 0.63) | +0.76 (± 0.72) | -0.41 (± 0.95) | -0.21 (± 0.51) | -0.59 (± 0.37) |
| Live ladder, no stop | +1.00 (± 0.00) | +1.00 (± 0.00) | +1.00 (± 0.00) | -11.63 (± 8.15) | +1.00 (± 0.00) | -1.04 (± 2.04) |
| Live ladder, basket stop $60 | -0.63 (± 0.29) | -0.74 (± 0.27) | +0.05 (± 0.21) | -2.74 (± 0.50) | -2.08 (± 0.34) | -0.70 (± 0.23) |
| Live ladder, basket stop $200 | +0.26 (± 0.42) | +0.26 (± 0.31) | +0.08 (± 0.37) | -3.11 (± 0.99) | -1.92 (± 0.48) | -1.24 (± 0.54) |
| Budget 1 R, no add | -0.05 (± 0.10) | -0.02 (± 0.09) | +0.03 (± 0.08) | -0.93 (± 0.14) | -0.23 (± 0.10) | -0.19 (± 0.11) |
| Budget 1 R, 2 adds 0.17 ATR apart | -0.31 (± 0.15) | -0.31 (± 0.12) | +0.07 (± 0.12) | -1.41 (± 0.22) | -0.62 (± 0.12) | -0.53 (± 0.20) |
| Budget 2 R, no add | -0.07 (± 0.17) | -0.05 (± 0.12) | +0.00 (± 0.14) | -0.91 (± 0.21) | -0.17 (± 0.18) | +0.08 (± 0.20) |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.09 (± 0.29) | -0.13 (± 0.21) | +0.20 (± 0.15) | -1.70 (± 0.28) | -0.50 (± 0.20) | -0.48 (± 0.24) |
| Budget 3 R, no add | +0.02 (± 0.22) | -0.22 (± 0.15) | -0.01 (± 0.17) | -0.84 (± 0.28) | -0.23 (± 0.23) | -0.13 (± 0.20) |
| Budget 3 R, 1 add 1 ATR apart | -0.26 (± 0.23) | -0.18 (± 0.18) | +0.04 (± 0.18) | -1.13 (± 0.28) | -0.20 (± 0.24) | +0.08 (± 0.26) |
| Budget 3 R, 2 adds 0.5 ATR apart | +0.05 (± 0.32) | -0.13 (± 0.17) | +0.15 (± 0.19) | -1.47 (± 0.32) | -0.45 (± 0.27) | -0.23 (± 0.27) |
| Budget 3 R, 3 adds 0.3 ATR apart | +0.08 (± 0.44) | -0.17 (± 0.25) | +0.04 (± 0.17) | -1.82 (± 0.35) | -0.59 (± 0.33) | -0.62 (± 0.29) |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.05 (± 0.46) | -0.07 (± 0.29) | +0.23 (± 0.23) | -2.52 (± 0.38) | -0.63 (± 0.29) | -0.67 (± 0.36) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.05 (± 0.32) | -0.13 (± 0.17) | +0.15 (± 0.19) | -1.47 (± 0.32) | -0.45 (± 0.27) | -0.22 (± 0.27) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | +0.05 (± 0.32) | -0.13 (± 0.17) | +0.15 (± 0.19) | -1.47 (± 0.32) | -0.45 (± 0.27) | -0.22 (± 0.27) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | +0.05 (± 0.32) | -0.13 (± 0.17) | +0.15 (± 0.19) | -1.47 (± 0.32) | -0.45 (± 0.27) | -0.22 (± 0.27) |
| Add when the M5 MACD histogram turns | -0.34 (± 0.24) | -0.10 (± 0.18) | +0.16 (± 0.17) | -1.49 (± 0.30) | -0.29 (± 0.25) | -0.06 (± 0.26) |
| Add when the M15 MACD histogram turns | -0.21 (± 0.24) | -0.18 (± 0.20) | +0.00 (± 0.19) | -1.02 (± 0.23) | -0.33 (± 0.23) | +0.21 (± 0.25) |
| Add when the M5 RSI comes back through 35 / 65 | -0.15 (± 0.21) | -0.15 (± 0.18) | +0.05 (± 0.19) | -1.30 (± 0.28) | -0.25 (± 0.26) | +0.00 (± 0.25) |
| Add when the M15 RSI comes back through 35 / 65 | -0.04 (± 0.19) | -0.34 (± 0.19) | -0.07 (± 0.16) | -1.04 (± 0.26) | -0.24 (± 0.26) | -0.07 (± 0.21) |
| Break-even at +0.5 ATR (stop 1, target 1) | +0.05 (± 0.12) | -0.09 (± 0.10) | -0.08 (± 0.11) | -0.94 (± 0.14) | -0.22 (± 0.12) | -0.20 (± 0.13) |
| Break-even at +1 ATR (stop 1, target 2) | +0.01 (± 0.23) | -0.16 (± 0.15) | -0.03 (± 0.17) | -0.82 (± 0.17) | -0.27 (± 0.19) | -0.31 (± 0.17) |
| Trailing stop 1 ATR, no target | +0.25 (± 0.17) | -0.25 (± 0.12) | +0.15 (± 0.20) | -0.84 (± 0.18) | -0.31 (± 0.13) | -0.40 (± 0.17) |
| Trailing stop 2 ATR, no target | +0.13 (± 0.38) | -0.28 (± 0.38) | -0.11 (± 0.32) | -0.75 (± 0.41) | -0.24 (± 0.39) | -0.16 (± 0.39) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | +0.10 (± 0.16) | -0.24 (± 0.15) | +0.01 (± 0.16) | -0.87 (± 0.18) | -0.23 (± 0.15) | -0.26 (± 0.14) |
| Pyramid, 2 adds | +0.40 (± 0.33) | -0.53 (± 0.21) | +0.34 (± 0.39) | -1.11 (± 0.25) | -0.49 (± 0.31) | -0.80 (± 0.32) |
| Pyramid, 4 adds | +0.37 (± 0.36) | -0.58 (± 0.23) | +0.43 (± 0.44) | -1.21 (± 0.26) | -0.49 (± 0.36) | -0.85 (± 0.36) |
| Hedge lock, unlocked by the next vote signal | +0.12 (± 0.24) | -0.33 (± 0.27) | -0.15 (± 0.20) | -1.46 (± 0.30) | -0.37 (± 0.22) | -0.21 (± 0.22) |
| Close at -1 ATR, re-enter on the next vote signal | +0.12 (± 0.24) | -0.33 (± 0.27) | -0.15 (± 0.20) | -1.46 (± 0.30) | -0.37 (± 0.22) | -0.21 (± 0.22) |
| Hedge lock, both legs closed 4 h later | +0.03 (± 0.16) | -0.26 (± 0.14) | -0.11 (± 0.12) | -1.17 (± 0.18) | -0.41 (± 0.15) | -0.32 (± 0.15) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -0.44 (± 0.82) | -0.80 (± 0.44) | -0.73 (± 0.75) | -5.49 (± 1.00) | -0.20 (± 0.57) | -2.20 (± 0.77) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.28 (± 0.42) | -1.30 (± 0.35) | -1.06 (± 0.28) | -4.26 (± 0.51) | -1.49 (± 0.40) | -2.25 (± 0.61) |
| Stop and reverse, same size | +0.15 (± 0.21) | -0.25 (± 0.14) | -0.16 (± 0.13) | -1.28 (± 0.20) | -0.39 (± 0.15) | -0.50 (± 0.20) |
| Stop and reverse, double size | +0.17 (± 0.31) | -0.33 (± 0.20) | -0.25 (± 0.20) | -1.67 (± 0.28) | -0.52 (± 0.21) | -0.83 (± 0.29) |
| Martingale: double after a loss, up to x8 | -0.08 (± 0.54) | -0.85 (± 0.71) | -0.20 (± 0.48) | -3.02 (± 0.79) | -0.48 (± 0.39) | -0.77 (± 0.54) |
| Anti-martingale: double after a win, up to x8 | +0.73 (± 0.93) | -0.56 (± 0.28) | +0.34 (± 0.36) | -1.72 (± 0.37) | -0.50 (± 0.53) | -0.54 (± 0.64) |
| Daily loss limit 1 R | -0.20 (± 0.33) | -0.54 (± 0.19) | -0.13 (± 0.17) | -0.82 (± 0.37) | -0.20 (± 0.30) | -0.43 (± 0.33) |
| Daily loss limit 2 R | +0.02 (± 0.23) | -0.22 (± 0.13) | -0.19 (± 0.14) | -0.99 (± 0.24) | -0.25 (± 0.20) | -0.19 (± 0.18) |
<!-- /table -->

BTC, random:

<!-- table halves:BTCUSDm:random -->
| Mechanism | DEV 2025 H2 (n=1,046) | DEV 2026 H1 (n=1,311) | DEV 2026 H2 (n=1,039) | CONFIRM 2024 H1 (n=968) | CONFIRM 2024 H2 (n=1,402) | CONFIRM 2025 H1 (n=1,346) |
|---|---|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | -0.34 (± 0.18) | -0.29 (± 0.13) | +0.08 (± 0.11) | -0.14 (± 0.19) | -0.29 (± 0.18) | +0.13 (± 0.25) |
| Fixed stop 2 ATR, target 2 ATR | -0.16 (± 0.46) | -0.12 (± 0.31) | -0.11 (± 0.25) | -0.52 (± 0.35) | -0.43 (± 0.44) | +0.54 (± 0.41) |
| Fixed stop 1 ATR, target 2 ATR | -0.32 (± 0.24) | -0.22 (± 0.24) | +0.01 (± 0.18) | -0.43 (± 0.22) | -0.28 (± 0.22) | +0.53 (± 0.33) |
| Fixed stop 2 ATR, target 1 ATR | -0.17 (± 0.30) | -0.04 (± 0.18) | +0.03 (± 0.15) | -0.16 (± 0.25) | -0.27 (± 0.22) | +0.37 (± 0.28) |
| Fixed stop $20, target $20 (the V2 exit) | +0.27 (± 0.61) | -0.15 (± 0.55) | -0.61 (± 0.64) | +0.17 (± 0.63) | +0.13 (± 0.59) | +0.26 (± 0.55) |
| Live ladder, no stop | +0.53 (± 0.47) | -5.38 (± 6.36) | +1.00 (± 0.00) | -14.96 (± 10.24) | -4.17 (± 5.16) | +0.50 (± 0.50) |
| Live ladder, basket stop $60 | -1.99 (± 0.30) | -0.91 (± 0.28) | -0.59 (± 0.29) | -2.47 (± 0.55) | -1.92 (± 0.41) | -1.76 (± 0.29) |
| Live ladder, basket stop $200 | -2.08 (± 0.56) | -0.38 (± 0.53) | -1.32 (± 0.67) | -3.15 (± 1.08) | -2.15 (± 0.68) | -0.94 (± 0.51) |
| Budget 1 R, no add | -0.25 (± 0.13) | -0.22 (± 0.11) | -0.02 (± 0.11) | -0.43 (± 0.14) | -0.32 (± 0.10) | +0.04 (± 0.17) |
| Budget 1 R, 2 adds 0.17 ATR apart | -0.11 (± 0.19) | -0.42 (± 0.18) | -0.25 (± 0.14) | -0.98 (± 0.17) | -0.78 (± 0.19) | -0.59 (± 0.24) |
| Budget 2 R, no add | -0.28 (± 0.17) | -0.02 (± 0.17) | -0.08 (± 0.12) | -0.48 (± 0.21) | -0.40 (± 0.15) | +0.25 (± 0.23) |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.32 (± 0.30) | -0.35 (± 0.16) | -0.00 (± 0.21) | -1.07 (± 0.28) | -0.52 (± 0.19) | -0.04 (± 0.24) |
| Budget 3 R, no add | -0.21 (± 0.16) | -0.11 (± 0.24) | -0.10 (± 0.12) | -0.43 (± 0.25) | -0.24 (± 0.22) | +0.33 (± 0.26) |
| Budget 3 R, 1 add 1 ATR apart | -0.51 (± 0.26) | -0.10 (± 0.27) | -0.14 (± 0.14) | -0.57 (± 0.28) | -0.53 (± 0.15) | +0.20 (± 0.31) |
| Budget 3 R, 2 adds 0.5 ATR apart | -0.46 (± 0.36) | -0.31 (± 0.23) | -0.09 (± 0.21) | -0.88 (± 0.25) | -0.67 (± 0.20) | +0.18 (± 0.27) |
| Budget 3 R, 3 adds 0.3 ATR apart | -0.64 (± 0.37) | -0.50 (± 0.23) | -0.11 (± 0.26) | -1.09 (± 0.31) | -0.63 (± 0.20) | +0.04 (± 0.30) |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.67 (± 0.40) | -0.38 (± 0.25) | -0.04 (± 0.29) | -1.71 (± 0.39) | -0.82 (± 0.28) | +0.17 (± 0.40) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.46 (± 0.36) | -0.31 (± 0.23) | -0.09 (± 0.21) | -0.88 (± 0.25) | -0.67 (± 0.20) | +0.18 (± 0.27) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | -0.46 (± 0.36) | -0.31 (± 0.23) | -0.09 (± 0.21) | -0.88 (± 0.25) | -0.67 (± 0.20) | +0.18 (± 0.27) |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.46 (± 0.36) | -0.31 (± 0.23) | -0.09 (± 0.21) | -0.88 (± 0.25) | -0.67 (± 0.20) | +0.18 (± 0.27) |
| Add when the M5 MACD histogram turns | -0.78 (± 0.28) | -0.03 (± 0.22) | -0.15 (± 0.18) | -0.67 (± 0.31) | -0.42 (± 0.15) | +0.19 (± 0.32) |
| Add when the M15 MACD histogram turns | -0.79 (± 0.24) | -0.01 (± 0.24) | -0.17 (± 0.12) | -0.79 (± 0.26) | -0.55 (± 0.25) | +0.25 (± 0.33) |
| Add when the M5 RSI comes back through 35 / 65 | -0.69 (± 0.26) | -0.04 (± 0.26) | -0.18 (± 0.15) | -0.69 (± 0.30) | -0.56 (± 0.20) | +0.22 (± 0.27) |
| Add when the M15 RSI comes back through 35 / 65 | -0.34 (± 0.19) | +0.03 (± 0.26) | -0.18 (± 0.12) | -0.74 (± 0.28) | -0.50 (± 0.26) | +0.15 (± 0.25) |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.23 (± 0.15) | -0.25 (± 0.11) | -0.03 (± 0.11) | -0.41 (± 0.16) | -0.29 (± 0.14) | +0.04 (± 0.23) |
| Break-even at +1 ATR (stop 1, target 2) | -0.34 (± 0.21) | -0.24 (± 0.19) | +0.01 (± 0.14) | -0.26 (± 0.18) | -0.37 (± 0.19) | +0.26 (± 0.32) |
| Trailing stop 1 ATR, no target | -0.13 (± 0.16) | -0.35 (± 0.12) | -0.03 (± 0.11) | -0.36 (± 0.17) | -0.54 (± 0.15) | +0.05 (± 0.26) |
| Trailing stop 2 ATR, no target | -0.42 (± 0.45) | -0.01 (± 0.32) | +0.07 (± 0.33) | -0.41 (± 0.50) | -0.03 (± 0.49) | +0.72 (± 0.64) |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | -0.35 (± 0.17) | -0.35 (± 0.13) | +0.06 (± 0.12) | -0.25 (± 0.19) | -0.34 (± 0.17) | +0.20 (± 0.28) |
| Pyramid, 2 adds | -0.07 (± 0.30) | -0.61 (± 0.19) | -0.13 (± 0.18) | -0.81 (± 0.22) | -0.77 (± 0.28) | +0.16 (± 0.43) |
| Pyramid, 4 adds | -0.16 (± 0.29) | -0.68 (± 0.20) | -0.14 (± 0.20) | -0.89 (± 0.22) | -0.72 (± 0.33) | +0.17 (± 0.45) |
| Hedge lock, unlocked by the next vote signal | -0.17 (± 0.24) | -0.41 (± 0.19) | +0.08 (± 0.12) | -0.61 (± 0.28) | -0.35 (± 0.20) | +0.04 (± 0.31) |
| Close at -1 ATR, re-enter on the next vote signal | -0.17 (± 0.24) | -0.41 (± 0.19) | +0.08 (± 0.12) | -0.61 (± 0.28) | -0.35 (± 0.20) | +0.04 (± 0.31) |
| Hedge lock, both legs closed 4 h later | -0.44 (± 0.18) | -0.37 (± 0.13) | +0.03 (± 0.11) | -0.41 (± 0.20) | -0.44 (± 0.18) | -0.01 (± 0.26) |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -1.06 (± 0.84) | -0.68 (± 0.45) | -0.04 (± 0.42) | -2.52 (± 0.73) | +0.20 (± 0.61) | -2.00 (± 1.00) |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.79 (± 0.41) | -1.77 (± 0.30) | -0.74 (± 0.19) | -3.49 (± 0.59) | -2.04 (± 0.30) | -2.04 (± 0.45) |
| Stop and reverse, same size | -0.38 (± 0.23) | -0.43 (± 0.15) | +0.06 (± 0.13) | -0.45 (± 0.24) | -0.38 (± 0.21) | -0.12 (± 0.33) |
| Stop and reverse, double size | -0.41 (± 0.35) | -0.57 (± 0.22) | +0.05 (± 0.17) | -0.76 (± 0.32) | -0.47 (± 0.25) | -0.36 (± 0.45) |
| Martingale: double after a loss, up to x8 | -1.16 (± 0.68) | -0.45 (± 0.45) | +0.22 (± 0.34) | -0.95 (± 0.65) | -0.31 (± 0.59) | +0.36 (± 0.64) |
| Anti-martingale: double after a win, up to x8 | -0.78 (± 0.53) | -0.48 (± 0.51) | +0.34 (± 0.45) | +0.73 (± 0.79) | -1.05 (± 0.47) | +1.09 (± 1.17) |
| Daily loss limit 1 R | -0.02 (± 0.35) | -0.34 (± 0.25) | +0.07 (± 0.16) | -0.21 (± 0.32) | -0.47 (± 0.22) | +0.40 (± 0.37) |
| Daily loss limit 2 R | -0.18 (± 0.23) | -0.29 (± 0.15) | +0.01 (± 0.15) | -0.33 (± 0.25) | -0.20 (± 0.21) | +0.44 (± 0.30) |
<!-- /table -->

</details>

## Recommendation

**If the ladder stays, this is the form that cannot eat the balance:**

| Rule | Value tested | Why |
|---|---|---|
| Lot of every add | equal to the entry (1, 1, 1), not 2, 3, 5, 8, 13 | the Fibonacci sizes put 31 of 32 units in after the trade has already gone wrong |
| Number of adds | at most 2 | every further add lowered the win rate and raised the spread paid; 4 adds emptied the account in 6 of 12 cells |
| Where the adds go | 0.5 and 1.0 ATR against the entry (H1 ATR of the entry hour), or on an M15 turn at least 0.5 ATR beyond the last fill | distances that scale with the market: R on gold was 2.6 times larger in DEV than in CONFIRM, so a fixed dollar step is a different rule each year |
| Target | 0.5 ATR above the average entry | "a better average entry when price pulls back" is exactly this |
| Hard stop on the basket | when its loss reaches the smaller of 3 R and 3 % of the balance ($60 on 2,000) | the dollar cap is what fixes the share of the balance; 3 R alone was $364 once |
| An add that does not fit | not made: if the add's own spread would take the basket through its budget, the ladder ends | otherwise the budget can be overshot by the spread on the add |
| Market closures (gold) | flat from Friday 20:30 UTC to Monday, and from 20:30 to 23:05 UTC on other days | the losses far beyond the budget all came from closures: -$222 against a $60 budget |

Measured over 31,952 baskets in twelve cells: none lost more than $60.00 (3 % of 2,000), sixteen lost
more than their own smaller budget (by $15 at most), the largest position was 3 units, and the win
rate 75 to 80 %. Its expectancy is that of the entries minus the spread on about 0.8 extra units; it
does not add an edge, and on the same budget the position without adds won more often and paid less
spread. The ladder is a preference about the shape of the result, and in this form it is an
affordable one.

**Worth adding to the engine and optimising** (on raw ticks, with the 1 s loop):

1. *The basket budget with its add guard and the equal-lot ladder of 0, 1 or 2 adds*, so that the
   optimiser can choose between adding and not adding inside one budget. This comparison says "0";
   the tick engine should confirm it.
2. *Flat over market closures.* It is what made the cap hold on gold, and it cost nothing measurable.
3. *The exit of with-trend entries: wide fixed exit against a trailing stop.* The V2 exit is the only
   row above zero in all four with-trend cells, and a 2 ATR trailing stop is above zero in 8 of 12
   cells; neither is proven. Distances should be in ATR with a dollar ceiling, because R on gold was
   2.6 times larger in one period than in the other.

**Not worth adding:** a hedge lock (it is a close and a re-entry, plus a spread), zone recovery,
martingale or anti-martingale sizing, stop and reverse, break-even (it changed the expectancy by
-$0.05 on average and cut the win rate from one in two to one in three). A daily loss limit is a
circuit breaker, not a source of profit: it bounds a bad day and otherwise only trades less.

## How far to trust this

- **Bar-level, not tick-level.** A stop inside an M1 bar is filled at its level. In a fast market the
  live loop, which looks once a second, is filled worse; the tick-level backtest of V2 showed -$34 on
  a $20 stop for one unit. "Worst basket -$60.00" therefore means "no gap went through it", not "no
  slippage is possible", and with three units a slip counts three times.
- **The spread is the bar's mean.** A spike of the spread inside a bar is not seen.
- **The live ladder here acts once a minute** and has no force-close; the bot looks once a second and
  closes on the M15 slope score. The bot itself is measured tick by tick in the main backtest; this
  row isolates what the ladder alone does.
- **The order inside a bar is an assumption.** All runs were repeated with the favourable extreme
  first and with the shortest path through the bar. For 33 of 42 mechanisms the three readings agree
  within 2 % of R in every cell. They differ for zone recovery (up to $2.21 per entry on gold DEV),
  the live ladder with a stop (up to $1.38), pyramiding and trailing stops (up to $0.42); the sign of
  an expectancy changes in 23 of 504 cells, all within noise of zero. No statement above depends on
  the reading; where a count does (zone recovery), both ends are given.
- **Baskets are simulated independently**, so long ones overlap in time; standard errors are clustered
  by week for that reason, and the account columns hold one basket at a time.
- **One random list per cell.** Four other seeds on DEV gave reference results before spread between
  -$0.35 and +$1.09 on gold (standard error about 0.5) and between -$0.13 and -$0.05 on BTC (about
  0.09).
- **Many comparisons.** With 42 rows in twelve cells, single values two standard errors from zero are
  expected by chance. Only patterns that hold in both periods are treated as findings here; all of
  those are costs, none is a gain.
- **Thirty-four months, 0.01 lot, no swap, no commission, no unit step-up.**

<details><summary>How much each expectancy depends on the order assumed inside a bar (a star marks an emptied account)</summary>

Gold, with the H1 trend:

<!-- table order:XAUUSDm:trend -->
| Mechanism | Unfavourable extreme first (the result) | Favourable extreme first | Shortest path | Widest gap |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | +0.46 / -0.08 | +0.53 / -0.07 | +0.49 / -0.08 | 0.06 / 0.01 |
| Fixed stop 2 ATR, target 2 ATR | -0.99 / -0.12 | -0.99 / -0.10 | -0.99 / -0.12 | 0.00 / 0.01 |
| Fixed stop 1 ATR, target 2 ATR | +0.32 / -0.13 | +0.32 / -0.12 | +0.32 / -0.12 | 0.00 / 0.01 |
| Fixed stop 2 ATR, target 1 ATR | +0.42 / +0.01 | +0.45 / +0.02 | +0.45 / +0.01 | 0.03 / 0.01 |
| Fixed stop $20, target $20 (the V2 exit) | +1.20 / +0.69 | +1.22 / +0.69 | +1.20 / +0.69 | 0.03 / 0.00 |
| Live ladder, no stop | +1.00* / +1.00 | +1.00* / +1.00 | +1.00* / +1.00 | 0.00 / 0.00 |
| Live ladder, basket stop $60 | -0.44 / -0.28 | -0.31 / -0.24 | -0.40 / -0.24 | 0.13 / 0.04 |
| Live ladder, basket stop $200 | -0.15 / -0.47 | -0.15 / -0.47 | -0.15 / -0.47 | 0.00 / 0.00 |
| Budget 1 R, no add | +0.21 / -0.25 | +0.24 / -0.24 | +0.21 / -0.25 | 0.03 / 0.00 |
| Budget 1 R, 2 adds 0.17 ATR apart | +0.28 / -0.54 | +0.32 / -0.54 | +0.32 / -0.54 | 0.04 / 0.01 |
| Budget 2 R, no add | +0.44 / -0.14 | +0.44 / -0.13 | +0.44 / -0.14 | 0.00 / 0.01 |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.09 / -0.56 | -0.03 / -0.57 | -0.10 / -0.58 | 0.07 / 0.02 |
| Budget 3 R, no add | +0.49 / -0.23 | +0.49 / -0.22 | +0.49 / -0.23 | 0.00 / 0.01 |
| Budget 3 R, 1 add 1 ATR apart | +0.46 / -0.47 | +0.45 / -0.44 | +0.46 / -0.47 | 0.01 / 0.02 |
| Budget 3 R, 2 adds 0.5 ATR apart | +0.48 / -0.43 | +0.41 / -0.44 | +0.42 / -0.45 | 0.07 / 0.02 |
| Budget 3 R, 3 adds 0.3 ATR apart | -0.91 / -0.59 | -0.88* / -0.64 | -0.94* / -0.64 | 0.05 / 0.05 |
| Budget 3 R, 4 adds 0.2 ATR apart | +0.16 / -1.01 | +0.24 / -1.09 | +0.14 / -1.09 | 0.11 / 0.09 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.27 / -0.53 | +0.21 / -0.54 | +0.22 / -0.55 | 0.07 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | +0.40 / -0.57 | +0.33 / -0.58 | +0.34 / -0.59 | 0.07 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | +0.22 / -0.61 | +0.16 / -0.61 | +0.17 / -0.63 | 0.06 / 0.02 |
| Add when the M5 MACD histogram turns | +0.51 / -0.40 | +0.51 / -0.38 | +0.51 / -0.40 | 0.00 / 0.02 |
| Add when the M15 MACD histogram turns | +1.12 / -0.20 | +1.15 / -0.19 | +1.12 / -0.20 | 0.02 / 0.01 |
| Add when the M5 RSI comes back through 35 / 65 | +0.95 / -0.38 | +0.95 / -0.36 | +0.95 / -0.38 | 0.00 / 0.02 |
| Add when the M15 RSI comes back through 35 / 65 | +0.95 / -0.25 | +0.97 / -0.24 | +0.95 / -0.25 | 0.02 / 0.01 |
| Break-even at +0.5 ATR (stop 1, target 1) | +0.35 / -0.22 | +0.27 / -0.27 | +0.36 / -0.21 | 0.09 / 0.05 |
| Break-even at +1 ATR (stop 1, target 2) | +0.07 / -0.14 | +0.12 / -0.14 | +0.08 / -0.13 | 0.05 / 0.01 |
| Trailing stop 1 ATR, no target | +0.67 / -0.21 | +0.56 / -0.23 | +0.67 / -0.20 | 0.11 / 0.03 |
| Trailing stop 2 ATR, no target | +0.10 / +0.35 | -0.02 / +0.31 | +0.11 / +0.36 | 0.13 / 0.04 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | +0.82 / -0.21 | +0.81 / -0.22 | +0.83 / -0.20 | 0.02 / 0.01 |
| Pyramid, 2 adds | +1.21 / -0.63 | +0.98 / -0.66 | +1.21 / -0.62 | 0.23 / 0.04 |
| Pyramid, 4 adds | +1.38 / -0.69 | +1.13 / -0.72 | +1.38 / -0.68 | 0.25 / 0.04 |
| Hedge lock, unlocked by the next vote signal | +0.69 / -0.06 | +0.75 / -0.03 | +0.70 / -0.04 | 0.06 / 0.03 |
| Close at -1 ATR, re-enter on the next vote signal | +0.69 / -0.06 | +0.75 / -0.03 | +0.70 / -0.04 | 0.06 / 0.03 |
| Hedge lock, both legs closed 4 h later | +0.35 / -0.17 | +0.42 / -0.16 | +0.38 / -0.17 | 0.06 / 0.01 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -2.10* / -0.23 | -0.72* / +0.03 | -0.72* / +0.03 | 1.38 / 0.26 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.80 / -0.81 | -0.35 / -0.33 | -0.38 / -0.35 | 1.46 / 0.48 |
| Stop and reverse, same size | +0.22 / -0.13 | +0.31 / -0.08 | +0.25 / -0.09 | 0.10 / 0.05 |
| Stop and reverse, double size | -0.03 / -0.17 | +0.10 / -0.09 | +0.02 / -0.09 | 0.13 / 0.08 |
| Martingale: double after a loss, up to x8 | +3.86 / -0.24 | +3.87 / -0.20 | +3.86 / -0.21 | 0.01 / 0.03 |
| Anti-martingale: double after a win, up to x8 | +0.69 / -0.01 | +1.17 / -0.01 | +0.69 / -0.01 | 0.49 / 0.00 |
| Daily loss limit 1 R | -0.08 / -0.11 | +0.00 / -0.11 | -0.04 / -0.11 | 0.09 / 0.00 |
| Daily loss limit 2 R | -0.06 / -0.20 | +0.01 / -0.19 | -0.02 / -0.19 | 0.07 / 0.01 |
<!-- /table -->

Gold, votes only:

<!-- table order:XAUUSDm:votes -->
| Mechanism | Unfavourable extreme first (the result) | Favourable extreme first | Shortest path | Widest gap |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | -0.37 / -0.11 | -0.33 / -0.10 | -0.36 / -0.11 | 0.04 / 0.01 |
| Fixed stop 2 ATR, target 2 ATR | -0.93 / -0.46 | -0.93 / -0.45 | -0.93 / -0.46 | 0.00 / 0.01 |
| Fixed stop 1 ATR, target 2 ATR | +0.08 / -0.19 | +0.08 / -0.18 | +0.08 / -0.19 | 0.00 / 0.01 |
| Fixed stop 2 ATR, target 1 ATR | -1.01 / -0.32 | -0.99 / -0.31 | -0.99 / -0.32 | 0.02 / 0.01 |
| Fixed stop $20, target $20 (the V2 exit) | -0.13 / -0.60 | -0.11 / -0.60 | -0.13 / -0.60 | 0.02 / 0.00 |
| Live ladder, no stop | -4.38* / -12.57* | -4.38* / -12.57* | -4.38* / -12.57* | 0.00 / 0.00 |
| Live ladder, basket stop $60 | -0.94* / -0.70 | -0.46 / -0.57 | -0.63 / -0.63 | 0.48 / 0.12 |
| Live ladder, basket stop $200 | -0.75 / -0.29 | -0.68 / -0.29 | -0.68 / -0.29 | 0.08 / 0.00 |
| Budget 1 R, no add | -0.08 / -0.20 | -0.06 / -0.20 | -0.08 / -0.20 | 0.02 / 0.00 |
| Budget 1 R, 2 adds 0.17 ATR apart | +0.13 / -0.56 | +0.12 / -0.57 | +0.15 / -0.56 | 0.03 / 0.00 |
| Budget 2 R, no add | -0.15 / -0.40 | -0.15 / -0.40 | -0.15 / -0.40 | 0.00 / 0.00 |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.18 / -0.49 | -0.19 / -0.51 | -0.24 / -0.51 | 0.06 / 0.02 |
| Budget 3 R, no add | -0.41 / -0.65 | -0.41 / -0.64 | -0.41 / -0.65 | 0.00 / 0.00 |
| Budget 3 R, 1 add 1 ATR apart | -0.85 / -0.74 | -0.85 / -0.78 | -0.84 / -0.79 | 0.01 / 0.05 |
| Budget 3 R, 2 adds 0.5 ATR apart | -0.68 / -0.54 | -0.71 / -0.55 | -0.73 / -0.56 | 0.05 / 0.02 |
| Budget 3 R, 3 adds 0.3 ATR apart | -1.03* / -0.58 | -1.18* / -0.60 | -1.22* / -0.60 | 0.20 / 0.02 |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.56 / -0.88* | -0.64* / -0.96* | -0.69* / -0.95* | 0.13 / 0.08 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.87 / -0.54 | -0.90 / -0.55 | -0.92 / -0.55 | 0.05 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | -0.67 / -0.55 | -0.70 / -0.56 | -0.72 / -0.57 | 0.05 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.60 / -0.51 | -0.62 / -0.52 | -0.64 / -0.53 | 0.04 / 0.02 |
| Add when the M5 MACD histogram turns | -0.93* / -0.75 | -0.89* / -0.75 | -0.92* / -0.75 | 0.04 / 0.00 |
| Add when the M15 MACD histogram turns | -0.16 / -0.59 | -0.15 / -0.58 | -0.16 / -0.59 | 0.01 / 0.01 |
| Add when the M5 RSI comes back through 35 / 65 | -0.34 / -0.68 | -0.30 / -0.68 | -0.34 / -0.68 | 0.04 / 0.00 |
| Add when the M15 RSI comes back through 35 / 65 | +0.14 / -0.58 | +0.16 / -0.57 | +0.14 / -0.58 | 0.01 / 0.00 |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.10 / -0.17 | -0.26 / -0.24 | -0.10 / -0.17 | 0.17 / 0.07 |
| Break-even at +1 ATR (stop 1, target 2) | -0.21 / -0.12 | -0.23 / -0.13 | -0.20 / -0.11 | 0.03 / 0.03 |
| Trailing stop 1 ATR, no target | -0.76* / -0.24 | -0.89* / -0.26 | -0.75* / -0.23 | 0.14 / 0.03 |
| Trailing stop 2 ATR, no target | +0.04 / -0.33 | -0.17 / -0.36 | +0.05 / -0.32 | 0.22 / 0.04 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | -0.36 / -0.18 | -0.43 / -0.19 | -0.34 / -0.17 | 0.08 / 0.02 |
| Pyramid, 2 adds | -1.46* / -0.66 | -1.77* / -0.69 | -1.45* / -0.64 | 0.32 / 0.05 |
| Pyramid, 4 adds | -1.52* / -0.74 | -1.85* / -0.76 | -1.51* / -0.71 | 0.34 / 0.05 |
| Hedge lock, unlocked by the next vote signal | -0.33 / -0.10 | -0.26 / -0.09 | -0.31 / -0.09 | 0.07 / 0.01 |
| Close at -1 ATR, re-enter on the next vote signal | -0.33 / -0.10 | -0.26 / -0.09 | -0.31 / -0.09 | 0.07 / 0.01 |
| Hedge lock, both legs closed 4 h later | -0.49 / -0.20 | -0.44 / -0.19 | -0.47 / -0.20 | 0.04 / 0.01 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | +0.14* / -0.26* | +2.06 / +0.07 | +2.06 / +0.03 | 1.92 / 0.32 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.94* / -0.80* | -0.76 / -0.34 | -0.78 / -0.36 | 1.18 / 0.46 |
| Stop and reverse, same size | -0.04 / +0.07 | +0.04 / +0.11 | -0.03 / +0.11 | 0.08 / 0.04 |
| Stop and reverse, double size | +0.29 / +0.25 | +0.41 / +0.33 | +0.30 / +0.32 | 0.12 / 0.08 |
| Martingale: double after a loss, up to x8 | -0.84* / -0.20* | -0.70* / -0.20* | -0.83* / -0.20* | 0.13 / 0.00 |
| Anti-martingale: double after a win, up to x8 | -0.97* / -0.37* | -0.92* / -0.33* | -0.96* / -0.34* | 0.05 / 0.04 |
| Daily loss limit 1 R | -0.59 / -0.35 | -0.54 / -0.34 | -0.59 / -0.34 | 0.05 / 0.02 |
| Daily loss limit 2 R | -0.45 / -0.04 | -0.39 / -0.03 | -0.42 / -0.03 | 0.06 / 0.01 |
<!-- /table -->

Gold, random:

<!-- table order:XAUUSDm:random -->
| Mechanism | Unfavourable extreme first (the result) | Favourable extreme first | Shortest path | Widest gap |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | +0.17 / -0.25 | +0.19 / -0.24 | +0.17 / -0.24 | 0.01 / 0.01 |
| Fixed stop 2 ATR, target 2 ATR | +0.23 / -0.02 | +0.23 / -0.01 | +0.23 / -0.01 | 0.00 / 0.01 |
| Fixed stop 1 ATR, target 2 ATR | +0.47 / -0.13 | +0.47 / -0.12 | +0.47 / -0.12 | 0.00 / 0.01 |
| Fixed stop 2 ATR, target 1 ATR | +0.02 / -0.22 | +0.04 / -0.21 | +0.02 / -0.22 | 0.02 / 0.01 |
| Fixed stop $20, target $20 (the V2 exit) | -0.35 / -0.35 | -0.33 / -0.35 | -0.35 / -0.35 | 0.02 / 0.00 |
| Live ladder, no stop | +1.00 / -10.09* | +1.00 / -10.09* | +1.00 / -10.09* | 0.00 / 0.00 |
| Live ladder, basket stop $60 | -2.55* / -1.19* | -1.17* / -0.96* | -1.58* / -1.00* | 1.38 / 0.24 |
| Live ladder, basket stop $200 | -2.02* / -0.76* | -1.38* / -0.76* | -1.46* / -0.76* | 0.64 / 0.00 |
| Budget 1 R, no add | -0.36 / -0.14 | -0.35 / -0.14 | -0.35 / -0.14 | 0.01 / 0.00 |
| Budget 1 R, 2 adds 0.17 ATR apart | -1.51* / -0.18 | -1.49* / -0.18 | -1.51* / -0.18 | 0.02 / 0.01 |
| Budget 2 R, no add | -0.20 / -0.15 | -0.20 / -0.15 | -0.20 / -0.15 | 0.00 / 0.00 |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.34 / -0.38 | -0.36 / -0.40 | -0.35 / -0.40 | 0.02 / 0.02 |
| Budget 3 R, no add | -0.55 / -0.25 | -0.55 / -0.25 | -0.55 / -0.25 | 0.00 / 0.00 |
| Budget 3 R, 1 add 1 ATR apart | -0.34 / -0.37 | -0.34 / -0.38 | -0.34 / -0.38 | 0.00 / 0.01 |
| Budget 3 R, 2 adds 0.5 ATR apart | +0.09 / -0.09 | -0.03 / -0.11 | -0.03 / -0.11 | 0.13 / 0.02 |
| Budget 3 R, 3 adds 0.3 ATR apart | +0.27 / -0.43 | +0.01 / -0.46 | +0.01 / -0.46 | 0.27 / 0.03 |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.77* / -0.70* | -0.91* / -0.77* | -0.89* / -0.77* | 0.14 / 0.08 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.25 / -0.13 | -0.27 / -0.16 | -0.28 / -0.16 | 0.02 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | -0.33 / -0.11 | -0.35 / -0.13 | -0.36 / -0.13 | 0.02 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.39 / -0.10 | -0.40 / -0.13 | -0.41 / -0.13 | 0.02 / 0.03 |
| Add when the M5 MACD histogram turns | +0.04 / -0.35 | +0.04 / -0.35 | +0.04 / -0.35 | 0.00 / 0.00 |
| Add when the M15 MACD histogram turns | -0.59 / -0.28 | -0.59 / -0.28 | -0.59 / -0.28 | 0.00 / 0.00 |
| Add when the M5 RSI comes back through 35 / 65 | -0.02 / -0.42 | -0.02 / -0.42 | -0.02 / -0.42 | 0.00 / 0.00 |
| Add when the M15 RSI comes back through 35 / 65 | -0.43 / -0.21 | -0.43 / -0.19 | -0.43 / -0.20 | 0.00 / 0.01 |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.31 / -0.06 | -0.44 / -0.10 | -0.30 / -0.06 | 0.13 / 0.05 |
| Break-even at +1 ATR (stop 1, target 2) | +0.53 / -0.11 | +0.51 / -0.11 | +0.53 / -0.10 | 0.02 / 0.02 |
| Trailing stop 1 ATR, no target | -0.30 / +0.03 | -0.44 / -0.01 | -0.30 / +0.04 | 0.14 / 0.05 |
| Trailing stop 2 ATR, no target | +1.09 / +0.29 | +0.79 / +0.25 | +1.10 / +0.30 | 0.31 / 0.05 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | +0.32 / -0.22 | +0.23 / -0.23 | +0.32 / -0.20 | 0.09 / 0.02 |
| Pyramid, 2 adds | -0.26 / +0.01 | -0.62 / -0.06 | -0.25 / +0.03 | 0.37 / 0.09 |
| Pyramid, 4 adds | -0.21 / -0.07 | -0.63 / -0.12 | -0.21 / -0.05 | 0.42 / 0.08 |
| Hedge lock, unlocked by the next vote signal | -0.38 / -0.24 | -0.35 / -0.23 | -0.37 / -0.23 | 0.03 / 0.01 |
| Close at -1 ATR, re-enter on the next vote signal | -0.38 / -0.24 | -0.35 / -0.23 | -0.37 / -0.23 | 0.03 / 0.01 |
| Hedge lock, both legs closed 4 h later | +0.06 / -0.34 | +0.07 / -0.33 | +0.06 / -0.33 | 0.01 / 0.01 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -1.26* / +0.42 | +0.94* / +0.82 | +0.82* / +0.82 | 2.21 / 0.40 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -2.06* / -0.96* | -0.75* / -0.51 | -0.77* / -0.51 | 1.31 / 0.45 |
| Stop and reverse, same size | +0.14 / -0.15 | +0.21 / -0.12 | +0.20 / -0.12 | 0.07 / 0.03 |
| Stop and reverse, double size | +0.11 / -0.05 | +0.24 / -0.00 | +0.22 / -0.00 | 0.13 / 0.05 |
| Martingale: double after a loss, up to x8 | +0.95* / -0.69* | +1.06* / -0.69* | +0.95* / -0.69* | 0.11 / 0.00 |
| Anti-martingale: double after a win, up to x8 | -0.33* / -0.95* | -0.32* / -0.93* | -0.33* / -0.93* | 0.01 / 0.02 |
| Daily loss limit 1 R | +0.18 / -0.27 | +0.18 / -0.25 | +0.18 / -0.25 | 0.00 / 0.01 |
| Daily loss limit 2 R | +0.01 / -0.22 | +0.03 / -0.20 | +0.01 / -0.20 | 0.02 / 0.02 |
<!-- /table -->

BTC, with the H1 trend:

<!-- table order:BTCUSDm:trend -->
| Mechanism | Unfavourable extreme first (the result) | Favourable extreme first | Shortest path | Widest gap |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | -0.00 / -0.39 | +0.00 / -0.39 | -0.00 / -0.39 | 0.00 / 0.00 |
| Fixed stop 2 ATR, target 2 ATR | +0.43 / +0.14 | +0.43 / +0.14 | +0.43 / +0.14 | 0.00 / 0.00 |
| Fixed stop 1 ATR, target 2 ATR | +0.12 / -0.23 | +0.12 / -0.23 | +0.12 / -0.23 | 0.00 / 0.00 |
| Fixed stop 2 ATR, target 1 ATR | +0.20 / -0.24 | +0.20 / -0.24 | +0.20 / -0.24 | 0.00 / 0.00 |
| Fixed stop $20, target $20 (the V2 exit) | +0.61 / +1.01 | +0.61 / +1.01 | +0.61 / +1.01 | 0.00 / 0.00 |
| Live ladder, no stop | +1.00 / +0.72 | +1.00 / +0.72 | +1.00 / +0.72 | 0.00 / 0.00 |
| Live ladder, basket stop $60 | -0.42 / -1.54* | -0.39 / -1.51* | -0.39 / -1.54* | 0.03 / 0.03 |
| Live ladder, basket stop $200 | -0.12 / -2.18* | -0.12 / -2.18* | -0.12 / -2.18* | 0.00 / 0.00 |
| Budget 1 R, no add | -0.04 / -0.47 | -0.04 / -0.47 | -0.04 / -0.47 | 0.00 / 0.00 |
| Budget 1 R, 2 adds 0.17 ATR apart | -0.11 / -0.79 | -0.12 / -0.78 | -0.12 / -0.78 | 0.01 / 0.01 |
| Budget 2 R, no add | -0.01 / -0.26 | -0.01 / -0.26 | -0.01 / -0.26 | 0.00 / 0.00 |
| Budget 2 R, 2 adds 0.33 ATR apart | +0.00 / -0.95* | -0.01 / -0.96* | -0.01 / -0.96* | 0.01 / 0.01 |
| Budget 3 R, no add | +0.01 / -0.27 | +0.01 / -0.27 | +0.01 / -0.27 | 0.00 / 0.00 |
| Budget 3 R, 1 add 1 ATR apart | -0.05 / -0.36 | -0.06 / -0.39 | -0.06 / -0.39 | 0.01 / 0.03 |
| Budget 3 R, 2 adds 0.5 ATR apart | -0.07 / -0.65 | -0.09 / -0.71 | -0.10 / -0.71 | 0.03 / 0.06 |
| Budget 3 R, 3 adds 0.3 ATR apart | -0.20 / -1.16* | -0.20 / -1.20* | -0.21 / -1.20* | 0.02 / 0.03 |
| Budget 3 R, 4 adds 0.2 ATR apart | +0.01 / -1.30* | -0.01 / -1.32* | -0.01 / -1.32* | 0.02 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.07 / -0.64 | -0.09 / -0.71 | -0.10 / -0.71 | 0.03 / 0.06 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | -0.07 / -0.64 | -0.09 / -0.71 | -0.10 / -0.71 | 0.03 / 0.06 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.07 / -0.64 | -0.09 / -0.71 | -0.10 / -0.71 | 0.03 / 0.06 |
| Add when the M5 MACD histogram turns | -0.04 / -0.59 | -0.04 / -0.59 | -0.04 / -0.59 | 0.00 / 0.00 |
| Add when the M15 MACD histogram turns | -0.07 / -0.33 | -0.07 / -0.33 | -0.07 / -0.33 | 0.00 / 0.00 |
| Add when the M5 RSI comes back through 35 / 65 | +0.02 / -0.33 | +0.02 / -0.33 | +0.02 / -0.33 | 0.00 / 0.00 |
| Add when the M15 RSI comes back through 35 / 65 | -0.17 / -0.35 | -0.17 / -0.35 | -0.17 / -0.35 | 0.00 / 0.00 |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.09 / -0.52 | -0.15 / -0.57 | -0.09 / -0.52 | 0.06 / 0.05 |
| Break-even at +1 ATR (stop 1, target 2) | +0.04 / -0.29 | +0.02 / -0.32 | +0.04 / -0.29 | 0.01 / 0.04 |
| Trailing stop 1 ATR, no target | -0.02 / -0.44 | -0.15 / -0.52 | -0.02 / -0.43 | 0.13 / 0.09 |
| Trailing stop 2 ATR, no target | +0.22 / +0.09 | +0.08 / +0.01 | +0.24 / +0.09 | 0.15 / 0.08 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | -0.01 / -0.38 | -0.09 / -0.43 | -0.01 / -0.38 | 0.07 / 0.05 |
| Pyramid, 2 adds | +0.01 / -0.64 | -0.32 / -0.84 | +0.02 / -0.63 | 0.34 / 0.21 |
| Pyramid, 4 adds | -0.02 / -0.72 | -0.38 / -0.92 | -0.01 / -0.71 | 0.37 / 0.21 |
| Hedge lock, unlocked by the next vote signal | +0.03 / -0.40 | +0.04 / -0.40 | +0.03 / -0.40 | 0.01 / 0.00 |
| Close at -1 ATR, re-enter on the next vote signal | +0.03 / -0.40 | +0.04 / -0.40 | +0.03 / -0.40 | 0.01 / 0.00 |
| Hedge lock, both legs closed 4 h later | -0.08 / -0.57 | -0.07 / -0.57 | -0.08 / -0.57 | 0.00 / 0.00 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -0.14 / -2.66* | -0.09 / -2.31* | -0.09 / -2.31* | 0.05 / 0.35 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.24 / -2.74* | -0.97 / -2.40* | -0.99 / -2.40* | 0.28 / 0.34 |
| Stop and reverse, same size | -0.10 / -0.68 | -0.09 / -0.66 | -0.10 / -0.66 | 0.02 / 0.03 |
| Stop and reverse, double size | -0.20 / -0.98 | -0.18 / -0.93 | -0.19 / -0.93 | 0.03 / 0.05 |
| Martingale: double after a loss, up to x8 | +0.00 / -0.74* | +0.03 / -0.74* | +0.00 / -0.74* | 0.02 / 0.00 |
| Anti-martingale: double after a win, up to x8 | +0.00 / -1.01* | +0.00 / -1.01* | +0.00 / -1.01* | 0.00 / 0.00 |
| Daily loss limit 1 R | +0.15 / -0.55 | +0.15 / -0.55 | +0.15 / -0.55 | 0.00 / 0.00 |
| Daily loss limit 2 R | +0.04 / -0.44 | +0.04 / -0.44 | +0.04 / -0.44 | 0.00 / 0.00 |
<!-- /table -->

BTC, votes only:

<!-- table order:BTCUSDm:votes -->
| Mechanism | Unfavourable extreme first (the result) | Favourable extreme first | Shortest path | Widest gap |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | -0.05 / -0.39 | -0.05 / -0.39 | -0.05 / -0.39 | 0.00 / 0.00 |
| Fixed stop 2 ATR, target 2 ATR | -0.13 / -0.04 | -0.13 / -0.04 | -0.13 / -0.04 | 0.00 / 0.00 |
| Fixed stop 1 ATR, target 2 ATR | -0.07 / -0.31 | -0.07 / -0.31 | -0.07 / -0.31 | 0.00 / 0.00 |
| Fixed stop 2 ATR, target 1 ATR | -0.03 / -0.30 | -0.03 / -0.30 | -0.03 / -0.30 | 0.00 / 0.00 |
| Fixed stop $20, target $20 (the V2 exit) | +0.12 / -0.40 | +0.12 / -0.40 | +0.12 / -0.40 | 0.00 / 0.00 |
| Live ladder, no stop | +1.00 / -3.07* | +1.00 / -3.07* | +1.00 / -3.07* | 0.00 / 0.00 |
| Live ladder, basket stop $60 | -0.46 / -1.75* | -0.34 / -1.54* | -0.38 / -1.61* | 0.12 / 0.20 |
| Live ladder, basket stop $200 | +0.21 / -1.98* | +0.21 / -1.93* | +0.21 / -1.93* | 0.00 / 0.05 |
| Budget 1 R, no add | -0.01 / -0.40 | -0.01 / -0.40 | -0.01 / -0.40 | 0.00 / 0.00 |
| Budget 1 R, 2 adds 0.17 ATR apart | -0.20 / -0.80* | -0.20 / -0.81* | -0.21 / -0.80* | 0.01 / 0.01 |
| Budget 2 R, no add | -0.04 / -0.27 | -0.04 / -0.27 | -0.04 / -0.27 | 0.00 / 0.00 |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.01 / -0.80* | -0.02 / -0.81* | -0.02 / -0.81* | 0.01 / 0.01 |
| Budget 3 R, no add | -0.08 / -0.36 | -0.08 / -0.36 | -0.08 / -0.36 | 0.00 / 0.00 |
| Budget 3 R, 1 add 1 ATR apart | -0.14 / -0.34 | -0.14 / -0.35 | -0.14 / -0.35 | 0.01 / 0.01 |
| Budget 3 R, 2 adds 0.5 ATR apart | +0.01 / -0.64* | -0.01 / -0.65* | -0.01 / -0.65* | 0.02 / 0.01 |
| Budget 3 R, 3 adds 0.3 ATR apart | -0.03 / -0.93* | -0.03 / -0.95* | -0.03 / -0.95* | 0.00 / 0.02 |
| Budget 3 R, 4 adds 0.2 ATR apart | +0.03 / -1.14* | +0.01 / -1.15* | +0.02 / -1.15* | 0.02 / 0.01 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | +0.01 / -0.64* | -0.01 / -0.65* | -0.01 / -0.65* | 0.02 / 0.01 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | +0.01 / -0.64* | -0.01 / -0.65* | -0.01 / -0.65* | 0.02 / 0.01 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | +0.01 / -0.64* | -0.01 / -0.65* | -0.01 / -0.65* | 0.02 / 0.01 |
| Add when the M5 MACD histogram turns | -0.10 / -0.52 | -0.10 / -0.52 | -0.10 / -0.52 | 0.00 / 0.00 |
| Add when the M15 MACD histogram turns | -0.13 / -0.32 | -0.13 / -0.32 | -0.13 / -0.32 | 0.00 / 0.00 |
| Add when the M5 RSI comes back through 35 / 65 | -0.09 / -0.43 | -0.09 / -0.43 | -0.09 / -0.43 | 0.00 / 0.00 |
| Add when the M15 RSI comes back through 35 / 65 | -0.16 / -0.39 | -0.16 / -0.39 | -0.16 / -0.39 | 0.00 / 0.00 |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.04 / -0.40 | -0.11 / -0.45 | -0.04 / -0.40 | 0.07 / 0.05 |
| Break-even at +1 ATR (stop 1, target 2) | -0.07 / -0.43 | -0.09 / -0.45 | -0.07 / -0.43 | 0.02 / 0.02 |
| Trailing stop 1 ATR, no target | +0.02 / -0.48 | -0.09 / -0.54 | +0.03 / -0.48 | 0.12 / 0.06 |
| Trailing stop 2 ATR, no target | -0.10 / -0.35 | -0.19 / -0.39 | -0.09 / -0.35 | 0.10 / 0.04 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | -0.06 / -0.41 | -0.13 / -0.45 | -0.06 / -0.41 | 0.07 / 0.04 |
| Pyramid, 2 adds | +0.02 / -0.77* | -0.27 / -0.90* | +0.03 / -0.76* | 0.30 / 0.14 |
| Pyramid, 4 adds | +0.02 / -0.81* | -0.32 / -0.94* | +0.03 / -0.81* | 0.35 / 0.14 |
| Hedge lock, unlocked by the next vote signal | -0.14 / -0.60 | -0.14 / -0.60 | -0.14 / -0.60 | 0.00 / 0.00 |
| Close at -1 ATR, re-enter on the next vote signal | -0.14 / -0.60 | -0.14 / -0.60 | -0.14 / -0.60 | 0.00 / 0.00 |
| Hedge lock, both legs closed 4 h later | -0.12 / -0.57 | -0.12 / -0.57 | -0.12 / -0.57 | 0.00 / 0.00 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -0.67 / -2.33* | -0.61 / -2.05* | -0.61 / -2.05* | 0.06 / 0.27 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.22* / -2.50* | -1.00* / -2.05* | -1.00* / -2.07* | 0.22 / 0.45 |
| Stop and reverse, same size | -0.10 / -0.66 | -0.09 / -0.64 | -0.09 / -0.64 | 0.02 / 0.03 |
| Stop and reverse, double size | -0.15 / -0.94* | -0.12 / -0.88* | -0.13 / -0.88* | 0.03 / 0.06 |
| Martingale: double after a loss, up to x8 | -0.41 / -1.25* | -0.40 / -1.25* | -0.41 / -1.25* | 0.01 / 0.00 |
| Anti-martingale: double after a win, up to x8 | +0.11 / -0.84* | +0.11 / -0.84* | +0.11 / -0.84* | 0.00 / 0.00 |
| Daily loss limit 1 R | -0.31 / -0.43 | -0.31 / -0.43 | -0.31 / -0.43 | 0.00 / 0.00 |
| Daily loss limit 2 R | -0.13 / -0.41 | -0.13 / -0.41 | -0.13 / -0.41 | 0.00 / 0.00 |
<!-- /table -->

BTC, random:

<!-- table order:BTCUSDm:random -->
| Mechanism | Unfavourable extreme first (the result) | Favourable extreme first | Shortest path | Widest gap |
|---|---|---|---|---|
| Fixed stop 1 ATR, target 1 ATR (reference) | -0.19 / -0.10 | -0.19 / -0.10 | -0.19 / -0.10 | 0.00 / 0.00 |
| Fixed stop 2 ATR, target 2 ATR | -0.13 / -0.10 | -0.13 / -0.10 | -0.13 / -0.10 | 0.00 / 0.00 |
| Fixed stop 1 ATR, target 2 ATR | -0.18 / -0.02 | -0.18 / -0.02 | -0.18 / -0.02 | 0.00 / 0.00 |
| Fixed stop 2 ATR, target 1 ATR | -0.06 / -0.01 | -0.06 / -0.01 | -0.06 / -0.01 | 0.00 / 0.00 |
| Fixed stop $20, target $20 (the V2 exit) | -0.16 / +0.19 | -0.16 / +0.19 | -0.16 / +0.19 | 0.00 / 0.00 |
| Live ladder, no stop | -1.61* / -5.29* | -1.61* / -5.29* | -1.61* / -5.29* | 0.00 / 0.00 |
| Live ladder, basket stop $60 | -1.14* / -2.00* | -0.89* / -1.68* | -0.94* / -1.74* | 0.25 / 0.33 |
| Live ladder, basket stop $200 | -1.19* / -1.97* | -1.13* / -1.92* | -1.13* / -1.92* | 0.06 / 0.05 |
| Budget 1 R, no add | -0.17 / -0.22 | -0.17 / -0.22 | -0.17 / -0.22 | 0.00 / 0.00 |
| Budget 1 R, 2 adds 0.17 ATR apart | -0.27 / -0.76* | -0.28 / -0.77* | -0.28 / -0.77* | 0.01 / 0.00 |
| Budget 2 R, no add | -0.12 / -0.18 | -0.12 / -0.18 | -0.12 / -0.18 | 0.00 / 0.00 |
| Budget 2 R, 2 adds 0.33 ATR apart | -0.23 / -0.49 | -0.24 / -0.49 | -0.24 / -0.49 | 0.00 / 0.00 |
| Budget 3 R, no add | -0.14 / -0.08 | -0.14 / -0.08 | -0.14 / -0.08 | 0.00 / 0.00 |
| Budget 3 R, 1 add 1 ATR apart | -0.24 / -0.28 | -0.24 / -0.29 | -0.24 / -0.29 | 0.00 / 0.01 |
| Budget 3 R, 2 adds 0.5 ATR apart | -0.29 / -0.42 | -0.29 / -0.43 | -0.29 / -0.43 | 0.00 / 0.02 |
| Budget 3 R, 3 adds 0.3 ATR apart | -0.42 / -0.51 | -0.44 / -0.51 | -0.44 / -0.51 | 0.02 / 0.01 |
| Budget 3 R, 4 adds 0.2 ATR apart | -0.36 / -0.69* | -0.37 / -0.69* | -0.36 / -0.68* | 0.00 / 0.01 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart | -0.29 / -0.41 | -0.29 / -0.43 | -0.29 / -0.43 | 0.00 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over the weekend | -0.29 / -0.41 | -0.29 / -0.43 | -0.29 / -0.43 | 0.00 / 0.02 |
| Budget 3 R but never more than $60, 2 adds 0.5 ATR apart, flat over every market closure | -0.29 / -0.41 | -0.29 / -0.43 | -0.29 / -0.43 | 0.00 / 0.02 |
| Add when the M5 MACD histogram turns | -0.30 / -0.26 | -0.30 / -0.26 | -0.30 / -0.26 | 0.00 / 0.01 |
| Add when the M15 MACD histogram turns | -0.30 / -0.33 | -0.30 / -0.32 | -0.30 / -0.32 | 0.00 / 0.01 |
| Add when the M5 RSI comes back through 35 / 65 | -0.28 / -0.31 | -0.28 / -0.31 | -0.28 / -0.31 | 0.00 / 0.01 |
| Add when the M15 RSI comes back through 35 / 65 | -0.15 / -0.32 | -0.15 / -0.32 | -0.15 / -0.32 | 0.00 / 0.00 |
| Break-even at +0.5 ATR (stop 1, target 1) | -0.18 / -0.20 | -0.21 / -0.25 | -0.17 / -0.20 | 0.04 / 0.04 |
| Break-even at +1 ATR (stop 1, target 2) | -0.20 / -0.12 | -0.21 / -0.13 | -0.20 / -0.12 | 0.01 / 0.01 |
| Trailing stop 1 ATR, no target | -0.19 / -0.28 | -0.27 / -0.32 | -0.18 / -0.27 | 0.09 / 0.05 |
| Trailing stop 2 ATR, no target | -0.11 / +0.14 | -0.17 / +0.10 | -0.11 / +0.14 | 0.06 / 0.04 |
| Scale-out: half at +1 ATR, rest trailed by 1 ATR | -0.23 / -0.12 | -0.29 / -0.15 | -0.22 / -0.12 | 0.06 / 0.03 |
| Pyramid, 2 adds | -0.30 / -0.45 | -0.52 / -0.56 | -0.29 / -0.43 | 0.23 / 0.13 |
| Pyramid, 4 adds | -0.35 / -0.44 | -0.60 / -0.58 | -0.35 / -0.43 | 0.25 / 0.16 |
| Hedge lock, unlocked by the next vote signal | -0.19 / -0.28 | -0.19 / -0.27 | -0.19 / -0.28 | 0.00 / 0.00 |
| Close at -1 ATR, re-enter on the next vote signal | -0.19 / -0.28 | -0.19 / -0.27 | -0.19 / -0.28 | 0.00 / 0.00 |
| Hedge lock, both legs closed 4 h later | -0.27 / -0.28 | -0.27 / -0.28 | -0.27 / -0.28 | 0.00 / 0.00 |
| Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12 | -0.60 / -1.31* | -0.46 / -0.98 | -0.46 / -0.98 | 0.14 / 0.33 |
| Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62 | -1.46* / -2.42* | -1.15* / -1.91* | -1.15* / -1.92* | 0.31 / 0.51 |
| Stop and reverse, same size | -0.26 / -0.30 | -0.25 / -0.27 | -0.25 / -0.27 | 0.01 / 0.03 |
| Stop and reverse, double size | -0.33 / -0.51 | -0.32 / -0.44 | -0.32 / -0.45 | 0.02 / 0.07 |
| Martingale: double after a loss, up to x8 | -0.46 / -0.23 | -0.46 / -0.23 | -0.46 / -0.23 | 0.00 / 0.00 |
| Anti-martingale: double after a win, up to x8 | -0.32 / +0.19 | -0.32 / +0.19 | -0.32 / +0.19 | 0.00 / 0.00 |
| Daily loss limit 1 R | -0.11 / -0.07 | -0.11 / -0.07 | -0.11 / -0.07 | 0.00 / 0.00 |
| Daily loss limit 2 R | -0.17 / +0.01 | -0.17 / +0.01 | -0.17 / +0.01 | 0.00 / 0.00 |
<!-- /table -->

</details>

## Reproduce

```
python -m backtesting.research.recovery run --periods DEV CONFIRM      # a few minutes; writes the three CSV files
python -m backtesting.research.recovery tables --update backtest_results/improve/recovery_mechanisms.md
python -m pytest tests/test_recovery_sim.py -q
```

Result files, all in this directory: `recovery_mechanisms.csv` (every number above and more: average
win and loss, units opened, holding time, expectancy in R, the two other bar readings, baskets beyond
their budget), `recovery_mechanisms_halfyears.csv` and `recovery_mechanisms_gaps.csv`. `run --cache DIR`
also writes every single basket of every mechanism to `DIR`.
