#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
from .utils import compute_cybernetic_oscillator_numba

__all__ = ['CyberneticOscillator']


class CyberneticOscillator(bt.Indicator):
    '''
    John Ehlers' Cybernetic Oscillator (TASC Apr 2025).

    HP = $HighPass(Close, HPLength);
    LP = $SuperSmoother(HP, LPLength);
    RMS = $RMS(LP, 100);

    if RMS <> 0 then 
        CyberneticOsc = LP / RMS;    
    '''
    lines = ('coscillator',)
    params = (
        ('hp_period', 30),  # High-pass period
        ('lp_period', 20),  # Low-pass (SuperSmoother) period
    )
    plotinfo = dict(plothlines=[0.0])
    plotlines = dict(corr=dict(ls='-'),)

    def __init__(self):
        min_period = max(self.p.hp_period, self.p.lp_period)
        self.addminperiod(100)
        #self.min_size = 100 + min_period * 10
        
    def next(self):
        series = np.asarray(self.data.get_array(), dtype=np.float64)

        co = compute_cybernetic_oscillator_numba(series, self.p.hp_period, self.p.lp_period, 100)
        self.lines.coscillator[0] = co[-1]


    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < 100:
            return

        co = compute_cybernetic_oscillator_numba(series, self.p.hp_period, self.p.lp_period, 100)
        self.lines.coscillator.ndbuffer(co)
