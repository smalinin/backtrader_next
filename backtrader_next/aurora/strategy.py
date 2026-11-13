#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
"""
AuroraStrategy - Base strategy class for Aurora backtesting engine

Provides a strategy base class for Aurora's vectorized execution model, with
familiar trading methods from backtrader_next.Strategy. Strategies must use
Aurora data feeds and indicators from backtrader_next.aurora.indicators;
standard bt.ind.* and bt.nind.* indicators are not supported.
"""

import backtrader_next as bt
from backtrader_next.strategy import Strategy


class AuroraStrategy(Strategy):
    """
    Base strategy class optimized for Aurora backtesting engine.
    
    This class extends backtrader_next.Strategy with Aurora-specific execution.
    It retains trading methods such as buy(), sell(), close(), and cancel(),
    and runs with Aurora's vectorized data feeds and indicator implementations.
    
    Key Features:
    - Familiar order and position APIs from backtrader_next.Strategy
    - Optimized for Aurora's unified array architecture
    - Simplified lifecycle management for runonce mode
    - Direct access to Aurora broker and data feeds
    
    Lifecycle Methods:
    - start(): Called before backtesting begins
    - prenext(): Called for bars before minimum period
    - nextstart(): Called on the minimum period bar
    - next(): Called for each bar after minimum period
    - stop(): Called after backtesting completes
    
    Trading Methods:
    - buy(): Create a buy (long) order
    - sell(): Create a sell (short) order
    - close(): Close existing position
    - cancel(): Cancel a pending order
    
    Properties:
    - position: Current position for default data
    - broker: Reference to the broker instance
    - datas: List of data feeds
    - data: Primary data feed (self.datas[0])
    
    Example:
        ```python
        class MyStrategy(AuroraStrategy):
            params = (
                ('period', 20),
                ('stop_loss', 0.02),
            )
            
            def __init__(self):
                self.sma = None
                
            def start(self):
                # Create Aurora simplified indicators here
                from backtrader_next.aurora.indicators import SMA
                self.sma = SMA(self.data, period=self.p.period)
            
            def next(self):
                if not self.position:
                    if self.sma and self.data.close[0] > self.sma[0]:
                        self.buy()
                else:
                    if self.sma and self.data.close[0] < self.sma[0]:
                        self.sell()
        ```
    
    Notes:
    - Use backtrader_next.aurora.indicators, not bt.ind.* or bt.nind.*
    - Existing Cerebro strategies require adaptation; indicator lifecycle
      compatibility is not provided by inheriting from Strategy
    - The examples create Aurora simplified indicators in start()
    - Always check if indicator exists before accessing: if self.indicator:
    - Aurora runs only in runonce mode - next() is called for each bar
    - Check indicator values after warmup before making trading decisions
    """

    # Class-level defaults ensure these are always found via normal attribute
    # lookup (before __getattr__ in lineseries delegates to self.lines)
    _aurora_min_period_reached = False
    _aurora_analyzers = None
    _aurora_observers = None
    _aurora_notify_lists = None  # lazily populated in _notify() for per-bar optimization

    # Override to add Aurora-specific initialization if needed
    def _aurora_init(self):
        """
        Aurora-specific initialization hook.
        
        This method is called during strategy initialization and can be
        overridden to add Aurora-specific setup logic. By default, it does nothing.
        
        This is useful for Aurora-specific optimizations or setup that shouldn't
        affect strategies used in standard backtrader.
        """
        # Cache frequently accessed attributes for performance
        self._aurora_analyzers = None
        self._aurora_observers = None
        self._aurora_min_period_reached = False
    
    def __init__(self):
        """
        Initialize the strategy.
        
        See start() for an example using Aurora simplified indicators.
        Inheriting this class does not enable standard Cerebro indicators.
        """
        # Initialize Aurora-specific attributes BEFORE parent init
        self._aurora_analyzers = None
        self._aurora_observers = None
        self._aurora_min_period_reached = False
        self._aurora_notify_lists = None  # lazy-init in _notify() for per-bar optimization
        
        super(AuroraStrategy, self).__init__()
        self._aurora_init()
    
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

    def clear(self):
        """
        Aurora-optimized clear: reuses list objects instead of allocating new ones.
        Saves ~452,910 list allocations per run (2 per bar × 226,455 bars).
        """
        if self._orderspending:
            self._orders.extend(self._orderspending)
            self._orderspending.clear()
        if self._tradespending:
            self._tradespending.clear()

    # Lifecycle methods - maintain compatibility with backtrader.Strategy
    # These are already implemented in Strategy base class, but documented here
    # for clarity in Aurora context
    
    def start(self):
        """
        Called right before backtesting begins.
        
        This is the recommended place to:
        - Create Aurora simplified indicators
        - Initialize strategy state
        - Log strategy parameters
        - Set up any required resources
        
        Example:
            ```python
            def start(self):
                from backtrader_next.aurora.indicators import SMA, RSI
                self.sma = SMA(self.data, period=20)
                self.rsi = RSI(self.data, period=14)
                print(f"Starting strategy with period={self.p.period}")
            ```
        """
        pass
    
    def prenext(self):
        """
        Called for bars before minimum period is reached.
        
        During this phase, indicators may not have valid values yet.
        This method is called before the strategy has enough data to start
        trading based on its indicators.
        
        Note: Most strategies don't need to override this. Override next()
        and check indicator values there instead.
        """
        pass
    
    def nextstart(self):
        """
        Called exactly once when minimum period is reached.
        
        This marks the transition from prenext() to next() phase.
        After this call, next() will be called for all subsequent bars.
        
        Default behavior: calls next()
        """
        self.next()
    
    def next(self):
        """
        Called for each bar after minimum period is reached.
        
        This is the main strategy logic method. Implement your trading logic here:
        - Check indicator values
        - Make trading decisions (buy/sell)
        - Manage positions
        - Track state
        
        Example:
            ```python
            def next(self):
                if not self.position:
                    if self.sma and self.data.close[0] > self.sma[0]:
                        self.buy()
                else:
                    if self.sma and self.data.close[0] < self.sma[0]:
                        self.close()
            ```
        """
        pass
    
    def stop(self):
        """
        Called right before backtesting stops.
        
        Use this for:
        - Cleanup operations
        - Final logging
        - Results summary
        - Resource cleanup
        
        Example:
            ```python
            def stop(self):
                print(f"Final portfolio value: {self.broker.getvalue()}")
                print(f"Total trades: {len(self.trades)}")
            ```
        """
        pass
    
    # Trading methods - inherited from Strategy, documented for Aurora context
    
    def buy(self, data=None, size=None, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            parent=None, transmit=True, **kwargs):
        """
        Create a buy (long) order and send it to the broker.
        
        Args:
            data: Data feed to trade (default: self.data)
            size: Position size in units (default: from sizer)
            price: Limit/stop price (default: None for market orders)
            plimit: Limit price for StopLimit orders
            exectype: Order type (Market, Limit, Stop, StopLimit, Close)
            valid: Order validity (None=GTC, datetime, Order.DAY)
            tradeid: Internal trade tracking ID
            oco: Link to OCO (One-Cancels-Other) group
            trailamount: Trailing stop distance (absolute)
            trailpercent: Trailing stop distance (percentage)
            parent: Parent order for bracket orders
            transmit: Transmit immediately (default: True)
            **kwargs: Additional broker-specific parameters
        
        Returns:
            Order instance or None if size is 0
        
        Example:
            ```python
            # Market order with auto-sizing
            self.buy()
            
            # Limit order with specific size
            self.buy(size=100, price=50.0, exectype=bt.Order.Limit)
            
            # Stop order
            self.buy(price=52.0, exectype=bt.Order.Stop)
            ```
        """
        return super(AuroraStrategy, self).buy(
            data=data, size=size, price=price, plimit=plimit,
            exectype=exectype, valid=valid, tradeid=tradeid, oco=oco,
            trailamount=trailamount, trailpercent=trailpercent,
            parent=parent, transmit=transmit, **kwargs
        )
    
    def sell(self, data=None, size=None, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             parent=None, transmit=True, **kwargs):
        """
        Create a sell (short) order and send it to the broker.
        
        Args: Same as buy()
        
        Returns:
            Order instance or None if size is 0
        
        Example:
            ```python
            # Market sell order
            self.sell()
            
            # Limit sell order
            self.sell(size=50, price=55.0, exectype=bt.Order.Limit)
            ```
        """
        return super(AuroraStrategy, self).sell(
            data=data, size=size, price=price, plimit=plimit,
            exectype=exectype, valid=valid, tradeid=tradeid, oco=oco,
            trailamount=trailamount, trailpercent=trailpercent,
            parent=parent, transmit=transmit, **kwargs
        )
    
    def close(self, data=None, size=None, **kwargs):
        """
        Close existing position (counter-trade).
        
        Automatically determines whether to buy or sell based on current position.
        If long, creates a sell order. If short, creates a buy order.
        
        Args:
            data: Data feed to close position for (default: self.data)
            size: Size to close (default: entire position)
            **kwargs: Additional order parameters (see buy/sell)
        
        Returns:
            Order instance or None if no position
        
        Example:
            ```python
            # Close entire position
            self.close()
            
            # Partially close position
            self.close(size=50)
            ```
        """
        return super(AuroraStrategy, self).close(data=data, size=size, **kwargs)
    
    def cancel(self, order):
        """
        Cancel a pending order.
        
        Args:
            order: Order instance to cancel
        
        Example:
            ```python
            def next(self):
                if self.order:  # Have pending order
                    if some_condition:
                        self.cancel(self.order)
                        self.order = None
            ```
        """
        return super(AuroraStrategy, self).cancel(order)
    
    # Properties - inherited from Strategy
    
    @property
    def position(self):
        """
        Current position for default data feed.
        
        Returns:
            Position instance with attributes:
            - size: Position size (positive=long, negative=short, 0=flat)
            - price: Average entry price
            - adjbase: Adjusted base for P&L calculation
        
        Example:
            ```python
            def next(self):
                pos = self.position
                if pos.size > 0:
                    print(f"Long {pos.size} units at {pos.price}")
                elif pos.size < 0:
                    print(f"Short {abs(pos.size)} units at {pos.price}")
                else:
                    print("Flat (no position)")
            ```
        """
        return self.getposition()
    
    # Utility methods for multi-data strategies
    
    def getposition(self, data=None, broker=None):
        """
        Get position for specific data feed.
        
        Args:
            data: Data feed (default: self.data)
            broker: Broker instance (default: self.broker)
        
        Returns:
            Position instance
        """
        return super(AuroraStrategy, self).getposition(data=data, broker=broker)
    
    def getpositionbyname(self, name=None, broker=None):
        """
        Get position by data feed name.
        
        Args:
            name: Data feed name (default: first data)
            broker: Broker instance (default: self.broker)
        
        Returns:
            Position instance
        """
        return super(AuroraStrategy, self).getpositionbyname(name=name, broker=broker)
    
    # Aurora-specific utility methods
    
    def _aurora_log(self, txt, dt=None):
        """
        Aurora-optimized logging helper.
        
        Args:
            txt: Message to log
            dt: Datetime (default: current bar datetime)
        
        Example:
            ```python
            def next(self):
                self._aurora_log(f"Close: {self.data.close[0]:.2f}")
            ```
        """
        dt = dt or self.data.datetime.date(0)
        print(f'{dt.isoformat()} {txt}')
    
    def _get_indicator_status(self):
        """
        Get status information about indicators.
        
        Returns:
            Dict with indicator information for debugging
        
        This is useful for debugging indicator initialization issues.
        """
        status = {
            'total_indicators': 0,
            'valid_indicators': 0,
            'indicators': []
        }
        
        # Get all indicators (attributes that look like indicators)
        for attr_name in dir(self):
            if attr_name.startswith('_'):
                continue
            attr = getattr(self, attr_name)
            # Check if it looks like an indicator (has __getitem__)
            if hasattr(attr, '__getitem__') and hasattr(attr, '_data'):
                status['total_indicators'] += 1
                try:
                    # Try to access current value
                    val = attr[0]
                    status['valid_indicators'] += 1
                    status['indicators'].append({
                        'name': attr_name,
                        'valid': True,
                        'value': val
                    })
                except:
                    status['indicators'].append({
                        'name': attr_name,
                        'valid': False,
                        'value': None
                    })
        
        return status


# Convenience alias
AStrat = AuroraStrategy
