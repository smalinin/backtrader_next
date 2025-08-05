import numpy as np
import numba
import backtrader as bt
from .utils import compute_ssf_numba

__all__ = ['DSMA']


@numba.njit
def rolling_rms_numba(filt, period):
    """Numba-jitted rolling Root Mean Square calculation."""
    n = len(filt)
    rms = np.full(n, np.nan)
    
    for i in range(period - 1, n):
        rms_val = 0.0
        for j in range(period):
            if i - j >= 0:
                rms_val += filt[i - j] ** 2
        rms[i] = np.sqrt(rms_val / period)
    
    return rms

@numba.njit
def compute_dsma_numba(series, period, k=5.0):
    """
    Calculates the Deviation-Scaled Moving Average (DSMA) using numba,
    based on John Ehlers' implementation.
    
    Args:
        series: Input data series (numpy array)
        period: Period for calculations
        k: Scaling factor (default 5.0)
    
    Returns:
        dsma: Deviation-Scaled Moving Average values
    """
    n = len(series)
    
    zeros = np.zeros_like(series)
    dsma = np.zeros_like(series)
    
    if n < 3:
        return dsma
    
    for i in range(2, n):
        diff = series[i] - series[i - 2]
        if np.isnan(diff) or np.isinf(diff):
            diff = 0.0
        zeros[i] = diff

    filt = compute_ssf_numba(zeros, period)
    rms = rolling_rms_numba(filt, period)
    
    dsma[0] = series[0] if n > 0 else 0.0
    
    for i in range(1, n):
        if i < period:
            dsma[i] = 0.0
        else:
            # Calculate adaptive alpha
            if rms[i] > 1e-9 and not np.isnan(rms[i]):
                alpha = np.abs(filt[i] / rms[i]) * k / period
            else:
                alpha = 0.0
                
            if np.isnan(alpha) or alpha < 0:
                alpha = 0.0
            if alpha > 1.0:
                alpha = 1.0
            
            # Apply adaptive EMA
            dsma_val = alpha * series[i] + (1.0 - alpha) * dsma[i - 1]
            
            if np.isnan(dsma_val):
                dsma_val = 0.0
                
            dsma[i] = dsma_val
    
    return dsma



class DSMA(bt.Indicator):
    '''
    Deviation-Scaled Moving Average (DSMA) by John Ehlers
    
    The DSMA is an adaptive moving average that adjusts its smoothing 
    based on the deviation of the filtered price data from its RMS value.
    
    Formula:
      1. Calculate 2-period price difference
      2. Apply SuperSmoother filter to the difference
      3. Calculate rolling RMS of the filtered values
      4. Calculate adaptive alpha = |filt[i] / rms[i]| * k / period
      5. Apply adaptive EMA: dsma[i] = alpha * price[i] + (1 - alpha) * dsma[i-1]
    '''
    lines = ('dsma',)
    params = (
        ('period', 40),
        ('k', 5.0),  # Scaling factor
    )
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.addminperiod(self.p.period + 2)  # +2 for the 2-period difference
        self.min_size = self.p.period * 20

    def next(self, status):
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)
        dsma_values = compute_dsma_numba(series, self.p.period, self.p.k)
        
        self.lines.dsma[0] = dsma_values[-1]

    def once(self, start, end):
        if end-start==1:
            return

        """Batch calculation for historical data."""
        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < self.p.period + 2:
            return

        dsma_values = compute_dsma_numba(series, self.p.period, self.p.k)
        self.lines.dsma.ndbuffer(dsma_values)
