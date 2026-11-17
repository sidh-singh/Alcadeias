# Silver (XAGUSDm, Exness): which strategies work, and at what size

## The answer

**No strategy we tested works on silver after costs at a survivable size. We recommend not running a silver bot; its
slot is better used on gold or BTC.** (This is the wording PREREG_SILVER.md §8 sets for this outcome.)

**Cost caveat (added after the review).** "After costs" means at the spreads of 2018 – 22, the development period.
Silver's spread as a share of its price has fallen about five times since 2024. The review re-checked the verdict at
roughly today's cost ratio: a few short-term rules come near break-even there, but none shows a robust edge, so the
answer stands. It is still a verdict about these 144 rules at those costs, not a proof that nothing could ever work.

- **Which strategies:** none. All 144 pre-registered variants failed the development tests (2018-11-01 → 2022-12-31).
  They cover trend, breakouts, intraday momentum, mean-reversion controls, gold-led and gold/silver ratio rules, calendar
  controls, and the bot's six basket designs. None reached validation, so there are **no finalists**.
- **At what size:** there is nothing to size. By §5.2 no sizing was chosen, because sizing a rule that has no edge only
  changes how fast it loses.
- **Expected profit per week:** none can be claimed. The best near miss, C12 Supertrend H4 (10, 4.0), made **$2.75 a
  week per 0.01 lot** in development. Buy-and-hold one 0.01 lot made **$2.20 a week** over the same weeks. C12's
  neighbouring setting lost money, so its result is a fit to the data, not an edge.
- **Worst drop:** not measured on the hold-out, because nothing qualified to be tested there. In development, the
  near misses fell $400–550 per 0.01 lot. The bot's own designs fell far more (table 2). For example, the Live logic
  fell **$120,000 per 0.01 lot**, so a $2,000 account would have been wiped many times over.
- **The exam was not run, as the pre-registration prescribes.** The hold-out (2024-07-01 → 2026-11-13) was never
  loaded. It stays a clean test for one future pre-registered idea.
- **What the live bot would need:** nothing, since there is no winner to trade. Any future silver bot would also need
  its own branch, a `symbols.json` silver trading window and its own MT5 terminal (§10). A Turtle on silver would also
  need `TURTLE_TICK` = 0.001 and the Sunday-stub merge in `turtle.py`.

## The exam step: what was checked

| Check | Result |
|---|---|
| `PREREG_SILVER.md` sha256 vs `.sha256` | match: `d11df94d72e3082998f52e20a8662834fc6a357a74ba333b42c517e9aba16855` |
| `FINALISTS.md` sha256 vs `.sha256` | match: `0e321a234630222d950d20cfd74ee407a8178aea5f059990145a2a7b9c111931` |
| Finalists named in `FINALISTS.md` | **0** |
| `backtesting/research/silver.py` sha256 vs the value frozen in FINALISTS.md | match: `808a03b7…201e` |
| Loader asked for the exam cut, 2026-11-13 | **refused**: `hold_out_allowed() = False`, `CutError` raised |
| Hold-out runs, §6 sizing, 2026-04-21-type event, cost ×1.5 / swap, §7 portfolio, §8 tests | **not run**: each one is defined per finalist, and there are none |

## The evidence (development, 2018-11-01 → 2023-01-01, 219 weeks, per 0.01 lot)

### 1. By family: what costs took

"Gross" means no spread and no slippage. "×1.0" is the real Exness spread plus one extra spread of slippage per stop fill.
"×1.5" is the stress case.

| Family | Variants | Profit > 0 after costs (×1.0) | Sum gross | Sum ×1.0 | Sum ×1.5 | Costs took (gross − ×1.0) |
|---|---|---|---|---|---|---|
| Trend (D1, monthly, H4) | 55 | 21 | +$4,100 | −$4,089 | −$8,101 | $8,189 |
| Intraday | 34 | **0** | +$8,211 | −$108,747 | −$164,566 | $116,958 |
| Mean-reversion (controls) | 13 | 2 | −$635 | −$11,761 | −$17,324 | $11,126 |
| Gold-led / ratio | 18 | 4 | +$414 | −$19,207 | −$29,244 | $19,621 |
| Season (controls) | 6 | 1 | −$18 | −$4,428 | −$6,634 | $4,410 |
| Bot basket designs | 18 | **0** | −$19,658 | −$425,161 | −$600,312 | $405,503 |

- **Costs decide silver.** 55 variants hold a position for less than a day on average. 44 of them make money gross,
  and **none** makes money after costs.
- One round trip costs $2–4 per 0.01 lot. The median development spread is $0.038, about 0.2% of the price.

### 2. The bot's own designs on silver (development)

| Design | Gross | After costs ×1.0 | ×1.5 | Max drop | Trades |
|---|---|---|---|---|---|
| C35 Live logic (Fibonacci ladder, M15 force-close), $10 target | −$6,318 | −$120,403 | −$168,769 | $120,440 | 8,326 |
| C36 slot-5 variant (flat ladder, H4 force-close), $10 target | +$811 | −$11,280 | −$15,565 | $11,418 | 1,853 |
| C36 slot-5 variant, $20 target | +$1,692 | −$8,906 | −$13,450 | $9,137 | 1,362 |
| C03 Turtle S1 + votes, 4 pyramids (the demo BTC design) | +$1,212 | +$618 | +$129 | **$2,344** | 34 |
| C03 Turtle S1, 1 unit, with votes | +$472 | +$301 | +$199 | $555 | 32 |

- The slot-5 variant you just deployed on gold and BTC is gross-positive on silver, but costs make it a large loser there.
  This says nothing about gold or BTC, where it is still untested.
- The demo Turtle design made money on one unit, but it fails the shortlist on consistency and on profit per unit of
  drawdown (the review: 47% of quarters positive, profit/DD 0.26). (An earlier version of this line said its drop would
  have wiped a $2,000 account at a fixed 0.01 lot; the review found that claim was not correct.)

### 3. The closest misses (for information only; none is a finalist)

| Variant | Gross | ×1.0 | ×1.5 | Max drop | Profit/drop | $/week | Trades | Failed |
|---|---|---|---|---|---|---|---|---|
| C12 Supertrend H4 (10, 4.0) | +$821 | +$597 | +$485 | $546 | 1.09 | 2.75 | 105 | D5: its neighbour (10, 3.0) lost $239 |
| C01 6-month momentum, long only | +$491 | +$474 | +$465 | $409 | 1.16 | 2.18 | 5 | D1: 5 trades, 12 needed |
| C32 long in December [control, M] | +$412 | +$388 | +$375 | $121 | 3.20 | 1.78 | 4 | D1: 4 trades |
| C30 gold/silver ratio + trend | +$221 | +$160 | +$130 | $176 | 0.91 | 0.74 | 19 | D3, D4, D5 |
| C08 Faber 10-month SMA | +$352 | +$325 | +$312 | $409 | 0.80 | 1.50 | 5 | D1, D4 |
| Buy-and-hold (reference) | | +$482 | | $619 | 0.78 | 2.20 | 1 | |

- The near misses earn about what holding silver earned, with similar drops.
- Failures by rule, out of 144 variants: D1 trades 27, D2 profit 118, D3 quarters 120, D4 profit/drop 141,
  D5 robustness 125, D6 survival 46.

### 4. Could the best result be luck? Yes.

- **Expected best from noise:** the best annualised weekly Sharpe that 144 random rules would show over 219 weeks
  is **1.30**.
- **Best observed:** the best development Sharpe was **1.26**, from C32 December, a control with 4 trades. The next
  best was 0.46.
- **Deflated Sharpe ratio:** 0.00 for every variant under the pre-registered definition, and at most 0.44 against a
  pure-noise null.
- **Hansen's SPA test:** **p = 0.29**. The best rule cannot be told apart from luck.

## Caveats

- **One market, one regime per split.** Development is 4.2 years of one market. Slow rules make a handful of trades in
  it, so "no edge found" is also weak evidence: an edge may exist that this sample cannot show.
- **Contamination.**
  - The six demo designs' silver results for 2024-05 → 2026-11 were already seen, including the wipe on 2026-04-21.
  - Silver's 2025–26 rally is public knowledge.
  - Both reasons mean the hold-out would have flattered any long-biased rule. Its clean value is now spent only if
    someone chooses to spend it.
- **Costs fall later.** The dollar spread stayed near $0.03–0.05 while the price rose about 4×. Spread as a share of
  price is about 5× smaller after 2024. Fast rules that fail on 2018–22 costs might look better now without any real
  edge. The pre-registration's H5 test (a constant 0.21% spread) existed to catch this, but it was never reached.
- **Multiple testing.** 144 variants were run, and the haircut above is why the near misses are not promoted.
- **Model limits.** There are no raw silver ticks, so the per-second replay is the finest model. Stop fills in fast
  markets may be worse than one extra spread. Swap is assumed zero: Exness silver is swap-free by default.

## What the owner can do next

1. **Recommended: do not run a silver bot.** Keep the slot on gold or BTC.
2. **If you still want silver,** there are two honest routes. Both need your explicit decision.
   - (a) Spend the hold-out once on one near miss (C12 or C01). This is logged as a deviation. A pass would still be
     weak evidence, and the rally flatters long rules.
   - (b) Pre-register one new idea and test it forward on the demo account, on data after 2026-11-13.
3. **Nothing in this study touches the live bots.** No existing module was edited, and nothing was committed.

## Files

`PREREG_SILVER.md`, `DEVIATIONS_SILVER.md` (entries 1–25), `DEVELOP.md`, `SHORTLIST.md`, `FINALISTS.md` (each with its
`.sha256`), `dev_results.csv` (1,728 rows), `dev/shortlist_table.csv`, `dev/streams/`, `dev/ticks/`, `logs/`.
`val_results.csv` holds only its header, and there is no `exam/` or `portfolio/` folder, because nothing qualified.
