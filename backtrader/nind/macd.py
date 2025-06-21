import numpy as np
import numba
import backtrader as bt

__all__ = ['MACD']

# JIT-compiled EMA computation
@numba.njit
def compute_ema_numba(closes, alpha, period):
    n = len(closes)
    result = np.empty(n, dtype=np.float64)
    result[:period - 1] = np.nan
    result[period - 1] = np.mean(closes[:period])
    for i in range(period, n):
        result[i] = alpha * closes[i] + (1 - alpha) * result[i - 1]
    return result

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
        self.addminperiod(self.p.slow_period + self.p.signal_period)
        self.fast_alpha = 2.0 / (self.p.fast_period + 1)
        self.slow_alpha = 2.0 / (self.p.slow_period + 1)
        self.signal_alpha = 2.0 / (self.p.signal_period + 1)
        self._fast_ema = None
        self._slow_ema = None
        self._macd = None
        self._signal_ema = None


    def next(self):
        price = self.data[0]

        if len(self.data) == self.p.slow_period:
            closes = self.data.get(size=self.p.slow_period)
            fast_seed = np.mean(closes[-self.p.fast_period:])
            slow_seed = np.mean(closes)
            macd = fast_seed - slow_seed
            self.lines.macd[0] = macd

        elif len(self.data) > self.p.slow_period:
            self._fast_ema = self.fast_alpha * price + (1 - self.fast_alpha) * self._fast_ema
            self._slow_ema = self.slow_alpha * price + (1 - self.slow_alpha) * self._slow_ema
            self._macd = self._fast_ema - self._slow_ema
            self._signal_ema = self.signal_alpha * self._macd + (1 - self.signal_alpha) * self._signal_ema

            self.lines.macd[0] = self._macd
            self.lines.signal[0] = self._signal_ema
            self.lines.hist[0] = self._macd - self._signal_ema


    def once(self, start, end):
        if end - start == 1:
            return

        closes = np.asarray(self.data.array, dtype=np.float64)
        if len(closes) < self.p.slow_period + self.p.signal_period:
            return

        macd, signal, hist = compute_macd_numba(
            closes,
            self.fast_alpha, self.p.fast_period,
            self.slow_alpha, self.p.slow_period,
            self.signal_alpha, self.p.signal_period
        )

        self.lines.macd.ndbuffer(macd)
        self.lines.signal.ndbuffer(signal)
        self.lines.hist.ndbuffer(hist)
