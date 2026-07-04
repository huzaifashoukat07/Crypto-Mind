import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from .exchange import ExchangeClient, ExchangeError
from .paper_broker import PaperBroker, PositionState
from .schemas import BotConfig, BotStatus, OrderSide, Position, Trade, TradingMode, WsEvent
from .strategy import MaCrossoverRsiStrategy, StrategyParams

logger = logging.getLogger("bot_engine")

EventCallback = Callable[[WsEvent], None]


class LiveLedger:
    """Tracks per-symbol position/entry-price/realized-pnl bookkeeping for
    testnet/live modes, where the exchange itself enforces balance
    constraints and fills real orders -- this class just mirrors the
    resulting positions so the bot can reason about stop-loss/take-profit
    and PnL."""

    def __init__(self):
        self.positions: dict[str, PositionState] = {}
        self.realized_pnl = 0.0

    def position(self, symbol: str) -> PositionState:
        return self.positions.setdefault(symbol, PositionState())

    def open_symbols(self) -> list[str]:
        return [s for s, p in self.positions.items() if p.quantity > 0]

    def on_fill(self, symbol: str, side: OrderSide, price: float, quantity: float) -> float:
        pos = self.position(symbol)
        pnl_delta = 0.0
        if side == OrderSide.buy:
            new_qty = pos.quantity + quantity
            if pos.entry_price is None:
                pos.entry_price = price
            else:
                pos.entry_price = ((pos.entry_price * pos.quantity) + (price * quantity)) / new_qty
            pos.quantity = new_qty
        else:
            if pos.entry_price is not None:
                pnl_delta = (price - pos.entry_price) * quantity
            pos.quantity = max(0.0, pos.quantity - quantity)
            self.realized_pnl += pnl_delta
            if pos.quantity <= 1e-9:
                pos.quantity = 0.0
                pos.entry_price = None
        return pnl_delta

    def unrealized_pnl(self, symbol: str, mark_price: float) -> float:
        pos = self.positions.get(symbol)
        if not pos or pos.quantity <= 0 or pos.entry_price is None:
            return 0.0
        return (mark_price - pos.entry_price) * pos.quantity


class BotEngine:
    def __init__(self, bot_id: str, config: BotConfig, on_event: EventCallback):
        self.id = bot_id
        self.config = config
        self.on_event = on_event
        self.symbols = config.normalized_symbols

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

        self.candles: dict[str, pd.DataFrame] = {s: pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"]) for s in self.symbols}
        self.last_price: dict[str, float] = {}
        self.trades: list[Trade] = []
        self.status: str = "starting"
        self.last_error: Optional[str] = None
        self.daily_pnl = 0.0
        self._daily_pnl_day = datetime.now(timezone.utc).date()

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
                quote_ccy = self.symbols[0].split("/")[-1]
                self._quote_balance_cache = await self.exchange.fetch_free_balance(quote_ccy)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"failed to initialize exchange connection: {exc}")
            return

        self.status = "running"
        self._emit_status()
        watch_desc = self.symbols[0] if len(self.symbols) == 1 else f"{len(self.symbols)} symbols ({', '.join(self.symbols)})"
        self._emit_log(f"bot started in {self.config.mode.value} mode, watching {watch_desc}")

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
        results = await asyncio.gather(
            *(self.exchange.fetch_ohlcv(s, self.config.timeframe, limit=max(self.config.slow_period * 3, 100)) for s in self.symbols)
        )
        for symbol, fresh in zip(self.symbols, results):
            self.candles[symbol] = pd.DataFrame([c.model_dump() for c in fresh])
            self.last_price[symbol] = float(fresh[-1].close)
            for c in fresh[-2:]:
                self._emit_event("candle", {"symbol": symbol, **c.model_dump()})

        self._roll_daily_pnl_if_new_day()

        if self._check_kill_switch():
            return

        exited_this_tick: set[str] = set()
        for symbol in list(self._open_symbols()):
            if await self._check_risk_exit(symbol):
                exited_this_tick.add(symbol)
                continue
            output = self.strategy.evaluate(self.candles[symbol], in_position=True)
            if output.signal == "sell":
                await self._exit(symbol, output.reason)
                exited_this_tick.add(symbol)

        open_count = len(self._open_symbols())
        slots_available = self.config.max_concurrent_positions - open_count
        if slots_available <= 0:
            return

        candidates = []
        for symbol in self.symbols:
            if symbol in self._open_symbols() or symbol in exited_this_tick:
                continue
            output = self.strategy.evaluate(self.candles[symbol], in_position=False)
            if output.signal == "buy":
                candidates.append((symbol, output))

        # Strongest signal first: lower RSI = more oversold = higher-conviction entry.
        candidates.sort(key=lambda item: item[1].rsi_value if item[1].rsi_value is not None else 100.0)

        for symbol, output in candidates[:slots_available]:
            await self._enter(symbol, output.reason)

    async def _check_risk_exit(self, symbol: str) -> bool:
        price = self.last_price.get(symbol)
        entry = self._entry_price(symbol)
        if price is None or entry is None:
            return False
        change_pct = (price - entry) / entry * 100
        if change_pct <= -self.config.stop_loss_pct:
            await self._exit(symbol, f"stop-loss hit ({change_pct:.2f}%)")
            return True
        if change_pct >= self.config.take_profit_pct:
            await self._exit(symbol, f"take-profit hit ({change_pct:.2f}%)")
            return True
        return False

    def _check_kill_switch(self) -> bool:
        if self.daily_pnl <= -abs(self.config.max_daily_loss_pct) / 100 * self._reference_balance():
            self.status = "stopped_kill_switch"
            self._emit_log(f"KILL SWITCH: daily loss limit reached ({self.daily_pnl:.2f}); bot stopped")
            self._emit_status()
            self._stop_event.set()
            return True
        return False

    def _open_symbols(self) -> list[str]:
        if self.paper_broker:
            return self.paper_broker.open_symbols()
        return self.live_ledger.open_symbols() if self.live_ledger else []

    def _position_qty(self, symbol: str) -> float:
        if self.paper_broker:
            return self.paper_broker.position(symbol).quantity
        return self.live_ledger.position(symbol).quantity if self.live_ledger else 0.0

    def _entry_price(self, symbol: str) -> Optional[float]:
        if self.paper_broker:
            return self.paper_broker.position(symbol).entry_price
        return self.live_ledger.position(symbol).entry_price if self.live_ledger else None

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

    async def _enter(self, symbol: str, reason: str):
        price = self.last_price.get(symbol)
        if price is None:
            return
        if self.paper_broker:
            budget = self.paper_broker.balance_quote * (self.config.position_size_pct / 100)
            qty = budget / price
            if qty <= 0:
                return
            self.paper_broker.execute(symbol, OrderSide.buy, price, qty)
        else:
            budget = self._quote_balance_cache * (self.config.position_size_pct / 100)
            qty = budget / price
            if qty <= 0:
                return
            order = await self.exchange.create_market_order(symbol, OrderSide.buy, qty)
            fill_price = float(order.get("average") or order.get("price") or price)
            fill_qty = float(order.get("filled") or qty)
            self.live_ledger.on_fill(symbol, OrderSide.buy, fill_price, fill_qty)
            price, qty = fill_price, fill_qty

        trade = Trade(time=int(time.time()), symbol=symbol, side=OrderSide.buy, price=price, quantity=qty, reason=reason)
        self.trades.append(trade)
        self._emit_event("trade", trade.model_dump())
        self._emit_log(f"BUY {qty:.6f} {symbol} @ {price:.2f} — {reason}")
        self._emit_status()

    async def _exit(self, symbol: str, reason: str):
        price = self.last_price.get(symbol)
        qty = self._position_qty(symbol)
        if price is None or qty <= 0:
            return
        if self.paper_broker:
            pnl_delta = self.paper_broker.execute(symbol, OrderSide.sell, price, qty)
        else:
            order = await self.exchange.create_market_order(symbol, OrderSide.sell, qty)
            fill_price = float(order.get("average") or order.get("price") or price)
            fill_qty = float(order.get("filled") or qty)
            pnl_delta = self.live_ledger.on_fill(symbol, OrderSide.sell, fill_price, fill_qty)
            price, qty = fill_price, fill_qty

        self.daily_pnl += pnl_delta
        trade = Trade(time=int(time.time()), symbol=symbol, side=OrderSide.sell, price=price, quantity=qty, reason=reason, pnl=pnl_delta)
        self.trades.append(trade)
        self._emit_event("trade", trade.model_dump())
        self._emit_log(f"SELL {qty:.6f} {symbol} @ {price:.2f} — {reason} (PnL {pnl_delta:+.2f})")
        self._emit_status()

    # ---- status / events --------------------------------------------------

    def _fail(self, message: str):
        self.status = "error"
        self.last_error = message
        self._emit_log(f"ERROR: {message}")
        self._emit_status()

    def to_status(self) -> BotStatus:
        positions = []
        for symbol in self._open_symbols():
            qty = self._position_qty(symbol)
            entry = self._entry_price(symbol)
            price = self.last_price.get(symbol, entry or 0.0)
            if entry is None:
                continue
            unrealized = (
                self.paper_broker.unrealized_pnl(symbol, price)
                if self.paper_broker
                else self.live_ledger.unrealized_pnl(symbol, price)
            )
            positions.append(Position(symbol=symbol, quantity=qty, entry_price=entry, unrealized_pnl=unrealized))

        if self.paper_broker:
            balance_quote = self.paper_broker.balance_quote
            realized = self.paper_broker.realized_pnl
        else:
            balance_quote = self._quote_balance_cache
            realized = self.live_ledger.realized_pnl

        return BotStatus(
            id=self.id,
            config=self.config,
            status=self.status,
            balance_quote=balance_quote,
            positions=positions,
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
