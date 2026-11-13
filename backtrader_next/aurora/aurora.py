#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Aurora - Optimized Backtesting Engine
# Copyright (C) 2026
#
# Lightweight engine for backtesting trading strategies.
# Works ONLY in runonce mode (vectorized computations).
# Supports ONLY backtesting mode (no live trading).
# Uses optimized AuroraDataFeed with unified index for all OHLCV elements.
#
###############################################################################
from __future__ import (absolute_import, division, print_function, unicode_literals)

import collections
import itertools
import math
import datetime
import sys
import multiprocessing
import pandas as pd
from .. import optimization as _optimization
from tqdm import tqdm

try:  # For new Python versions
    collectionsAbc = collections.abc  # collections.Iterable -> collections.abc.Iterable
except AttributeError:  # For old Python versions
    collectionsAbc = collections  # Используем collections.Iterable

from ..metabase import MetaParams
from ..utils.py3 import with_metaclass, string_types
from ..brokers import BackBroker
from ..utils import OrderedDict
from ..utils.datasync import DataSynchronizer
from ..nplot.utils import gen_timestamp


class Aurora(with_metaclass(MetaParams, object)):
    '''
    Aurora - Optimized backtesting engine (Cerebro API subset)
    
    This is a lightweight engine designed specifically for fast backtesting.
    
    **Key Features:**
    - Works ONLY in runonce mode (vectorized execution)
    - Supports ONLY backtesting (no live trading)
    - Uses optimized AuroraDataFeed with unified index
    - Selected Cerebro-style setup and trading APIs for adapted strategies
    
    **Limitations:**
    - No live trading support
    - No replay/resample modes
    - No runnext mode (always runonce)
    - Simplified timer API
    - Standard bt.ind.* and bt.nind.* indicators are not supported
    - Use AuroraStrategy, Aurora feeds, and aurora.indicators.*

    Existing Cerebro strategies require adaptation. Similar method names do
    not imply support for Cerebro's complete indicator or execution lifecycle.
    See docs/aurora/README.md for migration guidance.
    
    **Params:**
    
      - ``preload`` (default: ``True``) - Always True, data is preloaded
      
      - ``runonce`` (default: ``True``) - Always True, vectorized mode only
      
      - ``stdstats`` (default: ``False``) - Add standard observers (Broker, Trades, BuySell)
      
      - ``stats`` (default: ``True``) - Create a fresh Eq named ``eq`` per
        strategy/run unless already registered; keep engine configuration
        unchanged. Explicit analyzers are retained when stats is False.
      
      - ``lookahead`` (default: ``0``) - Lookahead bars for indicators
      
      - ``tz`` (default: ``None``) - Global timezone for strategies
      
      - ``maxcpus`` (default: ``None``) - Maximum CPU cores for optimization (None = all cores)
      
      - ``optdatas`` (default: ``True``) - Optimize data handling in multiprocessing mode
    '''
    
    params = (
        ('preload', True),          # Always True
        ('runonce', True),          # Always True  
        ('stdstats', False),        # Standard observers
        ('stats', True),            # Eq analyzer
        ('lookahead', 0),           # Lookahead bars
        ('tz', None),               # Global timezone
        ('quicknotify', False),     # Quick broker notifications
        ('maxcpus', 1),             # Maximum CPUs for optimization (1=single, 2/3/4/...=multi, None=all cores)
        ('optdatas', True),         # Optimize data in multiprocessing
    )

    def __init__(self, broker=None):
        '''
        Initialize Aurora engine
        
        Args:
            broker: Broker instance (default: BackBroker). Only backtesting brokers supported.
        '''
        # Data management
        self.datas = list()
        self.datasbyname = collections.OrderedDict()
        self._dataid = 0
        
        # Strategy management
        self.strats = list()
        self.runningstrats = list()
        self.runstrats = list()
        self.optcbs = list()  # Optimization callbacks
        
        # Broker (only BackBroker for backtesting)
        self._broker = broker or BackBroker()
        self._broker.cerebro = self
        
        # Analyzers, Observers, and Sizers
        self.analyzers = list()
        _optimization.reset_diagnostics(self)
        self.observers = list()
        self.sizers = dict()  # {idx or None: (sizercls, args, kwargs)}
        
        # Statistics
        self._statistics = None
        
        # Flags (always in runonce/preload mode)
        self._dopreload = True
        self._dorunonce = True
        self._dolive = False
        self._dooptimize = False  # Optimization mode flag
        
        # Strategy counter (for _id assignment)
        self._init_stcount()
    
    def _init_stcount(self):
        """Initialize strategy counter"""
        self.stcount = 0
    
    def _next_stid(self):
        """Get next strategy ID"""
        self.stcount += 1
        return self.stcount
    
    def __call__(self, iterstrat):
        '''
        Used during optimization to pass Aurora over the multiprocessing
        module without complaints
        '''
        predata = self.p.optdatas and self._dopreload and self._dorunonce
        return self.runstrategies(iterstrat, predata=predata)
    
    def __getstate__(self):
        '''
        Used during optimization to prevent optimization result `runstrats`
        and callbacks `optcbs` from being pickled to subprocesses.
        Callbacks will be called in the main process after receiving results.
        '''
        rv = vars(self).copy()
        if 'runstrats' in rv:
            del(rv['runstrats'])
        # Don't pickle callbacks - they will be called in main process
        if 'optcbs' in rv:
            del(rv['optcbs'])
        return rv
        
    def adddata(self, data, name=None):
        '''
        Add a Data Feed instance to Aurora
        
        Args:
            data: AuroraDataBase instance, such as AuroraPandasData or AuroraCSVData
            name: Optional name for the data feed (for reference/plotting)
            
        Returns:
            data: The added data feed instance
            
        Example:
            >>> aurora = Aurora()
            >>> data = AuroraPandasData(dataframe=df, name='AAPL')
            >>> aurora.adddata(data)
        '''
        if name is not None:
            data._name = name
        
        self._dataid += 1
        data._id = self._dataid
        data.setenvironment(self)
        
        self.datas.append(data)
        self.datasbyname[data._name] = data
        
        return data
    
    def addstrategy(self, strategy, *args, **kwargs):
        '''
        Add a Strategy class for execution
        
        Args:
            strategy: AuroraStrategy subclass (not instance) using Aurora indicators
            *args: Positional arguments passed to strategy __init__
            **kwargs: Keyword arguments passed to strategy __init__
            
        Returns:
            int: Index of the added strategy (for referencing)
            
        Example:
            >>> aurora = Aurora()
            >>> aurora.addstrategy(MyStrategy, period=20, fast=10, slow=30)
        '''
        self.strats.append([(strategy, args, kwargs)])
        return len(self.strats) - 1
    
    @staticmethod
    def iterize(iterable):
        '''
        Handy function which turns things into things that can be iterated upon
        including iterables
        '''
        niterable = list()
        for elem in iterable:
            if isinstance(elem, string_types):
                elem = (elem,)
            elif not isinstance(elem, collectionsAbc.Iterable):
                elem = (elem,)

            niterable.append(elem)

        return niterable
    
    def optcallback(self, cb):
        '''
        Add a callback for optimization results
        
        The callback will be called for each completed strategy run during optimization.
        
        Args:
            cb: Callable that accepts a strategy instance
            
        Example:
            >>> def mycallback(strategy):
            ...     print(f"Sharpe: {strategy.analyzers.sharpe.get_analysis()['sharperatio']}")
            >>> aurora.optcallback(mycallback)
        
        The signature: cb(strategy)
        '''
        self.optcbs.append(cb)
    
    def optstrategy(self, strategy, *args, **kwargs):
        '''
        Add a Strategy class for optimization. Instantiation happens during run().

        args and kwargs MUST BE iterables which hold the values to check.

        Example: if a Strategy accepts a parameter ``period``, for optimization
        purposes the call to ``optstrategy`` looks like:

          - aurora.optstrategy(MyStrategy, period=(15, 25))

        This will execute an optimization for values 15 and 25. Whereas

          - aurora.optstrategy(MyStrategy, period=range(15, 25))

        will execute MyStrategy with ``period`` values 15 -> 25 (25 not
        included, because ranges are semi-open in Python)

        If a parameter is passed but shall not be optimized the call looks
        like:

          - aurora.optstrategy(MyStrategy, period=(15,))

        Notice that ``period`` is still passed as an iterable ... of just 1
        element

        ``Aurora`` will anyhow try to identify situations like:

          - aurora.optstrategy(MyStrategy, period=15)

        and will create an internal pseudo-iterable if possible
        '''
        self._dooptimize = True
        args = self.iterize(args)
        optargs = list(itertools.product(*args))

        optkeys = list(kwargs)

        vals = self.iterize(kwargs.values())
        optvals = itertools.product(*vals)

        okwargs1 = map(zip, itertools.repeat(optkeys), optvals)

        optkwargs = list(map(dict, okwargs1))

        it = list(itertools.product([strategy], optargs, optkwargs))
        self.strats.append(it)
    
    def addanalyzer(self, ancls, *args, **kwargs):
        '''
        Add an Analyzer class to the engine
        
        Analyzers are instantiated and attached to strategies during run()

        Register Eq with its default name or _name='eq' to configure the
        equity analyzer used by stats=True without adding a second one.
        
        Args:
            ancls: Analyzer class to instantiate
            *args: Positional arguments for analyzer
            **kwargs: Keyword arguments for analyzer
            
        Example:
            >>> aurora.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
            >>> aurora.addanalyzer(bt.analyzers.DrawDown)
        '''
        self.analyzers.append((ancls, args, kwargs))
    
    def addobserver(self, obscls, *args, **kwargs):
        '''
        Add an Observer class to the engine
        
        Observers track strategy execution and are useful for plotting
        
        Args:
            obscls: Observer class to instantiate
            *args: Positional arguments for observer
            **kwargs: Keyword arguments for observer
            
        Example:
            >>> aurora.addobserver(bt.observers.Broker)
            >>> aurora.addobserver(bt.observers.Trades)
        '''
        self.observers.append((False, obscls, args, kwargs))
    
    def addsizer(self, sizercls, *args, **kwargs):
        '''
        Add a Sizer class as the default sizer for all strategies
        
        The sizer determines position sizing for trades. This sets
        the default sizer that will be used by all strategies unless
        overridden with addsizer_byidx().
        
        Args:
            sizercls: Sizer class to instantiate
            *args: Positional arguments for sizer
            **kwargs: Keyword arguments for sizer
            
        Example:
            >>> aurora.addsizer(bt.sizers.FixedSize, stake=10)
            >>> aurora.addsizer(SimpleSizer, percents=90)
        '''
        self.sizers[None] = (sizercls, args, kwargs)
    
    def addsizer_byidx(self, idx, sizercls, *args, **kwargs):
        '''
        Add a Sizer class for a specific strategy by index
        
        This allows setting different sizers for different strategies.
        The idx should match the index returned by addstrategy().
        
        Args:
            idx: Strategy index (from addstrategy return value)
            sizercls: Sizer class to instantiate
            *args: Positional arguments for sizer
            **kwargs: Keyword arguments for sizer
            
        Example:
            >>> idx = aurora.addstrategy(MyStrategy)
            >>> aurora.addsizer_byidx(idx, bt.sizers.PercentSizer, percents=50)
        '''
        self.sizers[idx] = (sizercls, args, kwargs)
    
    def setbroker(self, broker):
        '''
        Set a specific broker instance
        
        Args:
            broker: BackBroker instance (only backtesting brokers)
            
        Returns:
            broker: The set broker instance
            
        Note:
            Only BackBroker and its derivatives are supported (no live brokers)
        '''
        self._broker = broker
        broker.cerebro = self
        return broker
    
    def getbroker(self):
        '''
        Get the current broker instance
        
        Returns:
            broker: Current BackBroker instance
        '''
        return self._broker
    
    @property
    def broker(self):
        '''
        Property accessor for broker
        
        Returns:
            broker: Current BackBroker instance
        '''
        return self._broker
    
    @broker.setter
    def broker(self, value):
        '''
        Property setter for broker
        
        Args:
            value: BackBroker instance to set
        '''
        self.setbroker(value)
    
    @property
    def statistics(self):
        '''
        Get backtesting statistics as pandas Series
        
        Returns:
            pd.Series: Statistics from Eq analyzer (equity, drawdown, etc.)
            
        Note:
            Available only after run() has completed
        '''
        return self._statistics
    
    def run(self, **kwargs):
        '''
        Execute backtesting
        
        This is the main method that runs all strategies with all data feeds.
        
        Args:
            **kwargs: Override default parameters (preload, runonce, etc.)
            
        Returns:
            List[Strategy]: List of executed strategy instances with results
            
        Example:
            >>> aurora = Aurora()
            >>> aurora.adddata(data)
            >>> aurora.addstrategy(MyStrategy)
            >>> results = aurora.run()
            >>> print(results[0].analyzers.sharpe.get_analysis())
        '''
        # Validate that we have data
        if not self.datas:
            return []
        
        # Override parameters if provided
        pkeys = self.params._getkeys()
        for key, val in kwargs.items():
            if key in pkeys:
                setattr(self.params, key, val)
        
        # Ensure we have at least one strategy
        if not self.strats:
            from ..strategy import Strategy
            self.addstrategy(Strategy)
        
        # Execute strategies (with optimization support)
        iterstrats = itertools.product(*self.strats)
        self.runstrats = list()
        
        # Create progress bar for optimization
        progress = None
        strats_total = 0
        if self._dooptimize:
            strats_total = [len(lst) for lst in self.strats]
            strats_total = math.prod(strats_total)
            progress = tqdm(total=strats_total, desc="Optimization...")
        
        # Execute strategies: single-process or multi-process
        # maxcpus=1 (default) -> single process
        # maxcpus=2,3,4,... -> multi-process with specified cores
        # maxcpus=None -> multi-process with all cores
        use_multiprocessing = self._dooptimize and self.p.maxcpus != 1
        
        if not use_multiprocessing:
            # Single process mode (default for non-optimization or maxcpus=1)
            for iterstrat in iterstrats:
                runstrat = self.runstrategies(iterstrat)
                self.runstrats.append(runstrat)
                
                # Update progress and call callbacks for optimization
                if self._dooptimize:
                    if progress is not None:
                        progress.update(1)
                    for cb in self.optcbs:
                        cb(runstrat)  # callback receives finished strategy
        else:
            # Multi-process mode for optimization
            if self.p.optdatas and self._dopreload and self._dorunonce:
                # Preload data once for all processes
                for data in self.datas:
                    data.reset()
                    data._start()
                    if self._dopreload:
                        data.preload()
            
            # Use multiprocessing.Pool for parallel optimization
            with multiprocessing.Pool(self.p.maxcpus or None) as pool:
                for r in pool.imap(self, iterstrats):
                    self.runstrats.append(r)
                    if progress is not None:
                        progress.update(1)
                    # Note: callbacks with local functions don't work with multiprocessing
                    for cb in self.optcbs:
                        cb(r)  # callback receives finished strategy
                pool.close()
                pool.join()
            
            if self.p.optdatas and self._dopreload and self._dorunonce:
                # Stop data after all processes complete
                for data in self.datas:
                    data.stop()
        
        # Close progress bar
        if progress is not None:
            progress.close()
        
        # Extract statistics from Eq analyzer (only for single run)
        if self.p.stats and self.runstrats and not self._dooptimize:
            try:
                eq_analyzer = self.runstrats[0][0].analyzers.getbyname('eq')
                if eq_analyzer:
                    analysis = eq_analyzer.get_analysis()
                    self._statistics = pd.Series(analysis) if isinstance(analysis, dict) else None
            except (AttributeError, IndexError):
                pass
        
        # Return results: list of strategies for optimization, single strategy list otherwise
        if not self._dooptimize:
            return self.runstrats[0] if self.runstrats else []
        
        return self.runstrats
    
    def runstrategies(self, iterstrat, predata=False):
        '''
        Internal method to execute a set of strategies
        
        This method:
        1. Initializes broker and data feeds
        2. Instantiates strategies with analyzers/observers
        3. Runs the main _runonce loop
        4. Stops broker and data feeds
        
        Args:
            iterstrat: Iterator of (strategy_class, args, kwargs) tuples
            predata: If True, skip data initialization (already done in parent process)
            
        Returns:
            List[Strategy]: Executed strategy instances
        '''
        self.runningstrats = runstrats = list()
        
        # Start broker
        self._broker.start()
        
        # Initialize and start all data feeds (unless predata is True)
        if not predata:
            for data in self.datas:
                data.reset()
                data._start()
                if self._dopreload:
                    data.preload()
        
        # Get default sizer
        defaultsizer = self.sizers.get(None, (None, None, None))
        
        # Instantiate strategies
        for idx, (stratcls, sargs, skwargs) in enumerate(iterstrat):
            # Pass Aurora instance to strategy
            skwargs['_cerebro'] = self  # Pass Aurora as cerebro
            
            # Prepend datas to args (strategies expect data feeds as first positional args)
            sargs_list = list(self.datas) + list(sargs)
            
            # Now call strategy constructor
            strat = stratcls(*sargs_list, **skwargs)
            
            # Set broker
            strat.broker = self._broker
            
            # Instantiate and attach analyzers
            for ancls, anargs, ankwargs in self.analyzers:
                strat._addanalyzer(ancls, *anargs, **ankwargs)

            # Keep the automatic analyzer local to this strategy/run.
            if self.p.stats and 'eq' not in strat.analyzers.getnames():
                from ..analyzers import Eq
                strat._addanalyzer(Eq, _name='eq')
            
            # Instantiate and attach observers
            for multi, obscls, obargs, obkwargs in self.observers:
                if multi:
                    # Add one observer per data feed
                    for data in self.datas:
                        strat._addobserver(True, obscls, *obargs, data=data, **obkwargs)
                else:
                    # Add single observer
                    strat._addobserver(False, obscls, *obargs, **obkwargs)
            
            # Attach sizer (default or strategy-specific)
            sizer, sargs_sz, skwargs_sz = self.sizers.get(idx, defaultsizer)
            if sizer is not None:
                strat._addsizer(sizer, *sargs_sz, **skwargs_sz)
            
            # Initialize strategy
            strat._start()
            
            runstrats.append(strat)
        
        # Run strategies in runonce mode
        if runstrats:
            self._runonce(runstrats)
            
            # Stop strategies
            for strat in runstrats:
                strat._stop()
        
        # Stop data feeds
        for data in self.datas:
            data.stop()
        
        # Stop broker
        self._broker.stop()
        
        return runstrats
    
    def _runonce(self, runstrats):
        '''
        Main backtesting loop in runonce mode - OPTIMIZED
        
        This is the core algorithm that:
        1. Initializes all strategies (_once method)
        2. Sorts data feeds by timeframe
        3. Advances data in chronological order (checking is_on flag)
        4. Notifies broker of fills/orders
        5. Calls strategy _oncepost() methods with dt0 and dts
        
        Args:
            runstrats: List of strategy instances to execute
        '''
        # Step 1: Reset Aurora data feeds to beginning (use home() to keep data!)
        for data in self.datas:
            data.home()  # Reset position only, keep loaded data
        
        # Step 2: Initialize strategies
        for strat in runstrats:
            strat.reset()
        
        # OPTIMIZATION: Single data feed fast path (most common case)
        if len(self.datas) == 1:
            self._runonce_single(runstrats)
            return
        
        # Multi-data feed path (original logic)
        with DataSynchronizer(self, runstrats) as synchronizer:
            self._runonce_multi(runstrats, synchronizer)
    
    def _runonce_single(self, runstrats):
        '''
        Optimized loop for single data feed - most common case
        
        Removes overhead of multi-data synchronization.
        '''
        data = self.datas[0]
        broker = self._broker
        broker_next = broker.next
        broker_notifs = broker.notifs  # direct deque access — avoids get_notification() + IndexError per bar
        
        # Pre-calculate total bars for fast loop (use _length, not len() which depends on _idx)
        total_bars = data._length
        
        # Cache strategy methods
        strat = runstrats[0] if len(runstrats) == 1 else None
        
        if strat is not None:
            # Single strategy fast path
            strat_oncepost = strat._oncepost
            
            for _ in range(total_bars):
                # Advance data
                data.advance()
                dt0 = data.lines.datetime[0]
                
                # Broker processing  
                broker_next()
                
                # Distribute notifications via direct deque (no IndexError per bar)
                while broker_notifs:
                    order = broker_notifs.popleft()
                    owner = order.owner
                    if owner:
                        owner._addnotification(order)
                
                # Strategy tick
                strat_oncepost(dt0, None)
        else:
            # Multiple strategies
            for _ in range(total_bars):
                # Advance data
                data.advance()
                dt0 = data.lines.datetime[0]
                
                # Broker processing
                broker_next()
                
                # Distribute notifications via direct deque
                while broker_notifs:
                    order = broker_notifs.popleft()
                    owner = order.owner
                    if owner:
                        owner._addnotification(order)
                
                # Strategy ticks
                for strat in runstrats:
                    strat._oncepost(dt0, None)
    
    def _runonce_multi(self, runstrats, synchronizer):
        '''
        Loop for multiple data feeds with synchronization
        '''
        # Sort data feeds by timeframe and compression
        datas = sorted(self.datas, key=lambda x: (x._timeframe, x._compression))
        
        # Get initial datetime peek for each data
        dts = []
        for data in datas:
            try:
                dt = data.advance_peek() if data.is_on else float('inf')
                dts.append(dt)
            except (AttributeError, StopIteration):
                dts.append(float('inf'))
        
        broker = self._broker
        broker_notifs = broker.notifs  # direct deque access — avoids get_notification() + IndexError per bar
        ndatas = len(datas)
        
        # Main execution loop
        while True:
            # Find minimum datetime across all data feeds
            dt0 = min(dts)
            
            # Exit if no more data
            if dt0 == float('inf'):
                break

            synchronizer.datetime = dt0
            
            # Advance data feeds that match current datetime and are active.
            # is_end is checked only right after advance() — avoids 22x attribute
            # lookups per bar for inactive feeds (4.75M saved over full run).
            for i in range(ndatas):
                if dts[i] <= dt0 and datas[i].is_on:
                    try:
                        datas[i].advance()
                    except StopIteration:
                        dts[i] = float('inf')
                        datas[i].is_on = False
                        continue
                    if datas[i].is_end:
                        dts[i] = float('inf')
                        datas[i].is_on = False
            
            # Notify broker (process pending orders, check stops)
            broker.next()
            
            # Distribute notifications via direct deque (no get_notification() call + IndexError per bar)
            while broker_notifs:
                order = broker_notifs.popleft()
                owner = order.owner
                if owner:
                    owner._addnotification(order)
            
            # Call strategies with current datetime and all datetimes
            for strat in runstrats:
                strat._oncepost(dt0, dts)
            
            # Update datetime peek for advanced data feeds
            for i in range(ndatas):
                if not datas[i].is_on:
                    dts[i] = float('inf')
                elif dts[i] <= dt0 or dts[i] == float('inf'):
                    try:
                        dts[i] = datas[i].advance_peek()
                    except (AttributeError, StopIteration):
                        dts[i] = float('inf')
    
    def _brokernotify(self):
        '''
        Process broker notifications
        
        This method:
        - Calls broker.next() to process pending orders
        - Distributes order/trade notifications to strategies
        '''
        # Process broker logic (fills, stops, etc.)
        self._broker.next()
        
        # Get notifications directly from deque (avoids get_notification() + IndexError overhead)
        notifs = self._broker.notifs
        while notifs:
            order = notifs.popleft()
            owner = order.owner
            if owner:
                owner._addnotification(order)
    
    def _normalize_metrics(self, df, metrics_config):
        '''
        Normalize metrics to [0, 1] range for multi-objective optimization
        
        Args:
            df: DataFrame with results
            metrics_config: dict with metric names as keys and (direction, weight) tuples as values
                          direction: 'max' or 'min'
                          weight: float weight for this metric (optional)
        
        Returns:
            DataFrame with normalized metrics
        '''
        import numpy as np
        
        df_norm = df.copy()
        
        for metric, config in metrics_config.items():
            if metric not in df.columns:
                raise ValueError(f"Metric '{metric}' not found in results. Available: {list(df.columns)}")
            
            direction = config[0] if isinstance(config, tuple) else config
            
            values = df[metric].values
            
            # Handle NaN and inf values
            valid_mask = np.isfinite(values)
            if not valid_mask.any():
                df_norm[f'{metric}_normalized'] = 0.0
                continue
            
            valid_values = values[valid_mask]
            min_val = valid_values.min()
            max_val = valid_values.max()
            
            # Normalize to [0, 1]
            if max_val == min_val:
                # All values are the same
                normalized = np.full_like(values, 0.5, dtype=float)
            else:
                normalized = (values - min_val) / (max_val - min_val)
                
                # For minimization objectives, invert the scale
                if direction == 'min':
                    normalized = 1.0 - normalized
            
            # Handle invalid values
            normalized[~valid_mask] = 0.0
            
            df_norm[f'{metric}_normalized'] = normalized
        
        return df_norm
    
    def _calculate_multiobjective_score(self, df, metrics_config):
        '''
        Calculate weighted score for multi-objective optimization
        
        Args:
            df: DataFrame with normalized metrics
            metrics_config: dict with metric names as keys and (direction, weight) tuples as values
        
        Returns:
            Series with weighted scores
        '''
        import numpy as np
        
        # Extract weights or use equal weights
        weights = []
        metric_names = []
        
        for metric, config in metrics_config.items():
            metric_names.append(metric)
            if isinstance(config, tuple) and len(config) > 1:
                weights.append(config[1])
            else:
                weights.append(1.0)
        
        # Normalize weights to sum to 1
        weights = np.array(weights)
        weights = weights / weights.sum()
        
        # Calculate weighted sum of normalized metrics
        score = np.zeros(len(df))
        for metric, weight in zip(metric_names, weights):
            score += df[f'{metric}_normalized'].values * weight
        
        return score
    
    def optimize(self, strategy, 
                 method='grid', 
                 maximize='Sharpe Ratio',
                 constraint=None,
                 max_tries=None,
                 random_state=None,
                 return_heatmap=False,
                 return_optimization=False,
                 maxcpus=1,
                 on_error='raise',
                 **params):
        '''
        Optimize strategy parameters (SAMBO-compatible API)
        
        This method provides an interface similar to backtesting.py's optimize()
        and supports grid search, random search, and SAMBO Bayesian optimization.
        
        Args:
            strategy: Strategy class to optimize
            
            method: Optimization method:
                - 'grid': Grid search (default, exhaustive search)
                - 'random': Random search (Monte Carlo, good for exploration)
                - 'sambo': Bayesian optimization (requires sambo library)
            
            maximize: Name of metric to maximize (default: 'Sharpe Ratio')
                Examples: 'Sharpe Ratio', 'Return (Ann.) [%]', 'Cum Return [%]',
                         'Equity Final [$]', 'Max. Drawdown [%]' (negative, use 'max')
                
                Note: 'Max. Drawdown [%]' is stored as a NEGATIVE value (e.g. -15.3%).
                      Use 'max' direction — the optimizer selects the value closest to 0
                      (smallest absolute drawdown = best).
                
                Multi-objective optimization: Pass dict with metrics and directions:
                    {
                        'Sharpe Ratio': ('max', 0.7),  # maximize with weight 0.7
                        'Max. Drawdown [%]': ('max', 0.3)  # negative → max = closest to 0 = best
                    }
                Or with equal weights (auto-normalized):
                    {
                        'Sharpe Ratio': 'max',
                        'Max. Drawdown [%]': 'max'  # negative → max = smallest abs. drawdown
                    }
                The optimizer will normalize metrics to [0,1] and compute weighted score.
            
            constraint: Optional constraint function taking params object.
                Example: lambda p: p.n_exit < p.n_enter < p.n1 < p.n2
            
            max_tries: Maximum optimization iterations
                - Grid: ignored (all combinations tested)
                - Random: number of random samples (default: 100)
                - SAMBO: number of iterations (default: 50)
            
            random_state: Random seed for reproducibility (random/SAMBO only)
            
            return_heatmap: If True, return parameter heatmap dataframe
            
            return_optimization: If True, return optimization internals (SAMBO only)
            
            maxcpus: Maximum CPU cores for parallel optimization (grid/random only)
                - 1 (default): Single-process (sequential)
                - 2, 3, 4, ...: Multi-process with specified cores
                - None: Use all available CPU cores
                Note: SAMBO optimization cannot be parallelized due to sequential nature
            
            on_error: 'raise' (default) stops at the first exception and preserves
                its type, traceback and parameters in exception.optimization_error.
                'skip' continues and records failures in self.optimization_errors.
                Applies to backtests and constraint callbacks, not invalid search settings.
                KeyboardInterrupt and SystemExit are never treated as failed trials.

            **params: Parameter ranges as (min, max) tuples, discrete values, or fixed values
                For SAMBO: pass (min, max) tuples for optimized params: n1=(10, 100)
                    Fixed (non-optimized) values also supported: stop_loss=50
                For Random: pass (min, max) tuples or iterables; fixed values also supported
                For Grid: pass iterables: n1=range(10, 100, 5) or n1=[10, 20, 30]
        
        Returns:
            Tuple of (best_stats, heatmap, optimize_result):
                - best_stats: pd.Series with best strategy statistics
                - heatmap: pd.DataFrame with all parameter combinations (if return_heatmap=True)
                - optimize_result: optimization internals (if return_optimization=True, SAMBO only)
        
        Diagnostics:
            optimization_errors: List of dicts with params, strategy, stage,
                error_type, exception_module, message and traceback.
            optimization_summary: Counts of successful, failed, constraint_rejected
                and invalid_metrics. Reset for every optimize() call.
            Best statistics include Optimization Successful Runs / Failed Runs;
                best_stats.attrs and heatmap.attrs contain optimization_summary.
            Completed runs with NaN/inf objective metrics count as successful,
                but cannot win. An empty usable result raises OptimizationError.
            SAMBO's max_tries includes rejected constraint evaluations.

        Example (Random Search):
            >>> stats, heatmap = aurora.optimize(
            ...     MyStrategy,
            ...     n1=(10, 100),
            ...     n2=(20, 200),
            ...     constraint=lambda p: p.n1 < p.n2,
            ...     maximize='Sharpe Ratio',
            ...     method='random',
            ...     max_tries=100,
            ...     random_state=42,
            ...     return_heatmap=True
            ... )
        
        Example (SAMBO):
            >>> stats, heatmap, opt = aurora.optimize(
            ...     MyStrategy,
            ...     n1=(10, 100),
            ...     n2=(20, 200),
            ...     constraint=lambda p: p.n1 < p.n2,
            ...     maximize='Sharpe Ratio',
            ...     method='sambo',
            ...     max_tries=40,
            ...     return_heatmap=True,
            ...     return_optimization=True
            ... )
        
        Example (Grid):
            >>> stats = aurora.optimize(
            ...     MyStrategy,
            ...     n1=range(10, 100, 10),
            ...     n2=range(20, 200, 20),
            ...     constraint=lambda p: p.n1 < p.n2,
            ...     maximize='Sharpe Ratio',
            ...     method='grid'
            ... )
        
        Example (Multi-objective):
            >>> # Optimize for both Sharpe Ratio (70%) and Drawdown (30%)
            >>> # Note: 'Max. Drawdown [%]' is negative → use 'max' to select smallest abs. drawdown
            >>> stats, heatmap = aurora.optimize(
            ...     MyStrategy,
            ...     n1=(10, 100),
            ...     n2=(20, 200),
            ...     maximize={
            ...         'Sharpe Ratio': ('max', 0.7),
            ...         'Max. Drawdown [%]': ('max', 0.3)  # negative value → max = best
            ...     },
            ...     method='random',
            ...     max_tries=100,
            ...     return_heatmap=True
            ... )
        '''
        return _optimization.optimize(
            self, strategy, method, maximize, constraint, max_tries, random_state,
            return_heatmap, return_optimization, maxcpus, on_error, params)

    def _run_single_combination(self, args):
        return _optimization.run_single_combination(self, type(self), args)

    def _optimize_random(self, strategy, maximize, constraint, max_tries,
                         random_state, return_heatmap, maxcpus, params,
                         on_error='raise'):
        return _optimization.optimize_random(
            self, strategy, maximize, constraint, max_tries, random_state,
            return_heatmap, maxcpus, params, on_error)

    def _optimize_grid(self, strategy, maximize, constraint, return_heatmap,
                       maxcpus, params, on_error='raise'):
        return _optimization.optimize_grid(
            self, strategy, maximize, constraint, return_heatmap, maxcpus,
            params, on_error)

    def _optimize_sambo(self, strategy, maximize, constraint, max_tries,
                        random_state, return_heatmap, return_optimization,
                        params, on_error='raise'):
        return _optimization.optimize_sambo(
            self, strategy, maximize, constraint, max_tries, random_state,
            return_heatmap, return_optimization, params, on_error)

    def plot(self, iplot=False, start=None, end=None,
             width=1000, height=900, show=True, filename=None, **kwargs):
        '''
        Plots the strategies inside Aurora

        ``iplot``: if ``True`` and running in a ``notebook`` the charts will be
        displayed inline

        ``start``: An index to the datetime line array of the strategy or a
        ``datetime.date``, ``datetime.datetime`` instance indicating the start
        of the plot

        ``end``: An index to the datetime line array of the strategy or a
        ``datetime.date``, ``datetime.datetime`` instance indicating the end
        of the plot

        ``width``: in px of the saved figure

        ``height``: in px of the saved figure
        
        ``show``: whether to display the plot
        
        ``filename``: filename to save the plot (default: auto-generated)

        '''
        from .. import nplot
        plotter = nplot.Plot(**kwargs)

        flat_runstrats = [strat for stratlist in self.runstrats for strat in stratlist]
        if filename is None:
            filename = f"strat_charts_{gen_timestamp()}.html"
        if 'ipykernel' in sys.modules:
            iplot = True
        plotter.plot(flat_runstrats, iplot=iplot, start=start, end=end,
                        width=width, height=height, show=show, filename=filename)

    @property
    def statistics(self) -> pd.Series:
        '''
        Get strategy statistics
        
        Returns:
            pd.Series: Strategy performance statistics
        '''
        flat_runstrats = [strat for stratlist in self.runstrats for strat in stratlist]
        if len(flat_runstrats) == 0:
            return pd.DataFrame.empty()
        if len(flat_runstrats) > 1:
            desc = pd.Series(dtype=object)
            desc.loc["Strategy"] = "Multiple Strategies"
            eq = flat_runstrats[0].analyzers.getbyname('eq')
            stats = eq.compute_stats()
            return pd.concat([desc, stats])
        else:
            return flat_runstrats[0].statistics

    def show_report(self, name=None, filename=None, show=True):
        '''
        Generate and display/save a quantstats-style report
        
        Args:
            name: Report title (default: auto-generated)
            filename: HTML filename to save (default: auto-generated)
            show: Whether to display the report in browser
        '''
        from .. import nplot
        
        flat_runstrats = [strat for stratlist in self.runstrats for strat in stratlist]
        if len(flat_runstrats) == 0:
            return None
        eq = flat_runstrats[0].analyzers.getbyname('eq')
        if eq is None:
            return None
        if name is None:
            name = "Statistics "
            sname = []
            for s in flat_runstrats:
                sname.append(s.__class__.__name__)
            name = f"Statistics {' '.join(sname)} {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if filename is None:
            filename = f"strat_quantstats_{gen_timestamp()}.html"
        iplot = False
        if 'ipykernel' in sys.modules:
            iplot = True

        from .. import nplot
        report_gen = nplot.Statistics()
        report_gen.report(name=name, performance=eq, show=show, filename=filename, iplot=iplot)


# Convenience function for quick backtesting
def quickstart(data, strategy, **kwargs):
    '''
    Quick backtesting function for simple use cases
    
    Args:
        data: AuroraDataBase instance or list of data feeds
        strategy: Strategy class to execute
        **kwargs: Strategy parameters
        
    Returns:
        List[Strategy]: Executed strategy instances
        
    Example:
        >>> data = AuroraPandasData(dataframe=df)
        >>> results = quickstart(data, MyStrategy, period=20)
        >>> print(results[0].analyzers.eq.get_analysis())
    '''
    aurora = Aurora()
    
    # Add data (single or multiple)
    if isinstance(data, (list, tuple)):
        for d in data:
            aurora.adddata(d)
    else:
        aurora.adddata(data)
    
    # Add strategy with parameters
    aurora.addstrategy(strategy, **kwargs)
    
    # Add standard analyzers
    try:
        from .. import analyzers
        aurora.addanalyzer(analyzers.SharpeRatio, _name='sharpe')
        aurora.addanalyzer(analyzers.DrawDown, _name='drawdown')
        aurora.addanalyzer(analyzers.Returns, _name='returns')
    except ImportError:
        pass
    
    # Run and return results
    return aurora.run()


if __name__ == '__main__':
    # Basic usage example
    print("Aurora Engine - Optimized Backtesting")
    print("=" * 50)
    print("\nUsage Example:")
    print("""
    from backtrader_next.aurora import Aurora, AuroraPandasData
    import pandas as pd
    
    # Load data
    df = pd.read_csv('data.csv', parse_dates=['datetime'])
    data = AuroraPandasData(dataframe=df, name='AAPL')
    
    # Create engine
    aurora = Aurora()
    aurora.adddata(data)
    aurora.addstrategy(MyStrategy, period=20)
    
    # Run backtest
    results = aurora.run()
    
    # Get statistics
    print(aurora.statistics)
    """)
