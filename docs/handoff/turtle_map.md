# Map: the Turtle strategies for BTCUSDm ("Turtle + bot votes" and "Turtle System 2 + bot votes")

> **About this file.** This note was added on 16 Nov 2026, when the map was saved into the repo with `HANDOFF.md`.
> - **What it is.** The exact rules of the two BTC Turtle rows of the final ten, as the M1-bar simulator runs them: data and day boundaries, N and the channels, the System 1 filter, the order, stop and add execution, the "+ bot votes" gate, sizing, results, and what a live MT5 port needs (§13) and risks (§14). It was written for the demo port.
> - **When.** Written on 15 Nov 2026, about 17:41 IST, by an assistant session that worked read-only.
> - **What it describes.**
>   - `backtesting/research/external.py` and `final10.py` at `0ae5794`; both are unchanged since `9e4c71f` and still current at `bed551e` (16 Nov 2026), so the line numbers hold. `backtesting/analysis/signal.py` has not changed since `48933e6`.
>   - The final-ten result files in `backtest_results/final10/`.
>   - The live files of `origin/hedging_btcusd6` at `cef581a` (13 Nov 2026).
> - **What happened next.** `demo_hedging_btcusd6` (System 2 + bot votes) and `demo_hedging_btcusd7` (System 1 + bot votes) implement §13 in `turtle.py` behind `STRATEGY = 'turtle'`. Their decision-level replay, `tests_demo/test_turtle_replay.py`, takes the backtest's 88 and 60 eight-year trades exactly (`HANDOFF.md` §5.6). The statement that no poll-by-poll parity exists for the Turtle is still true.
> - **Scratch files.** The probe files named here (`turtle_probe/probe.py`, `probe2.py`, `out.txt`, `out2.txt`) and the parity scripts `parity_final.py` and `parity_recheck.py` live in a temporary session folder, `/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/`, which is not part of the repo. They were all still there at about 03:50 IST on 16 Nov 2026 (the first version of this note said they were gone), but a reboot or a clean-up can delete them. The probe results are written out in this map.
> - **Corrected on 16 Nov 2026.** §2 now says that the 3,233 D1 bars cover 3,238 calendar days (5 days have no bar). §6 step 4 now gives the exact re-entry rule after an exit. §14 item 9 now also names System 2's losing 2022.
> - **No credentials.** `mt5_credentials.json` was never opened or copied.

Read-only study of `backtesting/research/external.py`, `backtesting/research/final10.py`,
`backtesting/analysis/signal.py`, the final-ten result files, and the live files on
`origin/hedging_btcusd6` (identical to `_7` and `_8` except `mt5_credentials.json`). The line numbers for
repo files are those of the working tree on `backtest_hedging`. For live files they are the line numbers
`git show origin/hedging_btcusd6:<file>` prints. Nothing in the repo was changed. The two read-only
re-runs I did live in the scratchpad (`turtle_probe/probe.py`, `probe2.py`, outputs `out.txt`, `out2.txt`).

---------------------------------------------------------------------------------------------------------

## 0. In one screen

| | Turtle + bot votes (System 1) | Turtle System 2 + bot votes |
|---|---|---|
| final-ten row | pre-registered BTC **#3** (`selection.json`): family `turtle`, params `default`, variant `+ bot votes`, sizing `bot unit rule` | warm re-check BTC **#1** (`selection_warm.json`): family `turtle`, params `alt`, variant `+ bot votes`, sizing `bot unit rule`. Its result-file label is `Turtle [alt] + bot votes`; `final10.py:695` maps it to the display name |
| builder | `turtle(m, 1)` then `filtered(plan, m, sig.votes_at)` | `turtle(m, 2)` then `filtered(plan, m, sig.votes_at)` |
| bars | D1 = UTC calendar days built from M1 **bid** bars. Orders, stops and adds are checked on every **M1** bar | same |
| N | Wilder RMA(20) of the D1 true range, seeded with the simple mean of the first 20 TRs | same |
| entry | buy stop at 20-day high + 0.01, sell stop at 20-day low − 0.01; **55-day** levels instead whenever the skip-after-winner filter says so | buy stop at 55-day high + 0.01, sell stop at 55-day low − 0.01; no filter |
| exit channel | 10-day low (long) / 10-day high (short) | 20-day low / 20-day high |
| stop | the tighter of 2N from the fill and the exit channel. Every add moves it to 2N from the newest fill. Each D1 close raises it to the exit channel. It only ever tightens | same |
| pyramid | +1 unit every 0.5 N (N frozen at entry) from the previous fill, up to **4 units**. Adds are not gated by votes | same |
| "bot votes" | the entry fill needs the **M15 agreement on the last CLOSED M15 bar**: RSI(14) pivot-slope sign and MACD(12,26,9)-histogram pivot-slope sign both +1 (long) or both −1 (short). Gates entries only | same |
| size | unit rule: s = floor(balance / 2500) + 1, at most 10, set from the realized balance at the first fill. **Every leg is s × 0.01 lot** | same |
| 8y (Nov 2018 – Nov 2026) | $2,000 → **$6,977.48**, max DD 46.0%, 88 trades, PF 1.56 | $2,000 → **$7,814.72**, max DD 32.5%, 60 trades, PF 2.15 |
| 5y / fair test 2018-20 / last year | $6,304.88 (DD 44.6%) / $2,742.20 (DD 10.7%) / $3,412.49 (DD 26.4%, 11 trades) | $3,546.56 (DD 38.4%) / $2,857.89 (DD 9.4%) / $3,039.45 (DD 22.4%, 7 trades) |
| calendar years (8y account) | +2.4% 2018*, +3.6%, +29.3%, +32.6%, +19.4%, +23.1%, +24.4%, **−31.3% 2025**, +52.7% 2026* | +1.4%, +9.2%, +29.0%, +35.8%, −3.0%, +19.3%, +44.0%, **−15.2% 2025**, +42.5% |

A read-only re-run reproduced all eight accounts **to the cent** (see §11).

The Turtle exists **only** in the M1-bar simulator of `external.py`. The tick engine
(`engine/kernels.py`, `engine/fast.py`) has no breakout, pyramid or Donchian code. The reference
engine and the parity scripts (`engine/parity.py`, `parity_final.py`, `parity_recheck.py`) only check the
bot's own `app.py` logic. So no parity harness exists for a Turtle port.

---------------------------------------------------------------------------------------------------------

## 1. Where the rows come from

* Registry, `external.py:1715-1718`:
  ```
  1715	    Strategy("turtle", "Turtle Donchian breakout (Original Turtle Rules)", "breakout", "D1",
  1716	             {"default": ("System 1: 20-day entry with the skip-after-winner filter and 55-day failsafe, 10-day exit",
  1717	                          lambda m: turtle(m, 1)),
  1718	              "alt": ("System 2: 55-day entry, 20-day exit", lambda m: turtle(m, 2))}),
  ```
  It has no `params_btc`, so BTC uses exactly the same parameters as gold.
* Variant "+ bot votes", `external.py:1801`:
  `jobs.append((s.key, s.name, label, desc, "+ bot votes", filtered(b.plan, m, sig.votes_at), BOT))`
* Final-ten runner, `final10.py:424-449` (`_bar_plan`), lines 438-439:
  ```
  438	    elif v == "+ bot votes":
  439	        plan, sizing = X.filtered(b.plan, m, sig.votes_at), X.BOT
  ```
  `run_bars` (`final10.py:491-519`) loads `X.load_market(symbol, earliest=HISTORY_FROM[symbol], end=DATA_END)`
  (line 494). For BTC, `HISTORY_FROM` (line 65) is `"2018-01-01"` and `DATA_END` is `"2026-11-13"`.
  The plan is built once on all that history. Each window (`WINDOWS`, lines 56-61: 8y 2018-11-13..2026-11-13,
  5y 2021-11-13.., new 2018-11-13..2021-01-01, 1y 2025-11-13..) is then a fresh $2,000 account through
  `_bar_account` (lines 459-488): `run_path` plus `_account_kernel` with daily marks.
* Selection:
  * Pre-registered, cold evidence: S1 + votes scored 4.08 (+189/+116/+58/+139/+163 per quarter;
    worst fresh-quarter DD 32.5%) → **#3**. S2 + votes scored 3.32 (2021 −60), but the
    two-per-strategy cap (`FAMILY_CAP = 2`, `final10.py:51`) cut it, because S1 + votes and the 1%-risk
    Turtle already held the Turtle slots.
  * Warm re-check (history from 2018): S2 + votes scored **4.65** (+119/+13/+45/+198/+180, DD 23.9%) →
    warm **#1**. S1 + votes scored 3.97, just below Turtle risk-sized (3.98), so the family cap
    **pushed S1 + votes out** of the warm ten. It is still eligible in `evidence_warm.csv`.
* Result files (`backtest_results/final10/`):
  * S1 + votes: `runs_BTCUSDm_bars.csv`, `trades_BTCUSDm_bars.csv.gz`, `years_BTCUSDm_bars.csv`, label `Turtle + bot votes`.
  * S2 + votes: `runs_BTCUSDm_warm.csv`, `trades_BTCUSDm_warm.csv.gz`, `years_BTCUSDm_warm.csv`, label `Turtle [alt] + bot votes`.
  * In the trades files, `lots` is the size **per leg** and `legs` is the number of pyramid units.

---------------------------------------------------------------------------------------------------------

## 2. Data, bars, day boundaries

* M1 **bid** bars from the Exness public tick archive store (`data/store/BTCUSDm/YYYY_MM/m1.npz`, built by
  `data/store.py:build_bars`). Bars exist only where ticks exist.
* The ask is modelled as `bid + the M1 bar's MEAN spread` (`external.py:16`, and `ask_o = o[j] + sp[j]` in
  the kernel). One unit (0.01 lot of BTC) earns $0.01 per $1 of price (`external.py:129`,
  `self.k = spec.contract_size * 0.01`, with contract size 1). The tick is `10 ** -digits` = **0.01**
  (`external.py:130`; BTCUSDm has digits 2 in `config.py:69`).
* **D1 bars = UTC days**, `external.py:197-220`:
  ```
  197	def day_bars(m: Market, min_bars: int = DAY_MIN_BARS) -> Bars:
  198	    """UTC days; a day with fewer than ``min_bars`` M1 bars is merged into the next full day (it closes when that day ends)."""
  ...
  201	    day = m.t // DAY
  ...
  212	        if count[d] >= min_bars:
  213	            opens.append(start * DAY)
  214	            closes.append((int(days[d]) + 1) * DAY)
  ```
  `DAY_MIN_BARS = 360` (line 84: six hours of quotes). **On BTC no day was ever merged** from 2018-01-01
  to 2026-11-12. All 3,233 D1 bars open and close at 00:00 UTC. The thinnest day has 803 M1 bars
  (2021-03-02), and 17 days have fewer than 1,300 because of archive holes, e.g. 2020-05-30 and April 2024
  (probe).
* **The 3,233 bars cover 3,238 calendar days** (computed from the M1 store, 16 Nov 2026). Archive holes
  leave 5 days with no bar at all: 2021-03-03, 2025-04-28, 2025-08-30, 2026-03-30 and 2026-03-31. So for
  BTC a "20-day" channel means 20 calendar days, weekends included, except near those dates, where a
  K-bar channel spans K+1 or K+2 calendar days (21-22 for a 20-bar channel, 56-57 for a 55-bar one). A
  live port reads the terminal's own D1 bars, which may include those days, so its levels can differ from
  the backtest's there.
* A bar is readable from its close time `tc`: 00:00 UTC of the next day for D1, and the bucket end for
  M15. `value_at` (`external.py:244-248`) returns the last bar with `tc <= T`:
  ```
  246	    i = np.searchsorted(tc, np.asarray(T, np.int64), side="right") - 1
  ```
* The D1 decision executes at the open of the first M1 bar at or after 00:00 UTC (`make_plan`,
  `external.py:437`: `dx = np.searchsorted(m.t, dt, side="left")`).
* The backtest assumes Exness MT5 server time is UTC (`config.py:25-26`). Live code needs this to hold
  for the MT5 D1/M15 bars to coincide.

---------------------------------------------------------------------------------------------------------

## 3. N and the channels

```
1213	def turtle_n(tr: np.ndarray, n: int = 20) -> np.ndarray:
1214	    """N = (19 x N_prev + TR) / 20, seeded with the simple mean of the first 20 true ranges."""
1215	    return wilder(tr, n)
```
`wilder` (`external.py:265-280`) seeds the output at bar s+n−1 with the mean of the first n values, then
applies `v = (v*(n-1) + x)/n`. `true_range` (`external.py:293-298`) is
`max(H-L, |H-C_prev|, |L-C_prev|)`, with `tr[0] = H[0]-L[0]`. The channels are `roll_max(H, n)` and
`roll_min(L, n)` (pandas rolling with `min_periods=n`, lines 257-262). They are **count-based over D1 bars
and include the bar that just closed**. Element b uses bars b-n+1..b and is used for day b+1.

Convergence (probe): starting N from seven different dates, it agrees with the backtest's
2018-01-01-seeded N to 1e-6 (relative) after 198-268 days.

---------------------------------------------------------------------------------------------------------

## 4. The plan: `turtle()`, `external.py:1282-1301` (verbatim)

```
1282	def turtle(m: Market, system: int = 1) -> Built:
1283	    """The Original Turtle Trading Rules: Donchian breakouts on daily bars, 2N stop, pyramid every N/2 up to 4 units."""
1284	    d1 = m.bars("D1")
1285	    O, H, L, C = d1.o, d1.h, d1.l, d1.c
1286	    N = turtle_n(true_range(H, L, C), 20)
1287	    hi20, lo20 = roll_max(H, 20), roll_min(L, 20)
1288	    hi55, lo55 = roll_max(H, 55), roll_min(L, 55)
1289	    hi10, lo10 = roll_max(H, 10), roll_min(L, 10)
1290	    if system == 1:
1291	        use20 = _turtle_s1_use20(O, H, L, N, hi20, lo20, lo10, hi10, m.tick)
1292	        hi_e, lo_e = np.where(use20, hi20, hi55), np.where(use20, lo20, lo55)
1293	        trl, trs = lo10, hi10
1294	    else:
1295	        hi_e, lo_e = hi55, lo55
1296	        trl, trs = lo20, hi20
1297	    ok = np.isfinite(N) & np.isfinite(hi_e) & np.isfinite(lo_e)
1298	    plan = make_plan(m, d1.tc, bstop=np.where(ok, hi_e + m.tick, NAN), sstop=np.where(ok, lo_e - m.tick, NAN),
1299	                     sl=np.where(ok, 2.0 * N, NAN), pstep=np.where(ok, 0.5 * N, NAN), pmax=4, rk=N, trl=trl, trs=trs,
1300	                     orders=True)
1301	    return Built(plan, plan, Sizing("risk", rf=0.01, brake=True, label="1% of equity per N, 20% cut per 10% drawdown"))
```
The plan has one row per D1 bar b, executed at 00:00 UTC after it. For that day it carries:
* `bstop` / `sstop`: the stop-entry levels, valid until the next row replaces them.
* `sl = 2N[b]`: the stop distance.
* `pstep = 0.5 N[b]`: the add step.
* `pmax = 4`: total units.
* `trl` / `trs`: the exit-channel levels the stop is raised to while in a position.
* `want` = 0: no market entries. `xl` / `xs` = False: no signal exits.
* Pauses are 0 and `live_s` = INF: no quote-freshness rule.

`rk = N` and the risk `Sizing` are used **only** by the "risk-sized" row. The "+ bot votes" rows use `BOT`.

**When the filter says "skip", the 55-day failsafe applies to both directions** (lines 1292-1293). It is
not side-specific.

---------------------------------------------------------------------------------------------------------

## 5. System 1 skip-after-winner filter: `_turtle_s1_use20`, `external.py:1218-1279` (verbatim)

```
1219	def _turtle_s1_use20(O, H, L, N, hi20, lo20, lo10, hi10, tick):
1220	    """
1221	    The System 1 filter, decided at each day's close for the next day: True = trade the 20-day breakout,
1222	    False = only the 55-day failsafe. A hypothetical one-unit System 1 (2N stop, 10-day exit, no adds) is run on
1223	    the daily bars; a breakout is skipped when the last hypothetical breakout trade made money. The outcome of a
1224	    trade is known from the close of the day it ended.
1225	    """
1226	    nb = O.shape[0]
1227	    use20 = np.zeros(nb, np.bool_)
1228	    hyp = 0
1229	    entry = 0.0
1230	    stop = 0.0
1231	    last_win = False
1232	    for b in range(nb):
1233	        if b >= 1:
1234	            if hyp == 0 and hi20[b - 1] == hi20[b - 1] and N[b - 1] == N[b - 1]:
1235	                up_l = hi20[b - 1] + tick
1236	                dn_l = lo20[b - 1] - tick
1237	                up = H[b] >= up_l
1238	                dn = L[b] <= dn_l
1239	                if up and dn:
1240	                    if up_l - O[b] <= O[b] - dn_l:
1241	                        dn = False
1242	                    else:
1243	                        up = False
1244	                if up:
1245	                    hyp = 1
1246	                    entry = max(up_l, O[b])
1247	                    stop = entry - 2.0 * N[b - 1]
1248	                    if L[b] <= stop:
1249	                        hyp = 0
1250	                        last_win = False
1251	                elif dn:
1252	                    hyp = -1
1253	                    entry = min(dn_l, O[b])
1254	                    stop = entry + 2.0 * N[b - 1]
1255	                    if H[b] >= stop:
1256	                        hyp = 0
1257	                        last_win = False
1258	            elif hyp == 1:
1259	                ex = stop
1260	                if lo10[b - 1] == lo10[b - 1] and lo10[b - 1] > ex:
1261	                    ex = lo10[b - 1]
1262	                if O[b] <= ex:
1263	                    last_win = O[b] > entry
1264	                    hyp = 0
1265	                elif L[b] <= ex:
1266	                    last_win = ex > entry
1267	                    hyp = 0
1268	            elif hyp == -1:
1269	                ex = stop
1270	                if hi10[b - 1] == hi10[b - 1] and hi10[b - 1] < ex:
1271	                    ex = hi10[b - 1]
1272	                if O[b] >= ex:
1273	                    last_win = O[b] < entry
1274	                    hyp = 0
1275	                elif H[b] >= ex:
1276	                    last_win = ex < entry
1277	                    hyp = 0
1278	        use20[b] = hyp == 0 and not last_win
1279	    return use20
```
What it means exactly:
* It is a **separate, hypothetical, unfiltered** System 1. It uses D1 bid OHLC only, one unit, no spread,
  no adds, and a fixed stop at 2N from the first fill (N of the previous day). The exit is at
  max(stop, previous day's 10-day low) for a long, mirrored for a short, and checked only from the day
  after entry.
* It takes **every** 20-day breakout while it is flat, in either direction. **The bot votes are not used**:
  real trades never feed the filter.
* `use20[b]` is True only if the hypothetical is **flat** at the close of day b **and** its last trade was
  not a winner. That includes the stop-out-on-entry-day case (a loser) and a gap exit at the open.
* While the hypothetical trade is still open, `use20` stays False. So after a real exit (the real stop
  is tighter because it trails 2N from the last add), the real strategy can only re-enter on a **55-day**
  breakout until the hypothetical trade ends.
* `use20[b]` (decided at the close of day b) selects the levels for day b+1. Over 2018-2026 it was True
  on 18.3% of days. Of S1 + votes' 88 eight-year trades, 51 entered on the 20-day level and 37 on the
  55-day failsafe (probe).
* Path dependence (probe): computed from seven later start dates, `use20` matched the backtest's
  2018-started series at most 47 days after the start.
* Tested by `tests/test_external.py:372-394`.

System 2 has no filter.

---------------------------------------------------------------------------------------------------------

## 6. The simulator: how the orders, stops and adds are executed (`_path_kernel`, `external.py:519-780`)

Each M1 bar j runs these steps in this order:

1. **Gap at the open** (lines 572-594). A long whose `o[j] <= stop` exits at the bid open. A short whose
   `ask_o >= stop` exits at the ask open ("gap stop"). Neither row had a gap exit in its 8-year BTC
   account; BTC trades around the clock.
2. **Decisions executed at this open** (lines 595-648). The D1 row executes at 00:00 UTC. While in a
   position the stop is raised to the exit channel, never lowered:
   ```
   611	            if pos == 1 and trl[kk] == trl[kk] and trl[kk] > stop:
   612	                stop = trl[kk]
   613	            if pos == -1 and trs[kk] == trs[kk] and trs[kk] < stop:
   614	                stop = trs[kk]
   ```
   Then the day's stop-entry orders replace the old ones, flat or not:
   ```
   645	            o_k = kk
   646	            o_b = bstop[kk]
   647	            o_s = sstop[kk]
   ```
3. **Inside the bar, in a position** (lines 649-717): the stop first (unfavourable extreme first), then the
   pyramid adds. For a long:
   ```
   650	        if pos == 1:
   651	            if l[j] <= stop:
   652	                xp, why = stop, 2
   653	            elif h[j] >= target:
   654	                xp, why = target, 3
   655	            else:
   656	                why = 0
   657	                while units < p_max and p_step == p_step:
   658	                    lvl = last_fill + p_step
   659	                    if h[j] + sp[j] >= lvl:
   660	                        fp = max(lvl, ask_o)
   661	                        L_eix[nl] = j
   662	                        L_epx[nl] = fp
   663	                        nl += 1
   664	                        units += 1
   665	                        last_fill = fp
   666	                        if sl_d == sl_d and fp - sl_d > stop:
   667	                            stop = fp - sl_d
   668	                    else:
   669	                        break
   ```
   The short mirror is at lines 684-703. It stops when `h[j] + sp[j] >= stop` (on the ask) and adds when
   `l[j] <= last_fill - p_step`, filled at `min(lvl, o[j])`.
   * The target is +inf (no target) and the break-even is NaN (none).
   * The exit is at the stop level itself.
   * After an exit, `next_ok = t[j] + 60` (no pause), so a new entry can fill from the next M1 bar on.
4. **Stop-entry orders** (lines 718-769), only when flat since the bar's start and `t[j] >= next_ok`. After a
   stop exit inside bar j, `next_ok = t[j] + 60` (lines 683, 717, 769), so entries resume from the next M1
   bar's open, not 60 s after the exit itself. After a gap exit at the bar's open, `next_ok = t[j]` (line 594)
   and `exited` stays False, so an entry can fill in that same bar. (The demo port uses "not in the M1 bar
   of the last exit".)
   ```
   719	        if pos == 0 and not exited and o_k >= 0 and t[j] >= next_ok:
   720	            hb = o_b == o_b and h[j] + sp[j] >= o_b and m_l[j]
   721	            hs = o_s == o_s and l[j] <= o_s and m_s[j]
   722	            if hb and hs:
   723	                if (o_b - ask_o) <= (o[j] - o_s):
   724	                    hs = False
   725	                else:
   726	                    hb = False
   727	            if hb or hs:
   728	                d = 1 if hb else -1
   729	                px = max(o_b, ask_o) if d == 1 else min(o_s, o[j])
   730	                st = _tightest(d, px, sl[o_k], slf[o_k], slcap[o_k], bsl[o_k] if d == 1 else ssl[o_k],
   731	                               trl[o_k] if d == 1 else trs[o_k])
   ...
   743	                sl_d = sl[o_k]
   744	                p_step = pstep[o_k]
   745	                p_max = pmax[o_k]
   746	                units = 1
   747	                last_fill = px
   ...
   757	                o_b = np.nan
   758	                o_s = np.nan
   759	                # the bar's opposite extreme is taken to come after the fill
   760	                hit = (l[j] <= stop) if d == 1 else (h[j] + sp[j] >= stop)
   ```
5. **End of the window** (lines 770-778): an open position is closed at the last M1 close (bid for a long,
   close + spread for a short).

What this means for the entry fill model:
* A buy triggers when the **ask** high of the M1 bar (bid high + mean spread) reaches the level. A sell
  triggers when the **bid** low reaches it.
* The fill is at the level, or at the open (ask for buys, bid for sells) if the bar opened beyond it. The
  order is live all UTC day.
* `m_l[j]` / `m_s[j]` are the vote gate (§7). If the price is already beyond the level when the votes
  turn on, the trade fills at the **ask open of the M1 bar that starts at that M15 close**: effectively a
  market order.
* **One fill cancels both orders for the rest of that UTC day**, because `o_b`/`o_s` become NaN. After an
  exit on the same day nothing can re-enter until the next 00:00 decision. If the entry happened on an
  earlier day, the 00:00 refresh re-armed the orders, so a same-day re-entry is possible (it happened once
  in S1's 88 trades).
* With votes, the "both orders hit in one bar" rule (lines 722-726) never matters: the vote cannot be +1
  and −1 at once.
* **Initial stop** = the tightest of 2N from the fill and the exit-channel level
  (`_tightest`, lines 495-516, `trail` argument):
  ```
  514	    if trail == trail:
  515	        st = max(st, trail) if d == 1 else min(st, trail)
  ```
  That is, max(fill − 2N, 10-day low) for an S1 long. The channel was tighter at entry in 7 of S1's 88
  trades and none of S2's.
* **N is frozen at entry**: `sl_d` and `p_step` come from the decision row that armed the order (the N of
  the D1 bar that closed before the entry day). The add levels chain from the **actual** previous fill.
* The adds:
  * can fill several times in one M1 bar (`while` loop);
  * never fill in the entry's own M1 bar, nor in a bar that hits the stop;
  * are **not gated by the votes**.
  * In the probe, all add gaps were ≥ 0.5 N_entry.
* The stop after adds: every leg shares one stop. It is raised to `newest fill − 2N_entry` (long) after
  each add, and to the exit channel at each 00:00 decision. It is never lowered.
  `tests/test_external.py:202-210` pins this.
* The exit channel is not a separate exit: it is folded into the ratcheting stop. S1's 87 non-final exits:
  38 at 2N from the last fill, 49 at the 10-day channel. S2's 59: 33 at 2N, 26 at the 20-day channel.
  Every trade's exit reason is "stop" (or "end" for the last one).

---------------------------------------------------------------------------------------------------------

## 7. "+ bot votes", exactly

* The filter, `external.py:480-489`:
  ```
  480	def filtered(plan: PathPlan, m: Market, dir_at: Callable[[np.ndarray], np.ndarray]) -> PathPlan:
  481	    """The plan with entries kept only where ``dir_at`` (a direction known at that time) agrees with them."""
  482	    d = np.asarray(dir_at(plan.dt))
  483	    kw = dict(alw_l=plan.alw_l & (d == 1), alw_s=plan.alw_s & (d == -1))
  484	    if plan.orders:
  485	        dm = np.asarray(dir_at(m.t))
  486	        ml = dm == 1 if plan.m_l is None else plan.m_l & (dm == 1)
  487	        ms = dm == -1 if plan.m_s is None else plan.m_s & (dm == -1)
  488	        kw.update(m_l=np.ascontiguousarray(ml), m_s=np.ascontiguousarray(ms))
  489	    return plan.copy(**kw)
  ```
  For the Turtle only `m_l` / `m_s` matter (`want` is 0, so `alw_l` / `alw_s` are unused). They are
  evaluated at **each M1 bar's open time** `m.t[j]`.
* `dir_at = sig.votes_at` (`external.py:327-328`) is `value_at(self.m15_tc, self.m15_agree, T, 0)`: the
  agreement of the **last M15 bar closed at or before the M1 bar's open**. The bar [10:00, 10:15) is used
  from 10:15:00 on. The state can only change at :00, :15, :30 and :45 UTC.
* `m15_agree`, `bot_signals` (`external.py:341-343`):
  ```
  341	    m15, h1 = m.bars("M15"), m.bars("H1")
  342	    v15 = votes(pd.Series(m15.c))
  343	    agree = np.where((v15["macd"] == 1) & (v15["rsi"] == 1), 1, np.where((v15["macd"] == -1) & (v15["rsi"] == -1), -1, 0))
  ```
  M15 bars are UTC buckets of M1 bid bars (`tf_bars`, lines 192-194), and the vote uses their closes.
  **No grey fill.** The H1 votes, H1 trend and H1 volatility in `BotSignals` are **not** used by these rows.
* `votes()` (`backtesting/analysis/signal.py:48-72`) loads the **live** `indicator.py` and `constants.py`
  from the repo root. On `backtest_hedging` these are the hedging_xauusd6 copies: `indicator.py` is
  byte-identical to `origin/hedging_btcusd6:indicator.py` (blob a10cc86868), and `constants.py` differs
  only by a trailing newline. It computes, on each closed bar with that bar as "current":
  ```
  59	    rsi = ind.calculate_rsi(close, c.RSI_LENGTH)
  60	    macd = ind.calculate_macd(close, fast=c.MACD_FAST, slow=c.MACD_SLOW, signal=c.MACD_SIGNAL)
  ...
  66	        s = sig[i]
  67	        side = "high" if s > 0 else ("low" if s < 0 else None)
  68	        m = ind.latest_pivot_slope(hist.iloc[lo:i + 1], lookback=c.PEAK_LOOKBACK, width=c.PIVOT_WIDTH, side=side)
  69	        r = ind.latest_pivot_slope(rsi.iloc[lo:i + 1], lookback=c.PEAK_LOOKBACK, width=c.PIVOT_WIDTH,
  70	                                   ob_level=c.RSI_PEAK_OB, os_level=c.RSI_PEAK_OS)
  ```
  The live definitions (`origin/hedging_btcusd6`):
  * `indicator.py:86-111` `calculate_rsi`: RMA, SMA-seeded, alpha 1/14, NaN → 100.
  * `indicator.py:113-140` `calculate_macd`: SMA-seeded EMAs 12/26, signal EMA 9, `hist = macd - signal`.
  * `indicator.py:142-224` `latest_pivot_slope`: scans the last `lookback` = 20 bars back from bar
    n−1−width. A pivot must be strictly above (high) or below (low) the 2 bars on each side. The first
    (latest) qualifying pivot gives `slope = (current - pivot)/bars_ago`, and its sign is the vote; no
    pivot gives 0.
    * RSI highs count only at ≥ 60 and lows only at ≤ 40 (`RSI_PEAK_OB` / `RSI_PEAK_OS`,
      `constants.py:108-109`).
    * For the MACD histogram, the pivot side follows the signal line's sign (> 0 highs only, < 0 lows
      only, 0 both).
  * Constants: `RSI_LENGTH=14` (26), `RSI_MA_TYPE='RMA'` (27), `MACD_FAST/SLOW/SIGNAL=12/26/9` (56-58),
    `PEAK_LOOKBACK=20` (103), `PIVOT_WIDTH=2` (104).
  * The 26-bar slice in `votes()` gives the same pivot search as the live 500-bar call. RSI/RMA(14) and
    EMA(26) converge to ~1e-16 within 500 bars.
* The same quantity in the live strategy is `fc_score = _weighted_score(slopes, FORCE_CLOSE_SCORE_WEIGHTS)`
  with `{'M15': 1}` and raw signs (`strategy.py:77-104`, `235`; `constants.py:92`). Long agreement is
  `fc_score >= +2` and short agreement `fc_score <= -2`. That is the live entry-agreement gate with
  `ENTRY_AGREE_S = 2` (`constants.py:69`, `strategy.py:107-123`), **but computed on the closed bar**.
* M15 statistics, 2018-26 (probe): vote +1 on 34.9% of bars, −1 on 35.6%, and the median run of one state
  is 3 bars (45 min). The gate opens and closes many times a day.
* Effect on fills, eight years:
  * S1: 46 of 88 entries had the price beyond the level earlier the same UTC day while the votes
    disagreed. 39 filled worse than the level, 38 of them at the open of the M1 bar right after an M15
    close. Excess over the level: mean 0.117 N, p90 0.317 N, median 0.
  * S2: 30 of 60 delayed, 28 worse (27 at an M15 boundary). Excess: mean 0.161 N, p90 0.421 N.
  * Fills come a median 14.9 h (S1) / 12.6 h (S2) after the 00:00 UTC decision.

---------------------------------------------------------------------------------------------------------

## 8. Sizing: the bot unit rule, and how the pyramid legs are sized

`Sizing()` defaults (`external.py:1016-1025`) give `mode="bot"` and the label "bot unit rule". The
account kernel (`external.py:783-892`), mode 0:
```
819	        if mode == 0:
820	            s = math.floor(bal / step_up) + 1.0
821	            if s > unit_max:
822	                s = unit_max
```
The constants are `ACCOUNT = 2000.0`, `STEP_UP = 2500.0` and `UNIT_MAX = 10` (lines 77-79). `bal` is the
**realized** balance when the trade opens: trades are sequential, one position at a time. Every leg
of the trade is marked and paid with the same `s`:
```
841	        for j in range(e, x + 1):
...
844	            for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
845	                if L_eix[q] > j:
846	                    continue
...
858	                uc += s * k * d * (mc - ep)
...
879	        pl = 0.0
880	        for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
881	            pl += s * k * d * (T_xpx[i] - L_epx[q])
```
* **One unit = 0.01 lot.** A trade's units = s = floor(balance / 2500) + 1, capped at 10, fixed at the
  first fill.
* **Each pyramid add is another s × 0.01 lot**, so at most 4 × s × 0.01 lot (0.40 lot at s = 10).
* The legs observed over 8 years were 0.01-0.03 lot each (S1) and 0.01-0.04 (S2).
* This is the same rule as live `app.py:503-511`: `units = int(balance // step_up_balance) + 1`, capped by
  `unit_max_limit`, re-derived only while flat, with `mtqty = 0.01` (`symbols.json`: step_up_balance
  2500, unit_max_limit 10, mtqty 0.01).
* There is no margin model, no swap and no commission. The account is wiped at equity ≤ 0.

---------------------------------------------------------------------------------------------------------

## 9. Parameter values (BTCUSDm; identical to gold, none tuned)

| parameter | System 1 + votes | System 2 + votes | where |
|---|---|---|---|
| bar timeframe for levels | D1, UTC days (merge < 360 M1 bars: never on BTC) | same | `external.py:84,197-220` |
| N | Wilder RMA(20) of the D1 TR, SMA seed | same | `1213-1215`, `265-280`, `293-298` |
| entry levels | 20-day H/L ± 0.01, or 55-day when `use20` is False | 55-day H/L ± 0.01 | `1287-1298` |
| filter | skip-after-hypothetical-winner, 55-day failsafe | none | `1219-1279` |
| exit channel / trailing stop | 10-day L (long) / H (short) | 20-day L / H | `1293`, `1296`, `611-614` |
| stop distance | 2.0 × N_entry | same | `1299` (`sl`) |
| pyramid step / max units | 0.5 × N_entry / 4 | same | `1299` (`pstep`, `pmax=4`) |
| tick | 0.01 | same | `130` |
| vote gate | M15 closed-bar agreement, entries only | same | `480-489`, `327-328`, `341-343` |
| pause after exit | none (60 s, the next M1 bar) | same | `683`, `717`, `769` |
| quote-freshness rule | none (`live_s = INF`) | same | `make_plan` default |
| trading window | none (V3-lite only uses it) | same | — |
| sizing | floor(bal / 2500) + 1, ≤ 10, × 0.01 lot per leg | same | `819-822` |
| account | $2,000 per window, no swap or commission, leverage not modelled | same | `77`, `final10.py:68-69` |
| history | from 2018-01-01 (the store's start) | same | `final10.py:65` |
| ask model | bid + M1 mean spread | same | `16`, `568` |

---------------------------------------------------------------------------------------------------------

## 10. Facts about the 8-year trades (from `trades_*.csv.gz` and the probe)

* S1 + votes: 88 trades (46 long, 42 short).
  * Legs per trade: 1 leg 11, 2 legs 15, 3 legs 12, 4 legs 50.
  * Holding time: median 10.2 days, max 69.2 days. None was stopped in its entry bar.
  * N at entry: median $1,838, 3.89% of the price. So the 2N stop sits about 7.8% away and the adds about 1.9% apart.
  * The biggest trades: +$2,090 (Oct-Dec 2024), +$1,560 (Feb-Mar 2024), +$1,228 (Jan-Mar 2026), +$1,164 (Aug-Sep 2026).
* S2 + votes: 60 trades (31 long, 29 short).
  * Legs per trade: 1 leg 12, 2 legs 8, 3 legs 5, 4 legs 35.
  * Holding time: median 10.9 days, max 179 days.
  * N at entry: median $1,446, 3.53% of the price.
  * The biggest trades: +$1,923, +$1,698 and +$1,389.
* Both rows share several entries, wherever the S1 level was the 55-day failsafe or the 20- and 55-day
  levels coincided:
  * the two Nov 2018 shorts, the first of which is an identical trade;
  * the last one: a SELL opened 2026-11-08 22:00 at 74,054.54, 3 legs, still open at the data end and
    closed by the window end at 71,367.58.
* The last D1 bar in the data (2026-11-12) had N 2,296.03, hi20 81,908.47, lo20 = lo55 = lo10 71,016.16,
  hi55 87,399.03 and hi10 81,121.88. `use20` was False.

---------------------------------------------------------------------------------------------------------

## 11. Reproduction (read-only probe, `turtle_probe/probe.py`)

It loads `X.load_market("BTCUSDm", earliest="2018-01-01", end="2026-11-13")` and computes
`X.bot_signals`. It then runs `F._bar_account(X, m, X.filtered(X.turtle(m, s).plan, m, sig.votes_at),
X.BOT, a_ix, z_ix)` for each window. It ran with `NUMBA_CACHE_DIR` and the vote cache in the scratchpad
and `PYTHONDONTWRITEBYTECODE=1`, so nothing was written to the repo.

| row | 8y | 5y | new | 1y |
|---|---|---|---|---|
| S1 + votes | 6,977.48 / 46.0% / 88 | 6,304.88 / 44.6% / 58 | 2,742.20 / 10.7% / 21 | 3,412.49 / 26.4% / 11 |
| S2 + votes | 7,814.72 / 32.5% / 60 | 3,546.56 / 38.4% / 41 | 2,857.89 / 9.4% / 14 | 3,039.45 / 22.4% / 7 |

Identical to `runs_BTCUSDm_bars.csv` / `runs_BTCUSDm_warm.csv`.

---------------------------------------------------------------------------------------------------------

## 12. The live branch today (hedging_btcusd6 / 7 / 8)

* What differs between the branches: `git diff --name-only` shows 6 vs 7 and 6 vs 8 differ **only in
  `mt5_credentials.json`**. It exists on each branch and has `demo` and `live` keys; I did not open it.
  `app.py:157-175` reads `credentials[self.mode]`, and `start_job.bat:62` runs
  `app.py %MODE% --symbol BTCUSDm` (default mode demo; the Python path for demo is set on lines 18-22).
  The pattern for a demo branch is the same code with its own credentials file.
* The live loop, `app.py:479-845`:
  * one poll about every second (`time.sleep(max(brake, 1))`, line 834);
  * slopes from `get_rates(..., RSI_CANDLE_COUNT=500, simple=True)` (582-584);
  * `copy_rates_from_pos(symbol, timeframe, 0, count)` (`mt5_helper.py:272`) **includes the forming bar**,
    so the live votes are forming-bar votes;
  * the timeframes fetched are M1, M5, M15, M30, H1, H4 and H6 (`constants.py:36,45-47,53,100-102`):
    **no D1 bar is fetched**;
  * entries are market deals only (`mt5_helper.py:454-529`). `_build_request` sets "auto" SL = ask −
    ask×1 and TP = ask + ask×1, i.e. SL 0 / TP 2×ask for a buy and SL 2×ask / TP 0 for a sell
    (`RISK_REWARD_RATIO = [1, 1]`, `constants.py:121`);
  * there are no pending orders, no SL modification and no magic number;
  * exits are `close_by_type` (531-621);
  * the re-entry cooldown is 300 s (`constants.py:113`, `app.py:646`);
  * the brake applies outside the trading window (`app.py:513-517`). For BTC the window is Mon 00:00 →
    Sun 23:59, so app.py's half-open test leaves the last minute of each week outside;
  * trading is skipped when the M1 market probe shows no activity for 3 minutes
    (`app.py:543`, `constants.py:19`);
  * no state is persisted: `_last_close_time` lives in memory only.
* `OUTPUT_DIR = C:\Alcadeias` (`constants.py:124`) is shared by every bot on one Windows machine.
  `BTCUSDm.json`, the logs and `active_config.json` would collide if two branches ran on one host.
* Reusable for a port:
  * MT5 init and login;
  * `symbols.json` and the unit rule (`app.py:466-511`);
  * `indicator.py` unchanged;
  * `Strategy._weighted_score` for the M15 agreement;
  * the JSON and dashboard plumbing;
  * `get_rates` (with closed-bar handling added).

---------------------------------------------------------------------------------------------------------

## 13. What a live MT5 implementation needs to reproduce the backtest

### Data
1. **D1 bid bars**, completed only. Take bars whose `time < today 00:00 UTC (server)` from
   `copy_rates_from_pos(sym, TIMEFRAME_D1, 0, n)`; do not trust "pos 1" before the first tick of the new
   day.
   * The minimum is 56 bars for the 55-day channel.
   * N needs about 270+ bars to agree with the 2018-seeded backtest to 1e-6, and the S1 filter about
     50+ bars to converge.
   * **Use about 1,000 bars.** Check there are no missing days. The backtest would merge a UTC day with
     < 360 M1 bars into the next, but that never happened on BTC 2018-26.
2. **M15 bid bars**, completed only, ≥ 500 (better 1,000). Drop any bar with `time + 900 > server_now`.
   * Votes: the live `calculate_rsi` / `calculate_macd` / `latest_pivot_slope` with the constants above.
   * long ok = RSI sign +1 and MACD sign +1; short ok = both −1.
   * Recompute at every M15 close. **Never use the forming bar.** That would be a different, untested
     strategy, the effect FINAL10 §7 measured on V3-lite.
3. **Live bid/ask** (`symbol_info_tick`) for software triggers.
4. **The account's realized balance**, read when flat, for s.
5. Symbol facts to check on the demo:
   * `digits` = 2 (tick 0.01), volume min/step 0.01;
   * `trade_stops_level` / `trade_freeze_level`: the minimum distance for pending orders and SL;
   * filling modes;
   * the **swap** on BTCUSDm. The backtest has none, and trades last a median 10 days, up to 69 (S1) or
     179 (S2) days.
   * Confirm that the server time is UTC.

### Timing
* **At each new UTC day** (first poll at or after 00:00 UTC with the new D1 bar available):
  1. recompute N[b], the 10/20/55-day channels and, for S1, `use20[b]`, by replaying
     `_turtle_s1_use20` over the whole loaded D1 history;
  2. set today's levels (buy = high channel + 0.01, sell = low channel − 0.01), replacing yesterday's;
  3. if in a position, raise the stop to the exit channel (S1 10-day, S2 20-day) if tighter, never lower.
* **At each M15 close**: recompute the vote.
* **Every poll** (the backtest resolution is one M1 bar, using its extremes):
  * entry trigger: flat, today's orders not consumed, vote agrees, and `ask >= buy level`
    (or `bid <= sell level`);
  * pyramid trigger: `ask >= last_fill + 0.5·N_entry` (or `bid <= last_fill − 0.5·N_entry`), units < 4,
    any vote;
  * stop check, if the stop is not held broker-side.
* No pause after an exit beyond the next minute. The live 300 s `REENTRY_COOLDOWN_SECONDS` is a deviation
  if it is kept. There is no trading window and no end-of-day flat.

### Order types
* **Entry.** The vote gate cannot be expressed as one native order. Two options:
  * **(a) Software trigger plus a market deal** (TRADE_ACTION_DEAL). Simplest. It fills at the current
    ask rather than exactly at the level, and adds poll latency.
  * **(b) A native BUY STOP / SELL STOP** (TRADE_ACTION_PENDING at the level, an expiry or deletion at
    the next 00:00 UTC). Place it only while the vote agrees and delete it when the vote flips.
    * If the vote turns on with the price already through the level, send a **market** order: the
      backtest fills at the ask open in that case, 38/88 S1 entries and 27/60 S2.
    * A BUY STOP triggers on the ask and a SELL STOP on the bid, as in the backtest.
    * Delete the opposite order on fill (one fill cancels both until the next D1 close).
* **Pyramid adds.** Use a native BUY STOP at `last_fill + 0.5·N_entry` (SELL STOP mirror), re-placed
  after each fill from its **actual** fill price, or a software trigger. Size s × 0.01 lot, the same as
  unit 1. At most 4 legs in total. Not vote-gated, and no add in a moment the stop is hit.
* **Stop.** Use a broker-side SL on **every** leg, all at one common level, modified with
  TRADE_ACTION_SLTP:
  * at entry: long SL = max(fill − 2·N_entry, exit-channel level as of the last D1 close); short mirror;
  * after each add: SL = max(SL, new_fill − 2·N_entry);
  * at each 00:00 UTC: SL = max(SL, the new exit channel).
  * MT5 triggers a BUY position's SL on the bid and a SELL's on the ask, matching the backtest
    (`l <= stop` and `h + spread >= stop`).
  * Replace the current `_build_request` dummy SL/TP (100% of price) and do not send a TP.
* **Exits** happen only via that SL. There is no target, no force-close, no +$unit target and no Fibo
  ladder.
* On a hedging account each unit is its own position. Give the strategy a magic number and a comment
  (e.g. leg number and N_entry) so legs can be identified.

### State to persist across restarts (and how to recover it)
| state | why | recoverable from MT5? |
|---|---|---|
| direction, legs (tickets, fill prices, times), units count | adds, P/L, the 4-unit cap | yes: `positions_get` (magic/comment) |
| `N_entry` (frozen), `last_fill` | add level and 2N moves | `last_fill` = the newest leg's `price_open`. `N_entry` = N of the D1 bar that closed before the first leg's day, recomputable, but store it (e.g. in the comment or a state file) |
| current stop level | it ratchets and never loosens | the legs' SL, if broker-side |
| unit size s | fixed for the whole trade | the legs' volume |
| "today's orders consumed" flag | one fill cancels both orders until the next 00:00; an exit later that day must not re-enter (unless the entry was on an earlier day) | from `history_deals_get` (an entry deal since 00:00 UTC), or persist it |
| pending-order tickets, if option (b) | delete or replace on vote flips and at 00:00 | `orders_get` |
| S1 filter state (hyp, entry, stop, last_win), use20, N, channels | levels for today | deterministic: recompute from the D1 history at startup and at each 00:00 (do not persist; converges within ~50 days) |
| M15 vote | the gate | recompute from bars |
| last exit time | the 60 s gap | negligible |

Keep a per-account JSON state file, because `C:\Alcadeias` is shared, and reconcile it with
`positions_get` / `orders_get` / deals at startup. The backtest ended **in** a 3-leg short (both rows);
a live start is flat and simply waits for the next breakout.

### Validation before the demo
Build a replay test that feeds the stored M1 bars through the port's decision code (M1-bar granularity)
and compares trades with `external.run_path(m, X.filtered(X.turtle(m, s).plan, m, sig.votes_at), a, z)`.
The existing parity machinery does not cover this strategy.

---------------------------------------------------------------------------------------------------------

## 14. Risks: why a port could differ from the backtest

1. **Forming-bar vs closed-bar votes.** The backtest uses closed M15 bars. `app.py` computes slopes with
   the forming bar (`copy_rates_from_pos(..., 0, 500)`).
2. **Fill model.**
   * The backtest fills a stop exactly at its level (or at the M1 open) and uses ask = bid + the bar's
     **mean** spread.
   * Real stops slip, and spreads widen in fast BTC moves.
   * A software-emulated trigger adds poll latency.
   * 43-45% of entries (38/88 S1, 27/60 S2) were vote-delayed, market-like fills at an M15 boundary. The
     port must enter at market when the vote turns on beyond the level, not wait for a fresh touch.
3. **Bars and data.**
   * The backtest's D1 and M15 bars come from the Exness public tick archive, which has holes: 17 BTC days
     have < 1,300 M1 bars, e.g. 2021-03-02 with 803. MT5's own bars may differ.
   * Pivot votes (strict comparisons) and channel levels can flip on small differences.
   * The D1 boundary must be 00:00 UTC (server GMT+0 is assumed).
4. **The S1 filter is path-dependent.** It must replay `_turtle_s1_use20` exactly: D1 bid OHLC, no spread,
   1 unit, fixed 2N stop, the previous day's 10-day exit, gap-at-open rules, both directions, ignoring the
   votes. Too short a history gives different `use20` days (converges within ≤ 47 days in tests).
5. **State handling.** The details are: one fill cancels both orders until the next 00:00; N frozen at
   entry; adds chain from actual fills; the stop never loosens; legs share one stop. The live bot
   persists nothing, so a restart mid-trade must rebuild this state.
6. **Sizing depends on the balance.** The backtest starts at $2,000 (s = 1). A demo with a different
   balance trades bigger legs (s = floor(bal/2500) + 1). The unit must be fixed at the first fill, and
   pyramid legs are the same size.
7. **No swap or commission** in the backtest, while trades are held for days to months.
8. **Cooldown, window and liveness rules** in `app.py` (300 s re-entry cooldown, the Sunday 23:59 brake
   minute, the 3-minute liveness skip) are not in the Turtle backtest.
9. **Small samples and a concentrated edge.**
   * 88 (S1) and 60 (S2) trades in 8 years, with a win rate of about 38%.
   * Profit comes from a handful of trend trades, and there are losing years: 2025 was −31% (S1) and
     −15% (S2), and 2022 was −3.0% for S2 (§0).
   * Only Nov 2018 – Dec 2020 is out of sample. S2 + votes was picked after the results (warm re-check).
   * S1 + votes has the higher 5y and 1y figures; S2 + votes the higher 8y figure, with a lower DD.
10. **The two rows overlap.** They share many trades, including the open Nov 2026 short, so two demo
    accounts running them are highly correlated.
11. **Broker constraints.** `trade_stops_level` / `freeze_level` can reject a pending order or SL
    placed near the price (fall back to a market deal), and the IOC filling and price/deviation fields
    in the current request builder need care.
12. **No parity harness.** The Turtle has no tick-engine or reference-engine implementation, so
    `engine/parity.py` cannot certify a port. It needs its own replay test against `external.run_path`.
