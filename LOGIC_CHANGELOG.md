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
MACD turn helps a little on gold and hurts a little on BTC; not the default. Details: `IMPROVEMENT.md`.

---

## 2026-11-15 · Final exam on 2023 — designs frozen before the run

**Status:** pre-registered (written before any 2023 result was seen); the result is the entry above.

Chosen on DEV + CONFIRM together (11 quarters per symbol) by a rule fixed in advance: the largest sum over
both symbols of (mean per quarter − one standard error), never wiped, deepest dip under $500 on both.
All use the H1 trend filter, force-close off, distances in H1 volatility units (24-bar average move),
and are run unchanged on 2023.

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
