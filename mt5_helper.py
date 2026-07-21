from typing import Dict, List, Optional
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
from constants import RISK_REWARD_RATIO, ALLOW_SYNTHETIC_TICK_BAR



class MT5PositionHelper:
    """Helper class for MT5 position-related operations"""
    
    # MT5 Transaction Types
    MT5_BUY = 0
    MT5_SELL = 1
    
    def __init__(self, mt5_instance):
        """
        Initialize helper with MT5 instance from app
        
        Args:
            mt5_instance: The MetaTrader5 module instance from app.py
        """
        self.mt5 = mt5_instance
        self.risk_reward_ratio = RISK_REWARD_RATIO
        
        # Store MT5 constants for building per-call request dicts
        self._order_time_gtc = self.mt5.ORDER_TIME_GTC
        self._order_filling_ioc = self.mt5.ORDER_FILLING_IOC
        self._trade_action_deal = self.mt5.TRADE_ACTION_DEAL
    
    def get_buy_positions(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed position information for BUY positions
        
        Args:
            symbol: Trading symbol (e.g., 'GBPUSD', 'XAUUSD')
        
        Returns:
            Dict with keys:
                - type: Position type (0 for BUY)
                - count: Number of BUY positions
                - total_profit: Sum of all BUY position profits
                - total_volume: Sum of all BUY position volumes
                - first_profit: Profit of first BUY position
                - first_volume: Volume of first BUY position
                - last_profit: Profit of last BUY position
                - last_volume: Volume of last BUY position
            Returns None if no positions found
        """
        positions = self.mt5.positions_get(symbol=symbol)
        
        if positions is None or len(positions) == 0:
            return None
        
        # Filter BUY positions
        buy_positions = [pos for pos in positions if pos.type == self.MT5_BUY]
        
        if not buy_positions:
            return None
        
        # Calculate aggregates
        total_profit = sum(pos.profit for pos in buy_positions)
        total_volume = sum(pos.volume for pos in buy_positions)
        
        # Get first and last position details
        first_pos = buy_positions[0]
        last_pos = buy_positions[-1]
        
        return {
            'type': self.MT5_BUY,
            'count': len(buy_positions),
            'total_profit': round(total_profit, 2),
            'total_volume': round(total_volume, 2),
            'first_profit': round(first_pos.profit, 2),
            'first_volume': round(first_pos.volume, 2),
            'last_profit': round(last_pos.profit, 2),
            'last_volume': round(last_pos.volume, 2)
        }
    
    def get_sell_positions(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed position information for SELL positions
        
        Args:
            symbol: Trading symbol (e.g., 'GBPUSD', 'XAUUSD')
        
        Returns:
            Dict with keys:
                - type: Position type (1 for SELL)
                - count: Number of SELL positions
                - total_profit: Sum of all SELL position profits
                - total_volume: Sum of all SELL position volumes
                - first_profit: Profit of first SELL position
                - first_volume: Volume of first SELL position
                - last_profit: Profit of last SELL position
                - last_volume: Volume of last SELL position
            Returns None if no positions found
        """
        positions = self.mt5.positions_get(symbol=symbol)
        
        if positions is None or len(positions) == 0:
            return None
        
        # Filter SELL positions
        sell_positions = [pos for pos in positions if pos.type == self.MT5_SELL]
        
        if not sell_positions:
            return None
        
        # Calculate aggregates
        total_profit = sum(pos.profit for pos in sell_positions)
        total_volume = sum(pos.volume for pos in sell_positions)
        
        # Get first and last position details
        first_pos = sell_positions[0]
        last_pos = sell_positions[-1]
        
        return {
            'type': self.MT5_SELL,
            'count': len(sell_positions),
            'total_profit': round(total_profit, 2),
            'total_volume': round(total_volume, 2),
            'first_profit': round(first_pos.profit, 2),
            'first_volume': round(first_pos.volume, 2),
            'last_profit': round(last_pos.profit, 2),
            'last_volume': round(last_pos.volume, 2)
        }
    
    def get_account_info(self) -> Optional[Dict]:
        """
        Get account information (balance, equity, margin, etc.)
        
        Returns:
            Dict with keys:
                - balance: Account balance
                - equity: Account equity
                - margin: Used margin
                - margin_free: Free margin
                - margin_level: Margin level percentage
                - profit: Current floating profit
                - drawdown: Drawdown percentage
            Returns None if failed
        """
        account = self.mt5.account_info()
        if account is None:
            return None
        
        # Calculate drawdown percentage
        if account.balance > 0:
            drawdown_pct = ((account.balance - account.equity) / account.balance) * 100
        else:
            drawdown_pct = 0
        
        return {
            'balance': round(account.balance, 2),
            'equity': round(account.equity, 2),
            'margin': round(account.margin, 2),
            'margin_free': round(account.margin_free, 2),
            'margin_level': round(account.margin_level, 2) if account.margin_level else 0,
            'profit': round(account.profit, 2),
            'drawdown': round(drawdown_pct, 2),
        }

    def _ensure_symbol_ready(self, symbol: str) -> bool:
        """Ensure symbol is visible/subscribed in Market Watch before reads."""
        info = self.mt5.symbol_info(symbol)
        if info is None:
            return False
        if not info.visible and not self.mt5.symbol_select(symbol, True):
            return False
        return True

    def _warm_symbol_feed(self, symbol: str):
        """Touch tick/rates endpoints to force terminal history sync for symbol."""
        try:
            self.mt5.symbol_info_tick(symbol)
            copy_ticks_all = getattr(self.mt5, 'COPY_TICKS_ALL', None)
            if copy_ticks_all is not None:
                from_time = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
                self.mt5.copy_ticks_from(symbol, from_time, 200, copy_ticks_all)
            # Also poke the bar cache — requesting a fresh rate nudges the
            # terminal to sync its internal history for this symbol.
            self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_M1, 0, 1)
        except Exception:
            pass

    def _rebuild_m1_from_ticks(self, symbol: str, rates_frame: pd.DataFrame, count: int):
        """Rebuild/extend M1 bars from ticks when MT5 bar feed is stale."""
        copy_ticks_all = getattr(self.mt5, 'COPY_TICKS_ALL', None)
        if copy_ticks_all is None:
            return rates_frame, False

        try:
            # Start fetching ticks from the last known bar time (not a fixed
            # lookback).  This avoids wasting the tick budget on data we
            # already have and ensures we reach the current minute even for
            # very liquid instruments like XAUUSD.
            last_bar_ts = int(rates_frame['time'].iloc[-1])
            from_time = datetime.fromtimestamp(last_bar_ts, tz=timezone.utc)
            ticks = self.mt5.copy_ticks_from(symbol, from_time, 500_000, copy_ticks_all)
            if ticks is None or len(ticks) == 0:
                return rates_frame, False

            tdf = pd.DataFrame(ticks)
            if tdf.empty or 'time' not in tdf.columns:
                return rates_frame, False

            tdf['time'] = pd.to_datetime(tdf['time'], unit='s', utc=True).dt.floor('min')

            if 'last' in tdf.columns and (tdf['last'] != 0).any():
                tdf['price'] = tdf['last']
            elif 'bid' in tdf.columns and (tdf['bid'] != 0).any():
                tdf['price'] = tdf['bid']
            elif 'ask' in tdf.columns and (tdf['ask'] != 0).any():
                tdf['price'] = tdf['ask']
            else:
                return rates_frame, False

            bars = tdf.groupby('time')['price'].agg(['first', 'max', 'min', 'last', 'count']).reset_index()
            if bars.empty:
                return rates_frame, False

            bars.rename(columns={
                'first': 'open',
                'max': 'high',
                'min': 'low',
                'last': 'close',
                'count': 'tick_volume',
            }, inplace=True)

            base = rates_frame.copy()
            base['time'] = pd.to_datetime(base['time'], unit='s', utc=True).dt.floor('min')
            last_base_time = base['time'].iloc[-1]
            new_bars = bars[bars['time'] > last_base_time].copy()
            if new_bars.empty:
                return rates_frame, False

            spread_val = int(base['spread'].iloc[-1]) if 'spread' in base.columns else 0
            new_bars['spread'] = spread_val
            new_bars['real_volume'] = 0

            keep_cols = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            merged = pd.concat([base[keep_cols], new_bars[keep_cols]], ignore_index=True)
            merged = merged.tail(count).reset_index(drop=True)
            merged['time'] = (merged['time'].astype('int64') // 10**9).astype('int64')
            return merged, True
        except Exception:
            return rates_frame, False
    
    def get_rates(self, symbol: str, timeframe: int, count: int):
        """
        Fetch historical rates/candles for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'GBPUSD', 'XAUUSD')
            timeframe: MT5 timeframe constant (e.g., mt5.TIMEFRAME_M1, mt5.TIMEFRAME_H1)
            count: Number of candles to fetch
        
        Returns:
            DataFrame with OHLCV data or None if failed
            Each row contains: time, open, high, low, close, tick_volume, spread, real_volume
        """
        if not self._ensure_symbol_ready(symbol):
            return None

        rates = None
        rates_source = 'copy_rates_from_pos'
        for attempt in range(3):
            self._warm_symbol_feed(symbol)
            rates = self.mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is not None and len(rates) > 0:
                break
            if attempt < 2:
                time.sleep(0.2)

        if rates is None or len(rates) == 0:
            return None

        # Compare with time-based fetch and keep the freshest stream.
        # Some brokers/symbols return stale bars on copy_rates_from_pos while
        # copy_rates_from(symbol, now, ...) is fresh.
        # Use tick-derived broker server time instead of local UTC to avoid
        # clock-skew issues that cause the latest bar to be missed.
        try:
            _tick = self.mt5.symbol_info_tick(symbol)
            if _tick is not None and getattr(_tick, 'time', 0) > 0:
                now_ts = datetime.fromtimestamp(_tick.time, tz=timezone.utc)
            else:
                now_ts = datetime.now(tz=timezone.utc)
            alt_rates = self.mt5.copy_rates_from(symbol, timeframe, now_ts, count)
            if alt_rates is not None and len(alt_rates) > 0:
                pos_last = datetime.fromtimestamp(rates[-1][0], tz=timezone.utc)
                alt_last = datetime.fromtimestamp(alt_rates[-1][0], tz=timezone.utc)
                if alt_last >= pos_last:
                    rates = alt_rates
                    rates_source = 'copy_rates_from'
        except Exception:
            pass

        rates_frame = pd.DataFrame(rates)
        synthetic_appended = False
        tick_rebuilt = False

        # If bar stream lags but tick stream is live, add a provisional latest M1 bar
        # so downstream SHA can continue updating for this symbol.
        if ALLOW_SYNTHETIC_TICK_BAR:
            try:
                tick = self.mt5.symbol_info_tick(symbol)
                if tick is not None and getattr(tick, 'time', 0):
                    tick_time = datetime.fromtimestamp(tick.time, tz=timezone.utc).replace(second=0, microsecond=0)
                    last_bar_time = datetime.fromtimestamp(int(rates_frame['time'].iloc[-1]), tz=timezone.utc).replace(second=0, microsecond=0)

                    if tick_time > last_bar_time:
                        prev_close = float(rates_frame['close'].iloc[-1])
                        tick_price = float(tick.bid if getattr(tick, 'bid', 0) else getattr(tick, 'ask', prev_close))
                        spread_val = int(rates_frame['spread'].iloc[-1]) if 'spread' in rates_frame.columns else 0

                        synthetic = {
                            'time': int(tick_time.timestamp()),
                            'open': prev_close,
                            'high': max(prev_close, tick_price),
                            'low': min(prev_close, tick_price),
                            'close': tick_price,
                            'tick_volume': 0,
                            'spread': spread_val,
                            'real_volume': 0,
                        }

                        rates_frame = pd.concat([rates_frame, pd.DataFrame([synthetic])], ignore_index=True)
                        if len(rates_frame) > count:
                            rates_frame = rates_frame.tail(count).reset_index(drop=True)
                        synthetic_appended = True
            except Exception:
                pass

        # Last-resort fallback for stalled M1 stream: rebuild new minute bars from ticks
        try:
            tick = self.mt5.symbol_info_tick(symbol)
            tick_time = datetime.fromtimestamp(tick.time, tz=timezone.utc) if tick is not None and getattr(tick, 'time', 0) else None
            last_bar_time = datetime.fromtimestamp(int(rates_frame['time'].iloc[-1]), tz=timezone.utc)
            if timeframe == self.mt5.TIMEFRAME_M1 and tick_time is not None:
                stale_minutes = (tick_time - last_bar_time).total_seconds() / 60.0
                if stale_minutes >= 1.5:
                    rebuilt_frame, rebuilt = self._rebuild_m1_from_ticks(symbol, rates_frame, count)
                    if rebuilt:
                        rates_frame = rebuilt_frame
                        tick_rebuilt = True
                        rates_source = 'ticks_rebuild_m1'
        except Exception:
            pass

        rates_frame["time"] = pd.to_datetime(rates_frame["time"], unit="s", utc=True)
        rates_frame.attrs['rates_source'] = rates_source
        rates_frame.attrs['synthetic_appended'] = synthetic_appended
        rates_frame.attrs['tick_rebuilt'] = tick_rebuilt
        return rates_frame
    
    def get_market_status(self, symbol: str, timeframe: int, lookback_minutes: int = 15) -> Dict:
        """
        Detect whether the market is open or closed for a symbol.
        Compares the latest candle time against current time using a lookback window.
        
        Args:
            symbol: Trading symbol (e.g., 'GBPUSD', 'XAUUSD')
            timeframe: MT5 timeframe constant used for fetching rates
            lookback_minutes: Max minutes since last candle to consider market open (default 15)
        
        Returns:
            Dict with keys:
                - is_open: bool, True if market is open
                - status: str, 'OPEN' or 'CLOSED'
                - last_candle_time: str, ISO format of the last candle time
                - minutes_since_last: float, minutes elapsed since last candle
                - lookback_minutes: int, the threshold used
        """
        try:
            if not self._ensure_symbol_ready(symbol):
                return {
                    'is_open': False,
                    'status': 'CLOSED',
                    'last_candle_time': None,
                    'minutes_since_last': None,
                    'lookback_minutes': lookback_minutes,
                    'message': f'Symbol not available/visible: {symbol}',
                }

            rates = None
            for attempt in range(3):
                self._warm_symbol_feed(symbol)
                rates = self.mt5.copy_rates_from_pos(symbol, timeframe, 0, 3)
                if rates is not None and len(rates) > 0:
                    break
                if attempt < 2:
                    time.sleep(0.2)

            if rates is None or len(rates) == 0:
                return {
                    'is_open': False,
                    'status': 'CLOSED',
                    'last_candle_time': None,
                    'minutes_since_last': None,
                    'lookback_minutes': lookback_minutes,
                    'message': f'No rate data available for {symbol}',
                }
            
            last_candle_time = datetime.fromtimestamp(rates[-1][0], tz=timezone.utc)
            tick = self.mt5.symbol_info_tick(symbol)
            tick_time = None
            if tick is not None and getattr(tick, 'time', 0):
                tick_time = datetime.fromtimestamp(tick.time, tz=timezone.utc)

            now = datetime.now(tz=timezone.utc)
            minutes_since_candle = (now - last_candle_time).total_seconds() / 60.0
            minutes_since_tick = (now - tick_time).total_seconds() / 60.0 if tick_time else None
            activity_ref = max(last_candle_time, tick_time) if tick_time else last_candle_time
            minutes_since_activity = (now - activity_ref).total_seconds() / 60.0
            is_open = minutes_since_activity <= lookback_minutes
            
            return {
                'is_open': is_open,
                'status': 'OPEN' if is_open else 'CLOSED',
                'last_candle_time': last_candle_time.isoformat(),
                'last_tick_time': tick_time.isoformat() if tick_time else None,
                'minutes_since_last': round(minutes_since_activity, 1),
                'minutes_since_last_candle': round(minutes_since_candle, 1),
                'minutes_since_last_tick': round(minutes_since_tick, 1) if minutes_since_tick is not None else None,
                'lookback_minutes': lookback_minutes,
                'message': f'Market {"open" if is_open else "closed"} — last activity {round(minutes_since_activity, 1)}m ago',
            }
        except Exception as e:
            return {
                'is_open': False,
                'status': 'CLOSED',
                'last_candle_time': None,
                'minutes_since_last': None,
                'lookback_minutes': lookback_minutes,
                'message': f'Error checking market status: {str(e)}',
            }
    
    def _build_request(self, symbol: str, qty: float, order_type, sl: float, tp: float) -> dict:
        """
        Build a fresh, thread-safe request dict for an order.
        
        Args:
            symbol: Trading symbol
            qty: Order volume/quantity
            order_type: MT5 order type constant (ORDER_TYPE_BUY / ORDER_TYPE_SELL)
            sl: Stop loss (0 for auto-calculation)
            tp: Take profit (0 for auto-calculation)
        
        Returns:
            dict: Ready-to-send request dictionary
        """
        ask = self.mt5.symbol_info_tick(symbol).ask
        is_buy = (order_type == self.mt5.ORDER_TYPE_BUY)
        
        if sl == 0:
            computed_sl = ask - (ask * self.risk_reward_ratio[0]) if is_buy \
                          else ask + (ask * self.risk_reward_ratio[0])
        else:
            computed_sl = sl
        
        if tp == 0:
            computed_tp = ask + (ask * self.risk_reward_ratio[1]) if is_buy \
                          else ask - (ask * self.risk_reward_ratio[1])
        else:
            computed_tp = tp
        
        return {
            "action": self._trade_action_deal,
            "symbol": symbol,
            "volume": qty,
            "type": order_type,
            "price": ask,
            "type_time": self._order_time_gtc,
            "type_filling": self._order_filling_ioc,
            "sl": computed_sl,
            "tp": computed_tp,
        }

    def buy(self, symbol: str, qty: float, sl: float = 0, tp: float = 0):
        """
        Place a BUY order (thread-safe — builds a local request dict)
        
        Args:
            symbol: Trading symbol
            qty: Order volume/quantity
            sl: Stop loss (0 for auto-calculation based on risk_reward_ratio)
            tp: Take profit (0 for auto-calculation based on risk_reward_ratio)
        
        Returns:
            Order result from MT5
        """
        request = self._build_request(symbol, qty, self.mt5.ORDER_TYPE_BUY, sl, tp)
        order_status = self.mt5.order_send(request)
        time.sleep(0.1)
        return order_status
    
    def sell(self, symbol: str, qty: float, sl: float = 0, tp: float = 0):
        """
        Place a SELL order (thread-safe — builds a local request dict)
        
        Args:
            symbol: Trading symbol
            qty: Order volume/quantity
            sl: Stop loss (0 for auto-calculation based on risk_reward_ratio)
            tp: Take profit (0 for auto-calculation based on risk_reward_ratio)
        
        Returns:
            Order result from MT5
        """
        request = self._build_request(symbol, qty, self.mt5.ORDER_TYPE_SELL, sl, tp)
        order_status = self.mt5.order_send(request)
        time.sleep(0.1)
        return order_status
    
    def close_by_type(self, symbol: str, pos_type: int):
        """
        Close all positions of a specific type (BUY or SELL)
        
        Args:
            symbol: Trading symbol
            pos_type: Position type (0 = BUY, 1 = SELL)
        
        Returns:
            dict: Detailed information about the close operation with keys:
                - success: bool, overall success
                - message: str, status message
                - total_positions: int, total positions for symbol
                - filtered_count: int, positions of the specified type
                - closed_count: int, successfully closed positions
                - failed_count: int, failed closures
                - closed_tickets: list, ticket IDs that were closed
                - errors: list, error messages if any
        """
        result = {
            'success': False,
            'message': '',
            'total_positions': 0,
            'filtered_count': 0,
            'closed_count': 0,
            'failed_count': 0,
            'closed_tickets': [],
            'errors': [],
        }
        
        positions = self.mt5.positions_get(symbol=symbol)
        if positions is None:
            result['message'] = f"No positions found for {symbol}"
            result['success'] = True  # No positions is not an error
            return result
        
        result['total_positions'] = len(positions)
        
        # Filter positions by type (0 = BUY, 1 = SELL)
        filtered_positions = [pos for pos in positions if pos.type == pos_type]
        result['filtered_count'] = len(filtered_positions)
        
        if not filtered_positions:
            pos_type_name = 'BUY' if pos_type == 0 else 'SELL'
            result['message'] = f"No {pos_type_name} positions found for {symbol}"
            result['success'] = True
            return result
        
        for pos in filtered_positions:
            tick = self.mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                result['errors'].append(f"Failed to get tick data for position {pos.ticket}")
                result['failed_count'] += 1
                continue
            
            # Invert type to close (0 -> SELL, 1 -> BUY)
            opposite_type = 1 if pos.type == 0 else 0
            # Price: close BUY at bid, close SELL at ask
            price = tick.bid if pos.type == 0 else tick.ask
            
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": opposite_type,
                "price": price,
                "deviation": 20,
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }
            
            order_result = self.mt5.order_send(request)
            
            if order_result is None:
                result['errors'].append(f"order_send failed for position {pos.ticket}, no response")
                result['failed_count'] += 1
            elif order_result.retcode != self.mt5.TRADE_RETCODE_DONE:
                result['errors'].append(f"Failed to close position {pos.ticket}, retcode={order_result.retcode}")
                result['failed_count'] += 1
            else:
                result['closed_tickets'].append(pos.ticket)
                result['closed_count'] += 1
        
        result['success'] = result['failed_count'] == 0
        if result['success']:
            result['message'] = f"Successfully closed {result['closed_count']} positions"
        else:
            result['message'] = f"Closed {result['closed_count']}/{result['filtered_count']} positions, {result['failed_count']} failed"
        
        return result

    def get_deal_history(self, from_date: datetime, to_date: datetime, symbol: str = None) -> List[Dict]:
        """
        Get closed deal history from MT5 for a date range.
        Only returns deals with entry type DEAL_ENTRY_OUT (closed trades with realized P/L).
        
        Args:
            from_date: Start datetime
            to_date: End datetime
            symbol: Optional symbol filter. If None, returns all symbols.
        
        Returns:
            List of dicts, each containing:
                - ticket: Deal ticket number
                - order: Order ticket
                - symbol: Trading symbol
                - type: 'BUY' or 'SELL'
                - volume: Deal volume
                - price: Deal price
                - profit: Realized profit/loss
                - commission: Commission charged
                - swap: Swap charged
                - fee: Fee charged
                - time: Deal execution time (ISO format string)
                - comment: Deal comment
        """
        deals = self.mt5.history_deals_get(from_date, to_date)
        
        if deals is None or len(deals) == 0:
            return []
        
        result = []
        for deal in deals:
            # Only include closing deals (DEAL_ENTRY_OUT = 1) which have realized P/L
            if deal.entry != 1:
                continue
            
            # Apply symbol filter if provided
            if symbol and deal.symbol != symbol:
                continue
            
            net = round(deal.profit + deal.commission + deal.swap + deal.fee, 2)
            result.append({
                'ticket': deal.ticket,
                'order': deal.order,
                'symbol': deal.symbol,
                'type': 'BUY' if deal.type == 0 else 'SELL',
                'volume': round(deal.volume, 4),
                'price': round(deal.price, 6),
                'profit': round(deal.profit, 2),
                'net_profit': net,
                'commission': round(deal.commission, 2),
                'swap': round(deal.swap, 2),
                'fee': round(deal.fee, 2),
                'time': datetime.fromtimestamp(deal.time, tz=timezone.utc).isoformat(),
                'time_server': deal.time,
                'comment': deal.comment,
            })
        
        return result

    def get_today_deals(self, symbol: str = None) -> List[Dict]:
        """
        Get all closed deals for today.
        Uses server time from the latest candle to determine "today" on the broker's clock,
        avoiding local timezone mismatch (e.g. weekend deals appearing on wrong day).
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of deal dicts (see get_deal_history)
        """
        # Use server time to define "today" boundaries
        server_now = self._get_server_time(symbol)
        today_start = server_now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Fetch a wider window then filter by server-time date
        deals = self.get_deal_history(today_start, server_now, symbol)
        # Double-filter: only keep deals whose own timestamp falls on the server-date (UTC)
        today_date = today_start.date()
        return [
            d for d in deals
            if datetime.fromtimestamp(d['time_server'], tz=timezone.utc).date() == today_date
        ]

    def _get_server_time(self, symbol: str = None) -> datetime:
        """
        Get the MT5 broker's server time by reading the latest tick or candle timestamp.
        Returns UTC datetime (matches broker's displayed server time).
        Falls back to UTC now if unavailable.
        """
        try:
            candidates = []
            if symbol:
                candidates.append(symbol)
                base = symbol.rstrip('mM')
                if base and base != symbol:
                    candidates.append(base)
            candidates.extend(['EURUSDm', 'EURUSD', 'GBPUSDm', 'XAUUSDm', 'XAGUSDm'])

            # Deduplicate while keeping order
            seen = set()
            ordered = []
            for cand in candidates:
                if cand and cand not in seen:
                    seen.add(cand)
                    ordered.append(cand)

            for cand in ordered:
                tick = self.mt5.symbol_info_tick(cand)
                if tick is not None and getattr(tick, 'time', 0) > 0:
                    return datetime.fromtimestamp(tick.time, tz=timezone.utc)

            for cand in ordered:
                rates = self.mt5.copy_rates_from_pos(cand, self.mt5.TIMEFRAME_M1, 0, 1)
                if rates is not None and len(rates) > 0:
                    return datetime.fromtimestamp(rates[-1][0], tz=timezone.utc)
        except Exception:
            pass
        return datetime.now(tz=timezone.utc)

    def get_deals_since(self, days: int, symbol: str = None) -> List[Dict]:
        """
        Get all closed deals for the last N days.
        
        Args:
            days: Number of days to look back
            symbol: Optional symbol filter
            
        Returns:
            List of deal dicts (see get_deal_history)
        """
        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(days=days)
        return self.get_deal_history(start, now, symbol)