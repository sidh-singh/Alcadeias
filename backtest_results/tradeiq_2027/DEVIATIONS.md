# Deviations from the pre-registration

Each entry is written before the result it could affect exists: the date, what changed against `PREREG.md`, why, and
which results it can move. Entries are appended, never edited.

## Readings written on 28 Nov 2026 (IST) with the data and execution harness (`tradeiq2_market.py`, `tradeiq2_filters.py`), before any rule result existed

They read the plan where it is silent; they change no rule. They can move any result that uses the feature named.

1. **Weekly bars.** A merged 1D bar belongs to the ISO week of its last UTC day (its close minus one second). A last
   week that the data end cuts before its ISO end closes at that ISO end, so it is never read as closed. This is the
   same as `tradeiq2_ind_msd.weekly_bars`.
2. **Binance volume on M5 and M15.** M15 volume is the sum over our M5 bars inside the M15 bar, so a Binance slot
   inside an Exness hole belongs to no bar (study 1's DEVIATIONS 5, read for 5 minutes). The 241 klines off the
   5-minute grid on 9-10 Feb 2018 are floored to their slot (study 1's DEVIATIONS 8, read for 5 minutes). The
   check of PREREG 2 passed on 2018-01-01 to 2024-06-30 (correlation of M5 closes 0.999998; 5-minute returns 0.955 at
   lag 0, lag 0 best in every year), so no BTC row that needs volume is dropped.
3. **Event rules and the window's edges.** Candidates are decided at bars that close after the window's start and
   fill before its end (study 1's DEVIATIONS 7). Unlike a state rule, an event rule does not enter at the window's
   first bar unless an event happens there. What is open at the end closes at the last M1 close.
4. **When per-bar exits start.** Per-bar exits and tightenings act from the bar after a market entry's decision bar,
   and from the bar that contains a stop order's fill, so a stop-order trade can exit at the close of its own fill bar.
5. **Tightened stops.** A tightened level is compared with the bid (long) or the ask (short) at the open of the M1 bar
   that executes it. At or beyond that price it becomes a market exit there, booked as a signal exit with no extra
   spread. A level looser than the current stop changes nothing.
6. **Legs (the 50/50 partial exits).** An entry is dropped when its fill is at or beyond any leg's target, and the next
   entry waits until every leg is flat. A position's trade row carries the weighted P/L and the last leg's exit time
   and reason. The account uses `balke._multi_kernel` with k x weight, so legs have equal weights.
7. **Summed marks of legs and lanes** follow `balke._multi_kernel`'s event order. On a bar where one leg reaches its
   target while another stays open, the peak includes the target leg's realised profit and the other leg's close, and
   the trough sums the worst marks. This overstates a drawdown by at most one M1 bar's range times the weight.
8. **Stop orders.** Each fills at most once, and a newer order replaces an older unfilled one. An order placed while a
   position is open becomes active when the position closes, until its expiry. A fill dropped by the absolute-level
   rules (section 4) uses up the order. A fixed exit bar earlier than the fill's bar exits at the close of the fill's
   bar. An order with an absolute target runs in two passes: the fill first, then the target as a distance from the
   actual fill.
9. **R.** A trade's P/L after costs (spread and stop slippage) divided by k x its initial risk distance from the fill.
   A trade with no stop has no R unless the rule supplies its risk.
10. **Claim markets.** USTECm is 1 per lot with 2 digits; EURUSDm and GBPUSDm are 100,000 per lot with 5 digits.
    Their data ends are their stores' last ticks (13 and 15 Nov 2026); they were not refreshed.
11. **The guard** also refuses (with `HoldOutError`) any window that starts before a symbol's first scored day.
12. **Gold's 2016 warm-up.** The download built all twelve months of 2016 (340,082 M1 bars). The archive has three
    holes, all in the warm-up: 22-27 Jan, 25 Mar to 1 Apr (Good Friday and the week after) and 27-29 Jun 2016. The
    Early window starts 2017-01-01 as planned.
13. **Disclosure.** While checking the store spans the harness printed USTECm's 2026-11 `meta.json` once. It holds
    that month's lowest and highest bid (a claim market, inside the hold-out). No bar was read and no profit or loss
    was computed.
14. **Study 3 runs alongside.** Study 3 (`backtest_results/bot_filters/`) scores the bots' designs on 2021-01-01 to
    2026-11-13, which covers this study's hold-out. Before this study's `FINALISTS.md` is frozen it runs only the
    filters that use no indicator of this study (moving averages, TSI, Laguerre RSI, QQE, volume-weighted RSI,
    sessions). Its rows that read this study's ports (ribbon, structure dashboard, Heikin Ashi) wait until the
    freeze. Nothing in study 3 feeds a choice here: this study's selection is mechanical (sections 7 and 9).

## Readings written on 28 Nov 2026 (IST) with the reconciled ports and the nine rule modules, before any rule result existed

Every script was ported twice, independently. Port A (`backtesting/research/tradeiq2_ind_<key>.py`) is the one the study
uses; port B (`tests/tradeiq2_oracle_<key>.py`) is the oracle. Each pair was reconciled bit for bit on the study's bars
of both symbols (gold from 2016-01-03, BTC from 2018-01-01, to 2024-06-30), on synthetic charts and on hand cases; the
evidence, every mismatch found and how it was settled are in `porting/<key>.md`. All nine reconcile. The rule modules
(`backtesting/research/tradeiq2_rules_<key>.py`) then build the rows of PREREG 6 on port A and the harness. Their grids
match PREREG's size lines and section 7's totals: 1,543 rows, of which 1,458 are eligible (gold 738, BTC 720).

The items below are the readings the ports and the rule modules make where PREREG is silent or needs a reading. They
were written before any rule's profit or loss existed; the counts they quote are event counts on the Development
window, never profit or loss. Items `<KEY>-P<n>` come from the reconciliation, items `<KEY>-R<n>` from the rule module.
Where an item hands a choice to the study lead, the choice is the item's own proposal: BTC's MSD rows keep PREREG 3's
windows and the share of start-dependent labels is reported (MSD-P3); gold's Early-window dashboard is scored as
registered and its start dependence reported; WY-DERIVED has the 18 rows of WYCKOFF-R1 (WY-SP with X-S and X-S3, WY-CL
with X-2R50); WY-SP's provisional entries follow WYCKOFF-P3 / R2.

### BOSWaves Trend Target Ribbon (`ribbon`)

Ports, from the reconciliation (`porting/ribbon.md`):

- RIBBON-P1. 28 Nov 2026. RIB-LIT: the literal stop reads only flips of its own side (PREREG 6.1). PREREG 6.1 says that ta.lowest inside the flip branch "buffers only the lows of earlier flip bars". The reconciled ports (backtesting/research/tradeiq2_ind_ribbon.py and tests/tradeiq2_oracle_ribbon.py) read this as earlier flip bars of the same side. Why: L315-317 put ta.lowest(low, 12)[1] and ta.highest(high, 12)[1] in the two branches of a ternary inside `if flip` (L281), and Pine evaluates only the branch it takes. So ta.lowest runs, and stores the low, on bull-flip bars only, and ta.highest runs on bear-flip bars only. [1] is the call's previous result (TradingView's CW10003: it "reaches back to the last execution"). The k-th bull flip's structure level is therefore the lowest low of bull flips k-12 to k-1. The first bull flip has none and gets 0.75 ATR, by PREREG's "a missing raw risk becomes 0.75·ATR". Shorts mirror this with the highs of bear-flip bars. The other reading, in which both branches run on every flip so each call sees the flips of both sides, would change 17-24% of the 2019-2022 literal stops on every series: gold 1H / 4H / 1D 161 / 43 / 7 of 858 / 248 / 34 flips, BTC 256 / 66 / 12 of 1,271 / 322 / 49. Affects: the three RIB-LIT rows per symbol (a sensitivity row, not eligible). No flip, trend or intended stop depends on this reading.

- RIBBON-P2. 28 Nov 2026. RIB-LIT: the literal lookup before it holds 12 values (PREREG 6.1). PREREG does not say what the literal ta.lowest / ta.highest returns before the call has stored stopLookback = 12 values. The ports return na while the chart's bar_index is below 11, and from bar 11 on the lowest low (highest high) of the values stored so far, even if there are fewer than 12. Why: this is PineTS's documented account of TradingView's ta.lowest / ta.highest. It cannot be checked without TradingView. The other reading, na until 12 values are stored, gives the first 12 flips of each side 0.75 ATR. On 2019-2022 it would change no literal stop on 1H or 4H, none on gold 1D with the study's bars (gold's first 12 flips of each side fall before 2019 because the bars start in January 2016; with study 1's bars from 2017 it would change 4 of 34), and 8 of BTC's 49 1D stops. Affects: RIB-LIT on BTC 1D, Development only.

- RIBBON-P3. 28 Nov 2026. RIB-LIT: where the chart history starts (PREREG 6.1). The literal stop of the first 12 flips of each side depends on the chart's first bar, and TradingView's own chart start for XAUUSDm and BTCUSDm is unknown. The study computes the ribbon from the first bar of its own data (tradeiq2_market: gold 2016-01-03, with the 2016 warm-up months; BTC 2018-01-01). Measured on the 2019-2022 Development decision bars: any gold start from 2016-01 to 2018-01 gives the same literal stops (to 1e-9 relative; the ATR's seed leaves smaller differences). A gold start in 2018-07 would change 4 of 34 1D stops. A BTC start 3 or 6 months after 2018-01-01 would change 1 or 3 of its 49 1D stops. 1H and 4H are unaffected, flips never change, and the intended stop does not depend on the start for any start up to 2018-01. Gold's literal stops before 2019 do depend on the start: on 1D they differ until late 2018 between a 2016 and a 2017 start. Affects: RIB-LIT only; on BTC 1D early in Development, and gold's RIB-LIT in any information-only scoring of the Early window.


Rule module (`tradeiq2_rules_ribbon.py`):

- RIBBON-R1. A flip the filter refuses still closes the other side's trade. Section 5 says an event filter is checked at the entry's decision close and 'does not close an open trade, which keeps its own exits'. Section 6.1 says 'the opposite flip exits and reverses'. Read together, the opposite flip is the open trade's own X0 exit: it closes the trade even when the filter refuses the reverse entry, nothing opens there, and the rule waits for the next flip. This is coded as per-bar exit masks (every bear flip closes a long, every bull flip a short) that no filter changes. It affects every filtered RIB row (F1, F2-4H, F2-1D, FR, F3, FS).

- RIBBON-R2. ALMA-X when the close equals the ALMA exactly. Section 6.1 gives 'trend = sign(close - ALMA)' but does not say what a zero sign does. I read ALMA-X as the ribbon's own trend logic (L100-110) with strict setups close > ALMA and close < ALMA, like L97-98. A tie is no setup, so the trend keeps its side; before the ALMA exists (bar 33) there is no trend. Count: on the study's 1H, 4H and 1D bars of both symbols, from the data start to 2024-06-30, no bar closes exactly on its ALMA. This reading changes nothing there.

- RIBBON-R3. ALMA-X's stop ('the same stop rule') is the intended riskDist at the bar where the sign changes. That is the port's risk_long / risk_short, computed at every bar: the lowest low of the 12 bars before the cross bar, clamped to 0.75-3 ATR. The literal stop is refused for ALMA-X because it exists only on the ribbon's own flips.

- RIBBON-R4. The R levels are measured from the fill. Section 6.1 puts the stop 'riskDist from the fill' with 1R = riskDist, but the script draws its targets from the flip bar's close (L419-422, L621). So the 2R target (XT2, XP) and XBE's 1R trigger are also measured from the fill. They are touched the way section 4's limits are: a long's by the bid high, a short's by the ask low. The script's check marks (L626-629) read the bid chart for both sides.

- RIBBON-R5. XBE's break-even level is the entry fill. It takes effect from the M1 bar after the 1R touch, so a dip below the fill inside the touching bar does not exit. A break-even exit is charged one spread, like every stop fill (section 4).

- RIBBON-R6. A flip without a positive stop distance opens nothing. This can only happen while the ATR is missing or 0, during warm-up. Count: from the data start to 2024-06-30, every ribbon and ALMA-X flip of both symbols has a valid intended stop, and every ribbon flip a valid literal stop. So it never applies on the study's bars.

- RIBBON-R7. STK reads the signal timeframe's own ribbon trend ('one trend tool, the ribbon'), not FR's higher-timeframe ribbon. Before the first setup the trend is 0, which means flat. As a state rule (study 1's DEVIATIONS 1-2) STK takes the state at a window's first bar and closes where the state changes, so it exits when the dashboard or MA200 context turns against it. After an S1 stop it stays flat until the state changes. LO makes the short states flat. S1 is 3 x ATR(14) of the signal timeframe at the decision bar, set from the fill (ctx.atr, equal to study 1's s1_stop).

- RIBBON-R8. Not new, recorded for completeness. RIB, RIB-LIT and ALMA-X start each window flat and wait for the first flip decided inside it; a trend already running at the window start is not entered (the harness's DEVIATIONS 3). The old trade's stop is also checked on the M1 bars of the flip bar, where the script ends it at the flip without that check (porting/ribbon.md reading 17).



### Wyckoff (`wyckoff`)

Ports, from the reconciliation (`porting/wyckoff.md`):

- WYCKOFF-P1. **WY, stop S-W: "the hard level" is the script's `f_hardLevel` (28 Nov 2026, reconciled ports, before any WY result).** PREREG 6.3 sets S-W at "the hard level (the spring or UTAD extreme, otherwise the range edge) ∓ 0.15·ATR". The reconciled ports read "the hard level" as the script's own `f_hardLevel` (L723-729), the level its invalidation tests. For a long, that is the spring's extreme when the campaign holds an accumulation outcome from a spring. Otherwise it is min(origLow, rangeLow); on a selling-climax campaign the robust range low never lies below the climax low (L690-698), so a long without a spring has its stop under the climax low, not under the current range low. Shorts mirror this with max(origHigh, rangeHigh). Why: it is the script's named level, and it reproduces the specification's claim-16 geometry (median 2.7 / 4.8 / 6.8 ATR at Standard test / Aggressive SOS / LPS entries). The alternative, the plain current range edge (`range_lo` / `range_hi`), is a different level at 5 of 7 gold 1H, 3 of 4 gold 4H, 20 of 23 BTC 1H and 9 of 9 BTC 4H Standard entries of 2019-01 to 2024-06, 0.8-1.4 ATR closer to the close in the median. Affects: every WY-STD, WY-STD-L and WY-AGG row (S-W with X-S and X-S3, F0 and F2, both symbols, 1H/4H/1D), the BTC tick-volume control rows, the 0.25·ATR skip guard, the 3R targets, the primary pooled test and its placebo's stop-distance matching, and claim 16.

- WYCKOFF-P2. **WY-SP enters at the recovery bar, never at the adoption bar (28 Nov 2026, porting, before any WY result).** PREREG 6.3 enters WY-SP "at the recovery bar of a confirmed or provisional excursion". The ports' `exc` / `exc_px` mark exactly those bars (L1574): the bar on which a probe 0.15-2.5 ATR beyond the range closes back inside, whether the script confirms it (Phase C, the Spring/UTAD alert) or stores it as provisional (Phase B not yet mature, no alert). When a later breakout adopts a provisional spring (B -> D, L1654-1660), the script sets the Spring/UTAD alert bit again on the breakout bar. That bar is not a new recovery and is not a WY-SP entry. Why: the plan's wording; counting it would enter the same excursion a second time, up to max(50, 8·pLen) bars after its recovery. The specification's planning counts (D-SP: gold 1H / 4H / 1D 66 / 11 / 0, BTC on Binance 123 / 26 / 4) included these bars. The Development recovery bars are 64 / 11 / 0 and 122 / 25 / 4; the adoption bars are gold 1H 2 (Validation 1), BTC 1H 1 (Validation 2) and BTC 4H 1. Affects: every WY-SP row (F0, F2; 1H/4H/1D; both symbols).

- WYCKOFF-P3. **WY-SP: X-S after a provisional excursion (28 Nov 2026, porting, before any WY result; a reading of the rule for the study's code).** X-S exits "at the close of the first bar on which the entry's campaign no longer holds the trade's outcome in Phases C-E". At the recovery bar of a provisional excursion the campaign is still in Phase B without an outcome. Read literally, X-S closes every such trade at the next bar's close: on our bars `in_cde` is False on the bar after every provisional recovery. Provisional recoveries are most WY-SP entries; in Development gold 1H has 50 of 64, gold 4H 7 of 11, BTC (Binance) 1H 106 of 122, 4H 19 of 25 and 1D 4 of 4. Reading: for an entry whose campaign holds no outcome at the recovery bar's close, X-S starts on the first bar on which that campaign holds the trade's side in Phases C-E (an adoption at a breakout, or a later spring or terminal test of that side). Before that bar, the trade exits at the close of the first bar on which the campaign id changes (a reset or a re-seed) or the campaign holds the opposite outcome. From that bar on, it exits at the first bar with `in_cde` False, as for every other entry. An entry on a confirmed excursion is in Phase C from its recovery bar and uses X-S as written. Why: this keeps X-S's meaning (out when the structure behind the trade breaks) instead of a one-bar hold; the ports supply campaign, outcome, phase and in_cde for it. Affects: every WY-SP row (3R-or-X-S exits; F0 and F2; 1H/4H/1D; both symbols). WY-CL and the script's own entries are unaffected.

- WYCKOFF-P4. **WY-SP: the stop's extreme and its distance (28 Nov 2026, porting, before any WY result; for the study's code).** The extreme is `exc_px`, the probe's extreme as known at the recovery bar (L1551-1568). The script may extend an untested spring's extreme on later bars (L1598-1610); that moves `hard_lo` / `hard_hi`, never a WY-SP stop, which is fixed at entry like every stop of the plan. PREREG 6.3 says only "Stop beyond the extreme", where S-W and WY-CL say ∓ 0.15·ATR. Proposed: the same distance, so `exc_px` − 0.15·ATR(14) of the decision bar for a spring long and `exc_px` + 0.15·ATR for a UTAD short. Why: it is the script's own tolerance for an extreme that still holds (a test holds the spring within 0.15 ATR, L1479 and L1492), the one the plan uses for the other two Wyckoff stops. The alternative, a stop exactly at the extreme, makes every distance 0.15 ATR shorter, which also moves the 3R target. Affects: every WY-SP row (stop, R, the 3R target).

- WYCKOFF-P5. **WY, X-S: a demotion ends the hold even when the same bar re-enters Phase C (28 Nov 2026, porting, before any WY result).** The script can demote a Phase D campaign to Phase B (the highest of the last 3 closes below mid-range, L1206-1218) and, later in the same bar, re-enter Phase C with a new spring or terminal test of the same side. The ports' `in_cde` is False on that bar, so X-S exits at its close. Why: PREREG 6.3 lists "a demotion" among the breaks of X-S. The alternative, only the end-of-bar state (Phases C-E, same campaign, same outcome), keeps the trade open. On our bars it happens once: BTC 1H on Binance volume, 2023-11-22 00:00 (Validation). It is the X-S exit of the Standard and the Aggressive long of 2023-11-17 19:00, and of a WY-SP long on that campaign's confirmed spring of 2023-11-16 20:00. Affects: on BTC 1H only, WY-STD, WY-STD-L and WY-AGG with X-S or X-S3 (F0, and F2 where these entries pass it), WY-SP, Validation and the pooled test.

- WYCKOFF-P6. **WY: ties in the swing points (28 Nov 2026, porting, before any WY result).** `ta.pivothigh` / `ta.pivotlow` (L1106-1107) are read strictly on both sides, as PREREG 6.2 logs for the dashboard: a swing high must be above every other high of its window, a swing low below every other low. TradingView does not document ties. Measured on our bars from the data start to 2024-06-30: accepting equal neighbours changes 0.0-0.1% of the swing candidates and no entry of any setting on any series. On the newer side, or on both sides, it adds one secondary test on gold 1H (2023-09-13 22:00). It also moves that range's spring recovery two bars earlier, from 2023-09-14 16:00 to 14:00, at another extreme (Validation). On the older side it adds one secondary test on gold 4H without volume, in the warm-up (2018-11-07). Affects: WY-SP on gold 1H in Validation (one signal), nothing else.

- WYCKOFF-P7. **WY: swing points whose length changes from bar to bar (28 Nov 2026, porting).** The swing length `pLen` (L1105) is the campaign's `pivLen` while a campaign exists, else the ATR-adaptive `liveLen` (2-10 bars), and it can change from bar to bar. It is taken from the state at the start of the bar (L1105 runs before the update at L1162). `ta.pivothigh(high, pLen, pLen)` is read as stateless: each bar checks the window of its own `pLen`, and a swing is known `pLen` bars after its bar. The trend score's swing history (L593-594) is the series of these bar-by-bar values. Why: TradingView documents series lengths for these built-ins and asks for `max_bars_back` when they are series, which fits a look-back over each bar's own window; both ports and the scratch port read it this way. The internals are not documented, and the reading cannot be checked without TradingView. Affects: in principle every WY row (secondary tests, tests, LPS and the entries built on them); no alternative could be measured.

- WYCKOFF-P8. **WY: the engine runs from the study's data start (28 Nov 2026, porting, before any WY result; a clarification).** The script's `regime` (L1093) and its last swing bars (L1100-1101) outlive every campaign, so its outputs depend on the first bar it sees. As PREREG 6.3 says, the engine runs from each symbol's data start: gold 2016-01-03, the 2016 warm-up months of PREREG 2, and BTC 2018-01-01. Measured, counts only: gold started at study 1's start (2017-01-03) gives exactly the same outputs on every bar closing after 2018-01-01, and differs only inside 2017 (until 2017-09-03, two entry bars on gold 1H). BTC started on 2018-07-01 gives exactly the same outputs on every bar closing after 2019-01-01; started on 2018-10-01, BTC 1D on Binance volume would differ until 2019-05-03. So Development and Validation do not depend on the start. Gold's Early window does, and it is computed from the 2016 start. Affects: gold's WY rows in exam 2 (Early) only. On TradingView, whose history depth depends on the plan, the first months of a chart can differ.


Rule module (`tradeiq2_rules_wyckoff.py`):

- WYCKOFF-R1. D1. The 18 WY-DERIVED rows. PREREG 6.3 states '36 + 18 = 54 eligible rows per symbol' (section 7's 738 / 720 totals agree), but reading both 'Exit at A or B' clauses as single exits gives only 12. Reading chosen (closest to the script): WY-SP, the spring entry the video recommends, takes the script rows' two exits, X-S and X-S3 (= X-S plus a 3R target): 2 exits x F0/F2 x 3 timeframes = 12 rows. WY-CL is entered in Phase A, where no outcome is held and X-S does not apply. It gets one exit, X-2R50: a 2R target, or else a time stop at the close of the 50th bar after the entry, whichever comes first. That is 6 rows. This settles the open issue noted in the driver's COUNT_TABLE.

- WYCKOFF-R2. D2. WY-SP's X-S after a provisional spring or UTAD. At a provisional recovery the campaign is still in Phase B with no outcome, so a literal X-S would exit every such trade one bar later; most WY-SP entries are provisional (gold 1H 50 of 64, BTC 1H 106 of 122 in Development). Reading (the porting notes' proposal 3): X-S is armed from the first bar, the entry bar included, on which the entry's campaign holds the trade's side in Phases C-E, and is the normal X-S from then on. Before that, the trade exits at the close of the first bar on which the campaign is gone (a reset, or a re-seed with another id or none) or holds the opposite outcome. Confirmed springs are armed at their own bar, with one exception: BTC 1H 2023-11-22 00:00 (Validation), where a demotion on the same bar ends the hold, so that trade is armed from the next bar. Measured (counts only): of the provisional recoveries, 20 of 100 on gold 1H and 40 of 158 on BTC 1H are armed later; the rest end on a reset, a re-seed or the opposite outcome.

- WYCKOFF-R3. D3. WY-SP's stop, 'beyond the extreme'. It is exc_px (the extreme as known at the recovery bar) minus / plus 0.15 ATR, the same distance S-W and WY-CL use, and it is fixed. The script's later extension of an untested spring moves its hard level, never this stop (porting notes, proposal 4).

- WYCKOFF-R4. D4. The 0.25 ATR skip guard applies to S-W rows only, because PREREG 6.3 lists it with S-W. WY-CL and WY-SP stops sit 0.15 ATR beyond an extreme the close has already left: absorption needs a close at least 0.35 climax-ATR above the climax low (L1282), and a recovery needs a close back inside the range after a dip of at least 0.15 ATR (L1570-1572). Measured on real bars to 2024-06-30 (geometry only): the guard would skip none of them; the smallest distances are 0.38 ATR (WY-CL) and 0.39 ATR (WY-SP), both on BTC 1H.

- WYCKOFF-R5. D5. X-S is computed per entry as the first bar j > i where not (in_cde[j] and campaign[j] == campaign[i] and outcome[j] == side); this is port A's form. On every real entry of both symbols it equals port B's 'in_cde alone' (checked). An X-S, or WY-CL's bar i+50 time stop, that would fall after the last bar served is not an exit decision (-1). The trade then ends at its stop or at the window's last M1 close.

- WYCKOFF-R6. D6. The BTC control uses WY-STD's S-W stop and X-S exit with F0; only the engine's volume (Exness tick) differs.

- WYCKOFF-R7. D7. The pooled test (pooled_test_run, and pooled_test(ev) as the driver's claim-15 extra). Real trades come from WY-STD x S-W x X-S x F0 on 1H / 4H / 1D of gold and BTC, over Development + Validation as one continuous run per series, at x1.0. Each of the 1,000 placebo sets holds one random entry per real trade, matched on symbol, timeframe and side. Its decision bar is drawn uniformly from the window's bars with a seeded RNG per symbol and timeframe (seed 20261128). Its stop is the real trade's initial risk in ATR of its decision bar, times the placebo bar's ATR, measured from the placebo's own fill. It exits by time after the real trade's holding time in signal bars, counted from the entry bar to the bar of the last exposed M1 bar (minimum 1), with the stop active throughout. Placebo trades go through the same harness, in non-overlapping lanes so none is skipped as busy. The primary statistic is mean R, since R pools across symbols; total dollars per 0.01 lot is reported alongside. p = (1 + #{sets >= real}) / 1001, one-sided, with ties counted against the rule (identical arithmetic is used for the real trades and every set). The claims row says 'holds' at p < 0.05. A real trade whose holding time does not fit in the window is excluded from both sides and counted as unmatched.

- WYCKOFF-R8. D8. claim16(ev), not requested but expected by the driver's EXTRAS. It has two parts, each pooled over both symbols and the three timeframes, per window. Part 1: is the median S-W stop distance from the decision close, in ATR, at Standard test and terminal-test entries below that at Aggressive SOS entries and at LPS entries (geometry only)? Part 2: is the average R at test entries above that at SOS and LPS entries? Part 2 uses WY-STD x S-W x X-S x F0 trades for test and LPS entries and WY-AGG x S-W x X-S x F0 trades for SOS entries, at x1.0, with the entry type read from the trade tag (tag = 10 x (campaign id + 1) + kind).

- WYCKOFF-R9. Note (no change to any rule): one gold 1H Standard entry, 2023-01-13 08:00 (Validation), carries both an SOS and an LPS bit, although porting/wyckoff.md says the bits never overlap. The module follows the script's entryKind, where Standard's LPS fallback comes first (L1742/L1747), so the entry is LPS. On every real entry of both symbols this equals the reconciliation test's entry_kind.

- WYCKOFF-R10. Disclosure: while confirming that the real-data smoke test trades, I printed per-row counts of candidates, taken and busy entries, and of exit reasons (stop / target / signal / end), for the H1 2019 runs (2019-01-01 to 2019-06-30, Development) of 8 rows per symbol. Exit-reason counts are outcome information. No profit, loss or R was computed into any output, printed or stored. The test file prints nothing and asserts only bookkeeping and finiteness.



### Market Structure Dashboard (`msd`)

Ports, from the reconciliation (`porting/msd.md`):

- MSD-P1. **Dashboard: the weekly row (adds a measurement to entry 1).** The dashboard's W row is the harness's weekly bars of entry 1. A merged 1D bar belongs to the ISO week of its last UTC day, so gold's Sunday session opens the new week (428 of 443 weeks to 2024-06), and a short holiday Friday merged into the next Monday opens the following week (3 weeks). A week closes with its last day bar (gold: Saturday 00:00 UTC). Both ports' builders and the harness give the same bars (`tests/test_tradeiq2_ind_msd.py`). The alternative, the week of a day bar's open time, would move every gold Monday into the week before. It changes 4,132 / 1,265 / 248 gold Development labels (1H / 4H / 1D charts) and none on BTC. **Affects:** every MSD row on gold, MSD-F6, STK-RM / STK-RMA and study 3's MSD filter.

- MSD-P2. **Dashboard: when a closed higher-timeframe bar reaches the chart.** Model A takes each higher row from its last bar with close time at or before the chart bar's close (`htf_at`, PREREG 5). PREREG 6.2 says this "is what TradingView shows on historical bars". That holds except where no chart bar closes at the higher bar's close. Gold's Friday 20:00 4H bar, its Friday day bar and its week close at Saturday 00:00 UTC, so they reach a gold 1H chart at Sunday's first bar. TradingView shows them on Friday's last bar. The plan's definition is kept. In Development this concerns 234 / 213 / 209 gold 1H bars (4H / D / W rows) and 11 / 8 gold 4H bars. It changes 47 / 3 / 0 gold and 2 / 1 / 0 BTC labels (1H / 4H / 1D charts). **Affects:** every MSD row, MSD-F6, STK-RM / STK-RMA and study 3's MSD filter.

- MSD-P3. **Dashboard: BTC's rows depend on the data start until mid-2019.** Each row runs from the first bar of the data (BTC 2018-01-01), as PREREG 3 lets indicators read the history before a window. The map's pre-registered convergence check compares each row with the same row started 182 days later. BTC's daily row agrees from 2019-06-27 and its weekly row from 2019-07-01. Before that, 849 / 260 / 60 of BTC's Development labels (1H / 4H / 1D charts) differ between the two starts, all before 2019-07-01. Breaks of structure and BOS-trend do not differ. The map suggested starting BTC's dashboard Development window after convergence. PREREG 3 does not, and its windows are kept. The dependence is reported with the MSD results, as the share of BTC MSD-family trades decided before 2019-07-01. **Affects:** BTC's MSD-A1..A3, MSD-F4, MSD-F6 and STK-RM / STK-RMA rows, in the first half of 2019 only.

- MSD-P4. **Dashboard: gold's Early window (exam 2) is not converged until 2018-05-19.** With the 2016 warm-up, gold's rows agree with a start 182 days later only from the weekly bar closing 2018-05-19. Gold's weekly structure is first ready on 2017-01-21. Against that later start, 2,734 / 876 / 213 of the Early window's 11,798 / 3,186 / 515 chart labels (1H / 4H / 1D) differ, all before 2018-05-19. Against study 1's 2017 start, 3,962 / 1,223 / 241 differ. From 2018-05-19 on, the labels do not depend on the start. Exam 2 is scored as registered; this dependence is reported with it. **Affects:** exam 2 of a gold champion of the MSD-ALONE or MSD-FILTER family or of STK-RM / STK-RMA, and the Early-window base rate of those rows. BOS-trend is not affected.

- MSD-P5. **Dashboard: pivot ties, logged as PREREG 6.2 asks.** Pivots are strict on both sides. TradingView does not document equal highs or lows. To 2024-06, allowing an equal value on the newer side, the older side or both adds 5, 5 or 10 of gold's 6,200 1H pivots, 2 gold 4H highs, 1, 1 or 2 BTC 1H highs, and none on D or W. It changes 15, 7 or 16 gold and 0, 7 or 7 BTC 1H-chart Development labels, and none on the 4H or 1D charts. **Affects:** the MSD rows on 1H charts.

- MSD-P6. **Dashboard: the tick in the swing range.** `syminfo.mintick` (L706) is 0.001 on gold and 0.01 on BTC, the store's price digits. It matters only when the last pivot high lies below the last pivot low and the close is within one tick of the swing low. Ten times the tick changes no Development label. **Affects:** in principle every MSD row; measured, none.

- MSD-P7. **Dashboard: gold's 4H, D and W rows on UTC boundaries.** The bars are UTC (PREREG 2), not TradingView's gold session (day from 17:00 New York, 4H bars aligned to it, the week from Sunday's session). The map asked to log it, and it qualifies PREREG 6.2's "what TradingView shows". A scratch measurement with session bars from the same M1 data gives a different label at 13.4% / 18.3% / 4.4% of Development's 1H closes (1H / 4H / 1D charts), and a different long / flat / short side at 8.9% / 11.2% / 2.9%. **Affects:** gold's MSD rows, as a difference from TradingView only. The plan's bars are kept. BTC is not affected.

- MSD-P8. **Dashboard: model B for claim 14.** Model B, the live dashboard at a chart close, takes each higher row's state after its last closed bar and steps it once, tentatively, on the forming candle: its first chart bar's open, the high and low of its chart bars so far, and the chart close. Nothing is kept. Chart bars inside no higher bar take the last closed values; that happens only at a data end. Port A computes it, and the reconciliation checks it at every chart bar against port B's engine rolled back after each step. Model B's label differs from model A's on 19.1 / 18.1 / 13.7% (gold) and 19.9 / 20.0 / 15.5% (BTC) of Development bars. Claim 14's "the closed one" is read as the score the higher bar ends with: its own committed values (`row_values` at that bar), with the swing vote taken at its own close. Where a chart bar closes with the higher bar, that equals model A on that chart bar. Gold's week, its Friday day bar and its Friday 20:00 4H bar close when no chart bar closes, so there only the row's own values can supply it. **Affects:** claim 14 only (information).

- MSD-P9. **Dashboard: what MSD-F6's "row score" is.** F6 reads the chart's own dashboard: s_4H, s_D and s_W are the script's per-row scores before the weight (L710-722). Each is the sum of the structure, order-block, gap and swing votes, and the swing vote uses the chart's close (L1330). On a 1H chart, s_4H can therefore change from one 1H bar to the next inside a 4H bar, while its other three votes stay those of the last closed 4H bar. The map's other reading, "the row's structure is -1", is not used. **Affects:** MSD-F6 only.


Rule module (`tradeiq2_rules_msd.py`):

- MSD-R1. MSD-F6, 'all score below 0'. A row's score is calcBiasForTf (L710-721) without its weight: struct + order block + fair value gap + swing, in [-4, 4], the port's s_<row>. It is read from the signal chart's own dashboard (model A), so the swing vote uses the chart close (L705-708, L1330). The test is strict: a long is flat only while every veto row is < 0, a short only while every one is > 0. A row at 0 does not veto, and neither does a row with no closed bar yet (it scores 0, L703). The veto rows are 4H, D and W on the 1H and 4H charts, and D and W on the 1D chart. The 1H row of a 1H chart takes no part. The video says 'If the 4hour, the daily, and the weekly all say bearish, I don't take a long'. The script shows no bias per row, so 'says bearish' is read as a score below 0, as the PREREG writes it. My veto shares match the reconciliation's record exactly (porting/msd.md section 6, e.g. gold 1H 6.4% / 16.5%).

- MSD-R2. MSD-A3 trades both sides, as MSD-A1 does: long at BULLISH (+2), short at BEARISH (-2), flat otherwise. The PREREG says 'as A1, at BULLISH or BEARISH only'.

- MSD-R3. BTC's VWRSI base is study 1's 'VWRSI-RV' row (Binance BTCUSDT spot volume); gold's is the tick-volume VWRSI. The BTC MSD-FILTER ids therefore carry the token VWRSI-RV, e.g. BTCUSDm|4H|MSD-FILTER|MSD-F6|VWRSI-RV|R2|S1.

- MSD-R4. Base states of MSD-F4 / MSD-F6: they are computed with study 1's own functions (tradeiq.lines_of, tradeiq.raw_state, tradeiq_market.s1_stop) on the study-2 market. On gold that market starts in 2016, study 1's in 2017. Tested: every line and the S1 distance are bit-identical on both symbols from 2019-01-01 to 2024-06-30, so the scored states are exactly study 1's. The only differences sit inside study 1's own warm-up: at most 57 bars of a series, all closing on or before 2017-03-29, and S1 differs in its last bits until 2018-09-14 (1D). This touches only gold's Early window (exam 2), where study 1 has no result to pair with.

- MSD-R5. Pairing (study1_ids). An MSD-F4 / F6 row is paired with every study-1 F0, F1 and F2 row of the same indicator, family, stop and timeframe: on 1H F0, F1, F2-4H, F2-1D; on 4H F0, F1, F2-1D; on 1D F0, F1. Study 1's F3 rows are not paired, because the PREREG names only F0, F1 and F2. All 360 pairs per symbol exist in study 1's grid.csv.

- MSD-R6. BOS-trend's F1 is applied as a state filter, since BOS-trend is a state rule. The state is 0 before the first break; that happens only in the warm-up, never from 2019 (tested). BOS-trend runs with S1 only, as the PREREG says.

- MSD-R7. All 150 rows per symbol are eligible and their info is ''. Section 6.2 marks none 'not eligible' or 'information only', and section 7's totals of 738 gold and 720 BTC eligible rows include all of them.

- MSD-R8. Section 4's absolute-level rules have nothing to act on here. All 150 rows are state rules run by M.state_exec with no overlay, which is study 1's tradeiq_market.run exactly. They have no absolute levels, targets, break-even, legs or per-anchor / per-day / per-coil limits. S1 (3 x ATR(14), set from the actual fill) is the only stop; it is tested at x1.0 and x1.5.



### Swing Profile (`swing`)

Ports, from the reconciliation (`porting/swing.md`):

- SWING-P1. **Swing Profile, W1 / W2: "while the forming leg is up".** PREREG 6.4 does not restate what this means. It is the spec's definition (3.5): the forming leg is up when its stored swing high is on a later bar than its stored swing low (`tradeiq2_ind_swing` f_dir = +1), and down when earlier (-1). When both stored swing points are the same bar, the leg has no direction (f_dir = 0) and W1 / W2 do not trigger. That happens after an outside bar that was both the 50-bar high and the 50-bar low and was confirmed on both sides by the next bar. With one bar, neither the leg's swing low (W1's stop) nor its swing high (W1's target) is defined. On a flip bar, and until the new extreme is confirmed (usually the next bar), the stored pair is still the leg the flip just finished, so f_dir shows that leg, as the script's own forming leg does. Affects W1 and W2 with every filter, and their 50% placebo. No-direction bars in 2019-2022 (Development decision bars): gold 1H 46 (2 episodes, after the FOMC hours of 2019-05-01 and 2022-09-21), BTC 1H 115 (4 episodes), none on 4H, and 29 more BTC 1H bars in Validation. On those bars, 2 / 6 (gold) and 34 / 15 (BTC) have the long / short touch-and-hold shape. In the windows after a flip, these long / short bars have the shape: 17 / 14 on gold 1H, 7 / 2 on gold 4H, 25 / 25 on BTC 1H and 5 / 3 on BTC 4H. Of them, 6 / 10, 5 / 1, 16 / 17 and 5 / 2 are on the flip bar itself. A rule that also required the script's isDownMove side would drop them.

- SWING-P2. **Swing Profile, a finished leg's side (W3, claim 12).** A finished leg's side (legs.dir) is that of its flip, as the script colours and labels it (l.99, l.181): a flip to a new 50-bar low finishes the up leg (+1), a flip to a new high the down leg (-1). This holds even when the stored swing points run the other way; start_bar / end_bar are the older / newer stored point. The two disagree only when the flip bar is itself both a new high and a new low. The stored pair is then still the previous leg's, and two consecutive legs can carry the same pair, POC and delta with opposite sides. Affects W3 (the 'new direction' after such a flip, and the one-trade-per-anchor bookkeeping when two legs share an anchor) and claim 12 (which legs count as up legs), on BTC 1H only. In 2019-2022: one leg against its geometry, and two one-bar legs whose profile is a single outside bar (flips of 2019-03-15 12:00 and 2020-08-05 12:00 UTC). The first is the FOMC hour, 2022-09-21 18:00 UTC: it re-finishes, as 'up', the down leg the 17:00 flip had finished. In Validation there is one more of each (2023-09-24 18:00, 2023-09-07 20:00).

- SWING-P3. **Swing Profile, delta% and total (FD, claim 12).** A leg's delta is the script's (l.183-187): (buy - sell) / total, summed over the volume bins. A bar's volume counts in every bin it lands in: usually two, one at a bin midpoint or in the outer half of an edge bin. Green candles are buy; red candles and dojis are sell. The ports return the delta as a fraction; the label shows it x100. Why: it is the number the script's label shows, which is what the video's 'a leg up with weak buying' reads. The alternative counts each bar's volume once over the leg. On 2019-2022 it gives another sign on 1 gold 1H finished leg (the down leg flipped 2019-12-19 17:00 UTC) and 1 BTC 4H leg (the up leg flipped 2021-09-20 08:00). It also gives another FD verdict on 10 of 1,083 gold 1H and 2 of 1,846 BTC 1H touch-and-hold forming bars, and nothing on gold 4H. Affects the FD rows of W1-W3, and claim 12.

- SWING-P4. **Swing Profile, tied POCs of a finished leg (W3).** When bins tie at the maximum, a finished leg's POC is the tied level nearest the close of its flip bar, and it stays that leg's POC (legs.poc). The flip bar is the bar at which the leg and its POC first exist, so its close is PREREG 6.4's 'current close' then. Every tied level is in legs.poc_all. The forming leg's tie is re-chosen at every bar with that bar's close. An exactly equal distance goes to the lower bin; that never occurs in 2019-2024H1. The alternative re-chooses a finished leg's tie at every later bar from legs.poc_all. It can move W3 on the tied legs of 2019-2022: 7 on gold 1H, 13 on BTC 1H, 1 on BTC 4H and none on gold 4H. On 4, 9 and 1 of them, the tie nearest the flip close is not the lowest tied bin.

- SWING-P5. **Swing Profile, the history it runs on (calc_bars_count = 2000, l.6).** The script runs on the study's whole history from its first bar (gold 2016-01-03, BTC 2018-01-01), so ta.atr(200), and with it every bin size, is seeded there. Why: PREREG 3 lets indicators see the history before each window, and this is the only reading that gives every bar one value. TradingView runs the script on the chart's last 2,000 bars, which re-seeds the ATR 2,000 bars before the bar a live user looks at. Measured on the 2019-2022 Development bars: the ATR differs by at most 1.6e-4 relative. The bin count, and so the forming POC, changes on 2 / 3 / 10 / 5 bars (gold 1H / 4H, BTC 1H / 4H), never on a flip bar and never in a delta's sign. One of those bars has the touch-and-hold shape under both readings: the gold 4H bar opening 2019-04-02 12:00 UTC, a short. Affects at most that bar's W2 stop (POC + 1.5 ATR) and 2R target.

- SWING-P6. **Swing Profile, the POC's price.** The POC is the drawn line's level, math.avg(binLow, binHigh) = (binLow + binHigh) / 2 (l.146-154). It is not the bin-assignment midpoint binLow + binStep / 2 (l.132). Why: it is the line the trader sees. The two differ only in the last bits, on about a quarter of the bars: at most 4.5e-13 on gold and 7.3e-12 on BTC. No touch-and-hold shape changes on any 2019-2022 bar. Affects the W2 / W3 stop and target levels by at most 7.3e-12; no trigger.


Rule module (`tradeiq2_rules_swing.py`):

- SWING-R1. R1, one trade per swing anchor = one candidate per anchor. The candidate is the anchor's first touch-and-hold bar whose levels exist and that the row's filter allows. If that candidate is busy (a trade is open) or dropped by PREREG 4 (fill at or beyond its stop or target), the anchor gets no trade, and a later touch of it is not tried. Why: the harness executes one fixed candidate list for every window and both costs; feedback on whether an earlier touch filled would make the list differ between x1.0 and x1.5 and between windows. The first pullback to the level is also the event the video describes. An anchor whose first touch comes before a window's start has no candidate in that window. Anchors: W1/W2 longs use the forming up leg's stored swing low (ls_bar) and shorts the stored swing high (hs_bar), unchanged while the leg extends; W3 uses the finished leg (its flip bar). Development candidates with F0: W1/W2 227 / 61 on gold 1H / 4H (from 1,083 / 284 touch bars) and 326 / 73 on BTC (1,846 / 400); W3 161 / 42 on gold and 214 / 47 on BTC.

- SWING-R2. R2, the filter comes before the one-per-anchor rule. A touch refused by F2, LO or FD is no entry and does not use up its anchor, so a later allowed touch of the same anchor can be the candidate. A filtered row's candidates are therefore not always a subset of the F0 row's.

- SWING-R3. R3, 'while the forming leg is up' = the forming leg's geometry f_dir (the spec's 'confirmed high newer than confirmed low'; porting reading 1). There is no trigger while both stored points are one outside bar (46 gold 1H and 115 BTC 1H Development bars). On a flip bar, and until the new extreme is confirmed, the stored pair is still the just-finished leg, so W1/W2 can trigger with the script's flag already against the trade. Such a trade's 'flip against' is the next one after its decision bar, because per-bar exits act from the next bar. W1/W2 x F0 Development candidates in such windows: gold 9 / 2 (1H / 4H), BTC 8 / 2; for the placebo W1/W2 x F0: gold 28 / 4, BTC 41 / 4. Requiring the flag to agree would drop them.

- SWING-R4. R4, W3's window is the bars after the flip bar up to the next flip bar (excluded), with one candidate per finished leg. The flip and the leg's POC are known only at the flip bar's close, so the flip bar's own low or high reached the level before either was known. Reading the window from the flip bar on would make the flip bar itself (a bar through the POC) the first touch for 58 / 22 F0 legs on gold 1H / 4H and 113 / 19 on BTC. The touch is W1's bar shape in the new direction. The spec's extra condition (the close already past the POC at the flip, map 3.5) is not in the PREREG and is not applied: 56 / 12 (gold) and 61 / 14 (BTC) W3 x F0 candidates sit on legs whose flip close had not passed the POC, where the first touch is a close through the POC rather than a pullback to it.

- SWING-R5. R5, W3 exits only at its stop or its 2R target: it is not 'as W1', and the PREREG names no flip exit. A W3 trade can therefore still be open at the next flip, which makes the next leg's first touch busy (R1).

- SWING-R6. R6, FD's leg is the one whose level the rule trades: the forming leg at the decision bar (f_delta_pct) for W1/W2, the just-finished leg (legs.delta_pct) for W3. A long needs delta > 0, a short delta < 0; 0 or NaN allows neither. For a W3 short after an up leg, this means that leg's delta must be below 0 ('a leg up with weak buying', the same way claim 12 reads the warning). Consequence: a finished leg's delta has its own direction's sign in 93-97% of Development legs (against it: gold 14/318 1H and 6/88 4H, BTC 34/458 and 3/108). W3 x FD therefore keeps only 4 / 1 Development candidates on gold 1H / 4H and 16 / 1 on BTC, below the 30-trade minimum. W1/W2 x FD keep 219 / 58 (gold) and 308 / 73 (BTC) of F0's 227 / 61 and 326 / 73. The alternative reading for W3 (the forming leg's delta) would keep most W3 trades.

- SWING-R7. R7, the levels are those of the decision bar and never move. W1's stop and target are the stored swing low and high prices at that bar, even if the forming leg later extends; a touch whose target is not beyond its stop is no entry (never happens in Development). W2/W3's stop is the level -/+ 1.5 x PREREG 5's ATR(14) of the decision bar, not the script's ATR(200); 1R = |fill - stop| from the actual fill, and x1.5 recomputes it.

- SWING-R8. R8, the placebo level is the same leg's 50% level, computed as (lo + hi) / 2 like the port's 'fifty' (also for the forming leg: (f_lo + f_hi) / 2). Everything else is as in the POC row: the anchors, W1's swing stop and target, level -/+ 1.5 ATR with 2R for W2/W3, the exits, and filters F0 and F2. It reads the same profile, since swing points and flips do not depend on volume.



### Session Hunter (`session`)

Ports, from the reconciliation (`porting/session.md`):

- SESSION-P1. **Session Hunter: the 1H history of the script's EMA200.** The script's 1H trend (htfE, its L145) is computed on every 1H bar of the study's market from the data start: gold 2016-01-03, BTC 2018-01-01, USTECm 2020-06-01, EURUSDm and GBPUSDm 2017-11-01. It is read at the chart bar's open, as PREREG 6.6 says, and started from its first close. PREREG 6.6 fixes when htfE is read but not how much 1H history it is computed on, and a TradingView chart uses whatever 1H history it loads. Why: the longest history is the closest to a converged EMA, and it is the history the two ports were reconciled on. Effect, measured against 1H bars cut at 2019-01-02: the HTF direction differs on 536 / 182 gold bars (M5 / M15, the last on 2019-02-26) and on 539 / 183 BTC bars (the last on 2019-01-06). Of the Development K2 signals, 10 / 10 (gold) and 6 / 5 (BTC) differ, all before 2019-01-24. The EMA's start (first close or SMA) gives bit-identical htfE from 2019 on gold and BTC. On USTECm, which has 484 1H bars before its Development start, the two starts differ by at most 1.7e-4 of the price and change no signal. Rows: every Session Hunter row that reads HTF (the K2 core rows, K2 x E3, the Custom and Nasdaq presets, claim 10's USTECm rows), in January 2019 only (USTECm: early July 2020).

- SESSION-P2. **Session Hunter: the Monday variant (information only).** PREREG 6.6 asks for a 'variant that gives Monday Friday's levels'. It is built by replacing pWk ('the previous trading day was a weekday') with 'a weekday has finished since the data start', in the PD setup and the YC confirmation only. So every weekday trades the levels of the last finished weekday: Monday those of Friday, and likewise a Tuesday after a Monday without bars. A holiday Monday that opens at 18:00 keeps its two-hour stub as Tuesday's 'yesterday', as the script does. Why: it is the smallest change that gives Monday Friday's levels, and it leaves every other day and setup as coded. The two ports wrote it two ways ('pdh exists' and a pWk that stays true once set) and give identical rows. Effect: Development K2 PD signals go from 188 to 234 (gold M5), 158 to 193 (gold M15), 117 to 147 (BTC M5) and 93 to 116 (BTC M15); 47 / 36 / 30 / 23 of them fall on Mondays. No other setup changes. Rows: the information-only Monday-variant rows.

- SESSION-P3. **Session Hunter: the cancels at entry are the script's own, measured on the chart's bid open, E3's included.** PREREG 6.6 keeps 'the cancels at entry ... as coded' and gives E3 as 'cancelled when it is less than 1R away', without saying from which price the 1R is measured. The study applies the port's cancelled (the entry bar opens from 16:00, starts a new day, or opens at or beyond the stop) and, for E3, exit_reason_liq == 'cancel_lt_1R'. Both are measured as the script measures them: from the entry bar's bid open, with risk = |open - stop| (L431-439). PREREG 4's drop of a fill at or beyond its stop applies on top. Why: they are the script's cancels as coded. On every K2 signal of Development the fill's M1 open is the chart entry bar's open, so the two references differ only by the spread, and only on longs. Effect: with the 1R measured from the fill (a buy at the ask), E3 would cancel 95 / 67 more of the Development K2 signals on gold (M5 / M15) and 188 / 120 more on BTC, all longs, against 507 / 748 and 415 / 596. The other cancels change nothing in Development: no K2 entry opens from 16:00, starts a new day, or opens or fills at or beyond its stop. Rows: K2 x E3 on both symbols and timeframes. The E1 and E2 rows apply the same cancels, with no effect in Development.


Rule module (`tradeiq2_rules_session.py`):

- SESSION-R1. THE TIME EXIT (every exit mode). The script exits at the open of the first bar from 16:00 New York (L456-457), or on a new trading day at the previous bar's close (L454-455), whichever comes first after the entry bar. Here both become an exit decision at the close of the bar before that bar (the Entries' exit_bar), filled at the next M1 open. Normally that is the 16:00 bar's open. Across a data gap (an early close, a weekend) it is the first M1 bar after the gap, where the script would book the last close. E2 and E3 have the same time exit, as in the script.

- SESSION-R2. E2'S 2R IS MEASURED FROM THE ACTUAL FILL: 2 x |fill - stop|, the harness's target_r, R as in DEVIATIONS 9, the same as the ribbon and Wyckoff rule modules. The script draws TP2 from the chart's bid open (L436: open + d*2*risk). The level is identical for shorts (a sell fills at the bid) and three spreads further away for longs. The x1.5 run recomputes the target from its own fill.

- SESSION-R3. E3 FOR THE BREAKOUTS (AB, OR). The plan's 'opposite side of the swept range' exists only for the fades. For a breakout, E3's target is the script's tgtRef, the broken side plus one range width (L403), as coded. It is used as an absolute level, measured from the fill.

- SESSION-R4. THE CANCELS AT ENTRY ARE THE SCRIPT'S OWN DECISIONS ON ITS BID OPEN (porting/session.md section 8, reading 3). They are the port's 'cancelled' (closeT, new day, risk<=0, the open at or beyond the stop) and E3's 'less than 1R away' (exit_reason_liq == 'cancel_lt_1R'), both measured from the entry bar's bid open with risk = |open - stop| (L431-439). PREREG 4's rules on the actual fill apply on top: the harness drops a fill at or beyond the stop or the target, each cost on its own fill. For a long whose bid open is at or below the stop while the ask is above it, the script cancels where PREREG 4's rule alone would not (tested).

- SESSION-R5. THE 30 TREND ROWS REPLACE THE CONFIRMATION, THEY DO NOT GATE THE ENTRY. 'K2 x E1 with the 1H EMA200 replaced by F2-4H, F2-1D or F3' is read literally: the filter's side (allow_long - allow_short of tradeiq2_filters.allow, at the signal bar's close) takes the HTF confirmation's place inside f_conf (L319). As with the EMA, a bar the filter refuses does not end the setup, and a later bar of the window may still signal. PREREG 5's after-the-fact event gate would instead lose the day, because the script's setup is done at its first signal. This is what the port reconciliation also ran.

- SESSION-R6. THE MONDAY VARIANT: PD x K2 x E1 on M5 and M15, 2 rows per symbol, eligible False, information only. It uses the port's monday_friday_levels=True (porting/session.md section 8, reading 2). The plan gives no row count. These rows are the script's default confirmation set and exit on the only setup the quirk touches (no planned row uses YC).

- SESSION-R7. THE CLAIM ROWS (PREREG 8 claim 10). 'PD + HTF' is the PD setup with the HTF confirmation alone (no FVG), held to 16:00, on USTECm M5 and M15. This matches the author's 'previous-day sweep with the 1H trend held to the close' and the port reconciliation's configuration. With the Nasdaq preset on USTECm M5 and M15 and the Forex preset on EURUSDm and GBPUSDm M15, that makes 6 rows, all eligible False. The plan names no E2 or E3 rows on the claim markets, so there are none; 'E1 against E2 and E3' is read on gold's and BTC's grid, as the driver does. USTECm's 1H EMA200 uses the 1H bars from its data start (2020-06-01).

- SESSION-R8. THE FOREX PRESET has one setup, so its one-lane portfolio gives exactly the trades and scores of the core row AS x K3 x E1 (tested identical). Both rows are kept because the plan numbers both.

- SESSION-R9. The script's 1H EMA200 is computed on every 1H bar of the market from its data start and read at the chart bar's open (porting reading R7, as reconciled). No volume is read, because no planned row uses the RV confirmation.

- SESSION-R10. THE SMOKE TEST SPAN. Gold, BTC, EURUSDm and GBPUSDm use 2019-01-01 to 2019-06-30 as asked. USTECm uses 2020-07-01 to 2020-12-31 instead: it has no 2019 bars, and its Development starts 2020-07-01. That span is inside its Development window and far from the hold-out.

- SESSION-R11. Variant.info is the harness's string field. Information-only rows carry the string 'information only (...)' (truthy) rather than the literal True, as the ribbon and Wyckoff modules do. Every other row has info ''. eligible is False exactly on the information rows.



### LuxAlgo ORB (`orb`)

Ports, from the reconciliation (`porting/orb.md`):

- ORB-P1. **ORB-CX on M15 is the 08:30-09:00 range.** PREREG 6.5 names the COMEX-open range 08:20-08:50 New York for both timeframes. The reconciled ports follow the script's session test (l.87, `time(timeframe.period, session, tz)`), which puts a bar in the session when the bar OPENS inside it. 08:20 is not on the 15-minute grid, so on M15 the session's bars are the ones opening at 08:30 and 08:45: the range covers 08:30-09:00 and the first post-session bar is the 09:00 bar. On M5 the range is exactly 08:20-08:50. The alternatives would change most M15 sessions of 2019-2022 (1,030 sessions). Taking every bar that overlaps 08:20-08:50 (08:15-09:00) changes 795 ranges and 193 first breakouts. Taking only bars wholly inside (08:30-08:45) changes 784 ranges and 489 first breakouts. Affects the four ORB-CX rows on gold M15 (O1 and O5, with F0 and F2-4H); not the M5 rows.

- ORB-P2. **The ORB's day reset is the feed's own trading day: gold 17:00 New York, BTC 00:00 UTC.** The script ends its day, its hit window and its labels when the daily bar changes (`ta.change(time("D", "", timezoneInput)) != 0`, l.88, 147, 246). With an empty session string the timezone input cannot move the daily bar, and PREREG 6.5 does not say which day that is. The ports take TradingView's conventions. Gold's day starts at 17:00 New York with daylight saving, so the reset falls on the 18:00 reopen and on the Sunday open. BTC's day starts at 00:00 UTC (19:00 New York in winter, 20:00 in summer). This sets the span in which hits, raw breakouts and the first breakout are counted, from the 10:00 bar to the reset. It moves no label, no entry and no trail exit before 16:55 New York. Measured on 2019-2022: midnight on the session clock would instead change the hit flags of 176 of 1,031 gold sessions and 232 of 1,042 BTC sessions, and the first breakout of 21 / 32 gold and 4 / 3 BTC sessions (M5 / M15), with no label changing. A 17:00 New York day for BTC would change the hit flags of 193 sessions and 6 first breakouts per timeframe. Affects O4 and its LV control (the causal hit rates) and claims 6 and 8; not O1-O3 or O5.

- ORB-P3. **Claim 6 counts a first breakout only if its bar closes by 16:00 New York.** The reconciled ports report the day's first breakout as the script's alert condition: the first close beyond the range from 10:00 to the day reset, labelled or not. On BTC it can come after the 17:00 window. Claim 6 asks whether the 16:00 close is beyond the range on the side of the first breakout. That can be tested only when the first breakout's bar closes by 16:00, so a session whose first breakout comes later counts as a session without a breakout. In 2019-2022 this concerns 0 (M5) and 2 (M15) gold sessions and 12 and 13 BTC sessions; 6 of the BTC sessions per timeframe have their first breakout after 17:00. Affects claim 6 only.

- ORB-P4. **O4's hit rates count a target the way the script does.** A target counts once per session, at its first touch from the 10:00 bar to the day reset. The denominator is the sessions the script counts (`totalSessions`), which includes a session whose range a data hole wiped. So a touch after the 16:55 flat time still counts, as on the script's dashboard, although an O4 trade is flat by then. On BTC, 35 to 68 of each level's first touches in 2019-2022 come after 16:55 New York; on gold at most two. For "after past breakouts in that direction", the ports keep only each target's first touch. In 0-3 gold sessions and 1-6 BTC sessions per level in 2019-2022, that touch comes before the label of that side. The rule module must state whether such a session counts as reached after the breakout, for example by measuring again from the label bar on the bars. Affects O4 (and its LV control) on both symbols and timeframes, and claim 8.

- ORB-P5. **An ORB session with missing bars keeps the range of the bars it has.** This follows the script. A data hole inside the session shortens the range to the bars that exist. A hole from inside the session into the next trading day makes the session count with no range at all (the reset on its end bar runs first, l.147 before l.181), so it can give no breakout and no trade. In 2019-2024H1 this happens only to gold's ORB-CX. On 2021-03-02 (M5) there is one 08:20 bar and then no data until Wednesday 19:00, so the session counts with no range. On 2023-11-22, in Validation, M5 has only the 08:20, 08:25 and 08:45 bars and M15 only the 08:45 bar. The 09:30 sessions of both symbols are complete from 2019 on; gold's one short 09:30 session, 2016-05-18, is warm-up. Affects the ORB-CX rows (O1, O5) on 2023-11-22, on both timeframes.

- ORB-P6. **The ORB's HV tag uses TradingView's reference arithmetic for the average.** HV means the breakout bar's volume is strictly above `ta.sma(volume, 20)` with the bar included (PREREG 6.5). The average is summed as `pine_sma` does it (x[i] / 20 added from the newest bar, study 1's order), and a bar is LV while fewer than 20 bars exist. Integer tick volumes often equal their average exactly, so another order of addition can flip a tag at such a tie. In 2019-2024H1 no label of any planned HV, LV or HV + F2-4H row flips (gold on tick volume, BTC on Binance volume). One gold M15 label of the UTC-5 control flips (O1, which does not read the tag), and one BTC label per timeframe flips on Exness tick volume, which the study does not use. In principle this can move the HV, LV and HV + F2-4H rows; in Development and Validation it moves none.

- ORB-P7. **O1's and O5's trail use the ORB port's ATR, not the harness's `atr14`.** The script's trail is `low - 2 * ta.atr(14)` (for a short, `high + ...`), ratcheted bar by bar (l.258, 275, 282). The reconciled ports compute `ta.atr(14)` with the reference update `alpha * tr + (1 - alpha) * previous` (study 1's `tradeiq_ind.atr`). `tradeiq2_market.atr14` instead uses `external.wilder_atr`, `(previous * 13 + tr) / 14`. The two agree to 2e-15 relative. On the study's bars to 2024-06-30 the trail differs in its last bits on 331-1,512 bars per series and configuration, and no bar's trade state changes. The rule module therefore reads the port's `trail` / `active_dir` (or its `atr`) and does not rebuild the trail from `atr14`. Affects the trail exits of O1 and O5, and only at an exact tie of a close with the trail.


Rule module (`tradeiq2_rules_orb.py`):

- ORB-R1. Candidates are the script's labels: the first close-crossover of each side per day in the 09:30-17:00 display window. They count only if the bar closes by 16:00 New York and before the session's flat bar. A later re-cross of the same side is never a candidate, even when the first one was refused or busy.

- ORB-R2. 'No new trade while one is open' is read as the row's own position. With F0, O1 equals the script's own trades exactly (tested on real and synthetic bars). Under a filter, a refused label opens nothing and blocks nothing, so the other side's later label can trade; the script itself would not trade it. The script's order (bear branch before the trail exit) applies to O1 and O5: a label on the bar whose close exits the trade by its trail opens nothing. O2-O4 exit inside bars, so a trade stopped in a bar is flat by that bar's close.

- ORB-R3. Flat time: the exit decision is at the close of the last chart bar of the session's New York date closing at or before 16:55 (the 16:50 bar on M5, the 16:30 bar on M15), filled at the next M1 open. On an early close that fill is the first M1 bar after the break, so the trade is held over it. To 2024-06-30 this affects 91 of gold's 2,181 sessions (US holidays) and 5 of BTC's 1,693 (data holes). A label at or after the flat bar is dropped (at most one per configuration).

- ORB-R4. O2 and O3 targets are the script's u1/u2 (d1/d2): the range edge plus 1 or 2 widths. The stop is the far edge of the range. Both are absolute levels measured from the actual fill, per PREREG 4. No zero-width range occurs to 2024-06-30.

- ORB-R5. O4's hit rates. A past breakout is a session's label of that side decided by 16:00, whatever the row's filter and whether taken or busy. T_k counts as hit when a chart bar after the label bar, up to and including the flat bar, reaches it. Rates use sessions before the decision only; with fewer than 60 past breakouts, or no level at 50% or more, the target is T1, else the furthest level at 50% or more.

- ORB-R6. O5: OCO stop orders placed at the close of the range's last bar (10:00), live from the first post-session bar until 16:00. The buy triggers when the ask reaches orHigh, the sell when the bid reaches orLow. Stop at the far side. 'Exits as O1' means a trail started at the chart bar containing the fill (that bar's low - 2 ATR), first able to exit at a later close, plus the flat time. No order on a zero-width session or one with no bar after the range. One trade a day.

- ORB-R7. HV on O5. The 'breakout bar' of a touch entry is read as the chart bar containing the fill, whose volume is known at its close; an LV fill bar ends the trade at that close (next M1 open). This breaks PREREG 5's 'a filter does not close an open trade' for this one case. The alternative, gating the fill on the last closed bar's HV (tradeiq2_filters.fill_masks), reads a different bar's volume; the lead may prefer it. F2-4H, F2-1D and LO on O5 are checked at the placement close (gate_orders).

- ORB-R8. TIGHT is read as Session Hunter's own test (SH l.65-66, 191-194, 211, 324-325): width < 0.5 x SH's adr, the mean high-low of the last up to 10 finished weekday SH days (at least 5). It is read at the range's last bar; strict inequality, and a missing adr skips the session. It keeps 93% of gold's and 98% of BTC's sessions to 2024-06-30, so it is nearly a no-op. The other reading, half the mean opening-range width of the last 10 sessions, is not SH's computation and was not used.

- ORB-R9. ORB-CX: O5's orders run from the COMEX range's end (08:50 on M5, 09:00 on M15) to 16:00. On M15 the range covers 08:30-09:00, because sessions are defined by bar open times. The decision window and flat time are unchanged.

- ORB-R10. The UTC-5 control changes only the script's clock: the range, the display window and the session weekdays. The 16:00 cut and 16:55 flat time stay New York times. The BTC 7-day control is O1 x F0 with sessions on every day.

- ORB-R11. O1 has no stop, so its trades have no R.

- ORB-R12. BTC's HV tag uses Binance 5m volume, summed over our M5 bars on M15; a bar with no kline has volume 0. The HV test is the port's: strict, with SMA(20) including the bar.

- ORB-R13. Claims. Claim 6: the 16:00 close is the close of the last chart bar closing by 16:00; 'often' means more than half of the breakout days, with a second part 'more often than beyond the other side'. Claim 7: HV against LV on O1-O4 x M5, M15 from the results (most pairs), plus HV/LV geometry marked as information. Claim 8: the dashboard's rate over 2 x sessions (both sides pooled) against O4's after-breakout rate per level; 'differ' means a two-proportion z-test at 5%. Claim 9: the literal clock's range starts at 10:30 New York on every daylight-saving session and on no other (geometry), and New York O1 x F0 makes more net than the UTC-5 control on both timeframes (results).

- ORB-R14. When an O5 order is known: the port counts a session on its first post-session bar, which opens at the instant the range's last bar closes. An order therefore exists in the data once that bar does, and cannot fill before that bar's first M1 bar. The causality test dates orders by that bar's open.

- ORB-R15. Disclosure: one exploratory print showed the port's days frame for gold's first three sessions (2016-01-04 to 06, warm-up, never scored). It included the script's own entry and exit bookkeeping prices for three trades. No profit or loss was computed or looked at; every other print was counts, times or geometry, all before 2024-07-01.



### Harmonic & Chart Patterns (`patterns`)

Ports, from the reconciliation (`porting/patterns.md`):

- PATTERNS-P1. **Harmonic & Chart Patterns: ties in the zigzag's 5-bar test (L541-542).** TradingView does not document which bar `ta.highestbars` / `ta.lowestbars` return when two values in the window are equal. Both reconciled ports, and the planning pass's port, let the newest bar win, as PineTS does. So a high equal to the window's highest counts as a 5-bar high, and the same for lows. A tie cannot move the live swing, which needs a strictly higher high or lower low (L546, L558), so it matters only when the latest swing is on the other side. Measured over the 2019-2022 decision bars, the other reading (the oldest bar wins) changes the test on 7 / 2 / 0 gold bars (1H / 4H / 1D) and 6 / 0 / 0 BTC bars, and moves 2 gold 1H and 4 BTC 1H swings. The only events it changes are one more confirmed first hit on gold 1H (a Bear Three Drives) and 5 of gold 1H's 2,025 forming instances. Affects every HP row on 1H through those events; nothing on 4H or 1D.

- PATTERNS-P2. **Harmonic & Chart Patterns: the forming instance and its first bar (PREREG 6.7, 'the first bar of each forming instance').** An instance is the pattern id plus the bar indexes of its fixed swings Q1..Q(n-1), without the live D, so it exists only while that D is the live swing. When the pattern stops holding and holds again while D is still live, it is the same instance, not a new first bar (gold 1H 2019-2022: 30 of 2,025 instances return, 37 times in all). HP-HF reads the forming first hit, which is the pattern the script draws and its forming alert names (L808-813). It enters on the first bar on which an (id, swings) key is the first hit (gold 1H: 1,144 entry bars; with the chart ones these are the planning map's 321 instances a year). HP-CF reads every chart id, including chart patterns hidden behind a harmonic first hit, as the planning map's C-F row says. It enters on the first bar of each chart key over all hits (port A's `first_bar_of_instance`; gold 1H 160 instances, 139 of them as first hits). On one bar all harmonic hits point the same way and share the plan: every bearish harmonic needs Q2 above Q3 and every bullish one below, and the plan reads only Q0, Q3 and the direction. All chart hits of one direction also share their plan (it reads Q1 and Q2), so a rule enters at most once per bar and side. Why: HP-HF's 'forming harmonic' is the script's forming pattern, what a live user sees, and the planning counts that sized these rows were made this way. The alternative for HP-HF, first bars over all hits, gives 1,290 entry bars on gold 1H instead of 1,144 (215 bars only in that reading, 69 only in this one), and it counts the duplicate ids 8 and 19. Affects HP-HF and HP-CF.

- PATTERNS-P3. **Harmonic & Chart Patterns: the confirmed controls (HP-HC, HP-CC).** The confirmed alert names one pattern, the first hit in registry order (L783, L793-795). So HP-HC reads the confirmed detections whose first hit is a harmonic, and HP-CC those whose first hit is a chart pattern (gold 1H 2019-2022: 840 and 110 of 950). A chart pattern behind a harmonic first hit raises no chart alert (23 such detections on gold 1H). The decision close is the close of the detection bar (port A's `close`). It is not `c0`, which is the close of D's bar that the chart predicates read (L781). The rule 'skipped when the close is already beyond TP1' reads the decision close. Affects HP-HC, HP-CC and claim 19's comparison.

- PATTERNS-P4. **Harmonic & Chart Patterns: HP-CS's 'every condition except the breakout close'.** It is the chart predicate without its last conjunct: the close above Q2 for a bullish id, below Q2 for a bearish one. That conjunct is the only place the close is read in L322-480, which a test checks on the source. It is evaluated on the forming state with `tradeiq2_ind_patterns.armed(pid, out['forming_q'])`, and the neckline is p2 = Q2. It reads only the fixed swings Q1..Q8. So it is known at the close of the bar where the latest swing was added, and it stays unchanged until the next swing is added; at that point the same swings go to the confirmed detection. The stop order at p2 is placed at the close of the first bar on which its key is armed, and it is valid while the key stays armed. The key is the id plus the bars of Q1..Q(n-1), as for a forming instance. Gold 1H has 312 armed chart instances in 2019-2022, BTC 1H has 421. Affects HP-CS.

- PATTERNS-P5. **Harmonic & Chart Patterns: which D the time stop counts from ('30 bars after D') for forming entries.** D is the live swing at the decision close (the row's `b0`; for HP-CS, the live swing when the order is placed). A later move of the live swing does not move the time stop. Confirmed rows have a fixed D. Affects HP-HF, HP-CF and HP-CS.

- PATTERNS-P6. **Harmonic & Chart Patterns: the patterns of HP-DRAWN.** The script draws a confirmed first hit only if it does not overlap by more than half a pattern still on the chart (L767-792; the newest 15 are kept). Its alert is never gated (L793-795). HP-DRAWN (information only) is computed on the same confirmed first hits as the controls: harmonic first hits as HP-HC, chart first hits as HP-CC. Each pair then differs only in the entry time. The subset the chart draws (port A's `drawn`; gold 1H 641 of 950 in 2019-2022) is reported beside it. On our bars no first hit is suppressed by any drawn pattern except the newest, so the 15-pattern history never matters. Affects HP-DRAWN and claim 18 only (information rows).


Rule module (`tradeiq2_rules_patterns.py`):

- PATTERNS-R1. F2's timeframe. PREREG 6.7's sizes (27 = 3 targets x 3 filters x 3 timeframes, 12 = 2 x 3 x 2, 4 = 2 x 2) leave one F2 per timeframe, while section 5's table allows both F2-4H and F2-1D on 1H. I used the next higher timeframe: F2-4H on 1H and F2-1D on 4H. On 1D, HP-HF uses F1, as 6.7 says. Sections 6.3, 6.4, 6.8 and 6.10 spell F2 out the same way. In the ids the filter token is the filter module's own name (F2-4H, F2-1D, F1), so swapping it for F0 gives each row's unfiltered twin; params['filter_slot'] keeps the PREREG's slot (F2).

- PATTERNS-R2. What an instance is, and its first bar (porting notes 8.2). HP-HF reads the forming FIRST hit: an instance is the key (pattern id plus the bars of Q1..Q(n-1)), entered on the first bar where that key is the first hit, once per key. A return while D is still live is the same instance, and a moving D does not make a new one. HP-CF reads every chart id, including chart patterns hidden behind a harmonic first hit, at the key's first bar over all hits (first_bar_of_instance). All chart hits on one bar read the same Q2 and close, and bullish ids need close > Q2 while bearish ids need close < Q2. So they always share direction and plan: one entry per bar, tagged with the lowest id. Harmonics never read the close, so an HP-HF first bar is always D's bar.

- PATTERNS-R3. Confirmed controls (porting notes 8.3). HP-HC takes detections whose first hit is a harmonic, HP-CC those whose first hit is a chart pattern, one entry per detection. A chart pattern behind a harmonic first hit raises no chart alert. The decision close is the detection bar's own close, not c0 (the close of D's bar that the chart predicates read).

- PATTERNS-R4. The skip rule. 'Skipped when the close is already beyond TP1' is read as AT or beyond, on the decision close, for HP-HF, HP-HC and HP-DRAWN's harmonic rows. The plan gives the chart rows (CF, CS, CC) no skip rule, so they only have section 4's drop: an entry whose fill is at or beyond its stop or target. In Development the rule skips 85 of gold 1H's 1,144 HP-HF entry bars and 401 of its 840 HP-HC alerts; on BTC 1H, 146 of 1,546 and 562 of 1,182. These counts are asserted in the real-data test.

- PATTERNS-R5. '30 bars after D'. D is the swing in the row at its decision: the live D at the decision close for forming rows (a later move of the live swing does not move the time stop), the live D at the order's placement for HP-CS, and the fixed D for confirmed rows. The exit decision is the close of bar D + 30. A decision at or after that bar is not entered; this never happens in Development. When bar D + 30 lies beyond the data there is no exit bar, and the window's end closes the trade, exactly as a longer run of the same window would.

- PATTERNS-R6. HP-CS's stop order (porting notes 8.4), several parts:
- 'Every condition except the breakout close' is tradeiq2_ind_patterns.armed, the chart predicate without its last conjunct. It reads only the fixed swings Q1..Q8.
- The order is placed at the close of the bar where the key is first armed, which is always a bar that adds a swing.
- It is cancelled at the earlier of two moments: the close of the bar where the next swing is added (the key is no longer armed), and the close of bar D + 30 (the plan's horizon).
- Keys armed on one bar share p2 and h, so there is one order per bar.
- If keys of both directions are ever armed on one bar, the order carries both sides and one cancels the other. This never happened in Development, on random walks, or in 12 million random swing sets; a unit test with a stubbed armed() covers it.
- The order is placed even when the close is already beyond p2, because the plan adds no condition. It then fills at the next M1 open, per section 4's max(level, ask at the open). That is 85 of gold 1H's 312 armed keys in Development and 127 of BTC 1H's 421; both counts are asserted. The alternative, skipping those keys, would make HP-CS pure 'entry at the neckline' and differs by about 27% of the keys. The lead may want to log the choice.

- PATTERNS-R7. HP-CS's filter is checked at the order's placement close (gate_orders). A filter that turns later neither cancels the order nor closes the trade.

- PATTERNS-R8. HP-DRAWN ('the plan as drawn back at D, with look-ahead'; porting notes 8.6). It is a market entry decided at the close of D's bar, with the confirmed row's levels, TP1, F0, the 30-bar time stop, and its control's skip rule (harmonic rows only). The look-ahead is the confirmation delay (t_conf > the decision bar).
- The 'ALL' rows take the same confirmed first hits as HP-HC and HP-CC, so each pair differs only in the entry time.
- The 'SHOWN' rows take the subset the script's overlap gate actually draws (drawn, L785-792). That is what an old chart shows, and it is the porting notes' 'drawn subset reported beside it'.
- That makes 6 harmonic + 4 chart rows per symbol, eligible=False, with info starting 'information only'. The PREREG gives no number for these rows.

- PATTERNS-R9. Tags and notes. Each entry is tagged with its pattern id (0-37), which is carried to the trades. The 50/50 rows are written as two half legs (TP1 and TP2), per PREREG 4's partial exits. Their info carries PREREG 4's note that live trading needs at least 0.02 lot per unit. HP-HC and HP-CC are eligible, with info 'control' (PREREG 7: controls can qualify).



### Heikin Ashi trend statistics (`ha`)

Ports, from the reconciliation (`porting/ha.md`):

- HA-P1. Heikin Ashi statistics keep the script's cap of 5,000 streaks per colour. PREREG 6.8 computes the streak statistics 'using all history from the data start'. The reconciled ports (backtesting/research/tradeiq2_ind_ha.py and its oracle) read this as where the history starts, not as dropping the script's own cap (l.131-132): each colour's percentile and rare age use its latest 5,000 finished streak lengths. Why: it is the script as written, and the plan does not say to drop the cap. Effect, measured to 2024-06-30 (counts only): the cap binds on 1H only, BTC from 2022-04-21 and gold from 2022-11-28. Against an uncapped history the percentile (pct_below) differs on 4,500 BTC and 398 gold 1H Development bars and on 9,659 and 6,594 Validation bars. The rare age (rare_now) differs on no bar. The hold-out was not computed. Affects: claim 5's calibration on 1H for 2023 and 2024, whose 'before the year' statistics are capped; and the M4 rows on 1H bases, only if the hold-out shows a difference. It does not affect study 3's HA-M4 exits, which run on 4H and 1D, where the cap does not bind.

- HA-P2. Heikin Ashi statistics start at the study's data start: gold 2016-01-03, BTC 2018-01-01. PREREG 6.8's 'all history from the data start' is read as the first bar tradeiq2_market.load serves, which includes gold's 2016 warm-up months (PREREG 2). Spec 4.2 had said 'gold 2017'. Why: PREREG 2 downloaded 2016 as warm-up, the harness serves gold from 2016-01-03, and study 3's filter bars start there too. Effect, measured to 2024-06-30: against a 2017-01-03 start the gold rare age differs on 12 / 12 / 10 Development bars (1H / 4H / 1D) and 0 / 0 / 2 Validation bars, and the percentile on most bars. Candles, colours, phases, streaks and every other event are identical from 2017-03-05 at the latest. This start also gives gold's Early window warmed-up candles from its first day and the 50-streak minimum from 2016 on 1H and 4H; on 1D the minimum is reached only on 2017-11-07, so no gold 1D rare age can fire in the Early window before then. Affects: gold's M4 rows on 1H, 4H and 1D (Development, Validation and the Early exam) and claim 5 on gold. It does not affect study 3: its HA-M4 exits are the BTC Turtle's, and its HA filter rows read only the colour.

- HA-P3. The first, left-censored streak counts in the Heikin Ashi statistics. The first streak starts at the first bar given, so its true start and length are unknown. The reconciled ports count it like any other finished streak, as the script does (l.121-130). Why: it is the script as written, and the plan says 'all history'. Effect, measured to 2024-06-30: leaving it out would change the rare age on 11 gold 4H bars and 1 gold 1D bar of Development, on none of Validation, and on nothing on gold 1H or any BTC series. The percentile moves slightly on most bars. Affects: gold's M4 rows on 4H and 1D, and claim 5 on gold.


Rule module (`tradeiq2_rules_ha.py`):

- HA-R1. Whose events count (M2, M3, M4). A position reacts only to events of a streak of its own colour. A long tightens after INDECISION follows bullish STRONG candles, and after bullish WEAK candles. It exits when a bullish streak reaches its rare age. A short mirrors this. M1's flip is against the position by definition. Why: the video talks about the move you are in ('strong candles, you hold; a run of weak candles or indecision after a strong run, you tighten up'); the script names each alert by the candle's colour (l.290-298); study 3's HA-M4 reads it the same way. The other reading (either colour) would tighten a long when a bearish run tires, which is the opposite signal. In Development the events split about evenly by colour (bull / bear): INDECISION after STRONG gold 1H 500 / 473, BTC 1H 733 / 650; rare ages gold 1H 245 / 236, BTC 1H 440 / 431.

- HA-R2. 'That bar's low' (M2, M3) is the signal bar's own bid low, and for a short its high (spec 4.5: 'that bar's real low'). Under reading 1 this is also the Heikin Ashi low: an INDECISION candle has wicks on both sides, and a WEAK candle has a wick against its colour. A test checks this on random bars. Break-even is applied with the harness's tighten_be, so the level is the tighter of the fill and the bar's low or high.

- HA-R3. When M3 fires. It tightens at every WEAK candle of the position's colour that is at least the second in a row (weak_run >= 2), each time to the tighter of break-even and that candle's own low; a looser level changes nothing. The other reading (weak_run == 2, once per run) differs only where a third WEAK candle follows: 6 gold 1H, 8 BTC 1H and 4 BTC 4H Development bars (counts only).

- HA-R4. HA-AND ('the base, entered only while the Heikin Ashi colour agrees') gates the base's own entries at their decision close, for both kinds of base. The candle of that bar must have the entry's colour (a tie counts as bullish, l.85). It never closes a trade. A refused entry is not taken later: the base stays flat until its own state changes, as after a Heikin Ashi exit. For a ribbon base this is PREREG 5's event gate at the flip (rib_exec's gate). For a study-1 state base, the row's state is the base's state on the episodes (runs of one non-zero state) whose first bar had the colour, and flat on the others. This is causal, and a window that starts inside an episode takes that episode's verdict. HA-AND's trades are therefore a subset of the base's trades, unchanged (tested). Not chosen: the colour as a state filter (it would close trades when the colour turns, which is M1 with re-entries), and a delayed entry at the first agreeing bar of an episode (an entry the base never makes). Measured on Development entries (counts only), HA-AND refuses: gold QQE 3 of 347, LaRSI 77 / 377, RSI 54 / 234; BTC LaRSI 3 / 26, VWRSI 13 / 54, TSI 20 / 178. On the ribbon bases it refuses at most 2.5% of flips, and none on 1D. So several HA-AND rows are near copies of their bases.

- HA-R5. HA-H1 and HA-H2 are state rules with no stop. The plan's map says so for H1 (spec 4.5: 'A state rule, so run works as it is'); H2 is the colour itself; PREREG 6.8 names no stop. So F2 / F1 act on them as state filters (PREREG 5): the position closes when the filter turns against it and can reopen mid-streak. HA-H1's state is the streak's colour from its first STRONG candle (ev_first_strong, which can be the flip candle) to the streak's end; it is flat between a flip and the new streak's first STRONG candle. F2 = F2-4H on 1H, F2-1D on 4H and F1 on 1D, as PREREG 6.3, 6.4 and 6.7 spell 'F2'. With F0, the event reading (enter at the first STRONG candle or at the flip, exit at the next flip) gives the same trades except at a window's first bar.

- HA-R6. The overlays act from the bar after the entry's decision bar (harness DEVIATIONS 4). A flip, an INDECISION, a WEAK pair or a rare age on the decision bar itself is not acted on, because the trade is not yet open at that close. So M1 holds a long entered on a bearish flip bar until the next flip to bearish, and M4 a long entered on its streak's rare-age bar until the next bullish rare age. Measured on Development entries: a flip against the entry on its own decision bar on at most 7.4% of a base's entries (BTC VWRSI 4 / 54; ribbon bases at most 1.9%). A rare age of the entry's colour there on at most 2.7%, except BTC 1D LaRSI (2 / 26).

- HA-R7. Break-even is the entry's actual fill: the ask paid for a long, the bid for a short, and at x1.5 that run's own fill. It is the level RIB-XBE uses; a stop there is charged one extra spread like every stop fill. With PREREG 4's rule, a break-even above the bid (a losing long) is a market exit at the next open, so M2 and M3 close a losing trade at the event. This bites often on BTC 1H: in the 2019-H1 smoke run, BTC 1H RIB-LS M5 applied 11 tightenings and 42 were already crossed (market exits); these are counts, not P/L. On an S0 base (gold's three finalists, BTC TSI) the tightening sets the trade's first stop.

- HA-R8. Study 1's finalists are used exactly as their rows (indicator, family, filter, stop). They are built with study 1's own functions (lines_of, raw_state, htf_sides, allowed_of, apply_filter, s1_stop) on the study-2 market. BTC's VWRSI R3 finalist reads Exness tick volume, as study 1's row does. The base is the finalist itself, not study 1's Binance-volume VWRSI-RV row (that one is what PREREG 6.2's MSD-filter rows use). Gold's market starts in 2016 here and in 2017 in study 1. States and S1 are equal on every 2019-H1 bar (tested). Over 2019-2024, the MSD module's test shows the QQE / LaRSI / RSI states and S1 equal, and MA200 is a windowed sum of identical closes. BTC's two markets start together.

- HA-R9. Heikin Ashi is computed on the base's own bars from the study's data start (gold 2016-01-03, BTC 2018-01-01). It keeps the script's cap of 5,000 streaks per colour and counts the history's first streak: the reconciled port's readings 8.1-8.3 in porting/ha.md, unchanged.



### COIL (our stand-in for Coil Breakout AI) (`coil`)

Ports, from the reconciliation (`porting/coil.md`):

- COIL-P1. **COIL: what replaces an armed coil.** PREREG 6.9 keeps a coil armed "for 12 bars after its last squeeze bar, or until a new coil replaces it" but does not say when a new coil exists. Both ports (reconciled in tests/test_tradeiq2_ind_coil.py) read it as a newer run of squeeze bars reaching 6 bars, which is a coil by the plan's own definition from that bar on. It replaces the armed coil on that bar, not later when the newer run ends and its own coil arms. Replacing only at the arming would keep the old coil armed through the newer run's later bars. That would add 3 / 1 / 0 (gold 1H / 4H / 1D) and 8 / 1 / 1 (BTC) Development breakouts, and 1 / 0 / 0 and 4 / 0 / 0 in Validation (counts only). It can move every COIL row (COIL-RIB, COIL-MA, COIL-0; 36 per symbol).

- COIL-P2. **COIL: the replacement bar.** On the bar where a newer run reaches 6 squeeze bars, the old coil is dropped before that bar's close is tested, so its box cannot break out there. Why: a coil's state at a close follows that bar's squeeze, as on the fire bar (armed because its squeeze is off), and only then is the close tested. Both ports chose this reading independently. Testing the old box first would add 0 / 0 / 0 (gold 1H / 4H / 1D) and 5 / 0 / 1 (BTC) Development breakouts. Those are the BTC 1H bars closing 2021-09-18 05:00, 2022-03-03 16:00, 2022-09-30 15:00, 2022-10-07 07:00 and 2022-11-28 00:00 UTC, and BTC 1D 2022-08-20. It would also add one Validation breakout (gold 1H, 2023-06-07 14:00). It can move the COIL rows of BTC 1H and 1D, and of gold 1H in Validation.

- COIL-P3. **COIL: a newer run of 1-5 squeeze bars inside the armed window.** Such a run is no coil, so it neither replaces the armed coil nor pauses its 12-bar count. Its squeeze bars are armed bars and can be breakout bars. Why: PREREG 6.9 names only two early ends of the window, the 12 bars and a new coil. In Development, 11 / 1 / 0 (gold 1H / 4H / 1D) and 19 / 6 / 2 (BTC) breakouts fall on such bars. Disarming the coil at a newer run's first squeeze bar would lose 29 / 3 / 0 and 39 / 9 / 3 breakouts. Pausing the count on squeeze bars would change 27 / 3 / 0 and 30 / 7 / 3. It can move every COIL row.

- COIL-P4. **COIL: the armed window is the fire bar and the 11 bars after it, counted in chart bars.** For a run whose last squeeze bar is e, the coil is armed on bars e+1 to e+12. Bar e+1, the first bar without a squeeze (the bar that shows the run has ended), is armed and its own close is tested. A weekend or a data hole neither ends a run nor stretches the window (Pine counts bars, not time). Why: "12 bars after its last squeeze bar" read literally, and the end of a run is not known any earlier. The fire bar holds 187 / 25 / 8 (gold 1H / 4H / 1D) and 289 / 72 / 11 (BTC) of the Development breakouts. Arming one bar later would change 370 / 50 / 15 and 556 / 144 / 22 breakouts. An 11-bar window would lose 7 / 1 / 0 and 12 / 3 / 1; a 13-bar window would add 7 / 2 / 0 and 3 / 3 / 0. It can move every COIL row.

- COIL-P5. **COIL: the box spans the whole run.** "Its box is the highest high and lowest low of those bars" is read as all the run's consecutive squeeze bars, however many (the median run is 11-15 bars). The box uses highs and lows, not closes, and leaves out the fire bar. Why: "those bars" are the coil's bars, and a coil is the whole run. A box of the run's last 6 bars would change 80 / 13 / 2 (gold 1H / 4H / 1D) and 112 / 22 / 5 (BTC) Development breakouts. Its first 6 bars would change 214 / 87 / 9 and 454 / 110 / 21, and the closes 268 / 79 / 8 and 404 / 115 / 21. The box's opposite edge is also the stop, so the box sets the stop distance as well. It can move every COIL row.

- COIL-P6. **COIL: the population deviation.** "stdev(close, 20)" in the squeeze is read as Pine's ta.stdev with its default biased = true, which divides by 20. As in the reference code and study 1, a deviation of at most 1e-10 counts as 0. Why: the plan writes the squeeze in Pine's terms (PREREG 5 and 6.9). The sample deviation (dividing by 19) would change 514 / 122 / 15 (gold 1H / 4H / 1D) and 697 / 190 / 40 (BTC) Development squeeze bars, and 85 / 18 / 2 and 119 / 27 / 9 breakouts. It can move every COIL row.

- COIL-P7. **COIL: strict comparisons.** A squeeze needs the Bollinger band strictly inside the Keltner channel ("lies inside"), and a breakout needs a close strictly above or below the box ("above", "below"). From 2019 to 2024-06-30 no band touches the channel and no armed close equals a box edge, so the reading changes nothing in Development or Validation. In the gold Early window two closes sit exactly on a box edge (1H 2017-08-14 10:00 and 4H 2018-09-04 16:00 UTC). There >= / <= would change 2 and 1 breakout bars. It can move gold COIL rows in the Early window (exam 2), and any later bar with an exact tie.

- COIL-P8. **COIL: the ADX is that of TradingView's built-in DMI script.** The ta.dmi reference gives no code, so "Pine ta.dmi(14, 14) ADX" is computed as TradingView's built-in "Directional Movement Index" script does. A tie (up == down) or an inside bar gives no directional movement. The true range (ta.tr) is missing on bar 0. +DI and -DI pass through fixnan, DX divides by 1 when +DI + -DI is 0, and the first ADX value is on bar 27. Readings that are equal in exact arithmetic (ta.tr(true), another order of the scaling) differ by less than 1e-13. Giving a tie to +DM would flip the ADX >= 20 grade on 4 BTC 1H Development bars, none of them a breakout bar, and no breakout bar's ADX from 2019 comes within 0.0014 of 20. It changes no result to 2024-06-30. It could move only the ADX and ALL3 grades of COIL-RIB, where a directional-movement tie shortly before a breakout moves that breakout's ADX across 20.


Rule module (`tradeiq2_rules_coil.py`):

- COIL-R1. The plan leaves these points open; each is my reading, for the lead to log in DEVIATIONS.md. Counts are Development decisions on the study's bars, written 'gold 1H / 4H / 1D; BTC 1H / 4H / 1D', over every port breakout (338 / 75 / 15; 521 / 129 / 23). They are counts, timings and geometry only, never profit or loss.

- COIL-R2. X-TR, 'the highest close since the entry'. The entry is the fill at the first M1 open after the breakout close (PREREG 4, lines 96-98), so the trail's closes start with the bar after the breakout bar. The breakout close itself is not counted. Counting it would make the trail exit earlier on 36 / 7 / 0; 45 / 14 / 0 breakouts.

- COIL-R3. X-TR's level. The exit test is close < highest close - 3 x ATR(14), using the ATR(14) of the bar being tested. The level is recomputed every bar and never ratcheted, as the plan's words say; ORB's O1 trail (PREREG 312-313) says 'max of the previous trail' explicitly, 6.9 does not. A ratchet would move 111 / 20 / 5; 173 / 56 / 15 exits earlier. Holding the breakout bar's ATR fixed would move 211 / 35 / 8; 295 / 77 / 19.

- COIL-R4. Strictness. The trail exits only on a close strictly below its level (a short's: strictly above), for 'falls below'. The grades are inclusive, for 'at least'. No breakout from the data start to 2024-06-30 sits exactly on a grade threshold. The nearest are 2.5e-4 relative for BIG (BTC 1H), 3.2e-4 for VOL (gold 1H) and 0.0014 ADX points (BTC 1H), so rounding cannot move a grade.

- COIL-R5. BIG compares the breakout bar's range, high - low, not its true range, with the ATR(14) of the breakout bar itself (that bar's own true range included). A test pins this with a gapped bar whose true range passes but whose range does not.

- COIL-R6. VOL tests volume >= 1.5 x ta.sma(volume, 20), with the breakout bar inside its own average, as PREREG 6.5's HV and Session Hunter's vAvg do. Gold uses tick volume and BTC Binance volume (ctx.volume), which counts 0 for an hour without a kline, as study 1 did. 6 / 6 / 2 Development BTC breakouts (1 / 0 / 0 in Validation) have 1-5 hours without a kline in their 20-bar window; from 2019 on, no breakout bar is itself missing one (two are, in the 2018 warm-up). Read literally, a window with no volume at all would pass (0 >= 0); no breakout has such a window.

- COIL-R7. ADX is the port's ta.dmi(14, 14) ADX at the breakout bar, which must be >= 20. A missing ADX (bars 0-26) fails.

- COIL-R8. A breakout that the trend filter or the grade refuses opens nothing and uses up its coil. The breakout is the FIRST close beyond the box, once per coil (PREREG 445), and the filter and grades are read 'at the breakout' (447, 458), so a later close beyond the same box is not a new event. Tested with the real port on synthetic bars, where such later closes exist.

- COIL-R9. A breakout decided while a trade is open is skipped (one position per variant, PREREG 110), whichever side it is on. The plan gives the coil no reversal or opposite-signal exit, so the open trade keeps its stop, target and trail.

- COIL-R10. A breakout without a finite ATR(14) above 0 would open nothing. None exists on either symbol from the data start to 2024-06-30 (tested on real data).

- COIL-R11. COIL-RIB uses the ribbon trend of the same timeframe (tradeiq2_filters.ribbon_trend), which is +1 or -1 from the ribbon's first setup and 0 before it (0 allows neither side). It is not PREREG 5's FR, which reads the higher timeframe. It is read at the breakout bar's close, PREREG 5's decision close (lines 152-157), so a ribbon setup on the breakout bar itself counts. On 23 / 7 / 0; 54 / 11 / 1 breakouts the breakout bar is what flips the ribbon to the breakout's side; reading the bar before would refuse those. The ribbon agrees with 319 / 67 / 15; 498 / 123 / 22 breakouts (94-100%), so COIL-RIB filters out very little.

- COIL-R12. 'Set from the fill': the stop is a distance, min(max(raw, 0.75 ATR), 3 ATR), where raw is the gap from the breakout close to the opposite box edge, and it is placed from the actual fill. A fill that gaps through the box is still taken, so PREREG 4's absolute-level drop never applies to the coil, and the x1.5 run sets the stop and target from its own fill. To 2024-06-30 no fill lies at or beyond a stop drawn from the breakout close or beyond the opposite edge, so this reading changes nothing there.

- COIL-R13. X-3R's target is 3 x the stop distance from the fill (the harness's target_r). A long's target is touched by the bid high and a short's by the ask low; the stop wins an M1 bar that touches both.

- COIL-R14. Ids and tags. Ids are symbol|tf|COIL|rule|exit|grade with the PREREG's names; COIL-MA and COIL-0 carry the grade token 'none'. Params hold rule, filter (ribbon / F1 / F0), exit, grade and stop. The tag is the coil's ordinal counted from the data start; a new coil starts at an armed bar whose previous bar is unarmed or holds another box.



## Readings written on 28 Nov 2026 (IST) with the study driver (`tradeiq2.py`), before any rule result existed

The driver reads the plan as follows where it is silent (its `READINGS`, quoted as written; each names what it can
move). Reading D3's choice is made: WY-DERIVED's 18 rows are WYCKOFF-R1's (WY-SP with the X-S and X-S3 exits, WY-CL
with X-2R50), and the wyckoff module emits them.

- D1. Grid counts are checked per (module, symbol, family, eligible); RIB-LIT, the ORB controls, SP's placebo, the BTC Wyckoff control, HP-DRAWN, SH's Monday variant and the claim-market rows keep their script's family with eligible=False; rows the plan does not number are counted, not checked.
- D2. ORB controls: LV x O1-O4 x 2 timeframes, the UTC-5 clock x O1 x 2, BTC 7 days x O1 x 2; TIGHT on both symbols, ORB-CX and LO gold only (738 - 720 = 18).
- D3. WY-DERIVED = 18 rows as PREREG 6.3's size line says (its text gives 12): WY-CL's 6 plus WY-SP's 12, either as confirmed and provisional excursions or as the 3R and X-S exits; the lead picks one, the wyckoff module emits it, and the count check stops on a module that gives 12.
- D4. Only the session module is asked for USTECm / EURUSDm / GBPUSDm (claim 10); every row there is eligible=False; their Development starts as PREREG 3 says.
- D5. Ids: 'symbol|tf|...' without white space or backticks; the timeframe one of M5, M15, 1H, 4H, 1D; the family one of its module's PREREG 7 families.
- D6. Qualification: the minimum trades are PREREG 5's, counted at x1.0; rule 3 is inclusive at P/DD 1.0 and 50% positive quarters; a P/DD that does not exist (no drawdown) fails, as in study 1; not-eligible rows get q1-q4 but never qualify.
- D7. PREREG 6.3's 'insufficient events' (fewer than 15 Development trades on a WY / WY-DERIVED row) is a column and a verdict word; it changes no qualification.
- D8. The finalists' script groups come from the family (PREREG 7's list), not from Variant.script; ties between champions as between qualifiers: D+V P/DD, then Development's, then the id; a missing P/DD sorts last.
- D9. Multiple testing: as PREREG 7 says, N = every variant run on the symbol and SPA / the Reality Check over all of them (Development weekly P/L, x1.0, study 1's code); the same over the eligible variants only, for information (HP-DRAWN looks ahead and the controls are no trial of the selection); in select and again in exam.
- D10. The exam: every champion takes it (PREREG 7 'A champion passes exam 1 when'), the finalists among them; FINALISTS.md lists every champion with its role.
- D11. Run loads every market to 2024-07-01 even after the freeze, and refuses once FINALISTS.md exists, as select does.
- D12. The look-ahead checks: freeze recomputes each would-be champion's Development row on a market cut at the Development end and requires results_dev_val.csv's text; the exam recomputes every champion's D, V and D+V, and (unless --no-recheck) every variant's, on the data to the data end and requires the same text; HP-DRAWN (it looks ahead by design) is left out; a champion that fails gets the verdict 'void (look-ahead)'. A check that cuts the data at a window's end cannot see a rule that peeks at most one bar ahead (the decision at the last bar fills after the window): such rules are the ports' and the rule modules' own tests' to catch.
- D13. The code a result depends on: the harness, study 1's harness, config.py, store.py, the ports and the rule module (and Python, numpy, pandas and numba); freeze refuses when any of these or the data served differ from run_info.csv; exam and accounts refuse result code other than FINALISTS.md's unless --allow-code-change (then the files are recorded in exam_info.csv and EXAM.md) and refuse inputs whose sha256 FINALISTS.md does not record; the driver's, silver.py's and final10.py's blobs are recorded, not required.
- D14. The exam of record: exam.csv is never overwritten by a run with other result code (exam_info.csv).
- D15. The base rate: per symbol and window (gold also both), the share passing among all rows, the eligible rows, qualifiers, champions, finalists and the not-eligible rows, with buy-and-hold (every symbol) and the claim-check rows (information); results_full.csv is not written for every variant (PREREG 3 has no 'full' window; the champions' full rows are exam_full.csv).
- D16. Buy-and-hold beside the exam: study 1's DEVIATIONS 28 (P/DD above buy-and-hold's) and its exposure-matched net (time in the market x buy-and-hold's net).
- D17. Accounts: the champions and each family's best row (its champion, else its eligible row first in PREREG 7's order) over full, hold-out and (gold) Early at x1.0 and x1.5; every gold / BTC variant over 5y, 1y (both) and 8y, new (gold) at x1.0; next to them buy-and-hold of 0.01 lot and study 1's six finalists (study 1's code on this study's market) over full, hold-out and Early, and the bots' designs as study 1 rebuilt them from FINAL10's 8y trades on full and hold-out (the same spans; they cannot be rebuilt on 2017-2018: FINAL10's runs start 2018-11-13).
- D18. The account: M.account_curve with FINAL10's unit rule; its USD drawdown on the M1 marks with the trades weighted by their units; trades, win rate and profit factor per position (legs combined, lanes separate); weekly Sharpe on the weekly $ P/L (weeks from Saturday 00:00 UTC, partial first and last included, the page's definition); positive quarters and the worst quarter on the equity at calendar-quarter starts.
- D19. The page's curve: the opening row the day before the window at $2,000, then per UTC day with an M1 bar the equity at that day's last close mark; a wiped account's curve stops on the day it was wiped.
- D20. The page's fields: kind 'rule'; role finalist / champion / qualified / variant; eligible = qualifies (study 1's meaning on the page); exam = exam 1's pass or fail; label = the id without the symbol; rows that look ahead (HP-DRAWN) and the claim markets are not exported.
- D21. Partial exits (legs): 'live needs at least 0.02 lot per unit (PREREG 4)' wherever such a row is listed.
- D22. Comparisons pair rows by the PREREG's names as '|'-separated id tokens or param values (XP -> X0, XBE -> X0, F1 / F2 / F2-4H / F2-1D / F3 / FR / FS / FD / HV / HV+F2-4H -> F0, LO -> F0 on SP and ORB only, E1 -> E2 / E3, HV -> LV, O4 -> O2 / O3, a grade -> no grade); a filtered row without an F0 row is paired with its id without the filter token (SH's F2 / F3 rows with their K2 x E1 row and the script's 1H EMA200).
- D23. PREREG 6.11's combinations against the scripts alone: TIGHT -> the same ORB rule with F0, ORB-CX -> the New York range, STK -> RIB with the same side, X0, F0, WY-DERIVED -> WY-STD x X-S with the same filter; 'helps / does not help / mixed' is study 1's DEVIATIONS 30.
- D24. Claims: 'most' = more than half, a win = strictly more net at x1.0 (study 1's DEVIATIONS 31); claim 1 'ignores the noise' = fewer trades than ALMA-X in every pair and more net in most; claim 10's 'nothing held up' = at most half of the SH rows with net above 0; claim 13's removed trades = the F0 base's trades whose (entry time, side) the filtered row does not take (a delayed re-entry counts as removed), with their number and net; claim 15 reports events per year with no verdict (the plan gives no number for 'rare'); claim 17 = the share of the script's WY rows with net above 0 on 4H and 1D against 1H, with the entries per timeframe; claim 18 also compares the drawn chart patterns with HP-CC / HP-CF.

## The review of the rule modules, 28 Nov 2026 (IST), before any rule result existed

Five reviewers checked the nine rule modules against PREREG, the harness and the items above, look-ahead first; a
skeptic then tried to refute each serious finding. No look-ahead was found. Three findings were confirmed (ORB-2:
early-close days; HA-1: the streak cap; ORB-1: two items describing O4's hit rates differently) and are fixed in the
next section, with the notes that needed code (the claim functions 5, 11, 12 and 14 that the driver looks up were
missing; HA-H1 and HA-H2 ran as state rules). The other notes correct the record:

- REV-1 (COIL-R1). COIL-R1 is the rule author's preface, not a reading: COIL-R2 to COIL-R14 are the rule module's
  readings (its docstring's readings 1-12). Its counts are Development decisions on the study's bars.
- REV-2 (WYCKOFF-R2). Its '20 of 100' (gold 1H) and '40 of 158' (BTC 1H) provisional recoveries count from the data
  start to 2024-06-30, not Development (where gold 1H has 50 provisional entries of 64 and BTC 1H 106 of 122). 'The
  rest' also includes trades whose campaign is never armed and never gone: they end at their stop, target or the
  window's end.
- REV-3 (HA-R7), a disclosure. HA-R7's count of tightenings already crossed (42 of 53 M2 tightenings on BTC 1H
  RIB-LS x M5 in 2019-H1) came from a Development execution of a scored row. A crossed break-even tightening says
  that the bid was at or below the fill at that moment, so it is outcome-adjacent. No reading was chosen because of
  it: HA-R7 applies section 4's absolute-level rule as written.
- REV-4 (ORB-R7, O5 x HV). PREREG 5 says an event filter does not close an open trade, while O5 x HV closes a
  stop-order fill at the close of its fill bar when that bar is LV. Kept: a stop order's breakout bar is the bar it
  fills in, and its volume is known only at that bar's close. The other readings either look ahead (fill only on an HV
  bar) or read another bar (the order's placement bar), which is not 6.5's 'breakout bar'.
- REV-5 (ORB-P1, ORB-CX on M15). PREREG 6.5's 08:20-08:50 range is not on the 15-minute grid; M15 uses 08:30-09:00
  (ORB-P1). Kept.
- REV-6 (MSD-R4). Corrected with the code fixes below (what the test compares).


## The fixes after the review, 28 Nov 2026 (IST), before any rule result existed

The review's confirmed findings (ORB-2, HA-1, ORB-1) and its notes that needed code (the claim functions 5, 11, 12
and 14; HA-H1 / HA-H2 as event rules) were fixed; a verifier then re-derived every count below independently and
checked the code against these items. Counts are of the Development bars (2019-01-01 to 2022-12-31) or, where
named, of the bars to 2024-06-30: event geometry and sample sizes only. No rule's profit or loss was computed or read.
The harness's item keeps the label the code cites, "harness reading 15", although the harness's own section ends at 14.

- **Harness reading 15. Exits before a gap (`close_gap`), the harness side of ORB-2.** PREREG 4 fills an exit decided
  at a bar's close at the open of the first M1 bar at or after that close. When the market closes early (gold's
  early closes before the 17:00 New York break, BTC's data holes), that M1 bar is the reopen, so a rule that must be
  flat before the break (PREREG 6.5) was held over it and could gap through its stop there. `entries()` and
  `orders()` now take a per-row flag `close_gap` (default False). Take a flagged row whose own fixed exit is what
  ends the position: its `exit_bar`, or for an order the earlier of that and `on_fill`'s, at the earliest the
  fill's bar. When no M1 bar opens at that bar's close, the exit is booked at the close of the bar's last M1 bar: the
  bid for a long, the ask for a short, with no extra spread. For those exits only, PREREG 4's fill at the reopen
  becomes the last quote before the gap, so that the flat time holds. What it takes as known: whether an M1 bar
  opens at that close shows in the bars only at the reopen, and the booking takes it as known at the close. For
  gold's early closes that is the published trading schedule; a hole in the data (BTC's, and one gold session to
  2024-06-30 missing the M1 bar at the flat bar's close) could not be known then. The booking is reading 3's
  window-end exit at that close: a stop or a target touched before it wins, and every leg still open ends there. The
  marks and the accounts hold the position through that M1 bar, and the next entry may fill from the next M1 bar
  (the reopen) on. The trade row reads 'signal' (a time exit), with that M1 bar's close as its exit time; the paths
  keep 'end', which every mark and account kernel reads as an exit at a bar's close. When an exit mask falls on the
  row's own exit bar, the row's own exit decides, so it is booked at the close too; a window end inside the gap after
  the own exit bar only renames that window-end exit 'signal' and counts it (the same price and P/L). Not a gap: an
  M1 bar opening at the close, or the end of the data held. A bar whose last M1 bar lies past the window is closed by
  the window's end, as before. Otherwise exit masks, tightenings and stops are unaffected. Without a gap, or without
  the flag, nothing changes: 360 runs and 9,527 trades on synthetic gold- and BTC-like markets with breaks, weekends
  and holes are identical bit for bit to the harness before the change, at x1.0 and x1.5. Every run's counts and
  result rows gain `close_gap` (`n_close_gap`, `n_close_gap_x15`): the positions so closed, 0 when no row has the
  flag. It replaces no earlier item; readings 1-14 stand. It moves only rows whose rule module passes the flag; that
  module's own item replaces its reading of a flat exit across a gap (ORB-R16, SESSION-R12). Scope on the
  Development bars, from bar times alone: gold's last M5 or M15 bar at or before 16:55 New York closes into a gap on
  34 of 1,031 New York weekdays, its early closes (US holidays, the day after Thanksgiving, 24 and 31 December), that
  bar then closing between 12:45 and 15:00 New York; BTC's does on none of 1,042.
- **ORB-R16 (replaces ORB-R3; the review's ORB-2). Flat time.** The exit decision is at the close of the last chart
  bar of the session's New York date closing at or before 16:55 (the 16:50 bar on M5, the 16:30 bar on M15), filled
  at the next M1 open. When no M1 bar opens at that close (an early close on gold: US holidays, the day after
  Thanksgiving, 24 and 31 December; a data hole on BTC), the next M1 open is the reopen. ORB-R3 held such a trade over
  the break, against PREREG 6.5 ("Everything is flat at the last chart-bar close at or before 16:55 New York, because
  gold's daily break starts at 17:00"). Such an exit is now booked at the close of the flat bar's last M1 bar (the bid
  for a long, the ask for a short, no extra spread) and read as a time exit: the harness's `close_gap` (harness
  reading 15). A stop or a target touched before that close still wins. On an early close the bars show which bar is
  the flat bar only at 16:55 and the gap only at the reopen; booking at the flat bar's last M1 close takes both as
  known from the market's published early-close hours (not knowable for a data hole: BTC's 5 sessions to 2024-06-30,
  none in Development). The flag is set on every ORB row whose own exit decision is the flat bar, in every version
  (main, LO, ORB-CX, TIGHT, the controls): every O2-O4 entry, every O5 order (its `exit_bar` and its trail's cap), and
  every O1 entry whose trail has not fired before the flat bar (a trail firing on the flat bar's own close is the
  same decision). An O1 trail exit decided at an earlier bar keeps the next-M1-open fill, also when a hole follows
  that bar (in Development: one trade each on gold's ORB-CX M5 O1 x F0 and x F2-4H rows, 4 Aug 2021). The harness's
  flag is per order, so on O5 it also books an exit decided at an earlier bar (the trail, or HV's LV fill bar) at
  that bar's last M1 close when no M1 bar opens at its close; in Development this happens to no trade of any O5 row.
  To 2024-06-30 the flat bar is followed by a gap in 92 of gold's 2,181 09:30 sessions (ORB-R3's 91 early closes and
  one session missing the M1 bar at the flat bar's close) and in 5 of BTC's 1,693 (data holes). A bar from 10:00 to
  before the flat bar is followed by a gap in 22 / 15 gold sessions (M5 / M15; 27 / 17 on ORB-CX) and in 13 / 10 BTC
  sessions. In Development the flag moves the exit of 18 / 14 / 23 / 14 / 12 trades of gold's O1-O5 x F0 rows on M5
  and 28 / 16 / 24 / 16 / 21 on M15 (x1.5: the same except O5, 11 and 20); ORB-R3 held every one of them to the
  reopen. It moves none on BTC, which has no flat bar followed by a gap in Development. The rest of ORB-R3 stands: a
  label at or after the flat bar is dropped (at most one per configuration). Affects every ORB row on the sessions
  whose flat bar is followed by a gap (34 of gold's 1,031 Development sessions, none of BTC's), and O5 rows also
  where a gap follows an earlier exit bar (no trade in Development).
- **ORB-R17 (a wording correction; ORB-R5 stands; the review's ORB-5).** The ORB module's docstring and `describe()`
  said O4 needs "at least 60 past sessions"; `describe()`'s text goes into FINALISTS.md. The code (`o4_choice`) and
  ORB-R5 need at least 60 past sessions with a label of the trade's side decided by 16:00 New York (past breakouts
  of that side), so a session without such a label does not count toward the 60. The text now says so: "once at
  least 60 past sessions have a breakout of that side decided by 16:00 New York, else T1". No code changed; no
  result moves.
- **ORB-R18 (corrects the "Affects" lines of ORB-P4 and ORB-P2; the review's ORB-1; no code change).** O4's rule is
  ORB-R5. A past breakout is a session's label of the trade's side decided by 16:00 New York. T_k counts as hit when
  a chart bar after the label bar, up to and including the session's flat bar, reaches it. The rate is hits over
  those past labels, with at least 60 of them (`after_hits`, `o4_choice`, `o4_targets`; the same for O4's LV
  control). ORB-P4 describes the script's dashboard count instead: a target's first touch from the 10:00 bar to the
  day reset, over the sessions the script counts (`totalSessions`; the port's `hit_u1`-`hit_d3`). In the rule module
  only claim 8 reads that count, as the dashboard's unconditional rate (`hit_rate_stats`: those flags over 2 x the
  window's complete sessions), against ORB-R5's after-breakout rate. So ORB-P4 is the dashboard's reading and affects
  claim 8 only, not O4 or its LV control. Its open question is settled by ORB-R5: the hits are measured again on the
  bars after the label, so a target touched only before the label is not a hit. ORB-P2's "Affects" line is corrected
  the same way: of the spans the day reset sets (the port's hit flags, first breakout and raw breakouts), the rule
  module reads only the hit flags, in claim 8's dashboard rate. O4 and its LV control read bars up to the flat bar
  (16:55 New York at the latest), before gold's 17:00 New York reset and BTC's 00:00 UTC reset; claim 6 reads the
  labels decided by 16:00 (ORB-P3), which no reset moves. ORB-P2 therefore affects claim 8's dashboard rates only.
  No result moves.
- **SESSION-R12 (replaces SESSION-R1). The time exit (every exit mode), priced where the script prices it.** The
  script exits at the open of the first bar from 16:00 New York (L456-457), or on a new trading day at the previous
  bar's close (L454-455), whichever comes first after the entry bar (the new day first when both hold). Here both
  are an exit decision at the close of the bar before that bar (the Entries' `exit_bar`), each priced as the script
  prices it. The 16:00 exit fills at the next M1 open: normally the 16:00 bar's open; after an early close that
  reopens before 20:00 on the same trading day (gold's US holidays, closed from about 13:00 to 18:00 New York) the
  reopen's open, the trade held over the break as the script holds it. The new-day exit is booked at the close of
  the decision bar's last M1 bar (the row's `close_gap`, harness reading 15: the bid for a long, the ask for a short,
  no extra spread), not at the first M1 bar after the gap. A new trading day comes first only when no bar of the
  entry's trading day opens from 16:00 to 20:00: an early close into a weekend or a closed day (the Friday after
  Thanksgiving, 3 July 2020, 24 and 31 December) or a hole in the data. The reopen then usually opens at 18:00 of a
  later day, both a new day and from 16:00, and the new day is checked first (L454 before L456): 22 of the 30
  flagged Development K2 x E1 trades. So a gap always precedes it; on every lane (K0-K3, five setups, M5 and M15,
  both symbols, data start to 2024-06-30) no flagged exit lacks one. Whether the bar after the decision starts a new
  trading day shows in the bars only at the reopen; the booking before the gap takes it as known, as the script's
  own price does (L454-455): from the published hours for the early closes; the BTC hole of 2-3 Mar 2021 could not
  be known then. A stop or a target touched before then exits as usual, and on days without a gap nothing changes.
  SESSION-R1's "Across a data gap (an early close, a weekend) it is the first M1 bar after the gap, where the script
  would book the last close" held only for the new-day exits. Not taken: `close_gap` on every time exit, which would
  also book the same-day early closes at the last close before the break, where the script exits at the reopen's
  open (68 gold and 4 BTC Development K2 x E1 exits). Effect, Development K2 x E1 trades whose time exit falls
  before a gap (M5 / M15; event counts): gold 49 of 1,679 / 47 of 1,480, of which 16 / 12 are new-day exits now
  booked at the last close and 33 / 35 the 16:00 exit at the reopen's open, unchanged; BTC 3 of 1,358 / 3 of 1,197,
  of which 1 / 1 new-day (the hole from 2 Mar 2021 08:23 to 3 Mar 19:00 New York) and 2 / 2 the 16:00 exit (a
  missing 16:00 M1 bar on 2 Aug 2021). Per setup (new-day in brackets): gold M5 AS 8 (3), LS 15 (5), PD 4 (2), AB 5
  (1), OR 17 (5); gold M15 AS 6 (1), LS 11 (4), PD 4 (2), AB 12 (1), OR 14 (4); BTC M5 AS 1 (1), LS 1 (0), OR 1
  (0); BTC M15 AS 1 (1), LS 1 (0), AB 1 (0). A new-day trade stopped or at its target before the early close does
  not change; how many are was not counted (it reads stop hits). Rows: every Session Hunter row (all setups, K0-K3,
  E1-E3, the presets' lanes, the F2 / F3 rows, the Monday variant and the claim-market rows).
- **HA-R10 (replaces HA-P1 and the cap clause of HA-R9; the review's HA-1). All history.** The Heikin Ashi
  trend-age statistics of every HA row (HA-MANAGED M1-M5 and HA-AND, HA-ENTRY) and of claim 5 use every finished
  streak of the colour since the study's data start (gold 2016-01-03, BTC 2018-01-01), without the script's cap of
  5,000 per colour (l.131-132). PREREG 6.8 says "Streak statistics are computed causally at every bar, from the
  streaks finished before it, using all history from the data start". HA-P1 read this as where the history starts
  and kept the cap, but the plan's text asks for every finished streak. How: the rule module calls port A's
  `heikin_ashi(..., keep=None)`, a new public keyword that passes straight to the reconciled
  `_heikin_ashi(..., keep=None)` path. The port's default stays KEEP = 5,000, the reconciled contract, which study 3
  calls; nothing study 3 computes changes. Ports A and B agree bit for bit with `keep=None`, on every key and on the
  streak table, on synthetic bars (one series with 5,010 finished streaks of each colour) and on the study's 1H bars
  of gold and BTC from the data start to 2024-06-30 (`tests/test_tradeiq2_ind_ha.py`, section 4). On 4H and 1D the
  cap never binds, so `keep=None` gives the reconciled output there. Effect on the Development decision bars: the
  cap binds on 1H only, gold from 2022-11-28 and BTC from 2022-04-21. Without it `pct_below` differs on 398 gold and
  4,500 BTC 1H bars (6,594 and 9,659 in Validation). `rare_now` differs on no bar: none of gold's 481 or BTC's 871
  Development 1H rare ages, and no bar of any series from the data start to 2024-06-30. So no M4 exit moves.
  Affects: the M4 rows on 1H bases only where a later window (the hold-out) differs, and claim 5's 1H cells from
  2023 on (Validation and, for information, the hold-out). Not study 3.
- **HA-R11 (replaces HA-R5; the review's note that HA-H1 and HA-H2 ran as state rules). HA-H1 and HA-H2 are event
  rules.** PREREG 5 classes flips as events: "On event rules (flips, sweeps, breakouts, patterns): the filter must
  agree at the decision close of the entry. It does not close an open trade, which keeps its own exits." HA-R5 had
  made them state rules on the pre-plan map's word (spec 4.5): a filter turning against a trade closed it, and the
  rule could reopen mid-streak on a candle that is neither a first STRONG candle nor a flip. Now HA-H1 enters at the
  close of each streak's first STRONG candle (`ev_first_strong`, which can be the flip candle), on the streak's
  colour (LS both sides, LO longs only), and exits at the close of the next colour flip, the streak's end. A streak
  without a STRONG candle, or whose first STRONG candle the filter refuses, is not traded. HA-H2 is the colour
  stop-and-reverse: every colour flip closes the open trade whatever the filter says (an unfiltered exit mask), and
  opens the flip's side if the filter allows it at that close; the exit and the reverse entry fill at the same M1
  open. LO buys the flips to bullish and exits at the next flip to bearish. This is RIB-LS x X0's pattern
  (RIBBON-R1). There is no stop (PREREG 6.8 names none). F2 stays F2-4H on 1H, F2-1D on 4H and F1 on 1D. The rows
  are built with `tradeiq2_market.event_exec`, `entries` and `tradeiq2_filters.gate_entries`; exit masks are never
  filtered. The grid (24 rows per symbol) and the ids are unchanged; the params now read kind 'event', entry
  'first-strong' or 'ha-flip', exit 'ha-flip'. As event rules the rows start each window flat and take the first
  event decided inside it (harness reading 3). Development entries, state rule -> event rule (counts only; the event
  rows take every candidate, none busy): the F0 rows are equal or lose one entry, the state rule's entry at the
  window's first bar. The filtered rows lose 1.7-14.0% of their entries, the state rule's mid-streak entries after
  its filter turned (in 9 of the 24 also, as on F0, its entry at the window's first bar). In the order HA-H1 LS,
  HA-H1 LO, HA-H2 LS, HA-H2 LO: gold 1H F2-4H 2,030 -> 1,873, 1,099 -> 1,020, 3,033 -> 2,852, 1,659 -> 1,569; gold
  4H F2-1D 564 -> 519, 382 -> 361, 804 -> 756, 549 -> 526; gold 1D F1 110 -> 98, 75 -> 70, 157 -> 135, 104 -> 91;
  BTC 1H F2-4H 3,082 -> 2,911, 1,669 -> 1,581, 4,725 -> 4,509, 2,523 -> 2,410; BTC 4H F2-1D 755 -> 732, 385 -> 375,
  1,126 -> 1,103, 572 -> 562; BTC 1D F1 138 -> 127, 61 -> 57, 191 -> 176, 89 -> 83. Affects: the 12 filtered
  HA-ENTRY rows of each symbol (their trades change), and the 12 F0 rows only at each window's start.
- **HA-R12 (new; before claim 5 was computed on the study's bars). Claim 5.** The claim had no function, so it came
  out 'not computed'. Claim 5 (PREREG 8: the panel's "reached age A, then 5+ more" percentages, computed before each
  year, against what happened in that year) is now `tradeiq2_rules_ha.claim5`, the driver's `EXTRAS['claim5']`; its
  cells are in `claim5_table`. The panel's number at age A is 100 g / r = survive(curA, A, aheadN) (l.176-184,
  280-281; aheadN = 5, the script's default): of the finished streaks of the current colour, r reached age A and g
  of them reached A + 5; here every streak finished since the data start (HA-R10). Cells: one per symbol, timeframe
  (1H, 4H, 1D), colour, evidence window, calendar year inside it (`ev.years`: the year clipped to the window) and age
  A. "Computed before each year" means from the streaks whose flip candle closed at or before the cell's start, the
  indicator's state then; gold's history includes its 2016 warm-up and 2017-2018, read as indicator bars only, as
  every HA statistic reads them. "What happened in that year" means the year's streak-ages of that colour (a streak
  whose A-th candle opens and closes inside the cell) and the share of them that went on to age A + 5, with no flip
  on the next 5 candles. A streak-age counts only when those 5 candles also close inside the cell's window, whatever
  happens on them, so no outcome is read outside the windows (CLAIM_RULE) and the rule does not depend on the
  outcome. Ages: every A that at least 50 earlier streaks of the colour had reached (r >= 50), i.e. 1 up to the 50th
  longest finished length: PREREG 6.8's minimum of 50 finished streaks for a rare age, applied to the panel's own
  denominator. A cell is tested when its year has at least PREREG 5's minimum number of trades for its timeframe as
  streak-ages: 30 on 1H and 4H, 15 on 1D. The test, stated in advance: a tested cell is covered when the year's count
  lies inside the central 95% interval of Binomial(n, the panel's rate), with exact quantiles. A row is 'calibrated'
  in a window when most (more than half) of its tested cells are covered (study 1's DEVIATIONS 30-31; driver D24); a
  window without a tested cell makes the row 'cannot be tested'. Rows: per symbol one over all its tested cells (1H,
  4H, 1D, both colours), then one per timeframe and colour. dev holds Development's years 2019-2022, val holds
  Validation's 2023 and 2024-H1; after the freeze both hold the hold-out's years. If the panel's numbers were the
  true probabilities, at least 95% of cells would be covered in expectation; the panel's own sampling error (r >= 50,
  and one to eight years of history: BTC 1-6, gold 3-8) lowers that to roughly 84-96% (a synthetic simulation:
  84-91%, 91-94% and 93-96% with 1, 3 and 6 years). So 'holds' says the panel is within the year's sampling error in
  most cells; "most" is lenient (a panel that misses in close to half its cells would still hold), so every row also
  reports the share of cells covered, by year, the n-weighted mean gap between the year and the panel in percentage
  points, and how often the year is above the panel. Not chosen: every age the panel can print (at high ages it rests
  on a handful of streaks); the year's finished streaks instead of its streak-ages (the panel is read at a candle of
  age A, so the outcome belongs to the year in which that candle closed); a two-sample test of the year against the
  history (it tests the rate's stability, not the panel's numbers); a stricter share than "most" (a 90% bar would
  often fail a panel that is right on average).
- **SWING-R9 (new; supplies the claim-11 extra the review found missing). Claim 11.** PREREG 8.11: "the point of
  control of the last leg is a level price often comes back to. Test: how often the forming POC is touched before
  the leg ends, against the 50% level (W1-W3 against their placebo)"; `tradeiq2_rules_swing.claim11`. After each
  flip, the leg it starts runs from the bar after the flip bar up to and including the next flip bar, whose close
  ends it. A touch is a bar t of that span with low[t] <= level <= high[t] (equality counts; a gap through the level
  between two bars is no touch). The verdict part is the test as written: the forming leg's POC as drawn at bar t's
  close (`f_poc[t]`, W1 / W2's level, read as W1 reads it) against the forming 50% level ((f_lo[t] + f_hi[t]) / 2, the
  placebo's), a bar counting for either only when both exist at it. It holds in a window when the POC is touched in
  strictly more legs than the 50% level and the exact one-sided sign test on the discordant legs (those that touch
  only one of the two) gives p < 0.05; with too few discordant legs for that (0.5^n >= 0.05, n < 5) the window has
  no test and the part is 'cannot be tested'. The row gives both shares, the discordant legs and p. An information
  part (no verdict) reads the quoted sentence's own words, "the point of control of the last leg": on the same spans,
  the just-finished leg's POC (`legs.poc`, its tie nearest the flip bar's close, SWING-P4; W3's level, known only from
  its flip bar's close, so the flip bar itself is not read, as SWING-R4) against its 50% level (`legs.fifty`). The
  driver adds the second part (W1-W3 against their placebo, net pair by pair). Why: the verdict follows the test
  PREREG 8.11 names. A first version of this extra, written before any touch was computed, tested the just-finished
  leg's levels instead (the quote's "last leg"); the verifier showed that the plan's test names the forming POC, so
  that version is kept as the information part. The sign test puts claim 11 on claim 12's standard (p < 0.05): with
  about 100-450 legs a window, "strictly more legs" alone could be decided by one leg. The forming levels are drawn
  at a bar's close with that bar's own volume and close (the script's drawing, as W1 trades it), so a bar can touch a
  level it moved; the test is the comparison of the two levels on the same bars, not either touch rate alone.
  "Before the leg ends" includes the bar that ends it; leaving it out is the alternative. Windows (CLAIM_RULE): a leg
  belongs to the window its end bar closes in and is counted only when its first bar also opens inside that window,
  so no touch is counted on a bar outside the window (the leg across a window's start is left out); the levels are
  indicator values and may come from bars before it (on gold one just-finished leg per timeframe begins in December
  2018, in the Early window: 1H 2018-12-19 21:00, 4H 2018-12-14 12:00 UTC). The last leg, which no flip has ended, is
  not counted. Each row carries the first open and the last close it counted ('start', 'end'), which the driver's
  `check_rows` holds to the windows. Development sample (`claim_counts`, no touch computed): 317 / 87 legs on gold 1H
  / 4H and 457 / 107 on BTC, one left out at the window's start in each; every one has both forming levels on some
  bar and both just-finished levels. Affects claim 11 only.
- **SWING-R10 (new; supplies the claim-12 extra the review found missing; it applies SWING-P2 and SWING-P3, which
  name claim 12, and reads the warning as SWING-R6 does). Claim 12.** PREREG 8.12: "the next leg's size after up
  legs with negative against positive delta"; `tradeiq2_rules_swing.claim12`. The up legs are the finished legs with
  dir +1 (finished by a flip to a new 50-bar low, SWING-P2), split by the sign of their delta (`legs.delta_pct`, the
  script's bin sums, SWING-P3; gold on tick volume, BTC on Binance BTCUSDT volume, as the rules): below 0 against
  above 0. A delta of exactly 0, or none, is in neither group and is counted. The next leg is the following finished
  leg, the down leg (flips alternate). Its size is its high - low as the script draws it (`legs.hi - legs.lo`: from
  its swing high, usually the up leg's top, to its swing low), over PREREG 5's ATR(14) of the timeframe at the up
  leg's flip bar, the bar at whose close the warning is known (not the script's ATR(200)). The part holds in a window
  when the median size after a negative delta is above the median after a positive one and the exact one-sided
  Mann-Whitney U test (the next leg larger after a negative delta; the permutation distribution of the rank sum, ties
  as midranks) gives p < 0.05. A window with an empty group, or with groups so small that no ranking could reach
  p < 0.05 (1 / C(n_neg + n_pos, n_neg) >= 0.05; strict: 3 against 3 gives exactly 0.05 and has no test), has no
  test, and the part is then 'cannot be tested', also when the other window has one. Windows (CLAIM_RULE): a pair
  belongs to the window its next leg's end bar (its flip) closes in and is counted only when the next leg's first bar
  (its older swing point) also opens inside that window; the up leg's delta is an indicator value and may read
  earlier bars. Why: the literal "next leg's size", in the study's default ATR, at the bar where the warning is known;
  with 3-19 legs in the smaller group a comparison of medians alone could not tell noise from an effect. The size
  includes the fall from the top to the up leg's flip bar, which came before the warning was known: claim 12 asks
  what the delta says about the next leg; it is not a trade (the alternative, from the flip bar's close to the next
  leg's low, is not taken). Development sample (`claim_counts`, no size computed), up legs whose next leg is
  counted, delta below / above 0: gold 1H 5 / 154 and 4H 3 / 41; BTC 1H 19 / 209 and 4H 3 / 50. None has a delta of
  0. One pair is left out at the window's start on BTC 1H and one on BTC 4H, none on gold. BTC 1H's 19 include
  SWING-P2's FOMC-hour "up" leg (flip 2022-09-21 18:00 UTC), which carries the down leg's negative delta. The
  smallest p the test could give is at most 7.6e-5 in each of the four, so every Development sample can be tested.
  Affects claim 12 only.
- **MSD-C14 (adopts MSD-P8's reading of "the closed one"; replaces no item). Claim 14: what is counted, and when it
  holds.** The driver's `EXTRAS['claim14']` is now `tradeiq2_rules_msd.claim14`; until now the function was missing
  and claim 14 came out 'not computed'. PREREG 8's test, "the share of chart closes inside a higher-timeframe bar
  where the forming-bar score differs from the closed one", is computed per symbol, chart and higher row (1H chart:
  4H, D, W; 4H chart: D, W; 1D chart: W), in each of the evidence's two windows. The forming-bar score is model B's
  s_<row> at the chart close (MSD-P8): the row's state after its last closed bar, stepped once on the forming
  candle, with the swing vote at the chart close; this is what the live dashboard shows. The closed one is the score
  the higher bar ends with: its own row values with the swing vote at its own close, as MSD-P8 proposed. Where a
  chart bar closes with the higher bar, this is model A on that chart bar. Gold's week, its Friday day bar and its
  Friday 20:00 4H bar close at Saturday 00:00 UTC, when no 1H bar closes, so only the row's own values can supply
  them. A chart close is counted when it lies strictly inside a higher bar (the bar opened at or before the chart
  bar's open and closes after the chart bar's close) and that higher bar is complete and lies inside the window. Both
  bars pass `ev.in_window` (CLAIM_RULE), so the outcome is inside the window too, and a higher bar that straddles a
  window's edge is not counted. Chart closes at the higher bar's own close are left out: there the live score is the
  closed one by construction. "Inside" is by the clock: every counted close after which no data come in its higher
  bar agrees by construction (the last bar before a weekend, a holiday or early close, or a data hole); in
  Development these are 234 / 213 / 208 gold 1H closes (4H / D / W rows), 11 / 8 gold 4H closes (D / W), and on BTC
  6 / 5 / 0 and 1 / 0. The verdict line was fixed in the code before any count existed: "can change" states a
  possibility, so a part holds in a window when the share is above 0 (at least one counted close differs); it fails
  at 0 or when nothing is counted. A cut above 0, such as 5% or 10%, would be ours, not the claim's. The line is
  weak: the Development shares below (computed after it was fixed) are 19-27% in all 12 parts, so they will read
  'holds'; it is kept, because a cut chosen now would be chosen with those shares known. The share and the number of
  higher bars that change at least once are reported, so the size is visible. The claim's first half, that the rows
  use the forming candle, is the script's code (`request.security` on realtime bars); history cannot show it, and
  model B is built on it. For information, with no verdict, each chart also gets the label the live dashboard shows
  (model B) against the label the chart's history shows for the same bar (model A), and MSD-A1's side under each,
  over the window's chart closes that lie strictly inside a bar of at least one higher row. Before counting, `claim14`
  checks that at the last chart bar inside each higher bar of the windows the forming score equals the closed score,
  and raises otherwise; the check passes on every Development higher bar of both symbols. Development event counts:
  the forming score differs from the closed one at 25.4% / 24.9% / 26.9% of gold's counted 1H closes (4H / D / W
  rows), 24.4% / 27.0% of its 4H closes (D / W) and 27.0% of its 1D closes (W); on BTC 24.0% / 23.3% / 19.3%, 24.0%
  / 19.5% and 19.6%. The label differs at 4,497 / 1,155 / 141 gold and 6,971 / 1,753 / 227 BTC Development closes
  (1H / 4H / 1D charts), exactly the reconciliation's counts behind MSD-P8's percentages. Affects claim 14 only
  (information beside the rows; no row, filter or selection reads it).
- **MSD-1 (replaces MSD-R4's third and fourth sentences, "Tested: every line and the S1 distance are bit-identical
  ..." and "The only differences sit inside study 1's own warm-up ..."; see REV-6). What the test behind MSD-R4
  compares.** MSD-R4 and the rule module's reading 3 said that every study-1 line was tested bit-identical from
  2019-01-01 to 2024-06-30. The repository test compared the bars, S1's distance (by value), the 120 MSD-FILTER rows'
  base states and their filtered states, but not the lines. The line comparison has been added, and S1 is now
  compared by its bits: `tests/test_tradeiq2_rules_msd.py::test_bars_lines_s1_and_base_states_are_study_1s_on_every_
  bar_from_2019` compares the study-2 market (gold from 2016-01-03) with study 1's Study on study 1's own market
  (`tradeiq_market.load`; gold from 2017-01-03), for both symbols and the 1H, 4H and 1D bars. It asserts that the bars
  (open and close times, OHLC, tick volume) are equal on study 1's whole span; that on every bar closing after
  2019-01-01 00:00, up to the hold-out start, every array `tradeiq.lines_of` returns and the S1 distance are
  bit-identical (14 arrays on gold, 17 on BTC, which adds VWRSI-RV, its score and the missing-kline count; the same
  dtype, floats compared by their 64-bit patterns); and that each MSD-FILTER row's base state equals study 1's F0
  row of that base and the row's state equals study 1's `apply_filter` of it. It passes on both symbols, so MSD-R4's
  conclusion stands from 2019: the scored states of Development, Validation and the hold-out are exactly study 1's.
  A one-ulp change planted in a line no state reads (TSI:signal) fails the new test; the old test could not see it.
  Measured besides, not asserted (the module's reading 6): on gold the states differ on at most 57 bars of a series,
  all closing on or before 2017-03-29, so gold's Early window (exam 2) is the exception; S1 is missing on study 1's
  first 13 bars of each series (its ATR's warm-up) and then differs in its last bits until 2018-09-14 (1D); the lines
  differ in their last bits until 2018-12-25 (the 1D VWRSI; on 1H until 2017-01-31, on 4H until 2017-05-03), and
  during study 1's warm-up some by more (MA200 missing on its first 199 bars, QQE:color on 44 1H bars). None of this
  reaches 2019; study 1 has no Early result to pair with. On BTC both markets start on 2018-01-01 and nothing
  differs. Affects the record only; no state, line, count or result changes.
- **FIX-1, a process disclosure.** One fixer's mutation check (claim 14) wrote mutants into
  `tradeiq2_rules_msd.py` in place and restored it byte-identical (sha256 checked against its kept copy). Other test
  runs in that window could have imported a mutant, so every affected test file was run again on the final files
  before this section's commit. Later mutation checks ran in memory only.

## After the freeze, 28 Nov 2026 (IST)

- **FIX-2 (20:43 IST, after the exam and the accounts, before any claim was computed). The driver's
  `Evidence.trades`.** The first `claims` run stopped at claim 16: `tradeiq2_rules_wyckoff.claim16` calls
  `ev.trades(window)` and picks its own rows (WY-STD / WY-AGG x S-W x X-S x F0, x1.0). The driver's `trades` required
  a list of ids. The module's test had passed a stand-in with that one-argument call, so the two had never met. The
  driver now reads `vids=None` as every variant's trades of the window at the cost (`tests/test_tradeiq2.py::
  test_evidence_trades_without_ids_gives_every_variant_of_the_window`). The driver is an information file of
  FINALISTS.md (its blob is recorded, not required), and no rule module, port or harness file changed. So no
  variant's result, no exam row and no account moves; the change only lets claim 16 be computed. `claims` then ran
  to the end: 178 parts, none 'not computed'.
- **FIX-3 (21:47 IST, after the exam). The comparison page's files say which rows are out of sample.** The driver
  wrote the page's contract v1, which has no `sample` column, so the page could not tell the reader that study 2's
  hold-out rows are out of sample (study 1's are flagged). The driver (an information file of FINALISTS.md) now
  writes contract v2. Its optional columns are the series' `sizing` and `tags` (empty, as study 1's) and the metrics'
  `sample` (Development and Validation 'in'; the hold-out, gold's Early window and the last year 'out'; full, 5y, 8y
  and new 'mixed', as study 1 flags the same windows), `derived` and `row_notes` (empty). `accounts` was rerun; every
  account part was already complete for this code, so nothing was recomputed. Every v1 column and every curve's
  content is unchanged (checked against the committed files).
