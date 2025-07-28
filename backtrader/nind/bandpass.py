import math
import numpy as np
import numba
import backtrader as bt

__all__ = ['BandPass']

@numba.njit
def compute_bandpass_numba(prices, period, bandwidth):
    n = len(prices)
    bandpass = np.zeros(n, dtype=np.float64)

    if n < period + 2:
        return bandpass
    
    # Precompute constants
    L1 = math.cos(2 * math.pi / period)
    G1 = math.cos(bandwidth * 2 * math.pi / period)
    S1 = 1.0 / G1 - math.sqrt(1.0 / (G1 * G1) - 1.0) if G1 != 0 else 0.0
    
    # Start calculation from period+1 index
    # for i in range(period + 1, n):
    for i in range(2, n):
        bandpass[i] = (
            0.5 * (1.0 - S1) * (prices[i] - prices[i - 2]) +
            L1 * (1.0 + S1) * bandpass[i - 1] -
            S1 * bandpass[i - 2]
        )
    return bandpass

class BandPass(bt.Indicator):
    lines = ('bandpass',)
    params = (
        ('period', 20),
        ('bandwidth', 0.1),
    )

    def __init__(self):
        # Validate and adjust parameters
        self.p.period = max(self.p.period, 3)
        self.addminperiod(self.p.period + 2)  # Minimum required bars

        
    def next(self, status):
        series = np.asarray(self.data.get_array(), dtype=np.float64)

        BP = compute_bandpass_numba(
                  series, self.p.period, self.p.bandwidth)
        self.lines.bandpass[0] = BP[-1]

    def once(self, start, end):
        if end-start==1:
            return

        """Bulk processing for historical data using Numba acceleration"""
        # Convert to numpy array for efficient processing
        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < 3:
            return
        
        # Compute entire bandpass array
        BP = compute_bandpass_numba(
            series, self.p.period, self.p.bandwidth)
        
        # Assign results to indicator line
        self.lines.bandpass.ndbuffer(BP)

