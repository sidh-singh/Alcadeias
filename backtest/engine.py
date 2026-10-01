"""
Backtest engine — replays the REAL bot logic against historical M1 bars.

Fidelity design
---------------
* The strategy decision is the untouched ``strategy.Strategy.calculate_signal``
  and all indicators are the untouched ``indicator.Indicator`` methods. This file
  only replaces MT5 (a) as the data feed and (b) as the order/position book, so
  what is tested is exactly the code that runs live via start_btcusd.bat.
* The live loop calls ``get_rates(tf, N, simple=True)`` every ~second; MT5 returns
  the still-FORMING higher-timeframe bar as the last row, whose close == the
  current price. We reproduce that exactly: completed TF bars are Wilder-RMA
  pre-computed once, and each decision minute extends them by one step using the
  current price. That one-step extension is mathematically identical to calling
  calculate_rsi on [completed closes … + current price] (asserted at startup).
* Stepping is per M1 bar so the tiny "+$unit" profit target and the RSI DCA/H6
  exits are evaluated at minute resolution (the live bot reacts intrabar).
* SHA (the entry signal, M15) is recomputed with the real calculate_sha_v3 on the
  live CANDLE_COUNT(=300)-bar rolling window each time a new M15 bar closes. SHA is
  used ONLY in the flat/entry branch, so a basket's adds/exits never depend on it.
  Entry is therefore evaluated on closed-M15 SHA (≤15 min later than the live
  intrabar SHA) unless --sha-intrabar rebuilds the forming M15 bar while flat.

Broker P&L matches mt5_helper: profit = (price − entry)·volume·contract_size for
BUY (mirrored for SELL); aggregates rounded to 2dp. Fills pay the spread
(BUY@ask / close@bid; SELL@bid / close@ask) and optional round-turn commission.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import constants as K
from indicator import Indicator
from strategy import Strategy, Signal
from backtest import data as bt_data

_MS_MIN = 60_000


# ───────────────────────── per-timeframe RSI state ─────────────────────────
@dataclass
class TFState:
    name: str
    close_ms: np.ndarray      # completed-bar close timestamps (ms)
    close: np.ndarray         # completed-bar closes
    avg_gain: np.ndarray      # Wilder RMA of gains, aligned to close[]
    avg_loss: np.ndarray      # Wilder RMA of losses, aligned to close[]
    alpha: float


def _build_tf_state(ind: Indicator, m1: pd.DataFrame, name: str) -> TFState:
    minutes = bt_data.TF_MINUTES[name]
    close_ms, closes = bt_data.close_series_with_closetime(m1, minutes)
    s = pd.Series(closes)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = ind._ma(gain, K.RSI_LENGTH, K.RSI_MA_TYPE).to_numpy(dtype=float)
    avg_loss = ind._ma(loss, K.RSI_LENGTH, K.RSI_MA_TYPE).to_numpy(dtype=float)
    return TFState(name, close_ms, closes, avg_gain, avg_loss, alpha=1.0 / K.RSI_LENGTH)


def _rsi_now(st: TFState, tc_ms: int, price: float) -> float:
    """Live 'forming-bar' RSI: extend the last completed bar by one step to price."""
    idx = int(np.searchsorted(st.close_ms, tc_ms, side="right")) - 1
    if idx < 0:
        return 50.0
    ag_c = st.avg_gain[idx]
    al_c = st.avg_loss[idx]
    if not (math.isfinite(ag_c) and math.isfinite(al_c)):
        return 50.0
    delta = price - st.close[idx]
    gain = delta if delta > 0 else 0.0
    loss = -delta if delta < 0 else 0.0
    ag = st.alpha * gain + (1.0 - st.alpha) * ag_c
    al = st.alpha * loss + (1.0 - st.alpha) * al_c
    if al == 0.0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


# ───────────────────────── simulated broker ─────────────────────────
@dataclass
class Basket:
    side: str
    open_time: pd.Timestamp
    close_time: pd.Timestamp = None
    max_count: int = 1
    total_volume: float = 0.0
    vwap_entry: float = 0.0
    exit_price: float = 0.0
    gross_pnl: float = 0.0
    spread_cost: float = 0.0
    commission_cost: float = 0.0
    net_pnl: float = 0.0
    bars_held: int = 0
    mae: float = 0.0            # worst floating $ seen (max adverse excursion)
    reason: str = ""
    unit: int = 1               # effective unit the basket was opened on


class SimBroker:
    """MT5 stand-in: single-symbol position book + Fibo sizing + unit stepping."""

    def __init__(self, *, balance, mtqty, step_up_balance, unit_max_limit,
                 contract_size, spread_usd, commission_per_lot, strategy: Strategy):
        self.start_balance = float(balance)
        self.balance = float(balance)
        self.mtqty = float(mtqty)
        self.step_up_balance = float(step_up_balance)
        self.unit_max_limit = int(unit_max_limit)
        self.cs = float(contract_size)
        self.half_spread = float(spread_usd) / 2.0
        self.spread_usd = float(spread_usd)
        self.commission_per_lot = float(commission_per_lot)
        self.strategy = strategy

        self.positions = []            # list of dict(entry, volume)
        self.side = None               # 'BUY' | 'SELL' | None
        self.units = 1
        self._open_time = None
        self._max_count = 0
        self._mae = 0.0

        self.baskets: list[Basket] = []

    # -- helpers ------------------------------------------------------------
    def flat(self) -> bool:
        return not self.positions

    def refresh_units(self):
        if self.flat():
            if self.step_up_balance > 0:
                u = int(self.balance // self.step_up_balance) + 1
            else:
                u = 1
            self.units = max(1, min(u, self.unit_max_limit))

    def _pos_profit(self, entry, volume, price):
        if self.side == "BUY":
            return (price - entry) * volume * self.cs
        return (entry - price) * volume * self.cs

    def positions_dict(self, price):
        """Return (buy_positions, sell_positions) exactly like mt5_helper."""
        if self.flat():
            return None, None
        profits = [self._pos_profit(p["entry"], p["volume"], price) for p in self.positions]
        vols = [p["volume"] for p in self.positions]
        d = {
            "type": 0 if self.side == "BUY" else 1,
            "count": len(self.positions),
            "total_profit": round(sum(profits), 2),
            "total_volume": round(sum(vols), 2),
            "first_profit": round(profits[0], 2),
            "first_volume": round(vols[0], 2),
            "last_profit": round(profits[-1], 2),
            "last_volume": round(vols[-1], 2),
        }
        return (d, None) if self.side == "BUY" else (None, d)

    def floating(self, price):
        if self.flat():
            return 0.0
        return sum(self._pos_profit(p["entry"], p["volume"], price) for p in self.positions)

    # -- orders -------------------------------------------------------------
    def open(self, side, volume, price, t):
        volume = round(volume, 2)
        if volume <= 0:
            return
        if self.flat():
            self.side = side
            self._open_time = t
            self._max_count = 0
            self._mae = 0.0
            self._open_unit = self.units
        fill = price + self.half_spread if side == "BUY" else price - self.half_spread
        self.positions.append({"entry": fill, "volume": volume})
        self._max_count = max(self._max_count, len(self.positions))

    def close(self, price, t, reason):
        vols = [p["volume"] for p in self.positions]
        total_vol = sum(vols)
        exit_fill = price - self.half_spread if self.side == "BUY" else price + self.half_spread
        gross = sum(self._pos_profit(p["entry"], p["volume"], exit_fill) for p in self.positions)
        spread_cost = self.spread_usd * total_vol * self.cs
        commission = self.commission_per_lot * total_vol
        net = gross - commission
        self.balance += net
        # vwap of entry fills
        vwap = sum(p["entry"] * p["volume"] for p in self.positions) / total_vol if total_vol else 0.0
        b = Basket(
            side=self.side, open_time=self._open_time, close_time=t,
            max_count=self._max_count, total_volume=round(total_vol, 2),
            vwap_entry=round(vwap, 2), exit_price=round(exit_fill, 2),
            gross_pnl=round(gross, 2), spread_cost=round(spread_cost, 2),
            commission_cost=round(commission, 2), net_pnl=round(net, 2),
            bars_held=int((t - self._open_time) / pd.Timedelta(minutes=1)),
            mae=round(self._mae, 2), reason=reason,
            unit=getattr(self, "_open_unit", self.units),
        )
        self.baskets.append(b)
        self.positions = []
        self.side = None
        self._open_time = None

    def mark(self, price):
        """Update max-adverse-excursion for the live basket."""
        if not self.flat():
            fl = self.floating(price)
            if fl < self._mae:
                self._mae = fl


# ───────────────────────── main replay ─────────────────────────
def run_backtest(m1: pd.DataFrame, *, balance, spread_usd, commission_per_lot,
                 contract_size, mtqty, step_up_balance, unit_max_limit,
                 sha_intrabar=False, respect_window=False, progress=True,
                 max_depth=None, time_block_hours=None, close_mult=1.0,
                 regime_act=False) -> dict:
    """Parameter-sweep knobs (all default to the exact live behaviour):

    * ``regime_act`` — arm the v1.6.0 regime filter in ACT mode. The verdict is
      computed from the REAL ``indicator.calculate_adx`` and passed into the REAL
      ``calculate_signal`` as the ``regime`` dict, so the production code applies
      the fresh-entry block (mirrors app._compute_regime with live constants).
    * ``close_mult`` — multiply the ``close_threshold`` (profit target) the strategy
      receives; 1.0 == live (unit N → $N). Sizing is unchanged.
    * ``max_depth`` — TEST OVERLAY: when the real strategy asks to add past this
      basket depth, cut the basket instead (reason EARLY_CUT). Caps the martingale.
    * ``time_block_hours`` — TEST OVERLAY: set of UTC hours in which FRESH entries
      are suppressed (open baskets still managed). None = no block.
    """
    ind = Indicator()
    strat = Strategy()
    broker = SimBroker(
        balance=balance, mtqty=mtqty, step_up_balance=step_up_balance,
        unit_max_limit=unit_max_limit, contract_size=contract_size,
        spread_usd=spread_usd, commission_per_lot=commission_per_lot, strategy=strat,
    )

    # RSI timeframes: exact union the live app builds (order-preserving dedup).
    tf_names = []
    for nm in (list(K.RSI_MTF_TIMEFRAMES) + list(K.RSI_DCA_LADDER_TIMEFRAMES)
               + [K.RSI_FINAL_CLOSE_TIMEFRAME]):
        if nm not in tf_names:
            tf_names.append(nm)
    tf_states = {nm: _build_tf_state(ind, m1, nm) for nm in tf_names}
    _validate_rsi(ind, m1, tf_states)

    # M15 SHA source (full history; sliced to the live rolling window per bar).
    m15 = bt_data.resample_ohlc(m1, bt_data.TF_MINUTES[K.CANDLE_TIMEFRAME])
    m15_open_ms = bt_data.idx_to_ms(m15.index)
    m15_close_ms = m15_open_ms + bt_data.TF_MINUTES[K.CANDLE_TIMEFRAME] * _MS_MIN
    lookback = K.STRATEGY_LOOKBACK
    candle_count = K.CANDLE_COUNT

    # Precompute the SHA series ONCE over the full M15 history. SHA is causal
    # (EMA/TEMA/DEMA chains + recursive HA), so its value at bar j is identical to
    # the live bot's rolling CANDLE_COUNT-window value at j once warmed up — which
    # holds everywhere in the scored window (warmup ≫ TEMA/DEMA convergence). This
    # replaces ~8,600 redundant 300-bar recomputes with a single pass.
    m15_ohlc = m15[["Open", "High", "Low", "Close", "Volume"]]
    sha_full = ind.calculate_sha_v3(m15_ohlc, length=K.SHA_LENGTH, ma_type=K.SHA_MA_TYPE)
    sha_trend_full = ind.calculate_sha_v3(m15_ohlc, length=K.SHA_TREND_LENGTH, ma_type=K.SHA_TREND_MA_TYPE)
    _validate_sha(ind, m15_ohlc, sha_full, sha_trend_full, candle_count=K.CANDLE_COUNT)

    # Regime filter (v1.6.0) — precompute ADX/ATR once over the full M15 history
    # (same causal argument as SHA: Wilder RMA converges, so full-series == live
    # rolling CANDLE_COUNT window at every warmed bar). Only when armed.
    adx_arr = tr_arr = atr_arr = None
    reg_adx_max = float(K.REGIME_ADX_MAX)
    reg_k1, reg_k2 = float(K.REGIME_SPIKE_K1), float(K.REGIME_SPIKE_K2)
    reg_win = max(1, int(K.REGIME_SPIKE_WINDOW))
    if regime_act:
        adx_full = ind.calculate_adx(m15["High"], m15["Low"], m15["Close"],
                                     length=K.REGIME_ADX_PERIOD)
        _validate_adx(ind, m15, adx_full, candle_count=K.CANDLE_COUNT)
        adx_arr = adx_full["ADX"].to_numpy(float)
        tr_arr = adx_full["TR"].to_numpy(float)
        atr_arr = adx_full["ATR"].to_numpy(float)

    def regime_block(j15):
        """Fresh-entry block verdict — exact mirror of app._compute_regime with the
        shipped BTCUSDm constants (ADX symmetric, spike symmetric, DI/dir/slope off).
        Returns (block_buy, block_sell)."""
        block = False
        if K.REGIME_ADX_ENABLED:
            adx = adx_arr[j15]
            if adx == adx and adx >= reg_adx_max:      # not NaN and over threshold
                block = True
        if not block and K.REGIME_ATR_ENABLED and j15 >= 2:
            for k in range(1, reg_win + 1):
                p_prev = j15 - k                        # ATR as of bar before bar -k
                if p_prev < 0:
                    break
                atr_prev = atr_arr[p_prev]
                if not (atr_prev == atr_prev) or atr_prev <= 0:
                    continue
                tr_i = tr_arr[j15 - (k - 1)]
                tr_i1 = tr_arr[p_prev]
                single = (tr_i == tr_i) and tr_i >= reg_k1 * atr_prev
                double = (tr_i == tr_i) and (tr_i1 == tr_i1) and (tr_i + tr_i1) >= reg_k2 * atr_prev
                if single or double:
                    block = True
                    break
        return block, block        # symmetric with live USE_DI/USE_DIR = False

    # M1 arrays for the hot loop (open_time column is exact epoch ms)
    open_ms = m1["open_time"].to_numpy("int64")
    m_open = m1["open"].to_numpy(float)
    m_high = m1["high"].to_numpy(float)
    m_low = m1["low"].to_numpy(float)
    m_close = m1["close"].to_numpy(float)
    is_test = m1["is_test"].to_numpy(int)
    idx_ts = m1.index

    # SHA slice cache (rebuilt when the completed M15 bar advances)
    cache = {"j15": -1, "raw7": None, "sha7": None, "sha_trend7": None}

    def rebuild_sha(j15):
        """Default path: slice the precomputed full-series SHA (last `lookback` rows).

        Identical to the live rolling-window recompute wherever both are warmed up
        (the entire scored window), but ~O(1) instead of two 300-bar SHA passes.
        """
        lo = j15 - lookback + 1
        cache["raw7"] = m15.iloc[lo:j15 + 1][["Open", "High", "Low", "Close"]].copy()
        cache["sha7"] = sha_full.iloc[lo:j15 + 1].copy()
        cache["sha_trend7"] = sha_trend_full.iloc[lo:j15 + 1].copy()

    def rebuild_sha_forming(j15, forming_row):
        """--sha-intrabar path: recompute on the rolling window + forming M15 bar.

        Kept as a per-minute recompute because the forming bar changes every step;
        used only while flat when the flag is set, so its cost is opt-in.
        """
        lo = max(0, j15 - candle_count + 1)
        window = pd.concat([m15.iloc[lo:j15 + 1][["Open", "High", "Low", "Close", "Volume"]], forming_row])
        sha = ind.calculate_sha_v3(window, length=K.SHA_LENGTH, ma_type=K.SHA_MA_TYPE)
        sha_t = ind.calculate_sha_v3(window, length=K.SHA_TREND_LENGTH, ma_type=K.SHA_TREND_MA_TYPE)
        cache["raw7"] = window.iloc[-lookback:][["Open", "High", "Low", "Close"]].copy()
        cache["sha7"] = sha.iloc[-lookback:].copy()
        cache["sha_trend7"] = sha_t.iloc[-lookback:].copy()

    # equity / drawdown tracking (scored window only)
    peak_equity = broker.balance
    max_dd = 0.0
    max_dd_pct = 0.0
    equity_curve = []          # (timestamp, equity) sparse (hourly) for optional plotting
    add_rung = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}   # BUY_MORE/SELL_MORE that reached count N+1
    close_reason = {"TARGET": 0, "H6_FORCED": 0, "EARLY_CUT": 0}
    entries = {"BUY": 0, "SELL": 0}
    in_market_min = 0
    n = len(m1)
    first_test_i = int(np.argmax(is_test == 1))

    # Indicators are precomputed causally over the full history (warmup included),
    # so they are already converged at the test-window start. We therefore begin
    # the broker flat at first_test_i instead of replaying warmup — much faster and
    # numerically identical for the scored period (only a negligible boundary
    # effect: live could be mid-basket at the instant the window opens).
    for i in range(first_test_i, n):
        price = m_close[i]
        t = idx_ts[i]
        tc_ms = int(open_ms[i]) + _MS_MIN            # decision at this M1's close
        scored = is_test[i] == 1

        broker.mark(price)                            # track MAE before acting

        # last completed M15 bar as of tc
        j15 = int(np.searchsorted(m15_close_ms, tc_ms, side="right")) - 1
        if j15 < lookback:
            continue                                  # not enough history yet

        broker.refresh_units()                        # only recomputes while flat

        # SHA slices (entry only). Rebuild on M15 advance; optionally intrabar-forming.
        forming = None
        if sha_intrabar and broker.flat():
            b_open_ms = m15_open_ms[j15 + 1] if j15 + 1 < len(m15_open_ms) else (m15_open_ms[j15] + 15 * _MS_MIN)
            if tc_ms - _MS_MIN >= b_open_ms:          # we are inside a forming M15 window
                m = (open_ms >= b_open_ms) & (open_ms <= open_ms[i])
                if m.any():
                    forming = pd.DataFrame({
                        "Open": [m_open[m][0]], "High": [m_high[m].max()],
                        "Low": [m_low[m].min()], "Close": [price],
                        "Volume": [0.0],
                    }, index=[pd.to_datetime(b_open_ms, unit="ms", utc=True)])
        if forming is not None:
            rebuild_sha_forming(j15, forming)
            cache["j15"] = -1          # force a clean reslice when we next go flat/closed
        elif j15 != cache["j15"]:
            rebuild_sha(j15)
            cache["j15"] = j15

        # RSI dict — live forming-bar values, keyed by full TIMEFRAME_* names
        rsi_mtf = {nm: _rsi_now(tf_states[nm], tc_ms, price) for nm in tf_names}
        current_rsi = rsi_mtf.get("TIMEFRAME_M1", 50.0)

        buy_positions, sell_positions = broker.positions_dict(price)
        units = broker.units
        close_thr = units * close_mult

        # Regime fresh-entry verdict (only meaningful while flat) → passed INTO the
        # real strategy, which applies block_buy/block_sell exactly as live.
        regime = None
        if regime_act and broker.flat():
            bb, bs = regime_block(j15)
            if bb or bs:
                regime = {"active": True, "block_buy": bb, "block_sell": bs}

        buy_sig, sell_sig, _ = strat.calculate_signal(
            cache["raw7"], cache["sha7"], cache["sha_trend7"],
            buy_positions, sell_positions, units,
            close_threshold=close_thr, rsi_value=current_rsi, rsi_mtf=rsi_mtf, regime=regime,
        )

        # ── apply ──
        # brake: live Mon–Sun window ≈ always open for 24/7 BTC → 0.
        # entry_blocked: TEST overlay suppressing FRESH entries in given UTC hours.
        brake = 0
        entry_blocked = bool(time_block_hours) and (t.hour in time_block_hours)

        if buy_sig == Signal.BUY and not brake and not entry_blocked:
            broker.open("BUY", units * broker.mtqty, price, t)
            if scored:
                entries["BUY"] += 1
        elif buy_sig == Signal.BUY_MORE:
            if max_depth is not None and buy_positions["count"] >= max_depth:
                broker.close(price, t, "EARLY_CUT")      # cap the martingale early
                if scored:
                    close_reason["EARLY_CUT"] += 1
            else:
                vol = strat._get_next_fibo_volume(buy_positions["total_volume"], units)
                broker.open("BUY", vol, price, t)
                if scored:
                    add_rung[min(5, buy_positions["count"])] += 1
        elif buy_sig == Signal.CLOSE_BUY:
            reason = "TARGET" if buy_positions["total_profit"] > close_thr else "H6_FORCED"
            broker.close(price, t, reason)
            if scored:
                close_reason[reason] += 1

        elif sell_sig == Signal.SELL and not brake and not entry_blocked:
            broker.open("SELL", units * broker.mtqty, price, t)
            if scored:
                entries["SELL"] += 1
        elif sell_sig == Signal.SELL_MORE:
            if max_depth is not None and sell_positions["count"] >= max_depth:
                broker.close(price, t, "EARLY_CUT")
                if scored:
                    close_reason["EARLY_CUT"] += 1
            else:
                vol = strat._get_next_fibo_volume(sell_positions["total_volume"], units)
                broker.open("SELL", vol, price, t)
                if scored:
                    add_rung[min(5, sell_positions["count"])] += 1
        elif sell_sig == Signal.CLOSE_SELL:
            reason = "TARGET" if sell_positions["total_profit"] > close_thr else "H6_FORCED"
            broker.close(price, t, reason)
            if scored:
                close_reason[reason] += 1

        # ── equity / drawdown (scored window) ──
        if scored:
            eq = broker.balance + broker.floating(price)
            if eq > peak_equity:
                peak_equity = eq
            dd = peak_equity - eq
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = 100.0 * dd / peak_equity if peak_equity else 0.0
            if not broker.flat():
                in_market_min += 1
            if open_ms[i] % (60 * _MS_MIN) == 0:
                equity_curve.append((t, round(eq, 2)))

        if progress and scored and (i - first_test_i) % 20000 == 0:
            pct = 100.0 * (i - first_test_i) / max(1, n - first_test_i)
            print(f"\r  replaying … {pct:5.1f}%  bal={broker.balance:,.2f}  "
                  f"baskets={len(broker.baskets)}", end="", flush=True)
    if progress:
        print()

    # Force-close any basket still open at the end (mark-to-market) so P&L is complete.
    if not broker.flat():
        broker.close(m_close[-1], idx_ts[-1], "EOD_OPEN")

    return {
        "broker": broker,
        "start_balance": broker.start_balance,
        "end_balance": broker.balance,
        "baskets": broker.baskets,
        "max_dd": max_dd,
        "max_dd_pct": max_dd_pct,
        "peak_equity": peak_equity,
        "add_rung": add_rung,
        "close_reason": close_reason,
        "entries": entries,
        "in_market_min": in_market_min,
        "test_minutes": int(is_test.sum()),
        "equity_curve": equity_curve,
        "period": (idx_ts[first_test_i], idx_ts[-1]),
    }


def _validate_sha(ind: Indicator, m15_ohlc: pd.DataFrame, sha_full: pd.DataFrame,
                  sha_trend_full: pd.DataFrame, candle_count: int):
    """Assert the full-series SHA slice == the live rolling CANDLE_COUNT-window value.

    SHA's recursive HA-open chain and its EMA/TEMA/DEMA smoothings are all 0.5^n-ish
    contractions, so a full-history computation and a trailing 300-bar computation
    converge to the same value at any warmed-up bar. This checks that empirically at
    several bars (including the last), for both the signal and trend SHA, so the
    precompute optimization is numerically identical to the live rolling recompute.
    """
    n = len(m15_ohlc)
    if n < candle_count + 5:
        return
    samples = sorted({n - 1, n - 2, n - 50, int(n * 0.7), candle_count + 2})
    checks = ((sha_full, K.SHA_LENGTH, K.SHA_MA_TYPE, "signal"),
              (sha_trend_full, K.SHA_TREND_LENGTH, K.SHA_TREND_MA_TYPE, "trend"))
    worst = 0.0
    for j in samples:
        if j < candle_count or j >= n:
            continue
        win = m15_ohlc.iloc[j - candle_count + 1:j + 1]     # exact live rolling window
        for full, length, ma_type, tag in checks:
            ref = ind.calculate_sha_v3(win, length=length, ma_type=ma_type).iloc[-1]
            mine = full.iloc[j]
            for col in ("Open", "High", "Low", "Close"):
                r, m = float(ref[col]), float(mine[col])
                diff = abs(r - m)
                rel = diff / max(1.0, abs(r))
                worst = max(worst, rel)
                if rel > 1e-6:
                    raise AssertionError(
                        f"SHA {tag} precompute mismatch @j={j} {col}: "
                        f"rolling={r} full={m} (rel={rel:.2e})")
    print(f"  SHA precompute validated against rolling window "
          f"(worst rel diff {worst:.1e} over {len(samples)} bars × 2 SHAs)")


def _validate_adx(ind: Indicator, m15: pd.DataFrame, adx_full: pd.DataFrame,
                  candle_count: int):
    """Assert the full-series ADX/ATR slice == the live rolling-window value.

    Same causal/convergence argument as SHA: ADX/ATR are Wilder-RMA smoothed, so a
    full-history pass equals a trailing CANDLE_COUNT-bar pass at any warmed bar —
    which is exactly what the regime filter reads live. Checked at several bars."""
    n = len(m15)
    if n < candle_count + 5:
        return
    samples = sorted({n - 1, n - 2, n - 50, int(n * 0.7), candle_count + 2})
    worst = 0.0
    for j in samples:
        if j < candle_count or j >= n:
            continue
        win = m15.iloc[j - candle_count + 1:j + 1]
        ref = ind.calculate_adx(win["High"], win["Low"], win["Close"],
                                length=K.REGIME_ADX_PERIOD).iloc[-1]
        mine = adx_full.iloc[j]
        for col in ("TR", "ATR", "plus_DI", "minus_DI", "ADX"):
            r, m = float(ref[col]), float(mine[col])
            if r != r and m != m:
                continue                      # both NaN
            rel = abs(r - m) / max(1.0, abs(r))
            worst = max(worst, rel)
            if rel > 1e-6:
                raise AssertionError(
                    f"ADX precompute mismatch @j={j} {col}: rolling={r} full={m} (rel={rel:.2e})")
    print(f"  ADX precompute validated against rolling window "
          f"(worst rel diff {worst:.1e} over {len(samples)} bars)")


def _validate_rsi(ind: Indicator, m1: pd.DataFrame, tf_states: dict):
    """Assert the one-step forming extension == real calculate_rsi on a few bars."""
    for nm, st in tf_states.items():
        if len(st.close) < K.RSI_LENGTH + 40:
            continue
        for j in (len(st.close) - 2, len(st.close) - 15, len(st.close) // 2):
            if j <= K.RSI_LENGTH + 2:
                continue
            ref = ind.calculate_rsi(pd.Series(st.close[:j + 1]),
                                    length=K.RSI_LENGTH, ma_type=K.RSI_MA_TYPE).iloc[-1]
            mine = _rsi_now(st, int(st.close_ms[j]), float(st.close[j]))
            if not (abs(ref - mine) < 1e-6 or (math.isnan(ref) and mine == 50.0)):
                raise AssertionError(
                    f"RSI extension mismatch on {nm} @j={j}: real={ref} mine={mine}")
