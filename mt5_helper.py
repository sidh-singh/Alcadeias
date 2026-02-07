from typing import Dict, Optional
import pandas as pd
import time


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
        self.request = {
            "action": 0,
            "symbol": "",
            "volume": 0,
            "type": 0,
            "price": 0,
            "type_time": 0,
            "type_filling": 0,
            "sl": 0,
            "tp": 0,
        }
        self.risk_reward_ratio = [1, 1]
        
        # Initialize request defaults
        self.request['type_time'] = self.mt5.ORDER_TIME_GTC
        self.request['type_filling'] = self.mt5.ORDER_FILLING_IOC
        self.request['action'] = self.mt5.TRADE_ACTION_DEAL
    
    def get_buy_positions(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed position information for BUY positions
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSD', 'XAUUSD')
        
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
            symbol: Trading symbol (e.g., 'BTCUSD', 'XAUUSD')
        
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
    
    def get_rates(self, symbol: str, timeframe: int, count: int):
        """
        Fetch historical rates/candles for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSD', 'XAUUSD')
            timeframe: MT5 timeframe constant (e.g., mt5.TIMEFRAME_M1, mt5.TIMEFRAME_H1)
            count: Number of candles to fetch
        
        Returns:
            Numpy array with OHLCV data or None if failed
            Each row contains: time, open, high, low, close, tick_volume, spread, real_volume
        """
        rates = self.mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        rates_frame = pd.DataFrame(rates)
        rates_frame["time"] = pd.to_datetime(rates_frame["time"], unit="s")
        return rates_frame
    
    def buy(self, symbol: str, qty: float, sl: float = 0, tp: float = 0):
        """
        Place a BUY order
        
        Args:
            symbol: Trading symbol
            qty: Order volume/quantity
            sl: Stop loss (0 for auto-calculation based on risk_reward_ratio)
            tp: Take profit (0 for auto-calculation based on risk_reward_ratio)
        
        Returns:
            Order result from MT5
        """
        self.request['symbol'] = symbol
        self.request['volume'] = qty
        self.request['price'] = self.mt5.symbol_info_tick(symbol).ask
        self.request['type'] = self.mt5.ORDER_TYPE_BUY
        
        # Set SL/TP (auto-calculate if not provided)
        if sl == 0:
            self.request["sl"] = (self.mt5.symbol_info_tick(symbol).ask) - (
                self.mt5.symbol_info_tick(symbol).ask * self.risk_reward_ratio[0]
            )
        else:
            self.request["sl"] = sl
            
        if tp == 0:
            self.request["tp"] = (self.mt5.symbol_info_tick(symbol).ask) + (
                self.mt5.symbol_info_tick(symbol).ask * self.risk_reward_ratio[1]
            )
        else:
            self.request["tp"] = tp
        
        order_status = self.mt5.order_send(self.request)
        time.sleep(0.1)
        return order_status
    
    def sell(self, symbol: str, qty: float, sl: float = 0, tp: float = 0):
        """
        Place a SELL order
        
        Args:
            symbol: Trading symbol
            qty: Order volume/quantity
            sl: Stop loss (0 for auto-calculation based on risk_reward_ratio)
            tp: Take profit (0 for auto-calculation based on risk_reward_ratio)
        
        Returns:
            Order result from MT5
        """
        self.request['symbol'] = symbol
        self.request['volume'] = qty
        self.request['price'] = self.mt5.symbol_info_tick(symbol).ask
        self.request['type'] = self.mt5.ORDER_TYPE_SELL
        
        # Set SL/TP (auto-calculate if not provided)
        if sl == 0:
            self.request["sl"] = (self.mt5.symbol_info_tick(symbol).ask) + (
                self.mt5.symbol_info_tick(symbol).ask * self.risk_reward_ratio[0]
            )
        else:
            self.request["sl"] = sl
            
        if tp == 0:
            self.request["tp"] = (self.mt5.symbol_info_tick(symbol).ask) - (
                self.mt5.symbol_info_tick(symbol).ask * self.risk_reward_ratio[1]
            )
        else:
            self.request["tp"] = tp
        
        order_status = self.mt5.order_send(self.request)
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