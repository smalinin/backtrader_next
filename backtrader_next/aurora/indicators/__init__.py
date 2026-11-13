"""
Aurora Indicators - Simplified version with automatic synchronization.

These indicators don't require owner context and synchronize automatically
with data feed via data._idx. No manual advance() needed.

Use these implementations (SMA, EMA, RSI, MACD, BollingerBands, ATR) with
AuroraStrategy and Aurora feeds. Standard runonce indicators use the separate
StandardData(feed) interface exported by backtrader_next.aurora.
Numba compilation alone does not establish compatibility with that interface.
"""

# Import base classes
from .simple import AuroraSimpleIndicator, MultiLineIndicator, PlottableWrapper

# Import simplified indicators
from .sma import SMA
from .ema import EMA
from .rsi import RSI
from .macd import MACD
from .bollinger_simple import BollingerBands
from .atr_simple import ATR

__all__ = [
    # Base classes
    'AuroraSimpleIndicator',
    'MultiLineIndicator',
    'PlottableWrapper',
    
    # Indicators
    'SMA',
    'EMA', 
    'RSI',
    'MACD',
    'BollingerBands',
    'ATR',
]

