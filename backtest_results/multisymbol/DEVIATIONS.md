# Deviations from PREREG.md (and how its rules were read)

PREREG.md sha256 checked before the run step: `f8557434c42c64eb1dd780b7bf1be0f0941690e289e87f9554e85dd807b9300e` (matches PREREG.md.sha256).
The three fixed inputs (the two round-4 design files and `final10/results.csv`) match their recorded sha256 values.

Each entry was written before any result it could affect existed. Sections A and B were written at 2026-11-16
21:39 UTC (03:09 IST), before the gates ran and before anything was downloaded.

## A. Procedural deviations (none can move a result)

1. **The data-gate record (`quality_report`) runs in calendar-year chunks.** §3.4 runs it once per span. Here it runs on
   the pieces 2017-11-01 / 2018 / 2019 / 2020 / 2021-01-01 to 2021-05-01 / 2021-05-01 to 2022 / 2022 / 2023 /
   2024-01-01 to 2024-05-13 / 2024-05-13 to 2025 / 2025 / 2026-01-01 to 2026-11-13. The Turtle span is the first nine
   pieces and the basket span the last seven. The reason is memory: the machine has 16 GB and the step-up study uses
   most of it, and one span of per-second data needs several GB inside `quality_report`. §3.4 allows one year at a time
   when disk is short. The gate tests of §3.4 (missing months, 8-hour silences, thin weeks, decimals) are computed by
   the run step over each whole span, month by month, so the gate itself is unchanged.
2. **Data fetching overlaps G3.** §10.3 runs G3 after XAGUSDm "and before any other symbol". Here no design runs on
   any other symbol before G3 passes. The download, build, data gate and `specs.json` entry of the next symbols may run
   while G3 runs. They read no trading result. If G3 fails, the run stops and the fetched data are deleted unused.
3. **File layout.** The run step writes per-symbol folders, as the run-step instructions ask:
   `runs/<SYMBOL>/metrics.csv`, `runs/<SYMBOL>/trades.csv.gz`, `runs/<SYMBOL>/daily.csv.gz`, plus `runs/summary.csv`
   (every account x measure of §7, which is §10.6's `runs.csv`; it is also copied to `runs.csv`) and
   `runs/data_quality.csv`. `specs.json`, `quality/`, `checks/` and `logs/` are as in §10.6.
4. **Extra reproduction in G1.** Besides §10.1's five-year window, the gates also reproduce two eight-year figures of
   the final ten (gold V3-lite $11,957.34, BTC Turtle System 2 + bot votes $7,814.72), as the run-step instructions ask.

## B. How rules that leave a detail open were read (fixed before any result)

1. **Drawdown in USD and in %** (§6.1, §7): the largest fall in USD and the largest fall in % of the running peak are
   each taken as their own maximum (they can fall in different episodes). Both use the two measures of §6.1.
   Q5's 50% limit applies to the % figure, as in the final ten.
2. **Wiped** (§6.1): a basket's MAE trough (B_k + u_k x MAE_k x FX) is a mark too: an account whose trough is at or
   below zero is wiped at that basket, as the direct run would be stopped out at that second. The wipe date is the
   basket's first minute mark at or below zero, else its close.
3. **Closed trades** (§7, Q4): an open basket or Turtle position valued at the period end is in the profit, but it is
   not a closed trade (for the Turtles: the simulator's "end" exits are not counted).
4. **Equity at a time T** (blocks, weeks, days): the last mark before T; at the period start $2,000; at the period end
   the final equity. The weekly P/L of §8.4 uses the marks start, every Saturday 00:00 UTC inside the period, end.
5. **"Covers 25 December, 1 January or Good Friday"** (§3.4): the silence overlaps that UTC calendar day. **"The weeks
   of 25 December and 1 January"**: the Monday-to-Sunday weeks that contain those days. A full week is Monday 00:00 to
   Saturday 00:00 UTC inside the span. Leading and trailing silences against the span edges count as silences.
6. **D1 daily move in USD** (§5): converted at the rate of the minute of the day's last M1 bar.
7. **Nights held** (§7, §9): swap times are 17:00 America/New_York (21:00 UTC in US summer time, 22:00 in winter),
   Monday to Friday, weighted 3 on Wednesday (Thursday for USDCAD); per trade from its first entry to its close, and
   per position (lot-weighted) for the swap figures.
8. **The base's BTC Turtles** use BTC history from 2018-01-01 (the final ten's, "its own existing data", §10.2) and
   `external.load_market`, as the final ten did; the new symbols use `balke.SpecMarket` from 2017-11-01 (§2, §4).

## C. The budget scope (written 2026-11-16 23:40 UTC, before any new-symbol result existed; nothing had been downloaded)

1. **Only the first 8 symbols of §10.3 run in this step:** EURUSDm, XAGUSDm, USDJPYm, GBPUSDm, AUDUSDm, USDCADm,
   USDCHFm, NZDUSDm (silver and the 7 majors). The owner pays per token and decided on 2026-11-17 (IST), after the
   pre-registration, that the 13 crosses (and any reserve) come in a later run. Nothing else in §§1 - 9 changes; the
   crosses keep their place and order for that run. A major that fails the basket-span gate is reported and leaves the
   pool (§10.3); no reserve is called in, since reserves replace crosses only.
2. The base (§10.2: the six demo pairs on the two halves) runs here as planned.

## D. The sizing study's finding and G2 / G3 (written 2026-11-16 23:40 UTC, before G2 or G3 ran)

The sizing study (`backtest_results/sizing/SIZING.md`, after the pre-registration) found that for the tick-engine
basket designs a one-unit run replayed into a multi-unit account is not exact: the engine rounds each position's
floating profit to the cent before comparing the basket's profit with units x target, so a larger unit can move an exit
by a second or two and later trades with it (gold V3-lite, 8 years: -$0.54 at STEP $1,000, -$1,665 at STEP $500 with no
cap). §6.1 calls the replay exact up to that rounding, and §10.3 says "if G3 fails, stop". This is read as follows:

1. **G1 must pass to the cent, and the Turtle checks (G2 Turtle part, G3's FX = 1 check) must be exact.** A failure
   there stops the run, as written. The Turtle replay is exact (the sizing study verified it bit for bit).
2. **The basket-design rows of G2 and G3 measure the replay error; they do not stop the run.** A row whose direct
   baskets differ from the replay's (an exit moved by seconds) is reported as such, with the first basket that differs.
3. **"Material"** is fixed now, from §6.1's own tolerances: the replay error is material if any basket-design row of
   G3 (EURUSDm or XAGUSDm, either half, any of the 4 designs, account (a) or (b)) has |direct - replay| final equity
   above the rounding bound ($0.01 x the sum over positions of lots / 0.01), or a drawdown difference above 1 point,
   or a different wiped state. The decision uses only the difference between two computations of the same account,
   never a design's performance.
4. **If material:** for every USD-quoted symbol (XAGUSDm, EURUSDm, GBPUSDm, AUDUSDm, NZDUSDm, and the base XAUUSDm and
   BTCUSDm basket designs) the (a) and (b) accounts reported and used are the engine's own direct runs (the bot's unit
   rule from $2,000, `mtqty` 0.01 or L, the cap scaled to that lot as in G3). Their drawdown is §6.1's measure on the
   direct run's own minute marks and basket MAEs (FX = 1). The replay rows stay in the outputs as `a_replay` /
   `b_replay`. For the USD-base symbols (USDJPYm, USDCADm, USDCHFm) the engine's account is in the quote currency, so
   it cannot apply a unit rule on a USD balance: their (a) and (b) stay replays, flagged `replay`, and the error
   measured on the USD-quoted symbols (per design: the largest |direct - replay| in USD and in % of profit) is
   reported as their accuracy. The one-unit stream (used by the selection) is unaffected in every case.
5. **If not material:** the replay is used everywhere, as §6.1 says, and the G3 differences are reported.
6. **Added 2026-11-16 23:45 UTC, after G1 + G2 ran and before any new-symbol download.** G1 passed to the cent on all
   11 figures (incl. gold V3-lite 8 years $11,957.34 and BTC Turtle System 2 8 years $7,814.72); the G2 Turtle rows
   are exact. The G2 basket rows (gold, BTC, five years) are already over the bound for gold Top 1 + add: replay (a)
   $11,707.85 against the direct run's $12,433.38 (bound $21.58); the other three are within it ($0.82, $0.10, $0.13)
   but none has the same baskets. The error is therefore declared **material now** (the D.3 test applied to G2's rows,
   a method comparison on the base, not on any new symbol), and D.4's "if material" branch is fixed before G3 runs.
   G3 still runs on EURUSDm and XAGUSDm and is reported in full; it no longer decides anything.

## E. The data gate's silence test (written 2026-11-16 23:50 UTC, before any design ran on a new symbol)

1. **What happened.** The first two symbols, EURUSDm and XAGUSDm, fail both spans of §3.4 on the silence test alone
   (no missing month, no thin week, decimals fine). Every failing silence is shared with gold's own feed, which entered
   the final ten with `data_hole_s = 0` and would fail the same test: 2021-03-02 13:21 -> 03-04 00:00 (34.6 h, an
   archive outage: gold, BTC, EURUSDm, XAGUSDm and USDJPYm all silent), 2024-04-09 ~14:00 -> 24:00 (9 - 11 h, gold
   silent too), the US-holiday early closes of silver (2020-07-03, 2025-07-04, 2026-06-19: gold closes at the same
   minute), and the early stops before two weekends (2024-04-12 Friday 17:02, gold silent from 20:56; 2024-04-17
   silver 14:02 -> 24:00, gold silent from 20:56). Applied literally the test removes every symbol and gold itself,
   so G3 (on EURUSDm and XAGUSDm) could not run. The test was meant to catch a symbol's own broken feed.
2. **The nearest rule that can be applied (§11).** A silence that the §3.4 test flags counts only by its part that
   is the symbol's own: the minutes of it in which gold (XAUUSDm) has an M1 bar. The symbol fails the silence test
   when that part is 8 hours or more. Everything else in §3.4 is unchanged; the literal list stays in
   `quality/<SYM>.json` (`bad_silences_literal`) next to the applied one, and the report shows both.
3. **What it can have been influenced by.** Only by the data gate's own record (silences in quotes) of EURUSDm and
   XAGUSDm; no design had run on any new symbol, and the rule does not look at prices or results.
