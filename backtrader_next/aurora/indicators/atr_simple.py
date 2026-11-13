"""
Average True Range (ATR) indicator for Aurora - SIMPLIFIED VERSION
Uses Numba JIT compilation for fast calculation.
"""

import numpy as np
from ...nind.utils import compute_atr_numba
from .simple import AuroraSimpleIndicator


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
    
    _requires_ohlc = True
    plotinfo = dict(plot=True, subplot=True, plotname='ATR')
    plotlines = dict(atr=dict(_name='ATR', linewidth=1.5))
    
    def __init__(self, data, period=14):
        super().__init__(data, period=period)
        self._period = period
        self._values = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        high, low, close = self._input.ohlc()
        self._values = compute_atr_numba(high, low, close, self._period)
    
    @staticmethod
    def _calculate(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
        """Batch ATR calculation through the shared Numba kernel."""
        return compute_atr_numba(high, low, close, period)
    
    def _getplotdata(self) -> dict:
        return {'atr': self._values}
