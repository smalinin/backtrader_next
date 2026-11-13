"""
Simplified Aurora indicators with automatic synchronization and plotting support.

These indicators don't inherit from IndicatorBase, making them incompatible with
standard backtrader indicators but much simpler and faster. They sync automatically
with data feed index, eliminating the need for manual advance() calls.
"""

import numpy as np
from typing import Dict

from ...metabase import findowner
from ...strategy import Strategy
from ..feed import AuroraDataBase
from ..linebuffer import AuroraLineBufferView
from ..lineseries import AuroraLines


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


class AuroraSimpleIndicator:
    """
    Base class for simplified Aurora indicators.
    
    Key features:
    - No inheritance from IndicatorBase (simpler, faster)
    - Automatic synchronization via the resolved input clock
    - Full plotting support via PlottableWrapper
    - Vectorized calculations using NumPy
    - Multiple output lines supported
    
    Subclasses implement _do_calculate() and _getplotdata(). Use
    self._input.calculate(kernel, ...) to preserve leading NaN warmup and
    original bar alignment. Single-output subclasses populate self._values;
    multi-output subclasses populate self._lines.
    """
    
    # Override in subclasses
    plotinfo = dict(plot=True, subplot=False)
    plotlines = dict()
    _requires_ohlc = False
    
    def __init__(self, data, **kwargs):
        """
        Initialize the indicator.

        Args:
            data: Aurora feed, line container/view, single-output indicator,
                  or a selected output from a multi-line indicator.
            **kwargs: Additional parameters (stored in self._params)
        """
        self._input = _IndicatorInput(data, require_ohlc=self._requires_ohlc)
        self._clock = self._input.clock
        self._data_feed = self._input.feed
        self._params = kwargs
        self._period = kwargs.get('period', 1)
        self._initialized = False  # Flag for lazy initialization

        # Resolve the constructing strategy for each indicator. Data can be
        # shared by multiple strategies and reused across runs.
        owner = findowner(self, Strategy)

        # Auto-register for plotting if owner (Strategy) exists
        if owner is not None:
            if not hasattr(owner, '_simple_indicators'):
                owner._simple_indicators = []
            wrapper = PlottableWrapper(self, data_feed=self._data_feed)
            owner._simple_indicators.append(wrapper)
    
    def _ensure_initialized(self):
        """Lazy initialization - called on first access"""
        if not self._initialized:
            self._do_calculate()
            self._initialized = True
    
    def _do_calculate(self):
        """Override in subclasses to perform actual calculation"""
        raise NotImplementedError('Subclasses must implement _do_calculate')

    @property
    def array(self):
        """Return the full calculated output, including warmup NaNs."""
        self._ensure_initialized()
        return self._values
    
    def __getitem__(self, ago: int):
        """
        Access indicator values relative to current position.
        
        Uses the resolved input clock; no manual advance is needed.
        
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
        idx = self._clock._idx + ago
        if 0 <= idx < len(self._values):
            return self._values[idx]
        return float('nan')
    
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
        """Return the number of bars consumed by the input clock."""
        return max(0, self._clock._idx + 1)
    
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
        
        # Built-in output names are known without calculating the source.
        # Dynamic custom outputs retain their calculation-time lookup.
        if name not in self.plotlines:
            self._ensure_initialized()
            if not self._lines or name not in self._lines:
                raise AttributeError(f"'{self.__class__.__name__}' has no line '{name}'")
        return LineAccessor(self, name)
        
    @property
    def array(self):
        raise TypeError('Select a named output line from a multi-line indicator')


class LineAccessor:
    """
    Accessor for a single line in a multi-line indicator.
    
    Provides [ago] indexing synchronized with the original input clock.
    """
    
    def __init__(self, indicator, name):
        """
        Args:
            indicator: Native multi-line indicator owning the output
            name: Selected output name
        """
        self._indicator, self._name = indicator, name
        self._clock = indicator._clock
        self._data_feed = indicator._data_feed
    
    def __getitem__(self, ago: int) -> float:
        """
        Get a value at the current position plus ago.
        
        Args:
            ago: Bars back from current position
        
        Returns:
            Line value or np.nan if out of bounds
        """
        idx = self._clock._idx + ago
        values = self.array
        if idx < 0 or idx >= len(values):
            return np.nan
        return values[idx]
    
    def __len__(self) -> int:
        """Return the number of bars consumed by the input clock."""
        return max(0, self._clock._idx + 1)
    
    @property
    def array(self) -> np.ndarray:
        """Direct access to underlying numpy array"""
        self._indicator._ensure_initialized()
        return self._indicator._lines[self._name]


class _IndicatorInput:
    """Resolve native input storage, cursor owner and plotting feed once."""

    def __init__(self, source, *, require_ohlc=False):
        if isinstance(source, AuroraDataBase):
            self.clock = self.feed = source
            names = source._linenames
        elif isinstance(source, AuroraLines):
            self.feed = source._feed_ref
            self.clock = self.feed if self.feed is not None else source
            names = source._linenames
            if not require_ohlc and len(names) != 1 and 'close' not in names:
                raise TypeError('Select a named line from this AuroraLines container')
        elif isinstance(source, AuroraLineBufferView):
            self.clock = source._clock
            self.feed = self.clock if isinstance(self.clock, AuroraDataBase) else None
            names = ()
        elif isinstance(source, MultiLineIndicator):
            raise TypeError('Select a named output line from a multi-line indicator')
        elif isinstance(source, (AuroraSimpleIndicator, LineAccessor)):
            self.clock, self.feed = source._clock, source._data_feed
            names = ()
        else:
            raise TypeError('Expected an Aurora feed, line container/view or native indicator output')

        if require_ohlc and not {'high', 'low', 'close'}.issubset(names):
            raise TypeError('ATR requires an Aurora feed or container with high, low and close')
        self.source = source

    def _lines(self):
        if isinstance(self.source, AuroraDataBase):
            if self.source.lines is None:
                raise RuntimeError('Preload the Aurora feed before calculating indicators')
            return self.source.lines
        return self.source

    @staticmethod
    def _column(line):
        return line.parent_array[:, line.column_idx]

    def array(self):
        """Get the full input without copying its numerical storage."""
        if isinstance(self.source, (AuroraDataBase, AuroraLines)):
            lines = self._lines()
            line = lines.lines[0] if lines.size() == 1 else lines.close
            return self._column(line)
        if isinstance(self.source, AuroraLineBufferView):
            return self._column(self.source)
        return self.source.array

    def ohlc(self):
        lines = self._lines()
        return tuple(self._column(getattr(lines, name)) for name in ('high', 'low', 'close'))

    def calculate(self, kernel, *args):
        """Calculate after leading NaNs, then restore the original bar offsets."""
        values = self.array()
        start = 0
        if len(values) and np.isnan(values[0]):
            valid = ~np.isnan(values)
            start = int(valid.argmax()) if valid.any() else len(values)
        result = kernel(values[start:], *args)
        if not start:
            return result

        def aligned(output):
            full = np.full(len(values), np.nan)
            full[start:] = output
            return full

        return tuple(aligned(output) for output in result) if isinstance(result, tuple) else aligned(result)
