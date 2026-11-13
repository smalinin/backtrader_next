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
# the Free Software Foundation, either version 3 of the License, or
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
"""Aurora backtesting with NumPy feeds and native or standard indicators.

Use AuroraStrategy and AuroraPandasData/AuroraCSVData. Standard runonce
indicators use StandardData(feed); native indicators use aurora.indicators.
Direct native inputs to bt.ind.*, live trading, runnext, resampling, replay
and feed filters remain unsupported. See docs/aurora/README.md.
"""

__version__ = '0.1.0'
__author__ = 'Aurora Team'

from .linebuffer import AuroraLineBufferView
from .lineseries import AuroraLines, AuroraLinesSingle
from .feed import AuroraDataBase
from ._standard import StandardData
from .feeds import AuroraPandasData, AuroraCSVData
from .aurora import Aurora, quickstart
from .indicators import SMA, EMA, RSI, MACD, BollingerBands, ATR
from .strategy import AuroraStrategy
from . import indicators

__all__ = [
    '__version__', '__author__',
    'AuroraLineBufferView', 'AuroraLines', 'AuroraLinesSingle',
    'AuroraDataBase', 'AuroraPandasData', 'AuroraCSVData', 'StandardData',
    'Aurora', 'quickstart', 'AuroraStrategy',
    'SMA', 'EMA', 'RSI', 'MACD', 'BollingerBands', 'ATR', 'indicators',
]
