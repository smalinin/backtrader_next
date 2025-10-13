#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt

__all__ = ['ROC']

@numba.njit
def compute_roc_numba(data, period):
    n = len(data)
    result = np.empty(n, dtype=np.float64)
    result[:period] = np.nan
    for i in range(period, n):
        result[i] = (data[i] - data[i - period]) / data[i - period]
    return result

class ROC(bt.Indicator):
    '''
    Rate of Change

    Formula:
      - roc = (data - data(-period)) / data(-period)
    '''
    lines = ('roc',)
    params = (('period', 12),)

    def __init__(self):
        self.addminperiod(self.p.period)

    def next(self):
        self.lines.roc[0] = (self.data[0] - self.data[-self.p.period]) / self.data[-self.p.period]

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)

        roc = compute_roc_numba(series, self.p.period)
        self.lines.roc.ndbuffer(roc)
