#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
"""Strategy execution for Aurora's preloaded backtesting engine."""

from backtrader_next.strategy import Strategy
from backtrader_next.utils.datasync import advance_indicators
from ._lifecycle import CleanupOnExit


class AuroraStrategy(Strategy):
    """Use Strategy's trading and lifecycle APIs with Aurora feeds/indicators.

    Native indicators follow preloaded feed cursors; check their values after
    warmup. Standard bt.ind.* and bt.nind.* indicators remain unsupported.
    See docs/aurora/README.md for strategy and order examples.
    """

    # Immutable defaults also support constructors that omit super().__init__().
    # Updates in _oncepost/_notify are assigned to each strategy instance.
    _aurora_min_period_reached = False
    _aurora_notify_lists = None

    def _oncepost(self, dt0, dts=None):
        """
        Optimized _oncepost for Aurora - minimizes overhead per bar.
        """
        # Inline self.forward() → lineseries.forward() → lines.forward() → linebuffer.forward()
        # The strategy has only one line (datetime), so we can inline 3 function call layers.
        # Equivalent to self.forward() but saves 3 Python function calls per bar (× 226K = 678K)
        lb = self.lines[0]   # datetime LineBuffer
        lb.idx += 1
        lb.lencount += 1
        lb.array.append(lb.array[-1] if lb.array else float('nan'))  # extend with placeholder
        
        # Set current datetime (overwrites placeholder)
        self.lines.datetime[0] = dt0
        # Cache raw float datetime so analyzers (eq.py) can use it
        # without calling num2date on every bar
        self._dt0 = dt0

        if self._ind_iterator:
            advance_indicators(self)
        
        # Process notifications (orders, trades)
        self._notify()
        
        # Fast minperiod check for single-data case
        if not self._aurora_min_period_reached:
            data = self.datas[0]
            if len(data) >= self._minperiod:
                self._aurora_min_period_reached = True
                self.nextstart()
            else:
                self.prenext()
        else:
            # Main next() call - this is where strategy logic runs
            self.next()
        
        # Analyzers and observers - only if present
        if self.analyzers:
            for analyzer in self.analyzers:
                analyzer._next()
        
        if self.observers:
            for observer in self.observers:
                observer._next()
        
        self.clear()

    def _notify(self, qorders=[], qtrades=[]):
        """
        Aurora-optimized _notify: avoids itertools.chain and broker property
        getters on the hot path (called 226k+ times per run).
        """
        # Process pending orders (usually empty)
        for order in self._orderspending:
            if order.exectype != order.Historical or order.histnotify:
                self.notify_order(order)
            for analyzer in self.analyzers:
                analyzer._notify_order(order)
            for analyzer in self._slave_analyzers:
                analyzer._notify_order(order)

        # Process pending trades (usually empty)
        for trade in self._tradespending:
            self.notify_trade(trade)
            for analyzer in self.analyzers:
                analyzer._notify_trade(trade)
            for analyzer in self._slave_analyzers:
                analyzer._notify_trade(trade)

        if qorders:
            return  # cash is notified on a regular basis

        # Per-bar cash/value notifications — use direct attributes (no method/property overhead)
        broker = self.broker
        cash = broker.cash           # direct attr, same as getcash()
        value = broker._value        # direct attr, same as getvalue()
        fundvalue = broker._fundval  # direct attr, same as fundvalue property
        fundshares = broker._fundshares  # direct attr, same as fundshares property

        self.notify_cashvalue(cash, value)
        self.notify_fund(cash, value, fundvalue, fundshares)

        # Lazy setup: pre-compute which analyzers have child analyzers
        # (affects whether we can call notify_* directly or need _notify_* dispatch)
        if self._aurora_notify_lists is None:
            self._aurora_notify_lists = (
                [a for a in self.analyzers if a._children],      # need full dispatch
                [a for a in self.analyzers if not a._children],  # direct call safe
                [a for a in self._slave_analyzers if a._children],
                [a for a in self._slave_analyzers if not a._children],
            )

        a_dispatch, a_direct, s_dispatch, s_direct = self._aurora_notify_lists

        # Analyzers with children: full dispatch (preserves child notification)
        for analyzer in a_dispatch:
            analyzer._notify_cashvalue(cash, value)
            analyzer._notify_fund(cash, value, fundvalue, fundshares)
        # Analyzers without children: direct call (skips empty _children loop + wrapper overhead)
        for analyzer in a_direct:
            analyzer.notify_cashvalue(cash, value)   # saves 2 function call layers
            analyzer.notify_fund(cash, value, fundvalue, fundshares)  # saves wrapper layer

        for analyzer in s_dispatch:
            analyzer._notify_cashvalue(cash, value)
            analyzer._notify_fund(cash, value, fundvalue, fundshares)
        for analyzer in s_direct:
            analyzer.notify_cashvalue(cash, value)
            analyzer.notify_fund(cash, value, fundvalue, fundshares)

    def _stop(self):
        # A failing strategy/analyzer stop must not prevent the remaining
        # analyzers from closing or leave data in the execution stage.
        stops = [analyzer._stop for analyzer in self.analyzers]
        stops.extend(analyzer._stop for analyzer in self._slave_analyzers)
        stops.append(self._stage1)
        with CleanupOnExit(stops):
            self.stop()
