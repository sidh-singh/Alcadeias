# The independent re-derivation before the freeze (28 Nov 2026, IST)

Before `FINALISTS.md` was frozen, five agents checked the run of commit 512d15b without using its execution code.
Four re-executed the 17 would-be champions' decisions with their own fill-and-exit code. The fifth re-derived the
selection from the result files.

## How

- **Decisions.** The re-executions took the rule's decisions only from the harness's data and the rule module:
  `tradeiq2_market.load` (markets ending at the hold-out start) and `Context`, then the module's
  `build(variant, ctx)`. That gives the entries, orders or states, the stops and targets, exit masks, tightenings and
  `close_gap`.
- **Execution.** They executed those decisions with their own plain Python/numpy code over the M1 bars. They called
  no harness execution function: no `run_exec`, `run_variant`, `_Sim`, `_plan`, `_book` or `scores`, none of
  `external`'s kernels, and none of study 1's marks functions. The rules were taken from PREREG 4, the harness
  docstring, harness readings 1-15 and the modules' readings: fills at the next M1 open (buys at the ask), absolute
  levels re-measured from the fill, gap stops, one extra spread on stop fills, exit masks from the next bar, the
  window's start and end, and `close_gap`.
- **Scores.** They computed the drawdown from their own M1 marks and the quarter and week P/L from their own equity.
- **Entries.** For every finalist (and, as an extra, every other champion), they rebuilt the entries from the
  reconciled port's output with their own code (trend machines, filters, ATR, stops, anchors). They did not call
  the rule module's entry functions.
- **Comparison.** They compared field by field (entry and exit time, side, prices, reason, P/L, slippage, R, tag,
  bar) with `trades_dev_val.csv.gz`, and compared every score with `results_dev_val.csv`, `quarters_dev_val.csv` and
  `weekly_dev_val.csv.gz`. This covered Development and Validation at x1.0 and x1.5, and D+V for the scores.

## Result: every number matches

| Variant | Role | Trade rows | Equal | Scores | Entries rebuilt |
|---|---|---|---|---|---|
| `XAUUSDm\|1H\|RIB\|LO\|X0\|F2-4H` | finalist | 580 | 580 | equal | equal |
| `XAUUSDm\|1H\|COIL\|COIL-RIB\|X-3R\|VOL` | finalist | 274 | 274 | equal | equal |
| `XAUUSDm\|1H\|STK\|STK-RA\|LO\|S1` | finalist | 766 | 766 | equal | equal |
| `XAUUSDm\|4H\|ALMA-X\|LO\|X0\|F0` | champion | 1,244 | 1,244 | equal | equal |
| `XAUUSDm\|1H\|MSD-FILTER\|MSD-F6\|QQE\|R2\|S0` | champion | 1,628 | 1,628 | equal | equal |
| `XAUUSDm\|1H\|MSD-ALONE\|MSD-A2\|S0` | champion | 1,652 | 1,652 | equal | equal |
| `XAUUSDm\|4H\|HA-MANAGED\|M2\|RSI-R2-F1-S0` | champion | 632 | 632 | equal | equal |
| `XAUUSDm\|1D\|HA-ENTRY\|HA-H2\|LO\|F0` | champion | 342 | 342 | equal | equal |
| `XAUUSDm\|1H\|WY-DERIVED\|WY-CL\|S-CL\|X-2R50\|F0` | champion | 456 | 456 | equal | equal |
| `XAUUSDm\|4H\|SP\|W2\|POC\|LO` | champion | 84 | 84 | equal | equal |
| `XAUUSDm\|M5\|ORB\|O3\|HV+F2-4H` | champion | 940 | 940 | equal | equal |
| `BTCUSDm\|1D\|HA-MANAGED\|HA-AND\|LaRSI-R2-F3-S1` | finalist | 66 | 66 | equal | equal |
| `BTCUSDm\|1D\|MSD-FILTER\|MSD-F6\|LaRSI\|R1\|S1` | finalist | 192 | 192 | equal | equal |
| `BTCUSDm\|1D\|COIL\|COIL-RIB\|X-3R\|none` | finalist | 50 | 50 | equal | equal |
| `BTCUSDm\|4H\|RIB\|LS\|XBE\|F1` | champion | 458 | 458 | equal | equal |
| `BTCUSDm\|4H\|BOS\|BOS-trend\|LO\|F1\|S1` | champion | 326 | 326 | equal | equal |
| `BTCUSDm\|4H\|SP\|W2\|POC\|F2-1D` | champion | 104 | 104 | equal | equal |

Trade rows are Development plus Validation at both costs: 9,794 in all, every one bit-identical. Scores were equal
to the last bit once the CSVs were read exactly (pandas' default float parser is off by one unit in the last place
on some values; with `float_precision='round_trip'` or raw text every number is identical).

**The selection.** The selection audit wrote its own code for PREREG 7: rules 1-4, the ranking by D+V profit/DD,
the champion of each family and the finalists (at most one per script group, three per symbol). It reproduced
`qualification.csv` (all 38 columns of all 1,543 rows), `champions.csv`, the 101 qualifiers, 17 champions and 6
finalists, and `multiple_testing.csv`. It also matched 2,273 shown cells of `CANDIDATES.md` and
`FINALISTS.draft.md`. Every code blob id in `run_info.csv` equals the files, and the data's sha1 equals the run's.

`freeze` then repeated its own look-ahead check: on markets cut at 2023-01-01, all 11 gold and 6 BTC champions give
the same Development rows. It wrote `FINALISTS.md` (sha256 `106542cc04a27b4c34d77154d1e17ea7b1a5455b9f12ded2adee9ae36d4c53b0`).
