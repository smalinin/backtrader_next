import numpy as np
import numba
import backtrader as bt

__all__ = ['Momentum']

@numba.njit
def compute_momentum_numba(data, period):
    """Calculates momentum using numba for performance."""
    n = len(data)
    result = np.empty(n, dtype=np.float64)
    result[:period] = np.nan
    for i in range(period, n):
        result[i] = data[i] - data[i - period]
    return result

class Momentum(bt.Indicator):
    '''
    Momentum Indicator

    Formula:
      - momentum = data - data(-period)
    '''
    lines = ('momentum',)
    params = (
        ('period', 10),
    )

    def __init__(self):
        '''Initialize the indicator'''
        self.addminperiod(self.p.period + 1)

    def next(self, status):
        '''Calculate the next value of the indicator'''
        series = np.asarray(self.data.get_array(self.p.period), dtype=np.float64)
        self.lines.momentum[0] = series[0] - series[-self.p.period] ##??BUG

    def once(self, start, end):
        if end-start==1:
            return

        '''Calculate the indicator for a given period in a vectorized way'''
        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < self.p.period:
            return

        momentum = compute_momentum_numba(series, self.p.period)
        self.lines.momentum.ndbuffer(momentum)
