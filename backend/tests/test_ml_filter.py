import numpy as np
import pandas as pd
import joblib
import pytest

from app import ml_filter


class _StubModel:
    classes_ = [0, 1]

    def predict_proba(self, X):
        return np.tile([0.4, 0.6], (len(X), 1))


def _synthetic_candles(n=100, seed=1):
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


@pytest.fixture(autouse=True)
def _reset_cache():
    ml_filter.MlFilter._cache.clear()
    yield
    ml_filter.MlFilter._cache.clear()


def test_load_returns_none_when_no_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_filter, "MODELS_DIR", tmp_path)
    assert ml_filter.MlFilter.load("BTC/USDT", "5m") is None


def test_load_and_predict_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_filter, "MODELS_DIR", tmp_path)
    joblib.dump(
        {"model": _StubModel(), "feature_params": {"fast_period": 9, "slow_period": 21, "rsi_period": 14}},
        tmp_path / "BTC_USDT_5m.joblib",
    )

    loaded = ml_filter.MlFilter.load("BTC/USDT", "5m")
    assert loaded is not None
    proba = loaded.predict_up_probability(_synthetic_candles())
    assert proba == pytest.approx(0.6)


def test_load_is_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_filter, "MODELS_DIR", tmp_path)
    joblib.dump(
        {"model": _StubModel(), "feature_params": {}},
        tmp_path / "ETH_USDT_1h.joblib",
    )
    first = ml_filter.MlFilter.load("ETH/USDT", "1h")
    (tmp_path / "ETH_USDT_1h.joblib").unlink()
    second = ml_filter.MlFilter.load("ETH/USDT", "1h")
    assert first is second


def test_list_available_models(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_filter, "MODELS_DIR", tmp_path)
    joblib.dump({"model": _StubModel(), "feature_params": {}}, tmp_path / "BTC_USDT_5m.joblib")
    joblib.dump({"model": _StubModel(), "feature_params": {}}, tmp_path / "ETH_USDT_1h.joblib")

    models = ml_filter.list_available_models()
    assert {"symbol": "BTC/USDT", "timeframe": "5m"} in models
    assert {"symbol": "ETH/USDT", "timeframe": "1h"} in models
