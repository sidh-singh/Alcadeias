# The comparison page: every backtest on the bot's $2,000 account, side by side

`index.html` is one self-contained page (Plotly, the data and the code are inline; it makes no request) that puts the
equity curves, profit, max drawdown and the other figures of every comparable backtest of this repository next to each
other, per symbol (gold XAUUSDm, BTC BTCUSDm). The owner asked for it on 28 Nov 2026: "In final results set create html
page with equity graphs of all backtesting results so that i can compare and get Profit and max DD and all other things
which you already do."

The page reads only the files in `data/`, which follow the contract below. The code is
`backtesting/research/compare_page.py`; its tests are `tests/test_compare_page.py`.

## Rebuilding

```
python3 -B -m backtesting.research.compare_page export     # data/ from the studies' own result files (seconds)
python3 -B -m backtesting.research.compare_page compute    # study 1 + buy-and-hold on 5y and 1y (about 2 minutes, 1.5 GB)
python3 -B -m backtesting.research.compare_page check      # validate every contract file
python3 -B -m backtesting.research.compare_page build      # index.html
python3 -B -m backtesting.research.compare_page all        # the four above
```

`build` also lists, per source and symbol, the common windows it has no rows on.

**Later, once study 2's exam is written.** Gold 2017-2018 is study 2's sealed Early window, and the workflow computes
nothing on any bar before 2019-01-01 until then. Study 1 and buy-and-hold on the 8y and new windows (both start
2018-11-13) therefore wait for:

```
python3 -B -m backtesting.research.compare_page compute --windows 8y,new --allow-pre-2019
python3 -B -m backtesting.research.compare_page build
```

`--allow-pre-2019` refuses to run until `backtest_results/tradeiq_2027/EXAM.md` exists. The run loads study 1's market
from its own data start (`tradeiq_market.load`: gold 2017-01, BTC 2018-01) and merges the new rows into the files. Until
then the page shows those two windows of study 1 and of buy-and-hold as "pending".

**Studies 2 and 3.** `tradeiq_2027` and `bot_filters` write their own `<sid>__series.csv`, `<sid>__metrics.csv` and
`<sid>__curves_<window>.csv.gz` into `data/` (or the lead copies them there). Then run `check` and `build`. The page shows
each of them as "pending" until its series file exists, and picks it up without any code change. A source the page does
not know is drawn in the "earlier studies" colour.
- The page compares studies on the common windows (5y first). Study 2's pre-registration scores study 1's windows
  (dev, val, holdout, full, early): to appear on 5y and 1y next to the bots, it has to export its finalists and bases
  as $2,000 accounts on those windows too (and on 8y / new after its exam), computed with its frozen code. Until then
  `build` reports the missing windows, and the page says "no rows on 5y" for it.

## The contract (v2)

One set of files per source `<sid>`. The series ids are `"<sid>:<native id>"` and unique across all sources. Version 2
adds optional columns after the v1 ones; a v1 file (without them) is still valid.

**`<sid>__series.csv`**, one row per series:
`series_id, source, study, symbol, label, kind, family, tf, filter, role, eligible, exam, notes` [`, sizing, tags`]
- `symbol`: XAUUSDm or BTCUSDm. `kind`: bot, bot+filter, rule or benchmark.
- `role`: design (a design the live bots run), base, finalist, champion, qualified, variant or benchmark.
- `eligible`: 1 or 0 (the study's own eligibility or qualification rule). `exam`: pass, fail, or empty when not examined.
- `sizing` (optional): empty or `unit rule` (FINAL10's unit rule), `risk-sized` (1% risk or vol-targeted, as a
  strategy's source prescribes), `fully invested` or `0.01 lot fixed` (the two buy-and-hold lines).
- `tags` (optional): short badges the page shows on the row, `;`-separated (for example "reference, not a candidate").

**`<sid>__metrics.csv`**, one row per (series_id, window, cost, basis):
`series_id, window, start, end, cost, basis, start_usd, final_usd, net_usd, return_pct, cagr_pct, max_dd_usd,
max_dd_pct, p_dd, trades, win_rate_pct, profit_factor, sharpe_w, pos_quarters_pct, worst_quarter_usd, wiped, dd_marks,
score_final10, source_file` [`, sample, derived, row_notes`]
- `start`, `end`: ISO dates, UTC, end exclusive. `cost`: 1.0 (the broker's spread) or 1.5 (every spread x1.5).
- `basis`: `account` = a $2,000 account (`start_usd` 2000) with FINAL10's sizing (units = floor(balance / 2,500) + 1,
  at most 10, times 0.01 lot) unless the series' `sizing` says otherwise. `unit` = always 0.01 lot (`start_usd` 0,
  `return_pct` and `max_dd_pct` empty).
- `max_dd_pct`: % below the running peak, on the marks named by `dd_marks` (tick, second, M1, hour or day).
- `max_dd_usd`: the max DD in $ **on the same marks as `max_dd_pct`**, or empty. A drawdown read off a coarser curve is
  never put here. `check` enforces max_dd_usd >= max_dd_pct x $2,000 on account rows (the peak is never below the
  start). `p_dd` = `net_usd / max_dd_usd`.
- `score_final10`: FINAL10's selection yardstick, empty unless computed.
- `source_file`: the repository file, or the command, the numbers come from.
- `sample` (optional): `in`, `out` or `mixed`: was the window part of the data that chose this row? Empty when not
  stated (buy-and-hold, Balke's published settings, the ladder).
- `derived` (optional): the fields compare_page computed rather than read from the study's files, comma-separated
  (return_pct, cagr_pct, max_dd_usd, p_dd, profit_factor, sharpe_w, pos_quarters_pct, worst_quarter_usd). The page draws
  them with a dotted underline.
- `row_notes` (optional): caveats of this row (FINAL10's 1y medians, study 1's rebuilds, multisymbol's own figures).

**`<sid>__curves_<window>.csv.gz`**: `series_id, date, equity_usd`, account basis at cost 1.0.
- `equity_usd` is the account's equity at the end of that UTC day (its last mark, open positions marked).
- The first row is dated the day before the window starts and holds the $2,000 the account starts with.
- The last row is the final equity. A wiped account's curve stops on the day it was wiped.
- In the file name, characters other than letters, digits, `.` and `-` become `_` (balke's window "since 2020" is
  `balke__curves_since_2020.csv.gz`).

**Windows.** One window key means one span per symbol across all sources (`check` warns otherwise).
- The common windows are final10's: `5y` 2021-11-13..2026-11-13 (both symbols), `8y` 2018-11-13..2026-11-13, `new`
  2018-11-13..2021-01-01 (FINAL10's only out-of-sample window) and `1y` 2025-11-13..2026-11-13.
- A study's own windows keep their names and real dates, and the page names them after their owner: study 1's `dev`,
  `val`, `devval`, `holdout`, `full` (gold ends 2026-11-26, BTC 2026-11-27); Balke's `since 2020`; multisymbol's `sel`,
  `conf`, `tsel`.
- `bots-full` (2019-01-01..2026-11-13) and `bots-holdout` (2024-07-01..2026-11-13) hold study 1's rebuilds of the bots'
  designs. They end where FINAL10's trades end, so they are not study 1's `full` and `holdout`, which run to the data end.
- Buy-and-hold is computed over exactly every window that starts in 2019 or later.

`check` validates all of this: the exact columns, the vocabularies, the ids, the units, the dates, the $ drawdown bound
and every curve. It reports a warning when a curve does not end at its row's final equity. That happens only on the
1y tick rows of FINAL10 and of study 3's tick designs, whose row is the median of 8 loop timings while the curve is the
middle timing run.

## The sources

| Source (`sid`) | What is in it | Windows | Curves |
|---|---|---|---|
| `final10` | FINAL10's 164 accounts: 41 (symbol, label) series = the ten finalists per symbol, the references, the section 7 supplement and the section 8 warm additions. The five designs the live bots run have role `design`. | 8y, 5y, new, 1y | yes |
| `final10` (other studies' runs of the same designs) | the bots' designs rebuilt by study 1 from final10's 8y trades (`tradeiq_rsi/curves_bots_*`, `curves_summary.csv`); multisymbol's gold and BTC base rows on account (a) | bots-full, bots-holdout; sel, conf, tsel | yes |
| `tradeiq_rsi` | study 1, all 750 variants. Per 0.01 lot from its files: dev, val, devval, holdout and full at x1.0 and x1.5. $2,000 accounts from its files: its 19 curve rows on full and holdout. Computed here with its own code: every variant as an account and per 0.01 lot on 5y and 1y at x1.0. | as listed | full, holdout (19 series), 5y and 1y (750) |
| `benchmarks` | buy-and-hold: the $2,000 fully invested line (computed here) and study 1's 0.01-lot line (from its files on its windows; computed here on the others) | 5y, 1y, dev, val, devval, holdout, full, bots-full, bots-holdout, sel, conf, since 2020 | yes |
| `balke` | René Balke's gold and BTC strategies on the bot's unit rule: Range Breakout, ATR Breakout, Go Long, Turnaround Tuesday | 8y, 5y, new, 1y, since 2020 | yes |
| `ladder` | the ladder study's continuous gold accounts on the unit rule: L0 (the live bot on its kernel), L5, LB and G4 (8y and 5y per second; 1y the median of 8 timings) | 8y, 5y, 1y | none (the study wrote none) |
| `tradeiq_2027`, `bot_filters` | studies 2 and 3 | their own | pending |

How the series are classified:
- **FINAL10's `kind`:** our tick-engine designs and V3-lite variants are `bot`, the V3-lite + filter rows are
  `bot+filter`, and the published strategies (with or without "+ bot votes" / "+ H1 trend") are `rule`.
- **FINAL10's `eligible` and `score_final10`** come from its evidence (`evidence.csv`, or `evidence_warm.csv` for the
  warm rows). The selection files say which row a label stands for. The score is the same in every window of a
  series. References were scored too, but are not candidates: their `eligible` is 0 and their tag says so.
- **FINAL10's tags:** "reference, not a candidate", "§7 supplement, not pre-registered", "§8 warm re-check addition",
  and "not eligible on the warm re-check (§8)" for the two gold finalists that section 8 finds ineligible (V3-lite +
  200-day trend filter and V3-lite + 12-month momentum filter; their notes give the warm score).
- **FINAL10's `sizing`:** the four "(risk-sized)" rows (Turtle 1% risk, London breakout 1% risk, Noise-area momentum
  vol-targeted, TSMOM 12-month vol-targeted) are `risk-sized`: not the unit rule.
- **`sample`:** FINAL10 chose with data from 2021 on (FINAL10.md §3, §5), so `new` is `out`, `5y` and `1y` are `in`,
  `8y` is `mixed`; the same holds for the designs on every other study's window (`bots-holdout`, `sel`, `conf` are
  `in`; `bots-full`, `tsel` are `mixed`). Study 1 chose on 2019 - Jun 2024: `dev`, `val`, `devval` are `in`, `holdout`
  and `1y` (inside its hold-out) are `out`, `full` and `5y` are `mixed`.
- **Study 1's `role`:** `finalist` (its 6 finalists), `champion` (the best variant of each indicator), `base` (the
  finalists' RSI baselines and DEVIATIONS 35's best RSI R1 row), `qualified` and `variant`.
- **Study 1's `exam`** applies PREREG 8's rule to `exam.csv`: net > 0 at x1.0 and P/DD >= 0.5 over the hold-out. Gold
  passes 3 of 3, BTC 1 of 3, as the study reports.

## Definitions

**Buy-and-hold, two lines.**
- **"Buy and hold, $2,000 fully invested (no leverage)"** is the main benchmark. The $2,000 buys 2,000 / ask of the
  asset at the window's first M1 open (a fraction of a lot). The ask is the bid open plus that M1 bar's mean spread.
  The position is held and sold at the bid at the window's last M1 close. Nothing else is traded and there is no
  leverage, so it cannot be wiped. It is marked at every M1 bar: the close for the curve, the low for the drawdown.
  The running peak follows `tradeiq_market._unit_marks`.
- **"Buy and hold 0.01 lot (study 1's reference)"** is study 1's buy-and-hold (DEVIATIONS 6 and 35): 0.01 lot bought and
  sold the same way. On the $2,000 account the unit rule gives 1 unit, fixed at the open, so it never compounds.
- Both are computed by `bh_path` in `compare_page.py`. `tradeiq_checks` shows that it reproduces study 1's buy-and-hold
  on all its windows (net, max DD, entry and exit within 1e-12), and `compute` shows that it matches `tradeiq.bh_run`
  with `tradeiq.account_of` on the windows it accepts.

**The studies' own numbers are kept.** These come from each study's files unchanged: net profit, final equity, max DD
% (on the study's own marks), trades, win rate and profit factor.
- FINAL10's tick engine marks every second (8y, 5y, new) or every raw tick (1y). The bar engines (FINAL10, Balke and
  study 1) mark the worst price of every M1 bar.
- Study 1's rebuilds of the bots' accounts use daily marks.
- FINAL10's 1y tick rows give the median of 8 loop timings for the final equity and the max DD; their other columns,
  their curve and its daily-close drawdown are the middle (upper-median) timing run.

**Max DD $ and the drawdown at daily closes.**
- `max_dd_usd` (the table's "Max DD $") is on the same marks as the max DD %: multisymbol's own, study 1's per 0.01 lot,
  buy-and-hold's (M1), study 1's 5y and 1y accounts (computed here on their M1 marks: `account_dd_usd` runs
  `external._account_kernel`'s logic and also keeps the largest fall in $; `compute` checks on every run that its
  drawdown % and final equity equal `tradeiq.account_of`'s, see `data/tradeiq_rsi__checks.csv`), and study 1's
  daily-marked rebuilds of the bots (from their own daily curve). FINAL10, Balke, the ladder and study 1's own account
  rows publish the drawdown in % only, so it is empty there.
- "DD $, daily closes" is a page-only figure: the largest fall of the daily curve below its running peak, for every
  account with a curve. Daily closes miss the intraday lows: over the 1,782 account rows with a curve it is a median
  7% shallower than the study's own max DD %, and up to 51% (gold V3-lite over 5 years: 21.1% at daily closes against
  its own 30.6%). The page prints the current figures in its notes.
- **Growth ÷ DD** = CAGR % / max DD %, both the study's own (FINAL10's "growth per year ÷ drawdown"). It ranks the
  account basis: the table's default order and the Top 10 button. Per 0.01 lot the table ranks by profit / DD (net /
  max DD $, both per lot).

**Computed here, uniformly from the daily curves, only where a study did not give it** (`curve_stats`; listed in
`derived` and dotted on the page):
- **CAGR:** ((final / 2,000)^(1 / years) - 1) x 100, with years = (end - start) / 365.25 days. Multisymbol and the
  ladder publish none. **Return %** = net / 2,000 (multisymbol, the ladder).
- **Weekly Sharpe:** the weekly P/L in $ (weeks from Saturday 00:00 UTC, the partial first and last weeks included),
  mean / sd x sqrt(52). This is study 1's definition.
- **% positive quarters and the worst quarter in $:** calendar quarters, partial quarters included, as study 1. Study 1's
  per-lot worst quarter comes from its `quarters_dev_val.csv` for dev and val, and from its per-lot daily curve for its
  curve rows on full and holdout. Elsewhere it is empty.
- **Multisymbol** publishes its own % positive quarters (3-month blocks from its window start) and Sharpe (x
  sqrt(52.18)): another definition, so its rows carry the uniform figures in these columns and its own in `row_notes`.
  Its profit factor comes from its own trade files (`trades_direct.csv.gz`, `trades.csv.gz`), the trade count checked
  against its `runs.csv`.
- **Page-only:** the drawdown at daily closes, the worst calendar month and the longest time under water (days from the
  first day below a previous high to the first day back at it). `build` computes them from the contract curves for
  every account row with a curve; they are always dotted.
- A value that `build` fills for a source that left it blank (studies 2 and 3) is listed and dotted the same way.

**Curves.**
- FINAL10 and Balke publish the equity at the first mark of each day with a mark. Here day D carries the next such
  day's opening mark (for gold a Friday carries Sunday evening's first mark, the weekend gap included), and the last
  day carries the final equity.
- Study 1's curves are the equity at each UTC midnight (the close mark of the last M1 bar before it). A midnight is
  the end of the day before it. Days without an M1 bar are dropped.
- Multisymbol's `daily.csv.gz` already holds end-of-day marks for every calendar day (a day without a mark repeats the
  last one). It is kept as it is, with the opening row added.

**Study 1 on 5y and 1y, without any bar before 2019.**
- `compute` builds study 1's `TMarket` from the store's M1 bars starting 2019-01-01 (`market_from`; no earlier month
  file is read). Then it runs study 1's own `Study`, `run`, `account_of` and `curve_metrics`.
- `tradeiq_checks` (results in `data/tradeiq_rsi__checks.csv`) shows this is study 1's own computation:
  - every one of the 375 rules has the same state from 14 Oct 2021 on as a market starting 2019-07-01, so the warm-up
    has converged;
  - every one of the 750 variants re-run over study 1's validation window and hold-out on this market equals
    `results_dev_val.csv` / `results_holdout.csv` exactly (net, max DD and trade count; those were computed with
    history from 2017 / 2018);
  - buy-and-hold matches on all 20 of its rows;
  - the $ drawdown kernel gives `account_of`'s drawdown % and final on all 1,500 account runs (difference 0.0).

## The page

- **Controls.** The top bar (it stays on screen) holds the symbol and the window: 5y first, then 8y, new, 1y, and each
  study's own windows, grouped by the study that owns them. The scatter and table bar (it stays under the first)
  holds the basis (account or per 0.01 lot), the costs (x1.0 or x1.5) and the filters. A basis or cost with no rows in
  the window is disabled and says why; switching to a window without the current combination falls back to one it has.
  Every switch writes the view into the link, which can be shared: `index.html#sym=BTC&w=full&b=unit&c=1.5&y=cagr&log&dark`.
- **The sample line** under the top bar says which studies are in or out of sample in the window (the Sample column),
  then the pending studies and windows, and the present studies without rows on a common window.
- **Equity chart:** the $2,000 accounts at x1.0 (whatever the basis and cost switches show). One y axis in dollars with
  a log-scale toggle, a crosshair with one tooltip for every line, and a legend grouped by study (under the plot on
  narrow screens). A drawdown chart (% below the running peak of the drawn line, at daily closes) sits under it on the
  same x axis, with its own tooltip.
  - The default selection is the bots' designs, buy-and-hold, and at most two finalists per study (FINAL10's by its
    rank, unit-rule rows first, then those that passed their study's sealed exam); "Finalists" draws every one.
  - Quick buttons: Bots, Finalists, Top 10 accounts by growth ÷ DD (the unit-rule $2,000 accounts of the window at x1.0
    with a curve; the risk-sized rows, buy-and-hold, the basis, cost and filters are left out), Clear. Each keeps the
    buy-and-hold lines.
  - Within a study, each drawn line gets its own dash in drawing order (six dashes); past six a marker is added, so no
    two lines of a study look alike. The table shows each drawn row's line key.
- **Risk/return scatter:** max DD (%, or $ per lot) against net profit (or CAGR; per 0.01 lot has no CAGR), one small
  panel per study on shared scales, with the study's sample status in the heading. The panel's series are in its
  colour, every other series in grey, buy-and-hold as a diamond. A wiped account is a cross (they stack at 100%; the
  heading counts them). A point far above the rest is drawn on the top edge as a labelled triangle. A click adds the
  series to the chart.
- **Table:** every series of the view, sortable from the header buttons (numbers as numbers, blanks last), searchable,
  and filterable by study, kind, family, timeframe, role and exam. The Series column stays while the table scrolls
  sideways; it holds the draw checkbox, badges (risk-sized, the tags, wiped) and a "Notes" disclosure with the series'
  notes, the row's notes and its source file. Other columns: Sample, Eligible (where the study has a rule), the source
  folder ("via multisymbol") where a row's numbers are not the study's own folder.
- **Labels are data:** they reach the DOM through `textContent`, and Plotly's names and tooltips as escaped text
  (never inside a template), so a label like "RSI < 30" or one holding "%{" shows as written.
- **Colour follows the entity.** The palette is the dataviz skill's categorical one. Its slots go, in order, to the
  studies present in the build: first those with curves (the line chart's), then those without. In this build: the
  bots' designs blue, FINAL10 orange, study 1 aqua, Balke yellow, the ladder magenta (no curves). Studies 2 and 3 take
  the next slots after study 1 when they arrive (the slots then shift; within one page a colour never changes).

  | Slot | Light | Dark |
  |---|---|---|
  | 1 | `#257de0` | `#338ced` |
  | 2 | `#f47230` | `#e76624` |
  | 3 | `#00b894` | `#00a888` |
  | 4 | `#f2a600` | `#d28e05` |
  | 5 | `#ee7fac` | `#e24d8b` |
  | 6 | `#008a17` | `#0aac23` |
  | 7 | `#6a4ce2` | `#9887ef` |

  The hues side by side are therefore always the palette's first slots in its order. `validate_palette` on the
  displayed list (adjacent pairs, legend order): light, the four line hues: worst CVD ΔE 11.8, normal vision 23.8; with
  the ladder's slot 11.8 / 20.5. Dark: 11.1 / 21.1 for both. `tests/test_compare_page.py` re-checks the adjacent pairs
  of the built page in both modes. Buy-and-hold is drawn in the text colour. Three light hues sit under 3:1 contrast:
  the legend, the end labels (four lines or fewer) and the table view are the relief. The line chart is an
  adjacent-pair form; the scatter avoids all-pairs comparisons by giving each study its own panel (one hue each).
- **Size.** Featured series (designs, finalists, champions, baselines, benchmarks and the small sources) have daily
  curves; the rest are sampled every 7 days. Numbers keep the contract's digits and are rounded once, for display.
  `build` keeps the page under 12 MB: if needed it samples the others every 14, 28 or 56 days, then leaves out
  non-featured curves, and it reports what it did. This build: 7.2 MB. A synthetic full-size study 2 (1,460 variants,
  21,900 rows, account curves on 5 windows each) builds to 11.0 MB with 56-day sampling.

## Left out, and why

- **Balke's own sizings** ("his sizing", $2,000 and $10,000) and his US30m / USTECm rows: another account or symbol.
- **sizing:** other STEP values are another sizing. At STEP $2,500 with the cap it equals FINAL10's 24 accounts.
- **ladder:** the Z1 / Z2 / Z3 designs (G1-G3, G5, B1-B5) are not on the unit rule. V3 and V3L equal FINAL10's
  V3-lite and gold Top 1.
- **multisymbol:** silver, the FX pairs, accounts b and the stream (other symbols or sizings), and its 8y Turtles
  (FINAL10's to the cent).
- **improve, candidates, levers, packages, sweeps, robustness, baseline, long:** superseded by FINAL10 and the ladder
  study. They are per-quarter or 3-month windows of the old live ladder, metrics only.
- **optimise, live_safety, silver, signal, data_quality, parity, demo_parity:** per-lot monthly search results, a shared
  $1,500 two-bot account, another symbol, or no P/L.
- **Study 1's x1.5 accounts and its dev / val / devval accounts:** study 1 kept $2,000 accounts only at x1.0 on full
  and hold-out. Its other windows are per 0.01 lot and are shown on that basis.
