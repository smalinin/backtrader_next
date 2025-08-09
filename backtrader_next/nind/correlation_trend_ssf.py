import numpy as np
import numba
import backtrader as bt
from .utils import compute_ssf_numba

__all__ = ['CorrelationTrendSS']

@numba.njit
def compute_correlation_trend_ssf_numba(closes, length, lp_period):
    n = len(closes)
    corr = np.empty(n, dtype=np.float64)
    corr[:length-1] = np.nan
    
    filtered_closes = compute_ssf_numba(closes, lp_period)
    
    for i in range(length-1, n):
        # Calculate correlation for window ending at position i using filtered data
        sx = 0.0
        sy = 0.0
        sxx = 0.0
        sxy = 0.0
        syy = 0.0
        
        for count in range(length):
            x = filtered_closes[i - count]  # Filtered Close[count] in reverse order
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


class CorrelationTrendSS(bt.Indicator):
    '''
    Correlation Trend Indicator with SuperSmoother Filter by John F. Ehlers
    
    This indicator measures the correlation between filtered price and time.
    The prices are first processed through a SuperSmoother Filter 
    to remove market noise before calculating the correlation.
    
    A high positive correlation indicates a strong uptrend,
    while a high negative correlation indicates a strong downtrend.
    
    Formula:
      - First SuperSmoother filter
      - For each period, calculate correlation between filtered close prices and negative time index
      - Corr = (N*Sxy - Sx*Sy) / sqrt((N*Sxx - Sx*Sx) * (N*Syy - Sy*Sy))
      - Where X = Filtered Close prices, Y = -time_index
    '''
    lines = ('corr',)
    params = (
        ('length', 20),      # Correlation calculation period
        ('lp_period', 10),   # SuperSmoother filter period
    )
    
    plotinfo = dict(plothlines=[0.0])
    plotlines = dict(
        corr=dict(ls='-'),
    )

    def __init__(self):
        min_period = max(self.p.length, self.p.lp_period)
        self.addminperiod(min_period)
        self.min_size = min_period * 10

    def next(self, status):
        if len(self.data) < self.p.length:
            return
        
        closes = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)
        corr_value = compute_correlation_trend_ssf_numba(
            closes, self.p.length, self.p.lp_period)
        
        self.lines.corr[0] = corr_value[-1]

    def once(self, start, end):
        if end - start == 1:
            return

        closes = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(closes) < self.p.length:
            return

        correlation = compute_correlation_trend_ssf_numba(
            closes, self.p.length, self.p.lp_period)
        
        self.lines.corr.ndbuffer(correlation)
