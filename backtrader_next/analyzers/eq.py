from pandas import DataFrame

import backtrader_next as bt
from backtrader_next.utils.py3 import items, iteritems
from backtrader_next import Order
import numpy as np
import pandas as pd
from pandas import DataFrame as df
from numbers import Number
from typing import Dict, List, Optional, Sequence, Union, cast
import math
# from math import copysign


class Eq(bt.Analyzer):
    '''This analyzer calculates trading system drawdowns stats such as drawdown
    values in %s and in dollars, max drawdown in %s and in dollars, drawdown
    length and drawdown max length

    Params:

      - ``fund`` (default: ``None``)

        If ``None`` the actual mode of the broker (fundmode - True/False) will
        be autodetected to decide if the returns are based on the total net
        asset value or on the fund value. See ``set_fundmode`` in the broker
        documentation

        Set it to ``True`` or ``False`` for a specific behavior

    Methods:

      - ``get_analysis``

        Returns a dictionary (with . notation support and subdctionaries) with
        drawdown stats as values, the following keys/attributes are available:

        - ``drawdown`` - drawdown value in 0.xx %
        - ``moneydown`` - drawdown value in monetary units
        - ``len`` - drawdown length

        - ``max.drawdown`` - max drawdown value in 0.xx %
        - ``max.moneydown`` - max drawdown value in monetary units
        - ``max.len`` - max drawdown length
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
                            'dateopen', 'dateclose','size','barlen','priceopen','priceclose']
        self.orders_header = ['o_ref','data_name', 'o_datetime', 'o_ordtype', 'o_price', 'o_size']

        self.returns = None
        self.trades = list()
        self.orders = list()
        self.eq_df = None
        self.trades_df = None
        self.orders_df = None

    def notify_trade(self, trade):
        if trade.justopened:
            pass

        elif trade.status == trade.Closed:
            #self.trades_op.append([])  remove
            return_pct = (1 if trade.long else -1) * (trade.data.open[0] / trade.price - 1)
            size = (1 if trade.long else -1)
            self.trades.append([trade.ref, trade.data._name, trade.tradeid, trade.commission,
                                trade.pnl, trade.pnlcomm, return_pct, trade.open_datetime(),
                                trade.close_datetime(), size, trade.barlen, trade.price, trade.data.open[0]])


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
            pvals.append(self.strategy.broker.get_value(self.p.data))

        if self.p.cash:
            pvals.append(self._cash)
            # pvals.append(self.strategy.broker.get_cash())

        self.rets[self.strategy.datetime.datetime()] = pvals

    def notify_order(self, order):
        if order.status not in [Order.Partial, Order.Completed]:
            return  # It's not an execution
        self.orders.append([order.ref, order.data._name, order.data.datetime.datetime(),
                            order.ordtype, order.executed.price, order.executed.size])

    def gen_eq(self) -> 'DataFrame':
        if self.eq_df is not None:
            return self.eq_df
        data = [[k] + v[-2:] for k, v in iteritems(self.rets)]
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
            # self.trades_df = df.from_records(self.trades, index=self.trades_header[0], columns=self.trades_header)
        if data_name is None:
            rdf = self.trades_df.copy()
        else:
            rdf = self.trades_df[self.trades_df['data_name'] == data_name].copy()
        if pct:
            rdf['return_pct'] = rdf['return_pct'] * 100
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
        day_returns = eq_df['value'].resample('D').last().dropna().pct_change().dropna()
        gmean_day_return = geometric_mean(day_returns)
        annual_trading_days = float(365 if index.dayofweek.to_series().between(5, 6).mean() > 2 / 7 * .6
                                        else 252)
        num_years = (eq_df.index[-1] - eq_df.index[0]).days / annual_trading_days

        dd_df = (1 - eq_df['value'] / eq_df['value'].cummax()) * 100
        dd_dur, dd_peaks = compute_drawdown_duration_peaks(dd_df)

        trades_df['Duration'] = trades_df['dateclose'] - trades_df['dateopen']
        commissions = sum(trades_df['commission'].to_numpy())

        pl = trades_df['pnlcomm']
        returns_pct = trades_df['return_pct']
        durations = trades_df['Duration']
        ##TODO ????? new ver#   df['returns'] = df['equity'].pct_change() * 100

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
        s.loc['Equity Final [$]'] = equity[-1]
        s.loc['Equity Peak [$]'] = equity.max()
        s.loc['Commissions [$]'] = commissions
        s.loc['Cum Return [%]'] = ((equity[-1] - equity[0]) / equity[0] * 100).round(4)
        # c = ohlc_data.Close.values
        # s.loc['Buy & Hold Return [%]'] = (c[-1] - c[0]) / c[0] * 100  # long-only return


        # Annualized return and risk metrics are computed based on the (mostly correct)
        # assumption that the returns are compounded. See: https://dx.doi.org/10.2139/ssrn.3054517
        # Our annualized return matches `empyrical.annual_return(day_returns)` whereas
        # our risk doesn't; they use the simpler approach below.
        annualized_return = (1 + gmean_day_return) ** annual_trading_days - 1
        s.loc['Return (Ann.) [%]'] = (annualized_return * 100).round(4)
        # s.loc['Risk (Ann.) [%]'] = day_returns.std(ddof=1) * np.sqrt(annual_trading_days) * 100
        s.loc['Volatility (Ann.) [%]'] = volatility = (day_returns.std(ddof=1) * np.sqrt(annual_trading_days) * 100).round(4)

        # CAGR from quantstats
        # _total = day_returns.add(1).prod() - 1
        # _years = (day_returns.index[-1] - day_returns.index[0]).days / annual_trading_days
        # _res = abs(_total + 1.0) ** (1.0 / _years) - 1
        s.loc['CAGR [%]'] = (((equity[-1]/equity[0]) ** (1/num_years) - 1) * 100).round(4)

        # Sharpe Ratio using arithmetic mean of returns to align with standard definition.
        # See: https://en.wikipedia.org/wiki/Sharpe_ratio
        mean_daily_return = day_returns.mean()
        annualized_mean_return = mean_daily_return * annual_trading_days
        s.loc['Sharpe Ratio'] = sharpe = ((annualized_mean_return * 100 - risk_free_rate * 100) / (
                volatility if volatility != 0 else np.nan)).round(4)

        # Smart Sharpe Ratio
        skew = day_returns.skew()
        kurt = day_returns.kurt()  # Excess kurtosis
        s.loc['Skew'] = skew.round(4)
        s.loc['Kurtosis'] = kurt.round(4)
        # Smart Sharpe Ratio is a modification of the Sharpe Ratio that accounts for skewness
        # and kurtosis of the returns distribution. It is defined as:
        # Smart Sharpe Ratio = Sharpe Ratio * (1 + (Skewness / 6) * Sharpe Ratio - (Kurtosis / 24) * (Sharpe Ratio ** 2))
        # See: https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/smart-sharpe-ratio
        s.loc['Smart Sharpe Ratio'] = (sharpe * (1 + (skew / 6) * sharpe - (kurt / 24) * (sharpe ** 2))).round(4)

        # Our Sortino mismatches `empyrical.sortino_ratio()` because they use arithmetic mean return
        _downside_returns = day_returns.clip(-np.inf, 0)
        _downside_std = np.sqrt(np.mean(_downside_returns ** 2))
        sortino_ratio = (annualized_mean_return - risk_free_rate) / (
                _downside_std * np.sqrt(annual_trading_days)) if _downside_std != 0 else np.nan
        s.loc['Sortino Ratio'] = round(sortino_ratio, 4) if not np.isnan(sortino_ratio) else np.nan

        # s.loc['VWR Ratio'] = calc_vwr(eq_days=equity_df['Equity'].resample('D').last().dropna().to_numpy())
        s.loc['VWR Ratio'] = (calc_vwr(eq_days=day_eq.to_numpy())).round(4)
        max_dd = -np.nan_to_num(dd_df.max())
        s.loc['Calmar Ratio'] = round((annualized_return * 100) / abs(max_dd), 4) if max_dd != 0 else np.nan

        # total_return = (day_returns.add(1)).prod() - 1 # Wrong calc
        total_return = day_returns.sum()
        s.loc['Recovery factor [%]'] = round(abs(total_return) / abs(max_dd) * 100, 4) if abs(max_dd) != 0 else np.nan

        s.loc['Max. Drawdown [%]'] = round(max_dd, 4)
        s.loc['Avg. Drawdown [%]'] = round(-dd_peaks.mean(), 4)
        s.loc['Max. Drawdown Duration'] = _round_timedelta(dd_dur.max())
        s.loc['Avg. Drawdown Duration'] = _round_timedelta(dd_dur.mean())
        s.loc['Drawdown Peak'] = dd_df.idxmax()
        s.loc['# Trades'] = n_trades = len(trades_df)
        win_rate = np.nan if not n_trades else (pl > 0).mean()
        s.loc['Win Rate [%]'] = round(win_rate * 100, 4)
        s.loc['Best Trade [%]'] = round(returns_pct.max() * 100, 4)
        s.loc['Worst Trade [%]'] = round(returns_pct.min() * 100, 4)
        mean_return = geometric_mean(returns_pct)
        s.loc['Avg. Trade [%]'] = round(mean_return * 100, 4)
        s.loc['Max. Trade Duration'] = _round_timedelta(durations.max())
        s.loc['Avg. Trade Duration'] = _round_timedelta(durations.mean())

        gross_profit = day_returns[day_returns > 0].sum()
        gross_loss = abs(day_returns[day_returns < 0].sum())
        s.loc['Profit Factor'] = round(gross_profit / gross_loss, 4) if gross_loss != 0 else np.nan
        s.loc['Expectancy [%]'] = round(day_returns.mean() * 100, 4)
        s.loc['SQN'] = round(np.sqrt(n_trades) * pl.mean() / pl.std(), 4) if pl.std() != 0 else np.nan

        avg_win = pl[pl > 0].mean()
        avg_loss = -pl[pl < 0].mean()
        if avg_win is not np.nan and avg_loss > 0:
            b = avg_win / abs(avg_loss)
            s.loc['Kelly Criterion [%]'] = round((win_rate - (1 - win_rate) / b) * 100, 4)
        else:
            s.loc['Kelly Criterion [%]'] = np.nan

        # s.loc['_strategy'] = strategy_instance
        # s.loc['_equity_curve'] = equity_df
        # s.loc['_trades'] = trades_df
        #
        return s


def compute_drawdown_duration_peaks(dd: pd.Series):
    iloc = np.unique(np.r_[(dd == 0).values.nonzero()[0], len(dd) - 1])
    iloc = pd.Series(iloc, index=dd.index[iloc])
    df = iloc.to_frame('iloc').assign(prev=iloc.shift())
    df = df[df['iloc'] > df['prev'] + 1].astype(int)

    # If no drawdown since no trade, avoid below for pandas sake and return nan series
    if not len(df):
        return (dd.replace(0, np.nan),) * 2

    df['duration'] = df['iloc'].map(dd.index.__getitem__) - df['prev'].map(dd.index.__getitem__)
    df['peak_dd'] = df.apply(lambda row: dd.iloc[row['prev']:row['iloc'] + 1].max(), axis=1)

    df = df.reindex(dd.index)
    return df['duration'], df['peak_dd']


def remove_outliers(returns, quantile=0.95):
    """Returns series of returns without the outliers"""
    return returns[returns < returns.quantile(quantile)]


def geometric_mean(returns: pd.Series) -> float:
    returns = returns.fillna(0) + 1
    if np.any(returns <= 0):
        return 0
    return np.exp(np.log(returns).sum() / (len(returns) or np.nan)) - 1


def calc_vwr0(eq_days: np.array, sdev_max=2.0, tau=0.20) -> float:
    eq = eq_days #.to_numpy()
    eq_0 = eq_days.shift().to_numpy()

    try:
        nlrtot = eq[-1] / eq[0]
    except ZeroDivisionError:
        rtot = float('-inf')
    else:
        if nlrtot <= 0.0:
            rtot = float('-inf')
        else:
            rtot = math.log(nlrtot)

    ravg = rtot / len(eq)
    rnorm = math.expm1(ravg * 252)
    rnorm100 = rnorm * 100.0

    dts = []
    for n, zip_data in enumerate(zip(eq_0, eq), 0):
        eq0, eq1 = zip_data
        if (n > 0):
            _v = (eq0 * math.exp(ravg * n))
            if _v != 0:
                dt = eq1 / (eq0 * math.exp(ravg * n)) - 1.0
                dts.append(dt)
            else:
                dts.append(0.0)

    sdev_p = np.array(dts).std(ddof=True)
    vwr = rnorm100 * (1.0 - pow(sdev_p / sdev_max, tau))
    return vwr

#    calc VariabilityWeightedReturn
#    See:
#      - https://www.crystalbull.com/sharpe-ratio-better-with-log-returns/
def calc_vwr(eq_days: np.array, sdev_max=2.0, tau=0.20) -> float:
    eq = eq_days #.to_numpy()
    eq_0 = np.roll(eq, 1)  # shift()

    # Calculate nlrtot and rtot
    nlrtot = eq[-1] / eq[0] if eq[0] != 0 else float('-inf')
    if nlrtot <= 0.0:
        return float('-inf')
    rtot = math.log(nlrtot)

    # Calculate ravg
    ravg = rtot / len(eq)
    rnorm = math.expm1(ravg * 252)
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
