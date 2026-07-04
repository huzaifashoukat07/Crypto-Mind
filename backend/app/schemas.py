from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TradingMode(str, Enum):
    paper = "paper"
    testnet = "testnet"
    live = "live"


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class BotConfig(BaseModel):
    symbol: str = Field(default="BTC/USDT", description="ccxt-style market symbol")
    timeframe: str = Field(default="5m", description="candle timeframe, e.g. 1m/5m/15m/1h")
    mode: TradingMode = TradingMode.paper

    # Strategy params (MA crossover filtered by RSI)
    fast_period: int = Field(default=9, ge=2, le=200)
    slow_period: int = Field(default=21, ge=3, le=400)
    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_overbought: float = Field(default=70, ge=50, le=100)
    rsi_oversold: float = Field(default=30, ge=0, le=50)

    # Capital & risk management
    starting_balance: float = Field(default=1000.0, gt=0, description="paper-mode starting quote balance")
    position_size_pct: float = Field(default=25.0, gt=0, le=100, description="% of available balance per trade")
    stop_loss_pct: float = Field(default=2.0, gt=0, le=50)
    take_profit_pct: float = Field(default=4.0, gt=0, le=200)
    max_daily_loss_pct: float = Field(default=5.0, gt=0, le=100, description="kill switch: stop bot if daily loss exceeds this")

    poll_interval_sec: float = Field(default=5.0, ge=1, le=300)

    # Required to actually arm live trading; ignored for paper/testnet
    live_confirmation: Optional[Literal["I_UNDERSTAND_THE_RISK"]] = None

    @model_validator(mode="after")
    def _check(self):
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        if self.mode == TradingMode.live and self.live_confirmation != "I_UNDERSTAND_THE_RISK":
            raise ValueError(
                "live mode requires live_confirmation == 'I_UNDERSTAND_THE_RISK'"
            )
        return self


class Candle(BaseModel):
    time: int  # unix seconds, matches lightweight-charts expectation
    open: float
    high: float
    low: float
    close: float
    volume: float


class Trade(BaseModel):
    time: int
    side: OrderSide
    price: float
    quantity: float
    reason: str
    pnl: Optional[float] = None


class BotStatus(BaseModel):
    id: str
    config: BotConfig
    status: Literal["starting", "running", "stopped", "error", "stopped_kill_switch"]
    balance_quote: float
    balance_base: float
    position_qty: float
    entry_price: Optional[float]
    unrealized_pnl: float
    realized_pnl: float
    daily_pnl: float
    trades: list[Trade]
    last_error: Optional[str] = None


class StartBotRequest(BaseModel):
    config: BotConfig


class WsEvent(BaseModel):
    type: Literal["candle", "trade", "status", "log", "error"]
    bot_id: str
    data: dict
