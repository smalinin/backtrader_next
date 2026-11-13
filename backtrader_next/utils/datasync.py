#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

"""Synchronize preloaded feed clocks and activation catch-up."""

from bisect import bisect_right
from math import inf


def _indicator_graph(owner):
    """Collect registered indicators, including nested dependency trees."""
    nodes = {}

    def collect(parent):
        for indicator in getattr(parent, '_ind_iterator', ()):
            if id(indicator) not in nodes:
                nodes[id(indicator)] = indicator
                collect(indicator)
        for observer in getattr(parent, '_obs_iterator', ()):
            collect(observer)

    collect(owner)
    return nodes


def home_indicators(owner):
    """Reset output cursors without clearing their calculated arrays."""
    for indicator in _indicator_graph(owner).values():
        indicator.home()


def advance_indicators(owner, clocks=None):
    """Align calculated outputs to their clocks, optionally for activated data.

    Clock dependencies are visited before their consumers. Output arrays are
    fixed after preparation; neither an idle feed nor repeated synchronization
    may consume another output value. A strategy clock can outlive its first
    feed, so output navigation is also bounded by the calculated buffer length.
    """
    nodes = _indicator_graph(owner)
    visited = {}

    def advance(indicator):
        key = id(indicator)
        if key in visited:
            return visited[key]
        visited[key] = False

        clock = indicator._clock
        # A clock may be an indicator itself, or a line/stub owned by one.
        dependency = nodes.get(id(clock))
        if dependency is None:
            # LineSeriesStub can wrap a LineActions object whose owner is the
            # strategy. The wrapped line itself is then the clock dependency.
            dependency = nodes.get(id(clock.lines[0]))
        if dependency is None:
            dependency = nodes.get(id(getattr(clock, '_owner', None)))
        if dependency is not None:
            affected = advance(dependency)
        else:
            # Facades and their individual input lines share a raw feed cursor.
            shared = getattr(clock, '_once_cursor', None)
            clock_owner = getattr(clock, '_owner', None)
            affected = (clocks is None or id(clock) in clocks or
                        id(clock_owner) in clocks or id(shared) in clocks or
                        id(getattr(clock_owner, '_once_cursor', None)) in clocks)

        if affected:
            size = min(len(clock), indicator.buflen()) - len(indicator)
            if size > 0:
                indicator.advance(size=size)
        visited[key] = affected
        return affected

    for indicator in nodes.values():
        advance(indicator)


def synchronize_activated_data(data):
    environment = getattr(data, '_env', None)
    synchronizer = getattr(environment, '_data_sync', None)
    if synchronizer is not None:
        synchronizer.activate(data)


class DataSynchronizer:
    def __init__(self, environment, strategies):
        self.environment = environment
        self.strategies = strategies
        self.datetime = None

    def __enter__(self):
        self.environment._data_sync = self
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.environment._data_sync = None
        for data in self.environment.datas:
            data._activation_dt = None

    def bars(self):
        """Iterate Aurora bars; leave broker/strategy dispatch to the engine."""
        datas = self.environment.datas
        if len(datas) == 1:
            return self._single_bars(datas[0])
        datas = sorted(datas, key=lambda data: (data._timeframe, data._compression))
        return self._multi_bars(datas)

    @staticmethod
    def _peek(data):
        if not data.is_on:
            return inf
        try:
            return data.advance_peek()
        except StopIteration:
            return inf

    @staticmethod
    def _advance(data):
        try:
            delivered = data.advance()
        except StopIteration:
            delivered = False
        if not delivered:
            data.is_on = False
            return False
        # The final bar is still delivered to the broker and every strategy.
        if data.is_end:
            data.is_on = False
        return True

    def _single_bars(self, data):
        peek, advance = self._peek, self._advance
        while True:
            dt0 = peek(data)
            if dt0 == inf:
                return
            self.datetime = dt0
            if not advance(data):
                return
            yield dt0, None

    def _multi_bars(self, datas):
        peek, advance = self._peek, self._advance
        dts = [peek(data) for data in datas]
        while True:
            dt0 = min(dts)
            if dt0 == inf:
                return
            self.datetime = dt0
            delivered = False
            for index, data in enumerate(datas):
                if data.is_on and dts[index] <= dt0:
                    if advance(data):
                        delivered = True
                        if not data.is_on:
                            dts[index] = inf
                    else:
                        dts[index] = inf
            if delivered:
                yield dt0, dts
            # Callbacks may disable a feed or activate/catch it up to this bar.
            for index, data in enumerate(datas):
                if not data.is_on:
                    dts[index] = inf
                elif dts[index] <= dt0 or dts[index] == inf:
                    dts[index] = peek(data)

    def activate(self, data):
        if self.datetime is None:
            return

        # Consume only bars at or before the current clock. Relative datetime
        # indexing works for both standard line buffers and Aurora views.
        remaining = data.buflen() - len(data)
        datetimes = data.lines.datetime
        size = bisect_right(range(remaining), self.datetime,
                            key=lambda offset: datetimes[offset + 1])
        if size:
            data.advance(size=size)

        # Caught-up bars warm indicators, but must never execute new orders.
        data._activation_dt = self.datetime
        clocks = {id(data)}
        clocks.update(id(line) for line in data.lines)
        for strategy in self.strategies:
            advance_indicators(strategy, clocks)
