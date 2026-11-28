# TradeIQ's four RSI replacements on gold and BTC: pre-registration

Written 28 Nov 2026 on `backtest_hedging`, before any of these indicators was computed on our data. The sha256 of this
file is in `PREREG.md.sha256`. Every later change of a rule is a deviation, logged in `DEVIATIONS.md` with its reason and
written before the result it could affect exists.

## 1. The question

The owner sent the transcript of TradeIQ's video "the RSI and four better replacements" and the TradingView source of
the four indicators it ranks: QQE MOD (Mihkel00), Bjorgum TSI, Volume Weighted RSI (AlgoAlpha) and Laguerre RSI
(Ehlers / KivancOzbilgic). Source: `/Users/sidharthsingh/Desktop/study/rsi_study/` (read-only; not copied into the
repository, which is public).

1. Used with the rules the video gives, does each indicator beat the plain RSI(14), and does it make money after
   Exness costs, on XAUUSDm and BTCUSDm, on the 1H, 4H and 1D charts?
2. Do the pairings the video recommends (a trend filter: the TSI above zero, or price above the 200 moving average)
   help? Does the owner's idea help: a 200-period moving average on a higher timeframe (4H, 1D) or on the same one?
3. Which, if any, should be considered for the bots, and how much would it have earned on an account?

The video's own test (7 markets, 1H / 4H / 1D, 2021 to now, "real trading costs") is behind a paid sheet; its claims are
in section 9 and are checked, not assumed.

## 2. Data

- Exness ticks (bid and ask, UTC ms), the bots' own source: XAUUSDm from Jan 2017, BTCUSDm from Jan 2018, to the last
  tick of the store after the November 2026 month is downloaded again on 28 Nov 2026 (the data end is recorded in the
  build report). The M1 bars of the store: bid OHLC, mean spread, tick count.
- Bars of 1H, 4H and 1D are built from the M1 bars on UTC boundaries, exactly as `backtesting/research/external.py`
  does (`tf_bars`, `day_bars`: a UTC day with less than six hours of quotes is merged into the next day).
- Indicator source: the bid close (TradingView's CFD charts show the bid).
- Volume: the tick count of each bar (Exness has no traded volume; TradingView shows tick volume for CFDs too). For BTC
  only, a second volume source: BTCUSDT spot volume from Binance's public archive (data.binance.vision, 1h klines,
  summed to 4H and 1D on UTC boundaries). It is used only by the volume-weighted RSI variants marked "RV". If the
  download or the time alignment fails its check (bar times, gaps, a correlation of Binance and Exness closes above
  0.999 on 1H), those variants are dropped and that is logged.

## 3. Windows

| Window | From | To | Use |
|---|---|---|---|
| Warm-up | data start | 2018-12-31 | indicators only (the daily 200 MA needs 200 trading days) |
| Development | 2019-01-01 | 2022-12-31 | every variant; the selection |
| Validation | 2023-01-01 | 2024-06-30 | every variant; the selection |
| Hold-out (exam) | 2024-07-01 | data end | the finalists' verdict; computed for any variant only after `FINALISTS.md` is frozen |

The code refuses to compute any result inside the hold-out until `FINALISTS.md` and its sha256 exist.
Every window is scored as a continuous run that starts flat at its first bar (indicators see the history before it).

## 4. Execution and costs (the model of `external.py`, unchanged)

- A signal is read on the CLOSE of a bar of its timeframe. The order fills at the open of the first M1 bar at or after
  that close: a buy at the ask, a sell at the bid (ask = bid + that M1 bar's mean spread). Exits likewise.
- The stop variant (S1) is checked on every M1 bar: a gap at the open fills at the open; within a bar the stop fills at
  the stop price; one extra spread of slippage is charged on every stop fill.
- One position at a time per variant. No swap (the Standard account is swap-free, as in every earlier study).
- Size: 1 unit = 0.01 lot (gold 1 USD per 1.00 of price, BTC 0.01 USD per 1.00). Results are per 0.01 lot.
- Cost stress (x1.5): the spread of every fill times 1.5.
- Account curves (section 8): $2,000 start, the bots' unit rule (unit = floor(balance / 2,500) + 1, at most 10, set when
  a position opens), equity marked at the worst price of each M1 bar; an account is wiped at equity 0.

## 5. The indicators (the scripts' defaults; nothing is tuned)

The ports follow Pine semantics exactly (`ta.rsi` = Wilder RMA seeded with an SMA; `ta.ema` seeded with the first value;
`ta.rma`, `ta.sma`, `ta.wma`, `ta.hma`, `ta.stdev` as Pine computes them; `x[1]` = the previous bar). Two engineers port
each indicator independently; the two ports must agree on the real bars of both symbols before any test runs.

| Name | Script | Defaults | Lines used |
|---|---|---|---|
| RSI | the plain RSI | 14, close | RSI |
| LaRSI | Laguerre RSI | alpha 0.2, close | 100 x LaRSI (0-100) |
| VWRSI | Volume Weighted RSI | 14, close; consolidation length 10 | the RSI line (0-100); the consolidation score (`range_score`, above 0 = chopping) |
| TSI | Bjorgum TSI, speed "Fast" | short 5, long 25, signal 14 | TSI x 100 (zero line); signal = EMA(TSI, 14) (the copy of the script ends before the signal line: EMA is TradingView's standard TSI signal; logged) |
| QQE | QQE MOD | RSI 6, smoothing 5, factors 3.0 / 1.61, threshold 3, Bollinger 50 x 0.35 | colour of the bar: BLUE = secondary RSI - 50 > 3 and primary RSI - 50 > upper band; RED = secondary RSI - 50 < -3 and primary RSI - 50 < lower band; GRAY = neither. The secondary QQE trend line - 50 ("white line") |
| MA200 | simple 200 moving average of the close | 200 | |
| ATR | Wilder ATR | 14 | for the stop variant only |

## 6. The rules

Positions change only at bar closes of the signal timeframe. "Long state" / "short state" below decide the position.

**Families (the video's rules):**
- **R1, trend, both sides (stop-and-reverse):** long while the line is above its middle, short while below; the
  position flips at the close of the bar that crosses. Middle: RSI 50, LaRSI 50, VWRSI 50, TSI 0. QQE: a BLUE bar sets
  long, a RED bar sets short, a GRAY bar keeps the position ("a few gray bars on the pullbacks, but never red: stay in").
- **R2, trend, long only:** as R1, but the short state is flat.
- **R3, stand aside in chop** (the two indicators that have it): QQE: BLUE long, RED short, GRAY flat. VWRSI: flat
  while the consolidation score is above 0, else the side of 50.
- **R4, reversal levels (the scripts' alerts; a control):** RSI up through 30 = long, down through 70 = short; LaRSI
  20 / 80; VWRSI 20 / 80; TSI up through -30 = long, down through 30 = short; stop-and-reverse.
- **Controls:** TSI crossing its signal line (stop-and-reverse; the video calls it a coin flip). QQE white line crossing
  zero (stop-and-reverse).
- **MA200 alone (the owner's idea as a strategy):** long while the close is above MA200, short while below (R1) or
  flat (R2), on the same timeframe.

**Filters (applied to R1, R2 and R3 of the five oscillators; not to the controls):**
- **F0:** none.
- **F1 MA200, same timeframe:** a long state is allowed only while the last closed bar closed above its MA200, a short
  state only below.
- **F2 MA200, higher timeframe:** the same with the last CLOSED bar of the higher timeframe: 1H signals with the 4H
  MA200 (F2-4H) or with the 1D MA200 (F2-1D); 4H signals with the 1D MA200 (F2-1D). None for 1D.
- **F3 TSI:** a long state only while TSI > 0, a short state only while TSI < 0, on the signal timeframe.
- Under a filter a state that is not allowed becomes flat: entries only in the filter's direction, and a position
  is closed when the filter turns against it or the oscillator's state ends, whichever comes first.

**Stops:** S0, none (exits by the rule only). S1, a fixed stop 3 x ATR(14) of the signal timeframe from the entry
fill, set at the entry and never moved.

**The grid:** {RSI, LaRSI, VWRSI, TSI, QQE} x {R1, R2} x filters, plus {VWRSI, QQE} x R3 x filters, plus the R4
controls of RSI, LaRSI, VWRSI and TSI, the two other controls, and MA200 alone (R1, R2); every row with S0 and S1; on
1H, 4H and 1D; for XAUUSDm and BTCUSDm. For BTC also the VWRSI rows with Binance volume ("RV"). About 730 variants.
Nothing else is run before the exam; any addition is a deviation.

## 7. Scores and the selection (Development and Validation only)

Per variant and window, per 0.01 lot after costs: net profit (x1.0 and x1.5), number of trades, win rate, profit
factor, max drawdown (on equity marked at M1 bar extremes), profit / max drawdown, share of positive calendar quarters,
annualised weekly Sharpe, average holding time, time in the market. Buy-and-hold of 0.01 lot as a reference.

**Comparison with the RSI (question 1):** each oscillator's variant against the RSI variant with the same family,
filter, stop, timeframe and symbol: wins on net profit x1.0 and on profit / max drawdown, Development and Validation.

**A variant qualifies when:**
1. Development: net profit > 0 at x1.0 and at x1.5 costs;
2. Development: at least 30 trades (1H, 4H) or 15 trades (1D);
3. Development: profit / max drawdown >= 1.0, and at least 50% of the quarters positive;
4. Validation: net profit > 0 at x1.0.

**Finalists:** among the qualifiers of a symbol, the three with the highest profit / max drawdown over Development +
Validation together, with at most one per indicator (MA200 alone counts as one). If none qualifies, there is no finalist
and the answer is "none".

**Multiple testing:** for the best variant of each symbol, the deflated Sharpe ratio for the number of variants run on
that symbol, and White's Reality Check / Hansen's SPA p-value on Development weekly returns over all variants.

## 8. The exam and the money

- `FINALISTS.md` (the finalists, their exact rule rows, the code's git blob ids) is written and its sha256 stored before
  the hold-out is computed for anything.
- **A finalist passes when, over the hold-out:** net profit > 0 at x1.0 costs and profit / max drawdown >= 0.5.
- Afterwards the hold-out is computed for every variant, for information only.
- **Account curves** ($2,000, the unit rule, section 4): every finalist, and for comparison the best variant of each
  indicator and the RSI baseline, over 2019-01-01 to the data end, and over the hold-out alone. Shown as graphs together
  with the five designs the bots run today, where their published runs cover the same span.

## 9. The video's claims, checked one by one

1. Half of 8 alternatives could not beat the RSI; these four did, on most markets.
2. QQE MOD takes fewer trades than the RSI on every market and timeframe, and beats it on most, with shorter losing
   streaks.
3. TSI: the zero line works, the signal line is a coin flip; it beats the RSI on most markets with about half the trades.
4. VWRSI: the trend rule (side of 50) beats the RSI on every crypto market and timeframe; its 20 / 80 reversals are no
   better than the RSI's; it needs real volume (crypto), not tick volume.
5. Laguerre RSI: beats the RSI on most markets on every timeframe with far fewer trades; on 1H it mostly still did not
   make money on its own; 4H and 1D are where it works; pair it with a trend filter (TSI > 0 or MA200).
6. All four worked best on 4H and 1D; on 1H even the best struggled.

Each claim gets a verdict on our two markets: holds, does not hold, or cannot be tested here (and why).

## 10. Deliverables

- `RESULTS.md`: the answer in plain English for the owner, the equity graphs, the claims' verdicts, the caveats.
- `STUDY.md`: what each indicator computes and what the video says, the porting notes.
- CSVs of every variant and window; the account curves; PNG graphs and an HTML page.
- Code: `backtesting/research/tradeiq_ind.py` (the indicators), `backtesting/research/tradeiq.py` (the study),
  `tests/test_tradeiq.py`. Nothing is committed until the owner asks.
