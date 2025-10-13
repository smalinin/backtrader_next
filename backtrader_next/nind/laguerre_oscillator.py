#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
from .utils import compute_laguerre_oscillator_numba

__all__ = ['LaguerreOscillator']


class LaguerreOscillator(bt.Indicator):
    """
    John Ehlers' Laguerre Oscillator (TASC Jul 2025).

    L0 = UltimateSmoother(Close, length)
    L1 = recursive Laguerre with gamma
    Signal = L0 - L1
    RMS    = rolling RMS of Signal over rms_length bars
    Osc    = Signal / RMS  (if RMS != 0) else 0

    @returns: Laguerre Oscillator array
    """
    lines = ('oscillator',)
    params = (
        ('gama', 0.5),  
        ('length', 30),
    )
    plotinfo = dict(plothlines=[0.0])
    plotlines = dict(corr=dict(ls='-'),)

    def __init__(self):
        self.addminperiod(100)
        self.min_size = 100 + self.p.length * 20
        
    def next(self):
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)

        osc = compute_laguerre_oscillator_numba(series, self.p.gama, self.p.length, 100)
        self.lines.oscillator[0] = osc[-1]


    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < 100:
            return

        osc = compute_laguerre_oscillator_numba(series, self.p.gama, self.p.length, 100)
        
        self.lines.oscillator.ndbuffer(osc)
