# RSI+MACD Slope Entry — H4 × H1 Decision Table  (`_wd` / without-daily branch)

Entry **direction** (fresh entry only) is decided by `strategy._slope_direction()` from
**two** timeframes. **D1 has been removed on this branch** — there is no daily side-gate;
the entry is purely **H4 primary / H1 confirm**. Exits are unchanged (H4/H1). This document
mirrors the code exactly.

> This is the "without-daily" (`_wd`) A/B counterpart of the D1-gated branches. On those,
> a D1 pivot additionally filtered the side (see `docs/d1-decision-table.md` there); here
> that whole stage is gone.

## Inputs
Each timeframe yields **two pivot-slope signs** (RSI, MACD-histogram), each `+ / − / 0`:

- **RSI** sign: slope from the latest OB/OS-band pivot (HIGH only if RSI ≥ `RSI_PEAK_OB`
  = 60, LOW only if RSI ≤ `RSI_PEAK_OS` = 40) to the current RSI.
- **MACD** sign: slope from the latest MACD-histogram pivot (side chosen by the MACD
  **signal line**: signal > 0 → read the HIGH side, < 0 → the LOW side) to the current hist.

**Per-timeframe verdict:** `UP` = both `+` · `DOWN` = both `−` · `SPLIT` = one `+`/one `−` ·
`FLAT` = at least one `0`.

**H1 confirm:** `≥1 up` = at least one H1 sign `+`; `≥1 down` = at least one `−`;
`both up/down` = both.

## Decision table (H4 primary · H1 confirm)
| H4 | H1 | Decision |
|---|---|---|
| UP (both +) | ≥1 up | **BUY** |
| UP | no up (both ≤ 0) | WAIT |
| DOWN (both −) | ≥1 down | **SELL** |
| DOWN | no down (both ≥ 0) | WAIT |
| SPLIT (one +, one −) | both up | **BUY** |
| SPLIT | both down | **SELL** |
| SPLIT | mixed / flat | WAIT |
| FLAT (any 0) | anything | WAIT |

## Worked examples  `(H4 rsi,macd | H1 rsi,macd)`
| H4 | H1 | Path | Decision |
|---|---|---|---|
| +,+ | +,− | H4 UP, ≥1 H1 up | **BUY** |
| +,+ | −,− | H4 UP, H1 no up | WAIT |
| −,− | −,+ | H4 DOWN, ≥1 H1 down | **SELL** |
| −,− | +,+ | H4 DOWN, H1 no down | WAIT |
| +,− | +,+ | H4 SPLIT, H1 both up | **BUY** |
| +,− | −,− | H4 SPLIT, H1 both down | **SELL** |
| +,− | +,− | H4 SPLIT, H1 split | WAIT |
| +,0 | +,+ | H4 FLAT (a 0) | WAIT |

## Flowchart
```
signs: H4 · H1 (latest-pivot slopes; D1 removed)
        │
        ├─ H4 UP    & ≥1 H1 up     → BUY
        ├─ H4 DOWN  & ≥1 H1 down   → SELL
        ├─ H4 SPLIT & H1 both up   → BUY
        ├─ H4 SPLIT & H1 both down → SELL
        └─ else                    → WAIT
```

## Notes
- **D1 removed:** `SLOPE_TIMEFRAMES` is `['TIMEFRAME_H1', 'TIMEFRAME_H4']` (no D1 fetch,
  no D1 slope, no D1 dashboard row/graphs). `_slope_direction` has no D1 stage.
- Config knobs (shared by H4/H1): `PEAK_LOOKBACK` (20), `PIVOT_WIDTH` (2),
  `RSI_PEAK_OB`/`RSI_PEAK_OS` (60/40).
- Exits are unchanged (H4/H1): variant-A slope exits; `_h6` variant = +$unit target +
  slope force-close.
