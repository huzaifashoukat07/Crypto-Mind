from dataclasses import dataclass, field

from .schemas import OrderSide

TAKER_FEE_RATE = 0.001  # 0.1%, matches Binance's default spot taker fee


@dataclass
class PositionState:
    quantity: float = 0.0
    entry_price: float | None = None


@dataclass
class PaperBroker:
    """Simulated multi-symbol spot broker: fills market orders instantly at
    the given reference price and tracks a shared quote-currency balance plus
    one base-asset position per symbol. Used for mode=paper so the bot can be
    exercised risk-free against real live prices."""

    balance_quote: float
    realized_pnl: float = 0.0
    positions: dict[str, PositionState] = field(default_factory=dict)

    def position(self, symbol: str) -> PositionState:
        return self.positions.setdefault(symbol, PositionState())

    def open_symbols(self) -> list[str]:
        return [s for s, p in self.positions.items() if p.quantity > 0]

    def execute(self, symbol: str, side: OrderSide, price: float, quantity: float) -> float:
        """Returns the realized PnL delta from this fill (0 for entries)."""
        pos = self.position(symbol)
        notional = price * quantity
        fee = notional * TAKER_FEE_RATE
        pnl_delta = 0.0

        if side == OrderSide.buy:
            cost = notional + fee
            if cost > self.balance_quote + 1e-9:
                raise ValueError(f"insufficient paper balance for this buy on {symbol}")
            self.balance_quote -= cost
            new_qty = pos.quantity + quantity
            if pos.entry_price is None:
                pos.entry_price = price
            else:
                pos.entry_price = ((pos.entry_price * pos.quantity) + (price * quantity)) / new_qty
            pos.quantity = new_qty
        else:
            if quantity > pos.quantity + 1e-9:
                raise ValueError(f"insufficient paper position for this sell on {symbol}")
            proceeds = notional - fee
            if pos.entry_price is not None:
                pnl_delta = (price - pos.entry_price) * quantity - fee
            self.balance_quote += proceeds
            pos.quantity -= quantity
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
