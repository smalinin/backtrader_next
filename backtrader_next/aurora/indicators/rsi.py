"""
Relative Strength Index (RSI) indicator for Aurora.

Simplified implementation with automatic synchronization and plotting support.
Uses Numba JIT compilation for fast calculation.
"""

import numpy as np
from numba import jit
from .simple import AuroraSimpleIndicator


@jit(nopython=True, cache=True)
def _calculate_rsi_numba(close: np.ndarray, period: int) -> np.ndarray:
    """
    Numba-optimized RSI calculation using Wilder's smoothing.
    
    Args:
        close: Close price array
        period: RSI period
    
    Returns:
        Numpy array of RSI values (0-100)
    """
    n = len(close)
    result = np.full(n, np.nan)
    
    if n < period + 1:
        return result
    
    # Calculate price changes
    changes = np.zeros(n)
    for i in range(1, n):
        changes[i] = close[i] - close[i - 1]
    
    # Separate gains and losses
    gains = np.zeros(n)
    losses = np.zeros(n)
    for i in range(1, n):
        if changes[i] > 0:
            gains[i] = changes[i]
        else:
            losses[i] = -changes[i]
    
    # First average (simple average for initial period)
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        avg_gain += gains[i]
        avg_loss += losses[i]
    avg_gain /= period
    avg_loss /= period
    
    # Calculate first RSI
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))
    
    # Continue with Wilder's smoothing
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))
    
    return result


class RSI(AuroraSimpleIndicator):
    """
    Relative Strength Index indicator.
    
    Momentum oscillator measuring speed and magnitude of price changes.
    Values range from 0-100. Traditionally: >70 overbought, <30 oversold.
    
    Params:
        - period (default=14): Number of periods for RSI calculation
    
    Example:
        rsi = RSI(self.data, period=14)
        if rsi[0] < 30:  # Oversold
            self.buy()
    """
    
    # Plotting configuration
    plotinfo = dict(
        plot=True,
        subplot=True,  # Plot in separate subplot
        plotname='RSI',
        plotabove=False,
        plotymargin=0.15,
        plothlines=[30, 70],  # Oversold/Overbought lines
    )
    
    plotlines = dict(
        rsi=dict(_name='RSI', linewidth=1.5)
    )
    
    def __init__(self, data, period=14):
        """
        Initialize RSI indicator.
        
        Args:
            data: Aurora data feed
            period: Number of periods for RSI
        """
        super().__init__(data, period=period)
        self._period = period
        self._values = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        self._values = self._input.calculate(_calculate_rsi_numba, self._period)
    
    @staticmethod
    def _calculate(close: np.ndarray, period: int) -> np.ndarray:
        """
        Vectorized RSI calculation (non-Numba fallback).
        
        Args:
            close: Close price array
            period: RSI period
        
        Returns:
            Numpy array of RSI values (0-100)
        """
        return _calculate_rsi_numba(close, period)
    
    def _getplotdata(self) -> dict:
        """Return data for plotting"""
        return {'rsi': self._values}

