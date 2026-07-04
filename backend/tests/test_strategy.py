import math

import pandas as pd
import pytest

from app.strategy import MaCrossoverRsiStrategy, StrategyParams, rsi, sma


def _candles(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": prices})


def test_sma_basic():
    s = sma(pd.Series([1, 2, 3, 4, 5]), period=2)
    assert math.isnan(s.iloc[0])
    assert s.iloc[1] == pytest.approx(1.5)
    assert s.iloc[-1] == pytest.approx(4.5)


def test_rsi_bounds():
    prices = pd.Series([100, 101, 99, 102, 98, 103, 97, 105, 96, 110, 90])
    r = rsi(prices, period=5)
    assert ((r >= 0) & (r <= 100)).all()


def test_strategy_holds_while_warming_up():
    strat = MaCrossoverRsiStrategy(StrategyParams(3, 8, 5, 70, 30))
    output = strat.evaluate(_candles([100, 101, 102]), in_position=False)
    assert output.signal == "hold"
    assert "warming up" in output.reason


def test_strategy_buys_on_upward_crossover():
    strat = MaCrossoverRsiStrategy(StrategyParams(fast_period=2, slow_period=4, rsi_period=4, rsi_overbought=90, rsi_oversold=10))
    # flat (fast MA == slow MA) then a sharp upturn on the last candle only,
    # so the crossover happens strictly between the last two evaluation points
    prices = [100, 100, 100, 100, 100, 100, 120]
    output = strat.evaluate(_candles(prices), in_position=False)
    assert output.signal == "buy"


def test_strategy_sells_on_downward_crossover():
    strat = MaCrossoverRsiStrategy(StrategyParams(fast_period=2, slow_period=4, rsi_period=4, rsi_overbought=90, rsi_oversold=10))
    prices = [120, 120, 120, 120, 120, 120, 90]
    output = strat.evaluate(_candles(prices), in_position=True)
    assert output.signal == "sell"


def test_strategy_skips_buy_when_overbought():
    strat = MaCrossoverRsiStrategy(StrategyParams(fast_period=2, slow_period=4, rsi_period=4, rsi_overbought=50, rsi_oversold=10))
    prices = [100, 100, 100, 100, 100, 100, 120]
    output = strat.evaluate(_candles(prices), in_position=False)
    assert output.signal == "hold"
