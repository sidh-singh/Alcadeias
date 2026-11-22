# The six demo branches and how they were checked

On 2026-11-15 the owner asked for three demo branches per symbol, each running one of the best three strategies, built like the `hedging_<symbol>6/7/8` deployment branches so they can run on the demo account. This file records what each branch runs and how its code was shown to do what the backtest did.

## The branches

| Branch | Symbol | Strategy | Magic | Dashboard port | Its backtest (fresh $2,000, the bot's unit rule) |
|---|---|---|---|---|---|
| `demo_hedging_xauusd6` | XAUUSDm | V3-lite | 26116 | 8061 | 8 years $11,957, DD 33.0%; Nov 2018 – Dec 2020 +17.0%, DD 8.5% |
| `demo_hedging_xauusd7` | XAUUSDm | Top 2 | 26117 | 8062 | 8 years $8,545, DD 17.1%; Nov 2018 – Dec 2020 −4.5%, DD 10.7% |
| `demo_hedging_xauusd8` | XAUUSDm | Top 1 | 26118 | 8063 | 8 years $15,168, DD 32.5%; Nov 2018 – Dec 2020 +11.3%, DD 21.7% |
| `demo_hedging_btcusd6` | BTCUSDm | Turtle System 2 + bot votes | 26126 | 8071 | 8 years $7,815, DD 32.5%; Nov 2018 – Dec 2020 +42.9%, DD 9.4% |
| `demo_hedging_btcusd7` | BTCUSDm | Turtle System 1 + bot votes | 26127 | 8072 | 8 years $6,977, DD 46.0%; Nov 2018 – Dec 2020 +37.1%, DD 10.7% |
| `demo_hedging_btcusd8` | BTCUSDm | Top 2 | 26128 | 8073 | 8 years $4,149, DD 16.6%; Nov 2018 – Dec 2020 +4.1%, DD 2.3% |

Why these: the final ten's evidence (`backtest_results/final10/FINAL10.md`).
- Gold: V3-lite is the most dependable design, Top 2 has the best growth per unit of drawdown, and Top 1 has the most growth.
- BTC: the two Turtles are the only strategies that made real money, and Top 2 has the lowest drawdown of our designs.
- The two Turtles share many trades, so their demo results will move together.

Each branch was made from `hedging_<symbol><n>` with no upstream (a plain `git push` cannot reach the live branch). On top of the live code it has four layers.

1. **Plumbing.**
   - `mt5_credentials.json` keeps only the `demo` block, and the launchers refuse `live`.
   - Each branch has its own `OUTPUT_DIR` (`C:\Alcadeias\<branch>`), its own `DASHBOARD_PORT`, and its own `MAGIC`.
   - Each slot has its own demo account (set on 2026-11-16), shared by its gold and BTC bots, so the bots must still
     be kept apart on it.
2. **The port** (commit `22c382d` on gold; the same change on BTC). The backtest-only levers become constants of the bot: the H1 trend gate, the volatility target and stop with their cap, force-close off with the M15 votes kept for entry agreement, the pause after a loss, the M5 MACD-turn add, and the stop checked before the target.
   - Each lever defaults to the live v3.9.2 value. With all defaults the bot takes the live decisions, checked in `tests_demo/test_live_equivalence.py` and by the live replay below.
   - Every order carries the branch's magic number, and every decision reads only its own positions.
   - Units are sized from a virtual $2,000 plus the bot's own closed P/L (its deals since 2026-11-15). Each strategy is therefore sized as in the backtest, whatever the shared account holds.
   - A basket's fixed target, stop and add gap, and the pause, are kept in `OUTPUT_DIR/state`, so a restart keeps them.
3. **The Turtle** (BTC 6 and 7 only). `turtle.py` holds the rules as pure functions and runs behind `STRATEGY = 'turtle'`; the basket logic is untouched.
4. **The design block** at the end of `constants.py`, one per branch.

## The checks

### The basket designs: the bot's own code against the backtest engine, poll by poll

`backtesting/engine/demo_parity.py` replays a branch's own `app.py` through `backtesting/engine/reference.py`, a simulated MT5 terminal fed with real Exness ticks. It runs the fast engine on the same ticks with the design's settings, then compares:
- every 1 s poll: signal, scores, position count, floating P/L, unit, cooldown and pause state;
- every fill and close;
- the final balance.

The simulated terminal was extended for this (commit `c61c998`): magic numbers, comments, deal history, contract size, closed-bar reads, and a demo account shared with other bots.

| Design | Window (UTC) | Polls | What happened | Final balance, bot / engine | Verdict |
|---|---|---|---|---|---|
| Gold V3-lite | 2026-10-28 17:00 – 10-30 14:00 | 154,856 | buy stopped −$42.47, sell at target +$54.87; the trend held entries back on 12,290 polls | $2,012.40 / $2,012.40 | pass |
| Gold V3-lite | 2026-06-30 00:00 – 07-01 14:00 | 133,228 | sell stopped −$65.77; the next sell opened exactly when the 12 h pause ended, stopped −$80.66 | $1,853.57 / $1,853.57 | pass |
| Gold Top 2 | 2026-10-21 06:00 – 10-22 14:00 | 111,627 | sell stopped −$21.28, sell at target +$51.87; the pause changed the fills | $2,030.59 / $2,030.59 | pass |
| Gold Top 2 | 2026-01-28 22:00 – 01-30 02:00 | 93,359 | buy at target +$97.26, buy stopped −$51.97, both with the unit capped at $12 | $2,045.29 / $2,045.29 | pass |
| Gold Top 1 | 2026-11-02 22:00 – 11-03 14:00 | 53,960 | a 2-leg sell (the M5 MACD-turn add) at target +$82.60, a sell stopped −$64.75; 82 close-only refusals in both | $2,017.85 / $2,017.85 | pass |
| Gold Top 1 | 2026-10-12 00:00 – 10-13 05:00 | 100,819 | buy stopped −$51.73; the next buy opened when the 4 h pause ended, 2 legs, at target +$57.13 | $2,005.40 / $2,005.40 | pass |
| BTC Top 2 | 2026-09-03 14:00 – 09-04 13:00 | 82,799 | buy at target +$20.23, buy stopped −$21.20 | $1,999.03 / $1,999.03 | pass |
| BTC Top 2 | 2026-10-17 20:00 – 10-19 03:00 | 111,568 | sell stopped −$10.97; the next sell opened when the 4 h pause ended, stopped −$11.12; the trend held 5,400 polls | $1,977.91 / $1,977.91 | pass |

Every window had 0 signal, score and fill mismatches, and no live-code errors. The largest RSI difference was 4.3e-14.

The windows were chosen with the fast engine first, so that across a design's two windows the trend gate, the stop, the target and the pause each act at least once. The replays ran on the shared $10,000 account, so the magic-number isolation was checked too.

Two extra replays passed on scaled-down settings (minute bars, short windows) that make every rule fire often:
- gold V3-lite: 3 baskets, 2 targets, 1 stop;
- BTC Top 2 with the MACD-turn add: 9 baskets, 2 adds, 22 of 22 fills.

The port at its live defaults, replayed against the live configuration (XAUUSDm, 2026-11-12 00:00 – 10:00, 35,978 polls, 24 baskets), also passed: the port does not change the live bot.

### The Turtles: the bot's rules against the backtest's trade list

The fast engine has no Turtle, so the Turtle branches were checked at the level of decisions. `tests_demo/test_turtle_replay.py` feeds the stored BTCUSDm M1 bars to `turtle.py`'s rules and compares them with `external.py`'s Turtle plan (`run_path`).
- 2023-01-01 – 2026-11-13: every trade matches on its first and last M1 bar, side, legs and prices (System 1: 48 trades, System 2: 33).
- Over the eight years 2018-11-13 – 2026-11-13: 88 and 60 trades, ending at $6,977.48 and $7,814.72 on the unit rule, the final ten's figures to the cent.
- The daily levels and the M15 vote equal the backtest's on every bar checked.

### Tests on the branches

`tests_demo/` on each branch uses a fake MetaTrader5. Gold and BTC 8 have 69 tests; BTC 6 and 7 have 105. All pass on the final commits. They cover:
- the levers, their arithmetic for both contract sizes, the pause and the add;
- the magic isolation, the virtual balance and restarts with and without the state file;
- the Turtle's rules and its app loop.

## What the checks do not cover

- **Polls.** Parity holds on a fixed 1 s poll grid in a simulated terminal. On the demo account the loop's timing, the feed, requotes and slippage differ. The backtest's eight-timing spread is a guide to how much that matters (gold Top 3, last year: $3,708 – $4,674).
- **No broker-side stop or target, as in the backtest.** The bot checks its stop and target each second. If the bot or the terminal is down, an open position is unprotected.
- **Turtle fills.** Turtle orders are market orders when the price crosses the level. The backtest filled at the level or at the M1 open.
- **Swap.** If the demo account charges swap, it enters the realised P/L, which decides whether a basket "lost" for the pause, and the virtual balance. The backtest had no swap.
- **Lost state file.** If the state file is lost, a rebuilt Top 1 basket starts with its add disarmed, so the add can come later than the backtest's.
- **Server clock.** The Turtle takes the terminal's D1 bars as UTC days (Exness server time), as the backtest does. This is not checked at runtime.

## Files

- `backtesting/engine/demo_parity.py` and `reference.py`: the replay, and the extended simulated terminal.
- `tests/test_demo_parity.py`: 27 tests of the new terminal features and the design mapping.
- On each demo branch:
  - `README.md`: what it runs, how to start it, how it is kept apart;
  - `constants.py`: the design block at the end;
  - `tests_demo/`;
  - `turtle.py` (BTC 6 and 7).
