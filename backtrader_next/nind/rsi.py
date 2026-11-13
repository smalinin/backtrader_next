"""Wilder RSI with shared Numba batch calculation and standard line buffers."""

import numpy as np
import backtrader_next as bt

from .utils import compute_rsi_numba

__all__ = ['RSI']


class RSI(bt.Indicator):
    """Safe Wilder RSI; flat prices return safelow (50 by default)."""

    lines = ('rsi',)
    params = (('period', 14), ('safehigh', 100.0), ('safelow', 50.0))
    plotinfo = dict(subplot=True, plothlines=[30, 70])

    def __init__(self):
        if self.p.period < 1:
            raise ValueError('RSI period must be positive')
        self.addminperiod(self.p.period + 1)

    def _set_value(self):
        if self._loss == 0:
            value = self.p.safelow if self._gain == 0 else self.p.safehigh
        else:
            value = 100.0 - 100.0 / (1.0 + self._gain / self._loss)
        self.lines.rsi[0] = value

    def nextstart(self):
        changes = np.diff(self.data.get(size=self.p.period + 1))
        self._gain = np.maximum(changes, 0).sum() / self.p.period
        self._loss = np.maximum(-changes, 0).sum() / self.p.period
        self._set_value()

    def next(self):
        change = self.data[0] - self.data[-1]
        self._gain = (self._gain * (self.p.period - 1) + max(change, 0.0)) / self.p.period
        self._loss = (self._loss * (self.p.period - 1) + max(-change, 0.0)) / self.p.period
        self._set_value()

    def oncestart(self, start, end):
        pass

    def once(self, start, end):
        values = compute_rsi_numba(np.asarray(self.data.lines[0].array), self.p.period,
                                   self.p.safelow, self.p.safehigh)
        np.copyto(np.asarray(self.lines.rsi.array), values)
