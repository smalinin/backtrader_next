#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Aurora - Optimized backtesting engine for backtrader_next
#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#
###############################################################################

"""Strategy execution for Aurora's preloaded backtesting engine."""

from backtrader_next.strategy import Strategy
from backtrader_next.utils.datasync import advance_indicators
from ._lifecycle import CleanupOnExit


class AuroraStrategy(Strategy):
    """Use Strategy's trading and lifecycle APIs with Aurora feeds/indicators.

    Standard runonce graphs accept feeds/lines and use per-feed warmup.
    Construct bt.ind/bt.nind indicators in __init__ before graph preparation.
    StandardData supplies explicit column expressions and delayed inputs.
    See docs/aurora/README.md for strategy and order examples.
    """

    # An immutable default also supports constructors that omit super().__init__().
    # Updates in _oncepost are assigned to each strategy instance.
    _aurora_min_period_reached = False

    def _periodset(self):
        # addminperiod() applies to the strategy clock (the first feed). Its
        # datetime line retains this requirement independently of indicators
        # registered on other feeds. Base Strategy maps graph periods to feeds.
        strategy_period = self.lines.datetime._minperiod
        super()._periodset()
        self._minperiods[0] = max(self._minperiods[0], strategy_period)
        self._minperiod = max(self._minperiod, strategy_period)

    def _getminperstatus_once(self, dt0, dts=None):
        # Use actual feed clocks; dts follows the engine's sorted feed order.
        # An is_end feed is disabled before dispatch but still supplies its
        # final bar. Other inactive feeds do not delay the active instruments.
        if len(self.datas) == 1:
            data = self.data0
            if data.is_on or (len(data) and data.datetime[0] == dt0):
                status = self._minperiods[0] - len(data)
                deficits = [status]
            else:
                status, deficits = 1, []
        else:
            deficits = [period - len(data)
                        for data, period in zip(self.datas, self._minperiods)
                        if data.is_on or (len(data) and data.datetime[0] == dt0)]
            status = max(deficits, default=1)
        if status <= 0:
            # Equality can persist for several bars of another feed, and late
            # activation can jump directly past zero. nextstart is still once.
            status = -1 if self._aurora_min_period_reached else 0
        self._minperstatus = status
        return status, deficits

    def _oncepost(self, dt0, dts=None):
        """Advance strategy lines and dispatch the current preloaded bar."""
        self.forward()
        self.lines.datetime[0] = dt0
        # Cache raw float datetime so analyzers (eq.py) can use it
        # without calling num2date on every bar
        self._dt0 = dt0

        if self._ind_iterator:
            advance_indicators(self)
        
        # Process notifications (orders, trades)
        self._notify()
        
        minperstatus, _ = self._getminperstatus_once(dt0, dts)
        if minperstatus > 0:
            self.prenext()
        elif minperstatus == 0:
            self._aurora_min_period_reached = True
            self.nextstart()
        else:
            self.next()
        
        if self.analyzers or self._slave_analyzers:
            self._next_analyzers(minperstatus, once=True)
        if self._obs_iterator:
            self._next_observers(minperstatus, once=True)
        
        self.clear()

    def _stop(self):
        # A failing strategy/analyzer stop must not prevent the remaining
        # analyzers from closing or leave data in the execution stage.
        stops = [analyzer._stop for analyzer in self.analyzers]
        stops.extend(analyzer._stop for analyzer in self._slave_analyzers)
        stops.append(self._clear_execution_schedule)
        stops.append(self._stage1)
        with CleanupOnExit(stops):
            self.stop()

    def _clear_execution_schedule(self):
        self.__dict__.pop('_execution_schedule', None)
