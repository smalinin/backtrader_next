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


    cerebro.optstrategy(
        SmaCross,
        MA1=range(10, 50, 5),
        MA2=range(50, 100, 5),
        )

    start = time.perf_counter()
    results = cerebro.run()
    end = time.perf_counter()
    print(f"==Opt time : {end - start:.4f} seconds==")

    list = []
    for stratrun in results:
        for strat in stratrun:
            v = strat.statistics
            list.append(v)

    df = pd.DataFrame(list)
    print(df.head(5))  # Display first 5 rows of the DataFrame
    print(df.columns)  # Display all columns
    print("\n")

    # Save the Optimization results DataFrame to a CSV file
    df.to_csv('opt_results.csv', index=True, lineterminator='\r\n', sep=';')

    # Sort the DataFrame by 'Sharpe Ratio'
    df_sorted = df.sort_values(by='Sharpe Ratio', ascending=False)

    # Display top 5 strategies by Sharpe Ratio
    s = df_sorted.head(5)[['MA1', 'MA2', 'Sharpe Ratio', 'Cum Return [%]', 'Return (Ann.) [%]', 'Max. Drawdown [%]']].to_string(index=False)
    print(s)
