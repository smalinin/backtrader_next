"""
Aurora Indicators - Simplified version with automatic synchronization.

These indicators don't require owner context and synchronize automatically
with data feed via data._idx. No manual advance() needed.
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

