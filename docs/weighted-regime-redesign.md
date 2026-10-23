# Exit/Entry Redesign — Weighted Score + Regime (+ ADX)

> **STATUS: ANALYSIS / PROPOSED — NOT IMPLEMENTED.** Living design doc for the 4 `_h`
> branches (`rsimacd_btcusd1_wd_exp_h`, `rsimacd_xauusd1_wd_exp_h`,
> `rsimacd_h6_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h`). Started 2026-10-24 after a
> ~$1000 demo loss. Nothing here is in the code yet; it supersedes the current v2.6.0 exit
> logic *if/when* built. Profit-book bits = variant A (`rsimacd_*_wd_exp_h`) only.

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
- Regime engine: **A (ADX-qualifies v1)** vs **B (ADX/DI replaces v1)** — leaning **B**.
- `ADX_TREND_MIN` (~20–25?), ADX TFs (D1, H4).
- 4 TF weights; RSI>MACD within-TF option.
- 11 thresholds (table §6). Regime bands (55/45, 0) if v1 kept.
- Entry: keep a "15M not against" hard gate on top of S? (avoid entering into a 15M reversal.)
- ⚠️ Re-introduces D1/H4 into **entry** (today entry is slope-only, D1-excluded).

## 8. Rollout (build in order; demo-test each)
1. **Step 1:** weighted `S` + regime + **ladder gate + force-close** — kills the $1000 pattern (all 4 branches).
2. **Step 2:** **entry** on `S` + regime.
3. **Step 3:** **profit-book** on `S` + regime (variant A only).
Dashboard: show **S** and the **regime** (+ ADX/DI) on every loop so each action is explainable.

## 9. Plumbing needed
- Pass MACD-line sign (D1/H4) into `strategy` (v1 regime) — already computed in `app.py`.
- If ADX: recover `calculate_adx` into `indicator.py`; fetch D1/H4 as OHLC (not close-only); compute
  ADX/+DI/−DI on D1/H4; pass into `strategy`; add ADX/DI to the dashboard rows.
