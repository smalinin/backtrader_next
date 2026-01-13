import time
import pandas as pd
import backtrader_next as bt
from backtrader_next.feeds import PandasData


class SmaCross(bt.Strategy):
    params = (
        ('MA1', 15),
        ('MA2', 91),
    )

    def __init__(self):
        self.Order = None
        # self.ma1 = bt.indicators.SMA(self.data.close, period=self.p.MA1)
        # self.ma2 = bt.indicators.SMA(self.data.close, period=self.p.MA2)
        self.ma1 = bt.nind.SMA(self.data.close, period=self.p.MA1) #Numba based indicator
        self.ma2 = bt.nind.SMA(self.data.close, period=self.p.MA2) #Numba based indicator


    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:  # Order is submitted/accepted
            return  # Do nothing until the order is completed

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:  # Canceled, Margin, Rejected
            print('Order was Canceled/Margin/Rejected')

        self.Order = None  # Reset order



    def next(self):
        # Use ONLY Long Positions
        if self.crossover(self.ma1, self.ma2):
            pos = self.getposition()
            if pos:
                self.close(size=pos.size)
            self.Order = self.buy(size=1)
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
    cerebro.broker.setcommission(commission=0.0004, leverage=1) # 0.04% per trade

    start = time.perf_counter()
    df = pd.read_csv(f"STOCK_M1.csv.zip", sep=";", parse_dates=["Datetime"], index_col=0)

    data = PandasData(dataframe=df, timeframe=bt.TimeFrame.Minutes, compression=1)
    cerebro.adddata(data, name='STOCK')

    cerebro.addstrategy(SmaCross, )

    results = cerebro.run()
    end = time.perf_counter()
    print(f"Execution time for sum_list: {end - start:.4f} seconds\n\n")
    #print(cerebro.statistics)


