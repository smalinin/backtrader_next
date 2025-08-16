## How to run

### Notes. Only `PandasData` feed is optimized for testing performance for `runonce=True`

### Run optimization

Note: You must have [UV ](https://docs.astral.sh/uv/getting-started/installation/) package manager 
```
uv run run_optimize.py
```
#### Output log
```
==Opt time : 8.7383 seconds==
   Strategy  MA1  MA2      Start        End  Duration  Equity Start [$]  Equity Final [$]  ...  Worst Trade [%]  Avg. Trade [%]  Max. Trade Duration  Avg. Trade Duration  Profit Factor  Expectancy [%]     SQN  Kelly Criterion [%]
0  SmaCross   10   50 2010-01-04 2024-12-31 5475 days         1000000.0      4.188669e+06  ...         -11.0000          3.2100             256 days              74 days         1.1507          0.0436  2.0105              28.9543
1  SmaCross   10   55 2010-01-04 2024-12-31 5475 days         1000000.0      4.333700e+06  ...         -11.1497          4.0542             262 days              90 days         1.1541          0.0445  2.0614              31.9269
2  SmaCross   10   60 2010-01-04 2024-12-31 5475 days         1000000.0      4.671951e+06  ...         -11.1072          4.6047             629 days              97 days         1.1597          0.0466  1.8073              29.4843
3  SmaCross   10   65 2010-01-04 2024-12-31 5475 days         1000000.0      4.709983e+06  ...         -11.1469          4.7109             628 days             100 days         1.1606          0.0469  1.7976              26.6267
4  SmaCross   10   70 2010-01-04 2024-12-31 5475 days         1000000.0      4.811946e+06  ...         -10.5054          4.8914             629 days             103 days         1.1618          0.0475  1.8491              31.4215

[5 rows x 38 columns]

Index(['Strategy', 'MA1', 'MA2', 'Start', 'End', 'Duration',
       'Equity Start [$]', 'Equity Final [$]', 'Equity Peak [$]',
       'Commissions [$]', 'Cum Return [%]', 'Return (Ann.) [%]',
       'Volatility (Ann.) [%]', 'CAGR [%]', 'Sharpe Ratio', 'Skew', 'Kurtosis',
       'Smart Sharpe Ratio', 'Sortino Ratio', 'VWR Ratio', 'Calmar Ratio',
       'Recovery factor [%]', 'Max. Drawdown [%]', 'Avg. Drawdown [%]',
       'Max. Drawdown Duration', 'Avg. Drawdown Duration', 'Drawdown Peak',
       '# Trades', 'Win Rate [%]', 'Best Trade [%]', 'Worst Trade [%]',
       'Avg. Trade [%]', 'Max. Trade Duration', 'Avg. Trade Duration',
       'Profit Factor', 'Expectancy [%]', 'SQN', 'Kelly Criterion [%]'],
      dtype='object')


 MA1  MA2  Sharpe Ratio  Cum Return [%]  Return (Ann.) [%]  Max. Drawdown [%]
  35   65        0.8049        621.8594            14.1133           -32.6211
  20   95        0.7972        621.4102            14.1086           -26.3586
  20   80        0.7883        587.1283            13.7381           -30.5704
  15   95        0.7869        588.6359            13.7548           -28.5787
  10   85        0.7866        535.4134            13.1453           -25.5787
```
####  Optimization results saved to file  [opt_results.csv](https://smalinin.github.io/backtrader_next/2_optimize/opt_results.csv) 

```csv
;Strategy;MA1;MA2;Start;End;Duration;Equity Start [$];Equity Final [$];Equity Peak [$];Commissions [$];Cum Return [%];Return (Ann.) [%];Volatility (Ann.) [%];CAGR [%];Sharpe Ratio;Skew;Kurtosis;Smart Sharpe Ratio;Sortino Ratio;VWR Ratio;Calmar Ratio;Recovery factor [%];Max. Drawdown [%];Avg. Drawdown [%];Max. Drawdown Duration;Avg. Drawdown Duration;Drawdown Peak;# Trades;Win Rate [%];Best Trade [%];Worst Trade [%];Avg. Trade [%];Max. Trade Duration;Avg. Trade Duration;Profit Factor;Expectancy [%];SQN;Kelly Criterion [%]
0;SmaCross;10;50;2010-01-04;2024-12-31;5475 days;1000000.0;4188668.553565583;4913810.0508043505;0.0;318.8669;10.0395;16.8103;6.8151;0.6533;-0.1167;9.0822;0.5395;0.9461;3.6048;0.338;5.5358;-29.704;-3.2255;1098 days;48 days;2023-03-01;50;48.0;27.4678;-11.0;3.21;256 days;74 days;1.1507;0.0436;2.0105;28.9543
1;SmaCross;10;55;2010-01-04;2024-12-31;5475 days;1000000.0;4333700.432374537;5087365.077807643;0.0;333.37;10.29;16.8523;6.9826;0.6656;-0.1571;9.3777;0.5388;0.9636;3.6821;0.3472;5.6664;-29.6403;-3.1894;827 days;44 days;2023-03-01;41;51.2195;28.374;-11.1497;4.0542;262 days;90 days;1.1541;0.0445;2.0614;31.9269
2;SmaCross;10;60;2010-01-04;2024-12-31;5475 days;1000000.0;4671951.17639749;5588747.348524518;0.0;367.1951;10.845;17.0591;7.3533;0.689;-0.1096;9.0558;0.5569;1.0033;3.8533;0.3646;5.9171;-29.7425;-3.2663;823 days;40 days;2023-01-30;38;47.3684;74.0279;-11.1072;4.6047;629 days;97 days;1.1597;0.0466;1.8073;29.4843
3;SmaCross;10;65;2010-01-04;2024-12-31;5475 days;1000000.0;4709982.869475702;5656125.700274502;0.0;370.9983;10.905;17.0802;7.3933;0.6916;-0.1314;9.0693;0.5561;1.0049;3.8716;0.3747;6.0762;-29.107;-3.2383;923 days;43 days;2023-01-30;37;43.2432;73.1228;-11.1469;4.7109;628 days;100 days;1.1606;0.0469;1.7976;26.6267
4;SmaCross;10;70;2010-01-04;2024-12-31;5475 days;1000000.0;4811946.340528009;5696067.397313156;0.0;381.1946;11.0638;17.1492;7.4993;0.6978;-0.1216;9.0306;0.5601;1.0148;3.9205;0.4068;6.5873;-27.2004;-3.3442;955 days;43 days;2023-01-30;36;50.0;69.7794;-10.5054;4.8914;629 days;103 days;1.1618;0.0475;1.8491;31.4215
5;SmaCross;10;75;2010-01-04;2024-12-31;5475 days;1000000.0;5293772.733557964;6414363.245240125;0.0;429.3773;11.7739;17.3664;7.9725;0.728;-0.1437;8.8082;0.5737;1.0586;4.1399;0.3994;6.4204;-29.4823;-2.8998;861 days;39 days;2023-01-30;35;45.7143;76.4536;-10.0565;5.3272;630 days;107 days;1.1687;0.0502;1.7997;29.8128
6;SmaCross;10;80;2010-01-04;2024-12-31;5475 days;1000000.0;5615025.544542419;6846154.177102055;0.0;461.5026;12.2146;17.435;8.2657;0.7484;-0.1656;8.6734;0.5815;1.0862;4.2763;0.427;6.83;-28.6039;-2.9012;816 days;38 days;2022-12-28;35;40.0;110.801;-9.7487;5.5161;831 days;108 days;1.1728;0.0518;1.6887;26.0609
...
```

### Run strategy with optimized parameters
```
uv run run_strategy.py
```
#### Output log
```
Strategy                             SmaCross
MA1                                        35
MA2                                        65
Start                     2010-01-04 00:00:00
End                       2024-12-31 00:00:00
Duration                   5475 days 00:00:00
Equity Start [$]                    1000000.0
Equity Final [$]               7218593.659401
Equity Peak [$]                8087290.121056
Commissions [$]                           0.0
Cum Return [%]                       621.8594
Return (Ann.) [%]                     14.1133
Volatility (Ann.) [%]                  18.548
CAGR [%]                               9.5248
Sharpe Ratio                           0.8049
Skew                                  -0.1963
Kurtosis                              15.8372
Smart Sharpe Ratio                     0.4396
Sortino Ratio                          1.1743
VWR Ratio                              4.8679
Calmar Ratio                           0.4326
Recovery factor [%]                    6.8521
Max. Drawdown [%]                    -32.6211
Avg. Drawdown [%]                     -2.8806
Max. Drawdown Duration     1098 days 00:00:00
Avg. Drawdown Duration       35 days 00:00:00
Drawdown Peak             2023-01-05 00:00:00
# Trades                                   26
Win Rate [%]                          61.5385
Best Trade [%]                       113.7157
Worst Trade [%]                      -15.1364
Avg. Trade [%]                         8.8499
Max. Trade Duration         846 days 00:00:00
Avg. Trade Duration         145 days 00:00:00
Profit Factor                          1.1934
Expectancy [%]                         0.0592
SQN                                    2.2167
Kelly Criterion [%]                    49.468
dtype: object
```
#### Addons
Also it will create two HTML files  and open it in your current browser.
- [smacross.html](https://smalinin.github.io/backtrader_next/2_optimize/smacross.html)  - charts and trade stats  

- [smacross_stats.html](https://smalinin.github.io/backtrader_next/2_optimize/smacross_stats.html) - quantstats like strategy report

