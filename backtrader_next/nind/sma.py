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
        if self.p.period < 1:
            raise ValueError('SMA period must be positive')
        self.addminperiod(self.p.period)

    def next(self):
        series = np.asarray(self.data.get_array(self.p.period), dtype=np.float64)
        if len(series) >= self.p.period:
            series = series[-self.p.period:]
            self.lines.sma[0] = series.mean()

    def oncestart(self, start, end):
        # once() fills the complete history, including its first valid bar.
        pass

    def once(self, start, end):
        series = np.asarray(self.data.lines[0].array, dtype=np.float64)
        np.copyto(np.asarray(self.lines.sma.array), compute_sma_numba(series, self.p.period))


