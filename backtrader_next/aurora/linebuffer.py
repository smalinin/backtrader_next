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
"""Column views over Aurora's shared NumPy storage and cursor."""

import numpy as np
from backtrader_next.utils import num2date

NAN = float('NaN')


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
    
    __slots__ = ('parent_array', 'column_idx', 'parent_data', '_clock', 'bindings', '_tz', '_array_len')
    
    def __init__(self, parent_array, column_idx, parent_data, *, clock=None):
        """
        Initialize view into parent array column.
        
        Args:
            parent_array (np.ndarray): 2D array [rows x columns]
            column_idx (int): Column index (0=datetime, 1=open, etc.)
            parent_data (object): Reference to parent data object (must have _idx attribute)
            clock (object): Cursor owner; defaults to the parent container.
        """
        self.parent_array = parent_array
        self.column_idx = column_idx
        self.parent_data = parent_data
        self._clock = parent_data if clock is None else clock
        self.bindings = []
        self._tz = None
        self._array_len = len(parent_array)  # Cache array length
    
    @property
    def _idx(self):
        """Get current index from parent."""
        return self._clock._idx
    
    def __getitem__(self, ago):
        """Get value at offset from current position. Optimized hot path."""
        # Inline index calculation - avoid property call overhead
        idx = self._clock._idx + ago
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
        Get a view of preloaded data from an absolute index.
        
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
        Get a view of preloaded data for the absolute range [start, end).

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
