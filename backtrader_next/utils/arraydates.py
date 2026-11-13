"""Batch conversions with the scalar dateintern rounding conventions."""

from datetime import timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .dateintern import date2num, num2date


_EPOCH = 719163  # datetime(1970, 1, 1).toordinal()
_LAST_ORDINAL = 3652059  # datetime(9999, 12, 31).toordinal()
_DAY_US = 86_400_000_000


def date2num_array(values):
    """Convert a DatetimeIndex, preserving date2num's float results exactly.

    DatetimeIndex stores aware timestamps in UTC. Conversion to microseconds
    also reproduces to_pydatetime's truncation of nanoseconds. Near float
    rounding boundaries, use the scalar component-wise fsum rather than risk
    changing a feed clock by one ULP.
    """
    index = pd.DatetimeIndex(values)
    if index.hasnans:
        raise ValueError('NaT values detected in datetime input')
    tz = index.tz
    if tz is not None and not (
            isinstance(tz, ZoneInfo) or type(tz).__module__.split('.')[0] == 'pytz'
            or (isinstance(tz, timezone) and not tz.utcoffset(None).microseconds)):
        # Pandas' Python conversion can differ from its UTC storage for custom
        # tzinfo implementations, notably subsecond fixed offsets.
        return np.fromiter((date2num(value) for value in index.to_pydatetime()),
                           dtype=np.float64, count=len(index))
    micros = index.as_unit('us').asi8
    days, remainder = np.divmod(micros, _DAY_US)
    ordinal = days.astype(np.float64) + _EPOCH
    fraction = remainder / float(_DAY_US)
    result = ordinal + fraction
    # The component divisions in date2num and the combined fraction can differ
    # by less than four epsilons. Subtracting these nearby values is exact.
    residual = fraction - (result - ordinal)
    uncertain = (np.spacing(ordinal) * 0.5 - np.abs(residual)
                 <= 4 * np.finfo(np.float64).eps)
    uncertain |= (ordinal < 1) | (ordinal > _LAST_ORDINAL)
    if uncertain.any():
        selected = index[uncertain].to_pydatetime()
        result[uncertain] = np.fromiter((date2num(value) for value in selected),
                                       dtype=np.float64, count=len(selected))
    return result


def num2datetime_array(values):
    """Convert numeric dates to datetime64[us] as scalar num2date(tz=None)."""
    values = np.asarray(values, dtype=np.float64)
    invalid = ~np.isfinite(values) | (values < 1) | (values >= _LAST_ORDINAL + 1)
    if invalid.any():
        # Preserve scalar exception types for invalid/out-of-range values.
        return np.array([num2date(value) for value in values], dtype='datetime64[us]')
    ordinal = values.astype(np.int64)
    hour, remainder = np.divmod(24.0 * (values - ordinal), 1.0)
    minute, remainder = np.divmod(60.0 * remainder, 1.0)
    second, remainder = np.divmod(60.0 * remainder, 1.0)
    micros = (1_000_000.0 * remainder).astype(np.int64)
    micros[micros < 10] = 0
    micros[micros > 999990] = 1_000_000
    result = ((ordinal - _EPOCH) * _DAY_US
              + (hour.astype(np.int64) * 3600 + minute.astype(np.int64) * 60
                 + second.astype(np.int64)) * 1_000_000 + micros)
    if np.any(result >= (_LAST_ORDINAL + 1 - _EPOCH) * _DAY_US):
        return np.array([num2date(value) for value in values], dtype='datetime64[us]')
    return result.astype('datetime64[us]')
