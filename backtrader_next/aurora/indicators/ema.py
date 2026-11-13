"""
Exponential Moving Average (EMA) indicator for Aurora.

Simplified implementation with automatic synchronization and plotting support.
Uses Numba JIT compilation for fast calculation.
"""

import numpy as np
from numba import jit
from .simple import AuroraSimpleIndicator


@jit(nopython=True, cache=True)
def _calculate_ema_numba(close: np.ndarray, period: int) -> np.ndarray:
    """
    Numba-optimized EMA calculation.
    
    Args:
        close: Close price array
        period: EMA period
    
    Returns:
        Numpy array of EMA values
    """
    n = len(close)
    result = np.full(n, np.nan)
    
    if n == 0:
        return result
    
    # Smoothing factor
    k = 2.0 / (period + 1)
    one_minus_k = 1.0 - k

    # Seed: first EMA = SMA of first `period` values
    if n < period:
        return result

    total = 0.0
    for i in range(period):
        total += close[i]
    result[period - 1] = total / period

    # EMA from period onward
    for i in range(period, n):
        result[i] = close[i] * k + result[i - 1] * one_minus_k

    return result


class EMA(AuroraSimpleIndicator):
    """
    Exponential Moving Average indicator.
    
    Calculates exponentially weighted moving average where recent values
    have more weight. Uses smoothing factor k = 2 / (period + 1).
    
    Params:
        - period (default=20): Number of periods for the EMA
    
    Example:
        ema = EMA(self.data, period=12)
        if self.data.close[0] > ema[0]:
            self.buy()
    """
    
    # Plotting configuration
    plotinfo = dict(
        plot=True,
        subplot=False,
        plotname='EMA',
        plotabove=False,
    )
    
    plotlines = dict(
        ema=dict(_name='EMA', linewidth=1.5)
    )
    
    def __init__(self, data, period=20):
        """
        Initialize EMA indicator.
        
        Args:
            data: Aurora data feed
            period: Number of periods for EMA
        """
        super().__init__(data, period=period)
        self._period = period
        self._values = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        self._values = self._input.calculate(_calculate_ema_numba, self._period)
    
    @staticmethod
    def _calculate(close: np.ndarray, period: int) -> np.ndarray:
        """
        Vectorized EMA calculation (non-Numba fallback).
        
        Args:
            close: Close price array
            period: EMA period
        
        Returns:
            Numpy array of EMA values
        """
        return _calculate_ema_numba(close, period)
    
    def _getplotdata(self) -> dict:
        """Return data for plotting"""
        return {'ema': self._values}
