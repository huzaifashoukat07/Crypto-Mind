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
    symbols: list[str] = Field(
        default=["BTC/USDT"],
        min_length=1,
        max_length=10,
        description="ccxt-style market symbols to watch. One symbol trades that pair only; "
        "more than one puts the bot in scanner mode, where it evaluates every symbol each "
        "tick and automatically enters whichever show the strongest signal.",
    )
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
    max_concurrent_positions: int = Field(
        default=3, ge=1, le=10, description="cap on how many symbols can be held open at once in scanner mode"
    )

    poll_interval_sec: float = Field(default=5.0, ge=1, le=300)

    # Optional ML confirmation filter (see backend/ml/train.py). Requires a
    # model already trained for the symbol/timeframe; silently has no effect
    # otherwise (the bot logs that it found no model and falls back to the
    # base strategy signal alone).
    use_ml_filter: bool = Field(default=False, description="require a trained ML classifier to also confirm buy signals")
    ml_confidence_threshold: float = Field(default=0.55, ge=0.5, le=0.99)

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
        quote_currencies = {s.strip().upper().split("/")[-1] for s in self.symbols}
        if len(quote_currencies) > 1:
            raise ValueError(
                f"all watched symbols must share the same quote currency (got {sorted(quote_currencies)}), "
                "since balance is tracked as a single shared pool"
            )
        return self

    @property
    def normalized_symbols(self) -> list[str]:
        seen: dict[str, None] = {}
        for s in self.symbols:
            seen.setdefault(s.strip().upper(), None)
        return list(seen.keys())


class Candle(BaseModel):
    time: int  # unix seconds, matches lightweight-charts expectation
    open: float
    high: float
    low: float
    close: float
    volume: float


class Trade(BaseModel):
    time: int
    symbol: str
    side: OrderSide
    price: float
    quantity: float
    reason: str
    pnl: Optional[float] = None


class Position(BaseModel):
    symbol: str
    quantity: float
    entry_price: float
    unrealized_pnl: float


class BotStatus(BaseModel):
    id: str
    config: BotConfig
    status: Literal["starting", "running", "stopped", "error", "stopped_kill_switch"]
    balance_quote: float
    positions: list[Position]
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
