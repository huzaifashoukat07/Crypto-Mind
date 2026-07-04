"""Shared feature engineering for the optional ML confirmation filter.

Used by both `backend/ml/train.py` (offline training/backtesting) and
`backend/app/ml_filter.py` (live inference), so the exact same feature
definitions are computed both times -- training/serving skew is the most
common way an ML filter like this silently stops matching what it was
trained on.
"""
import numpy as np
import pandas as pd

from .strategy import rsi as _rsi, sma as _sma

FEATURE_COLUMNS = [
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_pct",
    "bb_width",
    "volume_ratio",
    "momentum",
    "volatility",
    "ma_gap_pct",
]


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def compute_features(
    candles: pd.DataFrame,
    fast_period: int = 9,
    slow_period: int = 21,
    rsi_period: int = 14,
) -> pd.DataFrame:
    """Returns a DataFrame aligned with `candles`, one row of features per candle.
    Early rows (before enough history has accumulated for a given indicator)
    are NaN, same as the underlying rolling/ewm computations."""
    close = candles["close"]
    volume = candles["volume"]

    rsi_val = _rsi(close, rsi_period)

    ema_fast = _ema(close, 12)
    ema_slow = _ema(close, 26)
    macd = ema_fast - ema_slow
    macd_signal = _ema(macd, 9)
    macd_hist = macd - macd_signal

    sma20 = _sma(close, 20)
    std20 = close.rolling(window=20, min_periods=20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    band_range = (upper - lower).replace(0, np.nan)
    bb_pct = (close - lower) / band_range
    bb_width = band_range / sma20.replace(0, np.nan)

    volume_ma20 = volume.rolling(window=20, min_periods=20).mean().replace(0, np.nan)
    volume_ratio = volume / volume_ma20

    momentum = close.pct_change(periods=10)
    volatility = close.pct_change().rolling(window=20, min_periods=20).std()

    fast_ma = _sma(close, fast_period)
    slow_ma = _sma(close, slow_period)
    ma_gap_pct = (fast_ma - slow_ma) / slow_ma.replace(0, np.nan)

    return pd.DataFrame(
        {
            "rsi": rsi_val,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "bb_pct": bb_pct,
            "bb_width": bb_width,
            "volume_ratio": volume_ratio,
            "momentum": momentum,
            "volatility": volatility,
            "ma_gap_pct": ma_gap_pct,
        },
        index=candles.index,
    )


def predict_up_probability(model, candles: pd.DataFrame, feature_params: dict | None = None) -> float | None:
    """Scores the probability of an upward move using the last row of computed
    features. Returns None if there isn't enough history yet for every
    feature to be defined, or if the model was never trained on both classes
    (both used by `ml_filter.py` at live inference and `ml/train.py` during
    backtesting, so the two stay consistent)."""
    features = compute_features(candles, **(feature_params or {}))
    last = features.iloc[-1]
    if last.isna().any():
        return None
    classes = list(model.classes_)
    if 1 not in classes:
        return None
    x = last[FEATURE_COLUMNS].to_frame().T
    proba = model.predict_proba(x)[0]
    return float(proba[classes.index(1)])
