## How to run

### Notes. Only `PandasData` feed is optimized for testing performance for `runonce=True`

### Run optimization

Note: You must have [UV ](https://docs.astral.sh/uv/getting-started/installation/) package manager 
```
uv run run_optimize.py
```
#### Output log
```
Optimization...: 100%|█████████████████████████████████████████████████████████████████| 80/80 [00:05<00:00, 14.98it/s]
==Opt time : 5.3422 seconds==
   Strategy  MA1  MA2      Start  ... Profit Factor Expectancy [%]     SQN  Kelly Criterion [%]
0  SmaCross   10   50 2010-01-04  ...        1.1509         0.0474  1.9570              28.6075
1  SmaCross   10   55 2010-01-04  ...        1.1553         0.0488  2.0050              31.6561
2  SmaCross   10   60 2010-01-04  ...        1.1601         0.0508  1.7574              29.0871
3  SmaCross   10   65 2010-01-04  ...        1.1607         0.0509  1.7398              26.1528
4  SmaCross   10   70 2010-01-04  ...        1.1619         0.0516  1.7939              30.9278

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
  35   65        0.8096        749.5372            15.3614           -34.7825
  20   95        0.8030        742.4304            15.2967           -27.8812
  20   80        0.7947        701.2967            14.9118           -32.7819
  10   85        0.7894        631.6195            14.2157           -27.6852
  15   95        0.7841        670.1736            14.6082           -30.2628

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
Equity Final [$]               8495372.329411
Equity Peak [$]                9625789.265913
Commissions [$]                           0.0
Cum Return [%]                       749.5372
Return (Ann.) [%]                     15.3614
Volatility (Ann.) [%]                 20.1744
CAGR [%]                                10.35
Sharpe Ratio                           0.8096
Skew                                   -0.164
Kurtosis                              15.8821
Smart Sharpe Ratio                     0.4405
Sortino Ratio                          1.1834
VWR Ratio                              5.2601
Calmar Ratio                           0.4416
Recovery factor [%]                    7.0306
Max. Drawdown [%]                    -34.7825
Avg. Drawdown [%]                      -3.103
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
Profit Factor                          1.1947
Expectancy [%]                         0.0648
SQN                                    2.1723
Kelly Criterion [%]                   49.2085
dtype: object
```

#### Addons
Also it will create two HTML files  and open it in your current browser.
- [smacross.html](https://smalinin.github.io/backtrader_next/2_optimize/smacross.html)  - charts and trade stats  

- [smacross_stats.html](https://smalinin.github.io/backtrader_next/2_optimize/smacross_stats.html) - quantstats like strategy report

