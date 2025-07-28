import numpy as np
import numba
import backtrader as bt
import math
from .utils import compute_ultimate_smoother_numba

__all__ = ['UltimateSmoother']


class UltimateSmoother(bt.Indicator):
    '''
    John Ehlers Ultimate Smoother
    
    The Ultimate Smoother is a 2-pole filter that provides excellent smoothing
    with minimal lag. It's designed to remove market noise while preserving
    the underlying trend.
    
    Formula:
      - Filter = (c1 * (Price + Price[1])) / 2 + c2 * Filter[1] + c3 * Filter[2]
      
    Where coefficients are calculated as:
      - a = exp(-1.414 * π / period)
      - c2 = 2 * a * cos(1.414 * π / period)
      - c3 = -a²
      - c1 = 1 - c2 - c3
    '''
    lines = ('usmoother',)
    params = (
        ('period', 14),
    )
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.addminperiod(3)
        self.min_size = self.p.period * 5
        
        # Pre-calculate coefficients
        #a = math.exp(-1.414213562373095 * math.pi / self.p.period)
        #self.c2 = 2.0 * a * math.cos(1.414213562373095 * math.pi / self.p.period)
        #self.c3 = -a * a
        #self.c1 = 1.0 - self.c2 - self.c3

    def next(self, status):
        """
        Calculate Ultimate Smoother value for streaming data (real-time)
        """
        if len(self.data) < 3:
            return

        # Get recent data for smoothing calculations
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)

        smoothed = compute_ultimate_smoother_numba(series, self.p.period)
        self.lines.usmoother[0] = smoothed[-1]


    def once(self, start, end):
        if end-start==1:
            return

        """
        Calculate Ultimate Smoother values for historical data (batch processing)
        """
        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < 3:
            return

        # Calculate using numba-optimized function
        smoother_values = compute_ultimate_smoother_numba(series, self.p.period)
        
        self.lines.usmoother.ndbuffer(smoother_values)
