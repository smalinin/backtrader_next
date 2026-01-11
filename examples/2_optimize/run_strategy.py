import time
import pandas as pd
import backtrader_next as bt
from backtrader_next.feeds import PandasData
from strategy import SimpleSizer, SmaCross


if __name__ == '__main__':

    cerebro = bt.Cerebro(cheat_on_open=True)
    cerebro.broker.setcash(1_000_000.0)
    cerebro.broker.set_shortcash(False)
    cerebro.broker.set_coo(True)
    cerebro.broker.setcommission(commission=0, margin=False)
    cerebro.addsizer(SimpleSizer, percents=99)

    df = pd.read_csv(f"MSFT_1d.csv.zip", sep=";")
    df['Datetime'] = pd.to_datetime(df['Date'].astype(str) , format='%Y-%m-%d')
    df.set_index('Datetime', inplace=True)

    data = PandasData(dataframe=df, timeframe=bt.TimeFrame.Days, compression=1)
    cerebro.adddata(data, name='MSFT')

    cerebro.addstrategy(SmaCross, MA1=35, MA2=65) # use optimized parameters

    cerebro.run()

    print(cerebro.statistics)

    cerebro.plot(filename="smacross.html")
    cerebro.show_report(filename="smacross_stats.html")

