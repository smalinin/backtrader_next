# Aurora: supported API and strategy migration

Aurora is a backtesting engine with data preloading, NumPy-based OHLCV storage,
and vectorized indicator calculation. It provides part of the familiar Cerebro
and Strategy API. Cerebro strategies require adaptation.

## Compatibility limits

| Component | Cerebro | Aurora |
| --- | --- | --- |
| Engine | `bt.Cerebro` | `bt.aurora.Aurora` |
| Base strategy | `bt.Strategy` | `bt.aurora.AuroraStrategy` |
| Pandas/CSV feeds | `bt.feeds.*` | `AuroraPandasData`, `AuroraCSVData` |
| Standard indicators | `bt.ind.*` | Not supported |
| Cerebro Numba indicators | `bt.nind.*` | Not supported |
| Aurora indicators | Separate infrastructure | `bt.aurora.indicators.*` |
| Orders and positions | Strategy and broker API | Familiar `buy`, `sell`, `close`, `cancel`, `getposition` |
| Analyzers | Cerebro API | Register with `addanalyzer`; compatibility depends on the analyzer's requirements |

Aurora does not run the usual precalculation and advancement cycle for standard
Cerebro indicators. Its simplified indicators are calculated from preloaded
arrays and follow the feed's current index.

Numba compilation does not make an indicator compatible with Aurora:
`bt.nind.MACD` is intended for Cerebro, while `bt.aurora.indicators.MACD` is for Aurora.
The exported low-level `AuroraIndicator` class is also not an adapter for
standard indicators.

`backtrader_next.aurora.indicators` provides `SMA`, `EMA`, `RSI`, `MACD`,
`BollingerBands`, and `ATR`. `AuroraSimpleIndicator` and `MultiLineIndicator`
are provided for custom implementations.

## Strategy example

`df` is a prepared DataFrame with a `DatetimeIndex` and OHLCV columns.
The indicator in the example is created in `start()`. Its readiness is checked
before use: simplified indicators do not register their warm-up period in the
standard Cerebro indicator tree.

```python
import math

from backtrader_next.aurora import Aurora, AuroraPandasData, AuroraStrategy
from backtrader_next.aurora.indicators import SMA


class TrendStrategy(AuroraStrategy):
    def start(self):
        self.sma = SMA(self.data, period=20)

    def next(self):
        average = self.sma[0]
        if not math.isfinite(average):
            return
        price = self.data.close[0]
        if not self.position and price > average:
            self.buy()
        elif self.position and price < average:
            self.close()


engine = Aurora()
engine.adddata(AuroraPandasData(dataframe=df))
engine.addstrategy(TrendStrategy)
strategies = engine.run()
statistics = engine.statistics
```

## Migration steps

1. Use `AuroraStrategy` and Aurora feeds.
2. Replace `bt.ind.*` and `bt.nind.*` indicators with Aurora implementations.
3. Check line access, indicator parameters, and the readiness of their values.
4. Check the compatibility of the analyzers and engine features you use.

The `Eq` analyzer is added by default. The presence of `addanalyzer` does not
mean that all aspects of the Cerebro analyzer lifecycle are supported.

Aurora supports backtesting only, with preloading and vectorized calculation.
Live trading, step-by-step `runnext` mode, replay/resample, and feed filters
are not supported. Resample and prepare data before running the engine.
