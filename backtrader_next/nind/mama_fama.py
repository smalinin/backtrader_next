#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt

__all__ = ['MAMA_FAMA']

@numba.njit
def compute_mama_fama_numba(high, low, fast_limit, slow_limit):
    n = len(high)
    price = (high + low) / 2.0
    mama = np.zeros(n, dtype=np.float64)
    fama = np.zeros(n, dtype=np.float64)

    # intermediate arrays
    smooth = np.zeros(n, dtype=np.float64)
    detrender = np.zeros(n, dtype=np.float64)
    Q1 = np.zeros(n, dtype=np.float64)
    I1 = np.zeros(n, dtype=np.float64)
    jI = np.zeros(n, dtype=np.float64)
    jQ = np.zeros(n, dtype=np.float64)
    I2 = np.zeros(n, dtype=np.float64)
    Q2 = np.zeros(n, dtype=np.float64)
    Re = np.zeros(n, dtype=np.float64)
    Im = np.zeros(n, dtype=np.float64)
    period = np.zeros(n, dtype=np.float64)
    smooth_period = np.zeros(n, dtype=np.float64)
    phase = np.zeros(n, dtype=np.float64)

    # initial values
    for i in range(6):
        period[i] = 0.0
        smooth[i] = 0.0
        detrender[i] = 0.0
        Q1[i] = 0.0
        I1[i] = 0.0
        I2[i] = 0.0
        Q2[i] = 0.0
        Re[i] = 0.0
        Im[i] = 0.0
        smooth_period[i] = 0.0
        phase[i] = 0.0
        mama[i] = price[i]
        fama[i] = price[i]

    for i in range(6, n):
        # smoothing
        smooth[i] = (4*price[i] + 3*price[i-1] + 2*price[i-2] + price[i-3]) / 10.0

        # detrender
        detrender[i] = (0.0962*smooth[i] + 0.5769*smooth[i-2] - 0.5769*smooth[i-4] - 0.0962*smooth[i-6]) * (0.075*period[i-1] + 0.54)

        # Q1 and I1
        Q1[i] = (0.0962*detrender[i] + 0.5769*detrender[i-2] - 0.5769*detrender[i-4] - 0.0962*detrender[i-6]) * (0.075*period[i-1] + 0.54)
        I1[i] = detrender[i-3]

        # jI and jQ
        jI[i] = (0.0962*I1[i] + 0.5769*I1[i-2] - 0.5769*I1[i-4] - 0.0962*I1[i-6]) * (0.075*period[i-1] + 0.54)
        jQ[i] = (0.0962*Q1[i] + 0.5769*Q1[i-2] - 0.5769*Q1[i-4] - 0.0962*Q1[i-6]) * (0.075*period[i-1] + 0.54)

        # I2 and Q2
        I2[i] = I1[i] - jQ[i]
        Q2[i] = Q1[i] + jI[i]

        I2[i] = 0.2*I2[i] + 0.8*I2[i-1]
        Q2[i] = 0.2*Q2[i] + 0.8*Q2[i-1]

        # homodyne discriminator
        Re[i] = I2[i]*I2[i-1] + Q2[i]*Q2[i-1]
        Im[i] = I2[i]*Q2[i-1] - Q2[i]*I2[i-1]
        Re[i] = 0.2*Re[i] + 0.8*Re[i-1]
        Im[i] = 0.2*Im[i] + 0.8*Im[i-1]

        # period calculation
        if Im[i] != 0.0 and Re[i] != 0.0:
            period[i] = 2.0*np.pi/np.arctan(Im[i]/Re[i])
        else:
            period[i] = period[i-1]
        if period[i] > 1.5*period[i-1]:
            period[i] = 1.5*period[i-1]
        if period[i] < 0.67*period[i-1]:
            period[i] = 0.67*period[i-1]
        if period[i] < 6.0:
            period[i] = 6.0
        if period[i] > 50.0:
            period[i] = 50.0
        period[i] = 0.2*period[i] + 0.8*period[i-1]

        # smooth period and phase
        smooth_period[i] = 0.33*period[i] + 0.67*smooth_period[i-1]
        if I1[i] != 0.0 and Q1[i] != 0.0:
            phase[i] = 180.0/np.pi*np.arctan(Q1[i]/I1[i])
        else:
            phase[i] = phase[i-1]

        # alpha calculation
        delta_phase = phase[i-1] - phase[i]
        if delta_phase < 1.0:
            delta_phase = 1.0
        alpha = fast_limit/delta_phase
        if alpha < slow_limit:
            alpha = slow_limit
        if alpha > fast_limit:
            alpha = fast_limit

        # MAMA and FAMA
        mama[i] = alpha*price[i] + (1.0-alpha)*mama[i-1]
        fama[i] = 0.5*alpha*mama[i] + (1.0-0.5*alpha)*fama[i-1]

    return mama, fama

class MAMA_FAMA(bt.Indicator):
    '''
    MESA Adaptive Moving Average (MAMA) and Following Adaptive Moving Average (FAMA)
    intraday                         fast=0.8  slow=0.1
    for balance                      fast=0.5  slow=0.05
    max noise cancel(swing, trends)  fast=0.3  slow=0.01
    '''
    lines = ('mama', 'fama')
    params = (
        ('fast_limit', 0.5),  # default fast limit
        ('slow_limit', 0.05), # default slow limit
    )
    plotinfo = dict(subplot=False)
    plotlines = dict(
        mama=dict(ls='-'),
        fama=dict(ls='-'),
    )

    def __init__(self):
        self.addminperiod(6)
        self.fast_limit = self.p.fast_limit
        self.slow_limit = self.p.slow_limit
        self.min_size = round((2/self.p.slow_limit - 1) * 20)

    def next(self):
        highs = np.asarray(self.data.high.get_array(self.min_size), dtype=np.float64)
        lows = np.asarray(self.data.low.get_array(self.min_size), dtype=np.float64)

        mama, fama = compute_mama_fama_numba(highs, lows, self.fast_limit, self.slow_limit)
        self.lines.mama[0] = mama[-1]
        self.lines.fama[0] = fama[-1]

    def once(self, start, end):
        if end-start==1:
            return

        highs = np.asarray(self.data.high.get_array_preloaded(), dtype=np.float64)
        lows = np.asarray(self.data.low.get_array_preloaded(), dtype=np.float64)

        mama, fama = compute_mama_fama_numba(highs, lows, self.fast_limit, self.slow_limit)

        self.lines.mama.ndbuffer(mama)
        self.lines.fama.ndbuffer(fama)

