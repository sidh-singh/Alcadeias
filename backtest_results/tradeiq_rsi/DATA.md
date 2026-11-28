# The data of the study (PREREG section 2)

Written 28 Nov 2026 by the data and execution harness (`backtesting/research/tradeiq_market.py`). Nothing here is a
result of any variant.

## The data end

| Symbol | First tick | **Last tick = the data end** | The archive file's Last-Modified | Exclusive end the code uses |
|---|---|---|---|---|
| XAUUSDm | 2017-01-03 00:00:03.000 UTC | **2026-11-25 23:59:59.968 UTC** | Thu, 26 Nov 2026 01:41:25 GMT | 2026-11-26 00:00 UTC |
| BTCUSDm | 2018-01-01 00:00:00.132 UTC | **2026-11-26 23:59:59.006 UTC** | Fri, 27 Nov 2026 01:41:09 GMT | 2026-11-27 00:00 UTC |

The hold-out therefore runs from 2024-07-01 00:00 UTC to these ends. Gold's archive had not yet published
26 November (US Thanksgiving) when it was fetched. The code holds these values as constants (`LAST_TICK`, `DATA_END`),
so a later refresh of the store does not move the study's end; `load()` refuses a store that ends earlier.

## The refresh of November 2026 (28 Nov 2026 01:57-02:02 IST, i.e. 27 Nov 20:27-20:32 UTC)

    python3 -B -m backtesting data --symbols XAUUSDm BTCUSDm --from 2026-11 --to 2026-11

| | XAUUSDm 2026-11 before | after | BTCUSDm 2026-11 before | after |
|---|---|---|---|---|
| ZIP size | 27,842,505 | 68,169,210 | 17,542,543 | 50,834,828 |
| ticks | 2,948,193 | 7,276,005 | 1,619,855 | 4,716,210 |
| M1 bars | 12,460 | 24,860 | 17,276 | 37,435 |
| last tick | 2026-11-12 23:59:56.864 | 2026-11-25 23:59:59.968 | 2026-11-12 23:59:59.652 | 2026-11-26 23:59:59.006 |

How it was confirmed that nothing else changed:
- The sha256, mtime and size of every `meta.json` of the store (226 months) before and after: only the two `2026_11`
  entries differ; the other 224 are identical.
- The sha256 of `m1.npz` of 2017-01 and 2024-06 (gold), 2018-01 and 2024-06 (BTC), and 2026-10 (both): unchanged.
- `find data/store/{XAUUSDm,BTCUSDm} -newer <snapshot>` lists only the four files of each `2026_11` folder.
- The re-published month kept its first part: the ticks before 2026-11-13 number 2,948,193 (gold) and 1,619,855 (BTC),
  the M1 bars 12,460 and 17,276, the bid minimum and maximum 3852.301 / 4148.652 and 71016.16 / 81121.88, all as in
  the old `meta.json`. (The old files themselves were overwritten by the download, so no byte-level comparison of
  those twelve days was possible.)

Through the hold-out start (what the code serves while `FINALISTS.md` does not exist): gold 2,638,586 M1 bars, BTC
3,403,835 M1 bars.

## Binance BTCUSDT spot volume (the RV variants)

    python3 -B -m backtesting.research.tradeiq_market fetch-binance --last-day 2026-11-26
    python3 -B -m backtesting.research.tradeiq_market check-binance

Files: `data/raw/binance/spot/{monthly,daily}/klines/BTCUSDT/1h/` (git-ignored), 106 monthly zips 2018-01 to 2026-10
and 26 daily zips 2026-11-01 to 2026-11-26, each with Binance's `.CHECKSUM`; inventory in
`data/raw/binance/BTCUSDT_1h_inventory.csv`.

Every file (the check of the download reads only the time columns):
- sha256 equal to its `.CHECKSUM`: 132 of 132.
- Time stamps: milliseconds in the files through 2024-12, microseconds in all rows of the 48 files from 2025-01 on.
  The unit is detected per row by its magnitude (above 10^14 is microseconds).
- Open times increasing and inside the file's month or day, one kline per hour once floored to the hour: all files.
- 77,928 hourly klines; 120 hours of the calendar have none (exchange outages), all between 2018-01 and 2023-03.
- 43 klines open 28 min 14.789 s past the hour (2018-02-09 09:28 to 2018-02-11 03:28 UTC, after Binance's 33-hour
  outage of 8-9 February 2018, in the warm-up): assigned to the hour they open in (DEVIATIONS 8).
- 13 klines close before their hour ends (the hour an outage began); one of them (2020-12-21 14:00) is empty.

The plan's check, on the span the hold-out guard serves (2018-01-01 to 2024-06-30):

| Check | Value |
|---|---|
| Exness 1H bars / matched by a kline of the same UTC open time | 56,840 / 56,720 |
| Exness hours without a kline (Binance outages; volume 0, DEVIATIONS 5) | 120 |
| Binance hours inside Exness data holes (belong to no bar) | 112 |
| Gaps in the Binance series | 27, 1 to 32 hours, the last on 2023-03-24 |
| **Correlation of the 1H closes, Binance vs Exness bid** | **0.999998** (by year 0.99965 in 2018, 0.99994 in 2019, at least 0.99999 from 2020) |
| Correlation of 1H log returns, Exness at t vs Binance at t - lag | lag -2 h: -0.032, -1 h: -0.023, **0: +0.985**, +1 h: -0.017, +2 h: -0.031 |
| Lag 0 best in every year | yes (0.961 in 2018 to 0.997 in 2022) |
| abs(Binance / Exness - 1), 1H closes | median 0.068%; p99 2.9% (2018), 2.2% (2019), at most 0.42% from 2020 |

**The check passes: the RV variants stay in the grid.** The larger differences of 2018-19 are in the price levels of
Exness's BTC feed in those years, not in the timing: the return correlation peaks at lag 0 in each year.

Not verifiable yet: the correlation over the hold-out (2024-07-01 to 2026-11-26). The guard refuses Exness and Binance
data past 2024-06-30 until `FINALISTS.md` is frozen; `check-binance` then covers it. The file-level checks above cover
every file, the hold-out's included.
