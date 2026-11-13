"""
Average True Range (ATR) indicator for Aurora
"""

import numpy as np
from backtrader_next.aurora.indicator import AuroraIndicator


class ATR(AuroraIndicator):
    """
    Average True Range
    
    ATR measures market volatility by calculating the average of true ranges
    over a specified period.
    
    Formula:
        True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ATR = EMA(True Range, period)
    
    Lines:
        - atr: The Average True Range line
    
    Params:
        - period (default: 14): Period for ATR calculation
    """
    
    lines = ('atr',)
    params = (('period', 14),)
    
    def __init__(self):
        super(ATR, self).__init__()
        self.addminperiod(self.p.period + 1)  # Need previous close
    
    def once(self, start, end):
        """
        Vectorized calculation of ATR using NumPy.

        NOTE: warm-up is always computed from index 0 regardless of `start`,
        because _once() calls once(minperiod, end) which skips the warm-up
        region. We compute the full TR array and initialize ATR properly.

        Args:
            start: Starting index for calculation (used only for EMA phase)
            end: Ending index (exclusive)
        """
        high = self.data.high.array
        low = self.data.low.array
        close = self.data.close.array
        dst = self.lines.atr.array

        period = self.p.period
        k = 1.0 / period  # Wilder's smoothing factor

        # --- Step 1: compute True Range for all bars 0..end-1 ---
        tr = np.empty(end)
        tr[0] = high[0] - low[0]
        for i in range(1, end):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr[i] = hl if hl >= hc and hl >= lc else (hc if hc >= lc else lc)

        # --- Step 2: first ATR = simple average of first `period` TRs ---
        init_idx = period - 1  # index where first valid ATR lives
        if end <= init_idx:
            return  # not enough data
        total = 0.0
        for i in range(period):
            total += tr[i]
        dst[init_idx] = total / period

        # --- Step 3: Wilder's EMA from init_idx+1 to end-1 ---
        for i in range(init_idx + 1, end):
            dst[i] = dst[i - 1] + k * (tr[i] - dst[i - 1])
    
    def next(self):
        """
        Fallback bar-by-bar calculation (used only when once() is not available).
        """
        period = self.p.period
        k = 1.0 / period

        if len(self) <= period:
            # Warm-up: accumulate TR values and compute simple average
            high = self.data.high.array
            low = self.data.low.array
            close = self.data.close.array
            idx = len(self) - 1  # current absolute index (0-based)
            tr_sum = 0.0
            for j in range(idx + 1):
                if j == 0:
                    tr_sum += high[j] - low[j]
                else:
                    hl = high[j] - low[j]
                    hc = abs(high[j] - close[j - 1])
                    lc = abs(low[j] - close[j - 1])
                    tr_sum += max(hl, hc, lc)
            self.lines.atr[0] = tr_sum / (idx + 1)
        else:
            # Calculate True Range
            tr1 = self.data.high[0] - self.data.low[0]
            tr2 = abs(self.data.high[0] - self.data.close[-1])
            tr3 = abs(self.data.low[0] - self.data.close[-1])
            tr = max(tr1, tr2, tr3)
            # Wilder's smoothing
            self.lines.atr[0] = self.lines.atr[-1] + k * (tr - self.lines.atr[-1])
