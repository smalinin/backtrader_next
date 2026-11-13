"""
Moving Average Convergence Divergence (MACD) indicator for Aurora.

Simplified implementation with automatic synchronization and plotting support.
"""

import numpy as np
from .simple import MultiLineIndicator
from .ema import EMA


class MACD(MultiLineIndicator):
    """
    Moving Average Convergence Divergence indicator.
    
    Trend-following momentum indicator showing relationship between two EMAs.
    Has three lines: MACD, Signal, and Histogram.
    
    Params:
        - period_me1 (default=12): Fast EMA period
        - period_me2 (default=26): Slow EMA period
        - period_signal (default=9): Signal line EMA period
    
    Example:
        macd = MACD(self.data, period_me1=12, period_me2=26, period_signal=9)
        if macd.macd[0] > macd.signal[0]:  # MACD crosses above signal
            self.buy()
    """
    
    # Plotting configuration
    plotinfo = dict(
        plot=True,
        subplot=True,  # Separate subplot
        plotname='MACD',
    )
    
    plotlines = dict(
        macd=dict(_name='MACD', linewidth=1.5),
        signal=dict(_name='Signal', linewidth=1.5),
        histo=dict(_name='Histogram', _method='bar', alpha=0.5),
    )
    
    def __init__(self, data, period_me1=12, period_me2=26, period_signal=9):
        """
        Initialize MACD indicator.
        
        Args:
            data: Aurora data feed
            period_me1: Fast EMA period
            period_me2: Slow EMA period
            period_signal: Signal line period
        """
        super().__init__(data, period_me1=period_me1, period_me2=period_me2, period_signal=period_signal)
        self._period = period_me2 + period_signal - 1  # Total minperiod: slow seed + signal seed - 1
        self._period_me1 = period_me1
        self._period_me2 = period_me2
        self._period_signal = period_signal
        self._lines = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        # Get full close column from parent array
        close = self._data.lines.close.parent_array[:, self._data.lines.close.column_idx]
        macd, signal, histo = self._calculate(close, self._period_me1, self._period_me2, self._period_signal)
        
        # Store lines for multi-line access
        self._lines = {
            'macd': macd,
            'signal': signal,
            'histo': histo
        }
    
    @staticmethod
    def _calculate(close: np.ndarray, fast_period: int, slow_period: int, signal_period: int):
        """
        Vectorized MACD calculation.
        
        Args:
            close: Close price array
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period
        
        Returns:
            Tuple of (macd, signal, histogram) numpy arrays
        """
        # Calculate fast and slow EMAs
        fast_ema = EMA._calculate(close, fast_period)
        slow_ema = EMA._calculate(close, slow_period)
        
        # MACD = fast EMA - slow EMA
        macd = fast_ema - slow_ema
        
        # Signal = EMA of MACD
        # Remove NaN values for signal calculation
        signal = np.full(len(macd), np.nan)
        valid_start = slow_period - 1  # Where MACD becomes valid
        if valid_start < len(macd):
            macd_valid = macd[valid_start:]
            signal_temp = EMA._calculate(macd_valid, signal_period)
            signal[valid_start:] = signal_temp
        
        # Histogram = MACD - Signal
        histo = macd - signal
        
        return macd, signal, histo
    
    def _getplotdata(self) -> dict:
        """Return data for plotting"""
        return self._lines

