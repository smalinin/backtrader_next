#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import numpy as np
import numba
import backtrader_next as bt
from .utils import compute_ultimate_smoother_numba

__all__ = ['UltimateChannel']


@numba.njit
def compute_ultimate_channel_numba(closes, highs, lows, str_length, length, num_strs):
    """
    Ultimate Channel Ehlers
    
    Formula from EasyLanguage:
    If Close[1] > High Then TH = Close[1] Else TH = High;
    If Close[1] < Low Then TL = Close[1] Else TL = Low;
    STR = $UltimateSmoother(TH - TL, STRLength);
    UpperChnl = $UltimateSmoother(Close, Length) + NumSTRs*STR;
    LowerChnl = $UltimateSmoother(Close, Length) - NumSTRs*STR;
    """
    n = len(closes)
    
    # Calculate True High and True Low
    true_range = np.empty(n, dtype=np.float64)
    true_range[0] = highs[0] - lows[0]
    
    # Initialize first values
    th = highs[0]
    tl = lows[0]
    
    for i in range(1, n):
        # TH = max(high, previous close)
        if closes[i-1] > highs[i]:
            th = closes[i-1]
        else:
            th = highs[i]
            
        # TL = min(low, previous close)  
        if closes[i-1] < lows[i]:
            tl = closes[i-1]
        else:
            tl = lows[i]
            
        true_range[i] = th - tl
    
    # Calculate STR using Ultimate Smoother on True Range
    str_values = compute_ultimate_smoother_numba(true_range, str_length)
    
    smoothed_close = compute_ultimate_smoother_numba(closes, length)
    
    upper_channel = np.empty(n, dtype=np.float64)
    lower_channel = np.empty(n, dtype=np.float64)
    
    #for i in range(n):
    #    upper_channel[i] = smoothed_close[i] + num_strs * str_values[i]
    #    lower_channel[i] = smoothed_close[i] - num_strs * str_values[i]
    upper_channel = smoothed_close + num_strs * str_values
    lower_channel = smoothed_close - num_strs * str_values
    
    return upper_channel, lower_channel, smoothed_close, str_values


class UltimateChannel(bt.Indicator):
    '''
    Ultimate Channel Ehlers
    
    The Ultimate Channel creates dynamic support and resistance levels based on
    John Ehlers' Ultimate Smoother and True Range calculations.
    
    Formula (from EasyLanguage):
      - TH = max(High, Close[1])
      - TL = min(Low, Close[1])  
      - STR = UltimateSmoother(TH - TL, STRLength)
      - UpperChnl = UltimateSmoother(Close, Length) + NumSTRs * STR
      - LowerChnl = UltimateSmoother(Close, Length) - NumSTRs * STR
    
    Lines:
      - upper: Upper channel line
      - lower: Lower channel line
      - middle: Middle line (smoothed close)
      - str: Smoothed True Range
    '''
    lines = ('upper', 'middle', 'lower', 'str_')
    params = (
        ('str_length', 20),    # STRLength parameter
        ('length', 20),        # Length parameter for close smoothing
        ('num_strs', 1.0),     # NumSTRs multiplier
    )
    
    plotinfo = dict(
        subplot=False,
        plotname='Ultimate Channel',
        plotlinelabels=True,
    )
    
    plotlines = dict(
        upper=dict(ls='-', _name='Upper'),
        lower=dict(ls='-', _name='Lower', _samecolor=True),
        middle=dict(ls='--', _name='Middle', _samecolor=True),
        str_=dict(color='gray', ls='--', _name='STR', subplot=True, _plotskip=True),
    )

    def __init__(self):
        self.addminperiod(max(self.p.str_length, self.p.length, 3))
        self.min_size = max(self.p.str_length, self.p.length, 3) * 20

    def next(self, status):
        closes = np.asarray(self.data.close.get_array(self.min_size), dtype=np.float64)

        highs = np.asarray(self.data.high.get_array(self.min_size), dtype=np.float64)
        lows = np.asarray(self.data.low.get_array(self.min_size), dtype=np.float64)
            
        upper, lower, middle, str_val = compute_ultimate_channel_numba(
            closes, highs, lows, 
            self.p.str_length, self.p.length, self.p.num_strs
        )
        
        self.lines.upper[0] = upper[-1]
        self.lines.lower[0] = lower[-1]
        self.lines.middle[0] = middle[-1]
        self.lines.str_[0] = str_val[-1]

    def once(self, start, end):
        if end-start==1:
            return

        closes = np.asarray(self.data.close.get_array_preloaded(), dtype=np.float64)
        highs = np.asarray(self.data.high.get_array_preloaded(), dtype=np.float64)
        lows = np.asarray(self.data.low.get_array_preloaded(), dtype=np.float64)
        
        upper, lower, middle, str_values = compute_ultimate_channel_numba(
            closes, highs, lows,
            self.p.str_length, self.p.length, self.p.num_strs
        )
        
        self.lines.upper.ndbuffer(upper)
        self.lines.lower.ndbuffer(lower)
        self.lines.middle.ndbuffer(middle)
        self.lines.str_.ndbuffer(str_values)
