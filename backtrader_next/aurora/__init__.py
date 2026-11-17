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

"""Aurora backtesting with NumPy feeds and standard indicators.

Use AuroraStrategy and AuroraPandasData/AuroraCSVData. Standard runonce
indicators accept feeds and feed-backed lines; StandardData provides explicit
line expressions. Use bt.ind or bt.nind for indicators. Live trading,
runnext, resampling, replay and feed filters remain unsupported.
See docs/aurora/README.md.
"""

__version__ = '0.1.0'
__author__ = 'Aurora Team'

from .linebuffer import AuroraLineBufferView
from .lineseries import AuroraLines, AuroraLinesSingle
from .feed import AuroraDataBase
from ._standard import StandardData
from .feeds import AuroraPandasData, AuroraCSVData
from .aurora import Aurora, quickstart
from .strategy import AuroraStrategy

__all__ = [
    '__version__', '__author__',
    'AuroraLineBufferView', 'AuroraLines', 'AuroraLinesSingle',
    'AuroraDataBase', 'AuroraPandasData', 'AuroraCSVData', 'StandardData',
    'Aurora', 'quickstart', 'AuroraStrategy',
]
