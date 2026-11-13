"""Standard Wilder ATR using the shared Numba true-range kernel."""

import numpy as np
import backtrader_next as bt

from .utils import compute_atr_numba

__all__ = ['ATR']


class ATR(bt.Indicator):
    """ATR requiring period + 1 source bars, as in bt.ind.ATR."""

    lines = ('atr',)
    params = (('period', 14),)
    plotinfo = dict(subplot=True)

    def __init__(self):
        if self.p.period < 1:
            raise ValueError('ATR period must be positive')
        self.addminperiod(self.p.period + 1)

    def _true_range(self, ago=0):
        return max(self.data.high[ago] - self.data.low[ago],
                   abs(self.data.high[ago] - self.data.close[ago - 1]),
                   abs(self.data.low[ago] - self.data.close[ago - 1]))

    def nextstart(self):
        self.lines.atr[0] = sum(self._true_range(-ago) for ago in range(self.p.period)) / self.p.period

    def next(self):
        self.lines.atr[0] = (self.lines.atr[-1] * (self.p.period - 1) + self._true_range()) / self.p.period

    def oncestart(self, start, end):
        pass

    def once(self, start, end):
        high, low, close = (np.asarray(line.array) for line in
                            (self.data.high, self.data.low, self.data.close))
        values = compute_atr_numba(high, low, close, self.p.period)
        np.copyto(np.asarray(self.lines.atr.array), values)
