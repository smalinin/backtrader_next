#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
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
        if self.p.new == 0:
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

    def next(self):
        if len(self) < 2:
            self.lines.ssf[0] = self.data[0]
        else:
            ssf_1 = self.lines.ssf[-1]
            ssf_2 = self.lines.ssf[-2]
            val = self.c1 * (self.data[0] + self.data[-1]) / 2 + self.c2 * (self.data[-1] if np.isnan(ssf_1) else ssf_1) + self.c3 * (self.data[-2] if np.isnan(ssf_2) else ssf_2)
            self.lines.ssf[0] = val

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < 2:
            return

        ssf_values = compute_ssf_numba(series, self.p.period)
        self.lines.ssf.ndbuffer(ssf_values)
