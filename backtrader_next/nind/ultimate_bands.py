#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
from .utils import compute_ultimate_smoother_numba

__all__ = ['UltimateBands']


@numba.njit
def compute_ultimate_bands_numba(closes, length, num_sds):
    """
    Ultimate Bands Ehlers
    
    Inputs:
    - closes: price data
    - length: period for calculation (default 20)
    - num_sds: number of standard deviations (default 1)
    
    Formula:
    - Smooth = UltimateSmoother(Close, Length)
    - Sum = Sum of (Close[count] - Smooth[count])^2 for count 0 to Length-1
    - SD = SquareRoot(Sum / Length) if Sum != 0
    - UpperBand = Smooth + NumSDs * SD
    - LowerBand = Smooth - NumSDs * SD
    """
    n = len(closes)
    
    smooth = compute_ultimate_smoother_numba(closes, length)
    
    upper_band = np.full(n, np.nan)
    lower_band = np.full(n, np.nan)
    std_dev = np.full(n, np.nan)
    
    if n < length:
        return smooth, upper_band, lower_band, std_dev
            
    # Calculate bands for each point
    for i in range(length, n):
        # Calculate sum of squared differences over the period
        sum_sq = 0.0
        for count in range(length):
            if i - count >= 0:
                diff = closes[i - count] - smooth[i - count]
                sum_sq += diff * diff
        
        # Calculate standard deviation
        sd = 0.0
        if sum_sq != 0.0:
            sd = np.sqrt(sum_sq / length)
        
        std_dev[i] = sd
        
        # Calculate bands
        upper_band[i] = smooth[i] + num_sds * sd
        lower_band[i] = smooth[i] - num_sds * sd
    
    return smooth, upper_band, lower_band, std_dev


class UltimateBands(bt.Indicator):
    '''
    Ultimate Bands Ehlers
    
    The Ultimate Bands indicator uses John Ehlers' Ultimate Smoother to create
    adaptive bands based on standard deviation calculations.
    
    Formula:
    - Smooth = UltimateSmoother(Close, Length)
    - Sum = Sum of (Close[count] - Smooth[count])^2 for count 0 to Length-1  
    - SD = SquareRoot(Sum / Length) if Sum != 0
    - UpperBand = Smooth + NumSDs * SD
    - LowerBand = Smooth - NumSDs * SD
    
    The bands adapt to market volatility and provide dynamic support/resistance levels.
    '''
    lines = ('upperband', 'smooth', 'lowerband', 'stddev')
    params = (
        ('length', 20),      # Period for calculation
        ('num_sds', 1.0),    # Number of standard deviations
    )
    
    plotinfo = dict(subplot=False)
    plotlines = dict(
        upperband=dict(_name='Upper Band'),
        smooth=dict(_name='Smooth', _samecolor=True, ls='--'),
        lowerband=dict(_name='Lower Band', _samecolor=True),
        stddev=dict(_plotskip=True)  # Don't plot standard deviation by default
    )

    def __init__(self):
        # Minimum period needed
        self.addminperiod(max(self.p.length, 3))
        self.min_size = max(self.p.length, 3) * 20

    def next(self, status):
        """
        Calculate Ultimate Bands values for real-time data (bar by bar)
        """
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)
        
        smooth, upper_band, lower_band, std_dev = compute_ultimate_bands_numba(
            series, self.p.length, self.p.num_sds
        )
        
        if not np.isnan(smooth[-1]):
            self.lines.smooth[0] = smooth[-1]
            self.lines.upperband[0] = upper_band[-1] 
            self.lines.lowerband[0] = lower_band[-1]
            self.lines.stddev[0] = std_dev[-1]

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)

        smooth, upper_band, lower_band, std_dev = compute_ultimate_bands_numba(
            series, self.p.length, self.p.num_sds
        )

        self.lines.smooth.ndbuffer(smooth)
        self.lines.upperband.ndbuffer(upper_band)
        self.lines.lowerband.ndbuffer(lower_band) 
        self.lines.stddev.ndbuffer(std_dev)
