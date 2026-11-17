# Silver study: deviations and readings of the pre-registration

`PREREG_SILVER.md` (sha256 `d11df94d…6855`, checked with `shasum -c` before this step) is frozen. Its §0 names this file
`DEVIATIONS_SILVER.md`; the step brief called it `DEVIATIONS.md`, which points here.

Every entry below was written **before any strategy result on silver was computed** in this study, unless its own
date line says otherwise. "Reading" = the pre-registration is ambiguous or self-contradictory and one reading had to be
chosen; "Deviation" = something is done differently from the text.

## Written 2026-11-17, before the first candidate run (G1 smoke `ALL PASS` already logged; no P/L seen)

1. **Reading: D1 bars are UTC days.** §4.1 says "the session day (the NY day shifted +7 h) … (`external.day_bars`)".
   The named function builds UTC days, Sunday's stub merged into Monday. Gate G2 has to reproduce numbers made with
   it, and Exness's MT5 D1 bars are UTC days too. So `external.day_bars` is used. Its close is 00:00 UTC, 1 to 2 hours after
   the daily reopen, so most D1 signals fill mid-session. A Friday or month-end decision fills at the Sunday reopen.
2. **Reading: the 5-minute no-entry zones of §4.1 apply to sub-daily rules only.** §4.1 also says "Signals on a D1
   close are filled at the next M1 bar's open after the reopen". So D1 and monthly signals may fill at a reopen, and that
   fill pays the extra spread of §2.2. For every sub-daily rule (M5, M15, H1, H4, time-of-day), an entry whose execution bar
   falls in the first 5 minutes after a reopen, inside a break, or in the 5 minutes before a break is dropped. Exits are
   never dropped. Breaks are taken from the data: a silence of 30 minutes or more. For a rule that re-sends its state at
   every bar (C12 Supertrend), a dropped entry is delayed to the next bar.
3. **Reading: "every stop-order entry" (§2.2).** The rule is applied as written: every buy-stop or sell-stop fill pays one
   extra spread. That includes the Turtle breakouts and their pyramid adds (C03, C04, C29 on C03), C14, C16, C17 and C18.
   The parenthetical list names C15, C19 and C28. Their entries are market orders at a bar's open, so they are not
   stop orders and pay only the spread, unless the fill is in the first 5 minutes after a reopen.
4. **At most one extra spread per fill.** A stop fill within 5 minutes of a reopen pays one extra spread, not two.
5. **How the slippage is booked.** The extra spread is applied as an adverse shift of that fill's price (entry legs and
   exits) before any marking or sizing. This is exact for the P/L, and the floating marks include it.
6. **Spread floor (§2.1): the month median of each engine's own spread series.** That is the M1 `spread_mean` for the bar
   models and the per-second ask − bid for the tick engine, over the calendar month. This is a cost floor, so the
   look-ahead inside the month affects only the cost.
7. **Constant-% spread (§2.4):** 0.21% × the bar's bid close (the bar models), or × the per-second bid (the tick engine).
8. **"Gross"** = the same rule re-run with zero spread and no slippage.
9. **TSMOM before the data start (C01).** The 12-month return at the end of October 2018 needs the October 2017 close,
   which the store does not hold (it starts on 2017-11-01). The open of the first M1 bar stands for it. Without this, the
   first DEV month of C01 L = 12 is flat.
10. **Turtle 1N variant (C03, C04).** Only the traded stop changes to 1N. The System 1 skip filter's hypothetical trade
    keeps the 2N stop of the original rules.
11. **OCO placement (C14, C16, C18).** A side whose level the price has already passed when the orders go in is
    skipped, as in `balke.range_breakout`. Otherwise MT5 would reject the order, or the model would turn it into a
    market fill.
12. **Reading, C27.** The prereg writes "mean20(s)" and "sd20(e)" next to "β over 20 sessions". The same 20-session window
    (20 × the median number of M15 bars per session) is used for all three.
13. **Non-overlap scheduling (C13, C26, C28).** A signal inside a scheduled trade is ignored until that trade's scheduled
    exit, even if a stop closed it earlier (C28).
14. **Readings, calendar controls.**
    - C32(b): "Friday close" = 16:45 NY Friday and "Monday close" = 16:45 NY Monday, the convention of §4.1.
    - C32(c): the Wednesday session runs from Tuesday's reopen + 5 min to 16:45 NY Wednesday.
    - C32(a, d): enter at the first bar of the month and exit at the first bar of the next month.
    - C33(a): "Mon–Thu sessions" = the reopens after the Monday–Thursday daily breaks, not the Sunday reopen.
    - C33(b): 23:00 → 23:59 UTC on Monday–Thursday UTC days, only when a quote exists at 23:00 (in winter 23:00 is inside the break).
15. **Tick engine.**
    - `fast.prepare` reads the *time* (never the price) of the first quote after the window end, to time the final close. This is kept.
    - The basket designs keep their own entry rules: the engine's close-only periods of 90 s and 210 s after a break, not 5 minutes. Their fills in the first 5 minutes after a reopen pay the extra spread.
    - Stop-type basket exits, which pay the extra spread, are those with reason `stop_loss`, `stop_out` and `trailing`.
16. **C35, C36.**
    - The "`ladder_min_gap` × 0.0245" clause is a no-op, because the Live logic's `ladder_min_gap` is 0.
    - C36 = the Live logic + `ladder_multipliers` all 1 + `fc_weights` {H4: 1}, with `agree_weights` None. So entries are gated by the H4 score too, as on the slot-5 branches.
17. **Identical variants that still count in N.**
    - C34 on the C14 base (orders go in at 08:55 NY) and on the C20 base (entry 12:55 NY) cannot be touched by an 08:25–08:45 NY block. They equal their bases.
    - C29's "C05 + silver filter" equals C05 (B = 50, m = 3), whose own rule already is that filter.
    - All of these run and count.
18. **Trade counts in a split** (D1, eligibility) = closed trades whose exit falls inside the split; the end-of-data exit is not a closed trade.
19. **C09 blend** has no neighbour in "the three speeds in order", so D5 uses the split-half test for it.
20. **Mean holding time for D1** = the mean over the split's closed trades, from the first fill to the last exit.
21. **Per-unit max DD.** The peak is the running maximum of the close-marked equity. The trough is each M1 bar's worst
    mark: bid low for longs, ask high for shorts, the exit price on the exit bar of a stop. For baskets, the trough is the
    engine's per-minute equity and each basket's per-second MAE.
22. **D5 "every grid neighbour has DEV profit > 0".** It is tested at costs × 1.0, as written.

## Written 2026-11-17, after the first DEV run (disclosed; no rule or threshold changed)

23. **Bug fix, C30 and C31.** The first DEV run gave both candidates 0 trades. The gold/silver ratio read gold's last M1
    close within 15 minutes of each silver D1 close. Every Saturday-00:00 close (Friday's bar) therefore had no gold
    price, and the 250- and 20/60-session rolling windows never filled.
    - The fix: gold's last D1 close at or before each silver D1 close, which is the stated rule.
    - All 126 bar variants were then re-run. No P/L of C30 or C31 existed before the fix: 0 trades.
24. **SHORTLIST.md was regenerated once before any VAL run.**
    - The flags column had printed a pandas attribute.
    - A DSR against a pure-noise null was added as an extra, informational column. The prereg's DSR, which uses the
      cross-variant variance, is the primary figure.
    - The decision (an empty shortlist) is unchanged. The sha256 in `SHORTLIST.md.sha256` is the final file's.
25. **Empty shortlist, so §5.2 applies.** No variant ran on VAL. `val_results.csv` is a header only. `FINALISTS.md`
    freezes "Finalists: 0", and the hold-out was not touched.
