# Safety limits of the live accounts: the final values

These are the limits each live branch carries in `constants.py` (`SAFETY_DROP_PCT`, `SAFETY_DAY_PCT`,
`SAFETY_STREAK_N`). `SAFETY_CALIBRATION.md` in this folder is the first calculation; this page says what was changed
after it and why.

## The limits

| Accounts | Gold bot + BTC bot | Block both bots when the balance is this far below its high | or when one day loses | Block one bot after this many losing trades in a row (gold / BTC) |
|---|---|---|---|---|
| 1 | Top 2 + Top 2 | 20% | 10% | 10 / 9 |
| 2, 3 | Top 2 + Turtle | 20% | 12.5% | 10 / 5 |
| 4 | V3-lite + Top 2 | 30% | 12.5% | 6 / 9 |
| 5, 6, 7 | V3-lite + Turtle | 25% | 15% | 6 / 5 |
| 8, 9, 10 | Top 1 + Top 2 | 35% | 20% | 9 / 9 |

On a $1,500 account, account 1 blocks at $1,200 (20% below a high of $1,500) or after losing $150 in one day.

## How often they would have blocked

Replay of the recorded backtest trades on fresh $1,500 accounts, each bot sized from half the balance, a block lifted
after 24 hours. "Recent" is the 24 accounts started from December 2023; "all" is all 84 accounts since December 2018.

| Accounts | Blocks per account per year: recent / all | Average end balance against no safety: recent / all | Deepest fall of the worst account: with / without the safety |
|---|---|---|---|
| 1 | 0.00 / 0.57 | $0 / +$1 | 30.0% / 30.7% |
| 2, 3 | 0.08 / 0.83 | -$3 / $0 | 31.0% / 31.0% |
| 4 | 0.12 / 0.18 | -$9 / -$2 | 24.0% / 24.0% |
| 5, 6, 7 | 0.38 / 0.45 | +$2 / $0 | 30.5% / 29.6% |
| 8, 9, 10 | 0.04 / 0.20 | -$20 / -$4 | 45.1% / 45.1% |

- **The safety costs little and, on this history, saves nothing.** The bots in the backtest never stopped working, so
  every block was a false alarm. The safety is there for a bot that does stop working, which a backtest of working
  bots cannot show.
- **One trade can lose more than any limit.** On 3 February 2026 gold V3-lite and gold Top 1 each lost about $400 at
  0.01 lot in a single trade: 26% and 28% of a $1,500 account. The safety only stops the next trade.

## What was changed after the first calculation, and why

The first rule was: the tightest limit that would have blocked at most once in two account-years. It was measured
mostly on 2019 to 2024, when a typical losing gold trade was $5 to $22 at 0.01 lot. In 2026 it is $38 to $75.
On an account opened today those first limits would have blocked 4 to 10 times in the last 12 months of ordinary,
profitable trading. An independent check therefore widened them:

| Accounts | First calculation (drop / day) | Final (drop / day) |
|---|---|---|
| 1 | 15% / 7.5% | 20% / 10% |
| 2, 3 | 20% / 10% | 20% / 12.5% |
| 4 | 15% / 7.5% | 30% / 12.5% |
| 5, 6, 7 | 20% / 12.5% | 25% / 15% |
| 8, 9, 10 | 25% / 15% | 35% / 20% |

The losing-trades limits are the first calculation's, except BTC Top 2: 9 instead of 8. Eight BTC Top 2 losses in a
row happened three times in eight years and lost only $25 to $87 in total, too little to block a bot for.

## Rules the numbers assume

- Only closed trades count: the rules read the booked balance.
- An Unblock after an account block starts all counting again from the current balance, for both bots. An Unblock
  after a losing-trades block sets only that bot's count back to 0.
- Deposits and withdrawals do not move the percentages.
- The Turtle's step-up stays at $2,500. With two bots sharing $1,500 a step of $1,750 behaves the same until the
  account passes $3,500; over eight years it earned about 10% to 17% more, with a deepest fall of 20% instead of 15%
  on the V3-lite + Turtle accounts.

## To reproduce

`python3 -m backtesting.research.live_safety` rebuilds the first calculation. The final values are replayed with
`live_safety.Pair(key, trades, accounts).run(x, y, (n_gold, n_btc), 24.0)` and `live_safety.effect_row(...)`.
