from typing import Tuple
import numpy as np
import numba
import backtrader as bt
from .utils import compute_roofing_filter_numba, compute_ssf_numba

__all__ = ['MESAStochastic']


@numba.njit
def mm_scalar(
    series: np.ndarray,
    idx: int,
    period: int
) -> (np.float64, np.float64,):
    """
    Returns (min, max) in the range series[idx-period+1 : idx+1].
    For idx < period-1: stretched window.
    """
    if period < 1:
        return series[idx], series[idx]
    start = idx - (period - 1)
    if start < 0:
        start = 0
    mn = series[start]
    mx = series[start]
    for j in range(start + 1, idx + 1):
        v = series[j]
        if v < mn:
            mn = v
        if v > mx:
            mx = v
    return mn, mx


@numba.njit
def compute_mesa_stochastic_numba(
    closes,
    period: int = 20,
    lp_period: float = 10.0,
    hp_period: float = 48.0
) -> np.ndarray:
    """
    MESA Stochastic (Ehlers, TASC 01.2014 – WealthLab Implementation):

    1. roofing = compute_roofing_filter(closes, lp_period, hp_period)
    2. LL = lowest value of roofing period
    3. HH = highest value of roofing period
    4. stoc[i] = (roofing[i] - LL) / (HH - LL), or 0 if HH == LL
    5. mesa = SuperSmoother(stoc, period=lp_period) * 100 ? [?0?100]
    """
    n = len(closes)
    mesa = np.zeros(n, np.float64)

    if n == 0:
        return mesa

    roofing = compute_roofing_filter_numba(closes, lp_period, hp_period)

    stoch = np.zeros(n, np.float64)
    for i in range(n):
        mn, mx = mm_scalar(roofing, i, period)
        dn = mx - mn
        if dn != 0.0:
            stoch[i] = (roofing[i] - mn) / dn
        else:
            stoch[i] = 0.0

    mesa = compute_ssf_numba(stoch, 10)
    mesa *= 100.0
    return mesa


class MESAStochastic(bt.Indicator):
    '''
    Ehlers Roofing Filter

    Formula:
      - High-pass filter
      - SuperSmoother filter on the result of the high-pass
    '''
    lines = ('stoch', )
    params = (
        ('period', 20),  # Stoch period
        ('lp_period', 10),  # Low-pass (SuperSmoother) period
        ('hp_period', 48),  # High-pass period
    )

    def __init__(self):
        self.addminperiod(self.p.period) # Minimum period for calculation
        self.min_size = self.p.hp_period * 20 
        

    def next(self, status):
        series = np.asarray(self.data.get_array(self.min_size), dtype=np.float64)

        mesa = compute_mesa_stochastic_numba(series, self.p.period,
            self.p.lp_period, self.p.hp_period
        )
        self.lines.stoch[0] = mesa[-1]


    def once(self, start, end):
        if end-start==1:
            return

        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        if len(series) < self.p.hp_period:
            return

        mesa = compute_mesa_stochastic_numba(series, self.p.period,
            self.p.lp_period, self.p.hp_period
        )

        self.lines.stoch.ndbuffer(mesa)
