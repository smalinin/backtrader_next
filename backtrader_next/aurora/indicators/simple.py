"""
Simplified Aurora indicators with automatic synchronization and plotting support.

These indicators don't inherit from IndicatorBase, making them incompatible with
standard backtrader indicators but much simpler and faster. They sync automatically
with data feed index, eliminating the need for manual advance() calls.
"""

import sys
import itertools
import numpy as np
from typing import Dict, Optional, Any


# ---------------------------------------------------------------------------
# Helper classes that make PlottableWrapper compatible with nplot.plotind()
# ---------------------------------------------------------------------------

class _GetDict:
    """Wraps a plain dict to provide AutoInfoClass._get() and attribute access."""
    def __init__(self, d):
        self._d = d or {}

    def _get(self, key, default=None):
        return self._d.get(key, default)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return self._d.get(name, None)


class _PlotLineInfo:
    """Wraps a per-line options dict providing ._get() interface."""
    def __init__(self, d):
        self._d = d or {}

    def _get(self, key, default=None):
        return self._d.get(key, default)


class _PlotLinesContainer:
    """Wraps plotlines dict for attribute access returning _PlotLineInfo."""
    def __init__(self, d):
        self._d = d or {}

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return _PlotLineInfo(self._d.get(name, {}))


class _LineRef:
    """Single line wrapper providing plotrange() interface."""
    def __init__(self, values):
        self._values = values

    def plotrange(self, start, end):
        if self._values is None:
            return np.array([])
        return self._values[start:end]


class _LineContainer:
    """Lines container providing [idx] and _getlinealias() interface."""
    def __init__(self, names, values_dict):
        self._names = list(names)
        self._values = values_dict

    def __getitem__(self, idx):
        name = self._names[idx]
        return _LineRef(self._values.get(name))

    def _getlinealias(self, idx):
        return self._names[idx]


def findowner(owned, target_class=None):
    """
    Find the owner of an object by traversing the Python call stack.
    
    Similar to backtrader's metabase.findowner(), this function walks up
    the call stack to find an instance of the target class that can be
    considered the owner of the current object.
    
    Args:
        owned: The object looking for an owner
        target_class: Class to look for (Strategy-like). If None, looks for
                     any object with 'datas' attribute (duck typing for Strategy)
    
    Returns:
        Owner object if found, None otherwise
    
    Example:
        # Called from indicator __init__:
        # Stack: Frame 0: __init__ (self=indicator)
        #        Frame 1: Strategy.__init__ (self=Strategy)
        # Returns: Strategy instance
    """
    # Start at level 2 to skip this function and the caller
    for framelevel in itertools.count(2):
        try:
            frame = sys._getframe(framelevel)
        except ValueError:
            # Frame depth exceeded - no owner found
            break
        
        # Look for 'self' in the frame's local variables
        self_ = frame.f_locals.get('self', None)
        if self_ is None or self_ is owned:
            continue
        
        # If target_class specified, check isinstance
        if target_class is not None:
            if isinstance(self_, target_class):
                return self_
        else:
            # Duck typing: if it has 'datas' attribute, it's likely a Strategy
            if hasattr(self_, 'datas'):
                return self_
    
    return None


class PlottableWrapper:
    """
    Wrapper that makes AuroraSimpleIndicator compatible with nplot.plotind().

    Implements the interface expected by nplot:
      - plotlabel()               → display name
      - size()                    → number of output lines
      - lines[i]                  → _LineRef with plotrange()
      - lines._getlinealias(i)    → line name string
      - plotinfo._get(key, def)   → plotinfo values
      - plotinfo.<attr>           → plotinfo values via attribute
      - plotlines.<attr>._get()   → per-line options
      - _plotinit()               → no-op (required by sortdataindicators)
    """

    def __init__(self, indicator: 'AuroraSimpleIndicator', data_feed=None):
        """
        Args:
            indicator: The simplified indicator to wrap
            data_feed: The AuroraDataBase feed this indicator belongs to
        """
        self._indicator = indicator
        self._data_feed = data_feed

        # Wrap plotinfo dict so ._get() and attribute access both work
        raw_plotinfo = getattr(indicator, 'plotinfo', {})
        self.plotinfo = _GetDict(raw_plotinfo)

        # Wrap plotlines dict so attribute access returns _PlotLineInfo
        raw_plotlines = getattr(indicator, 'plotlines', {})
        self.plotlines = _PlotLinesContainer(raw_plotlines)

    # ------------------------------------------------------------------
    # Interface required by nplot.sortdataindicators / nplot.plotind
    # ------------------------------------------------------------------

    def _plotinit(self):
        """Called by sortdataindicators before plotting - no-op here."""
        pass

    def plotlabel(self):
        """Return display label for legend."""
        name = self.plotinfo._get('plotname', '') or self._indicator.__class__.__name__
        return name

    def size(self):
        """Return number of output lines."""
        self._indicator._ensure_initialized()
        data = self._indicator._getplotdata()
        return len(data) if data else 0

    @property
    def lines(self):
        """Return _LineContainer for iteration by plotind."""
        self._indicator._ensure_initialized()
        data = self._indicator._getplotdata()
        if data is None:
            data = {}
        return _LineContainer(list(data.keys()), data)

    # ------------------------------------------------------------------
    # Legacy helpers (kept for backward compatibility)
    # ------------------------------------------------------------------

    def _getlines(self):
        """Return pseudo-lines for older plotter code."""
        data = self._indicator._getplotdata()
        lines = type('Lines', (), {})()
        if data:
            for name, values in data.items():
                setattr(lines, name, values)
        return lines

    def _getminperiod(self):
        return self._indicator._getminperiod()

    def _getplotinfo(self):
        return self.plotinfo

    def _getplotlines(self):
        return self.plotlines


class AuroraSimpleIndicator:
    """
    Base class for simplified Aurora indicators.
    
    Key features:
    - No inheritance from IndicatorBase (simpler, faster)
    - Automatic synchronization via data._idx (no manual advance needed)
    - Full plotting support via PlottableWrapper
    - Vectorized calculations using NumPy
    - Multiple output lines supported
    
    Subclasses must implement:
    - _calculate(): compute indicator values
    - _getplotdata(): return dict of line_name -> numpy array
    
    Example:
        class SMA(AuroraSimpleIndicator):
            plotinfo = dict(plot=True, subplot=False)
            plotlines = dict(sma=dict(_name='SMA', color='blue'))
            
            def __init__(self, data, period=20):
                super().__init__(data, period=period)
                self._period = period
                self._values = self._calculate(data.lines.close.array, period)
            
            @staticmethod
            def _calculate(close, period):
                # NumPy vectorized calculation
                ...
    """
    
    # Override in subclasses
    plotinfo = dict(plot=True, subplot=False)
    plotlines = dict()
    
    def __init__(self, data, **kwargs):
        """
        Initialize the indicator.

        Args:
            data: Aurora data feed OR a single line view (AuroraLineBufferView),
                  e.g. ``SMA(self.data.close, period=20)``.
            **kwargs: Additional parameters (stored in self._params)
        """
        self._data = data
        self._params = kwargs
        self._period = kwargs.get('period', 1)
        self._initialized = False  # Flag for lazy initialization

        # Detect whether a full data feed or a bare line view was passed.
        # AuroraLineBufferView uses __slots__ and has no 'lines' attribute;
        # AuroraDataBase / AuroraLines have 'lines'.
        _is_line_view = not hasattr(data, 'lines')

        # Auto-discover owner
        if _is_line_view:
            # Line view has no _owner slot; find owner via call stack
            owner = findowner(self)
        else:
            if not hasattr(data, '_owner') or data._owner is None:
                data._owner = findowner(self)
            owner = getattr(data, '_owner', None)

        # Resolve the actual data feed for the plotter
        if _is_line_view:
            parent_data = getattr(data, 'parent_data', None)  # AuroraLines
            data_feed = getattr(parent_data, '_feed_ref', None)
        else:
            data_feed = data

        # Auto-register for plotting if owner (Strategy) exists
        if owner is not None:
            if not hasattr(owner, '_simple_indicators'):
                owner._simple_indicators = []
            wrapper = PlottableWrapper(self, data_feed=data_feed)
            owner._simple_indicators.append(wrapper)
    
    def _ensure_initialized(self):
        """Lazy initialization - called on first access"""
        if not self._initialized:
            self._do_calculate()
            self._initialized = True
    
    def _do_calculate(self):
        """Override in subclasses to perform actual calculation"""
        pass
    
    def __getitem__(self, ago: int):
        """
        Access indicator values relative to current position.
        
        Uses data._idx for automatic synchronization - no manual advance() needed!
        
        Args:
            ago: Number of bars back (0 = current, -1 = previous, etc.)
        
        Returns:
            Indicator value or np.nan if out of bounds
        """
        # Inline lazy init check for performance (avoid function call overhead)
        if not self._initialized:
            self._do_calculate()
            self._initialized = True
        
        # Direct array access - fastest path
        idx = self._data._idx + ago
        if 0 <= idx < len(self._values):
            return self._values[idx]
        return float('nan')
    
    def _get_value_at(self, idx: int) -> float:
        """
        Get indicator value at specific index.
        
        Override in subclasses with single-line indicators.
        For multi-line indicators, override __getitem__ directly.
        
        Args:
            idx: Absolute index in data
        
        Returns:
            Indicator value or np.nan if out of bounds
        """
        raise NotImplementedError("Subclasses must implement _get_value_at or override __getitem__")
    
    def _getplotdata(self) -> Dict[str, np.ndarray]:
        """
        Return data for plotting.
        
        Must be implemented by subclasses.
        
        Returns:
            Dictionary mapping line names to numpy arrays
        """
        raise NotImplementedError("Subclasses must implement _getplotdata")
    
    def _getminperiod(self) -> int:
        """
        Return minimum period before indicator produces valid values.
        
        Returns:
            Minimum period
        """
        return self._period
    
    def __len__(self) -> int:
        """Return total length of indicator data"""
        return len(self._data)
    
    def __repr__(self) -> str:
        """String representation"""
        params_str = ', '.join(f'{k}={v}' for k, v in self._params.items())
        return f"{self.__class__.__name__}({params_str})"


class MultiLineIndicator(AuroraSimpleIndicator):
    """
    Base class for indicators with multiple output lines.
    
    Provides convenient access via attributes (e.g., macd.macd, macd.signal).
    """
    
    def __init__(self, data, **kwargs):
        super().__init__(data, **kwargs)
        self._lines = {}  # Dict of line_name -> numpy array
    
    def __getattr__(self, name: str):
        """Allow access to lines as attributes"""
        if name.startswith('_'):
            # Internal attributes
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        # Ensure calculation is done
        self._ensure_initialized()
        
        if self._lines and name in self._lines:
            # Return a line accessor
            return LineAccessor(self._data, self._lines[name])
        
        raise AttributeError(f"'{self.__class__.__name__}' has no line '{name}'")
    
    def _get_value_at(self, idx: int):
        """Not used for multi-line indicators"""
        raise NotImplementedError("MultiLineIndicator requires direct line access")


class LineAccessor:
    """
    Accessor for a single line in a multi-line indicator.
    
    Provides [ago] indexing synchronized with data._idx.
    """
    
    def __init__(self, data, values: np.ndarray):
        """
        Args:
            data: Data feed for index synchronization
            values: Numpy array of line values
        """
        self._data = data
        self._values = values
    
    def __getitem__(self, ago: int) -> float:
        """
        Get value at current position minus ago bars.
        
        Args:
            ago: Bars back from current position
        
        Returns:
            Line value or np.nan if out of bounds
        """
        idx = self._data._idx + ago
        if idx < 0 or idx >= len(self._values):
            return np.nan
        return self._values[idx]
    
    def __len__(self) -> int:
        """Return line length"""
        return len(self._values)
    
    @property
    def array(self) -> np.ndarray:
        """Direct access to underlying numpy array"""
        return self._values
