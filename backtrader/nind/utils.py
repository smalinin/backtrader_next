import numpy as np
import numba


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
def compute_sma_numba(closes: np.ndarray, period: int):
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
    ssf = np.zeros(n, dtype=np.float64)

    if n < 2:
        return ssf

    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2.0 * a1 * np.cos(1.414 * np.pi / period)
    c2 = b1
    c3 = -a1 * a1
    c1 = 1.0 - c2 - c3

    ssf[0] = series[0]
    ssf[1] = series[1]

    for i in range(2, n):
        ssf[i] = c1 * (series[i] + series[i - 1]) / 2 + c2 * ssf[i - 1] + c3 * ssf[i - 2]
    return ssf


@numba.njit
def compute_hp2_filter_numba(series, hp_period):
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
    hp = compute_hp2_filter_numba(series, hp_period)

    # Then apply SuperSmoother to HP result (low-pass)
    roof = compute_ssf_numba(hp, lp_period)
    return roof


@numba.njit
def compute_highpass1_numba(series: np.ndarray, period: float) -> np.ndarray:
    """
        a1 = exp(-1.414 · π / period)
        b1 = 2 · a1 · cos(1.414 · π / period)
        c2 = b1
        c3 = -a1²
        c1 = (1 + c2 - c3) / 4

    HP[i] = 
      c1 * (series[i] - 2·series[i-1] + series[i-2]) 
      + c2·HP[i-1] + c3·HP[i-2]     , for i >= 4  
    HP[i] = series[i] , for i < 4
    """
    n = len(series)
    hp = np.zeros(n, np.float64)

    if n < 4:
        for i in range(n):
            hp[i] = series[i]
        return hp

    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2.0 * a1 * np.cos(1.414 * np.pi / period)
    c2 = b1
    c3 = -a1 * a1
    c1 = 0.25 * (1.0 + c2 - c3)

    hp[0] = hp[1] = hp[2] = hp[3] = 0.0

    for i in range(4, n):
        hp[i] = (
            c1 * (series[i] - 2.0 * series[i - 1] + series[i - 2])
            + c2 * hp[i - 1]
            + c3 * hp[i - 2]
        )

    return hp


@numba.njit
def compute_rms_numba(series) -> np.float64:
    """
    Root‑Mean‑Square  (RMS) of a 1D array.

    Equivalent to:
        sqrt(sum(series**2) / len(series))

    Uses a plain for-loop to ensure fast, type-specialized code under numba.njit.
    """

    n = len(series)
    if n == 0:
        return 0.0

    acc = 0.0
    for i in range(n):
        acc += series[i] * series[i]
    return np.sqrt(acc / n)


@numba.njit
def compute_ultimate_oscillator_numba(
    closes: np.ndarray,
    bandedge: float = 20.0,
    bandwidth: float = 2.0
) -> np.ndarray:
    """
    John Ehlers' Ultimate Oscillator (TASC Apr 2025).

    HP1 = HighPass(Close, bandwidth * bandedge)
    HP2 = HighPass(Close, bandedge)
    Signal = HP1 - HP2
    RMS    = RMS of Signal using fixed window 100 bars
    UltimateOsc = Signal / RMS   (if RMS ≠ 0)  else 0

    @returns: (UltimateOsc)
    """
    n = len(closes)
    uo = np.zeros(n, dtype=np.float64)
    signal = np.zeros(n, dtype=np.float64)
    rms = np.zeros(n, dtype=np.float64)

    # HP1, HP2 — high-pass filters
    hp1 = compute_highpass1_numba(closes, bandwidth * bandedge)
    hp2 = compute_highpass1_numba(closes, bandedge)

    # Signal = HP1 - HP2
    for i in range(n):
        signal[i] = hp1[i] - hp2[i]

    # Rolling RMS len=100
    acc = 0.0
    count = 0
    for i in range(n):
        acc += signal[i] * signal[i]
        count += 1
        if i >= 100:
            acc -= signal[i - 100] * signal[i - 100]
            count -= 1
        if count > 0:
            rms[i] = np.sqrt(acc / count)
        else:
            rms[i] = 0.0

        if rms[i] != 0.0:
            uo[i] = signal[i] / rms[i]
        else:
            uo[i] = 0.0

    return uo


@numba.njit
def compute_cybernetic_oscillator_numba0(
    closes: np.ndarray,
    hp_period: int = 30,
    lp_period: int = 20,
    rms_length: int = 100
) -> np.ndarray:
    """
    John Ehlers' Cybernetic Oscillator (TASC June 2025).

    HP = $HighPass(Close, HPLength);
    LP = $SuperSmoother(HP, LPLength);
    RMS = $RMS(LP, 100);

    if RMS <> 0 then 
        CyberneticOsc = LP / RMS;
    """
    n = len(closes)
    co = np.zeros(n, dtype=np.float64)
    rms = np.zeros(n, dtype=np.float64)

    hp = compute_highpass1_numba(closes, hp_period)
    lp = compute_ssf_numba(hp, lp_period)

    # Rolling RMS
    acc = 0.0
    count = 0
    for i in range(n):
        acc += lp[i] * lp[i]
        count += 1
        if i >= rms_length:
            acc -= lp[i - rms_length] * lp[i - rms_length]
            count -= 1

        rms[i] = np.sqrt(acc / count)

        if rms[i] != 0.0:
            co[i] = lp[i] / rms[i]
        else:
            co[i] = 0.0

    return co


@numba.njit
def compute_cybernetic_oscillator_numba(
    closes: np.ndarray,
    hp_period: int = 30,
    lp_period: int = 20,
    rms_length: int = 100
) -> np.ndarray:
    """
    John Ehlers' Cybernetic Oscillator (TASC June 2025).

    HP = $HighPass(Close, HPLength);
    LP = $SuperSmoother(HP, LPLength);
    RMS = $RMS(LP, 100);

    if RMS <> 0 then 
        CyberneticOsc = LP / RMS;
    """
    n = len(closes)
    co = np.zeros(n, dtype=np.float64)
    
    hp = compute_highpass1_numba(closes, hp_period)
    lp = compute_ssf_numba(hp, lp_period)
    
    # RMS = $RMS(LP, 100);
    for i in range(n):
        sum_sq = 0.0
        count = 0
        
        # Sum from the current bar backward across rms_length periods
        for j in range(min(i + 1, rms_length)):
            if i - j >= 0:
                sum_sq += lp[i - j] * lp[i - j]
                count += 1
        
        if count > 0:
            rms_val = np.sqrt(sum_sq / count)
        else:
            rms_val = 0.0
            
        # if RMS <> 0 then CyberneticOsc = LP / RMS;
        if rms_val != 0.0:
            co[i] = lp[i] / rms_val
        else:
            co[i] = 0.0
    
    return co


@numba.njit
def compute_laguerre_oscillator_numba(
    closes: np.ndarray,
    gama: float = 0.5,
    length: float = 30.0,
    rms_length: int = 100
) -> np.ndarray:
    """
    John Ehlers' Laguerre Oscillator (TASC Jul 2025).

    L0 = UltimateSmoother(Close, length)
    L1 = recursive Laguerre with gamma
    Signal = L0 - L1
    RMS    = rolling RMS of Signal over rms_length bars
    Osc    = Signal / RMS  (if RMS != 0) else 0

    @returns: Laguerre Oscillator array
    """
    n = len(closes)
    osc    = np.zeros(n, dtype=np.float64)
    L0     = compute_ultimate_smoother_numba(closes, length)
    L1     = np.zeros(n, dtype=np.float64)
    signal = np.zeros(n, dtype=np.float64)
    rms    = np.zeros(n, dtype=np.float64)

    # build L1 and Signal
    for i in range(1, n):
        # skip until L0 is valid
        if np.isnan(L0[i]) or np.isnan(L0[i-1]):
            continue
        L1[i] = -gama * L0[i] + L0[i-1] + gama * L1[i-1]
        signal[i] = L0[i] - L1[i]

    # rolling RMS over signal
    acc = 0.0
    count = 0
    for i in range(n):
        acc += signal[i] * signal[i]
        count += 1
        if i >= rms_length:
            acc -= signal[i - rms_length] * signal[i - rms_length]
            count -= 1
        # compute RMS
        if count > 0:
            rms[i] = np.sqrt(acc / count)
        else:
            rms[i] = 0.0
        # compute oscillator
        if rms[i] != 0.0:
            osc[i] = signal[i] / rms[i]
        else:
            osc[i] = 0.0

    return osc


@numba.njit
def compute_ultimate_smoother_numba(series, period):
    n = len(series)
    us = np.full(n, np.nan) #np.full(n, np.nan)

    if n < 4:
        return us

    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2.0 * a1 * np.cos(1.414 * np.pi / period)
    c2 = b1
    c3 = -a1 * a1
    c1 = (1 + c2 - c3) / 4

    # Initialize first values
    us[0] = series[0]
    us[1] = series[1]
    us[2] = series[2]

    us[3] = (1 - c1) * series[3] + (2 * c1 - c2) * series[2] - (c1 + c3) * series[1] + c2 * us[2] + c3 * us[1]

    for i in range(4, n):
        us[i] = (1 - c1) * series[i] + (2 * c1 - c2) * series[i - 1] - (c1 + c3) * series[i - 2] + c2 * us[i - 1] + c3 * us[i - 2]

    return us


@numba.njit
def compute_laguerre_filter_numba(close, gama=0.8, length=40):
    n = len(close)
    laguerre = np.full(n, np.nan)
    L0 = compute_ultimate_smoother_numba(close, length)
    L1 = np.full(n, 0.0)
    L2 = np.full(n, 0.0)
    L3 = np.full(n, 0.0)
    L4 = np.full(n, 0.0)

    for i in range(1, n):
        if np.isnan(L0[i - 1]):
            continue

        L1[i] = -gama * L0[i - 1] + L0[i - 1] + gama * L1[i - 1]
        L2[i] = -gama * L1[i - 1] + L1[i - 1] + gama * L2[i - 1]
        L3[i] = -gama * L2[i - 1] + L2[i - 1] + gama * L3[i - 1]
        L4[i] = -gama * L3[i - 1] + L3[i - 1] + gama * L4[i - 1]

        laguerre[i] = (L0[i] + 4 * L1[i] + 6 * L2[i] + 4 * L3[i] + L4[i]) / 16.0

    return laguerre, L0
