# RSI+MACD Slope Entry — D1 × H4 × H1 Decision Table

Entry **direction** (fresh entry only) is decided by `strategy._slope_direction()` from
three timeframes. **D1 is a continuous trend regime; H4 is primary; H1 confirms.**
Exits are unchanged (H4/H1). This document mirrors the code exactly.

## Inputs
Each timeframe yields **two slope signs** (RSI, MACD), each `+ / − / 0`:

- **D1** — *regime* signs (NOT the pivot-slope):
  - RSI sign: `+` if RSI ≥ `D1_RSI_UP` (55), `−` if ≤ `D1_RSI_DN` (45), else `0` (45–55 neutral).
  - MACD sign: `+` if MACD line > 0, `−` if < 0, else `0` (`D1_MACD_MODE='line'`; `'hist'` = macd-vs-signal).
- **H4 / H1** — *pivot-slope* signs: RSI (latest OB/OS-band pivot → current) and MACD-hist
  (latest signal-side pivot → current).

**Per-timeframe verdict:** `UP` = both `+` · `DOWN` = both `−` · `SPLIT` = one `+`/one `−` ·
`FLAT` = at least one `0`. D1 collapses SPLIT+FLAT into **MIXED** (it only tests both-aligned).

**H1 confirm:** `≥1 up` = at least one H1 sign `+`; `≥1 down` = at least one `−`;
`both up/down` = both.

## Decision table

### Tier 1 — D1 = UP → strict, BUY-only (D1 and H4 must both be UP)
| H4 | H1 | Decision |
|---|---|---|
| UP | ≥1 up | **BUY** |
| UP | no up (both ≤ 0) | WAIT |
| DOWN / SPLIT / FLAT | anything | WAIT |

### Tier 1 — D1 = DOWN → strict, SELL-only
| H4 | H1 | Decision |
|---|---|---|
| DOWN | ≥1 down | **SELL** |
| DOWN | no down (both ≥ 0) | WAIT |
| UP / SPLIT / FLAT | anything | WAIT |

### Tier 2 — D1 = MIXED (SPLIT or any neutral) → fall back to the H4/H1 engine (D1 ignored)
| H4 | H1 | Decision |
|---|---|---|
| UP | ≥1 up | **BUY** |
| UP | no up | WAIT |
| DOWN | ≥1 down | **SELL** |
| DOWN | no down | WAIT |
| SPLIT | both up | **BUY** |
| SPLIT | both down | **SELL** |
| SPLIT | mixed / neutral | WAIT |
| FLAT (any 0) | anything | WAIT |

## Worked examples  `(D1 rsi,macd | H4 rsi,macd | H1 rsi,macd)`
| D1 | H4 | H1 | Path | Decision |
|---|---|---|---|---|
| +,+ | +,+ | +,− | D1 UP, H4 UP, ≥1 H1 up | **BUY** |
| +,+ | +,− | +,+ | D1 UP but H4 SPLIT → strict | WAIT |
| +,+ | −,− | any | D1 UP but H4 DOWN | WAIT |
| +,+ | +,+ | −,− | D1 UP, H4 UP, H1 no up | WAIT |
| +,0 | +,+ | +,0 | D1 not both-up → MIXED → fallback | **BUY** |
| +,− | −,− | −,+ | D1 MIXED → fallback (H4 DOWN + ≥1 down); D1 RSI+ ignored | **SELL** |
| 0,0 | +,− | +,+ | D1 MIXED → fallback (H4 SPLIT + H1 both up) | **BUY** |
| −,− | −,− | −,+ | D1 DOWN, H4 DOWN, ≥1 H1 down | **SELL** |
| −,− | −,− | +,+ | D1 DOWN, H4 DOWN, H1 no down | WAIT |

## Flowchart
```
FLAT? → signs: D1(regime) · H4(pivot) · H1(pivot)
   │
   ├─ D1 UP  (both +) ─► H4 UP?  ─ yes ─► ≥1 H1 up?   ─ yes ─► BUY
   │                                └ no / no ─────────────────► WAIT
   ├─ D1 DOWN (both −) ─► H4 DOWN? ─ yes ─► ≥1 H1 down? ─ yes ─► SELL
   │                                └ no / no ─────────────────► WAIT
   └─ D1 MIXED ─► H4/H1 engine:
                   H4 UP    & ≥1 H1 up     → BUY
                   H4 DOWN  & ≥1 H1 down   → SELL
                   H4 SPLIT & H1 both up   → BUY
                   H4 SPLIT & H1 both down → SELL
                   else                    → WAIT
```

## Notes
- When D1 clearly trends, an H4 **SPLIT no longer trades** (strict needs H4 fully aligned) —
  unlike the MIXED fallback, where H4-SPLIT + H1-both still trades.
- In the fallback, **D1 is ignored entirely** (a half-signal like `D1 +,0` is MIXED).
- Config knobs: `D1_RSI_UP`/`D1_RSI_DN` (55/45), `D1_MACD_MODE` ('line'), plus the H4/H1
  pivot config `PEAK_LOOKBACK` (20), `PIVOT_WIDTH` (2), `RSI_PEAK_OB`/`RSI_PEAK_OS` (60/40).
- Exits are unchanged (H4/H1): variant-A slope exits; `_h6` variant = +$unit target + slope
  force-close.
