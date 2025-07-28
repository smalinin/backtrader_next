import numpy as np
import numba
import backtrader as bt
from .utils import compute_ssf_numba

__all__ = ['SuperSmoother']


class SuperSmoother(bt.Indicator):
    '''
    Super Smoother Filter
    '''
    lines = ('ssf',)
    params = (
        ('period', 14),
        ('new', 0),
    )
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.addminperiod(3)
        if new == 0:
            # Ehlers version min phase shift and reversal sensitivity
            a1 = np.exp(-1.414 * np.pi / self.p.period)
            b1 = 2 * a1 * np.cos(1.414 * np.pi / self.p.period)
        else:
            # new better for trend and max noise canceling
            a1 = np.exp(2 * np.pi / self.p.period)
            b1 = 2 * a1 * np.cos(2 * np.pi / self.p.period)

        self.c2 = b1
        self.c3 = -a1 * a1
        self.c1 = 1 - self.c2 - self.c3

    def next(self, status):
        if len(self) < 2:
            self.lines.ssf[0] = self.data[0]
        else:
            val = self.c1 * (self.data[0] + self.data[-1]) / 2 + self.c2 * self.lines.ssf[-1] + self.c3 * self.lines.ssf[-2]
            self.lines.ssf[0] = val

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < 2:
            return

        ssf_values = compute_ssf_numba(series, self.p.period)
        self.lines.ssf.ndbuffer(ssf_values)
