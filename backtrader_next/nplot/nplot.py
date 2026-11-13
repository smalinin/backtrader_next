#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import bisect
import collections
import datetime
from copy import deepcopy
import webbrowser
from pathlib import Path

import pandas as pd
import numpy as np

from backtrader_next.strategy import Strategy
from backtrader_next.analyzers.eq import Eq

from ..utils.py3 import with_metaclass
from ..utils.date import format_datetime
from ..lineiterator import IndicatorBase
from .. import AutoInfoClass, MetaParams, date2num, num2date
from .nscheme import PlotScheme

from bn_lightweight_charts.widgets import HTMLChart_BN

#TODO add plot observers

class PInfo(object):
    def __init__(self, sch):
        self.sch = sch
        self.reset()

    def reset(self):
        self.coloridx = collections.defaultdict(lambda: -1)

    def nextcolor(self, ax:int):
        self.coloridx[ax] += 1
        return self.coloridx[ax]

    def color(self, ax):
        return self.sch.color(self.coloridx[ax])


class Plot(with_metaclass(MetaParams, object)):
    params = (('scheme', PlotScheme()),)

    def __init__(self, **kwargs):
        self.p.scheme = deepcopy(self.p.scheme)
        for pname, pvalue in kwargs.items():
            setattr(self.p.scheme, pname, pvalue)
        if not hasattr(self.p.scheme, 'locbg'):
            setattr(self.p.scheme, 'locbg', 'white')
            setattr(self.p.scheme, 'locbgother', 'white')
        self.chart = None

    def plot(self, stratlist, iplot=False,
             start=None, end=None, width=None, height=None, show_eq=False,
             show=True, filename=None, **kwargs):
        if filename is None:
            return
        self.chart = None
        strategies = list(stratlist)
        names = collections.Counter(type(strategy).__name__ for strategy in strategies)
        occurrences = collections.Counter()
        for strategy in strategies:
            if not isinstance(strategy, Strategy):
                raise TypeError(f"Expected Strategy instance, got {type(strategy)}")
            name = type(strategy).__name__
            occurrences[name] += 1
            if names[name] > 1:
                name += f" #{occurrences[name]}"
            self.plot_one(strategy, start=start, end=end, width=width, height=height,
                          show_eq=show_eq, filename=filename, strategy_name=name, **kwargs)
        if self.chart is None:
            return
        self.chart.load()
        if iplot or show:
            webbrowser.open(Path(filename).resolve().as_uri())

    def plot_one(self, strategy, start=None, end=None, width=None, height=None,
                 show_eq=False, filename=None, strategy_name=None, **kwargs):
        if not strategy.datas or not len(strategy) or filename is None:
            return
        self._strategy = strategy
        strat_name = strategy_name or type(strategy).__name__
        self.strat_params = pd.Series(strategy.p._getkwargs(), dtype=object)
        self.pinf = PInfo(self.p.scheme)
        named_eq = (strategy.analyzers.getbyname('eq')
                    if 'eq' in strategy.analyzers.getnames() else None)
        self.performance = (named_eq if isinstance(named_eq, Eq) else
                            next((analyzer for analyzer in reversed(list(strategy.analyzers))
                                  if isinstance(analyzer, Eq)), None))
        self.performance_metrics = None
        self.sortdataindicators(strategy)

        dates = np.asarray(strategy.datetime.plot())[:len(strategy)]
        if isinstance(start, datetime.date):
            start = bisect.bisect_left(dates, date2num(start))
        if isinstance(end, datetime.date):
            end = bisect.bisect_right(dates, date2num(end))
        if end is not None and end < 0:
            end = len(dates) + 1 + end
        window = dates[start:end]
        if not len(window):
            return
        self._time_start, self._time_end = window[0], window[-1]

        c_top = {}
        if self.performance is not None:
            self.performance_metrics = self.performance.compute_stats()
            if show_eq:
                equity = self.performance.gen_eq()['value']
                mask = [self._time_start <= date2num(date) <= self._time_end for date in equity.index]
                values = (equity / equity.iloc[0] - 1) * 100
                c_top['eq'] = {'label': 'Equity', 'mode': 'plot',
                               'data': {'time': equity.index[mask].to_pydatetime(),
                                        'Equity': values[mask].to_numpy()}}

        for data_index, data in enumerate(strategy.datas):
            if not data.plotinfo.plot or not len(data):
                continue
            mask, xdates = self._time_slice(data, len(data))
            if not len(xdates):
                continue
            self.pinf.reset()
            candles = {name: np.asarray(getattr(data, name).plotrange(0, len(mask)))[mask]
                       for name in ('open', 'high', 'low', 'close')}
            candles['time'] = xdates
            c_up, c_down = [], []
            if self.p.scheme.volume:
                volume = np.asarray(data.volume.plotrange(0, len(mask)))[mask]
                master = data.plotinfo.plotmaster
                if self.p.scheme.voloverlay and (master is None or master is data):
                    candles['volume'] = volume
                else:
                    c_down.append([{'label': 'volume', 'mode': 'bar',
                                    'data': {'time': xdates, 'volume': volume}}])
            c_data = [{'label': data._name, 'mode': 'candle', 'data': candles}]
            for indicator in self.dplots_up[data]:
                up, lines, down = self._indicator_panels(indicator)
                c_up.extend(up + ([lines] if lines else []) + down)
            for indicator in self.dplots_over[data]:
                up, lines, down = self._indicator_panels(indicator, overlay=True)
                c_up.extend(up)
                c_data.extend(lines)
                c_down.extend(down)
            for indicator in self.dplots_down[data]:
                up, lines, down = self._indicator_panels(indicator)
                c_down.extend(up + ([lines] if lines else []) + down)
            if self.chart is None:
                self.chart = self.create_chart(c_top, filename=filename)
            data_name = data._name or f'data{data_index}'
            self.show(self.chart, xdates, c_top, c_up, c_data, c_down, strat_name, data_name)

    def _time_slice(self, clock, size):
        if not len(clock) or not size:
            return np.zeros(0, dtype=bool), np.asarray([], dtype=object)
        dates = np.asarray(clock.datetime.plot())[:min(len(clock), size)]
        mask = (dates >= self._time_start) & (dates <= self._time_end)
        return mask, np.asarray([num2date(value) for value in dates[mask]], dtype=object)

    def prepare_trades_list(self, data_name:str):
        trades = self.performance.gen_trades(data_name, True) if self.performance else pd.DataFrame()
        orders = self.performance.gen_orders(data_name) if self.performance else pd.DataFrame()
        if orders.empty:
            lst = []
        elif trades.empty:
            lst = orders.assign(ref=np.nan).to_dict(orient='records')
        else:
            df_lst = pd.merge(trades, orders, left_on='dateopen', right_on='o_datetime', how='outer')
            lst = df_lst.to_dict(orient='records')
        trades_lst = []
        size = 0
        for v in lst:
            if size != 0:
                o_size = v['o_size']
                trades_lst.append({'type':1, 'o_ref':v['o_ref'], 'o_size':o_size,
                                'o_datetime':format_datetime(v['o_datetime']),
                                'o_price':v['o_price'], 'o_ordtype':v['o_ordtype']})
                size_prev = size
                size += o_size
                if (size_prev < 0 and size > 0) or (size_prev > 0 and size < 0):
                    trades_lst.append({'type':0, 'ref':v['ref'], 'tradeid':v['tradeid'],
                                    'commission':v['commission'], 'pnl':v['pnl'], 'pnlcomm':v['pnlcomm'],
                                    'return_pct':f"{v['return_pct']:0.3f}" , 'dateopen': format_datetime(v['dateopen']),
                                    'dateclose':format_datetime(v['dateclose']), 'size':v['size'],
                                    'barlen':v['barlen'], 'priceopen':v['priceopen'], 'priceclose':v['priceclose']})
            else:
                o_size = v['o_size']
                if not np.isnan(v['ref']):
                    trades_lst.append({'type':0, 'ref':v['ref'], 'tradeid':v['tradeid'],
                                    'commission':v['commission'], 'pnl':v['pnl'], 'pnlcomm':v['pnlcomm'],
                                    'return_pct':f"{v['return_pct']:0.3f}" , 'dateopen': format_datetime(v['dateopen']),
                                    'dateclose':format_datetime(v['dateclose']), 'size':v['size'],
                                    'barlen':v['barlen'], 'priceopen':v['priceopen'], 'priceclose':v['priceclose']})
                else:
                    trades_lst.append({'type':0, 'ref':'--', 'tradeid':'--',
                                    'commission':'', 'pnl':'', 'pnlcomm':'',
                                    'return_pct':'', 'dateopen': format_datetime(v['o_datetime']),
                                    'dateclose':'--', 'size':v['o_size'],
                                    'barlen':'', 'priceopen':v['o_price'], 'priceclose':''})

                trades_lst.append({'type':1, 'o_ref':v['o_ref'], 'o_size':o_size,
                                'o_datetime':format_datetime(v['o_datetime']),
                                'o_price':v['o_price'], 'o_ordtype':v['o_ordtype']})
                size += o_size
        return trades_lst

    def create_chart(self, c_top, filename):
        chart = HTMLChart_BN(width=1600, height=900,
                        inner_height=-300 if c_top else -500, filename=filename)
        chart.legend(visible=True)
        chart.price_scale(perm_width=100)
        chart.fit()
        return chart

    def show(self, chart, xdates, c_top, c_up, c_data, c_down, strat_name, data_name):
        chart.set_name(f"{strat_name}_{data_name}")
        self.draw_main(chart, xdates, c_top, c_up, c_data, c_down, data_name)
        chart.sync_charts()
        trades_lst = self.prepare_trades_list(data_name)
        chart.set_trades(lst=trades_lst)
        chart.set_parameters_list(self.strat_params)
        chart.set_performance_metrics(self.performance_metrics, strat_name)
        
        chart.new_window()
        chart.legend(visible=True)
        chart.fit()
        chart.price_scale(perm_width=100)

    def draw_main(self, chart, xdates, c_top, c_up, c_data, c_down, data_name):
        def create_subchart(height):
            subchart = chart.create_subchart(position='left', width=1, height=height, sync=True)
            subchart.legend(visible=True)
            subchart.price_scale(perm_width=100)
            return subchart

        def draw_item(target, items):
            for item in items:
                frame = pd.DataFrame(item['data'])
                if frame.empty:
                    continue
                if item['mode'] == 'candle':
                    target.set_zipped(frame)
                    continue
                if not item.get('samecolor', False):
                    self.pinf.nextcolor(0)
                color = item.get('color', self.pinf.color(0))
                if item['mode'] == 'bar':
                    line = target.create_histogram(item['label'], color=color,
                                                   price_line=False, price_label=False)
                else:
                    style = 'dashed' if item.get('ls') == '--' else 'solid'
                    line = target.create_line(item['label'], color=color, style=style,
                                              price_line=False, price_label=False)
                line.set_zipped(frame)
                for level in item.get('hlines') or ():
                    line.create_price_line(price=level, color=self.pinf.sch.hlinescolor,
                                           width=self.pinf.sch.hlineswidth,
                                           style='sparse_dotted' if self.pinf.sch.hlinesstyle == '...' else 'solid',
                                           price_label=False)

        first_panel = True
        if c_top:
            draw_item(chart, list(c_top.values()))
            first_panel = False
        for panel in c_up + [c_data] + c_down:
            if not panel:
                continue
            is_main = panel is c_data
            target = chart if first_panel else create_subchart(-500 if is_main else -300)
            first_panel = False
            draw_item(target, panel)
            if is_main and self.performance is not None:
                markers = []
                for _, row in self.performance.gen_orders(data_name).iterrows():
                    if not self._time_start <= date2num(row['o_datetime']) <= self._time_end:
                        continue
                    buying = row['o_size'] > 0
                    color = 'lightgreen' if buying else 'red'
                    markers.append(dict(time=row['o_datetime'], position='below',
                                        shape='arrow_up' if buying else 'arrow_down', color=color,
                                        text=f"{'Buy' if buying else 'Short'} @ {row['o_price']}"))
                    markers.append(dict(time=row['o_datetime'], position='atPriceMiddle',
                                        shape='circle', color=color, text='', price=row['o_price'], size=0.6))
                for _, row in self.performance.gen_trades(data_name).iterrows():
                    if not self._time_start <= date2num(row['dateclose']) <= self._time_end:
                        continue
                    profit = row['pnlcomm'] > 0
                    markers.append(dict(time=row['dateclose'], position='above', shape='square',
                                        color='yellow' if profit else 'fuchsia',
                                        text='+Profit+' if profit else '-Loss-'))
                markers.sort(key=lambda marker: marker['time'])
                target.marker_list(markers)
        return chart

    def _indicator_lines(self, indicator, overlay):
        clock = self._plotkey(indicator._clock, self._strategy, force=True, strategy_clock=True)
        mask, dates = self._time_slice(clock, len(indicator))
        hlines = [] if overlay else (indicator.plotinfo._get('plothlines', [])
                                    or indicator.plotinfo._get('plotyhlines', []))
        result = []
        for index, line in enumerate(indicator.lines):
            alias = indicator.lines._getlinealias(index)
            info = (getattr(indicator.plotlines, f'_{index}', None)
                    or getattr(indicator.plotlines, alias, None) or AutoInfoClass())
            if info._get('_plotskip', False):
                continue
            values = np.asarray(line.array)[:len(mask)][mask]
            line_dates = dates
            if info._get('_skipnan', False):
                finite = np.isfinite(values)
                values, line_dates = values[finite], dates[finite]
            label = indicator.plotlabel() + ' ' + (info._get('_name', '') or alias)
            result.append({'label': label, 'mode': info._get('_method', 'plot'),
                           'data': {'time': line_dates, label: values}, 'hlines': hlines,
                           'color': info._get('color', None),
                           'samecolor': info._get('_samecolor', False), 'ls': info._get('ls', None)})
            if result[-1]['color'] is None:
                del result[-1]['color']
            hlines = []
        return result

    def _indicator_panels(self, indicator, overlay=False, ancestors=frozenset()):
        if id(indicator) in ancestors:
            raise ValueError(f'Cyclic indicator plot hierarchy: {type(indicator).__name__}')
        ancestors = ancestors | {id(indicator)}
        up, down = [], []
        lines = self._indicator_lines(indicator, overlay)
        for child in self.dplots_up[indicator]:
            before, values, after = self._indicator_panels(child, ancestors=ancestors)
            up.extend(before + ([values] if values else []) + after)
        for child in self.dplots_over[indicator]:
            before, values, after = self._indicator_panels(child, overlay=True, ancestors=ancestors)
            up.extend(before)
            lines.extend(values)
            down.extend(after)
        for child in self.dplots_down[indicator]:
            before, values, after = self._indicator_panels(child, ancestors=ancestors)
            down.extend(before + ([values] if values else []) + after)
        return up, lines, down

    @staticmethod
    def _plotkey(clock, strategy, force=False, strategy_clock=False):
        """Resolve input views and line actions without comparing line values."""
        visited = set()
        while clock is not None and id(clock) not in visited:
            visited.add(id(clock))
            if any(clock is data for data in strategy.datas):
                return clock
            if clock is strategy:
                return strategy if strategy_clock else strategy.data
            if isinstance(clock, IndicatorBase) and not force:
                return clock
            # A line expression's clock can be a secondary feed even when its
            # owner is the strategy. Output lines without clocks use their owner.
            parent = getattr(clock, '_clock', None)
            clock = parent if parent is not None else getattr(clock, '_owner', None)
        raise ValueError('Plotting clock is cyclic or does not reach a strategy feed')

    def sortdataindicators(self, strategy:Strategy):
        # These lists/dictionaries hold the subplots that go above each data
        self.dplots_up = collections.defaultdict(list)
        self.dplots_down = collections.defaultdict(list)
        self.dplots_over = collections.defaultdict(list)

        # Sort indicators in the different lists/dictionaries
        for x in strategy.getindicators():
            if not hasattr(x, 'plotinfo'):
                # no plotting support - so far LineSingle derived classes
                continue

            if not x.plotinfo.plot or x.plotinfo.plotskip:
                continue

            x._plotinit()  # will be plotted ... call its init function

            xpmaster = x.plotinfo.plotmaster
            if xpmaster is x:
                xpmaster = None
            source = x._clock if xpmaster is None else xpmaster
            try:
                key = self._plotkey(source, strategy,
                                    force=xpmaster is None and x.plotinfo.plotforce)
            except ValueError as error:
                raise ValueError(f'Cannot resolve plotting clock for {type(x).__name__}: {error}') from error

            if x.plotinfo.subplot and xpmaster is None:
                if x.plotinfo.plotabove:
                    self.dplots_up[key].append(x)
                else:
                    self.dplots_down[key].append(x)
            else:
                self.dplots_over[key].append(x)
