import numpy as np
import pandas as pd
import pytest

from app.features import FEATURE_COLUMNS, compute_features, predict_up_probability


def _synthetic_candles(n=200, seed=0):
    rng = np.random.default_rng(seed)
    close = pd.Series(50000 + np.cumsum(rng.normal(0, 20, size=n)))
    return pd.DataFrame(
        {
            "time": range(n),
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": rng.uniform(1, 10, size=n),
        }
    )


def test_compute_features_returns_expected_columns():
    df = _synthetic_candles()
    features = compute_features(df)
    assert list(features.columns) == FEATURE_COLUMNS
    assert len(features) == len(df)


def test_compute_features_warms_up_then_stabilizes():
    df = _synthetic_candles(n=100)
    features = compute_features(df)
    # early rows lack enough history for rolling/ewm windows
    assert features.iloc[0].isna().any()
    # by the end, every feature should be defined
    assert not features.iloc[-1].isna().any()


class _StubModel:
    """Minimal stand-in for a fitted sklearn classifier."""

    classes_ = [0, 1]

    def predict_proba(self, X):
        return np.tile([0.3, 0.7], (len(X), 1))


def test_predict_up_probability_returns_value_once_warmed_up():
    df = _synthetic_candles(n=100)
    proba = predict_up_probability(_StubModel(), df)
    assert proba == pytest.approx(0.7)


def test_predict_up_probability_returns_none_when_not_enough_history():
    df = _synthetic_candles(n=5)
    proba = predict_up_probability(_StubModel(), df)
    assert proba is None


def test_predict_up_probability_returns_none_without_up_class():
    class _OnlyDownModel:
        classes_ = [0]

        def predict_proba(self, X):
            return np.ones((len(X), 1))

    df = _synthetic_candles(n=100)
    assert predict_up_probability(_OnlyDownModel(), df) is None
