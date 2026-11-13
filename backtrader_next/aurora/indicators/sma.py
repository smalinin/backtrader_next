"""
Simple Moving Average (SMA) indicator for Aurora.

Simplified implementation with automatic synchronization and plotting support.
Optimized with Numba JIT compilation for maximum performance.
"""

import numpy as np
from numba import jit
from .simple import AuroraSimpleIndicator


@jit(nopython=True, cache=True)
def _sma_numba(close: np.ndarray, period: int) -> np.ndarray:
    """
    Numba-optimized SMA calculation.
    
    Uses JIT compilation for 10-50x performance improvement.
    
    Args:
        close: Close price array
        period: Moving average period
    
    Returns:
        Numpy array of SMA values
    """
    n = len(close)
    result = np.full(n, np.nan)
    
    # Explicitly convert period to int to avoid type inference issues
    p = int(period)
    
    # Calculate first SMA value
    if n >= p:
        sum_val = 0.0
        for i in range(p):
            sum_val += close[i]
        result[p - 1] = sum_val / p
        
        # Use rolling window for subsequent values
        for i in range(p, n):
            sum_val = sum_val - close[i - p] + close[i]
            result[i] = sum_val / p
    
    return result


class SMA(AuroraSimpleIndicator):
    """
    Simple Moving Average indicator.
    
    Calculates the average of the last N periods using vectorized NumPy operations.
    Automatically synchronized with data feed - no manual advance() needed.
    
    Params:
        - period (default=20): Number of periods for the moving average
    
    Example:
        sma = SMA(self.data, period=20)
        if self.data.close[0] > sma[0]:  # Automatic sync via data._idx
            self.buy()
    """
    
    # Plotting configuration
    plotinfo = dict(
        plot=True,
        subplot=False,  # Plot on price chart
        plotname='SMA',
        plotabove=False,
    )
    
    plotlines = dict(
        sma=dict(_name='SMA', linewidth=1.5)
    )
    
    def __init__(self, data, period=20):
        """
        Initialize SMA indicator.
        
        Args:
            data: Aurora data feed
            period: Number of periods for moving average
        """
        super().__init__(data, period=period)
        self._period = period
        self._values = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        # Support both a full data feed and a bare line view (e.g. data.close)
        if hasattr(self._data, 'lines'):
            # Full data feed: SMA(self.data, period=N)
            close_line = self._data.lines.close
            close_array = close_line.parent_array[:, close_line.column_idx]
        else:
            # Line view passed directly: SMA(self.data.close, period=N)
            close_array = self._data.parent_array[:, self._data.column_idx]
        # Use Numba-optimized calculation
        self._values = _sma_numba(close_array, self._period)
    
    @staticmethod
    def _calculate(close: np.ndarray, period: int) -> np.ndarray:
        """
        Vectorized SMA calculation (fallback or external use).
        
        For internal use, _do_calculate() calls the Numba-optimized version.
        
        Args:
            close: Close price array
            period: Moving average period
        
        Returns:
            Numpy array of SMA values
        """
        return _sma_numba(close, period)
    
    def _get_value_at(self, idx: int) -> float:
        """Get SMA value at specific index"""
        if idx < 0 or idx >= len(self._values):
            return np.nan
        return self._values[idx]
    
    def _getplotdata(self) -> dict:
        """Return data for plotting"""
        return {'sma': self._values}
