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
