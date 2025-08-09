import numpy as np
import numba
import backtrader as bt

__all__ = ['SecondDerivative']

@numba.njit
def compute_second_derivative_numba(closes):
    n = len(closes)
    result = np.empty(n, dtype=np.float64)
    result[:2] = np.nan
    for i in range(2, n):
        result[i] = closes[i] - 2 * closes[i-1] + closes[i-2]
    return result

class SecondDerivative(bt.Indicator):
    '''
    Second Derivative Indicator

    Formula:
      - sd = close[0] - 2 * close[-1] + close[-2]
    '''
    lines = ('sd',)
    params = ()

    def __init__(self):
        # The formula needs access to `close[-2]`, so the min period is 3
        self.addminperiod(3)

    def next(self, status):
        self.lines.sd[0] = self.data[0] - 2 * self.data[-1] + self.data[-2]

    def once(self, start, end):
        if end-start==1:
            return

        closes = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(closes) < 3:
            return

        sd = compute_second_derivative_numba(closes)
        self.lines.sd.ndbuffer(sd)
