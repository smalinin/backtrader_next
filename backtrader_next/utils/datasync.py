#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

"""Synchronize feeds activated during a preloaded backtest."""

from bisect import bisect_right


def _indicator_graph(owner):
    """Collect registered indicators, including nested dependency trees."""
    nodes = {}

    def collect(parent):
        for indicator in getattr(parent, '_ind_iterator', ()):
            if id(indicator) not in nodes:
                nodes[id(indicator)] = indicator
                collect(indicator)

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
