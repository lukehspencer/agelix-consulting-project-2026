from pathlib import Path

import joblib
import numpy as np

from rul.feature_engineering import validate_feature_vector

_MODEL_PATH = Path(__file__).parent / "model.pkl"

_CI_HALF_WIDTH = 1.5


def _load_model():
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model file not found at {_MODEL_PATH}. "
            "Run rul/train.py first to generate model.pkl"
        )
    return joblib.load(_MODEL_PATH)


_model = None


def _get_model():
    global _model
    if _model is None:
        _model = _load_model()
    return _model


def predict(feature_vector: list[float]) -> dict:
    validate_feature_vector(feature_vector)
    model = _get_model()
    X = np.array([feature_vector])
    raw_prediction = float(model.predict(X)[0])
    rul_years = round(max(0.0, raw_prediction), 1)
    return {
        "rul_years": rul_years,
        "ci_low": round(max(0.0, rul_years - _CI_HALF_WIDTH), 1),
        "ci_high": round(rul_years + _CI_HALF_WIDTH, 1),
    }
