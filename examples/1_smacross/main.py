import pandas as pd
import backtrader_next as bt
from backtrader_next.feeds import PandasData
import backtrader_next.analyzers as anal


class SimpleSizer(bt.Sizer):
    params = (
        ('percents', 99),
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        value = self.broker.getvalue()
        price = data.close[0]+comminfo.p.commission
        size = value / price * (self.params.percents / 100)
        return int(size)


class SmaCross(bt.Strategy):
    params = (
        ('MA1', 20),
        ('MA2', 50),
    )

    def __init__(self):
        self.Order = None
        self.ma1 = bt.nind.SMA(self.data.close, period=self.params.MA1)
        self.ma2 = bt.nind.SMA(self.data.close, period=self.params.MA2)


    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:  # Order is submitted/accepted
            return  # Do nothing until the order is completed

        # if order.status in [order.Completed]:  # Order is completed
        #     if order.isbuy():  # Buy order
        #         pass
        #     elif order.issell():  # Sell order 
        #         pass

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:  # Canceled, Margin, Rejected
            print('Order was Canceled/Margin/Rejected')

        self.Order = None  # Reset order



    def next(self, status=None):
        # Use ONLY Long Positions
        if self.crossover(self.ma1, self.ma2):
            pos = self.getposition()
            if pos:
                self.close(size=pos.size)
            self.Order = self.buy()
        elif self.crossover(self.ma2, self.ma1):
            pos = self.getposition()
            if pos:
                self.close(size=pos.size)
            # self.Order = self.sell()

    def crossover(self, ma1, ma2):
        try:
            return ma1[-1] <= ma2[-1] and ma1[0] > ma2[0]
        except IndexError:
            return False



if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(1_000_000.0)
    cerebro.broker.set_shortcash(False)
    cerebro.broker.setcommission(commission=0, margin=1, mult=1)
    cerebro.addsizer(SimpleSizer, percents=90)

    df = pd.read_csv(f"AAPL_1d.csv.zip", sep=";")
    df['Datetime'] = pd.to_datetime(df['Date'].astype(str) , format='%Y-%m-%d')
    df.set_index('Datetime', inplace=True)

    data = PandasData(dataframe=df, timeframe=bt.TimeFrame.Days, compression=1)
    cerebro.adddata(data, name='AAPL')

    cerebro.addstrategy(SmaCross, )

    print(f'Starting Portfolio Value: {cerebro.broker.getvalue():.2f}\n')
    results = cerebro.run()
    print(f'\nFinal Portfolio Value: {cerebro.broker.getvalue():.2f}\n')

    rc = cerebro.statistics()
    print(rc)

    # old plot required matplotlib
    # cerebro.old_plot(style='candle')
    
    cerebro.plot(filename="smacross.html")
    cerebro.show_report(filename="smacross_stats.html")
    print("end")

