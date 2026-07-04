from dataclasses import dataclass, field

from .schemas import OrderSide

TAKER_FEE_RATE = 0.001  # 0.1%, matches Binance's default spot taker fee


@dataclass
class PaperBroker:
    """Simulated single-symbol spot broker: fills market orders instantly at
    the given reference price and tracks a quote-currency balance plus a
    base-asset position. Used for mode=paper so the bot can be exercised
    risk-free against real live prices."""

    balance_quote: float
    balance_base: float = 0.0
    realized_pnl: float = 0.0
    _entry_price: float | None = field(default=None, init=False)

    @property
    def entry_price(self) -> float | None:
        return self._entry_price

    def execute(self, side: OrderSide, price: float, quantity: float) -> float:
        """Returns the realized PnL delta from this fill (0 for entries)."""
        notional = price * quantity
        fee = notional * TAKER_FEE_RATE
        pnl_delta = 0.0

        if side == OrderSide.buy:
            cost = notional + fee
            if cost > self.balance_quote + 1e-9:
                raise ValueError("insufficient paper balance for this buy")
            self.balance_quote -= cost
            new_base = self.balance_base + quantity
            if self._entry_price is None:
                self._entry_price = price
            else:
                self._entry_price = (
                    (self._entry_price * self.balance_base) + (price * quantity)
                ) / new_base
            self.balance_base = new_base
        else:
            if quantity > self.balance_base + 1e-9:
                raise ValueError("insufficient paper position for this sell")
            proceeds = notional - fee
            if self._entry_price is not None:
                pnl_delta = (price - self._entry_price) * quantity - fee
            self.balance_quote += proceeds
            self.balance_base -= quantity
            self.realized_pnl += pnl_delta
            if self.balance_base <= 1e-9:
                self.balance_base = 0.0
                self._entry_price = None

        return pnl_delta

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.balance_base <= 0 or self._entry_price is None:
            return 0.0
        return (mark_price - self._entry_price) * self.balance_base
