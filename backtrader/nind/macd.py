import numpy as np
import numba
import backtrader as bt
from .utils import compute_ema_numba

__all__ = ['MACD']

@numba.njit
def compute_macd_numba(closes, fast_alpha, fast_period, slow_alpha, slow_period, signal_alpha, signal_period):
    fast_ema = compute_ema_numba(closes, fast_alpha, fast_period)
    slow_ema = compute_ema_numba(closes, slow_alpha, slow_period)
    macd = fast_ema - slow_ema
    signal = compute_ema_numba(macd, signal_alpha, signal_period)
    hist = macd - signal
    return macd, signal, hist

class MACD(bt.Indicator):
    '''
    Moving Average Convergence Divergence

    Formula:
      - macd = ema(data, fast_period) - ema(data, slow_period)
      - signal = ema(macd, signal_period)
      - hist = macd - signal
    '''
    lines = ('macd', 'signal', 'hist')
    params = (
        ('fast_period', 12),
        ('slow_period', 26),
        ('signal_period', 9),
    )
    plotinfo = dict(plothlines=[0.0])
    plotlines = dict(signal=dict(ls='--'), 
                     hist=dict(_method='bar', alpha=0.5, width=1.0)
    		     )    

    def __init__(self):
        self.addminperiod(self.p.slow_period)
        self.fast_alpha = 2.0 / (self.p.fast_period + 1)
        self.slow_alpha = 2.0 / (self.p.slow_period + 1)
        self.signal_alpha = 2.0 / (self.p.signal_period + 1)
        self.min_size = max(self.p.fast_period, self.p.slow_period, self.p.signal_period) * 20 


    def next(self, status):
        closes = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)
        macd, signal, hist = compute_macd_numba(
            closes,
            self.fast_alpha, self.p.fast_period,
            self.slow_alpha, self.p.slow_period,
            self.signal_alpha, self.p.signal_period
        )

        self.lines.macd[0] = macd[-1]
        self.lines.signal[0] = signal[-1]
        self.lines.hist[0] = hist[-1]



    def once(self, start, end):
        if end - start == 1:
            return

        closes = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)

        macd, signal, hist = compute_macd_numba(
            closes,
            self.fast_alpha, self.p.fast_period,
            self.slow_alpha, self.p.slow_period,
            self.signal_alpha, self.p.signal_period
        )

        self.lines.macd.ndbuffer(macd)
        self.lines.signal.ndbuffer(signal)
        self.lines.hist.ndbuffer(hist)
