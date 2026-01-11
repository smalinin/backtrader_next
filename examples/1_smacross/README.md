## How to run

#### Notes. Only `PandasData` feed is optimized for testing performance for `runonce=True`

#### Execute next command for smacross sample
Note: You must have [UV ](https://docs.astral.sh/uv/getting-started/installation/) package manager 
```
uv run main.py
```
#### Output log
```
Starting Portfolio Value: 1000000.00


Final Portfolio Value: 34851211.71

Strategy                             SmaCross
MA1                                        20
MA2                                        50
Start                     2000-01-03 00:00:00
End                       2024-12-31 00:00:00
Duration                   9129 days 00:00:00
Equity Start [$]                    1000000.0
Equity Final [$]              34851211.709695
Equity Peak [$]               36036465.624429
Commissions [$]                           0.0
Cum Return [%]                      3385.1212
Return (Ann.) [%]                     15.2939
Volatility (Ann.) [%]                 28.2518
CAGR [%]                                 10.3
Sharpe Ratio                           0.6555
Skew                                   -3.586
Kurtosis                             116.5671
Smart Sharpe Ratio                    -0.9693
Sortino Ratio                          0.9118
VWR Ratio                              5.1497
Calmar Ratio                           0.1977
Recovery factor [%]                     5.973
Max. Drawdown [%]                    -77.3588
Avg. Drawdown [%]                      -5.124
Max. Drawdown Duration     1679 days 00:00:00
Avg. Drawdown Duration       59 days 00:00:00
Drawdown Peak             2001-07-25 00:00:00
# Trades                                   66
Win Rate [%]                          56.0606
Best Trade [%]                       104.0816
Worst Trade [%]                      -63.5437
Avg. Trade [%]                         5.5053
Max. Trade Duration         276 days 00:00:00
Avg. Trade Duration          89 days 00:00:00
Profit Factor                          1.1697
Expectancy [%]                         0.0735
SQN                                    2.3002
Kelly Criterion [%]                   39.0365
dtype: object
end
```
#### Addons
Also it will create two HTML files  and open it in your current browser.
- [smacross.html](https://smalinin.github.io/backtrader_next/1_smacross/smacross.html)  - charts and trade stats  

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr1.png)

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr2.png?raw=true)

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr3.png)

- [smacross_stats.html](https://smalinin.github.io/backtrader_next/1_smacross/smacross_stats.html) - quantstats like strategy report

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr4.png)
