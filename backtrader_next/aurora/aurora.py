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
from ..utils.datasync import DataSynchronizer, home_indicators
from ..utils.notifications import notify_broker
from ..nplot.utils import gen_timestamp
from ._lifecycle import CleanupOnExit


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
    - Engine/strategy timers, writers and cheat-on-open callbacks are unsupported
    - Standard indicator support is limited to preloaded runonce execution
    - Use AuroraStrategy and Aurora feeds; stepping-only indicators are unsupported

    Existing Cerebro strategies require adaptation. Similar method names do
    not imply support for Cerebro's complete indicator or execution lifecycle.
    See docs/aurora/README.md for migration guidance.
    
    **Params:**
    
      - ``preload`` (default: ``True``) - Must be True; data is preloaded
      
      - ``runonce`` (default: ``True``) - Must be True; vectorized mode only
      
      - ``stdstats`` (default: ``False``) - Must be False; automatic standard
        observers are not supported
      
      - ``stats`` (default: ``True``) - Create a fresh Eq named ``eq`` per
        strategy/run unless already registered; keep engine configuration
        unchanged. Explicit analyzers are retained when stats is False.
      
      - ``lookahead`` (default: ``0``) - Must be 0; extra buffers are unsupported
      
      - ``tz`` (default: ``None``) - Must be None; no engine timezone conversion
      
      - ``maxcpus`` (default: ``1``) - Maximum CPU cores for optimization (None = all cores)
      
      - ``optdatas`` (default: ``True``) - Optimize data handling in multiprocessing mode
    '''
    
    params = (
        ('preload', True),          # Always True
        ('runonce', True),          # Always True  
        ('stdstats', False),        # Automatic standard observers unsupported
        ('stats', True),            # Eq analyzer
        ('lookahead', 0),           # Extra lookahead buffers unsupported
        ('tz', None),               # Engine timezone conversion unsupported
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
        self._validate_parameters(self.p._getkwargs())

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
        
        # Flags (always in runonce/preload mode)
        self._dopreload = True
        self._dorunonce = True
        self._dolive = False
        self._dooptimize = False  # Optimization mode flag
        self._run_cleanup_complete = False
        
        # Strategy counter (for _id assignment)
        self._init_stcount()
    
    @staticmethod
    def _validate_parameters(parameters):
        required = (
            ('preload', True), ('runonce', True), ('stdstats', False),
            ('lookahead', 0), ('tz', None),
        )
        for name, expected in required:
            value = parameters[name]
            unsupported = value is not None if expected is None else value != expected
            if unsupported:
                raise ValueError('Aurora supports only {}={!r}; got {!r}'.format(
                    name, expected, value))

    def _disable_runonce(self, indicator=None):
        name = type(indicator).__name__ if indicator is not None else 'The indicator'
        raise NotImplementedError(
            '{} requires runonce=False (_nextforce=True); Aurora supports only '
            'runonce=True. Use Cerebro for stepping-only indicators.'.format(name))

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
            strategy: AuroraStrategy subclass (not instance) with standard
                runonce graphs or native Aurora indicators
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
    
    def run(self, **kwargs):
        '''
        Execute backtesting
        
        This is the main method that runs all strategies with all data feeds.
        
        Args:
            **kwargs: Override declared engine parameters. Unsupported values
                and unknown names are rejected before starting resources.
            
        Returns:
            List[Strategy]: List of executed strategy instances with results
            
        Example:
            >>> aurora = Aurora()
            >>> aurora.adddata(data)
            >>> aurora.addstrategy(MyStrategy)
            >>> results = aurora.run()
            >>> print(results[0].analyzers.sharpe.get_analysis())
        '''
        parameters = self.params._getkwargs()
        unknown = set(kwargs).difference(parameters)
        if unknown:
            raise TypeError('Unknown Aurora.run() parameter(s): {}'.format(
                ', '.join(sorted(unknown))))
        parameters.update(kwargs)
        self._validate_parameters(parameters)

        # Apply a valid batch atomically, including when no data is attached yet.
        for key, val in kwargs.items():
            setattr(self.params, key, val)

        self.runstrats = list()
        if not self.datas:
            return []
        
        # Ensure we have at least one strategy
        if not self.strats:
            from ..strategy import Strategy
            self.addstrategy(Strategy)
        
        # Execute strategies (with optimization support)
        iterstrats = itertools.product(*self.strats)
        
        # The parent owns preloaded feeds and the progress bar during native
        # multiprocessing optimization. Workers manage their own run resources.
        progress = None
        data_stops = []
        progress_stops = []
        self._run_cleanup_complete = False
        try:
            with CleanupOnExit(itertools.chain(data_stops, progress_stops)):
                if self._dooptimize:
                    strats_total = math.prod(len(lst) for lst in self.strats)
                    progress = tqdm(total=strats_total, desc="Optimization...")
                    progress_stops.append(progress.close)

                use_multiprocessing = self._dooptimize and self.p.maxcpus != 1
                if not use_multiprocessing:
                    for iterstrat in iterstrats:
                        runstrat = self.runstrategies(iterstrat)
                        self.runstrats.append(runstrat)
                        if self._dooptimize:
                            progress.update(1)
                            for cb in self.optcbs:
                                cb(runstrat)
                else:
                    if self.p.optdatas and self._dopreload and self._dorunonce:
                        for data in self.datas:
                            data.reset()
                            data_stops.append(data.stop)
                            data._start()
                            data.preload()

                    with multiprocessing.Pool(self.p.maxcpus or None) as pool:
                        for result in pool.imap(self, iterstrats):
                            self.runstrats.append(result)
                            progress.update(1)
                            for cb in self.optcbs:
                                cb(result)
                        pool.close()
                        pool.join()
        finally:
            self._run_cleanup_complete = True
        
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
        self._run_cleanup_complete = False
        strategy_stops = []
        data_stops = [data.stop for data in self.datas] if predata else []
        broker_stops = []
        try:
            with CleanupOnExit(itertools.chain(strategy_stops, data_stops, broker_stops)):
                self._validate_parameters(self.p._getkwargs())
                # Register shutdown before startup to cover partial initialization.
                broker_stops.append(self._broker.stop)
                self._broker.start()

                if not predata:
                    for data in self.datas:
                        data.reset()
                        data_stops.append(data.stop)
                        data._start()
                        if self._dopreload:
                            data.preload()

                defaultsizer = self.sizers.get(None, (None, None, None))
                for idx, (stratcls, sargs, skwargs) in enumerate(iterstrat):
                    skwargs = dict(skwargs, _cerebro=self)
                    sargs_list = list(self.datas) + list(sargs)
                    strat = stratcls(*sargs_list, **skwargs)
                    strat.broker = self._broker

                    for ancls, anargs, ankwargs in self.analyzers:
                        strat._addanalyzer(ancls, *anargs, **ankwargs)

                    if self.p.stats and 'eq' not in strat.analyzers.getnames():
                        from ..analyzers import Eq
                        strat._addanalyzer(Eq, _name='eq')

                    for multi, obscls, obargs, obkwargs in self.observers:
                        strat._addobserver(multi, obscls, *obargs, **obkwargs)

                    sizer, sargs_sz, skwargs_sz = self.sizers.get(idx, defaultsizer)
                    if sizer is not None:
                        strat._addsizer(sizer, *sargs_sz, **skwargs_sz)

                    strategy_stops.append(strat._stop)
                    strat._start()
                    runstrats.append(strat)

                if runstrats:
                    self._runonce(runstrats)
        finally:
            # The optimizer must not stop these resources a second time.
            self._run_cleanup_complete = True

        return runstrats
    
    def _runonce(self, runstrats):
        """Prepare indicator graphs and execute synchronized preloaded bars."""
        # Prepare every registered graph through the standard dependency lifecycle.
        for strat in runstrats:
            if strat._ind_iterator or strat._obs_iterator:
                strat._once()
                # Next-only parents can leave nested outputs advanced after
                # calculation. All output clocks must start the trading loop
                # at home, including children not exposed as strategy roots.
                home_indicators(strat)

        # Calculation (including next-only fallbacks) can move shared inputs.
        # Rewind every feed after all strategies have prepared their graphs.
        for data in self.datas:
            data.home()

        # Home feeds before resetting strategy buffers; keep calculated outputs.
        for strat in runstrats:
            strat.reset()
        
        with DataSynchronizer(self, runstrats) as synchronizer:
            self._runonce_loop(runstrats, synchronizer)

    def _runonce_loop(self, runstrats, synchronizer):
        """Process each delivered clock tick once, in broker/strategy order."""
        broker_notify = self._brokernotify
        strategy_ticks = tuple(strategy._oncepost for strategy in runstrats)
        for dt0, dts in synchronizer.bars():
            broker_notify()
            for oncepost in strategy_ticks:
                oncepost(dt0, dts)
    
    def _brokernotify(self):
        notify_broker(self)

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
        self._validate_parameters(self.p._getkwargs())
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
        Return strategy statistics, or an empty Series before any bars run.

        Multiple strategies retain the existing behavior: use the first
        strategy's Eq statistics and the "Multiple Strategies" description.
        '''
        flat_runstrats = [strat for stratlist in self.runstrats for strat in stratlist]
        if not flat_runstrats or not any(len(strat) for strat in flat_runstrats):
            return pd.Series(dtype=object)
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
