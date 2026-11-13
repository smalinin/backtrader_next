#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import backtrader_next as bt
from .utils import compute_ema_numba

__all__ = ['EMA']

class EMA(bt.Indicator):
    '''
    Exponential Moving Average of the last n periods

    Formula:
      - EMA_t = alpha * price_t + (1 - alpha) * EMA_{t-1}
      - alpha = 2 / (period + 1)

    See also:
      - http://en.wikipedia.org/wiki/Moving_average#Exponential_moving_average
    '''
    lines = ('ema',)
    params = (('period', 10),)
    plotinfo = dict(subplot=False)

    def __init__(self):
        if self.p.period < 1:
            raise ValueError('EMA period must be positive')
        self.addminperiod(self.p.period)
        self.alpha = 2.0 / (self.p.period + 1)

    def nextstart(self):
        self.lines.ema[0] = sum(self.data.get(size=self.p.period)) / self.p.period

    def next(self):
        self.lines.ema[0] = self.alpha * self.data[0] + (1 - self.alpha) * self.lines.ema[-1]

    def oncestart(self, start, end):
        pass

    def once(self, start, end):
        series = np.asarray(self.data.lines[0].array, dtype=np.float64)
        vals = compute_ema_numba(series, self.alpha, self.p.period)
        np.copyto(np.asarray(self.lines.ema.array), vals)
