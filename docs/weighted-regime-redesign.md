# Exit/Entry Redesign — Weighted Score (regime removed)

> **STATUS: the strategy is now SCORE-ONLY — the regime/tide was fully REMOVED 2026-10-27.** Living
> design doc for the 4 `_h` branches (`rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`,
> `rsimacd_h6_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h`). Started 2026-10-24 after a ~$1000
> demo loss. The redesign added a weighted **score** (§3) and a level-based **regime/tide** (§4);
> but the regime lagged and vetoed valid slope-based opens, so over 2026-10-27 it was removed from
> every decision and the exits were collapsed to single score thresholds. **⚠ §4–§6 below (the
> regime "tide", ADX, and the regime-scaled decision table) are HISTORICAL — not in the code
> anymore.** The per-step CHANGELOG (v3.0.0 → v3.5.0) is the authoritative record.
>
> **CURRENT STATE — ONE engine, the weighted slope score**  `S = 4·D1 + 3·H4 + 2·H1 + 1·M15` (−20…+20):
> - **Entry** (flat): BUY `S ≥ +ENTRY_S` (6) · SELL `S ≤ −ENTRY_S`.
> - **Ladder add**: blocked once `S` is adverse past `LADDER_S` (6) — a BUY add needs `S > −6`.
> - **Force-close**: BUY `S ≤ −FORCE_CLOSE_S` (8) · SELL `S ≥ +8`   (exit reason `force_close`).
> - **Profit-book** (variant A only): in profit, BUY `S ≤ −BOOK_S` (4) · SELL `S ≥ +4`  (reason `book`).
> - No regime/tide anywhere, no TIDE badge. The h6/variant-B pair books with the `+$unit` target (no
>   profit-book). All thresholds live in `constants.py` and are tunable. ADX (§5) stays a FUTURE idea.

---

## 1. The problem — the slope is a reversal bet, and it's regime-blind

`latest_pivot_slope` reads "pivot → now": a `+` sign = "rising since the last low" and is
**presumed** to mean *reversal* (mean-reversion from an extreme). But a `+` slope can equally be
a **pullback inside a downtrend** (a 2-bar bounce before a new lower low). The slope alone can't
tell reversal from pullback — it has **no regime/trend context**. This is the classic failure of
every mean-reversion system; this strategy is mean-reversion end-to-end (RSI pivots + a DCA ladder
that *averages into* reversals), so it's fully exposed.

### The $1000 loss, diagnosed in the current code (v2.6.0)
Open BUY, D1 + H4 both bearish, H1/M15 MACD chopping `±`. It hit the D1-against "sensitive" path:
`buy_fc = (m15r<0 AND m15m<0) AND (≥1 H1 down)`. The close is **hard-gated on `15M both down`** — the
instant M15 MACD flips `+`, the condition is false → **no close**, however bearish D1/H4 are. Two
root causes:
1. **The lowest/noisiest TF (15M) is the gatekeeper of every exit;** D1/H4 only *modulate
   thresholds*, they have no authority to close on their own. Backwards for trend capitulation.
2. **The DCA ladder adds (`BUY_MORE`) have no higher-TF gate** — they fire on per-tier RSI-oversold
   and **average down into the bear trend** (Fibo-growing size). This compounding is ~half the loss.

---

## 2. The model — "Tide + Waves" (two layers, deliberately simple)

- **Score = the waves** (fast momentum): the weighted sum of the existing pivot-slope signs. One
  number, −20..+20. A single noisy sign can only nudge it, never veto.
- **Regime = the tide** (slow bias/strength): from the highest TFs (D1, H4), using **level** (not
  slope) — and ultimately **ADX** (§5). BULL / BEAR / NEUTRAL.
- **One rule: trade *with* the tide; the tide decides how much the waves must agree.** With the
  tide → patient (ignore small adverse waves); against the tide → twitchy + never add.

This is a **net simplification** — it replaces the D1-split cascade, sensitive/normal paths, and
the `pp_trend/pp_counter` book table with one score crossing one regime-set line.

---

## 3. The Score (waves)

```
S = 4·(D1_rsi + D1_macd) + 3·(H4_rsi + H4_macd) + 2·(H1_rsi + H1_macd) + 1·(M15_rsi + M15_macd)
```
Each sign ∈ {−1,0,+1} (existing pivot-slope signs). Range **−20..+20** (neg = bearish).
- Weights `D1=4, H4=3, H1=2, M15=1` (tunable) → bigger TF dominates; M15 chop moves S by ≤1.
- **Option:** weight each TF's RSI heavier than its MACD (MACD-hist is the noisy one) to dampen noise.

---

## 4. The Regime (tide) — v1: RSI-level + MACD-line

Per big TF (D1, H4), a verdict from **where it sits** (not its slope):
- **BULL**: RSI > 55 AND MACD-line > 0 · **BEAR**: RSI < 45 AND MACD-line < 0 · else **NEUTRAL**.

Combine (**D1 leads, H4 confirms**):

| D1 ＼ H4 | BULL | NEUTRAL | BEAR |
|---|---|---|---|
| **BULL** | BULL | BULL | NEUTRAL |
| **NEUTRAL** | NEUTRAL | NEUTRAL | NEUTRAL |
| **BEAR** | NEUTRAL | BEAR | BEAR |

Data: RSI level (D1/H4) already in `rsi_mtf`; MACD-line sign (D1/H4) already computed in `app.py`
for pivot-side selection — needs passing into `strategy`. (Cheap, no new fetch.)

**Limitation of v1:** RSI-level/MACD-line give *direction* but not *strength* — they can't tell a
strong trend from a weak chop (RSI<45 happens in a harmless range too). → that's what ADX adds (§5).

---

## 5. ADX — the missing STRENGTH / trend-vs-range dimension

> **DEFERRED (owner decision 2026-10-24):** ADX is **not** part of the current build. The owner
> will experiment with it on **new branches** later. The build below uses the §4 v1 regime
> (RSI-level + MACD-line), no ADX. This section is kept as the research record for that future work.

**What ADX uniquely gives:** trend **strength** (0–100, directionless), with **direction** from
`+DI` vs `−DI`. `ADX<~20-25` = range/no-trend; `>25` = trending; `>40` = strong trend. This is the
exact thing the slope AND the v1 regime lack: **"are we in a trend or a range right now?"** — which
is *the* question for a mean-reversion system (mean-reversion works in ranges, dies in trends).

### Why ADX matters more than RSI-level/MACD-line for *this* strategy
- RSI<45 / MACD<0 = "bearish bias." But a bearish bias **in a range** is fine for buying the bottom;
  the **same** bias in a strong **trend** is the falling knife. v1 regime treats both as BEAR.
- **ADX separates them.** BEAR + high ADX = real downtrend (danger). BEAR-ish + low ADX = chop
  (mean-reversion safe). So ADX makes the tide **both more aggressive in real trends and less
  trigger-happy in chop** — it sharpens the regime both ways.

### Three ways to wire it (recommend A or B)
- **A — ADX qualifies the regime (minimal change).** A regime counts as BULL/BEAR **only if
  ADX > `ADX_TREND_MIN`** (strong trend) with matching DI/RSI/MACD direction; **low ADX → NEUTRAL**
  (range). The master table (§6) is unchanged; ADX just changes *when* a regime is "strong." Keeps
  it two-layer, no new branch.
- **B — ADX/DI *becomes* the regime engine (cleanest).** Direction from `+DI vs −DI`, strength from
  `ADX`. Drops the RSI-level/MACD-line proxy entirely (one regime indicator instead of two). ADX is
  the textbook trend-vs-range measure, so it does the job better. BULL = `ADX>min AND +DI>−DI`;
  BEAR = `ADX>min AND −DI>+DI`; else NEUTRAL (incl. all low-ADX = range).
- **C — ADX as an entry-only filter (the old v1.6.0 idea).** Don't *open* a fade when ADX is high
  against you. Weakest on its own — leaves the exit/ladder exposed — but a fine subset of A/B.

### Per-decision effect (with ADX-qualified regime)
- **Entry:** high ADX against your direction → **don't open** (don't fade a strong trend). **Low
  ADX (range)** → mean-reversion entries fully allowed — their home turf. High ADX *with* you →
  trend entry (fine, but a "dip" may be continuation).
- **Force-close / book:** high-ADX-against ⇒ BEAR column ⇒ cut fast / grab fast. Low ADX ⇒ NEUTRAL ⇒
  patient (ranges revert; don't over-cut).
- **Ladder (the single biggest win):** **averaging down is a *range* tactic.** ADX is the correct
  brain for it: **add only when ADX says range (low)** or clearly with-trend; **NEVER add into a
  high-ADX trend against you** — that is exactly the $1000 compounding. If we wire only one thing to
  ADX, it should be the ladder gate.

### TFs, cost, caveats
- Compute ADX on the **regime TFs: D1 and H4** (match the tide).
- **Cost:** `calculate_adx` was REMOVED in the v2.0.0 rebuild but exists in git history (added
  v1.6.0, Wilder/TV-compatible: TR, ATR, +DI/−DI, DX, ADX) — recover it into `indicator.py`. ADX
  needs **OHLC**, but the current D1/H4 slope fetch is close-only (`simple=True`) → the D1/H4 fetch
  must return high/low/close. Real but small plumbing.
- **ADX lags** (smoothed) — it confirms trends *after* they establish. Fine on D1/H4 for multi-day
  moves (the $1000 case); it will **not** catch a fast spike early — a stateless ATR-spike guard
  (also from v1.6.0) is the separate tool for that if needed later.

### Does ADX cause "analysis fever"? — No, *if* it replaces/sharpens, doesn't stack
- Using ADX **as** the regime (B) or **to qualify** it (A) adds **zero** decision branches — it
  makes the one tide flag smarter. That's the opposite of fever.
- ⚠️ Fever = stacking ADX **and** RSI-level **and** MACD-line **and** ATR-spike as separate gates.
  Pick **ADX/DI as the primary regime**, keep at most one cheap cross-check. Stop there.

### History note
v1.6.0 already built an ADX + ATR-spike **entry** filter (OFF by default; removed in the v2.0.0
rebuild). The owner is re-arriving at the same conclusion from live pain — and the code to recover
is in git history.

---

## 6. Master decision table (holding/trading a **BUY**; SELL = mirror: flip S, swap BULL↔BEAR)

`S` ∈ −20..+20. Regime from §4 (v1) or §5 (ADX). Starting thresholds — **all tunable on demo**:

| Decision | **BULL** (tide with you) | **NEUTRAL** | **BEAR** (tide against) |
|---|---|---|---|
| **Open BUY** (flat) | `S ≥ +8` | `S ≥ +12` | **blocked** |
| **Close BUY** (force) | `S ≤ −12` *(deep reversal; room)* | `S ≤ −8` | `S ≤ −4` *(cut on any tilt)* |
| **Book BUY** (profit, var A)¹ | `S ≤ −6` | `S ≤ −4` | `S ≤ −2` |
| **Add ladder** (`BUY_MORE`) | if `S > −6` | if `S > −6` | **blocked** |

¹ only once in profit ≥ `times × PROFIT_PROTECT_USD_PER_UNIT` (already shipped v2.6.0), checked
before force-close. Pattern: close = 60/40/20% of max adverse; book = 30/20/10%; open = 40/60% favorable.

**$1000 re-run:** BEAR regime → Open blocked / Add blocked / Close at `S ≤ −4` (deeply met in a real
down-move). Noisy M15 MACD irrelevant (D1/H4 carry S; tide is bear).

---

## 7. Open decisions / knobs
- Regime engine for THIS build: **v1 (RSI-level + MACD-line)**, no ADX (ADX deferred, §5).
- 4 TF weights; RSI>MACD within-TF option.
- 11 thresholds (table §6). Regime bands (55/45, 0) if v1 kept.
- Entry: keep a "15M not against" hard gate on top of S? (avoid entering into a 15M reversal.)
- ⚠️ Re-introduces D1/H4 into **entry** (today entry is slope-only, D1-excluded).

## 8. Rollout — ONE step at a time, shadow-first (owner must comprehend + verify each)
ADX is deferred (§5). Each step: implement → owner watches demo → confirm it matches expectation → next.
1. ✅ **Score (shadow) — DONE 2026-10-23.** `slope_score` in `strategy.py` + `_score_gauge` tile in `dashboard.py`; `analysis_data['score']`. No behaviour change (loss case = S −14).
2. ✅ **Regime (shadow) — DONE 2026-10-23.** `_regime_tf` / `_regime_combine` in `strategy.py` (RSI-level vs `REGIME_RSI_BULL`/`BEAR` + MACD-line vs 0, D1-leads-H4); `app.py` now carries `slopes[tf]['macd_line']`; `analysis_data['regime'|'regime_d1'|'regime_h4']`; `_regime_badge` "TIDE" tile in `dashboard.py`. No behaviour change.
3. ✅ **Ladder gate (LIVE) — DONE 2026-10-23 (v3.0.0).** `buy_add_ok`/`sell_add_ok` in `strategy.py` wrap the DCA adds: a BUY may add only if regime ≠ BEAR AND `S > -REGIME_LADDER_S` (6); SELL mirror. Blocks the "average down into a trend" half of the loss. `constants.py` `REGIME_LADDER_S=6`. Entry/exits unchanged.
4. ✅ **Force-close (LIVE) — DONE 2026-10-23 (v3.1.0).** Replaced the v2.x D1 cascade with the S+regime table: close a BUY at `S ≤ −12` (BULL) / `−8` (NEUTRAL) / `−4` (BEAR); SELL mirror. Reasons `fc_bull`/`fc_neutral`/`fc_bear`. Consts `FORCE_CLOSE_S_WITH`/`_NEUTRAL`/`_AGAINST` = 12/8/4. `m15_both_*` kept for the variant-A profit-book. ← profit_protect (var A) still checked first.
5. ✅ **Entry (LIVE) — DONE 2026-10-23 (v3.2.0).** `_entry_direction(regime, score)` replaces the structural `_slope_direction` for OPENING: BUY when regime BULL & `S≥ENTRY_S_WITH`(8) or NEUTRAL & `S≥ENTRY_S_NEUTRAL`(12); SELL mirror (`S≤−8`/`−12`); BEAR blocks longs, BULL blocks shorts. ⚠ re-introduces D1/H4 into entry (via the score + the tide). `_slope_direction` is kept as the dashboard's "structural" read; the panel headline now shows the live `entry_direction`. Shipped WITHOUT the optional §7 "15M-not-against" gate (still available if demo shows poorly-timed opens). ← NEXT after this: Step 6.
6. ✅ **Profit-book (LIVE, variant A) — DONE 2026-10-23 (v3.3.0).** `profit_protect` now books on score+regime: once in profit ≥ `times·PROFIT_PROTECT_USD_PER_UNIT`, close a BUY at `S ≤ −BOOK_S_WITH`(6) BULL / `−BOOK_S_NEUTRAL`(4) NEUTRAL / `−BOOK_S_AGAINST`(2) BEAR; SELL mirror. Reasons `book_bull`/`book_neutral`/`book_bear`. Replaces the v2.6.0 D1-book (`pp_trend`/`pp_counter`/`profit_protect`). Checked before the force-close (in profit, a book beats a capitulation). The h6/variant-B pair is N/A (no profit-book; uses the `+$unit` target). **← REDESIGN COMPLETE.**
Dashboard "decision view" grows with each step (S panel → +regime → +what each decision would do),
built alongside (owner grants multi-prompt for it).

## 9. Plumbing needed
- Pass MACD-line sign (D1/H4) into `strategy` (v1 regime) — already computed in `app.py`.
- If ADX: recover `calculate_adx` into `indicator.py`; fetch D1/H4 as OHLC (not close-only); compute
  ADX/+DI/−DI on D1/H4; pass into `strategy`; add ADX/DI to the dashboard rows.

## 10. Open observations (watching on demo — no code change)
- **Indecisive / "grey" slope (sign 0), esp. at a peak — raised by owner 2026-10-26; KEEP as-is.**
  A timeframe's slope reads `0` (grey on the dashboard) when: it is at a peak/plateau (current ≈ the
  latest pivot value, so the per-bar slope ≈ 0), an RSI peak formed *below* the OB band (`RSI_PEAK_OB`
  = 60, so that high is skipped as a non-OB turn), there is no qualifying pivot in the 20-bar window
  (monotonic run), or the MACD side-filter (signal-line side) excludes the only recent pivot. See
  `indicator.latest_pivot_slope` and `Strategy._slope_sign`.
  **Decision: no change — grey = a neutral "zero vote".** It contributes `0` to the weighted score,
  and the regime ignores slope signs entirely (it reads *levels*), so the live decisions (entry /
  force-close / ladder / book) lean on the timeframes that *do* have a clear sign + the tide. One grey
  TF can never, by itself, force or veto a decision — graceful degradation. (The only place a grey
  "counts against" is the dashboard-only structural `_slope_direction`, which needs strict `>0`/`<0`.)
  *Watch:* whether a grey on a heavy TF (D1 w4 / H4 w3) noticeably delays an entry/exit. If it does,
  un-taken options are: tie-break a flat slope to the confirmed pivot's side; widen the OB/OS band
  (e.g. 58/42); or fall back to the raw recent-slope sign when no banded pivot qualifies.
- **Entry thresholds lowered `ENTRY_S` 8/12 → 4/6 — 2026-10-26 (v3.3.1 var-A / v3.2.1 h6).** Entry
  was too slow to start (bullish D1/H4 slope while the level-based regime lagged bearish/neutral).
  Watching 1–2 days. ⚠ only helps in a BULL/NEUTRAL regime — a BEAR tide still blocks new longs at
  *any* score; if still no trade, the next step is removing the regime from entry (keep slope only).
