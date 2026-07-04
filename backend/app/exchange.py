import asyncio
from typing import Optional

import ccxt

from .config import settings
from .schemas import Candle, OrderSide, TradingMode


class ExchangeError(Exception):
    pass


class ExchangeClient:
    """Thin async-friendly wrapper around ccxt's synchronous binance client.

    Market data (OHLCV) works in every mode without API keys. Order placement
    is only reachable for testnet/live modes, gated by BotConfig validation
    and the ALLOW_LIVE_TRADING env flag checked at the API layer.
    """

    def __init__(self, mode: TradingMode):
        self.mode = mode
        params: dict = {"enableRateLimit": True}
        if mode != TradingMode.paper:
            # Only attach credentials outside paper mode: ccxt authenticates
            # extra endpoints (e.g. fetch_currencies during load_markets)
            # whenever apiKey is present, even for calls that don't strictly
            # need it. Paper mode must stay pure public/unauthenticated data.
            params["apiKey"] = settings.binance_api_key or None
            params["secret"] = settings.binance_api_secret or None
            # Binance rejects signed requests if the client clock is more than
            # ~1s ahead of its server time (error -1021), which is common on
            # machines with clock drift (esp. Windows). This has ccxt measure
            # the offset once and apply it to every signed request's
            # timestamp, instead of requiring the OS clock to be exact.
            params["options"] = {"adjustForTimeDifference": True, "recvWindow": 10000}
        self._exchange = ccxt.binance(params)
        if mode == TradingMode.testnet:
            self._exchange.set_sandbox_mode(True)

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        raw = await asyncio.to_thread(self._exchange.fetch_ohlcv, symbol, timeframe, None, limit)
        return [
            Candle(time=int(row[0] // 1000), open=row[1], high=row[2], low=row[3], close=row[4], volume=row[5])
            for row in raw
        ]

    async def fetch_ticker_price(self, symbol: str) -> float:
        ticker = await asyncio.to_thread(self._exchange.fetch_ticker, symbol)
        price = ticker.get("last") or ticker.get("close")
        if price is None:
            raise ExchangeError(f"could not read last price for {symbol}")
        return float(price)

    async def create_market_order(self, symbol: str, side: OrderSide, quantity: float) -> dict:
        if self.mode == TradingMode.paper:
            raise ExchangeError("paper mode must not call create_market_order on the real exchange")
        if not settings.binance_api_key or not settings.binance_api_secret:
            raise ExchangeError("BINANCE_API_KEY/SECRET are not configured on the server")
        order = await asyncio.to_thread(
            self._exchange.create_order, symbol, "market", side.value, quantity
        )
        return order

    async def load_markets(self):
        await asyncio.to_thread(self._exchange.load_markets)

    async def fetch_free_balance(self, currency: str) -> float:
        balance = await asyncio.to_thread(self._exchange.fetch_balance)
        free = balance.get("free", {}).get(currency)
        return float(free) if free is not None else 0.0
