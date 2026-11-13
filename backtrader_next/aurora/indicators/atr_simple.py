"""
Average True Range (ATR) indicator for Aurora - SIMPLIFIED VERSION
Uses Numba JIT compilation for fast calculation.
"""

import numpy as np
from numba import jit
from .simple import AuroraSimpleIndicator


@jit(nopython=True, cache=True)
def _calculate_atr_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """
    Numba-optimized ATR calculation.
    
    Args:
        high: High price array
        low: Low price array
        close: Close price array
        period: ATR period
    
    Returns:
        Numpy array of ATR values
    """
    n = len(close)
    result = np.full(n, np.nan)
    
    if n == 0:
        return result
    
    # Calculate True Range
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        # Manual max for Numba
        tr[i] = hl
        if hc > tr[i]:
            tr[i] = hc
        if lc > tr[i]:
            tr[i] = lc
    
    # Smooth TR using Wilder's method
    if n >= period:
        # Initial ATR = simple average
        total = 0.0
        for i in range(period):
            total += tr[i]
        result[period - 1] = total / period
        
        # Continue with smoothing
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    
    return result


class ATR(AuroraSimpleIndicator):
    """
    Average True Range indicator (simplified).
    
    Measures market volatility using smoothed true range.
    
    Params:
        - period (default=14): Smoothing period
    
    Example:
        atr = ATR(self.data, period=14)
        if atr[0] > atr[-1]:  # Volatility increasing
            pass
    """
    
    plotinfo = dict(plot=True, subplot=True, plotname='ATR')
    plotlines = dict(atr=dict(_name='ATR', linewidth=1.5))
    
    def __init__(self, data, period=14):
        super().__init__(data, period=period)
        self._period = period
        self._values = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        # Get full OHLC columns from parent array
        high = self._data.lines.high.parent_array[:, self._data.lines.high.column_idx]
        low = self._data.lines.low.parent_array[:, self._data.lines.low.column_idx]
        close = self._data.lines.close.parent_array[:, self._data.lines.close.column_idx]
        
        self._values = _calculate_atr_numba(high, low, close, self._period)
    
    @staticmethod
    def _calculate(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
        """Non-Numba fallback."""
        return _calculate_atr_numba(high, low, close, period)
    
    def _get_value_at(self, idx: int) -> float:
        if idx < 0 or idx >= len(self._values):
            return np.nan
        return self._values[idx]
    
    def _getplotdata(self) -> dict:
        return {'atr': self._values}
