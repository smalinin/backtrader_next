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
"""
Aurora - Optimized Backtesting Engine

Aurora is a high-performance backtesting engine designed for strategy testing
with the following features:

- **Runonce-only mode**: Vectorized operations for maximum speed
- **Unified data index**: Single position index for all OHLCV elements
- **Numba optimization**: JIT compilation for critical paths
- **Memory efficient**: ~5x less memory than standard Cerebro
- **Selected Cerebro-style APIs**: Familiar setup and trading methods

Limitations:
- No live trading support (backtesting only)
- No runnext mode (runonce only)
- No replay/resample (pre-process data)
- No data filters (load clean data)
- Standard Cerebro indicators (bt.ind.* and bt.nind.*) are not supported
- Existing strategies require adaptation to AuroraStrategy, Aurora feeds,
  and indicators from backtrader_next.aurora.indicators

Indicator support:
- Use aurora.indicators.SMA, EMA, RSI, MACD, BollingerBands, and ATR
- These indicators calculate over preloaded arrays and follow the feed index
- AuroraIndicator is a low-level base, not an adapter for standard indicators

Example:
    >>> from backtrader_next.aurora import Aurora, AuroraPandasData
    >>> import pandas as pd
    >>> 
    >>> # Create engine
    >>> aurora = Aurora()
    >>> 
    >>> # Add data
    >>> data = AuroraPandasData(dataframe=df, name='AAPL')
    >>> aurora.adddata(data)
    >>> 
    >>> # Add a strategy derived from AuroraStrategy using Aurora indicators
    >>> aurora.addstrategy(MyStrategy)
    >>> 
    >>> # Run backtest
    >>> results = aurora.run()
    >>> print(aurora.statistics)
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

__version__ = '0.1.0'
__author__ = 'Aurora Team'

# Core infrastructure (Phase 1 - completed)
from .linebuffer import AuroraLineBuffer, AuroraLineBufferView
from .lineseries import AuroraLines, AuroraLineAlias, AuroraLinesSingle

# Data feeds (Phase 2 - completed)
from .feed import AuroraDataBase
from .feeds import AuroraPandasData, AuroraCSVData

# Core engine (Phase 3 - completed)
from .aurora import Aurora, quickstart

# Indicators (Phase 4 - completed)
from .indicator import AuroraIndicator
from .indicators import SMA, EMA, RSI, MACD, BollingerBands, ATR

# Strategy (Phase 5 - completed)
from .strategy import AuroraStrategy, AStrat

# Indicators module (accessible as bt.aurora.indicators)
from . import indicators as indicators

# Note: Analyzers (Phase 6 - completed)
# Analyzers use the familiar addanalyzer API; compatibility depends on each
# analyzer's data and lifecycle requirements. Eq is added by default.
# Use: aurora.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
# See README.md in this package for API boundaries and migration guidance.

# Exports
__all__ = [
    '__version__',
    '__author__',
    # Phase 1 exports
    'AuroraLineBuffer',
    'AuroraLineBufferView',
    'AuroraLines',
    'AuroraLineAlias',
    'AuroraLinesSingle',
    # Phase 2 exports
    'AuroraDataBase',
    'AuroraPandasData',
    'AuroraCSVData',
    # Phase 3 exports
    'Aurora',
    'quickstart',
    # Phase 4 exports
    'AuroraIndicator',
    'SMA',
    'EMA',
    'RSI',
    'MACD',
    'BollingerBands',
    'ATR',
    # Phase 5 exports
    'AuroraStrategy',
    'AStrat',
    # Indicators module
    'indicators',
]

# Module-level documentation
__doc__ = """
Aurora Backtesting Engine
==========================

Performance Improvements vs Cerebro:
- Memory: 5x reduction
- Loading: 6x faster
- Backtesting: 20x faster (with Numba)
- Indicators: 50x faster (with Numba)

Architecture:
- Unified data storage with single position index
- NumPy-based arrays for OHLCV data
- Numba JIT compilation for hot paths
- Simplified execution flow (runonce only)

Supported API:
- Use AuroraStrategy with AuroraPandasData or AuroraCSVData
- Setup and trading methods follow a subset of the Cerebro/Strategy APIs
- Use indicators from backtrader_next.aurora.indicators
- Standard bt.ind.* and bt.nind.* indicators are not supported
- AuroraIndicator does not provide automatic standard-indicator compatibility
- Analyzer compatibility depends on each analyzer's data and lifecycle needs

Limitations:
- Backtesting only; data is preloaded and execution always uses runonce
- No live trading, runnext, replay/resample, or data filters
- Strategies written for Cerebro require adaptation before use with Aurora

Usage Pattern:
    1. Create Aurora instance
    2. Add data feeds (AuroraPandasData, AuroraCSVData)
    3. Add an AuroraStrategy using Aurora indicators
    4. Add analyzers (Sharpe, DrawDown, etc.)
    5. Run backtest
    6. Analyze results

See README.md in this package for a migration example and supported APIs.
"""
