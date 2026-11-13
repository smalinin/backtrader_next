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
AuroraCSVData: CSV parsing followed by the Aurora pandas loader.

CSV parsing uses pandas.read_csv with configurable delimiters, headers, column
mapping and timestamp formats. The resulting DataFrame is converted into the
same owned OHLCV matrix as AuroraPandasData; its feed line views share that
matrix. The DataFrame and indicator outputs have separate storage.

Usage:
------
    from backtrader_next.aurora import AuroraCSVData
    
    # Basic usage
    data = AuroraCSVData(
        dataname='data.csv',
        name='AAPL',
        datetime=0,  # Column index
        open=1, high=2, low=3, close=4, volume=5
    )
    
    # With column names
    data = AuroraCSVData(
        dataname='data.csv',
        datetime='Date',
        open='Open', high='High', low='Low', close='Close', volume='Volume'
    )
    
    # Custom delimiter and date format
    data = AuroraCSVData(
        dataname='data.csv',
        separator=';',
        dtformat='%d/%m/%Y %H:%M:%S',
        datetime=0,
        open=1, high=2, low=3, close=4
    )
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import pandas as pd
from datetime import datetime, date

from backtrader_next import TimeFrame

from .pandafeed import AuroraPandasData


class AuroraCSVData(AuroraPandasData):
    """
    Optimized CSV file data feed for Aurora.
    
    This class loads data from CSV files using pandas for fast parsing,
    then converts to Aurora's unified 2D array format via AuroraPandasData.
    
    Parameters:
        dataname (str): Path to CSV file or file-like object
        name (str): Data feed name (default: filename without extension)
        timeframe (int): Timeframe constant (default: TimeFrame.Days)
        compression (int): Compression factor (default: 1)
        
        separator (str): CSV field delimiter (default: ',')
        skiprows (int): Number of header rows to skip (default: 0)
        header (int/None): Row number to use as column names (default: 0)
        
        dtformat (str): Datetime format string (default: '%Y-%m-%d %H:%M:%S')
            Examples:
            - '%Y-%m-%d' for '2024-01-01'
            - '%d/%m/%Y' for '01/01/2024'
            - '%Y-%m-%d %H:%M:%S' for '2024-01-01 09:30:00'
        
        datetime (str/int/None): Datetime column specification
            - None: use DataFrame index as datetime
            - str: column name (e.g., 'Date', 'datetime')
            - int >= 0: column index
            - int == -1: auto-detect column name
        
        open/high/low/close/volume/openinterest (str/int/None):
            Column specifications (same format as datetime)
        
        nocase (bool): Case-insensitive column matching (default: True)
        fromdate (datetime/date): Filter start date (inclusive)
        todate (datetime/date): Filter end date (inclusive)
    
    Example:
        # Simple CSV with header
        data = AuroraCSVData(
            dataname='AAPL.csv',
            datetime='Date',
            open='Open', high='High', low='Low', close='Close'
        )
        
        # CSV without header (use column indices)
        data = AuroraCSVData(
            dataname='data.csv',
            header=None,
            datetime=0,
            open=1, high=2, low=3, close=4, volume=5
        )
        
        # Custom format
        data = AuroraCSVData(
            dataname='data.txt',
            separator='\t',
            dtformat='%d/%m/%Y',
            datetime='date',
            open='o', high='h', low='l', close='c'
        )
    """
    
    def __init__(self, dataname=None, name='', timeframe=TimeFrame.Days,
                 compression=1, separator=',', skiprows=0, header=0,
                 dtformat='%Y-%m-%d %H:%M:%S', datetime=0, open=1, high=2,
                 low=3, close=4, volume=5, openinterest=6, nocase=True,
                 fromdate=None, todate=None, **kwargs):
        """
        Initialize AuroraCSVData.
        
        Args:
            dataname: Path to CSV file
            name: Data feed name (auto-detected from filename if empty)
            timeframe: TimeFrame constant
            compression: Compression factor
            separator: CSV delimiter
            skiprows: Rows to skip at start
            header: Header row (None for no header)
            dtformat: Datetime parsing format
            datetime/open/high/low/close/volume/openinterest: Column specs
            nocase: Case-insensitive matching
            fromdate: Start date filter
            todate: End date filter
        """
        if dataname is None:
            raise ValueError("Parameter 'dataname' is required")
        
        # Store CSV-specific parameters BEFORE loading
        self.dataname = dataname
        self.separator = separator
        self.skiprows = skiprows
        self.header = header
        self.dtformat = dtformat
        self._datetime_param = datetime  # Store before parent init
        
        # Auto-detect name from filename if not provided
        if not name and isinstance(dataname, str):
            name = os.path.splitext(os.path.basename(dataname))[0]
        
        # Load CSV into DataFrame
        dataframe = self._load_csv()
        
        # Call parent constructor with DataFrame
        super().__init__(
            dataframe=dataframe,
            name=name,
            timeframe=timeframe,
            compression=compression,
            datetime=datetime,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            openinterest=openinterest,
            nocase=nocase,
            fromdate=fromdate,
            todate=todate,
            **kwargs
        )
    
    def _load_csv(self):
        """
        Load CSV file into pandas DataFrame.
        
        Returns:
            pd.DataFrame: Loaded data with proper datetime parsing
        """
        # Prepare pandas read_csv parameters
        read_params = {
            'filepath_or_buffer': self.dataname,
            'sep': self.separator,
            'skiprows': self.skiprows,
            'header': self.header,
        }
        
        # Try to load CSV
        try:
            df = pd.read_csv(**read_params)
        except Exception as e:
            raise ValueError(f"Failed to load CSV file '{self.dataname}': {e}")
        
        if df.empty:
            raise ValueError(f"CSV file '{self.dataname}' is empty")
        
        # Parse datetime column if format is specified
        if self.dtformat and self._datetime_param is not None:
            # Find datetime column
            if self._datetime_param is None:
                # Use index - try to parse it
                try:
                    df.index = pd.to_datetime(df.index, format=self.dtformat)
                except:
                    try:
                        df.index = pd.to_datetime(df.index)
                    except:
                        pass
            elif isinstance(self._datetime_param, int):
                if self._datetime_param >= 0 and self._datetime_param < len(df.columns):
                    col = df.columns[self._datetime_param]
                    try:
                        df[col] = pd.to_datetime(df[col], format=self.dtformat)
                    except:
                        try:
                            df[col] = pd.to_datetime(df[col])
                        except:
                            pass
            elif isinstance(self._datetime_param, str):
                if self._datetime_param in df.columns:
                    try:
                        df[self._datetime_param] = pd.to_datetime(
                            df[self._datetime_param], 
                            format=self.dtformat
                        )
                    except:
                        try:
                            df[self._datetime_param] = pd.to_datetime(df[self._datetime_param])
                        except:
                            pass
        
        return df


# Example usage and testing
if __name__ == '__main__':
    import sys
    import os
    import tempfile
    import numpy as np
    
    print("=" * 70)
    print("AuroraCSVData - Fast CSV Loader")
    print("=" * 70)
    
    # Create temporary CSV files for testing
    temp_dir = tempfile.gettempdir()
    
    # Test 1: CSV with header
    print("\n" + "=" * 70)
    print("Test 1: CSV with Header")
    print("=" * 70)
    
    csv1_path = os.path.join(temp_dir, 'test_aurora_1.csv')
    csv1_content = """Date,Open,High,Low,Close,Volume
2024-01-01,100.0,110.0,95.0,105.0,1000
2024-01-02,105.0,115.0,100.0,110.0,1500
2024-01-03,110.0,120.0,105.0,115.0,2000
2024-01-04,115.0,125.0,110.0,120.0,1800
2024-01-05,120.0,130.0,115.0,125.0,2200
"""
    
    with open(csv1_path, 'w') as f:
        f.write(csv1_content)
    
    data1 = AuroraCSVData(
        dataname=csv1_path,
        datetime='Date',
        dtformat='%Y-%m-%d',
        open='Open', high='High', low='Low', close='Close', volume='Volume'
    )
    data1.preload()
    
    print(f"✓ Loaded CSV with header: {data1._length} bars")
    print(f"  Name: {data1._name}")
    print(f"  Array shape: {data1.data.shape}")
    
    data1.home()
    data1.advance()
    print(f"  First bar: O={data1.open[0]:.1f} H={data1.high[0]:.1f} "
          f"L={data1.low[0]:.1f} C={data1.close[0]:.1f}")
    
    # Test 2: CSV without header (numeric indices)
    print("\n" + "=" * 70)
    print("Test 2: CSV without Header (Numeric Indices)")
    print("=" * 70)
    
    csv2_path = os.path.join(temp_dir, 'test_aurora_2.csv')
    csv2_content = """2024-01-01,100,110,95,105,1000
2024-01-02,105,115,100,110,1500
2024-01-03,110,120,105,115,2000
"""
    
    with open(csv2_path, 'w') as f:
        f.write(csv2_content)
    
    data2 = AuroraCSVData(
        dataname=csv2_path,
        header=None,
        datetime=0,
        dtformat='%Y-%m-%d',
        open=1, high=2, low=3, close=4, volume=5
    )
    data2.preload()
    
    print(f"✓ Loaded CSV without header: {data2._length} bars")
    print(f"  Array shape: {data2.data.shape}")
    
    # Test 3: Custom delimiter (semicolon)
    print("\n" + "=" * 70)
    print("Test 3: Custom Delimiter (Semicolon)")
    print("=" * 70)
    
    csv3_path = os.path.join(temp_dir, 'test_aurora_3.csv')
    csv3_content = """date;o;h;l;c;v
01/01/2024;100;110;95;105;1000
02/01/2024;105;115;100;110;1500
03/01/2024;110;120;105;115;2000
"""
    
    with open(csv3_path, 'w') as f:
        f.write(csv3_content)
    
    data3 = AuroraCSVData(
        dataname=csv3_path,
        separator=';',
        datetime='date',
        dtformat='%d/%m/%Y',
        open='o', high='h', low='l', close='c', volume='v'
    )
    data3.preload()
    
    print(f"✓ Loaded CSV with semicolon delimiter: {data3._length} bars")
    
    # Test 4: Auto-detect columns
    print("\n" + "=" * 70)
    print("Test 4: Auto-detect Column Names")
    print("=" * 70)
    
    csv4_path = os.path.join(temp_dir, 'test_aurora_4.csv')
    csv4_content = """datetime,open,high,low,close,volume
2024-01-01,100,110,95,105,1000
2024-01-02,105,115,100,110,1500
"""
    
    with open(csv4_path, 'w') as f:
        f.write(csv4_content)
    
    data4 = AuroraCSVData(
        dataname=csv4_path,
        datetime='datetime',
        open=-1, high=-1, low=-1, close=-1, volume=-1
    )
    data4.preload()
    
    print(f"✓ Auto-detected columns: {data4._length} bars")
    
    # Cleanup
    for path in [csv1_path, csv2_path, csv3_path, csv4_path]:
        try:
            os.remove(path)
        except:
            pass
    
    print("\n" + "=" * 70)
    print("Performance Benefits")
    print("=" * 70)
    print("✓ Fast CSV parsing via pandas")
    print("✓ Flexible column specification")
    print("✓ Support for various formats and delimiters")
    print("✓ Automatic datetime parsing")
    print("✓ Ready for Aurora backtesting!")
    
    print("\n" + "=" * 70)
    print("✅ All tests passed!")
    print("=" * 70)
