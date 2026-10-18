# RSI+MACD Slope Entry — 4H × 1H × 15M Decision Table  (`_wd` / without-daily branch)

Entry **direction** (fresh entry only) is decided by `strategy._slope_direction()` from
**three** timeframes. **D1 does NOT enter the entry decision** — entry is purely the 4H/1H/15M
cascade (**4H primary / 1H confirm / 15M trigger**): 4H sets the bias, 1H confirms it, and 15M
is the finest tier that must also agree before anything fires. On `_exp`, **D1 is re-added for
the EXIT only** — a Daily-regime gate that modulates the force-close (see Exits). This document
mirrors the code exactly.

> This is the "without-daily" (`_wd`) base; on the D1-gated branches a D1 pivot filtered the
> entry SIDE — that stage is still gone here (D1 never gates entry). 15M was added in v2.1.0;
> the `_exp` fork re-introduces D1 purely as a force-close regime (`CHANGELOG.md` v2.3.0).

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

## Exits (open basket) — `_exp`/`_h` D1-regime force-close
Checked in order; closing has priority over adding. The `+$unit` target and the RSI DCA
ladder are **unchanged**; the slope force-close is **D1-regime-aware** (`_exp` v2.3.0; on
`_h`, v2.4.0, the sensitive path also requires a 1H confirm — see below).

1. **`+$unit` target** — basket profit > `close_threshold` (= unit) → **CLOSE** (reason `target`).
2. **Slope force-close (D1-regime).** First classify the Daily slope vs the open basket:
   - **D1 AGAINST** the basket = *both* D1 signs oppose it (BUY→both −, SELL→both +).
   - **Sensitive path (D1 against):** close as soon as **15M both AND ≥1 H1** oppose → **CLOSE**
     (reason `force_close_fast`). Counter-trend baskets are cut quickly — `_h` adds the `≥1 H1`
     confirm to filter pure-M15 noise (`_exp` was 15M-both only).
   - **Normal path (D1 with-trend OR neutral/mixed):** the v2.2.0 close —
     `≥1 4H (RSI pref.) AND 1H both AND 15M both` against → **CLOSE** (reason `force_close`).
     With or without a clear daily trend, pullbacks get room.
3. **RSI DCA ladder** — `BUY_MORE`/`SELL_MORE` at RSI 35/65, one tier per count
   (1→M1, 2→M5, 3→M15, 4→H1, 5→H4), Fibo lot sizing.
4. else **HOLD**.

**Why.** A basket aligned with the Daily trend is likely in a longer move, so small corrections
should be tolerated (hold the ladder) — only a Daily actively *against* the basket signals a
short-lived move that warrants a fast cut. D1 is deliberately **exit-only**: entry stays the
pure 4H/1H/15M table. A flat/mixed Daily is treated as "normal", not sensitive, so a ranging
Daily — common, since daily pivots are sparse — never puts baskets on a hair-trigger.

## Notes
- **Timeframes:** `SLOPE_TIMEFRAMES` is
  `['TIMEFRAME_M15', 'TIMEFRAME_H1', 'TIMEFRAME_H4', 'TIMEFRAME_D1']`. 15M/H1/H4 drive entry
  + the normal force-close; **D1 is used only by the force-close regime**. Unlike 15M, D1 is
  not fetched elsewhere, so it adds **+1 MT5 rates call per loop** (~500 daily bars).
- **D1 is exit-only:** `_slope_direction` (entry) never reads D1; it only appears in the
  force-close classifier and on the dashboard.
- **Dashboard:** the slope panel shows four rows (D1 / H4 / H1 / M15) and eight pivot
  mini-charts (RSI + MACD-hist per timeframe).
- Exits are otherwise unchanged: `_h6` variant = `+$unit` target + the D1-regime force-close above.
