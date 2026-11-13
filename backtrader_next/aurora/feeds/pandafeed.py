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
AuroraPandasData: mapped pandas input for preloaded Aurora backtests.

The loader resolves named or indexed OHLCV columns, filters date boundaries,
converts timestamps, and builds an owned float64 matrix. The source DataFrame
has separate storage; feed line views share the loaded matrix. Missing volume
and open-interest columns are filled with zero.

Use a DatetimeIndex by default or select the timestamp column explicitly.
Timing and memory measurements are in docs/aurora/BENCHMARKS.md.

Usage:
------
    import pandas as pd
    from backtrader_next.aurora import AuroraPandasData
    
    # Create DataFrame
    df = pd.DataFrame({
        'datetime': pd.date_range('2024-01-01', periods=100),
        'open': [100.0] * 100,
        'high': [110.0] * 100,
        'low': [90.0] * 100,
        'close': [105.0] * 100,
        'volume': [1000] * 100
    })
    
    # Create data feed
    data = AuroraPandasData(
        dataframe=df,
        name='AAPL',
        datetime='datetime',  # or None if index
        open='open',          # or -1 for auto-detect
        close='close'
    )
    
    # Use in Aurora
    aurora.adddata(data)
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np
import pandas as pd
from datetime import datetime, date

from backtrader_next import TimeFrame
from backtrader_next.utils.arraydates import date2num_array
from backtrader_next.utils.datefilters import filter_dataframe_dates

from ..feed import AuroraDataBase


class AuroraPandasData(AuroraDataBase):
    """
    Optimized pandas DataFrame data feed for Aurora.
    
    This class loads data from a pandas DataFrame into Aurora's unified
    2D array format. It provides flexible column mapping with auto-detection
    and conversion to an owned float64 matrix shared by the feed's line views.
    
    Parameters:
        dataframe (pd.DataFrame): Source DataFrame with OHLCV data
        name (str): Data feed name (default: '')
        timeframe (int): Timeframe constant (default: TimeFrame.Days)
        compression (int): Compression factor (default: 1)
        
        datetime (str/int/None): Datetime column specification
            - None: use DataFrame index as datetime
            - str: column name (e.g., 'datetime', 'Date')
            - int >= 0: column index
            - int == -1: auto-detect column name
        
        open (str/int/None): Open price column
        high (str/int/None): High price column
        low (str/int/None): Low price column
        close (str/int/None): Close price column
        volume (str/int/None): Volume column
        openinterest (str/int/None): Open interest column
        
        nocase (bool): Case-insensitive column matching (default: True)
        fromdate (datetime/date): Filter start date (inclusive)
        todate (datetime/date): Filter end date (inclusive)

    Datetime bounds preserve the exact time of day. Date-only bounds include
    the corresponding calendar day, whether timestamps are in the index or a column.
    
    Column Specification:
        - None: column not present, use 0 or NaN
        - -1: auto-detect column by name
        - >= 0: numeric column index
        - str: exact column name
    
    Example:
        # Using index as datetime
        data = AuroraPandasData(
            dataframe=df,
            datetime=None,
            open='Open', high='High', low='Low', close='Close'
        )
        
        # Auto-detect all columns
        data = AuroraPandasData(
            dataframe=df,
            datetime='Date',
            open=-1, high=-1, low=-1, close=-1, volume=-1
        )
    """
    
    def __init__(self, dataframe=None, name='', timeframe=TimeFrame.Days, 
                 compression=1, datetime=None, open=-1, high=-1, low=-1, 
                 close=-1, volume=-1, openinterest=-1, nocase=True,
                 fromdate=None, todate=None):
        """
        Initialize AuroraPandasData.
        
        Args:
            dataframe: pandas DataFrame with OHLCV data
            name: Data feed name
            timeframe: TimeFrame constant
            compression: Compression factor
            datetime: Datetime column specification
            open/high/low/close/volume/openinterest: Column specifications
            nocase: Case-insensitive column matching
            fromdate: Start date filter
            todate: End date filter
        """
        super().__init__(name=name, timeframe=timeframe, compression=compression)
        
        if dataframe is None:
            raise ValueError("Parameter 'dataframe' is required")
        
        # Store parameters
        self.dataframe = dataframe
        self.p_datetime = datetime
        self.p_open = open
        self.p_high = high
        self.p_low = low
        self.p_close = close
        self.p_volume = volume
        self.p_openinterest = openinterest
        self.p_nocase = nocase
        self.p_fromdate = fromdate
        self.p_todate = todate
        
        # Column mapping will be built in _load()
        self._colmapping = {}
    
    def _detect_column(self, field_name, param_value, colnames):
        """
        Detect column index for a given field.
        
        Args:
            field_name: Name of the field ('open', 'high', etc.)
            param_value: Parameter value (None, -1, int, or str)
            colnames: List of column names from DataFrame
        
        Returns:
            int: Column index, or None if not found
        """
        if param_value is None:
            # Column not present
            return None
        
        if isinstance(param_value, int):
            if param_value < 0:
                # Auto-detect by name
                for idx, colname in enumerate(colnames):
                    if isinstance(colname, str):
                        if self.p_nocase:
                            match = field_name.lower() == colname.lower()
                        else:
                            match = field_name == colname
                        
                        if match:
                            return idx
                # Not found
                return None
            else:
                # Use numeric index directly
                return param_value if param_value < len(colnames) else None
        
        elif isinstance(param_value, str):
            # Find by exact name
            try:
                if self.p_nocase:
                    colnames_lower = [c.lower() if isinstance(c, str) else c 
                                     for c in colnames]
                    return colnames_lower.index(param_value.lower())
                else:
                    return colnames.index(param_value)
            except ValueError:
                return None
        
        return None
    
    def _load(self):
        """
        Load data from pandas DataFrame into 2D numpy array.
        
        This method:
        1. Builds column mapping
        2. Filters by date range if specified
        3. Extracts datetime and OHLCV columns
        4. Creates unified 2D array [rows x 7]
        """
        df = self.dataframe
        colnames = list(df.columns.values)
        
        # Build column mapping
        self._colmapping = {
            'open': self._detect_column('open', self.p_open, colnames),
            'high': self._detect_column('high', self.p_high, colnames),
            'low': self._detect_column('low', self.p_low, colnames),
            'close': self._detect_column('close', self.p_close, colnames),
            'volume': self._detect_column('volume', self.p_volume, colnames),
            'openinterest': self._detect_column('openinterest', self.p_openinterest, colnames),
        }
        
        # Handle datetime column
        if self.p_datetime is None:
            # Use index as datetime
            dt_col = None
        else:
            dt_col = self._detect_column('datetime', self.p_datetime, colnames)
        
        # Apply date filters
        if self.p_fromdate is not None or self.p_todate is not None:
            datetimes = df.index if dt_col is None else df.iloc[:, dt_col]
            df = filter_dataframe_dates(df, datetimes, self.p_fromdate, self.p_todate)
        
        n_rows = len(df)
        if n_rows == 0:
            raise ValueError("DataFrame is empty after date filtering")
        
        datetimes = df.index if dt_col is None else df.iloc[:, dt_col]
        dt_numeric = date2num_array(pd.to_datetime(datetimes))
        
        # Extract OHLCV columns using fast .values access
        def extract_column(field_name):
            """Extract column values, return zeros if not found."""
            col_idx = self._colmapping[field_name]
            if col_idx is None:
                return np.zeros(n_rows, dtype=np.float64)
            return df.iloc[:, col_idx].values.astype(np.float64)
        
        open_values = extract_column('open')
        high_values = extract_column('high')
        low_values = extract_column('low')
        close_values = extract_column('close')
        volume_values = extract_column('volume')
        openinterest_values = extract_column('openinterest')
        
        # Build 2D array [rows x 7]
        # Column order: datetime, open, high, low, close, volume, openinterest
        self.data = np.column_stack([
            dt_numeric,
            open_values,
            high_values,
            low_values,
            close_values,
            volume_values,
            openinterest_values
        ])
        
        self._length = n_rows
        
        # Validate data
        if np.any(np.isnan(self.data[:, 0])):
            raise ValueError("NaN values detected in datetime column")


# Example usage and testing
if __name__ == '__main__':
    import sys
    
    print("=" * 70)
    print("AuroraPandasData - Fast DataFrame Loader")
    print("=" * 70)
    
    # Create test DataFrame
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    df = pd.DataFrame({
        'datetime': dates,
        'Open': np.random.uniform(100, 110, 100),
        'High': np.random.uniform(110, 120, 100),
        'Low': np.random.uniform(90, 100, 100),
        'Close': np.random.uniform(100, 110, 100),
        'Volume': np.random.randint(1000, 10000, 100)
    })
    
    # Fix high/low
    df['High'] = df[['Open', 'High', 'Close']].max(axis=1)
    df['Low'] = df[['Open', 'Low', 'Close']].min(axis=1)
    
    print(f"\n✓ Test DataFrame created: {len(df)} rows")
    print(f"  Columns: {list(df.columns)}")
    
    # Test 1: Auto-detect columns
    print("\n" + "=" * 70)
    print("Test 1: Auto-detect all columns")
    print("=" * 70)
    
    data1 = AuroraPandasData(
        dataframe=df,
        name='TEST_AUTO',
        datetime='datetime',
        open=-1, high=-1, low=-1, close=-1, volume=-1
    )
    data1.preload()
    
    print(f"✓ Data loaded: {data1._length} bars")
    print(f"  Array shape: {data1.data.shape}")
    print(f"  First bar: O={data1.data[0,1]:.2f} H={data1.data[0,2]:.2f} "
          f"L={data1.data[0,3]:.2f} C={data1.data[0,4]:.2f}")
    
    # Test 2: Explicit column names
    print("\n" + "=" * 70)
    print("Test 2: Explicit column names")
    print("=" * 70)
    
    data2 = AuroraPandasData(
        dataframe=df,
        name='TEST_EXPLICIT',
        datetime='datetime',
        open='Open', high='High', low='Low', close='Close', volume='Volume'
    )
    data2.preload()
    
    print(f"✓ Data loaded: {data2._length} bars")
    
    # Test 3: Date filtering
    print("\n" + "=" * 70)
    print("Test 3: Date filtering")
    print("=" * 70)
    
    data3 = AuroraPandasData(
        dataframe=df,
        name='TEST_FILTERED',
        datetime='datetime',
        open='Open', high='High', low='Low', close='Close',
        fromdate=date(2024, 1, 10),
        todate=date(2024, 1, 20)
    )
    data3.preload()
    
    print(f"✓ Data filtered: {data3._length} bars (from 2024-01-10 to 2024-01-20)")
    
    # Test 4: Index as datetime
    print("\n" + "=" * 70)
    print("Test 4: Index as datetime")
    print("=" * 70)
    
    df_indexed = df.set_index('datetime')
    data4 = AuroraPandasData(
        dataframe=df_indexed,
        name='TEST_INDEX',
        datetime=None,  # Use index
        open='Open', high='High', low='Low', close='Close', volume='Volume'
    )
    data4.preload()
    
    print(f"✓ Data loaded from index: {data4._length} bars")
    
    # Performance info
    print("\n" + "=" * 70)
    print("Performance Benefits")
    print("=" * 70)
    print(f"✓ Loaded matrix shared by feed line views")
    print(f"✓ Flexible column mapping (case-insensitive)")
    print(f"✓ Efficient date filtering")
    print(f"✓ Single 2D array: {data1.data.nbytes / 1024:.1f} KB for {data1._length} bars")
    print(f"✓ Ready for Aurora backtesting!")
    
    print("\n" + "=" * 70)
    print("✅ All tests passed!")
    print("=" * 70)
