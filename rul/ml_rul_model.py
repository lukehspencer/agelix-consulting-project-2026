from pathlib import Path

import joblib
import numpy as np

from rul.feature_engineering import validate_feature_vector

_MODEL_PATH = Path(__file__).parent / "model.pkl"
_CI_HALF_WIDTH = 1.5


def _load_model():
    if not _MODEL_PATH.exists():
        raise RuntimeError(
            "Run rul/train.py first to generate model.pkl"
        )
    return joblib.load(_MODEL_PATH)


_model = _load_model()


def predict(feature_vector: list) -> dict:
    validate_feature_vector(feature_vector)
    X = np.array([feature_vector])
    raw = float(_model.predict(X)[0])
    rul_years = round(max(0.0, raw), 1)
    return {
        "rul_years": rul_years,
        "ci_low": round(max(0.0, rul_years - _CI_HALF_WIDTH), 1),
        "ci_high": round(rul_years + _CI_HALF_WIDTH, 1),
    }


def predict_adjusted(feature_vector: list, risk_factor: float) -> dict:
    result = predict(feature_vector)
    r_asset = (risk_factor - 1) / 8
    rul_adjusted = round(max(0.0, result["rul_years"] * (1 - r_asset)), 1)
    return {
        "rul_years": rul_adjusted,
        "ci_low": round(max(0.0, rul_adjusted - _CI_HALF_WIDTH), 1),
        "ci_high": round(rul_adjusted + _CI_HALF_WIDTH, 1),
    }
