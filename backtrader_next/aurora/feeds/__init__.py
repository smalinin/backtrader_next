#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Aurora - Optimized backtesting engine for backtrader_next
#
# Copyright (C) 2026
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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
