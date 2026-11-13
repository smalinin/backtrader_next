#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
from .utils import compute_ema_numba

__all__ = ['MACD']

@numba.njit
def compute_macd_numba(closes, fast_alpha, fast_period, slow_alpha, slow_period, signal_alpha, signal_period):
    if fast_period < 1 or slow_period < 1 or signal_period < 1:
        raise ValueError('MACD periods must be positive')

    n = len(closes)
    signal = np.full(n, np.nan, dtype=np.float64)
    macd_period = max(fast_period, slow_period)
    if n < macd_period:
        macd = np.full(n, np.nan, dtype=np.float64)
        return macd, signal, macd - signal

    fast_ema = compute_ema_numba(closes, fast_alpha, fast_period)
    slow_ema = compute_ema_numba(closes, slow_alpha, slow_period)
    macd = fast_ema - slow_ema

    # Seed the signal EMA using valid MACD values after both price EMAs warm up.
    signal_start = macd_period - 1
    if n - signal_start >= signal_period:
        signal[signal_start:] = compute_ema_numba(
            macd[signal_start:], signal_alpha, signal_period,
        )
    hist = macd - signal
    return macd, signal, hist

class MACD(bt.Indicator):
    '''
    Moving Average Convergence Divergence

    Formula:
      - macd = ema(data, fast_period) - ema(data, slow_period)
      - signal = ema(macd, signal_period)
      - hist = macd - signal

    The MACD line starts after max(fast_period, slow_period) bars. Signal and
    histogram require another signal_period - 1 bars; earlier values are NaN.
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
        if self.p.fast_period < 1 or self.p.slow_period < 1 or self.p.signal_period < 1:
            raise ValueError('MACD periods must be positive')
        self._macd_period = max(self.p.fast_period, self.p.slow_period)
        self.addminperiod(self._macd_period + self.p.signal_period - 1)
        self.fast_alpha = 2.0 / (self.p.fast_period + 1)
        self.slow_alpha = 2.0 / (self.p.slow_period + 1)
        self.signal_alpha = 2.0 / (self.p.signal_period + 1)
        self.min_size = max(self.p.fast_period, self.p.slow_period, self.p.signal_period) * 20 

    def prenext(self):
        # The MACD line becomes available before its signal and histogram.
        if len(self.data) >= self._macd_period:
            self.next()


    def next(self):
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
        # Skip only oncestart: the main once call fills the entire history,
        # even when there is just one bar after the minimum period.
        if start == self._minperiod - 1:
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
