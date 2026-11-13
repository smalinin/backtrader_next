#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

"""Synchronize feeds activated during a preloaded backtest."""

from bisect import bisect_right


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
            self._synchronize_indicators(strategy, clocks)

    def _synchronize_indicators(self, owner, clocks):
        for indicator in getattr(owner, '_ind_iterator', ()):
            self._synchronize_indicators(indicator, clocks)
            clock = indicator._clock
            if id(clock) not in clocks and not any(
                    id(line) in clocks for line in clock.lines):
                continue

            size = len(clock) - len(indicator)
            if size > 0:
                indicator.advance(size=size)
            clocks.add(id(indicator))
            clocks.update(id(line) for line in indicator.lines)
