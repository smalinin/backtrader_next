import backtrader as bt
import numpy as np
from numba import njit

__all__ = ['SMA']

@njit
def compute_sma_numba(closes, period):
    n = len(closes)
    result = np.empty(n, dtype=np.float64)
    cum = 0.0
    for i in range(n):
        cum += closes[i]
        if i >= period:
            cum -= closes[i - period]
        if i >= period - 1:
            result[i] = cum / period
        else:
            result[i] = np.nan
    return result

class SMA(bt.Indicator):
    """
    SMA indicator using Numba for optimized performance with support for once method.
    """
    lines = ('sma',)
    params = (('period', 20),)

    def __init__(self):
        self.addminperiod(self.p.period)

    def once(self, start, end):
        if end-start==1:
            return

        closes = np.asarray(self.data.get(size=end + 1), dtype=np.float64)
        period = self.p.period
        vals = compute_sma_numba(closes, period)
        self.lines.sma.ndbuffer(vals)


    def next(self):
        if len(self.data) >= self.p.period:
            closes = np.asarray(self.data.get(size=self.p.period), dtype=np.float64)
            self.lines.sma[0] = closes.mean()

