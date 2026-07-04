import pytest

from app.paper_broker import PaperBroker
from app.schemas import OrderSide


def test_buy_reduces_balance_and_sets_position():
    broker = PaperBroker(balance_quote=1000.0)
    broker.execute("BTC/USDT", OrderSide.buy, price=100.0, quantity=2.0)
    assert broker.position("BTC/USDT").quantity == pytest.approx(2.0)
    assert broker.balance_quote == pytest.approx(1000.0 - 200.0 - 0.2)
    assert broker.position("BTC/USDT").entry_price == pytest.approx(100.0)


def test_sell_realizes_pnl():
    broker = PaperBroker(balance_quote=1000.0)
    broker.execute("BTC/USDT", OrderSide.buy, price=100.0, quantity=1.0)
    pnl = broker.execute("BTC/USDT", OrderSide.sell, price=110.0, quantity=1.0)
    assert pnl == pytest.approx(10.0 - 0.11, abs=0.01)
    assert broker.position("BTC/USDT").quantity == 0.0
    assert broker.position("BTC/USDT").entry_price is None


def test_insufficient_balance_raises():
    broker = PaperBroker(balance_quote=10.0)
    with pytest.raises(ValueError):
        broker.execute("BTC/USDT", OrderSide.buy, price=100.0, quantity=1.0)


def test_insufficient_position_raises():
    broker = PaperBroker(balance_quote=1000.0)
    with pytest.raises(ValueError):
        broker.execute("BTC/USDT", OrderSide.sell, price=100.0, quantity=1.0)


def test_unrealized_pnl_tracks_mark_price():
    broker = PaperBroker(balance_quote=1000.0)
    broker.execute("BTC/USDT", OrderSide.buy, price=100.0, quantity=2.0)
    assert broker.unrealized_pnl("BTC/USDT", 110.0) == pytest.approx(20.0)
    assert broker.unrealized_pnl("BTC/USDT", 90.0) == pytest.approx(-20.0)


def test_positions_are_independent_per_symbol():
    broker = PaperBroker(balance_quote=1000.0)
    broker.execute("BTC/USDT", OrderSide.buy, price=100.0, quantity=1.0)
    broker.execute("ETH/USDT", OrderSide.buy, price=50.0, quantity=2.0)
    assert set(broker.open_symbols()) == {"BTC/USDT", "ETH/USDT"}
    broker.execute("BTC/USDT", OrderSide.sell, price=120.0, quantity=1.0)
    assert broker.open_symbols() == ["ETH/USDT"]
    assert broker.position("ETH/USDT").quantity == pytest.approx(2.0)
