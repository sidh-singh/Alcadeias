# Deviations from PREREG.md

Each entry is written before any result it could affect exists.

## Clarifications written on 28 Nov 2026 before any result existed (they read the plan, they do not change it)

1. **After a stop (S1)** the variant stays flat until its state changes; it does not re-enter the same direction at the
   next bar close because the oscillator is still on the same side.
2. **At a window's first bar** the position takes the variant's state at that bar's close (states are computed over the
   whole history; QQE R1's state is the colour of the last bar that was not gray). The fill is at the next M1 open.
3. **A position still open at a window's end** is closed at the last bar's close of that window, as `external.py` does.

## Clarifications written on 28 Nov 2026 with the data and execution harness (`tradeiq_market.py`), before any result existed

4. **A flip, and a stop at the same open.** A flip (the state changes sides) closes the old side and opens the new
   one at the same fill, the open of the first M1 bar at or after the bar's close (section 4), also when no quote
   exists at that close (a weekend, gold's daily break, a missing minute). `external.py`'s path kernel, given
   decisions stamped at the bar's close, would open the new side one signal bar later in that case (its zero-length
   pause after an exit admits only decisions stamped at or after the exit's minute). The harness therefore stamps each
   decision with its fill bar's open; nothing else in the kernel reads the stamp (no pause, no quote-age limit). For
   the same reason, when a gap stop closes a position at the open where a change of state is filled, the new state is
   still entered there: the change was decided at the bar's close, and clarification 1 is about re-entering the
   side that was stopped.
5. **Binance volume (the RV variants).** Binance's base-asset volume (BTC) of the BTCUSDT 1h kline whose open time is
   our 1H bar's open (UTC). One of our hours without a kline (an exchange outage) gets volume 0, since no trade took
   place on Binance, and is counted; Binance hours inside our own data holes belong to none of our bars. 4H and 1D
   volumes are the sums over our 1H bars inside each bar (a 1D bar merged from a short day includes that day's hours).
6. **Definitions of the scores (section 7).** Per 0.01 lot, after costs, on the window's continuous run. Max drawdown:
   against the running peak of the equity marked at each M1 bar's close (a long at the bid, a short at the ask), the
   trough at the bar's worst mark (`external.py`'s convention, in dollars). Quarters: every calendar quarter of the
   window counts; positive means P/L > 0 between the quarter's edges, open positions marked at the close mark. Weekly
   Sharpe: the P/L between Saturday 00:00 UTC edges (the window's partial first and last weeks included), mean over
   standard deviation (ddof 1) x sqrt(52); the same weeks feed the SPA test. Win rate: the share of trades with
   P/L > 0, the trade closed at the window's end included. Losing streak: the most consecutive trades with P/L < 0.
   Holding time: entry fill to exit fill. Time in the market: the share of the window's M1 bars through which a
   position is held. Buy-and-hold: 0.01 lot bought at the ask at the window's first M1 open and sold at the bid at its
   last M1 close.
7. **The window's edges.** The window's first bar (clarification 2) is the first bar of the signal timeframe that
   closes after the window's start. A decision whose fill would fall at or after the window's end is not executed;
   what is open then is closed at the close of the window's last M1 bar (clarification 3), a long at the bid, a short
   at the ask.
8. **Binance klines off the whole hour.** 43 klines of the archive, from 2018-02-09 09:28:14.789 to 2018-02-11
   03:28:14.789 UTC (right after Binance's 30-hour outage of 8-9 February 2018, inside the warm-up), open 28 min 14.789
   s past the hour, so none of them matches a 1H bar's open exactly. Each is assigned to the UTC hour it opens in (no
   two fall in one hour). Hours whose kline closes before the hour's end (an outage begins) keep the volume they hold.
9. **Erratum to 8 (a fact, not a rule).** Binance's outage of February 2018 lasted 33 hours (no trade from
   2018-02-08 00:28:14.788 to 2018-02-09 09:28:14.789 UTC), not 30. Entry 8's rule is unchanged.

## Clarifications written on 28 Nov 2026 with the indicator module (`tradeiq_ind.py`), before any result existed

They read the plan's "as Pine computes them" (section 5) where the sources are silent; none changes a rule. Every
number below is an indicator value on the bars from the data start to 2024-06-30 (the guard served nothing later);
no rule was run. `PORTING.md` has the details.

10. **The two ports agree (a fact).** Port A and port B, written independently, give the same floats, bit for bit, on
    every line on the 1H, 4H and 1D bars of both symbols (BTC's VWRSI also on Binance volume), from the first bar on,
    except the QQE colour on the first six bars of each series (no RSI yet): GRAY in port A, no value in port B.
    `backtesting/research/tradeiq_ind.py` keeps port A's arithmetic and says GRAY there (neither BLUE nor RED, as
    section 5 defines it), so it equals port A on every bar and port B on every bar but those six; port B is kept as
    its test oracle. No line ever sits exactly on a threshold a rule reads from 2019 on; the closest is the RSI at
    3.1e-6 from 70 (gold 1H), so a last-digit difference from TradingView's own arithmetic could not flip a state.
11. **`ta.ema`'s seed stays the first value**, as section 5 says (TradingView's reference code `pine_ema`).
    TradingView's runtime appears to seed `ta.ema` with the SMA of the first `length` values instead: its output, as
    recorded in the PineTS project's tests, has `ta.ema(close, 5)` na four times and then the SMA. With the SMA seed
    every line from 2019-01-01 is equal bit for bit, except BTC 1D's TSI and its signal (at most 1.8e-10 and
    4.3e-10). No QQE colour, R1 state, white-line side or zero cross, TSI side of 0 or of its signal, signal cross or
    crossing of -30 / +30 differs on any of the six series. The seed cannot move a result.
12. **`ta.hma` with an odd length.** The consolidation score's `ta.hma(p, 5)` takes the half length floor(5/2) = 2
    and the final length floor(sqrt 5) = 2; its `ta.hma(f, 20)` takes 10 and 4. The evidence: TradingView's built-in
    Hull Moving Average script (`ta.wma(src, length/2)`, `math.floor(math.sqrt(length))`), and TradingView's own output
    of `ta.hma(close, 5)` and `ta.hma(close, 9)` as recorded in the PineTS tests, which a rounded half does not
    reproduce. This reading is material: a rounded half (3) would change "score > 0" on 4.1 to 4.6% of the bars from
    2019 (each symbol and timeframe, tick and Binance volume). It is therefore fixed here, before any R3 result.
13. **AlgoAlpha's `(2/3)` is 0.** The script is Pine v5, which divides two `const int` as integers (TradingView's
    migration guide to v6), so `f = ta.hma(p, v) * (v + (2/3) * v)` is 5 x `ta.hma(p, 5)`. `v = length/2` keeps its
    fraction (an input int over a const int), which is exactly 5 for the default 10. This scales the plotted histogram
    only: "score > 0" (R3) is the same under either reading.
14. **The QQE's warm-up and its crosses.**
    - In the owner's v6 copy `trendDirection := trendDirection[1]` has no `nz(..., 1)`. So the direction is na until
      its first cross, and the trend line is the short band until then. This only touches the first days of the data
      (2017 for gold, 2018 for BTC).
    - `ta.cross(a, b)` is read as "`a > b` changed". Reading it as crossover-or-crossunder gives identical lines and
      colours on all six series, because there is no exact tie.
    - The colour is GRAY on every bar before the Bollinger band exists (bar 56).
15. **`ta.stdev`'s reference code** has `SUM()` return 15 for a deviation of magnitude in (1e-10, 1e-4]. This is read
    as a slip of the documentation and not reproduced; deviations of at most 1e-10 count as 0, as that code does. Even
    the literal reading would change the Bollinger band on 23 bars from 2019 (gold 1H 6, BTC 1H 13, 4H 3, 1D 1) and no
    colour.
16. **The TSI signal (a fact).** The public Bjorgum TSI was read from TradingView's script service on 28 Nov 2026
    (version 11). It continues the owner's copy with line 95, `float tsl = ta.ema(tsi, signalvar)`. So the signal that
    section 5 assumes (EMA 14 for "Fast") is the script's own. The owner's 94 lines equal its first 94, apart from the
    whitespace of one comment.
17. **Erratum to 16 (a fact).** Two comment lines of the owner's TSI copy differ from the public script, not one:
    lines 74 and 76, in whitespace only (a tab against spaces). Entry 16's finding is unchanged.
18. **Erratum to 10: the consolidation score has floating-point dust on five BTC bars (a fact).**
    - Before its clamp `math.max(ta.hma(f, 20), 0)`, the score is -2.6e-19 on five bars from 2019:
      - with tick volume, BTC 1H 2024-04-23 09:00;
      - with Binance volume, BTC 1H 2019-11-19 15:00, 2021-03-16 08:00 and 2021-08-03 02:00, and BTC 4H
        2022-12-04 16:00.
    - In exact rational arithmetic the score is exactly 0 on each of them: an exact cancellation inside the HMAs.
      The clamp makes it 0 there, so "score > 0" is false (not chopping), which is the exact answer.
    - On every other bar the module's "score > 0" is the exact answer as well. Positive values are at least 5.3e-7.
      No other value lies in (-1e-9, 0). Every other 0 has no flip of the RSI across 50 inside its 37-bar support,
      so any order of arithmetic gives exactly 0 there.
    - A runtime that adds in another order, TradingView's included, could get +2.6e-19 on these five bars and call
      them chopping. So entry 10's "could not flip a state" holds for every line and threshold except "score > 0" on
      these five bars, which affects only BTC's R3 VWRSI rows (four of the five bars are Binance-volume "RV" rows).
      The module keeps the reference's arithmetic; no rule changes.

## Clarifications written on 28 Nov 2026 with the study code (`tradeiq.py`), before any result existed

They read sections 6 and 7 where the plan is silent; none changes a rule. When they were written, no variant of the
grid had been run on any data.

19. **The states, as the code builds them (section 6).** Every state is computed over the whole history, bar by bar,
    from the lines of `tradeiq_ind.py` on the bid bars of the signal timeframe.
    - The side of a line: above its middle, the long state; below it, the short state; on a bar where the line has no
      value yet (the warm-up) or sits exactly on the middle, the flat state. From 2019 no line sits on a level a rule
      reads (entry 10); the code counts such ties on the bars the windows read and records the count.
    - R4 and the two controls hold the side of the last event: up through the low level (`ta.crossover(x, level)`:
      x > level and x[1] <= level) sets the long state, down through the high level (`ta.crossunder`) the short
      state; flat before the first event. The levels are section 6's (RSI 30 / 70, LaRSI and VWRSI 20 / 80 as in
      their scripts' `alertcondition` lines, TSI -30 / +30). The TSI control crosses the TSI with its signal line, the
      QQE control the white line with 0, with the same two functions.
    - QQE: R1 is the colour of the last bar that was not gray (entry 2), flat before the first one; R2 the same with
      RED flat; R3 the colour itself (BLUE long, RED short, GRAY flat).
    - VWRSI R3: flat while the consolidation score is above 0 or has no value yet, else the side of 50.
    - MA200 alone: the side of the bar's close against the MA200 of the same bar.
20. **The filters (section 6).**
    - F1: at a bar's close the last closed bar is that bar: its close above its MA200 allows the long state, below it
      the short state.
    - F2: the last higher-timeframe bar whose close time is at or before the signal bar's close time
      (`tradeiq_market.htf_at`). For example, the 1H bar that closes at 08:00 reads the 4H bar of 04:00-08:00. The 1D
      bars are `external.day_bars`: a UTC day with fewer than 360 M1 bars is merged into the next day, and the merged
      bar closes at that next day's end.
    - F3: the TSI of the same bar above 0 allows the long state, below 0 the short state.
    - The filtered state is the variant's state, and the executor reads it. So a position opens at the close where the
      filter turns in favour while the oscillator already holds that side, and it closes where either of the two turns
      against it. Entry 1's "until its state changes" refers to this filtered state.
21. **S1's distance** is `tradeiq_market.s1_stop`: 3 x Wilder ATR(14) of the signal timeframe (`external.wilder_atr`),
    read on the entry's decision bar. It equals 3 x `tradeiq_ind.atr14` to 1.5e-15 relative (PORTING.md 2.6); only
    `s1_stop` is used.
22. **The grid has 750 variants, not "about 730".** Read literally, section 6 gives, per symbol, 68 rule rows on 1H
    (five filters), 56 on 4H (four) and 44 on 1D (three), each with S0 and S1: 336 per symbol. BTC adds 78 RV rows
    (39 VWRSI rows x 2 stops). So gold has 336 variants and BTC 414. TSI's R1 and R2 under F3 (the TSI's own side as
    its filter) give the same state series as under F0. They are run as listed, and the number of trials of the
    deflated Sharpe counts every variant run on the symbol (336 / 414), as section 7 says.
23. **The selection's numbers (section 7).**
    - Every comparison uses unrounded values.
    - Rule 2 counts the trades of the Development run at x1.0, the trade closed at the window's end included.
    - Rule 3 uses the Development run at x1.0; its quarters are all 16 calendar quarters of Development (entry 6).
    - "Development + Validation together" is a third window, 2019-01-01 to 2024-06-30, scored as one continuous run
      like the others (`tradeiq_market.WINDOWS["devval"]`), at x1.0. Its profit / max drawdown ranks the qualifiers.
24. **The finalists' indicators (section 7).** The six indicators are RSI, LaRSI, VWRSI, TSI, QQE and MA200 alone.
    A VWRSI row on Binance volume (RV) counts as the VWRSI. The TSI's signal-line control counts as the TSI, and the
    QQE's white-line control as the QQE. A tie in profit / max drawdown is broken by Development's profit / max
    drawdown, then by the id.
25. **The comparison with the RSI (section 7).** An oscillator's variant wins when its value is strictly greater than
    that of the RSI variant with the same family, filter, stop, timeframe and symbol. This is counted for net profit
    at x1.0 and for profit / max drawdown, in Development and in Validation. A profit / max drawdown that does not
    exist (no drawdown) is neither a win nor a loss. The rows of R3, of the controls and of MA200 alone have no RSI
    counterpart and are not compared. BTC's RV rows are compared with the same RSI rows as its tick-volume rows.
26. **Multiple testing (section 7)**, per symbol, on the weekly P/L of the Development runs at x1.0 (entry 6's weeks):
    - The deflated Sharpe ratio (`silver.dsr`) of the variant with the highest weekly Sharpe in Development, with
      N = the variants run on the symbol. The expected maximum Sharpe of N trials uses the variance (ddof 1) of the
      raw weekly Sharpe ratios of all those variants (`silver.expected_max_sr`, as `silver_develop.haircut` does),
      and also the null variance 1 / (T - 1). The variant's own weekly skewness and kurtosis are used. The would-be
      finalists get the same figure, for information.
    - Hansen's SPA p-value is `silver.spa_test` over all variants of the symbol: studentised, stationary bootstrap,
      mean block of 8 weeks, 5,000 resamples, seed 20261117, benchmark flat. White's Reality Check p-value comes from
      the same resamples: the largest sqrt(T) x mean, against the bootstrap maxima recentred at the sample means.

## Clarifications written on 28 Nov 2026 (IST) after the review of the Development and Validation run, before any hold-out result existed

When these were written, the run of 27 Nov 2026 22:14 UTC (`run_info.csv`) had computed every variant on Development,
Validation and D+V, `select` had written `CANDIDATES.md`, and two reviews of them had been read; the counts below come
from those results. No result of the hold-out existed: the guard had served nothing from 2024-07-01 on, and there was
no `FINALISTS.md`. None of these entries changes a rule of sections 6 to 8: the qualification, the would-be finalists
and section 8's pass rule stay as they are. Entry 27 records a reading that the run had already used; entries 28 to 31
read sections 1, 8 and 9 where the plan is silent.

27. **The x1.5 stress multiplies the spread of every M1 bar (a record of the run's reading, written after the run).**
    Section 4's "the spread of every fill times 1.5" is implemented as `TMarket.costed(1.5)`, which multiplies each M1
    bar's mean spread by 1.5 before anything is executed. So at x1.5, besides every fill (the close at the window's end
    included) and the stop slippage (one more spread), a short's stop also triggers on the ask at 1.5 spreads (inside
    a bar: the high + 1.5 spreads at or above the stop; at a gap: the open + 1.5 spreads), and a short is marked at the
    bid + 1.5 spreads. A long's trigger and its marks are on the bid at both costs.
    - The other reading (1.5 spreads at the fills, the trigger on the x1.0 ask) was measured after the run. A short
      enters at the bid, so its stop level is the same at both costs, and with the x1.0 trigger its exits are the x1.0
      run's. Those exits were repriced at 1.5 spreads (half a spread more at a signal, an in-bar stop or the end, one
      spread more at a gap stop); the longs are the x1.5 run's.
    - Over the 237 Development S1 variants that go short, the Development x1.5 net moves by at most $116.60 (BTC
      `1H|VWRSI-RV|R4|F0|S1`); the median absolute move is $1.58; it is higher in 147 variants, lower in 34 and the
      same in 56. Rule 1 changes for one variant, BTC `4H|TSI|R1|F2-1D|S1` (-1.73 to +18.62), which fails rule 3 under
      both readings. No qualifier and no would-be finalist changes. The run's reading stays.
28. **The exam is read against buy-and-hold (sections 1 and 8; information only: section 8's pass rule is unchanged).**
    - Both markets rose over Development and Validation, and five of the six would-be finalists never go short (R2
      rows; BTC's `1D|VWRSI|R3|F0|S1` does). Section 8's rule (net > 0 at x1.0 and profit / max drawdown >= 0.5) is met
      in Validation by buy-and-hold on both symbols, by 116 of gold's 126 and 132 of BTC's 150 R2 rows, and by 61 of 210
      and 99 of 264 of their other rows. A pass alone therefore does not tell a finalist's timing from the rise of its
      market.
    - So each finalist's hold-out result at x1.0 is reported next to: buy-and-hold of 0.01 lot over the same span (net,
      max drawdown, profit / max drawdown; entry 6); the exposure-matched buy-and-hold, i.e. the finalist's time in the
      market x buy-and-hold's net; and the shares of the symbol's R2 rows (long only, MA200 alone's included), of its
      other rows and of its qualifiers that meet section 8's rule over the hold-out, from the hold-out run of every
      variant that section 8 makes afterwards.
    - `RESULTS.md` calls a pass evidence of an edge over holding the market only if the finalist's hold-out profit /
      max drawdown is also above buy-and-hold's; otherwise it says that the pass does not tell the two apart. Passing
      or failing remains section 8's verdict and is reported as such.
    - `select` gives the same comparison for Development, Validation and D+V (`vs_buy_and_hold.csv`,
      `exam_rule_rates.csv`).
29. **Section 8's comparison curves.**
    - "The best variant of each indicator": per symbol and for each of the six indicators of entry 24, its first
      variant in section 7's order, i.e. its qualifier with the highest D+V profit / max drawdown (ties as in entry 24);
      where the indicator has a finalist, that is the finalist. An indicator without a qualifier on the symbol takes its
      variant with the highest D+V profit / max drawdown (ties likewise), marked as not qualifying; on this run's
      results that is only gold's MA200 alone.
    - "The RSI baseline": for each finalist, the RSI variant with the same family, filter, stop and timeframe (entry
      25's pair; the video compares each indicator with the RSI "with the same kind of rule"); an RSI finalist is its
      own baseline. A finalist of R3 or of a control, which has no RSI pair, takes the RSI's R1 row with its filter,
      stop and timeframe (the side of 50, both sides); a finalist of MA200 alone takes the RSI's row of its own family
      (R1 or R2) with F0. Whether that RSI row qualifies does not matter.
    - These rows are fixed by the Development and Validation results alone; `select` lists them (`curves.csv`).
30. **Question 2: a filter against no filter (section 1; the plan gives no comparison for it).**
    - Each variant with F1, F2-4H, F2-1D or F3 is compared with the variant of the same symbol, timeframe, indicator,
      family (R1, R2, R3) and stop with F0, as entry 25 compares with the RSI: a win is a strictly greater value, for
      net profit at x1.0 and for profit / max drawdown (a value that does not exist is neither a win nor a loss), in
      Development and in Validation (and, for information, later in the hold-out). The TSI's F3 rows are not compared,
      since they are its F0 rows (entry 22).
    - The counts are per symbol and filter, and within that per timeframe and per indicator. F1, F2-4H and F2-1D are
      the owner's MA200 idea (the same timeframe, the 4H, the 1D); F3 (TSI > 0) and F1 / F2 (price above its MA200)
      are the pairings the video recommends.
    - A filter "helps" on a symbol when it wins more than half of its pairs on net and more than half on profit / max
      drawdown (of the pairs where both values exist), in Development and in Validation; it "does not help" when it
      wins at most half on both scores in both windows; otherwise it is "mixed". The same words are given per
      timeframe and per indicator.
    - When this was written, the review had counted the net wins of every filter on Development and Validation.
31. **Section 9's claims are judged on the rows each claim is about, per symbol, in Development and in Validation
    separately**, not on pooled counts. A part of a claim holds on a symbol when it holds in both windows, does not hold
    when it fails in both, and is mixed otherwise. "Most" is more than half, "every" is all; "about half" is a median
    ratio in [0.375, 0.625] (nearer to 1/2 than to 1/4 or 3/4); "far fewer" is a median ratio of at most 0.5. A win is
    entry 25's (strictly more net profit at x1.0 than the RSI pair); a trade ratio is a variant's trades over its RSI
    pair's. The parts:
    1. "Half of 8 alternatives could not beat the RSI": cannot be tested (the video's other four are not in the grid).
       "These four did, on most markets": each of QQE, TSI, VWRSI and LaRSI (on BTC also the VWRSI on Binance volume)
       wins most of its RSI pairs.
    2. QQE: fewer trades than the RSI in every pair; it wins most of its pairs; a shorter longest losing streak than the
       RSI in most pairs.
    3. TSI: "the zero line works": its R1 and R2 rows with F0 have net > 0 in most rows; "the signal line is a coin
       flip": its R1 row with F0 earns more than the signal-line control of the same timeframe and stop in most pairs
       (how many control rows have net > 0 is shown with it); "it beats the RSI" is its part of claim 1; "about half
       the trades": the median trade ratio over its RSI pairs.
    4. VWRSI: "the trend rule beats the RSI on every crypto market and timeframe": on BTC, its R1 and R2 rows win most
       of their RSI pairs on each of the three timeframes (tick volume and Binance volume each); "its 20 / 80 reversals
       are no better than the RSI's": its R4 rows win at most half of their RSI pairs (on both symbols; on BTC for both
       volumes); "it needs real volume": on BTC, the RV row earns more than the same row on tick volume in most rows.
       On gold the crypto and real-volume parts cannot be tested (a CFD with tick volume only).
    5. LaRSI: it wins most of its RSI pairs on each of the three timeframes; "far fewer trades": the median trade ratio
       over its RSI pairs; "on 1H it mostly still did not make money on its own": its six 1H rows with F0 (R1, R2, R4;
       S0, S1) have net > 0 in at most half; "4H and 1D are where it shines": its shares of rows with net > 0 on 4H and
       on 1D are both above its share on 1H; "pair it with a trend filter": its F3 rows (TSI > 0) and its MA200 rows
       (F1, F2-4H, F2-1D) each win most of their F0 pairs (entry 30's pairs, on net).
    6. "All four worked best on 4H and 1D": among all rows of the four (on BTC with the RV rows), the share with
       net > 0 on 1H is below that on 4H and below that on 1D; "on 1H even the best struggled": the four's best 1H row
       by net earns less than their best 4H row and their best 1D row.
    `select` writes the evidence (`claims.csv`); the hold-out's counts, once section 8 has run every variant, are for
    information. When this was written, the review had counted the parts of claims 1 and 4 to 6 on Development and
    Validation, and the results of every row they name had been computed.

## Clarifications written on 28 Nov 2026 (IST) for the exam and the money (PREREG 8 and 9), before `FINALISTS.md` was frozen and before any result of the hold-out existed

When these were written there was no `FINALISTS.md`, and the guard had served nothing from 2024-07-01 on. The code of
the exam (`freeze`, `exam`, `holdout`, `curves`, `bots` and `claims` in `tradeiq.py`) had run only with the guard
closed. In that test the hold-out and the full span were replaced by Validation and D+V, and the outputs then equal
those of `results_dev_val.csv`. None of these entries changes a rule of sections 6 to 8: the finalists, the pass rule
and the curves' rows stay as written. They read sections 3, 4, 8 and 9 where the plan is silent.

32. **The freeze.**
    - The exam's code was added to `tradeiq.py` before the freeze. Its blob id therefore changed, so `run` and `select`
      were run again with it. A run into a scratch folder was checked first.
    - Every file of `run` and of `select` is byte for byte as before, except two: `run_info.csv` (the times and the
      blob id of `tradeiq.py`) and `CANDIDATES.md` (its time stamp and the blob id it prints).
    - `FINALISTS.md` holds the finalists in a block that `exam` reads, the code's git blob ids (`git hash-object`), and
      the sha256 of `results_dev_val.csv`, `qualification.csv`, `run_info.csv` and `CANDIDATES.md`.
    - `freeze` writes it once. It refuses while the code differs from the code `run_info.csv` records, and while
      `qualification.csv` is not the selection that `results_dev_val.csv` gives.
    - So the hold-out is computed by the code whose blob ids `FINALISTS.md` holds. `exam_info.csv` and
      `holdout_checks.csv` record whether the code is still that code.
33. **The exam.**
    - The hold-out is 2024-07-01 00:00 UTC to the data end: gold 2026-11-26 00:00 and BTC 2026-11-27 00:00, exclusive
      (`DATA.md`).
    - Each finalist runs once over it, as one continuous run that starts flat at its first bar (DEVIATIONS 2, 3, 7).
      The states are computed on all the bars from the data start, as in every window. It runs at x1.0 and at x1.5
      (DEVIATIONS 27). The scores are DEVIATIONS 6's.
    - "Net profit > 0 at x1.0 costs and profit / max drawdown >= 0.5" is judged on the x1.0 run, both parts, with
      unrounded values. x1.5 is reported, not judged.
    - A run without a drawdown has no profit / max drawdown and does not pass (as `exam_rule` reads it since entry 28).
      A trade's entry is marked at once on the far side of the spread, so in practice only a run without trades has
      no drawdown, and such a run's net is 0.
    - Beside each verdict EXAM.md gives entry 28's comparison: buy-and-hold of 0.01 lot over the same span, the
      exposure-matched figure, and whether the pass is evidence of an edge over holding the market.
34. **Every variant afterwards** (PREREG 8: "for information only").
    - `results_holdout.csv` holds every variant over the hold-out, and `results_full.csv` every variant over
      2019-01-01 to the data end (the span of section 8's curves). Each is one continuous run (DEVIATIONS 2, 3, 7),
      with the scores of `results_dev_val.csv` at x1.0 and x1.5.
    - Development, Validation and D+V are run again on the same load of the data, which reaches the data end. They
      must reproduce `results_dev_val.csv` byte for byte: no number of the selection may depend on data after the cut.
      The finalists' rows of `results_holdout.csv` must equal `exam.csv`. A difference makes the step fail and is
      reported in `holdout_checks.csv`.
    - DEVIATIONS 19's state checks cover the bars from 2019 to the data end. A line without a value stops the step,
      as in `run`; an exact tie with a level is counted.
    - PREREG 2's Binance check (`check-binance`) is then run on the whole span, 2018 to the data end. If it fails, this
      is logged and the RV rows are marked as failing it. Nothing else changes, because no RV row is a finalist.
    - EXAM.md also gives, for information, over the hold-out and over the full span:
      - entry 28's pass rates by kind of row;
      - question 1's counts (entry 25's pairs);
      - question 2's counts (entry 30's pairs).
35. **Section 8's account curves.**
    - The rows are entry 29's (`curves.csv`), plus two more:
      - The RSI's best R1 row (the side of 50, both sides). The lead's task text asks for "the RSI baseline (its best
        R1 variant on the same selection)". It is chosen as entry 29 chooses a best variant: the qualifier with the
        highest D+V profit / max drawdown; with no qualifier, the row with the highest D+V profit / max drawdown; ties
        as entry 24. It is information beside entry 29's baselines, which stay.
      - Buy-and-hold of 0.01 lot.
    - All rows are chosen on Development and Validation only.
    - Each row runs over the full span (2019-01-01 to the data end) and over the hold-out alone (a fresh account on
      2024-07-01). The run is the x1.0 run of `results_full.csv` / `results_holdout.csv`.
    - It is sized on one $2,000 account by `external.account` with the bot's unit rule (section 4): unit = floor
      (balance / 2,500) + 1, at most 10, set when a position opens. The account is wiped at equity 0, at the worst mark
      of an M1 bar.
    - The daily equity is taken at every UTC midnight, an open position at its close mark (a long at the bid, a short
      at the ask). The last point is the window's end, after the closing fill. The same run is also given per 0.01
      lot (`tradeiq_market.unit_curve`).
    - Buy-and-hold on the account is one unit for the whole span, because the unit rule gives 1 at $2,000.
    - The summary is `final10.account_metrics`: final equity, CAGR, max drawdown % at the M1 worst marks, losing
      months, the longest time under water. Beside it come the max drawdown on the daily marks, and the equity, CAGR
      and daily-mark drawdown on 2026-11-13, where the bots' curves end (entry 36).
36. **The five designs the bots run today** (section 8: "where their published runs cover the same span").
    - The designs are the ones the live branches run (22 Nov 2026):
      - gold: V3-lite, Top 1 and Top 2, on the tick engine (`backtest_results/final10/trades_XAUUSDm_ticks.csv.gz`);
      - BTC: Top 2 (ticks), and Turtle System 2 + bot votes (M1 bars; final10's warm re-check, label "Turtle [alt]
        + bot votes").
    - Their published runs that reach 2019 are final10's eight-year accounts: one fresh $2,000 account each,
      2018-11-13 to 2026-11-13. They do not cover 2026-11-13 to the study's data end (13 days on gold, 14 on BTC).
      So the bots' curves end on 2026-11-13, and the TradeIQ curves are set beside them at that date.
    - How a curve is rebuilt from a run's trades:
      - The trades are taken in order of entry; no two of them overlap.
      - Each trade's P/L per unit is its P/L over its size in units of 0.01 lot per position.
      - A fresh $2,000 account from 2019-01-01 (and one from 2024-07-01) takes the trades opened at or after its start.
        A trade still open at the start is dropped, because a fresh account starts flat.
      - Each trade is sized by the unit rule on this account's balance at the trade's open. Its P/L is that size times
        the P/L per unit.
      - The daily equity at each of the run's daily samples is this account's balance plus the run's open P/L at the
        sample, times this account's size over the run's size. A basket that the tick engine left open at the end
        (marked, not closed) is treated the same way.
    - What the rebuild rests on was checked on the runs before use (`bots_check.csv`). The check reads only final10's
      files, and it ran with the guard closed. In all ten runs (the five designs, eight and five years):
      - no two trades overlap;
      - every size is the unit rule on the run's own balance at the trade's open;
      - every sample with no trade open over the day's 00:00 equals that balance.
    - The accuracy, measured. final10's five-year accounts (fresh $2,000 on 2021-11-13) were rebuilt from the
      eight-year trades and compared with those accounts as the engine ran them. The rebuild differs from them by:

      | Design | Rebuilt minus engine | Share of the engine's final equity |
      |---|---|---|
      | V3-lite | -$108.19 | -1.0% of $10,747.58 |
      | Top 1 | +$14.03 | +0.1% |
      | gold Top 2 | +$0.17 | 0.0% |
      | BTC Top 2 | +$211.90 | +5.4% of $3,918.63 |
      | Turtle | $0.00 | 0.0%: every daily sample is equal to the cent |

      - The trades that both runs share agree to within $0.01 per unit.
      - The differences come from the trades that differ:
        - one to six trades in the first days, which the fresh run takes differently (BTC Top 2's two runs re-join
          within ten days);
        - on the tick engine, a few later trades whose exits are seconds apart (2 of V3-lite's 517 trades, 3 of Top
          1's 783). The engine rounds each position's profit to the cent before it compares that profit with a stop
          and a target that scale with the basket's size, so the same price path can cross them a tick apart;
        - the unit rule compounds them.
      - Expect the same accuracy of the bots' curves from 2019-01-01 and from 2024-07-01. On 2019-01-01 a trade was
        open in the eight-year runs of V3-lite, Top 1 and Top 2 on gold, and of Top 2 on BTC. On 2024-07-01 one was
        open in those of V3-lite, Top 1 and BTC Top 2. The Turtle had none open on either date.
    - What the rebuild cannot give:
      - the fresh account's own first trades where the run held a trade at the start;
      - the drawdown inside a day: these curves' max drawdown is on the daily samples, and the TradeIQ curves'
        daily-mark drawdown is given beside it;
      - the last 13-14 days.
    - The unit rule's step is $2,500 for all five, as in section 4 and final10. The live bots size from half the real
      balance with steps of $1,250 to $2,500, which is not modelled.
37. **Section 9's claims beside the hold-out.**
    - CLAIMS.md gives each part's verdict as entry 31 defines it, on Development and Validation. It is recomputed from
      `results_dev_val.csv` and must equal `claims.csv`.
    - Beside it come the same count and the same test on the hold-out's rows (`results_holdout.csv`), by the same
      code: the hold-out's rows stand in for both of `claims`' windows. They are reported as "holds" or "does not
      hold" in the hold-out, for information. They do not change a verdict.

## Facts recorded on 28 Nov 2026 (IST) after the exam (they change no rule)

38. **The checks of the exam's steps (facts).**
    - **The freeze.** `freeze` wrote `FINALISTS.md` (sha256 `2cdad1fae3836ca82d51cf638934e5baceb568743358ca8df3b91f4fe961ce5e`)
      with the code `tradeiq.py` d0ad7f06a226, `tradeiq_ind.py` 2a6483a415eb and `tradeiq_market.py` dc784854b60c. That
      code computed the exam, the hold-out of every variant, the curves and the claims (`exam_info.csv`,
      `holdout_checks.csv`).
    - **The reproduction.** On the data to the data end, Development, Validation and D+V reproduced
      `results_dev_val.csv` byte for byte (`holdout_checks.csv`: True). The finalists' rows of `results_holdout.csv` equal `exam.csv`
      (True).
    - **PREREG 2's Binance check** on 2018-01-01 to 2026-11-27 passes (`binance_check_full.json`), so the RV rows stay:
      - the 1H closes correlate at 0.9999991, and at least 0.99998 in each year from 2020;
      - the best lag of the returns is 0 h;
      - no Exness hour from 2024-07-01 on lacks a kline, and there is no gap in the Binance series after
        2023-03-24.
    - **The Turtle check.** The bots' Turtle System 2 + votes curves, rebuilt by `bots`, equal an exact re-run of the
      design by final10's bar runner (`external.py`, unchanged) from 2019-01-01 and from 2024-07-01 to 2026-11-13, to
      3e-12 on every day. That run's max drawdown at the M1 worst marks is 32.7% and 36.8%; on the daily marks it is
      30.8% and 34.8%.
    - **The tests after the freeze.** `tests/test_tradeiq.py::test_the_written_results_are_the_grid` now fails by
      design, because it asserts that `FINALISTS.md` does not exist. The other 124 tests pass. Before the freeze, all
      125 passed with the exam's code.
