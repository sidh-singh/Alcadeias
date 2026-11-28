# The data of study 2 (PREREG section 2)

Written 28 Nov 2026 with the study's data and execution harness (`backtesting/research/tradeiq2_market.py`). Nothing
here is a result of any rule: these are spans, counts, times and correlations of prices. While `FINALISTS.md` of this
folder does not exist, the harness's guard serves nothing at or after 2024-07-01 00:00 UTC, so every figure about bars
below stops at 2024-06-30 23:59 UTC. The file-level checks of the Binance download (sha256 and time columns only)
cover every file, the hold-out's included.

## The data end

The same as study 1 (`tradeiq_market.LAST_TICK` / `DATA_END`; the store as refreshed on 28 Nov 2026, see
`backtest_results/tradeiq_rsi/DATA.md`):

| Symbol | **Last tick = the data end** | Exclusive end the code uses |
|---|---|---|
| XAUUSDm | **2026-11-25 23:59:59.968 UTC** | 2026-11-26 00:00 UTC |
| BTCUSDm | **2026-11-26 23:59:59.006 UTC** | 2026-11-27 00:00 UTC |

The hold-out runs from 2024-07-01 00:00 UTC to these ends. The code holds them as constants, so a later refresh of the
store does not move them; `load()` refuses a store that ends earlier.

## The store's span per symbol

From the first and last month's `meta.json` of `data/store/<symbol>/` (no bar is read for this table):

| Symbol | Months | First tick | Last tick | `load()` reads from | Data end in the code (exclusive) |
|---|---|---|---|---|---|
| XAUUSDm | 131 (2016-01 .. 2026-11) | 2016-01-03 23:00:02 UTC | 2026-11-25 23:59:59.968 UTC | 2016-01-01 | 2026-11-26 00:00 |
| BTCUSDm | 107 (2018-01 .. 2026-11) | 2018-01-01 00:00:00.132 UTC | 2026-11-26 23:59:59.006 UTC | 2018-01-01 | 2026-11-27 00:00 |
| USTECm | 78 (2020-06 .. 2026-11) | 2020-06-01 00:00:00.073 UTC | 2026-11-13 21:54:59.935 UTC | 2020-06-01 | 2026-11-13 21:55 |
| EURUSDm | 109 (2017-11 .. 2026-11) | 2017-11-01 00:00:00.012 UTC | 2026-11-15 23:59:53.426 UTC | 2017-11-01 | 2026-11-16 00:00 |
| GBPUSDm | 109 (2017-11 .. 2026-11) | 2017-11-01 00:00:00.074 UTC | 2026-11-15 23:59:59.828 UTC | 2017-11-01 | 2026-11-16 00:00 |

- The claim-check markets (PREREG 8, information only) were not refreshed in November 2026: their stores end on
  13 and 15 November, so their hold-out, if it is ever computed, ends there. The code pins these ends too
  (`tradeiq2_market.LAST_TICK` / `DATA_END`); a refresh would have to move them, which would be a deviation.
- Their contracts are not in the engine's config, so the harness gives them the ones the repository already uses:
  USTECm 1 unit per lot, 2 digits (`balke.INDEX_SPECS`); EURUSDm and GBPUSDm 100,000 units per lot, 5 digits
  (`multisymbol`'s FX specs). Section 8 reports them in R and profit factor, which do not depend on the contract.

What the code serves while the hold-out is closed (from the symbol's load start to 2024-06-30 23:59 UTC):

| Symbol | M1 bars | M5 | M15 | 1H | 4H | 1D | 1W |
|---|---|---|---|---|---|---|---|
| XAUUSDm | 2,978,668 | 596,786 | 199,192 | 49,956 | 13,500 | 2,183 | 443 |
| BTCUSDm | 3,403,835 | 681,121 | 227,123 | 56,840 | 14,225 | 2,372 | 339 |
| USTECm | 1,370,640 | 274,424 | 91,538 | 23,294 | 6,393 | 1,055 | 213 |
| EURUSDm | 2,435,066 | 495,722 | 165,476 | 41,391 | 10,692 | 1,727 | 348 |
| GBPUSDm | 2,450,322 | 495,904 | 165,498 | 41,401 | 10,695 | 1,727 | 348 |

Gold's 2,978,668 are study 1's 2,638,586 (from 2017) plus the 340,082 of 2016; BTC's equal study 1's.

## Gold's 2016 months (the Early window's warm-up)

    python3 -B -m backtesting data --symbols XAUUSDm --from 2016-01 --to 2016-12

Run on 28 Nov 2026 at about 13:13-13:22 IST (07:43-07:52 UTC) with the repository's own downloader of the public
Exness archive (generic user agent). It succeeded: all twelve months were downloaded and built into
`data/store/XAUUSDm/2016_01 .. 2016_12` (git-ignored). Nothing else in the store changed: the only files newer than the
November 2026 refresh are the four of each of these twelve folders.

| Month | ZIP (MB) | Ticks | M1 bars | Median spread | First tick | Last tick |
|---|---|---|---|---|---|---|
| 2016-01 | 13.4 | 2,027,394 | 23,578 | 0.469 | 01-03 23:00:02 | 01-31 23:59:59 |
| 2016-02 | 16.2 | 2,338,108 | 28,515 | 0.477 | 02-01 00:00:00 | 02-29 23:59:59 |
| 2016-03 | 14.5 | 2,103,601 | 24,433 | 0.474 | 03-01 00:00:00 | 03-25 00:00:00 |
| 2016-04 | 40.7 | 7,365,452 | 28,204 | 0.470 | 04-01 06:52:51 | 04-29 20:59:26 |
| 2016-05 | 22.1 | 3,616,429 | 29,813 | 0.447 | 05-01 23:00:00 | 05-31 23:59:59 |
| 2016-06 | 13.7 | 1,942,084 | 27,836 | 0.460 | 06-01 00:00:01 | 06-30 23:59:59 |
| 2016-07 | 13.5 | 1,970,912 | 28,310 | 0.498 | 07-01 00:00:00 | 07-31 23:59:59 |
| 2016-08 | 11.9 | 1,694,089 | 31,693 | 0.503 | 08-01 00:00:01 | 08-31 23:59:59 |
| 2016-09 | 11.4 | 1,644,042 | 29,980 | 0.501 | 09-01 00:02:36 | 09-30 20:59:57 |
| 2016-10 | 9.9 | 1,396,001 | 29,060 | 0.488 | 10-02 22:05:00 | 10-31 23:59:50 |
| 2016-11 | 14.5 | 2,017,383 | 29,776 | 0.497 | 11-01 00:00:01 | 11-30 23:59:59 |
| 2016-12 | 10.6 | 1,466,888 | 28,884 | 0.494 | 12-01 00:00:01 | 12-30 21:59:56 |

No tick was dropped as invalid or out of order in any month. The median weekday has 1,380 M1 bars, as in 2017.

**Three holes in the archive** (no quote at all; silences of a weekend, the daily break or a holiday excluded):
- 2016-01-22 20:59 to 2016-01-27 11:16 UTC: Monday 25 and Tuesday 26 January and most of Wednesday 27.
- 2016-03-25 00:00 to 2016-04-01 06:52 UTC: Good Friday and the whole week after it (28-31 March).
- 2016-06-27 09:19 to 2016-06-29 00:00 UTC, with a 56-minute stub on the 28th.

They lie in the warm-up only (PREREG 3: 2016 is read by indicators, never scored), and they end more than nine
months before the Early window starts on 2017-01-01; the bars simply have no bar there, as at any other silence.
Because the download succeeded, the Early window starts on 2017-01-01 as planned (PREREG 2's fallback is not needed).
The guard refuses to score any gold window that starts before 2017-01-01, frozen or not.

## Bars (PREREG 2)

- **1H, 4H, 1D:** study 1's bars, built by `tradeiq_market.TMarket.tbars` itself (UTC boundaries; a UTC day with fewer
  than 360 M1 bars is merged into the next day).
- **M5, M15:** `external.tf_bars` on UTC boundaries (`TMarket2.tbars`), with study 1's construction: the tick volume is
  the sum of the M1 tick counts and the spread is tick-weighted. On real bars they are the store's own resampler's bars
  (`store.resample_bars`; test). New York's offset from UTC is a whole number of hours, so they are also New York bar
  boundaries.
- **1W:** the ISO (Monday-start, UTC) weeks of the merged 1D bars. A 1D bar belongs to the week of its last UTC day
  (`tc - 1 s`): gold's Sunday session, merged into Monday's bar, opens the new week; a short day merged into the next
  full day goes with that day (the short Good Friday sessions of 2016, 2017 and 2018 open the following week; the
  week before ends on Thursday). A last week that the data end cuts before its ISO end (the next Monday 00:00 UTC)
  closes at that ISO end, so it is never read as closed. This is the dashboard module's own
  `tradeiq2_ind_msd.weekly_bars`, bar for bar, on both symbols' real bars to 2024-06-30 (and a test on hand-made bars).
  Through 2024-06-30 gold's weeks span 3 to 8 days from their first bar's open to their close (holiday weeks; a week
  that opens on a Friday closes on the next Saturday 00:00); BTC's are all Monday 00:00 to Monday 00:00.
- **New York clock:** America/New_York with daylight saving (`external.local_seconds` / `utc_of_local`):
  `ny_minute`, `ny_date`, `ny_weekday` of the bars' open times, and Session Hunter's day key, the New York date of
  `time + 4h` (`sh_day_key`).

## Binance BTCUSDT spot volume (BTC's rows that read volume)

PREREG 2: study 1's 1h klines serve 1H and up; 5m klines serve M5 and M15.

    python3 -B -m backtesting.research.tradeiq2_market fetch-binance5 --last-day 2026-11-26
    python3 -B -m backtesting.research.tradeiq2_market check-binance5

Files: `data/raw/binance/spot/{monthly,daily}/klines/BTCUSDT/5m/` (git-ignored), 106 monthly zips 2018-01 to 2026-10
and 26 daily zips 2026-11-01 to 2026-11-26, each with Binance's `.CHECKSUM`, downloaded on 28 Nov 2026 with study 1's
`_http` (generic user agent, nothing identifying sent); inventory in `data/raw/binance/BTCUSDT_5m_inventory.csv`.

Every file (the check of the download reads only the two time columns):
- sha256 equal to its `.CHECKSUM`: 132 of 132.
- Time stamps: milliseconds through 2024-12, microseconds in all rows of the 48 files from 2025-01 on (detected per
  row by magnitude, study 1's `read_klines`).
- Open times increasing and inside the file's month or day, one kline per 5-minute slot once floored to the slot: all
  files.
- 934,970 klines; 1,606 slots of the calendar have none (exchange outages), all between 2018-01 and 2023-03 (2018: 792,
  2019: 352, 2020: 249, 2021: 197, 2023: 16).
- 241 klines open 3 min 14.789 s past their slot (2018-02-09 09:58 to 2018-02-10 05:58 UTC, after Binance's outage
  of 8-9 February 2018, in the warm-up): each is assigned to the 5-minute slot it opens in, as study 1's DEVIATIONS 8
  did for the hour (no two fall in one slot).
- 14 klines close before their slot ends (the slot in which an outage began); they keep the volume they hold.

How the volume is put on our bars (`binance_volume_5m`; study 1's DEVIATIONS 5 read for 5 minutes):
- M5: the base-asset volume (BTC) of the kline whose open time is the M5 bar's open (UTC). An M5 bar without a kline
  (a Binance outage) gets volume 0 and is counted.
- M15: the sum over our M5 bars inside it ("the sum of three"). A Binance slot inside one of our data holes belongs to
  no bar, as for hours in study 1.
- 1H, 4H, 1D: study 1's `binance_volume` (1h klines). 1W: the same function, the sum over our 1H bars inside each week.

The plan's check, on the span the guard serves (2018-01-01 to 2024-06-30):

| Check | Value |
|---|---|
| Binance 5m klines in the span / Exness M5 bars | 681,818 / 681,121 |
| Exness M5 bars matched by a kline of the same UTC open time | 679,515 |
| Exness M5 bars without a kline (Binance outages; volume 0) | 1,606 |
| Binance slots inside Exness data holes (belong to no bar) | 2,303 |
| Gaps in the Binance series | 30, of 1 to 401 slots (the largest: 2018-02-08 00:25 to 2018-02-09 09:55), the last on 2023-03-24 |
| **Correlation of the M5 closes, Binance vs Exness bid** | **0.999998** (by year 0.99966 in 2018, 0.99994 in 2019, at least 0.99999 from 2020) |
| Correlation of 5-minute log returns, Exness at t vs Binance at t - lag | lag -2 bars: -0.013, -1: -0.022, **0: +0.955**, +1: +0.004, +2: -0.012 |
| Lag 0 best in every year | yes (0.898 in 2018, 0.943 in 2019, 0.972 to 0.987 from 2020) |
| abs(Binance / Exness - 1), M5 closes | median 0.068%; p99 2.06% |

**The check passes: BTC's rows that read volume on M5 and M15 keep Binance's volume.** As on 1H in study 1, the larger
level differences of 2018-19 are in Exness's BTC prices of those years, not in the timing: the return correlation
peaks at lag 0 in every year. Study 1's 1h klines passed the same check (`backtest_results/tradeiq_rsi/DATA.md`).

Not verifiable yet: the correlation over the hold-out (2024-07-01 to 2026-11-26). The guard refuses Exness and Binance
data past 2024-06-30 until `FINALISTS.md` of this folder is frozen; `check-binance5` then covers it.
