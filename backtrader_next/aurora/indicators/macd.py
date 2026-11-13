"""
Moving Average Convergence Divergence (MACD) indicator for Aurora.

Simplified implementation with automatic synchronization and plotting support.
"""

import numpy as np
from .simple import MultiLineIndicator
from ...nind.macd import compute_macd_numba


class MACD(MultiLineIndicator):
    """
    Moving Average Convergence Divergence indicator.
    
    Trend-following momentum indicator showing relationship between two EMAs.
    Has three lines: MACD, Signal, and Histogram.

    Both EMA period orders are supported. MACD becomes available after
    max(period_me1, period_me2) bars; signal and histogram require another
    period_signal - 1 bars. Earlier values are NaN. Periods must be positive.
    
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
        if period_me1 < 1 or period_me2 < 1 or period_signal < 1:
            raise ValueError('MACD periods must be positive')
        super().__init__(data, period_me1=period_me1, period_me2=period_me2, period_signal=period_signal)
        self._period = max(period_me1, period_me2) + period_signal - 1
        self._period_me1 = period_me1
        self._period_me2 = period_me2
        self._period_signal = period_signal
        self._lines = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        macd, signal, histo = self._input.calculate(
            self._calculate, self._period_me1, self._period_me2, self._period_signal)
        
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
        if fast_period < 1 or slow_period < 1 or signal_period < 1:
            raise ValueError('MACD periods must be positive')
        return compute_macd_numba(
            close, 2.0 / (fast_period + 1), fast_period,
            2.0 / (slow_period + 1), slow_period,
            2.0 / (signal_period + 1), signal_period)
    
    def _getplotdata(self) -> dict:
        """Return data for plotting"""
        return self._lines

