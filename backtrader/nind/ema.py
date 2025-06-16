import numpy as np
import numba
import backtrader as bt

__all__ = ['EMA']

# JIT-compiled EMA computation
@numba.njit
def compute_ema_numba(closes, alpha, period):
    n = len(closes)
    result = np.empty(n, dtype=np.float64)
    # Seed with simple average
    seed = np.mean(closes[:period])
    for i in range(period):
        result[i] = np.nan
    result[period - 1] = seed
    # Recursive EMA
    for i in range(period, n):
        result[i] = alpha * closes[i] + (1 - alpha) * result[i - 1]
    return result

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

    def next(self):
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

        '''Compute EMA over full range via Numba JIT function.'''
        closes = np.asarray(self.data.array, dtype=np.float64)
        period = self.p.period
        if len(closes) < period:
            return
        vals = compute_ema_numba(closes, self.alpha, period)
        self.lines.ema.ndbuffer(vals)
