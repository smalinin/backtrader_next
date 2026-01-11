import time
import pandas as pd
import backtrader_next as bt

class SimpleSizer(bt.Sizer):
    params = (
        ('percents', 99),
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        value = self.broker.getvalue()
        price = data.open[0]+comminfo.p.commission
        size = value / price * (self.p.percents / 100)
        return int(size)


class SmaCross(bt.Strategy):
    params = (
        ('MA1', 20),
        ('MA2', 50),
    )

    def __init__(self):
        self.Order = None
        self.ma1 = bt.nind.SMA(self.data.close, period=self.p.MA1)
        self.ma2 = bt.nind.SMA(self.data.close, period=self.p.MA2)


    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:  # Order is submitted/accepted
            return  # Do nothing until the order is completed

        # if order.status in [order.Completed]:  # Order is completed
        #     if order.isbuy():  # Buy order
        #         pass
        #     elif order.issell():  # Sell order 
        #         pass

        elif order.status in [order.Canceled]:  # Canceled, Margin, Rejected
            print('Order was Canceled', self.data.datetime.datetime(0))

        elif order.status in [order.Margin]:  # Canceled, Margin, Rejected
            print('Order was Margin ', self.data.datetime.datetime(0))

        elif order.status in [order.Rejected]:  # Canceled, Margin, Rejected
            print('Order was Rejected', self.data.datetime.datetime(0))

        self.Order = None  # Reset order



    def next_open(self):
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

