"""
Bollinger Bands indicator for Aurora
"""

import numpy as np
from backtrader_next.aurora.indicator import AuroraIndicator


class BollingerBands(AuroraIndicator):
    """
    Bollinger Bands
    
    Bollinger Bands consist of:
    - Middle Band: Simple Moving Average (SMA)
    - Upper Band: SMA + (standard deviation × multiplier)
    - Lower Band: SMA - (standard deviation × multiplier)
    
    Formula:
        Middle = SMA(close, period)
        Upper = Middle + (stddev × devfactor)
        Lower = Middle - (stddev × devfactor)
    
    Lines:
        - mid: The middle band (SMA)
        - top: The upper band
        - bot: The lower band
    
    Params:
        - period (default: 20): Period for SMA and standard deviation
        - devfactor (default: 2.0): Number of standard deviations
    """
    
    lines = ('mid', 'top', 'bot')
    params = (
        ('period', 20),
        ('devfactor', 2.0),
    )
    
    def __init__(self):
        super(BollingerBands, self).__init__()
        self.addminperiod(self.p.period)
    
    def once(self, start, end):
        """
        Vectorized calculation of Bollinger Bands using NumPy.

        NOTE: warm-up bar (index period-1) is computed unconditionally
        because _once() calls once(period, end), skipping index period-1.

        Args:
            start: Starting index (used for EMA-like phases; here we always
                   start from period-1 to ensure the first band is filled)
            end: Ending index (exclusive)
        """
        src = self.data.close.array
        mid_line = self.lines.mid.array
        top_line = self.lines.top.array
        bot_line = self.lines.bot.array

        period = self.p.period
        devfactor = self.p.devfactor

        # Always compute from the first valid index (period-1) to end
        for i in range(period - 1, end):
            window = src[i - period + 1:i + 1]

            # Middle band (SMA)
            mid_line[i] = np.mean(window)

            # Standard deviation (population, ddof=0 — Bollinger standard)
            std = np.std(window, ddof=0)

            # Upper and lower bands
            top_line[i] = mid_line[i] + (std * devfactor)
            bot_line[i] = mid_line[i] - (std * devfactor)
    
    def next(self):
        """
        Fallback calculation for single bar
        """
        if len(self) >= self.p.period:
            # Get last 'period' values
            values = [self.data.close[-j] for j in range(self.p.period)]
            
            # Calculate middle (SMA)
            mid = sum(values) / self.p.period
            self.lines.mid[0] = mid
            
            # Calculate standard deviation (population, ddof=0)
            variance = sum((x - mid) ** 2 for x in values) / self.p.period
            std = variance ** 0.5
            
            # Calculate bands
            self.lines.top[0] = mid + (std * self.p.devfactor)
            self.lines.bot[0] = mid - (std * self.p.devfactor)
