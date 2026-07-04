from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

Signal = Literal["buy", "sell", "hold"]


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


@dataclass
class StrategyParams:
    fast_period: int
    slow_period: int
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float


@dataclass
class StrategyOutput:
    signal: Signal
    reason: str
    fast_ma: Optional[float]
    slow_ma: Optional[float]
    rsi_value: Optional[float]


class MaCrossoverRsiStrategy:
    """Momentum strategy: a fast/slow moving-average crossover generates the
    directional signal, and RSI is used as a filter to avoid buying into
    overbought conditions or selling into oversold ones (i.e. don't chase a
    move that's already extended)."""

    def __init__(self, params: StrategyParams):
        self.params = params

    def evaluate(self, candles: pd.DataFrame, in_position: bool) -> StrategyOutput:
        p = self.params
        needed = max(p.slow_period, p.rsi_period) + 2
        if len(candles) < needed:
            return StrategyOutput("hold", f"warming up ({len(candles)}/{needed} candles)", None, None, None)

        close = candles["close"]
        fast = sma(close, p.fast_period)
        slow = sma(close, p.slow_period)
        rsi_series = rsi(close, p.rsi_period)

        fast_now, fast_prev = fast.iloc[-1], fast.iloc[-2]
        slow_now, slow_prev = slow.iloc[-1], slow.iloc[-2]
        rsi_now = rsi_series.iloc[-1]

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        if not in_position and crossed_up and rsi_now < p.rsi_overbought:
            return StrategyOutput(
                "buy",
                f"fast MA crossed above slow MA (RSI {rsi_now:.1f} < {p.rsi_overbought})",
                fast_now, slow_now, rsi_now,
            )
        if in_position and (crossed_down or rsi_now > p.rsi_overbought):
            reason = "fast MA crossed below slow MA" if crossed_down else f"RSI overbought ({rsi_now:.1f})"
            return StrategyOutput("sell", reason, fast_now, slow_now, rsi_now)
        if not in_position and rsi_now < p.rsi_oversold and fast_now > fast_prev:
            return StrategyOutput(
                "buy",
                f"RSI oversold reversal ({rsi_now:.1f} < {p.rsi_oversold}) with upturn",
                fast_now, slow_now, rsi_now,
            )

        return StrategyOutput("hold", "no signal", fast_now, slow_now, rsi_now)
