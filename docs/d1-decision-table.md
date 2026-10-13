# RSI+MACD Slope Entry — D1 × H4 × H1 Decision Table

Entry **direction** (fresh entry only) is decided by `strategy._slope_direction()` from
three timeframes. **All three (D1, H4, H1) are latest-pivot slopes** — D1 is a *pivot*,
not a trend regime. The slope force-close exit also reads all three tiers (retuned
2026-10-13 — see Notes). This document mirrors the code exactly.

## How it works — two stages
1. **Base direction** — H4 **primary**, H1 **confirm** (the H4/H1 engine).
2. **D1 side-gate** — the D1 pivot filters which *side* is allowed:
   D1 UP ⇒ buys only · D1 DOWN ⇒ sells only · D1 MIXED ⇒ no filter.

## Inputs
Each timeframe yields **two pivot-slope signs** (RSI, MACD-histogram), each `+ / − / 0`:

- **RSI** sign: slope from the latest OB/OS-band pivot (HIGH only if RSI ≥ `RSI_PEAK_OB`
  = 60, LOW only if RSI ≤ `RSI_PEAK_OS` = 40) to the current RSI.
- **MACD** sign: slope from the latest MACD-histogram pivot (side chosen by the MACD
  **signal line**: signal > 0 → read the HIGH side, < 0 → the LOW side) to the current hist.

**Per-timeframe verdict:** `UP` = both `+` · `DOWN` = both `−` · `SPLIT` = one `+`/one `−` ·
`FLAT` = at least one `0`. For D1 only the UP / DOWN cases gate; everything else
(SPLIT or any `0`) is **MIXED** = no gate.

**H1 confirm:** `≥1 up` = at least one H1 sign `+`; `≥1 down` = at least one `−`;
`both up/down` = both.

## Stage 1 — base direction (H4 primary · H1 confirm)
| H4 | H1 | Base |
|---|---|---|
| UP (both +) | ≥1 up | **BUY** |
| UP | no up (both ≤ 0) | WAIT |
| DOWN (both −) | ≥1 down | **SELL** |
| DOWN | no down (both ≥ 0) | WAIT |
| SPLIT (one +, one −) | both up | **BUY** |
| SPLIT | both down | **SELL** |
| SPLIT | mixed / flat | WAIT |
| FLAT (any 0) | anything | WAIT |

## Stage 2 — D1 pivot side-gate
| D1 | Base = BUY | Base = SELL | Base = WAIT |
|---|---|---|---|
| **UP** (both +) | **BUY** | WAIT | WAIT |
| **DOWN** (both −) | WAIT | **SELL** | WAIT |
| **MIXED** (split / any 0) | **BUY** | **SELL** | WAIT |

Final decision = Stage 1 base, then filtered by Stage 2. (Invariant: D1 UP never sells,
D1 DOWN never buys.)

## Worked examples  `(D1 rsi,macd | H4 rsi,macd | H1 rsi,macd)`
| D1 | H4 | H1 | Path | Decision |
|---|---|---|---|---|
| +,+ | +,+ | +,− | base BUY (H4 UP, ≥1 H1 up); D1 UP allows | **BUY** |
| +,+ | +,− | +,+ | base BUY (H4 SPLIT, H1 both up); D1 UP allows | **BUY** |
| +,+ | −,− | any | base SELL/none (H4 DOWN); D1 UP blocks sells | WAIT |
| +,+ | +,+ | −,− | base none (H4 UP, H1 no up) | WAIT |
| +,0 | +,+ | +,0 | D1 MIXED (half); base BUY (H4 UP, ≥1 H1 up) | **BUY** |
| +,− | −,− | −,+ | D1 MIXED (split); base SELL (H4 DOWN, ≥1 H1 down) | **SELL** |
| 0,0 | +,− | +,+ | D1 MIXED; base BUY (H4 SPLIT, H1 both up) | **BUY** |
| −,− | −,− | −,+ | base SELL (H4 DOWN, ≥1 H1 down); D1 DOWN allows | **SELL** |
| −,− | +,− | −,− | base SELL (H4 SPLIT, H1 both down); D1 DOWN allows | **SELL** |
| −,− | −,− | +,+ | base none (H4 DOWN, H1 no down) | WAIT |

## Flowchart
```
signs: D1 · H4 · H1 (all latest-pivot slopes)
        │
   Stage 1  base direction (H4 primary, H1 confirm)
        ├─ H4 UP    & ≥1 H1 up     → base BUY
        ├─ H4 DOWN  & ≥1 H1 down   → base SELL
        ├─ H4 SPLIT & H1 both up   → base BUY
        ├─ H4 SPLIT & H1 both down → base SELL
        └─ else                    → base WAIT
        │
   Stage 2  D1 side-gate
        ├─ D1 UP   (both +) → BUY if base BUY  else WAIT
        ├─ D1 DOWN (both −) → SELL if base SELL else WAIT
        └─ D1 MIXED         → base passes through (BUY / SELL / WAIT)
```

## Notes
- **D1 is a pivot, not a regime** — it uses the same latest-pivot engine, OB/OS band
  (60/40) and MACD signal-side selection as H4/H1, on daily bars (`PEAK_LOOKBACK`=20,
  `PIVOT_WIDTH`=2). The old 55/45 RSI regime + MACD line-vs-0 (`D1_RSI_UP/DN`,
  `D1_MACD_MODE`) are **removed**.
- D1 only ever **removes** trades (gates the side); it never creates a direction the
  H4/H1 engine didn't already produce.
- Under a clearly-trending D1, an **H4-SPLIT with H1 fully aligned now trades** (e.g.
  D1 UP + H4 split + H1 both up → BUY) — the base engine decides, D1 just allows the side.
- Config knobs: `PEAK_LOOKBACK` (20), `PIVOT_WIDTH` (2), `RSI_PEAK_OB`/`RSI_PEAK_OS`
  (60/40) — shared by D1/H4/H1.
- **Slope force-close (retuned 2026-10-13):** fires when `>=1 D1 against (RSI preferred)
  AND H4 both against AND H1 both against` (opposite the open basket; SELL mirrors). D1
  just needs to lean; H4 and H1 must both fully reverse. Previously `H4 both + >=1 H1`
  (no D1) — it was booking losses by capitulating on a partial lower-TF turn. The `_h6`
  variant pairs this with the `+$unit` target; variant A pairs it with profit-protect
  (profit > min AND H1 both against — in-profit only, **unchanged**). The RSI DCA ladder
  is unchanged.
