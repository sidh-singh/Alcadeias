import pandas as pd
import numpy as np


class Indicator:
    """Smoothed Heiken Ashi v3 Indicator"""
    
    def __init__(self):
        """Initialize SHA Indicator"""
        pass
    
    def calculate_sha_v3(self, df, smooth_length=10, smooth_ma_type='EMA', 
                         after_smooth_length=10, after_smooth_ma_type='EMA'):
        """
        Calculate Smoothed Heiken Ashi v3
        
        Args:
            df: DataFrame with OHLCV data
            smooth_length: Length for initial smoothing (default=10)
            smooth_ma_type: MA type for initial smoothing (default='EMA')
            after_smooth_length: Length for post-HA smoothing (default=10)
            after_smooth_ma_type: MA type for post-HA smoothing (default='EMA')
        
        Returns:
            DataFrame with SHA OHLC columns
        """
        df = df.copy()

        # Step 1: Pre-smooth the OHLC
        o = self._ma(df['Open'], smooth_length, smooth_ma_type, df.get('Volume'))
        h = self._ma(df['High'], smooth_length, smooth_ma_type, df.get('Volume'))
        l = self._ma(df['Low'], smooth_length, smooth_ma_type, df.get('Volume'))
        c = self._ma(df['Close'], smooth_length, smooth_ma_type, df.get('Volume'))

        # Step 2: Heiken Ashi Calculation
        ha_close = (o + h + l + c) / 4
        ha_open = pd.Series(index=df.index, dtype=float)
        ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2

        # Recursive calculation
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2

        ha_high = pd.concat([h, ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([l, ha_open, ha_close], axis=1).min(axis=1)

        # Step 3: Smooth again after HA
        sha_open = self._ma(ha_open, after_smooth_length, after_smooth_ma_type, df.get('Volume'))
        sha_high = self._ma(ha_high, after_smooth_length, after_smooth_ma_type, df.get('Volume'))
        sha_low = self._ma(ha_low, after_smooth_length, after_smooth_ma_type, df.get('Volume'))
        sha_close = self._ma(ha_close, after_smooth_length, after_smooth_ma_type, df.get('Volume'))

        sha = pd.DataFrame({
            'Open': sha_open,
            'High': sha_high,
            'Low': sha_low,
            'Close': sha_close
        }, index=df.index)

        return sha
    
    def _ma(self, series, length, ma_type='EMA', volume=None):
        """
        Calculate moving average
        
        Args:
            series: Price series
            length: MA length
            ma_type: Type of MA (SMA, EMA, WMA, RMA, VWMA, DEMA, TEMA, ZLEMA, HMA, ALMA, SMMA, LSMA, DONCHIAN)
            volume: Volume series (required for VWMA)
        
        Returns:
            pd.Series with MA values
        """
        if length <= 0:
            return series
    
        ma_type = ma_type.upper()
        
        if ma_type == 'SMA':
            return series.rolling(window=length).mean()
        
        elif ma_type == 'EMA':
            return series.ewm(span=length, adjust=False).mean()
        
        elif ma_type == 'WMA':
            weights = np.arange(1, length + 1)
            return series.rolling(window=length).apply(
                lambda x: np.dot(x, weights) / weights.sum(), raw=True
            )
        
        elif ma_type == 'RMA':
            alpha = 1.0 / length
            return series.ewm(alpha=alpha, adjust=False).mean()
        
        elif ma_type == 'VWMA':
            if volume is None:
                return series.ewm(span=length, adjust=False).mean()
            pv = series * volume
            return pv.rolling(window=length).sum() / volume.rolling(window=length).sum()
        
        elif ma_type == 'DEMA':
            ema1 = series.ewm(span=length, adjust=False).mean()
            ema2 = ema1.ewm(span=length, adjust=False).mean()
            return 2 * ema1 - ema2
        
        elif ma_type == 'TEMA':
            ema1 = series.ewm(span=length, adjust=False).mean()
            ema2 = ema1.ewm(span=length, adjust=False).mean()
            ema3 = ema2.ewm(span=length, adjust=False).mean()
            return 3 * ema1 - 3 * ema2 + ema3
        
        elif ma_type == 'ZLEMA':
            lag = (length - 1) // 2
            zlema_series = 2 * series - series.shift(lag)
            return zlema_series.ewm(span=length, adjust=False).mean()
        
        elif ma_type == 'HMA':
            half_length = length // 2
            sqrt_length = int(np.sqrt(length))
            wma_half = series.rolling(window=half_length).apply(
                lambda x: np.dot(x, np.arange(1, half_length + 1)) / np.arange(1, half_length + 1).sum(), 
                raw=True
            )
            wma_full = series.rolling(window=length).apply(
                lambda x: np.dot(x, np.arange(1, length + 1)) / np.arange(1, length + 1).sum(), 
                raw=True
            )
            diff = 2 * wma_half - wma_full
            weights_sqrt = np.arange(1, sqrt_length + 1)
            return diff.rolling(window=sqrt_length).apply(
                lambda x: np.dot(x, weights_sqrt) / weights_sqrt.sum(), raw=True
            )
        
        elif ma_type == 'ALMA':
            offset = 0.85
            sigma = 6
            m = offset * (length - 1)
            s = length / sigma
            weights = np.exp(-((np.arange(length) - m) ** 2) / (2 * s * s))
            weights /= weights.sum()
            return series.rolling(window=length).apply(
                lambda x: np.dot(x, weights), raw=True
            )
        
        elif ma_type == 'SMMA' or ma_type == 'SWMA':
            alpha = 1.0 / length
            return series.ewm(alpha=alpha, adjust=False).mean()
        
        elif ma_type == 'LSMA':
            return series.rolling(window=length).apply(
                lambda x: np.polyfit(np.arange(len(x)), x, 1)[0] * (len(x)-1) + np.polyfit(np.arange(len(x)), x, 1)[1],
                raw=True
            )
        
        elif ma_type == 'DONCHIAN':
            return (series.rolling(window=length).max() + series.rolling(window=length).min()) / 2
        
        else:
            return series.ewm(span=length, adjust=False).mean()
