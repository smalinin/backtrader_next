## How to run
#### Execute next command for smacross sample
Note: You must have [UV ](https://docs.astral.sh/uv/getting-started/installation/) package manager 
```
uv run main.py
```
#### Output log
```
Starting Portfolio Value: 1000000.00

Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected
Order was Canceled/Margin/Rejected

Final Portfolio Value: 13125987.48

Strategy                             SmaCross
MA1                                        20
MA2                                        50
Start                     2000-01-03 00:00:00
End                       2024-12-31 00:00:00
Duration                   9129 days 00:00:00
Equity Start [$]                    1000000.0
Equity Final [$]              13125987.479046
Equity Peak [$]               13533263.280804
Commissions [$]                           0.0
Cum Return [%]                      1212.5987
Return (Ann.) [%]                     10.8691
Volatility (Ann.) [%]                 21.0469
CAGR [%]                               7.3656
Sharpe Ratio                           0.6044
Skew                                  -6.1434
Kurtosis                             219.8529
Smart Sharpe Ratio                    -1.7922
Sortino Ratio                           0.812
VWR Ratio                              3.6777
Calmar Ratio                           0.1917
Recovery factor [%]                    5.5986
Max. Drawdown [%]                    -56.6963
Avg. Drawdown [%]                      -4.674
Max. Drawdown Duration     2492 days 00:00:00
Avg. Drawdown Duration       69 days 00:00:00
Drawdown Peak             2000-10-03 00:00:00
# Trades                                   56
Win Rate [%]                          55.3571
Best Trade [%]                        92.0365
Worst Trade [%]                      -63.5437
Avg. Trade [%]                         4.8655
Max. Trade Duration         276 days 00:00:00
Avg. Trade Duration          85 days 00:00:00
Profit Factor                          1.1756
Expectancy [%]                         0.0505
SQN                                    2.2935
Kelly Criterion [%]                   37.6406
dtype: object
end
```
#### Addons
Also it will create two HTML files  and open it in your current browser.
- smacross.html  - charts and trade stats  

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr1.png)

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr2.png?raw=true)

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr3.png)

- smacross_stats.html - quantstats like strategy report

![chart1](https://raw.githubusercontent.com/smalinin/backtrader_next/master/examples/1_smacross/scr4.png)
