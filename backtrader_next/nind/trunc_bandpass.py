#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt

__all__ = ['TruncBandPass']

@numba.njit
def compute_trunc_bandpass_numba(prices, period, bandwidth, length):
    n = len(prices)
    trunc = np.zeros(n, np.float64)
    if n < max(period, length):
        return trunc
    
    # Precompute constants
    L1 = np.cos(2 * np.pi / period)
    G1 = np.cos(bandwidth * 2 * np.pi / period)
    S1 = 1.0 / G1 - np.sqrt(1.0 / (G1 * G1) - 1.0) if G1 != 0 else 0.0
    
    # Temporary buffer for calculations
    trunc_buf = np.zeros(101, np.float64)
    
    for i in range(max(period, length) - 1, n):
        # Shift buffer to the right
        for idx in range(100, 1, -1):
            trunc_buf[idx] = trunc_buf[idx - 1]

        
        # Reset positions
        trunc_buf[length + 1] = 0.0
        trunc_buf[length + 2] = 0.0
        
        # Compute truncated values
        for count in range(length, 0, -1):
            idx = i - count + 1
            if count + 2 < 101 and idx - 2 >= 0 and idx < n:
                trunc_buf[count] = (
                    0.5 * (1.0 - S1) * (prices[idx] - prices[idx - 2]) +
                    L1 * (1.0 + S1) * trunc_buf[count + 1] -
                    S1 * trunc_buf[count + 2]
                )
        trunc[i] = trunc_buf[1]
    return trunc

class TruncBandPass(bt.Indicator):
    lines = ('trunc',)
    params = (
        ('period', 20),
        ('bandwidth', 0.1),
        ('length', 10),
    )

    def __init__(self):
        # Validate parameters
        self.p.period = max(self.p.period, 3)
        self.p.length = min(max(self.p.length, 1), 98)  # 1-98 to fit in buffer
        min_period = max(self.p.period, self.p.length, 2)
        self.addminperiod(min_period)

        # Initialize calculation buffer
        self.trunc_buf = [0.0] * 101
        self.min_size = min_period * 5

    def next(self, status):
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)
        TBP = compute_trunc_bandpass_numba(
                series, self.p.period, self.p.bandwidth, self.p.length)
        self.lines.trunc[0] = TBP[-1]

    def once(self, start, end):
        if end-start==1:
            return

        """Bulk processing with Numba acceleration"""
        series = np.array(self.data.get_array_preloaded(), dtype=np.float64)
        BPT = compute_trunc_bandpass_numba(
            series,
            self.p.period,
            self.p.bandwidth,
            self.p.length
        )
        self.lines.trunc.ndbuffer(BPT)
