# Logic change log

Every change to the trading logic that has been designed, tested, adopted or rejected — newest first.
The live bot's own release notes stay in `CHANGELOG.md`; this file is about *what the strategy does and why*.

**Status** of an entry is one of:
*live* (in the bot's code) · *backtest-only* (a backtester setting, off by default, so the default run is still the live bot) · *in progress* · *rejected* (tested and not kept, with the reason).

Unless said otherwise, results are for a real $2,000 account with the bot's unit rule, every tick
replayed, five quarters (13 Aug 2025 → 13 Nov 2026), each run eight times with random loop timing.

---

## How the logic fits together (one pass of the loop, as the backtester runs it)

```
                       every ~1 second
                             │
              ┌──────────────▼──────────────┐
              │ read bid / ask, RSI & MACD  │
              │ votes (live: H1 + M15)      │
              └──────────────┬──────────────┘
                       basket open?
            ┌──────── no ────┴──── yes ────────┐
            ▼                                  ▼
 ┌──────────────────────┐        ┌──────────────────────────────┐
 │ ENTRY: all must pass │        │ EXIT: the first that fires   │
 │ · votes agree        │        │ closes the whole basket      │
 │ · pause over: 5 min  │        │ · stop-loss  ($ or vol ★)    │
 │   after a win, longer│        │ · target     ($ or vol ★)    │
 │   after a loss ★     │        │ · trailing stop ★            │
 │ · trading hours      │        │ · M15 force-close (can be    │
 │ · with the H1 trend ★│        │   switched off)              │
 │ · spread not wide ★  │        │ · time stop                  │
 │ · day's loss limit   │        └──────────────┬───────────────┘
 │   not reached ★      │                 nothing fired
 └──────────┬───────────┘                       ▼
            ▼                    ┌──────────────────────────────┐
       open 1 unit               │ LADDER: add the next tier if │
                                 │ · its trigger fires ★        │
                                 │ · far enough from the last   │
                                 │   fill ($ or vol ★)          │
                                 │ · adds left (max_adds)       │
                                 └──────────────────────────────┘
 ★ = added in Round 1 / Round 2 (backtest only, off by default)
```

**How the data is used, so that results generalise**

```
 2023            │ 2024 ──── Jun 2025    │ Jul 2025 ─────────── Nov 2026
 FINAL exam      │ CONFIRM               │ DEV
 locked until    │ run once, nothing     │ explore, tune, choose
 the very end    │ re-tuned              │
```

---

## 2026-11-15 · The final ten: pre-registration (before any 2018-2020 data is read)

**Status:** *in progress*. Results will be added to this entry; nothing about the selection or the test changes after this commit.

**What.** Every design and published strategy tested so far is narrowed to ten per symbol by one fixed rule. The ten are then run on three windows, each on a fresh $2,000 account: eight years (13 Nov 2018 → 13 Nov 2026), five years (13 Nov 2021 → 13 Nov 2026) and the last year (13 Nov 2025 → 13 Nov 2026). The eight-year window also gets its own account for the part no study had read: 13 Nov 2018 → 31 Dec 2020, downloaded for this test (BTC's archive starts in January 2018, gold's in 2016).

**The rule** (code: `backtesting/research/final10.py`; lists: `backtest_results/final10/selection.json`; evidence: `evidence.csv`)
- Pool: every row with results in all five periods 2021, 2022, 2023, 2024-25 and 2025-26. That is 87 rows for gold and 78 for BTC: our round-4 designs plus the ten published strategies, with every parameter set, variant and sizing.
- One yardstick: fresh $2,000 accounts per quarter, the average profit per quarter in each period. For our designs this is the median of the eight loop timings.
- Eligible: profit in at least 4 of the 5 periods, never wiped, worst quarter's drawdown at most 50%. That leaves 20 rows for gold and 25 for BTC.
- Ranked by profit per unit of drawdown: the average profit per quarter divided by the worst quarter's drawdown in %.
- At most two rows of any one published strategy; each of our designs counts on its own.

**The finalists** (average profit per quarter 2021 / 2022 / 2023 / 2024-25 / 2025-26, worst quarter's drawdown)

| # | Gold | Evidence | DD | BTC | Evidence | DD |
|---|---|---|---|---|---|---|
| 1 | London breakout + H1 trend | +10 / +50 / −0 / +62 / +179 | 11% | Top 2 (ours) | −24 / +20 / +21 / +148 / +56 | 10% |
| 2 | London breakout, 1% risk per trade | +2 / +52 / −2 / +170 / +7 | 9% | Top 3 (ours) | −61 / +43 / +18 / +102 / +157 | 12% |
| 3 | V3-lite + 200-day trend filter | +2 / +26 / +1 / +121 / +244 | 16% | Turtle + bot votes | +189 / +116 / +58 / +139 / +163 | 33% |
| 4 | V3-lite + 12-month momentum filter | +0 / +0 / +2 / +121 / +206 | 16% | V3-lite + 1/3/12-month momentum filter | +35 / +39 / −4 / +45 / +38 | 8% |
| 5 | Top 3 (ours) | +28 / −38 / +26 / +111 / +555 | 40% | Turtle, 1% of equity per N | +0 / +103 / +95 / +87 / +44 | 17% |
| 6 | 41 / 356 moving average (M5) + H1 trend | +13 / −13 / +5 / +112 / +450 | 35% | Daily volatility breakout + bot votes | +37 / +14 / +6 / +27 / +6 | 6% |
| 7 | V3-lite (ours) | +28 / +3 / +105 / +154 / +409 | 45% | Daily volatility breakout | +49 / +19 / +15 / +30 / +6 | 8% |
| 8 | Noise-area momentum, vol-targeted | −76 / +51 / +135 / +19 / +53 | 12% | Connors RSI(2) + bot votes | +2 / +14 / +1 / +16 / +28 | 4% |
| 9 | 34 / 339 moving average (M5) + H1 trend | +13 / −12 / +13 / +133 / +402 | 39% | V3-lite (ours) | −26 / +25 / +8 / +48 / +121 | 12% |
| 10 | V3-lite + H4 Supertrend filter | −37 / +14 / +5 / +76 / +105 | 30% | TSMOM (1/3/12-month) | +31 / +74 / −3 / +54 / +50 | 17% |

References, run alongside but not ranked: the live logic, the owner's rules design (round 3), our designs that missed the cut (gold: Top 1 and Top 2, which lost in 2 of the 5 periods; BTC: Top 1) and the bar-level V3-lite (to compare the two engines).

**How they run.** Our designs run on the tick engine: per-second replay for the long windows (eight years of raw ticks would not fit in memory) and raw ticks under eight loop timings for the last year. The published strategies and the V3-lite hybrids run on the M1-bar simulator of `external.py`, unchanged, with history from 2017 (gold) or 2018 (BTC) for the slow indicators. Rankings per symbol and window: highest final equity, lowest maximum drawdown, and the two combined (annual return ÷ maximum drawdown).

**How to read the results.** Data from 2021 on helped choose these rows. The five-year and one-year windows are therefore in-sample, and only Nov 2018 – Dec 2020 is a fair test.

---

## 2026-11-15 · Round 4: best combination of everything researched, and strategies from the internet

**Status:** backtest-only. Nothing changed in the live bot.

**Method.** (1) The optimiser searched 9,216 combinations of every rule that had held up (H1 trend filter, H1 or
H1 + M15 votes, M15 agreement on / off, stop and target 4-10 volatility units, a dollar cap on the unit, no ladder or one
MACD-turn add, 1 h / 4 h / 12 h pause after a loss, the owner's RSI-extreme entry block and RSI force-close, M15
force-close on / off) on 16 quarterly blocks of 2023 - Nov 2026, objective "average month minus its standard error",
drawdown limit $600. The three best that differ from each other were then run on raw ticks under eight loop timings.
(2) Two research agents collected ten published strategies (Supertrend, Turtle, Donchian ensemble, time-series momentum,
long-horizon moving averages, Asian-range / London breakout, intraday momentum, Connors RSI(2), ...) with their own
default settings, run standalone and combined with the bot's logic; an independent reviewer reproduced the top results.
(3) 2021-2022 was downloaded and kept untouched; everything above was fixed first, then run once on those two years.

**Our combinations** (average per quarter on a fresh $2,000, eight timings; continuous account and its deepest drawdown):

| Gold | 2023 | 2024-25 | 2025-26 | **2021-22** | One account 2023 – Nov 2026 | One account 2021-22 |
|---|---|---|---|---|---|---|
| Live logic | −$666 | −$675 | −$1,480 | **−$1,154** | wiped Mar 2023 | wiped Jun 2021 |
| V3-lite | +$106 | +$152 | +$404 | **+$16** | +$7,977 (DD 32%) | +$168 (DD 11%) |
| Top 1: H1 votes, target 10 / stop 8 units, one MACD-turn add, 4 h pause | +$2 | +$133 | +$685 | **$0** | +$10,446 (DD 32%) | −$43 (DD 28%) |
| Top 2: H1 votes, target 8 / stop 4 units, $12 cap, no ladder, 12 h pause | +$30 | +$158 | +$412 | **−$16** | +$6,889 (DD 15%) | −$119 (DD 13%) |
| Top 3: as Top 1 with a $12 cap and a 1 h pause | +$23 | +$115 | +$545 | **−$6** | +$5,459 (DD 37%) | −$26 (DD 21%) |

| BTC | 2023 | 2024-25 | 2025-26 | **2021-22** | One account 2023 – Nov 2026 | One account 2021-22 |
|---|---|---|---|---|---|---|
| Live logic | −$1,194 | −$1,995 | −$585 | **−$1,767** | wiped Apr 2023 | wiped Jan 2021 |
| V3-lite | +$7 | +$48 | +$114 | **+$2** | +$907 (DD 15%) | −$25 (DD 18%) |
| Top 1: H1 votes, 8 / 8 units, $20 cap, no ladder, 4 h pause | +$26 | +$73 | +$164 | **−$39** | +$1,705 (DD 13%) | −$384 (DD 27%) |
| Top 2: H1 votes, target 10 / stop 8 units, $12 cap, 4 h pause | +$22 | +$145 | +$53 | **−$2** | +$2,039 (DD 16%) | −$29 (DD 17%) |
| Top 3: H1 + M15 votes, 8 / 8 units, no cap, 4 h pause | +$18 | +$94 | +$160 | **−$6** | +$1,527 (DD 18%) | +$16 (DD 21%) |

None of the six uses the owner's RSI-extreme block, and none uses the M15 force-close; across the 400 sampled
combinations the M15 force-close made results worse on both symbols.

**Strategies from the internet** (per quarter, one account per period; full table in `external_strategies.md`):
the most consistent were, on gold, the Asian-range / London breakout (positive in all five periods 2021-2026, deepest
drawdown 29%); on BTC, Supertrend (10, 3) with the H1 trend filter (positive in all five, drawdown 21%), the daily
volatility breakout (all five, drawdown 10%) and the Turtle breakout with the bot's votes (all five, drawdown 48%). The
best gold rule of 2023-2026, Supertrend on H4 (+$1,340 a quarter in 2025-26), lost money in both 2021 and 2022.

**Verdict.** Every design that made money did so mostly in the strong gold trend of 2023-2026. In the range-bound and
falling markets of 2021-2022 the best of them were flat, and the live logic lost heavily in every period. For the most
equity with the least drawdown on gold: Top 1 had the highest equity in 2023-2026, Top 2 the lowest drawdown (15%), and
V3-lite was the only one that also ended 2021-22 in profit. On BTC no rule makes more than a few dollars a quarter.

---

## 2026-11-15 · Owner's rules on the live hedging logic: RSI-extreme entry block and RSI force-close

**Status:** backtest-only. Nothing changed in the live bot.

**Asked for.** Keep the live hedging logic (H1 + M15 entry, M15 force-close, Fibonacci ladder, $1 target) and add:
(1) no new position while the H1 or H4 RSI is beyond the overbought / oversold levels (35 / 65); (2) force-close a
basket also when the H1 and H4 RSI are both at the extreme against it (a buy: both ≤ 35; a sell: both ≥ 65), with the
reversal check on M15 (live) or H1. Aim: avoid entering on spikes and get out of spike positions quickly.

**New backtester settings** (off by default): `entry_rsi_block_tfs` with `entry_rsi_block_mode` (`any` = no entry
while either extreme is reached; `directional` = no buy at the overbought level, no sell at the oversold level),
`fc_rsi_tfs` (the RSI force-close), `agree_weights` (lets the force-close move to H1 while the entry still needs M15 to
agree, as live).

**Result.** Average per quarter, all 15 quarters (Feb 2023 – Nov 2026), real $2,000, every tick, eight loop timings per
quarter (accounts wiped of 120 runs):

| Design | Gold | BTC |
|---|---|---|
| Live logic | −$941 (27) | −$1,311 (49) |
| Your rules, entry block read as "directional" | −$781 (6) | −$1,255 (20) |
| **Your rules, literal: no entry while H1 or H4 RSI is beyond either level** | **−$175 (0)** | **−$712 (0)** |
| literal, force-close on H1 instead of M15 | −$197 (4) | −$598 (0) |
| literal entry block only (no RSI force-close) | −$129 (0) | −$772 (3) |
| literal + at most 3 ladder adds | −$148 (0) | −$620 (0) |
| "directional" reading + basket stop $40 per unit | −$1,057 (0) | −$1,209 (2) |
| literal + H1 trend filter | −$4 (0) | −$140 (0) |
| literal + H1 trend filter + 4 h pause after a loss | **+$9 (0)** | **−$125 (0)** |

- The "directional" reading lets the bot buy while H1 and H4 are both oversold; the RSI force-close then shuts that buy
  at once, so the bot churns small losses. The literal reading avoids it.
- The entry block is the part that removes the wipe-outs; the RSI force-close caps the worst basket.
- One continuous $2,000 account (per-second replay): the live logic was wiped in every window (gold 19 Jul 2024 and
  14 Oct 2025, BTC 28 Feb 2024 and 6 Feb 2026); with the literal rules gold ended Aug 2025 – Nov 2026 at +$1,244 (deepest
  drawdown 54%) but was wiped in the 2024-25 window on 9 Apr 2025, and BTC lost steadily. Chart:
  `backtest_results/improve/round3/equity_live_vs_your_rules.html`.

**Verdict.** The rules do what they are meant to: no more wiped accounts and a much smaller worst basket. The logic
still does not make money over 2023-2026: with the $1 target the small wins do not cover the spread and the remaining
losses. Adding the H1 trend filter and a 4 h pause brings gold to break-even and BTC to a small loss. For comparison,
V3-lite (entry below) made +$106 a quarter on gold in 2023.

---

## 2026-11-15 · Final exam result: V3-lite adopted for gold (backtest); BTC has no edge

**Status:** backtest-only. Recommended for a demo account: V3-lite on gold. Nothing changed in the live bot.

Average per quarter on a real $2,000 account (runs that lost money, of 8 timings × the quarters):

| Gold | DEV | CONFIRM | FINAL 2023 |
|---|---|---|---|
| Live | −$1,480 (37/40) | −$675 (47/48) | **−$666** (24/32) |
| V2 | +$251 (7/40) | +$71 (16/48) | **+$30** (16/32) |
| V3 (one MACD-turn add) | +$453 (8/40) | +$180 (12/48) | **+$58** (17/32) |
| V3 without the add | +$133 (8/40) | +$78 (16/48) | **+$5** (13/32) |
| **V3-lite** | +$404 (8/40) | +$152 (0/48) | **+$106** (0/32) |

| BTC | DEV | CONFIRM | FINAL 2023 |
|---|---|---|---|
| Live | −$585 (30/40) | −$1,995 (48/48) | **−$1,194** (32/32) |
| V2 | +$159 (7/40) | −$7 (24/48) | **−$17** (24/32) |
| V3 | +$109 (8/40) | +$34 (26/48) | **−$18** (16/32) |
| V3 without the add | +$100 (14/40) | +$60 (24/48) | **+$3** (12/32) |
| **V3-lite** | +$114 (8/40) | +$48 (24/48) | **+$7** (16/32) |

**Kept:** H1 trend filter; stop and target on the whole basket in volatility units (8 / 8); a long pause
after a loss; no ladder. **Rejected after testing:** support / resistance entries and targets (no edge in two
independent studies); every other recovery mechanism (none raises the expectancy); the live Fibonacci
ladder; an H4 trend filter (fails outside 2025-26). **Optional:** one equal-sized ladder add released by a
MACD turn earned more than no add on gold in every period and less on BTC in two of three; not the default. Details: `IMPROVEMENT.md`.

**V3-lite in one picture** (one pass of the loop, about once a second):

```
                     every ~1 second
                           │
              ┌────────────▼────────────┐
              │ market live? (a tick in │── no ──► wait
              │ the last 3 minutes)     │
              └────────────┬────────────┘
                          yes
                    basket open?
          ┌─────── no ─────┴───── yes ────────┐
          ▼                                   ▼
 ┌──────────────────────────┐   ┌────────────────────────────────┐
 │ all five must be true:   │   │ loss reaches the stop          │
 │ 1 inside the trading     │   │        → close the basket      │
 │   window (Mon 01:00 –    │   │ profit beyond the target       │
 │   Fri 22:00 UTC)         │   │        → close the basket      │
 │ 2 pause over: 5 min after│   │ otherwise → hold               │
 │   a win, 12 h after a    │   │ (no ladder, no M15 force-close,│
 │   loss                   │   │  no time limit)                │
 │ 3 H1 votes say BUY (SELL)│   └────────────────────────────────┘
 │ 4 both M15 votes agree   │
 │ 5 the H1 trend agrees    │
 └────────────┬─────────────┘
              ▼
  open 1 unit (unit × 0.01 lot) at the ask (buy) / bid (sell)
  stop = target = 8 × volatility unit × unit, fixed for this basket
```

- *H1 votes*: the bot's own RSI and MACD pivot-slope votes, read on H1 only (live: H1 + M15). BUY when both
  point up, or one points up and the other is neutral.
- *M15 agreement*: both M15 votes point the same way as the trade (the live `ENTRY_AGREE_S = 2`, unchanged).
- *H1 trend*: the H1 MACD signal line is above zero for a buy, below zero for a sell, on the last closed H1 bar.
- *Volatility unit*: the average move of one H1 candle (close to close) over about the last 24 H1 candles, in
  dollars per 0.01 lot, measured when the basket opens. Median 8 units per 0.01 lot: gold $16 (2023), $23 (2024),
  $39 (2025), $75 (2026); BTC $6, $18, $23, $16.
- In the tests, gold: about 25 baskets a quarter, held about a day (median 23 to 37 h), 60 to 64% won, the average
  win about the size of the average loss in 2023 and 2024-25 (2023: +$16.49 / −$16.09); in Aug 2025 – Nov 2026 the average
  loss was larger (−$112 against +$87, worst basket −$789).

---

## 2026-11-15 · Final exam on 2023 — designs frozen before the run

**Status:** pre-registered (written before any 2023 result was seen); the result is the entry above.

Chosen on DEV + CONFIRM together (11 quarters per symbol) by a rule fixed in advance: the largest sum over
both symbols of (mean per quarter − one standard error), never wiped, deepest dip under $500 on both.
V3, V3 without the add and V3-lite use the H1 trend filter, force-close off and distances in H1 volatility units
(24-bar average move); V2 (fixed $20 / $20) and Live are the references. All five are run unchanged on 2023.

| Design | Rule |
|---|---|
| **V3** (with a ladder) | live votes H1 + M15, M15 must agree, H1 trend filter · target 8 units, stop 8 units on the whole basket · one equal-sized add, released when the M5 MACD vote turns back with the basket, at least 1 unit from the entry · 4 h pause after a loss |
| V3 without the add | the same, no ladder (the paired twin: shows what the add itself is worth) |
| V3-lite | H1 votes only, M15 must agree, H1 trend filter · target 8, stop 8 units · no ladder · 12 h pause after a loss |
| V2 | H1 trend filter · target $20, stop $20 per 0.01 lot · no ladder · 4 h pause after a loss |
| Live | the bot as it runs today |

The test: every tick replayed, eight random loop timings per quarter, a real $2,000 account with the bot's unit
rule. FINAL = Feb → Dec 2023 (January is indicator warm-up), in four blocks. DEV and CONFIRM are run the same way
for comparison. Nothing is changed after the FINAL numbers are seen; whatever they show is reported.

---

## 2026-11-14 · Round 2 — keep a ladder but bound it; other recovery mechanisms; support / resistance again; an optimiser

**Status:** done; the outcome is the final-exam entry above. Everything below is on `backtest_hedging`.

**Asked for.** Keep the DCA ladder (it does lower the average entry when price pulls back) but stop it
eating the balance; try other triggers for the adds (MACD instead of an RSI level); say which other
recovery mechanisms exist; look again at support and resistance from H1 / H4 / D1; build an optimiser;
improve the score further without overfitting.

**State.**

| Item | What | State |
|---|---|---|
| Ladder triggers | see below | built and tested; reviewed (no look-ahead found; three fixes made) |
| Volatility units, trailing exit, daily loss limit | see below | built and tested; reviewed |
| Support / resistance | two independent studies of H1 / H4 / D1 levels: level reactions against matched non-levels, and S/R trading rules against placebo levels | done: no edge (`sr_study.md`, `sr_trades.md`) |
| Recovery mechanisms | averaging down with a hard budget, averaging up, break-even / trailing, scale-out, hedge lock, zone recovery, stop-and-reverse, martingale / anti-martingale, daily loss limit, compared on identical entries | done: none raises the expectancy (`recovery_mechanisms.md`) |
| Optimiser | search any setting from a parameter file; ranks by consistency; reports hold-out, walk-forward and the chance that the winner is overfitted | done: `python -m backtesting optimise`, guide in `backtesting/OPTIMISER.md` |
| More history | 2023-01 → 2025-06: 2024-01 → 2025-06 confirms what is found, 2023 stays untouched as the final exam | done: 47 months per symbol (Jan 2023 → Nov 2026) |

### Built: what releases a ladder add (`ladder_trigger`)

| Trigger | The next add happens when | Character |
|---|---|---|
| `rsi_level` (live) | the tier timeframe's RSI is ≤ 35 (buy) / ≥ 65 (sell) | a state: in a strong fall M1, M5, M15, H1 and H4 are all beyond 35 at once, so five adds (31 more units) go in within seconds |
| `rsi_cross` | that RSI has been beyond the level and has come back inside by `ladder_rsi_exit` points | waits for the fall to turn; one add per dip |
| `macd_turn` | that timeframe's MACD vote turns back in the basket's favour | waits for momentum to turn |
| `price_step` | price is a set distance worse than the last fill | classic evenly spaced averaging down |
| `profit_step` | price is a set distance better than the last fill | adds to a winner (pyramiding), normally with a trailing exit |

The size of each add (`ladder_multipliers`: live Fibonacci 1,2,3,5,8,13, or flat 1,1,1, or 1,1,2,3), how many (`max_adds`) and how far apart (`ladder_min_gap` / `ladder_gap_vol`, `ladder_min_interval_s`) are set separately.

**Why a basket stop bounds the ladder.** Stop and target are on the whole basket, in dollars per unit.
An add cannot make the loss larger than the stop; it brings both the stop and the target closer in price.
Gold, 0.01 lot each, stop and target $20, entry at 4,000, one add of the same size 10 lower:

| | no ladder | with one add at 3,990 |
|---|---|---|
| stop is hit at | 3,980 (−$20) | 3,985 (−$15 − $5 = −$20) |
| target is hit at | 4,020 (+$20) | 4,005 (+$5 + $15 = +$20) |

### Built: distances that follow the market, and two more exits

| Setting | Logic |
|---|---|
| `vol_tf`, `vol_len` | volatility unit = average size of one bar's move on that timeframe (exponentially weighted over `vol_len` bars), read from the last closed bar when the basket opens and kept for its life. Gold's H1 unit was about $6 per 0.01 lot in Aug–Oct 2025 and about $15 in Feb–Apr 2026, so a fixed $20 stop is about three normal bars in a calm quarter and barely one in a wild one |
| `target_vol`, `stop_vol`, `ladder_gap_vol`, `trail_start_vol`, `trail_gap_vol` | the same distances as multiples of that unit |
| `vol_cap_usd_per_unit` | a dollar ceiling on the unit, so the risk of a basket cannot grow without limit in a crash |
| `trail_start_usd_per_unit`, `trail_gap_usd_per_unit` | trailing exit: once the basket is that far in profit, close it when it gives back the gap from its best |
| `daily_loss_limit_usd_per_unit` | no new basket for the rest of the UTC day once that day's closed baskets have lost this much |

With all of these off the engine still makes the same decisions as the real `app.py` loop on the 14
recorded windows, and 244 rule tests pass on both variants.

### First reading (provisional)

Development quarters only, one run each, one fixed 0.01-lot unit, inside the frame "H1 trend filter,
force-close off, 4 h pause after a loss"; net per quarter averaged over seven stop / target sizes
(2 to 8 volatility units). All adds equal-sized unless stated.

| Ladder | Gold | BTC |
|---|---|---|
| no ladder | +$265 | +$81 |
| 1 add, price step 1 unit | +$219 | +$61 |
| 1 add, MACD turn, at least 1 unit apart | +$216 | +$58 |
| 1–3 adds, RSI cross-back | +$175 … +$196 | +$58 … +$78 |
| 1–3 adds, price step 2 units (flat or 1,1,2,3) | +$172 … +$188 | +$82 … +$90 |
| 2 adds, RSI level (the live trigger), at least 1 unit apart | +$150 | +$68 |
| 2–3 adds, price step 1 unit | +$84 … +$99 | +$27 … +$45 |
| adding to winners, trailing exit | +$76 … +$258 | +$11 … +$13 |

So far: one well-spaced add costs little or nothing against no ladder; several close adds cost a lot;
the live RSI-level trigger is the weakest. Inside the trend filter the live entry votes (H1 + M15) stay
the best entry, and an H1 trend beats an H4 trend on both symbols. Not yet confirmed on 2024 – mid-2025.

---

## 2026-11-14 · V2 design — trend filter, real stop, no ladder

**Status:** backtest-only (nothing changed in the live bot).

**What.** Entries only with the H1 trend (sign of the H1 MACD signal line on the last closed bar) ·
no DCA ladder · target $20 and stop $20 per 0.01 lot · M15 force-close off · 4-hour pause after a losing basket.

**Why.** An entry screen of twenty ideas found no reliable edge in any indicator signal; on gold the
bot's entries *against* the higher-timeframe trend are the losing half. The losses come from structure:
a ladder that puts 26 of 32 units in at one price within seconds, no stop, and a $1 target that the
spread eats a quarter of.

**Evidence.**

| | Live, gold | V2, gold | Live, BTC | V2, BTC |
|---|---|---|---|---|
| Average per quarter | −$1,480 | +$251 | −$585 | +$159 |
| Runs that lost money | 37 of 40 | 7 of 40 | 30 of 40 | 7 of 40 |
| Runs stopped out | 27 of 40 | 0 | 0 | 0 |
| Worst drawdown | 102% | 13% | 95% | 9% |
| Worst single basket | −$1,944 | −$34 | −$811 | −$22 |

Chosen on three quarters, positive on the two unseen ones. 191 designs were tried, so the best are
flattered; the edge per trade is small (about $2 on gold, $3.50 on BTC, on $20 of risk). Details: `IMPROVEMENT.md`.

**Settings.** `trend_tf=H1`, `max_adds=0`, `target_usd_per_unit=20`, `stop_loss_usd_per_unit=20`,
`force_close_enabled=false`, `loss_cooldown_s=14400`.

**Open point raised by the owner.** V2 has no ladder at all. Round 2 looks for a bounded ladder that keeps the benefit.

---

## 2026-11-14 · New backtester settings: trend filter, pause after a loss, spread cap

**Status:** backtest-only, off by default.

| Setting | Logic |
|---|---|
| `trend_tf`, `trend_mode` | a fresh entry is allowed only in the direction (+1) of the named timeframe's trend, or only against it (−1); the trend is the sign of the MACD signal line of that timeframe's last closed bar |
| `loss_cooldown_s` | after a basket that closed at a loss, wait this long before the next entry (instead of the usual 5 minutes) |
| `entry_max_spread` | no fresh entry while the quoted spread is wider than this |

**Result.** The trend filter is the largest single lever on gold (all designs averaged, per 0.01 lot per
quarter: no filter −$423, H4 trend −$25, H1 trend +$6). A one-hour pause after a loss roughly halves the
average loss on gold. **Rejected:** the spread cap changed nothing (the spread is rarely wide when the bot wants in).

---

## 2026-11-14 · Entry ideas screened and not built

**Status:** rejected for now (re-opened in Round 2 for support / resistance with higher-timeframe levels).

Twenty signals measured on every closed M15 bar over fifteen months: RSI extremes on M15 / H1 / H4, RSI
divergence (plain, with the trend, at the day's high / low), bounce off and breakout of the one-day high /
low, momentum, time of day, the bot's own votes. None is statistically reliable on either symbol; on gold
most fading signals lose in four or five quarters of five. Tables: `backtest_results/improve/edge_screen_*.txt`.

---

## Baseline · the live logic (v3.9.2) as the backtester reproduces it

**Status:** live.

- **Entry:** RSI(14) and MACD(12,26,9) "pivot-slope votes" on H1 and M15 must agree (OPEN score ≥ 2, M15 agreement ≥ 2); 5-minute cooldown after any close.
- **Ladder:** up to five adds of ×2, 3, 5, 8, 13 units when the RSI of M1, M5, M15, H1, H4 is at or beyond 35 (longs) / 65 (shorts).
- **Exit (hedging variant):** +$1 × unit for the whole basket; force-close when the M15 score turns against the basket. No stop at the broker.
- **Size:** unit = floor(balance / 2,500) + 1, re-derived when flat; 0.01 lot per unit.
- **Backtest:** stopped out in 27 of 40 quarter-runs on gold; average −$1,480 a quarter on gold and −$585 on BTC. The backtester makes the same decisions as the real `app.py` loop on 14 fidelity windows (711,376 polls).
