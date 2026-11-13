"""
Relative Strength Index (RSI) indicator for Aurora.

Simplified implementation with automatic synchronization and plotting support.
Uses Numba JIT compilation for fast calculation.
"""

import numpy as np
from ...nind.utils import compute_rsi_numba
from .simple import AuroraSimpleIndicator


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
        self._values = self._input.calculate(compute_rsi_numba, self._period)
    
    @staticmethod
    def _calculate(close: np.ndarray, period: int) -> np.ndarray:
        """
        Batch RSI calculation through the shared Numba kernel.
        
        Args:
            close: Close price array
            period: RSI period
        
        Returns:
            Numpy array of RSI values (0-100)
        """
        return compute_rsi_numba(close, period)
    
    def _getplotdata(self) -> dict:
        """Return data for plotting"""
        return {'rsi': self._values}

