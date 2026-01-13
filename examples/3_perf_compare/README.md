
# Trading Strategy Performance Comparison: Dual Moving Averages

This project provides a comprehensive performance benchmark comparing three Python backtesting frameworks: **Backtesting**, **Backtrader**, and **Backtrader-next**. 
The comparison is based on a dual moving average crossover strategy tested on 430,000 historical price candles.

## Backtesting Frameworks

1. [Backtesting.py](https://github.com/kernc/backtesting.py) - Lightweight and easy-to-use framework (doesn't support trading, only for backtesting)
2. [Backtrader](https://github.com/mementum/backtrader) - Feature-rich framework with extensive capabilities
3. [Backtrader-next](https://github.com/smalinin/backtrader_next) - Modern fork of Backtrader with optimizations  

 
## Testing Parameters

The performance test was conducted with the following specifications:

- **Python Version:** 3.13
- **Asset Type:** Stock / Equity
- **Historical Data Period:** January 1, 2024 - October 10, 2025 (~21 months)
- **Dataset Size:** 430,000 price candles
- **Position Size:** 1 contract per trade
- **Strategy:** Dual Simple Moving Average (SMA) Crossover
  - **SMA1 (Fast):** 15 periods
  - **SMA2 (Slow):** 91 periods
- **Backtest Mode:** Single full pass through historical data (no re-optimization)


## Installation and Usage

### Prerequisites

Ensure you have Python 3.13 installed on your system.

### 1. Install the `uv` Package Manager

We use `uv` for fast and efficient dependency management:

```bash
pip install uv
```

### 2. Run the Backtest

Execute any of the three frameworks:

**Backtesting** - Fastest execution
```bash
uv run main_backtesting.py
```

**Backtrader** - Feature-rich but slower
```bash
uv run main_backtrader.py
```

**Backtrader-next** - Modern optimized version
```bash
uv run main_backtrader_next.py
```

### 3. Performance Results

| Framework | Execution Time | Relative Speed |
|---|---|---|
| Backtesting | 2.95 sec | 14.3x faster than Backtrader |
| Backtrader-next | 12.33 sec | 3.4x faster than Backtrader |
| Backtrader | 42.25 sec | Baseline |


