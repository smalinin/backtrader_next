"""Bollinger Bands with population deviation and shared Numba calculation."""

import numpy as np
import backtrader_next as bt

from .utils import compute_bollinger_numba

__all__ = ['BollingerBands']


class BollingerBands(bt.Indicator):
    lines = ('mid', 'top', 'bot')
    params = (('period', 20), ('devfactor', 2.0))
    plotinfo = dict(subplot=False)
    plotlines = dict(top=dict(_samecolor=True), bot=dict(_samecolor=True))

    def __init__(self):
        if self.p.period < 1:
            raise ValueError('Bollinger period must be positive')
        self.addminperiod(self.p.period)

    def next(self):
        values = np.asarray(self.data.get(size=self.p.period))
        mid, deviation = values.mean(), values.std() * self.p.devfactor
        self.lines.mid[0] = mid
        self.lines.top[0], self.lines.bot[0] = mid + deviation, mid - deviation

    def oncestart(self, start, end):
        pass

    def once(self, start, end):
        outputs = compute_bollinger_numba(np.asarray(self.data.lines[0].array),
                                          self.p.period, self.p.devfactor)
        for line, values in zip(self.lines, outputs):
            np.copyto(np.asarray(line.array), values)
