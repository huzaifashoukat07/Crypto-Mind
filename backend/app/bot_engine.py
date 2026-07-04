import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from .exchange import ExchangeClient, ExchangeError
from .paper_broker import PaperBroker
from .schemas import BotConfig, BotStatus, Candle, OrderSide, Trade, TradingMode, WsEvent
from .strategy import MaCrossoverRsiStrategy, StrategyParams

logger = logging.getLogger("bot_engine")

EventCallback = Callable[[WsEvent], None]


class LiveLedger:
    """Tracks position/entry-price/realized-pnl bookkeeping for testnet/live
    modes, where the exchange itself enforces balance constraints and fills
    real orders -- this class just mirrors the resulting position so the bot
    can reason about stop-loss/take-profit and PnL."""

    def __init__(self):
        self.balance_base = 0.0
        self.entry_price: Optional[float] = None
        self.realized_pnl = 0.0

    def on_fill(self, side: OrderSide, price: float, quantity: float) -> float:
        pnl_delta = 0.0
        if side == OrderSide.buy:
            new_base = self.balance_base + quantity
            if self.entry_price is None:
                self.entry_price = price
            else:
                self.entry_price = (
                    (self.entry_price * self.balance_base) + (price * quantity)
                ) / new_base
            self.balance_base = new_base
        else:
            if self.entry_price is not None:
                pnl_delta = (price - self.entry_price) * quantity
            self.balance_base = max(0.0, self.balance_base - quantity)
            self.realized_pnl += pnl_delta
            if self.balance_base <= 1e-9:
                self.balance_base = 0.0
                self.entry_price = None
        return pnl_delta

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.balance_base <= 0 or self.entry_price is None:
            return 0.0
        return (mark_price - self.entry_price) * self.balance_base


class BotEngine:
    def __init__(self, bot_id: str, config: BotConfig, on_event: EventCallback):
        self.id = bot_id
        self.config = config
        self.on_event = on_event

        self.exchange = ExchangeClient(config.mode)
        self.strategy = MaCrossoverRsiStrategy(
            StrategyParams(
                fast_period=config.fast_period,
                slow_period=config.slow_period,
                rsi_period=config.rsi_period,
                rsi_overbought=config.rsi_overbought,
                rsi_oversold=config.rsi_oversold,
            )
        )

        self.paper_broker: Optional[PaperBroker] = None
        self.live_ledger: Optional[LiveLedger] = None
        if config.mode == TradingMode.paper:
            self.paper_broker = PaperBroker(balance_quote=config.starting_balance)
        else:
            self.live_ledger = LiveLedger()
            self._quote_balance_cache = config.starting_balance

        self.candles: pd.DataFrame = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        self.trades: list[Trade] = []
        self.status: str = "starting"
        self.last_error: Optional[str] = None
        self.daily_pnl = 0.0
        self._daily_pnl_day = datetime.now(timezone.utc).date()
        self._last_price: Optional[float] = None

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    # ---- lifecycle -----------------------------------------------------

    def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self, reason: str = "stopped by user"):
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()
        if self.status not in ("stopped_kill_switch", "error"):
            self.status = "stopped"
        self._emit_log(reason)
        self._emit_status()

    async def _run(self):
        try:
            await self.exchange.load_markets()
            if self.live_ledger is not None:
                quote_ccy = self.config.symbol.split("/")[-1]
                self._quote_balance_cache = await self.exchange.fetch_free_balance(quote_ccy)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"failed to initialize exchange connection: {exc}")
            return

        self.status = "running"
        self._emit_status()
        self._emit_log(f"bot started in {self.config.mode.value} mode for {self.config.symbol}")

        while not self._stop_event.is_set():
            try:
                await self._tick()
            except ExchangeError as exc:
                self._fail(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("bot tick failed")
                self._fail(f"unexpected error: {exc}")
                return

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.config.poll_interval_sec)
            except asyncio.TimeoutError:
                pass

    # ---- core tick -------------------------------------------------------

    async def _tick(self):
        fresh = await self.exchange.fetch_ohlcv(self.config.symbol, self.config.timeframe, limit=max(self.config.slow_period * 3, 100))
        df = pd.DataFrame([c.model_dump() for c in fresh])
        self.candles = df
        self._last_price = float(df["close"].iloc[-1])
        self._roll_daily_pnl_if_new_day()

        for c in fresh[-2:]:
            self._emit_event("candle", c.model_dump())

        in_position = self._position_qty() > 0
        exited = await self._check_risk_exits(in_position)
        if self.status != "running" or exited:
            return

        output = self.strategy.evaluate(self.candles, in_position=self._position_qty() > 0)
        if output.signal == "hold":
            return

        if output.signal == "buy":
            await self._enter(output.reason)
        elif output.signal == "sell":
            await self._exit(output.reason)

    async def _check_risk_exits(self, in_position: bool) -> bool:
        exited = False
        if in_position and self._last_price is not None:
            entry = self._entry_price()
            if entry is not None:
                change_pct = (self._last_price - entry) / entry * 100
                if change_pct <= -self.config.stop_loss_pct:
                    await self._exit(f"stop-loss hit ({change_pct:.2f}%)")
                    exited = True
                elif change_pct >= self.config.take_profit_pct:
                    await self._exit(f"take-profit hit ({change_pct:.2f}%)")
                    exited = True

        if self.daily_pnl <= -abs(self.config.max_daily_loss_pct) / 100 * self._reference_balance():
            self.status = "stopped_kill_switch"
            self._emit_log(f"KILL SWITCH: daily loss limit reached ({self.daily_pnl:.2f}); bot stopped")
            self._emit_status()
            self._stop_event.set()
        return exited

    def _position_qty(self) -> float:
        if self.paper_broker:
            return self.paper_broker.balance_base
        return self.live_ledger.balance_base if self.live_ledger else 0.0

    def _entry_price(self) -> Optional[float]:
        if self.paper_broker:
            return self.paper_broker.entry_price
        return self.live_ledger.entry_price if self.live_ledger else None

    def _reference_balance(self) -> float:
        if self.paper_broker:
            return self.config.starting_balance
        return self._quote_balance_cache

    def _roll_daily_pnl_if_new_day(self):
        today = datetime.now(timezone.utc).date()
        if today != self._daily_pnl_day:
            self._daily_pnl_day = today
            self.daily_pnl = 0.0

    # ---- order execution -------------------------------------------------

    async def _enter(self, reason: str):
        price = self._last_price
        if price is None:
            return
        if self.paper_broker:
            budget = self.paper_broker.balance_quote * (self.config.position_size_pct / 100)
            qty = budget / price
            if qty <= 0:
                return
            self.paper_broker.execute(OrderSide.buy, price, qty)
        else:
            budget = self._quote_balance_cache * (self.config.position_size_pct / 100)
            qty = budget / price
            if qty <= 0:
                return
            order = await self.exchange.create_market_order(self.config.symbol, OrderSide.buy, qty)
            fill_price = float(order.get("average") or order.get("price") or price)
            fill_qty = float(order.get("filled") or qty)
            self.live_ledger.on_fill(OrderSide.buy, fill_price, fill_qty)
            price, qty = fill_price, fill_qty

        trade = Trade(time=int(time.time()), side=OrderSide.buy, price=price, quantity=qty, reason=reason)
        self.trades.append(trade)
        self._emit_event("trade", trade.model_dump())
        self._emit_log(f"BUY {qty:.6f} {self.config.symbol} @ {price:.2f} — {reason}")
        self._emit_status()

    async def _exit(self, reason: str):
        price = self._last_price
        qty = self._position_qty()
        if price is None or qty <= 0:
            return
        if self.paper_broker:
            pnl_delta = self.paper_broker.execute(OrderSide.sell, price, qty)
        else:
            order = await self.exchange.create_market_order(self.config.symbol, OrderSide.sell, qty)
            fill_price = float(order.get("average") or order.get("price") or price)
            fill_qty = float(order.get("filled") or qty)
            pnl_delta = self.live_ledger.on_fill(OrderSide.sell, fill_price, fill_qty)
            price, qty = fill_price, fill_qty

        self.daily_pnl += pnl_delta
        trade = Trade(time=int(time.time()), side=OrderSide.sell, price=price, quantity=qty, reason=reason, pnl=pnl_delta)
        self.trades.append(trade)
        self._emit_event("trade", trade.model_dump())
        self._emit_log(f"SELL {qty:.6f} {self.config.symbol} @ {price:.2f} — {reason} (PnL {pnl_delta:+.2f})")
        self._emit_status()

    # ---- status / events --------------------------------------------------

    def _fail(self, message: str):
        self.status = "error"
        self.last_error = message
        self._emit_log(f"ERROR: {message}")
        self._emit_status()

    def to_status(self) -> BotStatus:
        price = self._last_price or 0.0
        if self.paper_broker:
            balance_quote = self.paper_broker.balance_quote
            balance_base = self.paper_broker.balance_base
            entry_price = self.paper_broker.entry_price
            unrealized = self.paper_broker.unrealized_pnl(price)
            realized = self.paper_broker.realized_pnl
        else:
            balance_quote = self._quote_balance_cache
            balance_base = self.live_ledger.balance_base
            entry_price = self.live_ledger.entry_price
            unrealized = self.live_ledger.unrealized_pnl(price)
            realized = self.live_ledger.realized_pnl

        return BotStatus(
            id=self.id,
            config=self.config,
            status=self.status,
            balance_quote=balance_quote,
            balance_base=balance_base,
            position_qty=balance_base,
            entry_price=entry_price,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
            daily_pnl=self.daily_pnl,
            trades=self.trades[-100:],
            last_error=self.last_error,
        )

    def _emit_status(self):
        self._emit_event("status", self.to_status().model_dump())

    def _emit_log(self, message: str):
        self._emit_event("log", {"message": message, "time": int(time.time())})

    def _emit_event(self, type_: str, data: dict):
        self.on_event(WsEvent(type=type_, bot_id=self.id, data=data))
