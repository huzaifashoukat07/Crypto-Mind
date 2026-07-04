import logging
from pathlib import Path
from typing import Optional

import joblib
import pandas as pd

from .features import predict_up_probability

logger = logging.getLogger("ml_filter")

MODELS_DIR = Path(__file__).resolve().parent.parent / "ml" / "models"


def _model_path(symbol: str, timeframe: str) -> Path:
    safe_symbol = symbol.replace("/", "_")
    return MODELS_DIR / f"{safe_symbol}_{timeframe}.joblib"


def list_available_models() -> list[dict]:
    if not MODELS_DIR.exists():
        return []
    out = []
    for path in sorted(MODELS_DIR.glob("*.joblib")):
        symbol, _, timeframe = path.stem.rpartition("_")
        if not symbol:
            continue
        out.append({"symbol": symbol.replace("_", "/"), "timeframe": timeframe})
    return out


class MlFilter:
    """Loads a trained per-symbol/timeframe classifier produced by
    `backend/ml/train.py` and scores the probability of an upward move, used
    as an optional second-opinion gate on top of the base MA/RSI strategy
    signal. Models are cached per-process since they don't change while a bot
    is running."""

    _cache: dict[str, Optional["MlFilter"]] = {}

    def __init__(self, model, feature_params: dict):
        self.model = model
        self.feature_params = feature_params

    @classmethod
    def load(cls, symbol: str, timeframe: str) -> Optional["MlFilter"]:
        key = f"{symbol}:{timeframe}"
        if key in cls._cache:
            return cls._cache[key]
        path = _model_path(symbol, timeframe)
        instance: Optional["MlFilter"] = None
        if path.exists():
            try:
                payload = joblib.load(path)
                instance = cls(payload["model"], payload.get("feature_params", {}))
            except Exception:  # noqa: BLE001
                logger.exception(f"failed to load ML model at {path}")
        cls._cache[key] = instance
        return instance

    def predict_up_probability(self, candles: pd.DataFrame) -> Optional[float]:
        return predict_up_probability(self.model, candles, self.feature_params)
