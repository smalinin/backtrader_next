#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

from math import e
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import webbrowser
from pathlib import Path


class Statistics(object):
    graphs = []
    tables = []

    def report(self, name="Statistics", performance=None, show=True, filename="strat_quantstats.html", iplot=False):
        """Prepare statistics for the report"""
        if performance is None:
            exception = "No performance data provided"
            raise ValueError(exception)

        df_eq = performance.gen_eq()
        df_stats = performance.compute_stats()

        annual_trading_days = float(365 if df_eq.index.dayofweek.to_series().between(5, 6).mean() > 2 / 7 * .6
                                        else 252)
        win_year = int(annual_trading_days)
        win_half_year = int(annual_trading_days // 2)
        daily = df_eq['value'].resample('D').last().dropna()
        d_returns = daily.pct_change().dropna()
        d_cum_returns = (1 + d_returns).cumprod() - 1
        d_drawdown = ((daily / daily.cummax()) - 1) * 100
        d_drawdown_details = _drawdown_details(d_drawdown)

        self.graphs.append(
            create_fig(
                x=d_cum_returns.index, y=d_cum_returns.values * 100,
                title="Cumulative Returns %", color="green", fill="tozeroy")
        )
        self.graphs.append(
            create_fig(
                x=d_drawdown.index, y=d_drawdown.values,
                title="Drawdown %", color="red", fill="tozeroy", height=350)
        )

        d_cum_retunrs_log_pct = np.log(d_cum_returns + 1) * 100
        self.graphs.append(
            create_fig(
                x=d_cum_retunrs_log_pct.index, y=d_cum_retunrs_log_pct.values,
                title="Cumulative Returns (Log Scaled) %", color="green", fill="tozeroy")
        )

        d_eoy_returns = d_returns.resample('YE').sum() * 100
        d_eoy_returns.index = d_eoy_returns.index.year
        self.graphs.append(
            create_bar(
                x=d_eoy_returns.index, y=d_eoy_returns.values,
                title="End of Year Returns %", color="dodgerblue")
        )

        d_distribution_monthly = d_returns.resample('ME').sum() * 100
        self.graphs.append(
            create_bar(
                x=d_distribution_monthly.index, y=d_distribution_monthly.values,
                title="Monthly Returns %", color="dodgerblue")
        )


        d_rolling_sharpe = (d_returns.rolling(window=win_half_year).mean() / d_returns.rolling(window=win_half_year).std()) * np.sqrt(win_year)
        fig = create_fig(
                x=d_rolling_sharpe.index, y=d_rolling_sharpe.values,
                title="Rolling Sharpe (6-Months)", color="blue")
        add_level(fig, x0=d_rolling_sharpe.index[0], x1=d_rolling_sharpe.index[-1], y0=1.0, y1=1.0)
        add_level(fig, x0=d_rolling_sharpe.index[0], x1=d_rolling_sharpe.index[-1], y0=2.0, y1=2.0, color="green")
        self.graphs.append(fig)

        _rolling_downside_std = d_returns.rolling(window=win_half_year).apply(lambda x: x[x < 0].std())
        d_rolling_sortino = (d_returns.rolling(window=win_half_year).mean() / _rolling_downside_std) * np.sqrt(win_year)
        fig = create_fig(
                x=d_rolling_sortino.index, y=d_rolling_sortino.values,
                title="Rolling Sortino (6-Months)", color="blue")
        add_level(fig, x0=d_rolling_sortino.index[0], x1=d_rolling_sortino.index[-1], y0=1.0, y1=1.0)
        add_level(fig, x0=d_rolling_sortino.index[0], x1=d_rolling_sortino.index[-1], y0=2.0, y1=2.0, color="green")
        self.graphs.append(fig)


        d_rolling_volatility = d_returns.rolling(window=win_half_year).std() * np.sqrt(win_year)
        fig = create_fig(
                x=d_rolling_volatility.index, y=d_rolling_volatility.values,
                title="Rolling Volatility (6-Months)", color="blue")
        self.graphs.append(fig)


        ### Metrics ####
        fig_metrics = go.Figure(data=[go.Table(
            header=dict(values=["Metric", "Value"], fill_color='lightgray'),
            cells=dict(values=[df_stats.index.tolist(), [str(val) for val in df_stats.values]],
            	align=["left", "right"],
            	font=dict(size=13),
            	height=26,
            	line_color='darkgray',
            	fill_color=[["#f0f0f0" if i % 2 == 0 else "rgb(244,255,255)" for i in range(len(df_stats))]],
            ),
        )])
        fig_metrics.update_layout(title="Performance Metrics", margin=dict(l=20, r=10, t=30, b=10), height=980, font=dict(size=12))
        self.tables.append(fig_metrics)


        # Metrics Additional
        addons = pd.Series(dtype=object)
        addons["Max Consecutive Wins"] = (_consecutive_wins(d_returns)).round(0)
        addons["Max Consecutive Losses"] = (_consecutive_losses(d_returns)).round(0)
        addons["Expected Daily [%]"] = (_expected_return(d_returns) * 100).round(2)
        addons["Expected Monthly [%]"] = (_expected_return(d_returns, aggregate="M") * 100).round(2)
        addons["Expected Yearly [%]"] = (_expected_return(d_returns, aggregate="A") * 100).round(2)

        fig_addons = go.Figure(data=[go.Table(
            header=dict(values=["Metric", "Value"], fill_color='lightgray'),
            cells=dict(values=[addons.index.tolist(), addons.values.tolist()],
            align=["left", "left"],
            font=dict(size=13),
            height=26,
            line_color='darkgray',
            fill_color=[["#f0f0f0" if i % 2 == 0 else "rgb(244,255,255)" for i in range(len(addons))]],
            ),
        )])
        fig_addons.update_layout(title="Additional Metrics", margin=dict(l=20, r=10, t=30, b=10), height=220, font=dict(size=12))
        self.tables.append(fig_addons)


        # EOY Returns
        yoy = pd.DataFrame(_group_returns(d_returns, d_returns.index.year) * 100)
        yoy.columns = ["Return"]
        yoy["Cumulative"] = _group_returns(d_returns, d_returns.index.year, True)
        yoy["Return"] = yoy["Return"].round(2)
        yoy["Cumulative"] = (yoy["Cumulative"] * 100).round(2)
        yoy_drawdown = d_drawdown.resample('YE').min().round(2)
        yoy_drawdown.index = yoy_drawdown.index.year
        yoy["Drawdown"] = yoy_drawdown
        yoy.index.name = "Year"

        fig_yoy = go.Figure(data=[go.Table(
            header=dict(values=["Year", "Return %", "Cumulative %", "Max Drawdown %"], fill_color='lightgray'),
            cells=dict(values=[yoy.index.tolist(), yoy["Return"].tolist(), yoy["Cumulative"].tolist(), yoy["Drawdown"].tolist()],
            align=["right", "right", "right", "right"],
            font=dict(size=13),
            height=26,
            line_color='darkgray',
            fill_color=[["#f0f0f0" if i % 2 == 0 else "rgb(244,255,255)" for i in range(len(yoy))]],
            ),
        )])
        fig_yoy.update_layout(title="EOY Returns", margin=dict(l=20, r=10, t=30, b=10), height=400, font=dict(size=12))
        self.tables.append(fig_yoy)

        # Worst 10 Drawdowns
        d_drawdown_details = _drawdown_details(d_drawdown)
        dd_info = d_drawdown_details.sort_values(by="max drawdown", ascending=True)[:10]
        dd_info = dd_info[["start", "end", "max drawdown", "days"]]
        dd_info.columns = ["Started", "Recovered", "Drawdown", "Days"]
        fig_dd = go.Figure(data=[go.Table(
            header=dict(values=["Started", "Recovered", "Drawdown %", "Days"], fill_color='lightgray'),
            cells=dict(values=[dd_info["Started"].tolist(), dd_info["Recovered"].tolist(), dd_info["Drawdown"].tolist(), dd_info["Days"].tolist()],
            align=["left", "left", "right", "right"],
            font=dict(size=13),
            height=26,
            line_color='darkgray',
            fill_color=[["#f0f0f0" if i % 2 == 0 else "rgb(244,255,255)" for i in range(len(dd_info))]],
            ),
        )])
        fig_dd.update_layout(title="Worst 10 Drawdowns", margin=dict(l=20, r=10, t=30, b=10), height=360, font=dict(size=12))
        self.tables.append(fig_dd)


        ## Gen HTML report
        html_graphs = [
            pio.to_html(fig, full_html=False, include_plotlyjs="cdn" if i == 0 else False)
            for i, fig in enumerate(self.graphs)
        ]
        html_tables = [
            pio.to_html(fig, full_html=False, include_plotlyjs=False)
            for fig in self.tables
        ]

        full_html = f"""
<html>
<head>
    <title>QuantStats Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 5px 20px;
            background: whitesmoke;
        }}
        .report-container {{
            display: flex;
        }}
        .column {{
            display: flex;
            flex-direction: column;
        }}
        .left-column {{
            flex: 1 1 0%;
            min-width: 500px;
        }}
        .right-column {{
            flex: 0 0 600px;
            min-width: 400px;
            max-width: 600px;
        }}
        .plot-container {{
            border: 1px solid #ddd;
            border-radius: 5px;
            position: relative;
            padding: 2px;
        }}
        .left-column .plot-container {{
            /*height: 550px;*/
        }}
        h4 {{
            width: 100%;
            text-align: center;
            margin-bottom: 5px;
        }}
        .fullscreen {{
            position: fixed !important;
            top: 0; left: 0; right: 0; bottom: 0;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 9999;
            background: #fff;
            margin: 0 !important;
            padding: 10px !important;
            box-sizing: border-box;
        }}
        .fullscreen-btn {{
            position: absolute;
            top: 8px;
            left: 12px;
            z-index: 10000;
            background: #eee;
            border: 1px solid #bbb;
            border-radius: 4px;
            padding: 2px 8px;
            cursor: pointer;
            font-size: 16px;
        }}
    </style>
</head>
<body>
    <h4>{name}</h4>
    <div class="report-container">
        <div class="column left-column">
            {''.join(f'<div class="plot-container"><button class="fullscreen-btn" onclick="toggleFullscreen(this)">⛶</button>{g}</div>' for g in html_graphs)}
        </div>
        <div class="column right-column">
            {''.join(f'<div class="plot-container">{t}</div>' for t in html_tables)}
        </div>
    </div>
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            if (window.Plotly) {{
                document.querySelectorAll('.js-plotly-plot').forEach(function(plot) {{
                    Plotly.Plots.resize(plot);
                }});
            }}
        }})

        function toggleFullscreen(btn) {{
            var container = btn.parentElement;
            var plotDiv = container.querySelector('.js-plotly-plot');
            var allBtns = document.querySelectorAll('.fullscreen-btn');
            if (!container.classList.contains('fullscreen')) {{
                container.classList.add('fullscreen');
                btn.textContent = '✖';
                allBtns.forEach(b => {{ if (b !== btn) b.style.display = 'none'; }});
            }} else {{
                container.classList.remove('fullscreen');
                btn.textContent = '⛶';
                allBtns.forEach(b => b.style.display = 'block');
            }}
            if (plotDiv && window.Plotly) {{
                setTimeout(function() {{
                    Plotly.Plots.resize(plotDiv);
                }}, 100);
            }}
        }}
    </script>
</body>
</html>
"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(full_html)
        file_path = Path(filename).resolve().as_uri()
        if iplot:
            print(f"Opening report in browser: {file_path}")
            webbrowser.open(file_path)
        elif show:
            webbrowser.open(file_path)


#### Figure Creation
def create_fig(x, y, title, color="blue", fill=None, height=550, margin=dict(l=50, r=10, t=30, b=10)):
    fig = go.Figure(go.Scatter(x=x, y=y, fill=fill, line=dict(color=color)))
    # fig_equity.update_layout(title="📈 Equity Curve", margin=dict(l=50, r=10, t=50, b=10), template="plotly_dark")
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12))
    return fig

def create_bar(x, y, title, color="blue", height=550, margin=dict(l=50, r=10, t=30, b=10)):
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=color))
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12))
    return fig

def add_level(fig, x0, x1, y0, y1, color="black", width=1, dash="dash"):
    fig.add_shape(
        type="line",
        x0=x0, x1=x1,
        y0=y0, y1=y1,
        line=dict(color=color, width=width, dash=dash)
    )

#### Statistics Functions
def _remove_outliers(returns, quantile=0.95):
    """Returns series of returns without the outliers"""
    return returns[returns < returns.quantile(quantile)]

def _drawdown_details(drawdown):
    # mark no drawdown
    no_dd = drawdown == 0
    _cols = ("start", "valley", "end", "days", "max drawdown", "99% max drawdown",)

    # extract dd start dates, first date of the drawdown
    starts = ~no_dd & no_dd.shift(1)
    starts = list(starts[starts.values].index)

    # extract end dates, last date of the drawdown
    ends = no_dd & (~no_dd).shift(1)
    ends = ends.shift(-1, fill_value=False)
    ends = list(ends[ends.values].index)

    # no drawdown
    if not starts:
        return pd.DataFrame(index=[], columns=_cols)

    # drawdown series begins in a drawdown
    if ends and starts[0] > ends[0]:
        starts.insert(0, drawdown.index[0])

    # series ends in a drawdown fill with last date
    if not ends or starts[-1] > ends[-1]:
        ends.append(drawdown.index[-1])

    # build dataframe from results
    data = []
    for i, _ in enumerate(starts):
        dd = drawdown[starts[i] : ends[i]]
        clean_dd = -_remove_outliers(-dd, 0.99)
        data.append(
            (starts[i],  dd.idxmin(), ends[i],  (ends[i] - starts[i]).days + 1,  dd.min(),  clean_dd.min(),)
        )

    df = pd.DataFrame(data=data, columns=_cols)
    df["days"] = df["days"].astype(int)
    df["max drawdown"] = df["max drawdown"].astype(float).round(2)
    df["99% max drawdown"] = df["99% max drawdown"].astype(float)
    df["start"] = df["start"].dt.strftime("%Y-%m-%d")
    df["end"] = df["end"].dt.strftime("%Y-%m-%d")
    df["valley"] = df["valley"].dt.strftime("%Y-%m-%d")
    return df

def _comp(returns):
    """Calculates total compounded returns"""
    return returns.add(1).prod() - 1

def _group_returns(returns, groupby, compounded=False):
    """Summarize returns
    group_returns(df, df.index.year)
    group_returns(df, [df.index.year, df.index.month])
    """
    if compounded:
        return returns.groupby(groupby).apply(_comp)
    return returns.groupby(groupby).sum()


def _aggregate_returns(returns, period=None, compounded=True):
    """Aggregates returns based on date periods"""
    if period is None or "day" in period:
        return returns
    index = returns.index

    if "month" in period:
        return _group_returns(returns, index.month, compounded=compounded)

    if "quarter" in period:
        return _group_returns(returns, index.quarter, compounded=compounded)

    if period == "A" or any(x in period for x in ["year", "eoy", "yoy"]):
        return _group_returns(returns, index.year, compounded=compounded)

    if "week" in period:
        return _group_returns(returns, index.week, compounded=compounded)

    if "eow" in period or period == "W":
        return _group_returns(returns, [index.year, index.week], compounded=compounded)

    if "eom" in period or period == "M":
        return _group_returns(returns, [index.year, index.month], compounded=compounded)

    if "eoq" in period or period == "Q":
        return _group_returns(returns, [index.year, index.quarter], compounded=compounded)

    if not isinstance(period, str):
        return _group_returns(returns, period, compounded)

    return returns

def _expected_return(returns, aggregate=None, compounded=True):
    """
    Returns the expected return for a given period
    by calculating the geometric holding period return
    """
    returns = _aggregate_returns(returns, aggregate, compounded)
    return np.prod(1 + returns) ** (1 / len(returns)) - 1


def _count_consecutive(data):
    """Counts consecutive data (like cumsum() with reset on zeroes)"""

    def _count(data):
        return data * (data.groupby((data != data.shift(1)).cumsum()).cumcount() + 1)

    if isinstance(data, pd.DataFrame):
        for col in data.columns:
            data[col] = _count(data[col])
        return data
    return _count(data)

def _consecutive_wins(returns, aggregate=None, compounded=True):
    """Returns the maximum consecutive wins by day/month/week/quarter/year"""
    returns = _aggregate_returns(returns, aggregate, compounded) > 0
    return _count_consecutive(returns).max()

def _consecutive_losses(returns, aggregate=None, compounded=True):
    """
    Returns the maximum consecutive losses by
    day/month/week/quarter/year
    """
    returns = _aggregate_returns(returns, aggregate, compounded) < 0
    return _count_consecutive(returns).max()

def _group_returns(returns, groupby, compounded=False):
    """Summarize returns
    group_returns(df, df.index.year)
    group_returns(df, [df.index.year, df.index.month])
    """
    if compounded:
        return returns.groupby(groupby).apply(_comp)
    return returns.groupby(groupby).sum()

