"""
Exponential Moving Average (EMA) indicator for Aurora.

Simplified implementation with automatic synchronization and plotting support.
Uses Numba JIT compilation for fast calculation.
"""

import numpy as np
from ...nind.utils import compute_ema_numba
from .simple import AuroraSimpleIndicator


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
        self._values = self._input.calculate(self._calculate, self._period)
    
    @staticmethod
    def _calculate(close: np.ndarray, period: int) -> np.ndarray:
        """
        Batch EMA calculation through the shared Numba kernel.
        
        Args:
            close: Close price array
            period: EMA period
        
        Returns:
            Numpy array of EMA values
        """
        return compute_ema_numba(close, 2.0 / (period + 1), period)
    
    def _getplotdata(self) -> dict:
        """Return data for plotting"""
        return {'ema': self._values}
