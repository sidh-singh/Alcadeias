# RSI+MACD Slope Entry — 4H × 1H × 15M Decision Table  (`_wd` / without-daily branch)

Entry **direction** (fresh entry only) is decided by `strategy._slope_direction()` from
**three** timeframes. **D1 has been removed on this branch** — there is no daily side-gate.
The cascade is **4H primary / 1H confirm / 15M trigger**: 4H sets the bias, 1H confirms it,
and 15M is the finest tier that must also agree before anything fires. The force-close exit
uses the same three-tier agreement (in the opposite direction). This document mirrors the
code exactly.

> This is the "without-daily" (`_wd`) A/B counterpart of the D1-gated branches. On those,
> a D1 pivot additionally filtered the side; here that whole stage is gone. 15M was added
> on top of the former 4H×1H table (see git history / `CHANGELOG.md` v2.1.0).

## Inputs
Each timeframe yields **two pivot-slope signs** (RSI, MACD-histogram), each `+ / − / 0`:

- **RSI** sign: slope from the latest OB/OS-band pivot (HIGH only if RSI ≥ `RSI_PEAK_OB`
  = 60, LOW only if RSI ≤ `RSI_PEAK_OS` = 40) to the current RSI.
- **MACD** sign: slope from the latest MACD-histogram pivot (side chosen by the MACD
  **signal line**: signal > 0 → read the HIGH side, < 0 → the LOW side) to the current hist.

All three timeframes (15M, 1H, 4H) use **identical** pivot params (`PEAK_LOOKBACK` = 20,
`PIVOT_WIDTH` = 2, `RSI_PEAK_OB`/`RSI_PEAK_OS` = 60/40).

**Per-timeframe verdict:** `UP` = both `+` · `DOWN` = both `−` · `SPLIT` = one `+`/one `−` ·
`FLAT` = at least one `0`.

**Confirm shorthand:** `≥1 up` = at least one of that TF's two signs is `+`; `≥1 down` = at
least one `−`; `both up/down` = both signs agree. (A `−` never counts toward "up", so a TF
with one `−` and one `0` is "no up".)

## Decision table (4H primary · 1H confirm · 15M trigger)
| 4H | 1H | 15M | Decision |
|---|---|---|---|
| UP (both +) | ≥1 up | ≥1 up | **BUY** |
| UP (both +) | ≥1 up | no up | WAIT |
| UP (both +) | no up | — | WAIT |
| DOWN (both −) | ≥1 down | ≥1 down | **SELL** |
| DOWN (both −) | ≥1 down | no down | WAIT |
| DOWN (both −) | no down | — | WAIT |
| SPLIT (one +, one −) | both up | ≥1 up | **BUY** |
| SPLIT (one +, one −) | both down | ≥1 down | **SELL** |
| SPLIT (one +, one −) | mixed / not-both | — | WAIT |
| FLAT (any 0 on 4H) | anything | anything | WAIT |

## Worked examples  `(4H rsi,macd | 1H rsi,macd | 15M rsi,macd)`
| 4H | 1H | 15M | Path | Decision |
|---|---|---|---|---|
| +,+ | +,− | −,+ | 4H UP, ≥1 1H up, ≥1 15M up | **BUY** |
| +,+ | +,− | −,− | 4H UP, ≥1 1H up, 15M no up | WAIT |
| +,+ | −,− | +,+ | 4H UP, 1H no up | WAIT |
| −,− | −,+ | +,− | 4H DOWN, ≥1 1H down, ≥1 15M down | **SELL** |
| −,− | −,+ | +,+ | 4H DOWN, ≥1 1H down, 15M no down | WAIT |
| +,− | +,+ | +,− | 4H SPLIT, 1H both up, ≥1 15M up | **BUY** |
| +,− | +,+ | −,− | 4H SPLIT, 1H both up, 15M no up | WAIT |
| −,+ | −,− | −,− | 4H SPLIT, 1H both down, ≥1 15M down | **SELL** |
| +,− | +,− | −,+ | 4H SPLIT, 1H split | WAIT |
| +,0 | +,+ | +,+ | 4H FLAT (a 0) | WAIT |

## Flowchart
```
signs: 4H · 1H · 15M (latest-pivot slopes; D1 removed)
        │
        ├─ 4H UP    & ≥1 1H up   & ≥1 15M up   → BUY
        ├─ 4H DOWN  & ≥1 1H down & ≥1 15M down → SELL
        ├─ 4H SPLIT & 1H both up & ≥1 15M up   → BUY
        ├─ 4H SPLIT & 1H both dn & ≥1 15M down → SELL
        └─ else                                → WAIT
```

## Exits (open basket)
Checked in order; closing has priority over adding. Only the force-close tier changed (it
gained the 15M gate); the `+$unit` target and the RSI DCA ladder are unchanged.

1. **`+$unit` target** — basket profit > `close_threshold` (= unit) → **CLOSE** (reason `target`).
2. **Slope force-close** — the three-tier reversal, same shape as entry but opposite the basket:
   - BUY basket → `4H both − AND ≥1 1H − AND ≥1 15M −` → **CLOSE** (reason `force_close`).
   - SELL basket → `4H both + AND ≥1 1H + AND ≥1 15M +` → **CLOSE**.
3. **RSI DCA ladder** — `BUY_MORE`/`SELL_MORE` at RSI 35/65, one tier per count
   (1→M1, 2→M5, 3→M15, 4→H1, 5→H4), Fibo lot sizing.
4. else **HOLD**.

Adding the 15M gate makes the force-close slightly **slower** (all three tiers must align
against the basket), which is the deliberate, owner-approved choice — consistent with the
rolled-back early-cut history (v1.1.0 lost money cutting open baskets early; v1.3.0 reverted
to holding till the target).

## Notes
- **Timeframes:** `SLOPE_TIMEFRAMES` is `['TIMEFRAME_M15', 'TIMEFRAME_H1', 'TIMEFRAME_H4']`.
  15M RSI is already fetched for the dashboard / DCA ladder, so adding its slopes needs **no
  extra MT5 call** — the app loop computes a slope for every entry in `SLOPE_TIMEFRAMES`.
- **D1 removed:** no D1 fetch, no D1 slope, no D1 dashboard row/graphs; `_slope_direction`
  has no D1 stage.
- **Dashboard:** the slope panel shows three rows (H4 / H1 / M15) and six pivot mini-charts
  (RSI + MACD-hist per timeframe).
- Exits are otherwise unchanged: `_h6` variant = `+$unit` target + the slope force-close above.
