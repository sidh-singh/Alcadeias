# TradeIQ's "9 best TradingView indicators going into 2027" on gold and BTC: pre-registration

Written 28 Nov 2026 on `backtest_hedging`, before any rule of this study was run on our data for profit or loss. The
sha256 of this file is in `PREREG.md.sha256`. Every later change of a rule is a deviation, logged in `DEVIATIONS.md`
with its reason, and written before the result it could affect exists. This is the second TradeIQ study. The first,
`backtest_results/tradeiq_rsi/` ("study 1"), keeps its own plan, results and code. Nothing of it is edited here.

**What was already looked at (disclosure).** Five reading passes ported parts of the scripts in scratch code, outside the
repository, and counted events on our bars to plan this test. They looked at counts, timings and geometry only, never
profit or loss, and only at bars up to 2024-06-30 (most only to 2022-12-31). Examples: ribbon flips per year, zigzag
swings, Wyckoff entries (4 on gold 1H in 2019-2022), session ranges against spreads, Heikin Ashi streak lengths. One
pass also printed the profit of two Turtle filters. That belongs to the bot-design study (`backtest_results/bot_filters/`),
where those two pairs are logged as seen. The hold-out's market path is known from study 1's exam: gold's rally and its
fall back, and BTC's run to about $126k and back. No rule of this study has been run there.

## 1. The question

The owner sent the transcript of TradeIQ's video "9 best TradingView indicators going into 2027" and the Pine source of
eight of the nine scripts. The ninth, Coil Breakout AI, is private and has no source. Source folder:
`/Users/sidharthsingh/Desktop/study/indicator/` (read-only; not copied into the repository, which is public).

| # in the video | Script | Author | What it is for, per the video |
|---|---|---|---|
| 1 | Trend Target Ribbon | BOSWaves | the trend tool: flips, a swing stop, 1-4R targets |
| 2 | Wyckoff | theUltimator5 | accumulation and distribution; entries after the spring and its test |
| 3 | Coil Breakout AI | TradeIQ (private) | breakouts from quiet "coils". No code, so we test our own version (6.9) |
| 4 | Market Structure Dashboard | Flux Charts | context: which way the higher timeframes point |
| 5 | Swing Profile | BigBeluga | levels: the point of control (POC) of the last swing leg |
| 6 | Session Hunter | TradeIQ | five ICT session setups (sweeps and breakouts) |
| 7 | Ultimate Opening Range Breakout | LuxAlgo | the New York opening range, its breakouts and hit rates |
| 8 | Harmonic & Chart Patterns | AI-AlgoCode | 22 harmonic and 16 chart patterns, with a stop and two targets |
| 9 | Heikin Ashi Candles, Trend Strength & Trend Age | LunqFX | trade management: hold strong, tighten on weakness |

1. Used the way the video says, does each script make money after Exness costs on XAUUSDm and BTCUSDm, and on which
   timeframes? Does it hold on data it was not chosen on?
2. Do the video's pairings help: the ribbon gated by the higher-timeframe direction or by the dashboard, Heikin Ashi
   managing open trades, the "2027 chart setup"? Do the owner's MA200 filters help, as they did on BTC in study 1?
3. Our own combinations (section 6.11): do any of them do better than the scripts alone?
4. How do the answers compare with study 1, with buy-and-hold, and with the designs the bots run? Should anything go to
   a bot?

## 2. Data

- **Ticks:** Exness ticks (bid and ask, UTC ms), the bots' own source, from the store as refreshed on 28 Nov 2026:
  - gold to 2026-11-25 23:59:59 UTC;
  - BTC to 2026-11-26 23:59:59 UTC.
  - Gold's 2016 months are downloaded first: `python -m backtesting data --symbols XAUUSDm --from 2016-01 --to
    2016-12`. They are warm-up for the gold Early exam (section 3). If the download fails, the Early window starts
    at the first day on which every indicator it needs is warmed up, and that is logged.
- **Bars:**
  - 1H, 4H and 1D bars are built exactly as study 1 built them (`tradeiq_market.TMarket.tbars`; UTC boundaries; a
    UTC day with fewer than 360 M1 bars is merged into the next day).
  - New: M5 and M15 bars, built the same way on UTC boundaries. New York's offset from UTC is a whole number of
    hours, so they are also New York bar boundaries.
  - New: weekly bars, for the dashboard. A week is the ISO (Monday-start) week of the merged 1D bars.
  - Tick volume is the sum of the M1 tick counts, and the spread is tick-weighted.
- **Price:** the bid OHLC is the indicators' source (TradingView's CFD charts show the bid).
- **Volume:**
  - Gold uses tick volume.
  - BTC uses Binance BTCUSDT spot volume for every rule that reads volume: Wyckoff, the Swing Profile POC and delta,
    the ORB's high/low-volume tag, Session Hunter's relative-volume confirmation, and the coil's volume grade. The
    reason: Exness BTC tick volume is a heartbeat of about one tick a second, with a coefficient of variation of 0.06.
  - Study 1's 1h klines serve 1H and up. 5m klines are fetched from data.binance.vision for M5 and M15 (M15 = the
    sum of three), with study 1's checks: bar times, gaps, and a correlation of closes above 0.999.
  - If a check fails, the BTC rows that need that volume are dropped, and that is logged.
- **Claim-check markets** (information only; they are not the owner's markets; section 8):
  - USTECm, in the store from June 2020;
  - EURUSDm and GBPUSDm, from November 2017.
- **Clock:** New York times use America/New_York with daylight saving (`external.local_seconds` /
  `utc_of_local`).

## 3. Windows

| Window | Gold | BTC | Use |
|---|---|---|---|
| Warm-up | data start to 2018-12-31 | data start to 2018-12-31 | indicators only |
| Development | 2019-01-01 to 2022-12-31 | same | every variant; the selection |
| Validation | 2023-01-01 to 2024-06-30 | same | every variant; the selection |
| Hold-out (exam 1) | 2024-07-01 to data end | same | the champions' verdict |
| Early (exam 2, gold only) | 2017-01-01 to 2018-12-31 | none (BTC data start in 2018-01, with gaps) | the gold champions' second verdict |

- The same three main windows as study 1, so that every number is comparable.
- The Early window has never been scored by any study (it was warm-up only). Gold drifted sideways in it, between
  $1,120 and $1,370, unlike the 2019-2026 rally.
- **A new hold-out guard,** tied to this study's folder, enforces the plan in code:
  - before `backtest_results/tradeiq_2027/FINALISTS.md` and its sha256 exist, nothing at or after 2024-07-01 is loaded;
  - no window that overlaps 2017-01-01 to 2018-12-31 is scored. Indicators may read those bars, but no profit or loss
    is computed on them.
- Every window is scored as a continuous run that starts flat at its first bar; indicators see the history before it.
- Claim-check markets: Development starts 2020-07-01 for USTECm and 2019-01-01 for the two FX pairs. The other windows
  are as above.

## 4. Execution and costs (study 1's model, unchanged)

**Fills:**
- A decision is taken at the close of a bar of its timeframe.
- It fills at the open of the first M1 bar at or after that close: a buy at the ask, a sell at the bid, where ask =
  bid + that M1 bar's mean spread.
- Stops are checked on every M1 bar. A gap through a stop fills at the open; inside a bar the stop fills at its level.
  One extra spread is charged on every stop fill.
- Targets are limit levels touched inside an M1 bar. If one M1 bar touches the stop and the target, the stop wins.
- Stop-entry orders fill at max(level, ask at the open) for a buy, and the mirror for a sell.
- No swap.

**Size and accounts:**
- Results are per 0.01 lot. Gold makes $1 per $1 of price; BTC makes $0.01 per $1.
- Cost stress x1.5: every spread is multiplied by 1.5.
- Accounts: $2,000 start; the bots' unit rule (unit = floor(balance / 2,500) + 1, at most 10, set when a position
  opens); equity marked at the worst price of each M1 bar; the account is wiped at equity 0.
- One position per variant. The exception is Session Hunter's presets: one position per setup ("lane"), summed, with
  the account from `balke.multi_account`.

**New in this study:** a plan adapter for absolute stops, R targets, break-even moves, stop-entry orders and tightened
stops. It drives `external.make_plan` / `external.run_path` and reuses study 1's slippage, marks, trades and metrics
unchanged. Existing modules are imported, never edited.

**Rules for absolute levels** (a kernel trap, verified on synthetic bars):
- An absolute stop or target level L becomes a distance from the actual fill: |fill − L|.
- An entry is dropped when its fill price is at or beyond its stop, or at or beyond its target.
- A tightened stop is applied only below the bid for a long, or above the ask for a short. A level that price has
  already crossed becomes a market exit at the next M1 open instead.
- The 1.5x run recomputes every distance from its own fills.

**Partial exits** ("half at 2R, let the rest run"):
- Two half-size legs with identical entries: one with the target, one without.
- Profit and loss is their sum. The drawdown is measured on the summed M1 marks.
- For the account curve the same 50/50 mix is applied per unit. Live, this needs at least 0.02 lot per unit, which is
  noted wherever such a row appears.

**After a stop or a target,** a state rule stays flat until its state changes (study 1's DEVIATIONS 1). An event rule
waits for its next event.

## 5. Common definitions

- **ATR** = Pine `ta.atr(14)` (Wilder RMA seeded with an SMA) on the signal timeframe, unless stated otherwise.
- **MA200** = SMA(close, 200).
- **TSI** = study 1's Bjorgum TSI "Fast" (5, 25), using study 1's verified port (`tradeiq_ind.py`).
- **Higher-timeframe (HTF) values** are those of the last CLOSED HTF bar (`tradeiq_market.htf_at`). The one exception is
  Session Hunter's own 1H EMA200, which follows its script (6.6).
- **Filters:**

| Filter | Definition |
|---|---|
| F0 | none |
| F1 | MA200 of the same timeframe: longs only while the close is above it, shorts only while below |
| F2-4H / F2-1D | the same with the MA200 of the last closed 4H / 1D bar. For 1H rules: F2-4H and F2-1D; for 4H rules: F2-1D; for M5/M15 rules: F2-4H and F2-1D |
| F3 | TSI on the side of 0: on the signal timeframe; for M5/M15 rules on the last closed 1H bar |
| FR | the Trend Target Ribbon's trend of the higher timeframe: 1H rules use the 4H ribbon, 4H rules the 1D ribbon. 1D rules use the 1D ribbon itself (there is no weekly ribbon) |
| FS | the Market Structure Dashboard's bias on the signal chart: longs only at LEAN BULL or BULLISH, shorts only at LEAN BEAR or BEARISH (6.2) |
| LO | long only |

- **How a filter applies:**
  - On state rules (study 1's semantics): a state the filter does not allow becomes flat. The position closes when the
    filter turns against it.
  - On event rules (flips, sweeps, breakouts, patterns): the filter must agree at the decision close of the entry. It
    does not close an open trade, which keeps its own exits.
  - Each rule below says which kind it is.
- **Minimum trades** (Development): 30 on M5, M15, 1H and 4H; 15 on 1D.
- **Ports:** two engineers port each script independently from the Pine source. The two ports must agree bit for bit
  on the real bars of both symbols, on every series a rule reads, before any rule runs. Each port has a hand-computed
  test of each named trap (the specs in `STUDY.md`). As in study 1, nothing is tuned: every input is the script's
  default unless this plan says otherwise.

## 6. The rules

### 6.1 Trend Target Ribbon (RIB), 1H / 4H / 1D

**Trend:**
- Inputs: ALMA(close, 34, offset 0.85, sigma 6; m = 0.85·33 not floored); dev = population stdev(close, 34); ATR(14).
- slope = (ALMA − ALMA[3]) / ATR.
- Bull setup: slope > 0.08 and close > ALMA + 0.65·dev. Bear setup: the mirror. Both inequalities are strict.
- trend = the side of the most recent setup; it never returns to 0. A flip is the first setup of the other side.

**Stop (the script's tooltip and the video, the "intended" reading):**
- At a bull flip, raw risk = close − the lowest low of the 12 bars before the flip bar.
- riskDist = min(max(raw risk, 0.75·ATR), 3·ATR); a missing raw risk becomes 0.75·ATR.
- The stop sits riskDist from the fill and never moves. 1R = riskDist. Shorts mirror this.

**Rules** (event rules: the entry is at the flip):
- RIB-LS: a bull flip opens a long, a bear flip a short. The opposite flip exits and reverses. After a stop the rule is
  flat until the next flip.
- RIB-LO: the same, long only.

**Exits:**
- X0: the stop or the opposite flip (the script).
- XT2: all out at the 2R target, else X0.
- XP: half out at 2R, the rest X0 (the video).
- XBE: the stop moves to break-even once 1R is touched, else X0 ("manage it").

**Filters:**
- 1H: F0, F1, F2-4H, F2-1D, FR, F3, FS.
- 4H: F0, F1, F2-1D, FR, F3, FS.
- 1D: F0, F1, F3, FS.
- The video's own rule: "take the flips in the direction of the higher time frame".

**Controls:**
- ALMA-X: trend = sign(close − ALMA), with the same stop rule and X0; LS and LO; three timeframes.
- RIB-LIT (sensitivity; not eligible): RIB-LS, X0, F0, with the stop TradingView literally computes. `ta.lowest`
  inside the flip branch buffers only the lows of earlier flip bars.

**Size:** 2 sides × 4 exits × 17 filter slots = 136 rows, plus 6 ALMA-X rows, plus 3 RIB-LIT rows, per symbol.

### 6.2 Market Structure Dashboard (MSD)

**The bias:**
- The script's bias label: BULLISH, LEAN BULL, NEUTRAL, LEAN BEAR or BEARISH.
- It is a weighted vote of structure, the nearest order block, the nearest fair value gap and the position in the last
  swing, over the rows at or above the chart's timeframe:
  - 1H chart: rows 1H, 4H, D, W;
  - 4H chart: rows 4H, D, W;
  - 1D chart: rows D, W.
- The integer weights and thresholds are the script's.
- Higher-timeframe rows use their last CLOSED bar ("model A"). Live, the script uses the forming bar, which can
  repaint (the video says so). Model A is what TradingView shows on historical bars.
- Pivot ties: strict on both sides (logged).

**Rules:**
- MSD-A1, alone, state rule: long at LEAN BULL or BULLISH, short at LEAN BEAR or BEARISH, flat at NEUTRAL.
- MSD-A2: as A1, long only.
- MSD-A3: as A1, at BULLISH or BEARISH only.
- Each with S0 (no stop) and S1 (3·ATR from the fill, fixed); on 1H, 4H and 1D.

**As a filter on study 1's oscillator rules** (the video's use: context):
- Base rules: RSI, LaRSI, VWRSI, TSI and QQE × R1 (both sides) and R2 (long only) × S0, S1 × 1H, 4H, 1D.
  On BTC the VWRSI uses Binance volume (study 1's "RV" rows).
- MSD-F4: FS as a state filter.
- MSD-F6: the video's literal veto. A long is flat while the 4H, D and W rows all score below 0 (on a 1D chart: D and
  W). A short is flat while they all score above 0.
- Paired with study 1's F0, F1 and F2 rows of the same base. Their published results are reused; they are not rerun.

**BOS-trend** (our own; the dashboard's structure engine as a complete system), a state rule:
- +1 after a bullish break of structure on the chart's row, −1 after a bearish one.
- LS and LO; S1; F0 and F1.

**Size:** 18 alone + 60 MSD-F4 + 60 MSD-F6 + 12 BOS-trend = 150 rows per symbol.

### 6.3 Wyckoff (WY), 1H / 4H / 1D

**Engine:** the script's engine, run from each symbol's data start. Gold uses tick volume, BTC Binance volume.

**Entries:** the script's entry alert only, at the close of the bar that qualifies. The labels, phases and schematics
are drawn back in time and are never used.
- WY-STD: Standard entries, both sides.
- WY-STD-L: Standard entries, long only (the video: "buy accumulation").
- WY-AGG: Aggressive entries, both sides.

**Stop and exits:**
- Stop S-W: the hard level (the spring or UTAD extreme, otherwise the range edge) ∓ 0.15·ATR, fixed.
- Skip guard: an entry is skipped if its stop is less than 0.25·ATR beyond the decision close.
- Exit X-S, structure: at the close of the first bar on which the entry's campaign no longer holds the trade's outcome
  in Phases C-E (a reset, a demotion or an outcome change, including the script's own invalidation and the end of
  Phase E).
- Exit X-S3: X-S plus a 3R target.

**Filters** (event rule): F0 and F2 (1H: F2-4H; 4H: F2-1D; 1D: F1).

**Control:** BTC on Exness tick volume (WY-STD, X-S, F0; three timeframes; not eligible).

**Derived families** (our own; not the script's signals):
- WY-CL, climax reversal: enter at the bar that confirms the climax (selling climax long, buying climax short). Stop
  beyond the climax extreme ± 0.15·ATR. Exit at a 2R target or after 50 bars.
- WY-SP, spring / UTAD: enter at the recovery bar of a confirmed or provisional excursion. Stop beyond the extreme.
  Exit at a 3R target or X-S.
- Both with F0 and F2, on three timeframes.

**Few trades:**
- Below 15 Development trades, a row's verdict is "insufficient events".
- One primary pooled test: WY-STD × X-S × S-W × F0, over both symbols and the three timeframes, in Development plus
  Validation. It reports trades in R and in dollars, against 1,000 placebo sets of random entries matched on symbol,
  timeframe, side, stop distance in ATR and holding time. The result is a p-value.

**Size:** 36 + 18 = 54 eligible rows per symbol, plus 3 control rows on BTC.

### 6.4 Swing Profile (SP), 1H / 4H

**Profile:**
- swingLen 50; bins of 0.5·ATR(200).
- Each bar's volume goes to every bin whose midpoint is within one bin step of the close (strict).
- Buy volume is that of green candles; a doji counts as sell.
- POC ties go to the bin nearest the current close.
- The forming leg's POC is recomputed at every bar from the swing points confirmed by then. A finished leg's POC is
  used only from its flip bar on, because before that it is not yet known.

**Rules** (event rules, at most one trade per swing anchor; shorts mirror longs):
- SP-W1, the video's use: while the forming leg is up, a bar with low ≤ POC and close > POC ("touch and hold") gives a
  long. Stop at the leg's swing low, target the leg's swing high; exit on a flip against the trade.
- SP-W2: as W1, with the stop at POC − 1.5·ATR and the target at 2R.
- SP-W3: after a flip, a touch and hold of the just-finished leg's POC in the new direction. Stop POC ∓ 1.5·ATR,
  target 2R.

**Filters:**
- F0.
- FD: the leg's delta% on the trade's side. This is the video's "a leg up with weak buying is a warning".
- F2: 1H rows use F2-4H, 4H rows F2-1D.
- LO.

**Placebo** (control; not eligible): W1-W3 with the POC replaced by the leg's 50% level; F0 and F2.

**Size:** 3 × 4 × 2 = 24 eligible rows, plus 12 placebo rows, per symbol.

### 6.5 Opening Range Breakout (ORB), M5 / M15

**Range and breakout:**
- Range: the high and low of 09:30-10:00 New York time, with daylight saving, on New York weekdays (BTC too: the New
  York open means nothing at weekends).
- Breakout: the script's crossover of the close from 10:00 on; one label per side per day; no new trade while one is
  open; the bear branch evaluated before the trail exit (the script's order).
- Entry decisions only up to 16:00 New York. Everything is flat at the last chart-bar close at or before 16:55 New York,
  because gold's daily break starts at 17:00.

**Rules** (event rules; market entry at the next M1 open, except O5):
- O1, the script's trade: exit on the close-based trail (max of the previous trail and low − 2·ATR for a long) or at
  the flat time. No other stop.
- O2: target T1 = the range edge + 1 range width; stop at the far side of the range.
- O3: as O2, with T2 = 2 widths.
- O4, the video's "use the hit rates to pick your target": the furthest of T1-T3 whose hit rate after past breakouts
  in that direction is at least 50%. Past days only, with at least 60 of them; otherwise T1. Stop at the far side.
- O5: stop orders at both range edges, one cancels the other, active 10:00-16:00; stop at the far side; exits as O1.

**Filters:**
- F0.
- HV: the breakout bar's volume above the SMA(20) of volume, the bar included (the video's advice).
- F2-4H, F2-1D.
- HV + F2-4H.
- LO (gold only).

**Controls** (not eligible; they serve claims 7 and 9):
- LV only (O1-O4).
- The script's literal fixed UTC−5 clock (O1). It is an hour late from March to November.
- BTC on all 7 days (O1).

**Our own:**
- ORB-CX, gold only: the COMEX-open range 08:20-08:50 New York, for O1 and O5, with F0 and F2-4H.
- TIGHT: skip ranges wider than 50% of the mean range of the last 10 weekday sessions (Session Hunter's tight-range
  idea), on O1 and O5.

**Size:** 2 timeframes × 5 rules × 5 filter sets = 50 rows per symbol, plus 10 LO rows on gold, 8 ORB-CX rows and 4
TIGHT rows; plus the controls.

### 6.6 Session Hunter (SH), M5 / M15

**The script as coded:**
- New York clock with daylight saving. The day key is the New York date of time + 4h.
- Five setups:
  - AS: Asia-range sweep, faded in 02:00-05:00;
  - LS: London-range sweep, faded in 07:00-11:00;
  - PD: previous weekday's high/low sweep, faded in 02:00-11:00;
  - AB: Asia-range breakout, followed in 02:00-05:00;
  - OR: opening-range breakout, followed in 10:00-12:00.
- The sweep and breakout state machines, the confirmations, the minimum stop of 0.5·ATR, the cancels at entry, and
  the Monday quirk (no PD on Mondays), all as coded. A variant that gives Monday Friday's levels is information only.
- The script's 1H EMA200 is the EMA of the last 1H bar closed at or before the chart bar's OPEN, as its
  `request.security(..., ema[1], lookahead_on)` computes it.
- Each setup is one lane, with at most one trade a day.

**Confirmation sets:**
- K0: none.
- K1: FVG.
- K2: FVG + 1H EMA200 trend (the script's default).
- K3: FVG + market structure shift (its Forex preset).

**Exits:**
- E1: hold to 16:00 New York (the script's default and, per its author, "the exit that tested best").
- E2: the 2R target.
- E3: the opposite side of the swept range (cancelled when it is less than 1R away).
- Stops at the sweep extreme, or at the range midpoint for breakouts. Market entry at the next M1 open, dropped when
  that open is at or beyond the stop.

**Grids:**
- Core: 5 setups × K1-K3 × E1-E2 × 2 timeframes = 60 rows.
- Plus K0 × E1 (10 rows) and K2 × E3 (10 rows).
- Plus the three presets as lane portfolios, on both timeframes (6 rows):
  - Custom: AS + LS, K2, E1;
  - Forex: AS, K3, E1;
  - Nasdaq: LS + PD, K2, E1.
- Plus K2 × E1 with the 1H EMA200 replaced by F2-4H, F2-1D or F3 (30 rows).
- Size: 116 rows per symbol.

**Pre-registered hypothesis:** on gold AB is positive and AS is negative in Development and Validation. Basis: the
improve study found the Asian-range breakout positive in 5 of 5 periods.

### 6.7 Harmonic & Chart Patterns (HP)

**Zigzag and patterns:**
- Zigzag depth 5; all 38 patterns; the script's 144 ratio constants, parsed from the source text.
- The script's predicates and its first-hit order.
- Confirmed patterns are known when the next swing appears, a median of 3 bars after point D. By then 41-48% of
  harmonics are already past their first target.
- The "forming" detection runs at every bar close on the zigzag state of that bar. That is what a live user sees.

**Rules** (event rules; the first bar of each forming instance; time stop 30 bars after D, the script's plan horizon):
- HP-HF: a forming harmonic gives a market entry. Stop D − dir·0.13·AD. Targets TP1 = 0.382·AD, TP2 = 0.618·AD, or
  50/50 of the two. Skipped when the close is already beyond TP1. On 1H, 4H and 1D, with F0, F2 and FR (1D: F1 in
  place of F2).
- HP-HC, control: the confirmed alert with the script's levels and the same skip rule. TP1, F0, three timeframes.
- HP-CF: a forming chart pattern; reversal and continuation families pooled. Entry at the market. Stop p2 − dir·0.5·h;
  TP1 = h, TP2 = 1.618·h. On 1H and 4H, with F0, F2 and FR.
- HP-CS: a stop order at the neckline p2 once every condition except the breakout close holds ("the breakout where the
  entry is real"). TP1; F0 and F2; 1H and 4H.
- HP-CC, control: the confirmed chart alert. TP1, F0, 1H and 4H.
- HP-DRAWN, information only, never a candidate: the plan as drawn back at D, with look-ahead. It measures how good the
  drawn patterns look.

**Size:** 27 HF + 3 HC + 12 CF + 4 CS + 2 CC = 48 eligible rows per symbol.

### 6.8 Heikin Ashi (HA)

**Candles and phases:**
- haC = (O+H+L+C)/4; haO = (haO[1] + haC[1])/2.
- Phases in the script's order: INDECISION, STRONG, WEAK, STEADY. A tie in colour counts as bullish.
- Streak statistics are computed causally at every bar, from the streaks finished before it, using all history from
  the data start. Rare-age rules need at least 50 finished streaks of that colour.

**Management overlays** (the video's use, "not for entries"). Each is paired with its base rule over the same windows.
- M1: exit at the close of a Heikin Ashi colour flip against the position.
- M2: at an indecision candle right after 2 or more strong candles, raise the stop to the tighter of break-even and
  that bar's low. Shorts mirror this. The absolute-level rules of section 4 apply.
- M3: the same tightening after 2 consecutive WEAK candles.
- M4: exit when the streak reaches its rare age (the 90th percentile).
- M5: M1 + M2, the video's complete "hold on strong, tighten up, get out on the flip".
- HA-AND: the base, entered only while the Heikin Ashi colour agrees.
- After a Heikin Ashi exit, the base stays flat until its own state changes.
- Bases:
  - study 1's three finalists on each symbol (`tradeiq_rsi/FINALISTS.md`);
  - RIB-LS × X0 × F0 and RIB-LO × X0 × F0 on 1H, 4H and 1D.
- Heikin Ashi is computed on the base's own timeframe.
- Size: 9 bases × 6 = 54 rows per symbol.

**Entry rules** (controls; the video says not to use it for entries):
- HA-H1: in at the first STRONG candle of a streak, out at the flip.
- HA-H2: colour stop-and-reverse.
- LS and LO; F0 and F2 (1D: F1); 1H, 4H and 1D. 24 rows per symbol.

### 6.9 Coil breakout (COIL): our version of the private Coil Breakout AI, 1H / 4H / 1D

The script is private, so this rule is ours, built only from the video's description: "the candles get smaller and the
range gets tighter ... when the coil breaks with the trend ... a grade from the breakout candle's size and volume ...
entry, stop, 1, 2, 3R and a trend trail to get out". A coil is the classic squeeze: Bollinger Bands inside Keltner
Channels.

**Coil and breakout:**
- squeeze_on: SMA(20) ± 2·stdev(close, 20) lies inside SMA(20) ± 1.5·ATR(20).
- A coil is at least 6 consecutive squeeze_on bars. Its box is the highest high and lowest low of those bars.
- It stays armed for 12 bars after its last squeeze bar, or until a new coil replaces it.
- The breakout is the first close above the box (long) or below it (short), once per coil.

**Trend filter at the breakout:**
- COIL-RIB: the ribbon's trend (same timeframe) on the breakout's side.
- COIL-MA: F1.
- COIL-0: none.

**Stop and exits:**
- Stop: the opposite box edge, as a distance clamped to [0.75, 3]·ATR(14) at the breakout close, set from the fill.
- X-TR, the trend trail: exit at the close when it falls below the highest close since the entry minus 3·ATR
  (mirrored for shorts), or at the stop.
- X-3R: X-TR plus a 3R target.

**Grades** (the three the video says helped):
- BIG: the breakout bar's range is at least 1.5·ATR.
- VOL: the breakout bar's volume is at least 1.5 × SMA(20) of volume.
- ADX: Pine `ta.dmi(14, 14)` ADX is at least 20.
- ALL3: all three.

**Size:** COIL-RIB × {X-TR, X-3R} × {none, BIG, VOL, ADX, ALL3} × 3 timeframes = 30 rows; COIL-MA and COIL-0 × X-TR ×
none × 3 timeframes = 6 rows. 36 rows per symbol.

### 6.10 The video's "2027 chart setup" (STK), our reading, 1H / 4H / 1D

"One trend tool, the ribbon; one context tool, the dashboard." These are state rules:

- STK-RM: long while the ribbon's trend is up AND the dashboard's bias is LEAN BULL or better; short in the mirror
  case; otherwise flat.
- STK-RA: the ribbon's trend AND the higher-timeframe MA200 (1H: F2-4H; 4H: F2-1D; 1D: F1).
- STK-RMA: all three agree.
- LS and LO; stop S1.

**Size:** 3 × 2 × 3 = 18 rows per symbol.

The video's crypto setup, "the ribbon, the dashboard and coil breakout on the 4-hour chart", is covered by RIB × FS,
STK-RM and COIL-RIB on 4H. Its Nasdaq setup (M5) is out of scope except as a claim check (section 8).

### 6.11 Our own combinations, in one list

These are rows already listed above, each with the reason for including it:

| Combination | Reason |
|---|---|
| RIB × F2 / FR / FS / F3 | the video's "trade flips in the higher-timeframe direction"; study 1's MA200 and TSI lessons |
| RIB × XP / XBE and HA overlays on RIB | the video's management advice for the ribbon |
| MSD-F4 / F6 on study 1's rules | the dashboard as context, against the MA200 filters of study 1 |
| BOS-trend | the dashboard's engine as a full system |
| WY × F2, WY-CL, WY-SP | Wyckoff with the higher-timeframe trend; more frequent sub-events |
| SP × FD / F2 | the video's "weak buying" warning; pullbacks with the trend |
| SH × F2 / F3 | the owner's MA200 instead of the script's 1H EMA200 |
| ORB × HV / F2, ORB-CX, TIGHT | the video's volume advice; gold's own US open; tight ranges |
| HP × F2 / FR | harmonic pullbacks with the trend |
| COIL | the private script's idea, rebuilt |
| STK | the video's 2027 setup as a rule |

Nothing else is run before the exam. Any addition is a deviation, and is labelled as found after seeing results.

## 7. Scores, the selection and the exam

**Scores:** per variant and window, per 0.01 lot after costs, as study 1:
- net profit (x1.0 and x1.5);
- trades, win rate, profit factor, average R where a rule has an R;
- max drawdown, on equity marked at M1 extremes;
- profit / max drawdown (P/DD);
- the share of positive calendar quarters;
- annualised weekly Sharpe;
- average holding time and time in the market.

Buy-and-hold 0.01 lot is the reference.

**A variant qualifies when** (study 1's rule):
1. its Development net profit is above 0 at x1.0 and x1.5 costs;
2. it has the minimum number of Development trades (section 5);
3. its Development P/DD is at least 1.0, with at least 50% of the quarters positive;
4. its Validation net profit is above 0 at x1.0.

Rows marked "not eligible" or "information only" are scored but never selected. Every other row, controls included,
can qualify.

**Size:** about 1,460 eligible variants (738 on gold, 720 on BTC), plus about 60 control and information rows.

**Families:**

| Family | What it contains |
|---|---|
| RIB | the ribbon rows |
| ALMA-X | the plain ALMA-cross control |
| MSD-ALONE | the dashboard alone |
| MSD-FILTER | MSD-F4 and MSD-F6 |
| BOS | BOS-trend |
| WY | the script's Wyckoff entries |
| WY-DERIVED | WY-CL and WY-SP |
| SP | Swing Profile |
| ORB | ORB, including ORB-CX and TIGHT |
| SH | Session Hunter |
| HP-HARMONIC | the harmonic rows |
| HP-CHART | the chart-pattern rows |
| HA-ENTRY | the Heikin Ashi entry rules |
| HA-MANAGED | the overlays and HA-AND |
| COIL | the coil breakout |
| STK | the 2027 setup |

**Champions:** per symbol and family, the qualifier with the highest P/DD over Development + Validation together (one
continuous run, 2019-01-01 to 2024-06-30, x1.0). Ties go to Development's P/DD, then to the id. A family with no
qualifier has no champion; its answer is "none".

**Finalists:** per symbol, the three champions with the highest P/DD over Development + Validation, at most one per
script. RIB and ALMA-X count as one script; so do MSD-ALONE, MSD-FILTER and BOS; WY and WY-DERIVED; HP-HARMONIC and
HP-CHART; HA-ENTRY and HA-MANAGED. COIL and STK, our own, count as one each. The finalists get account curves and the "should it
go to a bot" discussion.

**Freezing:** `FINALISTS.md` lists every champion and finalist, with their exact rule rows and the code's git blob ids.
Its sha256 is stored before the hold-out or the Early window is computed for anything.

**The exam:**
- A champion passes exam 1 when, over the hold-out, its net profit is above 0 at x1.0 and its P/DD is at least 0.5.
- A gold champion takes exam 2 on the Early window with the same rule.
- Gold verdicts are "passes both", "passes the hold-out only", "passes Early only" or "fails". BTC verdicts are "pass"
  or "fail".
- **Base rate:** after the exam the same exam is computed for every variant, for information only. It shows what
  share of all variants would have passed, as study 1 showed for gold (90%).

**Multiple testing:** for the best variant of each symbol, the deflated Sharpe ratio for the number of variants run on
that symbol, and White's Reality Check / Hansen's SPA p-value on the Development weekly returns over all variants.

**Accounts** ($2,000 and the unit rule):
- for every champion, finalist and family's best row, over 2019-01-01 to the data end and over the hold-out alone;
- for gold, also over the Early window;
- next to buy-and-hold, study 1's six finalists, and the bots' designs over the same spans.

## 8. The video's claims, checked one by one

Each claim gets a verdict on our two markets: holds, does not hold, or cannot be tested here (and why). The checks on
USTECm, EURUSDm and GBPUSDm are information only. They are reported in R-multiples and profit factor, so no contract
size is needed.

1. Ribbon: "the trend only flips when the slope and the close-beyond-the-band agree, so it ignores most of the noise."
   Test: RIB against ALMA-X, same exits.
2. Ribbon: "take partial profit at the second target and let the rest run." Test: XP against X0 and XT2.
3. Ribbon: "the stop never moves; a trade can hit two targets and come back. Manage it." Test: XBE and the HA overlays
   against X0.
4. Heikin Ashi: "strong candles, you hold; a run of weak candles or indecision after a strong run, you tighten up."
   Test: M2 / M3 / M5 against the base.
5. Heikin Ashi: the panel's "reached age A, then 5+ more" percentages, computed before each year, against what happened
   in that year (calibration).
6. ORB: "a break of the range often sets the direction for the day." Test: P(the 16:00 close is beyond the range on the
   side of the first breakout).
7. ORB: "take the breakouts that come with high volume." Test: HV against LV, same rule.
8. ORB: the dashboard's hit rates are unconditional, not win rates. Test: unconditional against after-breakout rates;
   O4 against O2 and O3.
9. ORB: the UTC−5 default is an hour late in summer. Test: the literal clock against New York time (O1).
10. Session Hunter, the author's test: Nasdaq best with a previous-day sweep and the 1H trend held to the close
    (profit factor 1.95 on 290 trades; "about 3 in 10 win"); a smaller forex edge for the London Judas swing (Asia
    sweep + FVG + structure shift, M15); gold and crypto "nothing held up". Tests: the Nasdaq preset and PD + HTF on
    USTECm M5/M15; the Forex preset on EURUSDm and GBPUSDm M15; all rows on gold and BTC; E1 against E2 and E3 ("holding
    to 16:00 tested best").
11. Swing Profile: "the point of control of the last leg is a level price often comes back to." Test: how often the
    forming POC is touched before the leg ends, against the 50% level (W1-W3 against their placebo).
12. Swing Profile: "a leg up with weak buying is a warning." Test: the next leg's size after up legs with negative
    against positive delta.
13. Dashboard: it "filters out a lot of bad trades". Test: the trades MSD-F4 / F6 remove, and their net, in Development
    and Validation; the filtered rule against the unfiltered and MA200-filtered ones, pair by pair.
14. Dashboard: its higher-timeframe rows use the forming candle and can change. Test: the share of chart closes inside
    a higher-timeframe bar where the forming-bar score differs from the closed one.
15. Wyckoff: it is strict and rare ("when it shows up, it means something"). Test: events per year, and the pooled test
    with its placebo.
16. Wyckoff: "the risk is smallest at the spring and the test." Test: the stop distance in ATR at Standard against
    Aggressive and LPS entries, and the R outcome per entry type.
17. Wyckoff: "on the 4-hour or the daily". Test: entries and results by timeframe.
18. Patterns: they are "only confirmed when the next swing forms ... on an old chart every pattern looks like it caught
    the exact turn". Test: HP-DRAWN against HP-HC and HP-HF.
19. Patterns: "trade the chart patterns on the breakout, where the entry is real." Test: HP-CS and HP-CF against HP-CC.
20. Coil Breakout AI: 731 trades on eight coins on 4H since 2021, one in four won, "almost three times what it lost",
    average winner 8.5R; big candle, volume surge and trend strength helped. It cannot be tested: the script is
    private. Our COIL rows test the idea on BTC and gold 4H, with the same three grades.

## 9. Deliverables

- `RESULTS.md`: the answer in plain English, the champions, the exam, the claims' verdicts, the comparison with study
  1, buy-and-hold and the bots, and the caveats.
- `STUDY.md`: what each script computes, what the video says, and the porting notes.
- `DATA.md`, `PORTING.md`, `CANDIDATES.md`, `FINALISTS.md`, `EXAM.md`, `CLAIMS.md`, `DEVIATIONS.md`.
- CSVs of every variant and window, account curves, trades, PNG graphs and `index.html`.
- **The comparison page** the owner asked for: one HTML page with the equity curves and the metrics (profit, max
  drawdown, P/DD, trades, win rate, profit factor and the rest) of every result of study 1, this study, the bot-design
  study (`backtest_results/bot_filters/`), the bots' published designs and buy-and-hold. It sits in
  `backtest_results/compare/` and is also published as a private page.
- **Code:**
  - `backtesting/research/tradeiq2_market.py`: the M5/M15/weekly bars, the guard and the plan adapter;
  - `backtesting/research/tradeiq2_ind*.py`: the reconciled ports;
  - `backtesting/research/tradeiq2.py`: the study;
  - `tests/test_tradeiq2*.py`.
- Committed and pushed to `backtest_hedging` at each checkpoint (the owner's standing rule of 28 Nov 2026).
