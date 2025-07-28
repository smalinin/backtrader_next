import backtrader as bt
import numpy as np
import numba

__all__ = ['InstantaneousTrendline']

@numba.njit
def compute_instantaneous_trend_numba(series, c1, c2, c3, c4, c5):
    n = len(series)
    trend = np.empty(n, dtype=np.float64)
    if n > 0:
        trend[0] = series[0]
    if n > 1:
        trend[1] = series[1]
    
    for i in range(2, n):
        trend[i] = (c1 * series[i] +
                    c2 * series[i - 1] +
                    c3 * series[i - 2] +
                    c4 * trend[i - 1] +
                    c5 * trend[i - 2])
    return trend

class InstantaneousTrendline(bt.Indicator):
    """
    Instantaneous Trendline Indicator
    """
    lines = ('trend',)
    params = (('alpha', 0.07),)
    plotinfo = dict(subplot=False)

    def __init__(self):
        # Pre-calculate coefficients for the formula
        alpha = self.p.alpha
        self.c1 = alpha - (alpha ** 2) / 4.0
        self.c2 = 0.5 * (alpha ** 2)
        self.c3 = -(alpha - 0.75 * (alpha ** 2))
        self.c4 = 2 * (1 - alpha)
        self.c5 = -((1 - alpha) ** 2)
        self.addminperiod(3)
        self.min_size = round((2/self.p.alpha - 1) * 5)

    def next(self, status):
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)

        trend = compute_instantaneous_trend_numba(
            series, self.c1, self.c2, self.c3, self.c4, self.c5
        )
        self.lines.trend[0] = trend[-1]

    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        trend = compute_instantaneous_trend_numba(
            series, self.c1, self.c2, self.c3, self.c4, self.c5
        )
        self.lines.trend.ndbuffer(trend)

