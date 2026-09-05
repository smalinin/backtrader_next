#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import bisect
import collections
import datetime
import json
from hashlib import file_digest
import webbrowser
from pathlib import Path

import pandas as pd
import numpy as np

# from backtrader_next import order
from backtrader_next.strategy import Strategy
from backtrader_next.analyzers.eq import Eq
from backtrader_next.utils.dateintern import format_datetime

from ..utils.py3 import with_metaclass
from ..utils.date import format_datetime
from .. import AutoInfoClass, MetaParams, TimeFrame, date2num, num2date
from .nscheme import PlotScheme

from bn_lightweight_charts.widgets import HTMLChart_BN

#TODO add plot observers

class PInfo(object):
    def __init__(self, sch):
        self.sch = sch
        self.reset()

    def reset(self):
        self.nrows = 0
        self.row = 0
        self.clock = None
        self.x = None
        self.xlen = 0
        self.coloridx = collections.defaultdict(lambda: -1)

    def nextcolor(self, ax:int):
        self.coloridx[ax] += 1
        return self.coloridx[ax]

    def color(self, ax):
        return self.sch.color(self.coloridx[ax])


class Plot(with_metaclass(MetaParams, object)):
    params = (
        ('scheme', PlotScheme()),
        ('trade_marker_tooltips', True),
    )

    def __init__(self, **kwargs):
        for pname, pvalue in kwargs.items():
            if pname == 'trade_marker_tooltips':
                continue
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

        for strategy in stratlist:
            if not isinstance(strategy, Strategy):
                raise TypeError(f"Expected Strategy instance, got {type(strategy)}")
            else:
                self.plot_one(strategy,
                            start=start, end=end, width=width, height=height,
                            show_eq=show_eq, filename=filename, **kwargs)
        if self.chart:
            self.chart.load()
        file_path = Path(filename).resolve().as_uri()
        if iplot:
            print(f"Opening charts in browser: {file_path}")
            webbrowser.open(file_path)
        elif show:
            webbrowser.open(file_path)


    def plot_one(self, strategy,
            start=None, end=None, width=None, height=None,
            show_eq=False, filename=None, **kwargs):

        if not strategy.datas:
            return
        if not len(strategy):
            return
        if filename is None:
            return

        strat_name = strategy.__class__.__name__
        self.strat_params = pd.Series(dtype=object)
        for key, val in strategy.p._getitems():
            self.strat_params.loc[key]= strategy.p._get(key)

        self.pinf = PInfo(self.p.scheme)
        self.performance = None
        self.performance_metrics = None
        for x in strategy.analyzers:
            if isinstance(x, Eq):
                self.performance = x

        self.sortdataindicators(strategy)
        self.calcrows(strategy)

        #list datetimes
        st_dtime = strategy.lines.datetime.plot()
        if start is None:
            start = 0
        if end is None:
            end = len(st_dtime)

        if isinstance(start, datetime.date):
            start = bisect.bisect_left(st_dtime, date2num(start))

        if isinstance(end, datetime.date):
            end = bisect.bisect_right(st_dtime, date2num(end))

        if end < 0:
            end = len(st_dtime) + 1 + end  # -1 =  len() -2 = len() - 1

        slen = len(st_dtime[start:end])

        self.pinf.pstart = start
        self.pinf.pend = end
        self.pinf.psize = slen

        self.pinf.xstart = self.pinf.pstart
        self.pinf.xend = self.pinf.pend

        ###########################################################################
        # Do the plotting
        # Things that go always at the top (observers)

        c_top = {}
        if self.performance:
            if show_eq:
                df = self.performance.gen_eq_dd()
                df['equity_pct'] = (df['Equity'] / df['Equity'].iloc[0] - 1) * 100
                c_top['eq'] = {'label':'Equity',
                    'mode':'plot',
                    'data':{'time':df.index.to_pydatetime(), 'Equity':df['equity_pct'].to_numpy()}
                    }
                c_top['eq0'] = {'label':'Equity',
                    'mode':'plot',
                    'data':{'time':df.index.to_pydatetime(), 'Equity':df['Equity'].to_numpy()}
                    }
                c_top['dd'] = {'label':'Drawdown',
                    'mode':'plot',
                    'data':{'time':df.index, 'Drawdown':df['DrawdownPct'].to_numpy() * -1.0}
                    }
            self.performance_metrics = self.performance.compute_stats()

        #??     self.plotind(None, ptop, subinds=self.dplots_over[ptop])

        # Create the rest on a per data basis
        for data in strategy.datas:
            if not data.plotinfo.plot:
                continue

            self.pinf.reset()

            # xd - list of datetimes (sliced to same range as plotrange data)
            xd = data.datetime.plotrange(self.pinf.xstart, self.pinf.xend)
            xdates = [num2date(value) for value in xd]

            # plot ind above data
            c_up = []
            for ind in self.dplots_up[data]:
                rc, sub_rc = self.plotind(
                    data,
                    ind,
                    subinds=self.dplots_over[ind],
                    upinds=self.dplots_up[ind],
                    downinds=self.dplots_down[ind])
                if len(rc)>0:
                    c_up.append(rc)
                if len(sub_rc) > 0:
                    c_up.extend(sub_rc)

            # plot candles and ind on candles
            c_data, c_down = self.plotdata(data, self.dplots_over[data])

            #TODO
            for ind in self.dplots_down[data]:
                rc, sub_rc = self.plotind(
                    data,
                    ind,
                    subinds=self.dplots_over[ind],
                    upinds=self.dplots_up[ind],
                    downinds=self.dplots_down[ind],
                    )
                if len(rc)>0:
                    c_down.append(rc)
                if (len(sub_rc) > 0):
                    c_down.extend(sub_rc)

            data_name = data._name if data._name else f'data{data._idx}'
            if self.chart is None:
                self.chart = self.create_chart(c_top, filename=filename)

            self.show(self.chart, xdates, c_top, c_up, c_data, c_down, strat_name, data_name)
        return None

    def prepare_trades_list(self, data_name:str):
        trades = self.performance.gen_trades(data_name, True) if self.performance else pd.DataFrame()
        orders = self.performance.gen_orders(data_name) if self.performance else pd.DataFrame()
        if trades.empty or orders.empty:
            lst = []
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
        # HTMLChart_BN replaces the chart container when switching instruments.
        # Dispose the prior view's tooltip listener and payload before drawing
        # the next view, including when that next view has no trade markers.
        chart.run_script('window.__btTradeTooltipCleanup?.();')
        self.draw_main(chart, xdates, c_top, c_up, c_data, c_down, data_name)
        chart.sync_charts()
        trades_lst = self.prepare_trades_list(data_name)
        chart.set_trades(lst=trades_lst)
        chart.set_parameters_list(self.strat_params)
        if self.performance_metrics is not None:
            chart.set_performance_metrics(self.performance_metrics, strat_name)
        
        chart.new_window()
        chart.legend(visible=True)
        chart.fit()
        chart.price_scale(perm_width=100)

    @staticmethod
    def _tooltip_number(value, precision=4):
        if value is None or pd.isna(value):
            return '—'
        return f'{float(value):,.{precision}f}'

    @staticmethod
    def _tooltip_text(value):
        if value is None or pd.isna(value):
            return '—'
        return str(value)

    def _add_trade_marker_tooltips(self, chart, marker_details):
        """Attach an HTML hover card to the current Lightweight Charts pane."""
        if not self.p.trade_marker_tooltips or not marker_details:
            return

        # The data is embedded in an inline script. Escape HTML-significant
        # characters so values such as a data name cannot close that script.
        details_json = json.dumps(marker_details, ensure_ascii=False).translate(str.maketrans({
            '&': r'\u0026',
            '<': r'\u003c',
            '>': r'\u003e',
            '\u2028': r'\u2028',
            '\u2029': r'\u2029',
        }))
        chart.run_script(f'''
        (() => {{
            const handler = {chart.id};
            const markerDetails = {details_json};
            const markerDetailsByTime = new Map();
            markerDetails.forEach(detail => {{
                const key = String(detail.time);
                const records = markerDetailsByTime.get(key) || [];
                records.push(detail);
                markerDetailsByTime.set(key, records);
            }});
            const tooltip = document.createElement('div');
            tooltip.className = 'bt-trade-marker-tooltip';
            Object.assign(tooltip.style, {{
                position: 'absolute', display: 'none', pointerEvents: 'none', zIndex: '1000',
                minWidth: '210px', maxWidth: '320px', padding: '10px 12px', borderRadius: '6px',
                background: 'rgba(17, 26, 43, 0.96)', border: '1px solid #40506a',
                boxShadow: '0 8px 24px rgba(0, 0, 0, 0.35)', color: '#e5edf7',
                font: '12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',
                lineHeight: '1.45', whiteSpace: 'nowrap'
            }});
            handler.div.appendChild(tooltip);

            const hideTooltip = () => {{ tooltip.style.display = 'none'; }};
            const tooltipPreferenceKey = 'backtrader-next.trade-marker-tooltips';
            let tooltipToggle = document.getElementById('trade-tooltip-toggle');
            if (!tooltipToggle) {{
                tooltipToggle = document.createElement('button');
                tooltipToggle.id = 'trade-tooltip-toggle';
                tooltipToggle.type = 'button';
                Object.assign(tooltipToggle.style, {{
                    marginLeft: '8px', marginBottom: '8px', background: 'none',
                    border: '1px solid var(--border2)', borderRadius: 'var(--radius)',
                    color: 'var(--text-muted)', cursor: 'pointer', display: 'flex',
                    alignItems: 'center', padding: '3px 10px', fontSize: '12px',
                    fontFamily: 'var(--font)', fontWeight: '500', whiteSpace: 'nowrap'
                }});
                let enabled = true;
                try {{
                    const savedPreference = localStorage.getItem(tooltipPreferenceKey);
                    if (savedPreference !== null) enabled = savedPreference === 'true';
                }} catch (error) {{}}
                const updateTooltipToggle = () => {{
                    tooltipToggle.dataset.enabled = String(enabled);
                    tooltipToggle.textContent = 'Trade tooltips: ' + (enabled ? 'On' : 'Off');
                    tooltipToggle.title = enabled ? 'Disable trade tooltips' : 'Enable trade tooltips';
                    tooltipToggle.setAttribute('aria-pressed', String(enabled));
                }};
                tooltipToggle.addEventListener('click', () => {{
                    enabled = !enabled;
                    try {{ localStorage.setItem(tooltipPreferenceKey, String(enabled)); }} catch (error) {{}}
                    document.querySelectorAll('.bt-trade-marker-tooltip').forEach(element => {{
                        element.style.display = 'none';
                    }});
                    updateTooltipToggle();
                }});
                updateTooltipToggle();
                document.getElementById('theme-btn').insertAdjacentElement('afterend', tooltipToggle);
            }}
            const tooltipsEnabled = () => tooltipToggle.dataset.enabled === 'true';

            window.__btApplyChartTheme = theme => {{
                const colors = theme === 'dark'
                    ? {{ background: 'rgb(18, 24, 38)', text: '#d8d9db', grid: '#444', label: 'rgb(46, 46, 46)' }}
                    : {{ background: '#d8dce8', text: '#1a1d24', grid: '#b4baca', label: '#9aa1b5' }};
                const handlers = Object.values(window).filter(value => value instanceof Lib.Handler && value.div.isConnected);
                handlers.forEach(currentHandler => {{
                    currentHandler.chart.applyOptions({{
                        layout: {{ textColor: colors.text, background: {{ type: LightweightCharts.ColorType.Solid, color: colors.background }} }},
                        grid: {{ vertLines: {{ color: colors.grid }}, horzLines: {{ color: colors.grid }} }},
                        crosshair: {{
                            vertLine: {{ labelBackgroundColor: colors.label }},
                            horzLine: {{ labelBackgroundColor: colors.label }}
                        }}
                    }});
                    currentHandler.legend.div.style.color = theme === 'light'
                        ? '#000000'
                        : currentHandler.legend.color;

                    const seriesMarkers = currentHandler.seriesMarkers;
                    if (seriesMarkers?.markers && seriesMarkers?.setMarkers) {{
                        const themedMarkers = seriesMarkers.markers().map(marker => {{
                            if (marker.color !== 'lightgreen' && marker.color !== '#006400') return marker;
                            return {{ ...marker, color: theme === 'light' ? '#006400' : 'lightgreen' }};
                        }});
                        seriesMarkers.setMarkers(themedMarkers);
                    }}
                }});
            }};
            window.__btApplyChartTheme(document.documentElement.getAttribute('data-theme'));
            if (!document.documentElement.dataset.tradeTooltipThemeListener) {{
                document.documentElement.dataset.tradeTooltipThemeListener = 'true';
                document.getElementById('theme-btn').addEventListener('click', () => {{
                    window.__btApplyChartTheme(document.documentElement.getAttribute('data-theme'));
                }});
            }}

            const appendRow = (parent, label, value) => {{
                const row = document.createElement('div');
                row.style.display = 'flex';
                row.style.justifyContent = 'space-between';
                row.style.gap = '16px';
                const key = document.createElement('span');
                key.style.color = '#9eacc2';
                key.textContent = label;
                const content = document.createElement('span');
                content.style.textAlign = 'right';
                content.textContent = value;
                row.append(key, content);
                parent.appendChild(row);
            }};
            const showTooltip = (detail, point) => {{
                tooltip.replaceChildren();
                const title = document.createElement('div');
                title.style.color = detail.color;
                title.style.fontWeight = '700';
                title.style.marginBottom = '6px';
                title.textContent = detail.title;
                tooltip.appendChild(title);
                detail.fields.forEach(field => appendRow(tooltip, field.label, field.value));
                tooltip.style.display = 'block';
                const padding = 14;
                const left = point.x + tooltip.offsetWidth + padding > handler.div.clientWidth
                    ? Math.max(padding, point.x - tooltip.offsetWidth - padding)
                    : point.x + padding;
                const top = point.y + tooltip.offsetHeight + padding > handler.div.clientHeight
                    ? Math.max(padding, point.y - tooltip.offsetHeight - padding)
                    : point.y + padding;
                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
            }};

            const onCrosshairMove = param => {{
                if (!tooltipsEnabled()) {{
                    hideTooltip();
                    return;
                }}
                if (!param.point || !param.time || param.point.x < 0 || param.point.y < 0) {{
                    hideTooltip();
                    return;
                }}
                const candle = param.seriesData.get(handler.series);
                const candidates = markerDetailsByTime.get(String(Number(param.time))) || [];
                if (!candle || !candidates.length) {{
                    hideTooltip();
                    return;
                }}
                let hovered = null;
                let nearestDistance = Infinity;
                for (const detail of candidates) {{
                    const x = handler.chart.timeScale().timeToCoordinate(detail.time);
                    let anchorPrice = detail.price;
                    if (detail.position === 'below') anchorPrice = candle.low;
                    if (detail.position === 'above') anchorPrice = candle.high;
                    let y = handler.series.priceToCoordinate(anchorPrice);
                    if (x === null || y === null) continue;
                    if (detail.position === 'below') y += 14;
                    if (detail.position === 'above') y -= 14;
                    const distance = Math.hypot(param.point.x - x, param.point.y - y);
                    if (distance < 18 && distance < nearestDistance) {{
                        hovered = detail;
                        nearestDistance = distance;
                    }}
                }}
                hovered ? showTooltip(hovered, param.point) : hideTooltip();
            }};
            handler.chart.subscribeCrosshairMove(onCrosshairMove);
            handler.div.addEventListener('mouseleave', hideTooltip);
            window.__btTradeTooltipCleanup = () => {{
                handler.chart.unsubscribeCrosshairMove(onCrosshairMove);
                handler.div.removeEventListener('mouseleave', hideTooltip);
                tooltip.remove();
                window.__btTradeTooltipCleanup = undefined;
            }};
        }})();
        ''')

    def draw_main(self, chart, xdates, c_top:{}, c_up, c_data, c_down, data_name):

        def create_subchart(height=-300, toolbox=False):
            subchart = self.chart.create_subchart(position='left', width=1, height=height, sync=True, toolbox=toolbox)
            subchart.legend(visible=True)
            subchart.price_scale(perm_width=100)
            return subchart

        def draw_item(chart, id:int, item):
            for ind in item:
                if ind['mode']=='candle':
                    v_data = ind['data']
                    v_data['time'] = xdates
                    chart.set_zipped(pd.DataFrame(v_data))
                elif ind['mode']=='bar':
                    i_ls = ind.get('ls', None)
                    i_style = 'dashed' if i_ls=='--' else 'solid'
                    i_color = ind.get('color', None)
                    if not ind.get('samecolor', False):
                        self.pinf.nextcolor(0)
                    if i_color is None:
                        i_color = self.pinf.color(0)
                    v_label = ind['label']
                    v_data = ind['data']
                    line = chart.create_histogram(v_label, price_line=False, price_label=False)
                    v_data['time'] = xdates
                    line.set_zipped(pd.DataFrame(v_data))
                    hlines = ind.get('hlines', None)
                    if hlines:
                        for hline in hlines:
                            i_style = 'sparse_dotted' if self.pinf.sch.hlinesstyle=='...' else 'solid'
                            line.create_price_line(price=hline,
                                                color=self.pinf.sch.hlinescolor,
                                                width=self.pinf.sch.hlineswidth,
                                                style=i_style,
                                                price_label=False)
                elif ind['mode']=='plot':
                    i_ls = ind.get('ls', None)
                    i_style = 'dashed' if i_ls=='--' else 'solid'
                    i_color = ind.get('color', None)
                    if not ind.get('samecolor', False):
                        self.pinf.nextcolor(0)
                    if i_color is None:
                        i_color = self.pinf.color(0)
                    v_label = ind['label']
                    v_data = ind['data']
                    line = chart.create_line(v_label, color=i_color, style=i_style, price_line=False, price_label=False)
                    v_data['time'] = xdates
                    line.set_zipped(pd.DataFrame(v_data))
                    hlines = ind.get('hlines', None)
                    if hlines:
                        for hline in hlines:
                            i_style = 'sparse_dotted' if self.pinf.sch.hlinesstyle=='...' else 'solid'
                            line.create_price_line(price=hline,
                                                color=self.pinf.sch.hlinescolor,
                                                width=self.pinf.sch.hlineswidth,
                                                style=i_style,
                                                price_label=False)

        i=0
        if c_top:
            eq = c_top.get('eq', None)
            if eq is not None:
                v_label = eq['label']
                i_style = 'solid'
                i_color = 'red'
                v_data = eq['data']
                line = chart.create_line(v_label, color=i_color, style=i_style, price_line=False, price_label=False)
                line.set_zipped(pd.DataFrame(v_data))
                line.create_price_line(price=0, color='lightgreen', width=1, style='sparse_dotted', price_label=False)
            # dd = c_top.get('dd', None)
            # if dd is not None:
            #     v_label = dd['label']
            #     i_style = 'solid'
            #     i_color = 'blue'
            #     v_data = dd['data']
            #     line = chart.create_line(v_label, color=i_color, style=i_style, price_line=False, price_label=False)
            #     line.set_zipped(pd.DataFrame(v_data))
            subchart = create_subchart(height=-500)
        else:
            subchart = self.chart

        i=0
        for lst in c_data:
            draw_item(subchart, id=i, item=lst)
            i += 1

        # Plot Trades
        if c_data and self.performance is not None:
            trades = self.performance.gen_trades(data_name)
            # orders = self.performance.gen_orders(data_name).groupby('o_datetime')['o_size'].sum().reset_index()
            orders = self.performance.gen_orders(data_name)
            markers = list()
            marker_details = []
            for index, row in orders.iterrows():
                size = row['o_size']
                price = row['o_price']
                shape = 'arrow_up' if size>0 else 'arrow_down'
                color = 'lightgreen' if size>0 else 'red'
                # text = f'Buy @ {size}' if size>0 else f'Short @ {abs(size)}'
                text = f'Buy @ {price}' if size>0 else f'Short @ {price}'
                markers.append(dict(time=row['o_datetime'], position='below', shape=shape, color=color, text=text))
                markers.append(dict(time=row['o_datetime'], position='atPriceMiddle', shape='circle', color=color, text='', price=price, size=0.6))
                marker_details.append({
                    'id': f'entry-{row["o_ref"]}-{index}',
                    'time': float(subchart._single_datetime_format(row['o_datetime'])),
                    'price': float(price),
                    'position': 'below',
                    'color': color,
                    'title': 'Buy' if size > 0 else 'Short',
                    'fields': [
                        {'label': 'Instrument', 'value': data_name},
                        {'label': 'Order Ref', 'value': self._tooltip_text(row['o_ref'])},
                        {'label': 'Executed', 'value': format_datetime(row['o_datetime'])},
                        {'label': 'Price', 'value': self._tooltip_number(price)},
                        {'label': 'Quantity', 'value': self._tooltip_number(size)},
                    ],
                })
            for index, row in trades.iterrows():
                pnlcomm = row['pnlcomm']
                shape = 'square'
                color = 'yellow' if pnlcomm>0 else 'fuchsia'
                text = '+Profit+' if pnlcomm>0 else '-Loss-'
                markers.append(dict(time=row['dateclose'], position='above', shape=shape, color=color, text=text))
                marker_details.append({
                    'id': f'exit-{row["ref"]}-{index}',
                    'time': float(subchart._single_datetime_format(row['dateclose'])),
                    'price': float(row['priceclose']),
                    'position': 'above',
                    'color': color,
                    'title': 'Profit' if pnlcomm > 0 else 'Loss',
                    'fields': [
                        {'label': 'Instrument', 'value': data_name},
                        {'label': 'Trade Ref', 'value': self._tooltip_text(row['ref'])},
                        {'label': 'Opened', 'value': format_datetime(row['dateopen'])},
                        {'label': 'Closed', 'value': format_datetime(row['dateclose'])},
                        {'label': 'Entry Price', 'value': self._tooltip_number(row['priceopen'])},
                        {'label': 'Exit Price', 'value': self._tooltip_number(row['priceclose'])},
                        {'label': 'Size', 'value': self._tooltip_number(row['size'])},
                        {'label': 'Duration', 'value': self._tooltip_text(row['barlen']) + ' bars'},
                        {'label': 'Gross P&L', 'value': self._tooltip_number(row['pnl'])},
                        {'label': 'Commission', 'value': self._tooltip_number(row['commission'])},
                        {'label': 'Net P&L', 'value': self._tooltip_number(pnlcomm)},
                        {'label': 'Return', 'value': self._tooltip_number(row['return_pct'] * 100) + '%'},
                    ],
                })
            markers.sort(key=lambda m: m['time'])
            subchart.marker_list(markers)
            self._add_trade_marker_tooltips(subchart, marker_details)

        i=0
        for lst in c_down:
            # id = f'down_{i}'
            subchart = create_subchart(height=-300)
            draw_item(subchart, id=i, item=lst)
            i += 1

        return chart


    def calcrows(self, strategy):
        # Calculate the total number of rows
        rowsmajor = self.pinf.sch.rowsmajor
        rowsminor = self.pinf.sch.rowsminor
        nrows = 0

        datasnoplot = 0 ##??
        for data in strategy.datas:
            if not data.plotinfo.plot:
                # neither data nor indicators nor volume add rows
                datasnoplot += 1
                self.dplots_up.pop(data, None)
                self.dplots_down.pop(data, None)
                self.dplots_over.pop(data, None)

            else:
                pmaster = data.plotinfo.plotmaster
                if pmaster is data:
                    pmaster = None
                if pmaster is not None:
                    # data doesn't add a row, but volume may
                    if self.pinf.sch.volume:
                        nrows += rowsminor
                else:
                    # data adds rows, volume may
                    nrows += rowsmajor
                    if self.pinf.sch.volume and not self.pinf.sch.voloverlay:
                        nrows += rowsminor

        # top indicators/observers
        nrows += len(self.dplots_top) * rowsminor

        # indicators above datas
        nrows += sum(len(v) for v in self.dplots_up.values())
        nrows += sum(len(v) for v in self.dplots_down.values())

        self.pinf.nrows = nrows


    def plotind(self, iref, ind,
                subinds=None, upinds=None, downinds=None,
                masterax=None):
        ind_charts = []
        # check subind
        subinds = subinds or []
        upinds = upinds or []
        downinds = downinds or []

        # plot subindicators on self with independent axis above
        for upind in upinds:
            rc, sub_rc = self.plotind(iref, upind)
            # ind_charts.extend(rc)
            ind_charts.append(rc)
            if len(sub_rc) > 0:
                ind_charts.extend(sub_rc)

        indlabel = ind.plotlabel()

        # Scan lines quickly to find out if some lines have to be skipped for
        # legend
        toskip = 0
        for lineidx in range(ind.size()):
            line = ind.lines[lineidx]
            linealias = ind.lines._getlinealias(lineidx)
            lineplotinfo = getattr(ind.plotlines, f'_{lineidx}', None)
            if not lineplotinfo:
                lineplotinfo = getattr(ind.plotlines, linealias, None)
            if not lineplotinfo:
                lineplotinfo = AutoInfoClass()
            pltmethod = lineplotinfo._get('_method', 'plot')
            if pltmethod != 'plot':
                toskip += 1 - lineplotinfo._get('_plotskip', False)

        if toskip >= ind.size():
            toskip = 0

        hlines = None
        if masterax is None:
            # Set specific hlines if asked to
            hlines = ind.plotinfo._get('plothlines', [])
            if not hlines:
                hlines = ind.plotinfo._get('plotyhlines', [])

        for lineidx in range(ind.size()):
            line = ind.lines[lineidx]
            linealias = ind.lines._getlinealias(lineidx)

            lineplotinfo = getattr(ind.plotlines, f'_{lineidx}', None)
            if not lineplotinfo:
                lineplotinfo = getattr(ind.plotlines, linealias, None)

            if not lineplotinfo:
                lineplotinfo = AutoInfoClass()

            if lineplotinfo._get('_plotskip', False):
                continue

            label = (indlabel + ' ')
            label += lineplotinfo._get('_name', '') or linealias

            # plot data
            lplot = line.plotrange(self.pinf.xstart, self.pinf.xend)

            pltmethod = lineplotinfo._get('_method', 'plot')

            lplotarray = lplot
            if lineplotinfo._get('_skipnan', False): #??
                # Get the full array and a mask to skipnan
                lplotarray = np.array(lplot)
                lplotmask = np.isfinite(lplotarray)

                # Get both the axis and the data masked
                lplotarray = lplotarray[lplotmask]

            # Create indicator dictionary
            indicator = {
                'label': label,
                'mode': lineplotinfo._get('_method', 'plot'),
                'data': {label:lplotarray.tolist()},
                'hlines': hlines,
            }
            hlines = None  # only once
            i_color = lineplotinfo._get('color', None)
            if i_color is not None:
                indicator['color'] = i_color
            if lineplotinfo._get('_samecolor', False):
                indicator['samecolor'] = True
            i_ls = lineplotinfo._get('ls', None)
            if i_ls is not None:
                indicator['ls'] = i_ls

            ind_charts.append(indicator)

        # plot subindicators that were created on self
        for subind in subinds:
            rc, sub_rc = self.plotind(iref, subind, subinds=self.dplots_over[subind], masterax=masterax)
            ind_charts.extend(rc)
            if len(sub_rc) > 0:
                ind_charts.extend(sub_rc)

        sub_down_inds = []
        # plot subindicators on self with independent axis below
        for downind in downinds:
            rc, sub_rc = self.plotind(iref, downind, masterax=True)
            sub_down_inds.append(rc)
            if len(sub_rc) > 0:
                sub_down_inds.append(sub_rc)
        return ind_charts, sub_down_inds


    def plotdata(self, data, indicators):
        chart_data = []
        charts_down = []
        for ind in indicators:
            upinds = self.dplots_up[ind]
            for upind in upinds:
                self.plotind(data, upind,
                            subinds=self.dplots_over[upind],
                            upinds=self.dplots_up[upind],
                            downinds=self.dplots_down[upind])

        opens = data.open.plotrange(self.pinf.xstart, self.pinf.xend)
        highs = data.high.plotrange(self.pinf.xstart, self.pinf.xend)
        lows = data.low.plotrange(self.pinf.xstart, self.pinf.xend)
        closes = data.close.plotrange(self.pinf.xstart, self.pinf.xend)
        volumes = data.volume.plotrange(self.pinf.xstart, self.pinf.xend)

        df_data = {
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
        }

        pmaster = data.plotinfo.plotmaster
        if pmaster is data:
            pmaster = None
        voloverlay = (self.pinf.sch.voloverlay and pmaster is None)

        if self.pinf.sch.volume and voloverlay:
            df_data['volume'] = volumes

        datalabel = ''
        if hasattr(data, '_name') and data._name:
            datalabel += data._name

        if hasattr(data, '_compression') and hasattr(data, '_timeframe'):
            tfname = TimeFrame.getname(data._timeframe, data._compression)
            datalabel += ' (%d %s)' % (data._compression, tfname)

        chart_data.append([{
            'label':datalabel,
            'mode':'candle',
            'data': df_data,
            }])


        if self.pinf.sch.volume and not voloverlay:
            df_vol = {
                # 'time': xdates,
                'volume': volumes,
            }
            charts_down.append([{
                'label':'volume',
                'mode':'hist',
                'data': df_vol,
                }])

        for ind in indicators:
            rc, sub_rc = self.plotind(data, ind, subinds=self.dplots_over[ind], masterax=True)
            # chart_data.extend(rc)
            chart_data.append(rc)
            if len(sub_rc) > 0:
                chart_data.append(sub_rc)

        for ind in indicators:
            downinds = self.dplots_down[ind]
            for downind in downinds:
                rc, sub_rc = self.plotind(data, downind,
                            subinds=self.dplots_over[downind],
                            upinds=self.dplots_up[downind],
                            downinds=self.dplots_down[downind])
                # charts_down.extend(rc)
                charts_down.append(rc)
                if len(sub_rc) > 0:
                    charts_down.append(sub_rc)
        return chart_data, charts_down


    #+-
    def sortdataindicators(self, strategy:Strategy):
        # These lists/dictionaries hold the subplots that go above each data
        self.dplots_top = list()
        self.dplots_up = collections.defaultdict(list)
        self.dplots_down = collections.defaultdict(list)
        self.dplots_over = collections.defaultdict(list)

        # Sort observers in the different lists/dictionaries
        #??TODO
        # for x in strategy.getobservers():
        #     if not x.plotinfo.plot or x.plotinfo.plotskip:
        #         continue

        #     if x.plotinfo.subplot:
        #         self.dplots_top.append(x)
        #     else:
        #         key = getattr(x._clock, 'owner', x._clock)
        #         self.dplots_over[key].append(x)

        # Sort indicators in the different lists/dictionaries
        for x in strategy.getindicators():
            if not hasattr(x, 'plotinfo'):
                # no plotting support - so far LineSingle derived classes
                continue

            if not x.plotinfo.plot or x.plotinfo.plotskip:
                continue

            x._plotinit()  # will be plotted ... call its init function

            # support LineSeriesStub which has "owner" to point to the data
            key = getattr(x._clock, 'owner', x._clock)
            if key is strategy:  # a LinesCoupler
                key = strategy.data

            if getattr(x.plotinfo, 'plotforce', False):
                if key not in strategy.datas:
                    datas = strategy.datas
                    while True:
                        if key not in strategy.datas:
                            key = key._clock
                        else:
                            break

            xpmaster = x.plotinfo.plotmaster
            if xpmaster is x:
                xpmaster = None
            if xpmaster is not None:
                key = xpmaster

            if x.plotinfo.subplot and xpmaster is None:
                if x.plotinfo.plotabove:
                    self.dplots_up[key].append(x)
                else:
                    self.dplots_down[key].append(x)
            else:
                self.dplots_over[key].append(x)
