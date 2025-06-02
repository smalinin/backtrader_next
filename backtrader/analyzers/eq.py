from pandas import DataFrame

import backtrader as bt
from backtrader.utils.py3 import items, iteritems
from backtrader import Order
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

    def gen_trades(self, data_name=None) -> 'DataFrame':
        if self.trades_df is None:
            self.trades_df = df.from_records(self.trades, columns=self.trades_header)
            # self.trades_df = df.from_records(self.trades, index=self.trades_header[0], columns=self.trades_header)
        if data_name is None:
            return self.trades_df
        else:
            return self.trades_df[self.trades_df['data_name'] == data_name]

    def gen_orders(self, data_name=None) -> 'DataFrame':
        if self.orders_df is None:
            self.orders_df = df.from_records(self.orders, columns=self.orders_header)
        if data_name is None:
            return self.orders_df
        else:
            return self.orders_df[self.orders_df['data_name'] == data_name]

    def compute_stats(self,
            # trades: Union[List['Trade'], pd.DataFrame],
            # equity: np.ndarray,
            # ohlc_data: pd.DataFrame,
            # strategy_instance: 'Strategy',
            risk_free_rate: float = 0.0,
        # ) -> (pd.Series, StatsRes):
        ) -> pd.Series:
        assert -1 < risk_free_rate < 1

        eq_df = self.gen_eq()
        trades_df = self.gen_trades()
        index = eq_df.index
        equity = eq_df['value'].to_numpy()

        gmean_day_return: float = 0
        day_returns = np.array(np.nan)
        annual_trading_days = np.nan

        day_returns = eq_df['value'].resample('D').last().dropna().pct_change().dropna()
        gmean_day_return = geometric_mean(day_returns)
        annual_trading_days = float(365 if index.dayofweek.to_series().between(5, 6).mean() > 2 / 7 * .6
                                        else 252)
        num_years = len(equity) / annual_trading_days 
        # returns = day_returns.to_numpy()

        # index = ohlc_data.index
        # dd = 1 - equity / np.maximum.accumulate(equity)
        dd = (1- equity / np.maximum.accumulate(equity)) * 100
        dd_dur, dd_peaks = compute_drawdown_duration_peaks(pd.Series(dd, index=index))
        dd_df = 1 - eq_df['value'] / eq_df['value'].cummax()

        equity_df = pd.DataFrame({
            'Equity': equity,
            'DrawdownPct': dd,
            'DrawdownDuration': dd_dur},
            index=index)

        # if isinstance(trades, pd.DataFrame):
        #     trades_df: pd.DataFrame = trades
        #     commissions = None  # Not shown
        # else:
        #     # Came straight from Backtest.run()
        #     trades_df = pd.DataFrame({
        #         'Size': [t.size for t in trades],
        #         'EntryBar': [t.entry_bar for t in trades],
        #         'ExitBar': [t.exit_bar for t in trades],
        #         'EntryPrice': [t.entry_price for t in trades],
        #         'ExitPrice': [t.exit_price for t in trades],
        #         'PnL': [t.pl for t in trades],
        #         'ReturnPct': [t.pl_pct for t in trades],
        #         'EntryTime': [t.entry_time for t in trades],
        #         'ExitTime': [t.exit_time for t in trades],
        #         'SL': [t.sl for t in trades],
        #         'TP': [t.tp for t in trades],
        #         'Tag': [t.tag for t in trades],
        #     })
        #     trades_df['Duration'] = trades_df['ExitTime'] - trades_df['EntryTime']
        #     commissions = sum(t._commissions for t in trades)
        # del trades
        trades_df['Duration'] = trades_df['dateclose'] - trades_df['dateopen']
        # commissions = sum(t._commissions for t in trades)
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

        """
        have_position = np.repeat(0, len(index))
        for t in trades_df.itertuples(index=False):
            have_position[t.EntryBar:t.ExitBar + 1] = 1

        s.loc['Exposure Time [%]'] = have_position.mean() * 100  # In "n bars" time, not index time
        """
        s.loc['Equity Start [$]'] = equity[0]
        s.loc['Equity Final [$]'] = equity[-1]
        s.loc['Equity Peak [$]'] = equity.max()
        s.loc['Commissions [$]'] = commissions
        s.loc['Return [%]'] = (equity[-1] - equity[0]) / equity[0] * 100
        # c = ohlc_data.Close.values
        # s.loc['Buy & Hold Return [%]'] = (c[-1] - c[0]) / c[0] * 100  # long-only return


        # Annualized return and risk metrics are computed based on the (mostly correct)
        # assumption that the returns are compounded. See: https://dx.doi.org/10.2139/ssrn.3054517
        # Our annualized return matches `empyrical.annual_return(day_returns)` whereas
        # our risk doesn't; they use the simpler approach below.
        annualized_return = (1 + gmean_day_return) ** annual_trading_days - 1
        s.loc['Return (Ann.) [%]'] = annualized_return * 100
        s.loc['Volatility (Ann.) [%]'] = np.sqrt(
            (day_returns.var(ddof=int(bool(day_returns.shape))) + (1 + gmean_day_return) ** 2) ** annual_trading_days - (
                    1 + gmean_day_return) ** (2 * annual_trading_days)) * 100  # noqa: E501
        s.loc['Risk (Ann.) [%]'] = day_returns.std(ddof=1) * np.sqrt(annual_trading_days) * 100

        cagr = (equity[-1]/equity[0]) ** (1/num_years) - 1
        s.loc['CAGR [%]'] = cagr

        # Our Sharpe mismatches `empyrical.sharpe_ratio()` because they use arithmetic mean return
        # and simple standard deviation
        s.loc['Sharpe Ratio'] = (s.loc['Return (Ann.) [%]'] - risk_free_rate * 100) / (
                s.loc['Volatility (Ann.) [%]'] or np.nan)  # noqa: E501
        # Our Sortino mismatches `empyrical.sortino_ratio()` because they use arithmetic mean return
        s.loc['Sortino Ratio'] = (annualized_return - risk_free_rate) / (
                np.sqrt(np.mean(day_returns.clip(-np.inf, 0) ** 2)) * np.sqrt(annual_trading_days))  # noqa: E501
        s.loc['VWR Ratio'] = calc_vwr(eq_days=equity_df['Equity'].resample('D').last().dropna().to_numpy())
        max_dd = -np.nan_to_num(dd.max())
        s.loc['Calmar Ratio'] = (annualized_return * 100) / (-max_dd or np.nan)
        s.loc['Recovery factor'] = abs(returns_pct.sum()) / abs(max_dd)
        s.loc['Max. Drawdown [%]'] = max_dd
        s.loc['Avg. Drawdown [%]'] = -dd_peaks.mean()
        s.loc['Max. Drawdown Duration'] = _round_timedelta(dd_dur.max())
        s.loc['Avg. Drawdown Duration'] = _round_timedelta(dd_dur.mean())
        s.loc['Drawdown Peak'] = dd_df.idxmax()
        s.loc['# Trades'] = n_trades = len(trades_df)
        win_rate = np.nan if not n_trades else (pl > 0).mean()
        s.loc['Win Rate [%]'] = win_rate * 100
        s.loc['Best Trade [%]'] = returns_pct.max() * 100
        s.loc['Worst Trade [%]'] = returns_pct.min() * 100
        mean_return = geometric_mean(returns_pct)
        s.loc['Avg. Trade [%]'] = mean_return * 100
        s.loc['Max. Trade Duration'] = _round_timedelta(durations.max())
        s.loc['Avg. Trade Duration'] = _round_timedelta(durations.mean())
        s.loc['Profit Factor'] = returns_pct[returns_pct > 0].sum() / (abs(returns_pct[returns_pct < 0].sum()) or np.nan)  # noqa: E501
        s.loc['Expectancy [%]'] = returns_pct.mean() * 100
        s.loc['SQN'] = np.sqrt(n_trades) * pl.mean() / (pl.std() or np.nan)
        s.loc['Kelly Criterion'] = win_rate - (1 - win_rate) / (pl[pl > 0].mean() / -pl[pl < 0].mean())

        # s.loc['_strategy'] = strategy_instance
        # s.loc['_equity_curve'] = equity_df
        # s.loc['_trades'] = trades_df
        #
        # s = _Stats(s)
        # return s, StatsRes(s, strategy_instance)
        # print(s)
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
    eq_0 = np.roll(eq, 1)  # ����� ������ shift()

    # ������������ nlrtot � rtot
    nlrtot = eq[-1] / eq[0] if eq[0] != 0 else float('-inf')
    if nlrtot <= 0.0:
        return float('-inf')
    rtot = math.log(nlrtot)

    # ������� �������� ���������� � ��� ������������
    ravg = rtot / len(eq)
    rnorm = math.expm1(ravg * 252)
    rnorm100 = rnorm * 100.0

    # ����������������� ������ ����������
    n_vals = np.arange(len(eq))
    expected = eq_0 * np.exp(ravg * n_vals)
    dts = np.where(expected != 0, eq / expected - 1.0, 0.0)

    # ����������� ���������� � ������������� �������� VWR
    sdev_p = np.std(dts[1:], ddof=1)  # ���������� ������ �������, �.�. ��� ����� NaN
    vwr = rnorm100 * (1.0 - (sdev_p / sdev_max) ** tau)
    return vwr

def _data_period(index) -> Union[pd.Timedelta, Number]:
    """Return data index period as pd.Timedelta"""
    values = pd.Series(index[-100:])
    return values.diff().dropna().median()
