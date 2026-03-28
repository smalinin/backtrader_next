#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from __future__ import (absolute_import, division, print_function, unicode_literals)

from tqdm import tqdm
import datetime
import collections
import itertools
import math
import multiprocessing
import sys
import pandas as pd
import math

try:  # For new Python versions
    collectionsAbc = collections.abc  # collections.Iterable -> collections.abc.Iterable
except AttributeError:  # For old Python versions
    collectionsAbc = collections  # Используем collections.Iterable

import backtrader_next as bt
from .utils.py3 import (with_metaclass, string_types, integer_types)

from . import linebuffer
from . import indicator
from .brokers import BackBroker
from .metabase import MetaParams
from . import observers
from . import analyzers
from .writer import WriterFile
from .utils import OrderedDict, tzparse, num2date, date2num
from .strategy import Strategy, SignalStrategy
from .tradingcal import (TradingCalendarBase, TradingCalendar, PandasMarketCalendar)
from .timer import Timer
from . import nplot
from .nplot.utils import tmpfilename, gen_timestamp

# Defined here to make it pickable. Ideally it could be defined inside Cerebro


class OptReturn(object):
    def __init__(self, params, **kwargs):
        self.p = self.params = params
        for k, v in kwargs.items():
            setattr(self, k, v)


class Cerebro(with_metaclass(MetaParams, object)):
    '''Params:

      - ``preload`` (default: ``True``)

        Whether to preload the different ``data feeds`` passed to cerebro for
        the Strategies

      - ``runonce`` (default: ``True``)

        Run ``Indicators`` in vectorized mode to speed up the entire system.
        Strategies and Observers will always be run on an event based basis

      - ``live`` (default: ``False``)

        If no data has reported itself as *live* (via the data's ``islive``
        method but the end user still want to run in ``live`` mode, this
        parameter can be set to true

        This will simultaneously deactivate ``preload`` and ``runonce``. It
        will have no effect on memory saving schemes.

        Run ``Indicators`` in vectorized mode to speed up the entire system.
        Strategies and Observers will always be run on an event based basis

      - ``maxcpus`` (default: None -> all available cores)

         How many cores to use simultaneously for optimization

      - ``stdstats`` (default: ``False``)

        If True default Observers will be added: Broker (Cash and Value),
        Trades and BuySell

      - ``stats`` (default: ``True``)

        If True default Observers will be added: Broker (Cash and Value),
        Trades and BuySell

      - ``exactbars`` (default: ``False``)

        With the default value each and every value stored in a line is kept in
        memory

        Possible values:
          - ``True`` or ``1``: all "lines" objects reduce memory usage to the
            automatically calculated minimum period.

            If a Simple Moving Average has a period of 30, the underlying data
            will have always a running buffer of 30 bars to allow the
            calculation of the Simple Moving Average

            - This setting will deactivate ``preload`` and ``runonce``
            - Using this setting also deactivates **plotting**

          - ``-1``: datafreeds and indicators/operations at strategy level will
            keep all data in memory.

            For example: a ``RSI`` internally uses the indicator ``UpDay`` to
            make calculations. This subindicator will not keep all data in
            memory

            - This allows to keep ``plotting`` and ``preloading`` active.

            - ``runonce`` will be deactivated

          - ``-2``: data feeds and indicators kept as attributes of the
            strategy will keep all points in memory.

            For example: a ``RSI`` internally uses the indicator ``UpDay`` to
            make calculations. This subindicator will not keep all data in
            memory

            If in the ``__init__`` something like
            ``a = self.data.close - self.data.high`` is defined, then ``a``
            will not keep all data in memory

            - This allows to keep ``plotting`` and ``preloading`` active.

            - ``runonce`` will be deactivated

      ?? - ``objcache`` (default: ``False``)

        Experimental option to implement a cache of lines objects and reduce
        the amount of them. Example from UltimateOscillator::

          bp = self.data.close - TrueLow(self.data)
          tr = TrueRange(self.data)  # -> creates another TrueLow(self.data)

        If this is ``True`` the 2nd ``TrueLow(self.data)`` inside ``TrueRange``
        matches the signature of the one in the ``bp`` calculation. It will be
        reused.

        Corner cases may happen in which this drives a line object off its
        minimum period and breaks things and it is therefore disabled.

      - ``writer`` (default: ``False``)

        If set to ``True`` a default WriterFile will be created which will
        print to stdout. It will be added to the strategy (in addition to any
        other writers added by the user code)

      - ``tradehistory`` (default: ``False``)

        If set to ``True``, it will activate update event logging in each trade
        for all strategies. This can also be accomplished on a per strategy
        basis with the strategy method ``set_tradehistory``

      - ``optdatas`` (default: ``True``)

        If ``True`` and optimizing (and the system can ``preload`` and use
        ``runonce``, data preloading will be done only once in the main process
        to save time and resources.

        The tests show an approximate ``20%`` speed-up moving from a sample
        execution in ``83`` seconds to ``66``

      - ``optreturn`` (default: ``True``)

        If ``True`` the optimization results will not be full ``Strategy``
        objects (and all *datas*, *indicators*, *observers* ...) but and object
        with the following attributes (same as in ``Strategy``):

          - ``params`` (or ``p``) the strategy had for the execution
          - ``analyzers`` the strategy has executed

        In most occassions, only the *analyzers* and with which *params* are
        the things needed to evaluate a the performance of a strategy. If
        detailed analysis of the generated values for (for example)
        *indicators* is needed, turn this off

        The tests show a ``13% - 15%`` improvement in execution time. Combined
        with ``optdatas`` the total gain increases to a total speed-up of
        ``32%`` in an optimization run.

      - ``tz`` (default: ``None``)

        Adds a global timezone for strategies. The argument ``tz`` can be

          - ``None``: in this case the datetime displayed by strategies will be
            in UTC, which has been always the standard behavior

          - ``pytz`` instance. It will be used as such to convert UTC times to
            the chosen timezone

          - ``string``. Instantiating a ``pytz`` instance will be attempted.

          - ``integer``. Use, for the strategy, the same timezone as the
            corresponding ``data`` in the ``self.datas`` iterable (``0`` would
            use the timezone from ``data0``)

      - ``cheat_on_open`` (default: ``False``)

        The ``next_open`` method of strategies will be called. This happens
        before ``next`` and before the broker has had a chance to evaluate
        orders. The indicators have not yet been recalculated. This allows
        issuing an orde which takes into account the indicators of the previous
        day but uses the ``open`` price for stake calculations

        For cheat_on_open order execution, it is also necessary to make the
        call ``cerebro.broker.set_coo(True)`` or instantite a broker with
        ``BackBroker(coo=True)`` (where *coo* stands for cheat-on-open) or set
        the ``broker_coo`` parameter to ``True``. Cerebro will do it
        automatically unless disabled below.

      - ``broker_coo`` (default: ``True``)

        This will automatically invoke the ``set_coo`` method of the broker
        with ``True`` to activate ``cheat_on_open`` execution. Will only do it
        if ``cheat_on_open`` is also ``True``

      - ``quicknotify`` (default: ``False``)

        Broker notifications are delivered right before the delivery of the
        *next* prices. For backtesting this has no implications, but with live
        brokers a notification can take place long before the bar is
        delivered. When set to ``True`` notifications will be delivered as soon
        as possible (see ``qcheck`` in live feeds)

        Set to ``False`` for compatibility. May be changed to ``True``

    '''
    params = (
        ('preload', True),
        ('runonce', True),
        ('maxcpus', None),
        ('stdstats', False),
        ('stats', True),
        ('lookahead', 0),
        ('exactbars', False),
        ('optdatas', True),
        ('optreturn', True),
        ('objcache', False),
        ('live', False),
        ('writer', False),
        ('tradehistory', False),
        ('tz', None),
        ('cheat_on_open', False),
        ('broker_coo', True),
        ('quicknotify', False),
    )


    def __init__(self, broker=None, datas=None):
        self._dolive = False
        self._doreplay = False
        self._dooptimize = False
        self.stores = list()
        self.feeds = list()
        self.datas = datas or list()
        self.datasbyname = collections.OrderedDict()
        self.strats = list()
        self.optcbs = list()  # holds a list of callbacks for opt strategies
        self.observers = list()
        self.analyzers = list()
        self.indicators = list()
        self.sizers = dict()
        self.writers = list()
        self.storecbs = list()
        self.datacbs = list()
        self.signals = list()
        self._signal_strat = (None, None, None)
        self._signal_concurrent = False
        self._signal_accumulate = False

        self._dataid = 0

        self._broker = broker or BackBroker()
        self._broker.cerebro = self

        self._tradingcal = None  # TradingCalendar()

        self._pretimers = list()
        self._ohistory = list()
        self._fhistory = None

    @staticmethod
    def iterize(iterable):
        '''Handy function which turns things into things that can be iterated upon
        including iterables
        '''
        niterable = list()
        for elem in iterable:
            if isinstance(elem, string_types):
                elem = (elem,)
            elif not isinstance(elem, collectionsAbc.Iterable):  # Different functions will be called for different Python versions
                elem = (elem,)

            niterable.append(elem)

        return niterable

    def set_fund_history(self, fund):
        '''
        Add a history of orders to be directly executed in the broker for
        performance evaluation

          - ``fund``: is an iterable (ex: list, tuple, iterator, generator)
            in which each element will be also an iterable (with length) with
            the following sub-elements (2 formats are possible)

            ``[datetime, share_value, net asset value]``

            **Note**: it must be sorted (or produce sorted elements) by
              datetime ascending

            where:

              - ``datetime`` is a python ``date/datetime`` instance or a string
                with format YYYY-MM-DD[THH:MM:SS[.us]] where the elements in
                brackets are optional
              - ``share_value`` is an float/integer
              - ``net_asset_value`` is a float/integer
        '''
        self._fhistory = fund

    def add_order_history(self, orders, notify=True):
        '''
        Add a history of orders to be directly executed in the broker for
        performance evaluation

          - ``orders``: is an iterable (ex: list, tuple, iterator, generator)
            in which each element will be also an iterable (with length) with
            the following sub-elements (2 formats are possible)

            ``[datetime, size, price]`` or ``[datetime, size, price, data]``

            **Note**: it must be sorted (or produce sorted elements) by
              datetime ascending

            where:

              - ``datetime`` is a python ``date/datetime`` instance or a string
                with format YYYY-MM-DD[THH:MM:SS[.us]] where the elements in
                brackets are optional
              - ``size`` is an integer (positive to *buy*, negative to *sell*)
              - ``price`` is a float/integer
              - ``data`` if present can take any of the following values

                - *None* - The 1st data feed will be used as target
                - *integer* - The data with that index (insertion order in
                  **Cerebro**) will be used
                - *string* - a data with that name, assigned for example with
                  ``cerebro.addata(data, name=value)``, will be the target

          - ``notify`` (default: *True*)

            If ``True`` the 1st strategy inserted in the system will be
            notified of the artificial orders created following the information
            from each order in ``orders``

        **Note**: Implicit in the description is the need to add a data feed
          which is the target of the orders. This is for example needed by
          analyzers which track for example the returns
        '''
        self._ohistory.append((orders, notify))

    def notify_timer(self, timer, when, *args, **kwargs):
        '''Receives a timer notification where ``timer`` is the timer which was
        returned by ``add_timer``, and ``when`` is the calling time. ``args``
        and ``kwargs`` are any additional arguments passed to ``add_timer``

        The actual ``when`` time can be later, but the system may have not be
        able to call the timer before. This value is the timer value and no the
        system time.
        '''
        pass

    def _add_timer(self, owner, when,
                   offset=datetime.timedelta(), repeat=datetime.timedelta(),
                   weekdays=[], weekcarry=False,
                   monthdays=[], monthcarry=True,
                   allow=None,
                   tzdata=None, strats=False, cheat=False,
                   *args, **kwargs):
        '''Internal method to really create the timer (not started yet) which
        can be called by cerebro instances or other objects which can access
        cerebro'''

        timer = Timer(
            tid=len(self._pretimers),
            owner=owner, strats=strats,
            when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata, cheat=cheat,
            *args, **kwargs
        )

        self._pretimers.append(timer)
        return timer

    def add_timer(self, when,
                  offset=datetime.timedelta(), repeat=datetime.timedelta(),
                  weekdays=[], weekcarry=False,
                  monthdays=[], monthcarry=True,
                  allow=None,
                  tzdata=None, strats=False, cheat=False,
                  *args, **kwargs):
        '''
        Schedules a timer to invoke ``notify_timer``

        Arguments:

          - ``when``: can be

            - ``datetime.time`` instance (see below ``tzdata``)
            - ``bt.timer.SESSION_START`` to reference a session start
            - ``bt.timer.SESSION_END`` to reference a session end

         - ``offset`` which must be a ``datetime.timedelta`` instance

           Used to offset the value ``when``. It has a meaningful use in
           combination with ``SESSION_START`` and ``SESSION_END``, to indicated
           things like a timer being called ``15 minutes`` after the session
           start.

          - ``repeat`` which must be a ``datetime.timedelta`` instance

            Indicates if after a 1st call, further calls will be scheduled
            within the same session at the scheduled ``repeat`` delta

            Once the timer goes over the end of the session it is reset to the
            original value for ``when``

          - ``weekdays``: a **sorted** iterable with integers indicating on
            which days (iso codes, Monday is 1, Sunday is 7) the timers can
            be actually invoked

            If not specified, the timer will be active on all days

          - ``weekcarry`` (default: ``False``). If ``True`` and the weekday was
            not seen (ex: trading holiday), the timer will be executed on the
            next day (even if in a new week)

          - ``monthdays``: a **sorted** iterable with integers indicating on
            which days of the month a timer has to be executed. For example
            always on day *15* of the month

            If not specified, the timer will be active on all days

          - ``monthcarry`` (default: ``True``). If the day was not seen
            (weekend, trading holiday), the timer will be executed on the next
            available day.

          - ``allow`` (default: ``None``). A callback which receives a
            `datetime.date`` instance and returns ``True`` if the date is
            allowed for timers or else returns ``False``

          - ``tzdata`` which can be either ``None`` (default), a ``pytz``
            instance or a ``data feed`` instance.

            ``None``: ``when`` is interpreted at face value (which translates
            to handling it as if it where UTC even if it's not)

            ``pytz`` instance: ``when`` will be interpreted as being specified
            in the local time specified by the timezone instance.

            ``data feed`` instance: ``when`` will be interpreted as being
            specified in the local time specified by the ``tz`` parameter of
            the data feed instance.

            **Note**: If ``when`` is either ``SESSION_START`` or
              ``SESSION_END`` and ``tzdata`` is ``None``, the 1st *data feed*
              in the system (aka ``self.data0``) will be used as the reference
              to find out the session times.

          - ``strats`` (default: ``False``) call also the ``notify_timer`` of
            strategies

          - ``cheat`` (default ``False``) if ``True`` the timer will be called
            before the broker has a chance to evaluate the orders. This opens
            the chance to issue orders based on opening price for example right
            before the session starts
          - ``*args``: any extra args will be passed to ``notify_timer``

          - ``**kwargs``: any extra kwargs will be passed to ``notify_timer``

        Return Value:

          - The created timer

        '''
        return self._add_timer(
            owner=self, when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata, strats=strats, cheat=cheat,
            *args, **kwargs)

    def addtz(self, tz):
        '''
        This can also be done with the parameter ``tz``

        Adds a global timezone for strategies. The argument ``tz`` can be

          - ``None``: in this case the datetime displayed by strategies will be
            in UTC, which has been always the standard behavior

          - ``pytz`` instance. It will be used as such to convert UTC times to
            the chosen timezone

          - ``string``. Instantiating a ``pytz`` instance will be attempted.

          - ``integer``. Use, for the strategy, the same timezone as the
            corresponding ``data`` in the ``self.datas`` iterable (``0`` would
            use the timezone from ``data0``)

        '''
        self.p.tz = tz

    def addcalendar(self, cal):
        '''Adds a global trading calendar to the system. Individual data feeds
        may have separate calendars which override the global one

        ``cal`` can be an instance of ``TradingCalendar`` a string or an
        instance of ``pandas_market_calendars``. A string will be will be
        instantiated as a ``PandasMarketCalendar`` (which needs the module
        ``pandas_market_calendar`` installed in the system.

        If a subclass of `TradingCalendarBase` is passed (not an instance) it
        will be instantiated
        '''
        if isinstance(cal, string_types):
            cal = PandasMarketCalendar(calendar=cal)
        elif hasattr(cal, 'valid_days'):
            cal = PandasMarketCalendar(calendar=cal)

        else:
            try:
                if issubclass(cal, TradingCalendarBase):
                    cal = cal()
            except TypeError:  # already an instance
                pass

        self._tradingcal = cal

    def add_signal(self, sigtype, sigcls, *sigargs, **sigkwargs):
        '''Adds a signal to the system which will be later added to a
        ``SignalStrategy``'''
        self.signals.append((sigtype, sigcls, sigargs, sigkwargs))

    def signal_strategy(self, stratcls, *args, **kwargs):
        '''Adds a SignalStrategy subclass which can accept signals'''
        self._signal_strat = (stratcls, args, kwargs)

    def signal_concurrent(self, onoff):
        '''If signals are added to the system and the ``concurrent`` value is
        set to True, concurrent orders will be allowed'''
        self._signal_concurrent = onoff

    def signal_accumulate(self, onoff):
        '''If signals are added to the system and the ``accumulate`` value is
        set to True, entering the market when already in the market, will be
        allowed to increase a position'''
        self._signal_accumulate = onoff

    def addstore(self, store):
        '''Adds an ``Store`` instance to the if not already present'''
        if store not in self.stores:
            self.stores.append(store)

    def addwriter(self, wrtcls, *args, **kwargs):
        '''Adds an ``Writer`` class to the mix. Instantiation will be done at
        ``run`` time in cerebro
        '''
        self.writers.append((wrtcls, args, kwargs))

    def addsizer(self, sizercls, *args, **kwargs):
        '''Adds a ``Sizer`` class (and args) which is the default sizer for any
        strategy added to cerebro
        '''
        self.sizers[None] = (sizercls, args, kwargs)

    def addsizer_byidx(self, idx, sizercls, *args, **kwargs):
        '''Adds a ``Sizer`` class by idx. This idx is a reference compatible to
        the one returned by ``addstrategy``. Only the strategy referenced by
        ``idx`` will receive this size
        '''
        self.sizers[idx] = (sizercls, args, kwargs)

    def addindicator(self, indcls, *args, **kwargs):
        '''
        Adds an ``Indicator`` class to the mix. Instantiation will be done at
        ``run`` time in the passed strategies
        '''
        self.indicators.append((indcls, args, kwargs))

    def addanalyzer(self, ancls, *args, **kwargs):
        '''
        Adds an ``Analyzer`` class to the mix. Instantiation will be done at
        ``run`` time
        '''
        self.analyzers.append((ancls, args, kwargs))

    def get_stats(self):
        return self.analyzers.getbyname('eq')

    def addobserver(self, obscls, *args, **kwargs):
        '''
        Adds an ``Observer`` class to the mix. Instantiation will be done at
        ``run`` time
        '''
        self.observers.append((False, obscls, args, kwargs))

    def addobservermulti(self, obscls, *args, **kwargs):
        '''
        Adds an ``Observer`` class to the mix. Instantiation will be done at
        ``run`` time

        It will be added once per "data" in the system. A use case is a
        buy/sell observer which observes individual datas.

        A counter-example is the CashValue, which observes system-wide values
        '''
        self.observers.append((True, obscls, args, kwargs))

    def addstorecb(self, callback):
        '''Adds a callback to get messages which would be handled by the
        notify_store method

        The signature of the callback must support the following:

          - callback(msg, *args, **kwargs)

        The actual ``msg``, ``*args`` and ``**kwargs`` received are
        implementation defined (depend entirely on the *data/broker/store*) but
        in general one should expect them to be *printable* to allow for
        reception and experimentation.
        '''
        self.storecbs.append(callback)

    def _notify_store(self, msg, *args, **kwargs):
        for callback in self.storecbs:
            callback(msg, *args, **kwargs)

        self.notify_store(msg, *args, **kwargs)

    def notify_store(self, msg, *args, **kwargs):
        '''Receive store notifications in cerebro

        This method can be overridden in ``Cerebro`` subclasses

        The actual ``msg``, ``*args`` and ``**kwargs`` received are
        implementation defined (depend entirely on the *data/broker/store*) but
        in general one should expect them to be *printable* to allow for
        reception and experimentation.
        '''
        pass

    def _storenotify(self):
        for store in self.stores:
            for notif in store.get_notifications():
                msg, args, kwargs = notif

                self._notify_store(msg, *args, **kwargs)
                for strat in self.runningstrats:
                    strat.notify_store(msg, *args, **kwargs)

    def adddatacb(self, callback):
        '''Adds a callback to get messages which would be handled by the
        notify_data method

        The signature of the callback must support the following:

          - callback(data, status, *args, **kwargs)

        The actual ``*args`` and ``**kwargs`` received are implementation
        defined (depend entirely on the *data/broker/store*) but in general one
        should expect them to be *printable* to allow for reception and
        experimentation.
        '''
        self.datacbs.append(callback)

    def _datanotify(self):
        for data in self.datas:
            for notif in data.get_notifications():
                status, args, kwargs = notif
                self._notify_data(data, status, *args, **kwargs)
                for strat in self.runningstrats:
                    strat.notify_data(data, status, *args, **kwargs)

    def _notify_data(self, data, status, *args, **kwargs):
        for callback in self.datacbs:
            callback(data, status, *args, **kwargs)

        self.notify_data(data, status, *args, **kwargs)

    def notify_data(self, data, status, *args, **kwargs):
        '''Receive data notifications in cerebro

        This method can be overridden in ``Cerebro`` subclasses

        The actual ``*args`` and ``**kwargs`` received are
        implementation defined (depend entirely on the *data/broker/store*) but
        in general one should expect them to be *printable* to allow for
        reception and experimentation.
        '''
        pass

    def adddata(self, data, name=None):
        '''
        Adds a ``Data Feed`` instance to the mix.

        If ``name`` is not None it will be put into ``data._name`` which is
        meant for decoration/plotting purposes.
        '''
        if name is not None:
            data._name = name

        self._dataid += 1
        data._id = self._dataid
        data.setenvironment(self)

        self.datas.append(data)
        self.datasbyname[data._name] = data
        feed = data.getfeed()
        if feed and feed not in self.feeds:
            self.feeds.append(feed)

        if data.islive():
            self._dolive = True

        return data

    def chaindata(self, *args, **kwargs):
        '''
        Chains several data feeds into one

        If ``name`` is passed as named argument and is not None it will be put
        into ``data._name`` which is meant for decoration/plotting purposes.

        If ``None``, then the name of the 1st data will be used
        '''
        dname = kwargs.pop('name', None)
        if dname is None:
            dname = args[0]._dataname
        d = bt.feeds.Chainer(dataname=dname, *args)
        self.adddata(d, name=dname)

        return d

    def rolloverdata(self, *args, **kwargs):
        '''Chains several data feeds into one

        If ``name`` is passed as named argument and is not None it will be put
        into ``data._name`` which is meant for decoration/plotting purposes.

        If ``None``, then the name of the 1st data will be used

        Any other kwargs will be passed to the RollOver class

        '''
        dname = kwargs.pop('name', None)
        if dname is None:
            dname = args[0]._dataname
        d = bt.feeds.RollOver(dataname=dname, *args, **kwargs)
        self.adddata(d, name=dname)

        return d

    def replaydata(self, dataname, name=None, **kwargs):
        '''
        Adds a ``Data Feed`` to be replayed by the system

        If ``name`` is not None it will be put into ``data._name`` which is
        meant for decoration/plotting purposes.

        Any other kwargs like ``timeframe``, ``compression``, ``todate`` which
        are supported by the replay filter will be passed transparently
        '''
        if any(dataname is x for x in self.datas):
            dataname = dataname.clone()

        dataname.replay(**kwargs)
        self.adddata(dataname, name=name)
        self._doreplay = True

        return dataname

    def resampledata(self, dataname, name=None, **kwargs):
        '''
        Adds a ``Data Feed`` to be resample by the system

        If ``name`` is not None it will be put into ``data._name`` which is
        meant for decoration/plotting purposes.

        Any other kwargs like ``timeframe``, ``compression``, ``todate`` which
        are supported by the resample filter will be passed transparently
        '''
        if any(dataname is x for x in self.datas):
            dataname = dataname.clone()

        dataname.resample(**kwargs)
        self.adddata(dataname, name=name)
        self._doreplay = True

        return dataname

    def optcallback(self, cb):
        '''
        Adds a *callback* to the list of callbacks that will be called with the
        optimizations when each of the strategies has been run

        The signature: cb(strategy)
        '''
        self.optcbs.append(cb)

    def optstrategy(self, strategy, *args, **kwargs):
        '''
        Adds a ``Strategy`` class to the mix for optimization. Instantiation
        will happen during ``run`` time.

        args and kwargs MUST BE iterables which hold the values to check.

        Example: if a Strategy accepts a parameter ``period``, for optimization
        purposes the call to ``optstrategy`` looks like:

          - cerebro.optstrategy(MyStrategy, period=(15, 25))

        This will execute an optimization for values 15 and 25. Whereas

          - cerebro.optstrategy(MyStrategy, period=range(15, 25))

        will execute MyStrategy with ``period`` values 15 -> 25 (25 not
        included, because ranges are semi-open in Python)

        If a parameter is passed but shall not be optimized the call looks
        like:

          - cerebro.optstrategy(MyStrategy, period=(15,))

        Notice that ``period`` is still passed as an iterable ... of just 1
        element

        ``backtrader_next`` will anyhow try to identify situations like:

          - cerebro.optstrategy(MyStrategy, period=15)

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

    def addstrategy(self, strategy, *args, **kwargs):
        '''
        Adds a ``Strategy`` class to the mix for a single pass run.
        Instantiation will happen during ``run`` time.

        args and kwargs will be passed to the strategy as they are during
        instantiation.

        Returns the index with which addition of other objects (like sizers)
        can be referenced
        '''
        self.strats.append([(strategy, args, kwargs)])
        return len(self.strats) - 1

    def setbroker(self, broker):
        '''
        Sets a specific ``broker`` instance for this strategy, replacing the
        one inherited from cerebro.
        '''
        self._broker = broker
        broker.cerebro = self
        return broker

    def getbroker(self):
        '''
        Returns the broker instance.

        This is also available as a ``property`` by the name ``broker``
        '''
        return self._broker

    broker = property(getbroker, setbroker)

    def old_plot(self, plotter=None, numfigs=1, iplot=True, start=None, end=None,
             width=16, height=9, dpi=300, tight=True, use=None,
             **kwargs):
        '''
        Plots the strategies inside cerebro

        If ``plotter`` is None a default ``Plot`` instance is created and
        ``kwargs`` are passed to it during instantiation.

        ``numfigs`` split the plot in the indicated number of charts reducing
        chart density if wished

        ``iplot``: if ``True`` and running in a ``notebook`` the charts will be
        displayed inline

        ``use``: set it to the name of the desired matplotlib backend. It will
        take precedence over ``iplot``

        ``start``: An index to the datetime line array of the strategy or a
        ``datetime.date``, ``datetime.datetime`` instance indicating the start
        of the plot

        ``end``: An index to the datetime line array of the strategy or a
        ``datetime.date``, ``datetime.datetime`` instance indicating the end
        of the plot

        ``width``: in inches of the saved figure

        ``height``: in inches of the saved figure

        ``dpi``: quality in dots per inches of the saved figure

        ``tight``: only save actual content and not the frame of the figure
        '''
        if self._exactbars > 0:
            return

        if not plotter:
            from . import plot
            plotter = plot.Plot(**kwargs)

        figs = []
        for stratlist in self.runstrats:
            for si, strat in enumerate(stratlist):
                rfig = plotter.plot(strat, figid=si * 100,
                                    numfigs=numfigs, iplot=iplot,
                                    start=start, end=end, use=use)
                figs.append(rfig)
            plotter.show()
        return figs

    def plot(self, iplot=False, start=None, end=None,
             width=1000, height=900, show=True, filename=None, **kwargs):
        '''
        Plots the strategies inside cerebro

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

        '''
        if self._exactbars > 0:
            return

        # if not plotter:
        #     from . import plot
        from . import nplot
        plotter = nplot.Plot(**kwargs)

        flat_runstrats = [strat for stratlist in self.runstrats for strat in stratlist]
        if filename is None:
            filename = f"strat_charts_{gen_timestamp()}.html"
        iplot = False
        if 'ipykernel' in sys.modules:
            iplot = True
        plotter.plot(flat_runstrats, iplot=iplot, start=start, end=end,
                        width=width, height=height, show=show, filename=filename)

    @property
    def statistics(self) -> pd.Series:
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

        report_gen = nplot.Statistics()
        report_gen.report(name=name, performance=eq, strats=flat_runstrats, show=show, filename=filename, iplot=iplot)
    
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
            
            **params: Parameter ranges as (min, max) tuples, discrete values, or fixed values
                For SAMBO: pass (min, max) tuples for optimized params: n1=(10, 100)
                    Fixed (non-optimized) values also supported: stop_loss=50
                For Random: pass (min, max) tuples or iterables; fixed values also supported
                For Grid: pass iterables: n1=range(10, 100, 5) or n1=[10, 20, 30]
                    Fixed (non-optimized) scalar values also supported: stop_loss=50
        
        Returns:
            Tuple of (best_stats, heatmap, optimize_result):
                - best_stats: pd.Series with best strategy statistics
                - heatmap: pd.DataFrame with all parameter combinations (if return_heatmap=True)
                - optimize_result: optimization internals (if return_optimization=True, SAMBO only)
        
        Example (Random Search):
            >>> stats, heatmap = cerebro.optimize(
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
            >>> stats, heatmap, opt = cerebro.optimize(
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
            >>> stats = cerebro.optimize(
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
            >>> stats, heatmap = cerebro.optimize(
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
        # Validate inputs
        if not params:
            raise ValueError("At least one parameter must be specified for optimization")
        
        method = method.lower()
        if method not in ('grid', 'sambo', 'random'):
            raise ValueError(f"Unknown optimization method: {method}. Use 'grid', 'sambo', or 'random'")
        
        # For SAMBO, check if library is available
        if method == 'sambo':
            try:
                import sambo
            except ImportError:
                raise ImportError(
                    "SAMBO library not installed. Install it with: pip install sambo\n"
                    "Or use method='grid' for grid search optimization"
                )
        
        # Dispatch to appropriate optimization method
        if method == 'sambo':
            return self._optimize_sambo(
                strategy=strategy,
                maximize=maximize,
                constraint=constraint,
                max_tries=max_tries,
                random_state=random_state,
                return_heatmap=return_heatmap,
                return_optimization=return_optimization,
                params=params
            )
        elif method == 'random':
            return self._optimize_random(
                strategy=strategy,
                maximize=maximize,
                constraint=constraint,
                max_tries=max_tries,
                random_state=random_state,
                return_heatmap=return_heatmap,
                maxcpus=maxcpus,
                params=params
            )
        else:  # grid
            return self._optimize_grid(
                strategy=strategy,
                maximize=maximize,
                constraint=constraint,
                return_heatmap=return_heatmap,
                maxcpus=maxcpus,
                params=params
            )

    def _run_single_combination(self, args):
        '''Helper function to run a single parameter combination (for multiprocessing)'''
        strategy, param_dict = args
        
        try:
            # Create fresh Cerebro instance for this run
            cerebro_run = Cerebro()
            cerebro_run.broker.setcash(self.broker.getvalue())
            
            # Copy commission settings
            if hasattr(self.broker, 'comminfo'):
                for name, comminfo in self.broker.comminfo.items():
                    cerebro_run.broker.addcommissioninfo(comminfo, name=name)
            
            # Copy sizer
            if self.sizers:
                for idx, (sizercls, sizerargs, sizerkwargs) in self.sizers.items():
                    if idx is None:
                        cerebro_run.addsizer(sizercls, *sizerargs, **sizerkwargs)
                    else:
                        cerebro_run.addsizer_byidx(idx, sizercls, *sizerargs, **sizerkwargs)
            
            # Copy data feeds
            for data in self.datas:
                cerebro_run.adddata(data)
            
            # Add Eq analyzer by default if not present
            has_eq = any(ancls.__name__ == 'Eq' for ancls, _, _ in self.analyzers)
            if not has_eq:
                cerebro_run.addanalyzer(bt.analyzers.Eq, _name='eq')
            
            # Copy analyzers
            for ancls, anargs, ankwargs in self.analyzers:
                cerebro_run.addanalyzer(ancls, *anargs, **ankwargs)
            
            # Copy observers  
            for multi, obscls, obargs, obkwargs in self.observers:
                cerebro_run.addobserver(obscls, *obargs, **obkwargs)
            
            # Add strategy with current parameters
            cerebro_run.addstrategy(strategy, **param_dict)
            
            # Run
            runstrats = cerebro_run.run()
            if runstrats:
                strat = runstrats[0]
                stats_dict = strat.statistics.to_dict() if hasattr(strat.statistics, 'to_dict') else {}
                
                # Add strategy parameters to stats,
                # excluding large/unpicklable objects (e.g. FuturesList data feeds)
                _EXCLUDED_MODULES = ('backtrader_next',)
                serializable_params = {}
                for k, v in param_dict.items():
                    mod = getattr(type(v), '__module__', '') or ''
                    if any(mod.startswith(m) for m in _EXCLUDED_MODULES):
                        continue  # skip backtrader objects
                    serializable_params[k] = v
                stats_dict.update(serializable_params)
                
                return stats_dict
        except Exception as e:
            # Silently skip failed combinations in multiprocessing
            return None
    
    def _optimize_random(self, strategy, maximize, constraint, max_tries,
                        random_state, return_heatmap, maxcpus, params):
        '''Random search (Monte Carlo) optimization'''
        import numpy as np
        
        # Set random seed for reproducibility
        if random_state is not None:
            np.random.seed(random_state)
        
        # Extract parameter bounds
        param_names = list(params.keys())
        param_ranges = []
        
        for key, value in params.items():
            if isinstance(value, tuple) and len(value) == 2:
                # (min, max) tuple - continuous range
                param_ranges.append(('continuous', value[0], value[1]))
            elif hasattr(value, '__iter__') and not isinstance(value, str):
                # Iterable - discrete values
                param_ranges.append(('discrete', list(value)))
            else:
                param_ranges.append(('value', value))
                # raise ValueError(
                #     f"Parameter '{key}' must be either (min, max) tuple or iterable. Got: {value}"
                # )
        
        # Generate random combinations
        max_tries = max_tries or 100
        combinations = []
        attempts = 0
        max_attempts = max_tries * 100  # Prevent infinite loop
        
        class TempParams:
            pass
        
        seen = set()

        while len(combinations) < max_tries and attempts < max_attempts:
            attempts += 1
            
            # Generate random values for each parameter
            combo = []
            for param_type, *param_info in param_ranges:
                if param_type == 'continuous':
                    min_val, max_val = param_info
                    # Random value in continuous range
                    if isinstance(min_val, int) and isinstance(max_val, int):
                        val = np.random.randint(min_val, max_val + 1)
                    else:
                        val = np.random.uniform(min_val, max_val)
                elif param_type == 'discrete':
                    values = param_info[0]
                    val = np.random.choice(values)
                else:  # value
                    val = param_info[0]
                combo.append(val)
            
            combo_tuple = tuple(combo)

            # Skip duplicate combinations
            if combo_tuple in seen:
                continue
            
            # Check constraint
            if constraint:
                temp = TempParams()
                for name, val in zip(param_names, combo_tuple):
                    setattr(temp, name, val)
                try:
                    if not constraint(temp):
                        continue
                except:
                    continue
            
            seen.add(combo_tuple)
            combinations.append(combo_tuple)
        
        if not combinations:
            raise ValueError(
                "Could not generate any valid parameter combinations. "
                "Check your constraints and parameter ranges."
            )
        
        # Run each combination (with optional multiprocessing)
        all_stats = []
        
        # Prepare arguments for each combination
        param_dicts = [{name: val for name, val in zip(param_names, combo)} for combo in combinations]
        run_args = [(strategy, param_dict) for param_dict in param_dicts]
        
        # Check if multiprocessing should be used
        use_multiprocessing = maxcpus != 1 and len(combinations) > 1
        
        if use_multiprocessing:
            # Parallel execution with multiprocessing
            with multiprocessing.Pool(maxcpus or None) as pool:
                results = list(tqdm(
                    pool.imap(self._run_single_combination, run_args),
                    total=len(run_args),
                    desc="Random Search (parallel)..."
                ))
                all_stats = [r for r in results if r is not None]
        else:
            # Sequential execution
            for args in tqdm(run_args, desc="Random Search..."):
                result = self._run_single_combination(args)
                if result is not None:
                    all_stats.append(result)
        
        # Find best result
        df = pd.DataFrame(all_stats)
        
        # Check if multi-objective optimization
        if isinstance(maximize, dict):
            # Multi-objective optimization
            df = self._normalize_metrics(df, maximize)
            df['_multiobjective_score'] = self._calculate_multiobjective_score(df, maximize)
            best_idx = df['_multiobjective_score'].idxmax()
            best_stats = df.loc[best_idx]
        else:
            # Single-objective optimization
            if maximize not in df.columns:
                raise ValueError(f"Metric '{maximize}' not found. Available: {list(df.columns)}")
            
            # Always maximize: negative metrics (e.g. Drawdown < 0) benefit from idxmax() too
            # (max of negative = closest to 0 = smallest absolute drawdown = best)
            best_idx = df[maximize].idxmax()
            best_stats = df.loc[best_idx]
        
        # Return results
        ret = (best_stats,)
        if return_heatmap:
            ret += (df,)
        
        return ret[0] if len(ret) == 1 else ret
    
    def _optimize_grid(self, strategy, maximize, constraint, return_heatmap, maxcpus, params):
        '''Grid search optimization'''
        # Convert params to iterables
        param_names = list(params.keys())
        param_values = []
        
        for key, value in params.items():
            if isinstance(value, tuple) and len(value) == 2 and not isinstance(value[0], str):
                # Check that it's actually a (min, max) numeric range, not a fixed 2-element value
                try:
                    min_val, max_val = value
                    _ = min_val + max_val  # will raise TypeError for non-numeric
                    # (min, max) tuple - create reasonable grid
                    step = (max_val - min_val) / 10
                    if isinstance(min_val, int) and isinstance(max_val, int):
                        step = max(1, int(step))
                        value = range(min_val, max_val + 1, step)
                    else:
                        import numpy as np
                        value = np.linspace(min_val, max_val, 10)
                except TypeError:
                    pass  # treat as fixed value / iterable below
            
            # Fixed scalar value: iterize wraps it into a 1-element tuple → single grid point
            param_values.append(self.iterize([value])[0])
        
        # Generate all combinations
        import itertools
        combinations = list(itertools.product(*param_values))
        
        # Apply constraint if provided
        if constraint:
            # Create temp params object for constraint checking
            class TempParams:
                pass
            
            filtered_combinations = []
            for combo in combinations:
                temp = TempParams()
                for name, val in zip(param_names, combo):
                    setattr(temp, name, val)
                try:
                    if constraint(temp):
                        filtered_combinations.append(combo)
                except:
                    pass  # Skip invalid combinations
            combinations = filtered_combinations
        
        # Run each combination (with optional multiprocessing)
        all_stats = []
        
        # Prepare arguments for each combination
        param_dicts = [{name: val for name, val in zip(param_names, combo)} for combo in combinations]
        run_args = [(strategy, param_dict) for param_dict in param_dicts]
        
        # Check if multiprocessing should be used
        use_multiprocessing = maxcpus != 1 and len(combinations) > 1
        
        if use_multiprocessing:
            # Parallel execution with multiprocessing
            with multiprocessing.Pool(maxcpus or None) as pool:
                results = list(tqdm(
                    pool.imap(self._run_single_combination, run_args),
                    total=len(run_args),
                    desc="Grid Search (parallel)..."
                ))
                all_stats = [r for r in results if r is not None]
        else:
            # Sequential execution
            for args in tqdm(run_args, desc="Optimization..."):
                result = self._run_single_combination(args)
                if result is not None:
                    all_stats.append(result)
        
        # Find best result
        df = pd.DataFrame(all_stats)
        
        # Check if multi-objective optimization
        if isinstance(maximize, dict):
            # Multi-objective optimization
            df = self._normalize_metrics(df, maximize)
            df['_multiobjective_score'] = self._calculate_multiobjective_score(df, maximize)
            best_idx = df['_multiobjective_score'].idxmax()
            best_stats = df.loc[best_idx]
        else:
            # Single-objective optimization
            if maximize not in df.columns:
                raise ValueError(f"Metric '{maximize}' not found. Available: {list(df.columns)}")
            
            # Always maximize: negative metrics (e.g. Drawdown < 0) benefit from idxmax() too
            # (max of negative = closest to 0 = smallest absolute drawdown = best)
            best_idx = df[maximize].idxmax()
            best_stats = df.loc[best_idx]
        
        # Return results
        ret = (best_stats,)
        if return_heatmap:
            ret += (df,)
        
        return ret[0] if len(ret) == 1 else ret

    def _optimize_sambo(self, strategy, maximize, constraint, max_tries, 
                       random_state, return_heatmap, return_optimization, params):
        '''SAMBO Bayesian optimization'''
        import sambo
        import numpy as np
        
        # Separate optimizable params (min, max) from fixed-value params
        opt_param_names = []   # names of params passed to SAMBO
        fixed_params = {}      # name -> fixed value (not optimized)
        bounds = []
        param_types = {}       # Track if parameter should be int or float

        for key, value in params.items():
            if isinstance(value, tuple) and len(value) == 2:
                # (min, max) tuple - optimizable by SAMBO
                min_val, max_val = value
                param_types[key] = 'int' if (isinstance(min_val, int) and isinstance(max_val, int)) else 'float'
                opt_param_names.append(key)
                bounds.append(value)
            else:
                # Scalar or other constant - fixed, not optimized
                fixed_params[key] = value

        if not opt_param_names:
            raise ValueError(
                "For method='sambo', at least one parameter must be a (min, max) tuple. "
                "All parameters appear to be fixed values."
            )

        bounds = np.array(bounds)

        # Define objective function
        results_cache = []
        # Use moderate penalty to avoid KDE numerical issues
        penalty_base = -1000.0

        def objective(param_array):
            '''Objective function for SAMBO'''
            # Convert optimized params to dict with proper types
            param_dict = {}
            for i, name in enumerate(opt_param_names):
                val = param_array[i] if len(param_array.shape) == 1 else param_array[0, i]
                # Convert to int if parameter bounds were integers
                if param_types[name] == 'int':
                    param_dict[name] = int(round(float(val)))
                else:
                    param_dict[name] = float(val)
            # Merge fixed params
            param_dict.update(fixed_params)
            
            # Check constraint
            if constraint:
                class TempParams:
                    pass
                temp = TempParams()
                for name, val in param_dict.items():
                    setattr(temp, name, val)
                try:
                    if not constraint(temp):
                        # Add small random variance to avoid identical penalties
                        return penalty_base + np.random.uniform(-10.0, 10.0)
                except:
                    return penalty_base + np.random.uniform(-10.0, 10.0)
            
            # Run single combination using unified method
            try:
                stats_dict = self._run_single_combination((strategy, param_dict))
                if not stats_dict:
                    return penalty_base + np.random.uniform(-10.0, 10.0)
                
                # Extract metric - handle both single and multi-objective
                if isinstance(maximize, dict):
                    # Multi-objective: use first metric for SAMBO optimization
                    primary_metric = list(maximize.keys())[0]
                    if primary_metric not in stats_dict:
                        return penalty_base + np.random.uniform(-10.0, 10.0)
                    metric_value = stats_dict[primary_metric]
                    metric_direction = maximize[primary_metric]
                    metric_direction = metric_direction[0] if isinstance(metric_direction, tuple) else metric_direction
                else:
                    # Single-objective
                    if maximize not in stats_dict:
                        return penalty_base + np.random.uniform(-10.0, 10.0)
                    metric_value = stats_dict[maximize]
                    metric_direction = 'max'
                
                # Handle nan/inf - robust checking
                try:
                    metric_float = float(metric_value)
                    if not np.isfinite(metric_float):
                        return penalty_base + np.random.uniform(-10.0, 10.0)
                    metric_value = metric_float
                except (ValueError, TypeError, OverflowError):
                    return penalty_base + np.random.uniform(-10.0, 10.0)
                
                # Cache results (already contains params from _run_single_combination)
                results_cache.append(stats_dict)
                
                # SAMBO minimizes the objective:
                # - 'max' metrics (incl. negative Drawdown): negate so SAMBO finds the max
                # - 'min' metrics: keep as-is
                if metric_direction != 'min':
                    metric_value = -metric_value
                
                # Final check for finite value
                if not np.isfinite(metric_value):
                    return penalty_base + np.random.uniform(-10.0, 10.0)
                
                return float(metric_value)
                
            except Exception as e:
                print(f"Error in backtest: {e}")
                return penalty_base + np.random.uniform(-10.0, 10.0)
        
        # Run SAMBO optimization
        max_tries = max_tries or 50
        
        print(f"Running SAMBO optimization with {max_tries} iterations...")
        
        # Wrap objective to update progress bar on each call
        progress = tqdm(total=max_tries, desc="SAMBO Optimization")
        
        def objective_with_progress(x):
            result = objective(x)
            progress.update(1)
            return result
        
        # Define constraint function for SAMBO
        constraint_func = None
        if constraint:
            def constraint_func(x):
                # Convert to dict with proper types
                param_dict = {}
                for i, name in enumerate(opt_param_names):
                    val = x[i] if len(x.shape) == 1 else x[0, i]
                    # Convert to int if parameter bounds were integers
                    if param_types[name] == 'int':
                        param_dict[name] = int(round(float(val)))
                    else:
                        param_dict[name] = float(val)
                # Merge fixed params
                param_dict.update(fixed_params)
                
                # Check constraint
                class TempParams:
                    pass
                temp = TempParams()
                for name, val in param_dict.items():
                    setattr(temp, name, val)
                try:
                    return constraint(temp)
                except:
                    return False
        
        # Run SAMBO optimization using minimize function
        result = sambo.minimize(
            fun=objective_with_progress,
            bounds=bounds,
            constraints=constraint_func,
            max_iter=max_tries,
            method='sceua',
            rng=random_state
        )
        
        progress.close()
        
        # Extract best parameters from result
        best_params = result.x
        best_value = result.fun
        
        # Find best result from cache
        if results_cache:
            df_cache = pd.DataFrame(results_cache)
            
            # Check if multi-objective optimization
            if isinstance(maximize, dict):
                # Multi-objective optimization - recalculate scores with proper normalization
                df_cache = self._normalize_metrics(df_cache, maximize)
                df_cache['_multiobjective_score'] = self._calculate_multiobjective_score(df_cache, maximize)
                best_idx = df_cache['_multiobjective_score'].idxmax()
                best_stats = df_cache.loc[best_idx]
            else:
                # Single-objective optimization
                # Always maximize: negative metrics (e.g. Drawdown < 0) use idxmax() too
                # (max of negative = closest to 0 = smallest absolute drawdown = best)
                best_idx = df_cache[maximize].idxmax()
                best_stats = df_cache.loc[best_idx]
        else:
            # No valid results - return empty Series
            best_stats = pd.Series({'error': 'No valid results'})
        
        # Return results
        ret = (best_stats,)
        
        if return_heatmap:
            df = pd.DataFrame(results_cache)
            ret += (df,)
        
        if return_optimization:
            ret += (result,)
        
        return ret[0] if len(ret) == 1 else ret

    def __call__(self, iterstrat):
        '''
        Used during optimization to pass the cerebro over the multiprocesing
        module without complains
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

    def runstop(self):
        '''If invoked from inside a strategy or anywhere else, including other
        threads the execution will stop as soon as possible.'''
        self._event_stop = True  # signal a stop has been requested

    def run(self, **kwargs):
        '''The core method to perform backtesting. Any ``kwargs`` passed to it
        will affect the value of the standard parameters ``Cerebro`` was
        instantiated with.

        If ``cerebro`` has not datas the method will immediately bail out.

        It has different return values:

          - For No Optimization: a list contanining instances of the Strategy
            classes added with ``addstrategy``

          - For Optimization: a list of lists which contain instances of the
            Strategy classes added with ``addstrategy``
        '''
        self._event_stop = False  # Stop is requested

        if not self.datas:
            return []  # nothing can be run

        pkeys = self.params._getkeys()
        for key, val in kwargs.items():
            if key in pkeys:
                setattr(self.params, key, val)

        # Manage activate/deactivate object cache
        linebuffer.LineActions.cleancache()  # clean cache
        indicator.Indicator.cleancache()  # clean cache

        linebuffer.LineActions.usecache(self.p.objcache)
        indicator.Indicator.usecache(self.p.objcache)

        self._dorunonce = self.p.runonce
        self._dopreload = self.p.preload
        self._exactbars = int(self.p.exactbars)

        if self._exactbars:
            self._dorunonce = False  # something is saving memory, no runonce
            self._dopreload = self._dopreload and self._exactbars < 1

        self._doreplay = self._doreplay or any(x.replaying for x in self.datas)
        if self._doreplay:
            # preloading is not supported with replay. full timeframe bars
            # are constructed in realtime
            self._dopreload = False

        if self._dolive or self.p.live:
            # in this case both preload and runonce must be off
            self._dorunonce = False
            self._dopreload = False

        self.runwriters = list()

        # Add the system default writer if requested
        if self.p.writer is True:
            wr = WriterFile()
            self.runwriters.append(wr)

        # Instantiate any other writers
        for wrcls, wrargs, wrkwargs in self.writers:
            wr = wrcls(*wrargs, **wrkwargs)
            self.runwriters.append(wr)

        # Write down if any writer wants the full csv output
        self.writers_csv = any(map(lambda x: x.p.csv, self.runwriters))

        self.runstrats = list()
        if self.p.stats:
            self.addanalyzer(analyzers.Eq, _name='eq')

        if self.signals:  # allow processing of signals
            signalst, sargs, skwargs = self._signal_strat
            if signalst is None:
                # Try to see if the 1st regular strategy is a signal strategy
                try:
                    signalst, sargs, skwargs = self.strats.pop(0)
                except IndexError:
                    pass  # Nothing there
                else:
                    if not isinstance(signalst, SignalStrategy):
                        # no signal ... reinsert at the beginning
                        self.strats.insert(0, (signalst, sargs, skwargs))
                        signalst = None  # flag as not presetn

            if signalst is None:  # recheck
                # Still None, create a default one
                signalst, sargs, skwargs = SignalStrategy, tuple(), dict()

            # Add the signal strategy
            self.addstrategy(signalst,
                             _accumulate=self._signal_accumulate,
                             _concurrent=self._signal_concurrent,
                             signals=self.signals,
                             *sargs,
                             **skwargs)

        if not self.strats:  # Datas are present, add a strategy
            self.addstrategy(Strategy)

        iterstrats = itertools.product(*self.strats)
        progress = None
        strats_total = 0
        if self._dooptimize:
            strats_total=[len(lst) for lst in self.strats]
            strats_total = math.prod(strats_total)
            progress = tqdm(total=strats_total, desc="Optimization...")
            
        if not self._dooptimize or self.p.maxcpus == 1:
            # If no optimmization is wished ... or 1 core is to be used
            # let's skip process "spawning"
            for iterstrat in iterstrats:
                runstrat = self.runstrategies(iterstrat)
                self.runstrats.append(runstrat)
                if self._dooptimize:
                    if progress is not None:
                        progress.update(1)
                    for cb in self.optcbs:
                        cb(runstrat)  # callback receives finished strategy
        else:
            if self.p.optdatas and self._dopreload and self._dorunonce:
                for data in self.datas:
                    data.reset()
                    if self._exactbars < 1:  # datas can be full length
                        data.extend(size=self.params.lookahead)
                    data._start()
                    if self._dopreload:
                        data.preload()

            with multiprocessing.Pool(self.p.maxcpus or None) as pool:
                for r in pool.imap(self, iterstrats):
                    self.runstrats.append(r)
                    if progress is not None:
                        progress.update(1)
                    for cb in self.optcbs:
                        cb(r)  # callback receives finished strategy
                pool.close()
                pool.join()

            if self.p.optdatas and self._dopreload and self._dorunonce:
                for data in self.datas:
                    data.stop()

        if progress is not None:
            progress.close()

        if not self._dooptimize:
            # avoid a list of list for regular cases
            return self.runstrats[0]

        return self.runstrats

    def _init_stcount(self):
        self.stcount = 0

    def _next_stid(self):
        self.stcount += 1
        return self.stcount

    def runstrategies(self, iterstrat, predata=False):
        '''
        Internal method invoked by ``run``` to run a set of strategies
        '''
        self._init_stcount()

        self.runningstrats = runstrats = list()
        for store in self.stores:
            store.start()

        if self.p.cheat_on_open and self.p.broker_coo:
            # try to activate in broker
            if hasattr(self._broker, 'set_coo'):
                self._broker.set_coo(True)

        if self._fhistory is not None:
            self._broker.set_fund_history(self._fhistory)

        for orders, onotify in self._ohistory:
            self._broker.add_order_history(orders, onotify)

        self._broker.start()

        for feed in self.feeds:
            feed.start()

        if self.writers_csv:
            wheaders = list()
            for data in self.datas:
                if data.csv:
                    wheaders.extend(data.getwriterheaders())

            for writer in self.runwriters:
                if writer.p.csv:
                    writer.addheaders(wheaders)

        if not predata:
            for data in self.datas:
                data.reset()
                if self._exactbars < 1:  # datas can be full length
                    data.extend(size=self.params.lookahead)
                data._start()
                if self._dopreload:
                    data.preload()

        for stratcls, sargs, skwargs in iterstrat:
            sargs = self.datas + list(sargs)
            try:
                strat = stratcls(*sargs, **skwargs)
            except bt.errors.StrategySkipError:
                continue  # do not add strategy to the mix

            if self.p.tradehistory:
                strat.set_tradehistory()
            runstrats.append(strat)

        tz = self.p.tz
        if isinstance(tz, integer_types):
            tz = self.datas[tz]._tz
        else:
            tz = tzparse(tz)

        ######################
        ## MAIN CYCLE
        ######################
        if runstrats:
            # loop separated for clarity
            defaultsizer = self.sizers.get(None, (None, None, None))
            for idx, strat in enumerate(runstrats):
                if self.p.stdstats:
                    strat._addobserver(False, observers.Broker)
                    strat._addobserver(True, observers.BuySell, barplot=True)

                    if len(self.datas) == 1:
                        strat._addobserver(False, observers.Trades)
                    else:
                        strat._addobserver(False, observers.DataTrades)

                for multi, obscls, obsargs, obskwargs in self.observers:
                    strat._addobserver(multi, obscls, *obsargs, **obskwargs)

                for indcls, indargs, indkwargs in self.indicators:
                    strat._addindicator(indcls, *indargs, **indkwargs)

                for ancls, anargs, ankwargs in self.analyzers:
                    strat._addanalyzer(ancls, *anargs, **ankwargs)

                sizer, sargs, skwargs = self.sizers.get(idx, defaultsizer)
                if sizer is not None:
                    strat._addsizer(sizer, *sargs, **skwargs)

                strat._settz(tz)
                strat._start()

                for writer in self.runwriters:
                    if writer.p.csv:
                        writer.addheaders(strat.getwriterheaders())

            if not predata:
                for strat in runstrats:
                    strat.qbuffer(self._exactbars, replaying=self._doreplay)

            for writer in self.runwriters:
                writer.start()

            # Prepare timers
            self._timers = []
            self._timerscheat = []
            for timer in self._pretimers:
                # preprocess tzdata if needed
                timer.start(self.datas[0])

                if timer.params.cheat:
                    self._timerscheat.append(timer)
                else:
                    self._timers.append(timer)

            if self._dopreload and self._dorunonce:
                self._runonce(runstrats)
            else:
                self._runnext(runstrats)

            for strat in runstrats:
                strat._stop()

        self._broker.stop()

        if not predata:
            for data in self.datas:
                data.stop()

        for feed in self.feeds:
            feed.stop()

        for store in self.stores:
            store.stop()

        self.stop_writers(runstrats)

        if self._dooptimize and self.p.optreturn:
            # Results can be optimized
            results = list()
            for strat in runstrats:
                for a in strat.analyzers:
                    a.strategy = None
                    a._parent = None
                    for attrname in dir(a):
                        if attrname.startswith('data'):
                            setattr(a, attrname, None)
                oreturn = OptReturn(strat.params, analyzers=strat.analyzers, statistics=strat.statistics, strategycls=type(strat))
                results.append(oreturn)

            return results

        return runstrats

    def stop_writers(self, runstrats):
        cerebroinfo = OrderedDict()
        datainfos = OrderedDict()

        for i, data in enumerate(self.datas):
            datainfos['Data%d' % i] = data.getwriterinfo()

        cerebroinfo['Datas'] = datainfos

        stratinfos = dict()
        for strat in runstrats:
            stname = strat.__class__.__name__
            stratinfos[stname] = strat.getwriterinfo()

        cerebroinfo['Strategies'] = stratinfos

        for writer in self.runwriters:
            writer.writedict(dict(Cerebro=cerebroinfo))
            writer.stop()

    def _brokernotify(self):
        '''
        Internal method which kicks the broker and delivers any broker
        notification to the strategy
        '''
        self._broker.next()
        # Direct deque access — avoids get_notification() call + IndexError per bar
        notifs = self._broker.notifs
        while notifs:
            order = notifs.popleft()
            owner = order.owner
            if owner is None:
                owner = self.runningstrats[0]  # default

            owner._addnotification(order, quicknotify=self.p.quicknotify)

    def _next_writers(self, runstrats):
        if not self.runwriters:
            return

        if self.writers_csv:
            wvalues = list()
            for data in self.datas:
                if data.csv:
                    wvalues.extend(data.getwritervalues())

            for strat in runstrats:
                wvalues.extend(strat.getwritervalues())

            for writer in self.runwriters:
                if writer.p.csv:
                    writer.addvalues(wvalues)

                    writer.next()

    def _disable_runonce(self):
        '''API for lineiterators to disable runonce (see HeikinAshi)'''
        self._dorunonce = False

    def _runnext(self, runstrats):
        '''
        Actual implementation of run in full next mode. All objects have its
        ``next`` method invoke on each data arrival
        '''
        datas = sorted(self.datas,
                       key=lambda x: (x._timeframe, x._compression))
        datas1 = datas[1:]
        data0 = datas[0]
        d0ret = True

        rs = [i for i, x in enumerate(datas) if x.resampling]
        rp = [i for i, x in enumerate(datas) if x.replaying]
        rsonly = [i for i, x in enumerate(datas)
                  if x.resampling and not x.replaying]
        onlyresample = len(datas) == len(rsonly)
        noresample = not rsonly

        clonecount = sum(d._clone for d in datas)
        ldatas = len(datas)
        ldatas_noclones = ldatas - clonecount
        lastqcheck = False
        dt0 = date2num(datetime.datetime.max) - 2  # default at max
        while d0ret or d0ret is None:
            # if any has live data in the buffer, no data will wait anything
            newqcheck = not any(d.haslivedata() for d in datas)
            if not newqcheck:
                # If no data has reached the live status or all, wait for
                # the next incoming data
                livecount = sum(d._laststatus == d.LIVE for d in datas)
                newqcheck = not livecount or livecount == ldatas_noclones

            lastret = False
            # Notify anything from the store even before moving datas
            # because datas may not move due to an error reported by the store
            self._storenotify()
            if self._event_stop:  # stop if requested
                return
            self._datanotify()
            if self._event_stop:  # stop if requested
                return

            # record starting time and tell feeds to discount the elapsed time
            # from the qcheck value
            drets = []
            qstart = datetime.datetime.utcnow()
            for d in datas:
                qlapse = datetime.datetime.utcnow() - qstart
                d.do_qcheck(newqcheck, qlapse.total_seconds())
                drets.append(d.next(ticks=False))

            d0ret = any((dret for dret in drets))
            if not d0ret and any((dret is None for dret in drets)):
                d0ret = None

            if d0ret:
                dts = []
                for i, ret in enumerate(drets):
                    dts.append(datas[i].datetime[0] if ret else None)

                # Get index to minimum datetime
                if onlyresample or noresample:
                    dt0 = min((d for d in dts if d is not None))
                else:
                    dt0 = min((d for i, d in enumerate(dts)
                               if d is not None and i not in rsonly))

                dmaster = datas[dts.index(dt0)]  # and timemaster
                self._dtmaster = dmaster.num2date(dt0)
                self._udtmaster = num2date(dt0)

                # slen = len(runstrats[0])
                # Try to get something for those that didn't return
                for i, ret in enumerate(drets):
                    if ret:  # dts already contains a valid datetime for this i
                        continue

                    # try to get a data by checking with a master
                    d = datas[i]
                    d._check(forcedata=dmaster)  # check to force output
                    if d.next(datamaster=dmaster, ticks=False):  # retry
                        dts[i] = d.datetime[0]  # good -> store
                    else:
                        pass

                # make sure only those at dmaster level end up delivering
                for i, dti in enumerate(dts):
                    if dti is not None:
                        di = datas[i]
                        rpi = False and di.replaying   # to check behavior
                        if dti > dt0:
                            if not rpi:  # must see all ticks ...
                                di.rewind()  # cannot deliver yet
                        elif not di.replaying:
                            # Replay forces tick fill, else force here
                            di._tick_fill(force=True)


            elif d0ret is None:
                # meant for things like live feeds which may not produce a bar
                # at the moment but need the loop to run for notifications and
                # getting resample and others to produce timely bars
                for data in datas:
                    data._check()
            else:
                lastret = data0._last()
                for data in datas1:
                    lastret += data._last(datamaster=data0)

                if not lastret:
                    # Only go extra round if something was changed by "lasts"
                    break

            # Datas may have generated a new notification after next
            self._datanotify()
            if self._event_stop:  # stop if requested
                return

            if d0ret or lastret:  # if any bar, check timers before broker
                self._check_timers(runstrats, dt0, cheat=True)
                if self.p.cheat_on_open:
                    for strat in runstrats:
                        strat._next_open()
                        if self._event_stop:  # stop if requested
                            return

            self._brokernotify()
            if self._event_stop:  # stop if requested
                return

            if d0ret or lastret:  # bars produced by data or filters
                self._check_timers(runstrats, dt0, cheat=False)
                for strat in runstrats:
                    strat._next()
                    if self._event_stop:  # stop if requested
                        return

                    self._next_writers(runstrats)

        # Last notification chance before stopping
        self._datanotify()
        if self._event_stop:  # stop if requested
            return
        self._storenotify()
        if self._event_stop:  # stop if requested
            return

    def _runonce(self, runstrats):
        '''
        Actual implementation of run in vector mode.

        Strategies are still invoked on a pseudo-event mode in which ``next``
        is called for each data arrival
        '''
        for strat in runstrats:
            strat._once()
            strat.reset()  # strat called next by next - reset lines

        # The default once for strategies does nothing and therefore
        # has not moved forward all datas/indicators/observers that
        # were homed before calling once, Hence no "need" to do it
        # here again, because pointers are at 0
        datas = sorted(self.datas, key=lambda x: (x._timeframe, x._compression))

        # Local references for speed
        brokernotify = self._brokernotify
        check_timers = self._check_timers
        next_writers = self._next_writers
        cheat_on_open = self.p.cheat_on_open

        dts = [d.advance_peek() if d.is_on else math.inf  for d in datas]
        ndatas = len(datas)
        while True:
            # Check next incoming date in the datas
            dt0 = min(dts)
            if dt0 == math.inf:
                break  # no data delivers anything

            for i in range(ndatas):
                if datas[i].is_on and dts[i] <= dt0:
                    datas[i].advance()
                    # is_end only checked after advance() — avoids N×bars unnecessary lookups
                    if datas[i].is_end:
                        dts[i] = math.inf
                        datas[i].is_on = False

            # Timers before broker (cheat)
            check_timers(runstrats, dt0, cheat=True)
            if cheat_on_open:
                for strat in runstrats:
                    strat._oncepost_open()
                    if self._event_stop:  # stop if requested
                        return

            # Broker notifications
            brokernotify()
            if self._event_stop:
                return

            # Timers after broker
            check_timers(runstrats, dt0, cheat=False)

            # Strategy once-post and writer updates
            for strat in runstrats:
                strat._oncepost(dt0, dts)
                if self._event_stop:  # stop if requested
                    return

                next_writers(runstrats)

            for i in range(ndatas):
                if datas[i].is_on and (dts[i] <= dt0 or dts[i] == math.inf):
                    dts[i] = datas[i].advance_peek()


    def _check_timers(self, runstrats, dt0, cheat=False):
        timers = self._timers if not cheat else self._timerscheat
        for t in timers:
            if not t.check(dt0):
                continue

            t.params.owner.notify_timer(t, t.lastwhen, *t.args, **t.kwargs)

            if t.params.strats:
                for strat in runstrats:
                    strat.notify_timer(t, t.lastwhen, *t.args, **t.kwargs)
