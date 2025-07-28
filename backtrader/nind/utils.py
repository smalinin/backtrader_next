import numpy as np
import numba
import math


# JIT-compiled EMA computation
@numba.njit
def compute_ema_numba(closes, alpha, period):
    n = len(closes)
    result = np.empty(n, dtype=np.float64)
    result[:period - 1] = np.nan
    # Seed with simple average
    result[period - 1] = np.mean(closes[:period])
    # Recursive EMA
    for i in range(period, n):
        result[i] = alpha * closes[i] + (1 - alpha) * result[i - 1]
    return result

@numba.njit
def compute_sma_numba(closes, period):
    n = len(closes)
    result = np.empty(n, dtype=np.float64)
    cum = 0.0
    for i in range(n):
        cum += closes[i]
        if i >= period:
            cum -= closes[i - period]
        if i >= period - 1:
            result[i] = cum / period
        else:
            result[i] = np.nan
    return result


@numba.njit
def compute_ssf_numba(series, period):
    # Ehlers SuperSmoother filter
    # period: period of the filter
    n = len(series)
    filt = np.full(n, np.nan)

    if n < 2:
        return filt

    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / period)
    c2 = b1
    c3 = -a1 * a1
    c1 = 1 - c2 - c3

    filt[0] = series[0]
    filt[1] = series[1]
    for i in range(2, n):
        filt[i] = c1 * (series[i] + series[i - 1]) / 2 + c2 * filt[i - 1] + c3 * filt[i - 2]
    return filt


@numba.njit
def compute_hp_filter_numba(series, hp_period):
    # Ehlers High-pass filter
    alpha1 = (np.cos(1.414 * np.pi / hp_period) + np.sin(1.414 * np.pi / hp_period) - 1) / np.cos(1.414 * np.pi / hp_period)
    
    # High-pass filter calculation
    hp = np.zeros_like(series)
    for i in range(2, len(series)):
        hp[i] = ((1 - alpha1 / 2)**2 * (series[i] - 2 * series[i-1] + series[i-2]) +
                 2 * (1 - alpha1) * hp[i-1] -
                 (1 - alpha1)**2 * hp[i-2])
    return hp


@numba.njit
def compute_roofing_filter_numba(series, lp_period, hp_period):
    # Ehlers Roofing Filter:
    # 1. High-pass filter
    # 2. SuperSmoother filter on the result of the high-pass
    hp = compute_hp_filter_numba(series, hp_period)

    # Then apply SuperSmoother to HP result (low-pass)
    filt = compute_ssf_numba(hp, lp_period)
    return hp, filt


@numba.njit
def compute_ultimate_smoother_numba(closes, period):
    """
    John Ehlers Ultimate Smoother
    Formula: Filter = (c1 * (Price + Price[1])) / 2 + c2 * Filter[1] + c3 * Filter[2]
    where:
        a = exp(-1.414 * π / period)
        c2 = 2 * a * cos(1.414 * π / period)
        c3 = -a²
        c1 = 1.0 - c2 - c3
    """
    n = len(closes)
    result = np.empty(n, dtype=np.float64)
    
    if n < 3:
        result[:] = closes[:]
        return result
    
    # Ehlers coefficients
    a = math.exp(-1.414213562373095 * math.pi / period)
    c2 = 2.0 * a * math.cos(1.414213562373095 * math.pi / period)
    c3 = -a * a
    c1 = 1.0 - c2 - c3
    
    # Initialize first values
    result[0] = closes[0]
    result[1] = closes[1]
    result[2] = closes[2]
    
    # Calculate Ultimate Smoother values
    for i in range(3, n):
        price_avg = (closes[i] + closes[i-1]) / 2.0
        result[i] = c1 * price_avg + c2 * result[i-1] + c3 * result[i-2]
    
    return result





