#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
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
        self.addminperiod(self.p.period)
        self.alpha = 2.0 / (self.p.period + 1)
        self.min_size = self.p.period * 5

    def next(self, status):
        price = self.data[0]
        if len(self.data) == self.p.period:
            closes = self.data.get(size=self.p.period)
            seed = sum(closes) / self.p.period
            self.lines.ema[0] = seed
        elif len(self.data) > self.p.period:
            prev = self.lines.ema[-1]
            self.lines.ema[0] = self.alpha * price + (1 - self.alpha) * prev

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        vals = compute_ema_numba(series, self.alpha, self.p.period)
        self.lines.ema.ndbuffer(vals)
