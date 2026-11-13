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
AuroraLineBuffer - Optimized line buffer using NumPy

This module provides an optimized implementation of LineBuffer using NumPy
arrays instead of array.array for better performance and vectorization support.

Key improvements:
- NumPy ndarray for O(1) access and vectorized operations
- Simplified index management (single _idx for all operations)
- Numba-compatible data structures
- Reduced memory overhead
- Faster slicing and access operations

Compatibility:
- API compatible with backtrader_next.LineBuffer
- Supports same indexing: [0] = current, [-1] = previous, [1] = future
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np
import math

from backtrader_next.utils import num2date, time2num

NAN = float('NaN')


class AuroraLineBuffer:
    """
    Optimized line buffer using NumPy arrays.
    
    Index 0 points to the current active element for input/output.
    Positive indices fetch values from the past (e.g., [1] = previous bar).
    Negative indices fetch values from the future (if preloaded).
    
    This implementation uses NumPy for:
    - Faster array operations
    - Better memory efficiency
    - Numba JIT compatibility
    - Vectorized computations
    
    Attributes:
        array (np.ndarray): The underlying numpy array storing the data
        _idx (int): Current position index (0-based)
        _length (int): Total length of data loaded
        _minperiod (int): Minimum period required before calculations
        bindings (list): List of bound LineBuffer objects
        _tz: Timezone information (optional)
    """

    def __init__(self, initdata=None):
        """
        Initialize the line buffer.
        
        Args:
            initdata (array-like, optional): Initial data to populate buffer
        """
        self.lines = [self]
        self.bindings = []
        self._tz = None
        self._minperiod = 1
        
        if initdata is not None:
            if isinstance(initdata, np.ndarray):
                self.array = initdata.copy()
            else:
                self.array = np.array(initdata, dtype=np.float64)
            self._length = len(self.array)
        else:
            self.array = np.array([], dtype=np.float64)
            self._length = 0
        
        self._idx = -1  # Start before first element
    
    def reset(self):
        """Reset the buffer to initial state."""
        self.array = np.array([], dtype=np.float64)
        self._idx = -1
        self._length = 0
        self.bindings = []
    
    def home(self):
        """Rewind the logical index to the beginning."""
        self._idx = -1
    
    def get_idx(self):
        """Get current index position."""
        return self._idx
    
    def set_idx(self, idx):
        """Set current index position."""
        self._idx = idx
    
    idx = property(get_idx, set_idx)
    
    def __len__(self):
        """Return the current length (number of bars processed)."""
        return self._idx + 1
    
    def buflen(self):
        """Return total buffer length (including preloaded future data)."""
        return self._length
    
    def __getitem__(self, ago):
        """
        Get value at position relative to current index.
        
        Args:
            ago (int): Offset from current position
                       0 = current, 1 = previous, -1 = next (future)
        
        Returns:
            float: Value at the specified position
        """
        return self.array[self._idx + ago]
    
    def __setitem__(self, ago, value):
        """
        Set value at position relative to current index.
        
        Args:
            ago (int): Offset from current position
            value (float): Value to set
        """
        self.array[self._idx + ago] = value
        
        # Execute bindings
        for binding in self.bindings:
            binding[ago] = value
    
    def set(self, value, ago=0):
        """
        Set value at position (alternative to __setitem__).
        
        Args:
            value (float): Value to set
            ago (int): Offset from current position (default: 0)
        """
        self[ago] = value
    
    def get(self, ago=0, size=1):
        """
        Get a slice of the array relative to current position.
        
        Args:
            ago (int): End position relative to current
            size (int): Number of elements to retrieve
        
        Returns:
            np.ndarray: Slice of the array
        """
        start = self._idx + ago - size + 1
        end = self._idx + ago + 1
        return self.array[start:end]
    
    def getzero(self, idx=0, size=1):
        """
        Get a slice relative to the absolute zero of the buffer.
        
        Args:
            idx (int): Start index (absolute)
            size (int): Number of elements
        
        Returns:
            np.ndarray: Slice of the array
        """
        return self.array[idx:idx + size]
    
    def getzeroval(self, idx=0):
        """
        Get single value at absolute index.
        
        Args:
            idx (int): Absolute index
        
        Returns:
            float: Value at index
        """
        return self.array[idx]
    
    def forward(self, value=NAN, size=1):
        """
        Move index forward and extend buffer if needed.
        
        Args:
            value (float): Value to fill new positions (default: NaN)
            size (int): Number of positions to advance
        """
        # Extend array if needed
        new_idx = self._idx + size
        if new_idx >= self._length:
            # Need to extend the array
            extend_size = new_idx - self._length + 1
            self.array = np.append(self.array, 
                                   np.full(extend_size, value, dtype=np.float64))
            self._length = len(self.array)
        
        self._idx = new_idx
    
    def backwards(self, size=1):
        """
        Move index backwards and shrink buffer.
        
        Args:
            size (int): Number of positions to move back
        """
        self._idx -= size
        # Optionally shrink array (not strictly necessary)
        if self._idx + 1 < self._length - size:
            self.array = self.array[:self._idx + 1]
            self._length = len(self.array)
    
    def rewind(self, size=1):
        """
        Move index backwards without changing buffer size.
        
        Args:
            size (int): Number of positions to rewind
        """
        self._idx -= size
    
    def advance(self, size=1):
        """
        Move index forward without extending buffer (must exist).
        
        Args:
            size (int): Number of positions to advance
        """
        self._idx += size
    
    def extend(self, value=NAN, size=0):
        """
        Extend buffer with future positions (lookahead).
        
        Args:
            value (float): Value to fill new positions
            size (int): Number of positions to add
        """
        if size > 0:
            self.array = np.append(self.array, 
                                   np.full(size, value, dtype=np.float64))
            self._length = len(self.array)
    
    def addbinding(self, binding):
        """
        Add a binding to another line buffer.
        
        Args:
            binding (AuroraLineBuffer): Buffer to bind
        """
        self.bindings.append(binding)
        if hasattr(binding, 'updateminperiod'):
            binding.updateminperiod(self._minperiod)
    
    def updateminperiod(self, minperiod):
        """
        Update minimum period.
        
        Args:
            minperiod (int): New minimum period
        """
        self._minperiod = max(self._minperiod, minperiod)
    
    def addminperiod(self, minperiod):
        """
        Add to minimum period.
        
        Args:
            minperiod (int): Period to add
        """
        self._minperiod += minperiod
    
    def oncebinding(self):
        """Execute bindings in 'once' mode (vectorized)."""
        blen = len(self)
        for binding in self.bindings:
            if hasattr(binding, 'array'):
                binding.array[:blen] = self.array[:blen]
    
    def get_array(self, nlast=0):
        """
        Get array data (current or last N elements).
        
        Args:
            nlast (int): Number of last elements (0 = all current)
        
        Returns:
            np.ndarray: Array slice
        """
        cur_len = self._idx + 1
        if cur_len <= 0:
            return np.array([], dtype=np.float64)
        
        if nlast == 0:
            return self.array[:cur_len].copy()
        else:
            nlast = abs(nlast)
            start = max(0, cur_len - nlast)
            return self.array[start:cur_len].copy()
    
    def plot(self, idx=0, size=None):
        """
        Get data for plotting.
        
        Args:
            idx (int): Start index (default: 0)
            size (int): Size of slice (default: all)
        
        Returns:
            np.ndarray: Data for plotting
        """
        if size is None:
            size = len(self)
        return self.getzero(idx, size)
    
    def plotrange(self, start, end):
        """
        Get plot data for specific range.
        
        Args:
            start (int): Start index
            end (int): End index
        
        Returns:
            np.ndarray: Data slice
        """
        return self.array[start:end].copy()
    
    def _settz(self, tz):
        """Set timezone."""
        self._tz = tz
    
    def datetime(self, ago=0, tz=None, naive=True):
        """
        Get datetime at position.
        
        Args:
            ago (int): Offset from current
            tz: Timezone (optional)
            naive (bool): Return naive datetime
        
        Returns:
            datetime: Datetime object
        """
        return num2date(self.array[self._idx + ago],
                       tz=tz or self._tz, naive=naive)
    
    def date(self, ago=0, tz=None, naive=True):
        """Get date at position."""
        return self.datetime(ago, tz, naive).date()
    
    def time(self, ago=0, tz=None, naive=True):
        """Get time at position."""
        return self.datetime(ago, tz, naive).time()
    
    def dt(self, ago=0):
        """Get numeric date part."""
        return math.trunc(self.array[self._idx + ago])
    
    def tm(self, ago=0):
        """Get numeric time part."""
        return time2num(num2date(self.array[self._idx + ago]).time())
    
    def __repr__(self):
        """String representation."""
        return (f"AuroraLineBuffer(length={len(self)}, "
                f"buflen={self.buflen()}, idx={self._idx})")


class AuroraLineBufferView:
    """
    View into a column of a 2D numpy array.
    
    This allows treating a single column from a shared OHLCV array
    as if it were a standalone LineBuffer, enabling the unified index
    architecture of Aurora.
    
    This is the key innovation: multiple "lines" (O, H, L, C, V, OI)
    share the same underlying array and position index.
    
    Performance: __getitem__ is called 500k+ times per backtest.
    Optimizations applied:
    - Direct array access without bounds check for common case
    - Cached array length
    - Inline index calculation
    """
    
    __slots__ = ('parent_array', 'column_idx', 'parent_data', 'bindings', '_tz', '_array_len')
    
    def __init__(self, parent_array, column_idx, parent_data):
        """
        Initialize view into parent array column.
        
        Args:
            parent_array (np.ndarray): 2D array [rows x columns]
            column_idx (int): Column index (0=datetime, 1=open, etc.)
            parent_data (object): Reference to parent data object (must have _idx attribute)
        """
        self.parent_array = parent_array
        self.column_idx = column_idx
        self.parent_data = parent_data
        self.bindings = []
        self._tz = None
        self._array_len = len(parent_array)  # Cache array length
    
    @property
    def _idx(self):
        """Get current index from parent."""
        return self.parent_data._idx
    
    def __getitem__(self, ago):
        """Get value at offset from current position. Optimized hot path."""
        # Inline index calculation - avoid property call overhead
        idx = self.parent_data._idx + ago
        # Fast path: assume valid index (most common case)
        # Bounds check only for edge cases
        if idx >= 0 and idx < self._array_len:
            return self.parent_array[idx, self.column_idx]
        return NAN
    
    def __setitem__(self, ago, value):
        """Set value at offset from current position."""
        idx = self._idx + ago
        if 0 <= idx < len(self.parent_array):
            self.parent_array[idx, self.column_idx] = value
            
            # Execute bindings
            for binding in self.bindings:
                binding[ago] = value
    
    def __len__(self):
        """Return current length."""
        return self._idx + 1
    
    def get_array(self):
        """Get column data up to current position."""
        cur_len = self._idx + 1
        if cur_len <= 0:
            return np.array([], dtype=np.float64)
        return self.parent_array[:cur_len, self.column_idx].copy()
    
    def plot(self):
        """
        Get column data for plotting (all values up to current position).
        
        Required by nplot for chart generation.
        Returns the same as get_array() for Aurora - all values up to current idx.
        """
        return self.get_array()
    
    def plotrange(self, start, end):
        """
        Get plot data for specific range.
        
        Args:
            start (int): Start index
            end (int): End index
        
        Returns:
            np.ndarray: Data slice for plotting
        """
        return self.parent_array[start:end, self.column_idx].copy()
    
    def addbinding(self, binding):
        """Add binding to another buffer."""
        self.bindings.append(binding)
    
    def _settz(self, tz):
        """Set timezone."""
        self._tz = tz
    
    def datetime(self, ago=0, tz=None, naive=True):
        """
        Get datetime at position.
        
        Converts numeric datetime value to Python datetime object.
        This is required by Order.__init__ and other backtrader components.
        
        Args:
            ago (int): Offset from current position (0=current, -1=previous, etc.)
            tz: Timezone (optional)
            naive (bool): Return naive datetime (default True)
        
        Returns:
            datetime: Python datetime object
        """
        value = self[ago]
        return num2date(value, tz=tz or self._tz, naive=naive)
    
    def date(self, ago=0, tz=None, naive=True):
        """
        Get date at position.
        
        Args:
            ago (int): Offset from current position
            tz: Timezone (optional)
            naive (bool): Return naive datetime (default True)
        
        Returns:
            date: Python date object
        """
        return self.datetime(ago, tz=tz, naive=naive).date()
    
    def time(self, ago=0, tz=None, naive=True):
        """
        Get time at position.
        
        Args:
            ago (int): Offset from current position
            tz: Timezone (optional)
            naive (bool): Return naive datetime (default True)
        
        Returns:
            time: Python time object
        """
        return self.datetime(ago, tz=tz, naive=naive).time()
    
    def buflen(self):
        """
        Return buffer length (number of loaded bars).
        
        Returns:
            int: Number of bars in buffer
        """
        return len(self.parent_array)
    
    def plot(self, idx=0, size=None):
        """
        Get data for plotting (from idx to current position).
        
        Args:
            idx (int): Start index (default: 0)
            size (int): Size of slice (default: entire buffer)
            
        Returns:
            np.ndarray: Array slice for plotting
        """
        if size is None:
            size = len(self.parent_array)
        end_idx = min(idx + size, len(self.parent_array))
        return self.parent_array[idx:end_idx, self.column_idx]
    
    def plotrange(self, start, end):
        """
        Get data slice for specific range.        
        Args:
            start (int): Start index
            end (int): End index
            
        Returns:
            np.ndarray: Array slice
        """
        return self.parent_array[start:end, self.column_idx]
    
    def __repr__(self):
        """String representation."""
        return (f"AuroraLineBufferView(column={self.column_idx}, "
                f"idx={self._idx}, len={len(self)})")
