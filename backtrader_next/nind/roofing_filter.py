#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
from .utils import compute_roofing_filter_numba

__all__ = ['RoofingFilter']


class RoofingFilter(bt.Indicator):
    '''
    Ehlers Roofing Filter

    Formula:
      - High-pass filter
      - SuperSmoother filter on the result of the high-pass
    '''
    lines = ('roof',)
    params = (
        ('lp_period', 10),  # Low-pass (SuperSmoother) period
        ('hp_period', 48),  # High-pass period
    )

    plotinfo = dict(hp=dict(_plot=False))  # Do not plot the hp line

    def __init__(self):
        self.addminperiod(self.p.hp_period) # Minimum period for calculation
        self.min_size = self.p.hp_period * 5 + 3
        

    def next(self):
        if len(self.data) < 3:
            return

        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)

        roof_values = compute_roofing_filter_numba(series,
            self.p.lp_period, self.p.hp_period
        )
        self.lines.roof[0] = roof_values[-1]


    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < 3:
            return

        roof_values = compute_roofing_filter_numba(series,
            self.p.lp_period, self.p.hp_period
        )

        self.lines.roof.ndbuffer(roof_values)
