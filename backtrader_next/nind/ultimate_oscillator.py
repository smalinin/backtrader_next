import numpy as np
import numba
import backtrader as bt
from .utils import compute_ultimate_oscillator_numba

__all__ = ['UltimateOscillator']


class UltimateOscillator(bt.Indicator):
    '''
    John Ehlers' Ultimate Oscillator (TASC Apr 2025).

    HP1 = HighPass(Close, bandwidth * bandedge)
    HP2 = HighPass(Close, bandedge)
    Signal = HP1 - HP2
    RMS    = RMS of Signal using fixed window 100 bars
    UltimateOsc = Signal / RMS   (if RMS ≠ 0)  else 0
    '''
    lines = ('uoscillator',)
    params = (
        ('bandedge', 20),
        ('bandwidth', 2),
    )
    plotinfo = dict(plothlines=[0.0])
    plotlines = dict(corr=dict(ls='-'),)

    def __init__(self):
        self.addminperiod(100)
        self.min_size = 100 + self.p.bandedge * 20
        
    def next(self, status):
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)

        uo = compute_ultimate_oscillator_numba(series, self.p.bandedge, self.p.bandwidth)
        self.lines.uoscillator[0] = uo[-1]


    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        uo = compute_ultimate_oscillator_numba(series, self.p.bandedge, self.p.bandwidth)
        
        self.lines.uoscillator.ndbuffer(uo)
