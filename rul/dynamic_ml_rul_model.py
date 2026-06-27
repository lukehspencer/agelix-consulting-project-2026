from pathlib import Path

import joblib
import numpy as np

_CI_HALF_WIDTH = 1.5

_cache = {}


def _load_bundle(model_path: str) -> dict:
    if model_path in _cache:
        return _cache[model_path]

    p = Path(model_path)
    if not p.exists():
        raise FileNotFoundError(
            f"Dynamic model not found at '{model_path}'. "
            "Run rul/dynamic_train.py first to train a model for this dataset."
        )

    bundle = joblib.load(p)
    _cache[model_path] = bundle
    return bundle


def predict_dynamic(feature_vector: list,
                    model_path: str = "rul/dynamic_model.pkl") -> dict:
    bundle = _load_bundle(model_path)
    expected_names = bundle["feature_names"]
    expected_len = len(expected_names)

    if len(feature_vector) != expected_len:
        raise ValueError(
            f"Feature vector length mismatch: expected {expected_len}, "
            f"got {len(feature_vector)}. "
            f"Expected features: {expected_names}"
        )

    X = np.array([feature_vector])
    raw = float(bundle["model"].predict(X)[0])
    rul_years = round(max(0.0, raw), 1)

    return {
        "rul_years": rul_years,
        "ci_low": round(max(0.0, rul_years - _CI_HALF_WIDTH), 1),
        "ci_high": round(rul_years + _CI_HALF_WIDTH, 1),
    }


def predict_adjusted_dynamic(feature_vector: list,
                              risk_factor: float,
                              model_path: str = "rul/dynamic_model.pkl") -> dict:
    result = predict_dynamic(feature_vector, model_path)
    r_asset = (risk_factor - 1) / 8
    rul_adjusted = round(max(0.0, result["rul_years"] * (1 - r_asset)), 1)

    return {
        "rul_years": rul_adjusted,
        "ci_low": round(max(0.0, rul_adjusted - _CI_HALF_WIDTH), 1),
        "ci_high": round(rul_adjusted + _CI_HALF_WIDTH, 1),
    }
