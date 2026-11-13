#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

"""Shared parameter search and failure reporting for Cerebro and Aurora."""

from dataclasses import dataclass
from copy import deepcopy
from functools import partial
from io import BytesIO
import itertools
import multiprocessing
from multiprocessing.reduction import ForkingPickler
from pickle import Unpickler, loads
import traceback
from types import SimpleNamespace

import numpy as np
import pandas as pd
from tqdm import tqdm

from .errors import OptimizationError


def reset_diagnostics(engine):
    engine.optimization_errors = []
    engine.optimization_summary = {
        'successful': 0,
        'failed': 0,
        'constraint_rejected': 0,
        'invalid_metrics': 0,
    }


def _snapshot(value, depth=0):
    """Keep diagnostics picklable even for feed/indicator parameters."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, np.generic):
        return _snapshot(value.item(), depth)
    if depth < 4:
        if isinstance(value, dict):
            return {str(k): _snapshot(v, depth + 1) for k, v in value.items()}
        if isinstance(value, tuple):
            return tuple(_snapshot(v, depth + 1) for v in value)
        if isinstance(value, list):
            return [_snapshot(v, depth + 1) for v in value]
    try:
        return repr(value)
    except Exception:
        return '<{}.{}>'.format(type(value).__module__, type(value).__qualname__)


def _annotate_error(error, strategy, params, stage):
    strategy_name = '{}.{}'.format(strategy.__module__, strategy.__qualname__)
    snapshot = {name: _snapshot(value) for name, value in params.items()}
    note = 'Optimization {}: strategy={}; params={!r}'.format(
        stage, strategy_name, snapshot)
    if hasattr(error, 'add_note'):
        error.add_note(note)
    record = {
        'params': snapshot,
        'strategy': strategy_name,
        'stage': stage,
        'error_type': type(error).__name__,
        'exception_module': type(error).__module__,
        'message': str(error),
        'traceback': ''.join(traceback.format_exception(
            type(error), error, error.__traceback__)),
    }
    error.optimization_error = record
    return record


def _record_failure(engine, record):
    engine.optimization_errors.append(record)
    engine.optimization_summary['failed'] += 1


def _cleanup_failed_run(child, error):
    if getattr(child, '_run_cleanup_complete', False):
        return
    # A failed run bypasses the engines' normal stop sequence. Release resources
    # before reusing feeds, without replacing the exception that caused failure.
    stops = [strat._stop for strat in getattr(child, 'runningstrats', ())]
    stops.append(child.broker.stop)
    for attribute in ('datas', 'feeds', 'stores', 'runwriters'):
        stops.extend(resource.stop for resource in getattr(child, attribute, ()))
    for stop in stops:
        try:
            stop()
        except Exception as cleanup_error:
            if hasattr(error, 'add_note'):
                error.add_note('Cleanup failed: {}: {}'.format(
                    type(cleanup_error).__name__, cleanup_error))


def _copy_engine_configuration(engine, child):
    # Keep references to the actual feeds and rebind timer owners to the trial.
    memo = {id(engine): child, id(engine.broker): child.broker}
    memo.update((id(data), data) for data in engine.datas)
    for name in ('writers', 'indicators', 'signals', '_signal_strat',
                 '_signal_concurrent', '_signal_accumulate', '_tradingcal',
                 '_pretimers', '_ohistory', '_fhistory'):
        if hasattr(engine, name):
            setattr(child, name, deepcopy(getattr(engine, name), memo))


def run_single_combination(engine, engine_class, args):
    """Run a trial and release resources on failure; the caller reports errors."""
    strategy, params = args
    child = None
    completed = False
    try:
        child = engine_class(broker=engine.broker.clone(),
                             **deepcopy(engine.p._getkwargs()))
        _copy_engine_configuration(engine, child)
        for idx, (sizercls, sizerargs, sizerkwargs) in engine.sizers.items():
            if idx is None:
                child.addsizer(sizercls, *sizerargs, **sizerkwargs)
            else:
                child.addsizer_byidx(idx, sizercls, *sizerargs, **sizerkwargs)
        for data in engine.datas:
            child.adddata(data)
        for ancls, anargs, ankwargs in engine.analyzers:
            child.addanalyzer(ancls, *anargs, **ankwargs)
        # optimize() always needs Eq to return statistics, including stats=False.
        if not child.p.stats and not any(
                kwargs.get('_name', cls.__name__.lower()) == 'eq'
                for cls, _, kwargs in child.analyzers):
            from .analyzers import Eq
            child.addanalyzer(Eq, _name='eq')
        child.observers.extend(engine.observers)
        child.addstrategy(strategy, **params)
        strategies = child.run()
        completed = True
        if not strategies:
            raise OptimizationError('Backtest returned no strategies')
        statistics = strategies[0].statistics
        stats = statistics.to_dict()
        # Preserve the existing heatmap convention: omit Backtrader objects.
        stats.update({name: value for name, value in params.items()
                      if not type(value).__module__.startswith('backtrader_next')})
        return stats
    except BaseException as error:
        if child is not None and not completed:
            _cleanup_failed_run(child, error)
        raise


@dataclass
class _FailedTrial:
    error: dict


@dataclass
class _RaisedTrial:
    exception: BaseException
    traceback: str


class _RemoteTraceback(Exception):
    """Display the original worker stack as the parent exception's cause."""


class _AbortSearch(BaseException):
    def __init__(self, original):
        self.original = original


def _execute_trial(engine, on_error, args):
    """Module-level worker so the same policy works with Windows spawn."""
    try:
        return engine._run_single_combination(args)
    except Exception as error:
        record = _annotate_error(error, args[0], args[1], 'backtest')
        if on_error == 'raise':
            raise
        return _FailedTrial(record)


def _execute_indexed_trial(engine, on_error, indexed_args):
    index, args = indexed_args
    try:
        result = _execute_trial(engine, on_error, args)
    except BaseException as error:
        # Transport exceptions as values. In particular, StopIteration must not
        # end imap's iterator, and KeyboardInterrupt must not kill a pool worker.
        result = _RaisedTrial(error, ''.join(traceback.format_exception(
            type(error), error, error.__traceback__)))
    return index, result


_worker_template = None
_worker_on_error = None


def _initialize_trial_worker(template, on_error):
    """Transfer the configured engine/data once per process, not per trial."""
    global _worker_template, _worker_on_error
    _worker_template, _worker_on_error = template, on_error


def _trial_references(engine):
    return (engine, engine.broker, *engine.datas)


class _TrialPickler(ForkingPickler):
    def persistent_id(self, obj):
        return self.references.get(id(obj))


class _TrialUnpickler(Unpickler):
    def persistent_load(self, key):
        return self.references[key]


def _encode_worker_trial(engine, indexed_args):
    index, args = indexed_args
    stream = BytesIO()
    encoder = _TrialPickler(stream)
    encoder.references = {id(obj): index for index, obj in enumerate(_trial_references(engine))}
    encoder.dump(args)
    return index, stream.getvalue()


def _execute_worker_trial(indexed_payload):
    index, payload = indexed_payload
    try:
        # Recreate the snapshot locally so input mutations, feed activation and
        # failures cannot leak into the next trial handled by this process.
        engine = loads(_worker_template)
        decoder = _TrialUnpickler(BytesIO(payload))
        decoder.references = _trial_references(engine)
        args = decoder.load()
        return _execute_indexed_trial(engine, _worker_on_error, (index, args))
    except BaseException as error:
        return index, _RaisedTrial(error, ''.join(traceback.format_exception(
            type(error), error, error.__traceback__)))


def _accept_result(engine, result, all_stats):
    if isinstance(result, _RaisedTrial):
        raise result.exception from _RemoteTraceback(result.traceback)
    if isinstance(result, _FailedTrial):
        _record_failure(engine, result.error)
        return False
    else:
        engine.optimization_summary['successful'] += 1
        all_stats.append(result)
        return True


def _collect_trials(engine, strategy, combinations, maxcpus, on_error, description):
    args = [(strategy, params) for params in combinations]
    worker = partial(_execute_trial, engine, on_error)
    all_stats = []
    try:
        if maxcpus != 1 and len(args) > 1:
            order = []
            # Serialize in the parent: an invalid configuration must raise here,
            # rather than repeatedly crashing and respawning pool initializers.
            template = bytes(ForkingPickler.dumps(engine))
            with multiprocessing.Pool(maxcpus or None, initializer=_initialize_trial_worker,
                                      initargs=(template, on_error)) as pool:
                tasks = (_encode_worker_trial(engine, task) for task in enumerate(args))
                with tqdm(pool.imap_unordered(_execute_worker_trial, tasks), total=len(args),
                          desc=description + ' (parallel)') as results:
                    for index, result in results:
                        if _accept_result(engine, result, all_stats):
                            order.append(index)
            all_stats = [stats for _, stats in sorted(zip(order, all_stats))]
        else:
            with tqdm(args, desc=description) as trials:
                for trial in trials:
                    _accept_result(engine, worker(trial), all_stats)
    except Exception as error:
        record = getattr(error, 'optimization_error', None)
        if record is not None:
            _record_failure(engine, record)
        raise
    return all_stats


def _constraint_allows(engine, strategy, params, constraint, on_error):
    if constraint is None:
        return True
    try:
        allowed = bool(constraint(SimpleNamespace(**params)))
    except Exception as error:
        record = _annotate_error(error, strategy, params, 'constraint')
        _record_failure(engine, record)
        if on_error == 'raise':
            raise
        return False
    if not allowed:
        engine.optimization_summary['constraint_rejected'] += 1
    return allowed


def _metric_values(frame, maximize):
    metrics = list(maximize) if isinstance(maximize, dict) else [maximize]
    if not metrics:
        raise ValueError('At least one objective metric must be specified')
    for metric in metrics:
        if metric not in frame.columns:
            raise ValueError("Metric {!r} not found. Available: {}".format(
                metric, list(frame.columns)))
    return frame[metrics].apply(pd.to_numeric, errors='coerce')


def _select_best(engine, all_stats, maximize):
    if not all_stats:
        failed = engine.optimization_summary['failed']
        if failed:
            raise OptimizationError(
                'No successful optimization runs: {} failed. '
                'See optimization_errors for details.'.format(failed))
        raise OptimizationError('No parameter combinations satisfied the constraints')
    frame = pd.DataFrame(all_stats)
    values = _metric_values(frame, maximize)
    valid = np.isfinite(values).all(axis=1)
    engine.optimization_summary['invalid_metrics'] = int((~valid).sum())
    if not valid.any():
        raise OptimizationError(
            'No finite objective metrics in {} successful optimization runs'.format(
                engine.optimization_summary['successful']))
    if isinstance(maximize, dict):
        # Ineligible rows must not affect normalization or win a weighted score.
        ranked = frame.loc[valid].copy()
        ranked[values.columns] = values.loc[valid]
        ranked = engine._normalize_metrics(ranked, maximize)
        ranked['_multiobjective_score'] = engine._calculate_multiobjective_score(
            ranked, maximize)
        for column in ranked.columns.difference(frame.columns):
            frame[column] = ranked[column]
        best_idx = ranked['_multiobjective_score'].idxmax()
    else:
        best_idx = values.loc[valid, maximize].idxmax()
    best = frame.loc[best_idx].copy()
    summary = engine.optimization_summary.copy()
    best['Optimization Successful Runs'] = summary['successful']
    best['Optimization Failed Runs'] = summary['failed']
    best.attrs['optimization_summary'] = summary.copy()
    frame.attrs['optimization_summary'] = summary.copy()
    return best, frame


def _result(best, frame, return_heatmap, optimization=None,
            return_optimization=False):
    result = (best,)
    if return_heatmap:
        result += (frame,)
    if return_optimization:
        result += (optimization,)
    return result[0] if len(result) == 1 else result


def optimize(engine, strategy, method, maximize, constraint, max_tries,
             random_state, return_heatmap, return_optimization, maxcpus,
             on_error, params):
    reset_diagnostics(engine)
    if on_error not in ('raise', 'skip'):
        raise ValueError("on_error must be 'raise' or 'skip'")
    if not params:
        raise ValueError('At least one parameter must be specified for optimization')
    method = method.lower()
    if method == 'grid':
        return engine._optimize_grid(strategy, maximize, constraint,
                                     return_heatmap, maxcpus, params, on_error)
    if method == 'random':
        return engine._optimize_random(strategy, maximize, constraint, max_tries,
                                       random_state, return_heatmap, maxcpus,
                                       params, on_error)
    if method == 'sambo':
        return engine._optimize_sambo(strategy, maximize, constraint, max_tries,
                                      random_state, return_heatmap,
                                      return_optimization, params, on_error)
    raise ValueError("Unknown optimization method: {}. Use 'grid', 'sambo', or 'random'".format(method))


def optimize_grid(engine, strategy, maximize, constraint, return_heatmap,
                  maxcpus, params, on_error='raise'):
    names = list(params)
    ranges = []
    for value in params.values():
        if isinstance(value, tuple) and len(value) == 2 and not isinstance(value[0], str):
            try:
                lower, upper = value
                step = (upper - lower) / 10
                if isinstance(lower, int) and isinstance(upper, int):
                    value = range(lower, upper + 1, max(1, int(step)))
                else:
                    value = np.linspace(lower, upper, 10)
            except TypeError:
                pass
        ranges.append(engine.iterize([value])[0])
    combinations = []
    for values in itertools.product(*ranges):
        candidate = dict(zip(names, values))
        if _constraint_allows(engine, strategy, candidate, constraint, on_error):
            combinations.append(candidate)
    stats = _collect_trials(engine, strategy, combinations, maxcpus, on_error,
                            'Grid Search')
    best, frame = _select_best(engine, stats, maximize)
    return _result(best, frame, return_heatmap)


def optimize_random(engine, strategy, maximize, constraint, max_tries,
                    random_state, return_heatmap, maxcpus, params,
                    on_error='raise'):
    rng = np.random.RandomState(random_state)
    ranges = []
    for value in params.values():
        if isinstance(value, tuple) and len(value) == 2:
            ranges.append(('continuous', value))
        elif hasattr(value, '__iter__') and not isinstance(value, str):
            ranges.append(('discrete', list(value)))
        else:
            ranges.append(('fixed', value))
    max_tries = max_tries or 100
    combinations = []
    seen = set()
    for _ in range(max_tries * 100):
        if len(combinations) >= max_tries:
            break
        values = []
        for kind, bounds in ranges:
            if kind == 'continuous':
                lower, upper = bounds
                if isinstance(lower, int) and isinstance(upper, int):
                    value = rng.randint(lower, upper + 1)
                else:
                    value = rng.uniform(lower, upper)
            elif kind == 'discrete':
                value = bounds[rng.randint(len(bounds))]
            else:
                value = bounds
            values.append(value)
        candidate = dict(zip(params, values))
        key = repr(_snapshot(candidate))
        if key in seen:
            continue
        # Remember rejected/failed constraints too, to avoid duplicate reports.
        seen.add(key)
        if _constraint_allows(engine, strategy, candidate, constraint, on_error):
            combinations.append(candidate)
    stats = _collect_trials(engine, strategy, combinations, maxcpus, on_error,
                            'Random Search')
    best, frame = _select_best(engine, stats, maximize)
    return _result(best, frame, return_heatmap)


def optimize_sambo(engine, strategy, maximize, constraint, max_tries,
                   random_state, return_heatmap, return_optimization, params,
                   on_error='raise'):
    try:
        import sambo
    except ModuleNotFoundError as error:
        if error.name != 'sambo':
            raise
        raise ImportError('SAMBO library not installed. Install it with: pip install sambo') from error
    optimized = {name: value for name, value in params.items()
                 if isinstance(value, tuple) and len(value) == 2}
    if not optimized:
        raise ValueError('SAMBO requires at least one (min, max) parameter range')
    fixed = {name: value for name, value in params.items() if name not in optimized}
    all_stats = []
    max_tries = max_tries or 50
    with tqdm(total=max_tries, desc='SAMBO Optimization') as progress:
        def objective(point):
            candidate = fixed.copy()
            for index, (name, bounds) in enumerate(optimized.items()):
                value = float(np.asarray(point).ravel()[index])
                candidate[name] = (int(round(value)) if all(isinstance(v, int) for v in bounds)
                                   else value)
            try:
                # Enforce constraints here so rejected points and errors obey the
                # same bounded evaluation budget, including when every point fails.
                if not _constraint_allows(engine, strategy, candidate, constraint, on_error):
                    return np.inf
                try:
                    stats = _execute_trial(engine, on_error, (strategy, candidate))
                except Exception as error:
                    _record_failure(engine, error.optimization_error)
                    raise
                _accept_result(engine, stats, all_stats)
                if isinstance(stats, _FailedTrial):
                    return np.inf
                values = _metric_values(pd.DataFrame([stats]), maximize)
                if not np.isfinite(values.to_numpy()).all():
                    return np.inf
                primary = next(iter(maximize)) if isinstance(maximize, dict) else maximize
                direction = maximize[primary] if isinstance(maximize, dict) else 'max'
                if isinstance(direction, tuple):
                    direction = direction[0]
                metric = float(values[primary].iloc[0])
                # SAMBO minimizes; a failed trial must never be attractive.
                return metric if direction == 'min' else -metric
            except BaseException as error:
                # SAMBO handles KeyboardInterrupt/StopIteration internally in
                # some paths. Restore the original exception outside its call.
                raise _AbortSearch(error) from None
            finally:
                progress.update(1)

        original_error = None
        try:
            optimization = sambo.minimize(
                fun=objective, bounds=np.asarray(list(optimized.values())),
                max_iter=max_tries, method='sceua', rng=random_state)
        except _AbortSearch as abort:
            original_error = abort.original
        # Re-raise outside the adapter's except block to retain the original
        # exception chain rather than introducing the internal adapter as context.
        if original_error is not None:
            raise original_error.with_traceback(original_error.__traceback__)
    best, frame = _select_best(engine, all_stats, maximize)
    return _result(best, frame, return_heatmap, optimization, return_optimization)
