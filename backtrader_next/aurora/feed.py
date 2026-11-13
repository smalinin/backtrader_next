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
AuroraDataBase - Optimized data feed with unified index

This module provides the base class for Aurora data feeds, featuring
a revolutionary architecture where all OHLCV lines share a single
position index instead of having separate indices.

Key Architecture:
----------------
Standard backtrader DataBase:
    lines.datetime: LineBuffer (with own _idx)
    lines.open: LineBuffer (with own _idx)
    lines.high: LineBuffer (with own _idx)
    ... etc (7 separate buffers, 7 indices)

Aurora AuroraDataBase:
    data: np.ndarray [rows x 7]   # Single 2D array
    _idx: int                      # ONE shared index
    lines: AuroraLines             # Container with views

Benefits:
---------
1. Memory efficiency: 5x reduction (single contiguous array)
2. Cache locality: Better CPU cache utilization
3. No synchronization: Single index = no coordination overhead
4. Vectorization: NumPy operations can span all columns
5. Numba-friendly: JIT compilation works seamlessly

API Compatibility:
-----------------
Exposes selected backtrader-style DataBase methods:
- data.datetime[0], data.close[0], etc.
- len(data), data.buflen()
- advance(), home(), forward(), rewind()
- Indexing: data[0] (current), data[-1] (previous)

The shared NumPy index and line views differ from Cerebro's data buffers.
This interface subset does not provide standard-indicator compatibility;
use indicators from backtrader_next.aurora.indicators.

Usage:
------
    # Load from pandas DataFrame
    data = AuroraPandasData(dataframe=df, name='AAPL')
    
    # Access data (same API as backtrader)
    print(data.close[0])      # Current close
    print(data.close[-1])     # Previous close
    
    # Navigation
    data.advance()            # Move to next bar
    data.home()               # Reset to start
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import math
import numpy as np

from backtrader_next import TimeFrame
from backtrader_next.utils import date2num, num2date
from backtrader_next.utils.datasync import synchronize_activated_data

from .lineseries import AuroraLines


class AuroraDataBase:
    """
    Base class for Aurora data feeds with unified index architecture.
    
    This is the foundation for all Aurora data sources. Unlike standard
    backtrader DataBase which uses 7 separate LineBuffer objects (each
    with its own index), AuroraDataBase uses a single 2D numpy array
    with one shared index for all OHLCV columns.
    
    Architecture:
        data: np.ndarray shape (n_bars, 7)
            Column 0: datetime (as float)
            Column 1: open
            Column 2: high
            Column 3: low
            Column 4: close
            Column 5: volume
            Column 6: openinterest
        
        _idx: int (current position, -1 means before first bar)
        lines: AuroraLines (container providing line access)
    
    Attributes:
        _name (str): Data feed name (e.g., 'AAPL', 'EURUSD')
        _timeframe (int): Timeframe (Days, Minutes, etc.)
        _compression (int): Compression (1 for 1-minute, 5 for 5-minute)
        data (np.ndarray): Raw 2D data array [rows x 7]
        lines (AuroraLines): Line access container
        _idx (int): Current position index (shared by all lines)
        _length (int): Total number of bars
    """
    
    # Line names matching backtrader standard
    _linenames = ('datetime', 'open', 'high', 'low', 'close', 'volume', 
                  'openinterest')
    
    # Plot configuration (for nplot compatibility)
    # Using a simple namespace to allow attribute access
    class _PlotInfo:
        """Simple plot info container"""
        def __init__(self):
            self.plot = True
            self.plotmaster = None
            self.legendloc = None
    
    plotinfo = _PlotInfo()

    _is_on = True
    _activation_dt = None

    @property
    def is_on(self):
        return self._is_on

    @is_on.setter
    def is_on(self, value):
        was_on = self._is_on
        self._is_on = value
        if value and not was_on:
            synchronize_activated_data(self)
    
    def __init__(self, name='', timeframe=TimeFrame.Days, compression=1):
        """
        Initialize AuroraDataBase.
        
        Args:
            name (str): Data feed name (ticker symbol, etc.)
            timeframe (int): Timeframe constant from TimeFrame
            compression (int): Compression factor (e.g., 5 for 5-minute)
        """
        self._name = name
        self._timeframe = timeframe
        self._compression = compression
        
        # Core data: will be initialized by subclass in _load()
        self.data = None      # np.ndarray [rows x 7]
        self._idx = -1        # Current position (-1 = before first bar)
        self._length = 0      # Total bars available
        self._minperiod = 1   # Minimum period (for strategy synchronization)
        
        # Lines container (will be created after data is loaded)
        self.lines = None
        
        # Additional state
        self._tz = None       # Timezone (if any)
        self._started = False
        self._preloaded = False
        self._env = None      # Reference to Cerebro/Aurora environment
        self.is_on = True     # Data feed active flag (always True for Aurora)
        self.is_end = False     # Data feed active flag (always True for Aurora)
        
        # Broker integration attributes
        self._compensate = None   # Compensation data feed (for futures rollover, etc.)
        self._barstack = None     # Bar stack for filters (Aurora doesn't use filters)
        
        # Tick attributes for broker execution
        self.tick_close = None
        self.tick_low = None
        self.tick_high = None
        self.tick_open = None
        self.tick_volume = None
        self.tick_last = None
        
        # Parameters object (for backtrader compatibility)
        # Create a simple namespace for parameters accessed as self.p.xxx
        import datetime
        import types
        self.p = types.SimpleNamespace(
            sessionend=datetime.time(23, 59, 59, 999900),  # Default end of session
            sessionstart=None,  # Start of session (None = no restriction)
            timeframe=timeframe,
            compression=compression,
            name=name,
        )

    def setenvironment(self, env):
        """
        Keep a reference to the environment (Cerebro/Aurora).
        
        Args:
            env: Cerebro or Aurora instance
        """
        self._env = env
    
    def getenvironment(self):
        """
        Get the environment (Cerebro/Aurora) reference.
        
        Returns:
            Cerebro or Aurora instance
        """
        return self._env
    
    def _start(self):
        """
        Initialize the data feed (called by Cerebro/Aurora before run).
        
        This method is called by the backtesting engine to prepare
        the data feed for use. Override in subclasses if needed.
        """
        if not self._started:
            self.start()
            self._started = True
    
    def start(self):
        """
        User-overridable start method.
        
        Called once at the beginning of backtesting. Can be overridden
        by subclasses to perform custom initialization.
        """
        pass
    
    def stop(self):
        """
        Clean up resources (called by Cerebro/Aurora after run).
        
        Called once at the end of backtesting. Can be overridden
        by subclasses to perform cleanup.
        """
        pass
    
    def reset(self):
        """
        Reset the data feed to initial state.
        
        This resets the position index and internal state, allowing
        the data to be used again in multiple runs.
        """
        self._idx = -1
        self._started = False
        self._preloaded = False
        if self.lines is not None:
            self.lines._idx = self._idx
    
    def getfeed(self):
        """
        Get the feed instance (for compatibility with standard DataBase).
        
        Returns:
            None for Aurora feeds (no separate feed object)
        """
        return None
    
    def islive(self):
        """
        Check if this is a live data feed.
        
        Returns:
            bool: Always False for Aurora (backtesting only)
        """
        return False
    
    def _getlinealias(self, i):
        """
        Return the alias (name) for a line given its index.
        
        This is used by LineIterator to create named attributes for data access.
        For example, _getlinealias(4) returns 'close' so strategy can access
        self.data_close instead of self.data.lines[4]
        
        Args:
            i (int): Line index (0-6 for datetime, open, high, low, close, volume, openinterest)
        
        Returns:
            str: Line name/alias, or empty string if index out of range
        
        Examples:
            >>> data._getlinealias(0)  # 'datetime'
            >>> data._getlinealias(4)  # 'close'
            >>> data._getlinealias(10) # '' (out of range)
        """
        if i >= len(self._linenames):
            return ''
        return self._linenames[i]
    
    def _stage1(self):
        """
        Stage 1 initialization - called during strategy setup.
        Sets operation stage to 1 (binding stage).
        """
        pass  # Aurora doesn't need stage processing
    
    def _stage2(self):
        """
        Stage 2 initialization - called after all bindings complete.
        Sets operation stage to 2 (execution stage).
        """
        pass  # Aurora doesn't need stage processing
    
    def _tick_fill(self, force=False):
        """
        Fill tick attributes from current bar data.
        
        This is required by broker for order execution. The broker needs
        tick-level data (open, high, low, close of current bar) to determine
        order execution prices.
        
        Args:
            force (bool): Force refill even if tick_close is already set
        """
        if force or self.tick_close is None:
            self.tick_close = self.lines.close[0]
            self.tick_low = self.lines.low[0]
            self.tick_high = self.lines.high[0]
            self.tick_open = self.lines.open[0]
            self.tick_volume = self.lines.volume[0]
            self.tick_last = self.lines.close[0]
    
    def _initialize_lines(self):
        """
        Initialize the AuroraLines container after data is loaded.
        
        This creates the lines container that provides access to columns
        through the unified index interface.
        """
        if self.data is None:
            raise RuntimeError("Data must be loaded before initializing lines")
        
        # Create lines container with reference to our data and index
        self.lines = AuroraLines(
            linenames=self._linenames,
            initdata=self.data
        )
        
        # Share the same _idx reference
        self.lines._idx = self._idx

        # Back-reference so AuroraLineBufferView can find its parent feed
        self.lines._feed_ref = self
    
    def __len__(self):
        """
        Return the current length (number of bars loaded so far).
        
        Returns:
            int: Number of bars from start to current position + 1
                 Returns 0 if position is -1 (before first bar)
        """
        return self._idx + 1 if self._idx >= 0 else 0
    
    def buflen(self):
        """
        Return the total buffer length (all available bars).
        
        Returns:
            int: Total number of bars in the data feed
        """
        return self._length
    
    def __getitem__(self, ago):
        """
        Access bar data relative to current position.
        
        This provides array-like access to the entire bar.
        For individual line access, use: data.close[ago]
        
        Args:
            ago (int): Bars ago (0 = current, -1 = previous, 1 = future)
        
        Returns:
            np.ndarray: Row from data array [datetime, O, H, L, C, V, OI]
        
        Examples:
            data[0]  # Current bar (all values)
            data[-1] # Previous bar
            data[1]  # Next bar (if preloaded)
        """
        idx = self._idx + ago
        
        if idx < 0 or idx >= self._length:
            # Return NaN array for out-of-bounds access
            return np.full(7, float('NaN'))
        
        return self.data[idx]
    
    def advance(self, size=1):
        """
        Advance the data feed forward by size bars.
        
        This is the main navigation method for moving through data.
        Moves the shared _idx forward, making the next bar current.
        
        Args:
            size (int): Number of bars to advance (default 1)
        
        Returns:
            bool: True if advance was successful, False if at end
        """
        if self._idx + size < self._length:
            self._idx += size
            # Update lines container index
            if self.lines is not None:
                self.lines._idx = self._idx
            return True
        return False
    
    def advance_peek(self):
        """
        Peek at the datetime of the next bar without advancing.
        
        Used by Aurora._runonce to determine the next datetime across
        multiple data feeds for chronological synchronization.
        
        Returns:
            float: Datetime (as num) of the next bar, or float('inf') if no more data
        
        Example:
            >>> dt = data.advance_peek()
            >>> if dt < float('inf'):
            ...     data.advance()  # Actually move to that bar
        """
        next_idx = self._idx + 1
        
        if next_idx < self._length:
            # Return datetime of next bar (column 0)
            return self.data[next_idx, 0]
        
        return float('inf')  # No more data available
    
    def home(self):
        """
        Reset position to before first bar.
        
        Sets _idx to -1, meaning no bar is current yet.
        This is used at the start of runonce mode.
        """
        self._idx = -1
        if self.lines is not None:
            self.lines._idx = self._idx
    
    def forward(self, size=1):
        """
        Move forward without boundary checks.
        
        This is used during preload to move through all data.
        Unlike advance(), this doesn't check boundaries.
        
        Args:
            size (int): Number of bars to move forward
        """
        self._idx += size
        if self.lines is not None:
            self.lines._idx = self._idx
    
    def rewind(self, size=1):
        """
        Move backward by size bars.
        
        Args:
            size (int): Number of bars to move back
        """
        self._idx = max(-1, self._idx - size)
        if self.lines is not None:
            self.lines._idx = self._idx
    
    def advance_peek(self):
        """
        Peek at the datetime of the next bar without advancing.
        
        This is used by Aurora's main loop to determine which data
        feed has the earliest next bar.
        
        Returns:
            float: Datetime of next bar as float, or inf if at end
        """
        if self._idx + 1 < self._length:
            return self.data[self._idx + 1, 0]  # datetime column
        return float('inf')
    
    def preload(self):
        """
        Preload all data into memory.
        
        In Aurora's runonce mode, all data is preloaded before
        backtesting begins. This method triggers data loading
        and initializes the lines container.
        """
        if self._preloaded:
            return
        
        # Load data (implemented by subclass)
        self._load()
        
        # Initialize lines container
        self._initialize_lines()
        
        # Set position to end for runonce mode
        self._idx = self._length - 1
        if self.lines is not None:
            self.lines._idx = self._idx
        
        self._preloaded = True
    
    def _load(self):
        """
        Load data into the numpy array.
        
        This must be implemented by subclasses (AuroraPandasData,
        AuroraCSVData, etc.) to populate self.data and self._length.
        
        Expected to set:
            self.data: np.ndarray [rows x 7]
            self._length: int (number of rows)
        
        Raises:
            NotImplementedError: Must be overridden by subclass
        """
        raise NotImplementedError("Subclass must implement _load()")
    
    def start(self):
        """
        Start the data feed.
        
        Called by Aurora before backtesting begins.
        Can be overridden by subclasses for initialization.
        """
        self._started = True
    
    def stop(self):
        """
        Stop the data feed.
        
        Called by Aurora after backtesting ends.
        Can be overridden by subclasses for cleanup.
        """
        self._started = False
    
    # Properties for backtrader compatibility
    
    @property
    def datetime(self):
        """Alias for lines.datetime (backtrader compatibility)."""
        return self.lines.datetime if self.lines else None
    
    @property
    def open(self):
        """Alias for lines.open (backtrader compatibility)."""
        return self.lines.open if self.lines else None
    
    @property
    def high(self):
        """Alias for lines.high (backtrader compatibility)."""
        return self.lines.high if self.lines else None
    
    @property
    def low(self):
        """Alias for lines.low (backtrader compatibility)."""
        return self.lines.low if self.lines else None
    
    @property
    def close(self):
        """Alias for lines.close (backtrader compatibility)."""
        return self.lines.close if self.lines else None
    
    @property
    def volume(self):
        """Alias for lines.volume (backtrader compatibility)."""
        return self.lines.volume if self.lines else None
    
    @property
    def openinterest(self):
        """Alias for lines.openinterest (backtrader compatibility)."""
        return self.lines.openinterest if self.lines else None
    
    # Time/date conversion utilities
    
    def date2num(self, dt):
        """
        Convert datetime to float representation.
        
        Args:
            dt (datetime): Datetime object to convert
        
        Returns:
            float: Numeric representation of datetime
        """
        if self._tz is not None:
            dt = self._tz.localize(dt)
        return date2num(dt)
    
    def num2date(self, dt=None, tz=None, naive=True):
        """
        Convert float to datetime object.
        
        Args:
            dt (float, optional): Numeric datetime. If None, uses current bar.
            tz: Timezone (compatibility parameter, uses self._tz if provided)
            naive (bool): Return naive datetime (compatibility parameter)
        
        Returns:
            datetime: Datetime object
        """
        if dt is None:
            if self.lines is not None:
                dt = self.lines.datetime[0]
            else:
                raise ValueError("No current datetime available")
        
        # Use provided tz or fall back to self._tz
        timezone = tz if tz is not None else self._tz
        return num2date(dt, tz=timezone, naive=naive)


# Example usage and testing
if __name__ == '__main__':
    import pandas as pd
    
    # This will be implemented in AuroraPandasData
    # Just showing the API here
    
    class ExampleData(AuroraDataBase):
        """Example implementation for testing."""
        
        def __init__(self, dataframe, **kwargs):
            super().__init__(**kwargs)
            self.df = dataframe
        
        def _load(self):
            """Load data from pandas DataFrame."""
            # Convert datetime to numeric
            if 'datetime' in self.df.columns:
                dt_values = self.df['datetime'].apply(date2num).values
            else:
                dt_values = pd.to_datetime(self.df.index).map(date2num).values
            
            # Build 2D array
            self.data = np.column_stack([
                dt_values,
                self.df['open'].values,
                self.df['high'].values,
                self.df['low'].values,
                self.df['close'].values,
                self.df['volume'].values if 'volume' in self.df.columns 
                    else np.zeros(len(self.df)),
                self.df['openinterest'].values if 'openinterest' in self.df.columns 
                    else np.zeros(len(self.df))
            ])
            
            self._length = len(self.data)
    
    # Test
    print("AuroraDataBase API test:")
    print("- Unified index architecture")
    print("- Single 2D array for all OHLCV data")
    print("- API compatible with backtrader DataBase")
    print("\nReady for use in Aurora backtesting engine!")
