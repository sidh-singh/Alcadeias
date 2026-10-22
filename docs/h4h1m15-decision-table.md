# RSI+MACD Slope Entry — 4H × 1H × 15M Decision Table  (`_wd` / without-daily branch)

Entry **direction** (fresh entry only) is decided by `strategy._slope_direction()` from
**three** timeframes. **D1 does NOT enter the entry decision** — entry is purely the 4H/1H/15M
cascade (**4H primary / 1H confirm / 15M trigger**): 4H sets the bias, 1H confirms it, and 15M
is the finest tier that must also agree before anything fires. On `_exp`, **D1 is re-added for
the EXIT only** — a Daily-regime gate that modulates the hard-stop (see Exits). This document
mirrors the code exactly.

> This is the "without-daily" (`_wd`) base; on the D1-gated branches a D1 pivot filtered the
> entry SIDE — that stage is still gone here (D1 never gates entry). 15M was added in v2.1.0;
> the `_exp` fork re-introduces D1 purely as a force-close regime (`CHANGELOG.md` v2.3.0).
>
> This is the **variant-A** (slope-exit) branch pair (`rsimacd_btcusd1_wd` /
> `rsimacd_xauusd1_wd`): exits are profit-protect + hard-stop. The `_h6` variant-B pair
> uses a `+$unit` target + the slope force-close instead — same entry table, different exit.

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

## Exits (open basket) — variant A (slope exits + ladder), `_h` D1-regime hard-stop (+ D1-split cascade)
Slope exits are checked **FIRST**, then the RSI DCA ladder (closing has priority over
adding). The RSI DCA ladder is unchanged. Both slope exits are **D1-regime-aware**: the
**hard-stop** (`_exp` v2.3.0 → `_h` v2.4.0 → v2.5.0 D1-split cascade) and now **profit-protect**
(**v2.6.0** — D1-graded reversal + a lot-dynamic profit threshold). For a BUY basket the threat
is a DOWN move (shown); SELL mirrors (threat = UP move).

1. **Profit-protect (D1-regime, v2.6.0).** Books when the basket is in profit by at least
   `times × PROFIT_PROTECT_USD_PER_UNIT` (threshold **scales with the unit / entry lot** — lot
   0.01→$1, 0.05→$5) **AND** a momentum reversal fires, whose strength scales with the Daily:
   | D1 vs position | reversal to book | reason | why |
   |---|---|---|---|
   | **WITH** (both up) | `1H both − AND 15M both −` | `pp_trend` | trend-aligned winner → wait a full reversal, let it run |
   | **split / flat** | `1H both − AND ≥1 15M −` | `profit_protect` | no daily opinion → the prior rule |
   | **AGAINST** (both down) | `≥1 1H − AND ≥1 15M −` | `pp_counter` | counter-trend profit → grab it on a lighter turn |

   Checked **before** the hard-stop, so in profit a book always wins over a capitulation.
2. **Hard stop (D1-regime).** Classify the Daily slope vs the basket (up=supportive, down=against,
   split=RSI/MACD disagree, flat=a 0):
   - **D1 AGAINST** (both oppose) → **sensitive**: `15M both − AND ≥1 1H −` → **CLOSE**
     (reason `force_close_fast`). *(Unchanged.)*
   - **D1 WITH-trend (both up) OR FLAT** → **normal**: `≥1 4H − AND 1H both − AND 15M both −`
     → **CLOSE** (reason `force_close`). *(Unchanged.)*
   - **D1 SPLIT** → **cascade 4H → H1 → floor.** First decisive TF sets the band; supportive =
     one notch stricter (wait), descending deeper = more sensitive. Ladder (all *against*):
     **C3** `H1 RSI AND 15M both` · **C2** `15M both` · **C1** `15M RSI` (floor):

     | first decisive TF | verdict | close | reason |
     |---|---|---|---|
     | 4H | supportive | C3 | `fc_split_4h_sup` |
     | 4H | against | C2 | `fc_split_4h_opp` |
     | H1 (4H indecisive) | supportive | C2 | `fc_split_h1_sup` |
     | H1 (4H indecisive) | against | C1 | `fc_split_h1_opp` |
     | none (4H & H1 indecisive) | — | C1 (floor) | `fc_split_floor` |

     ("indecisive" = split **or** flat.)
3. **RSI DCA ladder** — `BUY_MORE`/`SELL_MORE` at RSI 35/65, one tier per count
   (1→M1, 2→M5, 3→M15, 4→H1, 5→H4), Fibo lot sizing (max 6 positions).
4. else **HOLD**.

**Why.** Standard multi-timeframe exit logic: hold *with* the higher-TF trend, tighten *against*
it. A basket backed by the Daily (or the first decisive TF in a split cascade) gets more
confirmation before closing (wait); one fighting it is cut faster. D1 is **exit-only** — entry
stays the pure 4H/1H/15M table. Note: with the floor at `15M RSI`, a fully-split/choppy Daily can
cut *faster* than a cleanly-against Daily (`15M both + ≥1 1H`) — intentional (chop → quick exits).

## Notes
- **Timeframes:** `SLOPE_TIMEFRAMES` is
  `['TIMEFRAME_M15', 'TIMEFRAME_H1', 'TIMEFRAME_H4', 'TIMEFRAME_D1']`. 15M/H1/H4 drive entry
  + the normal hard-stop; **D1 is used only by the hard-stop regime**. Unlike 15M, D1 is not
  fetched elsewhere, so it adds **+1 MT5 rates call per loop** (~500 daily bars).
- **D1 is exit-only:** `_slope_direction` (entry) never reads D1; it only appears in the
  hard-stop classifier and on the dashboard.
- **Dashboard:** the slope panel shows four rows (D1 / H4 / H1 / M15) and eight pivot
  mini-charts (RSI + MACD-hist per timeframe).
