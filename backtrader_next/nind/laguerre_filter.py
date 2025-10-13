#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
from .utils import compute_laguerre_filter_numba

__all__ = ['LaguerreFilter']


class LaguerreFilter(bt.Indicator):
    '''
    John Ehlers Laguerre Filter

    This implementation combines the Ultimate Smoother and recursive Laguerre-style filters
    to produce a low-lag, smooth trend-following signal.

    The Ultimate Smoother is a 2-pole filter that removes market noise while preserving
    the underlying price trend. It acts as the base signal (L0) for the Laguerre filter.
  
    The Laguerre filter is then applied using recursive filtering:
      - L0 = $UltimateSmoother(Close, Length);
      - L1 = -γ * L0[1] + L0[1] + γ * L1[1]
      - L2 = -γ * L1[1] + L1[1] + γ * L2[1]
      - L3 = -γ * L2[1] + L2[1] + γ * L3[1]
      - L4 = -γ * L3[1] + L3[1] + γ * L4[1]

    The final output is a weighted sum:
      - Laguerre = (L0 + 4*L1 + 6*L2 + 4*L3 + L4) / 16
    '''
    lines = ('usmoother','laguerre')
    params = (
        ('gama', 0.8),
        ('length', 14),
    )
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.addminperiod(self.p.length)
        self.min_size = self.p.length * 20
        
    def next(self):
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)

        laguerre, usmoother = compute_laguerre_filter_numba(series, self.p.gama, self.p.length)
        self.lines.usmoother[0] = usmoother[-1]
        self.lines.laguerre[0] = laguerre[-1]


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
        laguerre, usmoother = compute_laguerre_filter_numba(series, self.p.gama, self.p.length)
        
        self.lines.usmoother.ndbuffer(usmoother)
        self.lines.laguerre.ndbuffer(laguerre)
