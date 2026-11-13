"""Standard line interfaces over Aurora input storage.

Aurora calculates standard dependency graphs after preloading and advances
their output cursors by clock. Automatic public input adaptation remains
a separate integration step.
"""

from backtrader_next.dataseries import OHLCDateTime
from backtrader_next.linebuffer import LineBuffer

from .feed import AuroraDataBase


class _StandardLine(LineBuffer):
    """A standard input line with storage and position owned by one feed."""

    def __init__(self, feed, column):
        # LineBuffer.__init__ allocates a mutable output buffer and resets its
        # cursor. Input storage already exists and must remain untouched.
        self._clock = feed
        self._column = column
        self.lines = [self]
        self.mode = self.NDBuffer
        self.bindings = []
        self.useislice = False
        self.extension = 0
        self._tz = feed._tz
        self._minperiod = feed._minperiod

    @property
    def array(self):
        if self._clock.data is None:
            raise RuntimeError('Preload the Aurora feed before reading standard line arrays')
        return self._clock.data[:, self._column]

    @property
    def _idx(self):
        return self._clock._idx

    @_idx.setter
    def _idx(self, value):
        self._clock._idx = value

    @property
    def lencount(self):
        return len(self._clock)

    @property
    def _once_cursor(self):
        return self._clock

    def home(self):
        self._clock.home()

    def reset(self):
        self.home()

    def advance(self, size=1):
        return self._clock.advance(size=size)

    def rewind(self, size=1):
        self._clock.rewind(size=size)

    def forward(self, value=float('nan'), size=1):
        raise ValueError('Cannot resize preloaded Aurora input lines; use advance()')

    def backwards(self, size=1, force=False):
        raise ValueError('Cannot resize preloaded Aurora input lines; use rewind()')

    def extend(self, value=float('nan'), size=0):
        raise ValueError('Cannot resize preloaded Aurora input lines')

    def qbuffer(self, savemem=0, extrasize=0):
        raise ValueError('Preloaded Aurora input lines require their full arrays')

    def ndbuffer(self, arr=None):
        raise ValueError('Aurora input arrays are owned by the feed')


class _StandardLines(OHLCDateTime.lines):
    def __init__(self, feed):
        self._feed = feed
        self.lines = [_StandardLine(feed, feed._linenames.index(name))
                      for name in self.getlinealiases()]

    # Moving seven lines independently would move the shared cursor seven
    # times. Container navigation delegates to its sole cursor owner once.
    def advance(self, size=1):
        return self._feed.advance(size=size)

    def rewind(self, size=1):
        self._feed.rewind(size=size)

    def home(self):
        self._feed.home()


class _StandardData(OHLCDateTime):
    """Internal close-first facade; the feed keeps its datetime-first rows.

    May be constructed before preloading. Column views resolve from the feed
    on access, so a subsequent reload does not leave stale NumPy references.
    Only the cursor is reset by home()/reset(); input arrays are fixed-size.
    """

    def __init__(self, feed):
        if not isinstance(feed, AuroraDataBase):
            raise TypeError('Standard Aurora data requires an AuroraDataBase feed')
        self._clock = feed
        self._minperiod = feed._minperiod
        self.lines = self.l = _StandardLines(feed)
        self.line = self.lines[0]
        # Replace the convenience references to MetaLineSeries' initial empty
        # buffers as well as the container. Named descriptors use the container.
        for index, line in enumerate(self.lines):
            setattr(self, 'line_%d' % index, line)
            setattr(self, 'line%d' % index, line)

    @property
    def _name(self):
        return self._clock._name

    @property
    def _timeframe(self):
        return self._clock._timeframe

    @property
    def _compression(self):
        return self._clock._compression

    @property
    def _tz(self):
        return self._clock._tz

    @property
    def _once_cursor(self):
        return self._clock

    @property
    def is_on(self):
        return self._clock.is_on

    @is_on.setter
    def is_on(self, value):
        self._clock.is_on = value

    @property
    def is_end(self):
        return self._clock.is_end

    @is_end.setter
    def is_end(self, value):
        self._clock.is_end = value
