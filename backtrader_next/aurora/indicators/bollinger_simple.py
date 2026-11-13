"""
Bollinger Bands indicator for Aurora - SIMPLIFIED VERSION
"""

import numpy as np
from .simple import MultiLineIndicator
from .sma import SMA


class BollingerBands(MultiLineIndicator):
    """
    Bollinger Bands indicator (simplified).
    
    Three bands: middle (SMA), upper (SMA + σ*devfactor), lower (SMA - σ*devfactor).
    
    Params:
        - period (default=20): SMA period
        - devfactor (default=2.0): Number of standard deviations
    
    Example:
        bb = BollingerBands(self.data, period=20, devfactor=2.0)
        if self.data.close[0] < bb.bot[0]:  # Price below lower band
            self.buy()
    """
    
    plotinfo = dict(plot=True, subplot=False, plotname='Bollinger Bands')
    plotlines = dict(
        mid=dict(_name='Mid', linewidth=1.0),
        top=dict(_name='Top', linewidth=1.0, linestyle='--', _samecolor=True),
        bot=dict(_name='Bot', linewidth=1.0, linestyle='--', _samecolor=True),
    )
    
    def __init__(self, data, period=20, devfactor=2.0):
        super().__init__(data, period=period, devfactor=devfactor)
        self._period = period
        self._devfactor = devfactor
        self._lines = None  # Will be calculated on first access
    
    def _do_calculate(self):
        """Perform actual calculation (called lazily on first access)"""
        mid, top, bot = self._input.calculate(self._calculate, self._period, self._devfactor)
        
        self._lines = {'mid': mid, 'top': top, 'bot': bot}
    
    @staticmethod
    def _calculate(close: np.ndarray, period: int, devfactor: float):
        mid = SMA._calculate(close, period)
        
        # Calculate standard deviation
        std = np.full(len(close), np.nan)
        for i in range(period - 1, len(close)):
            std[i] = np.std(close[i - period + 1:i + 1], ddof=0)
        
        top = mid + std * devfactor
        bot = mid - std * devfactor
        
        return mid, top, bot
    
    def _getplotdata(self) -> dict:
        return self._lines
