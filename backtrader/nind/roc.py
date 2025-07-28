import numpy as np
import numba
import backtrader as bt

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

    def next(self, status):
        series = np.asarray(self.data.get_array(self.p.period), dtype=np.float64)
        self.lines.roc[0] = (series[0] - series[-self.p.period]) / series[-self.p.period] ##BUG

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < self.p.period:
            return

        roc = compute_roc_numba(series, self.p.period)
        self.lines.roc.ndbuffer(roc)
