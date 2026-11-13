from pandas import DataFrame

import backtrader_next as bt
from backtrader_next.utils.py3 import items, iteritems
from backtrader_next import Order
import numpy as np
import pandas as pd
from pandas import DataFrame as df
from numbers import Number
from typing import Union
import math


class Eq(bt.Analyzer):
    '''This analyzer calculates comprehensive trading system performance statistics
    including equity curves, drawdown analysis, returns, risk metrics, and trade statistics.

    Params:

      - ``fund`` (default: ``None``)

        If ``None`` the actual mode of the broker (fundmode - True/False) will
        be autodetected to decide if the returns are based on the total net
        asset value or on the fund value. See ``set_fundmode`` in the broker
        documentation

        Set it to ``True`` or ``False`` for a specific behavior

      - ``data`` (default: ``None``)

        Specific data feed whose position value is recorded. If ``None``,
        record the total portfolio or fund value. Position valuation follows
        the broker's ``get_value(datas=[feed])`` semantics.

      - ``cash`` (default: ``True``)

        Include the broker's free cash as a separate column in equity tracking.

    Methods:

      - ``compute_stats(risk_free_rate=0.0)``

        Returns a pandas Series with comprehensive trading statistics including:

        - Equity metrics: Start, End, Duration, Peak equity
        - Returns: Cumulative return %, Annualized return, CAGR
        - Risk metrics: Volatility (Ann.), Sharpe Ratio, Sortino Ratio, Smart Sharpe Ratio
        - Drawdown stats: Max Drawdown %, Avg Drawdown %, Drawdown Duration
        - Trade statistics: Win Rate, Best/Worst/Avg Trade, # of Trades
        - Performance ratios: Calmar Ratio, VWR Ratio, Profit Factor, Profit Factor [eq], SQN, Kelly Criterion

        CAGR uses elapsed calendar time on a fixed 365-day year basis,
        independently of the observation frequency or trading calendar.
        Daily-return statistics use their separate annualization factor.

        Drawdowns, episode durations, peaks and Ulcer Index use every recorded
        equity point, including intraday observations. Return and volatility
        annualization uses daily returns. Recovery factor uses the full-period
        equity change and the maximum drawdown of the full curve.

        Without drawdowns, drawdown magnitude and duration are zero,
        and Drawdown Peak is NaT. Ratios requiring a nonzero drawdown remain NaN.

      - ``gen_eq()``

        Returns equity curve as a pandas DataFrame with datetime index.

      - ``gen_eq_dd()``

        Returns equity and drawdown data as a pandas DataFrame.

      - ``gen_trades(data_name=None, pct=False)``

        Returns trade-level statistics as a pandas DataFrame.
        Gross return_pct and net return_net_pct use the sum of all entry
        notionals, including additions and the contract multiplier. Both are
        fractions unless pct=True. A zero entry_notional gives NaN returns.
        priceopen/priceclose are volume-weighted execution prices; size is
        the peak position quantity with its direction sign.

      - ``gen_orders(data_name=None)``

        Returns order execution history as a pandas DataFrame. Each row holds
        a new fill's price and signed quantity, not cumulative order totals.
        Partial fills of the same order share o_ref.

    Generated frames are cached snapshots. New equity observations, closed
    trades and fills invalidate the corresponding cache, so reading results
    during run() does not freeze the final report. Execution dates use the
    broker's actual fill times, including fills at a previous bar's close.
    '''

    params = (
        ('fund', None),
        ('data', None),
        ('cash', True),
    )


    def start(self):
        #super(Eq, self).start()
        if self.p.fund is None:
            self._fundmode = self.strategy.broker.fundmode
        else:
            self._fundmode = self.p.fund

        self.rets_header = ['Datetime', 'value'] + ['cash'] * self.p.cash
        self.trades_header = ['ref', 'data_name', 'tradeid', 'commission', 'pnl', 'pnlcomm', 'return_pct',
                            'dateopen', 'dateclose','size','barlen','priceopen','priceclose',
                            'entry_notional', 'return_net_pct']
        self.orders_header = ['o_ref','data_name', 'o_datetime', 'o_ordtype', 'o_price', 'o_size']

        self.returns = None
        self.trades = list()
        self.orders = list()
        self.eq_df = None
        self.trades_df = None
        self.orders_df = None
        self._trade_executions = {}

    def notify_trade(self, trade):
        if trade.isclosed:
            self._trade_executions[trade.ref] = tuple(trade._execution_history)
            size = trade.peak_size * (1 if trade.long else -1)
            self.trades.append([trade.ref, trade.data._name, trade.tradeid, trade.commission,
                                trade.pnl, trade.pnlcomm, trade.return_pct, trade.open_datetime(),
                                trade.close_datetime(), size, trade.barlen, trade.priceopen,
                                trade.priceclose, trade.entry_notional, trade.return_net_pct])
            self.trades_df = None


    def notify_fund(self, cash, value, fundvalue, shares):
        self._cash = cash
        if not self._fundmode:
            self._value = value
        else:
            self._value = fundvalue

    def next(self):
        pvals = []
        if self.p.data is None:
            pvals.append(self._value)
        else:
            # A feed is itself iterable; keep it inside a broker data selection.
            datas = self.p.data if isinstance(self.p.data, (list, tuple)) else [self.p.data]
            pvals.append(self.strategy.broker.get_value(datas=datas))

        if self.p.cash:
            pvals.append(self._cash)

        # Use raw float datetime key (avoid num2date per bar).
        # _dt0 is set by AuroraStrategy._oncepost; fall back for non-Aurora.
        dt_key = getattr(self.strategy, '_dt0', None)
        if dt_key is None:
            dt_key = self.strategy.datetime.datetime()
        self.rets[dt_key] = pvals
        self.eq_df = None

    def notify_order(self, order):
        if order.status not in [Order.Partial, Order.Completed]:
            return  # It's not an execution
        for fill in order.executed.iterpending():
            if fill is None:
                break
            self.orders.append([order.ref, order.data._name, order.data.num2date(fill.dt),
                                order.ordtype, fill.price, fill.size])
            self.orders_df = None

    def gen_eq(self) -> 'DataFrame':
        if self.eq_df is not None:
            return self.eq_df
        if self.rets and all(isinstance(key, (int, float)) for key in self.rets):
            from backtrader_next.utils.arraydates import num2datetime_array
            times = num2datetime_array(np.fromiter(self.rets, dtype=np.float64))
            self.eq_df = df([value[-2:] for value in self.rets.values()],
                            index=pd.DatetimeIndex(times, name=self.rets_header[0]),
                            columns=self.rets_header[1:])
            return self.eq_df
        from backtrader_next.utils.dateintern import num2date as _n2d
        # Keys in self.rets may be float (Aurora fast-path) or datetime (fallback)
        def _to_dt(k):
            return _n2d(k) if isinstance(k, (int, float)) else k
        data = [[_to_dt(k)] + v[-2:] for k, v in iteritems(self.rets)]
        eq_df = df.from_records(data, index=self.rets_header[0], columns=self.rets_header)
        eq_df.index = pd.to_datetime(eq_df.index)
        #TODO eq_df.index = eq_df.index.tz_localize('UTC')
        self.eq_df = eq_df
        return eq_df

    def gen_eq_dd(self) -> 'DataFrame':
        eq_df = self.gen_eq()

        equity = eq_df['value']
        max_equity = equity.cummax()
        dd = (1- equity / max_equity) * 100

        equity_df = pd.DataFrame({
            'Equity': equity,
            'DrawdownPct': dd
        }, index=eq_df.index)

        return equity_df

    def gen_trades(self, data_name=None, pct=False) -> 'DataFrame':
        if self.trades_df is None:
            self.trades_df = df.from_records(self.trades, columns=self.trades_header)
        if data_name is None:
            rdf = self.trades_df.copy()
        else:
            rdf = self.trades_df[self.trades_df['data_name'] == data_name].copy()
        if pct:
            rdf[['return_pct', 'return_net_pct']] = rdf[['return_pct', 'return_net_pct']] * 100
        return rdf

    def gen_orders(self, data_name=None) -> 'DataFrame':
        if self.orders_df is None:
            self.orders_df = df.from_records(self.orders, columns=self.orders_header)
        if data_name is None:
            return self.orders_df
        else:
            return self.orders_df[self.orders_df['data_name'] == data_name]

    def compute_stats(self,
            risk_free_rate: float = 0.0,
        ) -> pd.Series:
        assert -1 < risk_free_rate < 1

        eq_df = self.gen_eq()
        trades_df = self.gen_trades()
        index = eq_df.index
        equity = eq_df['value'].to_numpy()

        gmean_day_return: float = 0
        day_returns = np.array(np.nan)
        annual_trading_days = np.nan

        day_eq = eq_df['value'].resample('D').last().dropna()
        day_returns = day_eq.pct_change().dropna()
        gmean_day_return = geometric_mean(day_returns)
        annual_trading_days = float(365 if index.dayofweek.to_series().between(5, 6).mean() > 2 / 7 * .6
                                        else 252)

        # Use the same observation frequency as gen_eq_dd(), retaining intraday risk.
        dd = (1 - eq_df['value'] / eq_df['value'].cummax()) * 100
        dd_dur, dd_peaks = compute_drawdown_duration_peaks(dd)

        trades_df['Duration'] = trades_df['dateclose'] - trades_df['dateopen']
        commissions = sum(trades_df['commission'].to_numpy())

        pl = trades_df['pnlcomm']
        returns_pct = trades_df['return_pct']
        durations = trades_df['Duration']

        def _round_timedelta(value, _period=_data_period(index)):
            if not isinstance(value, pd.Timedelta):
                return value
            resolution = getattr(_period, 'resolution_string', None) or _period.resolution
            return value.ceil(resolution)

        s = pd.Series(dtype=object)
        s.loc['Start'] = index[0]
        s.loc['End'] = index[-1]
        s.loc['Duration'] = s.End - s.Start

        s.loc['Equity Start [$]'] = equity[0]
        s.loc['Equity Final [$]'] = round(equity[-1], 4)
        s.loc['Equity Peak [$]'] = round(equity.max(), 4)
        s.loc['Commissions [$]'] = round(commissions, 4)
        s.loc['Cum Return [%]'] = round((equity[-1] - equity[0]) / equity[0] * 100, 4)
        # c = ohlc_data.Close.values
        # s.loc['Buy & Hold Return [%]'] = (c[-1] - c[0]) / c[0] * 100  # long-only return


        # Annualized return and risk metrics are computed based on the (mostly correct)
        # assumption that the returns are compounded. See: https://dx.doi.org/10.2139/ssrn.3054517
        # Our annualized return matches `empyrical.annual_return(day_returns)` whereas
        # our risk doesn't; they use the simpler approach below.
        annualized_return = (1 + gmean_day_return) ** annual_trading_days - 1
        s.loc['Return (Ann.) [%]'] = round(annualized_return * 100, 4)
        volatility = day_returns.std(ddof=1) * np.sqrt(annual_trading_days) * 100
        s.loc['Volatility (Ann.) [%]'] = round(volatility, 4)

        # CAGR uses elapsed calendar time on a fixed 365-day year basis.
        elapsed_days = (index[-1] - index[0]).total_seconds() / 86400
        num_years = elapsed_days / 365.0
        equity_ratio = equity[-1] / equity[0] if equity[0] != 0 else np.nan
        if num_years > 0:
            if equity_ratio == 0:
                cagr_value = -1.0
            elif equity_ratio < 0:
                cagr_value = np.nan
            else:
                cagr_value = equity_ratio ** (1 / num_years) - 1
        else:
            cagr_value = 0
        s.loc['CAGR [%]'] = round(cagr_value * 100, 4)

        # Sharpe Ratio using arithmetic mean of returns to align with standard definition.
        # See: https://en.wikipedia.org/wiki/Sharpe_ratio
        mean_daily_return = day_returns.mean()
        annualized_mean_return = mean_daily_return * annual_trading_days
        sharpe = (annualized_mean_return * 100 - risk_free_rate * 100) / (
                volatility if volatility != 0 else np.nan)
        s.loc['Sharpe Ratio'] = round(sharpe, 4)

        # Smart Sharpe Ratio
        skew = day_returns.skew()
        kurt = day_returns.kurt()  # Excess kurtosis
        s.loc['Skew'] = round(skew, 4)
        s.loc['Kurtosis'] = round(kurt, 4)
        # Smart Sharpe Ratio is a modification of the Sharpe Ratio that accounts for skewness
        # and kurtosis of the returns distribution. It is defined as:
        # Smart Sharpe Ratio = Sharpe Ratio * (1 + (Skewness / 6) * Sharpe Ratio - (Kurtosis / 24) * (Sharpe Ratio ** 2))
        # See: https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/smart-sharpe-ratio
        smart_sharpe = sharpe * (1 + (skew / 6) * sharpe - (kurt / 24) * (sharpe ** 2))
        s.loc['Smart Sharpe Ratio'] = round(smart_sharpe, 4)

        # Our Sortino mismatches `empyrical.sortino_ratio()` because they use arithmetic mean return
        risk_free_rate_daily = (1 + risk_free_rate) ** (1 / annual_trading_days) - 1
        _downside_returns = (day_returns - risk_free_rate_daily).clip(-np.inf, 0)
        _downside_std = np.sqrt(np.mean(_downside_returns ** 2))
        sortino_ratio = ((mean_daily_return - risk_free_rate_daily) / _downside_std) * np.sqrt(
                annual_trading_days) if _downside_std != 0 else np.nan
        s.loc['Sortino Ratio'] = round(sortino_ratio, 4) if not np.isnan(sortino_ratio) else np.nan

        # s.loc['VWR Ratio'] = calc_vwr(eq_days=equity_df['Equity'].resample('D').last().dropna().to_numpy())
        s.loc['VWR Ratio'] = round(calc_vwr(eq_days=day_eq.to_numpy(), annual_trading_days=annual_trading_days), 4)
        max_dd = -np.nan_to_num(dd.max())
        s.loc['Calmar Ratio'] = round((annualized_return * 100) / abs(max_dd), 4) if max_dd != 0 else np.nan

        ulcer_index = float(np.sqrt(np.mean(dd ** 2)))
        s.loc['Ulcer Index'] = round(ulcer_index, 4)
        s.loc['UPI'] = round((annualized_return * 100) / ulcer_index, 4) if ulcer_index != 0 else np.nan

        total_return = equity_ratio - 1
        s.loc['Recovery factor [%]'] = round(total_return / abs(max_dd) * 100, 4) if abs(max_dd) != 0 else np.nan

        s.loc['Max. Drawdown [%]'] = round(max_dd, 4)
        dd_dur = dd_dur.dropna()
        dd_peaks = dd_peaks.dropna()
        s.loc['Avg. Drawdown [%]'] = round(-dd_peaks.mean(), 4) if not dd_peaks.empty else 0.0
        dd_dur_max = dd_dur.max() if not dd_dur.empty else pd.Timedelta(0)
        s.loc['Max. Drawdown Duration'] = _round_timedelta(dd_dur_max)
        s.loc['Max. Drawdown Duration [D]'] = round(dd_dur_max.total_seconds() / 86400, 4)
        dd_dur_mean = dd_dur.mean() if not dd_dur.empty else pd.Timedelta(0)
        s.loc['Avg. Drawdown Duration'] = _round_timedelta(dd_dur_mean)
        s.loc['Avg. Drawdown Duration [D]'] = round(dd_dur_mean.total_seconds() / 86400, 4)
        s.loc['Drawdown Peak'] = dd.idxmax() if max_dd != 0 else pd.NaT
        s.loc['# Trades'] = n_trades = len(trades_df)
        win_rate = np.nan if not n_trades else (pl > 0).mean()
        s.loc['Win Rate [%]'] = round(win_rate * 100, 4)
        s.loc['Best Trade [%]'] = round(returns_pct.max() * 100, 4)
        s.loc['Worst Trade [%]'] = round(returns_pct.min() * 100, 4)
        avg_trade_return = returns_pct.mean()
        s.loc['Avg. Trade [%]'] = round(avg_trade_return * 100, 4)
        mean_return = geometric_mean(returns_pct.dropna())
        s.loc['Avg. Geometric Trade [%]'] = round(mean_return * 100, 4)
        s.loc['Max. Trade Duration'] = _round_timedelta(durations.max())
        s.loc['Avg. Trade Duration'] = _round_timedelta(durations.mean())

        gross_profit_eq = day_returns[day_returns > 0].sum()
        gross_loss_eq = abs(day_returns[day_returns < 0].sum())
        s.loc['Profit Factor [eq]'] = round(gross_profit_eq / gross_loss_eq, 4) if gross_loss_eq != 0 else np.nan

        gross_profit_trades = pl[pl > 0].sum()
        gross_loss_trades = abs(pl[pl < 0].sum())
        s.loc['Profit Factor'] = round(gross_profit_trades / gross_loss_trades, 4) if gross_loss_trades != 0 else np.nan
        s.loc['Expectancy [%]'] = round(returns_pct.mean() * 100, 4)
        pl_std = pl.std(ddof=1)
        if n_trades <= 1:
            s.loc['SQN'] = 0
        else:
            s.loc['SQN'] = round(np.sqrt(n_trades) * pl.mean() / pl_std, 4) if pl_std != 0 else np.nan

        avg_win = pl[pl > 0].mean()
        avg_loss = -pl[pl < 0].mean()
        if pd.notna(avg_win) and pd.notna(avg_loss) and avg_loss > 0:
            b = avg_win / abs(avg_loss)
            s.loc['Kelly Criterion [%]'] = round((win_rate - (1 - win_rate) / b) * 100, 4)
        else:
            s.loc['Kelly Criterion [%]'] = np.nan

        return s


def compute_drawdown_duration_peaks(dd: pd.Series):
    empty_durations = pd.Series(pd.NaT, index=dd.index, dtype='timedelta64[ns]')
    empty_peaks = pd.Series(np.nan, index=dd.index, dtype=float)
    if dd.empty:
        return empty_durations, empty_peaks

    iloc = np.unique(np.r_[(dd == 0).values.nonzero()[0], len(dd) - 1])
    iloc = pd.Series(iloc, index=dd.index[iloc])
    df = iloc.to_frame('iloc').assign(prev=iloc.shift())
    recovered = df['iloc'] > df['prev'] + 1
    # Include an unfinished episode even if only the final bar is below its peak.
    unfinished = (df['iloc'] == len(dd) - 1) & df['prev'].notna() & (dd.iloc[-1] > 0)
    df = df[recovered | unfinished].astype(int)

    # Keep duration and percentage types distinct when no episodes exist.
    if not len(df):
        return empty_durations, empty_peaks

    df['duration'] = df['iloc'].map(dd.index.__getitem__) - df['prev'].map(dd.index.__getitem__)
    df['peak_dd'] = df.apply(lambda row: dd.iloc[row['prev']:row['iloc'] + 1].max(), axis=1)

    df = df.reindex(dd.index)
    return df['duration'], df['peak_dd']


def remove_outliers(returns, quantile=0.95):
    """Returns series of returns without the outliers"""
    return returns[returns < returns.quantile(quantile)]


def geometric_mean(returns: pd.Series) -> float:
    returns = returns.fillna(0) + 1
    if np.any(returns < 0):
        return np.nan
    if np.any(returns == 0):
        return -1.0
    return np.exp(np.log(returns).sum() / (len(returns) or np.nan)) - 1


#    calc VariabilityWeightedReturn
#    See:
#      - https://www.crystalbull.com/sharpe-ratio-better-with-log-returns/
def calc_vwr(eq_days: np.array, sdev_max=0.2, tau=2.0, annual_trading_days=252.0) -> float:
    eq = eq_days #.to_numpy()
    eq_0 = np.roll(eq, 1)  # shift()

    # Calculate nlrtot and rtot
    nlrtot = eq[-1] / eq[0] if eq[0] != 0 else float('-inf')
    if nlrtot <= 0.0:
        return float('-inf')
    rtot = math.log(nlrtot)

    # Calculate ravg
    ravg = rtot / len(eq)
    rnorm = math.expm1(ravg * annual_trading_days)
    rnorm100 = rnorm * 100.0

    # Calculate expected returns
    n_vals = np.arange(len(eq))
    expected = eq_0 * np.exp(ravg * n_vals)
    dts = np.where(expected != 0, eq / expected - 1.0, 0.0)

    # Calculate standard deviation of the returns
    sdev_p = np.std(dts[1:], ddof=1)  # Use ddof=1 to get sample standard deviation
    vwr = rnorm100 * (1.0 - (sdev_p / sdev_max) ** tau)
    return vwr

def _data_period(index) -> Union[pd.Timedelta, Number]:
    """Return data index period as pd.Timedelta"""
    values = pd.Series(index[-100:])
    return values.diff().dropna().median()
