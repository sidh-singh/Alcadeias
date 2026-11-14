# Improving the strategy (hedging variant) — what was tested and what it did

Everything here is backtest-only: the live files (`app.py`, `strategy.py`, …) are untouched. The
designs below are switched on through backtester settings, so the default run is still the live bot.
The log of every logic change, adopted or rejected, is in `LOGIC_CHANGELOG.md`.

## Round 2 (15 Nov 2026): what holds up on data it was never fitted to

**Recommended for gold: V3-lite** — H1 trend filter · entry votes on H1, M15 must agree · target 8 and
stop 8 volatility units on the whole basket · no DCA ladder · 12 h pause after a losing basket · M15
force-close off. (A volatility unit is the average size of one H1 bar's move over the last day, read when
the basket opens.)

**BTC:** no design tested makes money reliably. Every improved design is close to break-even on BTC, with
small drawdowns; the live settings lose heavily. Trading BTC with V3-lite stops the losses; whether to
trade BTC with this strategy at all is a fair question.

Real $2,000 account per quarter, the bot's unit rule, every tick replayed, each quarter run under eight
random loop timings. Designs were chosen on DEV and CONFIRM together and frozen before 2023 was run once.

| Gold, average per quarter (runs that lost money) | DEV Aug 2025 – Nov 2026 | CONFIRM Jan 2024 – Jun 2025 | **FINAL Feb – Dec 2023 (untouched; three quarters and one two-month block)** |
|---|---|---|---|
| Live settings | −$1,480 (37 of 40, 27 wiped) | −$675 (47 of 48) | **−$666** (24 of 32) |
| V2 ($20 / $20, H1 trend, no ladder) | +$251 (7 of 40) | +$71 (16 of 48) | **+$30** (16 of 32) |
| V3 (live votes + one MACD-turn add) | +$453 (8 of 40) | +$180 (12 of 48) | **+$58** (17 of 32) |
| V3 without the add | +$133 (8 of 40) | +$78 (16 of 48) | **+$5** (13 of 32) |
| **V3-lite** | +$404 (8 of 40) | +$152 (**0 of 48**) | **+$106 (0 of 32)** |

| BTC, average per quarter (runs that lost money) | DEV | CONFIRM | **FINAL 2023** |
|---|---|---|---|
| Live settings | −$585 (30 of 40) | −$1,995 (48 of 48, 46 wiped) | **−$1,194** (32 of 32, 3 wiped) |
| V2 | +$159 (7 of 40) | −$7 (24 of 48) | **−$17** (24 of 32) |
| V3 | +$109 (8 of 40) | +$34 (26 of 48) | **−$18** (16 of 32) |
| V3 without the add | +$100 (14 of 40) | +$60 (24 of 48) | **+$3** (12 of 32) |
| **V3-lite** | +$114 (8 of 40) | +$48 (24 of 48) | **+$7** (16 of 32) |

Worst drawdown of any V3-lite run: gold 45% on DEV, 10% on CONFIRM, 6% in 2023; BTC 9%, 13%, 4%.

**What each idea came to** (details: `backtest_results/improve/`):

| Idea | Verdict |
|---|---|
| H1 trend filter | the change that matters most; an H4 trend does not hold up outside 2025-26 |
| Stop and target on the whole basket, in volatility units | removes the wipe-outs; 8 / 8 units was the best size in the ladder grid on both symbols and inside the V3-lite entry frame (across all no-ladder gold designs 6 / 6 averaged a little more) |
| DCA ladder | the live ladder (Fibonacci at RSI 35 / 65) is what empties the account. A bounded ladder (one equal add, released by a MACD turn, at least 1 unit away) earned more than its no-add twin on gold in every period (+$321, +$102, +$53 a quarter more, against a twin making +$133, +$78, +$5) and less on BTC in two of the three periods (+$9, −$27, −$21), and it makes the worst basket larger. Not recommended as the default |
| Other recovery mechanisms | 42 mechanisms on the same 32,553 entries (`recovery_mechanisms.md`): none raises the expectancy; they only trade many small losses for a few large ones or the reverse. A ladder with equal lots, at most two adds and a hard $60 budget, closed before every market closure, never lost more than $60 (held through closures, a gap took one gold basket to −$222); it earned no more than not adding. A hedge lock unlocked on the next signal pays exactly what closing and re-entering pays; closing both legs together later costs one spread more than a plain stop. Zone recovery and martingale lose the most |
| Support / resistance (H1, H4, D1 swings, previous day / week, round numbers) | two independent studies (`sr_study.md`, `sr_trades.md`): price does not hold at these levels more often than at random prices, and every bounce rule loses after the spread in both periods, doing worse than the same rule at placebo levels. Three gold retest / breakout rules that trade with the trend were slightly positive in both periods (+$1 to +$93 a quarter per 0.01 lot), but they were picked after both periods had been seen, the one rule named in advance (a BTC breakout) failed, and in 2025-26 the same rules at placebo levels did as well: leads, not an edge |
| MACD or RSI cross-back instead of an RSI level for the ladder | the RSI cross-back beat the live RSI-level trigger on both symbols, the MACD turn only on gold; no ladder trigger beat no ladder on average |
| Trailing exit, longer pause after any close, time stop | no gain on average over 500 designs (optimiser, `backtesting/OPTIMISER.md`) |
| Spread cap on entries | no effect |

**How far to trust this.** More than 1,200 strategy designs were tried in all (plus several hundred support /
resistance and recovery variants), so the best of them are flattered; the
2023 run is the honest number, and for gold it is about a quarter of the DEV figure. The edge per trade is
small (gold about +$4 a basket in 2023). Gold rose through most of 2023-2026, which suits a with-trend rule.
The next step is a demo account, not more searching.

**Settings** (backtester, `python -m backtesting run --set ...`): `trend_tf=H1`, `open_weights={"H1": 1}`,
`entry_agree_s=2`, `max_adds=0`, `force_close_enabled=false`, `vol_tf=H1`, `vol_len=24`, `target_vol=8`,
`stop_vol=8`, `target_usd_per_unit=null`, `stop_loss_usd_per_unit=null`, `loss_cooldown_s=43200`.
The volatility unit has no dollar ceiling in these runs; in wild markets (gold early 2026: about $15 a unit)
a basket risks about $120 per 0.01 lot. `vol_cap_usd_per_unit` caps it; that cap has not been through the 2023 test.

---

## Round 1 (14 Nov 2026): V2

### The short version

One redesign beats the live settings on both symbols, in all five quarters tested, without a single stop-out:

**V2 = trade only with the H1 trend · no DCA ladder · target $20 and stop $20 per 0.01 lot · M15 force-close off · 4 h pause after a losing basket.**

Real $2,000 account, the bot's own unit rule, every tick replayed, each quarter run eight times with
random loop timing (40 quarter-runs per row):

| | Live settings, gold | **V2, gold** | Live settings, BTC | **V2, BTC** |
|---|---|---|---|---|
| Average result per quarter | −$1,480 | **+$251** | −$585 | **+$159** |
| Quarter-runs that lost money | 37 of 40 | **7 of 40** | 30 of 40 | **7 of 40** |
| Quarter-runs stopped out (account wiped) | 27 of 40 | **0** | 0 | **0** |
| Max drawdown, median / worst run | 100% / 102% | **9% / 13%** | 27% / 95% | **6% / 9%** |
| Worst single basket | −$1,944 | **−$34** | −$811 | **−$22** |
| Worst quarter-run | −$2,000 | **−$74** | −$1,822 | **−$64** |
| Baskets per quarter | 2,427 | 116 | 2,615 | 46 |

This is a large improvement in what the backtest measures. It is **not proof of a profitable system**:
see "How far to trust this" below before risking money on it.

### What the evidence says, step by step

**1. No classic entry idea predicts direction here** (`backtest_results/improve/edge_screen_*.txt`).
Twenty signals were measured on every closed M15 bar of the fifteen months: the bot's own RSI / MACD
votes, RSI extremes on M15 / H1 / H4, RSI divergence (plain, with the trend, at the day's high / low),
bounce off and breakout of the one-day high / low, momentum, time of day. None reaches statistical
significance on either symbol. On gold, most *fading* signals lose in four or five quarters out of five
(buying an oversold H1 RSI and selling an overbought one: negative in all five), and the bot's entries
**against** the H4 trend lose about $1.44 per 0.01 lot over the next four hours while its entries
**with** the trend are flat. Divergence and support / resistance did not add an edge, so they were not built.

**2. What loses the money is structure, not the indicator settings.** With entries that are a coin
flip, each basket costs the spread; the ladder then puts 26 of 32 units in at one price within seconds
and nothing stops a loss. So the search (`backtest_results/improve/stage1_*.csv`, `stage1b_*.csv`:
191 designs × 5 quarters, one fixed 0.01-lot unit) varied the structure:

| Lever | Gold, average per quarter (0.01 lot) | BTC |
|---|---|---|
| No trend filter → with H4 trend → with H1 trend | −$423 → −$25 → **+$6** | −$15 → +$12 → +$12 |
| Exit: $1 target (live) → $10 target, $20 stop, force-close off | −$280 → **−$55** | −$74 → **+$83** |
| With the trend filter, no ladder, force-close off: target / stop $5/$10 → $20/$20 | +$53 → **+$265** | +$10 → **+$91** |
| Pause after a loss: live 5 min → 1 h | −$208 → −$87 | no change |
| Spread cap on entries (twice the usual spread) | no effect | no effect |

Designs were chosen on the three 2026 quarters only; the two earlier hold-out quarters then agreed
(rank correlation between the two periods +0.61 on gold, +0.23 on BTC), and V2 is positive in both of them on both symbols.

**3. The short list on raw ticks** (`backtest_results/improve/validate_*.csv`; median net P/L per quarter, USD, real $2,000):

| Gold | Aug–Nov 25 | Nov 25–Feb 26 | Feb–May 26 | May–Aug 26 | Aug–Nov 26 | Avg / quarter | Lost | Max DD med / worst |
|---|---|---|---|---|---|---|---|---|
| Live settings | −2,000 | −1,277 | −2,000 | −2,000 | −351 | −1,480 | 37/40 | 100% / 102% |
| Live + H4 trend filter only | +1,052 | +205 | −722 | −73 | −111 | −49 | 22/40 | 36% / 105% |
| No ladder, $10/$10, no trend filter | −174 | −1,338 | −178 | −929 | +60 | −504 | 31/40 | 25% / 81% |
| H1 trend, no ladder, $10/$20, 1 h pause | +324 | +300 | −73 | −140 | +281 | +133 | 16/40 | 10% / 19% |
| **V2: H1 trend, no ladder, $20/$20, 4 h pause** | +266 | +367 | +237 | −30 | +386 | **+251** | 7/40 | 9% / 13% |
| H1 trend, no ladder, $20/$40, 4 h pause | +311 | +327 | +358 | +276 | +9 | +265 | 2/40 | 12% / 14% |
| H4 trend, no ladder, $20/$20, 4 h pause | +850 | +177 | +498 | −23 | +62 | +307 | 6/40 | 11% / 15% |

| BTC | Aug–Nov 25 | Nov 25–Feb 26 | Feb–May 26 | May–Aug 26 | Aug–Nov 26 | Avg / quarter | Lost | Max DD med / worst |
|---|---|---|---|---|---|---|---|---|
| Live settings | −1,369 | −1,407 | −286 | −190 | +282 | −585 | 30/40 | 27% / 95% |
| Live + H4 trend filter only | −402 | −60 | −20 | −28 | +193 | −83 | 29/40 | 10% / 42% |
| No ladder, $10/$10, no trend filter | +150 | −81 | +238 | +143 | +255 | +138 | 8/40 | 5% / 14% |
| H1 trend, no ladder, $10/$20, 1 h pause | +243 | +163 | −8 | −101 | +107 | +80 | 16/40 | 5% / 11% |
| **V2: H1 trend, no ladder, $20/$20, 4 h pause** | +419 | +310 | −26 | +89 | +12 | **+159** | 7/40 | 6% / 9% |
| H1 trend, no ladder, $20/$40, 4 h pause | +249 | +292 | +110 | +157 | −160 | +129 | 8/40 | 6% / 10% |
| H4 trend, no ladder, $20/$20, 4 h pause | +122 | +141 | −34 | +113 | −48 | +59 | 16/40 | 9% / 12% |

Two things stand out. The trend filter is what gold needs (a no-ladder $10 / $10 design without it
still loses $504 a quarter). And removing the ladder with a real stop is what ends the wipe-outs on both.

### What V2 is, exactly

| Rule | Live | V2 | Backtester setting |
|---|---|---|---|
| Entry direction | RSI / MACD pivot votes on H1 + M15 | the same votes, but only **with the H1 trend** (sign of the H1 MACD signal line on the last closed bar) | `trend_tf=H1` |
| DCA ladder | 5 adds, ×2, 3, 5, 8, 13, at RSI 35 / 65 | **none** | `max_adds=0` |
| Profit exit | +$1 per unit | **+$20 per unit** (gold: a $20 move; BTC: a $2,000 move) | `target_usd_per_unit=20` |
| Loss exit | M15 slope score turns | **−$20 per unit**, nothing else | `stop_loss_usd_per_unit=20`, `force_close_enabled=false` |
| After a losing basket | 5 min cooldown | **4 h** (5 min after a winner) | `loss_cooldown_s=14400` |

```
python -m backtesting run --symbol XAUUSDm --start 2026-08-13 --end 2026-11-13 --mode ticks \
  --set trend_tf=H1 --set max_adds=0 --set target_usd_per_unit=20 --set stop_loss_usd_per_unit=20 \
  --set force_close_enabled=false --set loss_cooldown_s=14400
python -m backtesting.research.improve report XAUUSDm      # every table above, from the stored files
python -m backtesting.research.improve validate XAUUSDm    # recompute the raw-tick validation (about 6 min)
```

### How far to trust this

- **191 designs were tried and the best are shown.** That flatters them. What speaks for the result:
  they were chosen on three quarters and held up on two unseen ones; whole families of settings are
  positive on average, not one lucky row; and the reason is visible in an independent measurement
  (fading against the higher-timeframe trend is the losing half of the bot's entries).
- **The edge per trade is small and not statistically proven.** Gold: about +$2 per basket on $20
  of risk, 116 baskets a quarter; BTC about +$3.50 on 46. Seven of forty quarter-runs still lose, and
  with other loop timing the same quarter can come out lower.
- **Fifteen months, one regime.** Gold trended strongly in this period, which suits a with-trend rule.
  The weakest quarter for V2 on gold (May–Aug 2026, about −$30) is the range-bound one.
- **The stop is simulated once a second on the real bid / ask**; a gap through it is in the result
  (worst gold basket −$34 on a $20 stop). Live, it should also sit at the broker as a real stop-loss.
- **The unit still steps up with the balance** in these runs (the live rule). Keeping it at 1 until V2
  has run on a demo account for a quarter is the safer choice.

### What has not been done yet

- Nothing was changed in the live bot. Moving V2 into `strategy.py` / `app.py` (trend gate, stop and
  target, no ladder, loss pause) is a separate step; the backtester can then be parity-checked against it.
- The netting variant (slope "book" exit) has not been searched yet; the trend filter and the loss
  pause apply to it unchanged.
- A demo-account forward test is the only real confirmation.
