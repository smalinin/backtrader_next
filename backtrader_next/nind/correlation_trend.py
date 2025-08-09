#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt

__all__ = ['CorrelationTrend']

@numba.njit
def compute_correlation_trend_numba(closes, length):
    n = len(closes)
    corr = np.empty(n, dtype=np.float64)
    corr[:length-1] = np.nan
    
    for i in range(length-1, n):
        # Calculate correlation for window ending at position i
        sx = 0.0
        sy = 0.0
        sxx = 0.0
        sxy = 0.0
        syy = 0.0
        
        for count in range(length):
            x = closes[i - count]  # Close[count] in reverse order
            y = -count  # Y = -count
            sx += x
            sy += y
            sxx += x * x
            sxy += x * y
            syy += y * y
        
        denom_x = length * sxx - sx * sx
        denom_y = length * syy - sy * sy
        
        if denom_x > 0 and denom_y > 0:
            corr[i] = (length * sxy - sx * sy) / np.sqrt(denom_x * denom_y)
        else:
            corr[i] = 0.0
    return corr


class CorrelationTrend(bt.Indicator):
    '''
    Correlation Trend Indicator by John F. Ehlers
    
    This indicator measures the correlation between price and time.
    A high positive correlation indicates a strong uptrend,
    while a high negative correlation indicates a strong downtrend.
    
    Formula:
      - For each period, calculate correlation between close prices and negative time index
      - Corr = (N*Sxy - Sx*Sy) / sqrt((N*Sxx - Sx*Sx) * (N*Syy - Sy*Sy))
      - Where X = Close prices, Y = -time_index
    '''
    lines = ('corr',)
    params = (
        ('length', 20),
    )
    
    plotinfo = dict(plothlines=[0.0])
    plotlines = dict(corr=dict(ls='-'),
                     )    

    def __init__(self):
        self.addminperiod(self.p.length)


    def next(self, status):
        if len(self.data) < self.p.length:
            return
        
        closes = np.asarray(self.data.get_array(self.p.length), dtype=np.float64)
        CORR = compute_correlation_trend_numba(closes, self.p.length)
        self.lines.corr[0] = CORR[-1]
            

    def once(self, start, end):
        if end - start == 1:
            return

        closes = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(closes) < self.p.length:
            return

        correlation = compute_correlation_trend_numba(closes, self.p.length)
        
        self.lines.corr.ndbuffer(correlation)

