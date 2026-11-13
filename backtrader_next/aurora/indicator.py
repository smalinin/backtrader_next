#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Aurora Indicator - Optimized indicator base class for Aurora engine
#
###############################################################################
"""
AuroraIndicator - low-level indicator base class.

Features:
- Uses individual IndicatorBase interfaces
- Optimized once() method for Aurora Lines
- Supports NumPy vectorized operations
- Simplified logic without support for different timeframes

Implementation differences from the standard Indicator:
- once() works directly with NumPy arrays in Aurora Lines
- Optimized for runonce mode

Inheriting from IndicatorBase does not automatically support standard
bt.ind.* and bt.nind.* indicators in the Aurora engine. The supported set of
indicators is exported from backtrader_next.aurora.indicators and uses
AuroraSimpleIndicator / MultiLineIndicator with a shared feed index.
This class is not an adapter for standard Cerebro indicators.
"""

import numpy as np
from backtrader_next.lineiterator import LineIterator, IndicatorBase
from backtrader_next.utils.py3 import with_metaclass


class MetaAuroraIndicator(IndicatorBase.__class__):
    """
    Metaclass for Aurora indicators.
    
    Simplified version of MetaIndicator without caching, focused on
    runonce mode.
    """
    
    _refname = '_indcol'
    _indcol = dict()
    
    def __init__(cls, name, bases, dct):
        """
        Register the indicator and check its methods.
        """
        super(MetaAuroraIndicator, cls).__init__(name, bases, dct)
        
        # Register the indicator by name
        if not cls.aliased and name != 'AuroraIndicator' and not name.startswith('_'):
            refattr = getattr(cls, cls._refname)
            refattr[name] = cls
        
        # Aurora only runs in runonce mode
        # If once() is not overridden, use once_via_next
        next_over = cls.next != IndicatorBase.next
        once_over = cls.once != IndicatorBase.once
        
        if next_over and not once_over:
            cls.once = cls.once_via_next
            cls.preonce = cls.preonce_via_prenext
            cls.oncestart = cls.oncestart_via_nextstart


class AuroraIndicator(with_metaclass(MetaAuroraIndicator, IndicatorBase)):
    """
    Low-level base class with individual IndicatorBase interfaces.
    
    Inheriting from IndicatorBase does not connect the standard Cerebro
    indicator lifecycle to Aurora. For Aurora strategies, use the classes
    exported from backtrader_next.aurora.indicators; this base class is not
    an adapter for bt.ind.* or bt.nind.*.
    
    Key methods:
    - once(start, end): Vectorized indicator calculation over a range of bars
    - next(): Indicator calculation for the current bar (fallback)
    
    For custom indicators in Aurora, use AuroraSimpleIndicator or
    MultiLineIndicator. A strategy example is provided in this package's
    README.md.
    """
    
    _ltype = LineIterator.IndType
    csv = False
    
    def __init__(self):
        """
        Initialize the indicator.
        
        Called automatically after the object is created.
        Used to configure parameters and dependencies.
        """
        super(AuroraIndicator, self).__init__()
    
    def _once(self):
        """
        Wrapper for calling once() that overrides the standard behavior.
        
        In the standard Indicator, _once() works with LineBuffer.once(),
        but Aurora needs to call its custom once(start, end).
        """
        # DEBUG
        print(f"DEBUG: AuroraIndicator._once() called for {self.__class__.__name__}")
        
        # Get the data length
        data_len = len(self._clock)
        if data_len <= 0:
            return
        
        # First call _once() for dependent indicators
        for indicator in self._ind_iterator:
            indicator._once()
        
        # Set the size of the lines
        self.lines.home()
        self.lines.extend(size=data_len)
        
        # Call once() to calculate values
        self.preonce(0, self._minperiod - 1)
        self.oncestart(self._minperiod - 1, self._minperiod)
        self.once(self._minperiod, data_len)
        
        # Reset the index
        self.home()
    
    def advance(self, size=1):
        """
        Advance the indicator index.
        
        This is simplified for Aurora indicators because all lines
        share a single index.
        
        Args:
            size (int): Number of bars to advance
        """
        # Check synchronization with the clock
        if len(self) < len(self._clock):
            self.lines.advance(size=size)
    
    def once(self, start, end):
        """
        Vectorized indicator calculation over a range of bars.
        
        This is the main method for runonce mode. Subclasses should override
        it to implement indicator logic.
        
        Args:
            start (int): Start index (inclusive)
            end (int): End index (exclusive)
        
        Example:
            def once(self, start, end):
                src = self.data.close.array
                dst = self.lines.myline.array
                
                for i in range(start, end):
                    dst[i] = src[i] * 2  # Double the price
        
        Note:
            Use .array instead of [i] to access data:
            - src = self.data.close.array  # numpy array
            - dst[i] = src[i]  # direct array access
        """
        pass  # Overridden in subclasses
    
    def next(self):
        """
        Calculate the indicator for the current bar.
        
        Fallback method, called only if once() is not overridden.
        For Aurora, overriding once() is recommended instead of next().
        
        Example:
            def next(self):
                self.lines.myline[0] = self.data.close[0] * 2
        """
        pass  # Overridden in subclasses
    
    def prenext(self):
        """
        Called before minperiod is reached.
        
        Does nothing by default. Can be overridden for custom handling
        of the indicator warm-up period.
        """
        pass
    
    def nextstart(self):
        """
        Called once when minperiod is reached.
        
        Calls next() by default. Can be overridden for custom initialization.
        """
        self.next()
    
    # Methods for fallback mode (if once is not overridden)
    
    def once_via_next(self, start, end):
        """
        Emulate once() through calls to next().
        
        Used automatically if once() is not overridden,
        but next() is overridden.
        
        Note: Slower than a native once() implementation!
        """
        for i in range(start, end):
            # Advance the data
            for data in self.datas:
                data.advance()
            
            # Advance dependent indicators
            for indicator in self._ind_iterator:
                indicator.advance()
            
            # Advance this indicator and call next()
            self.advance()
            self.next()
    
    def preonce_via_prenext(self, start, end):
        """
        Emulate preonce() through calls to prenext().
        """
        for i in range(start, end):
            for data in self.datas:
                data.advance()
            
            for indicator in self._ind_iterator:
                indicator.advance()
            
            self.advance()
            self.prenext()
    
    def oncestart_via_nextstart(self, start, end):
        """
        Emulate oncestart() through a call to nextstart().
        """
        for i in range(start, end):
            for data in self.datas:
                data.advance()
            
            for indicator in self._ind_iterator:
                indicator.advance()
            
            self.advance()
            self.nextstart()
    
    # NumPy utilities
    
    def get_array(self, line, length=None):
        """
        Get a NumPy array from a line.
        
        Args:
            line: Line object (for example, self.data.close)
            length (int, optional): Array length. If None, use the full available length.
        
        Returns:
            np.ndarray: NumPy array containing the data
        
        Example:
            close_array = self.get_array(self.data.close)
            sma_array = self.get_array(self.lines.sma)
        """
        if hasattr(line, 'array'):
            arr = line.array
        elif hasattr(line, 'get'):
            # Fallback for standard LineBuffer objects
            arr = np.array([line.get(ago=i) for i in range(len(line))])
        else:
            raise TypeError(f"Cannot extract array from {type(line)}")
        
        if length is not None:
            return arr[:length]
        return arr
    
    def set_array(self, line, array, start=0):
        """
        Set line values from a NumPy array.
        
        Args:
            line: Line object to write to
            array (np.ndarray): Array of values
            start (int): Start index for writing
        
        Example:
            result = np.mean(close_array)
            self.set_array(self.lines.sma, result, start=self.p.period-1)
        """
        if hasattr(line, 'array'):
            # Aurora LineBuffer - direct write
            line.array[start:start+len(array)] = array
        else:
            # Fallback for standard LineBuffer objects
            for i, val in enumerate(array):
                line[i - len(line) + start] = val


# Aliases for compatibility
Indicator = AuroraIndicator
