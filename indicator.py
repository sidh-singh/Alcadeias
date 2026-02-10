import pandas as pd
import numpy as np


class Indicator:
    """Smoothed Heiken Ashi v3 Indicator"""
    
    def __init__(self):
        """Initialize SHA Indicator"""
        pass
    
    def calculate_sha_v3(self, df, length=10, ma_type='EMA'):
        """
        Calculate Smoothed Heiken Ashi v3
        
        Args:
            df: DataFrame with OHLCV data
            length: Smoothing length (used for both pre and post HA smoothing)
            ma_type: MA type (used for both pre and post HA smoothing)
        
        Returns:
            DataFrame with SHA OHLC columns
        """
        df = df.copy()

        # Step 1: Pre-smooth the OHLC
        o = self._ma(df['Open'], length, ma_type, df.get('Volume'))
        h = self._ma(df['High'], length, ma_type, df.get('Volume'))
        l = self._ma(df['Low'], length, ma_type, df.get('Volume'))
        c = self._ma(df['Close'], length, ma_type, df.get('Volume'))

        # Step 2: Heiken Ashi Calculation
        ha_close = (o + h + l + c) / 4
        ha_open = pd.Series(index=df.index, dtype=float)
        ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2

        # Recursive calculation
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2

        ha_high = pd.concat([h, ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([l, ha_open, ha_close], axis=1).min(axis=1)

        # Step 3: Smooth again after HA (same length & MA type)
        sha_open = self._ma(ha_open, length, ma_type, df.get('Volume'))
        sha_high = self._ma(ha_high, length, ma_type, df.get('Volume'))
        sha_low = self._ma(ha_low, length, ma_type, df.get('Volume'))
        sha_close = self._ma(ha_close, length, ma_type, df.get('Volume'))

        sha = pd.DataFrame({
            'Open': sha_open,
            'High': sha_high,
            'Low': sha_low,
            'Close': sha_close
        }, index=df.index)

        return sha
    
    def calculate_sha_gap(self, sha_df, sha_trend_df):
        """
        Calculate absolute gap ratio between signal SHA and trend SHA.
        Uses mean of OHLC candles; trend SHA is the base value.
        Result is always positive (absolute value).
        
        Args:
            sha_df: Signal SHA DataFrame (Open, High, Low, Close)
            sha_trend_df: Trend SHA DataFrame (Open, High, Low, Close)
        
        Returns:
            pd.Series: absolute gap ratio for each candle (e.g. 0.0015)
        """
        sha_mean = (sha_df['Open'] + sha_df['High'] + sha_df['Low'] + sha_df['Close']) / 4
        trend_mean = (sha_trend_df['Open'] + sha_trend_df['High'] + sha_trend_df['Low'] + sha_trend_df['Close']) / 4
        gap_pct = ((sha_mean - trend_mean) / trend_mean).abs()
        return gap_pct
    
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
