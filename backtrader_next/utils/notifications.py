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

"""Broker delivery and optional per-run strategy dispatch preparation."""

from itertools import chain


def strategy_analyzers(strategy):
    """Yield distinct roots; observer-owned analyzers run with their observer."""
    seen = {id(analyzer) for observer in strategy._obs_iterator
            for analyzer in observer._analyzers}
    for analyzer in chain(strategy.analyzers, strategy._slave_analyzers):
        if id(analyzer) in seen or analyzer._parent is not None:
            continue
        seen.add(id(analyzer))
        yield analyzer


def _fund_callbacks(strategy):
    # Runtime imports avoid the Strategy/Analyzer initialization cycle.
    from ..analyzer import Analyzer
    from ..strategy import Strategy

    def recipients(analyzer, event):
        wrapper = getattr(analyzer, '_' + event)
        if getattr(wrapper, '__func__', None) is not getattr(Analyzer, '_' + event):
            # A custom dispatcher may perform work beyond invoking children.
            yield wrapper
            return
        for child in analyzer._children:
            yield from recipients(child, event)
        callback = getattr(analyzer, event)
        if getattr(callback, '__func__', None) is not getattr(Analyzer, event):
            yield callback

    events = (('notify_cashvalue', False), ('notify_fund', True))
    callbacks = []
    for event, is_fund in events:
        callback = getattr(strategy, event)
        if getattr(callback, '__func__', None) is not getattr(Strategy, event):
            callbacks.append((is_fund, callback))
    # Keep the original order: strategy cash/fund, then each analyzer cash/fund.
    for analyzer in chain(strategy.analyzers, strategy._slave_analyzers):
        for event, is_fund in events:
            callbacks.extend((is_fund, callback) for callback in recipients(analyzer, event))
    return tuple(callbacks)


class _StrategySchedule:
    def __init__(self, strategy):
        self.strategy = strategy
        self.invalidate()

    def invalidate(self):
        self._analyzers = self._fund_callbacks = None

    @property
    def analyzers(self):
        if self._analyzers is None:
            self._analyzers = tuple(strategy_analyzers(self.strategy))
        return self._analyzers

    @property
    def fund_callbacks(self):
        if self._fund_callbacks is None:
            self._fund_callbacks = _fund_callbacks(self.strategy)
        return self._fund_callbacks


def prepare_strategy_schedule(strategy):
    """Prepare dispatch after strategy, analyzer and observer startup."""
    schedule = strategy._execution_schedule = _StrategySchedule(strategy)
    schedule.analyzers
    schedule.fund_callbacks


def invalidate_strategy_schedule(strategy):
    schedule = strategy.__dict__.get('_execution_schedule')
    if schedule is not None:
        schedule.invalidate()


def notify_broker(engine):
    """Process the broker once and deliver events using the engine's policy."""
    engine._broker.next()
    notifications = engine._broker.notifs
    while notifications:
        order = notifications.popleft()
        owner = order.owner
        if owner is None:
            owner = engine.runningstrats[0]
        owner._addnotification(order, quicknotify=engine.p.quicknotify)
