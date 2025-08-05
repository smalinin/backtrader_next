import numpy as np
import numba
import backtrader as bt

__all__ = ['Momentum']

@numba.njit
def compute_momentum_numba(data, period):
    """Calculates momentum using numba for performance."""
    n = len(data)
    result = np.full(n, np.nan)
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
        self.addminperiod(self.p.period)

    def next(self, status):
        self.lines.momentum[0] = self.data[0] - self.data[-self.p.period]

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)

        momentum = compute_momentum_numba(series, self.p.period)
        self.lines.momentum.ndbuffer(momentum)
