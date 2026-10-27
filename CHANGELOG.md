# Changelog

All notable changes to the Alcadeias trading bot are recorded here, newest first.
Each version lists **exactly what changed per file** and a **Rollback** section so any
version can be reversed cleanly.

Versioning is feature-based (`vMAJOR.MINOR.PATCH`). Each entry names the git
**baseline commit** it was applied on top of, so you can always return to a known state.

**Maintenance policy (every change, no exceptions):** every change — however small — is
recorded here with per-file detail (down to the small stuff), committed together with its
code, and propagated to **all 20 live-money fleet branches** in the same change
(cherry-pick; rebase onto `origin/<branch>` for any branch behind so remote-only
credential/symbol commits are preserved; never force-push). Fleet:
`dev_btcusd1_v2`…`dev_btcusd10_v2` (BTCUSDm) and `dev_xauusd1_v2`…`dev_xauusd10_v2`
(XAUUSDm).

---

## [v3.5.0] — 2026-10-27 — Remove the regime ENTIRELY — strategy is now score-only [_exp_h]

**Branches:** all 4 `_h`. **Files touched:** `constants.py`, `strategy.py`, `app.py`, `dashboard.py`,
`docs/weighted-regime-redesign.md` (+ this `CHANGELOG.md`).

**Why.** Entry (v3.4.0) and the ladder (v3.4.2) were already regime-free; the regime still scaled the
two EXITS. Owner: "remove all regime calculation and functionality — regime and slope will not work
together — keep the weightage (score)." So the level-based regime is fully deleted; the two exits
collapse to single score thresholds. One engine remains: the weighted slope score.

### Behaviour change — exits become single-threshold score-only
- **Force-close:** `buy_fc = score <= -FORCE_CLOSE_S` / `sell_fc = score >= +FORCE_CLOSE_S` (single
  `FORCE_CLOSE_S = 8`, replaces the regime trio 12/8/4). Reason `force_close` (was `fc_bull/neutral/bear`).
- **Profit-book (variant A):** `buy_pp = in-profit AND score <= -BOOK_S` / `sell_pp = … >= +BOOK_S`
  (single `BOOK_S = 4`, replaces 6/4/2). Reason `book` (was `book_bull/neutral/bear`). Still checked
  before the force-close.
- **Net threshold ladder for a long:** open `S≥+6` · ladder-add blocked `S≤−6` · book (in profit)
  `S≤−4` · force-close `S≤−8`. (The with/against-tide asymmetry on the exits is gone — one fixed line.)

### Removed (regime machinery)
- `strategy.py`: `_regime_tf`, `_regime_combine`, `_macd_line`; the `regime`/`d1_regime`/`h4_regime`/
  `rsi_d1` computation; the `regime*` fields from `analysis_data`.
- `constants.py`: `REGIME_RSI_BULL/BEAR`; the `FORCE_CLOSE_S_*` and `BOOK_S_*` trios (→ single
  `FORCE_CLOSE_S` / `BOOK_S`). Regime section rewritten as "weighted-score gates (no regime)".
- `app.py`: `slopes[tf]['macd_line']` (only the regime read it) — removed.
- `dashboard.py`: the `TIDE` badge (`_regime_badge` + its call + reads) — removed; the SCORE meter stays.
- `docs`: status rewritten to "score-only"; §4–§6 marked historical.

### Unchanged
The score formula, entry (`_entry_direction`), the ladder gate (`buy_add_ok`/`sell_add_ok`), RSI tiers
+ Fibo sizing, re-entry cooldown, the h6 `+$unit` target, and the dashboard SCORE threshold-meter.

### Rollback
`git revert` the Step v3.5.0 commit (restores the regime helpers, the regime-scaled exits, the
constants trios, `macd_line`, and the TIDE badge).

---

## [v3.4.2] — 2026-10-27 — DCA ladder: remove the regime gate too (adds open on the score alone) [_exp_h]

**Branches:** all 4 `_h`. **Files touched:** `constants.py`, `strategy.py` (+ this `CHANGELOG.md`).

**Why.** Follow-through on v3.4.0. The DCA ladder add (the RSI-ladder's *next* position) was still
gated by the regime — `buy_add_ok = (regime != BEAR) and (score > -REGIME_LADDER_S)` — so a BEAR tide
blocked averaging in regardless of RSI/score, the same lagging-regime veto we removed from fresh
entry. An RSI-ladder add is an OPENING, so it now opens on the weighted score alone.

### Behaviour change — ladder adds only
- `buy_add_ok = score > -LADDER_S` ; `sell_add_ok = score < LADDER_S` (the `regime !=` conjunct
  dropped). `REGIME_LADDER_S` renamed to **`LADDER_S`** (= 6; no regime involved now).
- A BEAR tide no longer blocks a BUY add; a BULL tide no longer blocks a SELL add. **The score guard
  stays:** an add is still blocked when the score is strongly adverse (`≤ -LADDER_S`), which still
  catches the 2026-10 "average down into a trend" case (it scored −14). And the **force-close stays
  regime-aware**, so a counter-tide basket is still protected / cut.
- **Net:** the regime now governs ONLY the exits (force-close + variant-A profit-book); all OPENING
  (fresh entry + ladder adds) is score-only.

### Rollback
Restore `buy_add_ok`/`sell_add_ok` to `(regime != 'BEAR'/'BULL') and (...)` and rename `LADDER_S`
back to `REGIME_LADDER_S`.

---

## [v3.4.1] — 2026-10-27 — Dashboard: score threshold-meter (BUY/SELL lines + no-open band) [_exp_h]

**Branches:** all 4 `_h` (dashboard.py only — a display change, no trading-behaviour change).
**Files touched:** `dashboard.py` (+ this `CHANGELOG.md`).

**Why / what.** Owner wanted to see at a glance whether the MTF score will open a position. The score
tile (`_score_gauge`) is now a diverging −20…+20 **threshold-meter**: BUY (+`ENTRY_S`) and SELL
(−`ENTRY_S`) threshold lines, a grey **no-open band** spanning −`ENTRY_S`…+`ENTRY_S`, the fill coloured
by zone (green BUY / grey within / red SELL) with the current-score marker (surface-ringed) on top, a
labelled scale (−20 … −`ENTRY_S` … 0 … +`ENTRY_S` … +20), a zone chip ("BUY ZONE · opens" / "SELL ZONE ·
opens" / "WAIT · within ±N") and a hover tooltip. Reads the live `ENTRY_S` (now imported into
`dashboard.py`) so the lines move if the threshold is tuned. Colour is reinforced by position, the
signed value and the chip (never colour-alone).

**Rollback.** Revert `dashboard.py` `_score_gauge` to the previous plain-fill gauge.

---

## [v3.4.0] — 2026-10-27 — Entry: remove the regime gate, open on the weighted score alone [_exp_h]

**Baseline:** the v3.3.1 HEAD (variant A) / v3.2.1 HEAD (h6 pair). Applies to **all 4 `_h` branches**
(entry is byte-identical across them); versioned **v3.4.0 on all 4** (re-unifies the pair lineages —
variant A 3.3.1→3.4.0, h6 pair 3.2.1→3.4.0, which skips the variant-A-only 3.3.0 profit-book line).
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py` (+ this `CHANGELOG.md`).

**Why.** Owner observed a trade that should have opened but didn't: MTF **score +12** with D1/H4/H1
slopes all rising, yet the **regime/tide read BEAR** (level-based = lagging) so the Step-5 entry gate
blocked the long — BEAR permits only SELLs at *any* score. Lowering the threshold (v3.3.1/v3.2.1) can't
fix this: in BEAR a long is blocked regardless of score. The slope (leading) and a lagging level
regime shouldn't *both* veto an open. Fix: **entry opens on the weighted slope score alone; the regime
no longer gates opening.** (The regime still governs the exits — force-close, ladder gate, and the
variant-A profit-book — so a slope entry taken against the tide is still protected: the ladder won't
average down and the force-close cuts it faster.)

### Behaviour change — entry only
- `_entry_direction(score)` (regime arg dropped): **BUY** if `score ≥ ENTRY_S`, **SELL** if
  `score ≤ -ENTRY_S`, else WAIT. No BULL/NEUTRAL/BEAR gate on opening.
- `constants.py`: the two regime-gated thresholds `ENTRY_S_WITH`/`ENTRY_S_NEUTRAL` (4/6) are replaced
  by a single **`ENTRY_S = 6`** (there is no entry tide to distinguish "with" vs "neutral" anymore).
  6 = the old no-tide value (a clear multi-TF slope, e.g. D1-both or H4-both); still far easier than
  the original 8/12, and the owner's +12 case opens instantly. Lower it for more eager entries.
- **Unchanged:** the score formula, the regime computation + TIDE badge, force-close (Step 4), ladder
  gate (Step 3), profit-book (Step 6, var A), RSI tiers, re-entry cooldown, and the dashboard
  (headline still shows the live `entry_direction`, now score-only; `_slope_direction` structural read
  kept for comparison).

### Rollback
Restore `_entry_direction(regime, score)` with the BULL/NEUTRAL/BEAR gate and the two constants
`ENTRY_S_WITH`/`ENTRY_S_NEUTRAL` (revert this commit).

---

## [v3.3.1] — 2026-10-26 — Lower the entry score thresholds (entry too slow to start) [_exp_h]

**Baseline:** the v3.3.0 HEAD (variant A) / v3.2.0 HEAD (h6 pair). Applies to **all 4 `_h` branches**
(entry is identical across them); on the h6/variant-B pair this same change is logged as **v3.2.1**.
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py` (+ this `CHANGELOG.md`).

**Why.** Owner reported ~2 days with no trade started: the Daily/H4 **slope** had turned bullish but
the level-based **regime** still read bearish/neutral, so the Step-5 entry gate held off. First,
cheapest fix — keep the regime, just lower the score needed to open (watch 1–2 days, then decide on
removing the regime). Owner authorized down to 4 and left the exact value to me.

### Behaviour change — entry thresholds only (no logic change)
- `constants.py`: `ENTRY_S_WITH` **8 → 4**, `ENTRY_S_NEUTRAL` **12 → 6**. A BUY now opens when the
  regime is BULL and `score ≥ 4`, or NEUTRAL and `score ≥ 6` (SELL mirrors). `WITH < NEUTRAL` is
  preserved (with the tide needs less confirmation than without). Everything else — the regime gate
  itself, the score formula, force-close, ladder gate, profit-book (var A), RSI tiers, cooldown — is
  unchanged.

> **⚠ Known limitation:** this helps only when the regime is **BULL or NEUTRAL**. If the regime is
> **BEAR**, a new long is still blocked at *any* score (BEAR permits only SELLs) — lowering the
> threshold cannot start a long there. If no trade starts within 1–2 days, the regime is the gate and
> removing it from entry (keep slope only) is the next step.

### Rollback
`constants.py`: restore `ENTRY_S_WITH = 8` / `ENTRY_S_NEUTRAL = 12`.

---

## [v3.3.0] — 2026-10-23 — Weighted-score + regime redesign, Step 6: profit-book via score+regime (LIVE, variant A) [_exp_h]

**Baseline:** the v3.2.0 (Step-5 entry) HEAD — `8bf5790` (btcusd1), `0a8f4b1` (xauusd1).
**Branches:** the **variant-A `_h`** pair ONLY — `rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`.
(The h6/variant-B `_h` pair has no `profit_protect` — it books with the `+$unit` target — so it is
NOT touched and stays at v3.2.0.)
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py`, `docs/weighted-regime-redesign.md` (+ this `CHANGELOG.md`).

**Why.** Final step of the redesign: variant A's profit-book (its only profit exit) moves onto the
same score+regime brain as the ladder/exit/entry. Replaces the v2.6.0 D1-book (which picked
strict/loose/current from the D1 slope signs + an H1/15M reversal). Now: in profit, book when the
score reverses past a regime-set line — let a with-trend winner run, grab a counter-trend one fast.

### Behaviour change — profit-book only (BUY shown; SELL mirrors; checked BEFORE force-close)
Book once `buy_profit > times × PROFIT_PROTECT_USD_PER_UNIT` (the v2.6.0 lot-dynamic buffer, kept) AND:
| tide (regime) | book a BUY when | reason |
|---|---|---|
| **BULL** (with the long — let it run) | `score ≤ -BOOK_S_WITH` (−6) | `book_bull` |
| **NEUTRAL** | `score ≤ -BOOK_S_NEUTRAL` (−4) | `book_neutral` |
| **BEAR** (against the long — grab it) | `score ≤ -BOOK_S_AGAINST` (−2) | `book_bear` |

- New consts `BOOK_S_WITH=6` / `_NEUTRAL=4` / `_AGAINST=2` (tunable). Book thresholds are tighter
  than the force-close (12/8/4), so in profit the basket books on a smaller reversal than it would
  capitulate on — and the book is still checked first, so a winner is never turned into a loss-cut.
- **Removed:** the v2.6.0 D1-book table (`pp_trend` / `pp_counter` / `profit_protect` reasons, the
  D1-slope-sign strict/loose/current branches). The now-dead `m15_both_dn` / `m15_both_up` locals
  (left over in the force-close block for the old book) are deleted.
- **Unchanged:** the force-close (Step 4), ladder gate (Step 3), entry (Step 5), RSI tiers + Fibo.

### Per-file
- `constants.py`: `BOOK_S_WITH/_NEUTRAL/_AGAINST`; regime-section note → "redesign complete".
- `strategy.py`: import the three consts; replace the D1-book precompute with the score+regime book
  (`buy_pp`/`sell_pp` + `book_<regime>` reasons); drop the dead `m15_both_*`; docstring updated.
- `docs/weighted-regime-redesign.md`: status → COMPLETE; §8 Step 6 marked done.

**Rollback.** `git revert` the Step-6 commit to restore the v2.6.0 D1-book. To only loosen/tighten:
adjust `BOOK_S_*` (lower = book sooner). The lot-dynamic buffer (`PROFIT_PROTECT_USD_PER_UNIT`) is
unchanged, so the "only book in real profit" guarantee holds.

---

## [v3.2.0] — 2026-10-23 — Weighted-score + regime redesign, Step 5: entry via score+regime (LIVE) [_exp_h]

**Baseline:** the v3.1.0 (Step-4 force-close) HEAD per branch — `30aca0e` (btcusd1), `a067079`
(xauusd1), `cf36ebb` (h6_btcusd1), `671bda6` (h6_xauusd1).
**Branches:** all 4 `_h` — `rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`,
`rsimacd_h6_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h`.
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py`, `dashboard.py`, `docs/weighted-regime-redesign.md` (+ this `CHANGELOG.md`).

**Why.** Puts *opening* on the same tide+waves footing as the exit/ladder. The structural entry
(`_slope_direction`: 4H both + ≥1 H1 + ≥1 M15) opened on lower-TF alignment with no trend
context. Entry now opens only **with the tide**, once the **score** confirms — so a new trade is
never taken against the daily/4H bias. ⚠ This re-introduces D1/H4 into the entry (today the
structural entry was slope-only on 4H/1H/15M), via both the score (D1/H4 weighted) and the regime.

### Behaviour change — fresh entry only (flat → open; BUY shown, SELL mirrors)
| tide (regime) | open a BUY when | open a SELL when |
|---|---|---|
| **BULL** | `score ≥ ENTRY_S_WITH` (+8) | **blocked** (no short vs bull tide) |
| **NEUTRAL** | `score ≥ ENTRY_S_NEUTRAL` (+12) | `score ≤ -ENTRY_S_NEUTRAL` (−12) |
| **BEAR** | **blocked** (no long vs bear tide) | `score ≤ -ENTRY_S_WITH` (−8) |

- New consts `ENTRY_S_WITH=8` / `ENTRY_S_NEUTRAL=12` (with the tide = less confirmation; no tide =
  need more; against the tide = never open). Still single-position and re-entry-cooldown-gated.
- `_slope_direction` (the structural 4H/1H/15M read) is **retained** but no longer drives entry —
  it is exposed as `analysis_data['slope_direction']` for the dashboard "structural" comparison,
  while the live decision is `entry_direction`.

### Per-file
- `constants.py`: `ENTRY_S_WITH` / `ENTRY_S_NEUTRAL`; regime-section note updated (entry now LIVE;
  only the variant-A profit-book is still shadow).
- `strategy.py`: import the two consts; new `_entry_direction(regime, score)` helper; compute
  `entry_direction`; the flat branch opens on it; `analysis_data['entry_direction']` added
  (`slope_direction` kept); docstring `Flat:` rewritten; score/regime comments refreshed.
- `dashboard.py`: the slope-panel headline now shows the live `entry_direction` (fallback
  `slope_direction`); when they differ, the structural read is shown in the status line.
- `docs/weighted-regime-redesign.md`: status header + §8 Step 5 marked done.

**Note — §7 open knob not taken.** Shipped the clean §6 rule *without* the optional "15M-not-against"
hard gate on top of the score. If demo shows poorly-timed opens (entering into a 15M reversal), that
gate is the documented tightening.

**Rollback.** `git revert` the Step-5 commit to restore the structural `_slope_direction` entry.
To only loosen/disable the new gate: lower `ENTRY_S_*` (more trades) or raise them very high (the
bot stops opening). The structural helper is still present, so reverting is clean.

---

## [v3.1.0] — 2026-10-23 — Weighted-score + regime redesign, Step 4: force-close via score+regime (LIVE) [_exp_h]

**Baseline:** the v3.0.0 (Step-3 ladder-gate) HEAD per branch — `47b147d` (btcusd1), `6f0fddd`
(xauusd1), `df578ba` (h6_btcusd1), `38bfbb9` (h6_xauusd1).
**Branches:** all 4 `_h` — `rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`,
`rsimacd_h6_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h`.
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py`, `docs/weighted-regime-redesign.md` (+ this `CHANGELOG.md`).

**Why.** Second half of the ~$1000-loss fix and a large simplification. The v2.x force-close was a
D1-regime **cascade** (sensitive / normal / D1-split 4H→H1→floor, reasons `force_close_fast` /
`force_close` / `fc_split_*`) hard-gated on noisy M15/H1 slope *signs* — the exact structure that
failed to cut the loss. It is replaced by one rule on the weighted **score** crossing a
**regime-set** line: close when the score has moved far enough against the basket, with the
distance scaled by the tide (give a with-trend winner room, cut a counter-trend loser fast).

### Behaviour change — force-close only (BUY shown; SELL mirrors: flip score, swap BULL↔BEAR)
| tide (regime) | close a BUY when | reason |
|---|---|---|
| **BULL** (with the long) | `score ≤ -FORCE_CLOSE_S_WITH` (−12) | `fc_bull` |
| **NEUTRAL** | `score ≤ -FORCE_CLOSE_S_NEUTRAL` (−8) | `fc_neutral` |
| **BEAR** (against the long) | `score ≤ -FORCE_CLOSE_S_AGAINST` (−4) | `fc_bear` |

- New consts `FORCE_CLOSE_S_WITH=12` / `_NEUTRAL=8` / `_AGAINST=4` (tunable). The score is
  `S = 4·D1 + 3·H4 + 2·H1 + 1·M15` (Step 1); the regime is the D1-leads-H4 tide (Step 2).
- **Removed:** the entire D1 cascade — `force_close_fast`, the D1-split `fc_split_*` ladder, the
  M15-both / ≥1-H1 sign gates. (`m15_both_dn` / `m15_both_up` are retained only because the
  variant-A `profit_protect` still uses them.)
- **Unchanged / still checked first:** variant-A `profit_protect` (in profit, a book beats a
  capitulation), the h6 `+$unit` target, the Step-3 ladder gate, entry (`_slope_direction`), the
  RSI tiers + Fibo sizing.

### Per-file
- `constants.py`: `FORCE_CLOSE_S_WITH/_NEUTRAL/_AGAINST`; regime-section note updated (force-close
  now LIVE too).
- `strategy.py`: import the three consts; replace the force-close cascade precompute with the
  score+regime close (per-side threshold by regime; `buy_fc`/`sell_fc` + `fc_<regime>` reasons);
  docstring exit section rewritten; obsolete build-phase labels dropped.
- `docs/weighted-regime-redesign.md`: status header + §8 Step 4 marked done.

**Rollback.** `git revert` the Step-4 commit to restore the v2.x cascade. To only widen/disable
the new close, raise `FORCE_CLOSE_S_*` (e.g. all `9999` → the basket never force-closes; exits
then rest on `profit_protect` (var A) / the `+$unit` target (h6) alone).

---

## [v3.0.0] — 2026-10-23 — Weighted-score + regime redesign, Step 3: DCA ladder gate (LIVE) [_exp_h]

**Baseline:** the Step-2 (shadow regime) HEAD per branch — `225a4e7` (btcusd1), `3542c67`
(xauusd1), `405c82c` (h6_btcusd1), `692e8ce` (h6_xauusd1).
**Branches:** all 4 `_h` — `rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`,
`rsimacd_h6_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h`.
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py`, `docs/weighted-regime-redesign.md` (+ this `CHANGELOG.md`).

**Why.** First behaviour change of the weighted-score + regime redesign (see
`docs/weighted-regime-redesign.md`); opens the v3.x line. A ~$1000 demo loss came half from the
DCA ladder averaging *down into* a bear trend — the adds had no higher-TF gate. This stops that:
the ladder may add only when the big-TF **tide** (regime) is not against the position AND the
weighted slope **score** is not strongly adverse. The score + regime shipped as shadow in
Steps 1–2 (telemetry only); this is the first decision wired to them.

### Behaviour change — DCA ladder adds only (BUY shown; SELL mirrors)
- **Gate.** A BUY add (`BUY_MORE`) fires only when `regime != BEAR` AND `score > -REGIME_LADDER_S`
  (new const, default **6**); a SELL add (`SELL_MORE`) only when `regime != BULL` AND
  `score < +REGIME_LADDER_S`. When blocked the basket **HOLDs** at its current size (no add).

  | tide vs position | ladder add |
  |---|---|
  | with (BULL for a long / BEAR for a short) | allowed if score not strongly adverse |
  | NEUTRAL | allowed if score not strongly adverse |
  | against (BEAR for a long / BULL for a short) | **blocked** |

- **Regime (tide):** per big-TF (D1/H4) BULL/BEAR/NEUTRAL from RSI level (vs 55/45) + MACD-line
  sign, combined D1-leads-H4 (shipped Step 2). **Score (waves):** `S = 4·D1 + 3·H4 + 2·H1 + 1·M15`
  (shipped Step 1).
- **Unchanged:** fresh entry (`_slope_direction`, 4H/1H/15M), the force-close cascade
  (`force_close` / `force_close_fast` / `fc_split_*`), the h6 `+$unit` target, variant-A
  `profit_protect`, the RSI tiers (35/65, count→TF map) and Fibo lot sizing. The gate only
  decides *whether* a tier add is allowed; it never touches the exits.

### Per-file
- `constants.py`: new `REGIME_LADDER_S = 6`; regime section header/note updated (no longer pure
  shadow — the ladder now reads the regime + score).
- `strategy.py`: import `REGIME_LADDER_S`; precompute `buy_add_ok` / `sell_add_ok` after the
  regime; wrap the 5-tier BUY and SELL ladders under `elif buy_add_ok:` / `elif sell_add_ok:`;
  refreshed the score/regime comments.
- `docs/weighted-regime-redesign.md`: status header + §8 Step 3 marked done.

**Rollback.** Full: `git revert` the Step-3 commit (restores the ungated always-add ladder).
Soften only the score half: raise `REGIME_LADDER_S` (e.g. `9999`) so the score never binds — the
regime BEAR/BULL block has no separate off-knob, so revert for that.

---

## [v2.6.0] — 2026-10-23 — Profit-protect: D1-regime book + lot-dynamic threshold (variant A) [_exp_h]

**Baseline:** the v2.5.0 HEAD per branch.
**Branches:** the **variant-A `_h`** pair ONLY — `rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`.
(The h6/variant-B `_h` pair has no `profit_protect` — it uses a `+$unit` target — so it is NOT touched.)
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py`, `docs/h4h1m15-decision-table.md` (+ this `CHANGELOG.md`).

**Why.** `profit_protect` is variant A's *only* profit-booking exit (no `+$unit` target). Two
upgrades: (1) its USD threshold was a flat constant (`0.0`) that didn't scale with position size;
(2) it booked on a single fixed reversal regardless of the Daily trend. Both now scale with context.

### Behaviour change — `profit_protect` only (BUY shown; SELL mirrors)
- **Lot-dynamic threshold.** `profit_protect_min = times × PROFIT_PROTECT_USD_PER_UNIT` (new const,
  default **1.0**). `times` is the effective unit (= balance tier); entry lot = `times × mtqty`
  (mtqty 0.01), so the buffer is **$1 per unit** — lot 0.01→$1, 0.05→$5. Replaces the flat
  `PROFIT_PROTECT_MIN_USD` (0.0).
- **D1-regime reversal strength** (book only once `buy_profit > profit_protect_min` AND):
  | D1 vs long | reversal to book | reason |
  |---|---|---|
  | WITH (both up) | `H1 both− AND 15M both−` (strict — let it run) | `pp_trend` |
  | split / flat | `H1 both− AND ≥1 15M−` (the prior rule) | `profit_protect` |
  | AGAINST (both down) | `≥1 H1− AND ≥1 15M−` (loose — grab it) | `pp_counter` |

  Principle: let a with-trend winner run (full reversal needed), grab a counter-trend winner fast.
  Still checked **before** the hard-stop, so in profit a book wins over a capitulation.

**Unchanged:** the hard-stop (D1-regime cascade, v2.5.0), the RSI DCA ladder, entry, and (h6 pair)
the `+$unit` target. No new data/TF.

### Change detail per file
- **`constants.py`** — `PROFIT_PROTECT_MIN_USD = 0.0` replaced by `PROFIT_PROTECT_USD_PER_UNIT = 1.0`
  (+ comment). (Variant-A `_h` only; other branches keep `PROFIT_PROTECT_MIN_USD`.)
- **`strategy.py`** — import swap; new precompute (after the force-close precompute) sets
  `profit_protect_min = times × PROFIT_PROTECT_USD_PER_UNIT` and `buy_pp`/`sell_pp` (+`_reason`) via
  the 3-way D1 book table; the two open-basket `profit_protect` `if`s become `if buy_pp:` /
  `if sell_pp:`. Docstring updated. Hard-stop/ladder/entry untouched.
- **`docs/h4h1m15-decision-table.md`** — variant-A Exits §1 rewritten to the D1 book table + dynamic threshold.

### Verification
- `python -m py_compile constants.py indicator.py strategy.py app.py dashboard.py` → OK.
- Offline unit-walk (ephemeral): threshold scales (same $1.5 books at times=1, holds at times=2);
  WITH→`pp_trend` (needs 15M both), split/flat→`profit_protect` (≥1 15M), AGAINST→`pp_counter`
  (≥1 H1 + ≥1 15M); profit-book priority over the hard-stop; force-close cascade unaffected when
  not in profit; SELL mirror; ladder — all pass.

### Rollback
`git revert <v2.6.0-sha>` per branch. To revert just the threshold: set the book gate back to a
flat const. To revert the D1 book table: restore the single `if buy_profit > min and h1 both and
≥1 m15` form.

---

## [v2.5.0] — 2026-10-22 — D1-SPLIT force-close cascade (4H → 1H → 15M-RSI floor) [_exp_h]

**Baseline:** the v2.4.0 HEAD per branch (the `_h` creds HEADs).
**Branches:** the 4 **`_h`** branches only — `rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`
(variant A) and `rsimacd_h6_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h` (variant B).
**EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `strategy.py`, `docs/h4h1m15-decision-table.md` (+ this `CHANGELOG.md`).

**Why.** Until now the force-close classified D1 only three ways and lumped **D1-SPLIT**
(daily RSI vs MACD disagree) into the NORMAL close. The owner wanted a graded, recursive
response for a *split/confused daily*: defer to the next lower timeframe, and the deeper you
must descend to find a decisive verdict, the more sensitive the exit (less higher-TF backing);
a *supportive* verdict adds confirmation (wait). Standard MTF exit logic — hold with the higher
TF, tighten against it.

### Behaviour change — force-close only (BUY shown; SELL mirrors, signs flipped)
D1 is now classified four ways vs the basket (up=supportive, down=against, split, flat):
- **D1 AGAINST** (`d1r<0 and d1m<0`) → **sensitive** `15M both AND ≥1 H1` (`force_close_fast`) — unchanged.
- **D1 WITH (both up) OR FLAT** → **normal** `≥1 4H AND 1H both AND 15M both` (`force_close`) — unchanged.
- **D1 SPLIT** (`(d1r<0 and d1m>0) or (d1r>0 and d1m<0)`) → **NEW cascade** 4H → H1 → floor. First
  decisive TF sets the close band; supportive = +1 stricter, deeper = more sensitive. Ladder:
  **C3** `H1 RSI− AND 15M both−` · **C2** `15M both−` · **C1** `15M RSI−` (floor):
  | first decisive TF | verdict | close | reason |
  |---|---|---|---|
  | 4H | supportive (both up) | C3 | `fc_split_4h_sup` |
  | 4H | against (both down) | C2 | `fc_split_4h_opp` |
  | H1 (4H indecisive) | supportive | C2 | `fc_split_h1_sup` |
  | H1 (4H indecisive) | against | C1 | `fc_split_h1_opp` |
  | none (4H & H1 indecisive) | — | C1 (floor) | `fc_split_floor` |

  "indecisive" = split **or** flat. Note: with the C1 floor at `15M RSI−`, a fully-split daily can
  cut faster than a cleanly-against daily (`15M both + ≥1 H1`) — intentional (chop → quick exits).

**Unchanged:** the D1-against (`force_close_fast`) and D1-with/flat (`force_close`) conditions,
the h6 `+$unit` target, the variant-A `profit_protect`, the RSI DCA ladder, and entry
(`_slope_direction`, 4H/1H/15M only — D1 stays exit-only). No new data/TF.

### Change detail per file
- **`strategy.py`** — the force-close precompute (per side) goes from a 2-way `if/else` to a
  3-way `if (D1 against) / elif (D1 split → nested 4H→H1→floor) / else (normal)`; adds `m15_both_dn`
  /`m15_both_up` locals and five `fc_split_*` reason labels. Comment + `calculate_signal` docstring
  updated. Identical edit in variant A & B (same precompute block).
- **`docs/h4h1m15-decision-table.md`** — Exits section rewritten to the 4-way regime + the cascade table.

### Verification
- `python -m py_compile constants.py indicator.py strategy.py app.py dashboard.py` → OK.
- Offline unit-walk (ephemeral): every cascade terminal (4H sup/opp, H1 sup/opp, floor) + both
  mirrors + the C1-floor "15M-RSI-alone fires even if 15M-MACD is with" edge + D1-against/with/flat
  unchanged + `+$unit` target priority + profit_protect (+ priority) + DCA ladder + entry — all pass.

### Rollback
`git revert <v2.5.0-sha>` per branch, or delete the 4 `_h` branches. To revert just this: replace
the `elif (D1 split)` cascade with the v2.4.0 `else: buy_fc = (h4r<0 or h4m<0) and h1r<0 and h1m<0
and m15r<0 and m15m<0` (D1-split falls back into NORMAL).

---

## [v2.4.0] — 2026-10-18 — Sensitive force-close gains a 1H confirm (D1-against path) [_exp_h]

**Baseline:** the v2.3.0 HEAD per branch (the `_exp` creds HEADs).
**Branches:** the 4 **`_h`** branches only — `rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`
(variant A) and `rsimacd_h6_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h` (variant B), derived
from the 4 `_exp` branches. **EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `strategy.py`, `docs/h4h1m15-decision-table.md` (+ this `CHANGELOG.md`).

**Why.** On `_exp` (v2.3.0) the D1-against "sensitive" force-close fired on **15M both** alone — a
very twitchy trigger that can cut counter-trend baskets on pure-M15 noise. Add a **1H confirm**: the
sensitive path now also needs **≥1 of {1H RSI, 1H MACD}** against. Still clearly looser than the
normal path (which needs 1H *both* + ≥1 4H), so it keeps the "cut counter-trend faster" intent while
filtering single-TF noise. (Owner chose ≥1 H1 over 1H-both: 1H-both would collapse the sensitive
path into ≈ the normal path, since that only differs by the dropped 4H lean.)

### Behaviour change — the D1-against (sensitive) force-close ONLY (BUY shown; SELL mirrors)
- **Was** (`_exp`): `m15r<0 and m15m<0` → CLOSE (`force_close_fast`).
- **Now** (`_h`):  `(m15r<0 and m15m<0) and (h1r<0 or h1m<0)` → CLOSE (`force_close_fast`).

**Unchanged:** the D1 classifier itself (sensitive only when D1 is **both-against**; D1 with-trend
OR flat/mixed still → the normal path), the **normal** force-close (`≥1 4H AND 1H both AND 15M both`),
the h6 `+$unit` target, the variant-A `profit_protect`, the RSI DCA ladder, and entry
(`_slope_direction`, 4H/1H/15M only). No new data/TF — D1 already fetched on `_exp`.

### Change detail per file
- **`strategy.py`** — in the `d1r<0 and d1m<0` / `d1r>0 and d1m>0` branches of the force-close
  precompute, `buy_fc`/`sell_fc` gain `and (h1r<0 or h1m<0)` / `and (h1r>0 or h1m>0)`; the inline
  comment + `calculate_signal` docstring updated. Nothing else touched (identical edit in variant A
  and B — the precompute block is the same).
- **`docs/h4h1m15-decision-table.md`** — the Exits sensitive/hard-stop bullet updated to `15M both AND ≥1 H1`.

### Verification
- `python -m py_compile constants.py indicator.py strategy.py app.py dashboard.py` → OK.
- Offline unit-walk (ephemeral): D1-against fires `force_close_fast` only when `15M both AND ≥1 H1`
  against (does NOT fire on 15M-both with 1H flat/with); D1 with/flat/mixed → normal `force_close`
  unchanged; `+$unit` target / profit_protect / DCA ladder / entry all unchanged — all pass.

### Rollback
`git revert <v2.4.0-sha>` per branch, or delete the 4 `_h` branches (the `_exp` parents are
untouched). To revert just this tweak: drop the `and (h1r…)` / `and (h1r>0…)` conjuncts from the
two sensitive lines (back to the `_exp` 15M-both form).

---

## [v2.3.0] — 2026-10-17 — D1-regime force-close (Daily-aligned baskets get room; counter-trend cut fast) [_exp]

**Baseline:** the v2.2.0 HEAD per branch.
**Branches:** the 4 **`_exp`** branches only — `rsimacd_btcusd1_wd_exp`, `rsimacd_xauusd1_wd_exp`
(variant A) and `rsimacd_h6_btcusd1_wd_exp`, `rsimacd_h6_xauusd1_wd_exp` (variant B), derived
from the 4 `_wd` branches. **EXPERIMENT — demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py`, `app.py`, `dashboard.py`,
`docs/h4h1m15-decision-table.md` (+ this `CHANGELOG.md`).

**Why.** When an open basket is aligned with the Daily trend the move tends to last, so small
corrections should be tolerated (hold the DCA ladder longer). When the Daily is *against* the
basket the move is more likely short-lived — so the force-close should be quick. This conditions
exit aggressiveness on a Daily (D1) RSI+MACD slope regime. **D1 is EXIT-only** — entry stays the
pure 4H/1H/15M table (`_slope_direction` never reads D1).

### Behaviour change — force-close only (BUY shown; SELL mirrors, signs flipped)
Classify the Daily slope vs the open basket, then pick the force-close condition:
- **D1 AGAINST** (BUY: `d1r<0 and d1m<0`) → **sensitive**: `m15r<0 and m15m<0` → CLOSE
  (`exit_reason='force_close_fast'`).
- **else** (D1 with-trend, flat, or mixed) → **normal** (v2.2.0): `(h4r<0 or h4m<0) and h1r<0 and
  h1m<0 and m15r<0 and m15m<0` → CLOSE (`exit_reason='force_close'`).
**Unchanged:** entry `_slope_direction`, the RSI DCA ladder, the h6 `+$unit` target, and the
variant-A `profit_protect`. A flat/mixed Daily → NORMAL (not sensitive), so a ranging daily never
hair-triggers and the rule degrades gracefully when D1 pivots are undefined (daily pivots are sparse).

### Change detail per file
- **`constants.py`** — `SLOPE_TIMEFRAMES` gains `'TIMEFRAME_D1'` →
  `['TIMEFRAME_M15','TIMEFRAME_H1','TIMEFRAME_H4','TIMEFRAME_D1']`; header/comment updated. ⚠ D1
  is not fetched elsewhere, so this is **+1 MT5 rates call per loop** (~500 daily bars).
- **`strategy.py`** — `calculate_signal` extracts `d1r`/`d1m` and precomputes
  `buy_fc`/`buy_fc_reason` + `sell_fc`/`sell_fc_reason` (the D1-regime classifier) above the exit
  chain; the force-close/hard-stop elifs become `elif buy_fc:` / `elif sell_fc:`. Ladder, target,
  profit_protect and entry untouched. Docstrings updated.
- **`app.py`** — no logic change (the slope loop already computes a slope for every
  `SLOPE_TIMEFRAMES` entry; D1 is now in the list so it's fetched + computed). Comments updated.
- **`dashboard.py`** — `build_slope_panel` gains a **D1 row** (top) + **two D1 pivot mini-charts**;
  panel is now D1/H4/H1/M15 (8 charts).
- **`docs/h4h1m15-decision-table.md`** — intro + Exits section + Notes updated to the D1-regime exit.

### Verification
- `python -m py_compile constants.py indicator.py strategy.py app.py dashboard.py` → OK.
- Offline unit-walk (ephemeral): D1-against → `force_close_fast` on M15-both only; D1
  with/flat/mixed → normal `force_close` (needs ≥1 H4 + H1 both + M15 both); +$unit target /
  profit_protect / DCA ladder / entry all unchanged — all pass.

### Rollback
`git revert <v2.3.0-sha>` per branch, or delete the 4 `_exp` branches (the `_wd` parents are
untouched). **Clean config disable:** remove `'TIMEFRAME_D1'` from `SLOPE_TIMEFRAMES` → D1 signs
read 0 → the `d1r<0 and d1m<0` / `d1r>0 and d1m>0` classifier is never true → force-close falls
back to the exact v2.2.0 normal path (and the fetch is dropped; the D1 dashboard row just goes blank).

---

## [v2.2.0] — 2026-10-13 — Retune the slope force-close (4H ≥1 / 1H both / 15M both)

**Baseline:** the v2.1.0 HEAD per branch.
**Branches:** all 4 `_wd` branches — `rsimacd_btcusd1_wd`, `rsimacd_xauusd1_wd` (variant A)
and `rsimacd_h6_btcusd1_wd`, `rsimacd_h6_xauusd1_wd` (variant B / h6). **EXPERIMENT —
demo-testing, NOT propagated to the 20 live fleet branches.**
**Files touched:** `strategy.py`, `docs/h4h1m15-decision-table.md` (+ this `CHANGELOG.md`).

**Why.** The v2.1.0 force-close (4H **both** against + ≥1 1H + ≥1 15M) was booking a lot of
losses: it capitulated whenever 4H fully flipped even if the lower timeframes had only hinted.
The owner retuned it to fire only on a **full lower-TF reversal**, with 4H just needing to lean:
- **4H:** ≥1 of {RSI, MACD} against (RSI `h4r` is the preferred/primary of the two).
- **1H:** **both** RSI and MACD against.
- **15M:** **both** RSI and MACD against.
So force-close no longer triggers on a full-4H / partial-1H-15M turn — it holds the basket (lets
the DCA ladder / target work) unless 1H **and** 15M have both fully turned. Consistent with the
hold-till-target history (v1.1.0 early cuts lost money → v1.3.0 revert).

### Behaviour change
- **force_close (all 4, uniform).** BUY basket closes on
  `(h4r<0 or h4m<0) AND h1r<0 AND h1m<0 AND m15r<0 AND m15m<0`; SELL mirrors (signs flipped).
  Replaces the v2.1.0 `h4 both AND ≥1 h1 AND ≥1 m15`.
- **Unchanged:** the entry `_slope_direction`, the RSI DCA ladder, the h6 pair's `+$unit`
  target, and the base pair's `profit_protect` (1H both + ≥1 15M, in profit only — not a
  loss-booker, so left as-is).

### Change detail per file
- **`strategy.py`** — both `force_close` elifs (BUY + SELL) rewritten to the new gate + an
  inline comment; the `calculate_signal` docstring force-close line updated. Entry, ladder,
  target / profit-protect untouched.
- **`docs/h4h1m15-decision-table.md`** — intro + Exits section updated to the retuned
  force-close (4H ≥1 RSI-preferred / 1H both / 15M both) and its rationale.

### Verification
- `python -m py_compile` → OK.
- Offline unit-walk (ephemeral): force_close fires only when `≥1 4H against AND 1H both against
  AND 15M both against`; does NOT fire when 1H is only ≥1 (not both) or 15M only ≥1; a 4H single
  sub-signal (RSI-only and MACD-only) each suffice; entry matrix + ladder unchanged — all pass.

### Rollback
`git revert <v2.2.0-sha>` per branch, or restore the two `force_close` elifs to the v2.1.0
form (`h4r<0 and h4m<0 and (h1r<0 or h1m<0) and (m15r<0 or m15m<0)`).

---

## [v2.1.0] — 2026-10-13 — Add 15M as the third slope-confirm tier (4H → 1H → 15M)

**Baseline:** `ce02b64` (btcusd1_wd HEAD) / its xauusd1_wd mirror.
**Branches:** `rsimacd_btcusd1_wd` and `rsimacd_xauusd1_wd` **only** (variant A, slope-exit pair).
**EXPERIMENT — demo-testing branches. NOT propagated to the 20 live fleet branches.**
**Files touched:** `constants.py`, `strategy.py`, `app.py`, `dashboard.py`,
`docs/h4h1-decision-table.md` → `docs/h4h1m15-decision-table.md` (+ this `CHANGELOG.md`).

**Why.** The owner wanted a finer entry/exit trigger under the existing 4H×1H slope engine:
keep **4H as the primary** direction-setter, **1H as the confirm**, and add **15M as the
final trigger** so a signal only fires when the fastest tier also agrees. Applied to **both**
entry and the slope exits. (Mirror of the v2.1.0 change on the `_h6` variant-B pair, adapted
to this pair's exits.)

### Behaviour change
- **Entry (flat only).** Identical to the `_h6` pair: the former 4H×1H table gains a 15M gate
  on every tradeable row. BUY needs `4H both + AND ≥1 1H + AND ≥1 15M +`; SELL mirrors;
  4H-SPLIT still needs `1H both` aligned plus `≥1 15M` aligned. 15M strength = **loose
  (≥1 sign)**. If 15M does not confirm → WAIT.
- **Exit (open basket) — variant A has TWO slope exits; BOTH gained the gate** (owner chose
  the uniform rule 2026-10-13):
  - **profit-protect**: `profit > PROFIT_PROTECT_MIN_USD AND both 1H slopes against AND
    ≥1 15M against` → CLOSE.
  - **hard stop (force-close)**: `4H both against AND ≥1 1H against AND ≥1 15M against` →
    CLOSE.
  The RSI DCA ladder is **unchanged**. Both slope exits are now slightly **slower** (all
  three tiers must align against) — consistent with the rolled-back early-cut history
  (v1.1.0 → v1.3.0).

### Change detail per file
- **`constants.py`** — `SLOPE_TIMEFRAMES` `['TIMEFRAME_H1','TIMEFRAME_H4']` →
  `['TIMEFRAME_M15','TIMEFRAME_H1','TIMEFRAME_H4']`; header/comment updated to "4H + 1H + 15M"
  and the doc reference repointed to `h4h1m15-decision-table.md`. Two nearby comments updated
  H1/H4 → 15M/H1/H4. Pivot params (`PEAK_LOOKBACK`/`PIVOT_WIDTH`/`RSI_PEAK_OB`/`RSI_PEAK_OS`)
  shared unchanged.
- **`strategy.py`** — `_slope_direction` reads `M15` RSI+MACD signs and requires
  `m15_up`/`m15_dn` (`≥1` sign) on each BUY/SELL branch (identical to the `_h6` pair).
  `calculate_signal` computes `m15r`/`m15m`; the BUY exits gain `and (m15r < 0 or m15m < 0)`
  on **both** the `profit_protect` and `force_close` branches, SELL mirrors with
  `(m15r > 0 or m15m > 0)`. Docstrings/comments updated. RSI DCA ladder untouched.
- **`app.py`** — **no logic change.** The RSI fetch loop already computes a slope for every
  `SLOPE_TIMEFRAMES` entry and 15M is already fetched → **zero new MT5 calls**; two comments
  updated H1/H4 → 15M/H1/H4.
- **`dashboard.py`** — `build_slope_panel` gains an `m15 = slopes.get('M15', …)`, an **M15
  row** in the slope grid, and **two M15 pivot mini-charts** (RSI + MACD-hist). Identical to
  the `_h6` pair.
- **`docs/`** — `h4h1-decision-table.md` renamed to `h4h1m15-decision-table.md` and rewritten
  to the 3-timeframe table; the Exits section documents variant A's profit-protect + hard-stop
  (both gated).

### Verification
- `python -m py_compile constants.py indicator.py strategy.py app.py dashboard.py` → OK.
- Offline unit-walk (ephemeral, not committed): full **17-case entry matrix** (same as `_h6`)
  + variant-A **exit matrix** — profit-protect and hard-stop each firing only when their H1/H4
  condition AND `≥1 15M against` all hold, HOLD when 15M does not confirm, profit-protect
  priority over hard-stop, and the DCA ladder still firing — **all pass**.

### Rollback
Revert the four code files + the doc rename to `ce02b64` (per branch), or
`git revert <v2.1.0-sha>`. ⚠ Note: merely setting `SLOPE_TIMEFRAMES` back to
`['TIMEFRAME_H1','TIMEFRAME_H4']` does **not** restore the old behaviour — with `M15` absent,
`_slope_sign` returns 0 so `m15_up`/`m15_dn` are False and **no** entry, profit-protect, or
hard-stop can fire (all blocked). A real revert must also drop the `m15_*` conjuncts.

---

## [v2.0.0] — 2026-10-10 — RSI+MACD Slope Strategy (full rewrite of direction + management)

**Baseline:** the live v1.6.0 fleet HEAD per branch (`adcb1cb` btcusd1 / `dca6788` xauusd1).
**Branches:** `rsimacd_dev_btcusd1_v2` (off `dev_btcusd1_v2`) and `rsimacd_dev_xauusd1_v2`
(off `dev_xauusd1_v2`). **EXPERIMENT — NOT propagated to the 20 live fleet branches.**
Must pass the offline backtest before any live money.
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py`, `dashboard.py` (+ this `CHANGELOG.md`).

**Why.** The bot kept taking large losses on spikes/slippage even after the v1.6.0 ADX
regime filter. The owner decided to replace the entire trade-direction + basket-management
logic: remove everything that previously chose direction or averaged down, and rebuild entry
and exit on RSI + MACD **slope** reversals (idea inspired by mean-reversion). The martingale is
removed — one position per signal with real stops — which is what eliminates the deep spike
drawdowns (previously depth-6 H6 capitulations on an averaged-down basket).

### Behaviour — the new strategy
- **Indicators (H1 & H4):** RSI(14) and MACD(12/26/9) histogram. For each, the *latest pivot*
  (local turning point, width `k=2`) within the last `N=20` bars is found — the most recent one
  wins even if smaller than earlier pivots — and a per-bar **slope sign** (pivot → current) is
  taken. 4 slopes total. No OB/OS thresholds anymore (sign only).
- **Entry (flat only):** H4-primary / H1-confirm. H4 both +ve & ≥1 H1 +ve → BUY; H4 both −ve &
  ≥1 H1 −ve → SELL; H4 split → H1-both-aligned decides; any zero/undefined slope → WAIT. Opens a
  **single** position; a 300 s post-close cooldown blocks instant re-entry.
- **Exit (open basket):** (1) profit-protect — profit > `PROFIT_PROTECT_MIN_USD` AND **both** H1
  slopes flipped against → CLOSE; (2) hard stop — H4 both flipped against AND (either H1 against)
  → CLOSE (accept loss); else HOLD. No DCA adds, no H6.

### Change detail per file
- **`constants.py`** — REMOVED the SHA block (`SHA_LENGTH`/`SHA_MA_TYPE`/`SHA_TREND_*`),
  `STRATEGY_LOOKBACK`, `STRATEGY_SHA_THRESHOLD`, the whole Regime Entry Filter block (all
  `REGIME_*`), `RSI_OVERSOLD`/`RSI_OVERBOUGHT`/`RSI_DCA_MAX_POSITIONS`,
  `RSI_MTF_OVERSOLD`/`RSI_MTF_OVERBOUGHT`. ADDED `MACD_FAST`/`SLOW`/`SIGNAL` (12/26/9),
  `SLOPE_TIMEFRAMES` (H1,H4), `PEAK_LOOKBACK` (20), `PIVOT_WIDTH` (2),
  `REENTRY_COOLDOWN_SECONDS` (300), `PROFIT_PROTECT_MIN_USD` (0.0 — tune to costs). KEPT
  `CANDLE_TIMEFRAME`/`CANDLE_COUNT` (price feed), `RSI_LENGTH`/`RSI_MA_TYPE`/`RSI_CANDLE_COUNT`,
  and the RSI timeframe lists (app fetch / dashboard RSI display).
- **`indicator.py`** — REMOVED `calculate_sha_v3`, `calculate_adx`. ADDED `calculate_macd`
  (ta.macd-compatible) and `latest_pivot_slope` (latest-pivot + per-bar slope sign). KEPT
  `calculate_rsi`, `_ma`, `_tv_exp_ma*`.
- **`strategy.py`** — `calculate_signal` fully rewritten. Removed `_analyze`/`_analyze_trend`,
  the SHA entry, the regime param/annotation, the MTF-RSI entry filter, the DCA ladder, the H6
  close, the fixed +$unit target and the Fibo helpers. Added `_slope_sign`, `_slope_direction`
  and the slope entry + exit. New `slopes` / `entry_allowed` params; `analysis_data` now carries
  `slopes` / `slope_direction` / `entry_allowed` / `exit_reason`.
- **`app.py`** — removed SHA fetch/calc, `_compute_regime` + all regime wiring/logging, and the
  `BUY_MORE`/`SELL_MORE` execution handlers. Added H1/H4 MACD + slope computation inside the
  existing RSI fetch loop (no new MT5 call), the re-entry cooldown (`_last_close_time`,
  `entry_allowed`), and `exit_reason` in the close logs.
- **`dashboard.py`** — added `build_slope_panel` (the 4 slopes + decision / cooldown / exit
  reason) and switched the analysis panel from `build_sha_analysis_panel` (now dead) to it.

### Verification
- `python -m py_compile` on all files — OK.
- Unit tests (offline): MACD identity (hist = macd − signal, macd = EMA12 − EMA26); 6 pivot cases
  incl. latest-smaller-wins and monotonic → none; all 25 Step-6 entry cases incl. zeros; full
  exit matrix (profit-protect / hard stop / give-room HOLD / priority / mirror); the cooldown gate
  and the open-position guard.
- **STILL REQUIRED before live:** the ~3-month offline backtest — quantifies `PROFIT_PROTECT_MIN_USD`
  and the strategy's expectancy / drawdown under real spread + commission.

### Rollback
Isolated feature branches off the live v1.6.0 HEADs. To abandon: delete the `rsimacd_dev_*`
branches (the live `dev_*` branches are untouched). To revert a single phase: `git revert <sha>`
— teardown `5a122d1`/`46a817e`/`73bbf63`, rebuild `abca018`/`e715f01`/`67cc93b` (btcusd; mirror
SHAs on xauusd).

---

## [v1.6.0] — 2026-10-01 — Regime Entry Filter (ADX + ATR-spike fresh-entry gate; OFF + shadow by default)

**Baseline commit (state before this change):** `60540a3` — *feat: MTF entry-filter thresholds 30/70 -> 35/65 (CHANGELOG v1.5.0)*.
**Branch:** `dev_btcusd2_v2` (then propagated to all 20 fleet branches).
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py` (+ this `CHANGELOG.md`).
**Behaviour change (when enabled):** adds a **fresh-entry-only** regime gate that can turn a
would-be BUY/SELL into **DO_NOTHING** when the current M15 price regime is hostile to
mean-reversion — a strong trend (**ADX**) or a fast **1–2 candle ATR spike**. It answers the
owner's two failure cases directly: (1) the 2-bar BULL/BEAR spike that lagging SHA enters the
wrong way, and (2) the dull→explosive trend where SHA gives the opposite direction and the
martingale cannot recover. **This is the exact opposite of the rolled-back v1.1.0 HTF
protection**: v1.1.0 *handled* spikes by cutting **open** baskets early (which locked in losses);
this gate only *prevents* a **new** basket from opening and **never touches an open basket** —
once `buy_count>0` or `sell_count>0`, the DCA ladder (M1/M5/M15/H1/H4 adds), RSI adds, `+$unit`
profit close and H6 forced close all run **byte-identical to v1.5.0**.

**Ships OFF and safe.** `REGIME_FILTER_ENABLED = False` → **byte-identical to v1.5.0** (the gate
computes nothing and `strategy.py` receives an inert `{}`). Turning it on defaults to **shadow
mode** (`REGIME_FILTER_SHADOW = True`): it computes the verdict and **logs** every fresh entry it
*would* have blocked, but still trades identically — so the block rate can be measured on live
data before it is ever allowed to suppress a trade. No new MT5 fetches (ATR is an intermediate of
ADX on the M15 `source_df` already pulled for SHA) and fully **stateless** (recomputed each loop;
no latch to get stuck, unlike v1.1.0's `spike_latched`).

### Why
Per the owner (planning phase → approved): SHA is a lagging trend pair (TEMA10/DEMA20 on M15) and
RSI is a range tool, so neither can veto an entry taken *into* a fresh trend/spike. A **regime**
dimension is the missing filter. ADX (inverted: high ADX = trend = **don't** open a mean-reversion
basket) plus a stateless ATR-spike guard catches both the slow trend and the fast 2-bar move. Built
entry-only and OFF-by-default precisely because the previous market-protection attempt (v1.1.0) lost
money by acting on open baskets — the owner asked to *prevent* bad entries, not *handle* them, and to
"be prepared to rollback if this also fails."

### Change detail per file
- **`constants.py`** — new `Regime Entry Filter (FRESH-ENTRY gate ONLY)` block (L76–118), placed
  after `RSI_FINAL_CLOSE_TIMEFRAME` and before `Risk Management`. Master switches
  `REGIME_FILTER_ENABLED = False`, `REGIME_FILTER_SHADOW = True`. ADX gate: `REGIME_ADX_ENABLED`,
  `REGIME_ADX_PERIOD = 14`, `REGIME_ADX_MAX = 25.0`, `REGIME_ADX_USE_DI = False`. ATR-spike guard:
  `REGIME_ATR_ENABLED`, `REGIME_SPIKE_K1 = 2.2`, `REGIME_SPIKE_K2 = 3.2`, `REGIME_SPIKE_WINDOW = 2`,
  `REGIME_SPIKE_USE_DIR = False`. RSI-slope phase-2 (off): `REGIME_RSI_SLOPE_ENABLED = False`,
  `REGIME_RSI_SLOPE_TIMEFRAMES = [M1, M5]`, `REGIME_RSI_SLOPE_BARS = 3`, `REGIME_RSI_SLOPE_MIN = 8.0`.
  A comment documents the optional per-symbol `"regime"` override in `symbols.json`
  (`adx_max`/`spike_k1`/`spike_k2`/`spike_window`). No existing key changed.
- **`indicator.py`** — new `calculate_adx(self, high, low, close, length=14)` (L169), inserted
  between `calculate_rsi` and `_ma`. Wilder / TradingView `ta.adx`-compatible: TR, RMA-smoothed ATR,
  `+DI`/`−DI` from directional movement, `DX`, and RMA-smoothed `ADX`; returns a DataFrame
  `{TR, ATR, plus_DI, minus_DI, ADX}` (ATR falls out for free, so the spike guard needs no extra
  math). Divide-by-zero guarded via `replace(0, np.nan)` on ATR and the DI sum. Pure addition — no
  existing indicator touched. Verified on synthetic data: ADX∈0–100, low in range / ~99 in trend,
  `+DI>−DI` on an uptrend, NaN-safe warmup.
- **`strategy.py`** — `calculate_signal(...)` gains a trailing `regime=None` param (L168) + docstring
  note (L184–185: entry-only, ignored once a basket is open). In the **flat** branch only
  (`buy_count == 0 and sell_count == 0`), the SHA decision is split into `sha_wants_buy`/`sha_wants_sell`
  (L277–278) and gated by `_block_buy`/`_block_sell` read from the regime dict (L274–276), so a blocked
  side falls through to DO_NOTHING (L283–285). Every open-basket branch (DCA ladder, RSI adds, profit
  close, H6 close) is **unchanged**. Adds a `regime_out` telemetry block (L326–334:
  `would_fire_buy/sell`, `blocked_buy/sell`, `shadow_would_block_buy/sell`) surfaced as
  `analysis_data['regime']` (L350); the early-return path carries `'regime': regime or {}` (L241).
  `regime=None` ⇒ `{}` ⇒ nothing blocks (full backward compatibility).
- **`app.py`** — imports the 15 `REGIME_*` constants (L25–30). New `_compute_regime(...)` (L444–565):
  returns an inert dict when `REGIME_FILTER_ENABLED` is False; else calls `calculate_adx` on the M15
  `source_df` (**fail-open** — any exception returns no-block, L476), applies the ADX gate
  (`adx >= adx_max`, symmetric or `+DI/−DI` directional), the stateless ATR-spike guard (scans the last
  `spike_window` bars, 1-bar `TR ≥ K1·priorATR` and 2-bar sum `≥ K2·priorATR`, optional direction from
  the last candle body), and the optional RSI-slope check; emits `would_block_*` (measurement) and
  `block_*` (= active **and** would-block) separately. Per-symbol overrides read once
  (L600–604) with constant fallbacks. The MTF-RSI loop optionally captures an RSI slope for the phase-2
  check (L750–755). `_compute_regime` is called just before `calculate_signal` and passed in
  (L764–778). Shadow verdicts ride along in the `BUY_EXECUTED`/`SELL_EXECUTED` log detail
  (L857–862 / L902–907); when actually blocking, a `REGIME_BLOCK_BUY`/`REGIME_BLOCK_SELL` event is
  logged **throttled to once per M15 bar** (`_last_regime_log_bar`, L605 / L945–960).

### Behaviour matrix
| `REGIME_FILTER_ENABLED` | `REGIME_FILTER_SHADOW` | Effect |
|---|---|---|
| `False` (default) | — | **Byte-identical to v1.5.0.** Gate computes nothing; `strategy.py` gets `{}`. |
| `True` | `True` (default when on) | Trades identically, but **logs** every fresh entry it *would* block. Measurement / A-B. |
| `True` | `False` | **Actively blocks** hostile-regime fresh entries (symmetric unless `*_USE_DIR`). |

### Verification
- `python -m py_compile constants.py indicator.py strategy.py app.py` → OK.
- `calculate_adx` unit-checked on synthetic calm→trend→spike data: ADX range 0–100, ~29 in range vs
  ~99 in trend, `+DI≫−DI` on the uptrend, and an injected 1-bar candle trips `TR/priorATR = 5.0 ≥ K1`.
- Entry-only guarantee: the regime dict is consulted **only** inside the `buy_count == 0 and
  sell_count == 0` branch; no open-basket branch reads it.

### Rollback
- **Instant, no code change:** leave/confirm `REGIME_FILTER_ENABLED = False` in `constants.py` — the
  filter is completely inert (this is the shipped default).
- **De-risk while keeping it on:** set `REGIME_FILTER_SHADOW = True` (log-only, never blocks).
- **Full removal:** revert the four files to `60540a3` (`git checkout 60540a3 -- constants.py
  indicator.py strategy.py app.py`), or if committed as `<v1.6.0-sha>`: `git revert <v1.6.0-sha>`.
  Removal is clean because every change is additive and OFF-gated — nothing in the v1.5.0 path was
  modified.

---

## [v1.5.0] — 2026-09-29 — MTF entry-filter thresholds 30/70 → 35/65 (match core RSI)

**Baseline commit (state before this change):** `93ddd21` — *feat: core RSI thresholds 30/70 -> 35/65 (CHANGELOG v1.4.0)*.
**Branch:** `dev_btcusd2_v2` (then propagated to all 20 fleet branches).
**Files touched:** `constants.py` (+ this `CHANGELOG.md`).
**Behaviour change:** the multi-timeframe **entry filter** thresholds are tightened
inward from 30/70 to 35/65 — `RSI_MTF_OVERSOLD 30 → 35`, `RSI_MTF_OVERBOUGHT 70 → 65` —
so both RSI threshold pairs now use the same 35/65 band. This filter gates **fresh
entries** only (`strategy.py` ~L253–254): a new BUY is blocked when ANY of M1/M5/M15/M30
RSI ≤ 35, a new SELL when ANY ≥ 65. Widening the block band from 30/70 to 35/65 makes
the entry filter **stricter** — fresh baskets open less often, only when all four MTF
RSIs sit in the calmer 35–65 middle. The core DCA-ladder / H6-close thresholds
(`RSI_OVERSOLD`/`RSI_OVERBOUGHT`) remain 35/65 from v1.4.0 — unchanged here.

### Why
Per the owner: apply the same 35/65 range to the MTF entry filter so it matches the
core RSI thresholds (one consistent band across entry + ladder).

### Change detail per file
- **`constants.py`** — L56 `RSI_MTF_OVERSOLD = 30` → `35`; L57 `RSI_MTF_OVERBOUGHT = 70`
  → `65` (comments and alignment unchanged). Core `RSI_OVERSOLD`/`RSI_OVERBOUGHT` stay
  at 35/65 (v1.4.0); `RSI_MTF_TIMEFRAMES` (M1/M5/M15/M30) unchanged.
- No logic files changed: `strategy.py` reads these constants by name
  (`any(v <= RSI_MTF_OVERSOLD ...)`, `any(v >= RSI_MTF_OVERBOUGHT ...)`), so the new
  values take effect with no code edits.

### Rollback
Restore the two values in `constants.py` (`RSI_MTF_OVERSOLD = 30`,
`RSI_MTF_OVERBOUGHT = 70`), or if committed as `<v1.5.0-sha>`: `git revert <v1.5.0-sha>`.

---

## [v1.4.0] — 2026-09-29 — Core RSI thresholds 30/70 → 35/65

**Baseline commit (state before this change):** `9e311b7` — *revert: roll back HTF spike/drawdown protection (CHANGELOG v1.3.0)*.
**Branch:** `dev_btcusd2_v2` (then propagated to all 20 fleet branches).
**Files touched:** `constants.py` (+ this `CHANGELOG.md`).
**Behaviour change:** the **core** RSI oversold/overbought thresholds are tightened
inward from 30/70 to 35/65 — `RSI_OVERSOLD 30 → 35`, `RSI_OVERBOUGHT 70 → 65`. These
gate the DCA ladder adds (`BUY_MORE`/`SELL_MORE` at M1/M5/M15/H1/H4, `strategy.py`
~L277–304) and the H6 RSI forced-close, so a basket adds the next rung — and
force-closes when maxed — at a less-extreme RSI (sooner / more readily). The
multi-timeframe **entry filter** is deliberately left at 30/70 (`RSI_MTF_OVERSOLD`,
`RSI_MTF_OVERBOUGHT`), so fresh-entry gating is unchanged.

### Why
Per the owner: make the mean-reversion ladder react on shallower RSI extremes.
Entry-filter behaviour intentionally unchanged (confirmed scope: "Core RSI only").

### Change detail per file
- **`constants.py`** — L50 `RSI_OVERSOLD = 30` → `35`; L51 `RSI_OVERBOUGHT = 70` → `65`
  (comments and alignment unchanged). `RSI_MTF_OVERSOLD` (30) and `RSI_MTF_OVERBOUGHT`
  (70) left untouched.
- No logic files changed: `strategy.py` references these constants by name
  (`rsi_* <= RSI_OVERSOLD`, `rsi_* >= RSI_OVERBOUGHT`), so the new values take effect
  with no code edits.

### Rollback
Restore the two values in `constants.py` (`RSI_OVERSOLD = 30`, `RSI_OVERBOUGHT = 70`),
or if committed as `<v1.4.0-sha>`: `git revert <v1.4.0-sha>`.

---

## [v1.3.0] — 2026-09-29 — Rollback HTF Spike / Drawdown Protection (revert v1.1.0)

**Baseline commit (state before this change):** `32dc79a` — *feat: HTF spike/drawdown protection + remove gap_range & SHA convergence entry filters* (this commit bundled v1.1.0 + v1.2.0 together).
**Branch:** `dev_btcusd2_v2`
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py` (+ this `CHANGELOG.md`)
**Status:** working tree (uncommitted).
**Behaviour change:** the entire v1.1.0 Higher-Timeframe Spike / Drawdown Protection
module is **removed**. The DCA/martingale basket is back to pure RSI mean-reversion:
the ladder runs all tiers — fresh entry, then M1/M5/M15/H1/**H4** adds — with the
**H6** RSI forced-close as the only capitulation exit. There is again **no tail-risk
stop** (no catastrophe stop, no spike medium stop, no ladder cap, no ATR spike
detector). This is exactly the pre-v1.1.0 (`d0bc0ec` / v1.0.0) loss-side behaviour.
The v1.2.0 entry-filter change (gap_range + SHA convergence removed) and the
balance-stepped auto unit sizing (`step_up_balance`) are **kept, untouched**.

### Why
Per the owner, in live trading the spike/slippage protection cut baskets early at
the H1/H4 tiers and locked in losses the mean-reversion ladder would otherwise have
recovered — it caused net loss. Reverting restores the profitable "mean-reverse till
H4, H6 forced close" logic. The auto lot-increment must stay, so this is a surgical
removal of v1.1.0 only, **not** a full reset to `d0bc0ec`.

### Verification
- `git diff d0bc0ec` for the four code files shows **no** HTF/spike content — the
  spike-protection surface is byte-identical to the pre-v1.1.0 baseline `d0bc0ec`.
- The BUY/SELL DCA `if/elif` ladder is **byte-identical to `d0bc0ec`** (full H4 add,
  H6 forced close).
- The v1.2.0 gap_range/convergence removal is still present (diff vs `d0bc0ec` still
  shows those deletions).
- Auto unit stepping (`step_up_balance`) is still present in `app.py`.
- All four files parse (`ast.parse`); grep finds none of `HTF_`, `_detect_htf_spike`,
  `spike_latched`, `spike_src_df`, `ladder_capped`, `calculate_atr`, `htf_spike`, or
  `acct_balance` remaining.

### Change detail per file (all REMOVALS of the v1.1.0 additions)
- **`constants.py`** — removed the whole `Higher-Timeframe Spike / Drawdown
  Protection` block (all 10 `HTF_*` keys). `RISK_REWARD_RATIO` is now immediately
  followed by the `File System / Output` section.
- **`indicator.py`** — removed the `calculate_atr(self, high, low, close, length=14)`
  method. `calculate_rsi` is now immediately followed by `_ma`.
- **`strategy.py`** — removed the 6 `HTF_*` imports; removed the `balance`/`spike`
  params (and their docstring lines) from `calculate_signal`; restored both the BUY
  and SELL `if/elif` ladders to their pre-v1.1.0 form (dropped the `catastrophe_hit` /
  `spike_medium_hit` / `ladder_capped` computation and the `and not ladder_capped` H4
  guard); removed the `htf_spike` and `htf_protection_enabled` keys from
  `analysis_data`.
- **`app.py`** — removed the 5 `HTF_*` imports; removed the `_detect_htf_spike`
  method; removed the `spike_latched` declaration and its flat-check reset (the
  adjacent `step_up_balance` auto-increment block was left in place); removed the
  `spike_src_df` init + in-loop capture; removed the spike detect/latch block; removed
  the `acct_balance` local and the `balance=`/`spike=` args on the
  `calculate_signal(...)` call; removed the two `'htf_spike'` log keys.

### Rollback (re-enable HTF protection)
This reversal is a pure removal of the v1.1.0 additions, applied on top of `32dc79a`.

**If this rollback is NOT yet committed** (current state) — discard it to get HTF back:
```bash
git checkout -- constants.py indicator.py strategy.py app.py
```
This restores the four files to `32dc79a` (HTF present). To then keep HTF present but
OFF, set `HTF_PROTECTION_ENABLED = False` in `constants.py`.

**If this rollback WAS committed** (say as `<v1.3.0-sha>`):
```bash
git revert <v1.3.0-sha>                                    # inverse commit, or:
git checkout 32dc79a -- constants.py indicator.py strategy.py app.py
```

---

## [v1.2.0] — 2026-09-20 — Remove gap_range + SHA convergence entry filters

**Baseline:** applied on top of v1.1.0 (working tree; still on commit `d0bc0ec`).
**Files touched:** `symbols.json`, `constants.py`, `indicator.py`, `strategy.py`, `app.py`, `dashboard.py`.
**Behaviour change:** the fresh-entry condition is **loosened**. Before, a new
basket opened only when SHA signal+trend agreed **AND** the gap% was inside
`gap_range` **AND** the SHA gap was `DIVERGING` **AND** no MTF RSI was extreme.
Now it opens when SHA signal+trend agree **AND** no MTF RSI is extreme. Two of
the four entry gates were removed, so entries fire more often. The DCA ladder,
exits, and HTF protection (v1.1.0) are unchanged.

### Why
Per the owner, the `gap_range` band and the SHA converging/diverging detection
"weren't much use" as entry filters. Removing them also drops two indicator calls
per loop (`calculate_sha_gap`, `calculate_sha_convergence`), trimming a little
compute.

### Verification requested (point 3 — no code change)
Confirmed: **RSI overbought/oversold never OPENS a fresh position on any
timeframe.** Fresh entries live only in the `buy_count == 0 and sell_count == 0`
branch, which is SHA-driven and gated by `rsi_mtf_blocked`. RSI extremes only
(a) *block* a fresh entry (via `rsi_mtf_blocked` on M1/M5/M15/M30), or (b) trigger
`BUY_MORE`/`SELL_MORE` on an already-open basket (count ≥ 1). No RSI path creates
a new basket. (Left as-is by request.)

### Change detail per file (all REMOVALS)
- **`symbols.json`** — removed the `"gap_range": [0.0002, 0.0200]` key from the
  `BTCUSDm` entry (and the trailing comma on the line above it).
- **`constants.py`** — removed `DEFAULT_GAP_RANGE` (and its `# ─── SHA Gap ───`
  header) and the whole `# ─── SHA Convergence ───` block
  (`SHA_CONVERGENCE_LOOKBACK`, `SHA_CLOSE_THRESHOLD`, `SHA_CONVERGENCE_THRESHOLD`).
- **`indicator.py`** — removed the methods `calculate_sha_gap` and
  `calculate_sha_convergence`. (`calculate_atr` from v1.1.0 now sits between
  `calculate_rsi` and `_ma`.)
- **`strategy.py`** — removed `DEFAULT_GAP_RANGE` + the 3 `SHA_CONVERGENCE_*`
  imports; removed `gap_pct_series`, `gap_range`, `convergence` params from
  `calculate_signal` (and their docstring lines); removed the `current_gap_pct`
  block, the `gap_range` default, and the convergence-state block; removed the
  `gap_in_range` / `below_gap` / `entry_conv_ok` / `exit_conv_ok` locals; dropped
  `and gap_in_range and entry_conv_ok` from both entry conditions; removed
  `current_gap_pct` / `gap_range` / `convergence` from both `analysis_data` dicts.
  Also fixed a stale comment on the MTF-RSI entry filter: it now correctly states
  that the filter uses `RSI_MTF_TIMEFRAMES` (M1/M5/M15/M30) and that the DCA-ladder
  (H1/H4) and final forced-close (H6, not H1) timeframes are excluded. Comment-only,
  no behaviour change.
- **`app.py`** — removed `DEFAULT_GAP_RANGE` + the 3 `SHA_CONVERGENCE_*` imports;
  removed the `symbol_gap_range = ...` lookup; removed the `gap_pct_series` +
  `convergence` computation block; removed `gap_pct_series`, `gap_range=`,
  `convergence=` from the `calculate_signal(...)` call.
- **`dashboard.py`** — removed the `_build_gap_row` function, its call in the SHA
  panel (and the `row_divider` above it), and the `gap_pct` / `gap_range_val` /
  `convergence` extraction lines.

### Rollback
All v1.1.0 + v1.2.0 changes are still **uncommitted**, and the removed gap/
convergence code is byte-identical to what exists at baseline `d0bc0ec`.

**Restore just the gap_range + convergence code (keep v1.1.0 HTF protection):**
this is a manual re-add — the exact original blocks are recoverable from git:
```bash
git show d0bc0ec:symbols.json     # copy back the gap_range key
git show d0bc0ec:constants.py     # copy back DEFAULT_GAP_RANGE + SHA_CONVERGENCE_*
git show d0bc0ec:indicator.py     # copy back calculate_sha_gap + calculate_sha_convergence
git show d0bc0ec:strategy.py      # copy back the params/blocks/entry gates listed above
git show d0bc0ec:app.py           # copy back the imports/lookup/calc/call args
git show d0bc0ec:dashboard.py     # copy back _build_gap_row + its call + extractions
```
Then re-apply the v1.1.0 additions to any file you overwrite (see the v1.1.0
entry's markers), since `d0bc0ec` predates v1.1.0.

**Revert everything to before v1.1.0 AND v1.2.0 (clean slate):**
```bash
git checkout d0bc0ec -- symbols.json constants.py indicator.py strategy.py app.py dashboard.py
```

**Cleaner granular rollback going forward:** commit v1.1.0 and v1.2.0 as separate
commits/tags; then each can be reversed independently with `git revert <sha>`.

---

## [v1.1.0] — 2026-09-20 — Higher-Timeframe Spike / Drawdown Protection

**Baseline commit (state before this change):** `d0bc0ec` — *chore: remove dead config keys (fibo_power, trading_window.timezone)*
**Branch:** `dev_btcusd2_v2`
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py` (+ this `CHANGELOG.md`)
**Behaviour change:** additive and OFF-safe. When `HTF_PROTECTION_ENABLED = False`
the bot behaves byte-for-byte like `d0bc0ec`. When `True`, it adds tail-risk
protection at the H1/H4/H6 tiers only; the low tiers (M1/M5/M15) and normal
(non-spike) deep reversions are unchanged.

### Why
The DCA/martingale basket had no real stop loss (the broker `sl`/`tp` are a no-op
because `RISK_REWARD_RATIO = [1, 1]`). The only loss-side exit was the H6
capitulation, so a rare adverse **spike/slippage** at the 1H/4H tiers produced huge
drawdowns (observed ≈ **$1000 on a ≈$1200 balance = 83%**). This adds a surgical,
low-compute defense for exactly that case.

### What was added — 4 layered mechanisms (strict priority chain, never conflict)
Priority order evaluated in `strategy.calculate_signal` (BUY and SELL branches):

```
catastrophe stop  >  profit close  >  spike medium stop  >  ladder cap  >  normal ladder
```

1. **Spike detector** — ATR on the H1 candles *already fetched* for RSI (no extra
   fetch). Adverse move over last N H1 bars ≥ `K × H1-ATR`. Latched per basket.
2. **Ladder cap on spike** — blocks the big H4 add (#6, 0.13 lot); allows up to the
   H1 add (#5, 0.08 lot). "Reduce to 1H, go no further."
3. **Spike medium stop** — flatten when spiking AND count ≥ H1 tier AND loss ≥
   `HTF_MEDIUM_LOSS_PCT × balance`.
4. **Catastrophe stop (always on)** — flatten when loss ≥ `HTF_CATASTROPHE_LOSS_PCT × balance`.

### Change detail per file

#### `constants.py`
- **Added** one block immediately after `RISK_REWARD_RATIO = [1, 1]`, header
  `# ─── Higher-Timeframe Spike / Drawdown Protection ───`, defining these 10 keys
  (all prefixed `HTF_`):
  `HTF_PROTECTION_ENABLED` (True), `HTF_CATASTROPHE_LOSS_PCT` (0.45),
  `HTF_MEDIUM_LOSS_PCT` (0.20), `HTF_PROTECT_MIN_COUNT` (4),
  `HTF_LADDER_CAP_ON_SPIKE` (True), `HTF_LADDER_CAP_MAX_COUNT` (5),
  `HTF_SPIKE_TIMEFRAME` ('TIMEFRAME_H1'), `HTF_SPIKE_ATR_PERIOD` (14),
  `HTF_SPIKE_LOOKBACK_BARS` (3), `HTF_SPIKE_ATR_MULT` (1.8).
- Nothing else changed.

#### `indicator.py`
- **Added** one method `calculate_atr(self, high, low, close, length=14)` immediately
  before `calculate_sha_convergence`. Pure/vectorized, reuses the existing `_ma(..., 'RMA')`.
- Nothing else changed.

#### `strategy.py`
- **Import block:** added 6 names to `from constants import (...)`:
  `HTF_PROTECTION_ENABLED, HTF_CATASTROPHE_LOSS_PCT, HTF_MEDIUM_LOSS_PCT,
  HTF_PROTECT_MIN_COUNT, HTF_LADDER_CAP_ON_SPIKE, HTF_LADDER_CAP_MAX_COUNT`.
- **`calculate_signal` signature:** added two trailing kwargs `balance=None, spike=False`
  (backward compatible — defaults reproduce old behaviour).
- **Docstring:** added `balance:` and `spike:` argument descriptions.
- **BUY branch** (`elif buy_count > 0 and sell_count == 0:`): added the
  `catastrophe_hit` / `spike_medium_hit` / `ladder_capped` computation and reordered
  the `if/elif` chain; the H4 add now has `and not ladder_capped`.
- **SELL branch** (`elif buy_count == 0 and sell_count > 0:`): mirror of the BUY change.
- **`analysis_data` (main dict):** added keys `'htf_spike'` and `'htf_protection_enabled'`.

#### `app.py`
- **Import block:** added 5 names to `from constants import (...)`:
  `HTF_PROTECTION_ENABLED, HTF_SPIKE_TIMEFRAME, HTF_SPIKE_ATR_PERIOD,
  HTF_SPIKE_LOOKBACK_BARS, HTF_SPIKE_ATR_MULT`.
- **Added** method `_detect_htf_spike(self, ohlc_df, is_buy_basket)` immediately before
  `def process_symbol`.
- **`process_symbol`:**
  - added `spike_latched = False` just before `while True:`.
  - added `spike_latched = False` reset inside the flat check
    (`if _buy_ct == 0 and _sell_ct == 0:`).
  - added `spike_src_df = None` before the RSI `for tf_name` loop; inside the loop,
    `if tf_name == HTF_SPIKE_TIMEFRAME: spike_src_df = tf_df`.
  - added the spike detect + latch block after `current_rsi = ...`.
  - added `acct_balance = ...` and passed `balance=acct_balance, spike=spike_latched`
    into `self.strategy.calculate_signal(...)`.
  - added `'htf_spike': spike_latched` to the `CLOSE_BUY` and `CLOSE_SELL` log details.

### Configuration reference (all in `constants.py`)
| Key | Default | Meaning |
|---|---|---|
| `HTF_PROTECTION_ENABLED` | `True` | Master switch. `False` = pre-v1.1.0 behaviour. |
| `HTF_CATASTROPHE_LOSS_PCT` | `0.45` | Always-on hard stop, fraction of balance. |
| `HTF_MEDIUM_LOSS_PCT` | `0.20` | Spike stop, fraction of balance. |
| `HTF_PROTECT_MIN_COUNT` | `4` | Arm medium stop only at count ≥ this (4 = H1 tier). |
| `HTF_LADDER_CAP_ON_SPIKE` | `True` | Block DCA adds beyond the cap during a spike. |
| `HTF_LADDER_CAP_MAX_COUNT` | `5` | Block adds when count ≥ this during a spike. |
| `HTF_SPIKE_TIMEFRAME` | `'TIMEFRAME_H1'` | Timeframe used for ATR/spike detection. |
| `HTF_SPIKE_ATR_PERIOD` | `14` | ATR period. |
| `HTF_SPIKE_LOOKBACK_BARS` | `3` | Bars over which the adverse move is measured. |
| `HTF_SPIKE_ATR_MULT` | `1.8` | Adverse move ≥ this × ATR → spike. |

### How to find every line this version added
All additions carry unique markers — grep for them to see the full footprint:
```
HTF_            _detect_htf_spike     spike_latched     spike_src_df
htf_spike       acct_balance          calculate_atr     ladder_capped
```

### Rollback

**Quick disable (no code removal):** set `HTF_PROTECTION_ENABLED = False` in
`constants.py`. The bot immediately reverts to pre-v1.1.0 behaviour.

**Full rollback — if these changes are NOT yet committed** (current state):
```bash
git checkout -- app.py strategy.py indicator.py constants.py
rm -f CHANGELOG.md            # optional: this file was added by v1.1.0
```
This restores the four files exactly to baseline `d0bc0ec`.

**Full rollback — if v1.1.0 WAS committed** (say as commit `<v1.1.0-sha>`):
```bash
git revert <v1.1.0-sha>       # creates an inverse commit, or:
git checkout d0bc0ec -- app.py strategy.py indicator.py constants.py
```

**Manual rollback (no git)** — reverse the "Change detail per file" list above:
delete the `HTF_*` block in `constants.py`; delete `calculate_atr` in `indicator.py`;
in `strategy.py` remove the 6 HTF imports, remove `balance`/`spike` from the
signature, and restore the BUY/SELL `if/elif` ladders to their original form
(remove the `catastrophe_hit`/`spike_medium_hit`/`ladder_capped` lines and the
`and not ladder_capped` guard) and drop the two `analysis_data` keys; in `app.py`
remove the 5 HTF imports, the `_detect_htf_spike` method, and every line matching the
markers above.

---

## [v1.0.0] — baseline (commit `d0bc0ec`)
Pre-existing behaviour before this changelog was introduced: RSI multi-timeframe
mean-reversion DCA basket (Fibo lot ladder gated by M1/M5/M15/H1/H4 RSI, H6 forced
close, `+$unit` basket profit target, balance-stepped unit sizing). No tail-risk stop.
