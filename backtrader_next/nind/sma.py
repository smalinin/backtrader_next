#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import backtrader_next as bt
import numpy as np
from .utils import compute_sma_numba

__all__ = ['SMA']

class SMA(bt.Indicator):
    """
    SMA indicator using Numba for optimized performance with support for once method.
    """
    lines = ('sma',)
    params = (('period', 20),)
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.addminperiod(self.p.period)

    def next(self, status):
        series = np.asarray(self.data.get_array(self.p.period), dtype=np.float64)
        if len(series) >= self.p.period:
            series = series[-self.p.period:]
            self.lines.sma[0] = series.mean()

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        period = self.p.period
        vals = compute_sma_numba(series, period)
        self.lines.sma.ndbuffer(vals)


