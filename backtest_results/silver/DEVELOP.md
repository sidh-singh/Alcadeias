# Silver study, step "develop": result

**No variant passed the development shortlist, so there are no finalists and the hold-out stays unused.** All 144
pre-registered variants ran on DEV (2018-11-01 → 2023-01-01) at costs × 1.0 and × 1.5, plus the constant-%
spread and gross. None met all of D1–D7. By §5.2 nothing ran on VAL, no sizing was chosen, and `FINALISTS.md`
freezes "Finalists: 0" with its sha256. The hold-out (2024-07-01 → 2026-11-13) was never loaded. The loader refuses
it unless FINALISTS.md matches its hash and names a finalist.

## What ran

- **Pre-registration:** `PREREG_SILVER.md`, sha256 `d11df94d…6855`, checked with `shasum -c` (OK) before anything ran.
  Readings and deviations are in `DEVIATIONS_SILVER.md`. Entries 1–22 were written before any result; 23–25 after,
  and they are a bug fix and formatting only.
- **Code (new modules only):** `backtesting/research/silver.py` (loader with the cut, costs, per-unit stream, the 40
  candidates, tick-engine wrapper, DSR/SPA, sizing kernel) and `silver_develop.py` (driver). No existing module was edited.
- **Gates** (`logs/gates.log`, `logs/g1_smoke.log`): all passed.
  - G1: the smoke test prints `ALL PASS`.
  - G2: the already-seen silver Turtle + votes streams, 2021-11-13 → 2024-05-13, were reproduced to the cent by the
    study's own stream code: S1 −$419.40, max DD $1,394.55, 23 trades; S2 −$1,335.00, $1,381.08, 17 trades. The
    study's sizing kernel equals `external.account` on the same paths.
  - **Published gold and BTC results were reproduced to the cent through the same code paths.** These are the FINAL10
    "new" window, 2018-11-13 → 2021-01-01:
    - gold London breakout (risk-sized): $1,624.85, 343 trades, DD 21.8014%;
    - BTC Turtle + bot votes: $2,742.20, 21 trades, DD 10.6613%.
  - G3 (March 2021): net P/L + slippage = price move × lots × 5,000 to the cent, and slippage = charged fills × spread × $50.
    This held for both bar rules and for both tick designs.
  - G4: the cut assertion fires on a bar dated 2023-01-01, and a hold-out load is refused.
  - **Hand check** (`logs/hand_check_C14.txt`): C14 COMEX ORB on 4, 5 and 8 March 2021. For each day it shows the
    range, the order levels, the fills with their slippage, and the P/L computed by hand ($−18.44, $−27.17, $−14.41).
    These equal the stream.
- **Runs:** 126 bar variants (M1 simulator / Balke kernel, continuous from 2018-11-01, data cut at 2023-01-01) and
  18 basket variants (tick engine, per second, on the DEV window). Each ran at four cost cases (×1.0, ×1.5,
  constant 0.21%, gross), and each case was scored on DEV and on its two halves. That is 1,728 rows in `dev_results.csv`.

## DEV in one table (per unit = 0.01 lot; $)

| Family | Variants | Profit > 0 at ×1.0 | Gross > 0 | Sum of profits ×1.0 | Sum gross | Best variant ×1.0 |
|---|---|---|---|---|---|---|
| TREND (D1, monthly, H4) | 55 | 21 | 31 | −4,089 | +4,100 | +618 |
| INTRADAY | 34 | **0** | 32 | −108,747 | +8,211 | −943 |
| MR (controls) | 13 | 2 | 7 | −11,761 | −635 | +162 |
| GOLD-led / ratio | 18 | 4 | 12 | −19,207 | +414 | +184 |
| SEASON (controls) | 6 | 1 | 3 | −4,428 | −18 | +388 |
| BOT (basket designs) | 18 | **0** | 4 | −425,161 | −19,658 | −1,099 |

Reference (not a candidate): buy-and-hold one unit made +$482 in DEV with a max DD of $619 (profit/DD 0.78).

- **Costs decide silver.**
  - Of the 55 variants that hold for less than a day, 44 make money gross and **none** after the spread.
    - Each round trip costs $2–4 per unit against a median DEV spread of 0.038 (about 0.2% of price).
  - The basket designs fare worse:
    - The Live logic (C35) loses about $120k per unit.
    - The slot-5 variant (C36) is gross-positive at the $10 and $20 targets (+$810, +$1,692), but loses $9–11k after costs.
- **The slow rules (D1 and monthly) are close to zero after costs, and none is robust.**

**Gate failures across the 144:** D1 trades 27, D2 profit 118, D3 quarters 120, D4 profit/DD 141, D5 robustness 125,
D6 survival 46.

## The shortlist: empty (`SHORTLIST.md`, sha256 `141bbf3f…c3c3`)

The six closest variants, by DEV annualised profit/DD, are listed for information only:

| Variant | DEV profit ×1.0 / ×1.5 | Max DD | Profit/DD | Failed | Why |
|---|---|---|---|---|---|
| C32 long December [C][M] | +388 / +375 | 121 | 3.20 | D1 | 4 trades. It is a control, and its idea came from MARKET.md |
| C01 6-month TSMOM, long only | +474 / +465 | 408 | 1.16 | D1 | 5 trades (12 needed) |
| C12 Supertrend H4 (10, 4.0) | +597 / +485 | 546 | 1.09 | D5 | its neighbour (10, 3.0) lost $239: a fit, not a plateau |
| C30 gold/silver ratio + trend | +160 / +130 | 176 | 0.91 | D3 D4 D5 | its second half lost $72 |
| C08 Faber SMA 10 (= C06 1/10 long only) | +325 / +312 | 408 | 0.80 | D1 D4 | 5 trades |
| C06 monthly SMA 1/10, long only | +325 / +312 | 408 | 0.80 | D1 D4 | 5 trades |

Other one-rule misses:
- The Turtle S1 one-unit runs (C03, P = 1) made +$263 to +$307 with a DD of $518–627, so they fail D4 (profit/DD 0.5).
- Both Bollinger fades with the 200-day filter (C23) fail D4 (0.47–0.62).
- C12 (20, 4.0) fails D4 (0.44).

The demo design (Turtle S1 + votes with pyramids, C03 P = 4 + votes) made +$618, but its DD was $2,344. That fails
D4, and also D6: the fixed 0.01-lot $2,000 account would have been wiped.

## Multiple-testing haircut (N = 144, 219 DEV weeks)

- **Expected best Sharpe from noise.** The best weekly Sharpe that 144 random rules would show is **1.30**
  annualised under a pure-noise null. With the cross-variant variance the prereg's DSR uses, it is 7.91; that figure is
  inflated by the deeply negative intraday rules.
- **Best DEV Sharpe, about equal to that.** The best DEV Sharpe is 1.26 (C32 December, 4 trades). The next best is
  0.46 (C01). The deflated Sharpe ratio is 0.00 for every variant under the prereg's definition. Against the noise
  null it is 0.44 at most.
- **Hansen's SPA test.** Over all 144 weekly DEV series against staying flat, p = 0.29 (best variant: C32 December).
  It cannot reject that the best rule is luck.

## What this means

On Exness silver in 2018–2022, no rule in the pre-registered set earned more than its costs with enough trades, robust
neighbours and survivable drawdowns. This holds for trend, breakouts, intraday momentum, mean-reversion controls,
gold-led and ratio signals, the calendar, and the bot's six basket designs.

The slow trend rules that came closest made about what buy-and-hold made, with comparable drawdowns. Their few trades
leave the evidence at noise level.

As §5.2 prescribes, the hold-out is unspent. Its clean test is still available for a new pre-registered idea. Spending
it on a near miss (C12 or C01 above) would need the owner's explicit decision and would be logged as a deviation.

## Files

- `dev_results.csv`: every variant × cost × split (DEV, H1, H2), with all §3 metrics.
- `dev/shortlist_table.csv`: every rule for every variant, plus DSR and SPA.
- `SHORTLIST.md` and `FINALISTS.md`, each with its `.sha256`.
- `val_results.csv`: header only, because nothing ran on VAL.
- `dev/streams/`: daily equity and trades of every bar variant. `dev/ticks/`: basket runs.
- `logs/`: gates, hand check, run logs.
- `DEVIATIONS_SILVER.md`. `DEVIATIONS.md` points to it.
