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

"""
Aurora Feeds Package

This package contains optimized data feed implementations for Aurora.
All feeds use the unified index architecture with single 2D numpy arrays.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from .pandafeed import AuroraPandasData
from .csvfeed import AuroraCSVData

__all__ = ['AuroraPandasData', 'AuroraCSVData']
