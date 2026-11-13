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
AuroraLines - Optimized lines container with unified index

This module provides an optimized implementation of Lines container where
all lines share a single position index (_idx), unlike the standard
backtrader implementation where each LineBuffer has its own index.

Key Innovation:
--------------
Instead of:
    datetime: LineBuffer (with own _idx)
    open: LineBuffer (with own _idx)
    high: LineBuffer (with own _idx)
    ...

Aurora uses:
    data: np.ndarray [rows x 7]  # Single 2D array
    _idx: int                     # ONE index for ALL columns

This provides:
- Faster access (no index synchronization needed)
- Less memory (one array vs 7 separate arrays)
- Better cache locality
- Vectorized operations support
- Numba compatibility

API Compatibility:
-----------------
Exposes selected backtrader-style Lines methods:
- lines.datetime, lines.open, lines.close, etc.
- lines[i] selects a line by its column index
- Historical indexing: lines.close[0] = current, lines.close[-1] = previous
- Methods: forward(), home(), advance(), etc.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np
from .linebuffer import AuroraLineBufferView

NAN = float('NaN')


class AuroraLines:
    """
    Container for multiple lines sharing a single 2D numpy array.
    
    This is the core innovation of Aurora: all OHLCV lines exist in
    one 2D array with a single shared position index.
    
    Structure:
        data: np.ndarray shape (n_bars, n_lines)
        _idx: single int (shared by all lines)
        lines: list of AuroraLineBufferView objects (views into columns)
    
    Attributes:
        _linenames (tuple): Names of lines ('datetime', 'open', 'high', ...)
        data (np.ndarray): Shared 2D array [rows x columns]
        _idx (int): Current position index (shared by ALL lines)
        lines (list): List of AuroraLineBufferView objects

    Standalone containers can resize while retaining existing line objects.
    Containers attached to preloaded feeds have a fixed shape; operations that
    would resize their matrix raise RuntimeError.
    """
    
    # Default line names for OHLCV data
    _linenames = ('datetime', 'open', 'high', 'low', 'close', 'volume', 
                  'openinterest')
    
    def __init__(self, linenames=None, initdata=None, *, copy=True):
        """
        Initialize AuroraLines container.
        
        Args:
            linenames (tuple, optional): Names of lines. 
                                        Defaults to OHLCV names.
            initdata (np.ndarray, optional): Initial 2D data array.
                                            Shape: (n_bars, n_lines)
            copy (bool): Copy a 2D NumPy input by default. Set False to reuse
                         an existing matrix, as preloaded data feeds do.
        """
        if linenames is not None:
            self._linenames = linenames
        
        n_lines = len(self._linenames)
        
        # Initialize shared data array
        if initdata is not None:
            if isinstance(initdata, np.ndarray):
                if initdata.ndim == 1:
                    # Single line, reshape to 2D
                    self.data = initdata.reshape(-1, 1)
                else:
                    self.data = initdata.copy() if copy else initdata
            else:
                # Convert to numpy array
                self.data = np.array(initdata, dtype=np.float64)
                if self.data.ndim == 1:
                    self.data = self.data.reshape(-1, 1)
            
            # Verify shape
            if self.data.shape[1] != n_lines:
                raise ValueError(
                    f"Data has {self.data.shape[1]} columns but "
                    f"{n_lines} lines expected"
                )
        else:
            # Empty array
            self.data = np.empty((0, n_lines), dtype=np.float64)
        
        # Single shared index for ALL lines
        self._idx = -1
        
        # Create line views (one per column)
        self.lines = []
        for col_idx in range(n_lines):
            view = AuroraLineBufferView(
                parent_array=self.data,
                column_idx=col_idx,
                parent_data=self
            )
            self.lines.append(view)
        
        # Create named attributes for each line
        for idx, name in enumerate(self._linenames):
            setattr(self, name, self.lines[idx])
    
    def __len__(self):
        """Return current length (number of bars processed)."""
        return self._idx + 1
    
    def size(self):
        """Return number of lines."""
        return len(self.lines)
    
    def fullsize(self):
        """Return number of lines (same as size for Aurora)."""
        return len(self.lines)
    
    def buflen(self):
        """Return total buffer length (including future data)."""
        return len(self.data)
    
    def __getitem__(self, line):
        """
        Get line by index.
        
        Args:
            line (int): Line index (0=datetime, 1=open, etc.)
        
        Returns:
            AuroraLineBufferView: View into the line
        """
        return self.lines[line]
    
    def __setitem__(self, line, value):
        """
        Set line value or binding.
        
        Args:
            line (int): Line index
            value: Value or line to bind
        """
        if hasattr(value, 'addbinding'):
            # It's a line, create binding
            value.addbinding(self.lines[line])
        else:
            # Direct value at current position
            self.lines[line][0] = value
    
    def get(self, ago=0, size=1, line=0):
        """
        Get slice from a specific line.
        
        Args:
            ago (int): Position relative to current (0=current)
            size (int): Number of elements
            line (int): Line index
        
        Returns:
            np.ndarray: Slice of data
        """
        start = self._idx + ago - size + 1
        end = self._idx + ago + 1
        return self.data[start:end, line]
    
    def home(self):
        """Reset index to beginning."""
        self._idx = -1

    def _check_resize(self):
        if getattr(self, '_feed_ref', None) is not None:
            raise RuntimeError(
                'Cannot resize preloaded feed lines; reset and reload the feed instead')

    def _replace_data(self, data):
        """Retain line objects and their bindings when replacing the matrix."""
        self.data = data
        length = len(data)
        for line in self.lines:
            line.parent_array = data
            line._array_len = length
    
    def forward(self, value=NAN, size=1):
        """
        Move index forward and extend array if needed.
        
        Args:
            value (float): Fill value for new positions
            size (int): Number of positions to advance
        """
        new_idx = self._idx + size
        current_len = len(self.data)
        
        if new_idx >= current_len:
            self._check_resize()
            # Need to extend array
            extend_size = new_idx - current_len + 1
            new_rows = np.full((extend_size, self.data.shape[1]), 
                             value, dtype=np.float64)
            self._replace_data(np.vstack([self.data, new_rows]))
        
        self._idx = new_idx
    
    def backwards(self, size=1):
        """
        Move index backwards and optionally shrink array.
        
        Args:
            size (int): Number of positions to move back
        """
        new_idx = self._idx - size
        # Optionally trim array
        if new_idx + 1 < len(self.data) - size:
            self._check_resize()
            self._replace_data(self.data[:new_idx + 1])
        self._idx = new_idx
    
    def rewind(self, size=1):
        """
        Move index backwards without changing array size.
        
        Args:
            size (int): Number of positions to rewind
        """
        self._idx -= size
    
    def advance(self, size=1):
        """
        Move index forward without extending array.
        
        Args:
            size (int): Number of positions to advance
        """
        self._idx += size
    
    def extend(self, value=NAN, size=0):
        """
        Extend array with future positions (lookahead).
        
        Args:
            value (float): Fill value
            size (int): Number of rows to add
        """
        if size > 0:
            self._check_resize()
            new_rows = np.full((size, self.data.shape[1]), 
                             value, dtype=np.float64)
            self._replace_data(np.vstack([self.data, new_rows]))
    
    def reset(self):
        """Reset to initial empty state."""
        self._check_resize()
        n_lines = len(self._linenames)
        self._replace_data(np.empty((0, n_lines), dtype=np.float64))
        self._idx = -1
    
    def get_array(self, line=0, nlast=0):
        """
        Get array data for a specific line.
        
        Args:
            line (int): Line index
            nlast (int): Number of last elements (0=all current)
        
        Returns:
            np.ndarray: Array data
        """
        cur_len = self._idx + 1
        if cur_len <= 0:
            return np.array([], dtype=np.float64)
        
        if nlast == 0:
            return self.data[:cur_len, line].copy()
        else:
            nlast = abs(nlast)
            start = max(0, cur_len - nlast)
            return self.data[start:cur_len, line].copy()
    
    def itersize(self):
        """Iterate over lines."""
        return iter(self.lines)
    
    def getlinealiases(self):
        """Get line names."""
        return self._linenames
    
    def _getlinealias(self, i):
        """Get line name by index."""
        if i >= len(self._linenames):
            return ''
        return self._linenames[i]
    
    def oncebinding(self):
        """Execute bindings in once mode (vectorized)."""
        blen = len(self)
        for line in self.lines:
            for binding in line.bindings:
                if hasattr(binding, 'array'):
                    # Copy data to binding
                    binding.array[:blen] = line.get_array()[:blen]
    
    def __repr__(self):
        """String representation."""
        return (f"AuroraLines(lines={len(self.lines)}, "
                f"length={len(self)}, buflen={self.buflen()}, "
                f"idx={self._idx})")


class AuroraLinesSingle(AuroraLines):
    """
    AuroraLines variant for single line (e.g., indicators).
    
    This is used for indicators that produce a single output line.
    """
    
    def __init__(self, linename='line', initdata=None):
        """
        Initialize single line container.
        
        Args:
            linename (str): Name of the line
            initdata (array-like): Initial data
        """
        super().__init__(linenames=(linename,), initdata=initdata)
        
        # For single line, provide direct access
        self.line = self.lines[0]
    
    def __getitem__(self, ago):
        """Get value at position (shortcut for single line)."""
        return self.line[ago]
    
    def __setitem__(self, ago, value):
        """Set value at position (shortcut for single line)."""
        self.line[ago] = value
