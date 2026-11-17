#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Aurora - Optimized backtesting engine for backtrader_next
#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#
###############################################################################

"""Shared inclusive date filtering for pandas-backed feeds."""

from datetime import date, datetime

import numpy as np
import pandas as pd


def filter_dataframe_dates(dataframe, datetimes, fromdate=None, todate=None):
    """Use whole days for date bounds and exact timestamps for datetime bounds."""
    if fromdate is None and todate is None:
        return dataframe

    timestamps = pd.DatetimeIndex(datetimes)
    mask = np.ones(len(dataframe), dtype=bool)
    for boundary, lower in ((fromdate, True), (todate, False)):
        if boundary is None:
            continue
        if isinstance(boundary, date) and not isinstance(boundary, datetime):
            values = timestamps.date
        else:
            values = timestamps
            boundary = pd.Timestamp(boundary)
        mask &= values >= boundary if lower else values <= boundary

    return dataframe.loc[mask].copy()
