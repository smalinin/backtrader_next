#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import webbrowser
from html import escape
from pathlib import Path

from ..utils.dateintern import date2num, num2date


class Statistics(object):
    def __init__(self):
        self.graphs = []
        self.tables = []

    def report(self, name="Statistics", performance=None, strats=None, show=True, filename="strat_quantstats.html", iplot=False):
        """Prepare statistics for the report"""
        if performance is None:
            exception = "No performance data provided"
            raise ValueError(exception)

        self.graphs = []
        self.tables = []

        df_eq = performance.gen_eq()
        df_stats = performance.compute_stats()

        df_desc = pd.Series(dtype=object)
        df_desc_name = strats[0].__class__.__name__ if strats and len(strats) == 1 else "Multiple Strategies"
        if strats and len(strats) == 1:
            for key, val in strats[0].p._getitems():
                df_desc.loc[key]= strats[0].p._get(key)

        annual_trading_days = float(365 if df_eq.index.dayofweek.to_series().between(5, 6).mean() > 2 / 7 * .6
                                        else 252)
        win_year = int(annual_trading_days)
        win_half_year = int(annual_trading_days // 2)
        equity = df_eq['value'].dropna()
        daily = equity.resample('D').last().dropna()
        d_returns = daily.pct_change().dropna()
        # Include the first partial day in period totals, but retain complete
        # close-to-close daily returns for daily risk/volatility statistics.
        period_returns = daily.pct_change()
        if not daily.empty:
            period_returns.iloc[0] = daily.iloc[0] / equity.iloc[0] - 1
        d_cum_returns = equity / equity.iloc[0] - 1
        d_drawdown = ((equity / equity.cummax()) - 1) * 100
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

        # Use pandas where to handle edge cases and avoid log of negative/zero values
        # Only compute log where values are positive
        d_cum_retunrs_log_pct = (d_cum_returns + 1).where(d_cum_returns + 1 > 0, np.nan)
        d_cum_retunrs_log_pct = np.log(d_cum_retunrs_log_pct) * 100
        self.graphs.append(
            create_fig(
                x=d_cum_retunrs_log_pct.index, y=d_cum_retunrs_log_pct.values,
                title="Cumulative Returns (Log Scaled) %", color="green", fill="tozeroy")
        )

        d_eoy_returns = period_returns.resample('YE').apply(_comp) * 100
        d_eoy_returns.index = d_eoy_returns.index.year
        self.graphs.append(
            create_bar(
                x=d_eoy_returns.index, y=d_eoy_returns.values,
                title="End of Year Returns %", color="dodgerblue")
        )

        d_distribution_monthly = period_returns.resample('ME').apply(_comp) * 100
        self.graphs.append(
            create_bar(
                x=d_distribution_monthly.index, y=d_distribution_monthly.values,
                title="Monthly Returns %", color="dodgerblue")
        )

        month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly_heatmap = d_distribution_monthly.groupby(
            [d_distribution_monthly.index.year, d_distribution_monthly.index.month]
        ).first().unstack()
        monthly_heatmap = monthly_heatmap.reindex(columns=range(1, 13))
        monthly_heatmap.columns = month_labels
        monthly_heatmap = monthly_heatmap.sort_index(ascending=False)
        if monthly_heatmap.empty:
            fig = create_empty_fig(title="Monthly Returns Heatmap %", height=380)
        else:
            monthly_heatmap_labels = monthly_heatmap.apply(
                lambda column: column.map(lambda value: "" if pd.isna(value) else f"{value:.2f}")
            )
            fig = create_heatmap(
                z=monthly_heatmap.to_numpy(),
                x=monthly_heatmap.columns.tolist(),
                y=monthly_heatmap.index.tolist(),
                title="Monthly Returns Heatmap %",
                colorscale="RdYlGn",
                zmid=0,
                colorbar_title="Return %",
                height=380,
                hovertemplate="Year %{y}<br>Month %{x}<br>Return %{z:.2f}%<extra></extra>",
            )
            fig.update_traces(
                text=monthly_heatmap_labels.to_numpy(),
                texttemplate="%{text}",
                textfont=dict(size=11),
            )
        self.graphs.append(fig)

        d_returns_pct = d_returns * 100
        histogram_bins = max(12, min(60, int(np.sqrt(len(d_returns_pct) or 1) * 4)))
        fig = create_histogram(
            x=d_returns_pct.values,
            title="Daily Returns Distribution %",
            color="dodgerblue",
            height=380,
            nbinsx=histogram_bins,
        )
        fig.update_layout(xaxis_title="Daily Return %", yaxis_title="Days")
        fig.update_traces(
            hovertemplate="Daily Return %{x:.2f}%<br>Days in Bin %{y}<extra></extra>"
        )
        if not d_returns_pct.empty:
            var_95 = float(np.nanpercentile(d_returns_pct, 5))
            cvar_95 = float(d_returns_pct[d_returns_pct <= var_95].mean())
            fig.add_vline(x=0, line_color="black", line_width=1, line_dash="dot")
            fig.add_vline(
                x=var_95,
                line_color="orange",
                line_width=2,
                line_dash="dash",
                annotation_text=f"VaR 95% {var_95:.2f}%",
                annotation_position="top left",
                annotation_font_color="orange",
            )
            fig.add_vline(
                x=cvar_95,
                line_color="red",
                line_width=2,
                line_dash="dash",
                annotation_text=f"CVaR 95% {cvar_95:.2f}%",
                annotation_position="top right",
                annotation_font_color="red",
            )
        self.graphs.append(fig)


        d_rolling_sharpe = (d_returns.rolling(window=win_half_year).mean() / d_returns.rolling(window=win_half_year).std()) * np.sqrt(win_year)
        fig = create_fig(
                x=d_rolling_sharpe.index, y=d_rolling_sharpe.values,
                title="Rolling Sharpe (6-Months)", color="blue")
        if not d_rolling_sharpe.empty:
            add_level(fig, x0=d_rolling_sharpe.index[0], x1=d_rolling_sharpe.index[-1], y0=1.0, y1=1.0)
            add_level(fig, x0=d_rolling_sharpe.index[0], x1=d_rolling_sharpe.index[-1], y0=2.0, y1=2.0, color="green")
        self.graphs.append(fig)

        _rolling_downside_std = d_returns.rolling(window=win_half_year).apply(
            lambda x: np.sqrt(np.mean(np.minimum(x, 0) ** 2))
        )
        _rolling_downside_std = _rolling_downside_std.where(_rolling_downside_std != 0)
        d_rolling_sortino = (d_returns.rolling(window=win_half_year).mean() / _rolling_downside_std) * np.sqrt(win_year)
        fig = create_fig(
                x=d_rolling_sortino.index, y=d_rolling_sortino.values,
                title="Rolling Sortino (6-Months)", color="blue")
        if not d_rolling_sortino.empty:
            add_level(fig, x0=d_rolling_sortino.index[0], x1=d_rolling_sortino.index[-1], y0=1.0, y1=1.0)
            add_level(fig, x0=d_rolling_sortino.index[0], x1=d_rolling_sortino.index[-1], y0=2.0, y1=2.0, color="green")
        self.graphs.append(fig)

        d_rolling_win_rate = (d_returns.gt(0).rolling(window=win_half_year).mean() * 100)
        fig = create_fig(
            x=d_rolling_win_rate.index, y=d_rolling_win_rate.values,
            title="Rolling Win Rate (6-Months) %", color="seagreen")
        fig.update_layout(yaxis=dict(range=[0, 100]))
        if not d_rolling_win_rate.empty:
            add_level(fig, x0=d_rolling_win_rate.index[0], x1=d_rolling_win_rate.index[-1], y0=50.0, y1=50.0)
        self.graphs.append(fig)


        d_rolling_volatility = d_returns.rolling(window=win_half_year).std() * np.sqrt(win_year)
        fig = create_fig(
                x=d_rolling_volatility.index, y=d_rolling_volatility.values,
                title="Rolling Volatility (6-Months)", color="blue")
        self.graphs.append(fig)

        d_rolling_geomean = d_returns.rolling(window=win_half_year).apply(_expected_return, raw=False)
        d_rolling_ann_return_pct = ((1 + d_rolling_geomean) ** win_year - 1) * 100
        rolling_risk = _rolling_drawdown_risk(equity, daily, win_half_year)
        d_rolling_window_max_drawdown = rolling_risk['max_drawdown']
        d_rolling_calmar = d_rolling_ann_return_pct / d_rolling_window_max_drawdown.abs()
        d_rolling_calmar = d_rolling_calmar.where(d_rolling_window_max_drawdown != 0)
        fig = create_fig(
            x=d_rolling_calmar.index, y=d_rolling_calmar.values,
            title="Rolling Calmar (6-Months)", color="mediumpurple")
        if not d_rolling_calmar.empty:
            add_level(fig, x0=d_rolling_calmar.index[0], x1=d_rolling_calmar.index[-1], y0=1.0, y1=1.0)
        self.graphs.append(fig)

        d_rolling_ulcer_index = rolling_risk['ulcer_index']
        fig = create_fig(
            x=d_rolling_ulcer_index.index, y=d_rolling_ulcer_index.values,
            title="Rolling Ulcer Index (6-Months)", color="indianred", fill="tozeroy", height=350)
        self.graphs.append(fig)

        d_rolling_max_drawdown = rolling_risk['max_drawdown']
        fig = create_fig(
            x=d_rolling_max_drawdown.index, y=d_rolling_max_drawdown.values,
            title="Rolling Max Drawdown (6-Months) %", color="crimson", fill="tozeroy", height=350)
        self.graphs.append(fig)

        d_time_under_water = _time_under_water(d_drawdown)
        fig = create_fig(
            x=d_time_under_water.index, y=d_time_under_water.values,
            title="Time Under Water (Calendar Days)", color="darkorange", fill="tozeroy", height=350)
        self.graphs.append(fig)

        trades_df = performance.gen_trades().copy()
        if trades_df.empty:
            self.graphs.append(create_empty_fig(title="Trade Duration vs Return", height=380))
            self.graphs.append(create_empty_fig(title="Trade Returns Distribution %", height=360))
            self.graphs.append(create_empty_fig(title="Trade PnL Distribution", height=360))
            self.graphs.append(create_empty_fig(title="MFE/MAE vs Final Return %", height=420))
        else:
            trades_df["Duration"] = trades_df["dateclose"] - trades_df["dateopen"]
            trades_df["Duration Hours"] = trades_df["Duration"].dt.total_seconds().div(3600)
            trades_df["Return %"] = trades_df["return_pct"] * 100

            fig = create_scatter(
                x=trades_df["Duration Hours"].values,
                y=trades_df["Return %"].values,
                title="Trade Duration vs Return",
                marker=dict(
                    size=8,
                    opacity=0.75,
                    color=trades_df["pnlcomm"].values,
                    colorscale="RdYlGn",
                    colorbar=dict(title="PnL"),
                    showscale=True,
                ),
                height=380,
                customdata=np.column_stack([
                    trades_df["data_name"].astype(str).values,
                    trades_df["pnlcomm"].round(2).values,
                    trades_df["dateopen"].astype(str).values,
                    trades_df["dateclose"].astype(str).values,
                ]),
                hovertemplate=(
                    "Instrument %{customdata[0]}<br>Duration %{x:.2f}h<br>Return %{y:.2f}%"
                    "<br>PnL %{customdata[1]}<br>Open %{customdata[2]}<br>Close %{customdata[3]}<extra></extra>"
                ),
            )
            fig.update_layout(xaxis_title="Duration (Hours)", yaxis_title="Return %")
            fig.add_hline(y=0, line_color="black", line_width=1, line_dash="dot")
            self.graphs.append(fig)

            trade_return_bins = max(10, min(50, int(np.sqrt(len(trades_df) or 1) * 4)))
            fig = create_histogram(
                x=trades_df["Return %"].values,
                title="Trade Returns Distribution %",
                color="mediumseagreen",
                height=360,
                nbinsx=trade_return_bins,
            )
            fig.update_layout(xaxis_title="Trade Return %", yaxis_title="Trades")
            fig.update_traces(
                hovertemplate="Trade Return %{x:.2f}%<br>Trades in Range %{y}<extra></extra>"
            )
            fig.add_vline(x=0, line_color="black", line_width=1, line_dash="dot")
            self.graphs.append(fig)

            trade_pnl_bins = max(10, min(50, int(np.sqrt(len(trades_df) or 1) * 4)))
            fig = create_histogram(
                x=trades_df["pnlcomm"].values,
                title="Trade PnL Distribution",
                color="steelblue",
                height=360,
                nbinsx=trade_pnl_bins,
            )
            fig.update_layout(xaxis_title="Trade PnL", yaxis_title="Trades")
            fig.update_traces(
                hovertemplate="Trade PnL %{x:.2f}<br>Trades in Range %{y}<extra></extra>"
            )
            fig.add_vline(x=0, line_color="black", line_width=1, line_dash="dot")
            self.graphs.append(fig)

            trade_excursions = _compute_trade_excursions(performance, trades_df)
            excursions_df = pd.concat([trades_df.reset_index(drop=True), trade_excursions], axis=1)
            excursions_df = excursions_df.dropna(subset=["mfe_pct", "mae_pct"], how="all")
            if excursions_df.empty:
                fig = create_empty_fig(title="MFE/MAE vs Final Return %", height=420)
            else:
                fig = create_multi_scatter(title="MFE/MAE vs Final Return %", height=420)
                customdata = np.column_stack([
                    excursions_df["data_name"].astype(str).values,
                    excursions_df["pnlcomm"].round(2).values,
                    excursions_df["dateopen"].astype(str).values,
                    excursions_df["dateclose"].astype(str).values,
                ])
                fig.add_trace(go.Scatter(
                    x=excursions_df["final_return_pct"].values,
                    y=excursions_df["mfe_pct"].values,
                    mode="markers",
                    name="MFE",
                    marker=dict(color="goldenrod", size=8, opacity=0.75),
                    customdata=customdata,
                    hovertemplate=(
                        "Instrument %{customdata[0]}<br>Final Return %{x:.2f}%<br>MFE %{y:.2f}%"
                        "<br>PnL %{customdata[1]}<br>Open %{customdata[2]}<br>Close %{customdata[3]}<extra></extra>"
                    ),
                ))
                fig.add_trace(go.Scatter(
                    x=excursions_df["final_return_pct"].values,
                    y=excursions_df["mae_pct"].values,
                    mode="markers",
                    name="MAE",
                    marker=dict(color="indianred", size=8, opacity=0.75),
                    customdata=customdata,
                    hovertemplate=(
                        "Instrument %{customdata[0]}<br>Final Return %{x:.2f}%<br>MAE %{y:.2f}%"
                        "<br>PnL %{customdata[1]}<br>Open %{customdata[2]}<br>Close %{customdata[3]}<extra></extra>"
                    ),
                ))
                fig.update_layout(xaxis_title="Final Return %", yaxis_title="Excursion %")
                fig.add_hline(y=0, line_color="black", line_width=1, line_dash="dot")
                fig.add_vline(x=0, line_color="black", line_width=1, line_dash="dot")
            self.graphs.append(fig)


        ### Params ####
        if strats and len(strats) == 1:
            fig_params = go.Figure(data=[go.Table(
                header=dict(values=["Parameter", "Value"], fill_color='lightgray'),
                cells=dict(values=[df_desc.index.tolist(), [str(val) for val in df_desc.values]],
            	    align=["left", "right"],
            	    font=dict(size=13),
            	    height=26,
            	    line_color='darkgray',
            	    fill_color=[["#f0f0f0" if i % 2 == 0 else "rgb(244,255,255)" for i in range(len(df_desc))]],
                ),
            )])
            fig_params.update_layout(title=f"Strategy [{df_desc_name}] Parameters", margin=dict(l=20, r=10, t=30, b=10), height=300, font=dict(size=12))
            self.tables.append(fig_params)

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
        fig_metrics.update_layout(title="Performance Metrics", margin=dict(l=20, r=10, t=30, b=10), height=1040, font=dict(size=12))
        self.tables.append(fig_metrics)


        # Metrics Additional
        addons = pd.Series(dtype=object)
        addons["Max Consecutive Wins"] = round(_consecutive_wins(d_returns), 0)
        addons["Max Consecutive Losses"] = round(_consecutive_losses(d_returns), 0)
        addons["Expected Daily [%]"] = round(_expected_return(d_returns) * 100, 2)
        addons["Expected Monthly [%]"] = round(_expected_return(period_returns, aggregate="M") * 100, 2)
        addons["Expected Yearly [%]"] = round(_expected_return(period_returns, aggregate="A") * 100, 2)

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
        yoy = pd.DataFrame(_group_returns(period_returns, period_returns.index.year, compounded=True) * 100)
        yoy.columns = ["Return"]
        yoy["Cumulative"] = d_cum_returns.groupby(d_cum_returns.index.year).last()
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
        dd_info = dd_info.copy()
        dd_info['start'] = dd_info['start'].map(lambda dt: dt.isoformat(sep=' '))
        dd_info['end'] = [end.isoformat(sep=' ') if recovered else 'Not recovered'
                          for end, recovered in zip(dd_info['end'], dd_info['recovered'])]
        dd_info['days'] = dd_info['days'].astype(float).round(4)
        dd_info['max drawdown'] = dd_info['max drawdown'].astype(float).round(2)
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
        _apply_initial_dark_theme(self.graphs)
        _apply_initial_dark_theme(self.tables)

        graph_items = []
        for i, fig in enumerate(self.graphs):
            graph_items.append({
                "id": f"graph-{i + 1}",
                "title": getattr(getattr(fig.layout, "title", None), "text", None) or f"Graph {i + 1}",
                "html": pio.to_html(fig, full_html=False, include_plotlyjs="cdn" if i == 0 else False),
            })

        graph_filters_html = "".join(
            f'<label class="graph-filter-item"><input class="graph-filter-checkbox" type="checkbox" data-graph-id="{item["id"]}" checked><span>{escape(item["title"])}</span></label>'
            for item in graph_items
        ) or '<div class="graph-filter-empty">No charts available</div>'
        html_graphs = "".join(
            f'<div class="plot-container graph-card" data-graph-id="{item["id"]}" data-graph-title="{escape(item["title"], quote=True)}"><button class="fullscreen-btn" onclick="toggleFullscreen(this)">⛶</button>{item["html"]}</div>'
            for item in graph_items
        )
        html_tables = [
            pio.to_html(fig, full_html=False, include_plotlyjs=False)
            for fig in self.tables
        ]

        full_html = f"""
<html>
<head>
    <title>QuantStats Report</title>
    <script>
        (function() {{
            var theme = 'dark';
            try {{
                var storedTheme = localStorage.getItem('stats-report-theme');
                if (storedTheme === 'light' || storedTheme === 'dark') {{
                    theme = storedTheme;
                }}
            }} catch (error) {{}}
            document.documentElement.dataset.theme = theme;
        }})();
    </script>
    <style>
        :root {{
            color-scheme: light;
            --page-bg: #f3f5f9;
            --page-text: #16202d;
            --muted-text: #5c6777;
            --panel-bg: #ffffff;
            --panel-border: #d6dbe4;
            --button-bg: #eef2f7;
            --button-text: #16202d;
            --button-border: #c2cad6;
            --button-hover: #e4e9f1;
            --plot-paper-bg: #ffffff;
            --plot-bg: #ffffff;
            --plot-font: #16202d;
            --plot-grid: #dde3eb;
            --plot-axis: #95a1b2;
            --plot-zero: #c7d0dc;
            --plot-hover-bg: #ffffff;
            --plot-hover-font: #16202d;
            --shape-neutral: #3d4756;
            --table-header-fill: #e5e7eb;
            --table-header-font: #111827;
            --table-cell-even: #f8fafc;
            --table-cell-odd: #eef2f7;
            --table-cell-font: #16202d;
            --table-line: #cbd5e1;
            --modebar-bg: rgba(255, 255, 255, 0.88);
            --modebar-color: #16202d;
        }}
        :root[data-theme="dark"] {{
            color-scheme: dark;
            --page-bg: #0b1220;
            --page-text: #e5edf7;
            --muted-text: #96a3b8;
            --panel-bg: #111a2b;
            --panel-border: #243147;
            --button-bg: #182235;
            --button-text: #e5edf7;
            --button-border: #33425c;
            --button-hover: #233149;
            --plot-paper-bg: #111a2b;
            --plot-bg: #111a2b;
            --plot-font: #e5edf7;
            --plot-grid: #2a3850;
            --plot-axis: #70819a;
            --plot-zero: #3d4d67;
            --plot-hover-bg: #182235;
            --plot-hover-font: #e5edf7;
            --shape-neutral: #d1dae6;
            --table-header-fill: #243147;
            --table-header-font: #f8fbff;
            --table-cell-even: #111a2b;
            --table-cell-odd: #162238;
            --table-cell-font: #e5edf7;
            --table-line: #33425c;
            --modebar-bg: rgba(17, 26, 43, 0.92);
            --modebar-color: #e5edf7;
        }}
        body {{
            font-family: Arial, sans-serif;
            margin: 5px 20px;
            background: var(--page-bg);
            color: var(--page-text);
            transition: background-color 0.2s ease, color 0.2s ease;
        }}
        .report-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 8px;
        }}
        .report-header-left {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }}
        .report-header-actions {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .theme-toggle {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            border: 1px solid var(--button-border);
            border-radius: 999px;
            background: var(--button-bg);
            color: var(--button-text);
            padding: 8px 14px;
            font-size: 14px;
            line-height: 1;
            white-space: nowrap;
            cursor: pointer;
            transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
        }}
        .theme-toggle svg {{
            flex: 0 0 auto;
        }}
        .theme-toggle:hover {{
            background: var(--button-hover);
        }}
        .header-icon-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 38px;
            height: 38px;
            border: 1px solid var(--button-border);
            border-radius: 999px;
            background: var(--button-bg);
            color: var(--button-text);
            cursor: pointer;
            transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
            flex: 0 0 auto;
        }}
        .header-icon-btn:hover {{
            background: var(--button-hover);
        }}
        .header-icon-btn svg {{
            width: 16px;
            height: 16px;
        }}
        .report-container {{
            display: flex;
            gap: 12px;
            align-items: flex-start;
        }}
        .report-container.sidebar-collapsed .filters-column {{
            flex-basis: 0;
            width: 0;
            min-width: 0;
            max-width: 0;
            max-height: 0;
            margin-right: -12px;
            opacity: 0;
            transform: translateX(-12px);
            pointer-events: none;
            overflow: hidden;
        }}
        .report-container.sidebar-collapsed .graphs-column {{
            flex: 1 1 auto;
        }}
        .column {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .filters-column {{
            flex: 0 0 280px;
            width: 280px;
            min-width: 240px;
            max-width: 320px;
            max-height: calc(100vh - 24px);
            align-self: flex-start;
            position: sticky;
            top: 12px;
            overflow: hidden;
            opacity: 1;
            transform: translateX(0);
            transition: flex-basis 0.24s ease, width 0.24s ease, min-width 0.24s ease, max-width 0.24s ease, max-height 0.24s ease, margin-right 0.24s ease, opacity 0.18s ease, transform 0.24s ease;
        }}
        .filters-panel {{
            border: 1px solid var(--panel-border);
            border-radius: 10px;
            background: var(--panel-bg);
            padding: 14px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
            overflow: hidden;
            transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, opacity 0.18s ease, transform 0.24s ease;
        }}
        .report-container.sidebar-collapsed .filters-panel {{
            opacity: 0;
            transform: translateX(-8px);
        }}
        .filters-title {{
            font-size: 15px;
            font-weight: 600;
            color: var(--page-text);
            margin-bottom: 6px;
        }}
        .filters-subtitle {{
            color: var(--muted-text);
            font-size: 13px;
            margin-bottom: 12px;
        }}
        .graph-filter-actions {{
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
        }}
        .filter-action-btn {{
            flex: 1 1 0%;
            border: 1px solid var(--button-border);
            border-radius: 8px;
            background: var(--button-bg);
            color: var(--button-text);
            padding: 8px 10px;
            font-size: 13px;
            cursor: pointer;
            transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
        }}
        .filter-action-btn:hover {{
            background: var(--button-hover);
        }}
        .graph-filter-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: calc(100vh - 220px);
            overflow: auto;
            padding-right: 4px;
        }}
        .graph-filter-item {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 9px 10px;
            border: 1px solid var(--button-border);
            border-radius: 8px;
            background: var(--button-bg);
            color: var(--page-text);
            cursor: pointer;
            line-height: 1.35;
            transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
        }}
        .graph-filter-item:hover {{
            background: var(--button-hover);
        }}
        .graph-filter-item input {{
            margin-top: 3px;
        }}
        .graph-filter-empty {{
            color: var(--muted-text);
            font-size: 13px;
            padding: 4px 0;
        }}
        .graphs-column {{
            flex: 1 1 0%;
            min-width: 500px;
        }}
        .right-column {{
            flex: 0 0 600px;
            min-width: 400px;
            max-width: 600px;
        }}
        .plot-container {{
            border: 1px solid var(--panel-border);
            border-radius: 10px;
            position: relative;
            padding: 2px;
            background: var(--panel-bg);
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
            transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        }}
        .graphs-column .plot-container {{
            /*height: 550px;*/
        }}
        .graph-card.graph-hidden {{
            display: none;
        }}
        h4 {{
            margin: 0;
            color: var(--page-text);
        }}
        .fullscreen {{
            position: fixed !important;
            top: 0; left: 0; right: 0; bottom: 0;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 9999;
            background: var(--page-bg);
            margin: 0 !important;
            padding: 10px !important;
            box-sizing: border-box;
        }}
        .fullscreen-btn {{
            position: absolute;
            top: 8px;
            left: 12px;
            z-index: 10000;
            background: var(--button-bg);
            color: var(--button-text);
            border: 1px solid var(--button-border);
            border-radius: 4px;
            padding: 2px 8px;
            cursor: pointer;
            font-size: 16px;
        }}
        .js-plotly-plot .modebar {{
            background: var(--modebar-bg) !important;
            border-radius: 8px !important;
        }}
        .js-plotly-plot .modebar-btn path {{
            fill: var(--modebar-color) !important;
        }}
        .js-plotly-plot .modebar-btn:hover {{
            background: var(--button-hover) !important;
        }}
        @media (max-width: 1200px) {{
            .report-header {{
                flex-direction: column;
                align-items: stretch;
            }}
            .report-header-left {{
                width: 100%;
            }}
            .report-header-actions {{
                width: 100%;
            }}
            .report-container {{
                flex-direction: column;
            }}
            .filters-column {{
                position: static;
                width: auto;
                min-width: 0;
                max-width: none;
                max-height: none;
                flex-basis: auto;
            }}
            .graphs-column,
            .right-column {{
                min-width: 0;
                max-width: none;
                flex-basis: auto;
            }}
            .graph-filter-list {{
                max-height: none;
            }}
            .theme-toggle {{
                width: auto;
                flex: 1 1 auto;
            }}
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <div class="report-header-left">
            <button id="sidebar-toggle" class="header-icon-btn" type="button" onclick="toggleSidebar()"></button>
        </div>
        <h4>{name}</h4>
        <div class="report-header-actions">
            <button id="theme-toggle" class="theme-toggle" type="button" onclick="toggleTheme()"></button>
        </div>
    </div>
    <div class="report-container sidebar-collapsed">
        <div class="column filters-column">
            <div class="filters-panel">
                <div class="filters-title">Charts</div>
                <div id="visible-graphs-count" class="filters-subtitle"></div>
                <div class="graph-filter-actions">
                    <button class="filter-action-btn" type="button" onclick="setAllGraphsVisible(true)">Show All</button>
                    <button class="filter-action-btn" type="button" onclick="setAllGraphsVisible(false)">Hide All</button>
                </div>
                <div class="graph-filter-list">
                    {graph_filters_html}
                </div>
            </div>
        </div>
        <div class="column graphs-column">
            {html_graphs}
        </div>
        <div class="column right-column">
            {''.join(f'<div class="plot-container">{t}</div>' for t in html_tables)}
        </div>
    </div>
    <script>
        function cssVar(name) {{
            return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        }}

        var LIGHT_THEME_BUTTON = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6m0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8M8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0m0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13m8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5M3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8m10.657-5.657a.5.5 0 0 1 0 .707l-1.414 1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0m-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0m9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707M4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .708"/></svg><span>Light</span>';
        var DARK_THEME_BUTTON = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M6 .278a.77.77 0 0 1 .08.858 7.2 7.2 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277q.792-.001 1.533-.16a.79.79 0 0 1 .81.316.73.73 0 0 1-.031.893A8.35 8.35 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.75.75 0 0 1 6 .278"/></svg><span>Dark</span>';
        var COLLAPSE_SIDEBAR_BUTTON = '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16"><path d="M1.5 2A1.5 1.5 0 0 0 0 3.5v9A1.5 1.5 0 0 0 1.5 14h13a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 14.5 2zm0 1h2v10h-2a.5.5 0 0 1-.5-.5v-9a.5.5 0 0 1 .5-.5m8.854 5.354-2 2a.5.5 0 0 1-.708-.708L9.293 8 7.646 6.354a.5.5 0 1 1 .708-.708l2 2a.5.5 0 0 1 0 .708"/></svg>';
        var EXPAND_SIDEBAR_BUTTON = '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16"><path d="M1.5 2A1.5 1.5 0 0 0 0 3.5v9A1.5 1.5 0 0 0 1.5 14h13a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 14.5 2zm0 1h2v10h-2a.5.5 0 0 1-.5-.5v-9a.5.5 0 0 1 .5-.5m6.146 5.354 2-2a.5.5 0 1 1 .708.708L8.707 8l1.647 1.646a.5.5 0 0 1-.708.708l-2-2a.5.5 0 0 1 0-.708"/></svg>';
        var SIDEBAR_TRANSITION_MS = 240;

        function currentTheme() {{
            return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
        }}

        function tableStripeColors(rowCount) {{
            var evenColor = cssVar('--table-cell-even');
            var oddColor = cssVar('--table-cell-odd');
            return [Array.from({{ length: rowCount }}, function(_, index) {{
                return index % 2 === 0 ? evenColor : oddColor;
            }})];
        }}

        function themePalette() {{
            return {{
                plotPaperBg: cssVar('--plot-paper-bg'),
                plotBg: cssVar('--plot-bg'),
                plotFont: cssVar('--plot-font'),
                plotGrid: cssVar('--plot-grid'),
                plotAxis: cssVar('--plot-axis'),
                plotZero: cssVar('--plot-zero'),
                plotHoverBg: cssVar('--plot-hover-bg'),
                plotHoverFont: cssVar('--plot-hover-font'),
                shapeNeutral: cssVar('--shape-neutral'),
                tableHeaderFill: cssVar('--table-header-fill'),
                tableHeaderFont: cssVar('--table-header-font'),
                tableCellFont: cssVar('--table-cell-font'),
                tableLine: cssVar('--table-line')
            }};
        }}

        function themedAxis(axis, palette) {{
            var currentAxis = axis || {{}};
            var currentTitle = currentAxis.title || {{}};
            return Object.assign({{}}, currentAxis, {{
                automargin: true,
                gridcolor: palette.plotGrid,
                linecolor: palette.plotAxis,
                zerolinecolor: palette.plotZero,
                tickfont: Object.assign({{}}, currentAxis.tickfont || {{}}, {{ color: palette.plotFont }}),
                title: Object.assign({{}}, currentTitle, {{
                    font: Object.assign({{}}, currentTitle.font || {{}}, {{ color: palette.plotFont }})
                }})
            }});
        }}

        function themedShapes(shapes, palette) {{
            if (!Array.isArray(shapes)) {{
                return shapes;
            }}
            return shapes.map(function(shape) {{
                var currentLine = shape.line || {{}};
                var currentColor = String(currentLine.color || '').replace(/\\s+/g, '').toLowerCase();
                var isNeutral = !currentColor || ['black', '#000', '#000000', 'rgb(0,0,0)', 'rgba(0,0,0,1)'].indexOf(currentColor) !== -1;
                if (!isNeutral) {{
                    return shape;
                }}
                return Object.assign({{}}, shape, {{
                    line: Object.assign({{}}, currentLine, {{ color: palette.shapeNeutral }})
                }});
            }});
        }}

        function applyThemeToPlot(plot) {{
            if (!window.Plotly || !plot) {{
                return;
            }}

            var palette = themePalette();
            var nextData = (plot.data || []).map(function(trace) {{
                if (trace.type !== 'table') {{
                    return trace;
                }}
                var rowCount = 0;
                if (trace.cells && Array.isArray(trace.cells.values) && Array.isArray(trace.cells.values[0])) {{
                    rowCount = trace.cells.values[0].length;
                }}
                return Object.assign({{}}, trace, {{
                    header: Object.assign({{}}, trace.header || {{}}, {{
                        fill: Object.assign({{}}, (trace.header || {{}}).fill || {{}}, {{ color: palette.tableHeaderFill }}),
                        font: Object.assign({{}}, (trace.header || {{}}).font || {{}}, {{ color: palette.tableHeaderFont }}),
                        line: Object.assign({{}}, (trace.header || {{}}).line || {{}}, {{ color: palette.tableLine }})
                    }}),
                    cells: Object.assign({{}}, trace.cells || {{}}, {{
                        fill: Object.assign({{}}, (trace.cells || {{}}).fill || {{}}, {{ color: tableStripeColors(rowCount) }}),
                        font: Object.assign({{}}, (trace.cells || {{}}).font || {{}}, {{ color: palette.tableCellFont }}),
                        line: Object.assign({{}}, (trace.cells || {{}}).line || {{}}, {{ color: palette.tableLine }})
                    }})
                }});
            }});

            var currentTitle = plot.layout.title || {{}};
            var currentLegend = plot.layout.legend || {{}};
            var currentHover = plot.layout.hoverlabel || {{}};
            var nextLayout = Object.assign({{}}, plot.layout, {{
                paper_bgcolor: palette.plotPaperBg,
                plot_bgcolor: palette.plotBg,
                font: Object.assign({{}}, plot.layout.font || {{}}, {{ color: palette.plotFont }}),
                title: Object.assign({{}}, currentTitle, {{
                    font: Object.assign({{}}, currentTitle.font || {{}}, {{ color: palette.plotFont }})
                }}),
                legend: Object.assign({{}}, currentLegend, {{
                    bgcolor: 'rgba(0,0,0,0)',
                    font: Object.assign({{}}, currentLegend.font || {{}}, {{ color: palette.plotFont }})
                }}),
                hoverlabel: Object.assign({{}}, currentHover, {{
                    bgcolor: palette.plotHoverBg,
                    font: Object.assign({{}}, currentHover.font || {{}}, {{ color: palette.plotHoverFont }})
                }}),
                shapes: themedShapes(plot.layout.shapes, palette)
            }});

            var hasCartesianTrace = nextData.some(function(trace) {{
                return trace.type !== 'table';
            }});
            if (hasCartesianTrace) {{
                nextLayout.xaxis = themedAxis(plot.layout.xaxis, palette);
                nextLayout.yaxis = themedAxis(plot.layout.yaxis, palette);
            }}

            Plotly.react(plot, nextData, nextLayout, plot._context || {{ responsive: true }});
        }}

        function updateThemeToggleLabel() {{
            var toggle = document.getElementById('theme-toggle');
            if (!toggle) {{
                return;
            }}
            var darkActive = currentTheme() === 'dark';
            toggle.innerHTML = darkActive ? LIGHT_THEME_BUTTON : DARK_THEME_BUTTON;
            toggle.setAttribute('aria-label', darkActive ? 'Switch to light theme' : 'Switch to dark theme');
        }}

        function applyTheme(theme) {{
            document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
            try {{
                localStorage.setItem('stats-report-theme', document.documentElement.dataset.theme);
            }} catch (error) {{
                // Ignore storage errors and keep runtime theme only.
            }}
            updateThemeToggleLabel();
            if (window.Plotly) {{
                document.querySelectorAll('.js-plotly-plot').forEach(function(plot) {{
                    applyThemeToPlot(plot);
                }});
            }}
        }}

        function toggleTheme() {{
            applyTheme(currentTheme() === 'dark' ? 'light' : 'dark');
        }}

        function sidebarContainer() {{
            return document.querySelector('.report-container');
        }}

        function sidebarCollapsed() {{
            var container = sidebarContainer();
            return !!container && container.classList.contains('sidebar-collapsed');
        }}

        function updateSidebarToggleLabel() {{
            var toggle = document.getElementById('sidebar-toggle');
            if (!toggle) {{
                return;
            }}
            var collapsed = sidebarCollapsed();
            toggle.innerHTML = collapsed ? EXPAND_SIDEBAR_BUTTON : COLLAPSE_SIDEBAR_BUTTON;
            toggle.setAttribute('aria-label', collapsed ? 'Show charts sidebar' : 'Hide charts sidebar');
            toggle.setAttribute('title', collapsed ? 'Show charts sidebar' : 'Hide charts sidebar');
        }}

        function applySidebarCollapsed(collapsed) {{
            var container = sidebarContainer();
            if (!container) {{
                return;
            }}
            container.classList.toggle('sidebar-collapsed', !!collapsed);
            updateSidebarToggleLabel();
            schedulePlotResize();
        }}

        function toggleSidebar() {{
            applySidebarCollapsed(!sidebarCollapsed());
        }}

        function graphCards() {{
            return Array.from(document.querySelectorAll('.graph-card'));
        }}

        function graphFilterCheckboxes() {{
            return Array.from(document.querySelectorAll('.graph-filter-checkbox'));
        }}

        function resizeVisiblePlots() {{
            if (!window.Plotly) {{
                return;
            }}
            document.querySelectorAll('.graph-card:not(.graph-hidden) .js-plotly-plot').forEach(function(plot) {{
                Plotly.Plots.resize(plot);
            }});
        }}

        function schedulePlotResize() {{
            resizeVisiblePlots();
            if (window.requestAnimationFrame) {{
                window.requestAnimationFrame(resizeVisiblePlots);
            }}
            window.setTimeout(resizeVisiblePlots, SIDEBAR_TRANSITION_MS + 20);
        }}

        function updateVisibleGraphsCount() {{
            var cards = graphCards();
            var visible = cards.filter(function(card) {{
                return !card.classList.contains('graph-hidden');
            }}).length;
            var counter = document.getElementById('visible-graphs-count');
            if (counter) {{
                counter.textContent = visible + ' of ' + cards.length + ' charts visible';
            }}
        }}

        function setGraphVisibility(graphId, visible) {{
            var card = document.querySelector('.graph-card[data-graph-id="' + graphId + '"]');
            if (!card) {{
                return;
            }}
            card.classList.toggle('graph-hidden', !visible);
        }}

        function syncGraphVisibilityFromFilters() {{
            graphFilterCheckboxes().forEach(function(checkbox) {{
                setGraphVisibility(checkbox.dataset.graphId, checkbox.checked);
            }});
            updateVisibleGraphsCount();
            setTimeout(resizeVisiblePlots, 0);
        }}

        function setAllGraphsVisible(visible) {{
            graphFilterCheckboxes().forEach(function(checkbox) {{
                checkbox.checked = visible;
            }});
            syncGraphVisibilityFromFilters();
        }}

        function initGraphFilters() {{
            graphFilterCheckboxes().forEach(function(checkbox) {{
                checkbox.addEventListener('change', syncGraphVisibilityFromFilters);
            }});
            syncGraphVisibilityFromFilters();
        }}

        function fullscreenPlotHeight() {{
            return Math.max(window.innerHeight - 24, 320);
        }}

        function fullscreenPlotWidth(container) {{
            return Math.max(container.clientWidth - 4, 320);
        }}

        function restoredPlotWidth(container) {{
            var originalContainerWidth = Number(container.dataset.originalContainerWidth || 0);
            var originalLayoutWidth = Number(container.dataset.originalPlotWidth || 0);
            return Math.max(originalLayoutWidth || originalContainerWidth || container.clientWidth || 320, 320);
        }}

        function syncPlotSize(plotDiv, container) {{
            if (!plotDiv || !window.Plotly || !container) {{
                return;
            }}

            if (!container.dataset.originalPlotHeight) {{
                container.dataset.originalPlotHeight = String((plotDiv.layout && plotDiv.layout.height) || plotDiv.clientHeight || 550);
            }}
            if (!container.dataset.originalPlotWidth) {{
                container.dataset.originalPlotWidth = String((plotDiv.layout && plotDiv.layout.width) || '');
            }}
            if (!container.dataset.originalPlotAutosize) {{
                container.dataset.originalPlotAutosize = String(!plotDiv.layout || plotDiv.layout.autosize !== false);
            }}

            var targetHeight = container.classList.contains('fullscreen')
                ? fullscreenPlotHeight()
                : Number(container.dataset.originalPlotHeight);

            if (container.classList.contains('fullscreen')) {{
                Plotly.relayout(plotDiv, {{
                    autosize: false,
                    width: fullscreenPlotWidth(container),
                    height: targetHeight,
                }}).then(function() {{
                    Plotly.Plots.resize(plotDiv);
                }});
                return;
            }}

            Plotly.relayout(plotDiv, {{
                autosize: false,
                width: restoredPlotWidth(container),
                height: targetHeight,
            }}).then(function() {{
                return Plotly.relayout(plotDiv, {{
                    autosize: container.dataset.originalPlotAutosize !== 'false',
                }});
            }}).then(function() {{
                Plotly.Plots.resize(plotDiv);
            }});
        }}

        document.addEventListener("DOMContentLoaded", function() {{
            updateSidebarToggleLabel();
            updateThemeToggleLabel();
            applyTheme(currentTheme());
            initGraphFilters();
            schedulePlotResize();
        }})

        window.addEventListener('resize', function() {{
            var fullscreenContainer = document.querySelector('.plot-container.fullscreen');
            if (!fullscreenContainer) {{
                resizeVisiblePlots();
                return;
            }}
            syncPlotSize(fullscreenContainer.querySelector('.js-plotly-plot'), fullscreenContainer);
        }});

        function toggleFullscreen(btn) {{
            var container = btn.parentElement;
            var plotDiv = container.querySelector('.js-plotly-plot');
            var allBtns = document.querySelectorAll('.fullscreen-btn');
            if (!container.classList.contains('fullscreen')) {{
                if (!container.dataset.originalContainerWidth) {{
                    container.dataset.originalContainerWidth = String(container.clientWidth || 0);
                }}
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
                    syncPlotSize(plotDiv, container);
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


def _apply_initial_dark_theme(figures):
    palette = {
        "plot_paper_bg": "#111a2b",
        "plot_bg": "#111a2b",
        "plot_font": "#e5edf7",
        "plot_grid": "#2a3850",
        "plot_axis": "#70819a",
        "plot_zero": "#3d4d67",
        "plot_hover_bg": "#182235",
        "plot_hover_font": "#e5edf7",
        "shape_neutral": "#d1dae6",
        "table_header_fill": "#243147",
        "table_header_font": "#f8fbff",
        "table_cell_even": "#111a2b",
        "table_cell_odd": "#162238",
        "table_cell_font": "#e5edf7",
        "table_line": "#33425c",
    }

    for fig in figures:
        _apply_initial_dark_theme_to_figure(fig, palette)


def _apply_initial_dark_theme_to_figure(fig, palette):
    if fig is None:
        return

    current_title = fig.layout.title.to_plotly_json() if fig.layout.title else {}
    current_title_font = current_title.get("font", {})
    current_legend = fig.layout.legend.to_plotly_json() if fig.layout.legend else {}
    current_legend_font = current_legend.get("font", {})
    current_hover = fig.layout.hoverlabel.to_plotly_json() if fig.layout.hoverlabel else {}
    current_hover_font = current_hover.get("font", {})
    current_font = fig.layout.font.to_plotly_json() if fig.layout.font else {}

    layout_update = dict(
        paper_bgcolor=palette["plot_paper_bg"],
        plot_bgcolor=palette["plot_bg"],
        font={**current_font, "color": palette["plot_font"]},
        title={**current_title, "font": {**current_title_font, "color": palette["plot_font"]}},
        legend={**current_legend, "bgcolor": "rgba(0,0,0,0)", "font": {**current_legend_font, "color": palette["plot_font"]}},
        hoverlabel={**current_hover, "bgcolor": palette["plot_hover_bg"], "font": {**current_hover_font, "color": palette["plot_hover_font"]}},
    )

    if any(getattr(trace, "type", None) != "table" for trace in fig.data):
        if fig.layout.xaxis:
            layout_update["xaxis"] = _apply_initial_dark_theme_to_axis(fig.layout.xaxis.to_plotly_json(), palette)
        if fig.layout.yaxis:
            layout_update["yaxis"] = _apply_initial_dark_theme_to_axis(fig.layout.yaxis.to_plotly_json(), palette)

    shapes = []
    for shape in fig.layout.shapes or []:
        shape_json = shape.to_plotly_json()
        line = shape_json.get("line", {})
        current_color = str(line.get("color", "")).replace(" ", "").lower()
        if current_color in {"", "black", "#000", "#000000", "rgb(0,0,0)", "rgba(0,0,0,1)"}:
            shape_json["line"] = {**line, "color": palette["shape_neutral"]}
        shapes.append(shape_json)
    if shapes:
        layout_update["shapes"] = shapes

    fig.update_layout(**layout_update)

    for trace in fig.data:
        if getattr(trace, "type", None) != "table":
            continue

        header = trace.header.to_plotly_json() if trace.header else {}
        header_fill = header.get("fill", {})
        header_font = header.get("font", {})
        header_line = header.get("line", {})

        cells = trace.cells.to_plotly_json() if trace.cells else {}
        cells_fill = cells.get("fill", {})
        cells_font = cells.get("font", {})
        cells_line = cells.get("line", {})
        cells_values = cells.get("values", [])
        row_count = len(cells_values[0]) if cells_values else 0
        stripe_colors = [[palette["table_cell_even"] if i % 2 == 0 else palette["table_cell_odd"] for i in range(row_count)]]

        trace.update(
            header={
                **header,
                "fill": {**header_fill, "color": palette["table_header_fill"]},
                "font": {**header_font, "color": palette["table_header_font"]},
                "line": {**header_line, "color": palette["table_line"]},
            },
            cells={
                **cells,
                "fill": {**cells_fill, "color": stripe_colors},
                "font": {**cells_font, "color": palette["table_cell_font"]},
                "line": {**cells_line, "color": palette["table_line"]},
            },
        )


def _apply_initial_dark_theme_to_axis(axis, palette):
    title = axis.get("title", {}) if isinstance(axis, dict) else {}
    title_font = title.get("font", {}) if isinstance(title, dict) else {}
    tickfont = axis.get("tickfont", {}) if isinstance(axis, dict) else {}
    return {
        **axis,
        "automargin": True,
        "gridcolor": palette["plot_grid"],
        "linecolor": palette["plot_axis"],
        "zerolinecolor": palette["plot_zero"],
        "tickfont": {**tickfont, "color": palette["plot_font"]},
        "title": {**title, "font": {**title_font, "color": palette["plot_font"]}},
    }


#### Figure Creation
def create_fig(x, y, title, color="blue", fill=None, height=550, margin=None):
    if margin is None:
        margin = dict(l=50, r=10, t=30, b=10)
    fig = go.Figure(go.Scatter(x=x, y=y, fill=fill, line=dict(color=color)))
    # fig_equity.update_layout(title="📈 Equity Curve", margin=dict(l=50, r=10, t=50, b=10), template="plotly_dark")
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12))
    return fig

def create_bar(x, y, title, color="blue", height=550, margin=None):
    if margin is None:
        margin = dict(l=50, r=10, t=30, b=10)
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=color))
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12))
    return fig

def create_heatmap(z, x, y, title, colorscale="RdYlGn", zmid=0, height=550, margin=None, colorbar_title=None, hovertemplate=None):
    if margin is None:
        margin = dict(l=50, r=10, t=30, b=10)
    heatmap_kwargs = dict(
        z=z,
        x=x,
        y=y,
        colorscale=colorscale,
        zmid=zmid,
        hoverongaps=False,
        xgap=1,
        ygap=1,
    )
    if colorbar_title is not None:
        heatmap_kwargs["colorbar"] = dict(title=colorbar_title)
    if hovertemplate is not None:
        heatmap_kwargs["hovertemplate"] = hovertemplate
    fig = go.Figure(go.Heatmap(**heatmap_kwargs))
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12))
    return fig

def create_histogram(x, title, color="blue", height=550, margin=None, nbinsx=40):
    if margin is None:
        margin = dict(l=50, r=10, t=30, b=10)
    fig = go.Figure(go.Histogram(x=x, marker_color=color, nbinsx=nbinsx, opacity=0.85))
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12), bargap=0.05)
    return fig

def create_scatter(x, y, title, marker=None, height=550, margin=None, customdata=None, hovertemplate=None):
    if margin is None:
        margin = dict(l=50, r=10, t=30, b=10)
    if marker is None:
        marker = dict(color="blue", size=8, opacity=0.75)
    fig = go.Figure(go.Scatter(
        x=x,
        y=y,
        mode="markers",
        marker=marker,
        customdata=customdata,
        hovertemplate=hovertemplate,
    ))
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12))
    return fig

def create_multi_scatter(title, height=550, margin=None):
    if margin is None:
        margin = dict(l=50, r=10, t=30, b=10)
    fig = go.Figure()
    fig.update_layout(title=title, margin=margin, height=height, font=dict(size=12))
    return fig

def create_empty_fig(title, height=550, margin=None):
    if margin is None:
        margin = dict(l=50, r=10, t=30, b=10)
    fig = go.Figure()
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
    """Drawdown episodes from the preceding peak to recovery (or last bar)."""
    columns = ("start", "valley", "end", "days", "max drawdown",
               "99% max drawdown", "recovered")
    drawdown = drawdown.dropna()
    data = []
    start = None
    peak = 0
    for pos, value in enumerate(drawdown):
        if value < 0 and start is None:
            start = peak
        recovered = value >= 0
        if start is not None and (recovered or pos == len(drawdown) - 1):
            episode = drawdown.iloc[start:pos + 1]
            begin, end = episode.index[0], episode.index[-1]
            depths = -episode[episode < 0]
            data.append((begin, episode.idxmin(), end,
                         (end - begin).total_seconds() / 86400,
                         episode.min(), -depths.quantile(0.99), recovered))
            start = None
        if recovered:
            peak = pos
    return pd.DataFrame(data, columns=columns)

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
    iso_calendar = index.isocalendar()

    if "month" in period:
        return _group_returns(returns, index.month, compounded=compounded)

    if "quarter" in period:
        return _group_returns(returns, index.quarter, compounded=compounded)

    if period == "A" or any(x in period for x in ["year", "eoy", "yoy"]):
        return _group_returns(returns, index.year, compounded=compounded)

    if "week" in period:
        return _group_returns(returns, iso_calendar.week, compounded=compounded)

    if "eow" in period or period == "W":
        return _group_returns(returns, [iso_calendar.year, iso_calendar.week], compounded=compounded)

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
    if len(returns) == 0:
        return 0

    gross_returns = pd.Series(returns).fillna(0) + 1
    if np.any(gross_returns < 0):
        return np.nan
    if np.any(gross_returns == 0):
        return -1.0

    prod_value = np.prod(gross_returns)
    return prod_value ** (1 / len(returns)) - 1


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

def _time_under_water(drawdown):
    """Elapsed calendar days since the latest observed equity peak."""
    if drawdown.empty:
        return pd.Series(index=drawdown.index, dtype=float)
    peaks = pd.Series(drawdown.index, index=drawdown.index).where(drawdown >= 0)
    peaks.iloc[0] = drawdown.index[0]
    elapsed = (pd.Series(drawdown.index, index=drawdown.index) - peaks.ffill())
    return elapsed.dt.total_seconds().div(86400).where(drawdown < 0, 0.0)


def _rolling_drawdown_risk(equity, daily, window):
    """Risk over daily-return windows, retaining all intraday equity points.

    The preceding daily close anchors each window of ``window`` returns.
    Prefix windows start at the first equity observation.
    """
    ends = equity.index.searchsorted(daily.index + pd.DateOffset(days=1), side='left') - 1
    values = equity.to_numpy(dtype=float)
    records = []
    for day, end in enumerate(ends):
        start = ends[day - window] if day >= window else 0
        segment = values[start:end + 1]
        with np.errstate(divide='ignore', invalid='ignore'):
            drawdown = (segment / np.maximum.accumulate(segment) - 1) * 100
        records.append((np.min(drawdown), np.sqrt(np.mean(drawdown ** 2))))
    return pd.DataFrame(records, index=daily.index,
                        columns=['max_drawdown', 'ulcer_index'])

def _compute_trade_excursions(performance, trades_df):
    columns = ["mfe_pct", "mae_pct", "final_return_pct"]
    if trades_df.empty:
        return pd.DataFrame(columns=columns)
    strategy = getattr(performance, "strategy", None)
    executions = getattr(performance, '_trade_executions', {})
    price_frame_cache = {}
    records = []
    for trade in trades_df.itertuples(index=False):
        final_return_pct = trade.return_pct * 100
        fills = executions.get(trade.ref, ())
        notional = getattr(trade, 'entry_notional', np.nan)
        price_frame = _trade_price_frame(strategy, trade.data_name, price_frame_cache)
        if price_frame is None or not fills or not np.isfinite(notional) or notional <= 0:
            records.append((np.nan, np.nan, final_return_pct))
            continue
        mfe, mae = _execution_excursions(price_frame, fills)
        records.append((mfe / notional * 100, mae / notional * 100, final_return_pct))
    return pd.DataFrame(records, columns=columns)


def _execution_excursions(price_frame, fills):
    """Gross realized + unrealized PnL, respecting changes in exposure.

    OHLC cannot locate extrema relative to an intrabar fill. On such bars,
    use only the open, actual executions and close, without guessing a path.
    """
    times = pd.DatetimeIndex([num2date(fill.dt) for fill in fills])
    if not times.isin(price_frame.index).all():
        return np.nan, np.nan
    grouped = {}
    for dt, fill in zip(times, fills):
        grouped.setdefault(dt, []).append(fill)
    bars = price_frame.loc[times.min():times.max()]
    position = cost = realized = 0.0
    mult = fills[0].mult
    best = worst = 0.0

    def observe(price):
        nonlocal best, worst
        pnl = realized + position * (price - cost) * mult
        if np.isfinite(pnl):
            best, worst = max(best, pnl), min(worst, pnl)

    def execute(fill):
        nonlocal position, cost, realized, mult
        observe(fill.price)
        position, cost, realized, mult = (
            fill.position_size, fill.position_price, fill.pnl, fill.mult)
        observe(fill.price)

    for dt, bar in bars.iterrows():
        events = grouped.get(dt, ())
        for fill in events:
            if fill.timing == 'open':
                execute(fill)
        observe(bar['open'])
        if any(fill.timing not in ('open', 'close') for fill in events):
            for fill in events:
                if fill.timing not in ('open', 'close'):
                    execute(fill)
        else:
            observe(bar['high'])
            observe(bar['low'])
        observe(bar['close'])
        for fill in events:
            if fill.timing == 'close':
                execute(fill)
    return best, worst


def _trade_price_frame(strategy, data_name, cache):
    if data_name in cache:
        return cache[data_name]
    try:
        data = strategy.getdatabyname(data_name)
    except (KeyError, AttributeError):
        cache[data_name] = None
        return None

    # Native buffers preserve feed filters, mappings and UTC conversion. They
    # also support feeds without a pandas source, including Aurora's views.
    frame = _buffer_price_frame(data)
    if frame is None:
        frame = _source_price_frame(data)
    if frame is not None:
        for field in ('open', 'high', 'low'):
            frame[field] = frame[field].fillna(frame['close'])
        frame = frame.dropna(subset=['close']).sort_index()
    cache[data_name] = frame
    return frame


def _buffer_price_frame(data):
    lines = getattr(data, 'lines', None)
    if lines is None:
        return None
    size = data.buflen()
    if not size or size < len(data):  # exactbars may discard earlier bars
        return None
    values = {}
    for field in ('datetime', 'open', 'high', 'low', 'close'):
        line = getattr(lines, field, None)
        if line is None:
            return None
        array = getattr(line, 'array', None)
        if array is None:
            get_array = getattr(line, 'get_array', None)
            array = get_array() if get_array is not None else None
        if array is None or len(array) < size:
            return None
        values[field] = np.asarray(array, dtype=float)[:size]
    datetimes = values.pop('datetime')
    valid = np.isfinite(datetimes) & (datetimes >= 1)
    frame = pd.DataFrame({key: val[valid] for key, val in values.items()},
                         index=pd.DatetimeIndex([num2date(dt) for dt in datetimes[valid]]))
    mapping = getattr(data, '_colmapping', {})
    for field in ('open', 'high', 'low'):
        if field in mapping and mapping[field] is None:
            frame[field] = np.nan
    return frame if not frame.empty else None


def _source_price_frame(data):
    params = getattr(data, 'p', None)
    frame = next((source for source in (
        getattr(data, 'dataframe', None), getattr(params, 'dataframe', None),
        getattr(params, 'dataname', None)) if isinstance(source, pd.DataFrame)), None)
    if frame is None or frame.empty:
        return None
    mapping = dict(getattr(data, '_colmapping', {}))
    mapping.setdefault('datetime', getattr(data, 'p_datetime', getattr(params, 'datetime', None)))
    # Resolve numeric column positions before extracting the datetime column.
    columns = {field: _resolve_trade_frame_column(frame, mapping, field)
               for field in ('datetime', 'open', 'high', 'low', 'close')}
    if columns['close'] is None:
        return None
    datetimes = frame.index if columns['datetime'] is None else frame[columns['datetime']]
    index = pd.DatetimeIndex(pd.to_datetime(datetimes))
    if index.tz is None and getattr(data, '_tzinput', None) is not None:
        index = index.tz_localize(data._tzinput)
    if index.tz is not None:
        index = index.tz_convert('UTC').tz_localize(None)
    # Match the date-number precision used by execution timestamps.
    index = pd.DatetimeIndex([num2date(date2num(dt)) for dt in index.to_pydatetime()])
    return pd.DataFrame({field: pd.to_numeric(frame[column], errors='coerce').to_numpy()
                         if column is not None else np.full(len(frame), np.nan)
                         for field, column in columns.items() if field != 'datetime'}, index=index)


def _resolve_trade_frame_column(frame, mapping, field):
    if field in mapping and mapping[field] is None:
        return None
    candidate = mapping.get(field)
    if isinstance(candidate, (int, np.integer)):
        if 0 <= candidate < len(frame.columns):
            return frame.columns[candidate]
        candidate = None
    if candidate in frame.columns:
        return candidate
    for column in frame.columns:
        if str(column).lower() == str(candidate or field).lower():
            return column
    return None

def _window_max_drawdown_pct(equity_window):
    drawdown = ((equity_window / equity_window.cummax()) - 1) * 100
    return drawdown.min()

def _window_ulcer_index(equity_window):
    drawdown = ((equity_window / equity_window.cummax()) - 1) * 100
    return np.sqrt(np.mean(drawdown ** 2))

