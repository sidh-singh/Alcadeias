# The optimiser

`python -m backtesting optimise` tries many settings of the backtester "just by changing
parameters" and then tells you how far the best of them can be trusted. The second half is the
point: with enough settings one of them always looks good. Everything here is built so that
the good-looking one has to pass tests it was not chosen on before the report calls it an edge.

It never touches the live files. A setting is a set of `BacktestConfig` overrides, exactly what
`python -m backtesting run --set ...` takes.

## Quick start

```bash
# 1. search on the development period (the default period), 200 settings + refinement
python -m backtesting optimise --space ladder --symbol XAUUSDm

# 2. read backtest_results/optimise/ladder_XAUUSDm/report.md, change the space file, run again ...

# 3. when the space is final: confirm ONCE on months that played no part in choosing
python -m backtesting optimise --space ladder --symbol XAUUSDm --start 2024-01-01 --holdout-to 2025-07-01

# 4. the short list on raw ticks, real 2,000 USD account, eight loop timings per block
python -m backtesting optimise --space ladder --symbol XAUUSDm --start 2024-01-01 --holdout-to 2025-07-01 --validate
```

The same command line can be repeated at any time: what is already computed is read from disk,
so an interrupted run continues where it stopped and a finished one computes nothing.
`--report-only` rebuilds the files without running anything, for example with another
`--objective`.

Rough cost on this machine: one setting on one three-month block of gold takes 1.5 to 3 s
(per-second series; settings that trade a lot are the slow ones). 200 settings on the six
blocks of the development period are 30 to 60 minutes of computing, half of that on the clock
with the default two workers. Each worker holds one block of data (about 0.6 GB).

## Which data to use

| Period | Dates | Use |
|---|---|---|
| Development | 2025-07-01 → 2026-11-13 (the default `--start` / `--end`) | develop, explore, choose |
| Confirmation | 2024-01-01 → 2025-07-01 | once, as the hold-out, for what was fixed on the development period |
| Reserved | before 2024-01-01 | one final test of one frozen setting; the tool refuses to start there without `--allow-reserved` |

The confirmation only means something if the space, the objective and the limits were fixed
before you looked. The report counts how often a hold-out has been shown in a directory
(`holdout_looks.json`) and says so from the second time on. Blocks are counted from `--start`
in steps of `--block`, and 2025-07-01 is a block boundary of a period that starts on
2024-01-01, so step 3 above keeps the development blocks already computed and runs the six new
ones. (A block is computed again only if the tick history under it has changed, or the
history before it as far back as the engine reads it to warm up the slowest timeframe of the
space: about six months for H4, almost three years for D1. Development blocks computed before
the earlier months were in the store are therefore run again, once; the log says so.)

## Writing a search space

A space is a JSON file. Three are shipped in `backtesting/spaces/` and can be named without
their path:

| Space | What it varies |
|---|---|
| `v2` | around the V2 design: trend timeframe, target, stop, pause after a loss, force-close (640 settings) |
| `ladder` | a bounded DCA ladder: 0–4 adds, flat / linear / Fibonacci lots, spacing in price and time, RSI levels, stop, target, target per lot, trend filter, pause after a loss, force-close |
| `entries` | which timeframes vote for the entry, with the V2 exits held fixed (384 settings) |

```json
{
  "name": "example",
  "description": "One sentence for the head of the report.",
  "base": {"force_close_enabled": false},
  "parameters": {
    "max_adds": {"range": [0, 4], "step": 1},
    "ladder_multipliers": {"values": {"flat": [1, 1, 1, 1, 1], "fibonacci": [1, 2, 3, 5, 8]}},
    "ladder_min_gap": {"values": [0, 2, 5, 10], "scale": "price"},
    "loss_cooldown_s": {"range": [300, 28800], "log": true, "n": 5},
    "stop_loss_usd_per_unit": [10, 20, 40],
    "trend_tf": [null, "H1", "H4"]
  },
  "conditions": [
    {"when": "max_adds == 0", "ignore": ["ladder_multipliers", "ladder_min_gap"]}
  ],
  "constraints": ["ladder_min_gap * max_adds < stop_loss_usd_per_unit"],
  "references": {"V2": {"trend_tf": "H1", "max_adds": 0, "target_usd_per_unit": 20, "stop_loss_usd_per_unit": 20,
                        "force_close_enabled": false, "loss_cooldown_s": 14400}}
}
```

| Key | Meaning |
|---|---|
| `base` | fixed overrides on top of the live settings; every setting of the space has them |
| `parameters` | what is varied. Any field of `BacktestConfig` can be named; a field that does not exist is an error, and so are the fields the optimiser sets itself (`symbol`, `start`, `end`, `initial_balance`, `fixed_units`) |
| `conditions` | when a parameter cannot matter, or two values mean the same, say so: the equivalent settings are then run once |
| `constraints` | expressions every setting has to meet; a setting that breaks one is never run |
| `references` | named settings to compare with, given as overrides on the **live** settings (not on `base`). The live settings themselves are always a reference. References are run and shown but are never candidates |
| `price_units` | list of fields that this file writes in USD per 0.01 lot instead of price units (same as `"scale": "price"` on a parameter, and also valid for fields in `base` and `references`) |

**Parameters.** One of:

| Form | Values |
|---|---|
| `[5, 10, 20]` or `{"values": [5, 10, 20]}` | the list, in this order |
| `{"values": {"flat": [1, 1, 1], "linear": [1, 2, 3]}}` | lists or dicts as choices, each with a name (without names the JSON text is the name) |
| `{"range": [0, 4], "step": 1}` | 0, 1, 2, 3, 4 |
| `{"range": [10, 40], "n": 4}` | four evenly spaced values |
| `{"range": [300, 28800], "log": true, "n": 5}` | five values on a log scale, rounded to three significant digits (`"digits"` changes that) |

Optional: `"scale": "price"` (the values are USD per 0.01 lot and are multiplied by the price
move worth 1 USD on a 0.01 lot: gold 1, BTC 100, taken from the contract size, so one file serves
both symbols); `"int": true`; `"ordered": true / false` (see neighbours below); `"note"` (free
text, ignored). `null` is a value like any other (`"trend_tf": [null, "H1"]`: no filter, or H1).
Numbers are converted to the type of the field, so `20` and `20.0` are one setting.

**Conditions.** `{"when": "<expression>", "ignore": [names]}` switches parameters off: they are
left at the value the base configuration has, shown as empty in the tables, and all settings
that differ only in them become one. `{"when": "...", "fix": {"name": value}}` replaces a value
by an equivalent one (the shipped `ladder` space uses it for "Fibonacci and linear lots are the
same up to the second add", and to keep the two RSI levels symmetric). Prefer `fix` to a
constraint for tying two parameters together: a constraint that rejects most combinations also
thins the sample.

**Constraints** remove settings that make no sense. The `ladder` space has one: the entry lot
alone has lost `ladder_min_gap * max_adds` by the time the last add is due, so a stop that is
not wider than that would always fire first, and the setting would only repeat one with fewer
adds.

**Expressions** (conditions and constraints) may use the names of configuration fields,
numbers, strings, `null` / `None`, `true` / `false`, comparisons, `in`, `and`, `or`, `not`,
`+ - * / // %`, and `abs`, `min`, `max`, `len`. A parameter with named values is compared by the
name (`ladder_multipliers == 'fibonacci'`), a price-scaled one by the number in the file. An
expression that names a switched-off parameter is passed over for that setting. Comparing
`null` with a number is an error with the offending values in it; write
`stop_loss_usd_per_unit is None or ...`.

## Samplers

| `--sampler` | What it adds |
|---|---|
| `random` (default) | a stratified sample of `--n` settings: every value of every parameter is covered evenly (to within one setting, wherever conditions and constraints leave room). Reproducible from `--seed`; a larger `--n` continues the same list, so raising it only runs the new settings. A space with no more than `--n` settings is taken whole |
| `grid` | every setting; refused above `--max-grid` (default 2,000) |
| `stored` | nothing new: finish and report what is stored |

After the sample, `--refine-rounds` rounds of **local refinement** (default 2) run every
setting one step away from the best `--refine-top` (default 5) eligible settings so far. A
step moves one parameter to the value next to it in the list; a parameter whose values have no
order (names, `null`) can move to any of its other values. Refinement is repeatable: round *r*
looks only at settings found before round *r*. When a round reports "0 new settings", every
setting around the best ones has been run; until then the "neighbours run" column of the report
shows how many are still missing, and more rounds fill them in.

Refinement is hill-climbing on the selection months, so its settings are the most likely to be
fitted to them. They count as tried, they can be the best setting, and they are judged by the
haircut and the hold-out like any other. They are **not** offered to the walk-forward and the
half-and-half test: those two imitate choosing without part of the data, and a setting that
exists only because all of the data was looked at would carry hindsight into them.

Every setting stored in the output directory stays part of the run, whatever sampler, seed or
`--n` produced it, so nothing can be quietly dropped from the count of settings tried. (To
start a space over, delete its directory, and count what you saw there with `--also-tried`.)

## What is run

- The period is cut into consecutive **blocks** (`--block`, default `3mo`), counted from
  `--start`; the last one is cut where the period ends. Every block is cut into **months**
  (`--slice`, default `1mo`). A month with less than half its days inside the period (the 12
  days of November 2026) is listed in `monthly.csv` and used in no statistic.
- A setting is run once per block: per-second series, one fixed 0.01-lot unit, a balance too
  large to stop out, every block starting flat. This is how the sweeps of the pipeline measure.
- Kept per block: net P/L, the P/L and the number of baskets of each month (a basket counts in
  the month it closed; a basket still open at the end of the block counts with its floating
  result in the last month, so the months add up to the block), the worst basket, and the
  **account replay**: the same baskets on a 2,000 USD account that sizes its unit as the bot
  does (`metrics.replay_account`). "wiped" and "dip" in the tables come from this replay, a fresh
  account in every block.
- Every result is appended to `evaluations.jsonl` as it arrives. Ctrl-C, a crash or a worker
  process that dies (the run then stops and says so) lose at most the runs in progress; the same
  command continues from there.

**When stored results are reused.** The file starts with a stamp: the space (base, values,
conditions, constraints), the symbol, the engine build, the live rules and the account size.
If any of them differs, the file is renamed `evaluations.stale-<time>.jsonl` and a new one is
started. Each result also carries its block (start, end, how it was sliced) and a fingerprint of
the tick data under that block, including the months before it that warm up the indicators; it is
used only for exactly that block and that data. So changing the period keeps the blocks that are
still part of it, and rebuilding a month of ticks, or adding earlier history, recomputes only the
blocks that read it (a log line names them). Do not edit the engine while a run is going: the
run stops rather than mix two builds.

## How a setting is chosen

On the **selection months only**. `--objective`:

| Objective | Ranks by |
|---|---|
| `lcb` (default) | mean monthly net minus one standard error of that mean: a lower bound. A setting that makes 10 every month beats one that makes 90 once and nothing otherwise |
| `mean` | mean monthly net |
| `median` | median monthly net |
| `sharpe` | mean monthly net divided by its standard deviation |
| `worst_block` | net of the worst block |

Not eligible, whatever the objective: a setting whose account replay is wiped in any selection
block (`--allow-wiped` lifts this), or stands more than `--max-dip` USD (default 1,000, half the
account; 0 = no limit) below its start in any selection block. This is the guard against "the
ladder eats most of the balance": such a setting can be the most profitable row of the table
and still never be the answer.

Changing the objective or the limits after seeing a report is one more way of choosing; decide
them first.

## Reading the report

`report.md` opens with what was run, then **What to believe**: a one-line verdict and the
evidence behind it. The rest of the report is that evidence in full.

| Section | What it shows | How to read it |
|---|---|---|
| The top settings | the best `--top` by the objective, with selection and hold-out side by side, then the references; then the net of every block | the hold-out columns are the honest ones; a top setting that is negative there was fitted to the selection months. In the block table, a result that comes from one block is one event, not an edge |
| Is the best result more than luck? | the best setting next to what the best of that many settings **without any edge** shows | see "the haircut" below |
| Does choosing on one half work on the other? | the probability of backtest overfitting | 0% ideal, 50% is noise, above that the search is choosing noise |
| Walk-forward | choose on all blocks up to *t* (among the settings of the sample), trade block *t + 1*, move on | the out-of-sample row is what re-optimising every quarter with past data only would have made; compare it with the hindsight row |
| Average by parameter value | for each value, the average over all sampled settings that contain it | a value that is good on average over everything it was combined with is worth more than one good row |
| Does the ranking carry over? | rank correlation between selection objective and hold-out mean over all settings; what the best tenth did on the hold-out | near zero or negative: ranking on the selection months tells nothing about other months |
| The short list on raw ticks | `--validate` | the real account, real tick timing; see below |
| Reproduce | the `run` line for the best setting | the second line reproduces the stored figure of its last block to the cent |

**The haircut.** Every eligible setting has its own average taken away, which leaves a setting
with no edge but with its real month-to-month spread and its real likeness to the other
settings. The months are then drawn again with replacement (the same months for all settings)
and the best setting is picked exactly as the search picks it. Repeated 2,000 times
(`--bootstrap`) this gives what "the best of N" yields when there is nothing to find. The
report prints that average, its 95th percentile, and the share of such searches that reach the
objective actually found. A best setting at +38 a month when edgeless searches average +29 has
+9 to its name, not +38. Similar settings count as one: the report says how many unrelated
settings the space behaves like, and for comparison what the haircut would be if all settings
were unrelated. `--also-tried N` adds settings tried elsewhere (other spaces, by hand); earlier
runs set aside in the same directory are added automatically.

**The probability of overfitting** (combinatorially symmetric cross-validation; Bailey,
Borwein, López de Prado, Zhu). The selection blocks are split into two halves in every possible
way. On one half the best eligible setting of the sample is chosen as the search would choose
it; on the other half its rank among the settings of the sample is recorded. The percentage is
the share of splits in which it lands below the median. Next to it: its average on the half it
was chosen on, its average on the other half, how often it lost money there and how often the
account replay was wiped there. Six blocks give 20 splits, so the percentage moves in steps of 5; `--block 1mo`
gives many more splits at the price of cutting every basket at each month end.

**Neighbours.** For each top setting the report lists how many settings one step away were run
and their average objective. A setting whose neighbours do about as well sits on a plateau,
and plateaus tend to repeat. One that towers over its neighbours is a spike.

**The verdict** is worded from five tests; the numbers are always printed beside it.

| Test | Pass | Fail |
|---|---|---|
| luck | fewer than 10% of edgeless searches reach the objective found | 25% or more |
| halves | overfitting probability below 25% and a positive average on the other half | 50% or more, or a negative average there |
| walk-forward | out-of-sample mean above its own standard error | out-of-sample mean not above zero |
| neighbours | their average objective is positive and at least half of the setting's own | their average objective is not positive |
| hold-out | mean above its standard error, not wiped | mean not above zero, or wiped |

- **No edge in this space**: the best setting's lower bound on the selection months is not above zero.
- **Probably overfitted**: it fails the luck test and the halves or the walk-forward test.
- **Not proven**: anything in between; the line says which tests it passes, fails or leaves unclear.
- **Holds up on the months it was chosen on**: at least three tests apply and all pass, but no
  months were held out. The next step is the confirmation run, once.
- **Holds up on every test run here, the held-out months included**: all tests pass and the
  hold-out is one of them. That is as much as a backtest can say. The next step is a demo
  account, not more searching.

## Validation on raw ticks

`--validate` replays the best `--validate-top` (default 5) eligible settings and every
reference on raw ticks: each block under `--validate-seeds` (default 8) random loop timings,
on the real 2,000 USD account with the live unit rule, a fresh account per block
(`robustness.timing_ensemble`, the same test the pipeline applies to its candidates). The
report shows, per setting, the median net of the account in every block, how many runs lost
money, how many were stopped out, the drawdown and the worst basket, separately for selection
and held-out blocks. This is the slow step: 7 settings × 6 blocks × 8 timings is 336 raw-tick
runs of a few seconds each, about a quarter of an hour with two workers. Finished blocks are
kept in `validation.csv`.

## Files

`backtest_results/optimise/<space>_<symbol>/` (or `--out`):

| File | Content |
|---|---|
| `report.md` | the report |
| `trials.csv` | one row per setting, best first, then the references. `rank` (eligible settings only), `key`, `origin` (random / grid / refine / reference), one column per parameter (empty = switched off by a condition, `none` = the value null), `eligible`, then for the selection months `objective`, `mean`, `se`, `lcb`, `median`, `sharpe`, `worst_block`, `total`, `months`, `positive`, `t`, `baskets`, `baskets_per_month`, `worst_basket`, `wiped_blocks`, `max_dip`, the same with `holdout_` in front for the held-out months, `neighbours`, `neighbours_of`, `neighbour_objective`, and `overrides` (JSON, relative to the live settings) |
| `monthly.csv` | settings × months, net P/L of one unit; held-out months and partial months are marked in the column name |
| `best.json` | the top setting: values, overrides, the `run` lines, its figures, the verdict and the diagnostics |
| `evaluations.jsonl` | the raw results; delete it to start over |
| `validation.csv` | raw-tick runs of the short list (`--validate`) |
| `holdout_looks.json` | every time a hold-out was reported here |

All figures are USD for one fixed 0.01-lot unit unless they say "account". With the default
unit rule the real account trades one unit up to a balance of 2,500 USD.

## Options

| Option | Default | |
|---|---|---|
| `--space` | required | file, or name of a shipped space |
| `--symbol` | `XAUUSDm` | |
| `--start`, `--end` | 2025-07-01, 2026-11-13 | the period; UTC, end exclusive |
| `--block`, `--slice` | `3mo`, `1mo` | block and month length: `3mo`, `1mo`, `2w`, `10d`, `6h`, `20min` |
| `--holdout-from`, `--holdout-to` | none | blocks never used to choose; must be block boundaries |
| `--holdout-top-only` | off | run the held-out blocks only for the short list and the references |
| `--sampler`, `--n`, `--seed`, `--max-grid` | `random`, 200, 1, 2000 | |
| `--refine-rounds`, `--refine-top` | 2, 5 | 0 rounds = no refinement |
| `--objective` | `lcb` | `lcb`, `mean`, `median`, `sharpe`, `worst_block` |
| `--allow-wiped`, `--max-dip`, `--account` | off, 1000, 2000 | eligibility limits and the account they are measured on |
| `--top` | 10 | settings in the report |
| `--also-tried`, `--bootstrap` | 0, 2000 | haircut: settings tried elsewhere; resamples |
| `--validate`, `--validate-top`, `--validate-seeds` | off, 5, 8 | raw-tick validation |
| `--report-only` | off | compute nothing, rebuild the files |
| `--jobs` | 2 | worker processes (about 0.6 GB each) |
| `--out`, `--live-root` | | output directory; another checkout whose `constants.py` / `symbols.json` are the live settings |
| `--allow-reserved` | off | let the period start before 2024-01-01 |

## From Python

```python
from backtesting import optimise as O

res = O.optimise(O.Options(space="v2", symbol="BTCUSDm", n=100))
a = res["analysis"]                     # everything the report is written from
a.keys, a.X                             # settings, and their monthly net on the selection months
O.cscv(a.X, a.sel.groups, ...)          # every diagnostic is a function of that matrix
```

`objective`, `eligible`, `walk_forward`, `cscv`, `haircut` and `carry_over` take plain arrays
(settings × months, and the columns of each block), so they can be applied to any table of
monthly results, not only to this tool's.

## What this cannot tell you

- Months are few. Sixteen selection months give wide standard errors; an edge of a few USD a
  month per unit cannot be told from zero, and the report will say "not proven" for it.
- The haircut and the overfitting probability resample the months that happened. A regime that
  is not in the data (gold trended strongly through the development period) is not in them either.
- With far more unrelated settings than months the resampled haircut runs a little low; the
  "if the settings were unrelated" line is the upper end.
- Settings tried outside this tool are invisible to it unless you pass `--also-tried`.
- Blocks start flat and the fixed unit never steps up. The account replay and the raw-tick
  validation show what the real account would have done; the validation is the one to trust.
- A setting that passes everything here has earned a demo account, not real money.
