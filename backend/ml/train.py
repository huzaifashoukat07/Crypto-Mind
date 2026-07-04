"""Train and honestly evaluate the optional ML confirmation filter.

Fetches real historical OHLCV data for a symbol/timeframe, trains a gradient-
boosting classifier to predict short-term upward moves, and -- critically --
backtests the *actual trading strategy* on a held-out chronological slice
both with and without the filter, so you see whether it helps before you
ever point it at your money. This is a research/offline tool, not something
the live bot runs -- run it, look at the report, and only enable
`use_ml_filter` in the UI if the "with filter" numbers actually look better
than the baseline on your own data.

Usage (from the `backend/` directory, with the venv activated):
    python -m ml.train --symbol BTC/USDT --timeframe 5m --days 180

The trained model is saved to backend/ml/models/<SYMBOL>_<TIMEFRAME>.joblib,
which `app/ml_filter.py` picks up automatically at runtime.
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ccxt  # noqa: E402
import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import accuracy_score, classification_report  # noqa: E402

from app.features import FEATURE_COLUMNS, compute_features, predict_up_probability  # noqa: E402
from app.paper_broker import PaperBroker  # noqa: E402
from app.schemas import OrderSide  # noqa: E402
from app.strategy import MaCrossoverRsiStrategy, StrategyParams  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
BACKTEST_SYMBOL = "BT"  # internal key for the PaperBroker instance used below


def fetch_history(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    exchange = ccxt.binance({"enableRateLimit": True})
    tf_seconds = exchange.parse_timeframe(timeframe)
    now_ms = exchange.milliseconds()
    since = now_ms - days * 24 * 60 * 60 * 1000

    rows: list[list[float]] = []
    print(f"Fetching {days}d of {timeframe} candles for {symbol}...")
    while since < now_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        next_since = batch[-1][0] + tf_seconds * 1000
        if next_since <= since:
            break
        since = next_since
        print(f"  ...{len(rows)} candles so far", end="\r")
        if len(batch) < 1000:
            break
        time.sleep(exchange.rateLimit / 1000)
    print()

    df = pd.DataFrame(rows, columns=["time_ms", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="time_ms").sort_values("time_ms").reset_index(drop=True)
    df["time"] = (df["time_ms"] // 1000).astype(int)
    return df[["time", "open", "high", "low", "close", "volume"]]


def build_labels(df: pd.DataFrame, horizon: int, up_threshold: float) -> pd.Series:
    future_close = df["close"].shift(-horizon)
    future_return = future_close / df["close"] - 1
    label = (future_return > up_threshold).astype(float)
    label[future_close.isna()] = np.nan
    return label


def simulate(
    df: pd.DataFrame,
    params: StrategyParams,
    start_idx: int,
    end_idx: int,
    *,
    starting_balance: float,
    position_size_pct: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    ml_model=None,
    ml_feature_params: dict | None = None,
    ml_threshold: float = 0.55,
) -> dict:
    """Replays the same signal/risk logic as the live BotEngine over
    df[start_idx:end_idx], optionally gating buy signals on the ML model, and
    reports the resulting PnL. Not a claim of future performance -- just an
    honest comparison on this one historical slice."""
    strategy = MaCrossoverRsiStrategy(params)
    broker = PaperBroker(balance_quote=starting_balance)
    round_trips: list[float] = []

    for t in range(start_idx, end_idx + 1):
        window = df.iloc[: t + 1]
        price = float(window["close"].iloc[-1])
        pos = broker.position(BACKTEST_SYMBOL)
        in_position = pos.quantity > 0

        if in_position and pos.entry_price:
            change_pct = (price - pos.entry_price) / pos.entry_price * 100
            if change_pct <= -stop_loss_pct or change_pct >= take_profit_pct:
                pnl = broker.execute(BACKTEST_SYMBOL, OrderSide.sell, price, pos.quantity)
                round_trips.append(pnl)
                continue

        output = strategy.evaluate(window, in_position=in_position)
        if output.signal == "sell" and in_position:
            pnl = broker.execute(BACKTEST_SYMBOL, OrderSide.sell, price, pos.quantity)
            round_trips.append(pnl)
        elif output.signal == "buy" and not in_position:
            if ml_model is not None:
                proba = predict_up_probability(ml_model, window, ml_feature_params)
                if proba is None or proba < ml_threshold:
                    continue
            budget = broker.balance_quote * (position_size_pct / 100)
            qty = budget / price
            if qty > 0:
                broker.execute(BACKTEST_SYMBOL, OrderSide.buy, price, qty)

    final_pos = broker.position(BACKTEST_SYMBOL)
    if final_pos.quantity > 0:
        final_price = float(df["close"].iloc[end_idx])
        pnl = broker.execute(BACKTEST_SYMBOL, OrderSide.sell, final_price, final_pos.quantity)
        round_trips.append(pnl)

    wins = sum(1 for pnl in round_trips if pnl > 0)
    return {
        "final_balance": broker.balance_quote,
        "total_return_pct": (broker.balance_quote - starting_balance) / starting_balance * 100,
        "num_round_trips": len(round_trips),
        "win_rate_pct": (wins / len(round_trips) * 100) if round_trips else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--days", type=int, default=180, help="how much history to fetch")
    parser.add_argument("--horizon", type=int, default=6, help="candles ahead the label looks")
    parser.add_argument("--up-threshold", type=float, default=0.005, help="min future return counted as 'up', e.g. 0.005 = 0.5%%")
    parser.add_argument("--confidence-threshold", type=float, default=0.55, help="min predicted p(up) to pass the filter in the backtest")
    parser.add_argument("--test-split", type=float, default=0.2, help="fraction of the most recent data held out for testing/backtest")
    parser.add_argument("--fast-period", type=int, default=9)
    parser.add_argument("--slow-period", type=int, default=21)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-overbought", type=float, default=70)
    parser.add_argument("--rsi-oversold", type=float, default=30)
    parser.add_argument("--position-size-pct", type=float, default=25)
    parser.add_argument("--stop-loss-pct", type=float, default=2)
    parser.add_argument("--take-profit-pct", type=float, default=4)
    parser.add_argument("--starting-balance", type=float, default=1000)
    args = parser.parse_args()

    feature_params = {
        "fast_period": args.fast_period,
        "slow_period": args.slow_period,
        "rsi_period": args.rsi_period,
    }
    strategy_params = StrategyParams(
        fast_period=args.fast_period,
        slow_period=args.slow_period,
        rsi_period=args.rsi_period,
        rsi_overbought=args.rsi_overbought,
        rsi_oversold=args.rsi_oversold,
    )

    df = fetch_history(args.symbol, args.timeframe, args.days)
    print(f"Fetched {len(df)} candles.")

    features = compute_features(df, **feature_params)
    labels = build_labels(df, args.horizon, args.up_threshold)
    dataset = features.copy()
    dataset["label"] = labels
    dataset = dataset.dropna()
    if len(dataset) < 200:
        print(f"Only {len(dataset)} usable rows after dropping warmup/NaN -- fetch more --days. Aborting.")
        return

    split_idx = int(len(dataset) * (1 - args.test_split))
    train_set = dataset.iloc[:split_idx]
    test_set = dataset.iloc[split_idx:]
    print(f"Train rows: {len(train_set)}  Test rows: {len(test_set)}")
    print(f"Label balance (train): up={train_set['label'].mean():.1%}  Label balance (test): up={test_set['label'].mean():.1%}")

    model = HistGradientBoostingClassifier(max_depth=4, max_iter=200, random_state=42)
    model.fit(train_set[FEATURE_COLUMNS], train_set["label"])

    preds = model.predict(test_set[FEATURE_COLUMNS])
    print("\n=== Raw classifier performance on held-out data ===")
    print(f"Accuracy: {accuracy_score(test_set['label'], preds):.3f}")
    print(classification_report(test_set["label"], preds, target_names=["down/flat", "up"], zero_division=0))

    test_start_idx = int(test_set.index.min())
    test_end_idx = int(test_set.index.max())

    common_kwargs = dict(
        starting_balance=args.starting_balance,
        position_size_pct=args.position_size_pct,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
    )
    baseline = simulate(df, strategy_params, test_start_idx, test_end_idx, **common_kwargs)
    filtered = simulate(
        df,
        strategy_params,
        test_start_idx,
        test_end_idx,
        ml_model=model,
        ml_feature_params=feature_params,
        ml_threshold=args.confidence_threshold,
        **common_kwargs,
    )

    print("\n=== Strategy backtest on held-out period (same window for both) ===")
    print(f"{'':20s}{'Baseline (no filter)':>22s}{'With ML filter':>18s}")
    print(f"{'Total return %':20s}{baseline['total_return_pct']:>22.2f}{filtered['total_return_pct']:>18.2f}")
    print(f"{'Round-trip trades':20s}{baseline['num_round_trips']:>22d}{filtered['num_round_trips']:>18d}")
    print(f"{'Win rate %':20s}{baseline['win_rate_pct']:>22.1f}{filtered['win_rate_pct']:>18.1f}")
    print(
        "\nThis is one historical slice, not a guarantee -- if 'With ML filter' isn't "
        "clearly better here, it's unlikely to help live. Try different --horizon / "
        "--up-threshold / --days values before trusting it."
    )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    safe_symbol = args.symbol.replace("/", "_")
    model_path = MODELS_DIR / f"{safe_symbol}_{args.timeframe}.joblib"
    joblib.dump(
        {
            "model": model,
            "feature_params": feature_params,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "horizon": args.horizon,
            "up_threshold": args.up_threshold,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        },
        model_path,
    )
    print(f"\nSaved model to {model_path}")


if __name__ == "__main__":
    main()
